import datetime
import pandas as pd
import streamlit as st
import yfinance as yf


def get_latest_wikifolio_price(isin="DE000LS9VFS2"):
  """Holt den Realtime-Kurs oder den letzten verfügbaren Kurs (bei Wochenende/Feiertag)."""
  try:
    # Wikifolios lassen sich oft über Yahoo Finance mit .F (Frankfurt) oder direkt abfragen.
    # Alternativ nutzen wir hier das Ticker-Symbol für Lang & Schwarz / Frankfurt.
    # Falls das Symbol abweicht, nutzen wir die ISIN direkt.
    ticker = yf.Ticker(f"{isin}.F")
    df = ticker.history(period="5d")

    if not df.empty:
      # Letzter verfügbarer Schlusskurs (greift automatisch auf Freitag zurück, wenn heute Sonntag ist)
      latest_row = df.iloc[-1]
      price = latest_row["Close"]
      date = df.index[-1].strftime("%Y-%m-%d")
      return price, date
    else:
      # Fallback: Yahoo Finance Standard Abfrage
      todays_data = yf.download(isin, period="2d", progress=False)
      if not todays_data.empty:
        price = float(todays_data["Close"].iloc[-1])
        date = todays_data.index[-1].strftime("%Y-%m-%d")
        return price, date
  except Exception as e:
    st.error(f"Fehler beim Laden des Kurses: {e}")

  return None, None


# --- Einbindung in deine UI (z.B. im Header-Bereich) ---
isin_code = "DE000LS9VFS2"
current_price, price_date = get_latest_wikifolio_price(isin_code)

# Header-Anzeige analog zu deinem Screenshot
st.markdown(
    f"""
    <div style="background: #09090B; border: 1px solid #27272A; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
        <div style="font-size: 1.25rem; font-weight: 700; color: #FFFFFF;">
            HAUPTINDIZES GLOBAL <span style="color: #00C853;">{current_price:,.3f} €</span>
        </div>
        <div style="font-size: 0.85rem; color: #71717A; margin-top: 4px;">
            WKN: LS9VFS • ISIN: {isin_code} • Kursstand vom: {price_date}
        </div>
    </div>
""",
    unsafe_allow_html=True,
)
