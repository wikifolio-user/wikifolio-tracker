"""Kursdienst: haelt alle Kurse (Live-Kurs und Tageshistorie je Instrument) im Speicher des
App-Prozesses und aktualisiert sie im Hintergrund nach Zeitplan - Benutzer warten nie auf
einen Neuabruf, sondern sehen bis zum Ende eines Laufs den letzten vollstaendigen Stand.

- hole(art, id): Wert aus dem Speicher; fehlt er, einmalig sofort abrufen (und merken -
  ab dann aktualisiert ihn jeder Lauf mit).
- aktualisieren(): einen Lauf im Hintergrund starten (False, wenn schon einer laeuft).
- Ein Lauf ruft alle gemerkten Werte parallel neu ab; nur erfolgreiche Abrufe ersetzen den
  alten Wert (fehlgeschlagene behalten ihren echten, aelteren Stand samt Zeitpunkt).
- zeitplan_starten(faellig): Hintergrund-Thread prueft regelmaessig, ob ein Lauf faellig ist.
"""
import datetime
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class KursDienst:
    def __init__(self, abrufe, max_parallel=8, jetzt=None, nach_lauf=None):
        """abrufe: {art: funktion(instrument_id) -> wert}, wirft bei Fehlern.
        jetzt: Uhr (-> aware datetime). nach_lauf: Rueckruf nach jedem Lauf."""
        self._abrufe = dict(abrufe)
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
    def hole(self, art, instrument_id):
        k = (art, str(instrument_id))
        with self._lock:
            e = self._daten.get(k)
        if e is not None and e[1] is not None:
            return e[0]
        wert = self._abrufe[art](k[1])          # Fehler -> Ausnahme, nichts wird gemerkt
        with self._lock:
            alt = self._daten.get(k)
            if alt is None or alt[1] is None:   # ein paralleler Lauf kann schneller gewesen sein
                self._daten[k] = (wert, self._jetzt())
            return self._daten[k][0]

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
                    "aeltester": min(zeiten) if zeiten else None,
                    "neuester": max(zeiten) if zeiten else None,
                    "ohne_wert": sum(1 for _, z in self._daten.values() if z is None)}
