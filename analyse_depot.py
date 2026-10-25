"""Analyse-Depot: eigenes, vom echten Depot getrenntes Depot fuer die Depot-Analyse (z. B. das Depot bei der
Bank). Rechenkern ohne Streamlit: Datenmodell, Pruefung, Schnelleingabe, Bestand fuer depot_analyse.

Gespeichert je Benutzer in state/analyse_depot.json:
{"positionen": [{id, name, wkn, isin, instrument_id, art, stueck, kaufkurs, kaufdatum}],
 "sparplan": {"rate", "ziel" (Positions-id oder ""), "start"}, "entnahme": {"rate", "start"}, "stand"}"""
import datetime
import math
import re
import uuid

import depot_analyse as D

PFAD = "state/analyse_depot.json"
ARTEN = {"": "automatisch", "aktie": "Aktie", "etf": "ETF", "wikifolio": "wikifolio", "fonds": "Fonds",
         "sonstiges": "Sonstiges"}


def _z(x):
    return D._zahl_de(x)


def leer():
    return {"positionen": [], "sparplan": {"rate": 0.0, "ziel": "", "start": None},
            "entnahme": {"rate": 0.0, "start": None}, "stand": None}


def neue_id():
    return f"ad-{uuid.uuid4().hex[:10]}"


def position(name, stueck, kaufkurs=None, kaufdatum=None, wkn="", isin="", instrument_id=None, art="", pid=None):
    """Eine gepruefte Position -> (dict, fehler-text oder None)."""
    stueck = _z(stueck)
    kk = _z(kaufkurs)
    if not str(name or "").strip():
        return None, "Name fehlt"
    if stueck is None or stueck <= 0:
        return None, f"{name}: Stückzahl muss größer als 0 sein"
    if kk is not None and kk < 0:
        return None, f"{name}: Kaufkurs darf nicht negativ sein"
    dat = D._datum(kaufdatum) if kaufdatum else None
    if dat and dat > datetime.date.today():
        return None, f"{name}: Kaufdatum liegt in der Zukunft"
    iid = None
    try:
        iid = int(instrument_id) if instrument_id not in (None, "", 0) and not (
            isinstance(instrument_id, float) and math.isnan(instrument_id)) else None
    except (TypeError, ValueError):
        iid = None
    return {"id": pid or neue_id(), "name": str(name).strip(), "wkn": str(wkn or "").strip().upper(),
            "isin": str(isin or "").strip().upper(), "instrument_id": iid, "art": art if art in ARTEN else "",
            "stueck": float(stueck), "kaufkurs": float(kk) if kk is not None else None,
            "kaufdatum": dat.isoformat() if dat else None}, None


def bereinigen(daten):
    """Gespeicherten Stand robust einlesen (fehlende Felder, alte Versionen)."""
    aus = leer()
    for p in (daten or {}).get("positionen") or []:
        q, f = position(p.get("name"), p.get("stueck"), p.get("kaufkurs"), p.get("kaufdatum"), p.get("wkn"),
                        p.get("isin"), p.get("instrument_id"), p.get("art") or "", p.get("id"))
        if q:
            aus["positionen"].append(q)
    sp = (daten or {}).get("sparplan") or {}
    aus["sparplan"] = {"rate": max(_z(sp.get("rate")) or 0.0, 0.0), "ziel": str(sp.get("ziel") or ""),
                       "start": sp.get("start") or None}
    en = (daten or {}).get("entnahme") or {}
    aus["entnahme"] = {"rate": max(_z(en.get("rate")) or 0.0, 0.0), "start": en.get("start") or None}
    if aus["sparplan"]["ziel"] not in {p["id"] for p in aus["positionen"]}:
        aus["sparplan"]["ziel"] = ""
    aus["stand"] = (daten or {}).get("stand")
    return aus


SCHNELL_HILFE = ("Eine Position je Zeile: Kennung (ISIN, WKN oder Name); Stück; Kaufkurs; Kaufdatum – "
                 "Trennzeichen ; oder Tab, Kaufkurs und Datum optional. Beispiel:\n"
                 "IE00B4L5Y983; 25; 85,40; 15.03.2024\nSiemens; 10\nA0RPWH\t5\t70,10")


def schnelleingabe(text):
    """Mehrzeilige Eingabe -> ([{kennung, stueck, kaufkurs, kaufdatum}], fehler)."""
    zeilen, fehler = [], []
    for nr, z in enumerate(str(text or "").splitlines(), 1):
        z = z.strip()
        if not z or z.startswith("#"):
            continue
        teile = [t.strip() for t in re.split(r"[;\t|]", z)]
        if len(teile) == 1:                       # "ISIN 25" mit Leerzeichen
            m = re.match(r"^(.*\S)\s+(\d+(?:[.,]\d+)?)$", z)
            teile = [m.group(1), m.group(2)] if m else teile
        kenn = teile[0]
        stueck = _z(teile[1]) if len(teile) > 1 else None
        if not kenn:
            fehler.append(f"Zeile {nr}: Kennung fehlt")
            continue
        if stueck is None or stueck <= 0:
            fehler.append(f"Zeile {nr} ({kenn}): Stückzahl fehlt oder ist nicht größer als 0")
            continue
        kk = _z(teile[2]) if len(teile) > 2 and teile[2] else None
        dat = D._datum(teile[3]) if len(teile) > 3 and teile[3] else None
        if len(teile) > 3 and teile[3] and dat is None:
            fehler.append(f"Zeile {nr} ({kenn}): Datum „{teile[3]}“ nicht erkannt – ohne Datum übernommen")
        zeilen.append({"kennung": kenn, "stueck": stueck, "kaufkurs": kk, "kaufdatum": dat})
    return zeilen, fehler


def zusammenfuehren(positionen, neu):
    """Neue Positionen anhaengen; gleicher Wert (Kursquelle/ISIN/WKN) wird zusammengelegt
    (Stueck addiert, Kaufkurs als gewichteter Durchschnitt, fruehestes Datum)."""
    aus = [dict(p) for p in positionen]

    def gleich(a, b):
        if a.get("instrument_id") and b.get("instrument_id"):
            return a["instrument_id"] == b["instrument_id"]
        return any(a.get(k) and a.get(k) == b.get(k) for k in ("isin", "wkn"))

    for n in neu:
        alt = next((p for p in aus if gleich(p, n)), None)
        if not alt:
            aus.append(dict(n))
            continue
        st_ = alt["stueck"] + n["stueck"]
        if alt.get("kaufkurs") is not None and n.get("kaufkurs") is not None:
            alt["kaufkurs"] = (alt["stueck"] * alt["kaufkurs"] + n["stueck"] * n["kaufkurs"]) / st_
        elif alt.get("kaufkurs") is None:
            alt["kaufkurs"] = n.get("kaufkurs")
        daten = [d for d in (alt.get("kaufdatum"), n.get("kaufdatum")) if d]
        alt["kaufdatum"] = min(daten) if daten else None
        alt["stueck"] = st_
    return aus


def bestand(depot, kurs_je_id, hist_je_id=None):
    """Positionen fuer depot_analyse (gleiches Format wie die Depot-Berechnung in app.py).
    kurs_je_id: {instrument_id: (kurs, vortag)}; ohne Kurs -> ohne_kurs (nicht bewertet)."""
    aus = []
    for p in depot.get("positionen") or []:
        kurs, vortag = (kurs_je_id or {}).get(p.get("instrument_id")) or (None, None)
        einstand = p["stueck"] * p["kaufkurs"] if p.get("kaufkurs") is not None else None
        q = {"name": p["name"], "wkn": p.get("wkn") or p.get("isin") or "", "isin": p.get("isin") or "",
             "instrument_id": p.get("instrument_id"), "stueck": p["stueck"], "kurs": kurs, "vortag": vortag,
             "wert": (kurs or 0.0) * p["stueck"], "einstand": einstand,
             "kaufdatum": D._datum(p["kaufdatum"]) if p.get("kaufdatum") else None,
             "ist_wikifolio": p.get("art") == "wikifolio" or str(p.get("wkn") or "").upper().startswith("LS9"),
             "hist": (hist_je_id or {}).get(p.get("instrument_id")), "ohne_kurs": not kurs, "ad_id": p["id"]}
        if p.get("art"):
            q["art_vorgabe"] = p["art"]
        aus.append(q)
    return aus


def monatsplan(depot):
    """Netto-Zufluss je Monat (Sparrate minus Entnahme) fuer die Modellrechnung."""
    return (depot.get("sparplan") or {}).get("rate", 0.0) - (depot.get("entnahme") or {}).get("rate", 0.0)
