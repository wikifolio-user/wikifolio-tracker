"""Einheitliches Speichern und Rueckgaengig fuer alle Eingabeseiten (Audit UX-03).

Jede Eingabeseite zeigt am Ende dieselbe Statuszeile:
    ✓ Gespeichert um 14:32            (Stand liegt im Speicher)
    ● Ungespeicherte Änderungen       (bei Seiten mit Speichern-Knopf)
    ⚠️ Nicht gespeichert …            (Speicher gerade nicht erreichbar)
    Nur für diese Sitzung …           (Seiten ohne Speicher, z. B. Prognose)
und - wo gespeichert wird - "↶ Rückgängig": nimmt die letzte Speicherung zurück (bis zu MAX_SCHRITTE je Bereich und
Sitzung) und schreibt den vorherigen Stand wieder in den Speicher.

Logik ohne Streamlit testbar: ss ist st.session_state (oder ein dict).
    aktualisieren(ss, bereich, gh_aktualisiere, pfad, aendern, ...)   statt gh_aktualisiere(...) - merkt den alten Stand
    gespeichert(ss, bereich, vorher)                                  fuer Seiten, die anders speichern
    zuruecknehmen(ss, bereich, gh_aktualisiere, pfad, ...) -> Stand   schreibt den letzten alten Stand zurueck
"""
import copy
import datetime

MAX_SCHRITTE = 10
_PRAEFIX = "_sl_"

TEXT_SITZUNG = "Nur für diese Sitzung – wird nicht gespeichert."


def _jetzt():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:            # pragma: no cover
        return datetime.datetime.now()


def zustand(ss, bereich):
    """-> {"stapel": [alte Staende], "zeit": datetime|None, "status": None|"gespeichert"|"geaendert"|"fehler"}"""
    k = _PRAEFIX + bereich
    if not isinstance(ss.get(k), dict):
        ss[k] = {"stapel": [], "zeit": None, "status": None}
    return ss[k]


def gespeichert(ss, bereich, vorher=None, zeit=None, merken=True):
    """Erfolgreich gespeichert. vorher: Stand VOR dieser Speicherung (fuer Rueckgaengig; None = nichts merken)."""
    z = zustand(ss, bereich)
    if merken and vorher is not None:
        z["stapel"].append(copy.deepcopy(vorher))
        del z["stapel"][:-MAX_SCHRITTE]
    z["zeit"] = zeit or _jetzt()
    z["status"] = "gespeichert"


def geaendert(ss, bereich):
    """Eingaben geaendert, aber (noch) nicht gespeichert (Seiten mit Speichern-Knopf)."""
    zustand(ss, bereich)["status"] = "geaendert"


def fehlgeschlagen(ss, bereich):
    zustand(ss, bereich)["status"] = "fehler"


def schritte(ss, bereich):
    return len(zustand(ss, bereich)["stapel"])


def aktualisieren(ss, bereich, gh_aktualisiere, pfad, aendern, default=None, message="", merken=True):
    """Wie gh_aktualisiere(pfad, aendern, default, message), merkt aber den Stand davor fuer Rueckgaengig.
    -> (ok, neu) wie gh_aktualisiere"""
    alt_box = {}

    def mit_merken(alt):
        alt_box["alt"] = copy.deepcopy(alt)
        return aendern(alt)
    try:
        ok, neu = gh_aktualisiere(pfad, mit_merken, default, message)
    except Exception:
        ok, neu = False, None
    if ok:
        vorher = alt_box.get("alt")
        unveraendert = neu is not None and vorher == neu
        gespeichert(ss, bereich, None if unveraendert else vorher, merken=merken)
    else:
        fehlgeschlagen(ss, bereich)
    return ok, neu


def zuruecknehmen(ss, bereich, gh_aktualisiere, pfad, default=None, message="rückgängig [skip ci]"):
    """Letzten alten Stand zurueckschreiben. -> der wiederhergestellte Stand oder None (nichts da / Fehler -
    dann bleibt der Stapel unveraendert)."""
    z = zustand(ss, bereich)
    if not z["stapel"]:
        return None
    stand = z["stapel"][-1]
    try:
        ok, _ = gh_aktualisiere(pfad, lambda _alt: copy.deepcopy(stand), default, message)
    except Exception:
        ok = False
    if not ok:
        fehlgeschlagen(ss, bereich)
        return None
    z["stapel"].pop()
    gespeichert(ss, bereich, merken=False)
    return copy.deepcopy(stand)


def statustext(ss, bereich, modus="speicher"):
    """-> (symbol, text) fuer die Statuszeile. modus: "speicher" (wird gespeichert) oder "sitzung"."""
    if modus == "sitzung":
        return "", TEXT_SITZUNG
    z = zustand(ss, bereich)
    if z["status"] == "fehler":
        return "⚠️", "Nicht gespeichert – der Speicher ist gerade nicht erreichbar. Änderungen gelten nur in dieser Sitzung."
    if z["status"] == "geaendert":
        return "●", "Ungespeicherte Änderungen"
    if z["status"] == "gespeichert" and z["zeit"]:
        return "✓", f"Gespeichert um {z['zeit'].strftime('%H:%M')} Uhr"
    return "✓", "Gespeicherter Stand"


CSS = """<style>
[class*="st-key-sl_"] { border-top: 1px solid var(--rand, rgba(255,255,255,.12)); padding-top: 10px; margin-top: 8px; }
[class*="st-key-sl_"] [data-testid="stHorizontalBlock"] { align-items: center !important; flex-wrap: wrap !important; gap: 8px 12px !important; }
.sl-status { font-size: .85rem; color: var(--label, #A9B1C4); }
.sl-status b { color: var(--text, #E8ECF6); font-weight: 650; }
</style>"""


def leiste(st, bereich, modus="speicher", rueck=None, hinweis=None, anzahl=None):
    """Statuszeile am Ende einer Eingabeseite. rueck: Funktion ohne Argumente, die die letzte Speicherung
    zuruecknimmt (z. B. lambda: zuruecknehmen(...) + Oberflaeche aktualisieren); None = kein Rueckgaengig.
    anzahl: moegliche Rueckgaengig-Schritte, wenn die Seite ihren Verlauf selbst fuehrt (sonst der Stapel hier)."""
    import html
    symbol, text = statustext(st.session_state, bereich, modus)
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key=f"sl_{bereich}"):
        n = (schritte(st.session_state, bereich) if anzahl is None else int(anzahl)) if rueck else 0
        spalten = st.columns([3, 1]) if rueck else [st.container()]
        spalten[0].markdown(f'<div class="sl-status">{html.escape(symbol)} <b>{html.escape(text)}</b>'
                            + (f" · {html.escape(hinweis)}" if hinweis else "") + "</div>", unsafe_allow_html=True)
        if rueck:
            spalten[1].button("↶ Rückgängig" + (f" ({n})" if n > 1 else ""), key=f"slundo_{bereich}",
                              disabled=n == 0, on_click=rueck, width="stretch",
                              help="Nimmt die letzte Speicherung zurück" if n else "Noch nichts zum Zurücknehmen")
