"""Rauchtest der Oberflaeche: die ganze App (app.py) startet mit Testdaten ohne Netz, und JEDE Ansicht des Menues
wird einmal geoeffnet - keine darf eine Ausnahme werfen.

Laeuft nur, wenn Streamlit und Plotly installiert sind (CI: eigener Schritt; sonst uebersprungen). Netz und
GitHub-Speicher ersetzt die Attrappe audit/harness/fake_net.py (Kurse, State) mit den Testdaten aus
audit/harness/seed_daten.py; der Login ist per Secret abgeschaltet. Geprueft wird nur "rendert ohne Ausnahme" -
die Rechenlogik decken die uebrigen Tests ab.
"""
import os
import re
import sys
import tempfile
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HIER, "audit", "harness")
try:
    import plotly  # noqa: F401
    import requests
    from streamlit.testing.v1 import AppTest
    OBERFLAECHE = True
except ImportError:                                   # Rechen-CI ohne Streamlit: Test entfaellt
    OBERFLAECHE = False

# Texte, mit denen app.py eine abgefangene Ausnahme einer Ansicht anzeigt (st.error vor notify_app_error)
ABGEFANGEN = re.compile(r"^\W*(Fehler (in|im) |Kurs konnte nicht geladen|Position .{0,80} konnte nicht)")
MIN_ANSICHTEN = 20            # faellt das Menue unter diese Zahl, stimmt etwas mit dem Test nicht
ZEITLIMIT = 180


@unittest.skipUnless(OBERFLAECHE, "Streamlit/Plotly nicht installiert")
class AlleAnsichten(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, HARNESS)
        import fake_net
        import seed_daten
        cls._alt = (requests.get, requests.put, requests.delete, requests.post, getattr(requests, "_harness", False))
        cls._tmp = tempfile.TemporaryDirectory()
        fake_net.DUMP = os.path.join(cls._tmp.name, "store_dump.json")      # nichts ins Repo schreiben
        fake_net.install()
        seed_daten.seed(fake_net)
        cls.at = AppTest.from_file(os.path.join(HIER, "app.py"), default_timeout=ZEITLIMIT)
        cls.at.secrets["login_deaktiviert"] = True
        cls.at.secrets["GITHUB_REPO"] = "test/repo"
        cls.at.secrets["GITHUB_TOKEN"] = "x"
        cls.at.run()

    @classmethod
    def tearDownClass(cls):
        requests.get, requests.put, requests.delete, requests.post, requests._harness = cls._alt
        cls._tmp.cleanup()
        if HARNESS in sys.path:
            sys.path.remove(HARNESS)

    def _ausnahmen(self):
        """Unbehandelte Ausnahmen UND die Fehlerkaesten, mit denen app.py abgefangene Ausnahmen einer Ansicht
        anzeigt ("Fehler in/im ...: <Ausnahme>", "... konnte nicht berechnet/geladen werden"). Fachliche
        Hinweise (z. B. "Ab Alter 73 reicht das Geld nicht") zaehlen nicht."""
        return ([str(e.value)[:300] for e in self.at.exception] +
                [str(e.value)[:300] for e in self.at.error if ABGEFANGEN.match(str(e.value))])

    def _menue(self):
        """Zurueck zur Startseite; -> Beschriftungen der Menue-Knoepfe (ohne 'Kurse aktualisieren')."""
        self.at.session_state["ansicht_aktiv"] = None
        self.at.run()
        return [b.label for b in self.at.button if (b.key or "") != "nav_refresh"]

    def test_startseite_und_jede_ansicht(self):
        self.assertEqual(self._ausnahmen(), [], "Startseite wirft eine Ausnahme")
        ansichten = self._menue()
        self.assertGreaterEqual(len(ansichten), MIN_ANSICHTEN, ansichten)
        fehler = {}
        for name in ansichten:
            knopf = [b for b in self.at.button if b.label == name]
            if not knopf:
                fehler[name] = ["Menü-Knopf nicht gefunden"]
            else:
                try:
                    knopf[0].click().run()
                    if self._ausnahmen():
                        fehler[name] = self._ausnahmen()
                except Exception as e:                    # z. B. Zeitlimit (haengende Ansicht)
                    fehler[name] = [f"{type(e).__name__}: {e}"[:300]]
            self._menue()
        self.assertEqual(fehler, {}, "Ansichten mit Ausnahme: " + ", ".join(fehler))


if __name__ == "__main__":
    unittest.main()
