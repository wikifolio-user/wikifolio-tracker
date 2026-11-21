"""Tests fuer den Produktdaten-Abruf (produktdaten.py) - ohne Netz, mit Antworten im Format von onvista."""
import unittest

import ko_rechner as K
import produktdaten as PD

KO_SNAP = {
    "instrument": {"isin": "DE000MK487D6", "wkn": "MK487D", "name": "OPEN END TURBO LONG AUF NASDAQ 100",
                   "displayType": "Knock-Out-Optionsschein"},
    "quote": {"isoCurrency": "EUR"}, "bid": {"last": 57.85},
    "ask": {"last": 57.86, "datetimeLast": "2026-11-20T20:59:59.984+00:00"},
    "keywords": {"idExerciseRight": "C"}, "derivativesIssuer": {"name": "Morgan Stanley"},
    "derivativesDetails": {"shortName": "OPEN END TURBO LONG AUF NASDAQ 100", "codeExerciseRight": "C",
                           "nameSubcategory": "Knock-Out ohne Stop Loss", "quanto": False, "totalLossOnKnockout": True,
                           "hasBarrierBeenHit": False},
    "derivativesUnderlyingList": {"list": [{"instrument": {"isin": "US6311011026", "name": "NASDAQ 100"},
                                            "shortName": "NASDAQ 100", "coverRatio": 0.01,
                                            "derivativesBarrierList": {"list": [
                                                {"typeBarrier": "KNOCK_OUT", "barrier": 18746.1069},
                                                {"typeBarrier": "STRIKE", "barrier": 18746.1069}]}}]}}
ETP_SNAP = {
    "instrument": {"isin": "IE00BLRPRL42", "wkn": "A3GL7E", "name": "WisdomTree NASDAQ 100 3x Daily Leveraged ETC"},
    "quote": {"isoCurrency": "EUR"}, "bid": {"last": 221.76}, "ask": {"last": 224.96},
    "derivativesIssuer": {"name": "WisdomTree"},
    "derivativesDetails": {"officialName": "WisdomTree NASDAQ 100 3x Daily Leveraged", "participationRateWin": 3.0,
                           "managementFeePct": 0.75},
    "derivativesUnderlyingList": {"list": [{"shortName": "NASDAQ-100 3x Leveraged Index", "coverRatio": 1.0}]}}


class R:
    def __init__(self, code, d=None):
        self.status_code, self.d = code, d

    def json(self):
        if isinstance(self.d, Exception):
            raise self.d
        return self.d


def fake_get(antworten):
    def get(url, params=None, headers=None, timeout=None):
        for teil, antwort in antworten.items():
            if teil in url:
                return antwort
        return R(404)
    return get


SUCHE_KO = R(200, {"list": [{"isin": "DE000MK487D6", "wkn": "MK487D", "name": "OPEN END TURBO",
                             "entitySubType": "KNOCKOUT_CERTIFICATE"}]})
SUCHE_ETP = R(200, {"list": [{"isin": "IE00BLRPRL42", "wkn": "A3GL7E", "name": "WisdomTree 3x",
                              "entitySubType": "ETC_ETN_CERTIFICATE"}]})


class Produktdaten(unittest.TestCase):
    def test_ko_produkt_und_rechnung(self):
        get = fake_get({"instruments/query": SUCHE_KO, "ISIN:DE000MK487D6/snapshot": R(200, KO_SNAP)})
        p = PD.ko_produkt("mk487d", get)
        self.assertEqual((p["basiswert"], p["richtung"], p["basispreis"], p["ko_schwelle"], p["bezug"], p["geld"],
                          p["brief"], p["emittent"], p["restwert"], p["fehlt"]),
                         ("NDX", "long", 18746.1069, 18746.1069, 0.01, 57.85, 57.86, "Morgan Stanley", 0.0, []))
        e = K.zertifikat(dict(p, finanzierung_pct=0), 10000, 25028.98, 27500, eurusd_start=1.0975)
        self.assertAlmostEqual(e["hebel"], 25028.98 * 0.01 / 1.0975 / 57.86)      # ~3,9 wie bei onvista (3,95)
        self.assertEqual(e["warnungen"], [])                                         # innerer Wert passt zum Kurs

    def test_short_dax_quanto_und_fehlendes(self):
        snap = {**KO_SNAP, "derivativesDetails": {**KO_SNAP["derivativesDetails"], "codeExerciseRight": "P",
                                                  "quanto": True},
                "derivativesUnderlyingList": {"list": [{"instrument": {"isin": "DE0008469008"}, "coverRatio": 0.01,
                                                        "derivativesBarrierList": {"list": []}}]}}
        p = PD.ko_aus_snapshot(snap)
        self.assertEqual((p["basiswert"], p["richtung"], p["quanto"]), ("DAX", "short", True))
        self.assertIn("Basispreis", p["fehlt"])                                      # nie geraten
        self.assertEqual(K._fx({"basiswert": "NDX", "quanto": True}, 1.2), 1.0)     # Quanto: kein Waehrungseffekt

    def test_etp_produkt(self):
        get = fake_get({"instruments/query": SUCHE_ETP, "ISIN:IE00BLRPRL42/snapshot": R(200, ETP_SNAP)})
        p = PD.etp_produkt("A3GL7E", get)
        self.assertEqual((p["basiswert"], p["hebel"], p["kurs"], p["kosten"], p["waehrung"], p["fehlt"]),
                         ("NDX", 3.0, 224.96, 0.75, "EUR", []))
        self.assertAlmostEqual(p["spread"], round(3.2 / 224.96 * 100, 3))
        short = {**ETP_SNAP, "derivativesDetails": {"officialName": "WisdomTree NASDAQ 100 3x Daily Short",
                                                    "participationRateWin": 3.0}}
        self.assertEqual(PD.etp_aus_snapshot(short)["hebel"], -3.0)

    def test_fehler(self):
        with self.assertRaises(PD.ProduktFehler):
            PD.kennung_pruefen("12")
        self.assertEqual(PD.kennung_pruefen(" de000mk487d6 "), "DE000MK487D6")
        with self.assertRaisesRegex(PD.ProduktFehler, "kein Produkt"):
            PD.ko_produkt("MK487D", fake_get({"instruments/query": R(200, {"list": []})}))
        with self.assertRaisesRegex(PD.ProduktFehler, "kein Knock-out"):
            PD.ko_produkt("A3GL7E", fake_get({"instruments/query": SUCHE_ETP}))
        with self.assertRaisesRegex(PD.ProduktFehler, "Fehler 503"):
            PD.ko_produkt("MK487D", fake_get({"instruments/query": R(503)}))
        with self.assertRaisesRegex(PD.ProduktFehler, "nicht erreichbar"):
            PD.ko_produkt("MK487D", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        with self.assertRaisesRegex(PD.ProduktFehler, "unlesbar"):
            PD.ko_produkt("MK487D", fake_get({"instruments/query": R(200, ValueError())}))


if __name__ == "__main__":
    unittest.main()
