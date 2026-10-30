"""Kurs-Agent: laedt alle Kurse, die die App anzeigt, im Hintergrund (GitHub Action alle 30 Min.) und legt sie
im Datenspeicher ab (Format: kurs_vorrat.py). Die App liest beim Seitenaufbau nur noch diese Dateien.

Welche Werte? Hauptposition und Standard-Vergleichswerte (config) sowie alle Kurs-IDs ("instrument_id") aus den
Dateien des Admins und aller Benutzer: Positionen, Beobachtung, Prognose-Basis, Vergleichswerte, Analyse-Depot,
Musterdepot, Planer-Szenarien, Portfolio Builder.

Portfolio-Planer: seine Werte stehen dort nur mit Ticker/ISIN. Der Agent sucht sie (Vorgaben aus planer_daten
und gespeicherte Planer-Szenarien), legt die Treffer in state/kurse/suche.json ab und laedt ihre Kurse mit.

Je Wert EIN Abruf bei ls-tc.de (Intraday + Tageshistorie). live.json wird jeden Lauf geschrieben, die
Historien-Teile nur, wenn sich etwas geaendert hat (meist einmal am Tag). Ein fehlgeschlagener Abruf behaelt den
alten Eintrag; ist eine Datei nicht lesbar, wird sie in diesem Lauf nicht ueberschrieben. Die Preisalarme
(discord_price_alert.py) und alle anderen Workflows bleiben unberuehrt.
"""
import datetime
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import requests

import config
import github_store
import kurs_vorrat as KV
import planer_daten
import portfolio_builder

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("kurse")

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GH_STATE_TOKEN", "")
BERLIN = ZoneInfo("Europe/Berlin")
PARALLEL = 6
DATEIEN = ("positionen.json", "beobachtung.json", "prognose_basis.json", "vergleichswerte.json",
           "analyse_depot.json", "musterdepot.json", "planer/szenarien.json", "portfolio_builder.json")


# ---------------------------------------------------------------------------
# Welche Kurse?
# ---------------------------------------------------------------------------
def ids_in(daten):
    """Alle Kurs-IDs ("instrument_id") in einer beliebig verschachtelten JSON-Struktur."""
    aus = set()
    if isinstance(daten, dict):
        for k, v in daten.items():
            if k == "instrument_id" and v not in (None, "") and str(v).strip().isdigit():
                aus.add(str(int(str(v).strip())))
            else:
                aus |= ids_in(v)
    elif isinstance(daten, list):
        for v in daten:
            aus |= ids_in(v)
    return aus


def suchbegriffe_in(daten):
    """Ticker und ISINs (Portfolio-Planer: Assets und Aktienkorb) in einer verschachtelten JSON-Struktur."""
    aus = set()
    if isinstance(daten, dict):
        for k, v in daten.items():
            if k in ("ticker", "isin") and isinstance(v, str) and v.strip():
                aus.add(v.strip())
            else:
                aus |= suchbegriffe_in(v)
    elif isinstance(daten, list):
        for v in daten:
            aus |= suchbegriffe_in(v)
    return aus


def builder_begriffe(daten):
    """Portfolio Builder: WKN/ISIN der Positionen ohne Kurs-ID (der Builder sucht sie beim Oeffnen)."""
    aus = set()
    for p in ((daten or {}).get("positionen") or []) if isinstance(daten, dict) else []:
        if isinstance(p, dict) and not p.get("instrument_id"):
            aus |= {str(p[k]).strip() for k in ("wkn", "isin") if p.get(k)}
    return aus


def grund_ids():
    ids = {str(config.LS_INSTRUMENT_ID)}
    ids |= {str(v) for v in (getattr(config, "BENCHMARKS", None) or {}).values()}
    return ids


def _lies(pfad):
    """-> (daten, ok). ok=False: nicht lesbar (Rate-Limit, Netz) - dann nicht ueberschreiben."""
    try:
        d, _ = github_store.lese_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, GITHUB_TOKEN, default=None)
        return d, True
    except github_store.LeseFehler as e:
        log.warning(f"{pfad} nicht lesbar: {e}")
        return None, False


def benoetigte_ids():
    """Kurs-IDs aus den Dateien des Admins (state/...) und aller Benutzer (state/benutzer/<name>/...)
    -> (ids, suchbegriffe des Portfolio-Planers)"""
    pfade = [f"state/{d}" for d in DATEIEN]
    try:
        benutzer = github_store._liste(GITHUB_REPO, config.GITHUB_STATE_BRANCH, "state/benutzer", GITHUB_TOKEN)
    except github_store.LeseFehler as e:
        log.warning(f"Benutzerordner nicht lesbar: {e}")
        benutzer = []
    for pfad, _ in benutzer:
        if any(pfad.endswith("/" + d) for d in DATEIEN):
            pfade.append(pfad)
    ids = grund_ids()
    begriffe = suchbegriffe_in([planer_daten.SEED_ASSETS, planer_daten.SEED_KORB])
    begriffe |= builder_begriffe(portfolio_builder.STANDARD)
    ids |= ids_in(portfolio_builder.STANDARD)
    for pfad in pfade:
        d, _ = _lies(pfad)
        ids |= ids_in(d)
        if pfad.endswith("planer/szenarien.json"):
            begriffe |= suchbegriffe_in(d)
        if pfad.endswith("portfolio_builder.json"):
            begriffe |= builder_begriffe(d)
    return ids, begriffe


def suchen(begriffe):
    """ls-tc-Suche fuer alle Begriffe. -> {begriff (klein): treffer} nur fuer erfolgreiche Abrufe."""
    def eins(b):
        try:
            r = requests.get(KV.SUCH_URL, params={"q": b, "localeId": "2"}, headers=config.LS_TC_HEADERS, timeout=10)
            r.raise_for_status()
            return b, KV.suche_auswerten(r.json())
        except Exception as e:
            log.warning(f"Suche {b} fehlgeschlagen: {type(e).__name__}")
            return b, None

    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        return {KV.such_schluessel(b): t for b, t in ex.map(eins, sorted(begriffe)) if t is not None}


def neue_suche(alt, gefunden, begriffe, stand):
    """Neue suche.json: frische Treffer, fuer fehlgeschlagene Suchen der alte Stand."""
    alte = (alt or {}).get("werte") or {}
    werte = {}
    for b in {KV.such_schluessel(x) for x in begriffe}:
        if b in gefunden:
            werte[b] = gefunden[b]
        elif b in alte:
            werte[b] = alte[b]
    return {"stand": stand, "werte": werte}


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------
def abrufen(instrument_id):
    """dataForInstrument (Intraday + Historie) fuer einen Wert; versucht notfalls einen zweiten Referer
    (Vergleichswerte/ETFs). Wirft bei Fehlern."""
    params = {"container": "chart1", "instrumentId": instrument_id, "marketId": "1", "quotetype": "mid",
              "series": "intraday,history", "type": "", "localeId": "2"}
    fehler = None
    for referer in (config.LS_TC_HEADERS.get("Referer"), f"https://www.ls-tc.de/de/etf/{instrument_id}"):
        try:
            r = requests.get(config.LS_TC_BASE_URL, params=params, timeout=10,
                             headers={**config.LS_TC_HEADERS, "Referer": referer})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            fehler = e
    raise fehler


def auswerten(antwort, jetzt_iso):
    """-> (live-Eintrag oder None, historie [[ts, schluss], ...] oder None)"""
    s = antwort.get("series") or {}
    intraday = (s.get("intraday") or {}).get("data") or (antwort.get("intraday") or {}).get("data") or []
    historie = (s.get("history") or {}).get("data") or (antwort.get("history") or {}).get("data") or []
    live = None
    gueltig = [x for x in intraday if isinstance(x, (list, tuple)) and len(x) >= 2 and x[1]]
    if gueltig:
        live = {"i": [list(gueltig[0][:2]), list(gueltig[-1][:2])], "p": config.extract_previous_close(antwort),
                "t": jetzt_iso}
    hist = [list(x[:2]) for x in historie if isinstance(x, (list, tuple)) and len(x) >= 2 and x[1]]
    return live, (hist or None)


def lauf(ids, jetzt=None):
    """Alle Werte abrufen. -> {id: (live, historie)} nur fuer erfolgreiche Abrufe."""
    jetzt_iso = (jetzt or datetime.datetime.now(BERLIN)).isoformat(timespec="seconds")
    ergebnis = {}

    def eins(iid):
        try:
            return iid, auswerten(abrufen(iid), jetzt_iso)
        except Exception as e:
            log.warning(f"Kurs {iid} nicht ladbar: {type(e).__name__}")
            return iid, None

    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        for iid, erg in ex.map(eins, sorted(ids)):
            if erg is not None:
                ergebnis[iid] = erg
    return ergebnis


# ---------------------------------------------------------------------------
# Zusammenfuehren und speichern
# ---------------------------------------------------------------------------
def neue_live(alt, ergebnis, ids, stand):
    """Neue live.json: frische Eintraege, fuer fehlgeschlagene der alte Stand; nur noch benoetigte Werte."""
    alte = (alt or {}).get("werte") or {}
    werte = {}
    for iid in ids:
        neu = (ergebnis.get(iid) or (None, None))[0]
        if neu is not None:
            werte[iid] = neu
        elif iid in alte:
            werte[iid] = alte[iid]
    return {"stand": stand, "werte": werte}


def neue_historie(alt, ergebnis, ids, stand):
    """Neuer Historien-Teil oder None, wenn sich nichts geaendert hat."""
    alte = (alt or {}).get("werte") or {}
    werte, geaendert = {}, False
    for iid in ids:
        neu = (ergebnis.get(iid) or (None, None))[1]
        if neu is not None:
            if (alte.get(iid) or {}).get("d") != neu:
                geaendert = True
                werte[iid] = {"d": neu, "t": stand}
            else:
                werte[iid] = alte[iid]
        elif iid in alte:
            werte[iid] = alte[iid]
    if set(werte) != set(alte):
        geaendert = True
    return {"stand": stand, "werte": werte} if geaendert else None


def _schreiben(pfad, daten, nachricht):
    ok = github_store.put_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, daten, GITHUB_TOKEN,
                               message=nachricht)
    if not ok:
        log.error(f"{pfad} konnte nicht gespeichert werden")
    return ok


def main():
    if not (GITHUB_REPO and GITHUB_TOKEN):
        log.error("GITHUB_REPOSITORY / GH_STATE_TOKEN fehlen")
        return 1
    ids, begriffe = benoetigte_ids()
    jetzt = datetime.datetime.now(BERLIN)
    stand = jetzt.isoformat(timespec="seconds")
    # Portfolio-Planer: Ticker/ISIN -> Kurs-ID (Suche), deren Kurse laedt der Lauf mit
    if begriffe:
        alt, ok = _lies(KV.PFAD_SUCHE)
        suche = neue_suche(alt if ok else None, suchen(begriffe), begriffe, stand)
        for b, treffer in suche["werte"].items():
            t = KV.bester_treffer(treffer, b)
            if t:
                ids.add(str(t["instrument_id"]))
        if ok:
            _schreiben(KV.PFAD_SUCHE, suche, "kurse suche [skip ci]")
    log.info(f"{len(ids)} Werte, {len(begriffe)} Suchbegriffe")
    ergebnis = lauf(ids, jetzt)
    log.info(f"{len(ergebnis)} von {len(ids)} Werten geladen")
    if not ergebnis:
        log.error("Kein einziger Kurs geladen - nichts gespeichert")
        return 1
    fehler = 0
    alt, ok = _lies(KV.PFAD_LIVE)
    if ok:
        fehler += not _schreiben(KV.PFAD_LIVE, neue_live(alt, ergebnis, ids, stand), "kurse live [skip ci]")
    for nr in range(KV.TEILE):
        pfad = KV.PFAD_HISTORIE.format(nr)
        teil_ids = {i for i in ids if KV.teil(i) == nr}
        alt, ok = _lies(pfad)
        if not ok:
            continue
        neu = neue_historie(alt, ergebnis, teil_ids, stand)
        if neu is not None:
            fehler += not _schreiben(pfad, neu, f"kurse historie {nr:02d} [skip ci]")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
