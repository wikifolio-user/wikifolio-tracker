import datetime
import re
import logging
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import config
import github_store

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PAGE CONFIG ---
st.set_page_config(page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# --- SECRETS ---
DISCORD_WEBHOOK_URL = st.secrets.get("DISCORD_WEBHOOK_URL", "")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")   # z.B. "dein-user/wikifolio-tracker"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # Personal Access Token, Scope "repo"
GH_STATE_READY = bool(GITHUB_REPO and GITHUB_TOKEN)

BERLIN_TZ = pytz.timezone("Europe/Berlin")


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
    logging.error(f"App-Fehler in '{context}': {exc}")
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

st_autorefresh(interval=30000, key="data_refresh")

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
    skaliert ihn so, dass er am ersten gemeinsamen Tag exakt beim
    Startkapital beginnt - macht die Linien direkt vergleichbar."""
    s = get_benchmark_history(instrument_id, start_date, end_date)
    if s is None or s.empty:
        return None
    s = s.reindex(df_index, method="ffill").bfill()
    if s.empty or s.iloc[0] == 0:
        return None
    return s / s.iloc[0] * startkapital


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

df_chart["Startkapital"] = config.STARTKAPITAL

# --- HIGH WATERMARK: mit echter Historie initialisieren/korrigieren ---
# Der Cron kennt beim allerersten Lauf nur den aktuellen Kurs als "Hoch" -
# hier wird das (still, ohne Alarm) auf den tatsächlichen historischen
# Höchststand korrigiert, falls der genauer/höher ist.
if not df_chart.empty:
    historischer_hoechststand = float(df_chart["Close"].max())
    hw_state = gh_read_cached(config.STATE_PATH_HIGH_WATERMARK, None)
    aktuelles_hoch = float(hw_state["high_watermark"]) if hw_state and "high_watermark" in hw_state else 0.0
    korrigiertes_hoch = max(historischer_hoechststand, aktuelles_hoch)
    if not hw_state or korrigiertes_hoch > aktuelles_hoch:
        gh_write(
            config.STATE_PATH_HIGH_WATERMARK,
            {"high_watermark": korrigiertes_hoch, "erreicht_am": datetime.datetime.now(BERLIN_TZ).isoformat()},
            message="app: korrigiere/initialisiere high watermark [skip ci]",
        )
    high_watermark_anzeige = korrigiertes_hoch
else:
    high_watermark_anzeige = aktueller_kurs

start_dt = pd.to_datetime(config.KAUFDATUM)
def get_entnahme_at_date(ts):
    months = (ts.year - start_dt.year) * 12 + (ts.month - start_dt.month)
    if ts.day < start_dt.day:
        months -= 1
    return max(0, months) * config.ENTNAHME_PM

df_chart["Kumulierte_Entnahme"] = [get_entnahme_at_date(ts) for ts in df_chart.index]

# --- BENCHMARKS: gleiche Handelstage, normiert auf dasselbe Startkapital ---
benchmark_series = {}
for label, inst_id in config.BENCHMARKS.items():
    s = benchmark_normiert_auf_startkapital(
        df_chart.index, inst_id, config.KAUFDATUM, heute_date, config.STARTKAPITAL
    )
    if s is not None:
        benchmark_series[label] = s

# --- SIMULATION (bisheriges Verhalten): Stückzahl bleibt konstant, Entnahme
# wird nur buchhalterisch vom Bruttowert abgezogen. ---
df_chart["Depotwert_Brutto"] = df_chart["Close"] * config.STUECKZAHL
df_chart["Depotwert_Netto"] = df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]

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
    df_chart, config.STUECKZAHL, config.ENTNAHME_PM, start_dt, config.SPREAD_PCT
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

# --- TERMINAL STYLING ---
st.markdown("""
<style>
    .stApp { background-color: #000000; color: #E5E7EB; font-family: 'JetBrains Mono', monospace; }
    .header-bar {
        display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
        background: #09090B; border: 1px solid #27272A; border-left: 3px solid #00C853;
        border-radius: 6px; padding: 12px 16px; margin-bottom: 16px;
    }
    .header-title { font-size: 1.1rem; font-weight: 800; color: #FFFFFF; }
    .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 14px 16px; }
    .m-label { font-size: 0.75rem; color: #A1A1AA; text-transform: uppercase; font-weight: 700; }
    .m-val { font-size: 1.4rem; font-weight: 800; color: #FFFFFF; margin: 6px 0; }
    .m-sub { font-size: 0.85rem; font-weight: 600; color: #CBD5E1; }
    .pos { color: #00C853; } .neg { color: #FF3D00; } .blue { color: #29B6F6; } .orange { color: #FF3D00; }
    #MainMenu, footer { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 4rem; }
</style>
""", unsafe_allow_html=True)

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

gesamt_entnommen = heutige_monate_anzahl * config.ENTNAHME_PM
brutto_ist = config.STUECKZAHL * aktueller_kurs
netto_ist = brutto_ist - gesamt_entnommen
gewinn_brutto = brutto_ist - config.STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - config.ANFANGSKURS) / config.ANFANGSKURS) * 100

# Reale Variante fuer die aktuellen Kennzahlen (Stückzahl nach echten Verkäufen)
stueckzahl_real_ist = df_chart["Stueckzahl_Real"].iloc[-1] if not df_chart.empty else config.STUECKZAHL
depotwert_real_ist = stueckzahl_real_ist * aktueller_kurs

sim_b = brutto_ist
monate_bis_ziel = 0
while sim_b < 100000.0 and monate_bis_ziel < 600:
    sim_b = (sim_b * (1 + erwarteter_zins_mo)) - config.ENTNAHME_PM
    monate_bis_ziel += 1

monate_namen = {1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni", 
                7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember"}

if brutto_ist >= 100000.0:
    meilenstein_datum_str, meilenstein_details_str = "Bereits erreicht", "Ziel erreicht"
elif monate_bis_ziel < 600:
    ms_date = (now_berlin + pd.DateOffset(months=monate_bis_ziel)).date()
    meilenstein_datum_str = f"{monate_namen[ms_date.month]} {ms_date.year}"
    meilenstein_details_str = f"In ca. {monate_bis_ziel // 12} Jahren & {monate_bis_ziel % 12} Monaten"
else:
    meilenstein_datum_str, meilenstein_details_str = "> 50 Jahre", "Unrealistisch"

verenderung_cls = "pos" if tages_verenderung_pct >= 0 else "neg"

# HEADER BAR
live_badge = (
    '<span style="color:#00C853; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.75rem; font-weight:700;">● VOLLAUTOMATISCH LIVE</span>'
    if is_live_data else
    '<span style="color:#FF3D00; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.75rem; font-weight:700;">● KEINE LIVE-DATEN</span>'
)

st.markdown(f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f}€</span></div>
        <div style="font-size: 0.75rem; color: #CBD5E1; margin-top:3px;">WKN: {config.WKN} • ISIN: {config.ISIN} • Börse Stuttgart • Stand: {letztes_update_zeit}</div>
    </div>
    <div>{live_badge}</div>
</div>
""", unsafe_allow_html=True)

# GRID OVERVIEW
st.markdown(f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Veränderung vs. Vortag</div>
        <div class="m-val {verenderung_cls}">{tages_verenderung_pct:+.2f}%</div>
        <div class="m-sub">Vortag: {vortag_kurs:.3f}€</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val pos">{fmt(brutto_ist, 2)}</div>
        <div class="m-sub pos">+{fmt(gewinn_brutto, 2)} ({rendite_ist_pct:.2f}%) | Ø {erwartete_rendite_pa:.1f}% p.a.</div>
        <div class="m-sub">{config.STUECKZAHL:.4f} Anteile (unverändert seit Kauf)</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (Simulation)</div>
        <div class="m-val blue">{fmt(netto_ist, 2)}</div>
        <div class="m-sub">Entnahme nur buchhalterisch abgezogen</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (Real, Anteile verkauft)</div>
        <div class="m-val" style="color:#FFB300;">{fmt(depotwert_real_ist, 2)}</div>
        <div class="m-sub">{stueckzahl_real_ist:.4f} Anteile nach realer Entnahme (inkl. {config.SPREAD_PCT:.2f}% Spread)</div>
    </div>
    <div class="m-card" style="border-left: 3px solid #00C853; background: #0c1410;">
        <div class="m-label" style="color: #00C853;">🎯 100k-Meilenstein</div>
        <div class="m-val" style="color: #00C853; font-size: 1.15rem;">{meilenstein_datum_str}</div>
        <div class="m-sub" style="color: #CBD5E1; font-size: 0.75rem;">{meilenstein_details_str}</div>
    </div>
    <div class="m-card">
        <div class="m-label">Entnommenes Kapital</div>
        <div class="m-val orange">{fmt(gesamt_entnommen, 2)}</div>
        <div class="m-sub">Monatlich: {fmt(config.ENTNAHME_PM, 2)}</div>
    </div>
    <div class="m-card">
        <div class="m-label">Anfangskapital</div>
        <div class="m-val">{fmt(config.STARTKAPITAL, 2)}</div>
        <div class="m-sub">Kauf ({config.KAUFDATUM.strftime('%d.%m.%Y')}): {config.ANFANGSKURS:.2f}€</div>
    </div>
    <div class="m-card" style="border-left: 3px solid #FFB300;">
        <div class="m-label" style="color: #FFB300;">🏆 High Watermark</div>
        <div class="m-val" style="color: #FFB300;">{high_watermark_anzeige:.3f}€</div>
        <div class="m-sub">Ab hier: {config.PERFORMANCE_FEE_PCT:.1f}% Performance Fee auf neue Gewinne</div>
    </div>
    <div class="m-card">
        <div class="m-label">Laufende Kosten (im Kurs enthalten)</div>
        <div class="m-val" style="font-size: 1.1rem;">{config.ZERTIFIKAT_GEBUEHR_PA_PCT:.2f}% p.a.</div>
        <div class="m-sub">Zertifikatsgebühr, bereits im ls-tc.de-Kurs eingepreist</div>
    </div>
</div>
""", unsafe_allow_html=True)

# TABS
tab_wealth, tab_trades, tab_candle, tab_forecast, tab_scenarios = st.tabs([
    "📈 VERMÖGENS- & SUBSTANZAUFBAU",
    "📝 TRADER-LOG (TRADES & KOMMENTARE)",
    "🕯️ TAGES-CANDLESTICK",
    "🔮 ZUKUNFTS-PROGNOSE",
    "📊 SZENARIO-SIMULATOR (5 JAHRE)",
])

try:
    with tab_wealth:
        st.caption(
            "„Netto (Simulation)“ zieht die Entnahme nur buchhalterisch vom Depotwert ab. "
            f"„Real“ verkauft monatlich tatsächlich Anteile zum dann gültigen Geldkurs "
            f"(inkl. {config.SPREAD_PCT:.2f}% Spread-Annahme) — realistischer, falls du die "
            "70€/Monat wirklich entnimmst. Die gestrichelten Vergleichslinien zeigen, wie sich "
            f"{fmt(config.STARTKAPITAL, 0)} im selben Zeitraum in gängigen Vergleichs-ETFs "
            "entwickelt hätten (Kosten der ETFs bereits im Kurs enthalten, keine Steuern)."
        )
        fig_wealth = go.Figure()
        fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Startkapital"], name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash")))
        fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Netto"], name="Netto (Simulation)", line=dict(color="#29B6F6", width=2)))
        fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Real"], name="Netto (Real)", line=dict(color="#FFB300", width=2, dash="dot")))
        fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Brutto"], name="Brutto-Depotwert", line=dict(color="#00C853", width=2.5)))

        benchmark_colors = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C"]
        for i, (label, s) in enumerate(benchmark_series.items()):
            fig_wealth.add_trace(go.Scatter(
                x=df_chart.index, y=s, name=label,
                line=dict(color=benchmark_colors[i % len(benchmark_colors)], width=1.5, dash="dashdot"),
            ))
    
        fig_wealth.update_layout(
            paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=80, b=40), height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#E5E7EB", size=11)),
            xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
            yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=2000),
            hovermode="x unified",
        )
        st.plotly_chart(fig_wealth, width="stretch")

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
                st.rerun()

    with tab_candle:
        fig_c = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart["Open"], high=df_chart["High"], low=df_chart["Low"], close=df_chart["Close"], increasing_line_color="#00C853", decreasing_line_color="#FF3D00")])
        fig_c.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40), height=450, xaxis=dict(showgrid=True, gridcolor="#1A1A1A"), yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", dtick=10), showlegend=False)
        st.plotly_chart(fig_c, width="stretch")
        st.caption(
            "Basiert auf ls-tc.de Tages-Schlusskursen (Open/High/Low approximiert). "
            "Der GitHub-Actions-Cron protokolliert seit Kurzem zusätzlich alle 5 Min den "
            "echten Kurs in state/price_history/ — daraus lässt sich künftig ein echter "
            "Intraday-Chart bauen, sobald genug Historie gesammelt ist."
        )

    with tab_forecast:
        st.info(f"Zukunfts-Prognose rechnet vollautomatisch auf Basis der bisherigen historischen Performance von **{erwartete_rendite_pa:.2f}% p.a.** weiter.")
    
        forecast_data = [
            {"Index": 0, "Jahr": "Start", "Datum": config.KAUFDATUM.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(config.STARTKAPITAL, 2), "Gesamter Gewinn": "+0,00€", "Netto Depotwert": fmt(config.STARTKAPITAL, 2), "Kumulierte Entnahme": "0,00€"},
            {"Index": 1, "Jahr": "Heute", "Datum": heute_date.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(brutto_ist, 2), "Gesamter Gewinn": f"+{fmt(gewinn_brutto, 2)}", "Netto Depotwert": fmt(netto_ist, 2), "Kumulierte Entnahme": fmt(gesamt_entnommen, 2)}
        ]
    
        sim_b_prog, sim_n_prog, sim_e_prog = brutto_ist, netto_ist, gesamt_entnommen
        milestone_added = brutto_ist >= 100000.0

        for m_idx in range(1, 121):
            sim_b_prog = (sim_b_prog * (1 + erwarteter_zins_mo))
            sim_e_prog += config.ENTNAHME_PM
            sim_n_prog = sim_b_prog - sim_e_prog
        
            current_date = now_berlin + pd.DateOffset(months=m_idx)
        
            if not milestone_added and sim_b_prog >= 100000.0:
                forecast_data.append({
                    "Index": "🎯", "Jahr": "100k Meilenstein",
                    "Datum": current_date.strftime("%d.%m.%Y"),
                    "Brutto Depotwert": fmt(sim_b_prog, 2), "Gesamter Gewinn": f"+{fmt(sim_b_prog - config.STARTKAPITAL, 2)}",
                    "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                })
                milestone_added = True

            if m_idx % 12 == 0:
                forecast_data.append({
                    "Index": m_idx // 12 + 1, "Jahr": f"Jahr +{m_idx // 12}",
                    "Datum": current_date.strftime("%d.%m.%Y"),
                    "Brutto Depotwert": fmt(sim_b_prog, 2), "Gesamter Gewinn": f"+{fmt(sim_b_prog - config.STARTKAPITAL, 2)}",
                    "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                })
            
        df_forecast = pd.DataFrame(forecast_data)
        df_forecast["Index"] = df_forecast["Index"].astype(str)
        st.dataframe(df_forecast, width="stretch", hide_index=True)

    with tab_scenarios:
        st.markdown("### 📊 Szenario-Analyse: Monatliche Entwicklungs-Raten (2,0% bis 6,0% p.M.)")
        st.info(f"Berechnung mit festen monatlichen Renditen ausgehend von **{fmt(config.STARTKAPITAL, 2)}** unter Berücksichtigung der monatlichen Entnahme von **{fmt(config.ENTNAHME_PM, 2)}**.")

        szenario_raten_mo = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
    
        summary_list = []
        scenario_series = {}

        for r_mo_pct in szenario_raten_mo:
            r_mo = r_mo_pct / 100.0
            r_pa_pct = ((1 + r_mo) ** 12 - 1) * 100.0
        
            cap_sim = config.STARTKAPITAL
            m_to_100k = None
            for m in range(1, 1200):
                cap_sim = (cap_sim * (1 + r_mo)) - config.ENTNAHME_PM
                if cap_sim >= 100000.0:
                    m_to_100k = m
                    break

            monthly_vals = [config.STARTKAPITAL]
            cap_5y = config.STARTKAPITAL
            for m in range(1, 61):
                cap_5y = (cap_5y * (1 + r_mo)) - config.ENTNAHME_PM
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
                "Ziel 100k (Monate)": m_str,
                "Monats-Rendite (p.M.)": f"{r_mo_pct:.1f}%",
                "Jahres-Wert (eff. p.a.)": f"{r_pa_pct:.2f}%",
                "Ziel-Datum (100k)": target_date,
                "Wert nach 1 Jahr": fmt(monthly_vals[12], 2),
                "Wert nach 2 Jahren": fmt(monthly_vals[24], 2),
                "Wert nach 3 Jahren": fmt(monthly_vals[36], 2),
                "Wert nach 4 Jahren": fmt(monthly_vals[48], 2),
                "Wert nach 5 Jahren": fmt(monthly_vals[60], 2),
            })

        df_summary = pd.DataFrame(summary_list)
        st.dataframe(df_summary, width="stretch", hide_index=True)

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
        st.plotly_chart(fig_scen, width="stretch")
except Exception as e:
    st.error(f"⚠️ Fehler beim Rendern der Tabs: {e}")
    notify_app_error("Tab-Rendering", e)
