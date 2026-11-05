"""Etappe 4a: Branchenmodelle (Banken, Versicherer, REITs, Hypotheken-REITs) und classic_v2-Einstufung (E1)."""
import unittest

import investoren_agent as A
from investor_checks import basis as IB
from kennzahlen import branchenmodell as BR
from kennzahlen import classic_v2 as V2
from kennzahlen import datenvertrauen as DV
from test_investor_checks import firma, jahr


def bank(**ueber):
    """Muster-Bank: Bilanzsumme 10.000, EK 800, Gewinn 100, Kredite 6.000, Einlagen 7.000."""
    def j(datum, ng, ek, aktien, **w):
        return jahr(datum, umsatz=500.0, nettogewinn=ng, ek=ek, bilanzsumme=10000.0, aktien=aktien,
                    zinsunabh_aufwand=300.0, risikovorsorge=-30.0, kredite=6000.0, einlagen=7000.0,
                    mat_buchwert=ek - 100.0, bruttogewinn=None, ebitda=None, op_cf=None, fcf=None, **w)
    J = [j("2022-12-31", 80.0, 700.0, 105.0), j("2023-12-31", 88.0, 730.0, 103.0),
         j("2024-12-31", 95.0, 770.0, 101.0), j("2025-12-31", 100.0, 800.0, 100.0)]
    f = firma(sektor="Financial Services", branche="Banks - Regional", jahre=J, kurs=9.0, kurs_in_bericht=9.0,
              beta=1.0, aktien=100.0)
    f.update(ueber)
    return f


def reit(**ueber):
    """Muster-REIT: Gewinn klein (Abschreibungen 120), FFO = 40 + 120 - 10 = 150, Dividende 110."""
    J = [jahr(f"{y}-12-31", nettogewinn=40.0, abschreibungen=a, verkaufsgewinne=10.0, dividenden=110.0, ebitda=260.0,
              schulden=1500.0, cash=100.0, bilanzsumme=3000.0, zinsaufwand=60.0, aktien=100.0)
         for y, a in ((2022, 100.0), (2023, 105.0), (2024, 112.0), (2025, 120.0))]
    f = firma(sektor="Real Estate", branche="REIT—Industrial", jahre=J, kurs=20.0, kurs_in_bericht=20.0)
    f.update(ueber)
    return f


class Erkennung(unittest.TestCase):
    def test_typ_fein(self):
        faelle = {("Financial Services", "Banks—Regional"): "bank",
                  ("Financial Services", "Banks - Diversified"): "bank",
                  ("Financial Services", "Mortgage Finance"): "bank",
                  ("Financial Services", "Insurance—Life"): "versicherer",
                  ("Financial Services", "Insurance - Property & Casualty"): "versicherer",
                  ("Financial Services", "Insurance Brokers"): "finanzdienstleister",
                  ("Financial Services", "Asset Management"): "finanzdienstleister",
                  ("Financial Services", "Capital Markets"): "finanzdienstleister",
                  ("Financial Services", "Credit Services"): "finanzdienstleister",
                  ("Financial Services", "Financial Data & Stock Exchanges"): "finanzdienstleister",
                  ("Real Estate", "REIT—Retail"): "reit",
                  ("Real Estate", "REIT - Mortgage"): "hypotheken_reit",
                  ("Technology", "Software—Application"): None}
        for (s, b), erwartet in faelle.items():
            self.assertEqual(BR.typ_fein({"sektor": s, "branche": b}), erwartet, b)

    def test_standardfirma_ohne_branchenmodell(self):
        self.assertIsNone(BR.analyse(firma()))
        self.assertIsNone(BR.analyse(firma(sektor="Financial Services", branche="Asset Management")))

    def test_classic_v1_einstufung_unveraendert(self):
        """E1: Vermoegensverwalter bleiben in classic_v1 'bank' - nur classic_v2 prueft sie wie normale Firmen."""
        f = firma(sektor="Financial Services", branche="Asset Management")
        self.assertEqual(IB.sektor_typ(f), "bank")
        self.assertEqual(IB.sektor_typ(dict(f, _typ_v2="normal")), "normal")


class Bankmodell(unittest.TestCase):
    def test_formeln(self):
        typ, k, warn, na = BR.kennzahlen(bank())
        self.assertEqual(typ, "bank")
        self.assertAlmostEqual(k["roe"], 100 / ((800 + 770) / 2))
        self.assertAlmostEqual(k["rote"], 100 / 700)
        self.assertAlmostEqual(k["roa"], 100 / 10000)
        self.assertAlmostEqual(k["cir"], 300 / 500)
        self.assertAlmostEqual(k["risikokosten"], 30 / 6000)
        self.assertAlmostEqual(k["ek_quote"], 0.08)
        self.assertAlmostEqual(k["kredit_einlagen"], 6000 / 7000)
        self.assertAlmostEqual(k["tbvps_cagr"], ((700 / 100) / (600 / 105)) ** (1 / 3) - 1)
        self.assertIn("kbv_fair", k)                     # Modellannahme (CAPM)
        self.assertEqual(warn, [])

    def test_score_und_module(self):
        a = BR.analyse(bank())
        self.assertIsNotNone(a["score"])
        self.assertEqual(set(a["module"]), {"ren", "eff", "kap", "wert"})
        self.assertTrue(all(sc is not None for _, sc, _ in a["module"].values()))
        self.assertIn("Harte Kernkapitalquote (CET1)", a["nicht_verfuegbar"])

    def test_fehlende_bankposten_nicht_erfunden(self):
        """Ohne Einlagen/Kredite/Risikovorsorge entfallen diese Kennzahlen - kein Ersatzwert."""
        J = [dict(j, kredite=None, einlagen=None, risikovorsorge=None, zinsunabh_aufwand=None) for j in bank()["jahre"]]
        typ, k, _, _ = BR.kennzahlen(bank(jahre=J))
        for s_ in ("kredit_einlagen", "risikokosten", "cir"):
            self.assertNotIn(s_, k)
        a = BR.analyse(bank(jahre=J))
        self.assertIsNone(a["module"]["eff"][1])
        self.assertIsNotNone(a["score"])                 # ROE, ROTE, ROA, EK-Quote reichen

    def test_warnungen(self):
        J = bank()["jahre"]
        J[-1] = dict(J[-1], risikovorsorge=-180.0, ek=300.0)
        _, _, warn, _ = BR.kennzahlen(bank(jahre=J))
        self.assertTrue(any("Risikovorsorge" in w for w in warn))
        self.assertTrue(any("Eigenkapitaldecke" in w for w in warn))

    def test_zu_wenige_kennzahlen_kein_score(self):
        J = [{"datum": "2025-12-31", "nettogewinn": 10.0, "ek": 100.0}]
        a = BR.analyse(bank(jahre=J, kurs_in_bericht=None))
        self.assertIsNone(a["score"])


class Versicherer(unittest.TestCase):
    def _vers(self, branche):
        J = [jahr(f"{y}-12-31", nettogewinn=90.0, ek=900.0, bilanzsumme=6000.0, praemien=1000.0, schaeden=-650.0,
                  sga=270.0, dividenden=40.0, rueckkaeufe=10.0, aktien=100.0) for y in (2022, 2023, 2024, 2025)]
        return firma(sektor="Financial Services", branche=branche, jahre=J, kurs=12.0, kurs_in_bericht=12.0)

    def test_schaden_unfall_mit_combined_ratio(self):
        typ, k, _, na = BR.kennzahlen(self._vers("Insurance—Property & Casualty"))
        self.assertEqual(typ, "versicherer")
        self.assertAlmostEqual(k["combined"], (650 + 270) / 1000)
        self.assertAlmostEqual(k["ausschuettung_gewinn"], 90 / 50)
        self.assertEqual(na, [])

    def test_leben_combined_nicht_anwendbar_kein_nachteil(self):
        a = BR.analyse(self._vers("Insurance—Life"))
        self.assertNotIn("combined", a["k"])
        self.assertEqual(a["nicht_anwendbar"], ["combined"])
        b = BR.kompakt(a)
        abd = BR.abdeckung({f"L{i}": {"b": b} for i in range(25)})
        self.assertNotIn("combined", BR.ausgeschlossen(abd, "versicherer"))
        self.assertEqual(DV.branchen_vollstaendigkeit(b), 100.0)


class Reit(unittest.TestCase):
    def test_ffo_statt_gewinn(self):
        typ, k, warn, _ = BR.kennzahlen(reit())
        ffo = 40 + 120 - 10
        self.assertAlmostEqual(k["ffo_rendite"], ffo / 2000)
        self.assertAlmostEqual(k["ffo_deckung"], ffo / 110)
        self.assertAlmostEqual(k["nde_reit"], (1500 - 100) / 260)
        self.assertAlmostEqual(k["zinsdeckung"], 260 / 60)
        self.assertAlmostEqual(k["schuldenquote"], 0.5)
        self.assertAlmostEqual(k["ffops_cagr"], (150 / 130) ** (1 / 3) - 1)
        self.assertEqual(warn, [])
        a = BR.analyse(reit())
        self.assertAlmostEqual(a["p_ffo"], 2000 / 150)
        self.assertIsNotNone(a["score"])

    def test_ohne_veraeusserungsgewinne_hinweis(self):
        J = [dict(j, verkaufsgewinne=None) for j in reit()["jahre"]]
        _, k, warn, _ = BR.kennzahlen(reit(jahre=J))
        self.assertAlmostEqual(k["ffo_rendite"], 160 / 2000)
        self.assertTrue(any("Veräußerungsgewinne" in w for w in warn))

    def test_negativer_ffo_ist_echter_wert(self):
        J = [dict(j, nettogewinn=-300.0) for j in reit()["jahre"]]
        _, k, warn, _ = BR.kennzahlen(reit(jahre=J))
        self.assertLess(k["ffo_rendite"], 0)
        self.assertEqual(BR.punkte("ffo_rendite", k["ffo_rendite"]), 0.0)
        self.assertTrue(any("nicht durch FFO gedeckt" in w for w in warn))

    def test_hypotheken_reit_bankartig(self):
        J = [jahr(f"{y}-12-31", nettogewinn=60.0, ek=1000.0, bilanzsumme=6000.0, dividenden=55.0, aktien=100.0)
             for y in (2022, 2023, 2024, 2025)]
        a = BR.analyse(firma(sektor="Real Estate", branche="REIT—Mortgage", jahre=J, kurs=9.0, kurs_in_bericht=9.0))
        self.assertEqual(a["typ"], "hypotheken_reit")
        self.assertAlmostEqual(a["k"]["div_deckung_gewinn"], 60 / 55)
        self.assertNotIn("ffo_rendite", a["k"])


class Abdeckung(unittest.TestCase):
    def test_seltene_kennzahl_wird_datenluecke(self):
        ohne = [dict(j, einlagen=None) for j in bank()["jahre"]]
        werte = {f"B{i}": {"b": BR.kompakt(BR.analyse(bank(jahre=ohne) if i < 15 else bank()))}
                 for i in range(25)}
        abd = A.branchen_neu_bewerten(werte)
        self.assertEqual(abd["bank"]["n"], 25)
        self.assertAlmostEqual(abd["bank"]["kredit_einlagen"], 10 / 25)
        self.assertEqual(BR.ausgeschlossen(abd, "bank"), ["kredit_einlagen"])
        b = werte["B20"]["b"]
        self.assertEqual(b["dl"], ["kredit_einlagen"])
        self.assertIn("kredit_einlagen", b["k"])         # Wert bleibt gespeichert, zaehlt nur nicht
        titel, score, module, hinweise = BR.anzeigen(b)
        self.assertFalse(any(z[0] == "Kredite / Einlagen" for _, _, zeilen in module for z in zeilen))
        self.assertTrue(any("Datenlücke" in h for h in hinweise))

    def test_kleine_stichprobe_ohne_regel(self):
        abd = {"bank": {"n": 5, "kredit_einlagen": 0.0}}
        self.assertEqual(BR.ausgeschlossen(abd, "bank"), [])


class ClassicV2E1(unittest.TestCase):
    def test_konsens_v2_nur_fuer_finanzdienstleister(self):
        from investor_checks import abruf as AB
        kx = AB.kontext({"id": "X"}, {}, {"greenblatt": {}, "sektor_rang": {}}, None)
        self.assertIsNone(A.konsens_v2(firma(), kx))
        self.assertIsNone(A.konsens_v2(bank(), kx))
        s2 = A.konsens_v2(firma(sektor="Financial Services", branche="Asset Management"), kx)
        self.assertIsNotNone(s2)

    def test_v2_nutzt_s2_v1_bleibt(self):
        q = {"gesamt": 70, "pt": [20, 20, 20, 10], "abz": 0}
        r = V2.bewerte(q, {"score": 40.0, "s2": 60.0})
        self.assertEqual(r["konsens"], 60.0)
        self.assertEqual(r["v1"], 70)
        self.assertEqual(V2.bewerte(q, {"score": 40.0})["konsens"], 40.0)


class Datenvertrauen(unittest.TestCase):
    def test_bank_ohne_qualitaets_score(self):
        """Banken fehlen im Qualitaets-Score - die Vollstaendigkeit kommt dann aus dem Branchenmodell."""
        b = BR.kompakt(BR.analyse(bank()))
        r = DV.aktie({}, {"b": b, "st": "2026-11-01"}, stand="2026-11-03", sektor_typ="bank")
        self.assertEqual(r["teile"]["vollstaendigkeit"], 100)


class Anzeige(unittest.TestCase):
    def test_ki_invest_begruendung(self):
        import wiki_idee as WI
        b = BR.kompakt(BR.analyse(reit()))
        r = WI.begruendung({"art": "aktie", "name": "Muster-REIT", "detail": {"inv": {"b": b}}})
        titel = [t for t, _ in r["abschnitte"] if t.startswith("Branchenmodell")]
        self.assertEqual(len(titel), 1)
        self.assertIn("REIT", titel[0])
        zeilen = dict(r["abschnitte"])[titel[0]]
        self.assertTrue(any("FFO-Rendite" in z and "(Näherung)" in z for z in zeilen))
        self.assertTrue(any("Nicht verfügbar" in z for z in zeilen))


if __name__ == "__main__":
    unittest.main()
