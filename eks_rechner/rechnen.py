"""Kennzahlen der EKS-Investmentbewertung (ohne Streamlit, nachrechenbar, getestet in test_eks.py).

Annahmen (bewusst einfach und fuer alle Ideen gleich):
- Monatsraster: Monat 0 = Startinvestition (Abfluss), Monate 1..12*Horizont = laufender Betrieb.
- Hochlauf: Der Umsatz steigt linear auf den vollen Monatsumsatz; in Monat m (1..Anlauf) m/Anlauf davon.
  Anlauf 0 = sofort voller Umsatz. Fixkosten fallen ab Monat 1 voll an.
- Szenario: Umsatz x Umsatz-Faktor; variable Kosten (Anteil am Umsatz) und Fixkosten x Kosten-Faktor.
- Steuern: Steuersatz auf den positiven Monatsgewinn (vereinfachte Annahme, kein Verlustvortrag).
- Kein Restwert am Ende des Horizonts, keine Abschreibung der Startinvestition.
- Diskontierung monatlich mit (1 + i)^(1/12) - 1; i = Opportunitaetsrendite p. a. (Standard 7 %).
- IRR: monatlicher Zinsfuss per Bisektion, auf p. a. hochgerechnet; ohne Vorzeichenwechsel "nicht definiert".
- Engpass-Kennzahl: durchschnittlicher Monatsgewinn nach Steuern (ohne Startinvestition) / Stunden je Monat
  (Stunden/Woche x 52 / 12).
"""
from . import modell as M

SENSITIVITAET = 0.20
AMPEL = {"gruen": "🟢", "gelb": "🟡", "rot": "🔴"}
AMPEL_TEXT = {"gruen": "Grün", "gelb": "Gelb", "rot": "Rot"}
WOCHEN_JE_MONAT = 52 / 12


def _norm(score, invers=False):
    """Score 1-10 -> 0-100 (invers: 10 -> 0, 1 -> 100)."""
    s = min(max(float(score), M.SCORE_MIN), M.SCORE_MAX)
    return ((M.SCORE_MAX - s) if invers else (s - M.SCORE_MIN)) / (M.SCORE_MAX - M.SCORE_MIN) * 100


def nutzwert(idee, kriterien):
    """Gewichtete Summe der Kriterien, 0-100. Gewichte werden auf ihre Summe normiert (falls != 100 %)."""
    g = sum(float(k["gewicht"]) for k in kriterien)
    if g <= 0:
        return None
    s = idee.get("kriterien") or {}
    return sum(float(k["gewicht"]) * _norm(s.get(k["id"], M.SCORE_START), k.get("invers")) for k in kriterien) / g


def eks_score(idee):
    """Mittelwert der 7 EKS-Phasen-Scores (1-10) x 10 -> 10-100."""
    p = [float((idee.get("phasen") or {}).get(nr, {}).get("score", M.SCORE_START)) for nr, _, _ in M.PHASEN]
    return sum(p) / len(p) * 10


def monate(fin):
    return int(fin["horizont_jahre"]) * 12


def verlauf(fin, umsatz_faktor=1.0, kosten_faktor=1.0):
    """-> Liste je Monat 0..N: {monat, umsatz, kosten, gewinn_vor, steuer, cashflow, kumuliert}"""
    u_voll = float(fin["umsatz_monat"]) * umsatz_faktor
    var = float(fin["var_kosten_pct"]) / 100 * kosten_faktor
    fix = float(fin["fix_monat"]) * kosten_faktor
    st = float(fin["steuersatz_pct"]) / 100
    anlauf = int(fin["anlauf_monate"])
    start = -float(fin["start_invest"])
    aus = [{"monat": 0, "umsatz": 0.0, "kosten": 0.0, "gewinn_vor": 0.0, "steuer": 0.0, "cashflow": start,
            "kumuliert": start}]
    kum = start
    for m in range(1, monate(fin) + 1):
        u = u_voll * (min(m / anlauf, 1.0) if anlauf > 0 else 1.0)
        kosten = u * var + fix
        g = u - kosten
        steuer = max(g, 0.0) * st
        cf = g - steuer
        kum += cf
        aus.append({"monat": m, "umsatz": u, "kosten": kosten, "gewinn_vor": g, "steuer": steuer, "cashflow": cf,
                    "kumuliert": kum})
    return aus


def break_even_umsatz(fin, kosten_faktor=1.0):
    """Monatsumsatz, bei dem der Gewinn vor Steuern 0 ist: Fixkosten / (1 - variable Kostenquote).
    None, wenn die variablen Kosten den Umsatz ganz aufzehren (Quote >= 100 %)."""
    var = float(fin["var_kosten_pct"]) / 100 * kosten_faktor
    if var >= 1:
        return None
    return float(fin["fix_monat"]) * kosten_faktor / (1 - var)


def break_even_monat(v):
    """Erster Betriebsmonat mit Umsatz > 0 und Gewinn vor Steuern >= 0 - sonst None."""
    return next((z["monat"] for z in v[1:] if z["umsatz"] > 0 and z["gewinn_vor"] >= 0), None)


def amortisation(v):
    """Erster Monat, in dem der kumulierte Cashflow (inkl. Startinvestition) >= 0 ist. 0 = keine Investition.
    None = im Horizont nicht erreicht."""
    if v[0]["cashflow"] >= 0:
        return 0
    return next((z["monat"] for z in v[1:] if z["kumuliert"] >= 0), None)


def monatszins(zins_pa):
    return (1 + zins_pa) ** (1 / 12) - 1


def npv(cashflows, zins_pa):
    r = monatszins(zins_pa)
    return sum(cf / (1 + r) ** t for t, cf in enumerate(cashflows))


def irr(cashflows, iterationen=200):
    """Interner Zinsfuss p. a. (aus dem monatlichen Zinsfuss). None, wenn es keinen Vorzeichenwechsel gibt
    (z. B. nur Verluste oder keine Investition) oder keine Nullstelle im Suchbereich liegt."""
    if not (any(c < 0 for c in cashflows) and any(c > 0 for c in cashflows)):
        return None

    def f(r):
        return sum(cf / (1 + r) ** t for t, cf in enumerate(cashflows))
    lo, hi = -0.99, 1.0                     # monatlich: -99 % ... +100 % (= +409.500 % p. a.)
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(iterationen):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if abs(f_mid) < 1e-9:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    r = (lo + hi) / 2
    return (1 + r) ** 12 - 1


def stunden_monat(fin):
    return float(fin["stunden_woche"]) * WOCHEN_JE_MONAT


def euro_je_stunde(fin, v):
    """Durchschnittlicher Monatsgewinn nach Steuern / Stunden je Monat. None ohne Stunden."""
    h = stunden_monat(fin)
    if h <= 0:
        return None
    betrieb = v[1:]
    return sum(z["cashflow"] for z in betrieb) / len(betrieb) / h if betrieb else None


def szenario(fin, faktoren, zins_pa):
    v = verlauf(fin, faktoren["umsatz"], faktoren["kosten"])
    cfs = [z["cashflow"] for z in v]
    return {"verlauf": v, "npv": npv(cfs, zins_pa), "irr": irr(cfs), "amortisation": amortisation(v),
            "break_even_monat": break_even_monat(v), "break_even_umsatz": break_even_umsatz(fin, faktoren["kosten"]),
            "euro_h": euro_je_stunde(fin, v), "summe_cf": sum(cfs),
            "gewinn_monat_voll": v[-1]["cashflow"] if len(v) > 1 else 0.0}


def sensitivitaet(fin, faktoren, zins_pa, delta=SENSITIVITAET):
    """NPV bei Umsatz +/- delta und Kosten +/- delta (Tornado). -> {basis, zeilen: [(name, npv_minus, npv_plus)]}"""
    u, k = faktoren["umsatz"], faktoren["kosten"]

    def n(uf, kf):
        return npv([z["cashflow"] for z in verlauf(fin, uf, kf)], zins_pa)
    return {"basis": n(u, k), "delta": delta,
            "zeilen": [("Umsatz", n(u * (1 - delta), k), n(u * (1 + delta), k)),
                       ("Kosten", n(u, k * (1 - delta)), n(u, k * (1 + delta)))]}


def ampel(nw, npv_real, eur_h, einstellungen):
    """Gruen: alle drei Bedingungen erfuellt; Gelb: genau eine verfehlt; Rot: zwei oder mehr verfehlt.
    Ohne Stunden (0 h/Woche) gilt die Stunden-Bedingung als erfuellt (kein Zeit-Engpass).
    -> (ampel, [verfehlte Bedingungen])"""
    verfehlt = []
    if nw is None or nw < float(einstellungen["schwelle_nutzwert"]):
        verfehlt.append("Nutzwert unter Schwelle")
    if not npv_real > 0:
        verfehlt.append("NPV (realistisch) nicht positiv")
    if eur_h is not None and eur_h < float(einstellungen["mindest_stundensatz"]):
        verfehlt.append("€/Stunde unter Mindestsatz")
    return ("gruen" if not verfehlt else "gelb" if len(verfehlt) == 1 else "rot"), verfehlt


def auswerten(idee, einstellungen):
    """Alle Kennzahlen einer Idee. -> dict (nutzwert, eks, szenarien {pess|real|opt}, sensitivitaet, ampel ...)"""
    e = einstellungen
    zins = float(e["diskont_pa"]) / 100
    fin = idee["finanzen"]
    sz = {k: szenario(fin, idee["szenarien"][k], zins) for k in M.SZENARIEN}
    nw = nutzwert(idee, e["kriterien"])
    real = sz["real"]
    a, verfehlt = ampel(nw, real["npv"], real["euro_h"], e)
    return {"id": idee["id"], "name": idee["name"], "status": idee["status"], "nutzwert": nw,
            "eks": eks_score(idee), "szenarien": sz, "npv": real["npv"], "irr": real["irr"],
            "amortisation": real["amortisation"], "euro_h": real["euro_h"],
            "break_even_umsatz": real["break_even_umsatz"], "break_even_monat": real["break_even_monat"],
            "sensitivitaet": sensitivitaet(fin, idee["szenarien"]["real"], zins), "ampel": a, "verfehlt": verfehlt,
            "stunden_monat": stunden_monat(fin)}


AMPEL_RANG = {"gruen": 0, "gelb": 1, "rot": 2}


def rangliste(daten):
    """Alle Ideen ausgewertet, sortiert: Ampel (gruen zuerst), dann Nutzwert, dann NPV. Verworfene ans Ende."""
    e = daten["einstellungen"]
    aus = [auswerten(i, e) for i in daten["ideen"]]
    aus.sort(key=lambda r: (r["status"] == "verworfen", AMPEL_RANG[r["ampel"]], -(r["nutzwert"] or 0), -r["npv"]))
    return aus


def kennzahlen_export(rang):
    """Fuer den CSV-Export: {idee_id: {spalte: wert}}"""
    return {r["id"]: {"Ampel": AMPEL_TEXT[r["ampel"]], "Nutzwert": round(r["nutzwert"] or 0, 1),
                      "EKS-Score": round(r["eks"], 1), "NPV €": round(r["npv"], 2),
                      "IRR % p. a.": None if r["irr"] is None else round(r["irr"] * 100, 2),
                      "Amortisation Monate": r["amortisation"],
                      "€ je Stunde": None if r["euro_h"] is None else round(r["euro_h"], 2)} for r in rang}
