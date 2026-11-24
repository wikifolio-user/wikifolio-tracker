"""Faceless YouTube - Render-Agent (GitHub Actions): fuehrt die Video Factory fuer Projekte in der Warteschlange
aus und legt die Ergebnisse (MP4, Thumbnails, Untertitel, Beschreibung, Lizenzen) als Release-Dateien im privaten
State-Repo ab. Projektdaten: state/youtube/projekte/<id>.json, Index in state/youtube.json unter "projekte".
Gestartet von der App (workflow_dispatch) oder als Ersatzlauf nach Zeitplan. Veroeffentlicht nie etwas."""
import datetime
import logging
import os
import sys
import tempfile

import requests

import config
import github_release as GR
import github_store
from video_factory import pipeline as PL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("youtube-render")
REPO = os.environ.get("STATE_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GH_STATE_TOKEN", "")
PFAD_INDEX = "state/youtube.json"
ERGEBNIS = ["video.mp4", "thumbnail_1.jpg", "thumbnail_2.jpg", "thumbnail_3.jpg", "untertitel.srt", "untertitel.vtt",
            "beschreibung.txt", "lizenzen.json"]
TYPEN = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".srt": "text/plain", ".vtt": "text/vtt", ".txt": "text/plain",
         ".json": "application/json"}


def projekt_pfad(pid):
    return f"state/youtube/projekte/{pid}.json"


def index_status(index, pid, status, titel=None):
    """Status eines Projekts im Index setzen -> neuer Index"""
    index = dict(index or {})
    liste = [dict(x) for x in index.get("projekte") or []]
    for x in liste:
        if x.get("id") == pid:
            x["status"] = status
            x["geaendert"] = PL.jetzt()
            if titel:
                x["titel"] = titel
    index["projekte"] = liste
    return index


def offene(index, nur=None):
    liste = (index or {}).get("projekte") or []
    if nur:
        return [x["id"] for x in liste if x.get("id") == nur]
    return [x["id"] for x in liste if x.get("status") == "warteschlange"]


def ergebnis_hochladen(p, ordner, release_holen=None, hochladen=None):
    """Ergebnisdateien als Release-Assets ablegen -> {"tag", "assets": {name: {...}}}"""
    tag = f"video-{p['id']}"
    release_holen = release_holen or (lambda t, n: GR.release_holen(REPO, t, TOKEN, n))
    hochladen = hochladen or (lambda rel, pfad, name, typ: GR.hochladen(REPO, rel, pfad, TOKEN, name, typ))
    rel = release_holen(tag, f"Video: {(p.get('skript') or {}).get('titel') or p['id']}")
    assets = {}
    for name in ERGEBNIS:
        pfad = os.path.join(ordner, name)
        if os.path.exists(pfad):
            assets[name] = hochladen(rel, pfad, name, TYPEN[os.path.splitext(name)[1]])
    return {"tag": tag, "assets": assets, "zeit": PL.jetzt()}


def projekt_rendern(pid, ki, get=requests.get):
    """Ein Projekt rendern. -> Status"""
    p, _ = github_store.lese_json(REPO, config.GITHUB_STATE_BRANCH, projekt_pfad(pid), TOKEN, default=None)
    if not p:
        log.warning(f"Projekt {pid} nicht gefunden.")
        return "fehler", None

    def speichern(x):
        github_store.aktualisiere_json(REPO, config.GITHUB_STATE_BRANCH, projekt_pfad(pid), TOKEN, lambda _alt: x,
                                       default={}, message=f"youtube projekt {pid} [skip ci]")
    with tempfile.TemporaryDirectory() as ordner:
        p = PL.ausfuehren(p, {"ordner": ordner, "get": get, "ki": ki,
                              "stimmen_ordner": os.environ.get("PIPER_STIMMEN", "stimmen"),
                              "release_laden": lambda aid: GR.laden(REPO, aid, TOKEN)}, speichern=speichern)
        if p["status"] in ("freigabe_noetig", "blockiert"):
            try:
                p["dateien"]["release"] = ergebnis_hochladen(p, ordner)
                PL._log(p, f"Ergebnis abgelegt (Release {p['dateien']['release']['tag']}).")
            except Exception as ex:
                p["status"] = "fehler"
                PL._log(p, f"Ablage fehlgeschlagen: {github_store.sauber(ex)}", "fehler")
        speichern(p)
    return p["status"], (p.get("skript") or {}).get("titel")


def main():
    if not (REPO and TOKEN):
        log.error("GITHUB_REPOSITORY / GH_STATE_TOKEN fehlen.")
        return 1
    try:
        index, _ = github_store.lese_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_INDEX, TOKEN, default={})
    except github_store.LeseFehler as ex:
        log.error(f"{PFAD_INDEX} nicht lesbar: {ex}")
        return 1
    ids = offene(index, os.environ.get("PROJEKT_ID") or None)
    if not ids:
        log.info("Keine Projekte in der Warteschlange.")
        return 0
    ki = None
    try:
        import ki_anbieter
        ki = ki_anbieter.verfuegbar()
    except Exception as ex:
        log.warning(f"KI nicht verfügbar: {type(ex).__name__}")
    fehler = 0
    for pid in ids:
        github_store.aktualisiere_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_INDEX, TOKEN,
                                       lambda i: index_status(i, pid, "rendert"), default={},
                                       message="youtube render start [skip ci]")
        t0 = datetime.datetime.now()
        try:
            status, titel = projekt_rendern(pid, ki)
        except Exception as ex:
            log.exception("Render-Fehler")
            status, titel = "fehler", None
            log.error(github_store.sauber(ex))
        fehler += status == "fehler"
        github_store.aktualisiere_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_INDEX, TOKEN,
                                       lambda i, s=status, t=titel: index_status(i, pid, s, t), default={},
                                       message="youtube render ende [skip ci]")
        log.info(f"Projekt {pid}: {status} nach {(datetime.datetime.now() - t0).seconds} s")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
