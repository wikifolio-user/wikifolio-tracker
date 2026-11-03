"""KI_Invest_System (Wiki-Idee) - Oberflaeche des Modelldepots (Rechenlogik in wiki_idee.py).

Nach Bedarf: "Liste jetzt erstellen" bewertet alle Werte neu (Bewertungssystem + Investoren-Checks), holt die
aktuellen Kurse (ls-tc.de) und zeigt Kaeufe/Verkaeufe mit einem Chart der Veraenderungen. Das Modelldepot
(state/wiki_idee/depot.json) aendert sich erst mit "Als umgesetzt uebernehmen" (rueckgaengig moeglich).
Heutiger Depotwert: Tagesschlusskurse aus dem Katalog des Watchlist-Agenten.
"""
import datetime
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import etf_merkmale as EM
import formate as FMT
import klassen_score as KS
import kurs_vorrat as KV
import schritte
import ui_stil as UI
import wiki_idee as WI

PFAD_DEPOT = "state/wiki_idee/depot.json"
PFAD_RANG = "state/wiki_idee/rangliste.json"
TEIL_TITEL = {k: t for k, t, _ in WI.BAUSTEINE}
VORSCHLAG = "_wiki_vorschlag"
try:
    from zoneinfo import ZoneInfo
    BERLIN = ZoneInfo("Europe/Berlin")
except Exception:
    BERLIN = None


def _datum(text):
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def _datum_de(text):
    d = _datum(text)
    return d.strftime("%d.%m.%Y") if d else "–"


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
    punkte = [(datetime.datetime.combine(_datum(d), datetime.time(18)), w) for d, w in depot.get("historie") or []
              if _datum(d)]
    if wert_heute is not None:
        jetzt = _jetzt().replace(tzinfo=None)
        if not punkte or jetzt > punkte[-1][0]:
            punkte.append((jetzt, wert_heute))
    start = float(depot.get("startkapital") or WI.STARTKAPITAL)
    fig = go.Figure()
    fig.add_hline(y=start, line=dict(color="rgba(148,163,184,.6)", dash="dot", width=1))
    fig.add_trace(go.Scatter(x=[d for d, _ in punkte], y=[w for _, w in punkte], mode="lines+markers",
                             name="Depotwert", hovertemplate="%{x|%d.%m.%Y}<br>%{y:,.0f} €<extra></extra>"))
    x_achse = dict(type="date", tickformat="%d.%m.%y")
    if punkte and (punkte[-1][0] - punkte[0][0]).days < 7:          # kurzer Verlauf: eine Woche zeigen
        mitte = punkte[0][0]
        x_achse["range"] = [mitte - datetime.timedelta(days=1), mitte + datetime.timedelta(days=7)]
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), showlegend=False, xaxis=x_achse,
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
        z.update({"Stück": p["stueck"], "Kurs Kauf €": p["kurs"], "Kurs heute €": heute, "Wert €": wert,
                  "Anteil %": wert / gesamt * 100 if gesamt else None,
                  "seit Kauf %": (heute / p["kurs"] - 1) * 100 if p["kurs"] else None})
        zeilen.append(z)
    return pd.DataFrame(zeilen)


def _tabelle(df, key):
    cfg = {"Rang": st.column_config.NumberColumn(width="small"),
           "Score": st.column_config.NumberColumn(format="%.0f"),
           "Stück": st.column_config.NumberColumn(format="%d"),
           "Kurs Kauf €": st.column_config.NumberColumn(format="%.2f"),
           "Kurs heute €": st.column_config.NumberColumn(format="%.2f"),
           "Wert €": st.column_config.NumberColumn(format="%.0f"),
           "Anteil %": st.column_config.NumberColumn(format="%.2f"),
           "seit Kauf %": st.column_config.NumberColumn(format="%+.1f")}
    cfg.update({t: st.column_config.ProgressColumn(t, min_value=0, max_value=100, format="%.0f")
                for t in TEIL_TITEL.values() if t in df.columns})
    st.dataframe(df, hide_index=True, width="stretch", column_config=cfg, key=key,
                 height=min(38 + 35 * len(df), 640))


def _balken(df, titel):
    d = df.sort_values("Wert €")
    farben = ["#34D399" if (v or 0) >= 0 else "#F87171" for v in d["seit Kauf %"]]
    fig = go.Figure(go.Bar(x=d["Wert €"], y=d["Name"], orientation="h", marker_color=farben,
                           customdata=d[["Stück", "seit Kauf %"]].values,
                           hovertemplate="%{y}<br>%{x:,.0f} € · %{customdata[0]} Stück · "
                                         "%{customdata[1]:+.1f} % seit Kauf<extra></extra>"))
    fig.update_layout(height=max(260, 18 * len(d) + 60), margin=dict(l=10, r=10, t=30, b=10), title=titel,
                      xaxis=dict(ticksuffix=" €", tickformat=",.0f"), yaxis=dict(tickfont=dict(size=10)))
    return UI.chart_stil(fig, schrumpfen=False)


def _jetzt():
    return datetime.datetime.now(BERLIN) if BERLIN else datetime.datetime.now()


def liste_erstellen(h, depot):
    """Bewertung aller Werte + aktuelle Kurse + Umschichtung (ohne Speichern). -> Vorschlag (dict)"""
    d = h["bewertung_daten"]()
    bewertet = [(e, h["bewerten"](e, d["ver"])) for e in d["u"] if e["art"] in ("aktie", "etf")]
    inv = {}
    for teil in UI.parallel_lesen(h["lesen_taeglich"], [f"state/investoren/ergebnis_{i:02d}.json" for i in range(16)],
                                  None):
        inv.update((teil or {}).get("werte") or {})
    katalog = [x for x in UI.parallel_lesen(h["lesen_taeglich"], [f"state/planer/katalog_gross_{i}.json"
                                                                  for i in range(4)], None) if isinstance(x, dict)]
    eur = tageskurse(katalog)                       # EUR-Tagesschluss je WKN/ISIN
    rang_a, aus, rang_e = WI.ranglisten(bewertet, inv, KS.HEBEL, EM.merkmale, eur)
    if len(rang_a) < WI.N_AKTIEN or len(rang_e) < WI.N_ETF:
        raise ValueError(f"Zu wenige bewertete Werte ({len(rang_a)} Aktien, {len(rang_e)} ETFs) – die Daten der "
                         "Agenten sind gerade unvollständig.")
    ids = KV.kennung_ids(h["lesen_taeglich"]("state/top50_ids.json", {}) or {},
                         h["lesen_taeglich"]("state/top50_wikifolios.json", {}) or {})
    jobs = []
    for w in WI.kurs_kandidaten(depot, rang_a, rang_e):
        iid = next((ids[k.upper()] for k in (w.get("wkn"), w.get("isin")) if k and k.upper() in ids), None)
        if iid:
            jobs.append((w["id"], iid))

    def holen(job):
        try:
            k = h["live_kurs"](job[1])
            return job[0], (float(k) if k and float(k) > 0 else None)
        except Exception:
            return job[0], None
    with ThreadPoolExecutor(8) as pool:
        live = {i: k for i, k in pool.map(holen, jobs) if k}
    # ohne aktuellen Kurs: letzter Tagesschluss in EUR (statt des alten Kaufkurses)
    preise = {**aktuelle_preise(depot, eur), **live}
    jetzt = _jetzt()
    neu, liste = WI.umschichten({k: v for k, v in depot.items() if k != "vorher"}, rang_a, rang_e, preise,
                                jetzt.date().isoformat(), zeitpunkt=jetzt.strftime("%Y-%m-%dT%H:%M"))
    neu["ausgeschlossen"] = aus[:200]
    return {"zeit": jetzt.strftime("%d.%m.%Y, %H:%M Uhr"), "neu": neu, "liste": liste, "basis": WI.signatur(depot),
            "live": len(live), "kandidaten": len(jobs), "rang": {"stand": jetzt.date().isoformat(),
                                                                   "aktien": rang_a[:100], "etf": rang_e[:40]}}


def _veraenderungschart(zeilen):
    d = sorted(zeilen, key=lambda z: z["betrag"])
    fig = go.Figure(go.Bar(
        x=[z["betrag"] for z in d], y=[f'{z["aktion"]} · {z["name"][:32]}' for z in d], orientation="h",
        marker_color=["#34D399" if z["betrag"] > 0 else "#F87171" for z in d],
        customdata=[[z["stueck"], z["kurs"]] for z in d],
        hovertemplate="%{y}<br>%{x:+,.0f} € · %{customdata[0]} Stück zu %{customdata[1]:,.2f} €<extra></extra>"))
    fig.update_layout(height=max(260, 20 * len(d) + 70), margin=dict(l=10, r=10, t=30, b=10),
                      title="Veränderungen (grün = kaufen, rot = verkaufen)",
                      xaxis=dict(ticksuffix=" €", tickformat="+,.0f"), yaxis=dict(tickfont=dict(size=10)))
    return UI.chart_stil(fig, schrumpfen=False)


def _vorschlag_zeigen(h, v):
    zeilen, summe = WI.betraege(v["liste"])
    neu = v["neu"]
    st.markdown(f"**Liste vom {v['zeit']}**")
    k1, k2 = st.columns(2)
    k3, k4 = st.columns(2)
    k1.metric("Depotwert jetzt", FMT.eur(neu["wert"], 0))
    k2.metric("Anpassungen", f"{len(zeilen)}", f"{sum(1 for z in zeilen if z['betrag'] < 0)} Verkäufe · "
              f"{sum(1 for z in zeilen if z['betrag'] > 0)} Käufe", delta_color="off")
    k3.metric("Verkaufen für", FMT.eur(summe["verkauf"], 0))
    k4.metric("Kaufen für", FMT.eur(summe["kauf"], 0), f"Kasse danach {FMT.eur(neu['kasse'], 0)}", delta_color="off")
    st.caption(f"Aktuelle Kurse von ls-tc.de für {v['live']} von {v['kandidaten']} Werten, übrige mit dem letzten "
               "Tagesschluss. Im wikifolio kann der Ausführungskurs abweichen – erst verkaufen, dann kaufen.")
    if not zeilen:
        st.success("Keine Anpassungen nötig – das Depot entspricht der aktuellen Rangliste.")
    else:
        st.plotly_chart(_veraenderungschart(zeilen), width="stretch", key="wiki_veraenderung",
                        config={"displayModeBar": False})
        df = pd.DataFrame([{"Aktion": z["aktion"], "Stück": z["stueck"], "Name": z["name"],
                            "WKN/ISIN": z["wkn"] or z["isin"], "Art": "Aktie" if z["art"] == "aktie" else "ETF",
                            "Kurs jetzt €": z["kurs"], "Betrag €": z["betrag"], "Bestand vorher": z["vorher"],
                            "Bestand nachher": z["nachher"]} for z in zeilen])
        st.dataframe(df, hide_index=True, width="stretch", key="wiki_vorschlag_tab",
                     height=min(38 + 35 * len(df), 560),
                     column_config={"Kurs jetzt €": st.column_config.NumberColumn(format="%.2f"),
                                    "Betrag €": st.column_config.NumberColumn(format="%+.2f")})
        st.download_button("⬇️ Liste als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           file_name=f"KI_Invest_System_liste_{neu['laeufe'][-1]['zeit'].replace(':', '')}.csv",
                           mime="text/csv", key="wiki_vorschlag_csv")
    b1, b2 = st.columns(2)
    if b1.button("✅ Als umgesetzt übernehmen", key="wiki_uebernehmen", type="primary", width="stretch",
                 disabled=not h.get("schreiben_ok", True),
                 help="Setzt das Modelldepot auf diesen Stand – die nächste Liste rechnet davon aus."):
        konflikt = []

        def aendern(gespeichert):
            neu_ = WI.uebernehmen(gespeichert or {}, neu, v["basis"])
            if neu_ is None:
                konflikt.append(True)
            return neu_
        ok, _ = h["schreiben"](PFAD_DEPOT, aendern, {}, "wiki-idee: umschichtung übernommen [skip ci]")
        if konflikt:
            st.error("Das Modelldepot wurde inzwischen geändert – bitte die Liste neu erstellen.")
        elif ok:
            h["schreiben"](PFAD_RANG, lambda _alt: v["rang"], {}, "wiki-idee: rangliste [skip ci]")
            st.session_state.pop(VORSCHLAG, None)
            st.session_state["_wiki_meldung"] = "✅ Übernommen – das Modelldepot ist auf dem neuen Stand."
            st.rerun()
        else:
            st.error("Speichern fehlgeschlagen – bitte erneut versuchen.")
    if b2.button("✖️ Verwerfen", key="wiki_verwerfen", width="stretch"):
        st.session_state.pop(VORSCHLAG, None)
        st.rerun()


def seite(h):
    """h: {"lesen": ungecachtes Lesen, "lesen_taeglich", "schreiben": gh_aktualisiere, "schreiben_ok": bool,
    "bewertung_daten": () -> {u, ver}, "bewerten": scoring.bewerten, "live_kurs": instrument_id -> kurs}"""
    schritte.leiste(st, "wiki")
    depot = h["lesen"](PFAD_DEPOT, {}) or {}
    rang = h["lesen"](PFAD_RANG, {}) or {}
    heute = _jetzt().date()
    if st.session_state.get("_wiki_meldung"):
        st.success(st.session_state.pop("_wiki_meldung"))

    # 1 - Liste erstellen
    schritte.titel(st, "wiki", 1)
    st.caption("Bewertet alle Aktien und ETFs jetzt neu (Bewertungssystem, Investoren-Checks, fairer Wert), holt die "
               "aktuellen Kurse und berechnet die Käufe und Verkäufe für das Modelldepot"
               + ("." if depot.get("positionen") else " – beim ersten Mal die Startkäufe für 100.000 €."))
    if st.button("📋 Liste jetzt erstellen", key="wiki_erstellen", type="primary", width="stretch"):
        with st.spinner("Bewerte alle Werte und hole aktuelle Kurse …"):
            try:
                st.session_state[VORSCHLAG] = liste_erstellen(h, depot)
            except Exception as e:
                st.error(f"Liste konnte nicht erstellt werden: {e}")
    v = st.session_state.get(VORSCHLAG)
    if v:
        _vorschlag_zeigen(h, v)

    if not depot.get("positionen"):
        _methodik()
        return

    # 2 - Ueberblick
    katalog = [d for d in UI.parallel_lesen(h["lesen_taeglich"], [f"state/planer/katalog_gross_{i}.json"
                                                                  for i in range(4)], None) if isinstance(d, dict)]
    preise = aktuelle_preise(depot, tageskurse(katalog))
    wert_heute = WI.bewerten_depot(depot, preise)
    start = float(depot.get("startkapital") or WI.STARTKAPITAL)
    pos = list(depot["positionen"].values())
    a = [p for p in pos if p["art"] == "aktie"]
    e = [p for p in pos if p["art"] == "etf"]
    schritte.titel(st, "wiki", 2)
    k1, k2 = st.columns(2)
    k3, k4 = st.columns(2)
    k1.metric("Depotwert heute", FMT.eur(wert_heute, 0), FMT.eur(wert_heute - start, 0, vz=True) + " seit Start")
    k2.metric("Entwicklung seit Start", FMT.pct((wert_heute / start - 1) * 100, 1, vz=True),
              f"Start {_datum_de(depot.get('start'))}", delta_color="off")
    k3.metric("Positionen", f"{len(a)} Aktien · {len(e)} ETFs", f"Kasse {FMT.eur(depot.get('kasse') or 0, 0)}",
              delta_color="off")
    laeufe = depot.get("laeufe") or []
    k4.metric("Letzte Umschichtung", _datum_de(depot.get("stand")), f"{len(laeufe)} Umschichtung" + ("en" if len(laeufe) != 1 else ""),
              delta_color="off")
    st.caption(f"Kurse „heute“: letzter Tagesschluss aus den Ranglisten-Daten ({len(preise)} von {len(pos)} Werten; "
               "fehlende mit dem Kaufkurs). Modellrechnung – keine echten Trades, keine Anlageberatung.")
    st.plotly_chart(_wertchart(depot, wert_heute, heute), width="stretch", key="wiki_chart",
                    config={"displayModeBar": False})

    # 3 - Positionen
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
                       "Score 0–100 · Balken: Wert je Position, grün = seit Kauf im Plus")
            _tabelle(df, f"wiki_tab_{key}")
            st.plotly_chart(_balken(df, f"{titel} nach Wert"), width="stretch", key=f"wiki_balken_{key}",
                            config={"displayModeBar": False})
            st.download_button(f"⬇️ {titel} als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                               file_name=f"KI_Invest_System_{key}_{depot.get('stand')}.csv", mime="text/csv",
                               key=f"wiki_csv_{key}")

    # 4 - Verlauf der Umschichtungen
    schritte.titel(st, "wiki", 4)
    if laeufe:
        namen = [f"{_datum_de(l['datum'])} {str(l.get('zeit') or '')[11:16]} · {len(l['auftraege'])} Anpassungen"
                 .replace("  ", " ") for l in reversed(laeufe)]
        wahl = st.selectbox("Umschichtung", namen, key="wiki_lauf")
        lauf = list(reversed(laeufe))[namen.index(wahl)]
        if lauf["auftraege"]:
            zeilen, _ = WI.betraege(lauf["auftraege"])
            df = pd.DataFrame([{"Aktion": z["aktion"], "Stück": z["stueck"], "Name": z["name"],
                                "WKN/ISIN": z["wkn"] or z["isin"], "Art": "Aktie" if z["art"] == "aktie" else "ETF",
                                "Kurs €": z["kurs"], "Betrag €": z["betrag"]} for z in zeilen])
            st.dataframe(df, hide_index=True, width="stretch", key="wiki_auftraege",
                         column_config={"Kurs €": st.column_config.NumberColumn(format="%.2f"),
                                        "Betrag €": st.column_config.NumberColumn(format="%+.2f")},
                         height=min(38 + 35 * len(df), 420))
        else:
            st.caption("Keine Anpassungen.")
    if "vorher" in depot:
        with st.expander("↩️ Letzte Übernahme rückgängig machen"):
            st.caption("Setzt das Modelldepot auf den Stand vor der letzten Übernahme zurück (nur einen Schritt).")
            if st.button("Rückgängig machen", key="wiki_zurueck", disabled=not h.get("schreiben_ok", True)):
                ok, _ = h["schreiben"](PFAD_DEPOT, lambda g: WI.rueckgaengig(g), {},
                                       "wiki-idee: rückgängig [skip ci]")
                st.session_state["_wiki_meldung"] = ("↩️ Letzte Übernahme rückgängig gemacht." if ok
                                                     else None)
                if not ok:
                    st.error("Rückgängig machen fehlgeschlagen.")
                else:
                    st.rerun()
    aus = depot.get("ausgeschlossen") or []
    if aus:
        with st.expander(f"🚫 Wegen Warnsignalen ausgeschlossen ({len(aus)})"):
            st.dataframe(pd.DataFrame(aus).rename(columns={"name": "Aktie", "grund": "Grund"}), hide_index=True,
                         width="stretch", key="wiki_aus")

    # 5 - Rangliste & Methode
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
    with st.expander("ℹ️ So funktioniert das KI_Invest_System"):
        st.markdown(
            "- **Start:** 100.000 € – 70 % auf **50 Aktien**, 30 % auf **20 ETFs**, je Klasse gleich gewichtet "
            "(je Aktie ca. 1.400 €, je ETF 1.500 €), ganze Stück; die Restkasse wird auf die Positionen verteilt.\n"
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
            f"- **Nach Bedarf:** „Liste jetzt erstellen“ bewertet neu und holt aktuelle Kurse (ls-tc.de). Ein Wert "
            f"bleibt, solange er in den Top {WI.PUFFER_AKTIEN} (Aktien) bzw. Top {WI.PUFFER_ETF} (ETFs) steht – kein "
            "Tausch wegen kleiner Score-Schwankungen; freie Plätze bekommen die Besten. Alle Positionen werden "
            "auf das Zielgewicht zurückgesetzt (im wikifolio ohne Kosten).\n"
            "- **Übernehmen:** Erst wenn du die Liste im wikifolio umgesetzt hast und „Als umgesetzt übernehmen“ "
            "klickst, ändert sich das Modelldepot – die nächste Liste rechnet davon aus. Rückgängig ist möglich.\n"
            "- **Kein Trading-Roboter:** Es werden keine Orders ausgeführt. Grundlage sind vergangene Daten; keine "
            "Anlageberatung.")
