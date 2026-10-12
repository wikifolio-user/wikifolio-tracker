"""Tests fuer den Kurs-Alarm-Job (python3 -m unittest test_alarm).

Ohne Netz: ls-tc.de, Discord und die GitHub-Contents-API sind gemockt. Nutzt
die echte config.py, echte chronik.py und das echte github_store-Modul (nur
dessen Netz-Funktionen werden durch einen In-Memory-Speicher ersetzt).
"""
import copy
import datetime
import logging
import time
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import requests

import config
import github_store as G
import discord_price_alert as D

# Laufende Ausgaben stumm schalten (assertLogs setzt den Level selbst).
logging.getLogger().setLevel(logging.CRITICAL)

BERLIN = ZoneInfo("Europe/Berlin")
WEBHOOK = "https://discord.com/api/webhooks/123456/GEHEIMES-TOKEN-xyz"
ALARM = config.STATE_PATH_PRICE_ALERT
HW = config.STATE_PATH_HIGH_WATERMARK
CHRONIK = config.STATE_PATH_TRADES_DB
INST = {"wkn": config.WKN, "name": "Hauptindizes Global", "instrument_id": "1", "onvista_url": None}


class FakeStore:
    """In-Memory-Ersatz fuer github_store (gleiche Signaturen/Semantik)."""

    def __init__(self):
        self.dateien = {}
        self.writes = []
        self.put_fehler = set()    # Pfade, deren Schreiben fehlschlaegt
        self.lese_fehler = set()   # Pfade, deren Lesen fehlschlaegt

    def lese_json(self, repo, branch, path, token, default=None):
        if path in self.lese_fehler:
            raise G.LeseFehler(f"{path}: HTTP 503")
        return copy.deepcopy(self.dateien.get(path, default)), "sha"

    def get_json(self, repo, branch, path, token, default=None):
        try:
            return self.lese_json(repo, branch, path, token, default)
        except G.LeseFehler:
            return default, None

    def put_json(self, repo, branch, path, obj, token, message="", max_retries=3, sha=None):
        self.writes.append(path)
        if path in self.put_fehler:
            return False
        self.dateien[path] = copy.deepcopy(obj)
        return True

    def aktualisiere_json(self, repo, branch, path, token, aendern, default=None, message="", max_retries=4):
        try:
            daten, _ = self.lese_json(repo, branch, path, token, copy.deepcopy(default))
        except G.LeseFehler:
            return False, None
        neu = aendern(copy.deepcopy(daten))
        if neu is None:
            return True, daten
        return (True, neu) if self.put_json(repo, branch, path, neu, token) else (False, None)

    def append_csv_line(self, *a, **k):
        return True


class Basis(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.gesendet = []          # Titel aller Discord-Versuche
        self.discord_ok = True
        self.now = datetime.datetime(2026, 10, 9, 11, 0, tzinfo=BERLIN)
        self.hist_abrufe = 0

        def fake_send(msg=None, embed=None):
            self.gesendet.append(embed["title"] if embed else msg)
            return self.discord_ok

        def fake_hist(_iid):
            self.hist_abrufe += 1
            return None, None

        patches = [
            mock.patch.multiple(G, lese_json=self.store.lese_json, get_json=self.store.get_json,
                                put_json=self.store.put_json, aktualisiere_json=self.store.aktualisiere_json,
                                append_csv_line=self.store.append_csv_line),
            mock.patch.object(D, "GITHUB_REPO", "owner/repo"),
            mock.patch.object(D, "GITHUB_TOKEN", "tok"),
            mock.patch.object(D, "send_discord", fake_send),
            mock.patch.object(D, "hole_historischen_hoechststand", fake_hist),
            mock.patch.object(D, "hole_onvista_kontrollkurs", lambda url: None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def lauf(self, akt, vor=100.0, hoch=None, minuten=5):
        self.now += datetime.timedelta(minutes=minuten)
        with mock.patch.object(D, "get_live_market_data", lambda iid: (akt, vor, akt if hoch is None else hoch)):
            return D.verarbeite_instrument(INST, self.now)

    def titel(self, teil):
        return [t for t in self.gesendet if teil in t]

    def chronik_schluessel(self):
        return [e["schluessel"] for e in self.store.dateien.get(CHRONIK, [])]


class TestDiscordFehler(Basis):
    """ALM-01: State nur fortschreiben, wenn Discord die Nachricht angenommen hat."""

    def test_alarm_wird_nach_fehlgeschlagenem_versand_wiederholt(self):
        self.discord_ok = False
        self.lauf(98.0)                                   # -2 % <= -1 % Schwelle
        self.assertEqual(len(self.titel("SCHWELLE")), 1)
        self.assertFalse(self.store.dateien.get(ALARM, {}).get("unter_schwelle"))
        self.assertEqual(self.chronik_schluessel(), [])  # keine Chronik ohne Zustellung
        self.discord_ok = True
        self.lauf(97.9)
        self.assertEqual(len(self.titel("SCHWELLE")), 2)  # Retry im naechsten Lauf
        self.assertTrue(self.store.dateien[ALARM]["unter_schwelle"])
        self.lauf(97.8)
        self.assertEqual(len(self.titel("SCHWELLE")), 2)  # danach kein weiterer Alarm
        self.assertEqual(self.chronik_schluessel(), ["schwelle-LS9VFS-20261009"])

    def test_entwarnung_wird_nach_fehlgeschlagenem_versand_wiederholt(self):
        self.lauf(98.0)
        self.discord_ok = False
        self.lauf(100.5)
        self.assertTrue(self.store.dateien[ALARM]["unter_schwelle"])
        self.discord_ok = True
        self.lauf(100.4)
        self.assertEqual(len(self.titel("Entwarnung")), 2)
        self.assertFalse(self.store.dateien[ALARM]["unter_schwelle"])

    def test_allzeithoch_wird_nach_fehlgeschlagenem_versand_nachgeholt(self):
        self.store.dateien[HW] = {"high_watermark": 100.0, "zuletzt_gemeldet": 100.0, "historie_geprueft": True}
        self.discord_ok = False
        self.lauf(102.0, vor=101.5)
        self.assertEqual(self.store.dateien[HW]["zuletzt_gemeldet"], 100.0)
        self.assertEqual(self.store.dateien[HW]["high_watermark"], 102.0)
        self.discord_ok = True
        self.lauf(101.8, vor=101.5)                        # Kurs schon wieder etwas tiefer
        self.assertEqual(len(self.titel("Allzeithoch")), 2)
        self.assertEqual(self.store.dateien[HW]["zuletzt_gemeldet"], 102.0)
        self.assertIn("ath-LS9VFS-102.00", self.chronik_schluessel())
        self.lauf(101.9, vor=101.5)
        self.assertEqual(len(self.titel("Allzeithoch")), 2)


class TestSendDiscord(unittest.TestCase):
    def antwort(self, status, headers=None, body=None):
        r = mock.Mock(status_code=status, headers=headers or {}, text=f"fehler {WEBHOOK}")
        r.json = mock.Mock(return_value=body or {})
        return r

    def setUp(self):
        p = mock.patch.object(D, "DISCORD_WEBHOOK_URL", WEBHOOK)
        p.start()
        self.addCleanup(p.stop)

    def test_nur_2xx_ist_erfolg(self):
        for status, erwartet in ((200, True), (204, True), (400, False), (404, False), (500, False)):
            with mock.patch.object(D.requests, "post", return_value=self.antwort(status)):
                self.assertIs(D.send_discord(msg="x"), erwartet, status)

    def test_429_kurz_ein_retry(self):
        with mock.patch.object(D.requests, "post", side_effect=[self.antwort(429, {"Retry-After": "0.2"}),
                                                                self.antwort(204)]) as post, \
                mock.patch.object(D.time, "sleep") as schlaf:
            self.assertTrue(D.send_discord(msg="x"))
        self.assertEqual(post.call_count, 2)
        schlaf.assert_called_once_with(0.2)

    def test_429_maximal_ein_retry_und_kein_langes_warten(self):
        with mock.patch.object(D.requests, "post", return_value=self.antwort(429, {"Retry-After": "0.1"})) as post, \
                mock.patch.object(D.time, "sleep"):
            self.assertFalse(D.send_discord(msg="x"))
        self.assertEqual(post.call_count, 2)
        with mock.patch.object(D.requests, "post", return_value=self.antwort(429, {"Retry-After": "60"})) as post, \
                mock.patch.object(D.time, "sleep") as schlaf:
            self.assertFalse(D.send_discord(msg="x"))
        self.assertEqual(post.call_count, 1)
        schlaf.assert_not_called()

    def test_keine_url_im_log(self):
        fehler = requests.ConnectionError(f"Max retries exceeded with url: {WEBHOOK}")
        with mock.patch.object(D.requests, "post", side_effect=fehler), \
                self.assertLogs(level="DEBUG") as logs:
            self.assertFalse(D.send_discord(msg="x"))
        with mock.patch.object(D.requests, "post", return_value=self.antwort(500)), \
                self.assertLogs(level="DEBUG") as logs2:
            self.assertFalse(D.send_discord(msg="x"))
        text = "\n".join(logs.output + logs2.output)
        self.assertNotIn("GEHEIMES-TOKEN", text)
        self.assertNotIn("webhooks", text)
        self.assertIn("ConnectionError", text)


class TestHysterese(Basis):
    """ALM-03"""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(config, "TAGESVERLUST_SCHWELLE_PCT", -3.0)
        p.start()
        self.addCleanup(p.stop)

    def test_flattern_um_die_schwelle(self):
        for pct in (-3.01, -2.99, -3.01, -2.99, -3.02):
            self.lauf(100.0 + pct)
        self.assertEqual(len(self.titel("SCHWELLE")), 1)
        self.assertEqual(len(self.titel("Entwarnung")), 0)

    def test_entwarnung_erst_ab_schwelle_plus_hysterese(self):
        self.lauf(96.9)
        self.lauf(97.4)                                    # -2,6 % < -2,5 %
        self.assertEqual(self.titel("Entwarnung"), [])
        self.lauf(97.5)                                    # -2,5 % = Schwelle + 0,5
        self.assertEqual(len(self.titel("Entwarnung")), 1)

    def test_hysterese_ueber_config_einstellbar(self):
        with mock.patch.object(config, "ALARM_HYSTERESE_PP", 1.0, create=True):
            self.lauf(96.9)
            self.lauf(97.6)
            self.assertEqual(self.titel("Entwarnung"), [])
            self.lauf(98.0)
            self.assertEqual(len(self.titel("Entwarnung")), 1)

    def test_neuer_handelstag_setzt_zustand_zurueck(self):
        self.lauf(96.9)
        self.assertEqual(self.store.dateien[ALARM]["handelstag"], "2026-10-09")
        self.lauf(96.8, minuten=24 * 60)                   # naechster Tag, immer noch unter Schwelle
        self.assertEqual(len(self.titel("SCHWELLE")), 2)
        self.assertEqual(self.store.dateien[ALARM]["handelstag"], "2026-10-10")
        self.assertEqual(self.titel("Entwarnung"), [])


class TestPlausibilitaet(Basis):
    """ALM-04 / DEP-04"""

    def test_unplausibler_tick_erzeugt_kein_allzeithoch(self):
        vorher = {"high_watermark": 100.0, "zuletzt_gemeldet": 100.0, "historie_geprueft": True}
        self.store.dateien[HW] = copy.deepcopy(vorher)
        self.lauf(99.0, vor=99.5, hoch=990.0)
        self.assertEqual(self.titel("Allzeithoch"), [])
        self.assertEqual(self.store.dateien[HW], vorher)

    def test_plausibles_tageshoch_wird_uebernommen(self):
        self.store.dateien[HW] = {"high_watermark": 100.0, "zuletzt_gemeldet": 100.0, "historie_geprueft": True}
        self.lauf(99.0, vor=99.5, hoch=101.0)
        self.assertEqual(len(self.titel("Allzeithoch")), 1)
        self.assertEqual(self.store.dateien[HW]["high_watermark"], 101.0)

    def _ls_antwort(self, ticks, plotlines=True):
        body = {"series": {"intraday": {"data": ticks}, "history": {"data": []}}}
        if plotlines:
            body["info"] = {"plotlines": [{"id": "previousDay", "value": 99.5}]}
        r = mock.Mock(status_code=200)
        r.json = mock.Mock(return_value=body)
        r.raise_for_status = mock.Mock()
        return r

    def test_fetch_filtert_fehlticks(self):
        ts = int(datetime.datetime.now(BERLIN).timestamp() * 1000)
        ticks = [[ts - 3000, 99.6], [ts - 2000, 990.0], [ts - 1000, 100.2], [ts, 99.0]]
        with mock.patch.object(D.requests, "get", return_value=self._ls_antwort(ticks)):
            akt, vor, hoch = D.get_live_market_data("1")
        self.assertEqual((akt, vor, hoch), (99.0, 99.5, 100.2))

    def test_fetch_ohne_vortageskurs_kein_ersatzwert(self):
        ts = int(datetime.datetime.now(BERLIN).timestamp() * 1000)
        with mock.patch.object(D.requests, "get", return_value=self._ls_antwort([[ts, 99.0]], plotlines=False)):
            with self.assertRaises(ValueError):
                D.get_live_market_data("1")

    def test_fetch_veraltete_ticks(self):
        gestern = int((datetime.datetime.now(BERLIN) - datetime.timedelta(days=1)).timestamp() * 1000)
        with mock.patch.object(D.requests, "get", return_value=self._ls_antwort([[gestern, 99.0]])):
            with self.assertRaises(D.VeralteteDaten):
                D.get_live_market_data("1")


class TestStateUndChronik(Basis):
    def test_state_update_erhaelt_felder(self):
        """ALM-05"""
        self.store.dateien[HW] = {"high_watermark": 100.0, "zuletzt_gemeldet": 100.0,
                                  "historie_geprueft": True, "eigenes_feld": "bleibt"}
        self.lauf(100.2, vor=100.0)                        # neues Hoch, still (unter Meldeschwelle)
        hw = self.store.dateien[HW]
        self.assertEqual(hw["high_watermark"], 100.2)
        self.assertTrue(hw["historie_geprueft"])
        self.assertEqual(hw["eigenes_feld"], "bleibt")
        self.lauf(100.3, vor=100.0)
        self.assertEqual(self.hist_abrufe, 0)              # keine erneute Selbstheilung

    def test_init_setzt_historie_geprueft(self):
        self.lauf(100.0, vor=100.0)
        self.lauf(100.1, vor=100.0)
        self.assertEqual(self.hist_abrufe, 1)
        self.assertTrue(self.store.dateien[HW]["historie_geprueft"])

    def test_chronik_schluessel_ereignisbasiert_kein_duplikat(self):
        """ALM-06: State-Write geht verloren -> Retry sendet erneut, Chronik bleibt einfach."""
        self.store.put_fehler.add(ALARM)
        with self.assertLogs(level="ERROR"):
            self.lauf(98.0)
        self.store.put_fehler.clear()
        self.lauf(97.9, minuten=7)
        self.assertEqual(len(self.titel("SCHWELLE")), 2)
        self.assertEqual(self.chronik_schluessel(), ["schwelle-LS9VFS-20261009"])

    def test_zweiter_alarm_am_selben_tag_eigener_schluessel(self):
        self.store.dateien[HW] = {"high_watermark": 150.0, "zuletzt_gemeldet": 150.0, "historie_geprueft": True}
        self.lauf(98.0)
        self.lauf(100.0)
        self.lauf(98.0)
        self.assertEqual(self.chronik_schluessel(),
                         ["schwelle-LS9VFS-20261009-2", "entwarnung-LS9VFS-20261009", "schwelle-LS9VFS-20261009"])


class TestKeineDatenKeinAlarm(Basis):
    """DEP-04"""

    def test_fetch_fehler_kein_state_kein_alarm(self):
        self.store.dateien[ALARM] = {"unter_schwelle": False, "handelstag": "2026-10-09"}

        def kaputt(_iid):
            raise requests.HTTPError(f"500 Server Error for url: {config.LS_TC_BASE_URL}?instrumentId=1")

        with mock.patch.object(D, "get_live_market_data", kaputt), self.assertLogs(level="ERROR") as logs:
            self.assertFalse(D.verarbeite_instrument(INST, self.now))
        self.assertEqual(self.store.writes, [])
        self.assertEqual(self.gesendet, [])
        self.assertNotIn("http", "\n".join(logs.output))

    def test_veraltete_daten_kein_state_kein_alarm(self):
        def alt(_iid):
            raise D.VeralteteDaten("Letzter Tick von gestern.")

        with mock.patch.object(D, "get_live_market_data", alt):
            self.assertTrue(D.verarbeite_instrument(INST, self.now))
        self.assertEqual(self.store.writes, [])
        self.assertEqual(self.gesendet, [])

    def test_state_lesefehler_kein_erneuter_alarm(self):
        self.store.dateien[ALARM] = {"unter_schwelle": True, "handelstag": "2026-10-09"}
        self.store.dateien[HW] = {"high_watermark": 50.0, "zuletzt_gemeldet": 50.0, "historie_geprueft": True}
        self.store.lese_fehler.update({ALARM, HW})
        self.assertFalse(self.lauf(98.0))
        self.assertEqual(self.titel("SCHWELLE"), [])
        self.assertEqual(self.titel("Allzeithoch"), [])
        self.assertNotIn(ALARM, self.store.writes)
        self.assertNotIn(HW, self.store.writes)

    def test_unplausibler_sprung_kein_alarm(self):
        self.assertTrue(self.lauf(50.0))                   # -50 % ohne Bestaetigung
        self.assertEqual(self.gesendet, [])
        self.assertEqual(self.store.writes, [])

    def test_main_ausserhalb_handelszeit_kein_abruf(self):
        samstag = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=BERLIN)
        with mock.patch.object(D, "verarbeite_instrument") as vi, \
                mock.patch.object(D, "ping_healthcheck"):
            D.main(samstag)
        vi.assert_not_called()

    def test_main_loggt_keine_url_bei_unerwartetem_fehler(self):
        montag = datetime.datetime(2026, 10, 12, 12, 0, tzinfo=BERLIN)
        fehler = RuntimeError(f"kaputt {WEBHOOK}")
        with mock.patch.object(D, "verarbeite_instrument", side_effect=fehler), \
                mock.patch.object(D, "ping_healthcheck"), \
                self.assertLogs(level="ERROR") as logs, \
                self.assertRaises(SystemExit):
            D.main(montag)
        self.assertNotIn("GEHEIMES-TOKEN", "\n".join(logs.output))

    def test_healthcheck_fehler_ohne_url(self):
        with mock.patch.object(D, "HEALTHCHECK_URL", "https://hc-ping.com/geheime-uuid"), \
                mock.patch.object(D.requests, "get",
                                  side_effect=requests.ConnectionError("url: https://hc-ping.com/geheime-uuid")), \
                self.assertLogs(level="ERROR") as logs:
            D.ping_healthcheck()
        self.assertNotIn("geheime-uuid", "\n".join(logs.output))


class TestHauptposition(Basis):
    """Die App sendet keine Alarme mehr - der Workflow muss fuer die Hauptposition
    alles abdecken: Routine-Update, Schwelle, Entwarnung, Allzeithoch."""

    def test_hauptposition_wird_ueberwacht(self):
        haupt = D.INSTRUMENTE[0]
        self.assertEqual(haupt["wkn"], config.WKN)
        self.assertEqual(haupt["instrument_id"], config.LS_INSTRUMENT_ID)
        self.assertEqual(D.state_pfad(config.STATE_PATH_PRICE_ALERT, haupt), config.STATE_PATH_PRICE_ALERT)
        self.assertEqual(D.state_pfad(config.STATE_PATH_HIGH_WATERMARK, haupt), config.STATE_PATH_HIGH_WATERMARK)

    def test_alle_meldungsarten_fuer_die_hauptposition(self):
        self.store.dateien[HW] = {"high_watermark": 101.0, "zuletzt_gemeldet": 101.0, "historie_geprueft": True}
        self.lauf(100.6)                                   # +0,6 % -> Routine-Update
        self.lauf(98.5)                                    # -1,5 % -> Schwelle (config -1 %)
        self.lauf(99.6)                                    # -0,4 % >= -0,5 % -> Entwarnung
        self.lauf(102.0, vor=101.0)                        # neues Hoch +0,99 % -> Allzeithoch
        for teil in ("Kurs-Update", "SCHWELLE", "Entwarnung", "Allzeithoch"):
            self.assertTrue(self.titel(teil), teil)
            self.assertTrue(all(config.WKN in t for t in self.titel(teil)))

    def test_routine_update_nur_bei_erfolg_gemerkt(self):
        self.discord_ok = False
        self.lauf(100.6)
        self.assertIsNone(self.store.dateien.get(ALARM, {}).get("zuletzt_gemeldet_pct"))
        self.discord_ok = True
        self.lauf(100.6)
        self.assertEqual(self.store.dateien[ALARM]["zuletzt_gemeldet_pct"], 0.6)
        self.lauf(100.7)                                   # zu nah an der letzten Meldung
        self.assertEqual(len(self.titel("Kurs-Update")), 2)


def _workflow():
    """price-alert.yml liegt im Repo unter .github/workflows/, beim Entwickeln ggf. daneben."""
    import pathlib
    hier = pathlib.Path(__file__).resolve().parent
    for pfad in (hier / ".github" / "workflows" / "price-alert.yml", hier / "price-alert.yml"):
        if pfad.exists():
            return pfad.read_text(encoding="utf-8")
    raise unittest.SkipTest("price-alert.yml nicht gefunden")


def _cron_feld_passt(feld, wert, lo):
    for teil in feld.split(","):
        schritt = 1
        if "/" in teil:
            teil, schritt = teil.split("/")
            schritt = int(schritt)
        if teil == "*":
            a, b = lo, 10 ** 6
        elif "-" in teil:
            a, b = map(int, teil.split("-"))
        else:
            a = b = int(teil)
        if a <= wert <= b and (wert - a) % schritt == 0:
            return True
    return False


def _cron_passt(ausdruck, t):
    minute, stunde, tag, monat, wtag = ausdruck.split()
    return (_cron_feld_passt(minute, t.minute, 0) and _cron_feld_passt(stunde, t.hour, 0)
            and _cron_feld_passt(tag, t.day, 1) and _cron_feld_passt(monat, t.month, 1)
            and _cron_feld_passt(wtag, t.isoweekday() % 7, 0))


class TestWorkflowZeitplan(unittest.TestCase):
    """ALM-02: Fallback-Schedule nur Mo-Fr, deckt 07:30-23:00 Berlin in Sommer- und Winterzeit ab."""

    def setUp(self):
        import re
        self.crons = re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', _workflow(), flags=re.M)
        self.assertTrue(self.crons)
        for c in self.crons:
            self.assertEqual(len(c.split()), 5, c)

    def laeufe(self, montag_utc):
        t = montag_utc
        ende = montag_utc + datetime.timedelta(days=7)
        aus = []
        while t < ende:
            if any(_cron_passt(c, t) for c in self.crons):
                aus.append(t.astimezone(BERLIN))
            t += datetime.timedelta(minutes=1)
        return aus

    def test_abdeckung_sommer_und_winter(self):
        utc = datetime.timezone.utc
        for montag in (datetime.datetime(2026, 7, 6, tzinfo=utc), datetime.datetime(2026, 1, 12, tzinfo=utc)):
            laeufe = self.laeufe(montag)
            self.assertFalse([t for t in laeufe if t.astimezone(datetime.timezone.utc).isoweekday() > 5],
                             "keine Laeufe an UTC-Wochenenden")
            for tag in range(5):
                datum = (montag + datetime.timedelta(days=tag)).date()
                im_handel = sorted(t for t in laeufe if t.date() == datum and config.ist_handelszeit(t))
                self.assertEqual((im_handel[0].hour, im_handel[0].minute), (7, 30), montag)
                self.assertEqual((im_handel[-1].hour, im_handel[-1].minute), (23, 0), montag)
                luecken = [(b - a).total_seconds() / 60 for a, b in zip(im_handel, im_handel[1:])]
                self.assertLessEqual(max(luecken), 15)
            # Leerlaeufe (enden im Gate-Schritt): hoechstens 6 je Handelstag
            leer = [t for t in laeufe if not config.ist_handelszeit(t)]
            self.assertLessEqual(len(leer), 6 * 5, montag)
            self.assertEqual(len(laeufe), 67 * 5)

    def _gate(self, wochentag, hhmm):
        import os
        import re
        import subprocess
        import tempfile
        skript = re.search(r"id: gate\n.*?run: \|\n(.*?)\n\s*\n", _workflow(), flags=re.S).group(1)
        skript = "\n".join(z[10:] if z.startswith(" " * 10) else z for z in skript.splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "date")
            with open(fake, "w") as f:
                f.write('#!/bin/sh\ncase "$*" in *%u*) echo "$FAKE_U";; *%H%M*) echo "$FAKE_HM";; '
                        '*) echo "Fake 00:00";; esac\n')
            os.chmod(fake, 0o755)
            ausgabe = os.path.join(tmp, "out")
            env = dict(os.environ, PATH=f"{tmp}:{os.environ.get('PATH', '')}", FAKE_U=str(wochentag),
                       FAKE_HM=hhmm, GITHUB_OUTPUT=ausgabe, HEALTHCHECK_URL="")
            r = subprocess.run(["bash", "-e", "-c", skript], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(ausgabe) as f:
                return f.read().strip()

    def test_gate_schritt(self):
        import shutil
        if not shutil.which("bash"):
            self.skipTest("bash fehlt")
        for wtag, hhmm, erwartet in ((1, "0729", "false"), (1, "0730", "true"), (3, "0959", "true"),
                                     (5, "2300", "true"), (5, "2301", "false"), (6, "1200", "false"),
                                     (7, "1800", "false"), (2, "0000", "false")):
            self.assertEqual(self._gate(wtag, hhmm), f"handelszeit={erwartet}", (wtag, hhmm))


if __name__ == "__main__":
    unittest.main()
