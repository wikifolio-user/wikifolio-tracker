"""Tests fuer den Altersteilzeit- & Rentenrechner (atz_rechner) - Sollwerte von Hand bzw. aus dem Gesetz."""
import datetime
import unittest

import abfindung
from atz_rechner import kapital as K
from atz_rechner import parameter as P
from atz_rechner import plan
from atz_rechner import rente as R
from atz_rechner import steuer as S

PAR = P.werte()
HEUTE = datetime.date(2026, 10, 30)


class Altersgrenzen(unittest.TestCase):
    def test_regelaltersgrenze_je_jahrgang(self):
        soll = {1958: (66, 0), 1959: (66, 2), 1960: (66, 4), 1961: (66, 6), 1962: (66, 8), 1963: (66, 10),
                1964: (67, 0), 1970: (67, 0), 1953: (65, 7)}
        for jg, (j, m) in soll.items():
            self.assertEqual(R.regelaltersgrenze(jg), j * 12 + m, jg)

    def test_besonders_langjaehrig(self):
        soll = {1952: (63, 0), 1953: (63, 2), 1958: (64, 0), 1960: (64, 4), 1963: (64, 10), 1964: (65, 0)}
        for jg, (j, m) in soll.items():
            self.assertEqual(R.grenze_besonders_langjaehrig(jg), j * 12 + m, jg)

    def test_schwerbehindert(self):
        soll = {1958: ((64, 0), (61, 0)), 1960: ((64, 4), (61, 4)), 1963: ((64, 10), (61, 10)),
                1964: ((65, 0), (62, 0)), 1955: ((63, 9), (60, 9))}
        for jg, ((a, b), (c, d)) in soll.items():
            self.assertEqual(R.grenze_schwerbehindert(jg), (a * 12 + b, c * 12 + d), jg)

    def test_langjaehrig_fruehestens_63(self):
        self.assertEqual(R.grenzen(1964)["langjaehrig"], (67 * 12, 63 * 12))

    def test_rentenbeginn_monat_nach_geburtstag(self):
        # geboren Juni 1964 -> 67 im Juni 2031 -> Rente ab 1. Juli 2031; am 1. geboren -> ab Juni
        self.assertEqual(R.jahr_monat(R.beginn_idx(1964, 6, 67 * 12)), (2031, 7))
        self.assertEqual(R.jahr_monat(R.beginn_idx(1964, 6, 67 * 12, am_ersten=True)), (2031, 6))
        self.assertEqual(R.jahr_monat(R.beginn_idx(1964, 12, 63 * 12)), (2028, 1))


class Abschlaege(unittest.TestCase):
    def test_abschlag_je_monat_und_hoechstens(self):
        self.assertAlmostEqual(R.abschlag(1, PAR), 0.003)
        self.assertAlmostEqual(R.abschlag(36, PAR), 0.108)
        self.assertAlmostEqual(R.abschlag(48, PAR), 0.144)
        self.assertAlmostEqual(R.abschlag(60, PAR), 0.144)
        self.assertEqual(R.abschlag(-5, PAR), 0.0)

    def test_beste_art(self):
        # Jahrgang 1964, mit 63: nur langjaehrig (14,4 %); mit 45 Jahren ab 65 abschlagsfrei
        art, a = R.beste_art(1964, 63 * 12, ["regel", "langjaehrig"], PAR)
        self.assertEqual((art, round(a, 4)), ("langjaehrig", 0.144))
        art, a = R.beste_art(1964, 65 * 12, ["regel", "langjaehrig", "besonders"], PAR)
        self.assertEqual((art, a), ("besonders", 0.0))
        art, a = R.beste_art(1964, 62 * 12, ["regel", "langjaehrig", "schwerbehindert"], PAR)
        self.assertEqual((art, round(a, 4)), ("schwerbehindert", 0.108))
        self.assertEqual(R.beste_art(1964, 62 * 12, ["regel", "langjaehrig"], PAR), (None, None))

    def test_wartezeiten(self):
        j35, j45 = R.wartezeit_jahre({"pflicht": 40, "kinder": 3, "pflege": 1, "ausbildung": 10, "alg": 1})
        self.assertEqual((j35, j45), (40 + 3 + 1 + 8 + 1, 40 + 3 + 1 + 1))   # Ausbildung hoechstens 8, nicht bei 45

    def test_ausgleichszahlung(self):
        a = R.ausgleichszahlung(40.0, 0.144, PAR)
        x = 40 * 0.144 / 0.856
        self.assertAlmostEqual(a["ep"], x)
        self.assertAlmostEqual(a["kosten"], x * 51944 * 0.186, places=2)
        # nach dem Ausgleich: (40 + x) * (1 - 14,4 %) = 40 EP
        self.assertAlmostEqual((40 + a["ep"]) * 0.856, 40.0)

    def test_break_even(self):
        self.assertEqual(R.break_even_monate(1200, 100), 12)
        self.assertIsNone(R.break_even_monate(1000, 0))
        self.assertLess(R.break_even_monate(12000, 100, 5.0), 120)

    def test_rentenwert_anpassung_juli(self):
        self.assertAlmostEqual(R.rentenwert(PAR, R.idx(2027, 6)), 42.52)
        self.assertAlmostEqual(R.rentenwert(PAR, R.idx(2027, 7)), 42.52 * 1.02)

    def test_entgeltpunkte(self):
        self.assertAlmostEqual(12 * R.ep_monat(51944 / 12, PAR, 2026), 1.0)
        self.assertAlmostEqual(12 * R.ep_monat(200000 / 12, PAR, 2026), 101400 / 51944)   # BBG


class Steuer(unittest.TestCase):
    def test_tarif_gleich_abfindungsrechner(self):
        for zve in (0, 12348, 12349, 15000, 17799, 30000, 50000, 69878, 69879, 100000, 300000):
            self.assertEqual(S.tarif(zve, PAR), abfindung.est_tarif(zve, 2026), zve)

    def test_tarif_von_hand(self):
        self.assertEqual(S.tarif(50000, PAR), 10548.0)    # Zone 3: (173,10 z + 2397) z + 1034,87
        self.assertEqual(S.tarif(12348, PAR), 0.0)

    def test_splitting_und_progressionsvorbehalt(self):
        self.assertEqual(S.est(60000, PAR, splitting=True), 2 * S.tarif(30000, PAR))
        ohne = S.est(30000, PAR)
        mit = S.est(30000, PAR, pv=6000)
        self.assertGreater(mit, ohne)
        self.assertEqual(mit, float(int(30000 * S.tarif(36000, PAR) / 36000)))

    def test_fuenftelregelung(self):
        normal = S.est(40000 + 50000, PAR)
        fuenftel = S.est_fuenftel(40000, 50000, PAR)
        self.assertLess(fuenftel, normal)
        self.assertAlmostEqual(fuenftel, S.est(40000, PAR) + 5 * (S.est(50000, PAR) - S.est(40000, PAR)))

    def test_besteuerungsanteil(self):
        self.assertAlmostEqual(S.besteuerungsanteil(2005), 0.50)
        self.assertAlmostEqual(S.besteuerungsanteil(2020), 0.80)
        self.assertAlmostEqual(S.besteuerungsanteil(2023), 0.825)
        self.assertAlmostEqual(S.besteuerungsanteil(2026), 0.84)
        self.assertAlmostEqual(S.besteuerungsanteil(2031), 0.865)
        self.assertAlmostEqual(S.besteuerungsanteil(2058), 1.0)
        self.assertAlmostEqual(S.besteuerungsanteil(2070), 1.0)

    def test_ertragsanteil(self):
        self.assertEqual(S.ertragsanteil(60), 0.22)
        self.assertEqual(S.ertragsanteil(63), 0.20)
        self.assertEqual(S.ertragsanteil(65), 0.18)
        self.assertEqual(S.ertragsanteil(66), 0.18)
        self.assertEqual(S.ertragsanteil(67), 0.17)

    def test_altersentlastung_und_versorgungsfreibetrag(self):
        self.assertEqual(S.altersentlastung(2005), (0.40, 1900.0))
        a, b = S.altersentlastung(2020)
        self.assertAlmostEqual(a, 0.16); self.assertEqual(b, 760.0)
        a, b = S.altersentlastung(2026)
        self.assertAlmostEqual(a, 0.124); self.assertEqual(b, 589.0)
        a, b, c = S.versorgungsfreibetrag(2026)
        self.assertAlmostEqual(a, 0.124); self.assertEqual((b, c), (930.0, 279.0))
        a, b, c = S.versorgungsfreibetrag(2025)
        self.assertAlmostEqual(a, 0.128); self.assertEqual((b, c), (960.0, 288.0))

    def test_halbeinkuenfte(self):
        self.assertEqual(S.halbeinkuenfte(2000, 2030, 66), "steuerfrei")
        self.assertEqual(S.halbeinkuenfte(2010, 2030, 61), "halb")      # Altvertrag bis 2011: ab 60
        self.assertEqual(S.halbeinkuenfte(2015, 2030, 61), "voll")      # ab 2012: erst ab 62
        self.assertEqual(S.halbeinkuenfte(2020, 2030, 66), "voll")      # keine 12 Jahre

    def test_abgeltung_mit_kirchensteuer(self):
        self.assertAlmostEqual(S.abgeltung_satz(PAR, 0.0), 0.25 * 1.055)
        k = 0.09
        kest = 0.25 / (1 + 0.25 * k)
        self.assertAlmostEqual(S.abgeltung_satz(PAR, k), kest * (1.055 + k))

    def test_atz_netto_aufstockung_steuerfrei(self):
        ohne = S.netto_arbeitnehmer(2500, PAR)
        mit = S.netto_arbeitnehmer(2500, PAR, steuerfrei_monat=500)
        self.assertGreater(mit["netto"], ohne["netto"])            # Aufstockung kommt dazu ...
        self.assertGreater(mit["steuer"], ohne["steuer"])          # ... erhoeht aber den Steuersatz
        self.assertEqual(mit["sv"], ohne["sv"])                    # und ist sozialversicherungsfrei


class Kapital(unittest.TestCase):
    def test_annuitaet_verbraucht_kapital(self):
        k, r, n, g = 200000.0, 0.04, 25, 0.02
        w = K.annuitaet(k, r, n, g)
        for _ in range(n):
            k = k * (1 + r) - w
            w *= 1 + g
        self.assertAlmostEqual(k, 0.0, places=4)

    def test_reichweite(self):
        self.assertAlmostEqual(K.reichweite(100000, 0.0, 10000), 10.0)
        self.assertIsNone(K.reichweite(100000, 0.05, 4000))          # Ertraege > Entnahme
        self.assertLess(K.reichweite(100000, 0.0, 10000, 0.05), 10.0)

    def test_brutto_fuer_netto(self):
        satz = S.abgeltung_satz(PAR)
        b = K.brutto_fuer_netto(10000, 100000, 50000, satz, 1000)
        st, _, _ = K.steuer_auf_entnahme(b, 100000, 50000, satz, 1000)
        self.assertAlmostEqual(b - st, 10000, places=1)
        self.assertEqual(K.brutto_fuer_netto(10000, 100000, 100000, satz, 0), 10000)   # kein Gewinn

    def test_sparplan(self):
        self.assertAlmostEqual(K.sparplan_endwert(1000, 100, 0.0, 2), 1000 + 2400)
        self.assertAlmostEqual(K.sparplan_endwert(1000, 0, 0.05, 1), 1050)


class Planung(unittest.TestCase):
    def test_regel_ohne_abschlag(self):
        erg = plan.berechne({}, PAR, HEUTE, "regel")
        self.assertEqual(R.jahr_monat(erg["zeit"]["rente"]), (2031, 7))
        self.assertEqual(erg["zeit"]["abschlag"], 0.0)
        self.assertEqual(erg["zeilen"][-1]["alter"], 95)

    def test_fruehestens_63_mit_abschlag(self):
        erg = plan.berechne({"rente_wahl": "frueh"}, PAR, HEUTE)
        self.assertEqual(R.jahr_monat(erg["zeit"]["rente"]), (2027, 7))
        self.assertAlmostEqual(erg["zeit"]["abschlag"], 0.144)

    def test_45_jahre_abschlagsfrei_ab_65(self):
        erg = plan.berechne({"jahre_pflicht": 43.0, "rente_wahl": "abschlagsfrei"}, PAR, HEUTE)
        self.assertEqual(erg["zeit"]["art"], "besonders")
        self.assertEqual(R.jahr_monat(erg["zeit"]["rente"]), (2029, 7))

    def test_atz_ep_90_prozent(self):
        # ATZ: 50 % Entgelt + AG-Beitraege auf 80 % davon = 90 % der Vollzeit-Punkte
        e = plan.normalisieren({})
        t = {"rente": 10 ** 9, "atz_start": 0, "erwerb_ende": 10 ** 9, "modell": "Gleichverteilungsmodell",
             "atz_rv": 80.0, "alg_von": 0, "alg_bis": 0, "atz_mitte": 0}
        voll = R.ep_monat(5000, PAR, 2026)
        e["brutto_jahr"] = 60000.0
        i = R.idx(2026, 11)
        self.assertAlmostEqual(plan._ep_bis(e, PAR, i, i + 1, t), 0.9 * voll)

    def test_ausgleich_hebt_abschlag_auf(self):
        ohne = plan.berechne({"rente_wahl": "frueh"}, PAR, HEUTE)
        mit = plan.berechne({"rente_wahl": "frueh", "ausgleich": True}, PAR, HEUTE)
        voll = ohne["ep_summe"] * R.rentenwert(PAR, ohne["zeit"]["rente"])
        self.assertAlmostEqual(mit["rente_start_brutto"], voll, places=6)
        self.assertGreater(mit["ausgleich"]["kosten"], 0)

    def test_vergleich_und_ampel(self):
        a = plan.berechne({"kapital": 400000, "einstand": 300000}, PAR, HEUTE)
        b = plan.berechne({"kapital": 400000, "einstand": 300000}, PAR, HEUTE, "regel")
        v = plan.vergleich_tabelle(a, b)
        self.assertEqual(len(v), len(a["zeilen"]))
        self.assertAlmostEqual(v[-1]["diff_kumuliert"], sum(x["diff_monat"] * z["monate"] for x, z in zip(v, a["zeilen"])))
        self.assertIn(plan.ampel(a)[0], ("gruen", "gelb", "rot"))
        arm = plan.berechne({"kapital": 0, "einstand": 0, "sparrate": 0, "bedarf": 5000}, PAR, HEUTE)
        self.assertEqual(plan.ampel(arm)[0], "rot")

    def test_szenario_json_kompatibel(self):
        alt = {"geb_jahr": "1963", "ep": "35,5", "unbekannt": 1, "vertraege": None}
        e = plan.normalisieren(alt)
        self.assertEqual(e["geb_jahr"], 1963)
        self.assertEqual(e["ep"], plan.STANDARD["ep"])     # unlesbar -> Standard
        self.assertNotIn("unbekannt", e)
        self.assertEqual(e["vertraege"], [])

    def test_parameter_eigene_werte(self):
        p = P.werte({"rentenwert": "45.0", "gibtsnicht": 3, "rv_satz": "abc"})
        self.assertEqual(p["rentenwert"], 45.0)
        self.assertEqual(p["rv_satz"], 18.6)
        self.assertNotIn("gibtsnicht", p)


if __name__ == "__main__":
    unittest.main()
