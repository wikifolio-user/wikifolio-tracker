"""Altersteilzeit & Rentenplanung - reine Rechenlogik (ohne Streamlit, CI-testbar).

- parameter.py: alle gesetzlichen Werte mit Quelle und Stand (in der UI editierbar)
- rente.py:     Altersgrenzen je Jahrgang, Wartezeiten, Abschlaege, Ausgleichszahlung, Hinterbliebenenrente
- steuer.py:    Einkommensteuer 2026 (Splitting, Progressionsvorbehalt, Fuenftelregelung), Rentenbesteuerung
- kapital.py:   Ansparen, Entnahmeplan, Abgeltungsteuer auf Entnahmen
- plan.py:      Jahr-fuer-Jahr-Rechnung (Arbeit -> Altersteilzeit -> Rente) und Vergleich
Orientierungshilfe - ersetzt keine Renten-, Steuer- oder Finanzberatung.
"""
