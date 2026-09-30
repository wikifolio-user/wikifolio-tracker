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
    "regional_equity": {"titel": "Regional Equity",  "typ": "index"},
    "sector":          {"titel": "Sektor / Thema",   "typ": "index"},
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
           emittent=None, tech=None, semi=None, aktiv=True, bias=False, notiz="", fix=False, quelle=None):
    return {
        "id": id, "name": name, "ticker": ticker, "isin": isin, "category": kategorie,
        "subCategory": sub, "region": region, "sector": sektor, "targetWeight": gewicht,
        "leverage": hebel, "leverageType": hebel_typ, "expenseRatio": ter, "performanceFee": perf_fee,
        "emittent": emittent, "techAnteil": tech, "semiAnteil": semi, "enabled": aktiv,
        "historicalWinnerBias": bias, "notes": notiz,
        "fixiert": fix,                 # bei "Gewichtung 100k" unveraendert lassen
        # "historisch" = tatsaechliche Rendite laut Kurshistorie statt Annahme (Standard bei Wikifolios)
        "renditequelle": quelle or ("historisch" if kategorie == "wikifolio" else "annahme"),
    }


SEED_ASSETS = [
    # --- Wikifolios (Zertifikate von Lang & Schwarz) ---
    _asset("wf_ff", "FF Inlinetrading", "wikifolio", 10.0, ticker="LS9VSU", isin="DE000LS9VSU1",
           emittent="Lang & Schwarz"),
    _asset("wf_hig", "Hauptindizes Global", "wikifolio", 10.0, ticker="LS9VFS", isin="DE000LS9VFS2",
           emittent="Lang & Schwarz"),
    _asset("wf_gwc", "Global Wealth Concentrated", "wikifolio", 10.0, ticker="LS9UTF", isin="DE000LS9UTF2",
           emittent="Lang & Schwarz"),
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
    _asset("reserve", "Nachkaufreserve", "cash", 10.0, region="-", sektor="Cash", fix=True),
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
_SZENARIO_WIKI = ("Nur Ersatzwert: Wikifolios rechnen mit der tatsächlichen Rendite laut Kurshistorie; diese "
                  "Annahme gilt nur, wenn keine Historie ≥ 1 Jahr vorliegt oder „Ist“ abgewählt ist.")
_AUSGANGSWERT = "Historischer / modellierter Ausgangswert aus dem bisherigen Modell – keine Zukunftsrendite."


def _annahme(asset_id, wert, quelle, notiz, stand="2026-09-28", beobachtung=None, auto=None):
    # auto: eigene Annahme (manualScenario) wird automatisch mit der bisherigen
    # Rendite p.a. laut Kurshistorie ueberschrieben, solange sie niemand aendert.
    # Standard: ja fuer alle eigenen Annahmen ausser Cash.
    if auto is None:
        auto = quelle == "manualScenario" and asset_id != "reserve"
    return {"assetId": asset_id, "value": wert, "sourceType": quelle, "observationYears": beobachtung,
            "dataDate": stand, "source": "User assumption", "notes": notiz, "auto": auto}


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
# ---------------------------------------------------------------------------
# ENTNAHMEPLAN (monatlich, nach dem Anlagehorizont) - alle Werte Annahmen
#   start: "modell" (Modell-Endwert) | "ziel" (Zielvermoegen) | "eigen" (startbetrag)
#   rendite_quelle: "eigen" (rendite_pa) | "modell" (modellierte Rendite der Aufbauphase)
#   dynamik_pa: jaehrliche Erhoehung der Entnahme (z. B. Inflationsausgleich)
#   Steuer vereinfacht: Abgeltungsteuer inkl. Soli auf den Gewinnanteil jeder
#   Entnahme (Durchschnittseinstand), Sparerpauschbetrag je Kalenderjahr.
# ---------------------------------------------------------------------------
ENTNAHME = {"aktiv": True, "auto_gewichtung": False, "monatlich": 1000.0, "dynamik_pa": 2.0, "dauer_jahre": 30, "start": "modell", "startbetrag": None,
            "rendite_quelle": "eigen", "rendite_pa": 5.0, "steuer": False, "steuersatz": 26.375,
            "freibetrag": 1000.0}
ENTNAHME_STARTS = {"modell": "Modell-Endwert", "ziel": "Zielvermögen", "eigen": "Eigener Betrag"}

SZENARIO_NAMEN = ["Aktuelles Modell", "Mehr Indizes", "Mehr Wikifolios", "Defensiver", "Aggressiv",
                  "Ohne Hebel", "100k Target"]


# ---------------------------------------------------------------------------
# BAUSTEIN-KATALOG (Auswahlliste im Portfolio Builder)
# Stammdaten wie vom Nutzer vorgegeben (Name, WKN, ISIN, Profil). Kennzahlen
# (Renditen, Volatilitaet, Drawdown, Historie) werden NICHT hier eingetragen,
# sondern zur Laufzeit aus der echten Kurshistorie berechnet. TER und
# Performance Fee bleiben leer, solange sie nicht bekannt sind.
#   typ: aktie | wikifolio | etf
# ---------------------------------------------------------------------------
KATALOG_TYPEN = {"aktie": "Aktien", "wikifolio": "Wikifolios", "etf": "ETFs & ETPs"}


def _kat(typ, name, wkn, isin, kategorie, profil, *, sektor=None, region=None, hebel=1.0, hebel_typ=None,
         tech=None, semi=None, treiber=None):
    return {"typ": typ, "name": name, "wkn": wkn, "isin": isin, "category": kategorie, "profil": profil,
            "sektor": sektor or profil, "region": region or ("USA" if typ == "aktie" else "Global"),
            "hebel": hebel, "hebel_typ": hebel_typ, "tech": tech, "semi": semi, "treiber": treiber,
            "ter": None, "perf_fee": None}


_A, _W, _E = "aktie", "wikifolio", "etf"
KATALOG = [
    # --- Aktien (ISIN nicht vorgegeben - Suche ueber die WKN) ---
    _kat(_A, "NVIDIA", "918422", None, "single_stock", "Halbleiter", tech=1.0, semi=1.0),
    _kat(_A, "Broadcom", "A2JG9Z", None, "single_stock", "Halbleiter", tech=1.0, semi=1.0),
    _kat(_A, "Rolls-Royce", "A1H81L", None, "single_stock", "Triebwerke / Luftfahrt", region="Großbritannien",
         tech=0.0, semi=0.0),
    _kat(_A, "Celestica", "A406LU", None, "single_stock", "Elektronik-Fertigung", region="Kanada", tech=1.0, semi=0.0),
    _kat(_A, "Sterling Infrastructure", "882359", None, "single_stock", "Infrastruktur / Bau", tech=0.0, semi=0.0),
    _kat(_A, "Comfort Systems USA", "907784", None, "single_stock", "Gebäudetechnik", tech=0.0, semi=0.0),
    _kat(_A, "Interactive Brokers", "A0MQY6", None, "single_stock", "Broker / Finanzen", tech=0.0, semi=0.0),
    _kat(_A, "EMCOR Group", "898814", None, "single_stock", "Gebäudetechnik", tech=0.0, semi=0.0),
    _kat(_A, "Micron Technology", "869020", None, "single_stock", "Halbleiter", tech=1.0, semi=1.0),
    _kat(_A, "Quanta Services", "912294", None, "single_stock", "Infrastruktur / Netze", tech=0.0, semi=0.0),
    _kat(_A, "Vertiv", "A2PZ5A", None, "single_stock", "Rechenzentrum-Infrastruktur", tech=1.0, semi=0.0),
    _kat(_A, "KLA", "865884", None, "single_stock", "Halbleiter-Ausrüstung", tech=1.0, semi=1.0),
    _kat(_A, "Lam Research", "A40L1V", None, "single_stock", "Halbleiter-Ausrüstung", tech=1.0, semi=1.0),
    _kat(_A, "Arista Networks", "A40V33", None, "single_stock", "Netzwerktechnik", tech=1.0, semi=0.0),
    _kat(_A, "Howmet Aerospace", "A2PZ2D", None, "single_stock", "Luftfahrt-Komponenten", tech=0.0, semi=0.0),
    # --- Wikifolios ---
    _kat(_W, "FF Inlinetrading", "LS9VSU", "DE000LS9VSU1", "wikifolio", "High Risk / Derivatives"),
    _kat(_W, "Hauptindizes Global", "LS9VFS", "DE000LS9VFS2", "wikifolio", "Index Trading / Leveraged"),
    _kat(_W, "Global Wealth Concentrated", "LS9UTF", "DE000LS9UTF2", "wikifolio", "Concentrated Growth"),
    _kat(_W, "PPinvest KI System", "LS9VSJ", "DE000LS9VSJ4", "wikifolio", "AI / Growth"),
    _kat(_W, "AlphaStars", "LS9UNZ", "DE000LS9UNZ3", "wikifolio", "Growth / Quantitative"),
    _kat(_W, "Global News and Trends", "LS9U3L", "DE000LS9U3L1", "wikifolio", "Trend / News"),
    _kat(_W, "NoLimits", "LS9BFD", "DE000LS9BFD6", "wikifolio", "Long Track Record"),
    _kat(_W, "Alpha AI Leaders", "LS9UB8", "DE000LS9UB81", "wikifolio", "AI / Growth"),
    _kat(_W, "UMBRELLA", "LS9AVX", "DE000LS9AVX3", "wikifolio", "Long Track Record"),
    _kat(_W, "TSI Strategie Nasdaq-Werte", "LS9LHG", "DE000LS9LHG4", "wikifolio", "Nasdaq / Momentum"),
    _kat(_W, "Investmentideen", "LS9CGP", "DE000LS9CGP6", "wikifolio", "Equity"),
    _kat(_W, "Rohstoffwerte", "LS9JK4", "DE000LS9JK44", "wikifolio", "Commodities / Mining"),
    _kat(_W, "5 Sektoren Diversifikation", "LS9TTE", "DE000LS9TTE7", "wikifolio", "Multi-Sector"),
    _kat(_W, "Szew Grundinvestment", "LS9EQQ", "DE000LS9EQQ9", "wikifolio", "Fundamental / Value"),
    _kat(_W, "Nordstern", "LS9GGD", "DE000LS9GGD3", "wikifolio", "Equity"),
    _kat(_W, "InlineXtreme", "LS9VVE", "DE000LS9VVE9", "wikifolio", "Extreme Leveraged"),
    _kat(_W, "Perlen der Woche mit Hebel", "LS9VK0", "DE000LS9VK06", "wikifolio", "Leveraged"),
    _kat(_W, "Innovation Leaders", "LS9V50", "DE000LS9V508", "wikifolio", "Innovation / Growth"),
    _kat(_W, "TRENDS BEGLEITEN", "LS9U6Z", "DE000LS9U6Z4", "wikifolio", "Trend Following"),
    _kat(_W, "Dynamic Vision", "LS9VJ4", "DE000LS9VJ41", "wikifolio", "Growth"),
    _kat(_W, "NDX Rotate Plus X", "LS9VGG", "DE000LS9VGG5", "wikifolio", "Nasdaq / Leveraged"),
    _kat(_W, "HB Kneis Performers Weltweit", "LS9VRQ", "DE000LS9VRQ1", "wikifolio", "Global Equity"),
    _kat(_W, "Innovation x Value", "LS9U6X", "DE000LS9U6X9", "wikifolio", "Fundamental Growth"),
    _kat(_W, "Accelerating Interest", "LS9V7U", "DE000LS9V7U2", "wikifolio", "Growth"),
    _kat(_W, "Global Nascent Opportunities", "LS9USP", "DE000LS9USP3", "wikifolio", "Global Growth"),
    _kat(_W, "EBEL2X BTC", "LS9VCE", "DE000LS9VCE9", "wikifolio", "Bitcoin / Leveraged"),
    _kat(_W, "MullhollandDrive", "LS9SMZ", "DE000LS9SMZ9", "wikifolio", "Equity"),
    _kat(_W, "Meine 5 Favoriten", "LS9UNW", "DE000LS9UNW0", "wikifolio", "Concentrated Equity"),
    _kat(_W, "BUY L0W SELL H1GH", "LS9PVY", "DE000LS9PVY9", "wikifolio", "US Growth / Equity"),
    _kat(_W, "3xGTAA", "LS9U6W", "DE000LS9U6W1", "wikifolio", "Leveraged Multi-Asset"),
    _kat(_W, "Edelmetalle und Krypto", "LS9PYL", "DE000LS9PYL0", "wikifolio", "Precious Metals / Crypto"),
    _kat(_W, "Highflyer USA", "LS9QFC", "DE000LS9QFC6", "wikifolio", "US Growth / Momentum"),
    _kat(_W, "Halbleitertechnologien", "LS9RDK", "DE000LS9RDK2", "wikifolio", "Semiconductor"),
    _kat(_W, "Weltindex und Event-Trading", "LS9VHD", "DE000LS9VHD0", "wikifolio", "Global / Event Trading"),
    # --- ETFs & ETPs ---
    _kat(_E, "Vanguard FTSE All-World UCITS ETF Acc", "A2PKXG", "IE00BK5BQT80", "global_equity", "Global Equity"),
    _kat(_E, "iShares Edge MSCI World Momentum Factor UCITS ETF", "A12ATF", "IE00BP3QZ825", "factor", "World Momentum"),
    _kat(_E, "Invesco EQQQ Nasdaq-100 UCITS ETF Acc", "A2N6RV", "IE00BFZXGZ54", "technology", "Nasdaq 100",
         region="USA"),
    _kat(_E, "VanEck Semiconductor UCITS ETF", "A2QC5J", "IE00BMC38736", "semiconductor", "Semiconductor",
         tech=1.0, semi=1.0),
    _kat(_E, "iShares MSCI World Small Cap UCITS ETF", "A2DWBY", "IE00BF4RFH31", "small_cap", "World Small Cap"),
    _kat(_E, "iShares Edge MSCI World Quality Factor UCITS ETF", "A12ATE", "IE00BP3QZ601", "factor", "World Quality"),
    _kat(_E, "iShares Core S&P 500 UCITS ETF Acc", "A0YEDG", "IE00B5BMR087", "regional_equity", "S&P 500",
         region="USA"),
    _kat(_E, "Amundi Nasdaq-100 Daily 2x Leveraged UCITS ETF", "A0LC12", "FR0010342592", "leveraged_etf",
         "Nasdaq 100 / 2x Leveraged", region="USA", hebel=2.0, hebel_typ="daily"),
    _kat(_E, "VanEck Gold Miners UCITS ETF", "A12CCL", "IE00BQQP9F84", "mining", "Gold Miners"),
    _kat(_E, "VanEck Junior Gold Miners UCITS ETF", "A12CCM", "IE00BQQP9G91", "mining", "Junior Gold Miners"),
    _kat(_E, "iShares Gold Producers UCITS ETF", "A1JKQJ", "IE00B6R52036", "mining", "Gold Producers"),
    _kat(_E, "Global X Copper Miners UCITS ETF", "A3C7FZ", "IE0003Z9E2Y3", "mining", "Copper Miners"),
    _kat(_E, "VanEck Rare Earth and Strategic Metals UCITS ETF", "A3CRL9", "IE0002PG6CA6", "mining",
         "Rare Earth / Strategic Metals"),
    _kat(_E, "SPDR S&P U.S. Energy Select Sector UCITS ETF", "A14QB0", "IE00BWBXM492", "sector", "US Energy",
         region="USA", tech=0.0, semi=0.0),
    _kat(_E, "SPDR MSCI World Energy UCITS ETF", "A2AGZ1", "IE00BYTRR863", "sector", "Global Energy",
         tech=0.0, semi=0.0),
    _kat(_E, "iShares S&P 500 Information Technology Sector UCITS ETF", "A142N1", "IE00B3WJKG14", "technology",
         "US Information Technology", region="USA", tech=1.0),
    _kat(_E, "iShares MSCI Europe Energy Sector UCITS ETF", "A2QBZ1", "IE00BMW42637", "sector", "Europe Energy",
         region="Europa", tech=0.0, semi=0.0),
    _kat(_E, "Xtrackers MSCI World Information Technology UCITS ETF", "A113FM", "IE00BM67HT60", "technology",
         "World Information Technology", tech=1.0),
    _kat(_E, "L&G Cyber Security Innovation UCITS ETF", "A3DLEJ", "IE000ST40PX8", "sector", "Cybersecurity",
         tech=1.0),
    _kat(_E, "VanEck Defense UCITS ETF", "A3D9M1", "IE000YYE6WK5", "sector", "Defense"),
    _kat(_E, "Scalable MSCI AC World Leveraged Daily Swap UCITS ETF 2x", "DBX2SC", "LU3386643970", "leveraged_etf",
         "Global Equity / 2x Leveraged", hebel=2.0, hebel_typ="daily", treiber="Welt-Aktien"),
    _kat(_E, "CoinShares Physical Top 10 Crypto Market ETP", "A3G4FD", "JE00BPRDNL86", "crypto", "Crypto Basket",
         tech=0.0, semi=0.0),
    _kat(_E, "21Shares Crypto Basket Index ETP", "A2TT3D", "CH0445689208", "crypto", "Crypto Basket",
         tech=0.0, semi=0.0),
]

# ---------------------------------------------------------------------------
# RISK SCORE 0-100 (hoeher = riskanter) - offen gelegte Formel:
#   0,45 x Volatilitaet (1 J., 0 %..60 % -> 0..100)
# + 0,35 x Max. Drawdown (0 %..-80 % -> 0..100)
# + 0,20 x Hebel (Hebel 2 -> 60, Hebel 3 -> 100; Profil mit "Leveraged",
#          "Derivatives", "Extreme" ... +40)
# ---------------------------------------------------------------------------
RISIKO = {"vola_max": 60.0, "dd_max": 80.0, "gewichte": {"vola": 0.45, "dd": 0.35, "hebel": 0.20},
          "hebel_je_faktor": 60.0, "hebel_text_zuschlag": 40.0,
          "hebel_texte": ("leverag", "derivat", "extreme", "hebel", "2x", "3x", "inlinetrading")}

# ---------------------------------------------------------------------------
# RENDITE-VORSCHLAG fuer Katalog-Bausteine (Base/Bear/Bull) - KEINE Prognose:
#   Base = Confidence x historische Rendite + (1 - Confidence) x Anker (8 %)
#   historische Rendite = 5 J. p.a., sonst 3 J., sonst seit Start (>= 1 J.)
#   Bear = Base - 50 % von |Base|, Bull = Base + 20 % von |Base|
# Kurze Historien werden damit stark Richtung einer Marktrendite gezogen.
# ---------------------------------------------------------------------------
VORSCHLAG = {"anker": 0.08, "bear_abschlag": 0.5, "bull_zuschlag": 0.2,
             "text": "Vorschlag: historische Rendite, nach Datenbasis Richtung 8 % gedämpft – keine Prognose."}


def seed_modell():
    """Vollstaendiges, unabhaengiges Ausgangsmodell (tiefe Kopie)."""
    import copy
    return copy.deepcopy({
        "version": MODELL_VERSION,
        "rahmen": SEED_RAHMEN, "assets": SEED_ASSETS, "korb": SEED_KORB, "annahmen": SEED_ANNAHMEN,
        "szenario_regel": SZENARIO_REGEL, "bewertungsregeln": BEWERTUNGSREGELN, "grenzen": GRENZEN,
        "nachkauf": NACHKAUF, "rebalancing": REBALANCING, "stress": STRESS, "entnahme": ENTNAHME,
        "korb_methode": "manual", "manuell": {},      # manuelle Moat-/Risiko-Punkte je Korbaktie
        "holdings": {},                               # {etf_id: {firma: anteil_%}} - fuer Effective Exposure
    })
