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


def _kacheln(df):
    """Positionen als Kacheln: Flaeche = Wert, gruppiert nach Branche/Region, Farbe = seit Kauf %."""
    ids, labels, parents, werte, farben, texte = [], [], [], [], [], []
    for g, teil in df.groupby(df["Gruppe"].replace({"–": "Sonstige", "": "Sonstige"})):
        ids.append(f"g:{g}")
        labels.append(g)
        parents.append("")
        werte.append(float(teil["Wert €"].sum()))
        farben.append(0.0)
        texte.append(FMT.eur(float(teil["Wert €"].sum()), 0))      # Gruppe: neutral (0 %)
        for _, r in teil.iterrows():
            ids.append(f"g:{g}/{r['Name']}/{r['WKN/ISIN']}")
            labels.append(str(r["Name"])[:26])
            parents.append(f"g:{g}")
            werte.append(float(r["Wert €"]))
            seit = r["seit Kauf %"] if pd.notna(r["seit Kauf %"]) else 0.0
            farben.append(float(seit))
            texte.append(f"{FMT.eur(float(r['Wert €']), 0)} · {FMT.pct(seit, 1, vz=True)} · Score {r['Score']:.0f}"
                         if pd.notna(r["Score"]) else f"{FMT.eur(float(r['Wert €']), 0)} · {FMT.pct(seit, 1, vz=True)}")
    fig = go.Figure(go.Treemap(ids=ids, labels=labels, parents=parents, values=werte, branchvalues="total",
                               text=texte, textinfo="label+text", tiling=dict(pad=3),
                               textfont=dict(size=13), pathbar=dict(visible=True),
                               marker=dict(colors=farben, colorscale=[[0, "#EF4444"], [0.5, "#334155"], [1, "#22C55E"]],
                                           cmid=0, cmin=-10, cmax=10, showscale=True,
                                           colorbar=dict(title="seit Kauf %", thickness=10)),
                               hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>"))
    fig.update_layout(height=480, margin=dict(l=4, r=4, t=4, b=4))
    return UI.chart_stil(fig, schrumpfen=False)


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
    # Werte direkt aus "Ranglisten & Screener": Aktien = Rangliste Qualitaets-Score, ETFs = ETF-Score
    lies = h["lesen_taeglich"]
    alle = [x for x in UI.parallel_lesen(lies, [f"state/qualitaet/alle_{i}.json" for i in range(6)], None)
            if isinstance(x, dict)]
    fx = {k: v[1] for k, v in (lies("state/top50_fx.json", {}) or {}).items()
          if isinstance(v, (list, tuple)) and len(v) > 1}
    yahoo_isin = (lies("state/top50_yahoo.json", {}) or {}).get("isin") or {}
    inv = {}
    for teil in UI.parallel_lesen(h["lesen_taeglich"], [f"state/investoren/ergebnis_{i:02d}.json" for i in range(16)],
                                  None):
        inv.update((teil or {}).get("werte") or {})
    katalog = [x for x in UI.parallel_lesen(h["lesen_taeglich"], [f"state/planer/katalog_gross_{i}.json"
                                                                  for i in range(4)], None) if isinstance(x, dict)]
    eur = tageskurse(katalog)                       # EUR-Tagesschluss je WKN/ISIN
    ids = KV.kennung_ids(lies("state/top50_ids.json", {}) or {}, lies("state/top50_wikifolios.json", {}) or {})
    aktien, nur_ls = WI.handelbar(WI.aktien_aus_qualitaet(alle, yahoo_isin, fx), ids)
    bewertet = [(e, {}) for e in aktien + WI.etfs_aus_katalog(katalog)]
    rang_a, aus, rang_e = WI.ranglisten(bewertet, inv, KS.HEBEL, EM.merkmale, eur, KS.je_kennung(katalog, "etf"))
    if len(rang_a) < WI.N_AKTIEN or len(rang_e) < WI.N_ETF:
        raise ValueError(f"Zu wenige bewertete Werte ({len(rang_a)} Aktien, {len(rang_e)} ETFs) – die Daten der "
                         "Agenten sind gerade unvollständig.")
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
            "alt": {k: x for k, x in depot.items() if k != "vorher"},
            "live": len(live), "kandidaten": len(jobs), "nur_ls": nur_ls, "aktien_basis": len(aktien), "rang": {"stand": jetzt.date().isoformat(),
                                                                   "aktien": rang_a[:100], "etf": rang_e[:40]}}


AKTION_FARBE = {"Neu": "#22C55E", "Kauf": "#86EFAC", "Verkauf": "#FCA5A5", "Raus": "#EF4444"}


def _anreichern(zeilen, neu, alt):
    """Auftraege + Score, Rang, Gruppe (Branche bzw. Region/Thema) und Gewicht nach der Umschichtung."""
    pos_neu, pos_alt = neu.get("positionen") or {}, (alt or {}).get("positionen") or {}
    wert = float(neu.get("wert") or 0) or 1.0
    aus = []
    for z in zeilen:
        p = pos_neu.get(z["id"]) or pos_alt.get(z["id"]) or {}
        g = p.get("gruppe") or "–"
        aus.append(dict(z, score=p.get("mix"), rang=p.get("rang"), gruppe="Sonstige" if g == "–" else g,
                        art_text="Aktie" if z["art"] == "aktie" else "ETF",
                        gewicht=(pos_neu.get(z["id"]) or {}).get("wert", 0) / wert * 100))
    return aus


def _filter(zeilen, key):
    """Mehrfachfilter Art / Aktion / Gruppe fuer Charts und Aufsteiger-Listen."""
    f1, f2, f3 = st.columns(3)
    arten = f1.multiselect("Art", ["Aktie", "ETF"], key=f"{key}_art", placeholder="alle")
    aktionen = f2.multiselect("Aktion", [a for a in ("Neu", "Kauf", "Verkauf", "Raus")
                                         if any(z["aktion"] == a for z in zeilen)], key=f"{key}_akt",
                              placeholder="alle")
    gruppen = f3.multiselect("Branche / Region", sorted({z["gruppe"] for z in zeilen}), key=f"{key}_grp",
                             placeholder="alle")
    return [z for z in zeilen if (not arten or z["art_text"] in arten) and (not aktionen or z["aktion"] in aktionen)
            and (not gruppen or z["gruppe"] in gruppen)]


def _treemap(zeilen, farbe):
    """Kacheln Art -> Branche/Region -> Wert; Flaeche = Betrag, Farbe = Aktion oder Score."""
    ids, labels, parents, werte, farben, texte = [], [], [], [], [], []
    summen = {}
    for z in zeilen:
        b = abs(z["betrag"])
        for k in (z["art_text"], f'{z["art_text"]}/{z["gruppe"]}'):
            summen[k] = summen.get(k, 0) + b
    for k, v in summen.items():
        ids.append(k)
        labels.append(("Aktien" if k == "Aktie" else "ETFs" if k == "ETF" else k.split("/", 1)[-1]))
        parents.append("" if "/" not in k else k.split("/", 1)[0])
        werte.append(v)
        farben.append("#1E293B" if "/" not in k else "#273449")
        texte.append(f"{FMT.eur(v, 0)}")
    skala = []
    for z in zeilen:
        ids.append(f'{z["art_text"]}/{z["gruppe"]}/{z["id"]}')
        labels.append(z["name"][:28])
        parents.append(f'{z["art_text"]}/{z["gruppe"]}')
        werte.append(abs(z["betrag"]))
        farben.append(AKTION_FARBE[z["aktion"]] if farbe == "Aktion" else None)
        skala.append(z.get("score"))
        texte.append(f'{z["aktion"]} {z["stueck"]} St. · {FMT.eur(z["betrag"], 0, vz=True)}'
                     + (f' · Score {z["score"]:.0f}' if z.get("score") is not None else ""))
    if farbe == "Aktion":
        marker = dict(colors=farben)
    else:
        werte_sc = [s_ for s_ in skala if s_ is not None]
        lo, hi = (min(werte_sc), max(werte_sc)) if werte_sc else (0, 100)
        hi = hi if hi > lo else lo + 1
        marker = dict(colors=farben[:len(summen)] + [s_ if s_ is not None else lo for s_ in skala],
                      colorscale=[[0, "#F87171"], [0.5, "#FBBF24"], [1, "#22C55E"]], cmin=lo, cmax=hi,
                      showscale=True, colorbar=dict(title="Score", thickness=10))
    marker["line"] = dict(width=1, color="rgba(15,23,42,.9)")
    fig = go.Figure(go.Treemap(ids=ids, labels=labels, parents=parents, values=werte, branchvalues="total",
                               marker=marker, text=texte, textinfo="label+text", maxdepth=3,
                               textfont=dict(size=13, color="#0B1220"), outsidetextfont=dict(size=15, color="#E2E8F0"),
                               pathbar=dict(visible=True, textfont=dict(size=13)),
                               hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>", tiling=dict(pad=3)))
    fig.update_layout(height=560, margin=dict(l=4, r=4, t=28, b=4))
    return UI.chart_stil(fig, schrumpfen=False)


def _streuchart(zeilen):
    """Score (x) gegen Betrag (y): oben rechts = gut bewertet und gross gekauft."""
    fig = go.Figure()
    for a in ("Neu", "Kauf", "Verkauf", "Raus"):
        d = [z for z in zeilen if z["aktion"] == a]
        if not d:
            continue
        fig.add_trace(go.Scatter(
            x=[z.get("score") for z in d], y=[z["betrag"] for z in d], mode="markers", name=a,
            marker=dict(color=AKTION_FARBE[a], size=[8 + min(abs(z["betrag"]) / 150, 18) for z in d],
                        line=dict(width=1, color="rgba(0,0,0,.35)")),
            text=[f'{z["name"]} ({z["art_text"]}, {z["gruppe"]})' for z in d],
            hovertemplate="%{text}<br>Score %{x:.0f} · %{y:+,.0f} €<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="rgba(148,163,184,.5)", width=1))
    fig.update_layout(height=440, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Score (0–100)",
                      yaxis=dict(title="Betrag", ticksuffix=" €", tickformat="+,.0f"),
                      legend=dict(orientation="h", y=-0.18))
    return UI.chart_stil(fig, schrumpfen=False)


def _veraenderungschart(zeilen, n=25):
    """Die groessten Kaeufe und Verkaeufe (je hoechstens n), nach Betrag sortiert."""
    kauf = sorted([z for z in zeilen if z["betrag"] > 0], key=lambda z: -z["betrag"])[:n]
    verk = sorted([z for z in zeilen if z["betrag"] < 0], key=lambda z: z["betrag"])[:n]
    d = sorted(kauf + verk, key=lambda z: z["betrag"])
    fig = go.Figure(go.Bar(
        x=[z["betrag"] for z in d], y=[f'{z["name"][:30]}' for z in d], orientation="h",
        marker_color=[AKTION_FARBE[z["aktion"]] for z in d],
        customdata=[[z["aktion"], z["stueck"], z["kurs"]] for z in d],
        hovertemplate="%{customdata[0]} · %{y}<br>%{x:+,.0f} € · %{customdata[1]} Stück zu "
                      "%{customdata[2]:,.2f} €<extra></extra>"))
    fig.update_layout(height=max(260, 20 * len(d) + 60), margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(ticksuffix=" €", tickformat="+,.0f"), yaxis=dict(tickfont=dict(size=10)))
    return UI.chart_stil(fig, schrumpfen=False)


HP_CSS = """<style>
.hp { display:flex; flex-direction:column; gap:6px; margin:4px 0 10px; }
.hp-z { display:grid; grid-template-columns:52px 58px 1fr auto; align-items:center; gap:10px; padding:8px 12px;
        border-radius:14px; background:rgba(148,163,184,.07); border:1px solid rgba(148,163,184,.16); }
.hp-z.hp-top { background:linear-gradient(90deg, rgba(251,191,36,.16), rgba(148,163,184,.05)); }
.hp-platz { font-size:1.65rem; font-weight:800; text-align:center; font-variant-numeric:tabular-nums;
            letter-spacing:-.02em; }
.hp-p1 { color:#FBBF24; } .hp-p2 { color:#CBD5E1; } .hp-p3 { color:#D97706; }
.hp-bew { font-size:.8rem; font-weight:800; text-align:center; padding:4px 0; border-radius:8px; }
.hp-hoch { color:#052E16; background:#4ADE80; } .hp-runter { color:#450A0A; background:#F87171; }
.hp-gleich { color:#E2E8F0; background:rgba(148,163,184,.28); }
.hp-neu { color:#422006; background:#FBBF24; } .hp-wieder { color:#082F49; background:#7DD3FC; }
.hp-name b { display:block; font-size:.98rem; line-height:1.25; }
.hp-name small { opacity:.75; font-size:.78rem; line-height:1.3; }
.hp-vor { text-align:right; font-size:.75rem; opacity:.8; line-height:1.3; white-space:nowrap; }
.hp-vor b { display:block; font-size:1rem; opacity:1; }
.hp-raus { opacity:.7; }
@media (max-width: 640px) {
  .hp-z { grid-template-columns:40px 46px 1fr; gap:8px; padding:7px 9px; }
  .hp-vor { grid-column:3; text-align:left; white-space:normal; margin-top:-4px; }
  .hp-vor b { display:inline; font-size:.8rem; margin-right:3px; }
  .hp-vor br { display:none; } .hp-vor .hp-tr::before { content:" · "; }
  .hp-platz { font-size:1.3rem; }
}
</style>"""
BEWEGUNG = {"hoch": "▲ {d}", "runter": "▼ {d}", "gleich": "=", "neu": "NEU", "wieder": "RE"}


def _hitparade_html(zeilen, raus, titel):
    """Chartliste wie in einer Musik-Hitparade: Platz, Bewegung, Name, Wochen/Listen, hoechster Platz."""
    h = [HP_CSS, f'<div class="hp" role="list" aria-label="{_esc(titel)}">']
    for z in zeilen:
        p = z["p"]
        bew = BEWEGUNG[z["bewegung"]].format(d=abs(z["delta"] or 0))
        top = " hp-top" if z["platz"] <= 3 else ""
        pk = f" hp-p{z['platz']}" if z["platz"] <= 3 else ""
        info = " · ".join(x for x in (
            "ETF" if p["art"] == "etf" else (p.get("gruppe") or ""),
            f"Score {p['mix']:.0f}" if p.get("mix") is not None else "",
            f"{p['stueck']} Stück · {FMT.eur(p['stueck'] * p['kurs'], 0)}") if x and x != "–")
        vor = (f"<b>{z['vorher']}</b>letzte Liste" if z["vorher"] else "<b>–</b>letzte Liste")
        h.append(f'<div class="hp-z{top}" role="listitem"><div class="hp-platz{pk}">{z["platz"]}</div>'
                 f'<div class="hp-bew hp-{z["bewegung"]}">{bew}</div>'
                 f'<div class="hp-name"><b>{_esc(p["name"])}</b><small>{_esc(info)}</small></div>'
                 f'<div class="hp-vor">{vor}<br><span class="hp-tr">{z["listen"]}. Liste · bester Platz {z["best"]}'
                 '</span></div></div>')
    h.append("</div>")
    if raus:
        h.append('<div class="hp hp-raus"><div style="font-weight:700;margin:6px 0 2px">⬇️ Aus den Charts gefallen'
                 f' ({len(raus)})</div>')
        for r in raus:
            p = r["p"]
            h.append(f'<div class="hp-z" role="listitem"><div class="hp-platz">–</div>'
                     f'<div class="hp-bew hp-runter">RAUS</div><div class="hp-name"><b>{_esc(p["name"])}</b>'
                     f'<small>{_esc(p.get("gruppe") or "")}</small></div>'
                     f'<div class="hp-vor"><b>{r["vorher"]}</b>letzte Liste</div></div>')
        h.append("</div>")
    return "".join(h)


def _esc(t):
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _charts_zeigen(neu_depot, alt_depot, key):
    """Hitparade der Aktien (Top 50) und ETFs (Top 20) im Vergleich zum vorigen Stand."""
    stat = (alt_depot or {}).get("charts") or {}
    t1, t2 = st.tabs(["🎵 Aktien-Charts", "🎵 ETF-Charts"])
    for tab, art, titel in ((t1, "aktie", "Aktien"), (t2, "etf", "ETFs")):
        with tab:
            zeilen, raus = WI.hitparade(neu_depot, alt_depot, art, stat)
            if not zeilen:
                st.caption("Keine Werte.")
                continue
            neu_n = sum(1 for z in zeilen if z["bewegung"] in ("neu", "wieder"))
            hoch = sum(1 for z in zeilen if z["bewegung"] == "hoch")
            runter = sum(1 for z in zeilen if z["bewegung"] == "runter")
            st.caption(f"Top {len(zeilen)} {titel} nach Score · {neu_n} Neueinsteiger · {hoch} gestiegen · "
                       f"{runter} gefallen · {len(raus)} raus. Bewegung gegenüber der letzten übernommenen Liste "
                       "(NEU = erstmals dabei, RE = Wiedereinstieg).")
            st.markdown(_hitparade_html(zeilen, raus, f"{titel}-Charts"), unsafe_allow_html=True)


def _auf_ab(zeilen, n=10):
    """Aufsteiger (neu + aufgestockt) und Absteiger (raus + reduziert) nebeneinander."""
    def karte(titel, liste, plus):
        st.markdown(f"**{titel}** ({len(liste)})")
        if not liste:
            st.caption("–")
            return
        for z in liste[:n]:
            sc = f' · Score {z["score"]:.0f}' if z.get("score") is not None else ""
            st.markdown(f'<div class="wiki-aa"><span class="{"pt-up" if plus else "pt-down"}">'
                        f'{"▲" if plus else "▼"} {FMT.eur(abs(z["betrag"]), 0)}</span> '
                        f'{z["aktion"]} · <b>{z["name"][:34]}</b><br><small>{z["stueck"]} Stück · '
                        f'{z["art_text"]} · {z["gruppe"]}{sc}</small></div>', unsafe_allow_html=True)
        if len(liste) > n:
            st.caption(f"… und {len(liste) - n} weitere (Tabelle unten)")
    st.markdown("<style>.wiki-aa{padding:6px 0;border-bottom:1px solid rgba(148,163,184,.15);"
                "line-height:1.35}</style>", unsafe_allow_html=True)
    try:
        import portfolio_builder_ui as _PB
        handy = _PB._smartphone()
    except Exception:
        handy = False
    c1, c2 = (st.container(), st.container()) if handy else st.columns(2)
    with c1:
        karte("⬆️ Aufsteiger: neu & aufgestockt",
              sorted([z for z in zeilen if z["betrag"] > 0], key=lambda z: -z["betrag"]), True)
    with c2:
        karte("⬇️ Absteiger: raus & reduziert",
              sorted([z for z in zeilen if z["betrag"] < 0], key=lambda z: z["betrag"]), False)


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
               "Tagesschluss. Im wikifolio kann der Ausführungskurs abweichen – erst verkaufen, dann kaufen. "
               f"Auswahl aus {FMT.zahl(v.get('aktien_basis') or 0, 0)} Aktien des Qualitäts-Scores "
               + ("mit ISIN, die bei Lang & Schwarz handelbar sind." if v.get("nur_ls") else
                  "mit ISIN (Handelbarkeit bei Lang & Schwarz bitte im wikifolio prüfen)."))
    if not zeilen:
        st.success("Keine Anpassungen nötig – das Depot entspricht der aktuellen Rangliste.")
    else:
        reich = _anreichern(zeilen, neu, v.get("alt"))
        gefiltert = _filter(reich, "wiki_vf")
        if not gefiltert:
            st.info("Kein Auftrag passt zum Filter.")
        else:
            ansicht = st.pills("Darstellung", ["🎵 Charts", "🗺️ Gewichtung", "⭐ Bewertung", "↕️ Käufe/Verkäufe"],
                               default="🎵 Charts", key="wiki_ansicht") or "🎵 Charts"
            if ansicht == "🎵 Charts":
                _charts_zeigen(neu, v.get("alt") or {}, "vorschlag")
            elif ansicht == "🗺️ Gewichtung":
                einheitlich = len({z["aktion"] for z in gefiltert}) == 1
                farbe = st.segmented_control("Farbe", ["Aktion", "Score"], default="Score" if einheitlich else "Aktion",
                                             key=f"wiki_farbe_{int(einheitlich)}") or "Aktion"
                st.caption("Fläche = Betrag, gruppiert nach Art und Branche bzw. Region/Thema. Grün = kaufen, "
                           "rot = verkaufen (bei „Score“: grün = hoch bewertet). Kachel antippen = hineinzoomen.")
                st.plotly_chart(_treemap(gefiltert, farbe), width="stretch", key="wiki_treemap",
                                config={"displayModeBar": False})
            elif ansicht == "⭐ Bewertung":
                st.caption("Je weiter rechts, desto besser bewertet; oberhalb der Linie wird gekauft, darunter "
                           "verkauft. Punktgröße = Betrag.")
                st.plotly_chart(_streuchart(gefiltert), width="stretch", key="wiki_streu",
                                config={"displayModeBar": False})
            else:
                st.caption("Die größten Käufe und Verkäufe (je höchstens 25).")
                st.plotly_chart(_veraenderungschart(gefiltert), width="stretch", key="wiki_veraenderung",
                                config={"displayModeBar": False})
            _auf_ab(gefiltert)
        df = pd.DataFrame([{"Aktion": z["aktion"], "Stück": z["stueck"], "Name": z["name"],
                            "WKN/ISIN": z["wkn"] or z["isin"], "Art": "Aktie" if z["art"] == "aktie" else "ETF",
                            "Kurs jetzt €": z["kurs"], "Betrag €": z["betrag"], "Bestand vorher": z["vorher"],
                            "Bestand nachher": z["nachher"], "Stück ausgeführt": z["stueck"],
                            "Ausführungskurs €": z["kurs"]} for z in zeilen], index=[z["id"] for z in zeilen])
        st.markdown("**Deine tatsächliche Umsetzung im wikifolio** – weicht etwas ab, hier die echten Werte "
                    "eintragen (Stück **0** = nicht ausgeführt). Übernommen wird genau das.")
        ist_df = st.data_editor(
            df, hide_index=True, width="stretch", key=f"wiki_ist_{v['zeit']}", height=min(38 + 35 * len(df), 560),
            disabled=[c for c in df.columns if c not in ("Stück ausgeführt", "Ausführungskurs €")],
            column_config={"Kurs jetzt €": st.column_config.NumberColumn(format="%.2f"),
                           "Betrag €": st.column_config.NumberColumn(format="%+.2f"),
                           "Stück ausgeführt": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
                           "Ausführungskurs €": st.column_config.NumberColumn(min_value=0.0, step=0.01,
                                                                              format="%.2f")})
        st.session_state["_wiki_ist"] = {i: {"stueck": int(r["Stück ausgeführt"] or 0),
                                             "kurs": float(r["Ausführungskurs €"] or 0) or None}
                                         for i, r in ist_df.iterrows()}
        st.download_button("⬇️ Liste als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           file_name=f"KI_Invest_System_liste_{neu['laeufe'][-1]['zeit'].replace(':', '')}.csv",
                           mime="text/csv", key="wiki_vorschlag_csv")
    b1, b2 = st.columns(2)
    if b1.button("✅ Als umgesetzt übernehmen", key="wiki_uebernehmen", type="primary", width="stretch",
                 disabled=not h.get("schreiben_ok", True),
                 help="Setzt das Modelldepot auf diesen Stand – die nächste Liste rechnet davon aus."):
        konflikt = []

        neu_ist = WI.ausfuehren(v.get("alt") or {}, neu, st.session_state.get("_wiki_ist") or {})
        neu_ist["charts"] = WI.charts_fortschreiben((v.get("alt") or {}).get("charts"), neu_ist)

        def aendern(gespeichert):
            neu_ = WI.uebernehmen(gespeichert or {}, neu_ist, v["basis"])
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
    "live_kurs": instrument_id -> kurs}"""
    schritte.leiste(st, "wiki")
    depot = h["lesen"](PFAD_DEPOT, {}) or {}
    rang = h["lesen"](PFAD_RANG, {}) or {}
    heute = _jetzt().date()
    if st.session_state.get("_wiki_meldung"):
        st.success(st.session_state.pop("_wiki_meldung"))

    # 1 - Liste erstellen
    schritte.titel(st, "wiki", 1)
    st.caption("Nimmt die Aktien aus dem ⭐ Qualitäts-Score und die ETFs aus dem 🏅 ETF-Score von „Ranglisten & "
               "Screener“, ergänzt um Investoren-Checks und fairen Wert, holt die aktuellen Kurse und berechnet die Käufe und Verkäufe für das Modelldepot"
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
            art = st.segmented_control("Darstellung", ["🎵 Charts", "🗺️ Kacheln", "📊 Balken"], default="🎵 Charts",
                                       key=f"wiki_pos_ansicht_{key}") or "🎵 Charts"
            if art == "🎵 Charts":
                vorher = depot.get("vorher") or {}
                zeilen_hp, raus_hp = WI.hitparade(depot, vorher, "aktie" if key == "a" else "etf",
                                                  vorher.get("charts") or {})
                st.caption("Platzierung nach Score, Bewegung gegenüber dem Stand vor der letzten Übernahme.")
                st.markdown(_hitparade_html(zeilen_hp, raus_hp, f"{titel}-Charts"), unsafe_allow_html=True)
            elif art == "🗺️ Kacheln":
                st.caption("Fläche = Wert der Position, gruppiert nach Branche bzw. Region/Thema; Farbe = "
                           "Entwicklung seit Kauf (grün plus, rot minus).")
                st.plotly_chart(_kacheln(df), width="stretch", key=f"wiki_kacheln_{key}",
                                config={"displayModeBar": False})
            else:
                st.plotly_chart(_balken(df, f"{titel} nach Wert"), width="stretch", key=f"wiki_balken_{key}",
                                config={"displayModeBar": False})
            st.download_button(f"⬇️ {titel} als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                               file_name=f"KI_Invest_System_{key}_{depot.get('stand')}.csv", mime="text/csv",
                               key=f"wiki_csv_{key}")

    _korrektur(h, depot, preise)

    # 4 - Verlauf der Umschichtungen
    schritte.titel(st, "wiki", 4)
    if laeufe:
        namen = [f"{_datum_de(l['datum'])} {str(l.get('zeit') or '')[11:16]} · "
                 f"{'Korrektur' if l.get('korrektur') else 'Umschichtung'} · {len(l['auftraege'])} Änderung"
                 f"{'en' if len(l['auftraege']) != 1 else ''}"
                 .replace("  ", " ") for l in reversed(laeufe)]
        wahl = st.selectbox("Umschichtung", namen, key="wiki_lauf")
        lauf = list(reversed(laeufe))[namen.index(wahl)]
        if lauf["auftraege"]:
            zeilen, _ = WI.betraege(lauf["auftraege"])
            df = pd.DataFrame([{"Aktion": z["aktion"], "Stück": z["stueck"], "Name": z["name"],
                                "WKN/ISIN": z["wkn"] or z["isin"],
                                "Art": {"aktie": "Aktie", "etf": "ETF"}.get(z["art"], "Kasse"),
                                "Kurs €": z["kurs"], "Betrag €": z["betrag"], "vorher": z.get("vorher"),
                                "nachher": z.get("nachher"),
                                "geplant": z.get("geplant", z["stueck"]) if not lauf.get("korrektur") else None}
                               for z in zeilen])
            st.dataframe(df, hide_index=True, width="stretch", key="wiki_auftraege",
                         column_config={"Kurs €": st.column_config.NumberColumn(format="%.2f"),
                                        "Betrag €": st.column_config.NumberColumn(format="%+.2f")},
                         height=min(38 + 35 * len(df), 420))
        else:
            st.caption("Keine Anpassungen.")
    if "vorher" in depot:
        with st.expander("↩️ Letzte Übernahme bzw. Korrektur rückgängig machen"):
            st.caption("Setzt das Modelldepot auf den Stand vor der letzten Übernahme oder Korrektur zurück "
                       "(nur einen Schritt).")
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


def _korrektur(h, depot, preise):
    """Bestand an die echte Umsetzung im wikifolio anpassen (Stueck, Kaufkurs, Positionen, Kasse)."""
    with st.expander("✏️ Bestand an meine echte Umsetzung anpassen"):
        st.caption("Stückzahl und Kaufkurs je Position ändern, Zeilen löschen (Zeile markieren → Papierkorb) oder "
                   "unten neue Positionen anfügen (Name, WKN/ISIN, Art, Stück, Kurs). Stück 0 entfernt eine "
                   "Position. Die Kasse ist dein tatsächlicher Kontostand im wikifolio.")
        pos = sorted(depot["positionen"].values(), key=lambda p: (p["art"], p.get("rang") or 999))
        df = pd.DataFrame([{"_id": p["id"], "Name": p["name"], "WKN/ISIN": p.get("wkn") or p.get("isin") or "",
                            "Art": "Aktie" if p["art"] == "aktie" else "ETF", "Stück": int(p["stueck"]),
                            "Kaufkurs €": float(p["kurs"])} for p in pos])
        with st.form("wiki_korrektur_form", border=False):
            ed = st.data_editor(df, hide_index=True, width="stretch", num_rows="dynamic", key="wiki_korrektur_tab",
                                column_order=["Name", "WKN/ISIN", "Art", "Stück", "Kaufkurs €"],
                                height=min(38 + 35 * (len(df) + 2), 560),
                                column_config={"Art": st.column_config.SelectboxColumn(options=["Aktie", "ETF"],
                                                                                        required=True),
                                               "Stück": st.column_config.NumberColumn(min_value=0, step=1,
                                                                                      format="%d"),
                                               "Kaufkurs €": st.column_config.NumberColumn(min_value=0.0, step=0.01,
                                                                                           format="%.2f")})
            kasse = st.number_input("Kasse €", min_value=0.0, value=float(depot.get("kasse") or 0), step=10.0,
                                    key="wiki_korrektur_kasse")
            gespeichert = st.form_submit_button("💾 Korrektur speichern", disabled=not h.get("schreiben_ok", True))
        if gespeichert:
            zeilen = []
            for _, r in ed.iterrows():
                kenn = str(r.get("WKN/ISIN") or "").strip()
                i = r.get("_id")
                zeilen.append({"id": i if isinstance(i, str) and i in depot["positionen"] else None,
                               "name": r.get("Name"), "wkn": kenn if len(kenn) <= 6 else "",
                               "isin": kenn if len(kenn) > 6 else "",
                               "art": "etf" if r.get("Art") == "ETF" else "aktie",
                               "stueck": 0 if pd.isna(r.get("Stück")) else r.get("Stück"),
                               "kurs": None if pd.isna(r.get("Kaufkurs €")) else r.get("Kaufkurs €")})
            jetzt = _jetzt()
            neu, aend = WI.korrigieren(depot, zeilen, kasse, jetzt.date().isoformat(),
                                       jetzt.strftime("%Y-%m-%dT%H:%M"))
            if not aend:
                st.info("Keine Änderungen.")
                return
            basis = WI.signatur(depot)
            konflikt = []

            def aendern(gespeichert):
                n = WI.uebernehmen(gespeichert or {}, neu, basis)
                if n is None:
                    konflikt.append(True)
                return n
            ok, _ = h["schreiben"](PFAD_DEPOT, aendern, {}, "wiki-idee: korrektur [skip ci]")
            if konflikt:
                st.error("Das Modelldepot wurde inzwischen geändert – bitte Seite neu laden.")
            elif ok:
                st.session_state["_wiki_meldung"] = (f"✏️ Korrektur gespeichert ({len(aend)} Änderung"
                                                     + ("en)." if len(aend) != 1 else ")."))
                st.rerun()
            else:
                st.error("Speichern fehlgeschlagen – bitte erneut versuchen.")


def _methodik():
    with st.expander("ℹ️ So funktioniert das KI_Invest_System"):
        st.markdown(
            "- **Start:** 100.000 € – 70 % auf **50 Aktien**, 30 % auf **20 ETFs**, je Klasse gleich gewichtet "
            "(je Aktie ca. 1.400 €, je ETF 1.500 €), ganze Stück; die Restkasse wird auf die Positionen verteilt.\n"
            "- **Aktien** aus „🏆 Ranglisten & Screener“: "
            + ", ".join(f"{g} % {t}" for _, t, g in WI.BAUSTEINE) + ". "
            "*Qualitäts-Score* = die Punkte der Rangliste „⭐ Qualitäts-Score“ (nur Aktien mit ISIN, die bei Lang & "
            "Schwarz – dem Handelspartner von wikifolio – handelbar sind); *Investoren-Checks* = Urteil der Börsenlegenden (Buffett, Graham, Lynch, Greenblatt, "
            "Piotroski, Fisher …); *Unterbewertung* = Abstand fairer Wert zum Kurs; *Qualität × Kurs* = gute Firma, "
            "zuletzt schwacher Kurs. Fehlt ein Baustein, zählt er neutral (50).\n"
            "- **Ausschluss:** Altman-Gefahrenzone, Beneish-Verdacht auf Bilanzmanipulation oder überwiegend "
            "Bilanz-Warnsignale.\n"
            f"- **ETFs** aus „🏆 Ranglisten & Screener“: der „🏅 ETF-Score“ (Rendite, Rendite je Risiko, Rückgang, "
            "Schwankung, Historie, Beständigkeit), ohne Hebel-/Short-Produkte, "
            f"mindestens {WI.MIN_ETF_JAHRE:.0f} Jahre Historie.\n"
            f"- **Streuung:** höchstens {WI.MAX_JE_SEKTOR} Aktien je Branche, höchstens {WI.MAX_JE_ETF_GRUPPE} ETFs "
            "je Region + Thema (sonst würden z. B. zehn fast gleiche S&P-500-ETFs gewählt).\n"
            f"- **Nach Bedarf:** „Liste jetzt erstellen“ bewertet neu und holt aktuelle Kurse (ls-tc.de). Ein Wert "
            f"bleibt, solange er in den Top {WI.PUFFER_AKTIEN} (Aktien) bzw. Top {WI.PUFFER_ETF} (ETFs) steht – kein "
            "Tausch wegen kleiner Score-Schwankungen; freie Plätze bekommen die Besten. Alle Positionen werden "
            "auf das Zielgewicht zurückgesetzt (im wikifolio ohne Kosten).\n"
            "- **Übernehmen:** Erst wenn du die Liste im wikifolio umgesetzt hast und „Als umgesetzt übernehmen“ "
            "klickst, ändert sich das Modelldepot – die nächste Liste rechnet davon aus. Weicht deine Umsetzung ab "
            "(Teilausführung, anderer Kurs, Order nicht ausgeführt), trägst du vor dem Übernehmen die echten Stück "
            "und Kurse ein; später geht das jederzeit unter „Bestand an meine echte Umsetzung anpassen“ (auch Kasse, "
            "neue oder gelöschte Positionen). Rückgängig ist möglich.\n"
            "- **Kein Trading-Roboter:** Es werden keine Orders ausgeführt. Grundlage sind vergangene Daten; keine "
            "Anlageberatung.")
