"""Kurssuche ueber mehrere Quellen fuer den Durchschnittskurs-Rechner - ohne Streamlit (get() von aussen).

1. Eingabe pruefen: ISIN (mit Pruefziffer, Vorschlag bei typischen Tippfehlern wie O statt 0), WKN oder Name.
2. Quellen:
   - Lang & Schwarz (ls-tc.de) ueber die vorhandene Instrumentensuche der App (Live-Kurs des Emittenten)
   - onvista (oeffentliche JSON-Schnittstelle der Website, wie produktdaten.py): Aktien, Fonds/ETFs, Indizes und
     Zertifikate - je Boerse der letzte Kurs, bei Zertifikaten Geld/Brief des Emittenten
3. Jede Quelle meldet, was sie gefunden hat oder warum nicht - so ist nachvollziehbar, welche Pruefung griff.
Keine offizielle API: aendert sich die Schnittstelle, liefert die Quelle "nicht erreichbar" und die Eingabe von Hand
bleibt moeglich."""
import datetime
import re
from zoneinfo import ZoneInfo

import produktdaten as PD

ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
WKN = re.compile(r"^[A-Z0-9]{6}$")
PFADE = {"STOCK": "stocks", "FUND": "funds", "INDEX": "indices", "DERIVATIVE": "derivatives", "BOND": "bonds",
         "CURRENCY": "currencies", "PRECIOUS_METAL": "preciousMetals"}
TYPEN = {"KNOCKOUT_CERTIFICATE": "Knock-out-Zertifikat", "WARRANT": "Optionsschein", "STOCK": "Aktie",
         "ETF": "ETF", "FUND": "Fonds", "INDEX": "Index", "BOND": "Anleihe", "CERTIFICATE": "Zertifikat",
         "FACTOR_CERTIFICATE": "Faktor-Zertifikat", "DISCOUNT_CERTIFICATE": "Discount-Zertifikat",
         "BONUS_CERTIFICATE": "Bonus-Zertifikat", "ETC": "ETC", "ETN": "ETN", "DERIVATIVE": "Derivat"}
LIVE_MIN = 20                      # juenger als 20 Minuten = aktuell


# ---------------------------------------------------------------------------------------------------- Eingabe
def isin_gueltig(isin):
    """Pruefziffer nach ISO 6166 (Buchstaben -> Zahlen, Luhn-Verfahren)."""
    if not ISIN.match(isin or ""):
        return False
    ziffern = "".join(str(int(c, 36)) for c in isin[:-1])
    summe = 0
    for i, z in enumerate(reversed(ziffern)):
        n = int(z) * (2 if i % 2 == 0 else 1)
        summe += n // 10 + n % 10
    return (10 - summe % 10) % 10 == int(isin[-1])


def _varianten(isin):
    """Typische Verwechslungen O/0, I/1, S/5, B/8 im Teil nach dem Laendercode."""
    tausch = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B"}
    for i in range(2, 12):
        c = isin[i]
        if c in tausch:
            v = isin[:i] + tausch[c] + isin[i + 1:]
            if ISIN.match(v) and isin_gueltig(v):
                yield v


def eingabe_pruefen(text):
    """-> {"art": isin/wkn/name/leer, "wert", "hinweise": [..], "vorschlag": ISIN oder None}"""
    roh = str(text or "").strip()
    kompakt = re.sub(r"[\s\-./]", "", roh).upper()
    if not roh:
        return {"art": "leer", "wert": "", "hinweise": [], "vorschlag": None}
    if len(kompakt) == 12 and re.match(r"^[A-Z]{2}", kompakt) and re.match(r"^[A-Z0-9]{12}$", kompakt):
        if isin_gueltig(kompakt):
            return {"art": "isin", "wert": kompakt, "hinweise": ["ISIN gültig (Prüfziffer stimmt)."], "vorschlag": None}
        vorschlag = next(_varianten(kompakt), None)
        h = ["Die Prüfziffer dieser ISIN stimmt nicht – vermutlich vertippt."]
        if vorschlag:
            h.append(f"Meintest du {vorschlag}? (O/0, I/1, S/5 oder B/8 vertauscht)")
        return {"art": "isin", "wert": kompakt, "hinweise": h, "vorschlag": vorschlag}
    if WKN.match(kompakt) and any(c.isdigit() for c in kompakt):
        h = [] if kompakt == roh.upper() else [f"Als WKN {kompakt} gesucht (Leerzeichen entfernt)."]
        return {"art": "wkn", "wert": kompakt, "hinweise": h, "vorschlag": None}
    if len(roh) < 2:
        return {"art": "leer", "wert": "", "hinweise": ["Bitte mindestens 2 Zeichen eingeben."], "vorschlag": None}
    return {"art": "name", "wert": roh, "hinweise": [], "vorschlag": None}


# ---------------------------------------------------------------------------------------------------- onvista
def onvista_suchen(begriff, get, maximal=8):
    """-> [{"quelle": "onvista", "name", "isin", "wkn", "typ", "pfad"}] (Fehler: QuelleFehler)."""
    d = PD._json(get, f"{PD.API}/instruments/query", {"searchValue": begriff})
    aus = []
    for x in (d.get("list") if isinstance(d, dict) else None) or []:
        if not x.get("isin"):
            continue
        typ = str(x.get("entityType") or "")
        aus.append({"quelle": "onvista", "name": x.get("name") or "", "isin": x.get("isin"), "wkn": x.get("wkn") or "",
                    "typ": x.get("entitySubType") or typ, "pfad": PFADE.get(typ, "")})
        if len(aus) >= maximal:
            break
    return aus


def typ_text(typ):
    t = str(typ or "").upper()
    return TYPEN.get(t) or str(typ or "").replace("_", " ").title()


def _zeit(text):
    try:
        z = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return z if z.tzinfo else z.replace(tzinfo=datetime.timezone.utc)


def _kurs_eintrag(q, art="Kurs"):
    try:
        k = float(q.get("last"))
    except (TypeError, ValueError):
        return None
    if not k or k <= 0 or k != k:
        return None
    return {"boerse": (q.get("market") or {}).get("name") or "", "kurs": k, "waehrung": q.get("isoCurrency") or "",
            "zeit": _zeit(q.get("datetimeLast")), "art": art,
            "vortag": float(q["previousLast"]) if isinstance(q.get("previousLast"), (int, float)) else None}


def onvista_kurse(kandidat, get):
    """Kurse eines onvista-Treffers. Zertifikate: Geld und Brief; sonst je Boerse der letzte Kurs.
    -> Liste, beste zuerst (Euro, juengster Kurs)."""
    pfade = [kandidat.get("pfad")] if kandidat.get("pfad") else []
    pfade += [p for p in ("derivatives", "stocks", "funds", "indices") if p not in pfade]
    letzter = None
    for pfad in pfade:
        try:
            d = PD._json(get, f"{PD.API}/{pfad}/ISIN:{kandidat['isin']}/snapshot")
        except PD.ProduktFehler as ex:
            letzter = ex
            continue
        if not isinstance(d, dict):
            continue
        aus = []
        if d.get("bid") or d.get("ask"):                          # Zertifikat: Geld/Brief des Emittenten
            for teil, art in (("bid", "Geld"), ("ask", "Brief")):
                e = _kurs_eintrag(d.get(teil) or {}, art)
                if e:
                    aus.append(e)
        for q in ((d.get("quoteList") or {}).get("list") or []) or ([d.get("quote")] if d.get("quote") else []):
            e = _kurs_eintrag(q or {})
            if e:
                aus.append(e)
        if aus:
            return sortieren(aus)
    if isinstance(letzter, PD.ProduktFehler):
        raise letzter
    raise PD.ProduktFehler("Zu diesem Wert liefert onvista keinen Kurs.")


def sortieren(kurse, jetzt=None):
    """Euro vor Fremdwaehrung, Geld vor Brief (Wert beim Verkauf), juengster Kurs zuerst."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    alt = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    return sorted(kurse, key=lambda k: (k["waehrung"] != "EUR", k["art"] == "Brief",
                                        -((k["zeit"] or alt).timestamp())))


def alter_text(zeit, jetzt=None):
    if not zeit:
        return "Zeit unbekannt"
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    m = (jetzt - zeit).total_seconds() / 60
    lokal = zeit.astimezone(ZoneInfo("Europe/Berlin"))
    if m < LIVE_MIN:
        return f"aktuell ({lokal:%H:%M} Uhr)"
    if m < 24 * 60:
        return f"Stand {lokal:%H:%M} Uhr"
    return f"Stand {lokal:%d.%m. %H:%M}"


# ---------------------------------------------------------------------------------------------------- Zusammenfuehren
def kandidaten(ls_treffer, ov_treffer):
    """Treffer beider Quellen vereinen (gleiche ISIN nur einmal, mit beiden Quellen)."""
    aus, je_isin = [], {}
    for t in ls_treffer or []:
        k = {"name": t.get("name") or "", "isin": t.get("isin") or "", "wkn": t.get("wkn") or "",
             "typ": t.get("kategorie") or "", "ls_id": t.get("instrument_id"), "onvista": None}
        aus.append(k)
        if k["isin"]:
            je_isin[k["isin"]] = k
    for t in ov_treffer or []:
        if t["isin"] in je_isin:
            je_isin[t["isin"]]["onvista"] = t
            je_isin[t["isin"]]["typ"] = je_isin[t["isin"]]["typ"] or t["typ"]
        else:
            k = {"name": t["name"], "isin": t["isin"], "wkn": t["wkn"], "typ": t["typ"], "ls_id": None, "onvista": t}
            aus.append(k)
            je_isin[t["isin"]] = k
    return aus


def passend(kandidaten_liste, pruefung):
    """Bei ISIN/WKN genau passende Treffer zuerst."""
    w = pruefung["wert"].upper()

    def schl(k):
        return 0 if w in (str(k["isin"]).upper(), str(k["wkn"]).upper()) else 1
    return sorted(kandidaten_liste, key=schl)
