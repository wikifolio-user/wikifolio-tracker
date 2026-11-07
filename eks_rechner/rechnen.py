"""Kennzahlen der EKS-Investmentbewertung (ohne Streamlit, nachrechenbar, getestet in test_eks.py).

Annahmen (bewusst einfach und fuer alle Ideen gleich):
- Monatsraster: Monat 0 = Startinvestition (Abfluss), Monate 1..12*Horizont = laufender Betrieb.
- Hochlauf: Der Umsatz steigt linear auf den vollen Monatsumsatz; in Monat m (1..Anlauf) m/Anlauf davon.
  Anlauf 0 = sofort voller Umsatz. Fixkosten fallen ab Monat 1 voll an.
- Szenario: Umsatz x Umsatz-Faktor; variable Kosten (Anteil am Umsatz) und Fixkosten x Kosten-Faktor.
- Umsaetze und Kosten netto (ohne Umsatzsteuer).
- Steuern je Geschaeftsjahr (Monate 1-12, 13-24, ...), gezahlt im letzten Monat des Jahres:
  Jahresgewinn - Abschreibung der Startinvestition (linear ueber "afa_jahre"; 0 = sofort im 1. Jahr)
  - Verlustvortrag aus Vorjahren = Bemessungsgrundlage. Einkommensteuer = Grenzsteuersatz x Grundlage.
  Gewerbesteuer = (Grundlage - Freibetrag 24.500 €) x 3,5 % x Hebesatz, abzueglich Anrechnung auf die
  Einkommensteuer (bis 4,0 x Messbetrag, hoechstens die Einkommensteuer) - bei Hebesatz <= 400 % meist ~0.
  Verluste mindern als Vortrag die Folgejahre (keine Verrechnung mit dem Gehalt).
- Kein Restwert am Ende des Horizonts.
- Diskontierung monatlich mit (1 + i)^(1/12) - 1; i = Opportunitaetsrendite p. a. (Standard 7 %).
- IRR: monatlicher Zinsfuss per Bisektion, auf p. a. hochgerechnet; ohne Vorzeichenwechsel "nicht definiert".
- Engpass-Kennzahl: Summe Gewinn nach Steuern (ohne Startinvestition) / Summe Stunden im Horizont; in der
  Anlaufzeit gelten die Anlauf-Stunden je Woche (x 52 / 12 je Monat).
- Max. Kapitalbedarf: tiefster Stand des kumulierten Cashflows (so viel Geld steckt man maximal hinein).
- Erwartungswert: NPV der drei Szenarien, gewichtet mit ihren Wahrscheinlichkeiten.
"""
from . import modell as M

SENSITIVITAET = 0.20
AMPEL = {"gruen": "🟢", "gelb": "🟡", "rot": "🔴"}
AMPEL_TEXT = {"gruen": "Grün", "gelb": "Gelb", "rot": "Rot"}
WOCHEN_JE_MONAT = 52 / 12
GEWST_FREIBETRAG = 24500.0
GEWST_MESSZAHL = 0.035
GEWST_ANRECHNUNG = 4.0


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


def jahressteuer(basis, satz, hebesatz_pct):
    """Steuer eines Jahres auf die Bemessungsgrundlage (nach Abschreibung und Verlustvortrag, > 0).
    -> (Einkommensteuer, Gewerbesteuer nach Anrechnung)"""
    if basis <= 0:
        return 0.0, 0.0
    est = basis * satz
    mess = max(basis - GEWST_FREIBETRAG, 0.0) * GEWST_MESSZAHL
    gewst = mess * hebesatz_pct / 100
    anrechnung = min(GEWST_ANRECHNUNG * mess, est, gewst)
    return est - anrechnung, gewst


def stunden_im_monat(fin, m):
    anlauf = int(fin["anlauf_monate"])
    woche = fin.get("stunden_anlauf_woche", fin["stunden_woche"]) if 0 < m <= anlauf else fin["stunden_woche"]
    return float(woche) * WOCHEN_JE_MONAT


def verlauf(fin, umsatz_faktor=1.0, kosten_faktor=1.0):
    """-> Liste je Monat 0..N: {monat, umsatz, kosten, gewinn_vor, steuer, cashflow, kumuliert, stunden}"""
    u_voll = float(fin["umsatz_monat"]) * umsatz_faktor
    var = float(fin["var_kosten_pct"]) / 100 * kosten_faktor
    fix = float(fin["fix_monat"]) * kosten_faktor
    st = float(fin["steuersatz_pct"]) / 100
    hebesatz = float(fin.get("hebesatz_pct", 400.0))
    anlauf = int(fin["anlauf_monate"])
    invest = float(fin["start_invest"])
    afa_jahre = int(fin.get("afa_jahre", 0))
    start = -invest
    aus = [{"monat": 0, "umsatz": 0.0, "kosten": 0.0, "gewinn_vor": 0.0, "steuer": 0.0, "cashflow": start,
            "kumuliert": start, "stunden": 0.0}]
    kum, jahr_gewinn, vortrag = start, 0.0, 0.0
    for m in range(1, monate(fin) + 1):
        u = u_voll * (min(m / anlauf, 1.0) if anlauf > 0 else 1.0)
        kosten = u * var + fix
        g = u - kosten
        jahr_gewinn += g
        steuer = 0.0
        if m % 12 == 0:                                  # Jahresabschluss: Steuer fuer dieses Geschaeftsjahr
            jahr = m // 12
            afa = (invest / afa_jahre if jahr <= afa_jahre else 0.0) if afa_jahre > 0 else (invest if jahr == 1 else 0.0)
            basis = jahr_gewinn - afa
            if basis <= 0:
                vortrag += -basis
            else:
                verrechnet = min(vortrag, basis)
                basis -= verrechnet
                vortrag -= verrechnet
                est, gewst = jahressteuer(basis, st, hebesatz)
                steuer = est + gewst
            jahr_gewinn = 0.0
        cf = g - steuer
        kum += cf
        aus.append({"monat": m, "umsatz": u, "kosten": kosten, "gewinn_vor": g, "steuer": steuer, "cashflow": cf,
                    "kumuliert": kum, "stunden": stunden_im_monat(fin, m)})
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


IRR_RASTER = [-0.9, -0.5, -0.2, -0.1, -0.05, -0.02, 0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]


def irr(cashflows, iterationen=200):
    """Interner Zinsfuss p. a. (aus dem monatlichen Zinsfuss). None, wenn es keinen Vorzeichenwechsel gibt
    (z. B. nur Verluste oder keine Investition) oder keine Nullstelle im Suchbereich liegt.
    Suche: Vorzeichenwechsel des NPV auf einem Raster monatlicher Zinssaetze, der Wechsel naechst 0 gewinnt
    (die jaehrlichen Steuerzahlungen erzeugen mehrere Vorzeichenwechsel in den Cashflows), dann Bisektion."""
    if not (any(c < 0 for c in cashflows) and any(c > 0 for c in cashflows)):
        return None

    def f(r):
        return sum(cf / (1 + r) ** t for t, cf in enumerate(cashflows))
    werte = [(r, f(r)) for r in IRR_RASTER]
    klammern = [(a, fa, b, fb) for (a, fa), (b, fb) in zip(werte, werte[1:]) if fa == 0 or fa * fb < 0]
    # NPV bei 0 % positiv -> der Zinsfuss liegt darueber (kleinste positive Nullstelle), sonst darunter
    klammern = ([k for k in klammern if k[0] >= 0] if f(0.0) > 0 else
                sorted((k for k in klammern if k[2] <= 0), key=lambda k: -k[0]))
    if not klammern:
        return None
    lo, f_lo, hi, f_hi = klammern[0]
    if f_lo == 0:
        return (1 + lo) ** 12 - 1
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
    """Gewinn nach Steuern (ohne Startinvestition) / Stunden im Horizont. None ohne Stunden."""
    h = sum(z.get("stunden", 0.0) for z in v[1:])
    if h <= 0:
        return None
    return sum(z["cashflow"] for z in v[1:]) / h


def kapitalbedarf(v):
    """Tiefster Stand des kumulierten Cashflows. -> (Betrag >= 0, Monat)"""
    tief = min(v, key=lambda z: z["kumuliert"])
    return max(-tief["kumuliert"], 0.0), tief["monat"]


def szenario(fin, faktoren, zins_pa):
    v = verlauf(fin, faktoren["umsatz"], faktoren["kosten"])
    cfs = [z["cashflow"] for z in v]
    kb, kb_monat = kapitalbedarf(v)
    return {"verlauf": v, "npv": npv(cfs, zins_pa), "irr": irr(cfs), "amortisation": amortisation(v),
            "kapitalbedarf": kb, "kapitalbedarf_monat": kb_monat, "steuer": sum(z["steuer"] for z in v),
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


def mindest_stundensatz(einstellungen):
    """Mindest-Stundensatz: aus dem Netto-Stundenlohn des Hauptjobs (falls gewaehlt und angegeben), sonst fest."""
    e = einstellungen
    netto, h = float(e.get("netto_monat_job") or 0), float(e.get("stunden_woche_job") or 0)
    if e.get("mindest_aus_job") and netto > 0 and h > 0:
        return netto / (h * WOCHEN_JE_MONAT)
    return float(e["mindest_stundensatz"])


def engpass_score(idee):
    return float((idee.get("phasen") or {}).get(M.ENGPASS_PHASE, {}).get("score", M.SCORE_START))


def ampel(nw, npv_real, eur_h, einstellungen, eks=None, engpass=None):
    """Vier Bedingungen: Nutzwert >= Schwelle, NPV (realistisch) > 0, €/h >= Mindestsatz und EKS (EKS-Score >=
    Schwelle UND brennendstes Problem = Phase 4 >= Mindestwert). Gruen: alle erfuellt; Gelb: genau eine verfehlt;
    Rot: zwei oder mehr. Ohne Stunden (0 h/Woche) gilt die Stunden-Bedingung als erfuellt; ohne EKS-Angaben
    (eks None) entfaellt die EKS-Bedingung. -> (ampel, [verfehlte Bedingungen])"""
    e = einstellungen
    verfehlt = []
    if nw is None or nw < float(e["schwelle_nutzwert"]):
        verfehlt.append("Nutzwert unter Schwelle")
    if not npv_real > 0:
        verfehlt.append("NPV (realistisch) nicht positiv")
    if eur_h is not None and eur_h < mindest_stundensatz(e):
        verfehlt.append("€/Stunde unter Mindestsatz")
    if eks is not None:
        teile = []
        if eks < float(e.get("schwelle_eks", 60)):
            teile.append("EKS-Score unter Schwelle")
        if engpass is not None and engpass < float(e.get("min_engpass", 6)):
            teile.append("Engpass (Phase 4) zu schwach")
        if teile:
            verfehlt.append(" und ".join(teile))
    return ("gruen" if not verfehlt else "gelb" if len(verfehlt) == 1 else "rot"), verfehlt


def erwartungswert(sz):
    """NPV der Szenarien gewichtet mit ihren Wahrscheinlichkeiten (Gewichte normiert). None ohne Gewichte."""
    g = {k: float(s.get("gewicht", 0)) for k, s in sz.items()}
    summe = sum(g.values())
    return sum(g[k] * sz[k]["npv"] for k in sz) / summe if summe > 0 else None


# ---------------------------------------------------------------- Ist-Werte und Abbruch-Kriterien
def monat_index(start_monat, monat):
    """'2026-11' relativ zu Start '2026-10' -> 2 (Startmonat = Monat 1)."""
    y0, m0 = (int(x) for x in start_monat.split("-"))
    y, m = (int(x) for x in monat.split("-"))
    return (y - y0) * 12 + (m - m0) + 1


def ist_vergleich(idee, v_real):
    """Ist-Werte neben dem Plan (realistisches Szenario, vor Steuern). -> [{monat, m, plan_*, ist_*, kum_*}]"""
    aus, kum_plan, kum_ist = [], 0.0, 0.0
    plan = {z["monat"]: z for z in v_real[1:]}
    for z in idee.get("ist") or []:
        m = monat_index(idee["start_monat"], z["monat"])
        if m < 1:
            continue
        p = plan.get(m) or {"umsatz": 0.0, "kosten": 0.0, "gewinn_vor": 0.0, "stunden": 0.0}
        kum_plan += p["gewinn_vor"]
        kum_ist += z["umsatz"] - z["kosten"]
        aus.append({"monat": z["monat"], "m": m, "plan_umsatz": p["umsatz"], "ist_umsatz": z["umsatz"],
                    "plan_kosten": p["kosten"], "ist_kosten": z["kosten"], "plan_stunden": p["stunden"],
                    "ist_stunden": z["stunden"], "kum_plan": kum_plan, "kum_ist": kum_ist})
    return aus


def abbruch_pruefen(idee, vergleich):
    """Abbruch-Kriterien gegen die Ist-Werte. -> [Text je erreichtem Kriterium]"""
    treffer = []
    for k in idee.get("abbruch") or []:
        n, wert = k["nach_monaten"], k["wert"]
        erste = [z for z in vergleich if z["m"] <= n]
        text = M.ABBRUCH_ARTEN[k["art"]][0].format(wert=f"{wert:,.0f}".replace(",", "."), n=n)
        if not vergleich or max(z["m"] for z in vergleich) < n:
            continue                                     # noch nicht genug Monate erfasst
        if k["art"] == "umsatz_min":
            letzter = vergleich[-1]
            if letzter["ist_umsatz"] < wert:
                treffer.append(f"{text} – zuletzt {letzter['ist_umsatz']:,.0f} €".replace(",", "."))
        elif k["art"] == "gewinn_kum_min":
            g = sum(z["ist_umsatz"] - z["ist_kosten"] for z in erste)
            if g < wert:
                treffer.append(f"{text} – erreicht {g:,.0f} €".replace(",", "."))
        elif k["art"] == "eur_h_min":
            h = sum(z["ist_stunden"] for z in erste)
            g = sum(z["ist_umsatz"] - z["ist_kosten"] for z in erste)
            if h > 0 and g / h < wert:
                treffer.append(f"{text} – erreicht {g / h:.2f} €".replace(".", ","))
        elif k["art"] == "stunden_max" and erste:
            woche = sum(z["ist_stunden"] for z in erste) / len(erste) / WOCHEN_JE_MONAT
            if woche > wert:
                treffer.append(f"{text} – Ø {woche:.1f} h".replace(".", ","))
    return treffer


def auswerten(idee, einstellungen):
    """Alle Kennzahlen einer Idee. -> dict (nutzwert, eks, szenarien {pess|real|opt}, sensitivitaet, ampel ...)"""
    e = einstellungen
    zins = float(e["diskont_pa"]) / 100
    fin = idee["finanzen"]
    sz = {k: szenario(fin, idee["szenarien"][k], zins) for k in M.SZENARIEN}
    nw = nutzwert(idee, e["kriterien"])
    real = sz["real"]
    eks, engpass = eks_score(idee), engpass_score(idee)
    a, verfehlt = ampel(nw, real["npv"], real["euro_h"], e, eks, engpass)
    for k in sz:
        sz[k]["gewicht"] = idee["szenarien"][k].get("gewicht", 0.0)
    vgl = ist_vergleich(idee, real["verlauf"])
    return {"id": idee["id"], "name": idee["name"], "status": idee["status"], "nutzwert": nw,
            "eks": eks, "engpass": engpass, "szenarien": sz, "npv": real["npv"], "irr": real["irr"],
            "e_npv": erwartungswert(sz), "kapitalbedarf": real["kapitalbedarf"],
            "kapitalbedarf_monat": real["kapitalbedarf_monat"], "mindest_stundensatz": mindest_stundensatz(e),
            "ist_vergleich": vgl, "abbruch": abbruch_pruefen(idee, vgl),
            "amortisation": real["amortisation"], "euro_h": real["euro_h"],
            "break_even_umsatz": real["break_even_umsatz"], "break_even_monat": real["break_even_monat"],
            "sensitivitaet": sensitivitaet(fin, idee["szenarien"]["real"], zins), "ampel": a, "verfehlt": verfehlt,
            "stunden_monat": stunden_monat(fin), "stunden_summe": sum(z["stunden"] for z in real["verlauf"])}


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
                      "EKS-Score": round(r["eks"], 1), "Engpass (Phase 4)": r["engpass"],
                      "NPV €": round(r["npv"], 2),
                      "NPV Erwartungswert €": None if r["e_npv"] is None else round(r["e_npv"], 2),
                      "Max. Kapitalbedarf €": round(r["kapitalbedarf"], 2),
                      "IRR % p. a.": None if r["irr"] is None else round(r["irr"] * 100, 2),
                      "Amortisation Monate": r["amortisation"],
                      "€ je Stunde": None if r["euro_h"] is None else round(r["euro_h"], 2)} for r in rang}
