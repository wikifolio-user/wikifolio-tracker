"""Wiki-Idee - Oberflaeche des Modelldepots (Rechenlogik in wiki_idee.py, Umschichtung freitags durch
wiki_idee_agent.py). Die Seite liest nur: state/wiki_idee/depot.json und rangliste.json sowie fuer den
heutigen Wert die Tagesschlusskurse aus dem Katalog des Watchlist-Agenten. Sie veraendert nichts.
"""
import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import formate as FMT
import schritte
import ui_stil as UI
import wiki_idee as WI

PFAD_DEPOT = "state/wiki_idee/depot.json"
PFAD_RANG = "state/wiki_idee/rangliste.json"
TEIL_TITEL = {k: t for k, t, _ in WI.BAUSTEINE}


def _datum(text):
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def _datum_de(text):
    d = _datum(text)
    return d.strftime("%d.%m.%Y") if d else "–"


def naechster_freitag(heute):
    tage = (4 - heute.weekday()) % 7
    return heute + datetime.timedelta(days=tage)


def tageskurse(katalog_teile):
    """{WKN/ISIN (gross): kurs EUR} aus dem Katalog (taeglicher Schlusskurs)."""
    aus = {}
    for d in katalog_teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            w = dict(zip(felder, z))
            try:
                k = float(w.get("kurs") or 0)
            except (TypeError, ValueError):
                continue
            if k > 0:
                for kenn in (w.get("kennung"), w.get("isin")):
                    if kenn:
                        aus.setdefault(str(kenn).upper(), k)
    return aus


def aktuelle_preise(depot, kurse):
    """{positions-id: kurs heute} - nur Werte mit Kurs im Katalog."""
    aus = {}
    for i, p in (depot.get("positionen") or {}).items():
        k = next((kurse[x.upper()] for x in (p.get("wkn"), p.get("isin")) if x and x.upper() in kurse), None)
        if k:
            aus[i] = k
    return aus


def _wertchart(depot, wert_heute, heute):
    hist = [(_datum(d), w) for d, w in depot.get("historie") or [] if _datum(d)]
    if wert_heute is not None and (not hist or heute > hist[-1][0]):
        hist.append((heute, wert_heute))
    start = float(depot.get("startkapital") or WI.STARTKAPITAL)
    fig = go.Figure()
    fig.add_hline(y=start, line=dict(color="rgba(148,163,184,.6)", dash="dot", width=1))
    fig.add_trace(go.Scatter(x=[d for d, _ in hist], y=[w for _, w in hist], mode="lines+markers", name="Depotwert",
                             hovertemplate="%{x|%d.%m.%Y}<br>%{y:,.0f} €<extra></extra>"))
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                      yaxis=dict(ticksuffix=" €", tickformat=",.0f"))
    return UI.chart_stil(fig, flaeche="Depotwert")


def _positionen_tabelle(pos, preise, gesamt):
    zeilen = []
    for p in sorted(pos, key=lambda p: p["rang"]):
        heute = preise.get(p["id"]) or p["kurs"]
        wert = p["stueck"] * heute
        z = {"Rang": p["rang"], "Name": p["name"], "WKN/ISIN": p.get("wkn") or p.get("isin") or "",
             "Gruppe": p.get("gruppe") or "", "Score": p["mix"]}
        if p["art"] == "aktie":
            for k in ("score", "investoren", "unterbewertung", "qualitaet_kurs"):
                z[TEIL_TITEL[k]] = (p.get("teile") or {}).get(k)
        z.update({"Stück": p["stueck"], "Kurs Freitag €": p["kurs"], "Kurs heute €": heute, "Wert €": wert,
                  "Anteil %": wert / gesamt * 100 if gesamt else None,
                  "seit Freitag %": (heute / p["kurs"] - 1) * 100 if p["kurs"] else None})
        zeilen.append(z)
    return pd.DataFrame(zeilen)


def _tabelle(df, key):
    cfg = {"Rang": st.column_config.NumberColumn(width="small"),
           "Score": st.column_config.NumberColumn(format="%.0f"),
           "Stück": st.column_config.NumberColumn(format="%d"),
           "Kurs Freitag €": st.column_config.NumberColumn(format="%.2f"),
           "Kurs heute €": st.column_config.NumberColumn(format="%.2f"),
           "Wert €": st.column_config.NumberColumn(format="%.0f"),
           "Anteil %": st.column_config.NumberColumn(format="%.2f"),
           "seit Freitag %": st.column_config.NumberColumn(format="%+.1f")}
    cfg.update({t: st.column_config.ProgressColumn(t, min_value=0, max_value=100, format="%.0f")
                for t in TEIL_TITEL.values() if t in df.columns})
    st.dataframe(df, hide_index=True, width="stretch", column_config=cfg, key=key,
                 height=min(38 + 35 * len(df), 640))


def _balken(df, titel):
    d = df.sort_values("Wert €")
    farben = ["#34D399" if (v or 0) >= 0 else "#F87171" for v in d["seit Freitag %"]]
    fig = go.Figure(go.Bar(x=d["Wert €"], y=d["Name"], orientation="h", marker_color=farben,
                           customdata=d[["Stück", "seit Freitag %"]].values,
                           hovertemplate="%{y}<br>%{x:,.0f} € · %{customdata[0]} Stück · "
                                         "%{customdata[1]:+.1f} % seit Freitag<extra></extra>"))
    fig.update_layout(height=max(260, 18 * len(d) + 60), margin=dict(l=10, r=10, t=30, b=10), title=titel,
                      xaxis=dict(ticksuffix=" €", tickformat=",.0f"), yaxis=dict(tickfont=dict(size=10)))
    return UI.chart_stil(fig, schrumpfen=False)


def seite(h):
    """h: {"lesen": gh_read_cached, "lesen_taeglich": gh_read_taeglich, "app_url": str}"""
    schritte.leiste(st, "wiki")
    depot = h["lesen"](PFAD_DEPOT, {}) or {}
    rang = h["lesen"](PFAD_RANG, {}) or {}
    heute = datetime.date.today()

    schritte.titel(st, "wiki", 1)
    if not depot.get("positionen"):
        st.info("Das Modelldepot wird beim ersten Lauf angelegt – automatisch am Freitag nach Börsenschluss "
                "(18:17 Uhr) oder sofort auf GitHub unter **Actions → Wiki-Idee Umschichtung (freitags) → "
                "Run workflow**. Startkapital: 100.000 €, 50 Aktien (70 %) und 20 ETFs (30 %).")
        _methodik()
        return

    katalog = [d for d in UI.parallel_lesen(h["lesen_taeglich"], [f"state/planer/katalog_gross_{i}.json"
                                                                  for i in range(4)], None) if isinstance(d, dict)]
    preise = aktuelle_preise(depot, tageskurse(katalog))
    wert_heute = WI.bewerten_depot(depot, preise)
    start = float(depot.get("startkapital") or WI.STARTKAPITAL)
    pos = list(depot["positionen"].values())
    a = [p for p in pos if p["art"] == "aktie"]
    e = [p for p in pos if p["art"] == "etf"]

    k1, k2 = st.columns(2)
    k3, k4 = st.columns(2)
    k1.metric("Depotwert heute", FMT.eur(wert_heute, 0), FMT.eur(wert_heute - start, 0, vz=True) + " seit Start")
    k2.metric("Entwicklung seit Start", FMT.pct((wert_heute / start - 1) * 100, 1, vz=True),
              f"Start {_datum_de(depot.get('start'))}", delta_color="off")
    k3.metric("Positionen", f"{len(a)} Aktien · {len(e)} ETFs", f"Kasse {FMT.eur(depot.get('kasse') or 0, 0)}",
              delta_color="off")
    nf = naechster_freitag(heute)
    k4.metric("Nächste Umschichtung", nf.strftime("%d.%m.%Y"),
              f"zuletzt {_datum_de(depot.get('stand'))}", delta_color="off")
    st.caption(f"Kurse „heute“: letzter Tagesschluss aus den Ranglisten-Daten ({len(preise)} von {len(pos)} Werten; "
               "fehlende mit dem Kurs vom Freitag). Modellrechnung – keine echten Trades, keine Anlageberatung.")

    schritte.titel(st, "wiki", 2)
    st.plotly_chart(_wertchart(depot, wert_heute, heute), width="stretch", key="wiki_chart",
                    config={"displayModeBar": False})
    if len(depot.get("historie") or []) < 2:
        st.caption("Der Verlauf wächst mit jedem Freitag um einen Punkt; dazwischen zeigt der letzte Punkt den "
                   "heutigen Wert.")

    schritte.titel(st, "wiki", 3)
    reiter = st.tabs([f"📈 Aktien ({len(a)})", f"🌍 ETFs ({len(e)})"])
    for tab, liste, titel, key in ((reiter[0], a, "Aktien", "a"), (reiter[1], e, "ETFs", "e")):
        with tab:
            if not liste:
                st.info("Keine Positionen.")
                continue
            df = _positionen_tabelle(liste, preise, wert_heute)
            st.caption(f"{titel}: {FMT.eur(df['Wert €'].sum(), 0)} "
                       f"({FMT.pct(df['Wert €'].sum() / wert_heute * 100 if wert_heute else 0, 1)} des Depots) · "
                       "Score 0–100 · Balken: Wert je Position, grün = seit Freitag im Plus")
            _tabelle(df, f"wiki_tab_{key}")
            st.plotly_chart(_balken(df, f"{titel} nach Wert"), width="stretch", key=f"wiki_balken_{key}",
                            config={"displayModeBar": False})
            st.download_button(f"⬇️ {titel} als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                               file_name=f"wiki_idee_{key}_{depot.get('stand')}.csv", mime="text/csv",
                               key=f"wiki_csv_{key}")

    schritte.titel(st, "wiki", 4)
    laeufe = depot.get("laeufe") or []
    if laeufe:
        namen = [f"{_datum_de(l['datum'])} · {len(l['auftraege'])} Anpassungen" for l in reversed(laeufe)]
        wahl = st.selectbox("Umschichtung", namen, key="wiki_lauf")
        lauf = list(reversed(laeufe))[namen.index(wahl)]
        if lauf["auftraege"]:
            df = pd.DataFrame([{"Aktion": x["aktion"], "Stück": x["stueck"], "Name": x["name"],
                                "WKN/ISIN": x["wkn"] or x["isin"], "Art": "Aktie" if x["art"] == "aktie" else "ETF",
                                "Kurs ca. €": x["kurs"], "Bestand vorher": x["vorher"], "Bestand nachher": x["nachher"]}
                               for x in lauf["auftraege"]])
            zahl = df["Aktion"].value_counts().to_dict()
            st.caption(" · ".join(f"{k}: {v}" for k, v in zahl.items()) + " – erst verkaufen, dann kaufen.")
            st.dataframe(df, hide_index=True, width="stretch", key="wiki_auftraege",
                         column_config={"Kurs ca. €": st.column_config.NumberColumn(format="%.2f")},
                         height=min(38 + 35 * len(df), 520))
            st.download_button("⬇️ Anpassungen als CSV", df.to_csv(index=False, sep=";", decimal=",")
                               .encode("utf-8-sig"), file_name=f"wiki_idee_umschichtung_{lauf['datum']}.csv",
                               mime="text/csv", key="wiki_csv_auf")
        else:
            st.success("Keine Anpassungen nötig.")
    aus = depot.get("ausgeschlossen") or []
    if aus:
        with st.expander(f"🚫 Wegen Warnsignalen ausgeschlossen ({len(aus)})"):
            st.dataframe(pd.DataFrame(aus).rename(columns={"name": "Aktie", "grund": "Grund"}), hide_index=True,
                         width="stretch", key="wiki_aus")

    schritte.titel(st, "wiki", 5)
    if rang.get("aktien"):
        with st.expander(f"🏁 Rangliste vom {_datum_de(rang.get('stand'))} (Top {len(rang['aktien'])} Aktien, "
                         f"Top {len(rang.get('etf') or [])} ETFs) – wer rückt nach?"):
            im_depot = set(depot["positionen"])
            for titel, liste in (("Aktien", rang["aktien"]), ("ETFs", rang.get("etf") or [])):
                st.markdown(f"**{titel}**")
                st.dataframe(pd.DataFrame([{"Rang": w["rang"], "Im Depot": "✓" if w["id"] in im_depot else "",
                                            "Name": w["name"], "Gruppe": w["gruppe"], "Score": w["mix"],
                                            **{TEIL_TITEL[k]: v for k, v in (w.get("teile") or {}).items()
                                               if titel == "Aktien"},
                                            "Kurs €": w["kurs"]} for w in liste]),
                             hide_index=True, width="stretch", key=f"wiki_rang_{titel}",
                             column_config={"Score": st.column_config.NumberColumn(format="%.0f"),
                                            "Kurs €": st.column_config.NumberColumn(format="%.2f")})
    _methodik()


def _methodik():
    with st.expander("ℹ️ So funktioniert die Wiki-Idee"):
        st.markdown(
            "- **Start:** 100.000 € – 70 % auf **50 Aktien**, 30 % auf **20 ETFs**, je Klasse gleich gewichtet "
            "(je Aktie ca. 1.400 €, je ETF 1.500 €), ganze Stück, Rest bleibt Kasse.\n"
            "- **Aktien-Rangliste** aus dem Bewertungssystem: "
            + ", ".join(f"{g} % {t}" for _, t, g in WI.BAUSTEINE) + ". "
            "*Gesamt-Score* = Bewertung, Qualität, Wachstum, Stabilität, Dividende, Momentum (wie unter "
            "„⚖️ Bewertung“); *Investoren-Checks* = Urteil der Börsenlegenden (Buffett, Graham, Lynch, Greenblatt, "
            "Piotroski, Fisher …); *Unterbewertung* = Abstand fairer Wert zum Kurs; *Qualität × Kurs* = gute Firma, "
            "zuletzt schwacher Kurs. Fehlt ein Baustein, zählt er neutral (50).\n"
            "- **Ausschluss:** Altman-Gefahrenzone, Beneish-Verdacht auf Bilanzmanipulation oder überwiegend "
            "Bilanz-Warnsignale.\n"
            f"- **ETFs:** Gesamt-Score (Rendite, Risiko, Momentum, Dividende), ohne Hebel-/Short-Produkte, "
            f"mindestens {WI.MIN_ETF_JAHRE:.0f} Jahre Historie.\n"
            f"- **Streuung:** höchstens {WI.MAX_JE_SEKTOR} Aktien je Branche, höchstens {WI.MAX_JE_ETF_GRUPPE} ETFs "
            "je Region + Thema (sonst würden z. B. zehn fast gleiche S&P-500-ETFs gewählt).\n"
            f"- **Jeden Freitag** nach Börsenschluss: neue Rangliste mit aktuellen Kursen (ls-tc.de). Ein Wert bleibt, "
            f"solange er in den Top {WI.PUFFER_AKTIEN} (Aktien) bzw. Top {WI.PUFFER_ETF} (ETFs) steht – kein Tausch "
            "wegen kleiner Score-Schwankungen; freie Plätze bekommen die Besten. Danach werden alle Positionen "
            "auf das Zielgewicht zurückgesetzt (im wikifolio ohne Kosten). Die Anpassungen kommen per Mail.\n"
            "- **Kein Trading-Roboter:** Das Modelldepot rechnet nur – die Käufe und Verkäufe buchst du selbst im "
            "wikifolio. Grundlage sind vergangene Daten; keine Anlageberatung.")
