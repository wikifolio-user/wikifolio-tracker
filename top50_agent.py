"""
Taeglicher Agent fuer die "Watchlist Top 50".

Laeuft per GitHub Actions (siehe .github/workflows/top50.yml), holt fuer alle
Werte aus top50_universum.py plus alle automatisch gefundenen wikifolios die
Kurshistorie von ls-tc.de, berechnet die Performance fuer 11 Zeitraeume und
schreibt je Kategorie und Zeitraum die 50 besten Werte nach
state/top50.json auf dem State-Branch. Die Streamlit-App liest nur diese
fertige Datei - sie muss also selbst nichts nachladen.

Ablauf:
  1. Instrument-IDs aufloesen (ISIN -> ID, ersatzweise Namenssuche).
     Ergebnis wird gecacht (state/top50_ids.json) - nur neue Werte kosten
     einen Suchaufruf.
  2. wikifolios entdecken: alle Zertifikate mit WKN "LS9..." ueber eine
     schrittweise verfeinerte Praefixsuche (die Suche liefert je Aufruf
     hoechstens 20 Treffer). Ergebnis wird 7 Tage gecacht.
  3. Indexlisten (S&P 500, MidCap 400, Russell 2000, MSCI Europe IMI, MSCI
     ACWI ex USA) woechentlich aus den iShares-Bestandslisten lesen; Kurse +
     Dividenden dieser Werte von Yahoo Finance (Heimatboerse), umgerechnet
     in Euro.
  4. Laufende Dividendenrendite (letzte 12 Monate / Kurs) fuer alle
     Kategorien mit "dividende" - bei den ls-tc-Werten ueber die ISIN bei
     Yahoo nachgeschlagen.
  5. Kurshistorie je Wert laden (parallel, gedrosselt).
  6. Performance je Zeitraum berechnen, Top 50 bilden, speichern.
"""
import bisect
import csv
import datetime
import io
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

import config
import github_store
from top50_universum import DIVIDENDEN_SCHLUESSEL, INDEX_FONDS, KATEGORIEN, TOP_N, ZEITRAEUME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("top50")

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GH_STATE_TOKEN", "")

SUCH_URL = "https://www.ls-tc.de/_rpc/json/.lstc/instrument/search/main"
STATE_TOP50 = "state/top50.json"
STATE_IDS = "state/top50_ids.json"
STATE_WIKIFOLIOS = "state/top50_wikifolios.json"
STATE_INDIZES = "state/top50_indizes.json"     # Mitgliederlisten der US-Indizes
STATE_YAHOO = "state/top50_yahoo.json"         # Symbol-Zuordnung + letzte Dividendenrenditen

SUCHE_MAX_TREFFER = 20        # Obergrenze der ls-tc-Suche je Aufruf (getestet)
WIKIFOLIO_CACHE_TAGE = 7      # Entdeckung nur woechentlich neu
MAX_ALTER_TAGE = 10           # Werte ohne Kurs seit >10 Tagen gelten als inaktiv
TOLERANZ_TAGE = 10            # Stichtag darf auf Wochenende/Feiertag fallen
PARALLEL = 6                  # gleichzeitige Abrufe
ANFRAGEN_PRO_SEKUNDE = 8      # Obergrenze gegenueber ls-tc.de - bewusst hoeflich
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

INDEX_CACHE_TAGE = 7          # Indexmitglieder nur woechentlich neu laden
YAHOO_PRO_SEKUNDE = 4         # Yahoo reagiert auf Massenabrufe mit 429 - vorsichtig
YAHOO_PARALLEL = 4
YAHOO_MAX_429_FOLGE = 40      # so viele 429 HINTEREINANDER = echte Sperre -> Yahoo fuer diesen
                              # Lauf aufgeben (Vortagesdaten bleiben); vereinzelte 429 sind normal
YAHOO_HISTORIE_TAGE = 3700    # gut 10 Jahre fuer die 10-Jahres-Liste
DIV_FENSTER_TAGE = 365        # "laufend" = Ausschuettungen der letzten 12 Monate
DIV_MAX_PROZENT = 30.0        # darueber fast sicher Sonderdividende/Datenfehler
DIV_CACHE_TAGE = 14           # Ersatzwert, falls Yahoo heute nicht antwortet
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
# Bevorzugte Yahoo-Boersenendung je ISIN-Land (Heimatboerse = Kurs und
# Dividende in derselben Waehrung)
YAHOO_ENDUNG = {"DE": ".DE", "FR": ".PA", "NL": ".AS", "BE": ".BR", "IT": ".MI", "ES": ".MC",
                "PT": ".LS", "GB": ".L", "CH": ".SW", "SE": ".ST", "NO": ".OL", "DK": ".CO",
                "FI": ".HE", "AT": ".VI", "JP": ".T", "AU": ".AX", "CA": ".TO", "HK": ".HK"}


# ---------------------------------------------------------------------------
# HTTP mit Drossel und Wiederholungen
# ---------------------------------------------------------------------------
class Drossel:
    """Begrenzt die Anfragerate ueber alle Threads hinweg."""
    def __init__(self, pro_sekunde):
        self.abstand = 1.0 / pro_sekunde
        self.naechster = 0.0
        self.lock = threading.Lock()

    def warten(self):
        with self.lock:
            jetzt = time.monotonic()
            warte = self.naechster - jetzt
            self.naechster = max(jetzt, self.naechster) + self.abstand
        if warte > 0:
            time.sleep(warte)


_drossel = Drossel(ANFRAGEN_PRO_SEKUNDE)
_lokal = threading.local()
ZAEHLER = {"anfragen": 0, "fehler": 0, "yahoo": 0, "yahoo_fehler": 0, "yahoo_429": 0,
           "yahoo_429_folge": 0}


def _session():
    if not hasattr(_lokal, "s"):
        _lokal.s = requests.Session()
        _lokal.s.headers.update(config.LS_TC_HEADERS)
    return _lokal.s


def hole_json(url, params):
    for versuch in range(3):
        _drossel.warten()
        ZAEHLER["anfragen"] += 1
        try:
            r = _session().get(url, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(5 * (versuch + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if versuch == 2:
                ZAEHLER["fehler"] += 1
                log.warning(f"Abruf fehlgeschlagen ({params}): {e}")
            time.sleep(1.5 * (versuch + 1))
    return None


# ---------------------------------------------------------------------------
# Suche und Aufloesung
# ---------------------------------------------------------------------------
def suche(begriff):
    daten = hole_json(SUCH_URL, {"q": begriff, "localeId": "2"})
    if isinstance(daten, dict):
        daten = daten.get("results") or daten.get("data", {}).get("results") or []
    treffer = []
    for e in daten or []:
        iid = e.get("instrumentId") or e.get("id")
        if iid:
            treffer.append({
                "id": int(iid),
                "name": e.get("displayname") or "",
                "wkn": str(e.get("wkn") or ""),
                "isin": e.get("isin") or "",
                "kategorie": e.get("categoryName") or "",
            })
    return treffer


def isin_gueltig(isin):
    """Prueft die ISIN-Pruefziffer (Luhn-Verfahren auf der Ziffernfolge)."""
    if not isin or len(isin) != 12 or not isin[:2].isalpha() or not isin[-1].isdigit():
        return False
    ziffern = "".join(str(int(c, 36)) for c in isin[:-1])
    summe = 0
    for i, z in enumerate(reversed(ziffern)):
        n = int(z) * (2 if i % 2 == 0 else 1)
        summe += n - 9 if n > 9 else n
    return (10 - summe % 10) % 10 == int(isin[-1])


def aufloesen(isin, name, erlaubt, cache):
    """ISIN -> Instrument. Zuerst exakt ueber die ISIN, sonst ueber den Namen
    (erster Treffer der erlaubten Kategorie - schuetzt z.B. davor, bei
    "Apple" die Anleihe statt der Aktie zu erwischen)."""
    if isin in cache:
        return cache[isin]
    ergebnis = None
    if isin_gueltig(isin):
        for t in suche(isin):
            if t["isin"] == isin and t["kategorie"] in erlaubt:
                ergebnis = t
                break
    if ergebnis is None:
        for t in suche(name):
            if t["kategorie"] in erlaubt:
                ergebnis = t
                log.info(f"{isin} ({name}) ueber Namenssuche gefunden: {t['isin']} {t['name']}")
                break
    if ergebnis:
        cache[isin] = {"id": ergebnis["id"], "wkn": ergebnis["wkn"], "isin": ergebnis["isin"]}
    return cache.get(isin)


def wikifolio_name(roh):
    """'Endlos-Zertifikat bezogen auf LUS Wikifolio-Index Pretty' -> 'Pretty'"""
    n = re.sub(r"^Endlos-Zertifikat bezogen auf\s*(LUS\s*)?Wikifolio(-Index)?\s*", "",
               roh or "", flags=re.I)
    n = re.sub(r"\s+Index$", "", n, flags=re.I)
    return n.strip() or roh


def wikifolios_entdecken():
    """Findet alle wikifolio-Zertifikate ueber die WKN-Praefixsuche.

    Die Suche liefert je Aufruf hoechstens 20 Treffer. Liefert ein Praefix
    genau diese Obergrenze, gibt es womoeglich mehr - dann wird es um jedes
    Zeichen verlaengert und erneut gesucht (LS9 -> LS9V -> LS9VA ...), bis
    jede Teilsuche vollstaendig ist. Ebenenweise, damit parallel gesucht
    werden kann."""
    gefunden = {}
    ebene = ["LS9"]
    with ThreadPoolExecutor(PARALLEL) as pool:
        while ebene:
            naechste = []
            for praefix, treffer in zip(ebene, pool.map(suche, ebene)):
                for t in treffer:
                    if t["kategorie"] == "Wikifolio" and t["wkn"].startswith("LS9"):
                        gefunden[t["id"]] = [t["id"], t["wkn"], wikifolio_name(t["name"]), t["isin"]]
                if len(treffer) >= SUCHE_MAX_TREFFER and len(praefix) < 6:
                    naechste += [praefix + c for c in ALPHABET]
            log.info(f"wikifolio-Suche: {len(ebene)} Praefixe durchsucht, "
                     f"bisher {len(gefunden)} gefunden, naechste Ebene {len(naechste)}")
            ebene = naechste
    return list(gefunden.values())


# ---------------------------------------------------------------------------
# Kurshistorie und Performance
# ---------------------------------------------------------------------------
def historie(instrument_id):
    params = {"container": "chart1", "instrumentId": instrument_id, "marketId": "1",
              "quotetype": "mid", "series": "history", "type": "", "localeId": "2"}
    roh = hole_json(config.LS_TC_BASE_URL, params)
    if not roh:
        return []
    daten = (roh.get("series", {}).get("history", {}).get("data")
             or roh.get("history", {}).get("data") or [])
    punkte = {}
    for ts, kurs in daten:
        try:
            kurs = float(kurs)
        except (TypeError, ValueError):
            continue
        if kurs > 0:
            tag = datetime.datetime.fromtimestamp(ts / 1000, ZoneInfo("Europe/Berlin")).date()
            punkte[tag] = kurs            # je Tag nur der letzte Wert
    reihe = sorted(punkte.items())
    return bereinigen(reihe)


def bereinigen(reihe):
    """Entfernt einzelne Ausreisser-Punkte (Datenfehler der Quelle): ein Kurs,
    der gegenueber BEIDEN Nachbarn um mehr als Faktor 3 abweicht, ist mit
    hoher Sicherheit ein Uebertragungsfehler - echte Kurssprünge bleiben
    stehen, weil der Folgekurs dort auf dem neuen Niveau liegt."""
    if len(reihe) < 3:
        return reihe
    sauber = [reihe[0]]
    for i in range(1, len(reihe) - 1):
        vor, akt, nach = reihe[i - 1][1], reihe[i][1], reihe[i + 1][1]
        spitze = (akt / vor > 3 and akt / nach > 3) or (akt / vor < 1 / 3 and akt / nach < 1 / 3)
        if not spitze:
            sauber.append(reihe[i])
    sauber.append(reihe[-1])
    return sauber


def performance(reihe, heute):
    """{Zeitraum: Prozent oder None}. Leer, wenn der Wert nicht mehr aktiv
    gehandelt wird (letzter Kurs aelter als MAX_ALTER_TAGE) - sonst wuerden
    eingefrorene Kurse delisteter Werte die Ranglisten verfaelschen."""
    if len(reihe) < 2:
        return {}
    letzter_tag, letzter = reihe[-1]
    if (heute - letzter_tag).days > MAX_ALTER_TAGE:
        return {}
    ergebnis = {"_kurs": letzter, "_stand": letzter_tag.isoformat()}
    tage_liste = [t for t, _ in reihe]
    for schluessel, _, tage in ZEITRAEUME:
        if schluessel == "1T":
            ref = reihe[-2][1]
        else:
            stichtag = letzter_tag - datetime.timedelta(days=tage)
            # letzter Kurs am oder vor dem Stichtag (Binaersuche)
            lo, hi = 0, len(tage_liste) - 1
            pos = -1
            while lo <= hi:
                mitte = (lo + hi) // 2
                if tage_liste[mitte] <= stichtag:
                    pos, lo = mitte, mitte + 1
                else:
                    hi = mitte - 1
            if pos < 0 or (stichtag - tage_liste[pos]).days > TOLERANZ_TAGE:
                ergebnis[schluessel] = None      # Historie reicht nicht so weit
                continue
            ref = reihe[pos][1]
        ergebnis[schluessel] = round((letzter / ref - 1) * 100, 2) if ref > 0 else None
    return ergebnis


# ---------------------------------------------------------------------------
# Yahoo Finance: US-Indexwerte (Kurse) und Dividenden aller Aktien
# ---------------------------------------------------------------------------
_yahoo_drossel = Drossel(YAHOO_PRO_SEKUNDE)
_yahoo_pause = {"bis": 0.0}
_yahoo_lock = threading.Lock()


_yahoo_s = {"session": None, "crumb": None, "crumb_versucht": False}


def _yahoo_session():
    """EINE gemeinsame Session fuer alle Threads: Yahoo bindet den Crumb an
    die Cookies - getrennte Sessions je Thread wuerden nicht zusammenpassen."""
    with _yahoo_lock:
        if _yahoo_s["session"] is None:
            s = requests.Session()
            s.headers.update({"User-Agent": BROWSER_UA, "Accept": "application/json,text/plain,*/*",
                              "Accept-Language": "en-US,en;q=0.9"})
            try:                   # setzt die Yahoo-Cookies - ohne gibt es eher 429
                s.get("https://fc.yahoo.com", timeout=10)
            except Exception:
                pass
            _yahoo_s["session"] = s
        return _yahoo_s["session"]


def yahoo_crumb(neu=False):
    """Crumb fuer die Endpunkte, die ihn verlangen (Kursuebersicht,
    Analystenschaetzungen). None, wenn Yahoo keinen ausgibt."""
    s = _yahoo_session()
    with _yahoo_lock:
        if neu:
            _yahoo_s["crumb"], _yahoo_s["crumb_versucht"] = None, False
        if not _yahoo_s["crumb_versucht"]:
            _yahoo_s["crumb_versucht"] = True
            for host in ("query1", "query2"):
                try:
                    r = s.get(f"https://{host}.finance.yahoo.com/v1/test/getcrumb", timeout=15)
                    text = (r.text or "").strip()
                    if r.status_code == 200 and text and len(text) < 64 and "<" not in text:
                        _yahoo_s["crumb"] = text
                        break
                except Exception:
                    pass
            if not _yahoo_s["crumb"]:
                log.warning("Yahoo-Crumb nicht erhalten - Analystendaten fehlen heute.")
        return _yahoo_s["crumb"]


def yahoo_aufgegeben():
    return ZAEHLER["yahoo_429_folge"] >= YAHOO_MAX_429_FOLGE


def yahoo_json(pfad, params, crumb=False):
    """GET gegen Yahoo, abwechselnd query1/query2. Bei 429 legt ein
    gemeinsamer Zeitstempel ALLE Threads kurz schlafen, statt dass jeder fuer
    sich weiter anklopft. crumb=True haengt den Sitzungs-Crumb an."""
    if crumb:
        c = yahoo_crumb()
        if not c:
            return None
        params = {**params, "crumb": c}
    for versuch in range(4):
        if yahoo_aufgegeben():
            return None
        warte = _yahoo_pause["bis"] - time.monotonic()
        if warte > 0:
            time.sleep(warte)
        _yahoo_drossel.warten()
        ZAEHLER["yahoo"] += 1
        host = "query1" if versuch % 2 == 0 else "query2"
        try:
            r = _yahoo_session().get(f"https://{host}.finance.yahoo.com{pfad}", params=params, timeout=20)
            if r.status_code == 429:
                with _yahoo_lock:
                    ZAEHLER["yahoo_429"] += 1
                    ZAEHLER["yahoo_429_folge"] += 1
                    if ZAEHLER["yahoo_429_folge"] == YAHOO_MAX_429_FOLGE:
                        log.error("Yahoo sperrt dauerhaft - breche Yahoo-Abrufe fuer heute ab.")
                    _yahoo_pause["bis"] = max(_yahoo_pause["bis"], time.monotonic() + 15 * (versuch + 1))
                continue
            ZAEHLER["yahoo_429_folge"] = 0         # Antwort ohne Sperre
            if r.status_code == 404:
                return None                         # Symbol unbekannt - kein Wiederholen
            if r.status_code == 401 and crumb and versuch == 0:
                c = yahoo_crumb(neu=True)           # Crumb abgelaufen -> einmal erneuern
                if not c:
                    return None
                params = {**params, "crumb": c}
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if versuch == 3:
                log.warning(f"Yahoo-Abruf fehlgeschlagen ({pfad}): {e}")
            time.sleep(1.5 * (versuch + 1))
    ZAEHLER["yahoo_fehler"] += 1
    return None


def _tag(ts, versatz):
    return datetime.datetime.fromtimestamp(int(ts) + int(versatz or 0), datetime.timezone.utc).date()


def yahoo_chart(symbol, tage, intervall="1d"):
    """Tageskurse (nicht dividendenbereinigt - wie bei ls-tc reine
    Kursperformance) plus Dividendenzahlungen eines Yahoo-Symbols."""
    jetzt = int(time.time())
    daten = yahoo_json(f"/v8/finance/chart/{quote(symbol)}", {
        "period1": jetzt - tage * 86400, "period2": jetzt + 86400,
        "interval": intervall, "events": "div", "includePrePost": "false"})
    ergebnis = ((daten or {}).get("chart") or {}).get("result") or []
    if not ergebnis:
        return None
    r0 = ergebnis[0]
    meta = r0.get("meta") or {}
    versatz = meta.get("gmtoffset") or 0
    kurse = (((r0.get("indicators") or {}).get("quote") or [{}])[0] or {}).get("close") or []
    punkte = {}
    for ts, kurs in zip(r0.get("timestamp") or [], kurse):
        try:
            kurs = float(kurs)
        except (TypeError, ValueError):
            continue
        if kurs > 0:
            punkte[_tag(ts, versatz)] = kurs
    divs = []
    for ts, d in ((r0.get("events") or {}).get("dividends") or {}).items():
        try:
            betrag = float((d or {}).get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if betrag > 0:
            divs.append((_tag((d or {}).get("date") or ts, versatz), betrag))
    if not punkte:
        return None
    return {"reihe": sorted(punkte.items()), "divs": sorted(divs),
            "waehrung": meta.get("currency") or "",
            "name": meta.get("longName") or meta.get("shortName") or ""}


def dividendenrendite(chart):
    """Laufende Dividendenrendite in % = Ausschuettungen der letzten 12 Monate
    / letzter Kurs (beides in der Waehrung der Heimatboerse). 0.0 = zahlt
    keine Dividende, None = nicht bestimmbar/unplausibel."""
    if not chart or not chart["reihe"]:
        return None
    letzter_tag, kurs = chart["reihe"][-1]
    divs = chart["divs"]
    summe = sum(b for t, b in divs if 0 <= (letzter_tag - t).days < DIV_FENSTER_TAGE)
    if summe == 0:
        # Jaehrliche Zahler: Termin kann sich um einige Tage nach hinten
        # verschieben - dann liegt die letzte Zahlung knapp vor dem Fenster
        summe = sum(b for t, b in divs if 0 <= (letzter_tag - t).days < DIV_FENSTER_TAGE + 35)
    if kurs <= 0:
        return None
    rendite = summe / kurs * 100
    # Londoner Werte: Yahoo nennt Kurse in Pence (GBp), Dividenden teils in Pfund
    if chart["waehrung"] in ("GBp", "GBX") and 0 < rendite < 0.3:
        rendite *= 100
    if rendite > DIV_MAX_PROZENT:
        return None
    return round(rendite, 2)


def yahoo_symbol_suchen(begriff, land="", endung=None):
    """Sucht das Yahoo-Symbol der Heimatboerse zu ISIN oder Name. endung
    erzwingt eine Boerse (".T", ".L" ...; "" = US-Listing)."""
    daten = yahoo_json("/v1/finance/search", {"q": begriff, "quotesCount": 10, "newsCount": 0,
                                               "listsCount": 0, "enableFuzzyQuery": "false"})
    kandidaten = [q.get("symbol") for q in (daten or {}).get("quotes") or []
                  if q.get("quoteType") == "EQUITY" and q.get("symbol")]
    if not kandidaten:
        return None
    if endung is None:
        endung = YAHOO_ENDUNG.get(land)
    if endung:
        return next((sym for sym in kandidaten if sym.endswith(endung)), None)
    if endung == "":
        return next((sym for sym in kandidaten if "." not in sym), None)
    for sym in kandidaten:
        if "." not in sym:                 # US-Heimatlisting
            return sym
    return kandidaten[0]


# ---------------------------------------------------------------------------
# Waehrungen: alles in Euro
# ---------------------------------------------------------------------------
# Unterwaehrungen (Pence, Agorot, Cent): fuer die PERFORMANCE spielt der
# konstante Faktor 100 keine Rolle - es zaehlt nur die Kursbewegung der
# Hauptwaehrung.
HAUPTWAEHRUNG = {"GBp": "GBP", "GBX": "GBP", "ILA": "ILS", "ZAc": "ZAR", "ZAC": "ZAR", "KWF": "KWD"}
_fx_cache = {}
_fx_lock = threading.Lock()


def fx_reihe(waehrung):
    """Tagesreihe 'Einheiten der Waehrung je 1 EUR' (Yahoo 'EURxxx=X').
    None = Euro (keine Umrechnung), False = nicht ladbar."""
    w = HAUPTWAEHRUNG.get(waehrung, (waehrung or "").upper())
    if w in ("", "EUR"):
        return None
    with _fx_lock:
        if w not in _fx_cache:
            chart = yahoo_chart(f"EUR{w}=X", YAHOO_HISTORIE_TAGE + 30)
            _fx_cache[w] = ([t for t, _ in chart["reihe"]], [k for _, k in chart["reihe"]]) if chart else False
            if not chart:
                log.warning(f"Wechselkurs EUR/{w} nicht ladbar - Werte in {w} fehlen heute.")
        return _fx_cache[w]


def in_euro(reihe, fx):
    """Rechnet eine Kursreihe mit dem Wechselkurs des jeweiligen Tages (bzw.
    des letzten Tages davor) in Euro um."""
    tage, kurse = fx
    ergebnis = []
    for tag, kurs in reihe:
        pos = bisect.bisect_right(tage, tag) - 1
        if pos >= 0 and (tag - tage[pos]).days <= TOLERANZ_TAGE and kurse[pos] > 0:
            ergebnis.append((tag, kurs / kurse[pos]))
    return ergebnis


# ---------------------------------------------------------------------------
# Mitgliederlisten der Indizes und Yahoo-Symbole
# ---------------------------------------------------------------------------
# Boerse (Spalte "Exchange" der iShares-Liste) -> Yahoo-Endung. Stichwort-
# suche, Reihenfolge wichtig (spezifisch vor allgemein).
BOERSE_ENDUNG = [
    ("shanghai", ".SS"), ("shenzhen", ".SZ"), ("hong kong", ".HK"), ("tokyo", ".T"),
    ("kosdaq", ".KQ"), ("korea", ".KS"), ("gretai", ".TWO"), ("taipei exchange", ".TWO"),
    ("taiwan", ".TW"), ("national stock exchange of india", ".NS"), ("bombay", ".BO"),
    ("london", ".L"), ("xetra", ".DE"), ("deutsche b", ".DE"), ("frankfurt", ".DE"),
    ("paris", ".PA"), ("amsterdam", ".AS"), ("brussels", ".BR"), ("lisbon", ".LS"),
    ("irish", ".IR"), ("dublin", ".IR"), ("swiss", ".SW"), ("helsinki", ".HE"),
    ("copenhagen", ".CO"), ("stockholm", ".ST"), ("oslo", ".OL"), ("italiana", ".MI"),
    ("milan", ".MI"), ("madrid", ".MC"), ("wiener", ".VI"), ("vienna", ".VI"),
    ("warsaw", ".WA"), ("athens", ".AT"), ("budapest", ".BD"), ("prague", ".PR"),
    ("toronto", ".TO"), ("tsx venture", ".V"), ("asx", ".AX"), ("australian", ".AX"),
    ("sao paulo", ".SA"), ("bovespa", ".SA"), ("b3 s.a", ".SA"), ("mexicana", ".MX"),
    ("johannesburg", ".JO"), ("singapore", ".SI"), ("tel aviv", ".TA"), ("saudi", ".SR"),
    ("thailand", ".BK"), ("bursa malaysia", ".KL"), ("indonesia", ".JK"),
    ("new zealand", ".NZ"), ("istanbul", ".IS"), ("santiago", ".SN"), ("philippine", ".PS"),
    ("qatar", ".QA"), ("kuwait", ".KW"), ("egypt", ".CA"), ("colombia", ".CL"),
    ("lima", ".LM"), ("abu dhabi", ".AE"), ("dubai", ".AE"),
    ("new york", ""), ("nyse", ""), ("cboe", ""), ("bats", ""), ("nasdaq", ""),
]
# Ersatz ueber das Sitzland, wenn die Boerse unbekannt/mehrdeutig ist
# (z.B. "Nasdaq Omx Nordic" = Stockholm, Kopenhagen oder Helsinki)
LAND_ENDUNG = {
    "United States": "", "United Kingdom": ".L", "Germany": ".DE", "France": ".PA",
    "Netherlands": ".AS", "Belgium": ".BR", "Portugal": ".LS", "Ireland": ".IR",
    "Switzerland": ".SW", "Finland": ".HE", "Denmark": ".CO", "Sweden": ".ST",
    "Norway": ".OL", "Italy": ".MI", "Spain": ".MC", "Austria": ".VI", "Poland": ".WA",
    "Greece": ".AT", "Japan": ".T", "Korea (South)": ".KS", "Taiwan": ".TW", "India": ".NS",
    "Hong Kong": ".HK", "Canada": ".TO", "Australia": ".AX", "Brazil": ".SA", "Mexico": ".MX",
    "South Africa": ".JO", "Singapore": ".SI", "Israel": ".TA", "Saudi Arabia": ".SR",
    "Thailand": ".BK", "Malaysia": ".KL", "Indonesia": ".JK", "New Zealand": ".NZ",
    "Turkey": ".IS", "Chile": ".SN", "Philippines": ".PS", "Qatar": ".QA", "Kuwait": ".KW",
    "Egypt": ".CA", "Colombia": ".CL", "Peru": ".LM", "United Arab Emirates": ".AE",
}


def yahoo_endung(boerse, standort):
    b = (boerse or "").lower()
    if "nordic" in b or "omx" in b:                    # Land entscheidet
        return LAND_ENDUNG.get(standort, ".ST")
    for stichwort, endung in BOERSE_ENDUNG:
        if stichwort in b:
            return endung
    return LAND_ENDUNG.get(standort, "")


def yahoo_symbol(ticker, boerse="", standort="United States"):
    """iShares-Ticker -> Yahoo-Symbol der Heimatboerse:
    'BRK.B' -> 'BRK-B', 'BP.' (London) -> 'BP.L', '700' (HK) -> '0700.HK',
    'VOLV B' (Stockholm) -> 'VOLV-B.ST', '5930' (Korea) -> '005930.KS'."""
    endung = yahoo_endung(boerse, standort)
    t = ticker.strip().upper().rstrip(".*").strip()
    if endung == ".HK" and t.isdigit():
        t = t.zfill(4)
    elif endung in (".KS", ".KQ", ".SS", ".SZ") and t.isdigit():
        t = t.zfill(6)
    t = re.sub(r"[./ ]+", "-", t).strip("-")
    return t + endung, endung


def ishares_mitglieder(fonds):
    """Liest die Bestandsliste eines iShares-ETFs (CSV mit einigen Kopfzeilen
    vor der eigentlichen Tabelle). Nur Aktien - Cash, Futures und
    Geldmarktfonds fallen raus. Eintrag: [Ticker, Name, Boerse, Sitzland, Sektor]."""
    try:
        r = requests.get(INDEX_FONDS[fonds]["url"], timeout=60,
                         headers={"User-Agent": BROWSER_UA, "Accept": "text/csv,*/*"})
        r.raise_for_status()
    except Exception as e:
        log.warning(f"iShares-Liste {fonds} nicht ladbar: {e}")
        return []
    zeilen = r.content.decode("utf-8-sig", errors="replace").splitlines()
    kopf = next((i for i, z in enumerate(zeilen) if z.replace('"', "").startswith("Ticker,")), None)
    if kopf is None:
        log.warning(f"iShares-Liste {fonds}: keine Tabelle gefunden (Format geaendert?)")
        return []
    mitglieder = []
    for z in csv.DictReader(io.StringIO("\n".join(zeilen[kopf:]))):
        ticker = (z.get("Ticker") or "").strip()
        klasse = (z.get("Asset Class") or "").strip().lower()
        if not ticker or klasse != "equity" or not re.fullmatch(r"[A-Z0-9./ &*\-]{1,15}", ticker):
            continue
        name = re.sub(r"\s+", " ", (z.get("Name") or ticker).strip())
        mitglieder.append([ticker, name, (z.get("Exchange") or "").strip(),
                           (z.get("Location") or "").strip(), (z.get("Sector") or "").strip()])
    log.info(f"iShares {fonds}: {len(mitglieder)} Aktien")
    return mitglieder


def nasdaq_filter(von, bis):
    """Ersatzquelle fuer US-Listen, falls iShares ausfaellt und noch keine
    Liste gespeichert ist: alle US-Aktien der Nasdaq-Uebersicht im
    Boersenwert-Bereich."""
    try:
        r = requests.get("https://api.nasdaq.com/api/screener/stocks",
                         params={"tableonly": "true", "limit": "10000", "offset": "0", "download": "true"},
                         headers={"User-Agent": BROWSER_UA, "Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        zeilen = ((r.json().get("data") or {}).get("rows")) or []
    except Exception as e:
        log.warning(f"Nasdaq-Aktienfilter nicht ladbar: {e}")
        return []
    mitglieder = []
    for z in zeilen:
        sym = (z.get("symbol") or "").strip()
        try:
            wert = float(str(z.get("marketCap") or "0").replace(",", "") or 0)
        except ValueError:
            continue
        if (re.fullmatch(r"[A-Z]{1,5}", sym) and (z.get("country") or "") == "United States"
                and wert >= von and (bis is None or wert < bis)):
            mitglieder.append([sym, (z.get("name") or sym).strip(), "NASDAQ", "United States",
                               (z.get("sector") or "").strip()])
    log.info(f"Nasdaq-Filter {von:.0e}-{bis or 'max'}: {len(mitglieder)} Aktien")
    return mitglieder


def index_mitglieder(kat, cache, heute):
    """Mitglieder einer Index-Kategorie; je Fonds woechentlich neu, sonst aus
    dem Cache. Gibt ([(ticker, name, boerse, standort, sektor)], quellen_hinweis)."""
    alle, hinweise = {}, []
    ohne = kat.get("ohne_standorte") or set()
    for fonds in kat["indizes"]:
        eintrag = cache.get(fonds) or {}
        try:
            alter = (heute - datetime.date.fromisoformat(eintrag.get("stand", "2000-01-01"))).days
        except Exception:
            alter = 9999
        if not eintrag.get("liste") or alter >= INDEX_CACHE_TAGE:
            neu = ishares_mitglieder(fonds)
            if len(neu) >= 50:
                eintrag = {"stand": heute.isoformat(), "liste": neu, "quelle": "iShares"}
                cache[fonds] = eintrag
            elif eintrag.get("liste"):
                log.warning(f"{fonds}: nutze gespeicherte Liste vom {eintrag.get('stand')}")
        if eintrag.get("liste"):
            hinweise.append(f"{INDEX_FONDS[fonds]['titel']} (Stand {eintrag.get('stand')})")
            for e in eintrag["liste"]:
                ticker, name = e[0], e[1]
                boerse = e[2] if len(e) > 2 else ""
                standort = e[3] if len(e) > 3 else "United States"
                sektor = e[4] if len(e) > 4 else ""
                if standort in ohne:
                    continue
                symbol, _ = yahoo_symbol(ticker, boerse, standort)
                alle.setdefault(symbol, (ticker, name, boerse, standort, sektor))
    if not alle and kat.get("ersatz_boersenwert"):
        von, bis = kat["ersatz_boersenwert"]
        for ticker, name, boerse, standort, sektor in nasdaq_filter(von, bis):
            alle.setdefault(ticker, (ticker, name, boerse, standort, sektor))
        if alle:
            hinweise.append("Ersatz: Nasdaq-Filter nach Börsenwert (iShares nicht erreichbar)")
    return [alle[k] for k in sorted(alle)], hinweise


def schoener_name(name):
    """'SUPER MICRO COMPUTER INC' -> 'Super Micro Computer Inc', Kuerzel wie
    'BP PLC' / 'SAP SE' bleiben gross."""
    if not name or not name.isupper():
        return name
    klein = {"INC", "CORP", "LTD", "CO", "THE", "AND", "OF", "DE", "LA", "DI", "DER", "NEW", "ONE"}
    return " ".join(w if len(w) <= 3 and w not in klein else w.capitalize() for w in name.split())


def lade_indexwert(ticker, name, boerse, standort, ymap):
    """Kurshistorie (in EUR) + Dividendenrendite eines Indexwerts.
    Unbekanntes Symbol -> einmalige Namenssuche bei Yahoo an derselben
    Boerse, Treffer wird gemerkt (ymap)."""
    standard, endung = yahoo_symbol(ticker, boerse, standort)
    gemerkt = ymap.setdefault("ticker", {})
    symbol = gemerkt.get(standard) or standard
    chart = yahoo_chart(symbol, YAHOO_HISTORIE_TAGE)
    if chart is None and not yahoo_aufgegeben() and standard not in gemerkt:
        gefunden = yahoo_symbol_suchen(schoener_name(name), endung=endung)
        if gefunden and gefunden != symbol:
            chart = yahoo_chart(gefunden, YAHOO_HISTORIE_TAGE)
            if chart:
                gemerkt[standard] = gefunden
                symbol = gefunden
    if chart is None:
        return symbol, None, None, name
    fx = fx_reihe(chart["waehrung"])
    if fx is False:
        return symbol, None, None, name                # Waehrung nicht umrechenbar
    reihe = in_euro(chart["reihe"], fx) if fx else chart["reihe"]
    anzeige = schoener_name(chart["name"] or name)
    return symbol, bereinigen(reihe), dividendenrendite(chart), anzeige


def lade_dividende_isin(isin, name, ymap):
    """Dividendenrendite einer ls-tc-Aktie ueber ihr Yahoo-Symbol."""
    zuordnung = ymap.setdefault("isin", {})
    symbol = zuordnung.get(isin)
    if symbol is None:                                 # noch nie gesucht
        symbol = yahoo_symbol_suchen(isin, isin[:2]) or yahoo_symbol_suchen(name, isin[:2]) or ""
        if symbol or not yahoo_aufgegeben():
            zuordnung[isin] = symbol                   # "" = bei Yahoo nicht vorhanden
    if not symbol:
        return None
    return dividendenrendite(yahoo_chart(symbol, DIV_FENSTER_TAGE * 2 + 60))


# ---------------------------------------------------------------------------
# Hauptablauf
# ---------------------------------------------------------------------------
def lade_state(pfad, standard):
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return standard
    daten, _ = github_store.get_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad,
                                     GITHUB_TOKEN, default=standard)
    return daten if daten is not None else standard


def speichere_state(pfad, daten, nachricht):
    if not (GITHUB_REPO and GITHUB_TOKEN):
        log.warning(f"Kein GitHub-Zugang - {pfad} wird nicht gespeichert.")
        return False
    return github_store.put_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, daten,
                                 GITHUB_TOKEN, message=nachricht)


def main():
    start = time.monotonic()
    jetzt = datetime.datetime.now(ZoneInfo("Europe/Berlin"))
    heute = jetzt.date()
    vorher = lade_state(STATE_TOP50, {}) or {}

    # 1) Instrument-IDs der festen Listen aufloesen (gecacht)
    id_cache = lade_state(STATE_IDS, {}) or {}
    anzahl_vorher = len(id_cache)
    mitglieder = {}             # kategorie -> [(schluessel, name, wkn/symbol, isin)]
    nicht_gefunden = []
    for key, kat in KATEGORIEN.items():
        if not isinstance(kat["quelle"], list):
            continue
        eintraege = kat["quelle"]
        with ThreadPoolExecutor(PARALLEL) as pool:
            aufgeloest = list(pool.map(
                lambda e: aufloesen(e[0], e[1], kat["kategorien_ls"], id_cache), eintraege))
        liste, gesehen = [], set()
        for (isin, name), info in zip(eintraege, aufgeloest):
            if not info:
                nicht_gefunden.append({"kategorie": kat["titel"], "isin": isin, "name": name})
                continue
            if info["id"] in gesehen:
                continue
            gesehen.add(info["id"])
            liste.append((info["id"], name, info["wkn"], info["isin"]))
        mitglieder[key] = liste
        log.info(f"{kat['titel']}: {len(liste)} von {len(eintraege)} aufgeloest")
    if len(id_cache) != anzahl_vorher:
        speichere_state(STATE_IDS, id_cache, "top50: id-cache [skip ci]")

    # 2) wikifolios entdecken (woechentlich)
    wiki = lade_state(STATE_WIKIFOLIOS, {}) or {}
    try:
        alter = (heute - datetime.date.fromisoformat(wiki.get("stand", "2000-01-01"))).days
    except Exception:
        alter = 9999
    if not wiki.get("liste") or alter >= WIKIFOLIO_CACHE_TAGE:
        log.info("Suche wikifolios neu ...")
        liste = wikifolios_entdecken()
        if liste:
            wiki = {"stand": heute.isoformat(), "liste": liste}
            speichere_state(STATE_WIKIFOLIOS, wiki, "top50: wikifolio-liste [skip ci]")
    mitglieder["wikifolios"] = [(i, n, w, s) for i, w, n, s in wiki.get("liste", [])]
    log.info(f"wikifolios: {len(mitglieder['wikifolios'])} Werte")

    # 3) Kurshistorien ls-tc laden - jedes Instrument nur einmal, auch wenn es
    #    in mehreren Kategorien steht (z.B. Allianz in Aktien UND Dividenden)
    alle_ids = sorted({m[0] for k, liste in mitglieder.items() for m in liste})
    log.info(f"Lade Kurshistorie fuer {len(alle_ids)} Werte ...")
    with ThreadPoolExecutor(PARALLEL) as pool:
        perf_je_id = dict(zip(alle_ids, pool.map(
            lambda i: performance(historie(i), heute), alle_ids)))

    # 4) US-Indizes ueber Yahoo (Kurse in EUR + Dividendenrendite)
    ymap = lade_state(STATE_YAHOO, {}) or {}
    ymap_vorher = repr(ymap)
    index_cache = lade_state(STATE_INDIZES, {}) or {}
    index_cache_vorher = repr(index_cache)
    quellen_hinweis = {}
    index_keys = [k for k, kat in KATEGORIEN.items() if kat["quelle"] == "index"]
    for key in index_keys:
        kat = KATEGORIEN[key]
        liste, quellen_hinweis[key] = index_mitglieder(kat, index_cache, heute)
        mitglieder[key] = []
        log.info(f"{kat['titel']}: lade {len(liste)} Werte von Yahoo ...")
        with ThreadPoolExecutor(YAHOO_PARALLEL) as pool:
            geladen = list(pool.map(lambda e: lade_indexwert(*e[:4], ymap), liste))
        ohne = 0
        for (ticker, name, *_), (symbol, reihe, div, anzeige) in zip(liste, geladen):
            uid = f"Y:{symbol}"
            mitglieder[key].append((uid, anzeige, symbol, ""))
            if uid not in perf_je_id:
                p = performance(reihe or [], heute)
                if p:
                    p["_div"] = div
                perf_je_id[uid] = p
            if not reihe:
                ohne += 1
                if ohne <= 100:
                    nicht_gefunden.append({"kategorie": kat["titel"], "isin": symbol, "name": name})
        log.info(f"{kat['titel']}: {len(liste) - ohne} von {len(liste)} mit Kursdaten")
    if repr(index_cache) != index_cache_vorher:
        speichere_state(STATE_INDIZES, index_cache, "top50: indexlisten [skip ci]")

    # 5) Dividendenrendite der ls-tc-Aktien in Kategorien mit "dividende"
    div_cache = ymap.setdefault("div", {})
    for key, kat in KATEGORIEN.items():
        if not kat.get("dividende") or not isinstance(kat["quelle"], list):
            continue
        ziele = [m for m in mitglieder.get(key, []) if m[3] and perf_je_id.get(m[0])]
        with ThreadPoolExecutor(YAHOO_PARALLEL) as pool:
            renditen = list(pool.map(lambda m: lade_dividende_isin(m[3], m[1], ymap), ziele))
        treffer = 0
        for (iid, name, wkn, isin), rendite in zip(ziele, renditen):
            if rendite is None:                         # heute nicht ermittelbar -> letzter Wert
                alt = div_cache.get(isin)
                try:
                    if alt and (heute - datetime.date.fromisoformat(alt[1])).days <= DIV_CACHE_TAGE:
                        rendite = alt[0]
                except Exception:
                    pass
            else:
                div_cache[isin] = [rendite, heute.isoformat()]
            if rendite is not None:
                treffer += 1
            perf_je_id[iid]["_div"] = rendite
        log.info(f"{kat['titel']}: Dividendenrendite fuer {treffer} von {len(ziele)} Werten")
    if repr(ymap) != ymap_vorher:
        speichere_state(STATE_YAHOO, ymap, "top50: yahoo-zuordnung [skip ci]")

    # 6) Ranglisten bilden
    ergebnis = {
        "stand": jetzt.isoformat(timespec="minutes"),
        "zeitraeume": [[k, t] for k, t, _ in ZEITRAEUME],
        "dividenden_zeitraum": list(DIVIDENDEN_SCHLUESSEL),
        "reihenfolge": list(KATEGORIEN),
        "kategorien": {},
        "nicht_gefunden": nicht_gefunden,
    }
    div_key = DIVIDENDEN_SCHLUESSEL[0]
    for key, kat in KATEGORIEN.items():
        eintraege = []
        for uid, name, wkn, isin in mitglieder.get(key, []):
            p = perf_je_id.get(uid) or {}
            if p:
                eintraege.append((uid, name, wkn, isin, p))

        def zeile(e, schluessel):
            uid, name, wkn, isin, p = e
            z = {"name": name, "wkn": wkn, "perf": p.get(schluessel)}
            if kat.get("dividende"):
                z["div"] = p.get("_div")
            return z

        top, mit_daten = {}, {}
        for schluessel, _, _ in ZEITRAEUME:
            mit_wert = [e for e in eintraege if e[4].get(schluessel) is not None]
            mit_daten[schluessel] = len(mit_wert)
            mit_wert.sort(key=lambda e: e[4][schluessel], reverse=True)
            top[schluessel] = [zeile(e, schluessel) for e in mit_wert[:TOP_N]]
        if kat.get("dividende"):
            # Rangliste nach laufender Rendite; "perf" zeigt dort das 1-Jahres-Kursplus
            mit_div = [e for e in eintraege if (e[4].get("_div") or 0) > 0]
            mit_daten[div_key] = len(mit_div)
            mit_div.sort(key=lambda e: e[4]["_div"], reverse=True)
            top[div_key] = [zeile(e, "1J") for e in mit_div[:TOP_N]]

        neu = {
            "titel": kat["titel"],
            "im_universum": len(mitglieder.get(key, [])),
            "aktiv": len(eintraege),
            "mit_daten": mit_daten,
            "top": top,
            "dividende": bool(kat.get("dividende")),
            "kennung": "Symbol" if kat["quelle"] == "index" else "WKN",
        }
        if key in quellen_hinweis:
            neu["quellen"] = quellen_hinweis[key]
        # Yahoo gesperrt/ausgefallen: lieber die Rangliste vom Vortag zeigen als
        # eine, der die Haelfte der Werte fehlt
        alt = (vorher.get("kategorien") or {}).get(key)
        if (kat["quelle"] == "index" and alt and alt.get("aktiv", 0) > neu["aktiv"]
                and neu["aktiv"] < 0.5 * max(neu["im_universum"], 1)):
            log.warning(f"{kat['titel']}: nur {neu['aktiv']} Werte geladen - behalte Vortagesliste.")
            alt["veraltet_seit"] = alt.get("veraltet_seit") or vorher.get("stand")
            neu = alt
        ergebnis["kategorien"][key] = neu
        log.info(f"{kat['titel']}: {neu['aktiv']} aktive Werte, "
                 f"mit 10-Jahres-Daten: {neu['mit_daten'].get('10J', 0)}")

    dauer = time.monotonic() - start
    ergebnis["laufzeit_sek"] = round(dauer)
    ergebnis["anfragen"] = ZAEHLER["anfragen"] + ZAEHLER["yahoo"]
    ergebnis["fehlgeschlagen"] = ZAEHLER["fehler"] + ZAEHLER["yahoo_fehler"]
    ergebnis["yahoo_gesperrt"] = ZAEHLER["yahoo_429"]

    if not any(k["aktiv"] for k in ergebnis["kategorien"].values()):
        log.error("Keine einzige Kurshistorie geladen - vorhandene Ranglisten bleiben unveraendert.")
        sys.exit(1)

    speichere_state(STATE_TOP50, ergebnis, "top50: taegliche ranglisten [skip ci]")
    log.info(f"Fertig in {dauer:.0f}s - ls-tc {ZAEHLER['anfragen']} Anfragen ({ZAEHLER['fehler']} "
             f"fehlgeschlagen), Yahoo {ZAEHLER['yahoo']} ({ZAEHLER['yahoo_fehler']} fehlgeschlagen, "
             f"{ZAEHLER['yahoo_429']}x gebremst), {len(nicht_gefunden)} nicht gefunden.")


if __name__ == "__main__":
    main()
