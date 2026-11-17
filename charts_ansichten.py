"""Chart-Ansichten Vermoegensaufbau, Performance seit 2026 / seit 2021, eigene Vergleichswerte und Candlestick
(aus app.render_dashboard ausgelagert, Audit ARCH-01). Die Rumpfe sind unveraendert; was sie bisher aus dem
Funktionskontext von render_dashboard lasen (Depotdaten, Kursreihen, gemeinsame Hilfsfunktionen), bekommen sie
jetzt ausdruecklich als Woerterbuch k uebergeben. app.py ruft sie ueber gleichnamige Huellen auf.
"""
import config
import datetime
import formate as FMT
import pandas as pd
import plotly.graph_objects as go
import schritte
import streamlit as st
import ui_stil as UI

from depot_rechnen import berechne_performance_kennzahlen, fmt, haenge_live_punkt_an, perf_sortierwert


def vergleich_eigen(k):
    """Frueher _render_vergleich_eigen in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _vergleichswerte_verwalten = k['_vergleichswerte_verwalten']
    heute_date = k['heute_date']
    kennzahl_umschalter = k['kennzahl_umschalter']
    lade_benchmarks_mit_fortschritt = k['lade_benchmarks_mit_fortschritt']
    lade_vergleichswerte = k['lade_vergleichswerte']
    pct_ueber_tage = k['pct_ueber_tage']
    performance_tabelle_html = k['performance_tabelle_html']
    tab_wealth = k['tab_wealth']
    vergleich_farbe = k['vergleich_farbe']
    """Vermoegensaufbau fuer Benutzer ohne Hauptposition: eigene Vergleichswerte, symbolisch angelegt ab
    einem waehlbaren Datum."""
    with tab_wealth:
        werte = lade_vergleichswerte()
        _vergleichswerte_verwalten(offen=not werte)
        if not werte:
            st.info("📈 Noch keine Vergleichswerte – oben aus der Top-500-Liste übernehmen oder einen Wert "
                    "suchen. Sie werden gespeichert und lassen sich jederzeit wieder entfernen.")
            return
        KAPITAL = 10000.0
        c1, _ = st.columns([1, 2])
        ab = c1.date_input("Vergleich ab", value=heute_date - datetime.timedelta(days=365),
                           max_value=heute_date - datetime.timedelta(days=7), key="vgl_ab", format="DD.MM.YYYY")
        idx = pd.bdate_range(pd.Timestamp(ab), pd.Timestamp(heute_date))
        series, startdaten = lade_benchmarks_mit_fortschritt(idx, ab, KAPITAL)
        if not series:
            st.warning("Für die gewählten Werte liegen gerade keine Kursdaten vor – bitte später mit 🔄 erneut laden.")
            return
        liste = []
        for label, s_ in series.items():
            g = s_.dropna()
            if g.empty or g.iloc[0] <= 0:
                continue
            start_ = startdaten.get(label)
            start_ = start_.date() if hasattr(start_, "date") else ab
            gesamt, monatlich, jaehrlich, diff = berechne_performance_kennzahlen(g.iloc[0], g.iloc[-1], start_,
                                                                                  heute_date)
            liste.append({"Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich,
                          "_euro": diff, "_q": pct_ueber_tage(g, 91), "_h": pct_ueber_tage(g, 182),
                          "_n": pct_ueber_tage(g, 273), "_z": pct_ueber_tage(g, 365), "_gelistet_seit": start_})
        st.caption(f"📅 Symbolisch {fmt(KAPITAL, 0)} je Wert, angelegt am {ab.strftime('%d.%m.%Y')} "
                   "(spätere Auflage: ab dem ersten Kurs) · Ø/Jahr erst ab 1 Jahr, Ø/Mon. ab 30 Tagen")
        liste.sort(key=perf_sortierwert, reverse=True)
        _fokus = kennzahl_umschalter("fokus_vgl_eigen", liste)
        st.markdown(performance_tabelle_html(liste, fokus=_fokus), unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=idx, y=[KAPITAL] * len(idx), name="Startkapital",
                                 line=dict(color="#71717A", width=1.5, dash="dash")))
        for i, (label, s_) in enumerate(series.items()):
            fig.add_trace(go.Scatter(x=idx, y=s_, name=label, line=dict(color=vergleich_farbe(label, i), width=2)))
        fig.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40),
                          height=450, showlegend=True, legend=dict(orientation="h", y=-0.15),
                          xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                          yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"),
                                     ticksuffix=" €"),
                          hovermode="x unified")
        schritte.titel(st, "vergleich", 3)
        st.plotly_chart(UI.chart_stil(fig), width="stretch", key="chart_vgl_eigen", config={"displayModeBar": False})


def vermoegen(k):
    """Frueher _render_wealth in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _vergleichswerte_verwalten = k['_vergleichswerte_verwalten']
    ausgezahlt_ist = k['ausgezahlt_ist']
    benchmark_series = k['benchmark_series']
    benchmark_start_daten = k['benchmark_start_daten']
    depotwert_real_ist = k['depotwert_real_ist']
    df_chart = k['df_chart']
    einstand_aktiv = k['einstand_aktiv']
    entnahme_rate = k['entnahme_rate']
    gewinn_real = k['gewinn_real']
    haupt_name = k['haupt_name']
    heute_date = k['heute_date']
    is_live_history = k['is_live_history']
    kaufdatum_aktiv = k['kaufdatum_aktiv']
    kennzahl_umschalter = k['kennzahl_umschalter']
    lese_pills_auswahl_still = k['lese_pills_auswahl_still']
    notify_app_error = k['notify_app_error']
    pct_ueber_tage = k['pct_ueber_tage']
    performance_tabelle_html = k['performance_tabelle_html']
    pills_auswahl = k['pills_auswahl']
    rendite_pa_hochgerechnet = k['rendite_pa_hochgerechnet']
    rendite_pa_real = k['rendite_pa_real']
    sparplan_eingezahlt = k['sparplan_eingezahlt']
    startkapital_aktiv = k['startkapital_aktiv']
    tab_wealth = k['tab_wealth']
    vergleich_farbe = k['vergleich_farbe']
    zeige_chart_legende_liste = k['zeige_chart_legende_liste']
    try:
        with tab_wealth:
            _vergleichswerte_verwalten()
            if not is_live_history:
                st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – der Vermögensverlauf "
                           "kann nicht gezeichnet werden. Bitte später mit 🔄 erneut laden.")
                return
            # Auswahl still aus dem gespeicherten Zustand lesen (Standard: alle an) -
            # der sichtbare Auswahl-Bereich selbst steht weiter unten, direkt vor dem Chart.
            ausgewaehlte_benchmarks = lese_pills_auswahl_still(benchmark_series.keys(), key="benchmark_pills")

            performance_liste_haupt = []
            kurs_reihe = df_chart["Close"]
            # Eigene Zeile = dieselben Zahlen wie die Depotkachel (Audit A-08/A-09/A-12):
            # Gesamt/Ø gegen den Einstand inkl. Sparraten, Ergebnis inkl. ausgezahlter
            # Entnahmen. Die Zeitraum-Spalten zeigen - wie bei den Vergleichswerten - die
            # Kursentwicklung (Ein-/Auszahlungen wuerden sie sonst verzerren).
            if not kurs_reihe.empty and einstand_aktiv > 0:
                gesamt, monatlich, jaehrlich, _ = berechne_performance_kennzahlen(
                    einstand_aktiv, depotwert_real_ist + ausgezahlt_ist, kaufdatum_aktiv, heute_date
                )
                # Ø/Jahr und Ø/Monat aus derselben (geldgewichteten) Rendite wie die Kachel
                jaehrlich = rendite_pa_real if not rendite_pa_hochgerechnet else None
                monatlich = (((1 + rendite_pa_real / 100) ** (1 / 12) - 1) * 100
                             if rendite_pa_real is not None else None)
                performance_liste_haupt.append({
                    "Wert": f"{haupt_name} ({config.WKN})",
                    "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": gewinn_real,
                    "_q": pct_ueber_tage(kurs_reihe, 91),
                    "_h": pct_ueber_tage(kurs_reihe, 182),
                    "_n": pct_ueber_tage(kurs_reihe, 273),
                    "_z": pct_ueber_tage(kurs_reihe, 365),
                    "_gelistet_seit": kaufdatum_aktiv,
                })
            for label, s in benchmark_series.items():
                s_gueltig = s.dropna()
                if label in ausgewaehlte_benchmarks and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                    start_dieser_wert = benchmark_start_daten.get(label)
                    start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else kaufdatum_aktiv
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                    )
                    performance_liste_haupt.append({
                        "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_q": pct_ueber_tage(s_gueltig, 91),
                        "_h": pct_ueber_tage(s_gueltig, 182),
                        "_n": pct_ueber_tage(s_gueltig, 273),
                        "_z": pct_ueber_tage(s_gueltig, 365),
                        "_gelistet_seit": start_dieser_wert,
                    })

            if performance_liste_haupt:
                # Tatsaechliches Startdatum der geladenen Reihe mit ausweisen -
                # weicht es vom Kaufdatum ab, ist das ein Hinweis darauf, dass
                # die Vergleichslinien einen anderen Zeitraum abdecken.
                _daten_start = df_chart.index.min()
                _start_hinweis = ""
                if _daten_start is not None and _daten_start.date() != kaufdatum_aktiv:
                    _start_hinweis = f" · Kursdaten ab {_daten_start.strftime('%d.%m.%Y')}"
                # kurz sichtbar, die Rechenregeln hinter dem "?" (UX 10/2026: der lange Text stand am Handy
                # mit 8 Zeilen vor der Tabelle)
                st.caption(
                    f"📅 Eigene Position ab Kaufdatum {kaufdatum_aktiv.strftime('%d.%m.%Y')}{_start_hinweis}",
                    help="Berechnet ab dem Kaufdatum gegen das eingesetzte Kapital"
                    + (f", inkl. Sparraten (Einstand {fmt(einstand_aktiv, 0)})" if sparplan_eingezahlt > 0 else "")
                    + (f", inkl. ausgezahlter Entnahmen ({fmt(ausgezahlt_ist, 0)})" if ausgezahlt_ist > 0 else "")
                    + ". 3–12 Mon.: reine Kursentwicklung. Ø/Jahr erst ab 1 Jahr Laufzeit, Ø/Mon. ab 30 Tagen "
                    "(sonst „–“).")
                performance_liste_haupt.sort(key=perf_sortierwert, reverse=True)   # DEP-08: ohne Ø/Jahr nach Gesamt
                _fokus = kennzahl_umschalter("fokus_haupt", performance_liste_haupt)
                st.markdown(
                    performance_tabelle_html(performance_liste_haupt, eigene_kennung=config.WKN,
                                             fokus=_fokus),
                    unsafe_allow_html=True,
                )

            with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                st.caption(
                    "„Depotwert“ ist der reale Wert nach den monatlichen Entnahmen: je Termin werden "
                    f"Anteile für {fmt(entnahme_rate, 2)} zum Geldkurs verkauft (Spread-Annahme "
                    f"{FMT.pct(config.SPREAD_PCT, 2)}), Sparplan-Käufe ab ihrem Kauftag. "
                    "„Eingezahlt“ = Startkapital plus Sparraten. Die Vergleichslinien zeigen, wie sich "
                    f"{fmt(startkapital_aktiv, 0)} im selben Zeitraum in gängigen Vergleichs-ETFs "
                    "entwickelt hätten (Kosten der ETFs bereits im Kurs enthalten, keine Steuern)."
                )
                zeige_chart_legende_liste([("Eingezahlt", "⚪"), (f"Depotwert {haupt_name} ({config.WKN})", "🟢")])
                pills_auswahl(benchmark_series.keys(), key="benchmark_pills")

            fig_wealth = go.Figure()
            fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Eingezahlt"], name="Eingezahlt", line=dict(color="#71717A", width=1.5, dash="dash")))
            fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Real"], name="Depotwert", line=dict(color=UI.AKZENT, width=2.5)))

            legende_eintraege = [("Eingezahlt", "#71717A"), (f"Depotwert {haupt_name} ({config.WKN})", UI.AKZENT)]
            for label, s in benchmark_series.items():
                if label not in ausgewaehlte_benchmarks:
                    continue
                farbe = vergleich_farbe(label, list(benchmark_series).index(label))
                fig_wealth.add_trace(go.Scatter(
                    x=df_chart.index, y=s, name=label,
                    line=dict(color=farbe, width=1.5, dash="dashdot"),
                ))
                legende_eintraege.append((label, farbe))

            fig_wealth.update_layout(
                paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=80, b=40), height=450,
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"),
                           ticksuffix=" €"),
                hovermode="x unified",
            )
            schritte.titel(st, "vergleich", 3)
            st.plotly_chart(UI.chart_stil(fig_wealth, flaeche="Depotwert"), width="stretch", key="chart_wealth", config={"displayModeBar": False})

    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Vermoegensaufbau", e)


def seit_2026(k):
    """Frueher _render_ytd in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _vergleichswerte_verwalten = k['_vergleichswerte_verwalten']
    df_chart = k['df_chart']
    haupt_name = k['haupt_name']
    heute_date = k['heute_date']
    is_live_history = k['is_live_history']
    kennzahl_umschalter = k['kennzahl_umschalter']
    lade_benchmarks_mit_fortschritt = k['lade_benchmarks_mit_fortschritt']
    lese_pills_auswahl_still = k['lese_pills_auswahl_still']
    notify_app_error = k['notify_app_error']
    pct_ueber_tage = k['pct_ueber_tage']
    performance_tabelle_html = k['performance_tabelle_html']
    pills_auswahl = k['pills_auswahl']
    tab_ytd = k['tab_ytd']
    vergleich_farbe = k['vergleich_farbe']
    zeige_chart_legende_liste = k['zeige_chart_legende_liste']
    try:
        with tab_ytd:
            _vergleichswerte_verwalten()
            if not is_live_history:
                st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – die Linie des Zertifikats "
                           "fehlt. Bitte später mit 🔄 erneut laden.")
                return
            v2_start = pd.Timestamp(config.VERGLEICH2_START_DATUM)
            v2_kapital = config.VERGLEICH2_STARTKAPITAL

            # Eigenes Zertifikat: aus bereits geladenem df_chart ab v2_start neu skalieren
            eigene_reihe_v2 = df_chart["Close"][df_chart.index >= v2_start]
            if not eigene_reihe_v2.empty and eigene_reihe_v2.iloc[0] > 0:
                eigene_reihe_v2 = eigene_reihe_v2 / eigene_reihe_v2.iloc[0] * v2_kapital

            # Benchmarks: eigener, frischer Abruf ab v2_start (eigene Cache-Zeile,
            # da anderer Startzeitpunkt als der Hauptvergleich oben)
            benchmark_series_v2, benchmark_start_daten_v2 = lade_benchmarks_mit_fortschritt(
                eigene_reihe_v2.index, config.VERGLEICH2_START_DATUM, v2_kapital
            )

            # Auswahl still aus dem gespeicherten Zustand lesen - der sichtbare
            # Auswahl-Bereich steht weiter unten, direkt vor dem Chart.
            ausgewaehlte_v2 = lese_pills_auswahl_still(benchmark_series_v2.keys(), key="benchmark_v2_pills")

            fig_v2 = go.Figure()
            fig_v2.add_trace(go.Scatter(
                x=eigene_reihe_v2.index, y=[v2_kapital] * len(eigene_reihe_v2),
                name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash"),
            ))
            fig_v2.add_trace(go.Scatter(
                x=eigene_reihe_v2.index, y=eigene_reihe_v2, name=f"{haupt_name} ({config.WKN})",
                line=dict(color=UI.AKZENT, width=2.5),
            ))
            benchmark_colors_v2 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
            legende_eintraege_v2 = [("Startkapital", "#71717A"), (f"{haupt_name} ({config.WKN})", UI.AKZENT)]
            for i, (label, s) in enumerate(benchmark_series_v2.items()):
                if label not in ausgewaehlte_v2:
                    continue
                farbe_v2 = vergleich_farbe(label, list(benchmark_series_v2).index(label))
                fig_v2.add_trace(go.Scatter(
                    x=eigene_reihe_v2.index, y=s, name=label,
                    line=dict(color=farbe_v2, width=1.5, dash="dashdot"),
                ))
                legende_eintraege_v2.append((label, farbe_v2))

            fig_v2.update_layout(
                paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=40, b=40), height=450,
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=1000),
                hovermode="x unified",
            )
            performance_liste_v2 = []
            if not eigene_reihe_v2.empty and eigene_reihe_v2.iloc[0] > 0:
                gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                    eigene_reihe_v2.iloc[0], eigene_reihe_v2.iloc[-1], config.VERGLEICH2_START_DATUM, heute_date
                )
                performance_liste_v2.append({
                    "Wert": f"{haupt_name} ({config.WKN})",
                    "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                    "_q": pct_ueber_tage(eigene_reihe_v2, 91),
                    "_h": pct_ueber_tage(eigene_reihe_v2, 182),
                    "_n": pct_ueber_tage(eigene_reihe_v2, 273),
                    "_z": pct_ueber_tage(eigene_reihe_v2, 365),
                    "_gelistet_seit": config.VERGLEICH2_START_DATUM,
                })
            for label, s in benchmark_series_v2.items():
                s_gueltig = s.dropna()
                if label in ausgewaehlte_v2 and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                    start_dieser_wert = benchmark_start_daten_v2.get(label)
                    start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else config.VERGLEICH2_START_DATUM
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                    )
                    performance_liste_v2.append({
                        "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_q": pct_ueber_tage(s_gueltig, 91),
                        "_h": pct_ueber_tage(s_gueltig, 182),
                        "_n": pct_ueber_tage(s_gueltig, 273),
                        "_z": pct_ueber_tage(s_gueltig, 365),
                        "_gelistet_seit": start_dieser_wert,
                    })

            if performance_liste_v2:
                st.caption(f"📅 Berechnet seit {config.VERGLEICH2_START_DATUM.strftime('%d.%m.%Y')}")
                performance_liste_v2.sort(key=perf_sortierwert, reverse=True)   # DEP-08: ohne Ø/Jahr nach Gesamt
                _fokus = kennzahl_umschalter("fokus_v2", performance_liste_v2)
                st.markdown(
                    performance_tabelle_html(performance_liste_v2, eigene_kennung=config.WKN,
                                             fokus=_fokus),
                    unsafe_allow_html=True,
                )

            with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                st.caption(
                    f"Alle Werte neu skaliert: {fmt(v2_kapital, 0)} investiert am "
                    f"{config.VERGLEICH2_START_DATUM.strftime('%d.%m.%Y')}, unabhängig vom "
                    "eigentlichen Kaufdatum deines Zertifikats - zeigt die reine "
                    "Performance seit Jahresanfang im direkten Vergleich."
                )
                zeige_chart_legende_liste([("Startkapital", "⚪"), (f"{haupt_name} ({config.WKN})", "🟢")])
                pills_auswahl(benchmark_series_v2.keys(), key="benchmark_v2_pills")

            schritte.titel(st, "vergleich", 3)
            st.plotly_chart(UI.chart_stil(fig_v2, flaeche=f"{haupt_name} ({config.WKN})"), width="stretch", key="chart_ytd", config={"displayModeBar": False})

    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Seit-2026", e)


def seit_2021(k):
    """Frueher _render_2021 in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    KEINE_HISTORIE = k['KEINE_HISTORIE']
    _vergleichswerte_verwalten = k['_vergleichswerte_verwalten']
    aktueller_kurs = k['aktueller_kurs']
    get_historical_market_data = k['get_historical_market_data']
    haupt_name = k['haupt_name']
    heute_date = k['heute_date']
    is_live_data = k['is_live_data']
    kennzahl_umschalter = k['kennzahl_umschalter']
    kurs_tag = k['kurs_tag']
    lade_benchmarks_mit_fortschritt = k['lade_benchmarks_mit_fortschritt']
    lese_pills_auswahl_still = k['lese_pills_auswahl_still']
    notify_app_error = k['notify_app_error']
    pct_ueber_tage = k['pct_ueber_tage']
    performance_tabelle_html = k['performance_tabelle_html']
    pills_auswahl = k['pills_auswahl']
    tab_2021 = k['tab_2021']
    vergleich_farbe = k['vergleich_farbe']
    zeige_chart_legende_liste = k['zeige_chart_legende_liste']
    try:
        with tab_2021:
            _vergleichswerte_verwalten()
            v3_start = pd.Timestamp(config.VERGLEICH3_START_DATUM)
            v3_kapital = config.VERGLEICH3_STARTKAPITAL
            master_index_v3 = pd.bdate_range(start=v3_start, end=pd.Timestamp(heute_date))

            # Eigenes Zertifikat: EIGENER, frischer Abruf ab 2021 (df_chart
            # reicht nur bis zum echten Kaufdatum zurueck, hier brauchen wir
            # ggf. deutlich mehr Historie). Wichtig: die Benchmarks werden
            # NICHT auf den (ggf. kuerzeren) Zeitraum des Zertifikats
            # zugeschnitten - sie laufen ueber den vollen 2021-Zeitraum,
            # nur die Zertifikat-Linie beginnt ggf. spaeter (echte Luecke).
            df_chart_v3, _v3_quelle = get_historical_market_data(config.VERGLEICH3_START_DATUM, heute_date)
            v3_echt = _v3_quelle != KEINE_HISTORIE              # Audit A-06: keine Ersatzreihen
            if v3_echt and is_live_data:                        # DEP-10: gleicher letzter Tag wie Vergleichswerte
                df_chart_v3 = haenge_live_punkt_an(df_chart_v3, kurs_tag, aktueller_kurs)
            if not v3_echt:
                st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – die Linie des Zertifikats "
                           "fehlt. Bitte später mit 🔄 erneut laden.")
            roh_eigen_v3 = df_chart_v3["Close"] if not df_chart_v3.empty else pd.Series(dtype=float)

            tatsaechlicher_start_v3 = roh_eigen_v3.index.min() if not roh_eigen_v3.empty else None

            if not roh_eigen_v3.empty and roh_eigen_v3.iloc[0] > 0:
                skaliert_eigen_v3 = roh_eigen_v3 / roh_eigen_v3.iloc[0] * v3_kapital
                # Auf vollen Zeitindex bringen, aber NUR nach vorne auffuellen -
                # vor dem echten Start bleibt es NaN (keine erfundene Rueckrechnung)
                eigene_reihe_v3 = skaliert_eigen_v3.reindex(master_index_v3).ffill()
            else:
                eigene_reihe_v3 = pd.Series(index=master_index_v3, dtype=float)

            benchmark_series_v3, benchmark_start_daten_v3 = lade_benchmarks_mit_fortschritt(
                master_index_v3, config.VERGLEICH3_START_DATUM, v3_kapital
            )

            # Auswahl still aus dem gespeicherten Zustand lesen - der sichtbare
            # Auswahl-Bereich steht weiter unten, direkt vor dem Chart.
            ausgewaehlte_v3 = lese_pills_auswahl_still(benchmark_series_v3.keys(), key="benchmark_v3_pills")

            fig_v3 = go.Figure()
            fig_v3.add_trace(go.Scatter(
                x=master_index_v3, y=[v3_kapital] * len(master_index_v3),
                name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash"),
            ))
            fig_v3.add_trace(go.Scatter(
                x=eigene_reihe_v3.index, y=eigene_reihe_v3,
                name=f"{haupt_name} ({config.WKN})",
                line=dict(color=UI.AKZENT, width=2.5),
            ))
            benchmark_colors_v3 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
            legende_eintraege_v3 = [("Startkapital", "#71717A"), (f"{haupt_name} ({config.WKN})", UI.AKZENT)]
            for i, (label, s) in enumerate(benchmark_series_v3.items()):
                if label not in ausgewaehlte_v3:
                    continue
                farbe_v3 = vergleich_farbe(label, list(benchmark_series_v3).index(label))
                fig_v3.add_trace(go.Scatter(
                    x=master_index_v3, y=s, name=label,
                    line=dict(color=farbe_v3, width=1.5, dash="dashdot"),
                ))
                legende_eintraege_v3.append((label, farbe_v3))

            fig_v3.update_layout(
                paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=40, b=40), height=450,
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=2000),
                hovermode="x unified",
            )
            performance_liste_v3 = []
            if not roh_eigen_v3.empty and roh_eigen_v3.iloc[0] > 0:
                start_datum_eigen_v3 = tatsaechlicher_start_v3.date() if tatsaechlicher_start_v3 is not None else config.VERGLEICH3_START_DATUM
                gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                    roh_eigen_v3.iloc[0], roh_eigen_v3.iloc[-1], start_datum_eigen_v3, heute_date
                )
                performance_liste_v3.append({
                    "Wert": f"{haupt_name} ({config.WKN})",
                    "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                    "_q": pct_ueber_tage(roh_eigen_v3, 91),
                    "_h": pct_ueber_tage(roh_eigen_v3, 182),
                    "_n": pct_ueber_tage(roh_eigen_v3, 273),
                    "_z": pct_ueber_tage(roh_eigen_v3, 365),
                    "_gelistet_seit": start_datum_eigen_v3,
                })
            for label, s in benchmark_series_v3.items():
                s_gueltig = s.dropna()
                if label in ausgewaehlte_v3 and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                    start_dieser_wert = benchmark_start_daten_v3.get(label)
                    start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else config.VERGLEICH3_START_DATUM
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                    )
                    performance_liste_v3.append({
                        "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_q": pct_ueber_tage(s_gueltig, 91),
                        "_h": pct_ueber_tage(s_gueltig, 182),
                        "_n": pct_ueber_tage(s_gueltig, 273),
                        "_z": pct_ueber_tage(s_gueltig, 365),
                        "_gelistet_seit": start_dieser_wert,
                    })

            if performance_liste_v3:
                st.caption(f"📅 Berechnet seit {config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')} (bzw. erstem verfügbaren Kurs)")
                performance_liste_v3.sort(key=perf_sortierwert, reverse=True)   # DEP-08: ohne Ø/Jahr nach Gesamt
                _fokus = kennzahl_umschalter("fokus_v3", performance_liste_v3)
                st.markdown(
                    performance_tabelle_html(performance_liste_v3, eigene_kennung=config.WKN,
                                             fokus=_fokus),
                    unsafe_allow_html=True,
                )

            with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                st.caption(
                    f"Alle Werte neu skaliert: {fmt(v3_kapital, 0)} investiert am "
                    f"{config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')}, unabhängig vom "
                    "eigentlichen Kaufdatum deines Zertifikats."
                )
                if tatsaechlicher_start_v3 is not None and tatsaechlicher_start_v3 > v3_start:
                    st.info(
                        f"ℹ️ Für {config.WKN} liegen erst ab {tatsaechlicher_start_v3.strftime('%d.%m.%Y')} "
                        "Kursdaten vor (vermutlich Auflegungsdatum des Zertifikats) - die Linie beginnt "
                        "entsprechend später als die Vergleichswerte, keine erfundenen Daten. Die "
                        "Vergleichswerte selbst laufen trotzdem über den vollen Zeitraum seit "
                        f"{config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')}."
                    )
                zeige_chart_legende_liste([("Startkapital", "⚪"), (f"{haupt_name} ({config.WKN})", "🟢")])
                pills_auswahl(benchmark_series_v3.keys(), key="benchmark_v3_pills")

            schritte.titel(st, "vergleich", 3)
            st.plotly_chart(UI.chart_stil(fig_v3, flaeche=f"{haupt_name} ({config.WKN})"), width="stretch", key="chart_2021", config={"displayModeBar": False})

    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Seit-2021", e)


def candlestick(k):
    """Frueher _render_candle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    df_chart = k['df_chart']
    is_live_history = k['is_live_history']
    notify_app_error = k['notify_app_error']
    tab_candle = k['tab_candle']
    try:
        with tab_candle:
            if not is_live_history:
                st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – die Linie des Zertifikats "
                           "fehlt. Bitte später mit 🔄 erneut laden.")
                return
            fig_c = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart["Open"], high=df_chart["High"], low=df_chart["Low"], close=df_chart["Close"], increasing_line_color="#34D399", decreasing_line_color="#F87171")])
            fig_c.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40), height=450, xaxis=dict(showgrid=True, gridcolor="#1A1A1A"), yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", dtick=10), showlegend=False)
            schritte.leiste(st, "candle")
            schritte.titel(st, "candle", 1)
            st.plotly_chart(UI.chart_stil(fig_c), width="stretch", key="chart_candlestick", config={"displayModeBar": False})
            schritte.titel(st, "candle", 2)
            st.caption(
                "Basiert auf ls-tc.de Tages-Schlusskursen (Open/High/Low approximiert). "
                "Der GitHub-Actions-Cron protokolliert seit Kurzem zusätzlich alle 5 Min den "
                "echten Kurs in state/price_history/ — daraus lässt sich künftig ein echter "
                "Intraday-Chart bauen, sobald genug Historie gesammelt ist."
            )

    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Candlestick", e)
