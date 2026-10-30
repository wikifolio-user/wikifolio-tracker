"""ui_stil.ausduennen: Linien fuers Handy ausduennen (ohne Plotly - einfache Ersatz-Spuren)."""
import unittest

import ui_stil as UI


class _Spur:
    def __init__(self, typ, n, customdata=True):
        self.type = typ
        self.x = list(range(n))
        self.y = [2 * i for i in range(n)]
        self.customdata = list(range(n)) if customdata else None
        self.text = None
        self.hovertext = None

    def update(self, werte):
        for k, v in werte.items():
            setattr(self, k, v)


class _Fig:
    def __init__(self, *spuren):
        self.data = spuren


class Ausduennen(unittest.TestCase):
    def test_lange_linie_wird_gekuerzt_erster_und_letzter_bleiben(self):
        s = _Spur("scatter", 1500)
        UI.ausduennen(_Fig(s), 400)
        self.assertLessEqual(len(s.x), 401)
        self.assertEqual((s.x[0], s.x[-1]), (0, 1499))
        self.assertEqual(len(s.y), len(s.x))
        self.assertEqual(len(s.customdata), len(s.x))
        self.assertEqual(s.y[5], 2 * s.x[5])              # Punkte bleiben zusammen

    def test_kurz_kerzen_und_balken_bleiben(self):
        kurz, kerze, balken = _Spur("scatter", 300), _Spur("candlestick", 1500), _Spur("bar", 1500)
        UI.ausduennen(_Fig(kurz, kerze, balken), 400)
        self.assertEqual((len(kurz.x), len(kerze.x), len(balken.x)), (300, 1500, 1500))

    def test_gleich_lange_spuren_gleich_ausgeduennt(self):
        a, b = _Spur("scatter", 1000), _Spur("scatter", 1000, customdata=False)
        UI.ausduennen(_Fig(a, b), 400)
        self.assertEqual(a.x, b.x)


if __name__ == "__main__":
    unittest.main()
