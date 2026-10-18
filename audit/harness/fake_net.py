"""Audit-Harness: ersetzt requests.get/put/delete/post durch In-Memory-Fakes.

- api.github.com Contents-API -> Speicher in STORE (mit sha-Pruefung wie GitHub)
- ls-tc.de dataForInstrument   -> synthetische Kurse mit bekannten Werten
- discord.com                  -> wird nur protokolliert
- alles andere                 -> ConnectionError

Fehlerinjektion ueber die Datei FAULT (JSON): {"github_read": "500"|"timeout",
"lstc": "down"} - wird bei jedem Aufruf neu gelesen.
"""
import base64
import datetime
import hashlib
import json
import os
import threading
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

import requests

BASIS = os.path.dirname(os.path.abspath(__file__))
FAULT = os.path.join(BASIS, "fault.json")
DUMP = os.path.join(BASIS, "store_dump.json")
LOG = os.path.join(BASIS, "netlog.jsonl")
BERLIN = ZoneInfo("Europe/Berlin")
HEUTE = datetime.datetime.now(ZoneInfo("Europe/Berlin")).date()

STORE = {}            # path -> (bytes, sha)
LOCK = threading.Lock()
ZAEHLER = {"github_get": 0, "github_put": 0, "lstc": 0, "discord": 0}


def _fault():
    try:
        with open(FAULT) as f:
            return json.load(f)
    except Exception:
        return {}


def _log(eintrag):
    with open(LOG, "a") as f:
        f.write(json.dumps(eintrag) + "\n")


class R:
    def __init__(self, status, payload=None, text=None):
        self.status_code = status
        self._p = payload
        self.text = text if text is not None else json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._p if self._p is not None else json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------- Kurse
def _ms(d):
    return int(datetime.datetime.combine(d, datetime.time(0, 0), BERLIN).timestamp() * 1000)


def kursreihe(instrument_id):
    """Bekannte synthetische Reihe: Hauptinstrument 3865540 ab 09.07.2025 bei 100,
    je Handelstag +0,1; alle anderen Instrumente ab 02.01.2024 bei 50, +0,05/Tag."""
    if str(instrument_id) == "3865540":
        start, p0, step = datetime.date(2025, 7, 9), 100.0, 0.1
    else:
        start, p0, step = datetime.date(2024, 1, 2), 50.0, 0.05
    d, i, out = start, 0, []
    while d < HEUTE:
        if d.weekday() < 5:
            out.append((d, round(p0 + step * i, 4)))
            i += 1
        d += datetime.timedelta(days=1)
    return out


# synthetische Treffer der ls-tc-Suche (Name/WKN/ISIN -> instrumentId)
SUCHE = [
    {"instrumentId": 501, "displayname": "Siemens AG", "wkn": "723610", "isin": "DE0007236101", "categoryName": "Aktie"},
    {"instrumentId": 502, "displayname": "SAP SE", "wkn": "716460", "isin": "DE0007164600", "categoryName": "Aktie"},
    {"instrumentId": 503, "displayname": "Xtrackers MSCI World UCITS ETF", "wkn": "A1XB5U", "isin": "IE00BJ0KDQ92",
     "categoryName": "ETF"},
    {"instrumentId": 504, "displayname": "FF Inlinetrading", "wkn": "LS9VSU", "isin": "DE000LS9VSU1",
     "categoryName": "Wikifolio-Zertifikat"},
    {"instrumentId": 505, "displayname": "NVIDIA Corp.", "wkn": "918422", "isin": "US67066G1040", "categoryName": "Aktie"},
]


def lstc(params):
    if _fault().get("lstc") == "down":
        raise requests.ConnectionError("ls-tc down (fault)")
    inst = params.get("instrumentId", [""])[0]
    reihe = kursreihe(inst)
    hist = [[_ms(d), p] for d, p in reihe]
    vortag = reihe[-1][1]
    live = 150.0 if inst == "3865540" else round(vortag * 1.01, 4)
    letzter_tag = reihe[-1][0] if HEUTE.weekday() >= 5 else HEUTE
    jetzt = int(datetime.datetime.combine(letzter_tag, datetime.time(14, 0), BERLIN).timestamp() * 1000)
    serien = params.get("series", [""])[0]
    data = {"series": {"history": {"data": hist}}, "info": {"plotlines": [{"id": "previousDay", "value": vortag}]}}
    if "intraday" in serien:
        data["series"]["intraday"] = {"data": [[jetzt - 3600000, vortag], [jetzt, live]]}
    return R(200, data)


# ---------------------------------------------------------------- GitHub
def _sha(b):
    return hashlib.sha1(b).hexdigest()


def _dump():
    with open(DUMP, "w") as f:
        json.dump({p: b.decode("utf-8", "replace") for p, (b, _) in STORE.items()
                   if not (p.startswith("state/top50") or p.startswith("state/qualitaet"))}, f, ensure_ascii=False, indent=1)


def _extra_laden():
    """Testdaten von aussen einspielen: extra_store.json {pfad: text} (wird danach geloescht)."""
    pfad = os.path.join(BASIS, "extra_store.json")
    if os.path.exists(pfad):
        with open(pfad) as fh:
            for p, text in json.load(fh).items():
                b = text.encode()
                STORE[p] = (b, _sha(b + p.encode()))
        os.remove(pfad)


def gh_get(path):
    _extra_laden()
    f = _fault().get("github_read")
    if f == "timeout":
        raise requests.Timeout("fault")
    if f:
        return R(int(f), {"message": "fault"})
    with LOCK:
        if path in STORE:
            b, sha = STORE[path]
            return R(200, {"content": base64.b64encode(b).decode(), "sha": sha, "path": path, "type": "file"})
        kinder = sorted({p for p in STORE if p.startswith(path.rstrip("/") + "/")})
        if kinder:
            eintraege, gesehen = [], set()
            for p in kinder:
                rest = p[len(path.rstrip("/")) + 1:]
                teil = rest.split("/")[0]
                voll = f"{path.rstrip('/')}/{teil}"
                if voll in gesehen:
                    continue
                gesehen.add(voll)
                if "/" in rest:
                    eintraege.append({"type": "dir", "path": voll})
                else:
                    eintraege.append({"type": "file", "path": voll, "sha": STORE[voll][1]})
            return R(200, eintraege)
    return R(404, {"message": "Not Found"})


def gh_put(path, body):
    if _fault().get("github_write"):
        return R(int(_fault()["github_write"]), {"message": "fault"})
    with LOCK:
        neu = base64.b64decode(body["content"])
        if path in STORE:
            if body.get("sha") != STORE[path][1]:
                return R(409 if body.get("sha") else 422, {"message": "sha mismatch"})
        elif body.get("sha"):
            return R(404, {"message": "not found"})
        STORE[path] = (neu, _sha(neu + path.encode()))
        _dump()
        return R(201, {"content": {"sha": STORE[path][1]}})


def gh_delete(path, body):
    with LOCK:
        if path not in STORE:
            return R(404, {})
        if body.get("sha") != STORE[path][1]:
            return R(409, {})
        del STORE[path]
        _dump()
        return R(200, {})


def _contents_path(url):
    p = urlparse(url).path
    teil = p.split("/contents/", 1)
    return teil[1] if len(teil) == 2 else None


# ---------------------------------------------------------------- Dispatcher
_orig = {"get": requests.get, "put": requests.put, "delete": requests.delete, "post": requests.post}


def _netz(art, url):
    p = os.environ.get("NETZ_LOG")
    if p:
        import time as _t
        with open(p, "a") as f:
            f.write(f"{_t.time():.3f} {art} {url}\n")


def _get(url, params=None, headers=None, timeout=None, **kw):
    host = urlparse(url).hostname or ""
    _netz("GET", url.split("?")[0])
    if host == "api.github.com" and "/contents/" in url:
        ZAEHLER["github_get"] += 1
        return gh_get(_contents_path(url))
    if host.endswith("ls-tc.de") and "/instrument/search" in url:
        ZAEHLER["lstc"] += 1
        q = str((params or {}).get("q") or "").lower()
        return R(200, [t for t in SUCHE if q and (q in t["displayname"].lower() or q == t["wkn"].lower()
                                                   or q == t["isin"].lower())])
    if host.endswith("ls-tc.de"):
        ZAEHLER["lstc"] += 1
        q = {k: [str(v)] for k, v in (params or {}).items()}
        q.update(parse_qs(urlparse(url).query))
        return lstc(q)
    _log({"blockiert": "GET", "host": host})
    raise requests.ConnectionError(f"harness: {host} gesperrt")


def _put(url, headers=None, json=None, timeout=None, **kw):
    _netz("PUT", url)
    ZAEHLER["github_put"] += 1
    return gh_put(_contents_path(url), json or {})


def _delete(url, headers=None, json=None, timeout=None, **kw):
    return gh_delete(_contents_path(url), json or {})


def _post(url, json=None, timeout=None, **kw):
    host = urlparse(url).hostname or ""
    if "discord" in host:
        ZAEHLER["discord"] += 1
        _log({"discord": (json or {}).get("content", "")[:300]})
        return R(204)
    raise requests.ConnectionError(f"harness: POST {host} gesperrt")


def install():
    if getattr(requests, "_harness", False):
        return
    requests.get, requests.put, requests.delete, requests.post = _get, _put, _delete, _post
    requests._harness = True


def seed(path, obj):
    b = json.dumps(obj, ensure_ascii=False).encode()
    STORE[path] = (b, _sha(b + path.encode()))
