"""Fairer Wert - alle Bewertungsmodelle nebeneinander (Abschnitt 8) und Reverse-DCF.

Alle Werte je Aktie in der Berichtswaehrung (wie EPS und Buchwert); der aktuelle Kurs wird dafuer umgerechnet.
Modelle: Graham-Zahl und Graham-Formel (graham.py), Lynch Fair Value (lynch.py), DCF auf Owner Earnings
(buffett.py), KGV-Mean-Reversion (Kurs beim eigenen Durchschnitts-KGV, templeton.py), Analysten-Kursziel.
Reverse-DCF: welches Wachstum der Owner Earnings preist der aktuelle Boersenwert ein?
"""
import statistics

import investor_config as C

from . import buffett, graham, lynch, templeton
from .basis import cagr, de, letztes, mittel, reihe, teile, vorhanden, zahl


def reverse_dcf(oe0, wert, diskont=None, ewig=None, jahre=None):
    """Wachstum p. a. (in %), bei dem der DCF der Owner Earnings genau `wert` (Boersenwert) ergibt.
    Bisektion zwischen -30 % und +60 %. None, wenn nicht loesbar (z. B. Owner Earnings <= 0)."""
    cfg = C.REVERSE_DCF
    diskont = cfg["diskont"] if diskont is None else diskont
    ewig = cfg["ewig"] if ewig is None else ewig
    jahre = cfg["jahre"] if jahre is None else jahre
    oe0, wert = zahl(oe0), zahl(wert)
    if not oe0 or oe0 <= 0 or not wert or wert <= 0:
        return None
    lo, hi = -30.0, 60.0
    f_lo, f_hi = buffett.dcf(oe0, lo, diskont, ewig, jahre), buffett.dcf(oe0, hi, diskont, ewig, jahre)
    if f_lo is None or f_hi is None or not (f_lo <= wert <= f_hi):
        return None
    for _ in range(80):
        mitte = (lo + hi) / 2
        if buffett.dcf(oe0, mitte, diskont, ewig, jahre) < wert:
            lo = mitte
        else:
            hi = mitte
    return (lo + hi) / 2


def uebersicht(f, kx=None, dcf=None):
    """-> {"modelle": [{methode, wert, text}], "median", "kurs", "reverse": {impliziert, historisch, text}}
    dcf: (wachstum, diskont, ewig) fuer den Owner-Earnings-DCF (Standard aus der Konfiguration)."""
    cfg = C.BUFFETT
    kurs = f.get("kurs_in_bericht")
    eps = letztes(f, "eps")
    aktien = letztes(f, "aktien") or f.get("aktien")
    bvps = teile(letztes(f, "ek"), aktien)
    m = []

    def neu(methode, wert, text):
        m.append({"methode": methode, "wert": wert if wert and wert > 0 else None, "text": text})

    neu("Graham-Zahl", graham.graham_zahl(eps, bvps), "√(22,5 × EPS × Buchwert je Aktie)")
    eps_r = vorhanden(reihe(f, "eps"))
    g_hist = cagr(eps_r[-1], eps_r[0], len(eps_r) - 1) if len(eps_r) >= 2 else None
    g_f = max(0.0, min(C.GRAHAM["formel_g_max"], g_hist)) if g_hist is not None else None
    neu("Graham-Formel", graham.graham_formel(eps, g_f), f"EPS × (8,5 + 2g) × 4,4 / Y, g = {de(g_f)} %")
    g_l = lynch.wachstumsrate(f, kx)
    neu("Lynch Fair Value", lynch.fair_value(eps, g_l), f"EPS × Wachstum ({de(g_l)} %)")
    oe = buffett.owner_earnings((f.get("jahre") or [{}])[-1]) if f.get("jahre") else None
    g, r, ge = dcf or (cfg["dcf_wachstum"], cfg["dcf_diskont"], cfg["dcf_ewig"])
    w = buffett.dcf(oe, g, r, ge, cfg["dcf_jahre"])
    neu("DCF (Owner Earnings)", teile(w, aktien), f"Wachstum {de(g)} %, Diskont {de(r)} %, ewig {de(ge)} %")
    kgvs = templeton.historisches_kgv(f)
    kgv_hist = mittel(kgvs)
    neu("KGV-Mean-Reversion", eps * kgv_hist if eps and kgv_hist else None,
        f"EPS × eigenes Ø-KGV ({de(kgv_hist)}, {len(kgvs)} Jahre)")
    ziel = zahl((f.get("analysten") or {}).get("targetMeanPrice"))
    faktor = teile(f.get("kurs_in_bericht"), f.get("kurs"))
    n = int((f.get("analysten") or {}).get("numberOfAnalystOpinions") or 0)
    neu("Analysten-Kursziel", ziel * faktor if ziel and faktor else None, f"Durchschnitt von {n} Analysten")
    werte = [x["wert"] for x in m if x["wert"]]
    # Reverse-DCF: Boersenwert in Berichtswaehrung vs. Owner Earnings
    mcap = f["mcap"] * faktor if f.get("mcap") and faktor else None
    imp = reverse_dcf(oe, mcap)
    hist = g_hist
    if imp is None:
        text = "Nicht berechenbar (Owner Earnings fehlen oder sind negativ)."
    else:
        text = (f"Der Markt erwartet {de(imp)} % Wachstum p. a. der Owner Earnings über 10 Jahre"
                + (f", historisch wuchs der Gewinn je Aktie {de(hist)} % p. a." if hist is not None else ".")
                + (" Die Erwartung liegt deutlich über der Historie." if hist is not None and imp > hist + 3 else
                   " Die Erwartung liegt unter der Historie." if hist is not None and imp < hist - 3 else ""))
    return {"modelle": m, "median": statistics.median(werte) if werte else None, "kurs": kurs,
            "waehrung": f.get("waehrung") or "", "reverse": {"impliziert": imp, "historisch": hist, "text": text}}
