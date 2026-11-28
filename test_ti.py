"""Tests Trading Intelligence Etappe 1: Daten, Technik (ohne Look-Ahead/Repainting), Pattern Matching, Score,
Backtest. Synthetische Kurse - kein Netz."""
import datetime
import math
import random
import unittest

import numpy as np

import ti_backtest as B
import ti_daten as TD
import ti_historie as H
import ti_score as S
import ti_technik as T

UTC = datetime.timezone.utc


def _kerzen(n=900, seed=1, start=datetime.date(2015, 1, 5), volumen=True, drift=0.0003):
    rnd = random.Random(seed)
    k, c, d = [], 100.0, start
    while len(k) < n:
        if d.weekday() < 5:
            r = drift + 0.015 * rnd.gauss(0, 1) + (0.06 * math.sin(len(k) / 37) / 37)
            o = c * (1 + 0.003 * rnd.gauss(0, 1))
            c2 = max(1.0, c * (1 + r))
            h = max(o, c2) * (1 + abs(0.006 * rnd.gauss(0, 1)))
            lo = min(o, c2) * (1 - abs(0.006 * rnd.gauss(0, 1)))
            v = (1e6 * (1 + abs(rnd.gauss(0, 0.5))) * (3 if abs(r) > 0.03 else 1)) if volumen else 0.0
            k.append([d.isoformat(), o, h, lo, c2, v])
            c = c2
        d += datetime.timedelta(days=1)
    return k


class Daten(unittest.TestCase):
    def _antwort(self, tage, letzte_ende):
        ts = [int(datetime.datetime(t.year, t.month, t.day, 14, 30, tzinfo=UTC).timestamp()) for t in tage]
        n = len(ts)
        return {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York", "instrumentType": "EQUITY",
                                               "currency": "USD", "currentTradingPeriod": {"regular": {"end": letzte_ende}}},
                                      "timestamp": ts,
                                      "indicators": {"quote": [{"open": [10] * n, "high": [11] * n, "low": [9] * n,
                                                                "close": [10] * (n - 1) + [None], "volume": [5] * n}],
                                                     "adjclose": [{"adjclose": [5] * n}]}}]}}

    def test_nur_abgeschlossene_bereinigte_kerzen(self):
        tage = [datetime.date(2026, 11, 23), datetime.date(2026, 11, 24), datetime.date(2026, 11, 25)]
        jetzt = datetime.datetime(2026, 11, 25, 17, 0, tzinfo=UTC)      # 12:00 New York: Handel laeuft
        ende = int(datetime.datetime(2026, 11, 25, 21, 0, tzinfo=UTC).timestamp())
        a = self._antwort(tage, ende)
        a["chart"]["result"][0]["indicators"]["quote"][0]["close"][-1] = 10
        e = TD.kerzen_parsen(a, jetzt)
        self.assertEqual([x[0] for x in e["kerzen"]], ["2026-11-23", "2026-11-24"])   # laufender Tag fehlt
        self.assertAlmostEqual(e["kerzen"][0][4], 5.0)                                # um Dividenden/Splits bereinigt
        self.assertAlmostEqual(e["kerzen"][0][2], 5.5)
        spaet = datetime.datetime(2026, 11, 25, 22, 0, tzinfo=UTC)
        self.assertEqual(len(TD.kerzen_parsen(a, spaet)["kerzen"]), 3)
        a["chart"]["result"][0]["indicators"]["quote"][0]["close"][-1] = None
        self.assertEqual(TD.kerzen_parsen(a, spaet)["verworfen"], 1)                  # unvollstaendige Kerze

    def test_symbolwahl_und_universum(self):
        t = [{"symbol": "X.SG", "quoteType": "MUTUALFUND", "exchange": "STU"},
             {"symbol": "X.L", "quoteType": "ETF", "exchange": "LSE"},
             {"symbol": "X.DE", "quoteType": "ETF", "exchange": "GER"}]
        self.assertEqual(TD.symbol_waehlen(t)["symbol"], "X.DE")
        self.assertIsNone(TD.symbol_waehlen([{"symbol": "Y", "quoteType": "OPTION"}]))
        isins = TD.isins_in({"a": [{"isin": "US67066G1040", "name": "NVIDIA"}, {"isin": "DE000LS9VSU1", "kategorie":
                                                                                  "Wikifolio"}]})
        cache = {"US67066G1040": {"symbol": "NVDA", "klasse": "aktie"}}
        uni, _ = TD.universum(isins, get=None, cache=cache)
        je = {u["id"]: u for u in uni}
        self.assertEqual(je["US67066G1040"]["symbol"], "NVDA")
        self.assertIn("Wikifolio", je["DE000LS9VSU1"]["grund"])
        self.assertIn("^GSPC", je)

    def test_pruefung_und_liquiditaet(self):
        k = _kerzen(300)
        jetzt = datetime.datetime.fromisoformat(k[-1][0] + "T23:00:00+00:00") + datetime.timedelta(days=10)
        p = TD.pruefen({"kerzen": k}, "aktie", jetzt)
        self.assertFalse(p["ok"])
        self.assertTrue(any("Tage alt" in g for g in p["gruende"]))
        self.assertTrue(TD.pruefen({"kerzen": k}, "aktie", jetzt - datetime.timedelta(days=9))["ok"])
        self.assertFalse(TD.pruefen({"kerzen": k[:100]}, "aktie", jetzt - datetime.timedelta(days=9))["ok"])
        self.assertTrue(TD.liquiditaet(k, "aktie")[0])
        self.assertFalse(TD.liquiditaet(_kerzen(300, volumen=False), "aktie")[0])
        self.assertTrue(TD.liquiditaet([], "devisen")[0])


class Technik(unittest.TestCase):
    def test_kein_repainting_und_kein_look_ahead(self):
        k = _kerzen(800, seed=3)
        voll = T.setups(T.indikatoren(k))
        for schnitt in (450, 600, 799):
            teil = T.setups(T.indikatoren(k[:schnitt]))
            for sid in T.LONG + T.SHORT:
                self.assertTrue(np.array_equal(teil[sid], voll[sid][:schnitt]), f"{sid} ändert sich bei {schnitt}")
        f_voll = H.merkmale(T.indikatoren(k))
        f_teil = H.merkmale(T.indikatoren(k[:600]))
        self.assertTrue(np.allclose(f_teil, f_voll[:600], equal_nan=True))

    def test_swings_erst_nach_bestaetigung(self):
        h = [1, 2, 3, 10, 3, 2, 1, 2]
        lo = [x - 0.5 for x in h]
        hochs, _ = T.swings(np.array(h, float), np.array(lo, float), k=3)
        self.assertEqual(hochs[0][:2], (3, 6))
        self.assertEqual(T.bekannt(hochs, 5), [])
        self.assertEqual(len(T.bekannt(hochs, 6)), 1)

    def test_indikatoren(self):
        c = np.array([1, 2, 3, 4, 5], float)
        self.assertTrue(np.isnan(T.sma(c, 3)[1]))
        self.assertEqual(T.sma(c, 3)[4], 4)
        self.assertEqual(T.rsi(np.arange(1, 30, dtype=float))[-1], 100.0)
        self.assertEqual(T.roll_mean(np.array([np.nan, 1, 3, 5]), 2)[-1], 4)

    def test_marken_long_short(self):
        ind = T.indikatoren(_kerzen(600, seed=5))
        i = ind["n"] - 1
        for r in ("long", "short"):
            m = T.marken(ind, i, r, [0.05, 0.1, 0.2])
            self.assertIsNotNone(m)
            if r == "long":
                self.assertLess(m["stop"], m["einstieg"])
                self.assertTrue(all(z > m["einstieg"] for z in m["ziele"]))
            else:
                self.assertGreater(m["stop"], m["einstieg"])
                self.assertTrue(all(z < m["einstieg"] for z in m["ziele"]))
            self.assertTrue(all(a < b for a, b in zip(m["crv"], m["crv"][1:])))
            self.assertLessEqual(len(m["ziele"]), 3)

    def test_kapitulation_erkannt(self):
        k = _kerzen(700, seed=7)
        c = k[-1][4]
        for j in range(15):                        # Ausverkauf
            c *= 0.965
            k.append([(datetime.date.fromisoformat(k[-1][0]) + datetime.timedelta(days=1)).isoformat(),
                      c * 1.01, c * 1.012, c * 0.99, c, 1.5e6])
        d = datetime.date.fromisoformat(k[-1][0]) + datetime.timedelta(days=1)
        k.append([d.isoformat(), c * 0.97, c * 1.0, c * 0.90, c * 0.99, 8e6])     # Kapitulationstag
        s = T.setups(T.indikatoren(k))
        self.assertEqual(s["L_kapitulation"][-1], 1)
        k.append([(d + datetime.timedelta(days=1)).isoformat(), c, c * 1.03, c * 0.99, c * 1.02, 3e6])
        self.assertEqual(T.setups(T.indikatoren(k))["L_kapitulation"][-1], 2)


class Historie(unittest.TestCase):
    def _pool(self):
        pool, inds = H.Pool(), {}
        for nr in range(3):
            ind = T.indikatoren(_kerzen(900, seed=10 + nr))
            f = H.merkmale(ind)
            pool.hinzufuegen(f"W{nr}", ind, f, H.ergebnisse(ind))
            inds[f"W{nr}"] = (ind, f)
        return pool, inds

    def test_nur_bekannte_ergebnisse(self):
        pool, inds = self._pool()
        ind, f = inds["W0"]
        i = 700
        tr = pool.abfragen(f[i], ind["datum"][i], horizonte=(20, 120))
        for hz in (20, 120):
            p = pool._bauen()
            ende = p[hz][3]
            tag = np.datetime64(ind["datum"][i])
            # jeder gewaehlte Fall hatte sein Ergebnis vor dem Abfragetag
            for wid, pos in zip(tr[hz]["id"], tr[hz]["pos"]):
                j = np.where((p["id"] == wid) & (p["pos"] == pos))[0][0]
                self.assertLess(ende[j], tag)
        frueh = pool.abfragen(f[230], ind["datum"][230], horizonte=(120,))
        self.assertIsNone(frueh[120])                                  # zu frueh: noch zu wenige bekannte Faelle

    def test_statistik_und_unsicherheit(self):
        pool, inds = self._pool()
        ind, f = inds["W1"]
        st = H.statistik(pool.abfragen(f[800], ind["datum"][800], horizonte=(20,)), "long", 0.002)[20]
        self.assertEqual(st["n"], H.K_NACHBARN)
        self.assertLessEqual(st["n_eff"], st["n"])
        if st["quote"] is not None:
            self.assertLessEqual(st["ki"][0], st["quote"])
            self.assertGreaterEqual(st["ki"][1], st["quote"])
        self.assertLessEqual(st["quantile"][10], st["quantile"][90])
        kurz = H.statistik(pool.abfragen(f[800], ind["datum"][800], horizonte=(20,)), "short", 0.002)[20]
        self.assertAlmostEqual(kurz["median"], -st["median"] - 0.004, places=6)
        self.assertEqual(H.effektiv(np.array(["a"] * 4), np.array([0, 5, 30, 31]), 20), 2)


class Score(unittest.TestCase):
    def _ind(self):
        return T.indikatoren(_kerzen(600, seed=2))

    def test_grenzen_klassen_und_widerspruch(self):
        ind = self._ind()
        i = ind["n"] - 1
        mk = {"crv_haupt": 3.5}
        hist = {20: {"quote": 0.8, "basis_quote": 0.55, "ki": (0.66, 0.9), "median": 0.05, "basis_median": 0.0,
                     "quantile": {25: -0.02, 75: 0.06}}}
        b = S.bewerten("long", [("L_spring", 2), ("L_divergenz", 2), ("L_kaufdruck", 2)], hist, mk, ind, i, True)
        self.assertTrue(0 <= b["score"] <= 100)
        self.assertEqual(b["bestaetigungen"], 3)
        self.assertTrue(b["hist_validiert"])
        self.assertEqual(S.klasse(96), "Außergewöhnliches Setup")
        self.assertEqual(S.klasse(59), "Kein relevantes Signal")
        schlecht = S.bewerten("long", [("L_spring", 2)], hist, mk, ind, i, True, daten_ok=False)
        self.assertLessEqual(schlecht["score"], 59)
        ohne = S.bewerten("long", [("L_spring", 2)], {20: None}, mk, ind, i, True)
        self.assertFalse(ohne["hist_validiert"])
        lb, sb = {"score": 70, "klasse": "", "gruende": []}, {"score": 65, "klasse": "", "gruende": []}
        S.widerspruch(lb, sb)
        self.assertEqual((lb["score"], sb["score"], lb["widerspruch"]), (55, 50, True))

    def test_alarm_mindestanforderungen(self):
        b = {"score": 90, "crv": 3.2, "bestaetigungen": 2, "hist_validiert": True}
        self.assertEqual(S.alarm_pruefen(b), (True, []))
        ok, fehlt = S.alarm_pruefen(dict(b, crv=2.0, hist_validiert=False), liquide=False)
        self.assertFalse(ok)
        self.assertEqual(len(fehlt), 3)


class Backtest(unittest.TestCase):
    def test_stop_zuerst_und_unvollstaendig(self):
        ind = {"o": np.array([10, 10, 10, 10.0]), "h": np.array([10, 10.6, 13, 10]), "l": np.array([10, 9.9, 8, 9]),
               "c": np.array([10, 10.2, 10, 10.0]), "n": 4}
        mk = {"richtung": "long", "trigger": 10.5, "stop": 9.5, "ziele": [11, 12]}
        sim = B.simulieren(ind, 0, mk, 0.0)
        self.assertEqual(sim["ausgang"], "Stop")                      # Tag 2: Stop und Ziel - Stop zaehlt
        self.assertAlmostEqual(sim["r"], -1.0)
        mk2 = dict(mk, trigger=20)
        self.assertIsNone(B.simulieren(ind, 0, mk2, 0.0))              # Trigger nie erreicht

    def test_lauf_und_bericht(self):
        werte = []
        for nr, sym in enumerate(("AAA", "BBB", "^GSPC")):
            u = {"id": sym, "symbol": sym, "name": sym, "klasse": "index" if sym.startswith("^") else "aktie"}
            werte.append({"u": u, "e": {"kerzen": _kerzen(1100, seed=20 + nr, start=datetime.date(2014, 1, 6)),
                                        "meta": {"waehrung": "USD"}}, "p": {"ok": True}})
        vb, pools = B.vorbereiten(werte)
        self.assertEqual(len(vb), 3)
        fl = B.faelle(vb, pools)
        self.assertTrue(fl)
        self.assertTrue(all(0 <= f["score"] <= 100 for f in fl))
        # Sperrfrist: je Wert und Richtung hoechstens ein Fall in 10 Tagen
        for sym in ("AAA", "BBB"):
            for r in ("long", "short"):
                d = sorted(datetime.date.fromisoformat(f["datum"]) for f in fl if f["symbol"] == sym and f["richtung"] == r)
                self.assertTrue(all((b - a).days >= 10 for a, b in zip(d, d[1:])))
        b = B.bericht(fl, "2017-06-01", B.basis(vb, "2017-06-01"))
        self.assertIn(b["validiert"]["long"], (True, False))
        md = B.markdown(b)
        self.assertIn("Ergebnis der Validierung", md)
        self.assertIn("jeder Tag (ohne Signal)", md)


if __name__ == "__main__":
    unittest.main()
