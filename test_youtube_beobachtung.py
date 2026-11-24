"""Tests Faceless YouTube - Beobachtungen und Recherche-Agent (youtube_beobachtung.py, youtube_recherche_agent.py,
Ansicht Recherche -> Beobachtung) mit nachgebauter API und nachgebautem State - ohne Netz, ohne Schluessel."""
import datetime
import json
import unittest
from unittest import mock

import youtube_api as YA
import youtube_beobachtung as YB

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

UTC = datetime.timezone.utc
JETZT = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


class Api:
    """search liefert 12 Videos; ab dem zweiten Aufruf kommt ein neuer Ausreisser dazu."""

    def __init__(self):
        self.suchen = 0

    def __call__(self, endpunkt, params):
        if endpunkt == "search":
            self.suchen += 1
            ids = [f"v{i}" for i in range(12)] + (["neu1"] if self.suchen > 1 else [])
            return {"items": [{"id": {"videoId": v}} for v in ids]}
        if endpunkt == "videos":
            datum = (JETZT - datetime.timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"items": [{"id": v, "snippet": {"title": f"Titel {v}", "channelId": "UC" + v.rjust(22, "x"),
                                                    "channelTitle": f"Kanal {v}", "publishedAt": datum},
                               "statistics": {"viewCount": "90000" if v == "neu1" else "20000"},
                               "contentDetails": {"duration": "PT9M"}} for v in params["id"].split(",")]}
        if endpunkt == "channels":
            return {"items": [{"id": c, "snippet": {"title": c}, "statistics": {
                "subscriberCount": "3000" if c.endswith("neu1") else "200000"}} for c in params["id"].split(",")]}
        raise AssertionError(endpunkt)


class Beobachtungen(unittest.TestCase):
    def test_anlegen_doppelt_grenze(self):
        b = YB.neue_beobachtung(" ETF Sparplan ", 90, "Longform", "DE", "de")
        self.assertEqual((b["begriff"], b["aktiv"]), ("ETF Sparplan", True))
        liste = YB.hinzufuegen([], b)
        self.assertEqual(YB.hinzufuegen(liste, dict(YB.neue_beobachtung("etf sparplan", 90, "Longform", "DE", "de"))),
                         liste)                                              # gleiche Suche nur einmal
        voll = [YB.neue_beobachtung(f"T{i}") for i in range(YB.MAX_BEOBACHTUNGEN)]
        with self.assertRaises(ValueError):
            YB.hinzufuegen(voll, YB.neue_beobachtung("zu viel"))
        with self.assertRaises(ValueError):
            YB.neue_beobachtung("  ")
        self.assertEqual(YB.kosten_pro_tag(voll[:3] + [dict(voll[3], aktiv=False)]), 3 * 102)

    def test_lauf_verlauf_und_neue_ausreisser(self):
        api = Api()
        b = YB.neue_beobachtung("ETF")
        s1, e1, z1 = YB.lauf([b], api, {}, 8000, JETZT, {})
        self.assertEqual(e1, 102)
        self.assertEqual(len(s1["verlauf"][b["id"]]), 1)
        self.assertEqual(s1["neu"][b["id"]], [])                    # erster Lauf: alles ist Grundbestand
        morgen = JETZT + datetime.timedelta(days=1)
        s2, _, z2 = YB.lauf([b], api, {}, 8000, morgen, s1)
        self.assertEqual([v["id"] for v in s2["neu"][b["id"]]], ["neu1"])
        self.assertIn("1 neue Ausreißer", z2[0])
        self.assertEqual(len(s2["verlauf"][b["id"]]), 2)
        s3, _, _ = YB.lauf([b], api, {}, 8000, morgen, s2)           # gleicher Tag: Eintrag ersetzt, nicht doppelt
        self.assertEqual(len(s3["verlauf"][b["id"]]), 2)
        self.assertEqual(len(s3["neu"][b["id"]]), 1)                 # bereits gesehen -> nicht erneut neu
        self.assertEqual(len(s3["laeufe"]), 3)

    def test_grenze_pause_und_aufraeumen(self):
        b1, b2 = YB.neue_beobachtung("A"), YB.neue_beobachtung("B")
        api = YA.buchen({}, 7850, JETZT)
        s, e, z = YB.lauf([b1, b2], Api(), api, 8000, JETZT, {})
        self.assertEqual(e, 102)                                     # zweite Suche passt nicht mehr unter die Grenze
        self.assertIn("übersprungen", z[1])
        s, e, _ = YB.lauf([dict(b1, aktiv=False)], Api(), {}, 8000, JETZT, s)
        self.assertEqual(e, 0)
        self.assertNotIn(b2["id"], s["verlauf"])                     # geloeschte/fehlende Beobachtung aufgeraeumt


class Agent(unittest.TestCase):
    def test_main_bucht_und_speichert(self):
        import youtube_recherche_agent as AG
        b = YB.neue_beobachtung("ETF")
        state = {"state/youtube.json": {"beobachtungen": [b], "einstellungen": {"api_grenze": 5000}},
                 "state/youtube_api.json": YA.buchen({}, 10, datetime.datetime.now(UTC))}

        def lese(repo, branch, pfad, token, default=None):
            return state.get(pfad, default), "sha"

        def aktualisiere(repo, branch, pfad, token, aendern, default=None, message=""):
            state[pfad] = aendern(state.get(pfad, default))
            return True, state[pfad]
        with mock.patch.object(AG, "REPO", "o/state"), mock.patch.object(AG, "TOKEN", "t"), \
                mock.patch.object(AG, "KEY", "k"), \
                mock.patch.object(AG.github_store, "lese_json", lese), \
                mock.patch.object(AG.github_store, "aktualisiere_json", aktualisiere), \
                mock.patch.object(AG.YA, "verbindung", lambda key, get: Api()):
            self.assertEqual(AG.main(), 0)
        self.assertEqual(YA.verbraucht(state["state/youtube_api.json"], datetime.datetime.now(UTC)), 112)
        self.assertEqual(len(state[YB.PFAD_RECHERCHE]["verlauf"][b["id"]]), 1)
        with mock.patch.object(AG, "REPO", "o/state"), mock.patch.object(AG, "TOKEN", "t"), \
                mock.patch.object(AG, "KEY", ""):
            self.assertEqual(AG.main(), 0)                           # ohne Secret: kein Fehler, nichts zu tun

    def test_workflow(self):
        import os
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github", "workflows",
                               "youtube-recherche.yml"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("python youtube_recherche_agent.py", text)
        self.assertIn("group: youtube-recherche", text)
        self.assertIn("YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}", text)


def _app():
    import json as _json
    import streamlit as st
    import test_pyramide as T
    import youtube_ui
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
    sp = st.session_state["speicher"]
    youtube_ui.seite({"lesen": sp.lesen, "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b,
                      "speichern": True, "get": None, "yt_abruf": None,
                      "zugaenge": {"YOUTUBE_API_KEY": True, "GEMINI_API_KEY": False}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/youtube.json") or {}))


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class BeobachtungOberflaeche(unittest.TestCase):
    def _d(self, at):
        return json.loads([x.value for x in at.markdown if x.value.startswith("SPEICHER:")][-1][len("SPEICHER:"):])

    def test_anlegen_verlauf_pausieren_loeschen(self):
        import test_pyramide as T
        at = AppTest.from_function(_app, default_timeout=120)
        at.session_state["speicher"] = T.Speicher()
        at.run()
        at.segmented_control(key="yt_bereich").set_value("Recherche").run()
        at.segmented_control(key="yt_rech_teil").set_value("Beobachtung").run()
        self.assertFalse(at.exception)
        at.text_input(key="yt_b_begriff").set_value("ETF Sparplan").run()
        at.button(key="yt_b_btn").click().run()
        b = self._d(at)["beobachtungen"]
        self.assertEqual(b[0]["begriff"], "ETF Sparplan")
        # Verlauf wie vom Agenten geschrieben
        api = Api()
        stand, _, _ = YB.lauf(b, api, {}, 8000, JETZT, {})
        stand, _, _ = YB.lauf(b, api, {}, 8000, JETZT + datetime.timedelta(days=1), stand)
        at.session_state["speicher"].d["u/" + YB.PFAD_RECHERCHE] = stand
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any("neue Ausreißer" in x.value for x in at.markdown))
        self.assertGreaterEqual(len(at.dataframe), 1)
        at.button(key=f"yt_b_pause_{b[0]['id']}").click().run()
        self.assertFalse(self._d(at)["beobachtungen"][0]["aktiv"])
        at.button(key=f"yt_b_del_{b[0]['id']}").click().run()
        self.assertEqual(self._d(at)["beobachtungen"], [])
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
