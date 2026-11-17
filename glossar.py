"""Glossar: Fachbegriffe der App in einfachen Worten (Audit UX-04) - ohne Streamlit testbar.

BEGRIFFE: Begriff -> (Bereich, Erklaerung). Die Erklaerung ist bewusst kurz (2-4 Saetze) und sagt, wie man den Wert
liest ("Faustregel"), nicht nur, wie er berechnet wird. ALIASE fuehrt Abkuerzungen und Schreibweisen auf den Begriff.
ANSICHT_BEGRIFFE: welche Begriffe am Ende einer Ansicht unter "Begriffe kurz erklaert" stehen.
"""
import re

BEREICHE = ("Rendite & Risiko", "Bewertung", "Qualität & Bilanz", "Investoren-Methoden", "Fonds & Steuern",
            "Geschäftsideen (EKS)", "Rente & Abfindung")

BEGRIFFE = {
    # --- Rendite & Risiko ---
    "CAGR": ("Rendite & Risiko",
             "Durchschnittliche jährliche Wachstumsrate (Compound Annual Growth Rate). Sagt, um wie viel Prozent ein "
             "Wert pro Jahr gleichmäßig hätte wachsen müssen, um vom Anfangs- zum Endwert zu kommen. Glättet "
             "Schwankungen zwischen den Jahren."),
    "XIRR (geldgewichtete Rendite)": ("Rendite & Risiko",
             "Rendite pro Jahr, die Zeitpunkt und Höhe jeder Ein- und Auszahlung berücksichtigt (interner Zinsfuß mit "
             "echten Datumsangaben). Eine Sparrate, die erst seit einem Monat im Depot liegt, zählt nur einen Monat. "
             "Damit zeigt sie, was Ihr Geld tatsächlich verdient hat."),
    "Zeitgewichtete Rendite": ("Rendite & Risiko",
             "Rendite eines Werts unabhängig davon, wann wie viel Geld eingezahlt wurde. Gut zum Vergleich mit einem "
             "Index; für das eigene Ergebnis mit Sparraten ist die geldgewichtete Rendite (XIRR) aussagekräftiger."),
    "Volatilität": ("Rendite & Risiko",
             "Wie stark der Kurs schwankt, als Standardabweichung der Renditen pro Jahr. Faustregel: unter 10 % ruhig "
             "(Anleihen, Mischfonds), 15–20 % üblich für breite Aktien-ETFs, über 30 % stark schwankend (Einzelaktien, "
             "Krypto)."),
    "Maximaler Drawdown": ("Rendite & Risiko",
             "Größter Verlust vom bisherigen Höchststand bis zum folgenden Tiefpunkt. Zeigt, wie weh die schlimmste "
             "Phase getan hätte: −35 % heißt, aus 10.000 € wurden zwischenzeitlich 6.500 €."),
    "Sharpe-Ratio": ("Rendite & Risiko",
             "Rendite über dem risikolosen Zins geteilt durch die Volatilität – also Rendite je Einheit Schwankung. "
             "Über 1 gilt als gut, über 2 als sehr gut; negative Werte heißen: schlechter als Tagesgeld."),
    "Sortino-Ratio": ("Rendite & Risiko",
             "Wie die Sharpe-Ratio, zählt aber nur Schwankungen nach unten als Risiko. Aufwärtsschwankungen werden "
             "nicht bestraft."),
    "Beta": ("Rendite & Risiko",
             "Wie stark ein Wert mit dem Markt mitschwingt. Beta 1 = wie der Markt, 1,5 = schwankt 50 % stärker, "
             "0,5 = nur halb so stark."),
    "Korrelation": ("Rendite & Risiko",
             "Wie gleichläufig sich zwei Werte bewegen, von −1 (immer gegenläufig) über 0 (unabhängig) bis +1 "
             "(immer gleich). Niedrige Korrelation im Depot senkt das Gesamtrisiko (Streuung)."),
    "Monte-Carlo-Simulation": ("Rendite & Risiko",
             "Tausende zufällige, aber realistische Kursverläufe auf Basis der bisherigen Rendite und Schwankung. "
             "Ergebnis ist keine Vorhersage, sondern eine Bandbreite: wie oft ein Ziel erreicht wird und wie schlecht "
             "es im ungünstigen Fall ausgehen kann."),
    "Median": ("Rendite & Risiko",
             "Mittlerer Wert: die Hälfte der Ergebnisse liegt darüber, die Hälfte darunter. Anders als der "
             "Durchschnitt wird er von wenigen Extremfällen kaum verzerrt."),
    "Verlustrisiko": ("Rendite & Risiko",
             "Anteil der simulierten Verläufe, die am Ende unter dem insgesamt eingesetzten Geld liegen."),
    "Rebalancing": ("Rendite & Risiko",
             "Regelmäßiges Zurücksetzen auf die Zielaufteilung: was stark gestiegen ist, wird verkauft, was "
             "zurückgefallen ist, nachgekauft. Hält das Risiko auf dem geplanten Niveau."),
    # --- Bewertung ---
    "KGV": ("Bewertung",
            "Kurs-Gewinn-Verhältnis: Aktienkurs geteilt durch den Gewinn je Aktie. Sagt, wie viele Jahresgewinne man "
            "für die Aktie bezahlt. Faustregel: unter 15 günstig, über 25 teuer – immer im Vergleich zur Branche und "
            "zum Wachstum."),
    "KBV": ("Bewertung",
            "Kurs-Buchwert-Verhältnis: Börsenwert geteilt durch das Eigenkapital laut Bilanz. Unter 1 kostet die Aktie "
            "weniger als ihr bilanzielles Vermögen. Wichtig vor allem bei Banken und Versicherern."),
    "KUV": ("Bewertung",
            "Kurs-Umsatz-Verhältnis: Börsenwert geteilt durch den Jahresumsatz. Nützlich bei Firmen ohne Gewinn; "
            "Ken Fisher hielt unter 0,75 für günstig."),
    "PEG": ("Bewertung",
            "KGV geteilt durch das erwartete Gewinnwachstum in Prozent (Peter Lynch). Um 1 gilt als fair bewertet, "
            "unter 1 als günstig im Verhältnis zum Wachstum."),
    "EV/EBIT": ("Bewertung",
                "Unternehmenswert (Börsenwert plus Schulden minus Kasse) geteilt durch das operative Ergebnis. Wie das "
                "KGV, berücksichtigt aber die Verschuldung – Firmen mit viel Schulden wirken so nicht künstlich billig."),
    "EBIT / EBITDA": ("Bewertung",
                      "EBIT = Gewinn vor Zinsen und Steuern (operatives Ergebnis). EBITDA = zusätzlich vor "
                      "Abschreibungen. EBITDA schönt kapitalintensive Firmen; EBIT ist meist ehrlicher."),
    "Free Cashflow (FCF)": ("Bewertung",
                            "Geld, das nach laufendem Betrieb und Investitionen übrig bleibt – daraus werden "
                            "Dividenden, Rückkäufe und Schuldenabbau bezahlt. Schwerer zu schönen als der Gewinn."),
    "FCF-Rendite": ("Bewertung",
                    "Free Cashflow geteilt durch den Börsenwert. 5 % heißt: Für 100 € Aktie erwirtschaftet die Firma "
                    "5 € freien Cash pro Jahr."),
    "Dividendenrendite": ("Bewertung",
                          "Jährliche Dividende geteilt durch den Aktienkurs. Sehr hohe Werte (über 7–8 %) sind oft ein "
                          "Warnzeichen: Der Markt erwartet eine Kürzung."),
    "Ausschüttungsquote": ("Bewertung",
                           "Anteil des Gewinns, der als Dividende ausgezahlt wird. Über 80 % (außer bei REITs und "
                           "Versorgern) lässt wenig Puffer für schlechte Jahre."),
    "Fairer Wert": ("Bewertung",
                    "Geschätzter innerer Wert je Aktie aus einem Bewertungsmodell (z. B. abgezinste künftige "
                    "Cashflows). Eine Schätzung mit Annahmen – deshalb zeigt die App eine Spanne statt eines Punkts."),
    "Sicherheitsmarge (Margin of Safety)": ("Bewertung",
             "Abstand zwischen fairem Wert und Kurs. 30 % Sicherheitsmarge heißt: Die Aktie kostet 30 % weniger als "
             "geschätzt. Puffer gegen Fehler in der Schätzung (Benjamin Graham)."),
    "DCF (Discounted Cashflow)": ("Bewertung",
             "Bewertung über künftige Cashflows, die mit einem Zinssatz auf heute abgezinst werden. Reagiert stark auf "
             "die Annahmen zu Wachstum und Zins."),
    "Gewinnrendite (Earnings Yield)": ("Bewertung",
             "Umkehrung des KGV: Gewinn (meist EBIT) geteilt durch Börsen- bzw. Unternehmenswert. Teil der Magic "
             "Formula von Greenblatt."),
    "Gewinnrevisionen": ("Bewertung",
             "Wie Analysten ihre Gewinnschätzungen zuletzt geändert haben. Viele Anhebungen sind ein positives "
             "Signal, Senkungen ein Warnzeichen."),
    # --- Qualitaet & Bilanz ---
    "ROIC": ("Qualität & Bilanz",
             "Rendite auf das investierte Kapital: operativer Gewinn nach Steuern geteilt durch Eigenkapital plus "
             "verzinsliche Schulden. Über 15 % dauerhaft spricht für einen Wettbewerbsvorteil."),
    "ROE (Eigenkapitalrendite)": ("Qualität & Bilanz",
             "Gewinn geteilt durch das Eigenkapital. Hohe Werte sind gut, können aber auch durch viele Schulden "
             "aufgebläht sein – deshalb zusammen mit ROIC und Verschuldung lesen."),
    "ROA (Gesamtkapitalrendite)": ("Qualität & Bilanz",
             "Gewinn geteilt durch die Bilanzsumme. Bei Banken üblich: um 1 % ist solide."),
    "ROCE": ("Qualität & Bilanz",
             "Return on Capital Employed: EBIT geteilt durch das eingesetzte Kapital (Bilanzsumme minus kurzfristige "
             "Verbindlichkeiten). Ähnlich wie ROIC, vor Steuern."),
    "ROTC (Rendite auf Sachkapital)": ("Qualität & Bilanz",
             "Return on Tangible Capital: operativer Gewinn geteilt durch das greifbare Kapital (ohne Firmenwerte und "
             "immaterielle Werte aus Zukäufen). Zeigt, wie profitabel das eigentliche Geschäft ist – unabhängig "
             "davon, wie teuer Übernahmen bezahlt wurden."),
    "Cash-ROIC": ("Qualität & Bilanz",
                  "Wie ROIC, aber mit Free Cashflow statt Gewinn – schwerer zu schönen."),
    "Kapitalkosten (WACC)": ("Qualität & Bilanz",
             "Durchschnittliche Rendite, die Eigen- und Fremdkapitalgeber verlangen. Liegt der ROIC darüber, schafft "
             "das Unternehmen Wert; liegt er darunter, vernichtet es Wert."),
    "Accrual-Quote (Sloan)": ("Qualität & Bilanz",
             "Nettogewinn minus operativer Cashflow, geteilt durch die durchschnittliche Bilanzsumme (Richard Sloan, "
             "1996). Misst, wie viel vom Gewinn nur buchhalterisch ist und (noch) nicht als Geld geflossen ist. "
             "Faustregel: unter 0 gut, über 10 % ein Warnzeichen – solche Gewinne halten oft nicht."),
    "Operativer Cashflow / Gewinn": ("Qualität & Bilanz",
             "Wie viel vom ausgewiesenen Gewinn tatsächlich als Geld hereinkam. Über 1 ist gut, deutlich unter 1 "
             "über Jahre ein Warnzeichen."),
    "Gross Profitability": ("Qualität & Bilanz",
             "Bruttogewinn (Umsatz minus Herstellkosten) geteilt durch die Bilanzsumme (Robert Novy-Marx). Hohe "
             "Werte zeigen Preissetzungsmacht."),
    "Bruttomarge / operative Marge": ("Qualität & Bilanz",
             "Anteil des Umsatzes, der nach Herstellkosten (brutto) bzw. nach allen Betriebskosten (operativ) bleibt. "
             "Stabile oder steigende Margen sprechen für Qualität."),
    "Verschuldung (Nettoverschuldung/EBITDA)": ("Qualität & Bilanz",
             "In wie vielen Jahren das Unternehmen seine Schulden (minus Kasse) aus dem EBITDA zurückzahlen könnte. "
             "Unter 2 solide, über 4 riskant (außer Versorger/REITs)."),
    "Zinsdeckung": ("Qualität & Bilanz",
                    "EBIT geteilt durch die Zinskosten. Unter 3 wird es eng, wenn die Gewinne fallen oder Zinsen "
                    "steigen."),
    "Burggraben (Moat)": ("Qualität & Bilanz",
             "Dauerhafter Wettbewerbsvorteil, der Konkurrenten fernhält – etwa Marke, Netzwerkeffekt, Kostenvorteil "
             "oder hohe Wechselkosten (Warren Buffett)."),
    "FFO (Funds from Operations)": ("Qualität & Bilanz",
             "Kennzahl für Immobilien-Gesellschaften (REITs): Gewinn ohne Abschreibungen und Verkaufsgewinne von "
             "Immobilien. Ersetzt dort den Gewinn je Aktie."),
    "Combined Ratio": ("Qualität & Bilanz",
             "Bei Versicherern: Schäden plus Kosten geteilt durch die Prämien. Unter 100 % verdient die Versicherung "
             "schon mit dem Versicherungsgeschäft Geld."),
    # --- Investoren-Methoden ---
    "Piotroski F-Score": ("Investoren-Methoden",
             "Neun Ja/Nein-Prüfungen zu Gewinn, Verschuldung und Effizienz (Joseph Piotroski). 8–9 Punkte = "
             "finanziell stark, 0–2 = schwach."),
    "Altman Z-Score": ("Investoren-Methoden",
             "Formel aus fünf Bilanzkennzahlen, die das Insolvenzrisiko schätzt (Edward Altman). Über 3 sicher, "
             "unter 1,8 gefährdet. Nicht für Banken und Versicherer geeignet."),
    "Beneish M-Score": ("Investoren-Methoden",
             "Prüft acht Kennzahlen auf Muster, die bei Bilanzmanipulation typisch sind. Über −1,78 ist ein "
             "Warnzeichen – kein Beweis."),
    "Magic Formula (Greenblatt)": ("Investoren-Methoden",
             "Rangliste aus Kapitalrendite und Gewinnrendite: gute Firmen zu günstigen Preisen. Beide Ränge werden "
             "addiert, der kleinste Gesamtrang ist am attraktivsten."),
    "Graham-Zahl": ("Investoren-Methoden",
             "Obergrenze für einen fairen Preis nach Benjamin Graham: Wurzel aus 22,5 × Gewinn je Aktie × Buchwert "
             "je Aktie. Liegt der Kurs darunter, gilt die Aktie als günstig."),
    "CAN SLIM / Minervini-Trend": ("Investoren-Methoden",
             "Wachstums- und Trendregeln (William O'Neil, Mark Minervini): steigende Gewinne, Kurs über den "
             "gleitenden Durchschnitten 50/150/200 Tage, nahe am 52-Wochen-Hoch."),
    "Insider-Käufe": ("Investoren-Methoden",
             "Käufe und Verkäufe von Vorständen und Aufsichtsräten mit eigenem Geld. Käufe sind aussagekräftiger als "
             "Verkäufe (verkauft wird auch aus privaten Gründen)."),
    # --- Fonds & Steuern ---
    "TER (laufende Kosten)": ("Fonds & Steuern",
             "Total Expense Ratio: jährliche Kosten eines Fonds oder ETFs in Prozent des Anlagebetrags, werden "
             "automatisch abgezogen. Breite ETFs liegen meist bei 0,1–0,3 %, aktive Fonds bei 1–2 %."),
    "Thesaurierend / ausschüttend": ("Fonds & Steuern",
             "Thesaurierend: Erträge werden im Fonds wieder angelegt. Ausschüttend: Erträge werden aufs Konto "
             "gezahlt. Die Gesamtrendite ist gleich, nur Steuerzeitpunkt und Zinseszins unterscheiden sich."),
    "Vorabpauschale": ("Fonds & Steuern",
             "Jährliche Mindestbesteuerung thesaurierender Fonds in Deutschland, abhängig vom Basiszins. Wird beim "
             "späteren Verkauf angerechnet – also keine doppelte Steuer."),
    "Teilfreistellung": ("Fonds & Steuern",
             "Bei Aktienfonds (mind. 51 % Aktien) sind 30 % der Erträge steuerfrei – als Ausgleich dafür, dass der "
             "Fonds selbst schon Steuern zahlt."),
    "Sparerpauschbetrag": ("Fonds & Steuern",
             "1.000 € (Paare 2.000 €) Kapitalerträge pro Jahr sind in Deutschland steuerfrei, wenn ein "
             "Freistellungsauftrag vorliegt."),
    "Wikifolio": ("Fonds & Steuern",
             "Musterdepot eines Traders auf wikifolio.com, als Zertifikat an der Börse handelbar. Kosten: jährliche "
             "Zertifikategebühr plus Performancegebühr auf neue Höchststände."),
    # --- Geschaeftsideen (EKS) ---
    "NPV (Kapitalwert)": ("Geschäftsideen (EKS)",
             "Net Present Value: alle künftigen Ein- und Auszahlungen, auf heute abgezinst, minus die "
             "Startinvestition. Über 0 bringt die Idee mehr als die Alternativanlage zum Diskontzins; unter 0 wäre "
             "das Geld im Depot besser aufgehoben."),
    "NPV Erwartungswert": ("Geschäftsideen (EKS)",
             "Der NPV der Szenarien pessimistisch, realistisch und optimistisch, gewichtet mit ihren "
             "Wahrscheinlichkeiten (Standard 25/50/25)."),
    "IRR (interner Zinsfuß)": ("Geschäftsideen (EKS)",
             "Internal Rate of Return: der Zinssatz, bei dem der NPV genau 0 ist – also die Rendite der Idee pro "
             "Jahr. Liegt er über dem Diskontzins, lohnt sich die Idee. Bei sehr kleiner Investition kann er "
             "riesig werden (z. B. über 1.000 %) und ist dann wenig aussagekräftig."),
    "Diskontzins": ("Geschäftsideen (EKS)",
             "Rendite, die das Geld anderswo bringen würde (Opportunitätskosten), z. B. 7 % im Depot. Damit werden "
             "künftige Zahlungen auf ihren heutigen Wert abgezinst."),
    "Amortisation": ("Geschäftsideen (EKS)",
             "Monat, ab dem die Startinvestition durch die Überschüsse wieder hereingeholt ist (kumulierter "
             "Cashflow erstmals ≥ 0)."),
    "Break-even": ("Geschäftsideen (EKS)",
             "Gewinnschwelle: ab diesem Umsatz bzw. Monat deckt der Umsatz alle Kosten. Bei der Rentenplanung: ab "
             "diesem Alter lohnt sich eine Entscheidung (z. B. Abschläge ausgleichen) finanziell."),
    "Kapitalbedarf": ("Geschäftsideen (EKS)",
             "Tiefster Stand des aufsummierten Cashflows – so viel Geld steckt man maximal hinein, bevor es "
             "zurückfließt."),
    "Nutzwert": ("Geschäftsideen (EKS)",
             "Gewichtete Punktzahl (0–100) aus allen Bewertungskriterien einer Idee. Macht Ideen vergleichbar, auch "
             "wenn sie sich finanziell kaum unterscheiden."),
    "EKS / Engpass": ("Geschäftsideen (EKS)",
             "Engpasskonzentrierte Strategie (Wolfgang Mewes): sich auf eine Zielgruppe und deren brennendstes "
             "Problem (den Engpass) konzentrieren. Der EKS-Score bewertet die sieben Phasen, der Engpass-Wert die "
             "wichtigste davon (Phase 4)."),
    "Sensitivität": ("Geschäftsideen (EKS)",
             "Wie stark sich das Ergebnis ändert, wenn eine Annahme anders kommt (hier Umsatz bzw. Kosten ±20 %). "
             "Zeigt, welche Annahme man am genauesten prüfen sollte."),
    # --- Rente & Abfindung ---
    "Fünftelregelung": ("Rente & Abfindung",
             "Steuerberechnung für Abfindungen: Die Steuer wird so berechnet, als wäre die Abfindung über fünf "
             "Jahre verteilt. Das mildert die Progression – lohnt sich vor allem, wenn das übrige Einkommen im "
             "Auszahlungsjahr niedrig ist."),
    "Entgeltpunkte": ("Rente & Abfindung",
             "Rentenpunkte für ein Jahr Arbeit: 1 Punkt für ein Durchschnittsgehalt. Rente = Punkte × Rentenwert × "
             "Zugangsfaktor (Abschläge)."),
    "Rentenabschlag": ("Rente & Abfindung",
             "0,3 % weniger Rente pro Monat, den man vor der Regelaltersgrenze in Rente geht – lebenslang. "
             "Ab 50 kann man ihn durch eine Ausgleichszahlung abkaufen."),
    "Altersteilzeit (Blockmodell)": ("Rente & Abfindung",
             "Erst arbeitet man voll (Arbeitsphase), dann gar nicht (Freistellungsphase), bekommt aber durchgehend "
             "das halbe Gehalt plus Aufstockung vom Arbeitgeber."),
    "Versorgungslücke": ("Rente & Abfindung",
             "Differenz zwischen dem gewünschten Netto im Ruhestand und dem, was Renten und Vorsorge liefern. Sie "
             "muss aus Erspartem gedeckt werden."),
    "Progressionsvorbehalt": ("Rente & Abfindung",
             "Steuerfreie Leistungen wie Arbeitslosengeld erhöhen den Steuersatz auf das übrige Einkommen."),
}

ALIASE = {
    "XIRR": "XIRR (geldgewichtete Rendite)", "geldgewichtete Rendite": "XIRR (geldgewichtete Rendite)",
    "Drawdown": "Maximaler Drawdown", "Max. Drawdown": "Maximaler Drawdown", "Sharpe": "Sharpe-Ratio",
    "Sortino": "Sortino-Ratio", "Monte Carlo": "Monte-Carlo-Simulation", "EBIT": "EBIT / EBITDA",
    "EBITDA": "EBIT / EBITDA", "FCF": "Free Cashflow (FCF)", "Free Cashflow": "Free Cashflow (FCF)",
    "Margin of Safety": "Sicherheitsmarge (Margin of Safety)", "Sicherheitsmarge": "Sicherheitsmarge (Margin of Safety)",
    "DCF": "DCF (Discounted Cashflow)", "Earnings Yield": "Gewinnrendite (Earnings Yield)",
    "ROE": "ROE (Eigenkapitalrendite)", "ROA": "ROA (Gesamtkapitalrendite)", "ROTC": "ROTC (Rendite auf Sachkapital)",
    "WACC": "Kapitalkosten (WACC)", "Sloan": "Accrual-Quote (Sloan)", "Accruals": "Accrual-Quote (Sloan)",
    "Moat": "Burggraben (Moat)", "FFO": "FFO (Funds from Operations)", "F-Score": "Piotroski F-Score",
    "Piotroski": "Piotroski F-Score", "Z-Score": "Altman Z-Score", "Altman": "Altman Z-Score",
    "M-Score": "Beneish M-Score", "Magic Formula": "Magic Formula (Greenblatt)", "Greenblatt": "Magic Formula (Greenblatt)",
    "TER": "TER (laufende Kosten)", "Thesaurierend": "Thesaurierend / ausschüttend", "NPV": "NPV (Kapitalwert)",
    "Kapitalwert": "NPV (Kapitalwert)", "IRR": "IRR (interner Zinsfuß)", "interner Zinsfuß": "IRR (interner Zinsfuß)",
    "Engpass": "EKS / Engpass", "EKS": "EKS / Engpass", "Minervini": "CAN SLIM / Minervini-Trend",
    "CAN SLIM": "CAN SLIM / Minervini-Trend", "Blockmodell": "Altersteilzeit (Blockmodell)",
    "Abschlag": "Rentenabschlag", "Revisionen": "Gewinnrevisionen", "Bruttomarge": "Bruttomarge / operative Marge",
    "Nettoverschuldung": "Verschuldung (Nettoverschuldung/EBITDA)",
}

# Begriffe, die am Ende einer Ansicht erklaert werden (Schluessel = interner Ansichtsname aus app.py)
_DEPOT = ["XIRR", "Zeitgewichtete Rendite", "CAGR", "Maximaler Drawdown", "Volatilität", "Wikifolio"]
ANSICHT_BEGRIFFE = {
    "🏠 Depot": _DEPOT,
    "💹 KI_Invest_System": ["Wikifolio", "Accrual-Quote (Sloan)", "ROTC", "ROIC", "Cash-ROIC", "Kapitalkosten (WACC)",
                           "Gross Profitability", "Operativer Cashflow / Gewinn", "Burggraben (Moat)", "KGV",
                           "Free Cashflow (FCF)", "Maximaler Drawdown"],
    "🧠 Depot-Analyse & Optimierung": ["Korrelation", "Volatilität", "Maximaler Drawdown", "Rebalancing", "KGV",
                                      "Dividendenrendite", "TER", "Fairer Wert"],
    "📥 Analyse-Depot": ["Korrelation", "Volatilität", "Rebalancing"],
    "📈 Vermögens- & Substanzaufbau": _DEPOT,
    "🔍 Seit 01.01.2026": ["Zeitgewichtete Rendite", "XIRR", "Maximaler Drawdown", "Volatilität"],
    "🔎 Seit 01.01.2021": ["Zeitgewichtete Rendite", "CAGR", "XIRR", "Maximaler Drawdown", "Volatilität"],
    "🔮 Zukunfts-Prognose": ["Monte-Carlo-Simulation", "Median", "Verlustrisiko", "Volatilität", "CAGR"],
    "📊 Szenario-Simulator (5 Jahre)": ["Monte-Carlo-Simulation", "Median", "Volatilität", "Maximaler Drawdown"],
    "💼 Portfolio-Planer": ["TER", "Rebalancing", "Korrelation", "Volatilität", "Monte-Carlo-Simulation",
                           "Thesaurierend / ausschüttend", "Vorabpauschale", "Teilfreistellung"],
    "🚀 Portfolio Builder 2.0": ["TER", "Rebalancing", "Korrelation", "Volatilität", "Maximaler Drawdown",
                                 "Monte-Carlo-Simulation", "Wikifolio"],
    "📦 Musterdepot": ["TER", "Rebalancing", "Volatilität"],
    "🤖 Investment-Scanner": ["TER", "Volatilität", "Maximaler Drawdown", "Monte-Carlo-Simulation", "Median",
                             "KGV", "Dividendenrendite", "Wikifolio"],
    "🔎 Investment Scanner Pro": ["TER", "Volatilität", "Maximaler Drawdown", "Sharpe-Ratio", "Sortino-Ratio",
                                 "Beta", "KGV", "PEG", "Free Cashflow (FCF)"],
    "🧭 Investment Scanner 2.0": ["TER", "Volatilität", "Maximaler Drawdown", "Monte-Carlo-Simulation",
                                 "Median", "Rebalancing", "Vorabpauschale", "Sparerpauschbetrag"],
    "🏆 Watchlist Top 50": ["CAGR", "Volatilität", "Maximaler Drawdown", "Sharpe-Ratio", "ROIC", "KGV",
                            "Free Cashflow (FCF)", "Wikifolio"],
    "⚖️ Bewertung": ["KGV", "KBV", "KUV", "PEG", "EV/EBIT", "FCF-Rendite", "Fairer Wert",
                    "Sicherheitsmarge (Margin of Safety)", "DCF", "ROIC", "ROTC", "Accrual-Quote (Sloan)",
                    "Piotroski F-Score", "Altman Z-Score", "Beneish M-Score", "Magic Formula (Greenblatt)",
                    "Graham-Zahl", "CAN SLIM / Minervini-Trend", "Insider-Käufe", "Gewinnrevisionen",
                    "Burggraben (Moat)", "FFO", "Combined Ratio"],
    "🎯 EKS-Investmentbewertung": ["NPV (Kapitalwert)", "NPV Erwartungswert", "IRR (interner Zinsfuß)", "Diskontzins",
                                  "Amortisation", "Break-even", "Kapitalbedarf", "Nutzwert", "EKS / Engpass",
                                  "Sensitivität"],
    "💶 Abfindungsrechner": ["Fünftelregelung", "Progressionsvorbehalt", "Sparerpauschbetrag"],
    "🧮 Zinseszinsrechner": ["CAGR", "TER", "Vorabpauschale", "Sparerpauschbetrag"],
    "🏖️ Altersteilzeit & Rente": ["Entgeltpunkte", "Rentenabschlag", "Altersteilzeit (Blockmodell)",
                                  "Versorgungslücke", "Break-even", "Fünftelregelung", "Progressionsvorbehalt"],
}


def finde(begriff):
    """Begriff oder Alias -> Schluessel in BEGRIFFE (Gross-/Kleinschreibung egal) oder None."""
    if begriff in BEGRIFFE:
        return begriff
    if begriff in ALIASE:
        return ALIASE[begriff]
    b = str(begriff or "").strip().lower()
    for k in BEGRIFFE:
        if k.lower() == b:
            return k
    for k, v in ALIASE.items():
        if k.lower() == b:
            return v
    return None


def erklaerung(begriff):
    """-> Erklaerungstext oder "" (unbekannt)."""
    k = finde(begriff)
    return BEGRIFFE[k][1] if k else ""


def fuer_ansicht(ansicht):
    """-> [(Begriff, Erklaerung)] fuer die Ansicht, ohne Doppelte, in der hinterlegten Reihenfolge."""
    aus, gesehen = [], set()
    for b in ANSICHT_BEGRIFFE.get(ansicht, []):
        k = finde(b)
        if k and k not in gesehen:
            gesehen.add(k)
            aus.append((k, BEGRIFFE[k][1]))
    return aus


def _norm(t):
    return re.sub(r"\s+", " ", str(t or "").lower()).strip()


def suchen(text):
    """Volltextsuche in Begriff, Alias und Erklaerung. -> [(Begriff, Bereich, Erklaerung)], Treffer im Begriff zuerst."""
    t = _norm(text)
    alle = sorted(BEGRIFFE.items(), key=lambda kv: kv[0].lower())
    if not t:
        return [(k, b, e) for k, (b, e) in alle]
    alias_zu = {}
    for a, k in ALIASE.items():
        alias_zu.setdefault(k, []).append(a)
    im_namen, im_text = [], []
    for k, (b, e) in alle:
        namen = [k] + alias_zu.get(k, [])
        if any(t in _norm(n) for n in namen):
            im_namen.append((k, b, e))
        elif t in _norm(e):
            im_text.append((k, b, e))
    return im_namen + im_text
