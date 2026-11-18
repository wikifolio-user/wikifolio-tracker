"""Tests fuer startseite.py (Kurs-Ticker der Startseite) - ohne Streamlit, ohne Netz."""
import unittest

import kurs_vorrat as KV
import startseite as S


def _live(kurs, vor):
    return {"i": [[1, kurs * 0.99], [2, kurs]], "p": vor, "t": "2026-11-18T10:00:00+01:00"}


class TickerDaten(unittest.TestCase):
    def test_depot_zuerst_dann_vergleich_ohne_doppelte(self):
        pos = [{"name": "Mein ETF", "instrument_id": 1}, {"name": "Doppelt", "instrument_id": "2"}]
        bm = {"DAX (593393)": "2", "Gold (A0S9GB)": "3"}
        live = {"1": _live(110, 100), "2": _live(90, 100), "3": _live(50, 50)}
        d = S.ticker_daten(pos, bm, live)
        self.assertEqual([x[0] for x in d], ["Mein ETF", "Doppelt", "Gold"])
        self.assertAlmostEqual(d[0][2], 10.0)
        self.assertAlmostEqual(d[1][2], -10.0)

    def test_ohne_kurs_oder_vortag_entfaellt(self):
        live = {"1": {"i": [[1, 5]], "p": None, "t": "x"}}
        self.assertEqual(S.ticker_daten([{"name": "A", "instrument_id": 1}, {"name": "B"}], {"C": "9"}, live), [])
        self.assertEqual(S.ticker_daten(None, None, None), [])

    def test_kurzname(self):
        self.assertEqual(S.kurzname("MSCI World (A0RPWH)"), "MSCI World")
        self.assertTrue(S.kurzname("x" * 50).endswith("…"))
        self.assertLessEqual(len(S.kurzname("x" * 50)), 28)


class TickerHtml(unittest.TestCase):
    def test_band_doppelt_und_maskiert(self):
        h = S.ticker_html([("<b>", 1234.5, 1.25), ("Ab", 10, -2)], "Stand")
        self.assertEqual(h.count('class="tk-teil"'), 2)
        self.assertIn("1.234,50", h)
        self.assertIn("+1,25", h)
        self.assertIn("tk-ab", h)
        self.assertNotIn("<b><b>", h)
        self.assertIn('role="marquee"', h)

    def test_leer(self):
        self.assertEqual(S.ticker_html([]), "")


class VorratAlleLive(unittest.TestCase):
    def test_alle_live(self):
        v = KV.Vorrat(lambda pfad: {"werte": {"1": {"i": [[1, 2]]}}} if pfad == KV.PFAD_LIVE else None)
        self.assertEqual(list(v.alle_live()), ["1"])
        self.assertEqual(KV.Vorrat(lambda p: None).alle_live(), {})


if __name__ == "__main__":
    unittest.main()
