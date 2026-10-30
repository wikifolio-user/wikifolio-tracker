"""Altersteilzeit & Rentenplanung - Oberflaeche (Rechenlogik in atz_rechner/, hier nur Anzeige).

Eingaben stehen in Reitern (handytauglich), Kennzahlen oben, darunter Zeitstrahl, Ampel, Verlauf,
Vergleich, Jahrestabelle (CSV), Szenarien (JSON) und die editierbaren Parameter.
Eingaben werden nur in der Sitzung gehalten und per JSON-Datei gespeichert - nichts landet im Repository.
"""
import copy
import datetime
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import formate as FMT
import schritte
import ui_stil as UI
from atz_rechner import kapital as K
from atz_rechner import parameter as PM
from atz_rechner import plan as PL
from atz_rechner import rente as R
from atz_rechner import steuer as S

P = "atz_"
SCHATTEN = "_atz_werte"      # letzte Eingaben (Widgets verlieren ihren Wert, wenn die Ansicht wechselt)
VERSION = "_atz_ver"         # Neuaufbau der Tabellen-Editoren nach dem Laden eines Szenarios
SZENARIEN = "_atz_szenarien"
PARAM = "_atz_param"         # eigene Parameterwerte {schluessel: wert}
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
FARBEN = {"arbeit": "#64748B", "atz_arbeit": "#7C9CFF", "atz_frei": "#22D3EE", "atz": "#7C9CFF",
          "sperrzeit": "#F87171", "alg": "#F59E0B", "luecke": "#EF4444", "rente": "#34D399"}

CSS = """<style>
.atz-zeit { display:flex; width:100%; height:30px; border-radius:10px; overflow:hidden; margin:6px 0 8px; }
.atz-zeit div { height:100%; min-width:3px; }
.atz-legende { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:.82rem; line-height:1.35; }
.atz-legende span { display:inline-flex; align-items:center; gap:6px; }
.atz-legende i { width:12px; height:12px; border-radius:3px; display:inline-block; flex:none; }
.atz-hinweis { font-size:.8rem; opacity:.85; }
</style>"""


def _eur(x, nk=0):
    return FMT.eur(x, nk)


def _datum(i):
    j, m = R.jahr_monat(i)
    return f"{m:02d}/{j}"


# ---------------------------------------------------------------------------
# Eingabefelder (Startwert aus dem Schatten-Speicher, danach gilt der Widget-Wert)
# ---------------------------------------------------------------------------
def _start(key, mini=None, maxi=None, optionen=None):
    k = P + key
    if k not in st.session_state:
        st.session_state[k] = copy.deepcopy((st.session_state.get(SCHATTEN) or {}).get(key, PL.STANDARD[key]))
    v = st.session_state[k]
    if optionen is not None and v not in optionen:
        st.session_state[k] = PL.STANDARD[key] if PL.STANDARD[key] in optionen else list(optionen)[0]
    if mini is not None and isinstance(v, (int, float)) and not isinstance(v, bool):
        st.session_state[k] = type(mini)(min(max(v, mini), maxi))
    return k


def _zahl(ort, key, label, mini, maxi, step, fmt=None, hilfe=None):
    k = _start(key, mini, maxi)
    return ort.number_input(label, min_value=mini, max_value=maxi, step=step, key=k, help=hilfe,
                            format=fmt or ("%d" if isinstance(step, int) else "%.2f"))


def _wahl(ort, key, label, optionen, hilfe=None):
    liste = list(optionen)
    k = _start(key, optionen=liste)
    namen = optionen if isinstance(optionen, dict) else None
    return ort.selectbox(label, liste, key=k, help=hilfe, format_func=(lambda x: namen[x]) if namen else str)


def _schalter(ort, key, label, hilfe=None):
    return ort.toggle(label, key=_start(key), help=hilfe)


def _editor(ort, key, spalten, konfig):
    """Dynamische Liste (Zeilen hinzufuegen/loeschen). Startdaten bleiben stabil, solange der Editor lebt."""
    ver = st.session_state.get(VERSION, 0)
    ed = f"{P}ed_{key}_{ver}"
    basis = f"_atz_basis_{key}"
    if ed not in st.session_state or basis not in st.session_state:
        st.session_state[basis] = copy.deepcopy((st.session_state.get(SCHATTEN) or {}).get(key, PL.STANDARD[key]))
    df = pd.DataFrame(st.session_state[basis], columns=list(spalten))
    aus = ort.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=ed,
                          column_config={s: konfig[s] for s in spalten})
    zeilen = []
    for z in aus.to_dict("records"):
        z = {k: (None if (v is None or (isinstance(v, float) and v != v)) else v) for k, v in z.items()}
        if any(v not in (None, "") for v in z.values()):
            zeilen.append(z)
    return zeilen


def _eingaben(p, depotwert):
    """Alle Eingaben in Reitern. -> dict (wie PL.STANDARD)."""
    e = {}
    reiter = st.tabs(["👤 Person", "🏛️ Rente", "⏳ Altersteilzeit", "🏢 Vorsorge", "💰 Kapital", "🧾 Weiteres"])

    # 1) Person
    t = reiter[0]
    c1, c2 = t.columns(2)
    e["geb_jahr"] = _zahl(c1, "geb_jahr", "Geburtsjahr", 1945, 2000, 1)
    e["geb_monat"] = _wahl(c2, "geb_monat", "Geburtsmonat", {i + 1: m for i, m in enumerate(MONATE)})
    e["geb_erster"] = _schalter(t, "geb_erster", "Am 1. eines Monats geboren",
                                "Dann beginnt die Rente bereits im Geburtsmonat.")
    c1, c2 = t.columns(2)
    e["steuerklasse"] = _wahl(c1, "steuerklasse", "Steuerklasse", PL.STEUERKLASSEN,
                              "III, IV oder V = verheiratet → gemeinsame Veranlagung (Splitting). Gerechnet wird die "
                              "Jahressteuer; die Steuerklasse verteilt nur den Abzug im Jahr.")
    e["bundesland"] = _wahl(c2, "bundesland", "Bundesland", PM.BUNDESLAENDER,
                            "Kirchensteuer 8 % in Bayern/Baden-Württemberg, sonst 9 %; Pflegeversicherung Sachsen.")
    c1, c2 = t.columns(2)
    e["kirche"] = _schalter(c1, "kirche", "Kirchensteuer")
    e["kinder"] = _schalter(c2, "kinder", "Kinder (Pflegeversicherung)",
                            "Ohne Kinder 0,6 % Zuschlag zur Pflegeversicherung.")
    e["schwerbehindert"] = _schalter(t, "schwerbehindert", "Schwerbehinderung (GdB ≥ 50)")
    e["kv_art"] = _wahl(t, "kv_art", "Krankenversicherung",
                        {"gesetzlich": "Gesetzlich", "privat": "Privat"})
    if e["kv_art"] == "gesetzlich":
        e["kvdr"] = _schalter(t, "kvdr", "Pflichtversichert als Rentner (KVdR)",
                              "Voraussetzung: 9/10 der zweiten Hälfte des Erwerbslebens gesetzlich versichert. "
                              "Sonst freiwillig: Beiträge auf alle Einnahmen (auch Miete, Kapitalerträge).")
    else:
        c1, c2, c3 = t.columns(3)
        e["pkv_beitrag"] = _zahl(c1, "pkv_beitrag", "PKV-Beitrag heute (€/Monat)", 0.0, 5000.0, 10.0, "%.0f")
        e["pkv_rente"] = _zahl(c2, "pkv_rente", "PKV-Beitrag im Ruhestand (€, heute)", 0.0, 5000.0, 10.0, "%.0f",
                               "Ohne Krankentagegeld, ggf. mit Beitragsentlastungstarif.")
        e["pkv_steigerung"] = _zahl(c3, "pkv_steigerung", "Beitragssteigerung (% p. a.)", 0.0, 10.0, 0.5, "%.1f")
    t.markdown("**Bisherige Versicherungszeiten** (laut Versicherungsverlauf)")
    c1, c2 = t.columns(2)
    e["jahre_pflicht"] = _zahl(c1, "jahre_pflicht", "Pflichtbeitragsjahre (inkl. Berufsausbildung)", 0.0, 55.0, 0.5,
                               "%.1f")
    e["jahre_kinder"] = _zahl(c2, "jahre_kinder", "Kindererziehung / Berücksichtigungszeiten", 0.0, 30.0, 0.5, "%.1f",
                              "Je Kind bis zu 10 Jahre Berücksichtigungszeit; zählt für 35 und 45 Jahre.")
    c1, c2, c3 = t.columns(3)
    e["jahre_pflege"] = _zahl(c1, "jahre_pflege", "Pflegezeiten", 0.0, 30.0, 0.5, "%.1f")
    e["jahre_ausbildung"] = _zahl(c2, "jahre_ausbildung", "Schule/Studium ab 17", 0.0, 15.0, 0.5, "%.1f",
                                  "Zählt nur für die 35 Jahre (höchstens 8 Jahre), nicht für 45 Jahre.")
    e["jahre_alg"] = _zahl(c3, "jahre_alg", "ALG I bisher", 0.0, 20.0, 0.5, "%.1f")

    # 2) Rente
    t = reiter[1]
    e["rente_eingabe"] = _wahl(t, "rente_eingabe", "Angabe laut Renteninformation", PL.RENTE_EINGABE,
                               "Steht in der jährlichen Renteninformation bzw. Rentenauskunft der DRV.")
    if e["rente_eingabe"] == "ep":
        e["ep"] = _zahl(t, "ep", "Entgeltpunkte bisher", 0.0, 150.0, 0.5, "%.4f")
    elif e["rente_eingabe"] == "anwartschaft":
        e["anwartschaft"] = _zahl(t, "anwartschaft", "Bisher erreichte Rentenanwartschaft (€/Monat)", 0.0, 6000.0,
                                  10.0, "%.2f")
    else:
        e["prognose"] = _zahl(t, "prognose", "Prognose Regelaltersrente (€/Monat)", 0.0, 8000.0, 10.0, "%.2f",
                              "Die Prognose unterstellt Beiträge wie bisher bis zur Regelaltersgrenze; der Rechner "
                              "zieht die künftigen Punkte ab und rechnet mit Ihrer Planung neu.")
    e["rente_wahl"] = _wahl(t, "rente_wahl", "Rentenbeginn", PL.RENTE_WAHL)
    if e["rente_wahl"] == "wunsch":
        c1, c2 = t.columns(2)
        e["rente_jahr"] = _zahl(c1, "rente_jahr", "Jahr", 2026, 2070, 1)
        e["rente_monat"] = _wahl(c2, "rente_monat", "Monat", {i + 1: m for i, m in enumerate(MONATE)})
    e["ausgleich"] = _schalter(t, "ausgleich", "Abschläge durch Ausgleichszahlung abkaufen (ab 50)",
                               "§ 187a SGB VI: Sonderzahlung an die DRV; als Altersvorsorgeaufwand steuerlich absetzbar.")
    if e["ausgleich"]:
        e["ausgleich_betrag"] = _zahl(t, "ausgleich_betrag", "Betrag (0 = Abschlag vollständig ausgleichen)", 0.0,
                                      500000.0, 1000.0, "%.0f")
    t.info("**Vorher klären:** Rentenauskunft bei der DRV anfordern (ab 55 mit Abschlagsberechnung), "
           "Versicherungskonto klären lassen (Kontenklärung – fehlende Zeiten nachmelden) und eine kostenlose "
           "Beratung der DRV nutzen (Auskunfts- und Beratungsstellen, Telefon 0800 1000 4800, "
           "www.deutsche-rentenversicherung.de).")

    # 3) Altersteilzeit
    t = reiter[2]
    c1, c2 = t.columns(2)
    e["brutto_jahr"] = _zahl(c1, "brutto_jahr", "Bruttogehalt heute (€/Jahr)", 0.0, 500000.0, 1000.0, "%.0f")
    e["lohnsteigerung"] = _zahl(c2, "lohnsteigerung", "Gehaltssteigerung (% p. a.)", 0.0, 10.0, 0.5, "%.1f")
    e["atz_an"] = _schalter(t, "atz_an", "Altersteilzeit planen")
    if e["atz_an"]:
        c1, c2 = t.columns(2)
        e["atz_jahr"] = _zahl(c1, "atz_jahr", "Beginn Jahr", 2026, 2070, 1)
        e["atz_monat"] = _wahl(c2, "atz_monat", "Beginn Monat", {i + 1: m for i, m in enumerate(MONATE)})
        e["atz_auto"] = _schalter(t, "atz_auto", "Dauer bis zum Rentenbeginn (bzw. bis zum Arbeitslosengeld)")
        if not e["atz_auto"]:
            e["atz_dauer"] = _zahl(t, "atz_dauer", "Dauer (Monate)", 1, 120, 1)
        e["atz_modell"] = _wahl(t, "atz_modell", "Modell", PL.ATZ_MODELLE,
                                "Blockmodell: erst Arbeitsphase (Vollzeit), dann Freistellung – Entgelt gleichbleibend. "
                                "Gleichverteilung: durchgehend halbe Arbeitszeit.")
        c1, c2 = t.columns(2)
        e["atz_aufstockung"] = _zahl(c1, "atz_aufstockung", "Aufstockung Arbeitgeber (% des ATZ-Brutto)", 0.0, 100.0,
                                     1.0, "%.0f", f"Gesetzlich mindestens {p['atz_aufstockung_min']:.0f} %, tariflich "
                                                  "oft mehr. Steuerfrei, aber mit Progressionsvorbehalt.")
        e["atz_rv"] = _zahl(c2, "atz_rv", "Zusätzliche RV-Beiträge auf … % des ATZ-Brutto", 0.0, 100.0, 5.0, "%.0f",
                            "Gesetzlich 80 %; zusammen mit dem ATZ-Entgelt meist 90 % der Vollzeit-Rentenpunkte.")
        if e["atz_aufstockung"] < p["atz_aufstockung_min"]:
            t.warning(f"Weniger als {p['atz_aufstockung_min']:.0f} % Aufstockung erfüllt nicht das AltTZG – "
                      "dann ist sie nicht steuerfrei.")
    t.markdown("**Optional**")
    e["abfindung"] = _zahl(t, "abfindung", "Abfindung brutto (€)", 0.0, 2000000.0, 1000.0, "%.0f")
    if e["abfindung"] > 0:
        c1, c2 = t.columns(2)
        e["abfindung_jahr"] = _zahl(c1, "abfindung_jahr", "Auszahlungsjahr", 2026, 2070, 1)
        e["fuenftel"] = _schalter(c2, "fuenftel", "Fünftelregelung")
    e["alg_an"] = _schalter(t, "alg_an", "Arbeitslosengeld als Brücke zur Rente")
    if e["alg_an"]:
        c1, c2 = t.columns(2)
        e["alg_monate"] = _zahl(c1, "alg_monate", "Anspruchsdauer (Monate)", 1, 24, 1,
                                hilfe="Ab 58 Jahren bis zu 24 Monate (bei 48 Monaten Versicherung).")
        e["alg_kind"] = _schalter(c2, "alg_kind", "Mit Kind (67 %)")
        e["alg_sperrzeit"] = _schalter(t, "alg_sperrzeit", "Sperrzeit (Aufhebungsvertrag / Eigenkündigung)")
        t.warning("**Arbeitslosengeld als Brücke:** Nach einem Aufhebungsvertrag droht eine Sperrzeit von 12 Wochen "
                  "(Anspruch −¼), eine Abfindung kann ohne Kündigungsfrist zum Ruhen führen. ALG in den letzten "
                  "2 Jahren vor Rentenbeginn zählt nicht für die 45 Jahre, und eine Rente direkt nach dem ALG ist "
                  "meist eine vorzeitige mit Abschlag. Vorher mit der Agentur für Arbeit klären.")

    # 4) Betriebsrente & Versicherungen
    t = reiter[3]
    t.markdown("**Betriebsrente (bAV)**")
    c1, c2 = t.columns(2)
    e["bav_form"] = _wahl(c1, "bav_form", "Auszahlung", ["Rente", "Kapital"])
    e["bav_betrag"] = _zahl(c2, "bav_betrag", "Betrag (€/Monat bzw. Kapital)", 0.0, 2000000.0, 10.0, "%.0f")
    if e["bav_betrag"] > 0:
        e["bav_weg"] = _wahl(t, "bav_weg", "Durchführungsweg", PL.BAV_WEGE,
                             "Direktzusage/Unterstützungskasse: Versorgungsbezug mit Versorgungsfreibetrag. "
                             "Direktversicherung/Pensionskasse/-fonds: voll steuerpflichtig (§ 22 Nr. 5).")
        c1, c2 = t.columns(2)
        e["bav_jahr"] = _zahl(c1, "bav_jahr", "Beginn Jahr", 2026, 2070, 1)
        e["bav_monat"] = _wahl(c2, "bav_monat", "Beginn Monat", {i + 1: m for i, m in enumerate(MONATE)})
        c1, c2 = t.columns(2)
        e["bav_abschlag"] = _zahl(c1, "bav_abschlag", "Abschlag bei vorzeitigem Bezug (%)", 0.0, 50.0, 0.5, "%.1f")
        if e["bav_form"] == "Rente":
            e["bav_dynamik"] = _zahl(c2, "bav_dynamik", "Anpassung (% p. a.)", 0.0, 5.0, 0.5, "%.1f")
        else:
            e["bav_fuenftel"] = _schalter(c2, "bav_fuenftel", "Fünftelregelung",
                                          "Meist nur bei Direktzusage/Unterstützungskasse möglich.")
        t.caption(f"Kranken-/Pflegeversicherung: voller Beitragssatz; KV-Freibetrag {_eur(p['bav_freibetrag'], 2)}/Monat "
                  "(PV: Freigrenze). Kapital wird 10 Jahre lang mit 1/120 je Monat verbeitragt.")
    t.markdown("**Lebens- & Rentenversicherungen**")
    e["vertraege"] = _editor(t, "vertraege", ["art", "auszahlung", "jahr", "betrag", "eingezahlt", "vertragsbeginn"], {
        "art": st.column_config.SelectboxColumn("Art", options=PL.VERTRAG_ARTEN, required=True, width="medium"),
        "auszahlung": st.column_config.SelectboxColumn("Auszahlung", options=PL.AUSZAHLUNG, required=True),
        "jahr": st.column_config.NumberColumn("Ab Jahr", min_value=2026, max_value=2080, step=1, format="%d"),
        "betrag": st.column_config.NumberColumn("Betrag €", min_value=0, step=100, format="%.0f",
                                                help="Kapital: Auszahlung gesamt · Rente: € je Monat"),
        "eingezahlt": st.column_config.NumberColumn("Eingezahlt €", min_value=0, step=100, format="%.0f",
                                                    help="Summe der Beiträge (für den steuerpflichtigen Ertrag)"),
        "vertragsbeginn": st.column_config.NumberColumn("Vertrag seit", min_value=1960, max_value=2030, step=1,
                                                        format="%d"),
    })
    t.caption("Steuer: Kapital-LV/private RV als Kapital – Altvertrag vor 2005 steuerfrei, sonst Ertrag zur Hälfte "
              "(12 Jahre + ab 62 bzw. 60) oder mit Abgeltungsteuer · als Rente: Ertragsanteil · Riester: voll "
              "(nachgelagert) · Rürup: nur Rente, Besteuerungsanteil wie gesetzliche Rente.")

    # 5) Kapital
    t = reiter[4]
    if depotwert is not None and t.button(f"Depotwert aus dem Dashboard übernehmen ({_eur(depotwert)})",
                                          key=P + "depot_btn"):
        st.session_state[P + "kapital"] = float(round(depotwert))
        st.session_state[P + "einstand"] = min(float(st.session_state.get(P + "einstand", 0.0)), float(round(depotwert)))
    c1, c2 = t.columns(2)
    e["kapital"] = _zahl(c1, "kapital", "Vorhandenes Kapital (€)", 0.0, 50000000.0, 1000.0, "%.0f")
    e["einstand"] = _zahl(c2, "einstand", "davon eingezahlt (Einstand, €)", 0.0, 50000000.0, 1000.0, "%.0f",
                          "Für die Steuer: nur der Gewinnanteil einer Entnahme ist steuerpflichtig.")
    e["sparrate"] = _zahl(t, "sparrate", "Sparrate bis Ende des Erwerbslebens (€/Monat)", 0.0, 100000.0, 50.0, "%.0f")
    e["rendite"] = t.slider("Rendite (% p. a., realistisch)", -5.0, 12.0, step=0.5, key=_start("rendite", -5.0, 12.0))
    c1, c2 = t.columns(2)
    e["spanne"] = c1.slider("Spanne pessimistisch/optimistisch (± %)", 0.0, 5.0, step=0.5,
                            key=_start("spanne", 0.0, 5.0))
    e["inflation"] = c2.slider("Inflation (% p. a.)", 0.0, 8.0, step=0.25, key=_start("inflation", 0.0, 8.0))
    e["teilfreistellung"] = _schalter(t, "teilfreistellung", "Aktienfonds/-ETF (30 % Teilfreistellung)")
    e["entnahme_modus"] = _wahl(t, "entnahme_modus", "Entnahmeplan", K.MODUS_NAMEN)
    if e["entnahme_modus"] == "verzehr":
        e["entnahme_alter"] = _zahl(t, "entnahme_alter", "Kapital aufbrauchen bis Alter", 60, 105, 1)
    elif e["entnahme_modus"] == "fest":
        e["entnahme_fest"] = _zahl(t, "entnahme_fest", "Entnahme (€/Monat)", 0.0, 100000.0, 50.0, "%.0f")
    e["pflegepuffer"] = _zahl(t, "pflegepuffer", "Pflegerisiko-Puffer (€, heute; wird nicht entnommen)", 0.0,
                              5000000.0, 5000.0, "%.0f",
                              "Ein Pflegeplatz kostet im Eigenanteil oft 2.500–3.500 € im Monat.")

    # 6) Weiteres
    t = reiter[5]
    e["bedarf"] = _zahl(t, "bedarf", "Monatlicher Bedarf im Ruhestand (€, heutige Kaufkraft)", 0.0, 100000.0, 50.0,
                        "%.0f", "Ab Ende des Erwerbslebens; wird mit der Inflation fortgeschrieben.")
    c1, c2 = t.columns(2)
    e["miete"] = _zahl(c1, "miete", "Mieteinnahmen nach Kosten (€/Monat)", 0.0, 100000.0, 50.0, "%.0f")
    e["miete_steuer_pct"] = _zahl(c2, "miete_steuer_pct", "davon steuerpflichtig (%)", 0.0, 100.0, 5.0, "%.0f",
                                  "Nach Abschreibung (AfA) ist oft nur ein Teil steuerpflichtig.")
    c1, c2 = t.columns(2)
    e["hinzuverdienst"] = _zahl(c1, "hinzuverdienst", "Hinzuverdienst in der Rente (€/Monat)", 0.0, 50000.0, 50.0,
                                "%.0f", f"Seit 2023 unbegrenzt erlaubt. Bis {_eur(p['minijob_grenze'])} als Minijob "
                                        "(pauschal, steuerfrei gerechnet).")
    e["hinzuverdienst_bis"] = _zahl(c2, "hinzuverdienst_bis", "bis Alter", 60, 90, 1)
    if e["steuerklasse"] in PL.VERHEIRATET:
        t.markdown("**Partner/in** (gemeinsame Veranlagung)")
        c1, c2 = t.columns(2)
        e["partner_lohn"] = _zahl(c1, "partner_lohn", "Einkommen bis zur Rente (brutto €/Monat)", 0.0, 50000.0, 50.0,
                                  "%.0f")
        e["partner_art"] = _wahl(c2, "partner_art", "Danach", PL.PARTNER_ARTEN)
        c1, c2 = t.columns(2)
        e["partner_rente"] = _zahl(c1, "partner_rente", "Rente/Pension (brutto €/Monat)", 0.0, 50000.0, 50.0, "%.0f")
        e["partner_jahr"] = _zahl(c2, "partner_jahr", "ab Jahr", 2026, 2070, 1)
        if e["partner_art"] != "rente":
            e["partner_kv"] = _zahl(t, "partner_kv", "Kranken-/Pflegeversicherung Partner/in (€/Monat)", 0.0, 3000.0,
                                    10.0, "%.0f")
    else:
        t.caption("Partnerrente/-pension: bei Steuerklasse III, IV oder V (Reiter Person) eingeben.")
    t.markdown("**Kredite mit Restlaufzeit**")
    e["kredite"] = _editor(t, "kredite", ["name", "rate", "bis_jahr"], {
        "name": st.column_config.TextColumn("Bezeichnung"),
        "rate": st.column_config.NumberColumn("Rate €/Monat", min_value=0, step=10, format="%.0f"),
        "bis_jahr": st.column_config.NumberColumn("bis Jahr", min_value=2026, max_value=2080, step=1, format="%d"),
    })
    t.markdown("**Größere Einmalausgaben**")
    e["einmal"] = _editor(t, "einmal", ["name", "jahr", "betrag"], {
        "name": st.column_config.TextColumn("Bezeichnung"),
        "jahr": st.column_config.NumberColumn("Jahr", min_value=2026, max_value=2080, step=1, format="%d"),
        "betrag": st.column_config.NumberColumn("Betrag €", min_value=0, step=500, format="%.0f"),
    })
    e["tarif_index"] = _schalter(t, "tarif_index", "Steuertarif mit der Inflation fortschreiben",
                                 "Ausgleich der kalten Progression wie in den letzten Jahren. Aus: Tarif 2026 bleibt.")
    # nicht angezeigte Felder behalten ihren letzten Wert
    alt = st.session_state.get(SCHATTEN) or {}
    for k, v in PL.STANDARD.items():
        if k not in e:
            e[k] = copy.deepcopy(alt.get(k, v))
    return e


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------
def _kennzahlen(ort, erg, k, regel):
    t = erg["zeit"]
    c1, c2 = ort.columns(2)
    c3, c4 = ort.columns(2)
    alter = R.lebensalter(erg["e"]["geb_jahr"], erg["e"]["geb_monat"], t["rente"], erg["e"]["geb_erster"])
    c1.metric("Rentenbeginn", _datum(t["rente"]), f"mit {R.alter_text(alter)}" +
              (f", −{FMT.pct(100 * t['abschlag'], 1)}" if t["abschlag"] else ", ohne Abschlag"),
              delta_color="off", help=R.NAMEN.get(t["art"], ""))
    c2.metric("Netto/Monat", _eur(k["netto_monat"]), f"{_eur(k['netto_monat_real'])} heute",
              delta_color="off", help=f"Im ersten vollen Rentenjahr {k['voll_jahr']}: alle laufenden Einkünfte "
                                      f"(Rente brutto {_eur(k['rente_brutto'])}) nach Steuern und KV/PV.")
    c3.metric("Lücke/Monat", _eur(k["luecke_monat"]),
              f"{_eur(k['luecke_monat_real'])} heute" if k["luecke_monat"] else "keine", delta_color="off",
              help="Versorgungslücke: Bedarf + Kredite minus Netto-Einkommen im ersten vollen Rentenjahr (ohne Kapitalentnahme).")
    if erg["ausgleich"].get("break_even"):
        be = R.alter_text(erg["ausgleich"]["break_even"])
        c4.metric("Break-even Ausgleich", be, f"Kosten {_eur(erg['ausgleich']['kosten'])}", delta_color="off")
    elif k["break_even"] is not None:
        c4.metric("Break-even", f"{k['break_even']} J.", "später lohnt ab dann",
                  delta_color="off", help="Ab diesem Alter hat die Regelaltersrente (ohne Abschlag, später) in "
                                          "Summe mehr gezahlt als die vorzeitige Rente.")
    else:
        c4.metric("Break-even", "–", "kein früher Beginn", delta_color="off")


def _zeitstrahl(ort, erg):
    t = erg["zeit"]
    h = PL.heute_idx()
    ende = max(t["rente"] + 36, t["regel_idx"] + 12)
    teile = []
    i = h
    aktuell = None
    start = h
    while i <= ende:
        ph = PL.phase(t, i) if i < ende else None
        if ph != aktuell:
            if aktuell is not None:
                teile.append((aktuell, start, i))
            aktuell, start = ph, i
        i += 1
    gesamt = max(ende - h, 1)
    balken = "".join(f'<div title="{PL.PHASEN_NAMEN[ph]}" style="width:{100 * (b - a) / gesamt:.2f}%;'
                     f'background:{FARBEN[ph]}"></div>' for ph, a, b in teile)
    legende = "".join(f'<span><i style="background:{FARBEN[ph]}"></i>{PL.PHASEN_NAMEN[ph]}: {_datum(a)}'
                      + (f" – {_datum(b - 1)}" if ph != "rente" else " →") + "</span>" for ph, a, b in teile)
    ort.markdown(f'{CSS}<div class="atz-zeit">{balken}</div><div class="atz-legende">{legende}</div>',
                 unsafe_allow_html=True)


def _ampel(ort, erg):
    farbe, text = PL.ampel(erg)
    {"gruen": ort.success, "gelb": ort.warning, "rot": ort.error}[farbe](
        {"gruen": "🟢 ", "gelb": "🟡 ", "rot": "🔴 "}[farbe] + text)


def _charts(ort, erg, szen):
    z = erg["zeilen"]
    x = [r["jahr"] for r in z]
    alter = [r["alter"] for r in z]
    fig = go.Figure()
    fig.add_bar(x=x, y=[r["netto"] / max(r["monate"], 1) for r in z], name="Netto/Monat nominal",
                customdata=alter, hovertemplate="%{x} (Alter %{customdata}): %{y:,.0f} €<extra></extra>")
    fig.add_scatter(x=x, y=[r["netto"] / max(r["monate"], 1) / r["inflationsfaktor"] for r in z],
                    name="in heutiger Kaufkraft", mode="lines", hovertemplate="%{x}: %{y:,.0f} €<extra></extra>")
    fig.add_scatter(x=x, y=[r["ausgaben"] / r["post_monate"] if r["post_monate"] else None for r in z],
                    name="Bedarf + Kredite", mode="lines", line=dict(dash="dot"),
                    hovertemplate="%{x}: %{y:,.0f} €<extra></extra>")
    fig.update_layout(title="Netto-Einkommen je Monat", height=360, barmode="overlay",
                      legend=dict(orientation="h", y=-0.2), margin=dict(l=10, r=10, t=40, b=10))
    ort.plotly_chart(UI.chart_stil(fig), width="stretch", key=P + "ch_netto", config={"displayModeBar": False})

    fig = go.Figure()
    for name, e2 in szen.items():
        zz = e2["zeilen"]
        fig.add_scatter(x=x, y=[r["kapital"] for r in zz], name=f"{name} nominal", mode="lines",
                        line=dict(width=3 if name == "realistisch" else 1.5),
                        hovertemplate="%{x}: %{y:,.0f} €<extra></extra>")
    fig.add_scatter(x=x, y=[r["kapital_real"] for r in szen["realistisch"]["zeilen"]], name="realistisch, heutige Kaufkraft",
                    mode="lines", line=dict(dash="dot"), hovertemplate="%{x}: %{y:,.0f} €<extra></extra>")
    fig.update_layout(title="Kapitalverlauf", height=360, legend=dict(orientation="h", y=-0.2),
                      margin=dict(l=10, r=10, t=40, b=10))
    ort.plotly_chart(UI.chart_stil(fig), width="stretch", key=P + "ch_kapital", config={"displayModeBar": False})
    zeilen = []
    for name, e2 in szen.items():
        leer = e2["leer_ab"]
        zeilen.append({"Szenario": f"{name} ({FMT.pct(100 * e2['rendite'], 1)})",
                       "Kapital mit 95": _eur(e2["zeilen"][-1]["kapital"]),
                       "heutige Kaufkraft": _eur(e2["zeilen"][-1]["kapital_real"]),
                       "Geld reicht": f"bis Alter {leer}" if leer is not None else "bis über 95"})
    ort.dataframe(pd.DataFrame(zeilen), hide_index=True, width="stretch")


def _vergleich(ort, plan_erg, regel_erg):
    v = PL.vergleich_tabelle(plan_erg, regel_erg)
    tp, tr = plan_erg["zeit"], regel_erg["zeit"]
    c1, c2 = ort.columns(2)
    c1.metric("Planung: Rente", _eur(plan_erg["rente_start_brutto"]), f"ab {_datum(tp['rente'])}",
              delta_color="off")
    c2.metric("Regelalter: Rente", _eur(regel_erg["rente_start_brutto"]), f"ab {_datum(tr['rente'])}",
              delta_color="off")
    ende = v[-1]
    ort.caption(f"Kumulierte Netto-Differenz bis 95: **{_eur(ende['diff_kumuliert'])}** "
                f"({'mehr' if ende['diff_kumuliert'] >= 0 else 'weniger'} mit Ihrer Planung) · "
                f"Kapital mit 95: {_eur(ende['kapital_plan'])} gegenüber {_eur(ende['kapital_regel'])}.")
    fig = go.Figure()
    fig.add_bar(x=[r["jahr"] for r in v], y=[r["diff_monat"] for r in v], name="Differenz je Monat",
                hovertemplate="%{x}: %{y:,.0f} €<extra></extra>")
    fig.add_scatter(x=[r["jahr"] for r in v], y=[r["diff_kumuliert"] for r in v], name="kumuliert", yaxis="y2",
                    mode="lines", hovertemplate="%{x}: %{y:,.0f} €<extra></extra>")
    fig.update_layout(title="Planung minus Regelaltersrente (netto)", height=340, legend=dict(orientation="h", y=-0.2),
                      yaxis2=dict(overlaying="y", side="right", showgrid=False), margin=dict(l=10, r=10, t=40, b=10))
    ort.plotly_chart(UI.chart_stil(fig), width="stretch", key=P + "ch_vgl", config={"displayModeBar": False})


TABELLE = [("jahr", "Jahr"), ("alter", "Alter"), ("phase", "Phase"), ("lohn", "Lohn/ATZ"), ("aufstockung", "Aufstockung"),
           ("alg", "ALG"), ("rente", "Gesetzl. Rente"), ("bav", "Betriebsrente"), ("versicherungen", "Versicherungen"),
           ("miete", "Miete"), ("hinzuverdienst", "Hinzuverdienst"), ("partner", "Partner"),
           ("einmal_brutto", "Einmalzahlungen"), ("steuer", "Steuern"), ("sozial", "KV/PV/SV"), ("netto", "Netto laufend"),
           ("einmal_netto", "Einmal netto"), ("ausgaben", "Bedarf + Kredite"), ("einmal_ausgaben", "Einmalausgaben"),
           ("entnahme", "Entnahme"), ("kapital", "Kapital"), ("kapital_real", "Kapital (heute)")]


def _tabelle(ort, erg):
    df = pd.DataFrame([{n: z[k] for k, n in TABELLE} for z in erg["zeilen"]])
    leer = [n for k, n in TABELLE[3:] if k not in ("kapital", "kapital_real", "steuer", "sozial", "netto")
            and not df[n].abs().gt(0.5).any()]
    sicht = df.drop(columns=leer)
    konfig = {n: st.column_config.NumberColumn(n, format="%.0f") for n in sicht.columns if n not in ("Jahr", "Alter", "Phase")}
    konfig["Jahr"] = st.column_config.NumberColumn("Jahr", format="%d", pinned=True)
    ort.dataframe(sicht, hide_index=True, width="stretch", height=420, column_config=konfig)
    csv = df.round(2).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    ort.download_button("⬇️ Tabelle als CSV", csv, file_name="rentenplanung.csv", mime="text/csv", key=P + "csv")


def _details(ort, e, p, erg):
    t = erg["zeit"]
    arten = PL.rentenarten(e, p)
    zeilen = []
    for a in arten:
        frueh = a["frueh_idx"] != a["frei_idx"]
        zeilen.append({"Rentenart": a["name"],
                       "abschlagsfrei ab": f"{_datum(a['frei_idx'])} ({R.alter_text(a['frei_alter'])})",
                       "frühestens ab": (f"{_datum(a['frueh_idx'])} ({R.alter_text(a['frueh_alter'])}, "
                                         f"−{FMT.pct(100 * a['max_abschlag'], 1)})") if frueh else "–",
                       "Wartezeit": f"{a['jahre']:.1f} von {a['wartezeit']} J. {'✅' if a['erfuellt'] else '❌'}"})
    ort.dataframe(pd.DataFrame(zeilen), hide_index=True, width="stretch")
    ort.caption(f"Wartezeiten zum geplanten Rentenbeginn {_datum(t['rente'])} hochgerechnet (Beschäftigung/ATZ bis "
                f"dahin). Entgeltpunkte: heute {erg['ep_heute']:.2f} + bis Rentenbeginn {erg['ep_neu']:.2f}"
                + (f" + Ausgleich {erg['ausgleich']['ep']:.2f}" if erg["ausgleich"]["ep"] else "")
                + f" = {erg['ep_summe']:.2f}.")
    for w in t["warnungen"]:
        ort.warning(w)

    if e["atz_an"]:
        vorher, waehrend = PL.netto_vorher_waehrend(e, p)
        ort.markdown("**Netto vorher vs. während Altersteilzeit** (Werte 2026, Monat)")
        df = pd.DataFrame([
            {"": "Brutto", "Vollzeit": _eur(vorher["brutto"]), "Altersteilzeit": _eur(waehrend["brutto"])},
            {"": "+ Aufstockung (steuerfrei)", "Vollzeit": "–", "Altersteilzeit": _eur(waehrend["steuerfrei"])},
            {"": "− Sozialversicherung", "Vollzeit": _eur(vorher["sv"]), "Altersteilzeit": _eur(waehrend["sv"])},
            {"": "− Steuern", "Vollzeit": _eur(vorher["steuer"]), "Altersteilzeit": _eur(waehrend["steuer"])},
            {"": "= Netto", "Vollzeit": _eur(vorher["netto"]), "Altersteilzeit": _eur(waehrend["netto"])},
        ])
        ort.dataframe(df, hide_index=True, width="stretch")
        ort.caption(f"Netto während ATZ: {FMT.pct(100 * waehrend['netto'] / vorher['netto'] if vorher['netto'] else 0, 0)} "
                    "des bisherigen Nettos. Steuer inkl. Progressionsvorbehalt der Aufstockung (Jahressteuer/12). "
                    "Blockmodell: Wertguthaben muss gegen Insolvenz gesichert sein (§ 8a AltTZG).")
    if erg["alg_monat"]:
        ort.caption(f"Geschätztes Arbeitslosengeld: {_eur(erg['alg_monat'])}/Monat (steuerfrei, Progressionsvorbehalt), "
                    f"{_datum(t['alg_von'])} – {_datum(t['alg_bis'] - 1)}.")
    a = erg["ausgleich"]
    if a["kosten"]:
        ort.markdown("**Ausgleichszahlung**")
        ort.caption(f"Zahlung {a['jahr']}: {_eur(a['kosten'])} (voller Ausgleich {_eur(a['voll'])}) → "
                    f"+{a['ep']:.2f} Entgeltpunkte, {_eur(a['mehr_rente'])} mehr Rente brutto/Monat. "
                    + (f"Break-even mit {R.alter_text(a['break_even'])} (brutto, mit Rentenanpassung)."
                       if a["break_even"] else "Kein Break-even innerhalb von 50 Jahren.")
                    + " Die Zahlung ist als Altersvorsorgeaufwand absetzbar (Höchstbetrag) – mehrere Teilzahlungen "
                      "über Jahre verteilen kann Steuern sparen.")
    if e["steuerklasse"] in PL.VERHEIRATET and e["partner_rente"] > 0 and e["partner_art"] == "rente":
        eigene = erg["rente_start_brutto"] * 0.86
        w = R.witwenrente(e["partner_rente"], eigene, p)
        ort.markdown("**Hinterbliebenenrente** (Info, nicht im Verlauf)")
        ort.caption(f"Stirbt Ihr/e Partner/in: große Witwen-/Witwerrente {_eur(w['voll'])} (55 %), abzüglich "
                    f"Einkommensanrechnung {_eur(w['anrechnung'])} (40 % über {_eur(w['freibetrag'], 2)}) → "
                    f"ca. {_eur(w['zahlbetrag'])}/Monat (heutige Werte). Im Sterbevierteljahr volle Rente.")


CHECKLISTE = [
    "Rentenauskunft mit Abschlagsberechnung bei der DRV anfordern (ab 55)",
    "Versicherungskonto klären (Kontenklärung) – fehlende Ausbildungs-, Kinder- und Pflegezeiten nachmelden",
    "Kostenlose DRV-Beratung nutzen (Termin über 0800 1000 4800 oder online)",
    "Tarifvertrag bzw. Betriebsvereinbarung zur Altersteilzeit prüfen (Aufstockung, RV-Beiträge, Insolvenzschutz)",
    "Betriebsrente: Leistungsausweis anfordern, Abschläge bei vorzeitigem Bezug klären",
    "Krankenversicherung im Ruhestand prüfen (KVdR-Vorversicherungszeit 9/10, Beiträge freiwillig/privat)",
    "Bei Abfindung/ALG: Agentur für Arbeit zu Sperr- und Ruhenszeit befragen",
    "Steuerberater/Lohnsteuerhilfe: Fünftelregelung, Progressionsvorbehalt, Ausgleichszahlung",
]


def _checkliste(ort):
    for i, text in enumerate(CHECKLISTE):
        ort.checkbox(text, key=f"{P}chk_{i}")


# ---------------------------------------------------------------------------
# Szenarien & Parameter
# ---------------------------------------------------------------------------
def _laden(werte):
    """Szenario in die Felder uebernehmen (Widget-Werte loeschen, Editoren neu aufbauen)."""
    st.session_state[SCHATTEN] = PL.normalisieren(werte)
    for k in [k for k in st.session_state.keys() if str(k).startswith(P)]:
        del st.session_state[k]
    for k in [k for k in st.session_state.keys() if str(k).startswith("_atz_basis_")]:
        del st.session_state[k]
    st.session_state[VERSION] = st.session_state.get(VERSION, 0) + 1


def _szenarien(ort, e, p, kz):
    sz = st.session_state.setdefault(SZENARIEN, {})
    c1, c2 = ort.columns([3, 1], vertical_alignment="bottom")
    name = c1.text_input("Name", key=P + "sz_name", placeholder="z. B. ATZ ab 2027, Blockmodell")
    if c2.button("💾 Merken", key=P + "sz_merken", width="stretch"):
        n = (name or "").strip() or f"Szenario {len(sz) + 1}"
        sz[n] = copy.deepcopy(e)
        ort.success(f"„{n}“ gemerkt (nur in dieser Sitzung – für später als Datei herunterladen).")
    if sz:
        c1, c2, c3 = ort.columns([3, 1, 1], vertical_alignment="bottom")
        wahl = c1.selectbox("Gemerkte Szenarien", list(sz), key=P + "sz_wahl")
        if c2.button("Laden", key=P + "sz_laden", width="stretch"):
            _laden(sz[wahl])
            st.rerun()
        if c3.button("Löschen", key=P + "sz_del", width="stretch"):
            sz.pop(wahl, None)
            st.rerun()
        zeilen = []
        for n, werte in sz.items():
            a = PL.berechne(werte, p)
            k = PL.kennzahlen(a)
            zeilen.append({"Szenario": n, "Rentenbeginn": _datum(a["zeit"]["rente"]),
                           "Abschlag": FMT.pct(100 * a["zeit"]["abschlag"], 1), "Rente brutto": _eur(k["rente_brutto"]),
                           "Netto/Monat": _eur(k["netto_monat"]), "Lücke/Monat": _eur(k["luecke_monat"]),
                           "Geld reicht": f"bis {k['leer_ab']}" if k["leer_ab"] is not None else "über 95"})
        ort.markdown("**Vergleich der gemerkten Szenarien**")
        ort.dataframe(pd.DataFrame(zeilen), hide_index=True, width="stretch")
    paket = {"typ": "atz-rentenplanung", "stand": datetime.date.today().isoformat(), "aktuell": e,
             "szenarien": sz, "parameter": st.session_state.get(PARAM) or {}}
    ort.download_button("⬇️ Eingaben & Szenarien als Datei (JSON)", json.dumps(paket, ensure_ascii=False, indent=1),
                        file_name="rentenplanung.json", mime="application/json", key=P + "json")
    datei = ort.file_uploader("Gespeicherte Datei laden", type=["json"], key=f"{P}upload_{st.session_state.get(VERSION, 0)}")
    if datei is not None:
        try:
            daten = json.loads(datei.getvalue().decode("utf-8"))
            if not isinstance(daten, dict) or daten.get("typ") != "atz-rentenplanung":
                raise ValueError("keine Datei dieses Rechners")
            st.session_state[SZENARIEN] = {str(k): PL.normalisieren(v) for k, v in (daten.get("szenarien") or {}).items()
                                           if isinstance(v, dict)}
            st.session_state[PARAM] = {k: v for k, v in (daten.get("parameter") or {}).items() if k in PM.PARAMETER}
            _laden(daten.get("aktuell") or {})
            st.rerun()
        except (ValueError, UnicodeDecodeError) as fehler:
            ort.error(f"Datei konnte nicht gelesen werden: {fehler}")


def _parameter(ort):
    eigen = st.session_state.setdefault(PARAM, {})
    ort.caption(f"Stand der Standardwerte: {PM.STAND}. Bitte jährlich prüfen (Rentenanpassung 1. Juli, "
                "Rechengrößen und Steuertarif 1. Januar). Änderungen gelten für diese Sitzung und werden mit der "
                "JSON-Datei gespeichert.")
    df = pd.DataFrame([{"schluessel": k, "Bezeichnung": v[2], "Wert": float(eigen.get(k, v[0])), "Einheit": v[1],
                        "Standard": v[0], "Quelle": v[3]} for k, v in PM.PARAMETER.items()])
    ver = st.session_state.get(VERSION, 0)
    aus = ort.data_editor(df, hide_index=True, width="stretch", height=380, key=f"{P}param_{ver}",
                          disabled=["Bezeichnung", "Einheit", "Standard", "Quelle"],
                          column_order=["Bezeichnung", "Wert", "Einheit", "Standard", "Quelle"],
                          column_config={"Wert": st.column_config.NumberColumn("Wert", format="%.4g"),
                                         "Standard": st.column_config.NumberColumn("Standard", format="%.4g")})
    neu = {r["schluessel"]: float(r["Wert"]) for r in aus.to_dict("records")
           if r["Wert"] == r["Wert"] and abs(float(r["Wert"]) - float(PM.PARAMETER[r["schluessel"]][0])) > 1e-12}
    st.session_state[PARAM] = neu
    if neu:
        ort.caption("Geändert: " + ", ".join(PM.PARAMETER[k][2] for k in neu))
        if ort.button("Alle Parameter auf Standard zurücksetzen", key=P + "param_reset"):
            st.session_state[PARAM] = {}
            st.session_state[VERSION] = ver + 1
            st.rerun()
    ort.caption("Tabellen aus dem Gesetz (im Code, mit Quelle): Altersgrenzen je Jahrgang (§§ 235–236b SGB VI), "
                "Besteuerungsanteil der Rente (§ 22 EStG, ab 2023 +0,5 Pkt./Jahr), Ertragsanteil, "
                "Altersentlastungsbetrag (§ 24a), Versorgungsfreibetrag (§ 19 Abs. 2).")
    return neu


# ---------------------------------------------------------------------------
# Seite
# ---------------------------------------------------------------------------
def seite(h=None):
    h = h or {}
    with st.container(key="atz_seite"):
        _seite(h)


def _seite(h):
    st.markdown(CSS, unsafe_allow_html=True)
    schritte.leiste(st, "atz")
    st.caption("⚠️ Orientierungshilfe mit vereinfachten Annahmen – ersetzt keine Renten-, Steuer- oder Finanzberatung. "
               "Alle Beträge sind Schätzungen.")
    depotwert = None
    try:
        depotwert = h.get("depotwert")() if h.get("depotwert") else None
    except Exception:
        depotwert = None

    schritte.titel(st, "atz", 1)
    oben = st.container()
    schritte.titel(st, "atz", 2)
    p = PM.werte(st.session_state.get(PARAM))
    e = _eingaben(p, depotwert)
    st.session_state[SCHATTEN] = copy.deepcopy(e)

    erg = PL.berechne(e, p)
    regel = PL.berechne(e, p, variante="regel")
    szen = {n: (erg if n == "realistisch" else PL.berechne(e, p, rendite=100 * r))
            for n, r in K.szenarien(e["rendite"] / 100.0, e["spanne"] / 100.0).items()}
    kz = PL.kennzahlen(erg, regel)
    _kennzahlen(oben, erg, kz, regel)

    schritte.titel(st, "atz", 3)
    _zeitstrahl(st, erg)
    _ampel(st, erg)
    with st.expander("Rentenarten, Altersgrenzen und Details", expanded=False):
        _details(st, e, p, erg)

    schritte.titel(st, "atz", 4)
    _charts(st, erg, szen)

    schritte.titel(st, "atz", 5)
    _vergleich(st, erg, regel)

    schritte.titel(st, "atz", 6)
    _tabelle(st, erg)
    with st.expander("✅ Vor der Entscheidung prüfen", expanded=False):
        _checkliste(st)
    with st.expander("💾 Szenarien speichern, laden und vergleichen", expanded=False):
        _szenarien(st, e, p, kz)
    with st.expander("⚙️ Parameter (Stand prüfen)", expanded=False):
        _parameter(st)
    st.caption("Vereinfachungen: Jahressteuer statt Lohnsteuer; Rendite gleichmäßig, Kapitalsteuer erst bei Entnahme "
               "(ohne Vorabpauschale); Gehalt, Rentenwert und Beitragsbemessungsgrenzen steigen gleichmäßig; "
               "Entgeltpunkte ohne Ost/West- und Zurechnungszeiten; Hinterbliebenen- und Erwerbsminderungsrenten "
               "nur als Info.")
