# Trading Intelligence – Backtest (Etappe 1)

Erstellt am 2026-11-28. Lernzeitraum bis 2019-01-01, Testzeitraum ab 2019-01-01 (Out-of-Sample). Gewichte und Schwellen wurden vorab festgelegt und nicht an diese Ergebnisse angepasst.

Untersucht: 43 Werte (10 aktie, 2 devisen, 22 etf, 4 index, 2 krypto, 3 rohstoff), Tageskerzen von Yahoo Finance ab 2005-01-03. Nicht analysierbar: 53 Dashboard-Werte (Wikifolios/Derivate ohne Börsenhistorie oder ohne Yahoo-Symbol); zu kurze oder fehlende Historie: 5 Werte.

## Ergebnis der Validierung

- long: zu wenige Testfälle mit Score ≥ 75 (4 < 30)
- short: zu wenige Testfälle mit Score ≥ 75 (0 < 30)

Solange eine Richtung nicht validiert ist, werden für sie in Etappe 3 keine Einstiegsalarme versendet.

## Alarm-Mindestanforderungen (Score ≥ 85, CRV ≥ 3, ≥ 2 unabhängige Bestätigungen, historisch validiert, liquide, Daten aktuell)

| Zeitraum | Fälle | pro Jahr | Trades | Trefferquote | Ø R | Median R |
|---|---|---|---|---|---|---|
| lern | 0 | 0.0 | 0 | – | – | – |
| test | 1 | 0.1 | 1 | 0 % | -1.07 R | -1.07 R |

## Score-Klassen (Trades mit Stop/Ziel 2/60 Tage)

| Richtung | Score | Lern: Trades | Lern: Ø R | Test: Trades | Test: Trefferquote | Test: Ø R | Test: Median 20-T.-Rendite |
|---|---|---|---|---|---|---|---|
| long | 85–100 | 0 | – | 1 | 0 % | -1.07 R | -2.5 % |
| long | 75–84 | 5 | +0.41 R | 3 | 100 % | +2.51 R | 6.2 % |
| long | 60–74 | 40 | +0.30 R | 64 | 41 % | +0.09 R | 0.6 % |
| long | unter 60 | 2649 | +0.10 R | 2848 | 50 % | +0.14 R | 1.3 % |
| short | 85–100 | 0 | – | 0 | – | – | – |
| short | 75–84 | 2 | +2.81 R | 0 | – | – | – |
| short | 60–74 | 14 | +0.17 R | 10 | 0 % | -1.08 R | -0.6 % |
| short | unter 60 | 2804 | -0.13 R | 2860 | 35 % | -0.17 R | -1.6 % |

## Setups (nur bestätigte Stufe)

| Setup | Lern: Trades | Lern: Ø R | Test: Trades | Test: Trefferquote | Test: Ø R |
|---|---|---|---|---|---|
| L_kapitulation | 3 | +0.84 R | 1 | 0 % | -1.15 R |
| L_divergenz | 24 | +0.00 R | 24 | 58 % | +0.39 R |
| L_spring | 83 | +0.08 R | 81 | 57 % | +0.31 R |
| L_rueckeroberung | 143 | +0.24 R | 148 | 57 % | +0.36 R |
| L_struktur | 357 | -0.02 R | 383 | 56 % | +0.25 R |
| L_kaufdruck | 94 | +0.15 R | 95 | 68 % | +0.38 R |
| L_ausbruch | 28 | -0.21 R | 48 | 67 % | +0.57 R |
| L_ruecksetzer | 370 | +0.10 R | 381 | 48 % | +0.14 R |
| L_mittelwert | 28 | -0.22 R | 31 | 61 % | +0.13 R |
| S_uebertreibung | 5 | -0.39 R | 14 | 43 % | -0.11 R |
| S_divergenz | 39 | -0.03 R | 25 | 44 % | -0.01 R |
| S_volumenschwaeche | 4 | +1.15 R | 5 | 0 % | -1.02 R |
| S_upthrust | 48 | -0.43 R | 55 | 44 % | +0.16 R |
| S_ablehnung | 126 | -0.01 R | 141 | 26 % | -0.19 R |
| S_bruch | 101 | -0.09 R | 100 | 51 % | -0.09 R |
| S_struktur | 330 | -0.19 R | 311 | 41 % | -0.21 R |
| S_erholung | 165 | +0.06 R | 127 | 41 % | -0.08 R |
| S_mittelwert | 5 | -1.04 R | 12 | 33 % | -0.45 R |

## Vergleich: alle Signale je Richtung

| Richtung | Zeitraum | Trades | Trefferquote | Ø R | Median 20-T.-Rendite | Anteil 20-T. positiv |
|---|---|---|---|---|---|---|
| long | lern | 2694 | 48 % | +0.11 R | 0.9 % | 57 % |
| long | test | 2916 | 50 % | +0.14 R | 1.3 % | 59 % |
| short | lern | 2820 | 37 % | -0.13 R | -1.1 % | 42 % |
| short | test | 2870 | 35 % | -0.17 R | -1.6 % | 38 % |
| long | lern: jeder Tag (ohne Signal) | – | – | – | 0.8 % | 56 % |
| long | test: jeder Tag (ohne Signal) | – | – | – | 1.2 % | 59 % |
| short | lern: jeder Tag (ohne Signal) | – | – | – | -1.1 % | 42 % |
| short | test: jeder Tag (ohne Signal) | – | – | – | -1.5 % | 39 % |

## Verteilung des Opportunity Scores (alle Signalfälle)

- long: Median 27, 90. Perzentil 46, 99. Perzentil 63, Maximum 86
- short: Median 24, 90. Perzentil 42, 99. Perzentil 57, Maximum 84

R = Ergebnis in Vielfachen des anfänglichen Risikos (Einstieg bis Stop), nach Kosten. Trefferquote = Anteil der Trades mit positivem Ergebnis. Der Opportunity Score ist keine Erfolgswahrscheinlichkeit. Short-Ergebnisse ohne Leihgebühren und Finanzierungskosten (dafür liegen keine Daten vor). Keine Anlageberatung.
