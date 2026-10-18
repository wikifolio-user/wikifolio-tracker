"""Tests Portfolio Builder 2.0 - Referenzwerte unabhaengig mit geschlossenen Formeln gerechnet."""
import unittest

import portfolio_builder as P


def eingaben(**kw):
    e = P.standard()
    e.update({"anfangskapital": 0.0, "sonstiges_kapital": 0.0, "kredit_summe": 0.0, "kredit_rate": 0.0,
              "einzahlung": 0.0, "entnahme": 0.0, "ausgaben": 0.0, "rendite_pa": 0.0,
              "laufzeit": 10, "laufzeit_einheit": "Jahre"})
    e.update(kw)
    return e


class Simulation(unittest.TestCase):
    def test_nur_anfangskapital(self):
        r = P.simulation(eingaben(anfangskapital=10000, rendite_pa=6))
        self.assertAlmostEqual(r["endwert"], 10000 * 1.06 ** 10, places=6)

    def test_sparrate_nachschuessig(self):
        r = P.simulation(eingaben(einzahlung=300, rendite_pa=6))
        rm = 1.06 ** (1 / 12) - 1
        self.assertAlmostEqual(r["endwert"], 300 * ((1 + rm) ** 120 - 1) / rm, places=6)
        self.assertAlmostEqual(r["summen"]["einzahlung"], 36000, places=6)

    def test_standardwerte(self):
        r = P.simulation(P.standard())
        rm = 1.06 ** (1 / 12) - 1
        erwartet = 10000 * 1.06 ** 10 + 300 * ((1 + rm) ** 120 - 1) / rm
        self.assertAlmostEqual(r["endwert"], erwartet, places=6)

    def test_entnahme_und_ausgaben_mindern(self):
        r = P.simulation(eingaben(anfangskapital=50000, entnahme=200, ausgaben=50, laufzeit=24,
                                  laufzeit_einheit="Monate"))
        self.assertAlmostEqual(r["endwert"], 50000 - 24 * 250, places=6)
        self.assertAlmostEqual(r["cashflow_monat"], -250, places=6)

    def test_laufzeit_in_monaten(self):
        r = P.simulation(eingaben(anfangskapital=1000, rendite_pa=12, laufzeit=6, laufzeit_einheit="Monate"))
        self.assertEqual(r["monate"], 6)
        self.assertAlmostEqual(r["endwert"], 1000 * 1.12 ** 0.5, places=6)

    def test_fehlbetrag_depot_nie_negativ(self):
        r = P.simulation(eingaben(anfangskapital=1000, entnahme=200, laufzeit=12, laufzeit_einheit="Monate"))
        self.assertEqual(r["endwert"], 0.0)
        self.assertAlmostEqual(r["summen"]["fehlbetrag"], 12 * 200 - 1000, places=6)
        self.assertTrue(all(z["portfolio"] >= 0 for z in r["verlauf"]))


class Kredit(unittest.TestCase):
    def test_annuitaet(self):
        # 10.000 EUR, 6 % p.a., 24 Monate: Rate nach Annuitaetenformel
        i = 0.06 / 12
        self.assertAlmostEqual(P.rate_fuer_tilgung(10000, 6, 24), 10000 * i / (1 - (1 + i) ** -24), places=9)
        self.assertAlmostEqual(P.rate_fuer_tilgung(12000, 0, 24), 500, places=9)

    def test_volltilgung_in_laufzeit(self):
        rate = P.rate_fuer_tilgung(20000, 5, 60)
        r = P.simulation(eingaben(anfangskapital=5000, kredit_summe=20000, kredit_zins_pa=5, kredit_rate=rate,
                                  laufzeit=5))
        self.assertAlmostEqual(r["restschuld"], 0.0, places=2)
        self.assertEqual(r["kredit"]["getilgt_monat"], 60)
        # ohne Rendite: Netto-Endvermoegen = Eigenkapital - gezahlte Zinsen
        self.assertAlmostEqual(r["netto_endvermoegen"], 5000 - r["summen"]["zinsen"], places=4)
        self.assertAlmostEqual(r["summen"]["kreditrate"], 20000 + r["summen"]["zinsen"], places=4)

    def test_kredit_zaehlt_nicht_doppelt(self):
        r = P.simulation(eingaben(anfangskapital=10000, kredit_summe=40000, kredit_zins_pa=0, laufzeit=1))
        self.assertAlmostEqual(r["anlagekapital"], 50000, places=6)
        self.assertAlmostEqual(r["eigenkapital"], 10000, places=6)
        self.assertAlmostEqual(r["verlauf"][0]["netto"], 10000, places=6)
        self.assertAlmostEqual(r["netto_endvermoegen"], 10000, places=6)   # ohne Zins, Rate, Rendite

    def test_zinsen_ohne_rate_erhoehen_schuld(self):
        r = P.simulation(eingaben(kredit_summe=10000, kredit_zins_pa=6, laufzeit=12, laufzeit_einheit="Monate"))
        self.assertTrue(r["kredit"]["rate_zu_klein"])
        self.assertAlmostEqual(r["restschuld"], 10000 * (1 + 0.06 / 12) ** 12, places=6)

    def test_letzte_rate_nur_rest(self):
        r = P.simulation(eingaben(anfangskapital=0, kredit_summe=1000, kredit_zins_pa=0, kredit_rate=300,
                                  laufzeit=12, laufzeit_einheit="Monate"))
        self.assertAlmostEqual(r["summen"]["kreditrate"], 1000, places=6)
        self.assertEqual(r["kredit"]["getilgt_monat"], 4)
        self.assertAlmostEqual(r["endwert"], 0.0, places=6)               # 1000 angelegt, 1000 getilgt


class Positionen(unittest.TestCase):
    def _e(self, **kw):
        e = eingaben(anfangskapital=10000, positionen=[
            {"name": "A", "kurs": 100.0, "gewicht": 50.0},
            {"name": "B", "kurs": 30.0, "gewicht": 30.0},
            {"name": "C", "kurs": 0.0, "gewicht": 10.0}])
        e.update(kw)
        return P.bereinigen(e)

    def test_betrag_stueck_wert(self):
        p = P.positionen(self._e())
        a, b, c = p["zeilen"]
        self.assertAlmostEqual(a["betrag"], 5000)
        self.assertAlmostEqual(a["stueck"], 50)
        self.assertAlmostEqual(b["stueck"], 100)
        self.assertEqual(c["stueck"], 0.0)                 # ohne Kurs keine Stuecke
        self.assertAlmostEqual(p["summe_gewicht"], 90)
        self.assertAlmostEqual(p["cash"], 10000 - 5000 - 3000)

    def test_ganze_stuecke(self):
        e = self._e(nur_ganze_stuecke=True)
        e["positionen"][1]["kurs"] = 33.0
        p = P.positionen(e)
        self.assertEqual(p["zeilen"][1]["stueck"], 90)     # 3000 / 33 = 90,9 -> 90
        self.assertAlmostEqual(p["zeilen"][1]["wert"], 2970)

    def test_kredit_wird_mit_angelegt(self):
        p = P.positionen(self._e(kredit_summe=10000))
        self.assertAlmostEqual(p["zeilen"][0]["betrag"], 10000)

    def test_stueck_aendern(self):
        e = self._e()
        neu = P.aenderungen_anwenden(e["positionen"], 10000, geaendert={0: {"stueck": 20}})
        self.assertAlmostEqual(neu[0]["gewicht"], 20.0)    # 20 x 100 / 10.000

    def test_betrag_aendern(self):
        e = self._e()
        neu = P.aenderungen_anwenden(e["positionen"], 10000, geaendert={"1": {"betrag": 1500}})
        self.assertAlmostEqual(neu[1]["gewicht"], 15.0)

    def test_gewicht_und_kurs(self):
        e = self._e()
        neu = P.aenderungen_anwenden(e["positionen"], 10000, geaendert={0: {"gewicht": 40, "kurs": 80}})
        self.assertAlmostEqual(neu[0]["gewicht"], 40.0)
        self.assertEqual(neu[0]["kurs"], 80.0)
        neu = P.aenderungen_anwenden(e["positionen"], 10000, geaendert={0: {"kurs": 200}})
        self.assertAlmostEqual(neu[0]["gewicht"], 50.0)    # neuer Kurs: Gewicht bleibt

    def test_neu_und_loeschen(self):
        e = self._e()
        neu = P.aenderungen_anwenden(e["positionen"], 10000, geloescht=[1],
                                     neu=[{"name": "D", "kurs": 10, "betrag": 1000}, {"name": "E", "gewicht": 5}])
        self.assertEqual([p["name"] for p in neu], ["A", "C", "D", "E"])
        self.assertAlmostEqual(neu[2]["gewicht"], 10.0)
        self.assertAlmostEqual(neu[3]["gewicht"], 5.0)

    def test_ohne_kapital_bleibt_gewicht(self):
        e = self._e()
        neu = P.aenderungen_anwenden(e["positionen"], 0, geaendert={0: {"betrag": 999}})
        self.assertAlmostEqual(neu[0]["gewicht"], 50.0)

    def test_auf_100(self):
        neu = P.auf_100(self._e()["positionen"])
        self.assertAlmostEqual(sum(p["gewicht"] for p in neu), 100.0)
        self.assertAlmostEqual(neu[0]["gewicht"], 50 / 90 * 100)
        gleich = P.auf_100([{"name": "x", "kurs": 1, "gewicht": 0}, {"name": "y", "kurs": 1, "gewicht": 0}])
        self.assertEqual([p["gewicht"] for p in gleich], [50.0, 50.0])


class Hinzufuegen(unittest.TestCase):
    def test_rest_bis_100(self):
        pos = [{"name": "A", "kurs": 10, "gewicht": 70}]
        neu, ok = P.position_hinzufuegen(pos, "NVIDIA", 120.5, art="aktie", wkn="918422", instrument_id=123)
        self.assertTrue(ok)
        self.assertEqual(neu[-1], {"name": "NVIDIA", "kurs": 120.5, "gewicht": 30.0, "art": "aktie",
                                   "wkn": "918422", "instrument_id": "123"})
        self.assertEqual(len(pos), 1)                       # Eingabe unveraendert

    def test_volles_portfolio_gewicht_0_oder_vorgegeben(self):
        pos = [{"name": "A", "kurs": 10, "gewicht": 100}]
        self.assertEqual(P.position_hinzufuegen(pos, "B")[0][-1]["gewicht"], 0.0)
        self.assertEqual(P.position_hinzufuegen(pos, "B", gewicht=15)[0][-1]["gewicht"], 15.0)

    def test_kein_doppelter_wert(self):
        pos = [{"name": "MSCI World", "kurs": 10, "gewicht": 50, "wkn": "A0RPWH"}]
        self.assertFalse(P.position_hinzufuegen(pos, "Irgendwas", wkn="a0rpwh")[1])
        self.assertFalse(P.position_hinzufuegen(pos, "msci world ")[1])
        self.assertTrue(P.position_hinzufuegen(pos, "MSCI World", wkn="ANDERE")[1])

    def test_art_und_kennungen_bleiben_beim_bereinigen(self):
        e = P.bereinigen({"positionen": [{"name": "W", "kurs": 1, "gewicht": 5, "art": "wikifolio",
                                          "wkn": "LS9ABC", "isin": "DE000LS9ABC1", "instrument_id": 42},
                                         {"name": "X", "kurs": 1, "gewicht": 5, "art": "quatsch"}]})
        self.assertEqual(e["positionen"][0]["art"], "wikifolio")
        self.assertEqual(e["positionen"][0]["instrument_id"], "42")
        self.assertEqual(e["positionen"][1]["art"], "sonstig")

    def test_anteile_nach_art(self):
        e = P.bereinigen(eingaben(anfangskapital=10000, positionen=[
            {"name": "A", "kurs": 100, "gewicht": 50, "art": "aktie"},
            {"name": "B", "kurs": 10, "gewicht": 20, "art": "etf"},
            {"name": "C", "kurs": 10, "gewicht": 20, "art": "etf"}]))
        a = P.anteile_nach_art(e)
        self.assertAlmostEqual(a["aktie"], 50)
        self.assertAlmostEqual(a["etf"], 40)
        self.assertAlmostEqual(a["cash"], 10)

    def test_art_in_tabelle_aendern(self):
        pos = [{"name": "A", "kurs": 10, "gewicht": 50, "art": "sonstig"}]
        neu = P.aenderungen_anwenden(pos, 1000, geaendert={0: {"art": "etf"}}, neu=[{"name": "B", "art": "aktie"}])
        self.assertEqual([p["art"] for p in neu], ["etf", "aktie"])
        self.assertEqual(neu[0]["gewicht"], 50)


class Bereinigen(unittest.TestCase):
    def test_grenzen(self):
        e = P.bereinigen({"anfangskapital": -5, "laufzeit": 0, "laufzeit_einheit": "x", "rendite_pa": "abc",
                          "positionen": [{"name": "", "kurs": None, "gewicht": None}, "kaputt"]})
        self.assertEqual(e["anfangskapital"], 0.0)
        self.assertEqual(e["laufzeit"], 1)
        self.assertEqual(e["laufzeit_einheit"], "Jahre")
        self.assertEqual(e["rendite_pa"], 0.0)
        self.assertEqual(e["positionen"], [])

    def test_max_laufzeit(self):
        e = P.bereinigen({"laufzeit": 99, "laufzeit_einheit": "Jahre"})
        self.assertEqual(e["laufzeit"], 50)
        self.assertEqual(P.monate(e), P.MAX_MONATE)
        self.assertEqual(P.bereinigen({"laufzeit": 900, "laufzeit_einheit": "Monate"})["laufzeit"], P.MAX_MONATE)

    def test_grenzen_der_eingabefelder(self):
        e = P.bereinigen({"rendite_pa": 120, "kredit_zins_pa": 45, "einzahlung": 5e8, "anfangskapital": 5e12})
        self.assertEqual(e["rendite_pa"], P.MAX_RENDITE)
        self.assertEqual(e["kredit_zins_pa"], P.MAX_KREDITZINS)
        self.assertEqual(e["einzahlung"], P.MAX_MONATLICH)
        self.assertEqual(e["anfangskapital"], P.MAX_KAPITAL)
        self.assertEqual(P.bereinigen({"rendite_pa": -80})["rendite_pa"], -P.MAX_RENDITE)


if __name__ == "__main__":
    unittest.main()
