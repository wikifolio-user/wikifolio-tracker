import datetime
import requests
import streamlit as st


@st.cache_data(ttl=300)  # Kurs für 5 Minuten cachen
def get_wikifolio_ls_price(isin="DE000LS9VFS2"):
  """Holt den Echtzeitkurs direkt über die offizielle Kurs-Schnittstelle."""
  try:
    # Direkte Abfrage der Lang & Schwarz Kursdaten (wird von Wikifolio genutzt)
    url = f"https://www.ls-tc.de/_api/stock/instrument/{isin}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    response = requests.get(url, headers=headers, timeout=5)

    if response.status_code == 200:
      data = response.json()
      # Extrahiere den aktuellen Preis
      price = float(data.get("price", {}.get("last", 0)))
      # Formatierter Zeitstempel
      date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

      if price > 0:
        return price, date_str
  except Exception:
    pass

  return None, None


# --- Ausführung & UI ---
isin_code = "DE000LS9VFS2"
current_price, price_date = get_wikifolio_ls_price(isin_code)

if current_price is not None:
  price_text = f"{current_price:,.3f} €"
  date_text = f"Live-Stand vom: {price_date}"
else:
  price_text = "300.338 €"  # Fallback auf deinen letzten bekannten Wert
  date_text = "Stand (Offline-Modus)"

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
