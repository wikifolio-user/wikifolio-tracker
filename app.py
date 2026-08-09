import datetime
import plotly.graph_objects as go
import requests
import streamlit as st
import pandas as pd

# Page Configuration
st.set_page_config(
    page_title="Wikifolio Core Terminal", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Futuristisches CSS-Design Inject
st.markdown("""
<style>
    /* Dark Futuristic Theme */
    .stApp {
        background-color: #0B0E14;
        color: #E2E8F0;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    
    /* Header Styling */
    .terminal-header {
        background: linear-gradient(135deg, rgba(20, 26, 38, 0.8), rgba(15, 23, 42, 0.9));
        border: 1px solid rgba(0, 240, 255, 0.2);
        box-shadow: 0 0 20px rgba(0, 240, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 24px;
        backdrop-filter: blur(10px);
    }
    .terminal-title {
        font-size: 1.5rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(90deg, #00F0FF, #7000FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .terminal-subtitle {
        font-size: 0.8rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-top: 4px;
    }

    /* Metric Cards (Glassmorphism) */
    .metric-card {
        background: rgba(18, 24, 38, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        backdrop-filter: blur(8px);
        transition: transform 0.2s, border 0.2s;
    }
    .metric-card:hover {
        border-color: rgba(0, 240, 255, 0.4);
        transform: translateY(-2px);
    }
    .metric-label {
        font-size: 0.75rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .metric-val {
        font-size: 1.6rem;
        font-weight: 700;
        color: #F8FAFC;
        margin: 4px 0;
    }
    .badge-pos {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        background: rgba(0, 255, 163, 0.15);
        color: #00FFA3;
        border: 1px solid rgba(0, 255, 163, 0.3);
    }
    .badge-neg {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        background: rgba(255, 0, 85, 0.15);
        color: #FF0055;
        border: 1px solid rgba(255, 0, 85, 0.3);
    }
    
    /* Hide Streamlit Native Overheads */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_html=True)

# Parameter
ISIN = "DE000LS9VFS2"
WIKIFOLIO_ID = "wf000ls9vf"
KAUFDATUM = datetime.date(2025, 8, 7)
EINSTIEGSKURS = 160.68
ENTNAHME_PM = 180.0

@st.cache_data(ttl=300)
def fetch_wikifolio_data():
    """Holt Kurse & Historie direkt über die Wikifolio API."""
    try:
        url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_ID}/chartdata"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            data = res.json()
            # Datenstruktur in DataFrame umwandeln
            points = data.get("ChartPoints", [])
            df = pd.DataFrame(points)
            if not df.empty:
                df["Date"] = pd.to_datetime(df["Date"])
                df.set_index("Date", inplace=True)
                df.rename(columns={"Close": "Close"}, inplace=True)
                df = df[df.index.date >= KAUFDATUM]
                return df
    except Exception:
        pass
    return None

# --- HEADER RENDERN ---
st.markdown("""
<div class="terminal-header">
    <div class="terminal-title">WIKIFOLIO // QUANT DASHBOARD</div>
    <div class="terminal-subtitle">Live Tracking & Performance Matrix</div>
</div>
""", unsafe_html=True)

df = fetch_wikifolio_data()

if df is not None and not df.empty:
    aktueller_kurs = float(df["Close"].iloc[-1])
    letztes_datum = df.index[-1].strftime("%d.%m.%Y")
    aktuelle_perf = ((aktueller_kurs - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
    df["Performance_%"] = ((df["Close"] - EINSTIEGSKURS) / EINSTIEGSKURS) * 100

    # Key Metrics Bar (Mobile Optimized Glass Cards)
    c1, c2, c3 = st.columns(3)
    
    badge_class = "badge-pos" if aktuelle_perf >= 0 else "badge-neg"
    sign = "+" if aktuelle_perf >= 0 else ""

    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Einstiegskurs</div>
            <div class="metric-val">{EINSTIEGSKURS:.2f} €</div>
        </div>
        """, unsafe_html=True)

    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Aktueller Kurs</div>
            <div class="metric-val">{aktueller_kurs:.2f} €</div>
            <span class="{badge_class}">{sign}{aktuelle_perf:.2f}%</span>
        </div>
        """, unsafe_html=True)

    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Monatl. Entnahme</div>
            <div class="metric-val">{ENTNAHME_PM:.2f} €</div>
        </div>
        """, unsafe_html=True)

    # Futuristic Chart
    fig = go.Figure()

    # Glowing Trendline
    fig.add_trace(go.Scatter(
        x=df.index, 
        y=df["Performance_%"], 
        mode="lines", 
        name="Performance",
        line=dict(color="#00F0FF", width=3),
        fill='tozeroy',
        fillcolor='rgba(0, 240, 255, 0.05)'
    ))

    # Baseline
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
        margin=dict(l=10, r=10, t=30, b=10),
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
        height=320
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    st.caption(f"⚡ Live-Sync: {letztes_datum} | Source: Wikifolio Core API")

else:
    st.error("⚠️ Signal unterbrochen: Marktdaten konnten nicht geladen werden.")
