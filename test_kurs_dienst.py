"""Kursdienst (python3 -m unittest test_kurs_dienst)."""
import threading
import time
import unittest

from kurs_dienst import KursDienst


class Dienst(unittest.TestCase):
    def setUp(self):
        self.aufrufe = []
        self.kurs = {"1": 10.0, "2": 20.0}
        self.kaputt = set()

        def live(i):
            self.aufrufe.append(i)
            if i in self.kaputt:
                raise ConnectionError("weg")
            return self.kurs[i]
        self.d = KursDienst({"live": live})

    def test_hole_merkt_und_ruft_nur_einmal_ab(self):
        self.assertEqual(self.d.hole("live", 1), 10.0)
        self.assertEqual(self.d.hole("live", "1"), 10.0)
        self.assertEqual(self.aufrufe, ["1"])
        self.assertEqual(self.d.status()["werte"], 1)

    def test_fehler_wird_nicht_gemerkt(self):
        self.kaputt.add("2")
        with self.assertRaises(ConnectionError):
            self.d.hole("live", 2)
        self.kaputt.clear()
        self.assertEqual(self.d.hole("live", 2), 20.0)

    def test_lauf_aktualisiert_alle_und_behaelt_alte_bei_fehler(self):
        self.d.hole("live", 1)
        self.d.hole("live", 2)
        self.kurs.update({"1": 11.0, "2": 21.0})
        self.kaputt.add("2")
        self.assertTrue(self.d.aktualisieren(warten=True))
        self.assertEqual(self.d.hole("live", 1), 11.0)
        self.assertEqual(self.d.hole("live", 2), 20.0)          # alter echter Wert bleibt
        st = self.d.status()
        self.assertFalse(st["laeuft"])
        self.assertEqual((st["letzter_fehler"], st["werte"]), (1, 2))
        self.assertIsNotNone(st["letzter_lauf"])

    def test_vorgemerkt_wird_im_lauf_geladen(self):
        self.d.merken("live", 1)
        self.assertEqual(self.d.status()["ohne_wert"], 1)
        self.d.aktualisieren(warten=True)
        self.assertEqual(self.d.status()["werte"], 1)
        self.assertEqual(self.aufrufe, ["1"])

    def test_nur_ein_lauf_gleichzeitig(self):
        sperre = threading.Event()

        def langsam(i):
            sperre.wait(5)
            return 1.0
        d = KursDienst({"live": langsam})
        d.merken("live", 1)
        self.assertTrue(d.aktualisieren())
        self.assertTrue(d.laeuft())
        self.assertFalse(d.aktualisieren())                    # blockiert, solange der Lauf laeuft
        self.assertEqual(d.status()["gesamt"], 1)
        sperre.set()
        for _ in range(100):
            if not d.laeuft():
                break
            time.sleep(0.02)
        self.assertFalse(d.laeuft())
        self.assertTrue(d.aktualisieren(warten=True))

    def test_zeitplan(self):
        self.d.merken("live", 1)
        faellig = []

        def f(letzter):
            faellig.append(letzter)
            return letzter is None
        self.assertTrue(self.d.zeitplan_starten(f, pruef_sek=0.01))
        self.assertFalse(self.d.zeitplan_starten(f))           # einmal je Prozess
        for _ in range(200):
            if self.d.status()["letzter_lauf"] is not None and len(faellig) > 2:
                break
            time.sleep(0.01)
        self.assertEqual(self.aufrufe, ["1"])                   # genau ein Lauf


if __name__ == "__main__":
    unittest.main()
