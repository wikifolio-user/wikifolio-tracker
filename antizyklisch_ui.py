"""Antizyklische Einstiege (Menuepunkt in der Gruppe Maerkte) - Oberflaeche. Rechnungen: antizyklisch.py.

Nur lesen: Tageskerzen und Fear & Greed aus dem State-Repo (Kurs-Agent). Keine Orders, keine Depotdaten.
h = {"ohlc": () -> dict wie state/markt/ohlc.json, "sentiment": () -> dict wie state/markt/sentiment.json}"""
import datetime
import html

import streamlit as st

import antizyklisch as A
import fear_greed as FG
import ui_stil as UI

P = "az_"
HORIZONTE = A.PARAM["horizonte"]
ZEITRAEUME = {"1 Jahr": 365, "2 Jahre": 730, "Seit 2021": None, "Alles": 0}
_CACHE = {}

CSS = """<style>
.az-raster { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; margin:6px 0 10px; }
@media (max-width: 900px) { .az-raster { grid-template-columns:1fr; } }
.az-karte { background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); border-radius:16px;
    padding:12px 14px; min-width:0; }
.az-karte h4 { margin:0 0 4px; font-size:.95rem; color:#E8ECF6; font-weight:700; }
.az-gross { font-size:1.35rem; font-weight:800; color:#ffffff; font-variant-numeric:tabular-nums; }
.az-status { font-weight:700; margin:2px 0 4px; }
.az-status.neg { color:#F87171; } .az-status.pos { color:#4ADE80; } .az-status.neu { color:#EAB308; }
.az-zeile { color:#C9CED8; font-size:.86rem; line-height:1.45; font-variant-numeric:tabular-nums; }
.az-klein { color:#A9ACB0; font-size:.76rem; line-height:1.35; }
.az-us { display:inline-block; font-size:.7rem; padding:1px 7px; border-radius:999px; margin-left:4px;
    border:1px solid rgba(124,156,255,.5); color:#AFC2FF; vertical-align:middle; }
.az-aussage { border-radius:16px; padding:12px 16px; margin:6px 0 8px; border:1px solid rgba(255,255,255,.1);
    background:rgba(255,255,255,.03); }
.az-aussage .kopf { font-weight:800; font-size:1.05rem; margin-bottom:4px; }
.az-aussage.auffaellig { border-color:rgba(74,222,128,.55); }
.az-aussage.kein_vorteil { border-color:rgba(234,179,8,.5); }
.az-aussage.unklar { border-color:rgba(169,172,176,.5); }
.az-zahlen { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin-top:8px; }
@media (max-width: 640px) { .az-zahlen { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.az-zahl { background:rgba(255,255,255,.04); border-radius:12px; padding:8px 10px; min-width:0; }
.az-zahl .t { color:#A9ACB0; font-size:.74rem; } .az-zahl .w { font-weight:700; font-size:1.05rem; color:#fff;
    font-variant-numeric:tabular-nums; } .az-zahl .u { color:#A9ACB0; font-size:.72rem; }
.az-erf { font-size:.86rem; color:#C9CED8; line-height:1.6; }
</style>"""


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _de(x, n=2):
    if x is None:
        return "–"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x, n=1, vz=True):
    if x is None:
        return "–"
    return (f"{x * 100:+.{n}f}" if vz else f"{x * 100:.{n}f}").replace(".", ",") + " %"


def _q(x):
    return "–" if x is None else f"{round(x * 100)} %"


def _dat(d):
    return d.strftime("%d.%m.%Y") if d else "–"


def _tage(n):
    return f"{n} Handelstag{'en' if n != 1 else ''}"


def _laden(h, code):
    ohlc, sent = h["ohlc"](), h["sentiment"]()
    # Datenstand + Objekt: neue Dateien (neuer Stand) oder neu geladene Daten rechnen neu
    schl = (code, id(ohlc), id(sent), str((ohlc or {}).get("stand")), str((sent or {}).get("stand")))
    if schl not in _CACHE:
        t = A.tabelle(code, ohlc, sent)
        _CACHE.clear() if len(_CACHE) > 8 else None
        _CACHE[schl] = (t, A.auswertung(t))
    return _CACHE[schl]


# ---------------------------------------------------------------------------------------------------- Karten
def _karte_sma(t):
    s = A.sma_status(t["kerzen"])
    if not s["ok"]:
        return (f'<div class="az-karte"><h4>200-Tage-Linie</h4><div class="az-status neu">⚠ Zu wenig Daten</div>'
                f'<div class="az-zeile">{s["vorhanden"]} von {A.PARAM["sma"]} Schlusskursen vorhanden – es fehlen '
                f'{s["fehlend"]}.</div></div>')
    if s["heute_unterschritten"]:
        status, k = "▼ 200-Tage-Linie heute unterschritten", "neg"
    elif s["unter"]:
        status = (f"▼ Seit {_tage(s['seit'])} unter der 200-Tage-Linie" if s["seit_kreuzung"]
                  else f"▼ Seit mindestens {_tage(s['seit'])} unter der 200-Tage-Linie")
        k = "neg"
    else:
        status, k = "▲ Über der 200-Tage-Linie", "pos"
    return (f'<div class="az-karte"><h4>200-Tage-Linie · {_e(t["name"])}</h4>'
            f'<div class="az-status {k}">{_e(status)}</div>'
            f'<div class="az-zeile">Schluss <b>{_de(s["schluss"])}</b> · SMA 200 <b>{_de(s["sma"])}</b><br>'
            f'Abstand <b>{_pct(s["abstand"], 2)}</b><br>Letzte Kreuzung nach unten: {_dat(s["letzte_kreuzung_unter"])}'
            f'<br>Letzte Kreuzung nach oben: {_dat(s["letzte_kreuzung_ueber"])}</div>'
            f'<div class="az-klein">Schlusskurs vom {_dat(s["datum"])} (nach Handelsschluss bestätigt)</div></div>')


def _us_marke(t):
    return '<span class="az-us">US-Marktindikator</span>' if t["code"] != "SPX" else ""


def _stand_hinweis(t, datum):
    if datum and t["stand"]["index"] and datum != t["stand"]["index"]:
        return f' · abweichend vom Index-Datenstand {_dat(t["stand"]["index"])}'
    return ""


def _phase_text(kat, x):
    name = A.KAT_DE[kat]
    lauf, letzte = x["laufend"], x["letzte"]
    med = f" · Median früherer Phasen: {_tage(round(x['median']))}" if x["median"] is not None else ""
    if lauf:
        dauer = (f"seit mindestens {_tage(lauf['dauer'])}" if lauf["beginn_unklar"]
                 else f"seit {_tage(lauf['dauer'])} (ab {_dat(lauf['start'])})")
        vgl = ""
        if x["median"] is not None:
            vgl = (" – länger als üblich" if lauf["dauer"] > x["median"] else
                   " – kürzer als üblich" if lauf["dauer"] < x["median"] else " – so lang wie üblich")
        return f"● <b>{name}</b> läuft {dauer}{vgl}{med}"
    if letzte:
        return (f"○ {name} nicht aktiv · zuletzt {_dat(letzte['start'])}–{_dat(letzte['ende'])} "
                f"({'mind. ' if letzte['beginn_unklar'] else ''}{_tage(letzte['dauer'])}){med}")
    return f"○ {name}: keine Phase im belastbaren Zeitraum"


def _karte_fg(t):
    fs = A.fg_status(t["fg"], t["fg_ab"])
    if not fs["ok"]:
        return ('<div class="az-karte"><h4>Fear &amp; Greed</h4><div class="az-status neu">⚠ Keine Daten</div>'
                '<div class="az-zeile">Der CNN-Index liegt derzeit nicht vor.</div></div>')
    kat, _ = FG.kategorie(fs["wert"])
    orig = (t["fg_eintrag"] or {}).get("kategorie") or ""
    zeilen = "<br>".join(_phase_text(k, fs[k]) for k in ("ef", "eg"))
    return (f'<div class="az-karte"><h4>Fear &amp; Greed (CNN){_us_marke(t)}</h4>'
            f'<div class="az-gross">{_de(fs["wert"], 1)} <span style="font-size:1rem">· {_e(kat)}</span></div>'
            f'<div class="az-zeile">{zeilen}</div>'
            f'<div class="az-klein">Stand {_dat(fs["datum"])}{_stand_hinweis(t, fs["datum"])} · CNN: '
            f'„{_e(orig.title())}“ · Kategorien nach CNN: 0–24 Extreme Fear, 25–44 Fear, 45–55 Neutral, '
            f'56–75 Greed, 76–100 Extreme Greed · Dauer in NYSE-Handelstagen, belastbar ab {_dat(fs["belastbar_ab"])}'
            f'</div></div>')


def _karte_vix(t):
    vr = A.vix_reihe(t["vix"])
    if not vr:
        return ('<div class="az-karte"><h4>VIX</h4><div class="az-status neu">⚠ Keine Daten</div></div>')
    v = vr[-1]
    r = A.richtung(v["aend5"])
    pfeil = {"steigend": "▲ steigend", "fallend": "▼ fallend"}.get(r, "–")
    pz = v["perzentil"]
    hoch = pz is not None and pz >= A.PARAM["vix_perzentil"]
    niveau = ("historisch hoch" if hoch else "nicht historisch hoch") if pz is not None else "Perzentil: zu wenig Historie"
    return (f'<div class="az-karte"><h4>VIX{_us_marke(t)}</h4>'
            f'<div class="az-gross">{_de(v["schluss"])}</div>'
            f'<div class="az-status {"neg" if r == "steigend" else "pos"}">{pfeil} '
            f'({_de(v["aend5"]) if v["aend5"] is not None else "–"} Pkt. / {_pct(v["aend5_pct"])} in 5 Handelstagen)</div>'
            f'<div class="az-zeile">{_de(pz, 0) if pz is not None else "–"}. Perzentil der letzten 5 Jahre · '
            f'<b>{"⬆ " if hoch else ""}{niveau}</b> (Schwelle {A.PARAM["vix_perzentil"]}.)</div>'
            f'<div class="az-klein">Schlussstand vom {_dat(v["datum"])}{_stand_hinweis(t, v["datum"])} · '
            f'Perzentil nur aus den {A.PARAM["vix_fenster"]} Handelstagen davor</div></div>')


# ---------------------------------------------------------------------------------------------------- Aussage
def _bed_text(bid):
    if bid == "B":
        return "Index unter der 200-Tage-Linie"
    k = int("".join(c for c in bid[1:] if c.isdigit()))
    t = f"unter der 200-Tage-Linie und Extreme Fear seit mindestens {_tage(k)}"
    if bid[0] == "D":
        t += f", VIX historisch hoch und {'steigend' if bid.endswith('s') else 'fallend'}"
    return t


def _zahlen(s, v, vgl_name):
    ki = s["ki"]
    return ('<div class="az-zahlen">'
            f'<div class="az-zahl"><div class="t">Historische Trefferquote</div><div class="w">{_q(s["quote"])}</div>'
            f'<div class="u">95-%-KI {_q(ki[0])}–{_q(ki[1])}</div></div>'
            f'<div class="az-zahl"><div class="t">Vergleich: {_e(vgl_name)}</div><div class="w">{_q(v["quote"])}</div>'
            f'<div class="u">Differenz {_pp(s, v)}</div></div>'
            f'<div class="az-zahl"><div class="t">Fälle</div><div class="w">{s["n"]}</div>'
            f'<div class="u">davon ohne Überlappung {s["n_eff"]}</div></div>'
            f'<div class="az-zahl"><div class="t">Typ. Zwischenverlust</div><div class="w">{_pct(s["verlust"])}</div>'
            f'<div class="u">Medianrendite {_pct(s["median"])}</div></div></div>')


def _pp(s, v):
    if s["quote"] is None or v["quote"] is None:
        return "–"
    return f"{(s['quote'] - v['quote']) * 100:+.0f} Pp."


def _aussage(t, a, h):
    e = A.einordnung(a, h)
    name = t["name"]
    kopf = {"auffaellig": "✅ Historisch auffällig", "kein_vorteil": "➖ Kein historischer Vorteil erkennbar",
            "unklar": "❔ Datenlage unklar"}[e["zustand"]]
    if not a.get("ok"):
        st.markdown(f'<div class="az-aussage unklar"><div class="kopf">{kopf}</div><div class="az-zeile">'
                    f'{_e(e.get("grund"))}</div></div>', unsafe_allow_html=True)
        return e
    b = a["erg"][("B", h, "gesamt")]
    if e["zustand"] == "auffaellig":
        bid = e["bid"]
        s = a["erg"][(bid, h, "gesamt")]
        text = (f"Frühester Einstieg mit historischem Vorteil: <b>{_e(_bed_text(bid))}</b>. In diesen Fällen lag der "
                f"{_e(name)} nach {h} Handelstagen in <b>{_q(s['quote'])}</b> der Fälle im Plus (historische "
                f"Trefferquote) – gegenüber {_q(b['quote'])} bei „Index unter der 200-Tage-Linie“. Der Vorteil hat "
                f"sich im späteren Testzeitraum bestätigt.")
        zahlen = _zahlen(s, b, "unter SMA 200")
    else:
        text = _e(e.get("grund") or "Ausreichend Fälle, aber keine untersuchte Stufe erfüllt das Kriterium "
                                    f"(mind. +{A.PARAM['vorteil_pp']} Pp. gegenüber „unter SMA 200“ und im "
                                    "Testzeitraum bestätigt).")
        if e.get("nur_lern"):
            text += (" Im Lernzeitraum auffällig, im Testzeitraum aber nicht bestätigt: "
                     + ", ".join(_e(x) for x in e["nur_lern"]) + ".")
        text += (f" Zum Vergleich: Nach Unterschreiten der 200-Tage-Linie lag der {_e(name)} nach {h} Handelstagen "
                 f"in {_q(b['quote'])} der Fälle im Plus (historische Trefferquote), an beliebigen Tagen in "
                 f"{_q(a['erg'][('A', h, 'gesamt')]['quote'])}.")
        zahlen = _zahlen(b, a["erg"][("A", h, "gesamt")], "beliebiger Tag") if b["n"] else ""
    st.markdown(f'<div class="az-aussage {e["zustand"]}"><div class="kopf">{kopf} · {h} Handelstage</div>'
                f'<div class="az-zeile">{text}</div>{zahlen}'
                f'<div class="az-klein" style="margin-top:6px">Zeitraum {_dat(a["von"])}–{_dat(a["bis"])} '
                f'(gemeinsamer Zeitraum von Index, CNN Fear &amp; Greed und VIX-Perzentil) · Lernzeitraum bis '
                f'{_dat(a["grenze"] - datetime.timedelta(days=1))}, Test ab {_dat(a["grenze"])} · Vergangene '
                f'Trefferquoten sind keine Prognose und keine Anlageberatung.</div></div>', unsafe_allow_html=True)
    return e


def _aktuell(t, e):
    erf = A.aktuell_erfuellt(t)
    if not erf:
        return
    z = t["zeilen"][-1]
    ef = z["ef"]
    teile = [f"{'✔' if erf['B'] else '✘'} unter SMA 200"]
    for k in A.PARAM["stufen"]:
        teile.append(f"{'✔' if erf[f'C{k}'] else '✘'} Extreme Fear ≥ {k} T.")
    vix = ("VIX hoch" if z["vix_pz"] is not None and z["vix_pz"] >= A.PARAM["vix_perzentil"] else "VIX nicht hoch")
    teile.append(f"{vix}, {z['vix_dir'] or '–'}")
    ziel = ""
    if e.get("bid"):
        ja = erf.get(e["bid"])
        ziel = f"<br><b>{'✔ Erfüllt' if ja else '✘ Noch nicht erfüllt'}</b>: {_e(_bed_text(e['bid']))}"
    st.markdown(f'<div class="az-erf"><b>Aktuelle Marktlage ({_dat(z["datum"])}):</b> ' + " · ".join(teile)
                + (f" · Extreme Fear derzeit {'mind. ' if z['ef_mind'] else ''}{_tage(ef)}" if ef else "")
                + ziel + "</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------------- Detail
def _tabelle(a, h):
    import pandas as pd
    zeilen = []
    for bid, text in a["bedingungen"]:
        s, l_, te = (a["erg"][(bid, h, x)] for x in ("gesamt", "lern", "test"))
        v = a["erg"][(A.vergleich_von(bid), h, "gesamt")]
        ok = ""
        if bid[0] in "CD":
            vt, grund = A.vorteil(a, bid, h)
            best = A.bestaetigt(a, bid, h)
            ok = ("✔ auffällig" if vt and best else "✔ Lernzeitraum, ✘ Test" if vt and best is False else
                  "✔ Lernzeitraum, Test offen" if vt else f"✘ {grund}")
        zeilen.append({"Bedingung": f"{bid}: {text}", "Fälle": s["n"], "ohne Überlappung": s["n_eff"],
                       "Trefferquote": _q(s["quote"]), "95-%-KI": f"{_q(s['ki'][0])}–{_q(s['ki'][1])}",
                       "Vergleich": f"{A.vergleich_von(bid)}: {_q(v['quote'])}" if bid != "A" else "–",
                       "Differenz": _pp(s, v) if bid != "A" else "–", "Medianrendite": _pct(s["median"]),
                       "Typ. Zwischenverlust": _pct(s["verlust"]),
                       "Lernzeitraum": f"{l_['n']} · {_q(l_['quote'])}", "Testzeitraum": f"{te['n']} · {_q(te['quote'])}",
                       "Kriterium": ok})
    st.dataframe(pd.DataFrame(zeilen), hide_index=True, width="stretch", key=P + "tab")
    st.caption("Fälle: je Signalphase nur der erste qualifizierte Einstieg (A: jeder Handelstag). Trefferquote = Anteil "
               "mit positiver Rendite. Das 95-%-Intervall (Wilson) rechnet mit der Zahl der Fälle ohne überlappende "
               "Haltedauer. Vergleich: B gegen A, alle anderen gegen B.")


def _signale(t, a):
    """Historische Signale (erster Tag je Signalphase und Bedingung) -> [(index, [bid, ...])]."""
    je = {}
    for bid, _, pruef in A.bedingungen():
        if pruef is None:
            continue
        for i in A.einstiege(t["zeilen"], a["phasen"], pruef):
            je.setdefault(i, []).append(bid)
    return sorted(je.items())


def _charts(t, a, auswahl):
    from plotly.subplots import make_subplots
    s = st.session_state
    if s.get(P + "zr") not in ZEITRAEUME:
        s[P + "zr"] = "2 Jahre"
    zr = st.segmented_control("Zeitraum", list(ZEITRAEUME), key=P + "zr", label_visibility="collapsed") or "2 Jahre"
    zeilen = t["zeilen"]
    ende = zeilen[-1]["datum"]
    tage = ZEITRAEUME[zr]
    ab = (a.get("von") if tage is None else datetime.date.min if tage == 0 else ende - datetime.timedelta(days=tage))
    zz = [z for z in zeilen if z["datum"] >= ab]
    x = [z["datum"] for z in zz]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.5, 0.25, 0.25])
    fig.add_scatter(x=x, y=[z["c"] for z in zz], name=t["name"], line=dict(color="#7C9CFF", width=1.6), row=1, col=1,
                    hovertemplate="%{x|%d.%m.%Y}: %{y:,.2f}<extra>Schluss</extra>")
    fig.add_scatter(x=x, y=[z["sma"] for z in zz], name="SMA 200", line=dict(color="#EAB308", width=1.4, dash="dot"),
                    row=1, col=1, hovertemplate="%{y:,.2f}<extra>SMA 200</extra>")
    kr = [zeilen[i] for i in A.kreuzungen([z["c"] for z in zeilen], [z["sma"] for z in zeilen])
          if zeilen[i]["datum"] >= ab]
    fig.add_scatter(x=[z["datum"] for z in kr], y=[z["c"] for z in kr], mode="markers", name="Kreuzung nach unten",
                    marker=dict(symbol="triangle-down", size=10, color="#F87171"), row=1, col=1,
                    hovertemplate="%{x|%d.%m.%Y}<extra>Kreuzung unter SMA 200</extra>")
    fx = [(z["datum"], z["fg"]) for z in zz if z["fg"] is not None]
    fig.add_hrect(y0=0, y1=25, fillcolor="#EF4444", opacity=0.10, line_width=0, row=2, col=1)
    fig.add_hrect(y0=75, y1=100, fillcolor="#22C55E", opacity=0.08, line_width=0, row=2, col=1)
    fig.add_scatter(x=[d for d, _ in fx], y=[v for _, v in fx], name="Fear & Greed", line=dict(color="#F97316", width=1.3),
                    row=2, col=1, hovertemplate="%{y:.1f}<extra>Fear & Greed</extra>")
    vx = [(z["datum"], z["vix"]) for z in zz if z["vix"] is not None]
    fig.add_scatter(x=[d for d, _ in vx], y=[v for _, v in vx], name="VIX", line=dict(color="#C084FC", width=1.3),
                    row=3, col=1, hovertemplate="%{y:.2f}<extra>VIX</extra>")
    if auswahl is not None and zeilen[auswahl]["datum"] >= ab:
        for r in (1, 2, 3):
            fig.add_vline(x=zeilen[auswahl]["datum"], line=dict(color="#4ADE80", width=1.5, dash="dash"), row=r, col=1)
    fig.update_yaxes(title_text="Kurs", row=1, col=1)
    fig.update_yaxes(title_text="F&G", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="VIX", row=3, col=1)
    fig.update_layout(height=620, margin=dict(l=10, r=10, t=10, b=30), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.08))
    st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), width="stretch", key=P + "chart",
                    config={"displayModeBar": False})
    if t["code"] != "SPX":
        st.caption("Fear & Greed und VIX sind US-Marktindikatoren; sie stehen je Tag mit dem Wert des letzten "
                   "US-Handelstags bis zum Signaltag.")
    if not fx:
        st.caption("Für diesen Zeitraum liegen keine belastbaren Fear-&-Greed-Werte vor.")


def _signal_detail(t, a, signale, h):
    import plotly.graph_objects as go
    if not signale:
        st.caption("Im gemeinsamen Zeitraum gab es noch kein Signal.")
        return None
    s = st.session_state
    ids = [i for i, _ in signale]
    if s.get(P + "signal") not in ids:
        s[P + "signal"] = ids[-1]
    je = dict(signale)
    i = st.selectbox("Historisches Signal", ids, key=P + "signal", format_func=lambda k: (
        f"{_dat(t['zeilen'][k]['datum'])} · {', '.join(je[k])}"))
    z = t["zeilen"][i]
    st.markdown(
        f'<div class="az-zeile"><b>Damals verfügbar (Signaltag {_dat(z["datum"])}, nach Handelsschluss):</b><br>'
        f'Schluss {_de(z["c"])} · SMA 200 {_de(z["sma"])} ({_pct(z["c"] / z["sma"] - 1, 2)})<br>'
        f'Fear &amp; Greed {_de(z["fg"], 1)} (Stand {_dat(z["us_tag"])}) · Extreme Fear '
        f'{("mind. " if z["ef_mind"] else "") + _tage(z["ef"]) if z["ef"] else "nicht aktiv"}<br>'
        f'VIX {_de(z["vix"])} · {_de(z["vix_pz"], 0) if z["vix_pz"] is not None else "–"}. Perzentil · '
        f'{z["vix_dir"] or "–"} ({_de(z["vix_aend5"]) if z["vix_aend5"] is not None else "–"} Pkt. in 5 Tagen)<br>'
        f'Erfüllte Bedingungen (erster Tag der Phase): {_e(", ".join(je[i]))}</div>', unsafe_allow_html=True)
    zeilen = t["zeilen"]
    if i + 1 >= len(zeilen):
        st.caption("Einstieg erst zur nächsten Eröffnung – noch kein Kursverlauf.")
        return i
    einstieg = zeilen[i + 1]["o"]
    weg = zeilen[i + 1:i + 1 + max(HORIZONTE)]
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,.3)", width=1))
    fig.add_scatter(x=list(range(1, len(weg) + 1)), y=[(w["c"] / einstieg - 1) * 100 for w in weg], name="Schluss",
                    line=dict(color="#7C9CFF", width=2), hovertemplate="Tag %{x}: %{y:+.1f} %<extra></extra>")
    fig.add_scatter(x=list(range(1, len(weg) + 1)), y=[(w["l"] / einstieg - 1) * 100 for w in weg], name="Tagestief",
                    line=dict(color="#F87171", width=1, dash="dot"), hovertemplate="Tief Tag %{x}: %{y:+.1f} %<extra></extra>")
    for hh in HORIZONTE:
        if hh <= len(weg):
            fig.add_vline(x=hh, line=dict(color="#EAB308" if hh == h else "rgba(255,255,255,.25)", width=1, dash="dash"))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=30), xaxis_title="Handelstage nach dem Einstieg",
                      yaxis_title="% ggü. Einstieg", legend=dict(orientation="h", y=-0.3))
    st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), width="stretch", key=P + "verlauf",
                    config={"displayModeBar": False})
    teile = []
    for hh in HORIZONTE:
        r = A.ergebnis(zeilen, i, hh)
        teile.append(f"{hh} T.: " + (f"{_pct(r['rendite'])} (Zwischenverlust {_pct(r['verlust'])})" if r
                                     else "noch nicht vollständig"))
    st.caption(f"Einstieg zur Eröffnung am {_dat(zeilen[i + 1]['datum'])} bei {_de(einstieg)} · " + " · ".join(teile))
    return i


def _methodik(t, a):
    p = A.PARAM
    st.markdown(
        f"- **Kreuzung:** Schluss am Vortag auf/über dem damaligen SMA 200 (einfacher Durchschnitt der letzten "
        f"{p['sma']} Schlusskurse), Schluss heute darunter – nur abgeschlossene Handelstage.\n"
        f"- **Signalphase:** beginnt mit einer Kreuzung und endet erst nach {p['phase_ende']} Handelstagen in Folge auf "
        f"oder über dem SMA 200. Je Phase und Bedingung zählt nur der erste qualifizierte Einstieg.\n"
        f"- **Extreme Fear:** CNN-Wert unter {p['ef_grenze']}. Dauer in bestätigten NYSE-Handelstagen; Wochenenden und "
        f"Börsenfeiertage unterbrechen nicht. Fehlt ein Tageswert, ist die Fortsetzung unbekannt – gezählt wird ab "
        f"dem nächsten bekannten Wert („mindestens“). Stufen: {', '.join(map(str, p['stufen']))} Tage.\n"
        f"- **VIX hoch:** Schluss ≥ {p['vix_perzentil']}. Perzentil der {p['vix_fenster']} Schlusskurse vor dem "
        f"Signaltag. Richtung: Veränderung über {p['vix_richtung_tage']} Handelstage (> 0 steigend, sonst fallend).\n"
        f"- **Einstieg:** Eröffnung des nächsten Handelstags des Zielindex nach dem Signaltag – dann sind Schlusskurs, "
        f"VIX-Schluss und CNN-Tageswert veröffentlicht. Beim DAX gelten die US-Werte des letzten US-Handelstags bis "
        f"zum Signaltag.\n"
        f"- **Ergebnis:** Schluss {', '.join(map(str, p['horizonte']))} Handelstage nach dem Signaltag ggü. Einstieg; "
        f"Zwischenverlust = tiefstes Tagestief ab dem Einstieg ggü. Einstieg (Median). Nur vollständige Fälle.\n"
        f"- **Kriterium für einen historischen Vorteil (vorab festgelegt):** mindestens {p['min_lern']} Fälle im "
        f"Lernzeitraum, Trefferquote mindestens +{p['vorteil_pp']} Prozentpunkte über „unter SMA 200“ und "
        f"Medianrendite nicht niedriger; bestätigt, wenn im Testzeitraum (mind. {p['min_test']} Fälle) die "
        f"Trefferquote ebenfalls über „unter SMA 200“ liegt. Lernzeitraum = erste {round(p['lern_anteil'] * 100)} % "
        f"des gemeinsamen Zeitraums.\n"
        f"- **Unsicherheit:** 95-%-Intervall nach Wilson mit der Zahl der Fälle ohne überlappende Haltedauer.")
    st.caption(f"Quellen: Yahoo Finance (Tageskerzen {t['symbol']} und ^VIX, Kurs-Agent, ab "
               f"{_dat(t['kerzen'][0][0]) if t['kerzen'] else '–'}); CNN Business Fear & Greed (Verlauf ab "
               f"{_dat(t['fg'][0][0]) if t['fg'] else '–'}, belastbar ab {_dat(t['fg_ab'])} – davor liefert CNN über "
               f"Wochen den Platzhalter 50,0). Keine Ersatzhistorie. Datenstand: Index {_dat(t['stand']['index'])}, "
               f"VIX {_dat(t['stand']['vix'])}, Fear & Greed {_dat(t['stand']['fg'])}.")


# ---------------------------------------------------------------------------------------------------- Seite
def seite(h):
    s = st.session_state
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("### 📉 Antizyklische Einstiege")
    st.caption("200-Tage-Linie, Dauer von Extreme Fear und VIX – und wie Einstiege in historisch vergleichbaren "
               "Lagen ausgingen. Historische Auswertung, keine Prognose und keine Anlageberatung.")
    codes = list(A.INDIZES)
    if s.get(P + "index") not in codes:
        s[P + "index"] = "SPX"
    code = st.segmented_control("Index", codes, key=P + "index", format_func=lambda c: A.INDIZES[c][1],
                                width="stretch") or "SPX"
    t, a = _laden(h, code)
    if not t["kerzen"]:
        st.warning(f"Für {t['name']} liegen keine Tageskerzen vor – die Ansicht braucht die Daten des Kurs-Agenten.")
        return
    st.markdown('<div class="az-raster">' + _karte_sma(t) + _karte_fg(t) + _karte_vix(t) + "</div>",
                unsafe_allow_html=True)
    if s.get(P + "h") not in HORIZONTE:
        s[P + "h"] = 60
    h_ = st.segmented_control("Anlagehorizont (Handelstage)", list(HORIZONTE), key=P + "h", format_func=lambda x: f"{x} T.",
                              width="stretch") or 60
    e = _aussage(t, a, h_)
    _aktuell(t, e)
    if not a.get("ok"):
        return
    with st.expander("📋 Vergleichstabelle aller Bedingungen", expanded=False):
        _tabelle(a, h_)
    signale = _signale(t, a)
    with st.expander("📈 Charts und historische Signale", expanded=True):
        auswahl = _signal_detail(t, a, signale, h_)
        _charts(t, a, auswahl)
    with st.expander("ℹ️ Berechnung und Datenquellen"):
        _methodik(t, a)
