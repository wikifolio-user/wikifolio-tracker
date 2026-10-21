"""Tests Investment-Scanner (synthetische Daten, Sollwerte mit geschlossenen Formeln)."""
import math
import unittest

import portfolio_builder as P
import scanner as S


def eingaben(**kw):
    e = P.standard()
    e.update({"anfangskapital": 10000.0, "sonstiges_kapital": 0.0, "kredit_summe": 0.0, "kredit_rate": 0.0,
              "einzahlung": 0.0, "entnahme": 0.0, "ausgaben": 0.0, "rendite_pa": 0.0, "laufzeit": 10,
              "laufzeit_einheit": "Jahre"})
    e.update(kw)
    return e


def etf(name, r5, vola=15.0, dd=-30.0):
    return {"art": "etf", "name": name, "wkn": name[:6].upper(), "isin": "", "5J": r5, "1J": r5 / 5,
            "vola": vola, "maxdd": dd, "jahre": 6}


class Kandidaten(unittest.TestCase):
    def test_hebel_und_krypto_fallen_heraus(self):
        k = S.kandidaten_katalog([etf("iShares Core MSCI World", 60), etf("Leverage Shares 3x Nvidia", 900),
                                  etf("Xtrackers S&P 500 2x Leveraged Daily", 200),
                                  {"art": "krypto", "name": "Bitcoin ETP", "1J": 50}])
        self.assertEqual([c["name"] for c in k], ["iShares Core MSCI World"])

    def test_aktien_mit_fundament_und_euro_kurs(self):
        q = {"AAA": {"name": "Alpha", "kurs": 112.4, "kwae": "USD", "gesamt": 90, "fcfy": 5, "g_ums": 10},
             "BBB": {"name": "Beta", "kurs": 250, "kwae": "GBp", "gesamt": 40}}
        a = S.kandidaten_aktien(q, {"AAA": {"kennung": "AAA", "5J": 61.051}}, {"USD": 1.124, "GBP": 0.85})
        self.assertAlmostEqual(a[0]["kurs"], 100.0, places=1)
        self.assertAlmostEqual(a[1]["kurs"], 2.5 / 0.85, places=6)
        self.assertAlmostEqual(S.hist_rendite(a[0])[0], 10.0, places=6)
        self.assertEqual(S.fundamental_rendite(a[0]["fund"]), 10.0)            # 5 % FCF + ½ × 10 %
        self.assertEqual(S.fundamental_rendite({"fcfy": 30, "g_ums": 80}), 13.0)  # begrenzt


class Prognose(unittest.TestCase):
    def test_schrumpfung_zur_erwartung(self):
        c = {"art": "wikifolio", "perf": {"1J": 300.0}, "vola": 30.0, "fund": None}
        p = S.prognose(c, 10)
        a = S.ANNAHMEN
        w = 1 / (1 + a["glaubwuerdigkeit_jahre"]) * a["vorsprung_anteil"]      # 1 J. Historie
        self.assertAlmostEqual(p["mu"], 5.0 + w * (a["rendite_deckel"] - 5.0), places=6)  # gedeckelt
        self.assertAlmostEqual(p["opt"] - p["mu"], 1.2816 * 30 / math.sqrt(10), places=6)

    def test_lange_historie_zaehlt_mehr(self):
        kurz = S.prognose({"art": "etf", "perf": {"1J": 20.0}, "vola": 15.0}, 10)["mu"]
        lang = S.prognose({"art": "etf", "perf": {"10J": (1.2 ** 10 - 1) * 100}, "vola": 15.0}, 10)["mu"]
        self.assertGreater(lang, kurz)


class Musterdepot(unittest.TestCase):
    def _bewertet(self):
        etfs = [etf(f"ETF {i} Welt", 40 + i, 15) for i in range(12)] + [etf("ETF A MSCI World", 90),
                                                                        etf("ETF B MSCI World", 89)]
        wik = [{"art": "wikifolio", "name": f"Wiki {i}", "wkn": f"LS9{i:03d}", "1J": 20 + i, "3J": 50 + i,
                "vola": 20.0, "maxdd": -25.0, "jahre": 4} for i in range(3)] + [
               {"art": "wikifolio", "name": "Wiki Jung", "wkn": "LS9JNG", "1J": 300, "vola": 20.0, "jahre": 1}]
        etfs += [etf("VanEck Semiconductor", 150), etf("iShares S&P 500 Information Technology", 120),
                 etf("Invesco Nasdaq-100", 110)]
        q = {f"S{i}": {"name": f"Aktie {i}", "gesamt": 95 - i, "br": "Software" if i < 6 else f"B{i}",
                       "fcfy": 4, "g_ums": 12} for i in range(10)}
        alle = {f"S{i}": {"5J": 80.0 + i} for i in range(10)}
        return S.bewerten(S.kandidaten_katalog(etfs + wik) + S.kandidaten_aktien(q, alle), 10)

    def test_hoechstgewicht_summe_und_diversifikation(self):
        d = S.musterdepot(self._bewertet(), {"etf": 50, "aktie": 30, "wikifolio": 15, "cash": 5},
                          max_gewicht=5, min_score=0)
        gew = [p["gewicht"] for p in d["positionen"]]
        self.assertTrue(all(g <= 5.0 + 1e-9 for g in gew))
        self.assertAlmostEqual(sum(gew) + d["cash"], 100.0, places=9)
        welt = [p for p in d["positionen"] if "MSCI World" in p["name"]]
        self.assertEqual(len(welt), 1)                                          # ein ETF je Kernindex
        software = [p for p in d["positionen"] if p.get("branche") == "Software"]
        self.assertTrue(0 < len(software) <= 3)                                 # max. 3 je Branche
        wik = [p for p in d["positionen"] if p["art"] == "wikifolio"]
        self.assertEqual(len(wik), 3)                                           # junges nicht im Depot
        tech = [p for p in d["positionen"] if any(k in p["name"] for k in ("Semi", "Technology", "Nasdaq"))]
        self.assertEqual(len(tech), 2)                                          # Tech-Cluster max. 2
        self.assertAlmostEqual(d["cash"], 5 + 0, places=9)                     # 15 % / 3 = 5 % je Wert
        self.assertTrue(d["hinweise"] == [] or all("Cash" in h or "ins Cash" in h for h in d["hinweise"]))

    def test_skalieren_bleibt_unter_grenze(self):
        d = S.musterdepot(self._bewertet(), {"etf": 50, "aktie": 30, "wikifolio": 15, "cash": 5}, 5, 0)
        voll = S.skalieren(d, 1.0)
        self.assertTrue(all(p["gewicht"] <= 5.0 + 1e-9 for p in voll["positionen"]))
        halb = S.skalieren(d, 0.5)
        self.assertAlmostEqual(sum(p["gewicht"] for p in halb["positionen"]), 50.0, places=9)
        self.assertAlmostEqual(halb["cash"], 50.0, places=9)


class Simulation(unittest.TestCase):
    def test_ohne_schwankung_wie_builder(self):
        e = eingaben(einzahlung=300, anfangskapital=10000)
        start, cfs, rest = S.zahlungsplan(e)
        sim = S.simulieren(6.0, 0.0, start, cfs, pfade=10, regime=False)
        self.assertAlmostEqual(sim["werte"][0, -1], P.simulation(e, rendite_pa=6.0)["endwert"], places=6)
        self.assertEqual(rest, 0.0)

    def test_kredit_restschuld_und_kosten(self):
        e = eingaben(kredit_summe=20000, kredit_zins_pa=4, kredit_rate=100)
        start, cfs, rest = S.zahlungsplan(e)
        self.assertAlmostEqual(rest, P.simulation(e)["restschuld"], places=6)
        a = S.simulieren(6.0, 0.0, start, cfs, kosten=1.0, pfade=5, regime=False)["werte"][0, -1]
        b = S.simulieren(5.0, 0.0, start, cfs, kosten=0.0, pfade=5, regime=False)["werte"][0, -1]
        self.assertAlmostEqual(a, b, places=6)                                  # Kosten mindern die Rendite

    def test_wahrscheinlichkeit_und_drawdown(self):
        e = eingaben()
        start, cfs, rest = S.zahlungsplan(e)
        median = 10000 * 1.06 ** 10
        # lognormal: ln(Ziel/Median) / (0,15 * sqrt(10)), Median um sigma²/2 je Jahr unter dem Mittel
        a = S.auswerten(S.simulieren(6.0, 15.0, start, cfs, pfade=10000, regime=False), median * 0.4)
        b = S.auswerten(S.simulieren(6.0, 15.0, start, cfs, pfade=10000, regime=False), median * 2.0)
        self.assertAlmostEqual(a["wahrscheinlichkeit"], 0.955, delta=0.02)
        self.assertAlmostEqual(b["wahrscheinlichkeit"], 0.045, delta=0.02)
        self.assertGreater(a["dd95"], a["dd50"])
        krise = S.auswerten(S.simulieren(6.0, 15.0, start, cfs, pfade=10000, regime=True), 0)
        ohne = S.auswerten(S.simulieren(6.0, 15.0, start, cfs, pfade=10000, regime=False), 0)
        self.assertGreater(krise["dd95"], ohne["dd95"])                         # Krisen: tiefere Einbrueche
        self.assertLess(krise["end"][10], ohne["end"][10])                     # schlechte Faelle schlechter

    def test_optimieren_haelt_verlusttoleranz(self):
        d = Musterdepot()._bewertet()
        depot = S.musterdepot(d, {"etf": 50, "aktie": 30, "wikifolio": 15, "cash": 5}, 5, 0)
        o = S.optimieren(depot, eingaben(einzahlung=300), 100000, max_dd=25, pfade=1500)
        beste = next(s for s in o["stufen"] if s["anteil"] == o["beste"])
        if o["eingehalten"]:
            self.assertLessEqual(beste["dd95"], 25)
        self.assertEqual(len(o["stufen"]), 8)

    def test_alternativen_ohne_hoehere_rendite(self):
        e = eingaben(einzahlung=100)
        alt = S.alternativen(6.0, 15.0, e, 200000, pfade=1500)
        self.assertGreater(alt["sparrate"], 100)
        start, cfs, rest = S.zahlungsplan(dict(e, einzahlung=alt["sparrate"]))
        w = S.auswerten(S.simulieren(6.0, 15.0, start, cfs, pfade=3000, seed=13), 200000, rest)
        self.assertGreaterEqual(w["wahrscheinlichkeit"], 0.45)
        self.assertIn("jahre_mehr", alt)


class Entnahme(unittest.TestCase):
    def _depot(self):
        return {"positionen": [{"name": "A", "art": "etf", "gewicht": 60.0, "kurs": 50.0, "isin": "IE00A",
                                "prognose": {"mu": 0.0}},
                               {"name": "B", "art": "aktie", "gewicht": 30.0, "kurs": 0.0, "wkn": "BBB",
                                "prognose": {"mu": 8.0}}], "cash": 10.0}

    def test_stueckzahlen_im_zahlungsplan(self):
        e = eingaben(laufzeit=12, laufzeit_einheit="Monate", einzahlung=100, scan_entnahme_art="stueck",
                     scan_verkauf={"IE00A": 4, "BBB": 9, P.TAGESGELD: 0})
        pos = S.depot_positionen(self._depot(), S.einstellungen_bereinigen(e)["scan_verkauf"])
        self.assertEqual([p["name"] for p in pos], ["A", "B", P.TAGESGELD])
        self.assertEqual(pos[0]["verkauf_stueck"], 4)
        start, cfs, rest = S.zahlungsplan(e, self._depot())
        # A: 120 Stueck (6.000 EUR / 50), 0 % Rendite -> jeden Monat 4 x 50 = 200 EUR; B ohne Kurs: nichts
        self.assertEqual(start, 10000)
        for c in cfs:
            self.assertAlmostEqual(c, 100 - 200, places=9)
        ohne_depot = S.zahlungsplan(e)[1]
        self.assertEqual(ohne_depot, [100.0] * 12)

    def test_betrag_und_bereinigen(self):
        e = eingaben(laufzeit=12, laufzeit_einheit="Monate", entnahme=250)
        self.assertEqual(S.zahlungsplan(e, self._depot())[1], [-250.0] * 12)
        b = S.einstellungen_bereinigen({"scan_entnahme_art": "x", "scan_verkauf": {"A": -1, "B": "3"}})
        self.assertEqual(b["scan_entnahme_art"], "betrag")
        self.assertEqual(b["scan_verkauf"], {"B": 3.0})


class Risiken(unittest.TestCase):
    def test_stress_und_empfehlungen(self):
        depot = {"positionen": [{"name": "A", "art": "etf", "gewicht": 50.0, "wkn": "AAA", "score": 80},
                                {"name": "B", "art": "aktie", "gewicht": 30.0, "wkn": "BBB", "score": 70}],
                 "cash": 20.0}
        crash = next(s for s in S.stresstest(depot, 10000) if s["szenario"] == "Aktiencrash")
        self.assertAlmostEqual(crash["prozent"], 0.5 * -35 + 0.3 * -40, places=9)
        self.assertAlmostEqual(crash["euro"], 10000 * crash["prozent"] / 100, places=9)
        best = [{"name": "A", "wkn": "AAA", "gewicht": 60}, {"name": "Z", "wkn": "ZZZ", "gewicht": 40}]
        emp = {x["name"]: x["aktion"] for x in S.empfehlungen(best, depot, [{"wkn": "ZZZ", "score": 30,
                                                                              "name": "Z"}])}
        self.assertEqual(emp, {"A": "Reduzieren", "Z": "Austausch prüfen", "B": "Neu"})


if __name__ == "__main__":
    unittest.main()
