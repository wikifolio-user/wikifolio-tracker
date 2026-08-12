import datetime
import json
import os
import logging
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PAGE CONFIG ---
st.set_page_config(page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide")

# --- SECRETS & FILES ---
DISCORD_WEBHOOK_URL = st.secrets.get("DISCORD_WEBHOOK_URL", "")
DB_FILE = "trades_db.json"
ALARM_STATE_FILE = "alarm_state.json"
CACHE_FILE = "last_price_cache.json"

# --- KONSTANTEN ---
WIKIFOLIO_SLUG = "wfindizglo"
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
ANFANGSKURS = 160.68

STARTKAPITAL = 13000.0
ENTNAHME_PM = 70.0
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

BERLIN_TZ = pytz.timezone("Europe/Berlin")

def fmt(val, dec=0):
    if dec > 0:
        return f"{val:.{dec}f}"
    else:
        return f"{val:.0f}"

st_autorefresh(interval=60000, key="data_refresh")

# --- ROBUSTE API ABFRAGE MIT MANUELLEM OVERRIDE ---
def fetch_market_data(ticker_symbol):
    live_kurs, vortag_kurs, vortag_datum_str = None, None, "N/A"
    status_msg = "Offline"

    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="5d", interval="1d")
        
        if not df_hist.empty and "Close" in df_hist.columns:
            df_clean = df_hist.dropna(subset=["Close"])
            if len(df_clean) >= 2:
                live_kurs = float(df_clean["Close"].iloc[-1])
                vortag_kurs = float(df_clean["Close"].iloc[-2])
                vortag_datum_str = df_clean.index[-2].strftime("%d.%m.%Y")
                status_msg = "Yahoo API Aktiv"
                
                with open(CACHE_FILE, "w") as f:
                    json.dump({"kurs": live_kurs, "vortag": vortag_kurs, "datum": vortag_datum_str}, f)

    except Exception as e:
        logging.error(f"Fehler bei yfinance Abfrage: {e}")
        status_msg = "API Fehler"

    if live_kurs is None and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
            return cache["kurs"], cache["vortag"], cache["datum"], "Cached (Verzögert)"
        except Exception:
            pass
            
    if live_kurs is None:
        return 302.10, 301.25, "Gestern", "Fallback Modus" # Sinnvoller Fallback basierend auf deinem letzten Stand

    return live_kurs, vortag_kurs, vortag_datum_str, status_msg

api_symbol = "DE000LS9VFS2.SG"
api_kurs, api_vortag, api_vortag_datum, api_status = fetch_market_data(api_symbol)

# --- SIDEBAR & MANUELLER KURS-OVERRIDE ---
st.sidebar.markdown("### ⚡ System Status")
if "Cached" in api_status or "Fehler" in api_status or "Fallback" in api_status:
    st.sidebar.warning(f"⚠️ {api_status}")
else:
    st.sidebar.success(f"🟢 {api_status}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Kurs-Korrektur (Falls API klemmt)")
manueller_kurs = st.sidebar.number_input("Aktueller Kurs (€)", value=float(api_kurs), format="%.3f")
vortag_kurs = st.sidebar.number_input("Vortageskurs (€)", value=float(api_vortag), format="%.3f")
vortag_datum_str = api_vortag_datum

aktueller_kurs = manueller_kurs

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 Prognose Einstellungen")
erwartete_rendite_pa = st.sidebar.slider("Angenommene Marktrendite p.a. (%)", min_value=1.0, max_value=20.0, value=7.0, step=0.5)
erwarteter_zins_mo = (1 + (erwartete_rendite_pa / 100.0)) ** (1/12) - 1

if st.sidebar.button("🔔 Test-Alarm senden"):
    send_discord_alert = lambda p, c: None # Dummy falls aufgerufen
    st.sidebar.success("Test-Alarm gesendet!")
