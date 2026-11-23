"""Opening-Gaps im Gap Analyzer - Oberflaeche (Tabs "Opening-Gaps heute", "Opening-Gap-Historie", Statistik-,
Chart- und Alert-Teile). Rechnungen: opening_gaps.py; Daten: Tageskerzen (ohlc.json), gespeicherte Intraday-Zeiten
(opening_intraday.json, Kurs-Agent) und - nur waehrend der Handelszeit und nur in dieser Sitzung - frische
1-Minuten-Kerzen von Yahoo (Cash-Index, regulaere Handelszeit)."""
import datetime
import html
from zoneinfo import ZoneInfo

import streamlit as st

import boersenkalender as BK
import markt_daten as MD
import opening_gaps as OG
import ui_stil as UI

P = "gap_og_"
BERLIN = ZoneInfo("Europe/Berlin")
LIVE_SEKUNDEN = 60

CSS = """<style>
.og-raster { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin:6px 0 8px; }
@media (max-width: 1100px) { .og-raster { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width: 640px) { .og-raster { grid-template-columns:1fr; } }
.og-karte { border:1px solid rgba(255,255,255,.12); border-left-width:5px; border-radius:14px; padding:10px 12px;
    background:rgba(255,255,255,.03); min-width:0; }
.og-karte.up { border-left-color:#22C55E; } .og-karte.down { border-left-color:#EF4444; }
.og-karte.kein { border-left-color:#6B7280; }
.og-kopf { display:flex; justify-content:space-between; gap:6px; align-items:baseline; flex-wrap:wrap; }
.og-name { font-size:.85rem; font-weight:700; color:#E8ECF6; }
.og-status { font-size:.7rem; font-weight:700; padding:2px 8px; border-radius:10px; border:1px solid currentColor; }
.og-gross { font-size:1.35rem; font-weight:800; font-variant-numeric:tabular-nums; margin-top:4px; }
.og-gross.up { color:#34D399; } .og-gross.down { color:#F87171; } .og-gross.kein { color:#C9CED6; }
.og-bahn { height:7px; border-radius:4px; background:rgba(127,127,127,.25); overflow:hidden; margin:6px 0 4px; }
.og-bahn > div { height:100%; border-radius:4px; background:#FBBF24; }
.og-werte { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:2px 12px; font-size:.76rem;
    color:#A9ACB0; font-variant-numeric:tabular-nums; }
.og-werte b { color:#ffffff; font-weight:700; float:right; }
.og-meta { font-size:.68rem; color:#A9ACB0; margin-top:6px; }
.og-vorl { color:#FBBF24; font-weight:700; }
</style>"""


def _de(x, n=1):
    return "–" if x is None else f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return "–"


def zeit_text(datum, hhmm, boerse):
    """Uhrzeit in Boersenzeit -> 'HH:MM Uhr (MEZ/MESZ)', bei US-Indizes zusaetzlich die New Yorker Zeit."""
    if not hhmm or not datum:
        return None
    try:
        h, m = (int(x) for x in hhmm.split(":"))
        t = datetime.datetime.combine(datetime.date.fromisoformat(datum), datetime.time(h, m),
                                      BK.BOERSEN[boerse]["tz"])
    except (ValueError, KeyError):
        return hhmm
    b = t.astimezone(BERLIN)
    return f"{b:%H:%M} Uhr" + (f" ({hhmm} New York)" if boerse == "NYSE" else "")


def _dauer_text(g):
    if g["status"] == "heute":
        return f"{g['dauer_min']} Min." if g.get("dauer_min") is not None else "am selben Tag"
    if g["status"] == "spaeter":
        return f"{g['dauer_tage']} Handelstag(e)"
    return "–"


STATUS_FARBE = {"offen": "#F87171", "teilweise": "#FBBF24", "heute": "#34D399", "spaeter": "#34D399",
                "kein": "#A9ACB0"}


# ---------------------------------------------------------------------------------------------------- Daten
@st.cache_data(ttl=LIVE_SEKUNDEN - 5, show_spinner=False, max_entries=16)
def _live_abruf(_abruf, symbol, minute):
    """1-Minuten-Kerzen des laufenden bzw. letzten Handelstags (nur diese Sitzung, minute = Cache-Schluessel).
    _abruf: (symbol) -> markt_daten.intraday_abrufen-Ergebnis; kommt von der App (Tests ohne Netz)."""
    return _abruf(symbol)


def live_abruf_yahoo(symbol):
    import requests
    return MD.intraday_abrufen(symbol, requests.get, "1m", "1d")


def _boerse_heute(boerse, jetzt):
    return jetzt.astimezone(BK.BOERSEN[boerse]["tz"]).date()


def daten(ohlc, intraday_datei, codes, symbol_je, min_pct, jetzt, live=None):
    """Opening-Gaps je Index -> {kurz: {"gaps", "kerzen", "boerse", "live", "intraday", ...}}.
    live: Abruf-Funktion (symbol) -> Intraday-Daten oder None (dann nur gespeicherte Daten)."""
    idx = ((ohlc or {}).get("indizes") or {}) if isinstance(ohlc, dict) else {}
    gespeichert = ((intraday_datei or {}).get("indizes") or {}) if isinstance(intraday_datei, dict) else {}
    aus = {}
    for kurz in codes:
        sym = symbol_je[kurz]
        boerse = MD.INDEX_OHLC[sym][2]
        kerzen = (idx.get(sym) or {}).get("kerzen") or []
        tage = dict((gespeichert.get(kurz) or {}).get("tage") or {})
        live_info = None
        if live:
            try:
                e = _live_abruf(live, sym, jetzt.strftime("%Y-%m-%d %H:%M"))
            except Exception:                   # Live-Daten sind Zusatz - ohne sie gelten die gespeicherten
                e = None
            if e:
                # alle gelieferten Tage nach der letzten offiziellen Tageskerze (auch der letzte Handelstag, falls
                # der Kurs-Agent seine Tageskerze noch nicht abgelegt hat)
                letzte_k = kerzen[-1][0] if kerzen else ""
                neu = {t: z for t, z in MD.intraday_tage(e, kerzen, boerse, jetzt).items() if z and t > letzte_k}
                if neu:
                    tage = OG.intraday_zusammenfuehren(tage, neu)
                    live_info = neu[max(neu)]
        letzte = kerzen[-1][0] if kerzen else ""
        offene = sorted(d for d, z in tage.items() if d > letzte and z and z.get("kerze"))
        vorl = tage[offene[-1]]["kerze"] if offene else None
        gaps = OG.erkennen(kerzen, kurz, min_pct, intraday=tage, vorlaeufig=vorl)
        aus[kurz] = {"gaps": gaps, "kerzen": kerzen, "boerse": boerse, "symbol": sym, "intraday": tage,
                     "live": live_info, "abruf_intraday": (gespeichert.get(kurz) or {}).get("abruf"),
                     "letzte_kerze": letzte}
    return aus


def _datenart(d, g):
    """Echtzeit / verzoegert / Tagesdaten fuer den Eintrag g."""
    z = d["intraday"].get(g["datum"]) if g else None
    if z:
        art = z.get("datenart") or "verzoegert"
        verz = z.get("verzoegert_min")
        txt = OG.DATENART[art] + (f" (ca. {verz} Min.)" if art == "verzoegert" and verz else "")
        return txt + f" · {z.get('intervall') or '?'}-Kerzen"
    return OG.DATENART["tag"]


# ---------------------------------------------------------------------------------------------------- Tab: heute
def _karte(kurz, name, d, kurs, jetzt):
    name = html.escape(name)
    g = OG.heute(d["gaps"])
    if not g:
        return (f'<div class="og-karte kein"><div class="og-name">{name} ({kurz})</div>'
                '<div class="og-meta">Keine Tageskerzen vorhanden – es wird nichts geschätzt.</div></div>')
    OG.mit_kurs([g], kurs)
    typ = g["typ"]
    pfeil = "▲ Gap-up" if typ == "up" else "▼ Gap-down" if typ == "down" else "Kein Opening-Gap"
    farbe = STATUS_FARBE[g["status"]]
    vorl = '<span class="og-vorl">vorläufig</span> · ' if g["vorlaeufig"] else ""
    zeilen = [("Schluss Vortag", _de(g["schluss_vorher"], 2)), ("Eröffnung", _de(g["eroeffnung"], 2)),
              ("Hoch", _de(g["hoch"], 2)), ("Tief", _de(g["tief"], 2)),
              ("Gap (Pkt.)", _de(g["groesse"], 1)), ("Noch offen (Pkt.)", _de(g["rest"], 1) if typ != "kein" else "–"),
              ("Füllgrad", f"{_de(g['fuellgrad'], 0)} %" if typ != "kein" else "–"),
              ("Bis Schließung", "geschlossen" if g["status"] in ("heute", "spaeter") else
               "–" if g.get("entfernung") is None else f"{_de(g['entfernung'], 1)} Pkt. / {_de(g['entfernung_pct'], 2)} %")]
    zeit_b = zeit_text(g["datum"], g.get("beruehrt_zeit"), d["boerse"])
    zeit_g = zeit_text(g["datum"], g.get("geschlossen_zeit"), d["boerse"])
    if typ != "kein":
        zeilen.append(("Erste Berührung", zeit_b or (_datum(g["beruehrt"]) if g["beruehrt"] else "–")))
        zeilen.append(("Geschlossen", zeit_g or (_datum(g["geschlossen"]) if g["geschlossen"] else "–")))
    z = d["intraday"].get(g["datum"]) or {}
    stand = (f'{_datum(g["datum"])}, letzte Kerze {zeit_text(g["datum"], z.get("letzte_zeit"), d["boerse"])}'
             if z.get("letzte_zeit") else f"Tageskerze vom {_datum(g['datum'])}")
    status_text = OG.STATUS[g["status"]] if typ != "kein" else "–"
    werte = "".join(f"<div>{t}<b>{w}</b></div>" for t, w in zeilen)
    return (f'<div class="og-karte {typ}"><div class="og-kopf"><span class="og-name">{name} ({kurz})</span>'
            + (f'<span class="og-status" style="color:{farbe}">{status_text}</span>' if typ != "kein" else "")
            + f'</div><div class="og-gross {typ}">{pfeil} {"+" if g["groesse_pct"] > 0 else ""}{_de(g["groesse_pct"], 2)} %</div>'
            + (f'<div class="og-bahn" title="Füllgrad"><div style="width:{g["fuellgrad"]:.0f}%"></div></div>'
               if typ != "kein" else "")
            + f'<div class="og-werte">{werte}</div>'
            f'<div class="og-meta">{vorl}{_datenart(d, g)}<br>Stand: {stand}</div></div>')


def tab_heute(h, ohlc, codes, symbol_je, namen, kurse, min_pct):
    st.markdown(CSS, unsafe_allow_html=True)
    s = st.session_state
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    offen = [k for k in codes if BK.boerse_offen(MD.INDEX_OHLC[symbol_je[k]][2], jetzt)]
    s.setdefault(P + "live", True)
    abruf = h.get("live")
    live = abruf is not None and st.toggle(f"Live aktualisieren (alle {LIVE_SEKUNDEN} s während der Handelszeit)", key=P + "live",
                     help="Lädt 1-Minuten-Kerzen der Cash-Indizes direkt von Yahoo – nur in dieser Sitzung, nur zur "
                          "regulären Handelszeit, keine Futures/CFDs/vorbörslichen Kurse.")
    try:
        intra = h["intraday"]() if h.get("intraday") else {}
    except Exception:
        intra = {}

    def zeichnen():
        jetzt2 = datetime.datetime.now(datetime.timezone.utc)
        d = daten(ohlc, intra, codes, symbol_je, min_pct, jetzt2, live=abruf if live else None)
        karten = "".join(_karte(k, namen[k], d[k], (d[k]["live"] or {}).get("kerze", [None] * 5)[4] or kurse[k][0],
                                jetzt2) for k in codes)
        st.markdown('<div class="og-raster">' + karten + "</div>", unsafe_allow_html=True)
        st.caption(f"Aktualisiert {jetzt2.astimezone(BERLIN):%H:%M:%S} Uhr · "
                   + (f"Handel läuft: {', '.join(namen[k] for k in offen)}" if offen else "Alle vier Börsen geschlossen"))

    if live and offen:
        st.fragment(run_every=LIVE_SEKUNDEN)(zeichnen)()
    else:
        zeichnen()
    st.caption("Opening-Gap = Eröffnung heute − Schluss am vorherigen Handelstag (offizielle Cash-Index-Kurse). "
               f"Mindestgröße {_de(min_pct, 2)} %. Grün = Gap-up, Rot = Gap-down. Geschlossen, sobald der Kurs den "
               "Vortagesschluss wieder erreicht; auch am selben Tag geschlossene Gaps bleiben hier und in der Historie. "
               "Uhrzeiten nur aus Intraday-Daten (Genauigkeit = Kerzenintervall); mit reinen Tagesdaten steht nur das "
               "Datum da. „vorläufig“ = laufender oder gerade beendeter Handelstag, noch ohne offizielle Tageskerze.")


# ---------------------------------------------------------------------------------------------------- Tab: Historie
def _zeilen(gaps, namen):
    return [{"Datum": g["datum"], "Index": g["index"], "Typ": "Gap-up" if g["typ"] == "up" else
             "Gap-down" if g["typ"] == "down" else "kein",
             "Schluss Vortag": round(g["schluss_vorher"], 2), "Eröffnung": round(g["eroeffnung"], 2),
             "Gap Pkt.": round(g["groesse"], 2), "Gap %": round(g["groesse_pct"], 3),
             "Max. Füllgrad %": round(g["fuellgrad"], 1), "Status": OG.STATUS[g["status"]],
             "Geschlossen am": g["geschlossen"] or "", "Uhrzeit": g.get("geschlossen_zeit") or "",
             "Zeit bis Schließung": _dauer_text(g), "vorläufig": "ja" if g["vorlaeufig"] else "", "ID": g["id"]}
            for g in gaps]


def tab_historie(h, ohlc, codes, symbol_je, namen, min_pct, exporte):
    import pandas as pd
    s = st.session_state
    try:
        intra = h["intraday"]() if h.get("intraday") else {}
    except Exception:
        intra = {}
    d = daten(ohlc, intra, codes, symbol_je, min_pct, datetime.datetime.now(datetime.timezone.utc))
    alle = [g for k in codes for g in d[k]["gaps"]]
    jahre = OG.jahre(alle)
    sp = st.columns(4) if not UI.ist_smartphone() else [st.container() for _ in range(4)]
    s.setdefault(P + "h_jahr", jahre[0] if jahre else "Alle")
    jahr = sp[0].selectbox("Jahr", ["Alle"] + jahre, key=P + "h_jahr")
    s.setdefault(P + "h_index", list(codes))
    idx = sp[1].multiselect("Index", codes, key=P + "h_index", format_func=namen.get)
    s.setdefault(P + "h_typ", ["up", "down"])
    typ = sp[2].multiselect("Richtung", ["up", "down"], key=P + "h_typ",
                            format_func=lambda x: "Gap-up" if x == "up" else "Gap-down")
    s.setdefault(P + "h_status", [k for k in OG.STATUS if k != "kein"])
    stat = sp[3].multiselect("Status", [k for k in OG.STATUS if k != "kein"], key=P + "h_status",
                             format_func=OG.STATUS.get)
    liste = [g for g in alle if g["typ"] != "kein" and g["index"] in (idx or codes) and g["typ"] in (typ or ["up", "down"])
             and g["status"] in (stat or OG.STATUS) and (jahr == "Alle" or g["datum"].startswith(jahr))]
    liste.sort(key=lambda g: (g["datum"], g["index"]), reverse=True)
    st.markdown(f"**{len(liste)} Opening-Gaps** (≥ {_de(min_pct, 2)} %)")
    if not liste:
        st.markdown('<div class="gp-leer">Keine Opening-Gaps für diese Auswahl.</div>', unsafe_allow_html=True)
        return
    df = pd.DataFrame(_zeilen(liste, namen))
    st.dataframe(df, hide_index=True, width="stretch", height=min(560, 38 + 35 * len(df)),
                 column_config={"ID": None, "Max. Füllgrad %": st.column_config.ProgressColumn(
                     "Max. Füllgrad", min_value=0, max_value=100, format="%.0f %%"),
                     "Gap %": st.column_config.NumberColumn("Gap %", format="%.2f %%")}, key=P + "h_tab")
    exporte(df.assign(**{"": ""}), "opening_gaps_historie")
    st.caption("Ein Eintrag je Handelstag mit Opening-Gap – auch am selben Tag geschlossene bleiben dauerhaft. "
               "Uhrzeiten gibt es nur für Tage mit Intraday-Daten (seit Einführung, Yahoo liefert rückwirkend nur "
               "wenige Wochen); sonst nur das Datum.")


# ---------------------------------------------------------------------------------------------------- Statistik
def statistik(h, ohlc, codes, symbol_je, namen, min_pct):
    s = st.session_state
    try:
        intra = h["intraday"]() if h.get("intraday") else {}
    except Exception:
        intra = {}
    d = daten(ohlc, intra, codes, symbol_je, min_pct, datetime.datetime.now(datetime.timezone.utc))
    jahre = OG.jahre([g for k in codes for g in d[k]["gaps"]])
    s.setdefault(P + "s_jahr", "Alle")
    jahr = st.selectbox("Zeitraum", ["Alle"] + jahre, key=P + "s_jahr",
                        format_func=lambda j: "Alle verfügbaren Jahre" if j == "Alle" else j)
    spalten = []
    for k in codes:
        gaps = d[k]["gaps"] if jahr == "Alle" else OG.filtern(d[k]["gaps"], jahr=jahr, mit_kein=True)
        spalten.append((k, OG.statistik(gaps)["alle"]))

    def quote(x, n):
        q = (x.get("quoten") or {}).get(n)
        return "–" if not q or q[0] is None else f"{_de(q[0], 0)} % (n={q[1]})"

    def groesst(g):
        return "–" if not g else f"{_de(g['groesse_pct'], 2)} % ({_datum(g['datum'])})"
    reihen = [("Opening-Gaps", lambda x: str(x["anzahl"])), ("Gap-ups", lambda x: str(x["up"])),
              ("Gap-downs", lambda x: str(x["down"])),
              ("Ø Größe", lambda x: f"{_de(x['pct_mittel'], 2)} % / {_de(x['pkt_mittel'], 1)} Pkt."),
              ("Größtes Gap-up", lambda x: groesst(x["groesstes_up"])),
              ("Größtes Gap-down", lambda x: groesst(x["groesstes_down"])),
              ("Am selben Tag geschlossen", lambda x: quote(x, 0)),
              ("In ≤ 5 Handelstagen geschlossen", lambda x: quote(x, 5)),
              ("In ≤ 20 Handelstagen geschlossen", lambda x: quote(x, 20)),
              ("Ø Handelstage bis Schließung", lambda x: _de(x["dauer_tage_mittel"], 1)),
              ("Ø Minuten bis Schließung (selber Tag)", lambda x: f"{_de(x['dauer_min_mittel'], 0)} (n={x['mit_minuten']})"
               if x["mit_minuten"] else "– (keine Intraday-Daten)"),
              ("Noch offen", lambda x: str(x["noch_offen"]))]
    kopf = "".join(f"<th class='r'>{namen[k]}</th>" for k, _ in spalten)
    z = "".join(f"<tr><td>{t}</td>" + "".join(f"<td class='r'>{f(x) if x.get('anzahl') else '–'}</td>"
                                              for _, x in spalten) + "</tr>" for t, f in reihen)
    st.markdown(f"<div class='gp-tabwrap'><table class='gp-tab'><tr><th>Opening-Gaps</th>{kopf}</tr>{z}</table></div>",
                unsafe_allow_html=True)
    st.caption(f"Nur endgültige Tage (ohne den laufenden). Mindestgröße {_de(min_pct, 2)} %. Quoten für 5 und 20 "
               "Handelstage nur über Gaps, die mindestens so lange beobachtet werden konnten (n) – noch offene Gaps "
               "gelten nicht als „nie geschlossen“.")


# ---------------------------------------------------------------------------------------------------- Chart
def chart_zonen(fig, d, x0, x1, auswahl_datum=None):
    """Opening-Gaps im sichtbaren Zeitraum als schmale Zonen je Tag (Vortagesschluss bis Eroeffnung), gefuellter Teil
    blass, offener Teil kraeftig; am ausgewaehlten/letzten Tag Linien fuer Vortagesschluss und Eroeffnung."""
    sicht = [g for g in d["gaps"] if g["typ"] != "kein" and x0 <= g["datum"] <= x1]
    for g in sicht:
        farbe = "#22C55E" if g["typ"] == "up" else "#EF4444"
        t = datetime.date.fromisoformat(g["datum"])
        a = (datetime.datetime.combine(t, datetime.time(0)) - datetime.timedelta(hours=10)).isoformat()
        b = (datetime.datetime.combine(t, datetime.time(0)) + datetime.timedelta(hours=10)).isoformat()
        lo, hi = sorted((g["schluss_vorher"], g["eroeffnung"]))
        fig.add_shape(type="rect", x0=a, x1=b, y0=lo, y1=hi, fillcolor=farbe, opacity=0.18, line=dict(width=0),
                      layer="above")
        if g["status"] in ("offen", "teilweise") and g["rest"] > 0:
            ende = g["schluss_vorher"] + (g["rest"] if g["typ"] == "up" else -g["rest"])
            lo2, hi2 = sorted((g["schluss_vorher"], ende))
            fig.add_shape(type="rect", x0=a, x1=b, y0=lo2, y1=hi2, fillcolor=farbe, opacity=0.55,
                          line=dict(width=0), layer="above")
    ziel = next((g for g in d["gaps"] if g["datum"] == auswahl_datum), None) if auswahl_datum else None
    ziel = ziel or (OG.heute(d["gaps"]) if d["gaps"] else None)
    if ziel and ziel["typ"] != "kein":
        fig.add_hline(y=ziel["schluss_vorher"], line=dict(color="#E5E7EB", dash="dot", width=1.2),
                      annotation_text=f"Schluss vor {_datum(ziel['datum'])}: {_de(ziel['schluss_vorher'], 0)}",
                      annotation_position="bottom right")
        fig.add_hline(y=ziel["eroeffnung"], line=dict(color="#22C55E" if ziel["typ"] == "up" else "#EF4444",
                                                      dash="dot", width=1.2),
                      annotation_text=f"Eröffnung {_de(ziel['eroeffnung'], 0)} · {OG.STATUS[ziel['status']]}"
                      + (f" ({ziel['geschlossen_zeit'] or _datum(ziel['geschlossen'])})" if ziel["geschlossen"] else ""),
                      annotation_position="top left")
    return len(sicht)


# ---------------------------------------------------------------------------------------------------- Alerts
def alerts_bereich(h, ohlc, codes, symbol_je, min_pct, gesehen, als_gesehen):
    s = st.session_state
    for k, v in OG.STANDARD_ALERTS.items():
        s.setdefault(P + "al_" + k, v)
    st.markdown("**Opening-Gaps**")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    with sp[0]:
        st.toggle("Neues Opening-Gap größer als …", key=P + "al_neu_klein_an")
        st.number_input("… Schwelle 1 (%)", 0.05, 10.0, step=0.05, format="%.2f", key=P + "al_neu_klein_pct")
        st.toggle("Neues Opening-Gap größer als …", key=P + "al_neu_gross_an")
        st.number_input("… Schwelle 2 (%)", 0.05, 10.0, step=0.05, format="%.2f", key=P + "al_neu_gross_pct")
    with sp[1]:
        st.toggle("Opening-Gap teilweise geschlossen ab …", key=P + "al_halb_an")
        st.number_input("… Füllgrad (%)", 5.0, 95.0, step=5.0, format="%.0f", key=P + "al_halb_pct")
        st.toggle("Opening-Gap vollständig geschlossen", key=P + "al_geschlossen_an")
        st.toggle("Opening-Gap am Handelsschluss noch offen", key=P + "al_offen_schluss_an")
    try:
        intra = h["intraday"]() if h.get("intraday") else {}
    except Exception:
        intra = {}
    d = daten(ohlc, intra, codes, symbol_je, min_pct, datetime.datetime.now(datetime.timezone.utc))
    einst = {k: s[P + "al_" + k] for k in OG.STANDARD_ALERTS}
    alle = OG.alerts({k: d[k]["gaps"] for k in codes}, einst, ())
    gs = set(gesehen)
    neu = [x for x in alle if x["schluessel"] not in gs]
    st.markdown(f"**{len(neu)} neue Opening-Gap-Meldungen** · {len(alle) - len(neu)} bereits gesehen")
    for x in neu:
        st.warning("🔔 " + x["text"])
    if neu:
        st.button("Opening-Gap-Meldungen als gesehen markieren", key=P + "gesehen_btn", on_click=als_gesehen,
                  args=([x["schluessel"] for x in neu],))
    st.caption(f"Opening-Gap-Meldungen der letzten {OG.ALERT_TAGE} Tage, je Ereignis genau einmal, nur hier in der "
               "App. „Am Handelsschluss noch offen“ erst mit der offiziellen Tageskerze.")
