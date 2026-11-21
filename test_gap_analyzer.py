"""Tests fuer den Gap Analyzer (gap_analyzer.py) - nachrechenbare Beispiele."""
import datetime
import unittest

import gap_analyzer as G


def K(*tage):
    """Kerzen aus (o, h, l, c) je Handelstag ab 2026-01-05 (Werktage)."""
    d, aus = datetime.date(2026, 1, 5), []
    for o, h, l_, c in tage:
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        aus.append([d.isoformat(), o, h, l_, c])
        d += datetime.timedelta(days=1)
    return aus


class Erkennung(unittest.TestCase):
    def test_gap_up_und_down_high_low(self):
        k = K((100, 102, 99, 101), (104, 106, 103, 105), (105, 106, 104, 105), (101, 102, 99, 100))
        g = G.erkennen(k, "NDX")
        self.assertEqual([(x["typ"], x["unten"], x["oben"]) for x in g], [("up", 102, 103), ("down", 102, 104)])
        self.assertEqual(g[0]["id"], "NDX|1d|hl|2026-01-06")
        self.assertAlmostEqual(g[0]["groesse_pct"], 1 / 102 * 100)
        self.assertEqual((g[0]["vortag_wert"], g[0]["tag_wert"]), (102, 103))

    def test_keine_luecke_bei_ueberlappung(self):
        self.assertEqual(G.erkennen(K((100, 102, 99, 101), (101, 103, 101.5, 102)), "DAX"), [])
        self.assertEqual(G.erkennen(K((100, 102, 99, 101), (101, 103, 102, 102)), "DAX"), [])   # Tief = Hoch

    def test_close_open_und_prozent(self):
        k = K((100, 101, 99, 100), (100.3, 101, 100.1, 100.8), (102, 103, 101.5, 102.5))
        co = G.erkennen(k, "SPX", "co")
        self.assertEqual([(x["typ"], x["unten"], x["oben"]) for x in co], [("up", 100, 100.3), ("up", 100.8, 102)])
        self.assertEqual(len(G.erkennen(k, "SPX", "pct")), 1)                   # 0,3 % < 0,5 % Mindestgroesse
        self.assertEqual(len(G.erkennen(k, "SPX", "hl")), 1)                    # nur 101 -> 101.5


class Fuellstatus(unittest.TestCase):
    def test_gap_up_teilweise_dann_geschlossen(self):
        k = K((100, 102, 99, 101), (106, 108, 105, 107), (107, 108, 104, 105),    # Gap 102-105, Tief 104 -> teilw.
              (105, 106, 103, 104), (104, 105, 101.5, 102), (110, 111, 109, 110))
        g = G.erkennen(k, "NDX")[0]
        self.assertEqual((g["status"], g["beruehrt"], g["geschlossen"]), ("geschlossen", k[2][0], k[4][0]))
        self.assertEqual((g["offen_breite"], g["fuellgrad"], g["dauer"]), (0.0, 100.0, 3))
        # Nach der Schliessung erneut darueber: bleibt geschlossen (kein Wieder-Oeffnen)
        self.assertEqual(G.erkennen(k + K((120, 121, 119, 120))[:0], "NDX")[0]["status"], "geschlossen")

    def test_gap_up_teilweise_offen(self):
        k = K((100, 102, 99, 101), (106, 108, 105, 107), (107, 108, 104, 105), (105, 109, 104.5, 108))
        g = G.erkennen(k, "NDX")[0]
        self.assertEqual((g["status"], g["unten"], g["oben"], g["offen_unten"], g["offen_oben"]),
                         ("teilweise", 102, 105, 102, 104))                       # Original bleibt, offen 102-104
        self.assertAlmostEqual(g["fuellgrad"], 100 / 3)
        self.assertEqual(g["alter"], 2)

    def test_gap_down_unberuehrt_und_geschlossen(self):
        k = K((100, 102, 99, 101), (96, 97, 95, 96), (95, 96, 94, 95))           # Gap Down 97-99
        g = G.erkennen(k, "DAX")[0]
        self.assertEqual((g["typ"], g["unten"], g["oben"], g["status"]), ("down", 97, 99, "offen"))
        k2 = k + K((96, 98, 95, 97), (97, 99.5, 96, 99))[:0]
        k2 = k + [["2026-01-08", 96, 98, 95, 97], ["2026-01-09", 97, 99.5, 96, 99]]
        g2 = G.erkennen(k2, "DAX")[0]
        self.assertEqual((g2["status"], g2["beruehrt"], g2["geschlossen"]), ("geschlossen", "2026-01-08", "2026-01-09"))

    def test_eroeffnungsluecke_am_selben_tag_geschlossen(self):
        k = K((100, 101, 99, 100), (101, 102, 99.5, 101.5))                     # Eroeffnung 101, Tief 99,5
        g = G.erkennen(k, "SPX", "co")[0]
        self.assertEqual((g["status"], g["geschlossen"], g["dauer"]), ("geschlossen", k[1][0], 0))


class LageUndNaechste(unittest.TestCase):
    def test_lage_unabhaengig_von_richtung(self):
        up = {"status": "offen", "offen_unten": 102, "offen_oben": 105}
        self.assertEqual(G.lage(up, 100)[:2], ("oberhalb", 2))                  # Gap Up liegt heute UEBER dem Kurs
        self.assertEqual(G.lage(up, 110)[:2], ("unterhalb", 5))
        self.assertEqual(G.lage(up, 103), ("innerhalb", 0.0, 0.0))
        self.assertEqual(G.lage(dict(up, status="geschlossen"), 103), (None, None, None))

    def test_naechste_und_uebersicht(self):
        k = K((100, 102, 99, 101), (106, 108, 105, 107), (107, 108, 106, 107),    # Up 102-105
              (100, 101, 98, 99), (99, 100, 97, 98),                              # Down 101-106
              (92, 93, 91, 92))                                                   # Down 93-97
        gaps = G.mit_lage(G.erkennen(k, "NDX"), 92)
        ob, un = G.naechste(gaps)
        self.assertEqual([g["unten"] for g in ob], [93, 101])                  # Gap Up 102-105: Tief 98 schliesst es
        self.assertEqual(un, [])
        u = G.uebersicht(gaps, 92)
        self.assertEqual((u["offen_up"], u["offen_down"], u["naechstes_oben"]["unten"]), (0, 2, 93))
        self.assertAlmostEqual(u["summe_offen"], 5 + 4)


class Datenqualitaet(unittest.TestCase):
    def test_pruefen_und_unvollstaendig(self):
        roh = [["2026-01-06", 1, 2, 0.5, 1.5], ["2026-01-05", 1, 2, 0.5, 1.5], ["2026-01-06", 1, 2, 0.5, 1.5],
               ["2026-01-07", 1, 0.9, 0.5, 1.5], ["x", 1, 1, 1, 1]]
        k, p = G.kerzen_pruefen(roh)
        self.assertEqual([x[0] for x in k], ["2026-01-05", "2026-01-06"])
        self.assertEqual(len(p), 3)
        k = K((100, 102, 99, 101), (104, 106, 103, 105), (105, 106, 104, 105))
        g = G.erkennen(k, "NDX", fehlende=["2026-01-07"])[0]                     # Tag nach Entstehung fehlt
        self.assertFalse(g["vollstaendig"])
        g2 = G.erkennen(k, "NDX", fehlende=["2025-12-01"])[0]
        self.assertTrue(g2["vollstaendig"])


class Statistik(unittest.TestCase):
    def test_zensierte_quoten(self):
        def g(typ, dauer, alter):
            return {"typ": typ, "dauer": dauer, "alter": alter, "groesse_pct": 1.0, "groesse": 10,
                    "status": "geschlossen" if dauer is not None else "offen"}
        gaps = [g("up", 1, 50), g("up", 8, 40), g("down", None, 3), g("down", None, 100)]
        s = G.statistik(gaps)["alle"]
        self.assertEqual((s["anzahl"], s["geschlossen"], s["zensiert"]), (4, 2, 2))
        q1, n1 = s["quoten"][1]
        self.assertEqual(n1, 4)                    # alle mind. 1 Tag beobachtet
        self.assertEqual(q1, 25.0)
        q5, n5 = s["quoten"][5]
        self.assertEqual((n5, round(q5, 6)), (3, round(100 / 3, 6)))   # das 3 Tage alte offene Gap zaehlt fuer 5 Tage NICHT mit
        self.assertEqual(s["dauer_median"], 4.5)
        self.assertEqual(G.statistik([])["alle"], {"anzahl": 0})


class Alerts(unittest.TestCase):
    def test_alerts_einmalig(self):
        k = K((100, 102, 99, 101), (104, 106, 103, 105), (105, 106, 102.5, 105))   # Up 102-103, teilweise
        gaps = G.erkennen(k, "NDX")
        heute = datetime.date(2026, 1, 8)
        a = G.alerts({"NDX": gaps}, {"NDX": 102.2}, {"gross_pct": 0.5}, heute=heute)   # Gap 0,98 %
        arten = {x["schluessel"].split("|")[-1] for x in a}
        self.assertTrue({"neu", "gross", "teilweise", "erreicht"} <= arten)
        self.assertTrue(all(x["neu"] for x in a))
        self.assertFalse(any(x["neu"] for x in G.alerts({"NDX": gaps}, {"NDX": 102.2}, {},
                                                         [x["schluessel"] for x in a], heute=heute)))
        aus = {k: False for k in G.STANDARD_ALERTS if k.endswith("_an")}
        self.assertEqual(G.alerts({"NDX": gaps}, {"NDX": 102.2}, aus, heute=heute), [])
        naehe = G.alerts({"NDX": gaps}, {"NDX": 103.0}, {"naehe_pct": 1.0}, heute=datetime.date(2026, 3, 1))
        self.assertEqual([x["schluessel"].split("|")[-1] for x in naehe], ["naehe"])   # 0,49 % ueber 102,5


if __name__ == "__main__":
    unittest.main()
