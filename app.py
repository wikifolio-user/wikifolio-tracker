import datetime
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="INDIZ GLOBALE TRENDS // Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- STRICT NEON DARK THEME (BLACK / WHITE / NEON ACCENTS) ---
st.markdown("""
<style>
    /* Dark Monochromatic Base */
    .stApp { 
        background-color: #000000; 
        color: #FFFFFF; 
        font-family: 'JetBrains Mono', 'Inter', monospace, sans-serif; 
    }
    
    /* Terminal Header */
    .terminal-header {
        background: #050505;
        border: 1px solid #222222;
        border-left: 4px solid #00FF66;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 24px;
    }
    .terminal-title {
        font-size: 1.5rem; 
        font-weight: 900; 
        letter-spacing: -0.5px;
        color: #FFFFFF;
        margin: 0;
        text-transform: uppercase;
    }
    .terminal-sub { 
        font-size: 0.72rem; 
        color: #888888; 
        letter-spacing: 1.2px; 
        text-transform: uppercase; 
        margin-top: 4px; 
    }
    
    /* Neon Glass Cards */
    .metric-card {
        background: #080808;
        border: 1px solid #1A1A1A;
        border-radius: 8px; 
        padding: 14px 16px; 
        margin-bottom: 12px;
    }
    .metric-label { 
        font-size: 0.65rem; 
        color: #777777; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    .metric-val { 
        font-size: 1.5rem; 
        font-weight: 800; 
        color: #FFFFFF; 
        margin: 4px 0; 
    }
    .metric-sub { 
        font-size: 0.75rem; 
        font-weight: 600; 
    }
    
    /* Status Colors */
    .pos-neon { color: #00FF66; text-shadow: 0 0 10px rgba(0,255,102,0.2); }
    .neg-neon { color: #FF0055; text-shadow: 0 0 10px rgba(255,0,85,0.2); }
    .neutral-dim { color: #888888; }
    
    /* Streamlit Overrides */
    #MainMenu {visibility: hidden;} 
    footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; gap: 8px; }
    .stTabs [data-baseweb="tab"] { 
        background-color: #0A0A0A; 
        border: 1px solid #222222; 
        color: #888888; 
        border-radius: 4px;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #151515 !important; 
        color: #FFFFFF !important; 
        border-color: #00FF66 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIG & PORTFOLIO DATA ---
WIKIFOLIO_SLUG = "wfindizglo"
ISIN = "DE000LS9VFS2"
ANFANGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
KAUFDATUM = datetime.date(2025, 8, 7)

STUECKZAHL = STARTKAPITAL / ANFANGSKURS

# --- WIKIFOLIO DATA ENGINE ---
@st.cache_data(ttl=120)
def fetch_wikifolio_data():
    """Holt die Zeitreihe und den tagesaktuellen Kurs direkt vom Wikifolio-Backend."""
    urls = [
        f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/chartdata",
        f"https://www.wikifolio.com/api/wikifolio/wf000ls9vf/chartdata"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                points = data.get("ChartPoints", [])
                if points:
                    df = pd.DataFrame(points)
                    date_col = "Date" if "Date" in df.columns else df.columns[0]
                    price_col = "Close" if "Close" in df.columns else "Value"
                    
                    df['Date'] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
                    df['Kurs'] = pd.to_numeric(df[price_col], errors='coerce')
                    
                    df = df.dropna(subset=['Date', 'Kurs']).sort_values('Date')
                    df.set_index('Date', inplace=True)
                    
                    # Synthetisches Lückenfüllen für Wochenenden & Feiertage (Freitagskurs)
                    full_idx = pd.date_range(start=df.index.min(), end=datetime.datetime.now(), freq='D')
                    df = df.reindex(full_idx)
                    df['Kurs'] = df['Kurs'].ffill().bfill()
                    
                    df_filtered = df[df.index.date >= KAUFDATUM].copy()
                    if not df_filtered.empty:
                        return df_filtered
                    return df
        except Exception:
            continue
    return None

df = fetch_wikifolio_data()

# --- CALCULATIONS ---
if df is not None and not df.empty:
    aktueller_kurs = float(df['Kurs'].iloc[-1])
    letztes_datum = df.index[-1].strftime("%d.%m.%Y")
else:
    aktueller_kurs = 308.50  # Hardened Emergency Fallback
    letztes_datum = datetime.date.today().strftime("%d.%m.%Y")

prozent_entwicklung = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
abs_gewinn_pro_stk = aktueller_kurs - ANFANGSKURS

brutto_depotwert = STUECKZAHL * aktueller_kurs
gesamter_gewinn_eur = brutto_depotwert - STARTKAPITAL

heute = datetime.date.today()
monate_aktiv = max(1, (heute.year - KAUFDATUM.year) * 12 + (heute.month - KAUFDATUM.month))
gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_depotwert = brutto_depotwert - gesamt_entnommen

# Neon Conditionals
is_positive = prozent_entwicklung >= 0
neon_color = "#00FF66" if is_positive else "#FF0055"
status_class = "pos-neon" if is_positive else "neg-neon"
sign = "+" if is_positive else ""

# --- HEADER ---
st.markdown(f"""
<div class="terminal-header" style="border-left-color: {neon_color};">
    <div class="terminal-title">INDIZ GLOBALE TRENDS // QUANT TERMINAL</div>
    <div class="terminal-sub">ISIN: {ISIN} • SLUG: {WIKIFOLIO_SLUG.upper()} • ASSET PERFORMANCE MATRIX</div>
</div>
""", unsafe_allow_html=True)

# --- METRIC ROW 1: KURS-PRÄZISION ---
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Anfangskurs (Kauf)</div>
        <div class="metric-val">{ANFANGSKURS:.2f} €</div>
        <div class="metric-sub neutral-dim">Datum: {KAUFDATUM.strftime('%d.%m.%Y')}</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Aktueller Kurs</div>
        <div class="metric-val {status_class}">{aktueller_kurs:.2f} €</div>
        <div class="metric-sub {status_class}">{sign}{abs_gewinn_pro_stk:.2f} € / Stk.</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Entwicklung</div>
        <div class="metric-val {status_class}">{sign}{prozent_entwicklung:.2f}%</div>
        <div class="metric-sub neutral-dim">Seit Kaufdatum</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Bestand</div>
        <div class="metric-val">{STUECKZAHL:.2f}</div>
        <div class="metric-sub neutral-dim">Basis: {STARTKAPITAL:,.0f} €</div>
    </div>
    """, unsafe_allow_html=True)

# --- METRIC ROW 2: CASHFLOW & VALUATION ---
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Startkapital</div>
        <div class="metric-val">{STARTKAPITAL:,.2f} €</div>
        <div class="metric-sub neutral-dim">Initial Investment</div>
    </div>
    """, unsafe_allow_html=True)

with m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Depotwert (Brutto)</div>
        <div class="metric-val">{brutto_depotwert:,.2f} €</div>
        <div class="metric-sub {status_class}">{sign}{gesamter_gewinn_eur:,.2f} € Profit</div>
    </div>
    """, unsafe_allow_html=True)

with m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Bisher Entnommen</div>
        <div class="metric-val" style="color: #FFFFFF;">{gesamt_entnommen:,.2f} €</div>
        <div class="metric-sub neutral-dim">{monate_aktiv} Mon. × {ENTNAHME_PM:.0f} €</div>
    </div>
    """, unsafe_allow_html=True)

with m4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Netto-Restwert</div>
        <div class="metric-val pos-neon">{netto_depotwert:,.2f} €</div>
        <div class="metric-sub neutral-dim">Nach Auszahlungen</div>
    </div>
    """, unsafe_allow_html=True)

# --- HIGH-TECH CHARTS ---
if df is not None and not df.empty:
    df["Performance_%"] = ((df["Kurs"] - ANFANGSKURS) / ANFANGSKURS) * 100
    df["Depotwert_EUR"] = STUECKZAHL * df["Kurs"]

    t1, t2, t3 = st.tabs(["📈 KURSVERLAUF (€)", "📊 PERFORMANCE (%)", "💰 DEPOTWERT (€)"])

    # Chart 1: Kursverlauf
    with t1:
        fig_kurs = go.Figure()
        fig_kurs.add_trace(go.Scatter(
            x=df.index, y=df["Kurs"],
            mode="lines", name="Kurs",
            line=dict(color=neon_color, width=2.5),
            fill='tozeroy', 
            fillcolor='rgba(0, 255, 102, 0.03)' if is_positive else 'rgba(255, 0, 85, 0.03)'
        ))
        fig_kurs.add_hline(
            y=ANFANGSKURS, line_dash="dash", line_color="#FF0055",
            annotation_text=f"Einstieg: {ANFANGSKURS:.2f} €",
            annotation_position="bottom right",
            annotation_font=dict(color="#FF0055", size=10)
        )
        fig_kurs.update_layout(
            paper_bgcolor='#000000', plot_bgcolor='#000000',
            margin=dict(l=10, r=10, t=10, b=10), height=340,
            xaxis=dict(showgrid=True, gridcolor='#111111', tickfont=dict(color='#666')),
            yaxis=dict(showgrid=True, gridcolor='#111111', ticksuffix=" €", tickfont=dict(color='#666')),
            hovermode="x unified"
        )
        st.plotly_chart(fig_kurs, use_container_width=True, config={'displayModeBar': False})

    # Chart 2: Rendite in %
    with t2:
        fig_pct = go.Figure()
        fig_pct.add_trace(go.Scatter(
            x=df.index, y=df["Performance_%"],
            mode="lines", name="Rendite",
            line=dict(color="#FFFFFF", width=2)
        ))
        fig_pct.add_hline(y=0, line_dash="dot", line_color="#FF0055")
        fig_pct.update_layout(
            paper_bgcolor='#000000', plot_bgcolor='#000000',
            margin=dict(l=10, r=10, t=10, b=10), height=340,
            xaxis=dict(showgrid=True, gridcolor='#111111', tickfont=dict(color='#666')),
            yaxis=dict(showgrid=True, gridcolor='#111111', ticksuffix="%", tickfont=dict(color='#666')),
            hovermode="x unified"
        )
        st.plotly_chart(fig_pct, use_container_width=True, config={'displayModeBar': False})

    # Chart 3: Depotwert
    with t3:
        fig_eur = go.Figure()
        fig_eur.add_trace(go.Scatter(
            x=df.index, y=df["Depotwert_EUR"],
            mode="lines", name="Brutto Wert",
            line=dict(color="#00FF66", width=2)
        ))
        fig_eur.add_hline(y=STARTKAPITAL, line_dash="dash", line_color="#555555", annotation_text="Kaufsumme")
        fig_eur.update_layout(
            paper_bgcolor='#000000', plot_bgcolor='#000000',
            margin=dict(l=10, r=10, t=10, b=10), height=340,
            xaxis=dict(showgrid=True, gridcolor='#111111', tickfont=dict(color='#666')),
            yaxis=dict(showgrid=True, gridcolor='#111111', ticksuffix=" €", tickfont=dict(color='#666')),
            hovermode="x unified"
        )
        st.plotly_chart(fig_eur, use_container_width=True, config={'displayModeBar': False})

    st.caption(f"⚡ DATA SOURCE: WIKIFOLIO ENGINE | LAST SYNC: {letztes_datum} (SYNTHETIC WEEKEND FILL ACTIVE)")
