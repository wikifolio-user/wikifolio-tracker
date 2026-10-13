"""
Persistenter State ueber die GitHub Contents API - funktioniert sowohl aus
Streamlit Cloud (fluechtiges Dateisystem!) als auch aus GitHub Actions,
ohne Branch-Checkout/-Push-Choreografie. Jede Datei liegt auf einem eigenen
Branch (config.GITHUB_STATE_BRANCH), getrennt vom main-Branch, damit
State-Updates KEINEN Streamlit-Cloud-Redeploy ausloesen.

Benoetigt:
- repo:  "owner/reponame" (in Streamlit: st.secrets["GITHUB_REPO"],
         in Actions: die eingebaute Variable ${{ github.repository }})
- token: Personal Access Token (Streamlit: Secret GITHUB_TOKEN) bzw. in
         Actions secrets.GITHUB_TOKEN ("Read and write permissions").

Datensicherheit (Audit DATA-01/DATA-02):
- get_json() bleibt fuer reine Anzeige-Lesezugriffe: bei JEDEM Fehler kommt
  der Standardwert zurueck. NIEMALS dessen Ergebnis veraendert zurueckschreiben -
  bei Rate-Limit/Timeout wuerde sonst die ganze Datei durch den Standardwert
  ersetzt.
- Fuer Lesen-Aendern-Schreiben immer aktualisiere_json() verwenden: liest streng
  (Fehler != "Datei fehlt"), schreibt mit dem gelesenen sha (Versionspruefung)
  und wiederholt bei einem Konflikt mit den FRISCHEN Daten.
- put_json() ohne erwarteten sha ueberschreibt (fuer Dateien, die komplett
  neu berechnet werden, z.B. Agenten-Ergebnisse); mit sha=... nur, wenn die
  Datei seit dem Lesen unveraendert ist.
"""
import base64
import copy
import json
import logging
import re
import threading
import time

import requests

GITHUB_API = "https://api.github.com"
_FEHLT = object()          # Marker: kein erwarteter sha angegeben (= ueberschreiben)
_lokal = threading.local()


def _fehlerhaft():
    """Pfade, deren letzter get_json()-Versuch IN DIESEM THREAD fehlschlug. Fuer sie
    verweigert put_json() ohne sha das Schreiben, bis wieder erfolgreich gelesen
    wurde - so kann ein nach einem Lesefehler gebildeter Leerwert nie die echte
    Datei ersetzen (Audit DATA-01). Thread-lokal, damit parallele Abrufe sich
    nicht gegenseitig sperren."""
    if not hasattr(_lokal, "pfade"):
        _lokal.pfade = set()
    return _lokal.pfade


class LeseFehler(Exception):
    """Datei konnte nicht gelesen werden (Netz, Rate-Limit, 5xx, kaputtes JSON) -
    ausdruecklich NICHT "Datei existiert nicht" (das ist kein Fehler)."""


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def sauber(text):
    """Fehlertexte ohne Tokens/Webhook-Pfade fuer Logs (Audit SEC-08)."""
    t = str(text)
    t = re.sub(r"(api/webhooks/)[^\s'\"]+", r"\1***", t)
    t = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1***", t)
    t = re.sub(r"gh[pousr]_[A-Za-z0-9]{10,}", "***", t)
    t = re.sub(r"github_pat_[A-Za-z0-9_]{10,}", "***", t)
    return t


def lese_json(repo, branch, path, token, default=None):
    """Streng: (daten, sha). Datei fehlt (404) -> (default, None).
    Jeder andere Fehler -> LeseFehler (der Aufrufer darf dann NICHT schreiben)."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    try:
        r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=10)
    except Exception as e:
        raise LeseFehler(f"{path}: {type(e).__name__}") from None
    if r.status_code == 404:
        return default, None
    if r.status_code != 200:
        raise LeseFehler(f"{path}: HTTP {r.status_code}")
    try:
        data = r.json()
        roh = data.get("content")
        if not roh and data.get("download_url"):
            # Dateien > 1 MB liefert die Contents-API ohne Inhalt -> Rohdatei laden
            r2 = requests.get(data["download_url"], headers=_headers(token), timeout=20)
            if r2.status_code != 200:
                raise LeseFehler(f"{path}: HTTP {r2.status_code} (Rohdatei)")
            return json.loads(r2.text), data["sha"]
        content = base64.b64decode(roh).decode("utf-8")
        return json.loads(content), data["sha"]
    except LeseFehler:
        raise
    except Exception as e:
        raise LeseFehler(f"{path}: {type(e).__name__}") from None


get_json_sicher = lese_json        # anderer Name, gleiche Funktion


def get_json(repo, branch, path, token, default=None):
    """Zum ANZEIGEN: (daten, sha); bei jedem Fehler (default, None). Nach einem
    Fehler sperrt put_json() (ohne sha) diesen Pfad, bis wieder erfolgreich
    gelesen wurde. Fuer Lesen-Aendern-Schreiben aktualisiere_json() verwenden."""
    try:
        daten, sha = lese_json(repo, branch, path, token, default)
    except LeseFehler as e:
        logging.error(f"github_store.get_json Fehler ({e})")
        _fehlerhaft().add(path)
        return default, None
    _fehlerhaft().discard(path)
    return daten, sha


def _put(url, token, payload):
    try:
        return requests.put(url, headers=_headers(token), json=payload, timeout=15)
    except Exception as e:
        logging.error(f"github_store PUT Fehler: {type(e).__name__}")
        return None


def put_json(repo, branch, path, obj, token, message="update state", max_retries=3, sha=_FEHLT):
    """Schreibt eine JSON-Datei. -> True/False.

    - Ohne sha-Argument: ueberschreibt den aktuellen Stand (sha wird direkt vorher
      gelesen). Nur fuer Dateien, die komplett neu berechnet werden.
    - Mit sha=<gelesener sha> (oder sha=None fuer "Datei existierte beim Lesen nicht"):
      schreibt nur, wenn die Datei seit dem Lesen unveraendert ist; bei Konflikt
      False (KEIN Ueberschreiben) - dann neu lesen und erneut aendern."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    content_b64 = base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    pruefen = sha is not _FEHLT
    if not pruefen and path in _fehlerhaft():
        logging.error(f"github_store.put_json: {path} wurde zuletzt nicht gelesen (Lesefehler) - "
                      "Schreiben verweigert, damit kein Leerwert die echte Datei ersetzt")
        return False

    for versuch in range(max_retries):
        if pruefen:
            akt_sha = sha
        else:
            try:
                _, akt_sha = lese_json(repo, branch, path, token)
            except LeseFehler as e:
                logging.warning(f"github_store.put_json: sha nicht lesbar ({e}), Versuch {versuch + 1}")
                time.sleep(1 + versuch)
                continue
        payload = {"message": message, "content": content_b64, "branch": branch}
        if akt_sha:
            payload["sha"] = akt_sha
        r = _put(url, token, payload)
        if r is not None and r.status_code in (200, 201):
            return True
        if r is not None and r.status_code in (409, 422):
            if pruefen:
                logging.warning(f"github_store.put_json Konflikt ({path}) - Datei wurde inzwischen geaendert")
                return False
            continue                                   # sha neu lesen und erneut
        status = r.status_code if r is not None else "keine Antwort"
        logging.warning(f"github_store.put_json ({path}) HTTP {status}, Versuch {versuch + 1}/{max_retries}")
        time.sleep(1 + versuch)
    logging.error(f"github_store.put_json Fehler ({path}) nach {max_retries} Versuchen")
    return False


def aktualisiere_json(repo, branch, path, token, aendern, default=None, message="update state", max_retries=4):
    """Sicheres Lesen-Aendern-Schreiben. aendern(daten) bekommt eine Kopie und
    gibt den neuen Inhalt zurueck (oder None = nichts zu schreiben).
    -> (ok, inhalt): ok=False bei Lese-/Schreibfehler - dann wurde NICHTS
    geschrieben. Bei einem Konflikt wird mit den frischen Daten wiederholt."""
    for versuch in range(max_retries):
        try:
            daten, sha = lese_json(repo, branch, path, token, default)
        except LeseFehler as e:
            logging.error(f"github_store.aktualisiere_json: nicht gelesen, nichts geschrieben ({e})")
            return False, None
        neu = aendern(copy.deepcopy(daten))
        if neu is None:
            return True, daten
        if put_json(repo, branch, path, neu, token, message=message, max_retries=2, sha=sha):
            return True, neu
        time.sleep(0.5 * (versuch + 1))
    logging.error(f"github_store.aktualisiere_json ({path}): nach {max_retries} Versuchen aufgegeben")
    return False, None


aendere_json = aktualisiere_json   # anderer Name, gleiche Funktion


def _liste(repo, branch, path, token):
    """Alle Dateien (pfad, sha) unter einem Ordner, rekursiv. Ordner fehlt -> [].
    Lesefehler -> LeseFehler (dann wird nichts geloescht)."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    try:
        r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=10)
    except Exception as e:
        raise LeseFehler(f"{path}: {type(e).__name__}") from None
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        raise LeseFehler(f"{path}: HTTP {r.status_code}")
    eintraege = r.json()
    if isinstance(eintraege, dict):                     # Pfad ist eine Datei
        return [(eintraege["path"], eintraege["sha"])]
    dateien = []
    for e in eintraege:
        if e.get("type") == "dir":
            dateien += _liste(repo, branch, e["path"], token)
        elif e.get("type") == "file":
            dateien.append((e["path"], e["sha"]))
    return dateien


def loesche_ordner(repo, branch, path, token, message="delete", max_retries=3):
    """Loescht alle Dateien unter path (z. B. den Datenordner eines geloeschten Benutzers).
    -> (ok, anzahl_geloescht). Nur Pfade unterhalb von state/benutzer/ sind erlaubt -
    so kann ein Fehler nie gemeinsame Daten treffen. Die Git-Historie enthaelt die
    Dateien weiter, bis squash-state-history.yml die Historie komprimiert."""
    path = str(path or "").strip("/")
    if not path.startswith("state/benutzer/") or ".." in path or path.count("/") < 2:
        logging.error(f"github_store.loesche_ordner: Pfad nicht erlaubt ({path})")
        return False, 0
    try:
        dateien = _liste(repo, branch, path, token)
    except LeseFehler as e:
        logging.error(f"github_store.loesche_ordner: nicht lesbar, nichts geloescht ({e})")
        return False, 0
    geloescht, fehler = 0, 0
    for datei, sha in dateien:
        url = f"{GITHUB_API}/repos/{repo}/contents/{datei}"
        for versuch in range(max_retries):
            try:
                r = requests.delete(url, headers=_headers(token), timeout=15,
                                    json={"message": f"{message} [skip ci]", "sha": sha, "branch": branch})
            except Exception as e:
                logging.warning(f"github_store.loesche_ordner: {datei} {type(e).__name__}")
                r = None
            if r is not None and r.status_code in (200, 404):
                geloescht += 1 if r.status_code == 200 else 0
                break
            if r is not None and r.status_code in (409, 422):   # inzwischen geaendert -> sha neu
                try:
                    _, sha = lese_json(repo, branch, datei, token)
                except LeseFehler:
                    pass
                if not sha:
                    break                                       # schon weg
            time.sleep(1 + versuch)
        else:
            fehler += 1
    return fehler == 0, geloescht


def append_csv_line(repo, branch, path, line, token, header=None, message="append data", max_retries=3):
    """Haengt eine Zeile an eine CSV-Datei an (liest, haengt an, schreibt mit dem
    gelesenen sha zurueck). Bei Konflikt komplett neu lesen und wiederholen;
    bei Lesefehler wird nichts geschrieben."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"

    for versuch in range(max_retries):
        sha = None
        existing = ""
        try:
            r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                existing = base64.b64decode(data["content"]).decode("utf-8")
                sha = data["sha"]
            elif r.status_code != 404:
                r.raise_for_status()
        except Exception as e:
            logging.error(f"github_store.append_csv_line Lesefehler ({path}): {type(e).__name__}")
            return False

        if not existing and header:
            existing = header + "\n"

        new_content = (existing.rstrip("\n") + "\n" + line + "\n") if existing else (line + "\n")
        content_b64 = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
        payload = {"message": message, "content": content_b64, "branch": branch}
        if sha:
            payload["sha"] = sha
        r = _put(url, token, payload)
        if r is not None and r.status_code in (200, 201):
            return True
        if r is not None and r.status_code in (409, 422) and versuch < max_retries - 1:
            logging.warning(f"github_store.append_csv_line Konflikt ({path}), Versuch {versuch + 1} - lese neu.")
            continue
        time.sleep(1 + versuch)
    logging.error(f"github_store.append_csv_line Schreibfehler ({path}) nach {max_retries} Versuchen")
    return False
