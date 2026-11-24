# Pyramidenmanager

Zusätzliches Modul des Finanz-Dashboards. Der Pyramidenmanager berechnet Trend, Signale, Stops und Risiko für
gestaffelte Long-Käufe (Pyramiden) auf die vier Indizes Nasdaq 100, DAX 40, S&P 500 und Dow Jones.

Er gibt **keine Orders** auf und verändert weder Depot noch Produktivdaten. Die vorhandenen Analysewerkzeuge
(Gap Analyzer, Fear & Greed, KO-Rechner) werden nur **gelesen** und nicht verändert.

| Etappe | Inhalt | Stand |
|---|---|---|
| 1 | Rechenkern, Adapter, Nachkaufprüfung, Tests | fertig |
| 2 | Ansicht, WKN-Erfassung, Tranchenüberwachung, Zeitleiste | fertig |
| 3 | Backtest A–D | dieser Stand |
| 4 | Aktien-Pyramiden und Aktien-Trendscanner | geplant |
| 5 | Abschluss der Dokumentation | geplant |

## Dateien

| Datei | Aufgabe |
|---|---|
| `pyramide.py` | Rechenkern ohne Streamlit und ohne Netz: Trend-Score, Signale, Stufen, Stops, Risiko, dynamischer Hebel, Gap- und Fear-&-Greed-Einstiegswert, kombinierter Wert, Nachkaufprüfung |
| `pyramide_daten.py` | Adapter zu den vorhandenen Werkzeugen. Er liest nur und rechnet die Gap- und Fear-&-Greed-Werte nicht selbst nach. |
| `pyramide_ui.py` | Ansicht „Märkte → Pyramiden“: Index-Trendscanner, „Meine Pyramiden“ mit Überblick, Nachkauf prüfen & erfassen (WKN über onvista oder von Hand), Einstellungen je Pyramide, Zeitleiste |
| `pyramide_backtest.py` | Backtest der Strategien A–D ohne Vorausschau (Etappe 3) |
| `pyramide_backtest_ui.py` | Ansicht „Pyramiden → Backtest A–D“ |
| `test_pyramide.py` | Tests für Datenzuordnung, Zeitstempel, fehlende und veraltete Werte sowie Nachkaufentscheidungen |

## Tatsächlich verwendete Datenquellen

| Wert | Quelle | Werkzeug (unverändert) | Zeitstempel |
|---|---|---|---|
| Tageskerzen der 4 Indizes | Yahoo Finance, Cash-Index (`instrumentType` INDEX), nur abgeschlossene Kerzen. Geladen vom Kurs-Agenten nach `state/markt/ohlc.json`. | `markt_daten.py`, Prüfung mit `gap_analyzer.kerzen_pruefen` | Datum der letzten Kerze, Alter in abgeschlossenen Handelstagen laut `boersenkalender` |
| Trend-Score, ATR | wird aus diesen Kerzen berechnet | `pyramide.trend_score`, `pyramide.atr` | wie die Kerzen |
| Gaps (Arten High-Low, Close-Open und Opening Gap ab x %; Standard High-Low) | dieselben Kerzen | `gap_analyzer.erkennen`, `mit_lage`, `statistik` | wie die Kerzen |
| Fear & Greed je Index (DAX, NDX, SPX, DJI) | eigener Score aus den Kerzen; VIX, VXN und VXD als Vola-Faktor; geeicht an CNN | `fear_greed.karten` | Datum des letzten Werts |
| US-Marktumfeld | CNN Fear & Greed (US-weit), `state/markt/sentiment.json` | `fear_greed.karten`, Karte „us“ | CNN-Zeitstempel |
| KO-Zertifikate | Modell des KO-Rechners: Basispreis, KO-Schwelle, Bezugsverhältnis, Finanzierung, Euro/Dollar | `ko_rechner.basispreis_am`, `innerer_wert_eur` | – |

Der CNN-Wert ist **US-weit**. Er steht nur bei den drei US-Indizes und dort getrennt als `us_umfeld` mit dem Bezug
„us“. Für den DAX wird er nie verwendet. Für die indexspezifische Bewertung zählt immer der eigene Indexwert
(Bezug „index“).

## Speicherung

Die Pyramiden liegen je Benutzer in dessen eigenem Datenbereich unter `state/pyramiden.json`. Sie werden über die
App mit Versionsprüfung geschrieben. Gespeichert werden:

- Index, Name und Kapital
- Start und Status
- die eigenen Einstellungen
- die Tranchen: Datum, Art, WKN, Stückzahl, Kaufkurs, Indexstand, Anfangsstop und Produktdaten
- die Ereignisse

Das ist reine Buchführung der tatsächlich getätigten Käufe. Es wird keine Order ausgelöst, und das Depot wird nicht
verändert.

Den gemeinsamen Nachzieh-Stop berechnet die App aus den Tageskerzen seit dem Start neu (`pyramide.stop_verlauf`), mit
den Daten bis zum jeweiligen Tag. Er wird nicht gespeichert.

## Regeln (Startwerte in `pyramide.STANDARD`, alle je Pyramide änderbar)

Jede Pyramide speichert ihre eigenen Abweichungen unter `einstellungen`. `pyramide.cfg_fuer(pyr)` legt sie auf die
Startwerte. Die erlaubten Bereiche stehen in `pyramide.GRENZEN`: Werte außerhalb werden auf die Grenze gesetzt,
ungültige Werte ignoriert. Frei einstellbar sind unter anderem:

- **ATR:** die Länge (`atr_tage`, 5–50 Tage, Start 20) und alle ATR-Faktoren, also Nachkaufmarke, Anfangsstop,
  Nachzieh-Stop, KO-Puffer und Gap-Nähe.
- **Hebel:** der gewünschte Hebel (`hebel`, 1–20, Start „automatisch“). Er wird nicht gesperrt. Ist er höher als
  der zum Stop passende Hebel, erscheint eine Warnung, weil die KO-Schwelle dann über der höchsten KO-Schwelle
  liegt, die noch zum Stop passt.
- **Obergrenze für den vorgeschlagenen Hebel:** `hebel_max`, 1–20, Start 20.

- **Trend-Score 0–100:** setzt sich aus fünf Bausteinen zusammen.

  | Baustein | Punkte |
  |---|---|
  | Lage zur 50- und 200-Tage-Linie | 25 |
  | Steigung der Linien | 20 |
  | Momentum über 3, 6 und 12 Monate | 25 |
  | Nähe zum 52-Wochen-Hoch | 15 |
  | Anteil der Tage über der 50-Tage-Linie | 15 |

  Er nutzt nur Kerzen bis zum Entscheidungstag.
- **Erster Einstieg:** Score mindestens 60, Kurs über der 200-Tage-Linie und die 50-Tage-Linie über der
  200-Tage-Linie.
- **Nachkauf:**
  - Der Index liegt mindestens 1 ATR über dem letzten Kauf, und der Score liegt weiter bei mindestens 60.
  - Höchstens 20 Stufen.
  - Die Tranchen werden kleiner: Faktor 0,8 je Stufe, mindestens 20 % der ersten Tranche.
- **Stops:**
  - Anfangsstop je Tranche: Kaufkurs minus 2 ATR.
  - Gemeinsamer Nachzieh-Stop: höchster Schlusskurs minus 3 ATR. Er steigt nur.
  - Ausstiegssignal: Schlusskurs unter dem Stop oder Score unter 40.
- **Dynamischer Hebel:**
  - Der zum Stop passende Hebel = Kurs ÷ (Kurs − höchste KO-Schwelle). Die höchste KO-Schwelle liegt 1 ATR unter
    dem Stop.
  - Der Hebel ist frei wählbar. Liegt er darüber, gibt es eine Warnung und keine Sperre.
- **Risiko:**
  - Bis zum Stop höchstens 1 % je neuer Tranche und 6 % insgesamt.
  - Höchstens 50 % des Pyramidenkapitals in KO-Zertifikaten.
- **Gap-Wert (abgeleitet):**
  - Er beginnt bei 50.
  - Jedes offene Gap innerhalb von 2 ATR **unter** dem Kurs zieht bis zu 25 Punkte ab (mögliches Rücklaufziel).
    Jedes solche Gap **über** dem Kurs gibt bis zu 25 Punkte dazu (mögliches Ziel nach oben).
  - Gewichtet wird mit der Füllquote nach 20 Handelstagen aus der Statistik des Gap Analyzers und mit der Nähe zum
    Kurs.
  - Ein Gap ist nie allein ein Kauf- oder Verkaufssignal.
- **Fear & Greed** wird in drei Stufen getrennt geführt:
  1. Originalwert
  2. Deutung (Kategorie)
  3. Einstiegswert. Modus „konträr“ (Standard): 100 − Fear & Greed. Modus „trend“: Fear & Greed. Modus „aus“:
     zählt nicht.
- **Kombinierter Wert:**
  - 70 % Trend, 20 % Gap, 10 % Fear & Greed. Das ist eine Testkonfiguration und änderbar.
  - Fehlt ein gewichteter Teil oder ist er veraltet, wird der kombinierte Wert **nicht** berechnet. Ausgegeben
    wird dann „nicht berechenbar – … fehlt/veraltet“.
- **Veraltet:** Daten, die älter als 3 abgeschlossene Handelstage der jeweiligen Börse sind. Bei Fear & Greed gilt
  dieselbe Regel. Der eigene Status des Werkzeugs steht zusätzlich als `status_werkzeug` daneben.

## Prüfung vor jedem Nachkauf (`pyramide.nachkauf_pruefung`)

| Nr. | Prüfung | Art |
|---|---|---|
| 1 | Technische Trendbestätigung | Pflicht |
| 2 | Gültiges Einstiegs- bzw. Nachkaufsignal | Pflicht |
| 3 | Gap-Analyse | Hinweis: unterstützt, neutral, Vorsicht, fehlt oder veraltet |
| 4 | Fear & Greed | Hinweis |
| 5 | Bestehende offene Tranchen | Hinweis |
| 6 | Gesamtes Stop-Risiko | Pflicht |
| 7 | KO-Kapitalrisiko (Anteil des Kapitals in KO-Zertifikaten) | Pflicht |
| 7.5 | Hebel und KO-Abstand zum Stop | Hinweis: Warnung, keine Sperre, weil der Hebel frei wählbar ist |
| 8 | Verfügbares Risikobudget der neuen Tranche | Pflicht |

Erlaubt ist ein Nachkauf nur, wenn **alle Pflichtprüfungen** bestanden sind. Ein guter kombinierter Wert oder
positive Hinweise können eine nicht bestandene Pflichtprüfung nie überstimmen.

## Backtest A–D (`pyramide_backtest.py`)

| Strategie | Kauf (Stufe 1 und Nachkauf) |
|---|---|
| A | nur die technischen Regeln: Einstiegssignal bzw. Nachkauf ab +1 ATR und Trend-Score ≥ Schwelle |
| B | A und Gap-Wert ≥ 40 |
| C | A und Fear-&-Greed-Einstiegswert ≥ 40 |
| D | A und kombinierter Wert (Trend/Gap/F&G, 70/20/10) ≥ Einstiegsschwelle |

Ausstieg für alle gleich: Schluss unter dem Stop der Tranche (Anfangsstop oder gemeinsamer Nachzieh-Stop) oder
Trend-Score unter der Ausstiegsschwelle.

**Keine Vorausschau:**
- Entschieden wird am Tagesschluss, ausgeführt zur Eröffnung des nächsten Tages.
- Trend-Score, ATR, Stops und Gap-Analyse rechnen je Tag nur mit Kerzen bis zu diesem Tag. Die Gap-Analyse nutzt
  dafür das Werkzeug des Gap Analyzers auf den letzten 500 Handelstagen.
- Fear & Greed: Der eigene **Rohwert** ohne CNN-Eichung wird als Perzentil gegen die eigenen Rohwerte der drei Jahre
  davor gerechnet. Ohne Wert lassen C und D keinen Kauf zu.
- Ein Test sichert das ab: Kerzen nach einem Stichtag ändern das Ergebnis bis zu diesem Tag nicht.

**Größe je Tranche:**
- Das Risiko bis zum Anfangsstop ist Risiko-% × Stufenanteil des aktuellen Depotwerts.
- Begrenzt wird die Größe durch das Gesamtrisiko, den KO-Kapitalanteil und das vorhandene Geld.

**Kosten:** Spread je Runde, zur Hälfte bei Kauf und Verkauf, Gebühr je Order, bei KO die Finanzierung.

**Kennzahlen:**
- Endwert, Rendite und Rendite p. a., maximaler Drawdown, Zeit im Markt
- Pyramiden, Tranchen, Trefferquote, Ø Gewinn und Verlust, Profit-Faktor
- Kosten, KO-Ereignisse, gefilterte Signaltage
- Signalqualität: Indexveränderung 20 Handelstage nach jedem Neueinstieg
- Vergleich mit Kaufen & Halten

**Vereinfachungen:**
- KO = Basispreis, kein Restwert nach einem Knock-out
- keine Währungseffekte
- Dividenden nur, soweit sie im Index enthalten sind
- Die Regeln sind die Startwerte des Pyramidenmanagers.

## Grenzen

- Nur Long-Pyramiden und nur Tageskerzen.
- Der Wert einer ungehebelten Tranche („direkt“) folgt dem Index ohne Währungseffekt.
- KO-Tranchen werden ohne Spread und ohne Restwert nach einem Knock-out gerechnet.
- Die eigenen Fear-&-Greed-Werte sind an CNN geeicht. Für den Backtest (Etappe 3) wird diese Eichung nicht
  verwendet, weil sie CNN-Daten bis heute enthält. Stattdessen zählen nur Rohwerte im Vergleich mit der eigenen
  Vergangenheit bis zum jeweiligen Tag.
