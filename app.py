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

# --- ZAHLENFORMATIERUNG (Gewünschtes Format: 00.000,00€) ---
def fmt(val, dec=2):
    if dec > 0:
        s = f"{val:,.{dec}f}"
    else:
        s = f"{val:,.0f}"
    # Tausenderpunkt und Dezimalkomma im deutschen Format, plus €
    formatted = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted}€"

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
        return 302.10, 301.25, "Gestern", "Fallback Modus"

    return live_kurs, vortag_kurs, vortag_datum_str, status_msg

api_symbol = "DE000LS9VFS2.SG"
api_kurs, api_vortag, api_vortag_datum, api_status = fetch_market_data(api_symbol)

# --- DISCORD ALERT ---
def send_discord_alert(pct_change, current_price):
    if not DISCORD_WEBHOOK_URL:
        return False
        
    last_alert_time = None
    if os.path.exists(ALARM_STATE_FILE):
        try:
            with open(ALARM_STATE_FILE, "r") as f:
                data = json.load(f)
                last_alert_time = datetime.datetime.fromisoformat(data.get("last_alert"))
        except Exception:
            pass

    now = datetime.datetime.now(BERLIN_TZ)
    if last_alert_time and (now - last_alert_time).total_seconds() < 3600:
        return False

    msg = (
        f"🚨 **QUANT TERMINAL ALARM** 🚨\nDas Wikifolio **{WKN}** ({ISIN}) ist"
        f" stark gefallen!\nTagesveränderung: **{pct_change:+.2f}%**\nAktueller"
        f" Kurs: **{current_price:.3f} €**"
    )
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
        if response.status_code in [200, 204]:
            with open(ALARM_STATE_FILE, "w") as f:
                json.dump({"last_alert": now.isoformat()}, f)
            return True
    except Exception as e:
        logging.error(f"Discord Alert fehlgeschlagen: {e}")
        
    return False

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
    send_discord_alert(-1.50, aktueller_kurs)
    st.sidebar.success("Test-Alarm gesendet!")

# --- TERMINAL STYLING ---
st.markdown(
    """
<style>
    .stApp { background-color: #000000; color: #E5E7EB; font-family: 'JetBrains Mono', monospace; }
    .header-bar {
        display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
        background: #09090B; border: 1px solid #27272A; border-left: 3px solid #00C853;
        border-radius: 6px; padding: 12px 16px; margin-bottom: 16px;
    }
    .header-title { font-size: 1.1rem; font-weight: 800; color: #FFFFFF; }
    .grid-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px; margin-bottom: 20px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 14px 16px; }
    .m-label { font-size: 0.75rem; color: #A1A1AA; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; }
    .m-val { font-size: 1.4rem; font-weight: 800; color: #FFFFFF; margin: 6px 0; white-space: nowrap; }
    .m-sub { font-size: 0.85rem; font-weight: 600; white-space: nowrap; color: #CBD5E1; }
    .pos { color: #00C853; }
    .neg { color: #FF3D00; }
    .blue { color: #29B6F6; }
    .orange { color: #FF3D00; }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 4rem; }
</style>
""",
    unsafe_allow_html=True,
)

# --- CHART DATEN ---
@st.cache_data(ttl=3600)
def get_real_chart_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df = tk.history(period="1y", interval="1d")
        if not df.empty:
            return df
    except Exception as e:
        logging.error(f"Chart error: {e}")
    
    dates = pd.date_range(start=KAUFDATUM, end=datetime.datetime.now(BERLIN_TZ).date(), freq="D")
    df_fallback = pd.DataFrame({"Close": [ANFANGSKURS]*len(dates)}, index=dates)
    df_fallback["Open"] = df_fallback["Close"]
    df_fallback["High"] = df_fallback["Close"]
    df_fallback["Low"] = df_fallback["Close"]
    return df_fallback

df_chart = get_real_chart_data(api_symbol)

# --- KENNZAHLEN ---
aktuelles_datum_str = datetime.datetime.now(BERLIN_TZ).strftime("%d.%m.%Y")
tages_verenderung_pct = ((aktueller_kurs - vortag_kurs) / vortag_kurs) * 100 if vortag_kurs else 0.0
letztes_update_zeit = datetime.datetime.now(BERLIN_TZ).strftime("%d.%m.%Y %H:%M:%S Uhr")

if tages_verenderung_pct <= -1.0:
    send_discord_alert(tages_verenderung_pct, aktueller_kurs)

start_dt = pd.to_datetime(KAUFDATUM)

def berechne_monatliche_entnahme(dt):
    monate = (dt.year - start_dt.year) * 12 + (dt.month - start_dt.month)
    if dt.day < start_dt.day:
        monate -= 1
    return max(0, monate) * ENTNAHME_PM

df_chart["Kumulierte_Entnahme"] = [berechne_monatliche_entnahme(ts) for ts in df_chart.index]
df_chart["Depotwert_Brutto"] = df_chart["Close"] * STUECKZAHL
df_chart["Depotwert_Netto"] = df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]
df_chart["Startkapital"] = STARTKAPITAL

now_berlin = datetime.datetime.now(BERLIN_TZ)
heute_date = now_berlin.date()

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
monate_gehalten = max(1, jahre_gehalten * 12)
mtl_gewinn_avg = gewinn_brutto / max(1, monate_gehalten)

sim_b = brutto_ist
monate_bis_ziel = 0

while sim_b < 100000.0 and monate_bis_ziel < 600:
    sim_b = (sim_b * (1 + erwarteter_zins_mo)) - ENTNAHME_PM
    monate_bis_ziel += 1

if brutto_ist >= 100000.0:
    meilenstein_datum_str = "Bereits erreicht"
    meilenstein_details_str = "Ziel erreicht"
elif monate_bis_ziel < 600:
    ms_date = (now_berlin + pd.DateOffset(months=monate_bis_ziel)).date()
    meilenstein_datum_str = ms_date.strftime("%m.%Y")
    meilenstein_details_str = f"In ca. {monate_bis_ziel // 12} Jahren & {monate_bis_ziel % 12} Monaten"
else:
    meilenstein_datum_str = "> 50 Jahre"
    meilenstein_details_str = "Mit aktueller Sparrate unrealistisch"

verenderung_cls = "pos" if tages_verenderung_pct >= 0 else "neg"
kaufdatum_str = KAUFDATUM.strftime("%d.%m.%Y")

# HEADER BAR
st.markdown(
    f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f}€</span> <span style="font-size:0.8rem; color:#CBD5E1;">({aktuelles_datum_str})</span></div>
        <div style="font-size: 0.75rem; color: #CBD5E1; margin-top:3px;">WKN: {WKN} • ISIN: {ISIN} • Börse Stuttgart • Stand: {letztes_update_zeit}</div>
    </div>
    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end;">
        <span style="color:#00C853; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.75rem; font-weight:700;">● FULL AUTO SYNC</span>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# GRID OVERVIEW
st.markdown(
    f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Veränderung vs. Vortag</div>
        <div class="m-val {verenderung_cls}">{tages_verenderung_pct:+.2f}%</div>
        <div class="m-sub">Schluss ({vortag_datum_str}): {vortag_kurs:.3f}€</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val pos">{fmt(brutto_ist, 2)}</div>
        <div class="m-sub pos">+{fmt(gewinn_brutto, 2)} ({rendite_ist_pct:.2f}%) | Ø +{fmt(mtl_gewinn_avg, 2)} mtl.</div>
        <div class="m-sub" style="margin-top: 4px; color: #CBD5E1;">Ø {rendite_pa:.1f}% p.a. historische Rendite</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (Nach Entnahme)</div>
        <div class="m-val blue">{fmt(netto_ist, 2)}</div>
        <div class="m-sub">Aktueller Depotwert bereinigt</div>
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
        <div class="m-sub">Kauf ({kaufdatum_str}): {ANFANGSKURS:.2f}€</div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

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

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

db_events = load_db()

with tab_trades:
    st.markdown("### 📋 Historie")
    if len(db_events) == 0:
        st.info("Keine Einträge vorhanden.")
    else:
        for ev in db_events:
            e_typ, e_datum, e_titel, e_inhalt = ev.get("typ", ""), ev.get("datum", ""), ev.get("titel", ""), ev.get("inhalt", "")
            st.markdown(
                f"""
                <div style="background: #09090B; border: 1px solid #27272A; border-left: 3px solid #29B6F6; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                    <div style="font-size: 0.75rem; color: #71717A;"><b>[{e_typ}]</b> - {e_datum}</div>
                    <div style="font-weight: 700; color: #FFFFFF; font-size: 0.95rem;">{e_titel}</div>
                    <div style="font-size: 0.85rem; color: #D1D5DB;">{e_inhalt}</div>
                </div>
                """, unsafe_allow_html=True
            )

    with st.form("trade_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([2, 2, 3])
        with col1:
            et = st.selectbox("Typ", ["Trade", "Kommentar", "Hinweis"])
        with col2:
            ed = st.date_input("Datum", heute_date)
        with col3:
            eti = st.text_input("Titel")
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
    st.info(f"Prognose auf Basis der angenommenen Marktrendite von **{erwartete_rendite_pa:.1f}% p.a.** (siehe Sidebar).")
    
    forecast_data = []
    forecast_data.append({
        "Index": 0, "Jahr": "Start", "Datum": KAUFDATUM.strftime("%d.%m.%Y"),
        "Brutto Depotwert": fmt(STARTKAPITAL, 2), "Gesamter Gewinn": "+0,00€",
        "Netto Depotwert": fmt(STARTKAPITAL, 2), "Kumulierte Entnahme": "0,00€",
    })
    forecast_data.append({
        "Index": 1, "Jahr": "Heute", "Datum": heute_date.strftime("%d.%m.%Y"),
        "Brutto Depotwert": fmt(brutto_ist, 2), "Gesamter Gewinn": f"+{fmt(gewinn_brutto, 2)}",
        "Netto Depotwert": fmt(netto_ist, 2), "Kumulierte Entnahme": fmt(gesamt_entnommen, 2),
    })

    sim_b_prog, sim_n_prog, sim_e_prog = brutto_ist, netto_ist, gesamt_entnommen
    for m_idx in range(1, 121):
        sim_b_prog = (sim_b_prog * (1 + erwarteter_zins_mo))
        sim_e_prog += ENTNAHME_PM
        sim_n_prog = sim_b_prog - sim_e_prog
        if m_idx % 12 == 0:
            forecast_data.append({
                "Index": m_idx // 12 + 1, "Jahr": f"Jahr +{m_idx // 12}",
                "Datum": (now_berlin + pd.DateOffset(months=m_idx)).strftime("%d.%m.%Y"),
                "Brutto Depotwert": fmt(sim_b_prog, 2),
                "Gesamter Gewinn": f"+{fmt(sim_b_prog - STARTKAPITAL, 2)}",
                "Netto Depotwert": fmt(sim_n_prog, 2),
                "Kumulierte Entnahme": fmt(sim_e_prog, 2),
            })

    df_f = pd.DataFrame(forecast_data)
    st.dataframe(df_f, use_container_width=True, hide_index=True)
