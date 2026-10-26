"""Eigene Bewertung fuer ETFs und wikifolios - unabhaengig vom Qualitaets-Score der Aktien.

Aktien werden ueber Geschaeftszahlen bewertet (qualitaet_agent.py). Fuer ETFs und wikifolios gibt es keine
Bilanz; bewertet wird, was die Kurshistorie hergibt - je Klasse mit eigenen Kriterien und Gewichten:

  ETF        langfristige Rendite, Rendite je Risiko, maximaler Rueckgang, Schwankung, Laenge der Historie,
             Bestaendigkeit. Hebel-/Short-Produkte werden gedeckelt (nur fuer kurzfristige Spekulation).
  wikifolio  Rendite, Rendite je Rueckgang (die gemessene Schwankung ist bei wikifolios oft untypisch niedrig),
             maximaler Rueckgang, Laenge der Historie (Track Record), Bestaendigkeit, Schwankung. Ausnahme-Renditen bringen keine Extrapunkte.

Datenquelle: Top-500-/Watchlist-Katalog (state/planer/katalog_gross_*.json): Kursentwicklung 1/3/5/10 Jahre
gesamt in %, Schwankung % p. a., maximaler Rueckgang %, Jahre Historie. Jeder Teilwert 0-100 Punkte, linear
zwischen den Grenzen der Klasse. Fehlt ein Teilwert, zaehlt er nicht (Abdeckung sinkt); ohne Rendite und
Rueckgang gibt es keinen Score.
"""
import re

ZEITRAEUME = (("10J", 10), ("5J", 5), ("3J", 3), ("1J", 1))
# Hebel-/Short-/Daily-Produkte (auch vom Investment-Scanner genutzt: scanner._HEBEL)
HEBEL = re.compile(r"(\b[2-9]x\b|\bx[2-9]\b|leverag|short|\bbear\b|\bbull\b|daily|ultra|hebel|inverse|"
                   r"\b[2-9]\s?fach|\bfaktor\b)", re.I)

# (Schluessel, Titel, Gewicht %, Grenze schlecht, Grenze gut)
KRITERIEN = {
    "etf": [
        ("rendite", "Rendite p. a. (längster Zeitraum)", 30, 0.0, 14.0),
        ("rr", "Rendite je Risiko", 25, 0.0, 1.0),
        ("dd", "Max. Rückgang", 20, 55.0, 15.0),
        ("vola", "Schwankung p. a.", 10, 35.0, 8.0),
        ("historie", "Bewährte Historie (Jahre)", 10, 1.0, 10.0),
        ("bestaendig", "Beständigkeit (positive Zeiträume)", 5, 0.0, 100.0),
    ],
    "wikifolio": [
        ("rendite", "Rendite p. a. (längster Zeitraum)", 25, 0.0, 20.0),
        ("rdd", "Rendite je Rückgang", 25, 0.0, 0.8),
        ("dd", "Max. Rückgang", 15, 50.0, 10.0),
        ("historie", "Track Record (Jahre)", 15, 1.0, 8.0),
        ("bestaendig", "Beständigkeit (positive Zeiträume)", 10, 0.0, 100.0),
        ("vola", "Schwankung p. a.", 10, 40.0, 6.0),
    ],
}
KLASSEN = {"prio": "Hohe Analysepriorität", "beobachten": "Beobachtungsliste", "nicht": "Nicht weiterverfolgen"}
GRENZE_PRIO, GRENZE_BEOBACHTEN = 70.0, 50.0
MIN_JAHRE = {"etf": 3.0, "wikifolio": 3.0}       # darunter hoechstens "Beobachtungsliste"
HEBEL_DECKEL = 40.0
AUSNAHME_RENDITE = 60.0                           # % p. a. - darueber Hinweis, keine Extrapunkte


def _z(x):
    try:
        return None if x is None or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


def _punkte(wert, schlecht, gut):
    if wert is None:
        return None
    anteil = (wert - schlecht) / (gut - schlecht)
    return round(max(0.0, min(1.0, anteil)) * 100.0, 1)


def pro_jahr(gesamt_pct, jahre):
    """Gesamtrendite % ueber `jahre` -> Rendite % p. a. (None ohne Daten; unter 1 Jahr nicht annualisiert)."""
    v, j = _z(gesamt_pct), _z(jahre)
    if v is None or not j or v <= -100:
        return None
    return v if j <= 1 else ((1 + v / 100.0) ** (1.0 / j) - 1) * 100.0


def kennzahlen(w):
    """w: Katalogzeile (1J/3J/5J/10J gesamt %, vola, maxdd, jahre). -> abgeleitete Kennzahlen."""
    rendite = jahre_r = None
    for z, j in ZEITRAEUME:
        v = _z(w.get(z))
        if v is not None and v > -100:
            rendite, jahre_r = ((1 + v / 100.0) ** (1.0 / j) - 1) * 100.0, j
            break
    vola = _z(w.get("vola"))
    vola = vola if vola is not None and vola >= 0.5 else None       # 0 = keine Messung (z. B. reine Cash-Phase)
    dd = _z(w.get("maxdd"))
    dd = abs(dd) if dd is not None else None
    jahre = max(_z(w.get("jahre")) or 0.0, float(jahre_r or 0))
    perioden = [_z(w.get(z)) for z, _ in ZEITRAEUME if _z(w.get(z)) is not None]
    pa = {z: pro_jahr(w.get(z), j) for z, j in ZEITRAEUME}
    pa["gesamt"] = pro_jahr(w.get("gesamt"), _z(w.get("jahre")) if (_z(w.get("jahre")) or 0) >= 1 else None)
    return {"rendite": rendite, "pa": pa, "rendite_jahre": jahre_r, "vola": vola, "dd": dd, "jahre": jahre or None,
            "historie": jahre or None,
            "rr": rendite / vola if rendite is not None and vola else None,
            "rdd": rendite / max(dd, 1.0) if rendite is not None and dd is not None else None,
            "bestaendig": 100.0 * sum(1 for p in perioden if p > 0) / len(perioden) if perioden else None}


def bewerte(w, art):
    """-> {score, einordnung, teile: {schluessel: Punkte}, kennzahlen, abdeckung, hinweise} oder
    {score: None, grund} ohne ausreichende Daten. art: "etf" | "wikifolio"."""
    k = kennzahlen(w)
    if k["rendite"] is None or k["dd"] is None:
        return {"score": None, "grund": "zu wenig Kursdaten", "kennzahlen": k, "teile": {}, "hinweise": []}
    teile, summe, gewicht = {}, 0.0, 0
    for schl, _, g, schlecht, gut in KRITERIEN[art]:
        p = _punkte(k[schl], schlecht, gut)
        teile[schl] = p
        if p is not None:
            summe, gewicht = summe + g * p, gewicht + g
    score = summe / gewicht
    hinweise = []
    hebel = art == "etf" and bool(HEBEL.search(str(w.get("name") or "")))
    if hebel:
        score = min(score, HEBEL_DECKEL)
        hinweise.append("Hebel-/Short-Produkt – nur für kurzfristige Spekulation, Score gedeckelt")
    if k["rendite"] > AUSNAHME_RENDITE:
        hinweise.append("Ausnahme-Rendite – nicht fortschreibbar")
    if (k["jahre"] or 0) < MIN_JAHRE[art]:
        hinweise.append(f"kurze Historie ({_de(k['jahre'] or 0)} J.)")
    if k["vola"] is None:
        hinweise.append("Schwankung nicht gemessen")
    score = round(score, 1)
    if score >= GRENZE_PRIO and (k["jahre"] or 0) >= MIN_JAHRE[art] and not hebel:
        einordnung = "prio"
    elif score >= GRENZE_BEOBACHTEN:
        einordnung = "beobachten"
    else:
        einordnung = "nicht"
    return {"score": score, "einordnung": einordnung, "teile": teile, "kennzahlen": k, "hebel": hebel,
            "abdeckung": round(100.0 * gewicht / sum(g for _, _, g, _, _ in KRITERIEN[art])), "hinweise": hinweise}


def _de(x, dez=1):
    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def staerken_schwaechen(b, art):
    """Kurze, aus den Teilpunkten abgeleitete Begruendung -> (staerken, schwaechen)."""
    titel = {s: t for s, t, *_ in KRITERIEN[art]}
    k = b.get("kennzahlen") or {}
    werte = {"rendite": lambda: f"{_de(k['rendite'])} %", "rr": lambda: _de(k["rr"], 2),
             "rdd": lambda: _de(k["rdd"], 2),
             "dd": lambda: f"{_de(k['dd'], 0)} %", "vola": lambda: f"{_de(k['vola'], 0)} %",
             "historie": lambda: f"{_de(k['jahre'], 0)} J.", "bestaendig": lambda: f"{_de(k['bestaendig'], 0)} %"}
    st, sw = [], []
    for schl, p in (b.get("teile") or {}).items():
        if p is None:
            continue
        kurz = titel[schl].split(" (")[0]
        if schl == "historie" and k.get("jahre") is None:
            continue
        if p >= 75:
            st.append(f"{kurz} {werte[schl]()}")
        elif p <= 25:
            sw.append(f"{kurz} {werte[schl]()}")
    return st[:3], (b.get("hinweise") or [])[:1] + sw[:3 - min(1, len(b.get("hinweise") or []))]


def rangliste(katalog_teile, art):
    """Alle Werte einer Klasse aus dem Katalog, bewertet und nach Score sortiert (ohne Score am Ende nicht
    enthalten). -> [{name, kennung, isin, art, ..., bewertung}]"""
    typ = {"etf": "etf", "wikifolio": "wikifolio"}[art]
    aus, gesehen = [], set()
    for d in katalog_teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            w = dict(zip(felder, z))
            if w.get("typ") != typ:
                continue
            kenn = str(w.get("isin") or w.get("kennung") or "").upper()
            if not kenn or kenn in gesehen:
                continue
            gesehen.add(kenn)
            b = bewerte(w, art)
            if b["score"] is None:
                continue
            aus.append({"name": str(w.get("name") or kenn), "kennung": str(w.get("kennung") or ""),
                        "isin": str(w.get("isin") or ""), "bewertung": b})
    aus.sort(key=lambda e: (-e["bewertung"]["score"], -(e["bewertung"]["kennzahlen"]["jahre"] or 0),
                            e["name"].lower()))
    for i, e in enumerate(aus, 1):
        e["rang"] = i
    return aus
