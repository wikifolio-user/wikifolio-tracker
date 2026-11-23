"""Gap Analyzer (Menuepunkt "Gap Analyzer") - Oberflaeche. Rechnungen: gap_analyzer.py.

Bereiche: Opening-Gaps heute | Offene High-Low-Gaps (inkl. Uebersicht und Historie) | Opening-Gap-Historie |
Gap-Chart | Gap-Statistik (inkl. Vergleich) | Alerts. Opening-Gaps: opening_gaps.py / opening_gaps_ui.py.
Datengrundlage: echte, abgeschlossene Tageskerzen der Cash-Indizes (state/markt/ohlc.json). Aktueller Stand fuer
Lage/Entfernung: indizes.json (Kurs-Agent), sonst letzter Schlusskurs (gekennzeichnet).
h = {"ohlc": () -> ohlc.json, "indizes": () -> indizes.json, "intraday": () -> opening_intraday.json (optional)}
"""
import datetime
import io
import json
import re
from zoneinfo import ZoneInfo

import streamlit as st

import gap_analyzer as G
import opening_gaps as OG
import opening_gaps_ui as OGU
import ui_stil as UI

P = "gap_"
BERLIN = ZoneInfo("Europe/Berlin")
SYMBOL = {kurz: sym for sym, (kurz, _) in G.INDEX.items()}
NAME = {kurz: name for _, (kurz, name) in G.INDEX.items()}
CODES = list(SYMBOL)
BEREICHE = ["Opening-Gaps heute", "Offene High-Low-Gaps", "Opening-Gap-Historie", "Gap-Chart", "Gap-Statistik",
            "Alerts"]
HALTEN = re.compile(r"^gap_(bereich|definition|pct_min|von|index|einheit|f_.*|h_.*|zeige_geschlossen|al_.*|auswahl|"
                    r"og_.*|hl_sicht|zeige_og|zeige_hl)$")
GRUEN, ROT = "#22C55E", "#EF4444"

CSS = """<style>
.gp-kopf { display:flex; gap:12px; align-items:center; margin:2px 0 8px; }
.gp-kopf .gp-sym { font-size:1.35rem; width:38px; height:38px; border-radius:10px; background:#252628;
    display:flex; align-items:center; justify-content:center; }
.gp-kopf b { font-size:1.05rem; color:#ffffff; } .gp-kopf div div { font-size:.8rem; color:#A9ACB0; }
.gp-raster { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin:6px 0 8px; }
@media (max-width: 1100px) { .gp-raster { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width: 640px) { .gp-raster { grid-template-columns:1fr; } }
.gp-karte { border:1px solid rgba(255,255,255,.12); border-radius:14px; padding:10px 12px; background:rgba(255,255,255,.03); }
.gp-karte .gp-name { font-size:.85rem; font-weight:700; color:#E8ECF6; }
.gp-karte .gp-kurs { font-size:1.4rem; font-weight:800; color:#ffffff; font-variant-numeric:tabular-nums; }
.gp-zahlen { display:grid; grid-template-columns:repeat(3, 1fr); gap:4px; margin:6px 0; }
.gp-zahlen div { font-size:.68rem; color:#A9ACB0; text-align:center; background:rgba(255,255,255,.04);
    border-radius:8px; padding:4px 2px; }
.gp-zahlen b { display:block; font-size:1.05rem; color:#ffffff; }
.gp-zeile { font-size:.78rem; color:#C9CED6; margin-top:3px; }
.gp-zeile b { color:#ffffff; }
.gp-meta { font-size:.68rem; color:#A9ACB0; margin-top:5px; }
.gp-warn { color:#FBBF24; font-weight:700; }
.gp-up { color:#34D399 !important; font-weight:700; } .gp-down { color:#F87171 !important; font-weight:700; }
.gp-tab { width:100%; border-collapse:collapse; font-size:.84rem; font-variant-numeric:tabular-nums; }
.gp-tab th { text-align:left; color:#A9ACB0; font-weight:600; padding:5px 8px; border-bottom:1px solid rgba(255,255,255,.12);
    white-space:nowrap; }
.gp-tab td { padding:5px 8px; color:#E8ECF6; border-bottom:1px solid rgba(255,255,255,.06); white-space:nowrap; }
.gp-tab td.r, .gp-tab th.r { text-align:right; }
.gp-tabwrap { overflow-x:auto; }
.gp-leer { font-size:.85rem; color:#A9ACB0; padding:6px 0; }
</style>"""


def _de(x, n=1):
    return "–" if x is None else f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _datum(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return "–"


def _typ(g):
    return "Gap Up" if g["typ"] == "up" else "Gap Down"


# ---------------------------------------------------------------------------------------------------- Daten
@st.cache_data(ttl=1800, show_spinner=False, max_entries=12)
def _gaps(_ohlc, stand, definition, pct_min):
    """Je Index: geprueften Kerzen, Probleme, Gaps (vollstaendig chronologisch bis zur letzten Kerze)."""
    aus = {}
    for kurz, sym in SYMBOL.items():
        e = ((_ohlc or {}).get("indizes") or {}).get(sym) or {}
        kerzen, probleme = G.kerzen_pruefen(e.get("kerzen"))
        fehlende = (e.get("pruefung") or {}).get("fehlende") or []
        aus[kurz] = {"kerzen": kerzen, "probleme": probleme, "fehlende": fehlende,
                     "gaps": G.erkennen(kerzen, kurz, definition, fehlende, pct_min, stand) if kerzen else [],
                     "quelle": e.get("quelle") or "–", "instrument": e.get("instrument") or "–",
                     "abruf": e.get("abruf"), "symbol": sym}
    return aus


def _kurse(h, daten):
    """Aktueller Stand je Index -> {kurz: (kurs, quelle_text)}."""
    try:
        idx = (h["indizes"]() or {}).get("werte") or {}
    except Exception:
        idx = {}
    aus = {}
    for kurz, d in daten.items():
        w = idx.get(d["symbol"]) or {}
        try:
            aus[kurz] = (float(w["k"]), "aktueller Stand (Kurs-Agent)")
        except (KeyError, TypeError, ValueError):
            aus[kurz] = (d["kerzen"][-1][4], "letzter Schlusskurs") if d["kerzen"] else (None, "–")
    return aus


def _halten():
    s = st.session_state
    for k in [k for k in list(s.keys()) if HALTEN.match(str(k))]:
        s[k] = s[k]


# ---------------------------------------------------------------------------------------------------- Seite
def seite(h):
    st.markdown(CSS, unsafe_allow_html=True)
    s = st.session_state
    _halten()
    st.markdown('<div class="gp-kopf"><span class="gp-sym">🕳️</span><div><b>Gap Analyzer – Gap Up &amp; Gap Down</b>'
                '<div>Kurslücken von Nasdaq 100, DAX 40, S&amp;P 500 und Dow Jones – chronologisch geprüft</div>'
                '</div></div>', unsafe_allow_html=True)
    try:
        ohlc = h["ohlc"]() or {}
    except Exception:
        ohlc = {}
    if not (ohlc.get("indizes") if isinstance(ohlc, dict) else None):
        st.warning("Noch keine Tageskerzen vorhanden. Der Kurs-Agent legt sie bei seinem nächsten Lauf ab – bis dahin "
                   "kann der Gap Analyzer nichts prüfen (es werden keine Werte geschätzt).")
        return
    with st.expander("⚙️ Definition und Analysezeitraum", expanded=False):
        s.setdefault(P + "og_min", OG.MIN_PCT)
        st.number_input("Mindestgröße Opening-Gaps (%)", 0.0, 5.0, step=0.05, format="%.2f", key=P + "og_min",
                        help="Kleinere Eröffnungslücken gelten als „kein Opening-Gap“ (Tabs Opening-Gaps).")
        s.setdefault(P + "definition", "hl")
        st.segmented_control("Definition der Range-Gaps (Tabs High-Low-Gaps, Chart, Statistik)",
                             list(G.DEFINITIONEN), key=P + "definition",
                             format_func=G.DEFINITIONEN.get, width="stretch")
        if s.get(P + "definition") == "pct":
            st.number_input("Mindestgröße Opening Gap (%)", 0.05, 10.0, value=None, step=0.05, format="%.2f",
                            key=P + "pct_min", placeholder=f"{G.PCT_MINDEST:.2f}")
        s.setdefault(P + "von", "2025-01-01")
        jahre = ["2025-01-01", "2024-01-01", "2023-01-01", "2020-01-01", "2015-01-01"]
        st.selectbox("Analyse ab", jahre, key=P + "von", format_func=lambda x: f"{x[:4]} (Gaps ab {_datum(x)})")
        st.caption("High-Low-Gap: Tief heute > Hoch gestern (Up) bzw. Hoch heute < Tief gestern (Down). "
                   "Close-Open: Eröffnung ≠ Schluss gestern. Opening Gap (%): Close-Open ab Mindestgröße. "
                   "Der Füllstatus wird immer bis zur letzten vollständigen Tageskerze geprüft.")
    definition = s.get(P + "definition") or "hl"
    pct_min = float(s.get(P + "pct_min") or G.PCT_MINDEST)
    daten = _gaps(ohlc, str(ohlc.get("stand")), definition, pct_min)
    kurse = _kurse(h, daten)
    von = s.get(P + "von") or "2025-01-01"
    gaps = {k: G.mit_lage(G.zeitraum(d["gaps"], von), kurse[k][0]) for k, d in daten.items()}
    st.caption(f"Definition: **{G.DEFINITIONEN[definition]}**"
               + (f" (≥ {_de(pct_min, 2)} %)" if definition == "pct" else "")
               + f" · Gaps entstanden ab {_datum(von)} · Instrument: Cash-Index (Tageskerzen)")
    if s.get(P + "bereich") not in BEREICHE:
        s[P + "bereich"] = BEREICHE[0]
    bereich = st.segmented_control("Bereich", BEREICHE, key=P + "bereich", label_visibility="collapsed",
                                   width="stretch") or BEREICHE[0]
    og_min = float(s.get(P + "og_min") if s.get(P + "og_min") is not None else OG.MIN_PCT)
    og = {"h": h, "ohlc": ohlc, "min": og_min}
    if bereich == "Opening-Gaps heute":
        OGU.tab_heute(h, ohlc, CODES, SYMBOL, NAME, kurse, og_min)
    elif bereich == "Opening-Gap-Historie":
        OGU.tab_historie(h, ohlc, CODES, SYMBOL, NAME, og_min, _exporte)
    elif bereich == "Offene High-Low-Gaps":
        _hl_bereich(daten, gaps, kurse, definition)
    elif bereich == "Gap-Chart":
        _chart(daten, gaps, kurse, definition, og)
    elif bereich == "Gap-Statistik":
        _statistik(daten, gaps, kurse, definition)
        st.markdown("**Index-Vergleich (Range-Gaps)**")
        _vergleich(daten, gaps, kurse, definition)
        st.markdown("**Opening-Gap-Statistik**")
        OGU.statistik(h, ohlc, CODES, SYMBOL, NAME, og_min)
    else:
        _alerts(daten, gaps, kurse, definition)
        OGU.alerts_bereich(h, ohlc, CODES, SYMBOL, og_min, _gesehen(), _als_gesehen)
    st.caption("Quelle: Yahoo Finance (Tageskerzen der Cash-Indizes ^NDX, ^GDAXI, ^GSPC, ^DJI) – keine Futures, CFDs "
               "oder ETFs. Keine geschätzten Werte. Keine Anlageberatung.")


def _index_wahl(label="Index"):
    s = st.session_state
    if s.get(P + "index") not in CODES:
        s[P + "index"] = "NDX"
    return st.segmented_control(label, CODES, key=P + "index", format_func=NAME.get, width="stretch") or "NDX"


# ---------------------------------------------------------------------------------------------------- Uebersicht
def _gap_kurz(g, kurs):
    if not g:
        return "keine offenen Gaps im geprüften Zeitraum"
    return (f"<b>{_de(g['offen_unten'], 0)}–{_de(g['offen_oben'], 0)}</b> ({_typ(g)} {_datum(g['datum'])}) · "
            f"{_de(g['entfernung'], 0)} Pkt. / {_de(g['entfernung_pct'], 2)} %")


def _uebersicht(daten, gaps, kurse, definition):
    karten = []
    for k in CODES:
        u = G.uebersicht(gaps[k], kurse[k][0])
        d = daten[k]
        letzte = d["kerzen"][-1][0] if d["kerzen"] else None
        warn = ""
        if d["fehlende"]:
            warn = f'<div class="gp-meta gp-warn">{len(d["fehlende"])} fehlende Handelstage – betroffene Gaps nicht vollständig geprüft</div>'
        karten.append(
            f'<div class="gp-karte"><div class="gp-name">{NAME[k]} ({k})</div>'
            f'<div class="gp-kurs">{_de(kurse[k][0], 2)}</div><div class="gp-meta">{kurse[k][1]}</div>'
            '<div class="gp-zahlen">'
            f'<div>offene Ups<b class="gp-up">{u["offen_up"]}</b></div><div>offene Downs<b class="gp-down">{u["offen_down"]}</b></div>'
            f'<div>teilweise<b>{u["teilweise"]}</b></div></div>'
            f'<div class="gp-zeile">▲ Nächstes oberhalb: {_gap_kurz(u["naechstes_oben"], u["kurs"])}</div>'
            f'<div class="gp-zeile">▼ Nächstes unterhalb: {_gap_kurz(u["naechstes_unten"], u["kurs"])}</div>'
            f'<div class="gp-zeile">Summe offener Gap-Breiten: <b>{_de(u["summe_offen"], 0)} Pkt.</b></div>'
            f'<div class="gp-meta">Letzter geprüfter Handelstag: {_datum(letzte)} · Datenabruf: '
            f'{_datum((d["abruf"] or "")[:10])}</div>{warn}</div>')
    st.markdown('<div class="gp-raster">' + "".join(karten) + "</div>", unsafe_allow_html=True)
    st.caption("Darunter: nächste Lücken je Index und alle offenen Gaps; „Gap-Chart“ zeigt sie im Kursverlauf.")


def _hl_bereich(daten, gaps, kurse, definition):
    """Tab "Offene High-Low-Gaps": Uebersichtskarten, offene Gaps und (umschaltbar) die ganze Historie."""
    s = st.session_state
    s.setdefault(P + "hl_sicht", "Offene")
    sicht = st.segmented_control("Ansicht", ["Offene", "Alle (Historie)"], key=P + "hl_sicht",
                                 label_visibility="collapsed") or "Offene"
    if sicht == "Offene":
        _uebersicht(daten, gaps, kurse, definition)
        _offene(daten, gaps, kurse, definition)
    else:
        _historie(daten, gaps, kurse, definition)


# ---------------------------------------------------------------------------------------------------- Tabellen
def _zeilen(liste, kurs_je, einheit="Punkte", markiert=None):
    zeilen = []
    for g in liste:
        kurs = kurs_je.get(g["index"])
        offen = g["status"] != "geschlossen"
        zeilen.append({
            "": "▶" if markiert == g["id"] else "",
            "Index": g["index"], "Datum": g["datum"], "Typ": _typ(g),
            "Untere Grenze": round(g["offen_unten"] if offen else g["unten"], 2),
            "Obere Grenze": round(g["offen_oben"] if offen else g["oben"], 2),
            "Orig. unten": round(g["unten"], 2), "Orig. oben": round(g["oben"], 2),
            "Originalgröße": round(g["groesse"] if einheit == "Punkte" else g["groesse_pct"], 2),
            "Noch offen": round(g["offen_breite"] if einheit == "Punkte" else g["offen_breite"] / kurs * 100, 2)
            if kurs else None,
            "Füllgrad %": round(g["fuellgrad"], 1), "Status": G.STATUS[g["status"]],
            "Lage": (g.get("lage") or "–").capitalize(),
            "Entfernung": None if g.get("entfernung") is None else round(g["entfernung"], 2),
            "Entfernung %": None if g.get("entfernung_pct") is None else round(g["entfernung_pct"], 3),
            "Alter (Tage)": g["alter"], "Berührt": g["beruehrt"] or "", "Geschlossen": g["geschlossen"] or "",
            "Geprüft": "vollständig" if g["vollstaendig"] else "nicht vollständig",
            "Letzte Prüfung": g["geprueft_bis"], "ID": g["id"]})
    return zeilen


def _tabelle(zeilen, key, auswahl=True):
    import pandas as pd
    if not zeilen:
        st.markdown('<div class="gp-leer">Keine Gaps für diese Auswahl.</div>', unsafe_allow_html=True)
        return None
    df = pd.DataFrame(zeilen)
    cfg = {"ID": None, "": st.column_config.TextColumn("", width="small"),
           "Füllgrad %": st.column_config.ProgressColumn("Füllgrad", min_value=0, max_value=100, format="%.0f %%"),
           "Entfernung %": st.column_config.NumberColumn("Entfernung %", format="%.2f %%")}
    ev = st.dataframe(df, hide_index=True, use_container_width=True, column_config=cfg, key=key,
                      height=min(520, 38 + 35 * len(df)),
                      **({"on_select": "rerun", "selection_mode": "single-row"} if auswahl else {}))
    if auswahl and ev and ev.selection.rows:
        gid = df.iloc[ev.selection.rows[0]]["ID"]
        if st.session_state.get(P + "auswahl") != gid:
            st.session_state[P + "auswahl"] = gid
    return df


def _naechste_block(liste, kurs, index):
    ob, un = G.naechste(liste)

    def tab(gs, titel):
        if not gs:
            return f"<b>{titel}</b><div class='gp-leer'>Keine offenen Gaps im geprüften Zeitraum.</div>"
        z = "".join(f"<tr><td>{_datum(g['datum'])}</td><td class='{'gp-up' if g['typ'] == 'up' else 'gp-down'}'>"
                    f"{_typ(g)}</td><td class='r'>{_de(g['offen_unten'], 1)}–{_de(g['offen_oben'], 1)}</td>"
                    f"<td class='r'>{_de(g['offen_breite'], 1)}</td><td class='r'>{_de(g['entfernung'], 1)}</td>"
                    f"<td class='r'>{_de(g['entfernung_pct'], 2)} %</td><td>{G.STATUS[g['status']]}"
                    f"{'' if g['vollstaendig'] else ' ⚠️'}</td></tr>" for g in gs)
        return (f"<b>{titel}</b><div class='gp-tabwrap'><table class='gp-tab'><tr><th>Datum</th><th>Typ</th>"
                "<th class='r'>Offener Bereich</th><th class='r'>Breite</th><th class='r'>Entf. Pkt.</th>"
                f"<th class='r'>Entf. %</th><th>Status</th></tr>{z}</table></div>")
    st.markdown(f"**Nächste Kurslücken – {NAME[index]}** (Stand {_de(kurs, 2)})")
    st.markdown(tab(ob, "▲ Oberhalb des Kurses") + "<div style='height:8px'></div>" + tab(un, "▼ Unterhalb des Kurses"),
                unsafe_allow_html=True)


def _offene(daten, gaps, kurse, definition):
    s = st.session_state
    index = _index_wahl()
    _naechste_block(gaps[index], kurse[index][0], index)
    st.markdown("**Alle offenen und teilweise geschlossenen Gaps**")
    alle = [g for k in CODES for g in gaps[k]]
    f = _filter(alle, standard_status=["offen", "teilweise"], key="f")
    liste = sorted(f, key=lambda g: (g.get("entfernung") is None, g.get("entfernung") or 0))
    einheit = s.get(P + "einheit") or "Punkte"
    df = _tabelle(_zeilen(liste, {k: v[0] for k, v in kurse.items()}, einheit, s.get(P + "auswahl")), key=P + "tab_offen")
    _exporte(df, "offene_gaps")
    st.caption("Zeile antippen → im Gap-Chart wird diese Lücke angesprungen. Typ = Entstehungsrichtung, Lage = heutige "
               "Position zum Kurs. Entfernung = Abstand zum nächsten Punkt des noch offenen Bereichs (0 = Kurs liegt "
               "im Gap). ⚠️/„nicht vollständig“: im Zeitraum fehlen Handelstage – kein verifizierter Status.")


def _filter(alle, standard_status, key):
    s = st.session_state
    with st.expander("Filter", expanded=False):
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        s.setdefault(P + f"{key}_index", CODES)
        idx = sp[0].multiselect("Index", CODES, key=P + f"{key}_index", format_func=NAME.get)
        s.setdefault(P + f"{key}_typ", ["up", "down"])
        typ = sp[1].multiselect("Typ", ["up", "down"], key=P + f"{key}_typ",
                                format_func=lambda x: "Gap Up" if x == "up" else "Gap Down")
        s.setdefault(P + f"{key}_status", standard_status)
        stat = sp[2].multiselect("Status", list(G.STATUS), key=P + f"{key}_status", format_func=G.STATUS.get)
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        lage = sp[0].multiselect("Lage zum Kurs", ["oberhalb", "unterhalb", "innerhalb"], key=P + f"{key}_lage",
                                 format_func=str.capitalize)
        jahre = sorted({g["datum"][:4] for g in alle}, reverse=True)
        jahr = sp[1].multiselect("Jahr", jahre, key=P + f"{key}_jahr")
        s.setdefault(P + "einheit", "Punkte")
        sp[2].segmented_control("Größen in", ["Punkte", "Prozent"], key=P + "einheit")
        sp = st.columns(4) if not UI.ist_smartphone() else [st.container() for _ in range(4)]
        min_pkt = sp[0].number_input("Mindestgröße (Pkt.)", 0.0, step=5.0, key=P + f"{key}_minpkt")
        min_pct = sp[1].number_input("Mindestgröße (%)", 0.0, step=0.05, format="%.2f", key=P + f"{key}_minpct")
        max_ent = sp[2].number_input("Max. Entfernung (%)", 0.0, step=0.5, format="%.1f", key=P + f"{key}_maxent",
                                     help="0 = ohne Grenze")
        max_alter = sp[3].number_input("Max. Alter (Handelstage)", 0, step=5, key=P + f"{key}_maxalter",
                                       help="0 = ohne Grenze")
    return [g for g in alle if g["index"] in (idx or CODES) and g["typ"] in (typ or ["up", "down"])
            and g["status"] in (stat or list(G.STATUS)) and (not lage or g.get("lage") in lage)
            and (not jahr or g["datum"][:4] in jahr) and g["groesse"] >= (min_pkt or 0)
            and g["groesse_pct"] >= (min_pct or 0)
            and (not max_ent or (g.get("entfernung_pct") is not None and g["entfernung_pct"] <= max_ent))
            and (not max_alter or g["alter"] <= max_alter)]


def _exporte(df, name):
    if df is None:
        return
    heute = datetime.date.today()
    raus = df.drop(columns=[""])
    csv = raus.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
    puffer = io.BytesIO()
    raus.to_excel(puffer, index=False, sheet_name="Gaps")
    with st.container(horizontal=True, key=P + f"reihe_export_{name}"):
        st.download_button("⬇️ CSV", csv, file_name=f"{name}_{heute}.csv", mime="text/csv", key=P + f"csv_{name}")
        st.download_button("⬇️ Excel", puffer.getvalue(), file_name=f"{name}_{heute}.xlsx", key=P + f"xlsx_{name}",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------------------------------- Chart
def _chart(daten, gaps, kurse, definition, og=None):
    import plotly.graph_objects as go
    s = st.session_state
    index = _index_wahl()
    d = daten[index]
    kerzen = d["kerzen"]
    if not kerzen:
        st.info("Für diesen Index liegen keine Tageskerzen vor.")
        return
    s.setdefault(P + "zeige_hl", True)
    s.setdefault(P + "zeige_og", True)
    with st.container(horizontal=True, key=P + "reihe_chart_schalter"):
        zeige_hl = st.toggle(f"Range-Gaps ({G.DEFINITIONEN[definition]})", key=P + "zeige_hl")
        zeige_og = st.toggle("Opening-Gaps", key=P + "zeige_og")
        zeige = st.toggle("Geschlossene Range-Gaps einblenden", key=P + "zeige_geschlossen")
    liste = [g for g in gaps[index] if zeige_hl and (zeige or g["status"] != "geschlossen")]
    auswahl = s.get(P + "auswahl") if str(s.get(P + "auswahl") or "").startswith(index + "|") else None
    fig = go.Figure(go.Candlestick(x=[k[0] for k in kerzen], open=[k[1] for k in kerzen], high=[k[2] for k in kerzen],
                                   low=[k[3] for k in kerzen], close=[k[4] for k in kerzen], name=index,
                                   increasing_line_color="#34D399", decreasing_line_color="#F87171", showlegend=False))
    letzte = kerzen[-1][0]
    mx, my, mt, mid = [], [], [], []
    for g in liste:
        farbe = GRUEN if g["typ"] == "up" else ROT
        ende = g["geschlossen"] or letzte
        breit = 3 if g["id"] == auswahl else 0
        if g["status"] == "geschlossen":
            fig.add_shape(type="rect", x0=g["datum"], x1=ende, y0=g["unten"], y1=g["oben"], fillcolor=farbe,
                          opacity=0.10, line=dict(width=breit, color="#FBBF24"), layer="below")
        else:
            fig.add_shape(type="rect", x0=g["datum"], x1=ende, y0=g["unten"], y1=g["oben"], fillcolor=farbe,
                          opacity=0.12, line=dict(width=0), layer="below")             # urspruenglicher Bereich
            fig.add_shape(type="rect", x0=g["datum"], x1=ende, y0=g["offen_unten"], y1=g["offen_oben"],
                          fillcolor=farbe, opacity=0.38, line=dict(width=breit, color="#FBBF24"), layer="below")
        mx.append(g["datum"])
        my.append((g["unten"] + g["oben"]) / 2)
        mid.append(g["id"])
        mt.append(f"{_typ(g)} {_datum(g['datum'])}<br>Original {_de(g['unten'], 1)}–{_de(g['oben'], 1)} "
                  f"({_de(g['groesse'], 1)} Pkt., {_de(g['groesse_pct'], 2)} %)<br>Offen {_de(g['offen_unten'], 1)}–"
                  f"{_de(g['offen_oben'], 1)} · {G.STATUS[g['status']]} ({_de(g['fuellgrad'], 0)} %)")
    if mx:
        fig.add_scatter(x=mx, y=my, mode="markers", marker=dict(size=9, color="#FBBF24", symbol="diamond"),
                        hovertext=mt, hoverinfo="text", customdata=mid, name="Gaps", showlegend=False)
    kurs = kurse[index][0]
    if kurs:
        fig.add_hline(y=kurs, line=dict(color="#7c9cff", dash="dash", width=1.5),
                      annotation_text=f"aktuell {_de(kurs, 0)}", annotation_position="top left")
    # Zeitraum: um das ausgewaehlte Gap, sonst die letzten 9 Monate; y-Achse passend zu den sichtbaren Kerzen
    x0 = (datetime.date.fromisoformat(letzte) - datetime.timedelta(days=270)).isoformat()
    x1 = (datetime.date.fromisoformat(letzte) + datetime.timedelta(days=5)).isoformat()
    g_aus = next((x for x in gaps[index] if x["id"] == auswahl), None) if auswahl else None
    if g_aus:
        a = datetime.date.fromisoformat(g_aus["datum"])
        x0 = (a - datetime.timedelta(days=45)).isoformat()
        x1 = (datetime.date.fromisoformat(g_aus["geschlossen"] or letzte) + datetime.timedelta(days=30)).isoformat()
    og_anzahl = None
    if og and zeige_og:
        try:
            intra = og["h"]["intraday"]() if og["h"].get("intraday") else {}
        except Exception:
            intra = {}
        od = OGU.daten(og["ohlc"], intra, [index], SYMBOL, og["min"], datetime.datetime.now(datetime.timezone.utc))
        og_anzahl = OGU.chart_zonen(fig, od[index], x0, x1, g_aus["datum"] if g_aus else None)
    sicht = [k for k in kerzen if x0 <= k[0] <= x1] or kerzen
    ys = [k[3] for k in sicht] + [k[2] for k in sicht] + ([g_aus["unten"], g_aus["oben"]] if g_aus else [])
    rand = (max(ys) - min(ys)) * 0.06 or max(ys) * 0.01
    fig.update_xaxes(range=[x0, x1])
    fig.update_yaxes(range=[min(ys) - rand, max(ys) + rand])
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=30), xaxis_rangeslider_visible=False,
                      dragmode="pan", yaxis=dict(fixedrange=False), hovermode="closest")
    fig.update_xaxes(rangeselector=dict(bgcolor="rgba(124,156,255,0.18)", activecolor="rgba(124,156,255,0.5)",
                                        font=dict(size=11), buttons=[dict(count=1, label="1M", step="month", stepmode="backward"),
                                                 dict(count=3, label="3M", step="month", stepmode="backward"),
                                                 dict(count=1, label="1J", step="year", stepmode="backward"),
                                                 dict(step="all", label="Alle")]),
                     rangebreaks=[dict(bounds=["sat", "mon"])])
    ev = st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), use_container_width=True, key=P + "chart",
                         on_select="rerun", selection_mode="points",
                         config={"displayModeBar": not UI.ist_smartphone(), "scrollZoom": True, "displaylogo": False})
    try:
        pkt = (ev or {}).get("selection", {}).get("points") or []
        cd = [p.get("customdata") for p in pkt if p.get("customdata")]
        if cd and cd[0] != s.get(P + "auswahl"):
            s[P + "auswahl"] = cd[0]
            st.rerun()
    except Exception:
        pass
    st.caption("Range-Gaps: Grün = Gap Up, Rot = Gap Down. Kräftig = noch offener Bereich, blass = ursprünglicher "
               "bzw. bereits gefüllter Bereich. Zonen reichen bis zur Schließung bzw. zum letzten Handelstag. ◆ antippen "
               "= Gap auswählen (wird in den Tabellen mit ▶ markiert)."
               + (f" Opening-Gaps: schmale Zone am Entstehungstag zwischen Vortagesschluss und Eröffnung (kräftig = "
                  f"noch offen); gepunktete Linien = Vortagesschluss und Eröffnung des letzten bzw. ausgewählten Tages. "
                  f"{og_anzahl} Opening-Gaps im Ausschnitt." if og_anzahl is not None else ""))
    if auswahl:
        g = next((x for x in gaps[index] if x["id"] == auswahl), None)
        if g:
            st.markdown("**Ausgewähltes Gap**")
            _tabelle(_zeilen([g], {k: v[0] for k, v in kurse.items()}, s.get(P + "einheit") or "Punkte", auswahl),
                     key=P + "tab_auswahl", auswahl=False)
            st.button("Auswahl aufheben", key=P + "auswahl_weg", on_click=lambda: s.pop(P + "auswahl", None))
    st.markdown("**Gaps dieses Index im Chart**")
    _tabelle(_zeilen(sorted(liste, key=lambda g: g["datum"], reverse=True), {k: v[0] for k, v in kurse.items()},
                     s.get(P + "einheit") or "Punkte", auswahl), key=P + "tab_chart")


# ---------------------------------------------------------------------------------------------------- Historie
def _historie(daten, gaps, kurse, definition):
    alle = [g for k in CODES for g in gaps[k]]
    f = _filter(alle, standard_status=list(G.STATUS), key="h")
    liste = sorted(f, key=lambda g: g["datum"], reverse=True)
    st.markdown(f"**{len(liste)} erkannte Gaps** ({G.DEFINITIONEN[definition]})")
    df = _tabelle(_zeilen(liste, {k: v[0] for k, v in kurse.items()}, st.session_state.get(P + "einheit") or "Punkte",
                          st.session_state.get(P + "auswahl")), key=P + "tab_hist")
    _exporte(df, "gaps_historie")
    probleme = {k: (d["probleme"], d["fehlende"]) for k, d in daten.items() if d["probleme"] or d["fehlende"]}
    if probleme:
        with st.expander("Datenprüfung"):
            for k, (p, fehl) in probleme.items():
                st.markdown(f"**{NAME[k]}**: {len(fehl)} fehlende Handelstage"
                            + (f" (z. B. {', '.join(_datum(x) for x in fehl[:5])})" if fehl else "")
                            + (f"; {len(p)} verworfene Kerzen" if p else ""))
            st.caption("Gaps, in deren Prüfzeitraum Handelstage fehlen, gelten als „nicht vollständig geprüft“.")


# ---------------------------------------------------------------------------------------------------- Statistik
def _statistik(daten, gaps, kurse, definition):
    index = _index_wahl()
    st_all = G.statistik(gaps[index])
    if not st_all["alle"]["anzahl"]:
        st.info("Im gewählten Zeitraum wurden keine Gaps erkannt.")
        return
    spalten = [("Alle", st_all["alle"]), ("Gap Up", st_all["up"]), ("Gap Down", st_all["down"])]
    reihen = [("Anzahl", lambda x: str(x.get("anzahl", 0))), ("Gap Up", lambda x: str(x.get("up", "–"))),
              ("Gap Down", lambda x: str(x.get("down", "–"))),
              ("Vollständig geschlossen", lambda x: str(x.get("geschlossen", "–"))),
              ("Teilweise geschlossen", lambda x: str(x.get("teilweise", "–"))),
              ("Unberührt", lambda x: str(x.get("offen", "–"))),
              ("Ø Größe", lambda x: f"{_de(x.get('groesse_mittel'), 1)} Pkt. / {_de(x.get('groesse_pct_mittel'), 2)} %"),
              ("Median Größe", lambda x: f"{_de(x.get('groesse_median'), 1)} Pkt. / {_de(x.get('groesse_pct_median'), 2)} %"),
              ("Ø Tage bis Schließung", lambda x: _de(x.get("dauer_mittel"), 1)),
              ("Median Tage bis Schließung", lambda x: _de(x.get("dauer_median"), 1))]
    for n in G.SCHLIESS_FENSTER:
        reihen.append((f"Geschlossen in ≤ {n} Tagen", lambda x, n=n: "–" if not x.get("quoten") or x["quoten"][n][0] is None
                       else f"{_de(x['quoten'][n][0], 0)} % (n={x['quoten'][n][1]})"))
    kopf = "".join(f"<th class='r'>{t}</th>" for t, _ in spalten)
    z = "".join(f"<tr><td>{t}</td>" + "".join(f"<td class='r'>{f(x) if x.get('anzahl') else '–'}</td>" for _, x in spalten)
                + "</tr>" for t, f in reihen)
    st.markdown(f"<div class='gp-tabwrap'><table class='gp-tab'><tr><th>{NAME[index]}</th>{kopf}</tr>{z}</table></div>",
                unsafe_allow_html=True)
    st.caption("Schließungsquote je Zeitfenster nur über Gaps, die mindestens so lange beobachtet werden konnten "
               "(n). Noch offene Gaps sind zensierte Beobachtungen – sie gelten nicht als „nie geschlossen“.")
    import pandas as pd
    rows = [{"Kennzahl": t, **{name: (f(x) if x.get("anzahl") else "") for name, x in spalten}} for t, f in reihen]
    csv = pd.DataFrame(rows).to_csv(sep=";", index=False).encode("utf-8-sig")
    st.download_button("⬇️ Statistik als CSV", csv, file_name=f"gap_statistik_{index}_{datetime.date.today()}.csv",
                       mime="text/csv", key=P + "csv_stat")


# ---------------------------------------------------------------------------------------------------- Vergleich
def _vergleich(daten, gaps, kurse, definition):
    spalten = []
    for k in CODES:
        st_k = G.statistik(gaps[k])["alle"]
        u = G.uebersicht(gaps[k], kurse[k][0])
        naechst = [g for g in (u["naechstes_oben"], u["naechstes_unten"]) if g]
        spalten.append((k, st_k, u, min((g["entfernung_pct"] for g in naechst), default=None)))
    reihen = [("Offene Gaps (inkl. teilweise)", lambda st_k, u, n: str(u["offen"])),
              ("Offene Gap Ups", lambda st_k, u, n: str(u["offen_up"])),
              ("Offene Gap Downs", lambda st_k, u, n: str(u["offen_down"])),
              ("Ø Gap-Größe", lambda st_k, u, n: f"{_de(st_k.get('groesse_pct_mittel'), 2)} %"),
              ("Schließungsquote gesamt", lambda st_k, u, n: f"{_de(st_k.get('quote_gesamt'), 0)} %"),
              ("Ø Tage bis Schließung", lambda st_k, u, n: _de(st_k.get("dauer_mittel"), 1)),
              ("Nächstes offenes Gap", lambda st_k, u, n: "–" if n is None else f"{_de(n, 2)} % entfernt")]
    kopf = "".join(f"<th class='r'>{NAME[k]}</th>" for k, *_ in spalten)
    z = "".join(f"<tr><td>{t}</td>" + "".join(f"<td class='r'>{f(st_k, u, n) if st_k.get('anzahl') else '–'}</td>"
                                              for _, st_k, u, n in spalten) + "</tr>" for t, f in reihen)
    st.markdown(f"<div class='gp-tabwrap'><table class='gp-tab'><tr><th></th>{kopf}</tr>{z}</table></div>",
                unsafe_allow_html=True)
    st.caption("Größen indexübergreifend in Prozent, weil die Punktestände sehr unterschiedlich sind.")


# ---------------------------------------------------------------------------------------------------- Alerts
def _gesehen():
    try:
        g = json.loads(st.session_state.get(P + "gesehen_json") or "[]")
    except ValueError:
        g = []
    return g if isinstance(g, list) else []


def _als_gesehen(schluessel):
    g = _gesehen()
    st.session_state[P + "gesehen_json"] = json.dumps((g + [x for x in schluessel if x not in g])[-500:])


def _alerts(daten, gaps, kurse, definition):
    s = st.session_state
    for k, v in G.STANDARD_ALERTS.items():
        s.setdefault(P + "al_" + k, v)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    with sp[0]:
        st.toggle("Annäherung an ein offenes Gap", key=P + "al_naehe_an")
        st.number_input("… näher als (%)", 0.05, 10.0, step=0.1, format="%.2f", key=P + "al_naehe_pct")
        st.toggle("Index erreicht einen offenen Gap-Bereich", key=P + "al_erreicht_an")
        st.toggle("Gap teilweise geschlossen", key=P + "al_teilweise_an")
    with sp[1]:
        st.toggle("Gap vollständig geschlossen", key=P + "al_geschlossen_an")
        st.toggle("Neues Gap entstanden", key=P + "al_neu_an")
        st.toggle("Besonders großes Gap", key=P + "al_gross_an")
        st.number_input("… ab Größe (%)", 0.1, 10.0, step=0.1, format="%.1f", key=P + "al_gross_pct")
    einst = {k: s[P + "al_" + k] for k in G.STANDARD_ALERTS}
    a = G.alerts({k: daten[k]["gaps"] and G.mit_lage(list(daten[k]["gaps"]), kurse[k][0]) for k in CODES},
                 {k: v[0] for k, v in kurse.items()}, einst, _gesehen())
    neu = [x for x in a if x["neu"]]
    st.markdown(f"**{len(neu)} neue Meldungen** · {len(a) - len(neu)} bereits gesehen")
    for x in neu:
        st.warning("🔔 " + x["text"])
    if neu:
        st.button("Alle als gesehen markieren", key=P + "gesehen_btn", on_click=_als_gesehen,
                  args=([x["schluessel"] for x in neu],))
    with st.expander("Bereits gesehene Meldungen"):
        for x in [x for x in a if not x["neu"]]:
            st.caption(x["text"])
    st.caption(f"Meldungen erscheinen nur hier in der App, je Ereignis (Gap + Art) genau einmal. Neue, teilweise und "
               f"vollständig geschlossene Gaps werden für die letzten {G.ALERT_TAGE} Tage gemeldet; Annäherung und "
               "Erreichen beziehen sich auf den aktuellen Stand.")
