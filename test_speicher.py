"""Tests fuer github_store und chronik (python3 -m unittest test_speicher) - ohne Netz, requests gemockt."""
import base64
import json
import unittest
from unittest import mock

import chronik as C
import github_store as G


class FakeGitHub:
    """Minimaler Ersatz fuer die Contents-API: speichert Dateien mit sha, kann Fehler einstreuen."""
    def __init__(self):
        self.dateien = {}          # pfad -> (json_text, sha)
        self.n = 0
        self.lesefehler = 0        # so viele naechste GETs liefern 403
        self.fremd_schreiben = None  # Funktion, die vor dem naechsten PUT "von aussen" schreibt

    def _resp(self, code, body=None):
        r = mock.Mock(status_code=code)
        r.json = lambda: body
        r.raise_for_status = mock.Mock(side_effect=None if code < 400 else Exception(f"HTTP {code}"))
        return r

    def get(self, url, headers=None, params=None, timeout=None):
        pfad = url.split("/contents/")[1]
        if self.lesefehler:
            self.lesefehler -= 1
            return self._resp(403, {})
        if pfad not in self.dateien:
            return self._resp(404, {})
        text, sha = self.dateien[pfad]
        return self._resp(200, {"content": base64.b64encode(text.encode()).decode(), "sha": sha, "size": len(text)})

    def put(self, url, headers=None, json=None, timeout=None):
        pfad = url.split("/contents/")[1]
        if self.fremd_schreiben:
            f, self.fremd_schreiben = self.fremd_schreiben, None
            f()
        akt = self.dateien.get(pfad, (None, None))[1]
        if akt != json.get("sha"):
            return self._resp(409, {})
        self.n += 1
        self.dateien[pfad] = (base64.b64decode(json["content"]).decode(), f"sha{self.n}")
        return self._resp(200, {})

    def setze(self, pfad, obj):
        self.n += 1
        self.dateien[pfad] = (json.dumps(obj), f"sha{self.n}")

    def inhalt(self, pfad):
        return json.loads(self.dateien[pfad][0])


class Basis(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub()
        self.p1 = mock.patch.object(G.requests, "get", self.gh.get)
        self.p2 = mock.patch.object(G.requests, "put", self.gh.put)
        self.p1.start(); self.p2.start()
        G._fehlerhaft().clear()

    def tearDown(self):
        self.p1.stop(); self.p2.stop()


class Speicher(Basis):
    def test_404_liefert_default_und_schreiben_erlaubt(self):
        daten, sha = G.get_json("r", "b", "x.json", "t", default=[])
        self.assertEqual((daten, sha), ([], None))
        self.assertTrue(G.put_json("r", "b", "x.json", [1], "t"))

    def test_lesefehler_sperrt_ueberschreiben(self):
        self.gh.setze("chronik.json", [{"id": i} for i in range(50)])
        self.gh.lesefehler = 1
        daten, _ = G.get_json("r", "b", "chronik.json", "t", default=[])
        self.assertEqual(daten, [])                                  # Leerwert wie bisher
        self.assertFalse(G.put_json("r", "b", "chronik.json", [{"id": 1}], "t"))
        self.assertEqual(len(self.gh.inhalt("chronik.json")), 50)    # nichts verloren
        G.get_json("r", "b", "chronik.json", "t", default=[])         # erfolgreich gelesen -> wieder frei
        self.assertTrue(G.put_json("r", "b", "chronik.json", [], "t"))

    def test_lese_json_wirft(self):
        self.gh.lesefehler = 1
        with self.assertRaises(G.LeseFehler):
            G.lese_json("r", "b", "a.json", "t")

    def test_aktualisiere_ohne_verlorene_updates(self):
        self.gh.setze("l.json", ["a"])
        # waehrend unseres Schreibens haengt jemand anderes "b" an
        self.gh.fremd_schreiben = lambda: self.gh.setze("l.json", ["a", "b"])
        ok, neu = G.aktualisiere_json("r", "b", "l.json", "t", lambda l: l + ["c"], default=[])
        self.assertTrue(ok)
        self.assertEqual(self.gh.inhalt("l.json"), ["a", "b", "c"])

    def test_aktualisiere_bei_lesefehler_nichts(self):
        self.gh.setze("l.json", ["a"])
        self.gh.lesefehler = 1
        ok, _ = G.aktualisiere_json("r", "b", "l.json", "t", lambda l: [], default=[])
        self.assertFalse(ok)
        self.assertEqual(self.gh.inhalt("l.json"), ["a"])

    def test_put_mit_sha_konflikt(self):
        self.gh.setze("k.json", {"v": 1})
        _, sha = G.get_json("r", "b", "k.json", "t")
        self.gh.setze("k.json", {"v": 2})
        self.assertFalse(G.put_json("r", "b", "k.json", {"v": 3}, "t", sha=sha))
        self.assertEqual(self.gh.inhalt("k.json"), {"v": 2})


class Chronik(Basis):
    def test_eintragen_bei_lesefehler_verliert_nichts(self):
        self.gh.setze("c.json", [C.neuer_eintrag("depot", f"e{i}") for i in range(30)])
        self.gh.lesefehler = 1
        self.assertFalse(C.eintragen_github(G, "r", "b", "c.json", "t", C.neuer_eintrag("alarm", "neu")))
        self.assertEqual(len(self.gh.inhalt("c.json")), 30)

    def test_eintragen_dedupe(self):
        e = C.neuer_eintrag("alarm", "x", schluessel="k1")
        self.assertTrue(C.eintragen_github(G, "r", "b", "c.json", "t", e))
        self.assertFalse(C.eintragen_github(G, "r", "b", "c.json", "t", e))
        self.assertEqual(len(self.gh.inhalt("c.json")), 1)

    def test_kuerzen_behaelt_notizen(self):
        liste = []
        liste, _ = C.anhaengen(liste, C.neuer_eintrag("notiz", "N", quelle="manuell"), max_n=3)
        for i in range(10):
            liste, _ = C.anhaengen(liste, C.neuer_eintrag("depot", f"a{i}"), max_n=3)
        self.assertEqual(len(liste), 3)
        self.assertIn("N", [x["titel"] for x in liste])
        self.assertEqual(liste[0]["titel"], "a9")

    def test_kaputte_id(self):
        liste, ok = C.anhaengen([{"id": "abc", "titel": "alt"}], C.neuer_eintrag("depot", "neu"))
        self.assertTrue(ok)
        self.assertEqual(liste[0]["id"], 1)


if __name__ == "__main__":
    unittest.main()
