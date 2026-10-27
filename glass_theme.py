"""
Premium Glass Theme für das Finanz Dashboard (Streamlit).

Einbinden in app.py direkt nach st.set_page_config(...):

    from glass_theme import apply_glass_theme
    apply_glass_theme()

Optimiert für Safari auf iPhone/iPad (-webkit-backdrop-filter, Touch-States).
"""
import streamlit as st

GLASS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

:root {
  --bg-0: #07090f;
  --bg-1: #0d1220;
  --accent: #7c9cff;
  --accent-2: #5eead4;
  --pos: #34d399;
  --neg: #f87171;
  --text: #e8ecf6;
  --text-dim: #8a93a8;
  --glass-bg: rgba(255, 255, 255, 0.055);
  --glass-bg-hover: rgba(255, 255, 255, 0.09);
  --glass-border: rgba(255, 255, 255, 0.12);
  --glass-border-strong: rgba(255, 255, 255, 0.22);
  --glass-blur: 22px;
  --radius-lg: 20px;
  --radius-md: 14px;
  --shadow: 0 10px 40px -12px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.25);
  --ease: cubic-bezier(.2, .8, .2, 1);
}

/* ---------- Hintergrund: tiefer Verlauf + weiche Lichtflecken ---------- */
.stApp {
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(124,156,255,0.18), transparent 60%),
    radial-gradient(900px 500px at 110% 10%, rgba(94,234,212,0.12), transparent 60%),
    radial-gradient(800px 600px at 50% 120%, rgba(167,139,250,0.12), transparent 60%),
    linear-gradient(180deg, var(--bg-1), var(--bg-0));
  background-attachment: fixed;
  color: var(--text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
}
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; max-width: 1200px; }

h1, h2, h3 { font-weight: 650; letter-spacing: -0.02em; color: var(--text); }
h1 {
  background: linear-gradient(135deg, #fff 0%, #c7d2fe 60%, var(--accent-2) 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
/* Textfarbe: p/label/span erben sie von .stApp (oben). Eine feste Farbe fuer alle Spans wuerde
   gruenen/roten Kurswerten in verschachtelten Spans die Farbe nehmen. */
small, .stCaption, [data-testid="stCaptionContainer"] { color: var(--text-dim) !important; }

/* ---------- Glas-Buttons ---------- */
.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button,
[data-testid^="stBaseButton"] {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  padding: 0.7rem 1.4rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.03) 100%),
    var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(170%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(170%);
  color: var(--text);
  font-weight: 600;
  font-size: 0.95rem;
  letter-spacing: 0.01em;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.25),
    inset 0 -1px 0 rgba(0,0,0,0.25),
    var(--shadow);
  transition: transform .25s var(--ease), box-shadow .25s var(--ease),
              border-color .25s var(--ease), background .25s var(--ease);
  -webkit-tap-highlight-color: transparent;
}

/* Spiegelnder Glanzstreifen oben */
.stButton > button::before,
.stDownloadButton > button::before,
.stFormSubmitButton > button::before {
  content: "";
  position: absolute; inset: 0 0 50% 0;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(255,255,255,0.22), rgba(255,255,255,0));
  pointer-events: none;
  z-index: -1;
}

/* Lichtreflex, der beim Hover durchläuft */
.stButton > button::after,
.stDownloadButton > button::after,
.stFormSubmitButton > button::after {
  content: "";
  position: absolute; top: 0; left: -120%;
  width: 60%; height: 100%;
  background: linear-gradient(110deg, transparent, rgba(255,255,255,0.28), transparent);
  transform: skewX(-20deg);
  transition: left .7s var(--ease);
  pointer-events: none;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
  transform: translateY(-2px);
  border-color: var(--glass-border-strong);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.05) 100%),
    var(--glass-bg-hover);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.35),
    0 0 0 1px rgba(124,156,255,0.25),
    0 14px 40px -10px rgba(124,156,255,0.45);
  color: #fff;
}
.stButton > button:hover::after,
.stDownloadButton > button:hover::after,
.stFormSubmitButton > button:hover::after { left: 140%; }

.stButton > button:active,
.stDownloadButton > button:active,
.stFormSubmitButton > button:active {
  transform: translateY(0) scale(0.98);
  box-shadow: inset 0 2px 8px rgba(0,0,0,0.35), 0 4px 14px -6px rgba(0,0,0,0.5);
}
.stButton > button:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

/* Primär-Button (type="primary"): getöntes Glas mit Akzent-Glow */
[data-testid="stBaseButton-primary"] {
  border-color: rgba(124,156,255,0.45);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.20) 0%, rgba(255,255,255,0) 60%),
    linear-gradient(135deg, rgba(124,156,255,0.55), rgba(94,234,212,0.35));
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.4),
    0 10px 30px -8px rgba(124,156,255,0.6);
}
[data-testid="stBaseButton-primary"]:hover {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.5),
    0 0 0 1px rgba(124,156,255,0.5),
    0 16px 44px -8px rgba(124,156,255,0.75);
}

/* ---------- Glas-Karten: Metriken, Expander, Container ---------- */
[data-testid="stMetric"],
[data-testid="stExpander"] details,
[data-testid="stVerticalBlockBorderWrapper"] > div[style*="border"],
[data-testid="stForm"] {
  background: linear-gradient(160deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));
  backdrop-filter: blur(var(--glass-blur)) saturate(160%);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(160%);
  border: 1px solid var(--glass-border) !important;
  border-radius: var(--radius-lg) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), var(--shadow);
}
[data-testid="stMetric"] { padding: 1.1rem 1.3rem; transition: transform .25s var(--ease); }
[data-testid="stMetric"]:hover { transform: translateY(-2px); }
[data-testid="stMetricLabel"] p {
  color: var(--text-dim) !important; font-size: 0.78rem !important;
  text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600;
}
[data-testid="stMetricValue"] {
  font-family: 'JetBrains Mono', monospace; font-weight: 600;
  font-variant-numeric: tabular-nums; letter-spacing: -0.02em;
}
[data-testid="stMetricDelta"] { font-family: 'JetBrains Mono', monospace; font-weight: 500; }

/* ---------- Tabs als Glas-Segmented-Control ---------- */
[data-baseweb="tab-list"] {
  gap: 4px; padding: 4px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border); border-radius: 999px;
  width: fit-content; max-width: 100%; overflow-x: auto;
}
[data-baseweb="tab"] {
  border-radius: 999px !important; padding: 0.45rem 1.1rem !important;
  background: transparent !important; color: var(--text-dim) !important;
  transition: all .25s var(--ease);
}
[data-baseweb="tab"][aria-selected="true"] {
  background: linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0.06)) !important;
  color: #fff !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.3), 0 4px 14px -4px rgba(0,0,0,0.5);
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* ---------- Inputs ---------- */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
  background: rgba(255,255,255,0.04) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: var(--radius-md) !important;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(124,156,255,0.2);
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
  background: rgba(10,14,24,0.6);
  backdrop-filter: blur(30px) saturate(160%); -webkit-backdrop-filter: blur(30px) saturate(160%);
  border-right: 1px solid var(--glass-border);
}

/* ---------- Tabellen & Charts ---------- */
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"] {
  border-radius: var(--radius-lg); overflow: hidden;
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,0.03);
}

hr { border-color: var(--glass-border) !important; }

/* ---------- Mobile (iPhone/iPad) ---------- */
@media (max-width: 768px) {
  .block-container { padding: 1rem 0.9rem 3rem; }
  .stButton > button { width: 100%; min-height: 48px; }
  [data-testid="stMetric"] { padding: 0.9rem 1rem; }
}
@media (hover: none) {
  .stButton > button:hover { transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}
</style>
"""


def apply_glass_theme() -> None:
    st.markdown(GLASS_CSS, unsafe_allow_html=True)
