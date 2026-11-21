"""Automatischer Abruf von Produktdaten zu WKN/ISIN (Knock-out-Zertifikate und gehebelte ETPs) - ohne Streamlit.

Quelle: onvista (oeffentliche JSON-Schnittstelle der Website api.onvista.de, keine offizielle API - kann sich
aendern; dann bleibt die manuelle Eingabe). Abruf nur auf Knopfdruck, Ergebnis wird vom Benutzer geprueft und kann
ueberschrieben werden. Die Antworten werden validiert; fehlende Werte bleiben leer (nie geraten).

  suchen(kennung)          WKN oder ISIN -> {isin, wkn, name, typ}
  ko_produkt(kennung)      -> Felder fuer ko_rechner.zertifikat (Basispreis, KO-Schwelle, Bezug, Geld/Brief, ...)
  etp_produkt(kennung)     -> Felder fuer den ETP-Rechner (Hebelfaktor, Kosten, Kurs, Spread, ...)
"""
import datetime
import re

API = "https://api.onvista.de/api/v1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36", "Accept": "application/json"}
QUELLE = "onvista.de"
# Basiswert (ISIN des Index bzw. Namensbestandteil) -> Code in ko_rechner.INDIZES
BASIS_ISIN = {"US6311011026": "NDX", "DE0008469008": "DAX", "DE0008469594": "DAX", "US78378X1072": "SPX",
              "US2605661048": "DJI"}
BASIS_NAME = [(re.compile(r"nasdaq[\s-]*100", re.I), "NDX"), (re.compile(r"\bdax\b", re.I), "DAX"),
              (re.compile(r"s\s*&\s*p\s*500", re.I), "SPX"), (re.compile(r"dow\s*jones|\bdjia\b", re.I), "DJI")]
KENNUNG = re.compile(r"^([A-Z]{2}[A-Z0-9]{9}[0-9]|[A-Z0-9]{6})$")


class ProduktFehler(Exception):
    pass


def _zahl(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def kennung_pruefen(kennung):
    k = re.sub(r"\s+", "", str(kennung or "")).upper()
    if not KENNUNG.match(k):
        raise ProduktFehler("Bitte eine gültige WKN (6 Zeichen) oder ISIN (12 Zeichen) eingeben.")
    return k


def _json(get, url, params=None):
    try:
        r = get(url, params=params, headers=HEADERS, timeout=15)
    except Exception:
        raise ProduktFehler("Die Produktdaten-Quelle ist gerade nicht erreichbar – bitte die Daten von Hand "
                            "eintragen.") from None
    if r.status_code == 404:
        raise ProduktFehler("Zu dieser Kennung wurden keine Produktdaten gefunden.")
    if r.status_code != 200:
        raise ProduktFehler(f"Die Produktdaten-Quelle hat nicht geantwortet (Fehler {r.status_code}).")
    try:
        return r.json()
    except ValueError:
        raise ProduktFehler("Die Antwort der Produktdaten-Quelle war unlesbar.") from None


def suchen(kennung, get):
    """WKN/ISIN -> {"isin", "wkn", "name", "typ" (entitySubType)}."""
    k = kennung_pruefen(kennung)
    d = _json(get, f"{API}/instruments/query", {"searchValue": k})
    for x in (d.get("list") if isinstance(d, dict) else None) or []:
        if k in (str(x.get("isin") or "").upper(), str(x.get("wkn") or "").upper()):
            return {"isin": x.get("isin"), "wkn": x.get("wkn"), "name": x.get("name") or "",
                    "typ": x.get("entitySubType") or x.get("entityType") or ""}
    raise ProduktFehler(f"Zu {k} wurde kein Produkt gefunden.")


def _snapshot(isin, get):
    d = _json(get, f"{API}/derivatives/ISIN:{isin}/snapshot")
    if not isinstance(d, dict) or "derivativesDetails" not in d:
        raise ProduktFehler("Für dieses Produkt liegen keine Derivate-Daten vor (kein Zertifikat/ETP?).")
    return d


def _basiswert(underlyings):
    for u in underlyings:
        isin = str(((u.get("instrument") or {}).get("isin")) or "")
        if isin in BASIS_ISIN:
            return BASIS_ISIN[isin]
    for u in underlyings:
        text = " ".join(str(x or "") for x in (u.get("shortName"), u.get("officialName"),
                                                 (u.get("instrument") or {}).get("name")))
        for muster, code in BASIS_NAME:
            if muster.search(text):
                return code
    return None


def _zeit(*kandidaten):
    for k in kandidaten:
        try:
            return datetime.datetime.fromisoformat(str(k).replace("Z", "+00:00")).isoformat(timespec="minutes")
        except (TypeError, ValueError):
            continue
    return ""


def ko_aus_snapshot(d):
    """onvista-Snapshot eines Knock-out-Produkts -> Produktdaten fuer ko_rechner (fehlende Werte None)."""
    det = d.get("derivativesDetails") or {}
    unter = (d.get("derivativesUnderlyingList") or {}).get("list") or []
    if not unter:
        raise ProduktFehler("Zum Produkt ist kein Basiswert hinterlegt.")
    u = unter[0]
    schwellen = {b.get("typeBarrier"): _zahl(b.get("barrier"))
                 for b in ((u.get("derivativesBarrierList") or {}).get("list") or [])}
    recht = str(det.get("codeExerciseRight") or (d.get("keywords") or {}).get("idExerciseRight") or "").upper()
    richtung = "long" if recht == "C" else "short" if recht == "P" else None
    geld, brief = _zahl((d.get("bid") or {}).get("last")), _zahl((d.get("ask") or {}).get("last"))
    aus = {"isin": (d.get("instrument") or {}).get("isin"), "wkn": (d.get("instrument") or {}).get("wkn"),
           "name": det.get("shortName") or (d.get("instrument") or {}).get("name") or "",
           "emittent": (d.get("derivativesIssuer") or {}).get("name") or "",
           "typ": det.get("nameSubcategory") or (d.get("instrument") or {}).get("displayType") or "",
           "basiswert": _basiswert(unter), "richtung": richtung,
           "basispreis": schwellen.get("STRIKE"), "ko_schwelle": schwellen.get("KNOCK_OUT") or schwellen.get("STRIKE"),
           "bezug": _zahl(u.get("coverRatio")), "geld": geld, "brief": brief,
           "waehrung": (d.get("quote") or {}).get("isoCurrency") or det.get("isoCurrency") or "",
           "quanto": bool(det.get("quanto")), "restwert": 0.0 if det.get("totalLossOnKnockout") else None,
           "ausgeknockt": bool(det.get("hasBarrierBeenHit")),
           "stand": _zeit((d.get("ask") or {}).get("datetimeLast"), (d.get("derivativesFigure") or {}).get("datetimePrice")),
           "quelle": QUELLE, "finanzierung_pct": None}
    fehlt = [t for f, t in (("basiswert", "Basiswert"), ("richtung", "Long/Short"), ("basispreis", "Basispreis"),
                            ("ko_schwelle", "Knock-out-Schwelle"), ("bezug", "Bezugsverhältnis"), ("brief", "Briefkurs"))
             if not aus[f]]
    aus["fehlt"] = fehlt
    return aus


def etp_aus_snapshot(d):
    """onvista-Snapshot eines gehebelten ETP/ETC/ETN -> Produktdaten fuer den ETP-Rechner."""
    det = d.get("derivativesDetails") or {}
    unter = (d.get("derivativesUnderlyingList") or {}).get("list") or []
    name = " ".join(str(x or "") for x in (det.get("officialName"), det.get("shortName"),
                                           (d.get("instrument") or {}).get("name")))
    hebel = _zahl(det.get("participationRateWin"))
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*x", name, re.I)
    if hebel is None and m:
        hebel = abs(_zahl(m.group(1).replace(",", ".")) or 0) or None
    if hebel is not None and re.search(r"\bshort\b|\binverse\b|-\s*\d+\s*x", name, re.I):
        hebel = -abs(hebel)
    geld, brief = _zahl((d.get("bid") or {}).get("last")), _zahl((d.get("ask") or {}).get("last"))
    aus = {"isin": (d.get("instrument") or {}).get("isin"), "wkn": (d.get("instrument") or {}).get("wkn"),
           "name": det.get("officialName") or det.get("shortName") or "",
           "emittent": (d.get("derivativesIssuer") or {}).get("name") or "",
           "basiswert": _basiswert(unter) or next((c for mu, c in BASIS_NAME if mu.search(name)), None),
           "hebel": hebel, "kurs": brief or geld,
           "waehrung": (d.get("quote") or {}).get("isoCurrency") or det.get("isoCurrency") or "",
           "kosten": _zahl(det.get("managementFeePct")),
           "spread": round((brief - geld) / brief * 100, 3) if geld and brief and brief >= geld else None,
           "stand": _zeit((d.get("ask") or {}).get("datetimeLast"), (d.get("derivativesFigure") or {}).get("datetimePrice")),
           "quelle": QUELLE}
    aus["fehlt"] = [t for f, t in (("hebel", "Hebelfaktor"), ("basiswert", "Basisindex"), ("kurs", "Produktkurs"))
                    if not aus[f]]
    return aus


def ko_produkt(kennung, get):
    treffer = suchen(kennung, get)
    if "KNOCKOUT" not in treffer["typ"].upper() and "WARRANT" not in treffer["typ"].upper():
        raise ProduktFehler(f"{treffer['name']} ist kein Knock-out-Produkt ({treffer['typ'] or 'unbekannter Typ'}).")
    return ko_aus_snapshot(_snapshot(treffer["isin"], get))


def etp_produkt(kennung, get):
    treffer = suchen(kennung, get)
    return etp_aus_snapshot(_snapshot(treffer["isin"], get))
