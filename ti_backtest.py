"""Trading Intelligence - historischer Backtest und Out-of-Sample-Pruefung (ohne Streamlit).

Ablauf je Wert (nur abgeschlossene Tageskerzen, siehe ti_daten):
  1. Indikatoren und Setups (ti_technik) - je Tag nur Daten bis zu diesem Tag.
  2. Vergleichspool je Marktgruppe (ti_historie); eine Abfrage am Tag i sieht nur Faelle, deren Ergebnis vor i
     feststand (Walk-Forward, kein Look-Ahead).
  3. An jedem Tag mit mindestens einem Setup: Marken (Einstieg/Stop/Ziele), Score (ti_score). Danach Sperrfrist
     SPERRE Tage je Wert und Richtung (ueberlappende Faelle zaehlen sonst mehrfach).
  4. Handelssimulation: Einstieg nur, wenn der Trigger innerhalb von WARTE Tagen erreicht wird (bei Kursluecke zur
     Eroeffnung), danach Stop oder Kursziel 2, spaetestens nach MAX_TAGE Schluss. Liegen Stop und Ziel am selben
     Tag in der Spanne, zaehlt der Stop (vorsichtig). Kosten je Anlageklasse (ti_historie.KOSTEN).
Out-of-Sample: Faelle vor TEILUNG = Lernzeitraum, ab TEILUNG = Testzeitraum. Gewichte und Schwellen wurden NICHT
anhand dieser Ergebnisse gewaehlt; der Bericht zeigt, ob sie im Testzeitraum tragen ("validiert") oder nicht.
"""
import datetime
import statistics

import numpy as np

import ti_historie as H
import ti_score as S
import ti_technik as T

TEILUNG = "2019-01-01"
SPERRE = 10
WARTE = 3
MAX_TAGE = 60
BUCKETS = [(85, 101, "85–100"), (75, 85, "75–84"), (60, 75, "60–74"), (0, 60, "unter 60")]
MIN_TEST_FAELLE = 30


def leit_symbol(u, meta):
    if u["klasse"] in ("aktie", "etf", "index"):
        return "^GDAXI" if (meta or {}).get("waehrung") == "EUR" and u["symbol"] != "^GSPC" else "^GSPC"
    return None


def vorbereiten(werte):
    """werte: [{"u": Universum-Eintrag, "e": Kerzen-Eintrag, "p": Pruefung}] -> (vorbereitet, pools)."""
    kerzen_je = {w["u"]["symbol"]: w["e"].get("kerzen") or [] for w in werte}
    aus, pools = [], {}
    for w in werte:
        k = w["e"].get("kerzen") or []
        if len(k) < 260:
            continue
        u = w["u"]
        ind = T.indikatoren(k)
        ls = leit_symbol(u, w["e"].get("meta"))
        leit = H.leit_ausrichten(ind["datum"], kerzen_je.get(ls)) if ls and ls != u["symbol"] else None
        leit_sma = T.sma(leit, 200) if leit is not None else None
        if ls == u["symbol"]:
            leit, leit_sma = None, ind["sma200"]
            leit_c = ind["c"]
        else:
            leit_c = leit
        f = H.merkmale(ind, leit)
        erg = H.ergebnisse(ind)
        gruppe = H.GRUPPE[u["klasse"]]
        pools.setdefault(gruppe, H.Pool()).hinzufuegen(u["symbol"], ind, f, erg)
        aus.append({"u": u, "p": w.get("p") or {}, "ind": ind, "s": T.setups(ind), "f": f, "erg": erg,
                    "gruppe": gruppe, "leit_c": leit_c, "leit_sma": leit_sma, "e": w["e"]})
    return aus, pools


def simulieren(ind, i, mk, kosten):
    """-> {"r","ret","tage","t1","ausgang"} oder None (Trigger nicht erreicht / zu wenig Daten)."""
    o, h, lo, c = ind["o"], ind["h"], ind["l"], ind["c"]
    n = ind["n"]
    lang = mk["richtung"] == "long"
    trig, stop, ziel = mk["trigger"], mk["stop"], mk["ziele"][min(1, len(mk["ziele"]) - 1)]
    t1 = mk["ziele"][0]
    e_tag = None
    for j in range(i + 1, min(n, i + 1 + WARTE)):
        if (lang and h[j] >= trig) or (not lang and lo[j] <= trig):
            e_tag, einstieg = j, (max(o[j], trig) if lang else min(o[j], trig))
            break
    if e_tag is None:
        return None
    risiko = (einstieg - stop) if lang else (stop - einstieg)
    if risiko <= 0:
        return None
    t1_erreicht = False
    for j in range(e_tag, min(n, e_tag + MAX_TAGE)):
        if lang:
            if lo[j] <= stop:
                aus, ausgang = min(stop, o[j]) if j > e_tag else stop, "Stop"
                break
            t1_erreicht |= h[j] >= t1
            if h[j] >= ziel:
                aus, ausgang = max(ziel, o[j]) if j > e_tag else ziel, "Ziel 2"
                break
        else:
            if h[j] >= stop:
                aus, ausgang = max(stop, o[j]) if j > e_tag else stop, "Stop"
                break
            t1_erreicht |= lo[j] <= t1
            if lo[j] <= ziel:
                aus, ausgang = min(ziel, o[j]) if j > e_tag else ziel, "Ziel 2"
                break
    else:
        if e_tag + MAX_TAGE > n:
            return None                                   # Haltedauer noch nicht vollstaendig
        j = e_tag + MAX_TAGE - 1
        aus, ausgang = c[j], "Zeit"
    ret = (aus / einstieg - 1) if lang else (einstieg / aus - 1)
    ret -= kosten
    return {"r": ret * einstieg / risiko, "ret": ret, "tage": j - e_tag + 1, "t1": t1_erreicht, "ausgang": ausgang}


def faelle(vorbereitet, pools, fortschritt=None):
    """Alle Signalfaelle -> Liste von dicts."""
    aus = []
    for nr, w in enumerate(vorbereitet):
        if fortschritt:
            fortschritt(nr, len(vorbereitet), w["u"]["symbol"])
        ind, s = w["ind"], w["s"]
        kosten = S.kosten(w["u"]["klasse"])
        liquide = True
        frei = {"long": 0, "short": 0}
        for i in range(200, ind["n"]):
            lst = {r: T.aktiv(s, i, r) for r in ("long", "short")}
            if not lst["long"] and not lst["short"]:
                continue
            if all(i < frei[r] or not lst[r] for r in lst):
                continue
            hist_roh = pools[w["gruppe"]].abfragen(w["f"][i], ind["datum"][i], horizonte=(20, 60))
            leit_ueber = None
            if w["leit_c"] is not None and w["leit_sma"] is not None and not np.isnan(w["leit_sma"][i]):
                leit_ueber = bool(w["leit_c"][i] > w["leit_sma"][i])
            bew = {}
            for r in ("long", "short"):
                hist = H.statistik(hist_roh, r, kosten)
                mk = T.marken(ind, i, r, _hist_ziele(hist, r))
                bew[r] = (S.bewerten(r, lst[r], hist, mk, ind, i, leit_ueber, True, liquide) if lst[r] else
                          {"score": 0}, mk, hist)
            S.widerspruch(bew["long"][0], bew["short"][0]) if lst["long"] and lst["short"] else None
            for r in ("long", "short"):
                if not lst[r] or i < frei[r]:
                    continue
                b, mk, hist = bew[r]
                if mk is None:
                    continue
                frei[r] = i + SPERRE
                sim = simulieren(ind, i, mk, kosten)
                h20 = hist.get(20) or {}
                ok, fehlt = S.alarm_pruefen(b, liquide, True)
                fw = {}
                for hz in (20, 60):
                    ret = w["erg"][hz][0][i]
                    fw[hz] = None if np.isnan(ret) else float((ret if r == "long" else -ret) - kosten)
                aus.append({"symbol": w["u"]["symbol"], "klasse": w["u"]["klasse"], "datum": ind["datum"][i],
                            "richtung": r, "setups": lst[r], "score": b["score"], "teile": b["teile"],
                            "bestaetigungen": b["bestaetigungen"], "hist_validiert": b["hist_validiert"],
                            "hist20": {k: h20.get(k) for k in ("quote", "basis_quote", "n_eff", "median")},
                            "crv": float(mk["crv_haupt"]), "alarm": ok, "fehlt": fehlt, "sim": sim, "fw": fw,
                            "widerspruch": bool(b.get("widerspruch"))})
    return aus


def _hist_ziele(hist, richtung):
    st = (hist or {}).get(60)
    if not st:
        return []
    return [st["guenstig"][p] for p in (50, 75, 90) if st["guenstig"][p] > 0]


def _kennzahlen(fl):
    sims = [f["sim"] for f in fl if f["sim"]]
    fw = [f["fw"][20] for f in fl if f["fw"].get(20) is not None]
    r = [s["r"] for s in sims]
    return {"faelle": len(fl), "trades": len(sims),
            "trefferquote": (sum(1 for x in r if x > 0) / len(r)) if r else None,
            "mittel_r": (sum(r) / len(r)) if r else None, "median_r": statistics.median(r) if r else None,
            "ziel2": (sum(1 for s in sims if s["ausgang"] == "Ziel 2") / len(sims)) if sims else None,
            "stop": (sum(1 for s in sims if s["ausgang"] == "Stop") / len(sims)) if sims else None,
            "fw20_median": statistics.median(fw) if fw else None,
            "fw20_quote": (sum(1 for x in fw if x > 0) / len(fw)) if fw else None}


def basis(vorbereitet, teilung=TEILUNG):
    """Vergleich ohne Signal: Einstieg an JEDEM Tag (ab Tag 200), 20-Tage-Rendite nach Kosten -> je Richtung und
    Zeitraum {"median", "quote", "n"}."""
    aus = {}
    for r in ("long", "short"):
        for t in ("lern", "test"):
            werte = []
            for w in vorbereitet:
                ret = w["erg"][20][0]
                k = S.kosten(w["u"]["klasse"])
                for i in range(200, w["ind"]["n"]):
                    d = w["ind"]["datum"][i]
                    if np.isnan(ret[i]) or ((d < teilung) != (t == "lern")):
                        continue
                    werte.append((ret[i] if r == "long" else -ret[i]) - k)
            aus[(r, t)] = {"n": len(werte), "median": statistics.median(werte) if werte else None,
                           "quote": (sum(1 for x in werte if x > 0) / len(werte)) if werte else None}
    return aus


def bericht(fl, teilung=TEILUNG, basis_werte=None):
    teile = {"lern": [f for f in fl if f["datum"] < teilung], "test": [f for f in fl if f["datum"] >= teilung]}
    aus = {"teilung": teilung, "erstellt": datetime.date.today().isoformat(), "gesamt": {}, "setups": {},
           "buckets": {}, "alarm": {}, "richtung": {}, "basis": basis_werte or {}, "verteilung": {}}
    for r in ("long", "short"):
        sc = sorted(f["score"] for f in fl if f["richtung"] == r)
        aus["verteilung"][r] = {p: sc[min(len(sc) - 1, int(len(sc) * p / 100))] for p in (50, 90, 99)} if sc else {}
        aus["verteilung"][r]["max"] = sc[-1] if sc else None
    for t, x in teile.items():
        aus["gesamt"][t] = _kennzahlen(x)
        for r in ("long", "short"):
            aus["richtung"][(r, t)] = _kennzahlen([f for f in x if f["richtung"] == r])
            for lo_, hi_, name in BUCKETS:
                aus["buckets"][(r, t, name)] = _kennzahlen([f for f in x if f["richtung"] == r and lo_ <= f["score"] < hi_])
        for sid in T.LONG + T.SHORT:
            aus["setups"][(sid, t)] = _kennzahlen([f for f in x if any(a == sid and st == 2 for a, st in f["setups"])])
        al = [f for f in x if f["alarm"]]
        jahre = _jahre(x)
        aus["alarm"][t] = dict(_kennzahlen(al), je_jahr=(len(al) / jahre) if jahre else None,
                               liste=[{k: f[k] for k in ("symbol", "datum", "richtung", "score", "crv")} for f in al][-30:])
    aus["validiert"], aus["validierung_text"] = validierung(aus)
    return aus


def _jahre(fl):
    if not fl:
        return 0
    d = sorted(f["datum"] for f in fl)
    return max(0.25, (datetime.date.fromisoformat(d[-1]) - datetime.date.fromisoformat(d[0])).days / 365.25)


def validierung(b):
    """Gilt die Gewichtung im Testzeitraum? Fuer jede Richtung: Bucket >= 75 hat genug Faelle, positives mittleres R
    und ein hoeheres mittleres R als der Bucket 60-74. -> (bool je Richtung, Text)."""
    aus, text = {}, []
    for r in ("long", "short"):
        hoch = _zusammen(b, r, ("85–100", "75–84"))
        mittel = b["buckets"][(r, "test", "60–74")]
        if hoch["trades"] < MIN_TEST_FAELLE:
            aus[r] = False
            text.append(f"{r}: zu wenige Testfälle mit Score ≥ 75 ({hoch['trades']} < {MIN_TEST_FAELLE})")
        elif (hoch["mittel_r"] or 0) <= 0:
            aus[r] = False
            text.append(f"{r}: Score ≥ 75 im Testzeitraum ohne positives Ergebnis (Ø {hoch['mittel_r']:+.2f} R)")
        elif mittel["trades"] and (hoch["mittel_r"] or 0) <= (mittel["mittel_r"] or 0):
            aus[r] = False
            text.append(f"{r}: höherer Score bringt im Testzeitraum kein besseres Ergebnis "
                        f"(Ø {hoch['mittel_r']:+.2f} R vs. {mittel['mittel_r']:+.2f} R)")
        else:
            aus[r] = True
            text.append(f"{r}: Score ≥ 75 im Testzeitraum Ø {hoch['mittel_r']:+.2f} R bei {hoch['trades']} Trades – "
                        f"besser als 60–74")
    return aus, text


def _zusammen(b, r, namen):
    fl_r = [(b["buckets"][(r, "test", n)]) for n in namen]
    trades = sum(x["trades"] for x in fl_r)
    mr = (sum((x["mittel_r"] or 0) * x["trades"] for x in fl_r) / trades) if trades else None
    return {"trades": trades, "mittel_r": mr}


def _p(x, n=0):
    return "–" if x is None else f"{x * 100:.{n}f} %"


def _r(x):
    return "–" if x is None else f"{x:+.2f} R"


def markdown(b, universum_info=None):
    z = [f"# Trading Intelligence – Backtest (Etappe 1)\n", f"Erstellt am {b['erstellt']}. Lernzeitraum bis "
         f"{b['teilung']}, Testzeitraum ab {b['teilung']} (Out-of-Sample). Gewichte und Schwellen wurden vorab "
         f"festgelegt und nicht an diese Ergebnisse angepasst.\n"]
    if universum_info:
        z.append(universum_info + "\n")
    z.append("## Ergebnis der Validierung\n")
    for t in b["validierung_text"]:
        z.append(f"- {t}")
    z.append("\nSolange eine Richtung nicht validiert ist, werden für sie in Etappe 3 keine Einstiegsalarme "
             "versendet.\n")
    z.append("## Alarm-Mindestanforderungen (Score ≥ 85, CRV ≥ 3, ≥ 2 unabhängige Bestätigungen, historisch "
             "validiert, liquide, Daten aktuell)\n")
    z.append("| Zeitraum | Fälle | pro Jahr | Trades | Trefferquote | Ø R | Median R |\n|---|---|---|---|---|---|---|")
    for t in ("lern", "test"):
        a = b["alarm"][t]
        z.append(f"| {t} | {a['faelle']} | {a['je_jahr'] or 0:.1f} | {a['trades']} | {_p(a['trefferquote'])} | "
                 f"{_r(a['mittel_r'])} | {_r(a['median_r'])} |")
    z.append("\n## Score-Klassen (Trades mit Stop/Ziel 2/60 Tage)\n")
    z.append("| Richtung | Score | Lern: Trades | Lern: Ø R | Test: Trades | Test: Trefferquote | Test: Ø R | "
             "Test: Median 20-T.-Rendite |\n|---|---|---|---|---|---|---|---|")
    for r in ("long", "short"):
        for _, _, name in BUCKETS:
            le, te = b["buckets"][(r, "lern", name)], b["buckets"][(r, "test", name)]
            z.append(f"| {r} | {name} | {le['trades']} | {_r(le['mittel_r'])} | {te['trades']} | "
                     f"{_p(te['trefferquote'])} | {_r(te['mittel_r'])} | {_p(te['fw20_median'], 1)} |")
    z.append("\n## Setups (nur bestätigte Stufe)\n")
    z.append("| Setup | Lern: Trades | Lern: Ø R | Test: Trades | Test: Trefferquote | Test: Ø R |\n|---|---|---|---|---|---|")
    for sid in T.LONG + T.SHORT:
        le, te = b["setups"][(sid, "lern")], b["setups"][(sid, "test")]
        z.append(f"| {sid} | {le['trades']} | {_r(le['mittel_r'])} | {te['trades']} | {_p(te['trefferquote'])} | "
                 f"{_r(te['mittel_r'])} |")
    z.append("\n## Vergleich: alle Signale je Richtung\n")
    z.append("| Richtung | Zeitraum | Trades | Trefferquote | Ø R | Median 20-T.-Rendite | Anteil 20-T. positiv |"
             "\n|---|---|---|---|---|---|---|")
    for r in ("long", "short"):
        for t in ("lern", "test"):
            x = b["richtung"][(r, t)]
            z.append(f"| {r} | {t} | {x['trades']} | {_p(x['trefferquote'])} | {_r(x['mittel_r'])} | "
                     f"{_p(x['fw20_median'], 1)} | {_p(x['fw20_quote'])} |")
    if b.get("basis"):
        for r in ("long", "short"):
            for t in ("lern", "test"):
                x = b["basis"][(r, t)]
                z.append(f"| {r} | {t}: jeder Tag (ohne Signal) | – | – | – | {_p(x['median'], 1)} | {_p(x['quote'])} |")
    z.append("\n## Verteilung des Opportunity Scores (alle Signalfälle)\n")
    for r in ("long", "short"):
        v = b["verteilung"].get(r) or {}
        z.append(f"- {r}: Median {v.get(50)}, 90. Perzentil {v.get(90)}, 99. Perzentil {v.get(99)}, Maximum {v.get('max')}")
    z.append("\nR = Ergebnis in Vielfachen des anfänglichen Risikos (Einstieg bis Stop), nach Kosten. "
             "Trefferquote = Anteil der Trades mit positivem Ergebnis. Der Opportunity Score ist keine "
             "Erfolgswahrscheinlichkeit. Short-Ergebnisse ohne Leihgebühren und Finanzierungskosten (dafür liegen keine "
             "Daten vor). Keine Anlageberatung.")
    return "\n".join(z) + "\n"


def main(argv=None):
    """Backtest von der Kommandozeile: python ti_backtest.py --state <Ordner des State-Repos> --aus <bericht.md>
    Liest die ISINs aus den Dashboard-Dateien, laedt die Kerzen (Yahoo) und schreibt den Bericht."""
    import argparse
    import glob
    import json
    import os

    import requests

    import kurs_agent as K
    import ti_daten as TD
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--aus", required=True)
    a = ap.parse_args(argv)
    isins = {}
    pfade = [os.path.join(a.state, "state", d) for d in K.DATEIEN]
    pfade += [p for p in glob.glob(os.path.join(a.state, "state", "benutzer", "*", "**", "*.json"), recursive=True)
              if any(p.endswith("/" + d) for d in K.DATEIEN)]
    pfade.append(os.path.join(a.state, "state", "kurse", "suche.json"))
    for p in pfade:
        try:
            with open(p, encoding="utf-8") as f:
                TD.isins_in(json.load(f), isins)
        except (OSError, ValueError):
            continue
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    uni, _ = TD.universum(isins, requests.get)
    werte = []
    for u in uni:
        if u["symbol"]:
            e = TD.kerzen_abrufen(u["symbol"], requests.get, jetzt)
            werte.append({"u": u, "e": e, "p": TD.pruefen(e, u["klasse"], jetzt)})
    vb, pools = vorbereiten(werte)
    fl = faelle(vb, pools)
    b = bericht(fl, basis_werte=basis(vb))
    info = universum_text(uni, werte, vb)
    with open(a.aus, "w", encoding="utf-8") as f:
        f.write(markdown(b, info))
    return b


def universum_text(uni, werte, vb):
    """Kurzbeschreibung des untersuchten Universums fuer den Bericht."""
    from collections import Counter
    genutzt = {w["u"]["symbol"] for w in vb}
    kl = Counter(w["u"]["klasse"] for w in vb)
    ohne = [u for u in uni if u["grund"]]
    kurz = [w["u"]["symbol"] for w in werte if w["u"]["symbol"] not in genutzt]
    erste = min((w["ind"]["datum"][0] for w in vb), default="–")
    return (f"Untersucht: {len(vb)} Werte ({', '.join(f'{v} {k}' for k, v in sorted(kl.items()))}), Tageskerzen "
            f"von Yahoo Finance ab {erste}. Nicht analysierbar: {len(ohne)} Dashboard-Werte (Wikifolios/Derivate "
            f"ohne Börsenhistorie oder ohne Yahoo-Symbol); zu kurze oder fehlende Historie: {len(kurz)} Werte.")


if __name__ == "__main__":
    main()
