"""Durchschnittskurs-Rechner (Menuepunkt „Durchschnittskurs-Rechner“) - Oberflaeche. Rechnungen: durchschnittskurs.py.

Kaeufe in einer Tabelle hinzufuegen, bearbeiten und loeschen; je Kauf Stueckzahl und entweder Kurs je Stueck oder
Gesamtwert (der andere Wert wird berechnet), optional Kaufgebuehren. Jede Aenderung rechnet sofort neu.
Gespeichert wird nur in den Rechner-Eingaben des Benutzers (wie bei den anderen Rechnern) - das Depot wird weder
gelesen noch veraendert. Alle Werte liegen im Sitzungszustand unter dem Praefix "dk_"."""
import html

import streamlit as st

import durchschnittskurs as DK
import ui_stil as UI

P = "dk_"
SPALTEN = {"stueck": "Stückzahl", "art": "Eingabe", "kurs": "Kurs je Stück", "gesamt": "Gesamtwert",
           "gebuehr": "Gebühr", "notiz": "Notiz"}
ART_TEXT = {"kurs": "Kurs je Stück", "gesamt": "Gesamtwert"}
TEXT_ART = {v: k for k, v in ART_TEXT.items()}

CSS = """<style>
.dk-kopf { display:flex; gap:12px; align-items:center; margin:2px 0 10px; }
.dk-kopf .dk-sym { font-size:1.35rem; width:38px; height:38px; border-radius:10px; background:#252628;
    display:flex; align-items:center; justify-content:center; flex:0 0 auto; }
.dk-kopf b { font-size:1.05rem; color:#ffffff; } .dk-kopf div div { font-size:.8rem; color:#A9ACB0; }
.dk-karte { border:1px solid rgba(124,156,255,.45); border-radius:16px; padding:14px 16px; margin:8px 0 10px;
    background:rgba(124,156,255,.06); }
.dk-karte .dk-titel { font-size:.75rem; letter-spacing:.5px; text-transform:uppercase; color:#A9ACB0; }
.dk-karte .dk-gross { font-size:2.4rem; font-weight:800; line-height:1.15; color:#ffffff;
    font-variant-numeric:tabular-nums; word-break:break-all; }
.dk-karte .dk-unter { font-size:.85rem; color:#C9CED6; margin:2px 0 10px; }
.dk-raster { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:8px 14px; }
.dk-raster div { font-size:.75rem; color:#A9ACB0; min-width:0; }
.dk-raster b { display:block; font-size:1rem; color:#ffffff; font-variant-numeric:tabular-nums; word-break:break-all; }
@media (max-width: 1000px) { .dk-raster { grid-template-columns:repeat(3, minmax(0,1fr)); } }
@media (max-width: 640px) { .dk-raster { grid-template-columns:repeat(2, minmax(0,1fr)); }
    .dk-karte .dk-gross { font-size:1.8rem; } }
.dk-leer { color:#A9ACB0; font-size:.9rem; }
</style>"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _zeilen(ss):
    k = DK.laden(ss.get(P + "daten"))
    return k or [{"stueck": "", "art": "kurs", "kurs": "", "gesamt": "", "gebuehr": "", "notiz": ""}]


def _abgeleitet(k):
    """Den nicht eingegebenen Wert (Gesamtwert bzw. Kurs) aus den gueltigen Eingaben fuellen."""
    k = dict(k)
    try:
        z = DK.kauf_pruefen(k)
    except DK.EingabeFehler:
        return k
    if z["art"] == "kurs":
        k["gesamt"] = DK.de(z["kaufwert"], DK.NACHKOMMA, 2)
    else:
        k["kurs"] = DK.de(z["kurs"], DK.NACHKOMMA, 2)
    return k


def _aus_tabelle(df, vorher):
    """Bearbeitete Tabelle -> Kaeufe. Welche Groesse eingegeben wurde, ergibt sich aus der Spalte „Eingabe“ -
    oder automatisch, wenn nur Kurs bzw. nur Gesamtwert geaendert wurde."""
    aus = []
    for i, (_, z) in enumerate(df.iterrows()):
        k = {f: ("" if z.get(SPALTEN[f]) is None or str(z.get(SPALTEN[f])) in ("nan", "None")
                 else str(z.get(SPALTEN[f])).strip()) for f in SPALTEN if f != "art"}
        art = TEXT_ART.get(str(z.get(SPALTEN["art"]) or ""), "kurs")
        alt = vorher[i] if i < len(vorher) else None
        if alt and art == alt.get("art"):
            if k["gesamt"] != alt.get("gesamt", "") and k["kurs"] == alt.get("kurs", ""):
                art = "gesamt"
            elif k["kurs"] != alt.get("kurs", "") and k["gesamt"] == alt.get("gesamt", ""):
                art = "kurs"
        elif not alt and k["gesamt"] and not k["kurs"]:
            art = "gesamt"
        k["art"] = art
        aus.append(k)
    return aus


def _tabelle(ss, kaeufe, mit_gebuehren, waehrung):
    import pandas as pd
    erg = DK.berechnen(kaeufe, mit_gebuehren)
    zeilen = []
    for k, z in zip(kaeufe, erg["zeilen"]):
        status = "" if z is None else ("⚠️ " + z["fehler"] if "fehler" in z else
                                       "✅ " + DK.geld(z["summe"], waehrung))
        zeilen.append({SPALTEN["stueck"]: k["stueck"], SPALTEN["art"]: ART_TEXT[k["art"]], SPALTEN["kurs"]: k["kurs"],
                       SPALTEN["gesamt"]: k["gesamt"], SPALTEN["gebuehr"]: k["gebuehr"], SPALTEN["notiz"]: k["notiz"],
                       "Summe inkl. Gebühr": status})
    df = pd.DataFrame(zeilen, columns=list(SPALTEN.values()) + ["Summe inkl. Gebühr"])
    z = DK.WAEHRUNGEN.get(waehrung, waehrung)
    cfg = {SPALTEN["stueck"]: st.column_config.TextColumn("Stückzahl", help="Auch Bruchstücke, z. B. 0,25 oder "
                                                          "0,00012345 (bis 8 Nachkommastellen)", width="small"),
           SPALTEN["art"]: st.column_config.SelectboxColumn("Eingabe", options=list(ART_TEXT.values()), required=True,
                                                             default=ART_TEXT["kurs"],
                                                             help="Was du eingibst – der andere Wert wird berechnet."),
           SPALTEN["kurs"]: st.column_config.TextColumn(f"Kurs je Stück ({z})", width="small"),
           SPALTEN["gesamt"]: st.column_config.TextColumn(f"Gesamtwert ({z})", width="small",
                                                          help="Kaufwert ohne Gebühr"),
           SPALTEN["gebuehr"]: st.column_config.TextColumn(f"Gebühr ({z})", width="small") if mit_gebuehren else None,
           SPALTEN["notiz"]: st.column_config.TextColumn("Notiz", help="z. B. Datum oder Börse (optional)",
                                                         max_chars=80),
           "Summe inkl. Gebühr": st.column_config.TextColumn("Summe / Prüfung", disabled=True)}
    return st.data_editor(df, key=P + f"tab_{ss.get(P + 'ver', 0)}", num_rows="dynamic", hide_index=True,
                          width="stretch", column_config=cfg)


def _karte(erg, waehrung, mit_gebuehren, name):
    if not erg["anzahl"]:
        st.markdown('<div class="dk-karte"><div class="dk-titel">Gewichteter Durchschnittskurs</div>'
                    '<div class="dk-leer">Noch kein gültiger Kauf – Stückzahl und Kurs (oder Gesamtwert) eintragen.'
                    '</div></div>', unsafe_allow_html=True)
        return
    felder = [("Gesamtstückzahl", DK.stueck_text(erg["stueck"])),
              ("Gesamtinvestition", DK.geld(erg["investition"], waehrung)),
              ("Kaufgebühren gesamt", DK.geld(erg["gebuehren"], waehrung) if mit_gebuehren else "nicht berücksichtigt"),
              ("Anzahl der Käufe", str(erg["anzahl"])),
              ("Ø ohne Gebühren", DK.kurs_text(erg["durchschnitt_ohne"], waehrung))]
    st.markdown(
        f'<div class="dk-karte"><div class="dk-titel">Gewichteter Durchschnittskurs'
        f'{" · " + _e(name) if name else ""}</div>'
        f'<div class="dk-gross">{_e(DK.kurs_text(erg["durchschnitt"], waehrung))}</div>'
        f'<div class="dk-unter">je Stück{" inklusive Kaufgebühren" if mit_gebuehren else ""} · Kaufwert ohne Gebühren '
        f'{_e(DK.geld(erg["kaufwert"], waehrung))}</div><div class="dk-raster">'
        + "".join(f"<div>{_e(t)}<b>{_e(w)}</b></div>" for t, w in felder) + "</div></div>",
        unsafe_allow_html=True)


def _nachkauf(ss, erg, waehrung, mit_gebuehren):
    with st.expander("🔮 Nachkauf simulieren (ohne ihn in die Tabelle zu übernehmen)"):
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        s = sp[0].text_input("Stückzahl", key=P + "nk_stueck", placeholder="z. B. 10")
        k = sp[1].text_input("Kurs je Stück", key=P + "nk_kurs", placeholder="z. B. 95,50")
        g = sp[2].text_input("Gebühr", key=P + "nk_gebuehr", placeholder="0", disabled=not mit_gebuehren)
        if not (s or "").strip() or not (k or "").strip():
            st.caption("Stückzahl und Kurs eingeben – der neue Durchschnittskurs erscheint sofort.")
            return
        try:
            r = DK.nachkauf(erg, s, k, g if mit_gebuehren else "")
        except DK.EingabeFehler as ex:
            st.warning(str(ex))
            return
        alt = erg["durchschnitt"]
        diff = "" if alt is None else f" ({'−' if r['durchschnitt'] < alt else '+'}" \
            f"{DK.de(abs((r['durchschnitt'] / alt - 1) * 100), 2)} %)"
        st.markdown(f"Neuer Durchschnittskurs: **{_e(DK.kurs_text(r['durchschnitt'], waehrung))}**{diff} · "
                    f"Stückzahl {_e(DK.stueck_text(r['stueck']))} · Investition "
                    f"{_e(DK.geld(r['investition'], waehrung))}")
        if st.button("In die Tabelle übernehmen", key=P + "nk_btn"):
            kaeufe = [x for x in _zeilen(ss) if not DK.leer(x)]
            kaeufe.append({"stueck": s.strip(), "art": "kurs", "kurs": k.strip(), "gesamt": "",
                           "gebuehr": (g or "").strip() if mit_gebuehren else "", "notiz": "Nachkauf (simuliert)"})
            ss[P + "daten"] = DK.speichern([_abgeleitet(x) for x in kaeufe])
            ss[P + "ver"] = ss.get(P + "ver", 0) + 1
            for f in ("nk_stueck", "nk_kurs", "nk_gebuehr"):
                ss.pop(P + f, None)
            st.rerun()


def seite():
    ss = st.session_state
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="dk-kopf"><span class="dk-sym">🧮</span><div><b>Durchschnittskurs-Rechner</b>'
                '<div>Gewichteter Einkaufskurs für Aktien, ETFs und Kryptowährungen – unabhängig vom Depot, auch '
                'für hypothetische Nachkäufe</div></div></div>', unsafe_allow_html=True)
    if ss.get(P + "meldung"):
        st.success(ss.pop(P + "meldung"))
    name = st.text_input("Wertpapier (optional)", key=P + "name", max_chars=60,
                         placeholder="z. B. MSCI World ETF oder Bitcoin")
    sp = st.columns([1, 2], vertical_alignment="bottom")
    waehrung = sp[0].selectbox("Währung", list(DK.WAEHRUNGEN), key=P + "waehrung")
    mit_gebuehren = sp[1].toggle("Kaufgebühren", value=True, key=P + "gebuehren",
                                 help="Kaufgebühren im Durchschnittskurs berücksichtigen")
    vorher = _zeilen(ss)
    neu = _aus_tabelle(_tabelle(ss, vorher, mit_gebuehren, waehrung), vorher)
    neu = [_abgeleitet(k) for k in neu]
    if DK.speichern(neu) != DK.speichern(vorher):            # Aenderung: speichern und Tabelle neu aufbauen
        ss[P + "daten"] = DK.speichern(neu)
        ss[P + "ver"] = ss.get(P + "ver", 0) + 1
        st.rerun()
    st.caption("Zeile hinzufügen: „+“ unter der Tabelle. Bearbeiten: Zelle antippen. Löschen: Zeile markieren und "
               "Papierkorb. Dezimalzeichen Komma (0,5); Tausenderpunkte nur zusammen mit Komma (1.234,56). Wer den Gesamtwert "
               "einträgt, bekommt den Kurs je Stück berechnet – und umgekehrt.")
    erg = DK.berechnen(neu, mit_gebuehren)
    for nr, text in erg["fehler"]:
        st.warning(f"Kauf {nr}: {text} – zählt nicht mit, bis er korrigiert ist.")
    _karte(erg, waehrung, mit_gebuehren, (name or "").strip())
    st.caption("Durchschnittskurs = Summe aller Kaufwerte" + (" inklusive Kaufgebühren" if mit_gebuehren else "")
               + " ÷ Summe aller Stückzahlen. Gerechnet wird exakt (Dezimalarithmetik), angezeigt mit bis zu 8 "
               "Nachkommastellen.")
    if erg["anzahl"]:
        _nachkauf(ss, erg, waehrung, mit_gebuehren)
    if st.button("↺ Alle Eingaben zurücksetzen", key=P + "reset_btn"):
        ss[P + "daten"] = DK.speichern([])
        ss[P + "ver"] = ss.get(P + "ver", 0) + 1
        for f in ("name", "nk_stueck", "nk_kurs", "nk_gebuehr"):
            ss.pop(P + f, None)
        ss[P + "meldung"] = "Alle Eingaben zurückgesetzt."
        st.rerun()
    st.caption("Die Eingaben werden automatisch gespeichert und sind beim nächsten Öffnen wieder da. Dein Depot "
                 "bleibt unverändert.")
