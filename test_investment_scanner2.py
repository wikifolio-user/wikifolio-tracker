"""Tests Investment Scanner 2.0 (synthetische Daten)."""
import unittest

import investment_scanner2 as S


def wert(i, typ="Aktie", preis=50.0, r12=10.0, vola=20.0, dd=-25.0, q=None, kgv=None):
    return {"id": f"X{i}", "name": f"Wert {i}", "type": typ, "price": preis, "rank": i, "sector": "",
            "return12mPct": r12, "return3mPct": None, "volatility12mPct": vola, "maxDrawdown12mPct": dd,
            "qualityScore": q, "annualCostPct": None, "peRatio": kgv, "volumeEur": None, "spreadPct": None}


class Score(unittest.TestCase):
    def test_abdeckung_und_kein_schaetzen(self):
        nur_kurs = S.calc_score(wert(1), [])                  # Momentum + Risiko = 50 von 95 -> kein Score
        self.assertIsNone(nur_kurs["value"])
        self.assertAlmostEqual(nur_kurs["coverage"], 52.6, places=1)
        aktie = S.calc_score(wert(2, q=80, kgv=20), [])        # + Qualitaet + KGV = 90 -> Score
        self.assertIsNotNone(aktie["value"])
        ohne_risiko = S.calc_score(wert(3, vola=None, dd=None, q=80, kgv=20), [])
        self.assertIsNone(ohne_risiko["value"])                # Risikokennzahl ist Pflicht

    def test_rangliste_score_vor_quellenrang(self):
        k = [wert(1), wert(2, q=90, kgv=15), wert(3, q=40, kgv=40)]
        r = S.rangliste(k, [])
        self.assertEqual([a["id"] for a in r], ["X2", "X3", "X1"])
        self.assertEqual([a["id"] for a in S.rangliste(k, [], "rank")], ["X1", "X2", "X3"])


class Plan(unittest.TestCase):
    def test_kaufplan_ganze_stuecke_reserve_und_grenze(self):
        k = [wert(i, "ETF", 100.0) for i in range(1, 4)] + [wert(i, "Aktie", 30.0, q=70, kgv=18) for i in range(4, 8)]
        inp = S.eingaben(capital=10000, goal=12000, years=5, reservePct=10, maxLinePct=20, fee=1)
        erg = S.berechnen(inp, k, [], {"ETF", "Aktie"}, modus="ausgewogen")
        m = erg["plans"]["ausgewogen"]
        self.assertAlmostEqual(m["reserve"], 1000.0)
        self.assertLessEqual(m["investedNew"] + m["fees"], 9000.0 + 1e-6)
        for o in m["orders"]:
            self.assertEqual(o["shares"], int(o["shares"]))
            self.assertLessEqual(o["amount"], 10000 * 0.2 + 1e-6)
        self.assertAlmostEqual(m["investedNew"] + m["fees"] + m["cash"], 10000.0, places=6)
        self.assertGreater(m["investedNew"], 8000)

    def test_sofortentnahme_mit_verkauf(self):
        bestand = [{"id": "B1", "name": "Bestand", "type": "ETF", "shares": 10, "price": 100.0}]
        inp = S.eingaben(capital=200, takeNow=500, fee=1)
        wd = S.sofortentnahme(inp, bestand)
        self.assertAlmostEqual(wd["fromCapital"], 200.0)
        self.assertEqual(wd["sales"][0]["shares"], 4)          # ceil((300 + 1) / 100)
        self.assertAlmostEqual(wd["paid"], 500.0)
        self.assertEqual(wd["snapshot"][0]["shares"], 6)

    def test_monatsentnahme_und_luecke(self):
        inp = S.eingaben(takeMonthly=100, takeStart=1, takeEnd=0)
        f = S.simulate_flows(500.0, 0.0, 12, 0.0, 0.0, inp, True)
        self.assertAlmostEqual(f["paid"], 500.0)
        self.assertEqual(f["firstShortfall"], 6)
        self.assertAlmostEqual(f["shortfall"], 700.0)

    def test_noetige_rendite(self):
        inp = S.eingaben()
        r = S.required_rate(10000.0, 0.0, 120, 0.0, 20000.0, inp)
        self.assertAlmostEqual((1 + r / 12) ** 120, 2.0, places=4)
        self.assertIsNone(S.required_rate(1.0, 0.0, 12, 0.0, 1e9, inp))


class Daten(unittest.TestCase):
    def test_universum_und_csv(self):
        kat = [{"felder": ["typ", "kat", "name", "kennung", "isin", "1J", "kurs", "vola", "maxdd"],
                "zeilen": [["aktie", "", "SAP", "716460", "DE0007164600", 12.5, 180.0, 25, 30],
                           ["wikifolio", "", "Wiki", "LS9AAA", "", 40, 150.0, 18, 22],
                           ["aktie", "", "Ohne Kurs", "X", "", 1, 0, 1, 1]]}]
        u = S.universum(kat, {"SAP.DE": {"gesamt": 88, "fkgv": 30, "br": "Software"}}, {"SAP.DE": "DE0007164600"})
        self.assertEqual([a["name"] for a in u], ["SAP", "Wiki"])
        sap = u[0]
        self.assertEqual((sap["type"], sap["qualityScore"], sap["peRatio"], sap["sector"]), ("Aktie", 88, 30, "Software"))
        self.assertEqual(sap["maxDrawdown12mPct"], -30)
        self.assertEqual(u[1]["rank"], 1)                      # hoechste 12-Monats-Rendite
        k, f = S.katalog_aus_csv("id;name;type;price;currency\nA;Alpha;ETF;100,50;EUR\nB;Beta;ETF;;EUR\nC;Gamma;ETF;5;USD\n")
        self.assertEqual([a["price"] for a in k], [100.5])
        self.assertEqual(len(f), 2)
        d, _ = S.depot_aus_csv("id;name;type;shares;price\nA;Alpha;ETF;3;100\n")
        self.assertEqual(d[0]["shares"], 3.0)
        self.assertIn("Score_Rang", S.kaufplan_csv(S.berechnen(S.eingaben(capital=1000), k, d, {"ETF"})))


if __name__ == "__main__":
    unittest.main()
