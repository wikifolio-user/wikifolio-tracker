"""Tests Faceless YouTube Phase 2a: youtube_api.py (Abruf, Kontingent, Zwischenspeicher, Trends, Suche, Kanal)
und die Recherche-Oberflaeche (youtube_recherche_ui.py) mit einer nachgebauten API - ohne Netz, ohne Schluessel."""
import datetime
import unittest

import youtube_api as YA

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

UTC = datetime.timezone.utc
JETZT = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
SCHLUESSEL = "AIzaTESTTESTTESTTESTTESTTESTTESTTEST123"


def _video(vid, kanal, views, tage_alt, dauer="PT8M", live="none", likes=None):
    datum = (JETZT - datetime.timedelta(days=tage_alt)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": vid, "snippet": {"title": f"Video {vid}", "channelId": kanal, "channelTitle": f"Kanal {kanal}",
                                   "publishedAt": datum, "categoryId": "27", "liveBroadcastContent": live,
                                   "thumbnails": {"medium": {"url": f"https://i.ytimg.com/{vid}.jpg"}}},
            "statistics": {"viewCount": str(views), "likeCount": str(likes if likes is not None else views // 50),
                           "commentCount": "3"},
            "contentDetails": {"duration": dauer}}


def _kanal(cid, abos, versteckt=False):
    return {"id": cid, "snippet": {"title": f"Kanal {cid}", "customUrl": f"@{cid.lower()}", "country": "DE",
                                   "publishedAt": "2020-01-01T00:00:00Z"},
            "statistics": {"subscriberCount": str(abos), "hiddenSubscriberCount": versteckt, "viewCount": "1000000",
                           "videoCount": "200"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}}}


KA, KB = "UC" + "a" * 22, "UC" + "b" * 22
VIDEOS = {v["id"]: v for v in [
    _video("v1", KA, 50000, 2), _video("v2", KB, 9000, 5, dauer="PT45S"), _video("v3", KA, 1000, 10),
    _video("v4", KB, 0, 0, live="upcoming"), _video("v5", KB, 300000, 30, dauer="PT1H2M3S")]}
# Kanal A: 8 Uploads, einer davon ein klarer Ausreisser
for i, (views, tage) in enumerate([(1000, 1), (1100, 8), (900, 15), (60000, 22), (1000, 29), (950, 36),
                                   (1200, 43), (800, 50)]):
    VIDEOS[f"a{i}"] = _video(f"a{i}", KA, views, tage)
VIDEOS["as"] = _video("as", KA, 5000, 3, dauer="PT30S")
KANAELE = {KA: _kanal(KA, 2000), KB: _kanal(KB, 500000, versteckt=True)}


class Api:
    """Nachgebaute YouTube Data API v3 (Antworten wie die echte API)."""

    def __init__(self):
        self.aufrufe = []

    def __call__(self, endpunkt, params):
        self.aufrufe.append((endpunkt, dict(params)))
        if endpunkt == "search":
            return {"items": [{"id": {"kind": "youtube#video", "videoId": v}} for v in ("v5", "v1", "v2", "v4", "v3")]}
        if endpunkt == "videos":
            if params.get("chart") == "mostPopular":
                return {"items": [VIDEOS[v] for v in ("v1", "v2", "v5")]}
            return {"items": [VIDEOS[v] for v in params["id"].split(",") if v in VIDEOS]}
        if endpunkt == "channels":
            if "forHandle" in params:
                return {"items": [KANAELE[KA]]} if params["forHandle"].lower() == "@kanala" else {}
            return {"items": [KANAELE[c] for c in params["id"].split(",") if c in KANAELE]}
        if endpunkt == "playlistItems":
            return {"items": [{"contentDetails": {"videoId": v}} for v in VIDEOS if v.startswith("a")]}
        raise AssertionError(endpunkt)


class Antwort:
    def __init__(self, status, daten):
        self.status_code, self._d = status, daten

    def json(self):
        if isinstance(self._d, Exception):
            raise self._d
        return self._d


class Verbindung(unittest.TestCase):
    def test_schluessel_nur_im_header(self):
        gesehen = {}

        def get(url, params=None, headers=None, timeout=None):
            gesehen.update(url=url, params=params, headers=headers)
            return Antwort(200, {"items": []})
        YA.verbindung(SCHLUESSEL, get)("videos", {"id": "x"})
        self.assertEqual(gesehen["headers"]["X-Goog-Api-Key"], SCHLUESSEL)
        self.assertNotIn(SCHLUESSEL, gesehen["url"] + str(gesehen["params"]))
        self.assertTrue(gesehen["url"].startswith("https://www.googleapis.com/youtube/v3/videos"))

    def test_fehlertexte_ohne_schluessel(self):
        def kaputt(url, **kw):
            raise ConnectionError(f"failed for {url}?key={SCHLUESSEL}")
        with self.assertRaises(YA.ApiFehler) as cm:
            YA.verbindung(SCHLUESSEL, kaputt)("videos", {})
        self.assertNotIn(SCHLUESSEL, str(cm.exception))
        self.assertIn("ConnectionError", str(cm.exception))

        def fehler(status, reason, msg=""):
            return lambda url, **kw: Antwort(status, {"error": {"code": status, "message": msg,
                                                                "errors": [{"reason": reason}]}})
        f = YA.verbindung(SCHLUESSEL, fehler(400, "weird", f"bad key {SCHLUESSEL}"))
        with self.assertRaises(YA.ApiFehler) as cm:
            f("videos", {})
        self.assertNotIn(SCHLUESSEL, str(cm.exception))
        self.assertIn("400", str(cm.exception))
        for reason, text in [("quotaExceeded", "Tageskontingent"), ("accessNotConfigured", "nicht aktiviert"),
                             ("videoChartNotFound", "keine Trendliste"), ("ipRefererBlocked", "Einschränkung")]:
            with self.assertRaises(YA.ApiFehler) as cm:
                YA.verbindung(SCHLUESSEL, fehler(403, reason))("videos", {})
            self.assertIn(text, str(cm.exception), reason)
        with self.assertRaises(YA.ApiFehler) as cm:
            YA.verbindung(SCHLUESSEL, fehler(400, "badRequest", "API key not valid. Please pass a valid API key."))(
                "videos", {})
        self.assertIn("ungültig", str(cm.exception))
        with self.assertRaises(YA.ApiFehler):
            YA.verbindung(SCHLUESSEL, lambda url, **kw: Antwort(200, ValueError("kein json")))("videos", {})
        with self.assertRaises(YA.ApiFehler):
            YA.verbindung(SCHLUESSEL, lambda url, **kw: Antwort(200, {}))("unbekannt", {})

    def test_zaehler(self):
        z = YA.Zaehler(Api())
        z("search", {})
        z("videos", {"id": "v1"})
        z("channels", {"id": KA})
        self.assertEqual((z.einheiten, z.aufrufe), (102, 3))


class Kontingent(unittest.TestCase):
    def test_tageswechsel_pazifik(self):
        vorher = datetime.datetime(2026, 11, 24, 7, 59, tzinfo=UTC)      # 23:59 in Kalifornien (PST, UTC-8)
        nachher = datetime.datetime(2026, 11, 24, 8, 1, tzinfo=UTC)
        s = YA.buchen({}, 102, vorher)
        s = YA.buchen(s, 3, vorher)
        self.assertEqual(YA.verbraucht(s, vorher), 105)
        self.assertEqual(YA.verbraucht(s, nachher), 0)
        self.assertEqual(YA.verbraucht(YA.buchen(s, 2, nachher), nachher), 2)
        self.assertIn("09:00", YA.neustart_text(vorher))                 # Mitternacht PST = 09:00 MEZ

    def test_grenze(self):
        s = YA.buchen({}, 7950, JETZT)
        self.assertEqual(YA.pruefen(s, 3, 8000, JETZT), 7950)
        with self.assertRaises(YA.ApiFehler) as cm:
            YA.pruefen(s, 102, 8000, JETZT)
        self.assertIn("Tagesgrenze", str(cm.exception))
        with self.assertRaises(YA.ApiFehler):                             # nie ueber das echte Tageslimit
            YA.pruefen(YA.buchen({}, 9950, JETZT), 102, 50000, JETZT)


class Zwischenspeicher(unittest.TestCase):
    def test_gueltigkeit_und_obergrenze(self):
        k = YA.cache_schluessel("suche", {"begriff": "ki", "tage": 30})
        self.assertEqual(k, YA.cache_schluessel("suche", {"tage": 30, "begriff": "ki"}))
        self.assertNotEqual(k, YA.cache_schluessel("suche", {"tage": 7, "begriff": "ki"}))
        s = YA.cache_ablegen({}, k, "suche", {"videos": [1]}, JETZT)
        self.assertEqual(YA.cache_holen(s, k, JETZT + datetime.timedelta(hours=23))["daten"], {"videos": [1]})
        self.assertIsNone(YA.cache_holen(s, k, JETZT + datetime.timedelta(hours=25)))
        for i in range(YA.CACHE_MAX + 5):
            s = YA.cache_ablegen(s, f"x{i}", "trends", i, JETZT + datetime.timedelta(minutes=i))
        self.assertEqual(len(s["cache"]), YA.CACHE_MAX)
        self.assertIn(f"x{YA.CACHE_MAX + 4}", s["cache"])
        s = YA.cache_ablegen(s, "neu", "trends", 1, JETZT + datetime.timedelta(days=2))   # Abgelaufenes faellt weg
        self.assertEqual(list(s["cache"]), ["neu"])


class Aufbereitung(unittest.TestCase):
    def test_dauer(self):
        for iso, s in [("PT45S", 45), ("PT8M", 480), ("PT1H2M3S", 3723), ("P1DT1S", 86401), ("P0D", 0), ("", None),
                       ("PT", None), ("xyz", None)]:
            self.assertEqual(YA.dauer_s(iso), s, iso)

    def test_video_und_kanal(self):
        v = YA.video_parsen(VIDEOS["v2"])
        self.assertEqual((v["shorts"], v["views"], v["dauer_s"]), (True, 9000, 45))
        self.assertEqual(v["url"], "https://www.youtube.com/watch?v=v2")
        k = YA.kanal_parsen(KANAELE[KB])
        self.assertIsNone(k["abonnenten"])                               # ausgeblendet = unbekannt, nicht 0
        self.assertEqual(k["uploads"], "UU" + "b" * 22)

    def test_anreichern(self):
        vs = YA.anreichern([YA.video_parsen(VIDEOS["v1"])], {KA: YA.kanal_parsen(KANAELE[KA])}, JETZT)
        self.assertAlmostEqual(vs[0]["views_pro_tag"], 25000)
        self.assertAlmostEqual(vs[0]["faktor_kanal"], 25.0)              # 50.000 Aufrufe / 2.000 Abos
        self.assertAlmostEqual(vs[0]["likes_pct"], 2.0)


class Abfragen(unittest.TestCase):
    def test_trends(self):
        api = YA.Zaehler(Api())
        r = YA.trends(api, "US", "27", JETZT)
        self.assertEqual(api.einheiten, 2)
        p = api._abruf.aufrufe[0][1]
        self.assertEqual((p["chart"], p["regionCode"], p["videoCategoryId"]), ("mostPopular", "US", "27"))
        self.assertEqual([v["id"] for v in r["videos"]], ["v1", "v2", "v5"])
        a = Api()
        YA.trends(a, "DE", "0", JETZT)
        self.assertNotIn("videoCategoryId", a.aufrufe[0][1])           # "Alle" = ohne Kategorie

    def test_suche(self):
        api = YA.Zaehler(Api())
        r = YA.suche(api, "KI Tools", 30, "Alle", "DE", "de", "viewCount", JETZT)
        self.assertEqual(api.einheiten, 102)
        p = api._abruf.aufrufe[0][1]
        self.assertEqual((p["q"], p["regionCode"], p["relevanceLanguage"], p["type"]), ("KI Tools", "DE", "de", "video"))
        self.assertEqual(p["publishedAfter"], "2026-10-25T12:00:00Z")
        self.assertEqual([v["id"] for v in r["videos"]], ["v5", "v1", "v2", "v3"])   # Reihenfolge der Suche, ohne Live
        self.assertEqual(r["treffer"], 5)
        self.assertEqual([v["id"] for v in YA.suche(Api(), "x", 30, "Shorts", jetzt=JETZT)["videos"]], ["v2"])
        self.assertEqual([v["id"] for v in YA.suche(Api(), "x", 30, "Longform", jetzt=JETZT)["videos"]],
                         ["v5", "v1", "v3"])
        a = Api()
        YA.suche(a, "x", 0, "Shorts", jetzt=JETZT)
        self.assertNotIn("publishedAfter", a.aufrufe[0][1])
        self.assertEqual(a.aufrufe[0][1]["videoDuration"], "short")
        with self.assertRaises(YA.ApiFehler):
            YA.suche(Api(), "  ")

    def test_kanal_eingaben(self):
        for e, erw in [(KA, ("id", KA)), (f"https://www.youtube.com/channel/{KA}/videos", ("id", KA)),
                       ("@KanalA", ("handle", "@KanalA")), ("https://youtube.com/@KanalA/videos", ("handle", "@KanalA")),
                       ("https://www.youtube.com/user/altername", ("username", "altername")),
                       ("KanalA", ("handle", "@KanalA"))]:
            self.assertEqual(YA.kanal_eingabe(e), erw, e)
        for e in ("https://www.youtube.com/c/Irgendwas", "", "zwei worte"):
            with self.assertRaises(YA.ApiFehler):
                YA.kanal_eingabe(e)

    def test_kanal_untersuchen(self):
        api = YA.Zaehler(Api())
        a = YA.kanal_untersuchen(api, "@KanalA", JETZT)
        self.assertEqual(api.einheiten, 3)
        self.assertEqual(a["kanal"]["abonnenten"], 2000)
        self.assertEqual(a["formate"]["Longform"]["anzahl"], 8)
        self.assertEqual(a["formate"]["Shorts"]["anzahl"], 1)
        aus = max(a["videos"], key=lambda v: v.get("outlier") or 0)
        self.assertEqual(aus["id"], "a3")
        self.assertGreater(aus["outlier"], 10)
        self.assertIsNone(next(v for v in a["videos"] if v["id"] == "as")["outlier"])   # zu wenig Shorts zum Vergleich
        self.assertEqual(a["letzter_upload"], (JETZT - datetime.timedelta(days=1)).date().isoformat())
        self.assertAlmostEqual(a["uploads_pro_woche"], round(9 / (90 / 7), 2))
        self.assertEqual(a["aufrufe_je_video"], 5000)
        with self.assertRaises(YA.ApiFehler):
            YA.kanal_untersuchen(Api(), "@gibtsnicht", JETZT)


def _app():
    import json as _json
    import streamlit as st
    import test_pyramide as T
    import test_youtube_api as TA
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
        st.session_state["api"] = TA.Api()
    sp, api = st.session_state["speicher"], st.session_state["api"]
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "get": None, "yt_abruf": api,
                      "zugaenge": {"YOUTUBE_API_KEY": True, "GEMINI_API_KEY": False}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/youtube.json") or {}))
    st.markdown("API:" + _json.dumps(sp.d.get("u/state/youtube_api.json") or {}))
    st.markdown(f"AUFRUFE:{len(api.aufrufe)}")


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class RechercheOberflaeche(unittest.TestCase):
    def _m(self, at, vorne):
        import json
        m = [x.value for x in at.markdown if x.value.startswith(vorne)][-1][len(vorne):]
        return json.loads(m) if vorne != "AUFRUFE:" else int(m)

    def test_suche_trends_kanal(self):
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        at.session_state["speicher"] = T.Speicher()
        at.session_state["api"] = Api()
        at.run()
        at.segmented_control(key="yt_bereich").set_value("Recherche").run()
        # Suche: 102 Einheiten gebucht, zweiter Klick aus dem Zwischenspeicher
        at.segmented_control(key="yt_rech_teil").set_value("Suche").run()
        self.assertFalse(at.exception)
        at.text_input(key="yt_s_begriff").set_value("KI Tools").run()
        at.button(key="yt_s_btn").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._m(at, "API:")["kontingent"]["verbraucht"], 102)
        n = self._m(at, "AUFRUFE:")
        self.assertEqual(len(at.dataframe), 1)
        at.button(key="yt_s_btn").click().run()
        self.assertEqual(self._m(at, "AUFRUFE:"), n)
        self.assertTrue(any("Zwischenspeicher" in x.value for x in at.caption))
        # Trends
        at.segmented_control(key="yt_rech_teil").set_value("Trends").run()
        at.button(key="yt_t_btn").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._m(at, "API:")["kontingent"]["verbraucht"], 104)
        # Kanal untersuchen per @Handle, dann ins Radar
        at.segmented_control(key="yt_rech_teil").set_value("Kanal untersuchen").run()
        at.text_input(key="yt_api_kanal").set_value("@KanalA").run()
        at.button(key="yt_k_btn").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._m(at, "API:")["kontingent"]["verbraucht"], 107)
        self.assertTrue(any("Kanal " + KA in x.value for x in at.markdown))
        at.text_input(key="yt_k_nische").set_value("Bildung").run()
        at.button(key="yt_k_radar_btn").click().run()
        r = self._m(at, "SPEICHER:")["radar"]
        self.assertEqual((r[0]["id"], r[0]["nische"]), (KA, "Bildung"))
        # Tagesgrenze greift: kein Abruf mehr, klare Meldung
        sp = at.session_state["speicher"]
        sp.d["u/state/youtube_api.json"]["kontingent"]["verbraucht"] = 7990
        at.segmented_control(key="yt_rech_teil").set_value("Suche").run()
        at.text_input(key="yt_s_begriff").set_value("etwas anderes").run()
        n = self._m(at, "AUFRUFE:")
        at.button(key="yt_s_btn").click().run()
        self.assertEqual(self._m(at, "AUFRUFE:"), n)
        self.assertTrue(any("Tagesgrenze" in x.value for x in at.warning))
        texte = " ".join(x.value for x in at.markdown) + " ".join(x.value for x in at.caption)
        self.assertNotIn("AIza", texte)

    def test_ohne_schluessel(self):
        import youtube_ui
        import test_pyramide as T

        def app():
            import streamlit as st
            import youtube_ui as Y
            sp = st.session_state["speicher"]
            Y.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: b, "speichern": True,
                     "zugaenge": {"YOUTUBE_API_KEY": False}})
        at = AppTest.from_function(app, default_timeout=60)
        at.session_state["speicher"] = T.Speicher()
        at.run()
        at.segmented_control(key="yt_bereich").set_value("Recherche").run()
        for teil in youtube_ui.RECHERCHE:
            at.segmented_control(key="yt_rech_teil").set_value(teil).run()
            self.assertFalse(at.exception, teil)
        at.segmented_control(key="yt_rech_teil").set_value("Suche").run()
        self.assertTrue(any("YOUTUBE_API_KEY" in x.value for x in at.info))


if __name__ == "__main__":
    unittest.main()
