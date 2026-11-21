"""Tests fuer den Knock-out-Gewinnrechner (ko_rechner.py) - ohne Streamlit, ohne Netz."""
import datetime
import unittest
from zoneinfo import ZoneInfo

import ko_rechner as K

BER = ZoneInfo("Europe/Berlin")
NY = ZoneInfo("America/New_York")


def _datei(**werte):
    return {"werte": {sym: w for sym, w in werte.items()}}


class Kalender(unittest.TestCase):
    def test_ostern_und_feiertage(self):
        self.assertEqual(K.ostersonntag(2026), datetime.date(2026, 4, 5))
        self.assertEqual(K.ostersonntag(2027), datetime.date(2027, 3, 28))
        x = K.feiertage("XETRA", 2026)
        self.assertTrue({datetime.date(2026, 4, 3), datetime.date(2026, 4, 6), datetime.date(2026, 12, 24)} <= x)
        n = K.feiertage("NYSE", 2026)
        self.assertIn(datetime.date(2026, 11, 26), n)                    # Thanksgiving
        self.assertIn(datetime.date(2026, 7, 3), n)                      # 4. Juli = Samstag -> Freitag
        self.assertIn(datetime.date(2026, 1, 19), n)                     # Martin Luther King Day
        self.assertIn(datetime.date(2026, 5, 25), n)                     # Memorial Day (letzter Montag)
        self.assertNotIn(datetime.date(2021, 12, 31), K.feiertage("NYSE", 2022))   # Neujahr Sa: kein Ersatz

    def test_offen_und_letzter_schluss(self):
        self.assertTrue(K.boerse_offen("XETRA", datetime.datetime(2026, 11, 20, 10, 0, tzinfo=BER)))
        self.assertFalse(K.boerse_offen("XETRA", datetime.datetime(2026, 11, 21, 10, 0, tzinfo=BER)))   # Samstag
        self.assertFalse(K.boerse_offen("NYSE", datetime.datetime(2026, 11, 26, 11, 0, tzinfo=NY)))     # Thanksgiving
        self.assertTrue(K.boerse_offen("NYSE", datetime.datetime(2026, 11, 20, 15, 59, tzinfo=NY)))
        s = K.letzter_handelsschluss("NYSE", datetime.datetime(2026, 11, 23, 8, 0, tzinfo=NY))   # Montag frueh
        self.assertEqual(s, datetime.datetime(2026, 11, 20, 16, 0, tzinfo=NY))
        s = K.letzter_handelsschluss("XETRA", datetime.datetime(2026, 4, 7, 8, 0, tzinfo=BER))   # nach Ostern
        self.assertEqual(s.date(), datetime.date(2026, 4, 2))
        self.assertEqual(K.handelstage("XETRA", datetime.date(2026, 12, 23), datetime.date(2026, 12, 31)), 3)


class Marktdaten(unittest.TestCase):
    def test_live_schluss_veraltet_fehlt(self):
        jetzt = datetime.datetime(2026, 11, 20, 15, 0, tzinfo=BER)                   # Freitag, Xetra offen
        d = _datei(**{"^GDAXI": {"k": 24100, "p": 24000, "t": "2026-11-20T14:40:00+01:00"}})
        m = K.marktdaten(d, "DAX", jetzt)
        self.assertEqual((m["status"], m["waehrung"], m["symbol"]), ("live", "EUR", "DAX"))
        self.assertAlmostEqual(m["diff"], 100)
        self.assertAlmostEqual(m["pct"], 100 / 240)
        self.assertEqual(K.marktdaten(d, "DAX", jetzt + datetime.timedelta(hours=2))["status"], "veraltet")
        sa = datetime.datetime(2026, 11, 21, 12, 0, tzinfo=BER)
        d2 = _datei(**{"^GDAXI": {"k": 24100, "p": 24000, "t": "2026-11-20T17:40:00+01:00",
                                  "m": "2026-11-20T16:35:00+00:00"}})
        self.assertEqual(K.marktdaten(d2, "DAX", sa)["status"], "schluss")
        alt = _datei(**{"^GDAXI": {"k": 24100, "p": 24000, "t": "2026-11-10T17:40:00+01:00"}})
        self.assertEqual(K.marktdaten(alt, "DAX", sa)["status"], "veraltet")
        leer = K.marktdaten({}, "NDX", sa)
        self.assertEqual((leer["status"], leer["kurs"], leer["waehrung"]), ("fehlt", None, "USD"))
        self.assertIn("von Hand", leer["hinweis"])
        self.assertEqual(K.eurusd(_datei(**{"EURUSD=X": {"k": 1.16}})), 1.16)
        self.assertIsNone(K.eurusd({}))

    def test_nur_offizielle_indexsymbole(self):
        self.assertEqual({i["yahoo"] for i in K.INDIZES.values()}, {"^NDX", "^GDAXI", "^GSPC", "^DJI"})


class Eingaben(unittest.TestCase):
    def test_kursziel_bereich_je_index(self):
        for kurs, schritt in ((24000, 50), (6800, 10), (48000, 50), (950, 1)):
            lo, hi, s = K.kursziel_bereich(kurs)
            self.assertEqual(s, schritt)
            self.assertTrue(lo <= kurs * 0.5 + s and hi >= kurs * 1.5 - s)
        self.assertEqual(K.kursziel_standard(24000), 26400)
        self.assertEqual(K.kursziel_standard(24000, "short"), 21600)

    def test_termine_und_pruefung(self):
        heute = datetime.date(2026, 11, 21)
        self.assertEqual(K.zieltermin_standard(heute), datetime.date(2027, 1, 29))
        self.assertEqual(K.zieltermin_standard(datetime.date(2027, 3, 1)), datetime.date(2027, 6, 1))
        self.assertEqual(K.zieltermin_schnell(datetime.date(2026, 11, 30), 3), datetime.date(2027, 2, 28))
        self.assertEqual(K.pruefe(10000, 100, 110, 3, "long"), [])
        self.assertEqual(len(K.pruefe(500, -1, 0, 30, "seitwaerts")), 5)


class Simulation(unittest.TestCase):
    def test_long_short(self):
        r = K.simulation(10000, 20000, 22000, 3, "long")
        self.assertAlmostEqual(r["index_pct"], 10)
        self.assertAlmostEqual(r["rendite_pct"], 30)
        self.assertAlmostEqual(r["gv"], 3000)
        self.assertAlmostEqual(r["endwert"], 13000)
        self.assertAlmostEqual(r["ko_schwelle"], 20000 * 2 / 3)
        s = K.simulation(10000, 20000, 22000, 3, "short")
        self.assertEqual([round(s[k], 6) for k in ("rendite_pct", "gv", "endwert")], [-30, -3000, 7000])
        self.assertAlmostEqual(s["ko_schwelle"], 20000 * 4 / 3)

    def test_verlust_hoechstens_einsatz(self):
        r = K.simulation(10000, 20000, 15000, 5, "long")                 # -25 % x 5 = -125 %
        self.assertEqual((r["rendite_pct"], r["gv"], r["endwert"]), (-100, -10000, 0))
        self.assertTrue(r["ko_erreicht"])
        self.assertFalse(K.simulation(10000, 20000, 15000, 1, "long")["ko_erreicht"])   # 1x: kein KO

    def test_hebelvergleich_alle_indizes_beide_richtungen(self):
        for start in (24000, 6800, 25000, 48000):
            for richtung in ("long", "short"):
                v = K.hebel_vergleich(10000, start, start * 1.05, richtung)
                self.assertEqual([x["hebel"] for x in v], [2, 3, 4, 5, 7, 10])
                vz = 1 if richtung == "long" else -1
                self.assertTrue(all(abs(x["rendite_pct"] - vz * 5 * x["hebel"]) < 1e-9 for x in v))

    def test_ungueltig(self):
        with self.assertRaises(ValueError):
            K.simulation(10000, 0, 100, 3, "long")


def _produkt(**k):
    p = {"basiswert": "DAX", "richtung": "long", "basispreis": 20000.0, "ko_schwelle": 20000.0, "bezug": 0.01,
         "geld": 39.99, "brief": 40.01, "finanzierung_pct": 0.0, "restwert": 0.0}
    p.update(k)
    return p


class Zertifikat(unittest.TestCase):
    def test_dax_long_ohne_kosten(self):
        r = K.zertifikat(_produkt(), 10000, 24000, 26400)
        self.assertEqual(r["stueck"], 249)                                  # 10.000 / 40,01
        self.assertAlmostEqual(r["kapital"], 249 * 40.01)
        self.assertAlmostEqual(r["hebel"], 240 / 40.01)                     # ~6x, aus dem Produkt
        self.assertAlmostEqual(r["endwert"], 249 * (64.0 - 0.02))           # Verkauf: innerer Wert - Spread
        self.assertFalse(r["ko_erreicht"])
        self.assertAlmostEqual(r["ko_abstand_pct"], 4000 / 24000 * 100)
        be = r["break_even"]                                                # Break-even: Erloes = Kapital
        self.assertAlmostEqual((be - 20000) * 0.01 - 0.02, r["kapital"] / 249, places=6)

    def test_knock_out_restwert(self):
        r = K.zertifikat(_produkt(ko_schwelle=21000), 10000, 24000, 20500)
        self.assertTrue(r["ko_erreicht"])
        self.assertEqual(r["endwert"], 0)
        self.assertAlmostEqual(r["rendite_pct"], -100)
        r2 = K.zertifikat(_produkt(ko_schwelle=21000, restwert=2.5), 10000, 24000, 20500)
        self.assertAlmostEqual(r2["endwert"], r2["stueck"] * 2.5)

    def test_short_und_finanzierung(self):
        p = _produkt(richtung="short", basispreis=28000, ko_schwelle=27500, geld=39.99, brief=40.01,
                     finanzierung_pct=3.65)
        r = K.zertifikat(p, 10000, 24000, 22000, tage=100)
        basis_t = 28000 * (1 - 0.0365 * 100 / 365)                          # Short: Basis faellt um 1 %
        self.assertAlmostEqual(r["basis_ziel"], basis_t)
        self.assertAlmostEqual(r["endwert"], r["stueck"] * ((basis_t - 22000) * 0.01 - 0.02))
        self.assertGreater(r["finanzierung_eur"], 0)
        self.assertTrue(K.zertifikat(p, 10000, 24000, 27400, tage=100)["ko_erreicht"])   # KO wandert mit

    def test_us_index_mit_wechselkurs(self):
        p = _produkt(basiswert="NDX", basispreis=20000, ko_schwelle=20000, geld=43.09, brief=43.11)
        r = K.zertifikat(p, 10000, 25000, 27500, eurusd_start=1.16, eurusd_ziel=1.16)
        self.assertAlmostEqual(r["hebel"], 25000 * 0.01 / 1.16 / 43.11)
        r_teurer = K.zertifikat(p, 10000, 25000, 27500, eurusd_start=1.16, eurusd_ziel=1.25)
        self.assertLess(r_teurer["endwert"], r["endwert"])                 # staerkerer Euro: Waehrungsverlust
        with self.assertRaises(ValueError):
            K.zertifikat(p, 10000, 25000, 27500)                           # ohne EUR/USD nicht rechenbar

    def test_plausibilitaet(self):
        f, _ = K.produkt_pruefen(_produkt(ko_schwelle=19000))
        self.assertTrue(any("Long" in x for x in f))
        f, _ = K.produkt_pruefen(_produkt(geld=41, brief=40))
        self.assertTrue(f)
        f, _ = K.produkt_pruefen(_produkt(), index_kurs=19900)
        self.assertTrue(any("ausgeknockt" in x for x in f))
        r = K.zertifikat(_produkt(bezug=0.1), 100000, 24000, 25000)        # falsches Bezugsverhaeltnis
        self.assertTrue(any("weicht deutlich" in w for w in r["warnungen"]))
        with self.assertRaises(ValueError):
            K.zertifikat(_produkt(brief=5000, geld=4999), 1000, 24000, 25000)  # Einsatz reicht nicht


class Auswertung(unittest.TestCase):
    def test_szenarien_warnung_achse_csv(self):
        sz = K.szenarien(lambda z: K.simulation(10000, 20000, z, 3, "long"), 20000)
        self.assertEqual([p for p, _ in sz], [-20, -10, -5, 5, 10, 20])
        self.assertAlmostEqual(dict(sz)[10]["gv"], 3000)
        self.assertEqual(K.ko_warnung(2.0)[0], "hoch")
        self.assertEqual(K.ko_warnung(5.0)[0], "mittel")
        self.assertIsNone(K.ko_warnung(20.0))
        x = K.diagramm_achse(20000, 22000, 15000)
        self.assertTrue(x[0] < 15000 and x[-1] > 22000 and len(x) == 121)
        r = K.simulation(10000, 20000, 22000, 3, "long")
        z = K.csv_zeilen({"Index": "DAX"}, r, K.hebel_vergleich(10000, 20000, 22000, "long"), sz)
        self.assertIn(("Ergebnis", "Gewinn/Verlust €", 3000.0), z)
        self.assertEqual(sum(1 for b, *_ in z if b == "Hebelvergleich"), 6)
        self.assertEqual(K.de(1234567.891), "1.234.567,89")


if __name__ == "__main__":
    unittest.main()
