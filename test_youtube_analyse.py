"""Tests Faceless YouTube Phase 3a: Kommentar- und Transkript-Analyse (youtube_analyse.py, youtube_analyse_ui.py)
mit nachgebauter API und nachgebauter KI - ohne Netz, ohne Schluessel."""
import json
import unittest

import youtube_analyse as YAN
import youtube_api as YA

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

TEXTE = ["Danke, super erklärt! 👍", "Kannst du bitte ein Video über ETF Sparpläne machen?",
         "Wie hoch sind die Kosten bei ETF Sparplänen?", "Die KI-Stimme ist echt nervig und zu leise",
         "Check my channel for free crypto signals https://spam.example", "Gutes Video, hilfreich",
         "Was ist mit Steuern auf ETF Sparpläne?", "Nächstes Video bitte über Dividenden", "ok", "aaaaaaaaaaaaaaa"]


def _item(i, text, likes=0):
    return {"snippet": {"totalReplyCount": i % 3, "topLevelComment": {"snippet": {
        "textOriginal": text, "likeCount": likes, "publishedAt": "2026-11-0%dT10:00:00Z" % (1 + i % 9),
        "authorDisplayName": "Max Mustermann", "authorChannelId": {"value": "UCgeheim"}}}}}


class Api:
    """commentThreads mit zwei Seiten, videos mit einem Video."""

    def __init__(self):
        self.aufrufe = []

    def __call__(self, endpunkt, params):
        self.aufrufe.append((endpunkt, dict(params)))
        if endpunkt == "commentThreads":
            if params.get("pageToken") == "s2":
                return {"items": [_item(i + 100, t, i) for i, t in enumerate(TEXTE[5:])]}
            return {"items": [_item(i, t, 10 - i) for i, t in enumerate(TEXTE[:5])], "nextPageToken": "s2"}
        if endpunkt == "videos":
            return {"items": [{"id": "dQw4w9WgXcQ", "snippet": {"title": "ETF für Anfänger", "channelId": "UCx",
                                                                 "channelTitle": "Finanzkanal",
                                                                 "publishedAt": "2026-10-01T00:00:00Z"},
                               "statistics": {"viewCount": "12345", "commentCount": "10"},
                               "contentDetails": {"duration": "PT9M"}}]}
        raise AssertionError(endpunkt)


class Ki:
    def __init__(self, antworten):
        self.antworten, self.prompts = list(antworten), []

    def antwort(self, prompt):
        self.prompts.append(prompt)
        return self.antworten.pop(0) if self.antworten else None


class Kommentare(unittest.TestCase):
    def test_video_id(self):
        for e in ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3", "https://youtu.be/dQw4w9WgXcQ",
                  "https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"):
            self.assertEqual(YAN.video_id(e), "dQw4w9WgXcQ", e)
        self.assertIsNone(YAN.video_id("https://www.youtube.com/@kanal"))

    def test_laden_seiten_und_ohne_namen(self):
        z = YA.Zaehler(Api())
        k = YAN.kommentare_laden(z, "dQw4w9WgXcQ", 300)
        self.assertEqual(len(k), 10)
        self.assertEqual(z.einheiten, 2)
        self.assertNotIn("Mustermann", json.dumps(k))                # nie Namen oder Kanaele der Verfasser
        self.assertNotIn("UCgeheim", json.dumps(k))
        self.assertEqual(len(YAN.kommentare_laden(Api(), "x", 3)), 3)

    def test_gruppen_spam_begriffe(self):
        a = YAN.kommentare_auswerten([YAN.kommentar_parsen(_item(i, t, 10 - i)) for i, t in enumerate(TEXTE)])
        self.assertEqual((a["anzahl"], a["spam"]), (10, 2))
        g = {k: v["anzahl"] for k, v in a["gruppen"].items()}
        self.assertEqual(g["wunsch"], 2)
        self.assertEqual(g["frage"], 2)
        self.assertEqual(g["kritik"], 1)
        self.assertEqual(g["lob"], 2)
        self.assertEqual(g["sonstiges"], 1)
        self.assertAlmostEqual(sum(v["anteil"] for v in a["gruppen"].values()), 100.0)
        self.assertTrue(any("etf" in b for b, _ in a["begriffe"]))
        self.assertIn("Wie hoch sind die Kosten bei ETF Sparplänen?", a["fragen"])

    def test_ki_pruefung(self):
        gut = json.dumps({"zusammenfassung": "Viele wollen mehr zu ETFs.", "gruppen": [
            {"name": "Wünsche", "anteil_prozent": 40, "kern": "Mehr Praxis", "beispiele": ["a", "b", "c", "d"]}],
            "offene_fragen": ["Steuern?"], "wuensche": [], "kritikpunkte": ["Stimme"],
            "chancen_fuer_eigenes_video": ["Steuern erklären"], "boese": "<script>"})
        obj, fehler = YAN.mit_ki(Ki(["kein json", gut]), "prompt", YAN.ki_kommentare_pruefen)
        self.assertIsNone(fehler)
        self.assertEqual(obj["gruppen"][0]["anteil"], 40.0)
        self.assertEqual(len(obj["gruppen"][0]["beispiele"]), 3)
        self.assertNotIn("boese", obj)
        self.assertEqual(obj["chancen"], ["Steuern erklären"])
        obj, fehler = YAN.mit_ki(Ki(["x", "y"]), "p", YAN.ki_kommentare_pruefen)
        self.assertIsNone(obj)
        self.assertIn("zweimal", fehler)
        self.assertIsNotNone(YAN.mit_ki(None, "p", YAN.ki_kommentare_pruefen)[1])
        p = YAN.ki_prompt_kommentare("Titel", [YAN.kommentar_parsen(_item(i, t)) for i, t in enumerate(TEXTE)])
        self.assertNotIn("spam.example", p)                          # Spam geht nicht an die KI
        self.assertIn("keine Namen", p.replace("Nenne keine Namen", "keine Namen"))

    def test_fehlertext_kommentare_aus(self):
        class R:
            status_code = 403

            def json(self):
                return {"error": {"errors": [{"reason": "commentsDisabled"}]}}
        with self.assertRaises(YA.ApiFehler) as cm:
            YA.verbindung("k", lambda url, **kw: R())("commentThreads", {})
        self.assertIn("deaktiviert", str(cm.exception))


SRT = """1
00:00:01,000 --> 00:00:04,000
Willkommen zu ETF für Anfänger.

2
00:00:04,500 --> 00:00:09,000
Ein ETF bildet einen Index nach und ist meist günstig.

3
00:02:40,000 --> 00:02:45,000
Der Sparplan auf einen ETF funktioniert schon ab kleinen Beträgen.

4
00:05:10,000 --> 00:05:20,000
Am Ende zählt die Kostenquote des ETF und die Streuung.
"""
VTT = "WEBVTT\n\n00:00.000 --> 00:03.000\n<v Sprecher>Hallo zusammen</v>\n\n00:03.000 --> 00:06.500\nHeute geht es um Zinsen.\n"


class Transkript(unittest.TestCase):
    def test_srt_vtt_text(self):
        t = YAN.transkript_parsen(SRT)
        self.assertEqual((t["art"], len(t["segmente"])), ("srt", 4))
        self.assertEqual(t["segmente"][2]["start"], 160.0)
        v = YAN.transkript_parsen(VTT)
        self.assertEqual((v["art"], v["segmente"][0]["text"]), ("vtt", "Hallo zusammen"))
        self.assertEqual(v["segmente"][1]["ende"], 6.5)
        x = YAN.transkript_parsen("Absatz eins ist hier.\n\nAbsatz zwei folgt.")
        self.assertEqual((x["art"], len(x["segmente"])), ("text", 2))
        self.assertEqual(YAN.transkript_parsen("   ")["segmente"], [])

    def test_auswertung(self):
        a = YAN.transkript_auswerten(YAN.transkript_parsen(SRT),
                                     fragen=["Was ist mit Steuern auf Gewinne?", "Wie hoch ist die Kostenquote?"])
        self.assertEqual(a["dauer_s"], 320.0)
        self.assertGreater(a["wpm"], 0)
        self.assertEqual(len(a["kapitel"]), 3)                       # 0:01, 2:40, 5:10 (je >= 2,5 Minuten)
        self.assertEqual(YAN.zeit_text(a["kapitel"][1]["start"]), "2:40")
        self.assertEqual(a["luecken"], ["Was ist mit Steuern auf Gewinne?"])   # Kostenquote kommt vor
        self.assertTrue(a["kernsaetze"])
        ohne = YAN.transkript_auswerten(YAN.transkript_parsen("Nur Text ohne Zeiten. " * 20))
        self.assertIsNone(ohne["dauer_s"])
        self.assertEqual(ohne["kapitel"], [])

    def test_ki_transkript(self):
        obj = YAN.ki_transkript_pruefen({"zusammenfassung": "Basics", "kernaussagen": ["ETF = Index"],
                                         "kapitel": [{"zeit": "0:00", "titel": "Start"}, {"titel": ""}]})
        self.assertEqual(len(obj["kapitel"]), 1)
        self.assertIsNone(YAN.ki_transkript_pruefen({"kapitel": []}))
        p = YAN.ki_prompt_transkript("T", YAN.transkript_parsen(SRT), ["Steuern?"])
        self.assertIn("[2:40]", p)
        self.assertIn("Steuern?", p)


def _app():
    import json as _json
    import streamlit as st
    import test_pyramide as T
    import test_youtube_analyse as TA
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
        st.session_state["api"] = TA.Api()
    ki_json = _json.dumps({"zusammenfassung": "Zuschauer wollen mehr zu Steuern.", "gruppen": [],
                           "offene_fragen": ["Steuern auf ETF?"], "wuensche": ["Dividenden"], "kritikpunkte": [],
                           "chancen_fuer_eigenes_video": [], "kernaussagen": ["ETF = Index"]})
    sp = st.session_state["speicher"]
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "get": None, "yt_abruf": st.session_state["api"],
                      "ki": lambda: TA.Ki([ki_json] * 5),
                      "zugaenge": {"YOUTUBE_API_KEY": True, "GEMINI_API_KEY": True}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/youtube.json") or {}))


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class AnalyseOberflaeche(unittest.TestCase):
    def _d(self, at):
        return json.loads([x.value for x in at.markdown if x.value.startswith("SPEICHER:")][-1][len("SPEICHER:"):])

    def test_kommentare_und_transkript(self):
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        at.session_state["speicher"] = T.Speicher()
        at.session_state["api"] = Api()
        at.run()
        at.segmented_control(key="yt_bereich").set_value("Analyse").run()
        self.assertFalse(at.exception)
        at.text_input(key="yt_an_video").set_value("https://youtu.be/dQw4w9WgXcQ").run()
        at.button(key="yt_an_btn").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("ETF für Anfänger" in x.value for x in at.markdown))
        api_datei = at.session_state["speicher"].d["u/state/youtube_api.json"]
        self.assertEqual(api_datei["kontingent"]["verbraucht"], 3)          # 1 Video + 2 Kommentarseiten
        self.assertEqual(api_datei.get("cache") or {}, {})                 # Kommentare nicht in der Datei
        at.button(key="yt_an_ki_btn").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("mehr zu Steuern" in x.value for x in at.markdown))
        at.button(key="yt_an_merken").click().run()
        an = self._d(at)["analysen"]
        self.assertEqual((len(an), an[0]["art"]), (1, "kommentare"))
        self.assertNotIn("Mustermann", json.dumps(an))
        # Transkript mit Abgleich der offenen Fragen
        at.segmented_control(key="yt_an_teil").set_value("Transkript").run()
        at.text_area(key="yt_tr_text").set_value(SRT).run()
        at.selectbox(key="yt_tr_bezug").set_value(an[0]["id"]).run()
        at.button(key="yt_tr_btn").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Steuern" in x.value for x in at.markdown))     # Luecke aus den Kommentarfragen
        at.button(key="yt_tr_ki_btn").click().run()
        at.button(key="yt_tr_merken").click().run()
        self.assertEqual(len(self._d(at)["analysen"]), 2)
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
