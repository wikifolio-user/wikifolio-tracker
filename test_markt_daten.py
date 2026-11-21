"""Tests fuer boersenkalender.py und markt_daten.py (Datenadapter) - ohne Netz."""
import datetime
import unittest
from zoneinfo import ZoneInfo

import boersenkalender as BK
import markt_daten as MD

NY = ZoneInfo("America/New_York")
BER = ZoneInfo("Europe/Berlin")


def _ts(d, tz, h=9, m=30):
    return int(datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=tz).timestamp())


def _yahoo(tage, tz, typ="INDEX", ohlc=None, h=9, m=30):
    ohlc = ohlc or [(100 + i, 102 + i, 99 + i, 101 + i) for i in range(len(tage))]
    return {"chart": {"result": [{"meta": {"instrumentType": typ}, "timestamp": [_ts(d, tz, h, m) for d in tage],
                                  "indicators": {"quote": [{"open": [x[0] for x in ohlc], "high": [x[1] for x in ohlc],
                                                            "low": [x[2] for x in ohlc],
                                                            "close": [x[3] for x in ohlc]}]}}]}}


class Kalender(unittest.TestCase):
    def test_feiertage_und_sonderschliessungen(self):
        self.assertEqual(BK.ostersonntag(2025), datetime.date(2025, 4, 20))
        self.assertFalse(BK.ist_handelstag("NYSE", datetime.date(2025, 1, 9)))        # Staatstrauer Carter
        self.assertFalse(BK.ist_handelstag("NYSE", datetime.date(2025, 6, 19)))       # Juneteenth
        self.assertTrue(BK.ist_handelstag("NYSE", datetime.date(2021, 6, 18)))        # vor 2022 kein Feiertag
        self.assertFalse(BK.ist_handelstag("XETRA", datetime.date(2025, 12, 24)))
        self.assertTrue(BK.ist_handelstag("NYSE", datetime.date(2025, 12, 24)))       # Halbtag = Handelstag
        self.assertFalse(BK.ist_handelstag("XETRA", datetime.date(2021, 5, 24)))     # Pfingstmontag (frueher frei)
        self.assertTrue(BK.ist_handelstag("XETRA", datetime.date(2025, 6, 9)))       # heute gehandelt
        self.assertEqual(len(BK.handelstage_zwischen("XETRA", datetime.date(2025, 12, 22),
                                                     datetime.date(2026, 1, 2))), 5)

    def test_kerze_vollstaendig(self):
        d = datetime.date(2026, 11, 20)
        self.assertFalse(BK.kerze_vollstaendig("NYSE", d, datetime.datetime(2026, 11, 20, 15, 0, tzinfo=NY)))
        self.assertTrue(BK.kerze_vollstaendig("NYSE", d, datetime.datetime(2026, 11, 20, 16, 5, tzinfo=NY)))
        self.assertTrue(BK.kerze_vollstaendig("XETRA", d, datetime.datetime(2026, 11, 21, 8, 0, tzinfo=BER)))


class Ohlc(unittest.TestCase):
    TAGE = [datetime.date(2026, 11, 16) + datetime.timedelta(days=i) for i in range(5)]    # Mo-Fr

    def test_parsen_nur_fertige_kerzen_und_index(self):
        jetzt = datetime.datetime(2026, 11, 20, 12, 0, tzinfo=NY)            # Freitag waehrend des Handels
        e = MD.ohlc_parsen(_yahoo(self.TAGE, NY), "^NDX", jetzt)
        self.assertEqual([k[0] for k in e["kerzen"]], [d.isoformat() for d in self.TAGE[:4]])
        self.assertEqual(e["kerzen"][0], ["2026-11-16", 100, 102, 99, 101])
        self.assertIsNone(MD.ohlc_parsen(_yahoo(self.TAGE, NY, typ="FUTURE"), "^NDX", jetzt))   # kein Future/CFD
        self.assertIsNone(MD.ohlc_parsen({"chart": {"result": []}}, "^NDX", jetzt))

    def test_ungueltige_kerzen_und_doppelte(self):
        jetzt = datetime.datetime(2026, 11, 23, 12, 0, tzinfo=NY)
        ohlc = [(100, 102, 99, 101), (None, 102, 99, 101), (100, 98, 99, 101), (100, 103, 99, 102), (0, 1, 0, 1)]
        e = MD.ohlc_parsen(_yahoo(self.TAGE, NY, ohlc=ohlc), "^NDX", jetzt)
        self.assertEqual(e["verworfen"], 3)                                  # None, Hoch < Schluss, 0
        self.assertEqual(len(e["kerzen"]), 2)
        doppelt = _yahoo(self.TAGE[:1] * 2, NY, ohlc=[(100, 102, 99, 101), (100, 103, 99, 102)])
        self.assertEqual(len(MD.ohlc_parsen(doppelt, "^NDX", jetzt)["kerzen"]), 1)  # ein Tag = eine Kerze

    def test_dax_boersenzeit(self):
        jetzt = datetime.datetime(2026, 11, 21, 8, 0, tzinfo=BER)
        e = MD.ohlc_parsen(_yahoo(self.TAGE, BER, h=9, m=0), "^GDAXI", jetzt)
        self.assertEqual(e["kerzen"][-1][0], "2026-11-20")
        self.assertEqual(e["boerse"], "XETRA")

    def test_pruefen_fehlende_tage(self):
        k = [[d.isoformat(), 1, 1, 1, 1] for d in (self.TAGE[0], self.TAGE[1], self.TAGE[3])]
        p = MD.pruefen(k, "NYSE")
        self.assertEqual(p["fehlende"], ["2026-11-18"])
        p = MD.pruefen([["2026-11-26", 1, 1, 1, 1]], "NYSE")                  # Thanksgiving
        self.assertEqual(p["unerwartet"], ["2026-11-26"])

    def test_abrufen_und_neue_datei(self):
        jetzt = datetime.datetime(2026, 11, 23, 12, 0, tzinfo=NY)

        class R:
            status_code = 200

            def __init__(self, d):
                self.d = d

            def json(self):
                return self.d
        e = MD.ohlc_abrufen("^NDX", lambda *a, **k: R(_yahoo(self.TAGE, NY)), jetzt)
        self.assertEqual((e["kurz"], e["instrument"], len(e["kerzen"]), e["pruefung"]["fehlende"]),
                         ("NDX", "INDEX", 5, []))
        neu = MD.neue_ohlc({}, {"^NDX": e}, "S1")
        self.assertIsNone(MD.neue_ohlc(neu, {"^NDX": e}, "S2"))               # unveraendert -> nicht schreiben
        neu2 = MD.neue_ohlc(neu, {"^GDAXI": dict(e, kurz="DAX")}, "S3")
        self.assertEqual(set(neu2["indizes"]), {"^NDX", "^GDAXI"})            # alter Eintrag bleibt
        self.assertIsNone(MD.ohlc_abrufen("^NDX", lambda *a, **k: (_ for _ in ()).throw(OSError()), jetzt))


class Sentiment(unittest.TestCase):
    def test_cnn(self):
        ms = lambda d: datetime.datetime(2026, 11, d, 20, tzinfo=datetime.timezone.utc).timestamp() * 1000
        a = {"fear_and_greed": {"score": 37.4, "rating": "fear", "timestamp": "2026-11-20T21:00:00+00:00",
                                "previous_close": 41.2, "previous_1_week": 55.0, "previous_1_month": 60,
                                "previous_1_year": 70},
             "fear_and_greed_historical": {"data": [{"x": ms(19), "y": 41.2}, {"x": ms(20), "y": 37.4},
                                                    {"x": ms(18), "y": 140}]}}
        r = MD.cnn_parsen(a)
        self.assertEqual((r["wert"], r["kategorie"], r["vortag"], r["vorwoche"]), (37.4, "fear", 41.2, 55.0))
        self.assertEqual(r["verlauf"], [["2026-11-19", 41.2], ["2026-11-20", 37.4]])   # 140 ungueltig
        self.assertIsNone(MD.cnn_parsen({"fear_and_greed": {"score": -3}}))
        self.assertIsNone(MD.cnn_parsen("<html>"))

    def test_crypto(self):
        t = lambda d: str(int(datetime.datetime(2026, 11, d, tzinfo=datetime.timezone.utc).timestamp()))
        a = {"data": [{"value": "22", "value_classification": "Extreme Fear", "timestamp": t(20)},
                      {"value": "30", "value_classification": "Fear", "timestamp": t(19)},
                      {"value": "50", "value_classification": "Neutral", "timestamp": t(13)}], "metadata": {"error": None}}
        r = MD.crypto_parsen(a)
        self.assertEqual((r["wert"], r["kategorie"], r["vortag"], r["vorwoche"]), (22, "Extreme Fear", 30, 50))
        self.assertEqual(r["verlauf"][0], ["2026-11-13", 50])
        self.assertIsNone(MD.crypto_parsen({"data": [], "metadata": {"error": "limit"}}))

    def test_lange_historie_mit_rueckfall(self):
        aufrufe = []

        class R:
            def __init__(self, code, d=None):
                self.status_code, self.d = code, d

            def json(self):
                return self.d

        def get(url, params=None, headers=None, timeout=None):
            aufrufe.append((url, (params or {}).get("limit")))
            if MD.CNN_START_LANG in url or (params or {}).get("limit") == 0:
                return R(400)                                                # lange Historie abgelehnt
            if "alternative" in url:
                return R(200, {"data": [{"value": "40", "value_classification": "Fear", "timestamp": "1763600000"}]})
            return R(200, {"fear_and_greed": {"score": 50, "rating": "neutral"}})
        r = MD.sentiment_abrufen(get, datetime.datetime(2026, 11, 21, tzinfo=datetime.timezone.utc))
        self.assertEqual((r["cnn"]["wert"], r["crypto"]["wert"]), (50, 40))  # Rueckfall auf 400 Tage
        self.assertEqual(len(aufrufe), 6)                                    # + CoinMarketCap aktuell und Verlauf
        self.assertIn(MD.CNN_START_LANG, aufrufe[0][0])

    def test_cnn_teile_und_cmc(self):
        a = {"fear_and_greed": {"score": 30, "rating": "fear"}, "put_call_options": {"score": 12.5, "rating": "extreme fear"},
             "junk_bond_demand": {"score": 150}, "unbekannt": {"score": 50}}
        r = MD.cnn_parsen(a)
        self.assertEqual(r["teile"], {"put_call_options": {"wert": 12.5, "kategorie": "extreme fear"}})   # 150 ungueltig
        latest = {"data": {"value": 8, "update_time": "2026-11-21T20:08:10.033Z", "value_classification": "Extreme fear"},
                  "status": {"error_code": "0"}}
        chart = {"data": {"dataList": [{"score": 20, "timestamp": "1763596800"}, {"score": 140, "timestamp": "1763683200"}]}}
        c = MD.cmc_parsen(latest, chart)
        self.assertEqual((c["wert"], c["kategorie"], c["vortag"], c["quelle"]), (8, "Extreme fear", 20, "CoinMarketCap"))
        self.assertEqual(c["verlauf"][-1], ["2026-11-21", 8])
        self.assertIsNone(MD.cmc_parsen({"status": {"error_code": "1002"}, "data": {}}))

    def test_neue_sentiment_behaelt_alte(self):
        alt = {"quellen": {"cnn": {"wert": 40, "ok": "S0"}, "crypto": {"wert": 20, "ok": "S0"}}}
        neu = MD.neue_sentiment(alt, {"cnn": {"wert": 45}, "crypto": None}, "S1")
        self.assertEqual(neu["quellen"]["cnn"], {"wert": 45, "ok": "S1"})
        self.assertEqual(neu["quellen"]["crypto"], {"wert": 20, "ok": "S0"})       # Ausfall: alter Wert bleibt


if __name__ == "__main__":
    unittest.main()
