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
from gesundheit import mikro as M
from gesundheit import referenz as F
from gesundheit import supplements as SU
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



class Mikronaehrstoffe(unittest.TestCase):
    def test_einheiten_und_ie_stoffabhaengig(self):
        self.assertAlmostEqual(N.in_basis("vit_d", 1000, "IE"), 25)
        self.assertAlmostEqual(N.in_basis("vit_a", 1000, "IE"), 300)
        self.assertAlmostEqual(N.in_basis("vit_e", 10, "IE"), 6.7)
        self.assertIsNone(N.in_basis("zink", 10, "IE"))               # fuer Zink gibt es keine IE
        self.assertAlmostEqual(N.in_basis("magnesium", 0.3, "g"), 300)
        self.assertAlmostEqual(N.in_basis("vit_b12", 0.5, "mg"), 500)
        self.assertIsNone(N.in_basis("gibtsnicht", 1, "mg"))
        self.assertEqual(len(N.MIKRO), len(set(N.MIKRO)))
        for n in N.EINFACH:
            self.assertIn(n, N.MIKRO)

    def test_referenzwerte(self):
        for r in F.REFERENZWERTE:                                       # Einheit passt zum Naehrstoff
            self.assertEqual(r.einheit, N.NAEHRSTOFFE[r.naehrstoff].einheit, r)
            self.assertTrue(r.ul is None or r.ul > 0)
        self.assertEqual(F.suchen("eisen", "w", 30).ziel, 16)
        self.assertEqual(F.suchen("eisen", "w", 60).ziel, 14)
        self.assertEqual(F.suchen("eisen", "m", 30).ziel, 11)
        self.assertEqual(F.suchen("magnesium", "x", 40).ziel, 325)        # keine Angabe: Mittelwert
        self.assertEqual(F.suchen("vit_d", "w", 40).ul, 100)
        self.assertIsNone(F.suchen("omega3"))

    def test_natrium_aus_salz_und_mikro_der_lebensmittel(self):
        self.assertAlmostEqual(L.NACH_ID["gouda"]["pro100"]["natrium"], 2.0 * 393)
        self.assertEqual(L.natrium_aus_salz({"salz": 1, "natrium": 5})["natrium"], 5)   # Angabe hat Vorrang
        for lm in L.MITGELIEFERT:
            for n in lm["pro100"]:
                self.assertIn(n, N.NAEHRSTOFFE, lm["name"])
        self.assertNotIn("calcium", L.NACH_ID["wasser"]["pro100"])      # schwankt je Wasser: unbekannt, nicht 0

    def test_off_mikro_in_basiseinheit(self):
        lm = Q.off_produkt({"code": "1", "product_name": "Saft", "nutriments": {
            "energy-kcal_100g": 45, "vitamin-c_100g": 0.03, "vitamin-d_100g": 0.0000025, "sodium_100g": 0.01}})
        self.assertAlmostEqual(lm["pro100"]["vit_c"], 30)
        self.assertAlmostEqual(lm["pro100"]["vit_d"], 2.5)
        self.assertAlmostEqual(lm["pro100"]["natrium"], 10)

    def test_tagessumme_mit_herkunft(self):
        m = S.essen_hinzu({}, HEUTE, [S.essen_eintrag(L.NACH_ID["mandeln"], 30, "g", "Snacks", ZEIT),
                                      S.essen_eintrag(L.NACH_ID["milch_15"], 200, "ml", "Frühstück", ZEIT),
                                      S.essen_eintrag(L.NACH_ID["toast"], 1, "Scheibe", "Frühstück", ZEIT)])
        mg = SU.neues(SU.VORLAGEN[2], "mg1", HEUTE)                      # Magnesium 250 mg
        m = S.einnahme_setzen(m, HEUTE, mg, "eingenommen", ZEIT)
        d3 = SU.neues(SU.VORLAGEN[0], "d3", HEUTE)
        m = S.einnahme_setzen(m, HEUTE, d3, "ausgelassen", ZEIT)        # ausgelassen zaehlt nicht
        t = S.tag_aus(m, HEUTE)
        w = M.tag_naehrstoffe(t, ["magnesium", "calcium", "vit_d"])
        self.assertAlmostEqual(w["magnesium"]["quellen"]["Lebensmittel"], 270 * 0.3)
        self.assertAlmostEqual(w["magnesium"]["quellen"]["Supplements"], 250)
        self.assertAlmostEqual(w["magnesium"]["wert"], 81 + 250)
        self.assertEqual((w["magnesium"]["bekannt"], w["magnesium"]["anzahl"]), (1, 3))   # Milch/Toast: unbekannt
        self.assertAlmostEqual(w["calcium"]["quellen"]["Getränke"], 123 * 2)
        self.assertEqual(w["vit_d"]["wert"], 0)
        self.assertEqual(w["magnesium"]["top"][0][0], "Magnesium")
        self.assertAlmostEqual(M.datenqualitaet(t), 2 / 3 * 100)
        self.assertIsNone(M.datenqualitaet({"essen": []}))
        u = {x["id"]: x for x in M.uebersicht(t, {"geschlecht": "m"}, ["magnesium"], 40)}
        self.assertAlmostEqual(u["magnesium"]["prozent"], 331 / 350 * 100)

    def test_durchschnitt_nur_tage_mit_eintraegen(self):
        t1 = S.tag_aus(S.essen_hinzu({}, HEUTE, [S.essen_eintrag(L.NACH_ID["kiwi"], 100, "g", "Snacks", ZEIT)]), HEUTE)
        leer = S.tag_leer()
        self.assertEqual(M.durchschnitt([t1, leer], "vit_c"), (93, 1))
        self.assertEqual(M.durchschnitt([leer], "vit_c"), (None, 0))


class Supplements(unittest.TestCase):
    def test_vorlagen_gueltig(self):
        for v in SU.VORLAGEN:
            s = SU.neues(v, "x", HEUTE)
            inhalt, fehler = SU.inhalt_basis(s)
            self.assertEqual(fehler, [], v["name"])
            self.assertTrue(inhalt, v["name"])
            self.assertIn(v["form"], SU.FORMEN)
            self.assertIn(v["zeit"], SU.ZEITEN)
        d3 = SU.neues(SU.VORLAGEN[0], "x", HEUTE)
        self.assertAlmostEqual(SU.inhalt_basis(d3, 2)[0]["vit_d"], 50)

    def test_plan_rhythmus(self):
        s = SU.neues(SU.VORLAGEN[0], "x", HEUTE)                         # 18.11.2026 = Mittwoch
        self.assertTrue(SU.geplant_am(s, HEUTE))
        s["plan"].update(rhythmus="wochentage", tage=[0, 2, 4])            # Mo / Mi / Fr
        self.assertTrue(SU.geplant_am(s, HEUTE))
        self.assertFalse(SU.geplant_am(s, HEUTE + datetime.timedelta(days=1)))
        self.assertEqual(SU.plan_text(s), "morgens, Mo / Mi / Fr")
        s["plan"].update(rhythmus="intervall", alle=3, ab="2026-11-16")
        self.assertEqual([SU.geplant_am(s, datetime.date(2026, 11, d)) for d in (15, 16, 17, 19)], [False, True, False, True])
        s["aktiv"] = False
        self.assertFalse(SU.geplant_am(s, datetime.date(2026, 11, 16)))

    def test_tagesplan_und_einnahme(self):
        a, b = SU.neues(SU.VORLAGEN[0], "a", HEUTE), SU.neues(SU.VORLAGEN[2], "b", HEUTE)
        plan = SU.tagesplan([a, b], HEUTE)
        self.assertEqual(list(plan), ["Morgens", "Abends"])
        m = S.einnahme_setzen({}, HEUTE, a, "ausgelassen", ZEIT)
        m = S.einnahme_setzen(m, HEUTE, a, "eingenommen", ZEIT)           # ersetzt, nicht doppelt
        t = S.tag_aus(m, HEUTE)
        self.assertEqual([(x["sup"], x["status"]) for x in t["supplements"]], [("a", "eingenommen")])
        self.assertAlmostEqual(t["supplements"][0]["inhalt"]["vit_d"], 25)
        self.assertEqual(S.tag_aus(S.einnahme_loeschen(m, HEUTE, "a"), HEUTE)["supplements"], [])

    def test_speichern_und_deaktivieren(self):
        a = SU.neues(SU.VORLAGEN[0], "a", HEUTE)
        d = S.supplement_speichern({}, a)
        a2 = {**a, "name": "D3 forte"}
        d = S.supplement_speichern(d, a2)
        self.assertEqual([x["name"] for x in d["supplements"]], ["D3 forte"])
        d = S.supplement_entfernen(d, "a")
        self.assertFalse(d["supplements"][0]["aktiv"])
        self.assertEqual(SU.tagesplan(d["supplements"], HEUTE), {})


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
        # Supplement aus Vorlage anlegen (Vitamin D3 ist vorgewaehlt) und mit einem Tipp einnehmen
        at.session_state["gs_bereich_neu"] = "Supplements"
        at.run()
        knopf("Hinzufügen").click().run()
        self.assertFalse(at.exception)
        sups = store[S.PFAD_PROFIL]["supplements"]
        self.assertEqual([x["name"] for x in sups], ["Vitamin D3"])
        knopf("☐ Vitamin D3 · 1 Tablette").click().run()
        heute = datetime.datetime.now(R_BERLIN).date()
        t = S.tag_aus(store[S.monat_pfad(heute)], heute)
        self.assertEqual([(x["name"], x["status"]) for x in t["supplements"]], [("Vitamin D3", "eingenommen")])
        # Naehrstoffe: Vitamin D aus dem Supplement, Details ohne Fehler
        at.session_state["gs_bereich_neu"] = "Nährstoffe"
        at.run()
        at.selectbox(key="gs_mikro_detail").set_value("vit_d").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Supplements: 25,0 µg" in m.value for m in at.markdown))


class NurAdmin(unittest.TestCase):
    def test_gesundheit_nur_fuer_angemeldeten_admin(self):
        """Gesundheitsdaten: dieselbe Sperre wie die Benutzerverwaltung (kein Zugriff ohne Admin-Login)."""
        with open("app.py", encoding="utf-8") as f:
            quelle = f.read()
        self.assertIn('if ansicht in (ANSICHT_BENUTZER, ANSICHT_GESUNDHEIT):', quelle)
        self.assertIn('_zugang_pruefen(ANSICHT_GESUNDHEIT)', quelle)


if __name__ == "__main__":
    unittest.main()
