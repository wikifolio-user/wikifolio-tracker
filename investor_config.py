"""Schwellenwerte und Annahmen der Investoren-Checks (Menuepunkt "Bewertung" -> "Investoren-Checks").

Alle Zahlen hier sind bewusst an einer Stelle, damit sie ohne Code-Kenntnis angepasst werden koennen.
Prozentwerte sind als Prozent angegeben (15 = 15 %), Faktoren als Zahl (2 = 2,0).
"""

# ---------------------------------------------------------------------------
# Allgemein
# ---------------------------------------------------------------------------
KAUFEN_AB_SCORE = 70           # ab diesem Check-Score (0-100) "wuerde kaufen" im Legenden-Konsens
MIN_BEWERTBAR = 3              # so viele bewertbare Kriterien braucht ein Check fuer ein Urteil
SOLL_JAHRE = 10                # "x von 10 Jahren geprueft" (Graham/Buffett wollen 10-20 Jahre)
NOTEN = [(85, "A"), (70, "B"), (55, "C"), (40, "D"), (25, "E"), (0, "F")]   # Gesamtnote aus Konsens-Score

# Marktdaten-Annahmen (selten aendern; Stand bitte mitpflegen)
AAA_RENDITE = 5.0              # Rendite AAA-Unternehmensanleihen in % (Graham-Formel, Y)
STAATSANLEIHE_10J = 4.2        # Rendite 10-j. Staatsanleihe in % (Terry Smith: FCF-Rendite-Vergleich)
ANNAHMEN_STAND = "10/2026"

# ---------------------------------------------------------------------------
# Value-Investoren
# ---------------------------------------------------------------------------
GRAHAM = {
    "min_umsatz_usd": 2e9,        # 1. ausreichende Groesse (Umsatz, in USD umgerechnet)
    "min_current_ratio": 2.0,     # 2. Umlaufvermoegen / kurzfristige Verbindlichkeiten
    "eps_wachstum_min": 33.0,     # 6. EPS-Wachstum ueber den Zeitraum in %
    "max_kgv": 15.0,              # 7. KGV auf Basis des Durchschnitts-EPS
    "max_kgv_mal_kbv": 22.5,      # 7. KGV x KBV
    "formel_basis_kgv": 8.5,      # Graham-Formel (revidiert): V = EPS x (8,5 + 2g) x 4,4 / Y
    "formel_g_max": 15.0,         # erwartetes Wachstum g wird hierauf begrenzt (Graham selbst warnte vor > 15)
    "ncav_faktor": 2 / 3,         # Net-Net: Kurs < 2/3 x NCAV je Aktie
}
BUFFETT = {
    "min_roe": 15.0,              # 1. in JEDEM Jahr
    "min_roic": 12.0,             # 2. ROIC > 12 % und stabil
    "roic_max_schwankung": 5.0,   #    stabil = (max - min) <= 5 Prozentpunkte
    "max_schulden_x_gewinn": 4.0, # 3. langfristige Schulden < 4 x Jahresnettogewinn
    "min_bruttomarge": 40.0,      # 4. Bruttomarge > 40 %
    "bruttomarge_max_schwankung": 5.0,
    "min_nettomarge": 10.0,       # 5.
    "max_capex_quote": 50.0,      # 7. Capex < 50 % des Nettogewinns
    "steuersatz": 25.0,           # pauschal fuer NOPAT = EBIT x (1 - Steuersatz) im ROIC
    "stabil_relativ": 25.0,       # "stabil" auch, wenn die Spanne <= 25 % des Durchschnitts ist (hohe ROIC)
    "moat_min_roic": 15.0, "moat_min_bruttomarge": 40.0, "moat_top_rang": 3,
    # DCF auf Owner Earnings (Startwerte der Schieberegler)
    "dcf_wachstum": 6.0, "dcf_diskont": 9.0, "dcf_ewig": 2.5, "dcf_jahre": 10,
}
GREENBLATT = {"gut_perzentil": 80.0}    # Rang-Perzentil (Summe der Raenge) fuer "besteht"
DREMAN = {"anteil": 20.0, "min_treffer": 2, "min_current_ratio": 2.0}
TEMPLETON = {"max_abstand_tief": 15.0,   # Kurs hoechstens 15 % ueber 52-Wochen- bzw. 5-Jahres-Tief
             "min_abschlag_kgv": 20.0}   # KGV mindestens 20 % unter eigenem Durchschnitts-KGV
FISHER_KUV = {"attraktiv": 0.75, "meiden": 3.0, "min_nettomarge": 5.0}

# ---------------------------------------------------------------------------
# Qualitaets-Investoren
# ---------------------------------------------------------------------------
TERRY_SMITH = {"min_roce": 20.0, "min_bruttomarge": 50.0, "min_op_marge": 20.0, "min_cash_conversion": 90.0,
               "min_zinsdeckung": 10.0}
PHILIP_FISHER = {"min_umsatzwachstum": 10.0, "max_verwaesserung": 2.0}
TEMPLETON_BILANZ = {"min_ek_quote": 30.0, "min_zinsdeckung": 3.0}

# ---------------------------------------------------------------------------
# Risiko- & Bilanzmodelle
# ---------------------------------------------------------------------------
PIOTROSKI = {"stark_ab": 8, "schwach_bis": 2}
ALTMAN = {"sicher": 2.99, "grau": 1.81,            # Produzierende (Original 1968)
          "sicher_2": 2.6, "grau_2": 1.1}          # Nicht-Produzierende / Dienstleister (Z'')
# Altman: Original-Z fuer Produzierende - Erkennung ueber Yahoo-Sektor/-Branche; alle anderen: Z''
ALTMAN_PRODUZIERENDE = ("industrials", "basic materials", "energy", "consumer cyclical", "consumer defensive",
                        "semiconductor", "hardware", "electronic", "auto", "chemicals", "steel", "machinery",
                        "aerospace", "packaging", "drug manufacturers", "medical devices", "building products")
BENEISH = {"warnschwelle": -1.78, "max_fehlend": 2}   # hoechstens 2 Teilindizes duerfen fehlen (dann = 1)
RED_FLAGS = {
    "forderungen_vorsprung": 10.0,   # Forderungen wachsen > 10 Prozentpunkte schneller als Umsatz
    "lager_vorsprung": 10.0,
    "goodwill_max_ek": 50.0,         # Goodwill > 50 % des Eigenkapitals
    "min_zinsdeckung": 3.0,
    "max_ausschuettung_fcf": 100.0,  # Dividenden > 100 % des FCF
    "max_verwaesserung": 5.0,        # Aktienanzahl > +5 % p. a.
}

# ---------------------------------------------------------------------------
# Sektor-Sonderregeln (Abschnitt 10)
# ---------------------------------------------------------------------------
# Erkennung ueber Yahoo-Sektor/-Branche (Kleinschreibung, Teilstring)
SEKTOR_BANK = ("bank", "insurance", "capital markets", "credit services", "financial conglomerates",
               "asset management", "mortgage finance")
SEKTOR_REIT = ("reit",)
SEKTOR_VERSORGER = ("utilities",)
SEKTOR_ZYKLISCH = ("energy", "basic materials", "oil & gas", "steel", "chemicals", "auto", "airlines",
                   "semiconductor", "building materials", "mining", "metals")
# Versorger: niedrigere Wachstums- und hoehere Verschuldungstoleranz (Faktoren auf die Schwellen)
VERSORGER_WACHSTUM_FAKTOR = 0.5
VERSORGER_SCHULDEN_FAKTOR = 2.0

# Kriterien, die je Sektor-Typ ausgeblendet werden: {typ: {check_id: [kriterium_id, ...] oder "alle"}}
AUSBLENDEN = {
    "bank": {"altman": "alle", "greenblatt": "alle", "beneish": "alle",
             "graham": ["current_ratio", "schulden_nca"], "buffett": ["bruttomarge", "capex"],
             "terry_smith": ["bruttomarge", "cash_conversion"], "dreman": ["qualitaet_cr"],
             "piotroski": ["current_ratio", "bruttomarge"], "red_flags": ["lager", "forderungen"]},
    "reit": {"graham": ["kgv"], "templeton": ["kgv_abschlag"], "dreman": ["kgv"]},
}
SEKTOR_GRUND = {
    "bank": "Bei Banken und Versicherungen sind Umlaufvermögen, Bruttomarge, EBIT und Investitionen nicht "
            "sinnvoll definiert – das Modell gilt dort nicht.",
    "reit": "Bei REITs ist der Gewinn durch hohe Abschreibungen verzerrt – maßgeblich ist FFO statt KGV.",
}

# ---------------------------------------------------------------------------
# Konsens-Kategorien (Filter-Chips)
# ---------------------------------------------------------------------------
KATEGORIEN = ["Value", "Qualität", "Wachstum", "Momentum", "Risiko", "Dividende"]
