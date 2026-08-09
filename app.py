import datetime
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Wikifolio Terminal Pro",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- MODERN DARK THEME UI ---
st.markdown("""
<style>
    .stApp { background-color: #080B10; color: #E2E8F0; font-family: 'Inter', system-ui, sans-serif; }
    
    .terminal-header {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(30, 41, 59, 0.8));
        border: 1px solid rgba(0, 240, 255, 0.25);
        box-shadow: 0 0 25px rgba(0, 240, 255, 0.1);
        border-radius: 16px;
        padding: 18px 22px;
        margin-bottom: 20px;
    }
    .terminal-title {
        font-size: 1.6rem; font-weight: 900; letter-spacing: -0.5px;
        background: linear-gradient(90deg, #00F0FF, #7000FF, #FF007A);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0;
    }
    .terminal-sub { font-size: 0.75rem; color: #64748B; letter-spacing: 1.5px; text-transform: uppercase; margin-top: 4px; }
    
    .metric-card {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px; padding: 14px 16px; margin-bottom: 12px;
        backdrop-filter: blur(12px);
    }
    .metric-label { font-size: 0.68rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 1px; }
    .metric-val { font-size: 1.4rem; font-weight: 800; color: #F8FAFC; margin: 2px 0; }
    .metric-sub { font-size: 0.78rem; font-weight: 600; }
    
    .pos { color: #00FFA3; }
    .neg { color: #FF0055; }
    .accent { color: #00F0FF; }
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- PORTFOLIO INITIALISIERUNG ---
ISIN = "DE000LS9VFS2"
WIKIFOLIO_ID = "wf000ls9vf"
ANFANGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
KAUFDATUM = datetime.date(2025, 8, 7)

STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# --- MULTI-SOURCE DATA ENGINE ---
@st.cache_data(ttl=180)
def fetch_robust_market_data():
    """Holt Kurse über Yahoo Finance & Lang/Schwarz mit Freitag-Fallback fürs Wochenende."""
    df = None
    source = "Unknown"
    
    # Primary Source: Yahoo Finance mit erweiterten Ticker-Varianten
    tickers = ["LS9VFS.SG", "LS9VFS.F", "LS9VFS.DE", "DE000LS9VFS2.SG"]
    start_buffer = KAUFDATUM - datetime.timedelta(days=10)
    
    for t in tickers:
        try:
            data = yf.Ticker(t).history(start=start_buffer)
            if not data.empty and len(data) > 1:
                df = data[['Close']].copy()
                source = f"Yahoo Finance ({t})"
                break
        except Exception:
            continue

    # Secondary Fallback: Wikifolio REST API
    if df is None or df.empty:
        try:
            url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_ID}/chartdata"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            if res.status_code == 200:
                pts = res.json().get("ChartPoints", [])
                if pts:
                    df = pd.DataFrame(pts)
                    df['Date'] = pd.to_datetime(df['Date'])
                    df.set_index('Date', inplace=True)
                    df = df[['Close']].copy()
                    source = "Wikifolio Core API"
        except Exception:
            pass

    if df is not None and not df.empty:
        # Datumsindex bereinigen
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.sort_index()
        
        # Wochenend- & Feiertagslücken mit dem letzten verfügbaren Kurs (Freitag) auffüllen
        full_idx = pd.date_range(start=df.index.min(), end=datetime.datetime.now(), freq='D')
        df = df.reindex(full_idx)
        df['Close'] = df['Close'].ffill().bfill()
        
        # Filter ab Kaufdatum
        df_filtered = df[df.index.date >= KAUFDATUM].copy()
        if not df_filtered.empty:
            return df_filtered, source
        return df, source

    return None, "No Connection"

df, data_source = fetch_robust_market_data()

# --- METRIKEN BERECHNEN ---
if df is not None and not df.empty:
    aktueller_kurs = float(df['Close'].iloc[-1])
    letztes_datum = df.index[-1].strftime("%d.%m.%Y")
else:
    aktueller_kurs = ANFANGSKURS
    letztes_datum = "N/A"

prozent_entwicklung = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
abs_gewinn_pro_stk = aktueller_kurs - ANFANGSKURS

brutto_depotwert = STUECKZAHL * aktueller_kurs
gesamter_gewinn_eur = brutto_depotwert - STARTKAPITAL

# Entnahmen seit Kaufdatum berechnen
heute = datetime.date.today()
monate_aktiv = max(1, (heute.year - KAUFDATUM.year) * 12 + (heute.month - KAUFDATUM.month))
gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_depotwert = brutto_depotwert - gesamt_entnommen

# --- HEADER ---
st.markdown("""
<div class="terminal-header">
    <div class="terminal-title">QUANT TERMINAL // WIKIFOLIO PERFORMANCE</div>
    <div class="terminal-sub">ISIN: DE000LS9VFS2 • Full Asset Tracking & Cashflow Analysis</div>
</div>
""", unsafe_allow_html=True)

# --- METRIC MATRIX (ROW 1: KURS-DETAILS) ---
c1, c2, c3, c4 = st.columns(4)

sign = "+" if prozent_entwicklung >= 0 else ""
color_class = "pos" if prozent_entwicklung >= 0 else "neg"

with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Anfangskurs (Kauf)</div>
        <div class="metric-val">{ANFANGSKURS:.2f} €</div>
        <div class="metric-sub" style="color: #64748B;">Datum: {KAUFDATUM.strftime('%d.%m.%Y')}</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Aktueller Kurs</div>
        <div class="metric-val">{aktueller_kurs:.2f} €</div>
        <div class="metric-sub {color_class}">{sign}{abs_gewinn_pro_stk:.2f} € pro Stück</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Prozentuale Entwicklung</div>
        <div class="metric-val {color_class}">{sign}{prozent_entwicklung:.2f}%</div>
        <div class="metric-sub" style="color: #94A3B8;">Seit Kaufdatum</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Gehaltene Stückzahl</div>
        <div class="metric-val">{STUECKZAHL:.2f}</div>
        <div class="metric-sub" style="color: #94A3B8;">Basis: {STARTKAPITAL:,.0f} € Einstieg</div>
    </div>
    """, unsafe_allow_html=True)

# --- METRIC MATRIX (ROW 2: KAPITAL & CASHFLOW) ---
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Investiertes Startkapital</div>
        <div class="metric-val">{STARTKAPITAL:,.2f} €</div>
        <div class="metric-sub" style="color: #64748B;">Einmalanlage</div>
    </div>
    """, unsafe_allow_html=True)

with m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Depotwert (Brutto)</div>
        <div class="metric-val">{brutto_depotwert:,.2f} €</div>
        <div class="metric-sub {color_class}">{sign}{gesamter_gewinn_eur:,.2f} € Gewinn</div>
    </div>
    """, unsafe_allow_html=True)

with m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Bisherige Entnahmen</div>
        <div class="metric-val" style="color: #FFB800;">{gesamt_entnommen:,.2f} €</div>
        <div class="metric-sub" style="color: #64748B;">{monate_aktiv} Monate × {ENTNAHME_PM:.0f} €</div>
    </div>
    """, unsafe_allow_html=True)

with m4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Rest-Depotwert (Netto)</div>
        <div class="metric-val accent">{netto_depotwert:,.2f} €</div>
        <div class="metric-sub" style="color: #94A3B8;">Nach Cash-Auszahlungen</div>
    </div>
    """, unsafe_allow_html=True)

# --- CHART SECTION ---
if df is not None and not df.empty:
    df["Performance_%"] = ((df["Close"] - ANFANGSKURS) / ANFANGSKURS) * 100
    df["Depotwert_EUR"] = STUECKZAHL * df["Close"]

    t1, t2 = st.tabs(["📊 Prozentuale Entwicklung (%)", "💰 Depotwert-Entwicklung (€)"])

    with t1:
        fig_pct = go.Figure()
        fig_pct.add_trace(go.Scatter(
            x=df.index, y=df["Performance_%"],
            mode="lines", name="Rendite",
            line=dict(color="#00F0FF", width=2.5),
            fill='tozeroy', fillcolor='rgba(0, 240, 255, 0.05)'
        ))
        fig_pct.add_hline(y=0, line_dash="dot", line_color="#FF0055", annotation_text="Einstieg")

        fig_pct.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=10, r=10, t=10, b=10), height=320,
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', ticksuffix="%"),
            hovermode="x unified"
        )
        st.plotly_chart(fig_pct, use_container_width=True, config={'displayModeBar': False})

    with t2:
        fig_eur = go.Figure()
        fig_eur.add_trace(go.Scatter(
            x=df.index, y=df["Depotwert_EUR"],
            mode="lines", name="Brutto Depotwert",
            line=dict(color="#00FFA3", width=2.5),
            fill='tozeroy', fillcolor='rgba(0, 255, 163, 0.05)'
        ))
        fig_eur.add_hline(y=STARTKAPITAL, line_dash="dash", line_color="#94A3B8", annotation_text="Startkapital")

        fig_eur.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=10, r=10, t=10, b=10), height=320,
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', ticksuffix=" €"),
            hovermode="x unified"
        )
        st.plotly_chart(fig_eur, use_container_width=True, config={'displayModeBar': False})

    st.caption(f"⚡ Daten-Engine: `{data_source}` | Letzter Handelsstand: {letztes_datum} (Automatisch geglättet für Wochenenden)")
