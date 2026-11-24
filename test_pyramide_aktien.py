"""Tests Pyramidenmanager Etappe 4: Aktien-Kerzen, Aktien-Trendscanner und Aktien-Pyramiden (pyramide_aktien.py,
pyramide.neue_pyramide(art="aktie")) - ohne Netz, mit nachgebauten Yahoo-Antworten."""
import datetime
import unittest

import pyramide as P
import pyramide_aktien as PA
import test_pyramide as T

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

UTC = datetime.timezone.utc
JETZT = datetime.datetime(2026, 11, 20, 23, 0, tzinfo=UTC)          # Freitag nach US-Handelsschluss


def antwort(kerzen, art="EQUITY", ende=None, tz="America/New_York", name="Beispiel AG"):
    ts = [int(datetime.datetime.fromisoformat(k[0] + "T15:30:00").replace(tzinfo=UTC).timestamp()) for k in kerzen]
    return {"chart": {"result": [{
        "meta": {"instrumentType": art, "exchangeTimezoneName": tz, "currency": "USD", "exchangeName": "NMS",
                 "longName": name, "currentTradingPeriod": {"regular": {"end": ende or 0}}},
        "timestamp": ts,
        "indicators": {"quote": [{"open": [k[1] for k in kerzen], "high": [k[2] for k in kerzen],
                                  "low": [k[3] for k in kerzen], "close": [k[4] for k in kerzen]}]}}]}}


class Antwort:
    def __init__(self, status, daten=None):
        self.status_code, self._d = status, daten

    def json(self):
        return self._d


class Kerzen(unittest.TestCase):
    def test_parsen(self):
        k = T.kerzen(300)
        k[5] = [k[5][0], 10, 9, 11, 10]                               # widerspruechlich -> verworfen
        d = PA.kerzen_parsen(antwort(k), JETZT)
        self.assertEqual(len(d["kerzen"]), 299)
        self.assertEqual(d["verworfen"], 1)
        self.assertEqual((d["waehrung"], d["name"]), ("USD", "Beispiel AG"))
        with self.assertRaises(PA.AbrufFehler):
            PA.kerzen_parsen(antwort(k, art="INDEX"), JETZT)
        with self.assertRaises(PA.AbrufFehler):
            PA.kerzen_parsen({"chart": {"result": []}}, JETZT)

    def test_laufender_handelstag_fehlt(self):
        k = T.kerzen(300)                                             # letzte Kerze 2026-11-20
        mittag = datetime.datetime(2026, 11, 20, 17, 0, tzinfo=UTC)
        ende = int(datetime.datetime(2026, 11, 20, 21, 0, tzinfo=UTC).timestamp())
        d = PA.kerzen_parsen(antwort(k, ende=ende), mittag)
        self.assertEqual(d["kerzen"][-1][0], k[-2][0])
        d = PA.kerzen_parsen(antwort(k, ende=ende), JETZT)
        self.assertEqual(d["kerzen"][-1][0], k[-1][0])

    def test_laden(self):
        k = T.kerzen(300)
        aufrufe = []

        def get(url, **kw):
            aufrufe.append(url)
            return Antwort(200, antwort(k))
        d = PA.kerzen_laden("aapl", get, JETZT)
        self.assertIn("/AAPL", aufrufe[0])
        self.assertEqual(len(d["kerzen"]), 300)
        with self.assertRaises(PA.AbrufFehler) as cm:
            PA.kerzen_laden("NOPE", lambda url, **kw: Antwort(404), JETZT)
        self.assertIn("nicht gefunden", str(cm.exception))
        with self.assertRaises(PA.AbrufFehler) as cm:
            PA.kerzen_laden("AAPL", lambda url, **kw: Antwort(500), JETZT)
        self.assertIn("500", str(cm.exception))
        with self.assertRaises(PA.AbrufFehler):
            PA.kerzen_laden("ZWEI WORTE", get, JETZT)

    def test_alter(self):
        self.assertEqual(PA.handelstage_alt("2026-11-19", JETZT), 0)   # bis gestern (Do) abgeschlossen
        self.assertEqual(PA.handelstage_alt("2026-11-13", JETZT), 4)   # Mo-Do
        self.assertIsNone(PA.handelstage_alt("kein datum", JETZT))


class Scanner(unittest.TestCase):
    def test_zeile_und_sortierung(self):
        auf = PA.analyse("AUF", "Aufwärts AG", {"kerzen": T.kerzen(320), "waehrung": "EUR"}, JETZT)
        ab = PA.analyse("AB", "Abwärts AG", {"kerzen": T.kerzen(320, schritt=-0.002)}, JETZT)
        alt = PA.analyse("ALT", "", {"kerzen": T.kerzen(320, ende=datetime.date(2026, 10, 1))}, JETZT)
        self.assertEqual(alt["status"], "veraltet")
        bew = ({"ticker": "AUF"}, {"gesamt": 72, "fazit": "solide"})
        z = [PA.scanner_zeile(x, bewertung=bew if x is auf else None,
                              investoren={"note": "B", "kaufen": 7, "inv": 12} if x is auf else None)
             for x in (ab, alt, auf)]
        z = PA.sortieren(z)
        self.assertEqual(z[0]["ticker"], "AUF")
        self.assertTrue(z[0]["signal"])
        self.assertEqual((z[0]["bewertung"], z[0]["fazit"], z[0]["investoren_kaufen"]), (72, "solide", "7/12"))
        zeile_alt = next(x for x in z if x["ticker"] == "ALT")
        self.assertFalse(zeile_alt["signal"])                         # veraltete Kerzen geben nie ein Signal
        self.assertIn("veraltet", zeile_alt["gruende"][0])
        s = PA.zusammenfassung(z)
        self.assertEqual((s["anzahl"], s["signale"], s["fehlt"]), (3, 1, 1))

    def test_liste(self):
        depot = [{"name": "Apple", "isin": "US0378331005"}, {"name": "Weltfonds", "isin": "LU000"},
                 {"name": "Apple doppelt", "wkn": "865985"}]
        zuordnung = {"US0378331005": ("AAPL", "Apple Inc."), "865985": ("AAPL", "Apple Inc.")}
        werte, ohne = PA.liste_zusammenstellen(
            depot, [{"ticker": "sap.de", "name": "SAP"}, {"ticker": "AAPL"}],
            lambda p: zuordnung.get(p.get("isin")) or zuordnung.get(p.get("wkn")))
        self.assertEqual([(w["ticker"], w["quelle"]) for w in werte], [("AAPL", "Depot"), ("SAP.DE", "eigene Liste")])
        self.assertEqual(ohne, ["Weltfonds"])


class AktienPyramide(unittest.TestCase):
    def test_anlegen_und_tranchen(self):
        p = P.neue_pyramide("x1", " sap.de ", "", 20000, "2026-11-20", art="aktie")
        self.assertEqual((p["index"], p["art"], p["name"]), ("SAP.DE", "aktie", "SAP.DE"))
        cfg = P.cfg_fuer(p)
        self.assertEqual((cfg["gewichte"], cfg["fg_modus"]), ({"trend": 100, "gap": 0, "fg": 0}, "aus"))
        ko = {"art": "ko", "stueck": 10, "kaufkurs": 5.0, "index_kauf": 180.0,
              "produkt": {"basiswert": "SAP.DE", "richtung": "long", "basispreis": 150, "ko_schwelle": 150,
                          "bezug": 0.1, "brief": 3.0}}
        with self.assertRaises(ValueError) as cm:
            P.tranche_hinzufuegen(p, ko, 4.0)
        self.assertIn("nur direkte", str(cm.exception))
        p2 = P.tranche_hinzufuegen(p, {"art": "direkt", "stueck": 10, "kaufkurs": 180.0, "index_kauf": 180.0,
                                       "datum": "2026-11-20"}, 4.0)
        self.assertAlmostEqual(p2["tranchen"][0]["anfangsstop"], 180 - 2 * 4.0)
        with self.assertRaises(ValueError):
            P.neue_pyramide("x2", "", "", 1000, "2026-11-20", art="aktie")

    def test_kombiniert_nur_trend(self):
        p = P.neue_pyramide("x1", "AUF", "", 20000, "2026-11-20", art="aktie")
        cfg = P.cfg_fuer(p)
        a = PA.analyse("AUF", "", {"kerzen": T.kerzen(320)}, JETZT, cfg)
        import pyramide_daten as D
        b = D.bewertung(a, cfg)
        self.assertEqual(b["kombiniert"]["wert"], a["trend"]["score"])   # ohne Gap/F&G kein "nicht berechenbar"
        self.assertEqual(b["gap"]["status"], "fehlt")
        self.assertEqual(b["fg"]["status"], "aus")


def _app():
    import datetime
    import json as _json
    import streamlit as st
    import pyramide_ui
    import test_pyramide as T
    import test_pyramide_aktien as TA
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
    sp = st.session_state["speicher"]
    o = T.ohlc()
    kerzen = T.kerzen(320, ende=datetime.date.today() - datetime.timedelta(days=1))

    def get(url, **kw):
        if "/chart/" in url:
            return TA.Antwort(200, TA.antwort(kerzen, name="Testaktie AG"))
        return TA.Antwort(404)
    pyramide_ui.seite({"ohlc": lambda: o, "sentiment": lambda: T.SENT, "indizes": lambda: {}, "lesen": sp.lesen,
                       "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b, "speichern": True,
                       "get": get, "oeffnen": lambda z: None,
                       "aktien_depot": lambda: [{"name": "Weltfonds", "isin": "LU000"}],
                       "bewertung_daten": lambda: None, "investoren": lambda: {}})
    st.markdown("SPEICHER:" + _json.dumps(sp.d.get("u/state/pyramiden.json") or {}))


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class AktienOberflaeche(unittest.TestCase):
    def _d(self, at):
        import json
        return json.loads([x.value for x in at.markdown if x.value.startswith("SPEICHER:")][-1][len("SPEICHER:"):])

    def test_scanner_anlegen_erfassen(self):
        at = AppTest.from_function(_app, default_timeout=120).run()
        self.assertFalse(at.exception)
        at.segmented_control(key="pyr_teil").set_value("Aktien-Trendscanner").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Weltfonds" in x.value for x in at.caption))   # nicht zuordenbarer Depotwert
        at.text_input(key="pyr_ak_neu_ticker").set_value("test").run()
        at.button(key="pyr_ak_neu_btn").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.dataframe), 1)
        self.assertEqual(at.session_state["speicher"].d["u/state/pyramiden_aktien.json"]["aktien"][0]["ticker"],
                         "TEST")
        # Aktien-Pyramide anlegen und eine Tranche erfassen
        at.segmented_control(key="pyr_teil").set_value("Meine Pyramiden").run()
        at.segmented_control(key="pyr_neu_basis").set_value("Aktie").run()
        at.text_input(key="pyr_neu_ticker").set_value("TEST").run()
        at.button(key="pyr_neu_btn").click().run()
        self.assertFalse(at.exception)
        p = self._d(at)["pyramiden"][0]
        self.assertEqual((p["index"], p["art"]), ("TEST", "aktie"))
        at.segmented_control(key="pyr_bereich").set_value("Nachkauf prüfen & erfassen").run()
        self.assertFalse(at.exception)
        at.number_input(key="pyr_stueck").set_value(10.0).run()
        at.number_input(key="pyr_kaufkurs_direkt").set_value(100.0).run()
        at.button(key="pyr_erfassen_btn").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self._d(at)["pyramiden"][0]["tranchen"][0]["art"], "direkt")
        for b in ("Überblick", "Einstellungen", "Zeitleiste"):
            at.segmented_control(key="pyr_bereich").set_value(b).run()
            self.assertFalse(at.exception, b)


if __name__ == "__main__":
    unittest.main()
