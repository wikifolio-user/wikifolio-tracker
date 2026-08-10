import datetime
import json
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide"
)

# -------------------------------------------------------------------
# ⚙️ KONFIGURATION
DISCORD_WEBHOOK_URL = (
    "https://discord.com/api/webhooks/1536127717622153236/"
    "WUsjAZmJjobz42r3zYtxJFS2rBWDLGXGfPKkxDPTMJHBmp8HmcgViaH9guzWoxUoz_Lc"
)
DB_FILE = "trades_db.json"
ALARM_STATE_FILE = "alarm_state.json"

WKN = "LS9VFS"
ISIN = "DE000LS9VFS2"
ANFANGSKURS = 160.68
STARTKAPITAL = 13000.0
ENTNAHME_PM = 70.0
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# Helper für Formatierung
def fmt(val, dec=0):
  s = f"{val:,.{dec}f}" if dec > 0 else f"{val:,.0f}"
  return s.replace(",", "X").replace(".", ",").replace("X", ".")

# --- STYLING (Optimierte Schriftgrößen) ---
st.markdown(
    """
<style>
    .stApp { background-color: #000000; color: #E5E7EB; font-family: 'JetBrains Mono', monospace; }
    .header-bar {
        background: #09090B; border: 1px solid #27272A; border-left: 3px solid #00C853;
        border-radius: 6px; padding: 12px 16px; margin-bottom: 16px;
    }
    .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 16px; }
    .m-label { font-size: 0.8rem; color: #A1A1AA; text-transform: uppercase; font-weight: 700; margin-bottom: 4px; }
    .m-val { font-size: 1.5rem; font-weight: 800; color: #FFFFFF; }
    .m-sub { font-size: 0.9rem; font-weight: 600; color: #CBD5E1; margin-top: 4px; }
    .pos { color: #00C853; }
    .neg { color: #FF3D00; }
    .blue { color: #29B6F6; }
    .orange { color: #FF3D00; }
</style>
""",
    unsafe_allow_html=True,
)

# --- DATEN GENERIERUNG ---
@st.cache_data
def get_chart_data(target_kurs):
  start_dt = pd.to_datetime("2025-07-09")
  end_dt = datetime.datetime.now()
  dates = pd.date_range(start=start_dt, end=end_dt, freq="h")
  np.random.seed(42)
  trend = np.linspace(ANFANGSKURS, target_kurs, len(dates))
  random_walk = np.cumsum(np.random.normal(0, 0.35, len(dates)))
  df = pd.DataFrame({"Close": trend + (random_walk - np.linspace(0, random_walk[-1], len(dates)))}, index=dates)
  return df

aktueller_kurs = 301.24 # Beispielwert aus Bild
df_chart = get_chart_data(aktueller_kurs)

# --- BERECHNUNGEN ---
start_dt = pd.to_datetime("2025-07-09")
tage_gehalten = max(1, (datetime.date.today() - KAUFDATUM).days)
monate_insgesamt = max(1, tage_gehalten / 30.44)

brutto_ist = STUECKZAHL * aktueller_kurs
gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100

# Annualisierte & Monatliche Rendite
rendite_pa = (((aktueller_kurs / ANFANGSKURS) ** (365.25 / tage_gehalten)) - 1) * 100
durchschnitt_monat_gesamt = (((brutto_ist / STARTKAPITAL) ** (1 / monate_insgesamt)) - 1) * 100

# --- UI ANZEIGE ---
st.markdown(f'<div class="header-bar"><h1>QUANT TERMINAL // {WKN}</h1></div>', unsafe_allow_html=True)

st.markdown(
    f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val pos">{fmt(brutto_ist)} €</div>
        <div class="m-sub pos">+{fmt(gewinn_brutto)} € Gewinn ({rendite_ist_pct:.2f}%)</div>
        <div class="m-sub" style="font-size: 0.75rem; color: #94A3B8; margin-top: 10px;">
            Ø {rendite_pa:.1f}% p.a. | {durchschnitt_monat_gesamt:+.2f}% mtl. (Ø seit Start)<br>
            <i style="color: #64748B;">*Werte sind mathematische Hochrechnungen basierend auf der bisherigen Laufzeit.</i>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)
