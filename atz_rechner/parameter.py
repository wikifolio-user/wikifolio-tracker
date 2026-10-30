"""Gesetzliche Rechengroessen fuer den Altersteilzeit- & Rentenrechner - zentral an EINER Stelle.

Jeder Wert: (Wert, Einheit, Bezeichnung, Quelle). In der Oberflaeche unter "Parameter (Stand pruefen)"
editierbar; gerechnet wird immer mit werte(...) (Standard + eigene Aenderungen). Bitte jaehrlich pruefen
(Rentenanpassung zum 1. Juli, Rechengroessen und Steuertarif zum 1. Januar).

Tabellen, die sich aus dem Gesetz direkt berechnen lassen (Besteuerungsanteil, Ertragsanteil,
Altersentlastungsbetrag, Versorgungsfreibetrag, Altersgrenzen), stehen als Funktionen in steuer.py/rente.py.
"""

STAND = "30.10.2026"

PARAMETER = {
    # --- Rente (DRV) ---
    "rentenwert": (42.52, "€ je EP", "Aktueller Rentenwert (ab 01.07.2026)",
                   "Rentenwertbestimmungsverordnung 2026; DRV-Meldung 05.03.2026 (+4,24 %)"),
    "rentenanpassung": (2.0, "% p. a.", "Annahme: jährliche Rentenanpassung (auch Lohn-/BBG-Entwicklung)",
                        "Annahme – Rentenversicherungsbericht: mittelfristig ca. 2–3 % p. a."),
    "durchschnittsentgelt": (51944.0, "€/Jahr", "Vorläufiges Durchschnittsentgelt 2026 (1 Entgeltpunkt)",
                             "Sozialversicherungs-Rechengrößenverordnung 2026, § 69 Abs. 2 SGB VI"),
    "abschlag_monat": (0.3, "% je Monat", "Rentenabschlag je Monat vor der Altersgrenze",
                       "§ 77 Abs. 2 SGB VI"),
    "witwe_anteil": (55.0, "%", "Große Witwen-/Witwerrente (Neurecht)", "§ 67 Nr. 6 SGB VI"),
    "witwe_freibetrag_rw": (26.4, "× Rentenwert", "Freibetrag bei Einkommensanrechnung (= 1.122,53 € ab 07/2026)",
                            "§ 97 SGB VI"),
    "witwe_anrechnung": (40.0, "%", "Anrechnung des Einkommens über dem Freibetrag", "§ 97 SGB VI"),
    # --- Sozialversicherung 2026 ---
    "rv_satz": (18.6, "%", "Beitragssatz Rentenversicherung (AN + AG)", "SV-Rechengrößen 2026"),
    "av_satz": (2.6, "%", "Beitragssatz Arbeitslosenversicherung (AN + AG)", "SV-Rechengrößen 2026"),
    "kv_satz": (14.6, "%", "Allgemeiner Beitragssatz Krankenversicherung", "§ 241 SGB V"),
    "kv_satz_erm": (14.0, "%", "Ermäßigter Beitragssatz (freiwillig Versicherte ohne Krankengeld)", "§ 243 SGB V"),
    "kv_zusatz": (2.9, "%", "Durchschnittlicher Zusatzbeitrag 2026 (eigene Kasse prüfen)",
                  "BMG-Bekanntmachung durchschnittlicher Zusatzbeitragssatz 2026"),
    "pv_satz": (3.6, "%", "Beitragssatz Pflegeversicherung", "§ 55 SGB XI (seit 01.01.2025)"),
    "pv_kinderlos": (0.6, "%", "Zuschlag Kinderlose ab 23 Jahren", "§ 55 Abs. 3 SGB XI"),
    "pv_sachsen": (0.5, "%", "Mehranteil Arbeitnehmer in Sachsen", "§ 58 Abs. 3 SGB XI"),
    "bbg_rv": (101400.0, "€/Jahr", "Beitragsbemessungsgrenze Renten-/Arbeitslosenversicherung",
               "SV-Rechengrößenverordnung 2026"),
    "bbg_kv": (69750.0, "€/Jahr", "Beitragsbemessungsgrenze Kranken-/Pflegeversicherung",
               "SV-Rechengrößenverordnung 2026"),
    "kv_mindest": (1318.33, "€/Monat", "Mindestbemessung freiwillig Versicherte (1/90 Bezugsgröße × 30)",
                   "§ 240 Abs. 4 SGB V; Bezugsgröße 2026: 3.955 €"),
    "bav_freibetrag": (197.75, "€/Monat", "KV-Freibetrag Versorgungsbezüge (PV: Freigrenze gleicher Höhe)",
                       "§ 226 Abs. 2 SGB V (1/20 Bezugsgröße)"),
    "minijob_grenze": (603.0, "€/Monat", "Minijob-Grenze", "§ 8 Abs. 1a SGB IV (2026)"),
    "sv_hinzuverdienst": (20.0, "%", "Pauschale SV-Abzüge auf Hinzuverdienst über der Minijob-Grenze",
                          "Annahme (KV/PV/RV-Arbeitnehmeranteil, ohne AV ab Regelalter)"),
    # --- Altersteilzeit / Arbeitslosengeld ---
    "atz_aufstockung_min": (20.0, "%", "Mindest-Aufstockung des Arbeitgebers (vom Regelarbeitsentgelt)",
                            "§ 3 Abs. 1 Nr. 1a AltTZG"),
    "atz_rv_basis": (80.0, "%", "Zusätzliche RV-Beiträge des Arbeitgebers auf … des Regelarbeitsentgelts",
                     "§ 3 Abs. 1 Nr. 1b AltTZG (höchstens bis 90 % der BBG)"),
    "alg_satz": (60.0, "%", "Arbeitslosengeld (ohne Kind)", "§ 149 SGB III"),
    "alg_satz_kind": (67.0, "%", "Arbeitslosengeld (mit Kind)", "§ 149 SGB III"),
    "alg_sv_pauschale": (20.0, "%", "SV-Pauschale bei der ALG-Berechnung", "§ 153 SGB III"),
    "alg_rv_basis": (80.0, "%", "RV-Beiträge der Agentur auf … des Bemessungsentgelts", "§ 166 Abs. 1 Nr. 2 SGB VI"),
    # --- Einkommensteuer 2026 (§ 32a EStG) ---
    "gfb": (12348.0, "€", "Grundfreibetrag", "§ 32a EStG i. d. F. Steuerfortentwicklungsgesetz (2026)"),
    "z2_ende": (17799.0, "€", "Tarif: Ende Zone 2", "§ 32a Abs. 1 Nr. 2 EStG 2026"),
    "z2_a": (914.51, "", "Tarif Zone 2: Faktor a ((a·y + b)·y)", "§ 32a Abs. 1 Nr. 2 EStG 2026"),
    "z2_b": (1400.0, "", "Tarif Zone 2: Faktor b", "§ 32a Abs. 1 Nr. 2 EStG 2026"),
    "z3_ende": (69878.0, "€", "Tarif: Ende Zone 3 (ab hier 42 %)", "§ 32a Abs. 1 Nr. 3 EStG 2026"),
    "z3_a": (173.10, "", "Tarif Zone 3: Faktor a ((a·z + b)·z + c)", "§ 32a Abs. 1 Nr. 3 EStG 2026"),
    "z3_b": (2397.0, "", "Tarif Zone 3: Faktor b", "§ 32a Abs. 1 Nr. 3 EStG 2026"),
    "z3_c": (1034.87, "", "Tarif Zone 3: Faktor c", "§ 32a Abs. 1 Nr. 3 EStG 2026"),
    "z4_ende": (277825.0, "€", "Tarif: Ende Zone 4 (ab hier 45 %)", "§ 32a Abs. 1 Nr. 4 EStG 2026"),
    "z4_abzug": (11135.63, "€", "Tarif Zone 4: 0,42·x − Abzug", "§ 32a Abs. 1 Nr. 4 EStG 2026"),
    "z5_abzug": (19470.38, "€", "Tarif Zone 5: 0,45·x − Abzug", "§ 32a Abs. 1 Nr. 5 EStG 2026"),
    "soli_freigrenze": (20350.0, "€ ESt", "Soli-Freigrenze (Einzelveranlagung; Splitting doppelt)", "§ 3 Abs. 3 SolZG 2026"),
    "soli_satz": (5.5, "%", "Solidaritätszuschlag", "§ 4 SolZG"),
    "soli_milderung": (11.9, "%", "Soli-Milderungszone", "§ 4 Satz 2 SolZG"),
    "kist_by_bw": (8.0, "%", "Kirchensteuer Bayern / Baden-Württemberg", "Kirchensteuergesetze der Länder"),
    "kist_sonst": (9.0, "%", "Kirchensteuer übrige Länder", "Kirchensteuergesetze der Länder"),
    "wk_arbeitnehmer": (1230.0, "€", "Arbeitnehmer-Pauschbetrag", "§ 9a Nr. 1a EStG"),
    "wk_rente": (102.0, "€", "Werbungskosten-Pauschbetrag Renten / Versorgungsbezüge", "§ 9a Nr. 1b, 3 EStG"),
    "sonderausgaben_pausch": (36.0, "€", "Sonderausgaben-Pauschbetrag (Splitting doppelt)", "§ 10c EStG"),
    "hoechst_altersvorsorge": (30826.0, "€", "Höchstbetrag Altersvorsorgeaufwendungen (Splitting doppelt)",
                               "§ 10 Abs. 3 EStG 2026 (= Höchstbeitrag knappschaftliche RV)"),
    # --- Kapitalanlage ---
    "abgeltung": (25.0, "%", "Abgeltungsteuer", "§ 32d Abs. 1 EStG"),
    "sparerpausch": (1000.0, "€", "Sparer-Pauschbetrag (Zusammenveranlagung 2.000 €)", "§ 20 Abs. 9 EStG"),
    "teilfreistellung": (30.0, "%", "Teilfreistellung Aktienfonds/-ETF", "§ 20 Abs. 1 InvStG"),
}

# Bundeslaender (Kirchensteuer 8 % in BY/BW, Pflegeversicherung Sachsen)
BUNDESLAENDER = ["Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen",
                 "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz",
                 "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"]


def standard():
    """Nur die Werte {schluessel: wert}."""
    return {k: v[0] for k, v in PARAMETER.items()}


def werte(eigene=None):
    """Standardwerte, ueberschrieben mit gueltigen eigenen Werten (unbekannte Schluessel/keine Zahl -> ignoriert)."""
    w = standard()
    for k, v in (eigene or {}).items():
        if k in w:
            try:
                w[k] = float(v)
            except (TypeError, ValueError):
                pass
    return w


def kirchensteuer_satz(p, bundesland, kirche):
    if not kirche:
        return 0.0
    return (p["kist_by_bw"] if bundesland in ("Bayern", "Baden-Württemberg") else p["kist_sonst"]) / 100.0
