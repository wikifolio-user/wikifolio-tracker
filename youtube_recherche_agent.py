"""Faceless YouTube - Recherche-Agent (GitHub Actions, taeglich): fuehrt die in der App gespeicherten Beobachtungen
(Faceless YouTube -> Recherche -> Beobachtung) ueber die YouTube Data API aus und schreibt Nischen-Verlauf und neue
Ausreisser nach state/youtube_recherche.json. Das Kontingent teilen sich App und Agent (state/youtube_api.json):
gebucht wird jede Einheit, die eigene Tagesgrenze aus den Einstellungen gilt auch hier.
Braucht das Secret YOUTUBE_API_KEY im Code-Repository. Veroeffentlicht nichts und sendet keine Nachrichten."""
import datetime
import logging
import os
import sys

import requests

import config
import github_store
import youtube_api as YA
import youtube_beobachtung as YB

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("youtube-recherche")
REPO = os.environ.get("STATE_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GH_STATE_TOKEN", "")
KEY = os.environ.get("YOUTUBE_API_KEY", "")
PFAD_LISTE = "state/youtube.json"
PFAD_API = "state/youtube_api.json"


def main(get=requests.get):
    if not (REPO and TOKEN):
        log.error("STATE_REPO / GH_STATE_TOKEN fehlen.")
        return 1
    if not KEY:
        log.warning("YOUTUBE_API_KEY ist als GitHub-Secret nicht eingerichtet – nichts zu tun.")
        return 0
    try:
        liste, _ = github_store.lese_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_LISTE, TOKEN, default={})
        api, _ = github_store.lese_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_API, TOKEN, default={})
        stand, _ = github_store.lese_json(REPO, config.GITHUB_STATE_BRANCH, YB.PFAD_RECHERCHE, TOKEN, default={})
    except github_store.LeseFehler as ex:
        log.error(f"State nicht lesbar: {ex}")
        return 1
    liste = liste if isinstance(liste, dict) else {}
    beob = [b for b in liste.get("beobachtungen") or [] if isinstance(b, dict) and b.get("id") and b.get("begriff")]
    if not any(b.get("aktiv", True) for b in beob):
        log.info("Keine aktiven Beobachtungen – nichts zu tun.")
        return 0
    try:
        grenze = int(((liste.get("einstellungen") or {}).get("api_grenze")) or YA.STANDARD_GRENZE)
    except (TypeError, ValueError):
        grenze = YA.STANDARD_GRENZE
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    neu, einheiten, zeilen = YB.lauf(beob, YA.verbindung(KEY, get), api if isinstance(api, dict) else {}, grenze,
                                     jetzt, stand if isinstance(stand, dict) else {})
    for z in zeilen:
        log.info(z)
    ok_api = True
    if einheiten:
        ok_api, _ = github_store.aktualisiere_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_API, TOKEN,
                                                   lambda alt: YA.buchen(alt if isinstance(alt, dict) else {},
                                                                         einheiten, jetzt),
                                                   default={}, message="youtube recherche: kontingent [skip ci]")
    ok, _ = github_store.aktualisiere_json(REPO, config.GITHUB_STATE_BRANCH, YB.PFAD_RECHERCHE, TOKEN,
                                           lambda _alt: neu, default={}, message="youtube recherche [skip ci]")
    log.info(f"{einheiten} Einheiten verbraucht · " + ("gespeichert" if ok and ok_api else "NICHT gespeichert"))
    return 0 if ok and ok_api else 1


if __name__ == "__main__":
    sys.exit(main())
