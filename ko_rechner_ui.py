"""Knock-out-Gewinnrechner (Menuepunkt "Knock-out-Rechner") - Oberflaeche. Rechnungen: ko_rechner.py.

Reihenfolge: Index -> Long/Short -> Einsatz -> Kursziel -> Hebel -> Zieltermin -> Ergebnis -> Hebelvergleich und
Gewinndiagramm -> Risikoanalyse -> optional echtes Zertifikat (WKN/ISIN, manuelle Produktdaten).

Alle Eingaben liegen je Index unter eigenen Schluesseln (ko_<INDEX>_...): so hat jeder Index seine eigenen
Einstellungen, und die App merkt sie je Benutzer (app.py: RECHNER_EINGABEN["ko_rechner"]).
h = {"indizes": () -> indizes.json-dict, "abrufen": (yahoo_symbol) -> {"k","p","t","m"} | None (Refresh-Knopf)}
"""
import datetime
import html
import json
import re
import time
from zoneinfo import ZoneInfo

import streamlit as st

import ko_rechner as K
import ui_stil as UI

P = "ko_"
BERLIN = ZoneInfo("Europe/Berlin")
NAMEN = {c: i["name"] for c, i in K.INDIZES.items()}
CODES = list(K.INDIZES)
REFRESH_ABSTAND_SEK = 30
POS, NEG = "#34D399", "#F87171"

CSS = """<style>
.ko-kopf { display:flex; gap:12px; align-items:center; margin:2px 0 10px; }
.ko-kopf .ko-sym { font-size:1.35rem; width:38px; height:38px; border-radius:10px; background:#252628;
    display:flex; align-items:center; justify-content:center; }
.ko-kopf b { font-size:1.05rem; color:#ffffff; } .ko-kopf div div { font-size:.8rem; color:#A9ACB0; }
.ko-markt { border:1px solid rgba(124,156,255,.35); border-radius:14px; padding:10px 14px; margin:4px 0 8px;
    background:rgba(255,255,255,.03); }
.ko-markt .ko-name { font-size:.78rem; letter-spacing:.5px; text-transform:uppercase; color:#A9ACB0; }
.ko-markt .ko-kurs { font-size:1.6rem; font-weight:800; color:#ffffff; font-variant-numeric:tabular-nums; }
.ko-markt .ko-meta { font-size:.78rem; color:#A9ACB0; margin-top:2px; }
.ko-badge { display:inline-block; font-size:.7rem; font-weight:700; padding:2px 8px; border-radius:999px;
    margin-left:6px; vertical-align:middle; }
.ko-live { background:#0F3D2E; color:#34D399; } .ko-schluss { background:#2A2F3A; color:#C9CED6; }
.ko-veraltet { background:#3D2A0F; color:#FBBF24; } .ko-ref { background:#3D0F1A; color:#F87171; }
.ko-pos { color:#34D399 !important; } .ko-neg { color:#F87171 !important; } .ko-neutral { color:#C9CED6 !important; }
.ko-karte { border:1px solid rgba(124,156,255,.45); border-radius:16px; padding:14px 16px; margin:8px 0 10px;
    background:rgba(124,156,255,.06); }
.ko-karte .ko-gross { font-size:2rem; font-weight:800; line-height:1.15; font-variant-numeric:tabular-nums; }
.ko-karte .ko-unter { font-size:.85rem; color:#C9CED6; margin-bottom:8px; }
.ko-raster { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px 14px; }
.ko-raster div { font-size:.75rem; color:#A9ACB0; } .ko-raster b { display:block; font-size:.98rem; color:#ffffff;
    font-variant-numeric:tabular-nums; }
@media (max-width: 640px) { .ko-raster { grid-template-columns:repeat(2, minmax(0,1fr)); }
    .ko-karte .ko-gross { font-size:1.6rem; } }
.ko-tab { width:100%; border-collapse:collapse; font-size:.85rem; font-variant-numeric:tabular-nums; }
.ko-tab th, .ko-tab td { white-space:nowrap; }
.ko-raster b.ko-pos, .ko-tab td.ko-pos { color:#34D399 !important; }
.ko-raster b.ko-neg, .ko-tab td.ko-neg { color:#F87171 !important; }
.ko-tab th { text-align:right; color:#A9ACB0; font-weight:600; padding:6px 8px;
    border-bottom:1px solid rgba(255,255,255,.12); }
.ko-tab td { text-align:right; padding:6px 8px; color:#E8ECF6; border-bottom:1px solid rgba(255,255,255,.06); }
.ko-tab th:first-child, .ko-tab td:first-child { text-align:left; }
.ko-tab tr.ko-aktiv td { background:rgba(124,156,255,.12); font-weight:700; }
.ko-tabwrap { overflow-x:auto; }
.ko-hinweis { font-size:.8rem; color:#A9ACB0; }
.st-key-ko_reihe_markt { justify-content: space-between; }
.st-key-ko_reihe_markt [data-testid="stButton"] { flex: 0 0 auto !important; width: auto !important; }
</style>"""


# ---------------------------------------------------------------------------------------------------- Helfer
def _de(x, n=2):
    return "–" if x is None else K.de(x, n)


def _eur(x, n=2, vz=False):
    if x is None:
        return "–"
    return ("+" if vz and x > 0 else "") + K.de(x, n) + " €"


def _pct(x, n=2, vz=True):
    if x is None:
        return "–"
    return ("+" if vz and x > 0 else "") + K.de(x, n) + " %"


def _klasse(x):
    return "ko-neutral" if x is None or abs(x) < 1e-9 else ("ko-pos" if x > 0 else "ko-neg")


def _k(code, feld):
    return f"{P}{code}_{feld}"


def _jetzt():
    return datetime.datetime.now(BERLIN)


def _heute():
    return _jetzt().date()


# Widget-Werte, die erhalten bleiben muessen, auch wenn ihr Widget einen Lauf lang nicht gezeichnet wird (anderer
# Index gewaehlt, Ansicht verlassen) - Streamlit loescht solche Werte sonst. Knoepfe sind ausgenommen.
HALTEN = re.compile(r"^ko_(index|gebuehr|fx_ziel|vergleich|[A-Z]{3}_(richtung|man_an|man|erweitert)|"
                    r"p[AB]_(kennung|basiswert|richtung|stand|emittent|typ|basispreis|ko_schwelle|bezug|geld|brief|"
                    r"finanzierung_pct|restwert))$")


def _werte_halten():
    s = st.session_state
    for k in [k for k in list(s.keys()) if HALTEN.match(str(k))]:
        s[k] = s[k]


# ---------------------------------------------------------------------------------------------------- Regler
def _setzen(key, wert):
    """Kanonischen Wert und beide Widgets (Regler, Zahlenfeld) setzen - nur aus Callbacks heraus aufrufen."""
    s = st.session_state
    s[key] = wert
    s.pop(key + "_s", None)
    s.pop(key + "_n", None)


def _von_widget(key, art, lo, hi):
    s = st.session_state
    wert = s.get(key + art)
    if wert is None:
        return
    s[key] = float(min(max(wert, lo), hi)) if art == "_s" else float(wert)


def _regler(label, key, lo, hi, schritt, fmt, hilfe=None, frei=False, fmt_regler=None):
    """Schieberegler + Zahlenfeld fuer denselben Wert (kanonisch unter `key`). frei=True: Zahlenfeld darf
    ausserhalb des Reglerbereichs liegen (z. B. beliebige Kursziele)."""
    s = st.session_state
    fmt_regler = fmt_regler or fmt
    wert = float(s[key])
    s.setdefault(key + "_s", float(min(max(wert, lo), hi)))
    s.setdefault(key + "_n", wert)
    sp = [st.container(), st.container()] if UI.ist_smartphone() else st.columns([3, 2], vertical_alignment="bottom")
    sp[0].slider(label, float(lo), float(hi), step=float(schritt), key=key + "_s", help=hilfe, format=fmt_regler,
                 on_change=lambda: (_von_widget(key, "_s", lo, hi), s.__setitem__(key + "_n", s[key])))
    sp[1].number_input(label + " (Zahl)", min_value=None if frei else float(lo), max_value=None if frei else float(hi),
                       step=float(schritt), format=fmt, key=key + "_n", label_visibility="collapsed",
                       on_change=lambda: (_von_widget(key, "_n", lo, hi),
                                          s.__setitem__(key + "_s", float(min(max(s[key], lo), hi)))))
    return float(s[key])


# ---------------------------------------------------------------------------------------------------- Marktdaten
def _daten(h):
    """indizes.json, ergaenzt um frisch per Refresh-Knopf geholte Werte dieser Sitzung (die neueren gewinnen)."""
    try:
        d = h["indizes"]() or {}
    except Exception:
        d = {}
    werte = dict((d.get("werte") or {}) if isinstance(d, dict) else {})
    for sym, w in (st.session_state.get(P + "frisch") or {}).items():
        alt = werte.get(sym) or {}
        if str(w.get("t") or "") >= str(alt.get("t") or ""):
            werte[sym] = w
    return {"stand": d.get("stand") if isinstance(d, dict) else None, "werte": werte}


def _refresh(h, code):
    s = st.session_state
    if time.time() - s.get(P + "refresh_zeit", 0) < REFRESH_ABSTAND_SEK:
        s[P + "meldung"] = "Die Daten wurden gerade erst aktualisiert."
        return
    s[P + "refresh_zeit"] = time.time()
    frisch = dict(s.get(P + "frisch") or {})
    n = 0
    for sym in (K.INDIZES[code]["yahoo"], K.FX_SYMBOL):
        try:
            w = h["abrufen"](sym)
        except Exception:
            w = None
        if w:
            frisch[sym] = w
            n += 1
    s[P + "frisch"] = frisch
    s[P + "meldung"] = "Marktdaten aktualisiert." if n else "Aktualisierung gerade nicht möglich – es gelten die " \
                                                            "zuletzt gespeicherten Daten."


def _markt_karte(m, manuell):
    zeit = m.get("zeit")
    zt = zeit.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M") + " Uhr" if zeit else "–"
    if manuell is not None:
        badge, kurs = '<span class="ko-badge ko-ref">Referenzwert (manuell)</span>', manuell
    else:
        badge = {"live": '<span class="ko-badge ko-live">● live</span>',
                 "schluss": '<span class="ko-badge ko-schluss">Schlusskurs</span>',
                 "veraltet": '<span class="ko-badge ko-veraltet">veraltet</span>'}.get(m["status"], "")
        kurs = m.get("kurs")
    veraend = ""
    if m.get("kurs") and manuell is None:
        veraend = (f' <span class="{_klasse(m["diff"])}" style="font-size:.95rem;font-weight:700">'
                   f'{"+" if m["diff"] > 0 else ""}{K.de(m["diff"])} Pkt. ({_pct(m["pct"])})</span>')
    st.markdown(f'<div class="ko-markt"><div class="ko-name">{html.escape(m["name"])} · {m["symbol"]} · '
                f'{m["waehrung"]}{badge}</div><div class="ko-kurs">{_de(kurs)}{veraend}</div>'
                f'<div class="ko-meta">Quelle: {html.escape(m["quelle"] if manuell is None else "eigene Eingabe")}'
                f' · Stand: {zt} · Börse {m["boerse"]} {"geöffnet" if m["offen"] else "geschlossen"}</div>'
                f'<div class="ko-meta">{html.escape(m["hinweis"]) if manuell is None else "Manuell eingegebener Indexstand – kein Börsenkurs."}'
                f'</div></div>', unsafe_allow_html=True)


@st.fragment(run_every=300)
def _auto_aktualisieren(h):
    """Alle 5 Minuten: neue Daten des Kurs-Agenten? -> ganze Seite neu rechnen."""
    stand = (_daten(h) or {}).get("stand")
    s = st.session_state
    if s.get(P + "stand_gesehen") is None:
        s[P + "stand_gesehen"] = stand
    elif stand and stand != s[P + "stand_gesehen"]:
        s[P + "stand_gesehen"] = stand
        st.rerun(scope="app")


# ---------------------------------------------------------------------------------------------------- Startwerte
def _startwerte(code, start):
    """Fehlende Einstellungen eines Index mit Standardwerten belegen (gespeicherte bleiben)."""
    s = st.session_state
    s.setdefault(_k(code, "richtung"), "Long")
    s.setdefault(_k(code, "einsatz"), float(K.EINSATZ["standard"]))
    s.setdefault(_k(code, "hebel"), float(K.HEBEL["standard"]))
    s.setdefault(_k(code, "termin"), K.zieltermin_standard(_heute()).isoformat())
    if start and not s.get(_k(code, "ziel")):
        s[_k(code, "ziel")] = float(K.kursziel_standard(start))


def _zuruecksetzen(code):
    s = st.session_state
    for k in [k for k in list(s.keys()) if str(k).startswith(_k(code, ""))]:
        del s[k]
    s[P + "meldung"] = f"Einstellungen für {NAMEN[code]} zurückgesetzt."


def _termin(code):
    try:
        return datetime.date.fromisoformat(st.session_state[_k(code, "termin")])
    except (KeyError, TypeError, ValueError):
        return K.zieltermin_standard(_heute())


def _termin_setzen(code, d):
    st.session_state[_k(code, "termin")] = d.isoformat()
    st.session_state.pop(_k(code, "termin_d"), None)


def _einstellungen(code, start):
    """Gespeicherte bzw. Standard-Einstellungen eines Index (fuer den Vergleich zweier Indizes)."""
    s = st.session_state
    return {"richtung": (s.get(_k(code, "richtung")) or "Long").lower(),
            "einsatz": float(s.get(_k(code, "einsatz")) or K.EINSATZ["standard"]),
            "ziel": float(s.get(_k(code, "ziel")) or K.kursziel_standard(start)),
            "hebel": float(s.get(_k(code, "hebel")) or K.HEBEL["standard"]), "termin": _termin(code)}


# ---------------------------------------------------------------------------------------------------- Seite
def seite(h):
    st.markdown(CSS, unsafe_allow_html=True)
    s = st.session_state
    st.markdown('<div class="ko-kopf"><span class="ko-sym">🎯</span><div><b>Knock-out-Gewinnrechner</b>'
                '<div>Nasdaq 100 · DAX 40 · S&amp;P 500 · Dow Jones – Hebel simulieren und echte Zertifikate '
                'durchrechnen</div></div></div>', unsafe_allow_html=True)
    _werte_halten()
    if s.get(P + "meldung"):
        st.toast(s.pop(P + "meldung"))
    _auto_aktualisieren(h)
    jetzt = _jetzt()
    daten = _daten(h)

    # 1. Index
    if s.get(P + "index") not in CODES:
        s[P + "index"] = "NDX"
    code = st.segmented_control("Index", CODES, key=P + "index", format_func=NAMEN.get, width="stretch") or "NDX"
    m = K.marktdaten(daten, code, jetzt)
    man_an = True
    with st.container(horizontal=True, vertical_alignment="center", key="ko_reihe_markt"):
        if m["kurs"] is not None:
            man_an = st.toggle("Indexstand manuell eingeben (Referenzwert)", key=_k(code, "man_an"))
        st.button("🔄", key=P + "refresh_btn", help="Marktdaten jetzt aktualisieren", on_click=_refresh,
                  args=(h, code))
    manuell = None
    if man_an:
        s.setdefault(_k(code, "man"), float(round(m["kurs"])) if m["kurs"] else None)
        manuell = st.number_input("Indexstand (manuell)", min_value=1.0, step=10.0, format="%.2f",
                                  key=_k(code, "man"), placeholder="z. B. Stand laut Börse")
        if not manuell:
            _markt_karte(m, None)
            st.info("Bitte einen Indexstand eingeben – ohne Stand ist keine Berechnung möglich.")
            return
    _markt_karte(m, manuell)
    start = float(manuell or m["kurs"])
    fx = K.eurusd(daten)
    _startwerte(code, start)

    # 2. Long / Short
    st.segmented_control("Handelsrichtung", ["Long", "Short"], key=_k(code, "richtung"), width="stretch",
                         help="Long gewinnt bei steigenden Kursen, Short bei fallenden.")
    richtung = (s.get(_k(code, "richtung")) or "Long").lower()

    # 3. Einsatz
    einsatz = _regler("Investitionsbetrag (€)", _k(code, "einsatz"), K.EINSATZ["min"], K.EINSATZ["max"],
                      K.EINSATZ["schritt"], "%.0f", fmt_regler="%.0f €")
    with st.container(horizontal=True, key="ko_reihe_einsatz"):
        for b in K.EINSATZ["schnell"]:
            st.button(_eur(b, 0), key=P + f"einsatz_q{b}", on_click=_setzen, args=(_k(code, "einsatz"), float(b)))

    # 4. Kursziel
    lo, hi, schritt = K.kursziel_bereich(start)
    ziel = _regler("Index-Kursziel (Punkte)", _k(code, "ziel"), lo, hi,
                   schritt, "%.2f", frei=True, fmt_regler="%.0f",
                   hilfe="Regler: ±50 % um den aktuellen Stand. Im Zahlenfeld ist jedes Kursziel möglich.")
    if ziel <= 0:
        st.error("Das Kursziel muss größer als 0 sein.")
        return
    st.caption(f"Kursziel {_de(ziel)} = {_pct((ziel / start - 1) * 100)} gegenüber dem Ausgangskurs {_de(start)}")

    # 5. Hebel
    erweitert = st.toggle("Hebel bis 20× erlauben", key=_k(code, "erweitert"))
    hmax = K.HEBEL["max_erweitert"] if erweitert else K.HEBEL["max"]
    if s[_k(code, "hebel")] > hmax:
        s[_k(code, "hebel")] = hmax
        s.pop(_k(code, "hebel") + "_s", None)
        s.pop(_k(code, "hebel") + "_n", None)
    hebel = _regler("Anfangshebel (×)", _k(code, "hebel"), K.HEBEL["min"], hmax, K.HEBEL["schritt"], "%.1f",
                    fmt_regler="%.1f×")

    # 6. Zieltermin
    termin = _termin(code)
    s.setdefault(_k(code, "termin_d"), termin)
    st.date_input("Zieltermin", key=_k(code, "termin_d"), min_value=_heute() + datetime.timedelta(days=1),
                  format="DD.MM.YYYY", on_change=lambda: s.__setitem__(_k(code, "termin"),
                                                                       s[_k(code, "termin_d")].isoformat()))
    with st.container(horizontal=True, key="ko_reihe_termin"):
        for mon in (1, 3, 6, 12):
            st.button(f"{mon} {'Monat' if mon == 1 else 'Monate'}", key=P + f"termin_q{mon}", on_click=_termin_setzen,
                      args=(code, K.zieltermin_schnell(_heute(), mon)))
    termin = _termin(code)
    tage = (termin - _heute()).days
    boerse = K.INDIZES[code]["boerse"]
    st.caption(f"Zieltermin {termin.strftime('%d.%m.%Y')} · {tage} Kalendertage · "
               f"{K.handelstage(boerse, _heute(), termin)} Handelstage ({K.BOERSEN[boerse]['name']})"
               + ("" if K.ist_handelstag(boerse, termin) else " · am Zieltermin selbst wird nicht gehandelt"))

    fehler = K.pruefe(einsatz, start, ziel, hebel, richtung)
    if fehler:
        for f in fehler:
            st.error(f)
        return

    # 7. Ergebnis (Simulation)
    r = K.simulation(einsatz, start, ziel, hebel, richtung)
    _ergebnis_karte(r, termin, "Freie Hebel-Simulation (konstanter Anfangshebel)")
    st.caption("Vereinfachte Simulation mit konstantem Anfangshebel – keine exakte Prognose eines "
               "Knock-out-Produkts. Finanzierungskosten, Spread und Wechselkurs sind hier nicht enthalten.")

    # 8. Hebelvergleich + Diagramm
    st.markdown("**Hebelvergleich**")
    _hebel_tabelle(K.hebel_vergleich(einsatz, start, ziel, richtung), hebel)
    st.markdown("**Gewinndiagramm**")
    _diagramm(einsatz, start, ziel, hebel, richtung)

    # Risikoanalyse
    st.markdown("**Risikoanalyse**")
    szen = K.szenarien(lambda z: K.simulation(einsatz, start, z, hebel, richtung), start)
    _risiko(r, szen, "Theoretische Hebel-Simulation", fx_relevant=K.INDIZES[code]["waehrung"] != "EUR")

    # 9. Echtes Zertifikat (optional)
    produkt_ergebnisse = _zertifikate(code, start, fx, einsatz, ziel, tage, termin)

    # Zusatz: Vergleich zweier Indizes, Export, Zuruecksetzen
    _index_vergleich(daten, jetzt, code)
    kopf = {"Index": NAMEN[code], "Ausgangskurs": start, "Kursziel": ziel, "Richtung": richtung.capitalize(),
            "Einsatz €": einsatz, "Hebel": hebel, "Zieltermin": termin.isoformat(),
            "Datenstand": (m.get("zeit").isoformat() if m.get("zeit") and manuell is None else "manuell")}
    zeilen = K.csv_zeilen(kopf, r, K.hebel_vergleich(einsatz, start, ziel, richtung), szen)
    for name, e in produkt_ergebnisse:
        zeilen += [(f"Zertifikat {name}", k, v) for _, k, v in K.csv_zeilen({}, e)]
    csv = "Bereich;Bezeichnung;Wert\n" + "\n".join(
        ";".join(str(x).replace(".", ",") if isinstance(x, float) else str(x) for x in z) for z in zeilen)
    with st.container(horizontal=True, key="ko_reihe_fuss"):
        st.download_button("⬇️ CSV-Export", csv.encode("utf-8-sig"), file_name=f"ko_rechner_{code}_{_heute()}.csv",
                           mime="text/csv", key=P + "csv")
        st.button("↺ Zurücksetzen", key=P + "reset", on_click=_zuruecksetzen, args=(code,),
                  help=f"Alle Einstellungen für {NAMEN[code]} auf Standard")
    st.caption("Alle Angaben ohne Gewähr, keine Anlageberatung. Knock-out-Produkte können innerhalb kurzer Zeit "
               "wertlos werden.")


# ---------------------------------------------------------------------------------------------------- Ergebnis
def _ergebnis_karte(r, termin, titel):
    gv = r["gv"]
    ko_txt = "–"
    if r.get("ko_abstand_pct") is not None:
        ko_txt = f"{_pct(r['ko_abstand_pct'], 1, vz=False)} ({_de(r.get('ko_schwelle'))})"
    felder = [("Theoretischer Gesamtwert", _eur(r["endwert"])), ("Indexveränderung", _pct(r["index_pct"])),
              ("Rendite", _pct(r["rendite_pct"])), ("Eingesetztes Kapital", _eur(r["kapital"])),
              ("Hebel" + (" (aus Produkt)" if r["modus"] == "zertifikat" else " (Anfang)"), f"{_de(r['hebel'], 2)}×"),
              ("Abstand Knock-out", ko_txt), ("Break-even-Kurs", _de(r["break_even"])),
              ("Zieltermin", termin.strftime("%d.%m.%Y"))]
    if r.get("stueck"):
        felder.append(("Stückzahl", f"{r['stueck']:,}".replace(",", ".")))
    st.markdown(f'<div class="ko-karte"><div class="ko-unter">{html.escape(titel)} · möglicher Gewinn/Verlust</div>'
                f'<div class="ko-gross {_klasse(gv)}">{_eur(gv, vz=True)}</div>'
                + ('<div class="ko-unter ko-neg">Knock-out: Die Schwelle liegt auf dem Weg zum Kursziel.</div>'
                   if r.get("ko_erreicht") else "")
                + '<div class="ko-raster">' + "".join(f"<div>{t}<b class='{_klasse(r['rendite_pct']) if t == 'Rendite' else ''}'>"
                                                      f"{w}</b></div>" for t, w in felder)
                + "</div></div>", unsafe_allow_html=True)


def _hebel_tabelle(vergleich, aktiv):
    zeilen = "".join(
        f'<tr class="{"ko-aktiv" if abs(e["hebel"] - aktiv) < 1e-9 else ""}"><td>{e["hebel"]:g}×</td>'
        f'<td class="{_klasse(e["gv"])}">{_eur(e["gv"], vz=True)}</td>'
        f'<td class="{_klasse(e["rendite_pct"])}">{_pct(e["rendite_pct"])}</td><td>{_eur(e["endwert"])}</td>'
        f'<td>{_pct(e["ko_abstand_pct"], 1, vz=False)} ({_de(e["ko_schwelle"], 0)})</td></tr>' for e in vergleich)
    st.markdown('<div class="ko-tabwrap"><table class="ko-tab"><tr><th>Hebel</th><th>Gewinn/Verlust</th>'
                '<th>Rendite</th><th>Gesamtwert</th><th>KO-Distanz (vereinf.)</th></tr>' + zeilen + "</table></div>",
                unsafe_allow_html=True)
    st.caption("KO-Distanz vereinfacht: Abstand ≈ 1 ÷ Hebel (Basispreis = Knock-out-Schwelle, ohne Kosten).")


def _diagramm(einsatz, start, ziel, hebel, richtung, produkt=None):
    import plotly.graph_objects as go
    hebel_liste = sorted(set(K.HEBEL_VERGLEICH) | {hebel})
    ko_sel = K.simulation(einsatz, start, ziel, hebel, richtung)["ko_schwelle"]
    x = K.diagramm_achse(start, ziel, ko_sel)
    fig = go.Figure()
    for hb in hebel_liste:
        y = [K.simulation(einsatz, start, xi, hb, richtung)["gv"] for xi in x]
        aktiv = abs(hb - hebel) < 1e-9
        fig.add_scatter(x=x, y=y, mode="lines", name=f"{hb:g}×", line=dict(width=4 if aktiv else 1.6),
                        opacity=1 if aktiv else 0.55,
                        hovertemplate=f"{hb:g}×: Index %{{x:,.0f}} → %{{y:,.0f}} €<extra></extra>")
    fig.add_hline(y=0, line=dict(color="#A9ACB0", width=1, dash="dot"), annotation_text="Break-even",
                  annotation_position="bottom right")
    for wert, text, farbe in ((start, "aktuell", "#7c9cff"), (ziel, "Kursziel", "#FBBF24")):
        fig.add_vline(x=wert, line=dict(color=farbe, width=1.5, dash="dash"), annotation_text=text,
                      annotation_position="top")
    if ko_sel and x[0] <= ko_sel <= x[-1]:
        fig.add_vline(x=ko_sel, line=dict(color=NEG, width=1.5), annotation_text=f"KO {hebel:g}× (vereinf.)",
                      annotation_position="bottom")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=40), xaxis_title="Indexstand",
                      yaxis_title="Gewinn/Verlust (€)", hovermode="x unified",
                      legend=dict(orientation="h", y=-0.22, x=0))
    st.plotly_chart(UI.chart_stil(fig), use_container_width=True, config={"displayModeBar": False},
                    key=P + "chart")


def _risiko(r, szen, titel, fx_relevant=False):
    zeilen = "".join(f'<tr><td>{p:+d} %</td><td>{_de(e["ziel"], 0)}</td>'
                     f'<td class="{_klasse(e["gv"])}">{_eur(e["gv"], vz=True)}</td>'
                     f'<td class="{_klasse(e["rendite_pct"])}">{_pct(e["rendite_pct"])}</td>'
                     f'<td>{"Knock-out" if e.get("ko_erreicht") else ""}</td></tr>' for p, e in szen)
    ko = r.get("ko_abstand_pct")
    st.markdown(f'<div class="ko-karte" style="padding:10px 14px"><div class="ko-unter">{html.escape(titel)}</div>'
                f'<div class="ko-raster"><div>Maximaler Verlust<b class="ko-neg">{_eur(r["max_verlust"])}</b></div>'
                f'<div>Abstand KO in Punkten<b>{_de(r.get("ko_abstand_pkt"), 0)}</b></div>'
                f'<div>Abstand KO in %<b>{_pct(ko, 1, vz=False)}</b></div></div></div>'
                '<div class="ko-tabwrap"><table class="ko-tab"><tr><th>Indexbewegung</th><th>Indexstand</th>'
                f'<th>Gewinn/Verlust</th><th>Rendite</th><th></th></tr>{zeilen}</table></div>', unsafe_allow_html=True)
    w = K.ko_warnung(ko)
    if w:
        (st.error if w[0] == "hoch" else st.warning)(w[1])
    st.caption("Ein Kursziel allein schließt einen Knock-out nicht aus: Entscheidend ist der Kursverlauf bis zum "
               "Zieltermin – wird die Schwelle zwischendurch berührt, ist die Position beendet, auch wenn der Index "
               "danach das Ziel erreicht. Bei echten Produkten kommen Finanzierungskosten (der Basispreis wandert "
               "täglich) und Spread hinzu" + (", bei US-Indizes außerdem das EUR/USD-Währungsrisiko." if fx_relevant
                                               else "."))


# ---------------------------------------------------------------------------------------------------- Zertifikate
FELDER = [("emittent", "Emittent", "text"), ("typ", "Produkttyp", "text"), ("basispreis", "Basispreis", "zahl"),
          ("ko_schwelle", "Knock-out-Schwelle", "zahl"), ("bezug", "Bezugsverhältnis (z. B. 0,01 = 100:1)", "bezug"),
          ("geld", "Geldkurs (€)", "zahl"), ("brief", "Briefkurs (€)", "zahl"),
          ("finanzierung_pct", "Finanzierungskosten (% p. a.)", "zahl"), ("restwert", "Restwert bei KO (€ je Stück)",
                                                                           "zahl")]


def _bibliothek():
    try:
        return json.loads(st.session_state.get(P + "produkte_json") or "{}")
    except ValueError:
        return {}


def _produkt_aus(slot):
    s = st.session_state
    k = f"{P}p{slot}_"
    p = {f: s.get(k + f) for f, _, _ in FELDER}
    p.update({"wkn": (s.get(k + "kennung") or "").strip().upper(), "basiswert": s.get(k + "basiswert"),
              "richtung": (s.get(k + "richtung") or "Long").lower(), "stand": s.get(k + "stand")})
    for f in ("finanzierung_pct", "restwert"):
        p[f] = p.get(f) or 0.0
    return p


def _produkt_speichern(slot):
    p = _produkt_aus(slot)
    if not p["wkn"]:
        st.session_state[P + "meldung"] = "Bitte zuerst eine WKN oder ISIN eingeben."
        return
    b = _bibliothek()
    b[p["wkn"]] = {k: v for k, v in p.items() if v is not None}
    st.session_state[P + "produkte_json"] = json.dumps(b, ensure_ascii=False)
    st.session_state[P + "meldung"] = f"Produkt {p['wkn']} gespeichert."


def _produkt_laden(slot):
    s = st.session_state
    k = f"{P}p{slot}_"
    p = _bibliothek().get(s.get(k + "auswahl") or "")
    if not p:
        return
    for f, _, _ in FELDER:
        s[k + f] = p.get(f)
    s[k + "kennung"] = p.get("wkn") or ""
    s[k + "basiswert"] = p.get("basiswert")
    s[k + "richtung"] = (p.get("richtung") or "long").capitalize()
    s[k + "stand"] = p.get("stand") or ""


def _spalten(n=2):
    """Am Handy untereinander (sonst werden Zahlenfelder zu schmal), am Desktop nebeneinander."""
    return [st.container() for _ in range(n)] if UI.ist_smartphone() else st.columns(n)


def _produkt_formular(slot, code):
    s = st.session_state
    k = f"{P}p{slot}_"
    b = _bibliothek()
    if b:
        st.selectbox("Gespeichertes Produkt laden", [""] + sorted(b), key=k + "auswahl", on_change=_produkt_laden,
                     args=(slot,), format_func=lambda x: x or "– auswählen –")
    sp = st.columns(2)
    sp[0].text_input("WKN oder ISIN", key=k + "kennung", max_chars=12, placeholder="z. B. MK487D")
    s.setdefault(k + "basiswert", code)
    sp[1].selectbox("Basiswert", CODES, key=k + "basiswert", format_func=NAMEN.get)
    st.button("Produktdaten automatisch laden", key=k + "auto", disabled=True,
              help="Automatischer Abruf folgt in einem eigenen Schritt – bis dahin bitte die Daten vom Emittenten "
                   "(Produktseite/Factsheet) übernehmen.")
    s.setdefault(k + "richtung", "Long")
    st.segmented_control("Typ", ["Long", "Short"], key=k + "richtung", width="stretch")
    sp = _spalten()
    for i, (f, label, art) in enumerate(FELDER):
        ziel = sp[i % 2]
        if art == "text":
            ziel.text_input(label, key=k + f)
        else:
            s.setdefault(k + f, None)
            ziel.number_input(label, min_value=0.0, step=0.0001 if art == "bezug" else 0.01,
                              format="%.4f" if art == "bezug" else "%.2f", key=k + f)
    st.text_input("Stand der Produktdaten (Datum/Uhrzeit)", key=k + "stand", placeholder="z. B. 21.11.2026 10:15")
    st.button("💾 Produkt speichern", key=k + "speichern", on_click=_produkt_speichern, args=(slot,))
    return _produkt_aus(slot)


def _zertifikate(code, start, fx, einsatz, ziel, tage, termin):
    """Optional: bis zu zwei echte Zertifikate. -> [(name, ergebnis)]"""
    s = st.session_state
    ergebnisse = []
    with st.expander("🔎 Echtes Knock-out-Zertifikat (WKN/ISIN) – optional", expanded=bool(s.get(P + "pA_brief"))):
        st.caption("Produktdaten bitte vom Emittenten übernehmen (Produktseite oder Factsheet). Der Hebel ergibt sich "
                   "aus dem Produkt; gerechnet wird mit Einsatz, Kursziel und Zieltermin von oben.")
        g = _spalten()
        gk = g[0].number_input("Ordergebühr je Kauf/Verkauf (€)", min_value=0.0, step=0.5, format="%.2f",
                               key=P + "gebuehr")
        fx_ziel = None
        if K.INDIZES[code]["waehrung"] != "EUR":
            s.setdefault(P + "fx_ziel", round(fx, 4) if fx else 1.10)
            fx_ziel = g[1].number_input("EUR/USD am Zieltermin", min_value=0.5, max_value=2.5, step=0.01,
                                        format="%.4f", key=P + "fx_ziel",
                                        help=f"Aktuell {_de(fx, 4) if fx else 'unbekannt'}. Ein stärkerer Euro "
                                             "senkt den Wert von Zertifikaten auf US-Indizes.")
        tabs = st.tabs(["Zertifikat A", "Zertifikat B (Vergleich)"])
        for slot, tab in zip("AB", tabs):
            with tab:
                p = _produkt_formular(slot, code)
                if not p.get("brief"):
                    st.caption("Noch keine vollständigen Produktdaten.")
                    continue
                if p["basiswert"] != code:
                    st.info(f"Basiswert ist {NAMEN.get(p['basiswert'], '?')} – oben diesen Index wählen, um das "
                            "Zertifikat zu berechnen.")
                    continue
                try:
                    e = K.zertifikat(p, einsatz, start, ziel, eurusd_start=fx, eurusd_ziel=fx_ziel or fx, tage=tage,
                                     gebuehr_kauf=gk, gebuehr_verkauf=gk)
                except ValueError as ex:
                    st.error(str(ex))
                    continue
                for w in e["warnungen"]:
                    st.warning(w)
                name = p["wkn"] or f"Zertifikat {slot}"
                _ergebnis_karte(e, termin, f"{name} · {p.get('emittent') or 'Emittent unbekannt'} · "
                                           f"{p['richtung'].capitalize()}")
                st.caption(f"Basispreis am Zieltermin ≈ {_de(e['basis_ziel'])}, KO-Schwelle ≈ "
                           f"{_de(e['ko_schwelle_ziel'])} (Finanzierungskosten ≈ {_eur(e['finanzierung_eur'])}). "
                           f"Verkauf zum Geldkurs (Spread {_eur(e['spread_eur'], 3)} je Stück)"
                           + (f" · Produktdaten-Stand: {p['stand']}" if p.get("stand") else ""))
                szen = K.szenarien(lambda z, p=p: K.zertifikat(p, einsatz, start, z, eurusd_start=fx,
                                                                eurusd_ziel=fx_ziel or fx, tage=tage, gebuehr_kauf=gk,
                                                                gebuehr_verkauf=gk), start)
                _risiko(e, szen, f"Tatsächliches Produkt {name}", fx_relevant=K.INDIZES[code]["waehrung"] != "EUR")
                ergebnisse.append((name, e))
        if len(ergebnisse) == 2:
            st.markdown("**Vergleich der beiden Zertifikate**")
            _vergleich_tabelle([(n, e) for n, e in ergebnisse])
    return ergebnisse


def _vergleich_tabelle(spalten):
    reihen = [("Gewinn/Verlust", lambda e: _eur(e["gv"], vz=True), "gv"), ("Rendite", lambda e: _pct(e["rendite_pct"]),
                                                                             "rendite_pct"),
              ("Gesamtwert", lambda e: _eur(e["endwert"]), None), ("Kapital", lambda e: _eur(e["kapital"]), None),
              ("Hebel", lambda e: f"{_de(e['hebel'])}×", None),
              ("Abstand KO", lambda e: _pct(e.get("ko_abstand_pct"), 1, vz=False), None),
              ("Break-even", lambda e: _de(e["break_even"]), None)]
    kopf = "".join(f"<th>{html.escape(n)}</th>" for n, _ in spalten)
    zeilen = "".join("<tr><td>" + t + "</td>" + "".join(
        f'<td class="{_klasse(e[k]) if k else ""}">{f(e)}</td>' for _, e in spalten) + "</tr>" for t, f, k in reihen)
    st.markdown(f'<div class="ko-tabwrap"><table class="ko-tab"><tr><th></th>{kopf}</tr>{zeilen}</table></div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------------- Indexvergleich
def _index_vergleich(daten, jetzt, code):
    with st.expander("⚖️ Zwei Indizes vergleichen"):
        andere = [c for c in CODES if c != code]
        zweiter = st.selectbox("Vergleichen mit", andere, key=P + "vergleich", format_func=NAMEN.get)
        spalten = []
        for c in (code, zweiter):
            m = K.marktdaten(daten, c, jetzt)
            start = st.session_state.get(_k(c, "man")) if st.session_state.get(_k(c, "man_an")) else m["kurs"]
            if not start:
                st.info(f"Für {NAMEN[c]} liegt kein Indexstand vor.")
                return
            e = _einstellungen(c, start)
            r = K.simulation(e["einsatz"], start, e["ziel"], e["hebel"], e["richtung"])
            spalten.append((f"{NAMEN[c]} ({e['richtung'].capitalize()}, {e['hebel']:g}×)", r))
        _vergleich_tabelle(spalten)
        st.caption("Jeder Index mit seinen eigenen gespeicherten Einstellungen (Einsatz, Kursziel, Hebel, Richtung). "
                   "Noch nicht eingestellte Indizes rechnen mit den Standardwerten (Kursziel +10 %).")
