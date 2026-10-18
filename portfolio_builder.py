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
    "rendite_pa": 6.0,              # %
    "nur_ganze_stuecke": False,
    "positionen": [
        {"name": "MSCI World ETF", "kurs": 100.0, "gewicht": 60.0},
        {"name": "Emerging Markets ETF", "kurs": 30.0, "gewicht": 20.0},
        {"name": "Bitcoin ETP", "kurs": 50.0, "gewicht": 10.0},
        {"name": "Tagesgeld / Cash", "kurs": 1.0, "gewicht": 10.0},
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
        pos.append({"name": name or "Neue Position", "kurs": kurs, "gewicht": gewicht})
    aus["positionen"] = pos
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
        p["gewicht"] = gewicht_aus(werte, p)
    weg = {int(i) for i in (geloescht or [])}
    pos = [p for i, p in enumerate(pos) if i not in weg]
    for werte in neu or []:
        p = {"name": str(werte.get("name") or "").strip() or "Neue Position",
             "kurs": max(_zahl(werte.get("kurs")), 0.0), "gewicht": 0.0}
        p["gewicht"] = gewicht_aus(werte, p)
        pos.append(p)
    return pos


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


def rendite_monat(e):
    return (1.0 + e["rendite_pa"] / 100.0) ** (1.0 / 12.0) - 1.0


def simulation(e):
    """Monatliche Simulation. -> dict mit Verlauf (Monat 0..n) und Kennzahlen."""
    e = bereinigen(e)
    n = monate(e)
    rm, iz = rendite_monat(e), zins_monat(e)
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
        "eigenkapital": eigenkapital(e), "anlagekapital": pos["kapital"],
        "portfoliowert": pos["kapital"],             # Positionen + Cash-Rest zum Start
        "cashflow_monat": erster_cashflow if erster_cashflow is not None else 0.0,
        "endwert": v, "restschuld": d, "netto_endvermoegen": v - d,
        "summen": summen, "verlauf": verlauf,
        "kredit": {"rate_zu_klein": rate_zu_klein, "getilgt_monat": getilgt_monat,
                   "rate_volltilgung": rate_fuer_tilgung(e["kredit_summe"], e["kredit_zins_pa"], n)},
    }
