"""Pyramidenmanager - Rechenkern (Etappe 1): technischer Trend-Score, Einstiegs- und Nachkaufsignale, Stufen,
Stops, Risiko, dynamischer KO-Hebel, abgeleitete Gap- und Fear-&-Greed-Einstiegswerte, kombinierter Wert und die
Pruefung vor jedem Nachkauf.

Reine Rechenlogik ohne Streamlit und ohne Netz. Die Daten kommen ueber pyramide_daten.py aus den vorhandenen
Werkzeugen (Gap Analyzer, Fear & Greed, KO-Rechner) - hier wird nichts davon nachgebaut oder veraendert.
Long-Pyramiden (Kauf in einen Aufwaertstrend). Keine Orders: alles sind Signale und Rechnungen.

Kerzen: [[iso, open, high, low, close]] aufsteigend (Format von state/markt/ohlc.json)."""
import copy
import math

import ko_rechner as KO

# ---------------------------------------------------------------- Startwerte (alle in der Ansicht aenderbar)
STANDARD = {
    "einstieg_ab": 60,          # Trend-Score fuer Stufe 1 und jeden Nachkauf
    "ausstieg_unter": 40,       # Trend-Score darunter -> Ausstiegssignal fuer alle Tranchen
    "nachkauf_atr": 1.0,        # Nachkauf erst, wenn der Index seit dem letzten Kauf so viele ATR gestiegen ist
    "max_stufen": 20,
    "groesse_faktor": 0.8,      # jede weitere Tranche = vorherige x Faktor (Pyramide) ...
    "groesse_min": 0.2,         # ... aber mindestens dieser Anteil der Grundgroesse
    "stop_anfang_atr": 2.0,     # Anfangsstop je Tranche: Kaufkurs - 2 ATR
    "stop_nachzieh_atr": 3.0,   # gemeinsamer Nachzieh-Stop: hoechster Schluss - 3 ATR (steigt nur)
    "risiko_tranche_pct": 1.0,  # max. Risiko bis Stop je neuer Tranche, in % des Pyramidenkapitals
    "risiko_gesamt_pct": 6.0,   # max. Risiko bis Stop aller Tranchen zusammen
    "ko_puffer_atr": 1.0,       # KO-Schwelle mind. so viele ATR UNTER dem Stop (der Stop greift vor dem KO)
    "hebel": None,              # gewuenschter Hebel je Pyramide (frei waehlbar); None = passender Hebel zum Stop
    "hebel_max": 20.0,          # Obergrenze fuer den vorgeschlagenen (passenden) Hebel
    "ko_kapital_max_pct": 50.0, # max. Anteil des Pyramidenkapitals, der in KO-Zertifikaten steckt
    "atr_tage": 20,
    "gap_naehe_atr": 2.0,       # nur offene Gaps innerhalb so vieler ATR zaehlen fuer den Gap-Wert
    "gap_fenster": 20,          # Fuellquote des Gap Analyzers nach so vielen Handelstagen
    "fg_modus": "kontraer",     # "kontraer" (100 - F&G), "trend" (= F&G) oder "aus"
    "gewichte": {"trend": 70, "gap": 20, "fg": 10},
    "max_alter_handelstage": 3, # aelter = veraltet (zaehlt nicht)
}
HINWEIS_STUFEN = ((60, "unterstützt"), (40, "neutral"), (0, "Vorsicht"))
MIN_KERZEN = 253 + 20            # 12-Monats-Momentum + 20 Tage Steigung der 200-Tage-Linie


# erlaubte Bereiche je Einstellung (Werte ausserhalb werden auf die Grenze gesetzt, ungueltige ignoriert)
GRENZEN = {
    "einstieg_ab": (0, 100), "ausstieg_unter": (0, 100), "nachkauf_atr": (0.1, 10.0), "max_stufen": (1, 20),
    "groesse_faktor": (0.1, 1.0), "groesse_min": (0.05, 1.0), "stop_anfang_atr": (0.25, 10.0),
    "stop_nachzieh_atr": (0.25, 10.0), "risiko_tranche_pct": (0.05, 10.0), "risiko_gesamt_pct": (0.1, 50.0),
    "ko_puffer_atr": (0.0, 10.0), "hebel": (1.0, 20.0), "hebel_max": (1.0, 20.0), "ko_kapital_max_pct": (0.0, 100.0),
    "atr_tage": (5, 50), "gap_naehe_atr": (0.25, 10.0), "gap_fenster": (1, 60), "max_alter_handelstage": (0, 20),
}
GANZZAHL = {"max_stufen", "atr_tage", "gap_fenster", "max_alter_handelstage"}


def einstellungen(aenderungen=None):
    """Startwerte mit eigenen Aenderungen (je Pyramide). Zahlen werden auf GRENZEN begrenzt, Unbekanntes und
    Ungueltiges ignoriert; "hebel": None = automatisch passender Hebel; "gewichte" als dict."""
    cfg = copy.deepcopy(STANDARD)
    for k, v in (aenderungen or {}).items():
        if k == "gewichte" and isinstance(v, dict):
            cfg["gewichte"].update({g: max(0.0, float(w)) for g, w in v.items()
                                    if g in cfg["gewichte"] and isinstance(w, (int, float))})
        elif k == "fg_modus":
            if v in FG_MODI:
                cfg[k] = v
        elif k == "hebel" and v is None:
            cfg[k] = None
        elif k in GRENZEN and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            lo, hi = GRENZEN[k]
            v = min(hi, max(lo, v))
            cfg[k] = int(round(v)) if k in GANZZAHL else float(v)
    return cfg


def cfg_fuer(pyr):
    """Wirksame Einstellungen einer Pyramide (ihre eigenen Aenderungen auf den Startwerten)."""
    return einstellungen((pyr or {}).get("einstellungen"))


def _linear(x, lo, hi):
    """0 bei x <= lo, 1 bei x >= hi, dazwischen linear."""
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def sma(werte, n):
    return sum(werte[-n:]) / n if len(werte) >= n else None


def atr(kerzen, n=20):
    """Average True Range (einfacher Durchschnitt der letzten n True Ranges) in Indexpunkten."""
    if len(kerzen) < n + 1:
        return None
    tr = [max(k[2] - k[3], abs(k[2] - v[4]), abs(k[3] - v[4])) for v, k in zip(kerzen[-n - 1:-1], kerzen[-n:])]
    return sum(tr) / n


def hinweis_stufe(wert):
    if wert is None:
        return "fehlt"
    return next(t for grenze, t in HINWEIS_STUFEN if wert >= grenze)


# ---------------------------------------------------------------- 1. technischer Trend-Score
TREND_TEILE = {"lage": ("Lage zu 50-/200-Tage-Linie", 25), "steigung": ("Steigung der Linien", 20),
               "momentum": ("Momentum 3/6/12 Monate", 25), "hoch": ("Nähe zum 52-Wochen-Hoch", 15),
               "stabil": ("Trendstabilität (Tage über 50-Tage-Linie)", 15)}


def trend_score(kerzen):
    """Technischer Trend-Score 0-100 aus abgeschlossenen Tageskerzen (nur Vergangenheit bis zur letzten Kerze).
    -> {"score", "teile": {key: 0..1}, "werte": {...}} oder None bei zu wenigen Kerzen."""
    if len(kerzen) < MIN_KERZEN:
        return None
    c = [k[4] for k in kerzen]
    kurs = c[-1]
    s50, s200 = sma(c, 50), sma(c, 200)
    s50_alt, s200_alt = sma(c[:-20], 50), sma(c[:-20], 200)
    lage = 0.5 * (kurs > s50) + 0.5 * (s50 > s200)
    steigung = 0.5 * (s50 > s50_alt) + 0.5 * (s200 > s200_alt)
    renditen = {m: kurs / c[-1 - t] - 1 for m, t in ((3, 63), (6, 126), (12, 252))}
    momentum = 0.4 * (renditen[3] > 0) + 0.3 * (renditen[6] > 0) + 0.3 * (renditen[12] > 0)
    hoch52 = max(c[-252:])
    abstand = (1 - kurs / hoch52) * 100
    hoch = 1 - _linear(abstand, 3.0, 20.0)
    ueber = sum(1 for i in range(60) if c[-1 - i] > sma(c[:len(c) - i], 50)) / 60
    teile = {"lage": lage, "steigung": steigung, "momentum": momentum, "hoch": hoch, "stabil": ueber}
    score = sum(TREND_TEILE[k][1] * v for k, v in teile.items())
    return {"score": round(score, 1), "teile": teile, "datum": kerzen[-1][0],
            "werte": {"kurs": kurs, "sma50": s50, "sma200": s200, "rendite_3m": renditen[3] * 100,
                      "rendite_6m": renditen[6] * 100, "rendite_12m": renditen[12] * 100,
                      "abstand_hoch_pct": abstand, "tage_ueber_sma50_pct": ueber * 100}}


def einstiegssignal(trend, cfg=STANDARD):
    """Stufe 1: Score >= Schwelle, Kurs > 200-Tage-Linie, 50-Tage-Linie > 200-Tage-Linie -> (bool, gruende)."""
    if not trend:
        return False, ["Zu wenige Tageskerzen für den Trend-Score."]
    w, gruende = trend["werte"], []
    if trend["score"] < cfg["einstieg_ab"]:
        gruende.append(f"Trend-Score {trend['score']:.0f} unter {cfg['einstieg_ab']}.")
    if w["kurs"] <= w["sma200"]:
        gruende.append("Kurs nicht über der 200-Tage-Linie.")
    if w["sma50"] <= w["sma200"]:
        gruende.append("50-Tage-Linie nicht über der 200-Tage-Linie.")
    return not gruende, gruende


# ---------------------------------------------------------------- 2. Stufen, Stops, Groessen
def tranchen_anteil(stufe, cfg=STANDARD):
    """Anteil der Grundgroesse fuer Stufe 1..max_stufen (Pyramide: kleiner werdend)."""
    return max(cfg["groesse_min"], cfg["groesse_faktor"] ** (stufe - 1))


def anfangsstop(index_kauf, atr_wert, cfg=STANDARD):
    return index_kauf - cfg["stop_anfang_atr"] * atr_wert


def nachzieh_stop(hoechster_schluss, atr_wert, bisher=None, cfg=STANDARD):
    """Gemeinsamer Stop: hoechster Schluss seit Start - k ATR; steigt nur."""
    neu = hoechster_schluss - cfg["stop_nachzieh_atr"] * atr_wert
    return neu if bisher is None else max(bisher, neu)


def tranche_stop(tranche, gemeinsam):
    """Wirksamer Stop einer Tranche: der hoehere aus Anfangsstop und gemeinsamem Nachzieh-Stop."""
    return max(x for x in (tranche.get("anfangsstop"), gemeinsam) if x is not None)


def nachkaufsignal(pyr, trend, atr_wert, cfg=STANDARD):
    """Gueltiges Nachkaufsignal? -> (bool, naechste_marke, gruende). Erste Stufe ueber einstiegssignal()."""
    tr = (pyr or {}).get("tranchen") or []
    if not tr:
        ok, gruende = einstiegssignal(trend, cfg)
        return ok, None, gruende
    if len(tr) >= cfg["max_stufen"]:
        return False, None, [f"Höchstzahl von {cfg['max_stufen']} Stufen erreicht."]
    if not trend or atr_wert is None:
        return False, None, ["Zu wenige Tageskerzen für Trend-Score und ATR."]
    letzte = max(t["index_kauf"] for t in tr)
    marke = letzte + cfg["nachkauf_atr"] * atr_wert
    gruende = []
    if trend["werte"]["kurs"] < marke:
        gruende.append(f"Index noch unter der Nachkaufmarke {KO.de(marke, 0)} "
                       f"(letzter Kauf + {KO.de(cfg['nachkauf_atr'], 1)} ATR).")
    if trend["score"] < cfg["einstieg_ab"]:
        gruende.append(f"Trend-Score {trend['score']:.0f} unter {cfg['einstieg_ab']}.")
    return not gruende, marke, gruende


def ausstiegssignal(trend, kurs, stop, cfg=STANDARD):
    gruende = []
    if stop is not None and kurs is not None and kurs < stop:
        gruende.append(f"Schlusskurs {KO.de(kurs, 0)} unter dem Stop {KO.de(stop, 0)}.")
    if trend and trend["score"] < cfg["ausstieg_unter"]:
        gruende.append(f"Trend-Score {trend['score']:.0f} unter {cfg['ausstieg_unter']}.")
    return bool(gruende), gruende


# ---------------------------------------------------------------- 3. Werte und Risiko
def tranche_wert(t, index, tage=0, eurusd=None):
    """Wert einer Tranche in EUR bei Indexstand `index`.
    art "direkt": ungehebelt (Index-ETF o. ae.) - Einsatz x Index/Index beim Kauf.
    art "ko": Knock-out-Zertifikat (Modell des KO-Rechners: innerer Wert, Finanzierung verschiebt den Basispreis);
              bei Erreichen der KO-Schwelle 0."""
    if t["art"] == "direkt":
        return t["stueck"] * t["kaufkurs"] * index / t["index_kauf"]
    p = t["produkt"]
    basis, ko = KO.basispreis_am(p, tage)
    if (index <= ko) if p["richtung"] == "long" else (index >= ko):
        return 0.0
    return t["stueck"] * KO.innerer_wert_eur(p, index, basis, eurusd)


def tranche_einsatz(t):
    return t["stueck"] * t["kaufkurs"]


def risiko(pyr, index, stop, eurusd=None, tage_je_tranche=None):
    """Risiko bis Stop je Tranche und gesamt (EUR) + KO-Kapitalrisiko.
    risiko = max(0, Wert jetzt - Wert am Stop): was bei einem Stop-Verkauf vom heutigen Stand verloren ginge."""
    zeilen = []
    for i, t in enumerate((pyr or {}).get("tranchen") or []):
        tage = (tage_je_tranche or {}).get(i, 0)
        s = tranche_stop(t, stop)
        jetzt = tranche_wert(t, index, tage, eurusd)
        am_stop = tranche_wert(t, s, tage, eurusd)
        zeilen.append({"stufe": t["stufe"], "art": t["art"], "stop": s, "wert": jetzt, "wert_am_stop": am_stop,
                       "einsatz": tranche_einsatz(t), "risiko": max(0.0, jetzt - am_stop),
                       "ko_schwelle": KO.basispreis_am(t["produkt"], tage)[1] if t["art"] == "ko" else None})
    ko = [z for z in zeilen if z["art"] == "ko"]
    kap = (pyr or {}).get("kapital") or 0
    gesamt = sum(z["risiko"] for z in zeilen)
    return {"tranchen": zeilen, "gesamt": gesamt, "gesamt_pct": gesamt / kap * 100 if kap else None,
            "ko_kapital": sum(z["wert"] for z in ko), "ko_kapital_pct": sum(z["wert"] for z in ko) / kap * 100
            if kap else None, "wert": sum(z["wert"] for z in zeilen)}


def max_hebel(kurs, stop, atr_wert, cfg=STANDARD):
    """Dynamischer Hebel: hoechste KO-Schwelle = Stop - Puffer x ATR; Hebel = Kurs / (Kurs - KO), gedeckelt.
    -> (hebel, ko_schwelle_max) oder (None, None), wenn kein sinnvoller Hebel moeglich ist."""
    if not kurs or stop is None or atr_wert is None:
        return None, None
    ko = stop - cfg["ko_puffer_atr"] * atr_wert
    if ko <= 0 or ko >= kurs:
        return None, None
    return min(cfg["hebel_max"], kurs / (kurs - ko)), ko


def ko_abstand_ok(ko_schwelle, stop, atr_wert, cfg=STANDARD):
    """Liegt die KO-Schwelle mindestens Puffer x ATR unter dem Stop?"""
    return ko_schwelle <= stop - cfg["ko_puffer_atr"] * atr_wert


def ko_fuer_hebel(kurs, hebel):
    """Ungefaehre KO-Schwelle eines Long-KO mit diesem Hebel (KO = Basispreis): Kurs x (1 - 1/Hebel)."""
    return kurs * (1 - 1 / hebel) if kurs and hebel and hebel > 1 else None


def hebel_bewertung(kurs, stop, atr_wert, cfg=STANDARD, hebel=None):
    """Frei gewaehlter Hebel gegen den zum Stop passenden Hebel. Ein zu hoher Hebel wird nicht gesperrt, sondern
    gewarnt. hebel: gewaehlter Hebel (sonst cfg["hebel"]; None = passender Hebel wird vorgeschlagen).
    -> {"gewaehlt", "passend", "ko_max", "ko_bei_gewaehlt", "warnung"}"""
    passend, ko_max = max_hebel(kurs, stop, atr_wert, cfg)
    gewaehlt = hebel if hebel is not None else cfg.get("hebel")
    aus = {"gewaehlt": gewaehlt, "passend": passend, "ko_max": ko_max, "ko_bei_gewaehlt": None, "warnung": None}
    if gewaehlt is None:
        return aus
    aus["ko_bei_gewaehlt"] = ko_fuer_hebel(kurs, gewaehlt)
    if passend is None:
        aus["warnung"] = "Zum aktuellen Stop passt kein Hebel-Produkt (Stop/ATR fehlen oder liegen zu nah am Kurs)."
    elif gewaehlt > passend + 1e-9:
        aus["warnung"] = (f"Hebel {KO.de(gewaehlt, 1)} liegt über dem passenden Hebel {KO.de(passend, 1)}: "
                          f"die KO-Schwelle (ca. {KO.de(aus['ko_bei_gewaehlt'], 0)}) läge über "
                          f"{KO.de(ko_max, 0)} – das KO könnte vor dem Stop greifen.")
    return aus


# ---------------------------------------------------------------- 4. Gap-Wert (abgeleitet aus dem Gap Analyzer)
def gap_wert(gap_daten, kurs, atr_wert, cfg=STANDARD):
    """Abgeleiteter Gap-Wert 0-100 aus den Ergebnissen des Gap Analyzers (offene Gaps nahe am Kurs, gewichtet
    mit der dort ausgewiesenen Fuellquote). Kein Kauf-/Verkaufssignal.
    gap_daten: {"gaps": [mit_lage], "statistik": {...}, "status": aktuell/veraltet/fehlt, "stand", "definition"}
    -> {"wert", "stufe", "gruende", "status", "naehe": [...]}"""
    if not gap_daten or gap_daten.get("status") == "fehlt" or not kurs or atr_wert is None:
        return {"wert": None, "stufe": "fehlt", "status": "fehlt", "gruende": ["Keine Gap-Analyse verfügbar."],
                "naehe": []}
    grenze = cfg["gap_naehe_atr"] * atr_wert
    stat = gap_daten.get("statistik") or {}

    def quote(typ):
        q = ((stat.get(typ) or {}).get("quoten") or {}).get(cfg["gap_fenster"]) or (None, 0)
        return (q[0] / 100) if q[0] is not None else None

    oben = [g for g in gap_daten.get("gaps") or [] if g.get("status") != "geschlossen"
            and g.get("lage") in ("oberhalb", "innerhalb") and g.get("entfernung") is not None
            and g["entfernung"] <= grenze]
    unten = [g for g in gap_daten.get("gaps") or [] if g.get("status") != "geschlossen"
             and g.get("lage") in ("unterhalb", "innerhalb") and g.get("entfernung") is not None
             and g["entfernung"] <= grenze]
    wert, gruende = 50.0, []
    # Gap unter dem Kurs (meist ein Gap Up) = moegliches Ruecklaufziel -> Vorsicht beim Kauf jetzt
    for g in unten:
        q = quote(g["typ"])
        if q is None:
            continue
        nah = 1 - g["entfernung"] / grenze
        wert -= 25 * q * nah
        gruende.append(f"Offenes Gap {_gap_text(g)} {KO.de(g['entfernung'], 0)} Punkte unter dem Kurs – "
                       f"{KO.de(q * 100, 0)} % solcher Gaps wurden binnen {cfg['gap_fenster']} Tagen gefüllt "
                       "(mögliches Rücklaufziel).")
    # Gap ueber dem Kurs = moegliches Ziel nach oben -> stuetzt den Einstieg
    for g in oben:
        q = quote(g["typ"])
        if q is None:
            continue
        nah = 1 - g["entfernung"] / grenze
        wert += 25 * q * nah
        gruende.append(f"Offenes Gap {_gap_text(g)} {KO.de(g['entfernung'], 0)} Punkte über dem Kurs – "
                       f"{KO.de(q * 100, 0)} % solcher Gaps wurden binnen {cfg['gap_fenster']} Tagen gefüllt "
                       "(mögliches Ziel nach oben).")
    if not gruende:
        gruende.append(f"Kein offenes Gap innerhalb von {KO.de(cfg['gap_naehe_atr'], 1)} ATR um den Kurs.")
    wert = max(0.0, min(100.0, wert))
    status = gap_daten.get("status") or "aktuell"
    return {"wert": round(wert, 1), "stufe": hinweis_stufe(wert), "status": status, "gruende": gruende,
            "naehe": oben + [g for g in unten if g not in oben], "stand": gap_daten.get("stand"),
            "definition": gap_daten.get("definition")}


def _gap_text(g):
    return f"{'Up' if g['typ'] == 'up' else 'Down'} vom {g['datum']} ({KO.de(g['offen_unten'], 0)}–" \
           f"{KO.de(g['offen_oben'], 0)})"


# ---------------------------------------------------------------- 5. Fear & Greed -> Einstiegswert
FG_MODI = {"kontraer": "Konträr im Aufwärtstrend (Einstiegswert = 100 − F&G)",
           "trend": "Trendfolgend (Einstiegswert = F&G)", "aus": "Aus (Fear & Greed zählt nicht)"}


def fg_einstiegswert(fg, cfg=STANDARD):
    """Originalwert, Deutung und abgeleiteter Einstiegswert getrennt.
    fg: {"wert", "kategorie", "status", "zeit", "quelle", "bezug": "index"/"us"} oder None."""
    modus = cfg["fg_modus"]
    if modus == "aus":
        return {"original": (fg or {}).get("wert"), "deutung": (fg or {}).get("kategorie"), "wert": None,
                "stufe": "aus", "status": "aus", "modus": modus, "gruende": ["Fear & Greed ist ausgeschaltet."]}
    if not fg or fg.get("wert") is None or fg.get("status") == "fehlt":
        return {"original": None, "deutung": None, "wert": None, "stufe": "fehlt", "status": "fehlt",
                "modus": modus, "gruende": ["Kein Fear-&-Greed-Wert für diesen Index verfügbar."]}
    w = float(fg["wert"])
    ein = 100 - w if modus == "kontraer" else w
    text = (f"{fg.get('quelle') or 'Fear & Greed'}: {KO.de(w, 0)} ({fg.get('kategorie') or '–'}) → "
            f"Einstiegswert {KO.de(ein, 0)} ({FG_MODI[modus]}).")
    gruende = [text]
    if fg.get("bezug") == "us":
        gruende.append("US-marktweiter Wert – keine indexspezifische Bewertung.")
    return {"original": w, "deutung": fg.get("kategorie"), "wert": round(ein, 1), "stufe": hinweis_stufe(ein),
            "status": fg.get("status") or "aktuell", "modus": modus, "gruende": gruende,
            "quelle": fg.get("quelle"), "zeit": fg.get("zeit"), "bezug": fg.get("bezug")}


# ---------------------------------------------------------------- 6. kombinierter Wert
def kombiniert(trend, gap, fg, cfg=STANDARD):
    """Gewichteter Analysewert. Fehlt ein gewichteter Teil oder ist er veraltet, wird NICHT gerechnet
    (kein stilles "neutral"). Gewicht 0 bzw. F&G "aus" = Teil zaehlt nicht. -> {"wert", "grund", "teile"}"""
    g = cfg["gewichte"]
    teile = {"trend": (trend or {}).get("score"), "gap": (gap or {}).get("wert"), "fg": (fg or {}).get("wert")}
    status = {"trend": "aktuell" if teile["trend"] is not None else "fehlt",
              "gap": (gap or {}).get("status", "fehlt"), "fg": (fg or {}).get("status", "fehlt")}
    aktiv = {k: w for k, w in g.items() if w and not (k == "fg" and cfg["fg_modus"] == "aus")}
    namen = {"trend": "Trend-Score", "gap": "Gap-Analyse", "fg": "Fear & Greed"}
    fehlt = [namen[k] for k in aktiv if teile[k] is None or status[k] in ("fehlt", "veraltet")]
    if fehlt or not aktiv:
        return {"wert": None, "teile": teile, "status": status,
                "grund": "nicht berechenbar – " + (", ".join(fehlt) + " fehlt/veraltet" if fehlt else
                                                   "keine Gewichte gesetzt")}
    summe = sum(aktiv.values())
    wert = sum(w * teile[k] for k, w in aktiv.items()) / summe
    return {"wert": round(wert, 1), "teile": teile, "status": status, "grund": None,
            "gewichte": {k: w / summe * 100 for k, w in aktiv.items()}}


# ---------------------------------------------------------------- 7. Pruefung vor einem Nachkauf
def nachkauf_pruefung(pyr, trend, atr_wert, gap, fg, neue_tranche, index, stop_bisher=None, eurusd=None,
                      cfg=None):
    """Die acht Pruefungen vor einem (geplanten) Nachkauf.
    neue_tranche: geplante Tranche (art, stueck, kaufkurs, index_kauf, produkt) oder None (nur Signal pruefen).
    -> {"erlaubt", "pruefungen": [{"nr", "name", "art": pflicht/hinweis, "ergebnis", "text"}],
        "risiko_vor", "risiko_nach", "stop", "hebel"}
    cfg: Einstellungen; ohne Angabe die der Pyramide (cfg_fuer). atr_wert muss mit cfg["atr_tage"] gerechnet sein."""
    cfg = cfg or cfg_fuer(pyr)
    kap = (pyr or {}).get("kapital") or 0
    p = []
    hoechst = max([k for k in ((pyr or {}).get("hoechst"), index) if k is not None], default=None)
    stop = nachzieh_stop(hoechst, atr_wert, stop_bisher, cfg) if (hoechst and atr_wert) else stop_bisher

    # 1 Trend
    w = (trend or {}).get("werte") or {}
    trend_ok = bool(trend) and trend["score"] >= cfg["einstieg_ab"] and w.get("kurs", 0) > w.get("sma200", math.inf)
    p.append({"nr": 1, "name": "Technische Trendbestätigung", "art": "pflicht", "ergebnis": "ok" if trend_ok else "nein",
              "text": (f"Trend-Score {trend['score']:.0f}, Kurs über der 200-Tage-Linie." if trend_ok else
                       "Kein bestätigter Aufwärtstrend." if trend else "Trend-Score nicht berechenbar.")})
    # 2 Signal
    sig, marke, gr = nachkaufsignal(pyr, trend, atr_wert, cfg)
    p.append({"nr": 2, "name": "Gültiges Einstiegs-/Nachkaufsignal", "art": "pflicht",
              "ergebnis": "ok" if sig else "nein", "text": "Signal liegt vor." if sig else " ".join(gr)})
    # 3 Gap, 4 F&G (Hinweise)
    for nr, name, teil in ((3, "Gap-Analyse", gap), (4, "Fear & Greed", fg)):
        stufe = (teil or {}).get("stufe", "fehlt")
        if (teil or {}).get("status") == "veraltet":
            stufe = "veraltet"
        p.append({"nr": nr, "name": name, "art": "hinweis", "ergebnis": stufe,
                  "text": " ".join((teil or {}).get("gruende") or ["Keine Daten."])})
    # 5 offene Tranchen
    n = len((pyr or {}).get("tranchen") or [])
    vor = risiko(pyr, index, stop, eurusd) if n else {"gesamt": 0.0, "gesamt_pct": 0.0, "ko_kapital": 0.0,
                                                       "ko_kapital_pct": 0.0, "tranchen": [], "wert": 0.0}
    unter_wasser = [z for z in vor["tranchen"] if z["wert"] < z["einsatz"]]
    p.append({"nr": 5, "name": "Bestehende offene Tranchen", "art": "hinweis",
              "ergebnis": "Vorsicht" if unter_wasser else "neutral",
              "text": f"{n} offene Tranche(n)" + (f", davon {len(unter_wasser)} im Minus – Nachkäufe nur in Gewinne."
                                                  if unter_wasser else ".")})
    # Risiko nach dem Kauf
    nach = vor
    neu_risiko = 0.0
    if neue_tranche:
        t = dict(neue_tranche, stufe=n + 1)
        t.setdefault("anfangsstop", anfangsstop(t["index_kauf"], atr_wert, cfg) if atr_wert else None)
        pyr_nach = dict(pyr or {}, tranchen=list((pyr or {}).get("tranchen") or []) + [t])
        nach = risiko(pyr_nach, index, stop, eurusd)
        neu_risiko = nach["tranchen"][-1]["risiko"]
    # 6 Stop-Risiko gesamt
    g_pct = nach["gesamt_pct"]
    ok6 = kap > 0 and g_pct is not None and g_pct <= cfg["risiko_gesamt_pct"] + 1e-9
    p.append({"nr": 6, "name": "Gesamtes Stop-Risiko", "art": "pflicht", "ergebnis": "ok" if ok6 else "nein",
              "text": (f"{KO.de(g_pct or 0, 2)} % des Kapitals bis Stop (Grenze {KO.de(cfg['risiko_gesamt_pct'], 1)} %)."
                       if kap else "Kein Pyramidenkapital hinterlegt.")})
    # 7 KO-Kapitalrisiko (Pflicht) + Hebel/KO-Abstand (Warnung, der Hebel ist frei waehlbar)
    stop_basis = stop if stop is not None else (anfangsstop(index, atr_wert, cfg) if atr_wert else None)
    hebel_neu = None
    if neue_tranche and neue_tranche.get("art") == "ko":
        try:
            hebel_neu = KO.produkt_hebel(neue_tranche["produkt"], index, eurusd)
        except (KeyError, ValueError, ZeroDivisionError):
            hebel_neu = None
    hb = hebel_bewertung(index, stop_basis, atr_wert, cfg, hebel_neu)
    ok7 = nach["ko_kapital_pct"] is None or nach["ko_kapital_pct"] <= cfg["ko_kapital_max_pct"] + 1e-9
    p.append({"nr": 7, "name": "KO-Kapitalrisiko", "art": "pflicht", "ergebnis": "ok" if ok7 else "nein",
              "text": f"KO-Kapital {KO.de(nach['ko_kapital'], 0)} € ({KO.de(nach['ko_kapital_pct'] or 0, 1)} % des "
                      f"Kapitals, Grenze {KO.de(cfg['ko_kapital_max_pct'], 0)} %) – bei KO verloren."})
    warn = []
    if neue_tranche and neue_tranche.get("art") == "ko" and atr_wert:
        ko_neu = nach["tranchen"][-1]["ko_schwelle"]
        if not ko_abstand_ok(ko_neu, nach["tranchen"][-1]["stop"], atr_wert, cfg):
            warn.append(f"KO-Schwelle {KO.de(ko_neu, 0)} liegt nicht mindestens {KO.de(cfg['ko_puffer_atr'], 1)} ATR "
                        f"unter dem Stop {KO.de(nach['tranchen'][-1]['stop'], 0)} – das KO könnte vor dem Stop greifen.")
    elif hb["warnung"]:
        warn.append(hb["warnung"])
    if hb["passend"] is not None:
        warn_text = f"Zum Stop passender Hebel bis {KO.de(hb['passend'], 1)} (KO höchstens {KO.de(hb['ko_max'], 0)})."
    else:
        warn_text = "Kein passender Hebel berechenbar."
    p.append({"nr": 7.5, "name": "Hebel und KO-Abstand zum Stop", "art": "hinweis",
              "ergebnis": "Vorsicht" if warn else "neutral", "text": " ".join(warn + [warn_text])})
    # 8 Risikobudget der neuen Tranche
    if neue_tranche:
        grenze = kap * cfg["risiko_tranche_pct"] / 100
        rest = kap * cfg["risiko_gesamt_pct"] / 100 - vor["gesamt"]
        ok8 = kap > 0 and neu_risiko <= grenze + 1e-9 and neu_risiko <= rest + 1e-9
        text = (f"Neue Tranche riskiert {KO.de(neu_risiko, 0)} € bis Stop; je Tranche erlaubt "
                f"{KO.de(grenze, 0)} €, frei im Gesamtbudget {KO.de(max(0.0, rest), 0)} €.")
    else:
        ok8 = False
        text = "Keine geplante Tranche angegeben – Budget nicht prüfbar."
    p.append({"nr": 8, "name": "Verfügbares Risikobudget", "art": "pflicht", "ergebnis": "ok" if ok8 else "nein",
              "text": text})
    erlaubt = all(x["ergebnis"] == "ok" for x in p if x["art"] == "pflicht")
    return {"erlaubt": erlaubt, "pruefungen": p, "risiko_vor": vor, "risiko_nach": nach, "stop": stop,
            "nachkauf_marke": marke, "hebel": hb, "einstellungen": cfg}


# ---------------------------------------------------------------- 8. Pyramiden-Datensatz (Speicherformat je Benutzer)
# {"pyramiden": [{"id", "index", "name", "kapital", "start", "status": "offen"/"geschlossen", "einstellungen": {},
#                 "tranchen": [tranche], "ereignisse": [{"datum", "art", "text"}], "ende"}]}
# tranche: {"stufe", "datum", "art": "direkt"/"ko", "stueck", "kaufkurs", "index_kauf", "anfangsstop", "wkn",
#           "name", "produkt": {basiswert, richtung, basispreis, ko_schwelle, bezug, brief, finanzierung_pct, quanto}}
# Reine Buchfuehrung: es werden nie Orders ausgeloest.
PRODUKT_FELDER = ("basiswert", "richtung", "basispreis", "ko_schwelle", "bezug", "brief", "geld",
                  "finanzierung_pct", "quanto", "isin", "wkn", "name", "emittent")


def neue_pyramide(pid, index, name, kapital, datum, einstellungen_=None):
    if index not in KO.INDIZES:
        raise ValueError("Unbekannter Index.")
    if not kapital or kapital <= 0:
        raise ValueError("Das Pyramidenkapital muss größer als 0 sein.")
    return {"id": str(pid), "index": index, "name": (name or KO.INDIZES[index]["name"]).strip()[:60],
            "kapital": float(kapital), "start": str(datum), "status": "offen",
            "einstellungen": dict(einstellungen_ or {}), "tranchen": [],
            "ereignisse": [{"datum": str(datum), "art": "start", "text": "Pyramide angelegt."}]}


def tranche_pruefen(t, index):
    """Plausibilitaet einer erfassten Tranche -> Liste von Fehlern (leer = ok)."""
    f = []
    if t.get("art") not in ("direkt", "ko"):
        f.append("Art muss „direkt“ oder „KO-Zertifikat“ sein.")
    for feld, text in (("stueck", "Stückzahl"), ("kaufkurs", "Kaufkurs"), ("index_kauf", "Indexstand beim Kauf")):
        if not (isinstance(t.get(feld), (int, float)) and t[feld] > 0):
            f.append(f"{text} muss größer als 0 sein.")
    if t.get("art") == "ko":
        p = t.get("produkt") or {}
        fehler, _ = KO.produkt_pruefen(p)
        f += fehler
        if p.get("basiswert") and p["basiswert"] != index:
            f.append(f"Das Zertifikat bezieht sich auf {p['basiswert']}, die Pyramide auf {index}.")
        if p.get("richtung") and p["richtung"] != "long":
            f.append("Die Pyramide ist eine Long-Pyramide – nur Long-Zertifikate.")
    return f


def tranche_hinzufuegen(pyr, t, atr_wert=None, cfg=None):
    """Tranche als naechste Stufe anhaengen (Anfangsstop aus der ATR, falls nicht angegeben). -> neue Pyramide"""
    cfg = cfg or cfg_fuer(pyr)
    f = tranche_pruefen(t, pyr["index"])
    if f:
        raise ValueError(f[0])
    if len(pyr["tranchen"]) >= cfg["max_stufen"]:
        raise ValueError(f"Höchstzahl von {cfg['max_stufen']} Stufen erreicht.")
    neu = copy.deepcopy(pyr)
    t = {k: v for k, v in t.items() if k != "produkt"} | (
        {"produkt": {k: t["produkt"].get(k) for k in PRODUKT_FELDER}} if t.get("art") == "ko" else {})
    t["stufe"] = len(neu["tranchen"]) + 1
    if t.get("anfangsstop") is None and atr_wert:
        t["anfangsstop"] = anfangsstop(t["index_kauf"], atr_wert, cfg)
    neu["tranchen"].append(t)
    neu["ereignisse"].append({"datum": t.get("datum"), "art": "kauf",
                              "text": f"Stufe {t['stufe']}: {t['stueck']:g} × {KO.de(t['kaufkurs'], 2)} € "
                                      f"({'KO ' + (t.get('wkn') or '') if t['art'] == 'ko' else 'direkt'}) bei Index "
                                      f"{KO.de(t['index_kauf'], 0)}"})
    return neu


def stop_verlauf(kerzen, start, cfg=STANDARD):
    """Gemeinsamer Nachzieh-Stop je Handelstag ab `start` (nur Daten bis zum jeweiligen Tag).
    -> [(datum, schluss, hoechster_schluss, stop)]"""
    aus, stop, hoechst = [], None, None
    n = cfg["atr_tage"]
    for i, k in enumerate(kerzen):
        if k[0] < start:
            continue
        hoechst = k[4] if hoechst is None else max(hoechst, k[4])
        a = atr(kerzen[:i + 1], n)
        if a:
            stop = nachzieh_stop(hoechst, a, stop, cfg)
        aus.append((k[0], k[4], hoechst, stop))
    return aus


def status(pyr, kerzen, kurs=None, eurusd=None, trend=None):
    """Aktueller Stand einer Pyramide: Stufe, Stop, Hoechststand, Risiko, naechste Nachkaufmarke, Ausstieg.
    kurs: aktueller Indexstand (sonst letzter Schluss)."""
    cfg = cfg_fuer(pyr)
    verlauf = stop_verlauf(kerzen, pyr["start"], cfg)
    a = atr(kerzen, cfg["atr_tage"])
    kurs = kurs or (kerzen[-1][4] if kerzen else None)
    hoechst = max([v[2] for v in verlauf[-1:]] + [kurs or 0]) if verlauf else kurs
    stop = verlauf[-1][3] if verlauf else None
    if stop is None and pyr["tranchen"]:
        stop = max(t.get("anfangsstop") or 0 for t in pyr["tranchen"]) or None
    stufe = len(pyr["tranchen"])
    marke = (max(t["index_kauf"] for t in pyr["tranchen"]) + cfg["nachkauf_atr"] * a) if (stufe and a) else None
    r = risiko(pyr, kurs, stop, eurusd) if stufe and kurs else None
    raus, gruende = ausstiegssignal(trend, kurs, stop, cfg) if stufe else (False, [])
    return {"stufe": stufe, "max_stufen": cfg["max_stufen"], "stop": stop, "hoechst": hoechst, "atr": a, "kurs": kurs,
            "nachkauf_marke": marke, "risiko": r, "ausstieg": raus, "ausstieg_gruende": gruende,
            "verlauf": verlauf, "einstellungen": cfg,
            "naechste_groesse": tranchen_anteil(stufe + 1, cfg) if stufe < cfg["max_stufen"] else None}
