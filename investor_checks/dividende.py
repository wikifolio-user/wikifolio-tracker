"""Dividende & Aktionaersrendite.

Quellen: Chowder-Regel (Forum "Seeking Alpha", Chowder 2006): Dividendenrendite + 5-J.-Dividendenwachstum >= 12 %
(Versorger >= 8 %). Shareholder Yield: M. Faber, "Shareholder Yield" (2013) = Dividendenrendite +
Netto-Rueckkaufrendite + Schuldenabbau-Rendite.
"""
import datetime

import investor_config as C

from . import registriere
from .basis import cagr, de, ergebnis, extra, kriterium, letztes, pct, sektor_typ, teile

INFO = ("Dividenden-Investoren achten auf verlässlich steigende Ausschüttungen, die gut durch Gewinn und Cashflow "
        "gedeckt sind. Die Chowder-Regel verbindet Rendite und Wachstum; der Shareholder Yield (Meb Faber) zählt "
        "auch Rückkäufe und Schuldenabbau mit.")


def jahressummen(f, heute=None):
    """{jahr: Summe der Dividenden je Aktie} fuer volle Kalenderjahre."""
    letztes_volles = (heute or datetime.date.today()).year - 1
    aus = {}
    for d, b in f.get("dividenden_hist") or []:
        j = int(d[:4])
        if j <= letztes_volles and b:
            aus[j] = aus.get(j, 0.0) + b
    return aus


def jahre_ohne_kuerzung(summen):
    """Aufeinanderfolgende Jahre (vom juengsten zurueck), in denen die Dividende nicht gesunken ist."""
    if not summen:
        return 0
    jahre = sorted(summen)
    n = 0
    for j in reversed(jahre[1:]):
        vor = summen.get(j - 1)
        if vor is None or summen[j] < vor * 0.99:        # 1 % Toleranz fuer Waehrungs-/Rundungseffekte
            break
        n += 1
    return n


def rendite_ttm(f, heute=None):
    """Dividendenrendite der letzten 12 Monate in % (Zahlungen / aktueller Kurs, beides in Handelswaehrung)."""
    heute = heute or datetime.date.today()
    grenze = (heute - datetime.timedelta(days=365)).isoformat()
    summe = sum(b for d, b in f.get("dividenden_hist") or [] if d >= grenze)
    return pct(summe, f.get("kurs")) if f.get("kurs") else None


def shareholder_yield(f):
    """(gesamt, dividende, rueckkauf netto, schuldenabbau) in % des Boersenwerts (Berichtswaehrung)."""
    faktor = teile(f.get("kurs_in_bericht"), f.get("kurs"))
    mcap = f["mcap"] * faktor if f.get("mcap") and faktor else None
    if not mcap:
        return None
    d = pct(letztes(f, "dividenden") or 0, mcap)
    r = pct((letztes(f, "rueckkaeufe") or 0) - (letztes(f, "emissionen") or 0), mcap)
    s_alt, s_neu = letztes(f, "schulden", 1), letztes(f, "schulden")
    s = pct(s_alt - s_neu, mcap) if s_alt is not None and s_neu is not None else 0.0
    return d + r + s, d, r, s


@registriere("dividende", "Dividenden-Check", "Dividende", 170)
def check(f, kx, heute=None):
    cfg = C.DIVIDENDE
    summen = jahressummen(f, heute)
    ohne = jahre_ohne_kuerzung(summen)
    jahre = sorted(summen)
    c5 = cagr(summen[jahre[-1]], summen.get(jahre[-1] - 5), 5) if jahre and summen.get(jahre[-1] - 5) else None
    rend = rendite_ttm(f, heute)
    if not rend and jahre and f.get("kurs"):
        # Jahreszahler mit verschobenem Termin: dann die Summe des letzten vollen Jahres
        rend = pct(summen[jahre[-1]], f["kurs"]) if jahre[-1] >= (heute or datetime.date.today()).year - 1 else rend
    zahlt = bool(summen) and rend is not None and rend > 0
    q_gew = pct(letztes(f, "dividenden"), letztes(f, "nettogewinn")) if (letztes(f, "nettogewinn") or 0) > 0 else None
    q_fcf = pct(letztes(f, "dividenden"), letztes(f, "fcf")) if (letztes(f, "fcf") or 0) > 0 else None
    chowder_min = cfg["chowder_versorger"] if sektor_typ(f) == "versorger" else cfg["chowder"]
    chowder = rend + c5 if rend is not None and c5 is not None else None
    sy = shareholder_yield(f)
    if not zahlt and f.get("dividenden_hist") is not None and f.get("jahre"):
        kr = [kriterium("zahlt", "Zahlt Dividende", "nein", "ja", False,
                        "Keine Dividende in den letzten 12 Monaten.", fmt="text")]
    else:
        kr = [kriterium("zahlt", "Zahlt Dividende", rend, "> 0 %", None if rend is None else rend > 0,
                        "Rendite der letzten 12 Monate.", fmt="pct")]
    kr += [kriterium("ohne_kuerzung", "Jahre ohne Kürzung", ohne if summen else None,
                     f"≥ {cfg['min_jahre_ohne_kuerzung']}", None if not summen else ohne >= cfg["min_jahre_ohne_kuerzung"],
                     f"Aufeinanderfolgende Jahre mit gleicher oder höherer Dividende (Historie ab {jahre[0]})."
                     if jahre else "Keine Dividendenhistorie.", fmt="zahl0"),
           kriterium("cagr5", "Dividendenwachstum 5 Jahre p. a.", c5, cfg["min_cagr5"],
                     None if c5 is None else c5 >= cfg["min_cagr5"], "Durchschnittliches Wachstum je Aktie p. a.",
                     fmt="pct"),
           kriterium("quote_gewinn", "Ausschüttungsquote (Gewinn)", q_gew, f"≤ {cfg['max_quote_gewinn']:.0f} %",
                     None if q_gew is None else q_gew <= cfg["max_quote_gewinn"], "Dividenden / Nettogewinn.", fmt="pct"),
           kriterium("quote_fcf", "Ausschüttungsquote (Free Cashflow)", q_fcf, f"≤ {cfg['max_quote_fcf']:.0f} %",
                     None if q_fcf is None else q_fcf <= cfg["max_quote_fcf"], "Dividenden / Free Cashflow.", fmt="pct"),
           kriterium("chowder", "Chowder-Regel", chowder, f"≥ {chowder_min:.0f} %",
                     None if chowder is None else chowder >= chowder_min,
                     f"Rendite {de(rend)} % + 5-J.-Wachstum {de(c5)} %" + (" (Versorger: 8 %)"
                                                                         if chowder_min != cfg["chowder"] else "")
                     if chowder is not None else "Rendite und 5-Jahres-Wachstum nötig.", fmt="pct"),
           kriterium("shareholder_yield", "Shareholder Yield", sy[0] if sy else None,
                     f"≥ {cfg['min_shareholder_yield']:.0f} %",
                     None if not sy else sy[0] >= cfg["min_shareholder_yield"],
                     (f"Dividende {de(sy[1])} % + Rückkäufe netto {de(sy[2])} % + Schuldenabbau {de(sy[3])} %"
                      if sy else "Börsenwert fehlt."), fmt="pct")]
    extras = [extra("Dividende je Aktie (letzte Jahre)", " · ".join(f"{j}: {de(summen[j], 2)}" for j in jahre[-6:]),
                    "Summe der Zahlungen je Kalenderjahr (Handelswährung).", fmt="text")] if jahre else []
    return ergebnis("dividende", "Dividenden-Check", "Verlässliche, wachsende und gedeckte Ausschüttung.",
                    "Dividende", kr, f, extras=extras, info=INFO)
