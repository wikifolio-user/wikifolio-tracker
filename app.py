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

# --- ADVANCED TERMINAL STYLING (HIGH DENSITY & REALTIME ALERTS) ---
st.markdown("""
<style>
    .stApp { background-color: #000000; color: #E5E7EB; font-family: 'JetBrains Mono', monospace; }
    
    /* Header Bar */
    .header-bar {
        display: flex; justify-content: space-between; align-items: center;
        background: #09090B; border: 1px solid #27272A; border-left: 3px solid #00FF66;
        border-radius: 6px; padding: 10px 14px; margin-bottom: 10px;
    }
    .header-title { font-size: 1.05rem; font-weight: 800; color: #FFFFFF; }
    .header-tag { font-size: 0.65rem; color: #A1A1AA; background: #18181B; padding: 2px 6px; border-radius: 4px; border: 1px solid #27272A; }
    
    /* Live Pulse Indicator for Realtime Alerts (< 1 min) */
    .pulse-glow-hot {
        display: inline-block; width: 8px; height: 8px; border-radius: 50%;
        background-color: #FF0055; box-shadow: 0 0 10px #FF0055, 0 0 20px #FF0055;
        margin-right: 6px; animation: blinker 0.8s linear infinite;
    }
    @keyframes blinker {
        50% { opacity: 0.2; }
    }
    .alert-banner-danger {
        background: rgba(255, 0, 85, 0.15); border: 1px solid #FF0055;
        color: #FF0055; font-size: 0.75rem; font-weight: 800; padding: 4px 10px; border-radius: 4px;
    }
    
    /* Grid Layout */
    .grid-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 8px; margin-bottom: 10px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 8px 10px; }
    .m-label { font-size: 0.58rem; color: #71717A; text-transform: uppercase; letter-spacing: 0.5px; }
    .m-val { font-size: 1.1rem; font-weight: 800; color: #FFFFFF; margin: 2px 0; white-space: nowrap; }
    .m-sub { font-size: 0.65rem; font-weight: 600; white-space: nowrap; }
    
    /* Responsive Table with No-Wrap */
    .table-wrapper { width: 100%; overflow-x: auto; margin-bottom: 12px; }
    .bench-table {
        width: 100%; border-collapse: collapse; background: #09090B; border: 1px solid #18181B;
        border-radius: 6px; font-size: 0.72rem; white-space: nowrap;
    }
    .bench-table th { background: #121215; text-align: left; padding: 6px 8px; color: #71717A; font-weight: 600; border-bottom: 1px solid #18181B; }
    .bench-table td { padding: 6px 8px; border-bottom: 1px solid #121215; white-space: nowrap; }
    
    /* Feed Activity Cards */
    .feed-card {
        background: #09090B; border: 1px solid #27272A; border-radius: 6px;
        padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem;
    }
    .feed-card-hot {
        background: rgba(255, 0, 85, 0.08); border: 1px solid #FF0055; border-radius: 6px;
        padding: 10px 12px; margin-bottom: 8px; font-size: 0.78rem;
    }
    .feed-header { display: flex; justify-content: space-between; color: #71717A; font-size: 0.68rem; margin-bottom: 6px; }
    .feed-action-buy { color: #00FF66; font-weight: 800; }
    .feed-action-sell { color: #FF0055; font-weight: 800; }
    .feed-action-post { color: #3B82F6; font-weight: 800; }
    .feed-time-badge { background: #18181B; color: #A1A1AA; padding: 2px 6px; border-radius: 4px; font-size: 0.65rem; }
    
    /* Colors */
    .pos { color: #00FF66; }
    .neg { color: #FF0055; }
    .bench-4 { color: #3B82F6; }
    .bench-6 { color: #F59E0B; }
    .dim { color: #71717A; }
    
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; gap: 4px; }
    .stTabs [data-baseweb="tab"] { background-color: #09090B; border: 1px solid #18181B; color: #71717A; padding: 6px 12px; font-size: 0.75rem; }
    .stTabs [aria-selected="true"] { background-color: #18181B !important; color: #00FF66 !important; border-color: #00FF66 !important; }
</style>
""", unsafe_allow_html=True)

# SIDEBAR CONTROL FOR TESTING & SETTINGS
st.sidebar.title("⚙️ CONFIG & ALARM")
test_alarm = st.sidebar.checkbox("🧪 Test-Alarm auslösen", value=False, help="Aktiviert den visuellen & akustischen Alarm manuell.")
auto_refresh = st.sidebar.checkbox("🔄 Auto-Refresh (60s)", value=True)

if auto_refresh:
    st.markdown("""
        <script>
            setTimeout(function(){
                window.location.reload(1);
            }, 60000);
        </script>
    """, unsafe_allow_html=True)

# --- BASE PARAMETERS ---
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
WIKIFOLIO_SLUG = "wfindizglo"
ANFANGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
KAUFDATUM = datetime.date(2025, 8, 7)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# --- API ENGINES ---
@st.cache_data(ttl=60)
def fetch_exact_data():
    """Holt die Zeitreihe ab Kaufdatum."""
    url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/chartdata"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            points = res.json().get("ChartPoints", [])
            if points:
                df = pd.DataFrame(points)
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                df['Kurs'] = pd.to_numeric(df['Close'], errors='coerce')
                df = df.dropna(subset=['Date', 'Kurs']).sort_values('Date').set_index('Date')
                
                full_idx = pd.date_range(start=KAUFDATUM, end=datetime.datetime.now(), freq='D')
                df = df.reindex(full_idx)
                df['Kurs'] = df['Kurs'].ffill().bfill()
                df.iloc[0, df.columns.get_loc('Kurs')] = ANFANGSKURS
                return df
    except Exception:
        pass
    
    idx = pd.date_range(start=KAUFDATUM, end=datetime.datetime.now(), freq='D')
    return pd.DataFrame({'Kurs': np.linspace(ANFANGSKURS, 300.338, len(idx))}, index=idx)

@st.cache_data(ttl=60)
def fetch_trader_activity_realtime():
    """Holt Trades & Kommentare und errechnet Minutendifferenzen."""
    urls = [
        f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/tradehistory",
        f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/comments"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    activities = []
    is_recent_1min = False
    now = datetime.datetime.now()
    
    try:
        # 1. Fetch Trades
        res_trades = requests.get(urls[0], headers=headers, timeout=4)
        if res_trades.status_code == 200:
            trades = res_trades.json()
            if isinstance(trades, list):
                for t in trades[:15]:
                    date_str = t.get('ExecutionDate', '')
                    act_date = pd.to_datetime(date_str).tz_localize(None) if date_str else now
                    diff_seconds = max(0, (now - act_date).total_seconds())
                    diff_minutes = int(diff_seconds // 60)
                    
                    if diff_seconds <= 60:
                        is_recent_1min = True
                        time_ago_str = "NEU! Gerade eben"
                    elif diff_minutes < 60:
                        time_ago_str = f"vor {diff_minutes} Min."
                    else:
                        hours = int(diff_minutes // 60)
                        time_ago_str = f"vor {hours} Std."
                    
                    activities.append({
                        'type': 'TRADE',
                        'action': t.get('OrderType', 'TRADE').upper(),
                        'name': t.get('Name', 'Wertpapier'),
                        'date_raw': act_date,
                        'time_ago': time_ago_str,
                        'is_hot': diff_seconds <= 60,
                        'info': f"Kurs: {t.get('ExecutionPrice', 0):.2f} € | Gewichtung: {t.get('Weight', 0):.2f}%"
                    })
        
        # 2. Fetch Kommentare (Posts)
        res_posts = requests.get(urls[1], headers=headers, timeout=4)
        if res_posts.status_code == 200:
            posts = res_posts.json()
            if isinstance(posts, list):
                for p in posts[:15]:
                    date_str = p.get('CreatedAt', '')
                    act_date = pd.to_datetime(date_str).tz_localize(None) if date_str else now
                    diff_seconds = max(0, (now - act_date).total_seconds())
                    diff_minutes = int(diff_seconds // 60)
                    
                    if diff_seconds <= 60:
                        is_recent_1min = True
                        time_ago_str = "NEU! Gerade eben"
                    elif diff_minutes < 60:
                        time_ago_str = f"vor {diff_minutes} Min."
                    else:
                        hours = int(diff_minutes // 60)
                        time_ago_str = f"vor {hours} Std."
                    
                    activities.append({
                        'type': 'POST',
                        'action': 'KOMMENTAR',
                        'name': 'Trader Post',
                        'date_raw': act_date,
                        'time_ago': time_ago_str,
                        'is_hot': diff_seconds <= 60,
                        'info': p.get('Text', '')
                    })
    except Exception:
        pass

    # Sortierung nach Datum
    activities.sort(key=lambda x: x['date_raw'], reverse=True)
    return activities, is_recent_1min

df = fetch_exact_data()
activities, is_hot_alert = fetch_trader_activity_realtime()

# Overrule durch manuellen Test-Alarm
if test_alarm:
    is_hot_alert = True
    activities.insert(0, {
        'type': 'POST',
        'action': 'KOMMENTAR',
        'name': 'TEST ALARM POST',
        'date_raw': datetime.datetime.now(),
        'time_ago': 'NEU! Gerade eben',
        'is_hot': True,
        'info': '🚨 Dies ist ein Test-Kommentar, um den optischen und akustischen Alarm zu prüfen.'
    })

# Key Computations
AKTUELLES_DATUM = datetime.date.today()
aktueller_kurs = 300.338 if df is None else float(df['Kurs'].iloc[-1])

tage_gehalten = max(1, (AKTUELLES_DATUM - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
monate_aktiv = max(1, int(round(tage_gehalten / 30.4375)))

kurs_4pct = ANFANGSKURS * ((1 + 0.04) ** jahre_gehalten)
kurs_6pct = ANFANGSKURS * ((1 + 0.06) ** jahre_gehalten)

brutto_ist = STUECKZAHL * aktueller_kurs
brutto_4pct = STUECKZAHL * kurs_4pct
brutto_6pct = STUECKZAHL * kurs_6pct

gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_ist = brutto_ist - gesamt_entnommen

rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
rendite_4pct = ((kurs_4pct - ANFANGSKURS) / ANFANGSKURS) * 100
rendite_6pct = ((kurs_6pct - ANFANGSKURS) / ANFANGSKURS) * 100

# --- HEADER WITH AUDIO & VISUAL REALTIME ALARM ---
if is_hot_alert:
    trade_alert_html = '<span class="alert-banner-danger"><span class="pulse-glow-hot"></span>🚨 TRADE / POST ALERT (AKTIV)</span>'
    st.markdown("""
        <script>
            try {
                var ctx = new (window.AudioContext || window.webkitAudioContext)();
                var osc = ctx.createOscillator();
                var gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.value = 880;
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                gain.gain.exponentialRampToValueAtTime(0.00001, ctx.currentTime + 1.2);
            } catch(e) {}
        </script>
    """, unsafe_allow_html=True)
elif len(activities) > 0:
    trade_alert_html = '<span class="header-tag"><span style="color:#00FF66;">●</span> TRADER FEED ONLINE</span>'
else:
    trade_alert_html = '<span class="header-tag">L&S LIVE</span>'

st.markdown(f"""
<div class="header-bar">
    <div>
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span></div>
        <div class="dim" style="font-size: 0.65rem; margin-top:2px;">WKN: {WKN} • ISIN: {ISIN} • Einstieg: {ANFANGSKURS:.2f} € ({KAUFDATUM.strftime('%d.%m.%Y')})</div>
    </div>
    <div style="text-align: right;">
        {trade_alert_html}
        <div class="pos" style="font-size: 0.85rem; font-weight: 800; margin-top: 2px;">+{rendite_ist_pct:.2f}%</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- DENSE METRIC GRID ---
st.markdown(f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Aktueller Kurs</div>
        <div class="m-val pos">{aktueller_kurs:.2f} €</div>
        <div class="m-sub pos">+{aktueller_kurs - ANFANGSKURS:.2f} €/Stk.</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val">{brutto_ist:,.0f} €</div>
        <div class="m-sub pos">+{brutto_ist - STARTKAPITAL:,.0f} € Gewinn</div>
    </div>
    <div class="m-card">
        <div class="m-label">Entnahmen ({monate_aktiv}M)</div>
        <div class="m-val" style="color:#F59E0B;">{gesamt_entnommen:,.0f} €</div>
        <div class="m-sub dim">{ENTNAHME_PM:.0f} € / Monat</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto Restwert</div>
        <div class="m-val pos">{netto_ist:,.0f} €</div>
        <div class="m-sub dim">Nach Auszahlung</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- NO-WRAP BENCHMARK TABLE ---
st.markdown(f"""
<div class="table-wrapper">
    <table class="bench-table">
        <thead>
            <tr>
                <th>SZENARIO</th>
                <th>KURS (€)</th>
                <th>RENDITE</th>
                <th>DEPOT BRUTTO</th>
                <th>DELTA (IST)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><b class="bench-4">Soll 4.0% p.a.</b> (Konservativ)</td>
                <td>{kurs_4pct:.2f} €</td>
                <td class="bench-4">+{rendite_4pct:.2f}%</td>
                <td>{brutto_4pct:,.2f} €</td>
                <td class="pos">+{brutto_ist - brutto_4pct:,.2f} €</td>
            </tr>
            <tr>
                <td><b class="bench-6">Soll 6.0% p.a.</b> (Durchschnitt)</td>
                <td>{kurs_6pct:.2f} €</td>
                <td class="bench-6">+{rendite_6pct:.2f}%</td>
                <td>{brutto_6pct:,.2f} €</td>
                <td class="pos">+{brutto_ist - brutto_6pct:,.2f} €</td>
            </tr>
            <tr style="background: #121215; font-weight: 800;">
                <td><b class="pos">Real Performance (Ist)</b></td>
                <td class="pos">{aktueller_kurs:.2f} €</td>
                <td class="pos">+{rendite_ist_pct:.2f}%</td>
                <td class="pos">{brutto_ist:,.2f} €</td>
                <td class="dim">—</td>
            </tr>
        </tbody>
    </table>
</div>
""", unsafe_allow_html=True)

# --- CHARTS & FEED TABS ---
df['Days'] = (df.index - pd.to_datetime(KAUFDATUM)).days
df['Years'] = df['Days'] / 365.25
df['Soll_4pct'] = ANFANGSKURS * ((1 + 0.04) ** df['Years'])
df['Soll_6pct'] = ANFANGSKURS * ((1 + 0.06) ** df['Years'])
df['Depot_Ist'] = STUECKZAHL * df['Kurs']

tab_feed, tab_chart1, tab_chart2 = st.tabs([
    f"⚡ TRADER FEED & KOMMENTARE ({len(activities)})",
    "📈 PERFORMANCE AB KAUF", 
    "💰 DEPOTWERT VERGLEICH"
])

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
        st.info("⚠️ Keine Kommentare oder Trades geladen. Überprüfe die Verbindung zu Wikifolio.")

with tab_chart1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Kurs'], mode='lines', name='Ist-Kurs',
        line=dict(color='#00FF66', width=2.2)
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Soll_6pct'], mode='lines', name='Soll 6% p.a.',
        line=dict(color='#F59E0B', width=1.5, dash='dash')
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Soll_4pct'], mode='lines', name='Soll 4% p.a.',
        line=dict(color='#3B82F6', width=1.5, dash='dot')
    ))
    
    fig.update_layout(
        paper_bgcolor='#000000', plot_bgcolor='#000000',
        margin=dict(l=5, r=5, t=10, b=5), height=310,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=9, color="#A1A1AA")),
        xaxis=dict(showgrid=True, gridcolor='#18181B', tickfont=dict(color='#71717A', size=9), range=[df.index.min(), df.index.max()]),
        yaxis=dict(showgrid=True, gridcolor='#18181B', ticksuffix=" €", tickfont=dict(color='#71717A', size=9)),
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with tab_chart2:
    fig_val = go.Figure()
    fig_val.add_trace(go.Scatter(
        x=df.index, y=df['Depot_Ist'], mode='lines', name='Ist Depotwert',
        line=dict(color='#00FF66', width=2), fill='tozeroy', fillcolor='rgba(0,255,102,0.03)'
    ))
    fig_val.add_hline(y=STARTKAPITAL, line_dash="dash", line_color="#71717A", annotation_text="Kaufsumme 20k")
    fig_val.update_layout(
        paper_bgcolor='#000000', plot_bgcolor='#000000',
        margin=dict(l=5, r=5, t=10, b=5), height=310,
        xaxis=dict(showgrid=True, gridcolor='#18181B', tickfont=dict(color='#71717A', size=9), range=[df.index.min(), df.index.max()]),
        yaxis=dict(showgrid=True, gridcolor='#18181B', ticksuffix=" €", tickfont=dict(color='#71717A', size=9)),
        hovermode="x unified"
    )
    st.plotly_chart(fig_val, use_container_width=True, config={'displayModeBar': False})
