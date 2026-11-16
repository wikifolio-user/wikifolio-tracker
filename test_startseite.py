"""Tests fuer startseite.py (Ueberblick-Kacheln der Startseite) - ohne Streamlit, ohne Netz."""
import unittest

import startseite as S
from eks_rechner import modell as M


def _eintrag(kategorie, titel, datum="2026-11-16", zeit="09:25"):
    return {"kategorie": kategorie, "titel": titel, "datum": datum, "zeit": zeit}


class Chronik(unittest.TestCase):
    def test_neuester_alarm_und_neuester_sonstiger_eintrag(self):
        liste = [_eintrag("zugang", "🔐 Anmeldung: anna", zeit=""), _eintrag("alarm", "🚨 Schwelle SAP"),
                 _eintrag("depot", "➕ Position angelegt: Allianz", "2026-11-15", "18:02"),
                 _eintrag("alarm", "🏆 Allzeithoch alt", "2026-11-01")]
        k = {x[0]: x for x in S.ueberblick_daten(liste, {})}
        self.assertEqual(k["alarm"][2:], ("🚨 Schwelle SAP", "16.11. 09:25 Uhr", "chronik"))
        self.assertEqual(k["chronik"][2:4], ("➕ Position angelegt: Allianz", "15.11. 18:02 Uhr"))

    def test_alte_manuelle_eintraege_ohne_kategorie_zaehlen_als_chronik(self):
        k = S.ueberblick_daten([{"titel": "Notiz", "datum": "2025-01-02", "typ": "Trade"}], None)
        self.assertEqual([(x[0], x[3]) for x in k], [("chronik", "02.01.")])

    def test_leer_und_kaputt(self):
        for liste in (None, [], {}, "x", [None, 3, "a"]):
            self.assertEqual(S.ueberblick_daten(liste, None), [])
        self.assertEqual(S.ueberblick_daten([_eintrag("zugang", "Anmeldung")], {}), [])


class Eks(unittest.TestCase):
    def _daten(self, n=2, verworfen=0):
        d = M.leer()
        for i in range(n):
            d["ideen"].append(M.neue_idee(f"Idee {i}", d["einstellungen"]))
        for i in range(verworfen):
            idee = M.neue_idee(f"Weg {i}", d["einstellungen"])
            idee["status"] = "verworfen"
            d["ideen"].append(idee)
        return d

    def test_ampeln_zaehlen_ohne_verworfene(self):
        k = S.ueberblick_daten([], self._daten(2, verworfen=1))
        self.assertEqual(len(k), 1)
        key, label, wert, sub, ziel = k[0]
        self.assertEqual((key, ziel, sub), ("eks", "eks", "2 aktive Ideen"))
        self.assertEqual(sum(int(t) for t in wert.split() if t.isdigit()), 2)

    def test_monatslauf_datum(self):
        d = self._daten(1)
        d["letzter_lauf"] = {"stand": "2026-11-01T06:17"}
        self.assertEqual(S.ueberblick_daten([], d)[0][3], "Monatslauf 01.11.")

    def test_nur_verworfene_keine_kachel(self):
        self.assertEqual(S.ueberblick_daten([], self._daten(0, verworfen=2)), [])


if __name__ == "__main__":
    unittest.main()
