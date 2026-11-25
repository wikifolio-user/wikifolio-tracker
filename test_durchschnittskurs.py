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
        self.assertEqual(DK.anzeige_kurs(Decimal("45.40830508")), "45,41 €")       # 2 Nachkommastellen
        self.assertEqual(DK.anzeige_kurs(Decimal("0.000123456789")), "0,00012346 €")  # unter 1: nicht 0,00
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

    def test_gewinn(self):
        e = DK.berechnen([{"stueck": "10", "kurs": "100", "gebuehr": "5"}])
        g = DK.gewinn(e, "110")
        self.assertEqual((g["wert"], g["gewinn"]), (Decimal(1100), Decimal(95)))
        self.assertAlmostEqual(float(g["prozent"]), 95 / 1005 * 100)
        v = DK.gewinn(e, "90,5")
        self.assertEqual(v["gewinn"], Decimal("-100"))
        with self.assertRaises(DK.EingabeFehler):
            DK.gewinn(e, "abc")

    def test_staffel(self):
        v = DK.staffel("100", "1", 10, 4, 2)
        self.assertEqual([x["stueck"] for x in v], [1, 2, 4, 8])
        self.assertEqual(v[-1]["kurs"], Decimal("72.9"))
        self.assertEqual(v[-1]["investiert"], Decimal("1187.2"))
        self.assertEqual(DK.de(v[-1]["durchschnitt"], 2), "79,15")
        self.assertEqual(DK.de(v[-1]["erholung_pct"], 1), "8,6")
        g = DK.staffel("100", "1", 10, 4, 1)
        self.assertEqual(DK.de(g[-1]["durchschnitt"], 2), "85,98")
        self.assertLess(v[-1]["erholung_pct"], g[-1]["erholung_pct"])       # Verdopplung: weniger Erholung noetig
        self.assertEqual(v[0]["erholung_pct"], 0)
        for falsch in (("100", "1", 100, 4, 2), ("100", "1", 10, 0, 2), ("100", "1", 10, 13, 2), ("x", "1", 10, 4, 2)):
            with self.assertRaises(DK.EingabeFehler):
                DK.staffel(*falsch)

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


def _app():
    import streamlit as st
    import durchschnittskurs_ui
    durchschnittskurs_ui.seite()


def _app_mit_abruf():
    import streamlit as st
    import durchschnittskurs_ui
    ss = st.session_state
    ss.setdefault("suchen", [])
    ss.setdefault("kurse", [])
    treffer = {"A0RPWH": [{"instrument_id": 1, "name": "Erster ETF", "wkn": "A0RPWH", "kategorie": "ETF"},
                          {"instrument_id": 2, "name": "Zweiter Fonds", "wkn": "A1XXXX", "kategorie": "Fonds"}],
               "OHNEKURS": [{"instrument_id": 9, "name": "Ohne Kurs", "wkn": "X"}]}

    def suche(b):
        ss["suchen"].append(b)
        return treffer.get(b, [])

    def kurs(iid):
        ss["kurse"].append(iid)
        return (48.9012, 47.895, "ls-tc.de Live (Emittent)") if iid != 9 else (None, None, "Fehler – keine Live-Daten")
    durchschnittskurs_ui.seite({"suche_instrument": suche, "get_live_kurs": kurs})


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class Oberflaeche(unittest.TestCase):
    def _texte(self, at):
        return " ".join(x.value for x in at.markdown) + " ".join(x.value for x in at.caption)

    def _ids(self, at):
        return json.loads(at.session_state["dk_ids"])

    def test_eingeben_umschalten_hinzufuegen_loeschen_zuruecksetzen(self):
        at = AppTest.from_function(_app, default_timeout=60)
        at.run()
        self.assertFalse(at.exception)
        ids = self._ids(at)
        self.assertEqual(len(ids), 3)                                   # drei leere Kaeufe zum Start
        self.assertIn("— €", self._texte(at))
        at.text_input(key=f"dk_r{ids[0]}_stueck").set_value("10").run()
        at.text_input(key=f"dk_r{ids[0]}_wert").set_value("100").run()
        at.text_input(key=f"dk_r{ids[1]}_stueck").set_value("5").run()
        at.text_input(key=f"dk_r{ids[1]}_wert").set_value("90").run()
        t = self._texte(at)
        self.assertIn("96,67 €", t)
        self.assertIn("1.450,00 €", t)
        self.assertIn("2 Käufe", t)
        # Gesamtwert je Kauf: Werte werden umgerechnet, Ergebnis bleibt gleich
        at.radio(key="dk_modus").set_value("gesamt").run()
        self.assertEqual(at.text_input(key=f"dk_r{ids[0]}_wert").value, "1.000,00")
        self.assertIn("96,67 €", self._texte(at))
        at.radio(key="dk_modus").set_value("kurs").run()
        self.assertEqual(at.text_input(key=f"dk_r{ids[1]}_wert").value, "90,00")
        # aktueller Kurs -> Wert, Gewinn/Verlust in Euro und Prozent
        at.text_input(key="dk_aktuell").set_value("100").run()
        t = self._texte(at)
        self.assertIn("1.500,00 €", t)
        self.assertIn("+50,00 €", t)
        self.assertIn("+3,45 %", t)                                    # 50 / 1450
        at.text_input(key="dk_aktuell").set_value("90").run()
        t = self._texte(at)
        self.assertIn("Verlust", t)
        self.assertIn("-100,00 €", t)
        self.assertIn("-6,90 %", t)
        at.text_input(key="dk_aktuell").set_value("x").run()
        self.assertTrue(any("Aktueller Kurs" in x.value for x in at.caption))
        at.text_input(key="dk_aktuell").set_value("").run()
        # Gebuehren
        at.toggle(key="dk_gebuehren").set_value(True).run()
        at.text_input(key=f"dk_r{ids[0]}_gebuehr").set_value("1,50").run()
        t = self._texte(at)
        self.assertIn("96,77 €", t)
        self.assertIn("Kaufgebühren 1,50 €", t)
        # ungueltige Eingabe -> Hinweis, zaehlt nicht mit
        at.text_input(key=f"dk_r{ids[2]}_stueck").set_value("5.000").run()
        at.text_input(key=f"dk_r{ids[2]}_wert").set_value("1").run()
        self.assertTrue(any("Kauf 3" in x.value and "mehrdeutig" in x.value for x in at.caption))
        # hinzufuegen und loeschen
        at.button(key="dk_add_btn").click().run()
        self.assertEqual(len(self._ids(at)), 4)
        at.button(key=f"dk_del_{ids[0]}_btn").click().run()
        self.assertNotIn(ids[0], self._ids(at))
        self.assertIn("1 Kauf", self._texte(at))
        # zuruecksetzen
        at.button(key="dk_reset_btn").click().run()
        self.assertFalse(at.exception)
        neu = self._ids(at)
        self.assertEqual(len(neu), 3)
        self.assertTrue(all(not at.text_input(key=f"dk_r{i}_stueck").value for i in neu))
        self.assertFalse(at.text_input(key="dk_aktuell").value)
        self.assertIn("— €", self._texte(at))

    def test_wkn_abruf_und_uebernehmen(self):
        at = AppTest.from_function(_app_mit_abruf, default_timeout=60)
        at.run()
        ids = self._ids(at)
        at.text_input(key=f"dk_r{ids[0]}_stueck").set_value("10").run()
        at.text_input(key=f"dk_r{ids[0]}_wert").set_value("40").run()
        at.text_input(key="dk_suche").set_value("A0RPWH").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["suchen"], ["A0RPWH"])
        at.selectbox(key="dk_wahl").set_value(1).run()                    # zweiter Treffer
        t = self._texte(at)
        self.assertIn("Zweiter Fonds", t)
        self.assertIn("48,9012 €", t)
        self.assertIn("+2,10 % zum Vortag", t)
        at.button(key="dk_uebernehmen_btn").click().run()
        self.assertEqual(at.text_input(key="dk_aktuell").value, "48,9012")
        t = self._texte(at)
        self.assertIn("+89,01 €", t)                                      # 10 x 48,9012 - 400
        self.assertIn("+22,25 %", t)
        n = len(at.session_state["kurse"])
        at.run()                                                          # kein erneuter Abruf innerhalb 60 s
        self.assertEqual(len(at.session_state["kurse"]), n)
        self.assertEqual(at.session_state["suchen"], ["A0RPWH"])          # keine erneute Suche
        at.button(key="dk_neu_btn").click().run()
        self.assertEqual(len(at.session_state["kurse"]), n + 1)
        at.text_input(key="dk_suche").set_value("gibtsnicht").run()
        self.assertTrue(any("Keine Treffer" in x.value for x in at.caption))
        at.text_input(key="dk_suche").set_value("OHNEKURS").run()
        self.assertTrue(any("kein Kurs verfügbar" in x.value for x in at.caption))
        self.assertFalse(at.exception)

    def test_beispiel_nachkaeufe(self):
        at = AppTest.from_function(_app, default_timeout=60)
        at.run()
        self.assertFalse(at.exception)
        t = self._texte(at)
        self.assertIn("Ø-Kurs **79,15 €**", t)
        self.assertIn("+8,6 %", t)
        at.number_input(key="dk_bsp_faktor").set_value(1.0).run()
        self.assertIn("Ø-Kurs **85,98 €**", self._texte(at))
        at.text_input(key="dk_bsp_kurs").set_value("abc").run()
        self.assertTrue(any("Startkurs" in x.value for x in at.caption))
        self.assertEqual(len(self._ids(at)), 3)                              # eigene Kaeufe unberuehrt
        self.assertFalse(at.exception)

    def test_uebernahme_der_tabellen_version(self):
        at = AppTest.from_function(_app, default_timeout=60)
        at.session_state["dk_daten"] = DK.speichern(Berechnung.KAEUFE)
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(len(self._ids(at)), 3)
        self.assertEqual(at.radio(key="dk_modus").value, "kurs")
        # gemischte Altdaten: der als Gesamtwert erfasste Kauf wird in den Kurs je Stueck umgerechnet
        self.assertEqual(at.text_input(key=f"dk_r{self._ids(at)[1]}_wert").value, "90,00")
        self.assertTrue(at.toggle(key="dk_gebuehren").value is not None)
        at.toggle(key="dk_gebuehren").set_value(True).run()
        self.assertIn("97,58 €", self._texte(at))                 # gleiches Ergebnis wie vorher
        self.assertNotIn("dk_daten", at.session_state)


if __name__ == "__main__":
    unittest.main()
