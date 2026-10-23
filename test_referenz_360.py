"""360°-Pruefung: Finanzkennzahlen gegen unabhaengig gerechnete Referenzwerte (python3 -m unittest test_referenz_360).

Sollwerte stammen aus geschlossenen Formeln oder Handrechnung - nie aus dem App-Code selbst.
Die Funktionen aus app.py werden wie in test_app_rechner per AST geladen.
"""
import ast
import datetime
import os
import unittest

import pandas as pd

import abfindung as AB
import investment_scanner2 as IS2
import zinsrechner as Z
from test_app_rechner import A as _A


def _lade(namen):
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    baum = ast.parse(open(pfad, encoding="utf-8").read())
    defs = {n.name: n for n in baum.body if isinstance(n, ast.FunctionDef)}
    ns = dict(_A)
    exec(compile(ast.Module(body=[defs[f] for f in namen], type_ignores=[]), pfad, "exec"), ns)
    return ns


A = _lade(["rendite_pa_geldgewichtet", "rendite_pa_seit_kauf", "referenzkurs_vor_tagen", "berechne_zeitraeume"])
D = datetime.date


def _endwert(zahlungen, rate, heute):
    """Referenz: jede Zahlung waechst ab ihrem Datum mit (1+rate)^(Tage/365,25)."""
    return sum(b * (1 + rate) ** ((heute - d).days / 365.25) for d, b in zahlungen)


class GeldgewichteteRendite(unittest.TestCase):              # F-01
    def test_reiner_sparplan_ergibt_die_echte_rendite(self):
        heute = D(2026, 1, 1)
        zahlungen = [(D(2024 + (m // 12), m % 12 + 1, 1), 500.0) for m in range(24)]   # 24 x 500 EUR
        ende = _endwert(zahlungen, 0.10, heute)
        einstand = 12000.0
        r, hoch = A["rendite_pa_seit_kauf"](einstand, ende, zahlungen[0][0], heute, zahlungen=zahlungen,
                                            depotwert=ende)
        self.assertAlmostEqual(r, 10.0, places=4)
        self.assertFalse(hoch)
        # die alte Rechnung (alles am ersten Tag investiert) lag weit darunter
        alt, _ = A["rendite_pa_seit_kauf"](einstand, ende, zahlungen[0][0], heute)
        self.assertLess(alt, 6.0)

    def test_startkapital_plus_sparplan_plus_entnahmen(self):
        heute = D(2026, 7, 1)
        zahlungen = [(D(2023, 7, 1), 10000.0)] + [(D(2024, m, 15), 250.0) for m in range(1, 13)] \
            + [(D(2025, m, 1), -100.0) for m in range(1, 13)]
        ende = _endwert(zahlungen, 0.07, heute)
        r = A["rendite_pa_geldgewichtet"](zahlungen, ende, heute)
        self.assertAlmostEqual(r, 7.0, places=4)

    def test_ohne_zusatzzahlungen_gleich_cagr(self):
        heute = D(2026, 1, 1)
        r_alt, _ = A["rendite_pa_seit_kauf"](1000.0, 1210.0, D(2024, 1, 1), heute)
        r_neu = A["rendite_pa_geldgewichtet"]([(D(2024, 1, 1), 1000.0)], 1210.0, heute)
        self.assertAlmostEqual(r_alt, r_neu, places=6)
        self.assertAlmostEqual(r_alt, (1.21 ** (365.25 / 731) - 1) * 100, places=6)

    def test_verlust_und_grenzen(self):
        heute = D(2026, 1, 1)
        z = [(D(2025, 1, 1), 1000.0)]
        self.assertAlmostEqual(A["rendite_pa_geldgewichtet"](z, 800.0, heute),
                               ((0.8) ** (365.25 / 365) - 1) * 100, places=4)
        self.assertIsNone(A["rendite_pa_geldgewichtet"]([], 100.0, heute))
        # unter 30 Tagen keine Jahresrendite, unter 1 Jahr als hochgerechnet markiert
        self.assertEqual(A["rendite_pa_seit_kauf"](100.0, 101.0, D(2025, 12, 20), heute,
                                                   zahlungen=[(D(2025, 12, 20), 100.0)], depotwert=101.0),
                         (None, False))
        r, hoch = A["rendite_pa_seit_kauf"](100.0, 101.0, D(2025, 10, 1), heute,
                                            zahlungen=[(D(2025, 10, 1), 100.0)], depotwert=101.0)
        self.assertTrue(hoch)
        self.assertGreater(r, 4.0)


class Zeitraeume(unittest.TestCase):
    def test_tag_woche_jahr_und_ytd(self):
        idx = pd.bdate_range("2024-12-02", "2026-03-13")
        kurse = pd.Series([100.0 + i * 0.1 for i in range(len(idx))], index=idx)
        heute = D(2026, 3, 13)
        z = dict((lbl, (d, p)) for lbl, d, p in A["berechne_zeitraeume"](130.0, 125.0, kurse, heute))
        self.assertAlmostEqual(z["Tag"][1], 4.0)                                  # 130/125 - 1
        ref_woche = float(kurse[kurse.index <= pd.Timestamp(2026, 3, 6)].iloc[-1])
        self.assertAlmostEqual(z["Woche"][0], 130.0 - ref_woche)
        ytd = float(kurse[kurse.index <= pd.Timestamp(2026, 1, 1)].iloc[-1])      # Schluss 31.12.2025
        self.assertAlmostEqual(z["Lfd. Jahr"][1], (130.0 / ytd - 1) * 100)
        ref_jahr = float(kurse[kurse.index <= pd.Timestamp(2025, 3, 13)].iloc[-1])
        self.assertAlmostEqual(z["Jahr"][1], (130.0 / ref_jahr - 1) * 100)

    def test_kurze_historie_ehrlich_beschriftet(self):
        idx = pd.bdate_range("2025-06-02", "2026-03-13")
        kurse = pd.Series(100.0, index=idx)
        zeilen = A["berechne_zeitraeume"](110.0, None, kurse, D(2026, 3, 13))
        labels = [z[0] for z in zeilen]
        self.assertNotIn("Jahr", labels)
        self.assertIn("seit 02.06.2025", labels)
        self.assertNotIn("Tag", labels)                                          # ohne Vortageskurs


class Einkommensteuer2026(unittest.TestCase):
    """§ 32a EStG 2026, eigene Umsetzung der Gesetzesformel als Referenz."""

    @staticmethod
    def _ref(x):
        x = int(x)
        if x <= 12348:
            return 0
        if x <= 17799:
            y = (x - 12348) / 10000
            return int((914.51 * y + 1400) * y)
        if x <= 69878:
            z = (x - 17799) / 10000
            return int((173.10 * z + 2397) * z + 1034.87)
        if x <= 277825:
            return int(0.42 * x - 11135.63)
        return int(0.45 * x - 19470.38)

    def test_tarif_alle_zonen(self):
        for x in (0, 12348, 12349, 15000, 17799, 17800, 40000, 69878, 69879, 100000, 277825, 277826, 500000):
            self.assertEqual(AB.est_tarif(x, 2026), self._ref(x), x)

    def test_splitting_und_fuenftel(self):
        self.assertEqual(AB.est(80000, splitting=True, jahr=2026), 2 * self._ref(40000))
        rest, abf = 40000, 60000
        basis = self._ref(rest)
        erwartet = basis + 5 * (self._ref(rest + abf / 5) - basis)
        self.assertEqual(AB.est_mit_abfindung(rest, abf, fuenftel=True, jahr=2026), min(erwartet, self._ref(rest + abf)))
        self.assertEqual(AB.est_mit_abfindung(rest, abf, fuenftel=False, jahr=2026), self._ref(rest + abf))

    def test_soli(self):
        self.assertEqual(AB.soli(20350, jahr=2026), 0.0)                             # Freigrenze
        self.assertAlmostEqual(AB.soli(21000, jahr=2026), round(0.119 * 650, 2), places=2)   # Milderungszone
        self.assertAlmostEqual(AB.soli(100000, jahr=2026), 5500.0, places=2)          # voller Satz 5,5 %


class Zinseszins(unittest.TestCase):
    def _p(self, **kw):
        p = dict(Z.STANDARD, sd="2026-01-01")
        p.update(kw)
        return p

    def test_einmalanlage_jaehrliche_gutschrift(self):
        r = Z.rechne(self._p(a=10000.0, s=0.0, z=3.0, n=10, st=0.0))
        self.assertAlmostEqual(r["end"], 10000 * 1.03 ** 10, delta=0.05)          # Cent-Rundung je Gutschrift

    def test_monatliche_rate_ein_jahr_nachschuessig(self):
        # 12 x 100 EUR am Monatsende, 3 % p. a., unterjaehrig linear: Zins = 100*0,0025*(11+10+...+0) = 16,50
        r = Z.rechne(self._p(a=0.0, s=100.0, z=3.0, n=1, ea="n", st=0.0))
        self.assertAlmostEqual(r["end"], 1216.50, places=2)
        self.assertAlmostEqual(r["einzahlungen"], 1200.0)

    def test_monatliche_rate_ein_jahr_vorschuessig(self):
        # Einzahlung am Monatsanfang: Zins = 100*0,0025*(12+11+...+1) = 19,50
        r = Z.rechne(self._p(a=0.0, s=100.0, z=3.0, n=1, ea="v", st=0.0))
        self.assertAlmostEqual(r["end"], 1219.50, places=2)

    def test_abgeltungsteuer_mit_freibetrag(self):
        # 100.000 EUR, 3 %: Zins 3.000, Freibetrag 1.000 -> Steuer 26,375 % auf 2.000 = 527,50
        r = Z.rechne(self._p(a=100000.0, s=0.0, z=3.0, n=1, st=26.375, fb=1000.0))
        self.assertAlmostEqual(r["steuer"], 527.50, places=2)
        self.assertAlmostEqual(r["end"], 102472.50, places=2)


class Scanner2Modell(unittest.TestCase):
    def test_endwert_monatliche_verzinsung(self):
        # 10.000 EUR + 100 EUR/Monat, 6 % nominal (0,5 % je Monat), 24 Monate:
        # FV = 10000*1,005^24 + 100*(1,005^24-1)/0,005
        f = 1.005 ** 24
        erwartet = 10000 * f + 100 * (f - 1) / 0.005
        self.assertAlmostEqual(IS2.simulate_flows(10000, 0, 24, 100, 0.06, None)["value"], erwartet, places=6)

    def test_noetige_rendite_trifft_ziel(self):
        r = IS2.required_rate(10000, 0, 120, 0, 20000, None)
        self.assertAlmostEqual((1 + r / 12) ** 120, 2.0, places=6)                 # Verdopplung in 10 Jahren
        self.assertIsNone(IS2.required_rate(0, 0, 12, 0, 1000, None))
        self.assertEqual(IS2.required_rate(1000, 0, 12, 0, 0, None), 0.0)


class Rundung(unittest.TestCase):                           # F-07
    def test_kaufmaennisch_halbe_cents_aufwaerts(self):
        self.assertEqual(_A["fmt"](2.675), "2,68€")
        self.assertEqual(_A["fmt"](1.005), "1,01€")
        self.assertEqual(_A["fmt"](-2.675), "-2,68€")
        self.assertEqual(_A["fmt"](1234567.125), "1.234.567,13€")
        self.assertEqual(_A["fmt_vz"](-0.004), "+0,00€")             # nie "-0,00€"
        self.assertEqual(_A["vz_zahl"](0.125, 2), "+0,13")
        self.assertEqual(_A["fmt"](0.5, 0), "1€")


if __name__ == "__main__":
    unittest.main()
