"""Tests fuer zinsrechner.py und abfindung.py (ohne Streamlit).

Referenzwerte sind unabhaengig gerechnet: geschlossene Formeln oder eine eigene kleine
Simulation hier im Test (ruft nicht den zu pruefenden Code auf).
Start: python3 -m unittest test_rechner
"""
import datetime
import math
import random
import sys
import types
import unittest

import abfindung as A
import zinsrechner as Z


def P(**kw):
    """Parameter wie im Rechner; Standard-Startdatum 1.1.2026 (sonst haengt das Ergebnis vom heutigen Monat ab)."""
    kw.setdefault("sd", "2026-01-01")
    return dict(Z.STANDARD, **kw)


# ---------------------------------------------------------------------------
# Unabhaengige Referenz-Simulation (Bankpraxis, Kalenderjahr)
# ---------------------------------------------------------------------------
def cent_auf(x):
    """Kaufmaennisch auf Cent (eigene Umsetzung ueber ganze Cent, nicht Decimal wie im Code;
    5e-5 Cent Toleranz gegen Gleitkomma-Rest wie 47.4799999999)."""
    c = math.floor(abs(x) * 100 + 0.5 + 5e-5)
    return math.copysign(c / 100, x) if c else 0.0


def cent_ab(x):
    """Auf Cent abrunden (Steuer)."""
    return math.floor(x * 100 + 5e-5) / 100


def ref_sim(a=0.0, s=0.0, si=1, vor=True, z=0.05, zp=12, monate=12, start_monat=1, st=0.0, fb=0.0,
            entnahme=None, dyn=0.0, dyn_jaehrlich=True, zinseszins=True, runden=True):
    """Kontostand nach 'monate' Monaten.
    - Rate s alle si Monate: vorschuessig am Anfang des Intervalls, nachschuessig am Ende (zinslos im Zahlmonat)
    - Monatszins linear z/12 auf den Kontostand, Gutschrift am Ende jeder Kalenderperiode (zp) und am Ende
    - Freibetrag fb je Kalenderjahr, Steuer st auf Zinsen ueber dem Freibetrag
    - entnahme: Liste je Monat (Monatsanfang bei vor, Monatsende sonst)
    - runden: Gutschrift kaufmaennisch auf Cent, Steuer auf Cent abgerundet (Kontoauszug)
    -> (Endkapital, Steuer gesamt, Zinsen gesamt, ausgezahlt)"""
    bal = float(a)
    offen = 0.0
    frei = fb
    steuer = zinsen = aus = 0.0
    zahl_nr = 0
    for m in range(1, monate + 1):
        zahlung = 0.0
        if (vor and (m - 1) % si == 0) or (not vor and m % si == 0):
            zahl_nr += 1
            start_m = m if vor else m - si + 1          # erster Monat des Intervalls
            stufe = (start_m - 1) // 12 if dyn_jaehrlich else zahl_nr - 1
            zahlung = s * (1 + dyn) ** stufe
        w = entnahme[m - 1] if entnahme and m <= len(entnahme) else 0.0
        if vor:
            bal += zahlung
            w = min(w, max(bal, 0.0))
            bal -= w
            offen += bal * z / 12
        else:
            offen += bal * z / 12
            bal += zahlung
            w = min(w, max(bal, 0.0))
            bal -= w
        kal = start_monat - 1 + m
        if kal % zp == 0 or m == monate:
            if runden:
                offen = cent_auf(offen)
            t = max(offen - frei, 0.0) * st if offen > 0 else 0.0
            if runden:
                t = cent_ab(t)
            if offen > 0:
                frei = max(frei - offen, 0.0)
            steuer += t
            zinsen += offen
            if zinseszins:
                bal += offen - t
            else:
                aus += offen - t
            offen = 0.0
        if kal % 12 == 0:
            frei = fb
    return bal, steuer, zinsen, aus


def bisektion(f, ziel, lo, hi, n=200):
    for _ in range(n):
        mi = (lo + hi) / 2
        if f(mi) >= ziel:
            hi = mi
        else:
            lo = mi
    return hi


# ---------------------------------------------------------------------------
# Einkommensteuertarif 2026 (§ 32a EStG) - unabhaengig ausgeschrieben
# ---------------------------------------------------------------------------
def tarif2026(x):
    x = math.floor(x)
    if x <= 12348:
        return 0
    if x <= 17799:
        y = (x - 12348) / 10000
        return math.floor((914.51 * y + 1400) * y)
    if x <= 69878:
        zz = (x - 17799) / 10000
        return math.floor((173.10 * zz + 2397) * zz + 1034.87)
    if x <= 277825:
        return math.floor(0.42 * x - 11135.63)
    return math.floor(0.45 * x - 19470.38)


ABG = 0.25 * 1.055


# ===========================================================================
# Zinsrechner
# ===========================================================================
class TestRegressionMonatlich(unittest.TestCase):
    def test_annuitaet_monatliche_gutschrift(self):
        # Geschlossene Rentenformel (ohne Cent-Rundung); die 120 Gutschriften sind je hoechstens 0,5 Cent
        # gerundet -> Abweichung hoechstens 0,005 * Summe q^k. Start am 1. eines beliebigen Monats: identisch.
        i = 0.05 / 12
        q = 1 + i
        grenze = 0.005 * sum(q ** k for k in range(120))
        for ea, faktor, soll in (("v", q, 17239.9384), ("n", 1.0, 17175.2374)):
            ref = 1000 * q ** 120 + 100 * (q ** 120 - 1) / i * faktor
            self.assertAlmostEqual(ref, soll, places=4)
            ergebnisse = set()
            for monat in range(1, 13):
                r = Z.rechne(P(a=1000, s=100, z=5, zp=1, n=10, ea=ea, sd=f"2026-{monat:02d}-01"))
                self.assertAlmostEqual(r["end"], ref, delta=grenze)
                self.assertAlmostEqual(r["end"], ref, delta=0.10)        # tatsaechlich nur wenige Cent
                ergebnisse.add(round(r["end"], 6))
            self.assertEqual(len(ergebnisse), 1)                         # Startmonat egal bei monatlicher Gutschrift
            self.assertAlmostEqual(r["end"], ref_sim(1000, 100, 1, ea == "v", 0.05, 1, 120)[0], places=6)

    def test_sparbuch_jaehrlich_monatsraten(self):
        # 100 €/Monat, 1 Jahr, 5 %: vorschuessig 1200 + 100*0,05*78/12, nachschuessig ... *66/12
        self.assertAlmostEqual(Z.rechne(P(a=0, s=100, z=5, n=1))["end"], 1200 + 100 * 0.05 * 78 / 12, places=9)
        self.assertAlmostEqual(Z.rechne(P(a=0, s=100, z=5, n=1, ea="n"))["end"], 1200 + 100 * 0.05 * 66 / 12,
                               places=9)

    def test_gegen_referenz_simulation_januar(self):
        random.seed(11)
        for _ in range(250):
            a, s, z = random.uniform(0, 5e4), random.uniform(0, 1500), random.uniform(-2, 8)
            jahre, zp, si = random.randint(1, 15), random.choice([1, 3, 6, 12]), random.choice([1, 3, 6, 12])
            vor = random.random() < 0.5
            st, fb = random.choice([(0, 0), (26.375, 1000), (26.375, 0)])
            r = Z.rechne(P(a=a, s=s, z=z, n=jahre, zp=zp, si=si, ea="v" if vor else "n", st=st, fb=fb))
            ref = ref_sim(a, s, si, vor, z / 100, zp, jahre * 12, 1, st / 100, fb)
            self.assertAlmostEqual(r["end"], ref[0], delta=1e-6 * (abs(ref[0]) + 1))
            self.assertAlmostEqual(r["steuer"], ref[1], delta=1e-6 * (abs(ref[1]) + 1))


class TestZins01Nachschuessig(unittest.TestCase):
    def test_jaehrlich_nachschuessig(self):
        self.assertAlmostEqual(Z.rechne(P(a=0, s=1200, si=12, z=5, n=1, ea="n"))["end"], 1200.00, places=9)
        ref = 1200 * (1.05 ** 10 - 1) / 0.05
        self.assertAlmostEqual(ref, 15093.47, places=2)
        r = Z.rechne(P(a=0, s=1200, si=12, z=5, n=10, ea="n"))["end"]
        self.assertAlmostEqual(r, ref, delta=0.05)                      # Formel ohne Cent-Rundung
        k = 0.0
        for _ in range(10):                                             # Kontoauszug: Zins je Jahr auf Cent
            k += cent_auf(k * 0.05) + 1200
        self.assertAlmostEqual(r, k, places=6)
        self.assertAlmostEqual(r, 15093.48, places=6)

    def test_jaehrlich_vorschuessig(self):
        self.assertAlmostEqual(Z.rechne(P(a=0, s=1200, si=12, z=5, n=1, ea="v"))["end"], 1260.0, places=9)
        ref = 1200 * 1.05 * (1.05 ** 10 - 1) / 0.05
        r = Z.rechne(P(a=0, s=1200, si=12, z=5, n=10, ea="v"))["end"]
        self.assertAlmostEqual(r, ref, delta=0.05)
        k = 0.0
        for _ in range(10):
            k += 1200
            k += cent_auf(k * 0.05)
        self.assertAlmostEqual(r, k, places=6)

    def test_vierteljaehrlich(self):
        self.assertAlmostEqual(Z.rechne(P(a=0, s=300, si=3, z=5, n=1, ea="n"))["end"], 1222.50, places=9)
        self.assertAlmostEqual(Z.rechne(P(a=0, s=300, si=3, z=5, n=1, ea="v"))["end"],
                               1200 + 300 * 0.05 * (12 + 9 + 6 + 3) / 12, places=9)

    def test_anzahl_raten(self):
        for ea in "vn":
            for si in (1, 3, 6, 12):
                r = Z.rechne(P(a=0, s=10, si=si, z=0, n=3, ea=ea))
                self.assertAlmostEqual(r["einzahlungen"], 10 * 36 / si, places=9)

    def test_dynamik_jaehrlich_nachschuessig(self):
        # Raten 100, 110, 121 jeweils am Jahresende
        r = Z.rechne(P(a=0, s=100, si=12, z=5, n=3, ea="n", dy=10, dya="j"))
        self.assertAlmostEqual(r["end"], 100 * 1.05 ** 2 + 110 * 1.05 + 121, places=9)
        self.assertAlmostEqual(r["letzte_rate"], 121, places=9)

    def test_dynamik_je_intervall_nachschuessig(self):
        raten = [300 * 1.1 ** k for k in range(4)]
        ref = sum(raten) + cent_auf(sum(b * 0.05 * m / 12 for b, m in zip(raten, (9, 6, 3, 0))))
        r = Z.rechne(P(a=0, s=300, si=3, z=5, n=1, ea="n", dy=10, dya="i"))
        self.assertAlmostEqual(r["end"], ref, places=9)
        self.assertAlmostEqual(r["end"], 1416.34, places=9)             # 1.416,3375 -> Zins auf Cent gerundet

    def test_dynamik_monatlich_unveraendert(self):
        # monatlich, jaehrliche Dynamik: Monate 1-12 Rate 100, 13-24 Rate 103 (beide Zahlungsarten)
        for ea in "vn":
            r = Z.rechne(P(a=0, s=100, si=1, z=0, n=2, ea=ea, dy=3, dya="j"))
            self.assertAlmostEqual(r["einzahlungen"], 1200 + 1236, places=9)

    def test_dynamik_fuzz(self):
        random.seed(5)
        for _ in range(150):
            si, vor, jaehrlich = random.choice([1, 3, 6, 12]), random.random() < .5, random.random() < .5
            n, z = random.randint(1, 8), random.uniform(0, 6)
            r = Z.rechne(P(a=0, s=100, si=si, z=z, n=n, ea="v" if vor else "n", dy=4, dya="j" if jaehrlich else "i"))
            ref = ref_sim(0, 100, si, vor, z / 100, 12, n * 12, 1, dyn=0.04, dyn_jaehrlich=jaehrlich)
            self.assertAlmostEqual(r["end"], ref[0], delta=1e-7 * (ref[0] + 1))


class TestZins04Kalenderjahr(unittest.TestCase):
    def test_start_juli(self):
        # 6 Monate bis 31.12. gutgeschrieben, Freibetrag neu ab Januar, Rest am Laufzeitende
        def rechnen(runden):
            k, steuer = 100000.0, 0.0
            for _ in range(2):
                zi = k * 0.05 / 2
                zi = cent_auf(zi) if runden else zi
                t = max(zi - 1000, 0) * 0.26375
                t = cent_ab(t) if runden else t
                k += zi - t
                steuer += t
            return k, steuer
        r = Z.rechne(P(a=100000, s=0, z=5, n=1, sd="2026-07-01", st=26.375, fb=1000))
        # Referenz des Audits ohne Cent-Rundung: Steuer 805,13 €, Ende 104.247,48 €
        k0, st0 = rechnen(False)
        self.assertAlmostEqual(st0, 805.13, places=2)
        self.assertAlmostEqual(k0, 104247.48, places=2)
        # mit Cent-Rundung wie auf dem Kontoauszug (ZINS-08): 395,62 + 409,50 = 805,12 €; Ende 104.247,49 €
        k1, st1 = rechnen(True)
        self.assertAlmostEqual(r["steuer"], st1, places=6)
        self.assertAlmostEqual(r["end"], k1, places=6)
        self.assertAlmostEqual(r["steuer"], 805.12, places=6)
        self.assertAlmostEqual(r["end"], 104247.49, places=6)
        self.assertAlmostEqual(r["steuer"], st0, delta=0.01)
        # Vertragsjahr (alt) haette 1.055,00 € Steuer ergeben - Freibetrag jetzt zweimal genutzt
        self.assertLess(r["steuer"], 1000)

    def test_januar_unveraendert_jahreszins_mit_steuer(self):
        k = k_ohne = 100000.0
        for _ in range(10):
            zi = cent_auf(k * 0.05)
            k += zi - cent_ab(max(zi - 1000, 0) * 0.26375)
            zi = k_ohne * 0.05
            k_ohne += zi - max(zi - 1000, 0) * 0.26375
        r = Z.rechne(P(a=100000, s=0, z=5, n=10, st=26.375, fb=1000))
        self.assertAlmostEqual(r["end"], k, places=6)
        self.assertAlmostEqual(r["end"], k_ohne, delta=0.10)

    def test_vierteljaehrlich_ab_februar(self):
        # Start Februar, Quartalsgutschrift: Ende Maerz (2 Monate), Juni, Sept., Dez., dann Jan. (Laufzeitende)
        k = 10000.0
        for mon in (2, 3, 3, 3, 1):
            k += cent_auf(k * 0.04 * mon / 12)
        r = Z.rechne(P(a=10000, s=0, z=4, n=1, zp=3, sd="2026-02-15"))
        self.assertAlmostEqual(r["end"], k, places=6)
        self.assertEqual(len([j for j in r["jahre"]]), 1)

    def test_startdatum_wirkt_sich_aus(self):
        a = Z.rechne(P(a=10000, s=100, z=3, n=5, sd="2026-01-01"))["end"]
        b = Z.rechne(P(a=10000, s=100, z=3, n=5, sd="2026-11-15"))["end"]
        self.assertNotAlmostEqual(a, b, places=2)

    def test_fuzz_kalender(self):
        random.seed(21)
        for _ in range(250):
            sm = random.randint(1, 12)
            a, s, z = random.uniform(0, 5e4), random.uniform(0, 1500), random.uniform(-2, 8)
            mon, zp, si = random.randint(1, 150), random.choice([1, 3, 6, 12]), random.choice([1, 3, 6, 12])
            vor = random.random() < 0.5
            st, fb = random.choice([(0, 0), (26.375, 1000), (26.375, 500)])
            r = Z.rechne(P(a=a, s=s, z=z, n=mon, ne="m", zp=zp, si=si, ea="v" if vor else "n", st=st, fb=fb,
                           sd=f"2027-{sm:02d}-01"))
            ref = ref_sim(a, s, si, vor, z / 100, zp, mon, sm, st / 100, fb)
            self.assertAlmostEqual(r["end"], ref[0], delta=1e-6 * (abs(ref[0]) + 1))
            self.assertAlmostEqual(r["steuer"], ref[1], delta=1e-6 * (abs(ref[1]) + 1))


class TestZins03Loese(unittest.TestCase):
    def test_anfangskapital_mit_entnahmeplan(self):
        ent = [1000.0] * 120

        def ende(a, runden=True):
            return ref_sim(a, z=0.03, monate=120, entnahme=ent, runden=runden)[0]
        ref = bisektion(lambda a: ende(a, False), 10000.0, 0.0, 1e6)   # ohne Rundung (wie im Audit)
        self.assertAlmostEqual(ref, 111466.76, delta=0.01)
        # kleinster Cent-Betrag mit Kontoauszug-Rundung (unabhaengige Simulation)
        c = round(math.floor(ref * 100) / 100 - 0.05, 2)
        while ende(c) < 10000.0 - 1e-6:
            c = round(c + 0.01, 2)
        self.assertAlmostEqual(c, 111466.76, delta=0.011)
        q, r, h = Z.loese(P(calc="a", e=10000, s=0, z=3, n=10, ep="10x1000"))
        self.assertEqual(h, "")
        self.assertGreaterEqual(r["end"], 10000.0)
        self.assertEqual(q["a"], c)
        weniger = Z.rechne(dict(q, a=q["a"] - 0.01))["end"]
        self.assertLess(weniger, 10000.0)

    def test_startwert_egal(self):
        q1 = Z.loese(P(calc="a", e=10000, s=0, z=3, n=10, ep="10x1000", a=200000))[0]
        q2 = Z.loese(P(calc="a", e=10000, s=0, z=3, n=10, ep="10x1000", a=0))[0]
        self.assertEqual(q1["a"], q2["a"])

    def test_sparrate_geschlossen(self):
        # Ziel 15093,47 mit jaehrlich nachschuessig 5 %, 10 J. -> Rate 1200
        q, r, h = Z.loese(P(calc="s", e=1200 * (1.05 ** 10 - 1) / 0.05, a=0, si=12, ea="n", z=5, n=10))
        self.assertEqual(h, "")
        self.assertAlmostEqual(q["s"], 1200.0, delta=0.011)

    def test_schon_erreicht_und_unerreichbar(self):
        q, r, h = Z.loese(P(calc="a", e=0, s=0, z=3, n=10, ep="10x1000"))
        self.assertEqual(q["a"], 0.0)
        self.assertIn("schon", h)
        _, _, h = Z.loese(P(calc="s", e=50000, a=0, n=0))
        self.assertIn("Nicht berechenbar", h)
        q, _, h = Z.loese(P(calc="a", e=1e12, s=0, z=-50, n=10))
        self.assertIn("nicht erreichbar", h)

    def test_fuzz_ziel_erreicht_cent_genau(self):
        random.seed(3)
        for _ in range(60):
            p = P(a=round(random.uniform(0, 5e4), 2), s=round(random.uniform(0, 1000), 2), z=round(random.uniform(-2, 8), 3),
                  n=random.randint(1, 25), zp=random.choice([1, 3, 6, 12]), si=random.choice([1, 3, 6, 12]),
                  ea=random.choice("vn"), st=random.choice([0, 26.375]), fb=random.choice([0, 1000]),
                  dy=random.choice([0, 2]), ep=random.choice(["", "3x200", "1x1000,2x100"]),
                  sd=f"2026-{random.randint(1, 12):02d}-01")
            soll = max(Z.rechne(p)["end"] * random.uniform(0.8, 1.3), 1.0)
            for c in ("a", "s"):
                q, r, h = Z.loese(dict(p, calc=c, e=soll))
                if h:
                    continue
                self.assertGreaterEqual(r["end"], soll, (c, p))
                self.assertAlmostEqual(q[c] * 100, round(q[c] * 100), places=6)
                if q[c] >= 0.01:
                    self.assertLess(Z.rechne(dict(q, **{c: round(q[c] - 0.01, 2)}))["end"], soll, (c, p))


class TestZins07Rundung(unittest.TestCase):
    def test_zins_und_dynamik_erreichen_ziel(self):
        random.seed(8)
        for _ in range(40):
            p = P(a=round(random.uniform(0, 5e4), 2), s=round(random.uniform(10, 1000), 2), z=round(random.uniform(0, 8), 3),
                  n=random.randint(1, 25), zp=random.choice([1, 3, 6, 12]), si=random.choice([1, 3, 6, 12]),
                  ea=random.choice("vn"), st=random.choice([0, 26.375]), dy=random.choice([0, 2]))
            soll = Z.rechne(p)["end"] * random.uniform(0.9, 1.2)
            for c in ("z", "dy"):
                q, r, h = Z.loese(dict(p, calc=c, e=soll))
                if h:
                    continue
                self.assertGreaterEqual(r["end"], soll, (c, p))
                self.assertAlmostEqual(q[c] * 1e4, round(q[c] * 1e4), places=4)

    def test_zinssatz_geschlossen(self):
        # 10.000 € -> 16.288,95 € in 10 J. jaehrlich = 5 %
        q, r, h = Z.loese(P(calc="z", e=10000 * 1.05 ** 10, a=10000, s=0, n=10))
        self.assertAlmostEqual(q["z"], 5.0, delta=1e-4)
        self.assertGreaterEqual(r["end"], 10000 * 1.05 ** 10 - 1e-9)


class TestZins02Permalink(unittest.TestCase):
    def test_roundtrip(self):
        for kw in (dict(a=123456.78, s=1234.56, z=3.125), dict(a=9999999999.99, s=0.01, z=-1.2345, calc="z", e=1e6 + 0.37),
                   dict(a=1.1, s=33.33, st=26.375, fb=1801.0, dy=1.75, n=7, ne="m", f=3, sd="2026-07-15"),
                   dict(sp="0.5x123.45,2x200", ep="1x1000.01", si=3, zp=6, ze=0, ea="n", dya="i", calc="a", e=12345.67)):
            p = P(**kw)
            back = Z.aus_url(Z.in_url(p))
            for k in Z.STANDARD:
                if k == "e" and p["calc"] == "e":
                    continue
                self.assertEqual(back[k], p[k], k)
            self.assertEqual(Z.rechne(back)["end"], Z.rechne(p)["end"])

    def test_phasen_text_verlustfrei(self):
        liste = [(1, 12345.67), (0.5, 0.01), (1 / 12, 1000.5), (2.25, 99999.99)]
        txt = Z.phasen_text(liste)
        self.assertEqual(Z.phasen(txt), [(12, 12345.67), (6, 0.01), (1, 1000.5), (27, 99999.99)])


class TestZins05Robust(unittest.TestCase):
    def test_aus_url_wirft_nie(self):
        random.seed(1)
        werte = ["inf", "-inf", "nan", "1e400", "-1e400", "abc", "", " ", "1,5", "12.5.3", "9" * 400, "-5", "0x10",
                 "1e9", "-1e9", "None", "[]", "2026-13-45", "9999-01-01", "0001-01-01", "1x1", "∞", "١٢"]
        for _ in range(3000):
            qp = {k: random.choice(werte + [str(random.uniform(-1e12, 1e12))]) for k in random.sample(list(Z.STANDARD), 6)}
            p = Z.aus_url(qp)
            for k, (lo, hi) in Z.GRENZEN.items():
                self.assertTrue(lo <= p[k] <= hi, (k, p[k]))
                self.assertTrue(math.isfinite(p[k]))
            self.assertIn(p["si"], Z.INTERVALLE)
            self.assertIn(p["zp"], Z.INTERVALLE)
            self.assertIn(p["ze"], (0, 1))
            self.assertIn(p["calc"], Z.ZIEL_FELDER)
            d = Z.startdatum(p)
            self.assertTrue(Z.JAHR_MIN <= d.year <= Z.JAHR_MAX)

    def test_aus_url_klemmen(self):
        p = Z.aus_url({"n": "1e9", "a": "-5", "z": "500", "st": "-1", "ze": "7", "ea": "x", "sd": "9999-06-01"})
        self.assertEqual((p["n"], p["a"], p["z"], p["st"], p["ze"], p["ea"], p["sd"]), (1200, 0.0, 100.0, 0.0, 1, "v", ""))
        self.assertEqual(Z.aus_url({"a": "nan", "s": "inf"})["a"], Z.STANDARD["a"])

    def test_startdatum_grenzen(self):
        heute = datetime.date.today()
        self.assertEqual(Z.startdatum({"sd": "9999-06-01"}), heute)
        self.assertEqual(Z.startdatum({"sd": "1899-12-31"}), heute)
        self.assertEqual(Z.startdatum({"sd": "2200-12-31"}), datetime.date(2200, 12, 31))

    def test_phasen(self):
        self.assertEqual(Z.phasen("0,5x100"), [(6, 100.0)])
        self.assertEqual(Z.phasen("1X100"), [(12, 100.0)])
        self.assertEqual(Z.phasen(" 2 x 300 "), [(24, 300.0)])
        self.assertEqual(Z.phasen("1x1000,3x500"), [(12, 1000.0), (36, 500.0)])
        self.assertEqual(Z.phasen("1x100,5"), [(12, 100.5)])
        self.assertEqual(Z.phasen("1x100;2x50"), [(12, 100.0), (24, 50.0)])
        self.assertEqual(Z.phasen("infx100,1xinf,nanx1,1xnan,-1x5,1x-5,1x100x5"), [])
        self.assertEqual(Z.phasen("1e308x1"), [(1200, 1.0)])
        self.assertEqual(sum(m for m, _ in Z.phasen("60x1,60x2,60x3")), 1200)

    def test_rechnen_nach_kaputtem_link(self):
        for qp in ({"sp": "1e308x1"}, {"ep": "99999x1", "a": "1e400"}, {"n": "inf", "z": "nan"}, {"sd": "9999-12-01"}):
            p = Z.aus_url(qp)
            r = Z.rechne(p)
            self.assertTrue(math.isfinite(r["end"]))
            Z.zeitachse(p, r)


class TestZins06Analyse(unittest.TestCase):
    def test_zinsauszahlung_erhalt(self):
        # 100.000 €, 200 €/Monat Entnahme (Monatsanfang), Zinsen jaehrlich ausgezahlt:
        # Summe ausgezahlter Zinsen = z * 879.000 muss die Entnahmen von 24.000 € decken
        p = P(a=100000, s=0, z=4, n=10, ze=0, ep="10x200")
        r = Z.rechne(p)
        an = Z.entnahme_analyse(p, r)
        self.assertIsNotNone(an["gesamt"]["erhalt"])
        self.assertAlmostEqual(an["gesamt"]["erhalt"], 24000 / 879000 * 100, delta=1e-4)
        self.assertGreater(an["phasen"][0]["deckung"], 1.0)
        html = Z.analyse_html(an)
        self.assertNotIn("nicht erreichbar", html)
        self.assertIn("ausgezahlte Zinsen", html)

    def test_unterscheidung(self):
        p = P(a=100000, s=0, z=4, n=10)
        self.assertIsNone(Z.noetiger_zins(p, 1e15))
        self.assertEqual(Z.noetiger_zins(p, 0.0), Z.IMMER_ERREICHT)
        self.assertAlmostEqual(Z.noetiger_zins(p, 100000 * 1.05 ** 10), 5.0, delta=1e-4)
        html = Z.analyse_html({"zins": 4.0, "gesamt": {"erhalt": Z.IMMER_ERREICHT, "wachstum": None}, "phasen": [],
                               "wachstum": 0.02, "eingezahlt": 1000.0})
        self.assertIn("jedem Zinssatz", html)

    def test_pdf_mit_analyse(self):
        for ze in (0, 1):
            p = P(a=100000, s=0, z=4, n=3, ze=ze, ep="1x500,2x300")
            r = Z.rechne(p)
            pdf = Z.pdf_bericht(p, r, "", "http://x/?a=1", Z.entnahme_analyse(p, r))
            self.assertTrue(pdf.startswith(b"%PDF"))


class TestZins06Loese(unittest.TestCase):
    def test_zinsauszahlung_zinssatz(self):
        # 10.000 €, Zinsen jaehrlich ausgezahlt, Ziel 13.000 € = Konto 10.000 + 10 x 300 € ausgezahlt -> 3 %
        q, r, h = Z.loese(P(calc="z", e=13000, a=10000, s=0, n=10, ze=0))
        self.assertAlmostEqual(q["z"], 3.0, delta=1e-4)
        self.assertGreaterEqual(r["end"] + r["ausgezahlt"], 13000.0)
        self.assertIn("ausgezahlte Zinsen", h)
        self.assertNotIn("nicht erreichbar", h)

    def test_deckung_passt_zu_erhalt(self):
        # Deckung >= 100 % (Zinsen nach Steuer decken die Entnahmen) <=> Erhalt-Zinssatz <= gewaehlter Zins
        random.seed(17)
        for _ in range(25):
            z = round(random.uniform(0.5, 7), 3)
            p = P(a=round(random.uniform(2e4, 3e5), 2), s=0, z=z, n=4, ze=random.choice([0, 1]),
                  st=random.choice([0, 26.375]), fb=random.choice([0, 1000]), ea=random.choice("vn"),
                  ep=f"2x{round(random.uniform(50, 1500), 2)},2x{round(random.uniform(50, 1500), 2)}",
                  sd=f"2026-{random.randint(1, 12):02d}-01")
            r = Z.rechne(p)
            an = Z.entnahme_analyse(p, r)
            for ph in an["phasen"]:
                if ph["deckung"] is None or ph["kapital"] <= 0:
                    continue
                if ph["deckung"] >= 1.0:
                    self.assertIsNotNone(ph["erhalt"])
                    self.assertLessEqual(ph["erhalt"], z + 1e-4, (p, ph))
                elif ph["erhalt"] not in (None, Z.IMMER_ERREICHT):
                    self.assertGreater(ph["erhalt"], z - 1e-4, (p, ph))
            if all((ph["deckung"] or 0) >= 1 for ph in an["phasen"]):
                self.assertNotIn("nicht erreichbar", Z.analyse_html(an))


class TestZins08Cent(unittest.TestCase):
    def test_halb_auf_und_steuer_ab(self):
        # 1 € zu 6 %, monatliche Gutschrift: 0,5 Cent -> 1 Cent (kaufmaennisch)
        self.assertAlmostEqual(Z.rechne(P(a=1, s=0, z=6, zp=1, n=1, ne="m"))["end"], 1.01, places=9)
        # 10,00 € Zinsen, 26,375 % ohne Freibetrag: 2,6375 -> 2,63 € (abgerundet)
        r = Z.rechne(P(a=1000, s=0, z=12, zp=1, n=1, ne="m", st=26.375, fb=0))
        self.assertAlmostEqual(r["zinsen"], 10.0, places=9)
        self.assertAlmostEqual(r["steuer"], 2.63, places=9)
        self.assertAlmostEqual(r["end"], 1007.37, places=9)
        # exakter Cent-Betrag trotz Gleitkomma: 24,00 € Zinsen * 26,375 % = 6,33 € genau
        r = Z.rechne(P(a=2400, s=0, z=12, zp=1, n=1, ne="m", st=26.375, fb=0))
        self.assertAlmostEqual(r["steuer"], 6.33, places=9)

    def test_alle_gutschriften_auf_cent(self):
        random.seed(4)
        for _ in range(60):
            r = Z.rechne(P(a=round(random.uniform(0, 1e5), 2), s=round(random.uniform(0, 900), 2),
                           z=random.uniform(-2, 9), zp=random.choice([1, 3, 6, 12]), n=random.randint(1, 12),
                           st=26.375, fb=random.choice([0, 801, 1000]), sd=f"2026-{random.randint(1, 12):02d}-01"))
            for j in r["jahre"]:
                self.assertAlmostEqual(j["zins"] * 100, round(j["zins"] * 100), places=5)
                self.assertAlmostEqual(j["steuer"] * 100, round(j["steuer"] * 100), places=5)
            self.assertAlmostEqual(r["end"] * 100, round(r["end"] * 100), places=4)


class TestZins10Chart(unittest.TestCase):
    def test_offene_zinsen_mit_freibetrag(self):
        # 10.000 € zu 5 %, Jahresgutschrift, Freibetrag 1.000 €: nach 6 Monaten 250 € aufgelaufen, steuerfrei
        r = Z.rechne(P(a=10000, s=0, z=5, n=1, st=26.375, fb=1000))
        self.assertAlmostEqual(r["zins_kum"][6], 250.0, places=6)
        self.assertAlmostEqual(r["wert"][6], 10250.0, places=6)
        # ohne Freibetrag: 250 € * (1 - 26,375 %)
        r = Z.rechne(P(a=10000, s=0, z=5, n=1, st=26.375, fb=0))
        self.assertAlmostEqual(r["zins_kum"][6], 250 * (1 - 0.26375), places=6)
        # teilweise verbraucht: 100.000 €, nach 6 Monaten 2.500 € -> Steuer auf 1.500 €
        r = Z.rechne(P(a=100000, s=0, z=5, n=1, st=26.375, fb=1000))
        self.assertAlmostEqual(r["zins_kum"][6], 2500 - 1500 * 0.26375, places=6)


class TestZins05Laufzeit(unittest.TestCase):
    def test_groesster_fall_unter_1s(self):
        import time
        for qp in ({"n": "1200", "f": "1200", "zp": "1", "st": "26.375", "ep": "1e9x5", "a": "1e10"},
                   {"sp": "100x100,100x200", "ep": "200x1", "zp": "1", "st": "26.375"}):
            p = Z.aus_url(qp)
            t = time.time()
            r = Z.rechne(p)
            self.assertLess(time.time() - t, 1.0)
            self.assertTrue(math.isfinite(r["end"]))

    def test_startjahr_und_phasen_grossbuchstabe(self):
        self.assertEqual(Z.aus_url({"sd": "2201-01-01"})["sd"], "")
        self.assertEqual(Z.aus_url({"sd": "2200-01-01"})["sd"], "2200-01-01")
        self.assertEqual(Z.phasen("0,5X100"), [(6, 100.0)])
        self.assertEqual(Z.phasen("0,25x100,1X200"), [(3, 100.0), (12, 200.0)])


# ===========================================================================
# Abfindung
# ===========================================================================
class TestTarif(unittest.TestCase):
    def test_tarif_2026(self):
        for x, soll in ((20000, 1570), (50000, 10548), (100000, 30864), (300000, 115529)):
            self.assertEqual(tarif2026(x), soll)
            self.assertEqual(A.est_tarif(x, 2026), soll)
        for x in range(0, 400000, 997):
            self.assertEqual(A.est_tarif(x, 2026), tarif2026(x), x)

    def test_splitting(self):
        for x in (30000, 80001, 123457, 600000):
            self.assertEqual(A.est(x, True, jahr=2026), 2 * tarif2026(math.floor(x / 2)))

    def test_fuenftelregel(self):
        # 50.000 € uebriges Einkommen + 100.000 € Abfindung
        ref = tarif2026(50000) + 5 * (tarif2026(70000) - tarif2026(50000))
        self.assertEqual(ref, 49128)
        self.assertEqual(A.est_mit_abfindung(50000, 100000, True, jahr=2026), ref)
        self.assertEqual(A.est_mit_abfindung(50000, 100000, False, jahr=2026), tarif2026(150000))


class TestAbf01Cent(unittest.TestCase):
    def test_soli(self):
        self.assertEqual(A.soli(20350), 0.0)
        self.assertEqual(A.soli(20351), 0.11)          # 0,119 € -> 0,11 €
        self.assertEqual(A.soli(20355), 0.59)          # 0,595 € -> abgerundet, nicht 0,60 €
        self.assertEqual(A.soli(100000), 5500.0)

    def test_kirchensteuer(self):
        self.assertEqual(A.steuern(1000.5, kirche=0.09)["kirche"], 90.04)   # 90,045 -> 90,04
        self.assertEqual(A.steuern(10548.0, kirche=0.09)["kirche"], 949.32)


class TestAbf02Anlage(unittest.TestCase):
    def ref_privat(self, betrag, jahre, rendite, aus, fb, tf=0.7):
        vp = bp = betrag
        g = rendite - aus
        for _ in range(jahre):
            div = vp * aus
            st = max(tf * div - fb, 0) * ABG
            rest = max(fb - tf * div, 0)
            vp = vp * (1 + g) + div - st
            bp += div - st
        return st, vp - max(tf * (vp - bp) - rest, 0) * ABG

    def test_etf_ein_jahr(self):
        av = A.anlage_vergleich(250000, 1, 0.06, art="etf", ausschuettung=0.02, freibetrag=1000)
        z = av["zeilen"][0]
        self.assertAlmostEqual(z["steuer_privat_lfd"], (0.7 * 5000 - 1000) * 0.26375, places=6)
        self.assertEqual(round(z["steuer_privat_lfd"], 2), 659.38)
        st, ref = self.ref_privat(250000, 1, 0.06, 0.02, 1000)
        self.assertAlmostEqual(z["privat"], ref, places=6)

    def test_freibetrag_nicht_doppelt(self):
        # kleine Ausschuettung: Rest des Pauschbetrags gilt beim Verkauf, aber nur einmal
        for jahre in (1, 5, 20):
            av = A.anlage_vergleich(100000, jahre, 0.07, art="etf", ausschuettung=0.005, freibetrag=1000)
            self.assertAlmostEqual(av["zeilen"][-1]["privat"], self.ref_privat(100000, jahre, 0.07, 0.005, 1000)[1],
                                   places=6)
        av = A.anlage_vergleich(100000, 3, 0.07, art="aktien", ausschuettung=0.02, freibetrag=1000)
        self.assertAlmostEqual(av["zeilen"][-1]["privat"], self.ref_privat(100000, 3, 0.07, 0.02, 1000, tf=1.0)[1],
                               places=6)


class TestAbf03Werbungskosten(unittest.TestCase):
    def e(self, wk):
        return dict(abfindung=100000.0, fuenftel_moeglich=True, splitting=False, kirche=0.09, zve1=50000.0, zve2=0.0,
                    alg1=0.0, alg2=0.0, jahr1=2026, werbungskosten=wk, rv=0.0, bav=0.0)

    def test_hinweis_und_netto(self):
        e = self.e(200000.0)
        titel = [t for t, _, wichtig in A.hinweise(e) if wichtig]
        self.assertIn("Kosten höher als die Abfindung", titel)
        for v in A.varianten(e):
            self.assertAlmostEqual(v["netto"], e["abfindung"] - v["steuer"]["summe"], places=6)
        self.assertNotIn("Kosten höher als die Abfindung", [t for t, _, _ in A.hinweise(self.e(5000.0))])

    def test_keine_negative_steuer(self):
        # Kosten > Abfindung: Steuer auf die Abfindung 0 € (vorher -11.497,32 €), Netto = Abfindung
        for wk in (100000.0, 200000.0, 1e6):
            for v in A.varianten(self.e(wk)):
                if v["kurz"].startswith("Zwei Jahre"):
                    continue
                self.assertAlmostEqual(v["steuer"]["summe"], 0.0, places=6, msg=(wk, v["kurz"]))
                self.assertLessEqual(v["netto"], 100000.0 + 1e-6)
        # 50/50: Kosten nur im 1. Jahr (Abflussprinzip), dort hoechstens 50.000 € -> 2. Haelfte normal besteuert
        v = [x for x in A.varianten(self.e(200000.0)) if x["kurz"].startswith("Zwei Jahre")][0]
        self.assertEqual(v["jahre"]["j1"]["abfindung"]["summe"], 0.0)
        j2 = v["jahre"]["j2"]["abfindung"]
        self.assertGreater(j2["est"], 9000)                      # 50.000 € im Folgejahr (zve2 = 0) voll besteuert
        self.assertAlmostEqual(v["steuer"]["summe"], j2["summe"], places=6)

    def test_kosten_unter_abfindung_unveraendert(self):
        # 5.000 € Anwalt bei 100.000 € Abfindung, Fuenftelregel: Abfindung 95.000 € in der Formel
        e = self.e(5000.0)
        v = [x for x in A.varianten(e) if x["kurz"] == "2026, Fünftel"][0]
        est_ref = tarif2026(50000) + 5 * (tarif2026(50000 + 19000) - tarif2026(50000))
        self.assertAlmostEqual(v["steuer"]["est"], est_ref - tarif2026(50000), places=6)


# ===========================================================================
# Oberflaeche mit einem Schein-Streamlit (nur: laeuft ohne Fehler durch)
# ===========================================================================
def _fake_streamlit(session=None, query=None):
    class W:
        session_state = {}

        def __init__(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def _wert(self, key, std):
            return W.session_state.get(key, std) if key else std

        def columns(self, n, **k):
            return [W() for _ in range(n if isinstance(n, int) else len(n))]

        def container(self, *a, **k):
            return W()

        def expander(self, *a, **k):
            return W()

        def empty(self, *a, **k):
            return W()

        def number_input(self, label, min_value=None, max_value=None, value="_", *a, key=None, **k):
            if value == "_":
                value = k.get("value", min_value if min_value is not None else 0)
            return self._wert(key, value)

        def toggle(self, label, value=False, key=None, **k):
            return value

        def selectbox(self, label, opts, index=0, key=None, **k):
            opts = list(opts)
            v = self._wert(key, opts[index or 0])
            return v if v in opts else opts[0]

        def date_input(self, label, value=None, key=None, **k):
            return self._wert(key, value or datetime.date.today())

        def data_editor(self, df, **k):
            return df

        def button(self, *a, **k):
            return False

        def download_button(self, label, data=None, *a, **k):
            W.downloads.append(data)
            return False

        def text_input(self, label, value="", **k):
            return value

        def __getattr__(self, n):
            return lambda *a, **k: None

    class QP(dict):
        def from_dict(self, d):
            pass

    st = W()
    W.session_state = dict(session or {})
    W.downloads = []
    st.query_params = QP(query or {})
    st.column_config = types.SimpleNamespace(NumberColumn=lambda *a, **k: None, TextColumn=lambda *a, **k: None,
                                             CheckboxColumn=lambda *a, **k: None)
    return st


class TestRenderSmoke(unittest.TestCase):
    def setUp(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas nicht installiert")
        self._alt = sys.modules.get("streamlit")

    def tearDown(self):
        if self._alt is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = self._alt

    def _run(self, modul, *args, session=None, query=None):
        st = _fake_streamlit(session, query)
        sys.modules["streamlit"] = st
        modul.render(*args)
        self.assertTrue(st.downloads and st.downloads[-1].startswith(b"%PDF"), "render nicht bis zum PDF gelaufen")
        return st

    def test_zinsrechner(self):
        self._run(Z, "https://x")
        st = self._run(Z, "", session={"zr_zielwert": 50000.0, "zr_sd_d": datetime.date(2026, 1, 1)})
        z = st.session_state["zr_z"]                    # Zielwert -> Zinssatz wird berechnet
        self.assertGreaterEqual(Z.rechne(P(z=z))["end"], 50000.0)
        self.assertLess(Z.rechne(P(z=round(z - 1e-4, 4)))["end"], 50000.0)
        st = self._run(Z, "", session={"zr_zielwert": 1500.0, "zr_sd_d": datetime.date(2026, 1, 1)},
                       query={"ze": "0", "a": "1000", "s": "0"})
        # 1.000 € + 10 x 50 € ausgezahlt -> 5 % (ab 4,9995 % rundet der Zins je Jahr schon auf 50,00 €)
        self.assertAlmostEqual(st.session_state["zr_z"], 4.9995, delta=1e-9)
        self._run(Z, "", query={"st": "26.375", "a": "100000", "zp": "3", "sd": "2026-07-01", "ep": "1x500"})
        st = self._run(Z, "", query={"calc": "a", "e": "10000", "ep": "0,5x1000,1X500", "ze": "0", "sd": "2026-07-01"})
        self.assertIsInstance(st.session_state.get("zr_a"), float)
        self._run(Z, "", query={"a": "nan", "n": "inf", "si": "1e400", "sd": "9999-01-01", "calc": "s", "e": "1e5",
                                "ea": "n"})
        for calc in ("n", "dy", "z"):
            self._run(Z, "", query={"calc": calc, "e": "30000", "s": "100"})

    def test_abfindung(self):
        self._run(A)
        self._run(A, session={"abf_wk": 200000.0, "abf_kirche": "9 % (übrige Länder)",
                              "abf_veranl": "Zusammen (Splitting)", "abf_rv": 5000.0, "abf_bav": 3000.0})


if __name__ == "__main__":
    unittest.main()
