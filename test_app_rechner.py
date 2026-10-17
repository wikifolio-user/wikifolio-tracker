"""Tests fuer die reinen Depot-Rechenfunktionen aus app.py (python3 -m unittest test_app_rechner).

app.py selbst laesst sich ohne Streamlit/Plotly nicht importieren. Deshalb werden die
benoetigten Modul-Funktionen per AST aus app.py herausgeloest und in einem eigenen
Namensraum ausgefuehrt (nur pandas/numpy/Standardbibliothek). Sollwerte sind
unabhaengig von Hand bzw. mit eigenen Formeln gerechnet.
"""
import ast
import bisect
import datetime
import html
import math
import os
import unittest

import numpy as np
import pandas as pd

FUNKTIONEN = [
    "fmt", "fmt_vz", "vz_zahl", "_h",
    "monats_termine", "sparplan_termine", "entnahme_termine", "kumulierte_entnahme",
    "sparplan_phasen", "sparrate_am", "sparplan_state_neu", "sparplan_einzelkaeufe", "sparplan_kaeufe",
    "sparplan_verlauf", "depot_kennzahlen_real", "rendite_pa_seit_kauf",
    "entnahme_rate_aus_state", "hochgerechnete_rendite_pa", "prognose_rate_rueckfall", "depot_kennzahlen",
    "berechne_reale_stueckzahl", "berechne_performance_kennzahlen", "perf_sortierwert",
    "realisierte_rendite_pa", "gesamt_perioden_berechnen", "haenge_live_punkt_an",
    "_berlin_tage", "mc_einsatz", "simuliere_bandbreite",
]


def _lade_funktionen():
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    with open(pfad, encoding="utf-8") as f:
        baum = ast.parse(f.read())
    defs = {n.name: n for n in baum.body if isinstance(n, ast.FunctionDef)}
    fehlend = [f for f in FUNKTIONEN if f not in defs]
    if fehlend:
        raise AssertionError(f"Funktionen fehlen in app.py: {fehlend}")
    modul = ast.Module(body=[defs[f] for f in FUNKTIONEN], type_ignores=[])
    ns = {"html": html, "bisect": bisect, "datetime": datetime, "pd": pd, "np": np, "math": math}
    exec(compile(modul, pfad, "exec"), ns)
    return ns


A = _lade_funktionen()
D = datetime.date


def _konstante_reihe(start, ende, preis):
    idx = pd.bdate_range(start, ende)
    return pd.Series([float(preis)] * len(idx), index=idx)


class GewinnMitSparplan(unittest.TestCase):          # DEP-01 / DEP-11
    def test_kurs_unveraendert_gibt_null_gewinn(self):
        kurse = _konstante_reihe("2025-01-01", "2025-05-01", 100.0)
        termine = A["sparplan_termine"](D(2025, 1, 15), D(2025, 4, 20))
        self.assertEqual(len(termine), 4)                      # 15.1., 15.2., 15.3., 15.4.
        eingezahlt, stueck = A["sparplan_kaeufe"](termine, kurse, 500.0)
        self.assertAlmostEqual(eingezahlt, 2000.0)
        self.assertAlmostEqual(stueck, 20.0)
        k = A["depot_kennzahlen"](100.0, stueck, 100.0, 10000.0, eingezahlt, 0.0, 0)
        self.assertAlmostEqual(k["brutto"], 12000.0)
        self.assertAlmostEqual(k["einstand"], 12000.0)
        self.assertAlmostEqual(k["gewinn"], 0.0)               # vorher: +2.000 € (Sparraten als Gewinn)
        self.assertAlmostEqual(k["rendite_pct"], 0.0)

    def test_beliebige_sparrate_kurs_unveraendert(self):
        for rate in (25.0, 137.5, 1000.0):
            kurse = _konstante_reihe("2024-01-01", "2025-12-31", 80.0)
            termine = A["sparplan_termine"](D(2024, 3, 1), D(2025, 6, 1))
            e, s = A["sparplan_kaeufe"](termine, kurse, rate)
            k = A["depot_kennzahlen"](50.0, s, 80.0, 4000.0, e, 0.0, 0)
            self.assertAlmostEqual(k["gewinn"], 0.0, places=8)

    def test_schwankende_kaufkurse(self):                  # Audit A-27: Ausfuehrung am naechsten Handelstag
        idx = pd.to_datetime(["2025-01-15", "2025-02-14", "2025-02-17", "2025-03-14", "2025-03-17", "2025-04-15"])
        kurse = pd.Series([100.0, 80.0, 90.0, 125.0, 110.0, 100.0], index=idx)
        termine = A["sparplan_termine"](D(2025, 1, 15), D(2025, 4, 15))
        e, s = A["sparplan_kaeufe"](termine, kurse, 500.0)
        # 15.02./15.03.2025 sind Samstage -> Kauf am Montag 17.02. (90) bzw. 17.03. (110)
        soll = 5 + 500 / 90 + 500 / 110 + 5
        self.assertAlmostEqual(s, soll)
        k = A["depot_kennzahlen"](100.0, s, 100.0, 10000.0, e, 0.0, 0)
        self.assertAlmostEqual(k["gewinn"], (100 + soll) * 100 - 12000)
        self.assertAlmostEqual(k["rendite_pct"], ((100 + soll) * 100 - 12000) / 12000 * 100)

    def test_kauftag_und_verlauf(self):
        idx = pd.bdate_range("2025-01-01", "2025-03-31")
        kurse = pd.Series(100.0, index=idx)
        termine = A["sparplan_termine"](D(2025, 1, 4), D(2025, 3, 31))     # 04.01. ist ein Samstag
        kaeufe = A["sparplan_einzelkaeufe"](termine, kurse, 100.0)
        self.assertEqual([k[0].date() for k in kaeufe], [D(2025, 1, 6), D(2025, 2, 4), D(2025, 3, 4)])
        stueck, geld = A["sparplan_verlauf"](pd.to_datetime(["2025-01-03", "2025-01-06", "2025-03-31"]), kaeufe)
        self.assertEqual(stueck, [0, 1.0, 3.0])
        self.assertEqual(geld, [0, 100.0, 300.0])
        # Kauf nach dem letzten Kurspunkt (Termin am Wochenende, Live-Kurs) zaehlt am Ende mit
        spaet = kaeufe + [(pd.Timestamp("2025-04-05"), 100.0, 1.0)]
        stueck, _ = A["sparplan_verlauf"](pd.to_datetime(["2025-03-31", "2025-04-04"]), spaet)
        self.assertEqual(stueck, [3.0, 4.0])

    def test_reale_kennzahlen_mit_auszahlungen(self):          # Audit A-12
        k = A["depot_kennzahlen_real"](120.0, 3.0, 150.0, 13500.0, 1050.0)
        self.assertAlmostEqual(k["wert"], 123 * 150.0)
        self.assertAlmostEqual(k["gewinn"], 123 * 150.0 + 1050.0 - 13500.0)
        self.assertAlmostEqual(k["rendite_pct"], k["gewinn"] / 13500.0 * 100)
        self.assertEqual(A["depot_kennzahlen_real"](0, 0, 100.0, 0.0, 0.0)["rendite_pct"], 0.0)

    def test_rendite_pa_seit_kauf(self):                        # Audit A-08
        r, hoch = A["rendite_pa_seit_kauf"](100.0, 150.0, D(2025, 7, 9), D(2026, 10, 17))
        self.assertFalse(hoch)
        self.assertAlmostEqual(r, (1.5 ** (365.25 / 465) - 1) * 100)
        r, hoch = A["rendite_pa_seit_kauf"](100.0, 110.0, D(2026, 1, 1), D(2026, 7, 1))
        self.assertTrue(hoch)
        self.assertEqual(A["rendite_pa_seit_kauf"](0.0, 110.0, D(2026, 1, 1), D(2026, 7, 1)), (None, False))

    def test_ohne_kurs_kein_kauf_und_kein_einstand(self):
        kurse = _konstante_reihe("2025-03-01", "2025-05-01", 100.0)
        termine = A["sparplan_termine"](D(2025, 1, 15), D(2025, 4, 20))
        e, s = A["sparplan_kaeufe"](termine, kurse, 500.0)     # 15.1./15.2. vor Datenbeginn
        self.assertAlmostEqual(e, 1000.0)
        self.assertAlmostEqual(s, 10.0)
        # auch mit Ersatz-(Live-)Kurs: alte Termine vor Datenbeginn werden nicht nachgekauft
        e, s = A["sparplan_kaeufe"](termine, kurse, 500.0, ersatzkurs=150.0)
        self.assertAlmostEqual(e, 1000.0)

    def test_phasen_rate_aenderung(self):
        st0 = A["sparplan_state_neu"]({}, 500.0, D(2025, 1, 15))
        self.assertEqual(st0["start_datum"], "2025-01-15")
        self.assertIsNone(A["sparplan_state_neu"](st0, 500.0, D(2025, 2, 1)))   # unveraendert
        st1 = A["sparplan_state_neu"](st0, 300.0, D(2025, 3, 1))
        start, phasen = A["sparplan_phasen"](st1)
        self.assertEqual(start, D(2025, 1, 15))
        self.assertEqual(phasen, [(D(2025, 1, 15), 500.0), (D(2025, 3, 1), 300.0)])
        kurse = _konstante_reihe("2025-01-01", "2025-05-01", 100.0)
        termine = A["sparplan_termine"](start, D(2025, 4, 20))
        e, s = A["sparplan_kaeufe"](termine, kurse, lambda t: A["sparrate_am"](phasen, t))
        self.assertAlmostEqual(e, 500 + 500 + 300 + 300)       # Jan, Feb mit 500; Mrz, Apr mit 300

    def test_altbestand_ohne_rate(self):
        start, phasen = A["sparplan_phasen"]({"start_datum": "2025-02-01"})
        self.assertEqual((start, phasen), (D(2025, 2, 1), []))
        neu = A["sparplan_state_neu"]({"start_datum": "2025-02-01"}, 200.0, D(2025, 6, 1))
        self.assertEqual(neu["phasen"], [{"ab": "2025-02-01", "rate": 200.0}])  # gilt ab Start
        self.assertEqual(A["sparplan_phasen"]({}), (None, []))
        self.assertEqual(A["sparplan_phasen"]({"start_datum": "kaputt"}), (None, []))


class Entnahme(unittest.TestCase):                    # DEP-03 / DEP-11
    def test_anzahl_seit_kauf_config(self):
        t = A["entnahme_termine"](D(2025, 7, 9), D(2026, 10, 12))
        self.assertEqual(len(t), 15)                           # 09.08.2025 ... 09.10.2026
        self.assertEqual(t[0], pd.Timestamp("2025-08-09"))
        self.assertEqual(t[-1], pd.Timestamp("2026-10-09"))
        self.assertEqual(len(A["entnahme_termine"](D(2025, 7, 9), D(2026, 10, 8))), 14)
        self.assertEqual(A["entnahme_termine"](D(2025, 7, 9), D(2025, 8, 8)), [])

    def test_monatsende_und_schaltjahr(self):
        t = A["entnahme_termine"](D(2025, 1, 31), D(2025, 4, 30))
        self.assertEqual([x.date() for x in t], [D(2025, 2, 28), D(2025, 3, 31), D(2025, 4, 30)])
        self.assertEqual(len(A["entnahme_termine"](D(2025, 1, 31), D(2025, 4, 29))), 2)
        self.assertEqual(A["entnahme_termine"](D(2024, 1, 31), D(2024, 2, 29))[0].date(), D(2024, 2, 29))
        t = A["entnahme_termine"](D(2024, 2, 29), D(2025, 3, 1))
        self.assertEqual(len(t), 12)
        self.assertEqual(t[-1].date(), D(2025, 2, 28))
        self.assertEqual(A["sparplan_termine"](D(2024, 1, 31), D(2024, 3, 31))[1].date(), D(2024, 2, 29))

    def test_netto_kumuliert(self):
        # Audit-Beispiel: 70 €/Monat, 9 Monate -> 12.000 - 630 = 11.370
        k = A["depot_kennzahlen"](120.0, 0.0, 100.0, 12000.0, 0.0, 70.0, 9)
        self.assertAlmostEqual(k["netto"], 11370.0)
        self.assertAlmostEqual(k["entnommen"], 630.0)
        self.assertAlmostEqual(k["gewinn"], 0.0)               # Entnahme mindert den Gewinn nicht doppelt

    def test_rate_null_netto_gleich_real_gleich_brutto(self):
        idx = pd.bdate_range("2025-01-01", "2025-06-30")
        df = pd.DataFrame({"Close": np.linspace(90, 110, len(idx))}, index=idx)
        termine = A["entnahme_termine"](D(2025, 1, 1), D(2025, 6, 30))
        real = A["berechne_reale_stueckzahl"](df, 50.0, 0.0, termine, 0.5)
        self.assertTrue(all(abs(x - 50.0) < 1e-12 for x in real))
        k = A["depot_kennzahlen"](50.0, 0.0, 110.0, 5000.0, 0.0, 0.0, len(termine))
        self.assertAlmostEqual(k["netto"], k["brutto"])

    def test_real_gleicher_plan_wie_netto(self):
        idx = pd.bdate_range("2025-01-01", "2025-04-30")
        df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
        termine = A["entnahme_termine"](D(2025, 1, 15), D(2025, 4, 30))    # 15.2., 15.3., 15.4.
        real = A["berechne_reale_stueckzahl"](df, 100.0, 70.0, termine, 0.0)
        self.assertAlmostEqual(real[-1], 100.0 - 3 * 0.7)
        self.assertAlmostEqual(real[-1] * 100.0, 10000.0 - 3 * 70.0)       # = Netto ohne Spread
        # Termin am Samstag (15.02.2025) -> Verkauf am naechsten Handelstag (17.02.)
        pos = list(df.index).index(pd.Timestamp("2025-02-17"))
        self.assertAlmostEqual(real[pos - 1], 100.0)
        self.assertAlmostEqual(real[pos], 99.3)
        mit_spread = A["berechne_reale_stueckzahl"](df, 100.0, 70.0, termine, 1.0)
        self.assertAlmostEqual(mit_spread[-1], 100.0 - 3 * 70.0 / 99.0)
        kum = A["kumulierte_entnahme"](df.index, termine, 70.0)
        self.assertEqual(kum[0], 0.0)
        self.assertEqual(kum[-1], 210.0)

    def test_entnahme_quelle(self):
        self.assertEqual(A["entnahme_rate_aus_state"](None, 70.0), 70.0)
        self.assertEqual(A["entnahme_rate_aus_state"]({"rate": 0}, 70.0), 0.0)
        self.assertEqual(A["entnahme_rate_aus_state"]({"rate": "120"}, 70.0), 120.0)
        self.assertEqual(A["entnahme_rate_aus_state"]({"rate": "x"}, 70.0), 70.0)


class MonteCarlo(unittest.TestCase):                  # DEP-05 / DEP-06
    @staticmethod
    def _reihe(log_renditen, start=100.0):
        werte = start * np.exp(np.concatenate([[0.0], np.cumsum(log_renditen)]))
        return pd.Series(werte, index=pd.bdate_range("2020-01-01", periods=len(werte)))

    def test_median_entspricht_log_drift(self):
        rng = np.random.default_rng(7)
        reihe = self._reihe(rng.normal(0.0004, 0.012, 1500))
        lr = np.diff(np.log(reihe.values))
        mu, sigma = float(np.mean(lr)), float(np.std(lr, ddof=1))
        perz, kz = A["simuliere_bandbreite"](10000.0, reihe, 5, shrinkage=False, pfade=20000)
        soll = 10000.0 * math.exp(mu * 1260)
        self.assertLess(abs(perz[50] / soll - 1), 0.01)
        # alter Fehler (doppeltes -sigma^2/2) laege um exp(-0,5*sigma^2*1260) daneben
        self.assertGreater(abs(10000.0 * math.exp((mu - 0.5 * sigma ** 2) * 1260) / soll - 1), 0.05)
        # angezeigte Rate passt zum simulierten Median (CAGR des Medians)
        median_cagr = ((perz[50] / 10000.0) ** (1 / 5) - 1) * 100
        self.assertLess(abs(median_cagr - kz["mu_verwendet_pa"]), 0.3)
        self.assertAlmostEqual(kz["mu_verwendet_pa"], (math.exp(mu * 252) - 1) * 100, places=6)

    def test_anker_ohne_zusatzabzug(self):
        # Driftfreie Historie, kurz: Median liegt zwischen 0 und dem 8-%-Anker - nie darunter
        r = np.tile([0.01, -0.01], 100)
        perz, kz = A["simuliere_bandbreite"](10000.0, self._reihe(r), 3, shrinkage=True, pfade=20000)
        jahre = 200 / 252
        g = jahre / (jahre + 3.0)
        mu = (1 - g) * math.log(1.08) / 252
        self.assertLess(abs(perz[50] / (10000.0 * math.exp(mu * 756)) - 1), 0.01)

    def test_verlust_gegen_eingezahltes_geld(self):
        r = np.tile([0.01, -0.01], 200)                        # mittlere Log-Rendite exakt 0
        reihe = self._reihe(r)
        _, ohne = A["simuliere_bandbreite"](10000.0, reihe, 5, shrinkage=False, pfade=8000)
        _, mit = A["simuliere_bandbreite"](10000.0, reihe, 5, sparrate_monat=500.0,
                                           shrinkage=False, pfade=8000)
        self.assertTrue(40 <= ohne["verlust_wahrscheinlichkeit"] <= 60)
        self.assertTrue(35 <= mit["verlust_wahrscheinlichkeit"] <= 65)   # vorher ~0 %
        self.assertAlmostEqual(mit["eingesetzt"], 10000.0 + 60 * 500.0)
        self.assertEqual(A["mc_einsatz"](10000.0, 1260, 500.0, 70.0), 10000.0 + 60 * 430.0)
        self.assertEqual(A["mc_einsatz"](10000.0, 20, 500.0), 10000.0)


class KurzeZeitraeume(unittest.TestCase):             # DEP-08
    def test_keine_hochrechnung_unter_einem_jahr(self):
        g, m, j, e = A["berechne_performance_kennzahlen"](100.0, 101.0, D(2025, 1, 1), D(2025, 1, 2))
        self.assertAlmostEqual(g, 1.0)
        self.assertIsNone(m)
        self.assertIsNone(j)                                   # vorher +3.688 % p.a.
        self.assertAlmostEqual(e, 1.0)
        g, m, j, _ = A["berechne_performance_kennzahlen"](100.0, 105.0, D(2025, 1, 1), D(2025, 1, 31))
        self.assertIsNone(j)                                   # vorher +81 % p.a.
        self.assertAlmostEqual(m, (1.05 ** (1 / (30 / 30.44)) - 1) * 100)
        _, _, j, _ = A["berechne_performance_kennzahlen"](100.0, 110.0, D(2024, 1, 1), D(2025, 2, 4))
        self.assertAlmostEqual(j, (1.1 ** (365.25 / 400) - 1) * 100)

    def test_rueckfallrate_erst_ab_180_tagen(self):
        self.assertIsNone(A["realisierte_rendite_pa"](110.0, 100.0, 179))
        self.assertAlmostEqual(A["realisierte_rendite_pa"](110.0, 100.0, 180), (1.1 ** (365.25 / 180) - 1) * 100)
        rate, hinweis = A["prognose_rate_rueckfall"](110.0, 100.0, 29)
        self.assertEqual(rate, 0.0)
        self.assertIn("< 1 Monat", hinweis)
        rate, hinweis = A["prognose_rate_rueckfall"](110.0, 100.0, 365)
        self.assertIsNone(hinweis)
        self.assertAlmostEqual(rate, (1.1 ** (365.25 / 365) - 1) * 100)

    def test_prognose_hochrechnung_unter_1_jahr(self):
        # Nutzerentscheid: < 1 Jahr Ø-Monatsrendite auf ein Jahr hochrechnen (ab 1 Monat)
        # 6 Monate (182,6 Tage) +5 % -> 1,05^2 - 1 = 10,25 % p.a. (unabhaengig gerechnet)
        rate, hinweis = A["prognose_rate_rueckfall"](105.0, 100.0, 182.6)
        self.assertAlmostEqual(rate, 10.25, delta=0.01)
        self.assertIn("Hochgerechnet aus 6.0 Monaten", hinweis)
        self.assertIn("Ø Monatsrendite", hinweis)
        r_pa, monate, r_m = A["hochgerechnete_rendite_pa"](105.0, 100.0, 182.6)
        self.assertAlmostEqual(monate, 6.0, delta=0.01)
        self.assertAlmostEqual(r_m, (1.05 ** (1 / 6) - 1) * 100, delta=0.01)
        # 3 Monate -6 % -> 0,94^4 - 1 = -21,93 % p.a.
        rate, hinweis = A["prognose_rate_rueckfall"](94.0, 100.0, 91.3125)
        self.assertAlmostEqual(rate, -21.92, delta=0.02)
        self.assertIn("3.0 Monaten", hinweis)
        # 20 Tage -> Rueckfall 0 % mit Hinweis, keine absurde Hochrechnung
        rate, hinweis = A["prognose_rate_rueckfall"](120.0, 100.0, 20)
        self.assertEqual(rate, 0.0)
        self.assertIn("< 1 Monat", hinweis)
        self.assertIsNone(A["hochgerechnete_rendite_pa"](120.0, 100.0, 20))
        # genau 1 Monat ist die Mindestbasis
        self.assertIsNotNone(A["hochgerechnete_rendite_pa"](101.0, 100.0, 30))
        # 400 Tage -> bisheriges Verhalten unveraendert (realisiert p.a., kein Hinweis)
        rate, hinweis = A["prognose_rate_rueckfall"](110.0, 100.0, 400)
        self.assertIsNone(hinweis)
        self.assertAlmostEqual(rate, A["realisierte_rendite_pa"](110.0, 100.0, 400))
        self.assertAlmostEqual(rate, 9.0930, delta=0.001)
        # ungueltige Kurse -> 0 %
        self.assertEqual(A["prognose_rate_rueckfall"](110.0, 0.0, 200)[0], 0.0)
        # Tabellen-Kennzahl Ø/Jahr bleibt unter 365 Tagen None (gemessener Wert)
        _, _, j, _ = A["berechne_performance_kennzahlen"](100.0, 105.0, D(2025, 1, 1), D(2025, 7, 2))
        self.assertIsNone(j)

    def test_sortierung(self):
        liste = [{"Wert": "kurz", "_perf": 50.0, "_jaehrlich": None},
                 {"Wert": "lang", "_perf": 5.0, "_jaehrlich": 4.0},
                 {"Wert": "lang2", "_perf": 9.0, "_jaehrlich": 8.0}]
        liste.sort(key=A["perf_sortierwert"], reverse=True)
        self.assertEqual([e["Wert"] for e in liste], ["lang2", "lang", "kurz"])


class Gesamtdepot(unittest.TestCase):                 # DEP-07
    def test_basis_nur_beitragende_positionen(self):
        erg = A["gesamt_perioden_berechnen"](
            [(11000.0, {"Tag": 50.0, "Jahr": 1000.0}), (10000.0, {"Tag": -50.0})], ["Tag", "Jahr", "Monat"])
        werte = {lbl: (b, p, t) for lbl, b, p, t in erg}
        self.assertNotIn("Monat", werte)
        b, p, teil = werte["Jahr"]
        self.assertAlmostEqual(b, 1000.0)
        self.assertAlmostEqual(p, 10.0)                        # vorher 5,26 %
        self.assertTrue(teil)
        b, p, teil = werte["Tag"]
        self.assertAlmostEqual(b, 0.0)
        self.assertFalse(teil)


class LivePunkt(unittest.TestCase):                   # DEP-10 / DEP-09
    def test_heute_wird_angehaengt(self):
        idx = pd.to_datetime(["2026-10-08", "2026-10-09"])
        df = pd.DataFrame({"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0], "Close": [1.0, 2.0]}, index=idx)
        neu = A["haenge_live_punkt_an"](df, D(2026, 10, 12), 3.0)
        self.assertEqual(list(neu.index[-2:]), [pd.Timestamp("2026-10-09"), pd.Timestamp("2026-10-12")])
        self.assertEqual(neu.loc["2026-10-09", "Close"], 2.0)  # gestriger Schluss bleibt
        self.assertEqual(neu["Close"].iloc[-1], 3.0)
        gleich = A["haenge_live_punkt_an"](df, D(2026, 10, 9), 2.5)
        self.assertEqual(len(gleich), 2)
        self.assertEqual(gleich["Close"].iloc[-1], 2.5)
        self.assertEqual(gleich["High"].iloc[-1], 2.5)
        self.assertEqual(df["Close"].iloc[-1], 2.0)            # Original unveraendert

    def test_berliner_kalendertag(self):
        utc = datetime.timezone.utc
        sommer = datetime.datetime(2025, 7, 8, 22, 0, tzinfo=utc).timestamp() * 1000
        winter = datetime.datetime(2025, 1, 14, 23, 0, tzinfo=utc).timestamp() * 1000
        mittag = datetime.datetime(2025, 1, 14, 12, 0, tzinfo=utc).timestamp() * 1000
        tage = list(A["_berlin_tage"]([sommer, winter, mittag]))
        self.assertEqual(tage, [pd.Timestamp("2025-07-09"), pd.Timestamp("2025-01-15"), pd.Timestamp("2025-01-14")])
        self.assertIsNone(tage[0].tzinfo)


class Darstellung(unittest.TestCase):                 # DEP-13 / SEC-04
    def test_vorzeichen(self):
        self.assertEqual(A["fmt_vz"](-500), "-500,00€")
        self.assertEqual(A["fmt_vz"](1234.5), "+1.234,50€")
        self.assertEqual(A["fmt_vz"](0), "+0,00€")
        self.assertEqual(A["fmt_vz"](-0.001), "+0,00€")
        self.assertEqual(A["vz_zahl"](-1234.5), "-1.234,50")
        self.assertEqual(A["vz_zahl"](2.0, 3), "+2,000")
        for v in (-1e6, -3.14159, -0.004, 0.0, 0.004, 7.5, 1e6):
            self.assertNotIn("+-", A["fmt_vz"](v))
            self.assertNotIn("+-", A["vz_zahl"](v))

    def test_escaping(self):
        self.assertEqual(A["_h"]("<b>x</b>"), "&lt;b&gt;x&lt;/b&gt;")
        self.assertEqual(A["_h"]('a"b\'c&'), "a&quot;b&#x27;c&amp;")
        self.assertEqual(A["_h"](None), "")
        self.assertEqual(A["_h"](12), "12")


class QuellcodeRegeln(unittest.TestCase):
    """Statische Pruefungen am Quelltext (app.py ist ohne Streamlit nicht ausfuehrbar)."""
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"), encoding="utf-8") as f:
            cls.src = f.read()

    def test_keine_kursalarme_mehr_in_der_app(self):            # DATA-03
        self.assertNotIn("STATE_PATH_PRICE_ALERT", self.src)
        self.assertNotIn("config.STATE_PATH_ALARM", self.src)
        self.assertNotIn("def check_and_send_price_updates", self.src)
        self.assertNotIn("gh_write(\n                config.STATE_PATH_HIGH_WATERMARK", self.src)
        self.assertNotIn("requests.post(DISCORD_WEBHOOK_URL", self.src.replace(
            'r = requests.post(DISCORD_WEBHOOK_URL, json={"content": text}, timeout=5)', ""))

    def test_kein_doppelter_volatilitaetsabzug(self):           # DEP-05
        self.assertNotIn("0.5 * sigma_tag ** 2", self.src)

    def test_sparplan_wird_nicht_mehr_still_geloescht(self):    # DEP-02
        self.assertNotIn("gh_write(config.STATE_PATH_SPARPLAN", self.src)

    def test_kein_fester_70_euro_text(self):                    # DEP-03
        self.assertNotIn("70€/Monat", self.src)


if __name__ == "__main__":
    unittest.main()
