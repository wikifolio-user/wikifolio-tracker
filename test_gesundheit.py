"""Gesundheitsmodul: Rechenkern, Lebensmittel, Speicher, Online-Quelle (python3 -m unittest test_gesundheit)."""
import datetime
import unittest
from zoneinfo import ZoneInfo

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

from gesundheit import lebensmittel as L
from gesundheit import naehrstoffe as N
from gesundheit import quellen as Q
from gesundheit import rechnen as R
from gesundheit import speicher as S

R_BERLIN = ZoneInfo("Europe/Berlin")
HEUTE = datetime.date(2026, 11, 18)
ZEIT = datetime.datetime(2026, 11, 18, 8, 15)


class Kalorien(unittest.TestCase):
    def test_bmr_mifflin(self):
        # 80 kg, 180 cm, 40 J., maennlich: 10*80 + 6.25*180 - 5*40 + 5 = 1730
        self.assertAlmostEqual(R.bmr(80, 180, 40, "m"), 1730)
        self.assertAlmostEqual(R.bmr(60, 165, 30, "w"), 600 + 1031.25 - 150 - 161)
        self.assertAlmostEqual(R.bmr(80, 180, 40, "x"), 1730 - 83)
        self.assertIsNone(R.bmr(None, 180, 40))

    def test_tdee_und_ziele(self):
        self.assertAlmostEqual(R.tdee(1730, "aktiv"), 1730 * 1.55)
        p = {"gewicht_kg": 80, "groesse_cm": 180, "geburtsjahr": 1986, "geschlecht": "m", "aktivitaet": "wenig",
             "ziel": "reduzieren"}
        z = R.ziele(p, HEUTE)
        self.assertEqual(z["bmr"], 1730)
        self.assertEqual(z["tdee"], round(1730 * 1.2))
        self.assertEqual(z["kcal"], round(1730 * 1.2 - 500))
        self.assertEqual(z["protein"], 144)                 # 1,8 g/kg beim Abnehmen
        self.assertEqual(z["fett"], round(z["kcal"] * 0.3 / 9))
        self.assertEqual(z["wasser_ml"], 2800)
        # Kalorien der Makro-Ziele ergeben (gerundet) das Tagesziel
        self.assertAlmostEqual(z["protein"] * 4 + z["kh"] * 4 + z["fett"] * 9, z["kcal"], delta=10)

    def test_ziel_nie_unter_minimum_und_eigene_vorgaben(self):
        p = {"gewicht_kg": 45, "groesse_cm": 150, "geburtsjahr": 1950, "geschlecht": "w", "ziel": "reduzieren"}
        self.assertEqual(R.ziele(p, HEUTE)["kcal"], R.KCAL_MINIMUM)
        p.update(kcal_eigen=1800, protein_eigen=100, wasser_eigen=2000)
        z = R.ziele(p, HEUTE)
        self.assertEqual((z["kcal"], z["protein"], z["wasser_ml"]), (1800, 100, 2000))

    def test_ohne_angaben(self):
        self.assertEqual(R.ziele({})["kcal"], None)

    def test_bilanz_sport_nicht_doppelt(self):
        b = R.bilanz(2000, 2500, 1800, sport=400, sport_zusaetzlich=False)
        self.assertEqual((b["ziel"], b["verbleibend"], b["bilanz"]), (2000, 200, -700))
        b = R.bilanz(2000, 2500, 1800, sport=400, sport_zusaetzlich=True)
        self.assertEqual((b["ziel"], b["verbleibend"], b["bilanz"]), (2400, 600, -1100))


class Mengen(unittest.TestCase):
    def test_gramm_einheiten(self):
        self.assertEqual(R.gramm(37, "g", {}), 37)
        self.assertEqual(R.gramm(2, "Stück", {"Stück": 120}), 240)
        self.assertEqual(R.gramm(0.5, "L", {}), 500)
        self.assertIsNone(R.gramm(1, "Tasse", {}))
        self.assertIsNone(R.gramm("x", "g", {}))
        self.assertIsNone(R.gramm(-1, "g", {}))

    def test_naehrwerte_und_rueckwaerts(self):
        pro100 = {"kcal": 350, "protein": 10, "kh": None}
        n = R.naehrwerte(pro100, 37)
        self.assertAlmostEqual(n["kcal"], 129.5)
        self.assertAlmostEqual(n["protein"], 3.7)
        self.assertNotIn("kh", n)                       # unbekannt bleibt unbekannt
        self.assertAlmostEqual(R.menge_fuer_kcal(pro100, 300), 300 * 100 / 350)
        self.assertIsNone(R.menge_fuer_kcal({}, 300))

    def test_summe_unbekannt_ist_nicht_null(self):
        s = R.summe([{"kcal": 100, "ballast": 2}, {"kcal": 50}], ["kcal", "ballast"])
        self.assertEqual(s["kcal"], {"wert": 150, "bekannt": 2, "anzahl": 2})
        self.assertEqual(s["ballast"], {"wert": 2, "bekannt": 1, "anzahl": 2})

    def test_einheiten_umrechnen(self):
        self.assertAlmostEqual(N.umrechnen(1, "mg", "µg"), 1000)
        self.assertAlmostEqual(N.umrechnen(250, "µg", "mg"), 0.25)
        self.assertAlmostEqual(N.umrechnen(1.5, "L", "ml"), 1500)
        self.assertIsNone(N.umrechnen(1, "g", "ml"))
        self.assertIsNone(N.umrechnen(1000, "IE", "µg"))      # IE nur stoffabhaengig - keine allgemeine Regel

    def test_mahlzeit_nach_uhrzeit(self):
        self.assertEqual(R.mahlzeit_vorschlag(datetime.time(7)), "Frühstück")
        self.assertEqual(R.mahlzeit_vorschlag(datetime.time(12, 30)), "Mittagessen")
        self.assertEqual(R.mahlzeit_vorschlag(datetime.time(19)), "Abendessen")
        self.assertEqual(R.mahlzeit_vorschlag(datetime.time(22)), "Snacks")


class Lebensmittel(unittest.TestCase):
    def test_daten_plausibel(self):
        ids = [lm["id"] for lm in L.MITGELIEFERT]
        self.assertEqual(len(ids), len(set(ids)))
        for lm in L.MITGELIEFERT:
            p = lm["pro100"]
            self.assertIn(lm["basis"], ("g", "ml"))
            self.assertLessEqual(p["zucker"], p["kh"] + 0.01, lm["name"])
            if lm["id"] in ("bier", "rotwein") or p["kcal"] < 20:     # Alkohol hat eigene Kalorien
                continue
            atwater = p["protein"] * 4 + p["kh"] * 4 + p["fett"] * 9 + p["ballast"] * 2
            self.assertLess(abs(atwater - p["kcal"]) / p["kcal"], 0.15, lm["name"])

    def test_suche_fehlertolerant(self):
        self.assertEqual(L.suchen("ban", L.MITGELIEFERT)[0]["id"], "banane")
        self.assertEqual(L.suchen("bananne", L.MITGELIEFERT)[0]["id"], "banane")
        self.assertEqual(L.suchen("Möhre", L.MITGELIEFERT)[0]["id"], "karotte")
        self.assertEqual(L.suchen("kase", L.MITGELIEFERT)[0]["kategorie"], "Käse")
        self.assertEqual(L.suchen("xyzqw", L.MITGELIEFERT), [])

    def test_suche_rangfolge_favoriten_und_nutzung(self):
        r = L.suchen("brot", L.MITGELIEFERT, favoriten=["toast"])
        self.assertEqual(r[0]["id"], "toast")
        nutzung = {"apfel": {"n": 5, "zuletzt": "2026-11-17T08:00:00"}, "ei": {"n": 1, "zuletzt": "2026-11-18T08:00:00"}}
        leer = L.suchen("", L.MITGELIEFERT, nutzung=nutzung, favoriten=["kiwi"])
        self.assertEqual([x["id"] for x in leer], ["kiwi", "apfel", "ei"])

    def test_standardmenge(self):
        self.assertEqual(L.standard_menge(L.NACH_ID["banane"]), (1.0, "Stück"))
        self.assertEqual(L.einheiten(L.NACH_ID["wasser"])[-1], "ml")


class Speicher(unittest.TestCase):
    def test_essen_trinken_gewicht_und_summen(self):
        m = {}
        e = S.essen_eintrag(L.NACH_ID["banane"], 1, "Stück", "Frühstück", ZEIT)
        m = S.essen_hinzu(m, HEUTE, [e, S.essen_eintrag(L.NACH_ID["milch_15"], 1, "Glas", "Frühstück", ZEIT)])
        m = S.trinken_hinzu(m, HEUTE, "wasser", 500, ZEIT)
        m = S.trinken_hinzu(m, HEUTE, "saft", 200, ZEIT)
        m = S.trinken_hinzu(m, HEUTE, "wasser", -5, ZEIT)              # ungueltig: ignoriert
        m = S.gewicht_setzen(m, HEUTE, 82.44)
        t = S.tag_aus(m, HEUTE)
        self.assertEqual(t["gewicht"], 82.4)
        s = S.tag_summen(t)
        self.assertAlmostEqual(s["kcal"], 93 * 1.2 + 47 * 2 + 45 * 2)
        self.assertAlmostEqual(s["fluessigkeit_ml"], 500 + 200 + 200)  # Milch zaehlt als Fluessigkeit
        self.assertAlmostEqual(s["mahlzeiten"]["Frühstück"], 93 * 1.2 + 47 * 2)

    def test_menge_aendern_entfernen_wiederherstellen(self):
        e = S.essen_eintrag(L.NACH_ID["banane"], 1, "Stück", "Frühstück", ZEIT)
        m = S.essen_hinzu({}, HEUTE, [e])
        m = S.essen_menge(m, HEUTE, e["id"], 2)
        self.assertEqual(S.tag_aus(m, HEUTE)["essen"][0]["gramm"], 240)
        m2 = S.essen_menge(m, HEUTE, e["id"], -3)                    # ungueltig: bleibt
        self.assertEqual(S.tag_aus(m2, HEUTE)["essen"][0]["gramm"], 240)
        m3, weg = S.entfernen(m, HEUTE, "essen", e["id"])
        self.assertEqual(S.tag_aus(m3, HEUTE)["essen"], [])
        m4 = S.wiederherstellen(m3, HEUTE, "essen", weg)
        m4 = S.wiederherstellen(m4, HEUTE, "essen", weg)            # doppelt: nur einmal
        self.assertEqual(len(S.tag_aus(m4, HEUTE)["essen"]), 1)
        self.assertEqual(S.tag_aus(m, HEUTE)["essen"][0]["menge"], 2)   # Original unveraendert (Kopien)

    def test_ungueltige_menge_kein_eintrag(self):
        self.assertIsNone(S.essen_eintrag(L.NACH_ID["banane"], 0, "Stück", "Snacks", ZEIT))
        self.assertIsNone(S.essen_eintrag(L.NACH_ID["banane"], 1, "Tasse", "Snacks", ZEIT))

    def test_kopieren_neue_ids(self):
        e = S.essen_eintrag(L.NACH_ID["ei"], 2, "Stück", "Frühstück", ZEIT)
        k = S.kopieren([e], datetime.datetime(2026, 11, 19, 7, 0))
        self.assertNotEqual(k[0]["id"], e["id"])
        self.assertEqual((k[0]["zeit"], k[0]["gramm"]), ("07:00", e["gramm"]))

    def test_profil_historie_und_einrichtung(self):
        d = S.profil_doc(None)
        self.assertFalse(S.eingerichtet(d))
        d = S.profil_setzen(d, {"gewicht_kg": 80, "groesse_cm": 180, "geburtsjahr": 1986, "ziel": "halten"}, ZEIT)
        self.assertTrue(S.eingerichtet(d))
        d = S.profil_setzen(d, {"gewicht_kg": 80}, ZEIT)            # keine Aenderung: keine neue Historie
        d = S.profil_setzen(d, {"gewicht_kg": 79}, ZEIT)
        self.assertEqual(len(d["historie"]), 2)
        self.assertEqual(d["einstellungen"]["glaeser"][0]["ml"], 300)

    def test_nutzung_favoriten_gewichte(self):
        d = S.nutzung_merken({}, "banane", 2, "Stück", ZEIT)
        d = S.nutzung_merken(d, "banane", 1, "Stück", ZEIT)
        self.assertEqual((d["nutzung"]["banane"]["n"], d["nutzung"]["banane"]["menge"]), (2, 1.0))
        d = S.favorit_umschalten(d, "banane")
        self.assertEqual(d["favoriten"], ["banane"])
        self.assertEqual(S.favorit_umschalten(d, "banane")["favoriten"], [])
        m = S.gewicht_setzen({}, HEUTE, 80)
        m = S.gewicht_setzen(m, datetime.date(2026, 11, 2), 81)
        self.assertEqual(S.gewichte([m]), [(datetime.date(2026, 11, 2), 81.0), (HEUTE, 80.0)])
        self.assertEqual(S.monat_pfad(HEUTE), "state/gesundheit/tage/2026-11.json")


class OpenFoodFacts(unittest.TestCase):
    def test_produkt_und_suche(self):
        p = {"code": "123", "product_name": "Skyr Natur", "brands": "Marke A, Marke B", "serving_quantity": "150",
             "quantity": "450 g", "nutriments": {"energy-kcal_100g": 63, "proteins_100g": 11, "fat_100g": "0.2"}}
        lm = Q.off_produkt(p)
        self.assertEqual((lm["id"], lm["marke"], lm["einheiten"], lm["basis"]), ("off:123", "Marke A", {"Portion": 150.0}, "g"))
        self.assertNotIn("kh", lm["pro100"])                          # fehlend = unbekannt
        self.assertIsNone(Q.off_produkt({"code": "1", "product_name": "x", "nutriments": {}}))

        class Antwort:
            status_code = 200

            def json(self):
                return {"products": [p, p, {"code": "9"}]}
        treffer, fehler = Q.off_suchen("skyr", lambda *a, **k: Antwort())
        self.assertEqual((len(treffer), fehler), (1, None))

        def kaputt(*a, **k):
            raise OSError("netz")
        treffer, fehler = Q.off_suchen("skyr", kaputt)
        self.assertEqual(treffer, [])
        self.assertIn("nicht erreichbar", fehler)
        self.assertEqual(Q.off_suchen("s", kaputt), ([], None))



@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class Oberflaeche(unittest.TestCase):
    """Rauchtest der Oberflaeche (AppTest, Speicher im Arbeitsspeicher): Einrichtung, Wasser, Essen."""

    def test_einrichtung_und_eintragen(self):
        def app():
            import copy
            import streamlit as st
            import gesundheit_ui
            store = st.session_state.setdefault("_store", {})

            def lesen(p, d):
                return copy.deepcopy(store.get(p, d)), True

            def akt(p, f, d, msg):
                neu = f(copy.deepcopy(store.get(p, d)))
                store[p] = copy.deepcopy(neu)
                return True, neu
            gesundheit_ui.seite({"lesen": lesen, "aktualisiere": akt, "upfad": lambda p: p, "speichern": True,
                                 "get": None})

        at = AppTest.from_function(app, default_timeout=30).run()
        self.assertFalse(at.exception)
        knopf = lambda text: next(b for b in at.button if b.label == text)
        knopf("Gewicht reduzieren").click().run()
        knopf("Weiter →").click().run()
        knopf("Aktiv – 3–5 × Sport pro Woche oder körperliche Arbeit").click().run()
        knopf("Fertig – Gesundheit starten").click().run()
        self.assertFalse(at.exception)
        store = at.session_state["_store"]
        self.assertTrue(S.eingerichtet(store[S.PFAD_PROFIL]))
        knopf("💧 250 ml").click().run()                         # Wasser: ein Tipp
        tage = store[S.monat_pfad(datetime.datetime.now(R_BERLIN).date())]["tage"]
        self.assertEqual([x["ml"] for t in tage.values() for x in t["trinken"]], [250.0])
        at.session_state["gs_bereich_neu"] = "Essen"
        at.run()
        at.selectbox(key="gs_wahl").set_value("banane").run()
        knopf("Speichern").click().run()
        self.assertFalse(at.exception)
        essen = [e for t in store[S.monat_pfad(datetime.datetime.now(R_BERLIN).date())]["tage"].values()
                 for e in t["essen"]]
        self.assertEqual([(e["name"], e["menge"], e["einheit"]) for e in essen], [("Banane", 1.0, "Stück")])
        self.assertEqual(store[S.PFAD_PROFIL]["nutzung"]["banane"]["n"], 1)


class NurAdmin(unittest.TestCase):
    def test_gesundheit_nur_fuer_angemeldeten_admin(self):
        """Gesundheitsdaten: dieselbe Sperre wie die Benutzerverwaltung (kein Zugriff ohne Admin-Login)."""
        quelle = open("app.py", encoding="utf-8").read()
        self.assertIn('if ansicht in (ANSICHT_BENUTZER, ANSICHT_GESUNDHEIT):', quelle)
        self.assertIn('_zugang_pruefen(ANSICHT_GESUNDHEIT)', quelle)


if __name__ == "__main__":
    unittest.main()
