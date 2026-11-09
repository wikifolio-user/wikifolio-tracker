"""EKS-Ideen monatlich auswerten (GitHub Action .github/workflows/eks.yml, am 1. des Monats + manuell).

Liest die Ideen aller Benutzer (state/eks_ideen.json und state/benutzer/<name>/eks_ideen.json), rechnet alles
neu (eks_rechner) und schreibt je Datei nur den Abschnitt "letzter_lauf" zurueck: Stand, Ampeln (fuer die
Aenderungen beim naechsten Lauf) und die Zusammenfassung, die die EKS-Seite unter "Letzter Monatslauf" zeigt.

Zusammenfassung: Top 3, Ampel-Aenderungen seit dem letzten Lauf, Ideen laenger als 30 Tage im Status
"Test laeuft" und erreichte Abbruch-Kriterien (aus den Ist-Werten). Discord (Secret DISCORD_WEBHOOK_URL, dasselbe wie die Preisalarme) bekommt nur die Ideen des
Haupt-Kontos (state/eks_ideen.json) - die anderer Benutzer bleiben in deren eigenem Bereich. Ist der Webhook
nicht gesetzt oder nicht erreichbar, laeuft alles andere normal weiter (Hinweis in der App).
Die Job-Zusammenfassung von GitHub Actions enthaelt nur Zahlen, keine Ideen-Namen (sie kann oeffentlich sein).
"""
import datetime
import logging
import os
import sys

import requests

import config
import github_store
from eks_rechner import modell as M
from eks_rechner import rechnen as R

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("eks")

# State-Repo: eigenes (privates) Repo ueber STATE_REPO, sonst wie bisher das Repo des Workflows
REPO = os.environ.get("STATE_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GH_STATE_TOKEN", "")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
HAUPT = "state/eks_ideen.json"
DATEI = "eks_ideen.json"
TEST_TAGE = 30
DISCORD_MAX = 1900


def _datum(x):
    try:
        return datetime.datetime.fromisoformat(str(x)[:16])
    except (TypeError, ValueError):
        return None


def zusammenfassung(daten, jetzt):
    """-> (zeilen, ampeln {id: ampel}, zahlen {ideen, gruen, aenderungen, test_alt}) - ohne Netz testbar."""
    daten = M.bereinigen(daten)
    rang = R.rangliste(daten)
    ampeln = {r["id"]: r["ampel"] for r in rang}
    alt = ((daten.get("letzter_lauf") or {}).get("ampeln")) or {}
    zeilen = []
    aktiv = [r for r in rang if r["status"] != "verworfen"]
    if aktiv:
        zeilen.append("Top 3:")
        for n, r in enumerate(aktiv[:3], 1):
            zeilen.append(f"{n}. {R.AMPEL[r['ampel']]} {r['name']} – Nutzwert {round(r['nutzwert'] or 0)}, "
                          f"NPV {round(r['npv']):,} €, ".replace(",", ".") +
                          ("€/h –" if r["euro_h"] is None else f"€/h {r['euro_h']:.2f}".replace(".", ",")))
    else:
        zeilen.append("Keine aktiven Ideen.")
    aenderungen = [r for r in rang if r["id"] in alt and alt[r["id"]] != r["ampel"]]
    if aenderungen:
        zeilen.append("Ampel-Änderungen seit dem letzten Lauf:")
        zeilen += [f"• {r['name']}: {R.AMPEL.get(alt[r['id']], '?')} → {R.AMPEL[r['ampel']]}" for r in aenderungen]
    elif alt:
        zeilen.append("Keine Ampel-Änderungen seit dem letzten Lauf.")
    test_alt = []
    for i in daten["ideen"]:
        seit = _datum(i.get("status_seit"))
        if i["status"] == "test" and seit and (jetzt - seit).days > TEST_TAGE:
            test_alt.append((i["name"], (jetzt - seit).days))
    if test_alt:
        zeilen.append(f"Länger als {TEST_TAGE} Tage im Test – Zeit für eine Entscheidung:")
        zeilen += [f"• {n} ({t} Tage)" for n, t in test_alt]
    abbruch = [(r["name"], t) for r in rang if r["status"] != "verworfen" for t in r.get("abbruch") or []]
    if abbruch:
        zeilen.append("⚠️ Abbruch-Kriterium erreicht:")
        zeilen += [f"• {n}: {t}" for n, t in abbruch]
    zahlen = {"ideen": len(rang), "gruen": sum(1 for r in rang if r["ampel"] == "gruen"),
              "aenderungen": len(aenderungen), "test_alt": len(test_alt), "abbruch": len(abbruch)}
    return zeilen, ampeln, zahlen


def discord_senden(zeilen, url=None, post=requests.post):
    """-> Statustext fuer die App ("gesendet", "nicht eingerichtet", "Fehler ...")."""
    url = WEBHOOK if url is None else url
    if not url:
        return "nicht eingerichtet"
    text = "🎯 **EKS-Ideen – Monatsauswertung**\n" + "\n".join(zeilen)
    if len(text) > DISCORD_MAX:
        text = text[:DISCORD_MAX - 1] + "…"
    try:
        r = post(url, json={"content": text}, timeout=15)
        if r.status_code >= 300:
            return f"Fehler (HTTP {r.status_code})"
    except Exception as e:
        return f"Fehler ({type(e).__name__})"
    return "gesendet"


def dateien():
    """Haupt-Datei + die der Benutzer (state/benutzer/<name>/eks_ideen.json)."""
    try:
        benutzer = [p for p, _ in github_store._liste(REPO, config.GITHUB_STATE_BRANCH, "state/benutzer", TOKEN)
                    if p.endswith("/" + DATEI)]
    except Exception as e:                     # ohne Liste nur die Haupt-Datei
        log.warning(f"Benutzerordner nicht lesbar: {type(e).__name__}")
        benutzer = []
    return [HAUPT] + sorted(benutzer)


def main():
    if not (REPO and TOKEN):
        log.error("GITHUB_REPOSITORY / GH_STATE_TOKEN fehlen.")
        return 1
    jetzt = datetime.datetime.now()
    summe = {"dateien": 0, "ideen": 0, "gruen": 0, "aenderungen": 0, "test_alt": 0, "abbruch": 0}
    discord = "–"
    for pfad in dateien():
        try:
            roh, _ = github_store.lese_json(REPO, config.GITHUB_STATE_BRANCH, pfad, TOKEN, default=None)
        except Exception as e:
            log.warning(f"{pfad}: nicht lesbar ({type(e).__name__}) - übersprungen")
            continue
        if not isinstance(roh, dict) or not roh.get("ideen"):
            continue
        zeilen, ampeln, zahlen = zusammenfassung(roh, jetzt)
        if pfad == HAUPT:
            discord = discord_senden(zeilen)
            log.info(f"Discord: {discord}")
        lauf = {"stand": M.jetzt_iso(jetzt), "ampeln": ampeln, "text": zeilen,
                "discord": discord if pfad == HAUPT else "nur Haupt-Konto"}

        def aendern(alt, lauf=lauf):
            if not isinstance(alt, dict):
                return None                     # Datei inzwischen weg/kaputt - nichts schreiben
            neu = dict(alt)
            neu["letzter_lauf"] = lauf
            return neu
        ok, _ = github_store.aktualisiere_json(REPO, config.GITHUB_STATE_BRANCH, pfad, TOKEN, aendern,
                                               default=None, message="eks: monatslauf [skip ci]")
        log.info(f"Datei {summe['dateien'] + 1}: {zahlen['ideen']} Ideen, gespeichert: {ok}")
        summe["dateien"] += 1
        for k in ("ideen", "gruen", "aenderungen", "test_alt", "abbruch"):
            summe[k] += zahlen[k]
    bericht = (f"EKS-Monatslauf: {summe['dateien']} Bereiche, {summe['ideen']} Ideen, {summe['gruen']} auf Grün, "
               f"{summe['aenderungen']} Ampel-Änderungen, {summe['test_alt']} länger als {TEST_TAGE} Tage im Test, "
               f"{summe['abbruch']} Abbruch-Kriterien erreicht. "
               f"Discord: {discord}.")
    log.info(bericht)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(bericht + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
