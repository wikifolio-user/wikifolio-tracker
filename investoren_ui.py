"""Investoren-Checks - Bereich der Bewertungsseite (Oberflaeche zu investor_checks/).

Daten: yfinance (Yahoo Finance, kostenlos) fuer die gewaehlte Aktie - Fundamentaldaten 24 h, Kurse 15 Min.
zwischengespeichert; Vergleichswerte (Raenge, Verteilungen) aus den Top-500-Daten der Bewertung.
Geladen wird erst, wenn eine Aktie gewaehlt ist - nie beim Login. Geschrieben wird nur die eigene Checkliste
(je Benutzer im vorhandenen Speicher der App).
"""
import datetime
import html
import logging
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

import investor_checks as IC
import investor_config as C
import ui_stil as UI
from investor_checks import buffett as BUF
from investor_checks import daten as DT
from investor_checks import greenblatt as GB
from investor_checks import konsens as KO

P = "ic_"
SYMBOL = {"pass": "✅", "fail": "❌", "na": "⚪"}
CHECKLISTE = [
    ("kompetenz", "Verstehe ich das Geschäftsmodell?", "Circle of Competence (Buffett): nur investieren, was man "
     "versteht."),
    ("burggraben", "Hat das Unternehmen einen echten Burggraben?", "Marke, Netzwerkeffekt, Wechselkosten, "
     "Kostenvorteil oder Lizenzen schützen die Gewinne."),
    ("management", "Ist das Management ehrlich und aktionärsfreundlich?", "Offene Kommunikation, faire Vergütung, "
     "eigene Beteiligung."),
    ("kapital", "Gute Kapitalallokation?", "Sinnvolle Übernahmen, Rückkäufe zu vernünftigen Preisen."),
    ("lindy", "Existiert das Geschäft in 10–20 Jahren noch?", "Lindy-Test: Was lange besteht, besteht eher weiter."),
    ("scuttlebutt", "Was sagen Kunden und Mitarbeiter?", "Philip Fishers „Scuttlebutt“: Bewertungen, Erfahrungen, "
     "Gespräche."),
    ("story", "Kann ich die Investmentstory in 2 Minuten erklären?", "Peter Lynch: Wer es nicht einfach erklären "
     "kann, versteht es nicht."),
]
NOTIZ_PFAD = "state/bewertung_notizen.json"

CSS = """
<style>
.ic-kopf { display:grid; grid-template-columns:auto 1fr; gap:16px; align-items:center;
  border:1px solid var(--glas-rand, rgba(255,255,255,.12)); border-radius:18px; padding:14px 16px;
  background:var(--surface-2,#191A1B); margin:4px 0 12px; }
.ic-note { width:84px; height:84px; border-radius:22px; display:grid; place-items:center; font-size:2.6rem;
  font-weight:800; color:var(--text,#E8ECF6); border:2px solid currentColor; }
.ic-note.A, .ic-note.B { color:var(--pos,#34D399); } .ic-note.C { color:#E5A50A; }
.ic-note.D, .ic-note.E, .ic-note.F { color:var(--neg,#F87171); } .ic-note.x { color:var(--label,#A9ACB0); }
.ic-gross { font-size:1.15rem; font-weight:800; }
.ic-m { color:var(--label,#A9ACB0); font-size:.85rem; }
.ic-warn { border:1px solid var(--neg,#F87171); border-left:4px solid var(--neg,#F87171); border-radius:12px;
  padding:10px 14px; margin:6px 0 12px; background:rgba(248,113,113,.08); }
.ic-warn b { color:var(--neg,#F87171); }
.ic-warn ul { margin:4px 0 0; padding-left:1.1rem; }
.ic-badge { display:inline-block; padding:2px 10px; border-radius:10px; font-size:.75rem; font-weight:700;
  border:1px solid var(--pos,#34D399); color:var(--pos,#34D399); margin:0 6px 4px 0; }
.ic-karte { border:1px solid var(--glas-rand, rgba(255,255,255,.12)); border-radius:14px; padding:10px 12px;
  background:var(--surface-2,#191A1B); margin-bottom:4px; }
.ic-karte .n { font-weight:800; } .ic-karte .s { color:var(--label,#A9ACB0); font-size:.8rem; margin:2px 0 6px; }
.ic-bahn { height:7px; border-radius:4px; background:rgba(127,127,127,.2); overflow:hidden; }
.ic-bahn > div { height:100%; border-radius:4px; }
.ic-g { background:var(--pos,#34D399); } .ic-y { background:#E5A50A; } .ic-r { background:var(--neg,#F87171); }
.ic-na { background:rgba(127,127,127,.4); }
.ic-zeile { display:flex; justify-content:space-between; gap:8px; font-size:.8rem; margin-top:4px; flex-wrap:wrap; }
.ic-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table.ic { display:table !important; width:100%; min-width:520px; border-collapse:separate; border-spacing:0;
  font-size:.84rem; }
table.ic th { text-align:left; color:var(--label,#A9ACB0); font-size:.72rem; text-transform:uppercase;
  letter-spacing:.4px; padding:5px 6px; border-bottom:1px solid var(--line,#353739); }
table.ic td { padding:6px; border-bottom:1px solid var(--line,#26282A); vertical-align:top; }
table.ic td.r { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.ic-eing { display:inline-block; font-size:.7rem; padding:0 6px; border-radius:6px; margin-left:4px;
  border:1px solid #E5A50A; color:#E5A50A; white-space:nowrap; }
.ic-heat { display:grid; grid-template-columns:minmax(110px, 160px) 1fr; gap:4px 10px; align-items:center;
  font-size:.82rem; margin:4px 0 12px; }
.ic-heat .z { display:flex; flex-wrap:wrap; gap:3px; }
.ic-heat .c { width:18px; height:18px; border-radius:4px; display:inline-block; }
.ic-heat .c.pass { background:var(--pos,#34D399); } .ic-heat .c.fail { background:var(--neg,#F87171); }
.ic-heat .c.na { background:rgba(127,127,127,.35); }
.ic-sw { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:10px 24px; margin:4px 0 12px; }
.ic-sw ul { margin:4px 0 0; padding-left:1.1rem; }
@media (max-width: 760px) { .ic-kopf { grid-template-columns:1fr; } .ic-sw { grid-template-columns:1fr; } }
</style>
"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _de(x, n=1):
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def wert_text(w, fmt, waehrung=""):
    """Anzeige eines Kriteriums-/Zusatzwerts je Format."""
    if w is None:
        return "n/a"
    if isinstance(w, str):
        return w
    if isinstance(w, float) and w == float("inf"):
        return "keine Zinslast" if fmt == "x" else "∞"
    if fmt == "pct":
        return f"{_de(w)} %"
    if fmt == "pctf":
        return f"{_de(w * 100)} %"
    if fmt in ("pp",):
        return f"{'+' if w > 0 else ''}{_de(w)} Pp."
    if fmt == "ppf":
        return f"{'+' if w > 0 else ''}{_de(w * 100, 2)} Pp."
    if fmt == "x":
        return f"{_de(w)}x"
    if fmt == "usd":
        return f"{_de(w / 1e9)} Mrd. USD"
    if fmt == "geld":
        if abs(w) >= 1e8:
            return f"{_de(w / 1e9, 2)} Mrd. {waehrung}".strip()
        if abs(w) >= 1e5:
            return f"{_de(w / 1e6)} Mio. {waehrung}".strip()
        return f"{_de(w, 0)} {waehrung}".strip()
    if fmt == "kurs":
        return f"{_de(w, 2)} {waehrung}".strip()
    if fmt == "zahl3":
        return _de(w, 3)
    if fmt == "stueck":
        return f"{_de(w / 1e6)} Mio."
    if fmt == "zahl":
        return _de(w, 2)
    if fmt == "zahl0":
        return _de(w, 0)
    return _de(w) if isinstance(w, (int, float)) else str(w)


# ---------------------------------------------------------------- Daten (yfinance)
def _yf():
    import yfinance as yf          # erst bei Bedarf laden (spart Startzeit der App)
    return yf


@st.cache_data(ttl=24 * 3600, show_spinner=False, max_entries=300)
def lade_fundamental(symbol):
    """Fundamentaldaten (24 h): info, Jahres-GuV/Bilanz/Cashflow, Quartals-GuV, Dividendenhistorie, Insider,
    Schaetzungsrevisionen - parallel abgerufen. -> {info, gj, bilanz, cashflow, q_gj, dividenden, insider,
    revisionen, fehler}"""
    t = _yf().Ticker(symbol)
    abrufe = {"info": lambda: t.info, "gj": lambda: t.income_stmt, "bilanz": lambda: t.balance_sheet,
              "cashflow": lambda: t.cashflow, "q_gj": lambda: t.quarterly_income_stmt,
              "dividenden": lambda: t.dividends, "insider": lambda: t.insider_transactions,
              "revisionen": lambda: t.eps_revisions}
    aus, fehler = {}, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        laeufe = {k: ex.submit(fn) for k, fn in abrufe.items()}
        for k, lauf in laeufe.items():
            try:
                aus[k] = lauf.result(timeout=20)
            except Exception as e:      # Yahoo drosselt/sperrt gelegentlich - Teilausfall statt Absturz
                logging.warning("yfinance %s %s: %s", symbol, k, type(e).__name__)
                aus[k] = None
                fehler.append(k)
    aus["fehler"] = fehler
    return aus


@st.cache_data(ttl=15 * 60, show_spinner=False, max_entries=300)
def lade_kurse(symbol):
    """Tageskurse 5 Jahre (15 Min.)."""
    try:
        return _yf().Ticker(symbol).history(period="5y", auto_adjust=True)
    except Exception as e:
        logging.warning("yfinance Kurse %s: %s", symbol, type(e).__name__)
        return None


@st.cache_data(ttl=15 * 60, show_spinner=False, max_entries=10)
def lade_index(symbol):
    """Leitindex 2 Jahre (15 Min.) fuer die Marktrichtung (CAN SLIM "M")."""
    try:
        return _yf().Ticker(symbol).history(period="2y", auto_adjust=True)
    except Exception as e:
        logging.warning("yfinance Index %s: %s", symbol, type(e).__name__)
        return None


@st.cache_resource(ttl=900, show_spinner=False)
def _vergleich(_d, tag):
    """Top-500-Vergleichsdaten fuer alle Aktien (einmal je Datenstand): Magic-Formula-Raenge und
    Rang nach Boersenwert im Sektor."""
    u = _d["u"]
    sektoren = {}
    for e in u:
        mcap = (e.get("info") or {}).get("mcap")
        if e["art"] == "aktie" and e.get("sektor") and mcap:
            sektoren.setdefault(e["sektor"], []).append((float(mcap), e["id"]))
    rang = {}
    for liste in sektoren.values():
        liste.sort(reverse=True)
        for i, (_, eid) in enumerate(liste, 1):
            rang[eid] = (i, len(liste))
    return {"greenblatt": GB.raenge(u), "sektor_rang": rang}


def fakten_fuer(e, h, d):
    """Fakten der gewaehlten Aktie (yfinance) + Kontext. -> (fakten, kontext, hinweis oder None)"""
    sym = e.get("ticker")
    fx = {k: v[1] for k, v in ((h["gh_read_taeglich"]("state/top50_fx.json", None) or {}).items())
          if isinstance(v, (list, tuple)) and len(v) > 1}
    roh, kurse, hinweis, idx, idx_name = {}, None, None, None, ""
    if sym:
        try:
            roh = lade_fundamental(sym)
            kurse = lade_kurse(sym)
            info = roh.get("info") or {}
            idx_sym, idx_name = DT.leitindex({"land": info.get("country") or "",
                                              "kurs_waehrung": info.get("currency") or ""})
            idx = lade_index(idx_sym)
        except Exception as ex:          # yfinance fehlt/Netz weg: mit Top-500-Daten weiter
            logging.warning("Investoren-Checks %s: %s", sym, ex)
            roh, hinweis = {}, "Yahoo Finance ist gerade nicht erreichbar – nur Checks aus den Top-500-Daten."
    else:
        hinweis = "Für diesen Wert gibt es kein Yahoo-Symbol – nur Checks aus den Top-500-Daten."
    if roh.get("fehler") and not hinweis:
        hinweis = "Yahoo Finance hat nicht alle Daten geliefert – betroffene Kriterien stehen auf n/a."
    f = DT.fakten_aus_yfinance(roh.get("info") or {}, roh.get("gj"), roh.get("bilanz"), roh.get("cashflow"),
                               q_gj=roh.get("q_gj"), hist=kurse, dividenden=roh.get("dividenden"), fx=fx, agent=e,
                               insider=roh.get("insider"), eps_revisionen=roh.get("revisionen"), index_hist=idx,
                               index_name=idx_name)
    if not f["sektor"] and not f["branche"]:
        f["branche"] = e.get("sektor") or ""
    v = _vergleich(d, datetime.date.today().isoformat())
    kx = {"agent": e, "verteilungen": d["ver"], "greenblatt": v["greenblatt"],
          "sektor_rang": v["sektor_rang"].get(e["id"])}
    return f, kx, hinweis


# ---------------------------------------------------------------- Checkliste (je Benutzer gespeichert)
def _notizen(h):
    s = st.session_state
    if P + "notizen" not in s:
        roh = None
        try:
            roh = h["gh_read"](h["pfad_notizen"], None) if h.get("speichern") else None
        except Exception as ex:
            logging.warning("Bewertung: Notizen nicht lesbar: %s", ex)
            s[P + "lesefehler"] = True
        s[P + "notizen"] = roh if isinstance(roh, dict) else {}
    return s[P + "notizen"]


def _notiz_speichern(h, schluessel, eintrag):
    _notizen(h)[schluessel] = eintrag
    if not h.get("speichern") or st.session_state.get(P + "lesefehler"):
        return False

    def aendern(alt):
        neu = dict(alt or {})
        neu[schluessel] = eintrag
        return neu
    try:
        ok, _ = h["gh_aktualisiere"](h["pfad_notizen"], aendern, {}, "bewertung notizen [skip ci]")
        return bool(ok)
    except Exception as ex:
        logging.warning("Bewertung: Speichern fehlgeschlagen: %s", ex)
        return False


def checkliste(h, e):
    """Qualitative Punkte zum Abhaken mit Notiz, dauerhaft je Aktie. -> Anteil erfuellt (0-100) oder None"""
    schluessel = e.get("ticker") or e["id"]
    alt = _notizen(h).get(schluessel) or {}
    punkte = dict(alt.get("punkte") or {})
    with st.form(P + "form_" + schluessel, border=False):
        for kid, frage, hilfe in CHECKLISTE:
            punkte[kid] = st.checkbox(frage, value=bool(punkte.get(kid)), help=hilfe, key=f"{P}{schluessel}_{kid}")
        notiz = st.text_area("Notiz", value=alt.get("notiz") or "", key=f"{P}{schluessel}_notiz", height=90,
                             placeholder="Eigene Gedanken, Quellen, offene Fragen …")
        if st.form_submit_button("Checkliste speichern", type="primary"):
            ok = _notiz_speichern(h, schluessel, {"punkte": punkte, "notiz": notiz,
                                                  "datum": datetime.date.today().isoformat(),
                                                  "quelle": "eigene Einschätzung"})
            (st.success if ok else st.info)("Gespeichert." if ok else "Für diese Sitzung übernommen – dauerhaftes "
                                            "Speichern ist gerade nicht möglich.")
    if alt.get("datum"):
        st.caption(f"Zuletzt gespeichert: {_datum(alt['datum'])} · Quelle: eigene Einschätzung")
    n = sum(1 for k, _, _ in CHECKLISTE if punkte.get(k))
    return 100.0 * n / len(CHECKLISTE) if alt.get("datum") else None


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso)


# ---------------------------------------------------------------- Darstellung
def _farbe(score):
    return "ic-na" if score is None else "ic-g" if score >= C.KAUFEN_AB_SCORE else "ic-y" if score >= 40 else "ic-r"


def _kopf(k, manuell):
    score = k["score"]
    if manuell is not None and score is not None:
        score = 0.8 * score + 0.2 * manuell
    note = KO.note(score)
    css = note if note in "ABCDEF" and note != "–" else "x"
    zus = (f'<div class="ic-m">inkl. eigener Checkliste ({_de(manuell, 0)} % erfüllt, 20 % Gewicht)</div>'
           if manuell is not None and k["score"] is not None else "")
    st.markdown(f'<div class="ic-kopf"><div class="ic-note {css}" role="img" aria-label="Gesamtnote {note}">'
                f'{note}</div><div><div class="ic-gross">{k["kaufen"]} von {k["investoren"]} Investoren würden '
                f'kaufen</div><div class="ic-m">{_e(k["satz"])}</div>{zus}'
                + "".join(f'<span class="ic-badge">{_e(b)}</span>' for b in k["badges"]) + "</div></div>",
                unsafe_allow_html=True)


def _warnungen(k):
    if k["warnungen"]:
        st.markdown('<div class="ic-warn"><b>Warnsignale</b><ul>' +
                    "".join(f"<li>{_e(w)}</li>" for w in dict.fromkeys(k["warnungen"])) + "</ul></div>",
                    unsafe_allow_html=True)


def _heatmap(ergebnisse):
    zeilen = []
    for r in ergebnisse:
        zellen = "".join(f'<span class="c {x["status"]}" title="{_e(x["name"])}: '
                         f'{ {"pass": "erfüllt", "fail": "nicht erfüllt", "na": "n/a"}[x["status"]]}"></span>'
                         for x in r["kriterien"]) or '<span class="ic-m">nicht anwendbar</span>'
        zeilen.append(f'<div>{_e(r["investor"])}</div><div class="z">{zellen}</div>')
    st.markdown('<div class="ic-heat">' + "".join(zeilen) + "</div>", unsafe_allow_html=True)
    st.caption("Grün = erfüllt · Rot = nicht erfüllt · Grau = n/a. Antippen/Hovern zeigt das Kriterium.")


def _karte(r, f):
    s, wae = r["score_0_100"], f.get("waehrung") or ""
    breite = 0 if s is None else s
    st.markdown(
        f'<div class="ic-karte"><div class="n">{_e(r["investor"])}</div><div class="s">{_e(r["strategie"])}</div>'
        f'<div class="ic-bahn"><div class="{_farbe(s)}" style="width:{breite:.0f}%"></div></div>'
        f'<div class="ic-zeile"><span>{r["erfuellt"]} von {r["gesamt"]} erfüllt'
        + (f' · {r["anzahl"] - r["gesamt"]} n/a' if r["anzahl"] > r["gesamt"] else "")
        + f'</span><span class="ic-m">{_e(r["fazit"])}</span></div></div>', unsafe_allow_html=True)
    with st.expander("Kriterien ansehen", expanded=False):
        if r.get("info"):
            st.caption(r["info"])
        if r["kriterien"]:
            zeilen = "".join(
                f'<tr><td>{SYMBOL[k["status"]]}</td><td>{_e(k["name"])}'
                + (f'<span class="ic-eing">eingeschränkt: {_e(k["eingeschraenkt"])}</span>' if k["eingeschraenkt"]
                   else "")
                + f'<div class="ic-m">{_e(k["erklaerung"])}</div></td>'
                f'<td class="r">{_e(wert_text(k["wert"], k["fmt"], wae))}</td>'
                f'<td class="r">{_e(wert_text(k["schwelle"], k["fmt"], wae))}</td></tr>' for k in r["kriterien"])
            st.markdown('<div class="ic-wrap"><table class="ic"><thead><tr><th></th><th>Kriterium</th>'
                        '<th class="r">Ist</th><th class="r">Schwelle</th></tr></thead><tbody>' + zeilen +
                        "</tbody></table></div>", unsafe_allow_html=True)
        for a in r["ausgeblendet"]:
            st.caption(f"Ausgeblendet: {a['name']} – {a['grund']}")
        if r["extras"]:
            st.markdown("**Zusätzlich**")
            for x in r["extras"]:
                st.markdown(f"- **{_e(x['name'])}:** {_e(wert_text(x['wert'], x['fmt'], wae))} "
                            f"<span class='ic-m'>– {_e(x['text'])}</span>", unsafe_allow_html=True)
        if r["id"] == "buffett":
            _dcf(r, f)
        if r["id"] == "minervini" and r.get("chart"):
            _trend_chart(f)
        st.caption(r["datenbasis"] + (" · Sektor-Sonderregel: " + r["sektor_typ"] if r["sektor_typ"] not in
                                      ("normal", "") else ""))


def _dcf(r, f):
    """Einfacher DCF auf Owner Earnings mit Schiebereglern."""
    cfg = C.BUFFETT
    oe, aktien = r.get("owner_earnings"), r.get("aktien")
    st.markdown("**DCF auf Owner Earnings**")
    if not oe or oe <= 0 or not aktien:
        st.caption("Nicht berechenbar – Owner Earnings fehlen oder sind negativ.")
        return
    sp = st.columns(3) if not UI.ist_smartphone() else [st.container(), st.container(), st.container()]
    g = sp[0].slider("Wachstum p. a.", 0.0, 20.0, float(cfg["dcf_wachstum"]), 0.5, key=P + "dcf_g", format="%.1f %%")
    rr = sp[1].slider("Diskontsatz", 5.0, 15.0, float(cfg["dcf_diskont"]), 0.5, key=P + "dcf_r", format="%.1f %%")
    ge = sp[2].slider("Ewiges Wachstum", 0.0, 4.0, float(cfg["dcf_ewig"]), 0.5, key=P + "dcf_ge", format="%.1f %%")
    wert = BUF.dcf(oe, g, rr, ge, cfg["dcf_jahre"])
    if wert is None:
        st.caption("Diskontsatz muss über dem ewigen Wachstum liegen.")
        return
    je = wert / aktien
    kurs = f.get("kurs_in_bericht")
    marge = (je - kurs) / je * 100 if kurs and je > 0 else None
    st.markdown(f"Innerer Wert je Aktie: **{_de(je, 2)} {_e(f.get('waehrung'))}**"
                + (f" · Kurs {_de(kurs, 2)} · Sicherheitsmarge **{_de(marge, 0)} %**" if marge is not None else ""))
    st.caption(f"{cfg['dcf_jahre']} Jahre Wachstum, danach ewige Rente. Annahme: Erhaltungs-Capex = gesamter Capex.")


def _trend_chart(f):
    """Mini-Chart: Kurs mit 50-/150-/200-Tage-Linie (letztes Jahr)."""
    import plotly.graph_objects as go
    from investor_checks import kurs as KU
    k = f.get("kurse") or []
    w = [c for _, c, _ in k]
    linien = {n: KU.smas(w, n) for n in (50, 150, 200)}
    ab = max(0, len(k) - 260)
    x = [d for d, _, _ in k][ab:]
    fig = go.Figure(go.Scatter(x=x, y=w[ab:], name="Kurs", line=dict(width=2, color=UI.AKZENT)))
    for n, farbe in ((50, UI.CHART_FARBEN[1]), (150, UI.CHART_FARBEN[3]), (200, UI.CHART_FARBEN[4])):
        fig.add_trace(go.Scatter(x=x, y=linien[n][ab:], name=f"{n} Tage", line=dict(width=1.3, color=farbe)))
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
                      legend=dict(orientation="h", y=-0.2))
    UI.chart_stil(fig, schrumpfen=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=P + "trend")


def _fairer_wert(f, kx):
    """Uebersicht "Fairer Wert": alle Modelle als Balken, aktueller Kurs als Linie, Median gestrichelt."""
    import plotly.graph_objects as go
    from investor_checks import fairer_wert as FW
    s = st.session_state
    dcf = (s.get(P + "dcf_g", C.BUFFETT["dcf_wachstum"]), s.get(P + "dcf_r", C.BUFFETT["dcf_diskont"]),
           s.get(P + "dcf_ge", C.BUFFETT["dcf_ewig"]))
    u = FW.uebersicht(f, kx, dcf)
    mit = [m for m in u["modelle"] if m["wert"]]
    wae = u["waehrung"]
    if not mit:
        st.caption("Für keine Bewertungsmethode reichen die Daten.")
        return
    namen = [m["methode"] for m in mit][::-1]
    werte = [m["wert"] for m in mit][::-1]
    kurs = u["kurs"]
    farben = [UI.CHART_FARBEN[0] if not kurs or w >= kurs else "#F87171" for w in werte]
    fig = go.Figure(go.Bar(x=werte, y=namen, orientation="h", marker_color=farben,
                           text=[wert_text(w, "kurs", wae) for w in werte], textposition="auto",
                           hovertemplate="%{y}: %{x:,.2f} " + wae + "<extra></extra>"))
    if kurs:
        fig.add_vline(x=kurs, line=dict(color="#E5A50A", width=2), annotation_text=f"Kurs {_de(kurs, 2)}",
                      annotation_position="top")
    if u["median"]:
        fig.add_vline(x=u["median"], line=dict(color="#A9B1C4", width=1.5, dash="dash"),
                      annotation_text=f"Median {_de(u['median'], 2)}", annotation_position="bottom")
    fig.update_layout(height=60 + 42 * len(namen), margin=dict(l=10, r=10, t=30, b=30), showlegend=False)
    UI.chart_stil(fig, schrumpfen=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=P + "fair")
    if kurs and u["median"]:
        abst = (u["median"] / kurs - 1) * 100
        st.markdown(f"Median aller Methoden: **{wert_text(u['median'], 'kurs', wae)}** – "
                    f"{'über' if abst >= 0 else 'unter'} dem Kurs um **{_de(abs(abst), 0)} %**.")
    st.markdown(f"**Reverse-DCF:** {_e(u['reverse']['text'])}")
    with st.expander("Methoden im Detail"):
        for m in u["modelle"]:
            st.markdown(f"- **{_e(m['methode'])}:** {_e(wert_text(m['wert'], 'kurs', wae))} "
                        f"<span class='ic-m'>– {_e(m['text'])}</span>", unsafe_allow_html=True)
    st.caption("Je Aktie in der Berichtswährung (der Kurs ist dafür umgerechnet). Rot = unter dem Kurs. "
               f"Reverse-DCF mit {_de(C.REVERSE_DCF['diskont'])} % Diskont und {_de(C.REVERSE_DCF['ewig'])} % "
               "ewigem Wachstum. Modelle sind Näherungen – die Spanne zeigt die Unsicherheit.")


def bereich(h, e, d):
    """Investoren-Checks fuer eine Aktie (aus bewertung_ui aufgerufen)."""
    st.markdown(CSS, unsafe_allow_html=True)
    t0 = datetime.datetime.now()
    with st.spinner("Lade Bilanzdaten von Yahoo Finance …"):
        f, kx, hinweis = fakten_fuer(e, h, d)
    ergebnisse = IC.alle_checks(f, kx)
    if hinweis:
        st.info(hinweis)
    alle_kat = [k for k in C.KATEGORIEN if any(r["kategorie"] == k for r in ergebnisse)]
    gewaehlt = st.pills("Filter", alle_kat, selection_mode="multi", key=P + "filter", label_visibility="collapsed",
                        default=alle_kat) or alle_kat
    sicht = [r for r in ergebnisse if r["kategorie"] in gewaehlt]
    k = KO.konsens(ergebnisse, gewaehlt)
    manuell_an = st.session_state.get(P + "manuell_an", False)
    manuell = None
    if manuell_an:
        alt = _notizen(h).get(e.get("ticker") or e["id"]) or {}
        if alt.get("datum"):
            pk = alt.get("punkte") or {}
            manuell = 100.0 * sum(1 for x, _, _ in CHECKLISTE if pk.get(x)) / len(CHECKLISTE)
    _kopf(k, manuell)
    _warnungen(KO.konsens(ergebnisse))
    if k["staerken"] or k["schwaechen"]:
        st.markdown('<div class="ic-sw"><div><b>Stärken</b><ul>' +
                    ("".join(f"<li>{_e(x)}</li>" for x in k["staerken"]) or "<li class='ic-m'>keine</li>") +
                    '</ul></div><div><b>Schwächen</b><ul>' +
                    ("".join(f"<li>{_e(x)}</li>" for x in k["schwaechen"]) or "<li class='ic-m'>keine</li>") +
                    "</ul></div></div>", unsafe_allow_html=True)
    ansicht = st.segmented_control("Ansicht", ["Karten", "Heatmap"], default="Karten", key=P + "ansicht",
                                   label_visibility="collapsed") or "Karten"
    if ansicht == "Heatmap":
        _heatmap(sicht)
    else:
        n = 1 if UI.ist_smartphone() else 2
        spalten = st.columns(n)
        for i, r in enumerate(sicht):
            with spalten[i % n]:
                _karte(r, f)
    st.markdown("**Fairer Wert – alle Methoden**")
    _fairer_wert(f, kx)
    with st.expander("Qualitative Checkliste (eigene Einschätzung)"):
        st.caption("Nicht automatisch berechenbar – hier selbst abhaken. Gespeichert je Aktie in deinem Bereich.")
        checkliste(h, e)
        st.toggle("Checkliste in die Gesamtnote einbeziehen (20 %)", key=P + "manuell_an")
    dauer = (datetime.datetime.now() - t0).total_seconds()
    st.caption(f"Quelle: Yahoo Finance (yfinance) · Fundamentaldaten bis 24 h, Kurse bis 15 Min. zwischengespeichert · "
               f"Vergleich: Top-500-Daten · Annahmen (AAA {_de(C.AAA_RENDITE)} %, Staatsanleihe "
               f"{_de(C.STAATSANLEIHE_10J)} %) Stand {C.ANNAHMEN_STAND} · geladen in {_de(dauer)} s")
    st.caption("Vereinfachte Annäherungen an die Methoden der genannten Investoren auf Basis öffentlich verfügbarer "
               "Daten – keine Anlageberatung und keine Aussage, was diese Personen tatsächlich kaufen würden.")
