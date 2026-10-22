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

    def test_kennungen_fuer_kursabruf(self):
        q = {"SAP.DE": {"name": "SAP"}, "AAPL": {"name": "Apple"}, "MSFT": {"name": "Microsoft"}}
        alle = {"SAP.DE": {"kennung": "716460"}, "AAPL": {"kennung": "AAPL"}}
        a = {c["ticker"]: c for c in S.kandidaten_aktien(q, alle, {}, {"AAPL": "US0378331005"})}
        self.assertEqual((a["SAP.DE"]["wkn"], a["SAP.DE"]["isin"]), ("716460", ""))    # ls-tc-Liste: WKN
        self.assertEqual((a["AAPL"]["wkn"], a["AAPL"]["isin"]), ("", "US0378331005"))  # Symbol ist keine WKN
        self.assertEqual((a["MSFT"]["wkn"], a["MSFT"]["isin"]), ("", ""))


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

    def test_nur_mit_kurs(self):
        b = self._bewertet()
        for c in b:
            c["kurs"] = None if c["name"] == "ETF A MSCI World" else 10.0
        d = S.musterdepot(b, {"etf": 50, "aktie": 30, "wikifolio": 15, "cash": 5}, 5, 0, nur_mit_kurs=True)
        namen = [p["name"] for p in d["positionen"]]
        self.assertNotIn("ETF A MSCI World", namen)
        self.assertIn("ETF B MSCI World", namen)                                # naechster mit Kurs

    def test_skalieren_bleibt_unter_grenze(self):
        d = S.musterdepot(self._bewertet(), {"etf": 50, "aktie": 30, "wikifolio": 15, "cash": 5}, 5, 0)
        voll = S.skalieren(d, 1.0)
        self.assertTrue(all(p["gewicht"] <= 5.0 + 1e-9 for p in voll["positionen"]))
        investiert = sum(p["gewicht"] for p in d["positionen"])
        self.assertAlmostEqual(sum(p["gewicht"] for p in voll["positionen"]), investiert, places=9)  # = eigene
        halb = S.skalieren(d, 0.5)
        self.assertAlmostEqual(sum(p["gewicht"] for p in halb["positionen"]), investiert / 2, places=9)
        self.assertAlmostEqual(halb["cash"], 100 - investiert / 2, places=9)


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

    def test_unerreichbares_ziel_haelt_eigene_aufteilung(self):
        d = Musterdepot()._bewertet()
        depot = S.musterdepot(d, {"etf": 30, "aktie": 30, "wikifolio": 30, "cash": 10}, 5, 0)
        o = S.optimieren(depot, eingaben(anfangskapital=160000, laufzeit=5), 1e9, max_dd=95, pfade=800)
        self.assertEqual(o["beste"], 1.0)                                 # Ziel ueberall 0 %: kein Cash-Berg

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


class EigeneEckdaten(unittest.TestCase):
    def test_scanner_rechnet_mit_eigenen_werten(self):
        e = eingaben(anfangskapital=160000, einzahlung=0, laufzeit=5, zielvermoegen=1e6, kredit_summe=5000,
                     scan_kapital=20000, scan_einzahlung=500, scan_laufzeit=12, scan_ziel=300000, scan_entnahme=100)
        s = S.scanner_eingaben(e)
        self.assertEqual((s["anfangskapital"], s["einzahlung"], s["entnahme"], s["kredit_summe"]), (20000, 500, 100, 0))
        self.assertEqual((P.monate(s), s["zielvermoegen"]), (144, 300000))
        start, cfs, rest = S.zahlungsplan(s)
        self.assertEqual((start, len(cfs), cfs[0]), (20000, 144, 400))
        self.assertEqual(e["anfangskapital"], 160000)                          # Builder-Werte unveraendert
        self.assertEqual(S.einstellungen_bereinigen({})["scan_kapital"], -1.0)  # noch nie gesetzt


class MusterdepotEintrag(unittest.TestCase):
    def test_ganze_stuecke_rest_cash(self):
        depot = {"positionen": [{"name": "A", "art": "etf", "gewicht": 60.0, "isin": "IE00A"},
                                {"name": "B", "art": "aktie", "gewicht": 30.0, "wkn": "BBB111"},
                                {"name": "C", "art": "wikifolio", "gewicht": 10.0, "wkn": "LS9CCC"}], "cash": 0.0}
        e, ohne = S.musterdepot_eintrag(depot, 10000, {"IE00A": (1, 33.0), "BBB111": (2, 1000.0)}, "2026-10-21",
                                        profil="Hoch")
        self.assertEqual([(p["name"], p["stueck"]) for p in e["positionen"]], [("A", 181), ("B", 3)])
        self.assertEqual(ohne, ["C"])                                           # ohne Kurs -> Cash
        self.assertAlmostEqual(e["cash"], 10000 - 181 * 33 - 3 * 1000, places=6)
        self.assertEqual((e["name"], e["quelle"]), ("Investment Scanner Musterdepot", "Investment-Scanner · Hoch"))


class Top500Kurse(unittest.TestCase):
    def test_ids_kurse_und_namen(self):
        ids = S.top500_ids({"US0378331005": {"id": 11, "wkn": "865985", "isin": "US0378331005"},
                            "KAT:A0RPWH": {"id": 22, "wkn": "A0RPWH", "isin": "IE00B4L5Y983"}},
                           {"liste": [[33, "LS9ABC", "Wiki", "DE000LS9ABC1"]]})
        self.assertEqual((ids["865985"], ids["IE00B4L5Y983"], ids["LS9ABC"]), (11, 22, 33))
        depot = {"positionen": [{"name": "Apple", "isin": "US0378331005", "wkn": "", "kurs": 200.0},
                                {"name": "Wiki", "wkn": "LS9ABC", "isin": "", "kurs": 150.0},
                                {"name": "Neu", "wkn": "XYZ123", "isin": "", "kurs": 10.0},
                                {"name": "Ohne", "wkn": "QQQ111", "isin": "", "kurs": None}], "cash": 0}
        k = S.kurse_aus_top500(depot, ids)
        self.assertEqual((k["US0378331005"], k["LS9ABC"], k["XYZ123"]), ((11, 200.0), (33, 150.0), (None, 10.0)))
        self.assertNotIn("QQQ111", k)                                          # ohne Kurs: kein Eintrag
        self.assertEqual(S.musterdepot_name({}, "Hoch", "21.10.2026"), "Investment Scanner · Hoch · 21.10.2026")
        self.assertEqual(S.musterdepot_name({"Investment Scanner · Hoch · 21.10.2026": {}}, "Hoch", "21.10.2026"),
                         "Investment Scanner · Hoch · 21.10.2026 (2)")       # nie ueberschreiben


class KursFehlt(unittest.TestCase):
    def test_nur_moegliche_depotwerte_ohne_kurs(self):
        b = [{"art": "etf", "name": f"E{i}", "ausreichend": True, "score": 90 - i, "kurs": None if i % 2 else 5.0}
             for i in range(6)] + [{"art": "etf", "name": "Schwach", "ausreichend": True, "score": 20, "kurs": None},
                                   {"art": "etf", "name": "Jung", "ausreichend": False, "score": 99, "kurs": None}]
        self.assertEqual([c["name"] for c in S.kurs_fehlt(b, je_klasse=4)], ["E1", "E3"])


class ZielDepot(unittest.TestCase):
    def test_renditestaerkste_mit_kurs_ohne_cash(self):
        def c(name, r5, kurs=10.0, art="etf", jahre_feld="5J"):
            return {"art": art, "name": name, "perf": {jahre_feld: ((1 + r5) ** (5 if jahre_feld == "5J" else 1) - 1) * 100},
                    "kurs": kurs, "vola": 30.0, "branche": "", "prognose": {"mu": 7.0, "sigma": 30.0}}
        b = [c("A", 0.50), c("B", 0.45), c("C", 0.40), c("D", 0.10), c("Ohne Kurs", 0.90, kurs=None)]
        d = S.ziel_depot(b, 44.0, max_gewicht=34.0)
        self.assertEqual([p["name"] for p in d["positionen"]], ["A", "B", "C"])     # 3 x 33,3 %
        self.assertAlmostEqual(d["cash"], 0.0, places=9)
        self.assertAlmostEqual(d["hist_rendite"], 45.0, places=6)
        self.assertTrue(d["erreicht"])
        mu, _ = S.portfolio_kennzahlen(d)
        self.assertAlmostEqual(mu, 45.0, places=6)                               # Prognose = Historie
        self.assertFalse(S.ziel_depot(b, 60.0, max_gewicht=34.0)["erreicht"])
        kaputt = [c("Eingestellt", 0.80, kurs=0.006), dict(c("Sprung", 9.0), vola=30.0),
                  dict(c("Wild", 0.60), vola=400.0)] + b
        namen = [p["name"] for p in S.ziel_depot(kaputt, 44.0, max_gewicht=34.0)["positionen"]]
        self.assertEqual(namen, ["A", "B", "C"])                                 # Datenfehler fallen heraus


class Favoriten(unittest.TestCase):
    def _kand(self):
        q = {"AAA": {"name": "Alpha", "kurs": 100, "kwae": "EUR", "gesamt": 90}}
        aktien = S.kandidaten_aktien(q, {"AAA": {"kennung": "A0AAAA", "5J": 61.051}}, {})
        return aktien + S.kandidaten_katalog([etf("iShares Core MSCI World", 60), etf("Vanguard FTSE All-World", 50)])

    def test_markieren_vorhandene_und_neue(self):
        auswahl = [{"art": "aktie", "name": "Alpha AG", "wkn": "A0AAAA", "isin": "", "kurs": 100.0},
                   {"art": "etf", "name": "Leverage Shares 3x Nvidia", "wkn": "LEV3XN", "isin": "", "kurs": 5.0},
                   {"art": "wikifolio", "name": "Ohne Historie", "wkn": "", "isin": "DE000LS9AAA0", "kurs": 120.0}]
        k = S.favoriten_markieren(self._kand(), auswahl)
        fav = {c["name"]: c for c in k if c.get("favorit")}
        self.assertEqual(set(fav), {"Alpha", "Leverage Shares 3x Nvidia", "Ohne Historie"})
        self.assertIsNotNone(fav["Alpha"]["fund"])                 # Aktie mit Fundamentaldaten wiederverwendet
        self.assertEqual(len(k), 5)                                # 3 Kandidaten + 2 neue Favoriten

    def test_depot_nur_aus_favoriten_alle_gleich_gewichtet(self):
        auswahl = [{"art": "aktie", "name": "Alpha", "wkn": "A0AAAA", "isin": "", "kurs": 100.0},
                   {"art": "etf", "name": "Leverage Shares 3x Nvidia", "wkn": "LEV3XN", "isin": "", "kurs": 5.0,
                    "1J": 80.0},
                   {"art": "etf", "name": "Ohne Kurs", "wkn": "OHNEKS", "isin": "", "1J": 10.0}]
        b = S.bewerten(S.favoriten_markieren(self._kand(), auswahl), 10)
        fav = [c for c in b if c.get("favorit")]
        d = S.musterdepot(fav, {"etf": 40, "aktie": 60, "wikifolio": 0, "cash": 0}, 50.0, nur_mit_kurs=True,
                          frei=True)
        g = {p["name"]: p["gewicht"] for p in d["positionen"]}
        self.assertEqual(g, {"Leverage Shares 3x Nvidia": 40.0, "Alpha": 50.0})   # Grenze 50 %, kein Score-Filter
        self.assertAlmostEqual(d["cash"], 10.0)
        self.assertEqual([c["name"] for c in S.kurs_fehlt(fav, alle=True)], ["Ohne Kurs"])

    def test_bereinigen(self):
        b = S.einstellungen_bereinigen({"scan_profil": "favoriten", "scan_favoriten": ["A", "A", 3, "", "B"]})
        self.assertEqual((b["scan_profil"], b["scan_favoriten"]), ("favoriten", ["A", "B"]))
        self.assertEqual(S.einstellungen_bereinigen({"scan_favoriten": "x"})["scan_favoriten"], [])


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
