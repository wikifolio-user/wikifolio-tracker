"""Regressionstests (Etappe 1): friert die Ergebnisse des KLASSISCHEN Bewertungssystems an festen Testfaellen ein.

Abgedeckt: Qualitaets-Score (qualitaet_agent.bewerte: 8 Bereiche, Red Flags, Einordnung), alle Investoren-Checks
und der Legenden-Konsens (investor_checks), fairer Wert (fairer_wert.uebersicht), ETF-/wikifolio-Score
(klassen_score), Gesamt-Score der Seite "Bewertung" (scoring.bewerten) und die Auswahl des KI_Invest_System
(wiki_idee). Weicht ein Ergebnis ab, wurde das klassische Modell veraendert - das darf nur bewusst geschehen.

Referenz neu schreiben (nur nach bewusster, dokumentierter Modellaenderung):
    python test_bewertung_golden.py --aktualisieren
"""
import json
import os
import sys
import unittest

import etf_merkmale as EM
import investor_checks as I
import klassen_score as KS
import qualitaet_agent as Q
import scoring as SC
import wiki_idee as WI
from investor_checks import fairer_wert as FW
from investor_checks import konsens as KO
from test_agenten import STAMM, jahre_roh
from test_investor_checks import firma, jahr

REFERENZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests_golden", "bewertung_klassisch.json")


def _norm(x):
    """Zahlen auf 6 Stellen, Tupel als Listen - stabil vergleichbar und als JSON speicherbar."""
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    return x


# ---------------------------------------------------------------------------
# Testfaelle
# ---------------------------------------------------------------------------
def qualitaet_faelle():
    def k_von(jahre):
        # in EUR: Fremdwaehrungen rechnet der Agent ueber einen Online-Wechselkurs um - im Test ohne Netz
        k = Q.kennzahlen("X", jahre, "EUR", [], "EUR")
        k.update(kurs_wae="EUR", kurs_fb=20.0, kh=[], name_y="X")
        return k
    faelle = {
        "wachstum_stark": jahre_roh([100, 130, 170, 220, 290], revs=[1000, 1200, 1450, 1750, 2100],
                                    ebit=[200, 250, 310, 380, 460]),
        "stagnation": jahre_roh([100, 100, 100, 100, 100], revs=[1000] * 5),
        "fcf_negativ": jahre_roh([50, -20, -40, -60, -80], revs=[1000, 980, 950, 900, 850],
                                 ebit=[100, 60, 20, -10, -30]),
        "verwaesserung": jahre_roh([100, 110, 120, 130, 140], sh=[100, 108, 117, 127, 138]),
        "ohne_eps": jahre_roh([100, 110, 120, 130, 140], eps=False),
    }
    aus = {}
    for name, jahre in faelle.items():
        e = Q.bewerte("X", k_von(jahre), {"regularMarketPrice": 20, "sharesOutstanding": 100}, None, STAMM)
        aus[name] = None if e is None else {k: e.get(k) for k in ("gesamt", "klasse", "pt", "q_ant", "b_ant",
                                                                  "mos", "flags", "moat", "mgmt", "bew", "risiko")}
    return aus


def investor_faelle():
    letzt = firma()["jahre"]
    faelle = {
        "musterfirma": firma(),
        "bank": firma(sektor="Financial Services", branche="Banks—Diversified"),
        "reit": firma(sektor="Real Estate", branche="REIT—Retail"),
        "verlust": firma(jahre=letzt[:-1] + [jahr("2025-12-31", nettogewinn=-50.0, eps=-0.5, ebit=-20.0,
                                                  op_cf=-10.0, fcf=-60.0)]),
        "hoch_verschuldet": firma(jahre=letzt[:-1] + [jahr("2025-12-31", schulden=2500.0, langfr_schulden=2400.0,
                                                           zinsaufwand=180.0, ek=200.0)]),
    }
    aus = {}
    for name, f in faelle.items():
        erg = I.alle_checks(f, {})
        fair = FW.uebersicht(f, {})
        aus[name] = {
            "checks": {e["id"]: [e["score_0_100"], e["erfuellt"], e["gesamt"], e["kauf"]] for e in erg},
            "konsens": KO.kurzform(erg, fair, f),
            "fair_median": fair.get("median"),
            "fair_modelle": {m["methode"]: m["wert"] for m in fair.get("modelle") or []},
        }
    return aus


def klassen_faelle():
    zeilen = {
        "etf_welt": {"typ": "etf", "name": "iShares Core MSCI World", "1J": 12.0, "3J": 30.0, "5J": 60.0,
                     "10J": 140.0, "gesamt": 210.0, "vola": 14.0, "maxdd": -34.0, "jahre": 15.0},
        "etf_kurz": {"typ": "etf", "name": "Neuer Themen ETF", "1J": 25.0, "3J": None, "5J": None, "10J": None,
                     "gesamt": 30.0, "vola": 28.0, "maxdd": -22.0, "jahre": 1.5},
        "etf_hebel": {"typ": "etf", "name": "Leverage Shares 3x Long Nasdaq", "1J": 80.0, "3J": 120.0, "5J": None,
                      "10J": None, "gesamt": 150.0, "vola": 70.0, "maxdd": -75.0, "jahre": 4.0},
        "wiki_gut": {"typ": "wikifolio", "name": "Musterstrategie", "1J": 18.0, "3J": 50.0, "5J": 110.0,
                     "10J": None, "gesamt": 130.0, "vola": 12.0, "maxdd": -18.0, "jahre": 6.0},
    }
    aus = {}
    for name, w in zeilen.items():
        b = KS.bewerte(w, w["typ"])
        aus[name] = {"score": b.get("score"), "einordnung": b.get("einordnung"), "teile": b.get("teile")}
    return aus


def scoring_faelle():
    import random
    rnd = random.Random(11)
    u = []
    for i in range(24):
        u.append({"id": f"A{i}", "art": "aktie", "name": f"A{i}", "sektor": "S" + str(i % 3), "k": {
            "fkgv": rnd.uniform(8, 40), "ev_ebit": rnd.uniform(6, 35), "fcfy": rnd.uniform(-2, 9),
            "roic": rnd.uniform(-5, 40), "om": rnd.uniform(-5, 35), "g_ums": rnd.uniform(-5, 25),
            "g_eps": rnd.uniform(-10, 30), "nde": rnd.uniform(-1, 4), "div": rnd.uniform(0, 5),
            "p12": rnd.uniform(-30, 60), "vola": rnd.uniform(15, 60), "dd": -rnd.uniform(10, 70)}})
    for i in range(12):
        u.append({"id": f"E{i}", "art": "etf", "name": f"E{i}", "sektor": "", "k": {
            "p12": rnd.uniform(-10, 30), "r3": rnd.uniform(-2, 15), "r5": rnd.uniform(0, 14),
            "vola_k": rnd.uniform(8, 30), "maxdd": -rnd.uniform(10, 50), "jahre": rnd.uniform(2, 20)}})
    ver = SC.verteilungen(u)
    aus = {}
    for e in u:
        b = SC.bewerten(e, ver)
        aus[e["id"]] = {"gesamt": b["gesamt"], "fazit": b["fazit"],
                        "kategorien": {c["key"]: c["score"] for c in b["kategorien"]}}
    return aus


def wiki_faelle():
    import random
    rnd = random.Random(7)
    aktien = [({"id": f"S{i}", "art": "aktie", "name": f"Aktie {i:03d}", "ticker": f"S{i}", "wkn": "",
                "isin": f"US{i:010d}", "sektor": f"B{i % 5}", "kurs": round(rnd.uniform(5, 900), 2),
                "waehrung": "EUR", "k": {"p6": rnd.uniform(-30, 40)},
                "info": {"gesamt": rnd.randint(40, 99), "klasse": None}}, {}) for i in range(90)]
    inv = {f"S{i}": {"score": rnd.uniform(20, 95), "fv": rnd.uniform(-40, 60), "kaufen": rnd.randint(0, 12),
                     "inv": 12, "c": {"altman": [0 if i == 3 else 100, 1, 1]}} for i in range(0, 90, 2)}
    regionen = ("MSCI World", "S&P 500", "MSCI Emerging Markets", "Stoxx Europe 600", "MSCI Japan")
    etfs = [({"id": f"E{i}", "art": "etf", "name": f"ETF {i:03d} {regionen[i % 5]} UCITS", "wkn": f"W{i}",
              "isin": f"IE{i:010d}",
              "kurs": round(rnd.uniform(20, 300), 2), "waehrung": "EUR", "k": {"jahre": 8.0}, "info": {}},
             {"gesamt": rnd.uniform(40, 90)}) for i in range(35)]
    rang_a, aus, rang_e = WI.ranglisten(aktien + etfs, inv, KS.HEBEL, EM.merkmale)
    neu, liste = WI.umschichten({}, rang_a, rang_e, {}, "2026-11-04")
    # zweite Umschichtung: die bisherigen Top 15 fallen zurueck -> Puffer, Nachruecker, Verkaeufe
    rang_a2 = [dict(w, mix=w["mix"] - (25 if w["rang"] <= 15 else 0)) for w in rang_a]
    rang_a2.sort(key=lambda w: (-w["mix"], w["name"].lower()))
    for r, w in enumerate(rang_a2, 1):
        w["rang"] = r
    # ETFs: der bisher beste (gehaltene) ETF faellt genau auf Platz 23 - innerhalb des Puffers (Top 24)
    gehalten_e = [w for w in rang_e if w["id"] in neu["positionen"]]
    faller = dict(gehalten_e[0])
    rang_e2 = [dict(w) for w in rang_e if w["id"] != faller["id"]]
    rang_e2.insert(22, faller)
    for r, w in enumerate(rang_e2, 1):
        w["rang"] = r
    neu2, liste2 = WI.umschichten(neu, rang_a2, rang_e2, {}, "2026-11-11")
    return {"aktien_top10": [[w["id"], w["mix"]] for w in rang_a[:10]], "ausgeschlossen": aus,
            "etf_top5": [[w["id"], w["mix"]] for w in rang_e[:5]],
            "positionen": {i: [p["stueck"], p["auswahl"]] for i, p in sorted(neu["positionen"].items())},
            "kasse": neu["kasse"], "auftraege": len(liste),
            "zweite_liste": {"positionen": {i: [p["stueck"], p["auswahl"]] for i, p in sorted(neu2["positionen"].items())},
                             "auftraege": sorted([a["id"], a["aktion"], a["stueck"]] for a in liste2),
                             "kasse": neu2["kasse"]},
            "etf_puffer_haelt": faller["id"] in neu2["positionen"],
            "puffer_grenzfaelle": puffer_grenzfaelle()}


def puffer_grenzfaelle():
    """Auswahl isoliert: gehaltener Wert genau auf Platz Puffer, Puffer + 1 bzw. N + 1 (ohne Gruppengrenzen)."""
    def liste(n):
        return [{"id": f"X{i}", "rang": i, "gruppe": "–", "kurs": 10.0, "mix": 100 - i} for i in range(1, n + 1)]
    aus = {}
    for art, n, puffer in (("aktie", WI.N_AKTIEN, WI.PUFFER_AKTIEN), ("etf", WI.N_ETF, WI.PUFFER_ETF)):
        r = liste(puffer + 10)
        for platz in (n + 1, puffer, puffer + 1):
            ziel = WI.auswahl(r, n, puffer, {f"X{platz}"}, 10)
            aus[f"{art}_platz_{platz}"] = f"X{platz}" in {w["id"] for w in ziel}
    return aus


def ergebnisse():
    return _norm({"qualitaet": qualitaet_faelle(), "investoren": investor_faelle(), "klassen": klassen_faelle(),
                  "scoring": scoring_faelle(), "wiki_idee": wiki_faelle()})


class KlassischesModellUnveraendert(unittest.TestCase):
    """Jeder Bereich einzeln, damit die Fehlermeldung zeigt, WO sich das klassische Modell veraendert hat."""

    @classmethod
    def setUpClass(cls):
        with open(REFERENZ, encoding="utf-8") as f:
            cls.ref = json.load(f)
        cls.ist = ergebnisse()

    def vergleiche(self, bereich):
        self.maxDiff = None
        for fall, wert in self.ref[bereich].items():
            with self.subTest(bereich=bereich, fall=fall):
                self.assertEqual(self.ist[bereich].get(fall), wert)
        self.assertEqual(sorted(self.ist[bereich]), sorted(self.ref[bereich]))

    def test_qualitaets_score(self):
        self.vergleiche("qualitaet")

    def test_investoren_checks_konsens_fairer_wert(self):
        self.vergleiche("investoren")

    def test_etf_und_wikifolio_score(self):
        self.vergleiche("klassen")

    def test_gesamt_score_bewertung(self):
        self.vergleiche("scoring")

    def test_ki_invest_auswahl(self):
        self.vergleiche("wiki_idee")


if __name__ == "__main__":
    if "--aktualisieren" in sys.argv:
        os.makedirs(os.path.dirname(REFERENZ), exist_ok=True)
        daten = ergebnisse()                     # erst rechnen, dann schreiben (kein halber Stand bei Fehlern)
        with open(REFERENZ, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=1, sort_keys=True)
        print("Referenz geschrieben:", REFERENZ)
    else:
        unittest.main()
