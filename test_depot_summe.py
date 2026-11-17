"""Tests fuer depot_summe.py: Depotwert und Rendite aus EINER Quelle (Audit FIN-03)."""
import unittest

import depot_analyse as DA
import depot_summe as DS

LEER = DA.marktdaten_index({})
HAUPT = {"name": "Haupt", "wert": 12000.0, "einstand": 10000.0, "ausgezahlt": 500.0}
ETF = {"name": "ETF", "wert": 5500.0, "einstand": 5000.0}
OHNE_KURS = {"name": "Ohne", "wert": 0.0, "einstand": 3000.0, "ohne_kurs": True}
BESTAND = [HAUPT, ETF, OHNE_KURS]


class Regeln(unittest.TestCase):
    def test_summe(self):
        s = DS.summe(BESTAND)
        self.assertEqual(s["wert"], 17500.0)
        self.assertEqual(s["einstand"], 15000.0)
        self.assertEqual(s["ausgezahlt"], 500.0)
        self.assertAlmostEqual(s["gewinn"], 3000.0)                      # 17.500 + 500 - 15.000
        self.assertAlmostEqual(s["rendite_pct"], 20.0)
        self.assertEqual(s["anzahl"], 2)
        self.assertEqual([p["name"] for p in s["ohne_kurs"]], ["Ohne"])

    def test_totalverlust_zaehlt(self):
        s = DS.summe([ETF, {"name": "Pleite", "wert": 0.0, "einstand": 1000.0}])
        self.assertEqual(s["einstand"], 6000.0)
        self.assertAlmostEqual(s["gewinn"], -500.0)

    def test_ohne_einstand_kein_gewinn(self):
        s = DS.summe([ETF, {"name": "Geschenkt", "wert": 800.0, "einstand": None}])
        self.assertEqual(s["wert"], 6300.0)
        self.assertAlmostEqual(s["gewinn"], 500.0)                       # Wert ohne Einstand ist kein Gewinn

    def test_leer_und_kaputt(self):
        for b in (None, [], [None, "x"], [{"wert": "kaputt"}], [{"wert": float("nan"), "einstand": 5}]):
            s = DS.summe(b)
            self.assertEqual((s["wert"], s["gewinn"], s["rendite_pct"]), (0.0, None, None), b)


class GleicherWertUeberall(unittest.TestCase):
    """Gleiche Daten -> gleicher Wert, Gewinn und Rendite in Depot (depot_summe) und Depot-Analyse."""

    def test_depot_analyse_wie_depot(self):
        for bestand in (BESTAND, [HAUPT], [ETF, {"name": "Pleite", "wert": 0.0, "einstand": 1000.0}],
                        [ETF, {"name": "Geschenkt", "wert": 800.0, "einstand": None}]):
            s = DS.summe(bestand)
            k = DA.kennzahlen([DA.anreichern(dict(p, kurs=p["wert"], stueck=1), LEER) for p in bestand])
            self.assertAlmostEqual(k["investiert"], s["wert"])
            self.assertAlmostEqual(k["einstand"], s["einstand"])
            self.assertAlmostEqual(k["gv"], s["gewinn"])
            self.assertAlmostEqual(k["rendite"], s["rendite_pct"])


if __name__ == "__main__":
    unittest.main()
