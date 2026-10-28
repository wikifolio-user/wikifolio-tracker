"""Beneish M-Score - Risiko fuer Bilanzmanipulation.

Quelle: M. Beneish, "The Detection of Earnings Manipulation", Financial Analysts Journal 55 (1999), 8-Variablen-
Modell: M = -4,84 + 0,92 DSRI + 0,528 GMI + 0,404 AQI + 0,892 SGI + 0,115 DEPI - 0,172 SGAI + 4,679 TATA
- 0,327 LVGI. M > -1,78 gilt als Warnsignal. Fehlt ein Teilindex, wird er (wie in der Praxis ueblich) mit dem
neutralen Wert 1 (TATA: 0) angesetzt - hoechstens BENEISH["max_fehlend"] Teilindizes.
"""
import investor_config as C

from . import registriere
from .basis import ergebnis, extra, kriterium, teile, zahl

INFO = ("Messod Beneish (Professor, Indiana University) entwickelte 1999 den M-Score: acht Kennzahlen, die "
        "typische Spuren geschönter Bilanzen erkennen (z. B. Forderungen wachsen schneller als der Umsatz).")

GEWICHTE = {"DSRI": 0.92, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892, "DEPI": 0.115, "SGAI": -0.172, "TATA": 4.679,
            "LVGI": -0.327}
TEXT = {
    "DSRI": "Forderungen im Verhältnis zum Umsatz (steigt = evtl. aggressive Umsatzbuchung)",
    "GMI": "Bruttomarge Vorjahr / aktuell (> 1 = Marge sinkt, Druck zum Schönen)",
    "AQI": "Anteil „weicher“ Vermögenswerte (> 1 = mehr aktivierte Kosten)",
    "SGI": "Umsatzwachstum (schnelles Wachstum erhöht den Druck)",
    "DEPI": "Abschreibungsquote Vorjahr / aktuell (> 1 = langsamer abgeschrieben)",
    "SGAI": "Vertriebs-/Verwaltungskosten im Verhältnis zum Umsatz",
    "TATA": "Periodenabgrenzungen: (Gewinn − operativer Cashflow) / Bilanzsumme",
    "LVGI": "Verschuldungsgrad aktuell / Vorjahr",
}


def indizes(t, v):
    """Die acht Teilindizes aus Jahr t und Vorjahr v. -> {name: wert oder None}"""
    def g(j, k):
        return zahl(j.get(k))

    def quote(j, a, b):
        return teile(g(j, a), g(j, b))

    s_t, s_v = g(t, "umsatz"), g(v, "umsatz")
    dsri = teile(quote(t, "forderungen", "umsatz"), quote(v, "forderungen", "umsatz"))
    gmi = teile(quote(v, "bruttogewinn", "umsatz"), quote(t, "bruttogewinn", "umsatz"))

    def weich(j):
        ta = g(j, "bilanzsumme")
        if not ta or g(j, "umlauf") is None or g(j, "sachanlagen") is None:
            return None
        return 1 - (g(j, "umlauf") + g(j, "sachanlagen")) / ta
    aqi = teile(weich(t), weich(v))
    sgi = teile(s_t, s_v)

    def abq(j):
        d, p = g(j, "abschreibungen"), g(j, "sachanlagen")
        return teile(d, (d or 0) + (p or 0)) if d is not None and p is not None else None
    depi = teile(abq(v), abq(t))
    sgai = teile(quote(t, "sga", "umsatz"), quote(v, "sga", "umsatz"))
    tata = teile((g(t, "nettogewinn") - g(t, "op_cf")) if g(t, "nettogewinn") is not None and g(t, "op_cf") is not None
                 else None, g(t, "bilanzsumme"))

    def lev(j):
        ta = g(j, "bilanzsumme")
        if not ta or g(j, "kurzfr_verb") is None:
            return None
        return (g(j, "kurzfr_verb") + (g(j, "langfr_schulden") or 0)) / ta
    lvgi = teile(lev(t), lev(v))
    return {"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi, "SGAI": sgai, "TATA": tata, "LVGI": lvgi}


def m_score(ind, max_fehlend=None):
    """-> (M, Anzahl ersetzter Indizes) oder (None, n) wenn zu viele fehlen."""
    max_fehlend = C.BENEISH["max_fehlend"] if max_fehlend is None else max_fehlend
    fehlend = [k for k, v in ind.items() if v is None]
    if len(fehlend) > max_fehlend:
        return None, len(fehlend)
    m = -4.84
    for k, gw in GEWICHTE.items():
        v = ind[k] if ind[k] is not None else (0.0 if k == "TATA" else 1.0)
        m += gw * v
    return m, len(fehlend)


@registriere("beneish", "Beneish M-Score", "Risiko", 110)
def check(f, kx):
    J = f.get("jahre") or []
    titel = ("beneish", "Beneish M-Score", "Gibt es Spuren geschönter Zahlen?", "Risiko")
    if len(J) < 2:
        return ergebnis(*titel, [], f, fazit="Mindestens zwei Geschäftsjahre nötig.", info=INFO)
    ind = indizes(J[-1], J[-2])
    m, fehlend = m_score(ind)
    extras = [extra(k, v, TEXT[k] + (" – fehlt, neutral angesetzt" if v is None else ""), fmt="zahl3")
              for k, v in ind.items()]
    if m is None:
        return ergebnis(*titel, [], f, extras=extras, fazit=f"{fehlend} von 8 Teilindizes fehlen – nicht berechenbar.",
                        info=INFO)
    s = C.BENEISH["warnschwelle"]
    ok = m <= s
    kr = [kriterium("m", "M-Score", m, f"≤ {s:.2f}".replace(".", ","), ok,
                    "Über der Schwelle steigt die Wahrscheinlichkeit geschönter Zahlen deutlich." +
                    (f" {fehlend} Teilindex/-indizes fehlten und wurden neutral angesetzt." if fehlend else ""),
                    fmt="zahl")]
    warn = [] if ok else [f"Beneish M-Score {m:.2f} über {s:.2f}".replace(".", ",") + ": Warnsignal für Bilanzmanipulation – genauer prüfen."]
    return ergebnis(*titel, kr, f, extras=extras, warnungen=warn, score=100.0 if ok else 0.0,
                    fazit=f"M-Score {m:.2f}".replace(".", ",") + " – " + ("unauffällig." if ok else "Warnsignal."), info=INFO)
