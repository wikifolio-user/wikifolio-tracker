"""Zentrale Suche im Gesundheitsbereich - ohne Streamlit.

Ein Suchbegriff findet alles Passende auf einmal, z. B. "Magnesium": den Naehrstoff (Tageswert), Lebensmittel,
die viel davon enthalten, und Supplements mit Magnesium; "Banane": das Lebensmittel zum direkten Eintragen.
"""
from . import foto as FO
from . import lebensmittel as L
from . import naehrstoffe as N
from . import sport as SP


def naehrstoffe(begriff):
    """Begriff -> passende Naehrstoff-IDs (Anzeigename oder gaengige Bezeichnung, auch Wortanfang)."""
    q = L._norm(begriff)
    if len(q) < 2:
        return []
    treffer = []
    for nid, n in N.NAEHRSTOFFE.items():
        namen = [L._norm(n.name)] + [k for k, v in FO.SYNONYME.items() if v == nid]
        if any(x.startswith(q) or f" {q}" in f" {x}" for x in namen):
            treffer.append(nid)
    nid = FO.naehrstoff_id(begriff)
    if nid and nid not in treffer:
        treffer.insert(0, nid)
    return [t for t in treffer if t in N.MIKRO or t in ("protein", "ballast", "zucker")][:3]


def reich_an(nid, alle, limit=5):
    """Lebensmittel mit dem hoechsten Gehalt je 100 g/ml (nur mit bekanntem Wert)."""
    mit = [lm for lm in alle if (lm.get("pro100") or {}).get(nid)]
    return sorted(mit, key=lambda lm: -float(lm["pro100"][nid]))[:limit]


def suchen(begriff, alle, supplements=(), vorlagen=(), limit=6):
    """-> {"naehrstoffe": [id], "lebensmittel": [lm], "reich_an": {id: [lm]}, "supplements": [sup],
    "vorlagen": [vorlage], "sport": [art]} - leere Gruppen bleiben leer."""
    q = L._norm(begriff)
    leer = {"naehrstoffe": [], "lebensmittel": [], "reich_an": {}, "supplements": [], "vorlagen": [], "sport": []}
    if len(q) < 2:
        return leer
    nst = naehrstoffe(begriff)
    aktive = [s for s in supplements or () if isinstance(s, dict) and s.get("aktiv", True)]
    sups = [s for s in aktive if q in L._norm(s.get("name")) or
            any(z.get("n") in nst for z in s.get("inhalt") or [])]
    return {"naehrstoffe": nst,
            "lebensmittel": [] if nst and not L.suchen(begriff, alle, limit=1) else L.suchen(begriff, alle, limit=limit),
            "reich_an": {n: reich_an(n, alle) for n in nst[:1]},
            "supplements": sups[:limit],
            "vorlagen": [v for v in vorlagen or () if q in L._norm(v.get("name"))][:limit],
            "sport": [a for a, x in SP.AKTIVITAETEN.items() if q in L._norm(x["name"])][:3]}
