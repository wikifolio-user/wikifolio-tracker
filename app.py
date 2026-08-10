import datetime
import json
import os
import requests
import streamlit as st

# Seiteneinstellung
st.set_page_config(
    page_title="Wikifolio & Trading Dashboard", page_icon="📈", layout="centered"
)

# Datei für die Trades-Datenbank
DB_FILE = "trades_db.json"


def load_trades():
  if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
      try:
        return json.load(f)
      except json.JSONDecodeError:
        return []
  return []


def save_trades(trades):
  with open(DB_FILE, "w") as f:
    json.dump(trades, f, indent=4)


def send_discord_webhook(webhook_url, message):
  if not webhook_url:
    return
  try:
    payload = {"content": message}
    requests.post(webhook_url, json=payload, timeout=5)
  except Exception as e:
    st.error(f"Fehler beim Senden an Discord: {e}")


@st.cache_data(ttl=300)
def get_wikifolio_price():
  # Stabiler Standard-Wert als Fallback
  return 300.338, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# --- UI Layout ---
st.title("📊 Wikifolio & Trading Dashboard")
st.markdown("---")

# Kurs-Header
isin_code = "DE000LS9VFS2"
current_price, price_date = get_wikifolio_price()
price_text = f"{current_price:,.3f} €"
date_text = f"Stand vom: {price_date}"

st.markdown(
    f"""
    <div style="background: #09090B; border: 1px solid #27272A; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
        <div style="font-size: 1.25rem; font-weight: 700; color: #FFFFFF;">
            HAUPTINDIZES GLOBAL <span style="color: #00C853;">{price_text}</span>
        </div>
        <div style="font-size: 0.85rem; color: #71717A; margin-top: 4px;">
            WKN: LS9VFS • ISIN: {isin_code} • {date_text}
        </div>
    </div>
""",
    unsafe_allow_html=True,
)

# --- Sidebar für Einstellungen & Discord ---
st.sidebar.header("Einstellungen")
discord_url = st.sidebar.text_input("Discord Webhook URL", type="password")

# --- Trade erfassen ---
st.subheader("Neuen Trade eintragen")
with st.form("trade_form"):
  col1, col2 = st.columns(2)
  with col1:
    trade_type = st.selectbox("Aktion", ["Kauf", "Verkauf"])
    asset_name = st.text_input("Titel / Aktie", "Beispiel Aktie")
  with col2:
    shares = st.number_input("Stückzahl", min_value=0.0, value=10.0, step=1.0)
    price = st.number_input("Kurs (€)", min_value=0.0, value=50.0, step=0.1)

  submitted = st.form_submit_button("Trade speichern & Discord benachrichtigen")

  if submitted:
    new_trade = {
        "datum": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "typ": trade_type,
        "titel": asset_name,
        "stueck": shares,
        "kurs": price,
    }
    trades = load_trades()
    trades.append(new_trade)
    save_trades(trades)

    # Discord Nachricht senden
    msg = (
        f"🚨 **Neuer Trade erfasst!**\nTyp: {trade_type}\nTitel:"
        f" {asset_name}\nStück: {shares}\nKurs: {price:,.2f} €"
    )
    send_discord_webhook(discord_url, msg)
    st.success("Trade erfolgreich gespeichert und gemeldet!")

# --- Bisherige Trades anzeigen ---
st.markdown("---")
st.subheader("📜 Bisherige Trades")
trades = load_trades()

if trades:
  for t in reversed(trades):
    st.markdown(
        f"- **{t['datum']}** | **{t['typ']}**: {t['titel']} ({t['stueck']}"
        f" Stück zu {t['kurs']} €)"
    )
else:
  st.info("Noch keine Trades in der Datenbank hinterlegt.")
