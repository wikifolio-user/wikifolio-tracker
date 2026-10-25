"""Depot-Analyse & Optimierung (python3 -m unittest test_depot_analyse).

Sollwerte aus geschlossenen Formeln/Handrechnung, Eingaben synthetisch (keine echten Depotdaten)."""
import copy
import math
import unittest

import pandas as pd

import depot_analyse as D

LEER = D.marktdaten_index({})


def reihe(werte, start="2025-01-01"):
    return pd.Series([float(w) for w in werte], index=pd.bdate_range(start, periods=len(werte)))


def pos(name, wert, art_hinweis=None, kurs=100.0, einstand=None, hist=None, **kw):
    p = {"name": name, "wkn": kw.pop("wkn", name.upper()[:6]), "kurs": kurs, "vortag": kw.pop("vortag", kurs),
         "stueck": wert / kurs, "wert": wert, "einstand": wert if einstand is None else einstand, "hist": hist}
    p.update(kw)
    return D.anreichern(p, LEER, {"art": art_hinweis} if art_hinweis else None)


def aktie(name, wert, score, **kw):
    p = pos(name, wert, "aktie", **kw)
    p["fund"] = {"gesamt": score, "bew": kw.get("bew"), "kgv": kw.get("kgv"), "h_kgv": kw.get("h_kgv"),
                 "land": kw.get("land", "USA"), "br": kw.get("br", "Technology"), "div": kw.get("div")}
    p["land"], p["branche"] = p["fund"]["land"], p["fund"]["br"]
    p.update(D.position_score(p))
    return p


class Historie(unittest.TestCase):
    def test_konstantes_wachstum_ohne_schwankung(self):
        h = D.historie_kennzahlen(reihe([100 * 1.001 ** i for i in range(300)]))
        self.assertAlmostEqual(h["vola"], 0.0, places=6)
        self.assertAlmostEqual(h["maxdd"], 0.0)
        self.assertAlmostEqual(h["vom_hoch"], 0.0)

    def test_rueckgang_und_wochenveraenderung(self):
        w = [100.0] * 50 + [80.0] * 30 + [90.0] * 30
        h = D.historie_kennzahlen(reihe(w))
        self.assertAlmostEqual(h["maxdd"], -20.0)
        self.assertAlmostEqual(h["vom_hoch"], -10.0)
        self.assertAlmostEqual(h["w1"], 0.0)
        self.assertIsNone(D.historie_kennzahlen(reihe([1, 2, 3])))      # zu wenig Daten

    def test_schwankung_alternierend(self):
        w = [100.0 * (1.01 if i % 2 else 1.0) for i in range(200)]
        r = [w[i] / w[i - 1] - 1 for i in range(1, 200)]
        m = sum(r) / len(r)
        sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
        self.assertAlmostEqual(D.historie_kennzahlen(reihe(w))["vola"], sd * math.sqrt(252) * 100, places=6)


class Klasse(unittest.TestCase):
    def test_erkennung(self):
        self.assertEqual(D.art_erkennen("iShares Core MSCI World UCITS ETF"), "etf")
        self.assertEqual(D.art_erkennen("Trend", "LS9ABC123"), "wikifolio")
        self.assertEqual(D.art_erkennen("Irgendwas"), "sonstiges")
        self.assertEqual(D.art_erkennen("Xtrackers ETF", hinweis="aktie"), "aktie")

    def test_anreichern_ueber_wkn_und_isin(self):
        zeilen = {"ALV.DE": {"s": "ALV.DE", "name": "Allianz", "gesamt": 72, "br": "Insurance", "kwae": "EUR",
                             "div": 4.5, "d": 0}}
        kat = [{"felder": ["typ", "name", "kennung", "isin", "1J", "3J", "vola", "maxdd", "jahre", "div"],
                "zeilen": [["aktie", "Allianz", "840400", "DE0008404005", 20, 60, 15, -40, 18, 4.0],
                           ["etf", "iShares Core MSCI World", "A0RPWH", "IE00B4L5Y983", 15, 45, 14, -30, 15, None]]}]
        m = D.marktdaten_index(zeilen, {"DE0008404005": "ALV.DE"}, kat)
        p = D.anreichern({"name": "Allianz", "wkn": "840400", "kurs": 300, "stueck": 1, "wert": 300}, m,
                         detail_lader=lambda s, z: {"land": "Deutschland", "p": {"qualitaet": 15}})
        self.assertEqual((p["art"], p["symbol"], p["score"], p["land"]), ("aktie", "ALV.DE", 72.0, "Deutschland"))
        self.assertEqual(p["div_quelle"], "Qualitäts-Agent (Yahoo Finance)")
        e = D.anreichern({"name": "iShares Core MSCI World", "wkn": "IE00B4L5Y983", "kurs": 100, "stueck": 1,
                          "wert": 100}, m)
        self.assertEqual(e["art"], "etf")
        self.assertEqual(e["index"], "MSCI World")
        self.assertIn("ETF-Score", e["score_quelle"])
        self.assertIsNone(e["ter"])                                     # nie geschaetzt
        self.assertEqual(e["teilfreistellung"], 30.0)

    def test_eigene_angaben_haben_vorrang(self):
        p = D.anreichern({"name": "X ETF", "wkn": "X", "kurs": 1, "stueck": 1, "wert": 1}, LEER,
                         {"ter": "0.2", "land": "Welt", "div": 1.5})
        self.assertEqual((p["ter"], p["land"], p["div"], p["div_quelle"]), (0.2, "Welt", 1.5, "eigene Angabe"))

    def test_ohne_daten_kein_score(self):
        p = pos("Unbekannt AG", 1000, "aktie")
        self.assertIsNone(p["score"])
        self.assertIn("nicht im Datenbestand", p["score_quelle"])


class Kennzahlen(unittest.TestCase):
    def setUp(self):
        self.p = [aktie("A", 3000, 80, vola=None), aktie("B", 1000, 40), pos("C ETF MSCI World", 6000, "etf")]

    def test_gewichte_und_werte(self):
        k = D.kennzahlen(self.p, cash=0)
        self.assertAlmostEqual(k["gesamt"], 10000)
        self.assertAlmostEqual(k["gewichte"]["A"], 30.0)
        self.assertEqual(k["groesste"][0], "C ETF MSCI World")
        # effektive Anzahl: 1 / (0,3² + 0,1² + 0,6²/10)
        self.assertAlmostEqual(k["eff_n"], 1 / (0.09 + 0.01 + 0.036), places=6)
        self.assertEqual(k["verteilung"]["Land"]["unbekannt"], 60.0)

    def test_positionen_ohne_kurs_zaehlen_nicht(self):
        ohne = pos("Ohne Kurs", 5000, "aktie", ohne_kurs=True)
        k = D.kennzahlen(self.p + [ohne], cash=0)
        self.assertAlmostEqual(k["gesamt"], 10000)
        self.assertEqual(len(k["ohne_kurs"]), 1)

    def test_depotschwankung_ein_wert_und_zwei_etfs(self):
        a = pos("ETF A", 5000, "etf")
        a["vola"] = 15.0
        self.assertAlmostEqual(D.kennzahlen([a])["vola"], 15.0)
        b = pos("ETF B", 5000, "etf")
        b["vola"] = 15.0
        # 0,5²·0,15²·2 + 2·0,5·0,5·0,15²·0,8
        erwartet = math.sqrt(0.25 * 0.0225 * 2 + 2 * 0.25 * 0.0225 * 0.8) * 100
        self.assertAlmostEqual(D.kennzahlen([a, b])["vola"], erwartet)

    def test_dividende_und_kosten_nur_bekannte(self):
        a = aktie("A", 4000, 70, div=2.0)
        a["div"] = 2.0
        e = pos("E ETF", 6000, "etf")
        k = D.kennzahlen([a, e])
        self.assertAlmostEqual(k["dividende"], 80.0)
        self.assertAlmostEqual(k["div_abdeckung"], 40.0)
        self.assertIsNone(k["kosten"])
        self.assertEqual(k["kosten_abdeckung"], 0.0)
        self.assertIsNone(k["teile"]["kosten"])                        # zaehlt nicht in den Score
        e["ter"] = 0.2
        k = D.kennzahlen([a, e])
        self.assertAlmostEqual(k["kosten"], 12.0)

    def test_leeres_depot(self):
        k = D.kennzahlen([], 0)
        self.assertIsNone(k["score"])

    def test_ueberschneidung(self):
        a, b = pos("iShares MSCI World ETF", 5000, "etf"), pos("Xtrackers MSCI World ETF", 5000, "etf")
        u = D.kennzahlen([a, b])["ueberschneidungen"]
        self.assertTrue(u and u[0]["stark"])
        c = pos("Vanguard S&P 500 ETF", 5000, "etf")
        u = D.kennzahlen([a, c])["ueberschneidungen"]
        self.assertFalse(u[0]["stark"])


class Profil(unittest.TestCase):
    def test_kurzer_horizont_mehr_liquiditaet(self):
        z = D.zielstruktur({"risiko": "wachstum", "horizont": 2})["ziel"]
        self.assertEqual(sum(z.values()), 100)
        self.assertEqual(z["cash"], 20)

    def test_langer_horizont(self):
        z = D.zielstruktur({"risiko": "defensiv", "horizont": 20})["ziel"]
        self.assertEqual((z["cash"], z["etf"], sum(z.values())), (5, 75, 100))

    def test_ungueltiges_profil(self):
        p = D.profil_bereinigen({"risiko": "xyz", "horizont": -3, "max_gewicht": 500})
        self.assertEqual((p["risiko"], p["horizont"], p["max_gewicht"]), ("ausgewogen", 0.0, None))


class Empfehlungen(unittest.TestCase):
    def test_regeln(self):
        ps = [aktie("Stark", 800, 85), aktie("Schwach", 1000, 30, bew="teuer"), aktie("Gross", 6000, 60),
              aktie("Mittel", 2000, 55)]
        k = D.kennzahlen(ps)
        e = {p["name"]: D.empfehlung(p, k) for p in ps}
        self.assertEqual(e["Stark"]["kategorie"], "Aufstocken prüfen")
        self.assertEqual(e["Schwach"]["kategorie"], "Verkauf prüfen")
        self.assertEqual(e["Gross"]["kategorie"], "Reduzieren prüfen")
        self.assertEqual(e["Gross"]["prio"], "hoch")
        self.assertEqual(e["Mittel"]["kategorie"], "Reduzieren prüfen")       # 20 % > 15 % Hoechstgewicht
        self.assertTrue(all(x["kategorie"] in D.EMPFEHLUNGEN for x in e.values()))

    def test_welt_etf_ist_kernposition(self):
        welt = pos("Vanguard FTSE All-World UCITS ETF", 6000, "etf")
        welt.update(score=80.0, score_quelle="Test")
        sp = pos("iShares Core S&P 500 UCITS ETF", 2500, "etf")
        sp.update(score=80.0, score_quelle="Test")
        rest = [aktie(f"A{i}", 300, 70) for i in range(5)]
        k = D.kennzahlen([welt, sp] + rest)
        self.assertEqual(D.hoechstgewicht(welt, 15), 100.0)
        self.assertEqual(D.hoechstgewicht(sp, 15), 30.0)
        self.assertNotIn(D.empfehlung(welt, k)["kategorie"], ("Reduzieren prüfen", "Verkauf prüfen"))
        self.assertNotIn(D.empfehlung(sp, k)["kategorie"], ("Reduzieren prüfen", "Verkauf prüfen"))
        typen = {(w["typ"], w["schluessel"]) for w in D.warnungen([welt, sp] + rest, k)}
        self.assertNotIn(("Übergewicht", D.schluessel(welt)), typen)
        einzel = aktie("Einzel", 6000, 80)
        k2 = D.kennzahlen([einzel, sp] + rest)
        self.assertEqual(D.empfehlung(einzel, k2)["kategorie"], "Reduzieren prüfen")

    def test_ohne_score_beobachten(self):
        p = pos("Unbekannt", 1000, "aktie")
        self.assertEqual(D.empfehlung(p, D.kennzahlen([p, pos("E ETF", 9000, "etf")]))["kategorie"], "Beobachten")

    def test_bewertung_aus_kgv(self):
        p = aktie("Teuer", 1000, 60, kgv=40, h_kgv=20)
        self.assertEqual(D.bewertungsaussage(p)[1], -1)
        p = aktie("ETF", 1000, 60)
        p["art"] = "etf"
        self.assertIsNone(D.bewertungsaussage(p)[1])


class Warnungen(unittest.TestCase):
    def test_nur_relevante(self):
        ruhig = aktie("Ruhig", 1000, 70)
        k = D.kennzahlen([ruhig] + [aktie(f"W{i}", 1000, 70) for i in range(9)])
        self.assertFalse([w for w in D.warnungen([ruhig], k) if w["schluessel"] == D.schluessel(ruhig)])

    def test_uebergewicht_kurssprung_scoreabfall(self):
        p = aktie("Gross", 8000, 50, vortag=90.0)       # +11 % zum Vortag
        q = aktie("Klein", 2000, 70)
        k = D.kennzahlen([p, q])
        vorher = {"GROSS": {"score": 65, "div": None}}
        typen = {w["typ"] for w in D.warnungen([p, q], k, vorher)}
        self.assertTrue({"Übergewicht", "Kursbewegung", "Fundamentale Veränderung"} <= typen)

    def test_stand_merken(self):
        p = aktie("A", 1000, 50)
        st = D.stand_merken([p], D.kennzahlen([p]))
        self.assertEqual(st["A"]["score"], 50.0)
        self.assertIn("_vola", st)


class Steuern(unittest.TestCase):
    def t(self, art, gewinn, tfs=0.0):
        return {"aktion": "Verkauf", "art": art, "gewinn": gewinn, "teilfreistellung": tfs}

    def test_abgeltung_soli(self):
        self.assertAlmostEqual(D.steuern([self.t("aktie", 1000)])["steuer"], 263.75)

    def test_teilfreistellung_und_freibetrag(self):
        self.assertAlmostEqual(D.steuern([self.t("etf", 1000, 30)])["steuer"], 700 * 0.26375)
        r = D.steuern([self.t("etf", 1000, 30)])
        self.assertEqual((r["realisiert"], r["nach_tfs"]), (1000, 700))
        self.assertAlmostEqual(D.steuern([self.t("aktie", 1000)], {"freibetrag": 400})["steuer"], 600 * 0.26375)

    def test_kirchensteuer(self):
        # Abgeltungsteuer = e / (4 + k), k = 0,09; KiSt 9 % und Soli 5,5 % darauf
        kest = 1000 / 4.09
        self.assertAlmostEqual(D.steuern([self.t("aktie", 1000)], {"kirchensteuer": 9})["steuer"],
                               kest * (1 + 0.055 + 0.09))

    def test_verlusttoepfe(self):
        # Aktienverlust verrechnet sich nicht mit ETF-Gewinn
        self.assertAlmostEqual(D.steuern([self.t("aktie", -500), self.t("etf", 1000, 30)])["steuerbar"], 700)
        # sonstiger Verlust verrechnet sich mit Aktiengewinn
        self.assertAlmostEqual(D.steuern([self.t("aktie", 1000), self.t("wikifolio", -400)])["steuerbar"], 600)
        self.assertAlmostEqual(D.steuern([self.t("aktie", 1000)], {"verlust_aktien": 1500})["steuer"], 0.0)
        r = D.steuern([{"aktion": "Verkauf", "art": "aktie", "gewinn": None}])
        self.assertTrue(any("ohne Einstand" in x for x in r["luecken"]))


class Simulator(unittest.TestCase):
    def setUp(self):
        self.ist = [aktie("A", 5000, 70, einstand=4000), pos("E ETF", 5000, "etf")]

    def test_echtes_depot_bleibt_unveraendert(self):
        vorher = copy.deepcopy(self.ist)
        D.simulieren(self.ist, {"A": 0}, cash=100, zusatz=1000, gebuehr_fix=1, gebuehr_pct=0.25)
        self.assertEqual([(p["stueck"], p["wert"], p["einstand"]) for p in self.ist],
                         [(p["stueck"], p["wert"], p["einstand"]) for p in vorher])

    def test_verkauf_gebuehr_steuer_liquiditaet(self):
        s = D.simulieren(self.ist, {"A": 25}, cash=100, gebuehr_fix=5, gebuehr_pct=0.1)   # 25 von 50 Stueck
        t = s["trades"][0]
        self.assertEqual((t["aktion"], t["stueck"], t["betrag"]), ("Verkauf", 25.0, 2500.0))
        self.assertAlmostEqual(t["gebuehr"], 7.5)
        self.assertAlmostEqual(t["gewinn"], 2500 - 2000 - 7.5)
        self.assertAlmostEqual(s["steuern"]["steuer"], 492.5 * 0.26375)
        self.assertAlmostEqual(s["cash_nachher"], 100 + 2500 - 7.5 - 492.5 * 0.26375)
        a = next(p for p in s["soll"] if p["name"] == "A")
        self.assertAlmostEqual(a["einstand"], 2000)

    def test_kauf_ueber_liquiditaet_warnt(self):
        s = D.simulieren(self.ist, {"A": 100}, cash=0)
        self.assertTrue(s["warnungen"])
        s = D.simulieren(self.ist, {"A": 100}, cash=0, zusatz=5000)
        self.assertFalse(s["warnungen"])

    def test_neue_position_und_zielgewichte(self):
        n = D.neue_position("Neu ETF", "etf", 50.0, 10)
        s = D.simulieren(self.ist + [n], {D.schluessel(n): 10}, cash=500)
        self.assertEqual(s["trades"][0]["aktion"], "Kauf")
        self.assertAlmostEqual(s["cash_nachher"], 0.0)
        st = D.stueck_fuer_zielgewichte(self.ist, {"A": 30.0}, 10000)
        self.assertEqual(st["A"], 30)

    def test_vergleich_und_urteil(self):
        k1 = D.kennzahlen(self.ist)
        s = D.simulieren(self.ist, {"A": 0}, cash=0)
        k2 = D.kennzahlen(s["soll"], s["cash_nachher"])
        z = {r["kennzahl"]: r for r in D.vergleich(k1, k2)}
        self.assertEqual(z["Depotwert"]["urteil"], "neutral")
        self.assertAlmostEqual(z["Liquidität"]["nachher"], s["cash_nachher"])
        b = D.simulation_bewerten(k1, k2, s)
        self.assertEqual(len(b["antworten"]), 7)
        self.assertIn(b["urteil"], ("besser", "ähnlich", "schlechter"))
        self.assertIn(b["urteil"], b["fazit"])


class Optimierer(unittest.TestCase):
    def test_verbessert_oder_schlaegt_nichts_vor(self):
        ps = [aktie("Gross", 7000, 75), aktie("Schwach", 1500, 25, bew="teuer"), pos("E ETF", 1500, "etf"),
              aktie("Gut", 1000, 85)]
        k = D.kennzahlen(ps, 0)
        o = D.optimieren(ps, k)
        self.assertGreater(o["score_nachher"], o["score_vorher"])
        namen = {m["name"]: m for m in o["massnahmen"]}
        self.assertEqual(namen["Gross"]["aktion"], "Verkaufen")
        self.assertFalse(any(m["aktion"] == "Kaufen" and m["name"] == "Schwach" for m in o["massnahmen"]))
        self.assertTrue(all(float(m["stueck"]).is_integer() for m in o["massnahmen"]))
        self.assertEqual(D.kennzahlen(ps, 0)["gesamt"], k["gesamt"])            # Eingabe unveraendert

    def test_ausgewogenes_depot_bleibt(self):
        ps = [aktie(f"A{i}", 1000, 70) for i in range(10)]
        o = D.optimieren(ps, D.kennzahlen(ps, 0), {"risiko": "offensiv"})
        self.assertTrue(o["score_nachher"] >= o["score_vorher"])

    def test_modellrechnung(self):
        k = D.kennzahlen([pos("E ETF", 10000, "etf")])
        m = D.modell_entwicklung(k, 10, 0)
        self.assertAlmostEqual(m["p50"], 10000 * 1.065 ** 10)
        self.assertLess(m["p10"], m["p50"])
        self.assertGreater(m["p90"], m["p50"])


class Assistent(unittest.TestCase):
    def setUp(self):
        self.ps = [aktie("Gross", 7000, 60), aktie("Klein", 3000, 80, div=3.0)]
        self.ps[1]["div"] = 3.0
        self.k = D.kennzahlen(self.ps)
        self.e = {D.schluessel(p): D.empfehlung(p, self.k) for p in self.ps}

    def frage(self, f):
        return D.assistent(f, self.ps, self.k, self.e)

    def test_absichten(self):
        self.assertEqual(self.frage("Welche Positionen sind am riskantesten?")["art"], "risiko")
        self.assertIn("Gross", self.frage("Welche Positionen sind am riskantesten?")["antwort"].split("\n")[1])
        r = self.frage("Was passiert, wenn ich meine größte Position halbiere?")
        self.assertEqual(r["simulation"]["aenderungen"], {"GROSS": 35})
        r = self.frage("Wie würde sich mein Depot verändern, wenn ich 10.000 € zusätzlich investiere?")
        self.assertEqual(r["simulation"]["zusatz"], 10000.0)
        self.assertEqual(self.frage("Welche Dividendenstrategie würde zu mir passen?")["simulation"]["szenario"],
                         "dividende")
        self.assertEqual(self.frage("Wie könnte ich mein Depot defensiver aufstellen?")["simulation"]["szenario"],
                         "defensiv")
        r = self.frage("Wie wird das Wetter morgen?")
        self.assertEqual(r["art"], "uebersicht")                 # nie leer: Bewertungen aller Positionen
        self.assertIn("Gross", r["antwort"])
        self.assertEqual(self.frage("Wie ist Klein bewertet?")["art"], "wert")

    def test_alternativen_aus_top500(self):
        zeilen = {"AAA": {"name": "Alpha AG", "gesamt": 88, "klasse": "prio", "roic": 20, "div": 1.0},
                  "BBB": {"name": "Beta AG", "gesamt": 75, "klasse": "beobachten", "div": 4.0},
                  "CCC": {"name": "Gamma AG", "gesamt": 30, "klasse": "nicht"}}
        kat = [{"felder": ["typ", "name", "kennung", "isin", "1J", "3J", "5J", "vola", "maxdd", "jahre"],
                "zeilen": [["etf", "Welt ETF", "W1", "IE0000000001", 15, 40, 70, 13, -25, 12]]}]
        rang = D.ranglisten(zeilen, {"DE000ALPHA01": "AAA"}, kat)
        self.assertEqual([e["name"] for e in rang["aktie"]], ["Alpha AG", "Beta AG", "Gamma AG"])
        self.assertEqual(rang["aktie"][0]["isin"], "DE000ALPHA01")
        self.assertEqual(rang["etf"][0]["name"], "Welt ETF")
        alt = D.alternativen(rang, "aktie", self.ps, 5)
        self.assertEqual([e["name"] for e in alt], ["Alpha AG", "Beta AG"])     # "nicht" ausgeschlossen
        self.assertEqual(D.alternativen(rang, "aktie", self.ps, 5, "dividende")[0]["name"], "Beta AG")
        r = D.assistent("Welche besseren Aktien gibt es als Alternative?", self.ps, self.k, self.e, None, rang)
        self.assertEqual(r["art"], "alternativen")
        self.assertEqual(r["kandidaten"][0]["name"], "Alpha AG")
        r = D.assistent("Wie ist Alpha AG bewertet?", self.ps, self.k, self.e, None, rang)
        self.assertEqual((r["art"], r["kandidaten"][0]["name"]), ("wert", "Alpha AG"))
        im_depot = self.ps + [dict(self.ps[0], name="Alpha AG", isin="DE000ALPHA01", wkn="")]
        self.assertNotIn("Alpha AG", [e["name"] for e in D.alternativen(rang, "aktie", im_depot, 5)])


class Gesamtanalyse(unittest.TestCase):
    def test_sieben_antworten_und_plan(self):
        ps = [aktie("Gross", 8000, 60), aktie("Schwach", 1000, 20, bew="teuer"), aktie("Gut", 1000, 85)]
        k = D.kennzahlen(ps)
        e = {D.schluessel(p): D.empfehlung(p, k) for p in ps}
        g = D.gesamtanalyse(ps, k, e, D.warnungen(ps, k))
        self.assertEqual(len(g["antworten"]), 7)
        self.assertEqual(g["aktionsplan"][0]["prio"], "hoch")
        self.assertEqual([a["prio"] for a in g["aktionsplan"]],
                         sorted([a["prio"] for a in g["aktionsplan"]], key=D.PRIO.get))


class Import(unittest.TestCase):
    def test_spalten_tolerant(self):
        z = [{"Bezeichnung": "MSCI World", "ISIN": "ie00b4l5y983", "Stück": "10", "Kaufkurs": "85,50",
              "Kaufdatum": "15.03.2024"},
             {"Name": "Allianz", "WKN": "840400", "Anzahl": 2, "Einstand": "1.000,00"},
             {"Name": "Fehler", "ISIN": "X", "Stueck": "0"}, {"Name": "", "ISIN": ""}]
        aus, fehler = D.import_zeilen(z)
        self.assertEqual(len(aus), 2)
        self.assertEqual((aus[0]["kennung"], aus[0]["stueck"], aus[0]["kaufkurs"]), ("IE00B4L5Y983", 10.0, 85.5))
        self.assertAlmostEqual(aus[0]["einstand"], 855.0)
        self.assertEqual(str(aus[0]["kaufdatum"]), "2024-03-15")
        self.assertEqual((aus[1]["kaufkurs"], aus[1]["einstand"]), (500.0, 1000.0))
        self.assertEqual(len(fehler), 1)

    def test_export(self):
        p = aktie("A", 1000, 70)
        k = D.kennzahlen([p])
        z = D.export_tabelle([p], k, {"A": D.empfehlung(p, k)})
        self.assertEqual(z[0]["Gewicht %"], 100.0)
        self.assertTrue(z[0]["Empfehlung"])

    def test_pdf(self):
        import depot_analyse_pdf as PDF
        b = PDF.bericht("Depot-Analyse", "Stand −1 → 2", [("Wert", "1.000 €")], [["A", "Aktie", "100 %", "70",
                        "Halten", "niedrig"]], ["Hinweis ≥ 5"], [("Frage?", "Antwort")], [("hoch", "M", "W")],
                        {"trades": [["Verkauf", "A", "1", "100 €", "1 €"]],
                         "vergleich": [["Score", "70", "72", "+2", "besser"]], "bewertung": [("F", "A")],
                         "fazit": "besser"}, ["Annahme"])
        self.assertTrue(b.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
