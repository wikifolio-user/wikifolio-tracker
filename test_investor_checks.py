"""Investoren-Checks: jede Formel mit einem bekannten Rechenbeispiel, Sektorregeln, Robustheit (synthetische Daten)."""
import datetime
import math
import unittest

import pandas as pd

import investor_checks as I
from investor_checks import altman, basis, beneish, buffett, daten, graham, greenblatt, konsens, piotroski
from investor_checks import red_flags, templeton, terry_smith


def jahr(datum, **w):
    basis_werte = dict(umsatz=1000.0, bruttogewinn=500.0, ebit=200.0, ebitda=250.0, nettogewinn=150.0, eps=1.5,
                       abschreibungen=50.0, zinsaufwand=10.0, fue=80.0, sga=200.0, op_cf=180.0, capex=40.0,
                       fcf=140.0, dividenden=50.0, rueckkaeufe=20.0, umlauf=600.0, kurzfr_verb=250.0,
                       langfr_schulden=200.0, schulden=250.0, verbindlichkeiten=500.0, ek=800.0, bilanzsumme=1300.0,
                       gewinnruecklagen=400.0, forderungen=150.0, lager=100.0, goodwill=100.0, sachanlagen=400.0,
                       cash=150.0, aktien=100.0)
    basis_werte.update(w)
    return {"datum": datum, **basis_werte}


def firma(**ueber):
    """Solide Musterfirma: 4 Jahre wachsend, Kurs 20 (Berichtswaehrung USD)."""
    J = [jahr("2022-12-31", umsatz=800, bruttogewinn=400, ebit=150, nettogewinn=110, eps=1.10, op_cf=140, fcf=110,
              aktien=104, bilanzsumme=1200, umlauf=560),
         jahr("2023-12-31", umsatz=880, bruttogewinn=440, ebit=170, nettogewinn=125, eps=1.24, op_cf=155, fcf=120,
              aktien=102, bilanzsumme=1250, umlauf=580),
         jahr("2024-12-31", umsatz=950, bruttogewinn=475, ebit=185, nettogewinn=140, eps=1.38, op_cf=170, fcf=130,
              aktien=101, bilanzsumme=1280, umlauf=590),
         jahr("2025-12-31")]
    kurse = []
    d = datetime.date(2021, 1, 4)
    while d <= datetime.date(2026, 10, 27):
        if d.weekday() < 5:
            t = (d - datetime.date(2021, 1, 4)).days
            kurse.append((d.isoformat(), 15 + 5 * t / 2122, 1e6))
        d += datetime.timedelta(days=1)
    f = {"symbol": "MUST", "name": "Musterfirma", "sektor": "Technology", "branche": "Software—Application",
         "waehrung": "USD", "kurs_waehrung": "USD", "usd_faktor": 1.0, "kurs": 20.0, "kurs_in_bericht": 20.0,
         "mcap": 2000.0, "aktien": 100.0, "kbv": 2.5, "kuv": 2.0, "jahre": J, "quartale": [], "kurse": kurse,
         "dividenden_hist": [(f"{j}-06-01", 0.5) for j in range(2000, 2026)], "zyklisch": False}
    f.update(ueber)
    return f


class Rechenhilfen(unittest.TestCase):
    def test_division_null_und_fehlend(self):
        self.assertIsNone(basis.teile(1, 0))
        self.assertIsNone(basis.teile(None, 2))
        self.assertIsNone(basis.wachstum(10, -5))
        self.assertAlmostEqual(basis.cagr(121, 100, 2), 10.0)
        self.assertIsNone(basis.cagr(-1, 100, 2))

    def test_sektor_typ(self):
        self.assertEqual(basis.sektor_typ({"sektor": "Financial Services", "branche": "Banks—Diversified"}), "bank")
        self.assertEqual(basis.sektor_typ({"sektor": "Real Estate", "branche": "REIT—Retail"}), "reit")
        self.assertEqual(basis.sektor_typ({"sektor": "Utilities", "branche": "Utilities—Regulated Electric"}),
                         "versorger")
        self.assertEqual(basis.sektor_typ({"sektor": "Energy", "branche": "Oil & Gas Integrated"}), "zyklisch")
        self.assertEqual(basis.sektor_typ({"sektor": "Technology", "branche": "Software"}), "normal")


class Sektorregeln(unittest.TestCase):
    def test_zykliker_hinweis_beim_kgv(self):
        r = graham.check(firma(sektor="Energy", branche="Oil & Gas Integrated"), {})
        self.assertIn("Zykliker", next(k for k in r["kriterien"] if k["id"] == "kgv")["erklaerung"])

    def test_versorger_hoehere_schuldentoleranz(self):
        f = firma(sektor="Utilities", branche="Utilities—Regulated Electric")
        f["jahre"][-1]["langfr_schulden"] = 900.0      # 6 x Gewinn: normal zu viel, Versorger (8x) erlaubt
        k = next(k for k in buffett.check(f, {})["kriterien"] if k["id"] == "schulden")
        self.assertEqual((k["schwelle"], k["status"]), (8.0, "pass"))

    def test_bank_blendet_current_ratio_aus(self):
        r = graham.check(firma(sektor="Financial Services", branche="Banks—Diversified"), {})
        self.assertNotIn("current_ratio", [k["id"] for k in r["kriterien"]])
        self.assertTrue(any("Banken" in a["grund"] for a in r["ausgeblendet"]))


class Daten(unittest.TestCase):
    def test_perioden_aus_dataframes(self):
        t = [pd.Timestamp("2024-12-31"), pd.Timestamp("2025-12-31")]
        gj = pd.DataFrame({t[0]: [100.0, 40.0, 10.0, 1.0], t[1]: [120.0, 50.0, 12.0, 1.2]},
                          index=["Total Revenue", "Gross Profit", "Net Income", "Diluted EPS"])
        cf = pd.DataFrame({t[0]: [20.0, -5.0, -3.0], t[1]: [25.0, -6.0, float("nan")]},
                          index=["Operating Cash Flow", "Capital Expenditure", "Cash Dividends Paid"])
        p = daten.perioden(gj, None, cf)
        self.assertEqual([x["datum"] for x in p], ["2024-12-31", "2025-12-31"])     # aelteste zuerst
        self.assertEqual(p[0]["capex"], 5.0)                                          # Abfluss positiv
        self.assertEqual(p[1]["fcf"], 19.0)                                           # FCF = OCF - Capex
        self.assertIsNone(p[1]["dividenden"])                                         # NaN -> fehlt

    def test_usd_faktor_und_unterwaehrung(self):
        fx = {"USD": 1.1, "GBP": 0.84}
        self.assertEqual(daten.usd_faktor("USD", fx), 1.0)
        self.assertAlmostEqual(daten.usd_faktor("EUR", fx), 1.1)
        self.assertAlmostEqual(daten.usd_faktor("GBp", fx), 1.1 / 0.84 / 100)
        self.assertIsNone(daten.usd_faktor("XYZ", fx))
        # ADR: Kurs in USD, Bericht in EUR -> Kurs in EUR
        self.assertAlmostEqual(daten.kurs_in_berichtswaehrung(110, "USD", "EUR", fx), 100.0)


class Graham(unittest.TestCase):
    def test_graham_zahl(self):
        self.assertAlmostEqual(graham.graham_zahl(4, 25), math.sqrt(2250))   # = 47,43
        self.assertIsNone(graham.graham_zahl(-1, 25))                         # Verlust -> n/a
        self.assertIsNone(graham.graham_zahl(4, -3))                          # negatives EK -> n/a

    def test_graham_formel(self):
        self.assertAlmostEqual(graham.graham_formel(5, 5, y=5), 5 * 18.5 * 4.4 / 5)   # = 81,4

    def test_eps_wachstum_perioden(self):
        g, k = graham.eps_wachstum_perioden([1.0, 1.0, 1.0, 2.0, 2.0, 2.0])
        self.assertEqual((round(g, 6), k), (100.0, 3))
        g, k = graham.eps_wachstum_perioden([1.0, 1.2, 1.4, 1.6])             # 2 vs 2: 1,1 -> 1,5
        self.assertEqual(k, 2)
        self.assertAlmostEqual(g, (1.5 / 1.1 - 1) * 100)

    def test_dividenden_luecke(self):
        f = {"dividenden_hist": [("2019-05-01", 1), ("2020-05-01", 1), ("2022-05-01", 1), ("2023-05-01", 1),
                                 ("2024-05-01", 1), ("2025-05-01", 1)]}
        self.assertEqual(graham.dividenden_jahre_ohne_luecke(f, datetime.date(2026, 3, 1)), (4, 7))

    def test_check_musterfirma(self):
        r = graham.check(firma(), {})
        st = {k["id"]: k["status"] for k in r["kriterien"]}
        self.assertEqual(st["groesse"], "fail")                 # 1 Mrd Umsatz < 2 Mrd
        self.assertEqual(st["current_ratio"], "pass")           # 600/250 = 2,4
        self.assertEqual(st["gewinn_stabil"], "pass")
        self.assertEqual(st["dividende"], "pass")
        self.assertEqual(r["datenbasis"], "4 von 10 Jahren geprüft")
        self.assertTrue(any(k["eingeschraenkt"] for k in r["kriterien"]))


class Buffett(unittest.TestCase):
    def test_dcf_ewige_rente(self):
        # ohne Wachstum: Barwert = OE / r (10 Jahre + Endwert ergeben exakt die ewige Rente)
        self.assertAlmostEqual(buffett.dcf(100, 0, 10, 0, 10), 1000.0, places=6)
        self.assertIsNone(buffett.dcf(100, 5, 3, 3))            # Diskont <= ewiges Wachstum
        self.assertIsNone(buffett.dcf(-5, 5, 9, 2))

    def test_owner_earnings(self):
        self.assertEqual(buffett.owner_earnings({"nettogewinn": 150, "abschreibungen": 50, "capex": 40}), 160)

    def test_roe_negatives_ek(self):
        f = firma()
        f["jahre"][-1]["ek"] = -50.0
        r = buffett.check(f, {})
        roe = next(k for k in r["kriterien"] if k["id"] == "roe")
        self.assertEqual(roe["status"], "na")
        self.assertIn("Negatives Eigenkapital", roe["erklaerung"])

    def test_check_format(self):
        r = buffett.check(firma(), {"sektor_rang": (1, 40)})
        for feld in ("investor", "strategie", "kriterien", "erfuellt", "gesamt", "score_0_100", "fazit"):
            self.assertIn(feld, r)
        self.assertEqual(len(r["kriterien"]), 10)
        self.assertEqual(r["moat"]["punkte"] >= 1, True)


class Piotroski(unittest.TestCase):
    def test_alle_neun(self):
        v = jahr("2024", nettogewinn=100, bilanzsumme=1000, op_cf=90, langfr_schulden=300, umlauf=500,
                 kurzfr_verb=300, aktien=100, bruttogewinn=400, umsatz=1000)
        t = jahr("2025", nettogewinn=150, bilanzsumme=1000, op_cf=200, langfr_schulden=200, umlauf=600,
                 kurzfr_verb=300, aktien=99, bruttogewinn=480, umsatz=1100)
        s = piotroski.signale(t, v)
        self.assertEqual(sum(1 for x in s if x[3]), 9)

    def test_score_fazit(self):
        r = piotroski.check(firma(), {})
        self.assertIn("F-Score", r["fazit"])
        self.assertEqual(r["gesamt"], 9)


class Altman(unittest.TestCase):
    def test_formel_produzierend(self):
        # A=0,1 B=0,2 C=0,15 D=1,5 E=1,0 -> Z = 0,12+0,28+0,495+0,9+1,0 = 2,795 (Grauzone)
        f = {"jahre": [jahr("2025", bilanzsumme=1000, umlauf=300, kurzfr_verb=200, gewinnruecklagen=200, ebit=150,
                            verbindlichkeiten=400, umsatz=1000)], "mcap": 600.0, "kurs": 1.0, "kurs_in_bericht": 1.0,
             "sektor": "Industrials", "branche": "Machinery"}
        z = altman.z_score(f)
        self.assertAlmostEqual(z["z"], 2.795)
        self.assertEqual(altman.zone(z["z"], True), "grau")

    def test_nicht_produzierend(self):
        f = {"jahre": [jahr("2025", bilanzsumme=1000, umlauf=300, kurzfr_verb=200, gewinnruecklagen=200, ebit=150,
                            verbindlichkeiten=400, ek=600)], "sektor": "Technology", "branche": "Software"}
        z = altman.z_score(f)
        self.assertAlmostEqual(z["z"], 6.56 * 0.1 + 3.26 * 0.2 + 6.72 * 0.15 + 1.05 * 1.5)
        self.assertEqual(altman.zone(z["z"], False), "sicher")

    def test_bank_ausgeblendet(self):
        r = altman.check(firma(sektor="Financial Services", branche="Banks—Regional"), {})
        self.assertEqual(r["kriterien"], [])
        self.assertEqual((r["fazit"], r["warnungen"], r["extras"]), ("Für diesen Sektor nicht anwendbar.", [], []))
        self.assertTrue(r["ausgeblendet"])
        self.assertIsNone(r["score_0_100"])


class Beneish(unittest.TestCase):
    def test_neutral(self):
        ind = {k: 1.0 for k in beneish.GEWICHTE}
        ind["TATA"] = 0.0
        m, _ = beneish.m_score(ind)
        self.assertAlmostEqual(m, -4.84 + 0.92 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 - 0.327)   # -2,48

    def test_zu_viele_fehlend(self):
        self.assertIsNone(beneish.m_score({k: None for k in beneish.GEWICHTE})[0])

    def test_dsri(self):
        v = jahr("2024", forderungen=100, umsatz=1000)
        t = jahr("2025", forderungen=200, umsatz=1000)
        self.assertAlmostEqual(beneish.indizes(t, v)["DSRI"], 2.0)


class Greenblatt(unittest.TestCase):
    def test_raenge(self):
        u = [{"id": f"X{i}", "art": "aktie", "sektor": "Software", "k": {"ev_ebit": 5 + i, "roic": 30 - i}}
             for i in range(10)]
        u.append({"id": "BANK", "art": "aktie", "sektor": "Banks—Regional", "k": {"ev_ebit": 1, "roic": 99}})
        r = greenblatt.raenge(u)
        self.assertEqual(r["n"], 10)                       # Bank ausgeschlossen
        self.assertEqual(r["je_id"]["X0"][0], 1)          # guenstigste UND rentabelste = Platz 1
        self.assertEqual(r["je_id"]["X9"][0], 10)

    def test_exakt(self):
        f = firma()
        roc, ey = greenblatt.greenblatt_exakt(f)
        # Kapital = (600 - 150 - 250) + 400 = 600; ROC = 200/600; EV = 2000 + 250 - 150 = 2100
        self.assertAlmostEqual(roc, 200 / 600 * 100)
        self.assertAlmostEqual(ey, 200 / 2100 * 100)


class Templeton(unittest.TestCase):
    def test_historisches_kgv(self):
        k = templeton.historisches_kgv(firma())
        self.assertEqual(len(k), 4)
        self.assertTrue(all(x > 0 for x in k))


class TerrySmith(unittest.TestCase):
    def test_roce_und_zinsdeckung(self):
        self.assertAlmostEqual(terry_smith.roce({"ebit": 200, "bilanzsumme": 1300, "kurzfr_verb": 300}), 20.0)
        f = {"jahre": [jahr("2025", zinsaufwand=0, schulden=0)]}
        self.assertEqual(terry_smith.zinsdeckung(f), float("inf"))


class RedFlags(unittest.TestCase):
    def test_forderungen_warnsignal(self):
        f = firma()
        f["jahre"][-1]["forderungen"] = 300.0          # +~100 % bei ~5 % Umsatzwachstum
        r = red_flags.check(f, {})
        self.assertTrue(any("Forderungen" in w for w in r["warnungen"]))

    def test_unauffaellig(self):
        r = red_flags.check(firma(), {})
        self.assertEqual(r["warnungen"], [])


class Verlustfirma(unittest.TestCase):
    def test_verlust_wird_erklaert_nicht_gerechnet(self):
        f = firma()
        for j in f["jahre"]:
            j.update(nettogewinn=-50.0, eps=-0.5, ebit=-30.0)
        g = {k["id"]: k for k in graham.check(f, {})["kriterien"]}
        self.assertEqual((g["kgv"]["wert"], g["kgv"]["status"]), ("Verlust", "fail"))
        b = {k["id"]: k for k in buffett.check(f, {})["kriterien"]}
        self.assertEqual(b["schulden"]["wert"], "Verlust")
        self.assertIsNone(graham.graham_zahl(-0.5, 8))
        self.assertTrue(all(e["score_0_100"] is None or 0 <= e["score_0_100"] <= 100 for e in I.alle_checks(f, {})))


class Registry(unittest.TestCase):
    def test_alle_checks_laufen_und_haben_format(self):
        erg = I.alle_checks(firma(), {})
        self.assertEqual(len(erg), len(I.REGISTRY))
        for e in erg:
            for k in e["kriterien"]:
                self.assertIn(k["status"], ("pass", "fail", "na"))
            if e["score_0_100"] is not None:
                self.assertTrue(0 <= e["score_0_100"] <= 100, e["id"])

    def test_leere_daten_sind_na_nicht_fehler(self):
        for e in I.alle_checks({"jahre": [], "kurse": []}, {}):
            self.assertNotIn("Nicht berechenbar (", e["fazit"], e["id"])
            self.assertTrue(all(k["status"] == "na" for k in e["kriterien"]), e["id"])

    def test_fehlerhafter_check_bricht_nichts(self):
        I.REGISTRY["_kaputt"] = {"fn": lambda f, k: 1 / 0, "investor": "Test", "kategorie": "Value",
                                 "reihenfolge": 999}
        try:
            erg = I.alle_checks(firma(), {})
            self.assertIn("Nicht berechenbar", erg[-1]["fazit"])
        finally:
            del I.REGISTRY["_kaputt"]

    def test_konsens(self):
        k = konsens.konsens(I.alle_checks(firma(), {}))
        self.assertIn(k["note"], list("ABCDEF"))
        self.assertLessEqual(k["kaufen"], k["investoren"])
        self.assertEqual(konsens.note(None), "–")


if __name__ == "__main__":
    unittest.main()
