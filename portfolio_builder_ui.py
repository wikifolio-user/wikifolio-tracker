"""Portfolio Builder 2.0 - eine Seite: Kennzahlen, Eingaben, Aufteilung, Diagramme.

Rechnen: portfolio_builder.py (ohne Streamlit). Hier nur Eingabe und Darstellung.
Jede Aenderung wirkt sofort (kein Berechnen-Knopf); gespeichert wird je Benutzer per Knopf.
"""
import copy
import datetime
import html
import json

import pandas as pd
import streamlit as st

import portfolio_builder as P

try:
    import nutzerdaten as N
except Exception:        # pragma: no cover - ohne nutzerdaten.py: gemeinsamer Pfad
    N = None

PFAD = "state/portfolio_builder.json"
FELDER = ("anfangskapital", "sonstiges_kapital", "kredit_summe", "kredit_zins_pa", "kredit_rate",
          "einzahlung", "entnahme", "ausgaben", "laufzeit", "laufzeit_einheit", "rendite_pa", "nur_ganze_stuecke",
          "zielvermoegen", "auto_ziel")
# Tabellenspalten <-> Felder des Rechenkerns
SPALTEN = {"Name": "name", "Art": "art", "Rendite % p. a.": "rendite", "Kurs €": "kurs", "Gewicht %": "gewicht",
           "Betrag €": "betrag", "Stück": "stueck",
           "Wert €": "wert"}
FARBEN = ["#16C784", "#4C9AFF", "#F5B942", "#A78BFA", "#22D3EE", "#F472B6", "#FB923C", "#94A3B8",
          "#84CC16", "#E879F9"]

CSS = """
<style>
.pb-kopf { display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin:2px 0 12px; }
.pb-titel { font-size:1.35rem; font-weight:800; color:var(--text,#E9EBEF); letter-spacing:.2px; }
.pb-titel span { color:var(--up,#16C784); }
.pb-unter { font-size:.8rem; color:var(--label,#AAB1BE); }
.pb-kpis { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; margin:0 0 16px; }
@media (max-width: 819px) { .pb-kpis { grid-template-columns:repeat(2, minmax(0,1fr)); gap:10px; } }
.pb-kpi { background:linear-gradient(180deg, rgba(255,255,255,.045), rgba(255,255,255,.015));
          border:1px solid var(--line,#21252C); border-radius:16px; padding:14px 16px; min-width:0; }
.pb-kpi .l { font-size:.8rem; color:var(--label,#AAB1BE); font-weight:600; letter-spacing:.3px; }
.pb-kpi .w { font-size:clamp(1.15rem, 4.6vw, 1.7rem); font-weight:800; color:var(--text,#E9EBEF);
             font-variant-numeric:tabular-nums; margin-top:4px; overflow-wrap:anywhere; line-height:1.15; }
.pb-kpi .s { font-size:.8rem; color:var(--muted,#7C8493); margin-top:4px; }
.pb-kpi.gut .w { color:var(--up,#16C784); } .pb-kpi.schlecht .w { color:var(--down,#EA3943); }
.pb-karte-t { font-size:.8rem; letter-spacing:1.3px; text-transform:uppercase; font-weight:800;
              color:var(--text,#E9EBEF); margin:2px 0 8px; }
.pb-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px 16px; }
@media (max-width: 819px) { .pb-grid { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.pb-grid div { display:flex; flex-direction:column; padding:8px 0; border-bottom:1px solid var(--line,#21252C); min-width:0; }
.pb-grid .l { font-size:.8rem; color:var(--label,#AAB1BE); }
.pb-grid .w { font-size:1rem; font-weight:700; color:var(--text,#E9EBEF); font-variant-numeric:tabular-nums; }
.pb-grid .w.gut { color:var(--up,#16C784); } .pb-grid .w.schlecht { color:var(--down,#EA3943); }
.pb-status { display:inline-block; font-size:.8rem; font-weight:700; padding:3px 10px; border-radius:999px; }
.pb-status.ok { background:rgba(22,199,132,.14); color:#16C784; border:1px solid rgba(22,199,132,.4); }
.pb-status.warn { background:rgba(245,185,66,.14); color:#F5B942; border:1px solid rgba(245,185,66,.4); }
.pb-tab { display:table; width:100%; border-collapse:collapse; font-size:.85rem; font-variant-numeric:tabular-nums; }
.pb-tab th { text-align:right; color:var(--label,#AAB1BE); font-weight:600; font-size:.8rem; padding:6px 8px;
             border-bottom:1px solid var(--line,#21252C); white-space:nowrap; }
.pb-tab td { text-align:right; padding:7px 8px; border-bottom:1px solid var(--line,#21252C); color:var(--text,#E9EBEF);
             white-space:nowrap; }
.pb-tab th:first-child, .pb-tab td:first-child { text-align:left; white-space:normal; }
.pb-tab tr.summe td { font-weight:800; border-bottom:none; }
.pb-tab i { display:inline-block; width:9px; height:9px; border-radius:3px; margin-right:7px; }
.pb-wrap { overflow-x:auto; }
@media (max-width: 480px) { .pb-tab .kurs { display:none; } }
.pb-hinweis { font-size:.8rem; color:var(--label,#AAB1BE); line-height:1.45; }
/* Eingabereihen: Desktop 4 nebeneinander, Handy 2 */
@media (max-width: 819px) {
  [class*="st-key-pb_reihe"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; gap:.6rem !important; }
  [class*="st-key-pb_reihe"] [data-testid="stColumn"] { flex:0 1 calc(50% - .3rem) !important;
      min-width:calc(50% - .3rem) !important; width:calc(50% - .3rem) !important; }
  .st-key-pb_reihe_add [data-testid="stColumn"]:first-child { flex:1 1 100% !important; min-width:100% !important;
      width:100% !important; }
  .st-key-pb_reihe3 [data-testid="stColumn"]:nth-child(3) { flex:1 1 100% !important; min-width:100% !important;
      width:100% !important; }
  /* Plus/Minus bei Eurobetraegen auf dem Handy aus - sie nehmen dem Betrag den Platz */
  [class*="st-key-pb_reihe"] [data-testid="stNumberInputStepDown"],
  [class*="st-key-pb_reihe"] [data-testid="stNumberInputStepUp"] { display:none !important; }
  .st-key-pb_diagramme [data-testid="stHorizontalBlock"] { flex-direction:column !important; }
  .st-key-pb_diagramme [data-testid="stColumn"] { width:100% !important; min-width:100% !important; flex:1 1 100% !important; }
}
</style>
"""


# ---------------------------------------------------------------- Format
def _de(x, dez=0):
    s = f"{x:,.{dez}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def eur(x, dez=0):
    return ("−" if x < -1e-9 else "") + _de(abs(x), dez) + " €"


def pct(x, dez=1):
    return _de(x, dez) + " %"


def _esc(t):
    return html.escape(str(t))


def _smartphone():
    """True auf Smartphones (User-Agent; iPad meldet sich als Mac)."""
    try:
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:
        return False
    return "iphone" in ua or ("android" in ua and "mobile" in ua) or "ipod" in ua


# ---------------------------------------------------------------- Speichern je Benutzer
def _pfad(h):
    nutzer = (h or {}).get("nutzer")
    return N.pfad(PFAD, nutzer) if N is not None else PFAD


def _laden(h):
    """-> (eingaben oder None, ok). ok=False: gespeicherter Stand gerade nicht lesbar - dann darf
    nicht automatisch gespeichert werden, sonst ueberschriebe der Standard den gespeicherten Stand."""
    try:
        akt = (h or {}).get("gh_aktualisiere")
        if akt:
            ok, d = akt(_pfad(h), lambda d: None, default={}, message="portfolio-builder: lesen [skip ci]")
            if not ok:
                return None, False
        else:
            d = h["gh_read"](_pfad(h), {})
    except Exception:
        return None, False
    return ((d or {}).get("eingaben") if isinstance(d, dict) else None), True


def _speichern(h, e):
    daten = {"eingaben": e, "gespeichert": datetime.datetime.now().isoformat(timespec="minutes")}
    try:
        akt = (h or {}).get("gh_aktualisiere")
        if akt:
            ok, _ = akt(_pfad(h), lambda d: daten, default={}, message="portfolio-builder: speichern [skip ci]")
            return bool(ok)
        return bool(h["gh_write"](_pfad(h), daten, message="portfolio-builder: speichern [skip ci]"))
    except Exception:
        return False


def _fingerabdruck(e):
    return json.dumps(P.bereinigen(e), sort_keys=True)


# ---------------------------------------------------------------- Werte-Katalog & Kurse
PFAD_KATALOG_GROSS = "state/planer/katalog_gross_{}.json"     # vom Watchlist-Agenten (top50_agent.py)
KATALOG_GROSS_TEILE = 4
ART_FILTER = {"Alle": None, "Aktien": "aktie", "ETFs & ETPs": "etf", "Wikifolios": "wikifolio"}
SUCHE = "__suche__"


def _art_aus(typ, kategorie=""):
    t = f"{typ} {kategorie}".lower()
    if "krypto" in t or "crypto" in t:
        return "krypto"
    if "wikifolio" in t:
        return "wikifolio"
    if "aktie" in t or "stock" in t or "share" in t:
        return "aktie"
    if any(w in t for w in ("etf", "etp", "etc", "etn", "fonds", "fund", "index")):
        return "etf"
    return "sonstig"


def _katalog(h):
    """Auswahl zum Hinzufuegen: alle Werte der Watchlist (mit Tageskurs in EUR) + Planer-Katalog.
    -> [{name, wkn, isin, art, kurs}] ohne Doppelte; je Sitzung und Tag gemerkt."""
    heute = datetime.date.today().isoformat()
    gemerkt = st.session_state.get("pb_katalog")
    if gemerkt and gemerkt[0] == heute:
        return gemerkt[1]
    werte, gesehen = [], set()

    def neu(name, wkn, isin, art, kurs, **kennz):
        # derselbe Wert kommt aus beiden Quellen teils nur mit WKN, teils mit ISIN - jede Kennung zaehlt
        schluessel = {k.upper() for k in (wkn, isin) if k} | {"N:" + name.strip().lower()}
        if not name or schluessel & gesehen:
            return
        gesehen.update(schluessel)
        werte.append(dict({"name": name, "wkn": wkn or "", "isin": isin or "", "art": art,
                           "kurs": kurs if isinstance(kurs, (int, float)) and kurs > 0 else None}, **kennz))

    lies = (h or {}).get("gh_read_taeglich")
    for i in range(KATALOG_GROSS_TEILE if lies else 0):
        try:
            d = lies(PFAD_KATALOG_GROSS.format(i), None) or {}
        except Exception:
            d = {}
        felder = d.get("felder") or []
        for z in d.get("zeilen") or []:
            w = dict(zip(felder, z))
            kennung = str(w.get("kennung") or "")
            neu(str(w.get("name") or ""), kennung if _ist_wkn(kennung) else "", str(w.get("isin") or ""),
                _art_aus(w.get("typ"), w.get("kat")), w.get("kurs"),
                **{k: w.get(k) for k in ("1J", "3J", "5J", "10J", "vola", "maxdd", "jahre")})
    try:
        import planer_daten as D
        for k in D.KATALOG:
            neu(k["name"], k.get("wkn") or "", k.get("isin") or "",
                "krypto" if k.get("category") == "crypto" else _art_aus(k.get("typ")), None)
    except Exception:
        pass
    werte.sort(key=lambda w: w["name"].lower())
    st.session_state["pb_katalog"] = (heute, werte)
    return werte


def _ist_wkn(k):
    return len(k) == 6 and k.isalnum() and any(c.isdigit() for c in k)


def _instrument(h, kennungen, name=""):
    """Kurs-ID ueber die Suche der Kursquelle (WKN, sonst ISIN, sonst Name). -> Treffer oder None"""
    suche = (h or {}).get("suche_instrument")
    if not suche:
        return None
    for begriff in [k for k in kennungen if k] + ([name] if name else []):
        treffer = suche(begriff) or []
        for t in treffer:
            if begriff.upper() in (str(t.get("wkn") or "").upper(), str(t.get("isin") or "").upper()):
                return t
        if treffer:
            return treffer[0]
    return None


def _live_kurs(h, instrument_id):
    hole = (h or {}).get("get_live_kurs")
    if not hole or not instrument_id:
        return None
    try:
        akt, vor, _ = hole(int(instrument_id))
    except Exception:
        return None
    kurs = akt if akt else vor
    return float(kurs) if kurs else None


def kurse_aktualisieren(h, nur_fehlende=False):
    """Aktuelle Kurse (ls-tc.de) fuer alle Positionen mit WKN/ISIN/Kurs-ID. Gewichte bleiben,
    Stueckzahlen passen sich an. nur_fehlende: nur Positionen ohne Kurs - die werden notfalls
    ueber ihren Namen gesucht. -> (aktualisiert, ohne_kurs)"""
    pos = copy.deepcopy(st.session_state.get("pb_positionen") or [])
    ok, fehlt = 0, []
    for p in pos:
        if nur_fehlende and p.get("kurs", 0) > 0:
            continue
        if not nur_fehlende and not (p.get("instrument_id") or p.get("wkn") or p.get("isin")):
            continue
        iid = p.get("instrument_id")
        if not iid:
            t = _instrument(h, [p.get("wkn"), p.get("isin")], p["name"] if nur_fehlende else "")
            iid = t and t.get("instrument_id")
        kurs = _live_kurs(h, iid)
        if kurs:
            p["kurs"], p["instrument_id"] = round(kurs, 4), str(iid)
            ok += 1
        else:
            fehlt.append(p["name"])
    st.session_state["pb_positionen"] = pos
    st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
    return ok, fehlt


# ---------------------------------------------------------------- Zustand
def _in_widgets(e):
    """Eingaben in die Widget-Schluessel schreiben (vor dem Zeichnen der Widgets)."""
    st.session_state["pb_daten"] = copy.deepcopy(e)
    st.session_state["pb_einheit_vorher"] = e["laufzeit_einheit"]
    for k in FELDER:
        st.session_state[f"pb_{k}"] = e[k]
    st.session_state["pb_positionen"] = copy.deepcopy(e["positionen"])
    st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
    st.session_state["pb_add_ver"] = st.session_state.get("pb_add_ver", 0) + 1   # Vorschlaege neu


def _widgets_wiederherstellen():
    """Streamlit raeumt die Werte von Eingabefeldern weg, sobald eine andere Ansicht offen war
    (die Felder wurden dann nicht gezeichnet). Fehlende Feldwerte kommen aus der eigenen Kopie
    pb_daten zurueck - sonst stuenden nach dem Zurueckwechseln alle Eingaben auf 0."""
    daten = st.session_state.get("pb_daten") or {}
    for k in FELDER:
        if f"pb_{k}" not in st.session_state and k in daten:
            st.session_state[f"pb_{k}"] = daten[k]


def _aus_widgets():
    e = {k: st.session_state.get(f"pb_{k}") for k in FELDER}
    e["positionen"] = st.session_state.get("pb_positionen") or []
    e = P.bereinigen(e)
    st.session_state["pb_daten"] = copy.deepcopy(e)
    return e


def _start(h):
    konto = str((h or {}).get("nutzer") or "")
    if st.session_state.get("pb_konto") != konto or "pb_daten" not in st.session_state:
        gespeichert, ok = _laden(h)
        e = P.bereinigen(gespeichert) if gespeichert else P.standard()
        _in_widgets(e)
        st.session_state["pb_konto"] = konto
        st.session_state["pb_lesefehler"] = not ok
        st.session_state["pb_gespeichert"] = _fingerabdruck(e)       # Ausgangsstand = nichts zu speichern
    _widgets_wiederherstellen()


def _standard_laden():
    _in_widgets(P.standard())


def _einheit_wechseln():
    """Jahre <-> Monate: Laufzeit umrechnen, damit derselbe Zeitraum bleibt."""
    alt = st.session_state.get("pb_einheit_vorher", "Jahre")
    neu = st.session_state.get("pb_laufzeit_einheit")
    if neu not in ("Jahre", "Monate"):              # Auswahl abgewaehlt: bei der bisherigen bleiben
        neu = st.session_state["pb_laufzeit_einheit"] = alt
    n = int(st.session_state.get("pb_laufzeit") or 1)
    if alt == "Jahre" and neu == "Monate":
        st.session_state["pb_laufzeit"] = min(n * 12, P.MAX_MONATE)
    elif alt == "Monate" and neu == "Jahre":
        st.session_state["pb_laufzeit"] = max(round(n / 12), 1)
    st.session_state["pb_einheit_vorher"] = neu


def _rate_uebernehmen(rate):
    st.session_state["pb_kredit_rate"] = round(rate, 2)


def _rebalancing(h, e, methode):
    """Alle Werte neu berechnen: fehlende Kurse holen, dann neu gewichten (zusammen 100 %)."""
    fehlt = []
    if any(p.get("kurs", 0) <= 0 for p in e["positionen"]):
        with st.spinner("Hole fehlende Kurse …"):
            _, fehlt = kurse_aktualisieren(h, nur_fehlende=True)
    e = dict(e, positionen=st.session_state.get("pb_positionen") or e["positionen"])
    st.session_state["pb_positionen"] = P.rebalancing(e, methode)
    st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
    st.session_state["pb_meldung_rebal"] = fehlt


# ---------------------------------------------------------------- Bausteine der Seite
def _kpis(r):
    e = r["eingaben"]
    netto = r["netto_endvermoegen"]
    jahre = r["monate"] / 12
    lz = f"{_de(jahre, 0 if r['monate'] % 12 == 0 else 1)} J." if r["monate"] >= 12 else f"{r['monate']} Mon."
    karten = [
        ("Startkapital", eur(r["eigenkapital"]),
         f"+ Kredit {eur(e['kredit_summe'])}" if e["kredit_summe"] > 0 else "Eigenkapital", ""),
        ("Portfoliowert", eur(r["portfoliowert"]),
         f"davon investiert {eur(r['positionen']['investiert'])}", ""),
        ("Monatlicher Cashflow", ("+" if r["cashflow_monat"] > 1e-9 else "") + eur(r["cashflow_monat"]),
         "Einzahlung − Entnahme − Kosten − Rate", "gut" if r["cashflow_monat"] > 1e-9 else
         ("schlecht" if r["cashflow_monat"] < -1e-9 else "")),
        (f"Endwert nach {lz}", eur(r["endwert"]),
         (f"Ziel {eur(e['zielvermoegen'])} {'✓' if netto >= e['zielvermoegen'] - 1 else '✗'}"
          if e["zielvermoegen"] > 0 else
          f"netto {eur(netto)}" if r["restschuld"] > 0.005 or e["kredit_summe"] > 0 else "Simulation"),
         "gut" if netto >= r["eigenkapital"] else "schlecht"),
    ]
    st.markdown('<div class="pb-kpis">' + "".join(
        f'<div class="pb-kpi {k}"><div class="l">{_esc(l)}</div><div class="w">{_esc(w)}</div>'
        f'<div class="s">{_esc(s)}</div></div>' for l, w, s, k in karten) + "</div>", unsafe_allow_html=True)


def _eingaben():
    """Eingabefelder in festen Reihen; vertical_alignment="bottom" haelt die Felder auf einer Linie,
    auch wenn ein Label umbricht (Handy: 2 je Reihe)."""
    with st.container(border=True):
        st.markdown('<div class="pb-karte-t">Kapital &amp; Finanzierung</div>', unsafe_allow_html=True)
        with st.container(key="pb_reihe1"):
            c = st.columns(4, vertical_alignment="bottom")
            c[0].number_input("Anfangskapital €", 0.0, P.MAX_KAPITAL, step=1000.0, format="%.0f",
                              key="pb_anfangskapital")
            c[1].number_input("Sonstiges Kapital €", 0.0, P.MAX_KAPITAL, step=1000.0, format="%.0f",
                              key="pb_sonstiges_kapital",
                              help="Zusätzlich verfügbares Kapital, z. B. Bonus oder Erbe – wird mit angelegt.")
            c[2].number_input("Einzahlung €/Monat", 0.0, P.MAX_MONATLICH, step=50.0, format="%.0f",
                              key="pb_einzahlung")
            c[3].number_input("Entnahme €/Monat", 0.0, P.MAX_MONATLICH, step=50.0, format="%.0f", key="pb_entnahme")
        with st.container(key="pb_reihe2"):
            c = st.columns(4, vertical_alignment="bottom")
            c[0].number_input("Ausgaben €/Monat", 0.0, P.MAX_MONATLICH, step=10.0, format="%.0f", key="pb_ausgaben",
                              help="Laufende Kosten und Gebühren (Depot, Sparplan, Beratung …).")
            c[1].number_input("Rendite % p. a.", -P.MAX_RENDITE, P.MAX_RENDITE, step=0.5, format="%.1f",
                              key="pb_rendite_pa",
                              help="Erwartete Rendite für Positionen ohne eigene Rendite und für nicht investiertes "
                                   "Geld. Eigene Werte je Position in der Spalte „Rendite % p. a.“ der Aufteilung.")
            einheit = st.session_state.get("pb_laufzeit_einheit") or "Jahre"
            c[2].number_input(f"Laufzeit ({einheit})", 1, P.MAX_MONATE if einheit == "Monate" else P.MAX_MONATE // 12,
                              step=1, key="pb_laufzeit")
            c[3].segmented_control("Laufzeit in", ["Jahre", "Monate"], key="pb_laufzeit_einheit",
                                   on_change=_einheit_wechseln)
        with st.container(key="pb_reihe3"):
            c = st.columns([1, 1, 2], vertical_alignment="bottom")
            c[0].number_input("Zielvermögen €", 0.0, P.MAX_KAPITAL, step=10000.0, format="%.0f",
                              key="pb_zielvermoegen",
                              help="Netto-Vermögen am Ende der Laufzeit (nach Abzug von Kreditschulden). 0 = kein Ziel.")
            c[1].toggle("Automatisch aufs Ziel", key="pb_auto_ziel",
                        help="Gewichte automatisch: verteilt die Prozente so, dass die Portfolio-Rendite genau die fürs Ziel nötige "
                             "Rendite ergibt – Beträge und Stücke rechnen sich daraus.")
            ziel_spalte = c[2]
        with st.container(key="pb_reihe4"):
            c = st.columns(4, vertical_alignment="bottom")
            c[0].number_input("Kredit €", 0.0, P.MAX_KAPITAL, step=1000.0, format="%.0f", key="pb_kredit_summe",
                              help="Wird mit angelegt und als Schuld wieder abgezogen – zählt also nicht doppelt.")
            c[1].number_input("Kreditzins % p. a.", 0.0, P.MAX_KREDITZINS, step=0.1, format="%.2f",
                              key="pb_kredit_zins_pa")
            c[2].number_input("Kreditrate €/Monat", 0.0, P.MAX_MONATLICH, step=50.0, format="%.2f",
                              key="pb_kredit_rate", help="Zins + Tilgung. Wird aus dem monatlichen Cashflow bezahlt.")
            return c[3], ziel_spalte


def _ziel_hinweis(spalte, r, z):
    """Benoetigte Rendite und Ergebnis der automatischen Verteilung."""
    e = r["eingaben"]
    if e["zielvermoegen"] <= 0:
        spalte.markdown('<div class="pb-hinweis">Ziel eintragen – dann rechnet die App die nötige Rendite und '
                        'auf Wunsch die Verteilung.</div>', unsafe_allow_html=True)
        return
    b = P.benoetigte_rendite(e)
    if not b:
        return
    txt = f"Nötig: {pct(b['rendite'], 2)} p. a." if b["erreichbar"] else f"Nötig: über {pct(P.MAX_RENDITE, 0)} p. a."
    txt += f" · Portfolio: {pct(r['rendite_pa'], 2)} p. a."
    ok = r["netto_endvermoegen"] >= e["zielvermoegen"] - 1
    spalte.markdown(f'<div class="pb-hinweis" style="margin-bottom:6px"><span class="pb-status {"ok" if ok else "warn"}">'
                    f'{"✓ Ziel erreicht" if ok else "Ziel verfehlt"}</span><br>{_esc(txt)}</div>',
                    unsafe_allow_html=True)
    if z and e["auto_ziel"]:
        if z["status"] == "zu_hoch":
            st.warning(f"Mit diesen Werten ist das Ziel nicht erreichbar: selbst der renditestärkste Wert bringt "
                       f"nur {pct(z['spanne'][1], 2)} p. a., nötig wären {pct(z['benoetigt'], 2)}. Deine Aufteilung "
                       "bleibt deshalb wie sie ist – Werte mit höherer Rendite hinzufügen, Laufzeit/Einzahlung "
                       "erhöhen oder das Ziel senken.")
        elif z["status"] == "uebertroffen":
            st.info(f"Das Ziel wird schon übertroffen – nötig wären nur {pct(z['benoetigt'], 2)} p. a., schon der "
                    f"renditeschwächste Wert bringt {pct(z['spanne'][0], 2)}. Deine Aufteilung bleibt deshalb wie "
                    "sie ist; neue Werte bekommen automatisch einen Anteil.")
        elif z["status"] == "leer":
            st.info("Für die automatische Verteilung erst Werte hinzufügen.")


def _kredit_hinweis(spalte, r):
    e = r["eingaben"]
    if e["kredit_summe"] <= 0:
        return
    k = r["kredit"]
    with spalte:
        st.caption(f"Für Tilgung in der Laufzeit: {eur(k['rate_volltilgung'], 2)}/Monat")
        st.button("Rate übernehmen", key="pb_rate_btn", on_click=_rate_uebernehmen, args=(k["rate_volltilgung"],),
                  width="stretch")
    if k["rate_zu_klein"]:
        st.warning("Die Kreditrate deckt nicht einmal die Zinsen – die Schuld wächst.")
    elif r["restschuld"] > 0.005:
        st.info(f"Am Ende der Laufzeit bleibt eine Restschuld von {eur(r['restschuld'])}.")


def _hinzufuegen(h, r):
    """Aktie, ETF oder Wikifolio aus dem Katalog (oder per Suche) als Position anlegen -
    mit Kurs und dem bis 100 % freien Gewicht als Vorschlag."""
    e = r["eingaben"]
    ver = st.session_state.get("pb_add_ver", 0)
    with st.container(border=True, key="pb_add"):
        st.markdown('<div class="pb-karte-t">➕ Wert hinzufügen</div>', unsafe_allow_html=True)
        art_wahl = st.segmented_control("Art", list(ART_FILTER), default="Alle", key="pb_add_art",
                                        label_visibility="collapsed") or "Alle"
        art = ART_FILTER[art_wahl]
        einzeln, top = st.tabs(["Einzeln auswählen", "🏆 Top 100"])
        with top:
            _top100(h, e, art, art_wahl)
        with einzeln:
            _einzeln(h, e, art, ver)
        meldung = st.session_state.pop("pb_meldung", None)
        if meldung:
            st.success(meldung)


def _einzeln(h, e, art, ver):
    """Einen Wert aus dem Katalog (oder per Suche) anlegen."""
    katalog = [w for w in _katalog(h) if art is None or w["art"] == art]
    optionen = list(range(len(katalog))) + [SUCHE]

    def beschriftung(i):
        if i == SUCHE:
            return "🔎 Nicht dabei? Name, WKN oder ISIN suchen …"
        w = katalog[i]
        teile = [w["name"], w["wkn"] or w["isin"]]
        if w["kurs"]:
            teile.append(eur(w["kurs"], 2))
        return " · ".join(t for t in teile if t)

    with st.container(key="pb_reihe_add"):
        c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
        wahl = c1.selectbox(f"Wert ({len(katalog)} zur Auswahl)", optionen, index=None, format_func=beschriftung,
                            placeholder="Name oder WKN eintippen …", key=f"pb_add_wahl_{ver}")
        frei = P.rest_gewicht(e["positionen"])
        vorschlag = frei if frei > 0.05 else 100.0 / (len(e["positionen"]) + 1)
        gewicht = c2.number_input("Gewicht %", 0.0, 100.0, value=round(vorschlag, 2),
                                  step=1.0, format="%.1f", key=f"pb_add_gew_{ver}",
                                  help="Vorschlag: der bis 100 % noch freie Anteil – ist nichts mehr frei, ein "
                                       "gleicher Anteil. Die übrigen Werte werden dann automatisch anteilig "
                                       "gekürzt (zusammen 100 %). 0 = automatisch.")
        treffer = None
        if wahl == SUCHE:
            begriff = st.text_input("Name, WKN oder ISIN", key=f"pb_add_such_{ver}",
                                    placeholder="z. B. Siemens, 723610, LS9…").strip()
            liste = ((h or {}).get("suche_instrument") or (lambda _: []))(begriff)[:12] if len(begriff) >= 2 else []
            if begriff and len(begriff) >= 2 and not liste:
                st.caption("Keine Treffer – andere Schreibweise oder WKN/ISIN versuchen.")
            if liste:
                treffer = st.selectbox(
                    "Treffer", liste, key=f"pb_add_treffer_{ver}",
                    format_func=lambda t: " · ".join(x for x in (t.get("name"), t.get("wkn") or t.get("isin"),
                                                                  t.get("kategorie")) if x))
        bereit = (wahl is not None and wahl != SUCHE) or treffer is not None
        if c3.button("Hinzufügen", key=f"pb_add_btn_{ver}", disabled=not bereit, type="primary",
                     width="stretch"):
            if treffer is not None:
                name, wkn, isin = treffer.get("name"), treffer.get("wkn"), treffer.get("isin")
                neu_art, iid = _art_aus(treffer.get("kategorie"), name), treffer.get("instrument_id")
                kurs, rendite = _live_kurs(h, iid), None
            else:
                w = katalog[wahl]
                name, wkn, isin, neu_art, kurs, iid = w["name"], w["wkn"], w["isin"], w["art"], w["kurs"], None
                rendite = P.katalog_rendite(w)          # Vorschlag: bisherige Rendite p. a. (5 J., sonst 3 J.)
                if not kurs:
                    t = _instrument(h, [wkn, isin])
                    iid = t and t.get("instrument_id")
                    kurs = _live_kurs(h, iid)
            pos, ok = P.position_hinzufuegen(e["positionen"], name, kurs or 0.0, gewicht, neu_art, rendite, wkn=wkn,
                                             isin=isin, instrument_id=iid)
            if not ok:
                st.warning(f"„{name}“ ist schon im Portfolio.")
            else:
                st.session_state["pb_positionen"] = pos
                st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
                st.session_state["pb_add_ver"] = ver + 1
                anteil = pos[-1]["gewicht"]
                st.session_state["pb_meldung"] = (
                    f"„{name}“ hinzugefügt ({pct(anteil)})"
                    + (" – die übrigen Werte wurden anteilig angepasst" if frei < anteil - 0.05 else "")
                    + ("" if kurs else " – Kurs bitte in der Tabelle eintragen, dann rechnen sich die Stücke"))
                st.rerun()


def _top100(h, e, art, art_wahl):
    """Rangliste der besten 100 Werte (Watchlist-Katalog) - Zeilen anhaken und uebernehmen."""
    alle = _katalog(h)
    kriterium = st.session_state.get("pb_top_krit") or next(iter(P.KRITERIEN))
    liste = P.rangliste(alle, kriterium, art)
    st.selectbox(f"Top {len(liste)} · {art_wahl} · sortiert nach", list(P.KRITERIEN), key="pb_top_krit",
                 format_func=lambda k: f"{k} – {P.KRITERIEN[k]}")
    if not liste:
        st.info("Für die Rangliste fehlen Kennzahlen – sie kommen mit dem nächsten Lauf des Watchlist-Agenten.")
        return
    df = pd.DataFrame([{"#": x["rang"], "Name": x["name"], "Art": P.ARTEN.get(x["art"], "Sonstiges"),
                        "Kurs €": x.get("kurs"), "1J %": x.get("1J"), "3J p.a. %": x.get("3J p.a."),
                        "5J p.a. %": x.get("5J p.a."), "Rendite/Risiko": x.get("Rendite/Risiko"),
                        "Vola %": x.get("vola"), "Max DD %": x.get("maxdd")}
                       for x in liste])
    zahl = {c: st.column_config.NumberColumn(c, format="localized", width="small")
            for c in ("Kurs €", "1J %", "3J p.a. %", "5J p.a. %", "Rendite/Risiko", "Vola %", "Max DD %")}
    spalte = {"5J p.a.": "5J p.a. %", "3J p.a.": "3J p.a. %", "1J": "1J %"}.get(kriterium, kriterium)
    # Handy: die Spalte, nach der sortiert wird, direkt neben dem Namen
    reihenfolge = (["#", "Name", spalte] + [c for c in ("5J p.a. %", "1J %", "Art", "Kurs €") if c != spalte]
                   if _smartphone() else list(df.columns))
    auswahl = st.dataframe(
        df.round(2), key=f"pb_top_tab_{kriterium}_{art_wahl}_{st.session_state.get('pb_add_ver', 0)}",
        hide_index=True, width="stretch", height=420, on_select="rerun", selection_mode="multi-row",
        column_order=reihenfolge,
        column_config=dict(zahl, **{"#": st.column_config.NumberColumn("#", width=36),
                                     "Name": st.column_config.TextColumn(
                                         "Name", width=130 if _smartphone() else "medium")}))
    zeilen = list(getattr(getattr(auswahl, "selection", None), "rows", []) or [])
    rest = P.rest_gewicht(e["positionen"])
    verteilt = (f"der freie Rest von {pct(rest)} wird gleichmäßig auf die neuen Werte verteilt" if rest > 0.05 else
                "jeder neue Wert bekommt einen gleichen Anteil, die übrigen werden anteilig gekürzt")
    st.markdown(f'<div class="pb-hinweis">Zeilen anhaken (Kästchen links) – {verteilt}. '
                f'Vergangene Renditen sind keine Prognose.</div>', unsafe_allow_html=True)
    if st.button(f"➕ {len(zeilen)} ausgewählte hinzufügen" if zeilen else "➕ Ausgewählte hinzufügen",
                 key="pb_top_btn", type="primary", disabled=not zeilen, width="stretch"):
        werte = [liste[i] for i in zeilen if 0 <= i < len(liste)]
        pos, anzahl, schon = P.mehrere_hinzufuegen(e["positionen"], werte)
        st.session_state["pb_positionen"] = pos
        st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
        st.session_state["pb_add_ver"] = st.session_state.get("pb_add_ver", 0) + 1
        st.session_state["pb_meldung"] = (
            f"{anzahl} Wert{'e' if anzahl != 1 else ''} hinzugefügt"
            + (f" mit je {pct(pos[-1]['gewicht'])}" if anzahl else "")
            + (" – die übrigen Werte wurden anteilig angepasst" if anzahl and rest < 0.05 else "")
            + (f" · schon vorhanden: {', '.join(schon[:3])}" if schon else ""))
        st.rerun()


def _tabelle(h, r):
    """Editierbare Aufteilung. Gespeichert wird je Position nur das Gewicht; Betrag/Stueck
    werden daraus gerechnet. Aenderungen (st.data_editor-Delta) -> Gewichte -> neu zeichnen."""
    e, pos = r["eingaben"], r["positionen"]
    with st.container(border=True):
        summe = pos["summe_gewicht"]
        ok = abs(summe - 100.0) < 0.05
        st.markdown('<div class="pb-karte-t">Portfolio-Aufteilung</div>', unsafe_allow_html=True)
        arten = [p.get("art", "sonstig") for p in e["positionen"]]
        # ohne eigene Angabe gilt die allgemeine Rendite - die steht dann auch in der Zelle (statt "None")
        renditen = [round(P.position_rendite(e, p), 2) for p in e["positionen"]]
        df = pd.DataFrame([{"Name": z["name"], "Art": P.ARTEN[a_], "Rendite % p. a.": rd, "Kurs €": z["kurs"],
                            "Gewicht %": round(z["gewicht"], 4),
                            "Betrag €": round(z["betrag"], 2), "Stück": round(z["stueck"], 4),
                            "Wert €": round(z["wert"], 2)} for z, a_, rd in zip(pos["zeilen"], arten, renditen)],
                          columns=list(SPALTEN))
        key = f"pb_tab_{st.session_state.get('pb_tab_ver', 0)}"
        # Handy: die Spalten zum Eintippen zuerst, "Wert" steht in der Positionstabelle darunter
        reihenfolge = (["Name", "Gewicht %", "Betrag €", "Stück", "Rendite % p. a.", "Kurs €", "Art"]
                       if _smartphone() else list(SPALTEN))
        auto = e["auto_ziel"] and e["zielvermoegen"] > 0
        st.data_editor(
            df, key=key, num_rows="dynamic", hide_index=True, width="stretch", column_order=reihenfolge,
            # automatische Verteilung: Prozente/Betrag/Stueck kommen aus dem Ziel, nicht von Hand
            disabled=["Wert €"] + (["Gewicht %", "Betrag €", "Stück"] if auto else []),
            column_config={
                "Name": st.column_config.TextColumn("Name", width=110 if _smartphone() else "medium",
                                                    required=True),
                "Art": st.column_config.SelectboxColumn("Art", options=list(P.ARTEN.values()), width="small",
                                                        default=P.ARTEN["sonstig"]),
                "Rendite % p. a.": st.column_config.NumberColumn(
                    "Rendite % p. a.", min_value=-P.MAX_RENDITE, max_value=P.MAX_RENDITE, format="localized",
                    step=0.1, width="small",
                    help="Erwartete Rendite dieses Werts (Vorschlag aus der bisherigen 5-J.-Rendite). Ohne eigene "
                         "Angabe gilt die allgemeine Rendite oben; Zelle leeren = wieder die allgemeine."),
                "Kurs €": st.column_config.NumberColumn("Kurs €", min_value=0.0, format="localized", step=0.01,
                                                        width="small"),
                "Gewicht %": st.column_config.NumberColumn("Gewicht %", min_value=0.0, max_value=100.0,
                                                           format="localized", step=0.1, width="small"),
                "Betrag €": st.column_config.NumberColumn("Betrag €", min_value=0.0, format="localized", step=1.0,
                                                          width="small"),
                "Stück": st.column_config.NumberColumn("Stück", min_value=0.0, format="localized",
                                                       step=1.0 if e["nur_ganze_stuecke"] else 0.0001, width="small"),
                "Wert €": st.column_config.NumberColumn("Wert €", format="localized", width="small"),
            })
        delta = st.session_state.get(key) or {}
        art_key = {v: k for k, v in P.ARTEN.items()}

        def feld(c, v):
            return art_key.get(v, "sonstig") if c == "Art" else v

        geaendert = {i: {SPALTEN[c]: feld(c, v) for c, v in w.items() if c in SPALTEN}
                     for i, w in (delta.get("edited_rows") or {}).items()}
        neu = [{SPALTEN[c]: feld(c, v) for c, v in w.items() if c in SPALTEN} for w in (delta.get("added_rows") or [])]
        weg = delta.get("deleted_rows") or []
        if any(geaendert.values()) or weg or any(neu):
            st.session_state["pb_positionen"] = P.aenderungen_anwenden(e["positionen"], pos["kapital"],
                                                                       geaendert, neu, weg)
            st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
            st.rerun()
        # Rebalancing: alle neuen und bestehenden Werte in einem Schritt neu berechnen
        null = [p["name"] for p in e["positionen"] if p["gewicht"] <= 1e-9]
        ohne_kurs = [p["name"] for p in e["positionen"] if p["kurs"] <= 0]
        if null or ohne_kurs or not ok:
            offen = ([f"{len(null)} Wert{'e' if len(null) != 1 else ''} mit 0 % ({', '.join(null[:3])})"]
                     if null else []) + ([f"{len(ohne_kurs)} ohne Kurs ({', '.join(ohne_kurs[:3])})"]
                                         if ohne_kurs else []) + ([] if ok else [f"Summe {pct(summe)}"])
            st.markdown(f'<div class="pb-hinweis"><span class="pb-status warn">Noch nicht eingerechnet</span> '
                        f'{_esc(" · ".join(offen))} – „⚖️ Rebalancing“ berechnet alle Werte neu.</div>',
                        unsafe_allow_html=True)
        with st.container(key="pb_reihe_rebal"):
            # Handy: Auswahl und Knopf untereinander (nebeneinander waere die Auswahl unlesbar schmal)
            r1, r2 = (st.container(), st.container()) if _smartphone() else st.columns([2, 1],
                                                                                    vertical_alignment="bottom")
            # "Automatisch aufs Ziel" verteilt ohnehin selbst - dort nur diese Methode
            methoden = ["ziel"] if auto else [m for m in P.REBALANCING if m != "ziel" or e["zielvermoegen"] > 0]
            methode = r1.selectbox("Rebalancing", methoden, format_func=P.REBALANCING.get,
                                   key=f"pb_rebal_{int(auto)}",
                                   help="Wie die Prozente neu verteilt werden (zusammen 100 %):\n\n"
                                        "- **Gewichte behalten, 0 % ergänzen**: die Verhältnisse bleiben, Werte mit "
                                        "0 % bekommen den durchschnittlichen Anteil\n"
                                        "- **Alle gleich gewichten**: jeder Wert gleich viel\n"
                                        "- **Aufs Zielvermögen**: nach erwarteter Rendite, so dass das Ziel erreicht "
                                        "wird\n\nFehlende Kurse werden vorher geholt; Betrag und Stück rechnen sich "
                                        "danach aus Kapital und Kurs.")
            if r2.button("⚖️ Rebalancing", key="pb_rebal_btn", type="primary", width="stretch",
                         disabled=not e["positionen"]):
                _rebalancing(h, e, methode)
                st.rerun()
        gemeldet = st.session_state.pop("pb_meldung_rebal", None)
        if gemeldet is not None:
            st.toast("⚖️ Alle Werte neu berechnet – zusammen 100 %"
                     + (f" · ohne Kurs (bitte eintragen): {', '.join(gemeldet[:3])}" if gemeldet else ""))
        c1, c3 = st.columns([1, 1], vertical_alignment="center")
        c1.toggle("Nur ganze Stücke", key="pb_nur_ganze_stuecke",
                  help="Stückzahlen abrunden; der Rest bleibt als Cash im Portfolio.")
        mit_kennung = any(p.get("wkn") or p.get("isin") or p.get("instrument_id") for p in e["positionen"])
        if c3.button("🔄 Kurse aktualisieren", key="pb_kurse_btn", width="stretch", disabled=not mit_kennung,
                     help="Aktuelle Kurse (ls-tc.de) für alle Werte mit WKN/ISIN – die Gewichte bleiben, "
                          "die Stückzahlen passen sich an."):
            with st.spinner("Lade Kurse …"):
                anzahl, fehlt = kurse_aktualisieren(h)
            st.session_state["pb_meldung_kurse"] = (anzahl, fehlt)
            st.rerun()
        gemeldet = st.session_state.pop("pb_meldung_kurse", None)
        if gemeldet:
            anzahl, fehlt = gemeldet
            st.toast(f"{anzahl} Kurs{'e' if anzahl != 1 else ''} aktualisiert"
                     + (f" · ohne Kurs: {', '.join(fehlt[:3])}" if fehlt else ""))
        texte = (["🎯 Prozente, Beträge und Stücke werden aufs Zielvermögen berechnet – Rendite je Position "
                  "oder das Ziel ändern."] if auto else
                 ["Prozent, Betrag oder Stück ändern – die anderen Werte rechnen sich sofort mit."])
        if pos["cash"] > 0.005:
            texte.append(f"Nicht investiert (Cash): {eur(pos['cash'], 2)}.")
        ohne_rendite = [p["name"] for p in e["positionen"] if p.get("rendite") is None and not p.get("allgemein")]
        if ohne_rendite:
            texte.append(f"Ohne Renditedaten (es gilt die allgemeine Rendite {pct(e['rendite_pa'], 2)}): "
                         f"{', '.join(ohne_rendite[:4])} – eigene erwartete Rendite in der Tabelle eintragen.")
        if pos["kapital"] <= 0:
            texte.append("Ohne Kapital lassen sich Betrag und Stück nicht umrechnen – erst Kapital eintragen.")
        # Summe unter der Tabelle - ueber ihr liegt beim Antippen die Werkzeugleiste der Tabelle
        st.markdown(f'<div class="pb-hinweis"><span class="pb-status {"ok" if ok else "warn"}">Summe {pct(summe)}'
                    f'{"" if ok else " – Ziel 100 %"}</span> {_esc(" ".join(texte))}</div>', unsafe_allow_html=True)


def _diagramme(r):
    import plotly.graph_objects as go
    pos = r["positionen"]
    namen = [z["name"] for z in pos["zeilen"] if z["wert"] > 0.005]
    werte = [z["wert"] for z in pos["zeilen"] if z["wert"] > 0.005]
    farben = [FARBEN[i % len(FARBEN)] for i, z in enumerate(pos["zeilen"]) if z["wert"] > 0.005]
    if pos["cash"] > 0.005:
        namen.append("Cash (nicht investiert)")
        werte.append(pos["cash"])
        farben.append("#3F4652")
    with st.container(key="pb_diagramme"):
        links, rechts = st.columns([1, 1.6], gap="medium")
        with links, st.container(border=True):
            st.markdown('<div class="pb-karte-t">Verteilung</div>', unsafe_allow_html=True)
            if werte:
                fig = go.Figure(go.Pie(
                    labels=namen, values=werte, hole=0.62, sort=False, marker=dict(colors=farben, line=dict(width=0)),
                    textinfo="none", customdata=[eur(w) for w in werte],
                    hovertemplate="%{label}<br>%{customdata} · %{percent}<extra></extra>"))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", height=300, margin=dict(l=0, r=0, t=0, b=0), separators=",.",
                    showlegend=True, font=dict(color="#D6D9DE", size=12),
                    legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center", font=dict(size=12)),
                    annotations=[dict(text=f"<b>{eur(r['portfoliowert'])}</b><br><span style='font-size:12px'>"
                                           f"Portfoliowert</span>", showarrow=False, font=dict(size=15,
                                                                                               color="#E9EBEF"))])
                st.plotly_chart(fig, width="stretch", key="pb_donut", config={"displayModeBar": False})
            else:
                st.caption("Noch keine Positionen mit Wert.")
        with rechts, st.container(border=True):
            st.markdown('<div class="pb-karte-t">Vermögensentwicklung</div>', unsafe_allow_html=True)
            heute = datetime.date.today().replace(day=1)
            v = r["verlauf"]
            x = [_monat_plus(heute, z["monat"]) for z in v]
            fig = go.Figure()
            hat_kredit = r["eingaben"]["kredit_summe"] > 0
            reihen = [("Portfolio", "portfolio", "#16C784")]
            if hat_kredit:
                reihen += [("Schulden", "schulden", "#EA3943"), ("Netto (Portfolio − Schulden)", "netto", "#E9EBEF")]
            for name, feld, farbe in reihen:
                fig.add_trace(go.Scatter(
                    x=x, y=[z[feld] for z in v], name=name, mode="lines", line=dict(color=farbe, width=2.4),
                    customdata=[eur(z[feld]) for z in v], hovertemplate=f"{name}: %{{customdata}}<extra></extra>",
                    fill="tozeroy" if feld == "portfolio" else None,
                    fillcolor="rgba(22,199,132,0.10)" if feld == "portfolio" else None))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=300, separators=",.",
                margin=dict(l=4, r=4, t=8, b=4), font=dict(color="#D6D9DE", size=12), hovermode="x unified",
                showlegend=hat_kredit,
                legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(size=12)),
                xaxis=dict(showgrid=False, tickformat="%Y"),
                yaxis=dict(gridcolor="#1E2228", tickformat=",.0f", ticksuffix=" €", side="right", zeroline=False))
            st.plotly_chart(fig, width="stretch", key="pb_linie", config={"displayModeBar": False})


def _monat_plus(d, n):
    m = d.month - 1 + n
    return datetime.date(d.year + m // 12, m % 12 + 1, 1)


def _positionen_tabelle(r):
    pos = r["positionen"]
    zeilen = []
    for i, z in enumerate(pos["zeilen"]):
        stueck = _de(z["stueck"], 0 if r["eingaben"]["nur_ganze_stuecke"] or z["stueck"] >= 1000 else 2)
        zeilen.append(f'<tr><td><i style="background:{FARBEN[i % len(FARBEN)]}"></i>{_esc(z["name"])}</td>'
                      f'<td>{pct(z["anteil"])}</td><td>{stueck}</td><td class="kurs">{eur(z["kurs"], 2)}</td>'
                      f'<td>{eur(z["wert"])}</td></tr>')
    if pos["cash"] > 0.005:
        zeilen.append(f'<tr><td><i style="background:#3F4652"></i>Cash (nicht investiert)</td>'
                      f'<td>{pct(pos["cash"] / pos["kapital"] * 100 if pos["kapital"] else 0)}</td>'
                      f'<td>–</td><td class="kurs">–</td><td>{eur(pos["cash"])}</td></tr>')
    summe_wert = pos["investiert"] + pos["cash"]
    summe_anteil = summe_wert / pos["kapital"] * 100 if pos["kapital"] else 0.0
    ueber = summe_anteil > 100.05                 # Gewichte > 100 %: mehr verplant als Kapital da ist
    zeilen.append(f'<tr class="summe"><td>Summe</td><td{" style=color:#F5B942" if ueber else ""}>{pct(summe_anteil)}'
                  f'</td><td></td><td class="kurs"></td><td>{eur(summe_wert)}</td></tr>')
    anteile = P.anteile_nach_art(r["eingaben"])
    namen = dict(P.ARTEN, cash="Cash")
    nach_art = " · ".join(f"{namen.get(k, k)} {pct(v)}" for k, v in sorted(anteile.items(), key=lambda x: -x[1]))
    with st.container(border=True):
        st.markdown('<div class="pb-karte-t">Positionen</div>'
                    '<div class="pb-wrap" tabindex="0" role="region" aria-label="Positionen (seitlich scrollbar)">'
                    '<table class="pb-tab"><thead><tr><th>Position</th><th>Anteil</th><th>Stück</th><th class="kurs">Kurs</th>'
                    '<th>Wert</th></tr></thead><tbody>' + "".join(zeilen) + "</tbody></table></div>",
                    unsafe_allow_html=True)
        if nach_art:
            st.markdown(f'<div class="pb-hinweis" style="margin-top:8px">Nach Art: {_esc(nach_art)}</div>',
                        unsafe_allow_html=True)


def _ergebnis(r):
    s, e = r["summen"], r["eingaben"]
    gewinn = s["rendite"]
    werte = [
        ("Verfügbares Anlagekapital", eur(r["anlagekapital"]), ""),
        ("Monatlicher Netto-Cashflow", eur(r["cashflow_monat"], 2),
         "gut" if r["cashflow_monat"] > 1e-9 else ("schlecht" if r["cashflow_monat"] < -1e-9 else "")),
        ("Prognostizierter Endwert", eur(r["endwert"]), ""),
        ("Portfolio-Rendite", pct(r["rendite_pa"], 2) + " p. a.", ""),
        ("Verbleibende Kreditschulden", eur(r["restschuld"]), "schlecht" if r["restschuld"] > 0.005 else ""),
        ("Nettoendvermögen", eur(r["netto_endvermoegen"]),
         "gut" if r["netto_endvermoegen"] >= r["eigenkapital"] else "schlecht"),
        ("Ertrag aus Rendite", eur(gewinn), "gut" if gewinn > 0 else ("schlecht" if gewinn < 0 else "")),
        ("Einzahlungen gesamt", eur(s["einzahlung"]), ""),
        ("Entnahmen + Ausgaben", eur(s["entnahme"] + s["ausgaben"]), ""),
        ("Kreditzinsen gesamt", eur(s["zinsen"]), ""),
    ]
    with st.container(border=True):
        st.markdown('<div class="pb-karte-t">Ergebnis</div><div class="pb-grid">' + "".join(
            f'<div><span class="l">{_esc(l)}</span><span class="w {k}">{_esc(w)}</span></div>' for l, w, k in werte)
            + "</div>", unsafe_allow_html=True)
        if s["fehlbetrag"] > 0.005:
            st.warning(f"Das Portfolio reicht nicht für alle Auszahlungen: insgesamt fehlen {eur(s['fehlbetrag'])}. "
                       "Es wurde bei 0 gehalten – der Rest müsste von außen kommen.")
        with st.expander("ℹ️ So wird gerechnet"):
            st.markdown(
                f"""<div class="pb-hinweis">
<b>Anlagekapital</b> = Anfangskapital + sonstiges Kapital + Kredit = {eur(r['anlagekapital'])}.
Der Kredit wird mit angelegt und als Schuld wieder abgezogen – er zählt nicht doppelt.<br>
<b>Je Monat</b>: 1) Kreditzinsen = Restschuld × {pct(e['kredit_zins_pa'], 2)} / 12, gezahlt wird die Rate
(zuletzt nur der Rest). 2) Netto-Cashflow = Einzahlung − Entnahme − Ausgaben − Kreditrate.
3) Portfolio = Portfolio × (1 + r) + Cashflow mit r = (1 + {pct(e['rendite_pa'], 2)})^(1/12) − 1.
Unter 0 fällt das Portfolio nicht; fehlende Beträge werden als Fehlbetrag ausgewiesen.<br>
<b>Nettoendvermögen</b> = Endwert − Restschuld. Szenariorechnung mit gleichbleibender Rendite – keine Prognose
und keine Anlageempfehlung.</div>""", unsafe_allow_html=True)


def _automatisch_speichern(h, e):
    """Jede Aenderung wird sofort im Ordner des Benutzers gespeichert (kein Speichern-Knopf).
    -> ("ok", "HH:MM") | ("unveraendert", zeit) | ("lesefehler", None) | ("fehler", None)"""
    jetzt = _fingerabdruck(e)
    if jetzt == st.session_state.get("pb_gespeichert"):
        return "unveraendert", st.session_state.get("pb_gespeichert_um")
    if st.session_state.get("pb_lesefehler"):
        return "lesefehler", None
    if _speichern(h, e):
        st.session_state["pb_gespeichert"] = jetzt
        st.session_state["pb_gespeichert_um"] = datetime.datetime.now().strftime("%H:%M")
        return "ok", st.session_state["pb_gespeichert_um"]
    return "fehler", None


def _speicherleiste(h, e):
    art, zeit = _automatisch_speichern(h, e)
    text = {"ok": f"✓ Automatisch gespeichert · {zeit} Uhr",
            "unveraendert": f"✓ Gespeichert{f' · {zeit} Uhr' if zeit else ''} – Änderungen werden automatisch "
                            "gespeichert",
            "lesefehler": "⚠ Dein gespeicherter Stand war beim Öffnen nicht lesbar – damit er nicht überschrieben "
                          "wird, wird gerade nicht automatisch gespeichert. Bitte die Seite neu laden.",
            "fehler": "⚠ Speichern gerade nicht möglich (Datenspeicher nicht erreichbar) – wird bei der nächsten "
                      "Änderung erneut versucht."}[art]
    st.markdown(f'<div class="pb-hinweis" style="margin-bottom:6px">{_esc(text)}</div>', unsafe_allow_html=True)
    # Zuruecksetzen ueberschreibt den gespeicherten Stand sofort - deshalb mit Rueckfrage
    if not st.session_state.get("pb_reset_frage"):
        st.button("↺ Standardwerte", key="pb_standard", width="stretch",
                  on_click=lambda: st.session_state.update(pb_reset_frage=True))
    else:
        st.warning("Alle Eingaben und Positionen auf die Standardwerte zurücksetzen? Das wird sofort gespeichert.")
        c1, c2 = st.columns(2)
        c1.button("Ja, zurücksetzen", key="pb_standard_ja", type="primary", width="stretch",
                  on_click=lambda: (_standard_laden(), st.session_state.update(pb_reset_frage=False)))
        c2.button("Abbrechen", key="pb_standard_nein", width="stretch",
                  on_click=lambda: st.session_state.update(pb_reset_frage=False))


# ---------------------------------------------------------------- Seite
def render(h):
    st.markdown(CSS, unsafe_allow_html=True)
    _start(h)
    st.markdown('<div class="pb-kopf"><div class="pb-titel">Portfolio Builder <span>2.0</span></div>'
                '<div class="pb-unter">Alles auf einer Seite · Änderungen wirken sofort</div></div>',
                unsafe_allow_html=True)
    kpi_platz = st.empty()
    kredit_spalte, ziel_spalte = _eingaben()
    e = _aus_widgets()
    if any((p.get("rendite") is None and not p.get("allgemein")) or p["kurs"] <= 0 or p.get("art") == "sonstig"
           for p in e["positionen"]):
        # fehlende Rendite/Kurs/Art (Suche, eigene Zeilen, aeltere Staende) aus dem Katalog vorschlagen
        pos, n = P.renditen_ergaenzen(e["positionen"], _katalog(h))
        if n:
            st.session_state["pb_positionen"] = pos
            st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
            e = _aus_widgets()
    z = None
    if e["auto_ziel"] and e["zielvermoegen"] > 0:
        # Gewichte automatisch: vor der Rechnung, damit Kennzahlen, Tabelle und Diagramme zusammenpassen
        z = P.ziel_gewichte(e)
        if z and z["positionen"] and any(abs(a["gewicht"] - b["gewicht"]) > 1e-6
                                         for a, b in zip(z["positionen"], e["positionen"])):
            st.session_state["pb_positionen"] = z["positionen"]
            st.session_state["pb_tab_ver"] = st.session_state.get("pb_tab_ver", 0) + 1
            e = _aus_widgets()
    r = P.simulation(e)
    _ziel_hinweis(ziel_spalte, r, z)
    _kredit_hinweis(kredit_spalte, r)
    _hinzufuegen(h, r)
    _tabelle(h, r)
    with kpi_platz.container():
        _kpis(r)
    _diagramme(r)
    _positionen_tabelle(r)
    _ergebnis(r)
    _speicherleiste(h, e)
