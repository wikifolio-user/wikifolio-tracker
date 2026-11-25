"""Durchschnittskurs-Rechner (Menuepunkt „Durchschnittskurs-Rechner“) - einfache Eingabemaske. Rechnungen:
durchschnittskurs.py.

Oben die Wahl „Kurs pro Stück“ oder „Gesamtwert je Kauf“, darunter nummerierte Kaeufe (Stueckzahl + Kurs bzw.
Gesamtwert, optional Gebuehr) mit Papierkorb und „Weiteren Kauf hinzufügen“. Jede Eingabe rechnet sofort neu.
Gespeichert wird nur in den Rechner-Eingaben des Benutzers (Praefix "dk_", wie bei den anderen Rechnern) - das
Depot wird weder gelesen noch veraendert.

Sitzungszustand: dk_ids (JSON-Liste der Zeilen-IDs), dk_modus ("kurs"/"gesamt"), dk_gebuehren (bool),
je Zeile dk_r<id>_stueck, dk_r<id>_wert, dk_r<id>_gebuehr (Texte)."""
import html
import json
import uuid

import streamlit as st

import durchschnittskurs as DK

P = "dk_"
START_ZEILEN = 3
MAX_ZEILEN = 100
MODI = {"kurs": "Kurs pro Stück", "gesamt": "Gesamtwert je Kauf"}

CSS = """<style>
.dk-titel { font-size:1.55rem; font-weight:800; color:#ffffff; margin:0 0 4px; }
.dk-kopf { display:flex; gap:10px; font-size:.82rem; color:#A9ACB0; padding:0 2px; }
.dk-nr { color:#A9ACB0; font-size:1.05rem; min-width:1.7rem; }
.dk-nr-kopf { font-size:.8rem; }
.dk-spalte { color:#E8ECF6; font-weight:700; font-size:.92rem; white-space:nowrap; overflow:hidden;
    text-overflow:ellipsis; }
@media (max-width: 480px) { .dk-spalte { font-size:.78rem; } }
.st-key-dk_kopfzeile { min-height:1.9rem; margin-bottom:.15rem; overflow:visible; }
.st-key-dk_kopfzeile .dk-spalte, .st-key-dk_kopfzeile .dk-nr { line-height:1.6rem; }
.dk-ergebnis { text-align:center; margin:14px 0 6px; }
.dk-ergebnis .dk-label { color:#A9ACB0; font-size:.95rem; }
.dk-ergebnis .dk-wert { color:#4ADE80; font-size:2.6rem; font-weight:800; line-height:1.2;
    font-variant-numeric:tabular-nums; word-break:break-all; }
.dk-raster { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:12px; margin:10px 0 4px; }
.dk-kachel { background:rgba(255,255,255,.04); border-radius:14px; padding:12px 14px; min-width:0; }
.dk-kachel .t { color:#A9ACB0; font-size:.85rem; }
.dk-kachel .w { color:#ffffff; font-size:1.45rem; font-weight:700; font-variant-numeric:tabular-nums;
    word-break:break-all; }
.dk-raster3 { grid-template-columns:repeat(3, minmax(0,1fr)); }
.dk-kachel .w.dk-pos { color:#4ADE80; } .dk-kachel .w.dk-neg { color:#F87171; }
@media (max-width: 640px) { .dk-raster3 { grid-template-columns:repeat(2, minmax(0,1fr)); }
    .dk-raster3 .dk-kachel:first-child { grid-column:1 / -1; } }
.dk-treffer { background:rgba(124,156,255,.08); border:1px solid rgba(124,156,255,.35); border-radius:12px;
    padding:10px 12px; margin:4px 0 8px; color:#E8ECF6; font-size:.9rem; }
.dk-treffer .dk-tkurs { font-size:1.35rem; font-weight:800; color:#ffffff; font-variant-numeric:tabular-nums;
    margin-right:6px; }
.dk-treffer .dk-tmeta { color:#A9ACB0; font-size:.8rem; }
.dk-fuss { text-align:center; color:#A9ACB0; font-size:.8rem; margin-top:4px; }
@media (max-width: 640px) { .dk-ergebnis .dk-wert { font-size:2.1rem; } .dk-kachel .w { font-size:1.2rem; } }
</style>"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _k(i, feld):
    return f"{P}r{i}_{feld}"


def _neue_id():
    return uuid.uuid4().hex[:6]


def _ids(ss):
    """Zeilen-IDs; beim ersten Aufruf aus einer gespeicherten Tabelle der frueheren Version uebernehmen."""
    try:
        ids = json.loads(ss.get(P + "ids") or "null")
    except (TypeError, ValueError):
        ids = None
    if isinstance(ids, list) and all(isinstance(x, str) for x in ids):
        return ids
    alt = DK.laden(ss.get(P + "daten"))            # Uebernahme aus der Tabellen-Version
    ids = []
    if alt:
        modus = "gesamt" if all(k.get("art") == "gesamt" for k in alt if not DK.leer(k)) else "kurs"
        ss[P + "modus"] = modus
        if any(str(k.get("gebuehr") or "").strip() for k in alt):
            ss[P + "gebuehren"] = True
        for k in alt:
            if DK.leer(k):
                continue
            i = _neue_id()
            ids.append(i)
            wert = k.get("gesamt") if modus == "gesamt" else k.get("kurs")
            try:                                     # gemischte Eingabearten: in die gewaehlte umrechnen
                z = DK.kauf_pruefen(k)
                wert = DK.de(z["kaufwert"] if modus == "gesamt" else z["kurs"], DK.NACHKOMMA, 2)
            except DK.EingabeFehler:
                pass
            ss[_k(i, "stueck")], ss[_k(i, "wert")], ss[_k(i, "gebuehr")] = k.get("stueck", ""), wert or "", \
                k.get("gebuehr", "")
    while len(ids) < START_ZEILEN:
        ids.append(_neue_id())
    ss[P + "ids"] = json.dumps(ids)
    ss.pop(P + "daten", None)
    return ids


def _setze_ids(ss, ids):
    ss[P + "ids"] = json.dumps(ids)


def kaeufe(ss, ids=None):
    """Eingaben -> Kaeufe im Format von durchschnittskurs.berechnen."""
    modus = ss.get(P + "modus", "kurs")
    aus = []
    for i in ids if ids is not None else _ids(ss):
        wert = str(ss.get(_k(i, "wert")) or "")
        aus.append({"stueck": str(ss.get(_k(i, "stueck")) or ""), "art": modus,
                    "kurs": wert if modus == "kurs" else "", "gesamt": wert if modus == "gesamt" else "",
                    "gebuehr": str(ss.get(_k(i, "gebuehr")) or "")})
    return aus


def _modus_gewechselt():
    """Beim Umschalten die zweite Spalte umrechnen (Kurs <-> Gesamtwert), damit die Rechnung gleich bleibt."""
    ss = st.session_state
    neu = ss.get(P + "modus", "kurs")
    for i in _ids(ss):
        try:
            s = DK.zahl(ss.get(_k(i, "stueck")), "Stückzahl")
            w = DK.zahl(ss.get(_k(i, "wert")), "Wert")
        except DK.EingabeFehler:
            continue
        ss[_k(i, "wert")] = DK.de(s * w if neu == "gesamt" else w / s, DK.NACHKOMMA, 2)


def _loeschen(i):
    ss = st.session_state
    ids = [x for x in _ids(ss) if x != i] or [_neue_id()]
    for f in ("stueck", "wert", "gebuehr"):
        ss.pop(_k(i, f), None)
    _setze_ids(ss, ids)


def _hinzufuegen():
    ss = st.session_state
    ids = _ids(ss)
    if len(ids) < MAX_ZEILEN:
        _setze_ids(ss, ids + [_neue_id()])


def _zuruecksetzen():
    ss = st.session_state
    for f in ("aktuell", "suche", "suche_letzter", "treffer", "wahl"):
        ss.pop(P + f, None)
    for i in _ids(ss):
        for f in ("stueck", "wert", "gebuehr"):
            ss.pop(_k(i, f), None)
    _setze_ids(ss, [_neue_id() for _ in range(START_ZEILEN)])


def _kurs_uebernehmen(text):
    st.session_state[P + "aktuell"] = text


def _kurs_holen(h, iid, neu=False):
    """Live-Kurs (ls-tc.de) je Instrument, in der Sitzung 60 s zwischengespeichert. -> (kurs, vortag, quelle, zeit)"""
    import datetime
    ss = st.session_state
    cache = ss.setdefault(P + "kurs_cache", {})
    jetzt = datetime.datetime.now()
    alt = cache.get(str(iid))
    if alt and not neu and (jetzt - alt[3]).total_seconds() < 60:
        return alt
    try:
        akt, vor, quelle = h["get_live_kurs"](iid)
    except Exception:
        akt, vor, quelle = None, None, "Fehler – keine Live-Daten"
    cache[str(iid)] = (akt, vor, quelle, jetzt)
    return cache[str(iid)]


def _wkn_abruf(h):
    """WKN, ISIN oder Name suchen, Kurs anzeigen und per Klick als aktuellen Kurs uebernehmen."""
    ss = st.session_state
    if not (h and h.get("suche_instrument") and h.get("get_live_kurs")):
        return
    begriff = (st.text_input("Kurs abrufen: WKN, ISIN oder Name", key=P + "suche", max_chars=60,
                             placeholder="z. B. A0RPWH, IE00B4L5Y983 oder Apple") or "").strip()
    if not begriff:
        return
    if ss.get(P + "suche_letzter") != begriff:
        with st.spinner("Suche …"):
            try:
                ss[P + "treffer"] = h["suche_instrument"](begriff) or []
            except Exception:
                ss[P + "treffer"] = []
        ss[P + "suche_letzter"] = begriff
        ss.pop(P + "wahl", None)
    treffer = [t for t in ss.get(P + "treffer") or [] if t.get("instrument_id")]
    if not treffer:
        st.caption("⚠️ Keine Treffer – Schreibweise prüfen oder den Kurs unten von Hand eintragen.")
        return
    namen = [f"{t.get('name') or '–'} · WKN {t.get('wkn') or '–'}" + (f" · {t['kategorie']}" if t.get("kategorie")
                                                                      else "") for t in treffer]
    if len(treffer) > 1:
        i = st.selectbox("Treffer", range(len(treffer)), format_func=lambda j: namen[j], key=P + "wahl")
    else:
        i = 0
    t = treffer[i or 0]
    akt, vor, quelle, zeit = _kurs_holen(h, t["instrument_id"])
    if not akt:
        st.caption(f"⚠️ {_e(t.get('name'))}: kein Kurs verfügbar ({_e(quelle)}).")
        return
    from decimal import Decimal
    kurs = Decimal(str(akt))
    veraend = ""
    if vor:
        pct = (kurs / Decimal(str(vor)) - 1) * 100
        veraend = f" · {'+' if pct > 0 else ''}{DK.de(pct, 2)} % zum Vortag"
    text = DK.de(kurs, 4, 2)
    st.markdown(f'<div class="dk-treffer"><b>{_e(t.get("name"))}</b> · WKN {_e(t.get("wkn") or "–")}<br>'
                f'<span class="dk-tkurs">{_e(text)} €</span><span class="dk-tmeta">{_e(veraend)} · '
                f'{_e(quelle)}, {zeit:%H:%M} Uhr</span></div>', unsafe_allow_html=True)
    with st.container(horizontal=True, key=P + "abruf_knoepfe"):
        st.button("Als aktuellen Kurs übernehmen", icon=":material/download:", key=P + "uebernehmen_btn",
                  type="primary", on_click=_kurs_uebernehmen, args=(text,))
        if st.button("Neu abrufen", icon=":material/refresh:", key=P + "neu_btn", type="tertiary"):
            _kurs_holen(h, t["instrument_id"], neu=True)
            st.rerun()


def _gewinn(ss, erg, h=None):
    """Aktueller Kurs -> aktueller Wert, Gewinn/Verlust in Euro und Prozent."""
    st.divider()
    _wkn_abruf(h)
    kurs = st.text_input("Aktueller Kurs (€)", key=P + "aktuell", placeholder="0,00", max_chars=30,
                         help="Kurs je Stück heute – daraus ergeben sich Wert und Gewinn bzw. Verlust.")
    if not (kurs or "").strip():
        return
    if not erg["anzahl"]:
        st.caption("Zuerst mindestens einen Kauf eintragen.")
        return
    try:
        g = DK.gewinn(erg, kurs)
    except DK.EingabeFehler as ex:
        st.caption(f"⚠️ {ex}")
        return
    css = "dk-pos" if g["gewinn"] > 0 else "dk-neg" if g["gewinn"] < 0 else ""
    vz = "+" if g["gewinn"] > 0 else ""
    st.markdown(f'<div class="dk-raster dk-raster3"><div class="dk-kachel"><div class="t">Aktueller Wert</div>'
                f'<div class="w">{_e(DK.geld(g["wert"]))}</div></div>'
                f'<div class="dk-kachel"><div class="t">{"Gewinn" if g["gewinn"] >= 0 else "Verlust"}</div>'
                f'<div class="w {css}">{vz}{_e(DK.geld(g["gewinn"]))}</div></div>'
                f'<div class="dk-kachel"><div class="t">in Prozent</div>'
                f'<div class="w {css}">{vz}{_e(DK.de(g["prozent"], 2))} %</div></div></div>',
                unsafe_allow_html=True)


def seite(h=None):
    """h (optional): {"suche_instrument": (begriff) -> Treffer, "get_live_kurs": (instrument_id) -> (kurs, vortag,
    quelle)} - ohne h gibt es keinen WKN-Abruf, der Rechner funktioniert sonst gleich."""
    ss = st.session_state
    st.markdown(CSS, unsafe_allow_html=True)
    ids = _ids(ss)
    with st.container(border=True, key=P + "karte"):
        st.markdown('<div class="dk-titel">Durchschnittskurs-Rechner</div>', unsafe_allow_html=True)
        if ss.get(P + "modus") not in MODI:
            ss[P + "modus"] = "kurs"
        modus = st.radio("Eingabe", list(MODI), format_func=MODI.get, key=P + "modus", horizontal=True,
                         label_visibility="collapsed", on_change=_modus_gewechselt)
        gebuehren = st.toggle("Kaufgebühren berücksichtigen", key=P + "gebuehren")
        st.divider()
        wert_titel = "Kurs (€)" if modus == "kurs" else "Gesamtwert (€)"
        with st.container(horizontal=True, wrap=False, key=P + "kopfzeile", gap="small",
                          vertical_alignment="center"):
            st.markdown('<div class="dk-nr dk-nr-kopf">Nr.</div>', unsafe_allow_html=True, width="content")
            for t in ["Stückzahl", wert_titel] + (["Gebühr (€)"] if gebuehren else []):
                st.markdown(f'<div class="dk-spalte">{_e(t)}</div>', unsafe_allow_html=True, width="stretch")
            st.markdown('<div style="width:2.2rem"></div>', unsafe_allow_html=True, width="content")
        for n, i in enumerate(ids, 1):
            with st.container(horizontal=True, wrap=False, key=P + f"zeile_{i}", gap="small",
                              vertical_alignment="center"):
                st.markdown(f'<div class="dk-nr">{n}.</div>', unsafe_allow_html=True, width="content")
                st.text_input(f"Stückzahl Kauf {n}", key=_k(i, "stueck"), placeholder="0",
                              label_visibility="collapsed", max_chars=30)
                st.text_input(f"{wert_titel} Kauf {n}", key=_k(i, "wert"), placeholder="0,00",
                              label_visibility="collapsed", max_chars=30)
                if gebuehren:
                    st.text_input(f"Gebühr Kauf {n}", key=_k(i, "gebuehr"), placeholder="0,00",
                                  label_visibility="collapsed", max_chars=20)
                st.button("", icon=":material/delete:", key=P + f"del_{i}_btn", type="tertiary",
                          help=f"Kauf {n} löschen", on_click=_loeschen, args=(i,))
        st.button("Weiteren Kauf hinzufügen", icon=":material/add:", key=P + "add_btn", width="stretch",
                  on_click=_hinzufuegen, disabled=len(ids) >= MAX_ZEILEN)
        erg = DK.berechnen(kaeufe(ss, ids), gebuehren)
        for nr, text in erg["fehler"]:
            st.caption(f"⚠️ Kauf {nr}: {text}")
        st.divider()
        wert = DK.anzeige_kurs(erg["durchschnitt"]) if erg["durchschnitt"] is not None else "— €"
        st.markdown(f'<div class="dk-ergebnis"><div class="dk-label">Dein Durchschnittskurs pro Stück</div>'
                    f'<div class="dk-wert">{_e(wert)}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="dk-raster"><div class="dk-kachel"><div class="t">Gesamtstückzahl</div>'
                    f'<div class="w">{_e(DK.stueck_text(erg["stueck"]))}</div></div>'
                    f'<div class="dk-kachel"><div class="t">Gesamtinvestition</div>'
                    f'<div class="w">{_e(DK.geld(erg["investition"]))}</div></div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="dk-fuss">{erg["anzahl"]} {"Kauf" if erg["anzahl"] == 1 else "Käufe"}'
                    + (f' · Kaufgebühren {_e(DK.geld(erg["gebuehren"]))}' if gebuehren else "")
                    + (f' · ohne Gebühren {_e(DK.anzeige_kurs(erg["durchschnitt_ohne"]))}'
                       if gebuehren and erg["gebuehren"] else "") + "</div>", unsafe_allow_html=True)
        _gewinn(ss, erg, h)
        with st.container(horizontal=True, horizontal_alignment="center", key=P + "fusszeile"):
            st.button("Zurücksetzen", icon=":material/refresh:", key=P + "reset_btn", type="tertiary",
                      on_click=_zuruecksetzen)
    st.caption("Durchschnittskurs = Summe aller Kaufwerte (inkl. Gebühren, falls eingeschaltet) ÷ Summe aller "
               "Stückzahlen. Bruchstücke und bis zu 8 Nachkommastellen, Dezimalkomma (0,5). Eingaben werden "
               "automatisch gespeichert – dein Depot bleibt unverändert.")
