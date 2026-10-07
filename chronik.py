"""Chronik (frueher "Trader-Log"): automatische Eintraege aus App und Workflows.

Eine Liste in config.STATE_PATH_TRADES_DB (neueste zuerst). Jeder Eintrag:
    {"id", "datum": "YYYY-MM-DD", "zeit": "HH:MM", "kategorie", "typ",
     "titel", "inhalt", "quelle": "auto"|"manuell", "schluessel"}

kategorie: "alarm" (Kurs-Alarme, Allzeithochs), "depot" (Positionen, Sparplan),
"beobachtung" (beobachtete Werte), "planer" (Musterdepots), "notiz" (manuell).
"schluessel" verhindert doppelte Eintraege (z. B. derselbe Alarm zweimal).
Alte, manuell angelegte Eintraege (typ Trade/Kommentar/Hinweis) bleiben gueltig.
"""
import datetime

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Berlin")
except Exception:          # pragma: no cover
    _TZ = None

MAX_EINTRAEGE = 800

KATEGORIEN = {
    "alarm": ("🚨", "Alarme & Hochs"),
    "depot": ("💼", "Depot"),
    "beobachtung": ("👀", "Beobachtung"),
    "planer": ("📦", "Planer"),
    "zugang": ("🔐", "Anmeldungen"),
    "notiz": ("✏️", "Notizen"),
}


def jetzt():
    return datetime.datetime.now(_TZ) if _TZ else datetime.datetime.now()


def neuer_eintrag(kategorie, titel, inhalt="", schluessel=None, typ=None, quelle="auto", zeitpunkt=None):
    t = zeitpunkt or jetzt()
    return {"datum": t.strftime("%Y-%m-%d"), "zeit": t.strftime("%H:%M"), "kategorie": kategorie,
            "typ": typ or KATEGORIEN.get(kategorie, ("", kategorie))[1], "titel": str(titel),
            "inhalt": str(inhalt or ""), "quelle": quelle, "schluessel": schluessel}


def anhaengen(liste, eintrag, max_n=MAX_EINTRAEGE):
    """Eintrag vorne einfuegen (ohne Duplikat ueber 'schluessel').
    -> (neue Liste, True wenn eingefuegt)"""
    liste = list(liste or [])
    s = eintrag.get("schluessel")
    if s and any(isinstance(x, dict) and x.get("schluessel") == s for x in liste):
        return liste, False
    naechste_id = max([int(x.get("id") or 0) for x in liste if isinstance(x, dict)] + [0]) + 1
    liste.insert(0, dict(eintrag, id=naechste_id))
    return liste[:max_n], True


def kategorie_von(eintrag):
    """Kategorie auch fuer alte, manuelle Eintraege ohne Feld 'kategorie'."""
    k = eintrag.get("kategorie")
    return k if k in KATEGORIEN else "notiz"


def eintragen_github(github_store, repo, branch, pfad, token, eintrag):
    """Fuer Workflows: Chronik lesen, Eintrag anhaengen, zurueckschreiben.
    Fehler werden geschluckt - die Chronik darf keinen Alarm verhindern."""
    try:
        liste, _ = github_store.get_json(repo, branch, pfad, token, default=[])
        neu, eingefuegt = anhaengen(liste if isinstance(liste, list) else [], eintrag)
        if eingefuegt:
            github_store.put_json(repo, branch, pfad, neu, token,
                                  message=f"chronik: {eintrag.get('titel', '')[:50]} [skip ci]")
        return eingefuegt
    except Exception:
        return False
