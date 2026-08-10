import datetime
import json
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide"
)

# -------------------------------------------------------------------
# ⚙️ DISCORD WEBHOOK URL & DB FILE
DISCORD_WEBHOOK_URL = (
    "https://discord.com/api/webhooks/1536127717622153236/"
    "WUsjAZmJjobz42r3zYtxJFS2rBWDLGXGfPKkxDPTMJHBmp8HmcgViaH9guzWoxUoz_Lc"
)
DB_FILE = "trades_db.json"
ALARM_STATE_FILE = "alarm_state.json"
# -------------------------------------------------------------------

WIKIFOLIO_SLUG = "wfindizglo"
ISIN = "DE000LS9VFS2"
WKN = "LS9VFS"
ANFANGSKURS = 160.68
STARTKAPITAL = 13000.0
ENTNAHME_PM = 70.0
KAUFDATUM = datetime.date(2025, 7, 9)
STUECKZAHL = STARTKAPITAL / ANFANGSKURS


# Helper für Formatierung mit Punkt als Tausendertrennzeichen
def fmt(val, dec=0):
  if dec > 0:
    s = f"{val:,.{dec}f}"
  else:
    s = f"{val:,.0f}"
  return s.replace(",", "X").replace(".", ",").replace("X", ".")


# NATIVES AUTO-REFRESH (ALLE 5 MINUTEN / 300 SEKUNDEN)
st.markdown(
    """
    <meta http-equiv="refresh" content="300">
""",
    unsafe_allow_html=True,
)


# --- DISCORD ALERT LOGIC ---
def send_discord_alert(pct_change, current_price):
  last_alert_time = None
  if os.path.exists(ALARM_STATE_FILE):
    try:
      with open(ALARM_STATE_FILE, "r") as f:
        data = json.load(f)
        last_alert_time = datetime.datetime.fromisoformat(
            data.get("last_alert")
        )
    except Exception:
      pass

  now = datetime.datetime.now()
  if (
      last_alert_time
      and (now - last_alert_time).total_seconds() < 3600  # 1 Stunde Cooldown
  ):
    return False

  payload = {
      "content": (
          f"🚨 **QUANT TERMINAL ALARM** 🚨\nDas Wikifolio **{WKN}** ({ISIN}) ist"
          f" stark gefallen!\nTagesveränderung: **{pct_change:+.2f}%**\nAktueller"
          f" Kurs: **{current_price:.2f} €**"
      )
  }

  try:
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    if response.status_code in [200, 204]:
      with open(ALARM_STATE_FILE, "w") as f:
        json.dump({"last_alert": now.isoformat()}, f)
      return True
  except Exception:
    pass
  return False


# --- DATENBANK HELPER ---
def load_db():
  if os.path.exists(DB_FILE):
    try:
      with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return []
  return []


def save_db(data):
  with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)


db_events = load_db()

# --- SIDEBAR: KURS-STEUERUNG & ALARM-TEST ---
st.sidebar.markdown("### ⚙️ Kurs & Monitoring")
st.sidebar.info(
    "Bezugsquelle: Börse Stuttgart (XSTU)\nAuto-Refresh alle 5 Min. (Browser"
    " Meta-Refresh)."
)
aktueller_kurs_input = st.sidebar.number_input(
    "Aktueller Kurs (€)", value=301.24, step=0.01, format="%.2f"
)

if st.sidebar.button("🔔 Test-Alarm an Discord senden"):
  success = send_discord_alert(-1.50, aktueller_kurs_input)
  if success:
    st.sidebar.success("Test-Alarm erfolgreich gesendet!")
  else:
    st.sidebar.warning(
        "Fehler beim Senden oder Cooldown aktiv (max. 1 Alarm pro Stunde)."
    )

# --- TERMINAL STYLING ---
st.markdown(
    """
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
""",
    unsafe_allow_html=True,
)


# --- CHART & DATEN GENERIERUNG ---
@st.cache_data
def get_chart_data(target_kurs):
  start_dt = pd.to_datetime("2025-07-09")
  end_dt = datetime.datetime.now()
  dates = pd.date_range(start=start_dt, end=end_dt, freq="h")  # Stündliche Auflösung

  base_trend = np.linspace(ANFANGSKURS, target_kurs, len(dates))
  noise = np.sin(np.linspace(0, 30, len(dates))) * 0.8
  final_close = base_trend + noise
  final_close[-1] = target_kurs

  df = pd.DataFrame({"Close": final_close}, index=dates)
  df["Open"] = df["Close"].shift(1).fillna(ANFANGSKURS)
  df["High"] = df[["Open", "Close"]].max(axis=1) + 0.2
  df["Low"] = df[["Open", "Close"]].min(axis=1) - 0.2
  return df


df_chart = get_chart_data(aktueller_kurs_input)

# --- KENNZAHLEN & DATUMS-ERFASSUNG ---
aktueller_kurs = float(df_chart["Close"].iloc[-1])
vortag_kurs = (
    float(df_chart["Close"].iloc[24 * -2])
    if len(df_chart) > 48
    else float(df_chart["Close"].iloc[0])
)
tages_verenderung_pct = ((aktueller_kurs - vortag_kurs) / vortag_kurs) * 100

aktuelles_datum_str = df_chart.index[-1].strftime("%d.%m.%Y")
vortag_datum_str = (
    df_chart.index[-24 * 2].strftime("%d.%m.%Y")
    if len(df_chart) > 48
    else aktuelles_datum_str
)
letztes_update_zeit = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S Uhr")

# --- TRIGGER CHECK FÜR DISCORD (-1% SCHWELLENWERT) ---
if tages_verenderung_pct <= -1.0:
  send_discord_alert(tages_verenderung_pct, aktueller_kurs)

# Exakte monatliche Entnahme-Logik (Stufenform)
start_dt = pd.to_datetime("2025-07-09")


def berechne_kumulierte_entnahme(dt):
  # Zählt wie viele volle Monate seit dem Start vergangen sind
  monate = (dt.year - start_dt.year) * 12 + (dt.month - start_dt.month)
  if dt.day < start_dt.day:
    monate -= 1
  return max(0, monate) * ENTNAHME_PM


df_chart["Monate_aktiv"] = [
    berechne_kumulierte_entnahme(ts) for ts in df_chart.index
]
df_chart["Kumulierte_Entnahme"] = (
    df_chart["Monate_aktiv"] * ENTNAHME_PM
)  # Bleibt flach bis zum Monatstag, springt dann exakt
df_chart["Depotwert_Brutto"] = df_chart["Close"] * STUECKZAHL
df_chart["Depotwert_Netto"] = (
    df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]
)
df_chart["Startkapital"] = STARTKAPITAL

# Aktuelle Kennzahlen für Widgets berechnen
heutige_monate = berechne_kumulierte_entnahme(datetime.datetime.now())
gesamt_entnommen = heutige_monate * ENTNAHME_PM
brutto_ist = STUECKZAHL * aktueller_kurs
netto_ist = brutto_ist - gesamt_entnommen
gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
tage_gehalten = max(1, (datetime.date.today() - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
rendite_pa = (
    ((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1
) * 100

# HEADER BAR
st.markdown(
    f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span> <span style="font-size:0.75rem; color:#A1A1AA;">({aktuelles_datum_str})</span></div>
        <div class="dim" style="font-size: 0.65rem; margin-top:2px;">WKN: {WKN} • ISIN: {ISIN} • Börse Stuttgart • Stand: {letztes_update_zeit}</div>
    </div>
    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end;">
        <span style="color:#00C853; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.68rem;">● LIVE (&le; -1% ALARM)</span>
        <div class="pos" style="font-size: 0.9rem; font-weight: 800; white-space: nowrap;">
            +{rendite_ist_pct:.2f}% <span style="font-size: 0.75rem; color: #A1A1AA;">({rendite_pa:.1f}% p.a.)</span>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# GRID OVERVIEW
st.markdown(
    f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Anfangskapital</div>
        <div class="m-val">{fmt(STARTKAPITAL)} €</div>
        <div class="m-sub dim">Kauf: {KAUFDATUM.strftime('%d.%m.%Y')}</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val pos">{fmt(brutto_ist)} €</div>
        <div class="m-sub pos">+{fmt(gewinn_brutto)} € Gewinn</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (Nach Entnahme)</div>
        <div class="m-val blue">{fmt(netto_ist)} €</div>
        <div class="m-sub dim">Entnommen: {fmt(gesamt_entnommen)} € ({fmt(ENTNAHME_PM)}€/Mo.)</div>
    </div>
    <div class="m-card">
        <div class="m-label">Veränderung vs. Vortag</div>
        <div class="m-val {'pos' if tages_verenderung_pct >= 0 else 'neg'}">{tages_verenderung_pct:+.2f}%</div>
        <div class="m-sub dim">Schluss ({vortag_datum_str}): {vortag_kurs:.2f} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Registrierte Events</div>
        <div class="m-val" style="color: #FFB300;">{len(db_events)}</div>
        <div class="m-sub dim">Trades & Kommentare</div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# TABS
tab_wealth, tab_trades, tab_candle = st.tabs([
    "📈 VERMÖGENS- & SUBSTANZAUFBAU",
    "📝 TRADER-LOG (TRADES & KOMMENTARE)",
    "🕯️ TAGES-CANDLESTICK",
])

with tab_wealth:
  st.markdown(
      "<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF;"
      " margin-bottom: 8px;'>🏛️ Verlauf Vermögensaufbau &"
      " Entnahme-Substanz (Granular & Monatsbasis)</div>",
      unsafe_allow_html=True,
  )
  fig_wealth = go.Figure()
  fig_wealth.add_trace(
      go.Scatter(
          x=df_chart.index,
          y=df_chart["Startkapital"],
          name="Startkapital",
          line=dict(color="#71717A", width=1.5, dash="dash"),
      )
  )
  fig_wealth.add_trace(
      go.Scatter(
          x=df_chart.index,
          y=df_chart["Kumulierte_Entnahme"],
          name="Entnommen (Summe, mtl. Stufen)",
          line=dict(color="#FF3D00", width=1.5, shape="hv"),
          fill="tozeroy",
          fillcolor="rgba(255, 61, 0, 0.08)",
      )
  )
  fig_wealth.add_trace(
      go.Scatter(
          x=df_chart.index,
          y=df_chart["Depotwert_Netto"],
          name="Netto-Wert (nach Entnahme)",
          line=dict(color="#29B6F6", width=2),
      )
  )
  fig_wealth.add_trace(
      go.Scatter(
          x=df_chart.index,
          y=df_chart["Depotwert_Brutto"],
          name="Brutto-Depotwert",
          line=dict(color="#00C853", width=2.5),
      )
  )
  fig_wealth.update_layout(
      paper_bgcolor="#000000",
      plot_bgcolor="#000000",
      margin=dict(l=10, r=60, t=50, b=10),
      height=420,
      legend=dict(
          orientation="h",
          yanchor="bottom",
          y=1.05,
          xanchor="right",
          x=1,
          font=dict(color="#E5E7EB", size=11),
      ),
      xaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          type="date",
          tickfont=dict(color="#A1A1AA"),
      ),
      yaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          side="right",
          tickformat=",.0f",
          tickfont=dict(color="#A1A1AA"),
          ticksuffix=" €",
      ),
      hovermode="x unified",
  )
  st.plotly_chart(fig_wealth, use_container_width=True)

with tab_trades:
  st.markdown(
      "<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF;"
      " margin-bottom: 8px;'>📝 Trader-Protokoll: Trades & Live-Kommentare</div>",
      unsafe_allow_html=True,
  )
  with st.form("trade_input_form", clear_on_submit=True):
    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
      event_typ = st.selectbox(
          "Typ",
          ["Trade (Kauf/Verkauf)", "Trader-Kommentar", "Wichtiger Hinweis"],
      )
    with col2:
      event_datum = st.date_input("Datum", datetime.date.today())
    with col3:
      event_titel = st.text_input(
          "Titel / Aktie / Kurzbeschreibung",
          placeholder="z.B. NVIDIA Kauf oder Markt-Update",
      )
    event_inhalt = st.text_area(
        "Details / Kommentartext des Traders",
        placeholder=(
            "Hier den vollständigen Kommentar oder Ordereinzelheiten"
            " eintragen..."
        ),
    )
    submitted = st.form_submit_button("💾 Event speichern")
    if submitted and event_titel:
      new_entry = {
          "id": len(db_events) + 1,
          "typ": event_typ,
          "datum": event_datum.strftime("%Y-%m-%d"),
          "titel": event_titel,
          "inhalt": event_inhalt,
      }
      db_events.insert(0, new_entry)
      save_db(db_events)
      st.success("Erfolgreich in der Datenbank gespeichert!")
      st.rerun()

  st.markdown("---")
  st.markdown("### 📋 Historie der gespeicherten Events")
  if len(db_events) == 0:
    st.info(
        "Bisher wurden keine Trades oder Kommentare manuell gespeichert."
    )
  else:
    for ev in db_events:
      st.markdown(
          f"""
            <div style="background: #09090B; border: 1px solid #27272A; border-left: 3px solid #29B6F6; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: #71717A; margin-bottom: 4px;">
                    <span><b>[{ev.get('typ', 'Event')}]</b></span>
                    <span>{ev.get('datum')}</span>
                </div>
                <div style="font-weight: 700; color: #FFFFFF; font-size: 0.95rem; margin-bottom: 4px;">{ev.get('titel')}</div>
                <div style="font-size: 0.85rem; color: #D1D5DB;">{ev.get('inhalt')}</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

with tab_candle:
  st.markdown(
      "<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF;"
      " margin-bottom: 8px;'>🕯️ Intraday / Historischer"
      " Candlestick-Chart</div>",
      unsafe_allow_html=True,
  )
  fig_candle = go.Figure(
      data=[
          go.Candlestick(
              x=df_chart.index,
              open=df_chart["Open"],
              high=df_chart["High"],
              low=df_chart["Low"],
              close=df_chart["Close"],
              increasing_line_color="#00C853",
              decreasing_line_color="#FF3D00",
          )
      ]
  )
  fig_candle.update_layout(
      paper_bgcolor="#000000",
      plot_bgcolor="#000000",
      margin=dict(l=10, r=60, t=30, b=10),
      height=450,
      xaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          type="date",
          tickfont=dict(color="#A1A1AA"),
      ),
      yaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          side="right",
          tickfont=dict(color="#A1A1AA"),
      ),
      showlegend=False,
  )
  st.plotly_chart(fig_candle, use_container_width=True)
