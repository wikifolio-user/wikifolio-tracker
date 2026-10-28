"""Mark Minervini - Trend Template (8 Kriterien).

Quelle: M. Minervini, "Trade Like a Stock Market Wizard" (2013), Kap. 5 "Trading with the Trend": Kurs ueber
150-/200-Tage-Linie, 150 > 200, 200-Tage-Linie steigt seit mind. 1 Monat, 50 > 150 und 200, Kurs > 50-Tage-Linie,
mind. 30 % ueber dem 52-Wochen-Tief, hoechstens 25 % unter dem 52-Wochen-Hoch, Relative Staerke >= 70.
"""
import investor_config as C

from . import registriere
from .basis import ergebnis, kriterium
from .daten import kurs_tief_hoch, sma
from .kurs import relative_staerke, schluss

INFO = ("Mark Minervini (*1964), US-Investmentmeister 1997 und 2021: kauft nur Aktien in einem klaren "
        "Aufwärtstrend („Stage 2“) – sein Trend Template filtert sie mit acht Regeln.")


@registriere("minervini", "Mark Minervini", "Momentum", 150)
def check(f, kx):
    cfg = C.MINERVINI
    w = schluss(f)
    kurs = w[-1] if w else None
    s50, s150, s200 = sma(w, 50), sma(w, 150), sma(w, 200)
    t = cfg["sma200_steigt_tage"]
    s200_vor = sma(w[:-t], 200) if len(w) > 200 + t else None
    tief, hoch = kurs_tief_hoch(f, 365)
    ueber_tief = (kurs / tief - 1) * 100 if kurs and tief else None
    unter_hoch = (1 - kurs / hoch) * 100 if kurs and hoch else None
    rs, _ = relative_staerke(f, kx)

    def vgl(a, b):
        return None if a is None or b is None else a > b

    kr = [kriterium("k150_200", "Kurs > 150- und 200-Tage-Linie", kurs, "über beiden",
                    None if None in (kurs, s150, s200) else kurs > s150 and kurs > s200, "Langfristiger Aufwärtstrend.",
                    fmt="kurs"),
          kriterium("150_200", "150-Tage > 200-Tage-Linie", s150, s200, vgl(s150, s200), "Die Trendlinien sind "
                    "richtig geordnet.", fmt="kurs"),
          kriterium("200_steigt", "200-Tage-Linie steigt seit 1 Monat", s200, s200_vor, vgl(s200, s200_vor),
                    f"Vergleich mit dem Stand vor {t} Handelstagen.", fmt="kurs"),
          kriterium("50_ueber", "50-Tage > 150- und 200-Tage-Linie", s50, "über beiden",
                    None if None in (s50, s150, s200) else s50 > s150 and s50 > s200, "Kurzfristiger Trend stärker.",
                    fmt="kurs"),
          kriterium("k50", "Kurs > 50-Tage-Linie", kurs, s50, vgl(kurs, s50), "Aktuell im Aufwärtsschwung.",
                    fmt="kurs"),
          kriterium("tief", "≥ 30 % über 52-Wochen-Tief", ueber_tief, cfg["min_ueber_tief"],
                    None if ueber_tief is None else ueber_tief >= cfg["min_ueber_tief"],
                    "Abstand vom Jahrestief.", fmt="pct"),
          kriterium("hoch", "≤ 25 % unter 52-Wochen-Hoch", unter_hoch, cfg["max_unter_hoch"],
                    None if unter_hoch is None else unter_hoch <= cfg["max_unter_hoch"],
                    "Nicht zu weit vom Jahreshoch entfernt.", fmt="pct"),
          kriterium("rs", "Relative Stärke ≥ 70", rs, cfg["min_rs"], None if rs is None else rs >= cfg["min_rs"],
                    "Perzentil der 12-Monats-Performance unter den Top-500-Aktien.", fmt="zahl0")]
    return ergebnis("minervini", "Mark Minervini", "Trend Template: nur Aktien im klaren Aufwärtstrend.", "Momentum",
                    kr, f, info=INFO) | {"chart": len(w) >= 200}
