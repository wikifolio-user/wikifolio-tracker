"""Firmen-Kategorien (python3 -m unittest test_branchen)."""
import unittest

import branchen as BR


class Einordnung(unittest.TestCase):
    def test_gekuerzte_yahoo_namen(self):
        self.assertEqual(BR.einordnen("Specialty Industrial Machine"), ("Industrie", "Maschinenbau"))
        self.assertEqual(BR.einordnen("Semiconductor Equipment & Ma"), ("Technologie", "Halbleiterausrüstung"))
        self.assertEqual(BR.einordnen("Semiconductors"), ("Technologie", "Halbleiter"))
        self.assertEqual(BR.einordnen("Insurance Brokers"), ("Finanzen", "Versicherungsmakler"))
        self.assertEqual(BR.einordnen("Insurance—Life"), ("Finanzen", "Versicherungen"))
        self.assertEqual(BR.einordnen("Beverages—Non-Alcoholic"), ("Basiskonsum", "Alkoholfreie Getränke"))
        self.assertEqual(BR.einordnen("Specialty Chemicals"), ("Rohstoffe", "Spezialchemie"))
        self.assertEqual(BR.einordnen("Chemicals"), ("Rohstoffe", "Chemie"))

    def test_unbekannt(self):
        self.assertEqual(BR.einordnen(""), ("Sonstige", "unbekannt"))
        self.assertEqual(BR.einordnen(None), ("Sonstige", "unbekannt"))
        self.assertEqual(BR.einordnen("Neue Branche XY"), ("Sonstige", "Neue Branche XY"))

    def test_text_und_vollstaendigkeit(self):
        self.assertEqual(BR.kategorie_text("Gold"), "Rohstoffe · Gold")
        self.assertEqual(BR.kategorie_text(""), "Sonstige")
        self.assertEqual(set(BR.SEKTOR_ICON) - {"Sonstige"}, set(BR.SEKTOREN))
        self.assertTrue(all(s in BR.SEKTOREN for _, s, _ in BR._TABELLE))


if __name__ == "__main__":
    unittest.main()
