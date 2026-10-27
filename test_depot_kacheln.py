"""Depot-Kacheln (UX 10/2026): Kennzahlen Tag/Woche/Monat/Jahr vorne, Rest aufklappbar,
Gewinn/Verlust nie nur ueber Farbe."""
import ast
import html
import os
import unittest

import formate

NAMEN = ["zeitraeume_teilen", "_richtung_html", "gv_zeile_html", "kennzahl_kacheln_html",
         "zeitraum_zeilen_html", "depot_kachel_html"]
KONSTANTEN = ["KERN_ZEITRAEUME", "ALLE_ZEITRAEUME"]


def _lade():
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    with open(pfad, encoding="utf-8") as f:
        baum = ast.parse(f.read())
    teile = [n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name in NAMEN]
    teile += [n for n in baum.body if isinstance(n, ast.Assign)
              and any(getattr(t, "id", None) in KONSTANTEN for t in n.targets)]
    ns = {"FMT": formate, "html": html}
    exec(compile(ast.Module(body=teile, type_ignores=[]), pfad, "exec"), ns)
    return ns


A = _lade()
ZEILEN = [("Tag", 10.0, 1.0), ("Woche", -5.0, -0.5), ("Monat", 20.0, 2.0), ("3 Monate", 1.0, 0.1),
          ("Lfd. Jahr", 2.0, 0.2), ("Jahr", 100.0, 10.0), ("seit Kauf", 500.0, 50.0)]


class Kacheln(unittest.TestCase):
    def test_teilen(self):
        kern, rest = A["zeitraeume_teilen"](ZEILEN)
        self.assertEqual([z[0] for z in kern], ["Tag", "Woche", "Monat", "Jahr"])
        self.assertEqual([z[0] for z in rest], ["3 Monate", "Lfd. Jahr"])

    def test_junges_produkt_seit_datum_ist_kern(self):
        kern, _ = A["zeitraeume_teilen"]([("Tag", 1, 1), ("seit 28.01.2026", 3, 3), ("Tag*", 1, 1)])
        self.assertEqual([z[0] for z in kern], ["Tag", "seit 28.01.2026", "Tag*"])

    def test_nie_nur_farbe(self):
        h = A["kennzahl_kacheln_html"]([("Woche", -5.0, -0.5)])
        self.assertIn("▼", h)
        self.assertIn("−5,00 €", h)
        self.assertIn('class="kz down"', h)
        g = A["gv_zeile_html"](12.5, 3.0)
        self.assertIn("▲", g)
        self.assertIn("+12,50 €", g)

    def test_kachel_mit_aufklappbereich(self):
        k = A["depot_kachel_html"]("Depot gesamt", "1.000,00 €", gv=(500.0, 50.0), zeilen=ZEILEN,
                                    kopfzeile=("Vortag", "1,00 €"), fussnote="Einstand")
        self.assertIn("Weitere Zeiträume (3)", k)          # 3 Monate, Lfd. Jahr, Vortag
        self.assertEqual(k.count('class="kz '), 4)
        self.assertNotIn(">seit Kauf<", k.split("<details")[0].split('class="gv')[0])

    def test_ohne_zeitraeume_kein_klappbereich(self):
        k = A["depot_kachel_html"]("Position", "0,00 €", chips='<span class="meta-chip">ohne Kursquelle</span>')
        self.assertNotIn("<details", k)
        self.assertNotIn("kz-grid", k)

    def test_titel_wird_nicht_doppelt_escaped(self):
        k = A["depot_kachel_html"]("A &amp; B", "1 €")
        self.assertIn("A &amp; B", k)


if __name__ == "__main__":
    unittest.main()
