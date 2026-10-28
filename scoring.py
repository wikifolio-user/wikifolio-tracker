"""Bewertung einzelner Werte der Top-500-Liste (Menuepunkt "Bewertung") - reine Rechenlogik ohne Streamlit.

Grundsaetze:
- Jede Kennzahl wird als Perzentil-Rang innerhalb der Top-500-Daten normalisiert (0-100 = "besser als x %"),
  Aktien nur unter Aktien, ETFs unter ETFs, Wikifolios unter Wikifolios.
- Bewertungskennzahlen (KGV, EV/EBIT ...) werden sektorrelativ verglichen (gleiche Branche, sofern mindestens
  MIN_SEKTOR Werte vorliegen - sonst gegen alle Aktien).
- Die Richtung ist je Kennzahl hinterlegt (niedriges KGV = gut, hohe Marge = gut).
- Fehlende Kennzahlen sind "n/a" und fallen aus der Gewichtung heraus - sie werden nie als 0 gewertet.
- Teilscore = gewichteter Mittelwert der vorhandenen Kennzahl-Perzentile einer Kategorie,
  Gesamtscore = gewichteter Mittelwert der vorhandenen Teilscores (Gewichte werden neu verteilt).

Datenquellen (Watchlist-/Top-500-Agent, Branch app-state, taeglich):
  state/planer/katalog_gross_*.json   Katalog: Aktien, ETFs, Wikifolios (Kursentwicklung, Vola, Rueckgang ...)
  state/qualitaet/alle_*.json         Fundamentaldaten aller bewerteten Aktien (Kennzahlen + Qualitaets-Score)
  state/qualitaet/details_*.json      weitere Kennzahlen eines Teils der Aktien (KGV, PEG, ROE, Vola ...)
  state/top50_alle_*.json             Kursentwicklung 1 Tag ... 10 Jahre aller Aktien der Ranglisten
"""
import bisect
import difflib
import math
import re
import unicodedata

# ---------------------------------------------------------------------------
# KONFIGURATION - Gewichtungen und Kennzahlen (leicht anpassbar)
# ---------------------------------------------------------------------------
# Gewicht der Kategorien im Gesamtscore (%). Fehlt eine Kategorie, werden die uebrigen hochgerechnet.
GEWICHTE = {
    "aktie": {"bewertung": 25, "qualitaet": 20, "wachstum": 15, "stabilitaet": 15, "dividende": 10, "momentum": 15},
    "etf": {"rendite": 40, "momentum": 15, "risiko": 35, "dividende": 10},
    "wikifolio": {"rendite": 45, "momentum": 15, "risiko": 40},
}
KATEGORIEN = {
    "bewertung": "Bewertung", "qualitaet": "Qualität & Profitabilität", "wachstum": "Wachstum",
    "stabilitaet": "Finanzielle Stabilität", "dividende": "Dividende", "momentum": "Momentum & Technik",
    "rendite": "Rendite (langfristig)", "risiko": "Risiko",
}

# Kennzahl: (Kategorie, Bezeichnung, Richtung (+1 hoeher besser / -1 niedriger besser), Format, Gewicht in der
#            Kategorie, sektorrelativ, Klassen)
KENNZAHLEN = {
    # --- Aktien: Bewertung (sektorrelativ) ---
    "fkgv": ("bewertung", "KGV (erwartet)", -1, "x", 1.0, True, "a"),
    "kgv": ("bewertung", "KGV (aktuell)", -1, "x", 0.7, True, "a"),
    "peg": ("bewertung", "PEG-Ratio", -1, "x", 0.7, True, "a"),
    "ev_ebit": ("bewertung", "EV/EBIT", -1, "x", 1.0, True, "a"),
    "ev_ebitda": ("bewertung", "EV/EBITDA", -1, "x", 0.7, True, "a"),
    "fcfy": ("bewertung", "Free-Cashflow-Rendite", +1, "pct", 1.0, True, "a"),
    "mos": ("bewertung", "Sicherheitsmarge (DCF)", +1, "pct", 0.8, False, "a"),
    # --- Qualitaet & Profitabilitaet ---
    "roic": ("qualitaet", "Kapitalrendite (ROIC)", +1, "pct", 1.0, False, "a"),
    "roe": ("qualitaet", "Eigenkapitalrendite (ROE)", +1, "pct", 0.7, False, "a"),
    "om": ("qualitaet", "Operative Marge", +1, "pct", 1.0, False, "a"),
    "gm": ("qualitaet", "Bruttomarge", +1, "pct", 0.5, False, "a"),
    "fm": ("qualitaet", "Free-Cashflow-Marge", +1, "pct", 1.0, False, "a"),
    # --- Wachstum ---
    "g_ums": ("wachstum", "Umsatzwachstum p. a.", +1, "pct", 1.0, False, "a"),
    "g_eps": ("wachstum", "Gewinnwachstum je Aktie p. a.", +1, "pct", 1.0, False, "a"),
    "g_fcf": ("wachstum", "Free-Cashflow-Wachstum p. a.", +1, "pct", 0.6, False, "a"),
    "g_fcfps": ("wachstum", "FCF-Wachstum je Aktie p. a.", +1, "pct", 0.6, False, "a"),
    # --- Finanzielle Stabilitaet ---
    "nde": ("stabilitaet", "Nettoschulden / EBITDA", -1, "nde", 1.0, False, "a"),
    "zinsd": ("stabilitaet", "Zinsdeckung (EBIT / Zinsen)", +1, "x", 0.7, False, "a"),
    "akt": ("stabilitaet", "Verwässerung (Aktienanzahl p. a.)", -1, "pct", 0.6, False, "a"),
    # --- Dividende ---
    "div": ("dividende", "Dividendenrendite", +1, "pct", 1.0, False, "ae"),
    "div_q": ("dividende", "Ausschüttungsquote", -1, "pct", 0.5, False, "a"),
    # --- Momentum & Technik ---
    "m1": ("momentum", "Kurs 1 Monat", +1, "pct", 0.5, False, "a"),
    "p6": ("momentum", "Kurs 6 Monate", +1, "pct", 1.0, False, "a"),
    "p12": ("momentum", "Kurs 12 Monate", +1, "pct", 1.0, False, "aew"),
    "p36": ("momentum", "Kurs 3 Jahre", +1, "pct", 0.6, False, "a"),
    "vola": ("momentum", "Schwankung (Vola p. a.)", -1, "pct0", 0.5, False, "a"),
    "dd": ("momentum", "Größter Rückgang", +1, "pct0", 0.5, False, "a"),
    # --- ETFs / Wikifolios ---
    "r3": ("rendite", "Rendite 3 J. p. a.", +1, "pct", 0.8, False, "ew"),
    "r5": ("rendite", "Rendite 5 J. p. a.", +1, "pct", 1.0, False, "ew"),
    "r10": ("rendite", "Rendite 10 J. p. a.", +1, "pct", 0.8, False, "ew"),
    "vola_k": ("risiko", "Schwankung (Vola p. a.)", -1, "pct0", 1.0, False, "ew"),
    "maxdd": ("risiko", "Größter Rückgang", +1, "pct0", 1.0, False, "ew"),
    "jahre": ("risiko", "Länge der Historie (Jahre)", +1, "jahre", 0.5, False, "ew"),
}
KLASSE_KUERZEL = {"aktie": "a", "etf": "e", "wikifolio": "w"}
KLASSEN_TEXT = {"aktie": "Aktien", "etf": "ETFs", "wikifolio": "Wikifolios"}

MIN_SEKTOR = 15                # so viele Werte braucht eine Branche fuer den sektorrelativen Vergleich
MIN_VERGLEICH = 5              # darunter kein Perzentil (zu wenig Vergleichswerte)
MIN_KATEGORIEN = {"aktie": 3, "etf": 2, "wikifolio": 2}   # weniger Teilscores -> kein Gesamtscore
GUT, SCHLECHT = 67.0, 33.0     # Einordnung einer Kennzahl nach Perzentil
AMPEL_GRUEN, AMPEL_GELB = 65.0, 45.0
FAZIT_GUENSTIG, FAZIT_TEUER = 62.0, 38.0   # Bewertungs-Teilscore -> unterbewertet / fair / teuer


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def _zahl(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def pro_jahr(gesamt_pct, jahre):
    """Gesamtrendite % ueber `jahre` -> % p. a."""
    v = _zahl(gesamt_pct)
    if v is None or v <= -100:
        return None
    return v if jahre <= 1 else ((1 + v / 100.0) ** (1.0 / jahre) - 1) * 100.0


def _norm(text):
    """Suchtext: Kleinbuchstaben, ohne Akzente/Satzzeichen (Tippfehler-tolerante Suche)."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _vergleichswert(key, wert):
    """Wert fuer den Rang. Negatives KGV/PEG = Verlust bzw. schrumpfender Gewinn -> schlechtester Rang.
    Negative EV-Multiplikatoren sind nicht eindeutig (Verlust ODER mehr Cash als Boersenwert) -> n/a."""
    if wert is None:
        return None
    if key in ("fkgv", "kgv", "peg") and wert <= 0:
        return math.inf
    if key in ("ev_ebit", "ev_ebitda") and wert <= 0:
        return None
    return wert


# ---------------------------------------------------------------------------
# Universum aus den Rohdaten
# ---------------------------------------------------------------------------
def _zeilen(teile):
    """Teil-Dateien {felder, zeilen} -> Liste von Dicts."""
    for d in teile or []:
        f = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            if isinstance(z, (list, tuple)):
                yield dict(zip(f, z))


def _symbol(w, qual, perf, sym_je_isin, sym_je_kennung):
    """Yahoo-Symbol einer Katalog-Aktie: Kennung ist schon das Symbol (Laender-Listen) -> ISIN -> WKN."""
    kennung = str(w.get("kennung") or "").strip()
    if kennung in qual or kennung in perf:
        return kennung
    isin = str(w.get("isin") or "").strip().upper()
    return sym_je_isin.get(isin) or sym_je_kennung.get(kennung.upper()) or ""


def universum(katalog_teile, qualitaet_teile, top50_teile=(), detail_teile=(), yahoo_isin=None):
    """Alle bewertbaren Werte der Top-500-Liste. yahoo_isin: {ISIN: Yahoo-Symbol} (state/top50_yahoo.json "isin").
    Dieselbe Aktie aus mehreren Listen (z. B. DAX-Liste mit WKN und Europa-Liste mit Symbol) wird zusammengefuehrt.
    -> [eintrag] mit eintrag = {id, art, name, ticker, wkn, isin, sektor, kurs, waehrung, tag, k: {kennzahl: wert},
       info: {...}, such}"""
    qual = {str(w.get("s")): w for w in _zeilen(qualitaet_teile) if w.get("s")}
    perf = {str(w.get("s")): w for w in _zeilen(top50_teile) if w.get("s")}
    details = {}
    for d in detail_teile or []:
        for s, w in ((d or {}).get("werte") or {}).items():
            if isinstance(w, dict):
                details[str(s)] = w
    sym_je_kennung = {str(w.get("kennung") or "").upper(): s for s, w in perf.items() if w.get("kennung")}
    sym_je_isin = {str(i).upper(): str(s) for i, s in (yahoo_isin or {}).items() if s}

    aus, je_id = [], {}
    for w in _zeilen(katalog_teile):
        art = str(w.get("typ") or "")
        if art not in KLASSE_KUERZEL:
            continue
        name = str(w.get("name") or "").strip()
        kennung = str(w.get("kennung") or "").strip().upper()
        isin = str(w.get("isin") or "").strip().upper()
        s = _symbol(w, qual, perf, sym_je_isin, sym_je_kennung) if art == "aktie" else ""
        schluessel = s or isin or kennung or name.lower()
        if not name:
            continue
        if schluessel in je_id:                       # Dublette: nur fehlende Kennungen ergaenzen
            e = je_id[schluessel]
            e["isin"] = e["isin"] or isin
            if kennung and kennung != s and not e["wkn"]:
                e["wkn"] = kennung
            e["such"] = _norm(" ".join(x for x in (e["such"], name, kennung, isin) if x))
            continue
        e = {"id": schluessel, "art": art, "name": name, "ticker": s, "wkn": kennung if kennung != s else "",
             "isin": isin, "sektor": "", "kurs": _zahl(w.get("kurs")), "waehrung": "EUR", "tag": None, "k": {},
             "info": {}}
        k = e["k"]
        if art == "aktie":
            q, p, dt = qual.get(s) or {}, perf.get(s) or {}, details.get(s) or {}
            if q.get("name"):
                e["name"] = str(q["name"]).strip()
            e["sektor"] = str(q.get("br") or dt.get("br") or "")
            if _zahl(q.get("kurs")):
                e["kurs"], e["waehrung"] = _zahl(q.get("kurs")), str(q.get("kwae") or "")
            e["tag"] = _zahl(p.get("1T"))
            for key in ("fkgv", "ev_ebit", "fcfy", "mos", "roic", "om", "fm", "g_ums", "g_eps", "g_fcf",
                        "g_fcfps", "akt", "div_q", "p6", "p12", "p36"):
                k[key] = _zahl(q.get(key))
            k["nde"] = -1.0 if q.get("netcash") is True else _zahl(q.get("nde"))
            for key in ("kgv", "peg", "ev_ebitda", "roe", "gm", "zinsd"):
                k[key] = _zahl(dt.get(key))
            # Schwankung und Rueckgang einheitlich aus dem Katalog (gleicher Zeitraum fuer alle Aktien)
            vola = _zahl(w.get("vola"))
            k["vola"] = vola if vola is not None and vola >= 0.5 else None
            k["dd"] = _zahl(w.get("maxdd"))
            k["div"] = next((x for x in (_zahl(q.get("div")), _zahl(p.get("DIV")), _zahl(w.get("div")))
                             if x is not None), None)
            if not k["div"]:
                k["div_q"] = None                         # ohne Dividende ist die Quote bedeutungslos
            k["m1"] = _zahl(p.get("1M"))
            if k.get("p12") is None:
                k["p12"] = _zahl(p.get("1J"))
            e["info"] = {key: q.get(key) for key in ("gesamt", "klasse", "moat", "mgmt", "bew", "risiko", "mcap",
                                                     "netcash") if q.get(key) not in (None, "", False)}
        else:
            e["waehrung"] = "EUR"
            k["p12"] = _zahl(w.get("1J"))
            for key, spalte, j in (("r3", "3J", 3), ("r5", "5J", 5), ("r10", "10J", 10)):
                k[key] = pro_jahr(w.get(spalte), j)
            vola = _zahl(w.get("vola"))
            k["vola_k"] = vola if vola is not None and vola >= 0.5 else None
            k["maxdd"] = _zahl(w.get("maxdd"))
            k["jahre"] = _zahl(w.get("jahre"))
            if art == "etf":
                k["div"] = _zahl(w.get("div"))
        e["k"] = {key: v for key, v in k.items() if v is not None}
        e["such"] = _norm(" ".join(x for x in (name, e["name"], s, kennung, isin) if x))
        je_id[schluessel] = e
        aus.append(e)
    return aus


# ---------------------------------------------------------------------------
# Vergleichsverteilungen (einmal je Datenstand vorberechnen)
# ---------------------------------------------------------------------------
def verteilungen(eintraege):
    """{(art, kennzahl): sortierte Werte} und {(art, kennzahl, sektor): sortierte Werte} fuer sektorrelative."""
    ver = {}
    for e in eintraege:
        for key, wert in e["k"].items():
            d = KENNZAHLEN.get(key)
            if not d or KLASSE_KUERZEL[e["art"]] not in d[6]:
                continue
            v = _vergleichswert(key, wert)
            if v is None:
                continue
            ver.setdefault((e["art"], key), []).append(v)
            if d[5] and e["sektor"]:
                ver.setdefault((e["art"], key, e["sektor"]), []).append(v)
    for liste in ver.values():
        liste.sort()
    return ver


def perzentil(sortiert, wert, richtung):
    """Anteil der Vergleichswerte, die schlechter sind (gleiche zaehlen halb) - 0..100."""
    n = len(sortiert)
    if wert is None or n < MIN_VERGLEICH:
        return None
    unter = bisect.bisect_left(sortiert, wert)
    gleich = bisect.bisect_right(sortiert, wert) - unter
    anteil = (unter + 0.5 * gleich) / n if richtung > 0 else (n - unter - gleich + 0.5 * gleich) / n
    return max(0.0, min(100.0, anteil * 100.0))


def median(sortiert):
    endlich = [x for x in sortiert if math.isfinite(x)]
    if not endlich:
        return None
    m = len(endlich) // 2
    return endlich[m] if len(endlich) % 2 else (endlich[m - 1] + endlich[m]) / 2


# ---------------------------------------------------------------------------
# Bewertung eines Werts
# ---------------------------------------------------------------------------
def einordnung(pz):
    if pz is None:
        return "n/a"
    return "gut" if pz >= GUT else "schlecht" if pz <= SCHLECHT else "neutral"


def ampel(score):
    if score is None:
        return "grau"
    return "gruen" if score >= AMPEL_GRUEN else "gelb" if score >= AMPEL_GELB else "rot"


def bewerten(e, ver):
    """-> {gesamt, ampel, fazit, kategorien: [{key, titel, score, gewicht, anzahl}], kennzahlen: [...],
           staerken, schwaechen, abdeckung}"""
    art = e["art"]
    kz = KLASSE_KUERZEL[art]
    zeilen = []
    for key, d in KENNZAHLEN.items():
        kat, titel, richtung, fmt, gewicht, sektorrel, klassen = d
        if kz not in klassen or kat not in GEWICHTE[art]:
            continue
        wert = e["k"].get(key)
        basis, vergleich = "alle", ver.get((art, key)) or []
        sek = ver.get((art, key, e["sektor"])) if sektorrel and e["sektor"] else None
        if sek and len(sek) >= MIN_SEKTOR:
            basis, vergleich = "sektor", sek
        pz = perzentil(vergleich, _vergleichswert(key, wert), richtung)
        zeilen.append({"key": key, "kategorie": kat, "titel": titel, "wert": wert, "format": fmt,
                       "richtung": richtung, "gewicht": gewicht, "perzentil": pz, "einordnung": einordnung(pz),
                       "median": median(vergleich), "basis": basis, "n": len(vergleich)})
    kategorien = []
    for kat, gew in GEWICHTE[art].items():
        teile = [z for z in zeilen if z["kategorie"] == kat and z["perzentil"] is not None]
        summe_g = sum(z["gewicht"] for z in teile)
        score = sum(z["perzentil"] * z["gewicht"] for z in teile) / summe_g if summe_g else None
        kategorien.append({"key": kat, "titel": KATEGORIEN[kat], "score": score, "gewicht": gew,
                           "anzahl": len(teile), "von": sum(1 for z in zeilen if z["kategorie"] == kat)})
    mit = [c for c in kategorien if c["score"] is not None]
    summe = sum(c["gewicht"] for c in mit)
    gesamt = sum(c["score"] * c["gewicht"] for c in mit) / summe if summe and len(mit) >= MIN_KATEGORIEN[art] \
        else None
    bew = next((c["score"] for c in kategorien if c["key"] == "bewertung"), None)
    if art == "aktie" and bew is not None:
        fazit = "unterbewertet" if bew >= FAZIT_GUENSTIG else "teuer" if bew <= FAZIT_TEUER else "fair bewertet"
    else:
        fazit = None
    vorhanden = [z for z in zeilen if z["perzentil"] is not None]
    staerken = sorted((z for z in vorhanden if z["perzentil"] >= 75), key=lambda z: -z["perzentil"])[:5]
    schwaechen = sorted((z for z in vorhanden if z["perzentil"] <= 25), key=lambda z: z["perzentil"])[:5]
    return {"gesamt": gesamt, "ampel": ampel(gesamt), "fazit": fazit, "kategorien": kategorien,
            "kennzahlen": zeilen, "staerken": staerken, "schwaechen": schwaechen,
            "abdeckung": (len(vorhanden), len(zeilen)), "kategorien_mit": len(mit)}


def kurzfazit(e, b):
    """Ein Satz zur Einordnung (fuer den Kopf der Bewertung)."""
    if b["gesamt"] is None:
        return (f"Zu wenige Kennzahlen für einen Gesamtscore (mindestens {MIN_KATEGORIEN[e['art']]} Teilbereiche "
                "nötig) – die vorhandenen Teilscores siehst du unten.")
    klasse = KLASSEN_TEXT[e["art"]]
    stufe = {"gruen": "stark", "gelb": "durchschnittlich", "rot": "schwach"}[b["ampel"]]
    besser = round(b["gesamt"])
    teile = [f"Insgesamt {stufe}: besser als {besser} % der {klasse} der Top-500-Liste"]
    if b["fazit"]:
        teile.append(f"Bewertung: {b['fazit']}")
    return " · ".join(teile) + "."


# ---------------------------------------------------------------------------
# Suche
# ---------------------------------------------------------------------------
_INDEX = {}


def _wortindex(eintraege):
    """Namenswoerter je Wert und alle Wortanfaenge nach Laenge (fuer die tippfehler-tolerante Suche), je Liste
    einmal berechnet."""
    schluessel = (id(eintraege), len(eintraege))
    if schluessel not in _INDEX:
        woerter, anfang = {}, {}
        for e in eintraege:
            ws = _norm(e["name"]).split()
            woerter[e["id"]] = ws
            for w in ws:
                for n in range(2, min(len(w), 14) + 1):
                    anfang.setdefault(n, set()).add(w[:n])
        _INDEX.clear()
        _INDEX[schluessel] = {"woerter": woerter, "anfang": {n: sorted(v) for n, v in anfang.items()}}
    return _INDEX[schluessel]


def suchen(eintraege, text, limit=15):
    """Teilstring-Suche (Gross-/Kleinschreibung, Akzente egal) ueber Name, Ticker, WKN, ISIN. Reichen die Treffer
    nicht, kommen tippfehler-tolerant aehnliche Namen dazu ("Appel" -> Apple). Reihenfolge: exakte Kennung,
    Namensanfang, Wortanfang, aehnlich, Teilstring mitten im Wort - bei Gleichstand Aktien vor ETFs vor Wikifolios, kurze Namen zuerst."""
    q = _norm(text)
    if len(q) < 2:
        return []
    woerter = q.split()
    reihe = {"aktie": 0, "etf": 1, "wikifolio": 2}
    treffer, ids = [], set()
    for e in eintraege:
        s = e.get("such") or ""
        if all(w in s for w in woerter):
            kennungen = {_norm(x) for x in (e["ticker"], e["wkn"], e["isin"]) if x}
            wortanfang = all((" " + w) in (" " + s) for w in woerter)
            rang = 0 if q in kennungen else 1 if _norm(e["name"]).startswith(q) else 2 if wortanfang else 4
            treffer.append((rang, reihe[e["art"]], len(e["name"]), e))
            ids.add(e["id"])
    if len(treffer) < limit and len(q) >= 3:
        index = _wortindex(eintraege)
        # je Suchwort aehnliche Namenswoerter (difflib), dann Werte, deren Name zu jedem Suchwort eines enthaelt
        naehe = []
        for w in woerter:
            nah = {}
            for laenge in range(max(1, len(w) - 1), len(w) + 3):
                kandidaten = index["anfang"].get(laenge) or ()
                for nw in difflib.get_close_matches(w, kandidaten, n=40, cutoff=0.75):
                    nah[nw] = max(nah.get(nw, 0), difflib.SequenceMatcher(None, w, nw).ratio())
            naehe.append(nah)
        aehnlich = []
        for e in eintraege:
            if e["id"] in ids:
                continue
            name_w = index["woerter"][e["id"]]
            werte = [max((nah.get(nw[:n], 0) for nw in name_w for n in range(1, len(nw) + 1)), default=0)
                     for nah in naehe]
            if werte and min(werte) >= 0.75:
                aehnlich.append((3, -min(werte), reihe[e["art"]], len(e["name"]), e))
        # Reihenfolge: exakt/Anfang/Wortanfang, dann aehnliche Namen, dann Treffer mitten im Wort
        aehnlich.sort(key=lambda t: t[:4])
        treffer.sort(key=lambda t: t[:3])
        vorne = [t[-1] for t in treffer if t[0] < 3]
        hinten = [t[-1] for t in treffer if t[0] >= 3]
        return (vorne + [t[-1] for t in aehnlich] + hinten)[:limit]
    treffer.sort(key=lambda t: t[:3])
    return [t[-1] for t in treffer[:limit]]
