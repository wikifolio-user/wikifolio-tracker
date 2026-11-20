"""Eigenes Rating im Stil von Investor's Business Daily (IBD) - zusaetzliche Bewertung, aendert keine andere Note.

IBD veroeffentlicht nur die Bausteine, nicht die Formel. Nachgebildet nach W. O'Neil ("How to Make Money in
Stocks"): beide Ratings sind Ranglisten 1-99 (99 = besser als 99 % der verglichenen Aktien).

  EPS-Rating        Gewinnwachstum: juengste Quartale ggue. Vorjahresquartal + Jahres-EPS-Wachstum (3 Jahre)
  Composite-Rating  EPS-Rating (doppelt), relative Kursstaerke (letztes Quartal doppelt), Branchenstaerke,
                    SMR (Umsatzwachstum, Nettomarge, Eigenkapitalrendite), Akkumulation (Volumen auf/ab, 13 Wochen),
                    Naehe zum 52-Wochen-Hoch

Ablauf: Der Investoren-Agent speichert je Aktie die Rohwerte (rohwerte -> Feld "ibd"); die Raenge entstehen erst
bei der Anzeige im Vergleich mit allen bewerteten Aktien (ratings). Fehlende Werte zaehlen nie als 0 - die Gewichte
werden auf die vorhandenen verteilt. Ohne Gewinnwachstum gibt es kein Rating.
"""
import bisect
import statistics

import investor_config as C

GEWICHTE_EPS = C.IBD["gewichte_eps"]
GEWICHTE_COMPOSITE = C.IBD["gewichte_composite"]
MIN_VERGLEICH = 30           # weniger Vergleichswerte -> kein Rang
MIN_BRANCHE = 5              # Aktien je Sektor fuer die Branchenstaerke
TEILE = {"eps": "Gewinnwachstum (EPS)", "rs": "Relative Kursstärke", "branche": "Branchenstärke",
         "smr": "Umsatz, Marge, Eigenkapitalrendite", "ad": "Akkumulation (Volumen)", "hoch": "Nähe zum 52-Wochen-Hoch"}


def _zahl(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _wachstum(neu, alt):
    neu, alt = _zahl(neu), _zahl(alt)
    if neu is None or alt is None or alt <= 0:
        return None
    return (neu / alt - 1) * 100


def _r(x, n=2):
    return None if x is None else round(x, n)


def quartals_wachstum(quartale):
    """EPS-Wachstum der beiden juengsten Quartale ggue. Vorjahresquartal (%) -> (q1, q2), je None wenn unbekannt."""
    eps = [q.get("eps") for q in quartale or []]
    q1 = _wachstum(eps[-1], eps[-5]) if len(eps) >= 5 else None
    q2 = _wachstum(eps[-2], eps[-6]) if len(eps) >= 6 else None
    return q1, q2


def jahres_wachstum(jahre, n=3):
    """Durchschnittliches EPS-Wachstum p. a. ueber n Jahre (%), nur bei positivem Anfangs- und Endwert."""
    eps = [_zahl(j.get("eps")) for j in jahre or []]
    if len(eps) < n + 1 or eps[-1] is None or eps[-1 - n] is None or eps[-1] <= 0 or eps[-1 - n] <= 0:
        return None
    return ((eps[-1] / eps[-1 - n]) ** (1 / n) - 1) * 100


def kursstaerke(schluss):
    """IBD-Gewichtung der 12-Monats-Performance: letztes Quartal 40 %, die drei davor je 20 % (je 63 Handelstage)."""
    if len(schluss) < 253 or any(not x for x in schluss[-253::63]):
        return None
    p = [(schluss[-1 - 63 * i] / schluss[-1 - 63 * (i + 1)] - 1) * 100 for i in range(4)]
    return 0.4 * p[0] + 0.2 * (p[1] + p[2] + p[3])


def akkumulation(kurse, tage=65):
    """Volumen an Aufwaertstagen / Abwaertstagen der letzten `tage` Handelstage (13 Wochen)."""
    k = (kurse or [])[-(tage + 1):]
    if len(k) < tage + 1:
        return None
    auf = sum(v or 0 for (_, c, v), (_, c0, _) in zip(k[1:], k[:-1]) if c > c0)
    ab = sum(v or 0 for (_, c, v), (_, c0, _) in zip(k[1:], k[:-1]) if c < c0)
    if not ab:
        return 10.0 if auf else None              # nur Aufwaertstage: gedeckelt statt unendlich
    return min(auf / ab, 10.0)


def abstand_hoch(schluss, tage=252):
    """Abstand zum hoechsten Schlusskurs der letzten 12 Monate in % (0 = am Hoch)."""
    k = [x for x in schluss[-tage:] if x]
    return (1 - k[-1] / max(k)) * 100 if k else None


def rohwerte(f):
    """Fakten einer Aktie (investor_checks.abruf.fakten) -> kompakte Rohwerte fuer den Datensatz ("ibd")."""
    kurse = f.get("kurse") or []
    schluss = [c for _, c, _ in kurse]
    q1, q2 = quartals_wachstum(f.get("quartale"))
    jahre = f.get("jahre") or []
    j = jahre[-1] if jahre else {}
    umsatz = _zahl(j.get("umsatz"))
    gewinn = _zahl(j.get("nettogewinn"))
    ek = _zahl(j.get("ek"))
    aus = {"q1": _r(q1), "q2": _r(q2), "a": _r(jahres_wachstum(jahre)), "rs": _r(kursstaerke(schluss)),
           "uw": _r(_wachstum(umsatz, jahre[-2].get("umsatz")) if len(jahre) >= 2 else None),
           "nm": _r(gewinn / umsatz * 100 if gewinn is not None and umsatz else None),
           "roe": _r(gewinn / ek * 100 if gewinn is not None and ek and ek > 0 else None),
           "ad": _r(akkumulation(kurse), 3), "hoch": _r(abstand_hoch(schluss))}
    return {k: v for k, v in aus.items() if v is not None}


def _rang(sortiert, wert, hoeher_besser=True):
    """Perzentil 0-100 (gleiche zaehlen halb) oder None."""
    n = len(sortiert)
    if wert is None or n < MIN_VERGLEICH:
        return None
    unter = bisect.bisect_left(sortiert, wert)
    gleich = bisect.bisect_right(sortiert, wert) - unter
    p = (unter + 0.5 * gleich) / n * 100
    return p if hoeher_besser else 100 - p


def _mittel(teile, gewichte):
    da = [(gewichte[k], v) for k, v in teile.items() if v is not None and k in gewichte]
    g = sum(w for w, _ in da)
    return sum(w * v for w, v in da) / g if g else None


def _skala(p):
    return None if p is None else max(1, min(99, round(p)))


def bewerte_alle(roh_je_symbol, sektor_je_symbol=None):
    """{symbol: rohwerte} (+ {symbol: sektor}) -> Vergleichsbasis fuer rating(). Einmal je Anzeige berechnen."""
    sektor_je_symbol = sektor_je_symbol or {}
    felder = ("q1", "q2", "a", "rs", "uw", "nm", "roe", "ad", "hoch")
    vert = {k: sorted(r[k] for r in roh_je_symbol.values() if r.get(k) is not None) for k in felder}
    je_sektor = {}
    for s, r in roh_je_symbol.items():
        if r.get("rs") is not None and sektor_je_symbol.get(s):
            je_sektor.setdefault(sektor_je_symbol[s], []).append(r["rs"])
    branche = {sek: statistics.mean(v) for sek, v in je_sektor.items() if len(v) >= MIN_BRANCHE}
    basis = {"vert": vert, "branche": branche, "branche_vert": sorted(
        branche[sektor_je_symbol[s]] for s in roh_je_symbol if sektor_je_symbol.get(s) in branche)}
    # Zweiter Durchgang: EPS- und Composite-Rohscores aller Aktien -> deren Verteilung fuer die 1-99-Skala
    eps_roh, comp_roh = [], []
    for s, r in roh_je_symbol.items():
        t = _teile(r, sektor_je_symbol.get(s), basis)
        if t["eps"] is not None:
            eps_roh.append(t["eps"])
            comp_roh.append(_mittel(t, GEWICHTE_COMPOSITE))
    basis["eps_vert"], basis["comp_vert"] = sorted(eps_roh), sorted(comp_roh)
    return basis


def _teile(r, sektor, basis):
    v = basis["vert"]
    aktuell = [x for x in (_rang(v["q1"], r.get("q1")), _rang(v["q2"], r.get("q2"))) if x is not None]
    eps = _mittel({"aktuell": statistics.mean(aktuell) if aktuell else None,
                   "jahre": _rang(v["a"], r.get("a"))}, GEWICHTE_EPS)
    smr = [x for x in (_rang(v["uw"], r.get("uw")), _rang(v["nm"], r.get("nm")), _rang(v["roe"], r.get("roe")))
           if x is not None]
    return {"eps": eps, "rs": _rang(v["rs"], r.get("rs")),
            "branche": _rang(basis["branche_vert"], basis["branche"].get(sektor)),
            "smr": statistics.mean(smr) if smr else None, "ad": _rang(v["ad"], r.get("ad")),
            "hoch": _rang(v["hoch"], r.get("hoch"), hoeher_besser=False)}


def rating(r, sektor, basis):
    """Rohwerte einer Aktie -> {"eps": 1-99, "composite": 1-99, "teile": {baustein: 0-100}} oder None
    (ohne Gewinnwachstum)."""
    if not r:
        return None
    t = _teile(r, sektor, basis)
    if t["eps"] is None:
        return None
    eps = _skala(_rang(basis["eps_vert"], t["eps"]))
    if eps is None:
        return None
    return {"eps": eps, "composite": _skala(_rang(basis["comp_vert"], _mittel(t, GEWICHTE_COMPOSITE))),
            "teile": {k: None if x is None else round(x) for k, x in t.items()}}


def alle_ratings(werte):
    """Vorberechnete Agenten-Datensaetze {symbol: {"ibd": rohwerte, "sek": ...}} -> ({symbol: rating}, basis)."""
    roh = {s: w["ibd"] for s, w in werte.items() if isinstance(w, dict) and w.get("ibd")}
    sek = {s: werte[s].get("sek") for s in roh}
    basis = bewerte_alle(roh, sek)
    return {s: x for s in roh if (x := rating(roh[s], sek[s], basis))}, basis
