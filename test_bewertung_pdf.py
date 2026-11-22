"""Tests fuer den PDF-Bericht der Bewertung (bewertung_pdf.py)."""
import datetime
import unittest

import bewertung_pdf as PDF
import investor_checks as I
from investor_checks import fairer_wert as FW
from investor_checks import konsens as KO
from test_investor_checks import firma


def _eintrag(art="aktie", **kw):
    e = {"id": "X1", "art": art, "name": "Muster & Söhne AG „Test“", "ticker": "MUS.DE", "wkn": "A1B2C3",
         "isin": "DE000A1B2C30", "sektor": "Industrials", "kurs": 123.45, "waehrung": "EUR", "tag": -1.2,
         "info": {}}
    e.update(kw)
    return e


def _bewertung(kategorien=None):
    kat = kategorien or [
        {"key": "bewertung", "titel": "Bewertung", "score": 72.0, "anzahl": 2, "von": 7, "gewicht": 25},
        {"key": "qualitaet", "titel": "Qualität & Profitabilität", "score": 40.0, "anzahl": 1, "von": 5,
         "gewicht": 20},
        {"key": "wachstum", "titel": "Wachstum", "score": None, "anzahl": 0, "von": 4, "gewicht": 15},
        {"key": "momentum", "titel": "Momentum & Technik", "score": 20.0, "anzahl": 1, "von": 6, "gewicht": 15}]
    zahlen = [
        {"key": "kgv", "titel": "KGV (erwartet)", "wert": 12.5, "format": "x", "kategorie": "bewertung",
         "perzentil": 80.0, "einordnung": "gut", "median": 17.0, "basis": "sektor", "richtung": -1},
        {"key": "fcf_y", "titel": "Free-Cashflow-Rendite", "wert": None, "format": "pct", "kategorie": "bewertung",
         "perzentil": None, "einordnung": "n/a", "median": 3.1, "basis": "alle", "richtung": 1},
        {"key": "roe", "titel": "Eigenkapitalrendite (ROE)", "wert": 9.0, "format": "pct", "kategorie": "qualitaet",
         "perzentil": 40.0, "einordnung": "neutral", "median": 9.5, "basis": "alle", "richtung": 1},
        {"key": "m1", "titel": "Kurs 1 Monat", "wert": -12.0, "format": "pct", "kategorie": "momentum",
         "perzentil": 10.0, "einordnung": "schlecht", "median": 1.0, "basis": "alle", "richtung": 1}]
    return {"gesamt": 55.0, "ampel": "gelb", "fazit": "unterbewertet", "abdeckung": (4, 22), "kategorien": kat,
            "kennzahlen": zahlen, "staerken": [zahlen[0]], "schwaechen": [zahlen[3]]}


def _investoren():
    f = firma()
    erg = I.alle_checks(f, {})
    return {"ergebnisse": erg, "konsens": KO.konsens(erg), "fair": FW.uebersicht(f, {}),
            "ibd": {"eps": 81, "composite": 74, "teile": {"eps": 81, "rs": 60, "branche": None, "smr": 70,
                                                          "ad": 55, "hoch": 90}},
            "waehrung": f.get("waehrung") or ""}


class Bericht(unittest.TestCase):
    def test_aktie_mit_investoren(self):
        pdf = PDF.bericht(_eintrag(), _bewertung(), "21.11.2026", _investoren(),
                          erstellt=datetime.datetime(2026, 11, 22, 9, 30))
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 5000)

    def test_ohne_investoren_etf_und_wikifolio(self):
        for art in ("aktie", "etf", "wikifolio"):
            pdf = PDF.bericht(_eintrag(art, sektor=None if art != "aktie" else "Tech"), _bewertung(), "21.11.2026")
            self.assertTrue(pdf.startswith(b"%PDF-"), art)

    def test_ohne_gesamtscore_und_wenige_teilscores(self):
        b = _bewertung([{"key": "dividende", "titel": "Dividende", "score": 74.0, "anzahl": 1, "von": 2,
                         "gewicht": 10}])
        b.update(gesamt=None, ampel="grau", fazit=None, staerken=[], schwaechen=[])
        self.assertTrue(PDF.bericht(_eintrag(), b, "21.11.2026").startswith(b"%PDF-"))

    def test_investoren_ohne_daten(self):
        inv = {"ergebnisse": [], "konsens": KO.konsens([]), "fair": {"modelle": [], "median": None, "kurs": None},
               "ibd": None, "waehrung": ""}
        self.assertTrue(PDF.bericht(_eintrag(), _bewertung(), "21.11.2026", inv).startswith(b"%PDF-"))

    def test_sonderzeichen_werden_ersetzt(self):
        self.assertEqual(PDF._roh("a − b → c ≥ d"), "a - b -> c >= d")
        self.assertEqual(PDF._t("A & B <x>"), "A &amp; B &lt;x&gt;")
        self.assertEqual(PDF._roh("Ölpreis – Größe"), "Ölpreis - Größe")

    def test_dateiname(self):
        heute = datetime.date(2026, 11, 22)
        self.assertEqual(PDF.dateiname(_eintrag(), heute), "Bewertung_MUS.DE_2026-11-22.pdf")
        self.assertEqual(PDF.dateiname(_eintrag(ticker="", wkn="", isin="", name="A/B C"), heute),
                         "Bewertung_A_B_C_2026-11-22.pdf")

    def test_fairer_wert_zeilen(self):
        z = PDF._fair_zeilen({"kurs": 100.0, "modelle": [{"methode": "Graham", "wert": 120.0},
                                                         {"methode": "DCF", "wert": None},
                                                         {"methode": "EPV", "wert": 80.0}]}, "EUR")
        self.assertEqual([r[0] for r in z], ["Graham", "EPV"])
        self.assertEqual([r[2] for r in z], ["+20 %", "-20 %"])


if __name__ == "__main__":
    unittest.main()
