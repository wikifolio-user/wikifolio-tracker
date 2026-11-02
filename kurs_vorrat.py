"""Kurs-Vorrat: vom Kurs-Agenten (kurs_agent.py, GitHub Action alle 30 Min.) im Datenspeicher abgelegte Kurse.

Die App liest beim Seitenaufbau nur diese Dateien - keine Kursabrufe bei ls-tc.de. Format (State-Branch):
  state/kurse/live.json          {"stand": iso, "werte": {id: {"i": [[ts_ms, kurs], [ts_ms, kurs]],
                                                                "p": vortageskurs | null, "t": iso}}}
                                  i = erster und letzter Intraday-Punkt, p = Vortageskurs (plotlines)
  state/kurse/historie_NN.json   {"stand": iso, "werte": {id: {"d": [[ts_ms, schluss], ...], "t": iso}}}
                                  NN = teil(id) - die App liest nur die Teile der Werte, die sie braucht
  state/kurse/suche.json         {"stand": iso, "werte": {suchbegriff (klein): [treffer, ...]}}
                                  Suchergebnisse (Ticker/ISIN -> Kurs-ID) fuer den Portfolio-Planer
  state/kurse/top50_live.json    {"stand": iso, "ids": {WKN/ISIN: id}, "werte": {id: wie live.json}}
                                  Live-Kurse der Top 50 je Watchlist-Kategorie (ohne Historie)
Gemeinsam genutzt von Agent und App (nur Standardbibliothek).
"""
import datetime
import threading
import time
import zlib

PFAD_LIVE = "state/kurse/live.json"
PFAD_HISTORIE = "state/kurse/historie_{:02d}.json"
PFAD_SUCHE = "state/kurse/suche.json"
PFAD_TOP50 = "state/kurse/top50_live.json"
SUCH_URL = "https://www.ls-tc.de/_rpc/json/.lstc/instrument/search/main"
TEILE = 8


def teil(instrument_id):
    return zlib.crc32(str(instrument_id).encode()) % TEILE


def zeit(text):
    """ISO-Zeitpunkt -> aware datetime (None bei Fehlern)."""
    try:
        t = datetime.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def such_schluessel(begriff):
    return str(begriff or "").strip().lower()


def suche_auswerten(daten):
    """Antwort der ls-tc-Suche -> [{"instrument_id", "name", "wkn", "isin", "kategorie"}]. Der Endpunkt liefert
    je nach Aufruf ein blankes Array oder ein Objekt mit "results"/"data" - beide Formen abfangen."""
    if isinstance(daten, dict):
        daten = daten.get("results") or (daten.get("data") or {}).get("results") or []
    treffer = []
    for eintrag in daten or []:
        if not isinstance(eintrag, dict):
            continue
        inst_id = eintrag.get("instrumentId") or eintrag.get("id")
        if not inst_id:
            continue
        treffer.append({
            "instrument_id": int(inst_id),
            "name": eintrag.get("displayname") or "(ohne Namen)",
            "wkn": str(eintrag.get("wkn") or ""),
            "isin": eintrag.get("isin") or "",
            "kategorie": eintrag.get("categoryName") or "",
        })
    return treffer


def bester_treffer(treffer, begriff):
    """Treffer mit genau dieser ISIN/WKN, sonst der erste (fuer die Kurs-ID, die der Agent mitlaedt)."""
    b = such_schluessel(begriff)
    for t in treffer:
        if b and b in (str(t.get("isin", "")).lower(), str(t.get("wkn", "")).lower()):
            return t
    return treffer[0] if treffer else None


def kennung_ids(id_cache, wikifolios):
    """Kurs-IDs (ls-tc) aus den Daten der Top-500-Listen: state/top50_ids.json ({isin | "KAT:wkn": {id, wkn,
    isin}}) und state/top50_wikifolios.json ({"liste": [[id, wkn, name, isin], ...]}).
    -> {WKN/ISIN (gross): instrument_id}"""
    aus = {}
    for schluessel, v in (id_cache or {}).items():
        if not isinstance(v, dict) or not v.get("id"):
            continue
        for k in (v.get("wkn"), v.get("isin"), str(schluessel).replace("KAT:", "")):
            if k:
                aus.setdefault(str(k).upper(), int(v["id"]))
    for z in (wikifolios or {}).get("liste") or []:
        if isinstance(z, (list, tuple)) and len(z) >= 2 and z[0]:
            for k in (z[1], z[3] if len(z) > 3 else None):
                if k:
                    aus.setdefault(str(k).upper(), int(z[0]))
    return aus


def top50_kennungen(top50):
    """WKN/Symbole aller Werte, die die Watchlist als Top 50 zeigt (alle Kategorien und Zeitraeume)."""
    aus = []
    for kat in ((top50 or {}).get("kategorien") or {}).values():
        for liste in ((kat or {}).get("top") or {}).values():
            for e in liste or []:
                k = str((e or {}).get("wkn") or "").strip().upper()
                if k and k not in aus:
                    aus.append(k)
    return aus


def heute(eintrag):
    """(kurs, vortageskurs) aus einem Live-Eintrag - nur mit echtem Vortageskurs, sonst None (die Veraenderung
    gegen den ersten Kurs des Tages waere kein "heute ±%")."""
    try:
        kurs, vor = float(eintrag["i"][-1][1]), float(eintrag.get("p") or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return (kurs, vor) if kurs > 0 and vor > 0 else None


def live_antwort(eintrag, historie=None):
    """Eintrag aus live.json -> Antwort im Format von dataForInstrument (fuer ls_tc_live_auswerten der App)."""
    p = eintrag.get("p")
    return {"series": {"intraday": {"data": eintrag.get("i") or []}, "history": {"data": historie or []}},
            "info": {"plotlines": [{"id": "previousDay", "value": p}] if p else []}}


def aktuell(stand, jetzt, max_alter_min):
    """Hat der Kurs-Agent zuletzt vor hoechstens max_alter_min Minuten geliefert?"""
    return stand is not None and (jetzt - stand) <= datetime.timedelta(minutes=max_alter_min)


def naechster_lauf(jetzt, utc_stunden):
    """Naechster planmaessiger Agenten-Lauf (volle/halbe Stunde, werktags in utc_stunden) in der Zeitzone
    von jetzt - oder None."""
    t = jetzt.astimezone(datetime.timezone.utc).replace(second=0, microsecond=0)
    t += datetime.timedelta(minutes=30 - t.minute % 30)
    for _ in range(7 * 48):
        if t.weekday() < 5 and t.hour in utc_stunden:
            return t.astimezone(jetzt.tzinfo)
        t += datetime.timedelta(minutes=30)
    return None


class Vorrat:
    """Liest die Vorrats-Dateien und haelt sie kurz im Speicher (live 2 Min., Historie 15 Min.).

    lesen(pfad) -> dict oder None (fehlt); wirft bei Lesefehlern - dann gilt der letzte gelesene Stand weiter
    bzw. "nichts im Vorrat" (die App laedt den Wert dann im Hintergrund nach)."""

    def __init__(self, lesen, ttl_live=120, ttl_historie=900, uhr=time.monotonic):
        self._lesen = lesen
        self._ttl = {"live": ttl_live, "historie": ttl_historie}
        self._uhr = uhr
        self._lock = threading.Lock()
        self._dateien = {}          # pfad -> (gelesen_um, daten)

    def _datei(self, pfad, art):
        jetzt = self._uhr()
        with self._lock:
            e = self._dateien.get(pfad)
        if e is not None and jetzt - e[0] < self._ttl[art]:
            return e[1]
        try:
            daten = self._lesen(pfad)
        except Exception:
            daten = e[1] if e is not None else None
        if not isinstance(daten, dict):
            daten = e[1] if (e is not None and isinstance(e[1], dict)) else {}
        with self._lock:
            self._dateien[pfad] = (jetzt, daten)
        return daten

    def live(self, instrument_id):
        """-> (eintrag, abgerufen_um) oder None"""
        w = (self._datei(PFAD_LIVE, "live").get("werte") or {}).get(str(instrument_id))
        if not isinstance(w, dict) or not w.get("i"):
            return None
        t = zeit(w.get("t"))
        return (w, t) if t else None

    def historie(self, instrument_id):
        """-> ([[ts_ms, schluss], ...], abgerufen_um) oder None"""
        pfad = PFAD_HISTORIE.format(teil(instrument_id))
        w = (self._datei(pfad, "historie").get("werte") or {}).get(str(instrument_id))
        if not isinstance(w, dict) or not w.get("d"):
            return None
        t = zeit(w.get("t"))
        return (w["d"], t) if t else None

    def suche(self, begriff):
        """Gespeicherte Suchergebnisse des Agenten -> Trefferliste oder None (Begriff nicht im Vorrat)."""
        w = (self._datei(PFAD_SUCHE, "historie").get("werte") or {}).get(such_schluessel(begriff))
        return w if isinstance(w, list) else None

    def top50(self):
        """Live-Kurse der Top-50-Werte -> {"ids": {WKN: id}, "werte": {id: eintrag}, "stand": datetime|None}"""
        d = self._datei(PFAD_TOP50, "live")
        return {"ids": d.get("ids") or {}, "werte": d.get("werte") or {}, "stand": zeit(d.get("stand"))}

    def stand(self):
        """Zeitpunkt des letzten Agenten-Laufs (live.json) oder None."""
        return zeit(self._datei(PFAD_LIVE, "live").get("stand"))
