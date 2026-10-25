"""Depot-Analyse & Optimierung - eigene Ansicht (Oberflaeche zu depot_analyse.py).

Grundlage ist das echte Depot der App (Bestand, Live-Kurse, Einstand aus der Depot-Berechnung in app.py).
Die Analyse verwendet nur vorhandene Daten (Agenten-Dateien im State-Branch, Kurshistorie von ls-tc.de,
eigene Angaben). Der Simulator rechnet virtuell: das echte Depot wird hier nie veraendert - einzige
Ausnahme ist der ausdruecklich bestaetigte Import "in mein Depot uebernehmen"."""
import datetime
import html
import io
import json
import logging

import pandas as pd
import streamlit as st

import depot_analyse as D
import portfolio_builder_ui as B

P = "da_"
REITER = ["📊 Übersicht", "🔍 Positionen", "🧪 Simulator", "🧭 Szenarien", "💬 Assistent", "⚙️ Daten & Profil"]
STUFE_CSS = {"hoch": "neg", "mittel": "warn", "niedrig": ""}
EMPF_CSS = {"Aufstocken prüfen": "pos", "Halten": "", "Beobachten": "warn", "Reduzieren prüfen": "warn",
            "Verkauf prüfen": "neg"}
BEISPIELE = ["Welche Positionen sind am riskantesten?", "Wie könnte ich mein Depot defensiver aufstellen?",
             "Welche Dividendenstrategie würde zu mir passen?",
             "Wie würde sich mein Depot verändern, wenn ich 10.000 € zusätzlich investiere?",
             "Welche Überschneidungen gibt es zwischen meinen ETFs?",
             "Wie könnte ich mein Portfolio besser gewichten?",
             "Was passiert, wenn ich meine größte Position halbiere?"]
CLAUDE_MODELL = "claude-opus-5-5"
STATE_PFAD = "state/depot_analyse.json"

CSS = """
<style>
.da-chip { display:inline-block; padding:3px 10px; border-radius:999px; font-size:.72rem; font-weight:700;
  background:rgba(91,155,255,.16); color:#BFD6FF; border:1px solid rgba(91,155,255,.35); margin:0 6px 4px 0; }
.da-chip.warn { background:#423523; color:#f4c67b; border-color:#6b5328; }
.da-chip.neg { background:#3f1d22; color:#fca5a5; border-color:#7f1d1d; }
.da-chip.pos { background:#163a2c; color:#86efac; border-color:#166534; }
.da-k { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin:6px 0 10px; }
.da-k .k { border:1px solid var(--line,#22344C); border-radius:12px; padding:10px 12px; background:var(--surface-2,#0E1826); }
.da-k .l { color:#9AA9BF; font-size:.68rem; text-transform:uppercase; letter-spacing:.5px; }
.da-k .w { font-size:1.18rem; font-weight:800; margin-top:2px; }
.da-k .s { color:#9AA9BF; font-size:.74rem; margin-top:2px; }
@media (max-width: 760px) { .da-k { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.da-pos { color:#4ade80; } .da-neg { color:#f87171; } .da-warn { color:#f4c67b; } .da-m { color:#9AA9BF; font-size:.78rem; }
.da-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table.da { display:table !important; width:100%; border-collapse:separate; border-spacing:0; font-size:.84rem; }
table.da th { text-align:left; color:#9AA9BF; font-size:.68rem; letter-spacing:.4px; text-transform:uppercase;
  padding:6px 8px; border-bottom:1px solid var(--line,#22344C); white-space:nowrap; }
table.da td { padding:6px 8px; border-bottom:1px solid #16243A; vertical-align:top; }
table.da .r { text-align:right; white-space:nowrap; }
table.da td.nm { min-width:150px; }
.da-wrap table.da { min-width:560px; }
.da-bahn { height:8px; border-radius:4px; background:#16243A; overflow:hidden; min-width:60px; }
.da-bahn > div { height:100%; background:var(--accent,#5B9BFF); }
.da-score { display:inline-block; min-width:38px; text-align:center; padding:1px 6px; border-radius:8px;
  font-weight:800; background:#16243A; }
.da-score.g { background:#163a2c; color:#86efac; } .da-score.m { background:#3a3418; color:#fde68a; }
.da-score.s { background:#3f1d22; color:#fca5a5; } .da-score.na { color:#9AA9BF; }
.da-box { border:1px solid var(--line,#22344C); border-left:3px solid var(--accent,#5B9BFF); border-radius:10px;
  padding:10px 12px; margin:6px 0; background:var(--surface-2,#0E1826); }
.da-box.warn { border-left-color:#f4c67b; } .da-box.neg { border-left-color:#f87171; } .da-box.pos { border-left-color:#4ade80; }
.da-box b { display:block; margin-bottom:2px; }
.da-sim { border:1px dashed #5B9BFF; border-radius:10px; padding:8px 12px; margin:4px 0 10px; color:#BFD6FF;
  background:rgba(91,155,255,.08); font-size:.85rem; }
</style>
"""


# ---------------------------------------------------------------- kleine Helfer
def _e(t):
    return html.escape(str(t if t is not None else ""))


def _kpis(paare):
    st.markdown('<div class="da-k">' + "".join(
        f'<div class="k"><div class="l">{_e(l)}</div><div class="w">{w}</div>'
        + (f'<div class="s">{u}</div>' if u else "") + "</div>" for l, w, u in paare) + "</div>",
        unsafe_allow_html=True)


def _tabelle(kopf, zeilen, breit=True):
    th = "".join(f'<th class="{k}">{_e(t)}</th>' for t, k in kopf)
    tr = "".join("<tr>" + "".join(f'<td class="{k}">{z}</td>' for (_, k), z in zip(kopf, zeile)) + "</tr>"
                 for zeile in zeilen)
    st.markdown(f'<div class="{"da-wrap" if breit else ""}" tabindex="0" role="region" '
                f'aria-label="Tabelle (seitlich scrollbar)"><table class="da"><thead><tr>{th}</tr></thead>'
                f'<tbody>{tr}</tbody></table></div>', unsafe_allow_html=True)


def _spalten(n):
    """n Felder nebeneinander, unten buendig (Handy: 2 je Zeile)."""
    if not B._smartphone():
        return st.columns(n, vertical_alignment="bottom")
    slots = []
    while len(slots) < n:
        slots += st.columns(2, vertical_alignment="bottom")
    return slots[:n]


def _score(v):
    if v is None:
        return '<span class="da-score na">n/v</span>'
    k = "g" if v >= 70 else "m" if v >= 50 else "s"
    return f'<span class="da-score {k}">{D.de(v, 0)}</span>'


def _bahn(v, max_=100.0):
    if v is None:
        return '<span class="da-m">–</span>'
    return f'<div class="da-bahn"><div style="width:{max(0, min(100, v / max_ * 100)):.0f}%"></div></div>'


def _titel(t):
    st.markdown(f'<div class="pb-karte-t">{_e(t)}</div>', unsafe_allow_html=True)


def _vz_css(x, hoeher_besser=True):
    if x is None or abs(x) < 1e-9:
        return ""
    return "da-pos" if (x > 0) == hoeher_besser else "da-neg"


# ---------------------------------------------------------------- Zustand (je Benutzer)
def _zustand(h):
    s = st.session_state
    if P + "zustand" not in s:
        roh = None
        try:
            roh = h["gh_read"](h["pfad"], None) if h.get("speichern") else None
        except Exception as e:                      # Lesefehler: mit leerem Zustand weiter, aber nichts ueberschreiben
            logging.warning(f"Depot-Analyse: Zustand nicht lesbar: {e}")
            s[P + "lesefehler"] = True
        s[P + "zustand"] = roh if isinstance(roh, dict) else {}
    z = s[P + "zustand"]
    z.setdefault("profil", dict(D.STANDARD_PROFIL))
    z.setdefault("angaben", {})
    z.setdefault("cash", 0.0)
    z.setdefault("varianten", [])
    z.setdefault("gemeldet", {})
    z.setdefault("steuer", {})
    return z


def _speichern(h, felder):
    """felder: {schluessel: wert} in den gespeicherten Zustand uebernehmen. -> True/False"""
    z = _zustand(h)
    z.update(copy_tief(felder))
    if not h.get("speichern") or st.session_state.get(P + "lesefehler"):
        return False

    def aendern(alt):
        neu = dict(alt or {})
        neu.update(copy_tief(felder))
        return neu
    try:
        ok, _ = h["gh_aktualisiere"](h["pfad"], aendern, {}, "depot-analyse [skip ci]")
        return bool(ok)
    except Exception as e:
        logging.warning(f"Depot-Analyse: Speichern fehlgeschlagen: {e}")
        return False


def copy_tief(x):
    return json.loads(json.dumps(x, default=str))


# ---------------------------------------------------------------- Marktdaten
@st.cache_data(ttl=900, show_spinner=False)
def _markt(_lesen, schluessel_tag):
    """Index aus den Agenten-Dateien (oeffentliche Marktdaten). schluessel_tag nur fuer den Cache."""
    zeilen, stand_q = {}, None
    for i in range(6):
        d = _lesen(f"state/qualitaet/alle_{i}.json", None) or {}
        f = d.get("felder") or []
        stand_q = d.get("stand") or stand_q
        for z in d.get("zeilen") or []:
            zeilen[z[0]] = dict(zip(f, z))
    kat, stand_k = [], None
    for i in range(4):
        d = _lesen(f"state/planer/katalog_gross_{i}.json", None) or {}
        stand_k = d.get("stand") or stand_k
        kat.append(d)
    yahoo = _lesen("state/top50_yahoo.json", None) or {}
    m = D.marktdaten_index(zeilen, yahoo.get("isin") or {}, kat)
    m["stand_q"], m["stand_k"] = stand_q, stand_k
    return m


def _details(h, sym, zeile):
    d = h["gh_read_taeglich"](f"state/qualitaet/details_{zeile.get('d', 0)}.json", None) or {}
    return (d.get("werte") or {}).get(sym)


def _bestand(h, z):
    """Analysegrundlage: echtes Depot oder (umschaltbar) ein importiertes Analyse-Depot."""
    if st.session_state.get(P + "quelle") == "import" and st.session_state.get(P + "import_pos"):
        return st.session_state[P + "import_pos"], True
    return h.get("bestand") or [], False


def _analyse(h):
    z = _zustand(h)
    roh, importiert = _bestand(h, z)
    heute = datetime.date.today().isoformat()
    m = _markt(h["gh_read_taeglich"], heute)
    pos = []
    for r in roh:
        try:
            pos.append(D.anreichern(r, m, z["angaben"].get(D.schluessel(r)), lambda s, zl: _details(h, s, zl)))
        except Exception as e:
            logging.warning(f"Depot-Analyse: {r.get('name')} nicht auswertbar: {e}")
            pos.append(dict(r, art="sonstiges", score=None, score_quelle=f"Fehler bei der Auswertung: {e}",
                            score_teile={}, hk=None, fund=None, div=None, ter=None, vola=None, maxdd=None))
    k = D.kennzahlen(pos, z["cash"], z["profil"])
    empf = {D.schluessel(p): D.empfehlung(p, k, z["profil"]) for p in pos if not p.get("ohne_kurs")}
    warn = D.warnungen(pos, k, z.get("stand"))
    return {"pos": pos, "k": k, "empf": empf, "warn": warn, "markt": m, "importiert": importiert, "z": z}


# ---------------------------------------------------------------- Ueberwachung
def _ueberwachung(h, a):
    """Neue relevante Hinweise einmal je 7 Tage in die Chronik (keine Wiederholung derselben Meldung)."""
    if a["importiert"] or not h.get("chronik"):
        return []
    z = a["z"]
    heute = datetime.date.today()
    gemeldet = dict(z.get("gemeldet") or {})
    neu = []
    for w in a["warn"]:
        sk = f"{w['typ']}|{w['schluessel']}"
        alt = gemeldet.get(sk)
        if alt and (heute - datetime.date.fromisoformat(alt)).days < 7:
            continue
        neu.append(w)
        gemeldet[sk] = heute.isoformat()
    if neu:
        for w in neu[:8]:
            try:
                h["chronik"]("analyse", f"🧠 {w['typ']}", w["text"], schluessel=f"da:{w['typ']}:{w['schluessel']}:"
                             f"{heute.isocalendar()[1]}")
            except Exception as e:
                logging.warning(f"Depot-Analyse: Chronik-Eintrag fehlgeschlagen: {e}")
        # alte Eintraege (> 60 Tage) aufraeumen
        gemeldet = {k: v for k, v in gemeldet.items() if (heute - datetime.date.fromisoformat(v)).days <= 60}
        _speichern(h, {"gemeldet": gemeldet})
    return neu


# ---------------------------------------------------------------- Uebersicht
def _uebersicht(h, a):
    k, pos, empf = a["k"], a["pos"], a["empf"]
    if st.button("🧠 Mein Depot jetzt analysieren", type="primary", key=P + "analysieren", width="stretch"):
        st.session_state[P + "gesamt_offen"] = True
        st.session_state[P + "stand_neu"] = True
    if st.session_state.get(P + "gesamt_offen"):
        g = D.gesamtanalyse(pos, k, empf, a["warn"])
        with st.container(border=True):
            _titel("Ergebnis der Analyse")
            for f, antw in g["antworten"]:
                st.markdown(f'<div class="da-box"><b>{_e(f)}</b>{_e(antw)}</div>', unsafe_allow_html=True)
            _titel("Priorisierter Aktionsplan")
            if g["aktionsplan"]:
                _tabelle([("Priorität", ""), ("Maßnahme", "nm"), ("Warum", "")],
                         [[f'<span class="da-chip {STUFE_CSS[x["prio"]]}">{x["prio"]}</span>', _e(x["massnahme"]),
                           f'<span class="da-m">{_e(x["warum"])}</span>'] for x in g["aktionsplan"]])
            else:
                st.caption("Keine Maßnahmen nötig.")
            st.caption("„… prüfen“ heißt: die Kennzahlen sprechen dafür, sich den Wert genauer anzusehen – es ist "
                       "keine Kauf- oder Verkaufsaufforderung. Umsetzen lässt sich alles zuerst virtuell im Simulator.")
        if st.session_state.pop(P + "stand_neu", False) and not a["importiert"]:
            jetzt = datetime.datetime.now().isoformat(timespec="minutes")
            if _speichern(h, {"stand": D.stand_merken(pos, k), "stand_zeit": jetzt}):
                st.caption(f"Analyse-Stand vom {_zeit_de(jetzt)} gespeichert – spätere Veränderungen "
                           "(Score, Dividende, Risiko) werden daran gemessen.")

    s = k.get("score")
    rendite = k.get("rendite")
    _kpis([("Depotwert", D.eur(k["gesamt"]), f'davon Liquidität {D.eur(k["cash"])}' if k["cash"] else
            f'{k["anzahl"]} Positionen mit Kurs'),
           ("Gesamtrendite", f'<span class="{_vz_css(k.get("gv"))}">{D.eur(k.get("gv"))}</span>',
            D.pct(rendite, 1, True) + " seit Kauf (inkl. Auszahlungen)" if rendite is not None else "Einstand unbekannt"),
           ("Depot-Score", f'{_score(s)} <span class="da-m">/ 100</span>',
            f'Qualität aus {D.pct(k.get("score_abdeckung"), 0)} des Depots' if s is not None else "keine Daten"),
           ("Risiko", _e(k.get("risiko")), f'Schwankung {D.pct(k.get("vola"))} p. a. · tragbar '
                                           f'{D.pct(k["ziel"]["vola"], 0)}'),
           ("Dividendenprognose", D.eur(k.get("dividende")),
            f'p. a. · bekannt für {D.pct(k.get("div_abdeckung"), 0)} des Depots'),
           ("Diversifikation", D.de(k.get("eff_n")), "effektive Positionen"),
           ("Größte Position", D.pct(k["groesste"][1]) if k.get("groesste") else "–",
            _e(k["groesste"][0]) if k.get("groesste") else ""),
           ("Laufende Kosten", D.eur(k.get("kosten")),
            f'p. a. · TER bekannt für {D.pct(k.get("kosten_abdeckung"), 0)} der Fonds')])
    if k["ohne_kurs"]:
        st.warning("Ohne Kurs und daher nicht bewertet: " + ", ".join(p["name"] for p in k["ohne_kurs"])
                   + ". Kursquelle unter „Depot verwalten“ ergänzen.")

    c1, c2 = (st.container(), st.container()) if B._smartphone() else st.columns(2)
    with c1, st.container(border=True):
        _titel("Depot-Score – Teilbewertungen")
        t = k.get("teile") or {}
        _tabelle([("Bereich", "nm"), ("Gewicht", "r"), ("Punkte", "r"), ("", "")],
                 [[_e(n), f"{g} %", D.de(t.get(key), 0) if t.get(key) is not None else
                   '<span class="da-m">keine Daten</span>', _bahn(t.get(key))] for key, n, g in D.SCORE_GEWICHTE],
                 breit=False)
        st.caption("Fehlende Teilbewertungen zählen nicht – der Score wird über die vorhandenen Teile gerechnet.")
    with c2, st.container(border=True):
        _titel("Hinweise & Warnungen")
        if not a["warn"]:
            st.caption("Keine relevanten Hinweise.")
        for w in a["warn"][:10]:
            st.markdown(f'<div class="da-box {STUFE_CSS.get(w["stufe"], "")}"><b>{_e(w["typ"])}</b>{_e(w["text"])}'
                        '</div>', unsafe_allow_html=True)
        if len(a["warn"]) > 10:
            st.caption(f"+ {len(a['warn']) - 10} weitere")

    with st.container(border=True):
        _titel("Verteilung")
        st.session_state.setdefault(P + "vert", "Anlageklasse")
        dim = st.pills("Aufteilung nach", list(k.get("verteilung") or {}), key=P + "vert") or "Anlageklasse"
        vert = (k.get("verteilung") or {}).get(dim) or {}
        _tabelle([(dim, "nm"), ("Anteil", "r"), ("", "")],
                 [[_e(n), D.pct(v), _bahn(v)] for n, v in vert.items()], breit=False)
        if dim in ("Land", "Branche") and "unbekannt" in vert:
            st.caption("„unbekannt“: Für ETFs liegt die Länder-/Branchenzusammensetzung nicht vor; Angaben je "
                       "Position lassen sich unter „Daten & Profil“ ergänzen.")
        zs = k["ziel"]
        _titel("Zielstruktur laut Profil")
        _tabelle([("Klasse", "nm"), ("Ist", "r"), ("Ziel", "r"), ("Abweichung", "r")],
                 [[D.ARTEN[a_], D.pct((k.get("klassen") or {}).get(a_, 0.0), 0), D.pct(v, 0),
                   f'<span class="{"da-warn" if abs(k["abweichung"].get(a_, 0)) >= 10 else ""}">'
                   f'{D.pct(k["abweichung"].get(a_, 0), 0, True)}</span>'] for a_, v in zs["ziel"].items()], breit=False)
        st.caption(" · ".join(zs["gruende"]))

    with st.container(border=True):
        _titel("Einzelpositionen & Empfehlungen")
        zeilen = []
        for p in sorted([p for p in pos if not p.get("ohne_kurs")], key=lambda p: -D._wert(p)):
            e = empf[D.schluessel(p)]
            zeilen.append([f'<b>{_e(p["name"])}</b><br><span class="da-m">{_e(D.ARTEN.get(p["art"]))} · '
                           f'{_e(p.get("isin") or p.get("wkn"))}</span>',
                           D.eur(p.get("wert")), D.pct(k["gewichte"].get(D.schluessel(p))), _score(p.get("score")),
                           f'<span class="da-chip {EMPF_CSS.get(e["kategorie"], "")}">{_e(e["kategorie"])}</span>',
                           _e(e["prio"])])
        _tabelle([("Position", "nm"), ("Wert", "r"), ("Gewicht", "r"), ("Score", "r"), ("Empfehlung", ""),
                  ("Priorität", "")], zeilen)
        st.caption("Details, Begründung, Chancen und Risiken je Position im Reiter „🔍 Positionen“.")
        if k.get("ueberschneidungen"):
            _titel("ETF-Überschneidungen (nach Index-Familie)")
            for u in k["ueberschneidungen"]:
                st.markdown(f'<div class="da-box {"warn" if u["stark"] else ""}"><b>{_e(u["a"])} / {_e(u["b"])}</b>'
                            f'{_e(u["grund"])} – zusammen {D.pct(u["gewicht"])} des Depots</div>',
                            unsafe_allow_html=True)


# ---------------------------------------------------------------- Positionen (Detail)
def _positionen(h, a):
    pos = [p for p in a["pos"] if not p.get("ohne_kurs")]
    if not pos:
        st.info("Keine Positionen mit Kurs vorhanden.")
        return
    namen = [p["name"] for p in sorted(pos, key=lambda p: -D._wert(p))]
    wahl = st.selectbox("Position", namen, key=P + "detail")
    p = next(x for x in pos if x["name"] == wahl)
    k, e = a["k"], a["empf"][D.schluessel(p)]
    f = p.get("fund") or {}
    hk = p.get("hk") or {}
    gv = (D._wert(p) + (D._z(p.get("ausgezahlt"), 0) or 0) - p["einstand"]) if D._z(p.get("einstand")) else None
    _kpis([("Wert", D.eur(p.get("wert"), 2), f'{D.de(p.get("stueck"), 4)} Stück × {D.de(p.get("kurs"), 2)} €'),
           ("Gewinn/Verlust", f'<span class="{_vz_css(gv)}">{D.eur(gv)}</span>',
            D.pct(gv / p["einstand"] * 100, 1, True) if gv is not None and p["einstand"] else "Einstand unbekannt"),
           ("Score", f'{_score(p.get("score"))} <span class="da-m">/ 100</span>', _e(p.get("score_quelle"))),
           ("Empfehlung", f'<span class="da-chip {EMPF_CSS.get(e["kategorie"], "")}">{_e(e["kategorie"])}</span>',
            f'Priorität {e["prio"]} · {e["horizont"]}')])
    c1, c2 = (st.container(), st.container()) if B._smartphone() else st.columns(2)
    with c1, st.container(border=True):
        _titel("Kennzahlen (Fakten)")
        werte = [("Klasse", D.ARTEN.get(p["art"])), ("Gewicht im Depot", D.pct(k["gewichte"].get(D.schluessel(p)))),
                 ("Land", p.get("land") or "unbekannt"), ("Branche", p.get("branche") or "unbekannt"),
                 ("Währung", p.get("waehrung") or "unbekannt"),
                 ("Dividendenrendite", (D.pct(p.get("div")) + f' ({p["div_quelle"]})') if p.get("div") is not None
                  else "unbekannt"),
                 ("Ausschüttungsquote", D.pct(D._z(f.get("div_q")), 0) if f.get("div_q") is not None else "–"),
                 ("KGV / hist. KGV", f'{D.de(D._z(f.get("kgv")))} / {D.de(D._z(f.get("h_kgv")))}' if f else "–"),
                 ("PEG", D.de(D._z(f.get("peg")), 2) if f.get("peg") is not None else "–"),
                 ("ROIC / ROE", f'{D.pct(D._z(f.get("roic")), 0)} / {D.pct(D._z(f.get("roe")), 0)}' if f else "–"),
                 ("Umsatz- / Gewinnwachstum p. a.", f'{D.pct(D._z(f.get("g_ums")), 0)} / {D.pct(D._z(f.get("g_eps")), 0)}'
                  if f else "–"),
                 ("Nettoverschuldung / EBITDA", D.de(D._z(f.get("nde")), 2) if f.get("nde") is not None else "–"),
                 ("Schwankung p. a.", D.pct(p.get("vola"))), ("Max. Rückgang", D.pct(p.get("maxdd"))),
                 ("Veränderung 1 Monat / 1 Jahr", f'{D.pct(hk.get("m1"), 1, True)} / {D.pct(hk.get("j1"), 1, True)}'),
                 ("Laufende Kosten (TER)", D.pct(p.get("ter"), 2) if p.get("ter") is not None else "unbekannt")]
        _tabelle([("Kennzahl", "nm"), ("Wert", "r")], [[_e(a_), _e(b_)] for a_, b_ in werte], breit=False)
        st.caption("Quellen: " + " · ".join(x for x in (
            "Kurs/Historie ls-tc.de" if p.get("hist") is not None else None,
            "Qualitäts-Agent (Geschäftszahlen Yahoo Finance)" if f else None,
            "Top-500-Katalog" if p.get("katalog") else None,
            "eigene Angaben" if a["z"]["angaben"].get(D.schluessel(p)) else None) if x))
    with c2, st.container(border=True):
        _titel("Score – Teilwerte")
        teile = D.score_teile_lesbar(p)
        if teile:
            _tabelle([("Bereich", "nm"), ("Punkte", "r"), ("", "")],
                     [[_e(n), (f"{D.de(v, 0)} / {m}" if v is not None else '<span class="da-m">keine Daten</span>'),
                       _bahn(v, m)] for n, v, m in teile], breit=False)
        else:
            st.caption("Keine Teilwerte – " + _e(p.get("score_quelle")))
        _titel("Begründung (Fakten)")
        st.markdown("\n".join(f"- {_e(g)}" for g in e["gruende"]))
        _titel("Bewertung")
        st.caption(_e(e["bewertung"]))
        _titel("Chancen (Einschätzung)")
        st.markdown("\n".join(f"- {_e(c)}" for c in e["chancen"]) or "–")
        _titel("Risiken (Einschätzung)")
        st.markdown("\n".join(f"- {_e(r)}" for r in e["risiken"]) or "–")
    if p.get("hist") is not None and len(p["hist"]) > 5:
        with st.container(border=True):
            _titel("Kursverlauf (ls-tc.de, Tagesschluss)")
            import plotly.graph_objects as go
            fig = go.Figure(go.Scatter(x=p["hist"].index, y=p["hist"].values, mode="lines",
                                       line={"color": "#5B9BFF", "width": 2}, hovertemplate="%{x|%d.%m.%Y}: %{y:.2f} €"
                                                                                         "<extra></extra>"))
            fig.update_layout(height=240, margin={"l": 10, "r": 10, "t": 10, "b": 10}, paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", font={"color": "#C9D4E5"}, showlegend=False,
                              separators=",.", xaxis={"gridcolor": "#16243A"},
                              yaxis={"gridcolor": "#16243A", "ticksuffix": " €"})
            st.plotly_chart(fig, width="stretch", key=P + "kurs_chart", config={"displayModeBar": False})


# ---------------------------------------------------------------- Simulator
def _sim_reset(a):
    st.session_state[P + "soll"] = {D.schluessel(p): D._z(p.get("stueck"), 0.0) for p in a["pos"]}
    st.session_state[P + "neu"] = []
    st.session_state[P + "ed_nr"] = st.session_state.get(P + "ed_nr", 0) + 1
    st.session_state.pop(P + "sim_quelle", None)


def _sim_optimieren(a, profil, zusatz=0.0, quelle="✨ Mein Depot optimieren"):
    k = a["k"]
    if zusatz:
        k = D.kennzahlen(a["pos"], a["z"]["cash"] + zusatz, profil)
    o = D.optimieren(a["pos"], k, profil)
    soll = {D.schluessel(p): D._z(p.get("stueck"), 0.0) for p in a["pos"]}
    soll.update({sk: v for sk, v in o["stueck"].items() if v is not None})
    st.session_state[P + "soll"] = soll
    st.session_state[P + "neu"] = []
    st.session_state[P + "ed_nr"] = st.session_state.get(P + "ed_nr", 0) + 1
    st.session_state[P + "sim_quelle"] = quelle
    st.session_state[P + "opt"] = o
    if zusatz:
        st.session_state[P + "zusatz"] = float(zusatz)


def _sim_neu_suchen(h):
    with st.expander("➕ Neuen Wert virtuell hinzufügen"):
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        q = c1.text_input("WKN, ISIN oder Name", key=P + "neu_q")
        if c2.button("Suchen", key=P + "neu_suche", width="stretch") and q.strip():
            st.session_state[P + "neu_treffer"] = (h["suche_instrument"](q.strip()) or [])[:8]
        treffer = st.session_state.get(P + "neu_treffer") or []
        if not treffer:
            st.caption("Der Kurs kommt aus der Kursquelle (ls-tc.de) – ohne echten Kurs wird kein Wert hinzugefügt.")
            return
        t = st.selectbox("Treffer", treffer, key=P + "neu_wahl",
                         format_func=lambda t: f'{t["name"]} · {t.get("wkn") or t.get("isin")} · {t.get("kategorie")}')
        c1, c2 = st.columns([1, 1], vertical_alignment="bottom")
        stueck = c1.number_input("Stück", 0.0, 1e7, 1.0, step=1.0, key=P + "neu_stueck")
        if c2.button("Hinzufügen", key=P + "neu_add", width="stretch"):
            kurs, _, _ = h["get_live_kurs"](int(t["instrument_id"]))
            if not kurs:
                st.error("Für diesen Wert liefert die Kursquelle gerade keinen Kurs – nicht hinzugefügt.")
                return
            kat = str(t.get("kategorie") or "").lower()
            art = "wikifolio" if "wikifolio" in kat else "etf" if "etf" in kat or "fonds" in kat else (
                "aktie" if "aktie" in kat else None)
            st.session_state[P + "neu"] = [n for n in st.session_state.get(P + "neu") or []
                                          if n["instrument_id"] != t["instrument_id"]] + [
                {"name": t["name"], "isin": t.get("isin") or "", "wkn": t.get("wkn") or "",
                 "instrument_id": int(t["instrument_id"]), "kurs": float(kurs), "stueck": float(stueck), "art": art}]
            st.rerun(scope="fragment")


def _simulator(h, a):
    s = st.session_state
    z = a["z"]
    if P + "soll" not in s:
        _sim_reset(a)
    if P + "zusatz_neu" in s:                       # aus "Variante laden" (Widget existierte schon)
        s[P + "zusatz"] = s.pop(P + "zusatz_neu")
    st.markdown('<div class="da-sim">🧪 <b>Simulation</b> – alle Änderungen sind virtuell. Dein echtes Depot wird '
                'hier nicht verändert; es werden keine Orders ausgelöst.</div>', unsafe_allow_html=True)
    b = _spalten(3)
    if b[0].button("✨ Mein Depot optimieren", key=P + "opt_knopf", type="primary", width="stretch"):
        _sim_optimieren(a, z["profil"], s.get(P + "zusatz") or 0.0)
        st.rerun(scope="fragment")
    if b[1].button("↺ Zurücksetzen", key=P + "sim_reset", width="stretch"):
        _sim_reset(a)
        s[P + "zusatz"] = 0.0
        st.rerun(scope="fragment")
    szen = b[2].selectbox("Szenario übernehmen", ["–"] + list(D.SZENARIEN), key=P + "szen_wahl",
                          format_func=lambda x: "Szenario übernehmen …" if x == "–" else D.SZENARIEN[x]["titel"],
                          label_visibility="collapsed")
    if szen != "–" and s.get(P + "szen_zuletzt") != szen:
        s[P + "szen_zuletzt"] = szen
        _sim_optimieren(a, dict(z["profil"], **D.SZENARIEN[szen]["profil"]), s.get(P + "zusatz") or 0.0,
                        f'Szenario „{D.SZENARIEN[szen]["titel"]}“')
        st.rerun(scope="fragment")
    if szen == "–":
        s.pop(P + "szen_zuletzt", None)
    if s.get(P + "sim_quelle"):
        o = s.get(P + "opt") or {}
        st.caption(f'Vorschlag aus {s[P + "sim_quelle"]}: ' + (
            f'Depot-Score {D.de(o.get("score_vorher"), 0)} → {D.de(o.get("score_nachher"), 0)}.'
            if o.get("massnahmen") else "keine Umschichtung verbessert den Depot-Score – Vorschlag = aktueller Bestand.")
            + (f' Im Depot fehlen: {", ".join(D.ARTEN[x] for x in o["fehlende_klassen"])} – neue Werte nur über '
               '„Neuen Wert virtuell hinzufügen“ (Vorschläge macht der Scanner 2.0).' if o.get("fehlende_klassen") else ""))
        for m in (o.get("massnahmen") or [])[:8]:
            st.markdown(f'<div class="da-box"><b>{_e(m["aktion"])} {D.de(m["stueck"], 0)} × {_e(m["name"])} '
                        f'(ca. {D.eur(m["betrag"])})</b>{_e(m["grund"])} · Gewicht {D.pct(m["ist_pct"])} → '
                        f'{D.pct(m["ziel_pct"])} · {_e(m["risiko"])}</div>', unsafe_allow_html=True)

    stz = z.get("steuer") or {}
    for key_, wert_ in (("cash_sim", float(z["cash"])), ("zusatz", 0.0), ("geb_fix", float(stz.get("geb_fix", 1.0))),
                        ("geb_pct", float(stz.get("geb_pct", 0.0))), ("st_fb", float(stz.get("freibetrag", 0.0))),
                        ("st_va", float(stz.get("verlust_aktien", 0.0))),
                        ("st_vs", float(stz.get("verlust_sonstige", 0.0))),
                        ("st_ki", int(stz.get("kirchensteuer", 0) or 0))):
        s.setdefault(P + key_, wert_)
    with st.container(border=True):
        _titel("Kapital, Gebühren & Steuern")
        c = _spalten(4)
        c[0].number_input("Liquidität heute €", 0.0, 1e9, step=100.0, format="%.0f", key=P + "cash_sim",
                          help="Aus „Daten & Profil“; hier nur für die Simulation änderbar.")
        c[1].number_input("Zusätzliches Kapital €", 0.0, 1e9, step=500.0, format="%.0f", key=P + "zusatz")
        c[2].number_input("Ordergebühr fix €", 0.0, 100.0, step=0.5, key=P + "geb_fix")
        c[3].number_input("Ordergebühr % vom Betrag", 0.0, 5.0, step=0.05, format="%.2f", key=P + "geb_pct")
        with st.expander("Steuer-Annahmen (Deutschland)"):
            c = _spalten(4)
            c[0].number_input("Rest-Sparerpauschbetrag €", 0.0, 2000.0, step=100.0, format="%.0f", key=P + "st_fb")
            c[1].number_input("Verlusttopf Aktien €", 0.0, 1e8, step=100.0, format="%.0f", key=P + "st_va")
            c[2].number_input("Verlusttopf sonstige €", 0.0, 1e8, step=100.0, format="%.0f", key=P + "st_vs")
            c[3].selectbox("Kirchensteuer", [0, 8, 9], key=P + "st_ki",
                           format_func=lambda x: "keine" if not x else f"{x} %")
            st.caption("Abgeltungsteuer 25 % + Soli 5,5 % (+ ggf. Kirchensteuer) auf realisierte Gewinne · "
                       "Aktienfonds-ETFs mit 30 % Teilfreistellung (je Position änderbar) · Einstand je Stück als "
                       "Durchschnitt (die App kennt keine Einzelkäufe/FIFO) · nicht berücksichtigt: Vorabpauschale, "
                       "Altbestand vor 2009, Quellensteuer.")
            if st.button("Annahmen als Standard speichern", key=P + "st_speichern"):
                ok = _speichern(h, {"steuer": {"freibetrag": s[P + "st_fb"], "verlust_aktien": s[P + "st_va"],
                                               "verlust_sonstige": s[P + "st_vs"], "kirchensteuer": s[P + "st_ki"],
                                               "geb_fix": s[P + "geb_fix"], "geb_pct": s[P + "geb_pct"]}})
                st.success("Gespeichert.") if ok else st.info("Nur für diese Sitzung übernommen (Speicher nicht "
                                                               "verfügbar).")

    neu_pos = [D.neue_position(n["name"], n["art"], n["kurs"], n["stueck"], n["isin"], n["wkn"], n["instrument_id"],
                               z["angaben"].get(D.schluessel(n)), a["markt"]) for n in s.get(P + "neu") or []]
    ist = [p for p in a["pos"] if not p.get("ohne_kurs")] + neu_pos
    modus = st.radio("Eingabe", ["Stückzahl", "Zielgewicht %"], horizontal=True, key=P + "modus")
    gesamt_soll = a["k"]["gesamt"] + (s.get(P + "zusatz") or 0.0) + (s[P + "cash_sim"] - z["cash"])
    soll = s[P + "soll"]
    for n in neu_pos:
        soll.setdefault(D.schluessel(n), n["ziel_stueck"])
    df = pd.DataFrame([{"Wert": p["name"], "Klasse": D.ARTEN.get(p["art"], p["art"]), "Kurs €": p["kurs"],
                        "Ist Stück": D._z(p.get("stueck"), 0.0), "Ist %": a["k"]["gewichte"].get(D.schluessel(p), 0.0),
                        "Soll Stück": soll.get(D.schluessel(p), D._z(p.get("stueck"), 0.0)),
                        "Soll %": (soll.get(D.schluessel(p), 0.0) * p["kurs"] / gesamt_soll * 100) if gesamt_soll else 0.0}
                       for p in ist])
    spalten = {"Kurs €": st.column_config.NumberColumn(format="%.2f"),
               "Ist Stück": st.column_config.NumberColumn(format="%.4f"),
               "Ist %": st.column_config.NumberColumn(format="%.1f"),
               "Soll Stück": st.column_config.NumberColumn(format="%.4f", min_value=0.0),
               "Soll %": st.column_config.NumberColumn(format="%.1f", min_value=0.0, max_value=100.0)}
    gesperrt = ["Wert", "Klasse", "Kurs €", "Ist Stück", "Ist %"] + (["Soll %"] if modus == "Stückzahl"
                                                                     else ["Soll Stück"])
    ed = st.data_editor(df, key=f"{P}ed_{s.get(P + 'ed_nr', 0)}_{modus}", hide_index=True, width="stretch",
                        disabled=gesperrt, column_config=spalten, num_rows="fixed")
    aend = {}
    for p, (_, zeile) in zip(ist, ed.iterrows()):
        sk = D.schluessel(p)
        if modus == "Stückzahl":
            aend[sk] = max(float(zeile["Soll Stück"] or 0.0), 0.0)
        else:
            aend[sk] = gesamt_soll * max(float(zeile["Soll %"] or 0.0), 0.0) / 100 / p["kurs"]
    s[P + "soll"] = dict(soll, **aend)
    if modus == "Zielgewicht %":
        summe = sum(float(x or 0) for x in ed["Soll %"])
        st.caption(f"Summe der Zielgewichte {D.pct(summe)} – der Rest ({D.pct(100 - summe)}) bleibt Liquidität. "
                   "Bei Zielgewichten wird mit Bruchstücken gerechnet.")
    _sim_neu_suchen(h)

    sim = D.simulieren(ist, aend, cash=s[P + "cash_sim"], zusatz=s.get(P + "zusatz") or 0.0,
                       gebuehr_fix=s[P + "geb_fix"], gebuehr_pct=s[P + "geb_pct"],
                       steuer={"freibetrag": s[P + "st_fb"], "verlust_aktien": s[P + "st_va"],
                               "verlust_sonstige": s[P + "st_vs"], "kirchensteuer": s[P + "st_ki"]})
    k_vor = D.kennzahlen(a["pos"], s[P + "cash_sim"] + (s.get(P + "zusatz") or 0.0), z["profil"])
    k_nach = D.kennzahlen(sim["soll"] + [p for p in a["pos"] if p.get("ohne_kurs")], sim["cash_nachher"],
                          z["profil"])
    for w in sim["warnungen"]:
        st.warning(w)
    with st.container(border=True):
        _titel("Ist und Soll im Vergleich")
        c1, c2 = (st.container(), st.container()) if B._smartphone() else st.columns(2)
        for spalte, titel, kk in ((c1, "IST (heute)", k_vor), (c2, "SOLL (simuliert)", k_nach)):
            with spalte:
                st.markdown(f'<div class="da-chip">{titel}</div>', unsafe_allow_html=True)
                _kpis([("Depotwert", D.eur(kk["gesamt"]), ""), ("Depot-Score", _score(kk.get("score")), ""),
                       ("Schwankung", D.pct(kk.get("vola")), _e(kk.get("risiko"))),
                       ("Größte Position", D.pct(kk["groesste"][1]) if kk.get("groesste") else "–",
                        _e(kk["groesste"][0]) if kk.get("groesste") else "")])
        zeilen = []
        for r in D.vergleich(k_vor, k_nach):
            fmt_ = {"eur": lambda x: D.eur(x), "pkt": lambda x: D.de(x, 0), "pct": lambda x: D.pct(x),
                    "zahl": lambda x: D.de(x), "gross": lambda x: D.pct(x), "vert": lambda x: D.pct(x)}[r["format"]]
            diff = r["diff"]
            diff_txt = "–" if diff is None else (("+" if diff > 0 else "") + (
                D.eur(diff) if r["format"] == "eur" else D.de(diff, 1) + (" Pkt." if r["format"] in ("gross", "vert",
                                                                                                 "pct", "pkt") else "")))
            if r["diff_pct"] is not None:
                diff_txt += f' ({D.pct(r["diff_pct"], 1, True)})'
            css = {"besser": "da-pos", "schlechter": "da-neg"}.get(r["urteil"], "")
            label = (lambda l: f'<br><span class="da-m">{_e(l)}</span>' if l else "")
            zeilen.append([_e(r["kennzahl"]), fmt_(r["vorher"]) + label(r["vorher_label"]),
                           fmt_(r["nachher"]) + label(r["nachher_label"]), f'<span class="{css}">{diff_txt}</span>',
                           f'<span class="{css}">{_e(r["urteil"])}</span>'])
        _tabelle([("Kennzahl", "nm"), ("Vorher", "r"), ("Nachher", "r"), ("Veränderung", "r"), ("", "")], zeilen)
        st.caption("Grün = Verbesserung, Rot = Verschlechterung, ohne Farbe = neutral (Depotwert, Dividende und "
                   "Liquidität sind keine Qualitätsurteile). Branche/Land: nur Werte mit bekannter Zuordnung – für "
                   "ETFs liegt sie meist nicht vor.")
    with st.container(border=True):
        _titel("Virtuelle Transaktionen")
        if sim["trades"]:
            _tabelle([("Aktion", ""), ("Wert", "nm"), ("Stück", "r"), ("Kurs", "r"), ("Betrag", "r"), ("Gebühr", "r"),
                      ("Gewinn (vor Steuer)", "r")],
                     [[f'<span class="da-chip {"pos" if t["aktion"] == "Kauf" else "warn"}">{t["aktion"]}</span>',
                       _e(t["name"]) + (' <span class="da-chip">neu</span>' if t["neu"] else ""),
                       D.de(t["stueck"], 4).rstrip("0").rstrip(","), D.eur(t["kurs"], 2), D.eur(t["betrag"], 2),
                       D.eur(t["gebuehr"], 2), D.eur(t["gewinn"], 2) if t["gewinn"] is not None else "–"]
                      for t in sim["trades"]])
            stx = sim["steuern"]
            _kpis([("Ordergebühren", D.eur(sim["gebuehren"], 2), ""),
                   ("Realisierter Gewinn", D.eur(stx["realisiert"], 2), "nach Gebühren, vor Steuer"),
                   ("Geschätzte Steuer", D.eur(stx["steuer"], 2),
                    f'steuerpflichtig {D.eur(stx["nach_freibetrag"], 2)} (nach Teilfreistellung, Verlusttöpfen, '
                    'Freibetrag)'),
                   ("Liquidität danach", D.eur(sim["cash_nachher"], 2), "")])
            st.caption(" · ".join([stx["teilfreistellung_hinweis"]] + stx["luecken"]) + ". Schätzung, keine "
                       "Steuerberatung.")
        else:
            st.caption("Noch keine Änderung – Soll-Stückzahlen in der Tabelle anpassen, einen neuen Wert hinzufügen "
                       "oder „Mein Depot optimieren“ wählen.")
    opt_k = None
    if s.get(P + "opt") and s.get(P + "opt", {}).get("massnahmen"):
        opt_k = {"score": s[P + "opt"].get("score_nachher")}
    else:
        try:
            o = D.optimieren(a["pos"], k_vor, z["profil"])
            opt_k = {"score": o.get("score_nachher")} if o.get("massnahmen") else None
        except Exception:
            opt_k = None
    bew = D.simulation_bewerten(k_vor, k_nach, sim, z["profil"], opt_k)
    with st.container(border=True):
        _titel("Bewertung der Simulation")
        if sim["trades"]:
            for f, antw in bew["antworten"]:
                st.markdown(f'<div class="da-box"><b>{_e(f)}</b>{_e(antw)}</div>', unsafe_allow_html=True)
            css = {"besser": "pos", "schlechter": "neg"}.get(bew["urteil"], "")
            st.markdown(f'<div class="da-box {css}"><b>Fazit</b>{_e(bew["fazit"])}</div>', unsafe_allow_html=True)
            st.caption("Regelbasierte Auswertung der Kennzahlen (Depot-Score ±3 Punkte entscheidet über "
                       "besser/schlechter) – keine Anlageberatung.")
        else:
            st.caption("Erst nach einer Änderung verfügbar.")
    _varianten(h, a, ist, aend, sim, k_vor, k_nach, bew)


def _varianten(h, a, ist, aend, sim, k_vor, k_nach, bew):
    s = st.session_state
    z = a["z"]
    with st.container(border=True):
        _titel("Varianten speichern & vergleichen")
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        name = c1.text_input("Name der Variante", key=P + "var_name", placeholder="z. B. Weniger Tech, mehr ETF")
        if c2.button("💾 Speichern", key=P + "var_save", width="stretch", disabled=not sim["trades"]):
            v = {"name": (name or "").strip() or f"Variante {len(z['varianten']) + 1}",
                 "zeit": datetime.datetime.now().isoformat(timespec="minutes"),
                 "soll": {sk: x for sk, x in aend.items()}, "neu": s.get(P + "neu") or [],
                 "zusatz": s.get(P + "zusatz") or 0.0,
                 "ergebnis": {"score": k_nach.get("score"), "vola": k_nach.get("vola"), "eff_n": k_nach.get("eff_n"),
                              "dividende": k_nach.get("dividende"), "groesste": k_nach["groesste"][1]
                              if k_nach.get("groesste") else None, "gebuehren": sim["gebuehren"],
                              "steuer": sim["steuern"]["steuer"], "urteil": bew["urteil"]}}
            varianten = [x for x in z["varianten"] if x["name"] != v["name"]] + [v]
            ok = _speichern(h, {"varianten": varianten[-20:]})
            st.success(f"„{v['name']}“ gespeichert.") if ok else st.info(f"„{v['name']}“ für diese Sitzung gemerkt.")
        if z["varianten"]:
            _tabelle([("Variante", "nm"), ("Score", "r"), ("Schwankung", "r"), ("Eff. Pos.", "r"), ("Dividende", "r"),
                      ("Größte", "r"), ("Kosten einmalig", "r"), ("Urteil", "")],
                     [["<b>Aktuelles Depot</b>", _score(k_vor.get("score")), D.pct(k_vor.get("vola")),
                       D.de(k_vor.get("eff_n")), D.eur(k_vor.get("dividende")),
                       D.pct(k_vor["groesste"][1]) if k_vor.get("groesste") else "–", "–", ""]]
                     + [[f'{_e(v["name"])}<br><span class="da-m">{_e(_zeit_de(v["zeit"]))}</span>',
                         _score(v["ergebnis"].get("score")), D.pct(v["ergebnis"].get("vola")),
                         D.de(v["ergebnis"].get("eff_n")), D.eur(v["ergebnis"].get("dividende")),
                         D.pct(v["ergebnis"].get("groesste")),
                         D.eur((v["ergebnis"].get("gebuehren") or 0) + (v["ergebnis"].get("steuer") or 0), 2),
                         _e(v["ergebnis"].get("urteil"))] for v in z["varianten"]])
            st.caption("Ergebnisse zum Zeitpunkt des Speicherns. „Laden“ rechnet mit den heutigen Kursen neu.")
            c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
            wahl = c1.selectbox("Variante", [v["name"] for v in z["varianten"]], key=P + "var_wahl")
            if c2.button("Laden", key=P + "var_laden", width="stretch"):
                v = next(x for x in z["varianten"] if x["name"] == wahl)
                s[P + "soll"] = dict(v["soll"])
                s[P + "neu"] = list(v.get("neu") or [])
                s[P + "zusatz_neu"] = float(v.get("zusatz") or 0.0)
                s[P + "ed_nr"] = s.get(P + "ed_nr", 0) + 1
                s[P + "sim_quelle"] = f"Variante „{wahl}“"
                s.pop(P + "opt", None)
                st.rerun(scope="fragment")
            if c3.button("Löschen", key=P + "var_del", width="stretch"):
                _speichern(h, {"varianten": [x for x in z["varianten"] if x["name"] != wahl]})
                st.rerun(scope="fragment")
        _export(h, a, sim, k_vor, k_nach, bew)


def _export(h, a, sim=None, k_vor=None, k_nach=None, bew=None):
    k = a["k"]
    zeilen = D.export_tabelle(a["pos"], k, a["empf"])
    df = pd.DataFrame(zeilen)
    c = _spalten(3)
    c[0].download_button("⬇ CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                         "depot_analyse.csv", "text/csv", key=P + "dl_csv", width="stretch")
    try:
        puffer = io.BytesIO()
        with pd.ExcelWriter(puffer, engine="openpyxl") as xw:
            df.to_excel(xw, sheet_name="Positionen", index=False)
            if sim and sim["trades"]:
                pd.DataFrame(sim["trades"]).drop(columns=["schluessel"], errors="ignore").to_excel(
                    xw, sheet_name="Simulation", index=False)
                pd.DataFrame(D.vergleich(k_vor, k_nach)).to_excel(xw, sheet_name="Vergleich", index=False)
        c[1].download_button("⬇ Excel", puffer.getvalue(), "depot_analyse.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=P + "dl_xlsx",
                             width="stretch")
    except ImportError:
        c[1].caption("Excel-Export: Paket openpyxl fehlt")
    if c[2].button("📄 PDF-Bericht", key=P + "pdf_knopf", width="stretch"):
        st.session_state[P + "pdf"] = _pdf(h, a, sim, k_vor, k_nach, bew)
    if st.session_state.get(P + "pdf"):
        st.download_button("⬇ PDF herunterladen", st.session_state[P + "pdf"], "depot_analyse.pdf",
                           "application/pdf", key=P + "dl_pdf")


def _pdf(h, a, sim, k_vor, k_nach, bew):
    import depot_analyse_pdf as PDF
    k = a["k"]
    g = D.gesamtanalyse(a["pos"], k, a["empf"], a["warn"])
    kpis = [("Depotwert", D.eur(k["gesamt"])), ("Gesamtrendite", D.pct(k.get("rendite"), 1, True)),
            ("Depot-Score", f'{D.de(k.get("score"), 0)} / 100'), ("Risiko", f'{k.get("risiko")} ({D.pct(k.get("vola"))} p. a.)'),
            ("Dividendenprognose", D.eur(k.get("dividende")) + " p. a."), ("Effektive Positionen", D.de(k.get("eff_n"))),
            ("Größte Position", f'{k["groesste"][0]} ({D.pct(k["groesste"][1])})' if k.get("groesste") else "–"),
            ("Laufende Kosten", D.eur(k.get("kosten")) + " p. a.")]
    empf = [[p["name"], D.ARTEN.get(p["art"]), D.pct(k["gewichte"].get(D.schluessel(p))), D.de(p.get("score"), 0),
             a["empf"][D.schluessel(p)]["kategorie"], a["empf"][D.schluessel(p)]["prio"]]
            for p in a["pos"] if not p.get("ohne_kurs")]
    simu = None
    if sim and sim["trades"]:
        simu = {"trades": [[t["aktion"], t["name"], D.de(t["stueck"], 4), D.eur(t["betrag"], 2), D.eur(t["gebuehr"], 2)]
                           for t in sim["trades"]],
                "vergleich": [[r["kennzahl"], D.de(r["vorher"], 1), D.de(r["nachher"], 1),
                               D.de(r["diff"], 1) if r["diff"] is not None else "-", r["urteil"]]
                              for r in D.vergleich(k_vor, k_nach)],
                "bewertung": bew["antworten"], "fazit": bew["fazit"]}
    return PDF.bericht("Depot-Analyse & Optimierung", _stand_text(h, a), kpis, empf, [w["text"] for w in a["warn"]],
                       g["antworten"], [(x["prio"], x["massnahme"], x["warum"]) for x in g["aktionsplan"]], simu,
                       _grenzen(a))


# ---------------------------------------------------------------- Szenarien
def _szenarien(h, a):
    z = a["z"]
    pr = z["profil"]
    st.caption("Je Szenario: Zielstruktur des Profils angewandt auf deine vorhandenen Werte (keine neuen Käufe), "
               "simuliert mit den heutigen Kursen. Die Spanne ist eine Modellrechnung aus den Renditeannahmen der "
               "Klassen und der Depotschwankung (10 % / 50 % / 90 %) – keine Prognose und keine Garantie.")
    jahre = int(max(pr.get("horizont") or 10, 1))
    zeilen, ergebnisse = [], {}
    szen = dict(D.SZENARIEN)
    szen["individuell"] = {"titel": "Individuell", "text": "Dein Profil unter „Daten & Profil“", "profil": {}}
    for key, sz in szen.items():
        prof = dict(pr, **sz["profil"])
        k0 = D.kennzahlen(a["pos"], z["cash"], prof)
        o = D.optimieren(a["pos"], k0, prof)
        sim = D.simulieren([p for p in a["pos"] if not p.get("ohne_kurs")], o["stueck"], cash=z["cash"])
        k1 = D.kennzahlen(sim["soll"], sim["cash_nachher"], prof)
        m = D.modell_entwicklung(k1, jahre, pr.get("sparrate") or 0.0)
        ergebnisse[key] = (k0, k1, o)
        zeilen.append([f'<b>{_e(sz["titel"])}</b><br><span class="da-m">{_e(sz["text"])}</span>',
                       f'{_score(k0.get("score"))} → {_score(k1.get("score"))}', D.pct(k1.get("vola")),
                       D.de(k1.get("eff_n")), D.eur(k1.get("dividende")), str(len(o["massnahmen"])),
                       (f'{D.eur(m["p10"])} – {D.eur(m["p90"])}<br><span class="da-m">Mitte {D.eur(m["p50"])}</span>'
                        if m else "–")])
    _tabelle([("Szenario", "nm"), ("Depot-Score", "r"), ("Schwankung", "r"), ("Eff. Pos.", "r"), ("Dividende", "r"),
              ("Umschichtungen", "r"), (f"Modell in {jahre} J.", "r")], zeilen)
    st.caption("Der Depot-Score wird je Szenario am jeweiligen Profil gemessen (z. B. Risiko gegen die tragbare "
               "Schwankung des Szenarios).")
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    wahl = c1.selectbox("Szenario im Simulator öffnen", list(szen), format_func=lambda x: szen[x]["titel"],
                        key=P + "szen_sim")
    if c2.button("Im Simulator öffnen", key=P + "szen_oeffnen", width="stretch"):
        _sim_optimieren(a, dict(pr, **szen[wahl]["profil"]), 0.0, f'Szenario „{szen[wahl]["titel"]}“')
        st.session_state[P + "reiter_neu"] = REITER[2]
        st.rerun(scope="fragment")


# ---------------------------------------------------------------- Assistent
def _claude(h, frage, a):
    """Optionale Freitextfrage an Claude (nur mit API-Schluessel in den Secrets und Zustimmung)."""
    import anthropic
    kontext = D.claude_kontext(a["pos"], a["k"], a["empf"], a["z"]["profil"])
    system = ("Du bist ein sachlicher Investment-Assistent in einem privaten Finanz-Dashboard. Antworte auf Deutsch, "
              "knapp und strukturiert. Nutze ausschließlich die mitgelieferten Depotdaten (JSON) – erfinde keine "
              "Kurse, Kennzahlen oder Nachrichten. Trenne klar zwischen Fakten (aus den Daten), Einschätzungen und "
              "Annahmen und kennzeichne sie. Fehlen Daten, sag es. Gib keine Kauf- oder Verkaufsaufforderungen, "
              "sondern Prüfhinweise; erwähne, dass es keine Anlageberatung ist.")
    client = anthropic.Anthropic(api_key=h["anthropic_key"], max_retries=2, timeout=90)
    nachricht = [{"role": "user", "content": f"Depotdaten:\n{json.dumps(kontext, ensure_ascii=False, default=str)}"
                                             f"\n\nFrage: {frage}"}]
    try:            # mit serverseitigem Ersatzmodell bei Ueberlast
        antwort = client.beta.messages.create(
            model=CLAUDE_MODELL, max_tokens=1500, system=system, messages=nachricht,
            betas=["server-side-fallback-2026-06-01"], fallbacks=[{"model": "claude-opus-4-8"}])
    except anthropic.BadRequestError:
        antwort = client.messages.create(model=CLAUDE_MODELL, max_tokens=1500, system=system, messages=nachricht)
    return "".join(b.text for b in antwort.content if getattr(b, "type", "") == "text").strip()


def _assistent(h, a):
    s = st.session_state
    st.caption("Antworten aus deinen echten Depotdaten. Typische Fragen beantwortet die App selbst (regelbasiert, "
               "mit Kennzahlen); Fragen mit Simulation lassen sich direkt im Simulator öffnen.")
    cols = [st.container()] * 2 if B._smartphone() else st.columns(2)
    for i, b in enumerate(BEISPIELE):
        if cols[i % 2].button(b, key=f"{P}bsp_{i}", width="stretch"):
            s[P + "frage"] = b
            s[P + "frage_los"] = True
    with st.form(P + "frage_form", clear_on_submit=False, border=False):
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        c1.text_input("Deine Frage", key=P + "frage", placeholder="z. B. Welche Positionen sind am riskantesten?")
        los = c2.form_submit_button("Fragen", width="stretch")
    if los or s.pop(P + "frage_los", False):
        frage = (s.get(P + "frage") or "").strip()
        if frage:
            r = D.assistent(frage, a["pos"], a["k"], a["empf"], a["z"]["profil"])
            s[P + "antwort"] = {"frage": frage, "r": r, "quelle": "App (regelbasiert)"}
    erg = s.get(P + "antwort")
    if not erg:
        return
    st.markdown(f'<div class="da-chip">Frage</div> {_e(erg["frage"])}', unsafe_allow_html=True)
    r = erg["r"]
    if r:
        st.markdown(f'<div class="da-box"><b>Antwort · {erg["quelle"]}</b>'
                    f'{_e(r["antwort"]).replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        sim = r.get("simulation")
        if sim and st.button("🧪 Im Simulator öffnen", key=P + "ass_sim", type="primary"):
            if sim.get("aenderungen"):
                _sim_reset(a)
                s[P + "soll"].update(sim["aenderungen"])
                s[P + "sim_quelle"] = "Assistent"
                s.pop(P + "opt", None)
            elif sim.get("szenario"):
                _sim_optimieren(a, dict(a["z"]["profil"], **D.SZENARIEN[sim["szenario"]]["profil"]), 0.0,
                                f'Szenario „{D.SZENARIEN[sim["szenario"]]["titel"]}“')
            else:
                _sim_optimieren(a, a["z"]["profil"], sim.get("zusatz") or 0.0)
            s[P + "reiter_neu"] = REITER[2]
            st.rerun(scope="fragment")
        return
    if erg.get("claude"):
        st.markdown(f'<div class="da-box"><b>Antwort · Claude (KI-Einschätzung, keine Anlageberatung)</b>'
                    f'{_e(erg["claude"]).replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        return
    if not h.get("anthropic_key"):
        st.info("Diese Frage kann die App nicht aus den Kennzahlen beantworten. Freitextfragen an eine KI (Claude) "
                "sind möglich, sobald ein Anthropic-API-Schlüssel als `ANTHROPIC_API_KEY` in den Streamlit-Secrets "
                "hinterlegt ist (kostenpflichtig, Abrechnung über console.anthropic.com).")
        return
    ok = st.checkbox("Ich bin einverstanden, dass meine Frage und eine Zusammenfassung meines Depots (Namen, "
                     "Gewichte, Werte, Kennzahlen – ohne Benutzername) an Anthropic übertragen werden.",
                     key=P + "claude_ok")
    if st.button("An Claude senden", key=P + "claude_los", disabled=not ok):
        try:
            with st.spinner("Claude antwortet …"):
                erg["claude"] = _claude(h, erg["frage"], a)
            st.rerun(scope="fragment")
        except Exception as e:
            logging.warning(f"Depot-Analyse: Claude-Anfrage fehlgeschlagen: {type(e).__name__}")
            st.error(f"Die KI-Anfrage ist fehlgeschlagen ({type(e).__name__}). Die Analyse der App bleibt verfügbar.")


# ---------------------------------------------------------------- Daten & Profil
def _profil(h, a):
    z = a["z"]
    pr = D.profil_bereinigen(z["profil"])
    with st.form(P + "profil_form", border=False):
        _titel("Anlegerprofil")
        c = _spalten(3)
        risiko = c[0].selectbox("Risikobereitschaft", list(D.PROFILE), index=list(D.PROFILE).index(pr["risiko"]),
                                format_func=lambda x: D.PROFILE[x]["titel"])
        strat = c[1].selectbox("Strategie", list(D.STRATEGIEN), index=list(D.STRATEGIEN).index(pr["strategie"]),
                               format_func=D.STRATEGIEN.get)
        horizont = c[2].number_input("Anlagehorizont (Jahre)", 1, 60, int(pr["horizont"] or 10))
        c = _spalten(3)
        ziel = c[0].number_input("Renditeziel % p. a.", 0.0, 30.0, float(pr["renditeziel"]), step=0.5, format="%.1f")
        spar = c[1].number_input("Sparrate € / Monat", 0.0, 1e6, float(pr["sparrate"]), step=25.0, format="%.0f")
        kapital = c[2].number_input("Verfügbares Kapital €", 0.0, 1e9, float(pr["kapital"]), step=500.0,
                                    format="%.0f")
        c = _spalten(3)
        cash = c[0].number_input("Liquidität (Konto/Verrechnung) €", 0.0, 1e9, float(z["cash"]), step=100.0,
                                 format="%.0f",
                                 help="Die App kennt dein Verrechnungskonto nicht – trage den Betrag hier ein.")
        mg = c[1].number_input("Höchstgewicht je Wert % (0 = laut Profil)", 0.0, 100.0,
                               float(pr["max_gewicht"] or 0.0), step=1.0, format="%.0f")
        gespeichert = st.form_submit_button("💾 Profil speichern", type="primary")
    if gespeichert:
        neu = {"risiko": risiko, "strategie": strat, "horizont": horizont, "renditeziel": ziel, "sparrate": spar,
               "kapital": kapital, "max_gewicht": mg or None}
        ok = _speichern(h, {"profil": neu, "cash": cash})
        st.session_state.pop(P + "soll", None)
        st.session_state[P + "meldung"] = ("Profil gespeichert." if ok else
                                           "Profil für diese Sitzung übernommen (Speicher nicht verfügbar).")
        st.rerun(scope="fragment")
    zs = D.zielstruktur(pr)
    erwartet = sum(zs["ziel"][x] * D.ERWARTUNG.get(x, 2.0) for x in zs["ziel"]) / 100
    st.caption(f"Zielstruktur: {', '.join(f'{D.ARTEN[x]} {v} %' for x, v in zs['ziel'].items())} · Höchstgewicht "
               f"{D.pct(zs['max_gewicht'], 0)} · tragbare Schwankung {D.pct(zs['vola'], 0)} p. a. · Modellrendite der "
               f"Zielstruktur ca. {D.pct(erwartet)} p. a." + (
                   f" – unter deinem Renditeziel von {D.pct(pr['renditeziel'])}: das Ziel ist mit diesem Risikoprofil "
                   "nur mit höherem Risiko erreichbar." if erwartet + 0.05 < pr["renditeziel"] else ""))


def _angaben(h, a):
    z = a["z"]
    _titel("Eigene Angaben je Position")
    st.caption("Für Daten, die in den Quellen fehlen (v. a. TER, Länder/Branchen von ETFs). Leere Felder = aus den "
               "Quellen bzw. unbekannt. Eigene Angaben haben Vorrang und werden als solche gekennzeichnet.")
    pos = [p for p in a["pos"]]
    if not pos:
        return
    def _a(p, feld, zahl=False):
        v = (z["angaben"].get(D.schluessel(p)) or {}).get(feld)
        if zahl:
            return float(v) if D._z(v) is not None else float("nan")
        return str(v) if v else ""

    df = pd.DataFrame([{"Wert": p["name"], "Klasse": D.ARTEN.get(_a(p, "art"), ""), "TER %": _a(p, "ter", True),
                        "Dividende %": _a(p, "div", True), "Land": _a(p, "land"), "Branche": _a(p, "branche"),
                        "Währung": _a(p, "waehrung"), "Teilfreistellung %": _a(p, "tfs", True)} for p in pos])
    klassen = [""] + [D.ARTEN[x] for x in ("aktie", "etf", "wikifolio", "fonds", "sonstiges")]
    ed = st.data_editor(df, key=P + "angaben_ed", hide_index=True, width="stretch", disabled=["Wert"],
                        column_config={"Klasse": st.column_config.SelectboxColumn(options=klassen),
                                       "TER %": st.column_config.NumberColumn(min_value=0.0, max_value=5.0, format="%.2f"),
                                       "Dividende %": st.column_config.NumberColumn(min_value=0.0, max_value=30.0,
                                                                                    format="%.2f"),
                                       "Teilfreistellung %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0,
                                                                                          format="%.0f")})
    if st.button("💾 Angaben speichern", key=P + "angaben_save"):
        rueck = {v: k_ for k_, v in D.ARTEN.items()}
        neu = {}
        for p, (_, r) in zip(pos, ed.iterrows()):
            e = {"art": rueck.get(r["Klasse"]) if r["Klasse"] else None, "ter": D._z(r["TER %"]),
                 "div": D._z(r["Dividende %"]), "land": (r["Land"] or "").strip() or None,
                 "branche": (r["Branche"] or "").strip() or None, "waehrung": (r["Währung"] or "").strip().upper() or None,
                 "tfs": D._z(r["Teilfreistellung %"])}
            e = {k_: v for k_, v in e.items() if v is not None}
            if e:
                neu[D.schluessel(p)] = e
        ok = _speichern(h, {"angaben": neu})
        st.session_state[P + "meldung"] = "Angaben gespeichert." if ok else "Für diese Sitzung übernommen."
        st.rerun(scope="fragment")


def _import(h, a):
    s = st.session_state
    _titel("Depot importieren (CSV / Excel)")
    st.caption("Spalten: Name, ISIN oder WKN, Stück, Kaufkurs (oder Einstand), Kaufdatum. Der Import bildet ein "
               "eigenes Analyse-Depot – dein gespeichertes Depot bleibt unverändert. Kurse kommen aus der "
               "Kursquelle (ls-tc.de).")
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    f = c1.file_uploader("Datei", type=["csv", "xlsx"], key=P + "imp_datei")
    c2.download_button("CSV-Vorlage", D.CSV_VORLAGE.encode("utf-8-sig"), "depot_vorlage.csv", "text/csv",
                       key=P + "imp_vorlage", width="stretch")
    if f is not None and s.get(P + "imp_name") != f.name + str(f.size):
        try:
            if f.name.lower().endswith(".xlsx"):
                df = pd.read_excel(f, dtype=str)
            else:
                text = f.getvalue().decode("utf-8-sig", "replace")
                df = pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str)
            zeilen, fehler = D.import_zeilen(df.to_dict("records"))
        except Exception as e:
            zeilen, fehler = [], [f"Datei nicht lesbar: {type(e).__name__}"]
        aufgeloest = []
        with st.spinner("Suche Kursquellen …"):
            for z_ in zeilen[:40]:
                tr = h["suche_instrument"](z_["kennung"] or z_["name"]) or []
                t = tr[0] if tr else None
                kurs = vortag = None
                hist = None
                if t:
                    kurs, vortag, _ = h["get_live_kurs"](int(t["instrument_id"]))
                    if kurs:
                        hist = h["get_kurshistorie"](int(t["instrument_id"]),
                                                     datetime.date.today() - datetime.timedelta(days=420),
                                                     datetime.date.today())
                p = {"name": (t or {}).get("name") or z_["name"], "wkn": (t or {}).get("wkn") or z_["kennung"],
                     "isin": (t or {}).get("isin") or (z_["kennung"] if len(z_["kennung"]) == 12 else ""),
                     "instrument_id": int(t["instrument_id"]) if t else None, "stueck": z_["stueck"],
                     "kurs": kurs, "vortag": vortag, "wert": (kurs or 0) * z_["stueck"], "einstand": z_["einstand"],
                     "kaufkurs": z_["kaufkurs"], "kaufdatum": z_["kaufdatum"], "hist": hist,
                     "ist_wikifolio": "wikifolio" in str((t or {}).get("kategorie") or "").lower(),
                     "ohne_kurs": not kurs}
                aufgeloest.append(p)
        if len(zeilen) > 40:
            fehler.append(f"Nur die ersten 40 von {len(zeilen)} Positionen übernommen")
        s[P + "import_pos"] = aufgeloest
        s[P + "imp_fehler"] = fehler
        s[P + "imp_name"] = f.name + str(f.size)
        s[P + "quelle"] = "import"
        s.pop(P + "soll", None)
        st.rerun(scope="fragment")
    imp = s.get(P + "import_pos") or []
    for x in s.get(P + "imp_fehler") or []:
        st.caption("⚠️ " + x)
    if not imp:
        return
    st.radio("Analysegrundlage", ["depot", "import"], key=P + "quelle", horizontal=True,
             format_func={"depot": "Mein Depot", "import": f"Importiertes Depot ({len(imp)} Positionen)"}.get,
             on_change=lambda: s.pop(P + "soll", None))
    _tabelle([("Position", "nm"), ("Stück", "r"), ("Kurs", "r"), ("Kursquelle", "")],
             [[_e(p["name"]), D.de(p["stueck"], 4), D.eur(p["kurs"], 2) if p["kurs"] else "–",
               "✓ gefunden" if p["kurs"] else '<span class="da-warn">nicht gefunden – nicht bewertet</span>']
              for p in imp], breit=False)
    with st.expander("In mein Depot übernehmen"):
        uebernehmbar = [p for p in imp if p["instrument_id"] and p["kurs"] and p.get("kaufkurs") and p.get("kaufdatum")]
        st.caption(f"{len(uebernehmbar)} von {len(imp)} Positionen haben Kursquelle, Kaufkurs und Kaufdatum und "
                   "können als neue Positionen angelegt werden. Vorhandene Positionen werden nicht verändert oder "
                   "gelöscht. Danach sind sie unter „Depot verwalten“ bearbeitbar.")
        ok = st.checkbox("Ja, diese Positionen dauerhaft in meinem Depot anlegen.", key=P + "imp_ok")
        if st.button("Positionen anlegen", key=P + "imp_los", disabled=not (ok and uebernehmbar)):
            import uuid
            neu = [{"id": f"pos-{uuid.uuid4().hex[:12]}", "name": p["name"], "wkn": p["wkn"] or p["isin"],
                    "instrument_id": p["instrument_id"], "kaufdatum": p["kaufdatum"].isoformat(),
                    "kaufkurs": float(p["kaufkurs"]), "startkapital": float(p["kaufkurs"]) * float(p["stueck"])}
                   for p in uebernehmbar]
            if h["aendere_positionen"](lambda l: l + neu, "positionen importiert [skip ci]"):
                st.success(f"{len(neu)} Positionen angelegt. Nach dem Neuladen der Seite sind sie Teil deines Depots.")
                s[P + "imp_ok"] = False
            else:
                st.error("Speichern fehlgeschlagen – es wurde nichts angelegt.")


def _grenzen(a):
    m = a["markt"]
    return [f"Kurse: ls-tc.de (Live/Tagesschluss); Kurshistorie 420 Tage je Position.",
            f"Aktien-Kennzahlen und Qualitäts-Score: Qualitäts-Agent (Geschäftszahlen von Yahoo Finance), Stand "
            f"{_datum_de(m.get('stand_q')) if m.get('stand_q') else 'unbekannt'}. Banken/Versicherer und Werte außerhalb des Agenten-Universums haben "
            "keinen Qualitäts-Score.",
            f"ETF-/wikifolio-Score: Top-500-Katalog (Kursentwicklung, Schwankung, Drawdown), Stand "
            f"{_datum_de(m.get('stand_k')) if m.get('stand_k') else 'unbekannt'}.",
            "Nicht verfügbar (nie geschätzt): TER, ETF-Zusammensetzung (Länder, Branchen, Einzeltitel), "
            "Broker-Anbindung. ETF-Überschneidungen werden über die Index-Familie im Namen erkannt.",
            "Depotschwankung aus den Einzelschwankungen mit Korrelationsannahmen je Klasse (wie Investment-Scanner).",
            "Steuern: Abgeltungsteuer + Soli (+ KiSt), Teilfreistellung 30 % für Aktien-ETFs, Durchschnittseinstand; "
            "keine Vorabpauschale, kein Altbestand, keine Quellensteuer.",
            "Modellrechnungen nutzen Renditeannahmen je Klasse (Aktie 7 %, ETF 6,5 %, wikifolio 5 %, Liquidität 2 % "
            "p. a.) – keine Prognose.",
            "Überwachung: Bei jedem Öffnen dieser Ansicht werden neue relevante Hinweise erkannt und höchstens einmal "
            "je Woche in die Chronik geschrieben; einen Hintergrunddienst gibt es nicht."]


def _daten(h, a):
    m = st.session_state.pop(P + "meldung", None)
    if m:
        st.success(m)
    with st.container(border=True):
        _profil(h, a)
    with st.container(border=True):
        _angaben(h, a)
    with st.container(border=True):
        _import(h, a)
    with st.container(border=True):
        _titel("Datenquellen, Zeitstempel & Grenzen")
        st.markdown("\n".join(f"- {_e(x)}" for x in _grenzen(a)))
        z = a["z"]
        if z.get("stand_zeit"):
            st.caption(f"Letzter gespeicherter Analyse-Stand: {_zeit_de(z['stand_zeit'])}")
        st.caption("Eine direkte Broker-Anbindung gibt es nicht. Positionen pflegst du unter „🛠️ Depot verwalten“ "
                   "oder importierst sie hier als CSV/Excel; die Kurse aktualisiert die App bei jedem Laden.")


def _zeit_de(x):
    try:
        return datetime.datetime.fromisoformat(str(x)).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(x)


def _datum_de(x):
    try:
        return datetime.date.fromisoformat(str(x)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(x)


def _stand_text(h, a):
    return " · ".join(x for x in (
        f"Kurse: {h.get('kurs_stand')}" if h.get("kurs_stand") else None,
        f"Qualitätsdaten {_datum_de(a['markt'].get('stand_q'))}" if a["markt"].get("stand_q") else None,
        f"Top-500-Katalog {_datum_de(a['markt'].get('stand_k'))}" if a["markt"].get("stand_k") else None,
        "Analyse-Depot aus Import" if a["importiert"] else None,
        f"Erstellt {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}") if x)


# ---------------------------------------------------------------- Seite
def seite(h):
    with st.container(key="da_seite"):
        _seite(h)


def _seite(h):
    st.markdown(B.CSS, unsafe_allow_html=True)
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="pb-kopf"><div class="pb-titel">Depot-Analyse <span>&amp; Optimierung</span></div>'
                '<div class="pb-unter">Bewertung · Empfehlungen · Simulator · Szenarien · Assistent</div></div>',
                unsafe_allow_html=True)
    a = _analyse(h)
    st.markdown(f'<span class="da-chip">{_e(_stand_text(h, a))}</span>'
                + ('<span class="da-chip warn">Analyse-Depot aus Import</span>' if a["importiert"] else ""),
                unsafe_allow_html=True)
    if st.session_state.get(P + "lesefehler"):
        st.warning("Deine gespeicherten Analyse-Einstellungen sind gerade nicht lesbar – es wird nichts überschrieben.")
    if not [p for p in a["pos"] if not p.get("ohne_kurs")] and not a["importiert"]:
        st.info("Dein Depot enthält noch keine Position mit Kurs. Lege Positionen unter „🛠️ Depot verwalten“ an "
                "oder importiere eine CSV/Excel-Datei unter „⚙️ Daten & Profil“.")
    neu = _ueberwachung(h, a)
    if neu:
        st.markdown(f'<div class="da-box warn"><b>🔔 {len(neu)} neue Hinweise seit der letzten Prüfung</b>'
                    + "<br>".join(_e(w["text"]) for w in neu[:5]) + ' <span class="da-m">(auch in der Chronik)</span>'
                    '</div>', unsafe_allow_html=True)
    if st.session_state.get(P + "reiter_neu"):
        st.session_state[P + "reiter"] = st.session_state.pop(P + "reiter_neu")
    st.session_state.setdefault(P + "reiter", REITER[0])
    reiter = st.pills("Bereich", REITER, key=P + "reiter", label_visibility="collapsed") or REITER[0]
    {REITER[0]: _uebersicht, REITER[1]: _positionen, REITER[2]: _simulator, REITER[3]: _szenarien,
     REITER[4]: _assistent, REITER[5]: _daten}[reiter](h, a)
    st.caption("Keine Anlageberatung. Scores und Empfehlungen sind regelbasierte Auswertungen der genannten Daten; "
               "„prüfen“ bedeutet: genauer ansehen. Prognosen sind Modellrechnungen ohne Garantie.")
