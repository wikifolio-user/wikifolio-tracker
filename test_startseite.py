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
        self.assertEqual([x[4] for x in e], [True, True])                   # Mi 13 Uhr Berlin: Xetra + Devisen offen
        self.assertEqual(I.ticker_eintraege(None), [])

    def test_boersenstatus_und_stand(self):
        import datetime
        import boersenkalender as BK
        utc = datetime.timezone.utc
        sa = datetime.datetime(2026, 11, 21, 12, tzinfo=utc)
        self.assertFalse(BK.markt_offen("XETRA", sa))
        self.assertFalse(BK.markt_offen("FX", sa))
        self.assertTrue(BK.markt_offen("KRYPTO", sa))
        mo_nacht = datetime.datetime(2026, 11, 23, 2, tzinfo=utc)            # So 21 Uhr New York
        self.assertTrue(BK.markt_offen("FX", mo_nacht))
        self.assertTrue(BK.markt_offen("COMEX", mo_nacht))
        self.assertFalse(BK.markt_offen("COMEX", datetime.datetime(2026, 11, 23, 22, 30, tzinfo=utc)))  # 17:30 NY
        self.assertFalse(BK.markt_offen("TSE", datetime.datetime(2026, 11, 23, 3, tzinfo=utc)))         # 12 Uhr Tokio
        self.assertTrue(BK.markt_offen("TSE", datetime.datetime(2026, 11, 23, 1, tzinfo=utc)))          # 10 Uhr Tokio
        self.assertTrue(BK.markt_offen("NYSE", datetime.datetime(2026, 11, 23, 15, tzinfo=utc)))
        self.assertTrue(set(I.MARKT) >= {s for s, _, _ in I.INDIZES})        # jeder Tickerwert hat einen Markt
        jetzt = datetime.datetime(2026, 11, 21, 13, tzinfo=utc)
        self.assertEqual(I.stand_text({"stand": "2026-11-21T13:35:00+01:00"}, jetzt), "Stand 13:35 Uhr")
        self.assertEqual(I.stand_text({"stand": "2026-11-20T22:10:00+01:00"}, jetzt), "Stand 20.11. 22:10 Uhr")
        self.assertEqual(I.stand_text({}), "")

    def test_pfad_wie_vorrat(self):
        self.assertEqual(I.PFAD, KV.PFAD_INDIZES)


class TickerHtml(unittest.TestCase):
    def test_boersenstatus_im_band(self):
        h = S.ticker_html([("DAX", 24000, 0.5, "", True), ("S&P 500", 6000, -1, "", False), ("Gold", 2000, 0, "$")],
                          "Indizes heute · Stand 13:35 Uhr")
        self.assertEqual(h.count('class="tk-live"'), 2)                      # je Haelfte des Bands einmal
        self.assertEqual(h.count('class="tk-schluss">Schluss<'), 2)
        self.assertIn("Börse geöffnet", h)
        self.assertIn("Schlusskurs", h)
        self.assertIn("Stand 13:35 Uhr", h)

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



import datetime as _dt  # noqa: E402

import news as NW  # noqa: E402

_RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Wirtschaft</title>
<item><title>DAX &amp; Co. legen zu</title><link>https://www.tagesschau.de/a1</link>
<pubDate>Thu, 19 Nov 2026 08:15:00 +0100</pubDate></item>
<item><title><![CDATA[Zinsen <b>sinken</b>]]></title><link>https://www.tagesschau.de/a2</link>
<pubDate>Wed, 18 Nov 2026 18:00:00 +0100</pubDate></item>
<item><title>Ohne Link</title></item>
<item><title>Boese</title><link>javascript:alert(1)</link></item>
<item><title>Uralt</title><link>https://x.de/alt</link><pubDate>Mon, 02 Nov 2026 08:00:00 +0100</pubDate></item>
</channel></rss>"""
_ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>DAX &amp; CO. LEGEN ZU</title>
<link href="https://b.de/x"/><updated>2026-11-19T09:00:00Z</updated></entry>
<entry><title>Neue Meldung</title><link href="https://b.de/y"/><updated>2026-11-19T09:30:00Z</updated></entry></feed>"""
_JETZT = _dt.datetime(2026, 11, 19, 12, 0, tzinfo=NW.datetime.timezone.utc)


class News(unittest.TestCase):
    def test_rss_und_atom(self):
        r = NW.parsen(_RSS, "tagesschau")
        self.assertEqual([x["titel"] for x in r], ["DAX & Co. legen zu", "Zinsen sinken", "Uralt"])
        self.assertEqual(r[0]["zeit"], "2026-11-19T08:15:00+01:00")
        a = NW.parsen(_ATOM, "b")
        self.assertEqual([x["link"] for x in a], ["https://b.de/x", "https://b.de/y"])
        self.assertEqual(NW.parsen("<kaputt", "x"), [])
        self.assertEqual(NW.parsen("", "x"), [])

    def test_zusammenfuehren(self):
        z = NW.zusammenfuehren([NW.parsen(_RSS, "t"), NW.parsen(_ATOM, "b")], _JETZT)
        # neueste zuerst, doppelte Schlagzeile (Gross/Klein, Satzzeichen) nur einmal, zu alte entfallen
        self.assertEqual([x["titel"] for x in z], ["Neue Meldung", "DAX & Co. legen zu", "Zinsen sinken"])

    def test_laden_fehlertolerant(self):
        class A:
            def __init__(self, code, text=""):
                self.status_code, self.text = code, text
        antworten = iter([A(500), A(200, _RSS)])
        e, ok = NW.laden(lambda *a, **k: next(antworten), _JETZT)
        self.assertEqual((ok, len(e)), (1, 2))

        def kaputt(*a, **k):
            raise OSError("netz")
        self.assertEqual(NW.laden(kaputt, _JETZT), ([], 0))

    def test_news_html(self):
        e = [{"titel": "<script>x</script>", "link": "https://a.de/1", "zeit": "2026-11-19T08:15:00+01:00",
              "quelle": "tagesschau"}, {"titel": "boese", "link": "javascript:1", "zeit": None, "quelle": "x"}]
        h = S.news_html(e, _dt.datetime(2026, 11, 19, 12, 0, tzinfo=S.BERLIN))
        self.assertIn("&lt;script&gt;", h)
        self.assertNotIn("javascript:", h)
        self.assertIn('rel="noopener noreferrer"', h)
        self.assertIn(">08:15<", h)
        self.assertIn("tagesschau.de", h)
        self.assertEqual(h.count('tabindex="-1"'), 1)              # Kopie nicht doppelt per Tab erreichbar
        self.assertEqual(S.news_html([]), "")
        self.assertIn("text-align: center", S.CSS)                 # Ueberschrift mittig

    def test_laufband_haelt_am_handy_nicht_an(self):
        """Am Handy bleibt :hover/:active nach einem Tipp haengen - Anhalten nur mit Maus oder Tastatur."""
        import re
        regeln = re.findall(r"([^{}]*)\{[^{}]*animation-play-state: paused", S.CSS)
        self.assertTrue(regeln)
        self.assertFalse(any(":active" in r or ":focus-within" in r for r in regeln))
        self.assertIn("@media (hover: hover) and (pointer: fine) { .tk-rahmen:hover", S.CSS)

    def test_vorrat_news(self):
        v = KV.Vorrat(lambda p: {"eintraege": [{"titel": "x"}]} if p == KV.PFAD_NEWS else None)
        self.assertEqual(v.news(), [{"titel": "x"}])
        self.assertEqual(KV.Vorrat(lambda p: None).news(), [])


if __name__ == "__main__":
    unittest.main()
