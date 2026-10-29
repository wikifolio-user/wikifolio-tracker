"""Qualitative Analyse: 10-K-Abschnitte, Textanalyse, Grosskunden, JSON aus KI-Antworten, Moat-Score (ohne Netz)."""
import datetime
import os
import unittest
from unittest import mock

import investor_config as C
import ki_anbieter as KI
import qualitativ_agent as QA
from investor_checks import qualitativ as Q

FUELL = " ".join(["word"] * 400)
HTML = f"""<html><body><div style="display:none">dei:EntityName Test</div>
<p>Table of Contents Item 1. Business 3 Item 1A. Risk Factors 9 Item 2. Properties 20</p>
<p>Item 1. Business</p><p>We are the market leader in widgets. Our brand and premium products drive loyalty.
Subscription and recurring revenue grow. {FUELL}</p>
<p>Competition. The market is competitive and we face pricing pressure from new entrants.</p>
<p>Customer A accounted for 14% of our net sales in fiscal 2025. No other customer exceeded 5% of revenue.</p>
<p>Item 1A. Risk Factors</p><p>Intense competition and disruption could harm us. {FUELL}</p>
<p>Item 1B. Unresolved Staff Comments</p><p>None.</p><p>Item 2. Properties</p><p>Offices.</p>
</body></html>"""


class Abschnitte(unittest.TestCase):
    def setUp(self):
        self.text = Q.text_aus_html(HTML)
        self.ab = Q.abschnitte(self.text)

    def test_inhaltsverzeichnis_wird_uebersprungen(self):
        self.assertIn("market leader", self.ab["business"])
        self.assertNotIn("Unresolved", self.ab["business"])
        self.assertIn("Intense competition", self.ab["risiken"])
        self.assertTrue(self.ab["competition"].lower().startswith("competition"))
        self.assertNotIn("EntityName", self.text)                 # versteckte XBRL-Daten entfernt

    def test_grosskunden(self):
        g = Q.grosskunden(self.ab["business"])
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0][0], 14.0)

    def test_dichte_je_10000_woerter(self):
        d = Q.moat_dichte("brand " * 10 + "word " * 990)    # 10 Treffer auf 1.000 Woerter
        self.assertAlmostEqual(d["Marke"], 100.0)
        self.assertEqual(Q.moat_dichte("zu kurz"), {})

    def test_risiko_woerter(self):
        r = Q.risiko_treffer(self.text)
        self.assertIn("intense competition", r)
        self.assertIn("pricing pressure", r)


class TextScore(unittest.TestCase):
    def test_sektordurchschnitt_ist_50(self):
        s, betont, _ = Q.text_score({"Marke": 10, "Netzwerkeffekt": 5}, {"Marke": 10, "Netzwerkeffekt": 5})
        self.assertEqual((s, betont), (50.0, []))

    def test_betont_und_gedeckelt(self):
        s, betont, v = Q.text_score({"Marke": 40, "Netzwerkeffekt": 5}, {"Marke": 10, "Netzwerkeffekt": 5})
        self.assertEqual(betont, ["Marke"])
        self.assertEqual(v["Marke"], 4.0)
        self.assertEqual(s, 75.0)                   # (min(4,2) + 1) / 2 * 50

    def test_ohne_peers(self):
        self.assertEqual(Q.text_score({"Marke": 3}, {})[0], None)

    def test_peer_mediane(self):
        self.assertEqual(Q.peer_mediane([{"Marke": 1}, {"Marke": 3}, {"Marke": 2}, {"Patente/Lizenzen": 1}]),
                         {"Marke": 2})


GUELTIG = {"marktposition": "Marktführer", "alleinstellungsmerkmal": "Ökosystem", "moat_typen": ["Marke"],
           "moat_trend": "stabil", "five_forces": {"rivalitaet": "Mittel"}, "abhaengigkeiten": ["China"],
           "disruptionsrisiko": "niedrig", "begruendung": "…", "konfidenz": 80}


class KiJson(unittest.TestCase):
    def test_markdown_und_text_drumherum(self):
        import json
        roh = "Hier ist die Analyse:\n```json\n" + json.dumps(GUELTIG) + "\n```\nViel Erfolg!"
        obj, fehler = Q.pruefen(Q.json_aus_text(roh))
        self.assertEqual(fehler, [])
        self.assertEqual(obj["konfidenz"], 0.8)                 # 80 -> 0,8
        self.assertEqual(obj["five_forces"]["rivalitaet"], "mittel")

    def test_klammern_in_strings(self):
        self.assertEqual(Q.json_aus_text('x {"a": "b } c", "d": 1} y'), {"a": "b } c", "d": 1})

    def test_ungueltig(self):
        self.assertIsNone(Q.json_aus_text("kein json"))
        obj, fehler = Q.pruefen({"marktposition": "x"})
        self.assertIsNone(obj)
        self.assertTrue(any("moat_typen" in f for f in fehler))

    def test_prompt_laenge_und_schema(self):
        p = Q.prompt({"name": "Test AG", "ticker": "TST"}, {"ROIC": "20 %"}, {"Business": "wort " * 20000},
                     max_woerter=1000)
        self.assertLessEqual(len(p.split()), 1100)
        self.assertIn("moat_typen", p)
        self.assertIn("Test AG", p)


class MoatScore(unittest.TestCase):
    def test_gewichtung_und_hochrechnung(self):
        m = Q.moat_score(3, 50.0, None)                     # ohne KI: 0,5*100 + 0,25*50 -> / 0,75
        self.assertAlmostEqual(m["score"], (0.5 * 100 + 0.25 * 50) / 0.75, places=1)
        self.assertEqual(m["quelle"], "berechnet + Textanalyse")

    def test_eigene_einschaetzung_ueberschreibt_mit_abweichung(self):
        m = Q.moat_score(3, 90.0, dict(GUELTIG, konfidenz=0.9), manuell=False)
        self.assertEqual((m["score"], m["quelle"]), (20.0, "eigene Einschätzung"))
        self.assertIn("weicht", m["abweichung"])

    def test_ki_score(self):
        self.assertEqual(Q.ki_moat_score({"moat_typen": ["keiner"], "moat_trend": "schrumpfend", "konfidenz": 1}), 0)
        self.assertIsNone(Q.ki_moat_score(None))


class Anbieter(unittest.TestCase):
    def test_ohne_key_kein_anbieter(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(KI.verfuegbar({}))

    def test_reihenfolge(self):
        a = KI.verfuegbar({"GROQ_API_KEY": "x", "GEMINI_API_KEY": "y"})
        self.assertEqual(a.name, C.KI_REIHENFOLGE[0])

    def test_analyse_wiederholt_einmal(self):
        import json
        antworten = iter(["Quatsch", json.dumps(GUELTIG)])
        a = KI.verfuegbar({"GEMINI_API_KEY": "y"})
        a.antwort = lambda p: next(antworten)
        obj, fehler = a.analyse("prompt")
        self.assertIsNone(fehler)
        self.assertEqual(obj["quelle"], "KI (Gemini)")


class Agent(unittest.TestCase):
    def test_faellig(self):
        heute = datetime.date(2026, 10, 29)
        self.assertTrue(QA.faellig(None, heute))
        self.assertTrue(QA.faellig({"st": "2026-10-01", "acc": "A"}, heute, acc="B"))      # neuer 10-K
        self.assertFalse(QA.faellig({"st": "2026-10-01", "acc": "A"}, heute, acc="A"))
        self.assertTrue(QA.faellig({"st": "2026-06-01"}, heute))                           # aelter als 90 Tage

    def test_dateiname(self):
        self.assertEqual(QA.datei("BRK/B"), "state/qualitativ/werte/BRK_B.json")

    def test_meta(self):
        idx = {str(i): {"q": "10-K", "sek": "Software", "d": {"Marke": float(i)}} for i in range(3)}
        m = QA.meta_aus_index(idx, datetime.date(2026, 1, 1))
        self.assertEqual(m["peer"]["10-K"]["Software"], {"Marke": 1.0})


if __name__ == "__main__":
    unittest.main()
