"""Wikifolio-Liste: Risiko-Kennzahlen aus Kursreihen, Laden, Filter, Mein Score, Rangliste."""
import datetime
import math
import unittest

import risiko_kennzahlen as RK
import wikifolio_liste as WL

T0 = datetime.date(2020, 1, 1)


def reihe(kurse):
    return [(T0 + datetime.timedelta(days=i), k) for i, k in enumerate(kurse)]


class Risiko(unittest.TestCase):
    def test_gerade_linie(self):
        # 4 Jahre stetig +10 % p. a., keine Rueckgaenge
        n = 4 * 365
        k = RK.kennzahlen(reihe([100 * 1.1 ** (i / 365.25) for i in range(n)]))
        self.assertAlmostEqual(k["rendite_pa"], 10.0, delta=0.1)
        self.assertEqual(k["maxdd"], 0.0)
        self.assertEqual(k["dd_akt"], 0.0)
        self.assertEqual(k["tage_unter_hoch"], 0)
        self.assertEqual(k["gewinnmonate"], 100.0)
        self.assertGreater(k["sma200"], 0)
        self.assertLess(k["vola1j"], 0.1)

    def test_rueckgang_und_monate(self):
        kurse = [100.0] * 100 + [50.0] * 100 + [80.0] * 200        # -50 %, dann Erholung auf 80
        k = RK.kennzahlen(reihe(kurse))
        self.assertEqual(k["maxdd"], -50.0)
        self.assertEqual(k["dd_akt"], -20.0)
        self.assertEqual(k["tage_unter_hoch"], 300)                 # Hoch zuletzt am Tag 99
        self.assertEqual(k["schlechtester_monat"], -50.0)
        self.assertIsNone(k["vola3j"])                              # keine 3 Jahre Historie
        self.assertIsNone(k["calmar3j"])

    def test_zu_kurz_und_kaputt(self):
        self.assertEqual(RK.kennzahlen(reihe([100.0] * 10)), {})
        k = RK.kennzahlen(reihe([100.0, 0, None] + [100.0] * 40))
        self.assertTrue(all(v is None or math.isfinite(v) for v in k.values()))


FELDER = ["wkn", "name", "isin", "1M", "3M", "6M", "1J", "2J", "3J", "5J"] + list(RK.FELDER)


def zeile(wkn, j1, sharpe, maxdd, vola, gewinn, sma):
    r = dict.fromkeys(FELDER)
    r.update(wkn=wkn, name=wkn.lower(), isin="", **{"1J": j1}, sharpe1j=sharpe, maxdd=maxdd, vola1j=vola,
             gewinnmonate=gewinn, sma200=sma, rendite_pa=j1)
    return [r[f] for f in FELDER]


TEILE = [{"felder": FELDER, "zeilen": [zeile("LS9A", 20.0, 1.5, -10.0, 8.0, 70, 5.0),
                                       zeile("LS9B", 60.0, 0.8, -45.0, 30.0, 55, -3.0),
                                       zeile("LS9C", -5.0, -0.2, -20.0, 12.0, 40, 2.0)]}]


class Liste(unittest.TestCase):
    def setUp(self):
        self.w = WL.laden(TEILE, {"LS9A": {"score": 80, "einordnung": "prio", "rdd": 2.0, "jahre": 5.0}})

    def test_laden(self):
        self.assertEqual(set(self.w), {"LS9A", "LS9B", "LS9C"})
        self.assertEqual(self.w["LS9A"]["perf"], {"1J": 20.0})
        self.assertEqual(self.w["LS9A"]["kz"]["score"], 80)
        self.assertEqual(self.w["LS9A"]["kz"]["_einordnung"], "prio")

    def test_filter(self):
        self.assertEqual(set(WL.filtern(self.w, {"maxdd": 25})), {"LS9A", "LS9C"})       # hoechstens 25 % Verlust
        self.assertEqual(set(WL.filtern(self.w, {"vola1j": 10})), {"LS9A"})
        self.assertEqual(set(WL.filtern(self.w, {"sharpe1j": 1.0})), {"LS9A"})
        self.assertEqual(set(WL.filtern(self.w, {}, nur_aufwaerts=True)), {"LS9A", "LS9C"})
        self.assertEqual(set(WL.filtern(self.w, {"jahre": 1})), {"LS9A"})                # ohne Wert -> raus

    def test_mein_score(self):
        WL.mein_score(self.w, {"sharpe1j": 1, "maxdd": 1})
        s = {k: v["kz"]["mein_score"] for k, v in self.w.items()}
        self.assertEqual(s["LS9A"], 100.0)                                               # bester in beidem
        self.assertLess(s["LS9B"], s["LS9A"])
        self.w["LS9C"]["kz"]["sharpe1j"] = None
        WL.mein_score(self.w, {"sharpe1j": 3, "maxdd": 1})                                # nur 1 von 4 belegt
        self.assertIsNone(self.w["LS9C"]["kz"]["mein_score"])
        WL.mein_score(self.w, {"sharpe1j": 1, "maxdd": 1})                                # Haelfte reicht
        self.assertIsNotNone(self.w["LS9C"]["kz"]["mein_score"])
        WL.mein_score(self.w, {})
        self.assertIsNone(self.w["LS9A"]["kz"]["mein_score"])

    def test_rangliste_richtung(self):
        self.assertEqual([w["wkn"] for w in WL.rangliste(self.w, "1J")], ["LS9B", "LS9A", "LS9C"])
        self.assertEqual([w["wkn"] for w in WL.rangliste(self.w, "vola1j")], ["LS9A", "LS9C", "LS9B"])  # klein zuerst
        self.assertEqual([w["wkn"] for w in WL.rangliste(self.w, "maxdd")], ["LS9A", "LS9C", "LS9B"])
        self.assertEqual([(w["wkn"], w["rang"]) for w in WL.rangliste(self.w, "1J", "ls9c")], [("LS9C", 3)])


class Wichtigkeit(unittest.TestCase):
    def test_reihenfolge(self):
        self.assertEqual(WL.nach_wichtigkeit(["1M", "jahre", "1J", "score", "xyz", "maxdd"]),
                         ["score", "1J", "maxdd", "1M", "jahre", "xyz"])
        alle = set(WL.ZEITRAEUME) | set(WL.BESSER_GROSS)
        self.assertEqual(set(WL.WICHTIGKEIT), alle)                                   # nichts vergessen


class EtfMerkmale(unittest.TestCase):
    def test_namen(self):
        import etf_merkmale as EM
        m = EM.merkmale("iShares Core MSCI World UCITS ETF USD (Acc)")
        self.assertEqual((m["anbieter"], m["region"], m["themen"], m["ertrag"], m["hebel"]),
                         ("iShares", "Welt", [EM.THEMA_BREIT], "Thesaurierend", False))
        m = EM.merkmale("Xtrackers II Eurozone Government Bond 1D")
        self.assertEqual((m["anbieter"], m["region"], m["themen"], m["ertrag"]),
                         ("Xtrackers", "Europa", ["Anleihen"], "Ausschüttend"))
        m = EM.merkmale("SPDR S&P US Dividend Aristocrats UCITS ETF (Dist)")
        self.assertEqual((m["region"], m["themen"], m["ertrag"]), ("USA", ["Dividende"], "Ausschüttend"))
        self.assertEqual(EM.merkmale("WisdomTree Physical Gold")["themen"], ["Edelmetalle"])
        self.assertTrue(EM.merkmale("Leverage Shares 3x Long Tesla")["hebel"])
        self.assertIsNone(EM.merkmale("Amundi S&P 500 Small Cap")["ertrag"])          # "Cap" ist kein Acc
        self.assertEqual(EM.merkmale("")["anbieter"], "Sonstige")

    def test_passt(self):
        import etf_merkmale as EM
        mm = EM.merkmale("iShares Global Clean Energy (Dist)")
        self.assertTrue(EM.passt(mm, {}))
        self.assertTrue(EM.passt(mm, {"themen": {"Nachhaltig/ESG", "Gesundheit"}}))
        self.assertFalse(EM.passt(mm, {"themen": {"Gesundheit"}}))
        self.assertFalse(EM.passt(mm, {"ertrag": {"Thesaurierend"}}))
        self.assertTrue(EM.passt(mm, {"anbieter": {"iShares"}, "region": {"Welt"}, "ohne_hebel": True}))
        self.assertFalse(EM.passt(EM.merkmale("Daily 2x Short DAX"), {"ohne_hebel": True}))


FELDER_NEU = FELDER[:10] + ["10J", "div"] + FELDER[10:]


def etf_zeile(wkn, name, j1, div=None):
    r = dict.fromkeys(FELDER_NEU)
    r.update(wkn=wkn, name=name, isin="IE00" + wkn, **{"1J": j1, "10J": 9.0}, div=div, rendite_pa=j1)
    return [r[f] for f in FELDER_NEU]


class EtfListe(unittest.TestCase):
    def setUp(self):
        teile = [{"felder": FELDER_NEU, "zeilen": [
            etf_zeile("A0RPWH", "iShares Core MSCI World UCITS ETF (Acc)", 12.0),
            etf_zeile("A1JX52", "Vanguard FTSE All-World High Dividend Yield (Dist)", 8.0, 3.1),
            etf_zeile("LEV3X", "Leverage Shares 3x Long Nasdaq", 70.0)]}]
        self.w = WL.laden(teile, {"IE00A0RPWH": {"score": 70, "rr": 0.8, "jahre": 15}}, art="etf")

    def test_laden_mit_merkmalen(self):
        w = self.w["A0RPWH"]
        self.assertEqual(w["mm"]["anbieter"], "iShares")
        self.assertEqual(w["kz"]["rr"], 0.8)                                           # Katalog ueber ISIN
        self.assertEqual(w["perf"]["10J"], 9.0)
        self.assertEqual(self.w["A1JX52"]["kz"]["div"], 3.1)
        self.assertIn("div", WL.vorhandene(self.w))
        self.assertNotIn("div", WL.vorhandene(WL.laden(TEILE)))                         # alte Dateien: keine Dividende

    def test_filter_merkmale_und_dividende(self):
        self.assertEqual(set(WL.filtern(self.w, {}, merkmale={"ohne_hebel": True})), {"A0RPWH", "A1JX52"})
        self.assertEqual(set(WL.filtern(self.w, {"div": 2.0})), {"A1JX52"})
        self.assertEqual(set(WL.filtern(self.w, {}, merkmale={"themen": {"Dividende"}})), {"A1JX52"})
        self.assertEqual([w["wkn"] for w in WL.rangliste(self.w, "1J", "ie00a1jx")], ["A1JX52"])  # Suche ISIN


class AgentSchreibt(unittest.TestCase):
    def test_etf_und_wikifolio_dateien(self):
        import top50_agent as A
        geschrieben = {}
        alt = A.speichere_state
        A.speichere_state = lambda pfad, daten, msg="": geschrieben.__setitem__(pfad, daten)
        try:
            perf = {"e1": {"1J": 10.0, "10J": 7.0, "_div": 2.345, "_risiko": {"sharpe1j": 0.9}},
                    "w1": {"1J": 30.0, "_risiko": {"maxdd": -12.0}}}
            mitglieder = {"etf": [("e1", "iShares Core MSCI World", "A0RPWH", "IE00B4L5Y983"),
                                  ("e1", "doppelt", "A0RPWH", "")],
                          "wikifolios": [("w1", "Test", "LS9ABC", "")]}
            A.wikifolio_kennzahlen_schreiben(mitglieder, perf, {"stand": "2026-11-02"})
        finally:
            A.speichere_state = alt
        self.assertEqual(len(geschrieben), 2 * A.WIKI_KZ_TEILE)
        etf = [dict(zip(d["felder"], z)) for p, d in geschrieben.items() if "etf_" in p for z in d["zeilen"]]
        self.assertEqual(len(etf), 1)                                                 # doppelte ID nur einmal
        self.assertEqual((etf[0]["10J"], etf[0]["div"], etf[0]["sharpe1j"]), (7.0, 2.35, 0.9))
        wiki = WL.laden([d for p, d in geschrieben.items() if "wikifolio_" in p])
        self.assertEqual(wiki["LS9ABC"]["kz"]["maxdd"], -12.0)


if __name__ == "__main__":
    unittest.main()
