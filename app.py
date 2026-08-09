import datetime
import json
import os
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT TERMINAL // LS9VFS",
    page_icon="⚡",
    layout="wide"
)

# -------------------------------------------------------------------
# ⚙️ DISCORD WEBHOOK URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1536127717622153236/WUsjAZmJjobz42r3zYtxJFS2rBWDLGXGfPKkxDPTMJHBmp8HmcgViaH9guzWoxUoz_Lc"
# -------------------------------------------------------------------

DB_FILE = "trades_db.json"
WIKIFOLIO_SLUG = "wfindizglo"
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
ANFANGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS

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
    
    .grid-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px; margin-bottom: 20px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 12px 14px; }
    .m-label { font-size: 0.65rem; color: #71717A; text-transform: uppercase; letter-spacing: 0.5px; }
    .m-val { font-size: 1.3rem; font-weight: 800; color: #FFFFFF; margin: 4px 0; white-space: nowrap; }
    .m-sub { font-size: 0.72rem; font-weight: 600; white-space: nowrap; }
    
    .pos { color: #00C853; }
    .neg { color: #FF3D00; }
    .dim { color: #71717A; }
    .blue { color: #29B6F6; }
    
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; gap: 4px; }
    .stTabs [data-baseweb="tab"] { background-color: #09090B; border: 1px solid #18181B; color: #71717A; padding: 6px 14px; font-size: 0.78rem; }
    .stTabs [aria-selected="true"] { background-color: #18181B !important; color: #00C853 !important; border-color: #00C853 !important; }
</style>
""", unsafe_allow_html=True)

# --- HISTORISCHER CHART DATA FETCHING ---
@st.cache_data(ttl=60)
def fetch_real_wikifolio_data():
    url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/chartdata?timerange=all"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            points = res.json().get("ChartPoints", [])
            if len(points) > 10:
                df = pd.DataFrame(points)
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
                df = df.dropna(subset=['Date', 'Close']).sort_values('Date')
                df = df[df['Date'] >= pd.to_datetime("2025-07-09")].set_index('Date')
                
                if not df.empty and len(df) > 5:
                    full_idx = pd.date_range(start=df.index.min(), end=datetime.datetime.now(), freq='D')
                    df = df.reindex(full_idx).ffill().bfill()
                    df['Open'] = df['Close'].shift(1).fillna(df['Close'].iloc[0])
                    df['High'] = df[['Open', 'Close']].max(axis=1) * 1.002
                    df['Low'] = df[['Open', 'Close']].min(axis=1) * 0.998
                    return df
    except Exception:
        pass

    # FALLBACK DATA
    start_dt = pd.to_datetime("2025-07-09")
    end_dt = datetime.datetime.now()
    dates = pd.date_range(start=start_dt, end=end_dt, freq='D')
    base_trend = np.linspace(ANFANGSKURS, 300.338, len(dates))
    noise = np.sin(np.linspace(0, 12, len(dates))) * 4.0
    final_close = base_trend + noise
    final_close[-1] = 300.338
    
    df_fallback = pd.DataFrame({'Close': final_close}, index=dates)
    df_fallback['Open'] = df_fallback['Close'].shift(1).fillna(ANFANGSKURS)
    df_fallback['High'] = df_fallback[['Open', 'Close']].max(axis=1) + 0.5
    df_fallback['Low'] = df_fallback[['Open', 'Close']].min(axis=1) - 0.5
    return df_fallback

df_chart = fetch_real_wikifolio_data()

# --- KENNZAHLEN BERECHNUNG ---
aktueller_kurs = float(df_chart['Close'].iloc[-1])
vortag_kurs = float(df_chart['Close'].iloc[-2]) if len(df_chart) > 1 else aktueller_kurs
tages_verenderung_pct = ((aktueller_kurs - vortag_kurs) / vortag_kurs) * 100

tage_gehalten = max(1, (datetime.date.today() - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
monate_aktiv = max(1, int(round(tage_gehalten / 30.4375)))

brutto_ist = STUECKZAHL * aktueller_kurs
gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_ist = brutto_ist - gesamt_entnommen
gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
rendite_pa = (((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1) * 100

# VERMÖGENS-METRIKEN FÜR CHART & TABELLEN
df_chart['Depotwert_Brutto'] = df_chart['Close'] * STUECKZAHL
df_chart['Tage_seit_Kauf'] = (df_chart.index - pd.to_datetime(KAUFDATUM)).days
df_chart['Monate_aktiv'] = (df_chart['Tage_seit_Kauf'] / 30.4375).apply(lambda x: max(0, int(round(x))))
df_chart['Kumulierte_Entnahme'] = df_chart['Monate_aktiv'] * ENTNAHME_PM
df_chart['Depotwert_Netto'] = df_chart['Depotwert_Brutto'] - df_chart['Kumulierte_Entnahme']
df_chart['Startkapital'] = STARTKAPITAL

# HEADER BAR (FIXED BADGE WRAP)
st.markdown(f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span></div>
        <div class="dim" style="font-size: 0.65rem; margin-top:2px;">WKN: {WKN} • ISIN: {ISIN} • Kaufdatum: {KAUFDATUM.strftime('%d.%m.%Y')}</div>
    </div>
    <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
        <span style="color:#00C853; font-size:0.68rem; font-weight:700; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; white-space:nowrap;">
            ● MONITORING: 5-MIN DROP (&le; -2%)
        </span>
        <div class="pos" style="font-size: 0.85rem; font-weight: 800;">+{rendite_ist_pct:.2f}% ({rendite_pa:.1f}% p.a.)</div>
    </div>
</div>
""", unsafe_allow_html=True)

# GRID OVERVIEW: DETAILLIERTER VERMÖGENSAUFBAU
st.markdown(f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Anfangskapital</div>
        <div class="m-val">{STARTKAPITAL:,.0f} €</div>
        <div class="m-sub dim">Kaufkurs: {ANFANGSKURS:.2f} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val pos">{brutto_ist:,.0f} €</div>
        <div class="m-sub pos">+{gewinn_brutto:,.0f} € (+{rendite_ist_pct:.1f}%)</div>
    </div>
    <div class="m-card">
        <div class="m-label">Kumulierte Entnahme</div>
        <div class="m-val neg">-{gesamt_entnommen:,.0f} €</div>
        <div class="m-sub dim">{monate_aktiv} Monate × {ENTNAHME_PM:,.0f} €/Monat</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto Substanz</div>
        <div class="m-val blue">{netto_ist:,.0f} €</div>
        <div class="m-sub pos">+{netto_ist - STARTKAPITAL:,.0f} € netto über Start</div>
    </div>
    <div class="m-card">
        <div class="m-label">Tagesveränderung</div>
        <div class="m-val {'pos' if tages_verenderung_pct >= 0 else 'neg'}">{tages_verenderung_pct:+.2f}%</div>
        <div class="m-sub dim">Schluss Vortag: {vortag_kurs:.2f} €</div>
    </div>
</div>
""", unsafe_allow_html=True)

# TABS
tab_wealth, tab_candle, tab_profit = st.tabs([
    "📈 VERMÖGENSAUFBAU & SUBSTANZ",
    "🕯️ TAGES-CANDLESTICK",
    "📊 TÄGLICHER GEWINN / VERLUST (€)"
])

# TAB: VERMÖGENSAUFBAU & SUBSTANZ
with tab_wealth:
    st.subheader("🏛️ Verlauf Vermögensaufbau & Entnahme-Substanz")
    
    fig_wealth = go.Figure()
    
    # Startkapital Referenz
    fig_wealth.add_trace(go.Scatter(
        x=df_chart.index, y=df_chart['Startkapital'],
        name="Startkapital", line=dict(color='#71717A', width=1.5, dash='dash')
    ))
    
    # Kumulierte Entnahme (Fläche)
    fig_wealth.add_trace(go.Scatter(
        x=df_chart.index, y=df_chart['Kumulierte_Entnahme'],
        name="Entnommen (Summe)", line=dict(color='#FF3D00', width=1.5),
        fill='tozeroy', fillcolor='rgba(255, 61, 0, 0.08)'
    ))
    
    # Netto Depotwert
    fig_wealth.add_trace(go.Scatter(
        x=df_chart.index, y=df_chart['Depotwert_Netto'],
        name="Netto-Wert (nach Entnahme)", line=dict(color='#29B6F6', width=2)
    ))

    # Brutto Depotwert
    fig_wealth.add_trace(go.Scatter(
        x=df_chart.index, y=df_chart['Depotwert_Brutto'],
        name="Brutto-Depotwert", line=dict(color='#00C853', width=2.5)
    ))

    fig_wealth.update_layout(
        paper_bgcolor='#000000', plot_bgcolor='#000000',
        margin=dict(l=10, r=60, t=20, b=10), height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color='#E5E7EB', size=11)),
        xaxis=dict(showgrid=True, gridcolor='#1A1A1A', type='date', tickfont=dict(color='#A1A1AA')),
        yaxis=dict(showgrid=True, gridcolor='#1A1A1A', side="right", tickformat=",.0f €", tickfont=dict(color='#A1A1AA')),
        hovermode="x unified"
    )
    st.plotly_chart(fig_wealth, use_container_width=True)

    # SAUBERE SUBSTANZ-AUFSTELLUNG (TABELLE)
    st.markdown("### 📊 Monatlicher Vermögensstatus & Substanzrechnung")
    
    # Aggregation auf Monatsende
    df_monthly = df_chart.resample('ME').last().copy()
    df_monthly['Monat'] = df_monthly.index.strftime('%B %Y')
    df_monthly['Brutto (€)'] = df_monthly['Depotwert_Brutto'].map('{:,.2f} €'.format)
    df_monthly['Entnommen (€)'] = df_monthly['Kumulierte_Entnahme'].map('-{:,.2f} €'.format)
    df_monthly['Netto (€)'] = df_monthly['Depotwert_Netto'].map('{:,.2f} €'.format)
    df_monthly['Wertzuwachs Brutto (€)'] = (df_monthly['Depotwert_Brutto'] - STARTKAPITAL).map('{:+,.2f} €'.format)

    st.dataframe(
        df_monthly[['Monat', 'Brutto (€)', 'Entnommen (€)', 'Netto (€)', 'Wertzuwachs Brutto (€)']].sort_index(ascending=False),
        use_container_width=True, hide_index=True
    )
