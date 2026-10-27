"""Helle Ansicht (ui_hell): Farbumrechnung, CSS-Umschreibung, Modi."""
import unittest

import ui_hell as H


def _kontrast(a, b):
    def lum(h):
        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b_)
    l1, l2 = sorted((lum(a), lum(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


class Farben(unittest.TestCase):
    def test_flaechen_hell_text_dunkel(self):
        self.assertGreater(_kontrast(H.hell("#0B1220"), "#000000"), 15)     # Seitengrund wird hell
        self.assertEqual(H.hell("#FFFFFF"), "#0F1B2D")                        # weisse Schrift -> Navy

    def test_kursfarben_lesbar_auf_hell(self):
        grund = H.hell("#0B1220")
        for farbe in ("#16C784", "#EA3943", "#5B9BFF", "#F5B942", "#AEBDD0", "#7F90A8"):
            self.assertGreaterEqual(_kontrast(H.hell(farbe), grund), 4.2, farbe)

    def test_transparente_weisse_ueberlagerung_wird_dunkle(self):
        self.assertTrue(H.hell("rgba(255, 255, 255, 0.06)").startswith("rgba(15, 27, 45"))


class Umschreiben(unittest.TestCase):
    def test_nur_farbregeln_mit_hoeherer_spezifitaet(self):
        aus = H.umschreiben(".a { color: #FFFFFF; font-size: 2rem; } .b { margin: 0; }")
        self.assertIn(".a:not(#fd-hell) { color: #0F1B2D !important; }", aus)
        self.assertNotIn("font-size", aus)
        self.assertNotIn(".b", aus)

    def test_verlauf_als_background_image(self):
        aus = H.umschreiben(".t { background: linear-gradient(90deg, #FFFFFF 0%, #0B1220 100%); "
                            "-webkit-background-clip: text; }")
        self.assertIn("background-image: linear-gradient", aus)
        self.assertNotIn("background: linear", aus)

    def test_pseudoelement_bleibt_am_ende(self):
        aus = H.umschreiben(".k::after { border: 1px solid #FFFFFF; }")
        self.assertIn(".k:not(#fd-hell)::after", aus)

    def test_media_bleibt_keyframes_fallen_weg(self):
        aus = H.umschreiben("@media (max-width: 600px) { .x { color: #E8EEF6; } } "
                            "@keyframes p { 0% { color: #FFFFFF; } }")
        self.assertIn("@media (max-width: 600px)", aus)
        self.assertNotIn("@keyframes", aus)

    def test_weisse_schrift_auf_kraeftiger_flaeche_bleibt(self):
        aus = H.umschreiben(".sym { background: #2563EB; color: #FFFFFF; }")
        self.assertNotIn("color: #0F1B2D", aus)


class Modi(unittest.TestCase):
    def test_dunkel_ohne_zusatz(self):
        self.assertEqual(H.stil("dunkel"), "")
        self.assertEqual(H.stil("unbekannt"), "")

    def test_auto_folgt_dem_geraet(self):
        self.assertIn("@media (prefers-color-scheme: light)", H.stil("auto"))
        self.assertNotIn("prefers-color-scheme", H.stil("hell"))


if __name__ == "__main__":
    unittest.main()
