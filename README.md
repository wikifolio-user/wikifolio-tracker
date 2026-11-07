# Finanz Dashboard

Streamlit-App (Depot, Charts, Planung & Analyse, Rechner). Zustände liegen als JSON auf dem State-Branch
`app-state`; Agenten laufen als GitHub Actions (`.github/workflows/`). Tests: `python -m unittest discover -p "test_*.py"`.

## 🎯 EKS-Investmentbewertung

Ideen für Nebengewerbe und Investments nach der **Engpasskonzentrierten Strategie (EKS, Wolfgang Mewes)** bewerten
und automatisch durchrechnen. Menü: *Geschäftsideen → 🎯 EKS-Bewertung*. Reiter je Idee: a) EKS-Phasen · b) Nutzwert · c) Finanzen ·
d) Szenarien · e) Ist & Abbruch.

| Datei | Inhalt |
|---|---|
| `eks_rechner/modell.py` | Datenmodell, Standardwerte, Bereinigung, Export/Import (JSON, CSV) |
| `eks_rechner/rechnen.py` | alle Kennzahlen, ohne Streamlit |
| `eks_ui.py` | Oberfläche: Übersicht, Idee bearbeiten (Tabs), Vergleich, Einstellungen |
| `eks_agent.py`, `.github/workflows/eks.yml` | Monatslauf (1. des Monats + manuell) |
| `test_eks.py` | Tests mit nachrechenbaren Beispielen und Randfällen (unittest, läuft auch mit pytest) |

Gespeichert wird je Benutzer in `state/eks_ideen.json` (Benutzer: `state/benutzer/<name>/eks_ideen.json`).

### Kennzahlen

| Kennzahl | Berechnung |
|---|---|
| Nutzwert (0–100) | Σ Gewicht × Score-Anteil / Σ Gewichte. Score 1–10 → (Score − 1) / 9; bei inversen Kriterien (Wettbewerb, Zeitbedarf, Risiko) (10 − Score) / 9. Stärken und brennendstes Problem zählen **nicht** noch einmal – sie stecken im EKS-Score |
| EKS-Score (10–100) | Mittel der 7 Phasen-Scores × 10; Engpass = Score der Phase 4 (brennendstes Problem) |
| Cashflow je Monat | Umsatz − variable Kosten (% vom Umsatz) − Fixkosten; im 12., 24. … Monat zusätzlich die Steuer des Geschäftsjahres; Monat 0 = −Startinvestition |
| Max. Kapitalbedarf | tiefster Stand des kumulierten Cashflows – so viel Geld steckt man maximal hinein |
| Break-even-Umsatz | Fixkosten / (1 − variable Kostenquote); bei Quote ≥ 100 % nicht erreichbar |
| Break-even-Monat | erster Monat mit Gewinn vor Steuern ≥ 0 (bei Umsatz > 0) |
| Amortisation | erster Monat mit kumuliertem Cashflow ≥ 0 (0 = keine Investition) |
| NPV | Σ Cashflow / (1 + i_m)^t mit i_m = (1 + Diskontzins)^(1/12) − 1 |
| IRR | monatlicher Zinsfuß (Bisektion), hochgerechnet auf p. a.; ohne Vorzeichenwechsel „nicht definiert“ |
| NPV Erwartungswert | NPV der drei Szenarien gewichtet mit ihren Wahrscheinlichkeiten (Standard 25/50/25) |
| Gewinn je Stunde (Engpass) | Summe Gewinn nach Steuern / Summe Stunden im Horizont (Anlaufzeit mit eigenen Stunden je Woche) |
| Mindest-Stundensatz | fester Wert oder – wenn gewählt – Netto-Gehalt des Hauptjobs / (Stunden je Woche × 52 / 12) |
| Sensitivität | NPV bei Umsatz ± 20 % und Kosten ± 20 % (Tornado-Chart) |
| Ampel | vier Bedingungen: Nutzwert ≥ Schwelle · NPV (realistisch) > 0 · €/h ≥ Mindestsatz · EKS-Score ≥ Schwelle **und** Engpass (Phase 4) ≥ Mindestwert (Standard 60 / 6). 🟢 alle erfüllt · 🟡 eine verfehlt · 🔴 zwei oder mehr |
| Ist gegen Plan | echte Monatswerte (Umsatz, Kosten, Stunden) ab dem Startmonat gegen das realistische Szenario, kumuliert vor Steuern |
| Abbruch-Kriterien | je Idee z. B. „Umsatz/Monat mindestens X ab Monat N“, „kumulierter Gewinn nach N Monaten mindestens X“, „€/h nach N Monaten mindestens X“, „höchstens X Stunden je Woche“ – greift eines, zeigen App und Monatslauf ⚠️ |

### Annahmen

- Umsatz läuft linear hoch: im Monat *m* der Anlaufzeit *m* / Anlauf des vollen Umsatzes; Fixkosten ab Monat 1 voll.
- Szenarien: Umsatz × Umsatz-Faktor, variable und fixe Kosten × Kosten-Faktor (Standard: pessimistisch 70 % / 115 %,
  realistisch 100 % / 100 %, optimistisch 130 % / 95 %; je Idee im Tab *Szenarien* änderbar).
- Beträge netto (ohne Umsatzsteuer).
- Steuer je Geschäftsjahr: (Jahresgewinn − Abschreibung der Startinvestition − Verlustvortrag) × persönlicher
  Grenzsteuersatz; Gewerbesteuer = (Grundlage − 24.500 € Freibetrag) × 3,5 % × Hebesatz, abzüglich Anrechnung auf
  die Einkommensteuer (bis 4,0 × Messbetrag). Verluste werden vorgetragen, nicht mit dem Gehalt verrechnet.
  Kein Restwert am Ende.
- Diskontzins = Opportunitätsrendite, Standard 7 % p. a. (die App speichert keine Depotrendite p. a.).
- 0 Stunden je Woche: keine €/h-Kennzahl, die Stunden-Bedingung der Ampel gilt als erfüllt.

### Gewichte und Schwellen ändern

In der App unter *Einstellungen*:
- **Kriterien und Gewichte**: Tabelle bearbeiten; neue Zeile = neues Kriterium (bestehende Ideen starten dort mit
  Score 5), *Invers* ankreuzen, wenn „viel davon“ schlecht ist. Die Summe der Gewichte muss 100 % ergeben.
- **Ampel-Schwellen**: Nutzwert, EKS-Score, Engpass (Phase 4).
- **Mindest-Stundensatz** fest oder aus Netto-Gehalt und Stunden des Hauptjobs, **Diskontierungszins**, die
  **Standard-Szenarien** (Faktoren und Wahrscheinlichkeiten) für neue Ideen.
- Wer die Kriterien nie geändert hatte, bekommt die neuen Standard-Kriterien (ohne Doppelzählung) automatisch;
  eigene Kriterien bleiben unverändert.

Zu jeder EKS-Phase gibt es in der App Leitfragen und ein Bewertungsraster (1–3 schwach … 9–10 herausragend).

Die Standardwerte selbst stehen in `eks_rechner/modell.py` (`STANDARD_KRITERIEN`, `STANDARD_EINSTELLUNGEN`,
`STANDARD_SZENARIEN`); die Sensitivität (± 20 %) in `eks_rechner/rechnen.py` (`SENSITIVITAET`).

### Export / Import

*Einstellungen → Export / Import*: JSON (vollständig, inkl. Phasentexte und Szenarien) oder CSV (Semikolon, deutsches
Komma; Scores, Finanzen und berechnete Kennzahlen – in Excel bearbeitbar). Beim Import werden Ideen mit gleicher
`id` ersetzt, neue angehängt.

### Monatslauf

`EKS-Ideen monatlich auswerten` (am 1. des Monats 06:17 UTC, manuell über *Actions → Run workflow*): rechnet alle
Ideen neu und speichert je Bereich die Zusammenfassung – Top 3, Ampel-Änderungen seit dem letzten Lauf, Ideen länger
als 30 Tage im Status „Test läuft“ und erreichte Abbruch-Kriterien. Sichtbar in der App unter *Einstellungen → Letzter Monatslauf*. Zusätzlich geht
die Zusammenfassung des Haupt-Kontos an Discord (Secret `DISCORD_WEBHOOK_URL`, wie die Preisalarme); ist der Webhook
nicht erreichbar, läuft alles andere normal weiter. Die Job-Zusammenfassung in GitHub enthält nur Zahlen.
