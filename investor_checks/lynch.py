"""Peter Lynch - Kategorie, PEG und Lynch-Fair-Value.

Quelle: P. Lynch, "One Up on Wall Street" (1989), Kap. 7 (sechs Kategorien), Kap. 13 "Some Famous Numbers"
(KGV ~ Wachstumsrate, PEG, dividendenbereinigtes PEG = KGV / (Wachstum + Dividendenrendite), Netto-Cash,
Lager vs. Umsatz, Schulden/Eigenkapital).
"""
import investor_config as C

from . import registriere
from .basis import cagr, de, ergebnis, extra, kriterium, letztes, reihe, sektor_typ, teile, vorhanden, wachstum, zahl

INFO = ("Peter Lynch (*1944) machte den Magellan Fund von 1977 bis 1990 zum erfolgreichsten Fonds der Welt "
        "(Ø 29 % p. a.). „Kaufe, was du kennst“ – und zahle nicht mehr als das Gewinnwachstum (PEG ≤ 1).")


def wachstumsrate(f, kx=None):
    """Gewinnwachstum p. a. in %: EPS-CAGR der verfuegbaren Jahre, sonst Wert der Top-500-Daten."""
    eps = vorhanden(reihe(f, "eps"))
    g = cagr(eps[-1], eps[0], len(eps) - 1) if len(eps) >= 2 else None
    if g is None:
        g = zahl((((kx or {}).get("agent") or {}).get("k") or {}).get("g_eps"))
    return g


def kategorie(f, g):
    """Lynchs Kategorie (Kap. 7)."""
    eps = vorhanden(reihe(f, "eps"))
    if len(eps) >= 2 and eps[0] < 0 < eps[-1]:
        return "Turnaround"
    if f.get("kbv") is not None and 0 < f["kbv"] < 1:
        return "Asset Play"
    if sektor_typ(f) == "zyklisch":
        return "Zykliker"
    if g is None:
        return None
    cfg = C.LYNCH
    if g < cfg["slow"]:
        return "Slow Grower"
    if g > cfg["fast"]:
        return "Fast Grower"
    return "Stalwart"


def peg(kgv, g, div=0.0):
    """PEG = KGV / Wachstum; dividendenbereinigt KGV / (Wachstum + Dividendenrendite). Nur fuer positive Werte."""
    kgv, g = zahl(kgv), zahl(g)
    nenner = (g or 0) + (zahl(div) or 0)
    if kgv is None or kgv <= 0 or nenner <= 0 or g is None:
        return None
    return kgv / nenner


def fair_value(eps, g):
    """Lynch: faires KGV ~ Wachstumsrate -> fairer Kurs = EPS x g (g in %, auf 5-25 begrenzt)."""
    eps, g = zahl(eps), zahl(g)
    if eps is None or g is None or eps <= 0 or g <= 0:
        return None
    return eps * max(5.0, min(25.0, g))


@registriere("lynch", "Peter Lynch", "Wachstum", 130)
def check(f, kx):
    cfg = C.LYNCH
    g = wachstumsrate(f, kx)
    kat = kategorie(f, g)
    eps = letztes(f, "eps")
    kurs = f.get("kurs_in_bericht")
    kgv = teile(kurs, eps) if eps and eps > 0 else None
    div = zahl(f.get("div_rendite"))
    div = div * 100 if div is not None and div < 1 else div        # Yahoo liefert teils 0,02 statt 2 %
    p = peg(kgv, g)
    p_div = peg(kgv, g, div or 0)
    aktien = letztes(f, "aktien") or f.get("aktien")
    netcash = teile((letztes(f, "cash") or 0) - (letztes(f, "schulden") or 0), aktien) \
        if letztes(f, "cash") is not None else None
    de_ = teile(letztes(f, "schulden"), letztes(f, "ek")) if (letztes(f, "ek") or 0) > 0 else None
    g_lager = wachstum(letztes(f, "lager"), letztes(f, "lager", 1))
    g_ums = wachstum(letztes(f, "umsatz"), letztes(f, "umsatz", 1))
    peg_max = cfg["peg_stalwart"] if kat == "Stalwart" else cfg["peg_gut"]
    kr = [kriterium("peg", "PEG-Ratio", p, f"< {de(peg_max)}", None if p is None else p < peg_max,
                    f"KGV {de(kgv)} / Gewinnwachstum {de(g)} % p. a." + (" Unter 0,5 = sehr gut." if p and p < 0.5
                                                                           else "") if p is not None else
                    "Nur bei Gewinn und positivem Wachstum berechenbar.", fmt="zahl"),
          kriterium("peg_div", "PEG dividendenbereinigt", p_div, "< 1", None if p_div is None else p_div < 1,
                    "KGV / (Wachstum + Dividendenrendite) – für Firmen mit hoher Dividende.", fmt="zahl"),
          kriterium("lager", "Lager wächst nicht schneller als Umsatz",
                    (g_lager - g_ums) if g_lager is not None and g_ums is not None else None, "≤ 0 Pp.",
                    None if g_lager is None or g_ums is None else g_lager <= g_ums,
                    "Steigende Lager bei stagnierendem Umsatz deuten auf Absatzprobleme.", fmt="pp"),
          kriterium("de", "Schulden / Eigenkapital < 0,5", de_, cfg["max_de"],
                    None if de_ is None else de_ < cfg["max_de"], "Lynch mied hoch verschuldete Firmen.", fmt="x")]
    # Kategoriespezifisch
    if kat == "Fast Grower":
        kr.append(kriterium("tempo", "Wachstum durchhaltbar (≤ 25 % p. a.)", g, cfg["fast_max_wachstum"],
                            g <= cfg["fast_max_wachstum"], "Mehr als 25 % p. a. hält kaum eine Firma lange durch.",
                            fmt="pct"))
    elif kat == "Slow Grower":
        q = teile(letztes(f, "dividenden"), letztes(f, "nettogewinn"))
        q = q * 100 if q is not None and (letztes(f, "nettogewinn") or 0) > 0 else None
        kr.append(kriterium("div_slow", "Dividende ≥ 3 % bei Quote ≤ 60 %", div, cfg["slow_min_div"],
                            None if div is None else div >= cfg["slow_min_div"] and (q is None or q <= cfg["slow_max_quote"]),
                            "Slow Grower kauft man wegen der Dividende.", fmt="pct"))
    elif kat == "Asset Play":
        kr.append(kriterium("substanz", "Kurs unter Buchwert", f.get("kbv"), "< 1", f["kbv"] < 1,
                            "Der Börsenwert liegt unter dem bilanziellen Vermögen.", fmt="x"))
    elif kat == "Turnaround":
        cf = letztes(f, "op_cf")
        kr.append(kriterium("turn_cf", "Operativer Cashflow positiv", cf, "> 0", None if cf is None else cf > 0,
                            "Ein Turnaround braucht Geld aus dem laufenden Geschäft.", fmt="geld"))
    fv = fair_value(eps, g)
    extras = [extra("Kategorie", kat or "n/a", "Slow Grower < 5 %, Stalwart 5–15 %, Fast Grower > 15 % Gewinnwachstum "
                    "p. a.; dazu Zykliker, Turnaround (Verlust → Gewinn) und Asset Play (Kurs < Buchwert).", fmt="text"),
              extra("Lynch Fair Value", fv, "Faires KGV ≈ Wachstumsrate: EPS × Wachstum (5–25 begrenzt)."
                    + (f" Abstand zum Kurs: {de((fv / kurs - 1) * 100, 0)} %." if fv and kurs else ""), fmt="kurs"),
              extra("Netto-Cash je Aktie", netcash, "(Cash − Finanzschulden) / Aktien – Lynch zog ihn vom Kurs ab.",
                    fmt="kurs")]
    if kat == "Zykliker":
        extras.append(extra("Hinweis", "Zykliker", "Bei Zyklikern ist ein niedriges KGV oft ein Warnsignal "
                            "(Gewinn-Hoch); Lynch kaufte sie bei hohem KGV im Zyklus-Tief.", fmt="text"))
    return ergebnis("lynch", "Peter Lynch", "Wachstum zum vernünftigen Preis (PEG) – je nach Firmenkategorie.",
                    "Wachstum", kr, f, extras=extras, info=INFO) | {"kategorie_lynch": kat, "fair_value": fv,
                                                                    "wachstum": g}
