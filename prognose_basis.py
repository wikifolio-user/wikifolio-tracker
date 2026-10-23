"""Prognose-Basis der Zukunfts-Prognose: eigene Liste je Benutzer (Werte aus der Top-500-Liste uebernehmen,
wieder entfernen). Ohne gespeicherte Liste gelten die Werte der Beobachtungsliste (bisheriges Verhalten)."""
import re

PFAD = "state/prognose_basis.json"
MAX_EINTRAEGE = 30                 # je Eintrag laedt die Prognose Kurs + Historie
ARTEN = {"wikifolio": "wikifolio", "etf": "ETF", "aktie": "Aktie"}
_WKN = re.compile(r"^(?=.*\d)[A-Z0-9]{6}$")


def _art(typ, kat=""):
    t = f"{typ} {kat}".lower()
    if "wikifolio" in t:
        return "wikifolio"
    if "aktie" in t or "stock" in t or "share" in t:
        return "aktie"
    if any(w in t for w in ("etf", "etp", "etc", "etn", "fonds", "fund", "index")):
        return "etf"
    return None


def top500_optionen(katalog_teile, ids):
    """Waehlbare Werte der Top-500-Daten (state/planer/katalog_gross_*.json) mit Kurs-ID (scanner.top500_ids).
    -> [{name, wkn, isin, art, instrument_id oder None}] ohne Doppelte, nach Name sortiert."""
    aus, gesehen = [], set()
    for d in katalog_teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            w = dict(zip(felder, z))
            art = _art(w.get("typ"), w.get("kat"))
            name = str(w.get("name") or "").strip()
            if not art or not name:
                continue
            kennung = str(w.get("kennung") or "").strip().upper()
            wkn = kennung if _WKN.match(kennung) else ""
            isin = str(w.get("isin") or "").strip().upper()
            schluessel = {k for k in (wkn, isin) if k} or {"N:" + name.lower()}
            if schluessel & gesehen:
                continue
            gesehen |= schluessel
            iid = next((ids[k] for k in (wkn, isin, kennung) if k and k in ids), None)
            aus.append({"name": name, "wkn": wkn, "isin": isin, "art": art, "instrument_id": iid})
    aus.sort(key=lambda w: w["name"].lower())
    return aus


def schluessel(w):
    return str(w.get("isin") or w.get("wkn") or w.get("name") or "")


def enthalten(liste, w):
    """Ist der Wert schon in der Liste (gleiche Kurs-ID, WKN oder ISIN)?"""
    kenn = {str(k).upper() for k in (w.get("wkn"), w.get("isin")) if k}
    for e in liste or []:
        if w.get("instrument_id") and e.get("instrument_id") == w.get("instrument_id"):
            return True
        if kenn & {str(k).upper() for k in (e.get("wkn"), e.get("isin")) if k}:
            return True
    return False


def eintrag(w, jetzt):
    """Neuer Listeneintrag aus einer Top-500-Option (instrument_id muss gesetzt sein)."""
    return {"id": f"prog-{int(jetzt)}-{int(w['instrument_id'])}", "name": w["name"],
            "wkn": w.get("wkn") or w.get("isin") or "", "isin": w.get("isin") or "",
            "instrument_id": int(w["instrument_id"])}


def hinzufuegen(liste, neu):
    """-> neue Liste oder None (schon enthalten / Liste voll / ohne Kurs-ID)."""
    liste = list(liste or [])
    if not neu.get("instrument_id") or enthalten(liste, neu) or len(liste) >= MAX_EINTRAEGE:
        return None
    return liste + [neu]


def entfernen(liste, eintrag_id):
    """-> neue Liste oder None (nicht gefunden)."""
    liste = list(liste or [])
    neu = [e for e in liste if e.get("id") != eintrag_id]
    return neu if len(neu) < len(liste) else None


def start_aus_beobachtung(beobachtung):
    """Erste Liste: die Werte der Beobachtungsliste (mit Kurs-ID) - so bleibt die bisherige Auswahl erhalten."""
    return [{"id": e.get("id") or f"prog-beob-{i}", "name": e.get("name") or e.get("wkn") or "Wert",
             "wkn": e.get("wkn") or "", "isin": e.get("isin") or "", "instrument_id": e["instrument_id"]}
            for i, e in enumerate(beobachtung or []) if e.get("instrument_id")][:MAX_EINTRAEGE]
