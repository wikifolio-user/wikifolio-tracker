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

    def test_steuer_nur_auf_gewinn(self):
        v = R.verlauf(fin(steuersatz_pct=30.0))
        self.assertAlmostEqual(v[1]["cashflow"], 600 * 0.7)
        verlust = R.verlauf(fin(umsatz_monat=100.0, steuersatz_pct=30.0))
        self.assertAlmostEqual(verlust[1]["steuer"], 0.0)          # kein Steuerabzug im Verlust
        self.assertAlmostEqual(verlust[1]["cashflow"], 100 - 20 - 200)

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
        # alle Scores 5: normal (5-1)/9 = 44,4 % (60 % Gewicht), invers (10-5)/9 = 55,6 % (40 % Gewicht)
        self.assertAlmostEqual(R.nutzwert(self.i, self.e["kriterien"]), 0.6 * 4 / 9 * 100 + 0.4 * 5 / 9 * 100)
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
        r = R.auswerten(i, e)
        self.assertEqual(r["ampel"], "gruen")                      # NW 84, NPV > 0, 27,69 €/h >= 25
        self.assertGreater(r["npv"], 0)
        self.assertEqual(set(r["szenarien"]), {"pess", "real", "opt"})
        self.assertLess(r["szenarien"]["pess"]["npv"], r["npv"])
        self.assertLess(r["npv"], r["szenarien"]["opt"]["npv"])

    def test_sensitivitaet(self):
        s = R.sensitivitaet(fin(), REAL, 0.0)
        self.assertAlmostEqual(s["basis"], 6000)
        (n1, um, up), (n2, km, kp) = s["zeilen"]
        self.assertAlmostEqual(um, -1200 + 12 * (800 - 160 - 200))      # Umsatz -20 %
        self.assertAlmostEqual(up, -1200 + 12 * (1200 - 240 - 200))     # Umsatz +20 %
        self.assertAlmostEqual(km, -1200 + 12 * (1000 - 160 - 160))     # Kosten -20 %
        self.assertAlmostEqual(kp, -1200 + 12 * (1000 - 240 - 240))     # Kosten +20 %


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
