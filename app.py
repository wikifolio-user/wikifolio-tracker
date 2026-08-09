import datetime
import bs4
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# Seite konfigurieren
st.set_page_config(page_title="Wikifolio Live-Tracking", layout="wide")
st.title("📈 Wikifolio Live-Performance vs. Modellpfade")

# Parameter
ISIN = "DE000LS9VFS2"
TICKERS = ["LS9VFS.F", "LS9VFS.SG", "LS9VFS"]
KAUFDATUM = datetime.date(2025, 8, 7)
EINSTIEGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0

def get_ls_live_price(isin):
    """Holt den tagesaktuellen Kurs direkt von Lang & Schwarz."""
    try:
        url = f"https://www.ls-tc.de/de/zertifikat/{isin}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            soup = bs4.BeautifulSoup(res.text, "html.parser")
            price_element = soup.find("span", {"id": "price-val"})
            if price_element:
                raw_price = price_element.text.strip()
                clean_price = raw_price.replace(".", "").replace(",", ".")
                val = float(clean_price)
                if val > 0:
                    return val
    except Exception:
        pass
    return None

def fetch_historical_data():
    """Holt historische Daten mit Zeitpuffer für Wochenenden/Feiertage."""
    start_buffer = KAUFDATUM - datetime.timedelta(days=30)
    
    for ticker in TICKERS:
        try:
            df_ticker = yf.Ticker(ticker).history(start=start_buffer)
            if not df_ticker.empty and len(df_ticker) > 0:
                # Bereinigung und Sortierung
                df_ticker = df_ticker.sort_index()
                df_ticker["Close"] = df_ticker["Close"].ffill()
                # Nur Daten ab Kaufdatum filtern
                df_filtered = df_ticker[df_ticker.index.date >= KAUFDATUM].copy()
                if not df_filtered.empty:
                    return df_filtered, ticker
        except Exception:
            continue
    return None, None

# --- DATENBESCHAFFUNG ---
aktueller_kurs = get_ls_live_price(ISIN)
daten_quelle = "Lang & Schwarz (Echtzeit)"

df, verwendeter_ticker = fetch_historical_data()

# Fallback-Kette für den aktuellen Kurs
if aktueller_kurs is None:
    if df is not None and not df.empty:
        aktueller_kurs = float(df["Close"].iloc[-1])
        daten_quelle = f"Yahoo Finance ({verwendeter_ticker} - Letzter Schlusskurs)"
    else:
        aktueller_kurs = EINSTIEGSKURS
        daten_quelle = "Notfall-Fallback (Einstiegskurs)"

# --- DASHBOARD RENDERN ---
if df is not None and not df.empty:
    letztes_datum = df.index[-1].strftime("%d.%m.%Y")
    aktuelle_perf = ((aktueller_kurs - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
    df["Performance_%"] = ((df["Close"] - EINSTIEGSKURS) / EINSTIEGSKURS) * 100

    # Status-Box
    st.info(
        f"📅 **Stand Daten:** {letztes_datum} | "
        f"💰 **Kurs ({daten_quelle}):** {aktueller_kurs:.2f} € ({aktuelle_perf:+.2f}%)"
    )

    # Interaktiver Chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, 
        y=df["Performance_%"], 
        mode="lines", 
        name="Tatsächlicher Verlauf",
        line=dict(color="#00FF7F", width=2)
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Einstieg")
    fig.update_layout(
        title="Performance-Entwicklung ab Kaufdatum (%)",
        xaxis_title="Datum",
        yaxis_title="Gewinn / Verlust in %",
        template="plotly_dark",
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Kennzahlen
    col1, col2, col3 = st.columns(3)
    col1.metric("Einstiegskurs", f"{EINSTIEGSKURS:.2f} €")
    col2.metric("Aktueller Kurs", f"{aktueller_kurs:.2f} €", f"{aktuelle_perf:+.2f}%")
    col3.metric("Monatl. Entnahme", f"{ENTNAHME_PM:.2f} €")

else:
    # Wenn alle historischen Datenquellen versagen, aber die App nutzbar bleiben soll
    st.warning("⚠️ Live-Chart derzeit nicht verfügbar (Wochenende/Börsenpause). Letzte bekannte Kennzahlen:")
    aktuelle_perf = ((aktueller_kurs - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Einstiegskurs", f"{EINSTIEGSKURS:.2f} €")
    col2.metric("Aktueller Kurs", f"{aktueller_kurs:.2f} €", f"{aktuelle_perf:+.2f}%")
    col3.metric("Monatl. Entnahme", f"{ENTNAHME_PM:.2f} €")
