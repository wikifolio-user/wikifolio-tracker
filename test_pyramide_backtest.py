"""Tests Pyramidenmanager Etappe 3: Backtest A-D (pyramide_backtest.py) - vor allem: keine Vorausschau,
stimmige Buchfuehrung, Kosten, Knock-outs und Filter. Dazu ein Klicktest der Ansicht."""
import datetime
import random
import unittest

import pyramide as P
import pyramide_backtest as B

try:                                                  # Oberflaechentest nur mit echtem Streamlit (CI: test_ui_rauch)
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:
    OBERFLAECHE = False


def reihe(phasen, start=100.0, seed=7, beginn=datetime.date(2022, 1, 3)):
    """Synthetische Handelstag-Kerzen: phasen = [(tage, tagesrendite, schwankung)]; deterministisch."""
    rnd = random.Random(seed)
    aus, c, d = [], start, beginn
    for tage, mu, sigma in phasen:
        n = 0
        while n < tage:
            if d.weekday() < 5:
                o = c * (1 + rnd.gauss(0, sigma / 3))
                c = o * (1 + mu + rnd.gauss(0, sigma))
                h = max(o, c) * (1 + abs(rnd.gauss(0, sigma / 2)))
                lo = min(o, c) * (1 - abs(rnd.gauss(0, sigma / 2)))
                aus.append([d.isoformat(), o, h, lo, c])
                n += 1
            d += datetime.timedelta(days=1)
    return aus


AUF_AB = reihe([(320, 0.0008, 0.008), (220, 0.0012, 0.008), (40, -0.006, 0.015), (60, 0.0, 0.01),
                (200, 0.001, 0.008)])


class KeineVorausschau(unittest.TestCase):
    def test_spaetere_kerzen_aendern_nichts(self):
        """Ergebnis bis Tag X ist identisch, egal ob danach noch Kerzen folgen."""
        schnitt = 650
        bis = AUF_AB[schnitt][0]
        kurz = B.backtest(AUF_AB[:schnitt + 1], "NDX", strategien="ABCD")
        lang = B.backtest(AUF_AB, "NDX", bis=bis, strategien="ABCD")
        for s in "ABCD":
            self.assertEqual(kurz[s]["kurve"], lang[s]["kurve"], s)
            self.assertEqual(kurz[s]["liste"], lang[s]["liste"], s)

    def test_fg_perzentil_nur_vergangenheit(self):
        voll = B.fg_perzentile(AUF_AB)
        teil = B.fg_perzentile(AUF_AB[:600])
        for d, w in teil.items():
            self.assertEqual(voll[d], w, d)
        self.assertTrue(all(0 <= w <= 100 for w in voll.values()))

    def test_reihen_wie_rechenkern(self):
        r = B.reihen(AUF_AB, P.STANDARD, mit_fg=False)
        i = 500
        self.assertEqual(r["trend"][i]["score"], P.trend_score(AUF_AB[:i + 1])["score"])
        self.assertAlmostEqual(r["atr"][i], P.atr(AUF_AB[:i + 1], 20))
        self.assertIsNone(r["trend"][P.MIN_KERZEN - 2])


class Buchfuehrung(unittest.TestCase):
    def test_endwert_gleich_kapital_plus_ergebnisse(self):
        r = B.backtest(AUF_AB, "NDX", strategien="A")["A"]
        self.assertGreater(r["pyramiden"], 0)
        self.assertAlmostEqual(r["endwert"], 10000 + sum(p["ergebnis"] for p in r["liste"]), places=4)
        self.assertGreaterEqual(r["max_dd_pct"], -100)
        self.assertLessEqual(r["max_dd_pct"], 0)
        # Einstieg erst zur Eroeffnung NACH dem Signaltag
        erste = r["liste"][0]["start"]
        tag = [k[0] for k in AUF_AB].index(erste)
        r2 = B.reihen(AUF_AB, P.STANDARD, mit_fg=False)
        self.assertTrue(P.einstiegssignal(r2["trend"][tag - 1])[0])

    def test_kosten(self):
        ohne = B.backtest(AUF_AB, "NDX", parameter={"spread_pct": 0, "gebuehr": 0}, strategien="A")["A"]
        mit = B.backtest(AUF_AB, "NDX", parameter={"spread_pct": 0.5, "gebuehr": 5}, strategien="A")["A"]
        self.assertEqual(ohne["kosten"], 0)
        self.assertGreater(mit["kosten"], 0)
        self.assertLess(mit["endwert"], ohne["endwert"])

    def test_kaufen_und_halten(self):
        r = B.backtest(AUF_AB, "NDX", parameter={"spread_pct": 0, "gebuehr": 0}, strategien="A")
        h = r["halten"]
        von = [k[0] for k in AUF_AB].index(r["von"])
        self.assertAlmostEqual(h["endwert"], 10000 * AUF_AB[-1][4] / AUF_AB[von][1], places=6)

    def test_fehler(self):
        with self.assertRaises(ValueError):
            B.backtest(AUF_AB[:200], "NDX")
        with self.assertRaises(ValueError):
            B.backtest(AUF_AB, "NDX", von=AUF_AB[-5][0])
        with self.assertRaises(ValueError):
            B.backtest(AUF_AB, "NDX", parameter={"art": "short"})


class KnockOut(unittest.TestCase):
    def test_gap_unter_ko(self):
        k = reihe([(360, 0.0015, 0.006)], seed=3)
        d = datetime.date.fromisoformat(k[-1][0])
        c = k[-1][4]
        for n in range(30):                                 # Absturz mit Eroeffnungsluecke weit unter jedem KO
            d += datetime.timedelta(days=1 if d.weekday() < 4 else 3)
            o = c * (0.75 if n == 0 else 1.0)
            c = o * 0.999
            k.append([d.isoformat(), o, o * 1.002, c * 0.998, c])
        r = B.backtest(k, "NDX", parameter={"art": "ko", "hebel": 10.0}, strategien="A")["A"]
        self.assertGreater(r["ko_ereignisse"], 0)
        self.assertTrue(any(p["grund"] == "Knock-out" for p in r["liste"]))
        self.assertGreater(r["endwert"], 0)                 # Risiko je Tranche begrenzt -> kein Totalverlust
        direkt = B.backtest(k, "NDX", strategien="A")["A"]
        self.assertEqual(direkt["ko_ereignisse"], 0)


class Filter(unittest.TestCase):
    def test_ohne_fg_kein_kauf_bei_c(self):
        r = B.backtest(AUF_AB, "NDX", strategien="AC", r=dict(B.reihen(AUF_AB, P.STANDARD, mit_fg=False)))
        self.assertGreater(r["A"]["pyramiden"], 0)
        self.assertEqual(r["C"]["pyramiden"], 0)            # kein F&G-Wert -> kein stilles "neutral"
        self.assertEqual(r["C"]["blockiert"], r["C"]["signale"])

    def test_alle_strategien_laufen(self):
        r = B.backtest(AUF_AB, "DAX")
        for s in "ABCD":
            self.assertIn("rendite_pct", r[s])
            self.assertLessEqual(r[s]["blockiert"], r[s]["signale"])
        self.assertEqual(r["A"]["blockiert"], 0)
        self.assertGreater(r["fg_abdeckung_pct"], 0)


def _app():
    import streamlit as st
    import pyramide_ui
    import test_pyramide as T
    import test_pyramide_backtest as TB
    if "speicher" not in st.session_state:
        st.session_state["speicher"] = T.Speicher()
    sp = st.session_state["speicher"]
    o = {"stand": "2026-11-21", "indizes": {"^NDX": {"kerzen": TB.AUF_AB, "pruefung": {"fehlende": []}}}}
    pyramide_ui.seite({"ohlc": lambda: o, "sentiment": lambda: T.SENT, "indizes": lambda: {}, "lesen": sp.lesen,
                       "aktualisiere": sp.aktualisiere, "upfad": lambda b: "u/" + b, "speichern": True,
                       "get": None, "oeffnen": lambda z: None})


@unittest.skipUnless(OBERFLAECHE, "Streamlit nicht installiert - laeuft im CI-Schritt der Oberflaeche (test_ui_rauch)")
class BacktestOberflaeche(unittest.TestCase):
    def test_rechnen(self):
        at = AppTest.from_function(_app, default_timeout=180).run()
        self.assertFalse(at.exception)
        at.segmented_control(key="pyr_teil").set_value("Backtest A–D").run()
        self.assertFalse(at.exception)
        at.button(key="pyr_bt_btn").click().run()
        self.assertFalse(at.exception)
        self.assertGreaterEqual(len(at.dataframe), 1)
        at.segmented_control(key="pyr_bt_art").set_value("ko").run()
        at.button(key="pyr_bt_btn").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("KO-Zertifikate" in x.value for x in at.markdown))


if __name__ == "__main__":
    unittest.main()
