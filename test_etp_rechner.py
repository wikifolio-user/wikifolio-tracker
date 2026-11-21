"""Tests fuer den Daily-Leveraged-ETP-Rechner (etp_rechner.py)."""
import math
import statistics
import unittest

import etp_rechner as E


class Verlaeufe(unittest.TestCase):
    def test_alle_enden_am_ziel(self):
        for art in E.VERLAEUFE:
            hist = [0.01 * math.sin(i) for i in range(300)] if art == "historisch" else None
            for ziel in (22000, 18000):
                p = E.kursverlauf(20000, ziel, 40, 25, art, hist)
                self.assertEqual(len(p), 41)
                self.assertEqual((p[0], p[-1]), (20000, ziel), art)
                self.assertTrue(all(x > 0 for x in p))

    def test_reproduzierbar_und_volatilitaet(self):
        a = E.kursverlauf(100, 110, 252, 30, "schwankend_auf")
        self.assertEqual(a, E.kursverlauf(100, 110, 252, 30, "schwankend_auf"))       # feste Saat
        vol = statistics.pstdev([math.log(1 + r) for r in E.renditen(a)]) * math.sqrt(252) * 100
        self.assertTrue(20 < vol < 40, vol)                                            # ~30 %
        g = E.kursverlauf(100, 110, 10, 30, "gleichmaessig_auf")
        self.assertTrue(all(abs(r - E.renditen(g)[0]) < 1e-12 for r in E.renditen(g)))  # konstant
        c = E.kursverlauf(100, 110, 100, 25, "crash")
        self.assertAlmostEqual(min(c), 80.0, places=6)                                 # 20 % Einbruch

    def test_historisch_zu_wenig(self):
        with self.assertRaises(ValueError):
            E.kursverlauf(100, 110, 40, 25, "historisch", [0.01] * 10)
        with self.assertRaises(ValueError):
            E.kursverlauf(100, 110, 40, 25, "unbekannt")


class Produkt(unittest.TestCase):
    def test_taegliche_verkettung(self):
        pfad = [100, 110, 99]                                    # +10 %, -10 %
        self.assertEqual([round(x, 6) for x in E.produkt_verlauf(pfad, 3)], [100, 130, 91])
        self.assertEqual([round(x, 6) for x in E.produkt_verlauf(pfad, -2)], [100, 80, 96])

    def test_gleicher_start_ende_verschiedene_ergebnisse(self):
        e1 = E.ergebnis(10000, E.kursverlauf(100, 100, 40, 40, "gleichmaessig_auf"), 3)
        e2 = E.ergebnis(10000, E.kursverlauf(100, 100, 40, 40, "seitwaerts"), 3)
        self.assertAlmostEqual(e1["endwert"], 10000)
        self.assertLess(e2["endwert"], 10000)                      # Volatility Decay im Seitwaertsmarkt
        self.assertEqual(e1["index_pct"], e2["index_pct"])

    def test_extreme_tagesbewegung_kein_negativer_wert(self):
        w = E.produkt_verlauf([100, 60, 90, 120], 3)               # -40 % x 3 = -120 % -> Totalverlust
        self.assertEqual(w[1:], [0.0, 0.0, 0.0])
        e = E.ergebnis(10000, [100, 60, 90], 3)
        self.assertTrue(e["totalverlust"])
        self.assertEqual((e["endwert"], e["gv"]), (0.0, -10000))
        self.assertEqual(E.produkt_verlauf([100, 140], -3)[-1], 0.0)   # Short: +40 % x -3

    def test_kosten_waehrung_gebuehren(self):
        p = E.kursverlauf(100, 100, 252, 0, "gleichmaessig_auf")
        self.assertAlmostEqual(E.ergebnis(10000, p, 2, kosten_pa=1)["endwert"], 10000 * (1 - 0.01 / 252) ** 252)
        self.assertAlmostEqual(E.ergebnis(10000, p, 2, fx_faktor=0.9, gebuehren=10)["endwert"], 8990)

    def test_drawdown_und_lange_haltedauer(self):
        self.assertEqual(E.max_drawdown([100, 120, 60, 90])[:3], (50.0, 1, 2))
        e = E.ergebnis(10000, E.kursverlauf(100, 150, 2520, 30, "schwankend_auf"), 3)
        self.assertGreaterEqual(e["endwert"], 0)
        self.assertEqual(len(e["produkt"]), 2521)

    def test_ungueltig(self):
        with self.assertRaises(ValueError):
            E.ergebnis(10000, [100, 101], 0)
        self.assertTrue(E.pruefe(einsatz=10, hebel=12, tage=0))


class Szenarien(unittest.TestCase):
    def test_szenarien_und_hebelvergleich(self):
        s = E.szenarien(10000, 20000, 22000, 40, 25, 3)
        self.assertEqual([a for a, _ in s], list(E.SZENARIO_VERGLEICH))
        self.assertTrue(all(abs(e["index_pct"] - 10) < 1e-9 for _, e in s))
        self.assertGreater(len({round(e["endwert"], 2) for _, e in s}), 2)
        self.assertIsNone(dict(E.szenarien(10000, 100, 110, 40, 25, 3, arten=("historisch",)))["historisch"])
        v = E.hebel_vergleich(10000, E.kursverlauf(100, 110, 40, 25, "schwankend_auf"))
        self.assertEqual([x["hebel"] for x in v], [-3, -2, 1, 2, 3, 5])
        self.assertAlmostEqual(v[2]["rendite_pct"], 10.0)                         # 1x = Index


class KnockOut(unittest.TestCase):
    def test_ko_auf_gleichem_pfad(self):
        auf = E.kursverlauf(100, 110, 40, 0, "gleichmaessig_auf")
        k = E.ko_auf_pfad(10000, auf, 3, "long")
        self.assertAlmostEqual(k["rendite_pct"], 30.0)                            # ohne Kosten: 3 x 10 %
        self.assertIsNone(k["ko_tag"])
        crash = E.kursverlauf(100, 110, 100, 50, "crash")                         # zwischendurch -40 %
        k2 = E.ko_auf_pfad(10000, crash, 3, "long")
        self.assertEqual(k2["endwert"], 0)                                         # KO trotz Ziel ueber Start
        self.assertIsNotNone(k2["ko_tag"])
        e = E.ergebnis(10000, crash, 3)
        self.assertGreater(e["endwert"], 0)                                        # ETP ueberlebt (theoretisch)
        s = E.ko_auf_pfad(10000, E.kursverlauf(100, 90, 20, 0, "gleichmaessig_ab"), 4, "short")
        self.assertAlmostEqual(s["rendite_pct"], 40.0)
        self.assertLess(E.ko_auf_pfad(10000, auf, 3, "long", finanzierung_pa=10)["endwert"], k["endwert"])
        with self.assertRaises(ValueError):
            E.ko_auf_pfad(10000, auf, 1, "long")


class Backtest(unittest.TestCase):
    def test_backtest(self):
        k = [[f"2026-01-{i + 1:02d}", 0, 0, 0, 100 * (1.01 if i % 2 else 0.99) ** 1 + i] for i in range(20)]
        b = E.backtest(k, "2026-01-03", "2026-01-15", 2, 10000)
        self.assertEqual((b["von"], b["bis"]), ("2026-01-03", "2026-01-15"))
        self.assertEqual(len(b["produkt"]), 13)
        self.assertGreaterEqual(b["bester_tag"][1], b["schlechtester_tag"][1])
        with self.assertRaises(ValueError):
            E.backtest(k, "2027-01-01", "2027-02-01", 2, 10000)
        self.assertEqual(len(E.historische_renditen(k)), 19)
        z = E.csv_zeilen({"Index": "NDX"}, b, [("seitwaerts", None)])
        self.assertIn(("Eingaben", "Index", "NDX"), z)


if __name__ == "__main__":
    unittest.main()
