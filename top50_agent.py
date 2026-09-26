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
  3. Kurshistorie je Wert laden (parallel, gedrosselt).
  4. Performance je Zeitraum berechnen, Top 50 bilden, speichern.
"""
import datetime
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import requests

import config
import github_store
from top50_universum import KATEGORIEN, TOP_N, ZEITRAEUME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("top50")

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GH_STATE_TOKEN", "")

SUCH_URL = "https://www.ls-tc.de/_rpc/json/.lstc/instrument/search/main"
STATE_TOP50 = "state/top50.json"
STATE_IDS = "state/top50_ids.json"
STATE_WIKIFOLIOS = "state/top50_wikifolios.json"

SUCHE_MAX_TREFFER = 20        # Obergrenze der ls-tc-Suche je Aufruf (getestet)
WIKIFOLIO_CACHE_TAGE = 7      # Entdeckung nur woechentlich neu
MAX_ALTER_TAGE = 10           # Werte ohne Kurs seit >10 Tagen gelten als inaktiv
TOLERANZ_TAGE = 10            # Stichtag darf auf Wochenende/Feiertag fallen
PARALLEL = 6                  # gleichzeitige Abrufe
ANFRAGEN_PRO_SEKUNDE = 8      # Obergrenze gegenueber ls-tc.de - bewusst hoeflich
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


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
ZAEHLER = {"anfragen": 0, "fehler": 0}


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

    # 1) Instrument-IDs aufloesen (gecacht)
    id_cache = lade_state(STATE_IDS, {}) or {}
    anzahl_vorher = len(id_cache)
    mitglieder = {}             # kategorie -> [(id, name, wkn, isin)]
    nicht_gefunden = []
    for key, kat in KATEGORIEN.items():
        if kat["quelle"] == "auto":
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

    # 3) Kurshistorien laden - jedes Instrument nur einmal, auch wenn es in
    #    mehreren Kategorien steht (z.B. Allianz in Aktien UND Dividenden)
    alle_ids = sorted({m[0] for liste in mitglieder.values() for m in liste})
    log.info(f"Lade Kurshistorie fuer {len(alle_ids)} Werte ...")
    with ThreadPoolExecutor(PARALLEL) as pool:
        perf_je_id = dict(zip(alle_ids, pool.map(
            lambda i: performance(historie(i), heute), alle_ids)))

    # 4) Ranglisten bilden
    ergebnis = {
        "stand": jetzt.isoformat(timespec="minutes"),
        "zeitraeume": [[k, t] for k, t, _ in ZEITRAEUME],
        "kategorien": {},
        "nicht_gefunden": nicht_gefunden,
    }
    for key, kat in KATEGORIEN.items():
        eintraege = []
        for iid, name, wkn, isin in mitglieder.get(key, []):
            p = perf_je_id.get(iid) or {}
            if p:
                eintraege.append((iid, name, wkn, isin, p))
        top, mit_daten = {}, {}
        for schluessel, _, _ in ZEITRAEUME:
            mit_wert = [e for e in eintraege if e[4].get(schluessel) is not None]
            mit_daten[schluessel] = len(mit_wert)
            mit_wert.sort(key=lambda e: e[4][schluessel], reverse=True)
            top[schluessel] = [{
                "name": name, "wkn": wkn, "isin": isin, "id": iid,
                "perf": p[schluessel], "kurs": round(p["_kurs"], 4), "stand": p["_stand"],
            } for iid, name, wkn, isin, p in mit_wert[:TOP_N]]
        ergebnis["kategorien"][key] = {
            "titel": kat["titel"],
            "im_universum": len(mitglieder.get(key, [])),
            "aktiv": len(eintraege),
            "mit_daten": mit_daten,
            "top": top,
        }
        log.info(f"{kat['titel']}: {len(eintraege)} aktive Werte, "
                 f"mit 10-Jahres-Daten: {mit_daten.get('10J', 0)}")

    dauer = time.monotonic() - start
    ergebnis["laufzeit_sek"] = round(dauer)
    ergebnis["anfragen"] = ZAEHLER["anfragen"]
    ergebnis["fehlgeschlagen"] = ZAEHLER["fehler"]

    if not any(k["aktiv"] for k in ergebnis["kategorien"].values()):
        log.error("Keine einzige Kurshistorie geladen - vorhandene Ranglisten bleiben unveraendert.")
        sys.exit(1)

    speichere_state(STATE_TOP50, ergebnis, "top50: taegliche ranglisten [skip ci]")
    log.info(f"Fertig in {dauer:.0f}s - {ZAEHLER['anfragen']} Anfragen, "
             f"{ZAEHLER['fehler']} fehlgeschlagen, {len(nicht_gefunden)} nicht gefunden.")


if __name__ == "__main__":
    main()
