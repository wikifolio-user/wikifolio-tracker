"""
Portfolio-Planer - DATEN & KONFIGURATION (keine Berechnungen, keine Oberflaeche).

Hier steht alles, was sich spaeter aendern laesst, ohne Programmcode anzufassen:
  - SEED_MODELL      Ausgangsdatensatz (Assets, Gewichte, Rahmenwerte)
  - SEED_ANNAHMEN    Renditeannahmen mit Herkunft ("Assumption Engine")
  - BEWERTUNGSREGELN Fundamental Score: Kategorien, Gewichte, Kennzahl-Schwellen
  - GRENZEN          Optimizer-Constraints
  - NACHKAUF / REBALANCING / STRESS / CONFIDENCE  Regeln und Parameter

Zwei getrennte Wahrheiten (zentraler Grundsatz):
  Historical Layer  = was tatsaechlich passiert ist (Kurshistorie, Kennzahlen) -
                      wird zur Laufzeit aus echten Daten geladen, NIE hier erfunden.
  Assumption Layer  = was fuer die Zukunftsrechnung angenommen wird - steht hier
                      als Seed und ist in der App frei aenderbar.

Keine externen Zahlen erfinden: Wo es keine belastbare Angabe gibt, steht None
und die App fordert eine eigene Annahme an.
"""

MODELL_VERSION = 1

# ---------------------------------------------------------------------------
# Kategorien - neue lassen sich einfach ergaenzen; die Berechnung arbeitet nur
# mit den Merkmalen der Kategorie (Typ fuer den Confidence Score, Standard-
# Drawdown fuer den Stresstest), nicht mit festen Namen.
# ---------------------------------------------------------------------------
KATEGORIEN = {
    "global_equity":   {"titel": "Global Equity",    "typ": "index"},
    "technology":      {"titel": "Technology",       "typ": "index"},
    "semiconductor":   {"titel": "Semiconductor",    "typ": "index"},
    "factor":          {"titel": "Factor",           "typ": "index"},
    "small_cap":       {"titel": "Small Cap",        "typ": "index"},
    "single_stock":    {"titel": "Single Stock",     "typ": "aktie"},
    "stock_basket":    {"titel": "Aktienkorb",       "typ": "aktie"},
    "wikifolio":       {"titel": "Wikifolio",        "typ": "wikifolio"},
    "leveraged_etf":   {"titel": "Leveraged ETF",    "typ": "hebel"},
    "crypto":          {"titel": "Crypto",           "typ": "krypto"},
    "mining":          {"titel": "Mining",           "typ": "index"},
    "cash":            {"titel": "Cash / Reserve",   "typ": "cash"},
}

# ---------------------------------------------------------------------------
# Rahmenwerte
# ---------------------------------------------------------------------------
SEED_RAHMEN = {
    "startkapital": 15000.0,
    "zielvermoegen": 100000.0,
    "horizont_jahre": 5,
    "sparrate_monat": 0.0,
    "kosten_beruecksichtigen": False,     # TER / Performance Fee in die Rechnung nehmen
    "methode": "manual",                  # aktive Renditequelle, siehe METHODEN
    "szenario": "base",                   # bear | base | bull | custom (fuer Methode "szenario")
    "korb_anteil": None,                  # None = Gewicht des Korb-Assets aus der Asset-Tabelle
}

METHODEN = {
    "manual":      "Meine Annahmen",
    "historical5Y": "Historische 5 Jahre",
    "historical10Y": "Historische 10 Jahre",
    "fundamentalModel": "Fundamental Scenario",
    "szenario":    "Bear / Base / Bull",
}

# ---------------------------------------------------------------------------
# Assets. Gewicht = Anteil am GESAMTportfolio in %.
# ACHTUNG: Die Startgewichte sind PLATZHALTER (die Gewichtung des bisherigen
# Modells liegt nicht vor) - in der App anpassen oder den Optimizer nutzen.
# ISIN/Ticker nur, wo sie sicher bekannt sind; sonst sucht die App per Name.
# ---------------------------------------------------------------------------
def _asset(id, name, kategorie, gewicht, *, ticker=None, isin=None, sub=None, region="Global",
           sektor="Diversifiziert", hebel=1.0, hebel_typ=None, ter=None, perf_fee=None,
           emittent=None, tech=None, semi=None, aktiv=True, bias=False, notiz=""):
    return {
        "id": id, "name": name, "ticker": ticker, "isin": isin, "category": kategorie,
        "subCategory": sub, "region": region, "sector": sektor, "targetWeight": gewicht,
        "leverage": hebel, "leverageType": hebel_typ, "expenseRatio": ter, "performanceFee": perf_fee,
        "emittent": emittent, "techAnteil": tech, "semiAnteil": semi, "enabled": aktiv,
        "historicalWinnerBias": bias, "notes": notiz,
    }


SEED_ASSETS = [
    # --- Wikifolios (Zertifikate von Lang & Schwarz) ---
    _asset("wf_ff", "FF Inlinetrading", "wikifolio", 10.0, emittent="Lang & Schwarz",
           notiz="WKN wird per Namenssuche ermittelt."),
    _asset("wf_hig", "Hauptindizes Global", "wikifolio", 10.0, ticker="LS9VFS", isin="DE000LS9VFS2",
           emittent="Lang & Schwarz"),
    _asset("wf_gwc", "Global Wealth Concentrated", "wikifolio", 10.0, emittent="Lang & Schwarz",
           notiz="WKN wird per Namenssuche ermittelt."),
    # --- Index-/ETF-Bausteine ---
    _asset("etf_allworld", "Vanguard FTSE All-World", "global_equity", 15.0, isin="IE00BK5BQT80"),
    _asset("etf_momentum", "MSCI World Momentum", "factor", 7.5, isin="IE00BP3QZ825", sub="Momentum"),
    _asset("etf_ndx", "Nasdaq 100", "technology", 7.5, isin="IE00B53SZB19", region="USA",
           sektor="Technologie-lastig"),
    _asset("etf_semi", "VanEck Semiconductor", "semiconductor", 5.0, isin="IE00BMC38736",
           sektor="Halbleiter", tech=1.0, semi=1.0),
    _asset("etf_ndx2x", "Amundi Nasdaq-100 Daily 2x Leveraged", "leveraged_etf", 5.0, isin="FR0010342592",
           region="USA", sektor="Technologie-lastig", hebel=2.0, hebel_typ="daily",
           notiz="Taegliche Hebelung: Langfristrendite ist NICHT 2x Indexrendite (Volatility Drag, "
                 "Finanzierungskosten) - eigene Renditeannahme."),
    _asset("etf_smallcap", "MSCI World Small Cap", "small_cap", 0.0, isin="IE00BF4RFH31", aktiv=False),
    _asset("etf_gold", "Gold Miners", "mining", 0.0, isin="IE00BQQP9F84", sektor="Rohstoffe", aktiv=False),
    _asset("etf_copper", "Copper Miners", "mining", 0.0, isin="IE0003Z9E2Y3", sektor="Rohstoffe", aktiv=False),
    # --- Fundamentaler Aktienkorb (als EIN Baustein, Zusammensetzung in SEED_KORB) ---
    _asset("korb", "Fundamental Growth Basket", "stock_basket", 20.0, bias=True,
           notiz="Aus Unternehmen zusammengestellt, die in den letzten Jahren stark gelaufen sind - "
                 "historische Renditen dieser Auswahl sind keine faire Zukunftserwartung."),
    # --- Nachkauf-/Liquiditaetsreserve ---
    _asset("reserve", "Nachkaufreserve", "cash", 10.0, region="-", sektor="Cash"),
]

# Aktienkorb: Gewicht INNERHALB des Korbs (Summe 100 %). Sektor/Region sind
# Stammdaten; yahoo = Symbol der Heimatboerse fuer die Kennzahlen des
# Qualitaets-Agenten (Fundamental Score).
SEED_KORB = [
    {"id": "nvda", "name": "Nvidia", "gewicht": 14.0, "yahoo": "NVDA", "isin": "US67066G1040",
     "sektor": "Halbleiter", "region": "USA"},
    {"id": "tsmc", "name": "TSMC", "gewicht": 14.0, "yahoo": "2330.TW", "isin": "US8740391003",
     "sektor": "Halbleiter", "region": "Taiwan"},
    {"id": "avgo", "name": "Broadcom", "gewicht": 12.0, "yahoo": "AVGO", "isin": "US11135F1012",
     "sektor": "Halbleiter", "region": "USA"},
    {"id": "lly", "name": "Eli Lilly", "gewicht": 10.0, "yahoo": "LLY", "isin": "US5324571083",
     "sektor": "Pharma", "region": "USA"},
    {"id": "su", "name": "Schneider Electric", "gewicht": 10.0, "yahoo": "SU.PA", "isin": "FR0000121972",
     "sektor": "Industrie/Elektrotechnik", "region": "Frankreich"},
    {"id": "meli", "name": "MercadoLibre", "gewicht": 10.0, "yahoo": "MELI", "isin": "US58733R1023",
     "sektor": "E-Commerce/Fintech", "region": "Lateinamerika"},
    {"id": "pwr", "name": "Quanta Services", "gewicht": 9.0, "yahoo": "PWR", "isin": "US74762E1029",
     "sektor": "Industrie/Infrastruktur", "region": "USA"},
    {"id": "fix", "name": "Comfort Systems USA", "gewicht": 8.0, "yahoo": "FIX", "isin": "US1999081045",
     "sektor": "Industrie/Infrastruktur", "region": "USA"},
    {"id": "asml", "name": "ASML", "gewicht": 7.0, "yahoo": "ASML.AS", "isin": "NL0010273215",
     "sektor": "Halbleiter", "region": "Niederlande"},
    {"id": "anet", "name": "Arista Networks", "gewicht": 6.0, "yahoo": "ANET", "isin": "US0404131064",
     "sektor": "Netzwerktechnik", "region": "USA"},
]
KORB_HALBLEITER = {"Halbleiter"}                     # fuer das Halbleiter-Exposure
KORB_TECH = {"Halbleiter", "Netzwerktechnik", "E-Commerce/Fintech"}

# ---------------------------------------------------------------------------
# ASSUMPTION ENGINE - Seed. Je Asset beliebig viele Annahmen mit Herkunft.
#   sourceType: historical5Y | historical10Y | analystInput | manualScenario |
#               fundamentalModel | bear | base | bull | custom
# historical5Y/10Y werden NICHT hier gesetzt, sondern zur Laufzeit aus der
# echten Kurshistorie berechnet (Historical Layer).
# ---------------------------------------------------------------------------
_SZENARIO_WIKI = "Frei gewählte Szenarioannahme – keine Prognose, keine historische Erwartungsrendite."
_AUSGANGSWERT = "Historischer / modellierter Ausgangswert aus dem bisherigen Modell – keine Zukunftsrendite."


def _annahme(asset_id, wert, quelle, notiz, stand="2026-09-28", beobachtung=None):
    return {"assetId": asset_id, "value": wert, "sourceType": quelle, "observationYears": beobachtung,
            "dataDate": stand, "source": "User assumption", "notes": notiz}


SEED_ANNAHMEN = [
    _annahme("wf_ff", 0.50, "manualScenario", _SZENARIO_WIKI),
    _annahme("wf_hig", 0.50, "manualScenario", _SZENARIO_WIKI),
    _annahme("wf_gwc", 0.50, "manualScenario", _SZENARIO_WIKI),
    _annahme("etf_allworld", 0.1108, "manualScenario", _AUSGANGSWERT),
    _annahme("etf_momentum", 0.1216, "manualScenario", _AUSGANGSWERT),
    _annahme("etf_ndx", 0.1444, "manualScenario", _AUSGANGSWERT),
    _annahme("etf_semi", 0.3313, "manualScenario", _AUSGANGSWERT),
    _annahme("etf_ndx2x", 0.1827, "manualScenario", _AUSGANGSWERT + " Eigene Annahme für das Hebelprodukt."),
    _annahme("korb", 0.25, "manualScenario", "Default-Modellrendite des Aktienkorbs – Szenarioannahme."),
    _annahme("korb", 0.10, "bear", "Szenarioannahme"),
    _annahme("korb", 0.25, "base", "Szenarioannahme"),
    _annahme("korb", 0.30, "bull", "Szenarioannahme"),
    _annahme("reserve", 0.0, "manualScenario", "Cash ohne Verzinsung (anpassbar)."),
    # Optionale Bausteine: bewusst OHNE Zahl - erst eigene Annahme eintragen
    _annahme("etf_smallcap", None, "manualScenario", "Noch keine Annahme – bitte eintragen."),
    _annahme("etf_gold", None, "manualScenario", "Noch keine Annahme – bitte eintragen."),
    _annahme("etf_copper", None, "manualScenario", "Noch keine Annahme – bitte eintragen."),
]

# Wo Bear/Bull fehlen: offen ausgewiesene Standardregel (in der App aenderbar)
SZENARIO_REGEL = {"bear_faktor": 0.5, "bull_faktor": 1.2,
                  "text": "Fehlt eine eigene Bear-/Bull-Annahme: Bear = 50 %, Bull = 120 % der Basisannahme."}

# ---------------------------------------------------------------------------
# CONFIDENCE SCORE (Belastbarkeit der Datenbasis - NICHT Wahrscheinlichkeit)
#   score = 100 * (1 - exp(-jahre / k)) * typfaktor
#   1 Jahr -> 22, 3 Jahre -> 53, 5 Jahre -> 71, 10 Jahre -> 92 (typfaktor 1,0)
# ---------------------------------------------------------------------------
CONFIDENCE = {
    "k_jahre": 4.0,
    "typfaktor": {"index": 1.0, "aktie": 0.95, "wikifolio": 1.0, "hebel": 0.8, "krypto": 0.7, "cash": 1.0},
    "cash_score": 100,
    "ohne_historie": 10,          # keine messbare Historie
}

# ---------------------------------------------------------------------------
# FUNDAMENTAL SCORE 0-100. Kategorien-Gewichte frei aenderbar (werden auf 100
# normiert). Jede Kennzahl wird linear zwischen "schlecht" und "gut" auf 0..1
# abgebildet (bei niedriger_besser umgekehrt). Kennzahlen stammen aus dem
# Qualitaets-Agenten (Yahoo-Jahresabschluesse); qualitative Punkte (Switching
# Costs, Kundenkonzentration ...) koennen je Aktie manuell 0-10 bewertet werden.
# ---------------------------------------------------------------------------
BEWERTUNGSREGELN = {
    "wachstum":  {"titel": "Wachstum", "gewicht": 25, "kennzahlen": [
        ("g_ums", "Umsatzwachstum p.a.", 0, 25, False), ("g_eps", "EPS-Wachstum p.a.", 0, 30, False),
        ("g_fcf", "FCF-Wachstum p.a.", 0, 30, False)]},
    "qualitaet": {"titel": "Qualität", "gewicht": 25, "kennzahlen": [
        ("om", "Operative Marge", 5, 40, False), ("fm", "FCF-Marge", 3, 35, False),
        ("roic", "ROIC", 5, 40, False), ("om_std", "Margenschwankung (Pp.)", 8, 1, True)]},
    "bilanz":    {"titel": "Bilanz", "gewicht": 15, "kennzahlen": [
        ("nde", "Net Debt/EBITDA", 3.5, -0.5, True), ("zinsd", "Zinsdeckung", 2, 20, False)]},
    "bewertung": {"titel": "Bewertung", "gewicht": 15, "kennzahlen": [
        ("fkgv", "Forward-KGV", 45, 12, True), ("peg", "PEG", 3.0, 0.8, True),
        ("ev_fcf", "EV/FCF", 70, 15, True), ("ev_ebitda", "EV/EBITDA", 40, 8, True)]},
    "moat":      {"titel": "Wettbewerbsvorteil", "gewicht": 10, "kennzahlen": [
        ("manuell_moat", "Manuelle Einschätzung (Marktstellung, Wechselkosten, Netzwerk, Technologie, "
                         "Eintrittsbarrieren) 0–10", 0, 10, False),
        ("gm", "Bruttomarge (Näherung)", 20, 70, False)]},
    "risiko":    {"titel": "Risiko", "gewicht": 10, "kennzahlen": [
        ("vola", "Volatilität p.a.", 60, 15, True), ("dd", "Max. Drawdown 5 J.", -75, -20, False),
        ("manuell_risiko", "Manuelle Einschätzung (Kundenkonzentration, Regulierung, Geopolitik) "
                           "0 = hohes Risiko … 10 = geringes", 0, 10, False)]},
}

# ---------------------------------------------------------------------------
# OPTIMIZER-GRENZEN (in % des Gesamtportfolios)
# Gruppe = Kategorien und/oder Exposure-Merkmal (semi = Halbleiteranteil)
# ---------------------------------------------------------------------------
GRENZEN = {
    "einzelasset_max": 20.0,
    "gruppen": [
        {"titel": "Wikifolios", "kategorien": ["wikifolio"], "max": 40.0},
        {"titel": "Einzelaktien", "kategorien": ["single_stock", "stock_basket"], "max": 20.0},
        {"titel": "Hebelprodukte", "kategorien": ["leveraged_etf"], "max": 10.0},
        {"titel": "Halbleiter", "merkmal": "semi", "max": 20.0},
        {"titel": "Krypto", "kategorien": ["crypto"], "max": 5.0},
        {"titel": "Reserve", "kategorien": ["cash"], "min": 5.0},
    ],
}

# ---------------------------------------------------------------------------
# NACHKAUFRESERVE - regelbasierte Tranchen (Anteil der Reserve je Tranche)
# ---------------------------------------------------------------------------
NACHKAUF = {
    "tranchen": [{"anteil": 1 / 3, "drawdown": -15.0}, {"anteil": 1 / 3, "drawdown": -25.0},
                 {"anteil": 1 / 3, "drawdown": -35.0}],
    "ziel": "proportional",          # untergewichtet | allworld | bester_score | hoechste_confidence | asset | proportional
    "ziel_asset": "etf_allworld",
    "min_score_aktiv": True,         # Einzelwerte/Korb nur bei Fundamental Score >= min_score
    "min_score": 70,
}
NACHKAUF_ZIELE = {
    "proportional": "Proportional nach Zielgewichtung", "untergewichtet": "Am stärksten untergewichtete Position",
    "allworld": "All-World", "bester_score": "Bester Fundamental Score",
    "hoechste_confidence": "Höchster Confidence Score", "asset": "Eigenes Asset",
}

# ---------------------------------------------------------------------------
# REBALANCING
# ---------------------------------------------------------------------------
REBALANCING = {"art": "keins", "schwelle_relativ": 25.0}   # 25 % relativ: Ziel 10 % -> Band 7,5–12,5 %
REBALANCING_ARTEN = {"keins": "Kein Rebalancing (Buy & Hold)", "jaehrlich": "Jährlich",
                     "halbjaehrlich": "Halbjährlich", "quartalsweise": "Quartalsweise",
                     "schwelle": "Threshold-Rebalancing"}

# ---------------------------------------------------------------------------
# STRESS-SZENARIO (fuer maximalen modellierten Verlust und Nachkaufreserve)
# Einbruch des Gesamtmarkts um "einbruch" % ueber "dauer" Monate ab Monat
# "start", danach Rueckkehr zum Trend ueber "erholung" Monate. Hebelprodukte
# fallen mit ihrem Hebel, Wikifolios mit "wikifolio_beta".
# Standard-Drawdowns je Kategorietyp, falls keine Historie vorliegt:
# ---------------------------------------------------------------------------
STRESS = {"einbruch": 35.0, "start": 13, "dauer": 6, "erholung": 12, "wikifolio_beta": 1.0}
DRAWDOWN_STANDARD = {"index": -35.0, "aktie": -50.0, "wikifolio": -40.0, "hebel": -65.0,
                     "krypto": -75.0, "cash": 0.0}

# ---------------------------------------------------------------------------
# Vorschlaege fuer gespeicherte Szenarien (Namen)
# ---------------------------------------------------------------------------
SZENARIO_NAMEN = ["Aktuelles Modell", "Mehr Indizes", "Mehr Wikifolios", "Defensiver", "Aggressiv",
                  "Ohne Hebel", "100k Target"]


def seed_modell():
    """Vollstaendiges, unabhaengiges Ausgangsmodell (tiefe Kopie)."""
    import copy
    return copy.deepcopy({
        "version": MODELL_VERSION,
        "rahmen": SEED_RAHMEN, "assets": SEED_ASSETS, "korb": SEED_KORB, "annahmen": SEED_ANNAHMEN,
        "szenario_regel": SZENARIO_REGEL, "bewertungsregeln": BEWERTUNGSREGELN, "grenzen": GRENZEN,
        "nachkauf": NACHKAUF, "rebalancing": REBALANCING, "stress": STRESS,
        "korb_methode": "manual", "manuell": {},      # manuelle Moat-/Risiko-Punkte je Korbaktie
        "holdings": {},                               # {etf_id: {firma: anteil_%}} - fuer Effective Exposure
    })

