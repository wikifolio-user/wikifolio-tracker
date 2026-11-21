"""Tests fuer den Fear & Greed Monitor (fear_greed.py) - ohne Netz, ohne Streamlit."""
import datetime
import math
import unittest

import fear_greed as F

UTC = datetime.timezone.utc
JETZT = datetime.datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def _kerzen(n=400, start=100.0, schritt=0.001, wellen=0.01, ende=datetime.date(2026, 11, 20)):
    """Kuenstliche Handelstage (nur fuer Tests): leichter Trend mit Schwankung."""
    tage, d = [], ende
    while len(tage) < n:
        if d.weekday() < 5:
            tage.append(d)
        d -= datetime.timedelta(days=1)
    tage.reverse()
    aus, k = [], start
    for i, t in enumerate(tage):
        k *= 1 + schritt + wellen * math.sin(i / 3)
        aus.append([t.isoformat(), k, k * 1.01, k * 0.99, k])
    return aus


class Klassifizierung(unittest.TestCase):
    def test_grenzen(self):
        self.assertEqual([F.kategorie(x)[0] for x in (0, 24.9, 25, 44.9, 45, 55, 55.9, 56, 75.9, 76, 100)],
                         ["Extreme Angst", "Extreme Angst", "Angst", "Angst", "Neutral", "Neutral", "Neutral", "Gier",
                          "Gier", "Extreme Gier", "Extreme Gier"])
        self.assertEqual(F.kategorie(None), (None, None))
        self.assertEqual(F.kategorie(101), (None, None))
        self.assertEqual((F.gruppe(10), F.gruppe(50), F.gruppe(80)), ("Angst", "Neutral", "Gier"))
        self.assertEqual(F.original_deutsch("extreme fear"), "Extreme Angst")


class EigenerScore(unittest.TestCase):
    def test_rsi(self):
        self.assertEqual(F.rsi([float(i) for i in range(1, 30)]), 100.0)
        self.assertLess(F.rsi([float(30 - i) for i in range(30)]), 1)
        self.assertIsNone(F.rsi([1.0, 2.0]))

    def test_score_aufwaerts_abwaerts_und_zu_wenig(self):
        auf = [k[4] for k in _kerzen(schritt=0.003, wellen=0.004)]
        ab = [k[4] for k in _kerzen(schritt=-0.003, wellen=0.004)]
        self.assertGreater(F.score(auf), 60)
        self.assertLess(F.score(ab), 40)
        self.assertIsNone(F.score(auf[:F.MIN_KERZEN - 1]))                 # zu wenige Daten -> kein Score
        self.assertEqual(sum(g for _, _, g, _ in F.FAKTOREN), 100)
        f = F.faktoren(auf)
        self.assertTrue(all(0 <= v <= 100 for v in f["teil"].values()))

    def test_verlauf_ganze_historie_und_vorberechnet(self):
        k = _kerzen(700)
        voll = F.score_verlauf(k)
        self.assertEqual(len(voll), 700 - F.MIN_KERZEN + 1)
        self.assertEqual(voll[-len(F.score_verlauf(k, tage=50)):], F.score_verlauf(k, tage=50))
        ohlc = {"indizes": {"^GDAXI": {"kerzen": k}}}
        e = F.eigene_verlaeufe(ohlc)
        self.assertEqual(e["^GDAXI"], voll)
        a = {x["id"]: x["wert"] for x in F.karten({}, ohlc, JETZT)}
        b = {x["id"]: x["wert"] for x in F.karten({}, ohlc, JETZT, eigene=e)}
        self.assertEqual(a, b)
        z = F.zeitraum(voll, 100 * 365)                                     # "Max"
        self.assertEqual((z["von"], len(z["punkte"])), (voll[0][0], len(voll)))

    def test_verlauf_nur_echte_tage(self):
        k = _kerzen(300)
        v = F.score_verlauf(k)
        self.assertEqual(len(v), 300 - F.MIN_KERZEN + 1)
        self.assertEqual(v[-1][0], k[-1][0])
        self.assertTrue({d for d, _ in v} <= {x[0] for x in k})


def _sentiment(ok="2026-11-21T08:00:00+00:00"):
    return {"quellen": {
        "cnn": {"wert": 22.0, "kategorie": "extreme fear", "vortag": 40.0, "vorwoche": 50.0, "ok": ok,
                "zeit": "2026-11-20T21:00:00+00:00", "verlauf": [["2026-11-19", 40.0], ["2026-11-20", 22.0]]},
        "crypto": {"wert": 80.0, "kategorie": "Extreme Greed", "vortag": 78.0, "ok": ok,
                   "zeit": "2026-11-21T00:00:00+00:00", "verlauf": [["2026-11-21", 80.0]]}}}


class Karten(unittest.TestCase):
    def setUp(self):
        self.ohlc = {"indizes": {"^GDAXI": {"kerzen": _kerzen()}, "^NDX": {"kerzen": _kerzen(schritt=-0.002)},
                                 "^GSPC": {"kerzen": _kerzen(100)}}}

    def test_sechs_karten_krypto_mit_zweitquelle(self):
        sent = _sentiment()
        sent["quellen"]["cmc"] = {"wert": 8.0, "kategorie": "Extreme fear", "ok": "2026-11-21T08:00:00+00:00",
                                  "zeit": "2026-11-21T08:00:00Z", "verlauf": [["2026-11-21", 8.0]]}
        sent["quellen"]["cnn"]["teile"] = {"put_call_options": {"wert": 20.0, "kategorie": "extreme fear"}}
        k = {x["id"]: x for x in F.karten(sent, self.ohlc, JETZT)}
        self.assertEqual(list(k), ["us", "krypto", "dax", "ndx", "spx", "dji"])          # kein Bitcoin/Ethereum mehr
        self.assertEqual((k["us"]["wert"], k["us"]["kategorie"], k["us"]["original"], k["us"]["aenderung"]),
                         (22.0, "Extreme Angst", "Extreme Angst", -18.0))
        self.assertEqual(k["us"]["teile"]["put_call_options"]["wert"], 20.0)
        self.assertEqual((k["krypto"]["zweit"]["wert"], k["krypto"]["zweit"]["kategorie"]), (8.0, "Extreme Angst"))
        self.assertIn("Eigener DAX 40-Sentiment-Score", k["dax"]["quelle"])
        self.assertIsNotNone(k["dax"]["faktoren"])
        self.assertIsNone(k["spx"]["wert"])                                   # 100 Kerzen: zu wenig
        self.assertIn("Zu wenige", k["spx"]["hinweis"])
        self.assertEqual(k["dji"]["status"], "fehlt")
        g = F.gesamt(list(k.values()))
        self.assertEqual(g["anzahl"], 4)                                       # CMC zaehlt nicht zusaetzlich

    def test_veraltet(self):
        k = {x["id"]: x for x in F.karten(_sentiment(ok="2026-11-18T08:00:00+00:00"), {}, JETZT)}
        self.assertEqual((k["us"]["status"], k["krypto"]["status"]), ("veraltet", "veraltet"))
        k2 = {x["id"]: x for x in F.karten(_sentiment(), self.ohlc, JETZT + datetime.timedelta(days=9))}
        self.assertEqual(k2["dax"]["status"], "veraltet")

    def test_gesamt_ohne_proxy_und_doppelte(self):
        kl = F.karten(_sentiment(), self.ohlc, JETZT)
        g = F.gesamt(kl)
        unab = [x for x in kl if x["art"] in ("extern", "eigen") and x["wert"] is not None]
        self.assertEqual(g["anzahl"], len(unab))
        self.assertEqual(g["angst"] + g["neutral"] + g["gier"], g["anzahl"])
        self.assertAlmostEqual(g["score"], round(sum(x["wert"] for x in unab) / len(unab), 1))
        self.assertIsNone(F.gesamt([])["score"])

    def test_zeitraum(self):
        v = [["2026-11-01", 30.0], ["2026-11-15", 70.0], ["2026-11-20", 50.0]]
        z = F.zeitraum(v, 7)
        self.assertEqual((z["aktuell"], z["hoch"], z["tief"], z["aenderung"]), (50.0, 70.0, 50.0, -20.0))
        self.assertEqual(len(F.zeitraum(v, 30)["punkte"]), 3)
        self.assertIsNone(F.zeitraum([], 7))


class EichungUndVola(unittest.TestCase):
    def test_eichung_monoton_und_naeher(self):
        roh = [[f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", 40 + i % 50] for i in range(200)]
        cnn = [[d, max(0, w - 25)] for d, w in roh]                          # CNN systematisch 25 tiefer
        e = F.eichung(roh, cnn)
        self.assertEqual(e["n"], 200)
        self.assertGreater(e["abstand_vor"], 20)
        self.assertLess(e["abstand_nach"], 2)
        werte = [F.geeicht(x, e) for x in range(0, 101, 5)]
        self.assertEqual(werte, sorted(werte))                               # Rangfolge bleibt erhalten
        self.assertEqual(F.anwenden([["a", 89]], None), [["a", 89]])          # ohne Eichung: Rohwert
        self.assertIsNone(F.eichung(roh[:10], cnn[:10]))                      # zu wenige gemeinsame Tage

    def test_volaindex_als_faktor_und_angstbarometer(self):
        k = _kerzen(300)
        ruhig = [[x[0], 0, 0, 0, 15.0] for x in k]
        panik = ruhig[:-1] + [[k[-1][0], 0, 0, 0, 40.0]]
        s_ruhig = F.score([x[4] for x in k][-F.MIN_KERZEN:], [x[4] for x in ruhig][-253:])
        s_panik = F.score([x[4] for x in k][-F.MIN_KERZEN:], [x[4] for x in panik][-253:])
        self.assertLess(s_panik, s_ruhig)                                     # hoher VIX = mehr Angst
        f = F.faktoren([x[4] for x in k], [x[4] for x in panik][-253:])
        self.assertEqual(f["vola_quelle"], "implizit")
        self.assertEqual(F.faktoren([x[4] for x in k])["vola_quelle"], "gemessen")   # DAX: ohne Index
        v = F.volatilitaet({"indizes": {"^VIX": {"kerzen": panik}}})
        self.assertEqual((v[0]["name"], v[0]["wert"]), ("VIX", 40.0))
        self.assertGreater(v[0]["perzentil"], 99)


class Warnungen(unittest.TestCase):
    def test_regeln_und_keine_doppelten(self):
        kl = F.karten(_sentiment(), {}, JETZT)
        w = F.warnungen(kl, F.STANDARD_REGELN)
        texte = " ".join(x["text"] for x in w)
        self.assertIn("US-Aktienmarkt fällt unter 25", texte)
        self.assertIn("Krypto (inkl. Bitcoin) steigt über 75", texte)
        self.assertIn("US-Aktienmarkt ändert sich um mehr als 15: aktuell -18,0 Punkte", texte)
        self.assertTrue(all(x["neu"] for x in w))
        gesehen = [x["schluessel"] for x in w]
        self.assertFalse(any(x["neu"] for x in F.warnungen(kl, F.STANDARD_REGELN, gesehen)))   # nicht doppelt
        aus = [dict(r, aktiv=False) for r in F.STANDARD_REGELN]
        self.assertEqual(F.warnungen(kl, aus), [])                             # abschaltbar


if __name__ == "__main__":
    unittest.main()
