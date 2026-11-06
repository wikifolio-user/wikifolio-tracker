"""EKS-Investmentbewertung: Ideen fuer Nebengewerbe und Investments nach der Engpasskonzentrierten Strategie
(Wolfgang Mewes) bewerten und durchrechnen. Rechenkern: eks_rechner/ (ohne Streamlit, getestet in test_eks.py).

Gespeichert wird je Benutzer in state/eks_ideen.json auf dem State-Branch (wie das Analyse-Depot).
Mobil zuerst: einspaltig, Karten statt breiter Tabellen auf dem iPhone, Formulare statt Sofort-Neuberechnung.
"""
import datetime
import html
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import formate as FMT
import schritte
import ui_stil as UI
from eks_rechner import modell as M
from eks_rechner import rechnen as R

P = "eks_"
BEREICHE = ["Übersicht", "Idee bearbeiten", "Vergleich", "Einstellungen"]
SZ_FARBE = {"pess": "#F87171", "real": UI.AKZENT, "opt": "#5EEAD4"}
CSS = """<style>
.st-key-eks_seite .eks-karte { border:1px solid rgba(255,255,255,.10); border-radius:14px; padding:10px 12px;
  margin:6px 0; background:rgba(255,255,255,.03); }
.st-key-eks_seite .eks-kopf { display:flex; gap:8px; align-items:center; font-weight:600; font-size:1.02rem; }
.st-key-eks_seite .eks-zeile { display:flex; flex-wrap:wrap; gap:4px 14px; margin-top:4px; font-size:.9rem;
  color:#A9B1C4; }
.st-key-eks_seite .eks-zeile b { color:#E8ECF6; font-weight:600; }
.st-key-eks_seite .eks-grund { font-size:.85rem; color:#A9B1C4; margin-top:2px; }
</style>"""


# ---------------------------------------------------------------- Formatierung
def _eur(x, nk=0):
    return FMT.eur(x, nk)


def _monate(m):
    if m is None:
        return "nicht erreicht"
    if m == 0:
        return "sofort"
    return f"{m} Mon." if m < 24 else f"{FMT.zahl(m / 12, 1)} J."


def _irr(x):
    if x is None:
        return "nicht definiert"
    return "> 1.000 %" if x > 10 else FMT.pct(x * 100, 1)


def _eur_h(x):
    return "– (0 h)" if x is None else FMT.eur(x, 2)


def _spalten(n):
    if UI.ist_smartphone():
        return [st.container() for _ in range(n)]
    return st.columns(n)


# ---------------------------------------------------------------- Laden / Speichern
def _daten(h):
    s = st.session_state
    if P + "daten" not in s:
        try:
            s[P + "daten"] = M.bereinigen(h["gh_read"](h["pfad"], None) if h.get("speichern") else None)
        except Exception as e:
            logging.warning(f"EKS: Ideen nicht lesbar: {e}")
            s[P + "daten"] = M.leer()
            s[P + "lesefehler"] = True
    return s[P + "daten"]


def _speichern(h, daten, meldung):
    daten = M.bereinigen(daten)
    st.session_state[P + "daten"] = daten
    ok = False
    if h.get("speichern") and not st.session_state.get(P + "lesefehler"):
        try:
            def aendern(alt):
                neu = dict(daten)
                neu["letzter_lauf"] = M.bereinigen(alt).get("letzter_lauf") or daten.get("letzter_lauf") or {}
                return neu
            ok, _ = h["gh_aktualisiere"](h["pfad"], aendern, {}, "eks-ideen [skip ci]")
        except Exception as e:
            logging.warning(f"EKS: Speichern fehlgeschlagen: {e}")
    st.session_state[P + "meldung"] = (("✅ " + meldung) if ok else
                                      f"ℹ️ {meldung} – nur für diese Sitzung (Speicher gerade nicht verfügbar).")
    return ok


def _idee(daten, iid):
    return next((i for i in daten["ideen"] if i["id"] == iid), None)


def _aendern(h, daten, iid, aenderung, meldung):
    i = _idee(daten, iid)
    if i is None:
        return
    aenderung(i)
    i["geaendert"] = M.jetzt_iso()
    _speichern(h, daten, meldung)


def _oeffnen(iid):
    st.session_state[P + "auswahl"] = iid
    st.session_state[P + "bereich_neu"] = "Idee bearbeiten"


# ---------------------------------------------------------------- Charts
def _chart(fig, key, hoehe=320):
    fig.update_layout(height=hoehe, margin=dict(l=8, r=8, t=30, b=8),
                      legend=dict(orientation="h", y=-0.18, x=0))
    UI.chart_stil(fig)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=key)


def chart_kumuliert(auswertungen, key, nur_real=False):
    """auswertungen: [(name, auswertung)]; je Szenario bzw. je Idee die kumulierte Cashflow-Linie,
    Null-Linie = Break-even (Investition zurueckverdient)."""
    fig = go.Figure()
    for name, a in auswertungen:
        for k, titel in M.SZENARIEN.items():
            if nur_real and k != "real":
                continue
            v = a["szenarien"][k]["verlauf"]
            fig.add_trace(go.Scatter(
                x=[z["monat"] for z in v], y=[z["kumuliert"] for z in v], mode="lines",
                name=name if nur_real else titel, line=dict(width=2.4 if k == "real" else 1.6,
                                                           color=None if nur_real else SZ_FARBE[k],
                                                           dash=None if k == "real" else "dot"),
                hovertemplate="Monat %{x}: %{y:,.0f} €<extra>" + html.escape(name if nur_real else titel) + "</extra>"))
    fig.add_hline(y=0, line=dict(color="#E5A50A", width=1.5, dash="dash"), annotation_text="Break-even",
                  annotation_position="top left")
    if len(auswertungen) == 1:
        m = auswertungen[0][1]["amortisation"]
        if m:
            fig.add_vline(x=m, line=dict(color="#E5A50A", width=1, dash="dot"))
    fig.update_xaxes(title_text="Monat")
    fig.update_yaxes(title_text="kumulierter Cashflow €")
    _chart(fig, key)


def chart_radar(ideen, key):
    namen = [t for _, t, _ in M.PHASEN]
    fig = go.Figure()
    for i in ideen:
        werte = [i["phasen"][nr]["score"] for nr, _, _ in M.PHASEN]
        fig.add_trace(go.Scatterpolar(r=werte + werte[:1], theta=namen + namen[:1], fill="toself", name=i["name"],
                                      opacity=0.75, hovertemplate="%{theta}: %{r}<extra></extra>"))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 10], dtick=2,
                                                                          gridcolor=UI.CHART_RASTER),
                                 angularaxis=dict(gridcolor=UI.CHART_RASTER)), showlegend=len(ideen) > 1)
    _chart(fig, key, 340)


def chart_tornado(sens, key):
    basis = sens["basis"]
    pct = int(sens["delta"] * 100)
    breite = max((abs(w - basis) for _, *ws in sens["zeilen"] for w in ws), default=0) or 1
    fig = go.Figure()
    for name, minus, plus in reversed(sens["zeilen"]):
        for wert, text, farbe in ((minus, f"−{pct} %", "#F87171" if minus < basis else "#5EEAD4"),
                                  (plus, f"+{pct} %", "#5EEAD4" if plus > basis else "#F87171")):
            schmal = abs(wert - basis) < 0.25 * breite        # schmale Balken: Text daneben statt gestaucht
            fig.add_trace(go.Bar(y=[name], x=[wert - basis], base=[basis], orientation="h", marker_color=farbe,
                                 name=text, showlegend=False, text=[text], textangle=0,
                                 textposition="outside" if schmal else "inside", cliponaxis=False,
                                 hovertemplate=f"{name} {text}: NPV %{{customdata:,.0f}} €<extra></extra>",
                                 customdata=[wert]))
    fig.add_vline(x=basis, line=dict(color="#E8ECF6", width=1.5), annotation_text=f"NPV {_eur(basis)}",
                  annotation_position="top")
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title_text="NPV €")
    _chart(fig, key, 220)


# ---------------------------------------------------------------- Bereiche
def _kennzahl_karte(r):
    zeile = (f"<b>Nutzwert</b> {FMT.zahl(r['nutzwert'], 0)} · <b>EKS</b> {FMT.zahl(r['eks'], 0)} · "
             f"<b>NPV</b> {_eur(r['npv'])} · <b>Amortisation</b> {_monate(r['amortisation'])} · "
             f"<b>€/h</b> {_eur_h(r['euro_h'])}")
    grund = (" · ".join(r["verfehlt"]) if r["verfehlt"] else "alle Bedingungen erfüllt")
    return (f'<div class="eks-karte"><div class="eks-kopf">{R.AMPEL[r["ampel"]]} {html.escape(r["name"])}'
            f'<span style="font-weight:400;color:#A9B1C4;font-size:.85rem">· {M.STATUS[r["status"]]}</span></div>'
            f'<div class="eks-zeile">{zeile}</div><div class="eks-grund">{html.escape(grund)}</div></div>')


def _uebersicht(h, daten):
    rang = R.rangliste(daten)
    with st.form(P + "neu_form", clear_on_submit=True, border=False):
        name = st.text_input("Neue Idee", placeholder="z. B. Online-Kurs Excel für Handwerker",
                             key=P + "neu_name")
        if st.form_submit_button("➕ Idee anlegen", use_container_width=True):
            i = M.neue_idee(name or "Neue Idee", daten["einstellungen"])
            daten["ideen"].append(i)
            _speichern(h, daten, f"„{i['name']}“ angelegt")
            _oeffnen(i["id"])
            st.rerun()
    if not rang:
        st.info("Noch keine Ideen. Lege oben die erste an – danach EKS-Phasen, Nutzwert und Finanzen ausfüllen.")
        return
    gruen = sum(1 for r in rang if r["ampel"] == "gruen")
    st.caption(f"{len(rang)} Ideen · {gruen} auf Grün · sortiert nach Ampel, Nutzwert und NPV (realistisch); "
               "verworfene am Ende")
    if UI.ist_smartphone():
        sortierung = st.selectbox("Sortieren nach", ["Ampel", "Nutzwert", "NPV", "Amortisation", "€/h"],
                                  key=P + "sort")
        schluessel = {"Nutzwert": lambda r: -(r["nutzwert"] or 0), "NPV": lambda r: -r["npv"],
                      "Amortisation": lambda r: r["amortisation"] if r["amortisation"] is not None else 10 ** 6,
                      "€/h": lambda r: -(r["euro_h"] if r["euro_h"] is not None else 10 ** 6)}.get(sortierung)
        if schluessel:
            rang = sorted(rang, key=schluessel)
        for r in rang:
            st.markdown(_kennzahl_karte(r), unsafe_allow_html=True)
            if st.button("Öffnen", key=P + "auf_" + r["id"], use_container_width=True):
                _oeffnen(r["id"])
                st.rerun()
        return
    df = pd.DataFrame([{"Ampel": R.AMPEL[r["ampel"]], "Idee": r["name"], "Status": M.STATUS[r["status"]],
                        "Nutzwert": round(r["nutzwert"] or 0), "NPV €": round(r["npv"]),
                        "Amortisation Mon.": r["amortisation"],
                        "€/h": None if r["euro_h"] is None else round(r["euro_h"], 2)} for r in rang])
    cfg = UI.tabellen_spalten(df, fortschritt=["Nutzwert"])
    cfg["Amortisation Mon."] = st.column_config.NumberColumn("Amortisation Mon.", format="%d",
                                                             help="leer = im Horizont nicht erreicht")
    st.dataframe(df, hide_index=True, use_container_width=True, column_config=cfg,
                 height=min(560, 38 + 35 * len(df)))
    sp = st.columns([3, 1], vertical_alignment="bottom")
    wahl = sp[0].selectbox("Idee öffnen", [r["id"] for r in rang], key=P + "auf_wahl",
                           format_func=lambda i: next(r["name"] for r in rang if r["id"] == i))
    if sp[1].button("Öffnen", key=P + "auf_knopf", use_container_width=True):
        _oeffnen(wahl)
        st.rerun()


def _kopf(r):
    st.markdown(f"### {R.AMPEL[r['ampel']]} {html.escape(r['name'])}")
    st.caption(("Ampel " + R.AMPEL_TEXT[r["ampel"]] + ": " + (" · ".join(r["verfehlt"]) if r["verfehlt"]
                                                            else "Nutzwert, NPV und €/Stunde erfüllt")))
    n = 2 if UI.ist_smartphone() else 3
    werte = [("Nutzwert", FMT.zahl(r["nutzwert"], 0) + " / 100"), ("EKS-Score", FMT.zahl(r["eks"], 0) + " / 100"),
             ("NPV (realistisch)", _eur(r["npv"])), ("IRR p. a.", _irr(r["irr"])),
             ("Amortisation", _monate(r["amortisation"])), ("Gewinn je Stunde", _eur_h(r["euro_h"]))]
    for start in range(0, len(werte), n):
        sp = st.columns(n)
        for c, (t, w) in zip(sp, werte[start:start + n]):
            c.metric(t, w)


def _stammdaten(h, daten, i):
    with st.expander("Name, Beschreibung, Status", expanded=False):
        with st.form(P + "stamm_" + i["id"], border=False):
            name = st.text_input("Name", i["name"], max_chars=120)
            beschr = st.text_area("Beschreibung", i["beschreibung"], height=90)
            status = st.selectbox("Status", list(M.STATUS), index=list(M.STATUS).index(i["status"]),
                                  format_func=M.STATUS.get)
            if st.form_submit_button("💾 Speichern", use_container_width=True):
                def f(x):
                    x["name"], x["beschreibung"] = name.strip() or x["name"], beschr
                    M.status_setzen(x, status)
                _aendern(h, daten, i["id"], f, "Stammdaten gespeichert")
                st.rerun()
        st.caption(f"Erstellt {i['erstellt'].replace('T', ' ')} · geändert {i['geaendert'].replace('T', ' ')} · "
                   f"Status seit {i['status_seit'][:10]}")
        weg = st.checkbox("Idee endgültig löschen", key=P + "weg_" + i["id"])
        if weg and st.button("🗑️ Löschen bestätigen", key=P + "weg_ok_" + i["id"]):
            daten["ideen"] = [x for x in daten["ideen"] if x["id"] != i["id"]]
            st.session_state.pop(P + "auswahl", None)
            _speichern(h, daten, f"„{i['name']}“ gelöscht")
            st.rerun()


def _tab_phasen(h, daten, i):
    st.caption("Die sieben Phasen der EKS: Text = deine Antwort, Score = wie stark die Idee hier ist "
               "(1 schwach … 10 sehr stark).")
    with st.form(P + "phasen_" + i["id"], border=False):
        neu = {}
        for nr, titel, frage in M.PHASEN:
            p = i["phasen"][nr]
            st.markdown(f"**{nr}. {titel}**")
            t = st.text_area(frage, p["text"], height=80, key=P + f"ph_t_{i['id']}_{nr}")
            s = st.slider(f"Score {titel}", 1, 10, int(p["score"]), key=P + f"ph_s_{i['id']}_{nr}")
            neu[nr] = {"text": t, "score": s}
        if st.form_submit_button("💾 EKS-Phasen speichern", use_container_width=True):
            _aendern(h, daten, i["id"], lambda x: x.update(phasen=neu), "EKS-Phasen gespeichert")
            st.rerun()
    chart_radar([i], P + "radar_" + i["id"])


def _tab_nutzwert(h, daten, i, r):
    kr = daten["einstellungen"]["kriterien"]
    st.caption("Score 1–10 je Kriterium. Bei inversen Kriterien (Wettbewerb, Zeitbedarf, Risiko) heißt ein hoher "
               "Score „viel davon“ – das senkt den Nutzwert. Gewichte unter „Einstellungen“.")
    with st.form(P + "nw_" + i["id"], border=False):
        neu = {}
        for k in kr:
            label = f"{k['name']} ({FMT.zahl(k['gewicht'], 0)} %{', invers' if k['invers'] else ''})"
            neu[k["id"]] = st.slider(label, 1, 10, int(i["kriterien"].get(k["id"], M.SCORE_START)),
                                     key=P + f"nw_{i['id']}_{k['id']}")
        if st.form_submit_button("💾 Nutzwert speichern", use_container_width=True):
            _aendern(h, daten, i["id"], lambda x: x["kriterien"].update(neu), "Nutzwert gespeichert")
            st.rerun()
    g = sum(k["gewicht"] for k in kr) or 1
    df = pd.DataFrame([{"Kriterium": k["name"] + (" (invers)" if k["invers"] else ""),
                        "Score": i["kriterien"].get(k["id"], M.SCORE_START),
                        "Beitrag": round(k["gewicht"] / g * R._norm(i["kriterien"].get(k["id"], M.SCORE_START),
                                                                    k["invers"]), 1)} for k in kr])
    st.dataframe(df, hide_index=True, use_container_width=True, column_config=UI.tabellen_spalten(df))
    st.markdown(f"**Nutzwert: {FMT.zahl(r['nutzwert'], 1)} / 100** (Schwelle "
                f"{FMT.zahl(daten['einstellungen']['schwelle_nutzwert'], 0)})")


FIN_FELDER = [("start_invest", "Startinvestition €", 0.0, 100.0), ("umsatz_monat", "Umsatz je Monat (voll) €", 0.0, 50.0),
              ("var_kosten_pct", "Variable Kosten % vom Umsatz", 0.0, 1.0),
              ("fix_monat", "Fixkosten je Monat €", 0.0, 10.0), ("stunden_woche", "Stunden je Woche", 0.0, 1.0),
              ("anlauf_monate", "Anlaufzeit bis vollen Umsatz (Monate)", 0, 1),
              ("horizont_jahre", "Betrachtungshorizont (Jahre)", 1, 1), ("steuersatz_pct", "Steuersatz-Annahme %", 0.0, 1.0)]


def _tab_finanzen(h, daten, i, r):
    f = i["finanzen"]
    with st.form(P + "fin_" + i["id"], border=False):
        neu = {}
        sp = _spalten(2)
        for n, (k, label, mini, schritt) in enumerate(FIN_FELDER):
            lo, hi = M.GRENZEN[k]
            ganz = k in M.GANZZAHL
            neu[k] = sp[n % 2].number_input(label, min_value=int(lo) if ganz else float(lo),
                                            max_value=int(hi) if ganz else float(hi),
                                            value=int(f[k]) if ganz else float(f[k]), step=schritt,
                                            key=P + f"fin_{i['id']}_{k}")
        if st.form_submit_button("💾 Finanzen speichern", use_container_width=True):
            _aendern(h, daten, i["id"], lambda x: x["finanzen"].update(neu), "Finanzen gespeichert")
            st.rerun()
    real = r["szenarien"]["real"]
    e = daten["einstellungen"]
    zeilen = [("Break-even-Umsatz je Monat", "nicht erreichbar (variable Kosten ≥ 100 %)"
               if r["break_even_umsatz"] is None else _eur(r["break_even_umsatz"])),
              ("Break-even-Monat (erster Monat mit Gewinn)", _monate(r["break_even_monat"]).replace(" Mon.", ". Monat")
               if r["break_even_monat"] else "nicht erreicht"),
              ("Amortisation der Startinvestition", _monate(r["amortisation"])),
              (f"NPV bei {FMT.pct(e['diskont_pa'], 1)} p. a.", _eur(r["npv"])), ("IRR p. a.", _irr(r["irr"])),
              ("Gewinn nach Steuern je Stunde", f"{_eur_h(r['euro_h'])} (Mindestsatz "
                                                 f"{_eur(e['mindest_stundensatz'], 2)})"),
              ("Stunden je Monat", FMT.zahl(r["stunden_monat"], 1)),
              ("Summe Cashflow im Horizont", _eur(real["summe_cf"]))]
    st.markdown("\n".join(f"- {t}: **{w}**" for t, w in zeilen))
    st.markdown("**Kumulierter Cashflow je Szenario**")
    chart_kumuliert([(i["name"], r)], P + "cf_" + i["id"])
    st.markdown(f"**Sensitivität: NPV bei ±{int(R.SENSITIVITAET * 100)} % Umsatz bzw. Kosten**")
    chart_tornado(r["sensitivitaet"], P + "tornado_" + i["id"])


def _tab_szenarien(h, daten, i, r):
    st.caption("Faktoren auf Umsatz und Kosten (variable + fixe) je Szenario, z. B. 70 % Umsatz und 115 % Kosten "
               "im pessimistischen Fall.")
    with st.form(P + "sz_" + i["id"], border=False):
        neu = {}
        for k, titel in M.SZENARIEN.items():
            st.markdown(f"**{titel.capitalize()}**")
            sp = st.columns(2)
            u = sp[0].number_input("Umsatz %", 0.0, 1000.0, round(i["szenarien"][k]["umsatz"] * 100, 1), 5.0,
                                   key=P + f"sz_{i['id']}_{k}_u")
            ko = sp[1].number_input("Kosten %", 0.0, 1000.0, round(i["szenarien"][k]["kosten"] * 100, 1), 5.0,
                                    key=P + f"sz_{i['id']}_{k}_k")
            neu[k] = {"umsatz": u / 100, "kosten": ko / 100}
        if st.form_submit_button("💾 Szenarien speichern", use_container_width=True):
            _aendern(h, daten, i["id"], lambda x: x.update(szenarien=neu), "Szenarien gespeichert")
            st.rerun()
    df = pd.DataFrame({"Kennzahl": ["NPV €", "IRR % p. a.", "Amortisation Mon.", "€ je Stunde"]} |
                      {titel: [round(s["npv"]), None if s["irr"] is None else round(s["irr"] * 100, 1),
                               s["amortisation"], None if s["euro_h"] is None else round(s["euro_h"], 2)]
                       for k, titel in M.SZENARIEN.items() for s in [r["szenarien"][k]]})
    st.dataframe(df, hide_index=True, use_container_width=True, column_config=UI.tabellen_spalten(df))
    st.caption("Leere Amortisation = im Horizont nicht erreicht; leerer IRR = nicht definiert (kein Vorzeichenwechsel).")
    chart_kumuliert([(i["name"], r)], P + "sz_cf_" + i["id"])


def _detail(h, daten):
    if not daten["ideen"]:
        st.info("Noch keine Ideen – unter „Übersicht“ eine anlegen.")
        return
    ids = [i["id"] for i in daten["ideen"]]
    s = st.session_state
    if s.get(P + "auswahl") not in ids:
        s[P + "auswahl"] = ids[0]
    iid = st.selectbox("Idee", ids, key=P + "auswahl", format_func=lambda x: _idee(daten, x)["name"])
    i = _idee(daten, iid)
    r = R.auswerten(i, daten["einstellungen"])
    _kopf(r)
    _stammdaten(h, daten, i)
    t1, t2, t3, t4 = st.tabs(["EKS-Phasen", "Nutzwert", "Finanzen", "Szenarien"])
    with t1:
        _tab_phasen(h, daten, i)
    with t2:
        _tab_nutzwert(h, daten, i, r)
    with t3:
        _tab_finanzen(h, daten, i, r)
    with t4:
        _tab_szenarien(h, daten, i, r)


def _vergleich(daten):
    if len(daten["ideen"]) < 2:
        st.info("Für einen Vergleich mindestens zwei Ideen anlegen.")
        return
    rang = R.rangliste(daten)
    je = {r["id"]: r for r in rang}
    wahl = st.multiselect("2–3 Ideen wählen", [r["id"] for r in rang], default=[r["id"] for r in rang[:2]],
                          max_selections=3, key=P + "vgl", format_func=lambda x: je[x]["name"])
    if len(wahl) < 2:
        st.info("Mindestens zwei Ideen wählen.")
        return
    rs = [je[x] for x in wahl]
    zeilen = [("Ampel", lambda r: f"{R.AMPEL[r['ampel']]} {R.AMPEL_TEXT[r['ampel']]}"),
              ("Status", lambda r: M.STATUS[r["status"]]), ("Nutzwert", lambda r: FMT.zahl(r["nutzwert"], 0)),
              ("EKS-Score", lambda r: FMT.zahl(r["eks"], 0)), ("NPV realistisch", lambda r: _eur(r["npv"])),
              ("NPV pessimistisch", lambda r: _eur(r["szenarien"]["pess"]["npv"])),
              ("NPV optimistisch", lambda r: _eur(r["szenarien"]["opt"]["npv"])),
              ("IRR p. a.", lambda r: _irr(r["irr"])), ("Amortisation", lambda r: _monate(r["amortisation"])),
              ("Break-even-Umsatz", lambda r: _eur(r["break_even_umsatz"])), ("€ je Stunde", lambda r: _eur_h(r["euro_h"])),
              ("Stunden/Monat", lambda r: FMT.zahl(r["stunden_monat"], 0))]
    if UI.ist_smartphone():
        for r in rs:
            st.markdown(_kennzahl_karte(r), unsafe_allow_html=True)
    else:
        spalten = {}
        for n, r in enumerate(rs, 1):
            titel = r["name"][:28]
            spalten[titel if titel not in spalten else f"{titel} ({n})"] = [f(r) for _, f in zeilen]
        df = pd.DataFrame({"Kennzahl": [z for z, _ in zeilen]} | spalten)
        st.dataframe(df, hide_index=True, use_container_width=True, height=38 + 35 * len(df))
    st.markdown("**EKS-Phasen im Vergleich**")
    chart_radar([_idee(daten, x) for x in wahl], P + "vgl_radar")
    st.markdown("**Kumulierter Cashflow (realistisch)**")
    chart_kumuliert([(r["name"], r) for r in rs], P + "vgl_cf", nur_real=True)


def _einstellungen(h, daten):
    e = daten["einstellungen"]
    st.markdown("**Nutzwert-Kriterien und Gewichte**")
    st.caption("Gewichte in %, Summe muss 100 % ergeben. „Invers“ = viel davon ist schlecht (z. B. Risiko). "
               "Neue Zeile unten = neues Kriterium; bestehende Ideen starten dort mit Score 5.")
    df = pd.DataFrame([{"Kriterium": k["name"], "Gewicht %": k["gewicht"], "Invers": k["invers"], "_id": k["id"]}
                       for k in e["kriterien"]])
    with st.form(P + "einst", border=False):
        neu = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True,
                             column_order=["Kriterium", "Gewicht %", "Invers"], key=P + "kr_editor",
                             column_config={"Kriterium": st.column_config.TextColumn(width="medium"),
                                            "Gewicht %": st.column_config.NumberColumn(min_value=0, max_value=100,
                                                                                       step=1, format="%.0f",
                                                                                       width="small"),
                                            "Invers": st.column_config.CheckboxColumn(width="small")})
        sp = _spalten(3)
        schwelle = sp[0].number_input("Nutzwert-Schwelle (0–100)", 0.0, 100.0, float(e["schwelle_nutzwert"]), 5.0)
        mindest = sp[1].number_input("Mindest-Stundensatz €", 0.0, 100000.0, float(e["mindest_stundensatz"]), 1.0)
        diskont = sp[2].number_input("Diskontierungszins % p. a.", -50.0, 100.0, float(e["diskont_pa"]), 0.5,
                                     help="Opportunitätsrendite: was das Geld alternativ im Depot bringen würde "
                                          "(Standard 7 % p. a.).")
        st.markdown("**Standard-Szenarien für neue Ideen** (Faktoren in %)")
        sz = {}
        for k, titel in M.SZENARIEN.items():
            c = st.columns(2)
            sz[k] = {"umsatz": c[0].number_input(f"{titel.capitalize()}: Umsatz %", 0.0, 1000.0,
                                                 round(e["szenarien"][k]["umsatz"] * 100, 1), 5.0) / 100,
                     "kosten": c[1].number_input(f"{titel.capitalize()}: Kosten %", 0.0, 1000.0,
                                                 round(e["szenarien"][k]["kosten"] * 100, 1), 5.0) / 100}
        if st.form_submit_button("💾 Einstellungen speichern", use_container_width=True):
            kr, ids = [], set()
            for z in neu.to_dict("records"):
                name = str(z.get("Kriterium") or "").strip()
                if not name or name == "nan":
                    continue
                kid = z.get("_id") if isinstance(z.get("_id"), str) and z.get("_id") else M.kriterium_id(name, ids)
                ids.add(kid)
                gew = z.get("Gewicht %")
                kr.append({"id": kid, "name": name, "gewicht": float(gew) if gew == gew and gew is not None else 0.0,
                           "invers": bool(z.get("Invers")) if z.get("Invers") == z.get("Invers") else False})
            if not kr:
                st.error("Mindestens ein Kriterium ist nötig.")
            elif not M.gewichte_ok(kr):
                st.error(f"Die Gewichte ergeben {FMT.zahl(M.gewichte_summe(kr), 1)} % – bitte auf 100 % anpassen.")
            else:
                daten["einstellungen"] = {"kriterien": kr, "schwelle_nutzwert": schwelle,
                                          "mindest_stundensatz": mindest, "diskont_pa": diskont, "szenarien": sz}
                _speichern(h, daten, "Einstellungen gespeichert")
                st.rerun()
    st.caption(f"Aktuelle Summe der Gewichte: {FMT.zahl(M.gewichte_summe(e['kriterien']), 0)} %")
    _export_import(h, daten)
    _monatslauf(daten)


def _export_import(h, daten):
    with st.expander("⬇️ Export / ⬆️ Import (JSON, CSV)", expanded=False):
        heute = datetime.date.today().isoformat()
        rang = R.rangliste(daten)
        sp = _spalten(2)
        sp[0].download_button("JSON herunterladen (alles)", M.export_json(daten).encode("utf-8"),
                              file_name=f"eks_ideen_{heute}.json", mime="application/json",
                              use_container_width=True, key=P + "dl_json")
        sp[1].download_button("CSV herunterladen (mit Kennzahlen)",
                              M.export_csv(daten, R.kennzahlen_export(rang)).encode("utf-8"),
                              file_name=f"eks_ideen_{heute}.csv", mime="text/csv", use_container_width=True,
                              key=P + "dl_csv")
        st.caption("Import: Ideen mit gleicher id werden ersetzt, neue angehängt. Die CSV trägt nur Scores und "
                   "Finanzen – Phasentexte bestehender Ideen bleiben erhalten.")
        datei = st.file_uploader("Datei wählen", type=["json", "csv"], key=P + "upload")
        mit_einst = st.checkbox("Bei JSON auch Gewichte und Schwellen übernehmen", key=P + "imp_einst")
        if datei is not None and st.button("Importieren", key=P + "imp_ok", use_container_width=True):
            try:
                text = datei.getvalue().decode("utf-8-sig")
                if datei.name.lower().endswith(".csv"):
                    neu, n, ers = M.import_csv(daten, text)
                else:
                    neu, n, ers = M.import_json(daten, text, mit_einst)
            except (ValueError, UnicodeDecodeError) as e:
                st.error(f"Import nicht möglich: {e}")
            else:
                _speichern(h, neu, f"Import: {n} neu, {ers} ersetzt")
                st.rerun()


def _monatslauf(daten):
    lauf = daten.get("letzter_lauf") or {}
    with st.expander("🗓️ Letzter Monatslauf", expanded=False):
        if not lauf.get("stand"):
            st.caption("Noch kein Monatslauf. Er läuft am 1. jedes Monats als GitHub Action "
                       "„EKS-Ideen monatlich auswerten“ (oder manuell: Actions → Run workflow) und schickt die "
                       "Zusammenfassung zusätzlich an Discord, sofern der Webhook erreichbar ist.")
            return
        st.caption(f"Stand {str(lauf['stand']).replace('T', ' ')} · Discord: {lauf.get('discord') or '–'}")
        for z in lauf.get("text") or []:
            st.markdown(f"- {html.escape(str(z))}")


# ---------------------------------------------------------------- Seite
def seite(h=None):
    h = h or {}
    with st.container(key="eks_seite"):
        _seite(h)


def _seite(h):
    st.markdown(CSS, unsafe_allow_html=True)
    schritte.leiste(st, "eks")
    daten = _daten(h)
    s = st.session_state
    if s.get(P + "lesefehler"):
        st.warning("Die gespeicherten Ideen sind gerade nicht lesbar – Änderungen gelten nur für diese Sitzung, "
                   "damit nichts überschrieben wird.")
    if s.get(P + "meldung"):
        st.toast(s.pop(P + "meldung"))
    if s.get(P + "bereich_neu"):
        s[P + "bereich"] = s.pop(P + "bereich_neu")
    s.setdefault(P + "bereich", BEREICHE[0])
    schritte.titel(st, "eks", 1)
    bereich = st.segmented_control("Bereich", BEREICHE, key=P + "bereich", label_visibility="collapsed") \
        or BEREICHE[0]
    if bereich == "Übersicht":
        _uebersicht(h, daten)
    elif bereich == "Idee bearbeiten":
        schritte.titel(st, "eks", 2)
        _detail(h, daten)
    elif bereich == "Vergleich":
        schritte.titel(st, "eks", 3)
        _vergleich(daten)
    else:
        schritte.titel(st, "eks", 4)
        _einstellungen(h, daten)
    st.caption("Vereinfachte Annahmen: linearer Umsatz-Hochlauf, Steuer nur auf positive Monatsgewinne, kein Restwert, "
               "monatliche Diskontierung. Orientierungshilfe, keine Steuer- oder Anlageberatung.")
