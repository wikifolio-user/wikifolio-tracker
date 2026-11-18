"""Intervallfasten: starten, beenden, Dauer und Essensfenster - ohne Streamlit.

Gespeichert im Profil (eine laufende Fastenzeit reicht ueber Mitternacht hinweg):
  "fasten": {"plan": "16:8", "laeuft": {"start": iso, "ziel_h": 16} | None,
             "verlauf": [{"start": iso, "ende": iso, "ziel_h": 16}]}
Alle Zeiten mit Zeitzone (Europe/Berlin) - so stimmt die Dauer auch ueber die Zeitumstellung.
"""
import datetime

PLAENE = {"12:12": 12, "14:10": 14, "16:8": 16, "18:6": 18}
MAX_VERLAUF = 500


def ziel_stunden(plan, eigene_h=None):
    if plan in PLAENE:
        return PLAENE[plan]
    try:
        return max(1.0, min(72.0, float(eigene_h)))
    except (TypeError, ValueError):
        return 16


def _dt(text):
    try:
        return datetime.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def standard():
    return {"plan": "16:8", "laeuft": None, "verlauf": []}


def zustand(doc):
    f = (doc or {}).get("fasten")
    return {**standard(), **f} if isinstance(f, dict) else standard()


def starten(doc, jetzt, ziel_h):
    d = dict(doc or {})
    f = zustand(d)
    if not f["laeuft"]:
        f["laeuft"] = {"start": jetzt.isoformat(timespec="seconds"), "ziel_h": float(ziel_h)}
    d["fasten"] = f
    return d


def beenden(doc, jetzt):
    """Laufende Fastenzeit beenden und in den Verlauf schreiben (Ende nie vor dem Start)."""
    d = dict(doc or {})
    f = zustand(d)
    l = f.get("laeuft")
    if l:
        start = _dt(l.get("start"))
        ende = max(jetzt, start) if start else jetzt
        f["verlauf"] = (f["verlauf"] + [{"start": l["start"], "ende": ende.isoformat(timespec="seconds"),
                                         "ziel_h": l.get("ziel_h")}])[-MAX_VERLAUF:]
        f["laeuft"] = None
    d["fasten"] = f
    return d


def abbrechen(doc):
    """Versehentlich gestartet: ohne Eintrag im Verlauf verwerfen."""
    d = dict(doc or {})
    f = zustand(d)
    f["laeuft"] = None
    d["fasten"] = f
    return d


def status(laeuft, jetzt):
    """Laufende Fastenzeit -> {"start", "dauer_h", "ziel_h", "ende_geplant", "fenster_bis", "anteil", "erreicht"}"""
    if not laeuft:
        return None
    start = _dt(laeuft.get("start"))
    if not start:
        return None
    ziel = float(laeuft.get("ziel_h") or 16)
    dauer = max(0.0, (jetzt - start).total_seconds() / 3600)
    ende = start + datetime.timedelta(hours=ziel)
    return {"start": start, "dauer_h": dauer, "ziel_h": ziel, "ende_geplant": ende,
            "fenster_bis": ende + datetime.timedelta(hours=max(0.0, 24 - ziel)), "anteil": dauer / ziel,
            "erreicht": dauer >= ziel}


def dauer_text(stunden):
    h = int(stunden)
    m = int(round((stunden - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h}:{m:02d} h"


def am_tag(verlauf, tag):
    """Abgeschlossene Fastenzeiten, die an diesem Tag ENDETEN -> [(dauer_h, ziel_h, erreicht)]."""
    aus = []
    for v in verlauf or []:
        s, e = _dt(v.get("start")), _dt(v.get("ende"))
        if s and e and e.date() == tag:
            d = (e - s).total_seconds() / 3600
            aus.append((d, float(v.get("ziel_h") or 0), d >= float(v.get("ziel_h") or 0)))
    return aus
