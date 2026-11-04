"""Wiki-Idee: Rangliste aus Score + Investoren-Checks, Auswahl mit Puffer und Streuung, Stueckzahlen,
Umschichtung, Mail - mit synthetischen Werten."""
import re
import unittest

import wiki_idee as WI


def aktie(i, score, kurs=50.0, sektor=None, fv=None, inv=None, qual=None, p6=None):
    """score = Qualitaets-Score (info.gesamt); qual ueberschreibt ihn (Test Qualitaet x Kurs)."""
    e = {"id": f"A{i}", "art": "aktie", "name": f"Aktie {i:03d}", "ticker": f"T{i}", "wkn": f"W{i}", "isin": "",
         "sektor": sektor or f"S{i % 12}", "kurs": kurs, "k": {"p6": p6},
         "info": {"gesamt": score if qual is None else qual}}
    return e, {"fazit": None}


def etf(i, score, name=None, kurs=80.0, jahre=8.0):
    e = {"id": f"E{i}", "art": "etf", "name": name or f"ETF {i:03d}", "ticker": "", "wkn": f"EW{i}", "isin": "",
         "kurs": kurs, "k": {"jahre": jahre}, "info": {}}
    return e, {"gesamt": score}


class Rangliste(unittest.TestCase):
    def test_mischung_und_neutral(self):
        eintraege = [aktie(1, 80), aktie(2, 80), aktie(3, 80)]
        inv = {"T1": {"score": 90, "fv": 40.0}, "T2": {"score": 10, "fv": -20.0}}
        liste, aus = WI.aktien_rangliste(eintraege, inv)
        self.assertEqual([w["id"] for w in liste], ["A1", "A3", "A2"])     # A3 ohne Investoren-Daten = neutral
        a1 = liste[0]
        self.assertAlmostEqual(a1["mix"], (40 * 80 + 30 * 90 + 20 * 100 + 10 * 50) / 100, places=1)
        self.assertEqual(aus, [])

    def test_warnsignale_ausgeschlossen(self):
        eintraege = [aktie(1, 90), aktie(2, 90), aktie(3, 90), aktie(4, 90)]
        inv = {"T1": {"c": {"altman": [0, 0, 1]}}, "T2": {"c": {"beneish": [0, 0, 1]}},
               "T3": {"c": {"red_flags": [33, 2, 6]}}, "T4": {"c": {"altman": [50, 0, 1], "red_flags": [83, 5, 6]}}}
        liste, aus = WI.aktien_rangliste(eintraege, inv)
        self.assertEqual([w["id"] for w in liste], ["A4"])
        self.assertEqual(len(aus), 3)

    def test_ohne_score_oder_kurs_fehlt(self):
        liste, _ = WI.aktien_rangliste([aktie(1, None), aktie(2, 70, kurs=None), aktie(3, 70)])
        self.assertEqual([w["id"] for w in liste], ["A3"])

    def test_qualitaet_x_kurs(self):
        # gleiche Scores; A1 hohe Qualitaet + schwacher Kurs schlaegt A2 (niedrige Qualitaet, starker Kurs)
        liste, _ = WI.aktien_rangliste([aktie(1, 60, qual=90, p6=-10), aktie(2, 60, qual=20, p6=30)])
        self.assertEqual(liste[0]["id"], "A1")
        self.assertEqual(liste[0]["teile"]["qualitaet_kurs"], 100.0)

    def test_nur_eur_kurse(self):
        e1, b1 = aktie(1, 80, kurs=120.0)
        e1["waehrung"] = "USD"
        e2, b2 = aktie(2, 70, kurs=50.0)
        e2["waehrung"] = "USD"
        liste, _ = WI.aktien_rangliste([(e1, b1), (e2, b2)], eur_kurse={"W1": 110.5})
        self.assertEqual([(w["id"], w["kurs"]) for w in liste], [("A1", 110.5)])    # A2 ohne EUR-Kurs fehlt

    def test_etf_score_aus_ranglisten(self):
        e1, e2, e3 = etf(1, 0)[0], etf(2, 0)[0], etf(3, 0)[0]
        score = {"EW1": {"score": 60, "jahre": 9, "einordnung": "beobachten"},
                 "EW2": {"score": 85, "jahre": 2, "einordnung": "prio"}}             # EW2 zu kurz, EW3 ohne Score
        liste = WI.etf_rangliste([(e1, {}), (e2, {}), (e3, {})], etf_score=score)
        self.assertEqual([(w["id"], w["mix"], w["klasse"]) for w in liste], [("E1", 60.0, "beobachten")])

    def test_etf_filter(self):
        hebel = re.compile(r"leverag|short|\b[2-9]x\b", re.I)
        liste = WI.etf_rangliste([etf(1, 70), etf(2, 90, "Daily 3x Long Nasdaq"), etf(3, 80, jahre=1.0),
                                  etf(4, 60)], hebel)
        self.assertEqual([w["id"] for w in liste], ["E1", "E4"])


def rangliste(n, art="aktie", gruppen=10, kurs=50.0):
    return [{"id": f"{art[0].upper()}{i}", "art": art, "name": f"{art} {i}", "wkn": f"K{i}", "isin": "",
             "ticker": "", "gruppe": f"G{i % gruppen}", "kurs": kurs, "mix": 100 - i * 0.5, "rang": i}
            for i in range(1, n + 1)]


class Auswahl(unittest.TestCase):
    def test_puffer_haelt_knapp_abgerutschte(self):
        r = rangliste(80, gruppen=80)
        ziel = WI.auswahl(r, 50, 60, gehalten={"A55", "A70"}, max_je_gruppe=10)
        ids = {w["id"] for w in ziel}
        self.assertEqual(len(ziel), 50)
        self.assertIn("A55", ids)            # Rang 55 < Puffer 60: bleibt
        self.assertNotIn("A70", ids)         # Rang 70: fliegt raus
        self.assertNotIn("A50", ids)         # dafuer rueckt Rang 50 nicht nach

    def test_streuung_und_budget(self):
        r = rangliste(100, gruppen=2)
        ziel = WI.auswahl(r, 50, 60, (), max_je_gruppe=10)
        self.assertEqual(len(ziel), 50)      # 2 Gruppen x 10, Rest aufgefuellt
        self.assertEqual([w["rang"] for w in ziel[:20]], list(range(1, 21)))
        teuer = rangliste(5, kurs=5000.0) + [dict(w, id=f"B{w['rang']}", rang=w["rang"] + 5)
                                             for w in rangliste(5)]
        ziel = WI.auswahl(teuer, 3, 3, (), 10, budget=1400.0)
        self.assertTrue(all(w["kurs"] <= 1400 for w in ziel))


class Depot(unittest.TestCase):
    def test_stueckzahlen_70_30(self):
        a, e = rangliste(50), rangliste(20, "etf", kurs=100.0)
        pos, kasse = WI.stueckzahlen(a, e, 100_000)
        self.assertEqual(len(pos), 70)
        self.assertEqual(pos["A1"]["stueck"], 28)          # 1.400 € / 50 €
        self.assertEqual(pos["E1"]["stueck"], 15)          # 1.500 € / 100 €
        wert_a = sum(p["wert"] for p in pos.values() if p["art"] == "aktie")
        self.assertAlmostEqual(wert_a, 70_000, delta=50 * 50)
        self.assertAlmostEqual(sum(p["wert"] for p in pos.values()) + kasse, 100_000, places=2)
        self.assertGreaterEqual(kasse, 0)

    def test_restkasse_wird_verteilt(self):
        import random
        rnd = random.Random(5)
        a = [dict(w, kurs=round(rnd.uniform(8, 1300), 2)) for w in rangliste(50)]
        e = [dict(w, kurs=round(rnd.uniform(20, 600), 2)) for w in rangliste(20, "etf")]
        pos, kasse = WI.stueckzahlen(a, e, 100_000)
        self.assertGreaterEqual(kasse, 0)
        self.assertLess(kasse, 1_000)                       # vorher bis zu 15 % Kasse
        self.assertEqual(len(pos), 70)
        self.assertTrue(all(p["wert"] <= max(p["ziel"] * 1.1, p["ziel"] + p["kurs"]) + 0.01 for p in pos.values()))

    def test_start_und_umschichtung(self):
        a, e = rangliste(80, gruppen=80), rangliste(30, "etf", gruppen=30, kurs=100.0)
        d1, auf1 = WI.umschichten({}, [dict(w) for w in a], [dict(w) for w in e], {}, "2026-11-06")
        self.assertEqual(d1["start"], "2026-11-06")
        self.assertEqual(d1["wert"], 100_000)
        self.assertEqual(len(auf1), 70)
        self.assertTrue(all(x["aktion"] == "Neu" for x in auf1))
        # eine Woche spaeter: A1 verdoppelt sich, A2 faellt aus der Rangliste (Puffer), A61 neu stark
        a2 = [dict(w) for w in a if w["id"] != "A2"]
        preise = {"A1": 100.0}
        d2, auf2 = WI.umschichten(d1, a2, [dict(w) for w in e], preise, "2026-11-13")
        self.assertAlmostEqual(d2["wert"], 100_000 + d1["positionen"]["A1"]["stueck"] * 50.0, places=2)
        aktionen = {x["id"]: x["aktion"] for x in auf2}
        self.assertEqual(aktionen.get("A2"), "Raus")
        self.assertEqual(aktionen.get("A1"), "Verkauf")      # zurueck aufs Zielgewicht
        self.assertEqual(aktionen.get("A51"), "Neu")
        self.assertEqual([h[0] for h in d2["historie"]], ["2026-11-06", "2026-11-13"])
        self.assertEqual(auf2[0]["aktion"], "Raus")           # Verkaeufe zuerst
        # gleicher Tag nochmal: Historie bekommt keinen zweiten Punkt
        d3, _ = WI.umschichten(d2, a2, [dict(w) for w in e], preise, "2026-11-13")
        self.assertEqual(len(d3["historie"]), 2)


class Ablauf(unittest.TestCase):
    def test_ranglisten_und_kandidaten(self):
        bewertet = [aktie(i, 90 - i) for i in range(1, 6)] + [etf(i, 80 - i) for i in range(1, 4)]
        a, aus, e = WI.ranglisten(bewertet, {"T2": {"c": {"altman": [0, 0, 1]}}})
        self.assertEqual([w["id"] for w in a], ["A1", "A3", "A4", "A5"])
        self.assertEqual(len(aus), 1)
        self.assertEqual([w["id"] for w in e], ["E1", "E2", "E3"])
        k = WI.kurs_kandidaten({"positionen": {"X9": {"id": "X9"}}}, a, e, n_aktien=2, n_etf=1)
        self.assertEqual([w["id"] for w in k], ["X9", "A1", "A3", "E1"])

    def test_betraege(self):
        z, s = WI.betraege([{"aktion": "Raus", "stueck": 2, "kurs": 10.0}, {"aktion": "Neu", "stueck": 3, "kurs": 5.0}])
        self.assertEqual([x["betrag"] for x in z], [-20.0, 15.0])
        self.assertEqual(s, {"kauf": 15.0, "verkauf": 20.0})

    def test_uebernehmen_und_rueckgaengig(self):
        a, e = rangliste(60, gruppen=60), rangliste(25, "etf", gruppen=25, kurs=100.0)
        d1, _ = WI.umschichten({}, a, e, {}, "2026-11-03", zeitpunkt="2026-11-03T10:00")
        gespeichert = WI.uebernehmen({}, d1, WI.signatur({}))
        self.assertEqual(gespeichert["vorher"], {})
        self.assertEqual(WI.rueckgaengig(gespeichert), {})
        d2, _ = WI.umschichten(gespeichert, a, e, {"A1": 99.0}, "2026-11-05", zeitpunkt="2026-11-05T15:00")
        basis = WI.signatur(gespeichert)
        neu = WI.uebernehmen(gespeichert, d2, basis)
        self.assertEqual(neu["vorher"]["stand"], "2026-11-03")
        self.assertNotIn("vorher", neu["vorher"])                       # keine Kette alter Staende
        self.assertIsNone(WI.uebernehmen(neu, d2, basis))                # inzwischen geaendert -> abgelehnt
        self.assertEqual(WI.rueckgaengig(neu)["stand"], "2026-11-03")
        self.assertIsNone(WI.rueckgaengig({"stand": "x"}))

class EchteUmsetzung(unittest.TestCase):
    def test_start_mit_abweichungen(self):
        a, e = rangliste(60, gruppen=60), rangliste(25, "etf", gruppen=25, kurs=100.0)
        neu, liste = WI.umschichten({}, a, e, {}, "2026-11-03")
        ist = {"A1": {"stueck": 0}, "A2": {"stueck": 20, "kurs": 51.0}}          # A1 nicht gekauft, A2 weniger
        d = WI.ausfuehren({}, neu, ist)
        self.assertNotIn("A1", d["positionen"])
        self.assertEqual((d["positionen"]["A2"]["stueck"], d["positionen"]["A2"]["kurs"]), (20, 51.0))
        investiert = sum(p["stueck"] * p["kurs"] for p in d["positionen"].values())
        self.assertAlmostEqual(d["kasse"], 100_000 - investiert, places=2)
        self.assertAlmostEqual(d["wert"], 100_000, places=2)
        lauf = d["laeufe"][-1]["auftraege"]
        self.assertEqual(len(lauf), len(liste) - 1)                                   # A1 nicht im Protokoll
        a2 = next(x for x in lauf if x["id"] == "A2")
        self.assertEqual((a2["stueck"], a2["geplant"], a2["kurs"]), (20, 28, 51.0))

    def test_verkauf_begrenzt_und_kasse(self):
        alt = {"kasse": 100.0, "positionen": {"A1": {"id": "A1", "art": "aktie", "name": "x", "stueck": 5,
                                                     "kurs": 10.0}}, "laeufe": []}
        neu = {"positionen": {}, "laeufe": [{"auftraege": [{"aktion": "Raus", "id": "A1", "name": "x", "art": "aktie",
                                                            "stueck": 5, "kurs": 12.0, "vorher": 5, "nachher": 0}]}]}
        d = WI.ausfuehren(alt, neu, {"A1": {"stueck": 9, "kurs": 12.5}})              # 9 > Bestand 5
        self.assertEqual(d["positionen"], {})
        self.assertAlmostEqual(d["kasse"], 100 + 5 * 12.5)

    def test_korrigieren(self):
        a, e = rangliste(60, gruppen=60), rangliste(25, "etf", gruppen=25, kurs=100.0)
        d, _ = WI.umschichten({}, a, e, {}, "2026-11-03")
        zeilen = [{"id": i, "stueck": p["stueck"], "kurs": p["kurs"]} for i, p in d["positionen"].items()
                  if i not in ("A1",)]
        zeilen[0]["stueck"] += 3
        zeilen.append({"id": None, "name": "Neue AG", "wkn": "neu123", "art": "aktie", "stueck": 4, "kurs": 25.0})
        k, aend = WI.korrigieren(d, zeilen, 500.0, "2026-11-04")
        self.assertNotIn("A1", k["positionen"])
        self.assertIn("H:NEU123", k["positionen"])
        self.assertEqual(k["kasse"], 500.0)
        self.assertAlmostEqual(k["wert"], sum(p["stueck"] * p["kurs"] for p in k["positionen"].values()) + 500.0)
        self.assertEqual({x["aktion"] for x in aend}, {"Korrektur"})
        self.assertEqual(len(aend), 4)                                    # +3 Stueck, A1 weg, neu, Kasse
        self.assertTrue(k["laeufe"][-1]["korrektur"])
        _, s = WI.betraege(aend)
        self.assertEqual(s, {"kauf": 0.0, "verkauf": 0.0})


class Quellen(unittest.TestCase):
    def test_in_eur(self):
        fx = {"USD": 1.10, "GBP": 0.85}
        self.assertAlmostEqual(WI.in_eur(110, "USD", fx), 100.0)
        self.assertAlmostEqual(WI.in_eur(8500, "GBp", fx), 100.0)       # Pence
        self.assertEqual(WI.in_eur(50, "EUR", fx), 50)
        self.assertIsNone(WI.in_eur(50, "JPY", fx))                     # ohne Wechselkurs kein Wert

    def test_aktien_und_etfs_aus_ranglisten(self):
        alle = [{"felder": ["s", "name", "br", "kurs", "kwae", "gesamt", "klasse", "p6"],
                 "zeilen": [["NVDA", "NVIDIA", "Technologie", 220.0, "USD", 88, "prio", 12.0],
                            ["XX", "Ohne Score", "Industrie", 10.0, "EUR", None, None, 1.0]]}]
        a = WI.aktien_aus_qualitaet(alle, {"US67066G1040": "NVDA"}, {"USD": 1.1})
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["isin"], a[0]["kurs"], a[0]["info"]["gesamt"]), ("US67066G1040", 200.0, 88.0))
        kat = [{"felder": ["typ", "name", "kennung", "isin", "kurs", "jahre"],
                "zeilen": [["etf", "iShares Core MSCI World", "A0RPWH", "IE00B4L5Y983", 100.0, 15],
                           ["aktie", "x", "1", "", 5.0, 3], ["etf", "doppelt", "A0RPWH", "IE00B4L5Y983", 1.0, 1]]}]
        e = WI.etfs_aus_katalog(kat)
        self.assertEqual([(x["id"], x["wkn"], x["kurs"]) for x in e], [("IE00B4L5Y983", "A0RPWH", 100.0)])
        liste, _ = WI.aktien_rangliste([(x, {}) for x in a])
        self.assertEqual(liste[0]["teile"]["score"], 88.0)


class Handelbar(unittest.TestCase):
    def test_nur_mit_isin_und_ls(self):
        a = [{"isin": "US1", "ticker": "A"}, {"isin": "", "ticker": "B"}, {"isin": "US3", "ticker": "C"}]
        self.assertEqual(WI.handelbar(a), ([a[0], a[2]], False))
        self.assertEqual(WI.handelbar(a, {"US1": 5}, mindestens=1), ([a[0]], True))
        self.assertEqual(WI.handelbar(a, {"US1": 5}, mindestens=2), ([a[0], a[2]], False))   # zu wenige bei L&S


class Charts(unittest.TestCase):
    def depot(self, scores):
        return {"positionen": {i: {"id": i, "art": "aktie", "name": i, "mix": s, "rang": n}
                               for n, (i, s) in enumerate(scores.items(), 1)}}

    def test_hitparade(self):
        alt = self.depot({"A": 90, "B": 80, "C": 70, "D": 60})
        neu = self.depot({"B": 95, "A": 85, "C": 70, "E": 65})
        stat = WI.charts_fortschreiben({"E": {"listen": 2, "best": 1}}, alt)
        z, raus = WI.hitparade(neu, alt, "aktie", stat)
        self.assertEqual([(r["p"]["id"], r["platz"], r["vorher"], r["bewegung"], r["delta"]) for r in z],
                         [("B", 1, 2, "hoch", 1), ("A", 2, 1, "runter", -1), ("C", 3, 3, "gleich", 0),
                          ("E", 4, None, "wieder", None)])
        self.assertEqual([(r["p"]["id"], r["vorher"]) for r in raus], [("D", 4)])
        self.assertEqual((z[0]["listen"], z[0]["best"]), (2, 1))          # B: 2. Liste, bester Platz 1
        self.assertEqual(z[3]["best"], 1)                                  # E: frueher schon auf Platz 1
        z2, _ = WI.hitparade(neu, {}, "aktie")
        self.assertTrue(all(r["bewegung"] == "neu" for r in z2))


class Begruendung(unittest.TestCase):
    def test_aktie_volle_begruendung(self):
        alle = [{"felder": ["s", "name", "br", "kurs", "kwae", "gesamt", "klasse", "p6", "pt", "g_ums", "roic", "fkgv",
                            "moat", "mgmt", "bew"],
                 "zeilen": [["NVDA", "NVIDIA", "Technologie", 110.0, "USD", 88, "prio", 12.0,
                             [19, 14, 13, 9, 8, 9, 3, 4], 45.2, 60.1, 28.4, "stark", "gut", "teuer"]] +
                           [[f"X{i}", f"Firma {i}", "Industrie", 10.0, "EUR", 50 + i, None, 0.0] + [None] * 7
                            for i in range(9)]}]
        aktien = WI.aktien_aus_qualitaet(alle, {"US67066G1040": "NVDA"}, {"USD": 1.1})
        inv = {"NVDA": {"note": "B", "score": 74, "kaufen": 7, "inv": 12, "fv": 24.0,
                        "c": {"buffett": [90, 5, 6], "lynch": [80, 4, 5], "graham": [20, 1, 6]}}}
        liste, _ = WI.aktien_rangliste([(e, {}) for e in aktien], inv)
        nv = next(w for w in liste if w["id"] == "NVDA")
        ziel = WI.auswahl(liste, 5, 6, (), 10)
        pos, _ = WI.stueckzahlen(ziel, [], 10_000)
        b = WI.begruendung(pos["NVDA"], {"buffett": "Warren Buffett", "lynch": "Peter Lynch", "graham": "Benjamin Graham"})
        titel = [t for t, _ in b["abschnitte"]]
        self.assertEqual(titel[:3], ["Platzierung", "Warum ausgewählt", "So setzt sich der Score zusammen"])
        self.assertIn("Qualitäts-Score je Bereich", titel)
        self.assertIn("Börsenprofis (Investoren-Checks)", titel)
        text = " ".join(z for _, zs in b["abschnitte"] for z in zs)
        self.assertIn("Platz 1 von 10", text)
        self.assertIn("Warren Buffett (90)", text)
        self.assertNotIn("Benjamin Graham", text)                      # Score 20 -> kauft nicht
        self.assertIn("Qualität 19/20", text)
        self.assertIn("+24,0 %", text)
        self.assertIn("Burggraben stark", text)
        self.assertTrue(b["kurz"].startswith("Platz 1 von 10"))
        self.assertIn("Bewertung 3/15", b["schwaechen"])
        self.assertEqual(nv["detail"]["inv"]["c"]["buffett"], 90)

    def test_puffer_und_etf(self):
        r = [dict(w, detail={}, von_gesamt=80) for w in rangliste(80, gruppen=80)]
        ziel = WI.auswahl(r, 50, 60, {"A55"}, 10)
        a55 = next(w for w in ziel if w["id"] == "A55")
        self.assertEqual(a55["auswahl"], "puffer")
        self.assertIn("Puffer", " ".join(z for _, zs in WI.begruendung(a55)["abschnitte"] for z in zs))
        e = {"art": "etf", "rang": 2, "von_gesamt": 400, "mix": 81, "auswahl": "top",
             "detail": {"etf": {"rendite": 11.2, "rendite_jahre": 10, "rr": 0.74, "dd": 33, "vola": 15, "jahre": 14,
                                "einordnung": "prio"}, "mm": {"region": "Welt", "themen": ["Breiter Markt"]}}}
        b = WI.begruendung(e)
        self.assertIn("+11,2 % p. a.", b["kurz"])
        self.assertIn("ETF-Score: hohe Analysepriorität", b["abschnitte"][2][1])


if __name__ == "__main__":
    unittest.main()
