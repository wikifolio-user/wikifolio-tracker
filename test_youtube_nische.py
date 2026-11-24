"""Tests Faceless YouTube Phase 2b: Nischen-Score und Einnahmepotenzial (youtube_nische.py), dazu der Klickweg
Nische -> Idee -> Video Factory und die RPM-Tabelle in der Oberflaeche - mit nachgebauter API, ohne Netz."""
import datetime
import unittest

import youtube_api as YA
import youtube_nische as YN

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

UTC = datetime.timezone.utc
JETZT = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def _v(i, views, abos, tage, kategorie="27"):
    return {"id": f"v{i}", "titel": f"Video {i}", "kanal_id": f"UC{i:022d}", "kanal": f"Kanal {i}", "views": views,
            "abonnenten": abos, "alter_tage": tage, "faktor_kanal": views / abos if abos else None,
            "kategorie": kategorie, "url": f"https://www.youtube.com/watch?v=v{i}", "shorts": False}


def _nische(n_gross, n_klein_treffer, n_rest, views=100000, jung=0):
    vs, i = [], 0
    for _ in range(n_gross):
        vs.append(_v(i, views, 500000, 200))
        i += 1
    for _ in range(n_klein_treffer):
        vs.append(_v(i, views, 5000, 200))
        i += 1
    for _ in range(n_rest):
        vs.append(_v(i, views, 50000, 200))
        i += 1
    for v in vs[:jung]:
        v["alter_tage"] = 30
    return vs


class Score(unittest.TestCase):
    def test_teilwerte(self):
        b = YN.bewerten(_nische(10, 5, 5, views=100000, jung=10), 365)
        self.assertEqual(b["teile"]["nachfrage"], 67)                    # log10(1e5) = 5 -> (5-3)/3
        self.assertEqual(b["teile"]["konkurrenz"], 50)                   # 50 % grosse Kanaele
        self.assertEqual(b["teile"]["chance"], 100)                      # 25 % kleine Kanaele mit Treffer
        self.assertEqual(b["teile"]["frische"], 100)                     # 50 % junge Videos
        self.assertEqual(b["gesamt"], round((67 * 35 + 50 * 25 + 100 * 25 + 100 * 15) / 100))
        self.assertFalse(b["vorlaeufig"])
        self.assertEqual(len(b["chancen"]), 5)
        self.assertIn("50%", b["texte"]["konkurrenz"].replace(" ", ""))

    def test_grenzen_und_einstufung(self):
        self.assertEqual(YN.bewerten(_nische(0, 0, 20, views=500), 365)["teile"]["nachfrage"], 0)
        self.assertEqual(YN.bewerten(_nische(0, 0, 20, views=5_000_000), 365)["teile"]["nachfrage"], 100)
        schwer = YN.bewerten(_nische(20, 0, 0, views=2000), 365)
        self.assertEqual((schwer["teile"]["konkurrenz"], schwer["teile"]["chance"]), (0, 0))
        self.assertEqual(schwer["einstufung"], "schwierig")
        gut = YN.bewerten(_nische(0, 10, 10, views=800000, jung=20), 365)
        self.assertEqual(gut["einstufung"], "vielversprechend")

    def test_zu_wenig_und_vorlaeufig(self):
        b = YN.bewerten(_nische(2, 2, 2), 365)
        self.assertIsNone(b["gesamt"])
        self.assertIn("mindestens 10", b["hinweis"])
        vs = _nische(0, 0, 15)
        for v in vs[:10]:                                                 # ausgeblendete Abonnenten
            v["abonnenten"], v["faktor_kanal"] = None, None
        b = YN.bewerten(vs, 365)
        self.assertTrue(b["vorlaeufig"])
        self.assertNotIn("konkurrenz", b["teile"])
        self.assertEqual(b["gesamt"], round((b["teile"]["nachfrage"] * 35 + b["teile"]["frische"] * 15) / 50))

    def test_frische_relativ_zum_zeitraum(self):
        vs = _nische(0, 0, 20)
        for v in vs[:10]:
            v["alter_tage"] = 8                                           # im 30-Tage-Zeitraum: Grenze 10 Tage
        self.assertEqual(YN.bewerten(vs, 30)["teile"]["frische"], 100)
        self.assertIn("10 Tage", YN.bewerten(vs, 30)["texte"]["frische"])


class Einnahmen(unittest.TestCase):
    def test_rpm_tabelle(self):
        t = YN.rpm_tabelle({"Technik & KI": [4, 12], "Eigene": [1, 2], "Kaputt": [5, 1], "X": ["a", 1]})
        self.assertEqual(t["Technik & KI"], (4.0, 12.0))
        self.assertEqual(t["Eigene"], (1.0, 2.0))
        self.assertNotIn("Kaputt", t)
        self.assertNotIn("X", t)
        self.assertEqual(YN.rpm_tabelle(None), YN.STANDARD_RPM)

    def test_potenzial(self):
        self.assertEqual(YN.einnahmen(100000, (2.0, 7.0)), (200.0, 700.0))
        p = YN.potenzial(100000, 8, (2.0, 7.0))
        self.assertEqual(p["realistisch"]["views_monat"], 160000)         # 20 % von 100.000 x 8
        self.assertAlmostEqual(p["realistisch"]["von"], 320.0)
        self.assertAlmostEqual(p["optimistisch"]["bis"], 100000 * 0.6 * 8 / 1000 * 7)
        s = YN.potenzial(100000, 8, (2.0, 7.0), shorts=True)
        self.assertAlmostEqual(s["realistisch"]["bis"], 160000 / 1000 * YN.SHORTS_RPM[1])

    def test_nische_raten(self):
        self.assertEqual(YN.nische_raten("ETF Sparplan für Anfänger"), "Finanzen & Investieren")
        self.assertEqual(YN.nische_raten("KI Tools"), "Technik & KI")
        self.assertEqual(YN.nische_raten("Excel Tipps"), "Software & Tutorials")
        self.assertEqual(YN.nische_raten("irgendwas", [{"kategorie": "20"}, {"kategorie": "20"}, {"kategorie": "27"}]),
                         "Gaming")
        self.assertEqual(YN.nische_raten("irgendwas"), "Sonstiges")

    def test_kanal_views_monat(self):
        vs = [{"alter_tage": 10, "views": 30000}, {"alter_tage": 80, "views": 60000}, {"alter_tage": 200, "views": 9e6}]
        self.assertEqual(YN.kanal_views_monat(vs), 30000)


class GrosseApi:
    """Nachgebaute API mit 30 Treffern: 5 kleine Kanaele mit Treffer, 15 grosse."""

    def __init__(self):
        self.aufrufe = []

    def __call__(self, endpunkt, params):
        self.aufrufe.append(endpunkt)
        if endpunkt == "search":
            return {"items": [{"id": {"videoId": f"n{i}"}} for i in range(30)]}
        if endpunkt == "videos":
            datum = (datetime.datetime.now(UTC) - datetime.timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"items": [{"id": v, "snippet": {"title": f"Excel Trick {v}", "channelId": "UC" + v.rjust(22, "x"),
                                                    "channelTitle": f"Kanal {v}", "publishedAt": datum,
                                                    "categoryId": "27", "liveBroadcastContent": "none"},
                               "statistics": {"viewCount": "200000", "likeCount": "5000"},
                               "contentDetails": {"duration": "PT9M"}} for v in params["id"].split(",")]}
        if endpunkt == "channels":
            aus = []
            for c in params["id"].split(","):
                n = int(c.lstrip("UCx").lstrip("n") or 0)
                abos = 4000 if n < 5 else 900000 if n < 20 else 50000
                aus.append({"id": c, "snippet": {"title": f"Kanal {c}"},
                            "statistics": {"subscriberCount": str(abos), "viewCount": "1", "videoCount": "1"}})
            return {"items": aus}
        raise AssertionError(endpunkt)


def _app():
    import json as _json
    import streamlit as st
    import test_pyramide as T
    import test_youtube_nische as TN
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
        st.session_state["api"] = TN.GrosseApi()
    sp = st.session_state["speicher"]
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "get": None, "yt_abruf": st.session_state["api"], "ki": lambda: None,
                      "zugaenge": {"YOUTUBE_API_KEY": True, "GEMINI_API_KEY": False}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/youtube.json") or {}))


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class NischeOberflaeche(unittest.TestCase):
    def _d(self, at):
        import json
        return json.loads([x.value for x in at.markdown if x.value.startswith("SPEICHER:")][-1][len("SPEICHER:"):])

    def test_nische_idee_factory_und_rpm(self):
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        at.session_state["speicher"] = T.Speicher()
        at.session_state["api"] = GrosseApi()
        at.run()
        at.segmented_control(key="yt_bereich").set_value("Recherche").run()
        at.segmented_control(key="yt_rech_teil").set_value("Nische").run()
        at.text_input(key="yt_n_begriff").set_value("Excel Tipps").run()
        at.button(key="yt_n_btn").click().run()
        self.assertFalse(at.exception)
        kpis = " ".join(x.value for x in at.markdown)
        self.assertIn("Nischen-Score", kpis)
        self.assertIn("Schätzung", kpis)
        self.assertEqual(at.selectbox(key="yt_n_rpm").value, "Software & Tutorials")
        self.assertEqual(len(at.dataframe), 1)                             # Chancen-Tabelle (5 kleine Kanaele)
        # Nische als Idee -> Video Factory mit vorbereitetem Auftrag
        at.button(key="yt_n_idee").click().run()
        ideen = self._d(at)["ideen"]
        self.assertEqual(ideen[0]["titel"], "Nische: Excel Tipps")
        self.assertIn("Nischen-Score", ideen[0]["notiz"])
        at.segmented_control(key="yt_rech_teil").set_value("Ideen").run()
        at.button(key=f"yt_idee_vf_{ideen[0]['id']}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.segmented_control(key="yt_bereich").value, "Video Factory")
        at.segmented_control(key="yt_vf_quelle").set_value("eigen").run()
        self.assertEqual(at.text_input(key="yt_vf_titel").value, "Excel Tipps")
        self.assertIn("„Excel Tipps“", at.session_state["yt_vf_auftrag"])
        # RPM-Spanne anpassen; Einstellungen speichern verliert sie nicht
        at.segmented_control(key="yt_bereich").set_value("Finanzen").run()
        at.segmented_control(key="yt_fin_teil").set_value("Einnahmepotenzial").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Werbung pro Monat" in x.value for x in at.markdown))
        sp = at.session_state["speicher"]
        sp.d["u/state/youtube.json"]["einstellungen"] = {"rpm": {"Gaming": [2.0, 4.0]}}
        at.segmented_control(key="yt_bereich").set_value("Einstellungen").run()
        at.button(key="yt_e_btn").click().run()
        e = self._d(at)["einstellungen"]
        self.assertEqual((e["rpm"], e["api_grenze"]), ({"Gaming": [2.0, 4.0]}, 8000))


if __name__ == "__main__":
    unittest.main()
