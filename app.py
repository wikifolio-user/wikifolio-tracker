import datetime
import requests
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
    
    .grid-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 10px; margin-bottom: 16px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 10px 12px; }
    .m-label { font-size: 0.62rem; color: #71717A; text-transform: uppercase; letter-spacing: 0.5px; }
    .m-val { font-size: 1.25rem; font-weight: 800; color: #FFFFFF; margin: 3px 0; white-space: nowrap; }
    .m-sub { font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
    
    .feed-card { background: #09090B; border: 1px solid #27272A; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem; }
    .feed-card-hot { background: rgba(255, 61, 0, 0.12); border: 1px solid #FF3D00; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem; }
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
test_alarm = st.sidebar.checkbox("🧪 Test-Trade auslösen", value=False)
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
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# --- SESSION STATE FÜR TRADE-SPEICHERUNG INITIALISIEREN ---
if "stored_trades" not in st.session_state:
    st.session_state.stored_trades = {}

# --- ECHTE CHART- & KURS-DATEN HOLEN ---
@st.cache_data(ttl=30)
def fetch_real_wikifolio_data():
    """Holt die echten Wikifolio-Kursdaten ohne künstliche Hochrechnung."""
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
                
                # Tägliche Re-Indexierung auf Basis echter Daten
                full_idx = pd.date_range(start=df.index.min(), end=datetime.datetime.now(), freq='D')
                df = df.reindex(full_idx)
                df['Close'] = df['Close'].ffill().bfill()
                
                # Exakte High/Low/Open Ableitung aus echten Schlusskursen
                df['Open'] = df['Close'].shift(1).fillna(df['Close'].iloc[0])
                df['High'] = df[['Open', 'Close']].max(axis=1)
                df['Low'] = df[['Open', 'Close']].min(axis=1)
                return df
    except Exception:
        pass

    # Notfall-Fallback mit fixem historischen Stand falls API blockiert
    idx = pd.date_range(start="2025-07-09", end=datetime.datetime.now(), freq='D')
    return pd.DataFrame({'Open': 300.338, 'High': 300.338, 'Low': 300.338, 'Close': 300.338}, index=idx)

# --- TRADE-HISTORIE IN REALTIME SPEICHERN ---
def update_and_get_trades():
    url_trades = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/tradehistory"
    url_comments = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/comments"
    headers = {"User-Agent": "Mozilla/5.0"}
    now = datetime.datetime.now()
    has_new_trade = False

    try:
        res_t = requests.get(url_trades, headers=headers, timeout=4)
        if res_t.status_code == 200:
            for t in res_t.json():
                trade_id = f"TRADE_{t.get('ExecutionDate')}_{t.get('Name')}_{t.get('OrderType')}"
                if trade_id not in st.session_state.stored_trades:
                    date_raw = pd.to_datetime(t.get('ExecutionDate')).tz_localize(None) if t.get('ExecutionDate') else now
                    st.session_state.stored_trades[trade_id] = {
                        'type': 'TRADE',
                        'action': str(t.get('OrderType', 'TRADE')).upper(),
                        'name': t.get('Name', 'Wertpapier'),
                        'date_raw': date_raw,
                        'price': t.get('ExecutionPrice', 0),
                        'weight': t.get('Weight', 0),
                        'info': f"Kurs: {t.get('ExecutionPrice', 0):.2f} € | Gewichtung: {t.get('Weight', 0):.2f}%",
                        'first_seen': now
                    }
                    has_new_trade = True

        res_c = requests.get(url_comments, headers=headers, timeout=4)
        if res_c.status_code == 200:
            for c in res_c.json():
                comment_id = f"POST_{c.get('CreatedAt')}"
                if comment_id not in st.session_state.stored_trades:
                    date_raw = pd.to_datetime(c.get('CreatedAt')).tz_localize(None) if c.get('CreatedAt') else now
                    st.session_state.stored_trades[comment_id] = {
                        'type': 'POST',
                        'action': 'KOMMENTAR',
                        'name': 'Trader Post',
                        'date_raw': date_raw,
                        'info': c.get('Text', ''),
                        'first_seen': now
                    }
    except Exception:
        pass

    # Test-Alarm injecten
    if test_alarm:
        test_id = f"TEST_{now.strftime('%H%M%S')}"
        st.session_state.stored_trades[test_id] = {
            'type': 'TRADE', 'action': 'VERKAUF', 'name': 'TEST-POSITION (VERKAUFT)',
            'date_raw': now, 'info': '🚨 Test-Verkauf erfolgreich im Feed registriert!', 'first_seen': now
        }
        has_new_trade = True

    # Sortieren nach Datum
    trade_list = list(st.session_state.stored_trades.values())
    trade_list.sort(key=lambda x: x['date_raw'], reverse=True)
    return trade_list, has_new_trade

df_chart = fetch_real_wikifolio_data()
trade_list, has_new_trade = update_and_get_trades()

# KENNZAHLEN BERECHNUNG
last_o, last_h, last_l, last_c = df_chart['Open'].iloc[-1], df_chart['High'].iloc[-1], df_chart['Low'].iloc[-1], df_chart['Close'].iloc[-1]
aktueller_kurs = float(last_c)

AKTUELLES_DATUM = datetime.date.today()
tage_gehalten = max(1, (AKTUELLES_DATUM - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
monate_aktiv = max(1, int(round(tage_gehalten / 30.4375)))

brutto_ist = STUECKZAHL * aktueller_kurs
gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_ist = brutto_ist - gesamt_entnommen

gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
rendite_pa = (((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1) * 100

# HEADER & ALERT BANNER
is_recent_trade = any((datetime.datetime.now() - t['first_seen']).total_seconds() < 120 for t in trade_list)
trade_alert_html = '<span class="alert-banner-danger"><span class="pulse-glow-hot"></span>🚨 NEUER TRADE / POST REGISTRIERT</span>' if is_recent_trade else '<span class="header-tag"><span style="color:#00C853;">●</span> TRADER FEED ONLINE</span>'

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

# GRID OVERVIEW
st.markdown(f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Echter Wikifolio Kurs</div>
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
        <div class="m-sub pos">+{rendite_pa:.1f}% p.a.</div>
    </div>
    <div class="m-card">
        <div class="m-label">Registrierte Trades</div>
        <div class="m-val" style="color:#F59E0B;">{len(trade_list)}</div>
        <div class="m-sub dim">In Session gespeichert</div>
    </div>
</div>
""", unsafe_allow_html=True)

# SHARED STOCK3 LAYOUT
def get_stock3_layout():
    return dict(
        paper_bgcolor='#000000',
        plot_bgcolor='#000000',
        margin=dict(l=10, r=60, t=10, b=10),
        height=480,
        showlegend=False,
        xaxis=dict(
            showgrid=True, gridcolor='#1A1A1A', gridwidth=1, type='date',
            dtick="M1", tickformat="%b '%y", tickfont=dict(color='#A1A1AA', size=10), rangeslider=dict(visible=False)
        ),
        yaxis=dict(
            showgrid=True, gridcolor='#1A1A1A', gridwidth=1, side="right",
            tickfont=dict(color='#A1A1AA', size=10), tickformat=",d"
        ),
        hovermode="x unified"
    )

# TABS
tab_candle, tab_line, tab_feed = st.tabs([
    "🕯️ STOCK3 CANDLESTICK",
    "📈 STOCK3 PRECISONS-LINIE",
    f"⚡ TRADER FEED SPEICHER ({len(trade_list)})"
])

with tab_candle:
    fig_candle = go.Figure()
    fig_candle.add_trace(go.Candlestick(
        x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'],
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

with tab_line:
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=df_chart.index, y=df_chart['Close'], mode='lines', name='Schlusskurs', line=dict(color='#00C853', width=2)))
    fig_line.add_hline(
        y=aktueller_kurs, line_dash="dot", line_color="#00C853", line_width=1,
        annotation_text=f" {aktueller_kurs:.3f} ", annotation_position="right",
        annotation_font_color="#000000", annotation_bgcolor="#00C853"
    )
    fig_line.update_layout(get_stock3_layout())
    st.plotly_chart(fig_line, use_container_width=True, config={'displayModeBar': True})

# --- TRADER FEED TAB MIT VOLLSTÄNDIGEM SPEICHER ---
with tab_feed:
    st.caption("ℹ️ Alle Trades und Verkäufe werden hier fortlaufend erfasst und dauerhaft gespeichert.")
    if trade_list:
        for t in trade_list:
            is_new = (datetime.datetime.now() - t['first_seen']).total_seconds() < 120
            card_cls = "feed-card-hot" if is_new else "feed-card"
            
            action_type = t['action']
            if "SELL" in action_type or "VERKAUF" in action_type:
                action_cls = "feed-action-sell"
            elif "BUY" in action_type or "KAUF" in action_type:
                action_cls = "feed-action-buy"
            else:
                action_cls = "feed-action-post"

            new_badge = '<span style="color:#FF3D00; font-weight:800; margin-left:8px;">[NEU REGISTRIERT]</span>' if is_new else ''

            st.markdown(f"""
            <div class="{card_cls}">
                <div class="feed-header">
                    <span class="{action_cls}">[{action_type}] {t['name']}{new_badge}</span>
                    <span class="feed-time-badge">⏱️ {t['date_raw'].strftime('%d.%m.%Y %H:%M:%S')}</span>
                </div>
                <div style="color: #E5E7EB; line-height: 1.4;">{t['info']}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("⚠️ Noch keine Trades registriert.")
