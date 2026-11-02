"""Wikifolio-Liste der Watchlist: alle Kennzahlen, Filter und eigene Bewertung ("Mein Score") - reine Logik.

Daten: state/wikifolio_kennzahlen_N.json (Watchlist-Agent, taeglich; Felder siehe top50_agent.WIKI_KZ_FELDER)
plus Score/Rendite je Verlust/Historie aus dem Katalog (klassen_score.je_kennung).
Jeder Wert: {"name", "wkn", "isin", "perf": {zeitraum: %}, "kz": {kennzahl: wert}}.
"""
ZEITRAEUME = ("1M", "3M", "6M", "1J", "2J", "3J", "5J")

# (Schluessel, Titel, groesser = besser, Einheit) - Reihenfolge = Anzeige in der Auswahl
KENNZAHLEN = (
    ("mein_score", "Mein Score", True, "punkte"),
    ("score", "Score", True, "punkte"),
    ("rendite_pa", "Rendite p. a. (gesamt)", True, "pct"),
    ("sharpe1j", "Sharpe 1 J.", True, "zahl"),
    ("sharpe3j", "Sharpe 3 J.", True, "zahl"),
    ("sortino1j", "Sortino 1 J.", True, "zahl"),
    ("calmar3j", "Calmar 3 J.", True, "zahl"),
    ("rdd", "Rendite je Verlust", True, "zahl"),
    ("vola1j", "Vola 1 J.", False, "pct_neutral"),
    ("vola3j", "Vola 3 J.", False, "pct_neutral"),
    ("maxdd", "Max. Verlust", True, "pct_minus"),
    ("maxdd1j", "Max. Verlust 1 J.", True, "pct_minus"),
    ("dd_akt", "Abstand zum Hoch", True, "pct_minus"),
    ("tage_unter_hoch", "Tage seit Hoch", False, "tage"),
    ("gewinnmonate", "Gewinnmonate", True, "pct_neutral"),
    ("bester_monat", "Bester Monat", True, "pct"),
    ("schlechtester_monat", "Schlechtester Monat", True, "pct"),
    ("sma200", "Trend (200-Tage-Linie)", True, "pct"),
    ("jahre", "Historie", True, "jahre"),
)
TITEL = {k: t for k, t, _, _ in KENNZAHLEN}
BESSER_GROSS = {k: g for k, _, g, _ in KENNZAHLEN}
EINHEIT = {k: e for k, _, _, e in KENNZAHLEN}

# Standard-Spalten und -Gewichte der eigenen Bewertung (0 = zaehlt nicht)
STANDARD_SPALTEN = ("score", "sharpe1j", "vola1j", "maxdd", "dd_akt", "gewinnmonate")
BEWERTUNG = (("rendite_pa", 3), ("sharpe1j", 3), ("sortino1j", 1), ("calmar3j", 2), ("maxdd", 3), ("vola1j", 1),
             ("gewinnmonate", 2), ("jahre", 2), ("sma200", 1), ("dd_akt", 1))

# Filter: (Schluessel, Titel, Art "min" | "max", Bereich (von, bis), Schritt)
FILTER = (
    ("jahre", "Historie mindestens (Jahre)", "min", (0.0, 15.0), 0.5),
    ("rendite_pa", "Rendite p. a. mindestens (%)", "min", (-20.0, 60.0), 1.0),
    ("sharpe1j", "Sharpe 1 J. mindestens", "min", (-1.0, 3.0), 0.1),
    ("maxdd", "Max. Verlust höchstens (%)", "max_verlust", (0.0, 90.0), 1.0),
    ("vola1j", "Vola 1 J. höchstens (%)", "max", (0.0, 80.0), 1.0),
    ("gewinnmonate", "Gewinnmonate mindestens (%)", "min", (0.0, 100.0), 5.0),
    ("dd_akt", "Abstand zum Hoch höchstens (%)", "max_verlust", (0.0, 90.0), 1.0),
)


def _zahl(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def laden(teile, katalog_kz=None):
    """Kennzahlen-Dateien (+ Katalog-Kennzahlen je WKN/ISIN) -> {wkn: wert}"""
    katalog_kz = katalog_kz or {}
    werte = {}
    for d in teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            r = dict(zip(felder, z))
            wkn = str(r.get("wkn") or "").strip()
            if not wkn or wkn in werte:
                continue
            kz = {k: _zahl(r.get(k)) for k in BESSER_GROSS if k in r}
            kat = katalog_kz.get(wkn.upper()) or katalog_kz.get(str(r.get("isin") or "").upper()) or {}
            for k in ("score", "rdd", "jahre"):
                if kat.get(k) is not None:
                    kz[k] = kat[k]
            kz["_einordnung"] = kat.get("einordnung")
            werte[wkn] = {"name": str(r.get("name") or wkn), "wkn": wkn, "isin": str(r.get("isin") or ""),
                          "perf": {zr: _zahl(r.get(zr)) for zr in ZEITRAEUME if _zahl(r.get(zr)) is not None},
                          "kz": kz}
    return werte


def wert_von(w, schluessel):
    """Zeitraum (perf) oder Kennzahl eines Werts."""
    if schluessel in ZEITRAEUME:
        return w["perf"].get(schluessel)
    return w["kz"].get(schluessel)


def filtern(werte, grenzen, nur_aufwaerts=False):
    """grenzen: {schluessel: grenzwert} (Art aus FILTER). Werte ohne die gefilterte Kennzahl fallen heraus."""
    arten = {k: a for k, _, a, _, _ in FILTER}
    aus = {}
    for wkn, w in werte.items():
        ok = True
        for k, g in (grenzen or {}).items():
            if g is None:
                continue
            v = w["kz"].get(k)
            art = arten.get(k, "min")
            if v is None or (art == "min" and v < g) or (art == "max" and v > g) or \
                    (art == "max_verlust" and v < -abs(g)):
                ok = False
                break
        if ok and nur_aufwaerts and not (w["kz"].get("sma200") is not None and w["kz"]["sma200"] > 0):
            ok = False
        if ok:
            aus[wkn] = w
    return aus


def _perzentile(werte, schluessel):
    """{wkn: 0..1} - Rang innerhalb der Werte (1 = bester), Richtung je Kennzahl."""
    mit = sorted(((w["kz"].get(schluessel), wkn) for wkn, w in werte.items() if w["kz"].get(schluessel) is not None),
                 key=lambda x: x[0], reverse=not BESSER_GROSS[schluessel])
    n = len(mit)
    if n < 2:
        return {wkn: 1.0 for _, wkn in mit}
    return {wkn: i / (n - 1) for i, (_, wkn) in enumerate(mit)}


def mein_score(werte, gewichte):
    """Eigene Bewertung 0-100: gewichteter Durchschnitt der Rangplaetze (Perzentile) je Kennzahl innerhalb der
    uebergebenen Werte. Fehlt einem Wert eine Kennzahl, zaehlt nur der Rest; ohne Gewicht -> kein Score.
    Setzt w["kz"]["mein_score"]."""
    aktiv = {k: float(g) for k, g in (gewichte or {}).items() if g and k in BESSER_GROSS}
    rang = {k: _perzentile(werte, k) for k in aktiv}
    for wkn, w in werte.items():
        summe = gewicht = 0.0
        for k, g in aktiv.items():
            p = rang[k].get(wkn)
            if p is not None:
                summe, gewicht = summe + g * p, gewicht + g
        w["kz"]["mein_score"] = round(100 * summe / gewicht, 1) if gewicht else None
    return werte


def rangliste(werte, schluessel, begriff="", n=500):
    """Die besten n nach Zeitraum oder Kennzahl (Werte ohne diesen Wert fehlen), danach optional nach Name/WKN
    gefiltert - der Rang bleibt der in der vollen Liste."""
    gross = True if schluessel in ZEITRAEUME else BESSER_GROSS[schluessel]
    mit = [(wert_von(w, schluessel), w) for w in werte.values() if wert_von(w, schluessel) is not None]
    mit.sort(key=lambda x: ((-x[0] if gross else x[0]), x[1]["name"].lower()))
    liste = [dict(w, rang=i) for i, (_, w) in enumerate(mit[:n], 1)]
    b = str(begriff or "").strip().lower()
    return [w for w in liste if b in (w["name"] + " " + w["wkn"]).lower()] if b else liste
