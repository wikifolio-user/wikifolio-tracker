"""Wiki-Idee: Rangliste aus Score + Investoren-Checks, Auswahl mit Puffer und Streuung, Stueckzahlen,
Umschichtung, Mail - mit synthetischen Werten."""
import re
import unittest

import wiki_idee as WI


def aktie(i, score, kurs=50.0, sektor=None, fv=None, inv=None, qual=None, p6=None):
    e = {"id": f"A{i}", "art": "aktie", "name": f"Aktie {i:03d}", "ticker": f"T{i}", "wkn": f"W{i}", "isin": "",
         "sektor": sektor or f"S{i % 12}", "kurs": kurs, "k": {"p6": p6}, "info": {"gesamt": qual}}
    return e, {"gesamt": score, "fazit": None}


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

    def test_mail(self):
        a, e = rangliste(60, gruppen=60), rangliste(25, "etf", gruppen=25, kurs=100.0)
        d, auf = WI.umschichten({}, a, e, {}, "2026-11-06")
        betreff, text, html = WI.mail_text(d, auf, "https://beispiel")
        self.assertIn("70 Anpassungen", betreff)
        self.assertIn("100.000 €", betreff)
        self.assertIn("Neu", text)
        self.assertIn("<table", html)
        self.assertIn("keine Anlageberatung", text)


class Agent(unittest.TestCase):
    """Ein kompletter Lauf mit synthetischen Daten - nichts wird wirklich gelesen, geschrieben oder gemailt."""
    def test_lauf_und_wiederholung_am_selben_tag(self):
        import os
        import wiki_idee_agent as AG
        u = [aktie(i, 90 - i * 0.3, sektor=f"S{i % 15}")[0] for i in range(1, 90)] + \
            [etf(i, 90 - i)[0] for i in range(1, 35)]
        speicher = {}
        alt = {}
        ersatz = {
            (AG.IA, "universum_laden"): lambda: (u, {}),
            (AG.IA, "lade_teile"): lambda: ({}, {}),
            (AG.SC, "verteilungen"): lambda u_: {},
            (AG.SC, "bewerten"): lambda e, v: {"gesamt": 90 - int(e["id"][1:]) * (0.3 if e["art"] == "aktie" else 1),
                                                "fazit": None},
            (AG.T, "lade_state"): lambda p, s: s,
            (AG.T, "lade_state_geprueft"): lambda p, s, versuche=2: (speicher.get(p, s), "ok"),
            (AG.T, "speichere_state"): lambda p, d, m: speicher.__setitem__(p, d) or True,
        }
        for (mod, name), f in ersatz.items():
            alt[(mod, name)] = getattr(mod, name)
            setattr(mod, name, f)
        for k in ("MAIL_ABSENDER", "MAIL_APP_PASSWORT"):
            os.environ.pop(k, None)
        try:
            self.assertEqual(AG.main(), 0)
            d1 = speicher[AG.STATE_DEPOT]
            self.assertEqual(sum(1 for p in d1["positionen"].values() if p["art"] == "aktie"), 50)
            self.assertEqual(sum(1 for p in d1["positionen"].values() if p["art"] == "etf"), 20)
            self.assertEqual(d1["vorher"], {})
            self.assertEqual(AG.main(), 0)                       # zweiter Lauf am selben Tag
            d2 = speicher[AG.STATE_DEPOT]
            self.assertEqual(len(d2["historie"]), 1)
            self.assertEqual(len(d2["laeufe"]), 1)
            self.assertEqual(len(d2["laeufe"][0]["auftraege"]), 70)   # wieder ab dem Stand vor dem ersten Lauf
            self.assertEqual(len(speicher[AG.STATE_RANG]["aktien"]), 89)
        finally:
            for (mod, name), f in alt.items():
                setattr(mod, name, f)


if __name__ == "__main__":
    unittest.main()
