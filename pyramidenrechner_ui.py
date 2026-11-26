"""Pyramidenrechner (Menuepunkt „Pyramidenrechner“) - Oberflaeche. Rechnungen: pyramidenrechner.py.

Reine Planrechnung: unabhaengig von Kontostand, Depot und Finanzdaten, keine Buchungen. Die aktuelle Eingabe merkt
die App wie bei den anderen Rechnern (Praefix "prr_"); benannte Szenarien liegen je Benutzer in
state/pyramidenrechner.json.
h = {"lesen": (pfad, default) -> (daten, ok), "aktualisiere": (pfad, aendern, default, msg) -> (ok, neu),
     "upfad": (basis) -> pfad, "speichern": bool} - ohne h keine Szenarien."""
import datetime
import html
import logging
import uuid

import streamlit as st

import durchschnittskurs as DK
import pyramidenrechner as PR
import ui_stil as UI

P = "prr_"
DATEI = "state/pyramidenrechner.json"
START_STUFEN = 4
FELDER = ("stueck", "preis", "mult", "modus", "auto", "aend", "budget")

CSS = """<style>
.prr-titel { font-size:1.55rem; font-weight:800; color:#ffffff; margin:0 0 2px; }
.prr-unter { color:#A9ACB0; font-size:.85rem; margin-bottom:6px; }
.prr-nr { color:#A9ACB0; font-size:1rem; min-width:1.9rem; }
.prr-st { font-size:.92rem; color:#E8ECF6; font-variant-numeric:tabular-nums; line-height:1.25; }
.prr-st small { color:#A9ACB0; font-size:.75rem; display:block; }
.prr-raster { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:10px; margin:8px 0 6px; }
@media (max-width: 900px) { .prr-raster { grid-template-columns:repeat(3, minmax(0,1fr)); } }
@media (max-width: 560px) { .prr-raster { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.prr-kachel { background:rgba(255,255,255,.04); border-radius:14px; padding:10px 12px; min-width:0; }
.prr-kachel .t { color:#A9ACB0; font-size:.78rem; }
.prr-kachel .w { color:#ffffff; font-size:1.25rem; font-weight:700; font-variant-numeric:tabular-nums;
    word-break:break-all; }
.prr-kachel .w.gross { color:#4ADE80; }
.prr-kachel .w.neg { color:#F87171; }
.prr-ueber { color:#F87171; }
</style>"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _ek(i):
    return f"{P}e{i}"


def _n(ss):
    try:
        return max(1, min(int(ss.get(P + "n") or START_STUFEN), PR.MAX_STUFEN))
    except (TypeError, ValueError):
        return START_STUFEN


def _eigene(ss, n=None):
    return {i: ss.get(_ek(i)) for i in range(1, n if n is not None else _n(ss)) if str(ss.get(_ek(i)) or "").strip()}


def _param(ss):
    return PR.parameter(ss.get(P + "stueck"), ss.get(P + "preis"), ss.get(P + "mult") or "2",
                        ss.get(P + "modus", "stueck"), ss.get(P + "auto", False), ss.get(P + "aend"),
                        ss.get(P + "budget"))


def _fmt(x, n=2):
    return DK.de(x, n) if x is not None else "–"


def _kurs(x):
    """Stueckpreis: 2 Nachkommastellen, unter 1 bis zu 8 (damit nicht 0,00 dasteht)."""
    return DK.de(x, DK.NACHKOMMA if x < 1 else 2, 2) if x is not None else "–"


def _stk(x):
    return DK.stueck_text(x)


# ---------------------------------------------------------------------------------------------------- Aktionen
def _weiter():
    ss = st.session_state
    ss[P + "n"] = min(_n(ss) + 1, PR.MAX_STUFEN)


def _entfernen(i):
    ss = st.session_state
    n = _n(ss)
    alt = _eigene(ss, n)
    for k in range(1, n):
        ss.pop(_ek(k), None)
    for k, t in PR.eigene_verschieben(alt, i).items():
        ss[_ek(k)] = t
    ss[P + "n"] = max(1, n - 1)


def _bis_budget():
    ss = st.session_state
    try:
        p = _param(ss)
    except PR.EingabeFehler as ex:
        ss[P + "meldung"] = ("warn", str(ex))
        return
    if p["budget"] is None:
        ss[P + "meldung"] = ("warn", "Bitte zuerst ein Budget eintragen.")
        return
    n = PR.bis_budget(p, _eigene(ss, PR.MAX_STUFEN))
    ss[P + "n"] = n
    ss[P + "meldung"] = ("ok", f"{n} Stufe{'n' if n != 1 else ''} passen ins Budget.")


def _modus_gewechselt():
    """Startpreis und eigene Preise beim Umschalten Stueckpreis <-> Gesamtpreis umrechnen."""
    ss = st.session_state
    neu = ss.get(P + "modus", "stueck")
    try:
        s0 = DK.zahl(ss.get(P + "stueck"), "Startstückzahl")
        m = DK.zahl(ss.get(P + "mult") or "2", "Multiplikator")
    except PR.EingabeFehler:
        return
    for i, k in [(0, P + "preis")] + [(i, _ek(i)) for i in range(1, _n(ss))]:
        try:
            w = DK.zahl(ss.get(k), "Preis")
        except PR.EingabeFehler:
            continue
        menge = s0 * m ** i
        ss[k] = DK.de(w * menge if neu == "gesamt" else w / menge, DK.NACHKOMMA, 2)


def _zuruecksetzen():
    ss = st.session_state
    for k in [P + f for f in FELDER] + [_ek(i) for i in range(1, PR.MAX_STUFEN)] + [P + "n", P + "aktiv"]:
        ss.pop(k, None)


# ---------------------------------------------------------------------------------------------------- Szenarien
def _laden(h):
    try:
        d, ok = h["lesen"](h["upfad"](DATEI), {"szenarien": []})
    except Exception:
        d, ok = {"szenarien": []}, False
    liste = d.get("szenarien") if isinstance(d, dict) and isinstance(d.get("szenarien"), list) else []
    return [s for s in liste if isinstance(s, dict) and s.get("id")], ok


def _speichern(h, aendern, text):
    if not h.get("speichern"):
        st.session_state[P + "meldung"] = ("warn", "Speichern ist gerade nicht möglich (kein Datenspeicher).")
        return False

    def f(alt):
        liste = alt.get("szenarien") if isinstance(alt, dict) and isinstance(alt.get("szenarien"), list) else []
        return {"szenarien": aendern(list(liste))}
    try:
        ok, _ = h["aktualisiere"](h["upfad"](DATEI), f, {"szenarien": []}, f"pyramidenrechner: {text} [skip ci]")
    except Exception as ex:
        logging.warning("Pyramidenrechner: Speichern fehlgeschlagen (%s)", type(ex).__name__)
        ok = False
    st.session_state[P + "meldung"] = ("ok", f"Gespeichert: {text}.") if ok else \
        ("warn", "Speichern fehlgeschlagen – bitte erneut versuchen.")
    return bool(ok)


def _stand(ss):
    return {"werte": {f: ss.get(P + f) for f in FELDER}, "n": _n(ss),
            "eigene": {str(i): t for i, t in _eigene(ss).items()}}


def _szenario_laden(s):
    ss = st.session_state
    _zuruecksetzen()
    for f, v in (s.get("werte") or {}).items():
        if f in FELDER and v is not None:
            ss[P + f] = v
    ss[P + "n"] = int(s.get("n") or START_STUFEN)
    for i, t in (s.get("eigene") or {}).items():
        ss[_ek(int(i))] = t
    ss[P + "aktiv"] = s["id"]
    ss[P + "meldung"] = ("ok", f"Szenario „{s.get('name')}“ geladen – ändern und mit „Aktualisieren“ speichern.")


def _berechne_szenario(s):
    w = s.get("werte") or {}
    p = PR.parameter(w.get("stueck"), w.get("preis"), w.get("mult") or "2", w.get("modus", "stueck"),
                     w.get("auto", False), w.get("aend"), w.get("budget"))
    zeilen, _ = PR.stufen(p, int(s.get("n") or 1), {int(i): t for i, t in (s.get("eigene") or {}).items()})
    return p, zeilen, PR.uebersicht(p, zeilen)


def _szenarien(h):
    ss = st.session_state
    if not h or not h.get("lesen"):
        return
    liste, ok = _laden(h)
    st.markdown("#### Szenarien")
    aktiv = next((s for s in liste if s["id"] == ss.get(P + "aktiv")), None)
    if ss.pop(P + "sz_leeren", False):
        ss.pop(P + "sz_name", None)
    with st.container(horizontal=True, key=P + "sz_neu", vertical_alignment="bottom", gap="small"):
        name = st.text_input("Name des Szenarios", key=P + "sz_name", max_chars=60,
                             placeholder="z. B. Nasdaq-ETF, Budget 5.000 €")
        if st.button("Als neues Szenario speichern", icon=":material/save:", key=P + "sz_save_btn",
                     disabled=not (name or "").strip() or not ok):
            neu = dict(_stand(ss), id=uuid.uuid4().hex[:8], name=name.strip()[:60],
                       datum=datetime.date.today().isoformat())
            if _speichern(h, lambda x: x + [neu], f"Szenario „{neu['name']}“"):
                ss[P + "aktiv"] = neu["id"]
                ss[P + "sz_leeren"] = True
                st.rerun()
    if aktiv:
        st.caption(f"Geladen: **{_e(aktiv.get('name'))}**")
        if st.button(f"„{aktiv.get('name')}“ mit der aktuellen Eingabe aktualisieren", icon=":material/sync:",
                     key=P + "sz_upd_btn"):
            if _speichern(h, lambda x: [dict(s, **_stand(ss), datum=datetime.date.today().isoformat())
                                        if s["id"] == aktiv["id"] else s for s in x], f"„{aktiv.get('name')}“"):
                st.rerun()
        neu_name = (name or "").strip()[:60]
        if neu_name and neu_name != aktiv.get("name") and st.button(
                f"„{aktiv.get('name')}“ in „{neu_name}“ umbenennen", icon=":material/edit:", key=P + "sz_ren_btn",
                type="tertiary"):
            if _speichern(h, lambda x: [dict(s, name=neu_name) if s["id"] == aktiv["id"] else s for s in x],
                          f"umbenannt in „{neu_name}“"):
                ss[P + "sz_leeren"] = True
                st.rerun()
    if not liste:
        st.caption("Noch keine Szenarien gespeichert.")
        return
    for s in liste:
        with st.container(horizontal=True, key=P + f"sz_{s['id']}", vertical_alignment="center", gap="small"):
            try:
                _, _, u = _berechne_szenario(s)
                info = f"{u['stufen']} Stufen · {_stk(u['stueck'])} Stk. · {_fmt(u['kosten'])} €"
            except PR.EingabeFehler:
                info = "unvollständig"
            st.markdown(f'<div class="prr-st"><b>{_e(s.get("name"))}</b><small>{_e(info)} · {_e(s.get("datum"))}'
                        f'</small></div>', unsafe_allow_html=True, width="stretch")
            st.button("Laden", key=P + f"sz_load_{s['id']}_btn", type="tertiary", on_click=_szenario_laden,
                      args=(s,))
            if st.button("", icon=":material/delete:", key=P + f"sz_del_{s['id']}_btn", type="tertiary",
                         help="Szenario löschen"):
                if _speichern(h, lambda x, i=s["id"]: [y for y in x if y["id"] != i], f"„{s.get('name')}“ gelöscht"):
                    if ss.get(P + "aktiv") == s["id"]:
                        ss.pop(P + "aktiv", None)
                    st.rerun()
    if len(liste) >= 2:
        _vergleich(liste)


def _vergleich(liste):
    import pandas as pd
    import plotly.graph_objects as go
    with st.expander("📊 Szenarien vergleichen", expanded=False):
        namen = {s["id"]: s.get("name") or s["id"] for s in liste}
        wahl = st.multiselect("Szenarien", list(namen), default=list(namen)[:3], format_func=namen.get,
                              key=P + "vgl")
        if not wahl:
            return
        zeilen_tab, fig = [], go.Figure()
        for sid in wahl:
            s = next(x for x in liste if x["id"] == sid)
            try:
                p, zeilen, u = _berechne_szenario(s)
            except PR.EingabeFehler:
                continue
            zeilen_tab.append({"Szenario": namen[sid], "Stufen": u["stufen"], "Stück": _stk(u["stueck"]),
                               "Gesamtkosten €": _fmt(u["kosten"]), "Ø-Preis €": _fmt(u["durchschnitt"]),
                               "Budget €": _fmt(u["budget"]) if u["budget"] is not None else "–",
                               "Rest €": _fmt(u["rest"]) if u["rest"] is not None else "–",
                               "weitere Stufen": u["weitere"] if u["weitere"] is not None else "–"})
            fig.add_trace(go.Scatter(x=[z["stufe"] for z in zeilen], y=[float(z["kosten_ges"]) for z in zeilen],
                                     mode="lines+markers", name=namen[sid]))
        st.dataframe(pd.DataFrame(zeilen_tab), hide_index=True, width="stretch", key=P + "vgl_tab")
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Stufe",
                          yaxis_title="Gesamtkosten €", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), width="stretch", key=P + "vgl_chart",
                        config={"displayModeBar": False})


# ---------------------------------------------------------------------------------------------------- Seite
def _diagramm(zeilen):
    import plotly.graph_objects as go
    fig = go.Figure()
    x = [z["stufe"] for z in zeilen]
    fig.add_bar(x=x, y=[float(z["stueck"]) for z in zeilen], name="Stück je Stufe", marker_color="#7C9CFF",
                yaxis="y")
    fig.add_scatter(x=x, y=[float(z["kosten_ges"]) for z in zeilen], name="Gesamtkosten (kumuliert) €",
                    mode="lines+markers", line=dict(color="#4ADE80", width=2), yaxis="y2")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(title="Stufe", dtick=1),
                      yaxis=dict(title="Stück"), yaxis2=dict(title="€", overlaying="y", side="right",
                                                              showgrid=False),
                      legend=dict(orientation="h", y=-0.25), bargap=0.35)
    st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), width="stretch", key=P + "chart",
                    config={"displayModeBar": False})


def _tabelle(zeilen, modus):
    import pandas as pd
    df = pd.DataFrame([{"Stufe": z["stufe"], "Stück": _stk(z["stueck"]), "Stückpreis €": _kurs(z["preis"]),
                        "Kosten der Stufe €": _fmt(z["kosten"]), "Stück gesamt": _stk(z["stueck_ges"]),
                        "Kosten gesamt €": _fmt(z["kosten_ges"]), "Ø-Preis €": _fmt(z["durchschnitt"]),
                        "Preis": "eigener" if z["eigen"] else ("automatisch" if z["stufe"] > 1 else "Start"),
                        "Budget": "✅" if z["im_budget"] else "❌ über Budget"} for z in zeilen])
    st.dataframe(df, hide_index=True, width="stretch", key=P + "tab")


def seite(h=None):
    ss = st.session_state
    st.markdown(CSS, unsafe_allow_html=True)
    if ss.get(P + "meldung"):
        art, text = ss.pop(P + "meldung")
        (st.success if art == "ok" else st.warning)(text)
    ss.setdefault(P + "mult", "2")
    if ss.get(P + "modus") not in PR.MODI:
        ss[P + "modus"] = "stueck"
    with st.container(border=True, key=P + "karte"):
        st.markdown('<div class="prr-titel">Pyramidenrechner</div><div class="prr-unter">Stückzahl je Stufe × '
                    'Multiplikator – reine Planrechnung, ohne Depot und ohne Buchungen</div>',
                    unsafe_allow_html=True)
        modus = st.radio("Preise eingeben als", list(PR.MODI), format_func=PR.MODI.get, key=P + "modus",
                         horizontal=True, on_change=_modus_gewechselt)
        sp = st.columns(3)
        sp[0].text_input("Startstückzahl", key=P + "stueck", placeholder="z. B. 1", max_chars=20)
        sp[1].text_input("Startpreis je Stück (€)" if modus == "stueck" else "Gesamtpreis Stufe 1 (€)",
                         key=P + "preis", placeholder="0,00", max_chars=20)
        sp[2].text_input("Multiplikator", key=P + "mult", max_chars=10, help="2 = Stückzahl verdoppeln")
        sp = st.columns(2, vertical_alignment="bottom")
        sp[0].text_input("Maximales Budget (€, optional)", key=P + "budget", placeholder="0,00", max_chars=20)
        with sp[1]:
            auto = st.toggle("Automatische Preisänderung", key=P + "auto",
                             help="Preis jeder weiteren Stufe ändert sich um den Prozentsatz (negativ = fallend)")
        if auto:
            st.text_input("Preisänderung je Stufe (%)", key=P + "aend", placeholder="z. B. 5 oder -10", max_chars=8)
        try:
            p = _param(ss)
        except PR.EingabeFehler as ex:
            p = None
            if any(str(ss.get(P + f) or "").strip() for f in ("stueck", "preis")):
                st.caption(f"⚠️ {ex}")
            else:
                st.caption("Startstückzahl und Startpreis eintragen – die Stufen erscheinen sofort.")
        if p is None:
            st.button("Zurücksetzen", icon=":material/refresh:", key=P + "reset_btn", type="tertiary",
                      on_click=_zuruecksetzen)
            _szenarien(h)
            return
        n = _n(ss)
        zeilen, fehler = PR.stufen(p, n, _eigene(ss, n))
        st.divider()
        for z in zeilen:
            i = z["stufe"] - 1
            with st.container(horizontal=True, wrap=False, key=P + f"stufe_{i}", vertical_alignment="center",
                              gap="small"):
                st.markdown(f'<div class="prr-nr">{z["stufe"]}.</div>', unsafe_allow_html=True, width="content")
                st.markdown(f'<div class="prr-st"><b>{_e(_stk(z["stueck"]))} Stk.</b><small>'
                            f'{"" if z["im_budget"] else "<span class=prr-ueber>über Budget · </span>"}'
                            f'{_e(_fmt(z["kosten"]))} €</small></div>', unsafe_allow_html=True, width=110)
                if i == 0:
                    st.markdown(f'<div class="prr-st">{_e(_kurs(z["preis"]))} €<small>Startpreis je Stück'
                                f'</small></div>', unsafe_allow_html=True, width="stretch")
                    st.markdown('<div style="width:2.2rem"></div>', unsafe_allow_html=True, width="content")
                else:
                    vorschlag = PR.auto_preis(p, i) * (z["stueck"] if modus == "gesamt" else 1)
                    st.text_input(f"Preis Stufe {z['stufe']}", key=_ek(i), label_visibility="collapsed",
                                  placeholder=f"{_fmt(vorschlag)} (auto)", max_chars=20,
                                  help="Leer lassen = automatischer Preis. "
                                       + ("Stückpreis" if modus == "stueck" else "Gesamtpreis dieser Stufe"))
                    st.button("", icon=":material/delete:", key=P + f"del_{i}_btn", type="tertiary",
                              help=f"Stufe {z['stufe']} entfernen", on_click=_entfernen, args=(i,))
        for nr, text in fehler:
            st.caption(f"⚠️ Stufe {nr}: {text} – es gilt der automatische Preis.")
        with st.container(horizontal=True, key=P + "knoepfe", gap="small"):
            st.button(f"Weiter ×{DK.de(p['multiplikator'], 2, 0)}", icon=":material/add:", key=P + "weiter_btn",
                      type="primary", on_click=_weiter, disabled=n >= PR.MAX_STUFEN, width="stretch")
            st.button("Bis zum Budget", icon=":material/savings:", key=P + "budget_btn", on_click=_bis_budget,
                      disabled=p["budget"] is None, width="stretch",
                      help="Fügt so viele Stufen hinzu bzw. entfernt sie, dass alles ins Budget passt"
                      if p["budget"] is not None else "Zuerst ein Budget eintragen")
        u = PR.uebersicht(p, zeilen)
        rest_css = "neg" if u["ueber_budget"] else ""
        kacheln = [("Gesamtstückzahl", _stk(u["stueck"]), ""), ("Gesamtkosten", f"{_fmt(u['kosten'])} €", ""),
                   ("Ø Stückpreis", f"{_fmt(u['durchschnitt'])} €", "gross"),
                   ("Verbleibendes Budget", f"{_fmt(u['rest'])} €" if u["rest"] is not None else "–", rest_css),
                   ("Weitere Verdopplungen" if p["multiplikator"] == 2 else "Weitere Stufen finanzierbar",
                    str(u["weitere"]) if u["weitere"] is not None else "–", "")]
        st.markdown('<div class="prr-raster">' + "".join(
            f'<div class="prr-kachel"><div class="t">{_e(t)}</div><div class="w {c}">{_e(w)}</div></div>'
            for t, w, c in kacheln) + "</div>", unsafe_allow_html=True)
        if u["ueber_budget"]:
            st.caption(f"⚠️ Die Gesamtkosten liegen {_fmt(-u['rest'])} € über dem Budget.")
        with st.container(horizontal=True, horizontal_alignment="center", key=P + "fuss"):
            st.button("Zurücksetzen", icon=":material/refresh:", key=P + "reset_btn", type="tertiary",
                      on_click=_zuruecksetzen)
    with st.expander("📋 Tabelle aller Stufen"):
        _tabelle(zeilen, modus)
    with st.expander("📈 Diagramm: Menge und Kosten", expanded=True):
        _diagramm(zeilen)
    _szenarien(h)
