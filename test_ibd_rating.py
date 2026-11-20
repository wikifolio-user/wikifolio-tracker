"""Tests fuer das IBD-aehnliche Rating (ibd_rating.py)."""
import random
import time
import unittest

import ibd_rating as I


def _kurse(start, faktor, n=300, volumen=1000):
    """Gleichmaessig steigende/fallende Kursreihe [(datum, schluss, volumen)]."""
    return [(f"t{i}", start * faktor ** i, volumen) for i in range(n)]


class Bausteine(unittest.TestCase):
    def test_quartale_und_jahre(self):
        q = [{"eps": x} for x in (1.0, 1.0, 1.0, 1.0, 1.0, 1.5, 2.0)]
        self.assertEqual(I.quartals_wachstum(q), (100.0, 50.0))         # -1 vs -5, -2 vs -6
        self.assertEqual(I.quartals_wachstum(q[:5])[1], None)              # zu kurz fuer das zweite Quartal
        self.assertEqual(I.quartals_wachstum([{"eps": -1}] * 4 + [{"eps": 1}]), (None, None))   # Verlust -> None
        self.assertAlmostEqual(I.jahres_wachstum([{"eps": 1}, {"eps": 1.1}, {"eps": 1.21}, {"eps": 1.331}]), 10.0)
        self.assertIsNone(I.jahres_wachstum([{"eps": -1}, {"eps": 1}, {"eps": 1}, {"eps": 2}]))

    def test_kursstaerke_gewichtet_letztes_quartal(self):
        flach = [100.0] * 190 + [100.0 * 1.002 ** i for i in range(63)]   # nur im letzten Quartal +
        frueh = [100.0 * 1.002 ** i for i in range(63)] + [100.0 * 1.002 ** 62] * 190
        self.assertGreater(I.kursstaerke(flach), I.kursstaerke(frueh))     # gleiche Performance, spaeter = staerker
        self.assertIsNone(I.kursstaerke([100.0] * 200))

    def test_akkumulation_und_hoch(self):
        k = [("t", 100 + (i % 2), 300 if i % 2 else 100) for i in range(70)]   # Aufwaertstage mit mehr Volumen
        self.assertAlmostEqual(I.akkumulation(k), 3.0, delta=0.1)       # ~gleich viele Auf-/Abwaertstage
        self.assertEqual(I.akkumulation(_kurse(10, 1.01, 70)), 10.0)        # nur Aufwaertstage -> gedeckelt
        self.assertAlmostEqual(I.abstand_hoch([100, 120, 90]), 25.0)

    def test_rohwerte(self):
        f = {"quartale": [{"eps": 1.0}] * 4 + [{"eps": 1.3}],
             "jahre": [{"eps": 1.0, "umsatz": 100}, {"eps": 1.2, "umsatz": 110}, {"eps": 1.3, "umsatz": 120},
                       {"eps": 1.5, "umsatz": 150, "nettogewinn": 15, "ek": 60}],
             "kurse": _kurse(10, 1.002)}
        r = I.rohwerte(f)
        self.assertEqual((r["q1"], r["uw"], r["nm"], r["roe"], r["hoch"]), (30.0, 25.0, 10.0, 25.0, 0.0))
        self.assertNotIn("q2", r)                                           # unbekannt -> fehlt (nie 0)
        self.assertEqual(I.rohwerte({}), {})


class Rangliste(unittest.TestCase):
    def setUp(self):
        random.seed(1)
        self.werte = {f"S{i}": {"sek": f"Sektor{i % 6}", "ibd": {
            "q1": random.uniform(-50, 100), "a": random.uniform(-10, 40), "rs": random.uniform(-40, 80),
            "uw": random.uniform(-10, 30), "nm": random.uniform(-20, 30), "roe": random.uniform(-10, 40),
            "ad": random.uniform(0.5, 2), "hoch": random.uniform(0, 60)}} for i in range(400)}

    def test_raenge_1_bis_99_und_reihenfolge(self):
        self.werte["BEST"] = {"sek": "Sektor0", "ibd": {"q1": 500, "q2": 500, "a": 90, "rs": 300, "uw": 90,
                                                        "nm": 60, "roe": 90, "ad": 5, "hoch": 0}}
        self.werte["SCHWACH"] = {"sek": "Sektor0", "ibd": {"q1": -90, "a": -9, "rs": -60, "ad": 0.2, "hoch": 80}}
        r, _ = I.alle_ratings(self.werte)
        self.assertTrue(all(1 <= x["eps"] <= 99 and 1 <= x["composite"] <= 99 for x in r.values()))
        self.assertEqual((r["BEST"]["eps"], r["BEST"]["composite"]), (99, 99))
        self.assertLessEqual(r["SCHWACH"]["composite"], 5)
        self.assertGreater(len(set(x["composite"] for x in r.values())), 50)   # breit verteilt

    def test_ohne_gewinnwachstum_kein_rating_und_fehlende_nicht_null(self):
        self.werte["OHNE"] = {"sek": "Sektor1", "ibd": {"rs": 80, "hoch": 1}}
        self.werte["NUR_EPS"] = {"sek": "Sektor1", "ibd": {"q1": 60, "a": 20}}
        r, basis = I.alle_ratings(self.werte)
        self.assertNotIn("OHNE", r)
        t = r["NUR_EPS"]["teile"]
        self.assertIsNone(t["rs"])                                          # fehlt, zaehlt nicht als 0
        self.assertEqual(I.rating(self.werte["NUR_EPS"]["ibd"], "Sektor1", basis)["eps"], r["NUR_EPS"]["eps"])

    def test_zu_wenige_vergleichswerte(self):
        r, _ = I.alle_ratings({k: self.werte[k] for k in list(self.werte)[:10]})
        self.assertEqual(r, {})

    def test_schnell_genug_fuer_alle_aktien(self):
        gross = {f"X{i}": {"sek": f"S{i % 11}", "ibd": dict(self.werte[f"S{i % 400}"]["ibd"])} for i in range(16000)}
        t0 = time.time()
        r, _ = I.alle_ratings(gross)
        self.assertEqual(len(r), 16000)
        self.assertLess(time.time() - t0, 5)


if __name__ == "__main__":
    unittest.main()
