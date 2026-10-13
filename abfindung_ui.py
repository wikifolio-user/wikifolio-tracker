"""Oberflaeche des erweiterten Abfindungsrechners (alle Modelle, Sozialplan, Verhandlung,
Arbeitslosengeld, Szenarien, Bericht). Rechenlogik: abfindung_modelle.py, Steuer: abfindung.py.

Alle Eingaben haben feste Schluessel "abf_..." und werden ueber die Bereiche hinweg gehalten
(siehe halten()); gemerkt wird ueber app.py (RECHNER_EINGABEN "abfindung"), geprueft ueber
FELDER (Typen). Personenbezogen wird nur gespeichert, was gerechnet werden muss (Alter statt
Geburtsdatum)."""
import datetime
import re
from decimal import Decimal

import abfindung as A
import abfindung_modelle as M

NAV = ["🧮 Abfindung berechnen", "📊 Alle Modelle", "💶 Brutto-Netto", "🏭 Sozialplan & Regelwerke",
       "🎚️ Verhandlung", "🧾 ALG & Risiken", "🔀 Szenarien", "📄 Bericht"]

ARTEN = {"ag_betriebsbedingt": "Arbeitgeberkündigung – betriebsbedingt",
         "ag_personenbedingt": "Arbeitgeberkündigung – personenbedingt",
         "ag_verhalten": "Arbeitgeberkündigung – verhaltensbedingt",
         "aufhebung": "Aufhebungsvertrag", "abwicklung": "Abwicklungsvertrag (nach Kündigung)",
         "eigen": "Eigenkündigung", "vergleich": "Gerichtlicher Vergleich (nach Klage)"}
JNU = ["unbekannt", "ja", "nein"]
METHODEN = {"faktor": "Faktor × Monatsverdienst × Jahre", "divisor": "Alter × Jahre × Monatsverdienst ÷ Divisor",
            "punkte": "Punktesystem × Punktwert", "fest": "Festbetrag"}
SONDER_AUSWAHL = list(M.SONDERFAELLE)

# Typen aller gemerkten Felder (fuer das Wiederherstellen gespeicherter Eingaben)
FELDER = {
    "abf_f_alter": int, "abf_f_kinder": int, "abf_f_unterhalt": int, "abf_f_sb": bool, "abf_f_gdb": int,
    "abf_f_rente_m": int, "abf_f_regelalter": bool, "abf_f_beginn": "date", "abf_f_ende": "date",
    "abf_f_zugang": "date", "abf_f_vorzeit": int, "abf_f_frist_auto": bool, "abf_f_frist": int,
    "abf_f_gross": JNU, "abf_f_mon": float, "abf_f_weihn": float, "abf_f_urlaub": float, "abf_f_boni": float,
    "abf_f_prov": float, "abf_f_zul": float, "abf_f_sach": float, "abf_f_sonder": bool, "abf_f_jentgelt": "opt",
    "abf_f_art": list(ARTEN), "abf_f_hinweis": JNU, "abf_f_klage": JNU, "abf_f_drohend": bool,
    "abf_f_wichtig": bool, "abf_f_baend": JNU, "abf_f_ia": JNU, "abf_f_versmon": int, "abf_f_sonderf": "liste",
    "abf_v_eigen": "opt", "abf_v_urlaub": float, "abf_v_gehalt": float, "abf_v_bonus": float,
    "abf_vh_f": float, "abf_vh_ziel_art": ["Netto", "Brutto"], "abf_vh_ziel": "opt", "abf_mo_jahr": int,
    "abf_sz_sprinter": float, "abf_sz_mehr": float, "abf_sz_ende": "date", "abf_sz_faktor": float,
    "abf_in_nach": bool, "abf_in_mv": "opt", "abf_in_masse": "opt", "abf_in_anspr": "opt", "abf_in_mva": int,
    "abf_in_an": bool,
}
for _p in ("auf", "abw", "ver", "zus"):
    FELDER.update({f"abf_v_{_p}_an": bool, f"abf_v_{_p}_betrag": "opt", f"abf_v_{_p}_faktor": "opt"})
FELDER.update({"abf_v_zus_erf": JNU, "abf_v_fw_an": bool, "abf_v_fw_faktor": float, "abf_v_fw_frueh": float,
               "abf_v_fw_unter": float, "abf_v_fw_praemie": float, "abf_v_fw_zuschlag": float,
               "abf_v_tu_an": bool, "abf_v_tu_basis": float, "abf_v_tu_ende_v": "date", "abf_v_tu_beteil": float,
               "abf_v_tu_sv": float, "abf_v_tu_fest": float})
for _p in ("sp", "tv", "bv"):
    FELDER.update({f"abf_{_p}_an": bool, f"abf_{_p}_meth": list(METHODEN), f"abf_{_p}_faktor": float,
                   f"abf_{_p}_div": float, f"abf_{_p}_pw": float, f"abf_{_p}_pj": float, f"abf_{_p}_pa": float,
                   f"abf_{_p}_pk": float, f"abf_{_p}_psb": float, f"abf_{_p}_fest": float, f"abf_{_p}_sockel": float,
                   f"abf_{_p}_kind": float, f"abf_{_p}_unterhalt": float, f"abf_{_p}_sbz": float,
                   f"abf_{_p}_min": float, f"abf_{_p}_max": float, f"abf_{_p}_maxm": float,
                   f"abf_{_p}_staffel": str, f"abf_{_p}_astaffel": str, f"abf_{_p}_rente_pct": float,
                   f"abf_{_p}_budget": "opt", f"abf_{_p}_summe": "opt"})

# Nicht halten/merken: Buttons, Tabellen, Navigation
_NICHT = re.compile(r"_btn$|_tab_|_pdf$|_karte|_form$|^abf_nav$|^abf_fj")


def gueltig(key, wert):
    """-> (ok, wert) fuer gemerkte Werte der neuen Felder."""
    typ = FELDER.get(key)
    if typ is None:
        return False, None
    if typ == "date":
        if isinstance(wert, datetime.date):
            return True, wert
        try:
            return True, datetime.date.fromisoformat(str(wert)[:10])
        except Exception:
            return False, None
    if typ == "opt":
        if wert is None:
            return True, None
        return (True, float(wert)) if isinstance(wert, (int, float)) and not isinstance(wert, bool) else (False, None)
    if typ == "liste":
        return (True, [x for x in wert if x in M.SONDERFAELLE]) if isinstance(wert, list) else (False, None)
    if isinstance(typ, list):
        return wert in typ, wert
    if typ is bool:
        return isinstance(wert, bool), wert
    if typ is str:
        return isinstance(wert, str), wert
    if isinstance(wert, bool) or not isinstance(wert, (int, float)) or wert != wert:
        return False, None
    return True, typ(wert)


def halten(session_state):
    """Werte aller Felder auch dann behalten, wenn ihr Bereich gerade nicht angezeigt wird
    (Streamlit raeumt nicht gezeichnete Felder sonst weg)."""
    for k in list(session_state.keys()):
        k = str(k)
        if k.startswith("abf_") and not _NICHT.search(k):
            try:
                session_state[k] = session_state[k]
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def _s(st, key, wert, name="value"):
    return A._start(st, key, wert, name)


def _jnu(x):
    return {"ja": True, "nein": False}.get(x)


def _staffel(text):
    """"10:0,7; 20:0,9" -> [(10, 0.7), (20, 0.9)] (ungueltige Teile werden ignoriert)."""
    aus = []
    for teil in re.split(r"[;\n]+", text or ""):
        if ":" in teil:
            a, b = teil.split(":", 1)
            try:
                aus.append((float(a.strip().replace(",", ".")), float(b.strip().replace(",", "."))))
            except ValueError:
                pass
    return aus


def _karte(st, nr, titel, text, key):
    import zinsrechner as _zr
    k = st.container(border=True, key=f"abf_karte_{key}")
    k.markdown(_zr._kopf(nr, titel, text).replace('style="margin-top:18px"', ""), unsafe_allow_html=True)
    return k


def _eur(x, nk=0):
    return "–" if x is None else f"{M.de(x, nk)} €"


def fall_aus_session(ss, null=False):
    """Fall-Daten aus den Eingaben (auch wenn der Bereich gerade nicht angezeigt wird)."""
    g = ss.get
    std = 0.0 if null else None

    def z(k, s):
        v = g(k)
        return s if v is None else v
    f = {
        "alter": z("abf_f_alter", 0 if null else 45), "kinder": z("abf_f_kinder", 0), "unterhalt": z("abf_f_unterhalt", 0),
        "schwerbehindert": bool(g("abf_f_sb")), "regelalter": bool(g("abf_f_regelalter")),
        "beginn": g("abf_f_beginn") if g("abf_f_beginn") else (None if null else datetime.date(2016, 1, 1)),
        "ende": g("abf_f_ende") if g("abf_f_ende") else (None if null else datetime.date(2026, 12, 31)),
        "zugang": g("abf_f_zugang"), "vorzeit_monate": z("abf_f_vorzeit", 0),
        "frist_monate": None if g("abf_f_frist_auto", True) else z("abf_f_frist", 0),
        "betrieb_gross": _jnu(g("abf_f_gross", "ja")),
        "brutto_monat": z("abf_f_mon", 0.0 if null else 4000.0), "weihnachtsgeld": z("abf_f_weihn", 0.0),
        "urlaubsgeld": z("abf_f_urlaub", 0.0), "boni": z("abf_f_boni", 0.0), "provisionen": z("abf_f_prov", 0.0),
        "zulagen": z("abf_f_zul", 0.0), "sachbezug": z("abf_f_sach", 0.0),
        "sonder_einbeziehen": g("abf_f_sonder", True),
        "art": g("abf_f_art", "ag_betriebsbedingt"), "hinweis_1a": _jnu(g("abf_f_hinweis", "unbekannt")),
        "klage": _jnu(g("abf_f_klage", "unbekannt")), "drohende_ag_kuendigung": bool(g("abf_f_drohend")),
        "wichtiger_grund": bool(g("abf_f_wichtig")), "betriebsaenderung": _jnu(g("abf_f_baend", "unbekannt")),
        "ia_verletzt": _jnu(g("abf_f_ia", "unbekannt")), "versicherungsmonate": z("abf_f_versmon", 0 if null else 60),
        "sonder": {k: True for k in (g("abf_f_sonderf") or [])},
    }
    if (g("abf_f_sonderf") or []) and "kleinbetrieb" in g("abf_f_sonderf"):
        f["betrieb_gross"] = False
    mv, _ = M.monatsverdienst(f)
    f["jahresentgelt"] = g("abf_f_jentgelt") if g("abf_f_jentgelt") else float(mv) * 12
    return f


def steuer_aus_session(ss, null=False):
    """Steuerdaten wie im Brutto-Netto-Rechner (gleiche Felder)."""
    g = ss.get
    brutto = g("abf_brutto")
    brutto = (0.0 if null else 60000.0) if brutto is None else float(brutto)
    zve = round(brutto * 0.8, -2) if g("abf_zve_auto", True) else float(g("abf_zve1") or 0.0)
    return {"zve": float(zve), "zve2": float(g("abf_zve2") or 0.0), "splitting": str(g("abf_veranl", "Einzeln")).startswith("Zusammen"),
            "kirche": {"keine": 0.0, "8 % (BY, BW)": 0.08, "9 % (übrige Länder)": 0.09}.get(g("abf_kirche", "keine"), 0.0),
            "alg": float(g("abf_alg1") or 0.0), "alg2": float(g("abf_alg2") or 0.0),
            "fuenftel_moeglich": bool(g("abf_fuenftel", True)), "jahr": int(g("abf_jahr1", A.STEUERJAHR)),
            "jahresbrutto": brutto, "vorjahr": g("abf_vorjahr")}


def _regel_aus_session(ss, p):
    g = ss.get
    r = {"methode": g(f"abf_{p}_meth", "faktor"), "faktor": g(f"abf_{p}_faktor", 0.5), "divisor": g(f"abf_{p}_div", 50.0),
         "punktwert": g(f"abf_{p}_pw", 0.0), "p_jahr": g(f"abf_{p}_pj", 0.0), "p_alter": g(f"abf_{p}_pa", 0.0),
         "p_kind": g(f"abf_{p}_pk", 0.0), "p_sb": g(f"abf_{p}_psb", 0.0), "festbetrag": g(f"abf_{p}_fest", 0.0),
         "sockel": g(f"abf_{p}_sockel", 0.0), "kind": g(f"abf_{p}_kind", 0.0), "unterhalt": g(f"abf_{p}_unterhalt", 0.0),
         "sb": g(f"abf_{p}_sbz", 0.0), "min": g(f"abf_{p}_min", 0.0), "max": g(f"abf_{p}_max", 0.0),
         "max_monate": g(f"abf_{p}_maxm", 0.0), "staffel": _staffel(g(f"abf_{p}_staffel", "")),
         "altersstaffel": _staffel(g(f"abf_{p}_astaffel", ""))}
    rm = g("abf_f_rente_m")
    if g(f"abf_{p}_rente_pct") and rm:
        r["rentennah"] = {"monate_bis_rente": rm, "prozent": g(f"abf_{p}_rente_pct")}
    if g(f"abf_{p}_budget") and g(f"abf_{p}_summe"):
        r["quote"] = float(M.sozialplan_quote(g(f"abf_{p}_budget"), g(f"abf_{p}_summe")))
    return r


def cfg_aus_session(ss):
    g = ss.get
    cfg = {}
    if g("abf_v_eigen"):
        cfg["eigener_faktor"] = g("abf_v_eigen")
    zusatz = [("Gehaltsnachzahlung / Gehalt bis Ende", g("abf_v_gehalt") or 0, "entgelt"),
              ("Urlaubsabgeltung", g("abf_v_urlaub") or 0, "entgelt"), ("Bonus / Tantieme", g("abf_v_bonus") or 0, "entgelt")]
    for p, k in (("auf", "aufhebung"), ("abw", "abwicklung"), ("ver", "vergleich"), ("zus", "zusage")):
        if g(f"abf_v_{p}_an"):
            cfg[k] = {"betrag": g(f"abf_v_{p}_betrag"), "faktor": g(f"abf_v_{p}_faktor"),
                      "zusatz": zusatz if k != "zusage" else None, "erfuellt": _jnu(g("abf_v_zus_erf", "unbekannt"))}
    if g("abf_v_fw_an"):
        cfg["freiwillig"] = {"faktor": g("abf_v_fw_faktor", 0.5), "frueh": g("abf_v_fw_frueh", 0.0),
                             "unterschrift": g("abf_v_fw_unter", 0.0), "praemie": g("abf_v_fw_praemie", 0.0),
                             "zuschlag_pct": g("abf_v_fw_zuschlag", 0.0)}
    if g("abf_v_tu_an"):
        cfg["turbo"] = {"basis": g("abf_v_tu_basis", 0.0), "ende_vertrag": g("abf_v_tu_ende_v"),
                        "ende_tatsaechlich": g("abf_f_ende"), "beteiligung": g("abf_v_tu_beteil", 50.0),
                        "ag_sv": g("abf_v_tu_sv", 0.0), "sprinter": g("abf_v_tu_fest", 0.0)}
    for p, k in (("sp", "sozialplan"), ("tv", "tarif"), ("bv", "bv")):
        if g(f"abf_{p}_an"):
            cfg[k] = _regel_aus_session(ss, p)
    return cfg


# ---------------------------------------------------------------------------
# Bereiche
# ---------------------------------------------------------------------------
def _bereich_fall(st, null):
    st.caption("Alle Angaben bleiben in dieser Sitzung erhalten und gelten für alle Bereiche. Pflicht sind nur "
               "Monatsgehalt sowie Beginn und Ende (oder die Jahre). Fehlende Angaben werden als „unbekannt“ "
               "gerechnet und ausdrücklich so gekennzeichnet.")
    form = st.container(key="abf_form")
    k = _karte(form, "1", "Person", "Alter, Kinder, Schwerbehinderung, Rentennähe", "person")
    c1, c2, c3 = k.columns(3)
    c1.number_input("Alter (Jahre)", 15, 80, **_s(st, "abf_f_alter", 0 if null else 45), key="abf_f_alter",
                    help="Alter zum Ende des Arbeitsverhältnisses (für § 10 KSchG, Sozialplan, ALG-Dauer). Statt "
                         "Geburtsdatum – es wird nichts Unnötiges gespeichert.")
    c2.number_input("Kinder", 0, 15, **_s(st, "abf_f_kinder", 0), key="abf_f_kinder")
    c3.number_input("Weitere Unterhaltsberechtigte", 0, 10, **_s(st, "abf_f_unterhalt", 0), key="abf_f_unterhalt")
    c4, c5 = k.columns(2)
    sb = c4.toggle("Schwerbehindert / gleichgestellt", **_s(st, "abf_f_sb", False), key="abf_f_sb")
    if sb:
        c5.number_input("GdB", 20, 100, **_s(st, "abf_f_gdb", 50), step=10, key="abf_f_gdb")
    c6, c7 = k.columns(2)
    c6.number_input("Monate bis zur (frühestmöglichen) Rente", 0, 600, **_s(st, "abf_f_rente_m", 0), key="abf_f_rente_m",
                    help="Optional – für Rentennah-Regeln im Sozialplan. 0 = nicht relevant.")
    c7.toggle("Regelaltersgrenze erreicht", **_s(st, "abf_f_regelalter", False), key="abf_f_regelalter",
              help="Dann gelten die erhöhten Grenzen des § 10 Abs. 2 KSchG nicht.")

    k = _karte(form, "2", "Beschäftigung", "Zeiten und Vergütung (Monatsverdienst nach § 10 Abs. 3 KSchG)", "besch")
    c1, c2 = k.columns(2)
    c1.date_input("Arbeitsbeginn", **_s(st, "abf_f_beginn", None if null else datetime.date(2016, 1, 1)),
                  format="DD.MM.YYYY", key="abf_f_beginn", min_value=datetime.date(1950, 1, 1))
    c2.date_input("Arbeitsende (letzter Arbeitstag)", **_s(st, "abf_f_ende", None if null else datetime.date(2026, 12, 31)),
                  format="DD.MM.YYYY", key="abf_f_ende", min_value=datetime.date(1950, 1, 1),
                  max_value=datetime.date(2040, 12, 31))
    c3, c4 = k.columns(2)
    c3.date_input("Zugang der Kündigung bzw. Vertragsschluss", **_s(st, "abf_f_zugang", None), format="DD.MM.YYYY",
                  key="abf_f_zugang", help="Für Kündigungsfrist, Klagefrist und Ruhen des Arbeitslosengelds")
    c4.number_input("Anrechenbare Vorbeschäftigung (Monate)", 0, 600, **_s(st, "abf_f_vorzeit", 0), key="abf_f_vorzeit",
                    help="Z. B. vertraglich anerkannte Zeiten beim Vorarbeitgeber")
    c5, c6 = k.columns(2)
    auto = c5.toggle("Kündigungsfrist nach § 622 BGB", **_s(st, "abf_f_frist_auto", True), key="abf_f_frist_auto",
                     help="Gesetzliche Arbeitgeberfrist je nach Betriebszugehörigkeit. Aus: eigene Frist "
                          "(Arbeits-/Tarifvertrag) eingeben.")
    if not auto:
        c6.number_input("Eigene Frist (Monate zum Monatsende)", 0, 24, **_s(st, "abf_f_frist", 3), key="abf_f_frist")
    k.selectbox("Betrieb mit mehr als 10 Arbeitnehmern (KSchG anwendbar)?", JNU, **_s(st, "abf_f_gross", 1, "index"),
                key="abf_f_gross")
    c1, c2 = k.columns(2)
    c1.number_input("Bruttomonatsgehalt (€) *", 0.0, 1e6, **_s(st, "abf_f_mon", 0.0 if null else 4000.0), step=100.0,
                    format="%.0f", key="abf_f_mon")
    c2.number_input("Zulagen monatlich (€)", 0.0, 1e6, **_s(st, "abf_f_zul", 0.0), step=50.0, format="%.0f", key="abf_f_zul")
    with k.expander("Sonderzahlungen und Sachbezüge (optional)"):
        c1, c2 = st.columns(2)
        c1.number_input("Weihnachtsgeld / 13. Gehalt jährlich (€)", 0.0, 1e6, **_s(st, "abf_f_weihn", 0.0), step=100.0,
                        format="%.0f", key="abf_f_weihn")
        c2.number_input("Urlaubsgeld jährlich (€)", 0.0, 1e6, **_s(st, "abf_f_urlaub", 0.0), step=100.0, format="%.0f",
                        key="abf_f_urlaub")
        c3, c4 = st.columns(2)
        c3.number_input("Regelmäßige Boni jährlich (€)", 0.0, 1e7, **_s(st, "abf_f_boni", 0.0), step=500.0,
                        format="%.0f", key="abf_f_boni")
        c4.number_input("Provisionen jährlich (€)", 0.0, 1e7, **_s(st, "abf_f_prov", 0.0), step=500.0, format="%.0f",
                        key="abf_f_prov")
        st.number_input("Geldwerte Vorteile / Sachbezüge monatlich (€, z. B. Dienstwagen)", 0.0, 1e5,
                        **_s(st, "abf_f_sach", 0.0), step=50.0, format="%.0f", key="abf_f_sach")
        st.toggle("Sonderzahlungen anteilig in den Monatsverdienst einbeziehen", **_s(st, "abf_f_sonder", True),
                  key="abf_f_sonder", help="§ 10 Abs. 3 KSchG: Geld- und Sachbezüge. Jahressonderzahlungen mit "
                                           "Entgeltcharakter werden in der Praxis meist anteilig (÷ 12) berücksichtigt "
                                           "– Einzelfallprüfung.")
        st.number_input("Arbeitsentgelt der letzten 12 Monate (€, für das Ruhen des ALG)", 0.0, 1e7,
                        **_s(st, "abf_f_jentgelt", None), step=1000.0, format="%.0f", key="abf_f_jentgelt",
                        placeholder="leer = Monatsverdienst × 12")

    k = _karte(form, "3", "Beendigung", "Wie endet das Arbeitsverhältnis?", "ende")
    k.selectbox("Art der Beendigung", list(ARTEN), format_func=ARTEN.get, **_s(st, "abf_f_art", 0, "index"),
                key="abf_f_art")
    c1, c2 = k.columns(2)
    c1.selectbox("Hinweis auf § 1a KSchG im Kündigungsschreiben?", JNU, key="abf_f_hinweis")
    c2.selectbox("Kündigungsschutzklage erhoben?", JNU, key="abf_f_klage")
    c3, c4 = k.columns(2)
    c3.toggle("Betriebsbedingte AG-Kündigung drohte (bei Aufhebungsvertrag)", **_s(st, "abf_f_drohend", False),
              key="abf_f_drohend")
    c4.toggle("Wichtiger Grund für die Aufgabe (z. B. Gesundheit, Mobbing)", **_s(st, "abf_f_wichtig", False),
              key="abf_f_wichtig", help="Nur relevant für die Sperrzeit beim Arbeitslosengeld")
    c5, c6 = k.columns(2)
    c5.selectbox("Betriebsänderung (§ 111 BetrVG)?", JNU, key="abf_f_baend")
    c6.selectbox("Interessenausgleich nicht versucht / ohne Grund abgewichen?", JNU, key="abf_f_ia",
                 help="Voraussetzung für den Nachteilsausgleich nach § 113 BetrVG")
    k.number_input("Versicherungspflichtige Monate in den letzten 5 Jahren (für die ALG-Dauer)", 0, 60,
                   **_s(st, "abf_f_versmon", 0 if null else 60), key="abf_f_versmon")
    k.multiselect("Besondere Situation (optional)", SONDER_AUSWAHL, format_func=lambda x: M.SONDERFAELLE[x][0],
                  key="abf_f_sonderf")

    k = _karte(form, "4", "Angebot / Vereinbarung", "Optional: was angeboten oder vereinbart ist", "vertrag")
    st_e = k
    for p, titel in (("auf", "Aufhebungsvertrag"), ("abw", "Abwicklungsvertrag"), ("ver", "Gerichtlicher Vergleich"),
                     ("zus", "Vertraglich zugesicherte Abfindung")):
        if st_e.toggle(titel, **_s(st, f"abf_v_{p}_an", False), key=f"abf_v_{p}_an"):
            c1, c2 = st_e.columns(2)
            c1.number_input(f"{titel}: Betrag (€)", 0.0, 1e8, **_s(st, f"abf_v_{p}_betrag", None), step=1000.0,
                            format="%.0f", key=f"abf_v_{p}_betrag", placeholder="Festbetrag")
            c2.number_input(f"{titel}: oder Faktor", 0.0, 10.0, **_s(st, f"abf_v_{p}_faktor", None), step=0.05,
                            key=f"abf_v_{p}_faktor", placeholder="z. B. 0,75", help="Nur wenn kein Betrag eingetragen ist")
            if p == "zus":
                st_e.selectbox("Vertragliche Voraussetzungen erfüllt?", JNU, key="abf_v_zus_erf")
    if st_e.toggle("Freiwilligenprogramm", **_s(st, "abf_v_fw_an", False), key="abf_v_fw_an"):
        c1, c2 = st_e.columns(2)
        c1.number_input("Faktor", 0.0, 10.0, **_s(st, "abf_v_fw_faktor", 0.5), step=0.05, key="abf_v_fw_faktor")
        c2.number_input("Freiwilligenzuschlag (%)", 0.0, 200.0, **_s(st, "abf_v_fw_zuschlag", 0.0), step=5.0,
                        key="abf_v_fw_zuschlag")
        c3, c4, c5 = st_e.columns(3)
        c3.number_input("Frühentscheider (€)", 0.0, 1e7, **_s(st, "abf_v_fw_frueh", 0.0), step=1000.0, format="%.0f",
                        key="abf_v_fw_frueh")
        c4.number_input("Unterschrift (€)", 0.0, 1e7, **_s(st, "abf_v_fw_unter", 0.0), step=1000.0, format="%.0f",
                        key="abf_v_fw_unter")
        c5.number_input("Zusatzprämie (€)", 0.0, 1e7, **_s(st, "abf_v_fw_praemie", 0.0), step=1000.0, format="%.0f",
                        key="abf_v_fw_praemie")
    if st_e.toggle("Turboklausel / Sprinterprämie", **_s(st, "abf_v_tu_an", False), key="abf_v_tu_an"):
        c1, c2 = st_e.columns(2)
        c1.number_input("Grundabfindung (€)", 0.0, 1e8, **_s(st, "abf_v_tu_basis", 0.0), step=1000.0, format="%.0f",
                        key="abf_v_tu_basis")
        c2.date_input("Ursprüngliches Vertragsende", **_s(st, "abf_v_tu_ende_v", None), format="DD.MM.YYYY",
                      key="abf_v_tu_ende_v", help="Tatsächliches Ausscheiden = „Arbeitsende“ oben")
        c3, c4, c5 = st_e.columns(3)
        c3.number_input("Beteiligung an eingesparten Gehältern (%)", 0.0, 100.0, **_s(st, "abf_v_tu_beteil", 50.0),
                        step=5.0, key="abf_v_tu_beteil")
        c4.number_input("+ AG-Sozialversicherung (%)", 0.0, 30.0, **_s(st, "abf_v_tu_sv", 0.0), step=1.0,
                        key="abf_v_tu_sv", help="Falls die Klausel die ersparten AG-Beiträge einbezieht")
        c5.number_input("Fester Sprinterbonus (€)", 0.0, 1e7, **_s(st, "abf_v_tu_fest", 0.0), step=500.0, format="%.0f",
                        key="abf_v_tu_fest")
    with st_e.expander("Weitere Zahlungen im Vertrag (Arbeitsentgelt – nicht Teil der Abfindung)"):
        c1, c2, c3 = st.columns(3)
        c1.number_input("Gehalt / Nachzahlung (€)", 0.0, 1e7, **_s(st, "abf_v_gehalt", 0.0), step=500.0, format="%.0f",
                        key="abf_v_gehalt")
        c2.number_input("Urlaubsabgeltung (€)", 0.0, 1e7, **_s(st, "abf_v_urlaub", 0.0), step=500.0, format="%.0f",
                        key="abf_v_urlaub")
        c3.number_input("Bonus (€)", 0.0, 1e7, **_s(st, "abf_v_bonus", 0.0), step=500.0, format="%.0f", key="abf_v_bonus")
        st.caption("Diese Beträge sind Arbeitslohn: steuer- und sozialversicherungspflichtig, ohne Fünftelregel. "
                   "Sie werden getrennt ausgewiesen und nicht zur Abfindung gezählt.")
    st_e.number_input("Eigener Vergleichsfaktor (optional)", 0.0, 10.0, **_s(st, "abf_v_eigen", None), step=0.05,
                      key="abf_v_eigen", placeholder="z. B. 0,8")

    # Kurzergebnis
    fall = fall_aus_session(st.session_state, null)
    erg = M.alle_modelle(fall, cfg_aus_session(st.session_state))
    st.markdown('<div class="abf-ergebnis-kopf">📊 Grundlagen</div>', unsafe_allow_html=True)
    dauer = erg["dauer"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Monatsverdienst", _eur(erg["mv"], 2))
    c2.metric("Beschäftigung", f"{dauer['jahre']} J. {dauer['monate']} M. {dauer['tage']} T." if dauer else "–",
              f"§ 1a: {dauer['jahre_1a']} Jahre" if dauer else None, delta_color="off")
    a1 = next((m for m in erg["modelle"] if m["key"] == "1a"), None)
    c3.metric("§ 1a KSchG", _eur(a1["brutto"]) if a1 and a1["brutto"] is not None else "nicht anwendbar",
              "nur bei allen Voraussetzungen" if a1 and a1["anwendbar"] else None, delta_color="off")
    if erg["mv_teile"]:
        st.caption("Monatsverdienst: " + " + ".join(f"{t} {_eur(b, 2)}" for t, b in erg["mv_teile"]))
    if not float(erg["mv"]):
        st.warning("Bitte das Bruttomonatsgehalt eintragen – ohne Monatsverdienst lässt sich nichts berechnen.")
    if not dauer:
        st.warning("Bitte Beginn und Ende des Arbeitsverhältnisses eintragen (Ende nach Beginn).")
    for k_ in (fall.get("sonder") or {}):
        titel, text = M.SONDERFAELLE[k_]
        st.info(f"**{titel}:** {text}")
    st.caption("➡️ Weiter: „📊 Alle Modelle“ zeigt alle Abfindungsmodelle mit Steuer und Netto nebeneinander.")


def _status_symbol(m):
    if not m["anwendbar"]:
        return "⛔"
    werte = [v["erfuellt"] for v in m["voraussetzungen"]]
    if any(w is None for w in werte):
        return "❓"
    return {"gesetz": "⚖️", "gericht": "🏛️", "kollektiv": "🏭", "vertrag": "📝", "verhandlung": "🤝"}.get(m["art"], "•")


def _bereich_modelle(st, pd, null):
    fall = fall_aus_session(st.session_state, null)
    st_e = steuer_aus_session(st.session_state, null)
    erg = M.alle_modelle(fall, cfg_aus_session(st.session_state))
    jahre_opt = [st_e["jahr"], st_e["jahr"] + 1]
    if st.session_state.get("abf_mo_jahr") not in jahre_opt:
        st.session_state.pop("abf_mo_jahr", None)
    jahr = st.radio("Auszahlungsjahr für die Steuer", jahre_opt, horizontal=True, key="abf_mo_jahr",
                    format_func=lambda j: f"{j}" + (" (Entwurf)" if A.tarif_hinweis(j) else ""))
    st_j = dict(st_e, zve=st_e["zve"] if jahr == st_e["jahr"] else st_e["zve2"],
                alg=st_e["alg"] if jahr == st_e["jahr"] else st_e["alg2"])
    if A.tarif_hinweis(jahr):
        st.caption(f"ℹ️ {A.tarif_hinweis(jahr)}.")
    st.caption(f"Steuer mit zu versteuerndem Einkommen ohne Abfindung von {_eur(st_j['zve'])} "
               f"({'Splitting' if st_j['splitting'] else 'Einzelveranlagung'}"
               + (f", Kirchensteuer {st_j['kirche'] * 100:.0f} %" if st_j["kirche"] else "")
               + ", " + ("mit Fünftelregel" if st_j["fuenftel_moeglich"] else "ohne Fünftelregel")
               + ") – ändern unter „💶 Brutto-Netto“. Steuer = Mehrsteuer durch die Abfindung, keine Pauschalquote.")
    zeilen = M.vergleich(erg, st_j, jahr)
    df = pd.DataFrame([{
        "": _status_symbol(z["modell"]), "Modell": z["modell"]["name"], "Faktor": z["modell"]["faktor"],
        "Brutto": float(z["modell"]["brutto"]) if z["modell"]["brutto"] is not None else None,
        "Steuer": float(z["steuer"]["steuer"]) if z["steuer"] else None,
        "Netto": float(z["steuer"]["netto"]) if z["steuer"] else None,
        "Status": z["modell"]["status"]} for z in zeilen])
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Brutto": st.column_config.NumberColumn("Brutto €", format="%.0f"),
        "Steuer": st.column_config.NumberColumn("Steuer €", format="%.0f"),
        "Netto": st.column_config.NumberColumn("Netto €", format="%.0f"),
        "": st.column_config.TextColumn("", width="small")})
    st.caption("⚖️ gesetzlich · 🏛️ gerichtliche Höchstgrenze · 🏭 Sozialplan/Tarif/BV · 📝 vertraglich · 🤝 "
               "verhandelbar · ❓ Voraussetzungen offen · ⛔ nicht anwendbar. Eine Zahl ersetzt nie fehlende "
               "Anspruchsvoraussetzungen.")
    try:
        import plotly.graph_objects as go
        ok = [z for z in zeilen if z["steuer"]]
        fig = go.Figure()
        fig.add_bar(y=[z["modell"]["name"] for z in ok], x=[float(z["steuer"]["netto"]) for z in ok], name="Netto",
                    orientation="h", marker_color="#16C784")
        fig.add_bar(y=[z["modell"]["name"] for z in ok], x=[float(z["steuer"]["steuer"]) for z in ok], name="Steuer",
                    orientation="h", marker_color="#EA3943")
        fig.update_layout(barmode="stack", height=max(260, 26 * len(ok) + 80), paper_bgcolor="#000",
                          plot_bgcolor="#000", font=dict(color="#D6D9DE", size=11), margin=dict(l=8, r=8, t=10, b=10),
                          legend=dict(orientation="h", y=1.05), separators=",.", xaxis=dict(gridcolor="#1A1A1A"),
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="abf_mo_chart")
    except Exception:
        pass
    c1, c2 = st.columns([3, 1])
    namen = [z["modell"]["name"] for z in zeilen if z["modell"]["brutto"] is not None and z["modell"]["anwendbar"]]
    if namen:
        if st.session_state.get("abf_mo_wahl") not in namen:
            st.session_state.pop("abf_mo_wahl", None)
        wahl = c1.selectbox("Betrag in den Brutto-Netto-Rechner übernehmen", namen, key="abf_mo_wahl")

        def _uebernehmen():
            z = next(z for z in zeilen if z["modell"]["name"] == st.session_state["abf_mo_wahl"])
            st.session_state["abf_summe"] = float(z["modell"]["brutto"])
            st.session_state["abf_nav"] = NAV[2]
        c2.button("Übernehmen", key="abf_mo_btn", width="stretch", on_click=_uebernehmen)
    for z in zeilen:
        m = z["modell"]
        with st.expander(f"{_status_symbol(m)} {m['name']} – {_eur(m['brutto']) if m['brutto'] is not None else 'nicht berechnet'}"):
            st.markdown(f"**Status:** {m['status']}  \n**Rechtsgrundlage:** {m['grundlage'] or '–'}")
            if m["formel"]:
                st.markdown(f"**Rechnung:** {m['formel']}")
            for v in m["voraussetzungen"]:
                st.markdown(f"{'✅' if v['erfuellt'] else '❌' if v['erfuellt'] is False else '❓'} {v['text']}")
            for t, b, art in m["bestandteile"]:
                st.caption(f"{'Abfindung' if art == 'abfindung' else 'Arbeitsentgelt (getrennt)'}: {t} {_eur(b, 2)}")
            for h in m["hinweise"]:
                st.caption(f"ℹ️ {h}")
            if z["steuer"]:
                s = z["steuer"]
                st.caption(f"Steuer {jahr}: ESt {_eur(s['est'], 2)} · Soli {_eur(s['soli'], 2)} · KiSt "
                           f"{_eur(s['kirche'], 2)} · Netto {_eur(s['netto'], 2)} · Lohnsteuerabzug bei Auszahlung ca. "
                           f"{_eur(s['lohnsteuer_ca'])} → Erstattung über die Erklärung ca. {_eur(s['erstattung'])}")


def _regel_eingabe(st, p, titel):
    with st.container(border=True):
        an = st.toggle(f"{titel} in den Modellvergleich übernehmen", **_s(st, f"abf_{p}_an", False), key=f"abf_{p}_an")
        meth = st.selectbox("Berechnungsart", list(METHODEN), format_func=METHODEN.get, key=f"abf_{p}_meth")
        c1, c2 = st.columns(2)
        if meth == "faktor":
            c1.number_input("Faktor je Jahr", 0.0, 10.0, **_s(st, f"abf_{p}_faktor", 0.5), step=0.05, key=f"abf_{p}_faktor")
        elif meth == "divisor":
            c1.number_input("Divisor", 1.0, 500.0, **_s(st, f"abf_{p}_div", 50.0), step=1.0, key=f"abf_{p}_div",
                            help="Typisch 40–80: Alter × Jahre × Monatsverdienst ÷ Divisor")
        elif meth == "punkte":
            c1.number_input("Punktwert (€)", 0.0, 1e6, **_s(st, f"abf_{p}_pw", 100.0), step=10.0, key=f"abf_{p}_pw")
            c2.number_input("Punkte je Jahr", 0.0, 100.0, **_s(st, f"abf_{p}_pj", 10.0), step=1.0, key=f"abf_{p}_pj")
            c3, c4, c5 = st.columns(3)
            c3.number_input("Punkte je Lebensjahr", 0.0, 100.0, **_s(st, f"abf_{p}_pa", 1.0), step=0.5, key=f"abf_{p}_pa")
            c4.number_input("Punkte je Kind", 0.0, 100.0, **_s(st, f"abf_{p}_pk", 5.0), step=1.0, key=f"abf_{p}_pk")
            c5.number_input("Punkte Schwerbeh.", 0.0, 100.0, **_s(st, f"abf_{p}_psb", 10.0), step=1.0, key=f"abf_{p}_psb")
        else:
            c1.number_input("Festbetrag (€)", 0.0, 1e8, **_s(st, f"abf_{p}_fest", 0.0), step=1000.0, format="%.0f",
                            key=f"abf_{p}_fest")
        with st.expander("Zuschläge, Staffeln, Mindest- und Höchstbeträge"):
            c1, c2 = st.columns(2)
            c1.number_input("Sockelbetrag (€)", 0.0, 1e7, **_s(st, f"abf_{p}_sockel", 0.0), step=500.0, format="%.0f",
                            key=f"abf_{p}_sockel")
            c2.number_input("Je Kind (€)", 0.0, 1e6, **_s(st, f"abf_{p}_kind", 0.0), step=250.0, format="%.0f",
                            key=f"abf_{p}_kind")
            c3, c4 = st.columns(2)
            c3.number_input("Je weitere unterhaltsber. Person (€)", 0.0, 1e6, **_s(st, f"abf_{p}_unterhalt", 0.0),
                            step=250.0, format="%.0f", key=f"abf_{p}_unterhalt")
            c4.number_input("Schwerbehinderung (€)", 0.0, 1e6, **_s(st, f"abf_{p}_sbz", 0.0), step=250.0, format="%.0f",
                            key=f"abf_{p}_sbz")
            st.text_input("Betriebszugehörigkeits-Staffel (ab Jahren: Faktor)", **_s(st, f"abf_{p}_staffel", ""),
                          key=f"abf_{p}_staffel", placeholder="z. B. 10: 0,7; 20: 0,9",
                          help="Ersetzt den Faktor ab der jeweiligen Betriebszugehörigkeit")
            st.text_input("Altersstaffel (ab Alter: Zuschlag zum Faktor)", **_s(st, f"abf_{p}_astaffel", ""),
                          key=f"abf_{p}_astaffel", placeholder="z. B. 45: 0,1; 50: 0,2")
            c5, c6, c7 = st.columns(3)
            c5.number_input("Mindestbetrag (€)", 0.0, 1e8, **_s(st, f"abf_{p}_min", 0.0), step=1000.0, format="%.0f",
                            key=f"abf_{p}_min")
            c6.number_input("Höchstbetrag (€)", 0.0, 1e8, **_s(st, f"abf_{p}_max", 0.0), step=1000.0, format="%.0f",
                            key=f"abf_{p}_max", help="0 = keine Kappung")
            c7.number_input("Höchstens Monatsverdienste", 0.0, 100.0, **_s(st, f"abf_{p}_maxm", 0.0), step=1.0,
                            key=f"abf_{p}_maxm", help="0 = keine Kappung")
            st.number_input("Rentennah: höchstens % des Monatsverdiensts × Monate bis zur Rente", 0.0, 100.0,
                            **_s(st, f"abf_{p}_rente_pct", 0.0), step=5.0, key=f"abf_{p}_rente_pct",
                            help="Nutzt „Monate bis zur Rente“ aus den Personenangaben; 0 = keine Regel")
            c8, c9 = st.columns(2)
            c8.number_input("Budget gesamt (€)", 0.0, 1e10, **_s(st, f"abf_{p}_budget", None), step=10000.0,
                            format="%.0f", key=f"abf_{p}_budget", placeholder="optional")
            c9.number_input("Summe aller Ansprüche (€)", 0.0, 1e10, **_s(st, f"abf_{p}_summe", None), step=10000.0,
                            format="%.0f", key=f"abf_{p}_summe", placeholder="optional",
                            help="Reicht das Budget nicht, werden alle Ansprüche anteilig gekürzt")
    return an


def _bereich_sozialplan(st, null):
    fall = fall_aus_session(st.session_state, null)
    mv, _ = M.monatsverdienst(fall)
    dauer = M.beschaeftigung(fall.get("beginn"), fall.get("ende"), fall.get("vorzeit_monate"))
    jahre = M.d(dauer["jahre_dezimal"]) if dauer else Decimal(0)
    st.caption("Es gibt keine allgemeingültige Sozialplanformel – alle Werte aus dem konkreten Sozialplan, "
               "Tarifvertrag oder der Betriebsvereinbarung eintragen. Gleichbehandlung (§ 75 BetrVG) und AGG beachten.")
    art = st.pills("Regelwerk", ["Sozialplan", "Tarifvertrag", "Betriebsvereinbarung", "Insolvenz"],
                   default="Sozialplan", key="abf_sp_nav") or "Sozialplan"
    st_e = steuer_aus_session(st.session_state, null)
    if art == "Insolvenz":
        st.caption("§ 123 InsO begrenzt das GESAMTVOLUMEN des Sozialplans (2,5 Monatsverdienste je Betroffenem, "
                   "höchstens ein Drittel der Teilungsmasse) – keine individuelle Obergrenze.")
        c1, c2 = st.columns(2)
        c1.toggle("Sozialplan nach Eröffnung des Verfahrens", **_s(st, "abf_in_nach", True), key="abf_in_nach")
        c2.number_input("Monate zwischen Sozialplan und Insolvenzantrag", 0, 120, **_s(st, "abf_in_mva", 6),
                        key="abf_in_mva", help="Für § 124 InsO (Widerruf, wenn ≤ 3 Monate)")
        c3, c4, c5 = st.columns(3)
        c3.number_input("Summe Monatsverdienste aller Betroffenen (€)", 0.0, 1e10, **_s(st, "abf_in_mv", None),
                        step=10000.0, format="%.0f", key="abf_in_mv", placeholder="z. B. 400000")
        c4.number_input("Teilungsmasse (€)", 0.0, 1e11, **_s(st, "abf_in_masse", None), step=100000.0, format="%.0f",
                        key="abf_in_masse", placeholder="optional")
        c5.number_input("Summe aller Sozialplanansprüche (€)", 0.0, 1e10, **_s(st, "abf_in_anspr", None),
                        step=10000.0, format="%.0f", key="abf_in_anspr", placeholder="z. B. 2000000")
        anspruch, _, _ = M.regelwerk(fall, mv, jahre, _regel_aus_session(st.session_state, "sp"))
        r = M.insolvenz(anspruch, {"summe_mv": st.session_state.get("abf_in_mv"),
                                   "masse": st.session_state.get("abf_in_masse"),
                                   "summe_ansprueche": st.session_state.get("abf_in_anspr"),
                                   "nach_eroeffnung": st.session_state.get("abf_in_nach", True),
                                   "monate_vor_antrag": st.session_state.get("abf_in_mva")})
        c1, c2, c3 = st.columns(3)
        c1.metric("Anspruch laut Sozialplan", _eur(r["anspruch"]))
        c2.metric("Quote", f"{M.de(r['quote'], 1)} %")
        c3.metric("Voraussichtliche Auszahlung", _eur(r["auszahlung"]))
        for h in r["hinweise"]:
            st.caption(f"ℹ️ {h}")
        st.caption("Der Anspruch laut Sozialplan kommt aus dem Reiter „Sozialplan“.")
        return
    p = {"Sozialplan": "sp", "Tarifvertrag": "tv", "Betriebsvereinbarung": "bv"}[art]
    _regel_eingabe(st, p, art)
    brutto, teile, hinweise = M.regelwerk(fall, mv, jahre, _regel_aus_session(st.session_state, p))
    s = M.steuer_netto(brutto, st_e)
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{art}-Abfindung brutto", _eur(brutto))
    c2.metric("Steuer", _eur(s["steuer"]))
    c3.metric("Netto", _eur(s["netto"]))
    for t, b in teile:
        st.caption(f"{t}: {_eur(b, 2)}")
    for h in hinweise:
        st.caption(f"ℹ️ {h}")


def _bereich_verhandlung(st, pd, null):
    fall = fall_aus_session(st.session_state, null)
    st_e = steuer_aus_session(st.session_state, null)
    mv, _ = M.monatsverdienst(fall)
    dauer = M.beschaeftigung(fall.get("beginn"), fall.get("ende"), fall.get("vorzeit_monate"))
    jahre = M.d(dauer["jahre_dezimal"]) if dauer else Decimal(0)
    if not mv or not jahre:
        st.info("Bitte unter „🧮 Abfindung berechnen“ Monatsgehalt sowie Beginn und Ende eintragen.")
        return
    f = st.slider("Abfindungsfaktor (Monatsverdienste je Beschäftigungsjahr)", 0.0, 3.0,
                  **_s(st, "abf_vh_f", 0.5), step=0.05, key="abf_vh_f")
    brutto = mv * jahre * M.d(f)
    s = M.steuer_netto(brutto, st_e)
    c1, c2, c3 = st.columns(3)
    c1.metric("Brutto", _eur(brutto))
    c2.metric("Steuer", _eur(s["steuer"]), f"{float(s['steuer']) / float(brutto) * 100:.1f} %".replace(".", ",")
              if brutto else None, delta_color="off")
    c3.metric("Netto", _eur(s["netto"]))
    stufen = [Decimal(x) / 4 for x in range(0, 13)]
    werte = [(x, M.steuer_netto(mv * jahre * x, st_e)) for x in stufen]
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_scatter(x=[float(x) for x, _ in werte], y=[float(w["brutto"]) for _, w in werte], name="Brutto",
                        line=dict(color="#4C9AFF"))
        fig.add_scatter(x=[float(x) for x, _ in werte], y=[float(w["netto"]) for _, w in werte], name="Netto",
                        line=dict(color="#16C784"))
        fig.add_vline(x=float(f), line_color="#F5B942", line_dash="dot")
        fig.update_layout(height=280, paper_bgcolor="#000", plot_bgcolor="#000", font=dict(color="#D6D9DE", size=11),
                          margin=dict(l=8, r=8, t=10, b=30), legend=dict(orientation="h", y=1.08), separators=",.",
                          xaxis=dict(title="Faktor", gridcolor="#1A1A1A"), yaxis=dict(gridcolor="#1A1A1A"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="abf_vh_chart")
    except Exception:
        pass
    st.dataframe(pd.DataFrame([{"Faktor": M.de(x, 2), "Brutto €": float(w["brutto"]), "Steuer €": float(w["steuer"]),
                                "Netto €": float(w["netto"])} for x, w in werte]), hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(c, format="%.0f") for c in ("Brutto €", "Steuer €", "Netto €")})

    st.markdown("##### 🎯 Abfindungsziel")
    c1, c2 = st.columns(2)
    art = c1.radio("Ziel", ["Netto", "Brutto"], horizontal=True, key="abf_vh_ziel_art")
    ziel = c2.number_input(f"Gewünschte {art}-Abfindung (€)", 0.0, 1e8, **_s(st, "abf_vh_ziel", None), step=1000.0,
                           format="%.0f", key="abf_vh_ziel", placeholder="z. B. 40000")
    if ziel:
        br = M.brutto_fuer_netto(ziel, st_e) if art == "Netto" else M.eur(ziel)
        fz = M.faktor_fuer_brutto(br, mv, jahre)
        basis = mv * jahre * Decimal("0.5")
        st.markdown(f"Erforderlich: **{_eur(br)} brutto** · Faktor **{M.de(fz, 2)}** · gegenüber der Basis "
                    f"0,5 ({_eur(basis)}) **{_eur(br - basis)}** {'mehr' if br >= basis else 'weniger'} zu verhandeln.")
    st.caption("Faktoren sind Verhandlungsgrößen – keine gesetzlichen Ansprüche. Steuer = Mehrsteuer durch die Abfindung "
               "mit den Angaben aus „💶 Brutto-Netto“.")


def _bereich_alg(st, null):
    fall = fall_aus_session(st.session_state, null)
    st_e = steuer_aus_session(st.session_state, null)
    erg = M.alle_modelle(fall, cfg_aus_session(st.session_state))
    dauer = erg["dauer"]
    kandidaten = [m for m in erg["modelle"] if m["brutto"] is not None and m["anwendbar"]
                  and m["key"] in ("aufhebung", "abwicklung", "vergleich", "zusage", "sozialplan", "tarif", "bv",
                                   "freiwillig", "turbo", "1a")]
    abf = float(kandidaten[0]["brutto"]) if kandidaten else float(st.session_state.get("abf_summe") or 0)
    st.caption(f"Geprüft mit Abfindung {_eur(abf)} "
               f"({kandidaten[0]['name'] if kandidaten else 'Betrag aus dem Brutto-Netto-Rechner'}).")
    c = M.alg_check(fall, dauer, abf, erg["mv"])
    sp = c["sperrzeit"]
    if sp:
        farbe = {"hoch": st.error, "mittel": st.warning, "gering": st.success}[sp["stufe"]]
        farbe(f"**Sperrzeit (§ 159 SGB III) – Risiko {sp['stufe']}:** {sp['text']}")
    if c["fiktives_ende"]:
        st.markdown(f"**Kündigungsfrist:** {c['frist_monate'] or '4 Wochen'}"
                    f"{' Monate zum Monatsende' if c['frist_monate'] else ''} → ordentliches Ende "
                    f"{c['fiktives_ende'].strftime('%d.%m.%Y')} · tatsächliches Ende "
                    f"{fall['ende'].strftime('%d.%m.%Y') if fall.get('ende') else '–'} → "
                    + ("✅ eingehalten" if c["frist_ok"] else "⚠️ nicht eingehalten"))
    else:
        st.caption("Für die Fristprüfung „Zugang der Kündigung bzw. Vertragsschluss“ eintragen.")
    r = c["ruhen"]
    if r:
        st.warning(f"**Ruhen des Arbeitslosengelds (§ 158 SGB III):** vom {r['beginn'].strftime('%d.%m.%Y')} bis "
                   f"{r['bis'].strftime('%d.%m.%Y')} = **{r['tage']} Kalendertage** (begrenzt durch: {r['grund']}). "
                   f"Berücksichtigt werden {r['anteil']} % der Abfindung"
                   + (f"; kalendertägliches Entgelt {_eur(r['tagesentgelt'], 2)}." if r["tagesentgelt"] else "."))
        st.caption("Ruhen verschiebt den Anspruch, kürzt ihn aber nicht. Bei unkündbaren Arbeitnehmern gelten "
                   "fiktive Fristen (18 Monate bzw. 1 Jahr) – hier nicht abgebildet.")
    for t in c["punkte"]:
        st.caption(f"⚠️ {t}")
    if c["meldung"]:
        st.info(f"**Arbeitsuchend melden:** {c['meldung']['text']}")
    if c["klagefrist"]:
        st.info(f"**Klagefrist:** {c['klagefrist']['text']}")
    if c["alg_monate"]:
        st.markdown(f"**Anspruchsdauer ALG I** (§ 147 SGB III, nach Alter und Versicherungsmonaten): "
                    f"{c['alg_monate']} Monate" + (" – durch eine Sperrzeit um mindestens ein Viertel kürzer."
                                                    if sp and sp["tage"] else ""))
    stt, txt = M.fuenftel_status(abf, st_e["jahresbrutto"], st_e["vorjahr"], st_e["alg"])
    {"anwendbar": st.success, "nicht anwendbar": st.error, "prüfen": st.warning}[stt](
        f"**Fünftelregel: {stt}.** {txt}")
    st.markdown("**Sozialversicherung:** Eine echte Entlassungsentschädigung ist kein Arbeitsentgelt und "
                "beitragsfrei. Gehaltsnachzahlungen, Urlaubsabgeltung, Boni und Vergütung für geleistete Arbeit sind "
                "beitragspflichtig. Freiwillig gesetzlich Versicherte ohne Leistungsbezug: Die Krankenkasse kann die "
                "Abfindung als Einnahme verbeitragen – vorher klären.")
    for k_ in (fall.get("sonder") or {}):
        titel, text = M.SONDERFAELLE[k_]
        st.caption(f"**{titel}:** {text}")


def _bereich_szenarien(st, pd, null):
    fall = fall_aus_session(st.session_state, null)
    st_e = steuer_aus_session(st.session_state, null)
    mv, _ = M.monatsverdienst(fall)
    dauer = M.beschaeftigung(fall.get("beginn"), fall.get("ende"), fall.get("vorzeit_monate"))
    jahre = M.d(dauer["jahre_dezimal"]) if dauer else Decimal(0)
    if not mv or not jahre:
        st.info("Bitte unter „🧮 Abfindung berechnen“ Monatsgehalt sowie Beginn und Ende eintragen.")
        return
    st.caption("Wirtschaftliches Gesamtpaket je Variante – Abfindung und Arbeitsentgelt getrennt. Netto des "
               "Entgelts ist eine Schätzung (Lohnsteuer über die Jahressteuer, Sozialversicherung pauschal 21 %).")
    c1, c2, c3 = st.columns(3)
    basis_f = c1.number_input("Basis-Faktor", 0.0, 5.0, **_s(st, "abf_sz_faktor", 0.5), step=0.05, key="abf_sz_faktor")
    mehr = c2.number_input("Höhere Einmalabfindung (+ %)", 0.0, 300.0, **_s(st, "abf_sz_mehr", 25.0), step=5.0,
                           key="abf_sz_mehr")
    sprint = c3.number_input("Sprinterprämie (% eingesparter Gehälter)", 0.0, 100.0, **_s(st, "abf_sz_sprinter", 50.0),
                             step=5.0, key="abf_sz_sprinter")
    frist_m = fall.get("frist_monate")
    if frist_m is None:
        frist_m = M.gesetzliche_frist_monate(dauer["jahre"])
    monate_frist = Decimal(max(frist_m, 1))
    abf = mv * jahre * M.d(basis_f)

    def netto_entgelt(brutto):
        if not brutto:
            return Decimal(0)
        x = A.est(st_e["zve"] + float(brutto), st_e["splitting"], 0, st_e["jahr"]) - A.est(st_e["zve"], st_e["splitting"], 0, st_e["jahr"])
        return M.eur(M.d(brutto) * Decimal("0.79") - M.d(x))

    def paket(name, abfindung, entgelt_brutto, jahr=None, hinweis=""):
        s = M.steuer_netto(abfindung, dict(st_e, zve=st_e["zve2"] if jahr else st_e["zve"]), jahr or st_e["jahr"])
        ne = netto_entgelt(entgelt_brutto)
        return {"Variante": name, "Abfindung brutto": float(M.eur(abfindung)), "Abfindung netto": float(s["netto"]),
                "Entgelt brutto": float(M.eur(entgelt_brutto)), "Entgelt netto (ca.)": float(ne),
                "Paket netto": float(s["netto"] + ne), "Hinweis": hinweis}
    gehalt_frist = mv * monate_frist
    zeilen = [
        paket("Ordentliche Kündigungsfrist", abf, gehalt_frist, hinweis=f"{monate_frist} Monate Gehalt + Abfindung"),
        paket("Bezahlte Freistellung bis Fristende", abf, gehalt_frist, hinweis="wie Frist, ohne Arbeitspflicht"),
        paket("Sofortige Beendigung", abf, 0, hinweis="Frist nicht eingehalten → Ruhen des ALG möglich"),
        paket("Sofort + Sprinterprämie", abf + gehalt_frist * M.d(sprint) / 100, 0,
              hinweis=f"{M.de(sprint, 0)} % der eingesparten Gehälter als Abfindung"),
        paket("Höhere Einmalabfindung (sofort)", abf * (1 + M.d(mehr) / 100), 0, hinweis=f"+{M.de(mehr, 0)} %"),
        paket(f"Auszahlung im Folgejahr {st_e['jahr'] + 1}", abf, gehalt_frist, jahr=st_e["jahr"] + 1,
              hinweis="Einkommen Folgejahr aus „💶 Brutto-Netto“" + (" (Entwurf)" if A.tarif_hinweis(st_e["jahr"] + 1) else "")),
    ]
    df = pd.DataFrame(zeilen)
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(c, format="%.0f") for c in
        ("Abfindung brutto", "Abfindung netto", "Entgelt brutto", "Entgelt netto (ca.)", "Paket netto")})
    beste = max(zeilen, key=lambda z: z["Paket netto"])
    st.success(f"Höchstes Netto-Paket: **{beste['Variante']}** ({_eur(beste['Paket netto'])}). Arbeitslosengeld-"
               "Folgen (Sperrzeit/Ruhen) sind nicht eingerechnet – siehe „🧾 ALG & Risiken“.")


def _bericht(st, null):
    fall = fall_aus_session(st.session_state, null)
    st_e = steuer_aus_session(st.session_state, null)
    erg = M.alle_modelle(fall, cfg_aus_session(st.session_state))
    zeilen = M.vergleich(erg, st_e)
    c = M.alg_check(fall, erg["dauer"], float(next((z["modell"]["brutto"] for z in zeilen
                                                    if z["modell"]["key"] == "f0.5" and z["modell"]["brutto"]), 0)),
                    erg["mv"])
    pdf = pdf_bericht(fall, st_e, erg, zeilen, c)
    st.download_button("📄 Berechnungsbericht als PDF", data=pdf, file_name="Abfindung_Modelle_Bericht.pdf",
                       mime="application/pdf", width="stretch", key="abf_ber_pdf")
    st.caption("Der Bericht enthält Grundlagen, alle Modelle mit Status, Steuer und Netto, den ALG-Check und die "
               "Rechtsgrundlagen. Er wird nur auf deinem Gerät erzeugt und nicht gespeichert.")


def pdf_bericht(fall, st_e, erg, zeilen, alg, erstellt=None):
    erstellt = erstellt or datetime.datetime.now()
    p = A._PDF()
    p.fuss = "Abfindungsrechner - Szenariorechnung, keine Rechts- oder Steuerberatung"
    p.y -= 8
    p.text(p.RAND, p.y, "Abfindung – alle Modelle im Vergleich", 18, True, (0.08, 0.1, 0.16))
    p.y -= 16
    p.text(p.RAND, p.y, f"Erstellt am {erstellt.strftime('%d.%m.%Y %H:%M')} · Steuerjahr {st_e['jahr']}"
           + (" (Tarif-Entwurf)" if A.tarif_hinweis(st_e["jahr"]) else ""), 9, False, (0.4, 0.4, 0.4))
    p.ueberschrift("Grundlagen")
    d = erg["dauer"]
    p.absatz(f"Monatsverdienst {M.de(erg['mv'])} € ("
             + ", ".join(f"{t} {M.de(b)} €" for t, b in erg["mv_teile"]) + "). "
             + (f"Beschäftigung {d['jahre']} Jahre, {d['monate']} Monate, {d['tage']} Tage (für § 1a: {d['jahre_1a']} "
                "Jahre). " if d else "Beschäftigungszeit fehlt. ")
             + f"Art der Beendigung: {ARTEN.get(fall.get('art'), '–')}. Alter {fall.get('alter')}. "
             + f"Zu versteuerndes Einkommen ohne Abfindung {M.de(st_e['zve'], 0)} €"
             + (", Splitting" if st_e["splitting"] else "") + ".")
    p.ueberschrift("Modelle")
    p.tabelle(["Modell", "Faktor", "Brutto", "Steuer", "Netto"],
              [[z["modell"]["name"], str(z["modell"]["faktor"]),
                f"{M.de(z['modell']['brutto'], 0)} €" if z["modell"]["brutto"] is not None else "–",
                f"{M.de(z['steuer']['steuer'], 0)} €" if z["steuer"] else "–",
                f"{M.de(z['steuer']['netto'], 0)} €" if z["steuer"] else "–"] for z in zeilen],
              [4.2, 1.1, 1.3, 1.2, 1.3])
    for z in zeilen:
        m = z["modell"]
        p.absatz(f"{m['name']}: {m['status']}" + (f" – {m['grundlage']}" if m["grundlage"] else ""), 8, True)
        for v in m["voraussetzungen"]:
            p.absatz(("[ja] " if v["erfuellt"] else "[nein] " if v["erfuellt"] is False else "[offen] ") + v["text"],
                     7.5, einzug=10)
        for h in m["hinweise"]:
            p.absatz(h, 7.5, einzug=10)
    p.ueberschrift("Arbeitslosengeld und Fristen")
    if alg["sperrzeit"]:
        p.absatz(f"Sperrzeit: Risiko {alg['sperrzeit']['stufe']} – {alg['sperrzeit']['text']}")
    if alg["ruhen"]:
        r = alg["ruhen"]
        p.absatz(f"Ruhen § 158 SGB III: {r['beginn'].strftime('%d.%m.%Y')} bis {r['bis'].strftime('%d.%m.%Y')} "
                 f"({r['tage']} Tage, Grenze: {r['grund']}).")
    for k in ("meldung", "klagefrist"):
        if alg.get(k):
            p.absatz(alg[k]["text"])
    p.ueberschrift("Rechtsgrundlagen")
    p.absatz("KSchG §§ 1a, 4, 9, 10, 13, 14, 23 · BGB §§ 622, 628 · BetrVG §§ 75, 111–113 · InsO §§ 123, 124 · "
             "SGB III §§ 38, 147, 148, 158, 159 · EStG §§ 24, 32a, 34 · SolZG · AGG § 10. Quellen: "
             "gesetze-im-internet.de, Bundesfinanzministerium, Bundesagentur für Arbeit.")
    p.absatz("Hinweis: Rechnerische Szenarien. Ob ein Anspruch besteht, hängt von den Voraussetzungen im Einzelfall "
             "ab. Keine Rechts- oder Steuerberatung.", 8, False, (0.4, 0.4, 0.4))
    return p.bytes()


def render_bereich(st, pd, bereich, null=False):
    if bereich == NAV[0]:
        _bereich_fall(st, null)
    elif bereich == NAV[1]:
        _bereich_modelle(st, pd, null)
    elif bereich == NAV[3]:
        _bereich_sozialplan(st, null)
    elif bereich == NAV[4]:
        _bereich_verhandlung(st, pd, null)
    elif bereich == NAV[5]:
        _bereich_alg(st, null)
    elif bereich == NAV[6]:
        _bereich_szenarien(st, pd, null)
    elif bereich == NAV[7]:
        _bericht(st, null)
