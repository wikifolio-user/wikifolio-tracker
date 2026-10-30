"""Kurs-Agent und Kurs-Vorrat (python3 -m unittest test_kurs_agent)."""
import datetime
import threading
import time
import unittest
from zoneinfo import ZoneInfo

import kurs_agent as A
import kurs_vorrat as KV
from kurs_dienst import KursDienst, KursFehlt

BERLIN = ZoneInfo("Europe/Berlin")
T0 = datetime.datetime(2026, 10, 30, 10, 0, tzinfo=BERLIN)


class Agent(unittest.TestCase):
    def test_ids_aus_verschachtelten_dateien(self):
        d = {"werte": [{"instrument_id": 123}, {"instrument_id": "456 "}, {"x": {"instrument_id": "abc"}}],
             "depots": {"a": {"positionen": [{"instrument_id": 789}, {"instrument_id": None}]}}}
        self.assertEqual(A.ids_in(d), {"123", "456", "789"})
        self.assertEqual(A.ids_in(None), set())

    def test_auswerten(self):
        antwort = {"series": {"intraday": {"data": [[1, 10.0], [2, 11.0], [3, 12.5]]},
                              "history": {"data": [[100, 9.0], [200, 9.5], [300, None]]}},
                   "info": {"plotlines": [{"id": "previousDay", "value": 9.5}]}}
        live, hist = A.auswerten(antwort, "2026-10-30T10:00:00+01:00")
        self.assertEqual(live["i"], [[1, 10.0], [3, 12.5]])
        self.assertEqual(live["p"], 9.5)
        self.assertEqual(hist, [[100, 9.0], [200, 9.5]])
        self.assertEqual(A.auswerten({"series": {}}, "x"), (None, None))

    def test_live_behaelt_alten_stand_bei_fehler_und_entfernt_ungenutzte(self):
        alt = {"werte": {"1": {"i": [[1, 1.0]], "t": "alt"}, "2": {"i": [[1, 2.0]], "t": "alt"},
                         "9": {"i": [[1, 9.0]], "t": "alt"}}}
        erg = {"1": ({"i": [[5, 1.5]], "t": "neu"}, None)}
        neu = A.neue_live(alt, erg, {"1", "2", "3"}, "stand")
        self.assertEqual(neu["werte"]["1"]["t"], "neu")
        self.assertEqual(neu["werte"]["2"]["t"], "alt")            # Abruf fehlgeschlagen -> alter Stand
        self.assertNotIn("9", neu["werte"])                         # nicht mehr gebraucht
        self.assertNotIn("3", neu["werte"])                         # nie geladen

    def test_historie_nur_bei_aenderung(self):
        alt = {"werte": {"1": {"d": [[1, 1.0]], "t": "alt"}}}
        self.assertIsNone(A.neue_historie(alt, {"1": (None, [[1, 1.0]])}, {"1"}, "s"))
        neu = A.neue_historie(alt, {"1": (None, [[1, 1.0], [2, 1.1]])}, {"1"}, "s")
        self.assertEqual(neu["werte"]["1"], {"d": [[1, 1.0], [2, 1.1]], "t": "s"})
        self.assertIsNotNone(A.neue_historie(alt, {}, set(), "s"))   # Wert entfallen -> neu schreiben


class Vorrat(unittest.TestCase):
    def setUp(self):
        self.uhr = [0.0]
        self.dateien = {
            KV.PFAD_LIVE: {"stand": T0.isoformat(), "werte": {"7": {"i": [[1, 10.0], [2, 11.0]], "p": 10.5,
                                                                      "t": T0.isoformat()}}},
            KV.PFAD_HISTORIE.format(KV.teil("7")): {"werte": {"7": {"d": [[1, 9.0]], "t": T0.isoformat()}}},
        }
        self.lesungen = []
        self.kaputt = False

        def lesen(p):
            self.lesungen.append(p)
            if self.kaputt:
                raise IOError("weg")
            return self.dateien.get(p)
        self.v = KV.Vorrat(lesen, ttl_live=60, uhr=lambda: self.uhr[0])

    def test_lesen_und_zwischenspeichern(self):
        e, t = self.v.live(7)
        self.assertEqual(e["p"], 10.5)
        self.assertEqual(t, T0)
        self.assertEqual(self.v.historie("7")[0], [[1, 9.0]])
        self.assertIsNone(self.v.live(8))
        self.assertEqual(self.lesungen.count(KV.PFAD_LIVE), 1)       # innerhalb der TTL nur einmal gelesen
        self.assertEqual(self.v.stand(), T0)

    def test_lesefehler_behaelt_letzten_stand(self):
        self.v.live(7)
        self.kaputt, self.uhr[0] = True, 120.0
        self.assertIsNotNone(self.v.live(7))

    def test_live_antwort_fuer_auswertung(self):
        d = KV.live_antwort({"i": [[1, 2.0]], "p": 1.5}, [[0, 1.4]])
        self.assertEqual(d["series"]["intraday"]["data"], [[1, 2.0]])
        self.assertEqual(d["info"]["plotlines"][0]["value"], 1.5)
        self.assertEqual(KV.live_antwort({"i": [[1, 2.0]]})["info"]["plotlines"], [])

    def test_aktuell_und_naechster_lauf(self):
        self.assertTrue(KV.aktuell(T0, T0 + datetime.timedelta(minutes=70), 75))
        self.assertFalse(KV.aktuell(T0, T0 + datetime.timedelta(minutes=80), 75))
        self.assertFalse(KV.aktuell(None, T0, 75))
        stunden = range(5, 22)
        self.assertEqual(KV.naechster_lauf(T0, stunden), T0 + datetime.timedelta(minutes=30))
        abend = datetime.datetime(2026, 10, 30, 23, 10, tzinfo=BERLIN)          # Freitag spaet -> Montag frueh
        n = KV.naechster_lauf(abend, stunden)
        self.assertEqual((n.weekday(), n.astimezone(datetime.timezone.utc).hour), (0, 5))


class DienstMitVorrat(unittest.TestCase):
    def test_vorrat_vor_netz_und_hintergrund_bei_fehlendem_wert(self):
        abrufe, freigabe = [], threading.Event()

        def live(i):
            abrufe.append(i)
            freigabe.wait(2)
            return 42.0
        vorrat = {("live", "1"): (10.0, T0)}
        d = KursDienst({"live": live}, jetzt=lambda: T0, vorrat=lambda a, i: vorrat.get((a, i)), wartezeit=0.05)
        self.assertEqual(d.hole("live", 1), 10.0)                    # aus dem Vorrat, kein Netzabruf
        self.assertEqual(abrufe, [])
        with self.assertRaises(KursFehlt):                           # fehlt: Hintergrund, Seite wartet nicht
            d.hole("live", 2)
        freigabe.set()
        for _ in range(100):
            if d.status()["werte"] == 2:
                break
            time.sleep(0.01)
        self.assertEqual(d.hole("live", 2), 42.0)                    # beim naechsten Aufbau da
        self.assertEqual(abrufe, ["2"])

    def test_neuerer_vorrat_ersetzt_speicher(self):
        vorrat = {}
        d = KursDienst({"live": lambda i: 1.0}, jetzt=lambda: T0, vorrat=lambda a, i: vorrat.get((a, i)))
        self.assertEqual(d.hole("live", 1), 1.0)
        vorrat[("live", "1")] = (2.0, T0 + datetime.timedelta(minutes=30))
        self.assertEqual(d.hole("live", 1), 2.0)
        vorrat[("live", "1")] = (0.5, T0 - datetime.timedelta(minutes=30))   # aelter -> Speicher gilt
        self.assertEqual(d.hole("live", 1), 2.0)


class Suche(unittest.TestCase):
    def test_suchbegriffe_und_builder(self):
        d = {"assets": [{"ticker": "IWDA", "isin": "IE00B4L5Y983", "name": "x"}, {"ticker": " "}],
             "korb": [{"isin": "US0378331005"}]}
        self.assertEqual(A.suchbegriffe_in(d), {"IWDA", "IE00B4L5Y983", "US0378331005"})
        pb = {"positionen": [{"wkn": "A111X9", "isin": "IE00BKM4GZ66"}, {"wkn": "A0RPWH", "instrument_id": "1"}]}
        self.assertEqual(A.builder_begriffe(pb), {"A111X9", "IE00BKM4GZ66"})
        self.assertEqual(A.builder_begriffe(None), set())

    def test_suche_auswerten_und_bester_treffer(self):
        roh = {"results": [{"instrumentId": 5, "displayname": "Apple", "wkn": "865985", "isin": "US0378331005"},
                           {"id": 6, "displayname": "Apple CFD"}, {"displayname": "ohne ID"}]}
        t = KV.suche_auswerten(roh)
        self.assertEqual([x["instrument_id"] for x in t], [5, 6])
        self.assertEqual(KV.suche_auswerten([{"instrumentId": 7}])[0]["name"], "(ohne Namen)")
        self.assertEqual(KV.bester_treffer(t, "us0378331005")["instrument_id"], 5)
        self.assertEqual(KV.bester_treffer(t[::-1], "unbekannt")["instrument_id"], 6)
        self.assertIsNone(KV.bester_treffer([], "x"))

    def test_neue_suche_behaelt_alten_stand(self):
        alt = {"werte": {"a": [{"instrument_id": 1}], "weg": []}}
        neu = A.neue_suche(alt, {"b": [{"instrument_id": 2}]}, {"A", "B"}, "s")
        self.assertEqual(neu["werte"], {"a": [{"instrument_id": 1}], "b": [{"instrument_id": 2}]})

    def test_vorrat_suche(self):
        v = KV.Vorrat(lambda p: {"werte": {"iwda": [{"instrument_id": 1}]}} if p == KV.PFAD_SUCHE else None)
        self.assertEqual(v.suche(" IWDA "), [{"instrument_id": 1}])
        self.assertIsNone(v.suche("andere"))


if __name__ == "__main__":
    unittest.main()
