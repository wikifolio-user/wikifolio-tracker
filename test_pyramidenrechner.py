"""Tests Pyramidenrechner: Rechenkern (pyramidenrechner.py) und Klickweg der Oberflaeche (pyramidenrechner_ui.py)."""
import unittest
from decimal import Decimal

import pyramidenrechner as PR

try:
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False


class Rechenkern(unittest.TestCase):
    def test_verdopplung_ohne_preisaenderung(self):
        p = PR.parameter("3", "10", "2")
        zeilen, fehler = PR.stufen(p, 4)
        self.assertEqual(fehler, [])
        self.assertEqual([z["stueck"] for z in zeilen], [3, 6, 12, 24])
        self.assertEqual(zeilen[-1]["stueck_ges"], 45)
        self.assertEqual(zeilen[-1]["kosten_ges"], 450)
        self.assertEqual(zeilen[-1]["durchschnitt"], 10)
        u = PR.uebersicht(p, zeilen)
        self.assertIsNone(u["budget"])
        self.assertIsNone(u["weitere"])

    def test_gesamtpreis_modus_und_multiplikator(self):
        p = PR.parameter("4", "100", "1,5", modus="gesamt")       # 100 € fuer 4 Stueck -> 25 €/Stueck
        self.assertEqual(p["start_preis"], 25)
        zeilen, _ = PR.stufen(p, 3, {1: "120", 2: "x"})            # Stufe 2: 6 Stk. fuer 120 € gesamt
        self.assertEqual([z["stueck"] for z in zeilen], [4, 6, 9])
        self.assertEqual(zeilen[1]["preis"], 20)
        self.assertTrue(zeilen[1]["eigen"])
        self.assertFalse(zeilen[2]["eigen"])                       # ungueltige Eingabe -> automatischer Preis
        self.assertEqual(zeilen[2]["kosten"], 225)

    def test_automatische_preisaenderung(self):
        p = PR.parameter("1", "100", "2", auto=True, aenderung_pct="-10")
        zeilen, _ = PR.stufen(p, 3)
        self.assertEqual([z["preis"] for z in zeilen], [100, 90, Decimal("81")])
        self.assertEqual(PR.parameter("1", "100", auto=False, aenderung_pct="50")["aenderung"], 0)
        with self.assertRaises(PR.EingabeFehler):
            PR.parameter("1", "100", auto=True, aenderung_pct="-100")
        with self.assertRaises(PR.EingabeFehler):
            PR.parameter("", "100")
        with self.assertRaises(PR.EingabeFehler):
            PR.parameter("1", "100", "500")

    def test_budget(self):
        p = PR.parameter("1", "10", "2", budget="200")            # 10, 20, 40, 80 = 150; +160 > 200
        zeilen, _ = PR.stufen(p, 2)
        u = PR.uebersicht(p, zeilen)
        self.assertEqual(u["rest"], 170)
        self.assertEqual(u["weitere"], 2)                          # 40 + 80 passen, 160 nicht
        self.assertEqual(PR.bis_budget(p), 4)
        zeilen, _ = PR.stufen(p, 5)
        u = PR.uebersicht(p, zeilen)
        self.assertTrue(u["ueber_budget"])
        self.assertEqual(u["rest"], -110)
        self.assertFalse(zeilen[-1]["im_budget"])
        self.assertEqual(PR.bis_budget(PR.parameter("1", "500", budget="100")), 1)
        self.assertIsNone(PR.bis_budget(PR.parameter("1", "10")))

    def test_eigene_verschieben(self):
        self.assertEqual(PR.eigene_verschieben({1: "a", 2: "b", 3: "c"}, 2), {1: "a", 2: "c"})

    def test_hoechstens_max_stufen(self):
        zeilen, _ = PR.stufen(PR.parameter("1", "1"), 999)
        self.assertEqual(len(zeilen), PR.MAX_STUFEN)


def _app():
    import pyramidenrechner_ui
    pyramidenrechner_ui.seite()


def _app_mit_speicher():
    import copy
    import streamlit as st
    import pyramidenrechner_ui
    speicher = st.session_state.setdefault("_test_speicher", {})

    def lesen(pfad, default):
        return copy.deepcopy(speicher.get(pfad, default)), True

    def aktualisiere(pfad, f, default, msg):
        speicher[pfad] = f(copy.deepcopy(speicher.get(pfad, default)))
        return True, speicher[pfad]
    pyramidenrechner_ui.seite({"lesen": lesen, "aktualisiere": aktualisiere, "upfad": lambda p: "u/" + p,
                               "speichern": True})


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class Oberflaeche(unittest.TestCase):
    def _texte(self, at):
        return " ".join(x.value for x in at.markdown) + " ".join(x.value for x in at.caption)

    def test_klickweg(self):
        at = AppTest.from_function(_app, default_timeout=60)
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.text_input(key="prr_mult").value, "2")
        self.assertEqual(at.text_input(key="prr_stueck").value, "")     # keine fest vorgegebenen Werte
        at.text_input(key="prr_stueck").set_value("1").run()
        at.text_input(key="prr_preis").set_value("10").run()
        t = self._texte(at)
        self.assertIn("150,00 €", t)                                    # 4 Stufen: 1+2+4+8 Stk. a 10 €
        at.button(key="prr_weiter_btn").click().run()
        self.assertEqual(at.session_state["prr_n"], 5)
        self.assertIn("310,00 €", self._texte(at))
        at.text_input(key="prr_e4").set_value("5").run()                # Stufe 5 billiger: 16 x 5
        self.assertIn("230,00 €", self._texte(at))
        at.button(key="prr_del_2_btn").click().run()                   # Stufe 3 entfernen -> eigener Preis rueckt nach
        self.assertEqual(at.session_state["prr_n"], 4)
        self.assertEqual(at.text_input(key="prr_e3").value, "5")
        # Budget: bis zum Budget auffuellen
        at.text_input(key="prr_budget").set_value("1000").run()
        at.button(key="prr_budget_btn").click().run()
        self.assertEqual(at.session_state["prr_n"], 6)
        self.assertFalse(at.exception)
        # Umschalten auf Gesamtpreis rechnet die Eingaben um, Ergebnis bleibt gleich
        vorher = self._texte(at)
        at.radio(key="prr_modus").set_value("gesamt").run()
        self.assertEqual(at.text_input(key="prr_preis").value, "10,00")
        self.assertEqual(at.text_input(key="prr_e3").value, "40,00")    # 8 Stk. x 5 €
        self.assertIn("Gesamtpreis Stufe 1", " ".join(x.label for x in at.text_input))
        self.assertTrue(all(w in self._texte(at) for w in ("Gesamtstückzahl",)))
        self.assertEqual(vorher.count("€"), self._texte(at).count("€"))
        at.button(key="prr_reset_btn").click().run()
        self.assertEqual(at.text_input(key="prr_stueck").value, "")
        self.assertFalse(at.exception)

    def test_szenarien_speichern_laden_vergleichen(self):
        at = AppTest.from_function(_app_mit_speicher, default_timeout=60)
        at.run()
        at.text_input(key="prr_stueck").set_value("1").run()
        at.text_input(key="prr_preis").set_value("10").run()
        at.text_input(key="prr_sz_name").set_value("Klein").run()
        at.button(key="prr_sz_save_btn").click().run()
        self.assertFalse(at.exception)
        liste = at.session_state["_test_speicher"]["u/state/pyramidenrechner.json"]["szenarien"]
        self.assertEqual(len(liste), 1)
        self.assertEqual(liste[0]["name"], "Klein")
        self.assertEqual(at.text_input(key="prr_sz_name").value, "")
        # zweites Szenario
        at.text_input(key="prr_preis").set_value("20").run()
        at.text_input(key="prr_sz_name").set_value("Teuer").run()
        at.button(key="prr_sz_save_btn").click().run()
        liste = at.session_state["_test_speicher"]["u/state/pyramidenrechner.json"]["szenarien"]
        self.assertEqual(len(liste), 2)
        self.assertEqual(len(at.dataframe), 2)                         # Stufentabelle + Vergleichstabelle
        # erstes laden, aendern, aktualisieren
        at.button(key=f"prr_sz_load_{liste[0]['id']}_btn").click().run()
        self.assertEqual(at.text_input(key="prr_preis").value, "10")
        at.text_input(key="prr_preis").set_value("12").run()
        at.button(key="prr_sz_upd_btn").click().run()
        liste = at.session_state["_test_speicher"]["u/state/pyramidenrechner.json"]["szenarien"]
        self.assertEqual(liste[0]["werte"]["preis"], "12")
        at.text_input(key="prr_sz_name").set_value("Mittel").run()
        at.button(key="prr_sz_ren_btn").click().run()
        liste = at.session_state["_test_speicher"]["u/state/pyramidenrechner.json"]["szenarien"]
        self.assertEqual(liste[0]["name"], "Mittel")
        # loeschen
        at.button(key=f"prr_sz_del_{liste[1]['id']}_btn").click().run()
        liste = at.session_state["_test_speicher"]["u/state/pyramidenrechner.json"]["szenarien"]
        self.assertEqual([s["name"] for s in liste], ["Mittel"])
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
