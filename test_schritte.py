"""Schritt-Fuehrung (schritte.py): Leiste, Sprungziele, Nummerierung."""
import re
import unittest

import schritte as S


class Leiste(unittest.TestCase):
    def test_jeder_link_hat_ein_sprungziel(self):
        for k, liste in S.FUEHRUNG.items():
            ziele = {m for nr in range(1, len(liste) + 1)
                     for m in re.findall(r'id="([^"]+)"', S.titel_html(k, nr))}
            links = set(re.findall(r'href="#([^"]+)"', S.leiste_html(k)))
            self.assertEqual(links, ziele, k)

    def test_ausgeblendete_schritte_fortlaufend_nummeriert(self):
        h = S.leiste_html("depot", aktiv=[1, 3])
        self.assertEqual(re.findall(r"<b>(\d)</b>", h), ["1", "2"])
        self.assertIn("#sf-depot-3", h)
        self.assertNotIn("#sf-depot-2", h)

    def test_spaetere_schritte_ohne_sprung(self):
        h = S.leiste_html("scanner", spaeter=(4,))
        self.assertNotIn("#sf-scanner-4", h)
        self.assertIn("sf-spaeter", h)

    def test_unbekannt_oder_ausserhalb_leer(self):
        self.assertEqual(S.leiste_html("gibtsnicht"), "")
        self.assertEqual(S.titel_html("builder", 99), "")
        self.assertEqual(S.nummer_html("builder", 0), "")

    def test_text_wird_maskiert(self):
        self.assertIn("&lt;b&gt;", S.titel_html("builder", 1, "<b>"))


if __name__ == "__main__":
    unittest.main()
