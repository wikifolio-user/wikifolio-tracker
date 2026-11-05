# Bewertungssystem – Ist-Stand (Etappe 1)

Stand: 04.11.2026 · Grundlage für die Erweiterung des Bewertungssystems.
Abgesichert durch `test_bewertung_golden.py`. Die Referenzwerte liegen in `tests_golden/bewertung_klassisch.json`.
Jede Änderung am klassischen Modell lässt diesen Test fehlschlagen. Danach die Referenz nur bewusst und dokumentiert
neu schreiben: `python test_bewertung_golden.py --aktualisieren`.

> Der Bewertungskatalog (PDF, 15 Seiten) lag beim Erstellen nicht vor. Katalogangaben stammen aus der Beschreibung im
> Auftrag und müssen gegen das PDF geprüft werden.

## 1. Bausteine und wo sie im Code stehen

| Baustein | Datei(en) | Datenquelle | Lauf |
|---|---|---|---|
| Qualitäts-Score (8 Bereiche, 100 P.), Red Flags, Einordnung prio/beobachten/nicht, eigenes Bär/Basis/Bull-DCF mit Sicherheitsmarge | `qualitaet_agent.py` (`kennzahlen`, `bewerte`) | yfinance: Jahresabschlüsse (meist 4 GJ), Wochenkurse | `qualitaet.yaml`, täglich rollierend |
| 12 Investorenlegenden + Dividenden-Check | `investor_checks/` (`graham`, `greenblatt`, `dreman`, `templeton`, `fisher_kuv`, `buffett`, `philip_fisher`, `terry_smith`, `lynch`, `can_slim`, `minervini`, `levy`, `dividende`) | yfinance: GuV/Bilanz/Cashflow, Quartale, Kurse 5 J., Dividenden | `investoren.yml`, wöchentlich, ca. 1.500 Aktien je Lauf |
| Risiko-Modelle und Signale | `piotroski`, `altman`, `beneish`, `red_flags`, `smart_money` | wie oben + Insider, Revisionen, Analysten | wie oben |
| Legenden-Konsens, Note A–F | `investor_checks/konsens.py` | – | – |
| Fairer Wert (Modelle + Median), Reverse-DCF | `investor_checks/fairer_wert.py` | – | – |
| Schwellen, Sektor-Sonderregeln | `investor_config.py` | – | – |
| Gesamt-Score Seite „Bewertung“ (Perzentile) | `scoring.py` | Katalog, Qualität, Details, Top-500 | App |
| Bewertung im Builder / Katalog | `bewertung.py` | Katalog | App |
| ETF-/wikifolio-Score | `klassen_score.py` | Kurshistorie (ls-tc) | `top50.yml` |
| Kursrisiko-Kennzahlen (Vola, Sharpe, Sortino, Calmar, Drawdown …) | `risiko_kennzahlen.py` | Kurshistorie | `top50.yml` |
| ETF-Merkmale (Region, Thema, Anbieter, Ausschüttung) | `etf_merkmale.py` | ETF-Name | App |
| KI_Invest_System (Auswahl, Puffer, Streuung, Stückzahlen) | `wiki_idee.py`, `wiki_idee_ui.py` | Qualitäts-Score, Investoren-Checks, ETF-Score, ls-tc | App, nach Bedarf |

## 2. Qualitäts-Score

Die acht Bereiche mit ihren Höchstpunkten: Qualität 20 · Wachstum 15 · Cashflow 15 · Bilanz 10 · Management 10 ·
Burggraben 10 · Bewertung 15 · Chance 5.

Red Flags mit Abzug: FCF überwiegend negativ (10), hohe Verwässerung > 5 % p. a. (8) bzw. > 3 % (4),
Verschuldung stark gestiegen (5), ROIC −8 Pp. (4), operative Marge −5 Pp. (4), aktienbasierte Vergütung > 10 % (5),
Goodwill > 50 % (2), Wachstum durch Zukäufe (4), FCF je Aktie < −10 % p. a. oder gedreht (5),
Reverse-DCF extrem (5).

Einordnung:
- **prio:** Qualitätsanteil ≥ 70 %, Bewertungsanteil ≥ 55 %, Gesamt ≥ 65 und kein schwerer Flag
- **beobachten:** Qualitätsanteil ≥ 62 %
- **nicht:** alles andere

## 3. Abweichungen Katalog ↔ Code

| # | Thema | Katalog (laut Auftrag) | Code | Bewertung |
|---|---|---|---|---|
| A1 | Red-Flag-Abzug | höchstens 30 Punkte | Summe **ohne Deckel**, theoretisch bis 52 Punkte | Entscheidung nötig |
| A2 | Legenden-Konsens | gewichtete Strategiegruppen | 75 % ungewichteter Ø aller Investoren-Scores + 25 % Ø Risiko-Modelle; „kauft“ ab Score 70 | Entscheidung nötig |
| A3 | Risiko-Score 0–100 | vorhanden | nicht vorhanden. Es gibt nur: Risiko-Stufe niedrig/mittel/hoch im Qualitäts-Agenten, Kursrisiko-Kennzahlen und `planer_engine.risiko_score` (Planer) | fehlt |
| A4 | Gesamtranking 55 % Qualität / 35 % Konsens / 10 % Risiko | vorhanden | nicht vorhanden. Stattdessen drei Gesamtscores: `scoring.py` (Bewertung 25 / Qualität 20 / Wachstum 15 / Stabilität 15 / Dividende 10 / Momentum 15), `bewertung.py`, KI_Invest (40/30/20/10) | Entscheidung nötig |
| A5 | Fehlende Daten | eine Hochrechnungsregel | vier Regeln: Qualitäts-Agent zählt Fehlendes als **0 Punkte**; `scoring.py` verteilt die Gewichte neu; `bewertung.py` zieht zur Mitte (50); KI_Invest verteilt die Gewichte neu (seit PR #89) | vereinheitlichen (Etappe 2) |
| A6 | Fairer Wert | ein Satz Modelle | zwei Pfade: `fairer_wert.py` (Graham-Zahl, Graham-Formel, Lynch, DCF Owner Earnings 9 % / 2,5 % / 10 J., KGV-Mean-Reversion, Analystenziel) und das eigene DCF-Szenario im Qualitäts-Agenten | zusammenführen (Etappe 5) |
| A7 | Historie | 10 Jahre (Graham/Buffett-Anspruch) | yfinance liefert meist 4 Geschäftsjahre | Datenquelle (Etappe 2) |

## 4. Bekannte Doppelzählungen (nicht geändert, nur dokumentiert)

- **Verwässerung:** Management-Punkte, Red-Flag-Abzug, Check „Warnsignale“, Philip Fisher
- **ROIC:** Qualität, Burggraben, Management (Trend), Buffett, Greenblatt, Terry Smith
- **Bewertung / FCF-Rendite:** Bewertung, Chance, Terry Smith, Greenblatt, fairer Wert, KI-Baustein „Unterbewertung“
- **Insolvenz/Manipulation:** Altman/Beneish im Konsens (25 %), als harter Ausschluss im KI_Invest und über die Red Flags
- **Zielkonflikt:** Momentum-Checks (O'Neil, Minervini, Levy) belohnen Kursstärke, „Qualität × Kurs“ im KI_Invest belohnt Kursschwäche

## 5. Regressionstest – was abgesichert ist

| Bereich | Testfälle |
|---|---|
| Qualitäts-Score | starkes Wachstum, Stagnation, FCF negativ, Verwässerung, ohne EPS: Punkte je Bereich, Gesamt, Einordnung, Flags |
| Investoren-Checks | Musterfirma, Bank, REIT, Verlustjahr, hoch verschuldet: jeder Check (Score, erfüllt/gesamt, kauft), Konsens, fairer Wert je Modell |
| ETF-/wikifolio-Score | breiter ETF, kurze Historie, Hebel-ETF, wikifolio |
| Gesamt-Score „Bewertung“ | 24 Aktien und 12 ETFs mit Teilscores |
| KI_Invest | Rangliste, Ausschluss, Start-Depot, zweite Umschichtung (Puffer, Nachrücker, Verkäufe), Puffer-Grenzfälle Aktien 51/60/61 und ETFs 21/24/25 |

Gegenprobe: Änderungen an Konsens-Schwelle, ETF-Gewichten, Behandlung fehlender Werte, Puffern,
Branchen- und ETF-Gruppengrenzen, Zielanzahl und Score-Gewichten lassen den Test jeweils fehlschlagen.

## 6. Etappe 2 – Kennzahlen, Datenvertrauen, classic_v2

Neue Module ohne Einfluss auf bestehende Scores:

| Modul | Inhalt |
|---|---|
| `kennzahlen/definitionen.py` | zentrale Kennzahl-Registry: Titel, Einheit, Bereich, Herkunft (gemessen / primär / berechnet / Schätzung / Annahme), Quelle, Zeitraum, Richtung, Anwendbarkeit je Sektor-Typ |
| `kennzahlen/fehlwerte.py` | welche Punkte im Qualitäts-Score nur wegen fehlender Daten fehlen; Vergleichsvariante „hochgerechnet“ |
| `kennzahlen/datenvertrauen.py` | `data_confidence_score` 0–100 aus Vollständigkeit (35), Historie (20), Aktualität (15), Konsistenz (15), Schätzanteil (15); nicht anwendbare Kennzahlen zählen nicht als fehlend |
| `kennzahlen/classic_v2.py` | katalogkonformes Vergleichsmodell: 55 % Qualität (Red-Flag-Abzug ≤ 30) + 35 % Konsens + 10 % Risiko; der Risiko-Score ist **vorläufig, nicht katalogbestätigt** |

Der Qualitäts-Agent schreibt zusätzlich `abz` (Red-Flag-Summe), `fp` (fehlende Punkte je Bereich) und `n`
(Geschäftsjahre) in `state/qualitaet/alle_N.json`. Diese Felder sind reine Information, der Score bleibt gleich.
Sie erscheinen rollierend mit den nächsten Läufen.

Im KI_Invest_System zeigt „🧪 Datenvertrauen & Vergleichsmodelle“ beim Erstellen einer Liste:
- Datenvertrauen der Top 50
- Überschneidung und Rangkorrelation aktives Modell ↔ classic_v2
- Wirkung einer Hochrechnung fehlender Daten

In „🔍 Warum dieser Wert?“ stehen Datenvertrauen und classic_v2 je Position. Die Auswahl selbst nutzt weiter das
aktive Modell.

## 7. Etappe 3 – Earnings Quality, Profitabilität, Cashflow-Qualität, Kapitalallokation

`kennzahlen/fundamental.py` bildet vier eigenständige Teilbewertungen (je 0–100). Sie werden **nur angezeigt** und nicht
zu bestehenden Scores addiert: ROIC, Verwässerung und FCF stecken auch im Qualitäts-Score, daher die Gefahr einer
Doppelzählung. Der Bericht im KI_Invest zeigt deshalb je Teilbewertung die Rangkorrelation mit dem Qualitäts-Score.

| Teilbewertung | Kennzahlen (schwach → stark) |
|---|---|
| Earnings Quality | Sloan-Accruals (10 % → −5 %), operativer Cashflow / Gewinn (0,6 → 1,1), Cashflow / Bilanzsumme (0 → 15 %), Veränderung der Forderungslaufzeit (+20 → 0 Tage) und der Lagerdauer (+30 → 0 Tage), Sondereffekte / Gewinn (30 % → 0) |
| Wirtschaftliche Profitabilität | ROCE (5 → 25 %), Cash-ROIC (0 → 20 %), ROTC (5 → 40 %), Gross Profitability (10 → 40 %), ROIC − WACC (−5 → +10 Pp.), inkrementeller ROIC (0 → 25 %) |
| Cashflow-Qualität | FCF-Marge nach Aktienvergütung (0 → 20 %), Schwankung der FCF-Marge (1,0 → 0,15), Jahre mit positivem FCF (50 → 100 %), Ausschüttungsdeckung (0,8 → 2,0), FCF je Aktie p. a. (−5 → +12 %) |
| Kapitalallokation | Aktienanzahl p. a. (+4 → −2 %), Aktienvergütung / Umsatz (10 → 1 %), Zukäufe / Cashflow (100 → 10 %), Rendite reinvestierter Mittel (0 → 25 %), Buchwert je Aktie p. a. (−2 → +12 %), Aktionärsrendite (0 → 6 %) |

Grundsätze:
- Je Kennzahl gibt es 0–100 Punkte, linear zwischen den Grenzen. Ein Modul braucht mindestens 2 Kennzahlen.
- Fehlende Werte entfallen, sie werden nie als 0 gezählt.
- Negative Ergebnisse (z. B. negative Kapitalrendite) sind echte Werte und bekommen 0 Punkte.
- Bei Banken und Versicherern sind cashflow- und kapitalbasierte Kennzahlen **nicht anwendbar**. Das wird gekennzeichnet und führt zu keinem Nachteil.
- Der WACC ist eine **Modellannahme**: CAPM mit 10-jähriger Staatsanleihe (`investor_config.STAATSANLEIHE_10J`), Beta von Yahoo (begrenzt auf 0,5–2,0), Marktrisikoprämie 5 %, Fremdkapitalkosten = Zinsaufwand / Schulden (1–12 %).
- Warnhinweise wie hohe Accruals, schwache Cash-Deckung, steigende Forderungslaufzeit, Sondereffekte, sehr niedrige Steuerquote oder starke Verwässerung sind **Risikohinweise, kein Beweis**.

Datenquelle: derselbe yfinance-Abruf des Investoren-Agenten, keine zusätzlichen API-Aufrufe. Neu eingelesen werden die
Posten Aktienvergütung, Steuern, Vorsteuerergebnis, Verbindlichkeiten aus L&L, Sondereffekte und Zukäufe
(`investor_checks/daten.ZEILEN_ERWEITERT`). Sie zählen bewusst nicht für die Mindestzahl an Posten je Periode, damit die
klassischen Checks unverändert bleiben (Test: `test_neue_posten_aendern_perioden_nicht`).

Speicherung: Feld `x` in `state/investoren/ergebnis_NN.json`, ab dem nächsten Wochenlauf rollierend.

## Etappe 4a: Branchenmodelle für Banken, Versicherer und REITs (nur Information)

`kennzahlen/branchenmodell.py` bewertet Finanzwerte und Immobilien-REITs mit branchentypischen Kennzahlen. Das
Standardmodell (Free Cashflow, ROIC, EBITDA, Bruttomarge) passt dort nicht: Banken und Versicherer fehlen deshalb im
Qualitäts-Score (Stand 4.11.2026: rund 230 Werte), REITs werden durch hohe Abschreibungen systematisch schlecht
bewertet (keiner unter den Top 500). Der Branchen-Score wird **nur angezeigt** – in der Einzelansicht der
Investoren-Checks, als Spalte im Legenden-Screener und in der Begründung im KI_Invest. Er ändert keinen bestehenden
Score, keine Rangliste und keine Auswahl (Freigabe für eine Einbeziehung: Etappe 4b, erst nach einem Vergleich).

| Typ | Erkennung (Yahoo-Branche) | Kennzahlen (schwach → stark) |
|---|---|---|
| Bank | Banks, Mortgage Finance, Financial Conglomerates | Eigenkapitalrendite (5 → 15 %), materielle EK-Rendite (6 → 18 %), Gesamtkapitalrendite (0,5 → 1,5 %), Kosten-Ertrags-Quote (70 → 45 %), Risikovorsorge / Kredite (1,5 → 0,2 %), Eigenkapital / Bilanzsumme (4 → 10 %), Kredite / Einlagen (110 → 80 %), materieller Buchwert je Aktie p. a. (0 → 10 %), Kurs-Buchwert / fairer Kurs-Buchwert (1,5 → 0,7) |
| Versicherer | Insurance (ohne Makler) | Eigenkapitalrendite, Schaden-Kosten-Quote (105 → 90 %, nur Schaden/Unfall, Spezial, Rück), Eigenkapital / Bilanzsumme (5 → 15 %), Ausschüttungsdeckung durch Gewinn (0,8 → 2,0), Buchwert je Aktie p. a., Kurs-Buchwert / fairer Kurs-Buchwert |
| REIT | REIT (ohne Mortgage) | FFO-Rendite (4 → 10 %), FFO je Aktie p. a. (0 → 6 %), Dividendendeckung durch FFO (1,0 → 1,43), Nettoschulden / EBITDA (9 → 5x), Zinsdeckung (2 → 5x), Schulden / Bilanzsumme (60 → 35 %) |
| Hypotheken-REIT | REIT—Mortgage | Eigenkapitalrendite, Eigenkapital / Bilanzsumme (8 → 25 %), Dividendendeckung durch Gewinn (0,8 → 1,2), Buchwert je Aktie p. a., Kurs-Buchwert / fairer Kurs-Buchwert |
| Finanzdienstleister | Asset Management, Capital Markets, Credit Services, Börsen, Versicherungsmakler | Standardmodell (kein Branchenmodell) |

Grundsätze:
- Je Kennzahl 0–100 Punkte linear; Modul-Score = Mittel seiner Kennzahlen; Branchen-Score = Mittel der Module, erst ab
  3 bewerteten Kennzahlen. Negative Werte (z. B. negativer FFO) sind echte Werte und bekommen 0 Punkte.
- Herkunft je Kennzahl: berechnet, **Näherung** (FFO = Gewinn + Abschreibungen − Veräußerungsgewinne; Schaden-Kosten-
  Quote mit Verwaltungskosten als Kostenteil) oder **Modellannahme** (fairer Kurs-Buchwert = (EK-Rendite − 2,5 %) /
  (Eigenkapitalkosten − 2,5 %), Eigenkapitalkosten per CAPM wie in Etappe 3).
- Abdeckungsregel: Eine Kennzahl zählt für einen Typ nur, wenn Yahoo sie bei mindestens 60 % der Werte dieses Typs
  liefert (ab 20 Werten). Sonst „Datenlücke“ – der Wert bleibt gespeichert, zählt aber nicht. Die Abdeckung je
  Kennzahl protokolliert der Investoren-Agent im Log und in `state/investoren/meta.json` (`branchen_abdeckung`).
- Nicht verfügbar und nie geschätzt: CET1, LCR, NPL-Quote (Banken), Solvency-II-Quote, Reserveabwicklung
  (Versicherer), NAV, AFFO, Belegungsquote (REITs).
- Das Datenvertrauen zählt bei diesen Typen die Kennzahlen des Branchenmodells als Pflichtkennzahlen mit.

Neue Yahoo-Posten (`investor_checks/daten.ZEILEN_ERWEITERT`, zählen nicht für die Mindestzahl je Periode): zinsunabhängiger
Aufwand, Risikovorsorge, Kredite, Einlagen, materieller Buchwert, immaterielle Werte, Prämien, Versicherungsleistungen,
Veräußerungsgewinne. Speicherung: Feld `b` in `state/investoren/ergebnis_NN.json`.

**Entscheidung E1 (nur classic_v2):** Finanzdienstleister zählen in classic_v1 weiter als „Bank“ (Kriterien ausgeblendet,
unverändert). Für das Vergleichsmodell classic_v2 prüft der Agent sie zusätzlich wie normale Firmen und speichert den
Konsens als `s2`; classic_v2 nutzt `s2`, wenn vorhanden. Tests: `test_branchenmodelle.py`, Golden-Test unverändert grün.
