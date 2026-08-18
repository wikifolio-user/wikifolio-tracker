"""
Zentrale Konfiguration - wird sowohl von der Streamlit-App (quant_terminal.py)
als auch vom GitHub-Actions-Cron (discord_price_alert.py) importiert, damit
Werte wie die Schwelle oder die Instrument-ID nur an EINER Stelle stehen.
"""
import datetime
from zoneinfo import ZoneInfo

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

# --- HANDELSZEITEN (Lang & Schwarz Exchange, Quelle: wikifolio.com/Partner-Seite) ---
# Mo-Fr 7:30-23:00, Sa 10:00-13:00, So 17:00-19:00 (jeweils Europe/Berlin,
# DST wird automatisch korrekt beruecksichtigt, da mit tz-aware datetime
# verglichen wird - siehe ist_handelszeit()).
TRADING_HOURS = {
    0: (datetime.time(7, 30), datetime.time(23, 0)),   # Montag
    1: (datetime.time(7, 30), datetime.time(23, 0)),   # Dienstag
    2: (datetime.time(7, 30), datetime.time(23, 0)),   # Mittwoch
    3: (datetime.time(7, 30), datetime.time(23, 0)),   # Donnerstag
    4: (datetime.time(7, 30), datetime.time(23, 0)),   # Freitag
    5: (datetime.time(10, 0), datetime.time(13, 0)),   # Samstag
    6: (datetime.time(17, 0), datetime.time(19, 0)),   # Sonntag
}


def ist_handelszeit(now_berlin):
    """now_berlin muss ein zeitzonen-bewusstes datetime in Europe/Berlin sein
    (pytz oder zoneinfo, egal - Hauptsache tz-aware)."""
    start, end = TRADING_HOURS.get(now_berlin.weekday(), (None, None))
    if start is None:
        return False
    return start <= now_berlin.time() <= end

# --- HANDELSKOSTEN-ANNAHME (für "Netto Real") ---
# Ein realer Verkauf läuft zum Geld-(Bid-)Kurs, nicht zum Mid-Kurs. Diese
# Annahme (in %) wird bei der realen Entnahme vom Kurs abgezogen, um die
# Renditeschmälerung durch den Spread realistischer abzubilden.
SPREAD_PCT = 0.15

# --- ECHTE KOSTENKENNZAHLEN (von wikifolio.com, Stand siehe Quelle) ---
# Diese Werte sind bereits im ls-tc.de-Kurs eingepreist (nicht zusätzlich
# von der App abgezogen!) - dienen hier nur der transparenten Anzeige.
ZERTIFIKAT_GEBUEHR_PA_PCT = 0.95   # "Certificate fee per year"
PERFORMANCE_FEE_PCT = 10.0        # "Performance fee" auf neue Höchststände

# --- HIGH-WATERMARK-ALARM ---
# Ersetzt das nicht zuverlässig auslesbare "Last Login"-Signal (wikifolio.com
# laedt das per JavaScript nach, mit einfachen HTTP-Requests nicht abrufbar).
# Stattdessen: eigene, garantiert verlässliche Berechnung aus den selbst
# gesammelten Kursdaten. Ein neues Allzeithoch ist zudem finanziell die
# relevantere Info - ab hier wird bei weiteren Gewinnen Performance Fee faellig.
STATE_PATH_HIGH_WATERMARK = "state/high_watermark_state.json"

# --- VERGLEICHSWERTE (Benchmarks), alle über ls-tc.de, gleiche API wie LS9VFS ---
BENCHMARKS = {
    "MSCI World (A0RPWH)": "44039",
    "Nasdaq-100 (A0F5UF)": "42380",
    "MSCI Semiconductors (LYX018)": "810652",
    "MSCI World IT Sector (A2PHCC)": "983893",
}

# --- QUELLEN ---
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
STATE_PATH_FETCH_FAIL_ALARM = "state/fetch_fail_alarm_state.json"
STATE_PATH_APP_ERROR = "state/app_error_state.json"


def price_history_csv_path(for_date=None):
    """Ein CSV-Pfad PRO MONAT (z.B. state/price_history/2026-08.csv), damit
    einzelne Dateien nicht unbegrenzt wachsen. Alte Monate bleiben als
    eigene Dateien erhalten - siehe github_store.py und die monatliche
    Squash-Routine fuer die Commit-Historie (nicht fuer die Dateien selbst!)."""
    d = for_date or datetime.date.today()
    return f"state/price_history/{d.strftime('%Y-%m')}.csv"


def pick_previous_close_from_history(history):
    """
    Robuste Vortageskurs-Ermittlung aus der ls-tc.de history-Serie
    ([timestamp_ms, close], chronologisch aufsteigend).

    Bug, den das hier behebt: kurz nach Handelsbeginn hat 'heute' oft noch
    KEINEN eigenen Eintrag in der history-Serie (der wird erst im Laufe des
    Tages nachgetragen). Ein simples "vorletztes Element" wuerde dann faelsch-
    licherweise VORGESTERN statt GESTERN liefern. Stattdessen: von hinten den
    ersten Eintrag suchen, dessen Datum wirklich vor heute liegt.

    Gibt None zurueck, falls kein passender Eintrag gefunden wird (Aufrufer
    sollte dann auf 'previousClose' aus der API-Antwort zurueckfallen).
    """
    if not history:
        return None
    heute = datetime.datetime.now(ZoneInfo("Europe/Berlin")).date()
    for ts_ms, close in reversed(history):
        try:
            eintrag_datum = datetime.datetime.fromtimestamp(
                ts_ms / 1000, tz=ZoneInfo("Europe/Berlin")
            ).date()
        except Exception:
            continue
        if eintrag_datum < heute:
            return float(close)
    return None
