"""Investment Scanner 2.0 - eigene Ansicht (Oberflaeche zu investment_scanner2.py).

Nachbau des HTML-Scanners "Echtdaten & Entnahmeplanung" mit den Daten der App: Universum aus den
Top-500-/Watchlist-Daten, aktuelle EUR-Kurse auf Knopfdruck von ls-tc.de, Bestandsdepot und eigene Werte per
CSV. Keine Orderausfuehrung, keine echte Auszahlung."""
import datetime
import html

import streamlit as st

import investment_scanner2 as E
import portfolio_builder_ui as B
import scanner as S

P = "is2_"                                         # Schluessel-Praefix in st.session_state
TOP_N = {"Top 50": 50, "Top 100": 100, "Top 250": 250, "Top 500": 500}
ANSATZ = {"auto": "✧ Automatisch", "defensiv": "Defensiv", "ausgewogen": "Ausgewogen", "wachstum": "Wachstum"}
ANSATZ_HINT = {"auto": "Innerhalb Risikolimit", "defensiv": "Stabilität im Fokus", "ausgewogen": "Breite Streuung",
               "wachstum": "Größere Schwankungen"}

CSS = """
<style>
.is2-chip { display:inline-block; padding:4px 10px; border-radius:999px; font-size:.72rem; font-weight:700;
  letter-spacing:.6px; background:#193c38; color:#9af1d4; }
.is2-chip.warn { background:#423523; color:#f4c67b; }
.pb-karte-t .is2-nr { color:#52d9b3; margin-right:6px; }
.is2-k { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin:8px 0; }
.is2-k .k { border:1px solid #262B33; border-radius:12px; padding:10px 12px; background:#0F1115; }
.is2-k .l { color:#9AA0A6; font-size:.7rem; text-transform:uppercase; letter-spacing:.4px; }
.is2-k .w { font-size:1.2rem; font-weight:800; margin-top:2px; }
.is2-k .s { color:#9AA0A6; font-size:.74rem; }
.is2-szen .c { min-height:150px; border:1px solid #262B33; border-radius:12px; padding:12px; background:#0F1115; }
.is2-szen .c.sel { border-color:#52d9b3; box-shadow:0 0 12px rgba(82,217,179,.25); }
.is2-szen .c.off { opacity:.55; }
.is2-szen .t { color:#9AA0A6; font-size:.7rem; text-transform:uppercase; letter-spacing:.6px; }
.is2-szen .n { font-weight:800; margin-top:2px; }
.is2-szen .v { font-size:1.35rem; font-weight:800; margin-top:4px; }
.is2-pos { color:#4ade80; } .is2-neg { color:#f87171; }
table.is2 { display:table !important; width:100% !important; border-collapse:separate; border-spacing:0; font-size:.84rem; }
table.is2 th { text-align:left; color:#9AA0A6; font-size:.7rem; letter-spacing:.4px; text-transform:uppercase;
  padding:6px 8px; border-bottom:1px solid #262B33; white-space:nowrap; }
table.is2 td { padding:6px 8px; border-bottom:1px solid #1A1E24; vertical-align:top; }
table.is2 .r { text-align:right; white-space:nowrap; }
table.is2 .m { color:#9AA0A6; font-size:.74rem; }
.is2-wrap { overflow-x:auto; }
.is2-wrap table.is2 { min-width:620px; }
table.is2 td.nm { min-width:160px; }
table.is2 .nr { width:36px; }
.is2-score { display:inline-block; min-width:42px; text-align:center; padding:2px 6px; border-radius:8px;
  background:#193c38; color:#9af1d4; font-weight:700; }
.is2-score.na { background:#2a2f37; color:#9AA0A6; }
.is2-mix { display:flex; height:16px; border-radius:8px; overflow:hidden; margin:6px 0; }
.is2-bar { height:8px; border-radius:4px; background:#1A1E24; overflow:hidden; }
.is2-bar > div { height:100%; }
.is2-leg { display:inline-flex; align-items:center; gap:5px; margin:2px 10px 2px 0; font-size:.8rem; }
.is2-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
@media (max-width: 640px) { .is2-k { grid-template-columns:repeat(2, minmax(0,1fr)); } }
/* Auswahlfelder in den Eingabezeilen beschriften wie die Zahlenfelder daneben (app-weit sind es Ueberschriften) */
.st-key-is2_seite [data-testid="stSelectbox"] label, .st-key-is2_seite [data-testid="stSelectbox"] label p {
  font-family:inherit !important; font-size:.875rem !important; font-weight:400 !important; letter-spacing:normal !important;
  text-transform:none !important; text-shadow:none !important; color:inherit !important; }
.st-key-is2_seite [data-testid="stSelectbox"] label { margin:0 0 4px 0 !important; }
</style>
"""


def _de(x, dez=0):
    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x, dez=0):
    return ("−" if x < -1e-9 else "") + _de(abs(x), dez) + " €"


def _pct(x, dez=1):
    return "–" if x is None else ("−" if x < 0 else "") + _de(abs(x), dez) + " %"


def _esc(t):
    return html.escape("" if t is None else str(t))


def _spalten(n):
    """n Felder nebeneinander, unten buendig (Handy: 2 je Zeile)."""
    if not B._smartphone():
        return st.columns(n, vertical_alignment="bottom")
    slots = []
    while len(slots) < n:
        slots += st.columns(2, vertical_alignment="bottom")
    return slots[:n]


# ---------------------------------------------------------------- Zustand
def _standard(null):
    """Neu angelegte Benutzer: keine Betraege vorbelegt; Regeln ohne Einschraenkung."""
    if null:
        return {"capital": 0.0, "goal": 0.0, "years": 10, "monthly": 0.0, "reserve": 0.0, "capmax": 100.0,
                "fee": 0.0}
    return {"capital": 15000.0, "goal": 26000.0, "years": 10, "monthly": 0.0, "reserve": 15.0, "capmax": 18.0,
            "fee": 1.0}


def _start(null):
    if st.session_state.get(P + "init"):
        return
    for k, v in _standard(null).items():
        st.session_state[P + k] = v
    for k, v in E.STANDARD_RENDITE.items():
        st.session_state[P + "rate_" + k] = v
    st.session_state.update({P + "risk": "wachstum", P + "ansatz": "auto", P + "top": "Top 100",
                             P + "rangmodus": "score", P + "take_now": 0.0, P + "take_monthly": 0.0,
                             P + "take_start": 1, P + "take_end": 0, P + "init": True})


def _zuruecksetzen(null):
    for k in [k for k in st.session_state if str(k).startswith(P)]:
        del st.session_state[k]
    _start(null)


# ---------------------------------------------------------------- Daten
def _lies(h, pfad, default):
    lies = (h or {}).get("gh_read_taeglich")
    try:
        return (lies(pfad, None) if lies else None) or default
    except Exception:
        return default


def _universum(h):
    """Top-500-/Watchlist-Universum - je Sitzung und Tag gemerkt."""
    heute = datetime.date.today().isoformat()
    gemerkt = st.session_state.get(P + "universum")
    if gemerkt and gemerkt[0] == heute:
        return gemerkt[1], gemerkt[2]
    teile = [_lies(h, f"state/planer/katalog_gross_{i}.json", {}) for i in range(4)]
    q = _lies(h, "state/qualitaet.json", {})
    isin = {sym: i for i, sym in ((_lies(h, "state/top50_yahoo.json", {}) or {}).get("isin") or {}).items()
            if sym and isinstance(i, str) and len(i) == 12}
    stand = str((_lies(h, "state/top50.json", {}) or {}).get("stand") or "")[:16].replace("T", " ")
    alle = {}
    for i in range(4):                                     # Index-Listen: Kennung + 3-Monats-Rendite der Aktien
        d = _lies(h, f"state/top50_alle_{i}.json", {})
        f = d.get("felder") or []
        if "s" in f:
            for z in d.get("zeilen") or []:
                alle[z[f.index("s")]] = dict(zip(f, z))
    u = E.universum(teile, (q or {}).get("werte") or {}, isin, stand, alle)
    st.session_state[P + "universum"] = (heute, u, stand)
    return u, stand


def _katalog(h):
    """Universum + eigene CSV-Werte, mit frisch abgerufenen Kursen (ls-tc)."""
    u, stand = _universum(h)
    eigene = st.session_state.get(P + "csv_katalog") or []
    je_id = {a["id"]: dict(a) for a in u}
    for a in eigene:                                       # CSV ersetzt bei gleicher ID
        je_id[a["id"]] = dict(a)
    for wid, (kurs, zeit) in (st.session_state.get(P + "live") or {}).items():
        if wid in je_id and kurs > 0:
            je_id[wid].update(price=kurs, asOf=zeit, source="ls-tc.de aktuell")
    return list(je_id.values()), stand


def _kurse_laden(h, orders):
    """Aktuelle EUR-Kurse (ls-tc) fuer die Kaufplan-Werte: Kurs-ID aus den Top-500-Daten, sonst exakte Suche."""
    hole, suche = (h or {}).get("get_live_kurs"), (h or {}).get("suche_instrument")
    if not hole:
        return 0, ["Kursdienst nicht angebunden"]
    ids = S.top500_ids(_lies(h, "state/top50_ids.json", {}), _lies(h, "state/top50_wikifolios.json", {}))
    live = dict(st.session_state.get(P + "live") or {})
    ok, fehlt = 0, []
    for o in orders:
        iid = next((ids[k.upper()] for k in (o.get("isin"), o.get("wkn"), o.get("id")) if k and k.upper() in ids), None)
        if iid is None and suche and (o.get("isin") or o.get("wkn")):
            import investment_scanner_pro_engine as PRO
            t, art = PRO.treffer_waehlen(o, suche(o.get("isin") or o.get("wkn")) or [])
            iid = t["instrument_id"] if t and art == "exakt" else None
        try:
            akt, vor, _ = hole(iid) if iid else (None, None, None)
        except Exception:
            akt = vor = None
        kurs = akt or vor
        if kurs and kurs > 0:
            live[o["id"]] = (float(kurs), datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
            ok += 1
        else:
            fehlt.append(o["name"])
    st.session_state[P + "live"] = live
    return ok, fehlt


# ---------------------------------------------------------------- Bausteine
def _karte_titel(titel, nr=None):
    st.markdown(f'<div class="pb-karte-t">{f"<span class=is2-nr>{nr}</span>" if nr else ""}{_esc(titel)}</div>',
                unsafe_allow_html=True)


def _tabelle(kopf, zeilen, rechts=(), breit=True):
    """kopf = [(titel, klasse)], zeilen = [[html je Spalte]]; klasse "r" rechtsbuendig, "nm" Namensspalte."""
    th = "".join(f'<th class="{k}">{_esc(t)}</th>' for t, k in kopf)
    tr = "".join("<tr>" + "".join(f'<td class="{k}">{z}</td>' for (_, k), z in zip(kopf, zeile)) + "</tr>"
                 for zeile in zeilen)
    st.markdown(f'<div class="{"is2-wrap" if breit else ""}"><table class="is2"><thead><tr>{th}</tr></thead>'
                f'<tbody>{tr}</tbody></table></div>', unsafe_allow_html=True)


def _kpis(paare):
    st.markdown('<div class="is2-k">' + "".join(
        f'<div class="k"><div class="l">{l}</div><div class="w">{w}</div>' + (f'<div class="s">{u}</div>' if u else "")
        + "</div>" for l, w, u in paare) + "</div>", unsafe_allow_html=True)


def _score_chip(v):
    return (f'<span class="is2-score">{_de(v, 1)}</span>' if v is not None
            else '<span class="is2-score na">n/v</span>')


# ---------------------------------------------------------------- Eingaben
def _eingaben():
    _karte_titel("Kapital & Anlageziel", "01")
    c = _spalten(4)
    c[0].number_input("Neues Anfangskapital €", 0.0, 1e9, step=100.0, format="%.0f", key=P + "capital")
    c[1].number_input("Zielwert Gesamtdepot €", 0.0, 1e10, step=500.0, format="%.0f", key=P + "goal")
    c[2].number_input("Anlagezeit (Jahre)", 1, 50, step=1, key=P + "years")
    c[3].number_input("Sparrate / Monat €", 0.0, 1e7, step=25.0, format="%.0f", key=P + "monthly")
    c = _spalten(4)
    c[0].number_input("Nachkaufreserve %", 0.0, 95.0, step=1.0, format="%.0f", key=P + "reserve")
    c[1].number_input("Max. Wertpapiergewicht %", 1.0, 100.0, step=1.0, format="%.0f", key=P + "capmax")
    c[2].selectbox("Max. Risikostufe (Auto)", list(E.PROFILES), key=P + "risk",
                   format_func=lambda k: E.PROFILES[k]["name"])
    c[3].selectbox("Portfolioansatz", list(ANSATZ), key=P + "ansatz", format_func=ANSATZ.get)
    with st.expander("Weitere Modellannahmen & Erklärungen"):
        c = _spalten(4)
        c[0].number_input("Orderkosten €", 0.0, 100.0, step=0.5, format="%.2f", key=P + "fee")
        for spalte, k, t in zip(c[1:], ("defensiv", "ausgewogen", "wachstum"),
                                ("Defensiv % p. a.", "Ausgewogen % p. a.", "Wachstum % p. a.")):
            spalte.number_input(t, -20.0, 40.0, step=0.5, format="%.1f", key=P + "rate_" + k)
        st.markdown(
            "- **Nachkaufreserve**: Anteil des neuen Kapitals (nach Sofortentnahmen), der nicht investiert wird.\n"
            "- **Max. Wertpapiergewicht**: Obergrenze je Position im gesamten Depot (Neukäufe).\n"
            "- **Max. Risikostufe**: Die automatische Auswahl nimmt höchstens diese Strategie.\n"
            "- **Portfolioansatz**: " + " · ".join(f"{ANSATZ[k]} – {ANSATZ_HINT[k]}" for k in ANSATZ) + ".\n"
            "- **Renditen** sind Szenarioannahmen, keine Prognosen. Steuern, Inflation, laufende Produktkosten und "
            "Kursschwankungen werden nicht simuliert.")


def _anlageklassen(katalog):
    _karte_titel("Anlageklassen & Auswahl", "02")
    vorhanden = [t for t in E.TYPES if any(a["type"] == t for a in katalog)]
    if st.session_state.get(P + "typen") is None:
        st.session_state[P + "typen"] = list(vorhanden)
    st.session_state[P + "typen"] = [t for t in st.session_state[P + "typen"] if t in vorhanden]
    c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom") if not B._smartphone() else (
        st.container(), *st.columns(2, vertical_alignment="bottom"))
    c1.pills("Anlageklassen für neue Käufe", vorhanden, selection_mode="multi", key=P + "typen",
             format_func=lambda t: f"{t} ({sum(1 for a in katalog if a['type'] == t):,})".replace(",", "."))
    c2.selectbox("Scan-Limit je Klasse", list(TOP_N), key=P + "top")
    c3.selectbox("Sortierung", ["score", "rank"], key=P + "rangmodus",
                 format_func={"score": "Investment-Score", "rank": "Quellenrang"}.get)
    st.caption("Anleihen, Gold, Fonds und Geldmarkt sind in den Top-500-Daten nicht enthalten – per Wertpapier-CSV "
               "ergänzbar; fehlende Klassen werden anteilig umverteilt. Werte ohne ausreichende Kennzahlen haben keinen "
               "Score und folgen nach Quellenrang (12-Monats-Rendite).")


def _daten(katalog, stand):
    _karte_titel("Daten & Gesamtdepot", "03")
    n_live = len(st.session_state.get(P + "live") or {})
    st.caption(f"{len(katalog):,} Wertpapiere aus den Top-500-/Watchlist-Daten · Tagesschluss vom {stand or '–'}"
               .replace(",", ".") + (f" · {n_live} aktuelle Kurse von ls-tc.de" if n_live else "")
               + " · unbekannte Preise werden nie geschätzt")
    # Handy: die beiden Upload-Felder untereinander (nebeneinander zu eng)
    c = [st.container(), st.container()] if B._smartphone() else st.columns(2)
    for spalte, art, titel, vorlage, datei in (
            (c[0], "kat", "Wertpapier-CSV importieren", E.CSV_VORLAGE_WERTPAPIERE, "wertpapiere_vorlage.csv"),
            (c[1], "dep", "Depot-CSV importieren", E.CSV_VORLAGE_DEPOT, "depot_vorlage.csv")):
        with spalte:
            f = st.file_uploader(titel, type=["csv"], key=P + "f_" + art)
            if f is not None and st.session_state.get(P + "f_" + art + "_name") != f.name + str(f.size):
                text = f.getvalue().decode("utf-8", "replace")
                liste, fehler = (E.katalog_aus_csv if art == "kat" else E.depot_aus_csv)(text)
                st.session_state[P + ("csv_katalog" if art == "kat" else "depot")] = liste
                st.session_state[P + "f_" + art + "_name"] = f.name + str(f.size)
                st.session_state[P + "meldung"] = (
                    f"{len(liste)} {'Wertpapiere (ungeprüft)' if art == 'kat' else 'Depotpositionen'} übernommen"
                    + (f" · {len(fehler)} Zeilen übersprungen" if fehler else ""))
            st.download_button("CSV-Vorlage", vorlage, datei, "text/csv", key=P + "dl_" + art)
    m = st.session_state.pop(P + "meldung", None)
    if m:
        st.success(m)
    depot = st.session_state.get(P + "depot") or []
    d1, d2 = ((st.container(), st.container()) if B._smartphone()
              else st.columns([4, 1], vertical_alignment="center"))
    if depot:
        d1.caption(f"**Vorhandenes Depot ({len(depot)} Positionen):** " + " · ".join(
            f"{_esc(d['name'])} {_de(d['shares'], 4).rstrip('0').rstrip(',')} Stk." for d in depot[:6])
            + (f" · + {len(depot) - 6} weitere" if len(depot) > 6 else ""))
        d2.button("Depot leeren", key=P + "depot_weg", width="stretch",
                  on_click=lambda: st.session_state.pop(P + "depot", None))
    else:
        d1.caption("**Vorhandenes Depot:** noch keine Positionen importiert.")


def _entnahme():
    _karte_titel("Geld entnehmen", "04")
    c = _spalten(4)
    c[0].number_input("Auszahlung sofort €", 0.0, 1e9, step=100.0, format="%.0f", key=P + "take_now")
    c[1].number_input("Auszahlung je Monat €", 0.0, 1e7, step=50.0, format="%.0f", key=P + "take_monthly")
    c[2].number_input("Ab Monat", 1, 600, step=1, key=P + "take_start")
    c[3].number_input("Bis Monat (0 = Ende)", 0, 600, step=1, key=P + "take_end")
    st.caption("Sofortentnahme zuerst aus neuem Geld, darüber hinaus aus modellierten Verkäufen vorhandener "
               "Wertpapiere. Monatsentnahmen mindern die Endwerte und können das Depot aufbrauchen. Keine echten "
               "Verkäufe, keine Steuer- und Spread-Berechnung.")


# ---------------------------------------------------------------- Ergebnis
def _ergebnis(erg):
    _karte_titel("Ergebnis")
    m = erg["plans"][erg["active"]]
    r = m["neededRate"]
    _kpis((("Depotwert zu Beginn", _eur(m["deposit"]), "nach Sofortentnahme und Gebühren"),
           ("Für Neukäufe", _eur(m["investBudget"]), "nach Abzug der Reserve"),
           ("Nachkaufreserve", _eur(m["reserve"]), "zzgl. Stückzahl-Rest"),
           ("Nötige Modellrendite", "> 300 %" if r is None else _pct(r * 100), "p. a. zum Ziel")))
    inp, p = erg["inp"], erg["active"]
    erreicht = m["projection"] >= inp["goal"]
    text = (f"{E.PROFILES[p]['name']}: {_eur(m['projection'])} in {inp['years']} Jahren bei {_pct(m['rate'] * 100)} "
            f"p. a. · {'Überschuss' if erreicht else 'Lücke'} {_eur(abs(m['projection'] - inp['goal']))}"
            + (" · Auto-Auswahl innerhalb der Risikogrenze" if st.session_state.get(P + "ansatz") == "auto" else ""))
    if inp["goal"] <= 0:
        st.info("Kein Zielwert eingetragen – " + text)
    elif erreicht:
        st.success("◉ Zielwert wird erreicht – " + text)
    else:
        st.warning("⚠ Zielwert wird verfehlt – " + text)


def _strategien(erg):
    _karte_titel("3 alternative Depotstrategien")
    inp, reihe = erg["inp"], list(E.PROFILES)
    spalten = st.columns(3) if not B._smartphone() else [st.container() for _ in reihe]
    for spalte, k in zip(spalten, reihe):
        x = erg["plans"][k]
        g = x["projection"] - inp["goal"]
        ueber = reihe.index(k) > reihe.index(inp["riskCeiling"])
        with spalte:
            st.markdown(
                f'<div class="is2-szen"><div class="c {"sel" if k == erg["active"] else ""} {"off" if ueber else ""}">'
                f'<div class="t">{"✧ Auto-Vorschlag" if k == erg["auto"] else "Szenario"}</div>'
                f'<div class="n">{E.PROFILES[k]["name"]}</div><div class="v">{_eur(x["projection"])}</div>'
                f'<div class="t">Modellrendite {_pct(x["rate"] * 100)} p. a.</div>'
                f'<div class="{"is2-pos" if g >= 0 else "is2-neg"}">{"+" if g >= 0 else "−"} {_eur(abs(g))} '
                f'{"über" if g >= 0 else "unter"} Ziel{" · über Risikolimit" if ueber else ""}</div></div></div>',
                unsafe_allow_html=True)
            st.button("✓ Gewählt" if k == erg["active"] else "Wählen", key=P + "wahl_" + k, width="stretch",
                      type="primary" if k == erg["active"] else "secondary",
                      on_click=lambda k=k: st.session_state.update({P + "ansatz": k}))
    st.caption("Illustrative Renditepfade, nicht garantiert – Endwerte für das gesamte Depot inkl. vorhandener "
               "Positionen, Sparraten, Entnahmen und Liquidität.")


def _kaufplan(h, erg):
    m, inp = erg["plans"][erg["active"]], erg["inp"]
    _karte_titel(f"Kaufplan · {E.PROFILES[erg['active']]['name']}")
    _kpis((("Kaufpositionen", str(len(m["orders"])), ""), ("Käufe", _eur(m["investedNew"]), ""),
           ("Freies Kapital danach", _eur(m["cash"]),
            f"{_pct(m['cash'] / m['deposit'] * 100 if m['deposit'] else 0)} des Gesamtdepots"),
           ("Ordergebühren", _eur(m["fees"], 2), "geschätzt")))
    if m["orders"]:
        _tabelle([("Instrument", "nm"), ("Score", "r"), ("Preis", "r"), ("Stück", "r"), ("Kaufsumme", "r"),
                  ("% Neukapital", "r"), ("% Gesamtdepot", "r")],
                 [[f'<b>{_esc(o["name"])}</b><div class="m">{_esc(o["type"])} · {_esc(o.get("isin") or o["id"])} · '
                   f'Kurs {_esc(o.get("asOf") or "unbekannt")}</div>', _score_chip(o.get("combinedScore")),
                   _eur(o["price"], 2), f'<b>{o["shares"]}</b>', _eur(o["amount"], 2),
                   _pct(o["amount"] / max(inp["capital"], 1) * 100), _pct(o["amount"] / max(m["deposit"], 1) * 100)]
                  for o in m["orders"]])
    else:
        st.info("Keine kaufbaren Positionen im gewählten Universum oder kein freies Kapital.")
    c = _spalten(2)
    if c[0].button("↻ Aktuelle Kurse laden (ls-tc.de)", key=P + "live_btn", width="stretch",
                   disabled=not m["orders"]):
        with st.spinner("Lade aktuelle EUR-Kurse …"):
            st.session_state[P + "meldung_kurse"] = _kurse_laden(h, m["orders"])
        st.rerun()
    c[1].download_button("↓ Kaufplan als CSV", E.kaufplan_csv(erg), "kaufplan.csv", "text/csv", key=P + "dl_kp",
                         width="stretch", disabled=not m["orders"])
    mk = st.session_state.pop(P + "meldung_kurse", None)
    if mk:
        (st.success if not mk[1] else st.warning)(
            f"{mk[0]} aktuelle Kurse geladen" + (f" · ohne Kurs: {', '.join(mk[1][:5])}" if mk[1] else "")
            + " – der Kaufplan ist neu berechnet.")


def _entnahmen(erg):
    wd, raw = erg["wd"], erg["raw"]
    _karte_titel("Entnahmen & notwendige Verkäufe")
    if not raw["takeNow"] and not raw["takeMonthly"]:
        st.caption("Keine Entnahme geplant – Beträge oben unter „04 · Geld entnehmen“.")
        return
    _kpis((("Sofort ausgezahlt", _eur(wd["paid"]), "Plan"), ("Je Monat vorgesehen", _eur(raw["takeMonthly"]), ""),
           ("Ungedeckt", _eur(wd["gap"]), "sofort"), ("Verkaufsgebühren", _eur(wd["fees"], 2), "")))
    if wd["sales"]:
        _tabelle([("Verkaufsvorschlag · sofort", "nm"), ("Kurs", "r"), ("Stück", "r"), ("Brutto", "r"),
                  ("Netto*", "r")],
                 [[_esc(v["name"]), _eur(v["price"], 2), str(v["shares"]), _eur(v["gross"], 2), _eur(v["net"], 2)]
                  for v in wd["sales"]])
        st.caption("*Netto abzüglich Ordergebühr, vor Steuern, Spread und Slippage. Tatsächliche Auszahlung erst nach "
                   "realem Verkauf über den Broker.")
    if raw["takeMonthly"]:
        _tabelle([("Strategie nach Entnahmen", "nm"), ("Ausgezahlt", "r"), ("Nicht gedeckt", "r"),
                  ("Lücke ab Monat", "r"), ("Endwert", "r")],
                 [[E.PROFILES[k]["name"], _eur(m["flow"]["paid"]), _eur(m["flow"]["shortfall"]),
                   str(m["flow"]["firstShortfall"] or "–"), _eur(m["projection"])] for k, m in erg["plans"].items()],
                 breit=False)
    st.download_button("↓ Entnahmeplan als CSV", E.entnahmeplan_csv(erg), "entnahmeplan.csv", "text/csv",
                       key=P + "dl_ep")


def _mix(erg):
    m = erg["plans"][erg["active"]]
    gesamt = m["existingValue"] + m["investedNew"] + m["cash"]
    _karte_titel("Gesamtdepot nach Kauf · Soll-Ist-Mix")
    teile = [(t, m["actualCat"][t]) for t in E.TYPES if m["actualCat"][t] > 0.005] + [("Liquidität", m["cash"])]
    st.markdown('<div class="is2-mix">' + "".join(
        f'<div title="{t}" style="width:{v / gesamt * 100 if gesamt else 0}%;background:{E.COLORS[t]}"></div>'
        for t, v in teile) + "</div>" + "".join(
        f'<span class="is2-leg"><span class="is2-dot" style="background:{E.COLORS[t]}"></span>{t} '
        f'{_pct(v / gesamt * 100 if gesamt else 0)}</span>' for t, v in teile)
        + f'<span class="is2-leg" style="color:#9AA0A6">· Depotwert nach Orders {_eur(gesamt)}</span>',
        unsafe_allow_html=True)
    _tabelle([("Anlageklasse", "nm"), ("Soll", "r"), ("Ist", "r"), ("", "")],
             [[t, _pct(m["ratios"][t] * 100), _pct(m["actualCat"][t] / max(gesamt, 1) * 100),
               f'<div class="is2-bar"><div style="width:{min(100, m["actualCat"][t] / max(gesamt, 1) * 100)}%;'
               f'background:{E.COLORS[t]}"></div></div>']
              for t in E.TYPES if m["ratios"][t] > 0 or m["actualCat"][t] > 0], breit=False)


def _scores(erg, typen):
    _karte_titel("Investment-Score · transparente Auswahl")
    verf = erg["available"]
    geeignet = [a for a in verf if a["type"] in typen]
    st.caption(f"{sum(1 for a in verf if a.get('combinedScore') is not None)} von {len(verf)} Werten bewertbar · "
               + " · ".join(f"{k} {v} %" for k, v in E.SCORE_WEIGHTS.items()))
    gezeigt = geeignet[:12]
    if not gezeigt:
        st.info("Keine Werte für die gewählten Anlageklassen.")
        return
    _tabelle([("#", "nr m"), ("Wertpapier", "nm"), ("Score", "r"), ("Daten", "r")],
             [[str(a["scannerRank"]), f'<b>{_esc(a["name"])}</b><div class="m">{_esc(a["type"])} · '
               f'{_esc(a.get("isin") or a["id"])}</div>', _score_chip(a["combinedScore"]), _pct(a["score"]["coverage"])]
              for a in gezeigt], breit=False)
    wahl = st.selectbox("Teilbewertungen", range(len(gezeigt)), key=P + "score_fokus",
                        format_func=lambda i: f"#{gezeigt[i]['scannerRank']} {gezeigt[i]['name']}")
    a = gezeigt[wahl if wahl is not None and wahl < len(gezeigt) else 0]
    _tabelle([("Faktor", "nm"), ("Wert", "r"), ("", "")],
             [[f'{k} <span class="m">({E.SCORE_WEIGHTS[k]} %)</span>', "keine Daten" if v is None else _de(v, 0),
               f'<div class="is2-bar"><div style="width:{0 if v is None else max(0.0, min(100.0, v))}%;'
               f'background:#52d9b3"></div></div>'] for k, v in a["score"]["details"].items()], breit=False)
    st.caption("Modellheuristik, keine Renditeprognose oder Anlageberatung. Fehlende Faktoren werden nicht geschätzt, "
               "sie senken die Datenabdeckung; Score erst ab 60 % Abdeckung und vorhandener Risikokennzahl.")


def _hinweise():
    with st.expander("ℹ️ Nachvollziehbarkeit · Auswahlverfahren & Hinweise"):
        st.markdown(
            "- **Universum:** Top-500-/Watchlist-Daten der App (Aktien, ETFs, wikifolios) mit Tagesschlusskurs in EUR; "
            "Hebelprodukte und Datenfehler ausgefiltert; eigene Werte per Wertpapier-CSV. Quellenrang = Rang nach "
            "12-Monats-Rendite.\n"
            "- **Score:** Momentum (12- und 3-Monats-Rendite), Risiko (Schwankung, maximaler Rückgang), Qualität und KGV "
            "(Aktien mit Daten des Qualitäts-Agenten). Kosten (TER), Handelsvolumen und Spread liegen nicht vor – ETFs "
            "und wikifolios haben daher meist keinen Score und werden nach Quellenrang berücksichtigt.\n"
            "- **Kaufplan:** je Anlageklasse die bis zu vier besten Werte, Budget nach Soll-Anteil der Strategie "
            "abzüglich vorhandenem Bestand, ganze Stücke, Ordergebühr je Kauf, Höchstgewicht je Wertpapier.\n"
            "- **Strategien:** feste Renditeannahmen (Szenario) mit Sparrate und Entnahmen; Auto wählt die "
            "vorsichtigste Strategie innerhalb der Risikogrenze, die das Ziel erreicht.\n\n"
            "Rechen- und Vergleichswerkzeug, keine Anlageberatung oder automatische Order. Kurse sind nicht zwingend "
            "Realtime. Wikifolio-Produkte sind Zertifikate mit Emittentenrisiko. Zielerreichung und Renditeannahmen "
            "sind nicht garantiert.")


# ---------------------------------------------------------------- Seite
def seite(h):
    with st.container(key="is2_seite"):
        _seite(h)


def _seite(h):
    null = bool((h or {}).get("null"))
    _start(null)
    st.markdown(B.CSS, unsafe_allow_html=True)
    st.markdown(CSS, unsafe_allow_html=True)
    katalog, stand = _katalog(h)
    live = bool(st.session_state.get(P + "live"))
    chip = ("● aktuelle Kurse teilweise geladen" if live else
            "● Top-500-Daten · Tagesschluss" if katalog else "● keine Kurse geladen")
    st.markdown('<div class="pb-kopf"><div class="pb-titel">Investment Scanner <span>2.0</span></div>'
                '<div class="pb-unter">Anlageziel · echte EUR-Kurse · Kauf-, Reserve- und Entnahmeplan</div></div>',
                unsafe_allow_html=True)
    k1, k2 = st.columns([3, 2] if B._smartphone() else [4, 1], vertical_alignment="center")
    k1.markdown(f'<span class="is2-chip {"" if katalog else "warn"}">{chip.upper()}</span>', unsafe_allow_html=True)
    k2.button("↺ Zurücksetzen", key=P + "reset", width="stretch", on_click=_zuruecksetzen, args=(null,))
    for teil in (_eingaben, lambda: _anlageklassen(katalog), lambda: _daten(katalog, stand), _entnahme):
        with st.container(border=True):
            teil()
    s = st.session_state
    typen = set(s.get(P + "typen") or [])
    if not katalog:
        st.warning("Noch keine Kurse vorhanden – die Top-500-Daten sind gerade nicht lesbar. Bitte später erneut "
                   "öffnen oder eine Wertpapier-CSV importieren. Es werden keine Kurse erfunden.")
        return
    if not typen:
        st.info("Bitte mindestens eine Anlageklasse wählen.")
        return
    roh = E.eingaben(capital=s[P + "capital"], goal=s[P + "goal"], years=s[P + "years"], monthly=s[P + "monthly"],
                     reservePct=s[P + "reserve"], maxLinePct=s[P + "capmax"], fee=s[P + "fee"],
                     riskCeiling=s.get(P + "risk") or "wachstum", takeNow=s[P + "take_now"],
                     takeMonthly=s[P + "take_monthly"], takeStart=s[P + "take_start"], takeEnd=s[P + "take_end"])
    erg = E.berechnen(roh, katalog, s.get(P + "depot") or [], typen, s.get(P + "ansatz") or "auto",
                      s.get(P + "rangmodus") or "score", TOP_N.get(s.get(P + "top") or "Top 100", 100),
                      {k: s[P + "rate_" + k] for k in E.PROFILES})
    for teil in (lambda: _ergebnis(erg), lambda: _strategien(erg), lambda: _kaufplan(h, erg),
                 lambda: _entnahmen(erg), lambda: _mix(erg), lambda: _scores(erg, typen)):
        with st.container(border=True):
            teil()
    _hinweise()
