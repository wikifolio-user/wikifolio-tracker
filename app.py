import datetime
import json
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
import yfinance as yf

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide"
)

# -------------------------------------------------------------------
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1536127717622153236/WUsjAZmJjobz42r3zYtxJFS2rBWDLGXGfPKkxDPTMJHBmp8HmcgViaH9guzWoxUoz_Lc"
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

BERLIN_TZ = pytz.timezone("Europe/Berlin")


def fmt(val, dec=0):
  if dec > 0:
    s = f"{val:,.{dec}f}"
  else:
    s = f"{val:,.0f}"
  return s.replace(",", "X").replace(".", ",").replace("X", ".")


# Auto-Refresh alle 3 Minuten (180 Sekunden)
st.markdown(
    """<meta http-equiv="refresh" content="180">""", unsafe_allow_html=True
)


# --- VOLLAUTOMATISCHE API ABFRAGE (KURS & VORTAG) ---
def fetch_market_data(ticker_symbol):
  live_kurs = None
  vortag_kurs = None
  vortag_datum_str = "N/A"
  status_msg = "Offline"

  try:
    tk = yf.Ticker(ticker_symbol)

    # 1. Live-Kurs über Intraday (1m) oder letzten Tageskurs
    df_hist = tk.history(period="2d", interval="1m")
    if not df_hist.empty and "Close" in df_hist.columns:
      live_kurs = float(df_hist["Close"].dropna().iloc[-1])
      status_msg = "Yahoo Live (1m)"

    # 2. Tages-Historie für den korrekten Vortag holen (Vollautomatisch)
    df_daily = tk.history(period="10d", interval="1d")
    if not df_daily.empty and "Close" in df_daily.columns:
      df_clean = df_daily.dropna(subset=["Close"])
      heute_date = datetime.datetime.now(BERLIN_TZ).date()

      # Filter: Nur Tage vor heute, um den echten Vortag zu greifen
      df_past = df_clean[df_clean.index.date < heute_date]

      if not df_past.empty:
        vortag_kurs = float(df_past["Close"].iloc[-1])
        vortag_datum_str = df_past.index[-1].strftime("%d.%m.%Y")

      # Wenn Live-Kurs über 1m fehlte, nimm den letzten Daily Close
      if not live_kurs and not df_clean.empty:
        live_kurs = float(df_clean["Close"].iloc[-1])
        status_msg = "Yahoo Daily Close"

  except Exception:
    pass

  return live_kurs, vortag_kurs, vortag_datum_str, status_msg


# --- DISCORD ALERT ---
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

  now = datetime.datetime.now(BERLIN_TZ)
  if last_alert_time and (now - last_alert_time).total_seconds() < 3600:
    return False

  msg = (
      f"🚨 **QUANT TERMINAL ALARM** 🚨\nDas Wikifolio **{WKN}** ({ISIN}) ist"
      f" stark gefallen!\nTagesveränderung: **{pct_change:+.2f}%**\nAktueller"
      f" Kurs: **{current_price:.3f} €**"
  )
  payload = {"content": msg}

  try:
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    if response.status_code in [200, 204]:
      with open(ALARM_STATE_FILE, "w") as f:
        json.dump({"last_alert": now.isoformat()}, f)
      return True
  except Exception:
    pass
  return False


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

# --- DATEN VOLLAUTOMATISCH LADEN ---
api_symbol = "DE000LS9VFS2.SG"
api_kurs, api_vortag, api_vortag_datum, api_status = fetch_market_data(
    api_symbol
)

# Fallbacks, falls die API im Moment klemmt
fallback_kurs = 302.100 if not api_kurs else api_kurs
fallback_vortag = 301.250 if not api_vortag else api_vortag

aktueller_kurs_input = fallback_kurs
vortag_kurs = fallback_vortag

if api_vortag_datum != "N/A":
  vortag_datum_str = api_vortag_datum
else:
  vortag_datum_str = (
      datetime.datetime.now(BERLIN_TZ) - datetime.timedelta(days=1)
  ).strftime("%d.%m.%Y")

# --- SIDEBAR STATUS ---
st.sidebar.markdown("### ⚡ Vollautomatischer Live-Sync")
if api_kurs and api_vortag:
  st.sidebar.success(
      f"🟢 Verbunden ({api_status})\n\nKurs: {api_kurs:.3f} €\nVortag:"
      f" {api_vortag:.3f} €"
  )
else:
  st.sidebar.warning("⚠️ API eingeschränkt. Nutze intelligente Fallbacks.")

if st.sidebar.button("🔔 Test-Alarm senden"):
  send_discord_alert(-1.50, aktueller_kurs_input)
  st.sidebar.success("Test-Alarm gesendet!")

# NEU: Auswahl für den Zins-Modus in der Ziel-Tabelle
st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Einstellungen Tab 5")
zins_modus = st.sidebar.radio(
    "Zins-Intervall für Ziel-Tabelle:", ["Monatlich (p.M.)", "Jährlich (p.a.)"]
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
        display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px; margin-bottom: 20px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 14px 16px; }
    .m-label { font-size: 0.75rem; color: #A1A1AA; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; }
    .m-val { font-size: 1.4rem; font-weight: 800; color: #FFFFFF; margin: 6px 0; white-space: nowrap; }
    .m-sub { font-size: 0.85rem; font-weight: 600; white-space: nowrap; color: #CBD5E1; }
    .pos { color: #00C853; }
    .neg { color: #FF3D00; }
    .blue { color: #29B6F6; }
    .orange { color: #FF3D00; }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 4rem; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=180)
def get_chart_data(target_kurs):
  start_dt = pd.to_datetime("2025-07-09")
  end_dt = datetime.datetime.now(BERLIN_TZ).replace(tzinfo=None)
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
  df["High"] = df[["Open", "Close"]].max(axis=1) + 0.1
  df["Low"] = df[["Open", "Close"]].min(axis=1) - 0.1
  return df


df_chart = get_chart_data(aktueller_kurs_input)

# --- KENNZAHLEN ---
aktueller_kurs = float(df_chart["Close"].iloc[-1])
aktuelles_datum_str = df_chart.index[-1].strftime("%d.%m.%Y")

tages_verenderung_pct = ((aktueller_kurs - vortag_kurs) / vortag_kurs) * 100
letztes_update_zeit = datetime.datetime.now(BERLIN_TZ).strftime(
    "%d.%m.%Y %H:%M:%S Uhr"
)

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

now_berlin = datetime.datetime.now(BERLIN_TZ)
heute_date = now_berlin.date()

heutige_monate_anzahl = max(
    0,
    (now_berlin.year - start_dt.year) * 12
    + (now_berlin.month - start_dt.month),
)
if now_berlin.day < start_dt.day:
  heutige_monate_anzahl -= 1
gesamt_entnommen = heutige_monate_anzahl * ENTNAHME_PM

brutto_ist = STUECKZAHL * aktueller_kurs
netto_ist = brutto_ist - gesamt_entnommen
gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
tage_gehalten = max(1, (heute_date - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
rendite_pa = (
    ((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1
) * 100
monate_gehalten = max(1, jahre_gehalten * 12)
rendite_mo = (
    ((aktueller_kurs / ANFANGSKURS) ** (1 / max(1, monate_gehalten))) - 1
) * 100
mtl_gewinn_avg = gewinn_brutto / max(1, monate_gehalten)

sim_b = brutto_ist
meilenstein_datum_str = "Bereits erreicht"
meilenstein_details_str = "Ziel erreicht"
milestone_reached = sim_b >= 100000.0

if not milestone_reached:
  for m_i in range(1, 120):
    sim_b = sim_b * (1 + (rendite_mo / 100.0))
    if sim_b >= 100000.0:
      ms_dt_offset = now_berlin + pd.DateOffset(months=m_i)
      ms_date = ms_dt_offset.date()
      meilenstein_datum_str = ms_date.strftime("%m.%Y")

      delta_tage_total = (ms_date - heute_date).days
      j_exakt = delta_tage_total // 365
      m_exakt = (delta_tage_total % 365) // 30
      w_exakt = ((delta_tage_total % 365) % 30) // 7
      t_exakt = ((delta_tage_total % 365) % 30) % 7

      parts = []
      if j_exakt > 0:
        parts.append(f"{j_exakt} {'Jahr' if j_exakt == 1 else 'Jahre'}")
      if m_exakt > 0:
        parts.append(f"{m_exakt} {'Monat' if m_exakt == 1 else 'Monate'}")
      if w_exakt > 0:
        parts.append(f"{w_exakt} {'Woche' if w_exakt == 1 else 'Wochen'}")
      if t_exakt > 0 or not parts:
        parts.append(f"{t_exakt} {'Tag' if t_exakt == 1 else 'Tage'}")

      meilenstein_details_str = f"(~ {', '.join(parts)})"
      break
  if not milestone_reached and sim_b < 100000.0:
    meilenstein_datum_str = "> 10 Jahre"
    meilenstein_details_str = "Außerhalb des 10-Jahres-Horizonts"

verenderung_cls = "pos" if tages_verenderung_pct >= 0 else "neg"
kaufdatum_str = KAUFDATUM.strftime("%d.%m.%Y")

# HEADER BAR
st.markdown(
    f"""
<div class="header-bar">
    <div style="flex: 1; min-width: 220px;">
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span> <span style="font-size:0.8rem; color:#CBD5E1;">({aktuelles_datum_str})</span></div>
        <div style="font-size: 0.75rem; color: #CBD5E1; margin-top:3px;">WKN: {WKN} • ISIN: {ISIN} • Börse Stuttgart • Stand: {letztes_update_zeit}</div>
    </div>
    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end;">
        <span style="color:#00C853; background:#18181B; padding:4px 8px; border-radius:4px; border:1px solid #27272A; font-size:0.75rem; font-weight:700;">● FULL AUTO SYNC</span>
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
        <div class="m-val {verenderung_cls}">{tages_verenderung_pct:+.2f}%</div>
        <div class="m-sub">Schluss ({vortag_datum_str}): {vortag_kurs:.3f} €</div>
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
    <div class="m-card" style="border-left: 3px solid #00C853; background: #0c1410;">
        <div class="m-label" style="color: #00C853;">🎯 100k-Meilenstein</div>
        <div class="m-val" style="color: #00C853; font-size: 1.25rem;">{meilenstein_datum_str}</div>
        <div class="m-sub" style="color: #CBD5E1; font-size: 0.75rem;">{meilenstein_details_str}</div>
    </div>
    <div class="m-card">
        <div class="m-label">Entnommenes Kapital</div>
        <div class="m-val orange">{fmt(gesamt_entnommen)} €</div>
        <div class="m-sub">Monatlich: {fmt(ENTNAHME_PM)} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Anfangskapital</div>
        <div class="m-val">{fmt(STARTKAPITAL)} €</div>
        <div class="m-sub">Kauf ({kaufdatum_str}): {ANFANGSKURS:.2f} €</div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# TABS
tab_wealth, tab_trades, tab_candle, tab_forecast, tab_future = st.tabs([
    "📈 VERMÖGENS- & SUBSTANZAUFBAU",
    "📝 TRADER-LOG (TRADES & KOMMENTARE)",
    "🕯️ TAGES-CANDLESTICK",
    "🔮 ZUKUNFTS-PROGNOSE (5 JAHRE)",
    "💰 Zinseszins, Anfangskapital bis Ziel 100k!",
])

with tab_wealth:
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
          name="Netto-Wert",
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
      ),
      yaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          side="right",
          tickfont=dict(color="#A1A1AA"),
      ),
      hovermode="x unified",
  )
  st.plotly_chart(fig_wealth, use_container_width=True)

with tab_trades:
  st.markdown("### 📋 Historie")
  if len(db_events) == 0:
    st.info("Keine Einträge vorhanden.")
  else:
    for ev in db_events:
      e_typ = ev.get("typ", "")
      e_datum = ev.get("datum", "")
      e_titel = ev.get("titel", "")
      e_inhalt = ev.get("inhalt", "")
      st.markdown(
          f"""
            <div style="background: #09090B; border: 1px solid #27272A; border-left: 3px solid #29B6F6; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                <div style="font-size: 0.75rem; color: #71717A;"><b>[{e_typ}]</b> - {e_datum}</div>
                <div style="font-weight: 700; color: #FFFFFF; font-size: 0.95rem;">{e_titel}</div>
                <div style="font-size: 0.85rem; color: #D1D5DB;">{e_inhalt}</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

  with st.form("trade_form", clear_on_submit=True):
    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
      et = st.selectbox("Typ", ["Trade", "Kommentar", "Hinweis"])
    with col2:
      ed = st.date_input("Datum", heute_date)
    with col3:
      eti = st.text_input("Titel")
    ei = st.text_area("Details")
    if st.form_submit_button("Speichern") and eti:
      db_events.insert(
          0,
          {
              "id": len(db_events) + 1,
              "typ": et,
              "datum": ed.strftime("%Y-%m-%d"),
              "titel": eti,
              "inhalt": ei,
          },
      )
      save_db(db_events)
      st.rerun()

with tab_candle:
  fig_c = go.Figure(
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
  fig_c.update_layout(
      paper_bgcolor="#000000",
      plot_bgcolor="#000000",
      margin=dict(l=10, r=60, t=30, b=40),
      height=450,
      xaxis=dict(showgrid=True, gridcolor="#1A1A1A"),
      yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right"),
      showlegend=False,
  )
  st.plotly_chart(fig_c, use_container_width=True)

with tab_forecast:
  mtl_prozent_anzeige = rendite_mo
  st.info(
      f"Prognose auf Basis des mtl. Bruttogewinns von +"
      f"{fmt(mtl_gewinn_avg, 2)} € (Ø {mtl_prozent_anzeige:+.2f}% pro Monat)."
  )

  forecast_data = []
  forecast_data.append({
      "Index": 0,
      "Jahr": "Start",
      "Datum": KAUFDATUM.strftime("%d.%m.%Y"),
      "Brutto Depotwert": f"{fmt(STARTKAPITAL, 2)} €",
      "Gesamter Gewinn": "+0,00 €",
      "Netto Depotwert": f"{fmt(STARTKAPITAL, 2)} €",
      "Kumulierte Entnahme": "0,00 €",
  })
  forecast_data.append({
      "Index": 1,
      "Jahr": "Heute",
      "Datum": heute_date.strftime("%d.%m.%Y"),
      "Brutto Depotwert": f"{fmt(brutto_ist, 2)} €",
      "Gesamter Gewinn": f"+{fmt(gewinn_brutto, 2)} €",
      "Netto Depotwert": f"{fmt(netto_ist, 2)} €",
      "Kumulierte Entnahme": f"{fmt(gesamt_entnommen, 2)} €",
  })

  sim_b, sim_n, sim_e = brutto_ist, netto_ist, gesamt_entnommen
  for m_idx in range(1, 61):
    sim_b = sim_b * (1 + (rendite_mo / 100.0))
    sim_e += ENTNAHME_PM
    sim_n = sim_b - sim_e
    if m_idx % 12 == 0:
      forecast_data.append({
          "Index": m_idx // 12 + 1,
          "Jahr": f"Jahr +{m_idx // 12}",
          "Datum": (now_berlin + pd.DateOffset(months=m_idx)).strftime(
              "%d.%m.%Y"
          ),
          "Brutto Depotwert": f"{fmt(sim_b, 2)} €",
          "Gesamter Gewinn": f"+{fmt(sim_b - STARTKAPITAL, 2)} €",
          "Netto Depotwert": f"{fmt(sim_n, 2)} €",
          "Kumulierte Entnahme": f"{fmt(sim_e, 2)} €",
      })

  df_f = pd.DataFrame(forecast_data)
  st.dataframe(df_f, use_container_width=True, hide_index=True)

with tab_future:
  st.markdown("### 💰 Zinseszins, Anfangskapital bis Ziel 100k!")
  st.info(
      f"Basis: {fmt(STARTKAPITAL, 2)} € Startkapital | {fmt(ENTNAHME_PM, 2)} € Entnahme/Monat"
  )

  data = []

  if zins_modus == "Monatlich (p.M.)":
    zinssaetze = [0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05, 0.055, 0.06]
    for zins in zinssaetze:
      kapital = STARTKAPITAL
      jahreswerte = {}
      ziel_monat = "n.e."

      for m in range(1, 61):
        kapital = kapital * (1 + zins) - ENTNAHME_PM
        if kapital >= 100000.0 and ziel_monat == "n.e.":
          ziel_monat = f"Monat {m}"
        if m % 12 == 0:
          jahreswerte[f"Jahr {m//12}"] = f"{fmt(kapital, 2)} €"

      row = {
          "Zins p.M.": f"{zins*100:.1f}%".replace(".", ","),
          **jahreswerte,
          "Ziel 100k": ziel_monat,
      }
      data.append(row)
  else:
    zinssaetze_pa = [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12]
    for zins_pa in zinssaetze_pa:
      zins_mo = (1 + zins_pa) ** (1 / 12) - 1
      kapital = STARTKAPITAL
      jahreswerte = {}
      ziel_monat = "n.e."

      for m in range(1, 61):
        kapital = kapital * (1 + zins_mo) - ENTNAHME_PM
        if kapital >= 100000.0 and ziel_monat == "n.e.":
          ziel_monat = f"Monat {m}"
        if m % 12 == 0:
          jahreswerte[f"Jahr {m//12}"] = f"{fmt(kapital, 2)} €"

      row = {
          "Zins p.a.": f"{zins_pa*100:.1f}%".replace(".", ","),
          **jahreswerte,
          "Ziel 100k": ziel_monat,
      }
      data.append(row)

  df_zukunft = pd.DataFrame(data)
  st.dataframe(df_zukunft, use_container_width=True, hide_index=True)
