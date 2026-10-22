"""Investment-Scanner fuer den Portfolio Builder (reiner Rechenkern, ohne Streamlit).

Ablauf: Kandidaten aus den Daten der Watchlist (Qualitaets-Score mit Fundamentaldaten, Ranglisten,
Katalog) -> Score 0-100 je Anlageklasse -> Prognose je Wert (historische Rendite, zur langfristigen
Erwartung der Klasse geschrumpft; bei Aktien zusaetzlich aus Fundamentaldaten) -> Musterdepot mit
Hoechstgewicht je Position -> Monte-Carlo-Simulation des Anlageziels (Korrelationsmodell, Krisen-Regime).

Grundsatz: nur vorhandene Daten verwenden. Was fehlt (z. B. TER, Tracking Difference, wikifolio-
Gebuehren), wird als Luecke ausgewiesen; alle Modellannahmen stehen gesammelt in ANNAHMEN.
"""
import bisect
import copy
import math
import re

import numpy as np

import portfolio_builder as P

KLASSEN = {"etf": "ETFs", "aktie": "Aktien", "wikifolio": "wikifolios", "cash": "Cash / Tagesgeld"}

# Modellannahmen (keine Messwerte) - werden in der Oberflaeche offen ausgewiesen
ANNAHMEN = {
    # langfristige Renditeerwartung % p. a., zu der kurze/auffaellige Historien hingezogen werden
    "erwartung": {"aktie": 7.0, "etf": 6.5, "wikifolio": 5.0, "cash": 2.0},
    # Schwankung % p. a., wenn fuer einen Wert keine gemessene Volatilitaet vorliegt
    "vola": {"aktie": 32.0, "etf": 17.0, "wikifolio": 25.0, "cash": 0.5},
    # Korrelationen zwischen Werten (gleiche Klasse / verschiedene Klassen)
    "korrelation": {("aktie", "aktie"): 0.45, ("etf", "etf"): 0.80, ("wikifolio", "wikifolio"): 0.45,
                    ("aktie", "etf"): 0.70, ("aktie", "wikifolio"): 0.55, ("etf", "wikifolio"): 0.60},
    # ab so vielen Jahren Historie zaehlt die eigene Rendite zur Haelfte (Glaubwuerdigkeit)
    "glaubwuerdigkeit_jahre": 10.0,
    # Auswahl nach vergangener Rendite erwischt auch Glueck: nur dieser Teil des Vorsprungs zaehlt
    "vorsprung_anteil": 0.6,
    # historische Renditen werden vor der Schrumpfung begrenzt (gegen Ausreisser / Glueckstraehnen)
    "rendite_deckel": 25.0,
    # Krisen-Regime je Monat: Eintritt / Ende, Renditeabschlag je Prozentpunkt Schwankung (ein Depot mit
    # 18 % Schwankung verliert in der Krise rund 14 % p. a. zusaetzlich), Schwankungsfaktor. Kalibriert:
    # 100 % Aktienrisiko (18 %) -> Drawdown im 95-%-Quantil ueber 10 Jahre rund 59 % (MSCI World 2000-03
    # und 2008: rund 50-55 %); ohne Regime waeren es 55 %.
    "krise": {"p_ein": 0.012, "p_aus": 0.10, "abschlag_je_vola": 0.8, "vola_faktor": 1.4},
    # wikifolios brauchen fuer das Musterdepot so viele Jahre Historie (kurze Erfolgsserien)
    "wikifolio_min_jahre": 3.0,
    "tagesgeld": 2.0,
}

PROFILE = {
    "niedrig": {"titel": "Niedrig", "etf": 55.0, "aktie": 15.0, "wikifolio": 5.0, "cash": 25.0, "max_dd": 25.0},
    "mittel": {"titel": "Mittel", "etf": 50.0, "aktie": 30.0, "wikifolio": 15.0, "cash": 5.0, "max_dd": 40.0},
    "hoch": {"titel": "Hoch", "etf": 30.0, "aktie": 45.0, "wikifolio": 25.0, "cash": 0.0, "max_dd": 55.0},
}

# Einstellungen des Scanners im Builder (gespeichert mit den Builder-Eingaben)
EINSTELLUNGEN = {"scan_profil": "mittel", "scan_etf": 50.0, "scan_aktie": 30.0, "scan_wikifolio": 15.0,
                 "scan_cash": 5.0, "scan_max_dd": 40.0, "scan_max_gewicht": 5.0, "scan_kosten": 0.3,
                 "scan_inflation": 2.0, "scan_optimieren": True,
                 # Entnahme im Scanner: fester Betrag (Builder-Feld "entnahme") oder Verkauf von Stuecken
                 # je Musterdepot-Position ({kennung: Stueck pro Monat})
                 "scan_entnahme_art": "betrag", "scan_verkauf": {},
                 # eigene Eckdaten des Scanners (unabhaengig vom Builder); Kapital -1 = noch nie gesetzt
                 # (beim ersten Oeffnen aus dem Builder vorbelegt)
                 "scan_kapital": -1.0, "scan_einzahlung": 0.0, "scan_laufzeit": 10, "scan_ziel": 0.0,
                 "scan_entnahme": 0.0,
                 # Profil "Favoriten": nur selbst ausgewaehlte Werte der Top-500-Liste (Kennungen, siehe kennung)
                 "scan_favoriten": []}
FAVORITEN = "favoriten"
MAX_FAVORITEN = 200


def einstellungen_bereinigen(e):
    """Scanner-Einstellungen pruefen/begrenzen (fehlende -> Standard)."""
    aus = {}
    for k, std in EINSTELLUNGEN.items():
        v = e.get(k, std)
        if k == "scan_profil":
            aus[k] = v if v in PROFILE or v in ("eigene", FAVORITEN) else std
        elif k == "scan_optimieren":
            aus[k] = bool(v)
        elif k == "scan_entnahme_art":
            aus[k] = "stueck" if v == "stueck" else "betrag"
        elif k == "scan_laufzeit":
            aus[k] = int(min(max(_z(v, std), 1), 50))
        elif k == "scan_favoriten":
            liste = [str(x)[:60] for x in v if isinstance(x, str) and x.strip()] if isinstance(v, (list, tuple)) else []
            aus[k] = list(dict.fromkeys(liste))[:MAX_FAVORITEN]
        elif k == "scan_verkauf":
            aus[k] = {str(n)[:60]: min(_z(x, 0.0), P.MAX_KAPITAL) for n, x in list((v or {}).items())[:300]
                      if _z(x, 0.0) > 0} if isinstance(v, dict) else {}
        else:
            v = _z(v, std)
            grenzen = {"scan_max_dd": (5.0, 95.0), "scan_max_gewicht": (1.0, 100.0), "scan_kosten": (0.0, 5.0),
                       "scan_inflation": (-5.0, 20.0), "scan_kapital": (-1.0, P.MAX_KAPITAL),
                       "scan_einzahlung": (0.0, P.MAX_MONATLICH), "scan_ziel": (0.0, P.MAX_KAPITAL),
                       "scan_entnahme": (0.0, P.MAX_MONATLICH)}.get(k, (0.0, 100.0))
            aus[k] = min(max(v, grenzen[0]), grenzen[1])
    return aus


def aufteilung(e):
    """Klassen-Aufteilung % (Profil oder eigene, auf 100 % gebracht)."""
    if e["scan_profil"] in PROFILE:
        p = PROFILE[e["scan_profil"]]
        return {k: p[k] for k in ("etf", "aktie", "wikifolio", "cash")}
    roh = {k: max(e[f"scan_{k}"], 0.0) for k in ("etf", "aktie", "wikifolio", "cash")}
    s = sum(roh.values())
    return {k: v / s * 100.0 for k, v in roh.items()} if s > 0 else {"etf": 0, "aktie": 0, "wikifolio": 0, "cash": 100.0}


# Hebel-, Short- und Faktor-Daily-Produkte gehoeren nicht in ein langfristiges Musterdepot
_HEBEL = re.compile(r"(\b[2-9]x\b|\bx[2-9]\b|leverag|short|\bbear\b|\bbull\b|daily|ultra|hebel|inverse|"
                    r"\b[2-9]\s?fach|\bfaktor\b)", re.I)
# ETFs auf denselben Kernindex nur einmal (Ueberschneidung der zugrunde liegenden Werte)
# Reihenfolge: Branchen-/Themenbegriffe vor den breiten Indizes ("S&P 500 Information Technology" ist IT)
_INDEX_GRUPPEN = [("semiconductor", "halbleiter"), ("information technology", "it"), ("technology", "it"),
                  ("bitcoin", "krypto"), ("crypto", "krypto"), ("nasdaq", "nasdaq"),
                  ("msci world", "world"), ("s&p 500", "sp500"), ("sp 500", "sp500"),
                  ("all-world", "allworld"), ("all world", "allworld"), ("acwi", "allworld"),
                  ("emerging", "em"), ("stoxx 600", "europa"), ("msci europe", "europa"), ("dax", "dax")]
# Themen-Cluster mit starker Ueberschneidung: hoechstens so viele ETFs je Cluster
_CLUSTER = {"halbleiter": "tech", "it": "tech", "nasdaq": "tech"}
MAX_JE_CLUSTER = 2
ZEITRAEUME_PA = (("10J", 10), ("5J", 5), ("3J", 3), ("2J", 2), ("1J", 1))


def _z(x, d=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return d
    return d if math.isnan(v) or math.isinf(v) else v


# ---------------------------------------------------------------- Kandidaten
_WKN = re.compile(r"^(?=.*\d)[A-Z0-9]{6}$")


def kandidaten_aktien(qualitaet_werte, alle_aktien, fx=None, isin_je_symbol=None):
    """Aktien mit Fundamentaldaten (Qualitaets-Score der Watchlist) + Kursentwicklung aus den
    Index-Listen. alle_aktien = {symbol: {name, kennung, 1J, 3J, 5J, 10J}}, fx = {waehrung: je EUR},
    isin_je_symbol = {yahoo_symbol: isin} (Zuordnung der Watchlist). Kennung aus den ls-tc-Listen ist
    die WKN - mit WKN/ISIN laesst sich der Kurs exakt abrufen."""
    isin_je_symbol = isin_je_symbol or {}
    aus = []
    for s, q in (qualitaet_werte or {}).items():
        perf = alle_aktien.get(s) or {}
        kurs, wae = _z(q.get("kurs")), str(q.get("kwae") or "")
        kurs_eur = None
        if kurs:
            if wae == "EUR":
                kurs_eur = kurs
            elif wae == "GBp" and fx and fx.get("GBP"):
                kurs_eur = kurs / 100.0 / fx["GBP"]
            elif fx and fx.get(wae):
                kurs_eur = kurs / fx[wae]
        kennung = str(perf.get("kennung") or "").strip().upper()
        aus.append({"art": "aktie", "name": str(q.get("name") or s), "ticker": s,
                    "wkn": kennung if _WKN.match(kennung) else "", "isin": isin_je_symbol.get(s, ""),
                    "kennung": str(perf.get("kennung") or s),
                    "perf": {z: _z(perf.get(z)) for z, _ in ZEITRAEUME_PA if _z(perf.get(z)) is not None},
                    "vola": None, "maxdd": None, "jahre": None, "kurs": kurs_eur,
                    "branche": str(q.get("br") or ""), "fund": q})
    return aus


def kandidaten_katalog(katalog, arten=("etf", "wikifolio"), alle=False):
    """ETFs und wikifolios aus dem Katalog des Builders (Watchlist-Katalog + Ranglisten). Hebel-,
    Short- und Krypto-Produkte fallen heraus. alle: selbst ausgewaehlte Werte (Favoriten) - kein Hebel-Filter,
    auch ohne Kursentwicklung (dann rechnet die Prognose mit der Erwartung der Klasse)."""
    aus = []
    for w in katalog or []:
        art = w.get("art")
        if art not in arten or (not alle and _HEBEL.search(str(w.get("name") or ""))):
            continue
        perf = {z: _z(w.get(z)) for z, _ in ZEITRAEUME_PA if _z(w.get(z)) is not None}
        if not perf and not alle:
            continue
        aus.append({"art": art, "name": str(w["name"]), "ticker": "", "wkn": str(w.get("wkn") or ""),
                    "isin": str(w.get("isin") or ""), "kennung": str(w.get("wkn") or w.get("isin") or ""),
                    "perf": perf, "vola": _z(w.get("vola")), "maxdd": _z(w.get("maxdd")),
                    "jahre": _z(w.get("jahre")), "kurs": _z(w.get("kurs")), "branche": "", "fund": None})
    return aus


def favoriten_markieren(kandidaten, auswahl):
    """Favoriten (ausgewaehlte Katalog-Eintraege) unter den Kandidaten kennzeichnen ("favorit": True). Ein Favorit,
    der schon Kandidat ist (gleiche ISIN/WKN, z. B. Aktie mit Fundamentaldaten), wird dort markiert, sonst aus dem
    Katalog-Eintrag angelegt. Bewertet wird danach die ganze Liste - Scores bleiben mit allen Werten vergleichbar.
    -> neue Kandidatenliste"""
    def schluessel(c):
        return {k.upper() for k in (c.get("isin"), c.get("wkn")) if k}

    aus, offen = [dict(c) for c in kandidaten], list(auswahl or [])
    je_kennung = {}
    for c in aus:
        for k in schluessel(c):
            je_kennung.setdefault(k, c)
    neu = []
    for w in offen:
        treffer = next((je_kennung[k] for k in schluessel(w) if k in je_kennung), None)
        if treffer is not None and treffer["art"] == w.get("art"):
            treffer["favorit"] = True
        else:
            neu += [dict(c, favorit=True) for c in kandidaten_katalog([w], ("aktie", "etf", "wikifolio"), alle=True)]
    return aus + neu


# ---------------------------------------------------------------- Kennzahlen je Wert
def hist_rendite(c):
    """Laengste vorhandene Rendite p. a. -> (rendite %, jahre) bzw. (None, 0)."""
    for z, j in ZEITRAEUME_PA:
        v = c["perf"].get(z)
        if v is not None and v > -100:
            return ((1 + v / 100.0) ** (1.0 / j) - 1) * 100.0, j
    return None, 0


def historie_jahre(c):
    _, j = hist_rendite(c)
    return max(j, c.get("jahre") or 0)


def vola(c):
    """Gemessene Schwankung % p. a., sonst die Annahme der Klasse. -> (wert, gemessen?)"""
    v = c.get("vola")
    if v and v > 0:
        return float(v), True
    return ANNAHMEN["vola"][c["art"]], False


def fundamental_rendite(f):
    """Aktien: Renditeerwartung aus Fundamentaldaten = Free-Cashflow-Rendite + halbes Umsatzwachstum
    (Ertrag heute plus vorsichtig angesetztes Wachstum, je begrenzt). None ohne Daten."""
    if not f:
        return None
    fcfy, g = _z(f.get("fcfy")), _z(f.get("g_ums"))
    if fcfy is None and g is None:
        return None
    return min(max(fcfy or 0.0, -5.0), 8.0) + min(max((g or 0.0) * 0.5, -3.0), 5.0)


def prognose(c, horizont_jahre):
    """Erwartete Rendite % p. a. und Spanne ueber den Anlagehorizont - nie die bloesse Fortschreibung:
    historische Rendite (begrenzt) wird je nach Laenge der Historie zur langfristigen Erwartung der
    Klasse hingezogen; bei Aktien mit Fundamentaldaten zur Haelfte die Fundamental-Erwartung.
    -> {"mu", "sigma", "pess", "opt", "teile": [Beschreibung]}"""
    a = ANNAHMEN
    prior = a["erwartung"][c["art"]]
    r, j = hist_rendite(c)
    teile = []
    if r is not None:
        rd = max(min(r, a["rendite_deckel"]), -a["rendite_deckel"])
        w = min(j, 10) / (min(j, 10) + a["glaubwuerdigkeit_jahre"]) * a["vorsprung_anteil"]
        mu = prior + w * (rd - prior)
        teile.append(f"{j} J. Historie {r:+.1f} % p. a." + (f" (begrenzt auf {rd:.0f} %)" if rd != r else "")
                     + f" zu {w * 100:.0f} %, Erwartung der Klasse {prior:.1f} %")
    else:
        mu = prior
        teile.append(f"keine Historie - Erwartung der Klasse {prior:.1f} %")
    fr = fundamental_rendite(c.get("fund"))
    if fr is not None:
        mu = 0.5 * mu + 0.5 * fr
        teile.append(f"Fundamental (FCF-Rendite + ½ Umsatzwachstum) {fr:.1f} % zur Hälfte")
    s, _ = vola(c)
    t = max(float(horizont_jahre), 1.0)
    breite = 1.2816 * s / math.sqrt(t)                    # 10-/90-%-Quantil der Jahresrendite ueber t Jahre
    return {"mu": mu, "sigma": s, "pess": mu - breite, "opt": mu + breite, "teile": teile}


def risikostufe(sigma):
    return "niedrig" if sigma < 12 else "mittel" if sigma < 25 else "hoch"


# ---------------------------------------------------------------- Scores
def _perzentile(werte):
    """Rang-Perzentil 0..100 je Eintrag (None -> 50, neutral)."""
    gueltig = sorted(v for v in werte if v is not None)
    if not gueltig:
        return [50.0] * len(werte)
    aus = []
    for v in werte:
        if v is None:
            aus.append(50.0)
            continue
        unter, bis = bisect.bisect_left(gueltig, v), bisect.bisect_right(gueltig, v)
        aus.append(100.0 * (unter + 0.5 * (bis - unter)) / len(gueltig))
    return aus


def bewerten(kandidaten, horizont_jahre):
    """Score 0-100 je Klasse (Perzentile innerhalb der Klasse, damit Aktien, ETFs und wikifolios mit
    passenden Massstaeben gemessen werden). Ergaenzt je Kandidat: score, prognose, datenbasis, luecken,
    chancen, risiken, ausreichend (genug Daten fuer eine Empfehlung). -> neue Liste, je Klasse sortiert."""
    aus, a_min_wiki = [], ANNAHMEN["wikifolio_min_jahre"]
    for art in ("aktie", "etf", "wikifolio"):
        cs = [copy.deepcopy(c) for c in kandidaten if c["art"] == art]
        if not cs:
            continue
        hist = [hist_rendite(c)[0] for c in cs]
        sig = [vola(c)[0] for c in cs]
        rr = [(h / s) if h is not None and s else None for h, s in zip(hist, sig)]
        dd = [(-abs(c["maxdd"]) if c.get("maxdd") is not None else None) for c in cs]
        p_rr, p_dd, p_h = _perzentile(rr), _perzentile(dd), _perzentile(
            [math.log1p(h / 100.0) if h is not None and h > -100 else None for h in hist])
        for i, c in enumerate(cs):
            jahre = historie_jahre(c)
            f = c.get("fund") or {}
            if art == "aktie":
                q = _z(f.get("gesamt"))
                score = 0.5 * (q if q is not None else 50.0) + 0.3 * p_rr[i] + 0.2 * p_dd[i]
                basis = ["Qualitäts-Score (Wachstum, ROIC, Margen, Verschuldung, Bewertung)",
                         "Rendite je Risiko", "Drawdown"]
                luecken = ["Analystenprognosen", "Volatilität gemessen"] if c.get("vola") is None else ["Analystenprognosen"]
                ausreichend = q is not None and hist[i] is not None
            elif art == "etf":
                score = 0.45 * p_h[i] + 0.35 * p_rr[i] + 0.2 * p_dd[i]
                basis = ["Rendite p. a.", "Rendite je Risiko", "Drawdown"]
                luecken = ["TER", "Tracking Difference", "Fondsvolumen", "Replikation"]
                ausreichend = jahre >= 3
            else:
                laenge = min(jahre, 10) / 10.0 * 100.0
                score = 0.35 * p_rr[i] + 0.25 * laenge + 0.2 * p_dd[i] + 0.2 * p_h[i]
                basis = ["Rendite je Risiko", "Länge der Historie", "Drawdown", "Rendite (logarithmisch)"]
                luecken = ["Gebühren", "Handelsstrategie", "Trader", "investiertes Kapital", "Emittentenrisiko"]
                ausreichend = jahre >= a_min_wiki
            if not ausreichend:
                score *= 0.6                                  # zu wenig Daten: nicht empfehlen
            c["score"] = int(round(max(min(score, 100.0), 0.0)))
            c["hist"], c["hist_jahre"] = hist[i], jahre
            c["prognose"] = prognose(c, horizont_jahre)
            c["datenbasis"], c["luecken"], c["ausreichend"] = basis, luecken, ausreichend
            c["chancen"], c["risiken"] = _chancen_risiken(c)
            aus.append(c)
    aus.sort(key=lambda c: (c["art"], -c["score"], c["name"].lower()))
    return aus


def _chancen_risiken(c):
    """Kurze, aus den Daten abgeleitete Punkte (keine erfundenen Aussagen)."""
    ch, ri = [], []
    f = c.get("fund") or {}
    if f:
        if _z(f.get("gesamt"), 0) >= 80:
            ch.append(f"hohe Qualität ({int(f['gesamt'])}/100)")
        if f.get("bew") in ("günstig", "fair"):
            ch.append(f"Bewertung {f['bew']}")
        elif f.get("bew"):
            ri.append(f"Bewertung {f['bew']}")
        if f.get("moat") == "stark":
            ch.append("starker Burggraben")
        if _z(f.get("roic"), 0) >= 15:
            ch.append(f"ROIC {f['roic']:.0f} %")
        if _z(f.get("g_eps"), 0) >= 15:
            ch.append(f"Gewinnwachstum {f['g_eps']:.0f} % p. a.")
        if _z(f.get("nde"), 0) > 3:
            ri.append(f"Verschuldung {_de1(f['nde'])}× EBITDA")
        if f.get("risiko") == "hoch":
            ri.append("Risikoeinstufung hoch")
    if c.get("hist") is not None and c.get("vola"):
        rr = c["hist"] / c["vola"]
        if rr >= 1:
            ch.append(f"Rendite je Risiko {_de1(rr)}")
    if c.get("maxdd") is not None and abs(c["maxdd"]) >= 40:
        ri.append(f"Drawdown {-abs(c['maxdd']):.0f} %")
    if c.get("vola") and c["vola"] >= 35:
        ri.append(f"Schwankung {c['vola']:.0f} % p. a.")
    if c.get("hist_jahre", 0) < 3:
        ri.append(f"kurze Historie ({c.get('hist_jahre', 0):.0f} J.)")
    if c.get("hist") is not None and c["hist"] > ANNAHMEN["rendite_deckel"]:
        ri.append("Ausnahme-Rendite – nicht fortschreibbar")
    return ch[:3], ri[:3]


# ---------------------------------------------------------------- Musterdepot
def _index_gruppe(name):
    n = name.lower()
    return next((g for k, g in _INDEX_GRUPPEN if k in n), None)


def musterdepot(bewertet, aufteilung, max_gewicht=5.0, min_score=55, max_je_branche=3, nur_mit_kurs=False,
                frei=False):
    """Musterdepot: je Klasse die besten Werte mit genug Daten, gleich gewichtet, jede Position hoechstens
    max_gewicht %. Diversifikation: je Branche hoechstens max_je_branche Aktien, je Kernindex ein ETF,
    je Themen-Cluster (z. B. Tech: Halbleiter/IT/Nasdaq) hoechstens MAX_JE_CLUSTER ETFs.
    Was nicht verteilt werden kann (zu wenig geeignete Werte), geht ins Cash. Summe = 100 %.
    nur_mit_kurs: nur Werte mit Kurs (Top-500-Daten) - sonst liesse sich keine Stueckzahl kaufen.
    frei: selbst ausgewaehlte Werte (Favoriten) - ohne Mindest-Score, Datenpruefung und Branchen-/Index-Grenzen.
    -> {"positionen": [...], "cash": %, "hinweise": [...]}"""
    max_gewicht = max(float(max_gewicht), 0.5)
    pos, hinweise, cash = [], [], float(aufteilung.get("cash", 0.0))
    for art in ("etf", "aktie", "wikifolio"):
        ziel = float(aufteilung.get(art, 0.0))
        if ziel <= 0:
            continue
        n_soll = int(math.ceil(ziel / max_gewicht - 1e-9))
        gewaehlt, branchen, gruppen, cluster = [], {}, set(), {}
        for c in (c for c in bewertet if c["art"] == art):
            if len(gewaehlt) >= n_soll and not frei:     # Favoriten: alle, gleich gewichtet
                break
            if not frei and (not c["ausreichend"] or c["score"] < min_score):
                continue
            if nur_mit_kurs and not (c.get("kurs") or 0) > 0:
                continue
            if frei:
                gewaehlt.append(c)
                continue
            if art == "aktie" and c["branche"]:
                if branchen.get(c["branche"], 0) >= max_je_branche:
                    continue
            g = _index_gruppe(c["name"]) if art == "etf" else None
            if g and g in gruppen:
                continue
            cl = _CLUSTER.get(g)
            if cl and cluster.get(cl, 0) >= MAX_JE_CLUSTER:
                continue
            gewaehlt.append(c)
            if art == "aktie" and c["branche"]:
                branchen[c["branche"]] = branchen.get(c["branche"], 0) + 1
            if g:
                gruppen.add(g)
            if cl:
                cluster[cl] = cluster.get(cl, 0) + 1
        if not gewaehlt:
            hinweise.append(f"{KLASSEN[art]}: keine Favoriten mit Kurs – {ziel:.0f} % bleiben Cash." if frei else
                            f"{KLASSEN[art]}: keine Werte mit ausreichenden Daten und Score ≥ {min_score} – "
                            f"{ziel:.0f} % bleiben Cash.")
            cash += ziel
            continue
        je = min(ziel / len(gewaehlt), max_gewicht)
        if len(gewaehlt) < n_soll:
            hinweise.append(f"{KLASSEN[art]}: nur {len(gewaehlt)} {'Favoriten' if frei else 'geeignete Werte'} – bei höchstens "
                            f"{max_gewicht:.1f} % je Position {ziel - je * len(gewaehlt):.1f} % ins Cash.")
        cash += ziel - je * len(gewaehlt)
        pos += [dict(c, gewicht=je) for c in gewaehlt]
    return {"positionen": pos, "cash": max(cash, 0.0), "hinweise": hinweise, "max_gewicht": max_gewicht}


def _korrelation(a, b):
    if a == "cash" or b == "cash":
        return 0.0
    k = ANNAHMEN["korrelation"]
    return k.get((a, b), k.get((b, a), 0.5))


def portfolio_kennzahlen(depot):
    """Erwartete Rendite und Schwankung des Depots (Gewichte inkl. Cash, Korrelationsmodell)."""
    eintraege = [(p["gewicht"] / 100.0, p["prognose"]["mu"], p["prognose"]["sigma"], p["art"])
                 for p in depot["positionen"]]
    eintraege.append((depot["cash"] / 100.0, ANNAHMEN["tagesgeld"], ANNAHMEN["vola"]["cash"], "cash"))
    mu = sum(w * m for w, m, _, _ in eintraege)
    var = 0.0
    for i, (wi, _, si, ai) in enumerate(eintraege):
        for j, (wj, _, sj, aj) in enumerate(eintraege):
            rho = 1.0 if i == j else _korrelation(ai, aj)
            var += wi * wj * rho * (si / 100.0) * (sj / 100.0)
    return mu, math.sqrt(max(var, 0.0)) * 100.0


# ---------------------------------------------------------------- Simulation
def scanner_eingaben(e):
    """Builder-Eingaben -> Eingaben fuer die Scanner-Rechnung mit den eigenen Eckdaten des Scanners
    (Startkapital, Einzahlung, Laufzeit in Jahren, Ziel, Entnahme; ohne Kredit und Ausgaben)."""
    e = P.bereinigen(e)
    return dict(e, anfangskapital=max(e["scan_kapital"], 0.0), sonstiges_kapital=0.0, kredit_summe=0.0,
                kredit_rate=0.0, ausgaben=0.0, einzahlung=e["scan_einzahlung"], entnahme=e["scan_entnahme"],
                laufzeit=e["scan_laufzeit"], laufzeit_einheit="Jahre", zielvermoegen=e["scan_ziel"])


def kennung(p):
    """Schluessel einer Depot-Position fuer gespeicherte Verkaufsmengen."""
    return str(p.get("isin") or p.get("wkn") or p.get("ticker") or p.get("name") or "")[:60]


def depot_positionen(depot, verkauf=None):
    """Musterdepot -> Positionen im Builder-Format (Kurs in EUR, Gewicht, erwartete Rendite aus der
    Prognose, Verkauf Stueck/Monat aus verkauf {kennung: stueck}); der Cash-Teil als Tagesgeld (Kurs 1)."""
    verkauf = verkauf or {}
    pos = []
    for p in depot["positionen"]:
        q = {"name": p["name"], "kurs": p.get("kurs") or 0.0, "gewicht": p["gewicht"],
             "art": p["art"] if p["art"] in P.ARTEN else "sonstig", "rendite": p["prognose"]["mu"],
             "wkn": p.get("wkn") or "", "isin": p.get("isin") or ""}
        if verkauf.get(kennung(p)):
            q["verkauf_stueck"] = verkauf[kennung(p)]
        pos.append(q)
    if depot.get("cash", 0) > 0.01:
        q = {"name": P.TAGESGELD, "kurs": 1.0, "gewicht": depot["cash"], "art": "sonstig",
             "rendite": ANNAHMEN["tagesgeld"]}
        if verkauf.get(P.TAGESGELD):
            q["verkauf_stueck"] = verkauf[P.TAGESGELD]
        pos.append(q)
    return pos


def depot_entnahmeplan(depot, e):
    """Verkaufsplan (portfolio_builder.entnahmeplan) fuer das Musterdepot mit der Entnahme-Art des Scanners."""
    e = P.bereinigen(e)
    return P.entnahmeplan(dict(e, positionen=depot_positionen(depot, e["scan_verkauf"]),
                               entnahme_art=e["scan_entnahme_art"]))


def entnahmen(e, depot=None):
    """Entnahme EUR je Monat im Scanner: fester Betrag oder Erloes der verkauften Stuecke des Depots."""
    e = P.bereinigen(e)
    if e["scan_entnahme_art"] == "stueck":
        return depot_entnahmeplan(depot, e)["monatlich"] if depot else [0.0] * P.monate(e)
    return [e["entnahme"]] * P.monate(e)


def zahlungsplan(e, depot=None):
    """Monatliche Zahlungen ins/aus dem Depot und Restschuld am Ende - wie in der Builder-Simulation
    (Einzahlung - Entnahme - Ausgaben - Kreditrate). Entnahme: siehe entnahmen (depot fuer Stueckzahlen).
    -> (start, [cashflow je Monat], restschuld)"""
    e = P.bereinigen(e)
    iz, d, cfs = P.zins_monat(e), e["kredit_summe"], []
    for entnahme in entnahmen(e, depot):
        zinsen = d * iz
        rate = min(e["kredit_rate"], d + zinsen) if d > 1e-9 else 0.0
        d = max(d + zinsen - rate, 0.0)
        cfs.append(e["einzahlung"] - entnahme - e["ausgaben"] - rate)
    return P.anlagekapital(e), cfs, d


def simulieren(mu, sigma, start, cashflows, kosten=0.0, pfade=10000, seed=7, regime=True):
    """Monte-Carlo: monatliche Renditen normalverteilt (Depot monatlich auf Zielgewichte zurueckgesetzt),
    mit Krisen-Regime (Markov: Eintritt/Ende je Monat, Renditeabschlag, hoehere Schwankung). Das Regime
    aendert weder Durchschnittsrendite noch Gesamtschwankung (gemessene Renditen und Volatilitaeten
    enthalten Krisen bereits): ausserhalb der Krisen liegen Rendite hoeher und Schwankung niedriger - es
    macht die Verlaeufe nur realistisch holpriger (Krisen gebuendelt statt gleichmaessig verteilt).
    -> {"werte": array pfade x (monate+1), "index": Wertindex ohne Zahlungen, "max_dd": je Pfad %}"""
    rng = np.random.default_rng(seed)
    n = len(cashflows)
    k = ANNAHMEN["krise"]
    netto = mu - kosten
    abschlag = k["abschlag_je_vola"] * sigma                                 # Krise trifft riskante Depots haerter
    anteil_krise = k["p_ein"] / (k["p_ein"] + k["p_aus"]) if regime else 0.0
    normal = netto + anteil_krise / (1 - anteil_krise) * abschlag          # Mittel ueber beide = netto
    mu_m = (1 + normal / 100.0) ** (1 / 12.0) - 1
    mu_k = (1 + max(normal - abschlag, -95.0) / 100.0) ** (1 / 12.0) - 1
    # Gesamtvarianz je Monat = Mischung beider Regime + Streuung der Regime-Mittel
    ziel_var = (sigma / 100.0) ** 2 / 12.0
    f = k["vola_faktor"] if regime else 1.0
    mittel_var = anteil_krise * (1 - anteil_krise) * (mu_m - mu_k) ** 2 if regime else 0.0
    sd_m = math.sqrt(max(ziel_var - mittel_var, 0.0) / (anteil_krise * f * f + (1 - anteil_krise)))
    werte = np.empty((pfade, n + 1))
    werte[:, 0] = start
    idx = np.ones(pfade)
    hoch = np.ones(pfade)
    max_dd = np.zeros(pfade)
    krise = np.zeros(pfade, dtype=bool)
    v = np.full(pfade, float(start))
    for t in range(n):
        if regime:
            u = rng.random(pfade)
            krise = np.where(krise, u >= k["p_aus"], u < k["p_ein"])
        z = rng.standard_normal(pfade)
        r = np.where(krise, mu_k + sd_m * k["vola_faktor"] * z, mu_m + sd_m * z) if regime else mu_m + sd_m * z
        r = np.maximum(r, -0.95)
        v = np.maximum(v * (1 + r) + cashflows[t], 0.0)
        idx = idx * (1 + r)
        hoch = np.maximum(hoch, idx)
        max_dd = np.maximum(max_dd, 1 - idx / hoch)
        werte[:, t + 1] = v
    return {"werte": werte, "max_dd": max_dd * 100.0}


def auswerten(sim, ziel, restschuld=0.0):
    """Kennzahlen einer Simulation: Endwerte (Perzentile), Wahrscheinlichkeit Ziel (netto), Drawdown."""
    end = sim["werte"][:, -1] - restschuld
    p = {q: float(np.percentile(end, q)) for q in (5, 10, 25, 50, 75, 90, 95)}
    return {"end": p, "mittel": float(end.mean()),
            "wahrscheinlichkeit": float((end >= ziel).mean()) if ziel > 0 else None,
            "dd50": float(np.percentile(sim["max_dd"], 50)), "dd95": float(np.percentile(sim["max_dd"], 95))}


def verlauf_jaehrlich(sim, restschuld_je_monat=None):
    """Perzentile 10/50/90 des Depotwerts je vollem Jahr (und am Ende)."""
    n = sim["werte"].shape[1] - 1
    punkte = sorted(set(list(range(0, n + 1, 12)) + [n]))
    return [{"monat": m, "p10": float(np.percentile(sim["werte"][:, m], 10)),
             "p50": float(np.percentile(sim["werte"][:, m], 50)),
             "p90": float(np.percentile(sim["werte"][:, m], 90))} for m in punkte]


def optimieren(depot, e, ziel, max_dd, kosten=0.0, pfade=4000):
    """Auf die Wahrscheinlichkeit des Anlageziels optimieren: der investierte Teil der gewaehlten Aufteilung
    wird in Stufen (30-100 % davon) gegen Cash getauscht - nie mehr als die eigene Aufteilung. Gewaehlt wird
    unter den Stufen, deren Drawdown (95-%-Quantil) die Verlusttoleranz einhaelt, die mit der hoechsten
    Zielwahrscheinlichkeit; bei Gleichstand (z. B. Ziel ueberall 0 %) die mit dem hoeheren mittleren Endwert -
    also eher die eigene Aufteilung als Cash. Haelt keine Stufe die Toleranz ein: die vorsichtigste.
    -> {"stufen": [...], "beste": anteil, "eingehalten": bool}"""
    stufen = []
    for anteil in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        d = skalieren(depot, anteil)
        start, cfs, rest = zahlungsplan(e, d)                      # Stueck-Entnahmen haengen am Depot
        mu, sig = portfolio_kennzahlen(d)
        a = auswerten(simulieren(mu, sig, start, cfs, kosten, pfade=pfade, seed=11), ziel, rest)
        stufen.append({"anteil": anteil, "investiert": 100.0 - d["cash"], "mu": mu, "sigma": sig, **a})
    erlaubt = [s for s in stufen if s["dd95"] <= max_dd]
    beste = (max(erlaubt, key=lambda s: (round(s["wahrscheinlichkeit"] or 0.0, 3), s["end"][50])) if erlaubt
             else stufen[0])
    return {"stufen": stufen, "beste": beste["anteil"], "eingehalten": bool(erlaubt)}


def skalieren(depot, anteil):
    """Investierten Teil auf 'anteil' (0..1) der gewaehlten Aufteilung setzen, Rest Cash (1.0 = genau die eigene
    Aufteilung); Positionen behalten ihr Verhaeltnis und bleiben unter dem Hoechstgewicht."""
    grenze = depot.get("max_gewicht", 100.0)
    pos = [dict(p, gewicht=min(p["gewicht"] * anteil, grenze)) for p in depot["positionen"]]
    return dict(depot, positionen=pos, cash=max(100.0 - sum(p["gewicht"] for p in pos), 0.0))


def alternativen(mu, sigma, e, ziel, kosten=0.0, pfade=3000, schwelle=0.5, depot=None):
    """Wenn das Ziel unrealistisch ist: noetige Sparrate bzw. Laufzeit fuer die Zielwahrscheinlichkeit
    'schwelle' und das mit dieser Wahrscheinlichkeit erreichbare Ziel. Keine hoeheren Renditeannahmen."""
    e = P.bereinigen(e)

    def wkt(e2):
        start, cfs, rest = zahlungsplan(e2, depot)
        return auswerten(simulieren(mu, sigma, start, cfs, kosten, pfade=pfade, seed=13), ziel, rest)

    basis = wkt(e)
    aus = {"erreichbar": basis["end"][50] if schwelle == 0.5 else None}
    lo, hi = e["einzahlung"], max(e["einzahlung"] * 2, 100.0)
    while (wkt(dict(e, einzahlung=hi))["wahrscheinlichkeit"] or 0) < schwelle and hi < P.MAX_MONATLICH:
        hi *= 2
    if hi < P.MAX_MONATLICH:
        for _ in range(14):
            m = (lo + hi) / 2
            if (wkt(dict(e, einzahlung=m))["wahrscheinlichkeit"] or 0) >= schwelle:
                hi = m
            else:
                lo = m
        aus["sparrate"] = hi
    jahre = P.monate(e) / 12.0
    for plus in range(1, 31):
        e2 = dict(e, laufzeit=int(round((jahre + plus) * 12)), laufzeit_einheit="Monate")
        if (wkt(e2)["wahrscheinlichkeit"] or 0) >= schwelle:
            aus["jahre_mehr"] = plus
            break
    return aus


# ---------------------------------------------------------------- Risiken, Empfehlungen
STRESS = {
    "Aktiencrash": {"aktie": -40.0, "etf": -35.0, "wikifolio": -40.0, "cash": 0.0},
    "Rezession": {"aktie": -25.0, "etf": -20.0, "wikifolio": -25.0, "cash": 0.0},
    "Dauerhaft hohe Inflation (1 Jahr, real)": {"aktie": -12.0, "etf": -10.0, "wikifolio": -12.0, "cash": -5.0},
    "Enttäuschende Unternehmensgewinne": {"aktie": -20.0, "etf": -12.0, "wikifolio": -15.0, "cash": 0.0},
}


def stresstest(depot, depotwert):
    """Sofortverlust des Depots je Szenario (Annahmen je Klasse, siehe STRESS)."""
    aus = []
    for name, schock in STRESS.items():
        verlust = sum(p["gewicht"] / 100.0 * schock[p["art"]] for p in depot["positionen"]) + \
            depot["cash"] / 100.0 * schock["cash"]
        aus.append({"szenario": name, "prozent": verlust, "euro": depotwert * verlust / 100.0})
    return aus


def schwachstellen(depot):
    """Groesste Schwachstellen aus der Zusammensetzung."""
    aus = []
    je_art = {}
    for p in depot["positionen"]:
        je_art[p["art"]] = je_art.get(p["art"], 0.0) + p["gewicht"]
    if je_art.get("wikifolio", 0) >= 20:
        aus.append(f"{je_art['wikifolio']:.0f} % in wikifolios: Strategien können sich ändern, Emittentenrisiko "
                   "des Zertifikats, Gebühren nicht in den Daten.")
    branchen = {}
    for p in depot["positionen"]:
        if p["art"] == "aktie" and p["branche"]:
            branchen[p["branche"]] = branchen.get(p["branche"], 0.0) + p["gewicht"]
    if branchen:
        b, g = max(branchen.items(), key=lambda x: x[1])
        if g >= 10:
            aus.append(f"Größte Branche bei den Einzelaktien: {b} mit {g:.0f} %.")
    if je_art.get("etf", 0) + je_art.get("aktie", 0) >= 70:
        aus.append("Hoher Aktienanteil: in einem Crash fällt der Großteil des Depots gemeinsam (Korrelation steigt in "
                   "Krisen).")
    kurz = [p["name"] for p in depot["positionen"] if p.get("hist_jahre", 0) < 3]
    if kurz:
        aus.append(f"{len(kurz)} Position(en) mit weniger als 3 Jahren Historie – Prognose besonders unsicher.")
    if depot["cash"] >= 25:
        aus.append(f"{depot['cash']:.0f} % Cash: wenig Schwankung, aber geringere Renditechance.")
    return aus


def empfehlungen(bestehende, depot, bewertet, toleranz=1.0):
    """Vergleich bestehender Builder-Positionen mit dem Musterdepot -> je Position Halten / Aufstocken /
    Reduzieren / Austausch pruefen / Neu. Austausch nur bei deutlich schwaecherem Score."""
    def schluessel(x):
        return (str(x.get("wkn") or x.get("isin") or x.get("ticker") or "").upper() or
                "N:" + str(x.get("name") or "").strip().lower())

    ziel = {schluessel(p): p for p in depot["positionen"]}
    score = {schluessel(c): c["score"] for c in bewertet}
    besten = sorted([p["score"] for p in depot["positionen"]] or [0])
    schwelle = besten[0] if besten else 0
    aus = []
    for p in bestehende:
        k = schluessel(p)
        ist = float(p.get("gewicht") or 0.0)
        if k in ziel:
            soll = ziel[k]["gewicht"]
            aktion = "Halten" if abs(ist - soll) <= toleranz else "Aufstocken" if soll > ist else "Reduzieren"
            aus.append({"name": p.get("name"), "aktion": aktion, "ist": ist, "soll": soll, "score": score.get(k)})
        else:
            sc = score.get(k)
            if sc is not None and sc < schwelle - 10:
                aktion = "Austausch prüfen"
            elif sc is None:
                aktion = "Nicht bewertbar (keine Daten)"
            else:
                aktion = "Halten (nicht im Musterdepot)"
            aus.append({"name": p.get("name"), "aktion": aktion, "ist": ist, "soll": 0.0, "score": sc})
    vorhanden = {schluessel(p) for p in bestehende}
    for k, p in ziel.items():
        if k not in vorhanden:
            aus.append({"name": p["name"], "aktion": "Neu", "ist": 0.0, "soll": p["gewicht"], "score": p["score"]})
    return aus


# ---------------------------------------------------------------- Musterdepot (Menue "📦 Musterdepot")
MUSTERDEPOT_NAME = "Investment Scanner Musterdepot"


def musterdepot_eintrag(depot, kapital, kurse, heute, name=MUSTERDEPOT_NAME, profil=""):
    """Musterdepot im Format des Menues "📦 Musterdepot" (planer_ui.render_musterdepot): ganze Stuecke je
    Position zum Kurs von heute, alles Uebrige (Cash-Anteil, Rundung, Werte ohne Kurs) ist Cash.
    kurse = {kennung(p): (instrument_id oder None, kurs_eur)}. -> (eintrag, [Namen ohne Kurs])"""
    pos, ohne = [], []
    for p in depot["positionen"]:
        iid, kurs = (kurse.get(kennung(p)) or (None, None))
        if not kurs or kurs <= 0:
            ohne.append(p["name"])
            continue
        stueck = math.floor(kapital * p["gewicht"] / 100.0 / kurs + 1e-9)
        if stueck <= 0:
            ohne.append(p["name"])
            continue
        pos.append({"name": p["name"], "wkn": p.get("wkn") or "", "isin": p.get("isin") or "",
                    "ticker": p.get("ticker") or "", "instrument_id": iid, "stueck": stueck, "kaufkurs": kurs, "kaufwert": round(stueck * kurs, 2),
                    "gewicht_soll": round(p["gewicht"], 3), "teil_von": None})
    eintrag = {"name": name, "erstellt": heute, "kaufwert": float(kapital),
               "cash": round(float(kapital) - sum(z["kaufwert"] for z in pos), 2), "positionen": pos,
               "quelle": "Investment-Scanner" + (f" · {profil}" if profil else "")}
    return eintrag, ohne


def top500_ids(id_cache, wikifolios):
    """Kurs-IDs (ls-tc) aus den Daten der Top-500-Listen: state/top50_ids.json ({isin | "KAT:wkn": {id, wkn,
    isin}}) und state/top50_wikifolios.json ({"liste": [[id, wkn, name, isin], ...]}).
    -> {WKN/ISIN (gross): instrument_id}"""
    aus = {}
    for schluessel, v in (id_cache or {}).items():
        if not isinstance(v, dict) or not v.get("id"):
            continue
        for k in (v.get("wkn"), v.get("isin"), str(schluessel).replace("KAT:", "")):
            if k:
                aus.setdefault(str(k).upper(), int(v["id"]))
    for z in (wikifolios or {}).get("liste") or []:
        if isinstance(z, (list, tuple)) and len(z) >= 2 and z[0]:
            for k in (z[1], z[3] if len(z) > 3 else None):
                if k:
                    aus.setdefault(str(k).upper(), int(z[0]))
    return aus


def kurse_aus_top500(depot, ids):
    """{kennung(p): (instrument_id oder None, kurs_eur)} - Kurs aus den Top-500-/Watchlist-Daten (p["kurs"],
    Tagesschluss), Kurs-ID aus top500_ids (fuer die spaetere Kursaktualisierung im Musterdepot)."""
    aus = {}
    for p in depot["positionen"]:
        kurs = p.get("kurs")
        if not kurs or kurs <= 0:
            continue
        iid = p.get("instrument_id") or next((ids[k.upper()] for k in (p.get("isin"), p.get("wkn"))
                                               if k and k.upper() in ids), None)
        aus[kennung(p)] = (iid, float(kurs))
    return aus


def musterdepot_name(vorhanden, profil_titel, heute):
    """Neuer, noch freier Name - vorhandene Musterdepots werden nie ueberschrieben."""
    basis = f"Investment Scanner · {profil_titel} · {heute}"
    name, nr = basis, 2
    while name in vorhanden:
        name, nr = f"{basis} ({nr})", nr + 1
    return name


def kurs_fehlt(bewertet, min_score=55, je_klasse=25, alle=False):
    """Kandidaten, die ins Musterdepot kommen koennten (genug Daten, Score >= min_score, je Klasse die besten
    je_klasse), aber keinen Kurs in den Top-500-Daten haben - fuer sie wird der aktuelle Kurs nachgeladen.
    alle: jeder Wert zaehlt (Favoriten), ohne Daten-/Score-Pruefung."""
    aus, n = [], {}
    for c in bewertet:
        if not alle and (not c.get("ausreichend") or (c.get("score") or 0) < min_score):
            continue
        n[c["art"]] = n.get(c["art"], 0) + 1
        if n[c["art"]] <= je_klasse and not (c.get("kurs") or 0) > 0:
            aus.append(c)
    return aus


PLAUSIBEL = {"min_kurs": 1.0, "vola": (3.0, 120.0), "min_dd": -90.0, "max_rendite": 150.0}


def plausibel(c, rendite=None):
    """Datenfehler aussortieren (eingestellte wikifolios mit Kurs 0,006 EUR, Totalverluste, Sprungwerte durch
    Splits, Vola 0 oder ueber 120 %, mehr als 150 % p. a.) - sonst 'erreicht' ein Depot das Ziel nur auf dem Papier
    eines Datenfehlers."""
    p = PLAUSIBEL
    if not (c.get("kurs") or 0) >= p["min_kurs"]:
        return False
    v, dd = c.get("vola"), c.get("maxdd")
    if v is not None and not (p["vola"][0] <= v <= p["vola"][1]):
        return False
    if dd is not None and dd < p["min_dd"]:
        return False
    return rendite is None or rendite <= p["max_rendite"]


def ziel_depot(bewertet, benoetigt, max_gewicht=5.0, max_je_branche=3, tagesgeld=None):
    """'Zielrendite'-Depot: so zusammengestellt, dass es das Ziel RECHNERISCH erreicht - nach der vergangenen
    Rendite p. a. der Werte (nicht nach der vorsichtigen Prognose). Bewusst renditemaximierend und damit
    riskant: Werte mit Kurs, deren bisherige Rendite p. a. (laengster Zeitraum) die noetige schon erreicht hat -
    lange Historie (mind. 3 J.) vor kurzer, jeweils nach Score; reicht das nicht fuer 100 %, die renditestaerksten
    uebrigen. Gleich gewichtet mit max_gewicht je Wert, ohne Cash, je Branche hoechstens max_je_branche Aktien.
    -> depot (wie musterdepot) + "hist_rendite" (% p. a., gewichtet) + "erreicht" (>= benoetigt)"""
    max_gewicht = max(float(max_gewicht), 0.5)
    n = int(math.ceil(100.0 / max_gewicht - 1e-9))

    kand, gesehen = [], set()
    for c in bewertet:
        r, j = hist_rendite(c)
        if r is None or j < 1 or not plausibel(c, r):
            continue
        schluessel = {k.upper() for k in (c.get("isin"), c.get("wkn")) if k} or {c["name"].lower()}
        if schluessel & gesehen:
            continue                                  # derselbe Wert aus zwei Quellen
        gesehen |= schluessel
        kand.append((r, j, c))
    ziel = benoetigt if benoetigt is not None else float("-inf")
    # Reihenfolge: erst Werte, die die noetige Rendite schon geschafft haben - mit langer Historie (mind. 3 J.)
    # vor kurzer, jeweils nach Score; erst danach (falls noetig) die renditestaerksten uebrigen
    def ruhig(k):                                     # Score, dann geringere Schwankung, dann laengere Historie
        return (-(k[2].get("score") or 0), k[2].get("vola") or 999.0, -k[1])
    reihe = (sorted([k for k in kand if k[0] >= ziel and k[1] >= 3], key=ruhig)
             + sorted([k for k in kand if k[0] >= ziel and k[1] < 3], key=ruhig)
             + sorted([k for k in kand if k[0] < ziel], key=lambda k: -k[0]))
    gew, branchen = [], {}
    for r, j, c in reihe:
        if c["art"] == "aktie" and c.get("branche"):
            if branchen.get(c["branche"], 0) >= max_je_branche:
                continue
            branchen[c["branche"]] = branchen.get(c["branche"], 0) + 1
        gew.append((r, j, c))
        if len(gew) >= n:
            break
    if not gew:
        return {"positionen": [], "cash": 100.0, "max_gewicht": max_gewicht, "hinweise": [], "hist_rendite": None,
                "erreicht": False}
    w = min(max_gewicht, 100.0 / len(gew))
    pos = []
    for r, j, c in gew:
        p = copy.deepcopy(c)
        p["gewicht"] = w
        p["prognose"] = dict(p.get("prognose") or {}, mu=r, sigma=vola(c)[0])
        p["hist"], p["hist_jahre"] = r, j
        pos.append(p)
    cash = max(100.0 - w * len(pos), 0.0)
    hist = sum(w / 100.0 * r for r, _, _ in gew) + cash / 100.0 * ANNAHMEN["tagesgeld"]
    hinweise = [] if cash < 0.01 else [f"Nur {len(pos)} Werte mit Kurs und Historie – {cash:.1f} % bleiben Cash."]
    return {"positionen": pos, "cash": cash, "max_gewicht": max_gewicht, "hinweise": hinweise, "hist_rendite": hist,
            "erreicht": benoetigt is not None and hist >= benoetigt}


# ---------------------------------------------------------------- Depot-Tabelle (Anzeige und PDF)
def _de1(x, vorzeichen=False):
    return (f"{x:+.1f}" if vorzeichen else f"{x:.1f}").replace(".", ",")


def begruendung(p, basis="modell", benoetigt=None):
    """Warum der Wert im Depot ist - fuer jede Position, aus den Daten abgeleitet (Score, Rendite, Chancen) und mit
    dem wichtigsten Risiko. basis "historisch": Zielrendite-Depot (bisherige Rendite gegen die noetige)."""
    teile = []
    if p.get("score") is not None:
        teile.append(f"Score {p['score']}")
    r, j = hist_rendite(p) if p.get("perf") else (p.get("hist"), p.get("hist_jahre") or 0)
    if basis == "historisch" and r is not None:
        txt = f"bisher {_de1(r, True)} % p. a. über {j:.0f} J."
        if benoetigt is not None:
            txt += f" – {'über' if r >= benoetigt else 'unter'} den nötigen {_de1(benoetigt)} %"
        teile.append(txt)
    if p.get("chancen") is not None and p.get("risiken") is not None:
        chancen, risiken = p["chancen"], p["risiken"]
    else:
        chancen, risiken = _chancen_risiken(dict(p, hist=r, hist_jahre=j))
    teile += chancen[:2]
    if basis != "historisch" and r is not None and not any("Rendite" in t for t in teile):
        teile.append(f"bisher {_de1(r, True)} % p. a. ({j:.0f} J.)")
    if not teile:
        teile.append(f"Erwartung der Klasse {KLASSEN.get(p.get('art'), '')} (wenig Daten)")
    if risiken:
        teile.append("Risiko: " + risiken[0])
    return " · ".join(teile)


def depot_zeilen(depot, kapital, basis="modell", benoetigt=None):
    """Einheitliche Zeilen fuer beide Musterdepots (Modell-Prognose oder bisherige Rendite):
    -> [{name, art, gewicht, betrag, rendite, grundlage, beitrag, kennung, grund, typ}] inkl. Cash und Summe"""
    zeilen = []
    for p in sorted(depot["positionen"], key=lambda p: (list(KLASSEN).index(p["art"]), -(p.get("score") or 0))):
        mu = p["prognose"]["mu"]
        grundlage = (f"bisher, {p.get('hist_jahre') or 0:.0f} J." if basis == "historisch" else "Prognose")
        zeilen.append({"typ": "wert", "name": p["name"], "art": p["art"], "gewicht": p["gewicht"],
                       "betrag": kapital * p["gewicht"] / 100.0, "rendite": mu, "grundlage": grundlage,
                       "beitrag": p["gewicht"] / 100.0 * mu,
                       "kennung": p.get("isin") or p.get("wkn") or p.get("ticker") or "–",
                       "grund": begruendung(p, basis, benoetigt)})
    tg = ANNAHMEN["tagesgeld"]
    if depot["cash"] > 0.01 or basis != "historisch":
        zeilen.append({"typ": "cash", "name": "Cash / Tagesgeld", "art": "cash", "gewicht": depot["cash"],
                       "betrag": kapital * depot["cash"] / 100.0, "rendite": tg, "grundlage": "Annahme",
                       "beitrag": depot["cash"] / 100.0 * tg, "kennung": "–",
                       "grund": "Puffer für Entnahmen und Schwankungen, nicht verteilbarer Rest"})
    summe = sum(z["gewicht"] for z in zeilen)
    zeilen.append({"typ": "summe", "name": "Summe", "art": "", "gewicht": summe, "betrag": kapital * summe / 100.0,
                   "rendite": None, "grundlage": "", "beitrag": sum(z["beitrag"] for z in zeilen), "kennung": "",
                   "grund": ""})
    return zeilen
