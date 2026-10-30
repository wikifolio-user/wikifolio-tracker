"""Szenario-Simulator (szenario.py): Fortschreibung, Steuern auf Entnahmen, Zeitraeume - mit Rechenbeispielen."""
import datetime
import unittest

import szenario as S

HEUTE = datetime.date(2026, 1, 15)


class Grundlagen(unittest.TestCase):
    def test_steuersatz(self):
        self.assertAlmostEqual(S.steuersatz(0), 0.26375)                       # 25 % + 5,5 % Soli
        # Kirchensteuer 9 %: KapESt 25/(1+0,0225) = 24,45 %, dazu Soli und KiSt -> 27,99 %
        self.assertAlmostEqual(S.steuersatz(9), 0.25 / 1.0225 * (1 + 0.055 + 0.09))

    def test_raten_und_zeitraeume(self):
        self.assertEqual(S.STANDARD_RATEN[:3], [-10.0, 0.0, 5.0])
        self.assertEqual(S.STANDARD_RATEN[-1], 100.0)
        self.assertEqual(len(S.STANDARD_RATEN), 22)
        self.assertEqual(S.jahres_stuetzpunkte(5), [1, 2, 3, 4, 5])
        self.assertEqual(S.jahres_stuetzpunkte(10), [1, 3, 5, 7, 10])
        self.assertEqual(S.jahres_stuetzpunkte(30), [3, 9, 15, 21, 30])

    def test_ohne_steuer_wie_bisher(self):
        r = S.monatsrate(12.0)
        v = S.simuliere(10000, r, 120, sparrate=100, entnahme=50, heute=HEUTE)["werte"]
        k = 10000.0
        for _ in range(120):
            k = k * (1 + r) + 100 - 50
        self.assertAlmostEqual(v[120], k, places=6)
        self.assertEqual(len(v), 121)

    def test_jahresrendite_exakt(self):
        v = S.simuliere(1000, S.monatsrate(10.0), 12, heute=HEUTE)["werte"]
        self.assertAlmostEqual(v[12], 1100.0, places=6)


class Steuern(unittest.TestCase):
    def test_ohne_gewinn_keine_steuer(self):
        r = S.simuliere(10000, 0.0, 12, entnahme=100, steuer={"freibetrag": 0}, heute=HEUTE)
        self.assertAlmostEqual(r["steuern"], 0.0)
        self.assertAlmostEqual(r["werte"][12], 10000 - 1200)

    def test_gewinnanteil_wird_besteuert_netto_kommt_an(self):
        # 10.000 € Wert, 5.000 € Einstand -> 50 % Gewinnanteil; 0 % Rendite, kein Pauschbetrag.
        # Brutto W mit W - 0,26375 x 0,5 x W = 100 -> W = 100 / 0,868125 = 115,19 €
        r = S.simuliere(10000, 0.0, 1, entnahme=100, steuer={"freibetrag": 0}, einstand=5000, heute=HEUTE)
        w = 100 / (1 - 0.26375 * 0.5)
        self.assertAlmostEqual(r["brutto"], w, places=6)
        self.assertAlmostEqual(r["netto"], 100.0, places=6)
        self.assertAlmostEqual(r["werte"][1], 10000 - w, places=6)

    def test_pauschbetrag_und_teilfreistellung(self):
        # 100 % Gewinn (Einstand 0), Teilfreistellung 30 % -> 70 % steuerpflichtig je Euro
        st = {"freibetrag": 1000, "teilfreistellung": 30}
        r = S.simuliere(100000, 0.0, 12, entnahme=100, steuer=st, einstand=0, heute=HEUTE)
        # 12 x 100 x 0,7 = 840 € steuerpflichtig < 1.000 € Pauschbetrag -> keine Steuer
        self.assertAlmostEqual(r["steuern"], 0.0)
        r = S.simuliere(100000, 0.0, 12, entnahme=200, steuer=st, einstand=0, heute=HEUTE)
        self.assertGreater(r["steuern"], 0.0)
        self.assertAlmostEqual(r["netto"], 2400.0, places=6)

    def test_pauschbetrag_jaehrlich_neu(self):
        st = {"freibetrag": 1000}
        # Start Mitte Dezember: Entnahmen Jan-Dez 2027 -> ein Pauschbetrag
        r1 = S.simuliere(100000, 0.0, 12, entnahme=150, steuer=st, einstand=0, heute=datetime.date(2026, 12, 15))
        # Start Mitte Juni: Entnahmen Jul 2026-Jun 2027 -> zwei Pauschbetraege, weniger Steuer
        r2 = S.simuliere(100000, 0.0, 12, entnahme=150, steuer=st, einstand=0, heute=datetime.date(2026, 6, 15))
        self.assertLess(r2["steuern"], r1["steuern"])
        # ein Jahr: 1.800 € Gewinn, 800 € ueber dem Pauschbetrag -> brutto so, dass 1.800 € netto ankommen
        self.assertAlmostEqual(r1["netto"], 1800.0, places=6)

    def test_kapital_aufgebraucht(self):
        r = S.simuliere(1000, 0.0, 24, entnahme=100, heute=HEUTE)
        self.assertEqual(r["leer_ab"], 10)
        self.assertEqual(r["werte"][-1], 0.0)

    def test_monate_bis(self):
        self.assertEqual(S.monate_bis(1100, 1000, S.monatsrate(10.0), heute=HEUTE), 12)
        self.assertIsNone(S.monate_bis(2000, 1000, 0.0, max_monate=24, heute=HEUTE))


class Zielwert(unittest.TestCase):
    def test_naechstes_ziel(self):
        self.assertEqual(S.naechstes_ziel(0), 100000.0)
        self.assertEqual(S.naechstes_ziel(100000), 250000.0)
        self.assertEqual(S.naechstes_ziel(180000), 250000.0)
        self.assertEqual(S.naechstes_ziel(12000000), 24000000.0)

    def test_ziel_text(self):
        self.assertEqual(S.ziel_text(100000), "100k")
        self.assertEqual(S.ziel_text(250000), "250k")
        self.assertEqual(S.ziel_text(1000000), "1 Mio.")
        self.assertEqual(S.ziel_text(1500000), "1,5 Mio.")

    def test_anderes_ziel_anderer_monat(self):
        a = S.monate_bis(150000, 100000, 0.01)
        b = S.monate_bis(200000, 100000, 0.01)
        self.assertLess(a, b)


if __name__ == "__main__":
    unittest.main()
