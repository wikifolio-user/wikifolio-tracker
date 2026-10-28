"""William O'Neil - CAN SLIM.

Quelle: W. O'Neil, "How to Make Money in Stocks" (4. Aufl. 2009). C = aktuelles Quartals-EPS >= +25 % ggue.
Vorjahresquartal, A = jaehrliches EPS-Wachstum >= 25 % (3 Jahre), N = nahe Hoch, S = Angebot/Nachfrage (Volumen),
L = Leader (Relative Staerke >= 80), I = institutionelle Unterstuetzung, M = Marktrichtung (Index > 200-Tage-Linie).
"""
import investor_config as C

from . import registriere
from .basis import de, ergebnis, kriterium, wachstum, zahl
from .daten import kurs_tief_hoch, sma
from .kurs import relative_staerke, schluss

INFO = ("William O'Neil (1933–2023), Gründer von Investor's Business Daily, untersuchte die größten Kursgewinner "
        "seit 1880 und fasste ihre Gemeinsamkeiten in sieben Buchstaben zusammen: CAN SLIM.")


def quartals_wachstum(f):
    """EPS juengstes Quartal vs. gleiches Quartal im Vorjahr (Index -1 vs. -5). Negativer Vorjahreswert -> None."""
    q = [x.get("eps") for x in f.get("quartale") or []]
    if len(q) < 5 or q[-1] is None or q[-5] is None:
        return None
    return wachstum(q[-1], q[-5])


def jahres_wachstum(f, n=3):
    """EPS-Wachstum der letzten n Jahre einzeln (%). -> Liste oder None bei zu kurzer Historie."""
    eps = [j.get("eps") for j in f.get("jahre") or []]
    if len(eps) < n + 1:
        return None
    return [wachstum(eps[-i], eps[-i - 1]) for i in range(n, 0, -1)]


def volumen_verhaeltnis(f, tage=50):
    """Summe Volumen an Aufwaerts- / an Abwaertstagen der letzten `tage` Handelstage."""
    k = (f.get("kurse") or [])[-(tage + 1):]
    if len(k) < tage + 1:
        return None
    auf = sum(v for (_, c, v), (_, c0, _) in zip(k[1:], k[:-1]) if c > c0)
    ab = sum(v for (_, c, v), (_, c0, _) in zip(k[1:], k[:-1]) if c < c0)
    return auf / ab if ab else None


@registriere("can_slim", "William O'Neil (CAN SLIM)", "Momentum", 140)
def check(f, kx):
    cfg = C.CANSLIM
    c = quartals_wachstum(f)
    a = jahres_wachstum(f)
    a_ok = None if a is None or any(x is None for x in a) else all(x >= cfg["a_min"] for x in a)
    kurs = (schluss(f) or [None])[-1]
    _, hoch = kurs_tief_hoch(f, 365)
    abstand = (1 - kurs / hoch) * 100 if kurs and hoch else None
    vv = volumen_verhaeltnis(f, cfg["s_tage"])
    rs, _ = relative_staerke(f, kx)
    inst = zahl((f.get("short") or {}).get("heldPercentInstitutions"))
    idx = [x for _, x, _ in f.get("index_kurse") or []]
    m_sma = sma(idx, cfg["m_sma"])
    kr = [kriterium("c", "C – Quartals-EPS ≥ +25 %", c, cfg["c_min"], None if c is None else c >= cfg["c_min"],
                    "Jüngstes Quartal vs. gleiches Quartal im Vorjahr.", fmt="pct"),
          kriterium("a", "A – Jahres-EPS ≥ +25 % (3 Jahre)", " / ".join(de(x, 0) + " %" if x is not None else "n/a"
                                                                        for x in a) if a else None,
                    "jedes Jahr ≥ 25 %", a_ok, "Jedes der letzten drei Jahre einzeln.", fmt="text"),
          kriterium("n", "N – Kurs nahe 52-Wochen-Hoch", abstand, f"≤ {cfg['n_max_abstand']:.0f} % darunter",
                    None if abstand is None else abstand <= cfg["n_max_abstand"],
                    "Neue Produkte, neues Management, neue Hochs – Gewinner notieren nahe am Hoch.", fmt="pct"),
          kriterium("s", "S – Volumen an Aufwärtstagen > Abwärtstagen", vv, "> 1", None if vv is None else vv > 1,
                    f"Verhältnis der Volumina der letzten {cfg['s_tage']} Handelstage (Nachfrage > Angebot).",
                    fmt="x"),
          kriterium("l", "L – Relative Stärke ≥ 80", rs, cfg["l_min_rs"], None if rs is None else rs >= cfg["l_min_rs"],
                    "Perzentil der 12-Monats-Performance unter den Top-500-Aktien.", fmt="zahl0"),
          kriterium("i", "I – Institutionelle Investoren beteiligt", inst * 100 if inst is not None else None, "> 0 %",
                    None if inst is None else inst > 0,
                    "Anteil institutioneller Investoren (Yahoo). Ob er steigt, liefert die kostenlose Quelle nicht.",
                    fmt="pct"),
          kriterium("m", "M – Markt im Aufwärtstrend", f.get("index_name") or None, "Index > 200-Tage-Linie",
                    None if m_sma is None else idx[-1] > m_sma,
                    f"{f.get('index_name') or 'Leitindex'} über seinem 200-Tage-Durchschnitt.", fmt="text")]
    return ergebnis("can_slim", "William O'Neil (CAN SLIM)", "Wachstumsführer mit Rückenwind von Markt und Profis.",
                    "Momentum", kr, f, info=INFO)
