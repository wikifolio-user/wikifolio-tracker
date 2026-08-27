import datetime
import re
import logging
import traceback
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st

import config
import github_store

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PAGE CONFIG ---
st.set_page_config(page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# --- PWA / "App-Icon"-Unterstuetzung ---
# Ermoeglicht, die Seite ueber "Zum Home-Bildschirm hinzufuegen" wie eine
# eigene App aussehen zu lassen: eigenes Icon, kein Safari-Rahmen/Adresszeile
# beim Start vom Homescreen, passende Statusleisten-/Titelleisten-Farbe.
# Icons werden von GitHub (raw-content) geladen, da Streamlit selbst keine
# eigenen statischen Zusatzdateien unter frei waehlbaren Pfaden ausliefert.
_GH_RAW_BASE = "https://raw.githubusercontent.com/wikifolio-user/wikifolio-tracker/main"
st.markdown(f"""
<link rel="manifest" href="{_GH_RAW_BASE}/manifest.json">
<link rel="apple-touch-icon" href="{_GH_RAW_BASE}/icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="LS9VFS">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#000000">
""", unsafe_allow_html=True)

# --- SECRETS ---
DISCORD_WEBHOOK_URL = st.secrets.get("DISCORD_WEBHOOK_URL", "")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")   # z.B. "dein-user/wikifolio-tracker"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # Personal Access Token, Scope "repo"
GH_STATE_READY = bool(GITHUB_REPO and GITHUB_TOKEN)

BERLIN_TZ = pytz.timezone("Europe/Berlin")

# --- ZUSATZQUELLE: Referenzkurse (1 Woche/1 Monat/lfd. Jahr/1 Jahr) fuer die
# Performance-Uebersicht (Tag/Woche/Monat/Jahr/seit Kauf). Kommt bewusst von
# der oeffentlichen wikifolio-Seite, NICHT vom LS9VFS-Zertifikat-Endpunkt -
# dort stehen die vorgerechneten Referenzwerte direkt in der Performance-
# Tabelle, muessten sonst muehsam aus der Tages-History rekonstruiert werden.
LS_WIKIFOLIO_PERFORMANCE_URL = "https://www.ls-tc.de/de/wikifolio/3865540"

# --- TERMINAL STYLING ---
# Bewusst AUSSERHALB des periodisch aktualisierenden Fragments (siehe unten) -
# wird dadurch nur EINMAL pro echtem Seitenaufbau injiziert, nicht alle 5 Min.
# War die Hauptursache fuer das sichtbare Aufhellen/Verdunkeln bei jedem
# Fragment-Rerun (kompletter CSS-Neuaufbau zwingt den Browser zum Neu-Rendern
# der gesamten Seite).
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* ============================================================
       DESIGN-SYSTEM
       Typo:  Space Grotesk = Labels/Text (charaktervoll, technisch)
              IBM Plex Mono = ALLE Zahlen (echte Tabellenziffern,
              fuer Datendarstellung entworfen - Betraege stehen
              dadurch sauber untereinander statt zu "wackeln")
       Farbe: Graustufen als Basis. Gruen/Rot AUSSCHLIESSLICH fuer
              Kursveraenderungen - dadurch sticht das hervor, was
              wirklich wichtig ist.
       ============================================================ */
    :root {
        --ink:     #0A0B0D;   /* Hintergrund - nicht reines Schwarz, Hauch Blau */
        --surface: #131519;   /* erhoehte Flaechen */
        --line:    #21252C;   /* Haarlinien */
        --muted:   #7C8493;   /* Sekundaertext, tertiaer (Fussnoten) */
        --label:   #AAB1BE;   /* Zeilen-Labels - deutlich besser lesbar als --muted */
        --text:    #E9EBEF;   /* Primaertext */
        --up:      #16C784;
        --down:    #EA3943;
    }

    .stApp { background-color: var(--ink); color: var(--text); }

    /* Basistypo fuer Text - Icon-Elemente (z.B. Expander-Pfeile,
       Number-Input-Steppers) werden HIER BEWUSST AUSGENOMMEN, da diese
       eine eigene Icon-Font (Material Symbols) benoetigen. Wurde diese
       durch Space Grotesk ueberschrieben, zeigte Streamlit statt des
       Pfeil-Glyphs den rohen Icon-Namen als Text an (z.B. "_arrow_right"). */
    .stApp,
    .stApp *:not([data-testid="stIconMaterial"]):not(.material-icons):not(.material-symbols-rounded):not(.material-symbols-outlined) {
        font-family: 'Space Grotesk', -apple-system, sans-serif;
    }

    /* Streamlit-eigene Icons (Expander-Chevron, Stepper-Pfeile etc.)
       explizit auf ihrer Icon-Font belassen. */
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    }

    /* Zahlen bekommen konsequent die Datenschrift mit Tabellenziffern */
    .num, .q-price, .q-delta, .row-val, .hero-val, .hero-sub {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum" 1;
    }

    /* ---------- KURS-KOPF: die Zahl ist der Held der Seite ---------- */
    .quote {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
    }
    .q-name {
        font-size: 0.72rem; font-weight: 700; color: var(--text);
        letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 6px;
    }
    .q-price {
        font-size: 1.6rem; font-weight: 700; color: var(--text);
        line-height: 1; letter-spacing: -0.5px;
    }
    /* Kurs + Live-Badge + Boerse in einer Zeile: die Statusinfos gehoeren
       unmittelbar zum Kurs, nicht in die Kennzahlen-Chipreihe darunter. */
    .price-line {
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    }
    .q-delta { font-size: 1.1rem; font-weight: 600; margin-top: 12px; }
    .up { color: var(--up); } .down { color: var(--down); }

    /* ---------- META-CHIPS statt Punkt-getrennter Textwurst ----------
       Live-Status als farbiges Pill-Badge, restliche Fakten als eigene
       Chips - deutlich schneller erfassbar als eine lange "A · B · C"
       Zeile. Zeitstempel bewusst separat und kleiner: es ist die am
       wenigsten wichtige Information hier (Meta zur Meta). */
    .meta-row {
        display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
        margin-top: 14px;
    }
    .live-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(22, 199, 132, 0.12); color: var(--up);
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.2px;
        padding: 4px 10px 4px 8px; border-radius: 999px;
    }
    .live-pill.offline { background: rgba(234, 57, 67, 0.12); color: var(--down); }
    .meta-chip {
        font-size: 0.85rem; color: var(--label); font-weight: 500;
        background: rgba(255, 255, 255, 0.04);
        padding: 4px 10px; border-radius: 999px;
    }

    .live-dot {
        display: inline-block; width: 7px; height: 7px; border-radius: 50%;
        background: var(--up); animation: pulse 2.4s ease-in-out infinite;
        flex-shrink: 0;
    }
    .live-dot.offline { background: var(--down); animation: none; }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50%      { opacity: 0.35; }
    }
    @media (prefers-reduced-motion: reduce) {
        .live-dot { animation: none; }
    }

    /* ---------- HERO: eine einzige hervorgehobene Kennzahl ---------- */
    .hero {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: 12px; padding: 14px 16px; margin-bottom: 8px;
    }
    .hero-label {
        font-size: 0.72rem; font-weight: 700; color: var(--text);
        letter-spacing: 1.1px; text-transform: uppercase;
    }
    .hero-val { font-size: 1.6rem; font-weight: 700; color: var(--text); letter-spacing: -0.3px; }
    .hero-sub { font-size: 0.92rem; color: var(--label); font-weight: 500; }

    /* Kompakte Fussnote am Kachelende (Zeitstempel, Stueckzahl) - bewusst
       ohne Chip-Pille, damit sie moeglichst wenig Hoehe kostet. */
    .card-footnote {
        font-size: 0.72rem; color: var(--muted); margin-top: 8px;
    }

    /* ---------- STAT-CHIPS: gleiche Pill-Optik wie die Meta-Chips
       oben beim Kurs-Kopf - Label + Wert in einer Pille, statt Label
       ueber Wert gestapelt. Sorgt fuer ein einheitliches Design ueber
       beide Kacheln hinweg. ---------- */
    .stat-chip {
        display: inline-flex; align-items: center; gap: 7px;
        background: rgba(255, 255, 255, 0.04);
        padding: 6px 12px; border-radius: 999px;
    }
    .stat-chip-label {
        font-size: 0.68rem; font-weight: 700; color: var(--muted);
        text-transform: uppercase; letter-spacing: 0.4px;
    }
    .stat-chip-val {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.9rem; font-weight: 700; color: var(--text);
    }
    .stat-chip-val.up { color: var(--up); } .stat-chip-val.down { color: var(--down); }

    /* ---------- DATENZEILEN statt Kachel-Wildwuchs ----------
       Sekundaerwerte als hairline-getrennte Liste: ruhiger, dichter
       und deutlich schneller zu scannen als 8 gleich grosse Boxen. */
    .rows { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; margin-bottom: 22px; }
    .row {
        display: flex; justify-content: space-between; align-items: flex-start;
        gap: 14px; padding: 14px 18px; background: var(--surface);
        border-bottom: 1px solid var(--line);
    }
    .row:last-child { border-bottom: none; }
    .row-label {
        font-size: 0.88rem; color: var(--text); font-weight: 600;
        line-height: 1.35; flex: 1 1 42%; min-width: 0;
    }
    .row-val {
        font-size: 1rem; color: var(--text); font-weight: 700;
        text-align: right; line-height: 1.35; flex: 1 1 58%; min-width: 0;
        overflow-wrap: break-word;
    }
    .row-note {
        display: block; font-size: 0.78rem; color: var(--muted);
        font-weight: 400; margin-top: 4px; white-space: normal;
    }

    /* ---------- PERFORMANCE-TABELLE INNERHALB einer Kachel ----------
       Hairline-getrennte Zeitraum-Zeilen (Tag/Woche/Monat/Jahr/seit Kauf)
       direkt unter den Chips. Bewusst ohne eigenen Rahmen/Hintergrund -
       sie sitzt ja schon IN der Kachel, ein zweiter Rahmen wuerde
       verschachtelt und unruhig wirken. */
    .perf-table {
        margin-top: 10px; border-top: 1px solid var(--line);
    }
    .perf-row {
        display: flex; justify-content: space-between; align-items: baseline;
        gap: 12px; padding: 7px 2px; border-bottom: 1px solid var(--line);
    }
    .perf-row:last-child { border-bottom: none; padding-bottom: 2px; }
    .perf-label {
        font-size: 0.82rem; color: var(--label); font-weight: 500;
    }
    .perf-vals {
        display: inline-flex; gap: 12px; justify-content: flex-end;
        flex-wrap: wrap; text-align: right;
    }
    .perf-vals .up, .perf-vals .down, .perf-vals .neutral {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.85rem; font-weight: 600; white-space: nowrap;
    }
    .perf-vals .neutral { color: var(--label); }

    /* ---------- Streamlit-Eigenheiten ---------- */
    #MainMenu, footer { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; }
    /* Streamlits eigenes "Running ..."-Kaestchen ausblenden - wir zeigen
       stattdessen den zentrierten Ladefortschritt unten. */
    [data-testid="stStatusWidget"] { display: none !important; }

    /* ---------- ZENTRIERTER LADEFORTSCHRITT ---------- */
    .loading-overlay {
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; gap: 12px;
        padding: 48px 20px; text-align: center;
    }
    .loading-pct {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums;
        font-size: 2.2rem; font-weight: 700; color: var(--text);
        letter-spacing: -1px; line-height: 1;
    }
    .loading-bar {
        width: min(280px, 80vw); height: 6px; border-radius: 999px;
        background: var(--line); overflow: hidden;
    }
    .loading-bar-fill {
        height: 100%; background: var(--up); border-radius: 999px;
        transition: width 0.3s ease;
    }
    .loading-text {
        font-size: 0.85rem; color: var(--muted); font-weight: 500;
    }
    .block-container { padding-top: 1.8rem; padding-bottom: 4rem; max-width: 780px; }

    [data-testid="stNumberInput"] input {
        font-family: 'IBM Plex Mono', monospace !important;
        font-variant-numeric: tabular-nums;
        font-size: 1.15rem !important; font-weight: 600 !important;
    }
    [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {
        width: 42px !important; height: 42px !important; min-width: 42px !important;
    }
    [data-testid="stNumberInputStepUp"] svg, [data-testid="stNumberInputStepDown"] svg {
        width: 20px !important; height: 20px !important;
    }
    /* Tabs ruhiger, ohne dicke gruene Unterstreichung */
    [data-testid="stTabs"] button { font-size: 0.78rem !important; letter-spacing: 0.3px; }
</style>
""", unsafe_allow_html=True)


# --- STATE-HELFER (persistent über GitHub statt fluechtiges Streamlit-Dateisystem) ---
def gh_read(path, default):
    if not GH_STATE_READY:
        return default
    data, _ = github_store.get_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, GITHUB_TOKEN, default=default)
    return data if data is not None else default


@st.cache_data(ttl=60)
def gh_read_cached(path, default):
    """Wie gh_read, aber 60s gecacht - für Status-/Alarm-Reads, die bei jedem
    30s-Autorefresh sonst unnötig oft die GitHub-API belasten (Rate-Limit
    5.000/Std.). NICHT für Daten verwenden, die sofort nach einem Schreiben
    im selben Nutzer-Flow wieder gelesen werden müssen (z.B. Trader-Log) -
    dafür bleibt gh_read() ungecacht."""
    return gh_read(path, default)


def gh_write(path, obj, message="update state [skip ci]"):
    if not GH_STATE_READY:
        return False
    return github_store.put_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, obj, GITHUB_TOKEN, message=message)


# --- APP-FEHLER AN DISCORD MELDEN (Punkt 10) ---
def notify_app_error(context, exc):
    """Meldet einen Fehler INNERHALB der Streamlit-App an Discord (nicht nur
    in die schwer einsehbaren Cloud-Logs). Cooldown pro 'context' (z.B. Tab-
    Name), damit ein wiederholt fehlschlagender Bereich nicht bei jedem
    30s-Autorefresh erneut pingt."""
    logging.error(f"App-Fehler in '{context}': {exc}", exc_info=True)  # voller Traceback jetzt in den Logs
    if not DISCORD_WEBHOOK_URL:
        return

    state = gh_read_cached(config.STATE_PATH_APP_ERROR, {})
    now = datetime.datetime.now(BERLIN_TZ)
    last_str = state.get(context)
    cooldown_ok = True
    if last_str:
        try:
            cooldown_ok = (now - datetime.datetime.fromisoformat(last_str)).total_seconds() > 30 * 60
        except Exception:
            pass

    if not cooldown_ok:
        return

    msg = (f"🐞 **App-Fehler ({config.WKN})**\n"
           f"Bereich: **{context}**\n"
           f"Fehler: `{type(exc).__name__}: {str(exc)[:200]}`\n"
           f"```\n{traceback.format_exc()[-1200:]}\n```\n"
           f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}")
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
        state[context] = now.isoformat()
        gh_write(config.STATE_PATH_APP_ERROR, state, message="update app error state [skip ci]")
    except Exception as e:
        logging.error(f"Discord App-Error-Alert Fehler: {e}")


# --- ZAHLENFORMATIERUNG (Punkt = Tausender, Komma = Dezimal) ---
def fmt(val, dec=2):
    if dec > 0:
        s = f"{val:,.{dec}f}"
    else:
        s = f"{val:,.0f}"
    return f"{s.replace(',', 'X').replace('.', ',').replace('X', '.')}€"

# --- VOLLAUTOMATISCHER LIVE-KURS ABRUF (ls-tc.de, direkter Emittent LS9VFS) ---
@st.cache_data(ttl=30)
def get_live_market_data():
    """
    Holt den aktuellen Mid-Kurs direkt von ls-tc.de (Lang & Schwarz
    TradeCenter), dem Emittenten des Zertifikats. Kostenlos, kein API-Key nötig.
    Vortageskurs: aus info.plotlines[id="previousDay"].value (siehe
    config.extract_previous_close - DAS ist der Ort, wo ls-tc.de den echten
    Vortageswert mitliefert, kein top-level 'previousClose'-Feld). Die
    History-Suche dient nur noch als Rückfalloption.
    """
    params = {
        "container": "chart1",
        "instrumentId": config.LS_INSTRUMENT_ID,
        "marketId": "1",
        "quotetype": "mid",
        "series": "intraday,history,flags",
        "type": "",
        "localeId": "2",
    }

    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params, headers=config.LS_TC_HEADERS, timeout=6)
        r.raise_for_status()
        data = r.json()

        intraday = (
            data.get("series", {}).get("intraday", {}).get("data")
            or data.get("intraday", {}).get("data")
            or []
        )
        if intraday:
            akt = float(intraday[-1][1])

            vor = config.extract_previous_close(data)

            if vor is None:
                history = (
                    data.get("series", {}).get("history", {}).get("data")
                    or data.get("history", {}).get("data")
                    or []
                )
                vor = config.pick_previous_close_from_history(history)

            if vor is None:
                vor = float(intraday[0][1])

            if akt > 0 and vor > 0:
                return akt, vor, "ls-tc.de Live (Emittent)"

        logging.warning("ls-tc.de: Unerwartete JSON-Struktur, kein Kurs extrahiert.")
    except Exception as e:
        logging.error(f"Fehler beim Abruf von ls-tc.de: {e}")

    return None, None, "Fehler – keine Live-Daten"


# --- ECHTE HISTORISCHE DATEN VON ls-tc.de LADEN ---
@st.cache_data(ttl=300)
def get_historical_market_data(start_date, end_date, live_close_fallback):
    """
    Holt die Tages-History direkt von ls-tc.de. Da der Endpunkt primär
    Schlusskurse liefert, werden Open/High/Low pragmatisch aus dem Close
    approximiert, sofern die API keine echten OHLC liefert.
    """
    params = {
        "container": "chart1",
        "instrumentId": config.LS_INSTRUMENT_ID,
        "marketId": "1",
        "quotetype": "mid",
        "series": "history",
        "type": "",
        "localeId": "2",
    }
    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params, headers=config.LS_TC_HEADERS, timeout=8)
        r.raise_for_status()
        raw = r.json()
        history = (
            raw.get("series", {}).get("history", {}).get("data")
            or raw.get("history", {}).get("data")
            or []
        )
        if history:
            rows = []
            for ts_ms, close in history:
                ts = pd.to_datetime(ts_ms, unit="ms")
                if ts.date() < start_date or ts.date() > end_date:
                    continue
                rows.append({"Date": ts, "Close": float(close)})
            if rows:
                df = pd.DataFrame(rows).set_index("Date").sort_index()
                df = df[df["Close"] > 0]
                if not df.empty:
                    df["Open"] = df["Close"]
                    df["High"] = df["Close"] * 1.003
                    df["Low"] = df["Close"] * 0.997
                    return df[["Open", "High", "Low", "Close"]], "ls-tc.de Live (Emittent)"

        logging.warning("ls-tc.de: Keine verwertbare History-Struktur gefunden.")
    except Exception as e:
        logging.error(f"Fehler beim Laden der Historie von ls-tc.de: {e}")

    # --- FALLBACK: klar gekennzeichnete synthetische Daten, NICHT echt ---
    date_range = pd.date_range(start=start_date, end=end_date, freq="B")
    n = len(date_range)
    import numpy as np
    np.random.seed(42)
    base_prices = [
        config.ANFANGSKURS * ((live_close_fallback / config.ANFANGSKURS) ** (i / max(1, n - 1)))
        for i in range(n)
    ]
    noise = np.random.normal(0, live_close_fallback * 0.003, n)
    prices = [max(10, p + n_val) for p, n_val in zip(base_prices, noise)]
    prices[-1] = live_close_fallback

    df = pd.DataFrame(index=date_range)
    df["Close"] = prices
    df["Open"] = prices
    df["High"] = [p * 1.005 for p in prices]
    df["Low"] = [p * 0.995 for p in prices]
    return df, "⚠️ SYNTHETISCH (Fallback, KEINE ECHTEN DATEN)"


# --- BENCHMARK-VERGLEICHSDATEN (ls-tc.de, gleiche API wie LS9VFS) ---
@st.cache_data(ttl=3600)
def get_benchmark_history(instrument_id, start_date, end_date):
    """Holt Tages-Schlusskurse für einen Vergleichswert (ETF) von ls-tc.de.
    Gibt eine Series (Index=Datum, Value=Close) zurück, oder None bei Fehler -
    Vergleichswerte sind "nice to have", kein Grund die App abstürzen zu lassen."""
    headers = {
        "User-Agent": config.LS_TC_HEADERS["User-Agent"],
        "Referer": f"https://www.ls-tc.de/de/etf/{instrument_id}",
    }
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "history", "type": "", "localeId": "2",
    }
    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        raw = r.json()
        history = (
            raw.get("series", {}).get("history", {}).get("data")
            or raw.get("history", {}).get("data") or []
        )
        rows = []
        for ts_ms, close in history:
            ts = pd.to_datetime(ts_ms, unit="ms")
            if start_date <= ts.date() <= end_date:
                rows.append({"Date": ts, "Close": float(close)})
        if not rows:
            return None
        s = pd.DataFrame(rows).set_index("Date").sort_index()["Close"]
        return s[s > 0]
    except Exception as e:
        logging.warning(f"Benchmark {instrument_id} nicht ladbar: {e}")
        return None


def benchmark_normiert_auf_startkapital(df_index, instrument_id, start_date, end_date, startkapital):
    """Reindext den Benchmark-Kurs auf die Handelstage von df_chart und
    skaliert ihn so, dass er am ersten ECHTEN Handelstag beim Startkapital
    beginnt. Kein Backfill mehr: existiert der Wert zu Beginn des Zeitraums
    noch nicht (z.B. spaeter aufgelegtes Produkt), bleibt die Linie davor
    leer statt rueckwirkend erfunden zu werden. Gibt (Series, erstes_echtes_Datum)
    zurueck."""
    s = get_benchmark_history(instrument_id, start_date, end_date)
    if s is None or s.empty:
        return None, None
    erstes_echtes_datum = s.index.min()
    s_reindexed = s.reindex(df_index).ffill()
    gueltige = s_reindexed.dropna()
    if gueltige.empty or gueltige.iloc[0] == 0:
        return None, None
    normiert = s_reindexed / gueltige.iloc[0] * startkapital
    return normiert, erstes_echtes_datum


@st.cache_data(ttl=1800)
def get_performance_referenzwerte():
    """Holt die Referenzkurse fuer 1 Woche/1 Monat/lfd. Jahr/1 Jahr von der
    oeffentlichen wikifolio-Seite auf ls-tc.de. Dient NUR als Basis fuer die
    Performance-Uebersicht (Tag/Woche/Monat/Jahr/seit Kauf) - der Live-Kurs
    selbst kommt weiterhin ausschliesslich aus get_live_market_data() oben.
    30 Min. Cache, da sich diese Referenzwerte nur einmal taeglich aendern.

    Zweistufig: primaer BeautifulSoup (liest die Performance-Tabelle strukturell
    ueber die Tabellenzeilen aus und ueberlebt damit reine Layout-/CSS-Aenderungen),
    als Fallback der einfachere Regex-Ansatz. Schlaegt beides fehl oder ist bs4
    nicht installiert, wird ein leeres Dict zurueckgegeben - die Anzeige laesst
    die betroffenen Zeilen dann einfach weg, statt die App abstuerzen zu lassen."""
    LABEL_MAP = {"1 woche": "Woche", "1 monat": "Monat",
                 "lfd. jahr": "YTD", "1 jahr": "Jahr"}

    def zahl(s):
        return float(s.replace(".", "").replace(",", "."))

    try:
        r = requests.get(
            LS_WIKIFOLIO_PERFORMANCE_URL, timeout=10,
            headers={"User-Agent": config.LS_TC_HEADERS.get("User-Agent", "Mozilla/5.0")},
        )
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logging.warning(f"Performance-Referenzwerte: Seite nicht abrufbar: {e}")
        return {}

    # --- 1. Versuch: strukturell ueber die Tabellenzeilen ---
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        referenz = {}
        for tr in soup.find_all("tr"):
            zellen = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(zellen) < 2:
                continue
            key = LABEL_MAP.get(zellen[0].lower())
            if not key:
                continue
            # erste Zelle nach dem Label, die wie eine deutsche Dezimalzahl aussieht
            for zelle in zellen[1:]:
                m = re.fullmatch(r"([\d.]+,\d+)\s*€?", zelle)
                if m:
                    referenz[key] = zahl(m.group(1))
                    break
        if referenz:
            return referenz
        logging.warning("Performance-Referenzwerte: bs4 fand keine Tabellenzeilen, nutze Regex-Fallback.")
    except ImportError:
        logging.info("Performance-Referenzwerte: beautifulsoup4 nicht installiert, nutze Regex-Fallback.")
    except Exception as e:
        logging.warning(f"Performance-Referenzwerte: bs4-Parsing fehlgeschlagen ({e}), nutze Regex-Fallback.")

    # --- 2. Versuch (Fallback): Regex direkt auf dem Rohtext ---
    try:
        referenz = {}
        for label, key in LABEL_MAP.items():
            m = re.search(re.escape(label) + r"\D*?([\d.]+,\d+)", html, re.IGNORECASE)
            if m:
                referenz[key] = zahl(m.group(1))
        return referenz
    except Exception as e:
        logging.warning(f"Performance-Referenzwerte: auch Regex-Fallback fehlgeschlagen: {e}")
        return {}


def check_and_alert_fetch_failure(is_live_data, is_live_history):
    """Meldet per Discord, wenn Live-Kurs und/oder Chart-Historie gerade NICHT
    echt sind - mit 30-Min-Cooldown, damit nicht jede Sekunde gepingt wird."""
    if not DISCORD_WEBHOOK_URL:
        return
    state = gh_read_cached(config.STATE_PATH_FETCH_FAIL_ALARM, {"last_alert": None, "war_down": False})
    now = datetime.datetime.now(BERLIN_TZ)
    is_down = (not is_live_data) or (not is_live_history)

    last_alert = None
    if state.get("last_alert"):
        try:
            last_alert = datetime.datetime.fromisoformat(state["last_alert"])
        except Exception:
            pass
    cooldown_ok = (last_alert is None) or ((now - last_alert).total_seconds() > 30 * 60)

    if is_down and cooldown_ok:
        msg = (f"⚠️ **Datenquelle down ({config.WKN})**\n"
               f"ls-tc.de liefert gerade keine echten Live-/Chartdaten mehr. "
               f"App zeigt Fallback-/Synthetikwerte an.\n"
               f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}")
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            state["last_alert"] = now.isoformat()
        except Exception as e:
            logging.error(f"Discord Fetch-Fail-Alarm Fehler: {e}")
    elif not is_down and state.get("war_down"):
        msg = f"✅ **Datenquelle wieder OK ({config.WKN})** — ls-tc.de liefert wieder Live-Daten."
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
        except Exception as e:
            logging.error(f"Discord Fetch-Recover Fehler: {e}")

    state["war_down"] = is_down
    gh_write(config.STATE_PATH_FETCH_FAIL_ALARM, state, message="update fetch fail alarm state [skip ci]")


# --- GESAMTE RENDER-LOGIK ALS FRAGMENT ---
# Vermeidet den harten Full-Page-Rerun von st_autorefresh (sichtbares
# Aufhellen/Neuzeichnen alle 30s). Ein Fragment aktualisiert sich selbst
# periodisch, ohne die komplette Seite neu zu bauen/zu scrollen.
@st.fragment(run_every="5m")
def render_dashboard():
    now_berlin = datetime.datetime.now(BERLIN_TZ)
    heute_date = now_berlin.date()

    aktueller_kurs, vortag_kurs, fetched_source = get_live_market_data()

    is_live_data = "Fehler" not in fetched_source

    if not is_live_data:
        aktueller_kurs, vortag_kurs = 302.980, 302.100
        fetched_source = "⚠️ FALLBACK-WERT (KEINE ECHTEN DATEN)"

    df_chart, hist_source_name = get_historical_market_data(config.KAUFDATUM, heute_date, aktueller_kurs)
    is_live_history = "SYNTHETISCH" not in hist_source_name

    check_and_alert_fetch_failure(is_live_data, is_live_history)

    if not df_chart.empty:
        df_chart.iloc[-1, df_chart.columns.get_loc("Close")] = aktueller_kurs
        df_chart.iloc[-1, df_chart.columns.get_loc("High")] = max(df_chart.iloc[-1]["High"], aktueller_kurs)
        df_chart.iloc[-1, df_chart.columns.get_loc("Low")] = min(df_chart.iloc[-1]["Low"], aktueller_kurs)

    # --- ANFANGSKAPITAL & ENTNOMMENES KAPITAL: manuell anpassbar ---
    # Still aus dem gespeicherten Zustand lesen (Standard: config-Werte) - die
    # sichtbaren Eingabefelder selbst stehen weiter unten, direkt unter der
    # "Veränderung vs. Vortag"-Kachel. Aendert der Nutzer das Anfangskapital,
    # wird die Stueckzahl konsistent neu berechnet (Anfangskapital / Kaufkurs).
    startkapital_aktiv = st.session_state.get("haupt_startkapital_input", float(config.STARTKAPITAL))
    stueckzahl_aktiv = startkapital_aktiv / config.ANFANGSKURS

    df_chart["Startkapital"] = startkapital_aktiv

    # --- HIGH WATERMARK: mit echter Historie initialisieren/korrigieren ---
    # Der Cron kennt beim allerersten Lauf nur den aktuellen Kurs als "Hoch" -
    # hier wird das (still, ohne Alarm) auf den tatsächlichen historischen
    # Höchststand korrigiert, falls der genauer/höher ist.
    if not df_chart.empty:
        historischer_hoechststand = float(df_chart["Close"].max())
        historischer_hoechststand_datum = df_chart["Close"].idxmax()  # echtes Datum des Hochs, nicht "jetzt"
        hw_state = gh_read_cached(config.STATE_PATH_HIGH_WATERMARK, None)
        aktuelles_hoch = float(hw_state["high_watermark"]) if hw_state and "high_watermark" in hw_state else 0.0
        korrigiertes_hoch = max(historischer_hoechststand, aktuelles_hoch)

        if historischer_hoechststand >= aktuelles_hoch:
            # Die Chart-Historie kennt das (mindestens ebenso) hohe Hoch - deren echtes Datum nutzen
            high_watermark_datum = historischer_hoechststand_datum.strftime("%d.%m.%Y")
        else:
            # Der gespeicherte State (z.B. vom Cron erfasster Intraday-Wert) ist hoeher als
            # die Tages-Schlusskurse - dessen eigenes gespeichertes Datum nutzen
            gespeichertes_datum = hw_state.get("erreicht_am") if hw_state else None
            try:
                high_watermark_datum = datetime.datetime.fromisoformat(gespeichertes_datum).strftime("%d.%m.%Y") if gespeichertes_datum else "-"
            except Exception:
                high_watermark_datum = "-"

        if not hw_state or korrigiertes_hoch > aktuelles_hoch:
            gh_write(
                config.STATE_PATH_HIGH_WATERMARK,
                {"high_watermark": korrigiertes_hoch, "erreicht_am": datetime.datetime.now(BERLIN_TZ).isoformat()},
                message="app: korrigiere/initialisiere high watermark [skip ci]",
            )
        high_watermark_anzeige = korrigiertes_hoch
    else:
        high_watermark_anzeige = aktueller_kurs
        high_watermark_datum = "-"

    start_dt = pd.to_datetime(config.KAUFDATUM)
    def get_entnahme_at_date(ts):
        months = (ts.year - start_dt.year) * 12 + (ts.month - start_dt.month)
        if ts.day < start_dt.day:
            months -= 1
        return max(0, months) * config.ENTNAHME_PM

    df_chart["Kumulierte_Entnahme"] = [get_entnahme_at_date(ts) for ts in df_chart.index]

    entnommen_aktiv = st.session_state.get("haupt_entnommen_input", 0.0)
    sparrate_aktiv = st.session_state.get("haupt_sparrate_input", 0.0)

    # --- SPARPLAN: Startdatum persistent verfolgen (GitHub-State), damit die
    # Berechnung nach einem Neustart nicht auf 0 zurueckfaellt. Wird beim
    # ersten Aktivieren (>0€) auf heute gesetzt, bei 0€ wieder geloescht -
    # reaktivieren startet die Zaehlung dann wieder neu ab dem Tag.
    #
    # Fachlich korrekt: eine Einzahlung kauft zusaetzliche ANTEILE zum
    # jeweiligen Monats-Kurs (nicht einfach ein fixer, nicht mitwachsender
    # Betrag) - diese Anteile schwanken danach mit dem Kurs mit, genau wie
    # die urspruenglichen. Deshalb fliesst das direkt in die Stueckzahl und
    # damit in den BRUTTO-Wert ein, nicht nur additiv in Netto. ---
    sparplan_state = gh_read_cached(config.STATE_PATH_SPARPLAN, {})
    zusaetzliche_stueckzahl_sparplan = 0.0
    if sparrate_aktiv > 0:
        if not sparplan_state.get("start_datum"):
            sparplan_state = {"start_datum": heute_date.isoformat()}
            gh_write(config.STATE_PATH_SPARPLAN, sparplan_state, message="sparplan gestartet [skip ci]")
        sparplan_start = datetime.date.fromisoformat(sparplan_state["start_datum"])
        monate_sparplan = max(0, (heute_date.year - sparplan_start.year) * 12 + (heute_date.month - sparplan_start.month))
        if heute_date.day < sparplan_start.day:
            monate_sparplan -= 1
        monate_sparplan = max(0, monate_sparplan)

        if not df_chart.empty:
            for k in range(0, monate_sparplan + 1):
                ziel_datum = pd.Timestamp(sparplan_start) + pd.DateOffset(months=k)
                passende_tage = df_chart.index[df_chart.index <= ziel_datum]
                preis_am_einzahlungstag = float(df_chart.loc[passende_tage[-1], "Close"]) if len(passende_tage) else aktueller_kurs
                if preis_am_einzahlungstag > 0:
                    zusaetzliche_stueckzahl_sparplan += sparrate_aktiv / preis_am_einzahlungstag
    else:
        if sparplan_state.get("start_datum"):
            gh_write(config.STATE_PATH_SPARPLAN, {}, message="sparplan gestoppt [skip ci]")

    # --- BENCHMARKS: gleiche Handelstage, normiert auf dasselbe Startkapital ---
    # Zentrierter Ladefortschritt mit Prozentangabe statt Streamlits kleinem
    # "Running get_benchmark_history(...)"-Widget oben rechts (per CSS
    # ausgeblendet). Jeder Vergleichswert ist ein eigener Netzabruf, deshalb
    # laesst sich der Fortschritt hier ehrlich in Schritten anzeigen.
    def lade_benchmarks_mit_fortschritt(df_index, start_datum, kapital, hinweis="Lade Vergleichswerte"):
        """Laedt alle Vergleichswerte und zeigt dabei einen zentrierten
        Fortschrittsbalken mit Prozentangabe. Gibt (series_dict, startdaten_dict)
        zurueck. Die Anzeige wird am Ende restlos entfernt."""
        series, startdaten = {}, {}
        items = list(config.BENCHMARKS.items())
        gesamt = len(items)
        box = st.empty()
        for i, (label, inst_id) in enumerate(items):
            pct = int(i / gesamt * 100) if gesamt else 100
            box.markdown(f"""
            <div class="loading-overlay">
                <div class="loading-pct">{pct} %</div>
                <div class="loading-bar"><div class="loading-bar-fill" style="width:{pct}%"></div></div>
                <div class="loading-text">{hinweis} … ({i + 1}/{gesamt})</div>
            </div>
            """, unsafe_allow_html=True)
            s, erstes_datum = benchmark_normiert_auf_startkapital(
                df_index, inst_id, start_datum, heute_date, kapital
            )
            if s is not None:
                series[label] = s
                startdaten[label] = erstes_datum
        box.empty()
        return series, startdaten

    benchmark_series, benchmark_start_daten = lade_benchmarks_mit_fortschritt(
        df_chart.index, config.KAUFDATUM, startkapital_aktiv
    )

    # --- SIMULATION (bisheriges Verhalten): Stückzahl bleibt konstant, Entnahme
    # wird nur buchhalterisch vom Bruttowert abgezogen. ---
    df_chart["Depotwert_Brutto"] = df_chart["Close"] * stueckzahl_aktiv
    df_chart["Depotwert_Netto"] = df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]

    def zeige_chart_legende_liste(eintraege):
        """eintraege: Liste von (label, emoji) Tupeln. Fuer NICHT abwaehlbare
        Linien (Startkapital, eigenes Zertifikat) - einfacher Text mit
        Emoji-Symbol, garantiert einzeilig auf jeder Bildschirmbreite."""
        for label, emoji in eintraege:
            st.write(f"{emoji} {label}")

    def lese_pills_auswahl_still(labels, key):
        """Wie pills_auswahl(), aber OHNE das Widget zu rendern - liest nur
        den zuletzt gespeicherten Auswahlzustand (Standard: alle an). Fuer
        die Performance-Tabelle, die VOR dem sichtbaren Auswahl-Bereich
        steht, aber trotzdem die aktuelle Auswahl beruecksichtigen soll."""
        optionen = [f"{config.BENCHMARK_EMOJI.get(label, '⚪')} {label}" for label in labels]
        gespeichert = st.session_state.get(key, optionen)
        praefix_map = {opt: label for opt, label in zip(optionen, labels)}
        return [praefix_map[opt] for opt in gespeichert if opt in praefix_map]

    def pills_auswahl(labels, key):
        """Mehrfachauswahl per st.pills (anklickbare 'Pillen'-Buttons) statt
        Checkboxen - komplett anderes Widget ohne Checkbox-Innenleben, das
        sich per CSS nicht anpassen liess (moegliches Shadow-DOM). Emoji
        stecken direkt im Options-Text, keine separate Farbzuordnung noetig.
        Gibt die Liste der aktuell ausgewaehlten (reinen) Labels zurueck."""
        optionen = [f"{config.BENCHMARK_EMOJI.get(label, '⚪')} {label}" for label in labels]
        ausgewaehlt = st.pills(
            "Vergleichswerte im Chart anzeigen",
            optionen, selection_mode="multi", default=optionen, key=key,
        )
        ausgewaehlt = ausgewaehlt or []
        praefix_map = {opt: label for opt, label in zip(optionen, labels)}
        return [praefix_map[opt] for opt in ausgewaehlt]

    def berechne_performance_kennzahlen(erste_werte, letzter_wert, start_datum, end_datum):
        """Gesamt-%, Ø-monatliche % und Ø-jährliche % (beide CAGR-Stil,
        laufzeitbereinigt - fair vergleichbar auch bei unterschiedlich langen
        Zeiträumen) sowie Gewinn/Verlust in € für eine normierte Wertreihe
        (erster Wert = eingesetztes Kapital)."""
        gesamt_pct = (letzter_wert / erste_werte - 1) * 100
        tage = max(1, (end_datum - start_datum).days)
        monate = tage / 30.44
        monatliche_pct = (((letzter_wert / erste_werte) ** (1 / monate)) - 1) * 100 if monate > 0 else 0.0
        jaehrliche_pct = (((1 + monatliche_pct / 100) ** 12) - 1) * 100
        gewinn_verlust_euro = letzter_wert - erste_werte
        return gesamt_pct, monatliche_pct, jaehrliche_pct, gewinn_verlust_euro

    # --- REAL: Entnahme erfolgt tatsächlich durch monatlichen Verkauf von Anteilen
    # zum jeweils gültigen GELDKURS (Bid, nicht Mid) -> Stückzahl sinkt dauerhaft,
    # und der Spread schmälert die Rendite zusätzlich realistisch. ---
    def berechne_reale_stueckzahl(df, start_stueckzahl, entnahme_pm, start_dt, spread_pct):
        stueckzahl = start_stueckzahl
        verlauf = []
        letzter_monat = None
        for ts, row in df.iterrows():
            monat_key = (ts.year, ts.month)
            if letzter_monat is not None and monat_key != letzter_monat:
                mid_preis = row["Close"]
                geld_preis = mid_preis * (1 - spread_pct / 100.0)  # realer Verkaufskurs
                if geld_preis and geld_preis > 0:
                    verkaufte_stueck = entnahme_pm / geld_preis
                    stueckzahl = max(0.0, stueckzahl - verkaufte_stueck)
            letzter_monat = monat_key
            verlauf.append(stueckzahl)
        return verlauf

    df_chart["Stueckzahl_Real"] = berechne_reale_stueckzahl(
        df_chart, stueckzahl_aktiv, config.ENTNAHME_PM, start_dt, config.SPREAD_PCT
    )
    df_chart["Depotwert_Real"] = df_chart["Close"] * df_chart["Stueckzahl_Real"]

    # --- DISCORD ALERT (klassischer -1%-Alarm, Legacy-Button in Sidebar) ---
    def send_discord_alert(pct_change, current_price):
        if not DISCORD_WEBHOOK_URL:
            return False
        state = gh_read(config.STATE_PATH_ALARM, {})
        last_alert_time = None
        if state.get("last_alert"):
            try:
                last_alert_time = datetime.datetime.fromisoformat(state["last_alert"])
            except Exception:
                pass

        now = datetime.datetime.now(BERLIN_TZ)
        if last_alert_time and (now - last_alert_time).total_seconds() < 3600:
            return False

        msg = f"🚨 **QUANT TERMINAL ALARM** 🚨\nDas Wikifolio **{config.WKN}** ist gefallen!\nTagesveränderung: **{pct_change:+.2f}%**\nAktueller Kurs: **{current_price:.3f}€**"
        try:
            response = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            if response.status_code in (200, 204):
                gh_write(config.STATE_PATH_ALARM, {"last_alert": now.isoformat()}, message="update alarm state [skip ci]")
                return True
        except Exception as e:
            logging.error(f"Discord Alert Fehler: {e}")
        return False

    # --- AUTOMATISCHE RENDITE-BERECHNUNG ---
    tage_gehalten = max(1, (heute_date - config.KAUFDATUM).days)
    erwartete_rendite_pa = (((aktueller_kurs / config.ANFANGSKURS) ** (365.25 / tage_gehalten)) - 1) * 100
    erwarteter_zins_mo = (1 + (erwartete_rendite_pa / 100.0)) ** (1/12) - 1

    # --- SIDEBAR & STEUERUNG ---
    st.sidebar.markdown("### ⚡ System Status")
    if is_live_data:
        st.sidebar.success(f"🟢 Live-Daten aktiv\nKurs-Feed: {fetched_source}\nChart-Feed: {hist_source_name}")
    else:
        st.sidebar.error(f"🔴 KEINE LIVE-DATEN\nKurs-Feed: {fetched_source}\nChart-Feed: {hist_source_name}")
    st.sidebar.write(f"Webhook geladen: {'Ja' if DISCORD_WEBHOOK_URL else 'Nein'}")
    st.sidebar.write(f"Persistenter State (GitHub): {'Ja' if GH_STATE_READY else '⚠️ Nein - GITHUB_REPO/GITHUB_TOKEN fehlen'}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Live-Daten Monitor")
    st.sidebar.text(f"Aktueller Kurs: {aktueller_kurs:.3f} €")
    st.sidebar.text(f"Vortageskurs: {vortag_kurs:.3f} €")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 Automatische Prognose-Basis")
    st.sidebar.info(f"Ermittelte Performance (CAGR):\n**{erwartete_rendite_pa:.2f}% p.a.**\n\n(Dient als automatische Basis für die 100k-Simulation)")

    if st.sidebar.button("🔔 Test-Alarm senden"):
        if send_discord_alert(-1.50, aktueller_kurs):
            st.sidebar.success("Test-Alarm gesendet!")

    # --- WARNBANNER: KEIN PERSISTENTER STATE KONFIGURIERT ---
    if not GH_STATE_READY:
        st.warning(
            "⚠️ Kein persistenter State konfiguriert (GITHUB_REPO/GITHUB_TOKEN fehlen in den "
            "Streamlit-Secrets). Trader-Log, Alarm-Cooldowns etc. gehen bei jedem Neustart der "
            "App verloren, da Streamlit Cloud kein dauerhaftes Dateisystem hat."
        )

    # --- WARNBANNER BEI FEHLENDEN LIVE-DATEN ---
    if not is_live_data or not is_live_history:
        st.error(
            "⚠️ Achtung: Es werden gerade **keine echten Live-Daten** von ls-tc.de angezeigt "
            "(Kurs und/oder Chart-Historie sind Fallback-/Synthetikwerte). "
            "Prüfe die Server-Logs bzw. die JSON-Struktur des ls-tc.de-Endpunkts."
        )

    # --- DIAGNOSE IM HAUPTBEREICH (statt Sidebar - auf Mobile oft nicht auffindbar) ---
    with st.expander("🔧 System-Status / Diagnose", expanded=not GH_STATE_READY):
        st.write(f"**Live-Daten aktiv:** {'✅ Ja' if is_live_data else '❌ Nein'} ({fetched_source})")
        st.write(f"**Chart-Historie live:** {'✅ Ja' if is_live_history else '❌ Nein'} ({hist_source_name})")
        st.write(f"**Discord-Webhook geladen:** {'✅ Ja' if DISCORD_WEBHOOK_URL else '❌ Nein'}")
        st.write(f"**Persistenter State (GitHub):** {'✅ Ja' if GH_STATE_READY else '❌ Nein - GITHUB_REPO/GITHUB_TOKEN fehlen'}")
        if GH_STATE_READY:
            st.caption(f"Repo: {GITHUB_REPO} • Branch: {config.GITHUB_STATE_BRANCH}")
        st.write(f"**High Watermark:** {high_watermark_anzeige:.3f}€")

    # --- KENNZAHLEN ---
    tages_verenderung_pct = ((aktueller_kurs - vortag_kurs) / vortag_kurs) * 100 if vortag_kurs else 0.0
    letztes_update_zeit = now_berlin.strftime("%d.%m.%Y %H:%M:%S Uhr")


    def check_and_send_price_updates(pct_change, current_price):
        """
        Nur noch der Schwellen-Alarm bei Über-/Unterschreiten von
        config.TAGESVERLUST_SCHWELLE_PCT. Die routinemäßigen 5-Minuten-Updates
        übernimmt ausschließlich der externe GitHub-Actions-Cronjob.
        """
        if not DISCORD_WEBHOOK_URL:
            return
        if not config.ist_handelszeit(datetime.datetime.now(BERLIN_TZ)):
            return  # außerhalb der Handelszeiten keine (Fehl-)Alarme auf eingefrorene Kurse

        state = gh_read_cached(config.STATE_PATH_PRICE_ALERT, {"unter_schwelle": False})

        aktuell_unter_schwelle = pct_change <= config.TAGESVERLUST_SCHWELLE_PCT
        war_unter_schwelle = state.get("unter_schwelle", False)

        if aktuell_unter_schwelle and not war_unter_schwelle:
            msg = (f"🚨 **SCHWELLE UNTERSCHRITTEN ({config.WKN})** 🚨\n"
                   f"Tagesveränderung: **{pct_change:+.2f}%** "
                   f"(Schwelle: {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%)\n"
                   f"Aktueller Kurs: **{current_price:.3f}€**")
            try:
                requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            except Exception as e:
                logging.error(f"Discord Schwellen-Alarm Fehler: {e}")
            state["unter_schwelle"] = True

        elif not aktuell_unter_schwelle and war_unter_schwelle:
            msg = (f"✅ **Entwarnung ({config.WKN})**\n"
                   f"Tagesveränderung wieder über {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%: "
                   f"**{pct_change:+.2f}%**\n"
                   f"Aktueller Kurs: **{current_price:.3f}€**")
            try:
                requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            except Exception as e:
                logging.error(f"Discord Entwarnung Fehler: {e}")
            state["unter_schwelle"] = False

        gh_write(config.STATE_PATH_PRICE_ALERT, state, message="update price alert state [skip ci]")


    check_and_send_price_updates(tages_verenderung_pct, aktueller_kurs)

    heutige_monate_anzahl = max(0, (now_berlin.year - start_dt.year) * 12 + (now_berlin.month - start_dt.month))
    if now_berlin.day < start_dt.day:
        heutige_monate_anzahl -= 1

    gesamt_entnommen = entnommen_aktiv
    brutto_ist = (stueckzahl_aktiv + zusaetzliche_stueckzahl_sparplan) * aktueller_kurs
    netto_ist = brutto_ist - gesamt_entnommen
    gewinn_brutto = brutto_ist - startkapital_aktiv
    rendite_ist_pct = ((aktueller_kurs - config.ANFANGSKURS) / config.ANFANGSKURS) * 100

    # Reale Variante fuer die aktuellen Kennzahlen (Stückzahl nach echten Verkäufen)
    stueckzahl_real_ist = df_chart["Stueckzahl_Real"].iloc[-1] if not df_chart.empty else stueckzahl_aktiv
    depotwert_real_ist = (stueckzahl_real_ist + zusaetzliche_stueckzahl_sparplan) * aktueller_kurs

    kumulierte_sparrate_marktwert = zusaetzliche_stueckzahl_sparplan * aktueller_kurs

    sim_b = brutto_ist
    monate_bis_ziel = 0
    while sim_b < 100000.0 and monate_bis_ziel < 600:
        sim_b = (sim_b * (1 + erwarteter_zins_mo)) - entnommen_aktiv + sparrate_aktiv
        monate_bis_ziel += 1

    monate_namen = {1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni", 
                    7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember"}

    if brutto_ist >= 100000.0:
        meilenstein_datum_str, meilenstein_details_str = "Bereits erreicht", "Ziel erreicht"
    elif monate_bis_ziel < 600:
        ms_date = (now_berlin.replace(tzinfo=None) + pd.DateOffset(months=monate_bis_ziel)).date()
        meilenstein_datum_str = f"{monate_namen[ms_date.month]} {ms_date.year}"
        meilenstein_details_str = f"In ca. {monate_bis_ziel // 12} Jahren & {monate_bis_ziel % 12} Monaten"
    else:
        meilenstein_datum_str, meilenstein_details_str = "> 50 Jahre", "Unrealistisch"

    richtung = "up" if tages_verenderung_pct >= 0 else "down"
    differenz_zum_vortag = aktueller_kurs - vortag_kurs

    # ---------- KURS-KOPF: der Kurs ist die eine Zahl, die zaehlt ----------
    live_markup = (
        '<span class="live-pill"><span class="live-dot"></span>Live</span>'
        if is_live_data else
        '<span class="live-pill offline"><span class="live-dot offline"></span>Keine Live-Daten</span>'
    )

    def de_zahl(wert, nachkomma=3):
        """Deutsche Schreibweise (Punkt = Tausender, Komma = Dezimal) - bewusst
        nur auf den ZAHLENWERT angewendet, nicht auf das umgebende HTML."""
        s = f"{wert:,.{nachkomma}f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    # ---------- PERFORMANCE JE ZEITRAUM (Tag/Woche/Monat/Jahr/seit Kauf) ----------
    # Referenzkurse fuer Woche/Monat/Jahr kommen von der oeffentlichen
    # wikifolio-Seite (get_performance_referenzwerte), "Tag" nutzt den bereits
    # vorhandenen Vortageskurs, "seit Kauf" nutzt die bereits berechneten
    # gewinn_brutto/rendite_ist_pct - dieselben Zahlen wie im Gewinn/Rendite-Chip,
    # keine zweite, potenziell abweichende Berechnung.
    #
    # WICHTIG - Einschraenkung: die €-Betraege je Zeitraum unterstellen eine ueber
    # den jeweiligen Zeitraum konstante Stueckzahl (aktuelle Stueckzahl rueckwirkend
    # angewendet). Bei zwischenzeitlichen Sparplan-Kaeufen ist das eine Naeherung.
    referenzwerte = get_performance_referenzwerte()
    gesamt_stueckzahl_perf = stueckzahl_aktiv + zusaetzliche_stueckzahl_sparplan

    periods_kurs = []
    if vortag_kurs:
        _d = aktueller_kurs - vortag_kurs
        periods_kurs.append(("Tag", _d, _d / vortag_kurs * 100))
    for _label, _key in [("Woche", "Woche"), ("Monat", "Monat"), ("Jahr", "Jahr")]:
        _ref = referenzwerte.get(_key)
        if _ref:
            _d = aktueller_kurs - _ref
            periods_kurs.append((_label, _d, _d / _ref * 100))

    periods_depot = [(lbl, d * gesamt_stueckzahl_perf, p) for lbl, d, p in periods_kurs]
    periods_depot.append(("seit Kauf", gewinn_brutto, rendite_ist_pct))

    def perf_zeilen_html(zeilen, nachkomma, kopfzeile=None):
        """Rendert die Zeitraum-Zeilen INNERHALB einer Kachel: hairline-getrennt,
        Betrag und Prozent rechtsbuendig nebeneinander, eingefaerbt nach Vorzeichen.
        kopfzeile: optionales (label, wert_html) Tupel fuer eine neutrale
        Referenzzeile ohne +/- Faerbung (z.B. der Vortageskurs) ganz oben."""
        html = ""
        if kopfzeile:
            k_label, k_wert = kopfzeile
            html += (
                f'<div class="perf-row"><span class="perf-label">{k_label}</span>'
                f'<span class="perf-vals"><span class="neutral">{k_wert}</span></span></div>'
            )
        for label, diff, prozent in zeilen:
            cls = "up" if diff >= 0 else "down"
            html += (
                f'<div class="perf-row"><span class="perf-label">{label}</span>'
                f'<span class="perf-vals">'
                f'<span class="{cls}">{"+" if diff >= 0 else ""}{de_zahl(diff, nachkomma)} €</span>'
                f'<span class="{cls}">{"+" if prozent >= 0 else ""}{de_zahl(prozent, 2)} %</span>'
                f'</span></div>'
            )
        return f'<div class="perf-table">{html}</div>' if html else ""

    st.markdown(f"""
    <div class="quote">
        <div class="q-name">Hauptindizes Global · {config.WKN}</div>
        <div class="price-line">
            <span class="q-price">{de_zahl(aktueller_kurs)} €</span>
            {live_markup}
            <span class="meta-chip">Lang &amp; Schwarz</span>
        </div>
        {perf_zeilen_html(periods_kurs, 3, kopfzeile=("Vortag", f"{de_zahl(vortag_kurs)} €"))}
        <div class="card-footnote">Stand: {letztes_update_zeit}</div>
    </div>
    """, unsafe_allow_html=True)

    # ---------- HERO: Depotwert ----------
    sparplan_zusatz = (
        f" · davon {zusaetzliche_stueckzahl_sparplan:.4f} aus Sparplan"
        if zusaetzliche_stueckzahl_sparplan > 0 else ""
    )
    richtung_gewinn = "up" if gewinn_brutto >= 0 else "down"
    st.markdown(f"""
    <div class="hero">
        <div class="hero-label">Depotwert</div>
        <div class="price-line">
            <span class="hero-val">{fmt(brutto_ist, 2)}</span>
            <span class="stat-chip"><span class="stat-chip-label">Ø p.a.</span><span class="stat-chip-val">{erwartete_rendite_pa:.1f} %</span></span>
        </div>
        {perf_zeilen_html(periods_depot, 2)}
        <div class="card-footnote">{stueckzahl_aktiv + zusaetzliche_stueckzahl_sparplan:.4f} Anteile{sparplan_zusatz}</div>
    </div>
    """, unsafe_allow_html=True)

    # ---------- Eingaben ----------
    # Wichtig: "value=" nur beim allerersten Erstellen des Widgets mitgeben,
    # NICHT bei jedem Rerun (klassischer Streamlit-Stolperstein).
    with st.expander("Anfangskapital, Entnahme und Sparrate anpassen", expanded=False):
        col_ak, col_ek = st.columns(2)
        with col_ak:
            ak_kwargs = dict(
                min_value=0.0, step=100.0, key="haupt_startkapital_input",
                help=f"Kauf ({config.KAUFDATUM.strftime('%d.%m.%Y')}): {config.ANFANGSKURS:.2f}€ - Stückzahl wird automatisch neu berechnet.",
            )
            if "haupt_startkapital_input" not in st.session_state:
                ak_kwargs["value"] = startkapital_aktiv
            st.number_input("Anfangskapital (€)", **ak_kwargs)
        with col_ek:
            ek_kwargs = dict(
                min_value=0.0, step=10.0, key="haupt_entnommen_input",
                help="Standard: 0€ - hier frei einstellbar, ganz wie du es tatsächlich entnommen hast.",
            )
            if "haupt_entnommen_input" not in st.session_state:
                ek_kwargs["value"] = entnommen_aktiv
            st.number_input("Monatliche Entnahme (€)", **ek_kwargs)

        sparrate_kwargs = dict(
            min_value=0.0, step=10.0, key="haupt_sparrate_input",
            help="Zusätzliche monatliche Einzahlung (Sparplan) - kauft laufend Anteile dazu und "
                 "fließt in die Zukunfts-Hochrechnungen ein. Ändert die bisherige Chart-Historie nicht.",
        )
        if "haupt_sparrate_input" not in st.session_state:
            sparrate_kwargs["value"] = 0.0
        st.number_input("Monatliche Sparrate (€)", **sparrate_kwargs)

    # ---------- DATENZEILEN: Sekundaerwerte kompakt und scanbar ----------
    st.markdown(f"""
    <div class="rows">
        <div class="row">
            <span class="row-label">100k-Meilenstein</span>
            <span class="row-val">{meilenstein_datum_str}
                <span class="row-note">{meilenstein_details_str}</span>
            </span>
        </div>
        <div class="row">
            <span class="row-label">High Watermark</span>
            <span class="row-val">{de_zahl(high_watermark_anzeige)} €
                <span class="row-note">Erreicht am {high_watermark_datum} · ab hier {config.PERFORMANCE_FEE_PCT:.0f} % Performance Fee</span>
            </span>
        </div>
        <div class="row">
            <span class="row-label">Anfangskapital</span>
            <span class="row-val">{fmt(startkapital_aktiv, 2)}
                <span class="row-note">Kauf am {config.KAUFDATUM.strftime('%d.%m.%Y')} zu {de_zahl(config.ANFANGSKURS, 2)} €</span>
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- NETTO-WERTE + Kosten: nur bei Bedarf einblenden ---
    sparrate_note = (
        f" · inkl. {zusaetzliche_stueckzahl_sparplan:.4f} Sparplan-Anteile ({fmt(kumulierte_sparrate_marktwert, 2)})"
        if zusaetzliche_stueckzahl_sparplan > 0 else ""
    )
    with st.expander("Netto-Werte und laufende Kosten", expanded=False):
        st.markdown(f"""
        <div class="rows">
            <div class="row">
                <span class="row-label">Netto (Simulation)</span>
                <span class="row-val">{fmt(netto_ist, 2)}
                    <span class="row-note">Entnahme nur buchhalterisch abgezogen{sparrate_note}</span>
                </span>
            </div>
            <div class="row">
                <span class="row-label">Netto (real verkauft)</span>
                <span class="row-val">{fmt(depotwert_real_ist, 2)}
                    <span class="row-note">{stueckzahl_real_ist:.4f} Anteile nach realer Entnahme, inkl. {config.SPREAD_PCT:.2f} % Spread</span>
                </span>
            </div>
            <div class="row">
                <span class="row-label">Laufende Kosten</span>
                <span class="row-val">{config.ZERTIFIKAT_GEBUEHR_PA_PCT:.2f} % p.a.
                    <span class="row-note">Zertifikatsgebühr, bereits im Kurs eingepreist</span>
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # TABS
    tab_wealth, tab_ytd, tab_2021, tab_candle, tab_forecast, tab_scenarios, tab_trades = st.tabs([
        "📈 VERMÖGENS- & SUBSTANZAUFBAU",
        "🔍 SEIT 01.01.2026",
        "🔎 SEIT 01.01.2021",
        "🕯️ TAGES-CANDLESTICK",
        "🔮 ZUKUNFTS-PROGNOSE",
        "📊 SZENARIO-SIMULATOR (5 JAHRE)",
        "📝 TRADER-LOG (TRADES & KOMMENTARE)",
    ])

    @st.fragment
    def _render_wealth():
        try:
            with tab_wealth:
                # Auswahl still aus dem gespeicherten Zustand lesen (Standard: alle an) -
                # der sichtbare Auswahl-Bereich selbst steht weiter unten, direkt vor dem Chart.
                ausgewaehlte_benchmarks = lese_pills_auswahl_still(benchmark_series.keys(), key="benchmark_pills")

                performance_liste_haupt = []
                brutto_reihe = df_chart["Depotwert_Brutto"]
                if not brutto_reihe.empty and brutto_reihe.iloc[0] > 0:
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        brutto_reihe.iloc[0], brutto_reihe.iloc[-1], config.KAUFDATUM, heute_date
                    )
                    performance_liste_haupt.append({
                        "Wert": f"Hauptindizes Global ({config.WKN})",
                        "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_gelistet_seit": config.KAUFDATUM,
                    })
                for label, s in benchmark_series.items():
                    s_gueltig = s.dropna()
                    if label in ausgewaehlte_benchmarks and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                        start_dieser_wert = benchmark_start_daten.get(label)
                        start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else config.KAUFDATUM
                        gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                            s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                        )
                        performance_liste_haupt.append({
                            "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                            "_gelistet_seit": start_dieser_wert,
                        })

                if performance_liste_haupt:
                    st.caption(f"📅 Berechnet seit {config.KAUFDATUM.strftime('%d.%m.%Y')} (Kaufdatum)")
                    performance_liste_haupt.sort(key=lambda x: x["_jaehrlich"], reverse=True)
                    zeilen_html_haupt = ""
                    for eintrag in performance_liste_haupt:
                        farbe = "#00C853" if eintrag["_perf"] >= 0 else "#FF3D00"
                        zeilen_html_haupt += f"""
                        <tr style="border-bottom: 1px solid #1A1A1A;">
                            <td style="padding: 8px 6px; color: #E5E7EB; font-size: 0.85rem;">{eintrag['Wert']}</td>
                            <td style="padding: 8px 6px; color: {farbe}; font-weight: 700; text-align: right; white-space: nowrap; font-size: 0.85rem;">{eintrag['_perf']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; text-align: right; white-space: nowrap; font-size: 0.8rem;">{eintrag['_monatlich']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; font-weight: 700; text-align: right; white-space: nowrap; font-size: 0.85rem;">{eintrag['_jaehrlich']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; text-align: right; white-space: nowrap; font-size: 0.8rem;">{fmt(eintrag['_euro'], 0)}</td>
                            <td style="padding: 8px 6px; color: #71717A; text-align: right; white-space: nowrap; font-size: 0.75rem;">{eintrag['_gelistet_seit'].strftime('%d.%m.%Y') if eintrag.get('_gelistet_seit') else '-'}</td>
                        </tr>"""
                    st.markdown(f"""
                    <table style="width: 100%; border-collapse: collapse; background: #09090B; border: 1px solid #27272A; border-radius: 6px; overflow: hidden; margin-bottom: 12px;">
                        <thead>
                            <tr style="border-bottom: 1px solid #27272A;">
                                <th style="padding: 8px 6px; text-align: left; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Wert</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Gesamt</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Ø/Monat</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Ø/Jahr (p.a.)</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">+/- €</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Gelistet seit</th>
                            </tr>
                        </thead>
                        <tbody>{zeilen_html_haupt}
                        </tbody>
                    </table>
                    """, unsafe_allow_html=True)

                with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                    st.caption(
                        "„Netto (Simulation)“ zieht die Entnahme nur buchhalterisch vom Depotwert ab. "
                        f"„Real“ verkauft monatlich tatsächlich Anteile zum dann gültigen Geldkurs "
                        f"(inkl. {config.SPREAD_PCT:.2f}% Spread-Annahme) — realistischer, falls du die "
                        "70€/Monat wirklich entnimmst. Die gestrichelten Vergleichslinien zeigen, wie sich "
                        f"{fmt(startkapital_aktiv, 0)} im selben Zeitraum in gängigen Vergleichs-ETFs "
                        "entwickelt hätten (Kosten der ETFs bereits im Kurs enthalten, keine Steuern)."
                    )
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"Hauptindizes Global ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series.keys(), key="benchmark_pills")

                fig_wealth = go.Figure()
                fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Startkapital"], name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash")))
                fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Brutto"], name="Brutto-Depotwert", line=dict(color="#00C853", width=2.5)))

                legende_eintraege = [("Startkapital", "#71717A"), (f"Hauptindizes Global ({config.WKN})", "#00C853")]
                for label, s in benchmark_series.items():
                    if label not in ausgewaehlte_benchmarks:
                        continue
                    farbe = config.BENCHMARK_COLORS.get(label, "#9E9E9E")
                    fig_wealth.add_trace(go.Scatter(
                        x=df_chart.index, y=s, name=label,
                        line=dict(color=farbe, width=1.5, dash="dashdot"),
                    ))
                    legende_eintraege.append((label, farbe))
    
                fig_wealth.update_layout(
                    paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=80, b=40), height=450,
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=2000),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_wealth, width="stretch", key="chart_wealth")

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Vermoegensaufbau", e)
    _render_wealth()

    @st.fragment
    def _render_ytd():
        try:
            with tab_ytd:
                v2_start = pd.Timestamp(config.VERGLEICH2_START_DATUM)
                v2_kapital = config.VERGLEICH2_STARTKAPITAL

                # Eigenes Zertifikat: aus bereits geladenem df_chart ab v2_start neu skalieren
                eigene_reihe_v2 = df_chart["Close"][df_chart.index >= v2_start]
                if not eigene_reihe_v2.empty and eigene_reihe_v2.iloc[0] > 0:
                    eigene_reihe_v2 = eigene_reihe_v2 / eigene_reihe_v2.iloc[0] * v2_kapital

                # Benchmarks: eigener, frischer Abruf ab v2_start (eigene Cache-Zeile,
                # da anderer Startzeitpunkt als der Hauptvergleich oben)
                benchmark_series_v2, benchmark_start_daten_v2 = lade_benchmarks_mit_fortschritt(
                    eigene_reihe_v2.index, config.VERGLEICH2_START_DATUM, v2_kapital
                )

                # Auswahl still aus dem gespeicherten Zustand lesen - der sichtbare
                # Auswahl-Bereich steht weiter unten, direkt vor dem Chart.
                ausgewaehlte_v2 = lese_pills_auswahl_still(benchmark_series_v2.keys(), key="benchmark_v2_pills")

                fig_v2 = go.Figure()
                fig_v2.add_trace(go.Scatter(
                    x=eigene_reihe_v2.index, y=[v2_kapital] * len(eigene_reihe_v2),
                    name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash"),
                ))
                fig_v2.add_trace(go.Scatter(
                    x=eigene_reihe_v2.index, y=eigene_reihe_v2, name=f"Hauptindizes Global ({config.WKN})",
                    line=dict(color="#00C853", width=2.5),
                ))
                benchmark_colors_v2 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
                legende_eintraege_v2 = [("Startkapital", "#71717A"), (f"Hauptindizes Global ({config.WKN})", "#00C853")]
                for i, (label, s) in enumerate(benchmark_series_v2.items()):
                    if label not in ausgewaehlte_v2:
                        continue
                    farbe_v2 = config.BENCHMARK_COLORS.get(label, "#9E9E9E")
                    fig_v2.add_trace(go.Scatter(
                        x=eigene_reihe_v2.index, y=s, name=label,
                        line=dict(color=farbe_v2, width=1.5, dash="dashdot"),
                    ))
                    legende_eintraege_v2.append((label, farbe_v2))

                fig_v2.update_layout(
                    paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=40, b=40), height=450,
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=1000),
                    hovermode="x unified",
                )
                performance_liste_v2 = []
                if not eigene_reihe_v2.empty and eigene_reihe_v2.iloc[0] > 0:
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        eigene_reihe_v2.iloc[0], eigene_reihe_v2.iloc[-1], config.VERGLEICH2_START_DATUM, heute_date
                    )
                    performance_liste_v2.append({
                        "Wert": f"Hauptindizes Global ({config.WKN})",
                        "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_gelistet_seit": config.VERGLEICH2_START_DATUM,
                    })
                for label, s in benchmark_series_v2.items():
                    s_gueltig = s.dropna()
                    if label in ausgewaehlte_v2 and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                        start_dieser_wert = benchmark_start_daten_v2.get(label)
                        start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else config.VERGLEICH2_START_DATUM
                        gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                            s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                        )
                        performance_liste_v2.append({
                            "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                            "_gelistet_seit": start_dieser_wert,
                        })

                if performance_liste_v2:
                    st.caption(f"📅 Berechnet seit {config.VERGLEICH2_START_DATUM.strftime('%d.%m.%Y')}")
                    performance_liste_v2.sort(key=lambda x: x["_jaehrlich"], reverse=True)
                    zeilen_html = ""
                    for eintrag in performance_liste_v2:
                        farbe = "#00C853" if eintrag["_perf"] >= 0 else "#FF3D00"
                        zeilen_html += f"""
                        <tr style="border-bottom: 1px solid #1A1A1A;">
                            <td style="padding: 8px 6px; color: #E5E7EB; font-size: 0.85rem;">{eintrag['Wert']}</td>
                            <td style="padding: 8px 6px; color: {farbe}; font-weight: 700; text-align: right; white-space: nowrap; font-size: 0.85rem;">{eintrag['_perf']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; text-align: right; white-space: nowrap; font-size: 0.8rem;">{eintrag['_monatlich']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; font-weight: 700; text-align: right; white-space: nowrap; font-size: 0.85rem;">{eintrag['_jaehrlich']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; text-align: right; white-space: nowrap; font-size: 0.8rem;">{fmt(eintrag['_euro'], 0)}</td>
                            <td style="padding: 8px 6px; color: #71717A; text-align: right; white-space: nowrap; font-size: 0.75rem;">{eintrag['_gelistet_seit'].strftime('%d.%m.%Y') if eintrag.get('_gelistet_seit') else '-'}</td>
                        </tr>"""
                    st.markdown(f"""
                    <table style="width: 100%; border-collapse: collapse; background: #09090B; border: 1px solid #27272A; border-radius: 6px; overflow: hidden;">
                        <thead>
                            <tr style="border-bottom: 1px solid #27272A;">
                                <th style="padding: 8px 6px; text-align: left; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Wert</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Gesamt</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Ø/Monat</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Ø/Jahr (p.a.)</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">+/- €</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Gelistet seit</th>
                            </tr>
                        </thead>
                        <tbody>{zeilen_html}
                        </tbody>
                    </table>
                    """, unsafe_allow_html=True)

                with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                    st.caption(
                        f"Alle Werte neu skaliert: {fmt(v2_kapital, 0)} investiert am "
                        f"{config.VERGLEICH2_START_DATUM.strftime('%d.%m.%Y')}, unabhängig vom "
                        "eigentlichen Kaufdatum deines Zertifikats - zeigt die reine "
                        "Performance seit Jahresanfang im direkten Vergleich."
                    )
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"Hauptindizes Global ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series_v2.keys(), key="benchmark_v2_pills")

                st.plotly_chart(fig_v2, width="stretch", key="chart_ytd")

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Seit-2026", e)
    _render_ytd()

    @st.fragment
    def _render_2021():
        try:
            with tab_2021:
                v3_start = pd.Timestamp(config.VERGLEICH3_START_DATUM)
                v3_kapital = config.VERGLEICH3_STARTKAPITAL
                master_index_v3 = pd.bdate_range(start=v3_start, end=pd.Timestamp(heute_date))

                # Eigenes Zertifikat: EIGENER, frischer Abruf ab 2021 (df_chart
                # reicht nur bis zum echten Kaufdatum zurueck, hier brauchen wir
                # ggf. deutlich mehr Historie). Wichtig: die Benchmarks werden
                # NICHT auf den (ggf. kuerzeren) Zeitraum des Zertifikats
                # zugeschnitten - sie laufen ueber den vollen 2021-Zeitraum,
                # nur die Zertifikat-Linie beginnt ggf. spaeter (echte Luecke).
                df_chart_v3, _ = get_historical_market_data(config.VERGLEICH3_START_DATUM, heute_date, aktueller_kurs)
                roh_eigen_v3 = df_chart_v3["Close"] if not df_chart_v3.empty else pd.Series(dtype=float)

                tatsaechlicher_start_v3 = roh_eigen_v3.index.min() if not roh_eigen_v3.empty else None

                if not roh_eigen_v3.empty and roh_eigen_v3.iloc[0] > 0:
                    skaliert_eigen_v3 = roh_eigen_v3 / roh_eigen_v3.iloc[0] * v3_kapital
                    # Auf vollen Zeitindex bringen, aber NUR nach vorne auffuellen -
                    # vor dem echten Start bleibt es NaN (keine erfundene Rueckrechnung)
                    eigene_reihe_v3 = skaliert_eigen_v3.reindex(master_index_v3).ffill()
                else:
                    eigene_reihe_v3 = pd.Series(index=master_index_v3, dtype=float)

                benchmark_series_v3, benchmark_start_daten_v3 = lade_benchmarks_mit_fortschritt(
                    master_index_v3, config.VERGLEICH3_START_DATUM, v3_kapital
                )

                # Auswahl still aus dem gespeicherten Zustand lesen - der sichtbare
                # Auswahl-Bereich steht weiter unten, direkt vor dem Chart.
                ausgewaehlte_v3 = lese_pills_auswahl_still(benchmark_series_v3.keys(), key="benchmark_v3_pills")

                fig_v3 = go.Figure()
                fig_v3.add_trace(go.Scatter(
                    x=master_index_v3, y=[v3_kapital] * len(master_index_v3),
                    name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash"),
                ))
                fig_v3.add_trace(go.Scatter(
                    x=eigene_reihe_v3.index, y=eigene_reihe_v3, name=f"Hauptindizes Global ({config.WKN})",
                    line=dict(color="#00C853", width=2.5),
                ))
                benchmark_colors_v3 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
                legende_eintraege_v3 = [("Startkapital", "#71717A"), (f"Hauptindizes Global ({config.WKN})", "#00C853")]
                for i, (label, s) in enumerate(benchmark_series_v3.items()):
                    if label not in ausgewaehlte_v3:
                        continue
                    farbe_v3 = config.BENCHMARK_COLORS.get(label, "#9E9E9E")
                    fig_v3.add_trace(go.Scatter(
                        x=master_index_v3, y=s, name=label,
                        line=dict(color=farbe_v3, width=1.5, dash="dashdot"),
                    ))
                    legende_eintraege_v3.append((label, farbe_v3))

                fig_v3.update_layout(
                    paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=40, b=40), height=450,
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=2000),
                    hovermode="x unified",
                )
                performance_liste_v3 = []
                if not roh_eigen_v3.empty and roh_eigen_v3.iloc[0] > 0:
                    start_datum_eigen_v3 = tatsaechlicher_start_v3.date() if tatsaechlicher_start_v3 is not None else config.VERGLEICH3_START_DATUM
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        roh_eigen_v3.iloc[0], roh_eigen_v3.iloc[-1], start_datum_eigen_v3, heute_date
                    )
                    performance_liste_v3.append({
                        "Wert": f"Hauptindizes Global ({config.WKN})",
                        "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_gelistet_seit": start_datum_eigen_v3,
                    })
                for label, s in benchmark_series_v3.items():
                    s_gueltig = s.dropna()
                    if label in ausgewaehlte_v3 and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                        start_dieser_wert = benchmark_start_daten_v3.get(label)
                        start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else config.VERGLEICH3_START_DATUM
                        gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                            s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                        )
                        performance_liste_v3.append({
                            "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                            "_gelistet_seit": start_dieser_wert,
                        })

                if performance_liste_v3:
                    st.caption(f"📅 Berechnet seit {config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')} (bzw. erstem verfügbaren Kurs)")
                    performance_liste_v3.sort(key=lambda x: x["_jaehrlich"], reverse=True)
                    zeilen_html_v3 = ""
                    for eintrag in performance_liste_v3:
                        farbe = "#00C853" if eintrag["_perf"] >= 0 else "#FF3D00"
                        zeilen_html_v3 += f"""
                        <tr style="border-bottom: 1px solid #1A1A1A;">
                            <td style="padding: 8px 6px; color: #E5E7EB; font-size: 0.85rem;">{eintrag['Wert']}</td>
                            <td style="padding: 8px 6px; color: {farbe}; font-weight: 700; text-align: right; white-space: nowrap; font-size: 0.85rem;">{eintrag['_perf']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; text-align: right; white-space: nowrap; font-size: 0.8rem;">{eintrag['_monatlich']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; font-weight: 700; text-align: right; white-space: nowrap; font-size: 0.85rem;">{eintrag['_jaehrlich']:+.2f}%</td>
                            <td style="padding: 8px 6px; color: {farbe}; text-align: right; white-space: nowrap; font-size: 0.8rem;">{fmt(eintrag['_euro'], 0)}</td>
                            <td style="padding: 8px 6px; color: #71717A; text-align: right; white-space: nowrap; font-size: 0.75rem;">{eintrag['_gelistet_seit'].strftime('%d.%m.%Y') if eintrag.get('_gelistet_seit') else '-'}</td>
                        </tr>"""
                    st.markdown(f"""
                    <table style="width: 100%; border-collapse: collapse; background: #09090B; border: 1px solid #27272A; border-radius: 6px; overflow: hidden;">
                        <thead>
                            <tr style="border-bottom: 1px solid #27272A;">
                                <th style="padding: 8px 6px; text-align: left; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Wert</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Gesamt</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Ø/Monat</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Ø/Jahr (p.a.)</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">+/- €</th>
                                <th style="padding: 8px 6px; text-align: right; color: #A1A1AA; font-size: 0.7rem; text-transform: uppercase;">Gelistet seit</th>
                            </tr>
                        </thead>
                        <tbody>{zeilen_html_v3}
                        </tbody>
                    </table>
                    """, unsafe_allow_html=True)

                with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                    st.caption(
                        f"Alle Werte neu skaliert: {fmt(v3_kapital, 0)} investiert am "
                        f"{config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')}, unabhängig vom "
                        "eigentlichen Kaufdatum deines Zertifikats."
                    )
                    if tatsaechlicher_start_v3 is not None and tatsaechlicher_start_v3 > v3_start:
                        st.info(
                            f"ℹ️ Für {config.WKN} liegen erst ab {tatsaechlicher_start_v3.strftime('%d.%m.%Y')} "
                            "Kursdaten vor (vermutlich Auflegungsdatum des Zertifikats) - die Linie beginnt "
                            "entsprechend später als die Vergleichswerte, keine erfundenen Daten. Die "
                            "Vergleichswerte selbst laufen trotzdem über den vollen Zeitraum seit "
                            f"{config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')}."
                        )
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"Hauptindizes Global ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series_v3.keys(), key="benchmark_v3_pills")

                st.plotly_chart(fig_v3, width="stretch", key="chart_2021")

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Seit-2021", e)
    _render_2021()

    @st.fragment
    def _render_trades():
        try:
            def load_db():
                return gh_read(config.STATE_PATH_TRADES_DB, [])

            def save_db(data):
                gh_write(config.STATE_PATH_TRADES_DB, data, message="update trades log [skip ci]")

            db_events = load_db()

            with tab_trades:
                st.markdown("### 📋 Historie")
                if not db_events:
                    st.info("Keine Einträge vorhanden.")
                else:
                    for ev in db_events:
                        st.markdown(f"""
                            <div style="background: #09090B; border: 1px solid #27272A; border-left: 3px solid #29B6F6; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                                <div style="font-size: 0.75rem; color: #71717A;"><b>[{ev.get('typ','')}]</b> - {ev.get('datum','')}</div>
                                <div style="font-weight: 700; color: #FFFFFF; font-size: 0.95rem;">{ev.get('titel','')}</div>
                                <div style="font-size: 0.85rem; color: #D1D5DB;">{ev.get('inhalt','')}</div>
                            </div>
                        """, unsafe_allow_html=True)

                with st.form("trade_form", clear_on_submit=True):
                    col1, col2, col3 = st.columns([2, 2, 3])
                    with col1: et = st.selectbox("Typ", ["Trade", "Kommentar", "Hinweis"])
                    with col2: ed = st.date_input("Datum", heute_date)
                    with col3: eti = st.text_input("Titel")
                    ei = st.text_area("Details")
                    if st.form_submit_button("Speichern") and eti:
                        db_events.insert(0, {"id": len(db_events) + 1, "typ": et, "datum": ed.strftime("%Y-%m-%d"), "titel": eti, "inhalt": ei})
                        save_db(db_events)
                        st.rerun(scope="fragment")

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Trader-Log", e)
    _render_trades()

    @st.fragment
    def _render_candle():
        try:
            with tab_candle:
                fig_c = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart["Open"], high=df_chart["High"], low=df_chart["Low"], close=df_chart["Close"], increasing_line_color="#00C853", decreasing_line_color="#FF3D00")])
                fig_c.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40), height=450, xaxis=dict(showgrid=True, gridcolor="#1A1A1A"), yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", dtick=10), showlegend=False)
                st.plotly_chart(fig_c, width="stretch", key="chart_candlestick")
                st.caption(
                    "Basiert auf ls-tc.de Tages-Schlusskursen (Open/High/Low approximiert). "
                    "Der GitHub-Actions-Cron protokolliert seit Kurzem zusätzlich alle 5 Min den "
                    "echten Kurs in state/price_history/ — daraus lässt sich künftig ein echter "
                    "Intraday-Chart bauen, sobald genug Historie gesammelt ist."
                )

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Candlestick", e)
    _render_candle()

    @st.fragment
    def _render_forecast():
        try:
            with tab_forecast:
                sparrate_hinweis = f" Zusätzlich wird eine monatliche Sparrate von **{fmt(sparrate_aktiv, 2)}** eingerechnet." if sparrate_aktiv > 0 else ""
                st.info(f"Zukunfts-Prognose rechnet vollautomatisch auf Basis der bisherigen historischen Performance von **{erwartete_rendite_pa:.2f}% p.a.** weiter.{sparrate_hinweis}")
    
                forecast_data = [
                    {"Index": 0, "Jahr": "Start", "Datum": config.KAUFDATUM.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(startkapital_aktiv, 2), "Gesamter Gewinn": "+0,00€", "Netto Depotwert": fmt(startkapital_aktiv, 2), "Kumulierte Entnahme": "0,00€"},
                    {"Index": 1, "Jahr": "Heute", "Datum": heute_date.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(brutto_ist, 2), "Gesamter Gewinn": f"+{fmt(gewinn_brutto, 2)}", "Netto Depotwert": fmt(netto_ist, 2), "Kumulierte Entnahme": fmt(gesamt_entnommen, 2)}
                ]
    
                sim_b_prog, sim_n_prog, sim_e_prog = brutto_ist, netto_ist, gesamt_entnommen
                milestone_added = brutto_ist >= 100000.0

                for m_idx in range(1, 121):
                    sim_b_prog = (sim_b_prog * (1 + erwarteter_zins_mo)) + sparrate_aktiv
                    sim_e_prog += entnommen_aktiv
                    sim_n_prog = sim_b_prog - sim_e_prog
        
                    current_date = now_berlin.replace(tzinfo=None) + pd.DateOffset(months=m_idx)
        
                    if not milestone_added and sim_b_prog >= 100000.0:
                        forecast_data.append({
                            "Index": "🎯", "Jahr": "100k Meilenstein",
                            "Datum": current_date.strftime("%d.%m.%Y"),
                            "Brutto Depotwert": fmt(sim_b_prog, 2), "Gesamter Gewinn": f"+{fmt(sim_b_prog - startkapital_aktiv, 2)}",
                            "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                        })
                        milestone_added = True

                    if m_idx % 12 == 0:
                        forecast_data.append({
                            "Index": m_idx // 12 + 1, "Jahr": f"Jahr +{m_idx // 12}",
                            "Datum": current_date.strftime("%d.%m.%Y"),
                            "Brutto Depotwert": fmt(sim_b_prog, 2), "Gesamter Gewinn": f"+{fmt(sim_b_prog - startkapital_aktiv, 2)}",
                            "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                        })
            
                df_forecast = pd.DataFrame(forecast_data)
                df_forecast["Index"] = df_forecast["Index"].astype(str)
                st.dataframe(df_forecast, width="stretch", hide_index=True, key="df_forecast")

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Prognose", e)
    _render_forecast()

    @st.fragment
    def _render_scenarios():
        try:
            with tab_scenarios:
                st.markdown(
                    '<div style="font-size: 1.05rem; font-weight: 800; color: #FFFFFF; margin-bottom: 4px;">'
                    '📊 Szenario-Analyse (1,0% – 10,0% p.M.)</div>',
                    unsafe_allow_html=True,
                )
                st.caption("✏️ Beide Werte unten frei anpassbar, um eigene Annahmen durchzurechnen:")

                col_sk, col_en = st.columns(2)
                with col_sk:
                    startkapital_szenario = st.number_input(
                        "✏️ Startkapital (€)", min_value=0.0, value=10000.0,
                        step=100.0, key="szenario_startkapital",
                    )
                with col_en:
                    entnahme_eingabe = st.number_input(
                        "✏️ Monatliche Entnahme (€)", min_value=0.0, value=0.0,
                        step=10.0, key="szenario_entnahme",
                    )
                sparrate_szenario = st.number_input(
                    "✏️ Monatliche Sparrate (€)", min_value=0.0, value=0.0,
                    step=10.0, key="szenario_sparrate",
                    help="Zusätzliche monatliche Einzahlung - erhöht das Kapital jeden Monat, statt es zu verringern.",
                )

                ohne_entnahme = st.toggle("Ohne monatliche Entnahme berechnen", value=False, key="szenario_ohne_entnahme")
                entnahme_fuer_szenario = 0.0 if ohne_entnahme else entnahme_eingabe
                netto_cashflow_szenario = sparrate_szenario - entnahme_fuer_szenario

                szenario_raten_mo = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]
    
                summary_list = []
                scenario_series = {}

                for r_mo_pct in szenario_raten_mo:
                    r_mo = r_mo_pct / 100.0
                    r_pa_pct = ((1 + r_mo) ** 12 - 1) * 100.0
        
                    cap_sim = startkapital_szenario
                    m_to_100k = None
                    for m in range(1, 1200):
                        cap_sim = (cap_sim * (1 + r_mo)) + netto_cashflow_szenario
                        if cap_sim >= 100000.0:
                            m_to_100k = m
                            break

                    monthly_vals = [startkapital_szenario]
                    cap_5y = startkapital_szenario
                    for m in range(1, 61):
                        cap_5y = (cap_5y * (1 + r_mo)) + netto_cashflow_szenario
                        monthly_vals.append(max(0, cap_5y))
            
                    scenario_series[f"{r_mo_pct:.1f}% p.M. ({r_pa_pct:.1f}% p.a.)"] = monthly_vals
        
                    if m_to_100k is not None:
                        years_100k = m_to_100k // 12
                        rem_months = m_to_100k % 12
                        m_str = f"🎯 {m_to_100k} Mon. ({years_100k}J {rem_months}M)"
                        target_date = (pd.to_datetime(config.KAUFDATUM) + pd.DateOffset(months=m_to_100k)).strftime("%m/%Y")
                    else:
                        m_str = "Nicht erreicht (>100J)"
                        target_date = "N/A"
            
                    summary_list.append({
                        "rate": r_mo_pct, "rate_pa": r_pa_pct, "ziel_100k": m_str, "ziel_datum": target_date,
                        "j1": monthly_vals[12], "j2": monthly_vals[24], "j3": monthly_vals[36],
                        "j4": monthly_vals[48], "j5": monthly_vals[60],
                    })

                karten_html = '<div style="display: flex; flex-direction: column; gap: 10px;">'
                for e in summary_list:
                    karten_html += f"""
                    <div style="background: #09090B; border: 1px solid #27272A; border-radius: 6px; padding: 12px 14px;">
                        <div style="font-size: 1rem; font-weight: 800; color: #FFFFFF; margin-bottom: 8px;">
                            {e['rate']:.1f}% p.M. <span style="color: #A1A1AA; font-weight: 600; font-size: 0.8rem;">({e['rate_pa']:.2f}% p.a.)</span>
                        </div>
                        <div style="font-size: 0.85rem; color: #00C853; font-weight: 700; margin-bottom: 6px;">{e['ziel_100k']}</div>
                        <div style="font-size: 0.8rem; color: #CBD5E1; margin-bottom: 8px;">Ziel-Datum (100k): {e['ziel_datum']}</div>
                        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; border-top: 1px solid #1A1A1A; padding-top: 8px;">
                            <div><div style="font-size: 0.65rem; color: #71717A;">1J</div><div style="font-size: 0.75rem; color: #E5E7EB; font-weight: 700;">{fmt(e['j1'], 0)}</div></div>
                            <div><div style="font-size: 0.65rem; color: #71717A;">2J</div><div style="font-size: 0.75rem; color: #E5E7EB; font-weight: 700;">{fmt(e['j2'], 0)}</div></div>
                            <div><div style="font-size: 0.65rem; color: #71717A;">3J</div><div style="font-size: 0.75rem; color: #E5E7EB; font-weight: 700;">{fmt(e['j3'], 0)}</div></div>
                            <div><div style="font-size: 0.65rem; color: #71717A;">4J</div><div style="font-size: 0.75rem; color: #E5E7EB; font-weight: 700;">{fmt(e['j4'], 0)}</div></div>
                            <div><div style="font-size: 0.65rem; color: #71717A;">5J</div><div style="font-size: 0.75rem; color: #E5E7EB; font-weight: 700;">{fmt(e['j5'], 0)}</div></div>
                        </div>
                    </div>"""
                karten_html += "</div>"
                st.markdown(karten_html, unsafe_allow_html=True)

                fig_scen = go.Figure()
                months_x = list(range(61))
    
                for label, vals in scenario_series.items():
                    fig_scen.add_trace(go.Scatter(x=months_x, y=vals, mode="lines", name=label))

                fig_scen.add_hline(
                    y=100000, 
                    line_dash="dot", 
                    line_color="#00C853", 
                    annotation_text="🎯 100k Zielwert", 
                    annotation_position="top left",
                    annotation_font=dict(color="#00C853", size=11)
                )

                fig_scen.update_layout(
                    title="5-Jahres Wertentwicklung<br>bei monatlichen Wachstumsraten",
                    paper_bgcolor="#000000", plot_bgcolor="#000000",
                    margin=dict(l=10, r=60, t=80, b=120), 
                    height=580, 
                    legend=dict(
                        orientation="h", 
                        yanchor="top", 
                        y=-0.15,  
                        xanchor="center", 
                        x=0.5, 
                        font=dict(color="#E5E7EB", size=11)
                    ),
                    xaxis=dict(title="Monate ab Kauf", showgrid=True, gridcolor="#1A1A1A", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(title="Depotwert (€)", showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA")),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_scen, width="stretch", key="chart_scenarios")
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Szenarien", e)
    _render_scenarios()



render_dashboard()
