"""Tests fuer startseite.py und indizes.py (Index-Ticker der Startseite) - ohne Streamlit, ohne Netz."""
import unittest

import kurs_vorrat as KV
import indizes as I
import startseite as S


class Indizes(unittest.TestCase):
    def test_auswerten(self):
        a = {"chart": {"result": [{"meta": {"regularMarketPrice": 24012.5, "chartPreviousClose": 23900}}]}}
        self.assertEqual(I.auswerten(a), (24012.5, 23900.0))
        self.assertIsNone(I.auswerten({"chart": {"result": []}}))
        self.assertIsNone(I.auswerten({"chart": {"result": [{"meta": {"regularMarketPrice": 5}}]}}))

    def test_abrufen_zweiter_host(self):
        class R:
            def __init__(self, code, daten=None):
                self.status_code, self._d = code, daten

            def json(self):
                return self._d
        ok = {"chart": {"result": [{"meta": {"regularMarketPrice": 2, "chartPreviousClose": 1}}]}}
        antworten = [R(429), R(200, ok)]
        w = I.abrufen("^GDAXI", lambda url, **kw: antworten.pop(0), "T")
        self.assertEqual(w, {"k": 2.0, "p": 1.0, "t": "T"})
        self.assertIsNone(I.abrufen("^X", lambda url, **kw: (_ for _ in ()).throw(OSError()), "T"))

    def test_neue_datei_behaelt_alte_und_wirft_fremde_raus(self):
        alt = {"werte": {"^GDAXI": {"k": 1}, "^ALT": {"k": 2}}}
        n = I.neue_datei(alt, {"^GSPC": {"k": 3}}, "S")
        self.assertEqual(set(n["werte"]), {"^GDAXI", "^GSPC"})
        self.assertEqual(n["stand"], "S")

    def test_ticker_eintraege_reihenfolge_und_alter(self):
        import datetime
        jetzt = datetime.datetime(2026, 11, 18, 12, tzinfo=datetime.timezone.utc)
        d = {"werte": {"EURUSD=X": {"k": 1.08, "p": 1.07, "t": "2026-11-18T10:00:00+00:00"},
                       "^GDAXI": {"k": 24000, "p": 24000, "t": "2026-11-18T10:00:00+00:00"},
                       "^GSPC": {"k": 6000, "p": 5900, "t": "2026-10-01T10:00:00+00:00"}}}
        e = I.ticker_eintraege(d, jetzt=jetzt)
        self.assertEqual([x[0] for x in e], ["DAX", "EUR/USD"])
        self.assertEqual(I.ticker_eintraege(None), [])

    def test_pfad_wie_vorrat(self):
        self.assertEqual(I.PFAD, KV.PFAD_INDIZES)


class TickerHtml(unittest.TestCase):
    def test_band_doppelt_einheiten_und_maskiert(self):
        h = S.ticker_html([("<b>", 1234.5, 1.25, "€"), ("DAX", 24012.5, -2, ""), ("EUR/USD", 1.0812, 0, "fx")], "Stand")
        self.assertEqual(h.count('class="tk-teil"'), 2)
        self.assertIn("1.234,50&nbsp;€", h)
        self.assertIn("24.012,50 <", h)           # Punkte ohne Waehrung
        self.assertIn("1,0812", h)
        self.assertIn("24.012,50 Punkte", h)
        self.assertIn("+1,25", h)
        self.assertIn("tk-ab", h)
        self.assertNotIn("<b><b>", h)
        self.assertIn('role="marquee"', h)
        self.assertIn("animation-duration:10s", h)     # doppelt so schnell wie zuvor (2,5 s je Wert, mind. 10 s)

    def test_nur_einmal_sichtbar(self):
        """Jede Haelfte des Bands ist mindestens bildschirmbreit - ein Wert erscheint nicht mehrfach nebeneinander."""
        self.assertIn("min-width: calc(100vw + 20rem)", S.CSS)

    def test_leer(self):
        self.assertEqual(S.ticker_html([]), "")


class VorratIndizes(unittest.TestCase):
    def test_indizes(self):
        v = KV.Vorrat(lambda pfad: {"werte": {"^GDAXI": {}}} if pfad == KV.PFAD_INDIZES else None)
        self.assertEqual(list(v.indizes()["werte"]), ["^GDAXI"])
        self.assertEqual(KV.Vorrat(lambda p: None).indizes(), {})


if __name__ == "__main__":
    unittest.main()
