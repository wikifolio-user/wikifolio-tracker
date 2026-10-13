"""Tests fuer abfindung_modelle.py (python3 -m unittest test_abfindung_modelle)."""
import datetime as dt
import unittest
from decimal import Decimal

import abfindung as A
import abfindung_modelle as M

D = Decimal


def fall(**kw):
    f = {"brutto_monat": 4000, "art": "ag_betriebsbedingt", "hinweis_1a": True, "klage": False,
         "betrieb_gross": True, "alter": 45, "sonder_einbeziehen": False}
    f.update(kw)
    return f


ST_E = {"zve": 40000.0, "splitting": False, "kirche": 0.0, "alg": 0.0, "fuenftel_moeglich": True}


class Beschaeftigung(unittest.TestCase):
    def test_volle_jahre(self):
        b = M.beschaeftigung(dt.date(2016, 1, 1), dt.date(2025, 12, 31))
        self.assertEqual((b["jahre"], b["monate"], b["tage"], b["jahre_1a"]), (10, 0, 0, 10))

    def test_2_genau_sechs_monate_keine_aufrundung(self):
        b = M.beschaeftigung(dt.date(2019, 1, 1), dt.date(2025, 6, 30))
        self.assertEqual((b["jahre"], b["monate"], b["tage"]), (6, 6, 0))
        self.assertEqual(b["jahre_1a"], 6)

    def test_3_mehr_als_sechs_monate_aufrunden(self):
        b = M.beschaeftigung(dt.date(2019, 1, 1), dt.date(2025, 7, 1))
        self.assertEqual(b["jahre_1a"], 7)
        b = M.beschaeftigung(dt.date(2019, 1, 1), dt.date(2025, 8, 31))
        self.assertEqual((b["monate"], b["jahre_1a"]), (8, 7))

    def test_vorzeiten_und_ungueltig(self):
        b = M.beschaeftigung(dt.date(2020, 1, 1), dt.date(2024, 12, 31), vorzeit_monate=14)
        self.assertEqual((b["jahre"], b["monate"]), (6, 2))
        self.assertIsNone(M.beschaeftigung(dt.date(2025, 1, 1), dt.date(2024, 1, 1)))
        self.assertIsNone(M.beschaeftigung(None, dt.date(2024, 1, 1)))

    def test_schaltjahr_monatsende(self):
        b = M.beschaeftigung(dt.date(2020, 2, 29), dt.date(2021, 2, 27))
        self.assertEqual((b["jahre"], b["monate"], b["tage"]), (0, 11, 30))
        b = M.beschaeftigung(dt.date(2020, 2, 29), dt.date(2021, 2, 28))
        self.assertEqual((b["jahre"], b["monate"], b["tage"]), (1, 0, 0))
        b = M.beschaeftigung(dt.date(2026, 3, 1), dt.date(2026, 3, 10))
        self.assertEqual((b["jahre"], b["monate"], b["tage"]), (0, 0, 10))


class Modelle(unittest.TestCase):
    def test_1_faktor_05_zehn_jahre(self):
        m = M.m_faktor(D(4000), D(10), D("0.5"))
        self.assertEqual(m["brutto"], D("20000.00"))
        r = M.alle_modelle(fall(beginn=dt.date(2016, 1, 1), ende=dt.date(2025, 12, 31)))
        a1 = next(x for x in r["modelle"] if x["key"] == "1a")
        self.assertEqual(a1["brutto"], D("20000.00"))
        self.assertTrue(a1["anwendbar"])

    def test_2_und_3_1a_rundung(self):
        r6 = M.alle_modelle(fall(beginn=dt.date(2019, 1, 1), ende=dt.date(2025, 6, 30)))
        r7 = M.alle_modelle(fall(beginn=dt.date(2019, 1, 1), ende=dt.date(2025, 7, 1)))
        self.assertEqual(next(x for x in r6["modelle"] if x["key"] == "1a")["brutto"], D("12000.00"))
        self.assertEqual(next(x for x in r7["modelle"] if x["key"] == "1a")["brutto"], D("14000.00"))

    def test_1a_nicht_bei_klage_oder_kleinbetrieb(self):
        for kw in ({"klage": True}, {"betrieb_gross": False}, {"art": "aufhebung"}, {"hinweis_1a": False}):
            r = M.alle_modelle(fall(beginn=dt.date(2016, 1, 1), ende=dt.date(2025, 12, 31), **kw))
            a1 = next(x for x in r["modelle"] if x["key"] == "1a")
            self.assertFalse(a1["anwendbar"], kw)
            self.assertIsNone(a1["brutto"])

    def test_1a_unbekannt_bleibt_pruefen(self):
        r = M.alle_modelle(fall(beginn=dt.date(2016, 1, 1), ende=dt.date(2025, 12, 31), hinweis_1a=None))
        a1 = next(x for x in r["modelle"] if x["key"] == "1a")
        self.assertTrue(a1["anwendbar"])
        self.assertIn(None, [v["erfuellt"] for v in a1["voraussetzungen"]])

    def test_4_obergrenze_50_15(self):
        self.assertEqual(M.obergrenze_10(50, 15), 15)
        self.assertEqual(M.obergrenze_10(50, 14), 12)
        self.assertEqual(M.obergrenze_10(49, 30), 12)

    def test_5_obergrenze_55_20_und_regelalter(self):
        self.assertEqual(M.obergrenze_10(55, 20), 18)
        self.assertEqual(M.obergrenze_10(55, 19), 15)
        self.assertEqual(M.obergrenze_10(67, 30, regelalter_erreicht=True), 12)
        r = M.alle_modelle(fall(alter=56, beginn=dt.date(2000, 1, 1), ende=dt.date(2025, 12, 31)))
        g = next(x for x in r["modelle"] if x["key"] == "gericht")
        self.assertEqual(g["brutto"], D("72000.00"))
        self.assertIn("Höchstgrenze", g["status"])

    def test_monatsverdienst_sonderzahlungen(self):
        mv, teile = M.monatsverdienst({"brutto_monat": 4000, "weihnachtsgeld": 4000, "urlaubsgeld": 1200,
                                       "sachbezug": 300, "sonder_einbeziehen": True})
        self.assertEqual(mv, D("4733.33"))
        mv2, _ = M.monatsverdienst({"brutto_monat": 4000, "weihnachtsgeld": 4000, "sonder_einbeziehen": False})
        self.assertEqual(mv2, D("4000.00"))

    def test_8_sozialplan(self):
        r = {"methode": "faktor", "faktor": 0.8, "sockel": 5000, "kind": 2500, "max": 60000}
        brutto, teile, _ = M.regelwerk({"kinder": 2}, D(4000), D(15), r)
        # 4000 * 15 * 0.8 = 48000 + 5000 + 5000 = 58000 (unter Deckel)
        self.assertEqual(brutto, D("58000.00"))
        brutto, teile, _ = M.regelwerk({"kinder": 2}, D(4000), D(20), r)
        self.assertEqual(brutto, D("60000.00"))
        self.assertTrue(any("Kappung" in t for t, _ in teile))

    def test_sozialplan_divisor_punkte_staffel_quote(self):
        b, _, _ = M.regelwerk({"alter": 50}, D(4000), D(20), {"methode": "divisor", "divisor": 40})
        self.assertEqual(b, D("100000.00"))
        b, _, _ = M.regelwerk({"alter": 40, "kinder": 1, "schwerbehindert": True}, D(4000), D(10),
                              {"methode": "punkte", "punktwert": 100, "p_jahr": 10, "p_alter": 1, "p_kind": 5,
                               "p_sb": 10})
        self.assertEqual(b, D("15500.00"))      # (100 + 40 + 5 + 10) * 100
        b, _, _ = M.regelwerk({"alter": 52}, D(4000), D(12), {"methode": "faktor", "faktor": 0.5,
                                                              "staffel": [(10, 0.7)],
                                                              "altersstaffel": [(45, 0.1), (50, 0.2)]})
        self.assertEqual(b, D("43200.00"))      # 4000 * 12 * (0.7 + 0.2)
        self.assertEqual(M.sozialplan_quote(800000, 1000000), D("80.00"))
        b, _, _ = M.regelwerk({}, D(4000), D(10), {"methode": "faktor", "faktor": 1, "quote": 80})
        self.assertEqual(b, D("32000.00"))
        b, _, _ = M.regelwerk({}, D(4000), D(1), {"methode": "faktor", "faktor": 0.5, "min": 5000})
        self.assertEqual(b, D("5000.00"))

    def test_9_insolvenz_gesamtvolumen(self):
        p = {"summe_mv": 400000, "summe_ansprueche": 2000000, "masse": 9000000, "nach_eroeffnung": True}
        r = M.insolvenz(50000, p)
        self.assertEqual(r["quote"], D("50.00"))           # 2,5 * 400.000 = 1 Mio. von 2 Mio.
        self.assertEqual(r["auszahlung"], D("25000.00"))
        r = M.insolvenz(50000, dict(p, masse=1500000))     # Drittel der Masse 500.000
        self.assertEqual(r["quote"], D("25.00"))
        r = M.insolvenz(50000, {"summe_mv": 400000, "summe_ansprueche": 500000, "masse": 9000000})
        self.assertEqual(r["auszahlung"], D("50000.00"))   # innerhalb der Grenzen: keine Kuerzung

    def test_turbo_ohne_doppelzaehlung(self):
        t = M.turbo(D(4000), dt.date(2026, 12, 31), dt.date(2026, 9, 30), 50, 0, 1000)
        self.assertEqual(t["monate"], D("3.00"))          # Oktober bis Dezember
        self.assertEqual(t["praemie"], D("6000.00"))
        self.assertEqual(t["gesamt"], D("7000.00"))
        self.assertEqual(M.turbo(D(4000), dt.date(2026, 9, 30), dt.date(2026, 12, 31), 50)["praemie"], D("0.00"))

    def test_personengruppen(self):
        r = M.alle_modelle(fall(sonder={"organ": True}))
        self.assertEqual(r["personengruppe"], "organ")
        self.assertFalse(any(x["key"] == "1a" for x in r["modelle"]))

    def test_vertrag_trennt_entgelt(self):
        m = M.m_vertrag("aufhebung", "Aufhebungsvertrag", D(4000), D(10), betrag=30000,
                        zusatz=[("Urlaubsabgeltung", 2000, "entgelt"), ("Startbonus", 1000, "abfindung")])
        self.assertEqual(m["brutto"], D("31000.00"))
        self.assertTrue(any(a == "entgelt" for _, _, a in m["bestandteile"]))


class Steuer(unittest.TestCase):
    def test_6_fuenftel_2026(self):
        mit = M.steuer_netto(30000, ST_E, 2026, fuenftel=True)
        ohne = M.steuer_netto(30000, ST_E, 2026, fuenftel=False)
        self.assertLess(mit["steuer"], ohne["steuer"])
        self.assertEqual(mit["netto"], D("30000.00") - mit["steuer"])
        self.assertEqual(mit["erstattung"], ohne["steuer"] - mit["steuer"])
        # Gegenrechnung mit der Fuenftelformel aus abfindung.py
        basis = A.est(40000, jahr=2026)
        erwartet = 5 * (A.est(40000 + 6000, jahr=2026) - basis)
        self.assertEqual(mit["est"], M.eur(erwartet))

    def test_10_jahreswechsel(self):
        a = M.steuer_netto(60000, dict(ST_E, zve=60000.0), 2026)
        b = M.steuer_netto(60000, dict(ST_E, zve=0.0), 2027)
        self.assertLess(b["steuer"], a["steuer"])
        self.assertEqual(a["jahr"], 2026)
        self.assertEqual(b["jahr"], 2027)

    def test_brutto_fuer_netto(self):
        br = M.brutto_fuer_netto(25000, ST_E, 2026)
        self.assertGreaterEqual(M.steuer_netto(br, ST_E, 2026)["netto"], D("25000.00"))
        self.assertLess(M.steuer_netto(br - D("1"), ST_E, 2026)["netto"], D("25000.00"))
        self.assertEqual(M.brutto_fuer_netto(0, ST_E), D("0.00"))

    def test_null_und_status(self):
        self.assertEqual(M.steuer_netto(0, ST_E)["steuer"], D("0.00"))
        self.assertEqual(M.fuenftel_status(30000, 40000, 60000)[0], "anwendbar")
        self.assertEqual(M.fuenftel_status(10000, 40000, 60000)[0], "nicht anwendbar")
        self.assertEqual(M.fuenftel_status(30000, 40000, None)[0], "prüfen")
        self.assertEqual(M.fuenftel_status(30000, 40000, 60000, teilzahlung_pct=20)[0], "nicht anwendbar")


class Arbeitslosengeld(unittest.TestCase):
    def test_7_ruhen_aufhebung_frist_nicht_eingehalten(self):
        # 10 Jahre -> Frist 4 Monate zum Monatsende; Vertrag am 15.03.2026, Ende 31.03.2026
        f = fall(art="aufhebung", zugang=dt.date(2026, 3, 15), ende=dt.date(2026, 3, 31), beginn=dt.date(2016, 1, 1),
                 jahresentgelt=48000, alter=45)
        dauer = M.beschaeftigung(f["beginn"], f["ende"])
        c = M.alg_check(f, dauer, 40000, D(4000))
        self.assertEqual(c["fiktives_ende"], dt.date(2026, 7, 31))
        self.assertFalse(c["frist_ok"])
        r = c["ruhen"]
        # Anteil: 60 - 2*5 (10 Jahre) - 2*5 (45 Jahre: 10 J. ueber 35) = 40 %; 16.000 € / (48.000/365) = 121 Tage
        self.assertEqual(r["anteil"], 40)
        self.assertEqual(r["tage_anteil"], 121)
        self.assertEqual(r["bis"], dt.date(2026, 7, 30))      # 31.03. + 121 Tage, vor dem Fristende
        self.assertEqual(c["sperrzeit"]["stufe"], "hoch")

    def test_ruhen_mindestanteil_und_jahresgrenze(self):
        r = M.ruhen_158(500000, dt.date(2026, 1, 31), dt.date(2028, 1, 31), 50000, 64, 30)
        self.assertEqual(r["anteil"], 25)
        self.assertEqual(r["grund"], "ein Jahr")
        self.assertIsNone(M.ruhen_158(10000, dt.date(2026, 6, 30), dt.date(2026, 6, 30), 50000, 40, 5))

    def test_ag_kuendigung_keine_sperrzeit_klagefrist(self):
        f = fall(zugang=dt.date(2026, 3, 2), ende=dt.date(2026, 7, 31), beginn=dt.date(2016, 1, 1))
        c = M.alg_check(f, M.beschaeftigung(f["beginn"], f["ende"]), 20000, D(4000))
        self.assertEqual(c["sperrzeit"]["stufe"], "gering")
        self.assertIsNone(c["ruhen"])
        self.assertEqual(c["klagefrist"]["bis"], dt.date(2026, 3, 23))
        self.assertEqual(c["meldung"]["spaetestens"], dt.date(2026, 4, 30))

    def test_wichtiger_grund_korridor(self):
        f = fall(art="aufhebung", drohende_ag_kuendigung=True, zugang=dt.date(2026, 3, 2), ende=dt.date(2026, 7, 31),
                 beginn=dt.date(2016, 1, 1))
        dauer = M.beschaeftigung(f["beginn"], f["ende"])
        c = M.alg_check(f, dauer, 4000 * 0.5 * float(dauer["jahre_dezimal"]), D(4000))
        self.assertEqual(c["sperrzeit"]["stufe"], "gering")
        c = M.alg_check(f, dauer, 4000 * 1.0 * float(dauer["jahre_dezimal"]), D(4000))
        self.assertEqual(c["sperrzeit"]["stufe"], "hoch")

    def test_fristen_622(self):
        self.assertEqual(M.gesetzliche_frist_monate(1), 0)
        self.assertEqual(M.gesetzliche_frist_monate(2), 1)
        self.assertEqual(M.gesetzliche_frist_monate(20), 7)
        self.assertEqual(M.fristende(dt.date(2026, 3, 2), 0, wochen4=True), dt.date(2026, 3, 31))
        self.assertEqual(M.fristende(dt.date(2026, 3, 10), 0, wochen4=True), dt.date(2026, 4, 15))
        self.assertEqual(M.alg_dauer(48, 58), 24)
        self.assertEqual(M.alg_dauer(24, 40), 12)
        self.assertEqual(M.alg_dauer(10, 40), 0)


if __name__ == "__main__":
    unittest.main()


class Oberflaeche(unittest.TestCase):
    def test_gemerkte_werte_pruefen(self):
        import abfindung_ui as U
        self.assertEqual(U.gueltig("abf_f_beginn", "2010-05-01"), (True, dt.date(2010, 5, 1)))
        self.assertEqual(U.gueltig("abf_f_art", "falsch")[0], False)
        self.assertEqual(U.gueltig("abf_f_sonderf", ["rentennah", "xx"]), (True, ["rentennah"]))
        self.assertEqual(U.gueltig("abf_v_auf_betrag", None), (True, None))
        self.assertEqual(U.gueltig("abf_f_alter", 52.0), (True, 52))
        self.assertFalse(U.gueltig("abf_f_alter", True)[0])
        self.assertFalse(U.gueltig("unbekannt", 1)[0])

    def test_staffel_und_fall(self):
        import abfindung_ui as U
        self.assertEqual(U._staffel("10: 0,7; 20:0.9; quatsch"), [(10.0, 0.7), (20.0, 0.9)])
        f = U.fall_aus_session({"abf_f_mon": 5000.0, "abf_f_sonderf": ["kleinbetrieb"]})
        self.assertFalse(f["betrieb_gross"])
        self.assertEqual(f["jahresentgelt"], 60000.0)
        f0 = U.fall_aus_session({}, null=True)
        self.assertEqual(f0["brutto_monat"], 0.0)
        self.assertIsNone(f0["beginn"])
        cfg = U.cfg_aus_session({"abf_sp_an": True, "abf_sp_faktor": 0.8, "abf_sp_budget": 800000.0,
                                 "abf_sp_summe": 1000000.0})
        self.assertEqual(cfg["sozialplan"]["quote"], 80.0)
