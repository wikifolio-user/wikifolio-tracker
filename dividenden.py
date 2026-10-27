"""Dividenden-Kategorien fuer die Top-500-Listen: Hoehe der Dividendenrendite (div, % p. a.) und
Nachhaltigkeit ueber die Ausschuettungsquote (div_q, % des Gewinns) - beides vom Qualitaets-Agenten."""

KATEGORIEN = [  # (Schluessel, Titel, von %, bis % (exklusiv))
    ("keine", "Keine Dividende", None, None),
    ("niedrig", "Niedrig (unter 2 %)", 0.0, 2.0),
    ("mittel", "Mittel (2–4 %)", 2.0, 4.0),
    ("hoch", "Hoch (4–6 %)", 4.0, 6.0),
    ("sehr_hoch", "Sehr hoch (6–10 %)", 6.0, 10.0),
    ("extrem", "Über 10 % (oft nicht haltbar)", 10.0, None),
]
TITEL = {k: t for k, t, _, _ in KATEGORIEN}
ICON = {"keine": "⚪", "niedrig": "🔹", "mittel": "🔷", "hoch": "💎", "sehr_hoch": "💰", "extrem": "⚠️"}

NACHHALTIG = [  # Ausschuettungsquote: (Schluessel, Titel, bis % inkl.)
    ("nachhaltig", "nachhaltig (≤ 60 % des Gewinns)", 60.0),
    ("solide", "solide (60–80 %)", 80.0),
    ("angespannt", "angespannt (80–100 %)", 100.0),
    ("ungedeckt", "nicht vom Gewinn gedeckt (> 100 %)", None),
]

# Auszahlungsrhythmus (vom Top-50-Agenten aus den Zahlungsterminen ermittelt)
RHYTHMEN = ("monatlich", "alle 2 Monate", "quartalsweise", "halbjährlich", "jährlich")

# Filter in der Watchlist (Titel -> Bedingung auf div/div_q)
FILTER = {
    "Alle": None,
    "Nur Dividendenzahler": ("ab", 0.0001),
    "ab 2 %": ("ab", 2.0),
    "ab 3 %": ("ab", 3.0),
    "ab 4 %": ("ab", 4.0),
    "ab 5 %": ("ab", 5.0),
    "Keine Dividende": ("keine", None),
}


def _z(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def kategorie(div):
    """Dividendenrendite % -> Schluessel (None = unbekannt)."""
    d = _z(div)
    if d is None:
        return None
    if d <= 0:
        return "keine"
    for k, _, von, bis in KATEGORIEN[1:]:
        if d >= von and (bis is None or d < bis):
            return k
    return None


def nachhaltigkeit(div, div_q):
    """Ausschuettungsquote -> Schluessel; None ohne Dividende oder ohne Quote."""
    d, q = _z(div), _z(div_q)
    if not d or d <= 0 or q is None:
        return None
    if q < 0:
        return "ungedeckt"                 # Verlust, Dividende aus der Substanz
    for k, _, bis in NACHHALTIG:
        if bis is None or q <= bis:
            return k
    return "ungedeckt"


def passt(w, filter_titel, nur_nachhaltig=False):
    """Erfuellt eine Aktie (dict mit div/div_q) den Dividenden-Filter?"""
    regel = FILTER.get(filter_titel)
    d = _z(w.get("div"))
    if regel:
        art, grenze = regel
        if art == "keine" and not (d is not None and d <= 0):
            return False
        if art == "ab" and not (d is not None and d >= grenze):
            return False
    if nur_nachhaltig and nachhaltigkeit(w.get("div"), w.get("div_q")) not in ("nachhaltig", "solide"):
        return False
    return True


def text(div, div_q=None):
    """Kurzer Anzeigetext, z. B. 'Hoch (4–6 %) · nachhaltig'."""
    k = kategorie(div)
    if k is None:
        return "unbekannt"
    n = nachhaltigkeit(div, div_q)
    return TITEL[k].split(" (")[0] + (f" · {n}" if n else "")


def uebersicht(werte):
    """[{schluessel, titel, anzahl, schnitt_punkte, nachhaltig, bester}] je Kategorie (nur belegte)."""
    je = {}
    for w in werte:
        k = kategorie(w.get("div"))
        if k:
            je.setdefault(k, []).append(w)
    aus = []
    for k, t, _, _ in KATEGORIEN:
        liste = je.get(k) or []
        if not liste:
            continue
        aus.append({"schluessel": k, "titel": t, "anzahl": len(liste),
                    "schnitt_punkte": sum(_z(w.get("gesamt")) or 0 for w in liste) / len(liste),
                    "nachhaltig": sum(1 for w in liste if nachhaltigkeit(w.get("div"), w.get("div_q"))
                                      in ("nachhaltig", "solide")),
                    "bester": max(liste, key=lambda w: _z(w.get("gesamt")) or 0)})
    return aus
