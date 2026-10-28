"""Robert Levy - Relative Staerke nach Levy (RSL).

Quelle: R. Levy, "Relative Strength as a Criterion for Investment Selection", Journal of Finance 22 (1967):
RSL = aktueller Kurs / Durchschnitt der letzten 27 Wochenschlusskurse. RSL > 1 = Aufwaertstrend; gekauft werden
die Aktien mit dem hoechsten RSL.
"""
import scoring as SC

import investor_config as C

from . import registriere
from .basis import de, ergebnis, kriterium, zahl
from .kurs import schluss

INFO = ("Robert Levy zeigte 1967, dass Aktien mit der stärksten relativen Kursentwicklung der letzten Monate "
        "auch danach überdurchschnittlich liefen – ein Vorläufer der Momentum-Strategien.")


def rsl(f, wochen=None):
    """Kurs / Schnitt der letzten `wochen` Wochenschlusskurse (jeder 5. Handelstag vom juengsten zurueck)."""
    wochen = C.LEVY["wochen"] if wochen is None else wochen
    w = schluss(f)
    woche = w[::-1][::5][:wochen]
    if len(woche) < wochen:
        return None
    return w[-1] / (sum(woche) / len(woche))


@registriere("levy", "Robert Levy (RSL)", "Momentum", 160)
def check(f, kx):
    cfg = C.LEVY
    r = rsl(f)
    p6 = zahl((((kx or {}).get("agent") or {}).get("k") or {}).get("p6"))
    rang = SC.perzentil(((kx or {}).get("verteilungen") or {}).get(("aktie", "p6")) or [], p6, +1) \
        if p6 is not None else None
    kr = [kriterium("rsl", "RSL > 1", r, de(cfg["min_rsl"], 2), None if r is None else r > cfg["min_rsl"],
                    f"Kurs / Ø der letzten {cfg['wochen']} Wochenschlusskurse (≈ 6 Monate).", fmt="zahl"),
          kriterium("rang", "Rang in den Top 500", rang, cfg["min_rang"], None if rang is None else rang >= cfg["min_rang"],
                    "Näherung: Perzentil der 6-Monats-Performance (≈ Zeitraum des RSL) unter den Top-500-Aktien – "
                    "ein RSL liegt nicht für alle Werte vor.", fmt="zahl0")]
    return ergebnis("levy", "Robert Levy (RSL)", "Die stärksten Aktien der letzten 6 Monate kaufen.", "Momentum", kr, f,
                    info=INFO, score=None if r is None or rang is None else
                    (100.0 if r > cfg["min_rsl"] and rang >= cfg["min_rang"] else 50.0 if r > cfg["min_rsl"] else 0.0))
