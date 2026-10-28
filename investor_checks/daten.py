"""Normierte Rohdaten ("fakten") einer Aktie fuer die Investoren-Checks.

Quelle: yfinance (kostenlos; Yahoo Finance). Abruf und Caching macht die Oberflaeche (st.cache_data:
Fundamentaldaten 24 h, Kurse 15 Min.) - dieses Modul wandelt nur um und ist ohne Netz testbar.

fakten = {
  symbol, name, sektor, branche, land, waehrung (Berichtswaehrung), kurs_waehrung, usd_faktor,
  kurs, mcap, aktien, kbv, kuv, beta, zyklisch,
  jahre:    [ {datum, umsatz, bruttogewinn, ebit, ebitda, nettogewinn, eps, abschreibungen, zinsaufwand, fue, sga,
               op_cf, capex, fcf, dividenden, rueckkaeufe, emissionen, umlauf, kurzfr_verb, langfr_schulden,
               schulden, verbindlichkeiten, ek, bilanzsumme, gewinnruecklagen, forderungen, lager, goodwill,
               sachanlagen, cash, aktien} ... ]   aelteste zuerst; Capex/Dividenden/Rueckkaeufe POSITIV
  quartale: dieselben Felder je Quartal (soweit vorhanden), aelteste zuerst
  kurse:    [(datum 'YYYY-MM-DD', schluss, volumen), ...] taeglich, aelteste zuerst
  dividenden_hist: [(datum, betrag je Aktie), ...]
  analysten: Konsens, Kursziele (Yahoo-Info)
  insider:  [{datum, art kauf/verkauf/sonstig, stueck, wert}]
  revisionen: {periode: {hoch30, runter30, hoch7, runter7}}   (Anzahl Analysten, die die EPS-Schaetzung aendern)
  index_kurse: [(datum, schluss, volumen)] des Leitindex (CAN SLIM "M"), index_name
}
"""
import math

from .basis import zahl

# Yahoo-Zeilennamen -> eigenes Feld (erste vorhandene Zeile gewinnt). Vorzeichen: Yahoo fuehrt Abfluesse
# (Capex, Dividenden, Rueckkaeufe) negativ - hier als positive Betraege (VORZEICHEN = -1).
ZEILEN = {
    "umsatz": ["Total Revenue", "Operating Revenue"],
    "bruttogewinn": ["Gross Profit"],
    "ebit": ["EBIT", "Operating Income"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "nettogewinn": ["Net Income Common Stockholders", "Net Income", "Net Income From Continuing Operation Net Minority Interest"],
    "eps": ["Diluted EPS", "Basic EPS"],
    "abschreibungen": ["Reconciled Depreciation", "Depreciation And Amortization",
                       "Depreciation Amortization Depletion"],
    "zinsaufwand": ["Interest Expense", "Interest Expense Non Operating"],
    "fue": ["Research And Development"],
    "sga": ["Selling General And Administration"],
    "op_cf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure"],
    "fcf": ["Free Cash Flow"],
    "dividenden": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "rueckkaeufe": ["Repurchase Of Capital Stock", "Common Stock Payments"],
    "emissionen": ["Issuance Of Capital Stock", "Common Stock Issuance"],
    "umlauf": ["Current Assets"],
    "kurzfr_verb": ["Current Liabilities"],
    "langfr_schulden": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "schulden": ["Total Debt"],
    "verbindlichkeiten": ["Total Liabilities Net Minority Interest", "Total Liabilities"],
    "ek": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
    "bilanzsumme": ["Total Assets"],
    "gewinnruecklagen": ["Retained Earnings"],
    "forderungen": ["Accounts Receivable", "Receivables"],
    "lager": ["Inventory"],
    "goodwill": ["Goodwill"],
    "sachanlagen": ["Net PPE"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "aktien": ["Ordinary Shares Number", "Share Issued", "Diluted Average Shares"],
}
VORZEICHEN = {"capex": -1, "dividenden": -1, "rueckkaeufe": -1}


def _spalten_werte(df):
    """DataFrame (Zeilen = Posten, Spalten = Stichtage) -> {datum: {zeile: wert}}; NaN entfaellt."""
    aus = {}
    if df is None or getattr(df, "empty", True):
        return aus
    for spalte in df.columns:
        datum = str(getattr(spalte, "date", lambda: spalte)())[:10]
        werte = {}
        for zeile, w in df[spalte].items():
            w = zahl(w)
            if w is not None:
                werte[str(zeile)] = w
        if werte:
            aus.setdefault(datum, {}).update(werte)
    return aus


def perioden(*dataframes):
    """GuV, Bilanz, Cashflow (yfinance-DataFrames) -> [{datum, feld: wert}] aelteste zuerst.
    Perioden mit weniger als 4 Posten (Yahoo fuellt alte Spalten oft nur teilweise) fallen weg."""
    roh = {}
    for df in dataframes:
        for datum, werte in _spalten_werte(df).items():
            roh.setdefault(datum, {}).update(werte)
    aus = []
    for datum in sorted(roh):
        r = roh[datum]
        p = {"datum": datum}
        for feld, namen in ZEILEN.items():
            w = next((r[n] for n in namen if n in r), None)
            if w is not None:
                w = abs(w) if VORZEICHEN.get(feld) == -1 else w
            p[feld] = w
        if p.get("fcf") is None and p.get("op_cf") is not None and p.get("capex") is not None:
            p["fcf"] = p["op_cf"] - p["capex"]
        if sum(1 for k, v in p.items() if k != "datum" and v is not None) >= 4:
            aus.append(p)
    return aus


def kursreihe(hist):
    """yfinance history() -> [(datum, schluss, volumen)]."""
    if hist is None or getattr(hist, "empty", True):
        return []
    aus = []
    for idx, z in hist.iterrows():
        c = zahl(z.get("Close"))
        if c is None:
            continue
        aus.append((str(getattr(idx, "date", lambda: idx)())[:10], c, zahl(z.get("Volume")) or 0.0))
    return aus


def dividendenreihe(div):
    if div is None or getattr(div, "empty", True):
        return []
    return [(str(getattr(i, "date", lambda: i)())[:10], float(v)) for i, v in div.items() if zahl(v)]


def insider_liste(df):
    """yfinance insider_transactions -> [{datum, art (kauf/verkauf/sonstig), stueck, wert}].
    Yahoo liefert die Art nur als Text ("Sale at price ...", "Purchase at price ..."); Zuteilungen, Schenkungen
    und Optionsausuebungen zaehlen als "sonstig" (kein Signal)."""
    if df is None or getattr(df, "empty", True):
        return []
    aus = []
    for _, z in df.iterrows():
        text = f"{z.get('Text') or ''} {z.get('Transaction') or ''}".lower()
        art = ("kauf" if ("purchase" in text or "buy" in text) else
               "verkauf" if ("sale" in text or "sell" in text) else "sonstig")
        d = z.get("Start Date")
        aus.append({"datum": str(getattr(d, "date", lambda: d)())[:10] if d is not None else "",
                    "art": art, "stueck": zahl(z.get("Shares")) or 0.0, "wert": zahl(z.get("Value")) or 0.0})
    return aus


def revisionen(df):
    """yfinance eps_revisions -> {periode: {"hoch30": n, "runter30": n, "hoch7": n, "runter7": n}}.
    Spaltennamen schreibt Yahoo uneinheitlich (upLast30days / downLast30Days) - daher klein vergleichen."""
    if df is None or getattr(df, "empty", True):
        return {}
    aus = {}
    for periode, z in df.iterrows():
        werte = {str(k).lower(): zahl(v) for k, v in z.items()}
        aus[str(periode)] = {"hoch30": werte.get("uplast30days"), "runter30": werte.get("downlast30days"),
                             "hoch7": werte.get("uplast7days"), "runter7": werte.get("downlast7days")}
    return aus


def fakten_aus_yfinance(info, gj, bilanz, cashflow, q_gj=None, q_bilanz=None, q_cashflow=None, hist=None,
                        dividenden=None, fx=None, agent=None, insider=None, eps_revisionen=None, index_hist=None,
                        index_name=""):
    """Baut die normierten Fakten. fx: {Waehrung: Kurs je EUR} (state/top50_fx.json) fuer die USD-Umrechnung.
    agent: Eintrag aus der Bewertung (scoring.universum) - Sektor-Fallback und Zyklik-Kennzeichen."""
    info = info or {}
    agent = agent or {}
    wae = info.get("financialCurrency") or info.get("currency") or ""
    f = {
        "symbol": info.get("symbol") or agent.get("ticker") or "",
        "name": info.get("longName") or info.get("shortName") or agent.get("name") or "",
        "sektor": info.get("sector") or "", "branche": info.get("industry") or agent.get("sektor") or "",
        "land": info.get("country") or "", "waehrung": wae, "kurs_waehrung": info.get("currency") or "",
        "kurs": zahl(info.get("currentPrice")) or zahl(info.get("regularMarketPrice")) or zahl(agent.get("kurs")),
        "mcap": zahl(info.get("marketCap")), "aktien": zahl(info.get("sharesOutstanding")),
        "kbv": zahl(info.get("priceToBook")), "kuv": zahl(info.get("priceToSalesTrailing12Months")),
        "beta": zahl(info.get("beta")), "zyklisch": bool((agent.get("info") or {}).get("zykl")),
        "usd_faktor": usd_faktor(wae, fx),
        "jahre": perioden(gj, bilanz, cashflow),
        "quartale": perioden(q_gj, q_bilanz, q_cashflow),
        "kurse": kursreihe(hist),
        "dividenden_hist": dividendenreihe(dividenden),
        "beschreibung": info.get("longBusinessSummary") or "",
        "mitarbeiter": zahl(info.get("fullTimeEmployees")),
        "analysten": {k: info.get(k) for k in ("recommendationMean", "recommendationKey", "targetMeanPrice",
                                              "targetLowPrice", "targetHighPrice", "numberOfAnalystOpinions",
                                              "earningsGrowth", "revenueGrowth")},
        "insider": insider_liste(insider),
        "revisionen": revisionen(eps_revisionen),
        "index_kurse": kursreihe(index_hist), "index_name": index_name,
        "div_rendite": zahl(info.get("dividendYield")),
        "short": {k: info.get(k) for k in ("shortRatio", "shortPercentOfFloat", "heldPercentInstitutions",
                                          "heldPercentInsiders")},
    }
    # Kurs in einer anderen Waehrung als die Bilanz (z. B. ADRs, GBp): Faktor fuer Je-Aktie-Vergleiche
    f["kurs_in_bericht"] = kurs_in_berichtswaehrung(f["kurs"], f["kurs_waehrung"], wae, fx)
    return f


UNTERWAEHRUNG = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ILA": ("ILS", 100), "ZAc": ("ZAR", 100)}


def usd_faktor(waehrung, fx):
    """Faktor Berichtswaehrung -> USD aus den EUR-Kursen der App ({W: Einheiten je 1 EUR})."""
    if not waehrung:
        return None
    if waehrung == "USD":
        return 1.0
    w, teiler = UNTERWAEHRUNG.get(waehrung, (waehrung, 1))
    fx = fx or {}
    if w == "EUR":
        eur = 1.0
    else:
        eur = zahl(fx.get(w))
    usd = zahl(fx.get("USD"))
    if not eur or not usd:
        return None
    return usd / eur / teiler


def kurs_in_berichtswaehrung(kurs, kurs_wae, bericht_wae, fx):
    """Aktienkurs umgerechnet in die Berichtswaehrung (fuer KGV, KBV, Graham-Zahl je Aktie)."""
    kurs = zahl(kurs)
    if kurs is None or not kurs_wae or not bericht_wae:
        return kurs
    if kurs_wae == bericht_wae:
        return kurs
    a, b = usd_faktor(kurs_wae, fx), usd_faktor(bericht_wae, fx)
    if not a or not b:
        return None                  # lieber n/a als ein Kurs in falscher Waehrung
    return kurs * a / b


def kurs_tief_hoch(f, tage):
    """(tief, hoch) der Schlusskurse der letzten `tage` Kalendertage."""
    k = f.get("kurse") or []
    if not k:
        return None, None
    import datetime as _dt
    ende = _dt.date.fromisoformat(k[-1][0])
    grenze = (ende - _dt.timedelta(days=tage)).isoformat()
    werte = [c for d, c, _ in k if d >= grenze]
    return (min(werte), max(werte)) if werte else (None, None)


def ist_leer(f):
    return not (f.get("jahre") or f.get("kurse")) or all(
        (v is None or (isinstance(v, float) and math.isnan(v))) for v in (f.get("kurs"),))


def sma(werte, n):
    """Gleitender Durchschnitt der letzten n Werte (None bei zu kurzer Reihe)."""
    if len(werte) < n:
        return None
    return sum(werte[-n:]) / n


def leitindex(f):
    """Yahoo-Symbol und Name des Leitindex fuer die Marktrichtung (CAN SLIM "M")."""
    land = (f.get("land") or "").lower()
    if land in ("united states", "usa", "") and (f.get("kurs_waehrung") in ("USD", "")):
        return "^GSPC", "S&P 500"
    if land == "germany":
        return "^GDAXI", "DAX"
    return "^STOXX", "STOXX Europe 600"
