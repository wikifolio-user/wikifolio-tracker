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
        m["rahmen"]["regeln"]["aktiv"] = False
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
        m["rahmen"]["regeln"]["aktiv"] = False
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
        self.assertAlmostEqual(E.entnahme_fuer(100000, 0.05, jahre=30), annuitaet, delta=0.01)
        self.assertAlmostEqual(E.entnahme_fuer(100000, 0.05, jahre=30, ziel_restwert=100000), 100000 * r, delta=0.01)

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


class Wunschrendite(unittest.TestCase):
    def test_ziel_und_gewichtung(self):
        m = D.seed_modell()
        r = renditen(m)
        ziel = E.ziel_aus_rendite(m, 0.35)
        self.assertAlmostEqual(ziel, 15000 * 1.35 ** 5, places=4)
        o = E.gewichtung_fuer_ziel(m, r, ziel=ziel)
        for a in m["assets"]:
            a["targetWeight"] = o["gewichte"].get(a["id"], 0.0)
        self.assertAlmostEqual(E.required_cagr(15000, E.projektion(m, r)["endwert"], 5), 0.35, places=5)

    def test_optimizer_mit_ziel(self):
        m = D.seed_modell()
        r = renditen(m)
        o = E.optimiere(m, r, E.confidence_fuer(m), ziel=E.ziel_aus_rendite(m, 0.25))
        self.assertTrue(o["erreichbar"])
        self.assertFalse(E.optimiere(m, r, E.confidence_fuer(m), ziel=E.ziel_aus_rendite(m, 0.40))["erreichbar"])


class IstWerte(unittest.TestCase):
    def test_wikifolios_nutzen_historie(self):
        m = D.seed_modell()
        self.assertEqual(next(a for a in m["assets"] if a["id"] == "wf_ff")["renditequelle"], "historisch")
        self.assertEqual(next(a for a in m["assets"] if a["id"] == "etf_ndx")["renditequelle"], "annahme")
        hist = {"wf_ff": {"historical3Y": 0.31, "historical1Y": 0.9, "stand": "2026-09-29"},
                "wf_hig": {"gesamt_cagr": 0.22}, "wf_gwc": {"historical1Y": 0.05}}
        for methode in ("manual", "historical5Y", "historical10Y", "fundamentalModel"):
            r = E.alle_renditen(m, hist, methode=methode)
            self.assertAlmostEqual(r["wf_ff"]["brutto"], 0.31)          # 3 J. vor 1 J.
            self.assertAlmostEqual(r["wf_hig"]["brutto"], 0.22)
            self.assertAlmostEqual(r["wf_gwc"]["brutto"], 0.05)
            self.assertEqual(r["wf_ff"]["herkunft"]["sourceType"], "historisch")
        bear = E.alle_renditen(m, hist, methode="szenario", szenario="bear")["wf_ff"]["brutto"]
        bull = E.alle_renditen(m, hist, methode="szenario", szenario="bull")["wf_ff"]["brutto"]
        self.assertLess(bear, 0.31)
        self.assertGreater(bull, 0.31)

    def test_fallback_und_abwahl(self):
        m = D.seed_modell()
        r = E.alle_renditen(m, {})
        self.assertEqual(r["wf_ff"]["brutto"], 0.50)                  # keine Historie -> Annahme mit Hinweis
        self.assertIn("Kurshistorie", r["wf_ff"]["hinweis"])
        next(a for a in m["assets"] if a["id"] == "wf_ff")["renditequelle"] = "annahme"
        r = E.alle_renditen(m, {"wf_ff": {"historical5Y": 0.2}})
        self.assertEqual(r["wf_ff"]["brutto"], 0.50)

    def test_negative_basis_szenario(self):
        regel = D.SZENARIO_REGEL
        self.assertLess(E._szenario_um(-0.1, "bear", regel), -0.1)
        self.assertGreater(E._szenario_um(-0.1, "bull", regel), -0.1)


class AnnahmenAusHistorie(unittest.TestCase):
    def test_auto_und_eigene(self):
        m = D.seed_modell()
        hist = {"etf_allworld": {"historical5Y": 0.09, "stand": "2026-09-29"}, "etf_ndx": {"historical3Y": 0.2},
                "korb": {"historical5Y": 0.4}, "etf_gold": {"historical1Y": 0.3}}
        E.setze_annahme(m, "etf_ndx", "manualScenario", 0.12)           # eigene Eingabe -> bleibt
        n = E.annahmen_aus_historie(m, hist)
        self.assertEqual(E.annahme(m, "etf_allworld", "manualScenario")["value"], 0.09)
        self.assertEqual(E.annahme(m, "etf_ndx", "manualScenario")["value"], 0.12)
        self.assertEqual(E.annahme(m, "korb", "manualScenario")["value"], 0.4)
        self.assertEqual(E.annahme(m, "etf_gold", "manualScenario")["value"], 0.3)   # vorher leer
        self.assertEqual(E.annahme(m, "reserve", "manualScenario")["value"], 0.0)     # Cash unveraendert
        self.assertEqual(n, 5)       # 3 aus Historie + 2 leere Seed-Werte mit Kategorie-Standard
        self.assertEqual(E.annahmen_aus_historie(m, hist), 0)                          # stabil
        E.annahmen_aus_historie(m, hist, alle=True)
        self.assertEqual(E.annahme(m, "etf_ndx", "manualScenario")["value"], 0.2)
        self.assertTrue(E.annahme(m, "etf_ndx", "manualScenario")["auto"])

    def test_ohne_historie_bleibt_startwert(self):
        m = D.seed_modell()
        E.annahmen_aus_historie(m, {})
        self.assertEqual(E.annahme(m, "etf_allworld", "manualScenario")["value"], 0.1108)


class NachRendite(unittest.TestCase):
    def test_proportional(self):
        m = D.seed_modell()
        m["rahmen"]["regeln"]["aktiv"] = False                            # reine Proportionalitaet pruefen
        for a in m["assets"]:
            if a["id"] == "etf_gold":
                a["enabled"], a["targetWeight"] = True, 0.0             # neu, 0 % -> wird beruecksichtigt
        r = renditen(m)
        r["etf_gold"] = 0.30
        r["etf_momentum"] = -0.05                                         # negativ -> 0 %
        g = E.gewichte_nach_rendite(m, r)["gewichte"]
        self.assertAlmostEqual(sum(g.values()), 100.0, places=6)
        self.assertAlmostEqual(g["reserve"], 10.0)                         # fixiert
        self.assertEqual(g["etf_momentum"], 0.0)
        self.assertAlmostEqual(g["etf_gold"] / g["korb"], 0.30 / 0.25, places=6)
        self.assertAlmostEqual(g["wf_ff"] / g["etf_allworld"], 0.50 / 0.1108, places=6)

    def test_nichts_zu_verteilen(self):
        m = D.seed_modell()
        self.assertIn("fehler", E.gewichte_nach_rendite(m, {i: 0.0 for i in E.gewichte(m)}))


class RenditeGewichtung(unittest.TestCase):
    def test_trifft_rendite(self):
        m = D.seed_modell()
        m["rahmen"]["regeln"]["aktiv"] = False
        r = renditen(m)
        for ziel in (0.10, 0.25, 0.30):
            o = E.gewichtung_fuer_rendite(m, r, ziel)
            self.assertTrue(o["erreichbar"])
            self.assertAlmostEqual(o["rendite"], ziel, places=6)
            self.assertAlmostEqual(sum(o["gewichte"].values()), 100.0, places=6)
            self.assertAlmostEqual(o["gewichte"]["reserve"], 10.0)

    def test_nicht_erreichbar_und_gleichverteilung(self):
        m = D.seed_modell()
        r = renditen(m)
        o = E.gewichtung_fuer_rendite(m, r, 0.9)
        self.assertFalse(o["erreichbar"])
        self.assertAlmostEqual(o["rendite"], o["max"], places=4)
        frei = [i for i in E.gewichte(m) if i != "reserve"]
        mittel = 0.1 * r["reserve"] + 0.9 * sum(r[i] for i in frei) / len(frei)
        g = E.gewichtung_fuer_rendite(m, r, mittel)["gewichte"]
        for i in frei:
            self.assertAlmostEqual(g[i], 90.0 / len(frei), places=3)       # ausgeglichen = gleich verteilt

    def test_ohne_aufbau(self):
        m = D.seed_modell()
        m["rahmen"]["horizont_jahre"] = 0
        r = renditen(m)
        z = E.zusammenfassung(m, r)
        self.assertEqual(z["endwert"], 15000)
        self.assertIsNone(z["modell_cagr"])
        self.assertIn("fehler", E.gewichtung_fuer_ziel(m, r))
        m["rahmen"]["horizont_jahre"] = 5
        m["rahmen"]["zielvermoegen"] = 0
        self.assertIn("fehler", E.gewichtung_fuer_ziel(m, r))


class LueckenFuellen(unittest.TestCase):
    def test_junge_historie_keine_gemessene_jahresrendite(self):   # gemessene p.a.-Werte erst ab 1 Jahr
        self.assertEqual(E.ist_rendite({"jahre": 0.5, "seit_start": 0.4}), (None, None))
        self.assertEqual(E.ist_rendite({"jahre": 0.02, "seit_start": 0.1}), (None, None))
        self.assertTrue(E.kurze_historie({"jahre": 0.5, "seit_start": 0.4}))
        self.assertFalse(E.kurze_historie({"jahre": 1.5, "gesamt_cagr": 0.2}))
        self.assertFalse(E.kurze_historie({}))

    def test_ohne_kursdaten_standardwert(self):
        m = D.seed_modell()
        aid = "neu_x"
        m["assets"].append(D._asset(aid, "Neu", "wikifolio", 0.0))
        E.setze_annahme(m, aid, "manualScenario", None, auto=True)
        E.annahmen_aus_historie(m, {})
        a = E.annahme(m, aid, "manualScenario")
        self.assertAlmostEqual(a["value"], E.STANDARD_RENDITE["wikifolio"])
        self.assertTrue(a["auto"])
        # unter 1 Monat Kursdaten: weiter Kategorie-Standard (gedaempft: 0,1*8 % + 0,9*8 % = 8 %)
        E.annahmen_aus_historie(m, {aid: {"jahre": 0.04, "seit_start": 0.3}})
        self.assertAlmostEqual(E.annahme(m, aid, "manualScenario")["value"], 0.08)
        self.assertEqual(E.annahme(m, aid, "manualScenario")["source"], "zu kurze Historie – Kategorie-Standard")
        # 6 Monate +30 %: hochgerechnet 1,3^2 - 1 = 69 % p.a.
        E.annahmen_aus_historie(m, {aid: {"jahre": 0.5, "seit_start": 0.3}})
        self.assertAlmostEqual(E.annahme(m, aid, "manualScenario")["value"], 0.69, places=12)
        self.assertEqual(E.annahme(m, aid, "manualScenario")["source"],
                         "hochgerechnet aus 6 Mon. (Ø Monatsrendite)")
        # sobald >= 1 Jahr Kursdaten da sind, wird der Standard ersetzt
        E.annahmen_aus_historie(m, {aid: {"jahre": 1.5, "gesamt_cagr": 0.3}})
        self.assertAlmostEqual(E.annahme(m, aid, "manualScenario")["value"], 0.3)
        for x in m["assets"]:
            if x["category"] != "cash":
                self.assertIsNotNone(E.annahme(m, x["id"], "manualScenario")["value"], x["id"])


class ZielvermoegenAuto(unittest.TestCase):
    def test_trifft_ziel_und_unerreichbar(self):
        m = D.seed_modell()
        r = renditen(m)
        m["rahmen"]["zielvermoegen"] = 60000
        o = E.gewichtung_fuer_zielvermoegen(m, r, m["rebalancing"])
        self.assertTrue(o["erreichbar"])
        self.assertAlmostEqual(o["endwert"], 60000, delta=5)
        self.assertAlmostEqual(o["benoetigt"], E.required_cagr(15000, 60000, 5))
        m["rahmen"]["zielvermoegen"] = 10 ** 7
        self.assertFalse(E.gewichtung_fuer_zielvermoegen(m, r, m["rebalancing"])["erreichbar"])
        m["rahmen"]["zielvermoegen"] = 0
        self.assertIn("fehler", E.gewichtung_fuer_zielvermoegen(m, r))


class ZielNachEntnahme(unittest.TestCase):
    def test_restwert_genau(self):
        r = E.rendite_fuer_restwert(300000, 3500, 1_000_000, jahre=10)
        self.assertAlmostEqual(E.entnahmeplan(300000, r, 3500, jahre=10)["restwert"], 1_000_000, delta=1)
        self.assertIsNone(E.rendite_fuer_restwert(300000, 3500, 0, jahre=10))


class Kaufplan(unittest.TestCase):
    def test_ganze_stuecke_und_cash(self):
        pos = [{"id": "a", "name": "A", "anteil": 0.5, "kurs": 330.0},
               {"id": "b", "name": "B", "anteil": 0.4, "kurs": 47.3},
               {"id": "r", "name": "Reserve", "anteil": 0.1, "cash": True},
               {"id": "x", "name": "X", "anteil": 0.0, "kurs": None}]
        o = E.kaufplan(pos, 10000)
        z = {r["id"]: r for r in o["zeilen"]}
        for r in z.values():
            self.assertEqual(r["stueck"], int(r["stueck"]))
        self.assertAlmostEqual(o["investiert"] + o["cash_soll"] + o["rest"], 10000, places=6)
        self.assertEqual(z["r"]["ist"], 1000)
        self.assertLessEqual(abs(z["b"]["abweichung"]), 47.3 / 2 + 1e-9)

    def test_bruchstuecke(self):
        o = E.kaufplan([{"id": "a", "name": "A", "anteil": 1.0, "kurs": 333.0}], 1000, bruchstuecke=True)
        self.assertAlmostEqual(o["zeilen"][0]["ist"], 1000, delta=0.04)


class Kredit(unittest.TestCase):
    def test_lohnt_ab_kreditkosten(self):
        be = E.kredit_break_even(20000, 0.065, 5, "annuitaet", "einkommen", 10)
        self.assertAlmostEqual(be, (1 + 0.065 / 12) ** 12 - 1, places=3)      # effektiver Kreditzins
        self.assertLess(E.kredit_simulation(20000, 0.065, 5, "annuitaet", "einkommen", 0.03, 10)["vorteil"], 0)
        self.assertGreater(E.kredit_simulation(20000, 0.065, 5, "annuitaet", "einkommen", 0.10, 10)["vorteil"], 0)

    def test_schuld_getilgt_und_zinsen(self):
        o = E.kredit_simulation(10000, 0.06, 2, "annuitaet", "einkommen", 0.05, 2)
        self.assertAlmostEqual(o["schuld"], 0, places=6)
        self.assertAlmostEqual(o["eigene"], o["rate"] * 24, places=4)
        self.assertAlmostEqual(o["eigene"] - 10000, o["zinsen"], places=4)
        e = E.kredit_simulation(10000, 0.06, 2, "endfaellig", "investment", 0.0, 2)
        self.assertAlmostEqual(e["netto_mit"], 10000 - 10000 - 1200, delta=1)  # ohne Rendite: Zinsen = Verlust


class ParalleleEntnahme(unittest.TestCase):
    def test_entnahme_im_aufbau(self):
        m = D.seed_modell()
        r = renditen(m)
        ohne = E.zusammenfassung(m, r)
        m["rahmen"]["entnahme_parallel"] = {"monatlich": 100.0, "dynamik": 0.0, "monate": 60}
        mit = E.zusammenfassung(m, r)
        self.assertLess(mit["endwert"], ohne["endwert"])
        self.assertAlmostEqual(mit["projektion"]["entnommen"], 6000.0, places=6)
        self.assertAlmostEqual(mit["modell_cagr"], ohne["modell_cagr"], places=9)   # Portfoliorendite unveraendert
        self.assertGreater(mit["erforderliche_cagr"], ohne["erforderliche_cagr"])


class ManuelleRendite(unittest.TestCase):
    def _m(self):
        m = D.seed_modell()
        return m, {a["id"]: E.rendite_fuer(m, a)[0] or 0.0 for a in m["assets"]}

    def test_trifft_cagr(self):
        m, r = self._m()
        o = E.gewichtung_fuer_cagr(m, r, 0.15, m["rebalancing"])
        self.assertTrue(o["erreichbar"])
        for a in m["assets"]:
            if a["id"] in o["gewichte"]:
                a["targetWeight"] = o["gewichte"][a["id"]]
        self.assertAlmostEqual(E.zusammenfassung(m, r, rebalancing=m["rebalancing"])["modell_cagr"], 0.15, places=3)

    def test_unerreichbar_gibt_maximum(self):
        m, r = self._m()
        o = E.gewichtung_fuer_cagr(m, r, 5.0, m["rebalancing"])
        self.assertFalse(o["erreichbar"])
        self.assertAlmostEqual(o["rendite"], o["max"], places=6)


class EntnahmeStufen(unittest.TestCase):
    def test_betrag(self):
        st_ = [{"ab_jahr": 4, "monatlich": 500.0}]
        self.assertAlmostEqual(E.entnahme_betrag(1500, 0.02, 1, st_), 1500)
        self.assertAlmostEqual(E.entnahme_betrag(1500, 0.02, 36, st_), 1500 * 1.02 ** 2)
        self.assertAlmostEqual(E.entnahme_betrag(1500, 0.02, 37, st_), 500)
        self.assertAlmostEqual(E.entnahme_betrag(1500, 0.02, 49, st_), 510)

    def test_plan_und_offset(self):
        st_ = [{"ab_jahr": 3, "monatlich": 0.0}]
        p = E.entnahmeplan(100000, 0.0, 1000, jahre=5, max_jahre=5, stufen=st_)
        self.assertAlmostEqual(p["restwert"], 100000 - 24000)
        # 2 Jahre schon waehrend des Aufbaus entnommen -> sofort Stufe 3 (0 €)
        p2 = E.entnahmeplan(100000, 0.0, 1000, jahre=5, max_jahre=5, stufen=st_, start_monat=24)
        self.assertAlmostEqual(p2["restwert"], 100000)

    def test_projektion_parallel(self):
        ent = {"monatlich": 1000.0, "dynamik": 0.0, "monate": 36, "stufen": [{"ab_jahr": 2, "monatlich": 0.0}]}
        self.assertAlmostEqual(E.endwert_mit_fluessen(50000, 0.0, 3, 0.0, ent), 50000 - 12000)


class StrukturRegeln(unittest.TestCase):
    def _wiki(self, m, g):
        a = {x["id"]: x for x in m["assets"]}
        return sum(v for i, v in g.items() if a[i]["category"] == "wikifolio")

    def test_auto_gewichtung_haelt_regeln(self):
        m = D.seed_modell()
        r = renditen(m)
        for ziel in (0.10, 0.20, 0.9):
            o = E.gewichtung_fuer_rendite(m, r, ziel)
            self.assertLessEqual(self._wiki(m, o["gewichte"]), 35.0 + 1e-6)
            self.assertTrue(5.0 - 1e-6 <= o["gewichte"]["reserve"] <= 10.0 + 1e-6)
            self.assertAlmostEqual(sum(o["gewichte"].values()), 100.0, places=6)

    def test_regeln_anwenden(self):
        m = D.seed_modell()
        g = {a["id"]: 0.0 for a in E.aktive_assets(m)}
        wikis = [a["id"] for a in E.aktive_assets(m) if a["category"] == "wikifolio"]
        for i in wikis:
            g[i] = 100.0 / len(wikis)                  # 100 % Wikifolios, 0 % Reserve
        g2 = E.regeln_anwenden(m, g)
        self.assertAlmostEqual(self._wiki(m, g2), 35.0, places=6)
        self.assertAlmostEqual(g2["reserve"], 5.0, places=6)
        self.assertAlmostEqual(sum(g2.values()), 100.0, places=6)
        self.assertEqual(E.regeln_verletzungen(m, g2), [])
        self.assertTrue(E.regeln_verletzungen(m, g))

    def test_optimierer(self):
        m = D.seed_modell()
        o = E.optimiere(m, renditen(m), E.confidence_fuer(m))
        if o and not o.get("fehler"):
            self.assertLessEqual(self._wiki(m, o["gewichte"]), 35.0 + 1e-4)


class MindestensEinStueck(unittest.TestCase):
    def test_gewicht_ergibt_mindestens_ein_stueck(self):
        pos = [{"id": "a", "name": "Teuer", "anteil": 0.011, "kurs": 400.0},
               {"id": "b", "name": "ETF", "anteil": 0.80, "kurs": 100.0},
               {"id": "c", "name": "Reserve", "anteil": 0.189, "cash": True}]
        r = E.kaufplan(pos, 10000)
        z = {x["id"]: x for x in r["zeilen"]}
        self.assertEqual(z["a"]["stueck"], 1.0)
        self.assertAlmostEqual(z["c"]["ist"], 1600.0)        # Mehrbetrag aus der Reserve
        self.assertEqual(r["mindest"], ["Teuer"])
        self.assertAlmostEqual(r["investiert"] + r["cash_soll"], 10000.0)

    def test_korbaktien_ohne_mindeststueck(self):
        pos = [{"id": "k:x", "name": "X", "teil_von": "Korb", "anteil": 0.001, "kurs": 500.0},
               {"id": "c", "name": "Reserve", "anteil": 0.999, "cash": True}]
        r = E.kaufplan(pos, 10000)
        self.assertEqual(r["zeilen"][0]["stueck"], 0.0)


# ===========================================================================
# Audit-Fixes (PLAN-01 .. PLAN-09) - Referenzwerte unabhaengig gerechnet
# ===========================================================================
import math
import sys
import types


def _ui_laden():
    """planer_ui importieren; ohne Streamlit/Plotly (Testumgebung) mit Minimal-Attrappen."""
    try:
        import planer_ui as U
        return U
    except ImportError:
        pass

    class _Egal:
        def __getattr__(self, k):
            return _Egal()

        def __call__(self, *a, **k):
            if len(a) == 1 and callable(a[0]) and not k:
                return a[0]
            return _Egal()

    def _deko(*a, **k):
        if len(a) == 1 and callable(a[0]):
            return a[0]
        return lambda f: f

    def _modul(name, **attr):
        mod = types.ModuleType(name)
        mod.__dict__.update(attr)

        def _attr(n):
            if n.startswith("__"):
                raise AttributeError(n)
            return _Egal()
        mod.__getattr__ = _attr
        if name == "plotly":
            mod.__path__ = []
        return mod

    for name in ("streamlit", "plotly", "plotly.graph_objects"):
        if name not in sys.modules:
            try:
                __import__(name)
            except ImportError:
                sys.modules[name] = _modul(name, session_state={}, cache_data=_deko, cache_resource=_deko,
                                           fragment=_deko, column_config=_Egal(), Figure=_Egal)
    if not hasattr(sys.modules["plotly"], "graph_objects"):
        sys.modules["plotly"].graph_objects = sys.modules["plotly.graph_objects"]
    try:
        import planer_ui as U
        return U
    except Exception:            # pragma: no cover - UI nicht ladbar: UI-Tests werden uebersprungen
        return None


U = _ui_laden()


def _annuitaet(betrag, zins_pa, monate):
    """Unabhaengig: Annuitaet mit Monatszins zins_pa/12 (wie Bankformel)."""
    q = zins_pa / 12.0
    return betrag * q / (1 - (1 + q) ** -monate)


def _schleife(start, r_pa, monate, spar=0.0, raten=()):
    """Unabhaengige Monatsschleife: geometrischer Monatssatz (1+r)^(1/12)-1, erst
    Verzinsung, dann Sparrate, dann Kreditraten (von, bis, betrag), nie unter 0."""
    rm = (1 + r_pa) ** (1 / 12) - 1
    v = float(start)
    for k in range(1, monate + 1):
        v = v * (1 + rm) + spar
        for von, bis, b in raten:
            if von <= k <= bis:
                v = max(v - b, 0.0)
    return v


def _gleiche_renditen(m, r):
    return {a["id"]: r for a in E.aktive_assets(m)}


class KreditFormeln(unittest.TestCase):
    def test_kredit_rate(self):
        self.assertAlmostEqual(E.kredit_rate(50000, 0.06, 5), 966.6401, places=4)
        self.assertAlmostEqual(E.kredit_rate(50000, 0.06, 5), _annuitaet(50000, 0.06, 60), places=8)

    def test_restschuld_nach_24_monaten(self):
        rate = E.kredit_rate(50000, 0.06, 5)
        s = 50000.0
        for _ in range(24):                    # unabhaengige Tilgungsschleife
            s = s * (1 + 0.06 / 12) - rate
        self.assertAlmostEqual(s, 31774.44, places=2)
        self.assertAlmostEqual(E.kredit_restschuld(50000, rate, 0.06, 24), s, places=6)


class StartkapitalNull(unittest.TestCase):        # PLAN-01
    def _m(self):
        m = D.seed_modell()
        m["rahmen"]["startkapital"] = 0.0
        m["rahmen"]["sparrate_monat"] = 500.0
        return m

    def test_projektion_gleich_future_value(self):
        m = self._m()
        r = 0.07
        p = E.projektion(m, _gleiche_renditen(m, r))
        n = int(m["rahmen"]["horizont_jahre"]) * 12
        rm = (1 + r) ** (1 / 12) - 1
        geschlossen = 500 * ((1 + rm) ** n - 1) / rm          # Rentenendwert, Zahlung am Monatsende
        self.assertAlmostEqual(p["endwert"], geschlossen, places=6)
        self.assertAlmostEqual(p["endwert"], E.future_value(0, r, m["rahmen"]["horizont_jahre"], 500), places=6)
        self.assertEqual(p["max_verlust_pfad"], 0.0)

    def test_max_verlust_ab_null(self):
        self.assertAlmostEqual(E._max_verlust([0.0, 100.0, 50.0]), -50.0)
        self.assertEqual(E._max_verlust([0.0, 0.0]), 0.0)

    def test_engine_funktionen_ohne_fehler(self):
        m = self._m()
        r = renditen(m)
        o = E.optimiere(m, r, E.confidence_fuer(m))
        self.assertNotIn("fehler", o)
        # optimiere: Endwert = Summe Gewicht x Sparfaktor (unabhaengig, Sparrate 500)
        jahre = int(m["rahmen"]["horizont_jahre"])
        erw = sum(o["gewichte"][i] / 100.0 * 500 * sum(((1 + r[i]) ** (1 / 12)) ** (jahre * 12 - k)
                                                      for k in range(1, jahre * 12 + 1)) for i in o["gewichte"])
        self.assertAlmostEqual(o["endwert"], erw, delta=1e-6 * erw)
        s = E.szenario_vergleich(m)
        self.assertGreater(s["base"]["endwert"], 0)
        g = E.gewichtung_fuer_ziel(m, r, ziel=45000)
        self.assertTrue(g["erreichbar"])
        self.assertAlmostEqual(g["endwert"], 45000, delta=1)
        zv = E.gewichtung_fuer_zielvermoegen(dict(m, rahmen=dict(m["rahmen"], zielvermoegen=45000)), r)
        self.assertAlmostEqual(zv["endwert"], 45000, delta=5)
        c = E.gewichtung_fuer_cagr(m, r, 0.15)
        self.assertNotIn("fehler", c)
        self.assertTrue(c["erreichbar"])
        self.assertAlmostEqual(c["rendite"], 0.15, delta=1e-4)
        m15 = dict(m, rahmen=dict(m["rahmen"], startkapital=15000.0))      # Rendite unabhaengig vom Betrag
        self.assertAlmostEqual(E.gewichtung_fuer_cagr(m15, r, 0.15)["rendite"], c["rendite"], delta=1e-6)
        z = E.zusammenfassung(m, _gleiche_renditen(m, 0.07))
        self.assertAlmostEqual(z["modell_cagr"], 0.07, places=9)

    @unittest.skipIf(U is None, "planer_ui nicht ladbar")
    def test_ui_rechnung(self):
        U.st.session_state = {}
        m = self._m()
        R = U._rechne(m, {}, None)                  # Standard: Entnahme parallel - darf nicht abstuerzen
        self.assertGreaterEqual(R["zus"]["endwert"], 0)
        m["entnahme"]["aktiv"] = False
        m["rahmen"]["rendite_modus"] = "aus"
        R = U._rechne(m, {}, None)
        self.assertAlmostEqual(R["zus"]["endwert"], E.projektion(m, R["r_calc"], rebalancing=R["reb"])["endwert"])
        self.assertGreater(R["zus"]["endwert"], 0)


class KreditRatenMonatsgenau(unittest.TestCase):        # PLAN-02 / PLAN-09
    def test_projektion_kredit_raten(self):
        m = D.seed_modell()
        m["rahmen"].update(startkapital=65000.0, sparrate_monat=0.0, horizont_jahre=20)
        rate = round(_annuitaet(50000, 0.06, 60), 2)
        m["rahmen"]["kredit_raten"] = [(1, 60, rate)]
        r = 0.09972
        p = E.projektion(m, _gleiche_renditen(m, r))
        ref = _schleife(65000, r, 240, raten=[(1, 60, rate)])
        self.assertAlmostEqual(p["endwert"], ref, places=4)
        self.assertAlmostEqual(ref, 127306.89, delta=0.01)
        self.assertAlmostEqual(p["kredit_raten_gezahlt"], 60 * rate, places=6)
        self.assertEqual(p["fehlbetrag"], 0.0)
        # ohne Raten-Einfluss: Modellrendite bleibt die Rendite der Bausteine
        self.assertAlmostEqual(E.zusammenfassung(m, _gleiche_renditen(m, r))["modell_cagr"], r, places=9)

    def test_raten_nie_unter_null(self):
        m = D.seed_modell()
        m["rahmen"].update(startkapital=1000.0, sparrate_monat=0.0, horizont_jahre=1)
        m["rahmen"]["kredit_raten"] = [(1, 12, 500.0)]
        p = E.projektion(m, _gleiche_renditen(m, 0.0))
        self.assertEqual(p["endwert"], 0.0)
        self.assertTrue(all(v >= 0 for vs in p["asset_verlauf"].values() for v in vs))
        self.assertAlmostEqual(p["kredit_raten_gezahlt"], 1000.0)
        self.assertAlmostEqual(p["fehlbetrag"], 12 * 500.0 - 1000.0)

    def test_negative_sparrate_nie_unter_null(self):
        m = D.seed_modell()
        m["rahmen"].update(startkapital=1000.0, sparrate_monat=-300.0, horizont_jahre=1)
        p = E.projektion(m, _gleiche_renditen(m, 0.0))
        self.assertEqual(p["endwert"], 0.0)
        self.assertTrue(all(v >= 0 for v in p["endwerte_asset"].values()))
        self.assertAlmostEqual(p["fehlbetrag"], 12 * 300.0 - 1000.0)

    def test_erforderliche_rendite_mit_raten(self):
        r = {"startkapital": 65000.0, "zielvermoegen": 127306.887, "horizont_jahre": 20, "sparrate_monat": 0.0,
             "kredit_raten": [(1, 60, round(_annuitaet(50000, 0.06, 60), 2))]}
        self.assertAlmostEqual(E.erforderliche_rendite_rahmen(r), 0.09972, delta=1e-7)

    @unittest.skipIf(U is None, "planer_ui nicht ladbar")
    def test_ui_kredit_rahmen_und_rechnung(self):
        U.st.session_state = {}
        m = D.seed_modell()
        m["rahmen"].update(rendite_modus="manuell", rendite_manuell=8.0, horizont_jahre=20)
        m["entnahme"]["aktiv"] = False
        rate = round(E.kredit_rate(50000, 0.06, 5), 2)
        m["kredit"] = {"kredite": [{"name": "K", "betrag": 50000.0, "rate": rate, "jahre": 5, "zins": 6.0}],
                       "aktiv": True, "aktiv_v2": True, "rate_aus": "investment", "rate_aus_v2": True}
        kr = U._kredit_rahmen(m)
        self.assertEqual(kr["raten"], [(1, 60, rate)])
        self.assertAlmostEqual(kr["restschuld"], 0.0, places=1)
        eff = U._mit_krediten(m)["rahmen"]
        self.assertEqual(eff["startkapital"], m["rahmen"]["startkapital"] + 50000.0)
        self.assertEqual(float(eff.get("sparrate_monat") or 0), float(m["rahmen"].get("sparrate_monat") or 0))
        R = U._rechne(m, {}, None)
        satz = next(iter(R["r_calc"].values()))
        ref = _schleife(eff["startkapital"], satz, 240, spar=float(eff.get("sparrate_monat") or 0),
                        raten=[(1, 60, rate)])
        self.assertAlmostEqual(R["zus"]["endwert"], ref, delta=0.01)
        if abs(satz - 0.09972) < 1e-9 and eff["startkapital"] == 65000 and not eff.get("sparrate_monat"):
            self.assertAlmostEqual(R["zus"]["endwert"], 127306.89, delta=0.01)      # Auditor-Referenz r9
        # Raten aus der Entnahme / dem Einkommen: kein zusaetzlicher Abzug
        m["kredit"]["rate_aus"] = "einkommen"
        self.assertEqual(U._kredit_rahmen(m)["raten"], [])


@unittest.skipIf(U is None, "planer_ui nicht ladbar")
class VorschlagEffektiv(unittest.TestCase):        # PLAN-03
    def _pruefe(self, m, ziel, grenzen):
        U.st.session_state = {}
        m["rahmen"]["zielvermoegen"] = ziel
        R = U._rechne(m, {}, None)
        v = U._vorschlag(m, R, "ziel", "vermoegen", None, grenzen)
        self.assertEqual(v["art"], "ok", v["text"])
        R2 = U._rechne(U._mit_gewichten(m, v["gewichte"]), {}, None)
        netto = R2["zus"]["endwert_netto"]
        self.assertGreaterEqual(netto, ziel - 0.01)
        self.assertLessEqual(netto, ziel + 1.0)
        self.assertTrue(R2["zus"]["ziel_erreicht"])

    def _basis(self):
        m = D.seed_modell()
        m["rahmen"]["rendite_modus"] = "aus"
        return m

    def test_mit_entnahme(self):
        m = self._basis()
        m["entnahme"]["monatlich"] = 200.0
        self.assertIsNotNone(U._entnahme_parallel(m))
        self._pruefe(m, 30000, False)
        self._pruefe(m, 33000, True)

    def test_mit_kredit(self):
        m = self._basis()
        m["entnahme"]["aktiv"] = False
        m["kredit"] = {"kredite": [{"name": "K", "betrag": 20000.0, "rate": 400.0, "jahre": 5, "zins": 6.0}],
                       "aktiv": True, "aktiv_v2": True, "rate_aus": "investment", "rate_aus_v2": True}
        self._pruefe(m, 60000, False)
        self._pruefe(m, 90000, True)

    def test_mit_restschuld(self):
        m = self._basis()
        m["entnahme"]["aktiv"] = False
        m["kredit"] = {"kredite": [{"name": "K", "betrag": 30000.0, "rate": 0.0, "jahre": 10, "zins": 5.0}],
                       "aktiv": True, "aktiv_v2": True, "rate_aus": "investment", "rate_aus_v2": True}
        self.assertAlmostEqual(U._kredit_rahmen(m)["restschuld"], 30000.0, places=6)   # nur Zinsen gezahlt
        self._pruefe(m, 50000, False)

    def test_unerreichbar_ehrlich(self):
        m = self._basis()
        m["entnahme"]["monatlich"] = 200.0
        m["rahmen"]["zielvermoegen"] = 10 ** 6
        U.st.session_state = {}
        R = U._rechne(m, {}, None)
        v = U._vorschlag(m, R, "ziel", "vermoegen", None, False)
        self.assertEqual(v["art"], "fehler")
        self.assertIn("nicht erreichbar", v["text"])


def _schleife_bausteine(start, gew_pct, renditen, monate, spar=0.0, entnahme=lambda k: 0.0, raten=()):
    """Unabhaengige Monatsschleife je Baustein (ohne Rebalancing): Wachstum je Baustein mit
    (1+r)^(1/12), Sparrate nach Zielgewicht, Entnahme und Kreditraten anteilig nach Wert,
    nie unter 0. -> Endwert"""
    s_ = sum(gew_pct.values())
    w = {i: g / s_ for i, g in gew_pct.items()}
    v = {i: start * w[i] for i in w}
    for k in range(1, monate + 1):
        for i in v:
            v[i] *= (1 + renditen[i]) ** (1 / 12)
            v[i] += spar * w[i]
        abzug = entnahme(k) + sum(b for von, bis, b in raten if von <= k <= bis)
        ges = sum(v.values())
        abzug = min(abzug, ges)
        if ges > 0:
            v = {i: max(x - abzug * x / ges, 0.0) for i, x in v.items()}
    return sum(v.values())


@unittest.skipIf(U is None, "planer_ui nicht ladbar")
class VorschlagStandardEntnahme(unittest.TestCase):        # PLAN-03 mit Standard-Entnahme (1.000 €/Monat, +2 % p.a.)
    def _basis(self):
        m = D.seed_modell()
        m["rahmen"].update(rendite_modus="aus", startkapital=200000.0)
        m["rebalancing"] = {"art": "keins"}
        self.assertEqual(m["entnahme"]["monatlich"], 1000.0)          # Standard des Ausgangsmodells
        self.assertEqual(m["entnahme"]["dynamik_pa"], 2.0)
        return m

    def _uebernehmen(self, m, ziel, grenzen):
        U.st.session_state = {}
        m["rahmen"]["zielvermoegen"] = ziel
        R = U._rechne(m, {}, None)
        v = U._vorschlag(m, R, "ziel", "vermoegen", None, grenzen)
        self.assertEqual(v["art"], "ok", v["text"])
        m2 = U._mit_gewichten(m, v["gewichte"])
        R2 = U._rechne(m2, {}, None)
        return m2, R2

    def _unabhaengig(self, m2, R2, raten=(), restschuld=0.0):
        n = int(m2["rahmen"]["horizont_jahre"]) * 12
        gew = {a["id"]: float(a["targetWeight"]) for a in E.aktive_assets(m2) if float(a["targetWeight"] or 0) > 0}
        start = float(m2["rahmen"]["startkapital"]) + sum(float(k["betrag"]) for k in
                                                          (m2.get("kredit") or {}).get("kredite", []) if raten)
        return _schleife_bausteine(start, gew, R2["r_calc"], n, entnahme=lambda k: 1000.0 * 1.02 ** ((k - 1) // 12),
                                   raten=raten) - restschuld

    def test_ohne_grenzen(self):
        m = self._basis()
        for ziel in (260000.0, 400000.0):
            m2, R2 = self._uebernehmen(m, ziel, False)
            self.assertAlmostEqual(R2["zus"]["endwert_netto"], ziel, delta=1.0)
            self.assertAlmostEqual(self._unabhaengig(m2, R2), ziel, delta=1.0)
            self.assertTrue(R2["zus"]["ziel_erreicht"])

    def test_mit_grenzen(self):
        m = self._basis()
        m2, R2 = self._uebernehmen(m, 700000.0, True)
        self.assertGreaterEqual(R2["zus"]["endwert_netto"], 700000.0 - 0.01)
        self.assertLessEqual(R2["zus"]["endwert_netto"], 700000.0 + 1.0)
        self.assertAlmostEqual(self._unabhaengig(m2, R2), R2["zus"]["endwert_netto"], delta=0.01)

    def test_mit_kredit_und_entnahme(self):
        m = self._basis()
        rate = round(_annuitaet(50000, 0.06, 60), 2)                     # 966,64 €
        m["kredit"] = {"kredite": [{"name": "K", "betrag": 50000.0, "rate": rate, "jahre": 5, "zins": 6.0}],
                       "aktiv": True, "aktiv_v2": True, "rate_aus": "investment", "rate_aus_v2": True}
        for ziel, grenzen in ((260000.0, False), (750000.0, True)):
            m2, R2 = self._uebernehmen(m, ziel, grenzen)
            self.assertGreaterEqual(R2["zus"]["endwert_netto"], ziel - 0.01)
            self.assertLessEqual(R2["zus"]["endwert_netto"], ziel + 1.0)
            # Laufzeit 5 J. = Aufbau 5 J. -> Restschuld 0; Raten Monat 1..60
            self.assertAlmostEqual(self._unabhaengig(m2, R2, raten=[(1, 60, rate)]), R2["zus"]["endwert_netto"],
                                   delta=0.05)

    def test_ziel_unter_minimum_ehrlich(self):
        m = self._basis()
        U.st.session_state = {}
        m["rahmen"]["zielvermoegen"] = 100000.0
        R = U._rechne(m, {}, None)
        v = U._vorschlag(m, R, "ziel", "vermoegen", None, False)
        self.assertEqual(v["art"], "fehler")
        self.assertIn("kleinsten", v["text"])
        v = U._vorschlag(m, R, "ziel", "vermoegen", None, True)
        self.assertEqual(v["art"], "warnung")            # nicht mehr "ok", obwohl weit ueber dem Ziel
        self.assertIn("übertroffen", v["text"])


@unittest.skipIf(U is None, "planer_ui nicht ladbar")
class FehlbetragAnzeige(unittest.TestCase):        # PLAN-09 in der Oberflaeche
    def test_kreditraten_ueber_depot(self):
        U.st.session_state = {}
        m = D.seed_modell()
        m["rahmen"].update(rendite_modus="manuell", rendite_manuell=8.0, horizont_jahre=10, startkapital=0.0,
                           sparrate_monat=0.0)
        m["entnahme"]["aktiv"] = False
        rate = round(_annuitaet(10000, 0.20, 120), 2)                    # 20 % Zins -> 193,26 €
        self.assertAlmostEqual(rate, 193.26, places=2)
        m["kredit"] = {"kredite": [{"name": "K", "betrag": 10000.0, "rate": rate, "jahre": 10, "zins": 20.0}],
                       "aktiv": True, "aktiv_v2": True, "rate_aus": "investment", "rate_aus_v2": True}
        R = U._rechne(m, {}, None)
        satz = next(iter(R["r_calc"].values()))
        # unabhaengig: Depot 10.000 €, Raten bis 0 €, Rest ungedeckt
        rm = (1 + satz) ** (1 / 12) - 1
        v, gezahlt = 10000.0, 0.0
        for _k in range(120):
            v *= 1 + rm
            weg = min(rate, v)
            v -= weg
            gezahlt += weg
        self.assertEqual(v, 0.0)
        z = R["zus"]
        self.assertEqual(z["endwert"], 0.0)
        self.assertAlmostEqual(z["projektion"]["kredit_raten_gezahlt"], gezahlt, places=6)
        self.assertAlmostEqual(z["fehlbetrag"], 120 * rate - gezahlt, places=6)
        self.assertGreater(z["fehlbetrag"], 1000)
        self.assertTrue(all(x >= 0 for vs in z["projektion"]["asset_verlauf"].values() for x in vs))
        txt = U._fehlbetrag_text(z)
        self.assertIn("nicht gedeckt", txt)
        self.assertIn(U._de(z["fehlbetrag"]), txt)
        self.assertEqual(U._fehlbetrag_text({"fehlbetrag": 0.0, "entnahme_fehlbetrag": 0.0}), "")


class EntnahmeAnnuitaetGrenze(unittest.TestCase):        # PLAN-05 Gegenprobe per Schleife
    def test_cent_mehr_reicht_nicht(self):
        w = E.entnahme_fuer(300000, 0.05, jahre=25)
        rm = 1.05 ** (1 / 12) - 1

        def rest(rate):
            k = 300000.0
            for _ in range(300):
                k = k * (1 + rm) - rate
            return k
        self.assertGreaterEqual(rest(w), -0.01)          # 300 volle Raten gedeckt
        self.assertLess(rest(w + 0.01), 0.0)              # 1 Cent mehr: letzte Rate nicht voll
        self.assertAlmostEqual(w, 1734.41, delta=0.01)
        # nominale Konvention (5 %/12) gaebe einen anderen Wert - Engine nutzt die geometrische
        nominal = 300000 * (0.05 / 12) / (1 - (1 + 0.05 / 12) ** -300)
        self.assertGreater(abs(nominal - w), 1.0)


class SzenarioNegativeBasis(unittest.TestCase):        # PLAN-04
    def test_rendite_fuer_negative_basis(self):
        m = D.seed_modell()
        a = [x for x in E.aktive_assets(m) if x.get("renditequelle") != "historisch" and E._typ(x) != "cash"][0]
        E.setze_annahme(m, a["id"], "manualScenario", -0.10)
        m["annahmen"] = [x for x in m["annahmen"]
                         if not (x["assetId"] == a["id"] and x["sourceType"] in ("base", "bear", "bull"))]
        w = {sz: E.rendite_fuer(m, a, methode="szenario", szenario=sz)[0] for sz in ("bear", "base", "bull")}
        self.assertLess(w["bear"], w["base"])
        self.assertLess(w["base"], w["bull"])
        regel = m.get("szenario_regel", D.SZENARIO_REGEL)
        self.assertAlmostEqual(w["bear"], -0.10 - (1 - regel["bear_faktor"]) * 0.10)
        self.assertAlmostEqual(w["bull"], -0.10 + (regel["bull_faktor"] - 1) * 0.10)


class EntnahmeVolleRaten(unittest.TestCase):        # PLAN-05
    def test_annuitaet_300k(self):
        rm = 1.05 ** (1 / 12) - 1              # Monatskonvention der Engine (geometrisch)
        w = 300000 * rm / (1 - (1 + rm) ** -300)
        self.assertAlmostEqual(w, 1734.41, delta=0.01)
        self.assertAlmostEqual(E.entnahme_fuer(300000, 0.05, jahre=25), w, delta=0.01)
        p = E.entnahmeplan(300000, 0.05, E.entnahme_fuer(300000, 0.05, jahre=25), jahre=25, max_jahre=25)
        self.assertIsNone(p["dauer_monate"])     # alle 300 Raten voll gezahlt


class ErforderlicheRenditeNone(unittest.TestCase):        # PLAN-06
    def test_unerreichbar_und_ohne_ziel(self):
        self.assertIsNone(E.erforderliche_rendite(1000, 1e15, 1, 1))
        self.assertIsNone(E.erforderliche_rendite(1000, 0, 5, 100))
        self.assertIsNone(E.erforderliche_rendite(1000, -5, 5, 100))
        r = E.erforderliche_rendite(0, 20000, 5, 300)
        self.assertAlmostEqual(E.future_value(0, r, 5, 300), 20000, delta=0.01)

    @unittest.skipIf(U is None, "planer_ui nicht ladbar")
    def test_ui_unerreichbar(self):
        U.st.session_state = {}
        m = D.seed_modell()
        m["rahmen"].update(startkapital=100.0, sparrate_monat=1.0, zielvermoegen=1e12, horizont_jahre=2)
        m["entnahme"]["aktiv"] = False
        R = U._rechne(m, {}, None)
        self.assertIsNone(R["zus"]["erforderliche_cagr"])
        self.assertEqual(U._pct_ziel(None), "nicht erreichbar")
        self.assertTrue(U._ziel_unerreichbar(m))
        self.assertEqual(U._auto_modus(m), "ziel")
        U._auto_gewichtung(m, R)
        auto = U.st.session_state["planer_autogew"]
        self.assertFalse(auto["erreichbar"])
        self.assertIsNone(auto["benoetigt"])


class KaufplanUngueltigeKurse(unittest.TestCase):        # PLAN-07
    def _bilanz(self, e, betrag):
        self.assertAlmostEqual(e["investiert"] + e["cash_soll"] + e["rest"] - e["ueberzogen"], betrag, places=6)

    def test_ungueltige_kurse(self):
        pos = [{"id": "neg", "name": "Neg", "anteil": 0.2, "kurs": -5.0},
               {"id": "nan", "name": "NaN", "anteil": 0.2, "kurs": float("nan")},
               {"id": "inf", "name": "Inf", "anteil": 0.1, "kurs": float("inf")},
               {"id": "null", "name": "Null", "anteil": 0.1, "kurs": 0.0},
               {"id": "ok", "name": "Ok", "anteil": 0.3, "kurs": 10.0},
               {"id": "c", "name": "Reserve", "anteil": 0.1, "cash": True}]
        e = E.kaufplan(pos, 1000)
        z = {x["id"]: x for x in e["zeilen"]}
        for i in ("neg", "nan", "inf", "null"):
            self.assertEqual(z[i]["stueck"], 0.0, i)
            self.assertEqual(z[i]["ist"], 0.0, i)
        self.assertEqual(sorted(e["ohne_kurs"]), sorted(["Neg", "NaN", "Inf", "Null"]))
        self.assertEqual(z["ok"]["stueck"], 30.0)
        self.assertEqual(e["mindest"], [])
        self._bilanz(e, 1000)
        self._bilanz(E.kaufplan(pos, 1000, bruchstuecke=True), 1000)

    def test_ungueltiger_anteil(self):
        e = E.kaufplan([{"id": "a", "name": "A", "anteil": float("nan"), "kurs": 5.0},
                        {"id": "b", "name": "B", "anteil": float("inf"), "kurs": 5.0},
                        {"id": "c", "name": "C", "anteil": 0.5, "kurs": 5.0}], 1000)
        z = {x["id"]: x for x in e["zeilen"]}
        self.assertEqual(z["a"]["stueck"], 0.0)
        self.assertEqual(z["b"]["stueck"], 0.0)
        self.assertEqual(z["c"]["stueck"], 100.0)
        self._bilanz(e, 1000)

    def test_mindeststueck_und_korb_bleiben(self):
        pos = [{"id": "a", "name": "Teuer", "anteil": 0.01, "kurs": 400.0},
               {"id": "k:x", "name": "X", "teil_von": "Korb", "anteil": 0.001, "kurs": 500.0},
               {"id": "c", "name": "Reserve", "anteil": 0.989, "cash": True}]
        e = E.kaufplan(pos, 10000)
        z = {x["id"]: x for x in e["zeilen"]}
        self.assertEqual(z["a"]["stueck"], 1.0)
        self.assertEqual(z["k:x"]["stueck"], 0.0)
        self._bilanz(e, 10000)


class JungeHistorie(unittest.TestCase):        # Entscheidung 12.10.2026: Ø Monatsrendite hochrechnen
    # Referenzwerte von Hand (unabhaengig vom Code):
    #   6 Mon. +5 %:  r_m = 1,05^(1/6) - 1; r_pa = (1 + r_m)^12 - 1 = 1,05^2 - 1 = 0,1025
    #   3 Mon. -6 %:  r_pa = 0,94^4 - 1 = 0,78074896 - 1 = -0,21925104
    #   Szenario-Regel: Bear = Basis - 50 % * |Basis|, Bull = Basis + 20 % * |Basis|
    #     +10,25 %: Bear 5,125 %, Bull 12,3 %;  -21,925104 %: Bear -32,887656 %, Bull -17,5400832 %
    #   Rueckfall (< 1 Monat), Halbleiter: c * 12 % + (1 - c) * 8 %, c = Confidence/100 <= 0,10
    def _m(self):
        m = D.seed_modell()
        a = D._asset("semi_jung", "Halbleiter jung", "semiconductor", 0.0)
        a["renditequelle"] = "historisch"
        a["targetWeight"] = 10.0
        m["assets"].append(a)
        return m, a

    def test_hochrechnung_referenzwerte(self):
        w, mon = E.hochrechnung_monate({"jahre": 0.5, "seit_start": 0.05})
        self.assertAlmostEqual(w, 0.1025, places=12)
        self.assertAlmostEqual(mon, 6.0)
        w, mon = E.hochrechnung_monate({"jahre": 0.25, "seit_start": -0.06})
        self.assertAlmostEqual(w, -0.21925104, places=12)
        # Monatsweg identisch: (1 + r_m)^12 - 1
        r_m = 1.05 ** (1 / 6) - 1
        self.assertAlmostEqual(E.hochrechnung_monate({"jahre": 0.5, "seit_start": 0.05})[0], (1 + r_m) ** 12 - 1,
                               places=12)
        # Mindestbasis 1 Monat (gerundete "jahre" 0,08 zaehlt noch), keine Hochrechnung darunter / ab 1 Jahr
        self.assertIsNotNone(E.hochrechnung_monate({"jahre": 0.08, "seit_start": 0.01})[0])
        for h in ({"jahre": 0.04, "seit_start": 0.05}, {"jahre": 0.5}, {"jahre": 0.5, "seit_start": None},
                  {"jahre": 0.5, "seit_start": float("nan")}, {"jahre": 0.5, "seit_start": float("inf")},
                  {"jahre": 0.5, "seit_start": -1.0}, {"jahre": 1.0, "seit_start": 0.2}, {}, None):
            self.assertEqual(E.hochrechnung_monate(h), (None, None), h)

    def test_rendite_fuer_hochgerechnet(self):
        m, a = self._m()
        hist = {a["id"]: {"jahre": 0.5, "seit_start": 0.05, "stand": "2026-10-01"}}
        w, herkunft, hinweis = E.rendite_fuer(m, a, hist, methode="manualScenario")
        self.assertAlmostEqual(w, 0.1025, places=12)
        self.assertEqual(herkunft["source"], "hochgerechnet aus 6 Mon. (Ø Monatsrendite)")
        self.assertEqual(herkunft["sourceType"], "hochgerechnet")
        self.assertIn("6 Mon.", hinweis)
        self.assertIn("hochgerechnet", hinweis)
        sz = {s_: E.rendite_fuer(m, a, hist, methode="szenario", szenario=s_)[0] for s_ in ("bear", "base", "bull")}
        self.assertAlmostEqual(sz["bear"], 0.05125, places=12)
        self.assertAlmostEqual(sz["base"], 0.1025, places=12)
        self.assertAlmostEqual(sz["bull"], 0.123, places=12)
        # negativ: 3 Mon. -6 %, Bear/Bull vorzeichenrichtig
        hist = {a["id"]: {"jahre": 0.25, "seit_start": -0.06}}
        self.assertAlmostEqual(E.rendite_fuer(m, a, hist, methode="manualScenario")[0], -0.21925104, places=12)
        sz = {s_: E.rendite_fuer(m, a, hist, methode="szenario", szenario=s_)[0] for s_ in ("bear", "bull")}
        self.assertAlmostEqual(sz["bear"], -0.32887656, places=12)
        self.assertAlmostEqual(sz["bull"], -0.17540083, places=8)
        self.assertLess(sz["bear"], -0.21925104)
        self.assertGreater(sz["bull"], -0.21925104)

    def test_rueckfall_unter_einem_monat(self):
        m, a = self._m()
        hist = {a["id"]: {"jahre": 0.04, "seit_start": 0.40}}          # ca. halber Monat
        w, herkunft, hinweis = E.rendite_fuer(m, a, hist, methode="manualScenario")
        # bisherige Daempfung: c = Confidence/100 (bei 0,04 J. sehr klein), c * 12 % + (1 - c) * 8 %;
        # die 40 % seit Start fliessen NICHT ein
        c = min(E.confidence_score(0.04, "semiconductor"), D.CONFIDENCE["ohne_historie"]) / 100.0
        self.assertLessEqual(c, 0.10)
        self.assertAlmostEqual(w, c * 0.12 + (1 - c) * 0.08, places=12)
        self.assertTrue(0.08 <= w <= 0.084)
        self.assertEqual(herkunft["source"], "zu kurze Historie – Kategorie-Standard")
        self.assertEqual(herkunft["sourceType"], "kategorie_standard")
        self.assertIn("keine Hochrechnung", hinweis)
        sz = {s_: E.rendite_fuer(m, a, hist, methode="szenario", szenario=s_)[0] for s_ in ("bear", "bull")}
        self.assertAlmostEqual(sz["bear"], w * 0.5, places=12)
        self.assertAlmostEqual(sz["bull"], w * 1.2, places=12)
        # ohne Rendite seit Start ebenfalls Rueckfall
        self.assertAlmostEqual(E.rendite_fuer(m, a, {a["id"]: {"jahre": 0.5}}, methode="manualScenario")[0],
                               0.084, places=12)
        self.assertEqual(E.kurze_historie_rendite(a, {"jahre": 0.04, "seit_start": 0.4}),
                         E.kurze_historie_rendite(a, {"jahre": 0.04}))
        self.assertLessEqual(E.kurze_historie_rendite(a, {"jahre": 0.04})[1], D.CONFIDENCE["ohne_historie"])

    def test_ab_einem_jahr_unveraendert(self):
        m, a = self._m()
        self.assertAlmostEqual(E.rendite_fuer(m, a, {a["id"]: {"jahre": 1.2, "historical1Y": 0.25,
                                                                "seit_start": 0.9}},
                                              methode="manualScenario")[0], 0.25)
        w, herkunft, _ = E.rendite_fuer(m, a, {a["id"]: {"jahre": 1.5, "gesamt_cagr": 0.12, "seit_start": 0.185}},
                                        methode="manualScenario")
        self.assertAlmostEqual(w, 0.12)
        self.assertEqual(herkunft["sourceType"], "historisch")

    def test_eigene_annahme_hat_vorrang(self):
        m, a = self._m()
        E.setze_annahme(m, a["id"], "manualScenario", 0.05)            # selbst eingetragen (auto=False)
        hist = {a["id"]: {"jahre": 0.5, "seit_start": 0.4}}
        w, herkunft, hinweis = E.rendite_fuer(m, a, hist, methode="manualScenario")
        self.assertAlmostEqual(w, 0.05)
        self.assertIn("< 1 Jahr", hinweis)
        a["renditequelle"] = "annahme"
        E.annahmen_aus_historie(m, hist)
        rec = E.annahme(m, a["id"], "manualScenario")
        self.assertAlmostEqual(rec["value"], 0.05)
        self.assertFalse(rec["auto"])

    def test_annahmen_aus_historie_und_confidence(self):
        m, a = self._m()
        a["renditequelle"] = "annahme"
        # Altbestand der vorherigen Regel (Kategorie-Standard, auto) wird ersetzt
        E.setze_annahme(m, a["id"], "manualScenario", 0.084, auto=True,
                        source="zu kurze Historie – Kategorie-Standard")
        n = E.annahmen_aus_historie(m, {a["id"]: {"jahre": 0.5, "seit_start": 0.05}})
        self.assertGreaterEqual(n, 1)
        rec = E.annahme(m, a["id"], "manualScenario")
        self.assertAlmostEqual(rec["value"], 0.1025, places=12)
        self.assertEqual(rec["source"], "hochgerechnet aus 6 Mon. (Ø Monatsrendite)")
        self.assertIn("hochgerechnet", rec["notes"])
        self.assertTrue(rec["auto"])
        self.assertEqual(E.annahmen_aus_historie(m, {a["id"]: {"jahre": 0.5, "seit_start": 0.05}}), 0)
        conf = E.confidence_fuer(m, {a["id"]: {"jahre": 0.9}})
        self.assertEqual(conf[a["id"]], D.CONFIDENCE["ohne_historie"])
        self.assertLessEqual(E.kurze_historie_rendite(a, {"jahre": 0.5, "seit_start": 0.05})[1], 10)
        conf5 = E.confidence_fuer(m, {a["id"]: {"jahre": 5.0}})
        self.assertGreater(conf5[a["id"]], D.CONFIDENCE["ohne_historie"])
        if U is not None:
            self.assertEqual(U._basis_text(m, a), "Hochger. ⚠")
        # unter 1 Monat: zurueck auf Kategorie-Standard
        E.annahmen_aus_historie(m, {a["id"]: {"jahre": 0.04, "seit_start": 0.05}})
        rec = E.annahme(m, a["id"], "manualScenario")
        self.assertEqual(rec["source"], "zu kurze Historie – Kategorie-Standard")
        self.assertTrue(0.08 <= rec["value"] <= 0.084)
        if U is not None:
            self.assertEqual(U._basis_text(m, a), "Kurz-Hist. ⚠")
        # ab 1 Jahr: gemessene Rendite p.a. ersetzt die Hochrechnung
        E.annahmen_aus_historie(m, {a["id"]: {"jahre": 1.1, "historical1Y": 0.07, "seit_start": 0.08}})
        rec = E.annahme(m, a["id"], "manualScenario")
        self.assertAlmostEqual(rec["value"], 0.07)
        self.assertTrue(rec["source"].startswith("Kurshistorie ("))


class _FakeStore:
    """GitHub-Speicher als dict: gh_read / gh_write / gh_aktualisiere wie in app.py."""
    def __init__(self, daten=None, lese_fehler=False):
        import copy
        self._copy = copy.deepcopy
        self.d = copy.deepcopy(daten or {})
        self.writes = []
        self.lese_fehler = lese_fehler

    def gh_read(self, pfad, default=None):
        return self._copy(self.d.get(pfad, default))

    def gh_write(self, pfad, obj, message=""):
        self.d[pfad] = self._copy(obj)
        self.writes.append(pfad)
        return True

    def gh_aktualisiere(self, pfad, aendern, default=None, message=""):
        if self.lese_fehler:
            return False, None
        neu = aendern(self._copy(self.d.get(pfad, default)))
        if neu is None:
            return True, self._copy(self.d.get(pfad, default))
        self.d[pfad] = self._copy(neu)
        self.writes.append(pfad)
        return True, neu

    def hilfen(self, nutzer="-", mit_aktualisiere=True):
        h = {"gh_read": self.gh_read, "gh_write": self.gh_write}
        if nutzer != "-":
            h["nutzer"] = nutzer
        if mit_aktualisiere:
            h["gh_aktualisiere"] = self.gh_aktualisiere
        return h


ANNA = {"name": "Anna Müller", "rolle": "nutzer"}
ADMIN = {"name": "Chef", "rolle": "admin"}
PFAD_ANNA = "state/benutzer/anna-muller/planer/szenarien.json"
PFAD_ADMIN = "state/planer/szenarien.json"


@unittest.skipIf(U is None, "planer_ui nicht ladbar")
class NutzerBereiche(unittest.TestCase):        # 13.10.2026: alle Planer-Eingaben je Benutzer
    def setUp(self):
        U.st.session_state = {}

    def _sitzung(self, h):
        """Erster Durchlauf einer Sitzung: Modell laden, Ausgangsstand merken (wie render)."""
        U.st.session_state = {}
        m = U._modell(h)
        U._auto_speichern(m, h)
        return m

    def test_pfade(self):
        self.assertEqual(U.szenarien_pfad(None), PFAD_ADMIN)
        self.assertEqual(U.szenarien_pfad(ADMIN), PFAD_ADMIN)
        self.assertEqual(U.szenarien_pfad(ANNA), PFAD_ANNA)
        self.assertEqual(U.musterdepot_pfad(None), "state/musterdepot.json")
        self.assertEqual(U.musterdepot_pfad(ADMIN), "state/musterdepot.json")
        self.assertEqual(U.musterdepot_pfad(ANNA), "state/benutzer/anna-muller/musterdepot.json")
        s = _FakeStore()
        self.assertEqual(U._pfad(s.hilfen(), U.PFAD_SZENARIEN), PFAD_ADMIN)        # Schluessel fehlt
        self.assertEqual(U._pfad(s.hilfen(None), U.PFAD_SZENARIEN), PFAD_ADMIN)
        self.assertEqual(U._pfad(s.hilfen(ANNA), U.PFAD_MUSTERDEPOT), "state/benutzer/anna-muller/musterdepot.json")
        # gemeinsame Daten bleiben global
        self.assertEqual(U.PFAD_KATALOG, "state/planer/katalog.json")

    def test_leeres_modell(self):
        m = U.leer_modell()
        r = m["rahmen"]
        for k in ("startkapital", "sparrate_monat", "zielvermoegen", "horizont_jahre"):
            self.assertEqual(r[k], 0, k)
        self.assertTrue(m["assets"])                                    # Vorlagen bleiben in der Liste
        for a in m["assets"]:
            self.assertFalse(a["enabled"], a["id"])
            self.assertEqual(a["targetWeight"], 0.0, a["id"])
        self.assertEqual(E.gewichte_summe(m), 0.0)
        self.assertNotIn("kredit", m)
        self.assertFalse(m["entnahme"]["aktiv"])
        self.assertEqual(m["entnahme"]["monatlich"], 0.0)
        self.assertEqual(m["kaufplan"]["betrag"], 0.0)
        # alles rechnet ohne Ausnahme
        R = U._rechne(m, {}, None)
        self.assertEqual(R["zus"]["endwert"], 0)
        r_ = renditen(m)
        self.assertEqual(E.projektion(m, r_)["endwert"], 0)
        E.szenario_vergleich(m)
        E.optimiere(m, r_, E.confidence_fuer(m))
        E.risiko_kennzahlen(m, r_, E.confidence_fuer(m), {})
        self.assertIsNone(U._benoetigt(m))
        self.assertIsNone(U._auto_modus(m))
        self.assertEqual(len(U._leer_hinweise(m)), 2)
        self.assertEqual(U._kauf_positionen(m, {}, {}), [])
        # mit Zielvermoegen, aber ohne aktive Bausteine: keine Ausnahme
        m["rahmen"].update(startkapital=1000.0, horizont_jahre=5, zielvermoegen=50000.0)
        R = U._rechne(m, {}, None)
        U._auto_gewichtung(m, R)
        self.assertEqual(len(U._leer_hinweise(m)), 1)

    def test_neuer_benutzer_startet_leer_admin_mit_beispiel(self):
        s = _FakeStore()
        m = self._sitzung(s.hilfen(ANNA))
        self.assertEqual(m["rahmen"]["startkapital"], 0)
        self.assertEqual(E.gewichte_summe(m), 0)
        m = self._sitzung(s.hilfen(ADMIN))
        self.assertEqual(m["rahmen"]["startkapital"], D.seed_modell()["rahmen"]["startkapital"])
        self.assertAlmostEqual(E.gewichte_summe(m), 100.0)
        m = self._sitzung(s.hilfen())                                   # ohne Login / alte app.py
        self.assertAlmostEqual(E.gewichte_summe(m), 100.0)
        self.assertEqual(s.writes, [])                                  # Oeffnen allein speichert nichts

    def test_speichern_und_wiederherstellen(self):
        admin_alt = {"szenarien": {"Aktuelles Modell": {"modell": D.seed_modell()}}, "aktiv": "Aktuelles Modell"}
        s = _FakeStore({PFAD_ADMIN: admin_alt})
        h = s.hilfen(ANNA)
        m = self._sitzung(h)
        self.assertEqual(U._auto_speichern(m, h), None)                 # nichts geaendert
        self.assertEqual(s.writes, [])
        m["rahmen"]["startkapital"] = 5000.0
        m["assets"][0]["enabled"], m["assets"][0]["targetWeight"] = True, 100.0
        self.assertEqual(U._auto_speichern(m, h)[0], "ok")
        self.assertEqual(s.writes, [PFAD_ANNA])
        U._auto_speichern(m, h)                                         # unveraendert -> kein zweiter Commit
        self.assertEqual(s.writes, [PFAD_ANNA])
        self.assertEqual(s.d[PFAD_ADMIN], admin_alt)                    # Admin-Daten unberuehrt
        # naechste Anmeldung
        m2 = self._sitzung(h)
        self.assertEqual(m2["rahmen"]["startkapital"], 5000.0)
        self.assertTrue(m2["assets"][0]["enabled"])
        self.assertEqual(U.st.session_state["planer_name"], "Aktuelles Modell")
        self.assertEqual(s.writes, [PFAD_ANNA])
        # anderer Benutzer sieht davon nichts
        m3 = self._sitzung(s.hilfen({"name": "Bob", "rolle": "nutzer"}))
        self.assertEqual(m3["rahmen"]["startkapital"], 0)

    def test_admin_pfad_unveraendert(self):
        alt = D.seed_modell()
        alt["rahmen"]["startkapital"] = 12345.0
        s = _FakeStore({PFAD_ADMIN: {"szenarien": {"Aktuelles Modell": {"modell": alt}, "Defensiver": {"modell": alt}},
                                     "aktiv": "Aktuelles Modell"}})
        for h in (s.hilfen(ADMIN), s.hilfen(), s.hilfen(None, mit_aktualisiere=False)):
            m = self._sitzung(h)
            self.assertEqual(m["rahmen"]["startkapital"], 12345.0)
        m["rahmen"]["sparrate_monat"] = 100.0
        self.assertEqual(U._auto_speichern(m, h)[0], "ok")              # alter Weg gh_read + gh_write
        self.assertEqual(s.writes, [PFAD_ADMIN])
        self.assertIn("Defensiver", s.d[PFAD_ADMIN]["szenarien"])       # andere Szenarien bleiben
        self.assertEqual(s.d[PFAD_ADMIN]["szenarien"]["Aktuelles Modell"]["modell"]["rahmen"]["sparrate_monat"], 100.0)

    def test_benutzerwechsel_in_derselben_sitzung(self):
        s = _FakeStore()
        hA = s.hilfen(ADMIN)
        U.st.session_state = {}
        self.assertAlmostEqual(E.gewichte_summe(U._modell(hA)), 100.0)
        m = U._modell(s.hilfen(ANNA))                                   # ohne Neuladen der Seite
        self.assertEqual(E.gewichte_summe(m), 0)
        self.assertEqual(U.st.session_state["planer_konto"], "state/benutzer/anna-muller")

    def test_lesefehler_schreibt_nichts(self):
        s = _FakeStore({PFAD_ANNA: {"szenarien": {"Aktuelles Modell": {"modell": D.seed_modell()}}}}, lese_fehler=True)
        h = s.hilfen(ANNA)
        m = self._sitzung(h)
        m["rahmen"]["startkapital"] = 1.0
        self.assertEqual(U._auto_speichern(m, h)[0], "lesefehler")
        self.assertEqual(s.writes, [])

    def test_aendern_speichern(self):
        s = _FakeStore({"x.json": {"depots": {"A": 1}}})
        for h in (s.hilfen(ANNA), s.hilfen(ANNA, mit_aktualisiere=False)):
            self.assertTrue(U._aendern_speichern(h, "x.json", lambda d: dict(d, depots=dict(d["depots"], B=2)), "m"))
        self.assertEqual(s.d["x.json"]["depots"], {"A": 1, "B": 2})
        self.assertTrue(U._aendern_speichern(s.hilfen(ANNA), "x.json", lambda d: None, "m"))   # nichts zu tun
        self.assertEqual(len(s.writes), 2)
        self.assertFalse(U._aendern_speichern(_FakeStore(lese_fehler=True).hilfen(ANNA), "x.json", lambda d: d, "m"))
        self.assertEqual(U._lesen(_FakeStore(lese_fehler=True).hilfen(ANNA), "x.json", {}), ({}, False))
        self.assertEqual(U._lesen(s.hilfen(ANNA), "x.json", {})[1], True)

    def test_hash_ignoriert_auto_annahmen(self):
        m = D.seed_modell()
        auto = next(a for a in m["annahmen"] if a.get("auto"))
        h0 = U._hash(m)
        auto["value"] = (auto.get("value") or 0) + 0.05                 # aus der Kurshistorie nachgefuehrt
        self.assertEqual(U._hash(m), h0)
        E.setze_annahme(m, auto["assetId"], auto["sourceType"], 0.33)   # eigene Eingabe
        self.assertNotEqual(U._hash(m), h0)


class Versionsmarker(unittest.TestCase):
    @unittest.skipIf(U is None, "planer_ui nicht ladbar")
    def test_versionen_gleich(self):
        self.assertEqual(E.ENGINE_VERSION, "13.10.2026 · 09:00")
        self.assertEqual(U.PLANER_VERSION, E.ENGINE_VERSION)


if __name__ == "__main__":
    unittest.main()
