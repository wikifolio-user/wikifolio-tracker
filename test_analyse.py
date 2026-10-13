"""Tests fuer analyse.py (python3 -m unittest test_analyse)."""
import unittest

import analyse as AN
import bewertung as BW
from test_bewertung import _basis, _etf


class AnalyseTests(unittest.TestCase):
    def setUp(self):
        self.basis = _basis() + [_etf(90, 9.0, 14.0, name="Vanguard FTSE All-World", jahre=13)]
        self.m = BW.Modell(self.basis)
        self.ctx = AN.kontext(self.basis)

    def _a(self, z, detail=None):
        return AN.analysiere(z, self.m.bewerte(z), self.ctx, detail=detail, stand="13.10.2026", q_stand="12.10.2026")

    def test_benchmark_ist_welt_etf(self):
        self.assertEqual(self.ctx["benchmark"]["name"], "Vanguard FTSE All-World")

    def test_alle_bereiche_vorhanden(self):
        for z in self.basis:
            a = self._a(z)
            for k in ("warum", "vergangenheit", "zukunft", "bewertung", "risiken", "gesamt"):
                self.assertTrue(a["box"][k], (z["name"], k))
            self.assertIn(a["urteil"], AN.URTEILE)
            self.assertLessEqual(len(a["argumente"]), 3)
            self.assertLessEqual(len(a["risiken"]), 3)
            self.assertTrue(a["quellen"])
            self.assertTrue(2 <= len(a["these"]) <= 5)

    def test_vergangenheit_wird_gedaempft(self):
        z = _etf(91, 30.0, 25.0, jahre=4)
        sz = AN.renditeszenarien(z)
        self.assertLess(sz["base"], sz["hist"])
        self.assertGreater(sz["base"], AN.ANKER)
        self.assertLess(sz["bear"], sz["base"])
        self.assertGreater(sz["bull"], sz["base"])
        self.assertIn("Winner Bias", self._a(z)["gegenargument"])

    def test_szenarien_werte(self):
        a = self._a(_etf(92, 10.0, 15.0))
        zeilen = {r["name"]: r for r in a["szenarien"]["zeilen"]}
        base = zeilen["Basis"]
        self.assertAlmostEqual(base["werte"][5], AN.STARTBETRAG * (1 + base["pa"] / 100) ** 5, places=4)
        self.assertGreater(zeilen["Optimistisch"]["werte"][5], base["werte"][5])
        self.assertIn("Stresstest", a["szenarien"]["stress"])

    def test_hebelprodukt_nie_besonders_attraktiv(self):
        z = _etf(93, 14.9, 10.5, name="Leverage Shares 3x Daily NVIDIA")
        self.assertNotEqual(self._a(z)["urteil"], "attraktiv")

    def test_heiss_gelaufen(self):
        z = _etf(94, 8.0, 15.0, r1=60.0)
        self.assertEqual(self._a(z)["bewertung"]["stufe"], "heiß gelaufen")

    def test_aktie_mit_detail_trennt_quellen(self):
        z = next(x for x in self.basis if x["typ"] == "aktie")
        detail = {"g1": 12.5, "rev90": 3.1, "g_ref": 9.0, "g_impl": 6.0, "erw": "konservativ", "bew": "günstig",
                  "mos": 22.0, "kat": ["Laufende Aktienrückkäufe"], "staerken": ["ROIC Ø 25 % über 10 Jahre"],
                  "risiken": ["Währungsrisiko (US-Dollar)"], "h_kgv": 25.0, "fkgv": 18.0, "moat": "stark",
                  "szen": {"bear": {"g": 2, "r": 10, "m": 12, "pot": -20}, "base": {"g": 7, "r": 9, "m": 16, "pot": 28},
                           "bull": {"g": 10, "r": 8, "m": 20, "pot": 60}}}
        a = self._a(z, detail)
        arten = {art for art, _ in a["zukunft"]}
        self.assertIn(AN.PROGNOSE, arten)
        self.assertIn(AN.MODELL, arten)
        self.assertEqual(a["bewertung"]["stufe"], "günstig")
        self.assertEqual(len(a["szenarien"]["dcf"]), 3)
        self.assertTrue(any("Analysten" in t for _, t in a["zukunft"]))
        self.assertTrue(any("Fundamentaldaten" in q for q in a["quellen"]))

    def test_keine_erfundenen_analystendaten(self):
        z = _etf(95, 9.0, 14.0)
        a = self._a(z)
        self.assertFalse(any(art == AN.PROGNOSE for art, _ in a["zukunft"]))
        self.assertTrue(any("nicht Teil der Datenbasis" in t for _, t in a["zukunft"]))

    def test_ohne_historie(self):
        z = {"typ": "wikifolio", "name": "Neu", "kennung": "N", "r1": None, "r3": None, "r5": None, "r10": None}
        a = self._a(z)
        self.assertIsNone(a["renditeszenario"])
        self.assertEqual(a["szenarien"]["zeilen"], [])
        self.assertNotEqual(a["urteil"], "attraktiv")


if __name__ == "__main__":
    unittest.main()
