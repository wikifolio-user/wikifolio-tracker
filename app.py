import datetime
import bs4
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# Seite konfigurieren
st.set_page_config(page_title="Wikifolio Live-Tracking", layout="wide")
st.title("📈 Wikifolio Live-Performance vs. Modellpfade")

# Parameter
ISIN = "DE000LS9VFS2"
TICKER_YFINANCE = "LS9VFS.F"
KAUFDATUM = datetime.date(2025, 8, 7)
EINSTIEGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0

def get_ls_live_price(isin):
    """Holt den tagesaktuellen Kurs direkt von Lang & Schwarz."""
    try:
        url = f"https://www.ls-tc.de/de/zertifikat/{isin}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            soup = bs4.BeautifulSoup(res.text, "html.parser")
            price_element = soup.find("span", {"id": "price-val"})
            if price_element:
                raw_price = price_element.text.strip()
                clean_price = raw_price.replace(".", "").replace(",", ".")
                return float(clean_price)
    except Exception:
        pass
    return None

# 1. Primär: Live-Kurs von Lang & Schwarz abrufen
aktueller_kurs = get_ls_live_price(ISIN)
daten_quelle = "Lang & Schwarz (Echtzeit)"

# 2. Historische Daten von Yahoo Finance laden
df = None
try:
    ticker_obj = yf.Ticker(TICKER_YFINANCE)
    df = ticker_obj.history(start=KAUFDATUM)
    if df.empty:
        df = yf.Ticker("LS9VFS").history(start=KAUFDATUM)
except Exception:
    df = None

if df is not None and not df.empty:
    df["Close"] = df["Close"].ffill()
    
    # Falls Lang & Schwarz nicht geantwortet hat, Yahoo-Schlusskurs nutzen
    if aktueller_kurs is None:
        aktueller_kurs = float(df["Close"].iloc[-1])
        daten_quelle = "Yahoo Finance (Fallback)"
    
    letztes_datum = df.index[-1].strftime("%d.%m.%Y")
    
    # Berechnungen
    aktuelle_perf = ((aktueller_kurs - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
    df["Performance_%"] = ((df["Close"] - EINSTIEGSKURS) / EINSTIEGSKURS) * 100

    # Status-Box im Dashboard
    st.info(
        f"📅 **Stand:** {letztes_datum} | "
        f"💰 **Kurs ({daten_quelle}):** {aktueller_kurs:.2f} € ({aktuelle_perf:+.2f}%)"
    )

    # Chart erstellen
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

    # Kennzahlen-Übersicht
    col1, col2, col3 = st.columns(3)
    col1.metric("Einstiegskurs", f"{EINSTIEGSKURS:.2f} €")
    col2.metric("Aktueller Kurs", f"{aktueller_kurs:.2f} €", f"{aktuelle_perf:+.2f}%")
    col3.metric("Monatl. Entnahme", f"{ENTNAHME_PM:.2f} €")

else:
    if aktueller_kurs is not None:
        st.warning("Historische Chartdaten derzeit nicht verfügbar, aber Live-Kurs geladen.")
        st.metric("Aktueller Kurs (L&S)", f"{aktueller_kurs:.2f} €")
    else:
        st.error("Weder Lang & Schwarz noch Yahoo Finance lieferten Daten. Bitte später erneut versuchen.")
