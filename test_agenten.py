"""Tests fuer die Batch-Agenten (python3 -m unittest test_agenten).

Ohne Netz: Yahoo und die GitHub-Contents-API sind gemockt (In-Memory-Speicher
mit derselben Semantik wie github_store). Sollwerte werden unabhaengig von den
Agenten-Funktionen gerechnet (eigene DCF-/CAGR-/Drawdown-Formeln).
"""
import copy
import datetime
import json
import logging
import math
import threading
import unittest
import zlib
from unittest import mock

import github_store as G
import top50_agent as T
import qualitaet_agent as Q

logging.getLogger().setLevel(logging.CRITICAL)
for _name in ("top50", "qualitaet"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)
T.log.setLevel(logging.CRITICAL)

d = datetime.date


# ---------------------------------------------------------------------------
# Unabhaengige Referenzen
# ---------------------------------------------------------------------------
def dcf_ref(f0, g1, r, n=10, ge=0.025, abflachend=False):
    """10-Jahres-DCF mit ewiger Rente, Wachstum ab Jahr 6 linear auf ge."""
    pv, f = 0.0, f0
    for t in range(1, n + 1):
        g = g1 + (ge - g1) * (t - 5) / 5 if (abflachend and t > 5) else g1
        f *= 1 + g
        pv += f / (1 + r) ** t
    return pv + f * (1 + ge) / (r - ge) / (1 + r) ** n


def max_drawdown_ref(kurse):
    hoch, dd = kurse[0], 0.0
    for p in kurse:
        hoch = max(hoch, p)
        dd = min(dd, p / hoch - 1)
    return dd * 100


def jahre_roh(fcfs, revs=None, ic=None, ebit=None, sh=None, eps=True, start=2020, extra=None):
    out = {}
    for i, f in enumerate(fcfs):
        rev = revs[i] if revs else 1000.0 + 100 * i
        j = {"TotalRevenue": rev, "EBIT": ebit[i] if ebit else 200.0, "FreeCashFlow": f,
             "DilutedAverageShares": sh[i] if sh else 100.0, "OrdinarySharesNumber": sh[i] if sh else 100.0,
             "NetIncome": 0.15 * rev, "TotalDebt": 300.0, "CashAndCashEquivalents": 100.0,
             "StockholdersEquity": 800.0, "EBITDA": 260.0, "GrossProfit": 0.5 * rev, "TaxRateForCalcs": 0.21}
        if eps:
            j["DilutedEPS"] = 0.0015 * rev
        if ic is not None and ic[i] is not None:
            j["InvestedCapital"] = ic[i]
        if extra:
            j.update(extra)
        out[f"{start + i}-12-31"] = j
    return out


class FakeStore:
    """In-Memory-Ersatz fuer github_store (gleiche Signaturen/Semantik)."""

    def __init__(self):
        self.dateien, self.writes = {}, []
        self.lese_fehler, self.put_fehler = set(), set()
        self.lock = threading.Lock()

    def lese_json(self, repo, branch, path, token, default=None):
        if path in self.lese_fehler:
            raise G.LeseFehler(f"{path}: HTTP 503")
        with self.lock:
            return copy.deepcopy(self.dateien.get(path, default)), "sha"

    def get_json(self, repo, branch, path, token, default=None):
        try:
            return self.lese_json(repo, branch, path, token, default)
        except G.LeseFehler:
            return default, None

    def put_json(self, repo, branch, path, obj, token, message="", max_retries=3, sha=None):
        with self.lock:
            self.writes.append(path)
            if path in self.put_fehler:
                return False
            self.dateien[path] = copy.deepcopy(obj)
            return True


class Basis(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        patches = [
            mock.patch.multiple(G, lese_json=self.store.lese_json, get_json=self.store.get_json,
                                put_json=self.store.put_json),
            mock.patch.object(T, "GITHUB_REPO", "owner/repo"),
            mock.patch.object(T, "GITHUB_TOKEN", "tok"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        T._lesefehler.clear()
        self._fx_reset()
        T._fx_cache["USD"] = ([d(2015, 1, 1)], [1.0])
        T.ZAEHLER["yahoo_429_folge"] = 0
        self.addCleanup(self._fx_reset)
        p = mock.patch.object(T, "_yahoo_session", side_effect=AssertionError("kein Netz im Test"))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(T._lesefehler.clear)

    @staticmethod
    def _fx_reset():
        T._fx_cache.clear()
        T._fx_fehl.clear()
        T._fx_ersatz.clear()
        T._fx_stand.update({"geladen": False, "ok": False, "daten": {}})

    @staticmethod
    def mk(jahre, wochen=(), wae="USD"):
        k = Q.kennzahlen("X", jahre, wae, list(wochen), wae)
        k.update(kurs_wae=wae, kurs_fb=20.0, kh=[], name_y="X")
        return k


STAMM = {"name": "Test AG", "branche": "Software", "land": "US"}


# ---------------------------------------------------------------------------
# AGT-01: technische Yahoo-Fehler loeschen keinen Cache-Eintrag
# ---------------------------------------------------------------------------
class TestAGT01Cache(Basis):
    def _yahoo(self, status):
        def fake(*a, **k):
            T._status(status)
            return None
        return fake

    def test_aktualisiere_unterscheidet_fehler_und_fehlt(self):
        with mock.patch.object(T, "yahoo_json", self._yahoo("fehler")):
            self.assertEqual(Q.aktualisiere("AAA")[2], "fehler")
        with mock.patch.object(T, "yahoo_json", self._yahoo("nicht_gefunden")):
            self.assertEqual(Q.aktualisiere("AAA")[2], "fehlt")

    def test_uebernehme(self):
        heute = d(2026, 10, 12)
        alt = {"stand": "2026-10-04", "k": {"x": 1}}
        cache = {"A": dict(alt)}
        Q.uebernehme(cache, "A", None, "Abruf fehlgeschlagen", "fehler", heute)
        self.assertEqual(cache["A"]["k"], {"x": 1})
        self.assertEqual(cache["A"]["stand"], "2026-10-04")       # bleibt faellig
        Q.uebernehme(cache, "A", None, "keine Abschlussdaten", "fehlt", heute)
        self.assertEqual(cache["A"]["k"], {"x": 1})                # < 30 Tage: behalten
        cache = {"A": {"stand": "2026-08-01", "k": {"x": 1}}}
        Q.uebernehme(cache, "A", None, "keine Abschlussdaten", "fehlt", heute)
        self.assertNotIn("k", cache["A"])                          # alt + inhaltlich leer: weg

    def test_ganzer_lauf_mit_yahoo_ausfall(self):
        heute = datetime.datetime.now(Q.ZoneInfo("Europe/Berlin")).date()
        k = Q.kennzahlen("AAA", jahre_roh([100, 110, 120, 130, 140]), "USD", [], "USD")
        k.update(kurs_wae="USD", kurs_fb=20.0, kh=[], name_y="A")
        stand = (heute - datetime.timedelta(days=8)).isoformat()
        self.store.dateien[Q.STATE_CACHE.format(Q.teil("AAA"))] = {"AAA": {"stand": stand, "k": k}}
        with mock.patch.object(Q, "universum", lambda h: ({"AAA": dict(STAMM)}, {"aktien": ["AAA"]}, {})), \
                mock.patch.object(T, "yahoo_json", self._yahoo("fehler")), \
                mock.patch.object(T, "index_mitgliedschaften", lambda *a, **kw: {}):
            Q.main()
        eintrag = self.store.dateien[Q.STATE_CACHE.format(Q.teil("AAA"))]["AAA"]
        self.assertEqual(eintrag["k"], k)
        self.assertEqual(eintrag["stand"], stand)
        erg = self.store.dateien[Q.STATE_ERGEBNIS]
        self.assertIn("AAA", erg["werte"])                         # weiterhin bewertet


# ---------------------------------------------------------------------------
# AGT-02: Zeitbudget + Zwischenspeichern
# ---------------------------------------------------------------------------
class TestAGT02Zeitbudget(Basis):
    def test_budget_stoppt_neue_abrufe_und_speichert_teile(self):
        uhr = {"t": 0.0}
        lock = threading.Lock()
        gestartet_bei = []
        heute = d(2026, 10, 12)
        symbole = [f"S{i:04d}" for i in range(200)]
        cache = {s: {"stand": "2026-09-01", "k": {"alt": s}} for s in symbole}
        k_neu = {"neu": True}

        def fake_aktualisiere(s):
            with lock:
                gestartet_bei.append(uhr["t"])
                uhr["t"] += 10.0                  # jeder Abruf kostet 10 s
            if int(s[1:]) % 10 == 0:              # 10 % technische Fehler (429/5xx)
                return None, "Abruf fehlgeschlagen", "fehler"
            return dict(k_neu), "", "ok"

        with mock.patch.object(Q, "aktualisiere", fake_aktualisiere), \
                mock.patch.object(Q, "_uhr", lambda: uhr["t"]), \
                mock.patch.object(Q, "ZEITBUDGET_ABRUF_SEK", 500.0), \
                mock.patch.object(Q, "SPEICHERN_NACH", 15):
            z = Q.abrufen_und_speichern(symbole, cache, {s: {} for s in symbole}, heute, 0.0)

        self.assertEqual(z["abbruch"], "Zeitbudget")
        gestartet = len(gestartet_bei)
        # Budget 500 s / 10 s = 50 Abrufe; hoechstens die parallel laufenden kommen dazu
        self.assertLessEqual(gestartet, 50 + T.YAHOO_PARALLEL)
        self.assertGreaterEqual(gestartet, 50)
        self.assertEqual(z["offen"], len(symbole) - gestartet)
        self.assertGreaterEqual(z["zwischenspeicher"], 2)
        self.assertEqual(z["ok"] + z["fehler"], gestartet)
        # Alles Abgerufene liegt gespeichert vor; Fehler behalten den alten Eintrag
        gespeichert = {}
        for i in range(Q.CACHE_TEILE):
            gespeichert.update(self.store.dateien.get(Q.STATE_CACHE.format(i), {}))
        for s in symbole[:gestartet]:
            erwartet = {"alt": s} if int(s[1:]) % 10 == 0 else k_neu
            self.assertEqual(gespeichert[s]["k"], erwartet, s)
        for s in symbole[gestartet:]:                  # nie gestartet -> unveraendert, nicht geschrieben
            self.assertEqual(cache[s]["k"], {"alt": s})

    def test_fehlgeschlagener_zwischenstand_wird_nachgeholt(self):
        heute = d(2026, 10, 12)
        symbole = [f"S{i:04d}" for i in range(12)]
        pfad = Q.STATE_CACHE.format(Q.teil(symbole[0]))
        self.store.put_fehler.add(pfad)
        aufrufe = {"n": 0}

        def fake_aktualisiere(s):
            aufrufe["n"] += 1
            if aufrufe["n"] == 8:
                self.store.put_fehler.discard(pfad)     # GitHub wieder erreichbar
            return {"neu": s}, "", "ok"

        with mock.patch.object(Q, "aktualisiere", fake_aktualisiere), \
                mock.patch.object(T, "YAHOO_PARALLEL", 1), \
                mock.patch.object(Q, "SPEICHERN_NACH", 4):
            z = Q.abrufen_und_speichern(symbole, {}, {s: {} for s in symbole}, heute, Q._uhr())
        self.assertEqual(z["nicht_gespeichert"], [])
        self.assertEqual(self.store.dateien[pfad][symbole[0]]["k"], {"neu": symbole[0]})


# ---------------------------------------------------------------------------
# AGT-03 Drawdown, AGT-04 ROIC, AGT-09 FCF-Vorzeichen, AGT-12 CAGR, AGT-14 Splits
# ---------------------------------------------------------------------------
class TestKennzahlen(Basis):
    def wochen(self, kurse):
        start = d(2021, 10, 1)
        return [(start + datetime.timedelta(weeks=i), p) for i, p in enumerate(kurse)]

    def test_agt03_drawdown(self):
        steigend = [10 + 90 * i / 259 for i in range(260)]
        k = Q.kennzahlen("X", jahre_roh([100, 110, 120, 130, 140]), "USD", self.wochen(steigend), "USD")
        self.assertEqual(k["dd"], 0.0)
        v = [100 - 50 * i / 129 for i in range(130)] + [50 + 50 * i / 129 for i in range(130)]
        k = Q.kennzahlen("X", jahre_roh([100, 110, 120, 130, 140]), "USD", self.wochen(v), "USD")
        self.assertEqual(k["dd"], -50.0)
        # Hoch am Anfang der 260er-Reihe (vor den letzten 156 Wochen) zaehlt mit
        frueh = [200.0] * 52 + [100.0] * 208
        k = Q.kennzahlen("X", jahre_roh([100, 110, 120, 130, 140]), "USD", self.wochen(frueh), "USD")
        self.assertEqual(k["dd"], round(max_drawdown_ref(frueh), 1))
        self.assertEqual(k["dd"], -50.0)

    def test_agt04_roic_vorzeichenwechsel(self):
        k = Q.kennzahlen("X", jahre_roh([100] * 5, ic=[500, 500, 500, 120, -100]), "USD", [], "USD")
        nopat = 200 * (1 - 0.21)
        ref = [nopat / 500 * 100] * 3 + [nopat / ((500 + 120) / 2) * 100]
        self.assertIsNone(k["roic"])                               # letztes Jahr nicht auswertbar
        self.assertEqual(k["roic_avg"], round(sum(ref) / 4, 1))     # 36.4

    def test_agt04_roic_begrenzt_und_einheitlich(self):
        k = Q.kennzahlen("X", jahre_roh([100] * 5, ic=[10] * 5), "USD", [], "USD")
        self.assertEqual(k["roic"], 100.0)                          # 1580 % -> Kappung
        # InvestedCapital nur in manchen Jahren -> ueberall Eigenkapital + Schulden
        k = Q.kennzahlen("X", jahre_roh([100] * 5, ic=[None, None, 50, 50, 50]), "USD", [], "USD")
        self.assertEqual(k["roic"], round(200 * 0.79 / 1100 * 100, 1))
        self.assertEqual(k["roic_trend"], 0.0)

    def test_agt09_fcf_positiv_zu_negativ(self):
        k = self.mk(jahre_roh([100, 90, 80, 60, -50]))
        self.assertIsNone(k["g_fcfps"])
        self.assertTrue(k["fcf_dreht"])
        e = Q.bewerte("X", k, {"regularMarketPrice": 20, "sharesOutstanding": 100}, None, STAMM)
        self.assertIn("FCF je Aktie von positiv auf negativ gedreht", [f[0] for f in e["flags"]])
        k2 = self.mk(jahre_roh([100, 90, 80, 60, 40]))
        self.assertFalse(k2["fcf_dreht"])
        self.assertEqual(k2["g_fcfps"], round(((40 / 100) ** (1 / 4) - 1) * 100, 1))

    def test_agt12_cagr_aus_datumsdifferenz(self):
        j = jahre_roh([100, 110, 120, 130])
        j = {("2019-12-31" if kk == "2020-12-31" else kk): v for kk, v in j.items()}
        j["2019-12-31"]["TotalRevenue"] = 1000
        j["2023-12-31"]["TotalRevenue"] = 2000
        k = Q.kennzahlen("X", j, "USD", [], "USD")
        jahre = (d(2023, 12, 31) - d(2019, 12, 31)).days / 365.25
        self.assertEqual(k["g_ums"], round((2 ** (1 / jahre) - 1) * 100, 1))   # 18.9, nicht 26.0

    def test_agt14_split_mit_chart_ereignis(self):
        sh = [100, 100, 400, 400, 400]
        revs = [1000, 1100, 2400, 2600, 2800]          # Umsatz springt mit -> Heuristik allein versagt
        ohne = Q.kennzahlen("X", jahre_roh([100] * 5, revs=revs, sh=sh), "USD", [], "USD")
        self.assertGreater(ohne["g_akt"], 30)          # ohne Split-Info: Verwaesserung
        mit = Q.kennzahlen("X", jahre_roh([100] * 5, revs=revs, sh=sh), "USD", [], "USD",
                           splits=[(d(2022, 6, 1), 4.0)])
        self.assertEqual(mit["g_akt"], 0.0)
        self.assertTrue(mit["akt_sprung"])

    def test_agt14_split_rest_bleibt_verwaesserung(self):
        sh = [100, 100, 440, 440, 440]                 # 4:1-Split + 10 % neue Aktien
        k = Q.kennzahlen("X", jahre_roh([100] * 5, sh=sh), "USD", [], "USD", splits=[(d(2022, 3, 1), 4.0)])
        jahre = (d(2024, 12, 31) - d(2020, 12, 31)).days / 365.25
        self.assertEqual(k["g_akt"], round((1.1 ** (1 / jahre) - 1) * 100, 2))

    def test_agt14_sprung_ohne_umsatz_keine_verwaesserung(self):
        k = Q.kennzahlen("X", jahre_roh([100] * 5, sh=[100, 100, 300, 300, 300]), "USD", [], "USD")
        self.assertEqual(k["g_akt"], 0.0)
        # echte Verwaesserung (Fusion: Umsatz verdoppelt sich mit), kein Split-Ereignis
        k = Q.kennzahlen("X", jahre_roh([100] * 5, revs=[1000, 1000, 2000, 2000, 2000],
                                        sh=[100, 100, 200, 200, 200]), "USD", [], "USD", splits=[])
        jahre = (d(2024, 12, 31) - d(2020, 12, 31)).days / 365.25
        self.assertEqual(k["g_akt"], round((2 ** (1 / jahre) - 1) * 100, 2))

    def test_agt14_chart_liefert_splits(self):
        ts = 1656633600                                  # 2022-07-01 00:00 UTC
        antwort = {"chart": {"result": [{"meta": {"currency": "USD", "gmtoffset": 0},
                                         "timestamp": [ts], "indicators": {"quote": [{"close": [10.0]}]},
                                         "events": {"splits": {str(ts): {"date": ts, "numerator": 4,
                                                                         "denominator": 1}}}}]}}
        with mock.patch.object(T, "yahoo_json", lambda *a, **k: antwort):
            c = T.yahoo_chart("X", 30)
        self.assertEqual(c["splits"], [(d(2022, 7, 1), 4.0)])


# ---------------------------------------------------------------------------
# AGT-05 Reverse-DCF, AGT-08 Dividende, AGT-10 Bear, AGT-11 EV <= 0
# ---------------------------------------------------------------------------
class TestBewertung(Basis):
    def _mit_implizitem_wachstum(self, k, g):
        ev = dcf_ref(k["fcf_basis"], g, 0.09)
        mcap = ev - (k["debt"] - k["cash"])
        return Q.bewerte("X", k, {"regularMarketPrice": mcap / 100, "sharesOutstanding": 100}, None, STAMM)

    def test_agt05_schrumpfend_nicht_konservativ(self):
        revs = [1000 * 0.95 ** i for i in range(5)]
        k = self.mk(jahre_roh([0.1 * r for r in revs], revs=revs))
        e = self._mit_implizitem_wachstum(k, 0.02)
        self.assertEqual(e["g_ref"], -5.0)
        self.assertAlmostEqual(e["g_impl"], 2.0, places=1)
        self.assertNotEqual(e["erw"], "konservativ")
        self.assertNotIn("Kurs preist weniger Wachstum ein als historisch erreicht", e["staerken"])

    def test_agt05_wachsend_konservativ_mit_staerke(self):
        revs = [1000 * 1.10 ** i for i in range(5)]
        k = self.mk(jahre_roh([0.1 * r for r in revs], revs=revs))
        e = self._mit_implizitem_wachstum(k, 0.05)
        self.assertEqual(e["g_ref"], 10.0)
        self.assertEqual(e["erw"], "konservativ")               # 5 % <= 10 % - 3 %
        self.assertIn("Kurs preist weniger Wachstum ein als historisch erreicht", e["staerken"])
        e = self._mit_implizitem_wachstum(k, 0.08)
        self.assertEqual(e["erw"], "realistisch")               # 8 % > 7 %

    def test_agt08_dividende(self):
        k = self.mk(jahre_roh([100] * 5))

        T._fx_cache["GBP"] = ([d(2015, 1, 1)], [1.0])
        T._fx_cache["ZAR"] = ([d(2015, 1, 1)], [1.0])

        def div(q, wae="USD"):
            kk = dict(k, kurs_wae=wae)
            kurs = 2000 if wae in ("GBp", "ZAc") else 20        # Pence/Cent: 2000 = 20 Pfund/Rand
            return Q.bewerte("X", kk, dict(regularMarketPrice=kurs, sharesOutstanding=100, **q), None, STAMM)["div"]

        self.assertEqual(div({"trailingAnnualDividendYield": 0.00035, "dividendYield": 3.5}), 3.5)
        self.assertEqual(div({"trailingAnnualDividendYield": 0.0, "dividendYield": 2.8}), 2.8)
        self.assertEqual(div({"trailingAnnualDividendYield": 0.025, "dividendYield": 0.0}), 2.5)
        self.assertEqual(div({"trailingAnnualDividendYield": 0.0003}, "GBp"), 3.0)   # Pence-Korrektur
        self.assertEqual(div({"trailingAnnualDividendYield": 0.0004}, "ZAc"), 4.0)
        self.assertEqual(div({"trailingAnnualDividendYield": 0.0003}, "USD"), 0.03)  # keine Korrektur
        kk = dict(k, div=0)
        e = Q.bewerte("X", kk, {"regularMarketPrice": 20, "sharesOutstanding": 100,
                                "trailingAnnualDividendYield": 0.0, "dividendYield": 0.0}, None, STAMM)
        self.assertEqual(e["div"], 0.0)

    def test_agt08_top50_dividende_zac(self):
        chart = {"reihe": [(d(2026, 10, 1), 1000.0)], "divs": [(d(2026, 5, 1), 0.4)], "waehrung": "ZAc"}
        self.assertEqual(T.dividendenrendite(chart), 4.0)        # 0.4 ZAR / 1000 ZAc = 4 %

    def test_agt10_bear_basis_positiv(self):
        revs = [100, 100, 100, 100, 5000]
        j = jahre_roh([-50, -50, -50, -50, 500], revs=revs, eps=False, ebit=[0.2 * r for r in revs],
                      extra={"TotalDebt": 0.0, "CashAndCashEquivalents": 0.0})
        k = self.mk(j)
        self.assertLess(k["fm_avg"], 0)
        e = Q.bewerte("X", k, {"regularMarketPrice": 10, "sharesOutstanding": 100}, None, STAMM)
        g_ref = 0.25                                              # Median > 25 % -> gekappt
        bear_wert = dcf_ref(0.5 * k["fcf_basis"] * 0.9, max(-0.02, 0.4 * g_ref), 0.10, abflachend=True)
        self.assertEqual(e["bear"], round((bear_wert / 1000 - 1) * 100, 1))
        self.assertGreater(e["szen"]["bear"]["pot"], -100)

    def test_agt10_bear_verlust_hoechstens_100(self):
        k = self.mk(jahre_roh([100, 110, 120, 130, 140], extra={"TotalDebt": 1e6, "CashAndCashEquivalents": 0.0}))
        e = Q.bewerte("X", k, {"regularMarketPrice": 20, "sharesOutstanding": 100}, None, STAMM)
        self.assertEqual(e["bear"], -100.0)
        self.assertEqual(e["szen"]["bear"]["pot"], -100.0)

    def test_agt11_ev_nicht_positiv(self):
        k = self.mk(jahre_roh([100] * 5))
        k["debt"], k["cash"] = 0, 5000
        e = Q.bewerte("X", k, {"regularMarketPrice": 30, "sharesOutstanding": 100}, None, STAMM)
        self.assertIsNone(e["g_impl"])
        self.assertIn("Unternehmenswert ≤ 0", e["erw"])
        k = self.mk(jahre_roh([-100] * 5))
        e = Q.bewerte("X", k, {"regularMarketPrice": 30, "sharesOutstanding": 100}, None, STAMM)
        self.assertIn("FCF ≤ 0", e["erw"])

    def test_bewerte_sicher_faengt_kaputte_eintraege(self):
        self.assertIsNone(Q.bewerte_sicher("X", {"wae": "USD"}, {}, None, STAMM))


# ---------------------------------------------------------------------------
# AGT-06 Dateigroesse
# ---------------------------------------------------------------------------
class TestAGT06Groesse(Basis):
    def test_groesse_nach_vollstaendigem_zusammenbau(self):
        gespeichert = []

        def komplett(n, speichern):
            if speichern:
                gespeichert.append(n)
            return {"werte": "x" * (15_000 * n),
                    "vergleich": {"alle|top": "v" * (5_000 * n), "i:dax|top": "i" * 50_000}}

        def groesse(o):
            return len(json.dumps(o).encode())

        ausgabe, n = Q.passende_groesse(komplett, groesse, max_bytes=900_000)
        self.assertLessEqual(groesse(ausgabe), 900_000)
        self.assertGreater(groesse(komplett(n + 5, False)), 900_000)   # groesstes passendes n
        self.assertEqual(gespeichert, [n])                              # Verlauf nur einmal, mit finalem n
        self.assertIn("i:dax|top", ausgabe["vergleich"])

    def test_letzter_ausweg_ohne_indexvergleich(self):
        def komplett(n, speichern):
            return {"werte": "x" * 850_000, "vergleich": {"alle|top": "v", "i:dax|top": "i" * 100_000}}

        ausgabe, n = Q.passende_groesse(komplett, lambda o: len(json.dumps(o).encode()), max_bytes=900_000)
        self.assertEqual(n, 15)
        self.assertNotIn("i:dax|top", ausgabe["vergleich"])
        self.assertTrue(ausgabe["vergleich_gekuerzt"])
        self.assertLess(len(json.dumps(ausgabe).encode()), 1_000_000)


# ---------------------------------------------------------------------------
# AGT-07 Wechselkurse
# ---------------------------------------------------------------------------
class TestAGT07Wechselkurs(Basis):
    def setUp(self):
        super().setUp()
        T._fx_cache.pop("USD", None)
        self.antworten = []

        def fake_chart(symbol, tage, intervall="1d"):
            return self.antworten.pop(0) if self.antworten else None

        p = mock.patch.object(T, "yahoo_chart", fake_chart)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(T, "FX_WIEDERHOLEN_SEK", 0)
        p.start()
        self.addCleanup(p.stop)

    def test_fehler_wird_nicht_fuer_den_lauf_gemerkt(self):
        self.antworten = [None, {"reihe": [(d(2026, 10, 9), 1.25)], "divs": [], "waehrung": "USD"}]
        self.assertIsNone(Q.nach_eur(125.0, "USD"))              # kein Ersatzkurs gespeichert
        self.assertEqual(Q.nach_eur(125.0, "USD"), 100.0)        # zweiter Versuch klappt

    def test_rueckfall_auf_letzten_bekannten_kurs(self):
        self.store.dateien[T.STATE_FX] = {"USD": ["2026-10-01", 1.10]}
        self.assertAlmostEqual(Q.nach_eur(110.0, "USD"), 100.0)
        self.assertTrue(T.fx_ist_ersatz("USD"))
        self.assertIsNone(Q.nach_eur(110.0, "USD", d(2023, 1, 1)))   # keine Historie erfunden
        self.antworten = [{"reihe": [(d(2026, 10, 9), 1.25)], "divs": [], "waehrung": "USD"}]
        self.assertEqual(Q.nach_eur(125.0, "USD"), 100.0)
        self.assertFalse(T.fx_ist_ersatz("USD"))
        self.assertTrue(T.fx_stand_speichern())
        self.assertEqual(self.store.dateien[T.STATE_FX]["USD"], ["2026-10-09", 1.25])

    def test_hoechstens_drei_versuche(self):
        for _ in range(6):
            Q.nach_eur(1.0, "USD")
        self.assertEqual(T._fx_fehl["USD"][0], T.FX_MAX_VERSUCHE)


# ---------------------------------------------------------------------------
# AGT-13 Wochenvergleich
# ---------------------------------------------------------------------------
class TestAGT13Wochenvergleich(Basis):
    def test_kuerzere_liste_ist_kein_rausflug(self):
        liste = [f"S{i}" for i in range(100)]
        self.store.dateien["v"] = {"staende": {"2026-10-01": {"alle|top": liste[:50]}}}
        ref, v = T.wochenvergleich("v", d(2026, 10, 9), {"alle|top": liste}, {}, top_n=45)
        self.assertEqual(ref, "2026-10-01")
        self.assertEqual(v["alle|top"]["raus"], [])
        self.assertEqual(self.store.dateien["v"]["top_n"]["2026-10-09"], 45)

    def test_echter_rausflug_bleibt(self):
        alt = [f"S{i}" for i in range(50)]
        neu = ["NEU"] + alt[:44] + alt[45:]                   # S44 faellt auf Platz 51
        neu = neu[:50] + ["S44"] + neu[50:]
        self.store.dateien["v"] = {"staende": {"2026-10-01": {"alle|top": alt}}, "top_n": {"2026-10-01": 50}}
        _, v = T.wochenvergleich("v", d(2026, 10, 9), {"alle|top": neu}, {}, top_n=50, speichern=False)
        self.assertEqual([(r["id"], r["vor"], r["jetzt"]) for r in v["alle|top"]["raus"]], [("S44", 45, 51)])
        self.assertNotIn("2026-10-09", self.store.dateien["v"]["staende"])


# ---------------------------------------------------------------------------
# AGT-15 Cache-Teile (64) mit Migration, unlesbare Teile werden nicht ueberschrieben
# ---------------------------------------------------------------------------
class TestAGT15CacheTeile(Basis):
    def setUp(self):
        super().setUp()
        self.heute = d(2026, 10, 12)
        self.symbole = [f"SYM{i}" for i in range(400)]
        for s in self.symbole:
            pfad = Q.STATE_CACHE_ALT.format(zlib.crc32(s.encode()) % 32)
            self.store.dateien.setdefault(pfad, {})[s] = {"stand": "2026-10-10", "k": {"s": s}}

    def test_aufteilung(self):
        self.assertEqual(Q.CACHE_TEILE, 64)
        self.assertEqual(Q.CACHE_TEILE % Q.CACHE_TEILE_ALT, 0)
        for s in self.symbole:
            self.assertEqual(Q.teil(s) % 32, zlib.crc32(s.encode()) % 32)

    def test_migration_aus_alten_32_teilen(self):
        cache, gesperrt, migriert = Q.lade_cache()
        self.assertEqual(set(cache), set(self.symbole))
        self.assertEqual(gesperrt, set())
        self.assertEqual(migriert, set(range(64)))
        geschrieben = Q.speichere_cache_teile(cache, migriert, gesperrt, {s: {} for s in self.symbole}, self.heute)
        self.assertEqual(geschrieben, set(range(64)))
        cache2, _, migriert2 = Q.lade_cache()
        self.assertEqual(cache2, cache)
        self.assertEqual(migriert2, set())

    def test_unlesbarer_alter_teil_sperrt_neue_teile(self):
        self.store.lese_fehler.add(Q.STATE_CACHE_ALT.format(7))
        cache, gesperrt, migriert = Q.lade_cache()
        self.assertEqual(gesperrt, {7, 39})
        self.assertNotIn(7, migriert)
        Q.speichere_cache_teile(cache, set(range(64)), gesperrt, {s: {} for s in self.symbole}, self.heute)
        self.assertNotIn(Q.STATE_CACHE.format(7), self.store.dateien)
        self.assertNotIn(Q.STATE_CACHE.format(39), self.store.dateien)

    def test_unlesbarer_neuer_teil_wird_nicht_ueberschrieben(self):
        cache, gesperrt, migriert = Q.lade_cache()
        Q.speichere_cache_teile(cache, migriert, gesperrt, {s: {} for s in self.symbole}, self.heute)
        vorher = copy.deepcopy(self.store.dateien[Q.STATE_CACHE.format(5)])
        self.store.lese_fehler.add(Q.STATE_CACHE.format(5))
        cache, gesperrt, _ = Q.lade_cache()
        self.assertIn(5, gesperrt)
        self.store.writes.clear()
        Q.speichere_cache_teile({}, set(range(64)), gesperrt, {}, self.heute)
        self.assertNotIn(Q.STATE_CACHE.format(5), self.store.writes)
        self.store.lese_fehler.clear()
        self.assertEqual(self.store.dateien[Q.STATE_CACHE.format(5)], vorher)


# ---------------------------------------------------------------------------
# SEC-08: keine Tokens/Crumbs im Log
# ---------------------------------------------------------------------------
class TestSEC08(unittest.TestCase):
    def test_fehlertext_ohne_query_und_token(self):
        import requests
        e = requests.ConnectionError("Max retries exceeded with url: /v7/finance/quote?symbols=A&crumb=GEHEIM "
                                     "https://discord.com/api/webhooks/1/TOKEN Bearer ghp_abcdefghijklmnop")
        t = T.fehlertext(e)
        for geheim in ("GEHEIM", "TOKEN", "ghp_abcdefghijklmnop"):
            self.assertNotIn(geheim, t)
        self.assertTrue(t.startswith("ConnectionError"))


if __name__ == "__main__":
    unittest.main()
