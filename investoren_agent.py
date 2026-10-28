"""Investoren-Checks fuer alle Aktien der Top-500-Liste vorberechnen (woechentlich, GitHub Action).

Die App liest nur die Ergebnisse (Legenden-Screener, Depot-Analyse) - schnell und ohne Yahoo-Limits beim Aufruf.
Rollierend wie der Qualitaets-Agent: je Lauf hoechstens INVESTOREN_MAX Werte (fehlende zuerst, dann die
aeltesten), mit Zeitbudget und Zwischenspeichern. Ein technischer Abruffehler ueberschreibt nie einen
vorhandenen Eintrag. Geschrieben wird nur auf den State-Branch (state/investoren/...), nichts anderes.

Ausgaben:
  state/investoren/ergebnis_NN.json   {stand, werte: {symbol: kurzform + {id, n, st}}}  (TEILE Dateien)
  state/investoren/meta.json          {stand, abdeckung, fue_median: {sektor: median}}
"""
import datetime
import os
import statistics
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed

import scoring as SC
import top50_agent as T
import investor_checks as IC
from investor_checks import abruf as AB
from investor_checks import fairer_wert as FW
from investor_checks import konsens as KO

log = T.log
TEILE = 16
STATE_ERGEBNIS = "state/investoren/ergebnis_{:02d}.json"
STATE_META = "state/investoren/meta.json"
MAX_ABRUFE = int(os.environ.get("INVESTOREN_MAX", "1500"))
ZEITBUDGET_SEK = float(os.environ.get("INVESTOREN_ZEITBUDGET_MIN", "150")) * 60
ALTER_TAGE = 7
PARALLEL = 3                      # gleichzeitige Aktien (je Aktie bis zu 4 Abrufe parallel)
SPEICHERN_NACH = 500
_uhr = time.monotonic             # in Tests ersetzbar


def teil(symbol):
    return zlib.crc32(symbol.encode()) % TEILE


def faellige(aktien, alte, heute, maximum):
    """Symbole in Abrufreihenfolge: ohne Eintrag zuerst (groesster Boersenwert zuerst - die bekannten Werte
    sind nach dem ersten Lauf da), dann aelter als ALTER_TAGE (aelteste zuerst)."""
    grenze = (heute - datetime.timedelta(days=ALTER_TAGE)).isoformat()

    def mcap(e):
        try:
            return float((e.get("info") or {}).get("mcap") or 0)
        except (TypeError, ValueError):
            return 0.0
    fehlt = [e["ticker"] for e in sorted(aktien, key=lambda e: -mcap(e)) if e["ticker"] not in alte]
    alt = sorted((alte[e["ticker"]].get("st") or "", e["ticker"]) for e in aktien
                 if e["ticker"] in alte and (alte[e["ticker"]].get("st") or "") < grenze)
    return (fehlt + [s for _, s in alt])[:maximum]


def fue_mediane(werte, min_n=5):
    """Sektor-Median der F&E-Quote (Philip Fisher) aus allen Ergebnissen mit Angabe."""
    je = {}
    for w in werte.values():
        if w.get("fue") is not None and w.get("sek"):
            je.setdefault(w["sek"], []).append(w["fue"])
    return {s: round(statistics.median(v), 2) for s, v in je.items() if len(v) >= min_n}


def bewerte(e, ver, vgl, fx, fue_median, index_cache, heute):
    """Eine Aktie: Abruf, alle Checks, Kurzform. -> Datensatz oder None (technischer Fehler / keine Daten)."""
    sym = e["ticker"]
    roh = AB.roh_laden(sym, parallel=4)
    if not roh.get("info") and len(roh.get("fehler") or []) >= 4:
        return None                                   # Abruf gescheitert - alter Eintrag bleibt
    kurse = AB.kurse_laden(sym, "5y")
    idx_sym, idx_name = AB.leitindex_fuer(roh)
    if idx_sym not in index_cache:
        index_cache[idx_sym] = AB.kurse_laden(idx_sym, "2y")
    f = AB.fakten(roh, kurse, index_cache[idx_sym], idx_name, fx, e)
    if not f.get("jahre") and not f.get("kurse"):
        return None
    kx = AB.kontext(e, ver, vgl, fue_median)
    erg = IC.alle_checks(f, kx)
    kf = KO.kurzform(erg, FW.uebersicht(f, kx), f)
    kf.update({"id": e["id"], "n": e["name"], "st": heute.isoformat()})
    return kf


def lade_teile():
    werte, status = {}, {}
    for i in range(TEILE):
        d, st = T.lade_state_geprueft(STATE_ERGEBNIS.format(i), {})
        status[i] = st
        werte.update((d or {}).get("werte") or {})
    return werte, status


def speichern(werte, status, heute):
    teile = {i: {} for i in range(TEILE)}
    for s, w in werte.items():
        teile[teil(s)][s] = w
    for i, inhalt in teile.items():
        if status.get(i) == "fehler":
            continue                                  # unlesbar -> nie mit Teilstand ueberschreiben
        T.speichere_state(STATE_ERGEBNIS.format(i), {"stand": heute.isoformat(), "werte": inhalt},
                          "investoren-checks [skip ci]")


def universum_laden():
    def teile_laden(muster, n):
        return [d for d in (T.lade_state(muster.format(i), None) for i in range(n)) if isinstance(d, dict)]
    kat = teile_laden("state/planer/katalog_gross_{}.json", 4)
    qual = teile_laden("state/qualitaet/alle_{}.json", 6)
    perf = teile_laden("state/top50_alle_{}.json", 4)
    det = teile_laden("state/qualitaet/details_{}.json", 32)
    yahoo = T.lade_state("state/top50_yahoo.json", {}) or {}
    fx = {k: v[1] for k, v in (T.lade_state("state/top50_fx.json", {}) or {}).items()
          if isinstance(v, (list, tuple)) and len(v) > 1}
    return SC.universum(kat, qual, perf, det, yahoo.get("isin") or {}), fx


def main():
    start = _uhr()
    heute = datetime.date.today()
    u, fx = universum_laden()
    if not u:
        log.error("Top-500-Daten nicht lesbar - Abbruch ohne zu schreiben.")
        return 1
    aktien = [e for e in u if e["art"] == "aktie" and e.get("ticker")]
    ver, vgl = SC.verteilungen(u), AB.vergleich(u)
    werte, status = lade_teile()
    meta = T.lade_state(STATE_META, {}) or {}
    fue = meta.get("fue_median") or fue_mediane(werte)
    plan = faellige(aktien, werte, heute, MAX_ABRUFE)
    je_sym = {e["ticker"]: e for e in aktien}
    log.info(f"Investoren-Checks: {len(aktien)} Aktien, {len(werte)} vorhanden, {len(plan)} fällig")
    index_cache, neu, fehler = {}, 0, 0
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        offen = {}
        it = iter(plan)
        for s in list(it)[:PARALLEL * 2]:
            offen[ex.submit(bewerte, je_sym[s], ver, vgl, fx, fue, index_cache, heute)] = s
        rest = plan[len(offen):]
        while offen:
            for fut in as_completed(list(offen)):
                s = offen.pop(fut)
                try:
                    r = fut.result()
                except Exception as e:                # ein Wert darf den Lauf nie abbrechen
                    log.warning(f"{s}: {type(e).__name__}: {e}")
                    r = None
                if r:
                    werte[s] = r
                    neu += 1
                    if neu % SPEICHERN_NACH == 0:
                        speichern(werte, status, heute)
                else:
                    fehler += 1
                if rest and _uhr() - start < ZEITBUDGET_SEK:
                    n = rest.pop(0)
                    offen[ex.submit(bewerte, je_sym[n], ver, vgl, fx, fue, index_cache, heute)] = n
                break
    speichern(werte, status, heute)
    T.speichere_state(STATE_META, {"stand": heute.isoformat(), "abdeckung": len(werte), "aktien": len(aktien),
                                   "fue_median": fue_mediane(werte)}, "investoren-checks meta [skip ci]")
    log.info(f"Fertig: {neu} neu bewertet, {fehler} ohne Ergebnis, {len(werte)} von {len(aktien)} vorhanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
