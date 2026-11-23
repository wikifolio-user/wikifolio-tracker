"""Pyramidenmanager - Ansicht "Märkte → Pyramiden" (Etappe 2). Rechnungen: pyramide.py, Daten: pyramide_daten.py.

Bereiche: Index-Trendscanner (Trend-Score, Gap-Wert, Fear & Greed, kombinierter Wert, Einstiegssignal je Index)
und "Meine Pyramiden" (Überblick, Nachkauf prüfen & erfassen per WKN, Einstellungen je Pyramide, Zeitleiste).
Reine Buchfuehrung und Signale - es werden keine Orders ausgeloest, das Depot wird nicht veraendert.
h = {"ohlc", "sentiment", "indizes": () -> Datei, "lesen": (pfad, default) -> (daten, ok),
     "aktualisiere": (pfad, aendern, default, msg) -> (ok, neu), "upfad": (basis) -> pfad, "speichern": bool,
     "get": requests.get (Produktdaten), "oeffnen": (ansicht_id) -> None (optional, Links zu Gap / Fear & Greed)}"""
import datetime
import html
import logging
import uuid

import streamlit as st

import ko_rechner as KO
import pyramide as P
import pyramide_daten as D
import ui_stil as UI

K = "pyr_"
DATEI = "state/pyramiden.json"
CODES = list(D.ZUORDNUNG)
STUFE_FARBE = {"unterstützt": "#34D399", "neutral": "#EAB308", "Vorsicht": "#F87171", "fehlt": "#A9ACB0",
               "veraltet": "#A9ACB0", "aus": "#A9ACB0"}
EINST_GRUPPEN = [
    ("Signale", [("einstieg_ab", "Trend-Score für Einstieg/Nachkauf ab", 1.0), ("ausstieg_unter", "Ausstieg, wenn Trend-Score unter", 1.0),
                 ("max_stufen", "Höchstzahl Stufen", 1.0), ("groesse_faktor", "Tranchenfaktor je Stufe", 0.05),
                 ("groesse_min", "Mindestanteil der Grundgröße", 0.05)]),
    ("ATR", [("atr_tage", "ATR-Länge (Tage)", 1.0), ("nachkauf_atr", "Nachkauf ab + … ATR über letztem Kauf", 0.25),
             ("stop_anfang_atr", "Anfangsstop: Kaufkurs − … ATR", 0.25),
             ("stop_nachzieh_atr", "Nachzieh-Stop: Hoch − … ATR", 0.25),
             ("ko_puffer_atr", "KO-Schwelle mind. … ATR unter dem Stop", 0.25),
             ("gap_naehe_atr", "Gaps zählen innerhalb … ATR", 0.25)]),
    ("Risiko & Hebel", [("risiko_tranche_pct", "Max. Risiko je neuer Tranche (% Kapital)", 0.1),
                        ("risiko_gesamt_pct", "Max. Risiko gesamt bis Stop (% Kapital)", 0.5),
                        ("ko_kapital_max_pct", "Max. Kapitalanteil in KO-Zertifikaten (%)", 5.0),
                        ("hebel_max", "Obergrenze vorgeschlagener Hebel", 0.5)]),
]

CSS = """<style>
.py-raster { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin:6px 0 8px; }
@media (max-width: 1100px) { .py-raster { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width: 640px) { .py-raster { grid-template-columns:1fr; } }
.py-karte { border:1px solid rgba(255,255,255,.12); border-radius:14px; padding:10px 12px;
    background:rgba(255,255,255,.03); min-width:0; }
.py-kopf { display:flex; justify-content:space-between; align-items:baseline; gap:6px; flex-wrap:wrap; }
.py-name { font-size:.88rem; font-weight:700; color:#E8ECF6; }
.py-sig { font-size:.72rem; font-weight:700; padding:2px 8px; border-radius:10px; border:1px solid currentColor; }
.py-zeile { display:flex; justify-content:space-between; gap:8px; font-size:.78rem; color:#A9ACB0; margin-top:5px; }
.py-zeile b { color:#ffffff; font-variant-numeric:tabular-nums; text-align:right; }
.py-bahn { height:6px; border-radius:3px; background:rgba(127,127,127,.25); overflow:hidden; margin-top:3px; }
.py-bahn > div { height:100%; border-radius:3px; background:#7c9cff; }
.py-meta { font-size:.68rem; color:#A9ACB0; margin-top:6px; }
.py-pruef { display:grid; grid-template-columns:auto 1fr; gap:4px 10px; font-size:.84rem; margin:6px 0; }
.py-pruef .e { font-weight:700; white-space:nowrap; }
.py-pruef .t { color:#C9CED6; }
</style>"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _de(x, n=1):
    return KO.de(x, n) if x is not None else "–"


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return "–"


# ---------------------------------------------------------------------------------------------------- Daten
@st.cache_data(ttl=600, show_spinner=False, max_entries=6)
def _analyse(_ohlc, _sent, o_key, s_key, zeit_key):
    """Analysewerte je Index (Trend, ATR, Gaps, Fear & Greed). Die teuren Fear-&-Greed-Verlaeufe kommen aus dem
    Zwischenspeicher der Fear-&-Greed-Ansicht."""
    try:
        import fear_greed_ui
        eigene = fear_greed_ui._eigene(_ohlc, o_key)
    except Exception:
        eigene = None
    return D.index_analyse(_ohlc, _sent, datetime.datetime.fromisoformat(zeit_key), eigene=eigene)


def _laden(h):
    try:
        d, ok = h["lesen"](h["upfad"](DATEI), {"pyramiden": []})
    except Exception:
        d, ok = {"pyramiden": []}, False
    if not isinstance(d, dict) or not isinstance(d.get("pyramiden"), list):
        d = {"pyramiden": []}
    return d, ok


def _speichern(h, aendern, text):
    """aendern(liste_der_pyramiden) -> neue Liste. -> True/False"""
    if not h.get("speichern"):
        st.session_state[K + "meldung"] = ("warn", "Speichern ist gerade nicht möglich (kein Datenspeicher).")
        return False

    def f(alt):
        alt = alt if isinstance(alt, dict) and isinstance(alt.get("pyramiden"), list) else {"pyramiden": []}
        return {"pyramiden": aendern(list(alt["pyramiden"]))}
    try:
        ok, _ = h["aktualisiere"](h["upfad"](DATEI), f, {"pyramiden": []}, f"pyramiden: {text} [skip ci]")
    except Exception as ex:
        logging.warning("Pyramiden: Speichern fehlgeschlagen: %s", ex)
        ok = False
    st.session_state[K + "meldung"] = ("ok", f"Gespeichert: {text}.") if ok else \
        ("warn", "Speichern fehlgeschlagen – bitte erneut versuchen.")
    return bool(ok)


def _ersetzen(pyr):
    return lambda liste: [pyr if p.get("id") == pyr["id"] else p for p in liste]


# ---------------------------------------------------------------------------------------------------- Scanner
def _hinweis(teil):
    stufe = (teil or {}).get("stufe", "fehlt")
    if (teil or {}).get("status") == "veraltet":
        stufe = "veraltet"
    return stufe, STUFE_FARBE.get(stufe, "#A9ACB0")


def _scanner_karte(a, b, kurs_info):
    t = b["trend"]
    sig = "Einstiegssignal" if b["einstieg"] else "kein Signal"
    sig_farbe = "#34D399" if b["einstieg"] else "#A9ACB0"
    trend_txt = "–" if not t else f"{t['score']:.0f} / 100" + ("" if b["trend_gilt"] else " (veraltet)")
    gap = b["gap"]
    g_stufe, g_farbe = _hinweis(gap)
    fg = b["fg"]
    f_stufe, f_farbe = _hinweis(fg)
    komb = b["kombiniert"]
    zeilen = [("Trend-Score", trend_txt),
              ("Gap-Wert (abgeleitet)", f'<span style="color:{g_farbe}">{_de(gap["wert"], 0)} · {g_stufe}</span>'),
              ("Fear & Greed (Index)", f'{_de(fg["original"], 0)} {_e(fg.get("deutung") or "")}'),
              ("→ Einstiegswert", f'<span style="color:{f_farbe}">{_de(fg["wert"], 0)} · {f_stufe}</span>'),
              ("Kombiniert (70/20/10)", _de(komb["wert"], 0) if komb["wert"] is not None else
               f'<span title="{_e(komb["grund"])}">nicht berechenbar</span>')]
    if b.get("us_umfeld"):
        us = b["us_umfeld"]
        zeilen.append(("US-Umfeld (CNN, US-weit)", f'{_de(us["original"], 0)} {_e(us.get("deutung") or "")}'))
    breite = 0 if not t else t["score"]
    stand = f'Letzte Kerze {_datum(a["letzte_kerze"])}' + (
        "" if a["status"] == "aktuell" else f' · <span style="color:#FBBF24">{a["status"]}</span>')
    kurs = f'{_de(kurs_info.get("kurs"), 0)}' if kurs_info.get("kurs") else _de(a["kurs"], 0)
    return (f'<div class="py-karte"><div class="py-kopf"><span class="py-name">{_e(a["name"])} · {kurs}</span>'
            f'<span class="py-sig" style="color:{sig_farbe}">{sig}</span></div>'
            f'<div class="py-bahn" title="Trend-Score"><div style="width:{breite:.0f}%"></div></div>'
            + "".join(f'<div class="py-zeile"><span>{n}</span><b>{w}</b></div>' for n, w in zeilen)
            + f'<div class="py-meta">{stand} · ATR {_de(a["atr"], 0)} Pkt.'
            + ("" if b["einstieg"] else "<br>" + _e(" ".join(b["einstieg_gruende"][:2])))
            + (f"<br>{_e(komb['grund'])}" if komb["wert"] is None else "") + "</div></div>")


def _scanner(h, analyse, indizes, jetzt):
    st.markdown("**Index-Trendscanner**")
    karten = []
    for code in CODES:
        a = analyse[code]
        b = D.bewertung(a)
        karten.append(_scanner_karte(a, b, KO.marktdaten(indizes, code, jetzt)))
    st.markdown('<div class="py-raster">' + "".join(karten) + "</div>", unsafe_allow_html=True)
    if h.get("oeffnen"):
        with st.container(horizontal=True, key=K + "reihe_links"):
            st.button("🕳️ Gap Analyzer öffnen", key=K + "zu_gap", on_click=h["oeffnen"], args=("gap",))
            st.button("🌡️ Fear & Greed öffnen", key=K + "zu_fg", on_click=h["oeffnen"], args=("fg",))
    st.caption("Trend-Score aus abgeschlossenen Tageskerzen (Lage, Steigung, Momentum, 52-Wochen-Hoch, Stabilität). "
               "Gap-Wert aus den offenen Gaps des Gap Analyzers (abgeleitet, kein Signal). Fear & Greed: eigener "
               "Indexwert, Einstiegswert konträr (100 − F&G); CNN steht nur als US-weites Umfeld dabei. Kombiniert "
               "nur, wenn alle Teile aktuell sind. Startwerte – eigene Werte je Pyramide unter „Einstellungen“.")


# ---------------------------------------------------------------------------------------------------- Pyramiden
def _neu_formular(h, jetzt):
    with st.expander("➕ Neue Pyramide anlegen", expanded=False):
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        idx = sp[0].selectbox("Index", CODES, key=K + "neu_index", format_func=lambda c: KO.INDIZES[c]["name"])
        name = sp[1].text_input("Name", key=K + "neu_name", placeholder=KO.INDIZES[idx]["name"] + "-Pyramide")
        kap = sp[2].number_input("Pyramidenkapital (€)", 100.0, 10_000_000.0, value=10_000.0, step=500.0,
                                 key=K + "neu_kapital")
        if st.button("Pyramide anlegen", key=K + "neu_btn"):
            try:
                p = P.neue_pyramide(uuid.uuid4().hex[:8], idx, name, kap, jetzt.date().isoformat())
            except ValueError as ex:
                st.error(str(ex))
                return
            if _speichern(h, lambda liste: liste + [p], f"Pyramide {p['name']} angelegt"):
                st.session_state[K + "wahl"] = p["id"]
                st.rerun()


def _ueberblick(h, pyr, s, a):
    r = s["risiko"]
    kap = pyr["kapital"]
    cfg = s["einstellungen"]
    sp = st.columns(4) if not UI.ist_smartphone() else st.columns(2)
    sp[0].metric("Stufe", f"{s['stufe']} / {s['max_stufen']}")
    sp[1].metric("Stop (gemeinsam)", _de(s["stop"], 0),
                 None if not (s["stop"] and s["kurs"]) else f"{_de((s['kurs'] / s['stop'] - 1) * 100, 1)} % Abstand",
                 delta_color="off")
    sp[2 % len(sp)].metric("Nächste Nachkaufmarke", _de(s["nachkauf_marke"], 0) if s["stufe"] else "Einstiegssignal")
    sp[3 % len(sp)].metric("Risiko bis Stop", f"{_de(r['gesamt'], 0)} €" if r else "–",
                           f"{_de(r['gesamt_pct'], 2)} % (Grenze {_de(cfg['risiko_gesamt_pct'], 1)} %)" if r else None,
                           delta_color="off")
    if s["ausstieg"]:
        st.error("🚪 Ausstiegssignal: " + " ".join(s["ausstieg_gruende"]) + " (nur Signal – es wird nichts verkauft)")
    if not pyr["tranchen"]:
        st.info("Noch keine Tranche erfasst. Unter „Nachkauf prüfen & erfassen“ die erste Stufe prüfen und – nach "
                "dem tatsächlichen Kauf – erfassen.")
        return
    zeilen = []
    for t, z in zip(pyr["tranchen"], r["tranchen"]):
        ko = z["ko_schwelle"]
        zeilen.append({"Stufe": t["stufe"], "Datum": t.get("datum") or "", "Art": "KO" if t["art"] == "ko" else "direkt",
                       "WKN": t.get("wkn") or "", "Stück": t["stueck"], "Kaufkurs €": round(t["kaufkurs"], 3),
                       "Index beim Kauf": round(t["index_kauf"], 1), "Stop": round(z["stop"], 1) if z["stop"] else None,
                       "KO-Schwelle": round(ko, 1) if ko else None,
                       "Abstand KO %": round((s["kurs"] / ko - 1) * 100, 2) if ko and s["kurs"] else None,
                       "Einsatz €": round(z["einsatz"], 2), "Wert €": round(z["wert"], 2),
                       "G/V €": round(z["wert"] - z["einsatz"], 2), "Risiko bis Stop €": round(z["risiko"], 2)})
    import pandas as pd
    st.dataframe(pd.DataFrame(zeilen), hide_index=True, width="stretch", key=K + "tranchen_tab")
    gv = r["wert"] - sum(z["einsatz"] for z in r["tranchen"])
    st.caption(f"Wert gesamt {_de(r['wert'], 0)} € · G/V {'+' if gv >= 0 else ''}{_de(gv, 0)} € · KO-Kapital "
               f"{_de(r['ko_kapital'], 0)} € ({_de(r['ko_kapital_pct'], 1)} % von {_de(kap, 0)} €) · Index "
               f"{_de(s['kurs'], 0)} · ATR({cfg['atr_tage']}) {_de(s['atr'], 0)}. Werte modellhaft (KO: innerer Wert "
               "ohne Spread, Euro/Dollar aktuell) – keine Depotbewertung.")


def _produkt_laden(h, kennung):
    import produktdaten
    return produktdaten.ko_produkt(kennung, h["get"])


def _nachkauf(h, pyr, s, a, b, eurusd, jetzt):
    ss = st.session_state
    cfg = s["einstellungen"]
    art = st.segmented_control("Art der Tranche", ["ko", "direkt"], key=K + "art", default="ko",
                               format_func=lambda x: "KO-Zertifikat" if x == "ko" else "direkt (Index-ETF/-Fonds)") or "ko"
    produkt = None
    if art == "ko":
        sp = st.columns([3, 1]) if not UI.ist_smartphone() else [st.container(), st.container()]
        kennung = sp[0].text_input("WKN oder ISIN des KO-Zertifikats", key=K + "wkn", placeholder="z. B. MK487D")
        if sp[1].button("Daten laden", key=K + "wkn_btn", width="stretch") and kennung:
            try:
                ss[K + "produkt"] = _produkt_laden(h, kennung)
                ss[K + "produkt_fehler"] = None
            except Exception as ex:
                ss[K + "produkt"] = None
                ss[K + "produkt_fehler"] = str(ex) or type(ex).__name__
        if ss.get(K + "produkt_fehler"):
            st.warning(f"Produktdaten nicht geladen: {ss[K + 'produkt_fehler']} – bitte unten von Hand eingeben.")
        p = dict(ss.get(K + "produkt") or {})
        if p:
            st.caption(f"{_e(p.get('name'))} · {_e(p.get('emittent'))} · Quelle {_e(p.get('quelle'))}, Stand "
                       f"{_e(str(p.get('stand') or '')[:16])}" + (f" · fehlt: {', '.join(p['fehlt'])}" if p.get("fehlt") else ""))
        with st.expander("Produktdaten (aus WKN-Abruf oder von Hand)", expanded=not p):
            sp = st.columns(4) if not UI.ist_smartphone() else [st.container() for _ in range(4)]
            basis = sp[0].number_input("Basispreis", 0.0, value=float(p.get("basispreis") or 0.0), step=10.0,
                                       key=K + f"basis_{p.get('wkn')}")
            ko = sp[1].number_input("KO-Schwelle", 0.0, value=float(p.get("ko_schwelle") or 0.0), step=10.0,
                                    key=K + f"ko_{p.get('wkn')}")
            bezug = sp[2].number_input("Bezugsverhältnis", 0.0, value=float(p.get("bezug") or 0.01), step=0.001,
                                       format="%.4f", key=K + f"bezug_{p.get('wkn')}")
            brief = sp[3].number_input("Briefkurs €", 0.0, value=float(p.get("brief") or 0.0), step=0.01,
                                       key=K + f"brief_{p.get('wkn')}")
        produkt = {**p, "basiswert": p.get("basiswert") or pyr["index"], "richtung": p.get("richtung") or "long",
                   "basispreis": basis, "ko_schwelle": ko, "bezug": bezug, "brief": brief,
                   "finanzierung_pct": p.get("finanzierung_pct") or 0.0, "quanto": bool(p.get("quanto"))}
    sp = st.columns(4) if not UI.ist_smartphone() else [st.container() for _ in range(4)]
    stueck = sp[0].number_input("Stück", 0.0, value=None, step=1.0, key=K + "stueck", placeholder="0")
    kurs_vorschlag = (produkt or {}).get("brief") if art == "ko" else None
    kaufkurs = sp[1].number_input("Kaufkurs je Stück €", 0.0, value=float(kurs_vorschlag) if kurs_vorschlag else None,
                                  step=0.01, key=K + f"kaufkurs_{art}", placeholder="0,00")
    idx_kauf = sp[2].number_input("Indexstand beim Kauf", 0.0, value=float(s["kurs"] or 0.0), step=1.0,
                                  key=K + "index_kauf")
    datum = sp[3].date_input("Kaufdatum", value=jetzt.date(), key=K + "datum", format="DD.MM.YYYY")
    neu = None
    if stueck and kaufkurs and idx_kauf:
        neu = {"art": art, "stueck": stueck, "kaufkurs": kaufkurs, "index_kauf": idx_kauf,
               "datum": datum.isoformat(), "wkn": (produkt or {}).get("wkn") or (ss.get(K + "wkn") or "").upper() or None,
               "name": (produkt or {}).get("name"), "produkt": produkt}
    # Pruefung (Ansicht der Pyramide: deren Einstellungen und ATR-Laenge)
    gap = P.gap_wert(a["gap_daten"], a["kurs"], s["atr"], cfg)
    fg = P.fg_einstiegswert(a["fg_index"], cfg)
    trend = a["trend"] if a["status"] == "aktuell" else None
    e = P.nachkauf_pruefung(dict(pyr, hoechst=s["hoechst"]), trend, s["atr"], gap, fg, neu, s["kurs"],
                            stop_bisher=s["stop"], eurusd=eurusd, cfg=cfg)
    komb = P.kombiniert(trend, gap, fg, cfg)
    st.markdown("**Prüfung vor dem Nachkauf**" + (" ✅ alle Pflichtprüfungen bestanden" if e["erlaubt"] else
                                                   " ⛔ mindestens eine Pflichtprüfung nicht bestanden"))
    symbol = {"ok": "✅", "nein": "⛔", "unterstützt": "🟢", "neutral": "🟡", "Vorsicht": "🟠", "fehlt": "⚪",
              "veraltet": "⚪", "aus": "⚪"}
    st.markdown('<div class="py-pruef">' + "".join(
        f'<div class="e">{symbol.get(x["ergebnis"], "•")} {x["nr"]:g}. {_e(x["name"])}</div>'
        f'<div class="t">{"Pflicht" if x["art"] == "pflicht" else "Hinweis"}: {_e(x["text"])}</div>'
        for x in e["pruefungen"]) + "</div>", unsafe_allow_html=True)
    rv, rn = e["risiko_vor"], e["risiko_nach"]
    hb = e["hebel"]
    st.caption(f"Risiko bis Stop vor dem Kauf {_de(rv['gesamt'], 0)} € ({_de(rv.get('gesamt_pct'), 2)} %) → nach dem "
               f"Kauf {_de(rn['gesamt'], 0)} € ({_de(rn.get('gesamt_pct'), 2)} %) · Stop {_de(e['stop'], 0)} · "
               f"zum Stop passender Hebel bis {_de(hb.get('passend'), 1)} (KO höchstens {_de(hb.get('ko_max'), 0)})"
               + (f" · gewählter Hebel {_de(hb['gewaehlt'], 1)}" if hb.get("gewaehlt") else "")
               + f" · kombinierter Wert {_de(komb['wert'], 0) if komb['wert'] is not None else '– (' + komb['grund'] + ')'}"
               + f" · nächste Tranche laut Pyramide {_de((s['naechste_groesse'] or 0) * 100, 0)} % der Grundgröße.")
    st.caption("Ein guter kombinierter Wert überstimmt nie eine nicht bestandene Pflichtprüfung. Die Erfassung ist "
               "reine Buchführung des tatsächlich getätigten Kaufs – es wird keine Order ausgelöst.")
    if st.button("Tranche erfassen (gekauft)", key=K + "erfassen_btn", disabled=neu is None, type="primary"):
        try:
            neue = P.tranche_hinzufuegen(pyr, neu, s["atr"], cfg)
        except ValueError as ex:
            st.error(str(ex))
            return
        if not e["erlaubt"]:
            neue["ereignisse"][-1]["text"] += " – erfasst trotz nicht bestandener Pflichtprüfung"
        if _speichern(h, _ersetzen(neue), f"Stufe {len(neue['tranchen'])} erfasst"):
            for k in ("stueck", "kaufkurs_ko", "kaufkurs_direkt"):
                ss.pop(K + k, None)
            st.rerun()


def _einstellungen(h, pyr):
    ss = st.session_state
    cfg = P.cfg_fuer(pyr)
    pid = pyr["id"]
    neu = {}
    for titel, felder in EINST_GRUPPEN:
        st.markdown(f"**{titel}**")
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        for i, (key, text, schritt) in enumerate(felder):
            lo, hi = P.GRENZEN[key]
            ganz = key in P.GANZZAHL
            neu[key] = sp[i % len(sp)].number_input(
                text, int(lo) if ganz else float(lo), int(hi) if ganz else float(hi),
                value=int(cfg[key]) if ganz else float(cfg[key]), step=int(schritt) if ganz else float(schritt),
                key=K + f"e_{pid}_{key}", help=f"Startwert {P.STANDARD[key]} · erlaubt {lo}–{hi}")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    auto = sp[0].toggle("Hebel automatisch (passend zum Stop)", value=cfg["hebel"] is None, key=K + f"e_{pid}_auto")
    neu["hebel"] = None if auto else sp[1].number_input("Gewünschter Hebel", 1.0, 20.0,
                                                        value=float(cfg["hebel"] or 5.0), step=0.5,
                                                        key=K + f"e_{pid}_hebel")
    st.markdown("**Fear & Greed und kombinierter Wert**")
    neu["fg_modus"] = st.segmented_control("Einstiegswert aus Fear & Greed", list(P.FG_MODI), default=cfg["fg_modus"],
                                           format_func=P.FG_MODI.get, key=K + f"e_{pid}_fg") or cfg["fg_modus"]
    sp = st.columns(3)
    neu["gewichte"] = {g: sp[i].number_input(t, 0.0, 100.0, value=float(cfg["gewichte"][g]), step=5.0,
                                             key=K + f"e_{pid}_w_{g}")
                       for i, (g, t) in enumerate((("trend", "Gewicht Trend"), ("gap", "Gewicht Gap"),
                                                   ("fg", "Gewicht F&G")))}
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    if sp[0].button("Einstellungen speichern", key=K + "e_speichern_btn", type="primary"):
        geaendert = {k: v for k, v in neu.items() if v != P.STANDARD.get(k)}
        p = dict(pyr, einstellungen=geaendert)
        p["ereignisse"] = pyr["ereignisse"] + [{"datum": datetime.date.today().isoformat(), "art": "einstellungen",
                                                "text": "Einstellungen geändert."}]
        if _speichern(h, _ersetzen(p), "Einstellungen"):
            st.rerun()
    if sp[1].button("Auf Startwerte zurücksetzen", key=K + "e_reset_btn"):
        for k in [k for k in ss if str(k).startswith(K + f"e_{pid}_")]:
            ss.pop(k, None)
        if _speichern(h, _ersetzen(dict(pyr, einstellungen={})), "Startwerte"):
            st.rerun()
    st.caption("Die Einstellungen gelten nur für diese Pyramide. Werte außerhalb der erlaubten Bereiche werden auf die "
               "Grenze gesetzt. Ein Hebel über dem zum Stop passenden Hebel wird gewarnt, nicht gesperrt.")


def _zeitleiste(pyr, s, kerzen):
    import plotly.graph_objects as go
    start = pyr["start"]
    ab = (datetime.date.fromisoformat(start) - datetime.timedelta(days=45)).isoformat()
    sicht = [k for k in kerzen if k[0] >= ab]
    if not sicht:
        st.info("Für den Zeitraum der Pyramide liegen keine Tageskerzen vor.")
        return
    fig = go.Figure(go.Scatter(x=[k[0] for k in sicht], y=[k[4] for k in sicht], name="Index (Schluss)",
                               line=dict(color=UI.AKZENT, width=2)))
    v = [x for x in s["verlauf"] if x[3] is not None]
    if v:
        fig.add_scatter(x=[x[0] for x in v], y=[x[3] for x in v], name="Nachzieh-Stop", line=dict(color="#F87171",
                                                                                                 dash="dash", width=1.5))
    tr = pyr["tranchen"]
    if tr:
        fig.add_scatter(x=[t.get("datum") for t in tr], y=[t["index_kauf"] for t in tr], mode="markers+text",
                        text=[f"S{t['stufe']}" for t in tr], textposition="top center", name="Käufe",
                        marker=dict(size=11, color="#FBBF24", symbol="triangle-up"))
        ko = [(t.get("datum"), KO.basispreis_am(t["produkt"], 0)[1]) for t in tr if t["art"] == "ko"]
        if ko:
            fig.add_scatter(x=[d for d, _ in ko], y=[x for _, x in ko], mode="markers", name="KO-Schwellen",
                            marker=dict(size=8, color="#A78BFA", symbol="x"))
    if s["nachkauf_marke"]:
        fig.add_hline(y=s["nachkauf_marke"], line=dict(color="#34D399", dash="dot", width=1.2),
                      annotation_text=f"Nachkaufmarke {_de(s['nachkauf_marke'], 0)}", annotation_position="top left")
    fig.add_vline(x=start, line=dict(color="#A9ACB0", dash="dot", width=1))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=30), legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), width="stretch", key=K + "zeit_chart",
                    config={"displayModeBar": False})
    st.markdown("**Ereignisse**")
    for ev in reversed(pyr.get("ereignisse") or []):
        st.markdown(f"- {_datum(ev.get('datum'))}: {_e(ev.get('text'))}")


def _verwalten(h, pyr):
    ss = st.session_state
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    if pyr["status"] == "offen" and sp[0].button("Pyramide schließen (alle Tranchen verkauft)", key=K + "schliessen_btn"):
        p = dict(pyr, status="geschlossen", ende=datetime.date.today().isoformat())
        p["ereignisse"] = pyr["ereignisse"] + [{"datum": p["ende"], "art": "ende", "text": "Pyramide geschlossen."}]
        if _speichern(h, _ersetzen(p), "Pyramide geschlossen"):
            st.rerun()
    bestaetigt = sp[1].checkbox("Löschen bestätigen", key=K + f"loesch_ok_{pyr['id']}")
    if sp[1].button("Pyramide löschen", key=K + "loeschen_btn", disabled=not bestaetigt):
        if _speichern(h, lambda liste: [p for p in liste if p.get("id") != pyr["id"]], "Pyramide gelöscht"):
            ss.pop(K + "wahl", None)
            st.rerun()


def seite(h):
    st.markdown(CSS, unsafe_allow_html=True)
    ss = st.session_state
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    st.markdown("### 🔺 Pyramidenmanager")
    st.caption("Gestaffelte Long-Käufe auf Nasdaq 100, DAX 40, S&P 500 und Dow Jones – Signale, Stops, Risiko und "
               "Buchführung. Es werden keine Orders ausgelöst. Keine Anlageberatung.")
    try:
        ohlc = h["ohlc"]() or {}
        sent = h["sentiment"]() or {}
        indizes = h["indizes"]() or {}
    except Exception:
        ohlc, sent, indizes = {}, {}, {}
    if not (ohlc.get("indizes") if isinstance(ohlc, dict) else None):
        st.warning("Noch keine Tageskerzen vorhanden – ohne sie kann der Pyramidenmanager nichts berechnen (es werden "
                   "keine Werte geschätzt).")
        return
    analyse = _analyse(ohlc, sent, str(ohlc.get("stand")), str((sent or {}).get("stand")),
                       jetzt.replace(minute=jetzt.minute // 10 * 10, second=0, microsecond=0).isoformat())
    _scanner(h, analyse, indizes, jetzt)
    if ss.get(K + "meldung"):
        art, text = ss.pop(K + "meldung")
        (st.success if art == "ok" else st.warning)(text)
    st.markdown("**Meine Pyramiden**")
    daten, ok = _laden(h)
    if not ok:
        st.warning("Deine Pyramiden sind gerade nicht lesbar – bitte später erneut versuchen (es wird nichts "
                   "überschrieben).")
        return
    _neu_formular(h, jetzt)
    liste = sorted(daten["pyramiden"], key=lambda p: (p.get("status") != "offen", p.get("start") or ""))
    if not liste:
        st.info("Noch keine Pyramide angelegt.")
        return
    ids = [p["id"] for p in liste]
    if ss.get(K + "wahl") not in ids:
        ss[K + "wahl"] = ids[0]
    je = {p["id"]: p for p in liste}
    st.selectbox("Pyramide", ids, key=K + "wahl", format_func=lambda i: f"{je[i]['name']} · {je[i]['index']} · "
                 f"{len(je[i]['tranchen'])} Stufe(n) · {'offen' if je[i]['status'] == 'offen' else 'geschlossen'}")
    pyr = je[ss[K + "wahl"]]
    a = analyse[pyr["index"]]
    cfg = P.cfg_fuer(pyr)
    b = D.bewertung(a, cfg)
    md = KO.marktdaten(indizes, pyr["index"], jetzt)
    eurusd = KO.eurusd(indizes)
    kurs = md.get("kurs") if md.get("status") in ("live", "schluss") else a["kurs"]
    s = P.status(pyr, a["kerzen"], kurs, eurusd, a["trend"] if a["status"] == "aktuell" else None)
    bereiche = ["Überblick", "Nachkauf prüfen & erfassen", "Einstellungen", "Zeitleiste"]
    if ss.get(K + "bereich") not in bereiche:
        ss[K + "bereich"] = bereiche[0]
    bereich = st.segmented_control("Bereich", bereiche, key=K + "bereich", label_visibility="collapsed",
                                   width="stretch") or bereiche[0]
    if pyr["index"] in KO.INDIZES and KO.INDIZES[pyr["index"]]["waehrung"] != "EUR" and not eurusd:
        st.warning("Kein EUR/USD-Kurs verfügbar – Werte von KO-Zertifikaten auf US-Indizes sind nicht berechenbar.")
    try:
        if bereich == "Überblick":
            _ueberblick(h, pyr, s, a)
            _verwalten(h, pyr)
        elif bereich == "Nachkauf prüfen & erfassen":
            if pyr["status"] != "offen":
                st.info("Diese Pyramide ist geschlossen.")
            else:
                _nachkauf(h, pyr, s, a, b, eurusd, jetzt)
        elif bereich == "Einstellungen":
            _einstellungen(h, pyr)
        else:
            _zeitleiste(pyr, s, a["kerzen"])
    except ValueError as ex:
        st.warning(f"Berechnung nicht möglich: {ex}")
