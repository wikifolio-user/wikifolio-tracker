"""Investment-Scanner im Portfolio Builder (Oberflaeche). Rechenkern: scanner.py.

Kapital, Sparrate, Kredit, Laufzeit und Zielvermoegen kommen aus den Builder-Eingaben; die Scanner-
Einstellungen (Risikoprofil, Aufteilung, Verlusttoleranz, Hoechstgewicht, Kosten, Inflation) werden mit
ihnen gespeichert. Gerechnet wird nur auf Knopfdruck - das Ergebnis bleibt in der Sitzung stehen.
"""
import datetime
import html

import pandas as pd
import streamlit as st

import portfolio_builder as P
import scanner as S
from portfolio_builder_ui import _smartphone

PROFIL_TITEL = {"niedrig": "Niedrig", "mittel": "Mittel", "hoch": "Hoch", "eigene": "Eigene"}
ART_TITEL = {"etf": "ETF", "aktie": "Aktie", "wikifolio": "wikifolio", "cash": "Cash"}


def _de(x, dez=0):
    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x, dez=0):
    return ("−" if x < -1e-9 else "") + _de(abs(x), dez) + " €"


def _pct(x, dez=1, vz=False):
    if x is None:
        return "–"
    return ("+" if vz and x > 0 else "−" if x < 0 else "") + _de(abs(x), dez) + " %"


def _esc(t):
    return html.escape("" if t is None else str(t))


# ---------------------------------------------------------------- Daten
def _daten(h, katalog):
    """Kandidaten aus Qualitaets-Score (Fundamentaldaten), Index-Listen und Builder-Katalog + Datenstand."""
    lies = (h or {}).get("gh_read_taeglich")

    def datei(pfad):
        try:
            return (lies(pfad, None) if lies else None) or {}
        except Exception:
            return {}

    q = datei("state/qualitaet.json")
    alle = {}
    for i in range(4):
        d = datei(f"state/top50_alle_{i}.json")
        f = d.get("felder") or []
        if "s" in f:
            for z in d.get("zeilen") or []:
                alle[z[f.index("s")]] = dict(zip(f, z))
    fx = {k: v[1] for k, v in (datei("state/top50_fx.json") or {}).items()
          if isinstance(v, (list, tuple)) and len(v) > 1 and v[1]}
    top = datei("state/top50.json")
    kand = S.kandidaten_aktien(q.get("werte") or {}, alle, fx) + S.kandidaten_katalog(katalog)
    stand = {"Qualitäts-Score (Fundamentaldaten)": q.get("stand"), "Ranglisten / Performance": top.get("stand")}
    return kand, stand


# ---------------------------------------------------------------- Einstellungen
def _profil_gewaehlt():
    p = st.session_state.get("pb_scan_profil")
    if p in S.PROFILE:
        st.session_state["pb_scan_max_dd"] = S.PROFILE[p]["max_dd"]
        for k in ("etf", "aktie", "wikifolio", "cash"):
            st.session_state[f"pb_scan_{k}"] = S.PROFILE[p][k]


def _einstellungen(e):
    st.segmented_control("Risikobereitschaft", list(PROFIL_TITEL), format_func=PROFIL_TITEL.get,
                         key="pb_scan_profil", on_change=_profil_gewaehlt,
                         help="Niedrig / Mittel / Hoch sind Vorschläge für die Aufteilung und die Verlusttoleranz. "
                              "„Eigene“: alles selbst festlegen.")
    eigene = e["scan_profil"] == "eigene"
    handy = _smartphone()
    with st.container(key="pb_scan_reihe1"):
        # Handy: 2 je Zeile - bei 4 nebeneinander zerbrechen die Beschriftungen
        c = (st.columns(2, vertical_alignment="bottom") + st.columns(2, vertical_alignment="bottom")) if handy \
            else st.columns(4, vertical_alignment="bottom")
        for spalte, (k, titel) in zip(c, (("etf", "ETFs %"), ("aktie", "Aktien %"), ("wikifolio", "wikifolios %"),
                                          ("cash", "Cash %"))):
            spalte.number_input(titel, 0.0, 100.0, step=5.0, format="%.0f", key=f"pb_scan_{k}", disabled=not eigene,
                                help=None if eigene else "Für eigene Werte oben „Eigene“ wählen.")
    summe = sum(e[f"scan_{k}"] for k in ("etf", "aktie", "wikifolio", "cash"))
    if eigene and abs(summe - 100) > 0.5:
        st.caption(f"Summe {_de(summe)} % – wird beim Berechnen auf 100 % umgerechnet.")
    with st.container(key="pb_scan_reihe2"):
        c = (st.columns(2, vertical_alignment="bottom") + st.columns(2, vertical_alignment="bottom")) if handy \
            else st.columns(4, vertical_alignment="bottom")
        c[0].number_input("Max. Verlust %", 5.0, 95.0, step=5.0, format="%.0f", key="pb_scan_max_dd",
                          help="Höchster tolerierter zwischenzeitlicher Rückgang vom bisherigen Höchststand. Geprüft wird, dass er in 19 "
                               "von 20 simulierten Verläufen (95 %) nicht überschritten wird – garantiert ist das nie.")
        c[1].number_input("Max. je Position %", 1.0, 100.0, step=0.5, format="%.1f",
                          key="pb_scan_max_gewicht", help="Höchstgewicht je Position: keine einzelne Aktie, kein ETF, "
                                                          "kein wikifolio darüber.")
        c[2].number_input("Kosten % p. a.", 0.0, 5.0, step=0.1, format="%.1f", key="pb_scan_kosten",
                          help="Laufende Kosten, Spreads, Ordergebühren – werden von der Rendite abgezogen.")
        c[3].number_input("Inflation % p. a.", -5.0, 20.0, step=0.5, format="%.1f", key="pb_scan_inflation",
                          help="Nur für die Kaufkraft-Angabe (realer Wert am Ende).")
    st.toggle("Auf Zielwahrscheinlichkeit optimieren", key="pb_scan_optimieren",
              help="Testet, wie viel des Depots investiert und wie viel Cash sein sollte: höchste Wahrscheinlichkeit, "
                   "das Ziel zu erreichen, ohne die Verlusttoleranz zu überschreiten.")


# ---------------------------------------------------------------- Rechnen
def _berechnen(h, e, katalog):
    kand, stand = _daten(h, katalog)
    jahre = P.monate(e) / 12.0
    bewertet = S.bewerten(kand, jahre)
    auft = S.aufteilung(e)
    depot = S.musterdepot(bewertet, auft, e["scan_max_gewicht"])
    ziel = e["zielvermoegen"]
    opt = None
    if e["scan_optimieren"] and depot["positionen"]:
        opt = S.optimieren(depot, e, ziel, e["scan_max_dd"], e["scan_kosten"])
        depot = S.skalieren(depot, opt["beste"])
    mu, sigma = S.portfolio_kennzahlen(depot)
    start, cfs, rest = S.zahlungsplan(e)
    sim = S.simulieren(mu, sigma, start, cfs, e["scan_kosten"], pfade=10000)
    a = S.auswerten(sim, ziel, rest)
    alt = None
    if ziel > 0 and (a["wahrscheinlichkeit"] or 0) < 0.5:
        alt = S.alternativen(mu, sigma, e, ziel, e["scan_kosten"])
    benoetigt = P.benoetigte_rendite(e) if ziel > 0 else None
    return {"zeit": datetime.datetime.now().strftime("%d.%m.%Y, %H:%M Uhr"), "stand": stand,
            "anzahl": {k: sum(1 for c in bewertet if c["art"] == k) for k in ("aktie", "etf", "wikifolio")},
            "bewertet": bewertet, "aufteilung": auft, "depot": depot, "optimierung": opt, "mu": mu, "sigma": sigma,
            "auswertung": a, "verlauf": S.verlauf_jaehrlich(sim), "restschuld": rest, "start": start,
            "eingezahlt": start + sum(c for c in cfs if c > 0), "alternativen": alt, "benoetigt": benoetigt,
            "monate": len(cfs), "eingaben": dict(e)}


def _signatur(e):
    felder = [k for k in e if k.startswith("scan_")] + ["anfangskapital", "sonstiges_kapital", "kredit_summe",
                                                        "kredit_rate", "kredit_zins_pa", "einzahlung", "entnahme",
                                                        "ausgaben", "laufzeit", "laufzeit_einheit", "zielvermoegen"]
    return tuple((k, e.get(k)) for k in sorted(felder))


# ---------------------------------------------------------------- Anzeige
def _tabelle_html(kopf, zeilen, rechts=(), text=(), breit=False):
    """Tabelle; rechts = rechtsbuendige Spalten, text = Spalten mit Fliesstext (duerfen umbrechen).
    Erste Spalte bleibt beim seitlichen Wischen stehen."""
    def kl(i):
        return " ".join(k for k, ja in (("r", i in rechts), ("t", i in text), ("n", i == 0)) if ja)

    th = "".join(f'<th class="{kl(i)}">{_esc(k)}</th>' for i, k in enumerate(kopf))
    tr = "".join("<tr>" + "".join(f'<td class="{kl(i)}">{z}</td>' for i, z in enumerate(zeile))
                 + "</tr>" for zeile in zeilen)
    st.markdown(f'<div class="pb-scan-wrap"><table class="pb-scan{" breit" if breit else ""}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody>'
                f'</table></div>', unsafe_allow_html=True)


def _kennung(c):
    return c.get("isin") or c.get("wkn") or c.get("ticker") or "–"


def _musterdepot(erg, kapital):
    d = erg["depot"]
    for hw in d["hinweise"]:
        st.info(hw)
    zeilen = []
    for p in sorted(d["positionen"], key=lambda p: (list(S.KLASSEN).index(p["art"]), -p["score"])):
        pr = p["prognose"]
        grund = f"Score {p['score']}" + (f" · {', '.join(p['chancen'][:2])}" if p["chancen"] else "")
        # wichtigste Spalten direkt hinter dem Namen (Handy: ohne Wischen sichtbar)
        zeilen.append([f"<b>{_esc(p['name'])}</b>", _pct(p["gewicht"]), _eur(kapital * p["gewicht"] / 100),
                       _pct(pr["mu"], 1, True), _pct(p["gewicht"] / 100 * pr["mu"], 2, True), ART_TITEL[p["art"]],
                       _esc(_kennung(p)), _esc(grund)])
    zeilen.append(["<b>Cash / Tagesgeld</b>", _pct(d["cash"]), _eur(kapital * d["cash"] / 100),
                   _pct(S.ANNAHMEN["tagesgeld"], 1, True), _pct(d["cash"] / 100 * S.ANNAHMEN["tagesgeld"], 2, True),
                   "Cash", "–", "Puffer, nicht verteilbarer Rest"])
    summe = sum(p["gewicht"] for p in d["positionen"]) + d["cash"]
    zeilen.append(["<b>Summe</b>", f"<b>{_pct(summe)}</b>", f"<b>{_eur(kapital * summe / 100)}</b>", "",
                   f"<b>{_pct(erg['mu'], 2, True)}</b>", "", "", ""])
    _tabelle_html(["Wertpapier", "Gewicht", "Betrag", "Erw. Rendite p. a.", "Beitrag", "Kategorie",
                   "ISIN / WKN / Ticker", "Begründung"], zeilen, rechts=(1, 2, 3, 4), text=(7,), breit=True)
    st.caption(f"{len(d['positionen'])} Positionen, jede höchstens {_pct(d.get('max_gewicht', 5))} · Erwartung vor "
               f"Kosten · „Beitrag“ = Gewicht × erwartete Rendite.")
    # als Callback: laeuft vor dem Neuaufbau, darf also auch "Automatisch aufs Ziel" umstellen
    st.button("📥 Musterdepot in den Builder übernehmen", key="pb_scan_uebernehmen", type="primary",
              width="stretch", on_click=_uebernehmen, args=(d,),
              help="Ersetzt die Positionen oben durch das Musterdepot (Gewichte, erwartete Renditen aus der "
                   "Prognose). „Automatisch aufs Ziel“ wird dabei ausgeschaltet.")


def _uebernehmen(d):
    pos = []
    for p in d["positionen"]:
        pos.append({"name": p["name"], "kurs": p.get("kurs") or 0.0, "gewicht": round(p["gewicht"], 4),
                    "art": p["art"], "wkn": p.get("wkn") or "", "isin": p.get("isin") or "",
                    "rendite": round(p["prognose"]["mu"], 2), "rendite_quelle": "Scanner-Prognose",
                    "rendite_basis": "1J"})
    if d["cash"] > 0.01:
        pos.append({"name": P.TAGESGELD, "kurs": 1.0, "gewicht": round(d["cash"], 4), "art": "sonstig",
                    "rendite": S.ANNAHMEN["tagesgeld"], "rendite_quelle": "Annahme Tagesgeld"})
    st.session_state["pb_positionen"] = P.bereinigen({"positionen": pos})["positionen"]
    st.session_state["pb_auto_ziel"] = False
    st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
    st.session_state["pb_meldung"] = (f"Musterdepot mit {len(pos)} Positionen übernommen – fehlende Kurse werden "
                                      "geholt, die Stückzahlen rechnen sich daraus.")


def _top_investments(erg):
    n = st.select_slider("Anzahl je Anlageklasse", [10, 25, 50], value=10, key="pb_scan_top_n")
    im_depot = {(_kennung(p), p["name"]): p["gewicht"] for p in erg["depot"]["positionen"]}
    for art in ("etf", "aktie", "wikifolio"):
        liste = [c for c in erg["bewertet"] if c["art"] == art][:n]
        st.markdown(f"**{S.KLASSEN[art]}** · {erg['anzahl'][art]} bewertet")
        if not liste:
            st.caption("Keine Daten.")
            continue
        zeilen = []
        for i, c in enumerate(liste, 1):
            pr = c["prognose"]
            hist = f"{_pct(c['hist'], 1, True)} p. a. ({c['hist_jahre']:.0f} J.)" if c["hist"] is not None else "–"
            zeilen.append([f"{i}. <b>{_esc(c['name'])}</b>" + ("" if c["ausreichend"] else " <span class=gr>"
                                                                          "(zu wenig Daten)</span>"),
                           f"<b>{c['score']}</b>", f"{_pct(pr['pess'], 0, True)} … {_pct(pr['opt'], 0, True)}", hist,
                           S.risikostufe(pr["sigma"]),
                           _pct(im_depot.get((_kennung(c), c["name"]))) if (_kennung(c), c["name"]) in im_depot
                           else "–", _esc(_kennung(c)),
                           _esc(", ".join(c["chancen"]) or "–"), _esc(", ".join(c["risiken"]) or "–")])
        _tabelle_html(["Name", "Score", "Erwartet p. a. (10–90 %)", "Historisch", "Risiko", "Im Depot",
                       "ISIN / WKN / Ticker", "Chancen", "Risiken"], zeilen, rechts=(1, 2, 3, 5), text=(7, 8),
                      breit=True)
    st.caption("Score 0–100 je Anlageklasse (Rang innerhalb der Klasse). Erwartete Spanne: 10- bis 90-%-Bereich der "
               "durchschnittlichen Jahresrendite über deinen Anlagezeitraum – keine Garantie.")


def _prognose(erg, e):
    a, ziel = erg["auswertung"], e["zielvermoegen"]
    w = a["wahrscheinlichkeit"]
    dd_ok = a["dd95"] <= e["scan_max_dd"]
    score = None if w is None else int(round(w * 100 * (1.0 if dd_ok else 0.8)))
    jahre = erg["monate"] / 12.0
    real = a["end"][50] / (1 + e["scan_inflation"] / 100.0) ** jahre
    k = [("Benötigte Rendite p. a.", _pct(erg["benoetigt"]["rendite"], 2) if erg["benoetigt"] else "–",
          "für das Zielvermögen" if ziel > 0 else "kein Ziel eingetragen"),
         ("Erwartete Rendite p. a.", _pct(erg["mu"] - e["scan_kosten"], 2), f"nach {_pct(e['scan_kosten'])} Kosten · "
                                                                             f"Schwankung {_pct(erg['sigma'])}"),
         ("Erwartetes Endvermögen", _eur(a["end"][50]), f"Median, netto · real {_eur(real)}"),
         ("Zielwahrscheinlichkeit", _pct(w * 100 if w is not None else None, 0),
          f"Ziel {_eur(ziel)}" if ziel > 0 else "Zielvermögen oben eintragen"),
         ("Zielerreichungs-Score", "–" if score is None else f"{score}/100",
          "Wahrscheinlichkeit, abgewertet bei verletzter Verlusttoleranz"),
         ("Max. Rückgang (95 %)", _pct(-a["dd95"], 0), "eingehalten" if dd_ok else
          f"über deiner Toleranz von {_pct(e['scan_max_dd'], 0)}")]
    st.markdown('<div class="pb-scan-kpis">' + "".join(
        f'<div class="k"><div class="l">{_esc(l)}</div><div class="w">{_esc(v)}</div><div class="s">{_esc(s)}</div>'
        f'</div>' for l, v, s in k) + "</div>", unsafe_allow_html=True)
    _faecher(erg, ziel)
    szen = [("Pessimistisch (10 %)", a["end"][10]), ("Basis (Median)", a["end"][50]), ("Optimistisch (90 %)",
                                                                                         a["end"][90])]
    _tabelle_html(["Szenario", "Endvermögen netto", "Rendite p. a. (ca.)"],
                  [[s, _eur(v), _pct(_rendite_aus(erg, v + erg["restschuld"]), 1, True)] for s, v in szen],
                  rechts=(1, 2))
    zeilen = [[f"Jahr {m // 12}" if m % 12 == 0 else f"Monat {m}", _eur(v["p10"]), _eur(v["p50"]), _eur(v["p90"])]
              for v in erg["verlauf"] for m in [v["monat"]]]
    with st.expander("Depotentwicklung je Jahr"):
        _tabelle_html(["", "Pessimistisch (10 %)", "Median", "Optimistisch (90 %)"], zeilen, rechts=(1, 2, 3))
        st.caption("Depotwert vor Abzug eines Kredits; Sparraten und Kosten eingerechnet, monatliches Rebalancing.")
    if erg["optimierung"]:
        o = erg["optimierung"]
        st.markdown("**Optimierung: investierter Anteil gegen Cash**")
        _tabelle_html(["Investiert", "Erw. Rendite", "Zielwahrscheinlichkeit", "Max. Rückgang (95 %)", ""],
                      [[_pct(s["investiert"], 0), _pct(s["mu"], 1), _pct((s["wahrscheinlichkeit"] or 0) * 100, 0),
                        _pct(-s["dd95"], 0), "✓ gewählt" if s["anteil"] == o["beste"] else
                        ("über Toleranz" if s["dd95"] > e["scan_max_dd"] else "")] for s in o["stufen"]],
                      rechts=(0, 1, 2, 3))
        if not o["eingehalten"]:
            st.warning("Selbst mit dem geringsten getesteten Anteil liegt der mögliche Rückgang über deiner Toleranz – "
                       "gewählt ist die vorsichtigste Variante. Toleranz erhöhen oder mehr Cash/Anleihen einplanen.")
    alt = erg["alternativen"]
    if alt:
        tipps = []
        if alt.get("sparrate"):
            tipps.append(f"Sparrate auf etwa **{_eur(alt['sparrate'])}/Monat** erhöhen")
        if alt.get("jahre_mehr"):
            tipps.append(f"Anlagezeitraum um etwa **{alt['jahre_mehr']} Jahre** verlängern")
        tipps.append(f"Ziel auf etwa **{_eur(alt['erreichbar'])}** anpassen (Median)")
        st.warning("Das Ziel ist mit realistischen Annahmen eher unwahrscheinlich (unter 50 %). Die Renditeannahmen "
                   "werden dafür bewusst **nicht** erhöht. Für 50 % Wahrscheinlichkeit: " + " · oder ".join(tipps) + ".")


def _rendite_aus(erg, endwert):
    """Grobe Jahresrendite, die vom Start mit den Zahlungen auf endwert fuehrt (Bisektion)."""
    e = erg["eingaben"]
    lo, hi = -50.0, 60.0
    for _ in range(50):
        m = (lo + hi) / 2
        if P.simulation(e, rendite_pa=m)["endwert"] < endwert:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def _faecher(erg, ziel):
    import plotly.graph_objects as go
    v = erg["verlauf"]
    heute = datetime.date.today()
    x = [heute.replace(day=1) + datetime.timedelta(days=round(z["monat"] * 30.44)) for z in v]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[z["p90"] for z in v], mode="lines", line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=[z["p10"] for z in v], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(22,199,132,0.16)", name="10–90 % der Verläufe",
                             customdata=[f"{_eur(z['p10'])} – {_eur(z['p90'])}" for z in v],
                             hovertemplate="10–90 %: %{customdata}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=[z["p50"] for z in v], mode="lines", line=dict(color="#16C784", width=2.6),
                             name="Median", customdata=[_eur(z["p50"]) for z in v],
                             hovertemplate="Median: %{customdata}<extra></extra>"))
    if ziel > 0:
        fig.add_hline(y=ziel + erg["restschuld"], line=dict(color="#F5B942", dash="dot", width=1.5),
                      annotation_text="Ziel", annotation_font_color="#F5B942")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=300, separators=",.",
                      margin=dict(l=4, r=4, t=8, b=4), font=dict(color="#D6D9DE", size=12), hovermode="x unified",
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0),
                      xaxis=dict(showgrid=False, tickformat="%Y"),
                      yaxis=dict(gridcolor="#1E2228", tickformat=",.0f", ticksuffix=" €", side="right"))
    st.plotly_chart(fig, width="stretch", key="pb_scan_faecher", config={"displayModeBar": False})


def _risiken(erg, kapital):
    d = erg["depot"]
    st.markdown("**Stresstest: sofortiger Rückgang des Depots**")
    _tabelle_html(["Szenario", "Rückgang", "In Euro (heute)"],
                  [[s["szenario"], _pct(s["prozent"], 1), _eur(s["euro"])] for s in S.stresstest(d, kapital)],
                  rechts=(1, 2))
    st.caption("Annahmen je Anlageklasse (Crash: Aktien −40 %, ETFs −35 %, wikifolios −40 %; Rezession −25/−20/−25 %; "
               "Inflation: realer Verlust im Jahr; enttäuschende Gewinne −20/−12/−15 %).")
    schwach = S.schwachstellen(d)
    if schwach:
        st.markdown("**Schwachstellen**\n\n" + "\n".join(f"- {s}" for s in schwach))
    st.markdown("**Grenzen der Vorhersage**\n\n"
                "- Korrelationen steigen in Krisen – Streuung schützt dann weniger als im Modell.\n"
                "- Vergangene Gewinner sind oft nicht die künftigen (Mean Reversion) – darum werden ihre Renditen "
                "begrenzt und zur langfristigen Erwartung hingezogen.\n"
                "- Die Ranglisten enthalten nur heute noch aktive Werte (Survivorship Bias).\n"
                "- Die Verlusttoleranz ist ein Planungswert, keine Garantie: reale Einbrüche können tiefer sein.")


def _plan(erg, e, positionen):
    d, kapital = erg["depot"], erg["start"]
    tranche = 3 if kapital < 50000 else 6
    st.markdown(
        "**Handlungsplan**\n\n"
        f"1. **Aufbau:** Startkapital in {tranche} gleichen Monatsraten investieren (glättet den Einstiegszeitpunkt), "
        "zuerst die ETFs, dann Einzelaktien, zuletzt wikifolios.\n"
        f"2. **Sparrate:** {_eur(e['einzahlung'])} im Monat nach den Zielgewichten verteilen – bevorzugt in Positionen, "
        "die unter ihrem Zielgewicht liegen (spart Verkäufe).\n"
        f"3. **Kontrolle:** vierteljährlich; Scanner neu rechnen lassen (die Daten werden täglich aktualisiert).\n"
        f"4. **Rebalancing:** wenn eine Position über {_pct(e['scan_max_gewicht'] + 1, 0)} steigt oder eine "
        "Anlageklasse mehr als 5 Prozentpunkte vom Ziel abweicht – sonst laufen lassen (Kosten, Steuern).\n"
        "5. **Austausch:** nur wenn ein Wert in zwei Prüfungen nacheinander deutlich (≥ 10 Punkte) schlechter "
        "abschneidet als der schwächste Wert im Musterdepot.\n"
        "6. **Steuern:** Gewinne sind beim Verkauf steuerpflichtig (in Deutschland Abgeltungsteuer plus "
        "Solidaritätszuschlag, ggf. Kirchensteuer; Freibetrag beachten) – in der Simulation **nicht** abgezogen.")
    if positionen:
        st.markdown("**Empfehlungen zu deinen aktuellen Positionen**")
        emp = S.empfehlungen(positionen, d, erg["bewertet"])
        _tabelle_html(["Position", "Empfehlung", "Ist", "Soll", "Score"],
                      [[_esc(x["name"]), f"<b>{_esc(x['aktion'])}</b>", _pct(x["ist"]), _pct(x["soll"]),
                        "–" if x["score"] is None else str(x["score"])] for x in emp], rechts=(2, 3, 4))


def _daten_annahmen(erg):
    st.markdown("**Datenstand**\n\n" + "\n".join(
        f"- {k}: {(v or 'nicht verfügbar')[:16].replace('T', ' ')}" for k, v in erg["stand"].items())
        + f"\n- Berechnet: {erg['zeit']}\n- Bewertet: {erg['anzahl']['aktie']} Aktien, {erg['anzahl']['etf']} ETFs, "
          f"{erg['anzahl']['wikifolio']} wikifolios")
    st.markdown("**Verwendet je Anlageklasse**\n\n"
                "- **Aktien:** Qualitäts-Score der Watchlist (Umsatz-, Gewinn- und Free-Cashflow-Wachstum, ROIC, "
                "Margen, Verschuldung, Forward-KGV, EV/EBIT, FCF-Rendite, Burggraben), Kursentwicklung 1–10 J.\n"
                "- **ETFs:** Kursentwicklung 1–10 J., Volatilität und maximaler Drawdown (soweit vorhanden). "
                "Hebel- und Short-Produkte ausgeschlossen, je Kernindex nur ein ETF.\n"
                "- **wikifolios:** Kursentwicklung, Volatilität, Drawdown, Länge der Historie; im Musterdepot "
                f"erst ab {S.ANNAHMEN['wikifolio_min_jahre']:.0f} Jahren Historie.")
    st.markdown("**Nicht in den Daten (deshalb nicht bewertet)**\n\n"
                "- ETFs: TER, Tracking Difference/Error, Fondsvolumen, Replikation, Länder-/Sektoraufteilung\n"
                "- wikifolios: Gebühren, Handelsstrategie, Trader, investiertes Kapital, Handelsaktivität\n"
                "- Aktien: Analystenprognosen\n- Korrelationen je Einzelwert (stattdessen Modellannahme je Klasse)")
    a = S.ANNAHMEN
    st.markdown("**Modellannahmen**\n\n"
                f"- Langfristige Erwartung p. a.: Aktien {a['erwartung']['aktie']:.1f} %, ETFs {a['erwartung']['etf']:.1f} %, "
                f"wikifolios {a['erwartung']['wikifolio']:.1f} %, Tagesgeld {a['tagesgeld']:.1f} %\n"
                f"- Historische Renditen werden auf ±{a['rendite_deckel']:.0f} % p. a. begrenzt; sie zählen je nach "
                f"Länge der Historie, höchstens zu {a['vorsprung_anteil'] * 50:.0f} % (bei 10 Jahren)\n"
                "- Aktien: zur Hälfte Fundamental-Erwartung = FCF-Rendite + ½ Umsatzwachstum (begrenzt)\n"
                f"- Schwankung ohne Messwert: Aktien {a['vola']['aktie']:.0f} %, ETFs {a['vola']['etf']:.0f} %, "
                f"wikifolios {a['vola']['wikifolio']:.0f} %\n"
                f"- Korrelation: Aktie–Aktie {a['korrelation'][('aktie', 'aktie')]}, ETF–ETF "
                f"{a['korrelation'][('etf', 'etf')]}, Aktie–ETF {a['korrelation'][('aktie', 'etf')]}, "
                f"wikifolio–wikifolio {a['korrelation'][('wikifolio', 'wikifolio')]}\n"
                "- 10.000 simulierte Verläufe, monatlich; Krisen-Regime (gebündelte Einbrüche) ohne Änderung von "
                "Durchschnittsrendite und Gesamtschwankung")
    st.caption("Keine Anlageberatung. Modellierte Wahrscheinlichkeiten sind keine garantierten Eintrittswahrscheinlichkeiten; "
               "vergangene Entwicklungen sind kein verlässlicher Indikator für die Zukunft.")


def render(h, e, katalog_fn):
    """Scanner-Karte im Builder. e = bereinigte Builder-Eingaben, katalog_fn() = Builder-Katalog."""
    with st.container(border=True, key="pb_scanner"):
        st.markdown('<div class="pb-karte-t">🤖 Investment-Scanner – Musterdepot für dein Ziel</div>',
                    unsafe_allow_html=True)
        st.caption("Durchsucht Aktien (mit Fundamentaldaten), ETFs und wikifolios aus den Daten der Watchlist, bewertet "
                   "sie, stellt ein Musterdepot zusammen und simuliert dein Ziel mit Kapital, Sparrate und Laufzeit von "
                   "oben.")
        _einstellungen(e)
        sig = _signatur(e)
        erg = st.session_state.get("pb_scan_erg")
        veraltet = erg is not None and st.session_state.get("pb_scan_sig") != sig
        if st.button("🔍 Scannen & Musterdepot berechnen" if erg is None else "🔄 Neu berechnen",
                     key="pb_scan_los", type="primary" if erg is None or veraltet else "secondary", width="stretch"):
            with st.spinner("Bewerte Aktien, ETFs und wikifolios und simuliere 10.000 Verläufe …"):
                erg = _berechnen(h, e, katalog_fn())
            st.session_state["pb_scan_erg"], st.session_state["pb_scan_sig"] = erg, sig
            veraltet = False
        if erg is None:
            return
        if veraltet:
            st.info("Eingaben geändert – „Neu berechnen“, damit das Ergebnis dazu passt.")
        kapital = erg["start"]
        tabs = st.tabs(["📦 Musterdepot", "🏆 Top-Investments", "📈 Prognose", "⚠️ Risiken", "🧭 Plan",
                        "ℹ️ Daten"])
        with tabs[0]:
            _musterdepot(erg, kapital)
        with tabs[1]:
            _top_investments(erg)
        with tabs[2]:
            _prognose(erg, erg["eingaben"])
        with tabs[3]:
            _risiken(erg, kapital)
        with tabs[4]:
            _plan(erg, erg["eingaben"], e["positionen"])
        with tabs[5]:
            _daten_annahmen(erg)


CSS = """
<style>
.pb-scan-wrap { overflow-x:auto; margin:4px 0 10px; }
table.pb-scan { width:100%; border-collapse:separate; border-spacing:0; font-size:.84rem; }
table.pb-scan.breit { min-width:640px; }
table.pb-scan th { text-align:left; color:#9AA0A6; font-weight:700; font-size:.72rem; letter-spacing:.4px;
  text-transform:uppercase; padding:6px 8px; border-bottom:1px solid #262B33; vertical-align:bottom; }
table.pb-scan td { padding:6px 8px; border-bottom:1px solid #1A1E24; vertical-align:top; white-space:nowrap; }
table.pb-scan td.t { white-space:normal; min-width:180px; max-width:280px; }
table.pb-scan .n { position:sticky; left:0; background:#0A0B0D; z-index:1; max-width:220px; white-space:normal; }
table.pb-scan .r { text-align:right; white-space:nowrap; }
table.pb-scan .gr { color:#9AA0A6; font-weight:400; }
.pb-scan-kpis { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin:6px 0 10px; }
.pb-scan-kpis .k { border:1px solid #262B33; border-radius:10px; padding:10px 12px; background:#0F1115; }
.pb-scan-kpis .l { color:#9AA0A6; font-size:.72rem; text-transform:uppercase; letter-spacing:.4px; }
.pb-scan-kpis .w { font-size:1.25rem; font-weight:800; margin-top:2px; }
.pb-scan-kpis .s { color:#9AA0A6; font-size:.76rem; margin-top:2px; }
@media (max-width: 640px) { .pb-scan-kpis { grid-template-columns:repeat(2, minmax(0,1fr)); }
  table.pb-scan .n { max-width:150px; } table.pb-scan { font-size:.8rem; } }
</style>
"""
