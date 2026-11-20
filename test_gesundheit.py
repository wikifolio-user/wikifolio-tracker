"""Gesundheitsmodul: Rechenkern, Lebensmittel, Speicher, Online-Quelle (python3 -m unittest test_gesundheit)."""
import datetime
import unittest
from zoneinfo import ZoneInfo

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

from gesundheit import fasten as FA
from gesundheit import foto as FO
from gesundheit import lebensmittel as L
from gesundheit import mikro as M
from gesundheit import referenz as F
from gesundheit import supplements as SU
from gesundheit import naehrstoffe as N
from gesundheit import quellen as Q
from gesundheit import rechnen as R
from gesundheit import bericht_pdf as BP
from gesundheit import speicher as S
from gesundheit import suche as SC
from gesundheit import statistik as ST
from gesundheit import sport as SP

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


class Sport(unittest.TestCase):
    def test_kalorien_ohne_ruheumsatz(self):
        # Laufen mittel: MET 9,8 -> (9,8 - 1) x 80 kg x 0,5 h = 352 kcal
        self.assertEqual(SP.kcal("laufen", 30, "mittel", 80), 352)
        self.assertEqual(SP.kcal("kraft", 60, "leicht", 80), round(2.5 * 80))
        self.assertIsNone(SP.kcal("gibtsnicht", 30, "mittel", 80))
        self.assertIsNone(SP.kcal("laufen", 0, "mittel", 80))
        self.assertIsNone(SP.kcal("laufen", 30, "mittel", None))
        for a in SP.AKTIVITAETEN.values():                          # MET steigt mit der Intensitaet
            self.assertLess(a["met"]["leicht"], a["met"]["intensiv"])

    def test_tag_und_bilanz(self):
        e = SP.eintrag("laufen", "Laufen", 30, "mittel", 352, False, ZEIT, "s1")
        m = S.sport_hinzu({}, HEUTE, e)
        m = S.sport_hinzu(m, HEUTE, SP.eintrag("eigene", "Klettern", 90, "mittel", 500, True, ZEIT, "s2"))
        t = S.tag_aus(m, HEUTE)
        self.assertEqual(SP.summe(t), (852, 120))
        m2, weg = S.entfernen(m, HEUTE, "sport", "s2")
        self.assertEqual(SP.summe(S.tag_aus(m2, HEUTE)), (352, 30))
        b = R.bilanz(2000, 2400, 1500, SP.summe(t)[0], sport_zusaetzlich=True)
        self.assertEqual(b["verbleibend"], 2000 + 852 - 1500)

    def test_sport_merken(self):
        d = S.sport_merken({}, "kraft", 75, "intensiv")
        d = S.sport_merken(d, "kraft", 60, "mittel")
        self.assertEqual(d["sport_nutzung"]["kraft"], {"n": 2, "minuten": 60.0, "intensitaet": "mittel"})


class Fasten(unittest.TestCase):
    def test_ueber_mitternacht(self):
        start = datetime.datetime(2026, 11, 17, 20, 0, tzinfo=R_BERLIN)
        d = FA.starten({}, start, FA.ziel_stunden("16:8"))
        d = FA.starten(d, start + datetime.timedelta(hours=1), 18)      # laeuft schon: kein Neustart
        st = FA.status(d["fasten"]["laeuft"], datetime.datetime(2026, 11, 18, 10, 30, tzinfo=R_BERLIN))
        self.assertAlmostEqual(st["dauer_h"], 14.5)
        self.assertEqual(st["ende_geplant"], datetime.datetime(2026, 11, 18, 12, 0, tzinfo=R_BERLIN))
        self.assertEqual(st["fenster_bis"], datetime.datetime(2026, 11, 18, 20, 0, tzinfo=R_BERLIN))
        self.assertFalse(st["erreicht"])
        d = FA.beenden(d, datetime.datetime(2026, 11, 18, 12, 15, tzinfo=R_BERLIN))
        self.assertIsNone(d["fasten"]["laeuft"])
        self.assertEqual([round(x[0], 2) for x in FA.am_tag(d["fasten"]["verlauf"], HEUTE)], [16.25])
        self.assertEqual(FA.am_tag(d["fasten"]["verlauf"], datetime.date(2026, 11, 17)), [])

    def test_zeitumstellung_und_texte(self):
        # 25.10.2026: Uhr wird von 3 auf 2 Uhr zurueckgestellt - die Nacht hat 25 Stunden
        start = datetime.datetime(2026, 10, 24, 20, 0, tzinfo=R_BERLIN)
        st = FA.status({"start": start.isoformat(), "ziel_h": 16},
                       datetime.datetime(2026, 10, 25, 12, 0, tzinfo=R_BERLIN))
        self.assertAlmostEqual(st["dauer_h"], 17)
        self.assertEqual(FA.dauer_text(14.5), "14:30 h")
        self.assertEqual(FA.dauer_text(15.999), "16:00 h")
        self.assertEqual(FA.ziel_stunden("eigene", 20), 20)
        self.assertEqual(FA.ziel_stunden("eigene", "x"), 16)

    def test_abbrechen_und_ende_nicht_vor_start(self):
        start = datetime.datetime(2026, 11, 18, 20, 0, tzinfo=R_BERLIN)
        d = FA.abbrechen(FA.starten({}, start, 16))
        self.assertEqual((d["fasten"]["laeuft"], d["fasten"]["verlauf"]), (None, []))
        d = FA.beenden(FA.starten({}, start, 16), start - datetime.timedelta(hours=1))
        self.assertEqual(d["fasten"]["verlauf"][0]["ende"], d["fasten"]["verlauf"][0]["start"])


class KoerperUndVorlagen(unittest.TestCase):
    def test_masse(self):
        m = S.masse_setzen({}, HEUTE, {"bauch": 92.04, "koerperfett": 21.5})
        m = S.masse_setzen(m, HEUTE, {"koerperfett": None})
        self.assertEqual(S.tag_aus(m, HEUTE)["masse"], {"bauch": 92.0})
        m = S.masse_setzen(m, datetime.date(2026, 11, 1), {"bauch": 94})
        self.assertEqual(S.mass_verlauf([m], "bauch"), [(datetime.date(2026, 11, 1), 94.0), (HEUTE, 92.0)])

    def test_vorlagen(self):
        e = [S.essen_eintrag(L.NACH_ID["haferflocken"], 1, "Portion", "Frühstück", ZEIT),
             S.essen_eintrag(L.NACH_ID["banane"], 1, "Stück", "Frühstück", ZEIT)]
        d = S.vorlage_speichern({}, "Standard-Frühstück", e, "v1")
        d = S.vorlage_speichern(d, "Standard-Frühstück", e[:1], "v2")      # gleicher Name ersetzt
        self.assertEqual([(v["id"], len(v["eintraege"])) for v in d["vorlagen"]], [("v2", 1)])
        self.assertNotIn("id", d["vorlagen"][0]["eintraege"][0])
        k = S.kopieren(d["vorlagen"][0]["eintraege"], ZEIT)
        m = S.essen_hinzu({}, HEUTE, k)
        self.assertAlmostEqual(S.tag_summen(S.tag_aus(m, HEUTE))["kcal"], 370 * 0.5)
        self.assertEqual(S.vorlage_entfernen(d, "v2")["vorlagen"], [])
        self.assertEqual(S.profil_doc({})["einstellungen"]["mahlzeiten"], S.MAHLZEITEN)


class Statistik(unittest.TestCase):
    def _daten(self):
        m, doc = {}, S.profil_doc({})
        doc = S.supplement_speichern(doc, SU.neues(SU.VORLAGEN[2], "mg", datetime.date(2026, 11, 1)))
        for i in range(14):                                         # 05.11. - 18.11.
            tag = HEUTE - datetime.timedelta(days=i)
            if i % 2 == 0:                                         # nur jeder zweite Tag dokumentiert
                m = S.essen_hinzu(m, tag, [S.essen_eintrag(L.NACH_ID["mandeln"], 100 + i, "g", "Snacks", ZEIT)])
                m = S.trinken_hinzu(m, tag, "wasser", 1000, ZEIT)
                m = S.einnahme_setzen(m, tag, doc["supplements"][0], "eingenommen", ZEIT)
            if i in (0, 13):
                m = S.gewicht_setzen(m, tag, 80 - (13 - i) * 0.1)
            if i == 3:
                m = S.sport_hinzu(m, tag, SP.eintrag("laufen", "Laufen", 30, "mittel", 350, False, ZEIT, "s"))
        return m, doc

    def test_zeitraum_und_monate(self):
        self.assertEqual(ST.zeitraum("7 Tage", HEUTE), (datetime.date(2026, 11, 12), HEUTE))
        self.assertEqual(ST.zeitraum("Monat", HEUTE), (datetime.date(2026, 11, 1), HEUTE))
        self.assertEqual(ST.zeitraum("Eigener", HEUTE, HEUTE, datetime.date(2026, 10, 1)),
                         (datetime.date(2026, 10, 1), HEUTE))
        self.assertEqual(ST.monate_zwischen(datetime.date(2025, 12, 15), datetime.date(2026, 2, 2)),
                         [datetime.date(2025, 12, 1), datetime.date(2026, 1, 1), datetime.date(2026, 2, 1)])

    def test_zusammenfassung_nur_erfasste_tage(self):
        m, doc = self._daten()
        r = ST.reihe(HEUTE - datetime.timedelta(days=13), HEUTE, lambda d: m, doc)
        z = ST.zusammenfassung(r)
        self.assertEqual((z["tage"], z["erfasst"]), (14, 7))
        mandeln = [100 + i for i in range(0, 14, 2)]
        self.assertAlmostEqual(z["kcal"], sum(595 * g / 100 for g in mandeln) / 7)   # Luecken zaehlen nicht als 0
        self.assertAlmostEqual(z["fluessigkeit_ml"], 1000)
        self.assertEqual((z["sport_tage"], z["sport_kcal"]), (1, 350))
        self.assertAlmostEqual(z["gewicht_diff"], -1.3)       # 80 kg (vor 13 Tagen) -> 78,7 kg (heute)
        self.assertAlmostEqual(z["supp_treue"], 50)                # 7 von 14 geplanten
        saetze = ST.aussagen(z, "in den letzten 14 Tagen")
        self.assertIn("an 7 von 14 Tagen", saetze[0])
        self.assertTrue(any("um -1,3 kg" in x for x in saetze))
        self.assertFalse(any("Mangel" in x for x in saetze))          # keine Diagnosen
        self.assertEqual(ST.aussagen(ST.zusammenfassung([]))[0][:6], "Für im")

    def test_wochenvergleich(self):
        m, doc = self._daten()
        diese = ST.reihe(HEUTE - datetime.timedelta(days=6), HEUTE, lambda d: m, doc)
        letzte = ST.reihe(HEUTE - datetime.timedelta(days=13), HEUTE - datetime.timedelta(days=7), lambda d: m, doc)
        v = {x[0]: x for x in ST.wochenvergleich(diese, letzte)}
        self.assertIn("Magnesium", v)
        self.assertIsNotNone(v["Kalorien"][3])
        self.assertIsNone(ST.veraenderung(5, 0))
        self.assertAlmostEqual(ST.veraenderung(110, 100), 10)
        self.assertEqual(v["Gewicht"][4], "kg")

    def test_kalender_und_export(self):
        m, doc = self._daten()
        r = ST.reihe(HEUTE - datetime.timedelta(days=13), HEUTE, lambda d: m, doc)
        self.assertEqual(ST.kalender_zeichen(r[-1]), ["🍽", "💧", "⚖", "💊"])
        self.assertEqual(ST.kalender_zeichen(r[-2]), [])
        csv_text = ST.als_csv(r)
        self.assertTrue(csv_text.startswith("\ufeffDatum;Kalorien"))
        self.assertIn("2026-11-18;", csv_text)
        self.assertIn(",", csv_text.splitlines()[-1])                # Dezimalkomma
        import json
        j = json.loads(ST.als_json(doc, {"2026-11": m}))
        self.assertEqual(j["profil"]["supplements"][0]["id"], "mg")
        self.assertIn("2026-11-18", j["monate"]["2026-11"]["tage"])

    def test_pdf(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab nicht installiert")
        m, doc = self._daten()
        r = ST.reihe(HEUTE - datetime.timedelta(days=13), HEUTE, lambda d: m, doc)
        z = R.ziele({"gewicht_kg": 80, "groesse_cm": 180, "geburtsjahr": 1986, "ziel": "halten"}, HEUTE)
        for detail in (False, True):
            pdf = BP.bericht(r, doc, z, "Gesundheitsbericht", r[0]["datum"], HEUTE, detail=detail)
            self.assertTrue(pdf.startswith(b"%PDF"))
        leer = BP.bericht(ST.reihe(HEUTE, HEUTE, lambda d: {}, {}), {}, R.ziele({}), "Leer", HEUTE, HEUTE, True)
        self.assertTrue(leer.startswith(b"%PDF"))


class Foto(unittest.TestCase):
    class _Antwort:
        def __init__(self, code, text=None, fehler=None):
            self.status_code, self._text, self._fehler = code, text, fehler

        def json(self):
            if self._fehler:
                return {"error": self._fehler}
            return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}

    def test_gemini_aufruf_und_fehler(self):
        gesendet = {}

        def post(url, headers=None, json=None, timeout=None):
            gesendet.update(url=url, headers=headers, json=json)
            return self._Antwort(200, '{"lebensmittel": []}')
        self.assertEqual(FO.gemini("k", "m1", "Prompt", b"bild", "image/jpeg", post), '{"lebensmittel": []}')
        teile = gesendet["json"]["contents"][0]["parts"]
        self.assertEqual(teile[1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(gesendet["headers"]["x-goog-api-key"], "k")
        self.assertIn("m1:generateContent", gesendet["url"])
        with self.assertRaises(FO.FotoFehler) as f:
            FO.gemini("", "m", "p", b"x", "image/jpeg", post)
        self.assertIn("GEMINI_API_KEY", str(f.exception))
        with self.assertRaises(FO.FotoFehler) as f:
            FO.gemini("k", "m", "p", b"x", "image/jpeg", lambda *a, **k: self._Antwort(429))
        self.assertIn("Kontingent", str(f.exception))

        def kaputt(*a, **k):
            raise OSError("netz")
        with self.assertRaises(FO.FotoFehler):
            FO.gemini("k", "m", "p", b"x", "image/jpeg", kaputt, warten=lambda s: None)

    def _folge(self, *antworten):
        """post-Attrappe: liefert die Antworten nacheinander und merkt sich die aufgerufenen Modelle."""
        aufrufe, rest = [], list(antworten)

        def post(url, headers=None, json=None, timeout=None):
            aufrufe.append(url.split("/models/")[1].split(":")[0])
            return rest.pop(0)
        return post, aufrufe

    def test_gemini_ueberlastet_wiederholen_und_ersatzmodell(self):
        ok = self._Antwort(200, "{}")
        post, aufrufe = self._folge(self._Antwort(503), ok)
        pausen = []
        self.assertEqual(FO.gemini("k", "m1", "p", b"x", "image/jpeg", post, warten=pausen.append), "{}")
        self.assertEqual((aufrufe, pausen), (["m1", "m1"], [2]))
        post, aufrufe = self._folge(self._Antwort(503), self._Antwort(503), ok)
        FO.gemini("k", "m1", "p", b"x", "image/jpeg", post, warten=lambda s: None)
        self.assertEqual(aufrufe, ["m1", "m1", FO.ERSATZ_MODELL])
        post, aufrufe = self._folge(self._Antwort(404), ok)             # Modell weg -> gleich Ersatzmodell
        FO.gemini("k", "m1", "p", b"x", "image/jpeg", post, warten=lambda s: None)
        self.assertEqual(aufrufe, ["m1", FO.ERSATZ_MODELL])
        post, _ = self._folge(*[self._Antwort(503)] * 3)
        with self.assertRaises(FO.FotoFehler) as f:
            FO.gemini("k", "m1", "p", b"x", "image/jpeg", post, warten=lambda s: None)
        self.assertIn("überlastet (Fehler 503)", str(f.exception))

    def test_gemini_fehler_verstaendlich(self):
        ungueltig = {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key.",
                     "details": [{"reason": "API_KEY_INVALID"}]}
        post, aufrufe = self._folge(self._Antwort(400, fehler=ungueltig))
        with self.assertRaises(FO.FotoFehler) as f:
            FO.gemini("geheim123", "m1", "p", b"x", "image/jpeg", post, warten=lambda s: None)
        self.assertIn("akzeptiert den Gemini-Schlüssel nicht", str(f.exception))
        self.assertNotIn("geheim123", str(f.exception))
        self.assertEqual(aufrufe, ["m1"])                               # kein sinnloses Wiederholen
        post, _ = self._folge(self._Antwort(403, fehler={"status": "PERMISSION_DENIED", "message": "denied"}))
        with self.assertRaises(FO.FotoFehler) as f:
            FO.gemini("k", "m1", "p", b"x", "image/jpeg", post)
        self.assertIn("Fehler 403", str(f.exception))
        post, _ = self._folge(self._Antwort(418))
        with self.assertRaises(FO.FotoFehler) as f:
            FO.gemini("k", "m1", "p", b"x", "image/jpeg", post)
        self.assertIn("Fehler 418", str(f.exception))

    def test_mahlzeit_auswerten(self):
        text = ('{"lebensmittel": [{"name": "Hähnchenbrust, gebraten", "menge_g": 180, "sicherheit": "hoch"},'
                '{"name": "Reis", "menge_g": "200"}, {"name": "Brokkoli", "menge_g": 99999},'
                '{"name": ""}, "kaputt"], "hinweis": "Schätzung"}')
        r = FO.mahlzeit_auswerten(text, L.MITGELIEFERT)
        self.assertEqual([p["name"] for p in r["posten"]], ["Hähnchenbrust, gebraten", "Reis", "Brokkoli"])
        self.assertEqual(r["posten"][0]["vorschlaege"][0]["id"], "haehnchen_gebraten")
        self.assertEqual(r["posten"][1]["gramm"], 200)
        self.assertEqual(r["posten"][2]["gramm"], 100)                       # unplausible Menge -> Standard
        self.assertEqual(r["posten"][1]["sicherheit"], "mittel")
        r = FO.mahlzeit_auswerten('Hier: {"lebensmittel": [{"name": "Banane", "menge_g": 120}]} fertig', L.MITGELIEFERT)
        self.assertEqual(r["posten"][0]["vorschlaege"][0]["id"], "banane")   # JSON in Text eingebettet
        with self.assertRaises(FO.FotoFehler):
            FO.mahlzeit_auswerten("kein json", L.MITGELIEFERT)

    def test_etikett_auswerten(self):
        text = ('{"produkt": "D3 Forte", "hersteller": "Marke", "form": "kapsel", "portion": "1 Kapsel", "inhalt": ['
                '{"naehrstoff": "Vitamin D3 (Cholecalciferol)", "menge": 1000, "einheit": "IU"},'
                '{"naehrstoff": "Zink", "menge": "10", "einheit": "mg"},'
                '{"naehrstoff": "Zink", "menge": 5, "einheit": "IE"},'
                '{"naehrstoff": "Coenzym Q10", "menge": 30, "einheit": "mg"}]}')
        e = FO.etikett_auswerten(text, SU.FORMEN)
        self.assertEqual((e["name"], e["form"], e["portion"]), ("D3 Forte", "Kapsel", "1 Kapsel"))
        self.assertEqual([(x["n"], x["menge"], x["einheit"]) for x in e["inhalt"]],
                         [("vit_d", 1000.0, "IE"), ("zink", 10.0, "mg")])
        self.assertEqual(e["unbekannt"], ["Zink 5 IE", "Coenzym Q10 30 mg"])   # Zink in IE, Coenzym Q10
        s = {**SU.neues(None, "x", HEUTE), "inhalt": e["inhalt"]}
        self.assertAlmostEqual(SU.inhalt_basis(s)[0]["vit_d"], 25)
        self.assertEqual(FO.etikett_auswerten('{"form": "Dose"}', SU.FORMEN)["form"], SU.FORMEN[0])

    def test_verkleinern(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow nicht installiert")
        import io
        puffer = io.BytesIO()
        Image.new("RGB", (4000, 3000), (200, 100, 50)).save(puffer, "PNG")
        klein, mime = FO.verkleinern(puffer.getvalue(), "image/png")
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(max(Image.open(io.BytesIO(klein)).size), FO.MAX_KANTE)
        self.assertEqual(FO.verkleinern(b"kein bild", "image/png"), (b"kein bild", "image/png"))


class Etappe6(unittest.TestCase):
    def test_vorschlaege_nach_tageszeit(self):
        d = {}
        for _ in range(3):
            d = S.nutzung_merken(d, "haferflocken", 1, "Portion", ZEIT, "Frühstück")
        for _ in range(5):
            d = S.nutzung_merken(d, "reis_gekocht", 1, "Portion", ZEIT, "Abendessen")
        d = S.favorit_umschalten(d, "kiwi")
        alle = L.MITGELIEFERT
        morgens = [x["id"] for x in L.vorschlaege(alle, d["nutzung"], d["favoriten"], "Frühstück")]
        abends = [x["id"] for x in L.vorschlaege(alle, d["nutzung"], d["favoriten"], "Abendessen")]
        self.assertEqual(morgens[0], "haferflocken")
        self.assertEqual(abends[0], "reis_gekocht")
        self.assertEqual(set(morgens), {"haferflocken", "reis_gekocht", "kiwi"})
        self.assertEqual(L.vorschlaege(alle, {}, (), "Frühstück"), [])
        self.assertEqual(d["nutzung"]["haferflocken"]["mahlzeiten"], {"Frühstück": 3})

    def test_eigene_getraenke_und_kcal(self):
        d, art = S.getraenk_speichern({}, "Eistee", 28)
        self.assertTrue(art.startswith("eigen:"))
        m = S.trinken_hinzu({}, HEUTE, art, 500, ZEIT, name="Eistee", kcal100=28)
        m = S.trinken_hinzu(m, HEUTE, "saft", 200, ZEIT)
        t = S.tag_aus(m, HEUTE)
        self.assertAlmostEqual(S.tag_summen(t)["kcal"], 140 + 90)
        self.assertEqual(S.getraenk_name(t["trinken"][0]), "Eistee")
        self.assertEqual(S.getraenk_name(t["trinken"][1]), "Saft")
        d, _ = S.getraenk_speichern(d, "Eistee light", 2, art)               # aendern: gleiche art
        self.assertEqual([(g["name"], g["kcal100"]) for g in d["einstellungen"]["getraenke"]], [("Eistee light", 2.0)])
        self.assertAlmostEqual(S.tag_summen(t)["kcal"], 230)                  # alte Tage behalten ihre Kopie
        self.assertEqual(S.getraenk_entfernen(d, art)["einstellungen"]["getraenke"], [])

    def test_haeufigste_menge(self):
        m = {}
        for ml in (330, 330, 500, 250, 330):
            m = S.trinken_hinzu(m, HEUTE, "wasser", ml, ZEIT)
        self.assertEqual(S.haeufigste_menge([m]), 330)
        self.assertIsNone(S.haeufigste_menge([S.trinken_hinzu({}, HEUTE, "wasser", 400, ZEIT)]))
        self.assertIsNone(S.haeufigste_menge([m], art="tee"))

    def test_lebensmittel_verwalten(self):
        lm = {"id": "eigen:1", "name": "Omas Kuchen", "basis": "g", "pro100": {"kcal": 300}, "einheiten": {"Stück": 90}}
        d = S.lebensmittel_speichern({}, lm)
        d = S.favorit_umschalten(S.nutzung_merken(d, "eigen:1", 1, "Stück", ZEIT), "eigen:1")
        e = S.essen_eintrag(lm, 1, "Stück", "Nachmittag", ZEIT)
        d = S.lebensmittel_speichern(d, {**lm, "pro100": {"kcal": 350}})
        self.assertEqual([x["pro100"]["kcal"] for x in d["eigene"]], [350])
        self.assertAlmostEqual(S.eintrag_naehrwerte(e)["kcal"], 270)          # alter Eintrag unveraendert
        d = S.lebensmittel_entfernen(d, "eigen:1")
        self.assertEqual((d["eigene"], d["favoriten"], d["nutzung"]), ([], [], {}))

    def test_tag_kopieren_und_vorlage_umbenennen(self):
        quelle = datetime.date(2026, 10, 30)
        mq = S.essen_hinzu({}, quelle, [S.essen_eintrag(L.NACH_ID["ei"], 2, "Stück", "Frühstück", ZEIT)])
        mz, n = S.tag_kopieren(mq, quelle, {}, HEUTE, ZEIT)
        self.assertEqual(n, 1)
        self.assertEqual(S.tag_aus(mz, HEUTE)["essen"][0]["menge"], 2)
        self.assertEqual(S.tag_kopieren({}, quelle, {}, HEUTE, ZEIT), ({}, 0))
        d = S.vorlage_speichern({}, "Alt", [], "v1")
        self.assertEqual(S.vorlage_umbenennen(d, "v1", "Neu")["vorlagen"][0]["name"], "Neu")
        self.assertEqual(S.vorlage_umbenennen(d, "v1", "  ")["vorlagen"][0]["name"], "Alt")
        sup = S.supplement_speichern({}, SU.neues(SU.VORLAGEN[0], "d3", HEUTE))
        S.supplement_entfernen(sup, "d3")
        self.assertTrue(sup["supplements"][0]["aktiv"])                    # Original bleibt unveraendert


class SucheUndRoutinen(unittest.TestCase):
    def test_suche_naehrstoff(self):
        mg = SU.neues(SU.VORLAGEN[2], "mg", HEUTE)                  # Magnesium-Supplement
        d3 = SU.neues(SU.VORLAGEN[0], "d3", HEUTE)
        r = SC.suchen("Magnesium", L.MITGELIEFERT, [mg, d3])
        self.assertEqual(r["naehrstoffe"][0], "magnesium")
        self.assertEqual([x["id"] for x in r["supplements"]], ["mg"])
        reich = [x["id"] for x in r["reich_an"]["magnesium"]]
        self.assertIn("leinsamen", reich[:2])                       # 392 mg je 100 g
        self.assertEqual(r["lebensmittel"], [])                     # kein Lebensmittel heisst "Magnesium"
        self.assertEqual(SC.suchen("folsäure", L.MITGELIEFERT)["naehrstoffe"][0], "vit_b9")
        self.assertEqual(SC.suchen("Vitamin D", L.MITGELIEFERT, [mg, d3])["supplements"][0]["id"], "d3")

    def test_suche_lebensmittel_vorlage_sport(self):
        v = [{"id": "v1", "name": "Standard-Frühstück", "eintraege": []}]
        r = SC.suchen("ban", L.MITGELIEFERT, [], v)
        self.assertEqual(r["lebensmittel"][0]["id"], "banane")
        self.assertEqual(SC.suchen("frühst", L.MITGELIEFERT, [], v)["vorlagen"][0]["id"], "v1")
        self.assertEqual(SC.suchen("lauf", L.MITGELIEFERT)["sport"], ["laufen"])
        self.assertEqual(SC.suchen("x", L.MITGELIEFERT)["lebensmittel"], [])        # zu kurz
        inaktiv = {**SU.neues(SU.VORLAGEN[2], "alt", HEUTE), "aktiv": False}
        self.assertEqual(SC.suchen("magnesium", L.MITGELIEFERT, [inaktiv])["supplements"], [])

    def test_routinen(self):
        d3, mg = SU.neues(SU.VORLAGEN[0], "d3", HEUTE), SU.neues(SU.VORLAGEN[2], "mg", HEUTE)
        d, rid = S.routine_speichern({}, "Training", ["d3", "mg", "d3", "weg"])
        self.assertEqual(d["routinen"][0]["sups"], ["d3", "mg", "weg"])
        m, n = S.routine_einnehmen({}, HEUTE, d["routinen"][0], [d3, mg], ZEIT)
        self.assertEqual(n, 2)                                      # unbekanntes Supplement uebersprungen
        self.assertEqual({x["sup"] for x in S.tag_aus(m, HEUTE)["supplements"]}, {"d3", "mg"})
        d, _ = S.routine_speichern(d, "Abends", ["mg"], rid)
        self.assertEqual([(r["name"], r["sups"]) for r in d["routinen"]], [("Abends", ["mg"])])
        self.assertEqual(S.routine_entfernen(d, rid)["routinen"], [])


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
            def ordner_loeschen(ordner):
                weg = [p for p in list(store) if p.startswith(ordner + "/")]
                for p in weg:
                    del store[p]
                return True, len(weg)
            gesundheit_ui.seite({"lesen": lesen, "aktualisiere": akt, "upfad": lambda p: p, "speichern": True,
                                 "get": None, "liste": lambda o: [p for p in store if p.startswith(o + "/")],
                                 "ordner_loeschen": ordner_loeschen, "ki": {"key": "test", "modell": "test"},
                                 "post": lambda *a, **k: None})

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
        # Routine anlegen und mit einem Tipp einnehmen
        at.text_input(key="gs_rt_neu_name").input("Training").run()
        at.button_group(key="gs_rt_neu_sups").set_value([sups[0]["id"]]).run()
        knopf("＋ Routine anlegen").click().run()
        self.assertFalse(at.exception)
        self.assertEqual([r["name"] for r in store[S.PFAD_PROFIL]["routinen"]], ["Training"])
        # Zentrale Suche: Naehrstoff -> Details, Lebensmittel -> Essen mit Vorauswahl
        at.session_state["gs_bereich_neu"] = "Heute"
        at.run()
        at.text_input(key="gs_suche").input("Magnesium").run()
        self.assertFalse(at.exception)
        knopf("Details zu Magnesium").click().run()
        self.assertEqual((at.session_state["gs_bereich"], at.session_state["gs_mikro_detail"]), ("Vitamine", "magnesium"))
        at.session_state["gs_bereich_neu"] = "Heute"
        at.run()
        at.text_input(key="gs_suche").input("Haferfl").run()
        knopf("＋ Haferflocken").click().run()
        self.assertFalse(at.exception)
        self.assertEqual((at.session_state["gs_bereich"], at.session_state["gs_wahl"]), ("Essen", "haferflocken"))
        # Naehrstoffe: Vitamin D aus dem Supplement, Details ohne Fehler
        at.session_state["gs_bereich_neu"] = "Nährstoffe"
        at.run()
        at.selectbox(key="gs_mikro_detail").set_value("vit_d").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Supplements: 25,0 µg" in m.value for m in at.markdown))
        # Fasten: ein Tipp auf "Heute" startet, einer beendet
        at.session_state["gs_bereich_neu"] = "Heute"
        at.run()
        knopf("⏱ Fasten starten").click().run()
        self.assertTrue(store[S.PFAD_PROFIL]["fasten"]["laeuft"])
        knopf("⏹ Fasten beenden").click().run()
        self.assertEqual(len(store[S.PFAD_PROFIL]["fasten"]["verlauf"]), 1)
        # Sport: Aktivitaet waehlen, speichern
        at.session_state["gs_bereich_neu"] = "Sport"
        at.run()
        at.button_group(key="gs_sport_art").set_value("laufen").run()
        knopf("Speichern").click().run()
        self.assertFalse(at.exception)
        t = S.tag_aus(store[S.monat_pfad(heute)], heute)
        self.assertEqual([(x["art"], x["minuten"]) for x in t["sport"]], [("laufen", 30.0)])
        self.assertGreater(t["sport"][0]["kcal"], 0)
        # Foto: Erkennungsergebnis liegt vor (wie nach "Erkennen") -> Menge aendern -> erst "Übernehmen" speichert
        at.session_state["gs_foto_an"] = True
        at.session_state["gs_foto_ergebnis"] = FO.mahlzeit_auswerten(
            '{"lebensmittel": [{"name": "Reis, gekocht", "menge_g": 200}, {"name": "Brokkoli", "menge_g": 120}]}',
            L.MITGELIEFERT)
        at.session_state["gs_bereich_neu"] = "Essen"
        at.run()
        self.assertFalse(at.exception)
        vorher = len(S.tag_aus(store[S.monat_pfad(heute)], heute)["essen"])
        at.number_input(key="gs_fp_g_0").set_value(150).run()
        at.checkbox(key="gs_fp_an_1").uncheck().run()                 # Brokkoli nicht uebernehmen
        knopf("✓ Übernehmen").click().run()
        self.assertFalse(at.exception)
        neu = S.tag_aus(store[S.monat_pfad(heute)], heute)["essen"][vorher:]
        self.assertEqual([(e["lm"], e["menge"], e["einheit"], e.get("foto")) for e in neu],
                         [("reis_gekocht", 150.0, "g", True)])
        self.assertNotIn("gs_foto_an", at.session_state)
        # Statistik ohne Fehler, dann alles loeschen -> Einrichtung beginnt von vorn
        at.session_state["gs_bereich_neu"] = "Statistik"
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any("an 1 von 7 Tagen" in m.value for m in at.markdown))
        at.session_state["gs_bereich_neu"] = "Profil"
        at.run()
        at.text_input(key="gs_loeschen_text").input("LÖSCHEN").run()
        knopf("Endgültig löschen").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(store, {})
        self.assertTrue(any(b.label == "Gewicht halten" for b in at.button))


class NurAdmin(unittest.TestCase):
    def test_gesundheit_nur_fuer_angemeldeten_admin(self):
        """Gesundheitsdaten: dieselbe Sperre wie die Benutzerverwaltung (kein Zugriff ohne Admin-Login)."""
        with open("app.py", encoding="utf-8") as f:
            quelle = f.read()
        self.assertIn('if ansicht in (ANSICHT_BENUTZER, ANSICHT_GESUNDHEIT):', quelle)
        self.assertIn('_zugang_pruefen(ANSICHT_GESUNDHEIT)', quelle)


if __name__ == "__main__":
    unittest.main()
