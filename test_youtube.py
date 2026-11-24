"""Tests Faceless YouTube Phase 1: Finanzrechner, Kassenbuch (youtube_finanzen.py) und Oberflaeche (youtube_ui.py)."""
import datetime
import unittest

import youtube_finanzen as YF

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False


class Rechner(unittest.TestCase):
    E = {"views_monat": 100000, "rpm": 4.0, "klickrate_pct": 1.0, "conversion_pct": 2.0, "provision": 25.0,
         "sponsoring_monat": 100.0, "sonstige_ein_monat": 0.0, "videos_monat": 10, "kanaele": 2,
         "produktion_monat": 50.0, "ki_monat": 30.0, "sonstige_kosten_monat": 20.0, "einmalig": 300.0}

    def test_formeln(self):
        m = YF.monat(YF.pruefe(self.E))
        self.assertAlmostEqual(m["youtube"], 400.0)                  # 100.000 / 1.000 x 4
        self.assertAlmostEqual(m["affiliate"], 500.0)                # 100.000 x 1 % x 2 % x 25
        self.assertAlmostEqual(m["umsatz"], 1000.0)
        self.assertAlmostEqual(m["kosten"], 100.0)
        self.assertAlmostEqual(m["gewinn"], 900.0)
        self.assertAlmostEqual(m["marge_pct"], 90.0)
        self.assertAlmostEqual(m["umsatz_je_video"], 100.0)
        self.assertAlmostEqual(m["umsatz_je_kanal"], 500.0)
        self.assertAlmostEqual(m["je_1000_views"], 10.0)

    def test_ohne_partnerprogramm_keine_werbung(self):
        m = YF.monat(YF.pruefe(self.E), monetarisiert=False)
        self.assertEqual(m["youtube"], 0.0)
        self.assertAlmostEqual(m["affiliate"], 500.0)

    def test_prognose_schaetzung_monetarisierung_breakeven(self):
        p = YF.prognose(self.E, "realistisch", 12)
        self.assertTrue(p["schaetzung"])
        self.assertEqual(len(p["monate"]), 12)
        ab = YF.SZENARIEN["realistisch"]["monetarisierung_ab"]
        self.assertEqual(p["monate"][ab - 2]["youtube"], 0.0)
        self.assertGreater(p["monate"][ab - 1]["youtube"], 0.0)
        self.assertEqual(p["break_even"], 1)                         # 900 - 300 > 0 im ersten Monat
        self.assertAlmostEqual(p["summe"]["kosten_gesamt"], 12 * 100 + 300)

    def test_szenarien_geordnet_und_zeitraeume(self):
        a = YF.alle_szenarien(self.E)
        g = {sz: a[sz]["zeitraeume"][12]["gewinn"] for sz in a}
        self.assertLess(g["konservativ"], g["realistisch"])
        self.assertLess(g["realistisch"], g["optimistisch"])
        self.assertEqual(set(a["realistisch"]["zeitraeume"]), {3, 6, 12})

    def test_eingaben_pruefen(self):
        with self.assertRaises(ValueError):
            YF.pruefe({"views_monat": -1})
        with self.assertRaises(ValueError):
            YF.pruefe({"klickrate_pct": 150})
        with self.assertRaises(ValueError):
            YF.pruefe({"rpm": "abc"})
        nur_kosten = YF.prognose({"views_monat": 0, "ki_monat": 10, "einmalig": 0}, "konservativ", 3)
        self.assertIsNone(nur_kosten["break_even"])
        self.assertIsNone(nur_kosten["marge_pct"])


class Kassenbuch(unittest.TestCase):
    def test_buchungen_und_auswertung(self):
        k = YF.neuer_kanal("KI-Tools DE", nische="KI")
        b = [YF.neue_buchung("2026-10-05", "ausgabe", "ki", 20, k["id"]),
             YF.neue_buchung("2026-11-01", "einnahme", "affiliate", 50.5, k["id"]),
             YF.neue_buchung("2026-11-02", "einnahme", "werbung", 9.5)]
        a = YF.auswertung(b)
        self.assertEqual((a["einnahmen"], a["ausgaben"], a["gewinn"]), (60.0, 20.0, 40.0))
        self.assertAlmostEqual(a["roi_pct"], 200.0)
        self.assertEqual(list(a["je_monat"]), ["2026-10", "2026-11"])
        self.assertEqual(YF.auswertung(b, k["id"])["einnahmen"], 50.5)
        self.assertEqual(YF.auswertung(b, von="2026-11-01")["anzahl"], 2)
        self.assertIsNone(YF.auswertung([])["roi_pct"])

    def test_ungueltige_buchungen(self):
        with self.assertRaises(ValueError):
            YF.neue_buchung("2026-11-01", "einnahme", "ki", 10)              # Kategorie passt nicht
        with self.assertRaises(ValueError):
            YF.neue_buchung("2026-11-01", "ausgabe", "ki", 0)
        with self.assertRaises(ValueError):
            YF.neue_buchung("kein datum", "ausgabe", "ki", 5)
        morgen = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):                                  # keine Prognose als Buchung
            YF.neue_buchung(morgen, "einnahme", "werbung", 5)
        with self.assertRaises(ValueError):
            YF.neuer_kanal("  ")


def _app():
    import json as _json
    import streamlit as st
    import test_pyramide as T
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
    sp = st.session_state["speicher"]
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "zugaenge": {"YOUTUBE_API_KEY": False, "GEMINI_API_KEY": True}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/youtube.json") or {}))


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class Oberflaeche(unittest.TestCase):
    def _d(self, at):
        import json
        m = [x.value for x in at.markdown if x.value.startswith("SPEICHER:")][-1]
        return json.loads(m[len("SPEICHER:"):])

    def test_rundgang(self):
        import youtube_ui as YU
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        at.session_state["speicher"] = T.Speicher()             # eigener, leerer Speicher je Lauf
        at.run()
        self.assertFalse(at.exception)
        for b in YU.BEREICHE:
            at.segmented_control(key="yt_bereich").set_value(b).run()
            self.assertFalse(at.exception, b)
        # Kanal anlegen, Buchung erfassen
        at.segmented_control(key="yt_bereich").set_value("Finanzen").run()
        at.segmented_control(key="yt_fin_teil").set_value("Kanäle").run()
        at.text_input(key="yt_k_name").set_value("KI-Tools DE").run()
        at.button(key="yt_k_btn").click().run()
        self.assertEqual(len(self._d(at)["kanaele"]), 1, self._d(at)["kanaele"])
        at.segmented_control(key="yt_fin_teil").set_value("Kassenbuch").run()
        at.number_input(key="yt_b_betrag").set_value(12.5).run()
        at.button(key="yt_b_btn").click().run()
        self.assertFalse(at.exception)
        b = self._d(at)["buchungen"]
        self.assertEqual((len(b), b[0]["art"], b[0]["betrag"]), (1, "ausgabe", 12.5))
        # Rechner
        at.segmented_control(key="yt_fin_teil").set_value("Finanzrechner").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Schätzung" in x.value for x in at.markdown))
        # Idee speichern
        at.segmented_control(key="yt_bereich").set_value("Recherche").run()
        self.assertTrue(any("Kanal-Radar" in x.value for x in at.markdown))
        at.text_input(key="yt_r_kanal").set_value("UCBJycsmduvYEL83R_U4JriQ").run()
        at.button(key="yt_r_add_btn").click().run()
        self.assertEqual(self._d(at)["radar"][0]["id"], "UCBJycsmduvYEL83R_U4JriQ")
        at.segmented_control(key="yt_rech_teil").set_value("Ideen").run()
        at.text_input(key="yt_idee_titel").set_value("5 KI-Tools für kleine Firmen").run()
        at.button(key="yt_idee_btn").click().run()
        self.assertEqual(self._d(at)["ideen"][0]["titel"], "5 KI-Tools für kleine Firmen")
        # Einstellungen
        at.segmented_control(key="yt_bereich").set_value("Einstellungen").run()
        at.number_input(key="yt_e_bm").set_value(10.0).run()
        at.button(key="yt_e_btn").click().run()
        self.assertEqual(self._d(at)["einstellungen"]["budget_monat"], 10.0)
        self.assertFalse(at.exception)
        texte = " ".join(x.value for x in at.markdown)
        self.assertIn("YOUTUBE_API_KEY", texte)
        self.assertNotIn("sk-", texte)


if __name__ == "__main__":
    unittest.main()
