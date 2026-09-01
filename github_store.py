"""
Persistenter State ueber die GitHub Contents API - funktioniert sowohl aus
Streamlit Cloud (fluechtiges Dateisystem!) als auch aus GitHub Actions,
ohne Branch-Checkout/-Push-Choreografie. Jede Datei liegt auf einem eigenen
Branch (config.GITHUB_STATE_BRANCH), getrennt vom main-Branch, damit
State-Updates KEINEN Streamlit-Cloud-Redeploy ausloesen.

Benoetigt:
- repo:  "owner/reponame" (in Streamlit: st.secrets["GITHUB_REPO"],
         in Actions: die eingebaute Variable ${{ github.repository }})
- token: Personal Access Token mit "repo"-Scope (Streamlit: eigenes Secret
         GITHUB_TOKEN in st.secrets) bzw. in Actions einfach
         secrets.GITHUB_TOKEN (Standard-Token reicht, wenn
         "Read and write permissions" aktiviert sind).
"""
import base64
import json
import logging

import requests

GITHUB_API = "https://api.github.com"


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_json(repo, branch, path, token, default=None):
    """Liest eine JSON-Datei vom State-Branch. Gibt (daten, sha) zurueck.
    sha wird fuer den naechsten put_json()-Aufruf gebraucht (Konflikterkennung)."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    try:
        r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=10)
        if r.status_code == 404:
            return default, None
        r.raise_for_status()
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content), data["sha"]
    except Exception as e:
        logging.error(f"github_store.get_json Fehler ({path}): {e}")
        return default, None


def put_json(repo, branch, path, obj, token, message="update state"):
    """Schreibt eine JSON-Datei auf den State-Branch (liest vorher den
    aktuellen sha, damit kein bestehender Inhalt versehentlich ueberschrieben
    wird, falls parallel etwas anderes geschrieben hat)."""
    _, sha = get_json(repo, branch, path, token)
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    content_b64 = base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": content_b64, "branch": branch}
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(url, headers=_headers(token), json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"github_store.put_json Fehler ({path}): {e}")
        return False


def append_csv_line(repo, branch, path, line, token, header=None, message="append data"):
    """Haengt eine Zeile an eine CSV-Datei auf dem State-Branch an (liest,
    haengt an, schreibt zurueck). Fuer hochfrequente Daten (z.B. alle 5 Min)
    einen nach Monat rotierenden Pfad verwenden (siehe config.price_history_csv_path),
    damit die einzelne Datei nicht unbegrenzt waechst."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
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
        logging.error(f"github_store.append_csv_line Lesefehler ({path}): {e}")
        return False

    if not existing and header:
        existing = header + "\n"

    new_content = (existing.rstrip("\n") + "\n" + line + "\n") if existing else (line + "\n")
    content_b64 = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": content_b64, "branch": branch}
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(url, headers=_headers(token), json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"github_store.append_csv_line Schreibfehler ({path}): {e}")
        return False
