import datetime
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# Seite konfigurieren
st.set_page_config(
    page_title="Wikifolio Live-Tracking", 
    layout="wide"
)

st.title("📈 Wikifolio Live-Performance vs. Modellpfade")

# Parameter auf Basis deiner Daten
KAUFDATUM = datetime.date(2025, 8, 7)
EINSTIEGSKURS = 160.68
STARTKAPITAL = 20000.0
ENTNAHME_PM = 180.0
TICKER = "LS9VFS.SG"

try:
    # Historic-Daten ab Kaufdatum laden
    df = yf.download(TICKER, start=KAUFDATUM)

    if df.empty:
        st.error(f"Keine Kursdaten für Ticker '{TICKER}' gefunden. Bitte überprüfe das Symbol.")
    else:
        # Datenlücken (z. B. Wochenenden/Feiertage) mit dem letzten verfügbaren Wert auffüllen
        df["Close"] = df["Close"].ffill()

        # Letzten verfügbaren Kurs & Datum ermitteln
        letzter_kurs = float(df["Close"].iloc[-1])
        letztes_datum = df.index[-1].strftime("%d.%m.%Y")

        # Live-Performance berechnen
        df["Performance_%"] = ((df["Close"] - EINSTIEGSKURS) / EINSTIEGSKURS) * 100
        aktuelle_perf = float(df["Performance_%"].iloc[-1])

        # Status-Box im Dashboard anzeigen
        st.info(f"📅 **Stand:** {letztes_datum} | 💰 **Letzter Kurs:** {letzter_kurs:.2f} € ({aktuelle_perf:+.2f}%)")

        # Interactive Chart erstellen
        fig = go.Figure()

        # Echtdaten-Kurve hinzufügen
        fig.add_trace(go.Scatter(
            x=df.index, 
            y=df["Performance_%"], 
            mode="lines", 
            name="Tatsächlicher Verlauf",
            line=dict(color="#00FF7F", width=2)
        ))

        # Nulllinie (Einstieg)
        fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Einstieg")

        # Layout anpassen
        fig.update_layout(
            title="Performance-Entwicklung ab Kaufdatum (%)",
            xaxis_title="Datum",
            yaxis_title="Gewinn / Verlust in %",
            template="plotly_dark",
            hovermode="x unified"
        )

        # Chart rendern
        st.plotly_chart(fig, use_container_width=True)

        # Kennzahlen-Übersicht darunter anzeigen
        col1, col2, col3 = st.columns(3)
        col1.metric("Einstiegskurs", f"{EINSTIEGSKURS:.2f} €")
        col2.metric("Aktueller Kurs", f"{letzter_kurs:.2f} €", f"{aktuelle_perf:+.2f}%")
        col3.metric("Monatl. Entnahme", f"{ENTNAHME_PM:.2f} €")

except Exception as e:
    st.error(f"Fehler beim Abrufen der Marktdaten: {e}")
