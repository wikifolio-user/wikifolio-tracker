"""Investoren-Agent (Vorberechnung fuer den Legenden-Screener): Reihenfolge, Kurzform, Mediane - ohne Netz."""
import datetime
import unittest

import investor_checks as IC
import investoren_agent as A
from investor_checks import konsens as KO

import test_investor_checks as T


class Plan(unittest.TestCase):
    def test_fehlende_zuerst_dann_aelteste(self):
        heute = datetime.date(2026, 10, 28)
        aktien = [{"ticker": s} for s in ("A", "B", "C", "D")]
        alte = {"A": {"st": "2026-10-27"}, "B": {"st": "2026-09-01"}, "C": {"st": "2026-10-01"}}
        self.assertEqual(A.faellige(aktien, alte, heute, 10), ["D", "B", "C"])     # A ist frisch
        self.assertEqual(A.faellige(aktien, alte, heute, 2), ["D", "B"])

    def test_groesste_zuerst(self):
        aktien = [{"ticker": "K", "info": {"mcap": 1}}, {"ticker": "G", "info": {"mcap": 900}}, {"ticker": "O"}]
        self.assertEqual(A.faellige(aktien, {}, datetime.date(2026, 1, 1), 5), ["G", "K", "O"])

    def test_teil_stabil(self):
        self.assertEqual(A.teil("AAPL"), A.teil("AAPL"))
        self.assertTrue(0 <= A.teil("SAP.DE") < A.TEILE)

    def test_fue_median(self):
        w = {str(i): {"fue": float(i), "sek": "Software"} for i in range(5)}
        w["x"] = {"fue": 9.0, "sek": "Banken"}
        self.assertEqual(A.fue_mediane(w), {"Software": 2.0})       # Banken: zu wenige Werte


class Kurzform(unittest.TestCase):
    def test_felder(self):
        f = T.firma()
        k = KO.kurzform(IC.alle_checks(f, {}), {"median": 30.0, "kurs": 20.0}, f)
        self.assertIn(k["note"], list("ABCDEF"))
        self.assertEqual(k["fv"], 50.0)                              # fairer Wert 50 % ueber Kurs
        self.assertEqual(k["fue"], 8.0)                              # 80 / 1000
        self.assertEqual(set(k["c"]), set(IC.REGISTRY))
        self.assertEqual(len(k["c"]["graham"]), 3)


if __name__ == "__main__":
    unittest.main()
