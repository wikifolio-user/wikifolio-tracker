"""Depot-Analyse & Optimierung: Rechenkern (ohne Streamlit, vollstaendig testbar).

Bewertet das echte Depot der App (Bestand, Kurse, Einstand kommen aus der Depot-Berechnung in app.py),
angereichert mit den Daten der Agenten:
  - Aktien: Qualitaets-Agent (state/qualitaet/details_*.json) - 100-Punkte-Score, KGV, PEG, Dividende,
    ROIC, Verschuldung, Wachstum, Land, Branche, Waehrung, Risiken, Staerken
  - ETFs/wikifolios: Top-500-Katalog (Kursentwicklung, Schwankung, Drawdown) und klassen_score
  - eigene Kurshistorie der Position (ls-tc.de) fuer Schwankung, Drawdown und Kursbewegungen
Was in diesen Quellen fehlt (TER, ETF-Zusammensetzung, Laender/Branchen von ETFs), wird NICHT geschaetzt:
es bleibt "unbekannt", bis der Nutzer es selbst eintraegt (Angaben je Position).

Alle Scores, Empfehlungen, Optimierungen und der Assistent sind regelbasiert und nachvollziehbar:
jede Aussage nennt die Kennzahl, auf der sie beruht. Prognosen sind als Modellrechnung gekennzeichnet.
"""
import copy
import math
import re

import branchen as BR
import dividenden as DV
import klassen_score as KS
import formate as FMT

ARTEN = {"aktie": "Aktie", "etf": "ETF", "wikifolio": "wikifolio", "fonds": "Fonds", "sonstiges": "Sonstiges",
         "cash": "Liquidität"}
EMPFEHLUNGEN = ["Aufstocken prüfen", "Halten", "Beobachten", "Reduzieren prüfen", "Verkauf prüfen"]
PRIO = {"hoch": 0, "mittel": 1, "niedrig": 2}

# Anlegerprofile: Zielstruktur je Klasse (% des Depots), tragbare Schwankung % p. a., Hoechstgewicht je Wert
PROFILE = {
    "defensiv":    {"titel": "Defensiv", "ziel": {"etf": 60, "aktie": 15, "wikifolio": 5, "cash": 20},
                    "vola": 8.0, "max_gewicht": 10.0},
    "ausgewogen":  {"titel": "Ausgewogen", "ziel": {"etf": 55, "aktie": 25, "wikifolio": 10, "cash": 10},
                    "vola": 13.0, "max_gewicht": 15.0},
    "wachstum":    {"titel": "Wachstum", "ziel": {"etf": 50, "aktie": 30, "wikifolio": 15, "cash": 5},
                    "vola": 18.0, "max_gewicht": 20.0},
    "offensiv":    {"titel": "Offensiv", "ziel": {"etf": 40, "aktie": 35, "wikifolio": 20, "cash": 5},
                    "vola": 25.0, "max_gewicht": 25.0},
}
STRATEGIEN = {"ausgewogen": "Ausgewogen", "wachstum": "Wachstum", "dividende": "Dividende"}
STANDARD_PROFIL = {"risiko": "ausgewogen", "strategie": "ausgewogen", "horizont": 10, "renditeziel": 6.0,
                   "sparrate": 0.0, "kapital": 0.0, "max_gewicht": None}
# Renditeerwartung/Schwankung der Klassen fuer Modellrechnungen (wie Investment-Scanner, scanner.ANNAHMEN)
ERWARTUNG = {"aktie": 7.0, "etf": 6.5, "wikifolio": 5.0, "fonds": 5.0, "sonstiges": 2.0, "cash": 2.0}
VOLA_ANNAHME = {"aktie": 32.0, "etf": 17.0, "wikifolio": 25.0, "fonds": 15.0, "sonstiges": 3.0, "cash": 0.5}
# Streuung innerhalb eines Werts (fuer die Diversifikation): breiter ETF ~ viele Titel, wikifolio ~ einige
STREUFAKTOR = {"aktie": 1.0, "etf": 10.0, "wikifolio": 3.0, "fonds": 6.0, "sonstiges": 1.0}
ETF_NAMEN = re.compile(r"(?i)\b(etf|ucits|ishares|xtrackers|vanguard|amundi|spdr|lyxor|invesco|wisdomtree|"
                       r"vaneck|l&g|hsbc msci|comstage|21shares|etc\b)")
INDEX_GRUPPEN = [("semiconductor", "Halbleiter"), ("halbleiter", "Halbleiter"),
                 ("information technology", "IT/Technologie"), ("technology", "IT/Technologie"),
                 ("nasdaq", "Nasdaq-100"), ("msci world", "MSCI World"), ("s&p 500", "S&P 500"),
                 ("sp 500", "S&P 500"), ("all-world", "FTSE All-World"), ("all world", "FTSE All-World"),
                 ("acwi", "MSCI ACWI"), ("emerging", "Schwellenländer"), ("stoxx 600", "Europa"),
                 ("msci europe", "Europa"), ("dax", "DAX"), ("gold", "Gold"), ("bitcoin", "Krypto")]
# Welche Index-Familien sich stark ueberschneiden (USA-Grosswerte stecken in allen Welt-Indizes)
UEBERSCHNEIDUNG = {
    frozenset({"MSCI World", "S&P 500"}): "rund 70 % des MSCI World sind US-Werte aus dem S&P 500",
    frozenset({"MSCI World", "FTSE All-World"}): "beide enthalten die Industrieländer fast vollständig",
    frozenset({"MSCI World", "MSCI ACWI"}): "der ACWI enthält den MSCI World vollständig",
    frozenset({"FTSE All-World", "S&P 500"}): "rund 60 % des All-World sind US-Werte aus dem S&P 500",
    frozenset({"MSCI ACWI", "S&P 500"}): "rund 60 % des ACWI sind US-Werte aus dem S&P 500",
    frozenset({"Nasdaq-100", "S&P 500"}): "fast alle Nasdaq-100-Werte stecken auch im S&P 500",
    frozenset({"Nasdaq-100", "IT/Technologie"}): "beide sind von denselben US-Technologiewerten geprägt",
    frozenset({"Nasdaq-100", "MSCI World"}): "die großen Nasdaq-Werte sind die größten MSCI-World-Positionen",
    frozenset({"IT/Technologie", "Halbleiter"}): "Halbleiter sind ein Kernteil der IT-Branche",
}
# Steuer Deutschland (Abgeltungsteuer)
ABGELTUNG = 0.25
SOLI = 0.055
TEILFREISTELLUNG_STANDARD = {"etf": 30.0, "fonds": 30.0, "aktie": 0.0, "wikifolio": 0.0, "sonstiges": 0.0}


# ============================================================ Hilfen
def _z(x, d=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return d
    return d if math.isnan(v) or math.isinf(v) else v


def de(x, nk=1):
    if x is None:
        return "–"
    s = f"{x:,.{nk}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def eur(x, nk=0, vz=False):
    return FMT.eur(x, nk, vz)


def pct(x, nk=1, vz=False):
    return FMT.pct(x, nk, vz)


def schluessel(p):
    """Stabiler Schluessel einer Position fuer gespeicherte Angaben/Varianten."""
    return str(p.get("isin") or p.get("wkn") or p.get("instrument_id") or p.get("name") or "").upper()


def art_erkennen(name, wkn="", ist_wikifolio=None, hinweis=None):
    """Anlageklasse aus Quelle/Name. hinweis: bekannte Klasse aus Agentendaten (hat Vorrang)."""
    if hinweis in ARTEN:
        return hinweis
    if ist_wikifolio or str(wkn or "").upper().startswith("LS9") or "wikifolio" in str(name).lower():
        return "wikifolio"
    if ETF_NAMEN.search(str(name or "")):
        return "etf"
    return "sonstiges"


def index_gruppe(name):
    n = str(name or "").lower()
    return next((g for k, g in INDEX_GRUPPEN if k in n), None)


KERN_INDIZES = {"MSCI World", "FTSE All-World", "MSCI ACWI"}          # selbst breit gestreut: Kernposition
BREITE_INDIZES = {"S&P 500", "Nasdaq-100", "Europa", "DAX", "Schwellenländer"}


def hoechstgewicht(p, mg):
    """Hoechstgewicht einer Position: Welt-ETF ohne Grenze (selbst gestreut), Laender-/Regionen-ETF doppelt,
    Branchen-ETF und Einzelwert einfach."""
    idx = p.get("index") if p.get("art") in ("etf", "fonds") else None
    if idx in KERN_INDIZES:
        return 100.0
    if idx in BREITE_INDIZES:
        return min(100.0, mg * 2)
    return mg


def klumpen_teiler(p):
    idx = p.get("index") if p.get("art") in ("etf", "fonds") else None
    return 10.0 if idx in KERN_INDIZES else 3.0 if idx in BREITE_INDIZES else 1.0


# ============================================================ Kennzahlen aus Kurshistorie
def historie_kennzahlen(reihe):
    """reihe: Tagesschlusskurse (pandas Series, Index Datum) -> Schwankung % p. a., max. Rueckgang %,
    Rueckgang vom Hoch %, Veraenderung 1 Woche/1 Monat/6 Monate/1 Jahr %, Jahre. None bei zu wenig Daten."""
    try:
        r = reihe.dropna()
        r = r[r > 0]
    except AttributeError:
        return None
    if len(r) < 20:
        return None
    werte = [float(x) for x in r.values]
    renditen = [werte[i] / werte[i - 1] - 1 for i in range(1, len(werte))]
    mittel = sum(renditen) / len(renditen)
    var = sum((x - mittel) ** 2 for x in renditen) / max(len(renditen) - 1, 1)
    hoch, mdd = werte[0], 0.0
    for w in werte:
        hoch = max(hoch, w)
        mdd = min(mdd, w / hoch - 1)
    tage = (r.index[-1] - r.index[0]).days

    def vor(t):
        stichtag = r.index[-1] - __import__("pandas").Timedelta(days=t)
        alt = r[r.index <= stichtag]
        if alt.empty or (stichtag - alt.index[-1]).days > 10:
            return None
        return (werte[-1] / float(alt.iloc[-1]) - 1) * 100

    return {"vola": math.sqrt(var) * math.sqrt(252) * 100, "maxdd": mdd * 100,
            "vom_hoch": (werte[-1] / max(werte) - 1) * 100, "w1": vor(7), "m1": vor(30), "m6": vor(182),
            "j1": vor(365), "jahre": tage / 365.25, "n": len(werte)}


# ============================================================ Anreichern
def marktdaten_index(aktien_zeilen, isin_zu_symbol=None, katalog_teile=None, kennung_je_symbol=None):
    """Nachschlage-Tabellen fuer die Anreicherung. Die Depotpositionen tragen WKN oder ISIN (Feld "wkn").
    aktien_zeilen: {symbol: Zeile aus state/qualitaet/alle_*.json}; isin_zu_symbol: {ISIN: Yahoo-Symbol}
    (state/top50_yahoo.json, Schluessel "isin"); katalog_teile: Top-500-Katalog (state/planer/katalog_gross_*,
    verbindet WKN und ISIN); kennung_je_symbol: {symbol: Kennung} (state/top50_alle_*)."""
    aktien_zeilen = aktien_zeilen or {}
    symbol_je = {}
    for isin, sym in (isin_zu_symbol or {}).items():
        if sym and sym in aktien_zeilen:
            symbol_je.setdefault(str(isin).upper(), sym)
    for sym, kenn in (kennung_je_symbol or {}).items():
        if kenn and sym in aktien_zeilen:
            symbol_je.setdefault(str(kenn).upper(), sym)
    katalog = {}
    for d in katalog_teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            w = dict(zip(felder, z))
            isin = str(w.get("isin") or "").upper()
            kenn = str(w.get("kennung") or "").upper()
            for k in (kenn, isin):
                if k:
                    katalog.setdefault(k, w)
            if kenn and isin in symbol_je:          # WKN -> ISIN -> Yahoo-Symbol
                symbol_je.setdefault(kenn, symbol_je[isin])
    return {"aktien": aktien_zeilen, "symbol_je": symbol_je, "katalog": katalog}


def anreichern(p, markt, angaben=None, detail_lader=None):
    """Position (aus der Depot-Berechnung) um Klasse, Fundamentaldaten, Risiko-Kennzahlen und Score
    ergaenzen. angaben: eigene Angaben des Nutzers fuer diese Position (TER, Land, Branche, Dividende,
    Klasse, Teilfreistellung). detail_lader(symbol, zeile) -> Detail-Datensatz (Qualitaets-Agent) oder None.
    -> neue Position (dict)"""
    p = dict(p)
    a = dict(angaben or {})
    kenn = [str(k).upper() for k in (p.get("isin"), p.get("wkn")) if k]
    sym = next((markt["symbol_je"][k] for k in kenn if k in markt["symbol_je"]), None)
    kat = next((markt["katalog"][k] for k in kenn if k in markt["katalog"]), None)
    zeile = markt["aktien"].get(sym) if sym else None
    hinweis = "aktie" if zeile else (kat.get("typ") if kat else None)
    p["art"] = a.get("art") or art_erkennen(p.get("name"), p.get("wkn"), p.get("ist_wikifolio"), hinweis)
    p["symbol"] = sym
    p["fund"] = None
    if zeile and p["art"] == "aktie":
        det = detail_lader(sym, zeile) if detail_lader else None
        p["fund"] = dict(zeile, **(det or {}))
    p["katalog"] = kat
    f = p["fund"] or {}
    hk = historie_kennzahlen(p.get("hist")) if p.get("hist") is not None else None
    p["hk"] = hk
    # Stammdaten: eigene Angabe > Agentendaten > unbekannt
    p["land"] = a.get("land") or f.get("land") or ("Strategie (wikifolio)" if p["art"] == "wikifolio" else None)
    p["branche"] = a.get("branche") or (BR.branche_de(f["br"]) if f.get("br") else None)
    p["sektor"] = a.get("sektor") or (BR.sektor(f["br"]) if f.get("br") else None)
    p["waehrung"] = a.get("waehrung") or f.get("kwae") or ("EUR" if p["art"] in ("wikifolio", "etf") else None)
    p["ter"] = _z(a.get("ter"))
    div = _z(a.get("div"))
    p["div_quelle"] = "eigene Angabe" if div is not None else None
    if div is None and f.get("div") is not None:
        div, p["div_quelle"] = _z(f.get("div")), "Qualitäts-Agent (Yahoo Finance)"
    if div is None and kat and _z(kat.get("div")) is not None and p["art"] != "wikifolio":
        div, p["div_quelle"] = _z(kat.get("div")), "Top-500-Katalog"
    if div is None and p["art"] == "wikifolio":
        div, p["div_quelle"] = 0.0, "wikifolios schütten nicht aus"
    p["div"] = div
    p["teilfreistellung"] = _z(a.get("tfs"), TEILFREISTELLUNG_STANDARD.get(p["art"], 0.0))
    # Risiko: eigene Kurshistorie > Agentendaten
    p["vola"] = (hk or {}).get("vola") or _z(f.get("vola")) or (_z(kat.get("vola")) if kat else None)
    mdd = (hk or {}).get("maxdd")
    if mdd is None:
        mdd = _z(f.get("dd")) if f else (_z(kat.get("maxdd")) if kat else None)
    p["maxdd"] = -abs(mdd) if mdd is not None else None
    p["index"] = index_gruppe(p.get("name")) if p["art"] in ("etf", "fonds") else None
    p.update(position_score(p))
    return p


# Teilwerte des Qualitaets-Scores (Punkte, Hoechstwert) - wie die Watchlist (app.py Q_BEREICHE)
Q_BEREICHE = [("qualitaet", "Unternehmensqualität", 20), ("wachstum", "Wachstum & Reinvestment", 15),
              ("fcf", "Free Cashflow & Gewinnqualität", 15), ("bilanz", "Bilanzqualität", 10),
              ("management", "Management & Kapitalallokation", 10), ("moat", "Wettbewerbsvorteil", 10),
              ("bewertung", "Bewertung", 15), ("chance", "Chance-Risiko / Margin of Safety", 5)]


def score_teile_lesbar(p):
    """[(Bezeichnung, Punkte, Hoechstpunkte)] fuer die Anzeige."""
    teile = p.get("score_teile") or {}
    if p.get("art") == "aktie":
        return [(n, _z(teile.get(k_)), m) for k_, n, m in Q_BEREICHE if k_ in teile]
    ks_art = "wikifolio" if p.get("art") == "wikifolio" else "etf"
    return [(n, _z(teile.get(k_)), 100) for k_, n, _, _, _ in KS.KRITERIEN[ks_art] if k_ in teile]


def position_score(p):
    """Score 0-100 mit Quelle und Teilwerten.
    Aktie: Qualitaets-Score des Agenten (100-Punkte-Schema: Qualitaet, Wachstum, Free Cashflow, Bilanz,
    Management, Burggraben, Bewertung, Chance-Risiko, abzueglich Red Flags).
    ETF/wikifolio: klassen_score (Kurshistorie, eigene Kriterien je Klasse) aus dem Top-500-Katalog, sonst
    aus der eigenen Kurshistorie der Position (kuerzer, als solche gekennzeichnet)."""
    f = p.get("fund")
    if p["art"] == "aktie" and f and _z(f.get("gesamt")) is not None:
        teile = f.get("p") or {}
        return {"score": float(f["gesamt"]), "score_quelle": "Qualitäts-Score (Geschäftszahlen, 100-Punkte-Schema)",
                "score_teile": {k: v for k, v in teile.items()}}
    if p["art"] in ("etf", "wikifolio", "fonds"):
        ks_art = "wikifolio" if p["art"] == "wikifolio" else "etf"
        kat = p.get("katalog")
        if kat:
            b = KS.bewerte(kat, ks_art)
            if b.get("score") is not None:
                return {"score": b["score"], "score_quelle": f"{'wikifolio' if ks_art == 'wikifolio' else 'ETF'}-Score "
                        "(Top-500-Kurshistorie)", "score_teile": b["teile"], "score_hinweise": b.get("hinweise", [])}
        hk = p.get("hk")
        if hk and hk.get("j1") is not None:
            ersatz = {"name": p.get("name"), "1J": hk["j1"], "vola": hk["vola"], "maxdd": hk["maxdd"],
                      "jahre": hk["jahre"]}
            b = KS.bewerte(ersatz, ks_art)
            if b.get("score") is not None:
                return {"score": b["score"], "score_quelle": "aus der eigenen Kurshistorie (nur 1 Jahr – vorläufig)",
                        "score_teile": b["teile"], "score_hinweise": b.get("hinweise", [])}
    if p["art"] == "aktie":
        return {"score": None, "score_teile": {},
                "score_quelle": "nicht im Datenbestand des Qualitäts-Agenten – keine Geschäftszahlen"}
    return {"score": None, "score_quelle": "keine ausreichenden Daten", "score_teile": {}}


# ============================================================ Profil / Zielstruktur
def profil_bereinigen(pr):
    p = dict(STANDARD_PROFIL)
    p.update({k: v for k, v in (pr or {}).items() if k in STANDARD_PROFIL})
    if p["risiko"] not in PROFILE:
        p["risiko"] = "ausgewogen"
    if p["strategie"] not in STRATEGIEN:
        p["strategie"] = "ausgewogen"
    for k in ("horizont", "renditeziel", "sparrate", "kapital"):
        p[k] = max(0.0, _z(p[k], STANDARD_PROFIL[k]) or 0.0)
    mg = _z(p.get("max_gewicht"))
    p["max_gewicht"] = mg if mg and 1 <= mg <= 100 else None
    return p


def zielstruktur(profil):
    """Zielanteile je Klasse (% des Depots) aus Risiko, Horizont und Strategie + Begruendung."""
    pr = profil_bereinigen(profil)
    basis = PROFILE[pr["risiko"]]
    ziel = dict(basis["ziel"])
    gruende = [f"Risikobereitschaft „{basis['titel']}“: {', '.join(f'{ARTEN[k]} {v} %' for k, v in basis['ziel'].items())}"]
    if pr["horizont"] < 3:
        um = min(15, ziel["aktie"] + ziel["wikifolio"])
        ziel["cash"] += um
        ab_a = min(ziel["aktie"], round(um * 0.6))
        ziel["aktie"] -= ab_a
        ziel["wikifolio"] -= um - ab_a
        gruende.append(f"Anlagehorizont unter 3 Jahren: {um} Prozentpunkte mehr Liquidität")
    elif pr["horizont"] >= 15 and ziel["cash"] > 5:
        ziel["etf"] += ziel["cash"] - 5
        gruende.append("Anlagehorizont ab 15 Jahren: Liquidität auf 5 % begrenzt, Rest in breite ETFs")
        ziel["cash"] = 5
    if pr["strategie"] == "dividende":
        gruende.append("Dividendenstrategie: innerhalb der Klassen werden Werte mit nachhaltiger Ausschüttung "
                       "(Rendite und Ausschüttungsquote) bevorzugt")
    elif pr["strategie"] == "wachstum":
        gruende.append("Wachstumsstrategie: innerhalb der Klassen werden Werte mit hohem Score und Wachstum bevorzugt")
    mg = pr["max_gewicht"] or basis["max_gewicht"]
    return {"ziel": ziel, "max_gewicht": mg, "vola": basis["vola"], "gruende": gruende, "profil": pr}


# ============================================================ Gesamtdepot
def _wert(p):
    return max(_z(p.get("wert"), 0.0) or 0.0, 0.0)


def kennzahlen(positionen, cash=0.0, profil=None):
    """Depotkennzahlen und Depot-Score (0-100) mit Teilwerten. Positionen ohne Kurs (ohne_kurs) zaehlen nicht."""
    zs = zielstruktur(profil)
    bewertbar = [p for p in positionen if not p.get("ohne_kurs") and _wert(p) > 0]
    cash = max(_z(cash, 0.0) or 0.0, 0.0)
    investiert = sum(_wert(p) for p in bewertbar)
    gesamt = investiert + cash
    # Gewinn/Rendite nur ueber Positionen mit bekanntem Einstand (sonst zaehlte ihr Wert als Gewinn)
    mit_einstand = [p for p in bewertbar if _z(p.get("einstand")) is not None]
    einstand = sum(_z(p.get("einstand")) for p in mit_einstand)
    ausgezahlt = sum(_z(p.get("ausgezahlt"), 0.0) or 0.0 for p in mit_einstand)
    wert_mit = sum(_wert(p) for p in mit_einstand)
    k = {"gesamt": gesamt, "investiert": investiert, "cash": cash, "einstand": einstand, "ausgezahlt": ausgezahlt,
         "gv": wert_mit + ausgezahlt - einstand if einstand else None,
         "rendite": ((wert_mit + ausgezahlt) / einstand - 1) * 100 if einstand else None,
         "einstand_abdeckung": (wert_mit / investiert * 100) if investiert else 0.0,
         "anzahl": len(bewertbar), "ohne_kurs": [p for p in positionen if p.get("ohne_kurs")]}
    if gesamt <= 0:
        k.update(score=None, teile={}, gewichte={}, verteilung={}, groesste=None, eff_n=0.0, vola=None,
                 dividende=None, div_abdeckung=0.0, kosten=None, kosten_abdeckung=0.0, risiko="–",
                 ziel=zs, abweichung={})
        return k
    gew = {schluessel(p): _wert(p) / gesamt * 100 for p in bewertbar}
    k["gewichte"] = gew
    # Verteilungen (inkl. Liquiditaet)

    def verteil(feld, standard="unbekannt"):
        v = {}
        for p in bewertbar:
            x = p.get(feld) or standard
            v[x] = v.get(x, 0.0) + gew[schluessel(p)]
        if cash > 0:
            v["Liquidität"] = v.get("Liquidität", 0.0) + cash / gesamt * 100
        return dict(sorted(v.items(), key=lambda kv: -kv[1]))

    klassen = {}
    for p in bewertbar:
        klassen[p["art"]] = klassen.get(p["art"], 0.0) + gew[schluessel(p)]
    klassen["cash"] = cash / gesamt * 100
    k["verteilung"] = {"Anlageklasse": {ARTEN.get(a, a): v for a, v in sorted(klassen.items(), key=lambda kv: -kv[1])
                                        if v > 0},
                       "Sektor": verteil("sektor"), "Branche": verteil("branche"), "Land": verteil("land"),
                       "Währung": verteil("waehrung")}
    k["klassen"] = klassen
    gr = max(bewertbar, key=_wert) if bewertbar else None
    k["groesste"] = (gr["name"], gew[schluessel(gr)]) if gr else None
    # effektive Anzahl Positionen (Streuung innerhalb ETF/wikifolio als Naeherung beruecksichtigt)
    hhi = sum((gew[schluessel(p)] / 100) ** 2 / STREUFAKTOR.get(p["art"], 1.0) for p in bewertbar)
    hhi += (cash / gesamt) ** 2
    k["eff_n"] = 1 / hhi if hhi > 0 else 0.0
    # Klumpen: groesstes "Einzelrisiko" (breiter ETF zaehlt nur zu einem Drittel)
    klumpen = max(((gew[schluessel(p)] / klumpen_teiler(p), p["name"])
                   for p in bewertbar), default=(0.0, None))
    k["klumpen"] = klumpen
    # Schwankung des Depots: Kovarianz mit den Korrelationsannahmen der Klassen
    k["vola"] = depot_vola(bewertbar, gew, cash / gesamt * 100)
    mdd = [(gew[schluessel(p)], p["maxdd"]) for p in bewertbar if p.get("maxdd") is not None]
    k["maxdd_gewichtet"] = (sum(w * d for w, d in mdd) / sum(w for w, _ in mdd)) if mdd else None
    # Dividende / Kosten (nur bekannte Werte, Abdeckung ausgewiesen)
    div_bek = [p for p in bewertbar if p.get("div") is not None]
    k["dividende"] = sum(_wert(p) * p["div"] / 100 for p in div_bek) if div_bek else None
    k["div_abdeckung"] = sum(gew[schluessel(p)] for p in div_bek) / max(sum(gew.values()), 1e-9) * 100
    ter_bek = [p for p in bewertbar if p.get("ter") is not None]
    fonds = [p for p in bewertbar if p["art"] in ("etf", "fonds", "wikifolio")]
    k["kosten"] = sum(_wert(p) * p["ter"] / 100 for p in ter_bek) if ter_bek else None
    k["kosten_abdeckung"] = (sum(_wert(p) for p in ter_bek if p in fonds) / sum(_wert(p) for p in fonds) * 100
                             if fonds else 100.0)
    k["ter_schnitt"] = (sum(_wert(p) * p["ter"] for p in ter_bek) / sum(_wert(p) for p in ter_bek)
                        if ter_bek else None)
    # Abweichung von der Zielstruktur
    k["ziel"] = zs
    k["abweichung"] = {a: klassen.get(a, 0.0) - zs["ziel"].get(a, 0.0)
                       for a in set(zs["ziel"]) | set(klassen) if a in ("etf", "aktie", "wikifolio", "cash")}
    k["ueberschneidungen"] = ueberschneidungen(bewertbar, gew)
    k["uebergewichtig"] = [(p["name"], gew[schluessel(p)], hoechstgewicht(p, zs["max_gewicht"])) for p in bewertbar
                           if gew[schluessel(p)] > hoechstgewicht(p, zs["max_gewicht"])]
    k.update(depot_score(k, bewertbar, gew))
    v = k["vola"]
    k["risiko"] = ("–" if v is None else "niedrig" if v < 8 else "mittel" if v < 15 else "hoch" if v < 22
                   else "sehr hoch")
    return k


def depot_vola(bewertbar, gew, cash_anteil):
    """Schwankung % p. a. des Depots aus den Einzelschwankungen und den Korrelationsannahmen je Klasse
    (wie Investment-Scanner). Fehlende Einzelschwankung -> Annahme der Klasse (gekennzeichnet)."""
    korr = {("aktie", "aktie"): 0.45, ("etf", "etf"): 0.80, ("wikifolio", "wikifolio"): 0.45,
            ("aktie", "etf"): 0.70, ("aktie", "wikifolio"): 0.55, ("etf", "wikifolio"): 0.60}
    teile = [(gew[schluessel(p)] / 100, (p.get("vola") or VOLA_ANNAHME.get(p["art"], 20.0)) / 100,
              p["art"] if p["art"] in ("aktie", "etf", "wikifolio") else "etf") for p in bewertbar]
    if not teile:
        return None
    var = 0.0
    for i, (wi, si, ai) in enumerate(teile):
        for j, (wj, sj, aj) in enumerate(teile):
            rho = 1.0 if i == j else korr.get((ai, aj)) or korr.get((aj, ai)) or 0.6
            var += wi * wj * si * sj * rho
    return math.sqrt(max(var, 0.0)) * 100


def ueberschneidungen(bewertbar, gew):
    """ETF-Ueberschneidungen ueber die Index-Familie im Namen (die Zusammensetzung selbst liegt nicht vor)."""
    etfs = [p for p in bewertbar if p.get("index")]
    aus = []
    for i, a in enumerate(etfs):
        for b in etfs[i + 1:]:
            if a["index"] == b["index"]:
                grund = f"beide bilden {a['index']} ab – nahezu identische Titel"
            else:
                grund = UEBERSCHNEIDUNG.get(frozenset({a["index"], b["index"]}))
            if grund:
                aus.append({"a": a["name"], "b": b["name"], "grund": grund,
                            "gewicht": gew[schluessel(a)] + gew[schluessel(b)],
                            "stark": a["index"] == b["index"]})
    return sorted(aus, key=lambda u: (-u["stark"], -u["gewicht"]))


def _linear(x, schlecht, gut):
    if x is None:
        return None
    return max(0.0, min(1.0, (x - schlecht) / (gut - schlecht))) * 100


SCORE_GEWICHTE = [("qualitaet", "Qualität der Positionen", 30), ("diversifikation", "Diversifikation", 25),
                  ("klumpen", "Klumpenrisiko", 20), ("risiko", "Risiko passend zum Profil", 15),
                  ("kosten", "Laufende Kosten", 5), ("ziel", "Nähe zur Zielstruktur", 5)]


def depot_score(k, bewertbar, gew):
    """Depot-Score 0-100: gewichteter Durchschnitt der Teilwerte (fehlende Teilwerte zaehlen nicht)."""
    zs = k["ziel"]
    mit = [(gew[schluessel(p)], p["score"]) for p in bewertbar if p.get("score") is not None]
    t = {"qualitaet": (sum(w * s for w, s in mit) / sum(w for w, _ in mit)) if mit else None,
         "diversifikation": _linear(k["eff_n"], 1.0, 12.0),
         "klumpen": _linear(k["klumpen"][0], 40.0, zs["max_gewicht"]),
         "risiko": (100.0 if k["vola"] is not None and k["vola"] <= zs["vola"] else
                    _linear(k["vola"], zs["vola"] * 2, zs["vola"])),
         "kosten": _linear(k.get("ter_schnitt"), 1.5, 0.2) if k.get("kosten_abdeckung", 0) >= 50 else None,
         "ziel": _linear(sum(abs(v) for v in k["abweichung"].values()) / 2, 50.0, 0.0)}
    summe = sum(g for key, _, g in SCORE_GEWICHTE if t[key] is not None)
    score = (sum(g * t[key] for key, _, g in SCORE_GEWICHTE if t[key] is not None) / summe) if summe else None
    q_abdeckung = sum(w for w, _ in mit) / max(sum(gew.values()), 1e-9) * 100
    return {"score": round(score, 1) if score is not None else None, "teile": t,
            "score_abdeckung": q_abdeckung}


# ============================================================ Empfehlungen je Position
def bewertungsaussage(p):
    """Ueber-/Unterbewertung nur, wo Daten das tragen (Aktien). -> (text, richtung -1/0/1 oder None)"""
    f = p.get("fund") or {}
    if p["art"] != "aktie" or not f:
        return ("keine Bewertungsaussage möglich (ETF/wikifolio: kein Gewinn je Anteil)"
                if p["art"] in ("etf", "wikifolio", "fonds") else "keine Bewertungsdaten", None)
    teile = []
    richtung = 0
    bew = f.get("bew")
    if bew:
        teile.append(f"Bewertung laut Qualitäts-Agent: {bew}")
        richtung = {"günstig": 1, "fair": 0, "teuer": -1}.get(bew, 0)
    kgv, h = _z(f.get("kgv")), _z(f.get("h_kgv"))
    if kgv and h:
        teile.append(f"KGV {de(kgv)} gegenüber {de(h)} im historischen Mittel")
        if kgv > h * 1.25:
            richtung = min(richtung, -1) if richtung <= 0 else 0
        elif kgv < h * 0.8:
            richtung = max(richtung, 1) if richtung >= 0 else 0
    if _z(f.get("mos")) is not None:
        teile.append(f"Sicherheitsmarge {pct(_z(f.get('mos')), 0, True)} (Reverse-DCF)")
    if _z(f.get("peg")) is not None:
        teile.append(f"PEG {de(_z(f.get('peg')), 2)}")
    return ("; ".join(teile) or "keine Bewertungsdaten", richtung)


def empfehlung(p, k, profil=None):
    """Kategorie, Prioritaet, Horizont und Begruendung (Fakten mit Zahlen, Chancen, Risiken) je Position."""
    zs = k["ziel"]
    mg = hoechstgewicht(p, zs["max_gewicht"])
    g = k["gewichte"].get(schluessel(p), 0.0)
    s = p.get("score")
    f = p.get("fund") or {}
    hk = p.get("hk") or {}
    gruende, chancen, risiken = [], [], []
    if s is not None:
        gruende.append(f"Score {de(s, 0)}/100 – {p['score_quelle']}")
    else:
        gruende.append("Kein Score: für diesen Wert liegen keine ausreichenden Daten vor")
    gruende.append(f"Depotgewicht {pct(g)} (Höchstgewicht laut Profil {pct(mg, 0)})" if mg < 100 else
                   f"Depotgewicht {pct(g)} (Welt-ETF: als breit gestreute Kernposition ohne Höchstgewicht)")
    bew_txt, richtung = bewertungsaussage(p)
    if p["art"] == "aktie":
        gruende.append(bew_txt)
    if hk.get("vom_hoch") is not None:
        gruende.append(f"Kurs {pct(hk['vom_hoch'], 0)} unter dem Hoch der Kurshistorie")
    if p.get("vola") is not None:
        gruende.append(f"Schwankung {pct(p['vola'], 0)} p. a.")
    chancen += list(f.get("staerken") or [])[:2] + list(f.get("kat") or [])[:2]
    risiken += list(f.get("risiken") or [])[:2] + [fl[0] for fl in (f.get("flags") or [])[:2]]
    risiken += list(p.get("score_hinweise") or [])[:2]
    if p.get("maxdd") is not None and p["maxdd"] <= -40:
        risiken.append(f"großer maximaler Rückgang ({pct(p['maxdd'], 0)})")
    if p["art"] == "wikifolio":
        risiken.append("Emittentenrisiko (Zertifikat) und Abhängigkeit vom Trader")
    if p["art"] in ("etf", "fonds") and p.get("ter") is None:
        risiken.append("laufende Kosten (TER) unbekannt – bitte unter „Angaben“ eintragen")
    # Regeln (in dieser Reihenfolge); anlass = der ausschlaggebende Grund
    if s is None:
        kat, prio = "Beobachten", "niedrig"
        anlass = "Ohne Score keine fundierte Empfehlung – Daten ergänzen oder Wert beobachten"
        gruende.append(anlass)
    elif s < 35 and (richtung == -1 or f.get("klasse") == "nicht" or (p.get("maxdd") or 0) <= -50):
        kat, prio = "Verkauf prüfen", "hoch"
        anlass = f"Score {de(s, 0)}/100 und " + ("teure Bewertung" if richtung == -1 else
                                                  "Einstufung „nicht weiterverfolgen“" if f.get("klasse") == "nicht"
                                                  else f"maximaler Rückgang {pct(p.get('maxdd'), 0)}")
    elif g > mg * 1.5:
        kat, prio = "Reduzieren prüfen", "hoch"
        anlass = (f"Klumpenrisiko: {pct(g)} des Depots, {de(g - mg)} Prozentpunkte über dem Höchstgewicht "
                  f"von {pct(mg, 0)}")
        gruende.append(anlass)
    elif s < 45:
        kat, prio = ("Reduzieren prüfen", "mittel") if g > 5 else ("Beobachten", "mittel")
        anlass = f"schwacher Score {de(s, 0)}/100 bei {pct(g)} Gewicht"
    elif g > mg:
        kat, prio = "Reduzieren prüfen", "mittel"
        anlass = f"Gewicht {pct(g)} über dem Höchstgewicht deines Profils ({pct(mg, 0)})"
        gruende.append(anlass)
    elif s >= 70 and g < mg * 0.6 and richtung != -1:
        kat, prio = "Aufstocken prüfen", "mittel" if s >= 80 else "niedrig"
        anlass = f"starker Score {de(s, 0)}/100 bei nur {pct(g)} Gewicht"
    elif richtung == -1 and s < 60:
        kat, prio = "Beobachten", "mittel"
        anlass = "eher teuer bewertet bei mittlerem Score"
        gruende.append(anlass)
    else:
        kat, prio = "Halten", "niedrig"
        anlass = f"Score {de(s, 0)}/100 und Gewicht {pct(g)} im Rahmen"
    horizont = {"etf": "langfristig (5+ Jahre)", "aktie": "mittel- bis langfristig (3–10 Jahre)",
                "wikifolio": "mittelfristig – Strategie regelmäßig prüfen", "fonds": "langfristig (5+ Jahre)"}.get(
        p["art"], "offen")
    return {"kategorie": kat, "prio": prio, "horizont": horizont, "gruende": gruende, "anlass": anlass,
            "chancen": [c for c in chancen if c][:4], "risiken": [r for r in risiken if r][:4],
            "bewertung": bew_txt, "bewertung_richtung": richtung}


# ============================================================ Warnungen / Ueberwachung
def warnungen(positionen, k, vorher=None):
    """Nur relevante Hinweise. vorher: gespeicherter Stand der letzten Analyse {schluessel: {score, div, gewicht},
    "_vola": ...} fuer Veraenderungen. -> [{typ, text, stufe, schluessel}]"""
    aus = []
    mg = k["ziel"]["max_gewicht"]
    for p in positionen:
        if p.get("ohne_kurs"):
            continue
        sk = schluessel(p)
        g = k["gewichte"].get(sk, 0.0)
        hk = p.get("hk") or {}
        mg_p = hoechstgewicht(p, mg)
        if g > mg_p:
            aus.append({"typ": "Übergewicht", "stufe": "hoch" if g > mg_p * 1.5 else "mittel", "schluessel": sk,
                        "text": f"{p['name']}: {pct(g)} des Depots – über deinem Höchstgewicht von {pct(mg_p, 0)}"})
        tag = None
        if _z(p.get("kurs")) and _z(p.get("vortag")):
            tag = (p["kurs"] / p["vortag"] - 1) * 100
        if tag is not None and abs(tag) >= 5:
            aus.append({"typ": "Kursbewegung", "stufe": "mittel", "schluessel": sk,
                        "text": f"{p['name']}: {pct(tag, 1, True)} gegenüber dem Vortag"})
        elif hk.get("w1") is not None and abs(hk["w1"]) >= 10:
            aus.append({"typ": "Kursbewegung", "stufe": "mittel", "schluessel": sk,
                        "text": f"{p['name']}: {pct(hk['w1'], 1, True)} in einer Woche"})
        if hk.get("vom_hoch") is not None and hk["vom_hoch"] <= -20:
            aus.append({"typ": "Rückgang", "stufe": "mittel", "schluessel": sk,
                        "text": f"{p['name']}: {pct(hk['vom_hoch'], 0)} unter dem Hoch der Kurshistorie"})
        alt = (vorher or {}).get(sk) or {}
        if alt.get("score") is not None and p.get("score") is not None and p["score"] - alt["score"] <= -10:
            aus.append({"typ": "Fundamentale Veränderung", "stufe": "hoch", "schluessel": sk,
                        "text": f"{p['name']}: Score von {de(alt['score'], 0)} auf {de(p['score'], 0)} gefallen"})
        if alt.get("div") and p.get("div") is not None and abs(p["div"] - alt["div"]) / alt["div"] >= 0.2:
            aus.append({"typ": "Dividende", "stufe": "mittel", "schluessel": sk,
                        "text": f"{p['name']}: Dividendenrendite von {pct(alt['div'])} auf {pct(p['div'])} verändert"})
    for a, d in (k.get("abweichung") or {}).items():
        if a == "cash" and not k.get("cash"):
            continue                        # Liquiditaet nicht angegeben (die App kennt das Konto nicht)
        if abs(d) >= 10:
            ist = (k.get("klassen") or {}).get(a, 0.0)
            aus.append({"typ": "Zielallokation", "stufe": "mittel", "schluessel": f"ziel:{a}",
                        "text": f"{ARTEN[a]}: {pct(ist, 0)} statt Ziel {pct(k['ziel']['ziel'].get(a, 0), 0)} "
                                f"({pct(d, 0, True)})"})
    v_alt = (vorher or {}).get("_vola")
    if v_alt is not None and k.get("vola") is not None and k["vola"] - v_alt >= 3:
        aus.append({"typ": "Risiko steigt", "stufe": "mittel", "schluessel": "depot:vola",
                    "text": f"Depotschwankung von {pct(v_alt)} auf {pct(k['vola'])} gestiegen"})
    for u in k.get("ueberschneidungen") or []:
        if u["stark"]:
            aus.append({"typ": "Überschneidung", "stufe": "mittel", "schluessel": f"ueb:{u['a']}|{u['b']}",
                        "text": f"{u['a']} und {u['b']}: {u['grund']}"})
    return sorted(aus, key=lambda w: PRIO.get(w["stufe"], 2))


def stand_merken(positionen, k):
    """Schnappschuss fuer die naechste Ueberwachung."""
    st = {schluessel(p): {"score": p.get("score"), "div": p.get("div"),
                          "gewicht": k["gewichte"].get(schluessel(p))} for p in positionen if not p.get("ohne_kurs")}
    st["_vola"] = k.get("vola")
    st["_score"] = k.get("score")
    return st


# ============================================================ Gesamtanalyse (7 Fragen + Aktionsplan)
def gesamtanalyse(positionen, k, empf, warn):
    """Antworten auf die sieben Fragen und priorisierter Aktionsplan. Fakten/Einschaetzungen getrennt."""
    pos = [p for p in positionen if not p.get("ohne_kurs")]
    mit_score = sorted([p for p in pos if p.get("score") is not None], key=lambda p: -p["score"])
    s = k.get("score")
    urteil = ("–" if s is None else "sehr gut" if s >= 80 else "gut" if s >= 65 else "solide mit Schwächen"
              if s >= 50 else "verbesserungsbedürftig")
    t = k.get("teile") or {}
    schwach = sorted([(v, n) for key, n, _ in SCORE_GEWICHTE if (v := t.get(key)) is not None])[:2]
    antworten = []
    antworten.append(("Wie gut ist mein Depot aktuell aufgestellt?",
                      f"Depot-Score {de(s, 0)}/100 – {urteil}. Schwächste Bereiche: "
                      + ", ".join(f"{n} ({de(v, 0)} Punkte)" for v, n in schwach) + "." if s is not None else
                      "Noch keine Bewertung möglich (keine Positionen mit Kurs)."))
    stark = [p for p in mit_score if p["score"] >= 70][:3]
    antworten.append(("Welche Werte sind besonders stark?",
                      "; ".join(f"{p['name']} ({de(p['score'], 0)} Punkte)" for p in stark)
                      or "Kein Wert erreicht 70 Punkte."))
    prob = [p for p in pos if empf[schluessel(p)]["kategorie"] in ("Verkauf prüfen", "Reduzieren prüfen")]
    antworten.append(("Welche Positionen sind problematisch?",
                      "; ".join(f"{p['name']}: {empf[schluessel(p)]['kategorie']} "
                                f"({empf[schluessel(p)]['anlass']})" for p in prob)
                      or "Keine Position fällt durch Score oder Gewicht negativ auf."))
    ueber = [p for p in pos if empf[schluessel(p)]["bewertung_richtung"] == -1]
    unter = [p for p in pos if empf[schluessel(p)]["bewertung_richtung"] == 1]
    antworten.append(("Welche Investments könnten über- oder unterbewertet sein?",
                      ("Eher teuer: " + ", ".join(p["name"].rstrip(".") for p in ueber) + ". " if ueber else "")
                      + ("Eher günstig: " + ", ".join(p["name"].rstrip(".") for p in unter) + ". " if unter else "")
                      + "Bewertungsaussagen gibt es nur für Aktien mit Daten des Qualitäts-Agenten; für ETFs "
                        "und wikifolios ist keine Bewertung (KGV) möglich."))
    risk = [w["text"] for w in warn if w["typ"] in ("Übergewicht", "Überschneidung", "Rückgang")][:4]
    if k.get("vola") is not None and k["vola"] > k["ziel"]["vola"]:
        risk.insert(0, f"Depotschwankung {pct(k['vola'])} p. a. liegt über dem tragbaren Wert deines Profils "
                       f"({pct(k['ziel']['vola'], 0)})")
    antworten.append(("Wo bestehen unnötige Risiken?", "; ".join(risk) or "Keine auffälligen Risiken gefunden."))
    plan = aktionsplan(pos, k, empf)
    antworten.append(("Welche Anpassungen könnten sinnvoll sein?",
                      "; ".join(a["massnahme"] for a in plan[:4]) or "Keine Anpassung nötig."))
    antworten.append(("Welche Maßnahmen sind besonders wichtig?",
                      "; ".join(a["massnahme"] for a in plan if a["prio"] == "hoch")
                      or "Keine dringenden Maßnahmen – Depot regelmäßig überprüfen."))
    return {"antworten": antworten, "aktionsplan": plan, "urteil": urteil}


def aktionsplan(pos, k, empf):
    plan = []
    for p in pos:
        e = empf[schluessel(p)]
        if e["kategorie"] in ("Verkauf prüfen", "Reduzieren prüfen", "Aufstocken prüfen"):
            plan.append({"prio": e["prio"], "massnahme": f"{p['name']}: {e['kategorie']}", "warum": e["anlass"]})
    for a, d in (k.get("abweichung") or {}).items():
        if a == "cash" and not k.get("cash"):
            continue
        if abs(d) >= 10:
            plan.append({"prio": "mittel", "massnahme": f"{ARTEN[a]} {'abbauen' if d > 0 else 'aufbauen'} "
                         f"({pct(abs(d), 0)} Abweichung zur Zielstruktur)",
                         "warum": "Zielstruktur aus Risiko, Horizont und Strategie"})
    for u in (k.get("ueberschneidungen") or [])[:2]:
        if u["stark"]:
            plan.append({"prio": "mittel", "massnahme": f"Überschneidung {u['a']} / {u['b']} zusammenlegen prüfen",
                         "warum": u["grund"]})
    if (k.get("kosten_abdeckung") or 100) < 100:
        plan.append({"prio": "niedrig", "massnahme": "TER der ETFs/Fonds eintragen", "warum":
                     "ohne laufende Kosten kann der Kostenvergleich nicht vollständig rechnen"})
    return sorted(plan, key=lambda a: PRIO[a["prio"]])


# ============================================================ Simulator
def simulieren(ist, aenderungen, cash=0.0, zusatz=0.0, gebuehr_fix=0.0, gebuehr_pct=0.0, steuer=None):
    """Virtuelle Umschichtung - das echte Depot wird NIE veraendert.
    ist: angereicherte Positionen; aenderungen: {schluessel: neue Stueckzahl}; neue Werte stehen als
    Positionen mit "neu": True und stueck in ist/aenderungen (siehe neue_position).
    -> {"soll": Positionen, "trades": [...], "cash_nachher", "gebuehren", "steuern", "warnungen"}"""
    soll, trades = [], []
    gebuehren = 0.0
    liquiditaet = max(_z(cash, 0.0) or 0.0, 0.0) + max(_z(zusatz, 0.0) or 0.0, 0.0)
    for p in ist:
        q = dict(p)
        sk = schluessel(p)
        alt = _z(p.get("stueck"), 0.0) or 0.0
        neu = max(_z(aenderungen.get(sk), alt), 0.0)
        kurs = _z(p.get("kurs"))
        if p.get("ohne_kurs") or not kurs:
            soll.append(q)
            continue
        delta = neu - alt
        if abs(delta) > 1e-9:
            betrag = abs(delta) * kurs
            geb = gebuehr_fix + betrag * gebuehr_pct / 100
            gebuehren += geb
            t = {"schluessel": sk, "name": p["name"], "art": p["art"], "aktion": "Kauf" if delta > 0 else "Verkauf",
                 "stueck": abs(delta), "kurs": kurs, "betrag": betrag, "gebuehr": geb,
                 "neu": bool(p.get("neu")), "gewinn": None}
            if delta < 0:
                liquiditaet += betrag - geb
                einstand_je = (_z(p.get("einstand")) / alt if alt and _z(p.get("einstand")) is not None
                               else None)                # unbekannter Einstand -> Gewinn unbekannt
                t["gewinn"] = (kurs - einstand_je) * abs(delta) - geb if einstand_je is not None else None
                t["teilfreistellung"] = p.get("teilfreistellung", 0.0)
                anteil = neu / alt if alt else 0.0
                q["einstand"] = (_z(p.get("einstand"), 0.0) or 0.0) * anteil
            else:
                liquiditaet -= betrag + geb
                q["einstand"] = (_z(p.get("einstand"), 0.0) or 0.0) + betrag + geb
            trades.append(t)
        q["stueck"] = neu
        q["wert"] = neu * kurs
        if neu <= 1e-9:
            q["verkauft"] = True
        soll.append(q)
    st_erg = steuern(trades, steuer)
    liquiditaet -= st_erg["steuer"]
    warn = []
    if liquiditaet < -0.5:
        warn.append(f"Die Käufe übersteigen die verfügbare Liquidität um {eur(-liquiditaet)} – "
                    "zusätzliches Kapital eintragen oder weniger kaufen.")
    soll = [q for q in soll if not q.get("verkauft") or q.get("ohne_kurs")]
    return {"soll": soll, "trades": trades, "cash_nachher": liquiditaet, "gebuehren": gebuehren,
            "steuern": st_erg, "warnungen": warn}


def steuern(trades, angaben=None):
    """Geschaetzte Steuer Deutschland auf realisierte Gewinne der simulierten Verkaeufe.
    angaben: freibetrag (verbleibender Sparerpauschbetrag), verlust_aktien, verlust_sonstige (Verlusttoepfe),
    kirchensteuer (0, 8 oder 9 %). Einstand je Stueck = Durchschnitt (die App kennt keine einzelnen Kaeufe,
    FIFO ist daher nicht abbildbar). Nicht beruecksichtigt: Vorabpauschale, Altbestand vor 2009, Quellensteuer."""
    a = {"freibetrag": 0.0, "verlust_aktien": 0.0, "verlust_sonstige": 0.0, "kirchensteuer": 0.0}
    a.update({k: max(_z(v, 0.0) or 0.0, 0.0) for k, v in (angaben or {}).items() if k in a})
    luecken = ["Einstand je Stück als Durchschnitt (keine Einzelkäufe/FIFO)",
               "Vorabpauschale, Altbestand vor 2009 und Quellensteuer nicht berücksichtigt"]
    aktien_g = sonst_g = roh = 0.0
    unbekannt = 0
    for t in trades:
        if t["aktion"] != "Verkauf":
            continue
        if t.get("gewinn") is None:
            unbekannt += 1
            continue
        roh += t["gewinn"]
        g = t["gewinn"] * (1 - (t.get("teilfreistellung") or 0.0) / 100) if t["gewinn"] > 0 else t["gewinn"]
        if t["art"] == "aktie":
            aktien_g += g
        else:
            sonst_g += g
    if unbekannt:
        luecken.append(f"{unbekannt} Verkauf/Verkäufe ohne Einstand – Gewinn unbekannt, nicht versteuert")
    # Aktienverluste nur mit Aktiengewinnen; uebrige Verluste mit allem
    aktien_rest = aktien_g - a["verlust_aktien"]
    if aktien_rest < 0:
        aktien_rest = 0.0 if aktien_g >= 0 else aktien_g
    sonst_rest = sonst_g - a["verlust_sonstige"]
    if aktien_rest > 0 and sonst_rest < 0:
        verrechnet = min(aktien_rest, -sonst_rest)
        aktien_rest -= verrechnet
        sonst_rest += verrechnet
    steuerbar = max(aktien_rest, 0.0) + max(sonst_rest, 0.0)
    nach_freibetrag = max(steuerbar - a["freibetrag"], 0.0)
    k = a["kirchensteuer"] / 100
    kest = nach_freibetrag * ABGELTUNG / (1 + ABGELTUNG * k) if k else nach_freibetrag * ABGELTUNG
    steuer = kest * (1 + SOLI + k)
    return {"realisiert": roh, "nach_tfs": aktien_g + sonst_g, "steuerbar": steuerbar, "nach_freibetrag": nach_freibetrag,
            "steuer": steuer, "kest": kest, "luecken": luecken, "angaben": a,
            "teilfreistellung_hinweis": "ETFs/Fonds mit 30 % Teilfreistellung (Aktienfonds) angenommen – "
                                        "je Position unter „Angaben“ änderbar"}


def neue_position(name, art, kurs, stueck, isin="", wkn="", instrument_id=None, angaben=None, markt=None):
    """Neuer (virtueller) Wert fuer den Simulator - Kurs muss aus einer echten Quelle kommen."""
    p = {"name": name, "isin": isin, "wkn": wkn, "instrument_id": instrument_id, "kurs": float(kurs),
         "stueck": 0.0, "wert": 0.0, "einstand": 0.0, "neu": True, "hist": None}
    p = anreichern(p, markt or {"aktien": {}, "symbol_je": {}, "katalog": {}}, dict(angaben or {}, art=art)
                   if art else angaben)
    p["ziel_stueck"] = float(stueck)
    return p


def stueck_fuer_zielgewichte(positionen, ziel_pct, gesamtwert, ganze=True):
    """{schluessel: Ziel-%} -> {schluessel: Stueckzahl} (abgerundet auf ganze Stuecke, sofern ganze)."""
    aus = {}
    for p in positionen:
        sk = schluessel(p)
        if sk not in ziel_pct or not _z(p.get("kurs")):
            continue
        st = gesamtwert * ziel_pct[sk] / 100 / p["kurs"]
        aus[sk] = math.floor(st + 1e-9) if ganze else st
    return aus


# ============================================================ Vorher/Nachher
VERGLEICH = [  # (Kennzahl, Feld/Funktion, hoeher_ist_besser, Format)
    ("Depotwert", "gesamt", None, "eur"),
    ("Depot-Score", "score", True, "pkt"),
    ("Risiko (Schwankung p. a.)", "vola", False, "pct"),
    ("Diversifikation (effektive Positionen)", "eff_n", True, "zahl"),
    ("Größte Einzelposition", "groesste", False, "gross"),
    ("Branchenverteilung (größte Branche)", "branche", False, "vert"),
    ("Ländergewichtung (größtes Land)", "land", False, "vert"),
    ("Dividendenprognose p. a.", "dividende", None, "eur"),
    ("Laufende Kosten p. a.", "kosten", False, "eur"),
    ("Liquidität", "cash", None, "eur"),
]


def _wert_vergleich(k, feld):
    if feld == "groesste":
        return k["groesste"][1] if k.get("groesste") else None
    if feld in ("branche", "land"):
        v = {n: x for n, x in ((k.get("verteilung") or {}).get("Branche" if feld == "branche" else "Land") or {}).items()
             if n not in ("unbekannt", "Liquidität")}
        return max(v.values()) if v else None
    return k.get(feld)


def _label_vergleich(k, feld):
    if feld == "groesste" and k.get("groesste"):
        return k["groesste"][0]
    if feld in ("branche", "land"):
        v = {n: x for n, x in ((k.get("verteilung") or {}).get("Branche" if feld == "branche" else "Land") or {}).items()
             if n not in ("unbekannt", "Liquidität")}
        return max(v, key=v.get) if v else "unbekannt"
    return ""


def vergleich(vorher, nachher):
    """Vorher/Nachher-Tabelle: [{kennzahl, vorher, nachher, diff, diff_pct, urteil (besser/schlechter/neutral),
    vorher_label, nachher_label, format}]"""
    zeilen = []
    for name, feld, hoeher_besser, fmt_ in VERGLEICH:
        a, b = _wert_vergleich(vorher, feld), _wert_vergleich(nachher, feld)
        diff = (b - a) if a is not None and b is not None else None
        dpct = (diff / abs(a) * 100) if diff is not None and a not in (0, None) and fmt_ in ("eur", "zahl") else None
        urteil = "neutral"
        schwelle = {"pkt": 1.0, "pct": 0.3, "zahl": 0.3, "gross": 1.0, "vert": 1.0, "eur": 1.0}[fmt_]
        if diff is not None and hoeher_besser is not None and abs(diff) >= schwelle:
            urteil = "besser" if (diff > 0) == hoeher_besser else "schlechter"
        zeilen.append({"kennzahl": name, "feld": feld, "vorher": a, "nachher": b, "diff": diff, "diff_pct": dpct,
                       "urteil": urteil, "format": fmt_, "vorher_label": _label_vergleich(vorher, feld),
                       "nachher_label": _label_vergleich(nachher, feld)})
    return zeilen


def simulation_bewerten(vorher, nachher, sim, profil=None, alternative=None):
    """KI-Bewertung (regelbasiert) der simulierten Aenderungen: 7 Fragen + Gesamturteil mit Kennzahlen."""
    def d(feld):
        a, b = _wert_vergleich(vorher, feld), _wert_vergleich(nachher, feld)
        return (a, b, (b - a) if a is not None and b is not None else None)

    aus = []
    a, b, x = d("eff_n")
    aus.append(("Verbessert die Umschichtung die Diversifikation?",
                f"{'Ja' if (x or 0) > 0.3 else 'Nein' if (x or 0) < -0.3 else 'Kaum verändert'}: effektive Positionen "
                f"{de(a)} → {de(b)}."))
    a, b, x = d("groesste")
    (ka, na), (kb, nb) = vorher.get("klumpen", (0, None)), nachher.get("klumpen", (0, None))
    aus.append(("Sinkt oder steigt das Konzentrationsrisiko?",
                f"{'Sinkt' if kb < ka - 1 else 'Steigt' if kb > ka + 1 else 'Bleibt etwa gleich'}: größtes "
                f"Einzelrisiko {pct(ka)} ({na}) → {pct(kb)} ({nb}); größte Position {pct(a)} → {pct(b)}. "
                "Breite ETFs zählen dabei als gestreut (Welt-ETF zu einem Zehntel, Länder-ETF zu einem Drittel)."))
    ka, kb = vorher.get("kosten"), nachher.get("kosten")
    da, db = vorher.get("dividende"), nachher.get("dividende")
    aus.append(("Verändern sich laufende Kosten und Dividenden?",
                ("Laufende Kosten unbekannt (keine TER eingetragen)" if ka is None and kb is None else
                 f"Laufende Kosten {eur(ka)} → {eur(kb)} p. a.")
                + ("" if (nachher.get("kosten_abdeckung") or 0) >= 100 else " (TER nicht für alle Werte bekannt)")
                + f"; Dividendenprognose {eur(da)} → {eur(db)} p. a."
                + f" Einmalig: Ordergebühren {eur(sim['gebuehren'], 2)}, geschätzte Steuern "
                  f"{eur(sim['steuern']['steuer'], 2)}."))
    sa, sb = vorher.get("score"), nachher.get("score")
    za = sum(abs(v) for v in (vorher.get("abweichung") or {}).values()) / 2
    zb = sum(abs(v) for v in (nachher.get("abweichung") or {}).values()) / 2
    aus.append(("Passt das neue Depot besser zu meinen Anlagezielen?",
                f"Abweichung von der Zielstruktur {pct(za, 0)} → {pct(zb, 0)}; Depotschwankung "
                f"{pct(vorher.get('vola'))} → {pct(nachher.get('vola'))} (tragbar laut Profil "
                f"{pct(nachher['ziel']['vola'], 0)})."))
    neue_r = []
    if (nachher.get("vola") or 0) > (vorher.get("vola") or 0) + 1:
        neue_r.append(f"höhere Schwankung ({pct(nachher['vola'])})")
    vorher_ueber = {n for n, _, _ in vorher.get("uebergewichtig") or []}
    for n, g, hg in nachher.get("uebergewichtig") or []:
        if n not in vorher_ueber:
            neue_r.append(f"{n} mit {pct(g)} über dem Höchstgewicht von {pct(hg, 0)}")
    neue_r += list(sim.get("warnungen") or [])
    if sim["cash_nachher"] > 0.25 * max(nachher.get("gesamt") or 1, 1):
        neue_r.append(f"hoher Liquiditätsanteil ({eur(sim['cash_nachher'])}) – Inflationsrisiko")
    aus.append(("Entstehen neue Risiken?", "; ".join(neue_r) or "Keine neuen Risiken erkennbar."))
    ta, tb = vorher.get("teile") or {}, nachher.get("teile") or {}
    besser_t = [n for key, n, _ in SCORE_GEWICHTE if ta.get(key) is not None and tb.get(key) is not None
                and tb[key] - ta[key] >= 3]
    schlechter_t = [n for key, n, _ in SCORE_GEWICHTE if ta.get(key) is not None and tb.get(key) is not None
                    and ta[key] - tb[key] >= 3]
    aus.append(("Werden bestehende Schwachstellen reduziert?",
                ("Verbessert: " + ", ".join(besser_t) + ". " if besser_t else "")
                + ("Verschlechtert: " + ", ".join(schlechter_t) + "." if schlechter_t else "")
                or "Die Teilbewertungen ändern sich kaum."))
    if alternative and alternative.get("score") is not None and sb is not None and alternative["score"] > sb + 2:
        alt_txt = (f"Ja: Der Vorschlag „Mein Depot optimieren“ erreicht {de(alternative['score'], 0)} Punkte "
                   f"(simuliert {de(sb, 0)}).")
    else:
        alt_txt = "Keine deutlich bessere Alternative aus den vorhandenen Werten gefunden."
    aus.append(("Gibt es eine sinnvollere Alternative?", alt_txt))
    if sa is None or sb is None:
        urteil = "ähnlich"
    elif sb >= sa + 3:
        urteil = "besser"
    elif sb <= sa - 3:
        urteil = "schlechter"
    else:
        urteil = "ähnlich"
    fazit = (f"Die simulierte Depotstruktur ist im Vergleich zum aktuellen Depot {urteil} auf deine angegebenen "
             f"Anlageziele abgestimmt (Depot-Score {de(sa, 0)} → {de(sb, 0)}).")
    return {"antworten": aus, "urteil": urteil, "fazit": fazit}


# ============================================================ Optimierung / Szenarien
def optimieren(positionen, k, profil=None, strategie=None, schwelle=2.0):
    """Zielgewichte fuer die VORHANDENEN Werte (keine neuen Kaeufe ausserhalb des Depots), passend zu
    Zielstruktur, Hoechstgewicht und Score. Kleine Abweichungen (< schwelle Prozentpunkte) bleiben, um
    unnoetige Transaktionen zu vermeiden. Gerechnet werden zwei Varianten (volle Umschichtung, nur
    Klumpen abbauen); vorgeschlagen wird nur, was den Depot-Score tatsaechlich verbessert.
    -> {"ziel_pct", "stueck", "massnahmen", "fehlende_klassen", "ziel", "score_vorher", "score_nachher"}"""
    pr_eff = dict(profil or {}, **({"strategie": strategie} if strategie else {}))
    beste = None
    for nur_kappen in (False, True):
        v = _optimieren_variante(positionen, k, pr_eff, schwelle, nur_kappen)
        if not v["massnahmen"]:
            continue
        sim = simulieren(positionen, v["stueck"], cash=k["cash"])
        v["score_nachher"] = kennzahlen(sim["soll"], sim["cash_nachher"], pr_eff).get("score")
        if v["score_nachher"] is not None and (beste is None or v["score_nachher"] > beste["score_nachher"]):
            beste = v
    leer = _optimieren_variante(positionen, k, pr_eff, schwelle, True)
    if beste is None or k.get("score") is None or beste["score_nachher"] <= k["score"] + 0.5:
        leer.update(massnahmen=[], stueck={schluessel(p): _z(p.get("stueck"), 0.0) for p in positionen},
                    score_nachher=k.get("score"))
        beste = leer
    beste["score_vorher"] = k.get("score")
    beste["fehlende_klassen"] = _optimieren_variante(positionen, k, pr_eff, schwelle, False)["fehlende_klassen"]
    return beste


def _optimieren_variante(positionen, k, profil, schwelle, nur_kappen):
    zs = zielstruktur(profil)
    pr = zs["profil"]
    mg = zs["max_gewicht"]
    pos = [p for p in positionen if not p.get("ohne_kurs") and _z(p.get("kurs")) and _wert(p) > 0]
    gesamt = k["gesamt"]
    if gesamt <= 0 or not pos:
        return {"ziel_pct": {}, "stueck": {}, "massnahmen": [], "fehlende_klassen": [], "ziel": zs}
    ist = {schluessel(p): k["gewichte"].get(schluessel(p), 0.0) for p in pos}

    def faktor(p):
        s = p.get("score")
        if s is None or nur_kappen:
            return 1.0
        vorlaeufig = "vorläufig" in str(p.get("score_quelle"))
        if s < 35:
            return 0.5 if vorlaeufig else 0.0
        f = max(0.5, min(1.5, s / 60))
        if pr["strategie"] == "dividende" and p.get("div") is not None:
            q = _z((p.get("fund") or {}).get("div_q"))
            nachhaltig = q is None or q <= 80
            f *= 1 + min(p["div"], 6) / 6 * (1.0 if nachhaltig else 0.3)
        if pr["strategie"] == "wachstum":
            g = _z((p.get("fund") or {}).get("g_ums"))
            if g is not None:
                f *= 1 + max(min(g, 30), 0) / 60
            elif (p.get("hk") or {}).get("j1") is not None:
                f *= 1 + max(min(p["hk"]["j1"], 30), 0) / 90
        return f

    def klasse(p):
        return p["art"] if p["art"] in ("etf", "aktie", "wikifolio") else "etf"

    ziel_pct, fehlend = {}, []
    klassen_ziel = dict(zs["ziel"])
    if nur_kappen:  # Klassenanteile wie heute, nur das Hoechstgewicht wird durchgesetzt
        klassen_ziel = {a: sum(ist[schluessel(p)] for p in pos if klasse(p) == a) for a in ("etf", "aktie", "wikifolio")}
        klassen_ziel["cash"] = (k["cash"] / gesamt * 100) if gesamt else 0.0
    # Klassen ohne Bestand: Budget anteilig auf die vorhandenen Klassen (neue Werte kauft nur der Nutzer selbst)
    vorhanden = {klasse(p) for p in pos}
    frei_budget = sum(v for a, v in klassen_ziel.items() if a not in vorhanden and a != "cash")
    fehlend = [a for a in ("etf", "aktie", "wikifolio") if a not in vorhanden and klassen_ziel.get(a, 0) > 0]
    basis = sum(klassen_ziel.get(a, 0) for a in vorhanden)
    for a in vorhanden:
        klassen_ziel[a] = klassen_ziel.get(a, 0) + (frei_budget * klassen_ziel.get(a, 0) / basis if basis
                                                    else frei_budget / len(vorhanden))
    for a in fehlend:
        klassen_ziel[a] = 0.0
    for art in ("etf", "aktie", "wikifolio"):
        gruppe = [p for p in pos if klasse(p) == art]
        if not gruppe:
            continue
        roh = {schluessel(p): ist[schluessel(p)] * faktor(p) for p in gruppe}
        summe = sum(roh.values())
        if summe <= 0:
            klassen_ziel["cash"] = klassen_ziel.get("cash", 0) + klassen_ziel.get(art, 0)
            for p in gruppe:
                ziel_pct[schluessel(p)] = 0.0
            continue
        budget = klassen_ziel.get(art, 0)
        anteile = {sk: budget * v / summe for sk, v in roh.items()}
        # Hoechstgewicht einhalten, Ueberschuss auf die anderen Werte der Klasse verteilen (breite ETFs: doppelt)
        for _ in range(10):
            ueber = 0.0
            frei = {}
            for p in gruppe:
                sk = schluessel(p)
                cap = hoechstgewicht(p, mg)
                if p.get("score") is not None and p["score"] < 45:
                    cap = min(cap, ist[sk])  # schwache Werte nie aufstocken
                if anteile[sk] > cap:
                    ueber += anteile[sk] - cap
                    anteile[sk] = cap
                elif roh[sk] > 0:
                    frei[sk] = cap - anteile[sk]
            if ueber <= 1e-6 or not frei:
                klassen_ziel["cash"] = klassen_ziel.get("cash", 0) + ueber
                break
            platz = sum(frei.values())
            for sk, f_ in frei.items():
                anteile[sk] += ueber * f_ / platz if platz else 0
        ziel_pct.update(anteile)
    # kleine Abweichungen behalten (weniger Transaktionen)
    for sk in list(ziel_pct):
        if abs(ziel_pct[sk] - ist[sk]) < schwelle and ziel_pct[sk] > 0:
            ziel_pct[sk] = ist[sk]
    stueck, massn = {}, []
    for p in pos:
        sk = schluessel(p)
        alt = _z(p.get("stueck"), 0.0) or 0.0
        neu_roh = gesamt * ziel_pct.get(sk, ist[sk]) / 100 / p["kurs"]
        delta = neu_roh - alt
        if ziel_pct.get(sk, ist[sk]) == ist[sk]:
            stueck[sk] = alt
            continue
        # ganze Stuecke handeln, Bruchstuecke (z. B. aus dem Sparplan) bleiben unangetastet
        d_ganz = math.floor(abs(delta)) * (1 if delta > 0 else -1)
        if ziel_pct.get(sk) == 0:
            d_ganz = -alt
        if d_ganz == 0:
            stueck[sk] = alt
            continue
        stueck[sk] = alt + d_ganz
        s = p.get("score")
        if ziel_pct.get(sk) == 0:
            grund = f"Score {de(s, 0)} unter 35 – fundamental schwächster Wert im Depot"
        elif ist[sk] > hoechstgewicht(p, mg) and ziel_pct[sk] < ist[sk]:
            grund = (f"Gewicht {pct(ist[sk])} über dem Höchstgewicht {pct(hoechstgewicht(p, mg), 0)} – "
                     "Klumpenrisiko senken")
        elif d_ganz > 0:
            grund = (f"Score {de(s, 0)}" if s is not None else "Klassenziel") + \
                f" – Klasse {ARTEN[p['art']]} unter Ziel {pct(klassen_ziel.get(p['art'], 0), 0)}"
        else:
            grund = f"Klasse {ARTEN.get(p['art'], p['art'])} über Ziel – anteilig reduzieren"
        risiko = ("senkt Konzentrations- und Einzelwertrisiko" if d_ganz < 0 else
                  "erhöht das Gewicht dieses Werts – Einzelwertrisiko beachten")
        massn.append({"schluessel": sk, "name": p["name"], "aktion": "Kaufen" if d_ganz > 0 else "Verkaufen",
                      "stueck": abs(d_ganz), "betrag": abs(d_ganz) * p["kurs"], "ist_pct": ist[sk],
                      "ziel_pct": ziel_pct.get(sk, ist[sk]), "grund": grund, "risiko": risiko})
    massn.sort(key=lambda m: -m["betrag"])
    return {"ziel_pct": ziel_pct, "stueck": stueck, "massnahmen": massn, "fehlende_klassen": fehlend, "ziel": zs}


SZENARIEN = {
    "defensiv": {"titel": "Defensiv", "text": "Schwerpunkt auf Risikobegrenzung und Stabilität",
                 "profil": {"risiko": "defensiv", "strategie": "ausgewogen"}},
    "ausgewogen": {"titel": "Ausgewogen", "text": "Ausgeglichenes Verhältnis zwischen Wachstum und Risiko",
                   "profil": {"risiko": "ausgewogen", "strategie": "ausgewogen"}},
    "wachstum": {"titel": "Wachstumsorientiert", "text": "Größere Gewichtung langfristiger Wachstumschancen",
                 "profil": {"risiko": "wachstum", "strategie": "wachstum"}},
    "dividende": {"titel": "Dividendenorientiert", "text": "Schwerpunkt auf nachhaltigen Ausschüttungen",
                  "profil": {"risiko": "ausgewogen", "strategie": "dividende"}},
}


def modell_entwicklung(k, jahre=10, sparrate=0.0):
    """Modellrechnung (keine Prognose): erwartete Rendite aus den Klassenannahmen, Spanne aus der
    Depotschwankung (10-/50-/90-%-Quantil, lognormal). -> {mu, p10, p50, p90}"""
    gesamt = k.get("gesamt") or 0
    if gesamt <= 0:
        return None
    kl = k.get("klassen") or {}
    mu = sum(kl.get(a, 0) * ERWARTUNG.get(a, 2.0) for a in kl) / max(sum(kl.values()), 1e-9) / 100
    sigma = (k.get("vola") or 0) / 100
    n = max(int(jahre), 1)
    einzahlung = sparrate * 12 * n
    basis = gesamt * (1 + mu) ** n + (sparrate * 12 * (((1 + mu) ** n - 1) / mu) if mu else einzahlung)
    z = 1.2816
    log_sd = sigma * math.sqrt(n)
    return {"mu": mu * 100, "p50": basis, "p10": basis * math.exp(-z * log_sd), "p90": basis * math.exp(z * log_sd),
            "jahre": n, "eingezahlt": gesamt + einzahlung}


# ============================================================ Top-500-Bewertungen (Ranglisten, Alternativen)
EINORDNUNG = {"prio": "Hohe Analysepriorität", "beobachten": "Beobachtungsliste", "nicht": "Nicht weiterverfolgen"}


def ranglisten(aktien_zeilen, isin_zu_symbol, katalog_teile, n=None):
    """Bewertete Top-500-Werte je Klasse, nach Score sortiert: Aktien nach dem Qualitaets-Score des Agenten,
    ETFs/wikifolios nach klassen_score. -> {"aktie": [...], "etf": [...], "wikifolio": [...]} mit
    {name, art, kennung, isin, score, einordnung, staerken, schwaechen, div, bew, branche}"""
    isin_je = {}
    for isin, sym in (isin_zu_symbol or {}).items():
        if sym:
            isin_je.setdefault(sym, str(isin).upper())
    aktien = []
    for sym, z in (aktien_zeilen or {}).items():
        sc = _z(z.get("gesamt"))
        if sc is None:
            continue
        st_, sw_ = [], []
        if z.get("moat") in ("stark", "breit"):
            st_.append(f"Burggraben {z['moat']}")
        if _z(z.get("roic")) is not None and z["roic"] >= 15:
            st_.append(f"ROIC {de(z['roic'], 0)} %")
        if _z(z.get("g_ums")) is not None and z["g_ums"] >= 10:
            st_.append(f"Umsatzwachstum {de(z['g_ums'], 0)} % p. a.")
        if z.get("bew") == "teuer":
            sw_.append("Bewertung teuer")
        if z.get("risiko") == "hoch":
            sw_.append("Risiko hoch")
        aktien.append({"name": str(z.get("name") or sym), "art": "aktie", "symbol": sym, "kennung": sym,
                       "isin": isin_je.get(sym, ""), "score": sc, "einordnung": z.get("klasse"),
                       "staerken": st_[:3], "schwaechen": sw_[:3], "div": _z(z.get("div")), "bew": z.get("bew"),
                       "branche": z.get("br"), "div_q": _z(z.get("div_q")), "risiko": z.get("risiko"),
                       "g_ums": _z(z.get("g_ums")), "moat": z.get("moat")})
    aktien.sort(key=lambda e: (-e["score"], e["name"].lower()))
    aus = {"aktie": aktien[:n]}
    for art in ("etf", "wikifolio"):
        liste = []
        for e in KS.rangliste(katalog_teile, art)[:n]:
            b = e["bewertung"]
            st_, sw_ = KS.staerken_schwaechen(b, art)
            liste.append({"name": e["name"], "art": art, "kennung": e["kennung"], "isin": e["isin"],
                          "score": b["score"], "einordnung": b.get("einordnung"), "staerken": st_,
                          "schwaechen": sw_, "div": None, "bew": None, "branche": None})
        aus[art] = liste
    return aus


def _im_depot(e, positionen):
    kenn = {str(x).upper() for p in positionen for x in (p.get("isin"), p.get("wkn"), p.get("symbol")) if x}
    namen = {str(p.get("name") or "").lower() for p in positionen}
    return bool({str(e.get("isin") or "").upper(), str(e.get("kennung") or "").upper()} & kenn) \
        or e["name"].lower() in namen


def alternativen(rang, art, positionen, n=5, strategie=None, mindest=None):
    """Bestbewertete Top-500-Werte einer Klasse, die nicht im Depot sind. mindest: nur Werte mit hoeherem Score.
    Dividendenstrategie: unter den gut bewerteten (Score >= 60) die hoechste Dividendenrendite zuerst."""
    liste = [e for e in (rang or {}).get(art) or [] if not _im_depot(e, positionen)
             and e.get("einordnung") != "nicht" and (mindest is None or e["score"] > mindest)]
    if strategie == "dividende" and art == "aktie":
        liste = sorted([e for e in liste if e["score"] >= 60 and e.get("div")], key=lambda e: -(e["div"] or 0))
    return liste[:n]


# Aktienauswahl je Szenario: (Bedingung, Sortierschluessel, Begruendung)
SZENARIO_AKTIEN = {
    "defensiv": (lambda e: e.get("risiko") == "niedrig" and e.get("bew") != "teuer",
                 lambda e: -e["score"],
                 "niedriges Risiko, keine teure Bewertung"),
    "ausgewogen": (lambda e: e.get("risiko") in ("niedrig", "mittel"),
                   lambda e: -e["score"],
                   "höchster Qualitäts-Score bei niedrigem bis mittlerem Risiko"),
    "wachstum": (lambda e: e["score"] >= 75 and (e.get("g_ums") or 0) >= 15,
                 lambda e: -(e["score"] + min(e.get("g_ums") or 0, 60) / 2),
                 "Umsatzwachstum ab 15 % p. a. bei Qualitäts-Score ab 75 – Score und Wachstum gemeinsam gewichtet"),
    "dividende": (lambda e: 3 <= (e.get("div") or 0) <= 8 and e.get("risiko") != "hoch"
                  and DV.nachhaltigkeit(e.get("div"), e.get("div_q")) in ("nachhaltig", "solide"),
                  lambda e: -(e["score"] + 2 * (e.get("div") or 0)),
                  "Dividende 3–8 %, vom Gewinn gedeckt (Ausschüttungsquote ≤ 80 %), ohne hohes Risiko – "
                  "Qualität und Rendite gemeinsam gewichtet"),
}


def szenario_aktien(rang, szenario, positionen, n=5, mindest=60, je_sektor=1):
    """Aktien der Top-500-Rangliste, die zum Szenario passen und noch nicht im Depot sind.
    Nur Werte mit Score >= mindest und nicht 'Nicht weiterverfolgen'; hoechstens je_sektor Werte je Sektor
    (Streuung). 'individuell' nutzt die Strategie des Profils. -> (liste, begruendung)"""
    if szenario not in SZENARIO_AKTIEN:
        szenario = "ausgewogen"
    bed, sort, grund = SZENARIO_AKTIEN[szenario]
    liste = sorted([e for e in (rang or {}).get("aktie") or [] if e["score"] >= mindest
                    and e.get("einordnung") != "nicht" and not _im_depot(e, positionen) and bed(e)], key=sort)
    aus, je = [], {}
    for e in liste:
        sek = BR.sektor(e.get("branche"))
        if je.get(sek, 0) >= je_sektor:
            continue
        je[sek] = je.get(sek, 0) + 1
        aus.append(dict(e, sektor=sek))
        if len(aus) >= n:
            break
    return aus, grund


def _text_alternative(e):
    teile = [f"Score {de(e['score'], 0)}/100", EINORDNUNG.get(e.get("einordnung"), "")]
    if e.get("div"):
        teile.append(f"Dividende {pct(e['div'])}")
    if e.get("staerken"):
        teile.append("Stärken: " + ", ".join(e["staerken"]))
    if e.get("schwaechen"):
        teile.append("Schwächen: " + ", ".join(e["schwaechen"]))
    return f"• {e['name']} ({ARTEN[e['art']]}" + (f", {e['isin'] or e['kennung']}" if e.get("isin") or
                                                    e.get("kennung") else "") + "): " + " · ".join(x for x in teile if x)


def wert_finden(frage, positionen, rang):
    """Position oder Top-500-Wert, der in der Frage genannt wird (laengster passender Name zuerst)."""
    f = (frage or "").lower()
    kandidaten = [("pos", p, str(p.get("name") or "")) for p in positionen]
    for art in ("aktie", "etf", "wikifolio"):
        kandidaten += [("rang", e, e["name"]) for e in (rang or {}).get(art) or []]
    treffer = []
    for typ, obj, name in kandidaten:
        n = name.lower()
        kurz = re.split(r"[\s,.(]+", n)[0] if n else ""
        kenn = [str(obj.get(x) or "").lower() for x in ("isin", "wkn", "kennung")]
        if (n and n in f) or any(k_ and len(k_) >= 5 and k_ in f for k_ in kenn) or \
                (typ == "pos" and len(kurz) >= 5 and re.search(rf"\b{re.escape(kurz)}\b", f)):
            treffer.append((typ == "pos", len(n), typ, obj))
    if not treffer:
        return None
    treffer.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return treffer[0][2], treffer[0][3]


def _bewertung_position(p, k, e):
    zeilen = [f"{p['name']} ({ARTEN.get(p['art'])}): Score {de(p.get('score'), 0)}/100 – {p.get('score_quelle')}",
              f"Gewicht {pct(k['gewichte'].get(schluessel(p)))} · Empfehlung: {e['kategorie']} ({e['anlass']})"]
    f = p.get("fund") or {}
    if f.get("klasse"):
        zeilen.append(f"Einordnung Top 500: {EINORDNUNG.get(f['klasse'], f['klasse'])}"
                      + (f" · {f['grund']}" if f.get("grund") else ""))
    if p["art"] == "aktie":
        zeilen.append(e["bewertung"])
    if e["chancen"]:
        zeilen.append("Chancen: " + "; ".join(e["chancen"]))
    if e["risiken"]:
        zeilen.append("Risiken: " + "; ".join(e["risiken"]))
    return "\n".join(zeilen)


# ============================================================ Assistent (regelbasiert)
def assistent(frage, positionen, k, empf, profil=None, rang=None):
    """Beantwortet Fragen mit den echten Depotdaten und den Bewertungen der Top 500 (Qualitaets-Score,
    ETF-/wikifolio-Score). Liefert immer eine Antwort. -> {"antwort", "art", "simulation"?, "kandidaten"?}"""
    f = (frage or "").lower()
    pos = [p for p in positionen if not p.get("ohne_kurs")]
    pr = profil_bereinigen(profil)
    if re.search(r"alternativ|ersetz|stattdessen|vorschl|empfiehl|empfehl.*kauf|was .*kaufen|neue[nr]? (wert|aktie|etf)|"
                 r"bessere[nr]? (wert|aktie|etf|wikifolio)|nachkauf|beimisch|ergänz", f):
        art = ("etf" if re.search(r"\betfs?\b|fonds", f) else "wikifolio" if "wikifolio" in f else
               "aktie" if re.search(r"aktie", f) else None)
        schwach = sorted([p for p in pos if p.get("score") is not None], key=lambda p: p["score"])
        bezug = None
        if art is None:
            if schwach and schwach[0]["score"] < 60:
                bezug = schwach[0]
                art = bezug["art"] if bezug["art"] in ("aktie", "etf", "wikifolio") else "etf"
            else:
                fehl = [a for a, d in (k.get("abweichung") or {}).items() if a != "cash" and d <= -10]
                art = fehl[0] if fehl else "etf"
        kand = alternativen(rang, art, positionen, 5, pr["strategie"], bezug["score"] if bezug else None)
        if not kand:
            return {"art": "alternativen", "antwort": f"In den Top-500-Bewertungen gibt es für {ARTEN[art]} keine "
                    "besser bewerteten Werte außerhalb deines Depots (oder die Daten sind gerade nicht lesbar)."}
        kopf = (f"Besser bewertete {ARTEN[art]}-Alternativen zu {bezug['name']} (Score {de(bezug['score'], 0)})"
                if bezug else f"Bestbewertete {ARTEN[art]}-Werte der Top 500, die du noch nicht hast"
                + (" (Dividendenstrategie: höchste Ausschüttung unter den gut bewerteten)"
                   if pr["strategie"] == "dividende" and art == "aktie" else ""))
        return {"art": "alternativen", "kandidaten": kand,
                "antwort": kopf + ":\n" + "\n".join(_text_alternative(e) for e in kand)
                + "\nBewertung = Score der Top-500-Liste (Aktien: Qualitäts-Score, ETFs/wikifolios: eigener "
                  "Klassen-Score). Im Simulator kannst du jeden Wert virtuell hinzufügen."}
    if not pos:
        return {"art": "leer", "antwort": "Dein Depot enthält keine Positionen mit Kurs – es gibt nichts zu analysieren."}
    zahl = None
    m = re.search(r"(\d[\d\.\s]*(?:,\d+)?)\s*(?:€|eur|euro)", f)
    if m:
        zahl = _z(m.group(1).replace(".", "").replace(" ", "").replace(",", "."))
    if re.search(r"riskant|risikoreich|gefährlich|größte[n]? risik", f):
        risk = sorted(pos, key=lambda p: -(k["gewichte"].get(schluessel(p), 0) / 100
                                            * (p.get("vola") or VOLA_ANNAHME.get(p["art"], 20))
                                            * (1.5 if (p.get("score") or 50) < 45 else 1.0)))[:3]
        zeilen = [f"{i + 1}. {p['name']}: Gewicht {pct(k['gewichte'].get(schluessel(p)))}, Schwankung "
                  f"{pct(p.get('vola'), 0)} p. a., max. Rückgang {pct(p.get('maxdd'), 0)}, Score "
                  f"{de(p.get('score'), 0)}" for i, p in enumerate(risk)]
        return {"art": "risiko", "antwort": "Am riskantesten (Risikobeitrag = Gewicht × Schwankung, schwacher "
                                            "Score zählt 1,5-fach):\n" + "\n".join(zeilen)}
    if re.search(r"überschneid|ueberschneid|doppel|überlapp", f):
        u = k.get("ueberschneidungen") or []
        if not u:
            return {"art": "ueberschneidung", "antwort": "Keine Überschneidungen zwischen deinen ETFs erkannt "
                    "(erkannt wird über die Index-Familie im Namen, die genaue Zusammensetzung liegt nicht vor)."}
        return {"art": "ueberschneidung", "antwort": "Überschneidungen (nach Index-Familie, Näherung):\n" + "\n".join(
            f"• {x['a']} / {x['b']}: {x['grund']} – zusammen {pct(x['gewicht'])} des Depots" for x in u)}
    if re.search(r"halbier", f) or ("größte" in f and "position" in f):
        gr = max(pos, key=_wert)
        sk = schluessel(gr)
        sim = simulieren(positionen, {sk: math.floor((gr.get("stueck") or 0) / 2)}, cash=k["cash"])
        return {"art": "simulation", "simulation": {"aenderungen": {sk: math.floor((gr.get("stueck") or 0) / 2)}},
                "antwort": f"Simulation: {gr['name']} halbieren ({de(math.ceil((gr.get('stueck') or 0) / 2), 0)} "
                           f"Stück verkaufen, ca. {eur(sum(t['betrag'] for t in sim['trades']))}). "
                           "Die Wirkung siehst du im Simulator."}
    if zahl and re.search(r"investier|zusätzlich|anlegen|mehr geld", f):
        return {"art": "simulation", "simulation": {"zusatz": zahl, "optimieren": True},
                "antwort": f"Simulation: {eur(zahl)} zusätzlich – „Mein Depot optimieren“ verteilt das Geld auf "
                           "deine vorhandenen Werte entsprechend Zielstruktur und Score. Ergebnis im Simulator."}
    if re.search(r"dividend", f):
        mit = sorted([p for p in pos if p.get("div")], key=lambda p: -(p["div"] or 0))[:5]
        if not mit:
            return {"art": "dividende", "antwort": "Für deine Werte liegen keine Dividendenrenditen vor (wikifolios "
                    "schütten nicht aus; für ETFs kannst du sie unter „Angaben“ eintragen)."}
        zeilen = [f"• {p['name']}: {pct(p['div'])} Rendite"
                  + (f", Ausschüttungsquote {pct(_z(p['fund'].get('div_q')), 0)}" if (p.get('fund') or {}).get('div_q')
                     is not None else "") for p in mit]
        return {"art": "simulation", "simulation": {"szenario": "dividende"},
                "antwort": f"Aktuelle Dividendenprognose {eur(k.get('dividende'))} p. a. "
                           f"({pct(k.get('div_abdeckung'), 0)} des Depots mit bekannter Dividende). Höchste "
                           "Ausschüttungen:\n" + "\n".join(zeilen) + "\nDas Szenario „Dividendenorientiert“ "
                           "gewichtet diese Werte höher – Vergleich im Simulator."}
    if re.search(r"defensiv|sicherer|weniger risiko|absichern", f):
        return {"art": "simulation", "simulation": {"szenario": "defensiv"},
                "antwort": "Das Szenario „Defensiv“ senkt Aktien/wikifolios zugunsten breiter ETFs und Liquidität "
                           f"(Ziel: {', '.join(f'{ARTEN[a]} {v} %' for a, v in PROFILE['defensiv']['ziel'].items())})."
                           " Vergleich im Simulator."}
    if re.search(r"gewichtung|optimier|besser aufstellen|umschicht", f):
        return {"art": "simulation", "simulation": {"optimieren": True},
                "antwort": "„Mein Depot optimieren“ berechnet eine bessere Gewichtung deiner vorhandenen Werte "
                           "– Ergebnis im Simulator."}
    w = wert_finden(frage, pos, rang)
    if w:
        typ, obj = w
        if typ == "pos":
            return {"art": "wert", "antwort": _bewertung_position(obj, k, empf[schluessel(obj)])}
        return {"art": "wert", "kandidaten": [obj],
                "antwort": "Bewertung laut Top 500 (nicht in deinem Depot):\n" + _text_alternative(obj)}
    # nicht erkannt: Bewertungen aller Positionen laut Top 500
    zeilen = [f"• {p['name']}: Score {de(p.get('score'), 0)} · {empf[schluessel(p)]['kategorie']}"
              for p in sorted(pos, key=lambda p: -(p.get("score") or -1))]
    return {"art": "uebersicht",
            "antwort": "Dazu habe ich keine gezielte Auswertung. Die Bewertungen deiner Werte laut Top 500:\n"
                       + "\n".join(zeilen) + f"\nDepot-Score {de(k.get('score'), 0)}/100. Gezielt beantworten kann "
                       "ich Fragen zu Risiko, Überschneidungen, Dividenden, Gewichtung, defensiver Aufstellung, "
                       "zusätzlichem Kapital, einzelnen Werten (Name nennen) und besseren Alternativen."}


# ============================================================ Import / Export
_SPALTEN = {"name": ("name", "bezeichnung", "wertpapier", "titel", "instrument"),
            "kennung": ("isin", "wkn", "kennung", "symbol", "ticker"),
            "stueck": ("stueck", "stück", "anzahl", "menge", "stk", "stk.", "bestand", "anteile", "nominal"),
            "kaufkurs": ("kaufkurs", "einstandskurs", "einstandspreis", "kaufpreis", "ø-kurs", "durchschnittskurs",
                         "kurs_kauf"),
            "einstand": ("einstand", "einstandswert", "kaufwert", "investiert"),
            "kaufdatum": ("kaufdatum", "datum", "kauf am", "erwerbsdatum")}
CSV_VORLAGE = "Name;ISIN;Stueck;Kaufkurs;Kaufdatum\niShares Core MSCI World UCITS ETF;IE00B4L5Y983;10;85,50;15.03.2024\n"


def _zahl_de(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return _z(x)
    s = str(x).strip().replace("€", "").replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return _z(s)


def _datum(x):
    import datetime as _dt
    if x is None or x == "":
        return None
    if hasattr(x, "date") and not isinstance(x, str):
        try:
            return x.date() if hasattr(x, "hour") else x
        except Exception:
            return None
    s = str(x).strip()[:10]
    for f in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return _dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def import_zeilen(zeilen):
    """Depot-Import (CSV/Excel als Liste von dicts) -> (positionen, fehler). Spaltennamen werden tolerant
    erkannt (Name, ISIN/WKN, Stueck, Kaufkurs oder Einstand, Kaufdatum). Kurse werden NICHT uebernommen:
    die App holt sie aus der Kursquelle."""
    aus, fehler = [], []
    for nr, z in enumerate(zeilen or [], start=2):
        norm = {str(k).strip().lower(): v for k, v in (z or {}).items() if k is not None}
        w = {}
        for feld, namen in _SPALTEN.items():
            w[feld] = next((norm[n] for n in namen if n in norm and str(norm[n]).strip() not in ("", "nan", "None")),
                           None)
        stueck = _zahl_de(w["stueck"])
        kenn = str(w["kennung"] or "").strip().upper()
        name = str(w["name"] or "").strip() or kenn
        if not kenn and not name:
            continue
        if not stueck or stueck <= 0:
            fehler.append(f"Zeile {nr}: Stückzahl fehlt oder ist nicht positiv")
            continue
        kk, einst = _zahl_de(w["kaufkurs"]), _zahl_de(w["einstand"])
        if kk is None and einst is not None:
            kk = einst / stueck
        if einst is None and kk is not None:
            einst = kk * stueck
        aus.append({"name": name, "kennung": kenn, "stueck": stueck, "kaufkurs": kk, "einstand": einst,
                    "kaufdatum": _datum(w["kaufdatum"])})
    return aus, fehler


def export_tabelle(positionen, k, empf):
    """Zeilen fuer CSV/Excel: je Position die Analyse."""
    zeilen = []
    for p in positionen:
        sk = schluessel(p)
        e = empf.get(sk) or {}
        zeilen.append({"Name": p.get("name"), "Kennung": p.get("isin") or p.get("wkn"),
                       "Klasse": ARTEN.get(p.get("art"), p.get("art")), "Stück": p.get("stueck"),
                       "Kurs €": p.get("kurs"), "Wert €": None if p.get("ohne_kurs") else p.get("wert"),
                       "Gewicht %": (k.get("gewichte") or {}).get(sk), "Score": p.get("score"),
                       "Score-Quelle": p.get("score_quelle"), "Schwankung % p. a.": p.get("vola"),
                       "Max. Rückgang %": p.get("maxdd"), "Dividende %": p.get("div"), "TER %": p.get("ter"),
                       "Land": p.get("land"), "Branche": p.get("branche"), "Empfehlung": e.get("kategorie"),
                       "Priorität": e.get("prio"), "Begründung": "; ".join(e.get("gruende") or [])})
    return zeilen
