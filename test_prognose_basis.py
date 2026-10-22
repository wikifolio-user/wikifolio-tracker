"""Tests Prognose-Basis der Zukunfts-Prognose (synthetische Daten)."""
import unittest

import prognose_basis as PB


KATALOG = [{"felder": ["typ", "kat", "name", "kennung", "isin"],
            "zeilen": [["wikifolio", "", "FF Inlinetrading", "LS9VSU", "DE000LS9VSU0"],
                       ["ETF", "", "iShares Core MSCI World", "A0RPWH", "IE00B4L5Y983"],
                       ["Aktie", "", "SAP", "716460", "DE0007164600"],
                       ["Aktie", "", "SAP doppelt", "716460", ""],
                       ["Anleihe", "", "Bund 2030", "113550", ""]]}]


class Optionen(unittest.TestCase):
    def test_arten_ids_ohne_doppelte(self):
        o = PB.top500_optionen(KATALOG, {"LS9VSU": 101, "IE00B4L5Y983": 202})
        self.assertEqual([w["name"] for w in o], ["FF Inlinetrading", "iShares Core MSCI World", "SAP"])
        ids = {w["name"]: w["instrument_id"] for w in o}
        self.assertEqual(ids, {"FF Inlinetrading": 101, "iShares Core MSCI World": 202, "SAP": None})


class Liste(unittest.TestCase):
    def test_hinzufuegen_entfernen(self):
        w = {"name": "FF Inlinetrading", "wkn": "LS9VSU", "isin": "DE000LS9VSU0", "instrument_id": 101}
        l1 = PB.hinzufuegen([], PB.eintrag(w, 1))
        self.assertEqual(len(l1), 1)
        self.assertIsNone(PB.hinzufuegen(l1, PB.eintrag(dict(w, instrument_id=999), 2)))   # gleiche WKN
        self.assertIsNone(PB.hinzufuegen(l1, PB.eintrag(dict(w, wkn="X", isin="Y"), 3)))    # gleiche Kurs-ID
        self.assertTrue(PB.enthalten(l1, {"isin": "de000ls9vsu0"}))
        self.assertEqual(PB.entfernen(l1, l1[0]["id"]), [])
        self.assertIsNone(PB.entfernen(l1, "gibt-es-nicht"))

    def test_obergrenze_und_ohne_id(self):
        voll = [{"id": str(i), "instrument_id": i, "wkn": f"W{i}"} for i in range(PB.MAX_EINTRAEGE)]
        self.assertIsNone(PB.hinzufuegen(voll, {"id": "x", "instrument_id": 999, "wkn": "NEU"}))
        self.assertIsNone(PB.hinzufuegen([], {"id": "x", "instrument_id": None, "wkn": "NEU"}))

    def test_start_aus_beobachtung(self):
        b = [{"id": "b1", "name": "A", "wkn": "LS9AAA", "instrument_id": 5}, {"name": "ohne ID", "wkn": "X"}]
        self.assertEqual(PB.start_aus_beobachtung(b),
                         [{"id": "b1", "name": "A", "wkn": "LS9AAA", "isin": "", "instrument_id": 5}])


if __name__ == "__main__":
    unittest.main()
