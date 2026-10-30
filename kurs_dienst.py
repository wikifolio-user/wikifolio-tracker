"""Kursdienst: haelt alle Kurse (Live-Kurs und Tageshistorie je Instrument) im Speicher des
App-Prozesses und aktualisiert sie im Hintergrund nach Zeitplan - Benutzer warten nie auf
einen Neuabruf, sondern sehen bis zum Ende eines Laufs den letzten vollstaendigen Stand.

- hole(art, id): Wert aus dem Speicher; fehlt er, einmalig sofort abrufen (und merken -
  ab dann aktualisiert ihn jeder Lauf mit).
- aktualisieren(): einen Lauf im Hintergrund starten (False, wenn schon einer laeuft).
- Ein Lauf ruft alle gemerkten Werte parallel neu ab; nur erfolgreiche Abrufe ersetzen den
  alten Wert (fehlgeschlagene behalten ihren echten, aelteren Stand samt Zeitpunkt).
- zeitplan_starten(faellig): Hintergrund-Thread prueft regelmaessig, ob ein Lauf faellig ist.
- vorrat(art, id) -> (wert, zeitpunkt) | None (optional): vom Kurs-Agenten gespeicherte Kurse. Ist ein Wert
  dort neuer als im Speicher, gilt er. Mit wartezeit (Sekunden) wird ein fehlender Wert NICHT mehr im
  Seitenaufbau abgerufen, sondern im Hintergrund; hole() wartet hoechstens so lange und wirft sonst
  KursFehlt (der Wert erscheint beim naechsten Aufbau).
"""
import datetime
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _Zeitueberschreitung


class KursFehlt(LookupError):
    """Wert (noch) nicht da - wird gerade im Hintergrund geladen."""


class KursDienst:
    def __init__(self, abrufe, max_parallel=8, jetzt=None, nach_lauf=None, vorrat=None, wartezeit=None):
        """abrufe: {art: funktion(instrument_id) -> wert}, wirft bei Fehlern.
        jetzt: Uhr (-> aware datetime). nach_lauf: Rueckruf nach jedem Lauf.
        vorrat: Lesefunktion fuer gespeicherte Kurse; wartezeit: None = fehlende Werte sofort abrufen (wie
        bisher), sonst Hintergrund-Abruf mit hoechstens so vielen Sekunden Wartezeit."""
        self._abrufe = dict(abrufe)
        self._vorrat = vorrat
        self._wartezeit = wartezeit
        self._nachlader = None      # Thread-Pool fuer Hintergrund-Abrufe fehlender Werte
        self._offen = {}            # (art, id) -> Future eines laufenden Hintergrund-Abrufs
        self._max_parallel = max_parallel
        self._jetzt = jetzt or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self._nach_lauf = nach_lauf
        self._lock = threading.Lock()
        self._daten = {}            # (art, id) -> (wert, zeitpunkt)
        self._lauf = None           # waehrend eines Laufs: {"start", "gesamt", "fertig", "fehler"}
        self._letzter = None        # letzter abgeschlossener Lauf: {"start", "ende", "gesamt", "fehler"}
        self._thread = None
        self._zeitplan = None

    # ------------------------------------------------------------ Lesen
    def _aus_vorrat(self, k):
        if self._vorrat is None:
            return None
        try:
            v = self._vorrat(*k)
        except Exception as e:
            logging.warning(f"Kursdienst: Vorrat {k[0]} {k[1]} nicht lesbar: {type(e).__name__}")
            return None
        return v if v and v[1] is not None else None

    def hole(self, art, instrument_id):
        k = (art, str(instrument_id))
        with self._lock:
            e = self._daten.get(k)
        v = self._aus_vorrat(k)
        if v is not None and (e is None or e[1] is None or v[1] > e[1]):
            with self._lock:
                self._daten[k] = v              # neuer als der Speicher (Agent-Lauf)
            return v[0]
        if e is not None and e[1] is not None:
            return e[0]
        if self._wartezeit is not None:
            return self._nachladen(k)
        wert = self._abrufe[art](k[1])          # Fehler -> Ausnahme, nichts wird gemerkt
        with self._lock:
            alt = self._daten.get(k)
            if alt is None or alt[1] is None:   # ein paralleler Lauf kann schneller gewesen sein
                self._daten[k] = (wert, self._jetzt())
            return self._daten[k][0]

    def _nachladen(self, k):
        """Fehlenden Wert im Hintergrund abrufen; hoechstens wartezeit Sekunden warten, sonst KursFehlt."""
        with self._lock:
            f = self._offen.get(k)
            if f is None:
                if self._nachlader is None:
                    self._nachlader = ThreadPoolExecutor(max_workers=4, thread_name_prefix="kursdienst-nachladen")
                f = self._nachlader.submit(self._abrufe[k[0]], k[1])
                self._offen[k] = f
                f.add_done_callback(lambda fut, k=k: self._nachgeladen(k, fut))
        try:
            return f.result(timeout=self._wartezeit)
        except _Zeitueberschreitung:
            raise KursFehlt(f"{k[0]} {k[1]} wird im Hintergrund geladen") from None

    def _nachgeladen(self, k, fut):
        with self._lock:
            self._offen.pop(k, None)
            if fut.exception() is None:
                alt = self._daten.get(k)
                if alt is None or alt[1] is None:
                    self._daten[k] = (fut.result(), self._jetzt())

    def merken(self, art, instrument_id):
        """Instrument fuer die naechsten Laeufe vormerken, ohne es jetzt abzurufen."""
        k = (art, str(instrument_id))
        with self._lock:
            if k not in self._daten:
                self._daten[k] = (None, None)

    def leeren(self):
        with self._lock:
            self._daten.clear()

    # ------------------------------------------------------------ Aktualisieren
    def laeuft(self):
        with self._lock:
            return self._lauf is not None

    def aktualisieren(self, warten=False):
        """Einen Lauf im Hintergrund starten. -> True, wenn gestartet; False, wenn schon einer laeuft."""
        with self._lock:
            if self._lauf is not None:
                return False
            self._lauf = {"start": self._jetzt(), "gesamt": len(self._daten), "fertig": 0, "fehler": 0}
            t = threading.Thread(target=self._lauf_ausfuehren, name="kursdienst-lauf", daemon=True)
            self._thread = t
        t.start()
        if warten:
            t.join()
        return True

    def _eins(self, k):
        art, inst_id = k
        try:
            wert = self._abrufe[art](inst_id)
        except Exception as e:
            logging.warning(f"Kursdienst: {art} {inst_id} nicht ladbar: {type(e).__name__}")
            with self._lock:
                self._lauf["fertig"] += 1
                self._lauf["fehler"] += 1
            return
        with self._lock:
            self._daten[k] = (wert, self._jetzt())
            self._lauf["fertig"] += 1

    def _lauf_ausfuehren(self):
        try:
            with self._lock:
                schluessel = list(self._daten)
                self._lauf["gesamt"] = len(schluessel)
            if schluessel:
                with ThreadPoolExecutor(max_workers=min(self._max_parallel, len(schluessel))) as ex:
                    list(ex.map(self._eins, schluessel))
        finally:
            with self._lock:
                lauf, self._lauf = self._lauf, None
                self._letzter = {"start": lauf["start"], "ende": self._jetzt(), "gesamt": lauf["gesamt"],
                                 "fehler": lauf["fehler"]}
            if self._nach_lauf:
                try:
                    self._nach_lauf()
                except Exception as e:
                    logging.warning(f"Kursdienst: nach_lauf fehlgeschlagen: {type(e).__name__}")

    # ------------------------------------------------------------ Zeitplan
    def zeitplan_starten(self, faellig, pruef_sek=60):
        """faellig(letzter_lauf_start_oder_None) -> bool. Laeuft als Daemon-Thread, einmal je Prozess."""
        with self._lock:
            if self._zeitplan is not None and self._zeitplan.is_alive():
                return False

            def schleife():
                while True:
                    try:
                        letzter = self.status()["letzter_lauf"]
                        if not self.laeuft() and faellig(letzter):
                            self.aktualisieren(warten=True)
                    except Exception as e:
                        logging.warning(f"Kursdienst-Zeitplan: {type(e).__name__}: {e}")
                    time.sleep(pruef_sek)

            self._zeitplan = threading.Thread(target=schleife, name="kursdienst-zeitplan", daemon=True)
            self._zeitplan.start()
        return True

    def zeitplan_aktiv(self):
        with self._lock:
            return self._zeitplan is not None and self._zeitplan.is_alive()

    # ------------------------------------------------------------ Status
    def status(self):
        """{laeuft, fertig, gesamt, letzter_lauf (Start des letzten abgeschlossenen Laufs), letzter_ende,
        letzter_fehler, anzahl {art: n}, aeltester, neuester, ohne_wert}"""
        with self._lock:
            zeiten = [z for _, z in self._daten.values() if z is not None]
            anzahl = {}
            for (art, _), (_, z) in self._daten.items():
                if z is not None:
                    anzahl[art] = anzahl.get(art, 0) + 1
            lauf, letzter = self._lauf, self._letzter
            return {"laeuft": lauf is not None,
                    "fertig": lauf["fertig"] if lauf else 0,
                    "gesamt": lauf["gesamt"] if lauf else 0,
                    "letzter_lauf": letzter["start"] if letzter else None,
                    "letzter_ende": letzter["ende"] if letzter else None,
                    "letzter_fehler": letzter["fehler"] if letzter else 0,
                    "anzahl": anzahl,
                    "werte": sum(anzahl.values()),
                    "instrumente": len({i for (_, i), (_, z) in self._daten.items() if z is not None}),
                    "aeltester": min(zeiten) if zeiten else None,
                    "neuester": max(zeiten) if zeiten else None,
                    "ohne_wert": sum(1 for _, z in self._daten.values() if z is None)}
