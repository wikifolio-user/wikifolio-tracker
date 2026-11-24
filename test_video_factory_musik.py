"""Tests Video Factory - Hintergrundmusik (video_factory/musik.py, Schritt "musik" der Pipeline): Einstellungen,
Openverse-Filter, erzeugte Klangflaeche, Mischen mit Absenkung, Fallback ohne Netz, eigene Datei nur mit Rechten,
Beschreibung, Lizenzen und Qualitaetsbericht. FFmpeg-Teile nur, wenn FFmpeg installiert ist."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from video_factory import musik as MU
from video_factory import pipeline as PL
from video_factory import skript as SK

FFMPEG = shutil.which("ffmpeg") is not None
try:
    import PIL  # noqa: F401
    PILLOW = True
except ImportError:
    PILLOW = False


def _dauer(pfad):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", pfad],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def _lautheit(pfad, start=None, dauer=None):
    args = ["ffmpeg", "-hide_banner", "-nostats"] + (["-ss", str(start)] if start is not None else []) + \
        (["-t", str(dauer)] if dauer else []) + ["-i", pfad, "-af", "volumedetect", "-f", "null", "-"]
    r = subprocess.run(args, capture_output=True, text=True)
    for z in r.stderr.splitlines():
        if "mean_volume" in z:
            return float(z.split("mean_volume:")[1].split("dB")[0])
    return None


def _testvideo(ziel, sekunden=6):
    """Schwarzes Bild, Ton: 3 s Stille, dann 3 s Ton (Stimme)."""
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c=black:s=320x180:d={sekunden}", "-f", "lavfi", "-i",
                    f"sine=frequency=600:duration={sekunden}:sample_rate=48000", "-filter_complex",
                    f"[1:a]volume='if(lt(t,{sekunden / 2}),0,0.5)':eval=frame[a]", "-map", "0:v", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", ziel], check=True)
    return ziel


class Kunde:
    def __init__(self, status, daten=None):
        self.status_code, self._d = status, daten

    def json(self):
        return self._d


class Einstellungen(unittest.TestCase):
    def test_grenzen(self):
        self.assertEqual(MU.einstellungen()["modus"], "klang")
        m = MU.einstellungen({"modus": "quatsch", "stimmung": "x", "lautstaerke_db": 5, "suche": "a" * 200})
        self.assertEqual((m["modus"], m["stimmung"], m["lautstaerke_db"], len(m["suche"])), ("klang", "ruhig", -8, 80))
        self.assertEqual(MU.einstellungen({"lautstaerke_db": "kaputt"})["lautstaerke_db"], -20)

    def test_openverse_filter(self):
        daten = {"results": [
            {"url": "https://a/x.mp3", "license": "cc0", "duration": 120000, "filetype": "mp3", "title": "Calm",
             "creator": "A", "foreign_landing_url": "https://a"},
            {"url": "https://b/x.mp3", "license": "by-nc", "duration": 120000, "filetype": "mp3"},   # NC verboten
            {"url": "https://c/x.mp3", "license": "by", "duration": 10000, "filetype": "mp3"},       # zu kurz
            {"url": "http://d/x.mp3", "license": "cc0", "duration": 120000, "filetype": "mp3"},       # kein https
            {"url": "https://e/x.mid", "license": "by", "duration": 120000, "filetype": "mid"},      # Format
            {"url": "https://f/x.ogg", "license": "by", "license_version": "4.0", "duration": 90000,
             "filetype": "ogg", "title": "Piano", "creator": "B", "license_url": "https://cc/by/4.0"},
            {"url": "https://g/?trackid=1&format=mp32", "license": "by", "duration": 200000, "filetype": "mp32"}]}
        k = MU.openverse_parsen(daten)
        self.assertEqual([x["url"] for x in k], ["https://a/x.mp3", "https://f/x.ogg",
                                                 "https://g/?trackid=1&format=mp32"])
        self.assertEqual(k[2]["typ"], "mp3")                            # Jamendo meldet "mp32"
        self.assertTrue(k[1]["namensnennung_noetig"])
        self.assertIn("CC BY 4.0", MU.namensnennung(k[1]))
        self.assertIn("license_type=commercial", MU.openverse_url("calm piano"))

    def test_suche_ohne_musik_kategorie(self):
        urls = []

        def get(url, **kw):
            urls.append(url)
            if "category=music" in url:
                return Kunde(200, {"results": []})
            return Kunde(200, {"results": [
                {"url": "https://a/kurz.mp3", "license": "cc0", "duration": 60000, "filetype": "mp3"},
                {"url": "https://a/lang.mp3", "license": "cc0", "duration": 300000, "filetype": "mp3"}]})
        k = MU.suchen("calm", get)
        self.assertEqual(len(urls), 2)
        self.assertEqual(k[0]["url"], "https://a/lang.mp3")              # laengere Stuecke zuerst
        with self.assertRaises(MU.MusikFehler):
            MU.suchen("x", lambda url, **kw: Kunde(503))

    def test_namensnennung(self):
        self.assertIn("erzeugte Klangfläche", MU.namensnennung({"lizenz": "eigen"}))
        self.assertIn("Nutzungsrechte", MU.namensnennung({"lizenz": "rechte"}))
        self.assertIsNone(MU.namensnennung(None))


@unittest.skipUnless(FFMPEG, "FFmpeg nicht installiert")
class Mischen(unittest.TestCase):
    def test_erzeugen_und_absenken(self):
        with tempfile.TemporaryDirectory() as d:
            klang = MU.erzeugen(os.path.join(d, "k.m4a"), 6, "spannend")
            self.assertAlmostEqual(_dauer(klang["pfad"]), 7.0, delta=0.3)
            self.assertEqual(klang["lizenz"], "eigen")
            video = _testvideo(os.path.join(d, "v.mp4"))
            ziel = MU.mischen(video, klang["pfad"], os.path.join(d, "m.mp4"), 6.0, -20)
            self.assertAlmostEqual(_dauer(ziel), 6.0, delta=0.2)
            # Musik ist in der Stille hoerbar, aber leise; mit Stimme bleibt die Stimme bestimmend
            still = _lautheit(ziel, 0.5, 2)
            self.assertIsNotNone(still)
            self.assertLess(still, -25)
            self.assertGreater(still, -70)
            stimme = _lautheit(ziel, 3.5, 2)
            self.assertGreater(stimme, still + 6)


def _still(ziel, sekunden):
    import wave
    with wave.open(ziel, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * int(22050 * sekunden))
    return sekunden


@unittest.skipUnless(FFMPEG and PILLOW, "FFmpeg/Pillow nicht installiert")
class Pipeline(unittest.TestCase):
    TEXT = "Einleitung zum Test.\n\n## Teil eins\nEin kurzer Satz für die Szene."

    def setUp(self):
        self.alt = PL.ST.stimme_laden, PL.ST.sprechen
        PL.ST.stimme_laden = lambda *a, **k: "modell.onnx"
        PL.ST.sprechen = lambda text, modell, ziel, tempo=1.0: (os.makedirs(os.path.dirname(ziel), exist_ok=True),
                                                                 _still(ziel, 2.5))[1]   # loudnorm braucht >= 3 s

    def tearDown(self):
        PL.ST.stimme_laden, PL.ST.sprechen = self.alt

    def _lauf(self, musik, ctx=None):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p = PL.neues_projekt("Test", dauer_min=0.5, skript=SK.aus_text("Musiktest", self.TEXT), qualitaet="entwurf",
                             musik=musik)
        return PL.ausfuehren(p, {"ordner": d, "get": None, "ki": None, **(ctx or {})}), d

    def test_openverse_ohne_netz_nimmt_klangflaeche(self):
        def get(url, **kw):
            raise ConnectionError("kein Netz")
        p, d = self._lauf({"modus": "openverse"}, {"get": get})
        self.assertEqual(p["status"], "freigabe_noetig", p["protokoll"][-3:])
        self.assertEqual(p["dateien"]["musik"]["lizenz"], "eigen")
        self.assertTrue(any("Klangfläche verwendet" in x["text"] for x in p["protokoll"]))
        self.assertEqual(os.path.basename(p["dateien"]["video"]), "video.mp4")      # Ergebnisname bleibt gleich
        self.assertTrue(os.path.exists(p["dateien"]["video_ohne_musik"]))
        with open(p["dateien"]["beschreibung"], encoding="utf-8") as f:
            self.assertIn("Musik: eigene, erzeugte Klangfläche.", f.read())
        with open(p["dateien"]["lizenzen"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)[-1]["szene"], "musik")
        self.assertEqual({n: e for n, e, _ in p["bericht"]["punkte"]}["Musiklizenz"], "ok")

    def test_aus_und_eigene_ohne_rechte(self):
        p, _ = self._lauf({"modus": "aus"})
        self.assertEqual(p["status"], "freigabe_noetig")
        self.assertIsNone(p["dateien"]["musik"])
        self.assertIn("keine Hintergrundmusik", dict((n, t) for n, _, t in p["bericht"]["punkte"])["Musiklizenz"])
        p, _ = self._lauf({"modus": "eigene", "asset_id": 5}, {"release_laden": lambda aid: b"x"})
        self.assertEqual(p["status"], "fehler")
        self.assertIn("Rechte", p["schritte"]["musik"]["meldung"])

    def test_alte_projekte_und_abhaengigkeiten(self):
        p = PL.neues_projekt("x", skript=SK.aus_text("T", "Ein Satz."))
        del p["musik"]
        del p["schritte"]["musik"]
        with tempfile.TemporaryDirectory() as d:
            p = PL.ausfuehren(p, {"ordner": d, "get": None, "ki": None}, bis="storyboard")
        self.assertEqual(p["musik"], {"modus": "aus"})                   # bisherige Projekte bleiben ohne Musik
        self.assertEqual(p["schritte"]["musik"]["status"], "offen")
        for s in ("musik", "beschreibung", "qualitaet"):
            p["schritte"][s] = {"status": "ok"}
        PL.zuruecksetzen(p, "schnitt")
        self.assertEqual([p["schritte"][s]["status"] for s in ("musik", "qualitaet")], ["offen", "offen"])
        PL.zuruecksetzen(p, "musik")
        self.assertEqual(p["schritte"]["beschreibung"]["status"], "offen")


if __name__ == "__main__":
    unittest.main()
