import datetime
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Wikifolio Core Terminal", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- FUTURISTIC UI STYLING ---
st.markdown("""
<style>
    .stApp {
        background-color: #0B0E14;
        color: #E2E8F0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .terminal-header {
        background: linear-gradient(135deg, rgba(20, 26, 38, 0.8), rgba(15, 23, 42, 0.9));
        border: 1px solid rgba(0, 240, 255, 0.25);
        box-shadow: 0 0 25px rgba(0, 240, 255, 0.12);
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 20px;
        backdrop-filter: blur(10px);
    }
    
    .terminal-title {
        font-size: 1.4rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(90deg, #00F0FF, #7000FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    
    .terminal-subtitle {
        font-size: 0.75rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-top: 4px;
    }

    .metric-card {
        background: rgba(18, 24, 38, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 10px;
        backdrop-filter: blur(10px);
    }
    
    .metric-label {
        font-size: 0.7rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .metric-val {
        font-size: 1.5rem;
        font-weight: 700;
        color: #F8FAFC;
        margin: 2px 0;
    }
    
    .badge-pos {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        background: rgba(0, 255, 163, 0.15);
        color: #00FFA3;
        border: 1px solid rgba(0, 255, 163, 0.3);
    }
    
    .badge-neg {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        background: rgba(255, 0, 85, 0.15);
        color: #FF0055;
        border: 1px solid rgba(255, 0, 85, 0.3);
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- PARAMETER CONFIGURATION ---
WIKIFOLIO_ID = "wf000ls9vf"
ISIN = "DE000LS9VFS2"
EINSTIEGSKURS = 160.68
ENTNAHME_PM = 180.0
STARTKAPITAL = 20000.0
KAUFDATUM = datetime.date(2025, 8, 7)

# --- ROBUST DATA FETCHING PIPELINE ---
@st.cache_data(ttl=300)
def load_market_data():
    """Fetches chart data from Wikifolio API with safe parsing and fallback."""
    try:
        url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_ID}/chartdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        response = requests.get(url, headers=headers, timeout=8)
        
        if response.status_code == 200:
            json_data = response.json()
            points = json_data.get("ChartPoints", [])
            
            if points:
                df = pd.DataFrame(points)
                
                # Datumsspalte flexibel parsen
                date_col = "Date" if "Date" in df.columns else df.columns[0]
                price_col = "Close" if "Close" in df.columns else "Value"
                
                df["parsed_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.tz_localize(None)
                df["Close"] = pd.to_numeric(df[price_col], errors="coerce")
                
                df = df.dropna(subset=["parsed_date", "Close"]).sort_values("parsed_date")
                df.set_index("parsed_date", inplace=True)
                
                # Datumsfilter anwenden (Sicherheitsnetz falls Kaufdatum nach allen Daten liegt)
                filtered_df = df[df.index.date >= KAUFDATUM]
                if not filtered_df.empty:
                    return filtered_df
                return df  # Fallback: Alle Daten anzeigen wenn Kaufdatum noch in der Zukunft/ohne Treffer liegt
    except Exception:
        pass
    return None

# --- HEADER ---
st.markdown("""
<div class="terminal-header">
    <div class="terminal-title">WIKIFOLIO // QUANT TERMINAL</div>
    <div class="terminal-subtitle">Live Tracking & Performance Matrix</div>
</div>
""", unsafe_allow_html=True)

df = load_market_data()

if df is not None and not df.empty:
    aktueller_kurs = float(df["Close"].iloc[-1])
    letztes_datum = df.index[-1].strftime("%d.%m.%Y")
    aktuelle_perf = ((aktueller_kurs - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
    
    df["Performance_%"] = ((df["Close"] - EINSTIEGSKURS) / EINSTIEGSKURS) * 100

    # KPI Row
    c1, c2, c3 = st.columns(3)
    badge_class = "badge-pos" if aktuelle_perf >= 0 else "badge-neg"
    sign = "+" if aktuelle_perf >= 0 else ""

    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Einstiegskurs</div>
            <div class="metric-val">{EINSTIEGSKURS:.2f} €</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Aktueller Kurs</div>
            <div class="metric-val">{aktueller_kurs:.2f} €</div>
            <span class="{badge_class}">{sign}{aktuelle_perf:.2f}%</span>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Monatl. Entnahme</div>
            <div class="metric-val">{ENTNAHME_PM:.2f} €</div>
        </div>
        """, unsafe_allow_html=True)

    # High-Tech Chart
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index, 
        y=df["Performance_%"], 
        mode="lines", 
        name="Performance",
        line=dict(color="#00F0FF", width=2.5),
        fill='tozeroy',
        fillcolor='rgba(0, 240, 255, 0.06)'
    ))

    fig.add_hline(
        y=0, 
        line_dash="dot", 
        line_color="#FF0055", 
        annotation_text="Einstieg", 
        annotation_position="bottom right",
        annotation_font=dict(color="#FF0055", size=10)
    )

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=5, r=5, t=25, b=5),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
            tickfont=dict(color='#64748B', size=10)
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
            ticksuffix="%",
            tickfont=dict(color='#64748B', size=10)
        ),
        hovermode="x unified",
        showlegend=False,
        height=300
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    st.caption(f"⚡ Sync Status: OK ({letztes_datum}) | Data Source: Wikifolio Engine")

else:
    # Graceful Offline State (wenn API komplett verweigert)
    st.warning("⚠️ Live-Signal aktuell unterbrochen. Verwende Notfall-Metriken:")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Einstiegskurs</div><div class="metric-val">{EINSTIEGSKURS:.2f} €</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Aktueller Kurs</div><div class="metric-val">{EINSTIEGSKURS:.2f} €</div><span class="badge-pos">+0.00%</span></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Monatl. Entnahme</div><div class="metric-val">{ENTNAHME_PM:.2f} €</div></div>', unsafe_allow_html=True)
