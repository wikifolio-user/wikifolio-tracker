"""Pyramidenmanager Etappe 3 - Backtest der Strategien A-D auf den Tageskerzen der vier Indizes.

  A  reine technische Trendstrategie (Einstieg/Nachkauf/Ausstieg nach den Regeln des Rechenkerns)
  B  A + Gap-Filter            (Gap-Wert aus dem Gap Analyzer >= FILTER_AB)
  C  A + Fear-&-Greed-Filter   (Einstiegswert aus dem eigenen Fear-&-Greed-Rohwert >= FILTER_AB)
  D  kombiniert                (kombinierter Wert aus Trend/Gap/F&G >= Einstiegsschwelle)

Keine Vorausschau: Jede Entscheidung faellt am Schluss eines Tages nur mit Kerzen bis zu diesem Tag und wird zur
Eroeffnung des naechsten Tages ausgefuehrt. Trend-Score, ATR, Stops und Gap-Analyse werden je Tag aus der
Vergangenheit gerechnet. Fear & Greed: der eigene ROH-Score (ohne die CNN-Eichung, die Daten bis heute enthaelt),
als Perzentil gegen die eigenen Rohwerte der vorangegangenen drei Jahre.

Vereinfachungen (stehen auch in der Ansicht): Long-KO mit KO = Basispreis, Finanzierung als Zins auf den
Basispreis, kein Restwert nach Knock-out, keine Waehrungseffekte, Spread je Kauf und Verkauf zur Haelfte.
Reine Rechenlogik ohne Streamlit und ohne Netz."""
import datetime
import math
import statistics

import fear_greed as FG
import gap_analyzer as G
import pyramide as P

STRATEGIEN = {"A": "Trend", "B": "Trend + Gap-Filter", "C": "Trend + Fear-&-Greed-Filter", "D": "Kombiniert"}
FILTER_AB = 40                    # Gap- bzw. F&G-Einstiegswert ab hier ("neutral" oder besser)
FG_FENSTER = 756                  # eigene Vergangenheit fuer das Perzentil (3 Jahre)
FG_MIN = 120
GAP_FENSTER = 500                 # Gap-Analyse ueber die letzten 500 Handelstage (ca. 2 Jahre)
TREND_FENSTER = 300
VORLAUF_TAGE = 20                 # Signalqualitaet: Indexrendite 20 Handelstage nach jedem Neueinstieg
STANDARD_PARAMETER = {"kapital": 10000.0, "art": "direkt", "hebel": None, "spread_pct": 0.1, "gebuehr": 1.0,
                      "finanzierung_pa": 3.0}


# ---------------------------------------------------------------------------------------------------- Zeitreihen
def fg_perzentile(kerzen, impl_kerzen=None):
    """{datum: Perzentil 0-100} des eigenen Roh-Scores gegen die Rohwerte der vorangegangenen FG_FENSTER Tage."""
    roh = FG.score_verlauf(kerzen, impl_kerzen=impl_kerzen)
    aus = {}
    for j, (d, w) in enumerate(roh):
        vor = [x for _, x in roh[max(0, j - FG_FENSTER):j]]
        if len(vor) >= FG_MIN:
            aus[d] = round(sum(1 for x in vor if x < w) / len(vor) * 100, 1)
    return aus


def reihen(kerzen, cfg, impl_kerzen=None, mit_fg=True):
    """Je Tag: Trend-Score und ATR aus der Vergangenheit, F&G-Perzentil. Alles nur bis zum jeweiligen Tag."""
    trend, atr_ = [], []
    for i in range(len(kerzen)):
        trend.append(P.trend_score(kerzen[max(0, i + 1 - TREND_FENSTER):i + 1]) if i + 1 >= P.MIN_KERZEN else None)
        atr_.append(P.atr(kerzen[max(0, i - cfg["atr_tage"] - 1):i + 1], cfg["atr_tage"]))
    return {"trend": trend, "atr": atr_, "fg": fg_perzentile(kerzen, impl_kerzen) if mit_fg else {}}


class Bewerter:
    """Gap- und F&G-Wert eines Tages - nur bei Bedarf gerechnet und fuer alle Strategien zwischengespeichert."""

    def __init__(self, kerzen, code, cfg, r, definition="hl"):
        self.k, self.code, self.cfg, self.r, self.definition = kerzen, code, cfg, r, definition
        self._gap = {}

    def gap(self, i):
        if i not in self._gap:
            fenster = self.k[max(0, i + 1 - GAP_FENSTER):i + 1]
            kurs = fenster[-1][4]
            gaps = G.mit_lage(G.erkennen(fenster, self.code, self.definition), kurs)
            daten = {"gaps": gaps, "statistik": G.statistik(gaps), "status": "aktuell", "stand": fenster[-1][0],
                     "definition": G.DEFINITIONEN[self.definition]}
            self._gap[i] = P.gap_wert(daten, kurs, self.r["atr"][i], self.cfg)
        return self._gap[i]

    def fg(self, i):
        w = self.r["fg"].get(self.k[i][0])
        eintrag = None if w is None else {"wert": w, "kategorie": None, "status": "aktuell", "bezug": "index",
                                          "quelle": "eigener Rohwert (Perzentil der letzten 3 Jahre)"}
        return P.fg_einstiegswert(eintrag, self.cfg)


# ---------------------------------------------------------------------------------------------------- Positionen
def _wert(t, kurs, datum, p):
    if t["ko"] is None:
        return t["anteile"] * kurs
    basis = _basis(t, datum, p)
    return max(0.0, t["anteile"] * (kurs - basis))


def _basis(t, datum, p):
    tage = (datetime.date.fromisoformat(datum) - datetime.date.fromisoformat(t["datum"])).days
    return t["basis"] * (1 + p["finanzierung_pa"] / 100 * tage / 365)


def _wert_am_stop(t, stop, datum, p):
    return _wert(t, stop, datum, p) if stop is not None else 0.0


def _tranche_stop(t, gemeinsam):
    return max(x for x in (t["anfangsstop"], gemeinsam) if x is not None)


def _filter(s, i, trend, bew, cfg):
    """-> (ok, Grund bei Ablehnung)."""
    if s == "A":
        return True, None
    if s == "B":
        g = bew.gap(i)
        return (g["wert"] is not None and g["wert"] >= FILTER_AB), "Gap-Wert"
    if s == "C":
        if cfg["fg_modus"] == "aus":
            return True, None
        f = bew.fg(i)
        return (f["wert"] is not None and f["wert"] >= FILTER_AB), "Fear & Greed"
    k = P.kombiniert(trend, bew.gap(i), bew.fg(i), cfg)
    return (k["wert"] is not None and k["wert"] >= cfg["einstieg_ab"]), "kombinierter Wert"


# ---------------------------------------------------------------------------------------------------- Simulation
def simulieren(kerzen, s, r, bew, cfg, p, von_i, bis_i):
    """Eine Strategie Tag fuer Tag. -> Ergebnis-dict."""
    kap = float(p["kapital"])
    halb = p["spread_pct"] / 200
    cash, tranchen, kurve, pyramiden, ereignisse = kap, [], [], [], []
    hoechst = stop = None
    offen = None                       # laufende Pyramide
    auftrag = None                     # ("kauf", stufe) / ("verkauf", [indizes], grund)
    kosten = 0.0
    blockiert, signale, im_markt = 0, 0, 0
    vorlauf = []

    def schliessen(t, preis, datum, grund):
        nonlocal cash, kosten
        w = _wert(t, preis, datum, p)
        erloes = w * (1 - halb) - p["gebuehr"]
        kosten += w * halb + p["gebuehr"]
        cash += erloes
        offen["ergebnis"] += erloes - t["einsatz"] - t["kauf_gebuehr"]
        offen["kosten"] += w * halb + p["gebuehr"]

    for i in range(von_i, bis_i + 1):
        d, o, h, l, c = kerzen[i]
        # 1. Auftrag des Vortags zur Eroeffnung ausfuehren
        if auftrag and auftrag[0] == "verkauf":
            for t in [tranchen[j] for j in auftrag[1]]:
                schliessen(t, o, d, auftrag[2])
            tranchen = [t for j, t in enumerate(tranchen) if j not in auftrag[1]]
            if not tranchen and offen:
                offen.update(ende=d, grund=auftrag[2])
                pyramiden.append(offen)
                offen, hoechst, stop = None, None, None
        elif auftrag and auftrag[0] == "kauf":
            a = r["atr"][i - 1]
            stufe = len(tranchen) + 1
            anf = P.anfangsstop(o, a, cfg)
            equity = cash + sum(_wert(t, o, d, p) for t in tranchen)
            ref_stop = max(anf, stop) if stop is not None else anf
            hebel, ko = 1.0, None
            grund = None
            if p["art"] == "ko":
                wunsch = p.get("hebel") or cfg.get("hebel")
                passend, ko_max = P.max_hebel(o, ref_stop, a, cfg)
                hebel = wunsch or passend
                if not hebel or hebel <= 1.05:
                    grund = "kein passender Hebel"
                else:
                    ko = o * (1 - 1 / hebel)
            if grund is None:
                abstand = max(o - anf, 1e-9) / o
                einsatz = equity * cfg["risiko_tranche_pct"] / 100 * P.tranchen_anteil(stufe, cfg) / (hebel * abstand)
                # Gesamtrisiko bis Stop begrenzen
                risiko_alt = sum(max(0.0, _wert(t, o, d, p) - _wert_am_stop(t, _tranche_stop(t, stop), d, p))
                                 for t in tranchen)
                frei = equity * cfg["risiko_gesamt_pct"] / 100 - risiko_alt
                einsatz = min(einsatz, max(0.0, frei) / (hebel * abstand))
                if ko is not None:
                    ko_kap = sum(_wert(t, o, d, p) for t in tranchen if t["ko"] is not None)
                    einsatz = min(einsatz, max(0.0, equity * cfg["ko_kapital_max_pct"] / 100 - ko_kap))
                einsatz = min(einsatz, cash - p["gebuehr"])
                if einsatz < max(50.0, 0.002 * equity):
                    grund = "Risiko- oder Kapitalgrenze"
            if grund is None:
                netto = einsatz * (1 - halb)
                t = {"stufe": stufe, "datum": d, "index_kauf": o, "einsatz": einsatz, "kauf_gebuehr": p["gebuehr"],
                     "anfangsstop": anf, "hebel": hebel, "ko": ko, "basis": ko if ko is not None else 0.0,
                     "anteile": netto / (o - ko) if ko is not None else netto / o}
                cash -= einsatz + p["gebuehr"]
                kosten += einsatz * halb + p["gebuehr"]
                tranchen.append(t)
                if offen is None:
                    offen = {"start": d, "ende": None, "stufen": 0, "einsatz": 0.0, "ergebnis": 0.0, "kosten": 0.0,
                             "ko": 0, "grund": ""}
                    hoechst = c
                    vorlauf.append(i)
                offen["stufen"] += 1
                offen["einsatz"] += einsatz
                offen["kosten"] += einsatz * halb + p["gebuehr"]
            else:
                ereignisse.append({"datum": d, "art": "kauf_ausgelassen", "text": grund})
        auftrag = None
        # 2. Knock-out im Tagesverlauf
        for t in list(tranchen):
            if t["ko"] is not None and l <= _basis(t, d, p):
                offen["ergebnis"] -= t["einsatz"] + t["kauf_gebuehr"]
                offen["ko"] += 1
                ereignisse.append({"datum": d, "art": "ko", "text": f"Stufe {t['stufe']} (Hebel "
                                   f"{t['hebel']:.1f}) ausgeknockt"})
                tranchen.remove(t)
        if offen and not tranchen:
            offen.update(ende=d, grund="Knock-out")
            pyramiden.append(offen)
            offen, hoechst, stop = None, None, None
        # 3. Schluss: Stop nachziehen, Entscheidung fuer morgen
        trend = r["trend"][i]
        a = r["atr"][i]
        if tranchen:
            im_markt += 1
            hoechst = max(hoechst or c, c)
            if a:
                stop = P.nachzieh_stop(hoechst, a, stop, cfg)
        if i < bis_i:
            if tranchen:
                raus = [j for j, t in enumerate(tranchen) if c < _tranche_stop(t, stop)]
                if trend and trend["score"] < cfg["ausstieg_unter"]:
                    auftrag = ("verkauf", list(range(len(tranchen))), "Trend-Score unter "
                               f"{cfg['ausstieg_unter']}")
                elif raus:
                    auftrag = ("verkauf", raus, "Stop")
            if auftrag is None and len(tranchen) < cfg["max_stufen"] and trend and a:
                if not tranchen:
                    sig, _ = P.einstiegssignal(trend, cfg)
                else:
                    letzte = max(t["index_kauf"] for t in tranchen)
                    sig = c >= letzte + cfg["nachkauf_atr"] * a and trend["score"] >= cfg["einstieg_ab"]
                if sig:
                    signale += 1
                    ok, _ = _filter(s, i, trend, bew, cfg)
                    if ok:
                        auftrag = ("kauf", len(tranchen) + 1)
                    else:
                        blockiert += 1
        kurve.append([d, cash + sum(_wert(t, c, d, p) for t in tranchen)])
    # Ende des Zeitraums: offene Tranchen zum letzten Schluss bewerten (nicht verkauft)
    if offen:
        d, c = kerzen[bis_i][0], kerzen[bis_i][4]
        for t in tranchen:
            offen["ergebnis"] += _wert(t, c, d, p) - t["einsatz"] - t["kauf_gebuehr"]
        offen.update(ende=None, grund="läuft noch (zum letzten Schluss bewertet)")
        pyramiden.append(offen)
    return _kennzahlen(kerzen, kurve, pyramiden, ereignisse, kosten, kap, blockiert, signale, im_markt, vorlauf,
                       von_i, bis_i)


def _max_drawdown(werte):
    hoch, dd = -math.inf, 0.0
    for w in werte:
        hoch = max(hoch, w)
        if hoch > 0:
            dd = min(dd, w / hoch - 1)
    return dd * 100


def _jahre(von, bis):
    return max((datetime.date.fromisoformat(bis) - datetime.date.fromisoformat(von)).days / 365.25, 1 / 365.25)


def _kennzahlen(kerzen, kurve, pyramiden, ereignisse, kosten, kap, blockiert, signale, im_markt, vorlauf, von_i,
                bis_i):
    ende = kurve[-1][1] if kurve else kap
    jahre = _jahre(kurve[0][0], kurve[-1][0]) if kurve else 1
    fertig = [x for x in pyramiden if x["ende"]]
    gewinne = [x["ergebnis"] for x in pyramiden if x["ergebnis"] > 0]
    verluste = [x["ergebnis"] for x in pyramiden if x["ergebnis"] <= 0]
    vor = [(kerzen[i + VORLAUF_TAGE][4] / kerzen[i][1] - 1) * 100 for i in vorlauf if i + VORLAUF_TAGE <= bis_i]
    return {"endwert": ende, "rendite_pct": (ende / kap - 1) * 100,
            "cagr_pct": ((ende / kap) ** (1 / jahre) - 1) * 100 if ende > 0 else -100.0,
            "max_dd_pct": _max_drawdown([w for _, w in kurve]), "pyramiden": len(pyramiden),
            "abgeschlossen": len(fertig), "tranchen": sum(x["stufen"] for x in pyramiden),
            "trefferquote_pct": len(gewinne) / len(pyramiden) * 100 if pyramiden else None,
            "gewinn_schnitt": statistics.mean(gewinne) if gewinne else None,
            "verlust_schnitt": statistics.mean(verluste) if verluste else None,
            "profit_faktor": sum(gewinne) / -sum(verluste) if verluste and sum(verluste) < 0 else None,
            "kosten": kosten, "ko_ereignisse": sum(1 for e in ereignisse if e["art"] == "ko"),
            "zeit_im_markt_pct": im_markt / max(len(kurve), 1) * 100, "signale": signale, "blockiert": blockiert,
            "signal_qualitaet_pct": statistics.mean(vor) if vor else None,
            "signal_treffer_pct": sum(1 for x in vor if x > 0) / len(vor) * 100 if vor else None,
            "kurve": kurve, "liste": pyramiden, "ereignisse": ereignisse}


def kaufen_und_halten(kerzen, p, von_i, bis_i):
    kap = float(p["kapital"])
    halb = p["spread_pct"] / 200
    o = kerzen[von_i][1]
    anteile = (kap - p["gebuehr"]) * (1 - halb) / o
    kurve = [[k[0], anteile * k[4]] for k in kerzen[von_i:bis_i + 1]]
    ende = kurve[-1][1]
    jahre = _jahre(kurve[0][0], kurve[-1][0])
    return {"endwert": ende, "rendite_pct": (ende / kap - 1) * 100,
            "cagr_pct": ((ende / kap) ** (1 / jahre) - 1) * 100, "max_dd_pct": _max_drawdown([w for _, w in kurve]),
            "kurve": kurve, "zeit_im_markt_pct": 100.0}


def backtest(kerzen, code, cfg=None, parameter=None, von=None, bis=None, impl_kerzen=None, strategien="ABCD",
             definition="hl", r=None):
    """Alle Strategien auf einer Kerzenreihe. von/bis: iso-Daten (einschliesslich). r: vorberechnete reihen().
    -> {"A": {...}, ..., "halten": {...}, "von", "bis", "parameter", "hinweise"}"""
    cfg = cfg or P.STANDARD
    p = {**STANDARD_PARAMETER, **(parameter or {})}
    if p["art"] not in ("direkt", "ko"):
        raise ValueError("Art muss „direkt“ oder „ko“ sein.")
    if len(kerzen) < P.MIN_KERZEN + 2:
        raise ValueError(f"Zu wenige Tageskerzen: {len(kerzen)} (mindestens {P.MIN_KERZEN + 2}).")
    r = r or reihen(kerzen, cfg, impl_kerzen, mit_fg=any(s in strategien for s in "CD"))
    erste = next(i for i, t in enumerate(r["trend"]) if t is not None)
    von_i = max(erste, next((i for i, k in enumerate(kerzen) if k[0] >= von), len(kerzen)) if von else erste)
    bis_i = max((i for i, k in enumerate(kerzen) if not bis or k[0] <= bis), default=-1)
    if bis_i - von_i < 20:
        raise ValueError("Der Zeitraum ist zu kurz (mindestens 20 Handelstage nach der Vorlaufzeit von gut einem Jahr).")
    bew = Bewerter(kerzen, code, cfg, r, definition)
    aus = {s: simulieren(kerzen, s, r, bew, cfg, p, von_i, bis_i) for s in strategien}
    aus["halten"] = kaufen_und_halten(kerzen, p, von_i, bis_i)
    fg_tage = sum(1 for k in kerzen[von_i:bis_i + 1] if k[0] in r["fg"])
    aus.update(von=kerzen[von_i][0], bis=kerzen[bis_i][0], parameter=p, tage=bis_i - von_i + 1,
               fg_abdeckung_pct=fg_tage / (bis_i - von_i + 1) * 100)
    return aus
