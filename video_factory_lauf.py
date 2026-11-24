"""Video Factory auf der Kommandozeile / in GitHub Actions.

  python video_factory_lauf.py projekt.json ausgabe/          # alle offenen Schritte
  python video_factory_lauf.py projekt.json ausgabe/ --nur bilder

projekt.json wird nach jedem Schritt aktualisiert (Status, Protokoll), die Dateien landen im Ausgabeordner."""
import argparse
import json
import logging
import os
import sys

import requests

from video_factory import pipeline as PL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("ausgabe")
    ap.add_argument("--nur", choices=PL.SCHRITTE)
    ap.add_argument("--stimmen", default=os.environ.get("PIPER_STIMMEN", "stimmen"))
    a = ap.parse_args(argv)
    with open(a.projekt, encoding="utf-8") as f:
        p = json.load(f)
    ki = None
    try:
        import ki_anbieter
        ki = ki_anbieter.verfuegbar()
    except Exception as ex:
        logging.warning("KI nicht verfügbar: %s", ex)

    def speichern(x):
        with open(a.projekt + ".teil", "w", encoding="utf-8") as f:
            json.dump(x, f, ensure_ascii=False, indent=1)
        os.replace(a.projekt + ".teil", a.projekt)
    p = PL.ausfuehren(p, {"ordner": a.ausgabe, "get": requests.get, "ki": ki, "stimmen_ordner": a.stimmen},
                      nur=a.nur, speichern=speichern)
    speichern(p)
    for name in PL.SCHRITTE:
        s = p["schritte"][name]
        logging.info("%-14s %-7s %s", name, s["status"], s.get("meldung", ""))
    return 0 if p["status"] not in ("fehler",) else 1


if __name__ == "__main__":
    sys.exit(main())
