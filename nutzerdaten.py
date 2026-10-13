"""Benutzerbezogene Speicherorte und gemerkte Eingaben.

Regel:
- Der Admin (und die App ohne Login) nutzt die bisherigen Pfade unveraendert -
  seine vorhandenen Daten bleiben exakt wo sie sind, auch die Workflows (Kursalarme,
  Allzeithoch) lesen weiter dort.
- Jeder andere Benutzer bekommt einen eigenen Ordner state/benutzer/<name>/ mit
  denselben Dateinamen. Existiert dort noch nichts, startet er leer (0).
- Gemeinsame Marktdaten (Top-Listen, Qualitaets-Score, Katalog, Kurse, Alarm-Zustaende)
  sind NICHT benutzerbezogen und werden nie ueber diese Funktion geleitet.

Gemerkte Eingaben (Rechner, Formulare): eine Datei je Benutzer
(<ordner>/eingaben.json, {bereich: {feld: wert}}). Gespeichert wird nur, wenn sich
etwas geaendert hat, und hoechstens alle MIN_ABSTAND_SEK Sekunden je Bereich - so
entsteht nicht bei jedem Tastendruck ein GitHub-Commit.
"""
import re
import time
import unicodedata

ORDNER = "state/benutzer"
EINGABEN_DATEI = "eingaben.json"
MIN_ABSTAND_SEK = 20


def slug(name):
    """Dateisystem-tauglicher, eindeutiger Ordnername aus dem Benutzernamen."""
    t = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[^a-z0-9_-]+", "-", t).strip("-")
    return t[:60] or "benutzer"


def ist_eigener_bereich(nutzer):
    """True, wenn der Benutzer eigene Daten hat (alle ausser Admin / ohne Login)."""
    return bool(nutzer) and nutzer.get("rolle") != "admin" and bool(nutzer.get("name"))


def ordner(nutzer):
    return f"{ORDNER}/{slug(nutzer['name'])}" if ist_eigener_bereich(nutzer) else None


def pfad(basis, nutzer):
    """Speicherort einer Datei fuer diesen Benutzer.
    basis: bisheriger Pfad, z. B. "state/positionen.json" -> fuer Benutzer "anna":
    "state/benutzer/anna/positionen.json"; fuer den Admin unveraendert."""
    o = ordner(nutzer)
    if not o:
        return basis
    datei = str(basis).replace("\\", "/").split("/state/", 1)[-1]
    if datei.startswith("state/"):
        datei = datei[len("state/"):]
    return f"{o}/{datei}"


def eingaben_pfad(nutzer):
    o = ordner(nutzer)
    return f"{o}/{EINGABEN_DATEI}" if o else f"state/{EINGABEN_DATEI}"


def _sauber(werte):
    """Nur JSON-taugliche einfache Werte merken (Zahlen, Text, Bool, Listen davon)."""
    aus = {}
    for k, v in (werte or {}).items():
        if isinstance(v, (bool, int, float, str)) or v is None:
            if isinstance(v, float) and v != v:            # NaN nicht speichern
                continue
            aus[str(k)] = v
        elif isinstance(v, (list, tuple)) and all(isinstance(x, (bool, int, float, str)) for x in v):
            aus[str(k)] = list(v)
        elif hasattr(v, "isoformat"):                      # date / datetime
            aus[str(k)] = v.isoformat()
    return aus


def eingaben_laden(gh_read, nutzer, bereich):
    """{feld: wert} des Bereichs (z. B. "zinsrechner"); leer, wenn noch nichts gemerkt."""
    daten = gh_read(eingaben_pfad(nutzer), {}) or {}
    b = daten.get(bereich) if isinstance(daten, dict) else None
    return dict(b) if isinstance(b, dict) else {}


def eingaben_merken(gh_aktualisiere, session_state, nutzer, bereich, werte, sofort=False, jetzt=None):
    """Merkt die Eingaben eines Bereichs, wenn sie sich geaendert haben.
    Hoechstens alle MIN_ABSTAND_SEK Sekunden (sofort=True umgeht das, z. B. beim
    Verlassen der Ansicht). -> True wenn gespeichert, False wenn nicht noetig/fehlgeschlagen."""
    neu = _sauber(werte)
    merk = f"_eingaben_{bereich}"
    letzte = session_state.get(merk) or {}
    if letzte.get("werte") == neu:
        return False
    t = time.time() if jetzt is None else jetzt
    if not sofort and t - float(letzte.get("zeit") or 0) < MIN_ABSTAND_SEK:
        session_state[merk + "_offen"] = neu               # spaeter nachholen
        return False

    def aendern(daten):
        daten = daten if isinstance(daten, dict) else {}
        if daten.get(bereich) == neu:
            return None
        daten[bereich] = neu
        return daten

    ok, _ = gh_aktualisiere(eingaben_pfad(nutzer), aendern, default={},
                            message=f"eingaben {slug((nutzer or {}).get('name') or 'admin')}/{bereich} [skip ci]")
    if ok:
        session_state[merk] = {"werte": neu, "zeit": t}
        session_state.pop(merk + "_offen", None)
    return bool(ok)


def eingaben_vorbelegen(session_state, gespeichert, schluessel_map):
    """Gemerkte Werte in die Widget-Schluessel schreiben - nur beim ersten Aufruf der
    Sitzung (danach gelten die aktuellen Eingaben). schluessel_map: {feld: widget_key}."""
    flag = "_vorbelegt_" + "_".join(sorted(schluessel_map.values()))[:80]
    if session_state.get(flag):
        return False
    for feld, key in schluessel_map.items():
        if feld in gespeichert and key not in session_state:
            session_state[key] = gespeichert[feld]
    session_state[flag] = True
    return True
