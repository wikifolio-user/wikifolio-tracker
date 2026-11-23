"""Tests Pyramidenmanager Etappe 1: Rechenkern (pyramide.py) und Adapter (pyramide_daten.py)."""
import datetime
import unittest

import pyramide as P
import pyramide_daten as D

UTC = datetime.timezone.utc


def kerzen(n=320, start=100.0, schritt=0.002, ende=datetime.date(2026, 11, 20), spanne=0.01, rauschen=0.003):
    """Synthetische Handelstag-Kerzen (Mo-Fr): konstante Tagesrendite plus kleines Hin und Her (sonst gaebe es keine
    Schwankung fuer den Fear-&-Greed-Score), endend am Datum `ende`."""
    tage, d = [], ende
    while len(tage) < n:
        if d.weekday() < 5:
            tage.append(d)
        d -= datetime.timedelta(days=1)
    tage.reverse()
    aus, c = [], start
    for i, t in enumerate(tage):
        o = c
        c = c * (1 + schritt + rauschen * (-1) ** i)
        aus.append([t.isoformat(), o, max(o, c) * (1 + spanne / 2), min(o, c) * (1 - spanne / 2), c])
    return aus


def gap(typ, unten, oben, lage, entfernung, status="offen", datum="2026-11-01"):
    return {"typ": typ, "datum": datum, "offen_unten": unten, "offen_oben": oben, "status": status, "lage": lage,
            "entfernung": entfernung, "vollstaendig": True}


STAT = {"up": {"quoten": {20: (80.0, 50)}}, "down": {"quoten": {20: (60.0, 40)}}}


class TrendScore(unittest.TestCase):
    def test_zu_wenige_kerzen(self):
        self.assertIsNone(P.trend_score(kerzen(100)))
        self.assertFalse(P.einstiegssignal(None)[0])

    def test_aufwaertstrend_volle_punkte(self):
        t = P.trend_score(kerzen())
        self.assertEqual(t["score"], 100.0)
        self.assertTrue(P.einstiegssignal(t)[0])

    def test_abwaertstrend(self):
        t = P.trend_score(kerzen(schritt=-0.002))
        self.assertLess(t["score"], 20)
        ok, gruende = P.einstiegssignal(t)
        self.assertFalse(ok)
        self.assertTrue(any("200-Tage-Linie" in g for g in gruende))

    def test_nur_vergangenheit(self):
        k = kerzen()
        self.assertEqual(P.trend_score(k[:-5])["datum"], k[-6][0])

    def test_atr(self):
        k = [["d", 10, 11, 9, 10]] * 21
        self.assertAlmostEqual(P.atr(k, 20), 2.0)
        self.assertIsNone(P.atr(k[:5], 20))


class StufenStops(unittest.TestCase):
    def test_tranchen_werden_kleiner_bis_minimum(self):
        a = [P.tranchen_anteil(s) for s in range(1, 21)]
        self.assertEqual(a[0], 1.0)
        self.assertAlmostEqual(a[1], 0.8)
        self.assertTrue(all(x >= y for x, y in zip(a, a[1:])))
        self.assertEqual(a[-1], 0.2)

    def test_nachzieh_stop_steigt_nur(self):
        s = P.nachzieh_stop(1000, 10)
        self.assertEqual(s, 970)
        self.assertEqual(P.nachzieh_stop(990, 10, s), 970)
        self.assertEqual(P.nachzieh_stop(1010, 10, s), 980)

    def test_nachkaufsignal(self):
        t = P.trend_score(kerzen())
        kurs = t["werte"]["kurs"]
        pyr = {"tranchen": [{"index_kauf": kurs - 5, "stufe": 1}]}
        ok, marke, gr = P.nachkaufsignal(pyr, t, 10)
        self.assertFalse(ok)                          # erst +1 ATR ueber dem letzten Kauf
        self.assertAlmostEqual(marke, kurs + 5)
        ok, _, _ = P.nachkaufsignal({"tranchen": [{"index_kauf": kurs - 15, "stufe": 1}]}, t, 10)
        self.assertTrue(ok)
        voll = {"tranchen": [{"index_kauf": 1, "stufe": i} for i in range(20)]}
        self.assertFalse(P.nachkaufsignal(voll, t, 10)[0])

    def test_ausstieg(self):
        self.assertTrue(P.ausstiegssignal({"score": 70}, 95, 100)[0])
        self.assertTrue(P.ausstiegssignal({"score": 30}, 105, 100)[0])
        self.assertFalse(P.ausstiegssignal({"score": 70}, 105, 100)[0])


KO_PROD = {"basiswert": "DAX", "richtung": "long", "basispreis": 18000.0, "ko_schwelle": 18000.0, "bezug": 0.01,
           "brief": 20.0, "finanzierung_pct": 0}


class WerteRisikoHebel(unittest.TestCase):
    def test_tranche_wert(self):
        d = {"art": "direkt", "stueck": 10, "kaufkurs": 100.0, "index_kauf": 20000.0}
        self.assertAlmostEqual(P.tranche_wert(d, 22000), 1100.0)
        k = {"art": "ko", "stueck": 100, "kaufkurs": 20.0, "index_kauf": 20000.0, "produkt": KO_PROD}
        self.assertAlmostEqual(P.tranche_wert(k, 20000), 2000.0)
        self.assertEqual(P.tranche_wert(k, 17999), 0.0)       # Knock-out

    def test_risiko_bis_stop(self):
        pyr = {"kapital": 10000, "tranchen": [{"stufe": 1, "art": "ko", "stueck": 100, "kaufkurs": 20.0,
                                               "index_kauf": 20000.0, "produkt": KO_PROD, "anfangsstop": 19500}]}
        r = P.risiko(pyr, 20000, 19000)               # Anfangsstop 19500 > gemeinsamer Stop -> 19500 gilt
        self.assertEqual(r["tranchen"][0]["stop"], 19500)
        self.assertAlmostEqual(r["gesamt"], 500.0)
        self.assertAlmostEqual(r["gesamt_pct"], 5.0)
        self.assertAlmostEqual(r["ko_kapital_pct"], 20.0)

    def test_max_hebel(self):
        h, ko = P.max_hebel(20000, 17000, 200)
        self.assertEqual(ko, 16800)
        self.assertAlmostEqual(h, 20000 / 3200)
        self.assertEqual(P.max_hebel(20000, 19990, 5)[0], 20.0)     # gedeckelt (hebel_max)
        self.assertEqual(P.max_hebel(20000, 19990, 5, P.einstellungen({"hebel_max": 8}))[0], 8.0)
        self.assertEqual(P.max_hebel(20000, None, 5), (None, None))
        self.assertTrue(P.ko_abstand_ok(18800, 19000, 200))
        self.assertFalse(P.ko_abstand_ok(18900, 19000, 200))


class Einstellungen(unittest.TestCase):
    def test_grenzen_und_ungueltiges(self):
        c = P.einstellungen({"atr_tage": 3, "hebel": 50, "nachkauf_atr": "x", "fg_modus": "quatsch",
                             "stop_anfang_atr": 1.5, "unbekannt": 1, "gewichte": {"gap": -5, "trend": 50}})
        self.assertEqual(c["atr_tage"], 5)
        self.assertEqual(c["hebel"], 20.0)
        self.assertEqual(c["nachkauf_atr"], P.STANDARD["nachkauf_atr"])
        self.assertEqual(c["fg_modus"], "kontraer")
        self.assertEqual(c["stop_anfang_atr"], 1.5)
        self.assertNotIn("unbekannt", c)
        self.assertEqual(c["gewichte"], {"trend": 50.0, "gap": 0.0, "fg": 10})
        self.assertIsNone(P.einstellungen({"hebel": None})["hebel"])
        self.assertEqual(P.STANDARD["atr_tage"], 20)                     # Startwerte unveraendert

    def test_cfg_fuer_pyramide(self):
        self.assertEqual(P.cfg_fuer({"einstellungen": {"atr_tage": 14}})["atr_tage"], 14)
        self.assertEqual(P.cfg_fuer(None)["atr_tage"], 20)

    def test_hebel_frei_mit_warnung(self):
        hb = P.hebel_bewertung(20000, 19000, 200, P.STANDARD, hebel=5)
        self.assertAlmostEqual(hb["passend"], 20000 / 1200)
        self.assertIsNone(hb["warnung"])
        hb = P.hebel_bewertung(20000, 19000, 200, P.einstellungen({"hebel": 20}))
        self.assertEqual(hb["gewaehlt"], 20.0)
        self.assertAlmostEqual(hb["ko_bei_gewaehlt"], 19000)
        self.assertIn("über dem passenden Hebel", hb["warnung"])
        self.assertIsNone(P.hebel_bewertung(20000, 19000, 200)["gewaehlt"])   # automatisch: nur Vorschlag


class GapWert(unittest.TestCase):
    def test_fehlt_nie_neutral(self):
        g = P.gap_wert(None, 100, 1)
        self.assertIsNone(g["wert"])
        self.assertEqual(g["stufe"], "fehlt")

    def test_gap_unter_dem_kurs_vorsicht(self):
        d = {"gaps": [gap("up", 95, 98, "unterhalb", 8)], "statistik": STAT, "status": "aktuell"}
        g = P.gap_wert(d, 100, 5)                      # Naehe-Grenze 10 Punkte
        self.assertAlmostEqual(g["wert"], 50 - 25 * 0.8 * 0.2)
        self.assertEqual(g["stufe"], "neutral")
        d["gaps"][0]["entfernung"] = 0
        self.assertEqual(P.gap_wert(d, 100, 5)["stufe"], "Vorsicht")

    def test_gap_ueber_dem_kurs_unterstuetzt(self):
        d = {"gaps": [gap("down", 101, 104, "oberhalb", 1)], "statistik": STAT, "status": "aktuell"}
        g = P.gap_wert(d, 100, 5)
        self.assertGreater(g["wert"], 60)
        self.assertEqual(g["stufe"], "unterstützt")

    def test_kein_nahes_gap_neutral_mit_daten(self):
        d = {"gaps": [gap("down", 200, 210, "oberhalb", 100), gap("up", 1, 2, "unterhalb", 3, "geschlossen")],
             "statistik": STAT, "status": "aktuell"}
        g = P.gap_wert(d, 100, 5)
        self.assertEqual(g["wert"], 50.0)
        self.assertEqual(g["status"], "aktuell")
        self.assertIn("Kein offenes Gap", g["gruende"][0])

    def test_veraltet_wird_weitergereicht(self):
        g = P.gap_wert({"gaps": [], "statistik": STAT, "status": "veraltet"}, 100, 5)
        self.assertEqual(g["status"], "veraltet")


class FearGreed(unittest.TestCase):
    FG = {"wert": 20, "kategorie": "Extreme Angst", "status": "aktuell", "quelle": "Eigener Score", "bezug": "index"}

    def test_original_deutung_einstieg_getrennt(self):
        e = P.fg_einstiegswert(self.FG)
        self.assertEqual((e["original"], e["deutung"], e["wert"]), (20.0, "Extreme Angst", 80.0))
        self.assertEqual(e["stufe"], "unterstützt")

    def test_modi(self):
        self.assertEqual(P.fg_einstiegswert(self.FG, P.einstellungen({"fg_modus": "trend"}))["wert"], 20.0)
        aus = P.fg_einstiegswert(self.FG, P.einstellungen({"fg_modus": "aus"}))
        self.assertIsNone(aus["wert"])
        self.assertEqual(aus["original"], 20)

    def test_us_wert_gekennzeichnet(self):
        e = P.fg_einstiegswert(dict(self.FG, bezug="us"))
        self.assertTrue(any("US-marktweit" in g for g in e["gruende"]))

    def test_fehlt(self):
        self.assertEqual(P.fg_einstiegswert(None)["stufe"], "fehlt")


class Kombiniert(unittest.TestCase):
    T = {"score": 80.0}
    G = {"wert": 50.0, "status": "aktuell"}
    F = {"wert": 30.0, "status": "aktuell"}

    def test_standardgewichtung(self):
        k = P.kombiniert(self.T, self.G, self.F)
        self.assertAlmostEqual(k["wert"], 0.7 * 80 + 0.2 * 50 + 0.1 * 30)

    def test_fehlend_oder_veraltet_nie_still_neutral(self):
        k = P.kombiniert(self.T, {"wert": None, "status": "fehlt"}, self.F)
        self.assertIsNone(k["wert"])
        self.assertIn("Gap-Analyse", k["grund"])
        k = P.kombiniert(self.T, self.G, dict(self.F, status="veraltet"))
        self.assertIsNone(k["wert"])
        self.assertIsNone(P.kombiniert(None, self.G, self.F)["wert"])

    def test_aus_und_eigene_gewichte(self):
        cfg = P.einstellungen({"fg_modus": "aus"})
        self.assertAlmostEqual(P.kombiniert(self.T, self.G, {"wert": None, "status": "aus"}, cfg)["wert"],
                               (70 * 80 + 20 * 50) / 90, places=1)
        cfg = P.einstellungen({"gewichte": {"trend": 100, "gap": 0, "fg": 0}})
        self.assertEqual(P.kombiniert(self.T, None, None, cfg)["wert"], 80.0)


class Nachkauf(unittest.TestCase):
    def setUp(self):
        self.t = P.trend_score(kerzen())
        self.kurs = self.t["werte"]["kurs"]
        self.atr = 1.0
        self.pyr = {"kapital": 100000.0, "hoechst": self.kurs, "tranchen": [
            {"stufe": 1, "art": "direkt", "stueck": 100, "kaufkurs": 100.0, "index_kauf": self.kurs - 3,
             "anfangsstop": self.kurs - 5}]}
        self.neu = {"art": "direkt", "stueck": 50, "kaufkurs": 100.0, "index_kauf": self.kurs}
        self.gut = {"wert": 80.0, "stufe": "unterstützt", "status": "aktuell", "gruende": ["x"]}

    def _p(self, erg, nr):
        return next(x for x in erg["pruefungen"] if x["nr"] == nr)

    def test_alles_ok(self):
        e = P.nachkauf_pruefung(self.pyr, self.t, self.atr, self.gut, self.gut, self.neu, self.kurs)
        self.assertTrue(e["erlaubt"], [x for x in e["pruefungen"] if x["ergebnis"] != "ok"])
        self.assertEqual([x["nr"] for x in e["pruefungen"]], [1, 2, 3, 4, 5, 6, 7, 7.5, 8])
        self.assertGreater(e["risiko_nach"]["gesamt"], e["risiko_vor"]["gesamt"])

    def test_guter_score_ueberstimmt_kein_fehlendes_signal(self):
        pyr = dict(self.pyr, tranchen=[dict(self.pyr["tranchen"][0], index_kauf=self.kurs)])   # keine +1 ATR
        e = P.nachkauf_pruefung(pyr, self.t, self.atr, self.gut, self.gut, self.neu, self.kurs)
        self.assertFalse(e["erlaubt"])
        self.assertEqual(self._p(e, 2)["ergebnis"], "nein")

    def test_risikolimit_verletzt(self):
        neu = dict(self.neu, stueck=100000)
        e = P.nachkauf_pruefung(self.pyr, self.t, self.atr, self.gut, self.gut, neu, self.kurs)
        self.assertFalse(e["erlaubt"])
        self.assertEqual(self._p(e, 8)["ergebnis"], "nein")

    def test_ko_zu_nah_am_stop_warnt_sperrt_aber_nicht(self):
        prod = dict(KO_PROD, basiswert="DAX", basispreis=self.kurs - 1.5, ko_schwelle=self.kurs - 1.5)
        neu = {"art": "ko", "stueck": 10, "kaufkurs": 0.02, "index_kauf": self.kurs, "produkt": prod}
        e = P.nachkauf_pruefung(self.pyr, self.t, self.atr, self.gut, self.gut, neu, self.kurs)
        self.assertEqual(self._p(e, 7.5)["ergebnis"], "Vorsicht")
        self.assertIn("vor dem Stop", self._p(e, 7.5)["text"])
        self.assertEqual(self._p(e, 7)["ergebnis"], "ok")
        self.assertTrue(e["erlaubt"])

    def test_ko_kapital_grenze_bleibt_pflicht(self):
        prod = dict(KO_PROD, basiswert="DAX", basispreis=self.kurs - 20, ko_schwelle=self.kurs - 20)
        neu = {"art": "ko", "stueck": 10, "kaufkurs": 0.2, "index_kauf": self.kurs, "produkt": prod}
        pyr = dict(self.pyr, einstellungen={"ko_kapital_max_pct": 0})
        e = P.nachkauf_pruefung(pyr, self.t, self.atr, self.gut, self.gut, neu, self.kurs)
        self.assertEqual(self._p(e, 7)["ergebnis"], "nein")
        self.assertFalse(e["erlaubt"])

    def test_einstellungen_der_pyramide_wirken(self):
        streng = dict(self.pyr, einstellungen={"risiko_tranche_pct": 0.05})
        e = P.nachkauf_pruefung(streng, self.t, self.atr, self.gut, self.gut, self.neu, self.kurs)
        self.assertEqual(self._p(e, 8)["ergebnis"], "nein")
        self.assertEqual(e["einstellungen"]["risiko_tranche_pct"], 0.05)

    def test_gap_und_fg_fehlen_nur_hinweis(self):
        e = P.nachkauf_pruefung(self.pyr, self.t, self.atr, None, None, self.neu, self.kurs)
        self.assertEqual(self._p(e, 3)["ergebnis"], "fehlt")
        self.assertEqual(self._p(e, 4)["ergebnis"], "fehlt")
        self.assertTrue(e["erlaubt"])

    def test_ohne_geplante_tranche_kein_ok(self):
        e = P.nachkauf_pruefung(self.pyr, self.t, self.atr, self.gut, self.gut, None, self.kurs)
        self.assertFalse(e["erlaubt"])
        self.assertIn("nicht prüfbar", self._p(e, 8)["text"])


def ohlc(**ueberschreiben):
    idx = {sym: {"kerzen": kerzen(), "pruefung": {"fehlende": []}} for sym in ("^NDX", "^GDAXI", "^GSPC", "^DJI")}
    idx.update(ueberschreiben)
    return {"stand": "2026-11-21T21:30:00+01:00", "indizes": idx}


SENT = {"stand": "2026-11-21T00:00:00+00:00", "quellen": {"cnn": {
    "wert": 12, "kategorie": "extreme fear", "zeit": "2026-11-20T21:00:00+00:00", "ok": "2026-11-21T00:00:00+00:00",
    "verlauf": [["2026-11-20", 12]]}}}


class Adapter(unittest.TestCase):
    JETZT = datetime.datetime(2026, 11, 23, 14, 0, tzinfo=UTC)     # Montag vor US-Handelsschluss

    def test_zuordnung_und_us_kennzeichnung(self):
        a = D.index_analyse(ohlc(), SENT, self.JETZT)
        self.assertEqual(set(a), {"NDX", "DAX", "SPX", "DJI"})
        self.assertEqual(a["DAX"]["yahoo"], "^GDAXI")
        self.assertIsNone(a["DAX"]["us_umfeld"])                  # CNN nie als DAX-Wert
        self.assertEqual(a["NDX"]["us_umfeld"]["bezug"], "us")
        self.assertEqual(a["NDX"]["fg_index"]["bezug"], "index")
        self.assertEqual(a["NDX"]["fg_index"]["karte"], "ndx")
        self.assertEqual(a["NDX"]["status"], "aktuell")
        self.assertEqual(a["NDX"]["alter_handelstage"], 0)        # Freitag ist die letzte abgeschlossene Kerze

    def test_zeitstempel_und_veraltet(self):
        alt = kerzen(ende=datetime.date(2026, 11, 10))
        a = D.index_analyse(ohlc(**{"^GDAXI": {"kerzen": alt}}), SENT, self.JETZT)
        self.assertEqual(a["DAX"]["letzte_kerze"], "2026-11-10")
        self.assertGreater(a["DAX"]["alter_handelstage"], 3)
        self.assertEqual(a["DAX"]["status"], "veraltet")
        b = D.bewertung(a["DAX"])
        self.assertFalse(b["trend_gilt"])
        self.assertIsNone(b["kombiniert"]["wert"])
        self.assertFalse(b["einstieg"])
        self.assertIn("veraltet", b["einstieg_gruende"][0])

    def test_fehlender_index(self):
        d = ohlc()
        del d["indizes"]["^DJI"]
        a = D.index_analyse(d, SENT, self.JETZT)
        self.assertEqual(a["DJI"]["status"], "fehlt")
        b = D.bewertung(a["DJI"])
        self.assertEqual(b["gap"]["stufe"], "fehlt")
        self.assertIsNone(b["kombiniert"]["wert"])

    def test_fear_greed_kaputt_ergibt_fehlt(self):
        orig = D.FG.karten
        D.FG.karten = lambda *a, **k: 1 / 0
        try:
            a = D.index_analyse(ohlc(), SENT, self.JETZT)
        finally:
            D.FG.karten = orig
        self.assertIsNone(a["NDX"]["fg_index"])
        self.assertEqual(D.bewertung(a["NDX"])["fg"]["stufe"], "fehlt")

    def test_handelstage_alt_wochenende_und_feiertag(self):
        self.assertEqual(D.handelstage_alt("XETRA", "2026-11-20", self.JETZT), 0)
        nach = datetime.datetime(2026, 11, 23, 22, 0, tzinfo=UTC)
        self.assertEqual(D.handelstage_alt("XETRA", "2026-11-20", nach), 1)
        self.assertEqual(D.handelstage_alt("NYSE", "2026-11-25", datetime.datetime(2026, 11, 27, 12, tzinfo=UTC)), 0)

    def test_atr_laenge_je_pyramide(self):
        a = D.index_analyse(ohlc(), SENT, self.JETZT)["DAX"]
        b20 = D.bewertung(a)
        b10 = D.bewertung(a, P.einstellungen({"atr_tage": 10}))
        self.assertEqual((b20["atr_tage"], b10["atr_tage"]), (20, 10))
        self.assertAlmostEqual(b10["atr"], P.atr(a["kerzen"], 10))

    def test_bewertung_mit_aufwaertstrend(self):
        b = D.bewertung(D.index_analyse(ohlc(), SENT, self.JETZT)["NDX"])
        self.assertTrue(b["trend_gilt"])
        self.assertTrue(b["einstieg"])
        self.assertEqual(b["trend"]["score"], 100.0)


if __name__ == "__main__":
    unittest.main()
