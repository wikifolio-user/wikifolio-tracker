"""Pyramidenmanager Etappe 3 - Ansicht „Backtest A–D“ (Rechenkern: pyramide_backtest.py)."""
import datetime
import html
import json

import streamlit as st

import fear_greed as FG
import gap_analyzer as G
import pyramide as P
import pyramide_backtest as B
import pyramide_daten as D
import ui_stil as UI

K = "pyr_bt_"
FARBEN = {"A": "#7c9cff", "B": "#34D399", "C": "#FBBF24", "D": "#F472B6", "halten": "#A9ACB0"}


def _de(x, n=1, einheit=""):
    if x is None:
        return "–"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".") + einheit


@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
def _rechnen(kerzen_json, impl_json, code, cfg_json, param_json, von, bis, definition):
    kerzen, _ = G.kerzen_pruefen(json.loads(kerzen_json))
    impl = json.loads(impl_json) if impl_json else None
    return B.backtest(kerzen, code, json.loads(cfg_json), json.loads(param_json), von, bis, impl,
                      definition=definition)


def _tabelle(erg):
    import pandas as pd
    zeilen = []
    for s in list(B.STRATEGIEN) + ["halten"]:
        x = erg.get(s)
        if not x:
            continue
        name = f"{s} · {B.STRATEGIEN[s]}" if s in B.STRATEGIEN else "Kaufen & Halten (Vergleich)"
        zeilen.append({
            "Strategie": name, "Endwert €": round(x["endwert"]), "Rendite %": round(x["rendite_pct"], 1),
            "p. a. %": round(x["cagr_pct"], 1), "Max. Drawdown %": round(x["max_dd_pct"], 1),
            "Zeit im Markt %": round(x["zeit_im_markt_pct"]),
            "Pyramiden": x.get("pyramiden"), "Tranchen": x.get("tranchen"),
            "Trefferquote %": round(x["trefferquote_pct"]) if x.get("trefferquote_pct") is not None else None,
            "Ø Gewinn €": round(x["gewinn_schnitt"]) if x.get("gewinn_schnitt") is not None else None,
            "Ø Verlust €": round(x["verlust_schnitt"]) if x.get("verlust_schnitt") is not None else None,
            "Profit-Faktor": round(x["profit_faktor"], 2) if x.get("profit_faktor") is not None else None,
            "Kosten €": round(x["kosten"]) if x.get("kosten") is not None else None,
            "KO-Ereignisse": x.get("ko_ereignisse"),
            "Index 20 T nach Einstieg %": round(x["signal_qualitaet_pct"], 2)
            if x.get("signal_qualitaet_pct") is not None else None,
            "davon positiv %": round(x["signal_treffer_pct"]) if x.get("signal_treffer_pct") is not None else None,
            "Signaltage gefiltert": f"{x['blockiert']} von {x['signale']}" if "signale" in x else None})
    df = pd.DataFrame(zeilen)
    st.dataframe(df, hide_index=True, width="stretch", key=K + "tab")


def _chart(erg):
    import plotly.graph_objects as go
    fig = go.Figure()
    for s in list(B.STRATEGIEN) + ["halten"]:
        x = erg.get(s)
        if not x:
            continue
        fig.add_trace(go.Scatter(x=[d for d, _ in x["kurve"]], y=[w for _, w in x["kurve"]], mode="lines",
                                 name=s if s in B.STRATEGIEN else "Halten",
                                 line={"color": FARBEN[s], "width": 1.6 if s in B.STRATEGIEN else 1.0,
                                       "dash": "solid" if s in B.STRATEGIEN else "dot"}))
    fig.update_layout(height=360, margin={"l": 10, "r": 10, "t": 10, "b": 10}, yaxis_title="Depotwert €",
                      legend={"orientation": "h", "y": -0.15})
    st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), width="stretch", key=K + "chart",
                    config={"displayModeBar": False})


def _details(erg):
    import pandas as pd
    for s in B.STRATEGIEN:
        x = erg.get(s)
        if not x:
            continue
        with st.expander(f"{s} · {B.STRATEGIEN[s]}: {x['pyramiden']} Pyramiden, {x['ko_ereignisse']} Knock-outs"):
            if x["liste"]:
                st.dataframe(pd.DataFrame([{
                    "Start": p["start"], "Ende": p["ende"] or "läuft", "Stufen": p["stufen"],
                    "Einsatz €": round(p["einsatz"]), "Ergebnis €": round(p["ergebnis"]),
                    "Kosten €": round(p["kosten"]), "Knock-outs": p["ko"], "Grund": p["grund"]}
                    for p in reversed(x["liste"])]), hide_index=True, width="stretch", key=K + f"liste_{s}")
            aus = [e for e in x["ereignisse"] if e["art"] == "ko"]
            if aus:
                st.caption("Knock-outs: " + "; ".join(f"{e['datum']} {html.escape(e['text'])}" for e in aus[-20:]))
            weg = sum(1 for e in x["ereignisse"] if e["art"] == "kauf_ausgelassen")
            if weg:
                st.caption(f"{weg} Käufe ausgelassen (Risiko- oder Kapitalgrenze bzw. kein passender Hebel).")


def bereich(ohlc):
    ss = st.session_state
    st.markdown("**Backtest A–D** – dieselben Regeln wie live, Tag für Tag nur mit den Daten bis zu diesem Tag")
    idx = (ohlc or {}).get("indizes") or {}
    codes = [c for c, (sym, *_) in D.ZUORDNUNG.items() if (idx.get(sym) or {}).get("kerzen")]
    if not codes:
        st.info("Keine Tageskerzen vorhanden.")
        return
    sp = st.columns(4) if not UI.ist_smartphone() else [st.container() for _ in range(4)]
    code = sp[0].selectbox("Index", codes, key=K + "index",
                           format_func=lambda c: f"{c} · {G.INDEX.get(D.ZUORDNUNG[c][0], (c, c))[1]}")
    art = sp[1].segmented_control("Umsetzung", ["direkt", "ko"], default="direkt", key=K + "art",
                                  format_func=lambda a: "ungehebelt" if a == "direkt" else "KO-Zertifikate") or "direkt"
    kapital = sp[2].number_input("Startkapital €", 1000, 10_000_000, 10000, step=1000, key=K + "kapital")
    definition = sp[3].selectbox("Gap-Art", list(G.DEFINITIONEN), format_func=G.DEFINITIONEN.get, key=K + "def")
    sym = D.ZUORDNUNG[code][0]
    kerzen = idx[sym]["kerzen"]
    erstes = datetime.date.fromisoformat(kerzen[min(len(kerzen) - 1, P.MIN_KERZEN)][0])
    letztes = datetime.date.fromisoformat(kerzen[-1][0])
    sp = st.columns(4) if not UI.ist_smartphone() else [st.container() for _ in range(4)]
    von = sp[0].date_input("Von", erstes, min_value=erstes, max_value=letztes, key=K + "von", format="DD.MM.YYYY")
    bis = sp[1].date_input("Bis", letztes, min_value=erstes, max_value=letztes, key=K + "bis", format="DD.MM.YYYY")
    spread = sp[2].number_input("Spread je Runde %", 0.0, 5.0, 0.1 if art == "direkt" else 0.3, step=0.05,
                                key=K + f"spread_{art}", help="Je zur Hälfte bei Kauf und Verkauf.")
    gebuehr = sp[3].number_input("Gebühr je Order €", 0.0, 50.0, 1.0, step=0.5, key=K + "gebuehr")
    hebel, fin = None, 3.0
    if art == "ko":
        sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
        fest = sp[0].number_input("Fester Hebel (0 = passender Hebel zum Stop)", 0.0, 20.0, 0.0, step=0.5,
                                  key=K + "hebel")
        hebel = fest if fest and fest > 1 else None
        fin = sp[1].number_input("Finanzierung % p. a.", 0.0, 15.0, 3.0, step=0.25, key=K + "fin")
    cfg = P.STANDARD
    st.caption(f"Regeln: Startwerte des Pyramidenmanagers (Einstieg ab Trend-Score {cfg['einstieg_ab']}, Ausstieg "
               f"unter {cfg['ausstieg_unter']}, Nachkauf ab +{_de(cfg['nachkauf_atr'])} ATR, Stop "
               f"{_de(cfg['stop_anfang_atr'])}/{_de(cfg['stop_nachzieh_atr'])} ATR, Risiko "
               f"{_de(cfg['risiko_tranche_pct'])} % je Tranche, {_de(cfg['risiko_gesamt_pct'])} % gesamt). Filter B/C: "
               f"Gap- bzw. Fear-&-Greed-Einstiegswert ab {B.FILTER_AB}; D: kombinierter Wert ab {cfg['einstieg_ab']}.")
    if st.button("📊 Backtest rechnen", key=K + "btn", type="primary", disabled=von >= bis):
        impl_sym = FG.IMPLIZIT.get(sym)
        impl = (idx.get(impl_sym) or {}).get("kerzen") if impl_sym else None
        param = {"kapital": float(kapital), "art": art, "hebel": hebel, "spread_pct": float(spread),
                 "gebuehr": float(gebuehr), "finanzierung_pa": float(fin)}
        try:
            with st.spinner("Rechne vier Strategien Tag für Tag …"):
                ss[K + "erg"] = dict(_rechnen(json.dumps(kerzen), json.dumps(impl) if impl else "", code,
                                              json.dumps(cfg), json.dumps(param), von.isoformat(), bis.isoformat(),
                                              definition), code=code, art=art)
        except ValueError as ex:
            st.warning(str(ex))
            ss.pop(K + "erg", None)
    erg = ss.get(K + "erg")
    if not erg:
        return
    st.markdown(f"**{erg['code']} · {_de(erg['tage'], 0)} Handelstage ({datetime.date.fromisoformat(erg['von']):%d.%m.%Y}"
                f" – {datetime.date.fromisoformat(erg['bis']):%d.%m.%Y}) · "
                f"{'KO-Zertifikate' if erg['art'] == 'ko' else 'ungehebelt'}**")
    _tabelle(erg)
    _chart(erg)
    _details(erg)
    st.caption(
        "So wurde gerechnet: Entscheidung am Tagesschluss, Ausführung zur Eröffnung des nächsten Tages. Trend-Score, "
        "ATR, Stops und Gap-Analyse (letzte 500 Handelstage) nur aus Kerzen bis zum jeweiligen Tag. Fear & Greed: "
        "eigener Rohwert als Perzentil gegen die eigenen Werte der drei Jahre davor – ohne die CNN-Eichung "
        f"(Abdeckung {_de(erg['fg_abdeckung_pct'], 0)} % der Tage; ohne Wert lässt C/D keinen Kauf zu). "
        "Größe je Tranche: Risiko bis zum Anfangsstop = Risiko-% × Stufenanteil des aktuellen Depotwerts, begrenzt "
        "durch das Gesamtrisiko. Vereinfachungen: KO = Basispreis, Finanzierung als Zins auf den Basispreis, kein "
        "Restwert nach Knock-out, keine Währungseffekte, Dividenden nur soweit im Index enthalten. "
        "„Index 20 T nach Einstieg“ misst die Signalqualität: Indexveränderung 20 Handelstage nach jedem Neueinstieg. "
        "Vergangene Ergebnisse sind keine Garantie für die Zukunft. Keine Anlageberatung.")
