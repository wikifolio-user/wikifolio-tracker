"""Trading Intelligence - Long/Short Opportunity Score (0-100) und Alarm-Mindestanforderungen.

Der Score ist eine BEWERTUNG der Setup-Qualitaet, keine Erfolgswahrscheinlichkeit. Gewichte und Schwellen sind
vorab festgelegt (GEWICHTE, ALARM) und werden im Backtest (ti_backtest.py) auf einem zeitlich spaeteren Testzeitraum
geprueft - nicht auf den Testdaten optimiert. Erst wenn diese Pruefung besteht, gilt die Gewichtung als validiert.

Bausteine (Summe hoechstens 100):
  Setups     bis 35  je unabhaengiger Familie: bestaetigt 12, frueh 6
  Historie   bis 35  Vergleichsfaelle (Pattern Matching, 20 Tage): Trefferquote ueber der Basisquote derselben
                     Vergleichsgruppe (bis 20) und Medianrendite ueber dem Basis-Median (bis 15); erst ab
                     MIN_FAELLE effektiven Faellen, darunter 0 ("historisch nicht validiert")
  Kontext    bis 15  Marktumfeld (Leitindex ueber/unter SMA 200 passend zur Richtung), Trend bzw. Ueberdehnung
                     passend zum Setup-Typ, Volumenbestaetigung
  Risiko     bis 15  Chance-Risiko-Verhaeltnis (zu Kursziel 2), Liquiditaet, Datenqualitaet
Abzuege: widerspruechliche Lage (Long und Short gleichzeitig >= 60) -15 fuer beide; veraltete/fehlerhafte Daten ->
hoechstens 59 (kein Signal).
"""
import ti_historie as H
import ti_technik as T

GEWICHTE = {"setup_bestaetigt": 12, "setup_frueh": 6, "setup_max": 35, "hist_quote": 20, "hist_median": 15,
            "kontext_markt": 5, "kontext_typ": 5, "kontext_volumen": 5, "crv3": 10, "crv2": 5, "liquide": 3,
            "daten": 2, "widerspruch": 15, "hist_quote_voll_pp": 15}
ALARM = {"score": 85, "crv": 3.0, "bestaetigungen": 2, "liquide": True, "daten_ok": True, "hist_validiert": True}
KLASSEN = [(95, "Außergewöhnliches Setup"), (90, "Sehr interessantes Setup"), (85, "Starkes Setup"),
           (75, "Interessante Beobachtung"), (60, "Unbestätigtes Setup"), (0, "Kein relevantes Signal")]
TREND_TYPEN = {"L_ruecksetzer", "L_ausbruch", "L_struktur", "L_kaufdruck", "S_erholung", "S_bruch", "S_struktur"}
HORIZONT_SCORE = 20


def klasse(score):
    return next(t for g, t in KLASSEN if score >= g)


def hist_validiert(st):
    """Historische Validierung: genug effektive Faelle und untere Grenze des 95-%-Intervalls ueber der Basisquote."""
    return bool(st and st.get("quote") is not None and st["ki"][0] is not None and st["ki"][0] > st["basis_quote"])


def bewerten(richtung, setups_liste, hist, mk, ind, i, leit_ueber_sma200=None, daten_ok=True, liquide=True):
    """-> {"score", "klasse", "teile": {...}, "gruende": [...], "bestaetigungen", "hist_validiert"}"""
    g = GEWICHTE
    teile, gruende = {}, []
    # Setups
    fam = {}
    for x, stufe in setups_liste:
        fam[T.FAMILIE[x]] = max(fam.get(T.FAMILIE[x], 0), stufe)
    teile["setups"] = min(g["setup_max"], sum(g["setup_bestaetigt"] if v == 2 else g["setup_frueh"] for v in fam.values()))
    best, alle = T.bestaetigungen(setups_liste)
    # Historie
    st = (hist or {}).get(HORIZONT_SCORE)
    hp = 0.0
    if st and st.get("quote") is not None:
        edge_pp = (st["quote"] - st["basis_quote"]) * 100
        hp += g["hist_quote"] * min(1.0, max(0.0, edge_pp / g["hist_quote_voll_pp"]))
        streu = max(1e-6, (st["quantile"][75] - st["quantile"][25]))
        hp += g["hist_median"] * min(1.0, max(0.0, (st["median"] - st["basis_median"]) / (0.5 * streu)))
    else:
        gruende.append("historisch nicht validiert (zu wenige vergleichbare Fälle)")
    teile["historie"] = round(hp, 1)
    # Kontext
    k = 0
    if leit_ueber_sma200 is not None and (leit_ueber_sma200 == (richtung == "long")):
        k += g["kontext_markt"]
    typen = {x for x, _ in setups_liste}
    c, s200, r = ind["c"][i], ind["sma200"][i], ind["rsi"][i]
    if typen & TREND_TYPEN:
        if (richtung == "long" and c > s200) or (richtung == "short" and c < s200):
            k += g["kontext_typ"]
    elif (richtung == "long" and r < 35) or (richtung == "short" and r > 65):
        k += g["kontext_typ"]
    if ind["hat_volumen"] and ind["vol50"][i] > 0 and ind["v"][i] >= 1.5 * ind["vol50"][i]:
        k += g["kontext_volumen"]
    teile["kontext"] = k
    # Risiko
    rk = 0
    crv = mk["crv_haupt"] if mk else 0
    rk += g["crv3"] if crv >= 3 else g["crv2"] if crv >= 2 else 0
    rk += g["liquide"] if liquide else 0
    rk += g["daten"] if daten_ok else 0
    teile["risiko"] = rk
    score = teile["setups"] + teile["historie"] + teile["kontext"] + teile["risiko"]
    if not setups_liste:
        score = min(score, 0)
    if not daten_ok:
        score = min(score, 59)
        gruende.append("Daten veraltet oder fehlerhaft – kein Signal")
    score = int(round(max(0, min(100, score))))
    return {"score": score, "klasse": klasse(score), "teile": teile, "gruende": gruende, "bestaetigungen": best,
            "familien": alle, "hist_validiert": hist_validiert(st), "crv": crv}


def widerspruch(long_b, short_b):
    """Beide Richtungen >= 60: als widerspruechlich kennzeichnen und beide abwerten."""
    if long_b["score"] >= 60 and short_b["score"] >= 60:
        for b in (long_b, short_b):
            b["score"] = max(0, b["score"] - GEWICHTE["widerspruch"])
            b["klasse"] = klasse(b["score"])
            b["gruende"].append("widersprüchliche Marktlage (Long und Short gleichzeitig ausgeprägt)")
            b["widerspruch"] = True
    return long_b, short_b


def alarm_pruefen(b, liquide=True, daten_ok=True, a=None):
    """Mindestanforderungen (ohne Risk-Manager-Veto und Auditor - die folgen in Etappe 2) -> (ok, fehlend)."""
    a = a or ALARM
    fehlt = []
    if b["score"] < a["score"]:
        fehlt.append(f"Score {b['score']} < {a['score']}")
    if b["crv"] < a["crv"]:
        fehlt.append(f"CRV {b['crv']:.1f} < {a['crv']:.0f}")
    if b["bestaetigungen"] < a["bestaetigungen"]:
        fehlt.append(f"{b['bestaetigungen']} unabhängige Bestätigungen < {a['bestaetigungen']}")
    if a["liquide"] and not liquide:
        fehlt.append("zu geringe Liquidität")
    if a["daten_ok"] and not daten_ok:
        fehlt.append("Daten nicht aktuell/zuverlässig")
    if a["hist_validiert"] and not b["hist_validiert"]:
        fehlt.append("historisch nicht validiert")
    return not fehlt, fehlt


def kosten(klasse_wert):
    return H.KOSTEN.get(klasse_wert, 0.002)
