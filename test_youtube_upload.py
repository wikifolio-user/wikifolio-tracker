"""Tests Faceless YouTube - Upload als privater Entwurf (youtube_upload.py, Video Factory) mit nachgebautem Google:
Anmeldung, Metadaten (immer privat), resumable Upload in Teilen, Thumbnail, Fehlertexte ohne Geheimnisse,
Klickweg nur fuer freigegebene Projekte mit Bestaetigung."""
import json
import os
import tempfile
import unittest
from unittest import mock

import youtube_upload as YU

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

GEHEIM = "1//0geheimerRefreshTokenXXXXXXXXXXXXXXXX"


class R:
    def __init__(self, status, daten=None, headers=None):
        self.status_code, self._d, self.headers = status, daten, headers or {}

    def json(self):
        if self._d is None:
            raise ValueError("kein json")
        return self._d


class Google:
    """Token-Endpunkt + resumable Upload (antwortet zwischendurch mit 308 und Range)."""

    def __init__(self):
        self.meta, self.teile, self.thumb = None, [], None

    def post(self, url, **kw):
        if url == YU.TOKEN_URL:
            if kw["data"]["refresh_token"] == "abgelaufen":
                return R(400, {"error": "invalid_grant"})
            return R(200, {"access_token": "ya29.zugang", "scope": YU.SCOPE})
        if url == YU.UPLOAD_URL:
            self.meta = json.loads(kw["data"])
            return R(200, {}, {"Location": "https://upload.example/sitzung"})
        if url == YU.THUMB_URL:
            self.thumb = kw["params"]["videoId"]
            return R(403, {"error": {"errors": [{"reason": "forbidden"}]}})
        raise AssertionError(url)

    def put(self, url, **kw):
        self.teile.append(kw["headers"]["Content-Range"])
        groesse = int(kw["headers"]["Content-Range"].split("/")[1])
        ende = int(kw["headers"]["Content-Range"].split("-")[1].split("/")[0])
        if ende + 1 < groesse:
            return R(308, None, {"Range": f"bytes=0-{ende}"})
        return R(200, {"id": "VIDEO123"})


class Anmeldung(unittest.TestCase):
    def test_zugang_und_fehler(self):
        g = Google()
        self.assertEqual(YU.zugang("id", "secret", "gut", g.post), "ya29.zugang")
        with self.assertRaises(YU.UploadFehler) as cm:
            YU.zugang("id", "secret", "abgelaufen", g.post)
        self.assertIn("7 Tagen", str(cm.exception))
        with self.assertRaises(YU.UploadFehler) as cm:
            YU.zugang("id", "s", GEHEIM, lambda url, **kw: R(401, {"error": "invalid_client"}))
        self.assertIn("Client-ID", str(cm.exception))
        with self.assertRaises(YU.UploadFehler) as cm:
            YU.zugang("id", "s", GEHEIM, lambda url, **kw: R(500, {"error": GEHEIM}))
        self.assertNotIn(GEHEIM, str(cm.exception))

        def kaputt(url, **kw):
            raise ConnectionError(f"kaputt {GEHEIM}")
        with self.assertRaises(YU.UploadFehler) as cm:
            YU.zugang("id", "s", GEHEIM, kaputt)
        self.assertNotIn(GEHEIM, str(cm.exception))
        with self.assertRaises(YU.UploadFehler):           # Token ohne Upload-Recht
            YU.zugang("id", "s", "x", lambda url, **kw: R(200, {"access_token": "a", "scope": "openid email"}))


class Metadaten(unittest.TestCase):
    def test_immer_privat_und_grenzen(self):
        m = YU.metadaten("<b>Titel</b> " + "x" * 200, "Text <script>", ["ETF", "Spar,plan"] + ["t" * 50] * 20,
                         "999", "de", False, True)
        self.assertEqual(m["status"]["privacyStatus"], "private")
        self.assertTrue(m["status"]["containsSyntheticMedia"])
        self.assertFalse(m["status"]["selfDeclaredMadeForKids"])
        self.assertEqual(len(m["snippet"]["title"]), 100)
        self.assertNotIn("<", m["snippet"]["title"] + m["snippet"]["description"])
        self.assertEqual(m["snippet"]["categoryId"], "27")
        self.assertIn("Spar plan", m["snippet"]["tags"])
        self.assertLessEqual(sum(len(t) + 2 for t in m["snippet"]["tags"]), 480)
        with self.assertRaises(YU.UploadFehler):
            YU.metadaten("  ", "")
        self.assertEqual(YU.titel_und_beschreibung("Mein Titel\n\nZeile 1\nZeile 2"), ("Mein Titel", "Zeile 1\nZeile 2"))


class Hochladen(unittest.TestCase):
    def test_in_teilen_mit_fortschritt(self):
        g = Google()
        stand = []
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\0" * (YU.STUECK * 2 + 123))
        try:
            with mock.patch.object(YU, "STUECK", YU.STUECK):
                vid = YU.hochladen(f.name, YU.metadaten("T", "B"), "ya29.zugang", g.post, g.put, stand.append)
        finally:
            os.unlink(f.name)
        self.assertEqual(vid, "VIDEO123")
        self.assertEqual(len(g.teile), 3)
        self.assertTrue(g.teile[0].startswith("bytes 0-"))
        self.assertEqual(g.meta["status"]["privacyStatus"], "private")
        self.assertEqual(stand[-1], 1.0)
        meta = YU.metadaten("T", "B")
        meta["status"]["privacyStatus"] = "public"
        with self.assertRaises(YU.UploadFehler):                 # oeffentlich geht nie
            YU.hochladen(__file__, meta, "t", g.post, g.put)
        quota = lambda url, **kw: R(403, {"error": {"errors": [{"reason": "quotaExceeded"}]}})  # noqa: E731
        with self.assertRaises(YU.UploadFehler) as cm:
            YU.hochladen(__file__, YU.metadaten("T", ""), "t", quota, g.put)
        self.assertIn("kontingent", str(cm.exception).lower())
        ok, text = YU.thumbnail_setzen("VIDEO123", b"jpg", "t", g.post)
        self.assertFalse(ok)
        self.assertIn("verifizierten Kanal", text)


def _app():
    import json as _json
    import streamlit as st
    import test_pyramide as T
    import test_youtube_upload as TU
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
    if "google" not in st.session_state:
        st.session_state["google"] = TU.Google()
    sp, g = st.session_state["speicher"], st.session_state["google"]
    dateien = {"video.mp4": b"\0" * 1000, "beschreibung.txt": "Mein Video\n\nBeschreibung hier".encode(),
               "thumbnail_1.jpg": b"jpg"}
    ids = {name: i for i, name in enumerate(dateien, 1)}
    upload = None if st.session_state.get("ohne_oauth") else {
        "zugang": lambda: YU_zugang(g), "post": g.post, "put": g.put}

    def YU_zugang(g):
        import youtube_upload
        return youtube_upload.zugang("id", "secret", "gut", g.post)
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "get": None, "yt_upload": upload,
                      "release_laden": lambda aid: next(v for k, v in dateien.items() if ids[k] == aid),
                      "zugaenge": {"YOUTUBE_API_KEY": True, "YOUTUBE_REFRESH_TOKEN": bool(upload)}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/youtube/projekte/p1.json") or {}))


def _projekt(status="freigegeben"):
    return {"id": "p1", "erstellt": "2026-11-24T10:00:00+00:00", "auftrag": "Test", "dauer_min": 1, "sprache": "de",
            "format": "16:9", "qualitaet": "standard", "untertitel": True, "stimme": "thorsten-medium",
            "skript": {"titel": "Mein Video"}, "szenen": [], "status": status, "protokoll": [],
            "schritte": {n: {"status": "ok"} for n in __import__("video_factory.pipeline", fromlist=["x"]).SCHRITTE},
            "kosten": {"posten": [], "summe": 0.0}, "bericht": None,
            "dateien": {"tags": ["ETF"], "release": {"tag": "video-p1", "assets": {
                "video.mp4": {"id": 1}, "beschreibung.txt": {"id": 2}, "thumbnail_1.jpg": {"id": 3}}}}}


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class UploadOberflaeche(unittest.TestCase):
    def _start(self, status="freigegeben", ohne_oauth=False):
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        sp = T.Speicher()
        sp.d["u/state/youtube/projekte/p1.json"] = _projekt(status)
        sp.d["u/state/youtube.json"] = {"projekte": [{"id": "p1", "titel": "Mein Video", "status": status,
                                                      "erstellt": "2026-11-24T10:00:00+00:00", "dauer_min": 1}]}
        at.session_state["speicher"] = sp
        at.session_state["ohne_oauth"] = ohne_oauth
        at.session_state["yt_bereich"] = "Video Factory"
        return at.run()

    def test_privat_hochladen(self):
        at = self._start()
        self.assertFalse(at.exception)
        self.assertEqual(at.text_input(key="yt_vf_up_titel_p1").value, "Mein Video")
        self.assertTrue(at.button(key="yt_vf_up_btn_p1").disabled)          # erst nach Bestaetigung
        at.selectbox(key="yt_vf_up_thumb_p1").set_value(1).run()
        at.checkbox(key="yt_vf_up_ok_p1").check().run()
        at.button(key="yt_vf_up_btn_p1").click().run()
        self.assertFalse(at.exception)
        p = at.session_state["speicher"].d["u/state/youtube/projekte/p1.json"]
        self.assertEqual((p["youtube"]["video_id"], p["youtube"]["sichtbarkeit"]), ("VIDEO123", "privat"))
        g = at.session_state["google"]
        self.assertEqual(g.meta["status"]["privacyStatus"], "private")
        self.assertEqual(g.meta["snippet"]["description"], "Beschreibung hier")
        self.assertEqual(g.thumb, "VIDEO123")
        api = at.session_state["speicher"].d["u/state/youtube_api.json"]
        self.assertEqual(api["kontingent"]["verbraucht"], YU.KOSTEN_UPLOAD + YU.KOSTEN_THUMBNAIL)
        self.assertTrue(any("YouTube Studio" in x.value for x in at.success))

    def test_ohne_freigabe_und_ohne_oauth(self):
        at = self._start(status="freigabe_noetig")
        self.assertFalse(at.exception)
        self.assertEqual([b for b in at.button if b.key == "yt_vf_up_btn_p1"], [])
        at = self._start(ohne_oauth=True)
        self.assertFalse(at.exception)
        self.assertTrue(any("OAuth" in x.value for x in at.info))


if __name__ == "__main__":
    unittest.main()
