"""Bewertung (scoring.py): Universum, Perzentile, Richtung, Sektorvergleich, n/a-Behandlung, Suche."""
import unittest

import scoring as sc


def _katalog(zeilen):
    felder = ["typ", "kat", "name", "kennung", "isin", "1J", "3J", "5J", "10J", "kurs", "div", "vola", "maxdd",
              "jahre", "gesamt"]
    return [{"felder": felder, "zeilen": [[z.get(f) for f in felder] for z in zeilen]}]


def _qual(zeilen):
    felder = sorted({k for z in zeilen for k in z})
    return [{"felder": felder, "zeilen": [[z.get(f) for f in felder] for z in zeilen]}]


def _daten(n=30):
    """n Aktien in zwei Branchen (Software teuer, Banken guenstig), 10 ETFs, 10 Wikifolios - synthetisch."""
    kat, qual = [], []
    for i in range(n):
        br = "Software" if i % 2 else "Banken"
        s = f"T{i}"
        kat.append({"typ": "aktie", "kat": "usa", "name": f"Firma {i} {br}", "kennung": s, "isin": "",
                    "1J": i, "kurs": 10 + i, "vola": 20 + i, "maxdd": -10 - i, "jahre": 10})
        qual.append({"s": s, "name": f"Firma {i} {br}", "br": br, "kurs": 10 + i, "kwae": "USD",
                     "fkgv": (40 if br == "Software" else 8) + i, "roic": i, "om": i, "g_ums": i, "nde": 3 - i / 10,
                     "div": (i % 5) or None, "p6": i, "p12": i})
    for i in range(10):
        kat.append({"typ": "etf", "kat": "etf", "name": f"Index ETF {i}", "kennung": f"E{i}", "isin": f"IE00{i}",
                    "1J": i, "3J": 10 * i, "5J": 20 * i, "10J": 50 * i, "vola": 10 + i, "maxdd": -20 - i, "jahre": 8})
        kat.append({"typ": "wikifolio", "kat": "wikifolios", "name": f"Strategie {i}", "kennung": f"W{i}",
                    "isin": f"DE000LS{i}", "1J": i, "3J": 5 * i, "5J": None, "vola": 15, "maxdd": -30, "jahre": 4})
    return _katalog(kat), _qual(qual)


class Universum(unittest.TestCase):
    def setUp(self):
        k, q = _daten()
        self.u = sc.universum(k, q)
        self.ver = sc.verteilungen(self.u)
        self.je = {e["ticker"] or e["wkn"]: e for e in self.u}

    def test_klassen_und_felder(self):
        arten = [e["art"] for e in self.u]
        self.assertEqual((arten.count("aktie"), arten.count("etf"), arten.count("wikifolio")), (30, 10, 10))
        a = self.je["T3"]
        self.assertEqual((a["sektor"], a["waehrung"], a["kurs"]), ("Software", "USD", 13))
        self.assertNotIn("kgv", a["k"])                       # nicht vorhanden -> gar nicht im Dict

    def test_dubletten_werden_zusammengefuehrt(self):
        k, q = _daten(4)
        k[0]["zeilen"].append(["aktie", "aktien", "Firma Eins", "123456", "US0001", 1, 1, 1, 1, 1, None, 20, -10,
                               5, 1])
        u = sc.universum(k, q, yahoo_isin={"US0001": "T1"})
        t1 = [e for e in u if e["ticker"] == "T1"]
        self.assertEqual(len(t1), 1)
        self.assertEqual((t1[0]["wkn"], t1[0]["isin"]), ("123456", "US0001"))

    def test_pro_jahr(self):
        self.assertAlmostEqual(sc.pro_jahr(21, 2), 10.0, places=6)
        self.assertIsNone(sc.pro_jahr(None, 3))
        self.assertIsNone(sc.pro_jahr(-100, 3))

    def test_etf_rendite_p_a(self):
        e = self.je["E2"]
        self.assertAlmostEqual(e["k"]["r3"], sc.pro_jahr(20, 3))


class Perzentile(unittest.TestCase):
    def test_richtung(self):
        werte = sorted(range(1, 11))
        self.assertEqual(sc.perzentil(werte, 10, +1), 95.0)     # hoch = gut
        self.assertEqual(sc.perzentil(werte, 10, -1), 5.0)      # hoch = schlecht
        self.assertEqual(sc.perzentil(werte, 1, -1), 95.0)

    def test_zu_wenige_vergleichswerte(self):
        self.assertIsNone(sc.perzentil([1, 2, 3], 2, +1))
        self.assertIsNone(sc.perzentil(list(range(10)), None, +1))

    def test_negatives_kgv_ist_schlechtester_rang(self):
        werte = sorted([5, 10, 15, 20, 25, sc._vergleichswert("fkgv", -3)])
        self.assertLess(sc.perzentil(werte, sc._vergleichswert("fkgv", -3), -1), 10)

    def test_negative_ev_multiplikatoren_sind_na(self):
        self.assertIsNone(sc._vergleichswert("ev_ebit", -12.0))
        self.assertIsNone(sc._vergleichswert("ev_ebitda", 0.0))
        self.assertEqual(sc._vergleichswert("ev_ebit", 12.0), 12.0)

    def test_median_ohne_unendlich(self):
        self.assertEqual(sc.median([1.0, 2.0, 3.0, float("inf")]), 2.0)


class Bewerten(unittest.TestCase):
    def setUp(self):
        k, q = _daten()
        self.u = sc.universum(k, q)
        self.ver = sc.verteilungen(self.u)
        self.je = {e["ticker"] or e["wkn"]: e for e in self.u}

    def test_kgv_sektorrelativ(self):
        # Software-KGV 40+i, Banken 8+i: die teuerste Bank ist guenstiger als jede Software-Aktie, im
        # eigenen Sektor aber die teuerste -> schlechtes Perzentil
        b = sc.bewerten(self.je["T28"], self.ver)
        z = next(z for z in b["kennzahlen"] if z["key"] == "fkgv")
        self.assertEqual(z["basis"], "sektor")
        self.assertLess(z["perzentil"], 10)
        self.assertEqual(z["einordnung"], "schlecht")

    def test_kleiner_sektor_vergleicht_mit_allen(self):
        alt = sc.MIN_SEKTOR
        try:
            sc.MIN_SEKTOR = 100
            b = sc.bewerten(self.je["T28"], self.ver)
            z = next(z for z in b["kennzahlen"] if z["key"] == "fkgv")
            self.assertEqual(z["basis"], "alle")
            self.assertGreater(z["perzentil"], 40)               # gegen alle ist eine Bank eher guenstig
        finally:
            sc.MIN_SEKTOR = alt

    def test_fehlende_werte_sind_na_und_nicht_null(self):
        e = self.je["T5"]                                      # i % 5 == 0 -> keine Dividende
        b = sc.bewerten(e, self.ver)
        z = next(z for z in b["kennzahlen"] if z["key"] == "div")
        self.assertEqual((z["wert"], z["perzentil"], z["einordnung"]), (None, None, "n/a"))
        div = next(c for c in b["kategorien"] if c["key"] == "dividende")
        self.assertIsNone(div["score"])
        # Gesamtscore = gewichteter Mittelwert NUR der vorhandenen Teilscores
        mit = [c for c in b["kategorien"] if c["score"] is not None]
        erwartet = sum(c["score"] * c["gewicht"] for c in mit) / sum(c["gewicht"] for c in mit)
        self.assertAlmostEqual(b["gesamt"], erwartet)

    def test_besser_ist_besser(self):
        gut, schlecht = sc.bewerten(self.je["T29"], self.ver), sc.bewerten(self.je["T1"], self.ver)
        q = lambda b: next(c["score"] for c in b["kategorien"] if c["key"] == "qualitaet")
        self.assertGreater(q(gut), q(schlecht))
        self.assertTrue(any(z["key"] == "roic" for z in gut["staerken"]))
        self.assertTrue(any(z["key"] == "roic" for z in schlecht["schwaechen"]))

    def test_score_grenzen_ampel_fazit(self):
        for e in self.u:
            b = sc.bewerten(e, self.ver)
            if b["gesamt"] is not None:
                self.assertTrue(0 <= b["gesamt"] <= 100)
                self.assertIn(b["ampel"], ("gruen", "gelb", "rot"))
            self.assertIn(b["fazit"], (None, "unterbewertet", "fair bewertet", "teuer"))
            if e["art"] != "aktie":
                self.assertIsNone(b["fazit"])
        self.assertEqual(sc.ampel(None), "grau")
        self.assertEqual((sc.ampel(80), sc.ampel(50), sc.ampel(10)), ("gruen", "gelb", "rot"))

    def test_zu_wenige_teilbereiche_kein_gesamtscore(self):
        e = dict(self.je["T3"], k={"p12": 3.0})
        b = sc.bewerten(e, self.ver)
        self.assertIsNone(b["gesamt"])
        self.assertEqual(b["ampel"], "grau")
        self.assertIn("Zu wenige", sc.kurzfazit(e, b))

    def test_etf_und_wikifolio(self):
        b = sc.bewerten(self.je["E9"], self.ver)
        self.assertEqual({c["key"] for c in b["kategorien"]}, set(sc.GEWICHTE["etf"]))
        self.assertGreater(b["gesamt"], 50)
        w = sc.bewerten(self.je["W3"], self.ver)
        r5 = next(z for z in w["kennzahlen"] if z["key"] == "r5")
        self.assertEqual(r5["einordnung"], "n/a")

    def test_gewichte_konfiguration_vollstaendig(self):
        for art, g in sc.GEWICHTE.items():
            for kat in g:
                self.assertIn(kat, sc.KATEGORIEN)
                self.assertTrue(any(d[0] == kat and sc.KLASSE_KUERZEL[art] in d[6] for d in sc.KENNZAHLEN.values()),
                                (art, kat))


class Suche(unittest.TestCase):
    def setUp(self):
        k, q = _daten()
        self.u = sc.universum(k, q)

    def test_teilstring_gross_klein(self):
        self.assertEqual(sc.suchen(self.u, "firma 12", 1)[0]["ticker"], "T12")
        self.assertTrue(all(e["art"] == "etf" for e in sc.suchen(self.u, "INDEX etf")))

    def test_kennung_zuerst(self):
        self.assertEqual(sc.suchen(self.u, "t7")[0]["ticker"], "T7")
        self.assertEqual(sc.suchen(self.u, "W3")[0]["wkn"], "W3")
        self.assertEqual(sc.suchen(self.u, "de000ls4")[0]["wkn"], "W4")

    def test_tippfehler(self):
        self.assertTrue(any(e["art"] == "wikifolio" for e in sc.suchen(self.u, "Stratgie")))

    def test_treffer_mitten_im_wort_nach_aehnlichen_namen(self):
        k, q = _daten(4)
        k[0]["zeilen"] += [["wikifolio", "wikifolios", "Mappel Invest", "WM1", "", 1, 1, 1, 1, 1, None, 15, -30, 4, 1],
                           ["aktie", "usa", "Apple", "AAPL", "", 1, 1, 1, 1, 1, None, 20, -40, 10, 1]]
        u = sc.universum(k, q)
        self.assertEqual([e["name"] for e in sc.suchen(u, "appel")][:2], ["Apple", "Mappel Invest"])

    def test_kurz_oder_leer(self):
        self.assertEqual(sc.suchen(self.u, "a"), [])
        self.assertEqual(sc.suchen(self.u, ""), [])


if __name__ == "__main__":
    unittest.main()
