"""ETF-/ETP-Hebelrechner (Menuepunkt "ETF-/ETP-Hebelrechner") - Oberflaeche. Rechnungen: etp_rechner.py.

Reihenfolge: Index -> Einsatz -> taeglicher Hebel (oder konkretes Produkt) -> Kursziel -> Haltedauer und
Volatilitaet -> Kursverlauf -> Ergebnis -> Diagramm -> Szenariovergleich -> Hebelvergleich -> Knock-out-Vergleich ->
historischer Backtest. Bedienelemente und Marktdaten wie im Knock-out-Rechner (ko_rechner_ui).
h = {"indizes": () -> indizes.json, "ohlc": () -> ohlc.json, "abrufen": wie KO-Rechner,
     "zum_ko": (dict) -> None  (Werte in den Knock-out-Rechner uebernehmen und dorthin wechseln)}
"""
import datetime
import html
import json
import re

import streamlit as st

import boersenkalender as BK
import etp_rechner as E
import ko_rechner as K
import ko_rechner_ui as KU
import ui_stil as UI

P = "etp_"
BASIS = {"NDX": "Nasdaq 100", "SPX": "S&P 500", "DAX": "DAX 40", "DJI": "Dow Jones", "BTC": "Bitcoin"}
OHLC_SYMBOL = {"NDX": "^NDX", "SPX": "^GSPC", "DAX": "^GDAXI", "DJI": "^DJI"}
HEBEL_OPTIONEN = [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5]
DIAGRAMM_HEBEL = (2, 3)
HALTEN = re.compile(r"^etp_(index|modus|verlauf|vgl_a|vgl_b|ko_hebel|ko_fin|bt_von|bt_von_d|bt_bis_d|bt_hebel|"
                    r"[A-Z]{3}_(man_an|man|fx_an|fx_ziel)|p_(kennung|name|emittent|hebel|kurs|waehrung|kosten|"
                    r"finanzierung|spread|stand|gesichert|abruf))$")
POS, NEG = "#34D399", "#F87171"


def _hebel_text(h):
    return f"{'+' if h > 0 else '−'}{abs(h):g}× {'Long' if h > 0 else 'Short'}"


def _k(code, feld):
    return f"{P}{code}_{feld}"


def _heute():
    return KU._jetzt().date()


def _halten():
    s = st.session_state
    for k in [k for k in list(s.keys()) if HALTEN.match(str(k))]:
        s[k] = s[k]


# ---------------------------------------------------------------------------------------------------- Marktdaten
def _markt(h, code, daten, jetzt):
    """-> (startkurs oder None, Marktdaten-dict). Bitcoin: Kurs in EUR aus indizes.json (BTC-EUR)."""
    if code == "BTC":
        w = (daten.get("werte") or {}).get("BTC-EUR") or {}
        try:
            kurs, vor = float(w["k"]), float(w["p"])
        except (KeyError, TypeError, ValueError):
            kurs = vor = None
        zeit = K._zeit(w.get("t")) if w else None
        m = {"code": "BTC", "name": "Bitcoin", "symbol": "BTC-EUR", "waehrung": "EUR", "quelle": K.QUELLE.replace(
            "offizieller Indexstand", "Kurs in Euro"), "boerse": "24/7", "offen": True, "kurs": kurs,
            "status": "fehlt" if kurs is None else ("live" if zeit and jetzt - zeit < datetime.timedelta(hours=2)
                                                     else "veraltet"),
            "hinweis": "Kryptowährungen werden rund um die Uhr gehandelt."}
        if kurs:
            m.update({"vortag": vor, "diff": kurs - vor, "pct": (kurs / vor - 1) * 100, "zeit": zeit})
        return m
    return K.marktdaten(daten, code, jetzt)


def _kerzen(h, code):
    if code not in OHLC_SYMBOL:
        return []
    try:
        o = h["ohlc"]() or {}
    except Exception:
        return []
    return ((o.get("indizes") or {}).get(OHLC_SYMBOL[code]) or {}).get("kerzen") or []


# ---------------------------------------------------------------------------------------------------- Produkte
FELDER = [("name", "Produktname", "text"), ("emittent", "Emittent", "text"), ("hebel", "Täglicher Hebelfaktor (z. B. 3 oder −3)", "zahl"),
          ("kurs", "Aktueller Produktkurs", "zahl"), ("waehrung", "Handelswährung", "text"),
          ("kosten", "Laufende Kosten (% p. a.)", "zahl"), ("finanzierung", "Finanzierungs-/Swapkosten (% p. a.)", "zahl"),
          ("spread", "Geld-Brief-Spread (%)", "zahl")]


def _produkt():
    s = st.session_state
    p = {f: s.get(f"{P}p_{f}") for f, _, _ in FELDER}
    p.update({"wkn": (s.get(P + "p_kennung") or "").strip().upper(), "gesichert": bool(s.get(P + "p_gesichert")),
              "stand": s.get(P + "p_stand") or ""})
    return p


def _bibliothek():
    try:
        b = json.loads(st.session_state.get(P + "produkte_json") or "{}")
    except ValueError:
        b = {}
    return b if isinstance(b, dict) else {}


def _produkt_speichern():
    p = _produkt()
    if not p["wkn"]:
        st.session_state[P + "meldung"] = "Bitte zuerst eine WKN oder ISIN eingeben."
        return
    b = _bibliothek()
    b[p["wkn"]] = {k: v for k, v in p.items() if v not in (None, "")}
    st.session_state[P + "produkte_json"] = json.dumps(b, ensure_ascii=False)
    st.session_state[P + "meldung"] = f"Produkt {p['wkn']} gespeichert."


def _produkt_laden():
    s = st.session_state
    p = _bibliothek().get(s.get(P + "p_auswahl") or "")
    if not p:
        return
    for f, _, _ in FELDER:
        s[f"{P}p_{f}"] = p.get(f)
    s[P + "p_kennung"] = p.get("wkn") or ""
    s[P + "p_gesichert"] = bool(p.get("gesichert"))
    s[P + "p_stand"] = p.get("stand") or ""


def _automatisch_laden(get):
    """WKN/ISIN -> ETP-Daten von onvista in die Felder uebernehmen (Callback); passender Basiswert wird gewaehlt."""
    import produktdaten as PD
    s = st.session_state
    try:
        p = PD.etp_produkt(s.get(P + "p_kennung"), get)
    except PD.ProduktFehler as e:
        s[P + "p_abruf"] = "fehler:" + str(e)
        return
    for f in ("name", "emittent", "hebel", "kurs", "waehrung", "kosten", "spread"):
        if p.get(f) is not None:
            s[f"{P}p_{f}"] = p[f]
    s[P + "p_kennung"] = p.get("wkn") or s.get(P + "p_kennung")
    s[P + "p_stand"] = (p.get("stand") or "").replace("T", " ")[:16] + " UTC" if p.get("stand") else ""
    if p.get("basiswert") in BASIS:
        s[P + "index"] = p["basiswert"]
    s[P + "p_abruf"] = ("ok:" + f"{p['name']} ({p['emittent']}) von {PD.QUELLE} übernommen. Bitte Währungssicherung und "
                        "Finanzierungskosten aus dem Factsheet/KID prüfen."
                        + (" Nicht geliefert: " + ", ".join(p["fehlt"]) + "." if p["fehlt"] else "")
                        + ("" if p.get("basiswert") in BASIS else " Der Basisindex ist keiner der unterstützten Indizes."))


def _produkt_formular(code, get=None):
    s = st.session_state
    b = _bibliothek()
    if b:
        st.selectbox("Gespeichertes Produkt laden", [""] + sorted(b), key=P + "p_auswahl", on_change=_produkt_laden,
                     format_func=lambda x: x or "– auswählen –")
    st.text_input("WKN oder ISIN", key=P + "p_kennung", max_chars=12, placeholder="z. B. A3GL7E")
    st.button("🔎 Produktdaten automatisch laden", key=P + "p_auto", disabled=get is None,
              on_click=_automatisch_laden, args=(get,),
              help="Lädt Name, Emittent, Hebelfaktor, Kurs, Währung, laufende Kosten und Spread (Quelle: onvista.de).")
    meldung = s.get(P + "p_abruf") or ""
    if meldung.startswith("ok:"):
        st.success(meldung[3:])
    elif meldung.startswith("fehler:"):
        st.warning(meldung[7:] + " Die Felder können von Hand ausgefüllt werden.")
    sp = KU._spalten()
    for i, (f, label, art) in enumerate(FELDER):
        ziel = sp[i % 2]
        if art == "text":
            ziel.text_input(label, key=f"{P}p_{f}")
        else:
            s.setdefault(f"{P}p_{f}", None)
            ziel.number_input(label, step=0.01 if f != "hebel" else 1.0, format="%.2f", key=f"{P}p_{f}")
    st.toggle("Währungsgesichert (kein EUR/USD-Effekt)", key=P + "p_gesichert",
              help="Viele ETPs auf US-Indizes notieren in Euro, sind aber nicht währungsgesichert – dann wirkt der "
                   "EUR/USD-Kurs zusätzlich.")
    st.text_input("Stand der Produktdaten", key=P + "p_stand", placeholder="z. B. 21.11.2026")
    st.button("💾 Produkt speichern", key=P + "p_speichern", on_click=_produkt_speichern)
    st.caption(f"Basisindex: {BASIS[code]} (oben gewählt). Bitte die Produktbedingungen prüfen: manche Produkte haben "
               "Schutzmechanismen (z. B. Intraday-Reset bei starken Bewegungen), die dieses Modell nicht abbildet. "
               "Laufende Kosten werden nur einmal abgezogen; sind sie schon in der Produktperformance enthalten, "
               "hier 0 eintragen.")
    return _produkt()


# ---------------------------------------------------------------------------------------------------- Seite
def _startwerte(code, start):
    s = st.session_state
    s.setdefault(_k(code, "einsatz"), float(E.EINSATZ["standard"]))
    s.setdefault(_k(code, "hebel"), E.HEBEL["standard"])
    s.setdefault(_k(code, "tage"), float(E.HALTEDAUER["standard"]))
    s.setdefault(_k(code, "vola"), float(E.VOLA["standard"]))
    if start and not s.get(_k(code, "ziel")):
        s[_k(code, "ziel")] = float(K.kursziel_standard(start))


def _zuruecksetzen(code):
    s = st.session_state
    for k in [k for k in list(s.keys()) if str(k).startswith(_k(code, ""))]:
        del s[k]
    s[P + "meldung"] = f"Einstellungen für {BASIS[code]} zurückgesetzt."


def _enddatum_uebernehmen(code, boerse):
    s = st.session_state
    d = s.get(_k(code, "ende_d"))
    if d:
        n = max(1, len(BK.handelstage_zwischen(boerse, _heute() + datetime.timedelta(days=1), d)))
        KU._setzen(_k(code, "tage"), float(min(n, E.HALTEDAUER["max"])))


def seite(h):
    st.markdown(KU.CSS, unsafe_allow_html=True)
    s = st.session_state
    _halten()
    if s.get(P + "meldung"):
        st.toast(s.pop(P + "meldung"))
    st.markdown('<div class="ko-kopf"><span class="ko-sym">📈</span><div><b>ETF-/ETP-Hebelrechner</b>'
                '<div>Täglich gehebelte ETFs/ETNs/ETPs simulieren – mit Pfadabhängigkeit und Knock-out-Vergleich'
                '</div></div></div>', unsafe_allow_html=True)
    jetzt = KU._jetzt()
    daten = KU._daten(h)

    # 1. Index
    if s.get(P + "index") not in BASIS:
        s[P + "index"] = "NDX"
    code = st.segmented_control("Basiswert", list(BASIS), key=P + "index", format_func=BASIS.get,
                                width="stretch") or "NDX"
    m = _markt(h, code, daten, jetzt)
    man_an = True
    with st.container(horizontal=True, vertical_alignment="center", key="ko_reihe_markt"):
        if m["kurs"] is not None:
            man_an = st.toggle("Stand manuell eingeben (Referenzwert)", key=_k(code, "man_an"))
        st.button("🔄", key=P + "refresh_btn", help="Marktdaten jetzt aktualisieren", on_click=KU._refresh,
                  args=(h, code if code in K.INDIZES else "NDX"))
    manuell = None
    if man_an:
        s.setdefault(_k(code, "man"), float(round(m["kurs"])) if m.get("kurs") else None)
        manuell = st.number_input("Stand (manuell)", min_value=0.01, step=10.0, format="%.2f", key=_k(code, "man"))
        if not manuell:
            st.info("Bitte einen Stand eingeben – ohne Stand ist keine Berechnung möglich.")
            return
    KU._markt_karte(m, manuell)
    start = float(manuell or m["kurs"])
    fx = K.eurusd(daten)
    _startwerte(code, start)
    boerse = K.INDIZES[code]["boerse"] if code in K.INDIZES else None
    kerzen = _kerzen(h, code)

    # 2. Einsatz
    einsatz = KU._regler("Einsatz (€)", _k(code, "einsatz"), E.EINSATZ["min"], E.EINSATZ["max"], E.EINSATZ["schritt"],
                         "%.0f", fmt_regler="%.0f €")

    # 3. Hebel bzw. Produkt
    s.setdefault(P + "modus", "Freie Hebel-Simulation")
    modus = st.segmented_control("Produkt", ["Freie Hebel-Simulation", "Konkretes ETF-/ETP-Produkt"], key=P + "modus",
                                 width="stretch") or "Freie Hebel-Simulation"
    kosten, spread_pct, gesichert, produkt = 0.0, 0.0, True, None
    if modus.startswith("Freie"):
        if s.get(_k(code, "hebel")) not in HEBEL_OPTIONEN:
            s[_k(code, "hebel")] = E.HEBEL["standard"]
        hebel = st.select_slider("Täglicher Hebel", HEBEL_OPTIONEN, key=_k(code, "hebel"), format_func=_hebel_text)
        with st.expander("Kosten und Währung (optional)"):
            kosten = st.number_input("Laufende Kosten + Finanzierung (% p. a.)", 0.0, 20.0, step=0.1, format="%.2f",
                                     key=_k(code, "kosten"))
            gesichert = not (code in ("NDX", "SPX", "DJI") and st.toggle(
                "EUR/USD-Effekt berücksichtigen (nicht währungsgesichertes Produkt)", key=_k(code, "fx_an")))
    else:
        with st.container(border=True):
            produkt = _produkt_formular(code, h.get("get"))
        if not produkt.get("hebel"):
            st.info("Bitte mindestens den täglichen Hebelfaktor des Produkts eintragen.")
            return
        hebel = float(produkt["hebel"])
        kosten = float(produkt.get("kosten") or 0) + float(produkt.get("finanzierung") or 0)
        spread_pct = float(produkt.get("spread") or 0)
        gesichert = produkt["gesichert"] or code in ("DAX", "BTC")
        st.caption(f"Gerechnet wird mit dem tatsächlichen täglichen Hebel des Produkts: {_hebel_text(hebel)}.")
    if E.pruefe(hebel=hebel):
        st.error(E.pruefe(hebel=hebel)[0])
        return
    fx_faktor = 1.0
    if not gesichert:
        s.setdefault(_k(code, "fx_ziel"), round(fx, 4) if fx else 1.10)
        fx_ziel = st.number_input("EUR/USD am Ende der Haltedauer", 0.5, 2.5, step=0.01, format="%.4f",
                                  key=_k(code, "fx_ziel"), help=f"Aktuell {KU._de(fx, 4) if fx else 'unbekannt'}.")
        if fx:
            fx_faktor = fx / fx_ziel
        else:
            st.warning("Aktueller EUR/USD-Kurs unbekannt – Währungseffekt bleibt unberücksichtigt.")

    # 4. Kursziel
    lo, hi, schritt = K.kursziel_bereich(start)
    ziel = KU._regler("Kursziel", _k(code, "ziel"), lo, hi, schritt, "%.2f", frei=True, fmt_regler="%.0f",
                      hilfe="Regler ±50 % um den aktuellen Stand; im Zahlenfeld ist jedes Kursziel möglich.")
    if ziel <= 0:
        st.error("Das Kursziel muss größer als 0 sein.")
        return

    # 5. Haltedauer + Volatilitaet
    tage = int(KU._regler("Haltedauer (Handelstage)", _k(code, "tage"), E.HALTEDAUER["min"], E.HALTEDAUER["max"], 1,
                          "%.0f", fmt_regler="%.0f Tage"))
    if boerse:
        st.date_input("… oder Enddatum wählen", value=None, key=_k(code, "ende_d"), format="DD.MM.YYYY",
                      min_value=_heute() + datetime.timedelta(days=1), on_change=_enddatum_uebernehmen,
                      args=(code, boerse))
    vola = KU._regler("Volatilität (% p. a.)", _k(code, "vola"), E.VOLA["min"], E.VOLA["max"], E.VOLA["schritt"],
                      "%.0f", fmt_regler="%.0f %%")

    # 6. Kursverlauf
    hist = E.historische_renditen(kerzen)
    arten = [a for a in E.VERLAEUFE if a != "historisch" or len(hist) >= tage]
    if s.get(P + "verlauf") not in arten:
        s[P + "verlauf"] = "schwankend_auf"
    art = st.selectbox("Kursverlauf", arten, key=P + "verlauf", format_func=E.VERLAEUFE.get)
    if "historisch" not in arten:
        st.caption("Historischer Kursverlauf: nicht genug Tageskerzen für diese Haltedauer verfügbar.")
    richtung_passt = (ziel >= start) if art.endswith("_auf") else (ziel <= start) if art.endswith("_ab") else True
    if not richtung_passt:
        st.caption("Hinweis: Das Kursziel passt nicht zur Richtung des gewählten Verlaufs – der Verlauf endet trotzdem "
                   "genau am Kursziel.")

    fehler = E.pruefe(einsatz, start, ziel, hebel, tage, vola)
    if fehler:
        st.error(fehler[0])
        return
    pfad = E.kursverlauf(start, ziel, tage, vola, art, hist)
    gebuehr = einsatz * spread_pct / 100
    r = E.ergebnis(einsatz, pfad, hebel, kosten, fx_faktor, gebuehr)

    # 7. Ergebnis
    _ergebnis_karte(r, hebel, tage, vola, art)

    # 8. Diagramm
    st.markdown("**Verlauf (normiert auf 100)**")
    _diagramm(pfad, hebel, kosten, tage, start_datum=_heute(), boerse=boerse)

    # 9. Szenarien
    st.markdown("**Szenariovergleich – gleicher Start, gleiches Ziel, anderer Weg**")
    szen = E.szenarien(einsatz, start, ziel, tage, vola, hebel, kosten, historische_renditen=hist,
                       arten=list(E.SZENARIO_VERGLEICH) + (["historisch"] if "historisch" in arten else []))
    _szenario_tabelle(szen)
    _zwei_szenarien(szen)

    # Hebelvergleich
    with st.expander("Vergleich verschiedener täglicher Hebel"):
        v = E.hebel_vergleich(einsatz, pfad, kosten_pa=kosten)
        zeilen = "".join(f'<tr class="{"ko-aktiv" if abs(e["hebel"] - hebel) < 1e-9 else ""}"><td>{_hebel_text(e["hebel"])}</td>'
                         f'<td class="{KU._klasse(e["gv"])}">{KU._eur(e["gv"], vz=True)}</td>'
                         f'<td class="{KU._klasse(e["rendite_pct"])}">{KU._pct(e["rendite_pct"])}</td>'
                         f'<td>{KU._pct(e["naiv_pct"])}</td><td>{KU._pct(e["max_dd_pct"], 1, vz=False)}</td></tr>'
                         for e in v)
        st.markdown('<div class="ko-tabwrap"><table class="ko-tab"><tr><th>Hebel</th><th>Gewinn/Verlust</th><th>Rendite'
                    '</th><th>Hebel × Index</th><th>Max. Drawdown</th></tr>' + zeilen + "</table></div>",
                    unsafe_allow_html=True)
        st.caption("„Hebel × Index“ ist die naive Erwartung – die Abweichung zeigt den Effekt der täglichen "
                   "Neugewichtung auf dem gewählten Kursverlauf.")

    # 10. Knock-out-Vergleich
    _ko_vergleich(h, code, einsatz, ziel, tage, hebel, pfad, r, boerse)

    # 11. Backtest
    _backtest(code, kerzen, einsatz, hebel, kosten)

    # Export / Reset
    kopf = {"Basiswert": BASIS[code], "Start": start, "Kursziel": ziel, "Täglicher Hebel": hebel,
            "Einsatz €": einsatz, "Haltedauer Tage": tage, "Volatilität %": vola, "Verlauf": E.VERLAEUFE[art],
            "Kosten % p.a.": kosten, "Simulation": "hypothetisch"}
    zeilen = E.csv_zeilen(kopf, r, szen)
    csv = "Bereich;Bezeichnung;Wert\n" + "\n".join(";".join(str(x).replace(".", ",") if isinstance(x, float) else str(x)
                                                           for x in z) for z in zeilen)
    diag = "Tag;Index (100);ETP (100)\n" + "\n".join(f"{t};{KU._de(i, 4)};{KU._de(p, 4)}"
                                                    for t, (i, p) in enumerate(zip(r["index"], r["produkt"])))
    with st.container(horizontal=True, key="ko_reihe_fuss"):
        st.download_button("⬇️ CSV Szenarien", csv.encode("utf-8-sig"), file_name=f"etp_szenarien_{code}_{_heute()}.csv",
                           mime="text/csv", key=P + "csv")
        st.download_button("⬇️ CSV Diagrammdaten", diag.encode("utf-8-sig"),
                           file_name=f"etp_verlauf_{code}_{_heute()}.csv", mime="text/csv", key=P + "csv_diag")
        st.button("↺ Zurücksetzen", key=P + "reset", on_click=_zuruecksetzen, args=(code,))
    st.caption("Hypothetische Simulation – keine Prognose und keine Anlageberatung. Reale Produkte können durch "
               "Kosten, Tracking-Differenz, Spreads und besondere Produktbedingungen abweichen.")


# ---------------------------------------------------------------------------------------------------- Ergebnis
def _ergebnis_karte(r, hebel, tage, vola, art):
    felder = [("Theoretischer Endwert", KU._eur(r["endwert"])), ("Gesamtrendite", KU._pct(r["rendite_pct"])),
              ("Indexveränderung", KU._pct(r["index_pct"])), ("Täglicher Hebel", _hebel_text(hebel)),
              ("Haltedauer", f"{tage} Handelstage"), ("Volatilität (Annahme)", f"{vola:g} %"),
              ("Max. zwischenzeitlicher Verlust", KU._pct(-r["max_dd_pct"], 1)),
              ("Ungehebelt (Index)", KU._eur(r["ungehebelt_endwert"])), ("Naiv: Hebel × Index", KU._pct(r["naiv_pct"]))]
    st.markdown(f'<div class="ko-karte"><div class="ko-unter">Hypothetische Simulation · {html.escape(E.VERLAEUFE[art])}'
                f' · möglicher Gewinn/Verlust</div><div class="ko-gross {KU._klasse(r["gv"])}">{KU._eur(r["gv"], vz=True)}</div>'
                + ('<div class="ko-unter ko-neg">Totalverlust: eine Tagesbewegung hat den Produktwert auf null gebracht.'
                   '</div>' if r["totalverlust"] else "")
                + '<div class="ko-raster">' + "".join(
                    f"<div>{t}<b class='{KU._klasse(r['rendite_pct']) if t == 'Gesamtrendite' else ''}'>{w}</b></div>"
                    for t, w in felder) + "</div></div>", unsafe_allow_html=True)


def _diagramm(pfad, hebel, kosten, tage, start_datum, boerse):
    import plotly.graph_objects as go
    fig = go.Figure()
    x = list(range(len(pfad)))
    fig.add_scatter(x=x, y=[100 * p / pfad[0] for p in pfad], mode="lines", name="Index (ungehebelt)",
                    line=dict(width=2, color="#A9ACB0"), hovertemplate="Tag %{x}: Index %{y:.1f}<extra></extra>")
    for hb in sorted(set(DIAGRAMM_HEBEL) | {hebel}):
        w = E.produkt_verlauf(pfad, hb, kosten)
        aktiv = abs(hb - hebel) < 1e-9
        fig.add_scatter(x=x, y=w, mode="lines", name=f"täglich {_hebel_text(hb)}", line=dict(width=3.5 if aktiv else 1.8),
                        hovertemplate=f"Tag %{{x}}: {hb:+g}× %{{y:.1f}}<extra></extra>")
        if aktiv:
            i_max, i_min = max(range(len(w)), key=w.__getitem__), min(range(len(w)), key=w.__getitem__)
            fig.add_scatter(x=[i_max, i_min, x[-1]], y=[w[i_max], w[i_min], w[-1]], mode="markers+text",
                            text=[f"Hoch {w[i_max]:.0f}", f"Tief {w[i_min]:.0f}", f"Ende {w[-1]:.0f}"],
                            textposition=["top center", "bottom center", "middle left"], marker=dict(size=8),
                            showlegend=False, hoverinfo="skip")
    ende = ""
    if boerse:
        tage_liste = BK.handelstage_zwischen(boerse, start_datum + datetime.timedelta(days=1),
                                             start_datum + datetime.timedelta(days=int(tage * 1.6) + 10))
        if len(tage_liste) >= tage:
            ende = tage_liste[tage - 1].strftime("%d.%m.%Y")
    fig.add_vline(x=x[-1], line=dict(color="#FBBF24", dash="dash", width=1.5),
                  annotation_text=f"Ziel{(' ' + ende) if ende else ''}", annotation_position="bottom left")
    fig.add_hline(y=100, line=dict(color="#A9ACB0", width=1, dash="dot"))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=40), xaxis_title="Handelstag",
                      yaxis_title="Wert (Start = 100)", hovermode="x unified", legend=dict(orientation="h", y=-0.22))
    st.plotly_chart(UI.chart_stil(fig), use_container_width=True, config={"displayModeBar": False}, key=P + "chart")


def _szenario_tabelle(szen):
    zeilen = ""
    for art, e in szen:
        if not e:
            zeilen += f"<tr><td>{E.VERLAEUFE[art]}</td><td colspan='5'>keine Daten</td></tr>"
            continue
        zeilen += (f"<tr><td>{E.VERLAEUFE[art]}</td><td>{KU._pct(e['index_pct'])}</td>"
                   f"<td class='{KU._klasse(e['rendite_pct'])}'>{KU._pct(e['rendite_pct'])}</td>"
                   f"<td class='{KU._klasse(e['gv'])}'>{KU._eur(e['gv'], vz=True)}</td><td>{KU._eur(e['endwert'])}</td>"
                   f"<td>{KU._pct(e['max_dd_pct'], 1, vz=False)}</td></tr>")
    st.markdown('<div class="ko-tabwrap"><table class="ko-tab"><tr><th>Kursverlauf</th><th>Index</th><th>ETP</th>'
                '<th>Gewinn/Verlust</th><th>Endwert</th><th>Max. Drawdown</th></tr>' + zeilen + "</table></div>",
                unsafe_allow_html=True)
    st.caption("Alle Verläufe starten und enden beim selben Indexstand – unterschiedliche Ergebnisse entstehen allein "
               "durch die tägliche Neugewichtung.")


def _zwei_szenarien(szen):
    gueltig = [(a, e) for a, e in szen if e]
    if len(gueltig) < 2:
        return
    with st.expander("Zwei Szenarien direkt vergleichen"):
        arten = [a for a, _ in gueltig]
        s = st.session_state
        if s.get(P + "vgl_a") not in arten:
            s[P + "vgl_a"] = arten[0]
        if s.get(P + "vgl_b") not in arten:
            s[P + "vgl_b"] = arten[-1]
        sp = KU._spalten()
        a = sp[0].selectbox("Szenario A", arten, key=P + "vgl_a", format_func=E.VERLAEUFE.get)
        b = sp[1].selectbox("Szenario B", arten, key=P + "vgl_b", format_func=E.VERLAEUFE.get)
        d = dict(gueltig)
        spalten = []
        for art in (a, b):
            e = d[art]
            spalten.append((E.VERLAEUFE[art], dict(e, kapital=e["einsatz"], ko_abstand_pct=None, break_even=None)))
        reihen = [("ETP-Rendite", lambda e: KU._pct(e["rendite_pct"]), "rendite_pct"),
                  ("Gewinn/Verlust", lambda e: KU._eur(e["gv"], vz=True), "gv"),
                  ("Endwert", lambda e: KU._eur(e["endwert"]), None),
                  ("Max. Drawdown", lambda e: KU._pct(e["max_dd_pct"], 1, vz=False), None),
                  ("Indexrendite", lambda e: KU._pct(e["index_pct"]), None)]
        kopf = "".join(f"<th>{html.escape(n)}</th>" for n, _ in spalten)
        zeilen = "".join("<tr><td>" + t + "</td>" + "".join(
            f'<td class="{KU._klasse(e[k]) if k else ""}">{f(e)}</td>' for _, e in spalten) + "</tr>"
            for t, f, k in reihen)
        st.markdown(f'<div class="ko-tabwrap"><table class="ko-tab"><tr><th></th>{kopf}</tr>{zeilen}</table></div>',
                    unsafe_allow_html=True)


def _ko_vergleich(h, code, einsatz, ziel, tage, hebel, pfad, r, boerse):
    with st.expander("🎯 Mit Knock-out vergleichen", expanded=False):
        s = st.session_state
        s.setdefault(P + "ko_hebel", float(max(2.0, abs(hebel))))
        s.setdefault(P + "ko_fin", 3.0)
        sp = KU._spalten()
        hk = sp[0].number_input("Anfangshebel des Knock-outs", 1.5, 20.0, step=0.5, format="%.1f", key=P + "ko_hebel")
        fin = sp[1].number_input("Finanzierungskosten KO (% p. a.)", 0.0, 20.0, step=0.5, format="%.1f", key=P + "ko_fin")
        richtung = "long" if hebel > 0 else "short"
        ko = E.ko_auf_pfad(einsatz, pfad, hk, richtung, fin)
        werte = [("Gewinn/Verlust", KU._eur(r["gv"], vz=True), KU._eur(ko["gv"], vz=True)),
                 ("Endwert", KU._eur(r["endwert"]), KU._eur(ko["endwert"])),
                 ("Rendite", KU._pct(r["rendite_pct"]), KU._pct(ko["rendite_pct"])),
                 ("Max. Drawdown", KU._pct(r["max_dd_pct"], 1, vz=False), KU._pct(ko["max_dd_pct"], 1, vz=False))]
        zeilen = "".join(f"<tr><td>{t}</td><td>{a}</td><td>{b}</td></tr>" for t, a, b in E.VERGLEICH_ZEILEN)
        zeilen += "".join(f"<tr><td>{t} (simuliert)</td><td>{a}</td><td>{b}</td></tr>" for t, a, b in werte)
        st.markdown('<div class="ko-tabwrap"><table class="ko-tab"><tr><th>Kennzahl</th><th>Daily Leveraged ETP</th>'
                    f'<th>Knock-out ({richtung.capitalize()}, {hk:g}×)</th></tr>{zeilen}</table></div>',
                    unsafe_allow_html=True)
        if ko["ko_tag"] is not None:
            st.error(f"Der Knock-out wäre an Handelstag {ko['ko_tag']} ausgelöst worden (Schwelle ≈ "
                     f"{KU._de(ko['ko_schwelle'])}) – trotz gleichem Endstand ist er wertlos.")
        st.caption("Beide Produkte auf DEMSELBEN simulierten Tagesverlauf. Knock-out vereinfacht: Basispreis = Schwelle, "
                   "geprüft an Schlusskursen (intraday kann die Schwelle früher berührt werden).")
        if code in K.INDIZES and h.get("zum_ko"):
            termin = None
            if boerse:
                t_liste = BK.handelstage_zwischen(boerse, _heute() + datetime.timedelta(days=1),
                                                  _heute() + datetime.timedelta(days=int(tage * 1.6) + 10))
                termin = t_liste[tage - 1] if len(t_liste) >= tage else None
            st.button("➜ Im Knock-out-Rechner öffnen", key=P + "zum_ko_btn", on_click=h["zum_ko"],
                      args=({"index": code, "einsatz": einsatz, "ziel": ziel, "termin": termin,
                             "richtung": "Long" if hebel > 0 else "Short", "hebel": float(min(hk, 20.0))},),
                      help="Übernimmt Basiswert, Einsatz, Kursziel, Zieltermin und Richtung in den Knock-out-Rechner.")


def _backtest(code, kerzen, einsatz, hebel, kosten):
    with st.expander("📜 Historische Simulation (Backtest)"):
        if len(kerzen) < 2:
            st.info("Für diesen Basiswert liegen keine historischen Tageskerzen vor.")
            return
        s = st.session_state
        erste = datetime.date.fromisoformat(kerzen[0][0])
        letzte = datetime.date.fromisoformat(kerzen[-1][0])
        s.setdefault(P + "bt_von_d", max(erste, letzte - datetime.timedelta(days=365)))
        s.setdefault(P + "bt_bis_d", letzte)
        sp = KU._spalten(3)
        von = sp[0].date_input("Startdatum", key=P + "bt_von_d", min_value=erste, max_value=letzte, format="DD.MM.YYYY")
        bis = sp[1].date_input("Enddatum", key=P + "bt_bis_d", min_value=erste, max_value=letzte, format="DD.MM.YYYY")
        s.setdefault(P + "bt_hebel", hebel)
        if s[P + "bt_hebel"] not in HEBEL_OPTIONEN:
            s[P + "bt_hebel"] = 3
        hb = sp[2].selectbox("Täglicher Hebel", HEBEL_OPTIONEN, key=P + "bt_hebel", format_func=_hebel_text)
        try:
            b = E.backtest(kerzen, von.isoformat(), bis.isoformat(), hb, einsatz, kosten)
        except ValueError as ex:
            st.warning(str(ex))
            return
        felder = [("Endwert", KU._eur(b["endwert"])), ("Gesamtrendite", KU._pct(b["rendite_pct"])),
                  ("Index ungehebelt", KU._pct(b["index_pct"])), ("Max. Drawdown ETP", KU._pct(-b["max_dd_pct"], 1)),
                  ("Max. Drawdown Index", KU._pct(-b["index_max_dd_pct"], 1)),
                  ("Bester Tag", f"{KU._pct(b['bester_tag'][1])} ({b['bester_tag'][0]})"),
                  ("Schlechtester Tag", f"{KU._pct(b['schlechtester_tag'][1])} ({b['schlechtester_tag'][0]})")]
        st.markdown(f'<div class="ko-karte"><div class="ko-unter">Modellrechnung auf echten Tageskerzen · '
                    f'{b["von"]} bis {b["bis"]} · {_hebel_text(hb)}</div><div class="ko-gross {KU._klasse(b["gv"])}">'
                    f'{KU._eur(b["gv"], vz=True)}</div><div class="ko-raster">'
                    + "".join(f"<div>{t}<b>{w}</b></div>" for t, w in felder) + "</div></div>", unsafe_allow_html=True)
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_scatter(x=b["daten"], y=b["index"], mode="lines", name="Index", line=dict(color="#A9ACB0"))
        fig.add_scatter(x=b["daten"], y=b["produkt"], mode="lines", name=f"Modell {_hebel_text(hb)}")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=30), hovermode="x unified",
                          legend=dict(orientation="h", y=-0.2), yaxis_title="Start = 100")
        st.plotly_chart(UI.chart_stil(fig), use_container_width=True, config={"displayModeBar": False},
                        key=P + "bt_chart")
        st.caption("Modellrechnung aus den Tagesrenditen des Cash-Index (Quelle: Yahoo Finance) – keine realen "
                   "Produktkurse. Echte historische Produktkurse liegen der App nicht vor; reale ETPs weichen durch "
                   "Kosten und Tracking-Differenz ab.")
