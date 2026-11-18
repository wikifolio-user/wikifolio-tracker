"""Tests fuer startseite.py (Kurs-Ticker der Startseite) - ohne Streamlit, ohne Netz."""
import unittest

import kurs_vorrat as KV
import indizes as I
import startseite as S


def _live(kurs, vor):
    return {"i": [[1, kurs * 0.99], [2, kurs]], "p": vor, "t": "2026-11-18T10:00:00+01:00"}


class TickerDaten(unittest.TestCase):
    def test_depot_ohne_doppelte_dann_indizes(self):
        pos = [{"name": "Mein ETF", "instrument_id": 1}, {"name": "Doppelt", "instrument_id": "1"},
               {"name": "Zwei", "instrument_id": "2"}]
        live = {"1": _live(110, 100), "2": _live(90, 100)}
        ind = {"werte": {"^GDAXI": {"k": 24000.0, "p": 23880.0, "t": "2026-11-18T10:00:00+01:00"}}}
        d = S.ticker_daten(pos, live, ind)
        self.assertEqual([x[0] for x in d], ["Mein ETF", "Zwei", "DAX"])
        self.assertAlmostEqual(d[0][2], 10.0)
        self.assertEqual(d[0][3], "€")
        self.assertEqual(d[2][3], "")             # Punkte

    def test_keine_etf_vergleichswerte_mehr(self):
        """config.BENCHMARKS sind ETFs ("DAX 214,80 €") - im Ticker nur echte Indexstaende."""
        self.assertEqual(S.ticker_daten([], {"42446": _live(214.8, 214.0)}, None), [])

    def test_ohne_kurs_oder_vortag_entfaellt(self):
        live = {"1": {"i": [[1, 5]], "p": None, "t": "x"}}
        self.assertEqual(S.ticker_daten([{"name": "A", "instrument_id": 1}, {"name": "B"}], live), [])
        self.assertEqual(S.ticker_daten(None, None, None), [])

    def test_kurzname(self):
        self.assertEqual(S.kurzname("MSCI World (A0RPWH)"), "MSCI World")
        self.assertTrue(S.kurzname("x" * 50).endswith("…"))
        self.assertLessEqual(len(S.kurzname("x" * 50)), 28)


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

    def test_leer(self):
        self.assertEqual(S.ticker_html([]), "")


class VorratAlleLive(unittest.TestCase):
    def test_alle_live(self):
        v = KV.Vorrat(lambda pfad: {"werte": {"1": {"i": [[1, 2]]}}} if pfad == KV.PFAD_LIVE else None)
        self.assertEqual(list(v.alle_live()), ["1"])
        self.assertEqual(KV.Vorrat(lambda p: None).alle_live(), {})
        v = KV.Vorrat(lambda pfad: {"werte": {"^GDAXI": {}}} if pfad == KV.PFAD_INDIZES else None)
        self.assertEqual(list(v.indizes()["werte"]), ["^GDAXI"])


if __name__ == "__main__":
    unittest.main()
