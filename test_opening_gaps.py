"""Tests Opening-Gaps (opening_gaps.py) und Intraday-Daten (markt_daten.intraday_*)."""
import datetime
import unittest
from zoneinfo import ZoneInfo

import markt_daten as MD
import opening_gaps as OG

BERLIN = ZoneInfo("Europe/Berlin")
NY = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc


def k(d, o, h, l_, c):
    return [d, o, h, l_, c]


class Erkennen(unittest.TestCase):
    def test_gap_up_am_selben_tag_geschlossen_bleibt_sichtbar(self):
        g = OG.erkennen([k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 102, 103, 99.5, 101)], "DAX")[0]
        self.assertEqual((g["typ"], g["status"], g["geschlossen"], g["dauer_tage"]), ("up", "heute", "2026-11-03", 0))
        self.assertAlmostEqual(g["groesse"], 2.0)
        self.assertAlmostEqual(g["groesse_pct"], 2.0)
        self.assertEqual(g["fuellgrad"], 100.0)
        self.assertEqual(g["rest"], 0.0)
        self.assertIsNone(g["geschlossen_zeit"])                   # ohne Intraday keine erfundene Uhrzeit

    def test_gap_down_teilweise_dann_spaeter_geschlossen(self):
        kerzen = [k("2026-11-02", 100, 101, 99, 100), k("2026-11-03", 96, 98, 95, 97),
                  k("2026-11-04", 97, 99, 96, 98), k("2026-11-05", 98, 100.5, 97, 100)]
        g = OG.erkennen(kerzen, "NDX")[0]
        self.assertEqual(g["typ"], "down")
        self.assertEqual(g["status"], "spaeter")
        self.assertEqual((g["geschlossen"], g["dauer_tage"]), ("2026-11-05", 2))
        self.assertEqual(g["beruehrt"], "2026-11-03")
        self.assertAlmostEqual(g["groesse"], 4.0)                  # urspruengliche Groesse bleibt unveraendert

    def test_fuellgrad_und_rest(self):
        g = OG.erkennen([k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 104, 106, 103, 105)], "SPX")[0]
        self.assertEqual(g["status"], "teilweise")
        self.assertAlmostEqual(g["fuellgrad"], 25.0)
        self.assertAlmostEqual(g["rest"], 3.0)
        g = OG.erkennen([k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 104, 106, 104, 105)], "SPX")[0]
        self.assertEqual((g["status"], g["fuellgrad"], g["beruehrt"]), ("offen", 0.0, None))

    def test_geschlossen_wird_nie_wieder_offen(self):
        kerzen = [k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 102, 103, 99, 101),
                  k("2026-11-04", 110, 112, 109, 111)]
        g = OG.erkennen(kerzen, "DJI")[0]
        self.assertEqual(g["status"], "heute")
        self.assertEqual(g["fuellgrad"], 100.0)

    def test_mindestgroesse_und_kein_gap(self):
        kerzen = [k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 100.05, 101, 99, 100),
                  k("2026-11-04", 100, 101, 99, 100)]
        e = OG.erkennen(kerzen, "DAX")
        self.assertEqual([g["typ"] for g in e], ["kein", "kein"])
        self.assertEqual(OG.erkennen(kerzen, "DAX", min_pct=0.01)[0]["typ"], "up")
        self.assertEqual(OG.filtern(e), [])
        self.assertEqual(len(OG.filtern(e, mit_kein=True)), 2)

    def test_eindeutige_ids(self):
        e = OG.erkennen([k(f"2026-11-{d:02d}", 100 + d, 102 + d, 99 + d, 101 + d) for d in range(2, 9)], "NDX")
        self.assertEqual(len({g["id"] for g in e}), len(e))

    def test_vorlaeufiger_tag(self):
        kerzen = [k("2026-11-02", 99, 101, 98, 100)]
        e = OG.erkennen(kerzen, "DAX", vorlaeufig=k("2026-11-03", 98, 99, 97.5, 98.5))
        self.assertTrue(e[-1]["vorlaeufig"])
        self.assertEqual(OG.heute(e)["datum"], "2026-11-03")
        self.assertEqual(OG.statistik(e)["alle"]["anzahl"], 0)      # vorlaeufig zaehlt nicht
        # alter Tag als "vorlaeufig" uebergeben -> ignoriert
        self.assertFalse(any(g["vorlaeufig"] for g in OG.erkennen(kerzen + [k("2026-11-03", 1, 1, 1, 1)], "DAX",
                                                                     vorlaeufig=k("2026-11-03", 98, 99, 97, 98))))

    def test_uhrzeiten_nur_mit_intraday(self):
        kerzen = [k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 102, 103, 99.5, 101)]
        z = {"2026-11-03": {"beruehrt": "09:05", "geschlossen": "10:40", "dauer_min": 100, "intervall": "5m",
                            "datenart": "verzoegert"}}
        g = OG.erkennen(kerzen, "DAX", intraday=z)[0]
        self.assertEqual((g["beruehrt_zeit"], g["geschlossen_zeit"], g["dauer_min"]), ("09:05", "10:40", 100))
        self.assertEqual(g["zeiten"]["intervall"], "5m")

    def test_entfernung_zur_schliessung(self):
        g = OG.mit_kurs(OG.erkennen([k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 104, 106, 103, 105)],
                                    "SPX"), 104)[0]
        self.assertAlmostEqual(g["entfernung"], 4.0)
        z = OG.mit_kurs(OG.erkennen([k("2026-11-02", 99, 101, 98, 100), k("2026-11-03", 102, 103, 99, 101)],
                                    "SPX"), 101)[0]
        self.assertIsNone(z["entfernung"])


class Statistik(unittest.TestCase):
    def test_quoten_nur_ausreichend_beobachtet(self):
        kerzen = [k("2026-10-01", 99, 101, 98, 100)]
        kerzen.append(k("2026-10-02", 102, 103, 99, 101))           # up, heute zu
        kerzen.append(k("2026-10-05", 99, 100, 98.5, 99.5))         # down (Schluss 101 -> 99), offen
        for i in range(6, 30):
            kerzen.append(k(f"2026-10-{i:02d}", 99.6, 99.9, 99.4, 99.6))
        e = OG.erkennen(kerzen, "DAX", min_pct=0.5)
        s = OG.statistik(e)["alle"]
        self.assertEqual((s["anzahl"], s["up"], s["down"]), (2, 1, 1))
        self.assertEqual(s["quoten"][0][0], 50.0)
        self.assertEqual(s["noch_offen"], 1)
        self.assertEqual(s["groesstes_up"]["datum"], "2026-10-02")
        self.assertEqual(s["groesstes_down"]["datum"], "2026-10-05")
        q20, basis = s["quoten"][20]
        self.assertEqual((q20, basis), (50.0, 2))                   # beide lange genug beobachtet

    def test_leer(self):
        self.assertEqual(OG.statistik([])["alle"], {"anzahl": 0})
        self.assertEqual(OG.jahre(OG.erkennen([k("2025-12-31", 1, 1, 1, 1), k("2026-01-02", 2, 2, 2, 2)], "X")),
                         ["2026"])


def _ts(tz, d, hh, mm):
    return int(datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).timestamp())


def yahoo(tz, tag, minuten, typ="INDEX", verz=15, gran="5m"):
    """Yahoo-Chart-Antwort mit Kerzen ab tag 09:00 (Berlin) alle 5 Minuten: minuten -> [(o, h, l, c)]."""
    ts, q = [], {"open": [], "high": [], "low": [], "close": []}
    for m, (o, h, l_, c) in minuten:
        ts.append(_ts(tz, tag, m // 60, m % 60))
        for key, v in zip(("open", "high", "low", "close"), (o, h, l_, c)):
            q[key].append(v)
    return {"chart": {"result": [{"meta": {"instrumentType": typ, "exchangeDataDelayedBy": verz,
                                           "dataGranularity": gran},
                                  "timestamp": ts, "indicators": {"quote": [q]}}]}}


class Intraday(unittest.TestCase):
    TAG = datetime.date(2026, 11, 3)

    def test_parsen_nur_index_und_handelszeit(self):
        a = yahoo(BERLIN, self.TAG, [(8 * 60 + 55, (1, 1, 1, 1)), (9 * 60, (102, 103, 101, 102)),
                                     (17 * 60 + 30, (5, 5, 5, 5))])
        e = OG.intraday_parsen(a, BERLIN, (9, 0), (17, 30))
        self.assertEqual(list(e["tage"]), ["2026-11-03"])
        self.assertEqual(len(e["tage"]["2026-11-03"]), 1)            # vor- und nachboerslich verworfen
        self.assertEqual(e["verzoegert_min"], 15)
        self.assertIsNone(OG.intraday_parsen(yahoo(BERLIN, self.TAG, [(540, (1, 1, 1, 1))], typ="FUTURE"),
                                             BERLIN, (9, 0), (17, 30)))

    def test_auswerten_zeiten(self):
        bars = [[_ts(BERLIN, self.TAG, 9, 0), 102, 102.5, 101.5, 102], [_ts(BERLIN, self.TAG, 9, 5), 102, 102, 100.5, 101],
                [_ts(BERLIN, self.TAG, 9, 10), 101, 101, 99.8, 100.2]]
        r = OG.intraday_auswerten(bars, 100, BERLIN, "5m", 15, False)
        self.assertEqual((r["beruehrt"], r["geschlossen"], r["dauer_min"]), ("09:00", "09:10", 10))
        self.assertEqual(r["kerze"], ["2026-11-03", 102, 102.5, 99.8, 100.2])
        self.assertEqual(r["datenart"], "verzoegert")
        self.assertEqual(OG.intraday_auswerten(bars[:2], 100, BERLIN, "5m", 0)["geschlossen"], None)
        self.assertEqual(OG.intraday_auswerten(bars[:2], 100, BERLIN, "5m", 0)["datenart"], "echtzeit")
        self.assertEqual(OG.datenart(None), "verzoegert")           # unbekannt nie als Echtzeit

    def test_zusammenfuehren_schliessung_bleibt(self):
        alt = {"2026-11-03": {"geschlossen": "10:00", "dauer_min": 60, "vollstaendig": False, "kerze": None}}
        neu = OG.intraday_zusammenfuehren(alt, {"2026-11-03": {"geschlossen": None, "vollstaendig": False,
                                                               "beruehrt": "09:05", "kerze": None}})
        self.assertEqual(neu["2026-11-03"]["geschlossen"], "10:00")
        fertig = {"2026-11-02": {"geschlossen": None, "vollstaendig": True, "kerze": None}}
        neu = OG.intraday_zusammenfuehren(fertig, {"2026-11-02": {"geschlossen": "11:00", "vollstaendig": False}})
        self.assertIsNone(neu["2026-11-02"]["geschlossen"])

    def test_intraday_tage_nutzt_offiziellen_vortagesschluss(self):
        e = {"tage": {"2026-11-03": [[_ts(BERLIN, self.TAG, 9, 0), 102, 102, 99, 100]]}, "intervall": "5m",
             "verzoegert_min": 15}
        kerzen = [k("2026-11-02", 98, 101, 97, 100.5)]
        t = MD.intraday_tage(e, kerzen, "XETRA", datetime.datetime(2026, 11, 3, 20, tzinfo=UTC))
        self.assertEqual(t["2026-11-03"]["geschlossen"], "09:00")
        self.assertTrue(t["2026-11-03"]["vollstaendig"])
        self.assertEqual(MD.intraday_tage(e, [], "XETRA", datetime.datetime(2026, 11, 3, 20, tzinfo=UTC)), {})

    def test_neue_intraday_nur_bei_aenderung(self):
        e = {"tage": {"2026-11-03": [[_ts(BERLIN, self.TAG, 9, 0), 102, 102, 99, 100]]}, "intervall": "5m",
             "verzoegert_min": 15}
        ohlc = {"indizes": {"^GDAXI": {"kerzen": [k("2026-11-02", 98, 101, 97, 100.5)]}}}
        jetzt = datetime.datetime(2026, 11, 3, 20, tzinfo=UTC)
        d1 = MD.neue_intraday(None, {"^GDAXI": e}, ohlc, "s1", jetzt)
        self.assertIn("DAX", d1["indizes"])
        self.assertIsNone(MD.neue_intraday(d1, {"^GDAXI": e}, ohlc, "s2", jetzt))

    def test_intraday_abrufen_netzfehler(self):
        class R:
            status_code = 500
        self.assertIsNone(MD.intraday_abrufen("^NDX", lambda *a, **kw: R()))


class Alerts(unittest.TestCase):
    def _gaps(self):
        kerzen = [k("2026-11-16", 99, 101, 98, 100), k("2026-11-17", 101.2, 102, 99.5, 100.5),
                  k("2026-11-18", 100.5, 101, 100, 100.8), k("2026-11-19", 100, 100.5, 99.8, 100.4)]
        return OG.erkennen(kerzen, "DAX")

    def test_schwellen_und_einmalig(self):
        a = OG.alerts({"DAX": self._gaps()}, heute_datum=datetime.date(2026, 11, 20))
        texte = " | ".join(x["text"] for x in a)
        self.assertIn("1.20 % (> 1 %)", texte)
        self.assertIn("vollständig geschlossen", texte)
        gesehen = [x["schluessel"] for x in a]
        self.assertEqual(OG.alerts({"DAX": self._gaps()}, gesehen=gesehen, heute_datum=datetime.date(2026, 11, 20)), [])

    def test_offen_am_schluss_und_eigene_schwelle(self):
        a = OG.alerts({"DAX": self._gaps()}, {"neu_gross_pct": 5.0, "neu_klein_pct": 0.5},
                      heute_datum=datetime.date(2026, 11, 20))
        self.assertTrue(any("0.79 % (> 0.5 %)" in x["text"] for x in a))
        self.assertTrue(any(x["art"] == "offen" for x in a))
        self.assertEqual(OG.alerts({"DAX": self._gaps()}, heute_datum=datetime.date(2026, 12, 30)), [])


if __name__ == "__main__":
    unittest.main()
