"""Tests fuer github_store (python3 -m unittest test_github_store) - ohne Netz,
die GitHub-API wird durch einen kleinen Speicher im Arbeitsspeicher ersetzt."""
import base64
import json
import unittest
from unittest import mock

import github_store as G


class _Antwort:
    def __init__(self, status, daten=None):
        self.status_code = status
        self._d = daten or {}
        self.text = json.dumps(self._d)

    def json(self):
        return self._d


class FakeGitHub:
    """Speichert Dateien mit sha; kann Lesefehler und fremde Zwischen-Schreiber simulieren."""
    def __init__(self):
        self.dateien = {}          # pfad -> (obj, sha)
        self.zaehler = 0
        self.lesefehler = 0        # so viele GETs liefern 403
        self.fremd_vor_put = []    # Liste von (pfad, obj): vor dem naechsten PUT schreibt "jemand anderes"
        self.puts = 0

    def _sha(self):
        self.zaehler += 1
        return f"sha{self.zaehler}"

    def get(self, url, headers=None, params=None, timeout=None):
        if self.lesefehler:
            self.lesefehler -= 1
            return _Antwort(403, {"message": "rate limit"})
        pfad = url.split("/contents/", 1)[1]
        if pfad not in self.dateien:
            return _Antwort(404)
        obj, sha = self.dateien[pfad]
        roh = base64.b64encode(json.dumps(obj).encode()).decode()
        return _Antwort(200, {"content": roh, "sha": sha})

    def put(self, url, headers=None, json=None, timeout=None):
        pfad = url.split("/contents/", 1)[1]
        if self.fremd_vor_put:
            fp, fo = self.fremd_vor_put.pop(0)
            self.dateien[fp] = (fo, self._sha())
        self.puts += 1
        akt = self.dateien.get(pfad)
        gesendet = json.get("sha")
        if akt and gesendet != akt[1]:
            return _Antwort(409)
        if not akt and gesendet:
            return _Antwort(422)
        obj = __import__("json").loads(base64.b64decode(json["content"]).decode())
        self.dateien[pfad] = (obj, self._sha())
        return _Antwort(200)


class GitHubStoreTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub()
        p1 = mock.patch.object(G.requests, "get", self.gh.get)
        p2 = mock.patch.object(G.requests, "put", self.gh.put)
        p3 = mock.patch.object(G.time, "sleep", lambda s: None)
        for p in (p1, p2, p3):
            p.start()
            self.addCleanup(p.stop)
        G._fehlerhaft().clear()

    def test_404_ist_kein_fehler(self):
        self.assertEqual(G.lese_json("o/r", "b", "x.json", "t", default=[]), ([], None))

    def test_lesefehler_wird_gemeldet(self):
        self.gh.lesefehler = 1
        with self.assertRaises(G.LeseFehler):
            G.lese_json("o/r", "b", "x.json", "t")

    def test_anzeige_lesen_liefert_standard_bei_fehler(self):
        self.gh.lesefehler = 1
        self.assertEqual(G.get_json("o/r", "b", "x.json", "t", default=[]), ([], None))

    def test_lesefehler_ueberschreibt_nichts(self):
        # DATA-01: frueher wurde bei Rate-Limit die ganze Chronik durch [neuer Eintrag] ersetzt
        self.gh.dateien["chronik.json"] = ([{"id": i} for i in range(50)], "sha0")
        self.gh.lesefehler = 1
        ok, _ = G.aktualisiere_json("o/r", "b", "chronik.json", "t", lambda l: [{"id": 99}] + l, default=[])
        self.assertFalse(ok)
        self.assertEqual(len(self.gh.dateien["chronik.json"][0]), 50)
        self.assertEqual(self.gh.puts, 0)

    def test_paralleler_schreiber_geht_nicht_verloren(self):
        # DATA-02: zwischen Lesen und Schreiben schreibt jemand anderes -> beide Aenderungen bleiben
        self.gh.dateien["c.json"] = ([{"id": 1}], "sha0")
        self.gh.fremd_vor_put = [("c.json", [{"id": 2}, {"id": 1}])]
        ok, neu = G.aktualisiere_json("o/r", "b", "c.json", "t", lambda l: [{"id": 3}] + l, default=[])
        self.assertTrue(ok)
        self.assertEqual([x["id"] for x in self.gh.dateien["c.json"][0]], [3, 2, 1])

    def test_neue_datei(self):
        ok, neu = G.aktualisiere_json("o/r", "b", "neu.json", "t", lambda d: dict(d, a=1), default={})
        self.assertTrue(ok)
        self.assertEqual(self.gh.dateien["neu.json"][0], {"a": 1})

    def test_nichts_zu_tun(self):
        self.gh.dateien["d.json"] = ({"a": 1}, "sha0")
        ok, d = G.aktualisiere_json("o/r", "b", "d.json", "t", lambda d: None, default={})
        self.assertTrue(ok)
        self.assertEqual(self.gh.puts, 0)

    def test_put_mit_erwartetem_sha_ueberschreibt_nicht(self):
        self.gh.dateien["e.json"] = ({"v": 2}, "sha9")
        self.assertFalse(G.put_json("o/r", "b", "e.json", {"v": 1}, "t", sha="sha_alt"))
        self.assertEqual(self.gh.dateien["e.json"][0], {"v": 2})

    def test_put_ohne_sha_ueberschreibt(self):
        self.gh.dateien["f.json"] = ({"v": 2}, "sha9")
        self.assertTrue(G.put_json("o/r", "b", "f.json", {"v": 3}, "t"))
        self.assertEqual(self.gh.dateien["f.json"][0], {"v": 3})

    def test_log_schwaerzt_geheimnisse(self):
        t = G.sauber("POST https://discord.com/api/webhooks/123/abcDEF failed, Bearer ghp_abcdefghijklmnop")
        self.assertNotIn("abcDEF", t)
        self.assertNotIn("ghp_abcdefghijklmnop", t)


if __name__ == "__main__":
    unittest.main()
