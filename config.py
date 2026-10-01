"""
Zentrale Konfiguration - wird sowohl von der Streamlit-App (quant_terminal.py)
als auch vom GitHub-Actions-Cron (discord_price_alert.py) importiert, damit
Werte wie die Schwelle oder die Instrument-ID nur an EINER Stelle stehen.
"""
import datetime

# --- INSTRUMENT ---
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
LS_INSTRUMENT_ID = "3865540"  # ls-tc.de interne ID fuer LS9VFS
ANFANGSKURS = 160.68

# --- DEPOT ---
STARTKAPITAL = 13000.0
ENTNAHME_PM = 70.0
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# "simulation": Entnahme wird nur buchhalterisch vom Depotwert abgezogen,
#               die gehaltene Stueckzahl bleibt unveraendert (bisheriges Verhalten)
# "real":       Entnahme erfolgt tatsaechlich durch monatlichen Verkauf von
#               Anteilen zum dann gueltigen Kurs - Stueckzahl sinkt dauerhaft
ENTNAHME_MODUS_VERGLEICH = True  # zeigt beide Varianten parallel im Chart an

# --- ALARME ---
TAGESVERLUST_SCHWELLE_PCT = -1.0

# --- QUELLEN ---
WIKIFOLIO_PUBLIC_URL = "https://www.wikifolio.com/de/de/w/wfindizglo"
LS_TC_BASE_URL = "https://www.ls-tc.de/_rpc/json/instrument/chart/dataForInstrument"
LS_TC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": f"https://www.ls-tc.de/de/wikifolio/{LS_INSTRUMENT_ID}",
}

# --- STATE-SPEICHERUNG (GitHub Contents API, siehe github_store.py) ---
GITHUB_STATE_BRANCH = "app-state"
STATE_PATH_TRADES_DB = "state/trades_db.json"
STATE_PATH_ALARM = "state/alarm_state.json"
STATE_PATH_PRICE_ALERT = "state/price_alert_state.json"
STATE_PATH_WIKIFOLIO_ACTIVITY = "state/wikifolio_activity_state.json"
STATE_PATH_FETCH_FAIL_ALARM = "state/fetch_fail_alarm_state.json"


def price_history_csv_path(for_date=None):
    """Ein CSV-Pfad PRO MONAT (z.B. state/price_history/2026-08.csv), damit
    einzelne Dateien nicht unbegrenzt wachsen. Alte Monate bleiben als
    eigene Dateien erhalten - siehe github_store.py und die monatliche
    Squash-Routine fuer die Commit-Historie (nicht fuer die Dateien selbst!)."""
    d = for_date or datetime.date.today()
    return f"state/price_history/{d.strftime('%Y-%m')}.csv"
