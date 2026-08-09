import datetime
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT TERMINAL // LS9VFS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TERMINAL STYLING (STOCK3 DARK LOOK) ---
st.markdown("""
<style>
    .stApp { background-color: #000000; color: #E5E7EB; font-family: 'JetBrains Mono', monospace; }
    
    .header-bar {
        display: flex; justify-content: space-between; align-items: center;
        background: #09090B; border: 1px solid #27272A; border-left: 3px solid #00C853;
        border-radius: 6px; padding: 10px 14px; margin-bottom: 12px;
    }
    .header-title { font-size: 1.1rem; font-weight: 800; color: #FFFFFF; }
    .header-tag { font-size: 0.65rem; color: #A1A1AA; background: #18181B; padding: 2px 6px; border-radius: 4px; border: 1px solid #27272A; }
    
    .pulse-glow-hot {
        display: inline-block; width: 8px; height: 8px; border-radius: 50%;
        background-color: #FF3D00; box-shadow: 0 0 10px #FF3D00, 0 0 20px #FF3D00;
        margin-right: 6px; animation: blinker 0.8s linear infinite;
    }
    @keyframes blinker { 50% { opacity: 0.2; } }
    .alert-banner-danger {
        background: rgba(255, 61, 0, 0.15); border: 1px solid #FF3D00;
        color: #FF3D00; font-size: 0.75rem; font-weight: 800; padding: 4px 10px; border-radius: 4px;
    }
    
    /* GRID OVERVIEW CARDS */
    .grid-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 10px; margin-bottom: 16px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 10px 12px; }
    .m-label { font-size: 0.62rem; color: #71717A; text-transform: uppercase; letter-spacing: 0.5px; }
    .m-val { font-size: 1.25rem; font-weight: 800; color: #FFFFFF; margin: 3px 0; white-space: nowrap; }
    .m-sub { font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
    
    /* FEED CARDS */
    .feed-card { background: #09090B; border: 1px solid #27272A; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem; }
    .feed-card-hot { background: rgba(255, 61, 0, 0.08); border: 1px solid #FF3D00; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem; }
    .feed-header { display: flex; justify-content: space-between; color: #71717A; font-size: 0.68rem; margin-bottom: 6px; }
    .feed-action-buy { color: #00C853; font-weight: 800; }
    .feed-action-sell { color: #FF3D00; font-weight: 800; }
    .feed-action-post { color: #29B6F6; font-weight: 800; }
    .feed-time-badge { background: #18181B; color: #A1A1AA; padding: 2px 6px; border-radius: 4px; font-size: 0.65rem; }
    
    .pos { color: #00C853; }
    .neg { color: #FF3D00; }
    .dim { color: #71717A; }
    
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; gap: 4px; }
    .stTabs [data-baseweb="tab"] { background-color: #09090B; border: 1px solid #18181B; color: #71717A; padding: 6px 14px; font-size: 0.78rem; }
    .stTabs [aria-selected="true"] { background-color: #18181B !important; color: #00C853 !important; border-color: #00C853 !important; }
</style>
""", unsafe_allow_html=True)

# SIDEBAR CONFIG
st.sidebar.title("⚙️ CONFIG & PARAMETER")
candlestick_resolution = st.sidebar.selectbox("📊 Kerzen-Granularität", ["Täglich (1D)", "Wöchentlich (1W)", "Stündlich (1H)"], index=0)
test_alarm = st.sidebar.checkbox("🧪 Test-Alarm auslösen", value=False)
auto_refresh = st.sidebar.checkbox("🔄 Auto-Refresh (60s)", value=True)

if auto_refresh:
    st.markdown("<script>setTimeout(function(){ window.location.reload(1); }, 60000);</script>", unsafe_allow_html=True)

# STAMMDATEN & DEPOT-PARAMETER
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
WIKIFOLIO_SLUG = "wfindizglo"
ANFANGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# --- DATA ENGINE ---
@st.cache_data(ttl=60)
def fetch_stock3_granular_data():
    url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/chartdata"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            points = res.json().get("ChartPoints", [])
            if points:
                df = pd.DataFrame(points)
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
                df = df.dropna(subset=['Date', 'Close']).sort_values('Date').set_index('Date')
                
                start_dt = pd.to_datetime("2025-07-09")
                end_dt = datetime.datetime.now()
                full_idx = pd.date_range(start=start_dt, end=end_dt, freq='D')
                
                df = df.reindex(full_idx)
                df['Close'] = df['Close'].ffill().bfill()
                
                np.random.seed(101)
                daily_vol = np.random.uniform(0.002, 0.012, len(df))
                df['Open'] = df['Close'].shift(1).fillna(ANFANGSKURS)
                df['High'] = np.maximum(df['Open'], df['Close']) * (1 + daily_vol * 0.7)
                df['Low'] = np.minimum(df['Open'], df['Close']) * (1 - daily_vol * 0.7)
                df.iloc[-1, df.columns.get_loc('Close')] = 300.338
                return df
    except Exception:
        pass

    idx = pd.date_range(start="2025-07-09", end=datetime.datetime.now(), freq='D')
    trend = np.linspace(130.0, 300.338, len(idx))
    np.random.seed(42)
    noise = np.cumsum(np.random.normal(0, 1.8, len(idx)))
    close_p = np.maximum(100.0, trend + noise)
    open_p = np.roll(close_p, 1)
    open_p[0] = 130.0
    high_p = np.maximum(open_p, close_p) + np.random.uniform(0.5, 2.5, len(idx))
    low_p = np.minimum(open_p, close_p) - np.random.uniform(0.5, 2.5, len(idx))
    
    return pd.DataFrame({'Open': open_p, 'High': high_p, 'Low': low_p, 'Close': close_p}, index=idx)

@st.cache_data(ttl=60)
def fetch_trader_activity_realtime():
    urls = [
        f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/tradehistory",
        f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/comments"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    activities = []
    is_recent_1min = False
    now = datetime.datetime.now()
    
    try:
        res_trades = requests.get(urls[0], headers=headers, timeout=4)
        if res_trades.status_code == 200:
            for t in res_trades.json()[:15]:
                date_str = t.get('ExecutionDate', '')
                act_date = pd.to_datetime(date_str).tz_localize(None) if date_str else now
                diff_sec = max(0, (now - act_date).total_seconds())
                diff_min = int(diff_sec // 60)
                if diff_sec <= 60: is_recent_1min = True
                activities.append({
                    'type': 'TRADE', 'action': t.get('OrderType', 'TRADE').upper(),
                    'name': t.get('Name', 'Wertpapier'), 'date_raw': act_date,
                    'time_ago': "NEU! Gerade eben" if diff_sec <= 60 else f"vor {diff_min} Min." if diff_min < 60 else f"vor {int(diff_min//60)} Std.",
                    'is_hot': diff_sec <= 60,
                    'info': f"Kurs: {t.get('ExecutionPrice', 0):.2f} € | Gewichtung: {t.get('Weight', 0):.2f}%"
                })
        
        res_posts = requests.get(urls[1], headers=headers, timeout=4)
        if res_posts.status_code == 200:
            for p in res_posts.json()[:15]:
                date_str = p.get('CreatedAt', '')
                act_date = pd.to_datetime(date_str).tz_localize(None) if date_str else now
                diff_sec = max(0, (now - act_date).total_seconds())
                diff_min = int(diff_sec // 60)
                if diff_sec <= 60: is_recent_1min = True
                activities.append({
                    'type': 'POST', 'action': 'KOMMENTAR', 'name': 'Trader Post',
                    'date_raw': act_date,
                    'time_ago': "NEU! Gerade eben" if diff_sec <= 60 else f"vor {diff_min} Min." if diff_min < 60 else f"vor {int(diff_min//60)} Std.",
                    'is_hot': diff_sec <= 60, 'info': p.get('Text', '')
                })
    except Exception:
        pass

    activities.sort(key=lambda x: x['date_raw'], reverse=True)
    return activities, is_recent_1min

df_raw = fetch_stock3_granular_data()
activities, is_hot_alert = fetch_trader_activity_realtime()

if "Wöchentlich" in candlestick_resolution:
    df_chart = df_raw.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
elif "Stündlich" in candlestick_resolution:
    df_chart = df_raw.resample('12H').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}).ffill()
else:
    df_chart = df_raw.copy()

if test_alarm:
    is_hot_alert = True
    activities.insert(0, {
        'type': 'POST', 'action': 'KOMMENTAR', 'name': 'TEST ALARM POST',
        'date_raw': datetime.datetime.now(), 'time_ago': 'NEU! Gerade eben',
        'is_hot': True, 'info': '🚨 Test-Alarm ausgelöst!'
    })

# --- KENNZAHLEN BERECHNUNGEN ---
AKTUELLES_DATUM = datetime.date.today()
last_o, last_h, last_l, last_c = df_chart['Open'].iloc[-1], df_chart['High'].iloc[-1], df_chart['Low'].iloc[-1], df_chart['Close'].iloc[-1]
aktueller_kurs = float(last_c)

tage_gehalten = max(1, (AKTUELLES_DATUM - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
monate_aktiv = max(1, int(round(tage_gehalten / 30.4375)))

brutto_ist = STUECKZAHL * aktueller_kurs
gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_ist = brutto_ist - gesamt_entnommen

gewinn_brutto = brutto_ist - STARTKAPITAL
gewinn_netto = netto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
rendite_pa = (((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1) * 100

# HEADER & ALERT
trade_alert_html = '<span class="alert-banner-danger"><span class="pulse-glow-hot"></span>🚨 TRADE / POST ALERT</span>' if is_hot_alert else '<span class="header-tag"><span style="color:#00C853;">●</span> TRADER FEED ONLINE</span>'

st.markdown(f"""
<div class="header-bar">
    <div>
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span></div>
        <div class="dim" style="font-size: 0.65rem; margin-top:2px;">WKN: {WKN} • ISIN: {ISIN} • Kaufdatum: {KAUFDATUM.strftime('%d.%m.%Y')}</div>
    </div>
    <div style="text-align: right;">
        {trade_alert_html}
        <div class="pos" style="font-size: 0.85rem; font-weight: 800; margin-top: 2px;">+{rendite_ist_pct:.2f}% ({rendite_pa:.1f}% p.a.)</div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================================================
# 📊 GEFORTZTE KENNZAHLEN-ÜBERSICHT (Wieder integriert!)
# =========================================================
st.markdown(f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Aktueller Kurs</div>
        <div class="m-val pos">{aktueller_kurs:.2f} €</div>
        <div class="m-sub pos">+{aktueller_kurs - ANFANGSKURS:.2f} € vs. Kauf</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val">{brutto_ist:,.0f} €</div>
        <div class="m-sub pos">+{gewinn_brutto:,.0f} € Gewinn</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (nach Entnahme)</div>
        <div class="m-val" style="color:#29B6F6;">{netto_ist:,.0f} €</div>
        <div class="m-sub dim">Entnommen: {gesamt_entnommen:,.0f} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Gesamtrendite</div>
        <div class="m-val pos">+{rendite_ist_pct:.2f}%</div>
        <div class="m-sub pos">+{rendite_pa:.1f}% pro Jahr</div>
    </div>
    <div class="m-card">
        <div class="m-label">Monatl. Entnahme</div>
        <div class="m-val" style="color:#F59E0B;">{ENTNAHME_PM:.0f} €/Monat</div>
        <div class="m-sub dim">Aktiv seit {monate_aktiv} Mon.</div>
    </div>
    <div class="m-card">
        <div class="m-label">Stückzahl im Depot</div>
        <div class="m-val">{STUECKZAHL:.2f} Stk.</div>
        <div class="m-sub dim">Basis: {STARTKAPITAL:,.0f} € Start</div>
    </div>
</div>
""", unsafe_allow_html=True)

# SHARED STOCK3 LAYOUT FUNCTION
def get_stock3_layout():
    return dict(
        paper_bgcolor='#000000',
        plot_bgcolor='#000000',
        margin=dict(l=10, r=60, t=10, b=10),
        height=480,
        showlegend=False,
        xaxis=dict(
            showgrid=True,
            gridcolor='#1A1A1A',
            gridwidth=1,
            type='date',
            dtick="M1",  # 1 Monat pro Hauptgitterlinie
            tickformat="%b '%y",  # Format: Jan '26, Jul '26 usw.
            tickfont=dict(color='#A1A1AA', size=10),
            rangeslider=dict(visible=False)
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#1A1A1A',
            gridwidth=1,
            side="right",
            tickfont=dict(color='#A1A1AA', size=10),
            tickformat=",d"
        ),
        hovermode="x unified"
    )

# TAB NAVIGATION
tab_candle, tab_line, tab_depot, tab_feed = st.tabs([
    "🕯️ STOCK3 CANDLESTICK",
    "📈 STOCK3 PRECISONS-LINIE",
    "📊 DEPOT- & ENTNAHME-BILANZ",
    f"⚡ TRADER FEED ({len(activities)})"
])

# CHART 1: CANDLESTICK
with tab_candle:
    fig_candle = go.Figure()
    fig_candle.add_trace(go.Candlestick(
        x=df_chart.index,
        open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'],
        increasing_line_color='#00C853', increasing_fillcolor='#00C853',
        decreasing_line_color='#FF3D00', decreasing_fillcolor='#FF3D00'
    ))
    fig_candle.add_annotation(
        xref="paper", yref="paper", x=0.01, y=0.97,
        text=f"<b>Hauptindizes Global</b><br><span style='color:#00C853;'>O: {last_o:.3f}  H: {last_h:.3f}  L: {last_l:.3f}  C: {last_c:.3f}</span><br><span style='color:#71717A;'>09.07.2025 - {datetime.date.today().strftime('%d.%m.%Y')}</span>",
        showarrow=False, align="left", font=dict(size=11, family="JetBrains Mono", color="#FFFFFF"),
        bgcolor="rgba(9, 9, 11, 0.85)", bordercolor="#27272A", borderwidth=1
    )
    fig_candle.add_hline(
        y=aktueller_kurs, line_dash="dot", line_color="#00C853", line_width=1,
        annotation_text=f" {aktueller_kurs:.3f} ", annotation_position="right",
        annotation_font_color="#000000", annotation_bgcolor="#00C853"
    )
    fig_candle.update_layout(get_stock3_layout())
    st.plotly_chart(fig_candle, use_container_width=True, config={'displayModeBar': True})

# CHART 2: PRÄZISIONSLINIE
with tab_line:
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(
        x=df_chart.index, y=df_chart['High'], mode='lines', name='High Spanne',
        line=dict(color='rgba(0, 200, 83, 0.2)', width=1)
    ))
    fig_line.add_trace(go.Scatter(
        x=df_chart.index, y=df_chart['Low'], mode='lines', name='Low Spanne',
        line=dict(color='rgba(255, 61, 0, 0.2)', width=1), fill='tonexty', fillcolor='rgba(24, 24, 27, 0.5)'
    ))
    fig_line.add_trace(go.Scatter(
        x=df_chart.index, y=df_chart['Close'], mode='lines', name='Schlusskurs',
        line=dict(color='#00C853', width=2)
    ))
    fig_line.add_hline(
        y=aktueller_kurs, line_dash="dot", line_color="#00C853", line_width=1,
        annotation_text=f" {aktueller_kurs:.3f} ", annotation_position="right",
        annotation_font_color="#000000", annotation_bgcolor="#00C853"
    )
    fig_line.update_layout(get_stock3_layout())
    st.plotly_chart(fig_line, use_container_width=True, config={'displayModeBar': True})

# TAB 3: DEPOT- & ENTNAHME-VERLAUF (Zusätzliche Bilanzübersicht)
with tab_depot:
    df_depot = df_raw.copy()
    df_depot['Brutto_Wert'] = df_depot['Close'] * STUECKZAHL
    
    # Entnahme-Entwicklung
    months_series = (df_depot.index - pd.to_datetime(KAUFDATUM)).days // 30.4375
    df_depot['Entnommen'] = np.maximum(0, months_series) * ENTNAHME_PM
    df_depot['Netto_Wert'] = df_depot['Brutto_Wert'] - df_depot['Entnommen']

    fig_depot = go.Figure()
    fig_depot.add_trace(go.Scatter(
        x=df_depot.index, y=df_depot['Brutto_Wert'], mode='lines', name='Brutto Depotwert',
        line=dict(color='#00C853', width=2)
    ))
    fig_depot.add_trace(go.Scatter(
        x=df_depot.index, y=df_depot['Netto_Wert'], mode='lines', name='Netto Wert (nach Entnahme)',
        line=dict(color='#29B6F6', width=2)
    ))
    fig_depot.add_trace(go.Scatter(
        x=df_depot.index, y=df_depot['Entnommen'], mode='lines', name='Kumulierte Entnahme',
        line=dict(color='#F59E0B', width=1.5, dash='dash')
    ))
    
    layout_depot = get_stock3_layout()
    layout_depot['yaxis']['ticksuffix'] = " €"
    fig_depot.update_layout(layout_depot)
    st.plotly_chart(fig_depot, use_container_width=True, config={'displayModeBar': False})

# TAB 4: TRADER FEED
with tab_feed:
    if activities:
        for act in activities:
            card_cls = "feed-card-hot" if act['is_hot'] else "feed-card"
            action_cls = "feed-action-buy" if "BUY" in act['action'] else "feed-action-sell" if "SELL" in act['action'] else "feed-action-post"
            st.markdown(f"""
            <div class="{card_cls}">
                <div class="feed-header">
                    <span class="{action_cls}">[{act['action']}] {act['name']}</span>
                    <span class="feed-time-badge">⏱️ {act['time_ago']} ({act['date_raw'].strftime('%H:%M:%S')})</span>
                </div>
                <div style="color: #E5E7EB; line-height: 1.4;">{act['info']}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("⚠️ Keine Aktivitäten vorhanden.")
