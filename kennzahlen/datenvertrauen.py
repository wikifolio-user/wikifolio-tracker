"""data_confidence_score (0-100): wie belastbar ist die Bewertung eines Werts?

Teilbewertungen (Gewicht):
  Vollstaendigkeit (35)  Anteil der Score-Punkte, fuer die Daten vorlagen (fehlende_punkte des Agenten);
                         ohne diese Angabe: Anteil vorhandener Pflichtkennzahlen
  Historie (20)          Anzahl Geschaeftsjahre (5 = volle Punkte; yfinance liefert meist 4)
  Aktualitaet (15)       Alter der Bewertungsdaten (Datei- bzw. Check-Datum)
  Konsistenz (15)        Plausibilitaet zentraler Werte (Kurs, Boersenwert, Waehrung, Kennzahl-Bereiche)
  Schaetzanteil (15)     wie stark die Bewertung auf Analystenschaetzungen beruht (erwartetes KGV, Revisionen)

Nicht anwendbare Kennzahlen (z. B. Bruttomarge bei Banken) zaehlen nicht als fehlend.
Das Datenvertrauen veraendert keinen Score - es wird nur angezeigt.
"""
import datetime

from . import branchenmodell as BR
from . import definitionen as D
from .fehlwerte import datenluecke_anteil

GEWICHTE = {"vollstaendigkeit": 35, "historie": 20, "aktualitaet": 15, "konsistenz": 15, "schaetzanteil": 15}
PFLICHT_AKTIE = ("g_ums", "g_eps", "g_fcf", "roic", "om", "fm", "nde", "akt", "ev_ebit", "fcfy", "mos")
PLAUSIBEL = {"fcfy": (-40, 40), "roic": (-100, 100), "om": (-100, 100), "fm": (-100, 100), "g_ums": (-60, 200),
             "g_eps": (-100, 300), "nde": (-20, 20), "akt": (-30, 50)}
BEKANNTE_WAEHRUNGEN = {"EUR", "USD", "GBP", "GBp", "GBX", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK", "HKD",
                       "CNY", "KRW", "INR", "SGD", "TWD", "BRL", "MXN", "ZAR", "ZAc", "ILS", "ILA", "PLN", "NZD", "IDR",
                       "THB", "MYR", "TRY", "SAR", "AED", "KWD", "KWF", "QAR", "CZK", "HUF", "PHP", "CLP"}


def _datum(x):
    try:
        return datetime.date.fromisoformat(str(x)[:10])
    except (TypeError, ValueError):
        return None


def _aktualitaet(daten, heute):
    tage = [(heute - d).days for d in (_datum(x) for x in daten) if d]
    if not tage:
        return None
    t = max(tage)                                   # das aelteste der benutzten Datenstaende zaehlt
    return 100 if t <= 7 else 80 if t <= 30 else 50 if t <= 90 else 20


def _gesamt(teile):
    da = {k: v for k, v in teile.items() if v is not None}
    g = sum(GEWICHTE[k] for k in da)
    return round(sum(GEWICHTE[k] * v for k, v in da.items()) / g) if g else None


def aktie(q, inv=None, stand=None, heute=None, sektor_typ="standard"):
    """q: Zeile der Rangliste Qualitaets-Score (dict, Felder wie state/qualitaet/alle_N.json), inv: Kurzform der
    Investoren-Checks, stand: Datum der Qualitaets-Datei. -> {score, teile, warnungen}"""
    heute = heute or datetime.date.today()
    q, inv = q or {}, inv or {}
    warn = []
    if isinstance(q.get("fp"), dict):
        voll = 100 * (1 - datenluecke_anteil(q["fp"]))
    else:
        pflicht = [k for k in PFLICHT_AKTIE if D.anwendbar(k, sektor_typ)]
        voll = 100 * sum(1 for k in pflicht if q.get(k) is not None) / len(pflicht) if pflicht else None
    voll_b = branchen_vollstaendigkeit(inv.get("b"))
    if voll_b is not None:                          # Etappe 4a: branchentypische Pflichtkennzahlen mitzaehlen
        voll = voll_b if voll is None or not q.get("gesamt") else (voll + voll_b) / 2
    if voll is not None and voll < 70:
        warn.append(f"nur {voll:.0f} % der Score-Punkte mit Daten bewertbar")
    n = q.get("n")
    hist = min(float(n), 5) / 5 * 100 if isinstance(n, (int, float)) else None
    if isinstance(n, (int, float)) and n < 3:
        warn.append(f"nur {n} Geschäftsjahre")
    akt = _aktualitaet([stand] + ([inv.get("st")] if inv.get("st") else []), heute)
    if akt is not None and akt <= 50:
        warn.append("Bewertungsdaten älter als 30 Tage")
    pruef = []
    pruef.append(bool(q.get("kurs")) and q["kurs"] > 0)
    pruef.append(q.get("mcap") is None or q["mcap"] > 0)
    pruef.append(str(q.get("kwae") or "EUR") in BEKANNTE_WAEHRUNGEN)
    for k, (lo, hi) in PLAUSIBEL.items():
        if q.get(k) is not None:
            ok = lo <= q[k] <= hi
            pruef.append(ok)
            if not ok:
                warn.append(f"unplausibler Wert: {D.REGISTER[k].titel if k in D.REGISTER else k} {q[k]}")
    konsistenz = 100 * sum(pruef) / len(pruef)
    schaetz = 100 - (25 if q.get("fkgv") is not None and q.get("ev_ebit") is None else 0) \
        - (15 if q.get("rev90") is not None else 0)
    teile = {"vollstaendigkeit": None if voll is None else round(voll), "historie": None if hist is None else round(hist),
             "aktualitaet": akt, "konsistenz": round(konsistenz), "schaetzanteil": schaetz}
    return {"score": _gesamt(teile), "teile": teile, "warnungen": warn}


def branchen_vollstaendigkeit(b):
    """Anteil vorhandener Kennzahlen des Branchenmodells (nicht anwendbare zaehlen nicht) in % oder None."""
    if not b or b.get("t") not in BR.TYPEN:
        return None
    schl = [s_ for _, s__ in BR.MODULE[b["t"]].values() for s_ in s__ if s_ not in (b.get("na") or ())]
    return 100 * sum(1 for s_ in schl if s_ in (b.get("k") or {})) / len(schl) if schl else None


def etf(e, stand=None, heute=None):
    """e: ETF-Kennzahlen (klassen_score.je_kennung bzw. Katalogzeile: rendite, vola, dd, jahre, rendite_jahre)."""
    heute = heute or datetime.date.today()
    e = e or {}
    warn = []
    felder = ("rendite", "vola", "dd", "jahre")
    voll = 100 * sum(1 for k in felder if e.get(k) is not None) / len(felder)
    j = e.get("jahre")
    hist = min(float(j), 10) / 10 * 100 if isinstance(j, (int, float)) else None
    if isinstance(j, (int, float)) and j < 3:
        warn.append(f"nur {j:.1f} Jahre Kurshistorie".replace(".", ","))
    akt = _aktualitaet([stand], heute)
    pruef = [e.get("vola") is None or 0 < e["vola"] < 150, e.get("dd") is None or 0 <= abs(e["dd"]) <= 100,
             e.get("rendite") is None or -60 < e["rendite"] < 150]
    teile = {"vollstaendigkeit": round(voll), "historie": None if hist is None else round(hist), "aktualitaet": akt,
             "konsistenz": round(100 * sum(pruef) / len(pruef)), "schaetzanteil": 100}
    warn.append("TER, Tracking Difference und Fondsvolumen fehlen in den Daten")
    return {"score": _gesamt(teile), "teile": teile, "warnungen": warn}
