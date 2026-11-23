"""Pyramidenmanager - Adapter zu den vorhandenen Analysewerkzeugen (nur lesen, nichts nachbauen).

Quellen (alle vom Kurs-Agenten im State-Repo, Branch app-state):
  state/markt/ohlc.json       Yahoo-Tageskerzen der Cash-Indizes (markt_daten.py) - Trend-Score, ATR, Gaps
  state/markt/sentiment.json  CNN Fear & Greed (US-weit), Krypto (markt_daten.py)
Werkzeuge:
  gap_analyzer.kerzen_pruefen / erkennen / mit_lage / statistik   (Gap Analyzer, unveraendert)
  fear_greed.karten                                               (Fear & Greed, unveraendert)
Zuordnung der vier Indizes: KO-Code (NDX, DAX, SPX, DJI) = Gap-Kurzname; Yahoo-Symbol; Fear-&-Greed-Karte.
Ein US-weiter Wert (CNN) wird nie als indexspezifischer Wert ausgegeben: er steht getrennt unter "us_umfeld"
und nur bei den drei US-Indizes."""
import datetime

import boersenkalender as BK
import fear_greed as FG
import gap_analyzer as G
import ko_rechner as KO
import pyramide as P

ZUORDNUNG = {  # KO-Code -> (Yahoo, Fear-&-Greed-Karte, US-Index?)
    "NDX": ("^NDX", "ndx", True), "DAX": ("^GDAXI", "dax", False),
    "SPX": ("^GSPC", "spx", True), "DJI": ("^DJI", "dji", True),
}
QUELLE_KERZEN = "Yahoo Finance, Cash-Index-Tageskerzen (Kurs-Agent, state/markt/ohlc.json)"


def handelstage_alt(boerse, letzte_iso, jetzt):
    """Wie viele ABGESCHLOSSENE Handelstage liegen nach dem Datum `letzte_iso`? 0 = aktuell."""
    try:
        letzte = datetime.date.fromisoformat(str(letzte_iso)[:10])
    except ValueError:
        return None
    heute = jetzt.astimezone(BK.BOERSEN[boerse]["tz"]).date()
    tage = BK.handelstage_zwischen(boerse, letzte + datetime.timedelta(days=1), heute)
    return sum(1 for d in tage if BK.kerze_vollstaendig(boerse, d, jetzt))


def _status(alter, cfg):
    if alter is None:
        return "fehlt"
    return "veraltet" if alter > cfg["max_alter_handelstage"] else "aktuell"


def _fg_eintrag(karte, bezug, boerse, jetzt, cfg):
    """Fear-&-Greed-Karte -> Eingabe fuer pyramide.fg_einstiegswert (mit eigener Alterspruefung in Handelstagen)."""
    if not karte or karte.get("wert") is None:
        return None
    zeit = karte.get("zeit")
    datum = zeit.date().isoformat() if isinstance(zeit, datetime.datetime) else str(zeit or "")[:10]
    alter = handelstage_alt(boerse, datum, jetzt) if datum else None
    # einheitlich in Handelstagen (das Werkzeug selbst rechnet in Stunden/Kalendertagen - steht als Info dabei)
    return {"wert": karte["wert"], "kategorie": karte.get("kategorie"), "status": _status(alter, cfg), "zeit": datum,
            "status_werkzeug": karte.get("status"),
            "alter_handelstage": alter, "quelle": karte.get("quelle") or "", "bezug": bezug,
            "karte": karte.get("id")}


def index_analyse(ohlc, sentiment, jetzt, eigene=None, cfg=None, definition="hl"):
    """Alle Analysewerte je Index -> {code: {...}}. eigene: vorberechnete Fear-&-Greed-Rohverlaeufe
    (fear_greed.eigene_verlaeufe; teuer, die App speichert sie je Datenstand zwischen)."""
    cfg = cfg or P.STANDARD
    idx = ((ohlc or {}).get("indizes") or {}) if isinstance(ohlc, dict) else {}
    try:
        karten = {k["id"]: k for k in FG.karten(sentiment, ohlc, jetzt, eigene)}
    except Exception:                    # Fear & Greed darf die Pyramide nie verhindern -> "fehlt"
        karten = {}
    aus = {}
    for code, (sym, fg_id, us) in ZUORDNUNG.items():
        info = KO.INDIZES[code]
        boerse = info["boerse"]
        e = idx.get(sym) or {}
        kerzen, probleme = G.kerzen_pruefen(e.get("kerzen"))
        fehlende = (e.get("pruefung") or {}).get("fehlende") or []
        letzte = kerzen[-1][0] if kerzen else None
        alter = handelstage_alt(boerse, letzte, jetzt) if letzte else None
        status = _status(alter, cfg) if kerzen else "fehlt"
        trend = P.trend_score(kerzen) if kerzen else None
        atr_wert = P.atr(kerzen, cfg["atr_tage"]) if kerzen else None
        kurs = kerzen[-1][4] if kerzen else None
        gaps = G.mit_lage(G.erkennen(kerzen, code, definition, fehlende, stand=(ohlc or {}).get("stand")), kurs) \
            if kerzen else []
        gap_daten = {"gaps": gaps, "statistik": G.statistik(gaps), "status": status if kerzen else "fehlt",
                     "stand": letzte, "definition": G.DEFINITIONEN[definition],
                     "ungeprueft": sum(1 for g in gaps if g["status"] != "geschlossen" and not g["vollstaendig"])}
        aus[code] = {
            "code": code, "name": info["name"], "yahoo": sym, "boerse": boerse, "kerzen": kerzen,
            "probleme": probleme, "fehlende": fehlende, "kurs": kurs, "letzte_kerze": letzte,
            "alter_handelstage": alter, "status": status, "quelle": QUELLE_KERZEN, "trend": trend, "atr": atr_wert,
            "gap_daten": gap_daten,
            "fg_index": _fg_eintrag(karten.get(fg_id), "index", boerse, jetzt, cfg),
            "us_umfeld": _fg_eintrag(karten.get("us"), "us", "NYSE", jetzt, cfg) if us else None,
        }
    return aus


def bewertung(a, cfg=None):
    """Bewertung eines Index aus index_analyse() -> Trend, ATR (Laenge aus cfg), Gap-Wert, F&G-Einstiegswert,
    kombiniert, Signal. cfg: Einstellungen der Pyramide (pyramide.cfg_fuer).
    Der Trend-Score einer veralteten Kerzenreihe zaehlt nicht (status "veraltet")."""
    cfg = cfg or P.STANDARD
    trend = a["trend"] if a["status"] == "aktuell" else None
    atr_wert = P.atr(a["kerzen"], cfg["atr_tage"]) if a["kerzen"] else None      # ATR-Laenge je Pyramide
    gap = P.gap_wert(a["gap_daten"], a["kurs"], atr_wert, cfg)
    fg = P.fg_einstiegswert(a["fg_index"], cfg)
    komb = P.kombiniert(trend, gap, fg, cfg)
    sig, gruende = P.einstiegssignal(trend, cfg)
    if a["status"] != "aktuell":
        gruende = [f"Tageskerzen {a['status']} (letzte Kerze {a['letzte_kerze'] or '–'})."] + gruende
    return {"trend": a["trend"], "trend_gilt": trend is not None, "atr": atr_wert, "atr_tage": cfg["atr_tage"],
            "gap": gap, "fg": fg, "kombiniert": komb,
            "einstieg": sig, "einstieg_gruende": gruende,
            "us_umfeld": P.fg_einstiegswert(a["us_umfeld"], cfg) if a.get("us_umfeld") else None}
