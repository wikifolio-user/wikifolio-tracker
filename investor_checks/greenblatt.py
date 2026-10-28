"""Joel Greenblatt - Magic Formula.

Quelle: J. Greenblatt, "The Little Book That Beats the Market" (2005):
  Return on Capital = EBIT / (Net Working Capital + Net Fixed Assets)
  Earnings Yield    = EBIT / Enterprise Value
Beide Werte werden innerhalb der Top-500-Liste gerangt, die Summe der Raenge ergibt den Gesamtrang.
Finanzwerte und Versorger schliesst Greenblatt aus (Bilanzstruktur nicht vergleichbar).

Rang ueber die Top-500-Liste: dort liegen nicht fuer alle Werte Bilanzpositionen vor - verglichen wird daher mit
den Agenten-Kennzahlen (Earnings Yield = 1 / (EV/EBIT), Return on Capital ~ ROIC). Die exakten Werte nach
Greenblatt werden fuer die gewaehlte Aktie zusaetzlich angezeigt.
"""
import bisect

import investor_config as C

from . import registriere
from .basis import ergebnis, extra, kriterium, letztes, sektor_typ, teile, zahl

INFO = ("Joel Greenblatt (*1957), Hedgefonds-Manager und Professor: Seine „Magic Formula“ kauft systematisch "
        "Firmen, die zugleich hohe Kapitalrenditen erzielen und günstig bewertet sind.")


def ey_roc(k):
    """(Earnings Yield %, Return on Capital %) aus Agenten-Kennzahlen eines Universum-Eintrags."""
    ev_ebit, roic = zahl(k.get("ev_ebit")), zahl(k.get("roic"))
    ey = 100.0 / ev_ebit if ev_ebit and ev_ebit > 0 else None
    return ey, roic


def raenge(universum):
    """Magic-Formula-Raenge ueber alle Aktien mit beiden Werten (Banken/Versorger ausgenommen).
    -> {"je_id": {id: (gesamtrang, perzentil)}, "ey": sortiert, "roc": sortiert, "n": anzahl}
    Rang 1 = bester; Perzentil = Anteil der Werte mit schlechterer Rangsumme."""
    werte = []
    for e in universum or []:
        if e.get("art") != "aktie":
            continue
        typ = sektor_typ({"sektor": "", "branche": e.get("sektor") or ""})
        if typ in ("bank", "versorger"):
            continue
        ey, roc = ey_roc(e.get("k") or {})
        if ey is not None and roc is not None:
            werte.append((e["id"], ey, roc))
    n = len(werte)
    if not n:
        return {"je_id": {}, "ey": [], "roc": [], "n": 0}
    r_ey = {i: r for r, (i, _, _) in enumerate(sorted(werte, key=lambda w: -w[1]), 1)}
    r_roc = {i: r for r, (i, _, _) in enumerate(sorted(werte, key=lambda w: -w[2]), 1)}
    summen = sorted((r_ey[i] + r_roc[i], i) for i, _, _ in werte)
    je_id = {}
    for platz, (s, i) in enumerate(summen, 1):
        je_id[i] = (platz, 100.0 * (n - platz) / n if n > 1 else 100.0)
    return {"je_id": je_id, "ey": sorted(w[1] for w in werte), "roc": sorted(w[2] for w in werte), "n": n}


def _perz(sortiert, wert):
    if wert is None or not sortiert:
        return None
    return 100.0 * bisect.bisect_left(sortiert, wert) / len(sortiert)


def greenblatt_exakt(f):
    """Exakte Werte nach Greenblatt aus der Bilanz. NWC ohne Cash (Ueberschussliquiditaet zaehlt nicht zum
    betrieblich gebundenen Kapital). EV = Boersenwert + Finanzschulden - Cash (in Berichtswaehrung)."""
    ebit = letztes(f, "ebit")
    umlauf, kv, cash = letztes(f, "umlauf"), letztes(f, "kurzfr_verb"), letztes(f, "cash") or 0
    ppe = letztes(f, "sachanlagen")
    roc = None
    if ebit is not None and umlauf is not None and kv is not None and ppe is not None:
        kapital = max(umlauf - cash - kv, 0) + ppe       # negatives Working Capital zaehlt als 0 (Greenblatt)
        roc = teile(ebit, kapital) * 100 if kapital > 0 else None
    faktor = teile(f.get("kurs_in_bericht"), f.get("kurs"))
    mcap = f["mcap"] * faktor if f.get("mcap") and faktor else None
    ev = mcap + (letztes(f, "schulden") or 0) - cash if mcap is not None else None
    ey = teile(ebit, ev) * 100 if ebit is not None and ev and ev > 0 else None
    return roc, ey


@registriere("greenblatt", "Joel Greenblatt", "Value", 30)
def check(f, kx):
    typ = sektor_typ(f)
    roc_x, ey_x = greenblatt_exakt(f)
    extras = [extra("Return on Capital (exakt)", roc_x, "EBIT / (Netto-Umlaufvermögen ohne Cash + Sachanlagen)",
                    fmt="pct"),
              extra("Earnings Yield (exakt)", ey_x, "EBIT / Unternehmenswert (EV)", fmt="pct")]
    if typ in ("bank", "versorger"):
        r = ergebnis("greenblatt", "Joel Greenblatt", "Magic Formula: hohe Kapitalrendite zum niedrigen Preis.",
                     "Value", [], f, extras=extras, fazit="Finanzwerte und Versorger schließt die Magic Formula aus.",
                     info=INFO)
        r["ausgeblendet"] = [{"name": "Magic Formula", "grund": "Greenblatt schließt Finanzwerte und Versorger aus – "
                              "ihre Bilanzen sind mit Industriefirmen nicht vergleichbar."}]
        return r
    rg = (kx or {}).get("greenblatt") or {}
    agent = (kx or {}).get("agent") or {}
    ey, roc = ey_roc(agent.get("k") or {})
    ey = ey if ey is not None else ey_x
    roc = roc if roc is not None else roc_x
    p_ey, p_roc = _perz(rg.get("ey"), ey), _perz(rg.get("roc"), roc)
    platz = (rg.get("je_id") or {}).get(agent.get("id"))
    kr = [kriterium("roc", "Return on Capital", roc, "Top-500-Median",
                    None if p_roc is None else p_roc >= 50,
                    f"Besser als {p_roc:.0f} % der Top-500-Aktien." if p_roc is not None else
                    "Nicht im Vergleich der Top-500-Liste.", fmt="pct"),
          kriterium("ey", "Earnings Yield", ey, "Top-500-Median", None if p_ey is None else p_ey >= 50,
                    f"Besser als {p_ey:.0f} % der Top-500-Aktien." if p_ey is not None else
                    "Nicht im Vergleich der Top-500-Liste.", fmt="pct"),
          kriterium("rang", "Magic-Formula-Gesamtrang", f"Platz {platz[0]} von {rg['n']}" if platz else None,
                    f"oberste {100 - C.GREENBLATT['gut_perzentil']:.0f} %",
                    None if not platz else platz[1] >= C.GREENBLATT["gut_perzentil"],
                    "Summe der Ränge aus Kapitalrendite und Earnings Yield (Vergleich mit Agenten-Kennzahlen: "
                    "EV/EBIT und ROIC).", fmt="text")]
    score = platz[1] if platz else None
    return ergebnis("greenblatt", "Joel Greenblatt", "Magic Formula: hohe Kapitalrendite zum niedrigen Preis.",
                    "Value", kr, f, extras=extras, score=score, info=INFO,
                    fazit=None if score is not None else "Nicht im Magic-Formula-Ranking (Daten fehlen).")
