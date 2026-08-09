import datetime
import json
import os
import requests
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
# ⚙️ DEINE DISCORD WEBHOOK URL (FEST EINGEBAUT)
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
        display: flex; justify-content: space-between; align-items: center;
        background: #09090B; border: 1px solid #27272A; border-left: 3px solid #00C853;
        border-radius: 6px; padding: 10px 14px; margin-bottom: 12px;
    }
    .header-title { font-size: 1.1rem; font-weight: 800; color: #FFFFFF; }
    
    .grid-container {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 10px; margin-bottom: 16px;
    }
    .m-card { background: #09090B; border: 1px solid #18181B; border-radius: 6px; padding: 10px 12px; }
    .m-label { font-size: 0.62rem; color: #71717A; text-transform: uppercase; letter-spacing: 0.5px; }
    .m-val { font-size: 1.25rem; font-weight: 800; color: #FFFFFF; margin: 3px 0; white-space: nowrap; }
    .m-sub { font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
    
    .pos { color: #00C853; }
    .neg { color: #FF3D00; }
    .dim { color: #71717A; }
    
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# --- DISCORD ALERT FUNCTION ---
def send_discord_alert(trade_data):
    """Sendet ein formatiertes Signal direkt in deinen Discord-Kanal."""
    if not DISCORD_WEBHOOK_URL:
        return

    action = trade_data['action']
    is_buy = "BUY" in action or "KAUF" in action
    color = 3066993 if is_buy else 15158332  # Grün für Kauf, Rot für Verkauf

    payload = {
        "username": "Wikifolio Signal Bot",
        "avatar_url": "https://www.wikifolio.com/favicon.ico",
        "embeds": [{
            "title": f"🚨 TRADE SIGNAL: {action}",
            "description": f"**{trade_data['name']}**",
            "color": color,
            "fields": [
                {"name": "Ausführungskurs", "value": f"**{trade_data['price']:.2f} €**", "inline": True},
                {"name": "Gewichtung", "value": f"**{trade_data['weight']:.2f}%**", "inline": True},
                {"name": "Ausgeführt am", "value": f"{trade_data['date_raw']}", "inline": False}
            ],
            "footer": {"text": "Quant Terminal // Wikifolio Realtime Monitoring"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Discord Fehler: {e}")

# --- ECHTE CHART- DATEN HOLEN ---
@st.cache_data(ttl=30)
def fetch_real_wikifolio_data():
    url = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/chartdata"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            points = res.json().get("ChartPoints", [])
            if points:
                df = pd.DataFrame(points)
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
                df = df.dropna(subset=['Date', 'Close']).sort_values('Date').set_index('Date')
                
                full_idx = pd.date_range(start=df.index.min(), end=datetime.datetime.now(), freq='D')
                df = df.reindex(full_idx)
                df['Close'] = df['Close'].ffill().bfill()
                
                df['Open'] = df['Close'].shift(1).fillna(df['Close'].iloc[0])
                df['High'] = df[['Open', 'Close']].max(axis=1)
                df['Low'] = df[['Open', 'Close']].min(axis=1)
                return df
    except Exception:
        pass

    idx = pd.date_range(start="2025-07-09", end=datetime.datetime.now(), freq='D')
    return pd.DataFrame({'Open': 300.338, 'High': 300.338, 'Low': 300.338, 'Close': 300.338}, index=idx)

# --- PERSISTENTE DB & TRADES VERARBEITUNG ---
def process_trades_and_notify():
    stored_trades = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                stored_trades = json.load(f)
        except Exception:
            stored_trades = {}

    url_trades = f"https://www.wikifolio.com/api/wikifolio/{WIKIFOLIO_SLUG}/tradehistory"
    headers = {"User-Agent": "Mozilla/5.0"}
    has_new = False

    try:
        res = requests.get(url_trades, headers=headers, timeout=5)
        if res.status_code == 200:
            for t in res.json():
                trade_id = f"TRADE_{t.get('ExecutionDate')}_{t.get('Name')}_{t.get('OrderType')}"
                
                # Wenn der Trade NEU ist (noch nie in der DB gespeichert)
                if trade_id not in stored_trades:
                    trade_data = {
                        'id': trade_id,
                        'action': str(t.get('OrderType', 'TRADE')).upper(),
                        'name': t.get('Name', 'Wertpapier'),
                        'price': t.get('ExecutionPrice', 0),
                        'weight': t.get('Weight', 0),
                        'date_raw': t.get('ExecutionDate'),
                        'first_seen': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # 1. In dauerhafte Datei eintragen
                    stored_trades[trade_id] = trade_data
                    has_new = True
                    
                    # 2. SOFORT DISCORD PUSH FEUERN
                    send_discord_alert(trade_data)

            # Auf Festplatte sichern
            if has_new:
                with open(DB_FILE, "w", encoding="utf-8") as f:
                    json.dump(stored_trades, f, ensure_ascii=False, indent=2)

    except Exception as e:
        st.warning(f"Abruf-Fehler: {e}")

    trade_list = list(stored_trades.values())
    for t in trade_list:
        t['date_dt'] = pd.to_datetime(t['date_raw'])
    trade_list.sort(key=lambda x: x['date_dt'], reverse=True)
    return trade_list

# AUTOMATISCHER REFRESH ALLE 60 SEKUNDEN
st.markdown("<script>setTimeout(function(){ window.location.reload(1); }, 60000);</script>", unsafe_allow_html=True)

# DATEN PROZESSIEREN
df_chart = fetch_real_wikifolio_data()
trade_list = process_trades_and_notify()

# KENNZAHLEN BERECHNUNG
aktueller_kurs = float(df_chart['Close'].iloc[-1])
tage_gehalten = max(1, (datetime.date.today() - KAUFDATUM).days)
jahre_gehalten = tage_gehalten / 365.25
monate_aktiv = max(1, int(round(tage_gehalten / 30.4375)))

brutto_ist = STUECKZAHL * aktueller_kurs
gesamt_entnommen = monate_aktiv * ENTNAHME_PM
netto_ist = brutto_ist - gesamt_entnommen
gewinn_brutto = brutto_ist - STARTKAPITAL
rendite_ist_pct = ((aktueller_kurs - ANFANGSKURS) / ANFANGSKURS) * 100
rendite_pa = (((aktueller_kurs / ANFANGSKURS) ** (1 / max(0.1, jahre_gehalten))) - 1) * 100

# HEADER BAR
st.markdown(f"""
<div class="header-bar">
    <div>
        <div class="header-title">HAUPTINDIZES GLOBAL <span class="pos">{aktueller_kurs:.3f} €</span></div>
        <div class="dim" style="font-size: 0.65rem; margin-top:2px;">WKN: {WKN} • ISIN: {ISIN} • Kaufdatum: {KAUFDATUM.strftime('%d.%m.%Y')}</div>
    </div>
    <div style="text-align: right;">
        <span style="color:#00C853; font-size:0.75rem; font-weight:800; background:#18181B; padding:3px 8px; border-radius:4px; border:1px solid #27272A;">● DISCORD LIVE MONITORING</span>
        <div class="pos" style="font-size: 0.85rem; font-weight: 800; margin-top: 4px;">+{rendite_ist_pct:.2f}% ({rendite_pa:.1f}% p.a.)</div>
    </div>
</div>
""", unsafe_allow_html=True)

# GRID OVERVIEW
st.markdown(f"""
<div class="grid-container">
    <div class="m-card">
        <div class="m-label">Echter Wikifolio Kurs</div>
        <div class="m-val pos">{aktueller_kurs:.2f} €</div>
        <div class="m-sub pos">+{aktueller_kurs - ANFANGSKURS:.2f} € vs. Kauf</div>
    </div>
    <div class="m-card">
        <div class="m-label">Brutto Depotwert</div>
        <div class="m-val">{brutto_ist:,.0f} €</div>
        <div class="m-sub pos">+{gewinn_brutto:,.0f} € Gewinn</div>
    </div>
    <div class="m-card">
        <div class="m-label">Netto (nach Entnahme)</div>
        <div class="m-val" style="color:#29B6F6;">{netto_ist:,.0f} €</div>
        <div class="m-sub dim">Entnommen: {gesamt_entnommen:,.0f} €</div>
    </div>
    <div class="m-card">
        <div class="m-label">Gesamtrendite</div>
        <div class="m-val pos">+{rendite_ist_pct:.2f}%</div>
        <div class="m-sub pos">+{rendite_pa:.1f}% p.a.</div>
    </div>
    <div class="m-card">
        <div class="m-label">Gespeicherte Trades</div>
        <div class="m-val" style="color:#F59E0B;">{len(trade_list)}</div>
        <div class="m-sub dim">Dauerhaft in DB</div>
    </div>
</div>
""", unsafe_allow_html=True)

# TEST-BUTTON FÜR DISCORD
if st.sidebar.button("🧪 Test-Discord-Signal senden"):
    test_trade = {
        'action': 'TEST-VERKAUF',
        'name': 'TEST-POSITION (SYSTEMTEST)',
        'price': 123.45,
        'weight': 5.0,
        'date_raw': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    send_discord_alert(test_trade)
    st.sidebar.success("Test-Nachricht gesendet! Prüfe Discord.")

# CHART
fig_line = go.Figure()
fig_line.add_trace(go.Scatter(x=df_chart.index, y=df_chart['Close'], mode='lines', name='Schlusskurs', line=dict(color='#00C853', width=2)))
fig_line.update_layout(
    paper_bgcolor='#000000', plot_bgcolor='#000000',
    margin=dict(l=10, r=60, t=10, b=10), height=380, showlegend=False,
    xaxis=dict(showgrid=True, gridcolor='#1A1A1A', type='date', tickfont=dict(color='#A1A1AA', size=10)),
    yaxis=dict(showgrid=True, gridcolor='#1A1A1A', side="right", tickfont=dict(color='#A1A1AA', size=10))
)
st.plotly_chart(fig_line, use_container_width=True)

# TRADES DISPLAY
st.subheader(f"⚡ Historischer Speichertrank & Live Trades ({len(trade_list)})")
if trade_list:
    for t in trade_list:
        color = "#00C853" if "BUY" in t['action'] or "KAUF" in t['action'] else "#FF3D00"
        st.markdown(f"""
        <div style="background:#09090B; border:1px solid #27272A; border-left:4px solid {color}; padding:10px; margin-bottom:8px; border-radius:4px;">
            <b style="color:{color}">[{t['action']}] {t['name']}</b> — Kurs: {t['price']:.2f} € | Gewichtung: {t['weight']:.2f}%
            <br><small style="color:#71717A">Ausgeführt am: {t['date_raw']} | Dauerhaft registriert: {t['first_seen']}</small>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("Warte auf erste Trades...")
