"""Etappe 3: erweiterte Fundamentalanalyse aus den Abschlussdaten der Investoren-Checks (investor_checks.daten).

Vier getrennte Teilbewertungen (je 0-100, nur ANGEZEIGT - kein Einfluss auf bestehende Scores oder die Auswahl):
  earnings_quality      Wie zuverlaessig sind die Gewinne? (Accruals, Cash-Deckung, Forderungen/Lager, Sondereffekte)
  economic_profitability Verdient das Unternehmen mehr als seine Kapitalkosten? (ROCE, Cash-ROIC, ROTC,
                        Gross Profitability, ROIC-WACC-Spread, inkrementeller ROIC)
  cashflow_quality      Wie robust und frei ist der Cashflow? (FCF-Marge nach aktienbasierter Verguetung,
                        Stabilitaet, positive Jahre, Ausschuettungsdeckung, FCF je Aktie)
  capital_allocation    Wie gut wird Kapital eingesetzt? (Verwaesserung, Verguetung in Aktien, Zukaufquote,
                        Rendite reinvestierter Mittel, Buchwert je Aktie, Aktionaersrendite)

Grundsaetze:
- Je Kennzahl 0-100 Punkte linear zwischen "schwach" und "stark" (SCHWELLEN, an einer Stelle aenderbar).
- Fehlende Daten werden nie erfunden: Kennzahl entfaellt, das Modul rechnet mit den vorhandenen (mind. 2).
- Branchenregeln: bei Banken/Versicherern sind cashflow- und kapitalbasierte Kennzahlen nicht anwendbar
  (Kennzeichnung "nicht anwendbar", kein Nachteil).
- Ueberschneidung: ROIC, Verwaesserung und FCF stecken auch im Qualitaets-Score - diese Module sind deshalb
  eigenstaendige Teilbewertungen und werden NICHT zum bestehenden Score addiert.
- Auffaellige Werte sind Risikohinweise, kein Beweis fuer Bilanzmanipulation.
"""
import statistics

import investor_config as C
from investor_checks import basis as IB

# Kennzahl: (schwach, stark) - linear dazwischen; schwach > stark heisst "niedriger ist besser"
SCHWELLEN = {
    # Earnings Quality
    "sloan": (0.10, -0.05),            # (Nettogewinn - operativer Cashflow) / Ø Bilanzsumme (Sloan 1996)
    "ocf_ni": (0.6, 1.1),              # operativer Cashflow / Nettogewinn (Ø 3 Jahre, nur bei Gewinn)
    "cfoa": (0.0, 0.15),               # operativer Cashflow / Bilanzsumme
    "dso_delta": (20.0, 0.0),          # Anstieg der Forderungslaufzeit in Tagen (erstes -> letztes Jahr)
    "dio_delta": (30.0, 0.0),          # Anstieg der Lagerdauer in Tagen
    "sonder_anteil": (0.30, 0.0),      # |Sondereffekte| / |Nettogewinn|
    # Wirtschaftliche Profitabilitaet
    "roce": (0.05, 0.25),              # EBIT / (Bilanzsumme - kurzfristige Verbindlichkeiten)
    "cash_roic": (0.0, 0.20),          # FCF / investiertes Kapital
    "rotc": (0.05, 0.40),              # NOPAT / (investiertes Kapital - Goodwill)
    "gross_prof": (0.10, 0.40),        # Bruttogewinn / Bilanzsumme (Novy-Marx 2013)
    "roic_wacc": (-0.05, 0.10),        # ROIC - WACC (Modellannahme Kapitalkosten)
    "inkr_roic": (0.0, 0.25),          # Zuwachs NOPAT / Zuwachs investiertes Kapital (erstes -> letztes Jahr)
    # Cashflow-Qualitaet
    "fcf_marge_sbc": (0.0, 0.20),      # (FCF - aktienbasierte Verguetung) / Umsatz
    "fcf_schwankung": (1.0, 0.15),     # Variationskoeffizient der FCF-Marge
    "fcf_positiv": (0.5, 1.0),         # Anteil der Jahre mit positivem FCF
    "ausschuettung_deckung": (0.8, 2.0),   # FCF / (Dividenden + Rueckkaeufe)
    "fcfps_cagr": (-0.05, 0.12),       # FCF je Aktie p. a.
    # Kapitalallokation
    "verwaesserung": (0.04, -0.02),    # Aktienanzahl p. a.
    "sbc_umsatz": (0.10, 0.01),        # aktienbasierte Verguetung / Umsatz
    "akq_quote": (1.0, 0.1),           # Zukaeufe / operativer Cashflow (kumuliert)
    "reinvest_rendite": (0.0, 0.25),   # Zuwachs EBIT / Summe Nettoinvestitionen (Capex - Abschreibungen + Zukaeufe)
    "bvps_cagr": (-0.02, 0.12),        # Buchwert je Aktie p. a.
    "shareholder_yield": (0.0, 0.06),  # (Dividenden + Rueckkaeufe - Emissionen) / Boersenwert
}
MODULE = {
    "earnings_quality": ("Earnings Quality", ("sloan", "ocf_ni", "cfoa", "dso_delta", "dio_delta", "sonder_anteil")),
    "economic_profitability": ("Wirtschaftliche Profitabilität",
                               ("roce", "cash_roic", "rotc", "gross_prof", "roic_wacc", "inkr_roic")),
    "cashflow_quality": ("Cashflow-Qualität",
                         ("fcf_marge_sbc", "fcf_schwankung", "fcf_positiv", "ausschuettung_deckung", "fcfps_cagr")),
    "capital_allocation": ("Kapitalallokation", ("verwaesserung", "sbc_umsatz", "akq_quote", "reinvest_rendite",
                                                 "bvps_cagr", "shareholder_yield")),
}
TITEL = {
    "sloan": "Accrual-Quote (Sloan)", "ocf_ni": "Operativer Cashflow / Gewinn", "cfoa": "Cashflow / Bilanzsumme",
    "dso_delta": "Forderungslaufzeit (Veränderung, Tage)", "dio_delta": "Lagerdauer (Veränderung, Tage)",
    "sonder_anteil": "Sondereffekte / Gewinn", "roce": "ROCE", "cash_roic": "Cash-ROIC",
    "rotc": "Rendite auf Sachkapital (ROTC)", "gross_prof": "Gross Profitability", "roic_wacc": "ROIC − Kapitalkosten",
    "inkr_roic": "Inkrementeller ROIC", "fcf_marge_sbc": "FCF-Marge nach Aktienvergütung",
    "fcf_schwankung": "Schwankung der FCF-Marge", "fcf_positiv": "Jahre mit positivem FCF",
    "ausschuettung_deckung": "Ausschüttungsdeckung durch FCF", "fcfps_cagr": "FCF je Aktie p. a.",
    "verwaesserung": "Aktienanzahl p. a.", "sbc_umsatz": "Aktienvergütung / Umsatz", "akq_quote": "Zukäufe / Cashflow",
    "reinvest_rendite": "Rendite reinvestierter Mittel", "bvps_cagr": "Buchwert je Aktie p. a.",
    "shareholder_yield": "Aktionärsrendite",
}
# als Prozent anzeigen (Rest: Faktor bzw. Tage)
PROZENT = {"sloan", "cfoa", "sonder_anteil", "roce", "cash_roic", "rotc", "gross_prof", "roic_wacc", "inkr_roic",
           "fcf_marge_sbc", "fcf_positiv", "fcfps_cagr", "verwaesserung", "sbc_umsatz", "akq_quote",
           "reinvest_rendite", "bvps_cagr", "shareholder_yield"}
# Bei Banken/Versicherern nicht aussagekraeftig (operativer Cashflow, Umlaufvermoegen, EBIT, Bruttogewinn)
NICHT_BANK = {"sloan", "ocf_ni", "cfoa", "dso_delta", "dio_delta", "roce", "cash_roic", "rotc", "gross_prof",
              "roic_wacc", "inkr_roic", "fcf_marge_sbc", "fcf_schwankung", "fcf_positiv", "ausschuettung_deckung",
              "fcfps_cagr", "akq_quote", "reinvest_rendite"}
MARKTRISIKOPRAEMIE = 5.0     # % - Modellannahme fuer die Eigenkapitalkosten (CAPM)
MIN_KENNZAHLEN = 2


def _z(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _t(a, b):
    a, b = _z(a), _z(b)
    return a / b if a is not None and b not in (None, 0) else None


def punkte(schluessel, wert):
    """0-100 linear zwischen schwach und stark (begrenzt)."""
    if wert is None:
        return None
    schwach, stark = SCHWELLEN[schluessel]
    p = (wert - schwach) / (stark - schwach) * 100
    return max(0.0, min(100.0, p))


def _cagr(erst, letzt, jahre):
    erst, letzt = _z(erst), _z(letzt)
    if not erst or not letzt or erst <= 0 or letzt <= 0 or jahre <= 0:
        return None
    return (letzt / erst) ** (1 / jahre) - 1


def _steuersatz(j):
    t = _t(j.get("steuern"), j.get("vor_steuern"))
    return t if t is not None and 0.0 <= t <= 0.5 else C.BUFFETT["steuersatz"] / 100


def _ic(j):
    ek, sch, cash = _z(j.get("ek")), _z(j.get("schulden")) or 0.0, _z(j.get("cash")) or 0.0
    return ek + sch - cash if ek is not None else None


def _nopat(j):
    ebit = _z(j.get("ebit"))
    return ebit * (1 - _steuersatz(j)) if ebit is not None else None


def kennzahlen(f):
    """f: fakten (investor_checks.daten) -> ({kennzahl: wert}, warnungen, nicht_anwendbar)"""
    J = [j for j in (f.get("jahre") or []) if j]
    typ = IB.sektor_typ(f)
    k, warn = {}, []
    if not J:
        return k, ["keine Abschlussdaten"], []
    a, z = J[0], J[-1]
    n = max(len(J) - 1, 1)
    jahre_span = n

    # --- Earnings Quality ---
    bil = [_z(j.get("bilanzsumme")) for j in J[-2:] if _z(j.get("bilanzsumme"))]
    if _z(z.get("nettogewinn")) is not None and _z(z.get("op_cf")) is not None and bil:
        k["sloan"] = (z["nettogewinn"] - z["op_cf"]) / (sum(bil) / len(bil))
    paare = [(j.get("op_cf"), j.get("nettogewinn")) for j in J[-3:]
             if _z(j.get("op_cf")) is not None and (_z(j.get("nettogewinn")) or 0) > 0]
    if paare:
        k["ocf_ni"] = sum(o for o, _ in paare) / sum(g for _, g in paare)
    k["cfoa"] = _t(z.get("op_cf"), z.get("bilanzsumme"))

    def tage(j, feld, basis):
        return _t(j.get(feld), basis) * 365 if _t(j.get(feld), basis) is not None else None
    dso_a, dso_z = tage(a, "forderungen", a.get("umsatz")), tage(z, "forderungen", z.get("umsatz"))
    if dso_a is not None and dso_z is not None and len(J) >= 2:
        k["dso_delta"] = dso_z - dso_a
    kosten = lambda j: (_z(j.get("umsatz")) - _z(j.get("bruttogewinn"))) \
        if _z(j.get("umsatz")) is not None and _z(j.get("bruttogewinn")) is not None else None  # noqa: E731
    dio_a, dio_z = tage(a, "lager", kosten(a)), tage(z, "lager", kosten(z))
    if dio_a is not None and dio_z is not None and len(J) >= 2 and (_z(z.get("lager")) or 0) > 0:
        k["dio_delta"] = dio_z - dio_a
    if _z(z.get("sonder")) is not None and _z(z.get("nettogewinn")):
        k["sonder_anteil"] = abs(z["sonder"]) / abs(z["nettogewinn"])
    steuer = _t(z.get("steuern"), z.get("vor_steuern"))
    if steuer is not None and (_z(z.get("vor_steuern")) or 0) > 0 and steuer < 0.10:
        warn.append(f"sehr niedrige Steuerquote ({steuer * 100:.0f} %) – Nachhaltigkeit prüfen")

    # --- Wirtschaftliche Profitabilitaet ---
    k["roce"] = _t(z.get("ebit"), (_z(z.get("bilanzsumme")) or 0) - (_z(z.get("kurzfr_verb")) or 0)) \
        if _z(z.get("bilanzsumme")) else None
    ic = _ic(z)
    k["cash_roic"] = _t(z.get("fcf"), ic) if ic and ic > 0 else None
    gw = _z(z.get("goodwill")) or 0.0
    k["rotc"] = _t(_nopat(z), ic - gw) if ic and ic - gw > 0 else None
    k["gross_prof"] = _t(z.get("bruttogewinn"), z.get("bilanzsumme"))
    roic = _t(_nopat(z), ic) if ic and ic > 0 else None
    wacc = _wacc(f, z)
    if roic is not None and wacc is not None:
        k["roic_wacc"] = roic - wacc
        k["_wacc"] = wacc
    ic_a = _ic(a)
    if len(J) >= 3 and ic and ic_a and _nopat(z) is not None and _nopat(a) is not None and ic - ic_a > 0:
        k["inkr_roic"] = (_nopat(z) - _nopat(a)) / (ic - ic_a)

    # --- Cashflow-Qualitaet ---
    if _z(z.get("fcf")) is not None and _z(z.get("umsatz")):
        k["fcf_marge_sbc"] = (z["fcf"] - (_z(z.get("sbc")) or 0.0)) / z["umsatz"]
    margen = [_t(j.get("fcf"), j.get("umsatz")) for j in J]
    margen = [m for m in margen if m is not None]
    if len(margen) >= 3 and statistics.mean(margen) > 0:
        k["fcf_schwankung"] = statistics.pstdev(margen) / statistics.mean(margen)
    fcfs = [_z(j.get("fcf")) for j in J if _z(j.get("fcf")) is not None]
    if len(fcfs) >= 3:
        k["fcf_positiv"] = sum(1 for x in fcfs if x > 0) / len(fcfs)
    aus = (_z(z.get("dividenden")) or 0.0) + (_z(z.get("rueckkaeufe")) or 0.0)
    if aus > 0 and _z(z.get("fcf")) is not None:
        k["ausschuettung_deckung"] = z["fcf"] / aus
    k["fcfps_cagr"] = _cagr(_t(a.get("fcf"), a.get("aktien")), _t(z.get("fcf"), z.get("aktien")), jahre_span) \
        if len(J) >= 3 else None

    # --- Kapitalallokation ---
    k["verwaesserung"] = _cagr(a.get("aktien"), z.get("aktien"), jahre_span) if len(J) >= 2 else None
    k["sbc_umsatz"] = _t(z.get("sbc"), z.get("umsatz"))
    akq = sum(_z(j.get("akquisitionen")) or 0.0 for j in J)
    ocf = sum(_z(j.get("op_cf")) or 0.0 for j in J)
    if any(_z(j.get("akquisitionen")) is not None for j in J) and ocf > 0:
        k["akq_quote"] = akq / ocf
    netto = sum((_z(j.get("capex")) or 0.0) - (_z(j.get("abschreibungen")) or 0.0) + (_z(j.get("akquisitionen")) or 0.0)
                for j in J[1:])
    if len(J) >= 3 and netto > 0 and _z(z.get("ebit")) is not None and _z(a.get("ebit")) is not None:
        k["reinvest_rendite"] = (z["ebit"] - a["ebit"]) / netto
    k["bvps_cagr"] = _cagr(_t(a.get("ek"), a.get("aktien")), _t(z.get("ek"), z.get("aktien")), jahre_span) \
        if len(J) >= 2 else None
    mcap = _z(f.get("kurs_in_bericht")) * _z(z.get("aktien")) if _z(f.get("kurs_in_bericht")) and \
        _z(z.get("aktien")) else None
    if mcap:
        k["shareholder_yield"] = ((_z(z.get("dividenden")) or 0) + (_z(z.get("rueckkaeufe")) or 0)
                                  - (_z(z.get("emissionen")) or 0)) / mcap

    # Warnhinweise (Risikohinweise, kein Beweis)
    if (k.get("sloan") or 0) > 0.10:
        warn.append("hohe Accruals: Gewinn deutlich über dem operativen Cashflow")
    if k.get("ocf_ni") is not None and k["ocf_ni"] < 0.7:
        warn.append("Gewinn nur schwach durch Cashflow gedeckt")
    if (k.get("dso_delta") or 0) > 20:
        warn.append("Forderungslaufzeit stark gestiegen")
    if (k.get("sonder_anteil") or 0) > 0.30:
        warn.append("hoher Anteil von Sondereffekten am Gewinn")
    if (k.get("verwaesserung") or 0) > 0.05:
        warn.append("starke Verwässerung der Aktionäre")

    na = sorted(NICHT_BANK) if typ == "bank" else []
    for s_ in na:
        k.pop(s_, None)
    return {s_: v for s_, v in k.items() if v is not None}, warn, na


def _wacc(f, j):
    """Kapitalkosten (Modellannahme): CAPM fuer das Eigenkapital, Zinsaufwand/Schulden fuer das Fremdkapital."""
    rf = C.STAATSANLEIHE_10J / 100
    beta = _z(f.get("beta"))
    beta = min(max(beta, 0.5), 2.0) if beta is not None else 1.0
    ke = rf + beta * MARKTRISIKOPRAEMIE / 100
    aktien = _z(j.get("aktien")) or _z(f.get("aktien"))
    e = _z(f.get("kurs_in_bericht")) * aktien if _z(f.get("kurs_in_bericht")) and aktien else None
    d = _z(j.get("schulden")) or 0.0
    if not e or e <= 0:
        return None
    kd = _t(j.get("zinsaufwand"), d) if d > 0 else None
    kd = min(max(abs(kd), 0.01), 0.12) if kd is not None else rf + 0.02
    return e / (e + d) * ke + d / (e + d) * kd * (1 - _steuersatz(j))


def analyse(f):
    """-> {modul: {"score", "titel", "kennzahlen": {k: (wert, punkte)}}, "warnungen", "nicht_anwendbar", "wacc"}"""
    k, warn, na = kennzahlen(f)
    aus = {"warnungen": warn, "nicht_anwendbar": na, "wacc": k.pop("_wacc", None)}
    for modul, (titel, schl) in MODULE.items():
        werte = {s_: (k[s_], punkte(s_, k[s_])) for s_ in schl if s_ in k}
        p = [v[1] for v in werte.values() if v[1] is not None]
        aus[modul] = {"titel": titel, "score": round(sum(p) / len(p)) if len(p) >= MIN_KENNZAHLEN else None,
                      "kennzahlen": werte}
    return aus


def kompakt(a):
    """Speicherform fuer state/investoren/ergebnis_NN.json (Feld "x"): Scores, Kennzahlen gerundet, Warnungen."""
    kurz = {"earnings_quality": "eq", "economic_profitability": "pr", "cashflow_quality": "cf",
            "capital_allocation": "ka"}
    aus = {kurz[m]: a[m]["score"] for m in MODULE}
    aus["k"] = {s_: round(w, 4) for m in MODULE for s_, (w, _) in a[m]["kennzahlen"].items()}
    if a.get("wacc") is not None:
        aus["wacc"] = round(a["wacc"], 4)
    if a.get("warnungen"):
        aus["w"] = a["warnungen"][:5]
    if a.get("nicht_anwendbar"):
        aus["na"] = 1
    return aus


def anzeigen(x):
    """Speicherform -> [(Modultitel, Score, [(Kennzahl-Titel, Text, Punkte)])] fuer die Oberflaeche."""
    if not x:
        return []
    lang = {"eq": "earnings_quality", "pr": "economic_profitability", "cf": "cashflow_quality",
            "ka": "capital_allocation"}
    k = x.get("k") or {}
    aus = []
    for kurz_, modul in lang.items():
        titel, schl = MODULE[modul]
        zeilen = []
        for s_ in schl:
            if s_ not in k:
                continue
            w = k[s_]
            txt = (f"{w * 100:.1f} %" if s_ in PROZENT else f"{w:.0f} Tage" if s_.endswith("_delta")
                   else f"{w:.2f}").replace(".", ",")
            zeilen.append((TITEL[s_], txt, round(punkte(s_, w))))
        aus.append((titel, x.get(kurz_), zeilen))
    return aus
