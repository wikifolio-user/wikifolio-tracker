"""GitHub-Releases als Dateiablage fuer grosse Dateien (fertige Videos) im privaten State-Repo und Start von
Workflows per API. Tokens werden nie ausgegeben (Fehlertexte ueber github_store.sauber)."""
import os

import requests

import github_store

API = github_store.GITHUB_API
UPLOAD = "https://uploads.github.com"


def _h(token, **extra):
    return dict(github_store._headers(token), **extra)


def release_holen(repo, tag, token, name=None):
    """Release mit diesem Tag holen oder anlegen (Entwurf=nein, als Vorabversion markiert). -> dict"""
    r = requests.get(f"{API}/repos/{repo}/releases/tags/{tag}", headers=_h(token), timeout=20)
    if r.status_code == 200:
        return r.json()
    if r.status_code != 404:
        raise IOError(github_store.sauber(f"Release lesen: HTTP {r.status_code}"))
    r = requests.post(f"{API}/repos/{repo}/releases", headers=_h(token), timeout=20,
                      json={"tag_name": tag, "name": name or tag, "prerelease": True,
                            "body": "Automatisch erzeugt von der Video Factory (Faceless YouTube)."})
    if r.status_code not in (200, 201):
        raise IOError(github_store.sauber(f"Release anlegen: HTTP {r.status_code}"))
    return r.json()


def hochladen(repo, release, pfad, token, name=None, typ="application/octet-stream"):
    """Datei als Asset hochladen (gleichnamiges Asset wird ersetzt). -> {"id", "name", "groesse"}"""
    name = name or os.path.basename(pfad)
    for a in release.get("assets") or []:
        if a.get("name") == name:
            requests.delete(f"{API}/repos/{repo}/releases/assets/{a['id']}", headers=_h(token), timeout=20)
    with open(pfad, "rb") as f:
        r = requests.post(f"{UPLOAD}/repos/{repo}/releases/{release['id']}/assets", params={"name": name},
                          headers=_h(token, **{"Content-Type": typ}), data=f, timeout=600)
    if r.status_code not in (200, 201):
        raise IOError(github_store.sauber(f"Hochladen {name}: HTTP {r.status_code}"))
    a = r.json()
    return {"id": a["id"], "name": a["name"], "groesse": a.get("size")}


def laden(repo, asset_id, token):
    """Asset (auch aus privatem Repo) herunterladen -> bytes"""
    r = requests.get(f"{API}/repos/{repo}/releases/assets/{asset_id}", timeout=120,
                     headers=_h(token, Accept="application/octet-stream"))
    if r.status_code != 200:
        raise IOError(github_store.sauber(f"Datei laden: HTTP {r.status_code}"))
    return r.content


def workflow_starten(repo, workflow, token, inputs=None, ref="main"):
    """workflow_dispatch ausloesen. -> (ok, meldung)"""
    try:
        r = requests.post(f"{API}/repos/{repo}/actions/workflows/{workflow}/dispatches", headers=_h(token),
                          json={"ref": ref, "inputs": inputs or {}}, timeout=20)
    except Exception as ex:
        return False, f"nicht erreichbar ({type(ex).__name__})"
    if r.status_code == 204:
        return True, "gestartet"
    return False, {403: "keine Berechtigung (der Zugang der App darf hier keine Workflows starten)",
                   404: "Workflow oder Repository nicht gefunden"}.get(r.status_code, f"HTTP {r.status_code}")
