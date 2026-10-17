"""Tests fuer Datenquellen-Funktionen aus app.py (python3 -m unittest test_app_quellen).

Wie test_app_rechner.py: die Funktionen werden per AST aus app.py geladen (ohne
Streamlit). Abgedeckt: eine Quelle fuer die Hauptposition (Audit A-04/A-05),
Kurskennzeichnung (A-11), Ersatzkurs aus der eigenen Preis-Historie (A-06) und die
Auswertung der ls-tc-Antwort (A-07).
"""
import ast
import datetime
import html
import os
import unittest
from zoneinfo import ZoneInfo

import config

FUNKTIONEN = ["hauptposition_werte", "kurs_status", "kurs_pill", "letzter_gespeicherter_kurs",
              "ls_tc_live_auswerten"]
BERLIN = ZoneInfo("Europe/Berlin")


def _lade():
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    with open(pfad, encoding="utf-8") as f:
        baum = ast.parse(f.read())
    defs = {n.name: n for n in baum.body if isinstance(n, ast.FunctionDef)}
    modul = ast.Module(body=[defs[f] for f in FUNKTIONEN], type_ignores=[])
    ns = {"datetime": datetime, "html": html, "config": config, "LIVE_MAX_ALTER_MIN": 20}
    exec(compile(modul, pfad, "exec"), ns)
    return ns


A = _lade()
HAUPT = {"id": "config-hauptposition", "name": "Hauptindizes Global", "wkn": config.WKN,
         "instrument_id": int(config.LS_INSTRUMENT_ID), "kaufdatum": "2025-07-09",
         "kaufkurs": 160.68, "startkapital": 26000.0}


class Hauptposition(unittest.TestCase):
    def test_gespeicherte_werte_gelten(self):
        w = A["hauptposition_werte"]([HAUPT], eigen=False)
        self.assertEqual(w["kaufkurs"], 160.68)
        self.assertEqual(w["startkapital"], 26000.0)
        self.assertEqual(w["kaufdatum"], datetime.date(2025, 7, 9))
        self.assertFalse(w["abweichend"])

    def test_ohne_gespeicherte_position_config(self):
        w = A["hauptposition_werte"]([], eigen=False)
        self.assertEqual((w["kaufkurs"], w["startkapital"]), (float(config.ANFANGSKURS), float(config.STARTKAPITAL)))

    def test_andere_erste_position_wird_nicht_verwendet(self):
        w = A["hauptposition_werte"]([dict(HAUPT, instrument_id=4361124)], eigen=False)
        self.assertTrue(w["abweichend"])
        self.assertEqual(w["kaufkurs"], float(config.ANFANGSKURS))

    def test_ungueltige_felder_fallen_auf_config(self):
        w = A["hauptposition_werte"]([dict(HAUPT, kaufkurs=0, kaufdatum="kaputt", startkapital="x")], eigen=False)
        self.assertEqual(w["kaufkurs"], float(config.ANFANGSKURS))
        self.assertEqual(w["kaufdatum"], config.KAUFDATUM)
        self.assertEqual(w["startkapital"], float(config.STARTKAPITAL))

    def test_normale_benutzer_ohne_startkapital(self):
        self.assertEqual(A["hauptposition_werte"]([HAUPT], eigen=True)["startkapital"], 0.0)


class KursStatus(unittest.TestCase):
    def _t(self, *a):
        return datetime.datetime(*a, tzinfo=BERLIN)

    def test_live_nur_frisch_und_in_handelszeit(self):
        jetzt = self._t(2026, 10, 14, 11, 0)                     # Mittwoch
        self.assertEqual(A["kurs_status"](self._t(2026, 10, 14, 10, 50), jetzt, True)[0], "live")
        self.assertEqual(A["kurs_status"](self._t(2026, 10, 14, 9, 0), jetzt, True), ("stand", "Stand 09:00"))

    def test_wochenende_nie_live(self):
        jetzt = self._t(2026, 10, 17, 0, 39)                     # Samstag nach Mitternacht
        self.assertEqual(A["kurs_status"](self._t(2026, 10, 16, 22, 59), jetzt, True),
                         ("stand", "Stand 16.10. 22:59"))

    def test_ohne_abruf_offline(self):
        self.assertEqual(A["kurs_status"](None, self._t(2026, 10, 14, 11, 0), False)[0], "offline")

    def test_pill_escaping(self):
        self.assertIn("&lt;b&gt;", A["kurs_pill"]("stand", "<b>"))


class GespeicherterKurs(unittest.TestCase):
    def test_letzte_gueltige_zeile_neueste_datei_zuerst(self):
        okt = "timestamp,price\n2026-10-16T22:55:00+02:00,133.1000\n2026-10-16T23:00:00+02:00,kaputt\n"
        sep = "timestamp,price\n2026-09-30T22:55:00+02:00,120.0000\n"
        kurs, zeit = A["letzter_gespeicherter_kurs"]([okt, sep])
        self.assertEqual(kurs, 133.1)
        self.assertEqual(zeit.hour, 22)

    def test_leer(self):
        self.assertEqual(A["letzter_gespeicherter_kurs"](["", "timestamp,price\n"]), (None, None))
        self.assertEqual(A["letzter_gespeicherter_kurs"](["", "timestamp,price\nx,0\n2026-09-01T10:00:00,95.5\n"])[0], 95.5)


class LiveAuswertung(unittest.TestCase):
    def test_kurs_vortag_zeitpunkt(self):
        data = {"series": {"intraday": {"data": [[1000, 98.0], [2000, 101.5]]}},
                "info": {"plotlines": [{"id": "previousDay", "value": 99.0}]}}
        self.assertEqual(A["ls_tc_live_auswerten"](data), (101.5, 99.0, 2000))

    def test_ohne_intraday_fehler(self):
        with self.assertRaises(ValueError):
            A["ls_tc_live_auswerten"]({"series": {}})

    def test_ungueltige_werte_fehler(self):
        with self.assertRaises(ValueError):
            A["ls_tc_live_auswerten"]({"series": {"intraday": {"data": [[1, 0.0]]}}})


if __name__ == "__main__":
    unittest.main()
