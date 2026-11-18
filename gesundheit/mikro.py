"""Mikronaehrstoffe eines Tages: Lebensmittel + Getraenke + eingenommene Supplements = Tagesaufnahme.

Herkunft je Naehrstoff bleibt erhalten (Lebensmittel / Getraenke / Supplements), ebenso, fuer wie viele erfasste
Lebensmittel der Wert bekannt ist (unbekannt ist nicht 0). Ohne Streamlit, getestet in test_gesundheit.py.
"""
from . import naehrstoffe as N
from . import rechnen as R
from . import referenz as F

QUELLEN = ("Lebensmittel", "Getränke", "Supplements")
MIN_MIKRO = 3       # ab so vielen bekannten Mikronaehrstoffen gilt ein Lebensmittel als "mit Mikronaehrstoffdaten"


def _quelle(e):
    return "Getränke" if e.get("basis") == "ml" else "Lebensmittel"


def tag_naehrstoffe(t, ids=None):
    """Tag (speicher.tag_aus) -> {naehrstoff: {"wert", "quellen": {Quelle: wert}, "bekannt", "anzahl",
    "top": [(Name, wert), ...]}} - bekannt/anzahl beziehen sich auf die erfassten Lebensmittel und Getraenke."""
    ids = ids or N.MIKRO
    essen = t.get("essen") or []
    nw = [R.naehrwerte(e.get("pro100"), e.get("gramm")) for e in essen]
    supps = [s for s in t.get("supplements") or [] if s.get("status") == "eingenommen"]
    aus = {}
    for n in ids:
        quellen = {q: 0.0 for q in QUELLEN}
        bekannt, beitraege = 0, []
        for e, w in zip(essen, nw):
            if w.get(n) is not None:
                bekannt += 1
                quellen[_quelle(e)] += w[n]
                beitraege.append((e.get("name") or "?", w[n]))
        for s in supps:
            v = (s.get("inhalt") or {}).get(n)
            if v:
                quellen["Supplements"] += float(v)
                beitraege.append((s.get("name") or "Supplement", float(v)))
        top = {}
        for name, v in beitraege:
            top[name] = top.get(name, 0.0) + v
        aus[n] = {"wert": sum(quellen.values()), "quellen": quellen, "bekannt": bekannt, "anzahl": len(essen),
                  "top": sorted(((k, v) for k, v in top.items() if v > 0), key=lambda x: -x[1])[:5]}
    return aus


def abdeckung(wert, ziel):
    """Anteil am Referenzwert in Prozent (None ohne Referenzwert)."""
    return None if not ziel else float(wert) / float(ziel) * 100


def datenqualitaet(t):
    """Anteil der erfassten Lebensmittel/Getraenke mit Mikronaehrstoffdaten (mind. MIN_MIKRO Werte) in Prozent,
    None ohne Eintraege."""
    essen = t.get("essen") or []
    if not essen:
        return None
    mit = sum(1 for e in essen if sum(1 for n in N.MIKRO if (e.get("pro100") or {}).get(n) is not None) >= MIN_MIKRO)
    return mit / len(essen) * 100


def uebersicht(t, profil, ids, heute_alter=None):
    """-> Liste je Naehrstoff: {"id", "name", "einheit", "wert", "ziel", "ul", "prozent", "ref", "daten", ...}"""
    werte = tag_naehrstoffe(t, ids)
    alter = heute_alter if heute_alter is not None else 40
    aus = []
    for n in ids:
        ref = F.suchen(n, (profil or {}).get("geschlecht", "x"), alter)
        w = werte[n]
        aus.append({"id": n, "name": N.NAEHRSTOFFE[n].name, "einheit": N.NAEHRSTOFFE[n].einheit, **w,
                    "ziel": ref.ziel if ref else None, "ul": ref.ul if ref else None, "ref": ref,
                    "prozent": abdeckung(w["wert"], ref.ziel) if ref else None})
    return aus


def durchschnitt(tage, n):
    """Mittelwert eines Naehrstoffs ueber Tage MIT Eintraegen (Tage ohne Erfassung zaehlen nicht als 0).
    tage: Liste von Tag-dicts. -> (mittelwert, anzahl_tage) oder (None, 0)."""
    werte = [tag_naehrstoffe(t, [n])[n]["wert"] for t in tage
             if (t.get("essen") or any(s.get("status") == "eingenommen" for s in t.get("supplements") or []))]
    return (sum(werte) / len(werte), len(werte)) if werte else (None, 0)
