"""Faceless YouTube - Radar-Agent (GitHub Actions, taeglich): laedt die RSS-Feeds der beobachteten Kanaele und
speichert je Video eine Momentaufnahme (Aufrufe, Likes) in state/youtube_radar.json - daraus entsteht gemessenes
Wachstum. Die beobachteten Kanaele stehen in state/youtube.json unter "radar" (Admin-Bereich, in der App gepflegt).
Kein API-Schluessel noetig, kein Scraping."""
import datetime
import logging
import os
import sys

import requests

import config
import github_store
import youtube_radar as YR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("youtube-radar")
REPO = os.environ.get("STATE_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GH_STATE_TOKEN", "")
PFAD_LISTE = "state/youtube.json"
PFAD_RADAR = "state/youtube_radar.json"


def lauf(kanaele, radar, jetzt, get=requests.get):
    """Alle Kanaele abrufen -> (neues Radar, Anzahl ok, Fehlertexte)."""
    ok, fehler = 0, []
    for k in kanaele:
        cid = k.get("id")
        try:
            radar = YR.einfuegen(radar, YR.abrufen(cid, get), jetzt)
            ok += 1
        except YR.RadarFehler as ex:
            radar = YR.fehler_merken(radar, cid, str(ex), jetzt)
            fehler.append(f"{k.get('name') or cid}: {ex}")
    return radar, ok, fehler


def main():
    if not (REPO and TOKEN):
        log.error("GITHUB_REPOSITORY / GH_STATE_TOKEN fehlen.")
        return 1
    try:
        liste, _ = github_store.lese_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_LISTE, TOKEN, default={})
    except github_store.LeseFehler as ex:
        log.error(f"{PFAD_LISTE} nicht lesbar: {ex}")
        return 1
    kanaele = [k for k in (liste or {}).get("radar") or [] if isinstance(k, dict) and k.get("id")]
    if not kanaele:
        log.info("Keine Kanäle im Radar – nichts zu tun.")
        return 0
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    ergebnis = {}

    def aendern(alt):
        neu, ok, fehler = lauf(kanaele, alt or {}, jetzt)
        ergebnis.update(ok=ok, fehler=fehler)
        return neu
    gespeichert, _ = github_store.aktualisiere_json(REPO, config.GITHUB_STATE_BRANCH, PFAD_RADAR, TOKEN, aendern,
                                                    default={}, message="youtube radar [skip ci]")
    log.info(f"Radar: {ergebnis.get('ok', 0)} von {len(kanaele)} Kanälen abgerufen"
             + (" (gespeichert)" if gespeichert else " (NICHT gespeichert)"))
    for f in ergebnis.get("fehler") or []:
        log.warning(f)
    return 0 if gespeichert else 1


if __name__ == "__main__":
    sys.exit(main())
