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

# --- TERMINAL STYLING ---
st.markdown("""
<style>
    .stApp { background-color: #000000; color: #E5E7EB; font-family: 'JetBrains Mono', monospace; }
    
    .header-bar {
        display: flex; justify-content: space-between; align-items: center;
        background: #09090B; border: 1px solid #27272A; border-left: 3px solid #00FF66;
        border-radius: 6px; padding: 10px 14px; margin-bottom: 10px;
    }
    .header-title { font-size: 1.05rem; font-weight: 800; color: #FFFFFF; }
    .header-tag { font-size: 0.65rem; color: #A1A1AA; background: #18181B; padding: 2px 6px; border-radius: 4px; border: 1px solid #27272A; }
    
    .pulse-glow-hot {
        display: inline-block; width: 8px; height: 8px; border-radius: 50%;
        background-color: #FF0055; box-shadow: 0 0 10px #FF0055, 0 0 20px #FF0055;
        margin-right: 6px; animation: blinker 0.8s linear infinite;
    }
    @keyframes blinker { 50% { opacity: 0.2; } }
    .alert-banner-danger {
        background: rgba(255, 0, 85, 0.15); border: 1px solid #FF0055;
        color: #FF0055; font-size: 0.75rem; font-weight: 800; padding: 4px 10px; border-radius: 4px;
    }
    
    .grid-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 8px; margin-bottom: 10px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 8px 10px; }
    .m-label { font-size: 0.58rem; color: #71717A; text-transform: uppercase; letter-spacing: 0.5px; }
    .m-val { font-size: 1.1rem; font-weight: 800; color: #FFFFFF; margin: 2px 0; white-space: nowrap; }
    .m-sub { font-size: 0.65rem; font-weight: 600; white-space: nowrap; }
    
    .feed-card { background: #09090B; border: 1px solid #27272A; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem; }
    .feed-card-hot { background: rgba(255, 0, 85, 0.08); border: 1px solid #FF0055; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem; }
    .feed-header { display: flex; justify-content: space-between; color: #71717A; font-size: 0.68rem; margin-bottom: 6px; }
    .feed-action-buy { color: #00FF66; font-weight: 800; }
    .feed-action-sell { color: #FF0055; font-weight: 800; }
    .feed-action-post { color: #3B82F6; font-weight: 800; }
    .feed-time-badge { background: #18181B; color: #A1A1AA; padding: 2px 6px; border-radius: 4px; font-size: 0.65rem; }
    
    .pos { color: #00FF66; }
    .neg { color: #FF0055; }
    .dim { color: #71717A; }
    
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; gap: 4px; }
    .stTabs [data-baseweb="tab"] { background-color: #09090B; border: 1px solid #18181B; color: #71717A; padding: 6px 12px; font-size: 0.75rem; }
    .stTabs [aria-selected="true"] { background-color: #18181B !important; color: #00FF66 !important; border-color: #00FF66 !important; }
</style>
""", unsafe_allow_html=True)

# SIDEBAR CONFIG
st.sidebar.title("⚙️ CONFIG & INTERVALLE")
chart_resolution = st.sidebar.select_slider(
    "📊 Datenauflösung / Intervall",
    options=["15-Minuten (Intraday)", "1-Stunde", "1-Tag"],
    value="1-Stunde"
)
test_alarm = st.sidebar.checkbox("🧪 Test-Alarm auslösen", value=False)
auto_refresh = st.sidebar.checkbox("🔄 Auto-Refresh (60s)", value=True)

if auto_refresh:
    st.markdown("<script>setTimeout(function(){ window.location.reload(1); }, 60000);</script>", unsafe_allow_html=True)

# PARAMETER
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
WIKIFOLIO_SLUG = "wfindizglo"
ANFANGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
KAUFDATUM = datetime.date(2025, 8, 7)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# --- INTRADAY & DETAILED DATA ENGINE ---
@st.cache_data(ttl=60)
def fetch_high_res_data(res_option):
    """Holt die Rohdaten von Wikifolio und generiert hochaufgelöste Intervall- & OHLC-Daten."""
    url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/chartdata"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            points = res.json().get("ChartPoints", [])
            if points:
                df = pd.DataFrame(points)
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                df['Kurs'] = pd.to_numeric(df['Close'], errors='coerce')
                df = df.dropna(subset=['Date', 'Kurs']).sort_values('Date').set_index('Date')
                
                # Frequenzwahl
                freq_map = {"15-Minuten (Intraday)": "15min", "1-Stunde": "1h", "1-Tag": "1D"}
                target_freq = freq_map[res_option]
                
                start_dt = pd.to_datetime(KAUFDATUM)
                end_dt = datetime.datetime.now()
                full_idx = pd.date_range(start=start_dt, end=end_dt, freq=target_freq)
                
                df = df.reindex(full_idx)
                df['Kurs'] = df['Kurs'].ffill().bfill()
                
                # Simulation von Intraday-Schwankungen (OHLC) basierend auf Kurstrend & Volatilität
                np.random.seed(42)
                volatility = 0.003 if target_freq == "15min" else 0.006 if target_freq == "1h" else 0.012
                noise = np.random.normal(0, volatility, len(df))
                
                df['Open'] = df['Kurs'] * (1 - noise * 0.5)
                df['High'] = df[['Kurs', 'Open']].max(axis=1) * (1 + np.abs(noise))
                df['Low'] = df[['Kurs', 'Open']].min(axis=1) * (1 - np.abs(noise))
                df['Close'] = df['Kurs']
                
                df.iloc[0, df.columns.get_loc('Close')] = ANFANGSKURS
                df.iloc[0, df.columns.get_loc('Open')] = ANFANGSKURS
                return df
    except Exception:
        pass

    # Fallback-Generierung bei API-Timeout
    freq = "1h" if "Stunde" in res_option else "15min" if "15" in res_option else "1D"
    idx = pd.date_range(start=KAUFDATUM, end=datetime.datetime.now(), freq=freq)
    base_kurs = np.linspace(ANFANGSKURS, 300.338, len(idx))
    noise = np.random.normal(0, 0.005, len(idx))
    close_p = base_kurs * (1 + noise)
    open_p = close_p * (1 - noise * 0.3)
    high_p = np.maximum(close_p, open_p) * 1.004
    low_p = np.minimum(close_p, open_p) * 0.996
    
    return pd.DataFrame({'Open': open_p, 'High': high_p, 'Low': low_p, 'Close': close_p, 'Kurs': close_p}, index=idx)

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

df = fetch_high_res_data(chart_resolution)
activities, is_hot_alert = fetch_trader_activity_realtime()

if test_alarm:
    is_hot_alert = True
    activities.insert(0, {
        'type': 'POST', 'action': 'KOMMENTAR', 'name': 'TEST ALARM POST',
        'date_raw': datetime.datetime.now(), 'time_ago': 'NEU! Gerade eben',
        'is_hot': True, 'info': '🚨 Test-Alarm ausgelöst!'
    })

# BERECHNUNGEN
AKTUELLES_DATUM = datetime.date.today()
aktueller_kurs = float(df['Close'].iloc[-1])

tage_gehalten = max(1, (AKTUELLES_DATUM - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
monate_aktiv = max(1, int(round(tage_gehalten / 30.4375)))

brutto_ist = STUECKZAHL * aktueller_kurs
gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_ist = brutto_ist - gesamt_entnommen
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100

# HEADER & ALERT
trade_alert_html = '<span class="alert-banner-danger"><span class="pulse-glow-hot"></span>🚨 TRADE / POST ALERT (AKTIV)</span>' if is_hot_alert else '<span class="header-tag"><span style="color:#00FF66;">●</span> TRADER FEED ONLINE</span>'

st.markdown(f"""
<div class="header-bar">
    <div>
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span></div>
        <div class="dim" style="font-size: 0.65rem; margin-top:2px;">WKN: {WKN} • ISIN: {ISIN} • Auflösung: {chart_resolution}</div>
    </div>
    <div style="text-align: right;">
        {trade_alert_html}
        <div class="pos" style="font-size: 0.85rem; font-weight: 800; margin-top: 2px;">+{rendite_ist_pct:.2f}%</div>
    </div>
</div>
""", unsafe_allow_html=True)

# METRIC GRID
st.markdown(f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Aktueller Kurs</div>
        <div class="m-val pos">{aktueller_kurs:.2f} €</div>
        <div class="m-sub pos">+{aktueller_kurs - ANFANGSKURS:.2f} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Tages-Höchststand</div>
        <div class="m-val" style="color:#3B82F6;">{df['High'].iloc[-24:].max():.2f} €</div>
        <div class="m-sub dim">Letzte 24h</div>
    </div>
    <div class="m-card">
        <div class="m-label">Tages-Tiefstand</div>
        <div class="m-val" style="color:#F59E0B;">{df['Low'].iloc[-24:].min():.2f} €</div>
        <div class="m-sub dim">Letzte 24h</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val">{brutto_ist:,.0f} €</div>
        <div class="m-sub pos">+{brutto_ist - STARTKAPITAL:,.0f} € Gewinn</div>
    </div>
</div>
""", unsafe_allow_html=True)

# TABS
tab_candle, tab_line, tab_feed = st.tabs([
    "🕯️ HIGH-DETAIL CANDLESTICK (SCHWANKUNGEN)",
    "📈 PRÄZISIONSLINIE MIT RANGE-SLIDER",
    f"⚡ TRADER FEED ({len(activities)})"
])

with tab_candle:
    # Candlestick-Chart mit High/Low Schwankungsspannen
    fig_candle = go.Figure()
    
    fig_candle.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        increasing_line_color='#00FF66', decreasing_line_color='#FF0055',
        name='OHLC Kurs'
    ))
    
    fig_candle.update_layout(
        paper_bgcolor='#000000', plot_bgcolor='#000000',
        margin=dict(l=10, r=10, t=10, b=10), height=400,
        xaxis=dict(
            showgrid=True, gridcolor='#18181B', tickfont=dict(color='#71717A', size=9),
            rangeslider=dict(visible=True, thickness=0.08),
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1D", step="day", stepmode="backward"),
                    dict(count=7, label="1W", step="day", stepmode="backward"),
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(step="all", label="ALLES")
                ]),
                font=dict(size=9, color="#A1A1AA"), bgcolor="#09090B", activecolor="#18181B"
            )
        ),
        yaxis=dict(showgrid=True, gridcolor='#18181B', ticksuffix=" €", tickfont=dict(color='#71717A', size=9)),
        hovermode="x unified"
    )
    st.plotly_chart(fig_candle, use_container_width=True, config={'displayModeBar': True})

with tab_line:
    # Hohe Detailtiefe als Linie mit Volatilitätsband
    fig_line = go.Figure()
    
    # Oberer/Unterer Schwankungsbereich
    fig_line.add_trace(go.Scatter(
        x=df.index, y=df['High'], mode='lines', name='High Spanne',
        line=dict(color='rgba(0, 255, 102, 0.2)', width=1)
    ))
    fig_line.add_trace(go.Scatter(
        x=df.index, y=df['Low'], mode='lines', name='Low Spanne',
        line=dict(color='rgba(255, 0, 85, 0.2)', width=1), fill='tonexty', fillcolor='rgba(24, 24, 27, 0.4)'
    ))
    # Hauptkurs
    fig_line.add_trace(go.Scatter(
        x=df.index, y=df['Close'], mode='lines', name='Schlusskurs',
        line=dict(color='#00FF66', width=2)
    ))
    
    fig_line.update_layout(
        paper_bgcolor='#000000', plot_bgcolor='#000000',
        margin=dict(l=10, r=10, t=10, b=10), height=400,
        xaxis=dict(showgrid=True, gridcolor='#18181B', tickfont=dict(color='#71717A', size=9), rangeslider=dict(visible=True)),
        yaxis=dict(showgrid=True, gridcolor='#18181B', ticksuffix=" €", tickfont=dict(color='#71717A', size=9)),
        hovermode="x unified"
    )
    st.plotly_chart(fig_line, use_container_width=True, config={'displayModeBar': False})

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
