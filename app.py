import datetime
import bs4
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# --- CONFIG & STYLING ---
st.set_page_config(
    page_title="QUANT // Wikifolio Terminal",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp { background-color: #080B10; color: #E2E8F0; font-family: 'Inter', system-ui, sans-serif; }
    
    /* Terminal Header */
    .terminal-header {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(30, 41, 59, 0.7));
        border: 1px solid rgba(0, 240, 255, 0.2);
        box-shadow: 0 0 30px rgba(0, 240, 255, 0.08);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .terminal-title {
        font-size: 1.6rem; font-weight: 900; letter-spacing: -0.5px;
        background: linear-gradient(90deg, #00F0FF, #7000FF, #FF007A);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0;
    }
    .terminal-sub { font-size: 0.75rem; color: #64748B; letter-spacing: 1.5px; text-transform: uppercase; margin-top: 4px; }
    
    /* Futuristic Glass Cards */
    .metric-card {
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 14px; padding: 14px 16px; margin-bottom: 12px;
        backdrop-filter: blur(12px);
    }
    .metric-label { font-size: 0.68rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 1px; }
    .metric-val { font-size: 1.45rem; font-weight: 800; color: #F8FAFC; margin: 2px 0; }
    .metric-sub { font-size: 0.8rem; font-weight: 600; }
    
    .pos-text { color: #00FFA3; }
    .neg-text { color: #FF0055; }
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- PORTFOLIO PARAMETER ---
ISIN = "DE000LS9VFS2"
TICKERS = ["LS9VFS.F", "LS9VFS.SG", "LS9VFS"]
KAUFDATUM = datetime.date(2025, 8, 7)
EINSTIEGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
STUECKZAHL = STARTKAPITAL / EINSTIEGSKURS

# --- DATA PIPELINE ---
@st.cache_data(ttl=300)
def fetch_market_data():
    """Holt historische Kurse über Yahoo Finance mit Datums-Puffer."""
    start_buffer = KAUFDATUM - datetime.timedelta(days=15)
    for t in TICKERS:
        try:
            df = yf.Ticker(t).history(start=start_buffer)
            if not df.empty and len(df) > 2:
                df = df.sort_index()
                df["Close"] = df["Close"].ffill()
                df = df[df.index.date >= KAUFDATUM].copy()
                if not df.empty:
                    return df, t
        except Exception:
            continue
    return None, None

def fetch_scraping_price():
    """Fallback Scraper von Wikifolio / L&S."""
    try:
        url = f"https://www.wikifolio.com/de/de/wikifolio/{ISIN}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        if res.status_code == 200:
            soup = bs4.BeautifulSoup(res.text, "html.parser")
            price_span = soup.find("span", {"class": "price"})
            if price_span:
                return float(price_span.text.replace(".", "").replace(",", ".").strip())
    except Exception:
        pass
    return None

df, ticker_used = fetch_market_data()

# Kurs-Ermittlung
aktueller_kurs = None
if df is not None and not df.empty:
    aktueller_kurs = float(df["Close"].iloc[-1])
else:
    aktueller_kurs = fetch_scraping_price()

if aktueller_kurs is None:
    aktueller_kurs = EINSTIEGSKURS # Notfall-Fallback

# --- BERECHNUNGEN & METRIKEN ---
aktuelle_perf_pct = ((aktueller_kurs - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
aktueller_depotwert = STUECKZAHL * aktueller_kurs
gewinn_abs = aktueller_depotwert - STARTKAPITAL

# Berechnung verstrichene Monate für Entnahme-Sim
heute = datetime.date.today()
monate_verstrichen = max(1, (heute.year - KAUFDATUM.year) * 12 + (heute.month - KAUFDATUM.month))
gesamt_entnommen = monate_verstrichen * ENTNAHME_PM
depotwert_nach_entnahme = aktueller_depotwert - gesamt_entnommen

# --- HEADER RENDERN ---
st.markdown("""
<div class="terminal-header">
    <div class="terminal-title">QUANT // PORTFOLIO INTELLIGENCE</div>
    <div class="terminal-subtitle">Wikifolio DE000LS9VFS2 • Live Yield & Capital Allocation</div>
</div>
""", unsafe_allow_html=True)

# KPI ROW 1: Hauptkennzahlen
c1, c2, c3, c4 = st.columns(4)

sign = "+" if aktuelle_perf_pct >= 0 else ""
color_cls = "pos-text" if aktuelle_perf_pct >= 0 else "neg-text"

with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Aktueller Kurs</div>
        <div class="metric-val">{aktueller_kurs:.2f} €</div>
        <div class="metric-sub {color_cls}">{sign}{aktuelle_perf_pct:.2f}% seit Kauf</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Gesamtdepotwert (Brutto)</div>
        <div class="metric-val">{aktueller_depotwert:,.2f} €</div>
        <div class="metric-sub {color_cls}">{sign}{gewinn_abs:,.2f} € Performance</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Bisher entnommen</div>
        <div class="metric-val">{gesamt_entnommen:,.2f} €</div>
        <div class="metric-sub" style="color: #64748B;">{monate_verstrichen} Monate × {ENTNAHME_PM:.0f} €</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Depotwert (Netto nach Entnahme)</div>
        <div class="metric-val" style="color:#00F0FF;">{depotwert_nach_entnahme:,.2f} €</div>
        <div class="metric-sub" style="color: #94A3B8;">Restkapital im Markt</div>
    </div>
    """, unsafe_allow_html=True)

# --- CHARTS SECTION ---
if df is not None and not df.empty:
    # Datenreihen aufbauen
    df["Depotwert_EUR"] = STUECKZAHL * df["Close"]
    df["Performance_%"] = ((df["Close"] - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
    
    # Modellpfade simulieren (z. B. 6% p.a. & 12% p.a. Zielrendite)
    tage = (df.index - pd.to_datetime(KAUFDATUM)).days
    df["Modell_6pct"] = STARTKAPITAL * ((1 + 0.06)**(tage / 365.25))
    df["Modell_12pct"] = STARTKAPITAL * ((1 + 0.12)**(tage / 365.25))

    tab1, tab2 = st.tabs(["📈 Portfoliowert vs. Modellpfade (€)", "📊 Prozentuale Performance (%)"])

    with tab1:
        fig_val = go.Figure()

        # Echtdaten Euro-Verlauf
        fig_val.add_trace(go.Scatter(
            x=df.index, y=df["Depotwert_EUR"],
            mode="lines", name="Reales Depot (€)",
            line=dict(color="#00F0FF", width=3),
            fill='tozeroy', fillcolor='rgba(0, 240, 255, 0.04)'
        ))

        # Modellpfad 6%
        fig_val.add_trace(go.Scatter(
            x=df.index, y=df["Modell_6pct"],
            mode="lines", name="Modellpfad 6% p.a.",
            line=dict(color="#FFB800", width=1.5, dash="dash")
        ))

        # Modellpfad 12%
        fig_val.add_trace(go.Scatter(
            x=df.index, y=df["Modell_12pct"],
            mode="lines", name="Modellpfad 12% p.a.",
            line=dict(color="#00FFA3", width=1.5, dash="dash")
        ))

        fig_val.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=5, r=5, t=10, b=5), height=340,
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', ticksuffix=" €"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#94A3B8")),
            hovermode="x unified"
        )
        st.plotly_chart(fig_val, use_container_width=True, config={'displayModeBar': False})

    with tab2:
        fig_pct = go.Figure()
        fig_pct.add_trace(go.Scatter(
            x=df.index, y=df["Performance_%"],
            mode="lines", name="Performance (%)",
            line=dict(color="#7000FF", width=2.5)
        ))
        fig_pct.add_hline(y=0, line_dash="dot", line_color="#FF0055", annotation_text="Kaufkurs")

        fig_pct.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=5, r=5, t=10, b=5), height=340,
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', ticksuffix="%"),
            hovermode="x unified"
        )
        st.plotly_chart(fig_pct, use_container_width=True, config={'displayModeBar': False})

    st.caption(f"⚡ Live Sync via `{ticker_used}` • Stand: {df.index[-1].strftime('%d.%m.%Y')}")

else:
    st.info("⚠️ Kein historischer Graph verfügbar (Markt geschlossen / Offline-Modus active). Live-Kurse oben bleiben aktiv.")
