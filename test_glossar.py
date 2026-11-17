"""Tests fuer glossar.py - ohne Streamlit."""
import os
import unittest

import glossar as G

HIER = os.path.dirname(os.path.abspath(__file__))


class Inhalt(unittest.TestCase):
    def test_audit_begriffe_erklaert(self):
        # Audit UX-04: "NPV, IRR, XIRR, Sloan-Accruals, ROTC sind nur teilweise erklaert"
        for b in ("NPV", "IRR", "XIRR", "Sloan", "Accruals", "ROTC", "KGV", "KBV", "Drawdown", "TER",
                  "Fünftelregelung", "Monte Carlo", "F-Score", "Z-Score", "Margin of Safety"):
            self.assertTrue(len(G.erklaerung(b)) > 60, b)

    def test_jeder_begriff_mit_bereich_und_text(self):
        for k, (bereich, text) in G.BEGRIFFE.items():
            self.assertIn(bereich, G.BEREICHE, k)
            self.assertGreater(len(text), 40, k)
            self.assertTrue(text.rstrip().endswith((".", ")")), k)

    def test_aliase_zeigen_auf_begriffe(self):
        for a, k in G.ALIASE.items():
            self.assertIn(k, G.BEGRIFFE, a)

    def test_ansicht_begriffe_alle_bekannt(self):
        for ansicht, liste in G.ANSICHT_BEGRIFFE.items():
            for b in liste:
                self.assertIsNotNone(G.finde(b), f"{ansicht}: {b}")

    def test_ansichtsnamen_gibt_es_in_der_app(self):
        quelle = open(os.path.join(HIER, "app.py"), encoding="utf-8").read()
        for ansicht in G.ANSICHT_BEGRIFFE:
            self.assertIn(f'"{ansicht}"', quelle, ansicht)


class Funktionen(unittest.TestCase):
    def test_finde_gross_klein(self):
        self.assertEqual(G.finde("kgv"), "KGV")
        self.assertEqual(G.finde("xirr"), "XIRR (geldgewichtete Rendite)")
        self.assertIsNone(G.finde("gibt es nicht"))
        self.assertEqual(G.erklaerung("gibt es nicht"), "")

    def test_fuer_ansicht_ohne_doppelte(self):
        f = G.fuer_ansicht("🏠 Depot")
        namen = [n for n, _ in f]
        self.assertEqual(len(namen), len(set(namen)))
        self.assertIn("XIRR (geldgewichtete Rendite)", namen)
        self.assertEqual(G.fuer_ansicht("unbekannt"), [])
        self.assertEqual(G.fuer_ansicht(None), [])

    def test_suchen(self):
        self.assertEqual(len(G.suchen("")), len(G.BEGRIFFE))
        self.assertEqual(G.suchen("sloan")[0][0], "Accrual-Quote (Sloan)")      # ueber den Alias
        t = [n for n, _, _ in G.suchen("insolvenz")]                            # nur im Erklaerungstext
        self.assertIn("Altman Z-Score", t)
        self.assertEqual(G.suchen("xyzxyz"), [])


if __name__ == "__main__":
    unittest.main()
