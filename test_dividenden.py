"""Dividenden-Kategorien (python3 -m unittest test_dividenden)."""
import unittest

import dividenden as DV


class Kategorien(unittest.TestCase):
    def test_grenzen(self):
        self.assertEqual([DV.kategorie(x) for x in (None, 0, 0.5, 2, 3.99, 4, 6, 9.9, 10, 25)],
                         [None, "keine", "niedrig", "mittel", "mittel", "hoch", "sehr_hoch", "sehr_hoch", "extrem",
                          "extrem"])

    def test_nachhaltigkeit(self):
        self.assertEqual(DV.nachhaltigkeit(3, 45), "nachhaltig")
        self.assertEqual(DV.nachhaltigkeit(3, 75), "solide")
        self.assertEqual(DV.nachhaltigkeit(3, 95), "angespannt")
        self.assertEqual(DV.nachhaltigkeit(3, 140), "ungedeckt")
        self.assertEqual(DV.nachhaltigkeit(3, -20), "ungedeckt")
        self.assertIsNone(DV.nachhaltigkeit(0, 50))
        self.assertIsNone(DV.nachhaltigkeit(3, None))

    def test_filter(self):
        w = {"div": 4.5, "div_q": 70}
        self.assertTrue(DV.passt(w, "Alle"))
        self.assertTrue(DV.passt(w, "ab 4 %"))
        self.assertFalse(DV.passt(w, "ab 5 %"))
        self.assertFalse(DV.passt(w, "Keine Dividende"))
        self.assertTrue(DV.passt({"div": 0}, "Keine Dividende"))
        self.assertFalse(DV.passt({"div": 0}, "Nur Dividendenzahler"))
        self.assertTrue(DV.passt(w, "ab 3 %", nur_nachhaltig=True))
        self.assertFalse(DV.passt({"div": 6, "div_q": 120}, "ab 3 %", nur_nachhaltig=True))
        self.assertFalse(DV.passt({"div": None}, "ab 2 %"))

    def test_text_und_uebersicht(self):
        self.assertEqual(DV.text(4.5, 50), "Hoch · nachhaltig")
        self.assertEqual(DV.text(None), "unbekannt")
        u = DV.uebersicht([{"div": 4.5, "div_q": 50, "gesamt": 80, "name": "A"},
                           {"div": 5, "div_q": 150, "gesamt": 60, "name": "B"},
                           {"div": 0, "gesamt": 70, "name": "C"}])
        self.assertEqual([z["schluessel"] for z in u], ["keine", "hoch"])
        hoch = u[1]
        self.assertEqual((hoch["anzahl"], hoch["nachhaltig"], hoch["bester"]["name"]), (2, 1, "A"))
        self.assertAlmostEqual(hoch["schnitt_punkte"], 70.0)


if __name__ == "__main__":
    unittest.main()
