"""Investment Scanner 2.0 - Rechenkern (ohne Streamlit).

Nachbau des eigenstaendigen HTML-Scanners "Investment Scanner - Echtdaten & Entnahmeplanung (Version 3)"
mit den Daten der App statt Yahoo/CORS-Proxy: Universum aus den Top-500-/Watchlist-Daten (Kurs, 12-Monats-
Rendite, Schwankung, Drawdown), Qualitaets-Score und KGV der Aktien aus dem Qualitaets-Agenten.

- Kombinierter Investment-Score 0-100 (Momentum 25, Risiko 25, Qualitaet 20, Kosten/Bewertung 15,
  Liquiditaet 10, Depot-Ergaenzung 5). Fehlende Faktoren werden NICHT geschaetzt, sie senken die
  Datenabdeckung; Score erst ab 60 % Abdeckung der Marktfaktoren und vorhandener Risikokennzahl.
- Drei Depotstrategien (Defensiv / Ausgewogen / Wachstum) mit Kaufplan in ganzen Stuecken,
  Nachkaufreserve, Hoechstgewicht je Wertpapier, Ordergebuehr.
- Sofortentnahme (zuerst aus neuem Geld, sonst Verkaufsvorschlaege aus dem vorhandenen Depot) und
  regelmaessige Monatsentnahmen in der Zielrechnung.
Szenariorechnung, keine Prognose und keine Anlageberatung."""
import csv
import io
import math
import re

from scanner import _HEBEL, PLAUSIBEL

TYPES = ["ETF", "Aktie", "Wikifolio", "Anleihe", "Gold", "Fonds", "Geldmarkt"]
COLORS = {"ETF": "#52d9b3", "Aktie": "#86b1f1", "Wikifolio": "#cf9cf2", "Anleihe": "#f3c47b", "Gold": "#eedc85",
          "Fonds": "#5ea2a8", "Geldmarkt": "#92a8b2", "Liquidität": "#536e80"}
PROFILES = {
    "defensiv": {"name": "Defensiv", "hint": "Stabilität im Fokus",
                 "weights": {"ETF": 25, "Aktie": 5, "Wikifolio": 0, "Anleihe": 40, "Gold": 10, "Fonds": 8,
                             "Geldmarkt": 12}},
    "ausgewogen": {"name": "Ausgewogen", "hint": "Breite Streuung",
                   "weights": {"ETF": 45, "Aktie": 22, "Wikifolio": 5, "Anleihe": 13, "Gold": 7, "Fonds": 5,
                               "Geldmarkt": 3}},
    "wachstum": {"name": "Wachstum", "hint": "Größere Schwankungen",
                 "weights": {"ETF": 40, "Aktie": 35, "Wikifolio": 12, "Anleihe": 0, "Gold": 5, "Fonds": 8,
                             "Geldmarkt": 0}},
}
STANDARD_RENDITE = {"defensiv": 2.0, "ausgewogen": 5.0, "wachstum": 8.0}     # % p. a., Szenarioannahmen
SCORE_WEIGHTS = {"Momentum": 25, "Risiko": 25, "Qualität": 20, "Kosten / Bewertung": 15, "Liquidität": 10,
                 "Depot-Ergänzung": 5}
MARKT_GEWICHT = 95                              # Summe ohne Depot-Ergaenzung
MIN_ABDECKUNG = 57                              # 60 % von 95
_TYP_ALIAS = {"etf": "ETF", "etp": "ETF", "etc": "Gold", "aktie": "Aktie", "stock": "Aktie", "wikifolio": "Wikifolio",
              "anleihe": "Anleihe", "bond": "Anleihe", "gold": "Gold", "fonds": "Fonds", "fund": "Fonds",
              "geldmarkt": "Geldmarkt", "money": "Geldmarkt"}


def _z(x):
    """Zahl oder None (auch "1.234,5" / "12,5")."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x) if math.isfinite(x) else None
    s = str(x).strip().replace("−", "-").replace("%", "").replace("€", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def kanon_typ(t):
    t = str(t or "").strip()
    if t in TYPES:
        return t
    return next((v for k, v in _TYP_ALIAS.items() if k in t.lower()), None)


# ---------------------------------------------------------------- Universum aus den App-Daten
def universum(katalog_teile, qualitaet=None, isin_je_symbol=None, stand="", alle_aktien=None):
    """Top-500-/Watchlist-Katalog (state/planer/katalog_gross_*.json) -> Wertpapierliste im Schema des Scanners.
    qualitaet = {symbol: {gesamt, fkgv, br, ...}}, isin_je_symbol = {symbol: isin},
    alle_aktien = {symbol: {kennung, 3M, ...}} (Index-Listen, state/top50_alle_*.json: Kennung wie im Katalog und
    3-Monats-Rendite). Quellenrang = Rang nach 12-Monats-Rendite im gesamten Universum (wie die Top-Listen)."""
    alle_aktien = alle_aktien or {}
    q_je_isin, q_je_kennung, drei_m = {}, {}, {}
    for sym, w in alle_aktien.items():
        kenn = str((w or {}).get("kennung") or "").strip().upper()
        if kenn and _z((w or {}).get("3M")) is not None:
            drei_m[kenn] = _z(w["3M"])
    for sym, q in (qualitaet or {}).items():
        if not isinstance(q, dict):
            continue
        isin = (isin_je_symbol or {}).get(sym)
        if isin:
            q_je_isin[isin.upper()] = q
        kenn = str((alle_aktien.get(sym) or {}).get("kennung") or "").strip().upper()
        if kenn:
            q_je_kennung[kenn] = q
    aus, gesehen = [], set()
    for d in katalog_teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            w = dict(zip(felder, z))
            typ = kanon_typ(w.get("typ"))
            kurs = _z(w.get("kurs"))
            name = str(w.get("name") or "").strip()
            if not typ or not name or not kurs or kurs <= 0:
                continue
            # Hebel-/Short-/Daily-Produkte und Datenfehler (Kurs < 1 EUR, Vola 0 oder > 120 %, Drawdown < -90 %,
            # mehr als 150 % in 12 Monaten) - wie im Investment-Scanner
            vola, dd_roh, r12 = _z(w.get("vola")), _z(w.get("maxdd")), _z(w.get("1J"))
            if (_HEBEL.search(name) or kurs < PLAUSIBEL["min_kurs"]
                    or (vola is not None and not PLAUSIBEL["vola"][0] <= vola <= PLAUSIBEL["vola"][1])
                    or (dd_roh is not None and -abs(dd_roh) < PLAUSIBEL["min_dd"])
                    or (r12 is not None and r12 > PLAUSIBEL["max_rendite"])):
                continue
            isin = str(w.get("isin") or "").strip().upper()
            kennung = str(w.get("kennung") or "").strip().upper()
            wid = isin or kennung
            if not wid or wid in gesehen:
                continue
            gesehen.add(wid)
            q = (q_je_isin.get(isin) if isin else None) or (q_je_kennung.get(kennung) if typ == "Aktie" else None)
            dd = _z(w.get("maxdd"))
            aus.append({"id": wid, "isin": isin, "wkn": kennung if re.match(r"^(?=.*\d)[A-Z0-9]{6}$", kennung) else "",
                        "name": name, "type": typ, "price": kurs, "rank": None, "currency": "EUR",
                        "sector": str((q or {}).get("br") or w.get("kat") or ""), "asOf": stand,
                        "return12mPct": _z(w.get("1J")),
                        "return3mPct": drei_m.get(kennung) if typ == "Aktie" else None,
                        "volatility12mPct": _z(w.get("vola")), "maxDrawdown12mPct": -abs(dd) if dd is not None else None,
                        "qualityScore": _z((q or {}).get("gesamt")),
                        "annualCostPct": None, "peRatio": _z((q or {}).get("fkgv")) if typ == "Aktie" else None,
                        "volumeEur": None, "spreadPct": None, "source": "Top-500-Daten"})
    rang = sorted((a for a in aus if a["return12mPct"] is not None), key=lambda a: -a["return12mPct"])
    for i, a in enumerate(rang):
        a["rank"] = i + 1
    return aus


# ---------------------------------------------------------------- CSV-Import (wie im HTML-Scanner)
def _csv_zeilen(text):
    text = text.lstrip("﻿")
    trenner = ";" if text.split("\n", 1)[0].count(";") >= text.split("\n", 1)[0].count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=trenner))


def katalog_aus_csv(text):
    """Wertpapier-CSV (id;name;type;price;rank;currency;sector;asOf;return12mPct;...) -> (liste, fehler).
    Pflicht: id, name, type, positiver price in EUR. Nichts wird geschaetzt."""
    aus, fehler = [], []
    for i, r in enumerate(_csv_zeilen(text), start=2):
        r = {str(k or "").strip(): v for k, v in r.items()}
        typ, preis = kanon_typ(r.get("type")), _z(r.get("price"))
        if str(r.get("currency") or "EUR").strip().upper() != "EUR":
            fehler.append(f"Zeile {i}: Währung nicht EUR – übersprungen")
            continue
        if not r.get("id") or not r.get("name") or not typ or not preis or preis <= 0:
            fehler.append(f"Zeile {i}: id, name, type oder positiver price fehlt – übersprungen")
            continue
        aus.append({"id": str(r["id"]).strip(), "isin": "", "wkn": "", "name": str(r["name"]).strip(), "type": typ,
                    "price": preis, "rank": _z(r.get("rank")), "currency": "EUR",
                    "sector": str(r.get("sector") or ""), "asOf": str(r.get("asOf") or ""),
                    **{k: _z(r.get(k)) for k in ("return12mPct", "return3mPct", "volatility12mPct",
                                                 "maxDrawdown12mPct", "qualityScore", "annualCostPct", "peRatio",
                                                 "volumeEur", "spreadPct")},
                    "source": "CSV (ungeprüft)"})
    return aus, fehler


def depot_aus_csv(text):
    """Bestandsdepot-CSV (id;name;type;shares;price) -> (liste, fehler)."""
    aus, fehler = [], []
    for i, r in enumerate(_csv_zeilen(text), start=2):
        r = {str(k or "").strip(): v for k, v in r.items()}
        typ, stueck, preis = kanon_typ(r.get("type")), _z(r.get("shares")), _z(r.get("price"))
        if not r.get("id") or not typ or not stueck or stueck <= 0 or not preis or preis <= 0:
            fehler.append(f"Zeile {i}: id, type, shares oder price fehlt – übersprungen")
            continue
        aus.append({"id": str(r["id"]).strip(), "name": str(r.get("name") or r["id"]).strip(), "type": typ,
                    "shares": stueck, "price": preis})
    return aus, fehler


def csv_text(zeilen):
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";")
    for z in zeilen:
        w.writerow(["" if v is None else (f"{v:.2f}".replace(".", ",") if isinstance(v, float) else v) for v in z])
    return puffer.getvalue()


CSV_VORLAGE_WERTPAPIERE = ("id;name;type;price;rank;currency;sector;asOf;return12mPct;return3mPct;volatility12mPct;"
                           "maxDrawdown12mPct;qualityScore;annualCostPct;peRatio;volumeEur;spreadPct\n")
CSV_VORLAGE_DEPOT = "id;name;type;shares;price\n"


# ---------------------------------------------------------------- Score
def scored_value(value, low, high, higher_better=True):
    if value is None or not math.isfinite(value):
        return None
    x = (value - low) / (high - low) if higher_better else (high - value) / (high - low)
    return max(0.0, min(100.0, x * 100.0))


def average_known(values):
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def calc_score(a, snapshot, sektor_je_id=None):
    """-> {value, coverage, details, hasRisk} (value None ohne ausreichende Daten)."""
    sektor_je_id = sektor_je_id or {}
    summe = sum(h["price"] * h["shares"] for h in snapshot)
    klasse = sum(h["price"] * h["shares"] for h in snapshot if h["type"] == a["type"])
    sektor = sum(h["price"] * h["shares"] for h in snapshot
                 if a.get("sector") and a["sector"] == sektor_je_id.get(h["id"]))
    fit = 100.0
    if any(h["id"] == a["id"] for h in snapshot):
        fit -= 25
    if summe > 0 and klasse / summe > 0.45:
        fit -= 20
    if summe > 0 and sektor / summe > 0.35:
        fit -= 15
    momentum = average_known([scored_value(a.get("return12mPct"), -30, 30), scored_value(a.get("return3mPct"), -12, 12)])
    dd = a.get("maxDrawdown12mPct")
    risiko = average_known([scored_value(a.get("volatility12mPct"), 5, 60, False),
                            scored_value(abs(dd) if dd is not None else None, 0, 55, False)])
    qualitaet = scored_value(a.get("qualityScore"), 0, 100)
    kosten = (scored_value(a.get("peRatio"), 8, 45, False) if a["type"] == "Aktie"
              else scored_value(a.get("annualCostPct"), 0, 3, False))
    vol = a.get("volumeEur")
    volumen = scored_value(math.log10(vol), 4, 7) if vol and vol > 0 else None
    liquiditaet = average_known([volumen, scored_value(a.get("spreadPct"), 0, 2, False)])
    details = {"Momentum": momentum, "Risiko": risiko, "Qualität": qualitaet, "Kosten / Bewertung": kosten,
               "Liquidität": liquiditaet, "Depot-Ergänzung": fit}
    komp = [(k, v) for k, v in details.items() if k != "Depot-Ergänzung" and v is not None]
    abgedeckt = sum(SCORE_WEIGHTS[k] for k, _ in komp)
    genug = abgedeckt >= MIN_ABDECKUNG and risiko is not None
    markt = sum(SCORE_WEIGHTS[k] * v for k, v in komp) / abgedeckt if genug else None
    wert = round(markt * 0.95 + fit * 0.05, 1) if genug else None
    return {"value": wert, "coverage": round(1000 * abgedeckt / MARKT_GEWICHT) / 10, "details": details,
            "hasRisk": risiko is not None}


def rangliste(katalog, snapshot, modus="score"):
    """Alle Werte mit Kurs, bewertet und sortiert (Score absteigend, ohne Score nach Quellenrang)."""
    sektor_je_id = {a["id"]: a.get("sector") for a in katalog}
    liste = [dict(a, score=calc_score(a, snapshot, sektor_je_id)) for a in katalog if (a.get("price") or 0) > 0]

    def nach_rang(a):
        return (a["rank"] if a.get("rank") is not None else float("inf"), a["id"])

    if modus == "rank":
        liste.sort(key=nach_rang)
    else:
        liste.sort(key=lambda a: (a["score"]["value"] is None, -(a["score"]["value"] or 0), *nach_rang(a)))
    for i, a in enumerate(liste):
        a["scannerRank"], a["combinedScore"] = i + 1, a["score"]["value"]
    return liste


# ---------------------------------------------------------------- Zahlungsstroeme
def simulate_flows(investiert, cash, monate, sparrate, rate, inp, mit_plan=False):
    a, c, gezahlt, luecke, erste_luecke, plan = max(0.0, investiert), max(0.0, cash), 0.0, 0.0, None, []
    rm = rate / 12.0
    for m in range(1, monate + 1):
        a = max(0.0, a * (1 + rm)) + sparrate
        faellig = (inp["takeMonthly"] if inp and inp["takeMonthly"] > 0 and m >= inp["takeStart"]
                   and (inp["takeEnd"] == 0 or m <= inp["takeEnd"]) else 0.0)
        if faellig:
            aus_cash = min(c, faellig)
            c -= aus_cash
            aus_depot = min(a, faellig - aus_cash)
            a -= aus_depot
            bezahlt = aus_cash + aus_depot
            gap = max(0.0, faellig - bezahlt)
            gezahlt += bezahlt
            if gap > 1e-4:
                luecke += gap
                erste_luecke = erste_luecke or m
            if mit_plan:
                plan.append({"month": m, "due": faellig, "fromCash": aus_cash, "fromAsset": aus_depot,
                             "paid": bezahlt, "gap": gap, "cashEnd": c, "investedEnd": a})
    return {"value": a + c, "paid": gezahlt, "shortfall": luecke, "firstShortfall": erste_luecke, "cash": c,
            "invested": a, "schedule": plan}


def required_rate(investiert, cash, monate, sparrate, ziel, inp):
    """Noetige Modellrendite p. a. (Dezimal) fuer den Zielwert, None wenn nicht erreichbar (> 300 %)."""
    if ziel <= 0:
        return 0.0
    if investiert <= 0 and sparrate <= 0:
        return None

    def v(x):
        return simulate_flows(investiert, cash, monate, sparrate, x, inp)["value"]

    lo, hi = -0.9, 3.0
    if v(lo) > ziel:
        return lo
    if v(hi) < ziel:
        return None
    for _ in range(85):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if v(mid) < ziel else (lo, mid)
    return (lo + hi) / 2


def sofortentnahme(inp, snapshot):
    """Sofortauszahlung zuerst aus neuem Kapital, sonst Verkaufsvorschlaege (ganze Stuecke, nach Positionswert)."""
    rest, cash = max(0.0, inp["takeNow"]), inp["capital"]
    aus_kapital = min(cash, rest)
    cash -= aus_kapital
    rest -= aus_kapital
    verkaeufe, danach, gebuehren = [], [dict(h) for h in snapshot], 0.0
    for h in sorted(danach, key=lambda h: -(h["shares"] * h["price"])):
        if rest <= 1e-5:
            break
        max_stk = math.floor(h["shares"] + 1e-9)
        if not h["price"] or h["price"] <= 0 or max_stk < 1:
            continue
        stk = min(max_stk, math.ceil((rest + inp["fee"]) / h["price"]))
        if stk * h["price"] - inp["fee"] <= 0:
            continue
        brutto = stk * h["price"]
        netto = max(0.0, brutto - inp["fee"])
        h["shares"] = max(0.0, h["shares"] - stk)
        cash += netto
        rest = max(0.0, rest - netto)
        verkaeufe.append(dict(h, shares=stk, gross=brutto, net=netto, fee=inp["fee"]))
        gebuehren += inp["fee"]
    bezahlt = min(inp["takeNow"], aus_kapital + sum(v["net"] for v in verkaeufe))
    cash_danach = max(0.0, cash - max(0.0, inp["takeNow"] - aus_kapital))
    return {"paid": bezahlt, "gap": max(0.0, inp["takeNow"] - bezahlt), "fromCapital": aus_kapital,
            "sales": verkaeufe, "fees": gebuehren, "cashAfter": cash_danach,
            "snapshot": [h for h in danach if h["shares"] > 1e-6]}


# ---------------------------------------------------------------- Kaufplan je Strategie
def model_plan(profil, inp, verfuegbar, snapshot, typen, rate_pct):
    bestand = sum(h["shares"] * h["price"] for h in snapshot)
    reserve = inp["capital"] * inp["reservePct"] / 100.0
    budget = inp["capital"] - reserve
    depot = bestand + inp["capital"]
    geeignet = [a for a in verfuegbar if a["type"] in typen]
    gewaehlt = {a["type"] for a in geeignet}
    roh = {t: (PROFILES[profil]["weights"].get(t, 0) if t in gewaehlt else 0) for t in TYPES}
    nenner = sum(roh.values())
    if nenner <= 0:
        for t in gewaehlt:
            roh[t] = 1
        nenner = sum(roh.values())
    anteile = {t: (roh[t] / nenner if nenner else 0.0) for t in TYPES}
    vorhanden = {t: sum(h["shares"] * h["price"] for h in snapshot if h["type"] == t) for t in TYPES}
    ziel_gesamt = bestand + budget
    defizit = {t: (max(0.0, ziel_gesamt * anteile[t] - vorhanden[t]) if anteile[t] > 0 else 0.0) for t in TYPES}
    dsum = sum(defizit.values())
    budgets = {t: (budget * defizit[t] / dsum if dsum > 0 else 0.0) for t in TYPES}
    je_id = {h["id"]: h for h in snapshot}
    orders, ausgegeben, gebuehren = [], 0.0, 0.0
    for t in TYPES:
        kb = budgets[t]
        if kb <= 0.01:
            continue
        gruppe = [a for a in geeignet if a["type"] == t][:min(4, len(geeignet))]
        if not gruppe:
            continue
        eintr = []
        for i, a in enumerate(gruppe):
            h = je_id.get(a["id"])
            eintr.append({"a": a, "qty": 0, "target": 0.0, "base": (h["shares"] * h["price"]) if h else 0.0,
                          "score": (0.35 + 0.65 * a["combinedScore"] / 100.0) if a.get("combinedScore") is not None
                          else 1.0 / (1 + i * 0.6)})
        ssum = sum(e["score"] for e in eintr)
        for e in eintr:
            e["target"] = kb * e["score"] / ssum
        frei = {"left": kb}

        def kaufen(e, menge):
            nonlocal ausgegeben, gebuehren
            if menge < 1:
                return False
            gebuehr = inp["fee"] if e["qty"] == 0 else 0.0
            kosten = menge * e["a"]["price"] + gebuehr
            if kosten > frei["left"] + 1e-6 or kosten > budget - ausgegeben + 1e-6:
                return False
            e["qty"] += menge
            frei["left"] -= kosten
            ausgegeben += kosten
            gebuehren += gebuehr
            return True

        def max_stk(e):
            return max(0, math.floor((depot * inp["maxLinePct"] / 100.0 - e["base"] - e["qty"] * e["a"]["price"] + 1e-8)
                                     / e["a"]["price"]))

        for e in eintr:
            p = e["a"]["price"]
            kaufen(e, min(max_stk(e), math.floor(max(0.0, e["target"] - inp["fee"]) / p),
                          math.floor(max(0.0, frei["left"] - inp["fee"]) / p)))
        for _ in range(3000):                    # Rest in ganzen Stuecken nach Soll-Abweichung verteilen
            kann = [e for e in eintr if max_stk(e) > 0
                    and e["a"]["price"] + (0 if e["qty"] else inp["fee"]) <= frei["left"] + 1e-6]
            if not kann:
                break
            kann.sort(key=lambda e: -((e["target"] - e["qty"] * e["a"]["price"]) / e["a"]["price"]))
            if not kaufen(kann[0], 1):
                break
        orders += [dict(e["a"], shares=e["qty"], amount=e["qty"] * e["a"]["price"], fee=inp["fee"],
                        priorValue=e["base"]) for e in eintr if e["qty"] > 0]
    orders.sort(key=lambda o: -o["amount"])
    neu = sum(o["amount"] for o in orders)
    cash = max(0.0, inp["capital"] - neu - gebuehren)
    investiert = bestand + neu
    ist = dict(vorhanden)
    for o in orders:
        ist[o["type"]] += o["amount"]
    rate = max(-20.0, min(40.0, rate_pct)) / 100.0
    monate = round(inp["years"] * 12)
    flow = simulate_flows(investiert, cash, monate, inp["monthly"], rate, inp, True)
    return {"profile": profil, "existingValue": bestand, "deposit": depot, "investBudget": budget, "reserve": reserve,
            "investedNew": neu, "cash": cash, "fees": gebuehren, "orders": orders, "rate": rate,
            "projection": flow["value"],
            "neededRate": required_rate(investiert, cash, monate, inp["monthly"], inp["goal"], inp),
            "flow": flow, "ratios": anteile, "actualCat": ist, "eligibleCount": len(geeignet), "months": monate}


def eingaben(capital=0.0, goal=0.0, years=10, monthly=0.0, reservePct=0.0, maxLinePct=100.0, fee=0.0,
             riskCeiling="wachstum", takeNow=0.0, takeMonthly=0.0, takeStart=1, takeEnd=0):
    """Eingaben pruefen/begrenzen (wie userInputs() im HTML-Scanner)."""
    return {"capital": max(0.0, float(capital or 0)), "goal": max(0.0, float(goal or 0)),
            "years": int(min(max(int(years or 1), 1), 50)), "monthly": max(0.0, float(monthly or 0)),
            "reservePct": min(max(float(reservePct or 0), 0.0), 95.0),
            "maxLinePct": min(max(float(maxLinePct or 100), 1.0), 100.0), "fee": max(0.0, float(fee or 0)),
            "riskCeiling": riskCeiling if riskCeiling in PROFILES else "wachstum",
            "takeNow": max(0.0, float(takeNow or 0)), "takeMonthly": max(0.0, float(takeMonthly or 0)),
            "takeStart": max(1, int(takeStart or 1)), "takeEnd": max(0, int(takeEnd or 0))}


def berechnen(roh, katalog, bestand, typen, modus="auto", rangmodus="score", top_n=100, renditen=None):
    """Gesamtrechnung (build() im HTML-Scanner). modus: "auto" oder ein Profil.
    -> {inp, available, snapshot, plans, active, auto, wd, raw}"""
    renditen = dict(STANDARD_RENDITE, **(renditen or {}))
    je_id = {a["id"]: a for a in katalog}
    snapshot = [dict(h, price=(je_id.get(h["id"]) or {}).get("price") or h["price"],
                     name=(je_id.get(h["id"]) or {}).get("name") or h["name"],
                     type=(je_id.get(h["id"]) or {}).get("type") or h["type"]) for h in bestand or []]
    wd = sofortentnahme(roh, snapshot)
    inp = dict(roh, capital=wd["cashAfter"])
    # Scan-Limit je Anlageklasse: ETFs und wikifolios haben in den Top-500-Daten keine Kosten-/Liquiditaets-
    # kennzahlen (meist kein Score) - ein gemeinsames Limit fuellten sonst allein bewertete Aktien
    gezaehlt, verfuegbar = {}, []
    for a in rangliste(katalog, wd["snapshot"], rangmodus):
        gezaehlt[a["type"]] = gezaehlt.get(a["type"], 0) + 1
        if gezaehlt[a["type"]] <= top_n:
            verfuegbar.append(a)
    plans = {k: model_plan(k, inp, verfuegbar, wd["snapshot"], typen, renditen[k]) for k in PROFILES}
    reihe = list(PROFILES)
    erlaubt = reihe[:reihe.index(inp["riskCeiling"]) + 1]
    auto = next((k for k in erlaubt if plans[k]["projection"] >= inp["goal"]), erlaubt[-1])
    return {"inp": inp, "available": verfuegbar, "snapshot": wd["snapshot"], "plans": plans,
            "active": auto if modus == "auto" else modus, "auto": auto, "wd": wd, "raw": roh}


def kaufplan_csv(erg):
    m, inp = erg["plans"][erg["active"]], erg["inp"]
    z = [["Score_Rang", "Quellenrang", "Investment_Score_0_bis_100", "Score_Datenabdeckung_Prozent", "ID/ISIN", "Name",
          "Typ", "Kurs_EUR", "Stueck", "Betrag_EUR", "Kaufanteil_Prozent_Neukapital", "Kaufanteil_Prozent_Gesamtdepot",
          "Ordergebuehr_EUR", "Datenquelle"]]
    for o in m["orders"]:
        z.append([o["scannerRank"], o.get("rank") or "", o.get("combinedScore") or "", o["score"]["coverage"], o["id"],
                  o["name"], o["type"], float(o["price"]), o["shares"], float(o["amount"]),
                  float(o["amount"] / max(inp["capital"], 1) * 100), float(o["amount"] / max(m["deposit"], 1) * 100),
                  float(o["fee"]), o.get("source", "")])
    for text, betrag in (("Kaufplan nur Simulation", m["investedNew"]), ("Nachkaufreserve", m["reserve"]),
                         ("Restliquidität (inkl. Reserve)", m["cash"])):
        z.append(["", "", "", "", "", text, "", "", "", float(betrag), "", "", "", ""])
    return csv_text(z)


def entnahmeplan_csv(erg):
    z = [["Strategie", "Monat", "Soll_EUR", "aus_Liquiditaet_EUR", "aus_Depot_EUR", "ausgezahlt_EUR",
          "Fehlbetrag_EUR", "Restliquiditaet_EUR", "Restdepot_EUR"]]
    for k, m in erg["plans"].items():
        for s in m["flow"]["schedule"]:
            z.append([PROFILES[k]["name"], s["month"], float(s["due"]), float(s["fromCash"]), float(s["fromAsset"]),
                      float(s["paid"]), float(s["gap"]), float(s["cashEnd"]), float(s["investedEnd"])])
    wd = erg["wd"]
    for v in wd["sales"]:
        z.append(["Sofort-Verkauf " + v["name"], 0, "", "", "", float(v["net"]), "", "", ""])
    return csv_text(z)
