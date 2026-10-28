"""Benjamin Graham - der defensive Investor (7 Kriterien).

Quelle: B. Graham, "The Intelligent Investor" (4. Aufl. 1973), Kap. 14 "Stock Selection for the Defensive
Investor"; Graham-Formel (revidiert) aus "The Decline and Fall of the Bond Rating Agencies" (1974):
V = EPS x (8,5 + 2g) x 4,4 / Y. Graham verlangte 10-20 Jahre Historie - hier wird mit der verfuegbaren
Historie angenaehert und das als "eingeschraenkt" gekennzeichnet.
"""
import datetime
import math

import investor_config as C

from . import registriere
from .basis import (cagr, de, ergebnis, extra, kriterium, letztes, mittel, reihe, schwelle_versorger, teile,
                    vorhanden, zahl)

INFO = ("Benjamin Graham (1894–1976) gilt als Vater des Value Investing und war Lehrer von Warren Buffett. "
        "Der „defensive Investor“ kauft nur große, solide finanzierte, beständig profitable Unternehmen zu "
        "einem moderaten Preis.")


def dividenden_jahre_ohne_luecke(f, heute=None):
    """Anzahl aufeinanderfolgender Kalenderjahre mit Dividende bis zum letzten vollen Jahr (aus der Historie)
    und Anzahl Jahre, die die Historie ueberhaupt abdeckt. -> (jahre_ohne_luecke, abgedeckt)"""
    hist = f.get("dividenden_hist") or []
    if not hist:
        return 0, 0
    jahre = {int(d[:4]) for d, b in hist if b and b > 0}
    letztes_volles = (heute or datetime.date.today()).year - 1
    erstes = min(jahre)
    n = 0
    j = letztes_volles
    while j in jahre:
        n += 1
        j -= 1
    return n, max(0, letztes_volles - erstes + 1)


def eps_wachstum_perioden(eps):
    """Graham: Durchschnitt der ersten 3 vs. letzten 3 Jahre; bei kurzer Historie k = n // 2 Jahre je Ende.
    -> (wachstum %, k) oder (None, k)."""
    e = vorhanden(eps)
    if len(e) < 3:
        return None, 0
    k = 3 if len(e) >= 6 else len(e) // 2
    a, b = mittel(e[:k]), mittel(e[-k:])
    if a is None or b is None or a <= 0:
        return None, k
    return (b / a - 1) * 100.0, k


def graham_zahl(eps, bvps):
    """sqrt(22,5 x EPS x Buchwert je Aktie) - nur fuer positive EPS und Buchwert definiert."""
    eps, bvps = zahl(eps), zahl(bvps)
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(22.5 * eps * bvps)


def graham_formel(eps, g, y=None, basis=None):
    """Revidierte Graham-Formel V = EPS x (8,5 + 2g) x 4,4 / Y (g und Y in Prozent)."""
    eps, g = zahl(eps), zahl(g)
    y = zahl(y if y is not None else C.AAA_RENDITE)
    basis = C.GRAHAM["formel_basis_kgv"] if basis is None else basis
    if eps is None or g is None or not y or eps <= 0:
        return None
    return eps * (basis + 2 * g) * 4.4 / y


@registriere("graham", "Benjamin Graham", "Value", 10)
def check(f, kx):
    cfg = C.GRAHAM
    n = len(f.get("jahre") or [])
    eing = f"{n} von {C.SOLL_JAHRE} Jahren" if n < C.SOLL_JAHRE else None
    kurs = f.get("kurs_in_bericht")
    kr = []

    # 1. Groesse
    ums = letztes(f, "umsatz")
    ums_usd = ums * f["usd_faktor"] if ums is not None and f.get("usd_faktor") else None
    kr.append(kriterium("groesse", "Ausreichende Größe (Umsatz)", ums_usd, cfg["min_umsatz_usd"],
                        None if ums_usd is None else ums_usd > cfg["min_umsatz_usd"],
                        "Kleine Firmen sind anfälliger – Graham wollte etablierte Unternehmen.", fmt="usd"))
    # 2. Current Ratio
    cr = teile(letztes(f, "umlauf"), letztes(f, "kurzfr_verb"))
    kr.append(kriterium("current_ratio", "Current Ratio", cr, cfg["min_current_ratio"],
                        None if cr is None else cr >= cfg["min_current_ratio"],
                        "Umlaufvermögen soll die kurzfristigen Schulden mindestens doppelt decken.", fmt="x"))
    # 3. Langfristige Schulden <= Net Current Assets
    umlauf, kv = letztes(f, "umlauf"), letztes(f, "kurzfr_verb")
    lfs = letztes(f, "langfr_schulden")
    if lfs is None and umlauf is not None and (letztes(f, "schulden") or 0) == 0:
        lfs = 0.0                   # Yahoo laesst die Zeile weg, wenn es keine Schulden gibt
    nca = umlauf - kv if umlauf is not None and kv is not None else None
    kr.append(kriterium("schulden_nca", "Langfr. Schulden ≤ Netto-Umlaufvermögen", lfs, nca,
                        None if lfs is None or nca is None else lfs <= nca,
                        "Die langfristigen Schulden sollen aus dem Netto-Umlaufvermögen tilgbar sein.", fmt="geld"))
    # 4. Gewinnstabilitaet
    ng = vorhanden(reihe(f, "nettogewinn"))
    kr.append(kriterium("gewinn_stabil", "Gewinn in allen Jahren positiv",
                        f"{sum(1 for x in ng if x > 0)} von {len(ng)}", "alle",
                        None if len(ng) < 2 else all(x > 0 for x in ng),
                        "Kein Verlustjahr – Graham verlangte 10 Jahre ohne Verlust.",
                        eingeschraenkt=eing, fmt="text"))
    # 5. Dividendenhistorie
    ohne_luecke, abgedeckt = dividenden_jahre_ohne_luecke(f)
    if abgedeckt:
        ok = ohne_luecke >= min(20, abgedeckt)
        kr.append(kriterium("dividende", "Ununterbrochene Dividende", f"{ohne_luecke} Jahre",
                            f"{min(20, abgedeckt)} Jahre", ok,
                            "Graham wollte 20 Jahre Dividende ohne Unterbrechung.",
                            eingeschraenkt=f"{abgedeckt} von 20 Jahren" if abgedeckt < 20 else None, fmt="text"))
    else:
        div = vorhanden(reihe(f, "dividenden"))
        kr.append(kriterium("dividende", "Ununterbrochene Dividende", "keine" if div and not any(div) else "n/a",
                            "20 Jahre", False if div and not any(div) else None,
                            "Graham wollte 20 Jahre Dividende ohne Unterbrechung.", fmt="text"))
    # 6. Gewinnwachstum
    g, k = eps_wachstum_perioden(reihe(f, "eps"))
    g_min = schwelle_versorger(f, cfg["eps_wachstum_min"], "wachstum")
    kr.append(kriterium("eps_wachstum", "EPS-Wachstum über den Zeitraum", g, g_min,
                        None if g is None else g >= g_min,
                        f"Ø der ersten {k} vs. letzten {k} Jahre; Graham: +33 % über 10 Jahre (Ø 3 vs. Ø 3)." if k
                        else "Mindestens 3 Jahre mit Gewinn je Aktie nötig.",
                        eingeschraenkt=eing, fmt="pct"))
    # 7. Moderate Bewertung
    eps_avg = mittel(reihe(f, "eps")[-3:])
    bvps = teile(letztes(f, "ek"), letztes(f, "aktien") or f.get("aktien"))
    kgv = teile(kurs, eps_avg) if eps_avg and eps_avg > 0 else None
    kbv = teile(kurs, bvps) if bvps and bvps > 0 else None
    if eps_avg is not None and eps_avg <= 0:
        ok7, wert7 = False, "Verlust"
    elif kgv is None:
        ok7, wert7 = None, None
    else:
        ok7 = kgv <= cfg["max_kgv"] and (kbv is not None and kgv * kbv <= cfg["max_kgv_mal_kbv"])
        wert7 = f"KGV {de(kgv)} · KGV×KBV {de(kgv * kbv)}" if kbv is not None else f"KGV {de(kgv)} · KBV n/a"
        if kbv is None:
            ok7 = None if kgv <= cfg["max_kgv"] else False
    kr.append(kriterium("kgv", "Moderate Bewertung", wert7, "KGV ≤ 15 und KGV×KBV ≤ 22,5", ok7,
                        "KGV auf Basis des 3-Jahres-Ø-Gewinns; negatives Ergebnis zählt als nicht erfüllt.",
                        fmt="text"))

    # Zusatz: Graham-Zahl, Graham-Formel, Net-Net
    extras, badges = [], []
    eps = letztes(f, "eps")
    gz = graham_zahl(eps, bvps)
    mos = (gz - kurs) / gz * 100 if gz and kurs else None
    extras.append(extra("Graham-Zahl", gz, "√(22,5 × EPS × Buchwert je Aktie)" +
                        (f" · Sicherheitsmarge {mos:+.0f} % zum Kurs" if mos is not None else
                         " · n/a bei Verlust oder negativem Eigenkapital"), fmt="kurs"))
    eps_reihe = vorhanden(reihe(f, "eps"))
    g_hist = cagr(eps_reihe[-1], eps_reihe[0], len(eps_reihe) - 1) if len(eps_reihe) >= 2 else None
    g_formel = max(0.0, min(cfg["formel_g_max"], g_hist)) if g_hist is not None else None
    gf = graham_formel(eps, g_formel)
    extras.append(extra("Graham-Formel (revidiert)", gf,
                        f"V = EPS × (8,5 + 2g) × 4,4 / Y mit g = {de(g_formel)} % (hist. EPS-Wachstum p. a., "
                        f"auf 0–{cfg['formel_g_max']:.0f} % begrenzt), Y = {de(C.AAA_RENDITE)} % (AAA-Rendite, "
                        f"Annahme {C.ANNAHMEN_STAND})" if g_formel is not None else
                        "n/a – kein positives Gewinnwachstum berechenbar", fmt="kurs"))
    ncav = teile((letztes(f, "umlauf") or 0) - (letztes(f, "verbindlichkeiten") or 0)
                 if letztes(f, "umlauf") is not None and letztes(f, "verbindlichkeiten") is not None else None,
                 letztes(f, "aktien") or f.get("aktien"))
    extras.append(extra("Net-Net (NCAV je Aktie)", ncav,
                        "(Umlaufvermögen − alle Verbindlichkeiten) je Aktie; Kurs < ⅔ davon = „Deep Value“",
                        fmt="kurs"))
    if ncav and kurs and ncav > 0 and kurs < cfg["ncav_faktor"] * ncav:
        badges.append("Deep Value (Net-Net)")
    return ergebnis("graham", "Benjamin Graham", "Defensiver Investor: groß, solide, beständig, günstig.",
                    "Value", kr, f, extras=extras, badges=badges, info=INFO)
