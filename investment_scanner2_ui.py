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
.is2-kopf { display:flex; justify-content:space-between; align-items:flex-end; gap:12px; flex-wrap:wrap; margin:4px 0 6px; }
.is2-ueber { color:#9AA0A6; font-size:.72rem; letter-spacing:1.4px; text-transform:uppercase; }
.is2-titel { font-size:1.6rem; font-weight:800; }
.is2-chip { display:inline-block; padding:4px 10px; border-radius:999px; font-size:.72rem; font-weight:700;
  letter-spacing:.6px; background:#193c38; color:#9af1d4; }
.is2-chip.warn { background:#423523; color:#f4c67b; }
.is2-nr { color:#52d9b3; font-weight:800; font-size:.8rem; letter-spacing:1px; }
.is2-k { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin:8px 0; }
.is2-k .k { border:1px solid #262B33; border-radius:12px; padding:10px 12px; background:#0F1115; }
.is2-k .l { color:#9AA0A6; font-size:.7rem; text-transform:uppercase; letter-spacing:.4px; }
.is2-k .w { font-size:1.2rem; font-weight:800; margin-top:2px; }
.is2-k .s { color:#9AA0A6; font-size:.74rem; }
.is2-szen { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin:6px 0; }
.is2-szen .c { border:1px solid #262B33; border-radius:12px; padding:12px; background:#0F1115; }
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
table.is2 td:first-child { min-width:150px; }
.is2-score { display:inline-block; min-width:42px; text-align:center; padding:2px 6px; border-radius:8px;
  background:#193c38; color:#9af1d4; font-weight:700; }
.is2-score.na { background:#2a2f37; color:#9AA0A6; }
.is2-mix { display:flex; height:16px; border-radius:8px; overflow:hidden; margin:6px 0; }
.is2-bar { height:8px; border-radius:4px; background:#1A1E24; overflow:hidden; }
.is2-bar > div { height:100%; }
.is2-leg { display:inline-flex; align-items:center; gap:5px; margin:2px 10px 2px 0; font-size:.8rem; }
.is2-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
@media (max-width: 640px) { .is2-k, .is2-szen { grid-template-columns:repeat(2, minmax(0,1fr)); } }
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
    if not B._smartphone():
        return st.columns(n)
    slots = []
    while len(slots) < n:
        slots += st.columns(2)
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


# ---------------------------------------------------------------- Eingaben
def _eingaben():
    st.markdown('<span class="is2-nr">01</span> **Kapital & Anlageziel**', unsafe_allow_html=True)
    c = _spalten(4)
    c[0].number_input("Neues Anfangskapital €", 0.0, 1e9, step=100.0, format="%.0f", key=P + "capital")
    c[1].number_input("Zielwert des gesamten Depots €", 0.0, 1e10, step=500.0, format="%.0f", key=P + "goal")
    c[2].number_input("Anlagezeit (Jahre)", 1, 50, step=1, key=P + "years")
    c[3].number_input("Sparrate / Monat €", 0.0, 1e7, step=25.0, format="%.0f", key=P + "monthly")
    c = _spalten(2)
    c[0].number_input("Nachkaufreserve %", 0.0, 95.0, step=1.0, format="%.0f", key=P + "reserve",
                      help="Vom verbleibenden neuen Kapital nach sofortigen Entnahmen.")
    c[1].number_input("Max. Wertpapiergewicht %", 1.0, 100.0, step=1.0, format="%.0f", key=P + "capmax",
                      help="Obergrenze je Position im gesamten Depot (Neukäufe).")
    st.caption("Nachkaufreserve: vom verbleibenden neuen Kapital nach sofortigen Entnahmen · Max. Wertpapiergewicht: "
               "Obergrenze je Position im gesamten Depot (Neukäufe).")
    st.segmented_control("Maximale Risikostufe für Auto-Auswahl", list(E.PROFILES),
                         format_func=lambda k: E.PROFILES[k]["name"], key=P + "risk")
    st.segmented_control("Portfolioansatz", list(ANSATZ), format_func=ANSATZ.get, key=P + "ansatz")
    st.caption(" · ".join(f"**{ANSATZ[k]}**: {ANSATZ_HINT[k]}" for k in ANSATZ))
    with st.expander("Weitere Modellannahmen"):
        c = _spalten(4)
        c[0].number_input("Orderkosten €", 0.0, 100.0, step=0.5, format="%.2f", key=P + "fee")
        for spalte, k, t in zip(c[1:], ("defensiv", "ausgewogen", "wachstum"),
                                ("Defensiv / Jahr %", "Ausgew. / Jahr %", "Wachstum / Jahr %")):
            spalte.number_input(t, -20.0, 40.0, step=0.5, format="%.1f", key=P + "rate_" + k)
        st.caption("Die Renditen sind Szenarioannahmen, keine Prognosen. Steuern, Inflation, laufende Produktkosten "
                   "und Kursschwankungen werden nicht simuliert.")


def _anlageklassen(katalog):
    st.markdown('<span class="is2-nr">02</span> **Anlageklassen**', unsafe_allow_html=True)
    st.caption("Wähle, welche Instrumenttypen der Scanner für neue Käufe berücksichtigen darf.")
    vorhanden = [t for t in E.TYPES if any(a["type"] == t for a in katalog)]
    if st.session_state.get(P + "typen") is None:
        st.session_state[P + "typen"] = list(vorhanden)
    st.session_state[P + "typen"] = [t for t in st.session_state[P + "typen"] if t in vorhanden]
    st.pills("Anlageklassen", vorhanden, selection_mode="multi", key=P + "typen", label_visibility="collapsed",
             format_func=lambda t: f"{t} ({sum(1 for a in katalog if a['type'] == t):,})".replace(",", "."))
    if len(vorhanden) < len(E.TYPES):
        st.caption("Anleihen, Gold, Fonds und Geldmarkt sind in den Top-500-Daten nicht enthalten – per Wertpapier-CSV "
                   "(Abschnitt 03) ergänzbar. Fehlende Klassen werden in den Strategien anteilig umverteilt.")
    c = _spalten(2)
    c[0].segmented_control("Scan-Limit je Anlageklasse (nach Investment-Score)", list(TOP_N), key=P + "top")
    c[1].selectbox("Sortierung der Top-Werte", ["score", "rank"], key=P + "rangmodus",
                   format_func={"score": "Kombinierter Investment-Score",
                                "rank": "Quellenrang (12-Monats-Rendite)"}.get)
    st.caption("Ohne ausreichende Kennzahlen kein Score; solche Werte erscheinen bei Score-Sortierung am Ende nach "
               "Quellenrang.")


def _daten(h, katalog, stand):
    st.markdown('<span class="is2-nr">03</span> **Daten & Gesamtdepot**', unsafe_allow_html=True)
    n_live = len(st.session_state.get(P + "live") or {})
    st.caption(f"Universum: {len(katalog):,} Wertpapiere aus den Top-500-/Watchlist-Daten (Kurse Tagesschluss, Stand "
               f"{stand or 'unbekannt'}){f' · {n_live} aktuelle Kurse von ls-tc.de' if n_live else ''}. Kennzahlen: "
               "12-Monats-Rendite, Schwankung und Drawdown für alle Werte; 3-Monats-Rendite für Aktien; Qualitäts-Score und "
               "KGV für Aktien aus dem Qualitäts-Agenten. Unbekannte Preise werden nie geschätzt.".replace(",", "."))
    c = _spalten(2)
    with c[0]:
        f = st.file_uploader("Wertpapier-CSV importieren", type=["csv"], key=P + "f_kat")
        if f is not None and st.session_state.get(P + "f_kat_name") != f.name + str(f.size):
            liste, fehler = E.katalog_aus_csv(f.getvalue().decode("utf-8", "replace"))
            st.session_state[P + "csv_katalog"] = liste
            st.session_state[P + "f_kat_name"] = f.name + str(f.size)
            st.session_state[P + "meldung"] = (f"{len(liste)} Wertpapiere aus CSV übernommen (ungeprüft)"
                                               + (f" · {len(fehler)} Zeilen übersprungen" if fehler else ""))
        st.download_button("CSV-Vorlage", E.CSV_VORLAGE_WERTPAPIERE, "wertpapiere_vorlage.csv", "text/csv",
                           key=P + "dl_v1")
    with c[1]:
        f = st.file_uploader("Depot-CSV importieren", type=["csv"], key=P + "f_dep")
        if f is not None and st.session_state.get(P + "f_dep_name") != f.name + str(f.size):
            liste, fehler = E.depot_aus_csv(f.getvalue().decode("utf-8", "replace"))
            st.session_state[P + "depot"] = liste
            st.session_state[P + "f_dep_name"] = f.name + str(f.size)
            st.session_state[P + "meldung"] = (f"{len(liste)} Depotpositionen übernommen"
                                               + (f" · {len(fehler)} Zeilen übersprungen" if fehler else ""))
        st.download_button("Depot-Vorlage", E.CSV_VORLAGE_DEPOT, "depot_vorlage.csv", "text/csv", key=P + "dl_v2")
    m = st.session_state.pop(P + "meldung", None)
    if m:
        st.success(m)
    depot = st.session_state.get(P + "depot") or []
    st.markdown(f"**Vorhandenes Depot ({len(depot)} Positionen)**")
    if depot:
        st.caption(" · ".join(f"{_esc(d['name'])} {_de(d['shares'], 4).rstrip('0').rstrip(',')} Stk."
                              for d in depot[:6]) + (f" · + {len(depot) - 6} weitere" if len(depot) > 6 else ""))
        st.button("Depot leeren", key=P + "depot_weg", on_click=lambda: st.session_state.pop(P + "depot", None))
    else:
        st.caption("Noch keine Positionen importiert.")


def _entnahme():
    st.markdown('<span class="is2-nr">04</span> **Geld entnehmen**', unsafe_allow_html=True)
    st.caption("Sofortige Auszahlungen und regelmäßige Entnahmen fließen in die Depot- und Zielrechnung ein. Es werden "
               "keine echten Verkäufe ausgeführt.")
    c = _spalten(4)
    c[0].number_input("Einmalige Auszahlung · sofort €", 0.0, 1e9, step=100.0, format="%.0f", key=P + "take_now")
    c[1].number_input("Regelmäßige Auszahlung pro Monat €", 0.0, 1e7, step=50.0, format="%.0f", key=P + "take_monthly")
    c[2].number_input("Ab Monat", 1, 600, step=1, key=P + "take_start")
    c[3].number_input("Bis Monat (0 = Ende)", 0, 600, step=1, key=P + "take_end")
    st.caption("Sofortentnahme zuerst aus neuem Geld, darüber hinaus aus modellierten Verkäufen vorhandener "
               "Wertpapiere. Regelmäßige Entnahmen mindern die Modell-Endwerte und können das Depot aufbrauchen. "
               "Keine Steuer- und Verkaufsspread-Berechnung.")


# ---------------------------------------------------------------- Ergebnis
def _kennzahlen(erg):
    m = erg["plans"][erg["active"]]
    r = m["neededRate"]
    st.markdown('<div class="is2-k">' + "".join(
        f'<div class="k"><div class="l">{l}</div><div class="w">{w}</div><div class="s">{s}</div></div>' for l, w, s in (
            ("Depotwert zu Beginn", _eur(m["deposit"]), "Nach sofortiger Entnahme und Gebühren"),
            ("Für Neukäufe vorgesehen", _eur(m["investBudget"]), "Nach Abzug der Reserve"),
            ("Nachkaufreserve", _eur(m["reserve"]), "Zusätzlich ggf. Stückzahl-Rest"),
            ("Erforderliche Modellrendite", "> 300 %" if r is None else _pct(r * 100), "p. a. zum Ziel (geschätzt)")))
        + "</div>", unsafe_allow_html=True)
    inp, p = erg["inp"], erg["active"]
    erreicht = m["projection"] >= inp["goal"]
    text = (f"{E.PROFILES[p]['name']}: {_eur(m['projection'])} in {inp['years']} Jahren bei angenommener Rendite von "
            f"{_pct(m['rate'] * 100)} p. a. · {'rechnerischer Überschuss' if erreicht else 'rechnerische Lücke'} "
            f"{_eur(abs(m['projection'] - inp['goal']))}."
            + (" Auto-Auswahl bleibt innerhalb der Risikogrenze." if st.session_state.get(P + "ansatz") == "auto" else ""))
    if inp["goal"] <= 0:
        st.info("Kein Zielwert eingetragen – " + text)
    elif erreicht:
        st.success("◉ Zielwert wird im ausgewählten Modell erreicht – " + text)
    else:
        st.warning("⚠ Zielwert wird im ausgewählten Modell verfehlt – " + text)


def _strategien(erg):
    st.markdown("#### Anlagevermögen im Vergleich · 3 alternative Depotstrategien")
    st.caption("Illustrative Renditepfade, nicht garantiert. Die Endwerte gelten für das gesamte Depot inkl. vorhandener "
               "Positionen, zusätzlicher Sparraten und verbleibender Liquidität. Keine Kursprognose.")
    inp, reihe = erg["inp"], list(E.PROFILES)
    karten = []
    for k in reihe:
        x = erg["plans"][k]
        g = x["projection"] - inp["goal"]
        ueber = reihe.index(k) > reihe.index(inp["riskCeiling"])
        karten.append(
            f'<div class="c {"sel" if k == erg["active"] else ""} {"off" if ueber else ""}">'
            f'<div class="t">{"✧ Auto-Vorschlag" if k == erg["auto"] else "Szenario"}</div>'
            f'<div class="n">{E.PROFILES[k]["name"]}</div><div class="v">{_eur(x["projection"])}</div>'
            f'<div class="t">Modellrendite {_pct(x["rate"] * 100)} p. a.</div>'
            f'<div class="{"is2-pos" if g >= 0 else "is2-neg"}">{"+" if g >= 0 else "−"} {_eur(abs(g))} '
            f'{"über" if g >= 0 else "unter"} Ziel{" · über Risikolimit" if ueber else ""}</div></div>')
    st.markdown('<div class="is2-szen">' + "".join(karten) + "</div>", unsafe_allow_html=True)
    c = _spalten(3)
    for spalte, k in zip(c, reihe):
        spalte.button(f"{E.PROFILES[k]['name']} wählen", key=P + "wahl_" + k, width="stretch",
                      type="primary" if k == erg["active"] else "secondary",
                      on_click=lambda k=k: st.session_state.update({P + "ansatz": k}))


def _scores(erg, typen):
    st.markdown("#### Transparente Wertpapier-Auswahl · Kombinierter Investment-Score / 100")
    st.caption(" · ".join(f"{k} {v} %" for k, v in E.SCORE_WEIGHTS.items()))
    verf = erg["available"]
    bewertbar = [a for a in verf if a.get("combinedScore") is not None]
    geeignet = [a for a in verf if a["type"] in typen]
    st.caption(f"{len(bewertbar)} von {len(verf)} Werten bewertbar · {len(geeignet)} in aktivierten Anlageklassen · "
               f"Rangmodus: {'kombinierter Score' if st.session_state.get(P + 'rangmodus') == 'score' else 'Quellenrang'}")
    gezeigt = geeignet[:12]
    if not gezeigt:
        st.info("Keine Werte für die gewählten Anlageklassen.")
        return
    zeilen = "".join(
        f'<tr><td class="m">{a["scannerRank"]}</td><td><b>{_esc(a["name"])}</b><div class="m">{_esc(a["type"])} · '
        f'{_esc(a.get("isin") or a["id"])}</div></td><td class="r"><span class="is2-score {"" if a["combinedScore"] is not None else "na"}">'
        f'{_de(a["combinedScore"], 1) if a["combinedScore"] is not None else "n/v"}</span></td>'
        f'<td class="r">{_pct(a["score"]["coverage"])}</td></tr>' for a in gezeigt)
    st.markdown(f'<div class="is2-wrap"><table class="is2"><thead><tr><th>#</th><th>Wertpapier</th><th class="r">Score</th>'
                f'<th class="r">Daten</th></tr></thead><tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    wahl = st.selectbox("Teilbewertungen ansehen", range(len(gezeigt)), key=P + "score_fokus",
                        format_func=lambda i: f"#{gezeigt[i]['scannerRank']} {gezeigt[i]['name']}")
    a = gezeigt[wahl if wahl is not None and wahl < len(gezeigt) else 0]
    reihen = []
    for k, v in a["score"]["details"].items():
        breite = 0 if v is None else max(0.0, min(100.0, v))
        reihen.append(f'<tr><td>{k} <span class="m">({E.SCORE_WEIGHTS[k]} %)</span></td><td style="width:50%">'
                      f'<div class="is2-bar"><div style="width:{breite}%;background:#52d9b3"></div></div></td>'
                      f'<td class="r">{"keine Daten" if v is None else _de(v, 0)}</td></tr>')
    st.markdown(f'<table class="is2"><tbody>{"".join(reihen)}</tbody></table>', unsafe_allow_html=True)
    st.caption("Modellheuristik, keine Renditeprognose, Anlageberatung oder Qualitätszertifizierung. Fehlende Faktoren "
               "werden nicht als null oder neutral geschätzt, sie senken die Datenabdeckung; erst ab 60 % Abdeckung der "
               "Marktfaktoren und vorhandener Risikokennzahl gibt es einen Score.")


def _kaufplan(h, erg):
    m, inp = erg["plans"][erg["active"]], erg["inp"]
    st.markdown(f"#### Modellbasierte Ordervorschläge · Kaufplan {E.PROFILES[erg['active']]['name']}")
    st.caption(f"{len(m['orders'])} Kaufpositionen · Käufe {_eur(m['investedNew'])} · freies Kapital danach "
               f"{_eur(m['cash'])} ({_pct(m['cash'] / m['deposit'] * 100 if m['deposit'] else 0)} des Gesamtdepots) · "
               f"geschätzte Ordergebühren {_eur(m['fees'], 2)}")
    if m["orders"]:
        zeilen = "".join(
            f'<tr><td><b>{_esc(o["name"])}</b><div class="m">Scanner #{o["scannerRank"]} · {_esc(o.get("isin") or o["id"])}'
            f' · Kursstand {_esc(o.get("asOf") or "unbekannt")} · {_esc(o["type"])}</div></td>'
            f'<td class="r"><span class="is2-score {"" if o.get("combinedScore") is not None else "na"}">'
            f'{_de(o["combinedScore"], 1) if o.get("combinedScore") is not None else "n/v"}</span></td>'
            f'<td class="r">{_eur(o["price"], 2)}</td><td class="r"><b>{o["shares"]}</b></td>'
            f'<td class="r">{_eur(o["amount"], 2)}</td><td class="r">{_pct(o["amount"] / max(inp["capital"], 1) * 100)}</td>'
            f'<td class="r">{_pct(o["amount"] / max(m["deposit"], 1) * 100)}</td></tr>' for o in m["orders"])
        st.markdown('<div class="is2-wrap"><table class="is2"><thead><tr><th>Instrument</th><th class="r">Score</th>'
                    '<th class="r">Preis</th><th class="r">Stück</th><th class="r">Kaufsumme</th>'
                    '<th class="r">% Neukapital</th><th class="r">% Gesamtdepot</th></tr></thead>'
                    f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    else:
        st.info("Keine kaufbaren Positionen im gewählten Universum oder kein freies Kapital.")
    c = _spalten(2)
    if c[0].button("↻ Aktuelle Kurse für den Kaufplan laden (ls-tc.de)", key=P + "live_btn", width="stretch",
                   disabled=not m["orders"]):
        with st.spinner("Lade aktuelle EUR-Kurse …"):
            ok, fehlt = _kurse_laden(h, m["orders"])
        st.session_state[P + "meldung_kurse"] = (ok, fehlt)
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
    st.markdown("#### Auszahlungs- und Liquiditätsplan · Entnahmen & notwendige Verkäufe")
    if not raw["takeNow"] and not raw["takeMonthly"]:
        st.caption("Keine Entnahme geplant.")
    st.markdown('<div class="is2-k">' + "".join(
        f'<div class="k"><div class="l">{l}</div><div class="w">{w}</div></div>' for l, w in (
            ("Sofort ausgezahlt (Plan)", _eur(wd["paid"])), ("Monatlich vorgesehen", _eur(raw["takeMonthly"])),
            ("Ungedeckte Auszahlung", _eur(wd["gap"])), ("Verkaufsgebühren", _eur(wd["fees"], 2))))
        + "</div>", unsafe_allow_html=True)
    if wd["sales"]:
        zeilen = "".join(f'<tr><td>{_esc(v["name"])}</td><td class="r">{_eur(v["price"], 2)}</td>'
                         f'<td class="r">{v["shares"]}</td><td class="r">{_eur(v["gross"], 2)}</td>'
                         f'<td class="r">{_eur(v["net"], 2)}</td></tr>' for v in wd["sales"])
        st.markdown('<div class="is2-wrap"><table class="is2"><thead><tr><th>Verkaufsvorschlag · sofort</th>'
                    '<th class="r">Kurs</th><th class="r">Stück</th><th class="r">Brutto</th><th class="r">Netto*</th>'
                    f'</tr></thead><tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    else:
        st.caption("Keine Verkäufe benötigt.")
    st.caption("*Netto abzüglich angenommener Ordergebühr, vor Steuern, Spread und Slippage. Tatsächliche Auszahlung erst "
               "nach realem Verkauf über den Broker. Zukünftige Verkaufsmengen sind wegen unsicherer Kurse nicht planbar.")
    if raw["takeMonthly"]:
        zeilen = "".join(
            f'<tr><td>{E.PROFILES[k]["name"]}</td><td class="r">{_eur(m["flow"]["paid"])}</td>'
            f'<td class="r">{_eur(m["flow"]["shortfall"])}</td>'
            f'<td class="r">{m["flow"]["firstShortfall"] or "–"}</td><td class="r">{_eur(m["projection"])}</td></tr>'
            for k, m in erg["plans"].items())
        st.markdown('<div class="is2-wrap"><table class="is2"><thead><tr><th>Strategievergleich nach Entnahmen</th>'
                    '<th class="r">Ausgezahlt</th><th class="r">Nicht gedeckt</th><th class="r">Lücke ab Monat</th>'
                    f'<th class="r">Endwert</th></tr></thead><tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    st.download_button("↓ Entnahmeplan als CSV", E.entnahmeplan_csv(erg), "entnahmeplan.csv", "text/csv",
                       key=P + "dl_ep", disabled=not (raw["takeNow"] or raw["takeMonthly"]))


def _mix(erg):
    m = erg["plans"][erg["active"]]
    st.markdown("#### Gesamtdepot nach Kauf · Gewichtung & Liquidität")
    gesamt = m["existingValue"] + m["investedNew"] + m["cash"]
    teile = [(t, m["actualCat"][t]) for t in E.TYPES if m["actualCat"][t] > 0.005] + [("Liquidität", m["cash"])]
    st.caption(f"Depotwert nach Orders: {_eur(gesamt)}")
    st.markdown('<div class="is2-mix">' + "".join(
        f'<div title="{t}" style="width:{v / gesamt * 100 if gesamt else 0}%;background:{E.COLORS[t]}"></div>'
        for t, v in teile) + "</div>" + "".join(
        f'<span class="is2-leg"><span class="is2-dot" style="background:{E.COLORS[t]}"></span>{t} '
        f'{_pct(v / gesamt * 100 if gesamt else 0)}</span>' for t, v in teile), unsafe_allow_html=True)
    reihen = "".join(
        f'<tr><td>{t}</td><td class="r">{_pct(m["ratios"][t] * 100)}</td><td style="width:45%"><div class="is2-bar">'
        f'<div style="width:{min(100, m["actualCat"][t] / max(gesamt, 1) * 100)}%;background:{E.COLORS[t]}"></div></div>'
        f'</td><td class="r">{_pct(m["actualCat"][t] / max(gesamt, 1) * 100)}</td></tr>'
        for t in E.TYPES if m["ratios"][t] > 0 or m["actualCat"][t] > 0)
    st.markdown('<table class="is2"><thead><tr><th>Soll-Ist-Mix</th><th class="r">Soll (Strategie)</th><th></th>'
                f'<th class="r">Ist (Gesamtdepot)</th></tr></thead><tbody>{reihen}</tbody></table>', unsafe_allow_html=True)


def _hinweise():
    with st.expander("Nachvollziehbarkeit · Auswahlverfahren & Hinweise"):
        st.markdown(
            "- **Universum:** Top-500-/Watchlist-Daten der App (Aktien, ETFs, wikifolios) mit Tagesschlusskurs in EUR; "
            "eigene Werte per Wertpapier-CSV. Quellenrang = Rang nach 12-Monats-Rendite.\n"
            "- **Score:** Momentum (12-Monats-Rendite), Risiko (Schwankung, maximaler Rückgang), Qualität und KGV "
            "(nur Aktien mit Daten des Qualitäts-Agenten). Kosten (TER), Handelsvolumen und Spread liegen in den Daten "
            "nicht vor – sie senken die Datenabdeckung, ETFs und wikifolios haben daher meist keinen Score und werden "
            "nach Quellenrang berücksichtigt.\n"
            "- **Kaufplan:** je Anlageklasse die bis zu vier besten Werte, Budget nach Soll-Anteil der Strategie abzüglich "
            "vorhandenem Bestand, ganze Stücke, Ordergebühr je Kauf, Höchstgewicht je Wertpapier im Gesamtdepot.\n"
            "- **Strategien:** feste Renditeannahmen (Szenario), monatliche Sparrate und Entnahmen; Auto wählt die "
            "vorsichtigste Strategie innerhalb der Risikogrenze, die das Ziel erreicht.\n\n"
            "Wichtig: Rechen- und Vergleichswerkzeug, keine individuelle Anlageberatung oder automatische Order. Kurse "
            "sind nicht zwingend Realtime. Wikifolio-Produkte sind Zertifikate mit Emittentenrisiko, nicht ETFs. "
            "Finanzprodukte können im Wert fallen; Zielerreichung und Renditeannahmen sind nicht garantiert.")


# ---------------------------------------------------------------- Seite
def seite(h):
    null = bool((h or {}).get("null"))
    _start(null)
    st.markdown(B.CSS, unsafe_allow_html=True)
    st.markdown(CSS, unsafe_allow_html=True)
    katalog, stand = _katalog(h)
    live = bool(st.session_state.get(P + "live"))
    chip = ("● AKTUELLE KURSE TEILWEISE GELADEN" if live else
            "● TOP-500-DATEN (TAGESSCHLUSS)" if katalog else "● KEINE KURSE GELADEN")
    k1, k2 = st.columns([4, 1], vertical_alignment="bottom")
    k1.markdown(f'<div class="is2-kopf"><div><div class="is2-ueber">Portfolio Intelligenz / Planung</div>'
                f'<div class="is2-titel">Investment Scanner 2.0</div></div>'
                f'<span class="is2-chip {"" if katalog else "warn"}">{chip}</span></div>', unsafe_allow_html=True)
    k2.button("Zurücksetzen", key=P + "reset", width="stretch", on_click=_zuruecksetzen, args=(null,))
    st.caption("Anlageziel definieren, echte EUR-Börsenkurse nutzen, vorhandenes Depot berücksichtigen und Kauf-, "
               "Reserve- sowie Entnahmepläne vergleichen. Keine Orderausführung oder echte Auszahlung.")
    with st.container(border=True):
        _eingaben()
    with st.container(border=True):
        _anlageklassen(katalog)
    with st.container(border=True):
        _daten(h, katalog, stand)
    with st.container(border=True):
        _entnahme()
    s = st.session_state
    typen = set(s.get(P + "typen") or [])
    roh = E.eingaben(capital=s[P + "capital"], goal=s[P + "goal"], years=s[P + "years"], monthly=s[P + "monthly"],
                     reservePct=s[P + "reserve"], maxLinePct=s[P + "capmax"], fee=s[P + "fee"],
                     riskCeiling=s.get(P + "risk") or "wachstum", takeNow=s[P + "take_now"],
                     takeMonthly=s[P + "take_monthly"], takeStart=s[P + "take_start"], takeEnd=s[P + "take_end"])
    if not katalog:
        st.warning("Noch keine Kurse vorhanden – die Top-500-Daten sind gerade nicht lesbar. Bitte später erneut "
                   "öffnen oder eine Wertpapier-CSV importieren. Es werden keine Kurse erfunden.")
        return
    if not typen:
        st.info("Bitte mindestens eine Anlageklasse wählen.")
        return
    erg = E.berechnen(roh, katalog, s.get(P + "depot") or [], typen, s.get(P + "ansatz") or "auto",
                      s.get(P + "rangmodus") or "score", TOP_N.get(s.get(P + "top") or "Top 100", 100),
                      {k: s[P + "rate_" + k] for k in E.PROFILES})
    _kennzahlen(erg)
    _strategien(erg)
    with st.container(border=True):
        _scores(erg, typen)
    with st.container(border=True):
        _kaufplan(h, erg)
    with st.container(border=True):
        _entnahmen(erg)
    with st.container(border=True):
        _mix(erg)
    _hinweise()
