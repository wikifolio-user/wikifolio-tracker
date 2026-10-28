"""Weitere Warnsignale (Red Flags) aus den Abschluessen.

Quellen: H. Schilit, "Financial Shenanigans" (4. Aufl. 2018) - Forderungen/Lager wachsen schneller als der Umsatz,
Gewinn steigt bei sinkendem Cashflow; uebliche Bilanzregeln fuer Goodwill-Anteil, Zinsdeckung, Ausschuettung
ueber dem Free Cashflow und Verwaesserung.
Bestanden = KEIN Warnsignal.
"""
import investor_config as C

from . import registriere
from .basis import cagr, ergebnis, kriterium, letztes, pct, reihe, teile, vorhanden, wachstum

INFO = ("Typische Warnsignale aus der Bilanzanalyse (u. a. nach Howard Schilit, „Financial Shenanigans“): "
        "Muster, die oft vor Gewinnwarnungen oder Bilanzproblemen auftauchen.")


WARNTEXT = {
    "forderungen": "Forderungen wachsen deutlich schneller als der Umsatz.",
    "lager": "Lagerbestand wächst deutlich schneller als der Umsatz.",
    "gewinn_cf": "Nettogewinn steigt, operativer Cashflow sinkt.",
    "goodwill": "Goodwill über 50 % des Eigenkapitals.",
    "zinsdeckung": "Zinsdeckung unter 3 – Zinslast drückt.",
    "ausschuettung": "Dividende höher als der Free Cashflow.",
    "verwaesserung": "Starke Verwässerung (Aktienanzahl > 5 % p. a.).",
}


@registriere("red_flags", "Warnsignale", "Risiko", 120)
def check(f, kx):
    cfg = C.RED_FLAGS
    J = f.get("jahre") or []
    kr, warn = [], []
    g_ums = wachstum(letztes(f, "umsatz"), letztes(f, "umsatz", 1))
    for feld, kid, name, schwelle in (("forderungen", "forderungen", "Forderungen wachsen nicht viel schneller als "
                                       "der Umsatz", cfg["forderungen_vorsprung"]),
                                      ("lager", "lager", "Lager wächst nicht viel schneller als der Umsatz",
                                       cfg["lager_vorsprung"])):
        g = wachstum(letztes(f, feld), letztes(f, feld, 1))
        vor = g - g_ums if g is not None and g_ums is not None else None
        kr.append(kriterium(kid, name, vor, f"≤ {schwelle:.0f} Pp. Vorsprung", None if vor is None else vor <= schwelle,
                            "Wachstum ggü. Vorjahr minus Umsatzwachstum (Prozentpunkte).", fmt="pp"))
    ni_up = (letztes(f, "nettogewinn") or 0) > (letztes(f, "nettogewinn", 1) or 0) if len(J) >= 2 else None
    cf_down = (letztes(f, "op_cf") or 0) < (letztes(f, "op_cf", 1) or 0) if len(J) >= 2 else None
    ok3 = None if ni_up is None or letztes(f, "op_cf") is None or letztes(f, "op_cf", 1) is None \
        else not (ni_up and cf_down)
    kr.append(kriterium("gewinn_cf", "Gewinn und Cashflow laufen gleich", "Gewinn ↑, Cashflow ↓" if ok3 is False else
                        "unauffällig" if ok3 else None, "nicht gegenläufig", ok3,
                        "Steigender Gewinn bei sinkendem operativem Cashflow ist ein klassisches Warnsignal.",
                        fmt="text"))
    gw = pct(letztes(f, "goodwill"), letztes(f, "ek")) if (letztes(f, "ek") or 0) > 0 else None
    if gw is None and letztes(f, "ek") is not None and letztes(f, "ek") > 0 and letztes(f, "bilanzsumme"):
        gw = 0.0 if letztes(f, "goodwill") is None else gw
    kr.append(kriterium("goodwill", "Goodwill ≤ 50 % des Eigenkapitals", gw, f"≤ {cfg['goodwill_max_ek']:.0f} %",
                        None if gw is None else gw <= cfg["goodwill_max_ek"],
                        "Viel Goodwill = teure Übernahmen; Abschreibungen drohen.", fmt="pct"))
    ebit, zins = letztes(f, "ebit"), letztes(f, "zinsaufwand")
    zd = teile(ebit, abs(zins)) if zins else (float("inf") if ebit is not None and (letztes(f, "schulden") or 0) == 0
                                              else None)
    kr.append(kriterium("zinsdeckung", "Zinsdeckung ≥ 3", zd, f"≥ {cfg['min_zinsdeckung']:.0f}",
                        None if zd is None else zd >= cfg["min_zinsdeckung"], "EBIT / Zinsaufwand.", fmt="x"))
    div, fcf = letztes(f, "dividenden"), letztes(f, "fcf")
    aq = pct(div, fcf) if div and fcf and fcf > 0 else None
    ok6 = None if div is None or fcf is None else (div == 0 or (fcf > 0 and aq <= cfg["max_ausschuettung_fcf"]))
    kr.append(kriterium("ausschuettung", "Dividende durch FCF gedeckt", aq if aq is not None else
                        ("FCF negativ" if div and fcf is not None and fcf <= 0 else None),
                        f"≤ {cfg['max_ausschuettung_fcf']:.0f} % des FCF", ok6,
                        "Ausschüttung über dem Free Cashflow geht an die Substanz.", fmt="pct"))
    ak = vorhanden(reihe(f, "aktien"))
    vera = cagr(ak[-1], ak[0], len(ak) - 1) if len(ak) >= 2 else None
    kr.append(kriterium("verwaesserung", "Keine starke Verwässerung", vera, f"≤ {cfg['max_verwaesserung']:.0f} % p. a.",
                        None if vera is None else vera <= cfg["max_verwaesserung"],
                        "Aktienanzahl-Veränderung p. a.", fmt="pct"))
    for k in kr:
        if k["status"] == "fail":
            warn.append(WARNTEXT[k["id"]])
    return ergebnis("red_flags", "Warnsignale", "Klassische Muster vor Bilanzproblemen.", "Risiko", kr, f,
                    warnungen=warn, info=INFO)
