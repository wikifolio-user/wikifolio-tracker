"""Analyse-Depot (python3 -m unittest test_analyse_depot)."""
import datetime
import unittest

import analyse_depot as A
import depot_analyse as D


class Position(unittest.TestCase):
    def test_pruefung(self):
        p, f = A.position("MSCI World", "10,5", "85,40", "15.03.2024", "a0rpwh", "ie00b4l5y983", "44039", "etf")
        self.assertIsNone(f)
        self.assertEqual((p["stueck"], p["kaufkurs"], p["kaufdatum"], p["wkn"], p["isin"], p["instrument_id"],
                          p["art"]), (10.5, 85.4, "2024-03-15", "A0RPWH", "IE00B4L5Y983", 44039, "etf"))
        self.assertIsNotNone(A.position("X", 0)[1])
        self.assertIsNotNone(A.position("", 1)[1])
        self.assertIsNotNone(A.position("X", 1, -5)[1])
        morgen = datetime.date.today() + datetime.timedelta(days=1)
        self.assertIsNotNone(A.position("X", 1, 1, morgen)[1])
        self.assertIsNone(A.position("X", 1, None, None, art="quatsch")[0]["art"] or None)

    def test_bereinigen(self):
        d = A.bereinigen({"positionen": [{"name": "A", "stueck": 2, "id": "x1"}, {"name": "kaputt", "stueck": 0}],
                          "sparplan": {"rate": "50", "ziel": "gibtsnicht"}, "entnahme": {"rate": -3}})
        self.assertEqual([p["id"] for p in d["positionen"]], ["x1"])
        self.assertEqual((d["sparplan"]["rate"], d["sparplan"]["ziel"], d["entnahme"]["rate"]), (50.0, "", 0.0))
        self.assertEqual(A.bereinigen(None), A.leer())


class Schnelleingabe(unittest.TestCase):
    def test_formate(self):
        z, f = A.schnelleingabe("IE00B4L5Y983; 25; 85,40; 15.03.2024\nSiemens; 10\nA0RPWH\t5\t70,10\n"
                                "SAP 3\n# Kommentar\n\nNull; 0\nFalsch; 2; 10; 99.99.2024")
        self.assertEqual([x["kennung"] for x in z], ["IE00B4L5Y983", "Siemens", "A0RPWH", "SAP", "Falsch"])
        self.assertEqual((z[0]["stueck"], z[0]["kaufkurs"], str(z[0]["kaufdatum"])), (25.0, 85.4, "2024-03-15"))
        self.assertEqual((z[1]["kaufkurs"], z[1]["kaufdatum"]), (None, None))
        self.assertEqual(z[2]["kaufkurs"], 70.1)
        self.assertEqual(z[3]["stueck"], 3.0)
        self.assertEqual(len(f), 2)                     # Null-Stueck und falsches Datum


class Zusammenfuehren(unittest.TestCase):
    def test_gleicher_wert_wird_addiert(self):
        a = A.position("A", 10, 100, "2024-01-01", isin="X1", instrument_id=1)[0]
        b = A.position("A", 30, 120, "2023-06-01", isin="X1", instrument_id=1)[0]
        c = A.position("B", 5, 10, isin="X2", instrument_id=2)[0]
        z = A.zusammenfuehren([a], [b, c])
        self.assertEqual(len(z), 2)
        self.assertEqual(z[0]["stueck"], 40)
        self.assertAlmostEqual(z[0]["kaufkurs"], (10 * 100 + 30 * 120) / 40)
        self.assertEqual(z[0]["kaufdatum"], "2023-06-01")
        self.assertEqual(a["stueck"], 10)               # Eingabe unveraendert


class Bestand(unittest.TestCase):
    def test_fuer_depot_analyse(self):
        d = A.leer()
        d["positionen"] = [A.position("Welt ETF", 10, 80, "2024-01-01", "A0RPWH", "IE00B4L5Y983", 1, "etf")[0],
                           A.position("Ohne Kurs", 5, 10, instrument_id=2)[0],
                           A.position("Ohne Einstand", 2, None, instrument_id=3)[0]]
        b = A.bestand(d, {1: (100.0, 99.0), 3: (50.0, 50.0)})
        self.assertEqual((b[0]["wert"], b[0]["einstand"], b[0]["art_vorgabe"]), (1000.0, 800.0, "etf"))
        self.assertTrue(b[1]["ohne_kurs"])
        self.assertIsNone(b[2]["einstand"])
        k = D.kennzahlen([D.anreichern(x, D.marktdaten_index({}), {"art": x.get("art_vorgabe")}
                                       if x.get("art_vorgabe") else None) for x in b])
        self.assertAlmostEqual(k["gesamt"], 1100.0)
        self.assertAlmostEqual(k["gv"], 200.0)            # nur Welt ETF: 1000 - 800, ohne Einstand zaehlt nicht
        self.assertAlmostEqual(k["rendite"], 25.0)
        self.assertEqual(len(k["ohne_kurs"]), 1)

    def test_monatsplan(self):
        d = A.bereinigen({"sparplan": {"rate": 200}, "entnahme": {"rate": 50}})
        self.assertEqual(A.monatsplan(d), 150.0)


if __name__ == "__main__":
    unittest.main()
