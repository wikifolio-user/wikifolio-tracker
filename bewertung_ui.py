"""Bewertung - eigene Ansicht (Oberflaeche zu scoring.py).

Man sucht einen Wert (Aktie, ETF oder wikifolio) aus der Top-500-Liste und bekommt eine Bewertung anhand aller
Kennzahlen, die die App zu diesem Wert hat: Gesamtscore mit Ampel, Teilscores, Radar, jede Kennzahl mit
Einordnung, Median-Vergleich und Perzentil-Rang, Staerken und Schwaechen. Datenbasis sind ausschliesslich die
oeffentlichen Agenten-Dateien (Branch app-state, taeglich) - nichts wird geschrieben."""
import datetime
import html

import plotly.graph_objects as go
import streamlit as st

import portfolio_builder_ui as B
import schritte
import scoring as SC
import ui_stil as UI

P = "bw_"
ART_TEXT = {"aktie": "Aktie", "etf": "ETF", "wikifolio": "wikifolio"}
AMPEL_TEXT = {"gruen": "stark", "gelb": "mittel", "rot": "schwach", "grau": "n/a"}
EINORDNUNG_CSS = {"gut": "pos", "neutral": "mit", "schlecht": "neg", "n/a": "na"}

CSS = """
<style>
.bw-kopf { border:1px solid var(--glas-rand, rgba(255,255,255,.12)); border-radius:18px; padding:14px 16px;
  background:var(--surface-2,#191A1B); margin:4px 0 12px; }
.bw-name { font-size:1.3rem; font-weight:800; line-height:1.25; overflow-wrap:anywhere; }
.bw-tags { margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; }
.bw-tag { display:inline-block; padding:2px 9px; border-radius:10px; font-size:.75rem; font-weight:600;
  border:1px solid var(--glas-rand, rgba(255,255,255,.14)); color:var(--label,#B1B3B7); overflow-wrap:anywhere; }
.bw-kurs { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-top:10px; }
.bw-kurs .w { font-size:1.6rem; font-weight:800; font-variant-numeric:tabular-nums; }
.bw-kurs .d { font-weight:700; font-variant-numeric:tabular-nums; }
.bw-pos { color:var(--pos,#34D399); } .bw-neg { color:var(--neg,#F87171); } .bw-m { color:var(--label,#A9ACB0); }
.bw-gesamt { display:grid; grid-template-columns:auto 1fr; gap:16px; align-items:center;
  border:1px solid var(--glas-rand, rgba(255,255,255,.12)); border-radius:18px; padding:14px 16px;
  background:var(--surface-2,#191A1B); margin:4px 0 12px; }
.bw-ring { width:96px; height:96px; border-radius:50%; display:grid; place-items:center; position:relative;
  background:conic-gradient(var(--bw-farbe) calc(var(--bw-wert) * 1%), rgba(127,127,127,.18) 0); }
.bw-ring::before { content:""; position:absolute; inset:9px; border-radius:50%; background:var(--surface-2,#191A1B); }
.bw-ring b { position:relative; color:var(--text,#E8ECF6); font-size:1.7rem; font-weight:800; font-variant-numeric:tabular-nums; }
.bw-ring small { position:absolute; bottom:16px; font-size:.65rem; color:var(--label,#A9ACB0); }
.bw-urteil { font-size:1.05rem; font-weight:800; }
.bw-satz { color:var(--label,#B1B3B7); font-size:.88rem; margin-top:4px; }
.bw-ampel { display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:12px; font-weight:700;
  font-size:.8rem; margin:0 6px 4px 0; border:1px solid currentColor; }
.bw-ampel::before { content:""; width:9px; height:9px; border-radius:50%; background:currentColor; }
.bw-a-gruen { color:var(--pos,#34D399); } .bw-a-gelb { color:#E5A50A; } .bw-a-rot { color:var(--neg,#F87171); }
.bw-a-grau { color:var(--label,#A9ACB0); }
.bw-teile { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin:6px 0 12px; }
.bw-teil { border:1px solid var(--glas-rand, rgba(255,255,255,.12)); border-radius:14px; padding:10px 12px;
  background:var(--surface-2,#191A1B); min-width:0; }
.bw-teil .t { font-size:.75rem; text-transform:uppercase; letter-spacing:.5px; color:var(--label,#A9ACB0);
  overflow-wrap:anywhere; }
.bw-teil .w { font-size:1.25rem; font-weight:800; margin-top:2px; font-variant-numeric:tabular-nums; }
.bw-teil .s { font-size:.75rem; color:var(--label,#A9ACB0); }
.bw-bahn { height:6px; border-radius:3px; background:rgba(127,127,127,.2); overflow:hidden; margin-top:6px; }
.bw-bahn > div { height:100%; border-radius:3px; }
.bw-g-gruen { background:var(--pos,#34D399); } .bw-g-gelb { background:#E5A50A; } .bw-g-rot { background:var(--neg,#F87171); }
.bw-sw { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:10px 24px; margin:4px 0 12px; }
.bw-liste { margin:4px 0 0; padding-left:1.1rem; } .bw-liste li { margin:3px 0; }
.bw-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; margin:4px 0 14px; }
table.bw { display:table !important; width:100%; min-width:560px; border-collapse:separate; border-spacing:0;
  font-size:.86rem; }
table.bw th { text-align:left; color:var(--label,#A9ACB0); font-size:.72rem; letter-spacing:.4px;
  text-transform:uppercase; padding:6px 8px; border-bottom:1px solid var(--line,#353739); white-space:nowrap; }
table.bw td { padding:7px 8px; border-bottom:1px solid var(--line,#26282A); vertical-align:middle; }
table.bw .r { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
table.bw tr.kat td { font-weight:800; padding-top:12px; border-bottom-color:transparent; }
.bw-e { display:inline-block; min-width:64px; text-align:center; padding:1px 8px; border-radius:8px; font-weight:700;
  font-size:.78rem; border:1px solid currentColor; }
.bw-e.pos { color:var(--pos,#34D399); } .bw-e.neg { color:var(--neg,#F87171); } .bw-e.mit { color:#E5A50A; }
.bw-e.na { color:var(--label,#A9ACB0); }
.bw-pz { display:flex; align-items:center; gap:8px; min-width:150px; }
.bw-pz .bw-bahn { flex:1; margin:0; min-width:60px; }
.bw-pz span { white-space:nowrap; font-size:.8rem; }
@media (max-width: 760px) {
  .bw-teile { grid-template-columns:repeat(2, minmax(0,1fr)); }
  .bw-gesamt { grid-template-columns:1fr; justify-items:start; }
  .bw-sw { grid-template-columns:1fr; }
}
@media (max-width: 420px) { .bw-teile { grid-template-columns:1fr; } }
</style>
"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _zahl_de(x, stellen=1):
    return f"{x:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def wert_text(z, info=None):
    """Kennzahl formatiert (deutsch) - fehlend = n/a."""
    w, fmt = z["wert"], z["format"]
    if w is None:
        return "n/a"
    if z["key"] == "nde" and (info or {}).get("netcash"):
        return "Nettocash"
    if z["key"] in ("ev_ebit", "ev_ebitda") and w <= 0:
        return f"{_zahl_de(w)}x (nicht aussagekräftig)"
    if fmt == "x" or fmt == "nde":
        return f"{_zahl_de(w)}x"
    if fmt == "pct0":
        return f"{_zahl_de(w, 0)} %"
    if fmt == "jahre":
        return f"{_zahl_de(w)} J."
    return f"{'+' if z['key'] in ('p6', 'p12', 'p36', 'm1', 'g_ums', 'g_eps', 'g_fcf', 'g_fcfps') and w > 0 else ''}" \
           f"{_zahl_de(w)} %"


def median_text(z):
    m = z["median"]
    if m is None:
        return "n/a"
    return wert_text(dict(z, wert=m, key="median"))


# ---------------------------------------------------------------- Daten (einmal je Tag, fuer alle Nutzer gleich)
@st.cache_resource(ttl=900, show_spinner=False)
def _daten(_lesen, tag):
    """Universum + Vergleichsverteilungen aus den oeffentlichen Agenten-Dateien. tag nur als Cache-Schluessel;
    cache_resource statt cache_data: die ~26.000 Eintraege werden nicht bei jedem Neuaufbau kopiert."""
    def teile(muster, n):
        return [d for d in (_lesen(muster.format(i), None) for i in range(n)) if isinstance(d, dict)]
    kat = teile("state/planer/katalog_gross_{}.json", 4)
    qual = teile("state/qualitaet/alle_{}.json", 6)
    perf = teile("state/top50_alle_{}.json", 4)
    det = teile("state/qualitaet/details_{}.json", 6)
    yahoo = _lesen("state/top50_yahoo.json", None) or {}
    u = SC.universum(kat, qual, perf, det, yahoo.get("isin") or {})
    stand = max((str(d.get("stand") or "") for d in kat + qual), default="")
    return {"u": u, "ver": SC.verteilungen(u), "je_id": {e["id"]: e for e in u}, "stand": stand,
            "anzahl": {a: sum(1 for e in u if e["art"] == a) for a in SC.KLASSE_KUERZEL}}


def _stand_text(stand):
    try:
        return datetime.datetime.fromisoformat(str(stand)[:19]).strftime("%d.%m.%Y")
    except ValueError:
        return str(stand)[:10] or "unbekannt"


# ---------------------------------------------------------------- Bausteine
def _kopf(e):
    tags = [ART_TEXT[e["art"]]]
    if e["ticker"]:
        tags.append(f"Ticker {e['ticker']}")
    if e["wkn"]:
        tags.append(f"WKN {e['wkn']}")
    if e["isin"]:
        tags.append(f"ISIN {e['isin']}")
    tags.append(f"Sektor: {e['sektor']}" if e["sektor"] else "Sektor: n/a")
    kurs = (f"{_zahl_de(e['kurs'], 2)} {_e(e['waehrung'] or '')}".strip() if e["kurs"] else "Kurs n/a")
    if e["tag"] is None:
        tag = '<span class="d bw-m">Tagesveränderung n/a</span>'
    else:
        css = "bw-pos" if e["tag"] > 0 else "bw-neg" if e["tag"] < 0 else "bw-m"
        tag = f'<span class="d {css}">{"+" if e["tag"] > 0 else ""}{_zahl_de(e["tag"], 2)} % heute</span>'
    st.markdown(f'<div class="bw-kopf"><div class="bw-name">{_e(e["name"])}</div><div class="bw-tags">'
                + "".join(f'<span class="bw-tag">{_e(t)}</span>' for t in tags)
                + f'</div><div class="bw-kurs"><span class="w">{kurs}</span>{tag}</div></div>',
                unsafe_allow_html=True)


FARBE = {"gruen": "var(--pos,#34D399)", "gelb": "#E5A50A", "rot": "var(--neg,#F87171)",
         "grau": "var(--label,#A9ACB0)"}


def _gesamt(e, b):
    g = b["gesamt"]
    wert = "n/a" if g is None else f"{g:.0f}"
    urteil = []
    urteil.append(f'<span class="bw-ampel bw-a-{b["ampel"]}">Ampel: {AMPEL_TEXT[b["ampel"]]}</span>')
    if b["fazit"]:
        css = {"unterbewertet": "gruen", "fair bewertet": "gelb", "teuer": "rot"}[b["fazit"]]
        urteil.append(f'<span class="bw-ampel bw-a-{css}">{_e(b["fazit"])}</span>')
    n, von = b["abdeckung"]
    st.markdown(
        f'<div class="bw-gesamt"><div class="bw-ring" style="--bw-farbe:{FARBE[b["ampel"]]};'
        f'--bw-wert:{0 if g is None else g:.0f}" role="img" aria-label="Gesamtscore {wert} von 100">'
        f'<b>{wert}</b><small>von 100</small></div><div><div class="bw-urteil">Gesamtscore</div>'
        f'<div>{"".join(urteil)}</div><div class="bw-satz">{_e(SC.kurzfazit(e, b))}</div>'
        f'<div class="bw-satz">{n} von {von} Kennzahlen vorhanden – fehlende zählen nicht mit.</div></div></div>',
        unsafe_allow_html=True)


def _teilscores(b):
    kacheln = []
    for c in b["kategorien"]:
        s = c["score"]
        if s is None:
            kacheln.append(f'<div class="bw-teil"><div class="t">{_e(c["titel"])}</div><div class="w bw-m">n/a</div>'
                           f'<div class="s">keine Kennzahl vorhanden · Gewicht {c["gewicht"]} %</div></div>')
            continue
        a = SC.ampel(s)
        kacheln.append(f'<div class="bw-teil"><div class="t">{_e(c["titel"])}</div><div class="w">{s:.0f}'
                       f'<span class="bw-m" style="font-size:.8rem;font-weight:600"> / 100</span></div>'
                       f'<div class="s">{c["anzahl"]} von {c["von"]} Kennzahlen · Gewicht {c["gewicht"]} %</div>'
                       f'<div class="bw-bahn"><div class="bw-g-{a}" style="width:{s:.0f}%"></div></div></div>')
    st.markdown('<div class="bw-teile">' + "".join(kacheln) + "</div>", unsafe_allow_html=True)


KURZ = {"bewertung": "Bewertung", "qualitaet": "Qualität", "wachstum": "Wachstum", "stabilitaet": "Stabilität",
        "dividende": "Dividende", "momentum": "Momentum", "rendite": "Rendite", "risiko": "Risiko"}


def _radar(b):
    mit = [c for c in b["kategorien"] if c["score"] is not None]
    if len(mit) < 3:
        st.caption("Für das Netzdiagramm braucht es mindestens drei Teilscores.")
        return
    namen = [KURZ.get(c["key"], c["titel"]) for c in mit]
    werte = [round(c["score"]) for c in mit]
    fig = go.Figure(go.Scatterpolar(r=werte + werte[:1], theta=namen + namen[:1], fill="toself",
                                    line=dict(color=UI.AKZENT, width=2), fillcolor="rgba(124,156,255,0.25)",
                                    hovertemplate="%{theta}: %{r} / 100<extra></extra>", name="Teilscore"))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)",
                                 radialaxis=dict(range=[0, 100], tickvals=[25, 50, 75], gridcolor=UI.CHART_RASTER,
                                                 linecolor=UI.CHART_RASTER, tickfont=dict(size=10)),
                                 angularaxis=dict(gridcolor=UI.CHART_RASTER, linecolor=UI.CHART_RASTER)),
                      showlegend=False, height=360, margin=dict(l=60, r=60, t=30, b=30))
    UI.chart_stil(fig, schrumpfen=False)
    if UI.ist_smartphone():
        fig.update_layout(height=300, margin=dict(l=70, r=70, t=28, b=28), font=dict(size=11))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False},
                    key=P + "radar")


def _staerken_schwaechen(e, b):
    """Zwei Listen nebeneinander, auf schmalen Bildschirmen untereinander (CSS-Raster statt st.columns)."""
    bloecke = []
    for titel, liste, leer in (("Stärken", b["staerken"], "Keine Kennzahl im oberen Viertel."),
                               ("Schwächen", b["schwaechen"], "Keine Kennzahl im unteren Viertel.")):
        inhalt = ('<ul class="bw-liste">' + "".join(
            f'<li><b>{_e(z["titel"])}</b>: {_e(wert_text(z, e["info"]))} – besser als '
            f'{z["perzentil"]:.0f} % ({_vergleich_text(e, z)})</li>' for z in liste) + "</ul>") if liste \
            else f'<div class="bw-m">{leer}</div>'
        bloecke.append(f'<div><div class="bw-urteil">{titel}</div>{inhalt}</div>')
    st.markdown('<div class="bw-sw">' + "".join(bloecke) + "</div>", unsafe_allow_html=True)


def _vergleich_text(e, z):
    if z["basis"] == "sektor":
        return "im Sektor"
    return f"aller {SC.KLASSEN_TEXT[e['art']]}"


def _kennzahlen(e, b):
    zeilen = []
    for c in b["kategorien"]:
        score = "Teilscore n/a" if c["score"] is None else f"Teilscore {c['score']:.0f}"
        zeilen.append(f'<tr class="kat"><td colspan="5">{_e(c["titel"])} '
                      f'<span class="bw-m" style="font-weight:600">· {score}</span></td></tr>')
        for z in (z for z in b["kennzahlen"] if z["kategorie"] == c["key"]):
            pz = z["perzentil"]
            if pz is None:
                pz_html = '<span class="bw-m">n/a</span>'
            else:
                pz_html = (f'<div class="bw-pz"><div class="bw-bahn"><div class="bw-g-{SC.ampel(pz)}" '
                           f'style="width:{pz:.0f}%"></div></div><span>besser als {pz:.0f} %</span></div>')
            basis = "Sektor-Median" if z["basis"] == "sektor" else "Median Top 500"
            richtung = "↑ höher besser" if z["richtung"] > 0 else "↓ niedriger besser"
            zeilen.append(
                f'<tr><td>{_e(z["titel"])}<div class="bw-m" style="font-size:.72rem">{richtung}</div></td>'
                f'<td class="r">{_e(wert_text(z, e["info"]))}</td>'
                f'<td><span class="bw-e {EINORDNUNG_CSS[z["einordnung"]]}">{_e(z["einordnung"])}</span></td>'
                f'<td class="r">{_e(median_text(z))}<div class="bw-m" style="font-size:.72rem">{basis}</div></td>'
                f'<td>{pz_html}</td></tr>')
    st.markdown('<div class="bw-wrap"><table class="bw"><thead><tr><th>Kennzahl</th><th class="r">Wert</th>'
                '<th>Einordnung</th><th class="r">Vergleich</th><th>Perzentil-Rang</th></tr></thead><tbody>'
                + "".join(zeilen) + "</tbody></table></div>", unsafe_allow_html=True)


def _app_einschaetzung(e):
    """Vorhandene Einschaetzung des Qualitaets-Agenten (zusaetzlich, fliesst nicht in den Score ein)."""
    i = e["info"]
    teile = []
    if i.get("gesamt") is not None:
        teile.append(f"Qualitäts-Score {i['gesamt']}/100")
    for key, titel in (("klasse", "Klasse"), ("moat", "Burggraben"), ("mgmt", "Management"), ("bew", "Bewertung"),
                       ("risiko", "Risiko")):
        if i.get(key):
            teile.append(f"{titel}: {i[key]}")
    if i.get("mcap"):
        teile.append(f"Börsenwert {_zahl_de(float(i['mcap']), 0)} Mrd.")
    if teile:
        st.caption("Einschätzung des Qualitäts-Agenten (zur Info, nicht im Score): " + " · ".join(teile))


def _methodik(e):
    g = SC.GEWICHTE[e["art"]]
    with st.expander("So wird gerechnet"):
        st.markdown(
            f"- **Perzentil-Rang:** Jede Kennzahl wird mit allen {SC.KLASSEN_TEXT[e['art']]} der Top-500-Liste "
            "verglichen – „besser als 82 %“ heißt: 82 % der Vergleichswerte schneiden bei dieser Kennzahl "
            "schlechter ab. Die Richtung ist je Kennzahl hinterlegt (z. B. niedriges KGV = gut).\n"
            f"- **Sektorrelativ:** Bewertungskennzahlen (KGV, EV/EBIT, FCF-Rendite …) werden nur mit Aktien "
            f"derselben Branche verglichen, sofern es dort mindestens {SC.MIN_SEKTOR} Werte gibt – sonst mit allen.\n"
            f"- **Einordnung:** gut ab {SC.GUT:.0f} %, schlecht bis {SC.SCHLECHT:.0f} %, dazwischen neutral.\n"
            "- **Teilscore:** gewichteter Mittelwert der vorhandenen Kennzahlen eines Bereichs. "
            "**Gesamtscore:** gewichteter Mittelwert der Teilscores ("
            + ", ".join(f"{SC.KATEGORIEN[k]} {v} %" for k, v in g.items()) + ").\n"
            "- **Fehlende Werte** stehen als „n/a“ da und fallen aus der Gewichtung heraus – sie zählen nie als 0. "
            f"Unter {SC.MIN_KATEGORIEN[e['art']]} Teilbereichen gibt es keinen Gesamtscore.\n"
            f"- **Ampel:** grün ab {SC.AMPEL_GRUEN:.0f}, gelb ab {SC.AMPEL_GELB:.0f}, sonst rot. "
            + (f"**Fazit** aus dem Bewertungs-Teilscore: unterbewertet ab {SC.FAZIT_GUENSTIG:.0f}, "
               f"teuer bis {SC.FAZIT_TEUER:.0f}." if e["art"] == "aktie" else
               "Ein Bewertungs-Fazit (unterbewertet/teuer) gibt es nur für Aktien.")
            + "\n- Negative KGV (Verlust) zählen als teuerster Wert, negative EV-Multiplikatoren sind nicht "
            "aussagekräftig (n/a).")


# ---------------------------------------------------------------- Seite
def seite(h):
    with st.container(key="bw_seite"):
        _seite(h)


def _seite(h):
    st.markdown(B.CSS, unsafe_allow_html=True)
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="pb-kopf"><div class="pb-titel">Bewertung <span>Top 500</span></div>'
                '<div class="pb-unter">Aktien · ETFs · wikifolios – alle vorhandenen Kennzahlen im Vergleich</div>'
                '</div>', unsafe_allow_html=True)
    schritte.leiste(st, "bewertung", spaeter=() if st.session_state.get(P + "wahl") else (2, 3, 4))
    schritte.titel(st, "bewertung", 1)
    with st.spinner("Lade Top-500-Daten …"):
        d = _daten(h["gh_read_taeglich"], datetime.date.today().isoformat())
    if not d["u"]:
        st.warning("Die Top-500-Daten sind gerade nicht lesbar – bitte später erneut versuchen.")
        return
    text = st.text_input("Name, Ticker, WKN oder ISIN", key=P + "suche", placeholder="z. B. Apple, SAP, A0RPWH …")
    treffer = SC.suchen(d["u"], text, limit=20) if text else []
    if text and not treffer:
        st.info("Kein Treffer in der Top-500-Liste. Tipp: Teil des Namens, Ticker, WKN oder ISIN eingeben.")
    if treffer:
        ids = [e["id"] for e in treffer]
        if st.session_state.get(P + "wahl") not in ids:
            st.session_state[P + "wahl"] = ids[0]
        st.selectbox(f"{len(treffer)} Treffer – Wert wählen", ids, key=P + "wahl",
                     format_func=lambda i: _auswahl_text(d["je_id"][i]))
    wahl = st.session_state.get(P + "wahl")
    e = d["je_id"].get(wahl) if wahl and treffer else None
    a = d["anzahl"]
    st.caption(f"Datenstand {_stand_text(d['stand'])} · {a['aktie']:,} Aktien, {a['etf']:,} ETFs, "
               f"{a['wikifolio']:,} wikifolios".replace(",", "."))
    if not e:
        if not text:
            st.info("Gib oben einen Namen, Ticker, eine WKN oder ISIN ein – die Bewertung erscheint sofort.")
        return
    b = SC.bewerten(e, d["ver"])
    schritte.titel(st, "bewertung", 2)
    _kopf(e)
    _gesamt(e, b)
    schritte.titel(st, "bewertung", 3)
    _teilscores(b)
    _radar(b)
    _staerken_schwaechen(e, b)
    schritte.titel(st, "bewertung", 4)
    _kennzahlen(e, b)
    if e["art"] == "aktie":
        _app_einschaetzung(e)
    _methodik(e)
    st.caption("Keine Anlageberatung. Der Score ist eine regelbasierte Auswertung der vorhandenen Kennzahlen im "
               "Vergleich zur Top-500-Liste; die Daten können verzögert oder unvollständig sein.")


def _auswahl_text(e):
    kennung = e["ticker"] or e["wkn"] or e["isin"]
    return f"{e['name']} · {ART_TEXT[e['art']]}" + (f" · {kennung}" if kennung else "")
