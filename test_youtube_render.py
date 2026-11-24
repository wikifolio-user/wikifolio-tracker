"""Tests Render-Agent (youtube_render_agent.py), Release-Ablage (github_release.py) und Video-Factory-Ansicht."""
import os
import tempfile
import unittest

import github_release as GR
import youtube_render_agent as AG

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False


class Warteschlange(unittest.TestCase):
    INDEX = {"projekte": [{"id": "a", "status": "warteschlange"}, {"id": "b", "status": "entwurf"},
                          {"id": "c", "status": "warteschlange"}]}

    def test_offene(self):
        self.assertEqual(AG.offene(self.INDEX), ["a", "c"])
        self.assertEqual(AG.offene(self.INDEX, "b"), ["b"])          # gezielter Start, auch ausserhalb der Schlange
        self.assertEqual(AG.offene({}), [])

    def test_index_status(self):
        neu = AG.index_status(self.INDEX, "a", "rendert", "Titel")
        self.assertEqual(neu["projekte"][0]["status"], "rendert")
        self.assertEqual(neu["projekte"][0]["titel"], "Titel")
        self.assertEqual(self.INDEX["projekte"][0]["status"], "warteschlange")   # Original unveraendert

    def test_ergebnis_hochladen(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("video.mp4", "beschreibung.txt", "fremd.txt"):
                with open(os.path.join(d, n), "w") as f:
                    f.write("x")
            hoch = []
            r = AG.ergebnis_hochladen({"id": "p1", "skript": {"titel": "T"}}, d,
                                      release_holen=lambda tag, name: {"id": 7, "tag": tag},
                                      hochladen=lambda rel, pfad, name, typ: hoch.append((name, typ)) or {"id": len(hoch)})
        self.assertEqual(r["tag"], "video-p1")
        self.assertEqual(set(r["assets"]), {"video.mp4", "beschreibung.txt"})     # nur Ergebnisdateien
        self.assertIn(("video.mp4", "video/mp4"), hoch)


class Release(unittest.TestCase):
    def test_workflow_starten_meldungen(self):
        class R:
            def __init__(self, code):
                self.status_code = code
        alt = GR.requests.post
        try:
            for code, erwartet in ((204, True), (403, False), (404, False)):
                GR.requests.post = lambda *a, c=code, **k: R(c)
                ok, text = GR.workflow_starten("o/r", "w.yml", "t", {"projekt": "x"})
                self.assertEqual(ok, erwartet, text)
            GR.requests.post = lambda *a, **k: (_ for _ in ()).throw(OSError())
            self.assertFalse(GR.workflow_starten("o/r", "w.yml", "t")[0])
        finally:
            GR.requests.post = alt


class Kosten(unittest.TestCase):
    def test_voranschlag_free(self):
        from video_factory import kosten as KO
        posten, summe, ok = KO.voranschlag({"budget_video": 0}, 5, True)
        self.assertEqual(summe, 0.0)
        self.assertTrue(ok)
        self.assertEqual(len(posten), 4)
        self.assertEqual(KO.renderminuten(5), 11)


def _app():
    import streamlit as st
    import test_pyramide as T
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
    sp = st.session_state["speicher"]
    st.session_state.setdefault("starts", [])
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "zugaenge": {}, "ki": lambda: None,
                      "render_starten": lambda pid: (st.session_state["starts"].append(pid), (False, "Test"))[1],
                      "release_laden": lambda aid: "Titel\n\nBeschreibung".encode("utf-8")})


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class Oberflaeche(unittest.TestCase):
    def test_eigenes_skript_bis_freigabe(self):
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        at.session_state["speicher"] = T.Speicher()
        at.session_state["yt_bereich"] = "Video Factory"
        at.run()
        sp = at.session_state["speicher"]                       # der Speicher, den die App wirklich benutzt
        self.assertFalse(at.exception)
        at.segmented_control(key="yt_vf_quelle").set_value("eigen").run()
        at.text_input(key="yt_vf_titel").set_value("Testvideo").run()
        at.text_area(key="yt_vf_text").set_value("Einstieg mit einem Satz.\n\n## Teil eins\nNoch ein Satz. [bild: office]").run()
        at.button(key="yt_vf_anlegen_btn").click().run()
        self.assertFalse(at.exception)
        index = sp.d["u/state/youtube.json"]["projekte"]
        self.assertEqual(len(index), 1)
        pid = index[0]["id"]
        p = sp.d[f"u/state/youtube/projekte/{pid}.json"]
        self.assertEqual((p["schritte"]["skript"]["status"], p["schritte"]["storyboard"]["status"]), ("ok", "ok"))
        self.assertEqual(len(p["szenen"]), 2)
        # Rendern anfordern: Start scheitert im Test -> Warteschlange + verstaendliche Meldung
        at.button(key="yt_vf_render_btn").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(sp.d[f"u/state/youtube/projekte/{pid}.json"]["status"], "warteschlange")
        self.assertEqual(at.session_state["starts"], [pid])
        self.assertTrue(any("Warteschlange" in w.value for w in at.warning))
        # fertiges Ergebnis (wie vom Render-Agenten) -> Bericht, Beschreibung, Freigabe
        p = sp.d[f"u/state/youtube/projekte/{pid}.json"]
        p.update(status="freigabe_noetig", bericht={"punkte": [("Lizenzen", "ok", "alle frei")], "blockiert": False,
                                                    "freigabe_noetig": True},
                 dateien={"release": {"tag": "video-x", "assets": {"beschreibung.txt": {"id": 1}}}})
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Qualitätsbericht" in m.value for m in at.markdown))
        at.checkbox(key=f"yt_vf_geprueft_{pid}").check().run()
        at.button(key="yt_vf_frei_btn").click().run()
        self.assertEqual(sp.d[f"u/state/youtube/projekte/{pid}.json"]["status"], "freigegeben")


if __name__ == "__main__":
    unittest.main()
