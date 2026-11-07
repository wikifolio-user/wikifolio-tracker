"""EKS-Investmentbewertung: Kennzahlen mit nachrechenbaren Beispielen, Randfaelle, Datenmodell, Export/Import.
Laeuft mit unittest (wie CI) und mit pytest."""
import datetime
import unittest

from eks_rechner import modell as M
from eks_rechner import rechnen as R


def fin(**w):
    f = dict(M.STANDARD_FINANZEN)
    f.update(start_invest=1200.0, umsatz_monat=1000.0, var_kosten_pct=20.0, fix_monat=200.0, stunden_woche=5.0,
             anlauf_monate=0, horizont_jahre=1, steuersatz_pct=0.0)
    f.update(w)
    return f


REAL = {"umsatz": 1.0, "kosten": 1.0}


class Cashflow(unittest.TestCase):
    def test_einfaches_beispiel(self):
        """1.000 € Umsatz - 20 % variabel (200) - 200 fix = 600 € je Monat; Investition 1.200 €."""
        v = R.verlauf(fin())
        self.assertEqual(len(v), 13)                               # Monat 0 + 12 Monate (Horizont 1 Jahr)
        self.assertEqual(v[0]["cashflow"], -1200)
        self.assertTrue(all(abs(z["cashflow"] - 600) < 1e-9 for z in v[1:]))
        self.assertAlmostEqual(v[-1]["kumuliert"], -1200 + 12 * 600)
        self.assertEqual(R.amortisation(v), 2)                     # -600 nach Monat 1, 0 nach Monat 2
        self.assertEqual(R.break_even_monat(v), 1)
        self.assertAlmostEqual(R.break_even_umsatz(fin()), 200 / 0.8)
        self.assertAlmostEqual(R.npv([z["cashflow"] for z in v], 0.0), 6000)
        self.assertAlmostEqual(R.euro_je_stunde(fin(), v), 600 / (5 * 52 / 12))

    def test_steuer_jaehrlich_mit_abschreibung(self):
        """Jahr 1: 12 x 600 = 7.200 € Gewinn - 400 € Abschreibung (1.200 € / 3 Jahre) = 6.800 € x 30 % = 2.040 €,
        gezahlt im 12. Monat; Gewerbesteuer 0 (unter dem Freibetrag 24.500 €)."""
        v = R.verlauf(fin(steuersatz_pct=30.0, afa_jahre=3))
        self.assertAlmostEqual(v[1]["cashflow"], 600)
        self.assertAlmostEqual(v[12]["steuer"], 6800 * 0.3)
        self.assertAlmostEqual(v[12]["cashflow"], 600 - 2040)
        sofort = R.verlauf(fin(steuersatz_pct=30.0, afa_jahre=0))           # 0 = sofort im 1. Jahr absetzen
        self.assertAlmostEqual(sofort[12]["steuer"], (7200 - 1200) * 0.3)
        verlust = R.verlauf(fin(umsatz_monat=100.0, steuersatz_pct=30.0))
        self.assertAlmostEqual(sum(z["steuer"] for z in verlust), 0.0)      # kein Steuerabzug im Verlust
        self.assertAlmostEqual(verlust[1]["cashflow"], 100 - 20 - 200)

    def test_verlustvortrag(self):
        """Hochlauf ueber 24 Monate: Jahr 1 = 3.250 - 7.200 = -3.950 € (Vortrag), Jahr 2 = 9.250 - 7.200 = 2.050 €
        -> voll mit dem Vortrag verrechnet, keine Steuer."""
        f = fin(umsatz_monat=1000.0, var_kosten_pct=0.0, fix_monat=600.0, start_invest=0.0, anlauf_monate=24,
                horizont_jahre=2, steuersatz_pct=30.0)
        v = R.verlauf(f)
        self.assertAlmostEqual(sum(z["gewinn_vor"] for z in v[1:13]), 3250 - 7200)
        self.assertAlmostEqual(sum(z["gewinn_vor"] for z in v[13:25]), 9250 - 7200)
        self.assertAlmostEqual(sum(z["steuer"] for z in v), 0.0)

    def test_gewerbesteuer(self):
        est, gewst = R.jahressteuer(100000, 0.42, 400)
        mess = (100000 - 24500) * 0.035
        self.assertAlmostEqual(gewst, mess * 4)
        self.assertAlmostEqual(est + gewst, 42000)                  # Hebesatz 400 %: voll angerechnet
        est, gewst = R.jahressteuer(100000, 0.42, 490)
        self.assertAlmostEqual(est + gewst, 42000 + mess * 4.9 - mess * 4)
        self.assertEqual(R.jahressteuer(20000, 0.42, 400)[1], 0.0)   # unter dem Freibetrag
        self.assertEqual(R.jahressteuer(-5, 0.42, 400), (0.0, 0.0))

    def test_linearer_hochlauf(self):
        v = R.verlauf(fin(var_kosten_pct=0.0, fix_monat=0.0, anlauf_monate=4, start_invest=0.0))
        self.assertEqual([round(z["umsatz"]) for z in v[1:6]], [250, 500, 750, 1000, 1000])
        self.assertAlmostEqual(v[-1]["kumuliert"], 250 + 500 + 750 + 9 * 1000)

    def test_szenario_faktoren(self):
        v = R.verlauf(fin(), umsatz_faktor=1.3, kosten_faktor=0.95)
        u = 1300.0
        self.assertAlmostEqual(v[1]["cashflow"], u - u * 0.20 * 0.95 - 200 * 0.95)
        self.assertAlmostEqual(R.break_even_umsatz(fin(), 0.95), 190 / (1 - 0.19))


class Zinsrechnung(unittest.TestCase):
    def test_npv_monatlich_diskontiert(self):
        r = 1.07 ** (1 / 12) - 1
        cfs = [-1200] + [600] * 12
        erwartet = -1200 + sum(600 / (1 + r) ** t for t in range(1, 13))
        self.assertAlmostEqual(R.npv(cfs, 0.07), erwartet)
        self.assertAlmostEqual(R.npv([0] * 12 + [1070], 0.07), 1000.0)   # 1.070 € in 12 Monaten bei 7 % = 1.000 €

    def test_irr_nachrechenbar(self):
        self.assertAlmostEqual(R.irr([-1000] + [0] * 11 + [1100]), 0.10, places=6)
        self.assertAlmostEqual(R.npv([-1200] + [600] * 12, R.irr([-1200] + [600] * 12)), 0.0, places=4)

    def test_irr_mit_jaehrlicher_steuer(self):
        """Steuerzahlung im 12./24./36. Monat erzeugt mehrere Vorzeichenwechsel - IRR muss trotzdem gefunden werden."""
        f = fin(start_invest=1500.0, umsatz_monat=2500.0, steuersatz_pct=30.0, horizont_jahre=3, anlauf_monate=6)
        cfs = [z["cashflow"] for z in R.verlauf(f)]
        self.assertLess(cfs[-1], 0)                                 # letzter Monat: Steuer > Monatsgewinn
        i = R.irr(cfs)
        self.assertIsNotNone(i)
        self.assertGreater(i, 0)                                    # NPV > 0 bei 0 % -> positiver Zinsfuss
        self.assertAlmostEqual(R.npv(cfs, i), 0.0, places=3)
        verlust = [-1000] + [-50] * 11 + [600]                      # NPV bei 0 % negativ -> negativer Zinsfuss
        self.assertLess(R.irr(verlust), 0)
        self.assertAlmostEqual(R.npv(verlust, R.irr(verlust)), 0.0, places=3)

    def test_irr_nicht_definiert(self):
        self.assertIsNone(R.irr([-100, -50, -50]))                 # nur Verluste
        self.assertIsNone(R.irr([0, 50, 50]))                      # ohne Investition
        self.assertIsNone(R.irr([]))


class Randfaelle(unittest.TestCase):
    def test_kein_break_even(self):
        f = fin(umsatz_monat=300.0, var_kosten_pct=0.0, fix_monat=500.0)
        v = R.verlauf(f)
        self.assertIsNone(R.break_even_monat(v))
        self.assertIsNone(R.amortisation(v))
        s = R.szenario(f, REAL, 0.07)
        self.assertIsNone(s["irr"])
        self.assertLess(s["npv"], 0)
        self.assertAlmostEqual(s["break_even_umsatz"], 500.0)

    def test_umsatz_null(self):
        f = fin(umsatz_monat=0.0)
        s = R.szenario(f, REAL, 0.07)
        self.assertIsNone(s["break_even_monat"])
        self.assertIsNone(s["amortisation"])
        self.assertAlmostEqual(s["summe_cf"], -1200 - 12 * 200)
        self.assertAlmostEqual(s["euro_h"], -200 / (5 * 52 / 12))
        self.assertIsNone(s["irr"])

    def test_horizont_ein_jahr_und_ohne_investition(self):
        v = R.verlauf(fin(start_invest=0.0))
        self.assertEqual(len(v), 13)
        self.assertEqual(R.amortisation(v), 0)

    def test_variable_kosten_100_prozent(self):
        self.assertIsNone(R.break_even_umsatz(fin(var_kosten_pct=100.0)))

    def test_ohne_stunden(self):
        self.assertIsNone(R.euro_je_stunde(fin(stunden_woche=0.0), R.verlauf(fin(stunden_woche=0.0))))


class Scores(unittest.TestCase):
    def setUp(self):
        self.e = M.standard_einstellungen()
        self.i = M.neue_idee("Test", self.e)

    def test_nutzwert(self):
        # alle Scores 5: normal (5-1)/9 = 44,4 % (50 % Gewicht), invers (10-5)/9 = 55,6 % (50 % Gewicht)
        self.assertAlmostEqual(R.nutzwert(self.i, self.e["kriterien"]), 0.5 * 4 / 9 * 100 + 0.5 * 5 / 9 * 100)
        for k in self.e["kriterien"]:
            self.i["kriterien"][k["id"]] = 1 if k["invers"] else 10
        self.assertAlmostEqual(R.nutzwert(self.i, self.e["kriterien"]), 100.0)
        for k in self.e["kriterien"]:
            self.i["kriterien"][k["id"]] = 10 if k["invers"] else 1
        self.assertAlmostEqual(R.nutzwert(self.i, self.e["kriterien"]), 0.0)

    def test_nutzwert_gewichtet(self):
        kr = [{"id": "a", "name": "A", "gewicht": 75, "invers": False},
              {"id": "b", "name": "B", "gewicht": 25, "invers": True}]
        i = {"kriterien": {"a": 10, "b": 10}}
        self.assertAlmostEqual(R.nutzwert(i, kr), 75.0)            # A voll, B (invers, 10) = 0
        self.assertIsNone(R.nutzwert(i, [dict(k, gewicht=0) for k in kr]))

    def test_eks_score(self):
        self.assertAlmostEqual(R.eks_score(self.i), 50.0)
        for nr in self.i["phasen"]:
            self.i["phasen"][nr]["score"] = 10
        self.assertAlmostEqual(R.eks_score(self.i), 100.0)


class Ampel(unittest.TestCase):
    E = {"schwelle_nutzwert": 60, "mindest_stundensatz": 25}

    def test_stufen(self):
        self.assertEqual(R.ampel(70, 100, 30, self.E), ("gruen", []))
        self.assertEqual(R.ampel(50, 100, 30, self.E)[0], "gelb")
        self.assertEqual(R.ampel(70, -1, 30, self.E)[0], "gelb")
        self.assertEqual(R.ampel(70, 100, 20, self.E)[0], "gelb")
        self.assertEqual(R.ampel(50, -1, 30, self.E)[0], "rot")
        self.assertEqual(R.ampel(50, -1, 20, self.E)[0], "rot")
        self.assertEqual(R.ampel(70, 100, None, self.E)[0], "gruen")   # keine Stunden -> kein Zeit-Engpass

    def test_auswerten_gesamt(self):
        e = M.standard_einstellungen()
        i = M.neue_idee("Kurs", e)
        i["finanzen"] = fin(horizont_jahre=3)
        for k in e["kriterien"]:
            i["kriterien"][k["id"]] = 2 if k["invers"] else 9
        self.assertEqual(R.auswerten(i, e)["ampel"], "gelb")         # EKS 50 < 60 und Engpass 5 < 6
        for nr in i["phasen"]:
            i["phasen"][nr]["score"] = 7
        r = R.auswerten(i, e)
        self.assertEqual(r["ampel"], "gruen")                      # NW 84, NPV > 0, 27,69 €/h >= 25, EKS 70
        self.assertGreater(r["npv"], 0)
        self.assertEqual(set(r["szenarien"]), {"pess", "real", "opt"})
        self.assertLess(r["szenarien"]["pess"]["npv"], r["npv"])
        self.assertLess(r["npv"], r["szenarien"]["opt"]["npv"])

    def test_eks_bedingung(self):
        e = dict(self.E, schwelle_eks=60, min_engpass=6)
        self.assertEqual(R.ampel(70, 100, 30, e, 70, 8), ("gruen", []))
        stufe, verfehlt = R.ampel(70, 100, 30, e, 70, 4)            # Score ok, aber Engpass schwach
        self.assertEqual((stufe, verfehlt), ("gelb", ["Engpass (Phase 4) zu schwach"]))
        self.assertEqual(R.ampel(70, -1, 30, e, 50, 8)[0], "rot")   # NPV und EKS verfehlt
        self.assertEqual(len(R.ampel(70, 100, 30, e, 50, 4)[1]), 1)  # EKS zaehlt als eine Bedingung

    def test_mindest_stundensatz_aus_job(self):
        e = {"mindest_stundensatz": 25, "netto_monat_job": 3250, "stunden_woche_job": 40, "mindest_aus_job": True}
        self.assertAlmostEqual(R.mindest_stundensatz(e), 3250 / (40 * 52 / 12))      # 18,75 €
        self.assertEqual(R.mindest_stundensatz(dict(e, mindest_aus_job=False)), 25)
        self.assertEqual(R.mindest_stundensatz(dict(e, stunden_woche_job=0)), 25)

    def test_sensitivitaet(self):
        s = R.sensitivitaet(fin(), REAL, 0.0)
        self.assertAlmostEqual(s["basis"], 6000)
        (n1, um, up), (n2, km, kp) = s["zeilen"]
        self.assertAlmostEqual(um, -1200 + 12 * (800 - 160 - 200))      # Umsatz -20 %
        self.assertAlmostEqual(up, -1200 + 12 * (1200 - 240 - 200))     # Umsatz +20 %
        self.assertAlmostEqual(km, -1200 + 12 * (1000 - 160 - 160))     # Kosten -20 %
        self.assertAlmostEqual(kp, -1200 + 12 * (1000 - 240 - 240))     # Kosten +20 %


class Erweiterungen(unittest.TestCase):
    def test_kapitalbedarf(self):
        v = R.verlauf(fin(var_kosten_pct=0.0, fix_monat=500.0, umsatz_monat=1000.0, anlauf_monate=4, start_invest=1000.0))
        # Monate 1-4: 250-500 = -250, 0, +250, +500 -> tiefster Stand nach Monat 1: -1.250
        self.assertEqual(R.kapitalbedarf(v), (1250.0, 1))
        self.assertEqual(R.kapitalbedarf(R.verlauf(fin(start_invest=0.0)))[0], 0.0)

    def test_anlauf_stunden(self):
        f = fin(stunden_woche=5.0, stunden_anlauf_woche=15.0, anlauf_monate=3, var_kosten_pct=0.0, fix_monat=0.0,
                start_invest=0.0)
        v = R.verlauf(f)
        h = 3 * 15 * 52 / 12 + 9 * 5 * 52 / 12
        self.assertAlmostEqual(sum(z["stunden"] for z in v), h)
        self.assertAlmostEqual(R.euro_je_stunde(f, v), (1000 / 3 + 2000 / 3 + 1000 + 9 * 1000) / h)

    def test_erwartungswert(self):
        sz = {"pess": {"npv": -100, "gewicht": 25}, "real": {"npv": 100, "gewicht": 50},
              "opt": {"npv": 300, "gewicht": 25}}
        self.assertAlmostEqual(R.erwartungswert(sz), 100.0)
        self.assertIsNone(R.erwartungswert({k: dict(v, gewicht=0) for k, v in sz.items()}))

    def _test_idee(self):
        e = M.standard_einstellungen()
        i = M.neue_idee("Test", e)
        i["finanzen"] = fin(horizont_jahre=1, start_invest=0.0)         # Plan: 600 € Gewinn je Monat, 21,67 h
        i["start_monat"] = "2026-09"
        i["ist"] = [{"monat": "2026-09", "umsatz": 500, "kosten": 300, "stunden": 30},
                    {"monat": "2026-10", "umsatz": 700, "kosten": 300, "stunden": 30},
                    {"monat": "2026-11", "umsatz": 400, "kosten": 300, "stunden": 30}]
        return M.idee_bereinigen(i, e), e

    def test_ist_vergleich(self):
        i, e = self._test_idee()
        v = R.ist_vergleich(i, R.verlauf(i["finanzen"]))
        self.assertEqual([z["m"] for z in v], [1, 2, 3])
        self.assertAlmostEqual(v[-1]["kum_ist"], 200 + 400 + 100)
        self.assertAlmostEqual(v[-1]["kum_plan"], 3 * 600)
        self.assertAlmostEqual(v[0]["plan_umsatz"], 1000)
        self.assertEqual(R.monat_index("2026-11", "2027-01"), 3)

    def test_abbruch_kriterien(self):
        i, e = self._test_idee()
        i["abbruch"] = M._abbruch([
            {"art": "umsatz_min", "wert": 500, "nach_monaten": 3},      # Monat 3: 400 < 500 -> greift
            {"art": "gewinn_kum_min", "wert": 1000, "nach_monaten": 2},  # 200 + 400 = 600 < 1000 -> greift
            {"art": "eur_h_min", "wert": 5, "nach_monaten": 3},          # 700 / 90 h = 7,78 >= 5 -> nicht
            {"art": "stunden_max", "wert": 10, "nach_monaten": 3},       # 30 h/Monat = 6,9 h/Woche -> nicht
            {"art": "umsatz_min", "wert": 500, "nach_monaten": 6},       # erst 3 Monate erfasst -> nicht
            {"art": "quatsch", "wert": 1}])
        self.assertEqual(len(i["abbruch"]), 5)
        treffer = R.auswerten(i, e)["abbruch"]
        self.assertEqual(len(treffer), 2)
        self.assertTrue(treffer[0].startswith("Umsatz im Monat mindestens 500 € ab Monat 3"))

    def test_ist_bereinigen(self):
        ist = M._ist([{"monat": "2026-13", "umsatz": 1}, {"monat": "2026-10", "umsatz": "-5", "kosten": "x"},
                      {"monat": "2026-09", "umsatz": 100}, {"monat": "2026-10", "umsatz": 50}])
        self.assertEqual([z["monat"] for z in ist], ["2026-09", "2026-10"])
        self.assertEqual(ist[1], {"monat": "2026-10", "umsatz": 50.0, "kosten": 0.0, "stunden": 0.0})

    def test_kriterien_migration(self):
        alt = {"einstellungen": {"kriterien": [{"id": i, "name": i, "gewicht": g, "invers": inv}
                                               for i, g, inv in M.ALTE_STANDARD_KRITERIEN]},
               "ideen": [{"id": "x", "name": "X", "kriterien": {"staerken": 9}}]}
        d = M.bereinigen(alt)
        self.assertEqual([k["id"] for k in d["einstellungen"]["kriterien"]], [k["id"] for k in M.STANDARD_KRITERIEN])
        self.assertEqual(d["ideen"][0]["kriterien"]["markt"], M.SCORE_START)
        self.assertEqual(d["ideen"][0]["kriterien"]["staerken"], 9)      # alter Wert bleibt erhalten
        eigen = {"einstellungen": {"kriterien": [{"id": "a", "name": "A", "gewicht": 100, "invers": False}]}}
        self.assertEqual(M.bereinigen(eigen)["einstellungen"]["kriterien"][0]["id"], "a")   # eigene bleiben
        # nach der Migration bleibt auch ein bewusst wieder eingestellter alter Satz erhalten
        wieder = dict(alt["einstellungen"], kriterien_version=2)
        self.assertEqual(M.bereinigen({"einstellungen": wieder})["einstellungen"]["kriterien"][0]["id"], "staerken")

    def test_alte_finanzen_anlaufstunden(self):
        i = M.idee_bereinigen({"name": "Alt", "finanzen": {"stunden_woche": 12}}, M.standard_einstellungen())
        self.assertEqual(i["finanzen"]["stunden_anlauf_woche"], 12.0)


class Datenmodell(unittest.TestCase):
    def test_bereinigen_kaputt(self):
        d = M.bereinigen({"ideen": [None, {"name": "X", "status": "quatsch", "finanzen": {"horizont_jahre": 0,
                                                                                          "umsatz_monat": "1.234,5"}},
                                    {"id": "a", "name": "A"}, {"id": "a", "name": "B"}],
                          "einstellungen": {"kriterien": [{"name": ""}], "schwelle_nutzwert": 500}})
        self.assertEqual(len(d["ideen"]), 3)
        x = d["ideen"][0]
        self.assertEqual(x["status"], "idee")
        self.assertEqual(x["finanzen"]["horizont_jahre"], 1)      # Grenze 1-30
        self.assertEqual(len({i["id"] for i in d["ideen"]}), 3)    # doppelte id neu vergeben
        self.assertEqual(d["einstellungen"]["schwelle_nutzwert"], 100)
        self.assertEqual(len(d["einstellungen"]["kriterien"]), 6)  # ungueltige Liste -> Standard
        self.assertTrue(M.gewichte_ok(d["einstellungen"]["kriterien"]))

    def test_status_seit(self):
        i = M.neue_idee("X", jetzt=datetime.datetime(2026, 1, 1))
        M.status_setzen(i, "test", datetime.datetime(2026, 2, 1, 12))
        self.assertEqual((i["status"], i["status_seit"]), ("test", "2026-02-01T12:00"))

    def test_json_rundreise(self):
        d = M.leer()
        d["ideen"].append(M.neue_idee("Online-Kurs", d["einstellungen"]))
        d["ideen"][0]["phasen"]["4"] = {"text": "Zeitmangel", "score": 8}
        neu, n, ers = M.import_json(M.leer(), M.export_json(d))
        self.assertEqual((n, ers), (1, 0))
        self.assertEqual(neu["ideen"][0]["phasen"]["4"], {"text": "Zeitmangel", "score": 8})
        _, n, ers = M.import_json(neu, M.export_json(d))
        self.assertEqual((n, ers), (0, 1))                         # gleiche id -> ersetzt
        with self.assertRaises(ValueError):
            M.import_json(d, "kein json")

    def test_csv_rundreise(self):
        d = M.leer()
        i = M.neue_idee("Kurs; mit Semikolon", d["einstellungen"])
        i["finanzen"]["umsatz_monat"] = 1234.5
        i["phasen"]["1"] = {"text": "Didaktik", "score": 9}
        d["ideen"].append(i)
        text = M.export_csv(d, R.kennzahlen_export(R.rangliste(d)))
        self.assertIn("1234,5", text)
        neu, n, ers = M.import_csv(d, text)
        self.assertEqual((n, ers), (0, 1))
        j = neu["ideen"][0]
        self.assertEqual(j["name"], "Kurs; mit Semikolon")
        self.assertEqual(j["finanzen"]["umsatz_monat"], 1234.5)
        self.assertEqual(j["phasen"]["1"], {"text": "Didaktik", "score": 9})   # Text bleibt erhalten
        frisch, n, _ = M.import_csv(M.leer(), text)
        self.assertEqual(n, 1)
        with self.assertRaises(ValueError):
            M.import_csv(d, "a;b\n1;2")

    def test_neues_kriterium(self):
        d = M.leer()
        d["ideen"].append(M.neue_idee("X", d["einstellungen"]))
        d["einstellungen"]["kriterien"].append({"id": M.kriterium_id("Spaß", [k["id"] for k in
                                                                              d["einstellungen"]["kriterien"]]),
                                               "name": "Spaß", "gewicht": 0, "invers": False})
        d = M.bereinigen(d)
        self.assertEqual(d["ideen"][0]["kriterien"]["spa"], M.SCORE_START)

    def test_rangliste_sortierung(self):
        d = M.leer()
        for name, umsatz, status in (("schlecht", 0, "idee"), ("gut", 3000, "idee"), ("weg", 3000, "verworfen")):
            i = M.neue_idee(name, d["einstellungen"])
            i["finanzen"] = fin(umsatz_monat=umsatz, horizont_jahre=3)
            i["status"] = status
            d["ideen"].append(i)
        self.assertEqual([r["name"] for r in R.rangliste(d)], ["gut", "schlecht", "weg"])


class Monatslauf(unittest.TestCase):
    def _daten(self):
        d = M.leer()
        for name, umsatz, status in (("A", 3000, "aktiv"), ("B", 2000, "test"), ("C", 0, "idee"), ("D", 3000, "verworfen")):
            i = M.neue_idee(name, d["einstellungen"], jetzt=datetime.datetime(2026, 9, 1))
            i["finanzen"] = fin(umsatz_monat=umsatz, horizont_jahre=3)
            i["status"] = status
            d["ideen"].append(i)
        return d

    def test_zusammenfassung(self):
        import eks_agent as A
        d = self._daten()
        zeilen, ampeln, zahlen = A.zusammenfassung(d, datetime.datetime(2026, 11, 1))
        self.assertEqual(zeilen[0], "Top 3:")
        self.assertEqual(len([z for z in zeilen if z[:2] in ("1.", "2.", "3.")]), 3)
        self.assertFalse(any(" D " in z for z in zeilen[:4]))          # verworfen nicht in den Top 3
        self.assertIn("• B (61 Tage)", zeilen)                          # seit 1.9. im Test
        self.assertEqual(zahlen["test_alt"], 1)
        self.assertEqual(len(ampeln), 4)
        # Ampel-Aenderung erkennen
        c = next(i for i in d["ideen"] if i["name"] == "C")
        d["letzter_lauf"] = {"ampeln": dict(ampeln, **{c["id"]: "gruen"})}
        zeilen, _, zahlen = A.zusammenfassung(d, datetime.datetime(2026, 11, 1))
        self.assertEqual(zahlen["aenderungen"], 1)
        self.assertTrue(any(z.startswith("• C: 🟢 → ") for z in zeilen))

    def test_abbruch_in_zusammenfassung(self):
        import eks_agent as A
        d = self._daten()
        b = next(i for i in d["ideen"] if i["name"] == "B")
        b["start_monat"] = "2026-09"
        b["ist"] = [{"monat": "2026-09", "umsatz": 100, "kosten": 50, "stunden": 10}]
        b["abbruch"] = [{"art": "umsatz_min", "wert": 500, "nach_monaten": 1}]
        zeilen, _, zahlen = A.zusammenfassung(d, datetime.datetime(2026, 11, 1))
        self.assertEqual(zahlen["abbruch"], 1)
        self.assertTrue(any(z.startswith("• B: Umsatz im Monat mindestens 500 €") for z in zeilen))

    def test_discord_optional(self):
        import eks_agent as A

        class Antwort:
            def __init__(self, code):
                self.status_code = code
        gesendet = []
        self.assertEqual(A.discord_senden(["x"], url="", post=None), "nicht eingerichtet")
        self.assertEqual(A.discord_senden(["x"], url="https://hook", post=lambda u, **k: gesendet.append(k)
                                          or Antwort(204)), "gesendet")
        self.assertIn("EKS-Ideen", gesendet[0]["json"]["content"])
        self.assertEqual(A.discord_senden(["x"], url="https://hook", post=lambda u, **k: Antwort(404)),
                         "Fehler (HTTP 404)")

        def kaputt(u, **k):
            raise ConnectionError("weg")
        self.assertEqual(A.discord_senden(["x" * 5000], url="https://hook", post=kaputt), "Fehler (ConnectionError)")


if __name__ == "__main__":
    unittest.main()
