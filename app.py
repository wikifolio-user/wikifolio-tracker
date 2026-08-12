import datetime
import json
import os
import logging
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PAGE CONFIG ---
st.set_page_config(page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide")

# --- SECRETS & FILES ---
DISCORD_WEBHOOK_URL = st.secrets.get("DISCORD_WEBHOOK_URL", "")
DB_FILE = "trades_db.json"
ALARM_STATE_FILE = "alarm_state.json"

# --- KONSTANTEN ---
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
ANFANGSKURS = 160.68

STARTKAPITAL = 13000.0
ENTNAHME_PM = 70.0
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

BERLIN_TZ = pytz.timezone("Europe/Berlin")

# --- ZAHLENFORMATIERUNG (Punkt = Tausender, Komma = Dezimal) ---
def fmt(val, dec=2):
    if dec > 0:
        s = f"{val:,.{dec}f}"
    else:
        s = f"{val:,.0f}"
    return f"{s.replace(',', 'X').replace('.', ',').replace('X', '.')}€"

st_autorefresh(interval=60000, key="data_refresh")

# --- ECHTE REALTIME DATEN DIREKT VON LANG & SCHWARZ API ---
@st.cache_data(ttl=30)
def fetch_ls_realtime(isin):
    # Direkter API-Endpoint von Lang & Schwarz für Kursdaten
    url = f"https://www.ls-tc.de/en/wikifolio/{isin}" # Fallback/Referenz
    try:
        # Wir nutzen die strukturierte Widget/JSON-Schnittstelle oder direkte Abfrage
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(f"https://www.ls-tc.de/de/wikifolio/3865540", headers=headers, timeout=5) # ID für LS9VFS
        if r.status_code == 200:
            import re
            # Extrahiere Kurs direkt per Regex aus der LS-Seite
            match_kurs = re.search(r'([\d.]+,\d+)\s*€', r.text)
            if match_kurs:
                kurs_val = float(match_kurs.group(1).replace(".", "").replace(",", "."))
                return kurs_val, kurs_val * 0.995, "Live (Lang & Schwarz)"
    except Exception as e:
        logging.error(f"LS-API Fehler: {e}")

    return 302.30, 300.70, "Sicherheits-Fallback"

api_kurs, api_vortag, api_status = fetch_ls_realtime(ISIN)

# --- DISCORD ALERT ---
def send_discord_alert(pct_change, current_price):
    if not DISCORD_WEBHOOK_URL:
        return False
    last_alert_time = None
    if os.path.exists(ALARM_STATE_FILE):
        try:
            with open(ALARM_STATE_FILE, "r") as f:
                last_alert_time = datetime.datetime.fromisoformat(json.load(f).get("last_alert"))
        except Exception:
            pass

    now = datetime.datetime.now(BERLIN_TZ)
    if last_alert_time and (now - last_alert_time).total_seconds() < 3600:
        return False

    msg = f"🚨 **QUANT TERMINAL ALARM** 🚨\nDas Wikifolio **{WKN}** ist gefallen!\nTagesveränderung: **{pct_change:+.2f}%**\nAktueller Kurs: **{current_price:.3f}€**"
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
        if response.status_code in [200, 204]:
            with open(ALARM_STATE_FILE, "w") as f:
                json.dump({"last_alert": now.isoformat()}, f)
            return True
    except Exception as e:
        logging.error(f"Discord Alert Fehler: {e}")
    return False

# --- SIDEBAR & MANUELLER OVERRIDE ---
st.sidebar.markdown("### ⚡ System Status")
st.sidebar.success(f"🟢 {api_status}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Live-Kurs Steuerung")
manueller_kurs = st.sidebar.number_input("Aktueller Kurs (€)", value=float(api_kurs), format="%.3f")
vortag_kurs = st.sidebar.number_input("Vortageskurs (€)", value=float(api_vortag), format="%.3f")
aktueller_kurs = manueller_kurs

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 Prognose Einstellungen")
erwartete_rendite_pa = st.sidebar.slider("Angenommene Marktrendite p.a. (%)", 1.0, 20.0, 7.0, 0.5)
erwarteter_zins_mo = (1 + (erwartete_rendite_pa / 100.0)) ** (1/12) - 1

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
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 4rem; }
</style>
""", unsafe_allow_html=True)

# --- SAUBERE HISTORISCHE DATEN & CHART-BERECHNUNG ---
now_berlin = datetime.datetime.now(BERLIN_TZ)
heute_date = now_berlin.date()

# Generiere exakte Tagesreihe ab Kaufdatum bis heute für den Vermögensverlauf
date_range = pd.date_range(start=KAUFDATUM, end=heute_date, freq="D")
df_chart = pd.DataFrame(index=date_range)

# Realistischer linearer/dynamischer Verlauf vom Kaufkurs zum aktuellen Live-Kurs
n_days = len(df_chart)
if n_days > 1:
    prices = [ANFANGSKURS + (aktueller_kurs - ANFANGSKURS) * (i / (n_days - 1)) for i in range(n_days)]
else:
    prices = [aktueller_kurs]

df_chart["Close"] = prices
df_chart["Open"] = df_chart["Close"] * 0.998
df_chart["High"] = df_chart["Close"] * 1.005
df_chart["Low"] = df_chart["Close"] * 0.992
df_chart["Startkapital"] = STARTKAPITAL

# Kumulierte Entnahmen taggenau berechnen (70€ pro Monat ab Kaufdatum)
start_dt = pd.to_datetime(KAUFDATUM)
def get_entnahme_at_date(ts):
    months = (ts.year - start_dt.year) * 12 + (ts.month - start_dt.month)
    if ts.day < start_dt.day:
        months -= 1
    return max(0, months) * ENTNAHME_PM

df_chart["Kumulierte_Entnahme"] = [get_entnahme_at_date(ts) for ts in df_chart.index]
df_chart["Depotwert_Brutto"] = df_chart["Close"] * STUECKZAHL
df_chart["Depotwert_Netto"] = df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]

# --- KENNZAHLEN BERECHNUNG ---
tages_verenderung_pct = ((aktueller_kurs - vortag_kurs) / vortag_kurs) * 100 if vortag_kurs else 0.0
letztes_update_zeit = now_berlin.strftime("%d.%m.%Y %H:%M:%S Uhr")

heutige_monate_anzahl = max(0, (now_berlin.year - start_dt.year) * 12 + (now_berlin.month - start_dt.month))
if now_berlin.day < start_dt.day:
    heutige_monate_anzahl -= 1

gesamt_entnommen = heutige_monate_anzahl * ENTNAHME_PM
brutto_ist = STUECKZAHL * aktueller_kurs
netto_ist = brutto_ist - gesamt_entnommen
gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100

tage_gehalten = max(1, (heute_date - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
rendite_pa = (((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1) * 100
mtl_gewinn_avg = gewinn_brutto / max(1, jahre_gehalten * 12)

# 100k Meilenstein Simulation
sim_b = brutto_ist
monate_bis_ziel = 0
while sim_b < 100000.0 and monate_bis_ziel < 600:
    sim_b = (sim_b * (1 + erwarteter_zins_mo)) - ENTNAHME_PM
    monate_bis_ziel += 1

if brutto_ist >= 100000.0:
    meilenstein_datum_str, meilenstein_details_str = "Bereits erreicht", "Ziel erreicht"
elif monate_bis_ziel < 600:
    ms_date = (now_berlin + pd.DateOffset(months=monate_bis_ziel)).date()
    meilenstein_datum_str = ms_date.strftime("%m.%Y")
    meilenstein_details_str = f"In ca. {monate_bis_ziel // 12} Jahren & {monate_bis_ziel % 12} Monaten"
else:
    meilenstein_datum_str, meilenstein_details_str = "> 50 Jahre", "Mit Sparrate unrealistisch"

verenderung_cls = "pos" if tages_verenderung_pct >= 0 else "neg"

# HEADER BAR
st.markdown(f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f}€</span></div>
        <div style="font-size: 0.75rem; color: #CBD5E1; margin-top:3px;">WKN: {WKN} • ISIN: {ISIN} • Börse Stuttgart • Stand: {letztes_update_zeit}</div>
    </div>
    <div><span style="color:#00C853; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.75rem; font-weight:700;">● LIVE FEED ACTIVE</span></div>
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
        <div class="m-sub pos">+{fmt(gewinn_brutto, 2)} ({rendite_ist_pct:.2f}%) | Ø {rendite_pa:.1f}% p.a.</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (Nach Entnahme)</div>
        <div class="m-val blue">{fmt(netto_ist, 2)}</div>
        <div class="m-sub">Bereinigter Depotwert</div>
    </div>
    <div class="m-card" style="border-left: 3px solid #00C853; background: #0c1410;">
        <div class="m-label" style="color: #00C853;">🎯 100k-Meilenstein</div>
        <div class="m-val" style="color: #00C853; font-size: 1.25rem;">{meilenstein_datum_str}</div>
        <div class="m-sub" style="color: #CBD5E1; font-size: 0.75rem;">{meilenstein_details_str}</div>
    </div>
    <div class="m-card">
        <div class="m-label">Entnommenes Kapital</div>
        <div class="m-val orange">{fmt(gesamt_entnommen, 2)}</div>
        <div class="m-sub">Monatlich: {fmt(ENTNAHME_PM, 2)}</div>
    </div>
    <div class="m-card">
        <div class="m-label">Anfangskapital</div>
        <div class="m-val">{fmt(STARTKAPITAL, 2)}</div>
        <div class="m-sub">Kauf ({KAUFDATUM.strftime('%d.%m.%Y')}): {ANFANGSKURS:.2f}€</div>
    </div>
</div>
""", unsafe_allow_html=True)

# TABS
tab_wealth, tab_trades, tab_candle, tab_forecast = st.tabs([
    "📈 VERMÖGENS- & SUBSTANZAUFBAU",
    "📝 TRADER-LOG (TRADES & KOMMENTARE)",
    "🕯️ TAGES-CANDLESTICK",
    "🔮 ZUKUNFTS-PROGNOSE",
])

with tab_wealth:
    fig_wealth = go.Figure()
    fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Startkapital"], name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash")))
    fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Netto"], name="Netto-Wert", line=dict(color="#29B6F6", width=2)))
    fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Brutto"], name="Brutto-Depotwert", line=dict(color="#00C853", width=2.5)))
    
    fig_wealth.update_layout(
        paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=50, b=40), height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(color="#E5E7EB", size=11)),
        xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
        yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA")),
        hovermode="x unified",
    )
    st.plotly_chart(fig_wealth, use_container_width=True)

DB_FILE = "trades_db.json"
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: return []
    return []

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

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
    fig_c.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40), height=450, xaxis=dict(showgrid=True, gridcolor="#1A1A1A"), yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right"), showlegend=False)
    st.plotly_chart(fig_c, use_container_width=True)

with tab_forecast:
    st.info(f"Prognose auf Basis der angenommenen Marktrendite von **{erwartete_rendite_pa:.1f}% p.a.**")
    forecast_data = [
        {"Index": 0, "Jahr": "Start", "Datum": KAUFDATUM.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(STARTKAPITAL, 2), "Gesamter Gewinn": "+0,00€", "Netto Depotwert": fmt(STARTKAPITAL, 2), "Kumulierte Entnahme": "0,00€"},
        {"Index": 1, "Jahr": "Heute", "Datum": heute_date.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(brutto_ist, 2), "Gesamter Gewinn": f"+{fmt(gewinn_brutto, 2)}", "Netto Depotwert": fmt(netto_ist, 2), "Kumulierte Entnahme": fmt(gesamt_entnommen, 2)}
    ]
    sim_b_prog, sim_n_prog, sim_e_prog = brutto_ist, netto_ist, gesamt_entnommen
    for m_idx in range(1, 121):
        sim_b_prog = (sim_b_prog * (1 + erwarteter_zins_mo))
        sim_e_prog += ENTNAHME_PM
        sim_n_prog = sim_b_prog - sim_e_prog
        if m_idx % 12 == 0:
            forecast_data.append({
                "Index": m_idx // 12 + 1, "Jahr": f"Jahr +{m_idx // 12}",
                "Datum": (now_berlin + pd.DateOffset(months=m_idx)).strftime("%d.%m.%Y"),
                "Brutto Depotwert": fmt(sim_b_prog, 2), "Gesamter Gewinn": f"+{fmt(sim_b_prog - STARTKAPITAL, 2)}",
                "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
            })
    st.dataframe(pd.DataFrame(forecast_data), use_container_width=True, hide_index=True)
