"""Faceless YouTube - Upload eines freigegebenen Videos als PRIVATER Entwurf auf den eigenen Kanal.
Reine Logik (ohne Streamlit); HTTP-Funktionen werden von aussen uebergeben.

- Anmeldung: OAuth 2.0 mit Refresh-Token (Scope youtube.upload). Client-ID, Client-Secret und Refresh-Token stehen
  nur in den Streamlit-Secrets; sie tauchen weder in Fehlertexten noch in Logs oder im Projekt auf.
- Sichtbarkeit ist IMMER "private" - fest im Code, nicht einstellbar. Veroeffentlichen geschieht von Hand in
  YouTube Studio. Hochgeladen wird nur ein freigegebenes Projekt, nur nach Bestaetigung.
- Kontingent: videos.insert kostet 1600 Einheiten, thumbnails.set 50 (gemeinsamer Zaehler mit der Recherche).
- Kennzeichnung: status.containsSyntheticMedia (veraenderte oder synthetische Inhalte) wird mitgesendet."""
import json
import os
import re

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
KOSTEN_UPLOAD = 1600
KOSTEN_THUMBNAIL = 50
SICHTBARKEIT = "private"
STUECK = 8 * 1024 * 1024
KATEGORIEN = {"27": "Bildung", "28": "Wissenschaft & Technik", "22": "Menschen & Blogs", "24": "Unterhaltung",
              "26": "Praktische Tipps & Styling", "25": "Nachrichten & Politik", "19": "Reisen & Events",
              "20": "Gaming", "17": "Sport", "10": "Musik"}
SECRETS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


class UploadFehler(Exception):
    pass


def _sauber(text, geheim=()):
    t = str(text)
    for g in geheim:
        if g:
            t = t.replace(g, "***")
    t = re.sub(r"ya29\.[0-9A-Za-z_\-]+", "***", t)
    return re.sub(r"1//[0-9A-Za-z_\-]{20,}", "***", t)


def zugang(client_id, client_secret, refresh_token, post):
    """Access-Token holen. -> str. Wirft UploadFehler mit verstaendlichem Text (ohne Geheimnisse)."""
    geheim = (client_secret, refresh_token)
    try:
        r = post(TOKEN_URL, data={"client_id": client_id, "client_secret": client_secret,
                                  "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=20)
    except Exception as ex:
        raise UploadFehler(f"Google-Anmeldung nicht erreichbar ({type(ex).__name__}).") from None
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code == 200 and d.get("access_token"):
        if d.get("scope") and SCOPE not in str(d["scope"]).split() and \
                "https://www.googleapis.com/auth/youtube" not in str(d["scope"]).split():
            raise UploadFehler("Der Refresh-Token hat keine Upload-Berechtigung (Scope youtube.upload fehlt).")
        return d["access_token"]
    fehler = str(d.get("error") or "")
    if fehler == "invalid_grant":
        raise UploadFehler("Der Refresh-Token ist abgelaufen oder widerrufen. Bitte neu erzeugen (Anleitung in der "
                           "App). Hinweis: Im Modus „Testing“ des Google-Projekts laufen Tokens nach 7 Tagen ab.")
    if fehler in ("invalid_client", "unauthorized_client"):
        raise UploadFehler("Client-ID oder Client-Secret passen nicht (Google meldet „" + fehler + "“).")
    raise UploadFehler(_sauber(f"Google-Anmeldung fehlgeschlagen (HTTP {r.status_code} {fehler})", geheim))


def _text(x, n):
    return re.sub(r"[<>]", "", str(x or "")).strip()[:n]


def metadaten(titel, beschreibung, tags=(), kategorie="27", sprache="de", fuer_kinder=False, synthetisch=True):
    """Snippet und Status fuer videos.insert. Sichtbarkeit ist immer privat."""
    t = _text(titel, 100)
    if not t:
        raise UploadFehler("Bitte einen Titel angeben.")
    tag_liste, laenge = [], 0
    for x in tags or ():
        x = _text(x, 60).replace(",", " ")
        if x and laenge + len(x) + 2 <= 480:
            tag_liste.append(x)
            laenge += len(x) + 2
    return {"snippet": {"title": t, "description": _text(beschreibung, 5000), "tags": tag_liste,
                        "categoryId": kategorie if kategorie in KATEGORIEN else "27",
                        "defaultLanguage": sprache, "defaultAudioLanguage": sprache},
            "status": {"privacyStatus": SICHTBARKEIT, "selfDeclaredMadeForKids": bool(fuer_kinder),
                       "containsSyntheticMedia": bool(synthetisch), "embeddable": True}}


def _api_fehler(r, was):
    try:
        e = (r.json() or {}).get("error") or {}
    except ValueError:
        e = {}
    gruende = {str(x.get("reason") or "") for x in e.get("errors") or [] if isinstance(x, dict)}
    if gruende & {"quotaExceeded", "uploadLimitExceeded"}:
        return f"{was}: Tageskontingent bzw. Upload-Limit erreicht – morgen erneut versuchen."
    if gruende & {"youtubeSignupRequired"}:
        return f"{was}: Das Google-Konto hat noch keinen YouTube-Kanal."
    if gruende & {"forbidden", "insufficientPermissions"} or r.status_code == 403:
        return f"{was}: keine Berechtigung (Kanal/Scope prüfen)."
    return f"{was}: HTTP {r.status_code} {_sauber(str(e.get('message') or ''))[:200]}"


def hochladen(pfad, meta, token, post, put, fortschritt=None):
    """Resumable Upload. -> video_id. fortschritt(anteil 0..1) optional."""
    if meta["status"]["privacyStatus"] != SICHTBARKEIT:
        raise UploadFehler("Es wird nur privat hochgeladen.")
    groesse = os.path.getsize(pfad)
    kopf = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(groesse)}
    try:
        r = post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                 data=json.dumps(meta).encode("utf-8"), headers=kopf, timeout=30)
    except Exception as ex:
        raise UploadFehler(f"YouTube nicht erreichbar ({type(ex).__name__}).") from None
    if r.status_code != 200 or not r.headers.get("Location"):
        raise UploadFehler(_api_fehler(r, "Upload starten"))
    ziel = r.headers["Location"]
    start = 0
    with open(pfad, "rb") as f:
        while start < groesse:
            f.seek(start)
            teil = f.read(STUECK)
            ende = start + len(teil) - 1
            try:
                r = put(ziel, data=teil, timeout=300, headers={"Authorization": f"Bearer {token}",
                                                               "Content-Length": str(len(teil)),
                                                               "Content-Range": f"bytes {start}-{ende}/{groesse}"})
            except Exception as ex:
                raise UploadFehler(f"Upload unterbrochen ({type(ex).__name__}) – bitte erneut versuchen.") from None
            if r.status_code in (200, 201):
                if fortschritt:
                    fortschritt(1.0)
                try:
                    return r.json()["id"]
                except (ValueError, KeyError):
                    raise UploadFehler("YouTube hat keine Video-ID zurückgegeben.") from None
            if r.status_code != 308:
                raise UploadFehler(_api_fehler(r, "Upload"))
            bereich = r.headers.get("Range") or ""
            m = re.search(r"bytes=0-(\d+)", bereich)
            start = int(m.group(1)) + 1 if m else start + len(teil)
            if fortschritt:
                fortschritt(min(start / groesse, 0.99))
    raise UploadFehler("Upload nicht abgeschlossen.")


def thumbnail_setzen(video_id, bild, token, post):
    """Eigenes Thumbnail (setzt einen verifizierten Kanal voraus). -> (ok, text)"""
    try:
        r = post(THUMB_URL, params={"videoId": video_id}, data=bild, timeout=60,
                 headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"})
    except Exception as ex:
        return False, f"Thumbnail nicht gesetzt ({type(ex).__name__})."
    if r.status_code == 200:
        return True, "Thumbnail gesetzt."
    return False, _api_fehler(r, "Thumbnail") + " Eigene Thumbnails brauchen einen verifizierten Kanal."


def titel_und_beschreibung(text, fallback=""):
    """beschreibung.txt der Video Factory: erste Zeile = Titel, Rest = Beschreibung."""
    zeilen = str(text or "").strip().split("\n")
    titel = zeilen[0].strip() if zeilen and zeilen[0].strip() else fallback
    return titel[:100], "\n".join(zeilen[1:]).strip()


def studio_link(video_id):
    return f"https://studio.youtube.com/video/{video_id}/edit"
