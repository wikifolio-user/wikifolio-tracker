"""Kurs-Hilfen fuer Momentum-Checks: Schlusskurse, gleitende Durchschnitte, Performance, Relative Staerke."""
import scoring as SC

from .basis import zahl
from .daten import sma


def schluss(f):
    return [c for _, c, _ in f.get("kurse") or []]


def performance(werte, tage):
    """Kursveraenderung in % ueber die letzten `tage` Handelstage."""
    if len(werte) <= tage or not werte[-1 - tage]:
        return None
    return (werte[-1] / werte[-1 - tage] - 1) * 100


def relative_staerke(f, kx, tage=252, key="p12"):
    """Relative Staerke 0-100: Perzentil der Performance (12 Monate) unter allen Top-500-Aktien.
    Eigene Performance aus der Kurshistorie, sonst aus den Top-500-Daten."""
    p = performance(schluss(f), tage)
    if p is None:
        p = zahl((((kx or {}).get("agent") or {}).get("k") or {}).get(key))
    liste = ((kx or {}).get("verteilungen") or {}).get(("aktie", key)) or []
    return SC.perzentil(liste, p, +1), p


def smas(werte, n, schritte=1):
    """Gleitender Durchschnitt fuer jeden Tag (fuer das Chart): Liste gleicher Laenge, anfangs None."""
    aus, summe = [], 0.0
    for i, w in enumerate(werte):
        summe += w
        if i >= n:
            summe -= werte[i - n]
        aus.append(summe / n if i >= n - 1 else None)
    return aus


__all__ = ["schluss", "performance", "relative_staerke", "smas", "sma"]
