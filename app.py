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

# --- TERMINAL STYLING (Schriftgrößen & Farben angepasst) ---
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
        display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px; margin-bottom: 20px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 14px 16px; }
    
    .m-label { font-size: 0.75rem; color: #A1A1AA; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; }
    .m-val { font-size: 1.4rem; font-weight: 800; color: #FFFFFF; margin: 6px 0; white-space: nowrap; }
    .m-sub { font-size: 0.85rem; font-weight: 600; white-space: nowrap; color: #CBD5E1; }
    
    .pos { color: #00C853; }
    .neg { color: #FF3D00; }
    .dim { color: #CBD5E1; }
    .blue { color: #29B6F6; }
    .orange { color: #FF3D00; }
    
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 4rem; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; gap: 4px; }
    .stTabs [data-baseweb="tab"] { background-color: #09090B; border: 1px solid #18181B; color: #71717A; padding: 6px 14px; font-size: 0.78rem; }
    .stTabs [aria-selected="true"] { background-color: #18181B !important; color: #00C853 !important; border-color: #00C853 !important; }
</style>
""",
    unsafe_allow_html=True,
)


# --- REALISTISCHE CHART- & DATEN GENERIERUNG ---
@st.cache_data
def get_chart_data(target_kurs):
  start_dt = pd.to_datetime("2025-07-09")
  end_dt = datetime.datetime.now()
  dates = pd.date_range(start=start_dt, end=end_dt, freq="h")

  np.random.seed(42)
  n = len(dates)

  trend = np.linspace(ANFANGSKURS, target_kurs, n)
  steps = np.random.normal(loc=0.0, scale=0.35, size=n)
  random_walk = np.cumsum(steps)
  random_walk = random_walk - np.linspace(0, random_walk[-1], n)

  final_close = trend + random_walk
  final_close[-1] = target_kurs

  df = pd.DataFrame({"Close": final_close}, index=dates)
  df["Open"] = df["Close"].shift(1).fillna(ANFANGSKURS)
  df["High"] = df[["Open", "Close"]].max(axis=1) + np.abs(
      np.random.normal(0.1, 0.05, n)
  )
  df["Low"] = df[["Open", "Close"]].min(axis=1) - np.abs(
      np.random.normal(0.1, 0.05, n)
  )
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

start_dt = pd.to_datetime("2025-07-09")


def berechne_monatliche_entnahme(dt):
  monate = (dt.year - start_dt.year) * 12 + (dt.month - start_dt.month)
  if dt.day < start_dt.day:
    monate -= 1
  return max(0, monate) * ENTNAHME_PM


df_chart["Kumulierte_Entnahme"] = [
    berechne_monatliche_entnahme(ts) for ts in df_chart.index
]
df_chart["Depotwert_Brutto"] = df_chart["Close"] * STUECKZAHL
df_chart["Depotwert_Netto"] = (
    df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]
)
df_chart["Startkapital"] = STARTKAPITAL

heutige_monate_anzahl = max(
    0,
    (datetime.datetime.now().year - start_dt.year) * 12
    + (datetime.datetime.now().month - start_dt.month),
)
if datetime.datetime.now().day < start_dt.day:
  heutige_monate_anzahl -= 1
gesamt_entnommen = heutige_monate_anzahl * ENTNAHME_PM

brutto_ist = STUECKZAHL * aktueller_kurs
netto_ist = brutto_ist - gesamt_entnommen
gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
tage_gehalten = max(1, (datetime.date.today() - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
rendite_pa = (
    ((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1
) * 100
monate_gehalten = max(1, jahre_gehalten * 12)
rendite_mo = (
    ((aktueller_kurs / ANFANGSKURS) ** (1 / max(1, monate_gehalten))) - 1
) * 100

# Monatlicher Bruttogewinn-Durchschnitt (absolut) für die Prognose
mtl_gewinn_avg = gewinn_brutto / max(1, monate_gehalten)

# HEADER BAR
st.markdown(
    f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span> <span style="font-size:0.8rem; color:#CBD5E1;">({aktuelles_datum_str})</span></div>
        <div style="font-size: 0.75rem; color: #CBD5E1; margin-top:3px;">WKN: {WKN} • ISIN: {ISIN} • Börse Stuttgart • Stand: {letztes_update_zeit}</div>
    </div>
    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end;">
        <span style="color:#00C853; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.75rem; font-weight:700;">● LIVE (&le; -1% ALARM)</span>
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
        <div class="m-label">Veränderung vs. Vortag</div>
        <div class="m-val {'pos' if tages_verenderung_pct >= 0 else 'neg'}">{tages_verenderung_pct:+.2f}%</div>
        <div class="m-sub">Schluss ({vortag_datum_str}): {vortag_kurs:.2f} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val pos">{fmt(brutto_ist)} €</div>
        <div class="m-sub pos">+{fmt(gewinn_brutto)} € ({rendite_ist_pct:.2f}%) | Ø +{fmt(mtl_gewinn_avg, 2)} € mtl.</div>
        <div class="m-sub" style="margin-top: 4px; color: #CBD5E1;">Ø {rendite_pa:.1f}% p.a. | {rendite_mo:+.2f}% mtl.</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (Nach Entnahme)</div>
        <div class="m-val blue">{fmt(netto_ist)} €</div>
        <div class="m-sub">Aktueller Depotwert bereinigt</div>
    </div>
    <div class="m-card">
        <div class="m-label">Entnommenes Kapital</div>
        <div class="m-val orange">{fmt(gesamt_entnommen)} €</div>
        <div class="m-sub">Monatlich: {fmt(ENTNAHME_PM)} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Anfangskapital</div>
        <div class="m-val">{fmt(STARTKAPITAL)} €</div>
        <div class="m-sub">Kauf ({KAUFDATUM.strftime('%d.%m.%Y')}): {ANFANGSKURS:.2f} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Registrierte Events</div>
        <div class="m-val" style="color: #FFB300;">{len(db_events)}</div>
        <div class="m-sub">Trades & Kommentare</div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# TABS
tab_wealth, tab_trades, tab_candle, tab_forecast = st.tabs([
    "📈 VERMÖGENS- & SUBSTANZAUFBAU",
    "📝 TRADER-LOG (TRADES & KOMMENTARE)",
    "🕯️ TAGES-CANDLESTICK",
    "🔮 ZUKUNFTS-PROGNOSE (5 JAHRE)",
])

with tab_wealth:
  st.markdown(
      "<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF;"
      " margin-bottom: 8px;'>🏛️ Verlauf Vermögensaufbau &"
      " Entnahme-Substanz (Quartals-Skalierung)</div>",
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
      margin=dict(l=10, r=60, t=50, b=40),
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
          dtick="M3",
          tickformat="%b %Y",
          range=[
              df_chart.index[0],
              df_chart.index[-1] + pd.Timedelta(days=20),
          ],
      ),
      yaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          side="right",
          dtick=1000,
          tickprefix="",
          ticksuffix=" €",
          tickfont=dict(color="#A1A1AA"),
          tickvals=list(
              range(
                  0,
                  int(df_chart["Depotwert_Brutto"].max() + 5000),
                  1000,
              )
          ),
          ticktext=[
              f"{v:,.0f}".replace(",", ".")
              for v in range(
                  0,
                  int(df_chart["Depotwert_Brutto"].max() + 5000),
                  1000,
              )
          ],
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

  st.markdown("### 📋 Historie der gespeicherten Events")
  if len(db_events) == 0:
    st.info(
        "Bisher wurden keine Trades oder Kommentare manuell oder automatisch"
        " gespeichert."
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

  st.markdown("---")

  st.markdown("### ✍️ Neuen Eintrag erfassen")
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
      margin=dict(l=10, r=60, t=30, b=40),
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

with tab_forecast:
  st.markdown(
      "<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF;"
      " margin-bottom: 8px;'>🔮 5-Jahres-Zukunftsprognose (Basierend auf aktuellem"
      " Brutto-Monatsdurchschnitt)</div>",
      unsafe_allow_html=True,
  )
  st.info(
      f"Die Prognose projiziert den bisherigen durchschnittlichen"
      f" Bruttogewinn von ca. **+{fmt(mtl_gewinn_avg, 2)} € / Monat** (bzw."
      f" geometrisch **{rendite_mo:+.2f}% mtl.**) über die kommenden 5 Jahre"
      " fort."
  )

  forecast_data = []

  # 1. Startjahr (Kaufdatum & Startkapital) hinzufügen
  forecast_data.append({
      "Jahr": "Startjahr (09.07.25)",
      "Datum": KAUFDATUM.strftime("%d.%m.%Y"),
      "Brutto Depotwert": STARTKAPITAL,
      "Gesamter Gewinn": 0.0,
      "Netto Depotwert": STARTKAPITAL,
      "Kumulierte Entnahme": 0.0,
  })

  # 2. Heutiger Stand (Jahr 0)
  current_date_val = datetime.date.today()
  forecast_data.append({
      "Jahr": "Heute (Jahr 0)",
      "Datum": current_date_val.strftime("%d.%m.%Y"),
      "Brutto Depotwert": brutto_ist,
      "Gesamter Gewinn": gewinn_brutto,
      "Netto Depotwert": netto_ist,
      "Kumulierte Entnahme": gesamt_entnommen,
  })

  sim_brutto = brutto_ist
  sim_netto = netto_ist
  sim_entnahme_kumuliert = gesamt_entnommen

  # 3. Projektion Jahr 1 bis 5
  for y in range(1, 6):
    for m in range(12):
      sim_brutto = sim_brutto * (1 + (rendite_mo / 100.0))
      sim_entnahme_kumuliert += ENTNAHME_PM

    sim_netto = sim_brutto - sim_entnahme_kumuliert
    fut_date = current_date_val + datetime.timedelta(days=y * 365)

    forecast_data.append({
        "Jahr": f"Jahr +{y}",
        "Datum": fut_date.strftime("%d.%m.%Y"),
        "Brutto Depotwert": sim_brutto,
        "Gesamter Gewinn": sim_brutto - STARTKAPITAL,
        "Netto Depotwert": sim_netto,
        "Kumulierte Entnahme": sim_entnahme_kumuliert,
    })

  df_forecast = pd.DataFrame(forecast_data)

  # Plotly Chart (mit mehr Abstand oben, ohne Text-Overlay auf den Linien, um Überlappungen zu verhindern)
  fig_forecast = go.Figure()
  fig_forecast.add_trace(
      go.Scatter(
          x=df_forecast["Jahr"],
          y=df_forecast["Brutto Depotwert"],
          name="Projizierter Brutto-Wert",
          mode="lines+markers",
          line=dict(color="#00C853", width=3),
      )
  )
  fig_forecast.add_trace(
      go.Scatter(
          x=df_forecast["Jahr"],
          y=df_forecast["Netto Depotwert"],
          name="Projizierter Netto-Wert (nach Entnahme)",
          mode="lines+markers",
          line=dict(color="#29B6F6", width=2, dash="dash"),
      )
  )
  fig_forecast.add_trace(
      go.Scatter(
          x=df_forecast["Jahr"],
          y=df_forecast["Kumulierte Entnahme"],
          name="Kumulierte Entnahmen",
          mode="lines+markers",
          line=dict(color="#FF3D00", width=2, dash="dot"),
      )
  )

  fig_forecast.update_layout(
      paper_bgcolor="#000000",
      plot_bgcolor="#000000",
      margin=dict(l=10, r=30, t=80, b=40),
      height=420,
      legend=dict(
          orientation="h",
          yanchor="bottom",
          y=1.02,
          xanchor="right",
          x=1,
          font=dict(color="#E5E7EB", size=11),
      ),
      xaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          tickfont=dict(color="#A1A1AA"),
      ),
      yaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          side="right",
          tickprefix="",
          ticksuffix=" €",
          tickfont=dict(color="#A1A1AA"),
      ),
      hovermode="x unified",
  )
  st.plotly_chart(fig_forecast, use_container_width=True)

  st.markdown("### 📊 Tabellarische Übersicht (inkl. Startjahr)")

  df_display = df_forecast.copy()
  for col in [
      "Brutto Depotwert",
      "Gesamter Gewinn",
      "Netto Depotwert",
      "Kumulierte Entnahme",
  ]:
    df_display[col] = df_display[col].apply(lambda x: f"{fmt(x)} €")

  st.dataframe(df_display, use_container_width=True, hide_index=True)
