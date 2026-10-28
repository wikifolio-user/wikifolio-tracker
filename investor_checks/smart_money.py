"""Smart-Money-Signale: Insider, Rueckkaeufe, Analysten, Leerverkaeufer.

Quellen der Daten: Yahoo Finance (Insider-Meldungen, v. a. US-Formular 4; Analystenkonsens, Kursziele,
Schaetzungsrevisionen; Short Interest nur fuer US-Werte). Superinvestoren-Positionen (13F) gibt es nicht
in einer sauber nutzbaren kostenlosen Quelle - bewusst weggelassen.
"""
import datetime

import investor_config as C

from . import registriere
from .basis import de, ergebnis, kriterium, reihe, vorhanden, zahl

INFO = ("„Smart Money“: Was tun die, die mehr wissen oder genauer hinsehen? Insider kaufen mit eigenem Geld, "
        "Firmen kaufen eigene Aktien zurück, Analysten ändern ihre Schätzungen, Leerverkäufer wetten dagegen.")


def insider_bilanz(f, monate=6, heute=None):
    """(Kaufvolumen, Verkaufsvolumen, Anzahl Kaeufe, Anzahl Verkaeufe) der letzten `monate`."""
    heute = heute or datetime.date.today()
    grenze = (heute - datetime.timedelta(days=int(monate * 30.5))).isoformat()
    k = [t for t in f.get("insider") or [] if t["datum"] >= grenze]
    kauf = [t for t in k if t["art"] == "kauf"]
    verk = [t for t in k if t["art"] == "verkauf"]
    return sum(t["wert"] for t in kauf), sum(t["wert"] for t in verk), len(kauf), len(verk)


@registriere("smart_money", "Smart-Money-Signale", "Signale", 180)
def check(f, kx, heute=None):
    cfg = C.SMART_MONEY
    kv, vv, nk, nv = insider_bilanz(f, cfg["insider_monate"], heute)
    hat_insider = bool(f.get("insider"))
    ak = vorhanden(reihe(f, "aktien"))
    a1 = (ak[-1] / ak[-2] - 1) * 100 if len(ak) >= 2 and ak[-2] else None
    a3 = (ak[-1] / ak[-4] - 1) * 100 if len(ak) >= 4 and ak[-4] else None
    an = f.get("analysten") or {}
    rating = zahl(an.get("recommendationMean"))
    ziel = zahl(an.get("targetMeanPrice"))
    abst = (ziel / f["kurs"] - 1) * 100 if ziel and f.get("kurs") else None
    rev = (f.get("revisionen") or {}).get("0y") or {}
    hoch, runter = zahl(rev.get("hoch30")), zahl(rev.get("runter30"))
    short = zahl((f.get("short") or {}).get("shortPercentOfFloat"))
    short = short * 100 if short is not None and short < 1 else short
    kr = [kriterium("insider", f"Insider: Käufe ≥ Verkäufe ({cfg['insider_monate']} Monate)",
                    f"{nk} Käufe / {nv} Verkäufe" if hat_insider else None, "Kaufvolumen ≥ Verkaufsvolumen",
                    None if not hat_insider or (nk + nv) == 0 else kv >= vv,
                    (f"Volumen Käufe {de(kv / 1e6)} Mio., Verkäufe {de(vv / 1e6)} Mio. (Handelswährung). "
                     "Zuteilungen und Optionsausübungen zählen nicht.") if hat_insider else
                    "Keine Insider-Meldungen verfügbar (außerhalb der USA meist lückenhaft).", fmt="text"),
          kriterium("rueckkauf_1j", "Aktienanzahl 1 Jahr", a1, "≤ 0 %", None if a1 is None else a1 <= 0,
                    "Sinkende Aktienanzahl = Rückkäufe.", fmt="pct"),
          kriterium("rueckkauf_3j", "Aktienanzahl 3 Jahre", a3, "≤ 0 %", None if a3 is None else a3 <= 0,
                    "Veränderung über drei Geschäftsjahre.", fmt="pct"),
          kriterium("rating", "Analysten-Konsens", rating, f"≤ {de(cfg['max_rating'])} (Kaufen)",
                    None if rating is None else rating <= cfg["max_rating"],
                    f"Skala 1 = Strong Buy … 5 = Sell · {int(an.get('numberOfAnalystOpinions') or 0)} Analysten.",
                    fmt="zahl"),
          kriterium("kursziel", "Kursziel über Kurs", abst, f"≥ +{cfg['min_kursziel_abstand']:.0f} %",
                    None if abst is None else abst >= cfg["min_kursziel_abstand"],
                    "Durchschnittliches Analysten-Kursziel vs. aktueller Kurs.", fmt="pct"),
          kriterium("revisionen", "Gewinnschätzungen 30 Tage", f"{int(hoch or 0)} hoch / {int(runter or 0)} runter"
                    if hoch is not None or runter is not None else None, "mehr hoch als runter",
                    None if hoch is None and runter is None else (hoch or 0) >= (runter or 0) and (hoch or 0) > 0,
                    "Anzahl Analysten, die die EPS-Schätzung fürs laufende Jahr in 30 Tagen angehoben/gesenkt haben.",
                    fmt="text"),
          kriterium("short", "Leerverkaufsquote niedrig", short, f"< {cfg['max_short_float']:.0f} %",
                    None if short is None else short < cfg["max_short_float"],
                    "Anteil leerverkaufter Aktien am Streubesitz (nur US-Werte).", fmt="pct")]
    return ergebnis("smart_money", "Smart-Money-Signale", "Insider, Rückkäufe, Analysten und Leerverkäufer.",
                    "Signale", kr, f, info=INFO)
