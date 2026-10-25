"""Analyse-Depot - eigener Menuepunkt zum bequemen Erfassen eines Depots fuer die Depot-Analyse.

Getrennt vom echten Depot ("Depot verwalten"): Suche nach Name/WKN/ISIN, Tabelle zum direkten Bearbeiten,
Schnelleingabe mehrerer Zeilen, CSV/Excel-Import, Sparplan und Entnahme. Kurse kommen immer aus der
Kursquelle (ls-tc.de), nie aus der Eingabe."""
import datetime
import io
import logging

import pandas as pd
import streamlit as st

import analyse_depot as A
import depot_analyse as D
import portfolio_builder_ui as B

P = "ad_"

CSS = """
<style>
.ad-k { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin:6px 0 10px; }
.ad-k .k { border:1px solid var(--line,#22344C); border-radius:12px; padding:10px 12px; background:var(--surface-2,#0E1826); }
.ad-k .l { color:#9AA9BF; font-size:.68rem; text-transform:uppercase; letter-spacing:.5px; }
.ad-k .w { font-size:1.15rem; font-weight:800; margin-top:2px; }
@media (max-width: 760px) { .ad-k { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.ad-hinweis { border:1px dashed #5B9BFF; border-radius:10px; padding:8px 12px; margin:4px 0 10px; color:#BFD6FF;
  background:rgba(91,155,255,.08); font-size:.85rem; }
.ad-pos { color:#4ade80; } .ad-neg { color:#f87171; }
</style>
"""


def _titel(t):
    st.markdown(f'<div class="pb-karte-t">{t}</div>', unsafe_allow_html=True)


def _spalten(n):
    if not B._smartphone():
        return st.columns(n, vertical_alignment="bottom")
    slots = []
    while len(slots) < n:
        slots += st.columns(2, vertical_alignment="bottom")
    return slots[:n]


# ---------------------------------------------------------------- Laden / Speichern
def _depot(h):
    s = st.session_state
    if P + "depot" not in s:
        try:
            s[P + "depot"] = A.bereinigen(h["gh_read"](h["pfad"], None) if h.get("speichern") else None)
        except Exception as e:
            logging.warning(f"Analyse-Depot nicht lesbar: {e}")
            s[P + "depot"] = A.leer()
            s[P + "lesefehler"] = True
    return s[P + "depot"]


def _speichern(h, depot, meldung):
    depot = A.bereinigen(depot)
    depot["stand"] = datetime.datetime.now().isoformat(timespec="minutes")
    st.session_state[P + "depot"] = depot
    st.session_state[P + "ed_nr"] = st.session_state.get(P + "ed_nr", 0) + 1
    st.session_state.pop("da_zustand_bestand", None)          # Depot-Analyse neu rechnen
    ok = False
    if h.get("speichern") and not st.session_state.get(P + "lesefehler"):
        try:
            ok, _ = h["gh_aktualisiere"](h["pfad"], lambda alt: depot, {}, "analyse-depot [skip ci]")
        except Exception as e:
            logging.warning(f"Analyse-Depot: Speichern fehlgeschlagen: {e}")
    st.session_state[P + "meldung"] = (("✅ " + meldung) if ok else
                                      f"ℹ️ {meldung} – nur für diese Sitzung (Speicher gerade nicht verfügbar).")
    return ok


def _kurs(h, iid):
    if not iid:
        return None
    try:
        return h["get_live_kurs"](int(iid))[0]
    except Exception:
        return None


def _art_aus_kategorie(kat):
    k = str(kat or "").lower()
    return ("wikifolio" if "wikifolio" in k else "etf" if "etf" in k or "etp" in k else
            "fonds" if "fonds" in k else "aktie" if "aktie" in k else "")


def _aufloesen(h, kennung):
    """Kennung/Name -> erster Treffer der Kursquelle oder None."""
    try:
        tr = h["suche_instrument"](str(kennung).strip()) or []
    except Exception:
        tr = []
    return tr[0] if tr else None


def _aus_treffer(t, stueck, kaufkurs, kaufdatum):
    return A.position(t["name"], stueck, kaufkurs, kaufdatum, t.get("wkn") or "", t.get("isin") or "",
                      t.get("instrument_id"), _art_aus_kategorie(t.get("kategorie")))


# ---------------------------------------------------------------- Bereiche
def _hinzufuegen(h, depot):
    s = st.session_state
    _titel("➕ Wert hinzufügen")
    with st.form(P + "suche_form", border=False):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        q = c1.text_input("Name, WKN oder ISIN", key=P + "q", placeholder="z. B. MSCI World, A0RPWH, Siemens")
        if c2.form_submit_button("🔍 Suchen", width="stretch") and q.strip():
            s[P + "treffer"] = (h["suche_instrument"](q.strip()) or [])[:10]
            s[P + "treffer_q"] = q.strip()
    treffer = s.get(P + "treffer")
    if treffer is None:
        st.caption("Suche starten – der Kurs kommt danach automatisch aus der Kursquelle (ls-tc.de).")
        return
    if not treffer:
        st.warning(f"Nichts gefunden für „{s.get(P + 'treffer_q')}“. Tipp: ISIN oder WKN verwenden.")
        return
    nr = st.selectbox("Treffer", range(len(treffer)), key=P + "wahl",
                      format_func=lambda i: " · ".join(x for x in (treffer[i]["name"], treffer[i].get("wkn")
                                                                   or treffer[i].get("isin"),
                                                                   treffer[i].get("kategorie")) if x))
    t = treffer[nr]
    kurs = _kurs(h, t.get("instrument_id"))
    with st.form(P + "neu_form", border=False):
        c = _spalten(3)
        stueck = c[0].number_input("Stück", 0.0, 1e9, None, step=1.0, format="%.4f", key=f"{P}st_{nr}",
                                   placeholder="z. B. 10")
        kk = c[1].number_input("Kaufkurs € (Durchschnitt)", 0.0, 1e7, float(kurs) if kurs else None, step=0.01,
                               format="%.2f", key=f"{P}kk_{nr}_{t.get('instrument_id')}",
                               help="Vorbelegt mit dem aktuellen Kurs – auf deinen Einstandskurs ändern.")
        dat = c[2].date_input("Kaufdatum", None, max_value=datetime.date.today(), format="DD.MM.YYYY",
                              key=f"{P}dt_{nr}")
        los = st.form_submit_button("➕ Ins Analyse-Depot übernehmen", type="primary")
    st.caption(f"Aktueller Kurs: {D.eur(kurs, 2)}" if kurs else "Für diesen Wert liefert die Kursquelle gerade keinen "
               "Kurs – er wird gespeichert, aber erst mit Kurs bewertet.")
    if los:
        p, fehler = _aus_treffer(t, stueck, kk, dat)
        if fehler:
            st.error(fehler)
            return
        neu = dict(depot, positionen=A.zusammenfuehren(depot["positionen"], [p]))
        _speichern(h, neu, f"„{p['name']}“ übernommen")
        s.pop(P + "treffer", None)
        st.rerun(scope="fragment")


def _tabelle(h, depot):
    s = st.session_state
    _titel(f"📋 Positionen ({len(depot['positionen'])})")
    if not depot["positionen"]:
        st.caption("Noch keine Positionen – oben suchen, unten mehrere Zeilen auf einmal eingeben oder eine Datei "
                   "importieren.")
        return
    kurse = {p["id"]: _kurs(h, p.get("instrument_id")) for p in depot["positionen"]}
    wert = sum((kurse[p["id"]] or 0) * p["stueck"] for p in depot["positionen"])
    einstand = sum(p["stueck"] * p["kaufkurs"] for p in depot["positionen"] if p.get("kaufkurs") is not None)
    mit_beidem = [p for p in depot["positionen"] if kurse[p["id"]] and p.get("kaufkurs") is not None]
    gv = sum((kurse[p["id"]] - p["kaufkurs"]) * p["stueck"] for p in mit_beidem)
    ohne = sum(1 for p in depot["positionen"] if not kurse[p["id"]])
    st.markdown('<div class="ad-k">' + "".join(
        f'<div class="k"><div class="l">{l}</div><div class="w">{w}</div></div>' for l, w in (
            ("Depotwert", D.eur(wert)), ("Einstand", D.eur(einstand)),
            ("Gewinn/Verlust" + (f" ({len(mit_beidem)} mit Kaufkurs)" if len(mit_beidem) < len(depot["positionen"])
                                 else ""), f'<span class="{"ad-pos" if gv >= 0 else "ad-neg"}">{D.eur(gv)}</span>'),
            ("Positionen", f'{len(depot["positionen"])}' + (f' <span style="font-size:.75rem;color:#f4c67b">'
                                                          f'({ohne} ohne Kurs)</span>' if ohne else ""))))
        + "</div>", unsafe_allow_html=True)
    df = pd.DataFrame([{"Wert": p["name"], "Kennung": p.get("isin") or p.get("wkn") or "",
                        "Klasse": A.ARTEN.get(p.get("art") or "", "automatisch"), "Stück": p["stueck"],
                        "Kaufkurs €": p.get("kaufkurs"),
                        "Kaufdatum": D._datum(p["kaufdatum"]) if p.get("kaufdatum") else None,
                        "Kurs €": kurse[p["id"]], "Wert €": (kurse[p["id"]] or 0) * p["stueck"] or None}
                       for p in depot["positionen"]])
    ed = st.data_editor(
        df, key=f"{P}tab_{s.get(P + 'ed_nr', 0)}", hide_index=True, width="stretch", num_rows="delete",
        disabled=["Wert", "Kennung", "Kurs €", "Wert €"],
        column_config={"Wert": st.column_config.TextColumn(pinned=True),
                       "Klasse": st.column_config.SelectboxColumn(options=list(A.ARTEN.values()), required=True),
                       "Stück": st.column_config.NumberColumn(min_value=0.0, format="%.4f", required=True),
                       "Kaufkurs €": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                       "Kaufdatum": st.column_config.DateColumn(format="DD.MM.YYYY",
                                                                max_value=datetime.date.today()),
                       "Kurs €": st.column_config.NumberColumn(format="%.2f"),
                       "Wert €": st.column_config.NumberColumn(format="%.2f")})
    st.caption("Direkt in der Tabelle ändern: Stück, Kaufkurs, Kaufdatum, Klasse. Zeile löschen: links markieren "
               "und 🗑 drücken. Danach „Änderungen speichern“.")
    rueck = {v: k for k, v in A.ARTEN.items()}
    neu, fehler = [], []
    ids = [p["id"] for p in depot["positionen"]]
    for i, zeile in ed.iterrows():
        alt = depot["positionen"][ids.index(depot["positionen"][i]["id"])] if i < len(ids) else None
        if alt is None:
            continue
        kd = zeile["Kaufdatum"]
        p, f = A.position(alt["name"], zeile["Stück"], None if pd.isna(zeile["Kaufkurs €"]) else zeile["Kaufkurs €"],
                          None if kd is None or (not isinstance(kd, (datetime.date, str)) and pd.isna(kd)) else kd,
                          alt.get("wkn"), alt.get("isin"), alt.get("instrument_id"),
                          rueck.get(zeile["Klasse"], ""), alt["id"])
        if f:
            fehler.append(f)
        else:
            neu.append(p)
    geaendert = [{k: v for k, v in p.items()} for p in neu] != depot["positionen"]
    for f in fehler:
        st.error(f)
    if geaendert and not fehler:
        st.info("Ungespeicherte Änderungen.")
    if st.button("💾 Änderungen speichern", key=P + "tab_save", type="primary" if geaendert else "secondary",
                 disabled=not geaendert or bool(fehler)):
        ziel = depot["sparplan"].get("ziel")
        sp = dict(depot["sparplan"], ziel=ziel if ziel in {p["id"] for p in neu} else "")
        _speichern(h, dict(depot, positionen=neu, sparplan=sp),
                   f"{len(neu)} Positionen gespeichert" + (f", {len(depot['positionen']) - len(neu)} gelöscht"
                                                           if len(neu) < len(depot["positionen"]) else ""))
        st.rerun(scope="fragment")


def _uebernehmen_zeilen(h, depot, zeilen, quelle):
    """[{kennung, name?, stueck, kaufkurs, kaufdatum}] ueber die Kursquelle aufloesen und speichern."""
    neu, fehler, nicht = [], [], []
    with st.spinner(f"Suche {len(zeilen)} Werte in der Kursquelle …"):
        for z in zeilen[:60]:
            t = _aufloesen(h, z.get("kennung") or z.get("name"))
            if t is None and z.get("name") and z.get("kennung"):
                t = _aufloesen(h, z["name"])
            if t is None:
                fehler.append(f"„{z.get('kennung') or z.get('name')}“ nicht gefunden – nicht übernommen")
                nicht.append("; ".join(x for x in (str(z.get("kennung") or z.get("name")), D.de(z["stueck"], 4)
                                                   .rstrip("0").rstrip(","), D.de(z["kaufkurs"], 2)
                                                   if z.get("kaufkurs") is not None else "") if x))
                continue
            p, f = _aus_treffer(t, z["stueck"], z.get("kaufkurs"), z.get("kaufdatum"))
            if f:
                fehler.append(f)
            else:
                neu.append(p)
    if len(zeilen) > 60:
        fehler.append(f"Nur die ersten 60 von {len(zeilen)} Zeilen verarbeitet")
    if neu:
        _speichern(h, dict(depot, positionen=A.zusammenfuehren(depot["positionen"], neu)),
                   f"{len(neu)} Positionen aus {quelle} übernommen")
    st.session_state[P + "fehler"] = fehler
    st.session_state[P + "nicht_gefunden"] = nicht
    return neu


def _schnell(h, depot):
    _titel("⚡ Schnelleingabe (mehrere Werte auf einmal)")
    if P + "schnell_neu" in st.session_state:              # nach dem Uebernehmen: nur nicht gefundene Zeilen behalten
        st.session_state[P + "schnell"] = st.session_state.pop(P + "schnell_neu")
    with st.form(P + "schnell_form", border=False):
        text = st.text_area("Eine Position je Zeile", key=P + "schnell", height=140,
                            placeholder="IE00B4L5Y983; 25; 85,40; 15.03.2024\nSiemens; 10\nA0RPWH; 5; 70,10")
        los = st.form_submit_button("➕ Alle übernehmen", type="primary")
    st.caption(A.SCHNELL_HILFE.split(" Beispiel")[0])
    if los:
        zeilen, fehler = A.schnelleingabe(text)
        if not zeilen:
            st.session_state[P + "fehler"] = fehler or ["Keine Zeile erkannt."]
        else:
            _uebernehmen_zeilen(h, depot, zeilen, "der Schnelleingabe")
            st.session_state[P + "fehler"] = fehler + st.session_state.get(P + "fehler", [])
            # nur die nicht gefundenen Zeilen bleiben zum Korrigieren stehen
            st.session_state[P + "schnell_neu"] = "\n".join(st.session_state.get(P + "nicht_gefunden", []))
        st.rerun(scope="fragment")


def _import(h, depot):
    s = st.session_state
    _titel("📄 Import aus CSV oder Excel (z. B. Depotauszug der Bank)")
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    f = c1.file_uploader("Datei", type=["csv", "xlsx"], key=P + "datei")
    c2.download_button("CSV-Vorlage", D.CSV_VORLAGE.encode("utf-8-sig"), "analyse_depot_vorlage.csv", "text/csv",
                       key=P + "vorlage", width="stretch")
    st.caption("Spalten werden automatisch erkannt: Name/Bezeichnung, ISIN/WKN, Stück/Anzahl, Kaufkurs oder "
               "Einstand, Kaufdatum.")
    if f is not None and s.get(P + "datei_name") != f.name + str(f.size):
        s[P + "datei_name"] = f.name + str(f.size)
        try:
            if f.name.lower().endswith(".xlsx"):
                df = pd.read_excel(f, dtype=str)
            else:
                df = pd.read_csv(io.StringIO(f.getvalue().decode("utf-8-sig", "replace")), sep=None,
                                 engine="python", dtype=str)
            zeilen, fehler = D.import_zeilen(df.to_dict("records"))
        except Exception as e:
            zeilen, fehler = [], [f"Datei nicht lesbar ({type(e).__name__})"]
        if zeilen:
            _uebernehmen_zeilen(h, depot, zeilen, f"„{f.name}“")
        s[P + "fehler"] = fehler + s.get(P + "fehler", [])
        st.rerun(scope="fragment")


def _plan(h, depot):
    _titel("🔁 Sparplan & Entnahme")
    sp, en = depot["sparplan"], depot["entnahme"]
    pos = depot["positionen"]
    optionen = [""] + [p["id"] for p in pos]
    namen = {"": "anteilig auf alle Positionen", **{p["id"]: p["name"] for p in pos}}
    with st.form(P + "plan_form", border=False):
        c = _spalten(3)
        rate = c[0].number_input("Sparrate € / Monat", 0.0, 1e7, float(sp["rate"]), step=25.0, format="%.0f")
        ziel = c[1].selectbox("Sparplan auf", optionen, index=optionen.index(sp["ziel"]) if sp["ziel"] in optionen
                              else 0, format_func=namen.get)
        start = c[2].date_input("Sparplan seit/ab", D._datum(sp["start"]) if sp.get("start") else None,
                                format="DD.MM.YYYY")
        c = _spalten(3)
        e_rate = c[0].number_input("Entnahme € / Monat", 0.0, 1e7, float(en["rate"]), step=25.0, format="%.0f")
        e_start = c[1].date_input("Entnahme seit/ab", D._datum(en["start"]) if en.get("start") else None,
                                  format="DD.MM.YYYY")
        los = st.form_submit_button("💾 Sparplan & Entnahme speichern", type="primary")
    netto = rate - e_rate
    st.caption(f"Netto je Monat: {'+' if netto >= 0 else '−'}{D.eur(abs(netto))} – fließt in die Modellrechnung "
               "der Szenarien ein. Die Stückzahlen oben gibst du als heutigen Bestand ein (bisherige Sparraten "
               "sind darin enthalten).")
    if los:
        _speichern(h, dict(depot, sparplan={"rate": rate, "ziel": ziel, "start": start.isoformat() if start else None},
                           entnahme={"rate": e_rate, "start": e_start.isoformat() if e_start else None}),
                   "Sparplan & Entnahme gespeichert")
        st.rerun(scope="fragment")


def _leeren(h, depot):
    with st.expander("🗑️ Analyse-Depot leeren"):
        ok = st.checkbox("Ja, alle Positionen, Sparplan und Entnahme des Analyse-Depots löschen. Dein echtes Depot "
                         "bleibt unverändert.", key=P + "leeren_ok")
        if st.button("Endgültig leeren", key=P + "leeren", disabled=not ok):
            _speichern(h, A.leer(), "Analyse-Depot geleert")
            st.session_state[P + "leeren_ok"] = False
            st.rerun(scope="fragment")


# ---------------------------------------------------------------- Seite
def seite(h):
    with st.container(key="ad_seite"):
        st.markdown(B.CSS, unsafe_allow_html=True)
        st.markdown(CSS, unsafe_allow_html=True)
        st.markdown('<div class="pb-kopf"><div class="pb-titel">Analyse-<span>Depot</span></div>'
                    '<div class="pb-unter">Positionen bequem erfassen · Grundlage für die 🧠 Depot-Analyse</div></div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="ad-hinweis">📥 Dieses Depot ist <b>getrennt von deinem echten Depot</b> („Depot '
                    'verwalten“) – ideal für das Depot bei deiner Bank. In der 🧠 Depot-Analyse oben „Analyse-Depot“ '
                    'wählen.</div>', unsafe_allow_html=True)
        depot = _depot(h)
        if st.session_state.get(P + "lesefehler"):
            st.warning("Dein gespeichertes Analyse-Depot ist gerade nicht lesbar – bitte später erneut öffnen. "
                       "Es wird nichts überschrieben.")
        m = st.session_state.pop(P + "meldung", None)
        if m:
            (st.success if m.startswith("✅") else st.info)(m)
        for f in st.session_state.pop(P + "fehler", []) or []:
            st.warning(f)
        for teil in (_hinzufuegen, _tabelle, _schnell, _import, _plan):
            with st.container(border=True):
                teil(h, depot)
        _leeren(h, depot)
        if depot.get("stand"):
            st.caption(f"Zuletzt gespeichert: {datetime.datetime.fromisoformat(depot['stand']).strftime('%d.%m.%Y %H:%M')}")
