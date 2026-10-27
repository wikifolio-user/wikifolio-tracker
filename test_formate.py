"""Zentrale Zahlenformate (formate.py) - UX 10/2026."""
import unittest

import formate as F


class Formate(unittest.TestCase):
    def test_euro(self):
        self.assertEqual(F.eur(1234.5), "1.234,50\u00a0€")
        self.assertEqual(F.eur(-2.675), "\u22122,68\u00a0€")
        self.assertEqual(F.eur(64542.9, 0), "64.543\u00a0€")
        self.assertEqual(F.eur(12.3, vz=True), "+12,30\u00a0€")

    def test_prozent(self):
        self.assertEqual(F.pct(2.345), "2,3\u00a0%")
        self.assertEqual(F.pct(2.345, 2, vz=True), "+2,35\u00a0%")
        self.assertEqual(F.pct(-0.04), "0,0\u00a0%")            # rundet auf 0 -> kein Minus

    def test_leer_und_ungueltig(self):
        for x in (None, "abc", float("nan"), float("inf")):
            self.assertEqual(F.eur(x), "–")
            self.assertEqual(F.pct(x), "–")

    def test_kurs_zwei_nachkommastellen(self):
        self.assertEqual(F.kurs(150), "150,00\u00a0€")

    def test_richtung_nie_nur_farbe(self):
        self.assertEqual(F.richtung(0.004), "flat")
        self.assertEqual(F.richtung(-1), "down")
        self.assertEqual(F.PFEIL[F.richtung(3)], "▲")

    def test_pdf_minus(self):
        self.assertEqual(F.eur(-5, 0, minus="-"), "-5\u00a0€")


if __name__ == "__main__":
    unittest.main()
