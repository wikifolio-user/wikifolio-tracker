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
.dk-tkurs { font-size:1.2rem; font-weight:800; color:#ffffff; font-variant-numeric:tabular-nums;
    margin-right:6px; }
.dk-tmeta { color:#A9ACB0; font-size:.8rem; display:block; line-height:1.3; }
.dk-tkurs { display:block; }
.dk-hmeta { padding-bottom:.6rem; }
.dk-pname { font-weight:700; color:#E8ECF6; font-size:.95rem; line-height:1.3; }
.dk-hkurs { font-size:2rem; font-weight:800; color:#ffffff; font-variant-numeric:tabular-nums; margin-top:6px;
    line-height:1.15; }
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
    for f in ("aktuell", "suche", "suche_letzter", "treffer", "wahl", "kq"):
        ss.pop(P + f, None)
    for i in _ids(ss):
        for f in ("stueck", "wert", "gebuehr"):
            ss.pop(_k(i, f), None)
    _setze_ids(ss, [_neue_id() for _ in range(START_ZEILEN)])


def _kurs_uebernehmen(text):
    st.session_state[P + "aktuell"] = text


def _vorschlag_nehmen(v):
    st.session_state[P + "suche"] = v


def _suchen(h, pruefung):
    """Beide Quellen durchsuchen. -> {"kandidaten", "status": [(quelle, ok, text)]}"""
    import kursquellen as KQ
    import produktdaten as PD
    status, ls, ov = [], [], []
    if h.get("suche_instrument"):
        try:
            ls = [t for t in (h["suche_instrument"](pruefung["wert"]) or []) if t.get("instrument_id")]
            status.append(("Lang & Schwarz", bool(ls), f"{len(ls)} Treffer" if ls else "keine Treffer"))
        except Exception:
            status.append(("Lang & Schwarz", False, "nicht erreichbar"))
    if h.get("get"):
        try:
            ov = KQ.onvista_suchen(pruefung["wert"], h["get"])
            status.append(("onvista", bool(ov), f"{len(ov)} Treffer" if ov else "keine Treffer"))
        except PD.ProduktFehler as ex:
            status.append(("onvista", False, "keine Treffer" if "keine" in str(ex).lower() or "kein" in str(ex).lower()
                           else "nicht erreichbar"))
        except Exception:
            status.append(("onvista", False, "nicht erreichbar"))
    return {"kandidaten": KQ.passend(KQ.kandidaten(ls, ov), pruefung)[:12], "status": status}


def _kurse(h, k, neu=False):
    """Kurse eines Kandidaten aus allen Quellen, je Wert 60 s zwischengespeichert."""
    import datetime
    import kursquellen as KQ
    import produktdaten as PD
    ss = st.session_state
    cache = ss.setdefault(P + "kurs_cache", {})
    schl = f"{k.get('ls_id')}|{k.get('isin')}"
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    alt = cache.get(schl)
    if alt and not neu and (jetzt - alt[0]).total_seconds() < 60:
        return alt[1], alt[2]
    kurse, status = [], []
    if k.get("ls_id") and h.get("get_live_kurs"):
        try:
            akt, vor, quelle = h["get_live_kurs"](k["ls_id"])
        except Exception:
            akt, vor, quelle = None, None, ""
        if akt:
            kurse.append({"boerse": "Lang & Schwarz (ls-tc.de)", "kurs": float(akt), "waehrung": "EUR", "zeit": jetzt,
                          "art": "Live", "vortag": float(vor) if vor else None})
            status.append(("Lang & Schwarz", True, "Live-Kurs"))
        else:
            status.append(("Lang & Schwarz", False, "kein Kurs"))
    if k.get("isin") and h.get("get"):
        try:
            ov = KQ.onvista_kurse(k.get("onvista") or {"isin": k["isin"]}, h["get"])
            kurse += ov
            status.append(("onvista", True, f"{len(ov)} Kurse"))
        except PD.ProduktFehler:
            status.append(("onvista", False, "kein Kurs"))
        except Exception:
            status.append(("onvista", False, "nicht erreichbar"))
    kurse = KQ.sortieren(kurse, jetzt)
    cache[schl] = (jetzt, kurse, status)
    return kurse, status


def _status_text(status):
    return " · ".join(f"{'✅' if ok else '❌'} {q}: {t}" for q, ok, t in status)


def _kurs_zeile(x):
    """-> (kurs_text fuer das Feld, Anzeige gross, Zeile mit Art/Boerse/Zeit/Veraenderung)"""
    import kursquellen as KQ
    from decimal import Decimal
    text = DK.de(Decimal(str(x["kurs"])), 4, 2)
    euro = x["waehrung"] == "EUR"
    teile = [x["art"], x["boerse"], KQ.alter_text(x["zeit"]).replace("aktuell (", "").replace(")", "")]
    if x.get("vortag"):
        pct = (x["kurs"] / x["vortag"] - 1) * 100
        teile.append(f"{'+' if pct > 0 else ''}{DK.de(Decimal(str(round(pct, 4))), 2)} % heute")
    return text, f"{text} {'€' if euro else x['waehrung']}", " · ".join(t for t in teile if t)


def _wkn_abruf(h):
    """WKN, ISIN oder Name pruefen, in mehreren Quellen suchen, besten Kurs zeigen und per Klick uebernehmen."""
    import kursquellen as KQ
    ss = st.session_state
    if not (h and (h.get("suche_instrument") or h.get("get"))):
        return
    begriff = st.text_input("Kurs abrufen: WKN, ISIN oder Name", key=P + "suche", max_chars=60,
                            placeholder="z. B. A0RPWH, DE000MM0SF40 oder Apple")
    pruefung = KQ.eingabe_pruefen(begriff)
    if pruefung["vorschlag"] or (pruefung["art"] == "isin" and not KQ.isin_gueltig(pruefung["wert"])):
        st.caption("⚠️ " + " ".join(pruefung["hinweise"]))
    if pruefung["vorschlag"]:
        st.button(f"Stattdessen {pruefung['vorschlag']} suchen", key=P + "vorschlag_btn",
                  on_click=_vorschlag_nehmen, args=(pruefung["vorschlag"],))
    if pruefung["art"] == "leer":
        return
    if (ss.get(P + "kq") or {}).get("begriff") != pruefung["wert"]:
        with st.spinner("Suche Kurs …"):
            ss[P + "kq"] = dict(_suchen(h, pruefung), begriff=pruefung["wert"])
        ss.pop(P + "wahl", None)
    kq = ss[P + "kq"]
    kand = kq["kandidaten"]
    if not kand:
        st.caption("⚠️ Nichts gefunden (" + _status_text(kq["status"]) + "). Schreibweise prüfen oder den Kurs "
                   "unten von Hand eintragen.")
        return
    i = 0
    if len(kand) > 1:
        i = st.selectbox("Welches Wertpapier?", range(len(kand)), key=P + "wahl", format_func=lambda j: (
            f"{kand[j]['name'] or '–'} · {kand[j]['wkn'] or kand[j]['isin']}"
            + (f" · {KQ.typ_text(kand[j]['typ'])}" if kand[j]['typ'] else ""))) or 0
    k = kand[i]
    kurse, status = _kurse(h, k)
    euro_kurse = [x for x in kurse if x["waehrung"] == "EUR"]
    with st.container(border=True, key=P + "kursbox"):
        st.markdown(f'<div class="dk-pname">{_e(k["name"])}</div><div class="dk-tmeta">'
                    + " · ".join(_e(t) for t in (KQ.typ_text(k["typ"]) if k["typ"] else "",
                                                  f"WKN {k['wkn']}" if k["wkn"] else "") if t)
                    + "</div>", unsafe_allow_html=True)
        if euro_kurse:
            text, gross, zeile = _kurs_zeile(euro_kurse[0])
            st.markdown(f'<div class="dk-hkurs">{_e(gross)}</div><div class="dk-tmeta dk-hmeta">{_e(zeile)}</div>',
                        unsafe_allow_html=True)
        else:
            text = None
            st.caption("⚠️ Kein Euro-Kurs gefunden" + (" (nur Fremdwährung)." if kurse else
                                                       f" ({_status_text(status)})."))
        with st.container(horizontal=True, key=P + "kursknoepfe", gap="small"):
            st.button("Übernehmen", icon=":material/check:", key=P + "uebernehmen_0_btn", type="primary",
                      width="stretch", disabled=text is None, on_click=_kurs_uebernehmen, args=(text,))
            if st.button("Kurs aktualisieren", icon=":material/refresh:", key=P + "neu_btn", width="stretch"):
                _kurse(h, k, neu=True)
                st.rerun()
        weitere = [x for x in euro_kurse[1:4]]
        if weitere:
            with st.expander(f"Weitere Kurse ({len(weitere)})"):
                for n, x in enumerate(weitere, 1):
                    t, g, z = _kurs_zeile(x)
                    with st.container(horizontal=True, wrap=False, key=P + f"kurs_{n}", vertical_alignment="center",
                                      gap="small"):
                        st.markdown(f'<b>{_e(g)}</b><div class="dk-tmeta">{_e(z)}</div>', unsafe_allow_html=True,
                                    width="stretch")
                        st.button("Übernehmen", key=P + f"uebernehmen_{n}_btn", type="tertiary",
                                  on_click=_kurs_uebernehmen, args=(t,))
                if any(x["art"] in ("Geld", "Brief") for x in euro_kurse):
                    st.caption("„Geld“ = Rückkaufkurs des Emittenten, der Wert beim Verkauf.")


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


def _beispiel():
    """Ausklappbares Rechenbeispiel: Nachkaeufe beim Nasdaq mit Stueckzahlverdopplung gegenueber gleich grossen
    Nachkaeufen - nur zur Veranschaulichung, ueberschreibt keine Eingaben."""
    with st.expander("📘 Beispiel: Nasdaq-Nachkäufe mit Stückzahlverdopplung"):
        st.markdown(
            "Fällt der Kurs, senkt jeder Nachkauf den Durchschnittskurs. **Verdoppelt** man dabei die Stückzahl, "
            "zählt der günstige Nachkauf stärker – der Durchschnitt rutscht schneller nach unten, und schon eine "
            "kleine Erholung bringt dich in die Gewinnzone. Der Preis dafür: Der Kapitalbedarf **verdoppelt sich "
            "mit jeder Stufe**. Spiele es hier mit einem Nasdaq-100-ETF durch:")
        sp = st.columns(2)
        start = sp[0].text_input("Startkurs (€)", value="100", key=P + "bsp_kurs", max_chars=12)
        stueck = sp[1].text_input("Stückzahl beim ersten Kauf", value="1", key=P + "bsp_stueck", max_chars=12)
        sp = st.columns(3)
        rueck = sp[0].number_input("Rückgang je Stufe (%)", 1, 50, 10, key=P + "bsp_rueck")
        stufen = sp[1].number_input("Stufen", 2, 8, 4, key=P + "bsp_stufen")
        faktor = sp[2].number_input("Faktor je Stufe", 1.0, 3.0, 2.0, step=0.5, key=P + "bsp_faktor",
                                    help="2 = Stückzahl verdoppeln, 1 = gleich große Nachkäufe")
        try:
            plan = DK.staffel(start, stueck, rueck, stufen, faktor)
            gleich = DK.staffel(start, stueck, rueck, stufen, 1)
        except DK.EingabeFehler as ex:
            st.caption(f"⚠️ {ex}")
            return
        import pandas as pd
        f_text = "Verdopplung" if faktor == 2 else f"Faktor {DK.de(faktor, 1, 0)}"
        df = pd.DataFrame([{
            "Stufe": a["stufe"], "Kurs": DK.geld(a["kurs"]), "Kauf (Stück)": DK.stueck_text(a["stueck"]),
            "Betrag": DK.geld(a["betrag"]), "Investiert gesamt": DK.geld(a["investiert"]),
            f"Ø-Kurs ({f_text})": DK.geld(a["durchschnitt"]), "nötige Erholung": f"+{DK.de(a['erholung_pct'], 1)} %",
            "Ø gleich große Käufe": DK.geld(b["durchschnitt"]),
            "Erholung dort": f"+{DK.de(b['erholung_pct'], 1)} %"} for a, b in zip(plan, gleich)])
        st.dataframe(df, hide_index=True, width="stretch", key=P + "bsp_tab")
        a, b = plan[-1], gleich[-1]
        st.markdown(
            f"**Ergebnis nach {stufen} Stufen** (Kurs {DK.geld(a['kurs'])}, "
            f"−{DK.de(100 - a['kurs'] / plan[0]['kurs'] * 100, 1)} % vom Start):\n"
            f"- {f_text}: Ø-Kurs **{DK.geld(a['durchschnitt'])}** – schon **+{DK.de(a['erholung_pct'], 1)} %** "
            f"Erholung reichen für die Gewinnschwelle; eingesetzt **{DK.geld(a['investiert'])}**.\n"
            f"- Gleich große Käufe: Ø-Kurs {DK.geld(b['durchschnitt'])}, nötig +{DK.de(b['erholung_pct'], 1)} %; "
            f"eingesetzt {DK.geld(b['investiert'])}.\n"
            f"- Der letzte Nachkauf allein kostet {DK.geld(a['betrag'])} – das "
            f"{DK.de(a['betrag'] / plan[0]['betrag'], 1, 0)}-Fache des ersten Kaufs.")
        st.warning(
            "**Risiken:** Die Verdopplung braucht immer mehr Kapital (nach 6 Stufen 63-mal so viele Stück wie beim "
            "ersten Kauf) und "
            "verlängert Verluste, wenn der Markt weiter fällt – der Nasdaq 100 verlor 2000–2002 rund 80 %, 2022 "
            "rund ein Drittel. Darum vorher festlegen: **Gesamtbudget, Abstand der Stufen und Höchstzahl der "
            "Stufen**, und nur in breite Indizes (nicht in Einzelwerte) staffeln. Rechenbeispiel ohne Kosten und "
            "Steuern – keine Anlageberatung.")
        st.caption("Tipp: Mit dem Pyramidenmanager (Märkte → Pyramiden) gibt es das Gegenstück – Nachkäufe im "
                   "Aufwärtstrend mit Stops.")


def seite(h=None):
    """h (optional): {"suche_instrument": (begriff) -> Treffer (ls-tc.de), "get_live_kurs": (instrument_id) -> (kurs,
    vortag, quelle), "get": requests.get (onvista)} - ohne h gibt es keinen Kursabruf, der Rechner funktioniert
    sonst gleich."""
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
    _beispiel()
    st.caption("Durchschnittskurs = Summe aller Kaufwerte (inkl. Gebühren, falls eingeschaltet) ÷ Summe aller "
               "Stückzahlen. Bruchstücke und bis zu 8 Nachkommastellen, Dezimalkomma (0,5). Eingaben werden "
               "automatisch gespeichert – dein Depot bleibt unverändert.")
