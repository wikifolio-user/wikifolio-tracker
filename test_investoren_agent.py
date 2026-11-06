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


class Drosselung(unittest.TestCase):
    """Yahoo drosselt (YFRateLimitError): Pause, spaeter erneut versuchen, nie Teildaten speichern."""

    def setUp(self):
        self.uhr = [0.0]
        self.pausen = []
        self.alt = (A._uhr, A._schlafen, A.ABSTAND_SEK, A.ZEITBUDGET_SEK)

        def schlafen(t):
            self.pausen.append(t)
            self.uhr[0] += t
        A._uhr, A._schlafen, A.ABSTAND_SEK, A.ZEITBUDGET_SEK = (lambda: self.uhr[0]), schlafen, 0.0, 10000.0

    def tearDown(self):
        A._uhr, A._schlafen, A.ABSTAND_SEK, A.ZEITBUDGET_SEK = self.alt

    def test_gedrosselt_erkannt(self):
        from investor_checks import abruf as AB
        self.assertTrue(AB.gedrosselt({"fehlerarten": ["YFRateLimitError"]}))
        self.assertFalse(AB.gedrosselt({"fehlerarten": ["TimeoutError"]}))
        self.assertFalse(AB.gedrosselt({}))

    def test_pause_und_wiederholung(self):
        import threading
        sperre, aufrufe = threading.Lock(), {}

        def fn(s):
            with sperre:
                aufrufe[s] = aufrufe.get(s, 0) + 1
                erster = aufrufe[s] == 1
            return A.DROSSEL if s in ("B", "C") and erster else {"id": s}
        gespeichert = {}
        st = A.abarbeiten(list("ABCDE"), fn, lambda s, r, n: gespeichert.__setitem__(s, r), start=0.0)
        self.assertEqual(sorted(gespeichert), list("ABCDE"))      # B und C beim zweiten Versuch
        self.assertEqual((st["neu"], st["fehler"], st["drossel"], st["offen"]), (5, 0, 2, 0))
        self.assertGreaterEqual(st["pausen"], 1)
        self.assertEqual(self.pausen[0], A.PAUSE_START)

    def test_dauerhaft_gedrosselt_kein_eintrag(self):
        gespeichert = {}
        st = A.abarbeiten(["X"], lambda s: A.DROSSEL, lambda s, r, n: gespeichert.__setitem__(s, r), start=0.0)
        self.assertEqual(gespeichert, {})
        self.assertEqual((st["drossel"], st["fehler"]), (1 + A.WIEDERHOLUNGEN, 1))
        self.assertEqual(self.pausen, [60.0, 120.0, 240.0])          # wachsende Pause

    def test_zeitbudget_beendet_statt_pause(self):
        A.ZEITBUDGET_SEK = 30.0
        st = A.abarbeiten(["X", "Y"], lambda s: A.DROSSEL, lambda *a: None, start=0.0)
        self.assertEqual(self.pausen, [])
        self.assertEqual(st["neu"], 0)

    def test_bewerte_speichert_bei_drosselung_nichts(self):
        from investor_checks import abruf as AB
        alt = AB.roh_laden
        AB.roh_laden = lambda sym, parallel=4: {"info": {"symbol": sym}, "fehler": ["gj"],
                                                 "fehlerarten": ["YFRateLimitError"]}
        try:
            self.assertEqual(A.bewerte({"ticker": "X"}, None, None, {}, {}, {}, datetime.date(2026, 11, 6)),
                             A.DROSSEL)
        finally:
            AB.roh_laden = alt


if __name__ == "__main__":
    unittest.main()
