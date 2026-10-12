"""Chronik (frueher "Trader-Log"): automatische Eintraege aus App und Workflows.

Eine Liste in config.STATE_PATH_TRADES_DB (neueste zuerst). Jeder Eintrag:
    {"id", "datum": "YYYY-MM-DD", "zeit": "HH:MM", "kategorie", "typ",
     "titel", "inhalt", "quelle": "auto"|"manuell", "schluessel"}

kategorie: "alarm" (Kurs-Alarme, Allzeithochs), "depot" (Positionen, Sparplan),
"beobachtung" (beobachtete Werte), "planer" (Musterdepots), "notiz" (manuell).
"schluessel" verhindert doppelte Eintraege (z. B. derselbe Alarm zweimal).
Alte, manuell angelegte Eintraege (typ Trade/Kommentar/Hinweis) bleiben gueltig.
"zugang" (Anmeldungen): nur Datum, keine Uhrzeit; schluessel "login-<name>-YYYYMMDD"
-> hoechstens ein Eintrag je Benutzer und Tag. Aufbewahrung: die Liste wird auf
MAX_EINTRAEGE gekuerzt (aelteste Auto-Eintraege zuerst, manuelle Notizen bleiben).
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


# Kategorien, deren Eintraege ohne Uhrzeit gespeichert werden (Datensparsamkeit,
# Audit DATA-06: Anmeldungen nur mit Datum, hoechstens einmal je Benutzer und Tag).
OHNE_UHRZEIT = {"zugang"}


def neuer_eintrag(kategorie, titel, inhalt="", schluessel=None, typ=None, quelle="auto", zeitpunkt=None):
    t = zeitpunkt or jetzt()
    zeit = "" if kategorie in OHNE_UHRZEIT else t.strftime("%H:%M")
    return {"datum": t.strftime("%Y-%m-%d"), "zeit": zeit, "kategorie": kategorie,
            "typ": typ or KATEGORIEN.get(kategorie, ("", kategorie))[1], "titel": str(titel),
            "inhalt": str(inhalt or ""), "quelle": quelle, "schluessel": schluessel}


def _id(x):
    try:
        return int(x.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def anhaengen(liste, eintrag, max_n=MAX_EINTRAEGE):
    """Eintrag vorne einfuegen (ohne Duplikat ueber 'schluessel').
    Beim Kuerzen auf max_n bleiben manuelle Notizen erhalten - gekuerzt werden
    nur die aeltesten automatischen Eintraege.
    -> (neue Liste, True wenn eingefuegt)"""
    liste = [x for x in (liste or []) if isinstance(x, dict)]
    s = eintrag.get("schluessel")
    if s and any(x.get("schluessel") == s for x in liste):
        return liste, False
    naechste_id = max([_id(x) for x in liste] + [0]) + 1
    liste.insert(0, dict(eintrag, id=naechste_id))
    if len(liste) > max_n:
        zu_viel = len(liste) - max_n
        behalten = []
        for x in reversed(liste):              # von alt nach neu: alte Auto-Eintraege fallen weg
            if zu_viel > 0 and x.get("quelle", "auto") != "manuell" and x is not liste[0]:
                zu_viel -= 1
                continue
            behalten.append(x)
        liste = list(reversed(behalten))
    return liste, True


def kategorie_von(eintrag):
    """Kategorie auch fuer alte, manuelle Eintraege ohne Feld 'kategorie'."""
    k = eintrag.get("kategorie")
    return k if k in KATEGORIEN else "notiz"


def eintragen_github(github_store, repo, branch, pfad, token, eintrag):
    """Fuer Workflows und App: Eintrag mit Versionspruefung anhaengen (keine
    verlorenen Eintraege bei gleichzeitigen Schreibern, kein Ueberschreiben bei
    Lesefehlern). Fehler werden geschluckt - die Chronik darf keinen Alarm verhindern.
    -> True wenn eingefuegt"""
    try:
        eingefuegt = {"ja": False}

        def aendern(liste):
            neu, ok = anhaengen(liste if isinstance(liste, list) else [], eintrag)
            eingefuegt["ja"] = ok
            return neu if ok else None

        if hasattr(github_store, "aktualisiere_json"):
            ok, _ = github_store.aktualisiere_json(
                repo, branch, pfad, token, aendern, default=[],
                message=f"chronik: {eintrag.get('titel', '')[:50]} [skip ci]")
            return bool(ok and eingefuegt["ja"])
        liste, _ = github_store.get_json(repo, branch, pfad, token, default=[])
        neu = aendern(liste)
        if neu is not None:
            return bool(github_store.put_json(repo, branch, pfad, neu, token,
                                              message=f"chronik: {eintrag.get('titel', '')[:50]} [skip ci]"))
        return False
    except Exception:
        return False
