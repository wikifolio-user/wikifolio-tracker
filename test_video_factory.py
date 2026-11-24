"""Tests Video Factory (video_factory/*): Skript, Storyboard, Untertitel, Lizenzpruefung, Bildsuche, Qualitaetsbericht
und ein kompletter Lauf (ohne Netz; Sprachausgabe durch stille Testdateien ersetzt; braucht FFmpeg + Pillow)."""
import json
import os
import shutil
import tempfile
import unittest
import wave

from video_factory import assets as AS
from video_factory import pipeline as PL
from video_factory import skript as SK
from video_factory import storyboard as SB

import importlib.util
PILLOW = importlib.util.find_spec("PIL") is not None
FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

TEXT = """Kleine Firmen haben wenig Zeit. KI kann helfen. [bild: small business office]

## Texte schreiben
Ein Assistent schreibt Entwürfe. Du prüfst sie immer selbst. [bild: typing laptop]

## Fazit
Starte mit einer Aufgabe."""


class Skript(unittest.TestCase):
    def test_aus_text(self):
        s = SK.aus_text("Titel", TEXT)
        self.assertEqual([k["titel"] for k in s["kapitel"]], ["Einleitung", "Texte schreiben", "Fazit"])
        self.assertEqual(s["kapitel"][0]["szenen"][0]["bild"], "small business office")
        self.assertNotIn("[bild", s["kapitel"][1]["szenen"][0]["text"])
        self.assertEqual((s["quelle"], s["geprueft"]), ("manuell", True))
        with self.assertRaises(SK.SkriptFehler):
            SK.aus_text("", "x")

    def test_ki_antwort_pruefen(self):
        obj = {"titel": "T", "hook": "Wusstest du?", "kapitel": [{"titel": "A", "szenen": [{"text": "Satz.", "bild": "x"}]},
                                                               {"titel": "leer", "szenen": [{"text": " "}]}],
               "tags": ["a", ""], "zu_pruefen": ["Zahl X"]}
        s = SK.pruefen(obj)
        self.assertEqual(len(s["kapitel"]), 1)                        # leeres Kapitel faellt weg
        self.assertEqual(s["kapitel"][0]["szenen"][0]["text"], "Wusstest du?")   # Hook vorne
        self.assertEqual((s["tags"], s["geprueft"]), (["a"], False))
        for kaputt in (None, {"titel": "T"}, {"kapitel": [{"titel": "A", "szenen": [{"text": "x"}]}]}):
            with self.assertRaises(SK.SkriptFehler):
                SK.pruefen(kaputt)

    def test_mit_ki_wiederholt_einmal(self):
        class KI:
            def __init__(self):
                self.n = 0

            def antwort(self, prompt):
                self.n += 1
                return "kein json" if self.n == 1 else json.dumps(
                    {"titel": "T", "kapitel": [{"titel": "A", "szenen": [{"text": "Ein Satz.", "bild": "b"}]}]})
        ki = KI()
        self.assertEqual(SK.mit_ki(ki, "Auftrag", 1)["titel"], "T")
        self.assertEqual(ki.n, 2)
        with self.assertRaises(SK.SkriptFehler):
            SK.mit_ki(None, "Auftrag", 1)
        self.assertIn("700 Wörter", SK.prompt("x", 5))

    def test_json_aus_text(self):
        self.assertEqual(SK.json_aus_text('Hier: {"a": 1} danke'), {"a": 1})
        self.assertIsNone(SK.json_aus_text("nichts"))


class Storyboard(unittest.TestCase):
    def test_szenen_teilen_und_zeiten(self):
        lang = " ".join(["Das ist ein ziemlich langer Satz mit vielen Wörtern drin."] * 8)
        s = SK.aus_text("T", lang)
        sz = SB.erstellen(s)
        self.assertGreater(len(sz), 1)
        self.assertTrue(all(len(x["text"].split()) <= SK.MAX_SZENE_WOERTER + 12 for x in sz))
        with self.assertRaises(ValueError):
            SB.zeiten_setzen(sz)
        for x in sz:
            x["audio"] = {"dauer": 2.0}
        gesamt = SB.zeiten_setzen(sz)
        self.assertAlmostEqual(gesamt, len(sz) * (2.0 + SB.PAUSE_S))
        self.assertEqual(sz[1]["start"], 2.0 + SB.PAUSE_S)

    def test_kapitel_untertitel(self):
        sz = SB.erstellen(SK.aus_text("T", TEXT))
        for x in sz:
            x["audio"] = {"dauer": 3.0}
        SB.zeiten_setzen(sz)
        marken = SB.kapitelmarken(sz)
        self.assertEqual(marken[0], (0.0, "Einleitung"))
        self.assertEqual(len(marken), 3)
        b = SB.untertitel(sz, 20)
        self.assertTrue(all(t.count("\n") <= 1 for _, _, t in b))
        self.assertTrue(all(a < e for a, e, _ in b))
        srt = SB.srt(b)
        self.assertTrue(srt.startswith("1\n00:00:00,000 --> "))
        self.assertTrue(SB.vtt(b).startswith("WEBVTT"))
        self.assertEqual(SB.zeit_text(75), "1:15")
        self.assertEqual(SB.zeit_text(3700), "1:01:40")


class Lizenzen(unittest.TestCase):
    def test_openverse_nur_freie_lizenzen(self):
        d = {"results": [{"license": "by-sa", "url": "u1", "width": 2000}, {"license": "by-nc", "url": "u2", "width": 2000},
                         {"license": "cc0", "url": "u3", "width": 2000, "creator": "A"},
                         {"license": "by", "url": "u4", "width": 800},
                         {"license": "by", "url": "u5", "width": 1600, "creator": "<b>B</b>", "license_version": "4.0"}]}
        k = AS.openverse_parsen(d)
        self.assertEqual([x["url"] for x in k], ["u3", "u5"])
        self.assertTrue(k[1]["namensnennung_noetig"])
        self.assertEqual(k[1]["urheber"], "B")

    def test_wikimedia_lizenzen(self):
        self.assertEqual(AS._lizenz_wikimedia("CC0"), "cc0")
        self.assertEqual(AS._lizenz_wikimedia("Public domain"), "pdm")
        self.assertEqual(AS._lizenz_wikimedia("CC BY 4.0"), "by")
        for x in ("CC BY-SA 4.0", "CC BY-NC 2.0", "CC BY-ND 3.0", "GFDL", ""):
            self.assertIsNone(AS._lizenz_wikimedia(x), x)

    def test_suche_faellt_zurueck(self):
        class R:
            def __init__(self, code, daten=None):
                self.status_code, self._d = code, daten

            def json(self):
                return self._d
        aufrufe = []

        def get(url, **kw):
            aufrufe.append(url)
            if "openverse" in url:
                return R(504)
            return R(200, {"query": {"pages": {"1": {"title": "File:x.jpg", "imageinfo": [{
                "thumburl": "https://upload.wikimedia.org/x.jpg", "width": 3000, "descriptionurl": "d",
                "extmetadata": {"LicenseShortName": {"value": "CC BY 4.0"}, "Artist": {"value": "Ann"}}}]}}}})
        k, fehler = AS.suchen("office", get)
        self.assertEqual((k["anbieter"], k["lizenz"]), ("Wikimedia Commons", "by"))
        self.assertIn("Openverse: HTTP 504", fehler)
        k2, fehler2 = AS.suchen("office", get, gesehen={"https://upload.wikimedia.org/x.jpg"})
        self.assertIsNone(k2)                                              # kein Bild doppelt
        self.assertIn("ohne Treffer", AS.namensnennung({"lizenz": "by", "titel": "ohne Treffer", "urheber": "A",
                                                        "lizenz_text": "CC BY", "quelle": "q"}))
        self.assertIsNone(AS.namensnennung({"lizenz": "eigen"}))

    @unittest.skipUnless(PILLOW, "Pillow nicht installiert")
    def test_eigene_folie(self):
        with tempfile.TemporaryDirectory() as d:
            a = AS.folie("Text", "Ein sehr langer Kapiteltitel, der umbrochen werden muss, weil er lang ist", os.path.join(d, "f.jpg"))
            self.assertTrue(os.path.exists(a["pfad"]))
            self.assertEqual((a["lizenz"], a["namensnennung_noetig"]), ("eigen", False))


def _still(pfad, sekunden):
    with wave.open(pfad, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * int(22050 * sekunden))
    return sekunden


@unittest.skipUnless(FFMPEG and PILLOW, "FFmpeg/Pillow nicht installiert")
class KompletterLauf(unittest.TestCase):
    def test_lauf_ohne_netz_mit_folien(self):
        alt = PL.ST.stimme_laden, PL.ST.sprechen
        PL.ST.stimme_laden = lambda *a, **k: "modell.onnx"
        PL.ST.sprechen = lambda text, modell, ziel, tempo=1.0: (os.makedirs(os.path.dirname(ziel), exist_ok=True),
                                                                 _still(ziel, 1.0 + len(text) / 200))[1]
        try:
            with tempfile.TemporaryDirectory() as d:
                p = PL.neues_projekt("Test", dauer_min=0.5, skript=SK.aus_text("Testvideo: Ablauf", TEXT),
                                     qualitaet="entwurf")
                p = PL.ausfuehren(p, {"ordner": d, "get": None, "ki": None})
                self.assertEqual(p["status"], "freigabe_noetig", p["protokoll"][-3:])
                self.assertTrue(all(p["schritte"][s]["status"] == "ok" for s in PL.SCHRITTE))
                info = p["dateien"]["video_info"]
                self.assertEqual((info["breite"], info["hoehe"], info["video"], info["audio"]), (1920, 1080, "h264", "aac"))
                self.assertEqual(len(p["dateien"]["thumbnails"]), 3)
                self.assertTrue(os.path.exists(p["dateien"]["srt"]))
                with open(p["dateien"]["beschreibung"], encoding="utf-8") as f:
                    b = f.read()
                self.assertIn("0:00 Einleitung", b)
                self.assertIn("KI-generiert", b)
                bericht = {n: e for n, e, _ in p["bericht"]["punkte"]}
                self.assertEqual(bericht["Lizenzen"], "ok")
                self.assertEqual(bericht["Ton synchron / Dauer"], "ok")
                # Szene aendern -> abhaengige Schritte wieder offen, Skript bleibt
                PL.zuruecksetzen(p, "stimme")
                self.assertEqual(p["schritte"]["skript"]["status"], "ok")
                self.assertEqual(p["schritte"]["schnitt"]["status"], "offen")
        finally:
            PL.ST.stimme_laden, PL.ST.sprechen = alt

    def test_fehler_stoppt_und_bleibt_erhalten(self):
        with tempfile.TemporaryDirectory() as d:
            p = PL.neues_projekt("Auftrag ohne Skript", dauer_min=1)
            p = PL.ausfuehren(p, {"ordner": d, "get": None, "ki": None})
            self.assertEqual(p["status"], "fehler")
            self.assertEqual(p["schritte"]["skript"]["status"], "fehler")
            self.assertIn("GEMINI_API_KEY", p["schritte"]["skript"]["meldung"])
            self.assertEqual(p["schritte"]["storyboard"]["status"], "offen")


class Qualitaet(unittest.TestCase):
    def test_ungeklaerte_lizenz_blockiert(self):
        p = PL.neues_projekt("x", skript=SK.aus_text("T", "Ein Satz."))
        p["szenen"] = SB.erstellen(p["skript"])
        p["szenen"][0].update(asset={"pfad": "a.jpg", "lizenz": "unbekannt"}, audio={"dauer": 2.0, "pfad": "a.wav"})
        SB.zeiten_setzen(p["szenen"])
        p["dateien"] = {"video_info": {"video": "h264", "audio": "aac", "breite": 1920, "hoehe": 1080, "dauer": 2.35},
                        "srt": "x.srt"}
        b = PL.qualitaetsbericht(p)
        self.assertTrue(b["blockiert"])
        self.assertEqual({n: e for n, e, _ in b["punkte"]}["Lizenzen"], "fehler")

    def test_neues_projekt_pruefung(self):
        for kw in ({"auftrag": ""}, {"auftrag": "x", "fmt": "4:3"}, {"auftrag": "x", "dauer_min": 99}):
            with self.assertRaises(ValueError):
                PL.neues_projekt(**kw)


if __name__ == "__main__":
    unittest.main()
