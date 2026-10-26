import unittest

import investment_scanner2 as E
import klassen_score as KS


def _zeile(typ, name, kennung, j1, j3, j5, j10, vola, maxdd, jahre):
    return [typ, typ, name, kennung, "DE000" + kennung, j1, j3, j5, j10, 100.0, None, vola, maxdd, jahre]


FELDER = ["typ", "kat", "name", "kennung", "isin", "1J", "3J", "5J", "10J", "kurs", "div", "vola", "maxdd", "jahre"]
KATALOG = [{"stand": "2026-10-22", "felder": FELDER, "zeilen": [
    _zeile("etf", "Welt ETF", "A00001", 18.0, 60.0, 80.0, 220.0, 11.0, -32.0, 15.0),
    _zeile("etf", "Nasdaq 3x Daily Leveraged", "A00002", 60.0, 150.0, 300.0, None, 55.0, -80.0, 8.0),
    _zeile("etf", "Neuer Themen ETF", "A00003", -3.0, None, None, None, 20.0, -25.0, 1.2),
    _zeile("etf", "Ohne Daten", "A00004", None, None, None, None, None, None, None),
    _zeile("wikifolio", "Ruhiger Langlaeufer", "LS9AAA", 4.0, 12.0, 22.0, None, 2.5, -9.0, 9.0),
    _zeile("wikifolio", "Starker Trader", "LS9BBB", 25.0, 90.0, 180.0, None, 14.0, -22.0, 8.0),
    _zeile("wikifolio", "Raketen-Start", "LS9CCC", 400.0, None, None, None, 60.0, -55.0, 1.0),
    _zeile("aktie", "Eine Aktie", "AKT001", 30.0, 90.0, 150.0, None, 25.0, -40.0, 10.0),
]}]


class Bewertung(unittest.TestCase):
    def test_gewichte_je_klasse_100(self):
        for art, kriterien in KS.KRITERIEN.items():
            self.assertEqual(sum(g for _, _, g, _, _ in kriterien), 100, art)
        # eigene Kriterien: wikifolios bewerten den Rueckgang statt der Schwankung je Rendite
        self.assertIn("rdd", [k for k, *_ in KS.KRITERIEN["wikifolio"]])
        self.assertIn("rr", [k for k, *_ in KS.KRITERIEN["etf"]])

    def test_rangliste_nur_eigene_klasse(self):
        etf = KS.rangliste(KATALOG, "etf")
        self.assertEqual([e["name"] for e in etf][0], "Welt ETF")
        self.assertNotIn("Ohne Daten", [e["name"] for e in etf])            # ohne Kursdaten kein Score
        self.assertNotIn("Eine Aktie", [e["name"] for e in etf])
        self.assertEqual([e["rang"] for e in etf], list(range(1, len(etf) + 1)))
        wiki = KS.rangliste(KATALOG, "wikifolio")
        self.assertEqual({e["name"] for e in wiki}, {"Ruhiger Langlaeufer", "Starker Trader", "Raketen-Start"})
        self.assertEqual(wiki[0]["name"], "Starker Trader")

    def test_hebel_gedeckelt_und_nie_prio(self):
        b = KS.bewerte(dict(zip(FELDER, KATALOG[0]["zeilen"][1])), "etf")
        self.assertTrue(b["hebel"])
        self.assertLessEqual(b["score"], KS.HEBEL_DECKEL)
        self.assertNotEqual(b["einordnung"], "prio")

    def test_kurze_historie_nie_prio_und_hinweis(self):
        b = KS.bewerte(dict(zip(FELDER, KATALOG[0]["zeilen"][6])), "wikifolio")
        self.assertNotEqual(b["einordnung"], "prio")
        self.assertTrue(any("Ausnahme-Rendite" in h for h in b["hinweise"]))
        self.assertTrue(any("kurze Historie" in h for h in b["hinweise"]))

    def test_kennzahlen(self):
        k = KS.kennzahlen({"1J": 10.0, "5J": 61.05, "vola": 0.0, "maxdd": -20.0, "jahre": 4.0})
        self.assertAlmostEqual(k["rendite"], 10.0, places=1)           # laengster Zeitraum: 5 Jahre p. a.
        self.assertEqual(k["rendite_jahre"], 5)
        self.assertIsNone(k["vola"])                                    # 0 = nicht gemessen
        self.assertIsNone(k["rr"])
        self.assertAlmostEqual(k["rdd"], 0.5, places=2)
        self.assertEqual(k["jahre"], 5.0)
        self.assertEqual(k["bestaendig"], 100.0)

    def test_staerken_schwaechen(self):
        b = KS.bewerte(dict(zip(FELDER, KATALOG[0]["zeilen"][0])), "etf")
        st, sw = KS.staerken_schwaechen(b, "etf")
        self.assertTrue(st)
        self.assertLessEqual(len(st), 3)
        self.assertLessEqual(len(sw), 3)

    def test_pdf(self):
        import wikifolio_pdf
        for art in ("etf", "wikifolio"):
            pdf = wikifolio_pdf.score_bericht(KS.rangliste(KATALOG, art), art, "Stand heute")
            self.assertTrue(pdf.startswith(b"%PDF"))


class Scanner2(unittest.TestCase):
    def test_etf_und_wikifolio_mit_eigenem_score(self):
        u = {a["name"]: a for a in E.universum(KATALOG, stand="2026-10-22")}
        self.assertNotIn("Nasdaq 3x Daily Leveraged", u)                 # Hebel bleibt draussen
        etf = E.calc_score(u["Welt ETF"], [])
        self.assertEqual(etf["basis"], "etf")
        self.assertIsNotNone(etf["value"])
        self.assertEqual(sum(etf["weights"].values()), 105)              # 100 Klasse + 5 Depot-Ergaenzung
        self.assertEqual(set(etf["details"]), set(etf["weights"]))
        wiki = E.calc_score(u["Starker Trader"], [])
        self.assertEqual(wiki["basis"], "wikifolio")
        self.assertIn("Rendite je Rückgang", wiki["details"])
        aktie = E.calc_score(u["Eine Aktie"], [])
        self.assertEqual(aktie["basis"], "allgemein")                    # Aktien unveraendert
        self.assertEqual(aktie["weights"], E.SCORE_WEIGHTS)

    def test_score_folgt_klassen_score(self):
        u = {a["name"]: a for a in E.universum(KATALOG, stand="2026-10-22")}
        ks = u["Welt ETF"]["klassenScore"]["score"]
        self.assertAlmostEqual(E.calc_score(u["Welt ETF"], [])["value"], round(ks * 0.95 + 100 * 0.05, 1))


class ProJahr(unittest.TestCase):
    def test_pro_jahr(self):
        self.assertAlmostEqual(KS.pro_jahr(21.0, 2), 10.0, places=6)      # 1,1^2 = 1,21
        self.assertEqual(KS.pro_jahr(5.0, 1), 5.0)
        self.assertIsNone(KS.pro_jahr(None, 3))
        self.assertIsNone(KS.pro_jahr(-100.0, 3))

    def test_kennzahlen_je_zeitraum_und_gesamt(self):
        w = dict(zip(FELDER + ["gesamt"], _zeile("etf", "Welt", "A1", 18.0, 60.0, 80.0, 220.0, 11.0, -32.0, 15.0)
                     + [300.0]))
        pa = KS.kennzahlen(w)["pa"]
        self.assertEqual(pa["1J"], 18.0)
        self.assertAlmostEqual(pa["3J"], (1.6 ** (1 / 3) - 1) * 100, places=6)
        self.assertAlmostEqual(pa["10J"], (3.2 ** 0.1 - 1) * 100, places=6)
        self.assertAlmostEqual(pa["gesamt"], (4.0 ** (1 / 15) - 1) * 100, places=6)
        alt = dict(zip(FELDER, _zeile("etf", "Alt", "A2", 1.0, None, None, None, 5.0, -3.0, 0.5)))
        self.assertIsNone(KS.kennzahlen(alt)["pa"]["gesamt"])          # alte Daten ohne "gesamt"


if __name__ == "__main__":
    unittest.main()
