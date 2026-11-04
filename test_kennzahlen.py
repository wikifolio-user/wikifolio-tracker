"""Etappe 2: Kennzahl-Register, fehlende Daten im Qualitaets-Score, Datenvertrauen, classic_v2 (Vergleichsmodell)."""
import datetime
import unittest

import qualitaet_agent as Q
from kennzahlen import classic_v2 as V2
from kennzahlen import datenvertrauen as DV
from kennzahlen import definitionen as D
from kennzahlen import fehlwerte as FW
from test_agenten import STAMM, jahre_roh

HEUTE = datetime.date(2026, 11, 4)


class Register(unittest.TestCase):
    def test_metadaten_und_anwendbarkeit(self):
        self.assertEqual(D.meta("fkgv").herkunft, "schaetzung")
        self.assertEqual(D.meta("roic").herkunft, "berechnet")
        self.assertFalse(D.anwendbar("roic", "bank"))
        self.assertTrue(D.anwendbar("roic", "standard"))
        self.assertTrue(D.anwendbar("unbekannt", "bank"))                 # keine stille Sperre
        m = D.mit_meta("nde", None, stand="2026-11-01", sektor_typ="reit")
        self.assertTrue(m["fehlt"])
        self.assertFalse(m["anwendbar"])
        self.assertEqual(m["einheit"], "x")
        self.assertTrue(all(k.herkunft in D.HERKUNFT for k in D.REGISTER.values()))


class Fehlwerte(unittest.TestCase):
    def test_fehlende_punkte(self):
        fp = FW.fehlende_punkte({"roic_avg": None, "om_avg": 12, "cc": 0.9, "capex": 4, "g_ums": 5, "g_eps": None,
                                 "g_fcfps": None, "fm_avg": 10, "nd": -5, "nd_ebitda": None, "zinsd": None,
                                 "g_akt": 0, "gm_avg": 50, "om_std": 1, "fcfy": 4, "ev_ebit": None, "peg": None,
                                 "h_fcfy": 3, "mos": 10, "bear": -20})
        self.assertEqual(fp, {"qualitaet": 8, "wachstum": 9, "fcf": 3, "moat": 4, "bewertung": 5})
        self.assertNotIn("bilanz", fp)                                     # Nettocash: Punkte ohnehin vergeben
        self.assertAlmostEqual(FW.datenluecke_anteil(fp), 0.29)

    def test_hochrechnung_erfindet_nichts(self):
        pt = [6, 3, 10, 8, 8, 4, 5, 3]
        aus, summe = FW.hochgerechnet(pt, {"qualitaet": 8, "wachstum": 15})
        self.assertEqual(aus[0], 10.0)                    # 6 von 12 messbaren Punkten -> 10 von 20
        self.assertEqual(aus[1], 3.0)                     # Bereich ganz ohne Daten: keine Hochrechnung
        self.assertEqual(aus[2:], [10, 8, 8, 4, 5, 3])
        self.assertEqual(summe, sum(aus))

    def test_agent_schreibt_fp_und_abzug_ohne_scoreaenderung(self):
        k = Q.kennzahlen("X", jahre_roh([50, -20, -40, -60, -80], revs=[1000, 980, 950, 900, 850],
                                        ebit=[100, 60, 20, -10, -30]), "EUR", [], "EUR")
        k.update(kurs_wae="EUR", kurs_fb=20.0, kh=[], name_y="X")
        e = Q.bewerte("X", k, {"regularMarketPrice": 20, "sharesOutstanding": 100}, None, STAMM)
        self.assertEqual(e["abz"], sum(a for _, a in e["flags"]))
        self.assertEqual(e["gesamt"], max(sum(e["pt"]) - e["abz"], 0))
        self.assertIsInstance(e["fp"], dict)
        self.assertIn("abz", Q.ALLE_FELDER)
        self.assertEqual(Q.ALLE_FELDER[-1], "d")                           # Detail-Teil bleibt letztes Feld


class Datenvertrauen(unittest.TestCase):
    Q_GUT = {"kurs": 120.0, "mcap": 50.0, "kwae": "USD", "g_ums": 8, "g_eps": 10, "g_fcf": 9, "roic": 25, "om": 22,
             "fm": 18, "nde": 0.5, "akt": -1, "ev_ebit": 18, "fcfy": 4.2, "mos": 10, "fkgv": 22, "n": 5,
             "fp": {}}

    def test_vollstaendig_aktuell(self):
        r = DV.aktie(self.Q_GUT, {"st": "2026-11-01"}, stand="2026-11-03", heute=HEUTE)
        self.assertEqual(r["score"], 100)
        self.assertEqual(r["warnungen"], [])

    def test_luecken_alt_unplausibel(self):
        q = dict(self.Q_GUT, fp={"qualitaet": 8, "wachstum": 15, "bewertung": 10}, n=2, fcfy=55.0, ev_ebit=None,
                 rev90=3.0)
        r = DV.aktie(q, {"st": "2026-07-01"}, stand="2026-11-03", heute=HEUTE)
        self.assertLess(r["score"], 70)
        self.assertEqual(r["teile"]["vollstaendigkeit"], 67)
        self.assertEqual(r["teile"]["historie"], 40)
        self.assertEqual(r["teile"]["aktualitaet"], 20)                   # Investoren-Check 4 Monate alt
        self.assertEqual(r["teile"]["schaetzanteil"], 60)                 # nur erwartetes KGV + Revisionen
        self.assertTrue(any("unplausibl" in w for w in r["warnungen"]))
        self.assertTrue(any("2 Geschäftsjahre" in w for w in r["warnungen"]))

    def test_bank_fehlende_kennzahlen_zaehlen_nicht(self):
        q = {k: v for k, v in self.Q_GUT.items() if k not in ("fp", "roic", "om", "fm", "nde", "g_fcf", "ev_ebit",
                                                                "fcfy")}
        bank = DV.aktie(q, stand="2026-11-03", heute=HEUTE, sektor_typ="bank")
        standard = DV.aktie(q, stand="2026-11-03", heute=HEUTE, sektor_typ="standard")
        self.assertEqual(bank["teile"]["vollstaendigkeit"], 100)
        self.assertLess(standard["teile"]["vollstaendigkeit"], 60)

    def test_etf(self):
        r = DV.etf({"rendite": 9.5, "vola": 15, "dd": -33, "jahre": 15}, stand="2026-11-03", heute=HEUTE)
        self.assertEqual(r["score"], 100)
        self.assertTrue(any("TER" in w for w in r["warnungen"]))
        kurz = DV.etf({"rendite": 30, "vola": 25, "dd": None, "jahre": 1.2}, stand="2026-08-01", heute=HEUTE)
        self.assertLess(kurz["score"], 70)


class ClassicV2(unittest.TestCase):
    def test_red_flag_deckel(self):
        pt = [18, 12, 12, 8, 8, 8, 10, 4]                                 # roh 80
        self.assertEqual(V2.qualitaet_v2(pt, 45), 50)                     # v1 waere 35
        self.assertEqual(V2.qualitaet_v2(pt, 10), 70)                     # unter dem Deckel identisch
        self.assertEqual(V2.qualitaet_v2(pt, None, gesamt_v1=62), 62)     # Rueckrechnung aus v1
        self.assertIsNone(V2.qualitaet_v2(None, 5))

    def test_risiko_vorlaeufig(self):
        r, t = V2.risiko_vorlaeufig("mittel", {"altman": [100, 1, 1], "beneish": [0, 0, 1], "buffett": [90, 5, 6]})
        self.assertEqual(t, {"stufe": 55.0, "modelle": 50.0})            # Buffett ist kein Risiko-Modell
        self.assertEqual(r, 52.5)
        self.assertEqual(V2.risiko_vorlaeufig(None, {}), (None, {}))

    def test_gesamt_und_hochrechnung(self):
        g, gew = V2.gesamt_v2(80, 60, 50)
        self.assertEqual(g, round((55 * 80 + 35 * 60 + 10 * 50) / 100, 1))
        g, gew = V2.gesamt_v2(80, None, None)
        self.assertEqual((g, gew), (80.0, {"qualitaet": 100}))
        self.assertEqual(V2.gesamt_v2(None, 60, 50), (None, {}))
        b = V2.bewerte({"pt": [18, 12, 12, 8, 8, 8, 10, 4], "abz": 45, "gesamt": 35, "risiko": "hoch"},
                       {"score": 70, "c": {"altman": [50, 1, 1]}})
        self.assertEqual((b["v1"], b["qualitaet_v2"], b["risiko"]), (35, 50, 37.5))
        self.assertIn("vorläufig", b["hinweis"])

    def test_vergleich(self):
        z = [{"id": i, "v1": 100 - i, "v2": 100 - i} for i in range(20)]
        v = V2.vergleich(z, top=5)
        self.assertEqual((v["spearman"], v["top_gleich"]), (1.0, 5))
        z[19]["v2"] = 200                                                  # Letzter wird Erster
        v = V2.vergleich(z, top=5)
        self.assertLess(v["spearman"], 1.0)
        self.assertEqual(v["neu_in_top"], [19])
        self.assertEqual(v["aufsteiger"][0], (19, 20, 1))


if __name__ == "__main__":
    unittest.main()
