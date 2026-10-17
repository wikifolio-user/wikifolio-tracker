"""Tests fuer benutzerbezogene Daten (python3 -m unittest test_nutzerdaten).

- nutzerdaten.py: Speicherorte je Benutzer, gemerkte Eingaben (Drosselung, nur bei
  Aenderung, sofort beim Verlassen), Vorbelegung nur einmal je Sitzung.
- app.py: die benutzerbezogenen Helfer (upfad, leeres Depot, Startbestand, Rechner-
  Eingaben sammeln) - per AST herausgeloest wie in test_app_rechnung.py, da app.py
  ohne Streamlit nicht importierbar ist.
"""
import ast
import bisect
import datetime
import html
import math
import os
import re
import types
import unittest

import pandas as pd

import config
import nutzerdaten as N

ADMIN = {"name": "chef", "rolle": "admin", "ansichten": []}
ANNA = {"name": "Anna Müller", "rolle": "benutzer", "ansichten": []}


class Pfade(unittest.TestCase):
    def test_admin_und_ohne_login_unveraendert(self):
        for nutzer in (ADMIN, None, {}):
            self.assertEqual(N.pfad("state/positionen.json", nutzer), "state/positionen.json")
            self.assertEqual(N.pfad("state/trades_db.json", nutzer), "state/trades_db.json")
        self.assertEqual(N.eingaben_pfad(ADMIN), "state/eingaben.json")
        self.assertEqual(N.eingaben_pfad(None), "state/eingaben.json")

    def test_normaler_benutzer_eigener_ordner(self):
        self.assertEqual(N.pfad("state/positionen.json", ANNA), "state/benutzer/anna-muller/positionen.json")
        self.assertEqual(N.pfad("state/sparplan_state.json", ANNA), "state/benutzer/anna-muller/sparplan_state.json")
        self.assertEqual(N.eingaben_pfad(ANNA), "state/benutzer/anna-muller/eingaben.json")
        self.assertTrue(N.ist_eigener_bereich(ANNA))
        self.assertFalse(N.ist_eigener_bereich(ADMIN))
        self.assertFalse(N.ist_eigener_bereich(None))

    def test_unterordner_und_backslash(self):
        self.assertEqual(N.pfad("state/planer/szenarien.json", ANNA), "state/benutzer/anna-muller/planer/szenarien.json")
        self.assertEqual(N.pfad("state\\musterdepot.json", ANNA), "state/benutzer/anna-muller/musterdepot.json")

    def test_benutzer_ohne_namen_ist_kein_eigener_bereich(self):
        self.assertFalse(N.ist_eigener_bereich({"name": "", "rolle": "benutzer"}))
        self.assertEqual(N.pfad("state/positionen.json", {"name": "", "rolle": "benutzer"}), "state/positionen.json")


class Slug(unittest.TestCase):
    def test_sonderfaelle(self):
        self.assertEqual(N.slug("Anna Müller"), "anna-muller")
        self.assertEqual(N.slug("  ÄÖÜ ß  "), "aou")            # ß faellt bei ASCII-Normalisierung weg
        self.assertEqual(N.slug("../../etc/passwd"), "etc-passwd")
        self.assertEqual(N.slug("a/b\\c"), "a-b-c")
        self.assertEqual(N.slug(""), "benutzer")
        self.assertEqual(N.slug(None), "benutzer")
        self.assertEqual(N.slug("!!!"), "benutzer")
        self.assertEqual(N.slug("max_mustermann-2"), "max_mustermann-2")
        self.assertEqual(len(N.slug("x" * 200)), 60)

    def test_kein_ausbruch_aus_dem_ordner(self):
        for name in ("..", "../admin", "/", "state", "a/../../b"):
            p = N.pfad("state/positionen.json", {"name": name, "rolle": "benutzer"})
            self.assertTrue(p.startswith("state/benutzer/"), p)
            self.assertNotIn("..", p)
            self.assertEqual(p.count("/"), 3, p)


class FakeStore:
    """gh_aktualisiere-Ersatz: speichert je Pfad, zaehlt Schreibvorgaenge."""
    def __init__(self, ok=True):
        self.daten, self.schreiben, self.ok = {}, [], ok

    def aktualisiere(self, pfad, aendern, default=None, message=""):
        if not self.ok:
            return False, None
        neu = aendern(dict(self.daten.get(pfad, default) or {}))
        if neu is None:
            return True, self.daten.get(pfad)
        self.daten[pfad] = neu
        self.schreiben.append((pfad, message))
        return True, neu

    def lesen(self, pfad, default):
        return self.daten.get(pfad, default)


class EingabenMerken(unittest.TestCase):
    def test_erstes_speichern_und_keine_wiederholung_ohne_aenderung(self):
        f, ss = FakeStore(), {}
        self.assertTrue(N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", {"zr_a": 1.0}, jetzt=1000))
        self.assertEqual(f.daten["state/benutzer/anna-muller/eingaben.json"], {"zinsrechner": {"zr_a": 1.0}})
        self.assertFalse(N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", {"zr_a": 1.0}, jetzt=5000))
        self.assertEqual(len(f.schreiben), 1)

    def test_drosselung_und_nachholen(self):
        f, ss = FakeStore(), {}
        N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", {"zr_a": 1.0}, jetzt=1000)
        # innerhalb von MIN_ABSTAND_SEK: nicht schreiben, aber als offen merken
        self.assertFalse(N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", {"zr_a": 2.0}, jetzt=1005))
        self.assertEqual(ss["_eingaben_zinsrechner_offen"], {"zr_a": 2.0})
        self.assertEqual(len(f.schreiben), 1)
        # nach Ablauf: geschrieben, offen geloescht
        self.assertTrue(N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", {"zr_a": 2.0},
                                          jetzt=1000 + N.MIN_ABSTAND_SEK))
        self.assertNotIn("_eingaben_zinsrechner_offen", ss)
        self.assertEqual(f.daten["state/benutzer/anna-muller/eingaben.json"]["zinsrechner"]["zr_a"], 2.0)

    def test_sofort_umgeht_drosselung(self):
        f, ss = FakeStore(), {}
        N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", {"zr_a": 1.0}, jetzt=1000)
        N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", {"zr_a": 3.0}, jetzt=1001)
        offen = ss["_eingaben_zinsrechner_offen"]
        self.assertTrue(N.eingaben_merken(f.aktualisiere, ss, ANNA, "zinsrechner", offen, sofort=True, jetzt=1002))
        self.assertEqual(f.daten["state/benutzer/anna-muller/eingaben.json"]["zinsrechner"]["zr_a"], 3.0)
        self.assertEqual(len(f.schreiben), 2)

    def test_bereiche_getrennt_und_admin_datei(self):
        f, ss = FakeStore(), {}
        N.eingaben_merken(f.aktualisiere, ss, ADMIN, "zinsrechner", {"zr_a": 1.0}, jetzt=1000)
        N.eingaben_merken(f.aktualisiere, ss, ADMIN, "abfindung", {"abf_summe": 9.0}, jetzt=1001)
        self.assertEqual(f.daten["state/eingaben.json"], {"zinsrechner": {"zr_a": 1.0}, "abfindung": {"abf_summe": 9.0}})

    def test_nur_einfache_werte(self):
        f, ss = FakeStore(), {}
        N.eingaben_merken(f.aktualisiere, ss, ANNA, "x", {"a": 1, "b": float("nan"), "c": object(), "d": None,
                                                         "e": datetime.date(2026, 1, 2), "f": [1, "z"]}, jetzt=1000)
        self.assertEqual(f.daten["state/benutzer/anna-muller/eingaben.json"]["x"],
                         {"a": 1, "d": None, "e": "2026-01-02", "f": [1, "z"]})

    def test_fehlschlag_wird_wiederholt(self):
        f, ss = FakeStore(ok=False), {}
        self.assertFalse(N.eingaben_merken(f.aktualisiere, ss, ANNA, "z", {"a": 1}, jetzt=1000))
        f.ok = True                                            # kein Erfolg -> keine Sperrzeit
        self.assertTrue(N.eingaben_merken(f.aktualisiere, ss, ANNA, "z", {"a": 1}, jetzt=1001))

    def test_laden(self):
        f = FakeStore()
        f.daten["state/benutzer/anna-muller/eingaben.json"] = {"zinsrechner": {"zr_a": 5.0}, "kaputt": 3}
        self.assertEqual(N.eingaben_laden(f.lesen, ANNA, "zinsrechner"), {"zr_a": 5.0})
        self.assertEqual(N.eingaben_laden(f.lesen, ANNA, "kaputt"), {})
        self.assertEqual(N.eingaben_laden(f.lesen, ANNA, "fehlt"), {})
        self.assertEqual(N.eingaben_laden(f.lesen, ADMIN, "zinsrechner"), {})     # andere Datei


class Vorbelegen(unittest.TestCase):
    def test_nur_einmal_und_ohne_ueberschreiben(self):
        ss = {"zr_s": 7.0}
        self.assertTrue(N.eingaben_vorbelegen(ss, {"zr_a": 1.0, "zr_s": 2.0}, {"zr_a": "zr_a", "zr_s": "zr_s"}))
        self.assertEqual(ss["zr_a"], 1.0)
        self.assertEqual(ss["zr_s"], 7.0)                      # vorhandene Eingabe bleibt
        ss["zr_a"] = 99.0
        self.assertFalse(N.eingaben_vorbelegen(ss, {"zr_a": 1.0, "zr_s": 2.0}, {"zr_a": "zr_a", "zr_s": "zr_s"}))
        self.assertEqual(ss["zr_a"], 99.0)


# ===========================================================================
# app.py-Helfer (per AST)
# ===========================================================================
FUNKTIONEN = ["upfad", "eigener_bereich", "_position_aus_config", "positionen_startbestand", "positionen_oder_start",
              "depot_aufteilung", "entnahme_standard", "haupt_position_aktiv", "auflegungen_zusammen",
              "entnahme_rate_aus_state", "depot_kennzahlen", "gesamt_perioden_berechnen", "eingaben_sammeln",
              "berechne_reale_stueckzahl", "kumulierte_entnahme", "entnahme_termine", "monats_termine"]
ZUWEISUNGEN = ["RECHNER_EINGABEN"]


def _lade_app():
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    with open(pfad, encoding="utf-8") as f:
        baum = ast.parse(f.read())
    defs = {n.name: n for n in baum.body if isinstance(n, ast.FunctionDef)}
    zuw = {t.id: n for n in baum.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    fehlend = [f for f in FUNKTIONEN if f not in defs] + [z for z in ZUWEISUNGEN if z not in zuw]
    if fehlend:
        raise AssertionError(f"fehlt in app.py: {fehlend}")
    modul = ast.Module(body=[zuw[z] for z in ZUWEISUNGEN] + [defs[f] for f in FUNKTIONEN], type_ignores=[])
    st = types.SimpleNamespace(session_state={})
    ns = {"html": html, "bisect": bisect, "datetime": datetime, "pd": pd, "math": math, "re": re,
          "config": config, "nutzerdaten": N, "st": st}
    exec(compile(modul, pfad, "exec"), ns)
    return ns, st


A, ST = _lade_app()


class AppPfade(unittest.TestCase):
    def tearDown(self):
        ST.session_state.clear()

    def test_upfad_admin_ohne_login_benutzer(self):
        ST.session_state["_nutzer"] = ADMIN
        self.assertEqual(A["upfad"]("state/positionen.json"), "state/positionen.json")
        self.assertFalse(A["eigener_bereich"]())
        ST.session_state.pop("_nutzer")
        self.assertEqual(A["upfad"]("state/trades_db.json"), "state/trades_db.json")
        self.assertFalse(A["eigener_bereich"]())
        ST.session_state["_nutzer"] = ANNA
        self.assertEqual(A["upfad"]("state/trades_db.json"), "state/benutzer/anna-muller/trades_db.json")
        self.assertEqual(A["upfad"]("state/musterdepot.json"), "state/benutzer/anna-muller/musterdepot.json")
        self.assertTrue(A["eigener_bereich"]())

    def test_marktdaten_bleiben_gemeinsam(self):
        # Gemeinsame Dateien werden in app.py nie ueber upfad gelesen
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"), encoding="utf-8") as f:
            text = f.read()
        for gemeinsam in ("STATE_PATH_HIGH_WATERMARK", "STATE_PATH_FETCH_FAIL_ALARM", "STATE_PATH_APP_ERROR",
                          "state/top50", "state/qualitaet"):
            self.assertNotRegex(text, r"upfad\([^)]*" + re.escape(gemeinsam))
        for eigen in ("upfad(STATE_PATH_POSITIONEN)", "upfad(STATE_PATH_BEOBACHTUNG)", "upfad(STATE_PATH_ENTNAHME)",
                      "upfad(config.STATE_PATH_SPARPLAN)", "upfad(config.STATE_PATH_TRADES_DB)",
                      "upfad(PFAD_MUSTERDEPOT)", "upfad(STATE_PATH_AUFLEGUNG)"):
            self.assertIn(eigen, text)


class LeeresDepot(unittest.TestCase):
    def test_startbestand(self):
        self.assertEqual(A["positionen_oder_start"](None, True), [])
        self.assertEqual(A["positionen_oder_start"]([], True), [])
        admin = A["positionen_oder_start"](None, False)
        self.assertEqual(len(admin), 1)
        self.assertEqual(admin[0]["id"], "config-hauptposition")
        eigene = [{"id": "p1", "name": "ETF"}]
        self.assertEqual(A["positionen_oder_start"](eigene, True), eigene)
        self.assertEqual(A["positionen_oder_start"](eigene, False), eigene)

    def test_aufteilung(self):
        name, weitere = A["depot_aufteilung"]([], True)
        self.assertEqual(weitere, [])
        self.assertIn(config.WKN, name)
        pos = [{"id": "a", "name": "Haupt"}, {"id": "b", "name": "ETF"}]
        self.assertEqual(A["depot_aufteilung"](pos, False), ("Haupt", [pos[1]]))
        self.assertEqual(A["depot_aufteilung"](pos, True)[1], pos)          # Benutzer: alles eigene Positionen
        self.assertEqual(A["depot_aufteilung"]([], False), ("Depotwert", []))

    def test_hauptposition_und_entnahme_standard(self):
        self.assertTrue(A["haupt_position_aktiv"](False, [], 0.0))
        self.assertFalse(A["haupt_position_aktiv"](True, [], 0.0))
        self.assertTrue(A["haupt_position_aktiv"](True, [(datetime.date(2026, 1, 1), 50.0)], 0.0))
        self.assertEqual(A["entnahme_standard"](True), 0.0)
        self.assertEqual(A["entnahme_standard"](False), float(getattr(config, "ENTNAHME_PM", 0.0) or 0.0))
        self.assertEqual(A["entnahme_rate_aus_state"](None, A["entnahme_standard"](True)), 0.0)

    def test_kennzahlen_ohne_kapital_kein_absturz(self):
        k = A["depot_kennzahlen"](0.0, 0.0, 333.3, 0.0, 0.0, 0.0, 0)
        self.assertEqual((k["brutto"], k["einstand"], k["gewinn"], k["rendite_pct"], k["netto"]), (0, 0, 0, 0.0, 0))
        self.assertEqual(A["gesamt_perioden_berechnen"]([], ["Tag", "Woche"]), [])
        idx = pd.bdate_range("2026-01-01", "2026-03-31")
        df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
        self.assertEqual(set(A["berechne_reale_stueckzahl"](df, 0.0, 50.0, [datetime.date(2026, 2, 1)], 1.0)), {0.0})
        self.assertEqual(A["kumulierte_entnahme"](idx[:3], [], 0.0), [0.0, 0.0, 0.0])

    def test_auflegungen(self):
        g = {"1": {"datum": "2020-01-01", "kurs": 100.0}, "2": {"datum": "2021-01-01", "kurs": 100.0}}
        e = {"2": {"datum": "2022-02-02", "kurs": 100.0}}
        self.assertEqual(A["auflegungen_zusammen"](g, e)["2"]["datum"], "2022-02-02")
        self.assertEqual(A["auflegungen_zusammen"](g, e)["1"]["datum"], "2020-01-01")
        self.assertEqual(A["auflegungen_zusammen"](None, None), {})


class RechnerEingabenSammeln(unittest.TestCase):
    def test_zinsrechner_nur_echte_eingaben(self):
        prefix, aus = A["RECHNER_EINGABEN"]["zinsrechner"]
        ss = {"zr_a": 1000.0, "zr_calc": "e", "zr_sp": "2x200", "zr_zielwert": None, "zr_init": True,
              "zr_dis_e_= 5 €": "= 5 €", "zr_sp_tab_3": {"edited_rows": {}}, "zr_sp_ver": 3, "zr_sp_neu": False,
              "zr_pdf": False, "zr_chart": None, "zr_sd_d": datetime.date(2026, 1, 1), "zr_sp_an": True,
              "abf_summe": 5.0, "anders": 1}
        self.assertEqual(A["eingaben_sammeln"](ss, prefix, aus),
                         {"zr_a": 1000.0, "zr_calc": "e", "zr_sp": "2x200", "zr_zielwert": None})

    def test_abfindung_ohne_tabellen(self):
        prefix, aus = A["RECHNER_EINGABEN"]["abfindung"]
        ss = {"abf_summe": 5.0, "abf_jahr1": 2026, "abf_g_immo": True, "abf_fj_tab_1_2_3_4": {"x": 1},
              "abf_pdf": False, "abf_av_betrag": 123.0, "abf_vorjahr": None, "zr_a": 1.0}
        self.assertEqual(A["eingaben_sammeln"](ss, prefix, aus),
                         {"abf_summe": 5.0, "abf_jahr1": 2026, "abf_g_immo": True, "abf_vorjahr": None})


if __name__ == "__main__":
    unittest.main()


class NamenUndOrdner(unittest.TestCase):                   # Audit A-03
    def test_kollidierende_namen_abgelehnt(self):
        import nutzerdaten as N
        self.assertIsNotNone(N.name_pruefen("anna.b", ["anna-b"]))     # unerlaubtes Zeichen
        self.assertIsNotNone(N.name_pruefen("anna-b", ["anna_b", "anna-b"]))
        self.assertIsNotNone(N.name_pruefen("jörg", []))
        self.assertIsNotNone(N.name_pruefen("chef", [], ("chef",)))
        self.assertIsNotNone(N.name_pruefen("benutzer", []))
        self.assertIsNotNone(N.name_pruefen("a", []))
        self.assertIsNone(N.name_pruefen("anna_b", ["anna-b"]))

    def test_erlaubte_namen_haben_eigene_ordner(self):
        import nutzerdaten as N
        for n in ("anna", "anna-b", "anna_b", "a1", "x" * 40):
            self.assertIsNone(N.name_pruefen(n, []), n)
            self.assertEqual(N.slug(n), n)

    def test_bestehende_kollisionen_melden(self):
        import nutzerdaten as N
        self.assertEqual(N.slug_kollisionen(["anna.b", "anna-b", "max"]), {"anna-b": ["anna-b", "anna.b"]})
