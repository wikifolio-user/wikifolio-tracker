"""Tests Antizyklische Einstiege: Rechenkern (antizyklisch.py) und Oberflaeche (antizyklisch_ui.py)."""
import datetime
import unittest

import antizyklisch as A
import boersenkalender as BK

try:
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False

D = datetime.date


def _tage(boerse, start, n):
    aus, d = [], start
    while len(aus) < n:
        if BK.ist_handelstag(boerse, d):
            aus.append(d)
        d += datetime.timedelta(days=1)
    return aus


def _kerzen(tage, schluss):
    return [[d.isoformat(), c, c * 1.01, c * 0.99, c] for d, c in zip(tage, schluss)]


def _ohlc(je):
    return {"stand": "x", "indizes": {s: {"kerzen": k} for s, k in je.items()}}


def _sent(punkte):
    return {"stand": "x", "quellen": {"cnn": {"wert": punkte[-1][1] if punkte else None, "kategorie": "extreme fear",
                                              "verlauf": [[d.isoformat(), v] for d, v in punkte]}}}


class Sma(unittest.TestCase):
    def test_kreuzung_genau_am_tag(self):
        tage = _tage("NYSE", D(2024, 1, 2), 203)
        sc = [100.0] * 200 + [99.0, 98.0, 101.0]
        li = A.sma(sc)
        self.assertEqual(A.kreuzungen(sc, li), [200])         # Vortag 100 >= SMA 100, heute 99 < SMA
        s = A.sma_status([(d, c, c, c, c) for d, c in zip(tage[:201], sc[:201])])
        self.assertTrue(s["heute_unterschritten"])
        self.assertEqual(s["letzte_kreuzung_unter"], tage[200])
        s = A.sma_status([(d, c, c, c, c) for d, c in zip(tage[:202], sc[:202])])
        self.assertFalse(s["heute_unterschritten"])
        self.assertEqual((s["unter"], s["seit"], s["seit_kreuzung"]), (True, 2, True))
        s = A.sma_status([(d, c, c, c, c) for d, c in zip(tage, sc)])
        self.assertFalse(s["unter"])
        self.assertEqual(s["letzte_kreuzung_ueber"], tage[202])

    def test_zu_wenig_schlusskurse(self):
        tage = _tage("NYSE", D(2024, 1, 2), 150)
        s = A.sma_status([(d, 1, 1, 1, 1) for d in tage])
        self.assertEqual((s["ok"], s["vorhanden"], s["fehlend"]), (False, 150, 50))

    def test_nur_eine_signalphase_bei_seitwaertsbewegung(self):
        sc = [100.0] * 200 + [99, 101, 99, 101, 99] + [105] * 9 + [99] + [110] * 10 + [100]
        zeilen = [{"datum": D(2024, 1, 1) + datetime.timedelta(days=i), "c": c, "sma": s, "unter": s is not None and c < s}
                  for i, (c, s) in enumerate(zip(sc, A.sma(sc)))]
        ph = A.signalphasen(zeilen)
        # erst nach 10 Tagen in Folge ueber der Linie endet die Phase: das Wieder-Unterschreiten nach 9 Tagen
        # gehoert noch zur ersten Phase
        self.assertEqual(A.kreuzungen(sc, A.sma(sc)), [200, 202, 204, 214, 225])      # 5 Kreuzungen ...
        self.assertEqual(ph, [(200, 224), (225, 225)])                                # ... aber nur 2 Phasen
        self.assertEqual(A.einstiege(zeilen, ph, lambda z: z["unter"])[0], 200)
        self.assertEqual(len(A.einstiege(zeilen, ph[:1], lambda z: z["unter"])), 1)    # einmal je Phase


class FearGreed(unittest.TestCase):
    def test_wochenende_und_feiertag_unterbrechen_nicht(self):
        # 23.12.2025 (Di) bis 29.12.2025 (Mo): 25.12. Feiertag, 27./28. Wochenende
        tage = BK.handelstage_zwischen("NYSE", D(2025, 12, 22), D(2025, 12, 29))
        werte = [(D(2025, 12, 22), 40)] + [(d, 10) for d in tage[1:]] + [(D(2025, 12, 27), 50)]   # Sa-Wert ignorieren
        ft = A.fg_tage(sorted(werte))
        self.assertNotIn(D(2025, 12, 27), [d for d, _ in ft])
        lauf = A.laufende_dauer(ft, "ef")
        self.assertEqual(lauf[-1], (len(tage) - 1, False))
        ph = A.phasen(ft, "ef")
        self.assertEqual((ph[-1]["start"], ph[-1]["dauer"], ph[-1]["laufend"]), (D(2025, 12, 23), len(tage) - 1, True))

    def test_luecke_macht_beginn_unklar(self):
        tage = BK.handelstage_zwischen("NYSE", D(2026, 3, 2), D(2026, 3, 20))
        luecke = tage[5]
        werte = [(d, 10.0) for d in tage if d != luecke]
        ft = A.fg_tage(werte)
        self.assertIn((luecke, None), ft)
        lauf = A.laufende_dauer(ft, "ef")
        self.assertEqual(lauf[4], (5, True))                  # Beginn der Reihe unbekannt -> mindestens
        self.assertEqual(lauf[5], (0, False))
        self.assertEqual(lauf[-1], (len(tage) - 6, True))     # nach der Luecke: nur bekannte Tage, "mindestens"
        ph = A.phasen(ft, "ef")
        self.assertTrue(ph[0]["ende_unklar"])
        self.assertTrue(ph[1]["beginn_unklar"] and ph[1]["laufend"])
        st = A.fg_status(werte, tage[0])
        self.assertEqual(st["ef"]["anzahl_fertig"], 0)        # unklare Phasen zaehlen nicht in den Median

    def test_median_und_letzte_phase(self):
        tage = BK.handelstage_zwischen("NYSE", D(2026, 1, 5), D(2026, 2, 27))
        werte = [(d, 50.0) for d in tage]
        for a, b in ((2, 4), (10, 14), (20, 21)):                 # Phasen mit 3, 5, 2 Tagen
            for i in range(a, b + 1):
                werte[i] = (tage[i], 80.0)
        st = A.fg_status(werte, tage[0])
        self.assertIsNone(st["eg"]["laufend"])
        self.assertEqual(st["eg"]["letzte"]["dauer"], 2)
        self.assertEqual(st["eg"]["median"], 3)

    def test_platzhalter_der_quelle(self):
        tage = BK.handelstage_zwischen("NYSE", D(2020, 7, 15), D(2020, 9, 30))
        werte = [(d, 50.0) for d in tage[:30]] + [(d, 30.0 + i % 7) for i, d in enumerate(tage[30:])]
        self.assertEqual(A.belastbar_ab(werte), tage[30])
        self.assertEqual(A.belastbar_ab([(tage[0], 1.0), (tage[1], 2.0)]), tage[0])


class VixUndZuordnung(unittest.TestCase):
    def test_perzentil_nur_aus_vergangenheit(self):
        alt = A.PARAM["vix_fenster"]
        A.PARAM["vix_fenster"] = 5
        try:
            tage = _tage("NYSE", D(2024, 1, 2), 8)
            vk = [(d, v, v, v, v) for d, v in zip(tage, [10, 11, 12, 13, 14, 15, 9, 30])]
            r = A.vix_reihe(vk)
            self.assertIsNone(r[4]["perzentil"])
            self.assertEqual(r[5]["perzentil"], 100.0)            # 15 > alle 5 davor
            self.assertEqual(r[6]["perzentil"], 0.0)              # 9 < alle 5 davor (11..15)
            zukunft = A.vix_reihe(vk[:7] + [(tage[7], 1, 1, 1, 1)])
            self.assertEqual([x["perzentil"] for x in zukunft[:7]], [x["perzentil"] for x in r[:7]])
            self.assertEqual(r[5]["aend5"], 5)
            self.assertEqual(A.richtung(r[5]["aend5"]), "steigend")
            self.assertEqual(A.richtung(0), "fallend")
        finally:
            A.PARAM["vix_fenster"] = alt

    def _daten(self):
        us = _tage("NYSE", D(2026, 11, 2), 20)
        de = _tage("XETRA", D(2026, 11, 2), 20)
        ohlc = _ohlc({"^GSPC": _kerzen(us, [100 + i for i in range(20)]),
                      "^GDAXI": _kerzen(de, [200 + i for i in range(20)]),
                      "^VIX": _kerzen(us, [20 + i for i in range(20)])})
        sent = _sent([(d, 10.0 + i) for i, d in enumerate(us)])
        return us, de, ohlc, sent

    def test_zielindex_wechsel_und_us_tag(self):
        us, de, ohlc, sent = self._daten()
        t = A.tabelle("DAX", ohlc, sent)
        thx = D(2026, 11, 26)                                 # Thanksgiving: NYSE zu, Xetra offen
        self.assertIn(thx, de)
        z = next(z for z in t["zeilen"] if z["datum"] == thx)
        self.assertEqual(z["us_tag"], D(2026, 11, 25))
        self.assertEqual(z["fg"], 10.0 + us.index(D(2026, 11, 25)))
        t2 = A.tabelle("SPX", ohlc, sent)
        self.assertEqual([z["us_tag"] for z in t2["zeilen"]], us)
        self.assertEqual(t2["name"], "S&P 500")

    def test_einstieg_zur_naechsten_eroeffnung(self):
        zeilen = [{"datum": D(2024, 1, i + 1), "o": 10 + i, "h": 0, "l": 5 + i, "c": 10 + i} for i in range(6)]
        e = A.ergebnis(zeilen, 1, 3)
        self.assertEqual((e["einstieg"], e["einstieg_datum"]), (12, D(2024, 1, 3)))
        self.assertAlmostEqual(e["rendite"], 14 / 12 - 1)
        self.assertAlmostEqual(e["verlust"], 7 / 12 - 1)
        self.assertIsNone(A.ergebnis(zeilen, 3, 3))           # Nachbeobachtung unvollstaendig


class Statistik(unittest.TestCase):
    def test_wilson_und_ueberlappung(self):
        lo, hi = A.wilson(8, 10)
        self.assertTrue(0.49 < lo < 0.50 and 0.94 < hi < 0.95)
        self.assertEqual(A.effektiv([0, 5, 10, 25, 26, 60], 20), 3)
        self.assertEqual(A.wilson(0, 0), (None, None))

    def _a(self, werte):
        """werte: {(bid, teil): (n, quote, median)} fuer Horizont 20."""
        erg = {}
        for bid, _ in [("A", 0), ("B", 0)] + [(f"C{k}", 0) for k in A.PARAM["stufen"]]:
            for teil in ("gesamt", "lern", "test"):
                n, q, m = werte.get((bid, teil), (0, None, None))
                erg[(bid, 20, teil)] = {"n": n, "n_eff": n, "quote": q, "median": m, "verlust": -0.05,
                                        "ki": A.wilson((q or 0) * n, n)}
        return {"ok": True, "erg": erg, "bedingungen": [(b, "") for b in ["A", "B"] +
                                                         [f"C{k}" for k in A.PARAM["stufen"]]]}

    def test_einordnung_zustaende(self):
        basis = {("B", "lern"): (10, .5, .01), ("B", "test"): (4, .5, .01), ("B", "gesamt"): (14, .5, .01)}
        self.assertEqual(A.einordnung(self._a({("B", "lern"): (3, .5, .0)}), 20)["zustand"], "unklar")
        self.assertEqual(A.einordnung(self._a(basis), 20)["zustand"], "unklar")      # keine Stufe pruefbar
        kein = {**basis, ("C3", "lern"): (9, .55, .02), ("C3", "test"): (3, .6, .02)}
        self.assertEqual(A.einordnung(self._a(kein), 20)["zustand"], "kein_vorteil")
        auff = {**kein, ("C5", "lern"): (8, .75, .03), ("C5", "test"): (3, .67, .03),
                ("C10", "lern"): (8, .9, .05), ("C10", "test"): (3, 1.0, .05)}
        e = A.einordnung(self._a(auff), 20)
        self.assertEqual((e["zustand"], e["bid"]), ("auffaellig", "C5"))               # frueheste Stufe
        nicht_best = {**kein, ("C5", "lern"): (8, .75, .03), ("C5", "test"): (3, .33, .03)}
        e = A.einordnung(self._a(nicht_best), 20)
        self.assertEqual((e["zustand"], e["nur_lern"]), ("kein_vorteil", ["C5"]))


def _h_daten(n_index=700, mit_fg=True, code_kurz=False):
    us = _tage("NYSE", D(2023, 1, 3), n_index)
    de = _tage("XETRA", D(2023, 1, 3), n_index)
    import math
    kurve = [1000 + 200 * math.sin(i / 40) + i for i in range(n_index)]
    ohlc = _ohlc({"^GSPC": _kerzen(us, kurve), "^GDAXI": _kerzen(de, kurve if not code_kurz else kurve[:120]),
                  "^NDX": _kerzen(us, kurve), "^DJI": _kerzen(us, kurve),
                  "^VIX": _kerzen(us, [20 + 10 * math.cos(i / 30) for i in range(n_index)])})
    sent = _sent([(d, 50 + 45 * math.sin(i / 25)) for i, d in enumerate(us)] if mit_fg else [])
    return ohlc, sent


def _app():
    import streamlit as st
    import antizyklisch_ui
    import test_antizyklisch as T
    fall = st.session_state.get("_fall", "normal")
    ohlc, sent = T._h_daten(mit_fg=fall != "ohne_fg", code_kurz=fall == "kurz")
    if fall == "leer":
        ohlc = {}
    antizyklisch_ui.seite({"ohlc": lambda: ohlc, "sentiment": lambda: sent})


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class Oberflaeche(unittest.TestCase):
    def _text(self, at):
        return " ".join(x.value for x in at.markdown) + " ".join(x.value for x in at.caption)

    def test_uebersicht_horizont_und_indexwechsel(self):
        alt = A.PARAM["vix_fenster"]
        A.PARAM["vix_fenster"] = 100                         # kurze Testreihe: Perzentil frueher verfuegbar
        try:
            at = AppTest.from_function(_app, default_timeout=60).run()
            self.assertFalse(at.exception)
            t = self._text(at)
            for w in ("200-Tage-Linie", "Fear &amp; Greed", "VIX", "Handelstage"):
                self.assertIn(w, t)
            self.assertNotIn("US-Marktindikator", t)            # Standard S&P 500
            self.assertEqual(at.session_state["az_index"], "SPX")
            self.assertTrue(any(w in t for w in ("Historisch auffällig", "Kein historischer Vorteil", "Datenlage unklar")))
            at.segmented_control(key="az_h").set_value(120).run()
            self.assertIn("120 Handelstage", self._text(at))
            at.segmented_control(key="az_index").set_value("DAX").run()
            self.assertFalse(at.exception)
            t = self._text(at)
            self.assertIn("US-Marktindikator", t)
            self.assertIn("DAX 40", t)
            at.segmented_control(key="az_zr").set_value("Alles").run()
            self.assertFalse(at.exception)
        finally:
            A.PARAM["vix_fenster"] = alt

    def test_fehlende_daten(self):
        at = AppTest.from_function(_app, default_timeout=60)
        at.session_state["_fall"] = "ohne_fg"
        at.run()
        self.assertFalse(at.exception)
        t = self._text(at)
        self.assertIn("Keine Daten", t)
        self.assertIn("Datenlage unklar", t)
        at.session_state["_fall"] = "kurz"
        at.segmented_control(key="az_index").set_value("DAX").run()
        self.assertFalse(at.exception)
        self.assertIn("es fehlen", self._text(at))
        at.session_state["_fall"] = "leer"
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any("keine Tageskerzen" in w.value for w in at.warning))


if __name__ == "__main__":
    unittest.main()
