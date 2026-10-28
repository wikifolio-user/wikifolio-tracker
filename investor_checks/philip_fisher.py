"""Philip Fisher - Wachstum mit Qualitaet (die quantifizierbaren seiner 15 Punkte).

Quelle: P. Fisher, "Common Stocks and Uncommon Profits" (1958), Kap. 3 "What to Buy - The Fifteen Points".
Quantifiziert: Umsatzwachstum (Punkt 1), F&E-Aufwand (3), Margen (5/6), keine Verwaesserung (13),
Vertriebseffizienz (4). Die uebrigen Punkte sind qualitativ (Scuttlebutt) - siehe Checkliste.
"""
import investor_config as C

from . import registriere
from .basis import cagr, ergebnis, kriterium, letztes, pct, reihe, schwelle_versorger, vorhanden

INFO = ("Philip Fisher (1907–2004) prägte das Wachstums-Investing und beeinflusste Warren Buffett: Er kaufte "
        "innovative Firmen mit überdurchschnittlichem, dauerhaftem Wachstum und hielt sie Jahrzehnte.")


@registriere("philip_fisher", "Philip Fisher", "Qualität", 80)
def check(f, kx):
    cfg = C.PHILIP_FISHER
    J = f.get("jahre") or []
    n = len(J)
    ums = vorhanden(reihe(f, "umsatz"))
    g = cagr(ums[-1], ums[0], len(ums) - 1) if len(ums) >= 2 else None
    fue = pct(letztes(f, "fue"), letztes(f, "umsatz"))
    med = ((kx or {}).get("fue_median") or {}).get(f.get("sektor") or "")
    om = [pct(j.get("ebit"), j.get("umsatz")) for j in J]
    omv = vorhanden(om)
    ak = vorhanden(reihe(f, "aktien"))
    vera = cagr(ak[-1], ak[0], len(ak) - 1) if len(ak) >= 2 else None
    sga = vorhanden([pct(j.get("sga"), j.get("umsatz")) for j in J])
    eing = f"{n} von {C.SOLL_JAHRE} Jahren" if n < C.SOLL_JAHRE else None
    g_min = schwelle_versorger(f, cfg["min_umsatzwachstum"], "wachstum")
    kr = [kriterium("umsatz", f"Umsatzwachstum > {g_min:.0f} % p. a.", g, g_min,
                    None if g is None else g > g_min, "Durchschnitt p. a. über den Zeitraum." +
                    (" Versorger: halbierte Schwelle." if g_min != cfg["min_umsatzwachstum"] else ""),
                    eingeschraenkt=eing, fmt="pct"),
          kriterium("fue", "F&E-Quote über Sektor-Median", fue, med if med is not None else "Sektor-Median",
                    None if fue is None or med is None else fue > med,
                    "F&E-Aufwand / Umsatz." + ("" if med is not None else
                                               " Sektor-Vergleich folgt mit der Vorberechnung (Screener)."),
                    fmt="pct"),
          kriterium("marge", "Steigende operative Marge", (omv[-1] - omv[0]) if len(omv) >= 2 else None, "> 0 Pp.",
                    None if len(omv) < 2 else omv[-1] > omv[0],
                    "Veränderung der EBIT-Marge vom ältesten zum jüngsten Jahr (Prozentpunkte).", fmt="pp"),
          kriterium("verwaesserung", "Keine starke Verwässerung", vera, f"< {cfg['max_verwaesserung']:.0f} % p. a.",
                    None if vera is None else vera < cfg["max_verwaesserung"], "Veränderung der Aktienanzahl p. a.",
                    fmt="pct"),
          kriterium("sga", "Vertriebskosten-Effizienz", (sga[-1] - sga[0]) if len(sga) >= 2 else None, "sinkend",
                    None if len(sga) < 2 else sga[-1] < sga[0],
                    "Vertriebs- und Verwaltungskosten (SG&A) / Umsatz sollen sinken.", fmt="pp")]
    return ergebnis("philip_fisher", "Philip Fisher", "Dauerhaftes Wachstum mit steigender Effizienz.",
                    "Wachstum", kr, f, info=INFO)
