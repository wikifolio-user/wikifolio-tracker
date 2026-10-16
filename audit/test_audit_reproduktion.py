"""Audit 2026-10: unabhaengige Nachrechnung und Reproduktion der Befunde.

Ausfuehren:  python -m unittest audit/test_audit_reproduktion.py -v   (aus dem Projektordner)

Bewusst NICHT im Muster test_*.py des Projektstamms: die CI (unittest discover im
Stammordner) sammelt diese Datei nicht ein. Tests der Klasse "Befund*" beschreiben das
ERWARTETE (korrekte) Verhalten und sind bis zur Behebung rot - sie dienen als
Abnahmetest der Korrektur. Die Klassen "Nachrechnung*" vergleichen die App mit eigenen,
unabhaengig hergeleiteten Referenzwerten und sollten gruen sein.

Keine Netzzugriffe, keine Produktivdaten; app.py wird wie in test_app_rechner.py per AST
geladen (nur reine Funktionen), die Sollwerte sind von Hand bzw. mit eigenen Formeln
gerechnet.
"""
import ast
import bisect
import datetime
import html
import math
import os
import sys
import unittest

import numpy as np
import pandas as pd

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)

import abfindung  # noqa: E402
import nutzerdaten  # noqa: E402
import zinsrechner  # noqa: E402

FUNKTIONEN = ["fmt", "fmt_vz", "monats_termine", "entnahme_termine", "kumulierte_entnahme",
              "depot_kennzahlen", "berechne_reale_stueckzahl", "berechne_performance_kennzahlen",
              "realisierte_rendite_pa", "sparplan_termine", "sparplan_kaeufe", "_berlin_tage",
              "historie_zuschnitt"]


def _lade():
    with open(os.path.join(WURZEL, "app.py"), encoding="utf-8") as f:
        baum = ast.parse(f.read())
    defs = {n.name: n for n in baum.body if isinstance(n, ast.FunctionDef)}
    modul = ast.Module(body=[defs[f] for f in FUNKTIONEN], type_ignores=[])
    ns = {"html": html, "bisect": bisect, "datetime": datetime, "pd": pd, "np": np, "math": math}
    exec(compile(modul, "app.py", "exec"), ns)
    return ns


A = _lade()
D = datetime.date


# ---------------------------------------------------------------------------
# Testdatensatz (identisch mit dem Browser-Durchlauf des Audits):
# Kurs am 09.07.2025 = 100,00; je Handelstag (Mo-Fr) +0,10; Live-Kurs 150,00.
# ---------------------------------------------------------------------------
def _reihe(bis=D(2026, 10, 16)):
    tage, preise, d, i = [], [], D(2025, 7, 9), 0
    while d <= bis:
        if d.weekday() < 5:
            tage.append(pd.Timestamp(d))
            preise.append(round(100.0 + 0.1 * i, 4))
            i += 1
        d += datetime.timedelta(days=1)
    return pd.Series(preise, index=pd.DatetimeIndex(tage))


class NachrechnungDepot(unittest.TestCase):
    """Sollwerte von Hand: 13.000 EUR / 100,00 EUR = 130 Anteile; Kurs 150."""

    def test_depotwert_gewinn_rendite(self):
        k = A["depot_kennzahlen"](130.0, 0.0, 150.0, 13000.0, 0.0, 70.0, 15)
        self.assertAlmostEqual(k["brutto"], 19500.0, places=6)     # 130 x 150
        self.assertAlmostEqual(k["gewinn"], 6500.0, places=6)      # 19.500 - 13.000
        self.assertAlmostEqual(k["rendite_pct"], 50.0, places=9)   # 6.500 / 13.000
        self.assertAlmostEqual(k["netto"], 18450.0, places=6)      # 19.500 - 15 x 70

    def test_anzahl_entnahmen_09_07_2025_bis_17_10_2026(self):
        # 09.08.2025 ... 09.10.2026 = 15 Termine (Aug-Dez 2025: 5, Jan-Okt 2026: 10)
        self.assertEqual(len(A["entnahme_termine"](D(2025, 7, 9), D(2026, 10, 17))), 15)

    def test_reale_stueckzahl_eigene_simulation(self):
        """Eigene Referenz: je Termin am ersten Handelstag >= Termin 70 EUR zum Geldkurs
        (Kurs x (1 - 0,15 %)) verkaufen. Browser-Anzeige des Audits: 120,9886 Anteile."""
        s = _reihe()
        stueck = 130.0
        for m in range(15):
            termin = pd.Timestamp(D(2025, 7, 9)) + pd.DateOffset(months=m + 1)
            tag = s.index[s.index >= termin][0]
            stueck -= 70.0 / (s[tag] * (1 - 0.0015))
        df = s.to_frame("Close")
        app = A["berechne_reale_stueckzahl"](df, 130.0, 70.0, A["entnahme_termine"](D(2025, 7, 9), D(2026, 10, 17)), 0.15)
        self.assertAlmostEqual(app[-1], stueck, places=9)
        self.assertAlmostEqual(stueck, 120.9886, places=4)

    def test_realisierte_rendite_pa(self):
        # (150/100)^(365,25/465) - 1 = 37,50 % (Browser-Tabelle: +37,50 %)
        soll = (1.5 ** (365.25 / 465) - 1) * 100
        self.assertAlmostEqual(A["realisierte_rendite_pa"](150.0, 100.0, 465, 365), soll, places=9)
        self.assertAlmostEqual(soll, 37.50, places=2)

    def test_monatsende_kappung(self):
        t = A["monats_termine"](D(2024, 1, 31), D(2024, 5, 1))
        self.assertEqual([x.date() for x in t],
                         [D(2024, 1, 31), D(2024, 2, 29), D(2024, 3, 31), D(2024, 4, 30)])


class NachrechnungSteuer2026(unittest.TestCase):
    """Eigene Implementierung von § 32a EStG 2026 (Formeln aus dem Gesetzestext), unabhaengig
    vom Code in abfindung.py; Sollwerte zusaetzlich teils von Hand."""

    @staticmethod
    def est_2026(x):
        x = math.floor(x)
        if x <= 12348:
            return 0
        if x <= 17799:
            y = (x - 12348) / 10000
            return math.floor((914.51 * y + 1400) * y)
        if x <= 69878:
            z = (x - 17799) / 10000
            return math.floor((173.10 * z + 2397) * z + 1034.87)
        if x <= 277825:
            return math.floor(0.42 * x - 11135.63)
        return math.floor(0.45 * x - 19470.38)

    def test_tarifpunkte(self):
        for x in (0, 12348, 12349, 15000, 17799, 17800, 30000, 50000, 69878, 69879, 100000, 277825, 300000):
            self.assertEqual(abfindung.est_tarif(x, 2026), self.est_2026(x), x)
        # Handrechnung zvE 50.000: z = 3,2201; (173,10 z + 2397) z + 1034,87 = 10.548,34 -> 10.548
        self.assertEqual(abfindung.est_tarif(50000, 2026), 10548)

    def test_splitting(self):
        self.assertEqual(abfindung.est(100000, splitting=True, jahr=2026), 2 * self.est_2026(50000))

    def test_fuenftelregelung(self):
        rest, a = 40000.0, 60000.0
        soll = self.est_2026(rest) + 5 * (self.est_2026(rest + a / 5) - self.est_2026(rest))
        self.assertEqual(abfindung.est_mit_abfindung(rest, a, True, jahr=2026), min(soll, self.est_2026(rest + a)))

    def test_fuenftel_negatives_resteinkommen(self):
        # zvE ohne Abfindung -5.000, Abfindung 60.000 -> 5 x ESt(55.000 / 5)
        soll = min(5 * self.est_2026(55000 / 5), self.est_2026(55000))
        self.assertEqual(abfindung.est_mit_abfindung(-5000.0, 60000.0, True, jahr=2026), soll)

    def test_soli_milderungszone(self):
        # ESt 25.000: min(5,5 % x 25.000 = 1.375; 11,9 % x (25.000 - 20.350) = 553,35)
        self.assertAlmostEqual(abfindung.soli(25000.0, jahr=2026), 553.35, places=2)
        self.assertEqual(abfindung.soli(20350.0, jahr=2026), 0.0)
        self.assertAlmostEqual(abfindung.soli(100000.0, jahr=2026), 5500.0, places=2)


class NachrechnungZinseszins(unittest.TestCase):
    def test_einmalanlage_jaehrliche_gutschrift(self):
        # 10.000 EUR, 5 % p.a., jaehrliche Gutschrift ab 01.01., 10 Jahre, je Jahr auf Cent
        p = dict(zinsrechner.STANDARD, a=10000.0, s=0.0, z=5.0, zp=12, n=10, ne="j", sd="2027-01-01")
        soll = 10000.0
        for _ in range(10):
            soll = round(soll * 1.05, 2)
        self.assertAlmostEqual(zinsrechner.rechne(p)["end"], soll, places=2)   # 16.288,95

    def test_sparplan_nachschuessig_jaehrlich(self):
        # 100 EUR am Monatsende, 3 % p.a., jaehrliche Gutschrift, 1 Jahr ab 01.01.:
        # Zins = 100 x 0,03/12 x (11 + 10 + ... + 0) = 0,25 x 66 = 16,50
        p = dict(zinsrechner.STANDARD, a=0.0, s=100.0, si=1, ea="n", z=3.0, zp=12, n=1, ne="j", sd="2027-01-01")
        self.assertAlmostEqual(zinsrechner.rechne(p)["end"], 1216.50, places=2)


class Randfaelle(unittest.TestCase):
    def test_performance_bei_startwert_null(self):
        """Latent (in der UI durch die Aufrufer abgesichert): Startwert 0 darf nicht abstuerzen."""
        try:
            A["berechne_performance_kennzahlen"](0.0, 100.0, D(2025, 1, 1), D(2026, 1, 1))
        except ZeroDivisionError:
            self.fail("ZeroDivisionError bei Startwert 0 (app.py berechne_performance_kennzahlen)")

    def test_fmt_vz_negative_null(self):
        self.assertEqual(A["fmt_vz"](-0.004), "+0,00€")


# ---------------------------------------------------------------------------
# Befunde (bis zur Behebung ROT)
# ---------------------------------------------------------------------------
class BefundSEC03_Mandantentrennung(unittest.TestCase):
    """Zwei verschiedene Benutzernamen duerfen nie denselben Datenordner bekommen."""

    def test_verschiedene_namen_verschiedene_ordner(self):
        paare = [("anna.b", "anna-b"), ("jörg", "jorg"), ("a b", "a-b"), ("日本", "中国")]
        for n1, n2 in paare:
            o1 = nutzerdaten.ordner({"name": n1, "rolle": "benutzer"})
            o2 = nutzerdaten.ordner({"name": n2, "rolle": "benutzer"})
            self.assertNotEqual(o1, o2, f"{n1!r} und {n2!r} teilen sich {o1}")


class BefundSEC01_Secrets(unittest.TestCase):
    def test_keine_secrets_im_repo(self):
        pfad = os.path.join(WURZEL, ".streamlit", "secrets.toml")
        if os.path.exists(pfad):
            with open(pfad, encoding="utf-8") as f:
                inhalt = f.read()
            self.assertFalse("discord.com/api/webhooks/" in inhalt, "Discord-Webhook im Repository (Inhalt bewusst nicht ausgegeben)")


class BefundFIN01_FesterErsatzkurs(unittest.TestCase):
    def test_kein_fest_kodierter_kurs(self):
        with open(os.path.join(WURZEL, "app.py"), encoding="utf-8") as f:
            quelle = f.read()
        self.assertFalse("302.980" in quelle, "fest kodierter Ersatzkurs wird als Kurs/Depotwert angezeigt")


class BefundDATA_FehlerNichtCachen(unittest.TestCase):
    """Fehlgeschlagene Live-Abrufe duerfen nicht 26 h im st.cache_data landen: die
    gecachten Abruffunktionen muessen bei Fehlern eine Ausnahme werfen (wie lade_rohhistorie)."""

    def test_live_abrufe_werfen_bei_fehler(self):
        with open(os.path.join(WURZEL, "app.py"), encoding="utf-8") as f:
            baum = ast.parse(f.read())
        for fn in baum.body:
            if isinstance(fn, ast.FunctionDef) and fn.name in ("get_live_market_data", "get_live_kurs",
                                                                "get_benchmark_history"):
                gecacht = any("cache_data" in ast.unparse(d) for d in fn.decorator_list)
                gibt_fehlerwert = any(isinstance(n, ast.Return) and "Fehler" in ast.unparse(n)
                                      or (isinstance(n, ast.Return) and ast.unparse(n) == "return None")
                                      for n in ast.walk(fn))
                self.assertFalse(gecacht and gibt_fehlerwert,
                                 f"{fn.name}: Fehlerergebnis wird zwischengespeichert")


if __name__ == "__main__":
    unittest.main()
