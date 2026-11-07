# Finanz Dashboard

Streamlit-App (Depot, Charts, Planung & Analyse, Rechner). Zustände liegen als JSON auf dem State-Branch
`app-state`; Agenten laufen als GitHub Actions (`.github/workflows/`). Tests: `python -m unittest discover -p "test_*.py"`.

## 🎯 EKS-Investmentbewertung

Ideen für Nebengewerbe und Investments nach der **Engpasskonzentrierten Strategie (EKS, Wolfgang Mewes)** bewerten
und automatisch durchrechnen. Menü: *Geschäftsideen → 🎯 EKS-Bewertung*.

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
| Nutzwert (0–100) | Σ Gewicht × Score-Anteil / Σ Gewichte. Score 1–10 → (Score − 1) / 9; bei inversen Kriterien (Wettbewerb, Zeitbedarf, Risiko) (10 − Score) / 9 |
| EKS-Score (10–100) | Mittel der 7 Phasen-Scores × 10 |
| Cashflow je Monat | Umsatz − variable Kosten (% vom Umsatz) − Fixkosten − Steuer; Monat 0 = −Startinvestition |
| Break-even-Umsatz | Fixkosten / (1 − variable Kostenquote); bei Quote ≥ 100 % nicht erreichbar |
| Break-even-Monat | erster Monat mit Gewinn vor Steuern ≥ 0 (bei Umsatz > 0) |
| Amortisation | erster Monat mit kumuliertem Cashflow ≥ 0 (0 = keine Investition) |
| NPV | Σ Cashflow / (1 + i_m)^t mit i_m = (1 + Diskontzins)^(1/12) − 1 |
| IRR | monatlicher Zinsfuß (Bisektion), hochgerechnet auf p. a.; ohne Vorzeichenwechsel „nicht definiert“ |
| Gewinn je Stunde (Engpass) | Ø Monatsgewinn nach Steuern / (Stunden je Woche × 52 / 12) |
| Sensitivität | NPV bei Umsatz ± 20 % und Kosten ± 20 % (Tornado-Chart) |
| Ampel | 🟢 Nutzwert ≥ Schwelle **und** NPV (realistisch) > 0 **und** €/h ≥ Mindestsatz · 🟡 eine Bedingung verfehlt · 🔴 sonst |

### Annahmen

- Umsatz läuft linear hoch: im Monat *m* der Anlaufzeit *m* / Anlauf des vollen Umsatzes; Fixkosten ab Monat 1 voll.
- Szenarien: Umsatz × Umsatz-Faktor, variable und fixe Kosten × Kosten-Faktor (Standard: pessimistisch 70 % / 115 %,
  realistisch 100 % / 100 %, optimistisch 130 % / 95 %; je Idee im Tab *Szenarien* änderbar).
- Steuer = Steuersatz × positiver Monatsgewinn (kein Verlustvortrag); kein Restwert, keine Abschreibung.
- Diskontzins = Opportunitätsrendite, Standard 7 % p. a. (die App speichert keine Depotrendite p. a.).
- 0 Stunden je Woche: keine €/h-Kennzahl, die Stunden-Bedingung der Ampel gilt als erfüllt.

### Gewichte und Schwellen ändern

In der App unter *Einstellungen*:
- **Kriterien und Gewichte**: Tabelle bearbeiten; neue Zeile = neues Kriterium (bestehende Ideen starten dort mit
  Score 5), *Invers* ankreuzen, wenn „viel davon“ schlecht ist. Die Summe der Gewichte muss 100 % ergeben.
- **Nutzwert-Schwelle**, **Mindest-Stundensatz**, **Diskontierungszins** und die **Standard-Szenarien** für neue Ideen.

Die Standardwerte selbst stehen in `eks_rechner/modell.py` (`STANDARD_KRITERIEN`, `STANDARD_EINSTELLUNGEN`,
`STANDARD_SZENARIEN`); die Sensitivität (± 20 %) in `eks_rechner/rechnen.py` (`SENSITIVITAET`).

### Export / Import

*Einstellungen → Export / Import*: JSON (vollständig, inkl. Phasentexte und Szenarien) oder CSV (Semikolon, deutsches
Komma; Scores, Finanzen und berechnete Kennzahlen – in Excel bearbeitbar). Beim Import werden Ideen mit gleicher
`id` ersetzt, neue angehängt.

### Monatslauf

`EKS-Ideen monatlich auswerten` (am 1. des Monats 06:17 UTC, manuell über *Actions → Run workflow*): rechnet alle
Ideen neu und speichert je Bereich die Zusammenfassung – Top 3, Ampel-Änderungen seit dem letzten Lauf, Ideen länger
als 30 Tage im Status „Test läuft“. Sichtbar in der App unter *Einstellungen → Letzter Monatslauf*. Zusätzlich geht
die Zusammenfassung des Haupt-Kontos an Discord (Secret `DISCORD_WEBHOOK_URL`, wie die Preisalarme); ist der Webhook
nicht erreichbar, läuft alles andere normal weiter. Die Job-Zusammenfassung in GitHub enthält nur Zahlen.
