"""Fear & Greed Monitor (Menuepunkt "Fear & Greed") - Oberflaeche. Rechnungen: fear_greed.py.

Aufbau: Gesamtstimmung -> acht Karten (Wert, Farbskala, Veraenderung, Sparkline) -> Detailansicht (Verlauf
7/30/90/365 Tage, Faktoren der eigenen Scores) -> Vergleich -> Warnungen (nur in der App, je Benutzer gemerkt).
h = {"sentiment": () -> sentiment.json, "ohlc": () -> ohlc.json, "abrufen": () -> {"cnn", "crypto"} (Refresh)}
"""
import datetime
import html
import json
import time
from zoneinfo import ZoneInfo

import streamlit as st

import fear_greed as F
import ui_stil as UI

P = "fg_"
BERLIN = ZoneInfo("Europe/Berlin")
NAMEN = {mid: name for mid, name, _, _ in F.MAERKTE}
ZEITRAEUME = {"7 Tage": 7, "30 Tage": 30, "90 Tage": 90, "1 Jahr": 365, "3 Jahre": 3 * 365, "5 Jahre": 5 * 365,
              "Max": 100 * 365}
ART_BADGE = {"extern": ("Extern", "fg-b-ext"), "eigen": ("Eigener Score", "fg-b-eig"), "proxy": ("Proxy", "fg-b-pro"),
             "fehlt": ("n. v.", "fg-b-nv")}
REFRESH_ABSTAND_SEK = 60
KURZ = {"fehlt": "Keine verlässliche frei nutzbare Quelle – Details unten."}

CSS = """<style>
.fg-kopf { display:flex; gap:12px; align-items:center; margin:2px 0 8px; }
.fg-kopf .fg-sym { font-size:1.35rem; width:38px; height:38px; border-radius:10px; background:#252628;
    display:flex; align-items:center; justify-content:center; }
.fg-kopf b { font-size:1.05rem; color:#ffffff; } .fg-kopf div div { font-size:.8rem; color:#A9ACB0; }
.fg-gesamt { border:1px solid rgba(124,156,255,.45); border-radius:16px; padding:12px 16px; margin:4px 0 10px;
    background:rgba(124,156,255,.06); display:grid; grid-template-columns: 1.3fr 1fr; gap:10px 18px; }
.fg-gesamt .fg-l { font-size:.72rem; letter-spacing:.5px; text-transform:uppercase; color:#A9ACB0; }
.fg-gesamt .fg-gw { font-size:1.9rem; font-weight:800; line-height:1.1; font-variant-numeric:tabular-nums; }
.fg-zaehl { display:flex; gap:8px; flex-wrap:wrap; margin-top:4px; }
.fg-chip { font-size:.8rem; font-weight:700; padding:3px 10px; border-radius:999px; background:#1F2430; color:#E8ECF6; }
.fg-raster { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin:6px 0 8px; }
@media (max-width: 1100px) { .fg-raster { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width: 640px) { .fg-gesamt { grid-template-columns:1fr; } .fg-raster { gap:8px; } }
.fg-karte { border:1px solid rgba(255,255,255,.12); border-radius:14px; padding:10px 12px; background:rgba(255,255,255,.03);
    min-width:0; }
.fg-karte .fg-name { font-size:.82rem; font-weight:700; color:#E8ECF6; display:flex; justify-content:space-between;
    gap:6px; align-items:center; }
.fg-badge { font-size:.62rem; font-weight:700; padding:1px 6px; border-radius:999px; white-space:nowrap; }
.fg-b-ext { background:#1E2A44; color:#9DB4FF; } .fg-b-eig { background:#20332B; color:#6EE7B7; }
.fg-b-pro { background:#3D2A0F; color:#FBBF24; } .fg-b-nv { background:#2A2F3A; color:#A9ACB0; }
.fg-wert { font-size:1.7rem; font-weight:800; line-height:1.15; font-variant-numeric:tabular-nums; margin-top:2px; }
.fg-kat { font-size:.78rem; font-weight:700; }
.fg-skala { position:relative; height:7px; border-radius:4px; margin:6px 0 4px;
    background:linear-gradient(90deg, #EF4444 0 25%, #F97316 25% 45%, #EAB308 45% 56%, #84CC16 56% 76%, #22C55E 76%); }
.fg-skala span { position:absolute; top:-4px; width:4px; height:15px; border-radius:2px; background:#ffffff;
    box-shadow:0 0 0 1px #0B0F1A; transform:translateX(-2px); }
.fg-zeile { display:flex; justify-content:space-between; align-items:flex-end; gap:6px; }
.fg-aend { font-size:.78rem; font-weight:700; white-space:nowrap; }
.fg-pos { color:#34D399; } .fg-neg { color:#F87171; } .fg-neu { color:#A9ACB0; }
.fg-meta { font-size:.68rem; color:#A9ACB0; margin-top:3px; line-height:1.3; }
.fg-alt { color:#FBBF24; font-weight:700; }
.fg-leer { font-size:1rem; color:#A9ACB0; font-weight:700; margin:8px 0 6px; }
.fg-tab { width:100%; border-collapse:collapse; font-size:.85rem; }
.fg-tab th { text-align:left; color:#A9ACB0; font-weight:600; padding:5px 8px; border-bottom:1px solid rgba(255,255,255,.12); }
.fg-tab td { padding:5px 8px; color:#E8ECF6; border-bottom:1px solid rgba(255,255,255,.06); }
.fg-tab td.r, .fg-tab th.r { text-align:right; font-variant-numeric:tabular-nums; }
.st-key-fg_kopfzeile { justify-content: space-between; flex-wrap: nowrap !important; }
.st-key-fg_kopfzeile > div:first-child { flex: 1 1 auto !important; min-width: 0; }
.st-key-fg_kopfzeile [data-testid="stButton"] { flex: 0 0 auto !important; width: auto !important; }
</style>"""


def _de(x, n=1):
    return "–" if x is None else f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _zeit_text(z):
    if isinstance(z, datetime.datetime):
        return z.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M") + " Uhr"
    if isinstance(z, datetime.date):
        return "Schluss " + z.strftime("%d.%m.%Y")
    return "–"


def _datum_de(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(iso)


def _jetzt():
    return datetime.datetime.now(BERLIN)


# ---------------------------------------------------------------------------------------------------- Daten
def _daten(h):
    try:
        s = h["sentiment"]() or {}
    except Exception:
        s = {}
    try:
        o = h["ohlc"]() or {}
    except Exception:
        o = {}
    frisch = st.session_state.get(P + "frisch") or {}
    if frisch:
        q = dict(((s.get("quellen") or {}) if isinstance(s, dict) else {}))
        q.update(frisch)
        s = {"stand": (s or {}).get("stand"), "quellen": q}
    return s, o


@st.cache_data(ttl=86400, show_spinner="Berechne die Verläufe der eigenen Scores …", max_entries=3)
def _eigene(_o, o_key):
    """Score-Verlaeufe seit 2016 - teuer, aendert sich nur mit neuen Tageskerzen (o_key = Datenstand)."""
    return F.eigene_verlaeufe(_o)


@st.cache_data(ttl=600, show_spinner=False, max_entries=8)
def _karten(_s, _o, s_key, o_key, zeit_key):
    """Karten fuer den aktuellen Stand (die eigenen Verlaeufe kommen aus dem Zwischenspeicher)."""
    return F.karten(_s, _o, datetime.datetime.fromisoformat(zeit_key), eigene=_eigene(_o, o_key))


def _refresh(h):
    s = st.session_state
    if time.time() - s.get(P + "refresh_zeit", 0) < REFRESH_ABSTAND_SEK:
        s[P + "meldung"] = "Die Daten wurden gerade erst aktualisiert."
        return
    s[P + "refresh_zeit"] = time.time()
    try:
        neu = h["abrufen"]() or {}
    except Exception:
        neu = {}
    stand = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    frisch = dict(s.get(P + "frisch") or {})
    frisch.update({k: dict(v, ok=stand) for k, v in neu.items() if v})
    s[P + "frisch"] = frisch
    s[P + "meldung"] = (f"Aktualisiert: {', '.join(F.QUELLEN_TEXT[k] for k, v in neu.items() if v)}."
                        if any(neu.values()) else "Aktualisierung gerade nicht möglich – es gelten die zuletzt "
                                                  "gespeicherten Werte.")


@st.fragment(run_every=600)
def _auto(h):
    """Alle 10 Minuten: hat der Kurs-Agent neue Werte abgelegt? -> Seite neu rechnen."""
    try:
        stand = (h["sentiment"]() or {}).get("stand")
    except Exception:
        return
    s = st.session_state
    if s.get(P + "stand_gesehen") is None:
        s[P + "stand_gesehen"] = stand
    elif stand and stand != s[P + "stand_gesehen"]:
        s[P + "stand_gesehen"] = stand
        st.rerun(scope="app")


# ---------------------------------------------------------------------------------------------------- Seite
def seite(h):
    st.markdown(CSS, unsafe_allow_html=True)
    s = st.session_state
    for k in [k for k in list(s.keys()) if str(k) in (P + "detail", P + "zeitraum", P + "vergleich", P + "aktiv")]:
        s[k] = s[k]                                    # Auswahl behalten, auch wenn ein Lauf sie nicht zeichnet
    if s.get(P + "meldung"):
        st.toast(s.pop(P + "meldung"))
    _auto(h)
    with st.container(horizontal=True, vertical_alignment="center", key="fg_kopfzeile"):
        st.markdown('<div class="fg-kopf"><span class="fg-sym">🌡️</span><div><b>Fear &amp; Greed Monitor</b>'
                    '<div>Marktstimmung von Aktien, Krypto und Indizes auf einen Blick</div></div></div>',
                    unsafe_allow_html=True)
        st.button("🔄", key=P + "refresh_btn", on_click=_refresh, args=(h,), help="Externe Werte jetzt abrufen")
    sent, ohlc = _daten(h)
    jetzt = _jetzt()
    zeit_key = jetzt.replace(minute=jetzt.minute // 10 * 10, second=0, microsecond=0).isoformat()
    kl = _karten(sent, ohlc, json.dumps((sent or {}).get("quellen") or {}, sort_keys=True, default=str)[:20000],
                 str((ohlc or {}).get("stand")), zeit_key)
    if not any(k["wert"] is not None for k in kl):
        st.warning("Noch keine Stimmungsdaten vorhanden. Der Kurs-Agent legt sie bei seinem nächsten Lauf ab "
                   "(etwa alle 30 Minuten) – oder oben 🔄 tippen.")
    _gesamt(F.gesamt(kl))
    _warn_banner(kl)
    st.markdown('<div class="fg-raster">' + "".join(_karte(k) for k in kl) + "</div>", unsafe_allow_html=True)
    st.caption("Farben einheitlich: 0–24 Extreme Angst · 25–44 Angst · 45–55 Neutral · 56–75 Gier · 76–100 Extreme "
               "Gier. In Klammern die Originalkategorie der Quelle. Eigene Scores sind keine offiziellen "
               "Fear-&-Greed-Indizes.")
    _detail(kl)
    _vergleich(kl)
    _warnungen_einstellen()
    st.caption("Quellen: CNN Business (Fear & Greed Index), Alternative.me (Crypto Fear & Greed Index), Yahoo Finance "
               "(Tageskerzen der Cash-Indizes für die eigenen Scores). Keine Anlageberatung.")


def _gesamt(g):
    sc = g["score"]
    kat, farbe = F.kategorie(sc)
    aend = g["aenderung"]
    st.markdown(
        '<div class="fg-gesamt"><div><div class="fg-l">Dashboard-Sentiment-Score</div>'
        f'<div class="fg-gw" style="color:{farbe or "#A9ACB0"}">{_de(sc)}'
        f'<span style="font-size:.95rem;font-weight:700"> {kat or "Nicht verfügbar"}</span></div>'
        + (f'<div class="fg-skala"><span style="left:{sc}%"></span></div>' if sc is not None else "")
        + f'<div class="fg-meta">Eigener Durchschnitt aus {g["anzahl"]} unabhängigen Indikatoren (ohne Proxy) – '
          'kein offizieller Fear-&amp;-Greed-Index.</div></div>'
        '<div><div class="fg-l">Stimmung der Märkte</div><div class="fg-zaehl">'
        f'<span class="fg-chip" style="color:#F87171">Angst {g["angst"]}</span>'
        f'<span class="fg-chip" style="color:#EAB308">Neutral {g["neutral"]}</span>'
        f'<span class="fg-chip" style="color:#34D399">Gier {g["gier"]}</span></div>'
        f'<div class="fg-meta">Ø Veränderung zum Vortag: <b class="{_klasse(aend)}">{_aend_text(aend)}</b><br>'
        f'Letzte Aktualisierung: {_zeit_text(g["letzte"])}</div></div></div>', unsafe_allow_html=True)


def _klasse(x):
    return "fg-neu" if x is None or abs(x) < 0.05 else ("fg-pos" if x > 0 else "fg-neg")


def _aend_text(x):
    if x is None:
        return "–"
    pfeil = "▲" if x > 0.05 else "▼" if x < -0.05 else "■"
    return f"{pfeil} {'+' if x > 0 else ''}{_de(x)}"


def _sparkline(verlauf, farbe, n=30):
    pkt = [w for _, w in verlauf[-n:]]
    if len(pkt) < 2:
        return ""
    b, hgt = 100, 26
    xs = [i * b / (len(pkt) - 1) for i in range(len(pkt))]
    linie = " ".join(f"{x:.1f},{hgt - w / 100 * hgt:.1f}" for x, w in zip(xs, pkt))
    return (f'<svg viewBox="0 0 {b} {hgt}" width="96" height="26" preserveAspectRatio="none" aria-hidden="true">'
            f'<line x1="0" y1="{hgt / 2}" x2="{b}" y2="{hgt / 2}" stroke="#3A4150" stroke-width=".6" stroke-dasharray="2 2"/>'
            f'<polyline points="{linie}" fill="none" stroke="{farbe}" stroke-width="1.8" '
            f'vector-effect="non-scaling-stroke"/></svg>')


def _karte(k):
    titel, cls = ART_BADGE[k["art"]]
    kopf = (f'<div class="fg-name"><span>{html.escape(k["name"])}</span>'
            f'<span class="fg-badge {cls}">{titel}</span></div>')
    if k["wert"] is None:
        return (f'<div class="fg-karte">{kopf}<div class="fg-leer">Nicht verfügbar</div>'
                f'<div class="fg-meta">{html.escape(KURZ.get(k["art"]) or k["hinweis"] or "Noch keine Daten.")}'
                '</div></div>')
    farbe = k["farbe"]
    orig = f' ({html.escape(k["original"])})' if k["original"] and k["original"] != k["kategorie"] else ""
    alt = '<span class="fg-alt">Veraltete Daten · </span>' if k["status"] == "veraltet" else ""
    hinweis = "<br>Proxy: Crypto Fear &amp; Greed – zählt nicht in der Gesamtstimmung." if k["art"] == "proxy" else ""
    return (f'<div class="fg-karte">{kopf}<div class="fg-wert" style="color:{farbe}">{_de(k["wert"], 0)}</div>'
            f'<div class="fg-kat" style="color:{farbe}">{k["kategorie"]}{orig}</div>'
            f'<div class="fg-skala"><span style="left:{k["wert"]}%"></span></div>'
            f'<div class="fg-zeile"><span class="fg-aend {_klasse(k["aenderung"])}">{_aend_text(k["aenderung"])}'
            f' <span class="fg-neu" style="font-weight:400">ggü. Vortag</span></span>{_sparkline(k["verlauf"], farbe)}</div>'
            f'<div class="fg-meta">{alt}{_zeit_text(k["zeit"])} · {html.escape(k["quelle"])}{hinweis}</div></div>')


# ---------------------------------------------------------------------------------------------------- Detail/Vergleich
def _linien_chart(serien, hoehe=300, baender=True, key=None):
    import plotly.graph_objects as go
    fig = go.Figure()
    if baender:
        unten = 0
        for grenze, name, farbe in F.KATEGORIEN:
            fig.add_hrect(y0=unten, y1=min(grenze, 100), fillcolor=farbe, opacity=0.07, line_width=0)
            unten = grenze
    for name, punkte in serien:
        fig.add_scatter(x=[d for d, _ in punkte], y=[w for _, w in punkte], mode="lines", name=name,
                        hovertemplate=f"{name}: %{{y:.1f}}<br>%{{x|%d.%m.%Y}}<extra></extra>")
    fig.update_layout(height=hoehe, margin=dict(l=10, r=10, t=10, b=30), yaxis=dict(range=[0, 100], title="0–100"),
                      hovermode="x unified", showlegend=len(serien) > 1, legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(UI.chart_stil(fig), use_container_width=True, config={"displayModeBar": False}, key=key)


def _detail(kl):
    st.markdown("**Detailansicht**")
    s = st.session_state
    if s.get(P + "detail") not in NAMEN:
        s[P + "detail"] = "us"
    mid = st.pills("Markt", list(NAMEN), key=P + "detail", format_func=NAMEN.get, label_visibility="collapsed") or "us"
    k = next(x for x in kl if x["id"] == mid)
    if s.get(P + "zeitraum") not in ZEITRAEUME:
        s[P + "zeitraum"] = "30 Tage"
    zr = st.segmented_control("Zeitraum", list(ZEITRAEUME), key=P + "zeitraum", label_visibility="collapsed") or "30 Tage"
    z = F.zeitraum(k["verlauf"], ZEITRAEUME[zr])
    if not z:
        st.info(f"{k['name']}: keine historischen Daten verfügbar. " + (k["hinweis"] or ""))
        return
    st.markdown(f'<table class="fg-tab"><tr><th>Aktuell</th><th>Höchster Wert</th><th>Niedrigster Wert</th>'
                f'<th>Veränderung im Zeitraum</th></tr><tr><td>{_de(z["aktuell"])} ({F.kategorie(z["aktuell"])[0]})</td>'
                f'<td>{_de(z["hoch"])}</td><td>{_de(z["tief"])}</td><td class="{_klasse(z["aenderung"])}">'
                f'{_aend_text(z["aenderung"])}</td></tr></table>', unsafe_allow_html=True)
    _linien_chart([(k["name"], z["punkte"])], key=P + "detail_chart")
    luecke = ""
    if zr != "Max" and k["verlauf"] and z["von"] == k["verlauf"][0][0] and ZEITRAEUME[zr] > 400:
        luecke = f" · Daten liegen erst ab {_datum_de(z['von'])} vor"
    st.caption(f"{len(z['punkte'])} Datenpunkte vom {_datum_de(z['von'])} bis {_datum_de(z['bis'])}{luecke} · "
               f"Quelle: {k['quelle']}"
               + (" · nur Handelstage" if k["art"] == "eigen" else ""))
    if k["art"] == "eigen" and k.get("faktoren"):
        f = k["faktoren"]
        roh_fmt = {"rsi": lambda x: _de(x), "sma50": lambda x: _de(x, 2) + " %", "sma200": lambda x: _de(x, 2) + " %",
                   "mom20": lambda x: _de(x, 2) + " %", "vola": lambda x: _de(x, 2) + "×"}
        zeilen = "".join(f'<tr><td>{t}</td><td class="r">{g} %</td><td class="r">{roh_fmt[key](f["roh"][key])}</td>'
                         f'<td class="r">{_de(f["teil"][key])}</td><td>{html.escape(norm)}</td></tr>'
                         for key, t, g, norm in F.FAKTOREN)
        st.markdown('<div style="overflow-x:auto"><table class="fg-tab"><tr><th>Faktor</th><th class="r">Gewicht</th>'
                    '<th class="r">Rohwert</th><th class="r">Teilwert</th><th>Normierung</th></tr>' + zeilen
                    + "</table></div>", unsafe_allow_html=True)
        st.caption("Eigener Sentiment-Score = gewichteter Mittelwert der Teilwerte (0–100) aus den Tageskerzen des "
                   "Cash-Index. Berechnet nur, wenn alle Faktoren aus mindestens "
                   f"{F.MIN_KERZEN} Handelstagen vorliegen. Kein offizieller Fear-&-Greed-Index.")
    elif k["hinweis"]:
        st.caption(k["hinweis"])


def _vergleich(kl):
    with st.expander("⚖️ Märkte vergleichen"):
        mit = [k for k in kl if k["verlauf"] and k["art"] != "proxy"]
        if len(mit) < 2:
            st.caption("Für einen Vergleich liegen noch zu wenige Verläufe vor.")
            return
        s = st.session_state
        s.setdefault(P + "vergleich", [k["id"] for k in mit[:3]])
        wahl = st.multiselect("Märkte", [k["id"] for k in mit], key=P + "vergleich", format_func=NAMEN.get)
        zr = st.segmented_control("Zeitraum (Vergleich)", list(ZEITRAEUME), default="90 Tage", key=P + "vgl_zr",
                                  label_visibility="collapsed") or "90 Tage"
        serien = []
        for k in mit:
            if k["id"] in wahl:
                z = F.zeitraum(k["verlauf"], ZEITRAEUME[zr])
                if z:
                    serien.append((k["name"], z["punkte"]))
        if serien:
            _linien_chart(serien, hoehe=320, baender=False, key=P + "vgl_chart")
            st.caption("Alle Werte auf der Skala 0–100. Externe Indizes und eigene Scores sind unterschiedlich "
                       "berechnet – der Vergleich zeigt Richtung und Lage, keine identische Messgröße.")


# ---------------------------------------------------------------------------------------------------- Warnungen
def _regeln():
    try:
        r = json.loads(st.session_state.get(P + "regeln_json") or "null")
    except ValueError:
        r = None
    return r if isinstance(r, list) else [dict(x) for x in F.STANDARD_REGELN]


def _gesehen():
    try:
        g = json.loads(st.session_state.get(P + "gesehen_json") or "[]")
    except ValueError:
        g = []
    return g if isinstance(g, list) else []


def _als_gesehen(schluessel):
    g = _gesehen()
    st.session_state[P + "gesehen_json"] = json.dumps((g + [x for x in schluessel if x not in g])[-200:])


def _warn_banner(kl):
    if not st.session_state.get(P + "aktiv", True):
        return
    w = F.warnungen(kl, _regeln(), _gesehen())
    neu = [x for x in w if x["neu"]]
    for x in neu:
        st.warning("🔔 " + x["text"])
    if neu:
        st.button("Gesehen – nicht erneut anzeigen", key=P + "gesehen_btn", on_click=_als_gesehen,
                  args=([x["schluessel"] for x in neu],))


def _warnungen_einstellen():
    import pandas as pd
    with st.expander("🔔 Warnungen einstellen"):
        st.session_state.setdefault(P + "aktiv", True)
        st.toggle("Warnungen anzeigen", key=P + "aktiv")
        maerkte = ["alle"] + [mid for mid, _, art, _ in F.MAERKTE if art in ("extern", "eigen")]
        df = pd.DataFrame(_regeln())
        for spalte, std in (("markt", "alle"), ("art", "unter"), ("schwelle", 25), ("aktiv", True)):
            if spalte not in df:
                df[spalte] = std
        bearbeitet = st.data_editor(
            df[["markt", "art", "schwelle", "aktiv"]], num_rows="dynamic", hide_index=True, key=P + "regeln_editor",
            use_container_width=True,
            column_config={"markt": st.column_config.SelectboxColumn("Markt", options=maerkte, required=True),
                           "art": st.column_config.SelectboxColumn("Bedingung", options=list(F.ART_TEXT), required=True),
                           "schwelle": st.column_config.NumberColumn("Schwelle", min_value=0, max_value=100, step=1),
                           "aktiv": st.column_config.CheckboxColumn("Aktiv")})
        regeln = [{"id": f"r{i + 1}", "markt": r["markt"], "art": r["art"], "schwelle": float(r["schwelle"] or 0),
                   "aktiv": bool(r["aktiv"])} for i, r in enumerate(bearbeitet.to_dict("records"))
                  if r.get("markt") and r.get("art")]
        neu = json.dumps(regeln)
        if neu != st.session_state.get(P + "regeln_json"):
            st.session_state[P + "regeln_json"] = neu
        st.caption("Bedingungen: unter = Wert fällt unter die Schwelle, ueber = steigt darüber, aenderung = ändert sich "
                   "innerhalb eines Tages um mehr als die Schwelle (Punkte). Jede Warnung erscheint je Ereignis nur "
                   "einmal. Der Bitcoin-Proxy löst keine eigenen Warnungen aus. Warnungen erscheinen nur hier in der App.")
