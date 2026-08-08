import datetime
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Wikifolio Live-Tracking", layout="wide", page_icon="📈"
)
st.title("📈 Wikifolio Live-Performance vs. Modellpfade")

# Parameter auf Basis deiner Echtdaten
KAUFDATUM = datetime.date(2025, 8, 7)
EINSTIEGSKURS = 160.68
STARTKAPITAL = 20000.0  # Modell 4 (anpassbar)
ENTNAHME_PM = 180.0
TICKER = "LS9VFS.SG"

try:
    df = yf.Ticker(TICKER).history(start=KAUFDATUM)
    if not df.empty:
        df["Performance_%"] = (
            (df["Close"] - EINSTIEGSKURS) / EINSTIEGSKURS
        ) * 100
        df["Days"] = (df.index.date - KAUFDATUM).map(lambda x: x.days)
        df["Months"] = df["Days"] / 30.44
        df["Reales_Kapital"] = (
            STARTKAPITAL * (1 + df["Performance_%"] / 100)
        ) - (df["Months"] * ENTNAHME_PM)

        akt_kurs = df["Close"].iloc[-1]
        akt_kapital = df["Reales_Kapital"].iloc[-1]
        perf = df["Performance_%"].iloc[-1]

        c1, c2, c3 = st.columns(3)
        c1.metric("Aktueller Kurs", f"{akt_kurs:.2f} €", f"{perf:+.2f} %")
        c2.metric("Tatsächlicher Vermögensstand", f"{akt_kapital:,.2f} €")
        c3.metric(
            "Zielerreichung (100k €)", f"{(akt_kapital / 100000) * 100:.1f} %"
        )

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["Reales_Kapital"],
                mode="lines",
                name="Tatsächlicher Verlauf (Ist)",
                line=dict(color="#0284c7", width=3),
            )
        )
        fig.add_hline(
            y=100000,
            line_dash="dash",
            line_color="red",
            annotation_text="Ziel 100.000 €",
        )
        fig.update_layout(
            title=f"Realer Vermögensaufbau ab Kaufdatum ({KAUFDATUM.strftime('%d.%m.%Y')})",
            xaxis_title="Datum",
            yaxis_title="Kapitalstand (€)",
            template="plotly_white",
        )
        st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.error(f"Fehler beim Laden der Live-Daten: {e}")
