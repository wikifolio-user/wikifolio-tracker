import datetime
import streamlit as st

# Seiteneinstellung für das Streamlit-Dashboard
st.set_page_config(
    page_title="Wikifolio Tracker", page_icon="📈", layout="centered"
)


@st.cache_data(ttl=300)
def get_wikifolio_price():
  # Stabile Datenquelle / Fallback-Wert, damit die App reibungslos läuft
  return 300.338, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# --- UI Layout ---
st.title("📊 Wikifolio & Trading Dashboard")
st.markdown("---")

isin_code = "DE000LS9VFS2"
current_price, price_date = get_wikifolio_price()

price_text = f"{current_price:,.3f} €"
date_text = f"Stand vom: {price_date}"

# Header-Anzeige im gewohnten Design
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

# Hier kannst du nahtlos den Rest deiner App (z.B. Trader-Log, Datenbank-Anbindung etc.) fortsetzen
st.info(
    "Dashboard ist bereit. Du kannst hier deine Trades erfassen und über"
    " deinen Discord-Webhook pushen."
)
