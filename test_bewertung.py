"""Tests fuer bewertung.py (python3 -m unittest test_bewertung)."""
import random
import unittest

import bewertung as BW


def _etf(i, r5, vola, name="iShares MSCI World", **kw):
    z = {"typ": "etf", "name": name, "kennung": f"E{i}", "r1": r5, "r3": r5, "r5": r5, "r10": r5,
         "vola": vola, "maxdd": -vola * 2, "jahre": 12, "div": None}
    z.update(kw)
    return z


def _basis():
    rnd = random.Random(1)
    zeilen = [_etf(i, rnd.uniform(0, 15), rnd.uniform(10, 30)) for i in range(40)]
    zeilen += [{"typ": "wikifolio", "name": f"W{i}", "kennung": f"W{i}", "r1": rnd.uniform(-10, 30),
                "r3": rnd.uniform(0, 20), "r5": rnd.uniform(0, 20), "r10": None, "vola": rnd.uniform(8, 30),
                "maxdd": rnd.uniform(-50, -5), "jahre": rnd.uniform(1, 12)} for i in range(30)]
    zeilen += [{"typ": "aktie", "name": f"A{i}", "kennung": f"A{i}", "r1": rnd.uniform(-20, 40),
                "r3": rnd.uniform(-5, 25), "r5": rnd.uniform(-5, 25), "r10": rnd.uniform(0, 20),
                "vola": rnd.uniform(15, 45), "maxdd": rnd.uniform(-70, -15), "jahre": 15, "div": rnd.uniform(0, 4),
                "qd": {"pt": [rnd.randint(0, 20), rnd.randint(0, 15), rnd.randint(0, 15), rnd.randint(0, 10),
                              rnd.randint(0, 10), rnd.randint(0, 10), rnd.randint(0, 15), rnd.randint(0, 5)],
                       "roic": rnd.uniform(0, 30), "g_ums": rnd.uniform(-5, 20), "g_eps": rnd.uniform(-5, 25),
                       "nde": rnd.uniform(-1, 4), "fkgv": rnd.uniform(8, 40), "fcfy": rnd.uniform(0, 8),
                       "rev90": rnd.uniform(-5, 5), "p6": rnd.uniform(-20, 30)}} for i in range(40)]
    return zeilen


class BewertungTests(unittest.TestCase):
    def setUp(self):
        self.zeilen = _basis()
        self.m = BW.Modell(self.zeilen)

    def test_gewichte_summe_100(self):
        for strat, klassen in BW.GEWICHTE.items():
            for typ, g in klassen.items():
                self.assertEqual(sum(g.values()), 100, (strat, typ))
                for gruppe in g:
                    self.assertTrue(any(d[0] == gruppe for d in BW.kriterien_der_klasse(typ).values()),
                                    (strat, typ, gruppe))

    def test_beitraege_addieren_sich_zum_score(self):
        for z in self.zeilen:
            b = self.m.bewerte(z)
            self.assertAlmostEqual(50 + sum(g["beitrag"] for g in b["gruppen"]), b["score_genau"], places=6)
            self.assertTrue(0 <= b["score"] <= 100)

    def test_besser_in_allem_ist_vorne(self):
        gut = _etf(99, 14.9, 10.5)
        schlecht = _etf(98, 0.5, 29.5)
        m = BW.Modell(self.zeilen + [gut, schlecht])
        self.assertGreater(m.bewerte(gut)["score"], 75)
        self.assertLess(m.bewerte(schlecht)["score"], 30)
        abstand, diffs = BW.vergleich(m.bewerte(gut), m.bewerte(schlecht))
        self.assertGreater(abstand, 40)
        self.assertTrue(all(d >= -0.01 for _, d in diffs if _ != "Streuung"))

    def test_fehlende_daten_ziehen_zur_mitte(self):
        voll = _etf(97, 14.9, 10.5)
        luecke = dict(voll, r10=None, r5=None, r3=None, r1=None)
        bv, bl = self.m.bewerte(voll), self.m.bewerte(luecke)
        self.assertLess(bl["abdeckung"], bv["abdeckung"])
        self.assertLess(abs(bl["score_genau"] - 50), abs(bv["score_genau"] - 50))
        self.assertIn("Rendite 5 J. p.a.", bl["fehlend"])

    def test_score_unabhaengig_von_filter(self):
        z = self.zeilen[3]
        self.assertEqual(self.m.bewerte(z)["score"], BW.Modell(self.zeilen).bewerte(z)["score"])

    def test_strategie_aendert_gewichtung(self):
        z = next(x for x in self.zeilen if x["typ"] == "aktie")
        a = BW.Modell(self.zeilen, "Ausgewogen").bewerte(z)
        d = BW.Modell(self.zeilen, "Dividende").bewerte(z)
        self.assertIn("dividende", [g["key"] for g in d["gruppen"]])
        self.assertNotIn("dividende", [g["key"] for g in a["gruppen"]])
        self.assertEqual(BW.Modell(self.zeilen, "Unbekannt").strategie, "Ausgewogen")

    def test_aktie_ohne_teilpunkte_nutzt_anteile(self):
        z = {"typ": "aktie", "name": "X", "kennung": "X", "r5": 10, "qd": {"q_ant": 80, "b_ant": 40}}
        b = self.m.bewerte(z)
        q = next(g for g in b["gruppen"] if g["key"] == "qualitaet")
        self.assertIsNotNone(q["score"])

    def test_erklaerungen(self):
        m = BW.Modell(self.zeilen + [_etf(99, 14.9, 10.5), _etf(98, 14.0, 11.0)])
        a, b = m.bewerte(_etf(99, 14.9, 10.5)), m.bewerte(_etf(98, 14.0, 11.0))
        self.assertTrue(a["plus"])
        t = BW.warum(1, a, b, "Zweiter")
        self.assertIn("Stark bei", t)
        self.assertIn("Platz 2", t)
        t2 = BW.warum(1, a, sortiert_nach_score=False, sortierung="10J p.a.")
        self.assertIn("10J p.a.", t2)

    def test_hinweise(self):
        z = _etf(5, 30, 60, name="WisdomTree NASDAQ 100 3x Daily Leveraged", jahre=1.5)
        b = self.m.bewerte(z)
        self.assertTrue(any("Kurze Historie" in h for h in b["hinweise"]))
        self.assertTrue(any("Hebel" in h for h in b["hinweise"]))
        self.assertTrue(any("Winner Bias" in h for h in b["hinweise"]))
        self.assertTrue(b["nicht_in_quelle"])

    def test_streuung(self):
        self.assertEqual(BW.streuung_geschaetzt("Vanguard FTSE All-World")[0], 90)
        self.assertLess(BW.streuung_geschaetzt("iShares MSCI World Information Technology")[0], 50)
        self.assertEqual(BW.streuung_geschaetzt("Leverage Shares 3x NVIDIA")[0], 10)

    def test_ampel_und_qualitaet(self):
        self.assertEqual(BW.ampel(70), "gruen")
        self.assertEqual(BW.ampel(50), "gelb")
        self.assertEqual(BW.ampel(20), "rot")
        self.assertEqual(BW.datenqualitaet(0.9), "gut")
        self.assertEqual(BW.datenqualitaet(0.5), "gering")

    def test_unbekannter_typ(self):
        self.assertIsNone(self.m.bewerte({"typ": "anleihe"}))


if __name__ == "__main__":
    unittest.main()
