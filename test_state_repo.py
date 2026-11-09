"""State-Repo-Umschaltung: mit STATE_REPO lesen/schreiben alle Agenten im privaten State-Repo, ohne die
Variable (oder leer, wie GitHub eine nicht gesetzte Variable liefert) wie bisher im Repo des Workflows."""
import glob
import os
import subprocess
import sys
import unittest

MODULE = {"discord_price_alert": "GITHUB_REPO", "kurs_agent": "GITHUB_REPO", "top50_agent": "GITHUB_REPO",
          "eks_agent": "REPO"}
HIER = os.path.dirname(os.path.abspath(__file__))


def _repo(modul, attr, **env):
    umgebung = {k: v for k, v in os.environ.items() if k not in ("STATE_REPO", "GITHUB_REPOSITORY")}
    umgebung.update(env)
    aus = subprocess.run([sys.executable, "-c", f"import {modul} as m; print('REPO=' + m.{attr})"], cwd=HIER,
                         env=umgebung, capture_output=True, text=True, timeout=120)
    zeilen = [z for z in aus.stdout.splitlines() if z.startswith("REPO=")]
    assert zeilen, aus.stderr[-500:]
    return zeilen[-1][5:]


class StateRepo(unittest.TestCase):
    def test_umschaltung_und_rueckfall(self):
        for modul, attr in MODULE.items():
            with self.subTest(modul=modul):
                self.assertEqual(_repo(modul, attr, GITHUB_REPOSITORY="a/code", STATE_REPO="a/state"), "a/state")
                self.assertEqual(_repo(modul, attr, GITHUB_REPOSITORY="a/code"), "a/code")
                self.assertEqual(_repo(modul, attr, GITHUB_REPOSITORY="a/code", STATE_REPO=""), "a/code")

    def test_workflows_reichen_repo_und_passendes_token_durch(self):
        """Token und Repo muessen zusammenpassen: das State-Token nur zusammen mit vars.STATE_REPO."""
        erwartet = "GH_STATE_TOKEN: ${{ vars.STATE_REPO && secrets.STATE_REPO_TOKEN || secrets.GITHUB_TOKEN }}"
        gefunden = 0
        for pfad in glob.glob(os.path.join(HIER, ".github", "workflows", "*.y*ml")):
            text = open(pfad, encoding="utf-8").read()
            if "GH_STATE_TOKEN" not in text:
                continue
            gefunden += 1
            self.assertNotIn("GH_STATE_TOKEN: ${{ secrets.GITHUB_TOKEN }}", text, pfad)
            self.assertEqual(text.count(erwartet), text.count("GH_STATE_TOKEN:"), pfad)
            self.assertEqual(text.count("STATE_REPO: ${{ vars.STATE_REPO }}"), text.count("GH_STATE_TOKEN:"), pfad)
        self.assertGreaterEqual(gefunden, 6)


if __name__ == "__main__":
    unittest.main()
