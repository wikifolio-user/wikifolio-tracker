"""Tests fuer den Portfolio-Planer (python3 -m unittest test_planer)."""
import unittest

import planer_daten as D
import planer_engine as E


def modell_ohne_optionale():
    m = D.seed_modell()
    return m


def renditen(m, **kw):
    return E.rendite_map(E.alle_renditen(m, **kw))


class Grundformeln(unittest.TestCase):
    def test_required_cagr(self):
        self.assertAlmostEqual(E.required_cagr(15000, 100000, 5), 0.4614, places=4)
        self.assertIsNone(E.required_cagr(0, 100000, 5))

    def test_future_value(self):
        self.assertAlmostEqual(E.future_value(15000, E.required_cagr(15000, 100000, 5), 5), 100000, places=4)
        # Sparrate bei 0 % Rendite = einfache Summe
        self.assertAlmostEqual(E.future_value(1000, 0.0, 2, 100), 1000 + 2400, places=6)

    def test_erforderliche_rendite_mit_sparrate(self):
        r = E.erforderliche_rendite(15000, 100000, 5, 500)
        self.assertLess(r, E.required_cagr(15000, 100000, 5))
        self.assertAlmostEqual(E.future_value(15000, r, 5, 500), 100000, delta=1)

    def test_runden(self):
        self.assertEqual(E.runden_ungefaehr(100013.4), 100000)
        self.assertEqual(E.runden_ungefaehr(57684), 57700)


class Gewichte(unittest.TestCase):
    def test_seed_summe_100(self):
        self.assertAlmostEqual(E.gewichte_summe(D.seed_modell()), 100.0)

    def test_korb_summe_100(self):
        self.assertAlmostEqual(sum(k["gewicht"] for k in D.SEED_KORB), 100.0)

    def test_normalisieren(self):
        m = D.seed_modell()
        m["assets"][0]["targetWeight"] = 13.5          # -> 103,5 %
        self.assertAlmostEqual(E.gewichte_summe(m), 103.5)
        E.normalisieren(m)
        self.assertAlmostEqual(E.gewichte_summe(m), 100.0, places=2)

    def test_deaktivierte_zaehlen_nicht(self):
        m = D.seed_modell()
        self.assertNotIn("etf_gold", E.gewichte(m))


class Annahmen(unittest.TestCase):
    def test_manuell(self):
        m = D.seed_modell()
        r = E.alle_renditen(m)
        self.assertEqual(r["wf_ff"]["brutto"], 0.50)
        self.assertEqual(r["korb"]["brutto"], 0.25)
        self.assertEqual(r["reserve"]["brutto"], 0.0)

    def test_hebel_nicht_2x(self):
        m = D.seed_modell()
        r = E.alle_renditen(m)
        self.assertNotAlmostEqual(r["etf_ndx2x"]["brutto"], 2 * r["etf_ndx"]["brutto"])
        self.assertAlmostEqual(r["etf_ndx2x"]["brutto"], 0.1827)

    def test_historie_fallback(self):
        m = D.seed_modell()
        hist = {"etf_allworld": {"historical5Y": 0.09}}
        r = E.alle_renditen(m, historie=hist, methode="historical5Y")
        self.assertEqual(r["etf_allworld"]["brutto"], 0.09)
        self.assertEqual(r["wf_ff"]["brutto"], 0.50)         # Fallback auf eigene Annahme
        self.assertIsNotNone(r["wf_ff"]["hinweis"])

    def test_szenarien(self):
        m = D.seed_modell()
        self.assertEqual(E.alle_renditen(m, methode="szenario", szenario="bear")["korb"]["brutto"], 0.10)
        self.assertEqual(E.alle_renditen(m, methode="szenario", szenario="bull")["korb"]["brutto"], 0.30)
        # Standardregel fuer Wikifolio ohne eigene Bear-Annahme
        self.assertAlmostEqual(E.alle_renditen(m, methode="szenario", szenario="bear")["wf_ff"]["brutto"], 0.25)

    def test_kosten(self):
        a = {"expenseRatio": 0.01, "performanceFee": 0.10}
        self.assertAlmostEqual(E.netto_rendite(a, 0.20, True), (1.2 * 0.99 - 1) * 0.9)
        self.assertEqual(E.netto_rendite(a, 0.20, False), 0.20)

    def test_setze_annahme(self):
        m = D.seed_modell()
        E.setze_annahme(m, "etf_gold", "manualScenario", 0.08)
        self.assertEqual(E.alle_renditen(m)["etf_allworld"]["brutto"], 0.1108)
        self.assertEqual(E.annahme(m, "etf_gold", "manualScenario")["value"], 0.08)


class Projektion(unittest.TestCase):
    def test_endwert_gleich_gewichtete_fv(self):
        m = D.seed_modell()
        r = renditen(m)
        p = E.projektion(m, r)
        erwartet = sum(15000 * g * (1 + r[i]) ** 5 for i, g in E.gewichte(m).items())
        self.assertAlmostEqual(p["endwert"], erwartet, places=4)
        self.assertEqual(len(p["jahreswerte"]), 6)
        self.assertAlmostEqual(p["jahreswerte"][0], 15000)

    def test_sparrate(self):
        m = D.seed_modell()
        null = {i: 0.0 for i in E.gewichte(m)}
        p = E.projektion(m, null, sparrate=100)
        self.assertAlmostEqual(p["endwert"], 15000 + 100 * 60, places=6)
        self.assertAlmostEqual(p["eingezahlt"], 21000)

    def test_rebalancing_haelt_gewichte(self):
        m = D.seed_modell()
        r = renditen(m)
        p = E.projektion(m, r, rebalancing={"art": "jaehrlich"})
        self.assertEqual(p["rebalancings"], 5)
        w = E.gewichte(m)
        risiko = [i for i in w if i != "reserve"]
        summe = sum(p["endwerte_asset"][i] for i in risiko)
        z = sum(w[i] for i in risiko)
        for i in risiko:
            self.assertAlmostEqual(p["endwerte_asset"][i] / summe, w[i] / z, places=6)

    def test_rebalancing_vs_buy_and_hold(self):
        # Bei konstanten, unterschiedlichen Renditen liegt Buy & Hold vorn
        m = D.seed_modell()
        r = renditen(m)
        bh = E.projektion(m, r)["endwert"]
        jr = E.projektion(m, r, rebalancing={"art": "jaehrlich"})["endwert"]
        self.assertGreater(bh, jr)

    def test_schwelle(self):
        m = D.seed_modell()
        r = renditen(m)
        p = E.projektion(m, r, rebalancing={"art": "schwelle", "schwelle_relativ": 25})
        self.assertGreater(p["rebalancings"], 0)
        gleich = {i: 0.1 for i in r}
        self.assertEqual(E.projektion(m, gleich, rebalancing={"art": "schwelle"})["rebalancings"], 0)


class StressUndReserve(unittest.TestCase):
    def test_pfad(self):
        pfad = E.stress_pfad(D.STRESS, 60)
        self.assertAlmostEqual(min(pfad), 0.65)
        self.assertAlmostEqual(pfad[-1], 1.0)

    def test_reserve_tranchen(self):
        m = D.seed_modell()
        null = {i: 0.0 for i in E.gewichte(m)}
        p = E.projektion(m, null, stress=m["stress"], nachkauf=m["nachkauf"], scores={"korb": 80})
        self.assertEqual(len(p["nachkaeufe"]), 3)
        self.assertEqual([n["drawdown"] <= t["drawdown"] + 1e-6 for n, t in
                          zip(p["nachkaeufe"], m["nachkauf"]["tranchen"])], [True] * 3)
        self.assertAlmostEqual(p["endwerte_asset"]["reserve"], 0.0, places=6)
        self.assertAlmostEqual(sum(n["betrag"] for n in p["nachkaeufe"]), 1500, places=6)

    def test_kein_nachkauf_ohne_score(self):
        m = D.seed_modell()
        null = {i: 0.0 for i in E.gewichte(m)}
        p = E.projektion(m, null, stress=m["stress"], nachkauf=m["nachkauf"], scores={"korb": 50})
        for n in p["nachkaeufe"]:
            self.assertNotIn("korb", n["ziele"])

    def test_nachkauf_erhoeht_endwert(self):
        m = D.seed_modell()
        r = renditen(m)
        ohne = E.projektion(m, r, stress=m["stress"])["endwert"]
        mit = E.projektion(m, r, stress=m["stress"], nachkauf=m["nachkauf"], scores={"korb": 80})["endwert"]
        self.assertGreater(mit, ohne)

    def test_hebel_faellt_staerker(self):
        m = D.seed_modell()
        null = {i: 0.0 for i in E.gewichte(m)}
        p = E.projektion(m, null, stress=m["stress"])
        v2 = p["asset_verlauf"]["etf_ndx2x"]
        v1 = p["asset_verlauf"]["etf_ndx"]
        self.assertLess(min(v2) / v2[0], min(v1) / v1[0])
        self.assertEqual(p["asset_verlauf"]["reserve"][-1], 1500)


class Szenarien(unittest.TestCase):
    def test_reihenfolge(self):
        m = D.seed_modell()
        s = E.szenario_vergleich(m)
        self.assertLess(s["bear"]["endwert"], s["base"]["endwert"])
        self.assertLess(s["base"]["endwert"], s["bull"]["endwert"])
        for v in s.values():
            self.assertAlmostEqual(sum(v["anteil_endwert"].values()), 1.0, places=6)
            self.assertLess(v["max_verlust_stress"], 0)

    def test_ziel(self):
        m = D.seed_modell()
        z = E.zusammenfassung(m, renditen(m))
        self.assertAlmostEqual(z["erforderliche_cagr"], 0.4614, places=4)
        self.assertEqual(z["ziel_erreicht"], z["endwert"] >= 100000)
        self.assertAlmostEqual(z["differenz"], z["endwert"] - 100000)

    def test_max_verlust(self):
        m = D.seed_modell()
        v = E.max_modell_verlust(m)
        self.assertLess(v, 0)
        self.assertGreater(v, -100)


class Sensitivitaet(unittest.TestCase):
    def test_tornado(self):
        m = D.seed_modell()
        basis, z = E.tornado(m, renditen(m))
        self.assertTrue(all(a["spanne"] >= b["spanne"] for a, b in zip(z, z[1:])))
        for zeile in z:
            self.assertLess(zeile["tief"], basis)
            self.assertGreater(zeile["hoch"], basis)

    def test_gruppe(self):
        m = D.seed_modell()
        g = E.gruppen_sensitivitaet(m, renditen(m), ["wf_ff", "wf_hig", "wf_gwc"], [0.4, 0.3, 0.2])
        self.assertGreater(g[0][1], g[1][1])
        self.assertGreater(g[1][1], g[2][1])


class Confidence(unittest.TestCase):
    def test_werte(self):
        self.assertEqual(E.confidence_score(1, "index"), 22)
        self.assertEqual(E.confidence_score(10, "index"), 92)
        self.assertEqual(E.confidence_score(None, "wikifolio"), 10)
        self.assertEqual(E.confidence_score(None, "cash"), 100)
        self.assertEqual(E.confidence_adjusted_return(0.5, 22), 0.11)

    def test_bias(self):
        m = D.seed_modell()
        r = E.alle_renditen(m)
        korb = next(a for a in m["assets"] if a["id"] == "korb")
        self.assertTrue(any("Winner Bias" in h for h in E.bias_hinweise(korb, r["korb"], 60)))
        hebel = next(a for a in m["assets"] if a["id"] == "etf_ndx2x")
        self.assertTrue(any("gehebelt" in h for h in E.bias_hinweise(hebel, r["etf_ndx2x"], 50)))


class Fundamental(unittest.TestCase):
    def test_score_grenzen(self):
        gut = {"g_ums": 30, "g_eps": 40, "g_fcf": 40, "om": 45, "fm": 40, "roic": 50, "om_std": 0.5,
               "nde": -1, "zinsd": 30, "fkgv": 10, "peg": 0.5, "ev_fcf": 10, "ev_ebitda": 6, "gm": 80,
               "vola": 10, "dd": -10}
        s = E.fundamental_score(gut, manuell={"moat": 10, "risiko": 10})
        self.assertEqual(s["gesamt"], 100.0)
        schlecht = {k: (-100 if k not in ("om_std", "nde", "fkgv", "peg", "ev_fcf", "ev_ebitda", "vola")
                        else 1000) for k in gut}
        self.assertEqual(E.fundamental_score(schlecht, manuell={"moat": 0, "risiko": 0})["gesamt"], 0.0)

    def test_zu_wenig_daten(self):
        self.assertIsNone(E.fundamental_score({"om": 30})["gesamt"])

    def test_gewichte_aenderbar(self):
        import copy
        k = {"g_ums": 25, "g_eps": 30, "g_fcf": 30, "om": 5, "fm": 3, "roic": 5, "om_std": 8,
             "nde": 3.5, "zinsd": 2, "fkgv": 45, "peg": 3, "ev_fcf": 70, "ev_ebitda": 40, "gm": 20, "vola": 60,
             "dd": -75}
        regeln = copy.deepcopy(D.BEWERTUNGSREGELN)
        for key in regeln:
            regeln[key]["gewicht"] = 100 if key == "wachstum" else 0
        self.assertEqual(E.fundamental_score(k, regeln)["gesamt"], 100.0)

    def test_korb_methoden(self):
        korb = D.SEED_KORB
        for methode in E.KORB_METHODEN:
            g = E.korb_gewichte(korb, methode, scores={k["id"]: 60 for k in korb})
            self.assertAlmostEqual(sum(g.values()), 100.0, places=1)
        self.assertEqual(E.korb_gewichte(korb, "manual")["nvda"], 14.0)
        self.assertEqual(E.korb_gewichte(korb, "equal")["anet"], 10.0)
        # ohne Daten -> bisherige Gewichte
        self.assertEqual(E.korb_gewichte(korb, "growth")["nvda"], 14.0)

    def test_korb_fundamentalrendite(self):
        k = {x["id"]: {"fcfy": 3.0, "g_ref": 12.0} for x in D.SEED_KORB}
        r, je = E.korb_fundamental_rendite(D.SEED_KORB, k)
        self.assertAlmostEqual(r, 0.15)
        self.assertIsNone(E.korb_fundamental_rendite(D.SEED_KORB, {})[0])


class Risiko(unittest.TestCase):
    def test_kennzahlen(self):
        m = D.seed_modell()
        r = renditen(m)
        conf = E.confidence_fuer(m)
        k = E.risiko_kennzahlen(m, r, conf)
        self.assertAlmostEqual(k["wikifolio_anteil"], 30.0)
        self.assertAlmostEqual(k["hebel_anteil"], 5.0)
        self.assertAlmostEqual(k["cash_quote"], 10.0)
        self.assertAlmostEqual(k["semi_bekannt"], 5.0 + 20.0 * 0.47)
        self.assertGreater(k["effektive_positionen"], 1)

    def test_exposure(self):
        m = D.seed_modell()
        m["holdings"] = {"etf_ndx": {"Nvidia": 8.0}}
        x = E.effektive_exposure(m)
        nv = x["firmen"]["Nvidia"]
        self.assertAlmostEqual(nv["direkt"], 20 * 0.14)
        self.assertAlmostEqual(nv["indirekt"], 7.5 * 0.08)
        self.assertAlmostEqual(nv["effektiv"], 2.8 + 0.6)


class Optimizer(unittest.TestCase):
    def pruefe_grenzen(self, m, gew):
        self.assertAlmostEqual(sum(gew.values()), 100.0, places=3)
        a = {x["id"]: x for x in E.aktive_assets(m)}
        for i, g in gew.items():
            self.assertGreaterEqual(g, -1e-6)
            if a[i]["category"] != "cash":
                self.assertLessEqual(g, 20.0 + 1e-6)
        grp = lambda kats: sum(g for i, g in gew.items() if a[i]["category"] in kats)
        self.assertLessEqual(grp(["wikifolio"]), 40 + 1e-6)
        self.assertLessEqual(grp(["single_stock", "stock_basket"]), 20 + 1e-6)
        self.assertLessEqual(grp(["leveraged_etf"]), 10 + 1e-6)
        self.assertGreaterEqual(grp(["cash"]), 5 - 1e-6)
        semi = sum(g * (E.asset_merkmal(a[i], m, "semi") or 0) for i, g in gew.items())
        self.assertLessEqual(semi, 20 + 1e-6)

    def test_simplex_einfach(self):
        x, z = E._simplex([3, 2], [[1, 1], [1, 3]], [4, 6], [], [])
        self.assertAlmostEqual(z, 12)
        x, z = E._simplex([1, 1], [[1, 0]], [1], [[1, 1]], [3])       # Gleichung
        self.assertAlmostEqual(z, 3)
        x, _ = E._simplex([1], [[-1]], [-5], [[1]], [1])               # x>=5 und x=1 -> unzulaessig
        self.assertIsNone(x)

    def test_ziel_erreichbar(self):
        m = D.seed_modell()
        m["rahmen"]["zielvermoegen"] = 60000
        r = renditen(m)
        o = E.optimiere(m, r, E.confidence_fuer(m))
        self.pruefe_grenzen(m, o["gewichte"])
        self.assertTrue(o["erreichbar"])
        self.assertGreaterEqual(o["endwert"], 60000 - 1)

    def test_nicht_erreichbar(self):
        m = D.seed_modell()                  # 100k mit Seed-Annahmen unter den Grenzen nicht erreichbar
        r = renditen(m)
        o = E.optimiere(m, r, E.confidence_fuer(m))
        self.assertFalse(o["erreichbar"])
        self.pruefe_grenzen(m, o["gewichte"])
        self.assertAlmostEqual(o["endwert"], o["max_endwert"], places=2)

    def test_konzentration_minimiert(self):
        m = D.seed_modell()
        m["rahmen"]["zielvermoegen"] = 20000        # leicht erreichbar -> breit streuen
        r = renditen(m)
        o = E.optimiere(m, r, E.confidence_fuer(m))
        self.pruefe_grenzen(m, o["gewichte"])
        nicht_cash = [g for i, g in o["gewichte"].items() if i != "reserve"]
        self.assertLess(max(nicht_cash), 20.0)

    def test_widerspruch(self):
        m = D.seed_modell()
        m["grenzen"]["einzelasset_max"] = 5.0
        m["grenzen"]["gruppen"].append({"titel": "x", "kategorien": ["cash"], "max": 5.0})
        o = E.optimiere(m, renditen(m), E.confidence_fuer(m))
        self.assertIn("fehler", o)


class GewichtungZiel(unittest.TestCase):
    def test_trifft_ziel(self):
        m = D.seed_modell()
        r = renditen(m)
        o = E.gewichtung_fuer_ziel(m, r)
        self.assertTrue(o["erreichbar"])
        self.assertAlmostEqual(sum(o["gewichte"].values()), 100.0, places=6)
        self.assertAlmostEqual(o["gewichte"]["reserve"], 10.0)            # fixiert
        for a in m["assets"]:
            a["targetWeight"] = o["gewichte"].get(a["id"], 0.0)
        self.assertGreaterEqual(E.projektion(m, r)["endwert"], 100000 - 1e-6)
        self.assertLess(E.projektion(m, r)["endwert"], 100000 * 1.0001)

    def test_nach_unten_und_mit_rebalancing(self):
        m = D.seed_modell()
        m["rahmen"]["zielvermoegen"] = 40000
        r = renditen(m)
        o = E.gewichtung_fuer_ziel(m, r, rebalancing={"art": "jaehrlich"})
        self.assertAlmostEqual(o["endwert"], 40000, delta=5)
        self.assertLess(o["gewichte"]["wf_ff"], 10.0)

    def test_fixiert_und_unerreichbar(self):
        m = D.seed_modell()
        for a in m["assets"]:
            if a["category"] == "wikifolio":
                a["fixiert"] = True
        o = E.gewichtung_fuer_ziel(m, renditen(m))
        self.assertFalse(o["erreichbar"])
        self.assertLess(o["max_endwert"], 100000)

    def test_grenzen_meldung(self):
        m = D.seed_modell()
        self.assertEqual(E.grenzen_verletzungen(m), [])
        o = E.gewichtung_fuer_ziel(m, renditen(m))
        self.assertTrue(any("Wikifolios" in t for t in E.grenzen_verletzungen(m, o["gewichte"])))


class Katalog(unittest.TestCase):
    def test_stammdaten(self):
        self.assertEqual(len(D.KATALOG), 72)
        self.assertEqual(len({k["wkn"] for k in D.KATALOG}), 72)
        for k in D.KATALOG:
            self.assertIn(k["category"], D.KATEGORIEN)
            self.assertIn(k["typ"], D.KATALOG_TYPEN)
            if k["isin"]:
                self.assertEqual(len(k["isin"]), 12)
            if k["typ"] == "wikifolio":
                self.assertTrue(k["wkn"].startswith("LS9"))
            self.assertIsNone(k["ter"])              # nichts erfunden
        self.assertEqual(sum(k["hebel"] > 1 for k in D.KATALOG), 2)

    def test_risiko_score(self):
        self.assertIsNone(E.risiko_score(None, None))
        self.assertEqual(E.risiko_score(0.6, -80, 3.0, ""), 100)
        self.assertEqual(E.risiko_score(0.0, 0.0, 1.0, ""), 0)
        self.assertGreater(E.risiko_score(0.3, -40, 1.0, "Extreme Leveraged"), E.risiko_score(0.3, -40, 1.0, "Equity"))

    def test_vorschlag_gedaempft(self):
        kurz = E.vorschlag_renditen({"gesamt_cagr": 1.0, "jahre": 1.0}, "wikifolio")
        lang = E.vorschlag_renditen({"historical5Y": 0.12, "jahre": 10.0}, "index")
        self.assertLess(kurz["base"], 0.35)                 # 100 % bei 1 J. Historie stark gedaempft
        self.assertAlmostEqual(lang["base"], 0.92 * 0.12 + 0.08 * 0.08, places=3)
        self.assertLess(kurz["bear"], kurz["base"])
        self.assertGreater(kurz["bull"], kurz["base"])
        neg = E.vorschlag_renditen({"historical5Y": -0.2, "jahre": 10.0}, "index")
        self.assertLess(neg["bear"], neg["base"])
        self.assertIsNone(E.vorschlag_renditen({"jahre": 0.5}, "index"))

    def test_treiber(self):
        leveraged_welt = next(k for k in D.KATALOG if k["wkn"] == "DBX2SC")
        self.assertEqual(E.treiber({"category": "leveraged_etf", "id": "x", "treiber": leveraged_welt["treiber"]}),
                         "Welt-Aktien")
        self.assertEqual(E.treiber({"category": "wikifolio", "id": "wf"}), "wf")


class Entnahme(unittest.TestCase):
    def test_ohne_rendite(self):
        p = E.entnahmeplan(100000, 0.0, 1000, jahre=30)
        self.assertEqual(p["dauer_monate"], 100)
        self.assertAlmostEqual(p["summe_netto"], 100000, places=4)
        self.assertEqual(p["restwert"], 0.0)

    def test_annuitaet(self):
        r = 1.05 ** (1 / 12) - 1
        annuitaet = 100000 * r / (1 - (1 + r) ** -360)
        self.assertAlmostEqual(E.entnahme_fuer(100000, 0.05, jahre=30), annuitaet, delta=1)
        self.assertAlmostEqual(E.entnahme_fuer(100000, 0.05, jahre=30, ziel_restwert=100000), 100000 * r, delta=1)

    def test_dauerhaft(self):
        p = E.entnahmeplan(100000, 0.06, 300, jahre=30)
        self.assertTrue(p["reicht_dauerhaft"])
        self.assertGreater(p["restwert"], 100000)

    def test_dynamik_und_steuer_kuerzen(self):
        basis = E.entnahmeplan(100000, 0.05, 400, jahre=30)["restwert"]
        dyn = E.entnahmeplan(100000, 0.05, 400, jahre=30, dynamik_pa=0.02)
        st_ = E.entnahmeplan(100000, 0.05, 400, jahre=30, einstand=30000, steuersatz=0.26375, freibetrag=1000)
        self.assertLess(dyn["restwert"], basis)
        self.assertLess(st_["restwert"], basis)
        self.assertGreater(st_["summe_steuer"], 0)
        self.assertAlmostEqual(st_["summe_brutto"] - st_["summe_steuer"], st_["summe_netto"], places=4)
        # Freibetrag deckt kleine Gewinne: keine Steuer
        klein = E.entnahmeplan(100000, 0.0, 500, jahre=2, max_jahre=2, einstand=99000, steuersatz=0.26375,
                               freibetrag=1000)
        self.assertEqual(klein["summe_steuer"], 0.0)


if __name__ == "__main__":
    unittest.main()
