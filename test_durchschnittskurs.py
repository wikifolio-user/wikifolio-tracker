"""Tests Durchschnittskurs-Rechner (durchschnittskurs.py, durchschnittskurs_ui.py): Zahlen einlesen (deutsch und
Punkt-Format, 8 Nachkommastellen), Validierung, Formel inkl. Gebuehren, Gesamtwert statt Kurs, deutsche Formatierung,
Speichern, Tabellenlogik und Klickweg (Ergebnis, Nachkauf, Zuruecksetzen) - ohne Depot und ohne Netz."""
import json
import unittest
from decimal import Decimal

import durchschnittskurs as DK

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False


class Zahlen(unittest.TestCase):
    def test_einlesen(self):
        for text, erw in [("1.234,56", "1234.56"), ("1234,56", "1234.56"), ("1234.56", "1234.56"),
                          ("1,234.56", "1234.56"), ("0,00012345", "0.00012345"), ("1.234.567", "1234567"),
                          (" 12 ", "12"), ("12,5 €", "12.5"), (3, "3"), (0.1, "0.1"), ("0,12345678", "0.12345678")]:
            self.assertEqual(DK.zahl(text), Decimal(erw), text)

    def test_ungueltig(self):
        for text in ("", "abc", "1,2,3", "-5", "0", "1.23.4", "nan", "inf", "0,123456789", "1e20", None, "5.000"):
            with self.assertRaises(DK.EingabeFehler, msg=text):
                DK.zahl(text)
        self.assertEqual(DK.zahl("", leer_null=True), 0)
        self.assertEqual(DK.zahl("0", null_erlaubt=True), 0)
        with self.assertRaises(DK.EingabeFehler) as cm:
            DK.zahl("0,123456789", "Stückzahl")
        self.assertIn("8 Nachkommastellen", str(cm.exception))
        with self.assertRaises(DK.EingabeFehler) as cm:
            DK.zahl("5.000")
        self.assertIn("mehrdeutig", str(cm.exception))
        self.assertEqual(DK.zahl("0.125"), Decimal("0.125"))              # fuehrende 0: eindeutig dezimal
        self.assertEqual(DK.zahl("12.5"), Decimal("12.5"))

    def test_format(self):
        self.assertEqual(DK.de(Decimal("1234567.891"), 2), "1.234.567,89")
        self.assertEqual(DK.geld(Decimal("1234.5")), "1.234,50 €")
        self.assertEqual(DK.geld(Decimal("10"), "USD"), "10,00 $")
        self.assertEqual(DK.kurs_text(Decimal("0.000123456789")), "0,00012346 €")
        self.assertEqual(DK.kurs_text(Decimal("101")), "101,00 €")
        self.assertEqual(DK.stueck_text(Decimal("2.50000000")), "2,5")
        self.assertEqual(DK.stueck_text(Decimal("3")), "3")
        self.assertEqual(DK.de(Decimal("0.125"), 2), "0,13")                 # kaufmaennisch gerundet


class Berechnung(unittest.TestCase):
    KAEUFE = [{"stueck": "10", "art": "kurs", "kurs": "100", "gebuehr": "1"},
              {"stueck": "5", "art": "gesamt", "gesamt": "450", "gebuehr": "1,50"},
              {"stueck": "0,5", "art": "kurs", "kurs": "120,00", "gebuehr": ""}]

    def test_formel(self):
        e = DK.berechnen(self.KAEUFE)
        self.assertEqual(e["anzahl"], 3)
        self.assertEqual(e["stueck"], Decimal("15.5"))
        self.assertEqual(e["kaufwert"], Decimal("1510"))                     # 1000 + 450 + 60
        self.assertEqual(e["gebuehren"], Decimal("2.5"))
        self.assertEqual(e["investition"], Decimal("1512.5"))
        self.assertEqual(e["durchschnitt"], Decimal("1512.5") / Decimal("15.5"))
        self.assertEqual(DK.kurs_text(e["durchschnitt"]), "97,58064516 €")
        self.assertEqual(e["zeilen"][1]["kurs"], Decimal(90))                # aus dem Gesamtwert berechnet
        ohne = DK.berechnen(self.KAEUFE, mit_gebuehren=False)
        self.assertEqual((ohne["gebuehren"], ohne["durchschnitt"]), (0, Decimal("1510") / Decimal("15.5")))

    def test_ungueltige_und_leere_zeilen(self):
        e = DK.berechnen([{"stueck": "abc", "kurs": "10"}, {}, {"stueck": "2", "kurs": "10"},
                          {"stueck": "1", "kurs": "-3"}])
        self.assertEqual(e["anzahl"], 1)
        self.assertEqual([nr for nr, _ in e["fehler"]], [1, 4])
        self.assertIsNone(e["zeilen"][1])
        self.assertEqual(e["durchschnitt"], Decimal(10))
        self.assertIsNone(DK.berechnen([])["durchschnitt"])                   # keine Division durch 0

    def test_krypto_bruchteile_exakt(self):
        e = DK.berechnen([{"stueck": "0,00012345", "kurs": "60.000,12345678"},
                          {"stueck": "0,1", "art": "gesamt", "gesamt": "5000"}])
        self.assertEqual(e["stueck"], Decimal("0.10012345"))
        self.assertEqual(e["kaufwert"], Decimal("0.00012345") * Decimal("60000.12345678") + 5000)

    def test_nachkauf(self):
        e = DK.berechnen([{"stueck": "10", "kurs": "100"}])
        r = DK.nachkauf(e, "10", "80", "2")
        self.assertEqual((r["stueck"], r["investition"], r["durchschnitt"]), (20, Decimal(1802), Decimal("90.1")))
        with self.assertRaises(DK.EingabeFehler):
            DK.nachkauf(e, "0", "80")

    def test_speichern_laden(self):
        t = DK.speichern(self.KAEUFE + [{"stueck": "1", "art": "boese", "kurs": "1", "x": "y"}])
        k = DK.laden(t)
        self.assertEqual(k[1]["gesamt"], "450")
        self.assertEqual(k[3]["art"], "kurs")
        self.assertNotIn("x", k[3])
        self.assertEqual(DK.laden("kein json"), [])
        self.assertEqual(DK.laden(json.dumps({"a": 1})), [])


class Tabelle(unittest.TestCase):
    def _df(self, zeilen):
        import pandas as pd
        import durchschnittskurs_ui as U
        return pd.DataFrame([{U.SPALTEN["stueck"]: z[0], U.SPALTEN["art"]: U.ART_TEXT[z[1]], U.SPALTEN["kurs"]: z[2],
                              U.SPALTEN["gesamt"]: z[3], U.SPALTEN["gebuehr"]: "", U.SPALTEN["notiz"]: None}
                             for z in zeilen])

    @unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert")
    def test_eingabeart_automatisch(self):
        import durchschnittskurs_ui as U
        vorher = [{"stueck": "10", "art": "kurs", "kurs": "100", "gesamt": "1.000,00", "gebuehr": "", "notiz": ""}]
        neu = U._aus_tabelle(self._df([("10", "kurs", "100", "900")]), vorher)      # nur Gesamtwert geaendert
        self.assertEqual(neu[0]["art"], "gesamt")
        self.assertEqual(U._abgeleitet(neu[0])["kurs"], "90,00")
        neu = U._aus_tabelle(self._df([("10", "kurs", "95", "1.000,00")]), vorher)  # nur Kurs geaendert
        self.assertEqual(U._abgeleitet(neu[0])["gesamt"], "950,00")
        neu = U._aus_tabelle(self._df([("10", "kurs", "100", "1.000,00"), ("2", "kurs", "", "50")]), vorher)
        self.assertEqual(neu[1]["art"], "gesamt")                                     # neue Zeile nur mit Gesamtwert
        self.assertEqual(neu[0]["notiz"], "")


def _app():
    import streamlit as st
    import durchschnittskurs_ui
    durchschnittskurs_ui.seite()
    st.markdown("DATEN:" + st.session_state.get("dk_daten", ""))


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class Oberflaeche(unittest.TestCase):
    def test_ergebnis_nachkauf_zuruecksetzen(self):
        at = AppTest.from_function(_app, default_timeout=60)
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Noch kein gültiger Kauf" in x.value for x in at.markdown))
        at.session_state["dk_daten"] = DK.speichern(Berechnung.KAEUFE)
        at.session_state["dk_ver"] = 1
        at.run()
        self.assertFalse(at.exception)
        texte = " ".join(x.value for x in at.markdown)
        self.assertIn("97,58064516 €", texte)                       # gross hervorgehoben
        self.assertIn("15,5", texte)
        self.assertIn("1.512,50 €", texte)
        self.assertIn("2,50 €", texte)
        # Gebuehren ausschalten -> Durchschnitt ohne Gebuehren
        at.toggle(key="dk_gebuehren").set_value(False).run()
        self.assertIn(DK.kurs_text(Decimal(1510) / Decimal("15.5")), " ".join(x.value for x in at.markdown))
        at.toggle(key="dk_gebuehren").set_value(True).run()
        # Waehrung
        at.selectbox(key="dk_waehrung").set_value("USD").run()
        self.assertIn("97,58064516 $", " ".join(x.value for x in at.markdown))
        # Nachkauf simulieren und uebernehmen
        at.text_input(key="dk_nk_stueck").set_value("4,5").run()
        at.text_input(key="dk_nk_kurs").set_value("80").run()
        self.assertTrue(any("Neuer Durchschnittskurs" in x.value for x in at.markdown))
        at.button(key="dk_nk_btn").click().run()
        self.assertFalse(at.exception)
        k = DK.laden(at.session_state["dk_daten"])
        self.assertEqual((len(k), k[-1]["stueck"], k[-1]["notiz"]), (4, "4,5", "Nachkauf (simuliert)"))
        self.assertEqual(k[-1]["gesamt"], "360,00")
        # Zuruecksetzen
        at.button(key="dk_reset_btn").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(DK.laden(at.session_state["dk_daten"]), [])
        self.assertTrue(any("zurückgesetzt" in x.value for x in at.success))

    def test_ungueltige_eingabe_warnt(self):
        at = AppTest.from_function(_app, default_timeout=60)
        at.session_state["dk_daten"] = DK.speichern([{"stueck": "1,2,3", "kurs": "10"}, {"stueck": "2", "kurs": "5"}])
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Kauf 1" in x.value for x in at.warning))
        self.assertIn("5,00 €", " ".join(x.value for x in at.markdown))


if __name__ == "__main__":
    unittest.main()
