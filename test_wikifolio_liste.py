"""Wikifolio-Liste: Risiko-Kennzahlen aus Kursreihen, Laden, Filter, Mein Score, Rangliste."""
import datetime
import math
import unittest

import risiko_kennzahlen as RK
import wikifolio_liste as WL

T0 = datetime.date(2020, 1, 1)


def reihe(kurse):
    return [(T0 + datetime.timedelta(days=i), k) for i, k in enumerate(kurse)]


class Risiko(unittest.TestCase):
    def test_gerade_linie(self):
        # 4 Jahre stetig +10 % p. a., keine Rueckgaenge
        n = 4 * 365
        k = RK.kennzahlen(reihe([100 * 1.1 ** (i / 365.25) for i in range(n)]))
        self.assertAlmostEqual(k["rendite_pa"], 10.0, delta=0.1)
        self.assertEqual(k["maxdd"], 0.0)
        self.assertEqual(k["dd_akt"], 0.0)
        self.assertEqual(k["tage_unter_hoch"], 0)
        self.assertEqual(k["gewinnmonate"], 100.0)
        self.assertGreater(k["sma200"], 0)
        self.assertLess(k["vola1j"], 0.1)

    def test_rueckgang_und_monate(self):
        kurse = [100.0] * 100 + [50.0] * 100 + [80.0] * 200        # -50 %, dann Erholung auf 80
        k = RK.kennzahlen(reihe(kurse))
        self.assertEqual(k["maxdd"], -50.0)
        self.assertEqual(k["dd_akt"], -20.0)
        self.assertEqual(k["tage_unter_hoch"], 300)                 # Hoch zuletzt am Tag 99
        self.assertEqual(k["schlechtester_monat"], -50.0)
        self.assertIsNone(k["vola3j"])                              # keine 3 Jahre Historie
        self.assertIsNone(k["calmar3j"])

    def test_zu_kurz_und_kaputt(self):
        self.assertEqual(RK.kennzahlen(reihe([100.0] * 10)), {})
        k = RK.kennzahlen(reihe([100.0, 0, None] + [100.0] * 40))
        self.assertTrue(all(v is None or math.isfinite(v) for v in k.values()))


FELDER = ["wkn", "name", "isin", "1M", "3M", "6M", "1J", "2J", "3J", "5J"] + list(RK.FELDER)


def zeile(wkn, j1, sharpe, maxdd, vola, gewinn, sma):
    r = dict.fromkeys(FELDER)
    r.update(wkn=wkn, name=wkn.lower(), isin="", **{"1J": j1}, sharpe1j=sharpe, maxdd=maxdd, vola1j=vola,
             gewinnmonate=gewinn, sma200=sma, rendite_pa=j1)
    return [r[f] for f in FELDER]


TEILE = [{"felder": FELDER, "zeilen": [zeile("LS9A", 20.0, 1.5, -10.0, 8.0, 70, 5.0),
                                       zeile("LS9B", 60.0, 0.8, -45.0, 30.0, 55, -3.0),
                                       zeile("LS9C", -5.0, -0.2, -20.0, 12.0, 40, 2.0)]}]


class Liste(unittest.TestCase):
    def setUp(self):
        self.w = WL.laden(TEILE, {"LS9A": {"score": 80, "einordnung": "prio", "rdd": 2.0, "jahre": 5.0}})

    def test_laden(self):
        self.assertEqual(set(self.w), {"LS9A", "LS9B", "LS9C"})
        self.assertEqual(self.w["LS9A"]["perf"], {"1J": 20.0})
        self.assertEqual(self.w["LS9A"]["kz"]["score"], 80)
        self.assertEqual(self.w["LS9A"]["kz"]["_einordnung"], "prio")

    def test_filter(self):
        self.assertEqual(set(WL.filtern(self.w, {"maxdd": 25})), {"LS9A", "LS9C"})       # hoechstens 25 % Verlust
        self.assertEqual(set(WL.filtern(self.w, {"vola1j": 10})), {"LS9A"})
        self.assertEqual(set(WL.filtern(self.w, {"sharpe1j": 1.0})), {"LS9A"})
        self.assertEqual(set(WL.filtern(self.w, {}, nur_aufwaerts=True)), {"LS9A", "LS9C"})
        self.assertEqual(set(WL.filtern(self.w, {"jahre": 1})), {"LS9A"})                # ohne Wert -> raus

    def test_mein_score(self):
        WL.mein_score(self.w, {"sharpe1j": 1, "maxdd": 1})
        s = {k: v["kz"]["mein_score"] for k, v in self.w.items()}
        self.assertEqual(s["LS9A"], 100.0)                                               # bester in beidem
        self.assertLess(s["LS9B"], s["LS9A"])
        WL.mein_score(self.w, {})
        self.assertIsNone(self.w["LS9A"]["kz"]["mein_score"])

    def test_rangliste_richtung(self):
        self.assertEqual([w["wkn"] for w in WL.rangliste(self.w, "1J")], ["LS9B", "LS9A", "LS9C"])
        self.assertEqual([w["wkn"] for w in WL.rangliste(self.w, "vola1j")], ["LS9A", "LS9C", "LS9B"])  # klein zuerst
        self.assertEqual([w["wkn"] for w in WL.rangliste(self.w, "maxdd")], ["LS9A", "LS9C", "LS9B"])
        self.assertEqual([(w["wkn"], w["rang"]) for w in WL.rangliste(self.w, "1J", "ls9c")], [("LS9C", 3)])


if __name__ == "__main__":
    unittest.main()
