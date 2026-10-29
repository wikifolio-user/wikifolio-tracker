"""Kostenlose Quellen fuer die qualitative Analyse: SEC EDGAR (10-K, nur US-Firmen) und Wikidata (SPARQL).

SEC: offizielle API ohne Key. Pflicht ist ein User-Agent mit Name und E-Mail (Secret SEC_USER_AGENT) und
hoechstens 10 Anfragen je Sekunde - hier mit Mindestabstand (investor_config.SEC). Ohne SEC_USER_AGENT wird
SEC nicht abgefragt. Wikidata: oeffentlicher SPARQL-Endpunkt, ebenfalls mit beschreibendem User-Agent.
"""
import logging
import os
import threading
import time

import requests

import investor_config as C

SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_ARCHIV = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
WIKIDATA = "https://query.wikidata.org/sparql"

_lock = threading.Lock()
_letzter = [0.0]


def sec_user_agent():
    return (os.environ.get("SEC_USER_AGENT") or "").strip()


def _sec_get(url, ua, timeout=30):
    """GET mit Mindestabstand (SEC-Limit) und einem Wiederholversuch bei 429/5xx."""
    for versuch in range(3):
        with _lock:
            warte = C.SEC["min_abstand_sek"] - (time.monotonic() - _letzter[0])
            if warte > 0:
                time.sleep(warte)
            _letzter[0] = time.monotonic()
        try:
            r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
        except requests.RequestException as e:
            logging.warning("SEC %s: %s", url, type(e).__name__)
            time.sleep(2 * (versuch + 1))
            continue
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (versuch + 1))
            continue
        logging.warning("SEC %s: HTTP %s", url, r.status_code)
        return None
    return None


def sec_cik_tabelle(ua):
    """{TICKER: CIK} aller bei der SEC gemeldeten Firmen."""
    r = _sec_get(SEC_TICKER_URL, ua)
    if not r:
        return {}
    return {str(v.get("ticker", "")).upper(): int(v["cik_str"]) for v in (r.json() or {}).values()
            if v.get("ticker") and v.get("cik_str")}


def sec_letzter_10k(cik, ua):
    """Juengster 10-K (bzw. 20-F/40-F fuer Auslandsemittenten). -> {form, datum, acc, url} oder None"""
    r = _sec_get(SEC_SUBMISSIONS.format(cik=cik), ua)
    if not r:
        return None
    rec = ((r.json() or {}).get("filings") or {}).get("recent") or {}
    for i, form in enumerate(rec.get("form") or []):
        if form in ("10-K", "20-F", "40-F"):
            acc = rec["accessionNumber"][i]
            doc = rec["primaryDocument"][i]
            return {"form": form, "datum": rec["filingDate"][i], "acc": acc,
                    "url": SEC_ARCHIV.format(cik=cik, acc=acc.replace("-", ""), doc=doc)}
    return None


def sec_dokument(url, ua):
    r = _sec_get(url, ua, timeout=60)
    return r.text if r else None


def wikidata(cik=None, isin=None, ua=None):
    """Gruendungsjahr, Produkte, Tochterfirmen ueber CIK (P5531) oder ISIN (P946). -> dict oder None"""
    if not cik and not isin:
        return None
    bedingung = f'?firma wdt:P5531 "{int(cik):010d}" .' if cik else f'?firma wdt:P946 "{isin}" .'
    abfrage = f"""
SELECT ?firma ?firmaLabel ?gruendung
  (GROUP_CONCAT(DISTINCT ?produktLabel; separator="|") AS ?produkte)
  (GROUP_CONCAT(DISTINCT ?tochterLabel; separator="|") AS ?toechter) WHERE {{
  {bedingung}
  OPTIONAL {{ ?firma wdt:P571 ?gruendung . }}
  OPTIONAL {{ ?firma wdt:P1056 ?produkt . ?produkt rdfs:label ?produktLabel . FILTER(LANG(?produktLabel) = "en") }}
  OPTIONAL {{ ?firma wdt:P355 ?tochter . ?tochter rdfs:label ?tochterLabel . FILTER(LANG(?tochterLabel) = "en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}
}} GROUP BY ?firma ?firmaLabel ?gruendung LIMIT 1"""
    try:
        r = requests.get(WIKIDATA, params={"query": abfrage, "format": "json"},
                         headers={"User-Agent": ua or "FinanzDashboard/1.0 (privates Projekt)",
                                  "Accept": "application/sparql-results+json"}, timeout=30)
        if r.status_code != 200:
            return None
        zeilen = (r.json().get("results") or {}).get("bindings") or []
    except (requests.RequestException, ValueError) as e:
        logging.warning("Wikidata: %s", type(e).__name__)
        return None
    if not zeilen:
        return None
    z = zeilen[0]

    def w(k):
        return (z.get(k) or {}).get("value") or ""
    return {"qid": w("firma").rsplit("/", 1)[-1], "name": w("firmaLabel"), "gruendung": w("gruendung")[:4] or None,
            "produkte": [p for p in w("produkte").split("|") if p][:15],
            "toechter": [t for t in w("toechter").split("|") if t][:15]}
