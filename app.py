import datetime
import json
import os
import logging
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import yfinance as yf
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

# --- VOLLAUTOMATISCHER LIVE-KURS ABRUF ---
@st.cache_data(ttl=60)
def get_live_market_data():
    tickers_to_try = ["LS9VFS.SG", "LS9VFS.F", "LS9VFS.MU", "LS9VFS.DU"]
    for ticker_symbol in tickers_to_try:
        try:
            t = yf.Ticker(ticker_symbol)
            fi = t.fast_info
            akt = float(fi.get("last_price") or fi.get("regularMarketPrice") or 0)
            vor = float(fi.get("previous_close") or fi.get("regularMarketPreviousClose") or 0)
            if akt > 0 and vor > 0:
                return akt, vor, f"Yahoo FastInfo ({ticker_symbol})"
        except Exception as e:
            logging.error(f"Fehler bei fast_info für {ticker_symbol}: {e}")
            
    for ticker_symbol in tickers_to_try:
        try:
            t = yf.Ticker(ticker_symbol)
            hist = t.history(period="5d")
            if not hist.empty and len(hist) >= 2:
                akt = float(hist["Close"].iloc[-1])
                vor = float(hist["Close"].iloc[-2])
                return akt, vor, f"Yahoo History ({ticker_symbol})"
        except Exception as e:
            logging.error(f"Fehler bei History für {ticker_symbol}: {e}")
            
    return 302.980, 302.100, "Fallback"

aktueller_kurs, vortag_kurs, fetched_source = get_live_market_data()

# --- ORIGINALE HISTORISCHE DATEN ---
@st.cache_data(ttl=300)
def get_historical_market_data(start_date, end_date, target_akt_kurs):
    tickers_to_try = ["LS9VFS.SG", "LS9VFS.F", "LS9VFS.MU", "LS9VFS.DU"]
    for ticker_symbol in tickers_to_try:
        try:
            t = yf.Ticker(ticker_symbol)
            df = t.history(start=start_date, end=end_date + datetime.timedelta(days=1))
            if not df.empty and len(df) > 1 and "Close" in df.columns:
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                return df[["Open", "High", "Low", "Close"]], f"Yahoo Original History ({ticker_symbol})"
        except Exception as e:
            logging.error(f"Fehler beim Laden der Historie für {ticker_symbol}: {e}")
            
    date_range = pd.date_range(start=start_date, end=end_date, freq="B")
    n = len(date_range)
    prices = [ANFANGSKURS * ((target_akt_kurs / ANFANGSKURS) ** (i / max(1, n - 1))) for i in range(n)]
    df = pd.DataFrame(index=date_range)
    df["Close"] = prices
    df["Open"] = prices
    df["High"] = prices
    df["Low"] = prices
    return df, "Direktverbindung (Start- bis Live-Wert)"

now_berlin = datetime.datetime.now(BERLIN_TZ)
heute_date = now_berlin.date()

df_chart, hist_source_name = get_historical_market_data(KAUFDATUM, heute_date, aktueller_kurs)

if not df_chart.empty:
    df_chart.iloc[-1, df_chart.columns.get_loc("Close")] = aktueller_kurs
    df_chart.iloc[-1, df_chart.columns.get_loc("High")] = max(df_chart.iloc[-1]["High"], aktueller_kurs)
    df_chart.iloc[-1, df_chart.columns.get_loc("Low")] = min(df_chart.iloc[-1]["Low"], aktueller_kurs)

df_chart["Startkapital"] = STARTKAPITAL

start_dt = pd.to_datetime(KAUFDATUM)
def get_entnahme_at_date(ts):
    months = (ts.year - start_dt.year) * 12 + (ts.month - start_dt.month)
    if ts.day < start_dt.day:
        months -= 1
    return max(0, months) * ENTNAHME_PM

df_chart["Kumulierte_Entnahme"] = [get_entnahme_at_date(ts) for ts in df_chart.index]
df_chart["Depotwert_Brutto"] = df_chart["Close"] * STUECKZAHL
df_chart["Depotwert_Netto"] = df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]

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

# --- AUTOMATISCHE RENDITE-BERECHNUNG ---
tage_gehalten = max(1, (heute_date - KAUFDATUM).days)
erwartete_rendite_pa = (((aktueller_kurs / ANFANGSKURS) ** (365.25 / tage_gehalten)) - 1) * 100
erwarteter_zins_mo = (1 + (erwartete_rendite_pa / 100.0)) ** (1/12) - 1

# --- SIDEBAR & STEUERUNG ---
st.sidebar.markdown("### ⚡ System Status")
st.sidebar.success(f"🟢 Vollautomatisch aktiv\nFeed: {fetched_source}\nChart-Feed: {hist_source_name}")
st.sidebar.write(f"Webhook geladen: {'Ja' if DISCORD_WEBHOOK_URL else 'Nein'}")

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
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 4rem; }
</style>
""", unsafe_allow_html=True)

# --- KENNZAHLEN ---
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

sim_b = brutto_ist
monate_bis_ziel = 0
while sim_b < 100000.0 and monate_bis_ziel < 600:
    sim_b = (sim_b * (1 + erwarteter_zins_mo)) - ENTNAHME_PM
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
st.markdown(f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f}€</span></div>
        <div style="font-size: 0.75rem; color: #CBD5E1; margin-top:3px;">WKN: {WKN} • ISIN: {ISIN} • Börse Stuttgart • Stand: {letztes_update_zeit}</div>
    </div>
    <div><span style="color:#00C853; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.75rem; font-weight:700;">● VOLLAUTOMATISCH LIVE</span></div>
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
    </div>
    <div class="m-card">
        <div class="m-label">Netto (Nach Entnahme)</div>
        <div class="m-val blue">{fmt(netto_ist, 2)}</div>
        <div class="m-sub">Bereinigter Depotwert</div>
    </div>
    <div class="m-card" style="border-left: 3px solid #00C853; background: #0c1410;">
        <div class="m-label" style="color: #00C853;">🎯 100k-Meilenstein</div>
        <div class="m-val" style="color: #00C853; font-size: 1.15rem;">{meilenstein_datum_str}</div>
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
tab_wealth, tab_trades, tab_candle, tab_forecast, tab_scenarios = st.tabs([
    "📈 VERMÖGENS- & SUBSTANZAUFBAU",
    "📝 TRADER-LOG (TRADES & KOMMENTARE)",
    "🕯️ TAGES-CANDLESTICK",
    "🔮 ZUKUNFTS-PROGNOSE",
    "📊 SZENARIO-SIMULATOR (5 JAHRE)",
])

with tab_wealth:
    fig_wealth = go.Figure()
    fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Startkapital"], name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash")))
    fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Netto"], name="Netto-Wert", line=dict(color="#29B6F6", width=2)))
    fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Brutto"], name="Brutto-Depotwert", line=dict(color="#00C853", width=2.5)))
    
    fig_wealth.add_hline(
        y=100000, 
        line_dash="dot", 
        line_color="#00C853", 
        annotation_text="🎯 100k Zielwert", 
        annotation_position="bottom right",
        annotation_font=dict(color="#00C853", size=11)
    )
    
    fig_wealth.update_layout(
        paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=50, b=40), height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(color="#E5E7EB", size=11)),
        xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
        yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA")),
        hovermode="x unified",
    )
    st.plotly_chart(fig_wealth, width="stretch")

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
    st.plotly_chart(fig_c, width="stretch")

with tab_forecast:
    st.info(f"Zukunfts-Prognose rechnet vollautomatisch auf Basis der bisherigen historischen Performance von **{erwartete_rendite_pa:.2f}% p.a.** weiter.")
    
    forecast_data = [
        {"Index": 0, "Jahr": "Start", "Datum": KAUFDATUM.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(STARTKAPITAL, 2), "Gesamter Gewinn": "+0,00€", "Netto Depotwert": fmt(STARTKAPITAL, 2), "Kumulierte Entnahme": "0,00€"},
        {"Index": 1, "Jahr": "Heute", "Datum": heute_date.strftime("%d.%m.%Y"), "Brutto Depotwert": fmt(brutto_ist, 2), "Gesamter Gewinn": f"+{fmt(gewinn_brutto, 2)}", "Netto Depotwert": fmt(netto_ist, 2), "Kumulierte Entnahme": fmt(gesamt_entnommen, 2)}
    ]
    
    sim_b_prog, sim_n_prog, sim_e_prog = brutto_ist, netto_ist, gesamt_entnommen
    milestone_added = brutto_ist >= 100000.0

    for m_idx in range(1, 121):
        sim_b_prog = (sim_b_prog * (1 + erwarteter_zins_mo))
        sim_e_prog += ENTNAHME_PM
        sim_n_prog = sim_b_prog - sim_e_prog
        
        current_date = now_berlin + pd.DateOffset(months=m_idx)
        
        if not milestone_added and sim_b_prog >= 100000.0:
            forecast_data.append({
                "Index": "🎯", "Jahr": "100k Meilenstein",
                "Datum": current_date.strftime("%d.%m.%Y"),
                "Brutto Depotwert": fmt(sim_b_prog, 2), "Gesamter Gewinn": f"+{fmt(sim_b_prog - STARTKAPITAL, 2)}",
                "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
            })
            milestone_added = True

        if m_idx % 12 == 0:
            forecast_data.append({
                "Index": m_idx // 12 + 1, "Jahr": f"Jahr +{m_idx // 12}",
                "Datum": current_date.strftime("%d.%m.%Y"),
                "Brutto Depotwert": fmt(sim_b_prog, 2), "Gesamter Gewinn": f"+{fmt(sim_b_prog - STARTKAPITAL, 2)}",
                "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
            })
            
    st.dataframe(pd.DataFrame(forecast_data), width="stretch", hide_index=True)

with tab_scenarios:
    st.markdown("### 📊 Szenario-Analyse: Monatliche Entwicklungs-Raten (2,0% bis 6,0% p.M.)")
    st.info(f"Berechnung mit festen monatlichen Renditen ausgehend von **{fmt(STARTKAPITAL, 2)}** unter Berücksichtigung der monatlichen Entnahme von **{fmt(ENTNAHME_PM, 2)}**.")

    szenario_raten_mo = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
    
    summary_list = []
    scenario_series = {}

    for r_mo_pct in szenario_raten_mo:
        r_mo = r_mo_pct / 100.0
        # Effektive Jahresrendite (p.a.)
        r_pa_pct = ((1 + r_mo) ** 12 - 1) * 100.0
        
        # Berechnung der Monate bis 100k
        cap_sim = STARTKAPITAL
        m_to_100k = None
        for m in range(1, 1200): # max 100 Jahre
            cap_sim = (cap_sim * (1 + r_mo)) - ENTNAHME_PM
            if cap_sim >= 100000.0:
                m_to_100k = m
                break

        # 5-Jahres Monatswert-Verlauf (60 Monate)
        monthly_vals = [STARTKAPITAL]
        cap_5y = STARTKAPITAL
        for m in range(1, 61):
            cap_5y = (cap_5y * (1 + r_mo)) - ENTNAHME_PM
            monthly_vals.append(max(0, cap_5y))
            
        scenario_series[f"{r_mo_pct:.1f}% p.M. ({r_pa_pct:.1f}% p.a.)"] = monthly_vals
        
        if m_to_100k is not None:
            years_100k = m_to_100k // 12
            rem_months = m_to_100k % 12
            m_str = f"🎯 {m_to_100k} Mon. ({years_100k}J {rem_months}M)"
            target_date = (pd.to_datetime(KAUFDATUM) + pd.DateOffset(months=m_to_100k)).strftime("%m/%Y")
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

    # Diagramm-Vergleich über 5 Jahre (60 Monate)
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
        title="5-Jahres Wertentwicklung bei monatlichen Wachstumsraten",
        paper_bgcolor="#000000", plot_bgcolor="#000000",
        margin=dict(l=10, r=60, t=50, b=40), height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(color="#E5E7EB", size=11)),
        xaxis=dict(title="Monate ab Kauf", showgrid=True, gridcolor="#1A1A1A", tickfont=dict(color="#A1A1AA")),
        yaxis=dict(title="Depotwert (€)", showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA")),
        hovermode="x unified",
    )
    st.plotly_chart(fig_scen, width="stretch")
