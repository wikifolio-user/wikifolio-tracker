"""Realistische Testdaten fuer den UX-Durchgang (synthetisch, keine echten Personen)."""
import datetime
import json
import os

import login

MARKT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "markt")


def _chronik():
    ein = []
    heute = datetime.date(2026, 10, 16)
    texte = [
        ("alarm", "🚨 LS9VFS −1,4 % unter Schwelle", "Kurs 147,90 € (Vortag 150,00 €)"),
        ("alarm", "🏆 Neues Allzeithoch LS9VFS", "152,30 € – ab hier 10 % Performance Fee"),
        ("depot", "➕ Position angelegt: FF Inlinetrading (LS9VSU)", "Kaufdatum 02.03.2026 · Kaufkurs 210,500 € · Startkapital 5.000,00 €"),
        ("depot", "💶 Sparrate gespeichert: 100,00 €/Monat", ""),
        ("beobachtung", "➕ Beobachtung angelegt: MSCI World (A0RPWH)", "ID 44039"),
        ("planer", "📦 Musterdepot erstellt: Wachstum 2030", "6 Bausteine"),
        ("notiz", "Rebalancing geprüft", "Gewichte passen noch, nächste Prüfung im Januar."),
        ("zugang", "🔐 Anmeldung: maria", ""),
    ]
    for i in range(16):
        k, t, inh = texte[i % len(texte)]
        d = heute - datetime.timedelta(days=i * 3)
        ein.append({"id": 100 - i, "datum": d.isoformat(), "zeit": "" if k == "zugang" else f"{9 + i % 12:02d}:{(i * 7) % 60:02d}",
                    "kategorie": k, "typ": k, "titel": t, "inhalt": inh,
                    "quelle": "manuell" if k == "notiz" else "auto", "schluessel": f"s{i}"})
    return ein


def seed(f):
    f.seed("state/benutzer.json", {"benutzer": {
        "maria": {"hash": login.passwort_hash("Maria-Test-Pass-1"), "aktiv": True, "ansichten": None},
        "neu": {"hash": login.passwort_hash("Neu-Test-Pass-12"), "aktiv": True, "ansichten": None},
        "leser": {"hash": login.passwort_hash("Leser-Pass-123"), "aktiv": True,
                  "ansichten": ["🏠 Depot", "🧮 Zinseszinsrechner", "💶 Abfindungsrechner"]},
    }})
    # Admin
    f.seed("state/positionen.json", [
        {"id": "config-hauptposition", "name": "Hauptindizes Global", "wkn": "LS9VFS", "instrument_id": 3865540,
         "kaufdatum": "2025-07-09", "kaufkurs": 128.8, "startkapital": 13000.0},
        {"id": "pos-1", "name": "FF Inlinetrading", "wkn": "LS9VSU", "instrument_id": 4361124,
         "kaufdatum": "2026-03-02", "kaufkurs": 58.25, "startkapital": 5000.0},
        {"id": "pos-2", "name": "iShares Core MSCI World UCITS ETF USD (Acc)", "wkn": "A0RPWH", "instrument_id": 44039,
         "kaufdatum": "2024-05-15", "kaufkurs": 52.10, "startkapital": 25000.0},
        {"id": "pos-3", "name": "Festgeld-Anteil (ohne Kurs)", "wkn": "", "instrument_id": None,
         "kaufdatum": "2026-01-10", "kaufkurs": 1.0, "startkapital": 2000.0},
    ])
    f.seed("state/beobachtung.json", [
        {"id": "beob-1", "name": "Nasdaq-100 (A0F5UF)", "wkn": "A0F5UF", "instrument_id": "42380"},
        {"id": "beob-2", "name": "Gold - Xetra-Gold (A0S9GB)", "wkn": "A0S9GB", "instrument_id": "43298"},
    ])
    f.seed("state/sparplan_state.json", {"start_datum": "2026-01-15", "rate": 100.0,
                                         "phasen": [{"ab": "2026-01-15", "rate": 100.0}]})
    f.seed("state/entnahme_state.json", {"rate": 70.0})
    f.seed("state/trades_db.json", _chronik())
    # Benutzerin maria (eigenes Depot)
    f.seed("state/benutzer/maria/positionen.json", [
        {"id": "m1", "name": "Vanguard FTSE All-World", "wkn": "A1JX52", "instrument_id": 42965,
         "kaufdatum": "2025-02-03", "kaufkurs": 48.0, "startkapital": 12000.0},
        {"id": "m2", "name": "DAX ETF", "wkn": "593393", "instrument_id": 42446,
         "kaufdatum": "2025-11-20", "kaufkurs": 55.0, "startkapital": 3000.0},
    ])
    f.seed("state/benutzer/maria/beobachtung.json", [
        {"id": "mb1", "name": "Bitcoin - 21Shares ETP (A2T64E)", "wkn": "A2T64E", "instrument_id": "982480"}])
    f.seed("state/benutzer/maria/sparplan_state.json", {"start_datum": "2026-03-01", "rate": 50.0,
                                                        "phasen": [{"ab": "2026-03-01", "rate": 50.0}]})
    # Werte-Katalog der Watchlist (synthetisch) fuer "Wert hinzufuegen" im Portfolio Builder
    f.seed("state/planer/katalog_gross_0.json", {
        "stand": "2026-10-16", "felder": ["typ", "kat", "name", "kennung", "isin", "1J", "3J", "5J", "10J", "kurs",
                                          "div", "vola", "maxdd", "jahre"],
        "kategorien": {}, "zeilen": [
            ["aktie", "tech", "NVIDIA", "918422", "US67066G1040", 40, 300, 900, None, 165.20, 0.1, 45, -60, 20],
            ["aktie", "industrie", "Siemens", "723610", "DE0007236101", 20, 40, 60, None, 201.35, 2.5, 22, -35, 20],
            ["etf", "welt", "Vanguard FTSE All-World UCITS ETF Acc", "A2PKXG", "IE00BK5BQT80", 15, 30, 70, None,
             132.48, 0, 14, -25, 6],
            ["wikifolio", "wiki", "Hauptindizes Global", "LS9VFS", "DE000LS9VFS2", 25, None, None, None, 150.0,
             0, 18, -20, 2],
        ]})
    # Marktdaten (oeffentliche Ranglisten / Qualitaets-Score aus dem State-Branch)
    basis = os.path.join(MARKT, "state")
    for wurzel, _, dateien in os.walk(basis):
        for d in dateien:
            pfad = os.path.join(wurzel, d)
            rel = "state/" + os.path.relpath(pfad, basis).replace(os.sep, "/")
            with open(pfad, "rb") as fh:
                b = fh.read()
            f.STORE[rel] = (b, f._sha(b + rel.encode()))
