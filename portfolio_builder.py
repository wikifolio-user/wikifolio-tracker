"""Portfolio Builder 2.0 - Rechenkern (ohne Streamlit, vollstaendig testbar).

Begriffe
- Eigenkapital      = Anfangskapital + sonstiges Kapital
- Anlagekapital     = Eigenkapital + Kreditsumme (der Kredit wird mit angelegt)
- Netto-Vermoegen   = Portfoliowert - Restschuld. Der Kredit steckt damit im Portfolio,
                      wird aber als Schuld wieder abgezogen - er zaehlt nie doppelt.

Monatliche Simulation (Monat 1 .. n), Reihenfolge je Monat:
1. Kredit: Zinsen = Restschuld x Zins p.a. / 12 (nominal, wie bei Annuitaetendarlehen ueblich);
   gezahlt wird die Rate, im letzten Monat nur noch der Rest (Restschuld + Zinsen).
2. Netto-Cashflow = Einzahlung - Entnahme - Ausgaben - gezahlte Kreditrate.
3. Portfolio = Portfolio x (1 + r_monat) + Netto-Cashflow, mit r_monat = (1 + r_jahr)^(1/12) - 1
   (Rendite p.a. als effektiver Jahreszins, d. h. 12 Monate ergeben genau r_jahr).
4. Faellt das Portfolio unter 0, bleibt es bei 0; der fehlende Betrag wird als Fehlbetrag gezaehlt
   (er muesste von aussen kommen).
"""
import copy
import math

MAX_MONATE = 600            # 50 Jahre
MAX_KAPITAL = 1e9
MAX_MONATLICH = 1e7
MAX_KREDITZINS = 30.0       # % p. a.
MAX_RENDITE = 50.0          # % p. a. (+/-)
EPS = 1e-9

# Art je Position (fuer Auswahl, Anzeige und Aufteilung nach Art)
ARTEN = {"aktie": "Aktie", "etf": "ETF / ETP", "wikifolio": "Wikifolio", "krypto": "Krypto",
         "sonstig": "Sonstiges"}

STANDARD = {
    "anfangskapital": 10000.0,
    "sonstiges_kapital": 0.0,
    "kredit_summe": 0.0,
    "kredit_zins_pa": 4.0,          # %
    "kredit_rate": 0.0,             # EUR je Monat
    "einzahlung": 300.0,            # EUR je Monat
    "entnahme": 0.0,
    "ausgaben": 0.0,
    "laufzeit": 10,
    "laufzeit_einheit": "Jahre",    # "Jahre" | "Monate"
    "rendite_pa": 6.0,              # % - fuer Positionen ohne eigene Rendite und den Cash-Rest
    "zielvermoegen": 0.0,           # EUR netto am Ende (0 = kein Ziel)
    "auto_ziel": False,             # Gewichte automatisch so verteilen, dass das Ziel erreicht wird
    "nur_ganze_stuecke": False,
    "positionen": [
        {"name": "MSCI World ETF", "kurs": 100.0, "gewicht": 60.0, "art": "etf"},
        {"name": "Emerging Markets ETF", "kurs": 30.0, "gewicht": 20.0, "art": "etf"},
        {"name": "Bitcoin ETP", "kurs": 50.0, "gewicht": 10.0, "art": "krypto"},
        {"name": "Tagesgeld / Cash", "kurs": 1.0, "gewicht": 10.0, "art": "sonstig"},
    ],
}


def standard():
    return copy.deepcopy(STANDARD)


def _zahl(x, default=0.0):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(v) or math.isinf(v) else v


def bereinigen(e):
    """Eingaben vervollstaendigen und in gueltige Grenzen bringen (fehlende Felder = Standard)."""
    aus = standard()
    for k in aus:
        if k in (e or {}):
            aus[k] = copy.deepcopy(e[k])
    # Grenzen = Grenzen der Eingabefelder (ein gespeicherter Wert ausserhalb liesse das Feld scheitern)
    for k in ("anfangskapital", "sonstiges_kapital", "kredit_summe"):
        aus[k] = min(max(_zahl(aus[k]), 0.0), MAX_KAPITAL)
    for k in ("kredit_rate", "einzahlung", "entnahme", "ausgaben"):
        aus[k] = min(max(_zahl(aus[k]), 0.0), MAX_MONATLICH)
    aus["kredit_zins_pa"] = min(max(_zahl(aus["kredit_zins_pa"]), 0.0), MAX_KREDITZINS)
    aus["rendite_pa"] = min(max(_zahl(aus["rendite_pa"]), -MAX_RENDITE), MAX_RENDITE)
    aus["zielvermoegen"] = min(max(_zahl(aus["zielvermoegen"]), 0.0), MAX_KAPITAL)
    aus["auto_ziel"] = bool(aus.get("auto_ziel"))
    aus["laufzeit_einheit"] = "Monate" if aus.get("laufzeit_einheit") == "Monate" else "Jahre"
    aus["laufzeit"] = min(max(int(_zahl(aus["laufzeit"], 1)), 1),
                          MAX_MONATE if aus["laufzeit_einheit"] == "Monate" else MAX_MONATE // 12)
    aus["nur_ganze_stuecke"] = bool(aus.get("nur_ganze_stuecke"))
    pos = []
    for p in aus.get("positionen") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        kurs = max(_zahl(p.get("kurs")), 0.0)
        gewicht = max(_zahl(p.get("gewicht")), 0.0)
        if not name and kurs <= 0 and gewicht <= 0:
            continue
        neu = {"name": name or "Neue Position", "kurs": kurs, "gewicht": gewicht,
               "art": p.get("art") if p.get("art") in ARTEN else "sonstig"}
        r = _zahl(p.get("rendite"), None)
        if r is not None:                                     # eigene erwartete Rendite % p. a.
            neu["rendite"] = min(max(r, -MAX_RENDITE), MAX_RENDITE)
        elif p.get("allgemein"):                              # bewusst geleert: allgemeine Rendite
            neu["allgemein"] = True
        for k in ("wkn", "isin", "instrument_id"):          # Kennungen fuer den Kursabruf
            if p.get(k) not in (None, ""):
                neu[k] = str(p[k]).strip()
        pos.append(neu)
    aus["positionen"] = pos
    return aus


def rest_gewicht(pos):
    """Gewicht, das bis 100 % noch frei ist (fuer neue Positionen)."""
    return max(100.0 - sum(max(_zahl(p.get("gewicht")), 0.0) for p in pos), 0.0)


def einpassen(pos, neu):
    """Neue Positionen (Indizes in neu) automatisch einpassen:
    - ohne Gewicht (0) bekommen sie den noch freien Rest bis 100 % zu gleichen Teilen; ist nichts
      mehr frei, je einen gleichen Anteil (100 % / Anzahl aller Positionen);
    - ergibt das zusammen mehr als 100 %, werden die bisherigen Positionen anteilig gekuerzt, so dass
      die neuen ihr Gewicht behalten und die Summe genau 100 % ist.
    -> neue Liste (Eingabe unveraendert)"""
    pos = copy.deepcopy(pos)
    neu = sorted({i for i in neu if 0 <= i < len(pos)})
    if not neu:
        return pos
    leer = [i for i in neu if pos[i]["gewicht"] <= EPS]
    if leer:
        rest = rest_gewicht(pos)
        anteil = rest / len(leer) if rest > 0.05 else 100.0 / len(pos)
        for i in leer:
            pos[i]["gewicht"] = anteil
    summe = sum(p["gewicht"] for p in pos)
    if summe <= 100.0 + 1e-9:
        return pos
    s_neu = sum(pos[i]["gewicht"] for i in neu)
    s_alt = summe - s_neu
    if s_neu >= 100.0 or s_alt <= EPS:
        return auf_100(pos)
    faktor = (100.0 - s_neu) / s_alt
    for i, p in enumerate(pos):
        if i not in neu:
            p["gewicht"] *= faktor
    return pos


def position_hinzufuegen(pos, name, kurs=0.0, gewicht=None, art="sonstig", rendite=None, **kennung):
    """Neue Position anhaengen und automatisch einpassen (siehe einpassen): gewicht None oder 0 =
    freier Rest bis 100 %, sonst ein gleicher Anteil; die uebrigen werden bei Bedarf anteilig gekuerzt.
    Gibt es den Wert schon (gleiche WKN/ISIN, sonst gleicher Name), wird nichts doppelt angelegt.
    -> (neue Positionen, hinzugefuegt: bool)"""
    pos = copy.deepcopy(pos)
    wkn, isin = str(kennung.get("wkn") or "").strip().upper(), str(kennung.get("isin") or "").strip().upper()
    for p in pos:
        if (wkn and str(p.get("wkn") or "").upper() == wkn) or (isin and str(p.get("isin") or "").upper() == isin) \
                or (not wkn and not isin and p["name"].strip().lower() == str(name).strip().lower()):
            return pos, False
    neu = {"name": str(name).strip() or "Neue Position", "kurs": max(_zahl(kurs), 0.0),
           "gewicht": 0.0 if gewicht is None else max(_zahl(gewicht), 0.0),
           "art": art if art in ARTEN else "sonstig"}
    for k, v in (("wkn", wkn), ("isin", isin), ("instrument_id", kennung.get("instrument_id"))):
        if v not in (None, ""):
            neu[k] = str(v)
    if _zahl(rendite, None) is not None:
        neu["rendite"] = round(min(max(_zahl(rendite), -MAX_RENDITE), MAX_RENDITE), 2)
    pos.append(neu)
    return einpassen(pos, [len(pos) - 1]), True


def katalog_rendite(w):
    """Erwartete Rendite fuer einen Katalogwert als Vorschlag: 5 J. p. a., sonst 3 J. p. a., sonst
    10 J., sonst 2 J. p. a., sonst die Entwicklung der letzten 12 Monate (junge Werte, z. B. viele Wikifolios).
    None = keine Daten."""
    k = kennzahlen(w)
    for r in (k["5J p.a."], k["3J p.a."], pro_jahr(w.get("10J"), 10), pro_jahr(w.get("2J"), 2), k["1J"]):
        if r is not None:
            return r
    return None


ZEITRAEUME = ("1J", "2J", "3J", "5J", "10J")


def _name_schluessel(name):
    return "".join(c for c in str(name or "").lower() if c.isalnum())


def mit_ranglisten(katalog, ranglisten, neu_arten=("wikifolio", "etf")):
    """Katalog um die Entwicklung aus den Watchlist-Ranglisten (Top 50 / Top 500 je Zeitraum) ergaenzen.
    ranglisten = [(art, [(name, kennung, {zeitraum: entwicklung gesamt %})])]. Werte ohne eigene Zahlen
    bekommen sie (Abgleich ueber WKN/ISIN, sonst den Namen); Werte der Arten neu_arten, die nur in den
    Ranglisten stehen, kommen dazu (Aktien nicht - deren Listen umfassen tausende Werte). -> neue Liste"""
    werte = copy.deepcopy(list(katalog or []))
    je_kennung, je_name = {}, {}
    for w in werte:
        for k in (w.get("wkn"), w.get("isin")):
            if k:
                je_kennung.setdefault(str(k).strip().upper(), w)
        je_name.setdefault(_name_schluessel(w.get("name")), w)
    for art, liste in ranglisten:
        for name, kennung, perf in liste:
            perf = {z: float(v) for z, v in (perf or {}).items()
                    if z in ZEITRAEUME and isinstance(v, (int, float)) and v > -100}
            if not name or not perf:
                continue
            k = str(kennung or "").strip().upper()
            w = je_kennung.get(k) if k else None
            w = w or je_name.get(_name_schluessel(name))
            if w is None and art not in neu_arten:
                continue
            if w is None:
                w = {"name": str(name), "wkn": k if len(k) == 6 else "", "isin": k if len(k) == 12 else "",
                     "art": art if art in ARTEN else "sonstig", "kurs": None}
                werte.append(w)
                if k:
                    je_kennung[k] = w
                je_name[_name_schluessel(name)] = w
            for z, v in perf.items():
                if w.get(z) is None:
                    w[z] = v
    return werte


def entwicklung_aus_historie(punkte):
    """[(ts_ms, kurs)] -> {zeitraum: Entwicklung gesamt %} fuer 1/2/3/5/10 Jahre, soweit die Historie
    reicht (wie in den Ranglisten). Leer bei zu kurzer Historie."""
    reihe = sorted((float(t), float(k)) for t, k in punkte or []
                   if isinstance(t, (int, float)) and isinstance(k, (int, float)) and k > 0)
    if len(reihe) < 10:
        return {}
    tag_ms, ende, letzter = 86400000.0, reihe[-1][0], reihe[-1][1]
    aus = {}
    for z, jahre in (("1J", 1), ("2J", 2), ("3J", 3), ("5J", 5), ("10J", 10)):
        stichtag = ende - jahre * 365.25 * tag_ms
        if reihe[0][0] > stichtag + 10 * tag_ms:         # Historie reicht nicht so weit zurueck
            break
        vorher = [k for t, k in reihe if t <= stichtag]
        start = vorher[-1] if vorher else reihe[0][1]
        aus[z] = (letzter / start - 1.0) * 100.0
    return aus


def renditen_ergaenzen(pos, katalog):
    """Fehlende Angaben aus dem Katalog nachtragen (Abgleich ueber WKN/ISIN, sonst den Namen):
    erwartete Rendite (ausser bewusst geleert), Kurs (wenn 0), WKN/ISIN und die Art (statt "Sonstiges").
    -> (neue Positionen, Anzahl geaenderter Positionen)"""
    pos = copy.deepcopy(pos)
    nach_kennung, nach_name = {}, {}
    for w in katalog or []:
        for k in (w.get("wkn"), w.get("isin")):
            if k:
                nach_kennung.setdefault(str(k).strip().upper(), w)
        if w.get("name"):
            nach_name.setdefault(str(w["name"]).strip().lower(), w)
    n = 0
    for p in pos:
        w = (next((nach_kennung[k] for k in (str(p.get("wkn") or "").upper(), str(p.get("isin") or "").upper())
                   if k and k in nach_kennung), None) or nach_name.get(str(p.get("name") or "").strip().lower()))
        if not w:
            continue
        vorher = dict(p)
        r = katalog_rendite(w)
        if p.get("rendite") is None and not p.get("allgemein") and r is not None:
            p["rendite"] = round(min(max(r, -MAX_RENDITE), MAX_RENDITE), 2)
        if _zahl(p.get("kurs")) <= 0 and _zahl(w.get("kurs")) > 0:
            p["kurs"] = float(w["kurs"])
        for k in ("wkn", "isin"):
            if not p.get(k) and w.get(k):
                p[k] = str(w[k])
        if p.get("art", "sonstig") == "sonstig" and w.get("art") in ARTEN and w.get("art") != "sonstig":
            p["art"] = w["art"]
        n += p != vorher
    return pos, n


def anteile_nach_art(e):
    """{art: % des Anlagekapitals} nach tatsaechlichem Wert (Cash-Rest als "cash")."""
    p = positionen(e)
    if p["kapital"] <= 0:
        return {}
    aus = {}
    for z, q in zip(p["zeilen"], e["positionen"]):
        aus[q.get("art", "sonstig")] = aus.get(q.get("art", "sonstig"), 0.0) + z["wert"] / p["kapital"] * 100.0
    if p["cash"] > 0.005:
        aus["cash"] = aus.get("cash", 0.0) + p["cash"] / p["kapital"] * 100.0
    return aus


def monate(e):
    n = int(e["laufzeit"]) * (12 if e["laufzeit_einheit"] == "Jahre" else 1)
    return min(max(n, 1), MAX_MONATE)


def eigenkapital(e):
    return e["anfangskapital"] + e["sonstiges_kapital"]


def anlagekapital(e):
    return eigenkapital(e) + e["kredit_summe"]


# ---------------------------------------------------------------- Positionen
def positionen(e):
    """Je Position: Betrag (Gewicht x Anlagekapital), Stueck (Betrag / Kurs, ggf. abgerundet),
    Wert (Stueck x Kurs). Nicht investierter Rest (Gewichte < 100 % oder Rundung) bleibt als Cash.
    -> {"zeilen": [...], "summe_gewicht", "investiert", "cash", "kapital"}"""
    kapital = anlagekapital(e)
    zeilen = []
    for p in e["positionen"]:
        betrag = kapital * p["gewicht"] / 100.0
        if p["kurs"] > 0:
            stueck = betrag / p["kurs"]
            if e["nur_ganze_stuecke"]:
                stueck = math.floor(stueck + EPS)
            wert = stueck * p["kurs"]
        else:
            stueck, wert = 0.0, 0.0
        zeilen.append({"name": p["name"], "kurs": p["kurs"], "gewicht": p["gewicht"], "betrag": betrag,
                       "stueck": stueck, "wert": wert,
                       "anteil": (wert / kapital * 100.0) if kapital > 0 else 0.0})
    investiert = sum(z["wert"] for z in zeilen)
    return {"zeilen": zeilen, "summe_gewicht": sum(p["gewicht"] for p in e["positionen"]),
            "investiert": investiert, "cash": max(kapital - investiert, 0.0), "kapital": kapital}


def aenderungen_anwenden(pos, kapital, geaendert=None, neu=None, geloescht=None):
    """Aenderungen aus der editierbaren Tabelle uebernehmen (Format wie st.data_editor:
    geaendert = {zeile: {feld: wert}}, neu = [{feld: wert}], geloescht = [zeile]).
    Felder: name, kurs, gewicht, betrag, stueck. Gespeichert wird je Position nur das Gewicht;
    Betrag und Stueck rechnen sich daraus. Wurde in einer Zeile Stueck oder Betrag geaendert,
    gilt das (Stueck vor Betrag) und das Gewicht wird daraus zurueckgerechnet; ein neuer Kurs
    laesst das Gewicht stehen (die Stueckzahl passt sich an).  -> neue Positionen"""
    pos = copy.deepcopy(pos)

    def gewicht_aus(werte, p):
        kurs = p["kurs"]
        if kapital > 0 and _zahl(werte.get("stueck"), None) is not None:
            return max(_zahl(werte["stueck"]), 0.0) * kurs / kapital * 100.0
        if kapital > 0 and _zahl(werte.get("betrag"), None) is not None:
            return max(_zahl(werte["betrag"]), 0.0) / kapital * 100.0
        if _zahl(werte.get("gewicht"), None) is not None:
            return max(_zahl(werte["gewicht"]), 0.0)
        return p["gewicht"]

    for i, werte in (geaendert or {}).items():
        i = int(i)
        if not 0 <= i < len(pos):
            continue
        p = pos[i]
        if "name" in werte:
            p["name"] = str(werte["name"] or "").strip() or p["name"]
        if "kurs" in werte:
            p["kurs"] = max(_zahl(werte["kurs"], p["kurs"]), 0.0)
        if werte.get("art") in ARTEN:
            p["art"] = werte["art"]
        if "rendite" in werte:                                # leer = allgemeine Rendite
            r = _zahl(werte["rendite"], None)
            if r is None:                                     # bewusst geleert: nicht wieder vorschlagen
                p.pop("rendite", None)
                p["allgemein"] = True
            else:
                p["rendite"] = min(max(r, -MAX_RENDITE), MAX_RENDITE)
                p.pop("allgemein", None)
        p["gewicht"] = gewicht_aus(werte, p)
    weg = {int(i) for i in (geloescht or [])}
    pos = [p for i, p in enumerate(pos) if i not in weg]
    vorher = len(pos)
    for werte in neu or []:
        p = {"name": str(werte.get("name") or "").strip() or "Neue Position",
             "kurs": max(_zahl(werte.get("kurs")), 0.0), "gewicht": 0.0,
             "art": werte.get("art") if werte.get("art") in ARTEN else "sonstig"}
        p["gewicht"] = gewicht_aus(werte, p)
        r = _zahl(werte.get("rendite"), None)
        if r is not None:
            p["rendite"] = min(max(r, -MAX_RENDITE), MAX_RENDITE)
        pos.append(p)
    # neue Zeilen ohne Gewicht bekommen automatisch einen Anteil (die uebrigen werden angepasst)
    return einpassen(pos, range(vorher, len(pos)))


def auf_100(pos):
    """Gewichte proportional auf zusammen 100 % bringen (alle 0 -> gleich verteilen)."""
    pos = copy.deepcopy(pos)
    s = sum(p["gewicht"] for p in pos)
    if not pos:
        return pos
    for p in pos:
        p["gewicht"] = p["gewicht"] / s * 100.0 if s > EPS else 100.0 / len(pos)
    return pos


# ---------------------------------------------------------------- Kredit & Simulation
def zins_monat(e):
    return e["kredit_zins_pa"] / 100.0 / 12.0


def rate_fuer_tilgung(summe, zins_pa_prozent, monate_n):
    """Annuitaet, die summe in monate_n Monaten genau tilgt (Zins nominal / 12)."""
    if summe <= 0 or monate_n <= 0:
        return 0.0
    i = zins_pa_prozent / 100.0 / 12.0
    if i <= EPS:
        return summe / monate_n
    return summe * i / (1.0 - (1.0 + i) ** (-monate_n))


def position_rendite(e, p):
    """Erwartete Rendite % p. a. einer Position: eigene, sonst die allgemeine."""
    r = p.get("rendite")
    return float(r) if r is not None else e["rendite_pa"]


def portfolio_rendite(e):
    """Erwartete Rendite des ganzen Portfolios % p. a.: nach Wert gewichteter Mittelwert der Positionen;
    der nicht investierte Rest (Cash) und ein Portfolio ohne Kapital rechnen mit der allgemeinen Rendite.
    Ohne eigene Renditen je Position ist das genau die allgemeine Rendite."""
    pos = positionen(e)
    if pos["kapital"] <= 0:
        return e["rendite_pa"]
    summe = sum(z["wert"] * position_rendite(e, p) for z, p in zip(pos["zeilen"], e["positionen"]))
    summe += pos["cash"] * e["rendite_pa"]
    return summe / max(pos["investiert"] + pos["cash"], EPS)


def rendite_monat(e, rendite_pa=None):
    r = portfolio_rendite(e) if rendite_pa is None else rendite_pa
    return (1.0 + r / 100.0) ** (1.0 / 12.0) - 1.0


def simulation(e, rendite_pa=None):
    """Monatliche Simulation. rendite_pa: Portfolio-Rendite vorgeben (sonst aus den Positionen).
    -> dict mit Verlauf (Monat 0..n) und Kennzahlen."""
    e = bereinigen(e)
    n = monate(e)
    r_pa = portfolio_rendite(e) if rendite_pa is None else rendite_pa
    rm, iz = rendite_monat(e, r_pa), zins_monat(e)
    pos = positionen(e)
    v = pos["kapital"]                       # Positionen + nicht investierter Rest
    d = e["kredit_summe"]
    summen = {"einzahlung": 0.0, "entnahme": 0.0, "ausgaben": 0.0, "kreditrate": 0.0, "zinsen": 0.0,
              "rendite": 0.0, "fehlbetrag": 0.0}
    verlauf = [{"monat": 0, "portfolio": v, "schulden": d, "netto": v - d}]
    rate_zu_klein = d > EPS and e["kredit_rate"] <= d * iz + EPS
    getilgt_monat = None
    erster_cashflow = None
    for t in range(1, n + 1):
        zinsen = d * iz
        rate = min(e["kredit_rate"], d + zinsen) if d > EPS else 0.0
        d = max(d + zinsen - rate, 0.0)
        if d <= 0.005 and getilgt_monat is None and e["kredit_summe"] > 0:
            d, getilgt_monat = 0.0, t
        cashflow = e["einzahlung"] - e["entnahme"] - e["ausgaben"] - rate
        if erster_cashflow is None:
            erster_cashflow = cashflow
        ertrag = v * rm
        v = v + ertrag + cashflow
        if v < 0:
            summen["fehlbetrag"] += -v
            v = 0.0
        summen["einzahlung"] += e["einzahlung"]
        summen["entnahme"] += e["entnahme"]
        summen["ausgaben"] += e["ausgaben"]
        summen["kreditrate"] += rate
        summen["zinsen"] += zinsen
        summen["rendite"] += ertrag
        verlauf.append({"monat": t, "portfolio": v, "schulden": d, "netto": v - d})
    return {
        "eingaben": e, "monate": n, "positionen": pos,
        "eigenkapital": eigenkapital(e), "anlagekapital": pos["kapital"], "rendite_pa": r_pa,
        "portfoliowert": pos["kapital"],             # Positionen + Cash-Rest zum Start
        "cashflow_monat": erster_cashflow if erster_cashflow is not None else 0.0,
        "endwert": v, "restschuld": d, "netto_endvermoegen": v - d,
        "summen": summen, "verlauf": verlauf,
        "kredit": {"rate_zu_klein": rate_zu_klein, "getilgt_monat": getilgt_monat,
                   "rate_volltilgung": rate_fuer_tilgung(e["kredit_summe"], e["kredit_zins_pa"], n)},
    }


# ---------------------------------------------------------------- Rangliste (Top 100)
KRITERIEN = {
    "5J p.a.": "Rendite pro Jahr über 5 Jahre",
    "3J p.a.": "Rendite pro Jahr über 3 Jahre",
    "1J": "Kursentwicklung der letzten 12 Monate",
    "Rendite/Risiko": "5 J. p. a. geteilt durch die Schwankung (Vola) – Rendite je Risiko",
}


def pro_jahr(gesamt_pct, jahre):
    """Gesamtentwicklung in % ueber n Jahre -> Rendite p. a. in % (geometrisch). None, wenn nicht rechenbar."""
    if gesamt_pct is None or jahre <= 0:
        return None
    try:
        g = float(gesamt_pct)
    except (TypeError, ValueError):
        return None
    if math.isnan(g) or g <= -100:
        return None
    return ((1 + g / 100.0) ** (1.0 / jahre) - 1) * 100.0


def kennzahlen(w):
    """Kennzahlen eines Katalogwerts (Felder 1J/3J/5J = Gesamtentwicklung in %, vola, maxdd)."""
    p5, p3 = pro_jahr(w.get("5J"), 5), pro_jahr(w.get("3J"), 3)
    vola = w.get("vola")
    vola = float(vola) if isinstance(vola, (int, float)) and vola > 0 else None
    eins = w.get("1J")
    return {"1J": float(eins) if isinstance(eins, (int, float)) else None, "3J p.a.": p3, "5J p.a.": p5,
            "Rendite/Risiko": (p5 / vola) if p5 is not None and vola else None,
            "vola": vola, "maxdd": w.get("maxdd") if isinstance(w.get("maxdd"), (int, float)) else None}


def rangliste(werte, kriterium="5J p.a.", art=None, n=100):
    """Die besten n Werte nach einem Kriterium (absteigend). Werte ohne Kennzahl fuer das Kriterium
    fallen heraus. art: nur diese Art (None = alle Arten gemischt).
    -> [dict(wert, rang, **kennzahlen)]"""
    aus = []
    for w in werte:
        if art and w.get("art") != art:
            continue
        k = kennzahlen(w)
        if k.get(kriterium) is None:
            continue
        aus.append(dict(w, **k))
    aus.sort(key=lambda x: (-x[kriterium], x.get("name", "").lower()))
    for i, x in enumerate(aus[:n], 1):
        x["rang"] = i
    return aus[:n]


def mehrere_hinzufuegen(pos, werte):
    """Mehrere Werte auf einmal anlegen; der bis 100 % freie Rest wird gleichmaessig verteilt
    (nur auf die wirklich neuen Werte). -> (neue Positionen, Anzahl neu, Namen schon vorhanden)"""
    pos = copy.deepcopy(pos)
    neu_werte, schon = [], []
    for w in werte:
        _, ok = position_hinzufuegen(pos + [dict(name=x["name"], kurs=0, gewicht=0, wkn=x.get("wkn"),
                                                 isin=x.get("isin")) for x in neu_werte],
                                     w["name"], wkn=w.get("wkn"), isin=w.get("isin"))
        (neu_werte if ok else schon).append(w if ok else w["name"])
    start = len(pos)
    for w in neu_werte:
        pos.append({"name": str(w["name"]).strip() or "Neue Position", "kurs": max(_zahl(w.get("kurs")), 0.0),
                    "gewicht": 0.0, "art": w.get("art") if w.get("art") in ARTEN else "sonstig"})
        for k in ("wkn", "isin"):
            if w.get(k) not in (None, ""):
                pos[-1][k] = str(w[k])
        r = katalog_rendite(w)
        if r is not None:
            pos[-1]["rendite"] = round(min(max(r, -MAX_RENDITE), MAX_RENDITE), 2)
    return einpassen(pos, range(start, len(pos))), len(neu_werte), schon


# ---------------------------------------------------------------- Rebalancing
REBALANCING = {
    "anteilig": "Gewichte behalten, 0 % ergänzen",
    "gleich": "Alle gleich gewichten",
    "ziel": "Aufs Zielvermögen",
}


def rebalancing(e, methode="anteilig"):
    """Alle Positionen neu gewichten, zusammen genau 100 %. Betrag und Stueck rechnen sich danach
    aus Gewicht und Kurs.
    - anteilig: bestehende Verhaeltnisse bleiben; Positionen mit 0 % zaehlen wie der Durchschnitt
      der uebrigen (alle 0 -> gleich verteilt)
    - gleich:   jede Position 100 % / Anzahl
    - ziel:     wie "Automatisch aufs Ziel" (ohne Zielvermoegen wie anteilig)
    -> neue Positionen (Eingabe unveraendert)"""
    e = bereinigen(e)
    pos = copy.deepcopy(e["positionen"])
    if not pos:
        return pos
    if methode == "gleich":
        for p in pos:
            p["gewicht"] = 100.0 / len(pos)
        return pos
    if methode == "ziel" and e["zielvermoegen"] > 0:
        z = ziel_gewichte(dict(e, positionen=rebalancing(e, "anteilig")))
        if z and z["positionen"]:
            return z["positionen"]
    gesetzt = [p["gewicht"] for p in pos if p["gewicht"] > EPS]
    mittel = sum(gesetzt) / len(gesetzt) if gesetzt else 1.0
    for p in pos:
        if p["gewicht"] <= EPS:
            p["gewicht"] = mittel
    return auf_100(pos)


# ---------------------------------------------------------------- Zielvermoegen
def benoetigte_rendite(e):
    """Portfolio-Rendite % p. a., mit der das Netto-Endvermoegen genau das Zielvermoegen erreicht
    (Bisektion ueber die Simulation; Kredit, Ein-/Auszahlungen und Laufzeit wie eingegeben).
    -> {"rendite", "erreichbar"} oder None ohne Ziel. erreichbar=False: liegt ausserhalb +/-MAX_RENDITE."""
    e = bereinigen(e)
    ziel = e["zielvermoegen"]
    if ziel <= 0:
        return None

    def netto(r):
        return simulation(e, rendite_pa=r)["netto_endvermoegen"]

    lo, hi = -MAX_RENDITE, MAX_RENDITE
    if netto(hi) < ziel:
        return {"rendite": hi, "erreichbar": False}
    if netto(lo) >= ziel:
        return {"rendite": lo, "erreichbar": True}
    for _ in range(80):
        mitte = (lo + hi) / 2.0
        if netto(mitte) < ziel:
            lo = mitte
        else:
            hi = mitte
        if hi - lo < 1e-7:
            break
    return {"rendite": hi, "erreichbar": True}


def ziel_gewichte(e):
    """Gewichte so verteilen, dass die Portfolio-Rendite die fuer das Ziel benoetigte Rendite ergibt.

    Die Positionen werden in "Basis" (Rendite <= benoetigt) und "Wachstum" (Rendite > benoetigt)
    geteilt. Innerhalb jeder Gruppe bleiben die bisherigen Verhaeltnisse (alle 0 -> gleich verteilt);
    zwischen den Gruppen wird so gemischt, dass der gewichtete Mittelwert genau die benoetigte Rendite
    ist. Trifft keine Mischung das Ziel (alle Werte darunter bzw. darueber), bleibt die eigene Aufteilung
    stehen - es fliegt kein Wert heraus. Positionen mit 0 % bekommen einen Anteil. Zusammen immer 100 %.
    -> {"positionen", "benoetigt", "erreicht" (Rendite nach Verteilung), "status", "spanne" (niedrigste,
       hoechste Rendite der Werte)} oder None ohne Ziel.
       status: "ok" | "zu_hoch" (Ziel mit diesen Werten nicht erreichbar) | "uebertroffen" (schon die
       Basis-Werte liegen ueber dem Ziel bzw. es gibt keine) | "leer" (keine Positionen)"""
    e = bereinigen(e)
    b = benoetigte_rendite(e)
    if b is None:
        return None
    pos = copy.deepcopy(e["positionen"])
    if not pos:
        return {"positionen": pos, "benoetigt": b["rendite"], "erreicht": None, "status": "leer", "spanne": None}
    ziel_r = b["rendite"]
    r = [position_rendite(e, p) for p in pos]
    tief = [i for i in range(len(pos)) if r[i] <= ziel_r + 1e-9]
    hoch = [i for i in range(len(pos)) if r[i] > ziel_r + 1e-9]

    def verteilung(gruppe):
        # Positionen mit 0 % (z. B. gerade hinzugefuegt) zaehlen wie der Durchschnitt ihrer Gruppe -
        # sonst blieben sie bei der automatischen Verteilung fuer immer bei 0
        g = {i: pos[i]["gewicht"] for i in gruppe}
        gesetzt = [v for v in g.values() if v > EPS]
        mittel = sum(gesetzt) / len(gesetzt) if gesetzt else 1.0
        g = {i: (v if v > EPS else mittel) for i, v in g.items()}
        s = sum(g.values())
        return {i: v / s for i, v in g.items()}

    spanne = (min(r), max(r))
    if not hoch or not tief:
        # keine Mischung trifft das Ziel genau: die eigene Aufteilung bleibt (nur 0 % -> Anteil)
        t, hoch = 0.0, []
        tief = list(range(len(pos)))
        status = ("ok" if abs(spanne[1] - ziel_r) < 1e-6 and abs(spanne[0] - ziel_r) < 1e-6
                  else "uebertroffen" if spanne[0] > ziel_r else "zu_hoch")
    else:
        status = "ok"
    v_tief, v_hoch = verteilung(tief), verteilung(hoch) if hoch else {}
    if hoch:
        r_tief = sum(v * r[i] for i, v in v_tief.items())
        r_hoch = sum(v * r[i] for i, v in v_hoch.items())
        t = (ziel_r - r_tief) / (r_hoch - r_tief)
    if not b["erreichbar"]:
        status = "zu_hoch"
    t = min(max(t, 0.0), 1.0)
    for i, p in enumerate(pos):
        p["gewicht"] = 100.0 * ((1.0 - t) * v_tief.get(i, 0.0) + t * v_hoch.get(i, 0.0))
    erreicht = sum(p["gewicht"] / 100.0 * r[i] for i, p in enumerate(pos))
    return {"positionen": pos, "benoetigt": ziel_r, "erreicht": erreicht, "status": status, "spanne": spanne}

