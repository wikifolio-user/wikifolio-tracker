"""
Portfolio-Planer - OBERFLAECHE (Streamlit).

Wird von app.py als Ansicht "💼 Portfolio-Planer" aufgerufen:
    planer_ui.render(hilfen)
hilfen = {"suche_instrument", "get_kurshistorie", "gh_read", "gh_write",
          "gh_read_taeglich", "heute", "benchmarks",
          "nutzer", "gh_aktualisiere"}  - die vorhandenen Funktionen der App,
damit Kursdaten, Suche und GitHub-Speicher nicht doppelt implementiert werden.
"nutzer" (angemeldeter Benutzer {name, rolle} oder None) legt den Speicherort fest
(nutzerdaten.pfad: Admin/ohne Login wie bisher, sonst state/benutzer/<name>/);
"gh_aktualisiere" (Lesen-Aendern-Schreiben mit Versionspruefung) wird fuer Modelle
und Musterdepots genutzt. Fehlen die Schluessel: Admin-Pfade, gh_read/gh_write.

Aufbau: Rahmen/Methode -> 4 KPI-Karten -> Bereichswahl -> ein Bereich.
Die KPI-Karten werden als Platzhalter angelegt und erst NACH den Eingaben des
Bereichs gefuellt - so zeigen sie immer den aktuellen Stand.

Alle Zahlen: Szenariorechnung, keine Prognose, vor Steuern.
"""
import copy
import datetime
import hashlib
import html
import json
import math
import re
import time
import zlib

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import planer_daten as D
import planer_engine as E
import bewertung as BW
import analyse as AN

try:
    import nutzerdaten as N
except Exception:        # pragma: no cover - ohne nutzerdaten.py: bisherige (gemeinsame) Pfade
    N = None

PFAD_SZENARIEN = "state/planer/szenarien.json"     # je Benutzer ueber nutzerdaten.pfad
PFAD_MUSTERDEPOT = "state/musterdepot.json"        # je Benutzer ueber nutzerdaten.pfad
QUALITAET_DETAIL_TEILE = 32          # wie qualitaet_agent.DETAIL_TEILE
HIST_CACHE_SEK = 6 * 3600

# Navigation: 6 Hauptbereiche in Arbeitsreihenfolge, darunter Unterseiten
HAUPT = ["🧩 Portfolio", "⚖️ Gewichtung", "📈 Ergebnis", "💳 Kredit", "⚠️ Risiko", "🔬 Analyse", "🗂️ Daten"]
UNTER = {
    "🧩 Portfolio": ["Bausteine", "Aufteilung", "Kaufplan"],
    "⚖️ Gewichtung": [],
    "📈 Ergebnis": ["Wachstum", "Ziel", "Szenarien", "Entnahme"],
    "💳 Kredit": [],
    "⚠️ Risiko": ["Konzentration", "Sensitivität", "Stress & Reserve"],
    "🔬 Analyse": ["Aktienkorb", "Wikifolios"],
    "🗂️ Daten": ["Annahmen & Quellen", "Gespeicherte Modelle"],
}
BEREICHE = HAUPT      # Kompatibilitaet

FARBEN = ["#4C9AFF", "#16C784", "#F5B942", "#EA3943", "#A78BFA", "#22D3EE", "#F472B6", "#FB923C",
          "#A3E635", "#94A3B8", "#FDE047", "#2DD4BF", "#C084FC", "#F87171"]

QUELLEN = {"historisch": "Kurshistorie (Ist)", "manualScenario": "Eigene Annahme", "historical5Y": "Historisch 5 J.", "historical10Y": "Historisch 10 J.",
           "fundamentalModel": "Fundamental-Modell", "analystInput": "Analysten-Input", "bear": "Bear",
           "base": "Base", "bull": "Bull", "custom": "Custom",
           "kategorie_standard": "Kategorie-Standard (Historie < 1 Mon.)",
           "hochgerechnet": "Hochgerechnet (Historie < 1 J.)"}

HINWEIS = "Szenariorechnung · keine Prognose · vor Steuern"
PLANER_VERSION = "16.10.2026 · 01:00"     # zur Kontrolle, welche Datei gerade laeuft

CSS = """
<style>
.pl-phase { font-size: 0.8rem; font-weight: 800; letter-spacing: 1.4px; text-transform: uppercase; color: #FFFFFF;
            margin: 14px 0 4px; padding-bottom: 5px; border-bottom: 1px solid rgba(255, 255, 255, 0.25); }
.pl-hinweis { font-size: 0.8rem; color: var(--label, #8A9099); margin: -2px 0 10px 2px;
              letter-spacing: 0.3px; }
.pl-badge { display: inline-block; font-size: 0.8rem; font-weight: 700; padding: 2px 7px;
            border-radius: 999px; margin: 1px 4px 1px 0; white-space: nowrap; }
.pl-warn { background: rgba(245, 185, 66, 0.14); color: #F5B942; border: 1px solid rgba(245, 185, 66, 0.4); }
.pl-info { background: rgba(76, 154, 255, 0.12); color: #8DBBFF; border: 1px solid rgba(76, 154, 255, 0.35); }
.pl-gut { color: #16C784; } .pl-schlecht { color: #EA3943; }
.q-kpi-v span.pl-gut, .q-kpi-v span.pl-schlecht { font-size: inherit; font-weight: 800; }
.q-kpi-v span.pl-gut { color: #16C784; } .q-kpi-v span.pl-schlecht { color: #EA3943; }
.pl-sub { font-size: 0.8rem; color: var(--label, #8A9099); font-weight: 600; }
.pl-zeile { font-size: 0.8rem; color: #D6D9DE; margin: 2px 0 12px 2px; line-height: 1.5; }
.q-kpi-v.pl-klein { font-size: 1.05rem; }
/* ---- Planer: einheitliche Eingabefelder ----
   Auswahlfelder sehen hier aus wie die Zahlenfelder (gleiche Beschriftung, gleiche Hoehe, dezenter
   Rahmen) statt wie Ueberschriften mit leuchtendem Rahmen - so stehen Felder sauber nebeneinander. */
[data-testid="stSelectbox"] label, [data-testid="stSelectbox"] label p,
[data-testid="stMultiSelect"] label p {
    font-family: inherit !important; font-size: 0.875rem !important; font-weight: 400 !important;
    letter-spacing: normal !important; text-transform: none !important; text-shadow: none !important;
    color: rgba(250, 250, 250, 0.85) !important; }
[data-testid="stSelectbox"] label { margin: 0 0 4px 0 !important; }
[data-testid="stSelectbox"] > div, [data-testid="stSelectbox"] [data-baseweb="select"] {
    outline: 1px solid rgba(255, 255, 255, 0.22) !important; box-shadow: none !important; animation: none !important;
    border-radius: 8px !important; }
[data-testid="stSelectbox"] > div:hover, [data-testid="stSelectbox"] > div:focus-within {
    outline-color: rgba(255, 255, 255, 0.6) !important; box-shadow: none !important; }
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div { min-height: 46px !important; }
/* Zeilen mit Eingabefeldern: Felder unten buendig, auch wenn eine Beschriftung zweizeilig ist */
[data-testid="stHorizontalBlock"]:has([data-testid="stNumberInput"], [data-testid="stSelectbox"],
                                      [data-testid="stTextInput"], [data-testid="stDateInput"]) {
    align-items: flex-end; }
/* Handy: Eingabefelder untereinander in voller Breite - Zahlen passen ganz hinein,
   Beschriftungen brechen nicht unterschiedlich um */
@media (max-width: 700px) {
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stNumberInput"],
                                        > [data-testid="stColumn"] [data-testid="stSelectbox"],
                                        > [data-testid="stColumn"] [data-testid="stTextInput"],
                                        > [data-testid="stColumn"] [data-testid="stDateInput"]) {
      flex-direction: column !important; align-items: stretch !important; gap: 0.7rem !important; }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stNumberInput"],
                                        > [data-testid="stColumn"] [data-testid="stSelectbox"],
                                        > [data-testid="stColumn"] [data-testid="stTextInput"],
                                        > [data-testid="stColumn"] [data-testid="stDateInput"]) > [data-testid="stColumn"] {
      width: 100% !important; min-width: 100% !important; flex: 1 1 100% !important; }
}
[data-testid="stNumberInput"] input { min-width: 0; }
.pl-planung-kopf { font-size: 0.95rem; font-weight: 800; color: #FFFFFF; letter-spacing: .3px; margin: 2px 0 2px; }
.st-key-pl_planung { border-radius: 14px !important; }
/* Knoepfe in einer Zeile mit Feldern: gleiche Hoehe wie die Eingabefelder */
.st-key-pl_planung [data-testid="stButton"] button, [data-testid="stHorizontalBlock"] [data-testid="stButton"] button {
    min-height: 42px; }
/* Ergebnis-Kacheln: so viele Spalten wie Platz ist (nie zu schmal), Werte ohne Umbruch */
.q-kpis.pl-kpis { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.pl-kpis .q-kpi { padding: 10px 12px 9px; display: flex; flex-direction: column; gap: 3px; }
.pl-kpis .q-kpi-l { line-height: 1.3; min-height: 1.7em; }
.pl-kpis .q-kpi-v { font-size: clamp(1.05rem, 2.1vw, 1.4rem); white-space: nowrap; overflow: hidden;
                    text-overflow: ellipsis; line-height: 1.25; }
.pl-kpis .pl-sub { font-size: 0.8rem; line-height: 1.35; }
@media (max-width: 700px) { .q-kpis.pl-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                            .pl-kpis .q-kpi-v { font-size: 1.12rem; } }
.pt.ue td.pt-wert.ue-fix { min-width: 110px; max-width: 170px; }
.pl-formhinweis { font-size: 0.8rem; color: #D6D9DE; background: rgba(76, 154, 255, 0.10);
                  border: 1px solid rgba(76, 154, 255, 0.35); border-radius: 8px; padding: 7px 10px; margin: 4px 0 8px; }
/* Formular-Buttons klar beschriftet und farbig statt weisser Flaeche */
[data-testid="stFormSubmitButton"] button {
    background: #16305A !important; border: 1px solid rgba(255, 255, 255, 0.8) !important; min-height: 44px;
    box-shadow: 0 0 6px rgba(255, 255, 255, 0.5), 0 0 16px rgba(255, 255, 255, 0.18) !important;
}
[data-testid="stFormSubmitButton"] button, [data-testid="stFormSubmitButton"] button * {
    color: #FFFFFF !important; font-weight: 700 !important;
}
[data-testid="stColumn"]:nth-child(2) [data-testid="stFormSubmitButton"] button {
    background: #1C1F26 !important; border: 1px solid rgba(255, 255, 255, 0.6) !important;
}
[data-testid="stFormSubmitButton"] button:hover { filter: brightness(1.2); }
@media (max-width: 700px) { .pl-zeile { font-size: 0.84rem; } }
/* Transparente Rangliste (bewertung.py) */
.sc-karte { border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 12px; padding: 10px 12px 8px;
            margin: 0 0 10px; background: rgba(255, 255, 255, 0.03); }
.sc-kopf { display: flex; align-items: center; gap: 8px; }
.sc-platz { font-weight: 900; font-size: 0.95rem; width: 26px; height: 26px; border-radius: 50%;
            display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto;
            background: rgba(255, 255, 255, 0.1); color: #FFFFFF; }
.sc-name { font-weight: 800; color: #FFFFFF; font-size: 0.92rem; flex: 1 1 auto; min-width: 0;
           overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sc-typ { font-size: 0.8rem; color: #8A9099; font-weight: 700; text-transform: uppercase; }
.sc-wert { font-weight: 900; font-size: 1.45rem; line-height: 1; }
.sc-wert small { font-size: 0.8rem; color: #8A9099; font-weight: 700; }
.sc-balken { height: 7px; border-radius: 4px; background: rgba(255, 255, 255, 0.08); margin: 7px 0 8px;
             overflow: hidden; }
.sc-balken > div { height: 100%; border-radius: 4px; }
.sc-gruen { color: #16C784; } .sc-gelb { color: #F5B942; } .sc-rot { color: #EA3943; } .sc-grau { color: #8A9099; }
.sc-bg-gruen { background: #16C784; } .sc-bg-gelb { background: #F5B942; } .sc-bg-rot { background: #EA3943; }
.sc-bg-grau { background: #5A606B; }
.sc-teil { display: grid; grid-template-columns: minmax(0, 9.5em) 1fr 2.2em 3.2em; gap: 6px; align-items: center;
           font-size: 0.8rem; color: #D6D9DE; margin: 2px 0; }
.sc-teil .sc-mini { height: 5px; border-radius: 3px; background: rgba(255, 255, 255, 0.08); overflow: hidden; }
.sc-teil .sc-mini > div { height: 100%; }
.sc-teil .sc-zahl { text-align: right; font-weight: 800; }
.sc-teil .sc-beitrag { text-align: right; color: #8A9099; font-size: 0.8rem; }
.sc-warum { font-size: 0.8rem; color: #D6D9DE; margin: 8px 0 4px; line-height: 1.45; }
.sc-pm { font-size: 0.8rem; line-height: 1.45; margin: 2px 0; }
.sc-pm .sc-plus { color: #9BE8C6; } .sc-pm .sc-minus { color: #F5A3A8; }
.sc-meta { font-size: 0.8rem; color: #8A9099; margin-top: 4px; }
.sc-formel { font-size: 0.8rem; color: #D6D9DE; background: rgba(76, 154, 255, 0.08);
             border: 1px solid rgba(76, 154, 255, 0.3); border-radius: 8px; padding: 6px 10px; margin: 6px 0 10px; }
@media (max-width: 700px) { .sc-teil { grid-template-columns: minmax(0, 7.5em) 1fr 2.2em 3em; } }
.an-box { border-left: 3px solid rgba(76, 154, 255, 0.6); background: rgba(76, 154, 255, 0.05);
          border-radius: 0 10px 10px 0; padding: 7px 10px; margin: 2px 0 10px; }
.an-zeile { font-size: 0.8rem; color: #D6D9DE; line-height: 1.45; margin: 3px 0; }
.an-zeile b { color: #FFFFFF; }
.an-tag { display: inline-block; font-size: 0.8rem; font-weight: 800; padding: 1px 6px; border-radius: 999px;
          margin-right: 5px; letter-spacing: 0.3px; text-transform: uppercase; vertical-align: 1px; }
.an-fakt { background: rgba(22, 199, 132, 0.14); color: #6EE7B7; }
.an-prognose { background: rgba(245, 185, 66, 0.16); color: #F5B942; }
.an-modell { background: rgba(167, 139, 250, 0.16); color: #C4B5FD; }
.an-einschaetzung { background: rgba(76, 154, 255, 0.16); color: #8DBBFF; }
.an-urteil { font-size: 0.95rem; font-weight: 800; color: #FFFFFF; margin: 4px 0 2px; }
</style>
"""


# ===========================================================================
# Formatierung (deutsch, ohne falsche Praezision)
# ===========================================================================
def _de(x, dec=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x, ungefaehr=True):
    if x is None:
        return "–"
    if ungefaehr:
        return f"≈ {_de(E.runden_ungefaehr(x))} €"
    return f"{_de(x)} €"


def _pct(x, dec=1, vorzeichen=False, anteil=True):
    """x als Anteil (0.1 = 10 %) bzw. mit anteil=False bereits in %."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    v = x * 100 if anteil else x
    return (("+" if vorzeichen and v > 0 else "") + _de(v, dec) + " %").replace("-", "−")


def _pct_ziel(x):
    """Benoetigte Rendite: None = Ziel nicht erreichbar."""
    return "nicht erreichbar" if x is None else _pct(x)


def _esc(t):
    return html.escape(str(t))


def _kacheln(eintraege, klein=False, klasse=""):
    zellen = "".join(
        f'<div class="q-kpi"><div class="q-kpi-l">{_esc(l)}</div>'
        f'<div class="q-kpi-v{" pl-klein" if klein else ""}">{v}</div>'
        + (f'<div class="pl-sub">{s}</div>' if s else "") + "</div>"
        for l, v, s in eintraege)
    st.markdown(f'<div class="q-kpis {klasse}">{zellen}</div>', unsafe_allow_html=True)


def _tabelle(kopf, zeilen, links=(0,)):
    """HTML-Tabelle im Stil der App (.pt). Breite Tabellen scrollen am iPhone
    seitlich (.ue-wrap), die erste Spalte bleibt dabei stehen."""
    th = "".join(f'<th class="{"ue-fix" if i == 0 else ""}">{_esc(k)}</th>' for i, k in enumerate(kopf))
    umbruch = ' style="white-space:normal;min-width:220px"'
    body = []
    for n, z in enumerate(zeilen):
        tds = "".join(
            f'<td class="{("pt-wert" if i in links else "pt-num") + (" ue-fix" if i == 0 else "")}"'
            f'{umbruch if (i in links and i) else ""}>{c}</td>'
            for i, c in enumerate(z))
        body.append(f'<tr class="{"pt-zebra" if n % 2 else ""}">{tds}</tr>')
    st.markdown(f'<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt ue"><thead><tr>{th}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)


def _kurz_eur(x):
    """Kompakte Beschriftung: 349.667 -> 350 T€, 96.420.874 -> 96,4 Mio €."""
    a = abs(x)
    if a >= 1e9:
        return f"{_de(x / 1e9, 1)} Mrd €"
    if a >= 1e6:
        return f"{_de(x / 1e6, 1)} Mio €"
    if a >= 1e4:
        return f"{_de(x / 1e3)} T€"
    return f"{_de(x)} €"


def _layout(fig, hoehe=360, y_titel=None, legende=True, eur=True):
    fig.update_layout(
        paper_bgcolor="#000000", plot_bgcolor="#000000", height=hoehe, separators=",.",
        margin=dict(l=8, r=8, t=30 if legende else 10, b=30), font=dict(color="#D6D9DE", size=12),
        showlegend=legende, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(showgrid=True, gridcolor="#1A1A1A", zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#1A1A1A", zeroline=False, title=y_titel,
                   tickformat=",.0f" if eur else None, side="right"),
    )
    return fig


def _chart(fig, key):
    st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False})


def _abschnitt(titel):
    st.markdown(f'<div class="abschnitt">{_esc(titel)}</div>', unsafe_allow_html=True)


def _hinweis(text=HINWEIS):
    st.markdown(f'<div class="pl-hinweis">{_esc(text)}</div>', unsafe_allow_html=True)


# ===========================================================================
# Modell-Zustand
# ===========================================================================
def _k(name):
    """Widget-Key mit Versionszaehler: nach Laden/Normalisieren/Optimieren
    starten alle Eingabefelder mit den Modellwerten neu."""
    return f"pl_{name}_{st.session_state.get('planer_ver', 0)}"


def _neu_zeichnen():
    st.session_state["planer_ver"] = st.session_state.get("planer_ver", 0) + 1


def _migriere(m):
    """Gespeicherte Modelle aelterer Versionen um neue Felder ergaenzen."""
    seed = D.seed_modell()
    m = copy.deepcopy(m)
    for k, v in seed.items():
        m.setdefault(k, v)
    for k, v in seed["rahmen"].items():
        m["rahmen"].setdefault(k, v)
    seed_werte = {x["assetId"]: x["value"] for x in D.SEED_ANNAHMEN if x["sourceType"] == "manualScenario"}
    for x in m["annahmen"]:
        if "auto" not in x and x.get("sourceType") == "manualScenario" and x.get("assetId") != "reserve":
            # unveraenderte Startwerte, leere Annahmen und Katalog-Vorschlaege gelten als automatisch
            x["auto"] = (x.get("value") is None or seed_werte.get(x["assetId"], object()) == x.get("value")
                         or str(x.get("notes", "")).startswith(D.VORSCHLAG["text"]))
    seed_assets = {a["id"]: a for a in seed["assets"]}
    for a in m["assets"]:
        if not a.get("enabled"):
            a["targetWeight"] = 0.0          # inaktive Bausteine haben keinen Anteil
        if a["id"] in seed_assets and not a.get("ticker") and not a.get("isin"):
            a["ticker"], a["isin"] = seed_assets[a["id"]].get("ticker"), seed_assets[a["id"]].get("isin")
        if "fixiert" not in a:
            a["fixiert"] = a["category"] == "cash"
        if "renditequelle" not in a:
            a["renditequelle"] = "historisch" if a["category"] == "wikifolio" else "annahme"
        for k, v in D._asset("x", "x", "cash", 0).items():
            a.setdefault(k, v)
    return m


# ===========================================================================
# Speicherorte je Benutzer (nutzerdaten.pfad): der Admin und die App ohne Login
# nutzen die bisherigen Pfade unveraendert, jeder andere Benutzer seinen Ordner
# state/benutzer/<name>/. Gemeinsame Daten (Katalog, Qualitaet, Kurse) bleiben global.
# ===========================================================================
def _nutzer(h):
    return (h or {}).get("nutzer")


def _eigener_bereich(h):
    return bool(N is not None and N.ist_eigener_bereich(_nutzer(h)))


def _pfad(h, basis):
    return N.pfad(basis, _nutzer(h)) if N is not None else basis


def szenarien_pfad(nutzer=None):
    """Speicherort der Planer-Modelle (inkl. automatisch gespeichertem Stand) fuer diesen Benutzer."""
    return N.pfad(PFAD_SZENARIEN, nutzer) if N is not None else PFAD_SZENARIEN


def musterdepot_pfad(nutzer=None):
    """Speicherort der Musterdepots fuer diesen Benutzer (auch fuer app.py: Menue-Button)."""
    return N.pfad(PFAD_MUSTERDEPOT, nutzer) if N is not None else PFAD_MUSTERDEPOT


def _konto(h):
    """Kennung des Speicherbereichs ("" = Admin / ohne Login)."""
    return (N.ordner(_nutzer(h)) or "") if N is not None else ""


def _lesen(h, pfad, default):
    """-> (daten, ok). ok=False: Datei gerade NICHT lesbar (daten = default) - dann
    darf nichts auf Basis dieser Daten geschrieben werden. Mit gh_aktualisiere wird
    streng gelesen (aendern -> None = nichts schreiben), sonst wie bisher gh_read."""
    akt = (h or {}).get("gh_aktualisiere")
    try:
        if akt:
            ok, daten = akt(pfad, lambda d: None, default=copy.deepcopy(default), message="planer: lesen [skip ci]")
            if not ok:
                return copy.deepcopy(default), False
        else:
            daten = h["gh_read"](pfad, copy.deepcopy(default))
    except Exception:
        return copy.deepcopy(default), False
    return (daten if isinstance(daten, dict) else copy.deepcopy(default)), True


def _aendern_speichern(h, pfad, aendern, message):
    """Sicheres Lesen-Aendern-Schreiben. aendern(daten) -> neue Daten oder None
    (nichts schreiben). Mit gh_aktualisiere (Versionspruefung, nach einem Lesefehler
    wird nichts geschrieben), sonst wie bisher gh_read + gh_write. -> True/False"""
    def _a(d):
        return aendern(d if isinstance(d, dict) else {})
    akt = (h or {}).get("gh_aktualisiere")
    try:
        if akt:
            ok, _ = akt(pfad, _a, default={}, message=message)
            return bool(ok)
        neu = _a(h["gh_read"](pfad, {}) or {})
        return True if neu is None else bool(h["gh_write"](pfad, neu, message=message))
    except Exception:
        return False


def leer_modell():
    """Startmodell eines neuen Benutzers: alle Eingaben 0 - kein Startkapital, keine
    Sparrate, kein Ziel, 0 Jahre, keine Entnahme, keine Kredite. Die Bausteine
    bleiben als Vorlage in der Liste, sind aber inaktiv (0 %)."""
    m = D.seed_modell()
    r = m["rahmen"]
    r["startkapital"] = 0.0
    r["sparrate_monat"] = 0.0
    r["zielvermoegen"] = 0.0
    r["horizont_jahre"] = 0
    e = m["entnahme"]
    e.update({"aktiv": False, "monatlich": 0.0, "dynamik_pa": 0.0, "auto_gewichtung": False, "startbetrag": None,
              "stufen": []})
    for a in m["assets"]:
        a["enabled"] = False
        a["targetWeight"] = 0.0
    m.pop("kredit", None)
    m["kaufplan"] = {"betrag": 0.0, "bruch": False}
    return m


def _start_modell(h):
    """Ausgangsmodell ohne gespeicherten Stand: Admin/ohne Login wie bisher das
    Beispielmodell, jeder andere Benutzer startet mit allen Eingaben auf 0."""
    return leer_modell() if _eigener_bereich(h) else D.seed_modell()


def _lade_gespeichert(h, mit_status=False):
    daten, ok = _lesen(h, _pfad(h, PFAD_SZENARIEN), {})
    daten = daten if isinstance(daten, dict) else {}
    if not isinstance(daten.get("szenarien"), dict):
        daten["szenarien"] = {}
    return (daten, ok) if mit_status else daten


def _norm(x):
    """Zahlen vereinheitlichen (40 und 40.0 gelten als gleich) - sonst loeste
    schon das blosse Oeffnen eines Bereichs eine Speicherung aus."""
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, (int, float)):
        return round(float(x), 6)
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in x.items() if v is not None}     # fehlend == None
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    return str(x)


_AUTO_FELDER = ("value", "notes", "source", "dataDate", "observationYears")


def _hash(m):
    """Fingerabdruck der EINGABEN. Automatisch aus der Kurshistorie nachgefuehrte
    Annahmen (auto=True) zaehlen nur mit ihrem Schalter, nicht mit dem Wert - die
    werden bei jedem Laden neu bestimmt und sind keine Eingabe des Benutzers."""
    x = dict(m)
    x["annahmen"] = [{k: v for k, v in a.items() if k not in _AUTO_FELDER} if a.get("auto") else a
                     for a in (m.get("annahmen") or [])]
    return hashlib.sha1(json.dumps(_norm(x), sort_keys=True).encode()).hexdigest()


def _basis_neu():
    """Gespeichert wird erst bei einer Aenderung: der Stand am Ende des naechsten
    Durchlaufs (nach Ergaenzung fehlender Felder, Annahmen aus der Historie und
    automatischer Gewichtung) gilt als Ausgangsstand."""
    st.session_state["planer_hash"] = None
    st.session_state["planer_basis"] = True


def _modell(h):
    konto = _konto(h)
    if "planer_modell" in st.session_state and st.session_state.get("planer_konto", "") != konto:
        # anderer Benutzer in derselben Sitzung: nichts vom vorigen Modell weiterverwenden
        for k in [k for k in st.session_state if str(k).startswith("planer_") and k != "planer_ver"]:
            st.session_state.pop(k, None)
        _neu_zeichnen()
    if "planer_modell" not in st.session_state:
        daten, ok = _lade_gespeichert(h, mit_status=True)
        eintrag = daten["szenarien"].get(daten.get("aktiv") or "Aktuelles Modell")
        if not isinstance(eintrag, dict) or not isinstance(eintrag.get("modell"), dict):
            eintrag = None
        st.session_state["planer_modell"] = _migriere(eintrag["modell"]) if eintrag else _start_modell(h)
        st.session_state["planer_name"] = (daten.get("aktiv") or "Aktuelles Modell") if eintrag else None
        st.session_state["planer_konto"] = konto
        # Gespeicherter Stand nicht lesbar: NICHT automatisch speichern - sonst wuerde
        # das Startmodell den gespeicherten Stand ueberschreiben
        st.session_state["planer_lesefehler"] = not ok
        st.session_state.setdefault("planer_ver", 0)
        _basis_neu()
    return st.session_state["planer_modell"]


def _auto_speichern(m, h):
    """Automatische Speicherung: jede Aenderung am Modell wird ins aktive
    Szenario geschrieben (Standard "Aktuelles Modell") - im Ordner des Benutzers.
    Lesen-Aendern-Schreiben (gh_aktualisiere), damit andere gespeicherte
    Szenarien erhalten bleiben (z. B. von einem anderen Geraet)."""
    neu = _hash(m)
    if st.session_state.pop("planer_basis", False):
        st.session_state["planer_hash"] = neu          # Ausgangsstand - nichts geaendert
        return st.session_state.get("planer_auto")
    if neu == st.session_state.get("planer_hash"):
        return st.session_state.get("planer_auto")
    name = st.session_state.get("planer_name") or "Aktuelles Modell"
    if st.session_state.get("planer_lesefehler"):
        st.session_state["planer_auto"] = ("lesefehler", name, None)
        return st.session_state["planer_auto"]
    eintrag = {"modell": copy.deepcopy(m), "gespeichert": datetime.datetime.now().isoformat(timespec="minutes")}

    def aendern(daten):
        if not isinstance(daten.get("szenarien"), dict):
            daten["szenarien"] = {}
        daten["szenarien"][name] = eintrag
        daten["aktiv"] = name
        return daten

    ok = _aendern_speichern(h, _pfad(h, PFAD_SZENARIEN), aendern, f"planer: auto {name} [skip ci]")
    if ok:
        st.session_state["planer_hash"] = neu
        st.session_state["planer_name"] = name
        st.session_state["planer_auto"] = ("ok", name, datetime.datetime.now().strftime("%H:%M"))
    else:
        st.session_state["planer_auto"] = ("fehler", name, None)
    return st.session_state["planer_auto"]


def _asset(m, aid):
    return next((a for a in m["assets"] if a["id"] == aid), None)


# ===========================================================================
# Historical Layer (echte Kursdaten, ls-tc.de ueber die App-Funktionen)
# ===========================================================================
def _waehle_treffer(treffer, begriff, wiki):
    b = begriff.strip().lower()
    for t in treffer:
        if b and b in (str(t.get("isin", "")).lower(), str(t.get("wkn", "")).lower()):
            return t
    for t in treffer:
        name = str(t.get("name", "")).lower()
        ist_wiki = str(t.get("wkn", "")).upper().startswith("LS9") or \
            "wiki" in (str(t.get("kategorie", "")) + name).lower()
        if wiki and not ist_wiki:
            continue
        if b and b in name:
            return t
    return None


def _reihen_kennzahlen(s):
    s = s.dropna()
    s = s[s > 0]
    if len(s) < 10:
        return None
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    erst, letzt = s.index[0], s.index[-1]
    jahre = (letzt - erst).days / 365.25
    if jahre <= 0:
        return None

    def cagr(n):
        if jahre < n - 0.05:
            return None
        ref = s[s.index <= letzt - pd.DateOffset(years=n)]
        basis = ref.iloc[-1] if not ref.empty else s.iloc[0]
        return float((s.iloc[-1] / basis) ** (1.0 / n) - 1.0)

    abstand = pd.Series(s.index).diff().dt.days.median() or 1.0
    je_jahr = 365.25 / max(abstand, 1.0) if abstand > 1.5 else 252.0
    log_r = (s / s.shift(1)).dropna().apply(math.log)
    vola = float(log_r.std() * math.sqrt(je_jahr)) if len(log_r) > 5 else None
    maxdd = float((s / s.cummax() - 1.0).min() * 100.0)
    s1 = s[s.index >= letzt - pd.DateOffset(years=1)]
    log1 = (s1 / s1.shift(1)).dropna().apply(math.log)
    vola1 = float(log1.std() * math.sqrt(je_jahr)) if len(log1) > 5 and jahre >= 0.95 else None
    try:
        monat = s.resample("ME").last()
    except Exception:
        monat = s.resample("M").last()
    return {
        "jahre": round(jahre, 2), "start": erst.date().isoformat(), "stand": letzt.date().isoformat(),
        "historical1Y": cagr(1), "historical3Y": cagr(3), "historical5Y": cagr(5), "historical10Y": cagr(10),
        "vola1y": vola1,
        "gesamt_cagr": float((s.iloc[-1] / s.iloc[0]) ** (1.0 / jahre) - 1.0) if jahre >= 1 else None,
        "seit_start": float(s.iloc[-1] / s.iloc[0] - 1.0),
        "vola": vola, "maxdd": maxdd,
        "monat": [(d.date().isoformat(), float(v)) for d, v in monat.dropna().items()],
    }


class _KeineDaten(Exception):
    pass


def _hist_eines(begriffe, wiki, heute_iso, _suche, _kurse, inst_id=None):
    """Wie _hist_eines_cache - Fehler werden aber NICHT zwischengespeichert,
    damit ein einmaliger Abruf-Aussetzer nicht stundenlang "fehlt" zeigt."""
    try:
        return _hist_eines_cache(begriffe, wiki, heute_iso, _suche, _kurse, inst_id)
    except _KeineDaten as e:
        return {"fehler": str(e)}
    except Exception as e:
        return {"fehler": f"Kurshistorie nicht ladbar ({e})"}


@st.cache_data(ttl=HIST_CACHE_SEK, show_spinner=False)
def _hist_eines_cache(begriffe, wiki, heute_iso, _suche, _kurse, inst_id=None):
    """Sucht das Instrument (WKN/ISIN/Name) und berechnet die Kennzahlen der
    kompletten verfuegbaren Historie. inst_id: bereits bekannte ls-tc-ID
    (aus config.BENCHMARKS). -> dict oder {"fehler": text}"""
    treffer, gefunden = [], None
    if inst_id:
        gefunden = {"instrument_id": inst_id, "name": begriffe[-1] if begriffe else "", "wkn": "", "isin": ""}
    for b in ([] if gefunden else begriffe):
        if not b:
            continue
        try:
            treffer = _suche(b) or []
        except Exception:
            treffer = []
        gefunden = _waehle_treffer(treffer, b, wiki)
        if gefunden:
            break
    if not gefunden:
        raise _KeineDaten("Instrument nicht gefunden – WKN/ISIN in den Stammdaten eintragen.")
    try:
        heute = datetime.date.fromisoformat(heute_iso)
        s = _kurse(gefunden["instrument_id"], datetime.date(2000, 1, 1), heute)
    except Exception as e:
        raise _KeineDaten(f"Kurshistorie nicht ladbar ({e})")
    if s is None or len(s) == 0:
        raise _KeineDaten("Keine Kurshistorie verfügbar.")
    k = _reihen_kennzahlen(pd.Series(s).astype(float))
    if not k:
        raise _KeineDaten("Kurshistorie zu kurz.")
    reihe = pd.Series(s).astype(float).dropna()
    reihe = reihe[reihe > 0]
    k.update({"quelle": "ls-tc.de Kurshistorie", "instrument": gefunden.get("name"),
              "wkn": gefunden.get("wkn"), "isin": gefunden.get("isin"),
              "instrument_id": gefunden.get("instrument_id"),
              "kurs": float(reihe.iloc[-1]) if len(reihe) else None,   # letzter Schlusskurs (fuer den Kaufplan)
              "abgerufen": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")})
    return k


def _parallel(aufgaben):
    """[(schluessel, funktion, args)] parallel ausfuehren (Netzabrufe)."""
    from concurrent.futures import ThreadPoolExecutor
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        ctx = get_script_run_ctx()
    except Exception:
        add_script_run_ctx, ctx = None, None

    def lauf(f, args):
        if ctx is not None and add_script_run_ctx is not None:
            try:
                import threading
                add_script_run_ctx(threading.current_thread(), ctx)
            except Exception:
                pass
        try:
            return f(*args)
        except Exception as e:
            return {"fehler": str(e)}

    with ThreadPoolExecutor(max_workers=6) as ex:
        zukunft = {k: ex.submit(lauf, f, a) for k, f, a in aufgaben}
        return {k: z.result() for k, z in zukunft.items()}


def _historie(m, h):
    """{asset_id: kennzahlen} + {korb_aktie: kennzahlen} aus echten Kursdaten."""
    heute = h["heute"].isoformat()
    aufgaben = []
    for a in m["assets"]:
        if a["category"] in ("cash", "stock_basket"):
            continue
        wiki = a["category"] == "wikifolio"
        kennung = a.get("ticker") or a.get("isin")
        begriffe = tuple(x for x in (a.get("ticker"), a.get("isin"), None if kennung else a["name"]) if x)
        inst_id = None
        if not kennung:
            # Vergleichswerte der App: Label -> ls-tc-ID (bereits gepflegt)
            for label, iid in (h.get("benchmarks") or {}).items():
                if a["name"].lower() in str(label).lower():
                    inst_id = iid
                    break
        aufgaben.append((("a", a["id"]), _hist_eines, (begriffe, wiki, heute, h["suche_instrument"],
                                                       h["get_kurshistorie"], inst_id)))
    if any(a["category"] == "stock_basket" and a.get("enabled") for a in m["assets"]):
        for k in m["korb"]:
            aufgaben.append((("k", k["id"]), _hist_eines, (tuple(x for x in (k.get("isin"),) if x), False, heute,
                                                           h["suche_instrument"], h["get_kurshistorie"])))
    erg = _parallel(aufgaben)
    assets = {k[1]: v for k, v in erg.items() if k[0] == "a"}
    korb = {k[1]: v for k, v in erg.items() if k[0] == "k"}
    return assets, korb


def _fundamentaldaten(m, h):
    """Kennzahlen der Korb-Aktien aus den Detaildateien des Qualitaets-Agenten."""
    aus, stand = {}, None
    for k in m["korb"]:
        sym = k.get("yahoo")
        if not sym:
            continue
        teil = zlib.crc32(sym.encode()) % QUALITAET_DETAIL_TEILE
        try:
            d = h["gh_read_taeglich"](f"state/qualitaet/details_{teil}.json", None) or {}
        except Exception:
            d = {}
        w = (d.get("werte") or {}).get(sym)
        if w:
            aus[k["id"]] = w
            stand = d.get("stand") or stand
    return aus, stand


def _layer(m, hist_assets, hist_korb, fund):
    """Baut den Historical Layer fuer die Engine:
    {asset_id: {historical5Y, historical10Y, fundamentalModel, jahre, maxdd, vola, ...}}"""
    historie = {}
    for aid, k in hist_assets.items():
        if k and not k.get("fehler"):
            historie[aid] = dict(k)
    korb = m["korb"]
    summe = sum(float(x["gewicht"]) for x in korb) or 1.0
    # Korb: gewichtetes Mittel der Einzel-CAGRs (nur wenn >= 50 % des Korbs Daten haben)
    eintrag = {}
    for feld in ("historical5Y", "historical10Y"):
        w_sum, v_sum = 0.0, 0.0
        for x in korb:
            k = hist_korb.get(x["id"]) or {}
            if k.get(feld) is not None:
                w_sum += float(x["gewicht"])
                v_sum += float(x["gewicht"]) * k[feld]
        if w_sum >= summe * 0.5:
            eintrag[feld] = v_sum / w_sum
    jahre = [(hist_korb.get(x["id"]) or {}).get("jahre") for x in korb]
    jahre = [j for j in jahre if j]
    if jahre:
        eintrag["jahre"] = min(sorted(jahre)[len(jahre) // 2], 10.0)     # Median, max. 10
    dds = [(hist_korb.get(x["id"]) or {}).get("maxdd") for x in korb]
    dds = [d for d in dds if d is not None]
    if dds:
        eintrag["maxdd"] = sum(dds) / len(dds) * 0.8        # Korb faellt weniger tief als der Schnitt der Einzelwerte
    fm, _ = E.korb_fundamental_rendite(korb, fund)
    if fm is not None:
        eintrag["fundamentalModel"] = fm
    if eintrag:
        eintrag["quelle"] = "Einzelwerte (ls-tc.de) / Qualitäts-Agent"
        historie["korb"] = eintrag
    return historie


def _scores(m, fund):
    """Fundamental Score je Korb-Aktie und fuer den Korb (gewichtet)."""
    je = {}
    for x in m["korb"]:
        je[x["id"]] = E.fundamental_score(fund.get(x["id"]), m["bewertungsregeln"],
                                          (m.get("manuell") or {}).get(x["id"]))
    summe, w = 0.0, 0.0
    for x in m["korb"]:
        g = je[x["id"]]["gesamt"]
        if g is not None:
            summe += g * float(x["gewicht"])
            w += float(x["gewicht"])
    korb = summe / w if w else None
    return je, korb


# ===========================================================================
# Rechnen
# ===========================================================================
def _kredit_konditionen(x):
    """-> (zins_pa, fehler). Zins eingetragen: so rechnen (Rate tilgt evtl. nur
    teilweise -> Schlussrate). Kein Zins: aus Betrag, Rate und Laufzeit errechnen."""
    betrag, rate, laufzeit = float(x.get("betrag") or 0), float(x.get("rate") or 0), int(x.get("jahre") or 0)
    if laufzeit <= 0:
        return None, "Laufzeit 0 J. – fließt in keine Berechnung ein"
    if betrag <= 0:
        return None, "unvollständig"
    if rate <= 0:
        # keine Rate: Kredit zaehlt trotzdem zum Kapital - nur Zinsen (falls Zins %), Rueckzahlung am Laufzeitende
        return (float(x.get("zins") or 0) / 100.0), None
    zins = x.get("zins")
    if zins:
        zins = float(zins) / 100.0
        if rate <= betrag * zins / 12.0:
            return None, "Rate deckt nicht einmal die Zinsen"
        return zins, None
    zins = E.kredit_zins_aus_rate(betrag, rate, laufzeit)
    if zins is None:
        # Rate tilgt nicht alles: trotzdem mitrechnen (0 % angenommen, Rest = Schlussrate)
        return 0.0, None
    return zins, None


def _kredit_rate_eff(x, zins=None):
    """Monatsrate fuer die Rechnung: eingetragene Rate, ohne Rate nur die Zinsen
    (bei 0 % = 0 €, der ganze Betrag wird am Laufzeitende getilgt)."""
    rate = float(x.get("rate") or 0)
    if rate > 0:
        return rate
    if zins is None:
        zins = _kredit_konditionen(x)[0] or 0.0
    return float(x.get("betrag") or 0) * zins / 12.0


def _kredite_aktiv(m):
    """Kredite zaehlen zum Kapital - Standard an (alte Modelle mit 'aus' werden einmalig umgestellt)."""
    k = m.get("kredit") or {}
    return bool(k.get("aktiv", True)) if k.get("aktiv_v2") else True


def _kredit_rahmen(m):
    """Wirkung der Kredite auf die Aufbauphase: zusaetzliches Startkapital,
    Restschuld am Ende des Aufbaus und (bei Raten zusaetzlich aus dem Depot) die
    Raten MONATSGENAU: raten = [(von_monat, bis_monat, betrag)] - nur waehrend der
    Kreditlaufzeit (innerhalb des Aufbaus). rate_depot = Summe der Monatsraten aus
    dem Depot im ersten Monat (Anzeige). None = keine aktiven Kredite."""
    k = _kredite(m) if m.get("kredit") else {}
    jahre = int(m["rahmen"].get("horizont_jahre") or 0)
    if not _kredite_aktiv(m) or jahre <= 0:
        return None
    summe = rest = 0.0
    raten = []
    for x in k.get("kredite") or []:
        betrag, rate, laufzeit = float(x.get("betrag") or 0), float(x.get("rate") or 0), int(x.get("jahre") or 0)
        zins, _ = _kredit_konditionen(x)
        if zins is None:
            continue
        monate = min(jahre, laufzeit) * 12
        rate = _kredit_rate_eff(x, zins)
        summe += betrag
        rest += E.kredit_restschuld(betrag, rate, zins, monate)
        if _rate_aus(m) == "investment" and rate > 0 and monate > 0:
            raten.append((1, monate, rate))                 # Monat 1 .. Laufzeitende
    if summe <= 0:
        return None
    return {"summe": summe, "restschuld": rest, "raten": raten, "rate_depot": E.kredit_rate_monat(raten, 1)}


def _entnahme_parallel(m):
    """Gleichzeitige Entnahme waehrend des Aufbaus (Standard) -> dict fuer die
    Projektion oder None."""
    e = m.get("entnahme") or {}
    jahre = int(m["rahmen"].get("horizont_jahre") or 0)
    if not e.get("aktiv", True) or not e.get("parallel", True) or jahre <= 0 or not float(e.get("monatlich") or 0):
        return None
    return {"monatlich": float(e["monatlich"]), "dynamik": float(e.get("dynamik_pa") or 0) / 100.0,
            "stufen": _stufen_sauber(e.get("stufen")),
            "monate": jahre * 12}


def _mit_krediten(m):
    """Modell fuer die Rechnung: Kreditgeld zusaetzlich investiert, Ziel = Ziel
    NACH Abzug der Restschuld, Raten aus dem Depot werden monatsgenau waehrend der
    Kreditlaufzeit abgezogen (rahmen["kredit_raten"]), und die Entnahme laeuft
    (Standard) schon waehrend des Aufbaus. Das Original bleibt unveraendert
    (gleiche Bausteine/Gewichte)."""
    kr = _kredit_rahmen(m)
    ent = _entnahme_parallel(m)
    if not kr and not ent:
        return m
    r = dict(m["rahmen"])
    if ent:
        r["entnahme_parallel"] = ent
    if not kr:
        return dict(m, rahmen=r)
    r["startkapital"] = float(r["startkapital"]) + kr["summe"]
    if float(r.get("zielvermoegen") or 0) > 0:
        r["zielvermoegen"] = float(r["zielvermoegen"]) + kr["restschuld"]
    if kr.get("raten"):
        r["kredit_raten"] = list(kr["raten"])
    return dict(m, rahmen=r)


def _rechne(m, historie, korb_score):
    info = E.alle_renditen(m, historie)
    r = E.rendite_map(info)
    conf = E.confidence_fuer(m, historie)
    reb = m["rebalancing"]
    # Manuelle Rendite: das GANZE Portfolio waechst gleichmaessig mit genau diesem Satz p.a.
    # (kein Auseinanderdriften der Bausteine) - Kapital inkl. Kredite, Entnahme, Restschuld
    r_calc = r
    if _auto_modus(m) == "manuell" and r:
        satz = _rendite_manuell(m)
        grenzen = E.gewichtung_fuer_rendite(m, r, satz)
        if not grenzen.get("fehler") and not grenzen.get("erreichbar", True):
            satz = min(max(satz, grenzen["min"]), grenzen["max"])
        r_calc = {i: satz for i in r}
    zus = E.zusammenfassung(_mit_krediten(m), r_calc, rebalancing=reb)
    kr = _kredit_rahmen(m)
    zus["kredit"] = kr
    zus["endwert_netto"] = zus["endwert"] - (kr["restschuld"] if kr else 0.0)
    # PLAN-09: Raten/negative Sparrate, die das Depot nicht mehr decken kann (Depot nie unter 0)
    zus["fehlbetrag"] = float(zus["projektion"].get("fehlbetrag") or 0.0)
    zus["entnahme_fehlbetrag"] = float(zus["projektion"].get("entnahme_fehlbetrag") or 0.0)
    scores = {"korb": korb_score}
    return {"info": info, "r": r, "r_calc": r_calc, "conf": conf, "zus": zus, "scores": scores, "reb": reb}


# ===========================================================================
# Bereiche
# ===========================================================================
def _phase(titel):
    st.markdown(f'<div class="pl-phase">{_esc(titel)}</div>', unsafe_allow_html=True)


class _Bereich:
    """Abschnitt im Planungsblock: im Schritt-Assistenten ein eigener, aufklappbarer
    Bereich; in der klassischen Ansicht (schon in einem Expander - Expander duerfen
    nicht verschachtelt werden) eine Zwischenueberschrift."""

    def __init__(self, titel, eingebettet, offen):
        self.titel, self.eingebettet, self.offen, self._ctx = titel, eingebettet, offen, None

    def __enter__(self):
        if self.eingebettet:
            self._ctx = st.expander(self.titel, expanded=self.offen)
            return self._ctx.__enter__()
        _phase(self.titel)
        return None

    def __exit__(self, *args):
        if self._ctx is not None:
            return self._ctx.__exit__(*args)
        return False


def _bereich(titel, eingebettet, offen=False):
    return _Bereich(titel, eingebettet, offen)


_BENOETIGT_CACHE = {}


def _benoetigt(m):
    """Wie _benoetigt_rechnen, aber je Eingabestand nur einmal gerechnet (die Funktion wird
    pro Seitenaufruf mehrfach gebraucht und loest jeweils eine Nullstellensuche aus)."""
    try:
        schluessel = json.dumps([m["rahmen"], _entnahme_daten(m), m.get("kredit")], sort_keys=True, default=str)
    except Exception:
        return _benoetigt_rechnen(m)
    if schluessel not in _BENOETIGT_CACHE:
        if len(_BENOETIGT_CACHE) > 200:
            _BENOETIGT_CACHE.clear()
        _BENOETIGT_CACHE[schluessel] = _benoetigt_rechnen(m)
    return _BENOETIGT_CACHE[schluessel]


def _benoetigt_rechnen(m):
    """Benoetigte Rendite p.a. fuers Zielvermoegen (None ohne Ziel).
    Mit Aufbau (> 0 Jahre): Ziel = Vermoegen am Ende des Aufbaus.
    Ohne Aufbau (0 Jahre): Ziel = Vermoegen am Ende der Entnahme -> benoetigte
    Rendite in der Entnahme (nach allen Entnahmen bleibt genau das Ziel)."""
    r = m["rahmen"]
    ziel = float(r.get("zielvermoegen") or 0)
    if ziel <= 0:
        return None
    if int(r.get("horizont_jahre") or 0) > 0:
        # Kredite: mehr Kapital, Ziel nach Restschuld; gleichzeitige Entnahme mindert das Wachstum
        return E.erforderliche_rendite_rahmen(_mit_krediten(m)["rahmen"])
    e = _entnahme_daten(m)
    if not e.get("aktiv", True):
        return None
    return E.rendite_fuer_restwert(float(r["startkapital"]), float(e["monatlich"]), ziel,
                                   jahre=int(e["dauer_jahre"]), dynamik_pa=float(e["dynamik_pa"]) / 100.0,
                                   stufen=e.get("stufen"))


def _ziel_unerreichbar(m):
    """True = Zielvermoegen (mit Aufbau) gesetzt, aber selbst mit extremer Rendite
    nicht erreichbar (benoetigte Rendite = None) -> "nicht erreichbar" anzeigen und
    trotzdem die renditestaerkste Verteilung rechnen."""
    r = m["rahmen"]
    return (float(r.get("zielvermoegen") or 0) > 0 and int(r.get("horizont_jahre") or 0) > 0
            and _benoetigt(m) is None)


def _ziel_in_entnahme(m):
    """True = das Zielvermoegen gilt fuer das Ende der Entnahme (0 Jahre Aufbau)."""
    return int(m["rahmen"].get("horizont_jahre") or 0) <= 0


RENDITE_MODI = {"ziel": "Automatisch aus dem Zielvermögen", "manuell": "Manuell: eigene Rendite p.a.",
                "aus": "Aus – eigene Gewichte"}


def _rendite_modus(m):
    """Wie wird die Rendite p.a. des Portfolios festgelegt? 'ziel' | 'manuell' | 'aus'
    (alte Modelle: auto_ziel True -> 'ziel', False -> 'aus')."""
    r = m["rahmen"]
    mo = r.get("rendite_modus")
    if mo not in RENDITE_MODI:
        mo = "ziel" if r.get("auto_ziel", True) else "aus"
    return mo


def _rendite_manuell(m):
    return float(m["rahmen"].get("rendite_manuell") or 8.0) / 100.0


def _auto_modus(m):
    """'ziel' = Gewichte automatisch aufs Zielvermoegen, 'manuell' = auf eine fest
    eingegebene Rendite p.a., 'entnahme' = auf die Entnahme-Rendite, None = aus.
    Ziel/manuell haben Vorrang (ein Portfolio, eine Rendite)."""
    mo = _rendite_modus(m)
    if mo == "manuell":
        return "manuell"
    if mo == "ziel" and (_benoetigt(m) is not None or _ziel_unerreichbar(m)):
        return "ziel"
    e = _entnahme_daten(m)
    if e.get("aktiv", True) and e.get("rendite_quelle", "eigen") == "eigen" and e.get("auto_gewichtung"):
        return "entnahme"
    return None


def _auto_aktiv(m):
    return _auto_modus(m) is not None


def _auto_gewichtung(m, R):
    """Automatische Gewichtung (Ziel oder Entnahme-Rendite).
    -> True, wenn Gewichte geaendert wurden"""
    modus = _auto_modus(m)
    if not modus:
        st.session_state.pop("planer_autogew", None)
        return False
    if modus == "ziel" and _ziel_in_entnahme(m):
        ben = _benoetigt(m)
        erg = E.gewichtung_fuer_rendite(m, R["r"], ben)
        erg["benoetigt"] = ben
    elif modus == "ziel":
        erg = E.gewichtung_fuer_zielvermoegen(_mit_krediten(m), R["r"], R["reb"])
    elif modus == "manuell":
        # gewichteter Mittelwert = manueller Satz (gerechnet wird gleichmaessig mit diesem Satz)
        erg = E.gewichtung_fuer_rendite(m, R["r"], _rendite_manuell(m))
        erg["soll"] = _rendite_manuell(m)
    else:
        erg = E.gewichtung_fuer_rendite(m, R["r"], float(_entnahme_daten(m)["rendite_pa"]) / 100.0)
    erg["modus"] = modus
    st.session_state["planer_autogew"] = erg
    if erg.get("fehler"):
        return False
    geaendert = False
    for a in m["assets"]:
        if a["id"] in erg["gewichte"] and abs(float(a.get("targetWeight") or 0) - erg["gewichte"][a["id"]]) > 0.005:
            a["targetWeight"] = round(erg["gewichte"][a["id"]], 3)
            geaendert = True
    return geaendert


def _ziel_feinabgleich(m, R):
    """Bei automatischer Gewichtung aufs Zielvermoegen: Endwert ueber dem Ziel (z. B. durch ganze
    Stuecke, Mindeststuecke oder sehr renditestarke Bausteine) -> investierten Teil anteilig
    verkleinern, Rest in die Reserve. So trifft das Modell das Ziel genau. -> True wenn geaendert"""
    if _auto_modus(m) != "ziel" or _ziel_in_entnahme(m):
        st.session_state.pop("planer_feinabgleich", None)
        return False
    erg = E.ziel_genau_ausrichten(_mit_krediten(m), R.get("r_calc", R["r"]), R["reb"])
    st.session_state["planer_feinabgleich"] = erg
    if erg.get("fehler") or not erg.get("geaendert"):
        return False
    for a in m["assets"]:
        if a["id"] in erg["gewichte"]:
            a["targetWeight"] = round(erg["gewichte"][a["id"]], 4)
            if a["id"] == erg["reserve_id"]:
                a["enabled"] = True
    return True


def _auto_hinweis(m):
    modus = _auto_modus(m)
    if modus == "ziel":
        wann = "am Ende der Entnahme" if _ziel_in_entnahme(m) else "am Ende des Aufbaus"
        st.info(f"Automatische Gewichtung ist aktiv: Die Prozente werden laufend so verteilt, dass das Zielvermögen "
                f"von {_de(m['rahmen']['zielvermoegen'])} € {wann} erreicht wird (benötigt {_pct_ziel(_benoetigt(m))} p.a.) – "
                "eigene Gewichte und Vorschläge werden überschrieben. Ausschalten unter „🎯 Ziel & Rahmen“ (bzw. ⚙️ Planung → Phase 1).")
    elif modus == "manuell":
        st.info(f"Manuelle Rendite ist aktiv: Die Prozente werden laufend so verteilt, dass das Portfolio "
                f"{_pct(_rendite_manuell(m))} p.a. erzielt – alle Werte (Aufbau, Entnahme, Kredite, Bilanz) "
                "werden damit gerechnet; eigene Gewichte und Vorschläge werden überschrieben. "
                "Ändern unter „🎯 Ziel & Rahmen“ (bzw. ⚙️ Planung → Phase 1).")
    elif modus == "entnahme":
        st.info(f"Automatische Gewichtung ist aktiv: Die Prozente werden laufend auf "
                f"{_de(_entnahme_daten(m)['rendite_pa'], 1)} % p.a. (Rendite in der Entnahme) ausgerichtet – "
                "eigene Gewichte und Vorschläge werden überschrieben. Ausschalten unter „🎯 Ziel & Rahmen → 💸 Entnahme“ (bzw. ⚙️ Planung → Phase 2).")


def _stufen_sauber(liste):
    """Entnahme-Stufen pruefen: ab Jahr >= 2, Betrag >= 0, sortiert, je Jahr nur eine."""
    aus = {}
    for x in liste or []:
        try:
            aj, b = int(float(x.get("ab_jahr"))), float(x.get("monatlich"))
        except (TypeError, ValueError):
            continue
        if aj >= 2 and b == b and b >= 0:
            aus[aj] = b
    return [{"ab_jahr": aj, "monatlich": aus[aj]} for aj in sorted(aus)]


def _stufen_text(e, kurz=False):
    st_ = e.get("stufen") or []
    if not st_:
        return ""
    t = " · ".join(f"ab J. {x['ab_jahr']}: {_de(x['monatlich'])} €" for x in st_)
    return t if kurz else f" (danach {t})"


def _entnahme_start_monat(m):
    """Entnahme-Monate, die schon waehrend des Aufbaus gelaufen sind."""
    return int(m["rahmen"].get("horizont_jahre") or 0) * 12 if _entnahme_parallel(m) else 0


def _entnahme_stufen_editor(m, e):
    """Entnahme nach X Jahren aendern (z. B. senken) - Tabelle direkt bearbeitbar."""
    parallel = bool(e.get("parallel", True)) and int(m["rahmen"].get("horizont_jahre") or 0) > 0
    st.markdown('<div class="pl-zeile" style="margin-top:6px"><b>Entnahme später ändern</b></div>',
                unsafe_allow_html=True)
    st.caption("Ab einem bestimmten Jahr einen anderen Monatsbetrag entnehmen (z. B. senken, wenn ein Kredit "
               "abbezahlt ist). Jahr 1 = " + ("ab sofort (Beginn der Planung)." if parallel
                                              else "erstes Jahr der Entnahme nach dem Aufbau.")
               + " Die jährliche Erhöhung läuft ab dem neuen Betrag weiter. 🗑️ antippen = Zeile löschen.")
    if st.button("➕ Änderung hinzufügen", key=_k("en_stufe_neu"), width="stretch"):
        letzte = e["stufen"][-1] if e["stufen"] else None
        e["stufen"] = _stufen_sauber(e["stufen"] + [{"ab_jahr": (letzte["ab_jahr"] + 5) if letzte else 6,
                                                     "monatlich": float(letzte["monatlich"] if letzte
                                                                        else e["monatlich"])}])
        st.session_state["planer_st_ver"] = st.session_state.get("planer_st_ver", 0) + 1
        st.rerun()
    if not e["stufen"]:
        return
    df = pd.DataFrame([{"Ab Jahr": int(x["ab_jahr"]), "€/Monat": float(x["monatlich"]), "🗑️": False}
                       for x in e["stufen"]])
    ed = st.data_editor(
        df, key=_k(f"en_stufen_{len(df)}_{st.session_state.get('planer_st_ver', 0)}"), hide_index=True,
        width="stretch", num_rows="fixed", height=_hoehe(len(df)),
        column_config={
            "Ab Jahr": st.column_config.NumberColumn("Ab Jahr", min_value=2, max_value=100, step=1, format="%d"),
            "€/Monat": st.column_config.NumberColumn("€/Monat", min_value=0.0, step=50.0, format="%.0f"),
            "🗑️": st.column_config.CheckboxColumn("🗑️", help="Antippen = Zeile löschen"),
        })
    if ed is not None and len(ed) == len(df):
        neu = _stufen_sauber([{"ab_jahr": z["Ab Jahr"], "monatlich": z["€/Monat"]}
                              for _, z in ed.iterrows() if not bool(z.get("🗑️"))])
        if _norm(neu) != _norm(e["stufen"]):
            e["stufen"] = neu
            st.session_state["planer_st_ver"] = st.session_state.get("planer_st_ver", 0) + 1
            st.rerun()


def _entnahme_daten(m):
    e = m.setdefault("entnahme", copy.deepcopy(D.ENTNAHME))
    for k, v in D.ENTNAHME.items():
        e.setdefault(k, copy.deepcopy(v))
    e["stufen"] = _stufen_sauber(e.get("stufen"))
    e["start"] = "modell"             # Entnahme beginnt immer mit dem Modell-Endwert der Aufbauphase
    return e


def _rahmen(m, eingebettet=False):
    """EINE Planung in zwei Phasen: Aufbau (Startkapital, Sparrate, Jahre) und
    direkt anschliessend Entnahme aus dem Endwert. Alle Eingaben an einer Stelle."""
    rahmen = m["rahmen"]
    e = _entnahme_daten(m)
    with (st.container() if eingebettet else st.container(border=True, key="pl_planung")):
        if not eingebettet:
            st.markdown('<div class="pl-planung-kopf">⚙️ Planung: Aufbau → Entnahme</div>', unsafe_allow_html=True)
        _phase("Phase 1 · Aufbau" if not eingebettet else "Grundangaben")
        if eingebettet:
            st.caption("Pflicht: Startkapital oder Sparrate. Alles andere ist optional und hat sinnvolle Standardwerte.")
        c1, c2 = st.columns(2)
        rahmen["startkapital"] = float(c1.number_input(
            "Startkapital (€)", 0.0, 1e9, float(rahmen["startkapital"]), step=1000.0, format="%.0f", key=_k("start"),
            help="Einmalbetrag, der zu Beginn investiert wird (ohne Kredite – die kommen unter „Kredit“ dazu)."))
        rahmen["sparrate_monat"] = float(c2.number_input(
            "Monatliche Sparrate (€)", 0.0, 1e6, float(rahmen.get("sparrate_monat") or 0.0), step=50.0,
            format="%.0f", key=_k("spar"),
            help="Wird jeden Monat nach Zielgewicht auf die Bausteine verteilt (Sparplan)."))
        bilanz_platz = st.empty()        # Kapital + Kredite + Monatsbilanz (nach der Rechnung gefuellt)
        c3, c4 = st.columns(2)
        rahmen["horizont_jahre"] = int(c3.number_input("Dauer Aufbau (Jahre)", 0, 40, int(rahmen["horizont_jahre"]),
                                                       key=_k("jahre"),
                                                       help="0 = kein Aufbau, die Entnahme startet sofort mit dem Startkapital"))
        rahmen["zielvermoegen"] = float(c4.number_input("Zielvermögen am Ende (€)", 0.0, 1e10,
                                                        float(rahmen["zielvermoegen"]), step=5000.0, format="%.0f",
                                                        key=_k("ziel"),
                                                        help="0 = kein Ziel. Mit Aufbau: Vermögen am Ende des Aufbaus. "
                                                             "Bei 0 Jahren Aufbau: Vermögen am Ende der Entnahme "
                                                             "(nach allen Entnahmen)."))
        if eingebettet:
            if float(rahmen["startkapital"] or 0) <= 0 and float(rahmen.get("sparrate_monat") or 0) <= 0:
                st.error("Bitte ein Startkapital oder eine monatliche Sparrate eingeben – sonst gibt es nichts zu "
                         "rechnen.")
            elif 0 < float(rahmen.get("zielvermoegen") or 0) <= float(rahmen["startkapital"] or 0) \
                    and int(rahmen["horizont_jahre"] or 0) > 0:
                st.info("Das Zielvermögen liegt nicht über dem Startkapital – es ist schon erreicht.")
        modi = list(RENDITE_MODI)
        c4a, c4b = st.columns(2)
        mo = c4a.selectbox(
            "Rendite p.a. / Gewichtung", modi, index=modi.index(_rendite_modus(m)), format_func=RENDITE_MODI.get,
            key=_k("rendite_modus"),
            help="Zielvermögen: benötigte Rendite wird berechnet und die Prozente automatisch darauf verteilt. "
                 "Manuell: du gibst die Rendite p.a. vor, die Prozente werden darauf verteilt und alles "
                 "(Aufbau, Entnahme, Kredite, Monatsbilanz) wird damit gerechnet. Aus: deine eigenen Gewichte. "
                 "Fixierte Bausteine und Reserve bleiben immer.")
        rahmen["rendite_modus"] = mo
        rahmen["auto_ziel"] = mo == "ziel"          # Rueckwaertskompatibel
        if mo == "manuell":
            rahmen["rendite_manuell"] = float(c4b.number_input(
                "Rendite p.a. (%)", -20.0, 200.0, float(rahmen.get("rendite_manuell") or 8.0), step=0.5,
                key=_k("rendite_manuell"), help="Fester Wert statt der Automatik"))
        ziel_platz = None
        if float(rahmen.get("zielvermoegen") or 0) > 0 or mo == "manuell":
            ziel_platz = st.empty()          # wird nach den Entnahme-Eingaben gefuellt (aktuelle Werte)

        with _bereich("💸 Entnahme · optional" if eingebettet else
                      "Phase 2 · Entnahme" + (" (gleichzeitig mit dem Aufbau)" if e.get("parallel", True)
                                              else " (ab Ende des Aufbaus)"), eingebettet,
                      offen=False):
            e["aktiv"] = st.toggle("Entnahme einplanen", value=bool(e.get("aktiv", True)), key=_k("en_aktiv"))
            if e["aktiv"]:
                e["parallel"] = st.toggle(
                    "Entnahme schon während des Aufbaus (ab sofort)", value=bool(e.get("parallel", True)),
                    key=_k("en_parallel"),
                    help="An (Standard): die monatliche Entnahme läuft ab dem ersten Monat, gleichzeitig mit dem Aufbau – "
                         "sie wird jeden Monat vom Depot abgezogen, nachdem die Rendite gutgeschrieben ist. Nach dem "
                         "Aufbau geht sie für „Dauer Entnahme“ Jahre weiter. Aus: Entnahme erst nach dem Aufbau.")
                c5, c6 = st.columns(2)
                e["monatlich"] = float(c5.number_input("Entnahme pro Monat (€, netto)", 0.0, 1e7, float(e["monatlich"]),
                                                       step=50.0, format="%.0f", key=_k("en_mon")))
                e["dauer_jahre"] = int(c6.number_input("Dauer Entnahme nach dem Aufbau (J.)" if e["parallel"]
                                                       else "Dauer Entnahme (Jahre)", 1, 60, int(e["dauer_jahre"]),
                                                       key=_k("en_dauer")))
                c7, c8 = st.columns(2)
                e["dynamik_pa"] = float(c7.number_input("Jährliche Erhöhung (%)", 0.0, 10.0, float(e["dynamik_pa"]),
                                                        step=0.5, key=_k("en_dyn"), help="z. B. Inflationsausgleich"))
                _entnahme_stufen_editor(m, e)
                quellen = {"eigen": "Eigene Annahme", "modell": "Wie Aufbauphase"}
                q = c8.selectbox("Rendite in der Entnahme", list(quellen),
                                 index=list(quellen).index(e.get("rendite_quelle", "eigen")),
                                 format_func=quellen.get, key=_k("en_quelle"))
                e["rendite_quelle"] = q
                if q == "eigen" and _auto_modus(m) == "manuell":
                    st.markdown(f'<div class="pl-zeile">Rendite p.a. in der Entnahme: <b>{_pct(_rendite_manuell(m))}</b> '
                                '(manuell aus Phase 1; ist das nicht erreichbar, gilt die höchstmögliche '
                                'Portfoliorendite)</div>', unsafe_allow_html=True)
                elif q == "eigen" and _auto_modus(m) == "ziel":
                    # ein Portfolio, eine Rendite: die Entnahme rechnet mit der benoetigten Rendite
                    if _ziel_in_entnahme(m):
                        st.markdown(f'<div class="pl-zeile">Rendite p.a. in der Entnahme: <b>{_pct(_benoetigt(m))}</b> '
                                    f'(automatisch aus dem Zielvermögen von {_de(rahmen["zielvermoegen"])} € nach '
                                    f'{e["dauer_jahre"]} J. Entnahme; ist das nicht erreichbar, gilt die höchstmögliche '
                                    'Portfoliorendite)</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="pl-zeile">Rendite p.a. in der Entnahme: <b>wie Aufbauphase</b> '
                                    f'(automatisch – benötigt {_pct_ziel(_benoetigt(m))}; ist das Ziel nicht erreichbar, gilt '
                                    'die tatsächlich erreichte Modellrendite)</div>', unsafe_allow_html=True)
                elif q == "eigen":
                    e["rendite_pa"] = float(st.number_input(
                        "Rendite p.a. in der Entnahme (%)", -20.0, 200.0, float(e["rendite_pa"]), step=0.5,
                        key=_k("en_rendite"), help="Ziel-Rendite des Portfolios in der Entnahmephase"))
                    e["auto_gewichtung"] = st.toggle(
                        "Portfolio automatisch auf diese Rendite gewichten", value=bool(e.get("auto_gewichtung", False)),
                        key=_k("en_auto"),
                        help="Verteilt die Prozente im Portfolio automatisch so, dass die gewichtete Rendite p.a. genau "
                             "diesem Wert entspricht – ausgehend von einer Gleichverteilung, ausgeglichen über die "
                             "Renditen der Bausteine. Fixierte Bausteine und Reserve bleiben. Manuelle Gewichte werden "
                             "dabei überschrieben.")
                e["steuer"] = st.toggle("Abgeltungsteuer berücksichtigen (vereinfacht)", value=bool(e["steuer"]),
                                        key=_k("en_st"))
                if e["steuer"]:
                    c9, c10 = st.columns(2)
                    e["steuersatz"] = float(c9.number_input("Steuersatz (%)", 0.0, 60.0, float(e["steuersatz"]), step=0.5,
                                                            key=_k("en_satz"),
                                                            help="Abgeltungsteuer + Soli, ohne Kirchensteuer"))
                    e["freibetrag"] = float(c10.number_input("Freibetrag pro Jahr (€)", 0.0, 1e5, float(e["freibetrag"]),
                                                             step=100.0, format="%.0f", key=_k("en_frei"),
                                                             help="Sparerpauschbetrag – bitte aktuellen Wert prüfen"))

        if ziel_platz is not None:
            ben = _benoetigt(m)
            if mo == "manuell":
                ziel_platz.markdown(
                    '<div class="pl-zeile">' + (f'Benötigte Rendite fürs Ziel: <b>{_pct(ben)}</b> · ' if ben is not None
                                                else "")
                    + f'gerechnet wird mit <b>{_pct(_rendite_manuell(m))}</b> p.a. (manuell) → Gewichte werden '
                    'automatisch darauf verteilt'
                    + ((lambda a: f' · ⚠ mit diesen Bausteinen höchstens {_pct(a["max"])}'
                        if a and a.get("modus") == "manuell" and not a.get("erreichbar") and a.get("max") is not None
                        and a["max"] < _rendite_manuell(m) else "")(st.session_state.get("planer_autogew")))
                    + '</div>', unsafe_allow_html=True)
            elif ben is None:
                ziel_platz.caption("Ohne Aufbau gilt das Zielvermögen für das Ende der Entnahme – dafür die "
                                   "Entnahme einplanen." if _ziel_in_entnahme(m) else
                                   "Benötigte Rendite: Ziel nicht erreichbar (auch mit extremer Rendite nicht – "
                                   "Startkapital/Sparrate zu klein oder Entnahme/Kreditraten zu hoch).")
            else:
                ziel_platz.markdown(
                    f'<div class="pl-zeile">Benötigte Rendite p.a.' + (" in der Entnahme" if _ziel_in_entnahme(m) else "")
                    + f': <b>{_pct(ben)}</b>' + (" → Gewichte werden automatisch darauf verteilt" if mo == "ziel"
                                                  else "") + "</div>", unsafe_allow_html=True)

        with _bereich("⚙️ Erweiterte Einstellungen (Regeln, Kosten, Rebalancing, Renditequelle)", eingebettet,
                      offen=False):
            _regeln_editor(m)
            rahmen["kosten_beruecksichtigen"] = st.toggle(
                "Kosten berücksichtigen (TER und Performance Fee, soweit hinterlegt)",
                value=bool(rahmen.get("kosten_beruecksichtigen")), key=_k("kosten"))
            arten = list(D.REBALANCING_ARTEN)
            c11, c12 = st.columns(2)
            art = c11.selectbox("Rebalancing", arten, index=arten.index(m["rebalancing"].get("art", "keins")),
                                format_func=D.REBALANCING_ARTEN.get, key=_k("reb"))
            m["rebalancing"]["art"] = art
            if art == "schwelle":
                m["rebalancing"]["schwelle_relativ"] = float(c12.number_input(
                    "Band (± % relativ zum Zielgewicht)", 1.0, 100.0,
                    float(m["rebalancing"].get("schwelle_relativ", 25.0)), step=2.5, key=_k("band"),
                    help="25 % relativ: Zielgewicht 10 % → Band 7,5–12,5 %"))
            methoden = list(D.METHODEN)
            wahl = st.selectbox("Renditequelle der Rechnung", methoden, index=methoden.index(rahmen["methode"]),
                                format_func=D.METHODEN.get, key=_k("methode"),
                                help="Standard „Meine Annahmen“ = Spalte „Annahme %“ bzw. Ist-Werte im Portfolio")
            rahmen["methode"] = wahl
            if rahmen["methode"] == "szenario":
                sz = ["bear", "base", "bull", "custom"]
                rahmen["szenario"] = st.selectbox("Szenario", sz, index=sz.index(rahmen.get("szenario", "base")),
                                                  format_func=str.capitalize, key=_k("szenario"))
            if rahmen["methode"] in ("historical5Y", "historical10Y", "fundamentalModel"):
                st.caption("Wo für diese Quelle keine Daten vorliegen, gilt die eigene Annahme.")
            st.caption("Renditen sind effektive Jahresrenditen vor Steuern. Die Nachkaufreserve nimmt am "
                       "Rebalancing nicht teil.")
    return bilanz_platz


def _stufen_bilanz(m, R, e, r):
    """Je Entnahme-Stufe: Betrag (inkl. Erhoehung), Depotwert und Monatsbilanz zu Beginn der Stufe."""
    if not e.get("aktiv", True) or not e.get("stufen"):
        return []
    rm = (1 + r) ** (1 / 12) - 1 if r > -1 else -1.0
    jahre = int(m["rahmen"].get("horizont_jahre") or 0)
    n_auf = jahre * 12
    parallel = bool(_entnahme_parallel(m))
    werte = R["zus"]["projektion"].get("monatswerte") or []
    asset_v = R["zus"]["projektion"].get("asset_verlauf") or {}
    r_je = R.get("r_calc", R["r"])
    try:
        _, r_ent, _, plan = _entnahme_rechnen(m, R, e)
        rm_ent = (1 + r_ent) ** (1 / 12) - 1
        nach = plan["verlauf"]
    except Exception:
        rm_ent, nach = rm, []
    eff_r = _mit_krediten(m)["rahmen"]
    spar = float(eff_r.get("sparrate_monat") or 0.0)
    raten = eff_r.get("kredit_raten")
    aus = []
    for x in e["stufen"]:
        mon_ent = (x["ab_jahr"] - 1) * 12                    # Entnahme-Monate davor
        t = mon_ent if (parallel or jahre == 0) else n_auf + mon_ent   # Monate ab heute
        betrag = E.entnahme_betrag(e["monatlich"], float(e["dynamik_pa"]) / 100.0, mon_ent + 1, e["stufen"])
        gewinn = None
        if t < len(werte) and t < n_auf:
            wert, sp = werte[t], spar - E.kredit_rate_monat(raten, t + 1)
            # Gewinn je Baustein mit SEINER Rendite (nicht dem 5-Jahres-Durchschnitt)
            gewinn = sum(v[t] * ((1 + r_je.get(i, 0.0)) ** (1 / 12) - 1) for i, v in asset_v.items()
                         if t < len(v)) if asset_v else wert * rm
        elif 0 <= t - n_auf < len(nach):
            wert, sp = nach[t - n_auf], 0.0
            gewinn = wert * rm_ent
        else:
            wert, sp = None, 0.0
        saldo = None if wert is None else gewinn + sp - betrag
        aus.append({"ab_jahr": x["ab_jahr"], "betrag": betrag, "wert": wert, "saldo": saldo,
                    "in_jahren": t / 12})
    return aus


def _monatsbilanz(m, R):
    """Was pro Monat ins Depot hinein- und herausgeht - am Start:
    Gewinn (Rendite p.a. auf Eigenkapital + Kredite, in Monatsgewinn umgerechnet)
    + Sparrate - Entnahme - Kreditraten (nur wenn ZUSAETZLICH aus dem Depot bezahlt;
    standardmaessig stecken die Raten in der Entnahme und werden nicht extra abgezogen)."""
    rahmen = m["rahmen"]
    e = _entnahme_daten(m)
    k = _kredite(m) if m.get("kredit") else {}
    eff = _mit_krediten(m)["rahmen"]
    z = R["zus"]
    r_je = R.get("r_calc", R["r"])
    gew = E.gewichte(m)
    # Rendite im ersten Jahr = gewichteter Mittelwert der Bausteine. Die "modellierte Rendite p.a."
    # (CAGR ueber den ganzen Aufbau) kann viel hoeher liegen, wenn ein Baustein mit sehr hoher
    # Annahme ohne Rebalancing immer groesser wird - fuer den Monatsgewinn am Start waere sie falsch.
    r = sum(g * r_je.get(i, 0.0) for i, g in gew.items())
    r_cagr = z.get("modell_cagr")
    kr = _kredit_rahmen(m)
    kredite = [x for x in (k.get("kredite") or []) if _kredite_aktiv(m) and _kredit_konditionen(x)[0] is not None]
    # warum ist ein eingetragener Kredit NICHT im Kapital? (sichtbar machen)
    nicht = []
    for x in k.get("kredite") or []:
        if float(x.get("betrag") or 0) <= 0:
            continue
        if not _kredite_aktiv(m):
            nicht.append(f"{x['name']}: „Kredite in die Planung einrechnen“ (Seite 💳 Kredit) ist aus")
        elif int(rahmen.get("horizont_jahre") or 0) <= 0:
            nicht.append(f"{x['name']}: nur mit Aufbau (> 0 Jahre)")
        elif _kredit_konditionen(x)[0] is None:
            nicht.append(f"{x['name']}: {_kredit_konditionen(x)[1]}")
    raten = sum(_kredit_rate_eff(x) for x in kredite)
    ek = float(rahmen["startkapital"])
    kapital = ek + (kr["summe"] if kr else 0.0)
    gewinn_jahr = sum(kapital * g * r_je.get(i, 0.0) for i, g in gew.items())
    gewinn_monat = sum(kapital * g * ((1 + r_je.get(i, 0.0)) ** (1 / 12) - 1) for i, g in gew.items())
    jahre = int(rahmen.get("horizont_jahre") or 0)
    ent_sofort = bool(e.get("aktiv", True)) and (bool(_entnahme_parallel(m)) or jahre == 0)
    entnahme = float(e["monatlich"]) if ent_sofort else 0.0
    art = _rate_aus(m)
    raten_depot = raten if (kredite and art == "investment") else 0.0
    raten_in_entnahme = raten if (kredite and art == "entnahme") else 0.0
    spar = float(rahmen.get("sparrate_monat") or 0.0)
    saldo = gewinn_monat + spar - entnahme - raten_depot
    return {"ek": ek, "kredite": kredite, "kredit_summe": kr["summe"] if kr else 0.0, "kapital": kapital, "r": r,
            "r_cagr": r_cagr,
            "gewinn_jahr": gewinn_jahr, "gewinn_monat": gewinn_monat, "spar": spar, "entnahme": entnahme,
            "entnahme_spaeter": float(e["monatlich"]) if (e.get("aktiv", True) and not ent_sofort) else 0.0,
            "raten": raten, "raten_depot": raten_depot, "raten_einkommen": raten if (kredite and art == "einkommen") else 0.0,
            "raten_in_entnahme": raten_in_entnahme, "saldo": saldo, "nicht": nicht,
            "stufen": _stufen_bilanz(m, R, e, r),
            "kredit_ohne_aufbau": bool(_kredite_aktiv(m) and kredite and jahre == 0)}


def _monatsbilanz_anzeigen(platz, m, R):
    b = _monatsbilanz(m, R)

    def z(label, wert, klasse="", fett=False):
        w = f"<b>{wert}</b>" if fett else wert
        return (f'<tr><td style="padding:3px 8px 3px 0">{label}</td>'
                f'<td style="padding:3px 0;text-align:right;white-space:nowrap" class="{klasse}">{w}</td></tr>')

    zeilen = [z("Eigenkapital (Startkapital)", f"{_de(b['ek'])} €")]
    for x in (b["kredite"] if b["kredit_summe"] else []):
        zeilen.append(z(f"+ {_esc(x['name'])} (Kredit)", f"{_de(x['betrag'])} €"))
    if b["kredit_summe"]:
        zeilen.append(z("= investiertes Kapital", f"{_de(b['kapital'])} €", fett=True))
    zeilen.append(z(f"Gewinn im 1. Jahr bei Ø {_pct(b['r'])} p.a. (gewichtet)", f"{_de(b['gewinn_jahr'])} €/Jahr"))
    zeilen.append(z("→ Gewinn im 1. Monat (mit Zinseszins)", f"+{_de(b['gewinn_monat'])} €", "pl-gut", fett=True))
    if b["spar"]:
        zeilen.append(z("+ Sparrate", f"+{_de(b['spar'])} €", "pl-gut"))
    if b["entnahme"]:
        zeilen.append(z("− Entnahme (ab sofort)", f"−{_de(b['entnahme'])} €", "pl-schlecht"))
    if b["raten_in_entnahme"] and (b["entnahme"] or b["entnahme_spaeter"]):
        ent = b["entnahme"] or b["entnahme_spaeter"]
        frei = ent - b["raten_in_entnahme"]
        zeilen.append(z("&nbsp;&nbsp;davon Kreditraten (kein extra Abzug)", f"{_de(b['raten_in_entnahme'])} €"))
        zeilen.append(z("&nbsp;&nbsp;davon frei verfügbar", f'{"" if frei >= 0 else "−"}{_de(abs(frei))} €',
                        "" if frei >= 0 else "pl-schlecht"))
    if b["raten_depot"]:
        zeilen.append(z("− Kreditraten (aus dem Depot)", f"−{_de(b['raten_depot'])} €", "pl-schlecht"))
    if b["raten_einkommen"]:
        zeilen.append(z("Kreditraten aus dem Einkommen (laufende Kosten, nicht vom Depot)",
                        f"{_de(b['raten_einkommen'])} €/Monat"))
    s_ = b["saldo"]
    zeilen.append(z("= Monatsbilanz Depot", f'{"+" if s_ >= 0 else "−"}{_de(abs(s_))} €',
                    "pl-gut" if s_ >= 0 else "pl-schlecht", fett=True))
    hinweis = ("Depot wächst" if s_ > 0 else "Depot schrumpft") + " – Stand am Start, die Gewinne steigen bzw. sinken mit dem Kapital."
    extra = []
    if b["entnahme_spaeter"]:
        extra.append(f"Entnahme {_de(b['entnahme_spaeter'])} €/Monat beginnt erst nach dem Aufbau.")
    if b["raten_in_entnahme"] and not (b["entnahme"] or b["entnahme_spaeter"]):
        extra.append(f"Kreditraten {_de(b['raten_in_entnahme'])} €/Monat sollen aus der Entnahme kommen – "
                     "es ist aber keine Entnahme eingeplant.")
    elif b["raten_in_entnahme"] and b["raten_in_entnahme"] > (b["entnahme"] or b["entnahme_spaeter"]):
        extra.append("⚠ Die Kreditraten sind höher als die Entnahme.")
    for t in b["nicht"]:
        extra.append("⚠ Nicht eingerechnet – " + t)
    stufen_html = ""
    if b.get("stufen"):
        teile = []
        for x in b["stufen"]:
            t = f'Ab Jahr {x["ab_jahr"]}: Entnahme <b>{_de(x["betrag"])} €/Monat</b>'
            if x["saldo"] is not None:
                t += (f' · Depot dann {_eur(x["wert"])} · Monatsbilanz <b class="{"pl-gut" if x["saldo"] >= 0 else "pl-schlecht"}">'
                      f'{"+" if x["saldo"] >= 0 else "−"}{_de(abs(x["saldo"]))} €</b>')
            teile.append(t)
        stufen_html = '<div class="pl-zeile" style="margin-top:4px">' + "<br>".join(teile) + "</div>"
    if b.get("r_cagr") is not None and b["r_cagr"] - b["r"] > 0.05:
        extra.append(f"Hinweis: Am Start wächst das Depot mit Ø {_pct(b['r'])} p.a. Die modellierte Rendite von "
                     f"{_pct(b['r_cagr'])} ist der Durchschnitt über den ganzen Aufbau – sie steigt, weil Bausteine "
                     "mit hoher Annahme ohne Rebalancing einen immer größeren Anteil bekommen.")
    if b["kredit_ohne_aufbau"] and not b["nicht"]:
        extra.append("Kredite werden nur bei einer Aufbauphase (> 0 Jahre) aufs Startkapital gerechnet.")
    with platz.container():
        st.markdown('<div class="pl-zeile" style="margin:6px 0 2px"><b>Kapital & Monatsbilanz</b></div>'
                    f'<table style="width:100%;border-collapse:collapse;font-size:.92rem">{"".join(zeilen)}</table>'
                    f'<div class="pl-zeile" style="margin-top:4px"><b class="{"pl-gut" if s_ >= 0 else "pl-schlecht"}">'
                    f'{_esc(hinweis)}</b></div>' + stufen_html, unsafe_allow_html=True)
        if extra:
            with st.expander(("⚠️ " if any("⚠" in t for t in extra) else "ℹ️ ") + "Hinweise zur Monatsbilanz",
                             expanded=False):
                for t in extra:
                    st.caption(t)


def _fehlbetrag_text(z):
    """PLAN-09: Hinweis, wenn das Depot Kreditraten / negative Sparrate oder die Entnahme
    nicht mehr decken kann (die Rechnung stoppt bei 0 €, der Rest ist ungedeckt)."""
    fb = float(z.get("fehlbetrag") or 0.0)
    fe = float(z.get("entnahme_fehlbetrag") or 0.0)
    teile = []
    if fb > 0.5:
        teile.append(f"Kreditraten/Abbuchungen {_de(fb)} € nicht gedeckt")
    if fe > 0.5:
        teile.append(f"Entnahmen {_de(fe)} € nicht gedeckt")
    if not teile:
        return ""
    return ("⚠ Depot im Aufbau aufgebraucht (Wert 0 €): " + " · ".join(teile)
            + " – diese Beträge müssten aus dem Einkommen kommen.")


def _plausibilitaet(m, R, port_r):
    """Warnungen, wenn das Modell von wenigen extremen Annahmen getragen wird."""
    z = R["zus"]
    proj = z["projektion"]
    r_je = R.get("r_calc", R["r"])
    gew = E.gewichte(m)
    aus = []
    hoch = [(i, r_je.get(i, 0.0)) for i, g in gew.items() if g > 0 and r_je.get(i, 0.0) > 0.5]
    if hoch:
        aus.append("Sehr hohe Renditeannahme: " + ", ".join(
            f"{_asset(m, i)['name']} {_pct(r_)} p.a." for i, r_ in sorted(hoch, key=lambda x: -x[1])[:3])
            + " – über Jahre kaum erreichbar; bitte die Annahme prüfen (z. B. kurze Historie hochgerechnet).")
    cagr = z.get("modell_cagr")
    ende = proj.get("endwerte_asset") or {}
    summe = sum(ende.values()) or 0.0
    if cagr is not None and summe > 0 and cagr - port_r > 0.05:
        haupt = max(ende, key=ende.get)
        anteil_ende = ende[haupt] / summe
        aus.append(f"Die modellierte Rendite ({_pct(cagr)}) liegt weit über der Startrendite ({_pct(port_r)}): "
                   f"{_asset(m, haupt)['name']} wächst von {_pct(gew.get(haupt, 0.0))} auf {_pct(anteil_ende)} "
                   "des Depots (ohne Rebalancing) und trägt fast den ganzen Endwert.")
    return aus



# ===========================================================================
# Gefuehrter Ablauf (Schritt fuer Schritt) - nur Oberflaeche, gleiche Logik
# ===========================================================================
SCHRITTE = [
    {"icon": "🎯", "titel": "Ziel & Rahmen",
     "text": "Startkapital, Sparrate, Dauer und optional ein Zielvermögen festlegen. Entnahme und erweiterte "
             "Einstellungen sind eingeklappt und nur bei Bedarf nötig.", "seiten": []},
    {"icon": "🧩", "titel": "Bausteine",
     "text": "ETFs, Aktien und Wikifolios auswählen – am schnellsten über den Katalog mit Score und Analyse.",
     "seiten": ["Auswahl", "Aktienkorb", "Wikifolios"]},
    {"icon": "⚖️", "titel": "Gewichtung",
     "text": "Anteile festlegen – von Hand in der Tabelle, automatisch nach Ziel/Regeln oder auf ganze Stücke.",
     "seiten": ["Gewichte", "Aufteilung", "Kaufplan"]},
    {"icon": "🛠️", "titel": "Erweitert",
     "text": "Optional: Kredite, Risiko-Checks und die Herkunft der Renditeannahmen. Für ein erstes Portfolio "
             "nicht nötig.", "seiten": ["Kredit", "Konzentration", "Sensitivität", "Stress & Reserve",
                                       "Annahmen & Quellen"]},
    {"icon": "✅", "titel": "Prüfen & Speichern",
     "text": "Alles auf einen Blick prüfen, Ergebnis und Szenarien ansehen und das Modell speichern.",
     "seiten": ["Überblick", "Wachstum", "Ziel", "Szenarien", "Entnahme", "Speichern"]},
]
ANSICHTEN = ["🧭 Schritt für Schritt", "🗂️ Alle Bereiche"]

WZ_CSS = """
<style>
.wz-stepper { display: flex; gap: 6px; margin: 4px 0 6px; }
.wz-step { flex: 1 1 0; min-width: 0; text-align: center; font-size: 0.8rem; color: #8A9099; font-weight: 700; }
.wz-dot { width: 26px; height: 26px; border-radius: 50%; margin: 0 auto 3px; display: flex; align-items: center;
          justify-content: center; font-size: 0.8rem; font-weight: 900; border: 1.5px solid rgba(255,255,255,0.25);
          color: #D6D9DE; background: transparent; }
.wz-step.ok .wz-dot { background: rgba(22,199,132,0.18); border-color: #16C784; color: #16C784; }
.wz-step.warn .wz-dot { background: rgba(245,185,66,0.15); border-color: #F5B942; color: #F5B942; }
.wz-step.fehler .wz-dot { background: rgba(234,57,67,0.15); border-color: #EA3943; color: #EA3943; }
.wz-step.aktiv .wz-dot { box-shadow: 0 0 0 3px rgba(76,154,255,0.45); border-color: #4C9AFF; }
.wz-step.aktiv { color: #FFFFFF; }
.wz-lbl { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wz-bar { height: 5px; border-radius: 3px; background: rgba(255,255,255,0.08); overflow: hidden; margin: 2px 0 10px; }
.wz-bar > div { height: 100%; background: linear-gradient(90deg, #4C9AFF, #16C784); border-radius: 3px; }
.wz-kopf { border: 1px solid rgba(76,154,255,0.35); background: rgba(76,154,255,0.06); border-radius: 12px;
           padding: 10px 14px; margin: 4px 0 12px; }
.wz-kopf .wz-nr { font-size: 0.8rem; letter-spacing: 1.2px; text-transform: uppercase; color: #8DBBFF; font-weight: 800; }
.wz-kopf .wz-t { font-size: 1.05rem; font-weight: 900; color: #FFFFFF; margin: 1px 0 2px; }
.wz-kopf .wz-d { font-size: 0.8rem; color: #C9CDD3; line-height: 1.45; }
.wz-check { font-size: 0.82rem; color: #D6D9DE; margin: 3px 0; line-height: 1.4; }
.wz-vs { border: 1px solid rgba(255,255,255,0.14); border-radius: 12px; padding: 10px 12px; background: rgba(255,255,255,0.025); }
.wz-vs-t { font-size: 0.8rem; letter-spacing: 1.2px; text-transform: uppercase; font-weight: 800; color: #FFFFFF;
           margin-bottom: 4px; }
.wz-vs-k { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 6px 0; }
.wz-vs-k div { background: rgba(255,255,255,0.04); border-radius: 8px; padding: 5px 7px; font-size: 0.8rem; color: #8A9099; }
.wz-vs-k b { display: block; font-size: 0.92rem; color: #FFFFFF; }
.wz-liste { margin: 2px 0 8px; }
.wz-row { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-size: 0.8rem;
          color: #C9CDD3; padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.06); }
.wz-row span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wz-row span i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; }
.wz-row b { color: #FFFFFF; white-space: nowrap; font-variant-numeric: tabular-nums; }
.wz-kz .wz-row { font-size: 0.82rem; }
.wz-vs-u { font-size: 0.8rem; letter-spacing: 1.1px; text-transform: uppercase; color: #8A9099; font-weight: 800;
           margin: 10px 0 2px; }
.wz-mehr { font-size: 0.8rem; color: #8A9099; padding-top: 4px; }
.wz-hinweis { font-size: 0.8rem; color: #8DBBFF; background: rgba(76,154,255,0.08); border-radius: 8px;
              padding: 5px 8px; margin: 4px 0 8px; }
.wz-hinweis.wz-rot { color: #F5A3A8; background: rgba(234,57,67,0.1); }
.wz-leer { border: 1px dashed rgba(255,255,255,0.25); border-radius: 12px; padding: 14px; text-align: center;
           color: #C9CDD3; font-size: 0.84rem; margin: 6px 0 10px; }
.st-key-pl_wz_weiter button { background: #16305A !important; border: 1px solid #4C9AFF !important; min-height: 46px; }
.st-key-pl_wz_weiter button, .st-key-pl_wz_weiter button * { color: #FFFFFF !important; font-weight: 800 !important; }
.st-key-pl_wz_ziel button { border: 1px solid #F5B942 !important; }
@media (max-width: 700px) { .wz-lbl { font-size: 0.8rem; } .wz-dot { width: 24px; height: 24px; } }
</style>
"""


def _pruefungen(m, R):
    """Pruefliste fuer den gefuehrten Ablauf -> [(stufe 'fehler'|'warnung'|'ok', text, schritt)]."""
    r = m["rahmen"]
    aus = []
    kredit = bool(m.get("kredit")) and any(float(x.get("betrag") or 0) > 0
                                           for x in (_kredite(m).get("kredite") or []))
    if float(r.get("startkapital") or 0) <= 0 and float(r.get("sparrate_monat") or 0) <= 0 and not kredit:
        aus.append(("fehler", "Startkapital oder Sparrate fehlt", 0))
    else:
        aus.append(("ok", f"Kapital: {_de(r.get('startkapital') or 0)} € Start"
                    + (f" + {_de(r.get('sparrate_monat'))} €/Monat" if float(r.get("sparrate_monat") or 0) else "")
                    + f", {int(r.get('horizont_jahre') or 0)} J. Aufbau", 0))
    aktiv = [a for a in E.aktive_assets(m) if a.get("category") != "cash"]
    if not aktiv:
        aus.append(("fehler", "Noch kein Baustein aktiv", 1))
    else:
        aus.append(("ok", f"{len(aktiv)} Bausteine aktiv", 1))
        ohne = [a["name"] for a in aktiv if _basis_text(m, a) == "fehlt"]
        if ohne:
            aus.append(("warnung", "Ohne Renditeannahme (rechnet mit 0 %): " + ", ".join(ohne[:4]), 1))
    summe = E.gewichte_summe(m)
    if aktiv and abs(summe - 100.0) > 0.05 and not _auto_modus(m):
        aus.append(("fehler", f"Gewichte ergeben {_de(summe, 1)} % statt 100 %", 2))
    elif aktiv and summe > 0:
        aus.append(("ok", f"Gewichte ergeben {_de(summe, 1)} %" + (" (automatisch)" if _auto_modus(m) else ""), 2))
    try:
        port_r = sum(g * R.get("r_calc", R["r"]).get(i, 0.0) for i, g in E.gewichte(m).items())
        for t in _plausibilitaet(m, R, port_r):
            aus.append(("warnung", t, 2))
    except Exception:
        pass
    if aktiv:
        verletzt = E.regeln_verletzungen(m) if abs(summe - 100.0) <= 0.05 else []
        if verletzt:
            aus.append(("warnung", "Regeln verletzt: " + " · ".join(verletzt), 2))
    z = R.get("zus") or {}
    fehl = _fehlbetrag_text(z) if z else ""
    if fehl:
        aus.append(("warnung", fehl, 0))
    ziel = float(r.get("zielvermoegen") or 0)
    if ziel > 0 and int(r.get("horizont_jahre") or 0) > 0 and aktiv and z:
        if z.get("ziel_erreicht"):
            aus.append(("ok", f"Zielvermögen {_de(ziel)} € wird im Modell erreicht", 4))
        else:
            aus.append(("warnung", f"Zielvermögen {_de(ziel)} € wird im Modell nicht erreicht", 4))
    return aus


def _schritt_status(pruef, i, besucht):
    stufen = [st_ for st_, _, s_ in pruef if s_ == i]
    if "fehler" in stufen:
        return "fehler"
    if "warnung" in stufen:
        return "warn"
    if i == 3:                    # optional
        return "ok" if besucht else ""
    if i == 4:
        return "ok" if besucht and not any(x[0] == "fehler" for x in pruef) else ""
    return "ok" if "ok" in stufen else ""


def _stepper_html(pruef, aktiv_i):
    besucht = st.session_state.setdefault("pl_wz_besucht", set())
    besucht.add(aktiv_i)
    teile, fertig = [], 0
    for i, s_ in enumerate(SCHRITTE):
        status = _schritt_status(pruef, i, i in besucht)
        fertig += status == "ok"
        zeichen = {"ok": "✓", "warn": "!", "fehler": "✕"}.get(status, str(i + 1))
        teile.append(f'<div class="wz-step {status}{" aktiv" if i == aktiv_i else ""}">'
                     f'<div class="wz-dot">{zeichen}</div><span class="wz-lbl">{_esc(s_["titel"])}</span></div>')
    return (f'<div class="wz-stepper" role="list" aria-label="Fortschritt">{"".join(teile)}</div>'
            f'<div class="wz-bar" aria-label="{fertig} von {len(SCHRITTE)} Schritten erledigt">'
            f'<div style="width:{fertig / len(SCHRITTE) * 100:.0f}%"></div></div>')


def _geh_zu(i, seite=None):
    st.session_state["pl_schritt"] = i
    if seite:
        st.session_state[f"pl_wz_seite_{i}"] = seite


def _schritt_navigation(pruef, i):
    """Zurueck / Weiter unten und der naechste sinnvolle Schritt."""
    fehler = [(t, s_) for st_, t, s_ in pruef if st_ == "fehler"]
    if fehler and fehler[0][1] != i:
        t, s_ = fehler[0]
        c1, c2 = st.columns([3, 2])
        c1.markdown(f'<div class="wz-check">👉 <b>Nächster Schritt:</b> {_esc(t)}</div>', unsafe_allow_html=True)
        with c2.container(key="pl_wz_ziel"):
            st.button(f"Zu {SCHRITTE[s_]['icon']} {SCHRITTE[s_]['titel']}", key="pl_wz_fix", width="stretch",
                      on_click=_geh_zu, args=(s_,))
    c1, c2 = st.columns([1, 2])
    c1.button("← Zurück", key="pl_wz_zurueck", width="stretch", disabled=i == 0, on_click=_geh_zu,
              args=(max(i - 1, 0),))
    if i < len(SCHRITTE) - 1:
        nxt = SCHRITTE[i + 1]
        with c2.container(key="pl_wz_weiter"):
            st.button(f"Weiter: {nxt['icon']} {nxt['titel']} →", key="pl_wz_weiter_btn", width="stretch",
                      on_click=_geh_zu, args=(i + 1,))
    else:
        c2.caption("✓ Letzter Schritt – Änderungen werden automatisch gespeichert; unter „Speichern“ als eigenes "
                   "Modell sichern.")


def _vs_gewicht(aid):
    m = st.session_state.get("planer_modell")
    wert = st.session_state.get(_k(f"vs_w_{aid}"))
    if not m or wert is None:
        return
    for a in m["assets"]:
        if a["id"] == aid:
            a["targetWeight"] = float(wert)
            a["enabled"] = float(wert) > 0 or a.get("enabled")
    _neu_zeichnen()


def _vs_aus(aid):
    m = st.session_state.get("planer_modell")
    for a in (m or {}).get("assets", []):
        if a["id"] == aid:
            a["enabled"], a["targetWeight"] = False, 0.0
    st.session_state["planer_meldung"] = ("ok", f"„{_asset(m, aid)['name']}“ deaktiviert (0 %) – in Schritt 2 "
                                          "über „Aktiv“ wieder einschaltbar.", [])
    _neu_zeichnen()


def _vs_normalisieren():
    m = st.session_state.get("planer_modell")
    if m:
        E.normalisieren(m)
        _neu_zeichnen()


VS_GRUPPEN = {"index": ("ETFs & Indizes", "#4C9AFF"), "aktie": ("Aktien", "#A78BFA"),
              "wikifolio": ("Wikifolios", "#16C784"), "hebel": ("Hebel-Produkte", "#F5B942"),
              "krypto": ("Krypto", "#FB923C"), "cash": ("Reserve / Cash", "#94A3B8")}
VS_TOP = 8


def _vorschau(m, R, mobil=False):
    """Kompakte, live aktualisierte Portfolio-Vorschau: Aufteilung nach Art (Donut), Eckdaten als
    Liste, die groessten Positionen und EIN Bearbeitungsfeld (passt auch in eine schmale Spalte)."""
    w = E.gewichte(m)
    summe = E.gewichte_summe(m)
    z = R.get("zus") or {}
    rahmen = m["rahmen"]
    auto = _auto_modus(m)
    port_r = sum(g * R.get("r_calc", R["r"]).get(i, 0.0) for i, g in w.items())
    st.markdown('<div class="wz-vs-t">📊 Dein Portfolio</div>', unsafe_allow_html=True)
    ids = sorted([a["id"] for a in E.aktive_assets(m) if w.get(a["id"], 0) > 0], key=lambda i: -w[i])
    if not ids or summe <= 0:
        st.markdown('<div class="wz-leer">Noch keine Bausteine gewichtet.<br>Wähle in Schritt 2 ETFs, Aktien oder '
                    'Wikifolios aus – sie erscheinen dann hier.</div>', unsafe_allow_html=True)
        st.button("🧩 Bausteine auswählen", key="pl_vs_leer", width="stretch", on_click=_geh_zu, args=(1,))
        return
    # 1) Aufteilung nach Art - wenige, feste Farben statt einer Farbe je Position
    gruppen = {}
    for i in ids:
        typ = D.KATEGORIEN.get(_asset(m, i)["category"], {}).get("typ", "index")
        gruppen[typ] = gruppen.get(typ, 0.0) + w[i] * 100
    reihen = sorted(gruppen.items(), key=lambda x: -x[1])
    ok_summe = abs(summe - 100) <= 0.05
    fig = go.Figure(go.Pie(labels=[VS_GRUPPEN.get(k, (k, "#94A3B8"))[0] for k, _ in reihen],
                           values=[v for _, v in reihen], hole=0.7, sort=False, direction="clockwise",
                           marker=dict(colors=[VS_GRUPPEN.get(k, (k, "#94A3B8"))[1] for k, _ in reihen],
                                       line=dict(color="#0B0C0E", width=2)),
                           textinfo="none", hovertemplate="%{label}: %{value:.1f} %<extra></extra>"))
    fig.update_layout(height=150 if mobil else 165, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      annotations=[dict(text=f"<b>{_de(summe, 1)} %</b><br><span style='font-size:12px'>"
                                         f"{len(ids)} Positionen</span>", x=0.5, y=0.5, showarrow=False,
                                        font=dict(size=15, color="#FFFFFF" if (ok_summe or auto) else "#EA3943"))])
    _chart(fig, "pl_vs_donut")
    st.markdown('<div class="wz-liste">' + "".join(
        f'<div class="wz-row"><span><i style="background:{VS_GRUPPEN.get(k, (k, "#94A3B8"))[1]}"></i>'
        f'{_esc(VS_GRUPPEN.get(k, (k, ""))[0])}</span><b>{_de(v, 1)} %</b></div>' for k, v in reihen)
        + "</div>", unsafe_allow_html=True)
    if not ok_summe and not auto:
        st.markdown(f'<div class="wz-hinweis wz-rot">⚠ Summe {_de(summe, 1)} % – {_de(abs(summe - 100), 1)} % '
                    f'{"zu viel" if summe > 100 else "fehlen"}</div>', unsafe_allow_html=True)
        st.button("Auf 100 % normalisieren", key="pl_vs_norm", width="stretch", on_click=_vs_normalisieren)

    # 2) Eckdaten als Liste (Bezeichnung links, Wert rechts)
    endwert = z.get("endwert_netto", z.get("endwert"))
    kz = [("Rendite Ø am Start", _pct(port_r))]
    if int(rahmen.get("horizont_jahre") or 0) > 0 and endwert is not None:
        kz.append((f"Endwert nach {int(rahmen['horizont_jahre'])} J.", "≈ " + _kurz_eur(E.runden_ungefaehr(endwert))))
        if float(rahmen.get("zielvermoegen") or 0) > 0:
            kz.append(("Ziel " + _kurz_eur(float(rahmen["zielvermoegen"])),
                       '<span class="pl-gut">✓ erreicht</span>' if z.get("ziel_erreicht")
                       else '<span class="pl-schlecht">✕ nicht erreicht</span>'))
    st.markdown('<div class="wz-liste wz-kz">' + "".join(
        f'<div class="wz-row"><span>{_esc(l)}</span><b>{v if "<span" in v else _esc(v)}</b></div>' for l, v in kz)
        + "</div>", unsafe_allow_html=True)
    if auto:
        st.markdown('<div class="wz-hinweis">⚙️ Gewichte automatisch ' + {
            "ziel": "aufs Zielvermögen", "manuell": "auf die feste Rendite",
            "entnahme": "auf die Entnahme-Rendite"}.get(auto, "") + " verteilt</div>", unsafe_allow_html=True)

    # 3) Groesste Positionen
    st.markdown('<div class="wz-vs-u">Größte Positionen</div><div class="wz-liste">' + "".join(
        f'<div class="wz-row"><span>{_esc(_asset(m, i)["name"])}</span><b>{_de(w[i] * 100, 1)} %</b></div>'
        for i in ids[:VS_TOP]) + (f'<div class="wz-mehr">+ {len(ids) - VS_TOP} weitere</div>'
                                  if len(ids) > VS_TOP else "") + "</div>", unsafe_allow_html=True)

    # 4) Eine Position bearbeiten (nur ohne Automatik)
    if not auto:
        with st.expander("✏️ Position ändern"):
            if st.session_state.get("pl_vs_wahl") not in ids:
                st.session_state.pop("pl_vs_wahl", None)
            i = st.selectbox("Position", ids, format_func=lambda x: _asset(m, x)["name"], key="pl_vs_wahl",
                             label_visibility="collapsed")
            a = _asset(m, i)
            st.number_input("Gewicht %", 0.0, 100.0, float(a.get("targetWeight") or 0.0), step=0.5, format="%.1f",
                            key=_k(f"vs_w_{i}"), on_change=_vs_gewicht, args=(i,))
            st.button("Deaktivieren (0 %)", key=_k(f"vs_x_{i}"), width="stretch", on_click=_vs_aus, args=(i,),
                      help="Bleibt in der Liste und ist in Schritt 2 jederzeit wieder einschaltbar")


def _b_ueberblick(m, R, platz):
    """Pruefen: Checkliste, Eckdaten und die KPI-Kacheln (werden nach der Rechnung gefuellt)."""
    pruef = _pruefungen(m, R)
    _abschnitt("Checkliste")
    farbe = {"ok": "✅", "warnung": "⚠️", "fehler": "❌"}
    for stufe, t, s_ in sorted(pruef, key=lambda x: ({"fehler": 0, "warnung": 1, "ok": 2}[x[0]], x[2])):
        c1, c2 = st.columns([5, 2], vertical_alignment="center")
        c1.markdown(f'<div class="wz-check">{farbe[stufe]} {_esc(t)}</div>', unsafe_allow_html=True)
        if stufe != "ok":
            c2.button(f"→ {SCHRITTE[s_]['titel']}", key=f"pl_ue_{s_}_{zlib.crc32(t.encode())}", width="stretch",
                      on_click=_geh_zu, args=(s_,))
    if not any(x[0] == "fehler" for x in pruef):
        st.success("Das Portfolio ist vollständig. Es wird automatisch gespeichert – unter „Speichern“ kannst "
                   "du es zusätzlich unter einem eigenen Namen sichern.")
    _abschnitt("Ergebnis auf einen Blick")
    platz["kpi"] = st.empty()


def _schritt_kopf(i):
    s_ = SCHRITTE[i]
    st.markdown(f'<div class="wz-kopf"><div class="wz-nr">Schritt {i + 1} von {len(SCHRITTE)}'
                + (" · optional" if i == 3 else "") + f'</div><div class="wz-t">{s_["icon"]} {_esc(s_["titel"])}</div>'
                f'<div class="wz-d">{_esc(s_["text"])}</div></div>', unsafe_allow_html=True)

def _kpis(platz, m, R):
    z = R["zus"]
    rahmen = m["rahmen"]
    jahre_n = int(rahmen.get("horizont_jahre") or 0)
    ziel = float(rahmen.get("zielvermoegen") or 0)
    diff = z["differenz"]
    farbe = "pl-gut" if diff >= 0 else "pl-schlecht"
    w = E.gewichte(m)
    port_r = sum(g * R.get("r_calc", R["r"]).get(i, 0.0) for i, g in w.items())      # Portfoliorendite p.a. (gewichtet)
    with platz.container():
        if jahre_n <= 0:
            k1 = ("Aufbau", "–", "keine Aufbauphase (0 Jahre)")
            k2 = ("Portfolio-Rendite p.a.", _pct(port_r), "gewichtet · " + D.METHODEN[rahmen["methode"]])
            k3 = ("Startkapital", _eur(z["endwert"]), "Entnahme startet sofort")
        else:
            k1 = ("Benötigte Rendite p.a.", (_pct(z["erforderliche_cagr"]) if z["erforderliche_cagr"] is not None
                                             else "nicht erreichbar") if ziel > 0 else "–",
                  (_kurz_eur(rahmen["startkapital"])
                   + (f' + {_kurz_eur(z["kredit"]["summe"])} Kredit' if z.get("kredit") else "")
                   + f' → {_kurz_eur(ziel)} in {jahre_n} J.') if ziel > 0 else "kein Ziel gesetzt")
            k2 = ("Modellierte Rendite p.a.", _pct(z["modell_cagr"]), D.METHODEN[rahmen["methode"]])
            if z.get("kredit"):
                k3 = ("Modell-Endwert", "≈ " + _kurz_eur(E.runden_ungefaehr(z["endwert_netto"])),
                      f'nach {jahre_n} J., abzgl. Restschuld {_kurz_eur(z["kredit"]["restschuld"])}')
            else:
                k3 = ("Modell-Endwert", "≈ " + _kurz_eur(E.runden_ungefaehr(z["endwert"])), f'nach {jahre_n} J.')
        if ziel > 0 and jahre_n > 0:
            k4 = ("Abstand zum Ziel", f'<span class="{farbe}">{"+" if diff >= 0 else "−"}'
                                      f'{_kurz_eur(abs(E.runden_ungefaehr(diff) or 0))}</span>',
                  f'Ziel {_kurz_eur(ziel)} ' + ("✓ erreicht" if z["ziel_erreicht"] else "nicht erreicht"))
        else:
            k4 = ("Portfolio-Rendite p.a." if jahre_n > 0 else "Positionen", _pct(port_r) if jahre_n > 0
                  else str(sum(1 for g in w.values() if g > 0)), "gewichtet" if jahre_n > 0 else "mit Gewicht")
        _kacheln([k1, k2, k3, k4], klasse="pl-kpis")
        proj = z["projektion"]
        zeilen = []
        if jahre_n > 0:
            for t in _plausibilitaet(m, R, port_r):
                zeilen.append(f'<b class="pl-schlecht">⚠ {_esc(t)}</b>')
        if jahre_n > 0:
            zeilen.append(f'Multiplikator <b>{_de(z["multiplikator"], 2)}×</b>'
                          + (f' · Einzahlungen gesamt {_de(proj["eingezahlt"])} €' if rahmen.get("sparrate_monat") else ""))
            zeilen.append(" · ".join(f"J{j}: {_eur(v)}" for j, v in enumerate(proj["jahreswerte"]) if j))
        e = _entnahme_daten(m)
        if e.get("aktiv", True):
            try:
                _kap, _r, _kw, plan = _entnahme_rechnen(m, R, e)
                dauer = "dauerhaft" if plan["reicht_dauerhaft"] else _dauer_text(plan)
                ok = plan["reicht_dauerhaft"] or plan["dauer_monate"] >= int(e["dauer_jahre"]) * 12
                zeilen.append(f'{("Nach dem Aufbau weiter" if _entnahme_parallel(m) else "Danach") if jahre_n > 0 else "Sofort"} Entnahme <b>{_de(e["monatlich"])} €/Monat</b>{_stufen_text(e)} '
                              f'aus {_eur(_kap)} bei {_pct(_r)} p.a. · reicht '
                              f'<b class="{"pl-gut" if ok else "pl-schlecht"}">{dauer}</b> (Plan {e["dauer_jahre"]} J.)')
                if _entnahme_parallel(m):
                    zeilen.insert(0 if not jahre_n else 2,
                                  f'Entnahme während des Aufbaus: <b>{_de(e["monatlich"])} €/Monat</b> ab sofort{_stufen_text(e)} · '
                                  f'gesamt {_eur(proj.get("entnommen") or 0)} in {jahre_n} J.')
                    # Rechenweg: ohne Entnahme -> Entnahmen inkl. entgangener Rendite -> Restschuld -> Endwert
                    try:
                        eff_m = _mit_krediten(m)
                        ohne_m = dict(eff_m, rahmen={k_: v_ for k_, v_ in eff_m["rahmen"].items()
                                                     if k_ != "entnahme_parallel"})
                        ohne_ew = E.projektion(ohne_m, R.get("r_calc", R["r"]), rebalancing=R["reb"])["endwert"]
                        kr_ = R["zus"].get("kredit")
                        rs_ = kr_["restschuld"] if kr_ else 0.0
                        kosten_ent = ohne_ew - proj["endwert"]
                        zeilen.insert(1 if not jahre_n else 3,
                                      f'Rechenweg: {_de(eff_m["rahmen"]["startkapital"])} € Kapital'
                                      + (f' + {_de(eff_m["rahmen"]["sparrate_monat"])} €/Monat'
                                         if float(eff_m["rahmen"].get("sparrate_monat") or 0) else "")
                                      + (f' − Kreditraten aus dem Depot {_eur(proj.get("kredit_raten_gezahlt") or 0)}'
                                         if eff_m["rahmen"].get("kredit_raten") else "")
                                      + f' ohne Entnahme → {_eur(ohne_ew)} · − Entnahmen inkl. entgangener Rendite '
                                        f'{_eur(kosten_ent)}' + (f' · − Restschuld {_eur(rs_)}' if rs_ else "")
                                      + f' = <b>{_eur(proj["endwert"] - rs_)}</b>')
                    except Exception:
                        pass
                b = _monatsbilanz(m, R)
                teile = [f'Gewinn {_de(b["gewinn_monat"])} €']
                if b["spar"]:
                    teile.append(f'+ Sparrate {_de(b["spar"])} €')
                if b["entnahme"]:
                    teile.append(f'− Entnahme {_de(b["entnahme"])} €')
                if b["raten_depot"]:
                    teile.append(f'− Raten {_de(b["raten_depot"])} €')
                sb = b["saldo"]
                zeilen.append("Monatsbilanz: " + " ".join(teile)
                              + f' = <b class="{"pl-gut" if sb >= 0 else "pl-schlecht"}">{"+" if sb >= 0 else "−"}'
                                f'{_de(abs(sb))} €/Monat → {"Depot wächst" if sb > 0 else "Depot schrumpft"}</b>')
            except Exception:
                pass
        try:
            kr = _kredit_rechnen(m, R)
        except Exception:
            kr = None
        if kr:
            vv = kr["vorteil"]
            zeilen.append(f'Mit Krediten ({_de(kr["summe"])} €, {_de(kr["rate"], 2)} €/Monat): nach {kr["horizont"]} J. '
                          f'<b>{_eur(kr["mit"])}</b> netto · ohne {_eur(kr["ohne"])} · '
                          f'<b class="{"pl-gut" if vv >= 0 else "pl-schlecht"}">{"+" if vv >= 0 else "−"}'
                          f'{_de(abs(vv))} €</b>')
        fehl = _fehlbetrag_text(z)
        if fehl:
            zeilen.insert(0, f'<b class="pl-schlecht">{_esc(fehl)}</b>')
        auto = st.session_state.get("planer_autogew")
        if auto and auto.get("fehler"):
            zeilen.append(f'⚠ Automatische Gewichtung: {_esc(auto["fehler"])}')
        elif auto and auto.get("modus") == "ziel" and _ziel_in_entnahme(m):
            if auto["erreichbar"]:
                zeilen.append(f'Gewichte automatisch aufs Ziel verteilt · benötigt <b>{_pct(auto["benoetigt"])} p.a.</b> '
                              f'in der Entnahme · Rest nach {e["dauer_jahre"]} J. ≈ {_de(rahmen["zielvermoegen"])} €')
            else:
                zeilen.append(f'⚠ Ziel mit diesen Bausteinen nicht erreichbar (benötigt {_pct(auto["benoetigt"])} p.a., '
                              f'höchstens {_pct(auto["max"])})')
        elif auto and auto.get("modus") == "ziel":
            if auto["erreichbar"]:
                zeilen.append(f'Gewichte automatisch aufs Ziel verteilt · benötigt <b>{_pct(auto["benoetigt"])} p.a.</b>'
                              f' · Modell-Endwert {_eur(auto["endwert"])}')
            else:
                zeilen.append('⚠ Ziel mit diesen Bausteinen nicht erreichbar ('
                              + (f'benötigt {_pct(auto["benoetigt"])} p.a.' if auto.get("benoetigt") is not None
                                 else "auch mit extremer Rendite nicht erreichbar")
                              + f') – renditestärkste Verteilung ergibt {_eur(auto["endwert"])}')
        elif auto and auto.get("modus") == "manuell":
            if auto.get("erreichbar"):
                zeilen.append(f'Manuelle Rendite: Gewichte auf <b>{_pct(auto["rendite"])} p.a.</b> verteilt')
            else:
                zeilen.append(f'⚠ Manuelle Rendite {_pct(auto["soll"])} p.a. mit diesen Bausteinen nicht genau '
                              f'erreichbar – gerechnet wird mit <b>{_pct(auto["rendite"])} p.a.</b> '
                              f'(möglich {_pct(auto["min"])} bis {_pct(auto["max"])})')
            ben = _benoetigt(m)
            if ben is not None:
                zeilen.append(f'Fürs Zielvermögen benötigt: {_pct(ben)} p.a. → Ziel '
                              + ("erreicht" if auto["rendite"] >= ben - 1e-4 else "<b class=\"pl-schlecht\">verfehlt</b>"))
        elif auto:
            zeilen.append(("Gewichte automatisch auf " if auto["erreichbar"] else "⚠ Höchstens erreichbar: ")
                          + f'<b>{_pct(auto["rendite"])} p.a.</b> ausgerichtet'
                          + ("" if auto["erreichbar"] else f' (mit diesen Bausteinen max. {_pct(auto["max"])})'))
        fa = st.session_state.get("planer_feinabgleich") or {}
        if fa.get("geaendert"):
            res = _asset(m, fa["reserve_id"])
            zeilen.insert(0, f'🎯 Ziel genau getroffen: Schon die defensivste Verteilung lag über dem Ziel – deshalb '
                             f'liegen <b>{_pct(float(res.get("targetWeight") or 0) / 100)}</b> in „{_esc(res["name"])}“, '
                             'die übrigen Bausteine behalten ihr Verhältnis zueinander.'
                             + (' ⚠ Auch fixierte Bausteine mussten verkleinert werden – sie allein lagen schon über '
                                'dem Ziel.' if fa.get("fixierte_angepasst") else ''))
        elif fa.get("fehler") and z.get("differenz", 0) > 0.01 * float(rahmen.get("zielvermoegen") or 0) \
                and _auto_modus(m) == "ziel":
            zeilen.insert(0, f'⚠ Ziel wird überschritten: {_esc(fa["fehler"])} Eine Reserve (Cash) aktivieren, dann wird '
                             'das Ziel genau getroffen.')
        if zeilen:
            warnungen = sum(1 for t in zeilen if "⚠" in t)
            titel = ("⚠️ " if warnungen else "ℹ️ ") + "Rechenweg & Hinweise" + (
                f" · {warnungen} Warnung{'en' if warnungen > 1 else ''}" if warnungen else "")
            with st.expander(titel, expanded=False):
                st.markdown(f'<div class="pl-zeile">{"<br>".join(zeilen)}</div>', unsafe_allow_html=True)
        _hinweis()


def _regeln_daten(m):
    """rahmen["regeln"] im neuen Format (je Anlageklasse min/max) - alte Form wird umgerechnet."""
    rg = m["rahmen"].setdefault("regeln", copy.deepcopy(D.SEED_RAHMEN["regeln"]))
    if "klassen" not in rg:
        kl = copy.deepcopy(D.SEED_RAHMEN["regeln"]["klassen"])
        if "wiki_max" in rg:
            kl["wikifolio"]["max"] = float(rg.pop("wiki_max"))
        if "reserve_min" in rg:
            kl["cash"]["min"] = float(rg.pop("reserve_min"))
        if "reserve_max" in rg:
            kl["cash"]["max"] = float(rg.pop("reserve_max"))
        rg["klassen"] = kl
    for k, v in D.SEED_RAHMEN["regeln"]["klassen"].items():
        rg["klassen"].setdefault(k, dict(v))
    return rg


def _regeln_editor(m, pre=""):
    """Gewichtung je Anlageklasse manuell begrenzen (min/max %) - gilt fuer jede Automatik."""
    rg = _regeln_daten(m)
    rg["aktiv"] = st.toggle(
        "Gewichtungs-Regeln je Kategorie (Wikifolios, ETFs, Aktien, Reserve …)", value=bool(rg.get("aktiv", True)),
        key=_k(pre + "regeln_aktiv"),
        help="Min./Max. % je Kategorie. Gilt für jede automatische Gewichtung (Zielvermögen, manuelle Rendite, "
             "Vorschläge, Optimierer). Zu viel in einer Kategorie wird anteilig auf die anderen verteilt. "
             "Min. = Max. ergibt einen festen Anteil.")
    if not rg["aktiv"]:
        return
    ist = E.klassen_anteile(m)
    df = pd.DataFrame([{"Kategorie": D.REGEL_KLASSEN[k], "Min %": float(rg["klassen"][k]["min"]),
                        "Max %": float(rg["klassen"][k]["max"]),
                        "Ist %": round(ist.get(k, 0.0), 1) if k in ist else None}
                       for k in D.REGEL_KLASSEN])
    ed = st.data_editor(
        df, key=_k(f"{pre}regeln_tab_{st.session_state.get('planer_rg_ver', 0)}"), hide_index=True, width="stretch",
        num_rows="fixed", height=_hoehe(len(df)), disabled=["Kategorie", "Ist %"],
        column_config={
            "Kategorie": st.column_config.TextColumn("Kategorie"),
            "Min %": st.column_config.NumberColumn("Min %", min_value=0.0, max_value=100.0, step=1.0, format="%.0f"),
            "Max %": st.column_config.NumberColumn("Max %", min_value=0.0, max_value=100.0, step=1.0, format="%.0f"),
            "Ist %": st.column_config.NumberColumn("Ist %", format="%.1f",
                                                   help="Aktueller Anteil (leer = kein Baustein dieser Kategorie aktiv)"),
        })
    if ed is not None and len(ed) == len(df):
        neu = {}
        for k, (_, z) in zip(D.REGEL_KLASSEN, ed.iterrows()):
            lo = 0.0 if pd.isna(z["Min %"]) else float(z["Min %"])
            hi = 100.0 if pd.isna(z["Max %"]) else float(z["Max %"])
            neu[k] = {"min": lo, "max": max(hi, lo)}
        if _norm(neu) != _norm(rg["klassen"]):
            rg["klassen"] = neu
            st.session_state["planer_rg_ver"] = st.session_state.get("planer_rg_ver", 0) + 1
            st.rerun()
    summe_min = sum(v["min"] for k, v in rg["klassen"].items() if k in ist)
    summe_max = sum(v["max"] for k, v in rg["klassen"].items() if k in ist)
    if summe_min > 100.0 + 1e-6:
        st.caption(f"⚠ Die Mindestanteile ergeben zusammen {_de(summe_min)} % – mehr als 100 %.")
    if summe_max < 100.0 - 1e-6:
        st.caption(f"⚠ Die Höchstanteile der aktiven Kategorien ergeben nur {_de(summe_max)} % – weniger als 100 %.")
    if "cash" not in ist and rg["klassen"]["cash"]["min"] > 0:
        st.caption("⚠ Keine Nachkaufreserve (Cash-Baustein) aktiv – unter 🧩 Portfolio → Bausteine aktivieren.")
    st.caption("Gilt für die automatische Gewichtung. Eigene Gewichte werden nicht verändert – bei Abweichung "
               "erscheint oben ein Hinweis mit „Auf Regeln ausrichten“.")


def _leer_hinweise(m):
    """Hinweise fuer ein (noch) leeres Modell - z. B. neuer Benutzer, alles auf 0."""
    r = m["rahmen"]
    aus = []
    kredit = bool(m.get("kredit")) and any(float(x.get("betrag") or 0) > 0
                                           for x in (_kredite(m).get("kredite") or []))
    if float(r.get("startkapital") or 0) <= 0 and float(r.get("sparrate_monat") or 0) <= 0 and not kredit:
        aus.append("Trag Startkapital oder Sparrate ein – unter „🎯 Ziel & Rahmen“ (Schritt 1) bzw. „⚙️ Planung: Aufbau → Entnahme“ "
                   "(dort auch die Dauer des Aufbaus und ein Zielvermögen).")
    if E.gewichte_summe(m) <= 0:
        aus.append("Noch keine Bausteine gewichtet – unter „🧩 Portfolio → Bausteine“ „Aktiv“ anhaken und "
                   "Gewichte vergeben (oder unter „⚖️ Gewichtung“ automatisch verteilen).")
    return aus


def _gewichtswarnung(platz, m, leer_zeigen=True):
    summe = E.gewichte_summe(m)
    leer = _leer_hinweise(m) if leer_zeigen else []
    if leer:
        with platz.container():
            for t in leer:
                st.info(t)
        if summe <= 0:
            return
    verletzt = E.regeln_verletzungen(m) if abs(summe - 100.0) <= 0.05 else []
    if verletzt:
        with platz.container():
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.warning("Regeln verletzt: " + " · ".join(verletzt))
            if c2.button("Auf Regeln ausrichten", key=_k("regeln_oben"), width="stretch"):
                g = E.regeln_anwenden(m, {a["id"]: float(a.get("targetWeight") or 0) for a in E.aktive_assets(m)})
                for a in E.aktive_assets(m):
                    if a["id"] in g:
                        a["targetWeight"] = round(g[a["id"]], 3)
                _neu_zeichnen()
                st.rerun()
        return
    if abs(summe - 100.0) > 0.05:
        with platz.container():
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.warning(f"Portfolio = {_de(summe, 1)} % – die Rechnung skaliert auf 100 %.")
            if c2.button("Gewichte normalisieren", key=_k("norm_oben"), width="stretch"):
                E.normalisieren(m)
                _neu_zeichnen()
                st.rerun()


# --- Katalog: Bausteine nach Kennzahlen auswaehlen ---------------------------
PFAD_KATALOG = "state/planer/katalog.json"
KATALOG_GRUPPEN = {
    "Rendite": ["1J %", "3J p.a.", "5J p.a.", "10J p.a."],
    "Risiko": ["Vola 1J", "Max DD", "Risk", "Hebel"],
    "Annahmen": ["Base", "Bear", "Bull", "Conf."],
    "Kosten & Daten": ["Perf.-Fee", "TER", "Historie ab", "Profil", "Gefunden"],
}
KATALOG_SORT = ["5J p.a.", "3J p.a.", "1J %", "10J p.a.", "Vola 1J", "Max DD", "Risk", "Conf.", "Base",
                "Historie ab", "Name"]


def _katalog_daten(h):
    # spaetestens alle 10 Minuten neu lesen - sonst sieht eine offene Sitzung den
    # neuen Stand des Agenten erst nach dem Neuladen der Seite
    d = st.session_state.get("planer_katalog")
    if d is not None and time.time() - st.session_state.get("planer_katalog_zeit", 0) > 600:
        d = None
    if d is None:
        st.session_state["planer_katalog_zeit"] = time.time()
        try:
            d = h["gh_read"](PFAD_KATALOG, {}) or {}
        except Exception:
            d = {}
        st.session_state["planer_katalog"] = d
    return d


def _katalog_laden(h):
    """Kennzahlen aller Katalogwerte aus der echten Kurshistorie (ls-tc.de) -
    parallel geladen und als Tagesstand im GitHub-Speicher abgelegt, damit
    der naechste Aufruf (auch auf einem anderen Geraet) sofort da ist.
    Fehlgeschlagene Werte werden einmal einzeln nachgeladen; klappt es dann
    immer noch nicht, bleibt der letzte gute Stand dieses Werts erhalten."""
    heute = h["heute"].isoformat()
    alt = (_katalog_daten(h).get("werte") or {})

    def aufgabe(k):
        return (k["wkn"], _hist_eines,
                (tuple(x for x in (k["wkn"], k["isin"]) if x), k["typ"] == "wikifolio", heute,
                 h["suche_instrument"], h["get_kurshistorie"], None))

    erg = _parallel([aufgabe(k) for k in D.KATALOG])
    # zweiter Versuch einzeln (die Kursquelle bremst bei vielen parallelen Abrufen)
    for k in D.KATALOG:
        r = erg.get(k["wkn"])
        if not r or r.get("fehler"):
            _, f, args = aufgabe(k)
            time.sleep(0.3)               # der Kursquelle kurz Luft lassen
            try:
                erg[k["wkn"]] = f(*args)
            except Exception as e:
                erg[k["wkn"]] = {"fehler": str(e)}
    werte = {}
    for k in D.KATALOG:
        r = erg.get(k["wkn"]) or {}
        if r and not r.get("fehler"):
            werte[k["wkn"]] = {x: v for x, v in r.items() if x != "monat"}
        elif (alt.get(k["wkn"]) or {}) and not alt[k["wkn"]].get("fehler"):
            werte[k["wkn"]] = dict(alt[k["wkn"]], veraltet=True)          # letzter guter Stand
        else:
            werte[k["wkn"]] = {"fehler": r.get("fehler") or "keine Daten"}
    ok = sum(1 for v in werte.values() if not v.get("fehler"))
    d = {"stand": heute, "berechnet": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), "werte": werte,
         "ok": ok}
    st.session_state["planer_katalog"] = d
    # nur speichern, wenn wenigstens die Haelfte Daten hat - sonst bleibt der alte Stand
    if ok >= len(D.KATALOG) / 2:
        try:
            h["gh_write"](PFAD_KATALOG, d, message="planer: katalog-kennzahlen [skip ci]")
        except Exception:
            pass
    return d


def _im_portfolio(m, k):
    return any((a.get("ticker") or "").upper() == k["wkn"] or (k["isin"] and a.get("isin") == k["isin"])
               for a in m["assets"])


def _name_norm(n):
    n = re.sub(r"[^a-z0-9 ]+", " ", (n or "").lower())
    weg = {"inc", "corp", "corporation", "plc", "ag", "se", "group", "holdings", "holding", "co", "ltd", "the",
           "nv", "sa", "class", "a", "company", "ucits", "etf", "acc", "dist"}
    return "".join(t for t in n.split() if t not in weg)


def _watchlist_kennzahlen(h):
    """Kennzahlen der 72 Katalogwerte aus den Daten der Watchlist (Top 500) -
    dieselben Dateien, die dort angezeigt werden, also ohne eigenen Kursabruf.
    Performance gesamt in % -> p.a. -> {wkn: kennzahlen}"""
    def lies(pfad):
        try:
            return h["gh_read_taeglich"](pfad, None) or {}
        except Exception:
            return {}

    je_wkn, je_name = {}, {}

    def merken(wkn, name, felder):
        felder = {k: v for k, v in felder.items() if v is not None}
        if not felder:
            return
        if wkn:
            je_wkn.setdefault(str(wkn).upper(), {}).update({k: v for k, v in felder.items()
                                                            if k not in je_wkn.get(str(wkn).upper(), {})})
        nn = _name_norm(name)
        if nn:
            alt = je_name.get(nn)
            if alt is None or len(felder) > len(alt):
                je_name[nn] = felder

    # 1) alle Aktien (Index-/Laenderlisten) mit voller Performance je Zeitraum
    for i in range(4):
        d = lies(f"state/top50_alle_{i}.json")
        f = d.get("felder") or []
        if "name" not in f:
            continue
        idx = {k: f.index(k) for k in ("name", "kennung", "1J", "3J", "5J", "10J") if k in f}
        for z in d.get("zeilen") or []:
            merken(z[idx["kennung"]] if "kennung" in idx else None, z[idx["name"]],
                   {zr: z[idx[zr]] for zr in ("1J", "3J", "5J", "10J") if zr in idx})
    # 2) grosser Katalog des Agenten (falls schon vorhanden): alle Werte inkl. ETFs/wikifolios
    for i in range(KATALOG_GROSS_TEILE):
        d = lies(PFAD_KATALOG_GROSS.format(i))
        f = d.get("felder") or []
        for z in d.get("zeilen") or []:
            e = dict(zip(f, z))
            merken(e.get("kennung"), e.get("name"), {zr: e.get(zr) for zr in ("1J", "3J", "5J", "10J", "vola", "maxdd",
                                                                                 "jahre")})
    # 3) Ranglisten je Kategorie (Top 50 und Top 500 je Zeitraum) - ETFs, wikifolios, Aktien
    top = lies("state/top50.json")
    for key, kat in (top.get("kategorien") or {}).items():
        quellen = [(zr, [(e.get("name"), e.get("wkn"), e.get("perf")) for e in liste])
                   for zr, liste in (kat.get("top") or {}).items()]
        lang = lies(f"state/top50_lang_{key}.json")
        quellen += [(zr, [(r[0], r[1], r[2]) for r in liste]) for zr, liste in (lang.get("top") or {}).items()]
        for zr, liste in quellen:
            if zr not in ("1J", "3J", "5J", "10J"):
                continue
            for name, wkn, perf in liste:
                merken(wkn, name, {zr: perf})

    aus = {}
    for k in D.KATALOG:
        p = je_wkn.get(k["wkn"].upper()) or (je_wkn.get(k["isin"].upper()) if k.get("isin") else None)
        if not p:
            nn = _name_norm(k["name"])
            p = je_name.get(nn)
            if p is None and len(nn) >= 4:
                # Praefix nur bei eindeutigem Treffer ("rollsroyce" <-> "rollsroyceholdings")
                kand = [v for n, v in je_name.items() if n.startswith(nn)]
                p = kand[0] if len(kand) == 1 else None
        if not p:
            continue
        pa = {n: None if p.get(zr) is None or p[zr] <= -100 else (1 + p[zr] / 100.0) ** (1.0 / n) - 1
              for zr, n in (("3J", 3), ("5J", 5), ("10J", 10))}
        jahre = p.get("jahre") or (10 if pa[10] is not None else 5 if pa[5] is not None else 3 if pa[3] is not None
                                   else 1)
        aus[k["wkn"]] = {"historical1Y": None if p.get("1J") is None else p["1J"] / 100.0,
                         "historical3Y": pa[3], "historical5Y": pa[5], "historical10Y": pa[10],
                         "vola1y": None if p.get("vola") is None else p["vola"] / 100.0, "maxdd": p.get("maxdd"),
                         "jahre": jahre, "quelle": "Watchlist (Top 500)", "instrument": k["name"]}
    return aus


def _katalog_zeilen(m, werte):
    zeilen = []
    for k in D.KATALOG:
        kz = werte.get(k["wkn"]) or {}
        ok = bool(kz) and not kz.get("fehler")
        typ = D.KATEGORIEN[k["category"]]["typ"]
        vs = E.vorschlag_renditen(kz, typ) if ok else None

        def pct(feld, _kz=kz):
            v = _kz.get(feld) if ok else None
            return None if v is None else round(v * 100, 1)

        zeilen.append({
            "wkn": k["wkn"], "Name": k["name"], "Typ": D.KATALOG_TYPEN[k["typ"]],
            "1J %": pct("historical1Y"), "3J p.a.": pct("historical3Y"), "5J p.a.": pct("historical5Y"),
            "10J p.a.": pct("historical10Y"),
            "Vola 1J": pct("vola1y") if ok and kz.get("vola1y") is not None else pct("vola"),
            "Max DD": round(kz["maxdd"], 1) if ok and kz.get("maxdd") is not None else None,
            "Risk": E.risiko_score(kz.get("vola1y") or kz.get("vola"), kz.get("maxdd"), k["hebel"], k["profil"])
            if ok else None,
            "Hebel": k["hebel"],
            "Base": None if not vs else round(vs["base"] * 100, 1),
            "Bear": None if not vs else round(vs["bear"] * 100, 1),
            "Bull": None if not vs else round(vs["bull"] * 100, 1),
            "Conf.": E.confidence_score(kz.get("jahre"), typ) if ok else None,
            "Perf.-Fee": None if k["perf_fee"] is None else k["perf_fee"] * 100,
            "TER": None if k["ter"] is None else k["ter"] * 100,
            "Historie ab": _datum(kz.get("start")) if ok and kz.get("start") else "",
            "Profil": k["profil"],
            "Gefunden": (kz.get("instrument") or "") if ok else (kz.get("fehler") or ""),
            "Im Portf.": _im_portfolio(m, k),
            "_k": k, "_vs": vs,
        })
    return zeilen


def _spalte(name, pinned=False, **kw):
    """Spaltenkonfiguration; 'pinned' (Name bleibt beim Wischen stehen) nur,
    wenn die Streamlit-Version es kennt."""
    typ = kw.pop("typ", "zahl")
    f = {"zahl": st.column_config.NumberColumn, "text": st.column_config.TextColumn,
         "check": st.column_config.CheckboxColumn}[typ]
    if pinned:
        try:
            return f(name, pinned=True, **kw)
        except TypeError:
            pass
    return f(name, **kw)


# --- Grosser Katalog: alle Werte der Watchlist (vom Agenten berechnet) -------
PFAD_KATALOG_GROSS = "state/planer/katalog_gross_{}.json"
KATALOG_GROSS_TEILE = 4
GROSS_TYPEN = {"aktie": "Aktien", "etf": "ETFs & ETPs", "wikifolio": "Wikifolios"}
GROSS_SORT = ["⭐ Gesamt-Score", "5J p.a.", "3J p.a.", "1J %", "10J p.a.", "Q-Score", "Div. %", "Vola 1J", "Max DD",
              "Name"]
Q_KLASSEN_TXT = {"prio": "Hohe Analysepriorität", "beobachten": "Beobachtungsliste", "nicht": "Nicht weiterverfolgen"}


def _ist_wkn(kennung):
    return bool(re.fullmatch(r"[A-Z0-9]{6}", kennung or "")) and any(c.isdigit() for c in kennung)


def _gross_daten(h):
    """-> (zeilen, kategorie_titel, stand) - alle Werte, Performance gesamt in %."""
    zeilen, titel, stand, felder = [], {}, None, None
    for i in range(KATALOG_GROSS_TEILE):
        try:
            d = h["gh_read_taeglich"](PFAD_KATALOG_GROSS.format(i), None) or {}
        except Exception:
            d = {}
        felder = d.get("felder") or felder
        titel.update(d.get("kategorien") or {})
        stand = d.get("stand") or stand
        zeilen += d.get("zeilen") or []
    if not felder:
        return [], {}, None
    return [dict(zip(felder, z)) for z in zeilen], titel, stand


def _q_voll(h):
    """-> ({yahoo_symbol: alle Felder des Qualitaets-Agenten}, stand) - fuer die transparente Bewertung."""
    aus, stand = {}, None
    for i in range(6):
        try:
            d = h["gh_read_taeglich"](f"state/qualitaet/alle_{i}.json", None) or {}
        except Exception:
            d = {}
        f = d.get("felder") or []
        if "gesamt" not in f or "s" not in f:
            continue
        stand = d.get("stand") or stand
        for z in d.get("zeilen") or []:
            e = dict(zip(f, z))
            aus[e["s"]] = e
    return aus, stand


_BW_CACHE = {}


def _bw_basis(h, strategie):
    """-> dict(roh, titel, stand, qvoll, q_stand, basis, modell, ctx, scores) - einmal je Datenstand
    und Strategie gerechnet und zwischengespeichert (Marktdaten, fuer alle Benutzer gleich).
    scores: {kennung: bewertung} fuer ALLE Werte - Filter und Seitenwechsel rechnen nichts neu."""
    roh, titel, stand = _gross_daten(h)
    qvoll, q_stand = _q_voll(h)
    schluessel = (stand, q_stand, strategie, len(roh), len(qvoll))
    c = _BW_CACHE.get(schluessel)
    if c is None:
        basis = []
        for z in roh:
            r = {"r1": z.get("1J"), "r3": _pa(z.get("3J"), 3), "r5": _pa(z.get("5J"), 5),
                 "r10": _pa(z.get("10J"), 10)}
            basis.append(dict(z, **r, qd=qvoll.get(z["kennung"]) if z["typ"] == "aktie" else None))
        modell = BW.Modell(basis, strategie) if basis else None
        ctx = AN.kontext(basis) if basis else {"median": {}, "benchmark": None}
        c = {"roh": roh, "titel": titel, "stand": stand, "qvoll": qvoll, "q_stand": q_stand, "basis": basis,
             "modell": modell, "ctx": ctx, "scores": {}}
        if len(_BW_CACHE) > 8:
            _BW_CACHE.clear()
        _BW_CACHE[schluessel] = c
    return c


def _bw_score(c, z):
    """Bewertung eines Katalogwerts aus dem Zwischenspeicher (sonst einmal rechnen)."""
    k = (z.get("typ"), z.get("kennung"))
    if k not in c["scores"]:
        c["scores"][k] = c["modell"].bewerte(z) if c["modell"] else None
    return c["scores"][k]


def _q_daten(h):
    """{yahoo_symbol: (punkte, klasse)} aus dem Qualitaets-Score (falls vorhanden)."""
    return {s_: (e.get("gesamt"), e.get("klasse")) for s_, e in _q_voll(h)[0].items()}


def _pa(gesamt_pct, jahre):
    """Gesamtperformance in % -> Rendite p.a. in %."""
    if gesamt_pct is None or gesamt_pct <= -100:
        return None
    return round(((1 + gesamt_pct / 100.0) ** (1.0 / jahre) - 1) * 100, 1)


def _etf_kategorie(name):
    n = (name or "").lower()
    for muster, kat in ((r"2x|3x|lever|daily|hebel", "leveraged_etf"), (r"semicon|halbleiter", "semiconductor"),
                        (r"crypto|bitcoin|ethereum|krypto", "crypto"), (r"gold|silver|silber|miner|copper|metal|rohstoff", "mining"),
                        (r"nasdaq|tech|information|cyber|robot|ai\b|artificial", "technology"),
                        (r"small ?cap|nebenwerte", "small_cap"), (r"momentum|quality|value|factor|min(imum)? vol", "factor"),
                        (r"s&p 500|usa|\bus\b|europe|euro|japan|emerging|china|india|dax|stoxx", "regional_equity"),
                        (r"energy|health|defen|bank|financ|util|real estate|reit", "sector")):
        if re.search(muster, n):
            return kat
    return "global_equity"


def _im_portfolio_gross(m, z):
    k = (z["kennung"] or "").upper()
    return any((a.get("ticker") or "").upper() == k or (z.get("isin") and a.get("isin") == z["isin"])
               or (a.get("yahoo") and a["yahoo"] == z["kennung"]) for a in m["assets"])


def _score_spalte():
    hilfe = ("Gesamt-Score 0–100 relativ zur eigenen Anlageklasse (50 = Durchschnitt). "
             "Gewichtung je nach gewählter Strategie; Erklärung unter der Tabelle.")
    try:
        return st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d", help=hilfe,
                                               width="small")
    except Exception:
        return _spalte("Score", format="%d", width="small", help=hilfe)


def _sc_farbe(score):
    return "sc-" + BW.ampel(score)


def _sc_zahl(x, dec=0, vz=False):
    if x is None:
        return "–"
    t = f"{x:+.{dec}f}" if vz else f"{x:.{dec}f}"
    return t.replace(".", ",").replace("-", "−")


def _sc_teile_html(b):
    reihen = []
    for g in sorted(b["gruppen"], key=lambda x: -x["gewicht"]):
        sc = g["score"]
        breite = 0 if sc is None else max(2, sc)
        farbe = "sc-bg-" + BW.ampel(sc)
        reihen.append(
            f'<div class="sc-teil"><span>{_esc(g["label"])} <span class="sc-typ">{g["gewicht"]:.0f} %</span></span>'
            f'<div class="sc-mini"><div class="{farbe}" style="width:{breite:.0f}%"></div></div>'
            f'<span class="sc-zahl {_sc_farbe(sc)}">{_sc_zahl(sc)}</span>'
            f'<span class="sc-beitrag">{_sc_zahl(g["beitrag"], 1, True) if sc is not None else "fehlt"}</span></div>')
    return "".join(reihen)


def _sc_karte(platz, z, b, text):
    plus = "".join(f'<div class="sc-plus">✓ {_esc(t)}</div>' for t in b["plus"])
    minus = "".join(f'<div class="sc-minus">✗ {_esc(t)}</div>' for t in b["minus"])
    hinweise = "".join(f'<span class="pl-badge pl-warn">⚠ {_esc(t)}</span>' for t in b["hinweise"])
    return (
        f'<div class="sc-karte"><div class="sc-kopf"><span class="sc-platz">{platz}</span>'
        f'<span class="sc-name">{_esc(z["name"])}</span><span class="sc-typ">{_esc(GROSS_TYPEN[z["typ"]])}</span>'
        f'<span class="sc-wert {_sc_farbe(b["score"])}">{b["score"]}<small>/100</small></span></div>'
        f'<div class="sc-balken"><div class="sc-bg-{BW.ampel(b["score"])}" style="width:{b["score"]}%"></div></div>'
        f'{_sc_teile_html(b)}'
        f'<div class="sc-warum"><b>Warum auf diesem Platz?</b> {_esc(text)}</div>'
        f'<div class="sc-pm">{plus}{minus}</div>{hinweise}'
        f'<div class="sc-meta">Datenqualität {b["datenqualitaet"]} · {b["abdeckung"] * 100:.0f} % der Kriterien '
        f'mit Daten · Strategie {_esc(b["strategie"])}</div></div>')


def _sc_alter(stand):
    try:
        d = datetime.date.fromisoformat(str(stand)[:10])
    except Exception:
        return None, "–"
    return (datetime.date.today() - d).days, d.strftime("%d.%m.%Y")


_AN_TAG = {AN.FAKT: "an-fakt", AN.PROGNOSE: "an-prognose", AN.MODELL: "an-modell",
           AN.EINSCHAETZUNG: "an-einschaetzung"}


def _an_tag(art):
    return f'<span class="an-tag {_AN_TAG.get(art, "an-fakt")}">{_esc(art)}</span>'


def _analyse_box_html(a):
    b = a["box"]
    zeilen = (("Warum interessant?", b["warum"]), ("Vergangenheit", b["vergangenheit"]),
              ("Zukunft", b["zukunft"]), ("Bewertung", b["bewertung"]), ("Risiken", b["risiken"]),
              ("Gesamteinschätzung", b["gesamt"]))
    return '<div class="an-box">' + "".join(
        f'<div class="an-zeile"><b>{_esc(l)}</b> {_esc(t)}</div>' for l, t in zeilen) + "</div>"


def _q_detail(h, z):
    """Detaildaten einer Aktie aus state/qualitaet/details_<teil>.json (nur bei Bedarf geladen)."""
    q = z.get("qd") or {}
    if z.get("typ") != "aktie" or not q.get("s"):
        return None
    teil = q.get("d")
    if teil is None:
        teil = zlib.crc32(q["s"].encode()) % QUALITAET_DETAIL_TEILE
    try:
        d = h["gh_read_taeglich"](f"state/qualitaet/details_{teil}.json", None) or {}
    except Exception:
        return None
    return (d.get("werte") or {}).get(q["s"])


def _detailanalyse(a):
    """Aufklappbare Detailanalyse: Urteil, Argumente, Historie, Zukunft, Szenarien, Quellen."""
    st.markdown(f'<div class="an-urteil">{a["emoji"]} {_esc(a["urteil_text"])}</div>'
                f'<div class="an-zeile">{_an_tag(AN.EINSCHAETZUNG)}{_esc(", ".join(a["urteil_gruende"]))}.</div>',
                unsafe_allow_html=True)
    st.markdown("**Warum mich dieser Wert derzeit nicht überzeugt**" if a["urteil"] == "unattraktiv"
                else "**Warum ich diesen Wert interessant finde**")
    st.markdown(f'<div class="an-zeile">{_an_tag(AN.EINSCHAETZUNG)}{_esc(" ".join(a["these"]))}</div>',
                unsafe_allow_html=True)
    st.markdown("**Die drei stärksten Argumente**\n" + "\n".join(f"- ✓ {t}" for t in a["argumente"]))
    st.markdown("**Die drei größten Risiken**\n" + "\n".join(f"- ✗ {t}" for t in a["risiken"]))
    st.caption(a["gegenargument"])
    bw = a["bewertung"]
    st.markdown(f'<div class="an-zeile"><b>Aktuelle Bewertung: {_esc(bw["stufe"] or "nicht einzuordnen")}</b> '
                f'{_an_tag(bw["art"])}{_esc(bw["text"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="an-zeile"><b>Langfristiges Potenzial (3–5 J.)</b> {_an_tag(AN.MODELL)}'
                f'{_esc(a["potenzial"])}</div>', unsafe_allow_html=True)

    _abschnitt("Vergangenheit")
    _tabelle(["Kennzahl", "Wert", "Vergleich"], [[_esc(l), _esc(w), _esc(v)] for l, w, v in a["kennzahlen"]],
             links=(0, 2))
    st.markdown("".join(f'<div class="an-zeile">{_an_tag(art)}{_esc(t)}</div>' for art, t in a["vergangenheit"]),
                unsafe_allow_html=True)

    _abschnitt("Zukunftsaussichten")
    st.markdown("".join(f'<div class="an-zeile">{_an_tag(art)}{_esc(t)}</div>' for art, t in a["zukunft"]),
                unsafe_allow_html=True)

    sz = a["szenarien"]
    _abschnitt("Drei Szenarien (Schätzungen, keine Prognose)")
    if sz["zeilen"]:
        _tabelle(["Szenario", "Rendite p.a.", "nach 1 J.", "nach 3 J.", "nach 5 J.", "Annahme"],
                 [[_esc(r["name"]), _pct(r["pa"] / 100, vorzeichen=True),
                   *[_esc(AN._eur(r["werte"][n])) for n in (1, 3, 5)], _esc(r["annahme"])] for r in sz["zeilen"]],
                 links=(0, 5))
        st.caption(f"Startbetrag {AN._eur(AN.STARTBETRAG)}, vor Kosten und Steuern.")
    else:
        st.caption("Für Szenarien fehlt eine ausreichende Historie.")
    for t in (sz["band"], sz["stress"]):
        if t:
            st.markdown(f'<div class="an-zeile">{_an_tag(AN.MODELL if t is sz["band"] else AN.FAKT)}{_esc(t)}</div>',
                        unsafe_allow_html=True)
    if sz["dcf"]:
        st.markdown("**Fairer Wert laut Cashflow-Modell (DCF des Qualitäts-Agenten)**")
        _tabelle(["Szenario", "Fairer Wert vs. Kurs", "FCF-Wachstum", "Diskontsatz", "Exit-Multiple"],
                 [[_esc(d["name"]), _esc(AN._p(d["pot"], 0)), _esc(AN._p(d["g"])), _esc(AN._p(d["r"], vz=False)),
                   _esc(f'{AN._de(d["m"])}x' if d["m"] is not None else "–")] for d in sz["dcf"]])

    _abschnitt("Quellen und Datenstand")
    st.markdown("\n".join(f"- {t}" for t in a["quellen"]))
    if a["nicht_in_quelle"]:
        st.caption("Nicht in der Datenquelle und daher nicht bewertet: " + ", ".join(a["nicht_in_quelle"]) + ".")


def _rang_transparenz(zeilen, modell, typ_key, sortierung, stand, q_stand, h, ctx=None):
    """'Warum auf diesem Platz?' fuer die ersten drei, Direktvergleich, Einzelwert-Erklaerung
    und die offengelegte Bewertungsmethode."""
    mit = [z for z in zeilen if z.get("bw")]
    if not mit:
        return
    nach_score = sortierung == "⭐ Gesamt-Score"
    _abschnitt("🏅 Warum auf diesem Platz?")
    alter_k, stand_k = _sc_alter(stand)
    alter_q, stand_q = _sc_alter(q_stand)
    zeit = f"Bewertet {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')} · Kurse Stand {stand_k}"
    if any(z["typ"] == "aktie" for z in mit):
        zeit += f" · Fundamentaldaten Stand {stand_q}"
    veraltet = [n for n, a in (("Kurse", alter_k), ("Fundamentaldaten", alter_q if any(
        z["typ"] == "aktie" for z in mit) else None)) if a is not None and a > 3]
    st.caption(zeit)
    if veraltet:
        st.warning(" und ".join(veraltet) + " sind älter als 3 Tage – die Bewertung kann überholt sein.")
    if typ_key is None and len({z["typ"] for z in mit[:10]}) > 1:
        st.caption("ℹ️ Gemischte Liste: Jeder Score ist relativ zur eigenen Anlageklasse (Aktie gegen Aktien, "
                   "ETF gegen ETFs). Für einen fairen Vergleich oben eine Art wählen.")
    if not nach_score:
        st.caption(f"Sortiert nach „{sortierung}“ – für eine Rangfolge nach dem Gesamt-Score oben "
                   "„⭐ Gesamt-Score“ wählen.")

    ctx = ctx or AN.kontext(mit)

    def _an(i, z, detail=None):
        return AN.analysiere(z, z["bw"], ctx, detail=detail, platz=i + 1, stand=stand_k, q_stand=stand_q)

    top = mit[:3]
    for i, z in enumerate(top):
        naechster = top[i + 1] if i + 1 < len(top) else None
        text = BW.warum(i + 1, z["bw"], naechster["bw"] if naechster else None,
                        naechster["name"] if naechster else None, nach_score, sortierung)
        st.markdown(_sc_karte(i + 1, z, z["bw"], text) + _analyse_box_html(_an(i, z)), unsafe_allow_html=True)

    if len(top) >= 2:
        _abschnitt("⚖️ Direktvergleich der Spitze")
        keys = []
        for z in top:
            for g in z["bw"]["gruppen"]:
                if g["key"] not in keys:
                    keys.append(g["key"])
        kopf = ["Teilscore"] + [f'#{i + 1} {z["name"][:18]}' for i, z in enumerate(top)]
        reihen = []
        for k in keys:
            zellen = [_esc(BW.GRUPPEN[k])]
            werte = []
            for z in top:
                g = next((x for x in z["bw"]["gruppen"] if x["key"] == k), None)
                werte.append(None if not g else g["score"])
            beste = max((w for w in werte if w is not None), default=None)
            for w in werte:
                fett = ' style="font-weight:900"' if w is not None and w == beste and len(top) > 1 else ""
                zellen.append(f'<span class="{_sc_farbe(w)}"{fett}>{_sc_zahl(w)}</span>')
            reihen.append(zellen)
        reihen.append(["<b>Gesamt</b>"] + [f'<b class="{_sc_farbe(z["bw"]["score"])}">{z["bw"]["score"]}</b>'
                                           for z in top])
        _tabelle(kopf, reihen)
        for i in range(len(top) - 1):
            a, b = top[i], top[i + 1]
            abstand, diffs = BW.vergleich(a["bw"], b["bw"])
            pro = [f"{l} ({_sc_zahl(d, 1, True)})" for l, d in diffs if d > 0.3][:3]
            contra = [f"{l} ({_sc_zahl(-d, 1, True)})" for l, d in reversed(diffs) if d < -0.3][:2]
            satz = f"**#{i + 1} vs. #{i + 2}:** Abstand {_sc_zahl(abstand, 1)} Punkte"
            if abs(abstand) < BW.GLEICHWERTIG:
                satz += " – praktisch gleichwertig."
            else:
                satz += "."
            if pro:
                satz += f" #{i + 1} besser bei " + ", ".join(pro) + "."
            if contra:
                satz += f" #{i + 2} besser bei " + ", ".join(contra) + "."
            if a["typ"] != b["typ"]:
                satz += " (Unterschiedliche Anlageklassen – nur bedingt vergleichbar.)"
            st.markdown(satz)
        st.caption("Zahlen in Klammern = Punkte, die der Teilscore zum Gesamt-Score beiträgt (Differenz zwischen "
                   f"den beiden). Abstände unter {BW.GLEICHWERTIG} Punkten sind innerhalb der Messgenauigkeit.")

    _abschnitt("📋 Analyse je Eintrag")
    st.caption("Kompakte Analysebox je Rang; „Detailanalyse“ zeigt alle Kennzahlen, Szenarien und Quellen. "
               "Gekennzeichnet: Fakt · Externe Prognose · Modell/Annahme · Einschätzung.")
    for i, z in enumerate(mit[:25]):
        a = _an(i, z)
        with st.expander(f'#{i + 1} {z["name"]} · Score {z["bw"]["score"]} · {a["emoji"]} {a["urteil_text"]}'):
            st.markdown(_analyse_box_html(a), unsafe_allow_html=True)
            if st.toggle("🔬 Detailanalyse", key=f'pl_gk_det_{z["kennung"]}'):
                _detailanalyse(_an(i, z, _q_detail(h, z)))
    if len(mit) > 25:
        st.caption("Analyseboxen für die ersten 25 Einträge – alle weiteren über „Einzelnen Wert erklären“.")

    _abschnitt("🔎 Einzelnen Wert erklären")
    namen = [f'{i + 1}. {z["name"]} ({z["bw"]["score"]})' for i, z in enumerate(mit)]
    sig = zlib.crc32("|".join(str(z["kennung"]) for z in mit).encode())
    wahl_i = st.selectbox("Wert", list(range(len(mit))), format_func=lambda i: namen[i], key=f"pl_gk_erkl_{sig}")
    z = mit[int(wahl_i or 0)]
    b = z["bw"]
    teile = " ".join(f'{g["label"]} {_sc_zahl(g["beitrag"], 1, True)}'
                     for g in sorted(b["gruppen"], key=lambda x: -abs(x["beitrag"])) if g["score"] is not None)
    st.markdown(f'<div class="sc-formel"><b>{b["score"]}</b> = 50 (neutral) {_esc(teile)}'
                + (f' · gedämpft auf Datenabdeckung {b["abdeckung"] * 100:.0f} %' if b["abdeckung"] < 0.995 else "")
                + '</div>', unsafe_allow_html=True)
    reihen = []
    for g in sorted(b["gruppen"], key=lambda x: -x["gewicht"]):
        reihen.append([f'<b>{_esc(g["label"])}</b>', "", "",
                       f'<b class="{_sc_farbe(g["score"])}">{_sc_zahl(g["score"])}</b>',
                       f'{g["gewicht"]:.0f} %', f'<b>{_sc_zahl(g["beitrag"], 1, True)}</b>'])
        for k in g["kriterien"]:
            reihen.append([f'&nbsp;&nbsp;{_esc(k["label"])}', _esc(k["wert_txt"]), _esc(k["info"]),
                           f'<span class="{_sc_farbe(k["score"])}">{"–" if k["score"] is None else k["score"]}</span>',
                           "", ""])
    _tabelle(["Kriterium", "Wert", "Einordnung", "Punkte", "Gewicht", "Beitrag"], reihen, links=(0, 2))
    for t in b["hinweise"]:
        st.caption(f"⚠️ {t}")
    if b["fehlend"]:
        st.caption("Ohne Daten (zieht den Score zur Mitte): " + ", ".join(b["fehlend"]))
    _abschnitt(f"🧠 Investment-Analyse: {z['name']}")
    a = _an(int(wahl_i or 0), z, _q_detail(h, z))
    st.markdown(_analyse_box_html(a), unsafe_allow_html=True)
    _detailanalyse(a)

    with st.expander("ℹ️ Wie wird bewertet? (Methode, Gewichte, Datenlücken)"):
        st.markdown(
            "- **Fairer Vergleich:** Aktien werden nur mit Aktien verglichen, ETFs mit ETFs, Wikifolios mit "
            "Wikifolios – über alle Werte der Watchlist, unabhängig von den Filtern.\n"
            "- **Kriterium → Punkte:** meist der Rang in der Klasse („besser als 80 % der ETFs“ = 80 Punkte). "
            "Feste Skalen: Punkte des Qualitäts-Agenten, Länge der Historie (10 Jahre = 100), Streuung, "
            "Analysten-Revisionen (±10 % = 100/0).\n"
            "- **Teilscore** = Mittel seiner Kriterien; **Gesamt-Score** = gewichtetes Mittel der Teilscores. "
            "Er startet bei 50 (neutral), die Beiträge addieren sich genau zum Score.\n"
            "- **Datenlücken:** Fehlen Kriterien, wird der Score zur Mitte gezogen (Lücken werden weder belohnt "
            "noch bestraft). Datenqualität: gut ≥ 85 %, mittel ≥ 60 % der Kriterien.\n"
            f"- **Genauigkeit:** ganze Punkte; Abstände unter {BW.GLEICHWERTIG} Punkten sind praktisch "
            "gleichwertig. Der Score beschreibt die Vergangenheit und ist keine Empfehlung.")
        for t_key, t_name in BW.KLASSEN.items():
            if typ_key and t_key != typ_key:
                continue
            gew = modell.gewichte(t_key)
            st.markdown(f"**{t_name}** – Strategie „{modell.strategie}“: " + " · ".join(
                f"{BW.GRUPPEN[g]} {w} %" for g, w in sorted(gew.items(), key=lambda x: -x[1])))
            krit = BW.kriterien_der_klasse(t_key)
            st.caption("Kriterien: " + "; ".join(
                f"{BW.GRUPPEN[g]}: " + ", ".join(d[1] for d in krit.values() if d[0] == g) for g in gew))
            st.caption("Nicht in der Datenquelle (fließt nicht ein): " + ", ".join(BW.NICHT_IN_QUELLE[t_key]))
            st.caption(f"Vergleichsbasis: {modell.anzahl(t_key)} {t_name}")


def _katalog_gross(m, h):
    strategie = st.session_state.get("pl_gk_strat") or "Ausgewogen"
    c_bw = _bw_basis(h, strategie)
    roh, titel, stand = c_bw["roh"], c_bw["titel"], c_bw["stand"]
    if not roh:
        st.info("Die Liste aller Werte entsteht beim nächsten Lauf des Watchlist-Agenten (täglich morgens, oder "
                "auf GitHub unter Actions → Watchlist Top 50 → Run workflow).")
        return
    qvoll, q_stand = c_bw["qvoll"], c_bw["q_stand"]
    qd = {s_: (e.get("gesamt"), e.get("klasse")) for s_, e in qvoll.items()}
    try:
        stand_txt = datetime.datetime.fromisoformat(stand).strftime("%d.%m.%Y")
    except Exception:
        stand_txt = stand or "–"
    st.caption(f"{_de(len(roh))} Werte aus der Watchlist · Stand {stand_txt} · Kurse ls-tc.de / Yahoo Finance, "
               "in Euro")

    such = st.text_input("Suche (Name, WKN, Symbol)", key="pl_gk_such", placeholder="z. B. Nvidia, A2PKXG, LS9…").strip().lower()
    typ = st.pills("Art", ["Alle"] + list(GROSS_TYPEN.values()), default="Alle", key="pl_gk_typ") or "Alle"
    typ_key = next((k for k, v in GROSS_TYPEN.items() if v == typ), None)
    kats = sorted({z["kat"] for z in roh if typ_key in (None, z["typ"])}, key=lambda k: titel.get(k, k))
    c1, c2 = st.columns(2)
    kat_wahl = c1.selectbox("Kategorie", ["Alle"] + [titel.get(k, k) for k in kats], key=f"pl_gk_kat_{typ}")
    hist = c2.selectbox("Mindest-Historie", ["egal", "≥ 3 Jahre", "≥ 5 Jahre", "≥ 10 Jahre"], key="pl_gk_hist")
    c3, c4 = st.columns(2)
    sortierung = c3.selectbox("Sortieren nach", GROSS_SORT, key="pl_gk_sort")
    min_r = c4.number_input("Mind. Rendite p.a. (%)", -100.0, 1000.0, -100.0, step=1.0, key="pl_gk_minr",
                            help="Gilt für die Rendite, nach der sortiert wird (sonst 5 J. p.a.)")
    c5, c6 = st.columns(2)
    q_filter = c5.selectbox("Qualitäts-Score (Aktien)", ["egal", "Hohe Analysepriorität", "mind. Beobachtungsliste",
                                                         "mind. 60 Punkte", "mind. 70 Punkte"], key="pl_gk_q")
    laenge = c6.selectbox("Anzahl", [50, 100, 250, 500], index=1, key="pl_gk_n")
    strategie = st.pills("Bewertungs-Strategie", list(BW.STRATEGIEN), default="Ausgewogen", key="pl_gk_strat",
                         help="Ändert nur die Gewichtung der Teilscores im Gesamt-Score – die Daten bleiben gleich."
                         ) or "Ausgewogen"
    st.caption(f"⭐ {BW.STRATEGIEN[strategie]}")

    kat_key = next((k for k in kats if titel.get(k, k) == kat_wahl), None)
    min_jahre = {"egal": 0, "≥ 3 Jahre": 3, "≥ 5 Jahre": 5, "≥ 10 Jahre": 10}[hist]
    feld_sort = {"⭐ Gesamt-Score": "score", "1J %": "r1", "3J p.a.": "r3", "5J p.a.": "r5", "10J p.a.": "r10",
                 "Q-Score": "q", "Div. %": "div", "Vola 1J": "vola", "Max DD": "maxdd", "Name": "name"}[sortierung]
    feld_min = feld_sort if feld_sort in ("r1", "r3", "r5", "r10") else "r5"
    # Vergleichsbasis fuer den Score: ALLE Werte (Filter aendern den Score eines Werts nicht)
    if c_bw["modell"] is None or c_bw["modell"].strategie != strategie:
        c_bw = _bw_basis(h, strategie)
    basis, modell, ctx = c_bw["basis"], c_bw["modell"], c_bw["ctx"]
    zeilen = []
    for z in basis:
        if typ_key and z["typ"] != typ_key:
            continue
        if kat_key and z["kat"] != kat_key:
            continue
        if such and such not in (z["name"] or "").lower() and such not in (z["kennung"] or "").lower() \
                and such not in (z.get("isin") or "").lower():
            continue
        r = z
        if min_jahre and r[{3: "r3", 5: "r5", 10: "r10"}[min_jahre]] is None:
            continue
        q = qd.get(z["kennung"]) if z["typ"] == "aktie" else None
        if q_filter != "egal":
            if not q:
                continue
            if q_filter == "Hohe Analysepriorität" and q[1] != "prio":
                continue
            if q_filter == "mind. Beobachtungsliste" and q[1] not in ("prio", "beobachten"):
                continue
            if q_filter.startswith("mind. ") and q_filter.endswith("Punkte") and q[0] < int(q_filter.split()[1]):
                continue
        if min_r > -100 and (r[feld_min] is None or r[feld_min] < min_r):
            continue
        b = _bw_score(c_bw, z)
        zeilen.append(dict(z, q=q[0] if q else None, klasse=q[1] if q else None, bw=b,
                           score=b["score_genau"] if b else None))
    if feld_sort == "name":
        zeilen.sort(key=lambda z: (z["name"] or "").lower())
    else:
        richtung = 1 if feld_sort == "vola" else -1          # Vola: niedrigste zuerst
        zeilen.sort(key=lambda z: (z.get(feld_sort) is None, richtung * (z.get(feld_sort) or 0)))
    treffer = len(zeilen)
    zeilen = zeilen[:int(laenge)]
    st.caption(f"{_de(treffer)} Treffer" + (f" · angezeigt die ersten {len(zeilen)}" if treffer > len(zeilen) else ""))
    if not zeilen:
        st.info("Keine Werte für diese Filter.")
        return

    wahl = st.session_state.setdefault("planer_gk_wahl", {})
    df = pd.DataFrame([{
        "＋": z["kennung"] in wahl, "Name": z["name"],
        "Score": z["bw"]["score"] if z.get("bw") else None,
        "Daten": {"gut": "● gut", "mittel": "◐ mittel", "gering": "○ gering"}.get((z.get("bw") or {}).get(
            "datenqualitaet"), "–"),
        "Typ": GROSS_TYPEN[z["typ"]].split(" ")[0],
        "Kategorie": titel.get(z["kat"], z["kat"]), "1J %": z["r1"], "3J p.a.": z["r3"], "5J p.a.": z["r5"],
        "10J p.a.": z["r10"], "Vola 1J": z.get("vola"), "Max DD": z.get("maxdd"), "Q-Score": z["q"],
        "Div. %": z.get("div"), "WKN/Symbol": z["kennung"],
        "Im Portf.": _im_portfolio_gross(m, z)} for z in zeilen])
    for c in ("Score", "1J %", "3J p.a.", "5J p.a.", "10J p.a.", "Vola 1J", "Max DD", "Q-Score", "Div. %"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    cfg = {"＋": _spalte("＋", typ="check", width="small", help="Zum Hinzufügen auswählen"),
           "Score": _score_spalte(),
           "Daten": _spalte("Daten", typ="text", width="small",
                            help="Datenqualität: Anteil der Bewertungskriterien, für die Daten vorliegen"),
           "Name": _spalte("Name", pinned=True, typ="text", width="medium"),
           "Typ": _spalte("Typ", typ="text", width="small"), "Kategorie": _spalte("Kategorie", typ="text"),
           "WKN/Symbol": _spalte("WKN/Symbol", typ="text"), "Im Portf.": _spalte("Im Portf.", typ="check", width="small"),
           "Q-Score": _spalte("Q-Score", format="%d", width="small", help="Qualitäts-Score 0–100 (nur Aktien)")}
    for c in ("1J %", "3J p.a.", "5J p.a.", "10J p.a.", "Vola 1J", "Max DD", "Div. %"):
        cfg[c] = _spalte(c, format="%.1f", width="small")
    signatur = zlib.crc32(("|".join(df["WKN/Symbol"].astype(str))).encode())
    ed = st.data_editor(df, key=_k(f"gk_{signatur}"), hide_index=True, width="stretch", height=_hoehe(len(df)),
                        disabled=[c for c in df.columns if c != "＋"], column_config=cfg)
    for i, z in enumerate(zeilen):
        an = bool(ed.iloc[i]["＋"])
        if an:
            wahl[z["kennung"]] = z
        else:
            wahl.pop(z["kennung"], None)
    st.caption("Rendite = reine Kursentwicklung in Euro (1 J. gesamt, 3/5/10 J. p.a.), ohne Dividenden. "
               "Hohe Vergangenheitsrenditen sind keine Zukunftserwartung (Winner Bias).")
    try:
        _rang_transparenz(zeilen, modell, typ_key, sortierung, stand, q_stand, h, ctx)
    except Exception as e:          # Erklaerung darf die Liste nie blockieren
        st.caption(f"Bewertungs-Erklärung nicht verfügbar ({e}).")

    c7, c8 = st.columns(2)
    gew = c7.number_input("Startgewicht je Baustein %", 0.0, 100.0, 0.0, step=0.5, key="pl_gk_gew",
                          help="Danach unter „⚖️ Gewichtung“ verteilen oder normalisieren")
    vorschlag = c8.toggle("Base/Bear/Bull-Vorschlag als Annahme", value=True, key="pl_gk_vs")
    if wahl:
        st.caption("Ausgewählt: " + ", ".join(z["name"] for z in list(wahl.values())[:10])
                   + (" …" if len(wahl) > 10 else ""))
    if st.button(f"➕ {len(wahl)} ausgewählte hinzufügen", key="pl_gk_add", width="stretch", disabled=not wahl):
        doppelt = []
        for z in list(wahl.values()):
            if _im_portfolio_gross(m, z):
                doppelt.append(z["name"])
                continue
            kategorie = {"aktie": "single_stock", "wikifolio": "wikifolio"}.get(z["typ"]) or _etf_kategorie(z["name"])
            jahre = 10 if z.get("r10") is not None else 5 if z.get("r5") is not None else 3 if z.get("r3") is not None else 1
            kz = {"historical5Y": None if z.get("r5") is None else z["r5"] / 100,
                  "historical3Y": None if z.get("r3") is None else z["r3"] / 100, "jahre": jahre}
            vs = E.vorschlag_renditen(kz, D.KATEGORIEN[kategorie]["typ"])
            wkn = z["kennung"] if _ist_wkn(z["kennung"]) else None
            extra = {"emittent": "Lang & Schwarz" if z["typ"] == "wikifolio" else None,
                     "subCategory": titel.get(z["kat"], z["kat"]),
                     "historicalWinnerBias": bool(vs and vs["hist"] >= 0.20)}
            if not wkn:
                extra["yahoo"] = z["kennung"]          # Yahoo-Symbol (Kurssuche dann ueber den Namen)
            nutzen = vorschlag and vs is not None
            aid = _baustein_neu(
                m, z["name"], kategorie, wkn=wkn, isin=z.get("isin") or None, gewicht=gew,
                rendite=vs["base"] * 100 if nutzen else None, extra=extra, auto=True,
                notiz=(D.VORSCHLAG["text"] + f" Historisch {vs['quelle']}: {_pct(vs['hist'])} p.a.") if nutzen else None)
            if nutzen:
                for sz in ("bear", "base", "bull"):
                    E.setze_annahme(m, aid, sz, vs[sz], notiz="Vorschlag aus dem Katalog – keine Prognose")
        st.session_state["planer_gk_wahl"] = {}
        if doppelt:
            st.session_state["planer_meldung"] = ("warnung", "Schon im Portfolio, nicht doppelt angelegt: "
                                               + ", ".join(doppelt), [])
        _neu_zeichnen()
        st.rerun()


def _katalog(m, h):
    gross_n = len(_gross_daten(h)[0])
    optionen = [f"⭐ Auswahl ({len(D.KATALOG)})",
                f"🌐 Alle Werte ({_de(gross_n)})" if gross_n else "🌐 Alle Werte (Watchlist)"]
    # sobald die grosse Liste da ist, ist sie die Standardansicht
    quelle = st.pills("Katalog", optionen, default=optionen[1] if gross_n else optionen[0],
                      key=f"pl_kat_quelle_{bool(gross_n)}") or optionen[0]
    if quelle.startswith("🌐"):
        _katalog_gross(m, h)
        return
    d = _katalog_daten(h)
    werte = d.get("werte") or {}
    heute = h["heute"].isoformat()
    fehler = [v.get("fehler") for v in werte.values() if v.get("fehler")]
    if werte and len(fehler) > len(werte) / 2:
        # gespeicherter Stand ist (fast) leer - z. B. weil die Kursquelle beim Laden nicht antwortete
        haeufig = max(set(fehler), key=fehler.count)
        st.warning(f"Für {len(fehler)} von {len(werte)} Werten liegen keine Kennzahlen vor "
                   f"(häufigster Grund: {haeufig}). Bitte „Aktualisieren“ tippen – fehlgeschlagene Werte werden "
                   "dabei einzeln nachgeladen.")
    if not werte:
        st.info("Für den Katalog sind noch keine Kennzahlen berechnet. Sie entstehen beim nächsten Lauf des "
                "Watchlist-Agenten (täglich, oder auf GitHub unter Actions → Watchlist Top 50 → Run workflow). "
                "Alternativ hier direkt laden: Das Laden der Kurshistorien "
                f"({len(D.KATALOG)} Werte) dauert einmalig etwa eine halbe Minute – danach steht der Tagesstand "
                "gespeichert bereit.")
    c1, c2 = st.columns([3, 1])
    if werte:
        c1.caption(f"Kennzahlen Stand {d.get('berechnet', '–')} · Quelle ls-tc.de Kurshistorie"
                   + (" · täglich berechnet vom Watchlist-Agenten" if d.get("quelle") == "Agent" else "")
                   + ("" if d.get("stand") == heute else " · nicht von heute"))
    if c2.button("📊 Kennzahlen laden" if not werte else "Aktualisieren", key="pl_kat_laden", width="stretch"):
        with st.spinner(f"Lade Kurshistorien für {len(D.KATALOG)} Werte …"):
            d = _katalog_laden(h)
        werte = d["werte"]
        if d.get("ok", 0) < len(D.KATALOG) / 2:
            st.error(f"Nur {d.get('ok', 0)} von {len(D.KATALOG)} Werten geladen – die Kursquelle antwortet gerade "
                     "nicht zuverlässig. Bitte später erneut „Aktualisieren“ tippen.")

    with st.expander("🔧 Diagnose Kursquelle", expanded=bool(werte) and len(fehler) > len(werte) / 2):
        ok_n = sum(1 for v in werte.values() if not v.get("fehler"))
        st.caption(f"Gespeicherter Stand: {ok_n} von {len(werte)} Werten mit Kennzahlen · berechnet "
                   f"{d.get('berechnet', '–')}")
        gruende = {}
        for w, v in werte.items():
            if v.get("fehler"):
                gruende.setdefault(v["fehler"], []).append(w)
        for g, ws in sorted(gruende.items(), key=lambda x: -len(x[1]))[:5]:
            st.caption(f"• {len(ws)}× {g} (z. B. {', '.join(ws[:3])})")
        if st.button("Verbindung testen (NVIDIA, Vanguard All-World)", key="pl_kat_test", width="stretch"):
            for begriff, wiki in (("918422", False), ("IE00BK5BQT80", False)):
                try:
                    treffer = h["suche_instrument"](begriff) or []
                except Exception as e:
                    treffer, fehler_s = [], str(e)
                else:
                    fehler_s = ""
                st.write(f"**Suche „{begriff}“:** {len(treffer)} Treffer {fehler_s}")
                if treffer:
                    t = _waehle_treffer(treffer, begriff, wiki) or treffer[0]
                    st.write(f"→ {t.get('name')} · WKN {t.get('wkn')} · ID {t.get('instrument_id')}")
                    try:
                        reihe = h["get_kurshistorie"](t["instrument_id"], datetime.date(2000, 1, 1), h["heute"])
                        n = 0 if reihe is None else len(reihe)
                        st.write(f"→ Kurshistorie: {n} Kurse" + (f", letzter {float(reihe.iloc[-1]):.2f} €" if n else ""))
                    except Exception as e:
                        st.write(f"→ Kurshistorie: Fehler {e}")
                r = _hist_eines((begriff,), wiki, h["heute"].isoformat(), h["suche_instrument"], h["get_kurshistorie"])
                st.write("→ Kennzahlen: " + (f"Fehler: {r['fehler']}" if r.get("fehler") else
                                            f"ok, 5 J. p.a. {_pct(r.get('historical5Y'))}"))

    typen = ["Alle"] + list(D.KATALOG_TYPEN.values())
    typ = st.pills("Art", typen, default="Alle", key="pl_kat_typ") or "Alle"
    gruppen = st.pills("Spalten", list(KATALOG_GRUPPEN), default=["Rendite", "Risiko"], selection_mode="multi",
                       key="pl_kat_spalten") or []
    c3, c4 = st.columns([3, 2])
    sortierung = c3.selectbox("Sortieren nach", KATALOG_SORT, key="pl_kat_sort")
    absteigend = c4.toggle("Absteigend", value=sortierung not in ("Risk", "Vola 1J", "Name"), key=f"pl_kat_ab_{sortierung}")

    # Fehlt fuer einen Wert die eigene Kurshistorie, gelten die Zahlen der Watchlist (Top 500)
    fehlend = [k["wkn"] for k in D.KATALOG if not (werte.get(k["wkn"]) or {}) or werte[k["wkn"]].get("fehler")]
    if fehlend:
        wl = _watchlist_kennzahlen(h)
        ersetzt = 0
        werte = dict(werte)
        for w in fehlend:
            if w in wl:
                werte[w] = wl[w]
                ersetzt += 1
        if ersetzt:
            st.caption(f"{ersetzt} von {len(fehlend)} fehlenden Werten aus den Daten der Watchlist ergänzt"
                       + (" – Vola, Max DD und Risk kommen mit dem nächsten Lauf des Watchlist-Agenten dazu."
                          if not any(v.get("vola1y") is not None for v in wl.values()) else "."))
    zeilen = [z for z in _katalog_zeilen(m, werte) if typ == "Alle" or z["Typ"] == typ]

    def wert(z):
        if sortierung == "Historie ab":
            return (werte.get(z["wkn"]) or {}).get("start")
        return z[sortierung].lower() if sortierung == "Name" else z[sortierung]
    mit = [z for z in zeilen if wert(z) not in (None, "")]
    mit.sort(key=wert, reverse=absteigend)
    zeilen = mit + [z for z in zeilen if wert(z) in (None, "")]

    wahl = st.session_state.setdefault("planer_kat_wahl", [])
    spalten = [s_ for g in KATALOG_GRUPPEN if g in gruppen for s_ in KATALOG_GRUPPEN[g]]
    kopf = ["＋", "Name"] + ([] if typ != "Alle" else ["Typ"]) + spalten + ["Im Portf."]
    df = pd.DataFrame([{**{c: z[c] for c in kopf if c != "＋"}, "＋": z["wkn"] in wahl} for z in zeilen])[kopf] \
        if zeilen else pd.DataFrame(columns=kopf)
    for c in spalten:
        if c not in ("Historie ab", "Profil", "Gefunden"):
            df[c] = pd.to_numeric(df[c], errors="coerce")       # fehlende Werte leer statt "None"
    cfg = {"＋": _spalte("＋", typ="check", width="small", help="Zum Hinzufügen auswählen"),
           "Name": _spalte("Name", pinned=True, typ="text", width="medium"),
           "Im Portf.": _spalte("Im Portf.", typ="check", width="small")}
    for c in spalten:
        if c in ("Historie ab", "Profil", "Gefunden"):
            cfg[c] = _spalte(c, typ="text")
        elif c == "Hebel":
            cfg[c] = _spalte(c, format="%.0f×", width="small")
        elif c in ("Risk", "Conf."):
            cfg[c] = _spalte(c, format="%d", width="small",
                             help="Risk Score 0–100 (höher = riskanter)" if c == "Risk" else "Datenbasis 0–100")
        else:
            cfg[c] = _spalte(c, format="%.1f", width="small")
    signatur = zlib.crc32(("|".join(df["Name"].astype(str)) + "|".join(kopf)).encode()) if len(df) else 0
    ed = st.data_editor(df, key=_k(f"kat_{signatur}"), hide_index=True, width="stretch", height=_hoehe(len(df)),
                        disabled=[c for c in kopf if c != "＋"], column_config=cfg)
    for i, z in enumerate(zeilen):
        an = bool(ed.iloc[i]["＋"])
        if an and z["wkn"] not in wahl:
            wahl.append(z["wkn"])
        elif not an and z["wkn"] in wahl:
            wahl.remove(z["wkn"])

    st.caption("Renditen = Kursentwicklung (1 J.) bzw. p.a. über 3/5/10 J., Vola = Schwankung der letzten 12 Monate, "
               "Max DD = größter Rückgang seit Beginn der Historie. Risk Score 0–100: 45 % Vola, 35 % Drawdown, "
               "20 % Hebel. Base/Bear/Bull: " + D.VORSCHLAG["text"] + " Performance Fee und TER nur, soweit "
               "hinterlegt. Hohe Vergangenheitsrenditen sind keine Zukunftserwartung (Winner Bias).")

    gewaehlt = [k for k in D.KATALOG if k["wkn"] in wahl]
    c5, c6 = st.columns(2)
    gew = c5.number_input("Startgewicht je Baustein %", 0.0, 100.0, 0.0, step=0.5, key="pl_kat_gew",
                          help="Danach mit „Gewichtung 100k“ oder „Normalisieren“ verteilen")
    vorschlag = c6.toggle("Base/Bear/Bull-Vorschlag als Annahme", value=True, key="pl_kat_vs")
    if st.button(f"➕ {len(gewaehlt)} ausgewählte hinzufügen", key="pl_kat_add", width="stretch",
                 disabled=not gewaehlt):
        doppelt = []
        for k in gewaehlt:
            if _im_portfolio(m, k):
                doppelt.append(k["name"])
                continue
            kz = werte.get(k["wkn"]) or {}
            vs = E.vorschlag_renditen(kz, D.KATEGORIEN[k["category"]]["typ"]) if kz and not kz.get("fehler") else None
            extra = {"subCategory": k["profil"], "sector": k["sektor"], "region": k["region"],
                     "leverage": k["hebel"], "leverageType": k["hebel_typ"], "techAnteil": k["tech"],
                     "semiAnteil": k["semi"], "treiber": k["treiber"], "expenseRatio": k["ter"],
                     "performanceFee": k["perf_fee"],
                     "emittent": "Lang & Schwarz" if k["typ"] == "wikifolio" else None,
                     "historicalWinnerBias": bool(vs and vs["hist"] >= 0.20)}
            nutzen = vorschlag and vs is not None
            aid = _baustein_neu(
                m, k["name"], k["category"], wkn=k["wkn"], isin=k["isin"], gewicht=gew,
                rendite=vs["base"] * 100 if nutzen else None, extra=extra, auto=True,
                notiz=(D.VORSCHLAG["text"] + f" Historisch {vs['quelle']}: {_pct(vs['hist'])} p.a., "
                       f"Confidence {vs['confidence']}/100.") if nutzen else None)
            if nutzen:
                for sz in ("bear", "base", "bull"):
                    E.setze_annahme(m, aid, sz, vs[sz], notiz="Vorschlag aus Katalog – keine Prognose")
        st.session_state["planer_kat_wahl"] = []
        if doppelt:
            st.session_state["planer_meldung"] = ("warnung", "Schon im Portfolio, nicht doppelt angelegt: "
                                               + ", ".join(doppelt), [])
        _neu_zeichnen()
        st.rerun()
    if any(k["typ"] == "aktie" for k in gewaehlt) and any(a["category"] == "stock_basket" and a.get("enabled")
                                                           for a in m["assets"]):
        st.caption("Hinweis: Einige Aktien (z. B. NVIDIA, Broadcom, Quanta, Comfort Systems, Arista) stecken auch im "
                   "Fundamental Growth Basket – einzeln hinzugefügt, zählen sie doppelt.")


# --- 1 Allocation -----------------------------------------------------------
def _suche_hinzufuegen(m, h):
    c4, c5 = st.columns([3, 1], vertical_alignment="bottom")
    suchtext = c4.text_input("WKN oder ISIN", key=_k("add_such"), placeholder="z. B. A1JX52 oder IE00B4L5Y983")
    if c5.button("Suchen", key=_k("add_btn"), width="stretch", disabled=not suchtext.strip()):
        try:
            st.session_state["planer_treffer"] = h["suche_instrument"](suchtext.strip()) or []
        except Exception:
            st.session_state["planer_treffer"] = []
        st.session_state["planer_treffer_q"] = suchtext.strip()
    treffer = st.session_state.get("planer_treffer")
    if treffer is not None and st.session_state.get("planer_treffer_q"):
        if not treffer:
            st.warning(f"Kein Treffer für „{st.session_state['planer_treffer_q']}“.")
        else:
            wahl = st.selectbox("Treffer", list(range(len(treffer))), key=_k("add_wahl"),
                                format_func=lambda i: f'{treffer[i]["name"]} · {treffer[i].get("wkn") or "–"} · '
                                                      f'{treffer[i].get("isin") or ""}'.strip(" ·"))
            t = treffer[wahl]
            kats = list(D.KATEGORIEN)
            c6, c7, c8 = st.columns(3)
            kat = c6.selectbox("Kategorie", kats, index=kats.index(_kategorie_raten(t)),
                               format_func=lambda k: D.KATEGORIEN[k]["titel"], key=_k("add_kat"))
            gew = c7.number_input("Gewicht %", 0.0, 100.0, 0.0, step=0.5, key=_k("add_gew"))
            ren = c8.number_input("Annahme % p.a.", -50.0, 300.0, value=None, step=0.5, key=_k("add_ren"),
                                  placeholder="leer = später")
            if st.button("➕ Zum Portfolio hinzufügen", key=_k("add_ok"), width="stretch"):
                _baustein_neu(m, t["name"], kat, wkn=t.get("wkn"), isin=t.get("isin"), gewicht=gew, rendite=ren)
                st.session_state.pop("planer_treffer", None)
                st.session_state.pop("planer_treffer_q", None)
                _neu_zeichnen()
                st.rerun()
            st.caption("Ohne Annahme rechnet der Baustein mit 0 % – die historische Rendite erscheint nach dem "
                       "Hinzufügen unter „🗂️ Daten → Annahmen & Quellen“.")




def _editor_formular(df, key, **kw):
    """Tabelle als Formular: Aenderungen werden gesammelt und erst mit
    „Änderungen übernehmen“ gerechnet und gespeichert - nicht nach jeder
    einzelnen Zelle. Ohne Klick liefert die Funktion die unveraenderte
    Tabelle zurueck, die nachfolgende Uebernahme-Schleife findet dann nichts."""
    with st.form(key + "_form", border=False):
        st.markdown('<div class="pl-formhinweis">✏️ Werte in der Tabelle ändern – gerechnet und gespeichert wird '
                    'erst mit <b>„Daten aktualisieren“</b>.</div>', unsafe_allow_html=True)
        ed = st.data_editor(df, key=key, **kw)
        c1, c2 = st.columns(2)
        # Bewusst ohne type="primary": primaryColor ist in der App Weiss -
        # ein Primary-Button waere weisse Schrift auf weissem Grund.
        ok = c1.form_submit_button("🔄 Daten aktualisieren", width="stretch",
                                   help="Alle geänderten Werte übernehmen, neu berechnen und speichern")
        verwerfen = c2.form_submit_button("↺ Verwerfen", width="stretch",
                                          help="Nur noch nicht übernommene Änderungen in dieser Tabelle zurücknehmen")
    if verwerfen:
        _neu_zeichnen()
        st.rerun()
    return ed if ok else df


def _hoehe(zeilen):
    """Tabellenhoehe fuer st.data_editor: alle Zeilen sichtbar, kein inneres
    Scrollen. +16 px Reserve fuer eine evtl. waagerechte Scrollleiste, die
    sonst die letzte Zeile verdeckt."""
    return int(35 * (zeilen + 1) + 3 + 16)


def _smartphone():
    """True auf Smartphones (User-Agent). iPad/Desktop -> False: dort ist
    Platz fuer volle Spaltenbreiten. iPadOS meldet sich als Mac - passt."""
    try:
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:
        return False
    return "iphone" in ua or ("android" in ua and "mobile" in ua) or "ipod" in ua


def _kategorie_raten(t):
    """Kategorie eines Suchtreffers aus Name/WKN/Gattung - in den Stammdaten aenderbar."""
    txt = f'{t.get("name", "")} {t.get("kategorie", "")}'.lower()
    wkn = str(t.get("wkn", "")).upper()
    regeln = [
        (wkn.startswith("LS9") or "wikifolio" in txt, "wikifolio"),
        (any(x in txt for x in ("2x", "3x", "leverag", "hebel", "long x")), "leveraged_etf"),
        (any(x in txt for x in ("bitcoin", "ethereum", "crypto", "krypto")), "crypto"),
        (any(x in txt for x in ("semicond", "halbleiter", "chip")), "semiconductor"),
        (any(x in txt for x in ("gold", "silver", "silber", "miner", "copper", "kupfer", "rohstoff")), "mining"),
        ("small" in txt, "small_cap"),
        (any(x in txt for x in ("momentum", "quality", "value", "min vol", "dividend")), "factor"),
        (any(x in txt for x in ("nasdaq", "tech", "informat")), "technology"),
        (any(x in txt for x in ("etf", "ucits", "fonds", "fund", "index", "msci", "ftse", "s&p")), "global_equity"),
    ]
    return next((k for bed, k in regeln if bed), "single_stock")


def _baustein_neu(m, name, kategorie, *, wkn=None, isin=None, gewicht=0.0, rendite=None, extra=None,
                  notiz=None, auto=False):
    aid = "u_" + str(abs(zlib.crc32((name + (wkn or "") + datetime.datetime.now().isoformat()).encode())))
    a = D._asset(aid, name, kategorie, float(gewicht), isin=isin or None, ticker=wkn or None,
                 hebel=2.0 if kategorie == "leveraged_etf" else 1.0,
                 hebel_typ="daily" if kategorie == "leveraged_etf" else None,
                 notiz="Über den Portfolio Builder hinzugefügt.")
    a.update(extra or {})
    m["assets"].append(a)
    E.setze_annahme(m, aid, "manualScenario", None if rendite is None else float(rendite) / 100.0,
                    notiz=notiz or ("Eigene Annahme" if rendite is not None else "Wird aus der Kurshistorie ergänzt."),
                    auto=rendite is None or auto)
    return aid


def _basis_text(m, a):
    if a["category"] == "cash":
        return "Cash"
    rec = next((x for x in m["annahmen"] if x["assetId"] == a["id"] and x["sourceType"] == "manualScenario"), None)
    if rec is None or rec.get("value") is None:
        return "fehlt"
    if rec.get("auto"):
        src = str(rec.get("source") or "")
        if src.startswith("Kurshistorie ("):
            return "Hist. " + src[len("Kurshistorie ("):].rstrip(")").replace(" p.a.", "")
        if src.startswith(E.HOCH_PREFIX):
            return "Hochger. ⚠"
        if src == E.KURZ_TEXT:
            return "Kurz-Hist. ⚠"
        if src.startswith("Standard"):
            return "Standard ⚠"
        return "Startwert ⚠"
    return "eigene"


def _baustein_entfernen(m, aid):
    m["assets"] = [a for a in m["assets"] if a["id"] != aid]
    m["annahmen"] = [x for x in m["annahmen"] if x["assetId"] != aid]
    (m.get("holdings") or {}).pop(aid, None)
    if m["nachkauf"].get("ziel_asset") == aid:
        m["nachkauf"]["ziel_asset"] = "etf_allworld"


def _ziel_label(ziel):
    return f"{_de(ziel / 1000)}k" if ziel >= 1000 and ziel % 1000 == 0 else _de(ziel) + " €"


def _stueck_je_baustein(m, betrag, hist_assets, hist_korb):
    """Kaufplan fuer 'betrag', je Baustein zusammengefasst (Aktienkorb = Summe
    seiner Aktien). -> ({asset_id: {"stueck", "ist", "kurs", "korb": n}}, kaufplan)"""
    erg = E.kaufplan(_kauf_positionen(m, hist_assets or {}, hist_korb or {}), betrag,
                     bool((m.get("kaufplan") or {}).get("bruch")))
    je = {}
    for z in erg["zeilen"]:
        aid = z["id"].split(":")[0]
        e = je.setdefault(aid, {"stueck": 0.0, "ist": 0.0, "kurs": None, "korb": 0, "cash": bool(z.get("cash")),
                                "ohne_kurs": False})
        e["ist"] += z["ist"]
        if ":" in z["id"]:
            e["korb"] += 1 if z["stueck"] else 0
        else:
            e["stueck"], e["kurs"] = z["stueck"], z.get("kurs")
        if not z.get("cash") and not z.get("kurs"):
            e["ohne_kurs"] = True
    return je, erg


def _auf_stuecke(m, hist_assets, hist_korb):
    """Setzt jedes Gewicht auf den tatsaechlich gekauften Anteil (Stueck x Kurs
    fuer das Startkapital); der Rest der Stueckelung kommt zur Reserve.
    -> (geaendert, rest_prozent, reserve_name oder None)"""
    start = float(m["rahmen"]["startkapital"] or 0)
    if start <= 0:
        return False, 0.0, None
    stueck, _ = _stueck_je_baustein(m, start, hist_assets, hist_korb)
    vorher = {a["id"]: float(a.get("targetWeight") or 0) for a in m["assets"]}
    for a in m["assets"]:
        v = stueck.get(a["id"])
        if a.get("enabled") and v and not v["cash"] and not v["ohne_kurs"]:
            a["targetWeight"] = v["ist"] / start * 100     # ungerundet - sonst kippt die Stueckzahl
    rest = 100.0 - sum(float(a.get("targetWeight") or 0) for a in m["assets"]
                       if a.get("enabled") and a["category"] != "cash")
    cash_assets = [a for a in m["assets"] if a.get("enabled") and a["category"] == "cash"]
    if cash_assets:
        cash_assets[0]["targetWeight"] = max(rest, 0.0)
        for a in cash_assets[1:]:
            a["targetWeight"] = 0.0
    geaendert = any(abs(float(a.get("targetWeight") or 0) - vorher[a["id"]]) > 0.005 for a in m["assets"])
    return geaendert, max(rest, 0.0), cash_assets[0]["name"] if cash_assets else None


URTEIL_KURZ = {"attraktiv": "🟢 attraktiv", "eingeschraenkt": "🟡 mit Einschr.", "unattraktiv": "🔴 eher nicht"}


def _baustein_typ(a):
    k = a.get("category")
    if k in ("cash", "stock_basket"):
        return None
    return {"wikifolio": "wikifolio", "single_stock": "aktie"}.get(k, "etf")


def _bausteine_bewertung(m, h, hist_assets=None):
    """Score + Analyse je Baustein - gleiche Methode wie im Katalog „Alle Werte“.
    Werte aus der Watchlist werden dort gefunden (WKN/ISIN/Symbol); sonst wird aus der
    Kurshistorie des Planers gerechnet und gegen dieselbe Vergleichsgruppe bewertet.
    -> ({asset_id: {"z", "b", "a", "quelle"}}, stand_txt, q_stand_txt)"""
    hist_assets = hist_assets or {}
    strategie = st.session_state.get("pl_gk_strat") or "Ausgewogen"
    c_bw = _bw_basis(h, strategie)
    basis, stand, qvoll, q_stand = c_bw["basis"], c_bw["stand"], c_bw["qvoll"], c_bw["q_stand"]
    if not basis:
        return {}, None, None
    modell, ctx = c_bw["modell"], c_bw["ctx"]
    nach_kennung = {str(z["kennung"] or "").upper(): z for z in basis}
    nach_isin = {z["isin"]: z for z in basis if z.get("isin")}
    _, stand_k = _sc_alter(stand)
    _, stand_q = _sc_alter(q_stand)
    aus = {}
    for a in m["assets"]:
        typ = _baustein_typ(a)
        if not typ:
            continue
        z = None
        for k in (a.get("ticker"), a.get("yahoo")):
            if k and str(k).upper() in nach_kennung:
                z = nach_kennung[str(k).upper()]
                break
        if z is None and a.get("isin") in nach_isin:
            z = nach_isin[a["isin"]]
        if z is not None and z["typ"] == typ:
            z = dict(z, name=a["name"])
            quelle = "Watchlist (täglich vom Agenten berechnet)"
        else:
            ha = hist_assets.get(a["id"]) or {}

            def pz(feld, f=100.0):
                v = ha.get(feld)
                return None if v is None else round(float(v) * f, 2)
            vola = ha.get("vola1y") if ha.get("vola1y") is not None else ha.get("vola")
            z = {"typ": typ, "kat": a.get("category"), "name": a["name"], "kennung": a.get("ticker") or a["id"],
                 "isin": a.get("isin"), "r1": pz("historical1Y"), "r3": pz("historical3Y"),
                 "r5": pz("historical5Y"), "r10": pz("historical10Y"),
                 "vola": None if vola is None else round(float(vola) * 100, 1),
                 "maxdd": ha.get("maxdd"), "jahre": ha.get("jahre"), "div": None,
                 "qd": qvoll.get(a.get("yahoo") or a.get("ticker") or "") if typ == "aktie" else None}
            quelle = "Kurshistorie des Planers (nicht in der Watchlist)" if ha and not ha.get("fehler") else \
                "keine Kursdaten"
        b = modell.bewerte(z)
        if not b:
            continue
        an = AN.analysiere(z, b, ctx, stand=stand_k, q_stand=stand_q)
        aus[a["id"]] = {"z": z, "b": b, "a": an, "quelle": quelle, "ctx": ctx, "stand": stand_k,
                        "q_stand": stand_q}
    return aus, stand_k, stand_q


def _bausteine_analyse_anzeigen(m, h, bew):
    """Analysebox + aufklappbare Detailanalyse je aktivem Baustein."""
    aktiv = [a for a in m["assets"] if a.get("enabled") and a["id"] in bew]
    if not aktiv:
        return
    _abschnitt("🧠 Analyse der Bausteine")
    st.caption("Score, Analysebox und Detailanalyse wie im Katalog „🌐 Alle Werte“ – Strategie "
               f"„{(next(iter(bew.values()))['b'])['strategie']}“ (dort umstellbar). Gekennzeichnet: Fakt · Externe "
               "Prognose · Modell/Annahme · Einschätzung.")
    for a in sorted(aktiv, key=lambda x: -bew[x["id"]]["b"]["score_genau"]):
        e = bew[a["id"]]
        b, an = e["b"], e["a"]
        with st.expander(f'{a["name"]} · Score {b["score"]} · {an["emoji"]} {an["urteil_text"]} · '
                         f'{_pct(float(a.get("targetWeight") or 0) / 100)}'):
            st.markdown(
                f'<div class="sc-karte"><div class="sc-kopf"><span class="sc-name">{_esc(a["name"])}</span>'
                f'<span class="sc-typ">{_esc(BW.KLASSEN[e["z"]["typ"]])}</span>'
                f'<span class="sc-wert {_sc_farbe(b["score"])}">{b["score"]}<small>/100</small></span></div>'
                f'<div class="sc-balken"><div class="sc-bg-{BW.ampel(b["score"])}" style="width:{b["score"]}%"></div>'
                f'</div>{_sc_teile_html(b)}<div class="sc-meta">Datenqualität {b["datenqualitaet"]} · '
                f'{b["abdeckung"] * 100:.0f} % der Kriterien · Quelle: {_esc(e["quelle"])}</div></div>'
                + _analyse_box_html(an), unsafe_allow_html=True)
            if st.toggle("🔬 Detailanalyse", key=_k(f"bs_det_{a['id']}")):
                detail = _q_detail(h, e["z"])
                _detailanalyse(AN.analysiere(e["z"], b, e["ctx"], detail=detail, stand=e["stand"],
                                             q_stand=e["q_stand"]) if detail else an)

def _b_bausteine(m, R, h, hist_assets=None, hist_korb=None):
    _abschnitt("Bausteine")
    if getattr(E, "ENGINE_VERSION", None) != PLANER_VERSION:
        st.warning("⚠️ **planer_engine.py** im Repo ist nicht auf dem Stand von planer_ui.py "
                   f"(Rechenkern: {getattr(E, 'ENGINE_VERSION', 'alt')}, Oberfläche: {PLANER_VERSION}). "
                   "Bitte beide Dateien hochladen und die App neu starten (⋮ → Reboot app).")
    _auto_hinweis(m)
    if not any(a.get("enabled") and a.get("category") != "cash" for a in m["assets"]):
        st.markdown('<div class="wz-leer">Noch keine Bausteine aktiv.<br>Unten unter <b>„Baustein hinzufügen“</b> '
                    'im Katalog Werte ankreuzen (mit Score und Analyse) oder per WKN/ISIN suchen – oder in der '
                    'Tabelle „Aktiv“ anhaken.</div>', unsafe_allow_html=True)
    start = m["rahmen"]["startkapital"]
    summe = E.gewichte_summe(m) or 1.0
    bruch = bool((m.get("kaufplan") or {}).get("bruch"))
    stueck, kp = _stueck_je_baustein(m, start, hist_assets, hist_korb)
    try:
        bew, _, _ = _bausteine_bewertung(m, h, hist_assets)
    except Exception as ex:            # Bewertung darf die Tabelle nie blockieren
        bew = {}
        st.caption(f"Score/Analyse nicht verfügbar ({ex}).")
    zeilen = []
    for a in m["assets"]:
        eig = E.annahme(m, a["id"], "manualScenario")
        info = R["info"].get(a["id"]) or {}
        sz = stueck.get(a["id"]) if a.get("enabled") else None
        if not sz or sz["cash"]:
            stk_txt = "Cash" if sz and sz["cash"] else "–"
        elif sz["korb"]:
            stk_txt = f'Korb ({sz["korb"]} Akt.)'
        elif sz["ohne_kurs"]:
            stk_txt = "kein Kurs"
        else:
            stk_txt = (_de(sz["stueck"], 4).rstrip("0").rstrip(",") if bruch else _de(sz["stueck"]))
        zeilen.append({
            "Aktiv": bool(a.get("enabled")), "Baustein": a["name"],
            "Gew. %": float(a.get("targetWeight") or 0.0) if a.get("enabled") else 0.0,
            "Stück": stk_txt,
            "Score": (bew.get(a["id"]) or {}).get("b", {}).get("score"),
            "Urteil": URTEIL_KURZ.get((bew.get(a["id"]) or {}).get("a", {}).get("urteil"), "–"),
            "Daten": {"gut": "● gut", "mittel": "◐ mittel", "gering": "○ gering"}.get(
                (bew.get(a["id"]) or {}).get("b", {}).get("datenqualitaet"), "–"),
            "Kauf €": round(sz["ist"]) if sz else 0,
            "Real %": round(sz["ist"] / start * 100, 1) if sz and start else 0.0,
            "Annahme %": None if not eig or eig.get("value") is None else round(eig["value"] * 100, 2),
            "Basis": _basis_text(m, a),
            "Ist": a.get("renditequelle") == "historisch",
            "Fix": bool(a.get("fixiert")),
            "Kurs €": round(sz["kurs"], 2) if sz and sz.get("kurs") else None,
            "Betrag €": round(start * float(a.get("targetWeight") or 0) / summe) if a.get("enabled") else 0,
            "Genutzt %": None if info.get("netto") is None else round(info["netto"] * 100, 2),
            "Conf.": R["conf"].get(a["id"]),
        })
    df = pd.DataFrame(zeilen)
    # iPhone: schmale, feste Spalten, damit Name + Gewicht auf den Schirm passen.
    # iPad/Desktop: Spalten wachsen mit dem Inhalt (volle Namen, alles sichtbar).
    schmal = _smartphone()
    breite = (lambda w: w) if schmal else (lambda w: None)
    ed = _editor_formular(
        df, key=_k("builder"), hide_index=True, width="stretch", num_rows="fixed", height=_hoehe(len(df)),
        disabled=["Baustein", "Basis", "Betrag €", "Genutzt %", "Conf.", "Stück", "Kauf €", "Real %", "Kurs €",
                  "Score", "Urteil", "Daten"],
        column_config={
            "Score": _score_spalte(),
            "Urteil": st.column_config.TextColumn("Urteil", width="medium",
                                                  help="Gesamteinschätzung der Analyse (Details unter der Tabelle)"),
            "Daten": st.column_config.TextColumn("Daten", width=breite("small"),
                                                 help="Datenqualität: Anteil der Bewertungskriterien mit Daten"),
            "Basis": st.column_config.TextColumn(
                "Basis", width=breite("small"),
                help="Woher die Annahme stammt: „Hist. 5 J.“ usw. = automatisch aus der bisherigen Rendite p.a. "
                     "(wird täglich nachgeführt), „Hochger. ⚠“ = weniger als 1 Jahr Kurshistorie – Ø Monatsrendite seit Start "
                     "aufs Jahr hochgerechnet (wenig belastbar, ab 1 Jahr Historie automatisch ersetzt), "
                     "„Kurz-Hist. ⚠“ = unter 1 Monat Kurshistorie – Kategorie-Standard (gedämpft), „Standard ⚠“ = keine Kursdaten gefunden, Kategorie-Standard, „Startwert ⚠“ = Wert aus dem "
                     "Ausgangsmodell, keine Kursdaten, „eigene“ = selbst eingetragen"),
            "Aktiv": st.column_config.CheckboxColumn("Aktiv", width=breite("small")),
            "Baustein": st.column_config.TextColumn("Baustein", width=breite("medium")),
            "Gew. %": st.column_config.NumberColumn("Gew. %", min_value=0.0, max_value=100.0, step=0.5,
                                                    format="%.1f", width=breite("small"),
                                                    help="Anteil am Gesamtportfolio – auch für Wikifolios frei einstellbar"),
            "Annahme %": st.column_config.NumberColumn(
                "Annahme %", step=0.5, format="%.1f", width=breite("small"),
                help="Eigene Renditeannahme p.a. (Szenario, keine Prognose)"),
            "Ist": st.column_config.CheckboxColumn(
                "Ist", width=breite("small"),
                help="Tatsächliche Rendite laut Kurshistorie statt der Annahme verwenden (Standard bei Wikifolios)"),
            "Fix": st.column_config.CheckboxColumn(
                "Fix", width=breite("small"),
                help="Fixierte Gewichte bleiben bei allen Verfahren unter „Gewichtung“ unverändert"),
            "Betrag €": st.column_config.NumberColumn("Soll €", format="%d",
                                                      help="Startkapital × Gewicht (ohne Rücksicht auf Stückelung)"),
            "Stück": st.column_config.TextColumn("Stück", width=breite("small"),
                                                 help="Ganze Stücke zum aktuellen Kurs für das Startkapital "
                                                      "(Bruchstücke, wenn im Kaufplan eingeschaltet)"),
            "Kauf €": st.column_config.NumberColumn("Kauf €", format="%d", width=breite("small"),
                                                    help="Tatsächlicher Kaufbetrag = Stück × Kurs"),
            "Real %": st.column_config.NumberColumn("Real %", format="%.1f", width=breite("small"),
                                                    help="Tatsächlicher Anteil nach Stückelung"),
            "Kurs €": st.column_config.NumberColumn("Kurs €", format="%.2f",
                                                    help="Letzter Schlusskurs laut ls-tc.de"),
            "Genutzt %": st.column_config.NumberColumn("Genutzt %", format="%.1f",
                                                       help="In der Rechnung verwendet (aktive Quelle, ggf. netto)"),
            "Conf.": st.column_config.NumberColumn("Conf.", format="%d",
                                                   help="Belastbarkeit der Datenbasis 0–100"),
        })
    geaendert = False
    for i, a in enumerate(m["assets"]):
        z = ed.iloc[i]
        aktiv = bool(z["Aktiv"])
        gew = 0.0 if pd.isna(z["Gew. %"]) or not aktiv else float(z["Gew. %"])   # inaktiv = 0 %
        if aktiv != bool(a.get("enabled")) or abs(gew - float(a.get("targetWeight") or 0)) > 1e-9:
            a["enabled"], a["targetWeight"] = aktiv, gew
            geaendert = True
        ist = "historisch" if bool(z["Ist"]) else "annahme"
        if a["category"] != "cash" and ist != a.get("renditequelle"):
            a["renditequelle"] = ist
            geaendert = True
        if bool(z["Fix"]) != bool(a.get("fixiert")):
            a["fixiert"] = bool(z["Fix"])
            geaendert = True
        ann = z["Annahme %"]
        if not pd.isna(ann):
            eig = E.annahme(m, a["id"], "manualScenario")
            # Toleranz: die Tabelle zeigt 2 Nachkommastellen - nur echte Aenderungen
            # zaehlen (sonst wuerde jede automatische Annahme zur "eigenen")
            if eig is None or eig.get("value") is None or abs(eig["value"] * 100.0 - float(ann)) > 0.006:
                E.setze_annahme(m, a["id"], "manualScenario", float(ann) / 100.0)
                geaendert = True
    if geaendert:
        st.rerun()

    summe = E.gewichte_summe(m)
    c1, c2 = st.columns(2, vertical_alignment="center")
    c1.markdown(f'<div class="pl-zeile" style="margin:0">Summe aktiver Gewichte: <b class="{"pl-gut" if abs(summe - 100) <= 0.05 else "pl-schlecht"}">'
                f'{_de(summe, 1)} %</b></div>', unsafe_allow_html=True)
    if c2.button("Auf 100 % normalisieren", key=_k("norm"), width="stretch", disabled=abs(summe - 100) <= 0.05):
        E.normalisieren(m)
        _neu_zeichnen()
        st.rerun()
    # Stueckelung: was fuer das Startkapital wirklich gekauft wird
    investiert = sum(v["ist"] for v in stueck.values() if not v["cash"])
    cash = start - investiert
    st.markdown(f'<div class="pl-zeile">Für <b>{_de(start)} €</b> Startkapital: gekauft '
                f'<b>{_de(investiert, 2)} €</b> in {"Bruchstücken" if bruch else "ganzen Stücken"} · '
                f'Cash (Reserve + Rest) <b>{_de(cash, 2)} €</b></div>', unsafe_allow_html=True)
    if kp["ohne_kurs"]:
        st.caption("Ohne aktuellen Kurs (Stückzahl nicht berechenbar): " + ", ".join(kp["ohne_kurs"]))
    if kp.get("mindest"):
        st.caption("Mindestens 1 Stück gekauft, obwohl das Gewicht dafür eigentlich nicht reicht (Kurs höher als "
                   "der Anteil): " + ", ".join(str(x) for x in kp["mindest"]) + " – der Mehrbetrag kommt aus "
                   "Rest bzw. Reserve" + (f"; Startkapital um {_de(kp['ueberzogen'], 2)} € überschritten"
                                          if kp.get("ueberzogen") else "") + ".")
    kpe = m.setdefault("kaufplan", {"betrag": float(start), "bruch": False})
    runden = st.toggle("Gewichte immer auf ganze Stücke ausrichten", value=bool(kpe.get("runden")), key=_k("stk_runden"),
                       help="Prozente = tatsächlich gekaufter Anteil (Stück × Kurs) für das Startkapital, der Rest der "
                            "Stückelung geht in die Reserve. Gilt auch nach der automatischen Gewichtung – das Ziel "
                            "wird dann bis auf die Rundung erreicht.")
    if runden != bool(kpe.get("runden")):
        kpe["runden"] = runden
        st.rerun()
    if not runden and st.button("🧮 Einmalig: Gewichte auf die Stückzahlen übernehmen", key=_k("stk_ueber"),
                                width="stretch", disabled=bool(_auto_modus(m)) or not start or not investiert):
        _, rest, res = _auf_stuecke(m, hist_assets, hist_korb)
        st.session_state["planer_meldung"] = ("ok", f"Gewichte auf die Stückzahlen gesetzt – Rest {_de(rest, 1)} % "
                                              + (f"in „{res}“." if res else "unverteilt (keine Reserve aktiv)."), [])
        _neu_zeichnen()
        st.rerun()
    if not runden and _auto_modus(m):
        st.caption("Die automatische Gewichtung ist aktiv – für Stückzahlen den Schalter oben einschalten, dann "
                   "werden ihre Prozente jeweils auf ganze Stücke gerundet.")
    if investiert > 0:
        with st.expander("📦 Diese Stückzahlen als Musterdepot übernehmen", expanded=False):
            _musterdepot_formular(h, kp, float(start), "bs")
    ann_ok = st.checkbox("Eigene Annahmen dabei überschreiben (Bestätigung)", key=_k("ann_hist_ok"))
    if st.button("📥 Alle Annahmen aus bisheriger Rendite p.a.", key=_k("ann_hist"), width="stretch",
                 disabled=not ann_ok,
                 help="Setzt auch selbst eingetragene Annahmen wieder auf die bisherige Rendite p.a. laut "
                      "Kurshistorie zurück (5 J., sonst 3 J., sonst seit Start, sonst 1 J.; bei weniger als 1 Jahr "
                      "Historie die Ø Monatsrendite aufs Jahr hochgerechnet, unter 1 Monat und ohne Kursdaten "
                      "Standardwert der Kategorie)"):
        n = E.annahmen_aus_historie(m, st.session_state.get("planer_historie") or {}, alle=True)
        st.session_state["planer_meldung"] = ("ok", f"{n} Annahmen aus der bisherigen Rendite p.a. übernommen.", [])
        _neu_zeichnen()
        st.rerun()
    _meldung_zeigen()
    st.caption("Spalten: Gew. % = Anteil · Stück / Kauf € / Real % = was für das Startkapital zum aktuellen Kurs "
               "wirklich gekauft wird (Kurs € = letzter Schlusskurs) · Soll € = Startkapital × Gewicht · "
               "Annahme % = Rendite p.a. (Basis zeigt die Herkunft) · Ist = tatsächliche "
               "Rendite laut Kurshistorie statt Annahme · Fix = bleibt beim Gewichten unverändert · Genutzt % = "
               "damit wird gerechnet. Gewichte automatisch verteilen: Bereich „⚖️ Gewichtung“. "
               "Score / Urteil / Daten = Analyse wie im Katalog (Details unter „🧠 Analyse der Bausteine“).")
    try:
        _bausteine_analyse_anzeigen(m, h, bew)
    except Exception as ex:
        st.caption(f"Analyse der Bausteine nicht verfügbar ({ex}).")

    _abschnitt("Baustein hinzufügen")
    leer = not any(a_.get("enabled") and a_.get("category") != "cash" for a_ in m["assets"])
    # Der Katalog (alle Werte mit Score) ist der aufwendigste Teil der Seite - er wird nur
    # gezeichnet, wenn er gebraucht wird; der Schalter merkt sich die Wahl in der Sitzung.
    if st.toggle("➕ Katalog und Suche öffnen", value=st.session_state.get("pl_add_offen", leer),
                 key="pl_add_offen", help="Alle Werte der Watchlist mit Score und Analyse oder Suche per WKN/ISIN"):
        weg_ = st.pills("Hinzufügen über", ["📋 Katalog", "🔎 WKN / ISIN"], default="📋 Katalog", key="pl_add_art")
        if weg_ == "🔎 WKN / ISIN":
            _suche_hinzufuegen(m, h)
        else:
            _katalog(m, h)
    else:
        st.caption("Zum Hinzufügen neuer ETFs, Aktien oder Wikifolios den Schalter einschalten.")

    _abschnitt("Baustein entfernen")
    c9, c10 = st.columns([3, 1], vertical_alignment="center")
    weg = c9.selectbox("Baustein", [a["id"] for a in m["assets"]], key=_k("del_wahl"),
                       format_func=lambda i: _asset(m, i)["name"], label_visibility="collapsed")
    sicher_weg = st.checkbox("Ja, diesen Baustein samt Annahmen endgültig entfernen", key=_k("del_ok"))
    if c10.button("🗑 Entfernen", key=_k("del_btn"), width="stretch", disabled=not m["assets"] or not sicher_weg):
        _baustein_entfernen(m, weg)
        _neu_zeichnen()
        st.rerun()
    st.caption("Entfernen löscht den Baustein samt Annahmen aus diesem Modell; „Aktiv“ abwählen lässt ihn in "
               "der Liste, sein Anteil wird 0 %.")

    _abschnitt("Zurücksetzen")
    st.caption("„↺ Verwerfen“ unter der Tabelle nimmt nur noch nicht übernommene Tabellen-Änderungen zurück. "
               "Hier wird das komplette Modell auf das Ausgangsmodell zurückgesetzt – Bausteine, Gewichte, "
               "Annahmen, Planung und Grenzen.")
    if _eigener_bereich(h):
        st.caption("Dein Ausgangsmodell ist leer: Startkapital, Sparrate, Ziel und alle Gewichte 0, keine Entnahme.")
    sicher = st.checkbox("Ja, alles auf das Ausgangsmodell zurücksetzen", key=_k("reset_ok"))
    if st.button("↺ Modell komplett zurücksetzen", key=_k("reset_btn"), width="stretch", disabled=not sicher):
        st.session_state["planer_modell"] = _start_modell(h)
        for k in ("planer_vorschlag", "planer_meldung", "planer_autogew"):
            st.session_state.pop(k, None)
        st.session_state["planer_meldung"] = ("ok", "Modell auf das Ausgangsmodell zurückgesetzt"
                                              + (" (alle Eingaben 0)." if _eigener_bereich(h) else "."), [])
        _neu_zeichnen()
        st.rerun()


def _meldung_zeigen():
    meldung = st.session_state.get("planer_meldung")
    if meldung:
        art, text, verletzt = meldung
        {"ok": st.success, "warnung": st.warning, "fehler": st.error}[art](text)
        if verletzt:
            st.caption("Hinweis – über den Optimizer-Grenzen: " + " · ".join(verletzt) + ". Reine Rückrechnung aus "
                       "den Annahmen, keine Empfehlung.")


def _b_aufteilung(m, R):
    _abschnitt("Aufteilung")
    start = m["rahmen"]["startkapital"]
    w = E.gewichte(m)
    namen = {a["id"]: a["name"] for a in m["assets"]}
    ids = [i for i in w if w[i] > 0]
    fig = go.Figure(go.Pie(labels=[namen[i] for i in ids], values=[w[i] * 100 for i in ids], hole=0.55,
                           sort=False, marker=dict(colors=FARBEN[:len(ids)], line=dict(color="#000", width=1)),
                           textinfo="percent", hovertemplate="%{label}: %{value:.1f} %<extra></extra>"))
    _layout(fig, 380, legende=True)
    fig.update_layout(legend=dict(orientation="h", y=-0.05, yanchor="top"), margin=dict(t=10, b=10))
    _chart(fig, "pl_alloc")

    # Nach Kategorie
    kat = {}
    for i in ids:
        titel = D.KATEGORIEN.get(_asset(m, i)["category"], {}).get("titel", _asset(m, i)["category"])
        kat[titel] = kat.get(titel, 0.0) + w[i] * 100
    _tabelle(["Kategorie", "Anteil", "Betrag"],
             [[_esc(k), _pct(v, anteil=False), _eur(start * v / 100, False)] for k, v in
              sorted(kat.items(), key=lambda x: -x[1])])




# --- Gewichtung: EIN Assistent statt verstreuter Knoepfe ----------------------
VERFAHREN = {"rendite": "⚖️ Nach Rendite p.a.", "gleich": "🟰 Gleich verteilt", "ziel": "🎯 Auf Ziel rechnen",
             "start": "↺ Startgewichte"}
VERFAHREN_TEXT = {
    "rendite": "Verteilt die freien Prozente im Verhältnis der Rendite p.a. (Spalte „Genutzt %“). Bausteine mit "
               "Rendite ≤ 0 bekommen 0 %. Bezieht auch neue Bausteine mit bisher 0 % ein.",
    "gleich": "Alle aktiven, nicht fixierten Bausteine bekommen denselben Anteil – die neutrale Ausgangsbasis.",
    "ziel": "Rechnet die Gewichte so, dass das Modell ein Ziel trifft: Zielvermögen oder Wunschrendite p.a. "
            "Ohne Grenzen werden die bisherigen Gewichte stufenlos zu den renditestärkeren Bausteinen verschoben "
            "(Bausteine mit 0 % bleiben außen vor). Mit Grenzen verteilt ein Optimizer so breit wie möglich.",
    "start": "Stellt die Platzhalter-Gewichte des Ausgangsmodells wieder her; gelöschte Start-Bausteine kommen zurück.",
}


def _mit_gewichten(m, gew):
    m2 = dict(m)
    m2["assets"] = [dict(a, targetWeight=gew[a["id"]]) if a["id"] in gew else a for a in m["assets"]]
    return m2


def _grenzen_editor(m):
    g = m["grenzen"]
    g["einzelasset_max"] = float(st.number_input("Max. Gewicht je Baustein (%)", 1.0, 100.0,
                                                 float(g["einzelasset_max"]), step=1.0, key=_k("g_einzel")))
    df = pd.DataFrame([{"Grenze": x["titel"], "Max %": x.get("max"), "Min %": x.get("min")} for x in g["gruppen"]])
    ed = st.data_editor(df, key=_k("grenzen"), hide_index=True, height=_hoehe(len(df)), width="stretch",
                        disabled=["Grenze"],
                        column_config={"Max %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
                                       "Min %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0)})
    for i, x in enumerate(g["gruppen"]):
        mx, mn = ed.iloc[i]["Max %"], ed.iloc[i]["Min %"]
        x["max"] = None if pd.isna(mx) else float(mx)
        x["min"] = None if pd.isna(mn) else float(mn)
    st.caption("Halbleiter zählt den Halbleiteranteil je Baustein (VanEck Semiconductor 100 %, Korb nach "
               "Zusammensetzung); Indizes ohne hinterlegten Anteil zählen 0 – ergänzbar unter „🗂️ Daten“.")


def _vorschlag(m, R, verfahren, ziel_art, wunsch, mit_grenzen):
    """-> dict(gewichte, art, text) - noch NICHT uebernommen."""
    rahmen = m["rahmen"]
    if verfahren == "rendite":
        erg = E.gewichte_nach_rendite(m, R["r"])
        if erg.get("fehler"):
            return {"art": "fehler", "text": erg["fehler"]}
        return {"gewichte": erg["gewichte"], "art": "ok", "text": "Verteilung nach Rendite p.a."}
    if verfahren == "gleich":
        aktiv = E.aktive_assets(m)
        fest = {a["id"]: float(a.get("targetWeight") or 0) for a in aktiv
                if a.get("fixiert") or a["category"] == "cash"}
        frei = [a["id"] for a in aktiv if a["id"] not in fest]
        rest = 100.0 - sum(fest.values())
        if not frei or rest <= 0:
            return {"art": "fehler", "text": "Keine freien Bausteine zum Verteilen."}
        return {"gewichte": {**fest, **{i: rest / len(frei) for i in frei}}, "art": "ok",
                "text": f"Gleich verteilt: {len(frei)} Bausteine je {_pct(rest / len(frei), 1, anteil=False)}."}
    if verfahren == "start":
        seed = {a["id"]: a["targetWeight"] for a in D.SEED_ASSETS}
        gew = {a["id"]: seed.get(a["id"], 0.0) for a in m["assets"]}
        return {"gewichte": gew, "art": "ok", "text": "Startgewichte des Ausgangsmodells (Platzhalter).",
                "start": True}
    # Ziel
    if int(rahmen.get("horizont_jahre") or 0) <= 0:
        return {"art": "fehler", "text": "Keine Aufbauphase (0 Jahre) – für eine Zielrendite in der Entnahme die "
                                         "automatische Gewichtung unter „🎯 Ziel & Rahmen → 💸 Entnahme“ (bzw. ⚙️ Planung → Phase 2) nutzen."}
    # dieselbe Rechnung wie die KPIs: Kredite (Kapital, Restschuld, Raten) und
    # gleichzeitige Entnahme eingerechnet
    eff = _mit_krediten(m)
    kr = _kredit_rahmen(m)
    if ziel_art == "rendite":
        zielwert = E.ziel_aus_rendite(eff, wunsch / 100.0)
        ziel_txt = f"{_de(wunsch, 1)} % p.a. (≈ {_de(E.runden_ungefaehr(zielwert))} €)"
    else:
        zielwert = float(eff["rahmen"]["zielvermoegen"])
        ziel_txt = f"{_de(rahmen['zielvermoegen'])} €" + (
            f" (+ Restschuld {_de(kr['restschuld'])} € = {_de(zielwert)} € Depotwert)" if kr and kr["restschuld"] > 0.5
            else "")
    if mit_grenzen:
        return _vorschlag_grenzen(eff, R, zielwert, ziel_txt)
    erg = E.gewichtung_fuer_ziel(eff, R["r"], ziel=zielwert, rebalancing=R["reb"])
    if erg.get("fehler"):
        return {"art": "fehler", "text": erg["fehler"]}
    if not erg["erreichbar"] and erg.get("min_endwert") is not None:
        return {"art": "fehler", "text": f"Ziel {ziel_txt} liegt unter dem kleinsten mit diesen Bausteinen "
                                         f"möglichen Endwert (mindestens {_eur(erg['min_endwert'])}) – es wird "
                                         "in jedem Fall übertroffen. Renditeschwächere Bausteine/Reserve ergänzen "
                                         "oder Fixierungen lösen."}
    if not erg["erreichbar"]:
        return {"art": "fehler", "text": f"Ziel {ziel_txt} ist mit den aktuellen Annahmen auch bei maximaler "
                                         f"Verschiebung nicht erreichbar (höchstens {_eur(erg['max_endwert'])}). "
                                         "Fixierungen lösen, Annahmen prüfen oder Grenzen nutzen."}
    return {"gewichte": erg["gewichte"], "art": "ok", "text": f"Ziel {ziel_txt} exakt erreicht.",
            "endwert": erg["endwert"]}


def _vorschlag_grenzen(eff, R, zielwert, ziel_txt):
    """Optimizer unter den Grenzen fuer das effektive Modell (inkl. Krediten und
    Entnahme). Der LP-Optimizer rechnet linear ohne Entnahme/Kreditraten/Rebalancing -
    deshalb wird sein Zielwert per Bisektion so nachgestellt, dass die ECHTE
    Projektion (wie die KPIs) das Ziel trifft; geht das nicht, ehrlich melden."""
    aktive = [a["id"] for a in E.aktive_assets(eff)]

    def opt(z):
        o = E.optimiere(eff, R["r"], R["conf"], ziel=z)
        if not o or o.get("fehler"):
            return o, None, None
        g = {i: o["gewichte"].get(i, 0.0) for i in aktive}
        return o, g, E.projektion(_mit_gewichten(eff, g), R["r"], rebalancing=R["reb"])["endwert"]

    o, g, ew = opt(zielwert)
    if not o or o.get("fehler"):
        return {"art": "fehler", "text": (o or {}).get("fehler") or "Keine Lösung."}
    def passt(e):           # Ziel erreicht, hoechstens 1 EUR darueber
        return 0.0 <= e - zielwert <= 1.0

    if not passt(ew):
        # hoechster unter den Grenzen moeglicher Endwert (renditestaerkste LP-Loesung)
        _o, g_max, ew_max = opt(max(o["max_endwert"], zielwert) * 10.0 + 1.0)
        if ew_max < zielwert - 1.0:
            return {"gewichte": g_max, "art": "warnung",
                    "text": f"Ziel {ziel_txt} ist unter den Grenzen nicht erreichbar. Vorschlag = höchster möglicher "
                            f"Endwert unter den Grenzen ({_eur(ew_max)}, inkl. Entnahme/Kreditraten)."}
        lo, hi = (zielwert, o["max_endwert"]) if ew < zielwert else (0.0, zielwert)
        g_best, ew_best = (g_max, ew_max) if ew < zielwert else (g, ew)
        for _ in range(60):
            mitte = (lo + hi) / 2.0
            _o, g_m, ew_m = opt(mitte)
            if g_m is None:
                break
            if ew_m >= zielwert:
                hi, g_best, ew_best = mitte, g_m, ew_m
                if passt(ew_m):
                    break
            else:
                lo = mitte
        g, ew = g_best, ew_best
    if passt(ew):
        return {"gewichte": g, "art": "ok", "text": f"Ziel {ziel_txt} innerhalb aller Grenzen erreichbar.",
                "endwert": ew}
    if ew > zielwert + 1.0:
        return {"gewichte": g, "art": "warnung", "endwert": ew,
                "text": f"Ziel {ziel_txt} wird unter den Grenzen übertroffen – genauer als {_eur(ew)} (inkl. "
                        "Entnahme/Kreditraten) lässt es sich nicht ansteuern. Grenzen (z. B. Mindestanteile) prüfen."}
    return {"gewichte": g, "art": "warnung", "endwert": ew,
            "text": f"Ziel {ziel_txt} unter den Grenzen nicht genau erreichbar – höchstens {_eur(ew)}."}


def _b_gewichtung(m, R):
    _abschnitt("Gewichtung")
    _auto_hinweis(m)
    st.caption("Ein Verfahren wählen → Vorschlag berechnen → vergleichen → übernehmen. Fixierte Bausteine "
               "(Spalte „Fix“) und die Reserve bleiben immer unverändert.")
    keys = list(VERFAHREN)
    wahl = st.pills("Verfahren", [VERFAHREN[k] for k in keys], default=VERFAHREN["rendite"], key="pl_verfahren") \
        or VERFAHREN["rendite"]
    verfahren = keys[[VERFAHREN[k] for k in keys].index(wahl)]
    st.markdown(f'<div class="pl-zeile">{_esc(VERFAHREN_TEXT[verfahren])}</div>', unsafe_allow_html=True)

    ziel_art, wunsch, mit_grenzen = "vermoegen", None, False
    if verfahren == "ziel":
        rahmen = m["rahmen"]
        req = R["zus"]["erforderliche_cagr"] or 0.0
        ziel_art = st.radio("Ziel", ["vermoegen", "rendite"], horizontal=True, key=_k("ziel_art"),
                            format_func=lambda x: (f"Zielvermögen {_ziel_label(rahmen['zielvermoegen'])}"
                                                   if x == "vermoegen" else "Wunschrendite p.a."))
        if ziel_art == "rendite":
            wunsch = float(st.number_input("Wunschrendite p.a. (%)", -20.0, 200.0,
                                           float(rahmen.get("wunschrendite") if rahmen.get("wunschrendite") is not None
                                                 else round(req * 100, 1)), step=1.0, key=_k("wunsch")))
            rahmen["wunschrendite"] = wunsch
        else:
            st.caption(f"Benötigt für das Zielvermögen: {_pct(req)} p.a. (Zielvermögen und Dauer unter "
                       "„⚙️ Planung“).")
        mit_grenzen = st.toggle("Optimizer-Grenzen einhalten (breit streuen)", value=False, key=_k("mit_grenzen"))
        with st.expander("Optimizer-Grenzen bearbeiten", expanded=False):
            _grenzen_editor(m)

    sig = (verfahren, ziel_art, wunsch, mit_grenzen)
    if st.button("🔍 Vorschlag berechnen", key=_k("vorschlag_btn"), width="stretch"):
        v = _vorschlag(m, R, verfahren, ziel_art, wunsch, mit_grenzen)
        v["sig"] = sig
        st.session_state["planer_vorschlag"] = v
    v = st.session_state.get("planer_vorschlag")
    if not v or v.get("sig") != sig:
        _meldung_zeigen()
        return
    {"ok": st.success, "warnung": st.warning, "fehler": st.error}[v["art"]](v["text"])
    gew = v.get("gewichte")
    if not gew:
        return

    # Vergleich vorher / nachher
    summe = E.gewichte_summe(m) or 1.0
    vorher = R["zus"].get("endwert_netto", R["zus"]["endwert"])
    try:     # gleiche Rechnung wie die KPIs (Kredite, Entnahme, Rechenrenditen, nach Restschuld)
        _kr = R["zus"].get("kredit")
        nachher = E.projektion(_mit_krediten(_mit_gewichten(m, gew)), R.get("r_calc", R["r"]),
                               rebalancing=R["reb"])["endwert"] - (_kr["restschuld"] if _kr else 0.0)
    except Exception:
        nachher = None
    jahre = m["rahmen"]["horizont_jahre"]
    ohne_spar = not m["rahmen"].get("sparrate_monat")
    _kacheln([
        ("Endwert vorher", _eur(vorher), _pct(E.required_cagr(m["rahmen"]["startkapital"], vorher, jahre)) + " p.a."
         if ohne_spar else None),
        ("Endwert nachher", _eur(nachher), (_pct(E.required_cagr(m["rahmen"]["startkapital"], nachher, jahre))
                                            + " p.a.") if ohne_spar and nachher else None),
    ], klein=True)
    namen = {a["id"]: a["name"] for a in m["assets"]}
    zeilen = []
    for aid, neu in sorted(gew.items(), key=lambda x: -x[1]):
        a = _asset(m, aid)
        if a is None:
            continue
        alt = float(a.get("targetWeight") or 0) * 100 / summe if a.get("enabled") else 0.0
        if neu < 0.005 and alt < 0.005:
            continue
        d = neu - alt
        zeilen.append([_esc(namen[aid]), _pct(alt, 1, anteil=False), f"<b>{_pct(neu, 1, anteil=False)}</b>",
                       f'<span class="{"pl-gut" if d > 0.05 else "pl-schlecht" if d < -0.05 else ""}">'
                       f'{_pct(d, 1, vorzeichen=True, anteil=False)}</span>'])
    _tabelle(["Baustein", "Aktuell", "Neu", "Δ"], zeilen)
    verletzt = E.grenzen_verletzungen(m, {i: g for i, g in gew.items() if g > 0})
    if verletzt:
        st.caption("Über den Optimizer-Grenzen: " + " · ".join(verletzt) + ".")
    c1, c2 = st.columns(2)
    if c1.button("✔ Vorschlag übernehmen", key=_k("vorschlag_ok"), width="stretch"):
        if v.get("start"):
            vorhanden = {a["id"] for a in m["assets"]}
            seed_m = D.seed_modell()
            for a in seed_m["assets"]:
                if a["id"] not in vorhanden:
                    m["assets"].append(a)
                    m["annahmen"] += [x for x in seed_m["annahmen"] if x["assetId"] == a["id"]]
            seed = {a["id"]: a for a in D.SEED_ASSETS}
            for a in m["assets"]:
                a["targetWeight"] = seed[a["id"]]["targetWeight"] if a["id"] in seed else 0.0
                if a["id"] in seed:
                    a["enabled"] = seed[a["id"]]["enabled"]
        else:
            for a in m["assets"]:
                if a["id"] in gew:
                    a["targetWeight"] = gew[a["id"]]
        st.session_state["planer_meldung"] = ("ok", f"Gewichtung übernommen: {v['text']}", verletzt)
        st.session_state.pop("planer_vorschlag", None)
        _neu_zeichnen()
        st.rerun()
    if c2.button("✖ Verwerfen", key=_k("vorschlag_weg"), width="stretch"):
        st.session_state.pop("planer_vorschlag", None)
        st.rerun()
    st.caption("Reine Rückrechnung aus den Annahmen – keine Renditeprognose, keine Anlageempfehlung.")


# --- 2 Projected Growth -----------------------------------------------------
def _gesamtverlauf(m, R):
    """Aufbau + Entnahme als EINE Zeitachse (Monatswerte) und Jahrestabelle.
    Funktioniert auch ohne Aufbau (0 Jahre), ohne Ziel und ohne Sparrate."""
    rahmen = m["rahmen"]
    proj = R["zus"]["projektion"]
    aufbau = list(proj["monatswerte"])
    n_auf = len(aufbau) - 1
    eff_r = _mit_krediten(m)["rahmen"]
    spar = float(eff_r.get("sparrate_monat") or 0.0)
    raten = eff_r.get("kredit_raten")
    ent_p = _entnahme_parallel(m)
    zeilen = []
    for j in range(n_auf // 12):
        anf, ende = aufbau[j * 12], aufbau[(j + 1) * 12]
        fluss = spar * 12 - sum(E._entnahme_monat(ent_p, mm) + E.kredit_rate_monat(raten, mm)
                                for mm in range(j * 12 + 1, j * 12 + 13))
        zeilen.append({"jahr": j + 1, "phase": "Aufbau + Entnahme" if ent_p else "Aufbau", "anfang": anf,
                       "fluss": fluss, "ertrag": ende - anf - fluss, "steuer": 0.0, "ende": ende})
    e = _entnahme_daten(m)
    ent, rendite, plan = [], None, None
    if e.get("aktiv", True) and float(e.get("monatlich") or 0) > 0:
        _, rendite, _, plan = _entnahme_rechnen(m, R, e)
        jahre = int(e["dauer_jahre"])
        ent = plan["verlauf"][: jahre * 12 + 1]
        for z in plan["jahre_tabelle"][:jahre]:
            zeilen.append({"jahr": n_auf // 12 + z["jahr"], "phase": "Entnahme", "anfang": z["anfang"],
                           "fluss": -z["netto"], "ertrag": z["ertrag"], "steuer": z.get("steuer", 0.0),
                           "ende": z.get("ende", 0.0)})
    return aufbau, ent, zeilen, rendite, plan


def _jahres_chart(zeilen, ziel=0.0, rendite=None):
    """Die Jahresuebersicht als reiner Linienchart (ein Punkt je Jahr):
    Vermoegen (Jahr 0 = Anfangswert, danach Endwert = Anfang des Folgejahres),
    Ertraege je Jahr nach oben, Entnahmen je Jahr und in Summe nach unten."""
    xs = [0] + [z["jahr"] for z in zeilen]
    verm = [zeilen[0]["anfang"]] + [z["ende"] for z in zeilen]
    ertr = [0.0] + [z["ertrag"] for z in zeilen]
    ein = [0.0] + [max(z["fluss"], 0.0) for z in zeilen]
    aus = [0.0] + [min(z["fluss"], 0.0) - z["steuer"] for z in zeilen]
    summe_aus, s_ = [], 0.0
    for v in aus:
        s_ += v
        summe_aus.append(s_)
    # Vergleich: dasselbe Vermoegen OHNE Entnahme (gleiche Rendite, Einzahlungen bleiben)
    ohne, w_ = [verm[0]], verm[0]
    for z in zeilen:
        if z["phase"] == "Entnahme" and rendite is not None:
            w_ = w_ * (1.0 + rendite)
        else:
            w_ = w_ + z["ertrag"] + max(z["fluss"], 0.0)
        ohne.append(w_)
    zeige_ohne = any(aus) and rendite is not None
    n = len(xs)
    schritt = max(1, math.ceil((n - 1) / 5))
    zeige = {0, n - 1} | set(range(0, n, schritt))
    fig = go.Figure()

    def linie(y, name, farbe, breite=2, strich=None, text=False, pos="top", marker=5):
        fig.add_trace(go.Scatter(
            x=xs, y=y, name=name, mode="lines+markers+text" if text else "lines+markers",
            line=dict(color=farbe, width=breite, dash=strich), marker=dict(size=marker, color=farbe),
            text=[_kurz_eur(v).replace("-", "−") if (k in zeige and (k > 0 or pos == "top") and abs(v) > 0.5) else ""
                  for k, v in enumerate(y)] if text else None,
            textposition=[f"{pos} right" if k == 0 else f"{pos} left" if k == n - 1 else f"{pos} center"
                          for k in range(n)],
            textfont=dict(size=11, color=farbe)))

    if zeige_ohne:
        linie(ohne, "Vermögen ohne Entnahme", "#8A9099", 2, "dash", marker=3)
    linie(verm, "Vermögen", "#FFFFFF", 3, text=True, marker=7)
    linie(ertr, "Erträge je Jahr", "#16C784")
    if any(ein):
        linie(ein, "Einzahlung je Jahr", "#A78BFA")
    if any(aus):
        linie(aus, "Entnahme je Jahr", "#EA3943")
        linie(summe_aus, "Entnahmen gesamt", "#FF6B6B", 2, "dot", text=True, pos="bottom")
    if ziel > 0:
        fig.add_hline(y=ziel, line=dict(color="#F5B942", dash="dash", width=1),
                      annotation_text="Ziel", annotation_font_color="#F5B942")
    _layout(fig, 420)
    fig.update_layout(hovermode="x unified", legend=dict(font=dict(size=11)))
    fig.update_xaxes(title="Jahr (0 = heute, Anfangswert)", dtick=max(1, math.ceil((n - 1) / 10)))
    lo = min(summe_aus + ertr + [0.0])
    hi = max(verm + (ohne if zeige_ohne else [])) * 1.12
    lo = lo * 1.35 if lo < 0 else 0.0                          # Platz fuer die Beschriftung unten
    # Ticks selbst setzen, damit auch der Minusbereich beschriftet ist
    stufe = 10 ** math.floor(math.log10(max(hi - lo, 1.0) / 5))
    stufe = next(f * stufe for f in (1, 2, 2.5, 5, 10) if (hi - lo) / (f * stufe) <= 6)
    ticks = [stufe * i for i in range(math.floor(lo / stufe), math.ceil(hi / stufe) + 1)]
    if lo < 0 and not any(t < 0 for t in ticks if t >= lo):
        ticks.append(lo / 1.35)                                # mindestens ein Wert unter null
    fig.update_yaxes(hoverformat=",.0f", zeroline=True, zerolinecolor="#8A9099", zerolinewidth=1,
                     range=[lo, hi], tickvals=ticks, ticktext=[_kurz_eur(t).replace("-", "−") for t in ticks])
    _chart(fig, "pl_growth")
    if zeige_ohne:
        diff = ohne[-1] - verm[-1]
        _kacheln([
            ("Entnommen gesamt", _eur(-summe_aus[-1], False), f"in {n - 1 - sum(1 for z in zeilen if z['phase'] == 'Aufbau')} J. Entnahme"),
            ("Vermögen am Ende", _eur(verm[-1]), "mit Entnahme"),
            ("Ohne Entnahme", _eur(ohne[-1]), "gleiche Rendite"),
            ("Kosten der Entnahme", _eur(diff), "entgangener Zinseszins inkl. Entnahmen"),
        ], klein=True)
    st.caption("Antippen zeigt alle Werte eines Jahres. Vermögen: Jahr 0 = Anfangswert, danach Stand am "
               "Jahresende (= Anfang des nächsten Jahres). Entnahmen zeigen nach unten.")


def _b_growth(m, R):
    rahmen = m["rahmen"]
    proj = R["zus"]["projektion"]
    monate = len(proj["monatswerte"]) - 1
    x = [m_ / 12 for m_ in range(monate + 1)]
    ziel = float(rahmen.get("zielvermoegen") or 0.0)
    aufbau, ent, zeilen, rendite, plan = _gesamtverlauf(m, R)
    e = _entnahme_daten(m)

    _abschnitt("Vermögensverlauf je Jahr" if zeilen else "Projected Growth")
    if zeilen:
        _jahres_chart(zeilen, ziel if monate > 0 else 0.0, rendite)
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=aufbau, name="Aufbau", line=dict(color="#4C9AFF", width=3)))
        _layout(fig, 340)
        fig.update_xaxes(title="Jahre ab heute")
        _chart(fig, "pl_growth")
    _hinweis()

    if zeilen:
        _abschnitt("Jahresübersicht")
        st.caption(("Aufbau: Einzahlung = Sparrate · " if monate > 0 else "")
                   + "Entnahme: " + f"{_de(e['monatlich'])} €/Monat netto"
                   + (f", +{_de(e['dynamik_pa'], 1)} % p.a." if e.get("dynamik_pa") else "")
                   + (f" · Erträge: Kapital wächst mit {_pct(rendite)} p.a. (monatlich verzinst), "
                      "die Entnahme wird jeden Monat abgezogen" if rendite is not None else ""))
        steuer = any(z["steuer"] for z in zeilen)
        kopf = ["Jahr", "Phase", "Anfang", "Ein-/Auszahlung", "Erträge"] + (["Steuer"] if steuer else []) + ["Ende"]
        _eu = lambda v: _eur(round(v), False)
        _tabelle(kopf, [[str(z["jahr"]), z["phase"], _eu(z["anfang"]),
                         ("+" if z["fluss"] > 0 else "") + _eu(z["fluss"]) if z["fluss"] else "–",
                         _eu(z["ertrag"])] + ([_eu(z["steuer"])] if steuer else []) + [_eu(z["ende"])]
                        for z in zeilen])
        if plan is not None and not plan["reicht_dauerhaft"] and plan["dauer_monate"] < int(e["dauer_jahre"]) * 12:
            st.caption(f"⚠ Das Kapital ist nach {_dauer_text(plan)} Entnahme aufgebraucht.")
    if monate == 0:
        st.caption("Keine Aufbauphase (0 Jahre) – Details zur Entnahme unter „Entnahme“.")
        return

    _abschnitt("Wertentwicklung je Baustein")
    fig2 = go.Figure()
    namen = {a["id"]: a["name"] for a in m["assets"]}
    for n, (aid, reihe) in enumerate(proj["asset_verlauf"].items()):
        if reihe[0] <= 0:
            continue
        fig2.add_trace(go.Scatter(x=x, y=reihe, name=namen[aid], stackgroup="a", mode="none",
                                  fillcolor=FARBEN[n % len(FARBEN)]))
    _layout(fig2, 360)
    _chart(fig2, "pl_stack")

    _abschnitt("Rebalancing-Vergleich")
    varianten = [("keins", "Buy & Hold"), ("jaehrlich", "Jährlich")]
    if R["reb"]["art"] not in ("keins", "jaehrlich"):
        varianten.append((R["reb"]["art"], D.REBALANCING_ARTEN[R["reb"]["art"]]))
    fig3 = go.Figure()
    zeilen = []
    for n, (art, titel) in enumerate(varianten):
        reb = dict(R["reb"], art=art)
        p = E.projektion(m, R["r"], rebalancing=reb)
        ps = E.projektion(m, R["r"], rebalancing=reb, stress=m["stress"])
        fig3.add_trace(go.Scatter(x=x, y=ps["monatswerte"], name=f"{titel} (Stresspfad)",
                                  line=dict(color=FARBEN[n], width=2)))
        zeilen.append([_esc(titel), _eur(p["endwert"]), _eur(ps["endwert"]), _pct(ps["max_verlust_pfad"], anteil=False),
                       str(ps["rebalancings"])])
    _layout(fig3, 320)
    _chart(fig3, "pl_rebal")
    _tabelle(["Variante", "Endwert glatt", "Endwert Stresspfad", "Max. Verlust", "Rebal."], zeilen)
    st.caption("Glatte Rechnung: konstante Renditen – Rebalancing verschiebt dort nur Gewicht von stärkeren zu "
               "schwächeren Bausteinen. Stresspfad: zusätzlicher Markteinbruch (Einstellungen unter "
               "„⚠️ Risiko → Stress & Reserve“), in dem Rebalancing antizyklisch wirkt.")


# --- 3 Zielerreichung -------------------------------------------------------
def _b_ziel(m, R):
    z = R["zus"]
    proj = z["projektion"]
    namen = {a["id"]: a["name"] for a in m["assets"]}
    _abschnitt("Zielerreichung")
    _kacheln([
        ("Benötigt p.a.", _pct(z["erforderliche_cagr"]) if z["erforderliche_cagr"] is not None or
         not m["rahmen"].get("zielvermoegen") else "nicht erreichbar", None),
        ("Modell p.a.", _pct(z["modell_cagr"]), None),
        ("Lücke p.a.", _pct(z["erforderliche_cagr"] - (z["modell_cagr"] or 0), vorzeichen=True)
         if z["erforderliche_cagr"] is not None else "–", "Prozentpunkte"),
        ("Endwert / Ziel", _pct(z["endwert"] / m["rahmen"]["zielvermoegen"], 0) if m["rahmen"]["zielvermoegen"] else "–",
         None),
    ], klein=True)
    beitr = sorted(proj["beitraege"].items(), key=lambda x: -x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in beitr], y=[namen[i] for i, _ in beitr], orientation="h",
                           marker_color=["#16C784" if v >= 0 else "#EA3943" for _, v in beitr],
                           hovertemplate="%{y}: %{x:,.0f} €<extra></extra>"))
    _layout(fig, 60 + 30 * len(beitr), legende=False)
    fig.update_yaxes(autorange="reversed", side="left", tickformat=None)
    fig.update_xaxes(tickformat=",.0f")
    fig.update_layout(title=dict(text="Gewinnbeitrag je Baustein (€)", font=dict(size=13)), margin=dict(t=40))
    _chart(fig, "pl_beitrag")

    st.caption("Gewichte auf ein Ziel ausrichten: Bereich „⚖️ Gewichtung“ → „🎯 Auf Ziel rechnen“.")


# --- 4 Fundamental Basket ---------------------------------------------------
def _b_korb(m, R, fund, fund_stand, je_score, korb_score, hist_korb):
    korb_asset = _asset(m, "korb")
    _abschnitt("Fundamental Growth Basket")
    if korb_asset is None:
        st.info("Kein Korb-Baustein im Modell.")
        return
    st.markdown('<span class="pl-badge pl-warn">⚠ Historical Winner Bias</span>'
                '<span class="pl-badge pl-info">Szenarioannahme</span>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    anteil = c1.slider("Anteil des Korbs am Gesamtportfolio (%)", 0.0, 50.0,
                       float(korb_asset.get("targetWeight") or 0.0), step=0.5, key=_k("korb_anteil"))
    if abs(anteil - float(korb_asset.get("targetWeight") or 0)) > 1e-9:
        korb_asset["targetWeight"], korb_asset["enabled"] = anteil, anteil > 0
    methoden = list(E.KORB_METHODEN)
    m["korb_methode"] = c2.selectbox("Gewichtung im Korb", methoden, index=methoden.index(m.get("korb_methode", "manual")),
                                     format_func=E.KORB_METHODEN.get, key=_k("korb_meth"))
    if m["korb_methode"] != "manual":
        neu = E.korb_gewichte(m["korb"], m["korb_methode"], {i: s["gesamt"] for i, s in je_score.items()}, fund)
        for x in m["korb"]:
            x["gewicht"] = neu.get(x["id"], x["gewicht"])

    # Renditeannahmen des Korbs
    c3, c4, c5 = st.columns(3)
    for spalte, sz, titel in ((c3, "bear", "Bear % p.a."), (c4, "base", "Base % p.a."), (c5, "bull", "Bull % p.a.")):
        alt = E.annahme(m, "korb", sz)
        wert = spalte.number_input(titel, -50.0, 100.0, float(alt["value"] * 100) if alt else 0.0, step=1.0,
                                   key=_k(f"korb_{sz}"))
        if alt is None or abs(alt["value"] - wert / 100) > 1e-9:
            E.setze_annahme(m, "korb", sz, wert / 100, notiz="Szenarioannahme")
            if sz == "base":
                E.setze_annahme(m, "korb", "manualScenario", wert / 100,
                                notiz="Default-Modellrendite des Aktienkorbs – Szenarioannahme.")

    manuell = m.setdefault("manuell", {})
    df = pd.DataFrame([{
        "Aktie": x["name"], "Gewicht %": float(x["gewicht"]),
        "Score": je_score[x["id"]]["gesamt"],
        "Moat 0–10": (manuell.get(x["id"]) or {}).get("moat"),
        "Risiko 0–10": (manuell.get(x["id"]) or {}).get("risiko"),
        "5J p.a. %": None if (hist_korb.get(x["id"]) or {}).get("historical5Y") is None
        else round(hist_korb[x["id"]]["historical5Y"] * 100, 1),
        "Sektor": x["sektor"],
    } for x in m["korb"]])
    ed = _editor_formular(
        df, key=_k("korb_ed"), hide_index=True, width="stretch", height=_hoehe(len(df)),
        disabled=["Aktie", "Score", "5J p.a. %", "Sektor"] + ([] if m["korb_methode"] == "manual" else ["Gewicht %"]),
        column_config={
            "Gewicht %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.5, format="%.1f"),
            "Score": st.column_config.NumberColumn(format="%.0f", help="Fundamental Score 0–100"),
            "Moat 0–10": st.column_config.NumberColumn(min_value=0, max_value=10, step=1,
                                                       help="Manuell: Marktstellung, Wechselkosten, Netzwerk, Technologie"),
            "Risiko 0–10": st.column_config.NumberColumn(min_value=0, max_value=10, step=1,
                                                         help="Manuell: 0 = hohes Risiko … 10 = geringes"),
            "5J p.a. %": st.column_config.NumberColumn(format="%.1f", help="Historisch (Winner Bias!)"),
        })
    geaendert = False
    for i, x in enumerate(m["korb"]):
        z = ed.iloc[i]
        if m["korb_methode"] == "manual" and not pd.isna(z["Gewicht %"]) and abs(float(z["Gewicht %"]) - x["gewicht"]) > 1e-9:
            x["gewicht"] = float(z["Gewicht %"])
            geaendert = True
        for feld, spalte in (("moat", "Moat 0–10"), ("risiko", "Risiko 0–10")):
            neu = None if pd.isna(z[spalte]) else float(z[spalte])
            if (manuell.get(x["id"]) or {}).get(feld) != neu:
                manuell.setdefault(x["id"], {})[feld] = neu
                geaendert = True
    if geaendert:
        st.rerun()
    summe = sum(float(x["gewicht"]) for x in m["korb"])
    if abs(summe - 100) > 0.05:
        st.warning(f"Korb = {_de(summe, 1)} % – für die Rechnung wird auf 100 % skaliert.")

    _kacheln([
        ("Korb-Score", _de(korb_score, 0) if korb_score is not None else "–", "gewichtet, 0–100"),
        ("Annahme Base", _pct((E.annahme(m, "korb", "base") or {}).get("value")), "Szenarioannahme"),
        ("Fundamental-Modell", _pct((R["info"].get("korb") or {}).get("brutto")) if m["rahmen"]["methode"] ==
         "fundamentalModel" else _pct(E.korb_fundamental_rendite(m["korb"], fund)[0]),
         "FCF-Rendite + Wachstum"),
        ("Halbleiteranteil", _pct(E.korb_anteile(m["korb"], D.KORB_HALBLEITER)), "im Korb"),
    ], klein=True)

    ids = [x["id"] for x in m["korb"]]
    sc = [je_score[i]["gesamt"] for i in ids]
    fig = go.Figure(go.Bar(
        x=[x["name"] for x in m["korb"]], y=[x["gewicht"] for x in m["korb"]],
        marker_color=["#8A9099" if s is None else "#16C784" if s >= 70 else "#F5B942" if s >= 50 else "#EA3943"
                      for s in sc],
        text=["–" if s is None else f"{s:.0f}" for s in sc], textposition="outside",
        hovertemplate="%{x}: %{y:.1f} % · Score %{text}<extra></extra>"))
    _layout(fig, 320, legende=False, eur=False)
    fig.update_layout(title=dict(text="Gewicht im Korb (%) · Zahl = Fundamental Score", font=dict(size=13)),
                      margin=dict(t=40))
    _chart(fig, "pl_korb")

    with st.expander("Fundamental Score: Kategorien & Gewichte", expanded=False):
        regeln = m["bewertungsregeln"]
        spalten = st.columns(3)
        for n, (key, r) in enumerate(regeln.items()):
            r["gewicht"] = float(spalten[n % 3].number_input(r["titel"], 0.0, 100.0, float(r["gewicht"]), step=5.0,
                                                             key=_k(f"sw_{key}")))
        st.caption(f"Summe {_de(sum(r['gewicht'] for r in regeln.values()), 0)} – wird auf 100 normiert. "
                   "Jede Kennzahl wird linear zwischen einer schwachen und einer starken Schwelle bewertet; "
                   "Kategorien ohne Daten fallen heraus, unter 50 % Abdeckung kein Gesamtwert.")
        kopf = ["Aktie"] + [r["titel"] for r in regeln.values()] + ["Gesamt"]
        zeilen = []
        for x in m["korb"]:
            s = je_score[x["id"]]
            zeilen.append([_esc(x["name"])] + [_de(s["kategorien"].get(k), 0) for k in regeln] + [
                f'<b>{_de(s["gesamt"], 0)}</b>'])
        _tabelle(kopf, zeilen)
    st.caption(f"Kennzahlen: Qualitäts-Agent (Yahoo-Finance-Jahresabschlüsse), Stand "
               f"{_datum(fund_stand)} · {len(fund)} von {len(m['korb'])} Aktien mit Daten. Der Korb wurde aus "
               "Unternehmen gebildet, die zuletzt stark gelaufen sind – deren Vergangenheitsrendite ist keine "
               "faire Zukunftserwartung.")


def _datum(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except Exception:
        return iso or "–"


# --- 5 Wikifolio Analyse ----------------------------------------------------
def _b_wiki(m, R, hist_assets):
    _abschnitt("Wikifolio Analyse")
    wikis = [a for a in m["assets"] if a["category"] == "wikifolio"]
    if not wikis:
        st.info("Keine Wikifolios im Modell.")
        return
    zeilen = []
    for a in wikis:
        h = hist_assets.get(a["id"]) or {}
        info = R["info"].get(a["id"]) or {}
        herkunft = info.get("herkunft") or {}
        quelle_txt = herkunft.get("source") if herkunft.get("sourceType") in ("historisch", "hochgerechnet", "kategorie_standard") \
            else "Annahme"
        conf = R["conf"].get(a["id"]) or E.confidence_score(h.get("jahre"), "wikifolio")
        zeilen.append([
            f'<span class="pt-name">{_esc(a["name"])}</span><span class="pt-sub">'
            f'{_esc(h.get("wkn") or a.get("ticker") or "WKN offen")} · {_esc(a.get("emittent") or "–")}</span>',
            f'<b>{_pct(info.get("brutto"), 1)}</b><span class="pt-sub">{_esc(quelle_txt)}</span>',
            f'{_de(conf)}/100',
            _de(h.get("jahre"), 1) + " J." if h.get("jahre") else "–",
            _pct(h.get("gesamt_cagr")) if h.get("gesamt_cagr") is not None else
            (_pct(h.get("seit_start")) + " ges." if h.get("seit_start") is not None else "–"),
            _pct(h.get("historical5Y")),
            _pct(h.get("vola")),
            _pct(h.get("maxdd"), 0, anteil=False),
            _pct(a.get("performanceFee"), 0),
            _pct(a.get("expenseRatio"), 2),
            _de(a.get("leverage") or 1, 1) + "×",
        ])
    _tabelle(["Wikifolio", "Genutzt p.a.", "Confidence", "Historie", "Ø seit Start", "5 J. p.a.", "Vola",
              "Max. DD", "Perf.-Fee", "Kosten", "Hebel"], zeilen)
    for a in wikis:
        h = hist_assets.get(a["id"]) or {}
        if h.get("fehler"):
            st.caption(f"{a['name']}: {h['fehler']}")
    st.caption("„Genutzt p.a.“ = tatsächliche Rendite laut Kurshistorie (5 J. p.a., sonst 3 J., sonst seit Start, "
               "sonst 1 J.; bei weniger als 1 Jahr Historie die Ø Monatsrendite seit Start aufs Jahr hochgerechnet – "
               "„hochgerechnet aus N Mon. (Ø Monatsrendite)“, wenig belastbar, bis 1 Jahr Historie vorliegt; "
               "unter 1 Monat der Kategorie-Standard, Richtung 8 % gedämpft). "
               "Die eigene Annahme gilt nur, wenn keine Kurshistorie vorliegt oder im Portfolio "
               "Builder „Ist“ abgewählt ist. Vergangene Renditen sind keine Zukunftserwartung. Confidence misst nur, wie lang und belastbar die investierbare Historie ist – z. B. "
               "„Expected Return 50 % / Data Confidence 22/100“. Performance Fee und Kosten nur, soweit unter "
               "„🗂️ Daten → Annahmen & Quellen“ eingetragen.")
    fig = go.Figure()
    for n, a in enumerate(wikis):
        mon = (hist_assets.get(a["id"]) or {}).get("monat") or []
        if len(mon) < 2:
            continue
        basis = mon[0][1]
        fig.add_trace(go.Scatter(x=[d for d, _ in mon], y=[v / basis * 100 for _, v in mon], name=a["name"],
                                 line=dict(color=FARBEN[n % len(FARBEN)], width=2)))
    if fig.data:
        _layout(fig, 320, eur=False)
        fig.update_layout(title=dict(text="Investierbare Historie (Start = 100)", font=dict(size=13)), margin=dict(t=46))
        _chart(fig, "pl_wiki_hist")
    anteil = sum(w for i, w in E.gewichte(m).items() if _asset(m, i)["category"] == "wikifolio")
    st.markdown(f'<div class="pl-zeile">Wikifolio-Anteil am Portfolio: <b>{_pct(anteil)}</b> · '
                f'Anteil am Modell-Endwert: <b>{_pct(sum(v for i, v in R["zus"]["projektion"]["endwerte_asset"].items() if _asset(m, i)["category"] == "wikifolio") / (R["zus"]["endwert"] or 1))}</b></div>',
                unsafe_allow_html=True)


# --- 6 Szenariovergleich ----------------------------------------------------
def _b_szenarien(m, R, historie, h):
    _abschnitt("Szenariovergleich")
    s = E.szenario_vergleich(m, historie, rebalancing=R["reb"])
    rahmen = m["rahmen"]
    ein = rahmen["startkapital"] + (rahmen.get("sparrate_monat") or 0) * 12 * rahmen["horizont_jahre"]
    zeilen = []
    for sz in ("bear", "base", "bull", "custom"):
        v = s[sz]
        zeilen.append([sz.capitalize(), f'<b>{_eur(v["endwert"])}</b>',
                       _pct(v["cagr"]) if v["cagr"] is not None else "–",
                       _pct(v["max_verlust_stress"], 0, anteil=False), _de(ein) + " €",
                       '<span class="pl-gut">ja</span>' if v["ziel_erreicht"] else '<span class="pl-schlecht">nein</span>',
                       ("+" if v["abstand"] >= 0 else "−") + _de(abs(E.runden_ungefaehr(v["abstand"]) or 0)) + " €"])
    _tabelle(["Szenario", "Endwert", "CAGR", "Max. Verlust*", "Einzahlungen", "Ziel", "Abstand"], zeilen)
    st.caption("* im Stresspfad (Markteinbruch unter „⚠️ Risiko → Stress & Reserve“). Custom = eigene Custom-Annahmen, "
               "sonst Base. " + m["szenario_regel"]["text"])
    fig = go.Figure(go.Bar(x=["Bear", "Base", "Bull", "Custom"], y=[s[x]["endwert"] for x in ("bear", "base", "bull", "custom")],
                           marker_color=["#EA3943", "#4C9AFF", "#16C784", "#A78BFA"],
                           hovertemplate="%{x}: %{y:,.0f} €<extra></extra>"))
    fig.add_hline(y=rahmen["zielvermoegen"], line=dict(color="#F5B942", dash="dash"), annotation_text="Ziel",
                  annotation_font_color="#F5B942")
    _layout(fig, 320, legende=False)
    _chart(fig, "pl_szen")



def _b_modelle(m, R, historie, h):
    _abschnitt("Gespeicherte Modelle")
    st.caption(f"Aktives Modell: „{st.session_state.get('planer_name') or 'Aktuelles Modell'}“ – Änderungen werden "
               "automatisch darin gespeichert. Für eine Variante erst unter neuem Namen speichern, dann ändern.")
    daten, lesbar = _lade_gespeichert(h, mit_status=True)
    if not lesbar:
        st.error("Gespeicherte Modelle gerade nicht lesbar (GitHub-Speicher nicht erreichbar) – bitte später neu laden.")
    vorhanden = list(daten["szenarien"])
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    vorschlag = D.SZENARIO_NAMEN + [n for n in vorhanden if n not in D.SZENARIO_NAMEN]
    aktuell = st.session_state.get("planer_name") or "Aktuelles Modell"
    name = c1.selectbox("Name", vorschlag + ["Eigener Name …"],
                        index=vorschlag.index(aktuell) if aktuell in vorschlag else 0, key=_k("sz_name"))
    if name == "Eigener Name …":
        name = c1.text_input("Eigener Name", key=_k("sz_eigen")).strip()
    if c2.button("💾 Speichern", key=_k("sz_save"), width="stretch", disabled=not name):
        eintrag = {"modell": copy.deepcopy(m), "gespeichert": datetime.datetime.now().isoformat(timespec="minutes")}

        def _speichern(d):
            if not isinstance(d.get("szenarien"), dict):
                d["szenarien"] = {}
            d["szenarien"][name] = eintrag
            d["aktiv"] = name
            return d
        if _aendern_speichern(h, _pfad(h, PFAD_SZENARIEN), _speichern, f"planer: szenario {name} [skip ci]"):
            st.session_state["planer_name"] = name
            st.session_state["planer_hash"] = _hash(m)
            if h.get("chronik"):
                try:
                    rr = m["rahmen"]
                    h["chronik"]("planer", f"💾 Planung gespeichert: {name}",
                                 f"Start {_de(rr['startkapital'])} € · {rr['horizont_jahre']} J. Aufbau · Ziel "
                                 f"{_de(rr['zielvermoegen'])} € · {len(E.aktive_assets(m))} Bausteine")
                except Exception:
                    pass
            st.success(f"„{name}“ gespeichert.")
        else:
            st.error("Speichern nicht möglich (GitHub-Speicher nicht verfügbar).")
    if vorhanden:
        c3, c4, c5 = st.columns([2, 1, 1], vertical_alignment="bottom")
        laden = c3.selectbox("Gespeichertes Modell", vorhanden, key=_k("sz_laden"))
        if c4.button("Laden", key=_k("sz_load"), width="stretch"):
            st.session_state["planer_modell"] = _migriere(daten["szenarien"][laden]["modell"])
            st.session_state["planer_name"] = laden
            _basis_neu()
            st.session_state.pop("planer_opt", None)
            _neu_zeichnen()
            st.rerun()
        if c5.button("Löschen", key=_k("sz_del"), width="stretch"):
            def _loeschen(d):
                sz = d.get("szenarien") if isinstance(d.get("szenarien"), dict) else {}
                if laden not in sz:
                    return None
                sz.pop(laden, None)
                d["szenarien"] = sz
                if d.get("aktiv") == laden:
                    d["aktiv"] = None
                return d
            if _aendern_speichern(h, _pfad(h, PFAD_SZENARIEN), _loeschen,
                                  f"planer: szenario {laden} geloescht [skip ci]"):
                if st.session_state.get("planer_name") == laden:
                    st.session_state["planer_name"] = None      # naechste Aenderung -> "Aktuelles Modell"
                    st.session_state["planer_hash"] = None
                _neu_zeichnen()
                st.rerun()
            else:
                st.error("Löschen nicht möglich (GitHub-Speicher nicht erreichbar).")
        zeilen = []
        for n, e in daten["szenarien"].items():
            try:
                mm = _migriere(e["modell"])
                r = E.rendite_map(E.alle_renditen(mm, historie))
                zz = E.zusammenfassung(mm, r, rebalancing=mm["rebalancing"])
                rk = E.risiko_kennzahlen(mm, r, E.confidence_fuer(mm, historie), historie)
                zeilen.append([_esc(n), f'<b>{_eur(zz["endwert"])}</b>', _pct(zz["modell_cagr"]),
                               _pct(rk["wikifolio_anteil"], 0, anteil=False), _pct(rk["hebel_anteil"], 0, anteil=False),
                               _pct(rk["max_gewicht"], 0, anteil=False), _de(rk["confidence_gewichtet"]),
                               _datum(e.get("gespeichert"))])
            except Exception as ex:
                zeilen.append([_esc(n), f"Fehler: {_esc(ex)}"] + ["–"] * 6)
        _tabelle(["Modell", "Endwert", "p.a.", "Wikifolios", "Hebel", "Max. Gew.", "Conf.", "Gespeichert"], zeilen)
        st.caption("Alle gespeicherten Modelle mit den heutigen Kursdaten neu gerechnet.")


# --- 7 Risiko & Konzentration -----------------------------------------------
def _b_risiko(m, R, historie):
    rk = E.risiko_kennzahlen(m, R["r"], R["conf"], historie)
    if not rk:
        st.info("Keine aktiven Bausteine.")
        return
    _abschnitt("Risiko & Konzentration")
    _kacheln([
        ("Größte Position", _pct(rk["max_gewicht"], 0, anteil=False), _esc(rk["max_gewicht_name"])),
        ("Effektive Positionen", _de(rk["effektive_positionen"], 1), "1 / Summe Gewicht²"),
        ("Unabhängige Treiber", _de(rk["unabhaengige_treiber"], 1), "Welt, US-Tech, je Wikifolio, Korb"),
        ("Cash-Quote", _pct(rk["cash_quote"], 0, anteil=False), "Nachkaufreserve"),
        ("Wikifolio-Anteil", _pct(rk["wikifolio_anteil"], 0, anteil=False), None),
        ("Hebel-Anteil", _pct(rk["hebel_anteil"], 0, anteil=False),
         f'Exposure {_pct(rk["hebel_exposure"], 0, anteil=False)}'),
        ("Halbleiter (bekannt)", _pct(rk["semi_bekannt"], 0, anteil=False),
         _esc("+ unbekannt in: " + ", ".join(rk["semi_unbekannt"])) if rk["semi_unbekannt"] else None),
        ("Max. Drawdown (Modell)", _pct(rk["drawdown_gewichtet"], 0, anteil=False), "alle gleichzeitig"),
    ], klein=True)
    _kacheln([
        ("Ø Rendite (gewichtet)", _pct(rk["rendite_gewichtet"]), "aktive Quelle"),
        ("Ø Confidence", _de(rk["confidence_gewichtet"]) + "/100", "Datenbasis"),
        ("Confidence-adj. Rendite", _pct(rk["confidence_adjusted_return"]),
         "interne Kennzahl: Rendite × Conf./100"),
        ("Tech (bekannt)", _pct(rk["tech_bekannt"], 0, anteil=False),
         "Indizes ohne Holdings nicht gezählt" if rk["tech_unbekannt"] else None),
    ], klein=True)

    w = E.gewichte(m)
    gruppen = {}
    for i, g in w.items():
        a = _asset(m, i)
        if a["category"] == "cash":
            titel = "Reserve"
        else:
            titel = E.TREIBER_GRUPPEN.get(a["category"], a["name"])
        gruppen[titel] = gruppen.get(titel, 0.0) + g * 100
    gr = sorted(gruppen.items(), key=lambda x: -x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in gr], y=[k for k, _ in gr], orientation="h", marker_color="#4C9AFF",
                           hovertemplate="%{y}: %{x:.1f} %<extra></extra>"))
    _layout(fig, 60 + 32 * len(gr), legende=False, eur=False)
    fig.update_yaxes(autorange="reversed", side="left")
    fig.update_layout(title=dict(text="Anteil je Renditetreiber (%)", font=dict(size=13)), margin=dict(t=40))
    _chart(fig, "pl_treiber")

    _abschnitt("Effektive Exposure")
    x = E.effektive_exposure(m)
    top = list(x["firmen"].items())[:12]
    if top:
        _tabelle(["Unternehmen", "Direkt", "Über ETFs", "Effektiv"],
                 [[_esc(n), _pct(v["direkt"], 2, anteil=False), _pct(v["indirekt"], 2, anteil=False) if v["indirekt"] else "–",
                   f'<b>{_pct(v["effektiv"], 2, anteil=False)}</b>'] for n, v in top])
    c1, c2 = st.columns(2)
    with c1:
        _tabelle(["Sektor", "Anteil"], [[_esc(k), _pct(v, 1, anteil=False)] for k, v in x["sektoren"].items()])
    with c2:
        _tabelle(["Region", "Anteil"], [[_esc(k), _pct(v, 1, anteil=False)] for k, v in x["regionen"].items()])
    st.caption("ETF-Bestände (Holdings) sind noch nicht hinterlegt – die indirekte Exposure über Indizes "
               "(z. B. Nvidia im Nasdaq 100) fehlt daher. Die Struktur ist vorbereitet "
               "(Modellfeld „holdings“: {ETF: {Firma: Anteil %}}).")


# --- 8 Nachkaufreserve ------------------------------------------------------
def _b_reserve(m, R):
    _abschnitt("Nachkaufreserve")
    nk, stress = m["nachkauf"], m["stress"]
    res = _asset(m, "reserve")
    if res is None or not res.get("enabled"):
        st.info("Die Nachkaufreserve ist deaktiviert (🧩 Portfolio → Bausteine).")
    c1, c2 = st.columns(2)
    if res is not None:
        neu = c1.number_input("Reserve (% des Portfolios)", 0.0, 60.0, float(res.get("targetWeight") or 0), step=1.0,
                              key=_k("res_w"))
        if abs(neu - float(res.get("targetWeight") or 0)) > 1e-9:
            res["targetWeight"], res["enabled"] = neu, neu > 0
    ziele = list(D.NACHKAUF_ZIELE)
    nk["ziel"] = c2.selectbox("Ziel der Tranchen", ziele, index=ziele.index(nk.get("ziel", "proportional")),
                              format_func=D.NACHKAUF_ZIELE.get, key=_k("nk_ziel"))
    if nk["ziel"] == "asset":
        auswahl = [a["id"] for a in m["assets"] if a.get("enabled") and a["category"] != "cash"]
        if auswahl:
            nk["ziel_asset"] = st.selectbox("Baustein", auswahl, format_func=lambda i: _asset(m, i)["name"],
                                            index=auswahl.index(nk["ziel_asset"]) if nk.get("ziel_asset") in auswahl else 0,
                                            key=_k("nk_asset"))
    c3, c4 = st.columns(2)
    nk["min_score_aktiv"] = c3.toggle("Einzelwerte/Korb nur mit Mindest-Score", value=bool(nk.get("min_score_aktiv")),
                                      key=_k("nk_ms"))
    nk["min_score"] = float(c4.number_input("Mindest-Score", 0.0, 100.0, float(nk.get("min_score", 70)), step=5.0,
                                            key=_k("nk_score"), disabled=not nk["min_score_aktiv"]))
    df = pd.DataFrame([{"Tranche": n + 1, "Drawdown %": t["drawdown"], "Anteil der Reserve %": round(t["anteil"] * 100, 1)}
                       for n, t in enumerate(nk["tranchen"])])
    ed = st.data_editor(df, key=_k("tranchen"), hide_index=True, height=_hoehe(len(df)), width="stretch", disabled=["Tranche"],
                        column_config={"Drawdown %": st.column_config.NumberColumn(min_value=-95.0, max_value=0.0, step=5.0),
                                       "Anteil der Reserve %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0,
                                                                                             step=5.0)})
    for n, t in enumerate(nk["tranchen"]):
        d, a = ed.iloc[n]["Drawdown %"], ed.iloc[n]["Anteil der Reserve %"]
        if not pd.isna(d):
            t["drawdown"] = float(d)
        if not pd.isna(a) and abs(float(a) - round(t["anteil"] * 100, 1)) > 1e-9:
            t["anteil"] = float(a) / 100
    st.caption("Regelbasiert: Eine Tranche wird nur bei einem Markt-Drawdown ab der Schwelle eingesetzt. Ein "
               "Kursrückgang allein ist kein Grund – Einzelwerte bzw. der Korb kommen nur bei ausreichendem "
               "Fundamental Score in Frage.")

    with st.expander("Stress-Szenario", expanded=False):
        s1, s2, s3 = st.columns(3)
        stress["einbruch"] = float(s1.number_input("Einbruch (%)", 0.0, 90.0, float(stress["einbruch"]), step=5.0,
                                                   key=_k("st_e")))
        stress["start"] = int(s2.number_input("Beginn (Monat)", 1, 480, int(stress["start"]), key=_k("st_s")))
        stress["dauer"] = int(s3.number_input("Dauer (Monate)", 1, 60, int(stress["dauer"]), key=_k("st_d")))
        s4, s5 = st.columns(2)
        stress["erholung"] = int(s4.number_input("Erholung (Monate)", 1, 120, int(stress["erholung"]), key=_k("st_r")))
        stress["wikifolio_beta"] = float(s5.number_input("Wikifolio-Beta", 0.0, 3.0, float(stress["wikifolio_beta"]),
                                                         step=0.1, key=_k("st_b")))
        st.caption("Modellhafter Markteinbruch zusätzlich zum Trend der Annahmen. Hebelprodukte fallen mit ihrem "
                   "Hebel, Cash gar nicht.")

    ohne = E.projektion(m, R["r"], rebalancing=R["reb"], stress=stress)
    mit = E.projektion(m, R["r"], rebalancing=R["reb"], stress=stress, nachkauf=nk, scores=R["scores"],
                       confidences=R["conf"])
    x = [i / 12 for i in range(len(mit["monatswerte"]))]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=ohne["monatswerte"], name="Reserve bleibt Cash", line=dict(color="#8A9099", width=2)))
    fig.add_trace(go.Scatter(x=x, y=mit["monatswerte"], name="Mit Tranchen", line=dict(color="#16C784", width=3)))
    for n in mit["nachkaeufe"]:
        fig.add_trace(go.Scatter(x=[n["monat"] / 12], y=[mit["monatswerte"][n["monat"]]], mode="markers",
                                 marker=dict(color="#F5B942", size=11, symbol="triangle-up"), showlegend=False,
                                 hovertemplate=f"Tranche bei {_de(n['drawdown'], 0)} %: {_de(n['betrag'])} €<extra></extra>"))
    _layout(fig, 340)
    fig.update_xaxes(title="Jahre")
    _chart(fig, "pl_reserve")
    _kacheln([
        ("Endwert ohne Einsatz", _eur(ohne["endwert"]), "Stresspfad"),
        ("Endwert mit Tranchen", _eur(mit["endwert"]), "Stresspfad"),
        ("Tranchen ausgelöst", str(len(mit["nachkaeufe"])), f'von {len(nk["tranchen"])}'),
        ("Max. Verlust", _pct(mit["max_verlust_pfad"], 0, anteil=False), "im Stresspfad"),
    ], klein=True)
    if mit["nachkaeufe"]:
        namen = {a["id"]: a["name"] for a in m["assets"]}
        _tabelle(["Monat", "Markt-DD", "Betrag", "Verteilung"],
                 [[str(n["monat"]), _pct(n["drawdown"], 0, anteil=False), _de(n["betrag"]) + " €",
                   _verteilung(n["ziele"], namen)]
                  for n in mit["nachkaeufe"]], links=(3,))
    elif R["scores"].get("korb") is None and nk.get("min_score_aktiv") and nk.get("ziel") == "bester_score":
        st.caption("Kein Fundamental Score verfügbar – Tranchen gehen nicht in Einzelwerte.")
    _hinweis()


def _verteilung(ziele, namen, max_n=3):
    teile = sorted(((b, i) for i, b in ziele.items() if b >= 1), reverse=True)
    txt = ", ".join(f"{namen[i]} {_de(b)} €" for b, i in teile[:max_n])
    if len(teile) > max_n:
        txt += f" + {len(teile) - max_n} weitere"
    return _esc(txt)


# --- 9 Sensitivitaet --------------------------------------------------------
def _b_sensitiv(m, R):
    _abschnitt("Sensitivität (Tornado)")
    delta = st.select_slider("Abweichung je Annahme", options=[5, 10, 15, 20, 30], value=10,
                             format_func=lambda v: f"± {v} Pp.", key="pl_tornado_delta")
    basis, zeilen = E.tornado(m, R["r"], delta / 100.0, rebalancing=R["reb"])
    namen = {a["id"]: a["name"] for a in m["assets"]}
    zeilen = [z for z in zeilen if z["spanne"] > 1][:10]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=[namen[z["id"]] for z in zeilen], x=[z["tief"] - basis for z in zeilen], base=basis,
                         orientation="h", name=f"−{delta} Pp.", marker_color="#EA3943",
                         hovertemplate="%{y}: %{x:,.0f} €<extra></extra>"))
    fig.add_trace(go.Bar(y=[namen[z["id"]] for z in zeilen], x=[z["hoch"] - basis for z in zeilen], base=basis,
                         orientation="h", name=f"+{delta} Pp.", marker_color="#16C784",
                         hovertemplate="%{y}: %{x:,.0f} €<extra></extra>"))
    fig.add_vline(x=basis, line=dict(color="#FFFFFF", width=1))
    _layout(fig, 80 + 34 * len(zeilen))
    fig.update_layout(barmode="overlay", hovermode="closest")
    fig.update_yaxes(autorange="reversed", side="left", tickformat=None)
    fig.update_xaxes(tickformat=",.0f")
    _chart(fig, "pl_tornado")
    st.caption(f"Endwert, wenn EINE Annahme um ± {delta} Prozentpunkte abweicht (Basis {_eur(basis)}). "
               "Oben stehen die Annahmen, von denen das Ergebnis am stärksten abhängt.")

    wiki_ids = [a["id"] for a in m["assets"] if a["category"] == "wikifolio" and a.get("enabled")]
    if wiki_ids:
        _abschnitt("Wikifolios gemeinsam")
        stufen = [0.50, 0.40, 0.30, 0.20, 0.10, 0.0]
        erg = E.gruppen_sensitivitaet(m, R["r"], wiki_ids, stufen, rebalancing=R["reb"])
        fig2 = go.Figure(go.Bar(x=[_pct(s, 0) for s, _ in erg], y=[v for _, v in erg],
                                marker_color=["#16C784" if v >= m["rahmen"]["zielvermoegen"] else "#4C9AFF" for _, v in erg],
                                hovertemplate="Wikifolios %{x} p.a.: %{y:,.0f} €<extra></extra>"))
        fig2.add_hline(y=m["rahmen"]["zielvermoegen"], line=dict(color="#F5B942", dash="dash"))
        _layout(fig2, 300, legende=False)
        fig2.update_xaxes(title="Rendite aller Wikifolios p.a.")
        _chart(fig2, "pl_wiki_sens")
        _tabelle(["Wikifolios p.a.", "Endwert", "Ziel"],
                 [[_pct(s, 0), _eur(v), '<span class="pl-gut">ja</span>' if v >= m["rahmen"]["zielvermoegen"]
                   else '<span class="pl-schlecht">nein</span>'] for s, v in erg])
    _hinweis()


# --- 10 Annahmen & Datenqualitaet -------------------------------------------
def _b_annahmen(m, R, historie, hist_assets):
    _abschnitt("Annahmen (Assumption Layer)")
    quellen = ["manualScenario", "bear", "base", "bull", "custom"]
    titel = {"manualScenario": "Eigene %", "bear": "Bear %", "base": "Base %", "bull": "Bull %", "custom": "Custom %"}
    zeilen = []
    for a in m["assets"]:
        z = {"Baustein": a["name"]}
        for q in quellen:
            an = E.annahme(m, a["id"], q)
            z[titel[q]] = None if not an else round(an["value"] * 100, 2)
        eig = E.annahme(m, a["id"], "manualScenario")
        z["Notiz"] = (eig or {}).get("notes", "")
        zeilen.append(z)
    ed = _editor_formular(pd.DataFrame(zeilen), key=_k("annahmen"), hide_index=True, height=_hoehe(len(zeilen)), width="stretch",
                        disabled=["Baustein"],
                        column_config={t: st.column_config.NumberColumn(t, step=0.5, format="%.2f") for t in titel.values()})
    geaendert = False
    for i, a in enumerate(m["assets"]):
        for q in quellen:
            v = ed.iloc[i][titel[q]]
            alt = E.annahme(m, a["id"], q)
            if pd.isna(v):
                if alt is not None and q != "manualScenario":
                    m["annahmen"] = [x for x in m["annahmen"] if not (x["assetId"] == a["id"] and x["sourceType"] == q)]
                    geaendert = True
                continue
            if alt is None or abs(alt["value"] * 100 - float(v)) > 0.006:
                E.setze_annahme(m, a["id"], q, float(v) / 100)
                geaendert = True
        notiz = ed.iloc[i]["Notiz"]
        eig = E.annahme(m, a["id"], "manualScenario")
        if eig is not None and isinstance(notiz, str) and notiz != eig.get("notes", ""):
            eig["notes"] = notiz
            geaendert = True
    if geaendert:
        st.rerun()
    c1, c2 = st.columns(2)
    regel = m["szenario_regel"]
    regel["bear_faktor"] = float(c1.number_input("Bear = Basis ×", 0.0, 2.0, float(regel["bear_faktor"]), step=0.05,
                                                 key=_k("rb")))
    regel["bull_faktor"] = float(c2.number_input("Bull = Basis ×", 0.0, 3.0, float(regel["bull_faktor"]), step=0.05,
                                                 key=_k("rbu")))
    regel["text"] = (f"Fehlt eine eigene Bear-/Bull-Annahme: Bear = {_de(regel['bear_faktor'] * 100)} %, "
                     f"Bull = {_de(regel['bull_faktor'] * 100)} % der Basisannahme.")

    _abschnitt("Historical Layer & Datenqualität")
    zeilen = []
    for a in m["assets"]:
        h = historie.get(a["id"]) or {}
        ha = hist_assets.get(a["id"]) or {}
        info = R["info"].get(a["id"]) or {}
        conf = R["conf"].get(a["id"])
        badges = "".join(f'<span class="pl-badge pl-warn">{_esc(b)}</span>'
                         for b in E.bias_hinweise(a, info, conf)) if a.get("enabled") else ""
        if info.get("hinweis"):
            badges += f'<span class="pl-badge pl-info">{_esc(info["hinweis"])}</span>'
        quelle = (info.get("herkunft") or {}).get("sourceType") or "–"
        zeilen.append([
            f'<span class="pt-name">{_esc(a["name"])}</span><span class="pt-sub">'
            f'{_esc(ha.get("instrument") or ha.get("fehler") or "")}</span>{badges}',
            _pct(info.get("brutto")) if a.get("enabled") else "aus",
            _esc(QUELLEN.get(quelle, quelle)),
            _pct(h.get("historical5Y")), _pct(h.get("historical10Y")), _pct(h.get("fundamentalModel")),
            (_de(h.get("jahre"), 1) + " J.") if h.get("jahre") else "–",
            f"{_de(conf)}/100" if conf is not None else "–",
            _datum(h.get("stand")) if h.get("stand") else "–",
        ])
    _tabelle(["Baustein", "Rendite", "Quelle", "Hist. 5J", "Hist. 10J", "Fundam.", "Historie", "Confidence",
              "Datenstand"], zeilen)
    st.caption("Zwei getrennte Ebenen: Historical Layer = gemessene Vergangenheit (ls-tc.de-Kurshistorie, "
               "Qualitäts-Agent), Assumption Layer = frei gewählte Annahmen für die Rechnung. Confidence misst "
               "nur die Länge/Belastbarkeit der Datenbasis (1 J. ≈ 22, 5 J. ≈ 71, 10 J. ≈ 92), keine "
               "Wahrscheinlichkeit. Werte ohne Quelle werden nicht erfunden, sondern bleiben leer.")

    ids = [a["id"] for a in m["assets"] if a.get("enabled") and a["category"] != "cash"]
    if ids:
        w = E.gewichte(m)
        fig = go.Figure(go.Scatter(
            x=[R["conf"].get(i) for i in ids], y=[(R["info"][i]["brutto"] or 0) * 100 for i in ids],
            mode="markers+text", text=[_asset(m, i)["name"][:18] for i in ids], textposition="top center",
            textfont=dict(size=10), marker=dict(size=[8 + w[i] * 120 for i in ids], color="#4C9AFF", opacity=0.75),
            hovertemplate="%{text}: %{y:.1f} % · Conf. %{x}<extra></extra>"))
        _layout(fig, 360, legende=False, eur=False)
        fig.update_layout(hovermode="closest")
        fig.update_xaxes(title="Data Confidence (0–100)", range=[0, 105])
        fig.update_yaxes(title="Angenommene Rendite % p.a.", side="left")
        _chart(fig, "pl_conf")
        st.caption("Rechts oben = hohe Annahme mit guter Datenbasis. Links oben = hohe Annahme mit dünner Datenbasis.")

    _abschnitt("Stammdaten")
    kats = list(D.KATEGORIEN)
    df = pd.DataFrame([{
        "Baustein": a["name"], "WKN/Ticker": a.get("ticker") or "", "ISIN": a.get("isin") or "",
        "Kategorie": a["category"], "TER %": None if a.get("expenseRatio") is None else a["expenseRatio"] * 100,
        "Perf.-Fee %": None if a.get("performanceFee") is None else a["performanceFee"] * 100,
        "Hebel": a.get("leverage") or 1.0, "Tech %": None if a.get("techAnteil") is None else a["techAnteil"] * 100,
        "Halbl. %": None if a.get("semiAnteil") is None else a["semiAnteil"] * 100,
    } for a in m["assets"]])
    ed = _editor_formular(df, key=_k("stamm"), hide_index=True, height=_hoehe(len(df)), width="stretch", disabled=["Baustein"],
                        column_config={"Kategorie": st.column_config.SelectboxColumn(options=kats),
                                       "TER %": st.column_config.NumberColumn(format="%.2f", step=0.05),
                                       "Perf.-Fee %": st.column_config.NumberColumn(format="%.0f", step=1.0),
                                       "Hebel": st.column_config.NumberColumn(format="%.1f", step=0.5),
                                       "Tech %": st.column_config.NumberColumn(format="%.0f", min_value=0, max_value=100),
                                       "Halbl. %": st.column_config.NumberColumn(format="%.0f", min_value=0, max_value=100)})
    geaendert = False

    def zahl(v, faktor=1.0):
        return None if pd.isna(v) else float(v) / faktor

    for i, a in enumerate(m["assets"]):
        z = ed.iloc[i]
        neu = {"ticker": (str(z["WKN/Ticker"]).strip() or None) if not pd.isna(z["WKN/Ticker"]) else None,
               "isin": (str(z["ISIN"]).strip() or None) if not pd.isna(z["ISIN"]) else None,
               "category": z["Kategorie"] if z["Kategorie"] in kats else a["category"],
               "expenseRatio": zahl(z["TER %"], 100), "performanceFee": zahl(z["Perf.-Fee %"], 100),
               "leverage": zahl(z["Hebel"]) or 1.0, "techAnteil": zahl(z["Tech %"], 100),
               "semiAnteil": zahl(z["Halbl. %"], 100)}
        for k, v in neu.items():
            alt = a.get(k)
            if (alt is None) != (v is None) or (v is not None and alt != v and not
                                                 (isinstance(v, float) and isinstance(alt, (int, float))
                                                  and abs(alt - v) < 1e-12)):
                a[k] = v
                geaendert = True
    if geaendert:
        st.rerun()
    st.caption("WKN/ISIN steuern die Kurssuche für den Historical Layer. Wikifolios ohne WKN werden per Name "
               "gesucht – bitte den gefundenen Namen oben prüfen.")



# --- 11 Entnahmeplan --------------------------------------------------------
def _entnahme_rechnen(m, R, e=None):
    """Entnahme aus dem Modell-Endwert der Aufbauphase (eine durchgehende Rechnung)."""
    e = e or _entnahme_daten(m)
    proj = R["zus"]["projektion"]
    kapital = R["zus"].get("endwert_netto", proj["endwert"])
    einstand = min(proj["eingezahlt"], kapital)
    if e.get("rendite_quelle", "eigen") == "eigen" and _auto_modus(m) not in ("ziel", "manuell"):
        rendite = e["rendite_pa"] / 100.0
    elif R["zus"]["modell_cagr"] is not None and not _ziel_in_entnahme(m):
        rendite = R["zus"]["modell_cagr"]
    else:
        # keine Aufbauphase (0 Jahre): gewichtete Portfoliorendite statt 0 %
        rendite = sum(g * R.get("r_calc", R["r"]).get(i, 0.0) for i, g in E.gewichte(m).items())
    kw = dict(dynamik_pa=e["dynamik_pa"] / 100.0, einstand=einstand,
              steuersatz=(e["steuersatz"] / 100.0) if e["steuer"] else 0.0,
              freibetrag=e["freibetrag"] if e["steuer"] else 0.0,
              stufen=e.get("stufen"), start_monat=_entnahme_start_monat(m))
    plan = E.entnahmeplan(kapital, rendite, e["monatlich"], jahre=int(e["dauer_jahre"]), **kw)
    return kapital, rendite, kw, plan


def _dauer_text(p, jahre_max=100):
    if p["reicht_dauerhaft"]:
        return f"über {jahre_max} J."
    mon = p["dauer_monate"]
    return f"{mon // 12} J. {mon % 12} M." if mon % 12 else f"{mon // 12} J."


def _entnahme_gegen_gewinne(m, R, e, kapital, rendite, plan):
    """Wie wird die Entnahme mit den Gewinnen verrechnet - bringt das Kapital
    trotz Entnahme noch Gewinn, und wie lange dauert es bis zum Zielwert, wenn
    sofort entnommen wird?"""
    _abschnitt("Entnahme gegen Gewinne")
    rm = (1 + rendite) ** (1 / 12) - 1
    gewinn_monat = kapital * rm
    ent = float(e["monatlich"])
    j1 = (plan.get("jahre_tabelle") or [None])[0]
    ertr1 = j1["ertrag"] if j1 else gewinn_monat * 12
    ent1 = j1["brutto"] if j1 else ent * 12
    saldo1 = ertr1 - ent1
    deckung = (ertr1 / ent1 * 100) if ent1 else None
    _kacheln([
        ("Gewinn pro Monat", f"{_de(gewinn_monat)} €", f"am Start: {_eur(kapital)} × {_pct(rendite)} p.a."),
        ("Entnahme pro Monat", f"{_de(ent)} €", f"{_de(ent / gewinn_monat * 100) if gewinn_monat > 0 else '–'} % des Gewinns"),
        ("Saldo 1. Jahr", f'<span class="{"pl-gut" if saldo1 >= 0 else "pl-schlecht"}">{"+" if saldo1 >= 0 else "−"}'
                          f'{_de(abs(saldo1))} €</span>', "Erträge minus Entnahme"),
        ("Ergebnis", f'<span class="{"pl-gut" if saldo1 >= 0 else "pl-schlecht"}">'
                     f'{"Kapital wächst" if saldo1 >= 0 else "Kapital schrumpft"}</span>',
         (f"Gewinne decken {_de(deckung)} % der Entnahme" if deckung is not None else "")),
    ], klein=True)
    st.caption(f"Jeden Monat wird zuerst verzinst ({_pct(rendite)} p.a.), dann die Entnahme abgezogen. Solange die "
               f"Entnahme unter dem Monatsgewinn bleibt (am Start {_de(gewinn_monat)} €), wird nur vom Gewinn gelebt "
               "und das Kapital wächst weiter.")

    # Zielwert trotz Entnahme: sofort entnehmen statt erst nach dem Aufbau
    ziel = float(m["rahmen"].get("zielvermoegen") or 0)
    if ziel <= 0:
        return
    eff = _mit_krediten(m)["rahmen"]
    start = float(eff["startkapital"])
    r_auf = R["zus"].get("modell_cagr")
    if r_auf is None:
        r_auf = rendite
    spar = float(m["rahmen"].get("sparrate_monat") or 0)
    ohne, _ = E.zeit_bis_ziel(start, r_auf, ziel, spar)
    mit, verlauf = E.zeit_bis_ziel(start, r_auf, ziel, spar, ent, float(e["dynamik_pa"]) / 100.0,
                                   stufen=e.get("stufen"))

    def dauer(mon):
        return "nie (Entnahme frisst die Gewinne)" if mon is None else \
            (f"{mon // 12} J. {mon % 12} M." if mon % 12 else f"{mon // 12} J.")
    _abschnitt("Wie lange bis zum Zielwert – mit Entnahme ab sofort?")
    _kacheln([
        ("Ohne Entnahme", dauer(ohne), f"{_eur(start)} → {_eur(ziel)} bei {_pct(r_auf)} p.a."),
        (f"Mit {_de(ent)} €/Monat", f'<span class="{"pl-gut" if mit is not None else "pl-schlecht"}">{dauer(mit)}</span>',
         "Entnahme läuft vom ersten Monat an"),
        ("Verzögerung", "–" if mit is None or ohne is None else
         (f"+{(mit - ohne) // 12} J. {(mit - ohne) % 12} M." if (mit - ohne) % 12 else f"+{(mit - ohne) // 12} J."),
         "durch die Entnahme"),
    ], klein=True)
    zeilen = [[str(int(j)) if float(j).is_integer() else _de(j, 1), f"{_de(er)} €", f"{_de(en)} €",
               f'<span class="{"pl-gut" if er - en >= 0 else "pl-schlecht"}">{"+" if er - en >= 0 else "−"}{_de(abs(er - en))} €</span>',
               f"<b>{_de(w)} €</b>" + (" ✓" if w >= ziel else "")]
              for j, w, er, en in verlauf[1:41]]
    if zeilen:
        _tabelle(["Jahr", "Erträge", "Entnahme", "Saldo", "Vermögen"], zeilen)
    st.caption(f"Startkapital {_eur(start)}" + (" (inkl. Kredite)" if _kredit_rahmen(m) else "")
               + f", Sparrate {_de(spar)} €/Monat, Rendite wie im Aufbau ({_pct(r_auf)} p.a.). ✓ = Zielwert erreicht.")


def _b_entnahme(m, R):
    e = _entnahme_daten(m)
    rahmen = m["rahmen"]
    proj = R["zus"]["projektion"]
    _abschnitt("Entnahmeplan (monatlich)")
    _hinweis("Szenariorechnung · keine Prognose · Entnahme beginnt nach dem Aufbau mit dem Modell-Endwert")
    if not e.get("aktiv", True):
        st.info("Die Entnahme ist ausgeschaltet – unter „🎯 Ziel & Rahmen“ (Schritt 1) bzw. „⚙️ Planung: Aufbau → Entnahme“ einschalten.")
        return
    kapital, rendite, kw, plan = _entnahme_rechnen(m, R, e)
    st.caption("Alle Eingaben (Aufbau und Entnahme) stehen unter „🎯 Ziel & Rahmen“ (Schritt 1) bzw. „⚙️ Planung: Aufbau → Entnahme“.")
    if e.get("rendite_quelle") == "modell":
        st.caption(f"Rendite in der Entnahme wie Aufbauphase: {_pct(rendite)} p.a. – so hohe Renditen über "
                   "Jahrzehnte durchzuhalten ist nicht plausibel; eine eigene Annahme ist meist ehrlicher.")
    jahre = e["dauer_jahre"]
    plan = E.entnahmeplan(kapital, rendite, e["monatlich"], jahre=jahre, **kw)
    verzehr = E.entnahme_fuer(kapital, rendite, jahre=jahre, **kw)
    erhalt = E.entnahme_fuer(kapital, rendite, jahre=jahre, ziel_restwert=kapital, **kw)
    reicht = plan["reicht_dauerhaft"] or plan["dauer_monate"] >= jahre * 12

    _kacheln([
        ("Startkapital", _eur(kapital), D.ENTNAHME_STARTS[e["start"]] + f" · nach {rahmen['horizont_jahre']} J."),
        ("Entnahme", f"{_de(e['monatlich'])} €", "pro Monat netto" + (" · " + _stufen_text(e, True) if e.get("stufen") else "")
         + (f", +{_de(e['dynamik_pa'], 1)} % p.a." if e["dynamik_pa"] else "")),
        ("Kapital reicht", f'<span class="{"pl-gut" if reicht else "pl-schlecht"}">{_dauer_text(plan)}</span>',
         f"Plan: {jahre} J. bei {_pct(rendite)} p.a."),
        (f"Rest nach {jahre} J.", _eur(plan["restwert"]) if plan["restwert"] else "0 €",
         f"Steuern gesamt {_eur(plan['summe_steuer'])}" if e["steuer"] else "vor Steuern"),
    ])
    _kacheln([
        ("Kapitalverzehr", f"{_de(verzehr)} €", f"max. pro Monat, aufgebraucht nach {jahre} J."),
        ("Kapitalerhalt", f"{_de(erhalt)} €", f"max. pro Monat, nach {jahre} J. noch {_eur(kapital)}"),
    ], klein=True)
    st.caption("Kapitalverzehr/-erhalt: erste Monatsentnahme (netto) – mit derselben jährlichen Erhöhung.")
    _entnahme_gegen_gewinne(m, R, e, kapital, rendite, plan)

    # Chart: Aufbau + Entnahme auf einer Zeitachse
    aufbau = proj["monatswerte"]
    n_auf = len(aufbau) - 1
    x_auf = [i / 12 for i in range(n_auf + 1)]
    ent = plan["verlauf"][: jahre * 12 + 1] if plan["reicht_dauerhaft"] or (plan["dauer_monate"] or 0) >= jahre * 12 \
        else plan["verlauf"]
    x_ent = [(n_auf + i) / 12 for i in range(len(ent))]
    fig = go.Figure()
    if e["start"] == "modell":
        fig.add_trace(go.Scatter(x=x_auf, y=aufbau, name="Aufbau (Modell)", line=dict(color="#4C9AFF", width=2)))
    fig.add_trace(go.Scatter(x=x_ent, y=ent, name="Entnahmephase", line=dict(color="#16C784", width=3)))
    netto_kum, summe = [0.0], 0.0
    for i in range(1, len(ent)):
        summe += E.entnahme_betrag(e["monatlich"], e["dynamik_pa"] / 100.0, i + kw.get("start_monat", 0),
                                   e.get("stufen"))
        netto_kum.append(summe)
    fig.add_trace(go.Scatter(x=x_ent, y=netto_kum, name="Summe Entnahmen", line=dict(color="#F5B942", dash="dot")))
    _layout(fig, 340)
    fig.update_xaxes(title="Jahre ab heute")
    _chart(fig, "pl_entnahme")

    _abschnitt("Rendite-Sensitivität")
    zeilen = []
    for d in (-0.04, -0.02, 0.0, 0.02):
        r = rendite + d
        p = E.entnahmeplan(kapital, r, e["monatlich"], jahre=jahre, **kw)
        ok = p["reicht_dauerhaft"] or p["dauer_monate"] >= jahre * 12
        zeilen.append([("<b>" if d == 0 else "") + _pct(r) + ("</b>" if d == 0 else ""),
                       f'<span class="{"pl-gut" if ok else "pl-schlecht"}">{_dauer_text(p)}</span>',
                       _eur(p["restwert"]) if p["restwert"] else "0 €",
                       _de(E.entnahme_fuer(kapital, r, jahre=jahre, **kw)) + " €"])
    _tabelle(["Rendite p.a.", "Reicht", f"Rest nach {jahre} J.", "Verzehr/Monat"], zeilen)
    st.caption("Konstante Renditen – echte Märkte schwanken. Verluste gleich zu Beginn der Entnahme wiegen deutlich "
               "schwerer (Reihenfolge-Risiko); der Stresspfad unter „⚠️ Risiko → Stress & Reserve“ zeigt die Aufbauphase.")

    _abschnitt("Jahresübersicht")
    tab = plan["jahre_tabelle"][:max(jahre, 1)]
    kopf = ["Jahr", "Anfang", "Erträge", "Entnahme netto"] + (["Steuer"] if e["steuer"] else []) + ["Saldo", "Ende"]

    def _saldo(z):
        v = z["ertrag"] - z["brutto"]
        return f'<span class="{"pl-gut" if v >= 0 else "pl-schlecht"}">{"+" if v >= 0 else "−"}{_de(abs(v))} €</span>'
    _tabelle(kopf, [[str(rahmen["horizont_jahre"] + z["jahr"]), _de(z["anfang"]) + " €", _de(z["ertrag"]) + " €",
                     _de(z["netto"]) + " €"] + ([_de(z["steuer"]) + " €"] if e["steuer"] else [])
                    + [_saldo(z), _de(z.get("ende", 0)) + " €"] for z in tab])
    st.caption("Saldo = Erträge minus Entnahme (inkl. Steuer): grün = die Gewinne decken die Entnahme, das Kapital "
               "wächst; rot = es wird vom Kapital gelebt.")
    st.caption("„Jahr“ = Jahre ab heute (Aufbauphase + Entnahmejahr). Beträge ungerundet zur Nachvollziehbarkeit – "
               "alle Werte bleiben Szenariorechnung.")


# ===========================================================================
# Kredite: Betrag + monatliche Rate je Kredit, in die Planung eingerechnet
# ===========================================================================
KREDIT_SEED = [{"name": "Kredit 1", "betrag": 0.0, "rate": 0.0, "jahre": 5}]


def _kredite(m):
    """Kreditliste (neues, einfaches Format) - alte Eintraege werden umgerechnet."""
    k = m.setdefault("kredit", {})
    liste = k.get("kredite")
    if liste is None:
        liste = copy.deepcopy(KREDIT_SEED)
    neu = []
    for i, x in enumerate(liste, 1):
        if "rate" not in x:                  # altes Format: Zins + Laufzeit -> Monatsrate
            x = {"name": x.get("name") or f"Kredit {i}", "betrag": float(x.get("betrag") or 0),
                 "rate": round(E.kredit_rate(float(x.get("betrag") or 0), float(x.get("zins") or 0) / 100.0,
                                             int(x.get("jahre") or 1)), 2),
                 "jahre": int(x.get("jahre") or 1)}
        x = dict(x)
        for f in ("betrag", "rate"):
            try:
                v = float(x.get(f) or 0)
                x[f] = 0.0 if v != v else v          # NaN -> 0
            except (TypeError, ValueError):
                x[f] = 0.0
        try:
            j = x.get("jahre")
            j = float(j) if j is not None else float("nan")
            # fehlende Laufzeit -> 5 J.; 0 ist erlaubt (Kredit zaehlt dann in keiner Rechnung)
            x["jahre"] = max(int(j), 0) if j == j else 5
        except (TypeError, ValueError):
            x["jahre"] = 5
        neu.append(x)
    k["kredite"] = neu
    if not k.get("aktiv_v2"):               # neu: eingetragene Kredite zaehlen standardmaessig zum Kapital
        k["aktiv"] = True
        k["aktiv_v2"] = True
    if not k.get("rate_aus_v2"):            # neu: Raten stecken standardmaessig in der Entnahme
        k["rate_aus"] = "entnahme"
        k["rate_aus_v2"] = True
    if k.get("rate_aus") not in RATE_AUS:
        k["rate_aus"] = "entnahme"
    return k


RATE_AUS = {"entnahme": "aus der Entnahme (darin enthalten)", "einkommen": "aus dem Einkommen",
            "investment": "zusätzlich aus dem Depot"}


def _rate_aus(m):
    k = m.get("kredit") or {}
    return k.get("rate_aus") if k.get("rate_aus_v2") and k.get("rate_aus") in RATE_AUS else "entnahme"


def _sim_rate_aus(m):
    """Fuer die Kreditsimulation: Raten aus der Entnahme belasten das Depot nicht
    zusaetzlich -> wie 'einkommen' (Vergleich: ohne Kredit bliebe die Rate im Depot)."""
    return "investment" if _rate_aus(m) == "investment" else "einkommen"


def _kredit_rechnen(m, R):
    """Alle Kredite gegen die Alternative ohne Kredit. Das Kreditgeld wird wie das
    Portfolio angelegt (Portfolio-Rendite des Modells).
    -> dict oder None (keine Kredite / ausgeschaltet)"""
    k = _kredite(m)
    kredite = [x for x in k["kredite"] if x.get("betrag") and int(x.get("jahre") or 0) > 0]
    if not _kredite_aktiv(m) or not kredite:
        return None
    z = R["zus"]
    r = z["modell_cagr"] if z.get("modell_cagr") is not None else \
        sum(g * R.get("r_calc", R["r"]).get(i, 0.0) for i, g in E.gewichte(m).items())
    jahre_aufbau = int(m["rahmen"].get("horizont_jahre") or 0)
    horizont = max(jahre_aufbau, max(int(x["jahre"]) for x in kredite))
    ek_end = E.zusammenfassung(m, R.get("r_calc", R["r"]), rebalancing=R["reb"])["endwert"] if jahre_aufbau == horizont and jahre_aufbau > 0 else \
        float(m["rahmen"]["startkapital"]) * (1 + r) ** horizont
    zeilen = []
    for x in kredite:
        zins, fehler = _kredit_konditionen(x)
        if zins is None:
            zeilen.append({"x": x, "fehler": fehler})
            continue
        o = E.kredit_simulation(float(x["betrag"]), zins, int(x["jahre"]), "annuitaet", _sim_rate_aus(m), r, horizont,
                                rate=_kredit_rate_eff(x, zins))
        be = E.kredit_break_even(float(x["betrag"]), zins, int(x["jahre"]), "annuitaet", _sim_rate_aus(m), horizont,
                                rate=_kredit_rate_eff(x, zins))
        zeilen.append({"x": x, "zins": zins, "o": o, "lohnt_ab": be})
    ok = [z_ for z_ in zeilen if "o" in z_]
    mit = ek_end + sum(z_["o"]["netto_mit"] for z_ in ok)
    ohne = ek_end + sum(z_["o"]["netto_ohne"] for z_ in ok)
    return {"zeilen": zeilen, "r": r, "horizont": horizont, "ek_end": ek_end, "mit": mit, "ohne": ohne,
            "vorteil": mit - ohne, "summe": sum(float(x["betrag"]) for x in kredite),
            "rate": sum(_kredit_rate_eff(x) for x in kredite), "zinsen": sum(z_["o"]["zinsen"] for z_ in ok),
            "rate_aus": _rate_aus(m)}


def _b_kredit(m, R):
    _abschnitt("Kredite")
    _hinweis("Szenariorechnung · keine Anlage- oder Kreditberatung. Kredit = Hebel: Gewinne UND Verluste werden "
             "größer, die Raten bleiben in jedem Fall fällig.")
    k = _kredite(m)
    c1, c2 = st.columns(2)
    k["aktiv"] = c1.toggle("Kredite in die Planung einrechnen", value=_kredite_aktiv(m), key=_k("kr_aktiv"),
                           help="Das Kreditgeld wird zusätzlich zum Startkapital angelegt; oben in den Kennzahlen "
                                "steht dann das Ergebnis nach Abzug der Restschuld")
    arten = list(RATE_AUS)
    k["rate_aus"] = c2.selectbox(
        "Kreditraten bezahlt", arten, index=arten.index(_rate_aus(m)), format_func=RATE_AUS.get, key=_k("kr_aus2"),
        help="Aus der Entnahme (Standard): die Raten sind in der monatlichen Entnahme schon enthalten – sie werden "
             "nicht noch einmal abgezogen. Aus dem Einkommen: Raten belasten das Depot nicht. Zusätzlich aus dem "
             "Depot: für jede Rate werden zusätzlich zur Entnahme Anteile verkauft.")
    k["rate_aus_v2"] = True

    if not k["kredite"]:
        k["kredite"] = [{"name": "Kredit 1", "betrag": 0.0, "rate": 0.0, "jahre": 5}]
    # „Hinzufügen“ ueber der Tabelle; Loeschen direkt in der Zeile (🗑️ hinter dem Namen)
    if st.button("➕ Kredit hinzufügen", key=_k("kr_neu"), width="stretch"):
        k["kredite"].append({"name": f"Kredit {len(k['kredite']) + 1}", "betrag": 0.0, "rate": 0.0, "jahre": 5,
                             "zins": None})
        st.session_state["planer_kr_ver"] = st.session_state.get("planer_kr_ver", 0) + 1
        st.rerun()
    df = pd.DataFrame([{"Kredit": x["name"], "🗑️": False, "Betrag €": float(x["betrag"]),
                        "Rate/Monat €": float(x["rate"]), "Laufzeit J.": int(x["jahre"]),
                        "Zins %": float(x.get("zins") or 0.0)}
                       for x in k["kredite"]])
    st.caption("Werte direkt in der Tabelle ändern – wird sofort übernommen. 🗑️ antippen = Kredit löschen.")
    cfg = {
        "Kredit": st.column_config.TextColumn("Kredit", width="small", pinned=True),
        "🗑️": st.column_config.CheckboxColumn("🗑️", width=40, pinned=True, help="Antippen = diesen Kredit löschen"),
        "Betrag €": st.column_config.NumberColumn("Betrag €", min_value=0.0, step=1000.0, format="%d"),
        "Rate/Monat €": st.column_config.NumberColumn("Rate/Monat €", min_value=0.0, step=10.0, format="%.2f",
                                                      help="Monatliche Belastung laut Kreditvertrag (Zins + Tilgung)"),
        "Laufzeit J.": st.column_config.NumberColumn("Laufzeit J.", min_value=0, max_value=40, step=1, format="%d",
                                                     help="0 = Kredit bleibt in der Liste, fließt aber in keine "
                                                          "Berechnung ein (Kapital, Raten, Restschuld, Monatsbilanz)"),
        "Zins %": st.column_config.NumberColumn("Zins %", min_value=0.0, max_value=30.0, step=0.1, format="%.2f",
                                                help="Optional. 0 = aus Rate und Laufzeit errechnen (Rate tilgt "
                                                     "komplett). Eingetragen: Tilgt die Rate nicht alles, bleibt "
                                                     "eine Schlussrate, die aus dem Depot bezahlt wird."),
    }
    kw = dict(key=_k(f"kredite4_{len(df)}_{st.session_state.get('planer_kr_ver', 0)}"), hide_index=True,
              width="stretch", num_rows="fixed", height=_hoehe(len(df)))
    try:
        ed = st.data_editor(df, column_config=cfg, **kw)
    except TypeError:                     # aeltere Streamlit-Version ohne pinned/width-Zahl
        for c in ("Kredit", "🗑️"):
            cfg[c] = (st.column_config.TextColumn("Kredit", width="small") if c == "Kredit"
                      else st.column_config.CheckboxColumn("🗑️", width="small"))
        ed = st.data_editor(df, column_config=cfg, **kw)
    if ed is not None and len(ed) == len(df):
        neu = []
        for i, (_, z) in enumerate(ed.iterrows(), 1):
            if bool(z.get("🗑️")):
                continue
            neu.append({"name": str(z.get("Kredit") or "").strip() or f"Kredit {i}",
                        "betrag": 0.0 if pd.isna(z.get("Betrag €")) else float(z["Betrag €"]),
                        "rate": 0.0 if pd.isna(z.get("Rate/Monat €")) else float(z["Rate/Monat €"]),
                        "jahre": 0 if pd.isna(z.get("Laufzeit J.")) else max(int(z["Laufzeit J."]), 0),
                        "zins": None if pd.isna(z.get("Zins %")) or not z.get("Zins %") else float(z["Zins %"])})
        geloescht = len(neu) < len(df)
        if geloescht:
            for j, y in enumerate(neu, 1):            # Standardnamen neu durchzaehlen
                if re.fullmatch(r"Kredit \d+", y["name"] or ""):
                    y["name"] = f"Kredit {j}"
        if geloescht or _norm(neu) != _norm(k["kredite"]):
            k["kredite"] = neu
            st.session_state["planer_kr_ver"] = st.session_state.get("planer_kr_ver", 0) + 1
            st.rerun()

    ohne = [x["name"] for x in k["kredite"] if int(x.get("jahre") or 0) <= 0]
    if ohne:
        st.caption("⏸️ Laufzeit 0 J. – nicht eingerechnet (Kapital, Raten, Restschuld, Monatsbilanz): "
                   + ", ".join(ohne))
    erg = _kredit_rechnen(m, R)
    if erg is None:
        st.info("Kredite eintragen (Betrag und Laufzeit, optional Rate und Zins) und „Kredite in die Planung "
                "einrechnen“ einschalten.")
        return
    v = erg["vorteil"]
    _kacheln([
        ("Mit Krediten", _eur(erg["mit"]), f"nach {erg['horizont']} J. · nach Abzug der Restschuld"),
        ("Ohne Kredite", _eur(erg["ohne"]), {"einkommen": "Raten stattdessen gespart",
                                              "entnahme": "Raten-Anteil der Entnahme bleibt im Depot"}
         .get(erg["rate_aus"], "nur Startkapital")),
        ("Vorteil Kredite", f'<span class="{"pl-gut" if v >= 0 else "pl-schlecht"}">{"+" if v >= 0 else "−"}'
                            f'{_de(abs(v))} €</span>', "lohnt sich" if v >= 0 else "lohnt sich nicht"),
        ("Belastung", f"{_de(erg['rate'], 2)} €/Monat", ("in der Entnahme enthalten · " if erg["rate_aus"] == "entnahme" else "")
         + f"Kredite {_de(erg['summe'])} € · Zinsen {_de(erg['zinsen'])} €"),
    ])
    st.caption(f"Gerechnet mit der Portfolio-Rendite des Modells: {_pct(erg['r'])} p.a. – das Kreditgeld wird wie das "
               "Portfolio angelegt.")
    zeilen = []
    for z in erg["zeilen"]:
        x = z["x"]
        if "fehler" in z:
            zeilen.append([f"<b>{_esc(x['name'])}</b>", f"{_de(x['betrag'])} €", f"{_de(x['rate'], 2)} €",
                           f"{x['jahre']} J.", f'<span class="pl-schlecht">{_esc(z["fehler"])}</span>', "", "", ""])
            continue
        o = z["o"]
        vv = o["vorteil"]
        zeilen.append([f"<b>{_esc(x['name'])}</b>", f"{_de(x['betrag'])} €",
                       f"{_de(x['rate'], 2)} €" if float(x.get("rate") or 0) else "keine (endfällig)",
                       f"{x['jahre']} J.", f"{_de(z['zins'] * 100, 2)} %"
                       + ("" if x.get("zins") or not float(x.get("rate") or 0) else " (err.)"),
                       f"{_de(o['zinsen'])} €",
                       f'<span class="{"pl-gut" if vv >= 0 else "pl-schlecht"}"><b>{"+" if vv >= 0 else "−"}'
                       f'{_de(abs(vv))} €</b></span>', _pct(z["lohnt_ab"]) if z["lohnt_ab"] is not None else "–"])
    _tabelle(["Kredit", "Betrag", "Rate", "Laufzeit", "Zins", "Zinskosten", "Vorteil", "Lohnt ab"], zeilen)
    for z in erg["zeilen"]:
        if "o" in z and z["o"]["schlussrate"] > 1:
            if not float(z["x"].get("rate") or 0):
                st.caption(f"{z['x']['name']}: keine Rate eingetragen – "
                           + (f"monatlich nur Zinsen ({_de(_kredit_rate_eff(z['x'], z['zins']), 2)} €), " if z["zins"]
                              else "zinsfrei gerechnet, ")
                           + f"der ganze Betrag ({_de(z['o']['schlussrate'])} €) wird am Laufzeitende aus dem Depot "
                             "getilgt.")
                continue
            st.caption(f"{z['x']['name']}: Die Rate tilgt nicht alles – am Laufzeitende bleiben "
                       f"{_de(z['o']['schlussrate'])} € Schlussrate, die aus dem Depot getilgt werden."
                       + ("" if z["x"].get("zins") else " Gerechnet mit 0 % Zins – für eine genaue Rechnung "
                                                       "„Zins %“ eintragen."))
    st.caption("Zins = aus Betrag, Rate und Laufzeit errechneter Sollzins. „Lohnt ab“ = Rendite p.a., ab der der "
               "Kredit mehr bringt, als er kostet. Vorteil = Ergebnis mit Kredit minus Ergebnis, wenn man die Raten "
               "stattdessen selbst anlegt.")

    # Tilgungsplan: Restschuld Jahr fuer Jahr (alle Kredite zusammen)
    _abschnitt("Tilgungsplan")
    plan = {}
    for z in erg["zeilen"]:
        if "o" not in z:
            continue
        x, zm = z["x"], z["zins"] / 12.0
        rest, n = float(x["betrag"]), int(x["jahre"]) * 12
        for mon in range(1, n + 1):
            j_ = (mon - 1) // 12 + 1
            p = plan.setdefault(j_, {"anfang": 0.0, "zinsen": 0.0, "tilgung": 0.0, "schluss": 0.0, "ende": 0.0})
            if (mon - 1) % 12 == 0:
                p["anfang"] += rest
            zins = rest * zm
            tilg = min(_kredit_rate_eff(x, z["zins"]) - zins, rest)
            rest -= tilg
            p["zinsen"] += zins
            p["tilgung"] += tilg
            if mon == n and rest > 1e-6:
                p["schluss"] += rest
                rest = 0.0
            if mon % 12 == 0 or mon == n:
                p["ende"] += rest
    if plan:
        jahre_p = sorted(plan)
        _tabelle(["Jahr", "Restschuld Anfang", "Zinsen", "Tilgung", "Schlussrate", "Restschuld Ende"],
                 [[str(j_), f'{_de(plan[j_]["anfang"])} €', f'{_de(plan[j_]["zinsen"])} €',
                   f'{_de(plan[j_]["tilgung"])} €', f'{_de(plan[j_]["schluss"])} €' if plan[j_]["schluss"] else "–",
                   f'<b>{_de(plan[j_]["ende"])} €</b>'] for j_ in jahre_p])
        fig_s = go.Figure()
        fig_s.add_trace(go.Bar(x=[0] + jahre_p, y=[plan[jahre_p[0]]["anfang"]] + [plan[j_]["ende"] for j_ in jahre_p],
                               name="Restschuld", marker_color="#EA3943",
                               text=[_kurz_eur(v) for v in [plan[jahre_p[0]]["anfang"]] + [plan[j_]["ende"] for j_ in jahre_p]],
                               textposition="outside", textfont=dict(color="#FFFFFF", size=11)))
        _layout(fig_s, 280, legende=False)
        fig_s.update_xaxes(title="Jahr (0 = Start)", dtick=1)
        fig_s.update_yaxes(rangemode="tozero")
        _chart(fig_s, "pl_kredit_schuld")

    # Verlauf: Vermoegen mit/ohne Kredite
    _abschnitt("Vermögen mit und ohne Kredite")
    jahre = list(range(0, erg["horizont"] + 1))
    ek0 = float(m["rahmen"]["startkapital"])
    pfad_ek = [ek0 * (1 + erg["r"]) ** j for j in jahre]
    mit_p, ohne_p = list(pfad_ek), list(pfad_ek)
    for z in erg["zeilen"]:
        if "o" not in z:
            continue
        for j in jahre:
            pkt = next((p for p in z["o"]["verlauf"] if p[0] == j * 12), z["o"]["verlauf"][-1])
            mit_p[j] += pkt[1]
            ohne_p[j] += pkt[2]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=jahre, y=mit_p, name="Mit Krediten (nach Restschuld)", line=dict(color="#16C784", width=3)))
    fig.add_trace(go.Scatter(x=jahre, y=ohne_p, name="Ohne Kredite", line=dict(color="#4C9AFF", width=2, dash="dash")))
    _layout(fig, 340)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title="Jahre")
    fig.update_yaxes(hoverformat=",.0f")
    _chart(fig, "pl_kredit")


# ===========================================================================
# Kaufplan (Stueckzahlen) und Musterdepot
# ===========================================================================


def _kauf_positionen(m, hist_assets, hist_korb):
    """Kaufbare Einzelpositionen mit Anteil am Gesamtbetrag und aktuellem Kurs.
    Der Aktienkorb wird in seine Aktien aufgeteilt (nach Korbgewichten)."""
    pos = []
    for aid, w in E.gewichte(m).items():
        if w <= 0:
            continue
        a = _asset(m, aid)
        if a["category"] == "cash":
            pos.append({"id": aid, "name": a["name"], "anteil": w, "cash": True, "wkn": "", "kurs": None})
            continue
        if a["category"] == "stock_basket":
            korb = m.get("korb") or []
            summe = sum(float(k.get("gewicht") or 0) for k in korb) or 1.0
            for k in korb:
                hk = hist_korb.get(k["id"]) or {}
                pos.append({"id": f"{aid}:{k['id']}", "name": k["name"], "teil_von": a["name"],
                            "anteil": w * float(k.get("gewicht") or 0) / summe, "kurs": hk.get("kurs"),
                            "wkn": hk.get("wkn") or "", "isin": k.get("isin") or hk.get("isin") or "",
                            "instrument_id": hk.get("instrument_id")})
            continue
        ha = hist_assets.get(aid) or {}
        pos.append({"id": aid, "name": a["name"], "anteil": w, "kurs": ha.get("kurs"),
                    "wkn": ha.get("wkn") or a.get("ticker") or "", "isin": ha.get("isin") or a.get("isin") or "",
                    "instrument_id": ha.get("instrument_id"), "kategorie": a["category"]})
    return pos


def _b_kaufplan(m, R, h, hist_assets, hist_korb):
    _abschnitt("Kaufplan – Stückzahlen")
    kp = m.setdefault("kaufplan", {"betrag": float(m["rahmen"]["startkapital"]), "bruch": False})
    c1, c2 = st.columns(2)
    kp["betrag"] = float(c1.number_input("Kaufwert gesamt (€)", 0.0, 1e9, float(kp.get("betrag") or 0.0),
                                         step=500.0, format="%.0f", key=_k("kp_betrag"),
                                         help="Betrag, der nach den aktuellen Gewichten investiert werden soll"))
    kp["bruch"] = c2.toggle("Bruchstücke erlauben", value=bool(kp.get("bruch")), key=_k("kp_bruch"),
                            help="Aus: nur ganze Stücke (Rest bleibt Cash). An: exakte Stückzahl, z. B. für "
                                 "Sparpläne oder Broker mit Bruchteilshandel")
    pos = _kauf_positionen(m, hist_assets, hist_korb)
    if not pos:
        st.info("Keine aktiven Bausteine mit Gewicht – erst unter „Bausteine“ Gewichte vergeben.")
        return
    erg = E.kaufplan(pos, kp["betrag"], bool(kp["bruch"]))
    st.session_state["planer_kaufplan"] = erg

    _kacheln([
        ("Kaufwert", f'{_de(kp["betrag"])} €', "nach aktuellen Gewichten"),
        ("Investiert", f'{_de(erg["investiert"], 2)} €', f'{len([z for z in erg["zeilen"] if z["stueck"]])} Positionen'),
        ("Reserve (Cash)", f'{_de(erg["cash_soll"], 2)} €', "laut Gewichtung"),
        ("Rest (Cash)", f'{_de(erg["rest"], 2)} €', "durch Stückelung übrig"),
    ], klein=True)
    zeilen = []
    for z in sorted(erg["zeilen"], key=lambda z: -z["soll"]):
        name = f'<b>{_esc(z["name"])}</b><br><span class="pt-sub">' + _esc(
            " · ".join(x for x in (z.get("wkn"), ("aus " + z["teil_von"]) if z.get("teil_von") else "") if x)) + "</span>"
        if z.get("cash"):
            zeilen.append([name, _pct(z["anteil"]), _de(z["soll"], 2) + " €", "–", "Cash", _de(z["ist"], 2) + " €", "–"])
            continue
        stueck = (_de(z["stueck"], 4).rstrip("0").rstrip(",") if kp["bruch"] else _de(z["stueck"])) if z["kurs"] else "–"
        abw = z["abweichung"]
        zeilen.append([name, _pct(z["anteil"]), _de(z["soll"], 2) + " €",
                       (_de(z["kurs"], 2) + " €") if z["kurs"] else '<span class="pl-schlecht">kein Kurs</span>',
                       f"<b>{stueck}</b>", _de(z["ist"], 2) + " €",
                       f'<span class="{"pl-gut" if abs(abw) < max(z["kurs"] or 0, 1) else "pl-schlecht"}">'
                       f'{"+" if abw >= 0 else "−"}{_de(abs(abw), 2)} €</span>'])
    _tabelle(["Position", "Gewicht", "Soll", "Kurs", "Stück", "Ist", "Abw."], zeilen)
    st.caption("Kurs = letzter Schlusskurs laut ls-tc.de (Kurshistorie) – beim echten Kauf weichen Kurse, "
               "Spreads und Gebühren ab. Ganze Stücke: abgerundet, der Rest wird stückweise auf die Positionen "
               "mit dem größten Rückstand verteilt.")
    if erg["ohne_kurs"]:
        st.warning("Ohne aktuellen Kurs (nicht gekauft, Betrag bleibt Cash): " + ", ".join(erg["ohne_kurs"]))

    _musterdepot_formular(h, erg, float(kp["betrag"]), "kp")


def _musterdepot_formular(h, erg, betrag, prefix):
    """Name + Button: legt aus einem Kaufplan (E.kaufplan) ein Musterdepot an."""
    _abschnitt("Als Musterdepot übernehmen")
    st.caption(f"Legt aus diesen Stückzahlen ({_de(betrag)} €) ein Musterdepot an – Kaufkurs = Kurs von heute. "
               "Es erscheint im Menü unter „Depot“ als eigener Button „📦 Musterdepot“ und zeigt die Entwicklung "
               "seit heute.")
    vorhanden = (_lesen(h, _pfad(h, PFAD_MUSTERDEPOT), {})[0].get("depots") or {})
    name = st.text_input("Name des Musterdepots", value="Portfolio Builder Musterdepot",
                         key=_k(f"md_name_{prefix}")).strip()
    ueber = True
    if name in vorhanden:
        ueber = st.checkbox(f"„{name}“ gibt es schon – überschreiben", key=_k(f"md_ueber_{prefix}"))
    kaufbar = [z for z in erg["zeilen"] if not z.get("cash") and z["stueck"] > 0 and z.get("instrument_id")]
    if st.button("📦 Musterdepot erstellen", key=_k(f"md_los_{prefix}"), width="stretch",
                 disabled=not name or not ueber or not kaufbar):
        heute = h["heute"].isoformat() if h.get("heute") else datetime.date.today().isoformat()
        depot = {
            "name": name, "erstellt": heute, "kaufwert": float(betrag),
            # alles, was nicht als Stueck im Depot liegt, ist Cash (Reserve, Rest, Werte ohne Kurs)
            "cash": round(float(betrag) - sum(z["ist"] for z in kaufbar), 2),
            "positionen": [{"name": z["name"], "wkn": z.get("wkn") or "", "isin": z.get("isin") or "",
                            "instrument_id": z["instrument_id"], "stueck": z["stueck"], "kaufkurs": z["kurs"],
                            "kaufwert": round(z["ist"], 2), "gewicht_soll": round(z["anteil"] * 100, 3),
                            "teil_von": z.get("teil_von")} for z in kaufbar],
            "quelle": st.session_state.get("planer_name") or "Aktuelles Modell",
        }
        def _anlegen(d):
            if not isinstance(d.get("depots"), dict):
                d["depots"] = {}
            d["depots"][name] = depot
            d["aktiv"] = name
            return d
        ok = _aendern_speichern(h, _pfad(h, PFAD_MUSTERDEPOT), _anlegen, f"planer: musterdepot {name} [skip ci]")
        if ok and h.get("chronik"):
            try:
                h["chronik"]("planer", f"📦 Musterdepot erstellt: {name}",
                             f"Kaufwert {_de(betrag)} € · {len(kaufbar)} Positionen · Cash {_de(depot['cash'], 2)} € · "
                             f"aus „{depot['quelle']}“")
            except Exception:
                pass
        if ok:
            st.success(f"✓ Musterdepot „{name}“ erstellt ({len(kaufbar)} Positionen, Cash {_de(depot['cash'], 2)} €). "
                       "Zu finden im Menü unter „Depot“ → „📦 Musterdepot“.")
        else:
            st.error("Speichern nicht möglich – GitHub-Speicher nicht erreichbar.")


def render_musterdepot(h):
    """Eigene Ansicht im Menue (Depot): Entwicklung der Musterdepots seit Erstellung."""
    st.markdown(CSS, unsafe_allow_html=True)
    daten, lesbar = _lesen(h, _pfad(h, PFAD_MUSTERDEPOT), {})
    depots = daten.get("depots") if isinstance(daten.get("depots"), dict) else {}
    if not lesbar:
        st.error("Musterdepots gerade nicht lesbar (GitHub-Speicher nicht erreichbar) – bitte später neu laden.")
        return
    if not depots:
        st.info("Noch kein Musterdepot vorhanden. Anlegen im Portfolio-Planer unter „🧩 Portfolio → Kaufplan“.")
        return
    namen = list(depots)
    wahl = namen[0] if len(namen) == 1 else (
        st.pills("Musterdepot", namen, default=daten.get("aktiv") if daten.get("aktiv") in namen else namen[0],
                 key="md_wahl") or namen[0])
    d = depots[wahl]
    pos = d.get("positionen") or []
    with st.spinner("Lade Kurse …"):
        kurse = _parallel([(i, h["get_live_kurs"], (p["instrument_id"],)) for i, p in enumerate(pos)])
    zeilen, wert, kauf, heute_diff = [], 0.0, 0.0, 0.0
    berechnet = []
    for i, p in enumerate(pos):
        k = kurse.get(i)
        akt = vor = None
        if isinstance(k, (tuple, list)) and k and k[0]:
            akt, vor = float(k[0]), (float(k[1]) if k[1] else None)
        akt_w = (akt or p["kaufkurs"]) * p["stueck"]
        wert += akt_w
        kauf += p["kaufwert"]
        if akt and vor:
            heute_diff += (akt - vor) * p["stueck"]
        berechnet.append((p, akt, akt_w))
    cash = float(d.get("cash") or 0.0)
    gesamt = wert + cash
    basis = kauf + cash
    gv = gesamt - basis
    try:
        seit = datetime.date.fromisoformat(d["erstellt"]).strftime("%d.%m.%Y")
    except Exception:
        seit = d.get("erstellt", "–")
    st.markdown(f'<div class="abschnitt">📦 {_esc(wahl)}</div>', unsafe_allow_html=True)
    _hinweis(f"Musterdepot aus dem Portfolio-Planer („{d.get('quelle', '–')}“) · erstellt am {seit} · "
             "Kaufkurse = Schlusskurse vom Erstellungstag · ohne Gebühren und Steuern")
    farbe = "pl-gut" if gv >= 0 else "pl-schlecht"
    _kacheln([
        ("Depotwert", f"{_de(gesamt, 2)} €", f"davon Cash {_de(cash, 2)} €"),
        ("Gewinn/Verlust", f'<span class="{farbe}">{"+" if gv >= 0 else "−"}{_de(abs(gv), 2)} €</span>',
         f'{"+" if gv >= 0 else "−"}{_de(abs(gv) / basis * 100 if basis else 0, 2)} % seit {seit}'),
        ("Heute", f'<span class="{"pl-gut" if heute_diff >= 0 else "pl-schlecht"}">'
                  f'{"+" if heute_diff >= 0 else "−"}{_de(abs(heute_diff), 2)} €</span>', "gegenüber Vortag"),
        ("Positionen", str(len(pos)), f"Kaufwert {_de(basis, 2)} €"),
    ])
    for p, akt, akt_w in sorted(berechnet, key=lambda x: -x[2]):
        g = (akt / p["kaufkurs"] - 1) * 100 if akt and p["kaufkurs"] else None
        name = f'<b>{_esc(p["name"])}</b><br><span class="pt-sub">' + _esc(
            " · ".join(x for x in (p.get("wkn"), ("aus " + p["teil_von"]) if p.get("teil_von") else "") if x)) + "</span>"
        stueck = _de(p["stueck"], 4).rstrip("0").rstrip(",") if p["stueck"] % 1 else _de(p["stueck"])
        zeilen.append([name, stueck, _de(p["kaufkurs"], 2) + " €",
                       (_de(akt, 2) + " €") if akt else "–", _de(akt_w, 2) + " €",
                       (f'<span class="{"pl-gut" if g >= 0 else "pl-schlecht"}">{"+" if g >= 0 else "−"}'
                        f'{_de(abs(g), 2)} %</span>') if g is not None else "–",
                       _de(akt_w / gesamt * 100 if gesamt else 0, 1) + " %"])
    if cash:
        zeilen.append(["<b>Cash</b><br><span class=\"pt-sub\">Reserve und Rest</span>", "–", "–", "–",
                       _de(cash, 2) + " €", "–", _de(cash / gesamt * 100 if gesamt else 0, 1) + " %"])
    _tabelle(["Position", "Stück", "Kaufkurs", "Kurs", "Wert", "G/V", "Anteil"], zeilen)
    st.caption("Kurse von ls-tc.de, aktualisiert mit den übrigen Kursen der App.")
    with st.expander("Musterdepot löschen", expanded=False):
        sicher = st.checkbox(f"Ja, „{wahl}“ endgültig löschen", key="md_loeschen_ok")
        if st.button("🗑️ Löschen", key="md_loeschen", disabled=not sicher, width="stretch"):
            def _loeschen(d):
                dep = d.get("depots") if isinstance(d.get("depots"), dict) else {}
                if wahl not in dep:
                    return None
                dep.pop(wahl, None)
                d["depots"] = dep
                if d.get("aktiv") == wahl or d.get("aktiv") not in dep:
                    d["aktiv"] = next(iter(dep), None)
                return d
            if _aendern_speichern(h, _pfad(h, PFAD_MUSTERDEPOT), _loeschen,
                                  f"planer: musterdepot {wahl} geloescht [skip ci]"):
                if h.get("chronik"):
                    try:
                        h["chronik"]("planer", f"🗑️ Musterdepot gelöscht: {wahl}")
                    except Exception:
                        pass
                st.success("Gelöscht.")
                st.rerun()
            else:
                st.error("Löschen nicht möglich – GitHub-Speicher nicht erreichbar.")


# ===========================================================================
# Einstieg
# ===========================================================================
def render(h):
    st.markdown(CSS + WZ_CSS, unsafe_allow_html=True)
    m = _modell(h)
    name = st.session_state.get("planer_name")
    st.markdown(f'<div class="abschnitt">💼 Portfolio-Planer{" · " + _esc(name) if name else ""}</div>',
                unsafe_allow_html=True)
    st.caption(f"Planer-Version {PLANER_VERSION} · Rechenkern {getattr(E, 'ENGINE_VERSION', 'alt')}")
    _hinweis("Szenariorechnung / keine Prognose – alle Renditen sind Annahmen oder historische Ausgangswerte, "
             "keine Erwartung und keine Anlageempfehlung.")

    with st.container(key="pl_nav_ansicht"):
        ansicht = st.pills("Ansicht", ANSICHTEN, default=ANSICHTEN[1], key="pl_ansicht",
                           help="Schritt für Schritt: geführter Ablauf mit Vorschau. Alle Bereiche: alle Seiten direkt "
                                "(für Erfahrene) – beide arbeiten mit demselben Modell.") or ANSICHTEN[1]
    gefuehrt = ansicht == ANSICHTEN[0]
    status_platz = st.empty()
    platz = {"bilanz": None, "kpi": None}
    if gefuehrt:
        with st.container(key="pl_nav_schritt"):
            schritt = st.pills("Schritt", list(range(len(SCHRITTE))), default=0, key="pl_schritt",
                               format_func=lambda i: f"{i + 1} {SCHRITTE[i]['icon']} {SCHRITTE[i]['titel']}",
                               label_visibility="collapsed")
        schritt = 0 if schritt is None else int(schritt)
        stepper_platz = st.empty()
        warn_platz = st.empty()
        mobil = _smartphone()
        if mobil:
            vorschau_platz = st.empty()
            inhalt = st.container()
        else:
            inhalt, rechts = st.columns([2.2, 1], gap="medium")
            vorschau_platz = rechts.empty()
        seiten_liste = SCHRITTE[schritt]["seiten"]
        with inhalt:
            _schritt_kopf(schritt)
            unter = None
            if seiten_liste:
                with st.container(key="pl_nav_unter"):
                    unter = st.pills("Unterseite", seiten_liste, default=seiten_liste[0],
                                     key=f"pl_wz_seite_{schritt}", label_visibility="collapsed") or seiten_liste[0]
    else:
        platz["bilanz"] = _rahmen(m)
        platz["kpi"] = st.empty()
        warn_platz = st.empty()
        with st.container(key="pl_nav_bereich"):
            haupt = st.pills("Bereich", HAUPT, default=HAUPT[0], key="pl_haupt") or HAUPT[0]
            unter = None
            if UNTER[haupt]:
                unter = st.pills("Unterseite", UNTER[haupt], default=UNTER[haupt][0],
                                 key=f"pl_unter_{HAUPT.index(haupt)}", label_visibility="collapsed") \
                    or UNTER[haupt][0]

    with st.spinner("Lade historische Daten …"):
        try:
            hist_assets, hist_korb = _historie(m, h)
        except Exception:
            hist_assets, hist_korb = {}, {}
        fund, fund_stand = _fundamentaldaten(m, h)
    je_score, korb_score = _scores(m, fund)
    historie = _layer(m, hist_assets, hist_korb, fund)
    # Annahmen automatisch aus den bisherigen Renditen p.a. (nur automatisch
    # gefuehrte - selbst eingetragene Werte bleiben)
    E.annahmen_aus_historie(m, historie)
    st.session_state["planer_historie"] = historie

    # Eingaben des Bereichs zuerst (sie aendern das Modell), danach rechnen
    R = _rechne(m, historie, korb_score)
    if _auto_gewichtung(m, R):
        R = _rechne(m, historie, korb_score)
    if (m.get("kaufplan") or {}).get("runden") and _auf_stuecke(m, hist_assets, hist_korb)[0]:
        R = _rechne(m, historie, korb_score)
    if _ziel_feinabgleich(m, R):
        R = _rechne(m, historie, korb_score)

    def _gewichte_seite():
        with st.expander("📐 Gewichtung je Kategorie begrenzen (Wikifolios, ETFs, Aktien, Reserve …)",
                         expanded=False):
            _regeln_editor(m, "gw_")
        _b_gewichtung(m, R)

    def _rahmen_seite():
        platz["bilanz"] = _rahmen(m, eingebettet=True)
        _abschnitt("Ergebnis auf einen Blick")
        platz["kpi"] = st.empty()

    seiten = {
        ("🧩 Portfolio", "Bausteine"): lambda: _b_bausteine(m, R, h, hist_assets, hist_korb),
        ("🧩 Portfolio", "Aufteilung"): lambda: _b_aufteilung(m, R),
        ("🧩 Portfolio", "Kaufplan"): lambda: _b_kaufplan(m, R, h, hist_assets, hist_korb),
        ("⚖️ Gewichtung", None): _gewichte_seite,
        ("💳 Kredit", None): lambda: _b_kredit(m, R),
        ("📈 Ergebnis", "Wachstum"): lambda: _b_growth(m, R),
        ("📈 Ergebnis", "Ziel"): lambda: _b_ziel(m, R),
        ("📈 Ergebnis", "Szenarien"): lambda: _b_szenarien(m, R, historie, h),
        ("📈 Ergebnis", "Entnahme"): lambda: _b_entnahme(m, R),
        ("⚠️ Risiko", "Konzentration"): lambda: _b_risiko(m, R, historie),
        ("⚠️ Risiko", "Sensitivität"): lambda: _b_sensitiv(m, R),
        ("⚠️ Risiko", "Stress & Reserve"): lambda: _b_reserve(m, R),
        ("🔬 Analyse", "Aktienkorb"): lambda: _b_korb(m, R, fund, fund_stand, je_score, korb_score, hist_korb),
        ("🔬 Analyse", "Wikifolios"): lambda: _b_wiki(m, R, hist_assets),
        ("🗂️ Daten", "Annahmen & Quellen"): lambda: _b_annahmen(m, R, historie, hist_assets),
        ("🗂️ Daten", "Gespeicherte Modelle"): lambda: _b_modelle(m, R, historie, h),
    }
    if gefuehrt:
        # gleiche Seiten, nur in der Reihenfolge des Ablaufs
        wz = {
            (0, None): _rahmen_seite,
            (1, "Auswahl"): seiten[("🧩 Portfolio", "Bausteine")],
            (1, "Aktienkorb"): seiten[("🔬 Analyse", "Aktienkorb")],
            (1, "Wikifolios"): seiten[("🔬 Analyse", "Wikifolios")],
            (2, "Gewichte"): _gewichte_seite,
            (2, "Aufteilung"): seiten[("🧩 Portfolio", "Aufteilung")],
            (2, "Kaufplan"): seiten[("🧩 Portfolio", "Kaufplan")],
            (3, "Kredit"): seiten[("💳 Kredit", None)],
            (3, "Konzentration"): seiten[("⚠️ Risiko", "Konzentration")],
            (3, "Sensitivität"): seiten[("⚠️ Risiko", "Sensitivität")],
            (3, "Stress & Reserve"): seiten[("⚠️ Risiko", "Stress & Reserve")],
            (3, "Annahmen & Quellen"): seiten[("🗂️ Daten", "Annahmen & Quellen")],
            (4, "Überblick"): lambda: _b_ueberblick(m, R, platz),
            (4, "Wachstum"): seiten[("📈 Ergebnis", "Wachstum")],
            (4, "Ziel"): seiten[("📈 Ergebnis", "Ziel")],
            (4, "Szenarien"): seiten[("📈 Ergebnis", "Szenarien")],
            (4, "Entnahme"): seiten[("📈 Ergebnis", "Entnahme")],
            (4, "Speichern"): seiten[("🗂️ Daten", "Gespeicherte Modelle")],
        }
        with inhalt:
            wz[(schritt, unter)]()
    else:
        seiten[(haupt, unter)]()

    # KPIs mit dem Stand NACH den Eingaben
    je_score, korb_score = _scores(m, fund)
    R = _rechne(m, historie, korb_score)
    if _auto_gewichtung(m, R):
        R = _rechne(m, historie, korb_score)
    if (m.get("kaufplan") or {}).get("runden") and _auf_stuecke(m, hist_assets, hist_korb)[0]:
        R = _rechne(m, historie, korb_score)
    if _ziel_feinabgleich(m, R):
        R = _rechne(m, historie, korb_score)
    if platz["kpi"] is not None:
        _kpis(platz["kpi"], m, R)
    if platz["bilanz"] is not None:
        try:
            _monatsbilanz_anzeigen(platz["bilanz"], m, R)
        except Exception as ex:
            platz["bilanz"].caption(f"Monatsbilanz nicht berechenbar: {ex}")
    _gewichtswarnung(warn_platz, m, leer_zeigen=not gefuehrt)
    if gefuehrt:
        pruef = _pruefungen(m, R)
        stepper_platz.markdown(_stepper_html(pruef, schritt), unsafe_allow_html=True)
        with vorschau_platz.container():
            if mobil:
                summe = E.gewichte_summe(m)
                with st.expander(f"📊 Portfolio-Vorschau · {len([1 for g in E.gewichte(m).values() if g > 0])} "
                                 f"Bausteine · {_de(summe, 1)} %", expanded=False):
                    _vorschau(m, R, mobil=True)
            else:
                with st.container(border=True):
                    _vorschau(m, R)
        with inhalt:
            st.divider()
            with st.container(key="pl_nav_knoepfe"):
                _schritt_navigation(pruef, schritt)

    status = _auto_speichern(m, h)
    if status:
        art, sz_name, zeit = status
        text = (f"✓ Automatisch gespeichert als „{sz_name}“ · {zeit} Uhr" if art == "ok" else
                "⚠ Dein gespeichertes Modell war beim Öffnen nicht lesbar – damit es nicht überschrieben wird, "
                "wird gerade nicht automatisch gespeichert. Bitte die Seite neu laden." if art == "lesefehler" else
                "⚠ Automatische Speicherung nicht möglich (GitHub-Speicher nicht erreichbar) – "
                "Änderungen gelten nur bis zum Neuladen.")
        status_platz.markdown(f'<div class="pl-hinweis">{_esc(text)}</div>', unsafe_allow_html=True)
