"""Tests Faceless YouTube Phase 3b: Better-Video-Konzepte und Affiliate-Finder (youtube_konzepte.py,
youtube_konzepte_ui.py) - mit nachgebauter KI, ohne Netz."""
import json
import unittest

import youtube_konzepte as YK

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

ANALYSEN = [{"id": "a1", "art": "kommentare", "titel": "ETF Sparplan für Anfänger erklärt", "datum": "2026-11-20",
             "ergebnis": {"fragen": ["Wie hoch sind die Kosten?", "Was ist mit Steuern?"],
                          "wuensche": ["Video über Dividenden-ETFs"]},
             "ki": {"kritikpunkte": ["Zu schnell gesprochen"], "offene_fragen": ["Was ist mit Steuern?"]}},
            {"id": "a2", "art": "transkript", "titel": "Transkript X", "datum": "2026-11-21",
             "ergebnis": {"luecken": ["Steuern"], "kernsaetze": ["Ein ETF bildet einen Index nach."]}, "ki": None}]
KI_JSON = json.dumps({"konzepte": [
    {"titel": "ETF Sparplan für Anfänger erklärt", "format": "erklaer", "hook": "Kopie", "aufbau": [],
     "laenge_min": 8},
    {"titel": "Steuern beim ETF-Sparplan: was wirklich anfällt", "format": "faq", "hook": "Wusstest du …",
     "versprechen": "Steuern verstehen", "aufbau": [{"kapitel": "Freibetrag", "inhalt": "Wie er wirkt."}],
     "zu_pruefen": ["Höhe des Sparerpauschbetrags"], "laenge_min": "12", "boese": "x"},
    {"titel": "Dividenden oder thesaurierend?", "format": "unbekannt", "aufbau": "kaputt", "laenge_min": 999},
    {"titel": "Viertes wird ignoriert"}]})


class Ki:
    def __init__(self, antworten):
        self.antworten = list(antworten)

    def antwort(self, prompt):
        return self.antworten.pop(0) if self.antworten else None


class BetterVideo(unittest.TestCase):
    def test_material(self):
        m = YK.material(ANALYSEN)
        self.assertEqual(m["fragen"], ["Wie hoch sind die Kosten?", "Was ist mit Steuern?"])   # ohne Doppelte
        self.assertEqual(m["quellen"], ["ETF Sparplan für Anfänger erklärt", "Transkript X"])
        self.assertIn("Zu schnell gesprochen", m["kritik"])
        self.assertIn("Steuern", m["luecken"])

    def test_prompt_verbietet_kopie(self):
        p = YK.prompt("ETF-Sparplan", "Anfänger", 8, YK.material(ANALYSEN), "Eigene Notiz")
        self.assertIn("weder übersetzen noch umschreiben", p)
        self.assertIn("NICHT übernehmen", p)
        self.assertIn("Eigene Notiz", p)

    def test_pruefen_und_aehnlichkeit(self):
        obj = YK.pruefen(json.loads(KI_JSON), ["ETF Sparplan für Anfänger erklärt"])
        k = obj["konzepte"]
        self.assertEqual(len(k), 3)
        self.assertEqual(k[0]["aehnlich"], "ETF Sparplan für Anfänger erklärt")   # zu nah am Original
        self.assertIsNone(k[1]["aehnlich"])
        self.assertEqual((k[1]["laenge_min"], k[1]["zu_pruefen"]), (12, ["Höhe des Sparerpauschbetrags"]))
        self.assertNotIn("boese", k[1])
        self.assertEqual((k[2]["format"], k[2]["aufbau"], k[2]["laenge_min"]), ("erklaer", [], 60))
        self.assertIsNone(YK.pruefen({"konzepte": []}))
        self.assertGreater(YK.aehnlichkeit("ETF Sparplan Anfänger", "ETF-Sparplan für Anfänger"), 0.5)

    def test_geruest_ohne_ki(self):
        g = YK.geruest("ETF-Sparplan", YK.material(ANALYSEN))["konzepte"]
        self.assertEqual(len(g), 3)
        self.assertEqual(g[0]["format"], "faq")
        self.assertIn("Was ist mit Steuern?", [x["inhalt"] for x in g[0]["aufbau"]])
        self.assertTrue(all(k["quelle"] == "Gerüst (ohne KI)" for k in g))
        self.assertEqual(len(YK.geruest("", {})["konzepte"]), 3)

    def test_auftrag(self):
        k = YK.pruefen(json.loads(KI_JSON))["konzepte"][1]
        a = YK.auftrag(k, "ETF")
        self.assertIn("Steuern beim ETF-Sparplan", a)
        self.assertIn("Freibetrag", a)
        self.assertIn("Keine Inhalte anderer Videos", a)


class Affiliate(unittest.TestCase):
    def test_liste_hat_offizielle_quellen(self):
        for p in YK.PROGRAMME:
            self.assertTrue(p["url"].startswith("https://"), p["id"])
            self.assertTrue(p["kategorien"], p["id"])
            self.assertNotRegex(p["hinweis"], r"\d|%|€")               # keine Konditionen/Zahlen erfunden

    def test_passende_und_pruefung(self):
        alle = YK.passende("Finanzen & Investieren", "DE")
        self.assertIn("financeads", [p["id"] for p in alle])
        self.assertNotIn("getyourguide", [p["id"] for p in alle])
        self.assertTrue(all(p["status"] == "ungeprüft" for p in alle))
        gepr = YK.passende("Finanzen & Investieren", "DE", pruefungen={"awin": {"datum": "2026-11-24",
                                                                               "konditionen": "lt. Seite"}})
        self.assertEqual((gepr[0]["id"], gepr[0]["status"], gepr[0]["konditionen"]), ("awin", "geprüft", "lt. Seite"))
        self.assertNotIn("financeads", [p["id"] for p in YK.passende("Finanzen & Investieren", "US")])
        self.assertEqual(len(YK.passende("alle")), len(YK.PROGRAMME))

    def test_eigene_und_ki(self):
        e = YK.eigenes_programm("Mein Broker", "https://partner.example.com/x", ["Finanzen & Investieren"], ki=True)
        liste = YK.passende("Finanzen & Investieren", "", [e])
        x = next(p for p in liste if p["id"] == e["id"])
        self.assertEqual(x["status"], "ungeprüft (KI)")
        with self.assertRaises(ValueError):
            YK.eigenes_programm("X", "http://unsicher.example.com", [])
        with self.assertRaises(ValueError):
            YK.eigenes_programm("", "https://a.de", [])
        obj = YK.ki_affiliate_pruefen({"programme": [{"name": "A", "url": "https://a.example.com", "warum": "x"},
                                                     {"name": "B", "url": "javascript:alert(1)"}, "kaputt"]})
        self.assertEqual([p["name"] for p in obj["programme"]], ["A"])
        self.assertIn("keine Provisionen", YK.ki_prompt_affiliate("ETF", "Finanzen & Investieren"))


def _app():
    import json as _json
    import streamlit as st
    import test_pyramide as T
    import test_youtube_konzepte as TK
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
        st.session_state["speicher"].d["u/state/youtube.json"] = {"analysen": TK.ANALYSEN}
    sp = st.session_state["speicher"]
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "get": None, "ki": lambda: TK.Ki([TK.KI_JSON] * 3),
                      "zugaenge": {"YOUTUBE_API_KEY": False, "GEMINI_API_KEY": True}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/youtube.json") or {}))


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class KonzepteOberflaeche(unittest.TestCase):
    def _d(self, at):
        return json.loads([x.value for x in at.markdown if x.value.startswith("SPEICHER:")][-1][len("SPEICHER:"):])

    def test_konzepte_factory_affiliate(self):
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        sp = T.Speicher()
        sp.d["u/state/youtube.json"] = {"analysen": ANALYSEN}
        at.session_state["speicher"] = sp
        at.run()
        at.segmented_control(key="yt_bereich").set_value("Analyse").run()
        at.segmented_control(key="yt_an_teil").set_value("Better Video").run()
        self.assertFalse(at.exception)
        at.text_input(key="yt_bv_thema").set_value("ETF-Sparplan").run()
        at.multiselect(key="yt_bv_analysen").set_value(["a1", "a2"]).run()
        at.button(key="yt_bv_ki_btn").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("sehr nah an" in x.value for x in at.warning))
        at.button(key="yt_bv_idee_1").click().run()
        self.assertEqual(self._d(at)["ideen"][0]["titel"], "Steuern beim ETF-Sparplan: was wirklich anfällt")
        at.button(key="yt_bv_geruest_btn").click().run()
        self.assertTrue(any("Gerüst (ohne KI)" in x.value for x in at.markdown))
        at.button(key="yt_bv_vf_0").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.segmented_control(key="yt_bereich").value, "Video Factory")
        self.assertIn("Keine Inhalte anderer Videos", at.session_state["yt_vf_auftrag"])
        # Affiliate: pruefen und eigenes Programm
        at.segmented_control(key="yt_bereich").set_value("Analyse").run()
        at.segmented_control(key="yt_an_teil").set_value("Affiliate").run()
        at.selectbox(key="yt_af_kat").set_value("Finanzen & Investieren").run()
        self.assertFalse(at.exception)
        at.text_input(key="yt_af_kond_financeads").set_value("laut Seite geprüft").run()
        at.checkbox(key="yt_af_ok_financeads").check().run()
        at.button(key="yt_af_pr_financeads").click().run()
        a = self._d(at)["affiliate"]["financeads"]
        self.assertEqual(a["konditionen"], "laut Seite geprüft")
        at.text_input(key="yt_af_name").set_value("Mein Broker").run()
        at.text_input(key="yt_af_url").set_value("https://partner.example.com").run()
        at.button(key="yt_af_add").click().run()
        self.assertEqual(self._d(at)["affiliate_eigene"][0]["name"], "Mein Broker")
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
