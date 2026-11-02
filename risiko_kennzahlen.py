"""Kennzahlen aus einer Tageskurs-Reihe [(datum, kurs), ...] - fuer die Wikifolio-Liste der Watchlist.

Berechnet vom Watchlist-Agenten (top50_agent.py) fuer jedes wikifolio, abgelegt in state/wikifolio_kennzahlen_N.json.
Nur Standardbibliothek. Alle Prozentwerte in % (gerundet), Kennzahlen ohne ausreichende Historie fehlen (None).

  rendite_pa    Rendite p. a. ueber die gesamte Historie (ab 1 Jahr)
  vola1j/3j     Schwankung der Tagesrenditen p. a. (1 bzw. 3 Jahre)
  sharpe1j/3j   (Rendite p. a. - risikofreier Zins) / Vola - Ertrag je Schwankung
  sortino1j     wie Sharpe, aber nur Abwaertsschwankung
  maxdd         groesster Rueckgang vom Hoechststand seit Beginn (negativ)
  maxdd1j       groesster Rueckgang im letzten Jahr (negativ)
  dd_akt        Abstand zum bisherigen Hoechststand (0 = auf Allzeithoch)
  tage_unter_hoch  Kalendertage seit dem letzten Allzeithoch
  calmar3j      Rendite p. a. (3 J.) / |max. Rueckgang (3 J.)|
  gewinnmonate  Anteil der Monate mit Plus (%)
  bester_monat / schlechtester_monat   Monatsrendite in %
  sma200        Abstand zur 200-Tage-Linie in % (positiv = darueber, Aufwaertstrend)
"""
import datetime
import math

RISIKOFREI = 0.02            # risikofreier Zins p. a. fuer Sharpe/Sortino (Annahme, Tagesgeld-Niveau)
FELDER = ("rendite_pa", "vola1j", "vola3j", "sharpe1j", "sharpe3j", "sortino1j", "maxdd", "maxdd1j", "dd_akt",
          "tage_unter_hoch", "calmar3j", "gewinnmonate", "bester_monat", "schlechtester_monat", "sma200")


def _r(x, n=2):
    return None if x is None or not math.isfinite(x) else round(x, n)


def _ab(reihe, tage):
    grenze = reihe[-1][0] - datetime.timedelta(days=tage)
    return [p for p in reihe if p[0] >= grenze]


def _log_renditen(teil):
    return [math.log(teil[i][1] / teil[i - 1][1]) for i in range(1, len(teil))
            if teil[i - 1][1] > 0 and teil[i][1] > 0]


def _vola(teil):
    r = _log_renditen(teil)
    if len(r) <= 20:
        return None
    m = sum(r) / len(r)
    return (sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5 * math.sqrt(252)


def _abwaerts(teil):
    r = _log_renditen(teil)
    if len(r) <= 20:
        return None
    return (sum(min(x, 0.0) ** 2 for x in r) / len(r)) ** 0.5 * math.sqrt(252)


def _cagr(teil, min_tage=300):
    if len(teil) < 2 or teil[0][1] <= 0:
        return None
    tage = (teil[-1][0] - teil[0][0]).days
    if tage < min_tage:
        return None
    return (teil[-1][1] / teil[0][1]) ** (365.25 / tage) - 1


def _maxdd(teil):
    hoch, dd = 0.0, 0.0
    for _, k in teil:
        hoch = max(hoch, k)
        if hoch > 0:
            dd = min(dd, k / hoch - 1)
    return dd


def _quote(zaehler, nenner):
    return zaehler / nenner if zaehler is not None and nenner else None


def kennzahlen(reihe):
    """reihe: [(datum, kurs)] aufsteigend. -> {feld: wert} (siehe FELDER) oder {} bei zu kurzer Historie."""
    reihe = [(d, float(k)) for d, k in reihe if k and k > 0]
    if len(reihe) < 30:
        return {}
    letzt_tag, letzt = reihe[-1]
    j1, j3 = _ab(reihe, 365), _ab(reihe, 3 * 365)
    hat3 = (letzt_tag - reihe[0][0]).days >= 3 * 365 - 20

    vola1, vola3 = _vola(j1), (_vola(j3) if hat3 else None)
    c1, c3, cg = _cagr(j1), (_cagr(j3) if hat3 else None), _cagr(reihe, 365)
    unten1 = _abwaerts(j1)
    dd3 = _maxdd(j3) if hat3 else None

    hoch, hoch_tag = 0.0, reihe[0][0]
    for d, k in reihe:
        if k >= hoch:
            hoch, hoch_tag = k, d

    # Monatsrenditen aus dem letzten Kurs je Monat
    monat_ende = {}
    for d, k in reihe:
        monat_ende[(d.year, d.month)] = k
    werte = [monat_ende[m] for m in sorted(monat_ende)]
    monate = [werte[i] / werte[i - 1] - 1 for i in range(1, len(werte)) if werte[i - 1] > 0]

    letzte200 = [k for _, k in reihe[-200:]]
    sma = sum(letzte200) / len(letzte200) if len(letzte200) >= 200 else None

    return {
        "rendite_pa": _r(cg * 100 if cg is not None else None, 1),
        "vola1j": _r(vola1 * 100 if vola1 else None, 1),
        "vola3j": _r(vola3 * 100 if vola3 else None, 1),
        "sharpe1j": _r(_quote(None if c1 is None else c1 - RISIKOFREI, vola1)),
        "sharpe3j": _r(_quote(None if c3 is None else c3 - RISIKOFREI, vola3)),
        "sortino1j": _r(_quote(None if c1 is None else c1 - RISIKOFREI, unten1)),
        "maxdd": _r(_maxdd(reihe) * 100, 1),
        "maxdd1j": _r(_maxdd(j1) * 100, 1),
        "dd_akt": _r((letzt / hoch - 1) * 100, 1) if hoch > 0 else None,
        "tage_unter_hoch": (letzt_tag - hoch_tag).days,
        "calmar3j": _r(c3 / abs(dd3)) if c3 is not None and dd3 else None,
        "gewinnmonate": _r(100.0 * sum(1 for m in monate if m > 0) / len(monate), 0) if len(monate) >= 6 else None,
        "bester_monat": _r(max(monate) * 100, 1) if len(monate) >= 6 else None,
        "schlechtester_monat": _r(min(monate) * 100, 1) if len(monate) >= 6 else None,
        "sma200": _r((letzt / sma - 1) * 100, 1) if sma else None,
    }
