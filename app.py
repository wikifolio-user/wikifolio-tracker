import datetime
import pandas as pd
import streamlit as st
import yfinance as yf


# Caching mit Streamlit, damit nicht bei jedem Klick eine Anfrage rausgeht (schützt vor Rate Limits)
@st.cache_data(ttl=600)  # Cacht das Ergebnis für 10 Minuten
def get_latest_wikifolio_price(isin="DE000LS9VFS2"):
  """Holt den Realtime-Kurs mit Fallback und Schutz vor Rate Limits."""
  try:
    ticker = yf.Ticker(f"{isin}.F")
    df = ticker.history(period="5d")

    if not df.empty:
      price = float(df["Close"].iloc[-1])
      date = df.index[-1].strftime("%Y-%m-%d")
      return price, date
  except Exception:
    pass

  try:
    # Alternativer Fallback über Direktabfrage
    todays_data = yf.download(isin, period="2d", progress=False)
    if not todays_data.empty:
      price = float(todays_data["Close"].iloc[-1])
      date = todays_data.index[-1].strftime("%Y-%m-%d")
      return price, date
  except Exception:
    pass

  return None, None


# --- Einbindung in deine UI mit Fehlerschutz ---
isin_code = "DE000LS9VFS2"
current_price, price_date = get_latest_wikifolio_price(isin_code)

# Falls Yahoo Finance blockiert, nehmen wir einen Platzhalter statt abzustürzen
if current_price is not None:
  price_text = f"{current_price:,.3f} €"
  date_text = f"Kursstand vom: {price_date}"
else:
  price_text = "Nicht verfügbar (Rate Limit)"
  date_text = "Bitte später versuchen"

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
