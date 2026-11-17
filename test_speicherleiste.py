"""Tests fuer speicherleiste.py - ohne Streamlit."""
import copy
import unittest

import speicherleiste as SL


class Speicher:
    """gh_aktualisiere-Attrappe: eine Datei im Speicher."""
    def __init__(self, inhalt=None, ok=True):
        self.inhalt, self.ok, self.schreibvorgaenge = copy.deepcopy(inhalt), ok, 0

    def __call__(self, pfad, aendern, default=None, message=""):
        if not self.ok:
            return False, None
        neu = aendern(copy.deepcopy(self.inhalt if self.inhalt is not None else default))
        if neu is None:
            return True, self.inhalt
        self.inhalt = copy.deepcopy(neu)
        self.schreibvorgaenge += 1
        return True, neu


class Ablauf(unittest.TestCase):
    def test_speichern_und_zuruecknehmen(self):
        ss, sp = {}, Speicher({"x": 1})
        SL.aktualisieren(ss, "b", sp, "p", lambda a: dict(a, x=2))
        SL.aktualisieren(ss, "b", sp, "p", lambda a: dict(a, x=3))
        self.assertEqual(SL.schritte(ss, "b"), 2)
        self.assertEqual(SL.statustext(ss, "b")[0], "✓")
        self.assertEqual(SL.zuruecknehmen(ss, "b", sp, "p"), {"x": 2})
        self.assertEqual(sp.inhalt, {"x": 2})
        self.assertEqual(SL.zuruecknehmen(ss, "b", sp, "p"), {"x": 1})
        self.assertEqual(sp.inhalt, {"x": 1})
        self.assertIsNone(SL.zuruecknehmen(ss, "b", sp, "p"))      # nichts mehr da

    def test_unveraendert_kein_schritt(self):
        ss, sp = {}, Speicher({"x": 1})
        SL.aktualisieren(ss, "b", sp, "p", lambda a: dict(a))
        SL.aktualisieren(ss, "b", sp, "p", lambda a: None)          # aendern liefert None: nichts geschrieben
        self.assertEqual(SL.schritte(ss, "b"), 0)

    def test_hoechstens_max_schritte(self):
        ss, sp = {}, Speicher({"x": 0})
        for i in range(SL.MAX_SCHRITTE + 5):
            SL.aktualisieren(ss, "b", sp, "p", lambda a, i=i: {"x": i + 1})
        self.assertEqual(SL.schritte(ss, "b"), SL.MAX_SCHRITTE)

    def test_fehler_beim_speichern(self):
        ss = {}
        ok, _ = SL.aktualisieren(ss, "b", Speicher({"x": 1}, ok=False), "p", lambda a: {"x": 2})
        self.assertFalse(ok)
        self.assertEqual(SL.statustext(ss, "b")[0], "⚠️")
        self.assertEqual(SL.schritte(ss, "b"), 0)

    def test_fehler_beim_zuruecknehmen_behaelt_stapel(self):
        ss, sp = {}, Speicher({"x": 1})
        SL.aktualisieren(ss, "b", sp, "p", lambda a: {"x": 2})
        sp.ok = False
        self.assertIsNone(SL.zuruecknehmen(ss, "b", sp, "p"))
        self.assertEqual(SL.schritte(ss, "b"), 1)
        self.assertEqual(SL.statustext(ss, "b")[0], "⚠️")

    def test_ausnahme_im_speicher(self):
        def kaputt(*a, **k):
            raise RuntimeError("weg")
        ss = {}
        self.assertEqual(SL.aktualisieren(ss, "b", kaputt, "p", lambda a: a), (False, None))
        self.assertEqual(SL.statustext(ss, "b")[0], "⚠️")

    def test_texte(self):
        ss = {}
        self.assertEqual(SL.statustext(ss, "b", "sitzung")[1], SL.TEXT_SITZUNG)
        SL.geaendert(ss, "b")
        self.assertEqual(SL.statustext(ss, "b"), ("●", "Ungespeicherte Änderungen"))
        SL.gespeichert(ss, "b", {"a": 1})
        self.assertTrue(SL.statustext(ss, "b")[1].startswith("Gespeichert um "))
        self.assertEqual(SL.schritte(ss, "b"), 1)

    def test_bereiche_getrennt(self):
        ss, sp = {}, Speicher({"x": 1})
        SL.aktualisieren(ss, "a", sp, "p", lambda a: {"x": 2})
        self.assertEqual((SL.schritte(ss, "a"), SL.schritte(ss, "b")), (1, 0))


if __name__ == "__main__":
    unittest.main()
