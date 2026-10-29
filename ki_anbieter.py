"""KI-Auswertung ueber ein kostenloses API-Kontingent (Option A) - austauschbar ueber eine Provider-Abstraktion.

Anbieter: Google Gemini (generateContent mit JSON-Ausgabe) und Groq (OpenAI-kompatibel, JSON-Modus).
Keys NUR aus Umgebungsvariablen/Secrets (GEMINI_API_KEY, GROQ_API_KEY), nie im Code. Ohne Key: kein Anbieter ->
die App blendet Option A aus. Mindestabstand zwischen Anfragen und Wiederholung mit wachsender Wartezeit bei
429/5xx (Limits in investor_config.KI). Ungueltiges JSON wird genau einmal neu angefragt.
"""
import logging
import os
import threading
import time

import requests

import investor_config as C
from investor_checks import qualitativ as Q


class Anbieter:
    name = ""
    url = ""

    def __init__(self, key, cfg):
        self.key, self.cfg = key, cfg
        self._lock, self._letzter = threading.Lock(), 0.0

    def _warten(self):
        with self._lock:
            w = self.cfg["min_abstand_sek"] - (time.monotonic() - self._letzter)
            if w > 0:
                time.sleep(w)
            self._letzter = time.monotonic()

    def _anfrage(self, prompt):          # -> Antworttext
        raise NotImplementedError

    def antwort(self, prompt):
        """Rohtext der Antwort; Wiederholung mit Backoff bei Limit/Serverfehler. -> str oder None"""
        for versuch in range(C.KI["versuche"]):
            self._warten()
            try:
                return self._anfrage(prompt)
            except Limit as e:
                pause = e.warte or C.KI["backoff_sek"] * (2 ** versuch)
                logging.warning("%s: Limit erreicht, warte %.0f s", self.name, pause)
                time.sleep(pause)
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                logging.warning("%s: %s", self.name, type(e).__name__)
                time.sleep(C.KI["backoff_sek"])
        return None

    def analyse(self, prompt):
        """Antwort als gepruefte KI-Einschaetzung; bei ungueltigem JSON genau ein zweiter Versuch.
        -> (dict oder None, Fehlertext oder None)"""
        fehler = None
        for _ in range(2):
            obj, fehler_liste = Q.pruefen(Q.json_aus_text(self.antwort(prompt)))
            if obj:
                obj.update({"quelle": f"KI ({self.titel})", "modell": self.cfg["modell"]})
                return obj, None
            fehler = "; ".join(fehler_liste)
            prompt += "\n\nDeine letzte Antwort war kein gültiges JSON im verlangten Schema. Nur das JSON-Objekt!"
        return None, fehler


class Limit(Exception):
    def __init__(self, warte=None):
        super().__init__("rate limit")
        self.warte = warte


def _retry_after(r):
    try:
        return float(r.headers.get("retry-after") or 0) or None
    except ValueError:
        return None


class Gemini(Anbieter):
    name, titel = "gemini", "Gemini"

    def _anfrage(self, prompt):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.cfg['modell']}:generateContent"
        r = requests.post(url, headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}},
                          timeout=C.KI["timeout_sek"])
        if r.status_code == 429 or r.status_code >= 500:
            raise Limit(_retry_after(r))
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


class Groq(Anbieter):
    name, titel = "groq", "Groq"

    def _anfrage(self, prompt):
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                          json={"model": self.cfg["modell"], "temperature": 0.2,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "user", "content": prompt}]},
                          timeout=C.KI["timeout_sek"])
        if r.status_code == 429 or r.status_code >= 500:
            raise Limit(_retry_after(r))
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


KLASSEN = {"gemini": (Gemini, "GEMINI_API_KEY"), "groq": (Groq, "GROQ_API_KEY")}


def verfuegbar(secrets=None):
    """Erster Anbieter mit hinterlegtem Key (Reihenfolge KI_REIHENFOLGE) oder None.
    secrets: dict-aehnlich (st.secrets) - sonst Umgebungsvariablen."""
    for name in C.KI_REIHENFOLGE:
        klasse, var = KLASSEN[name]
        key = None
        try:
            key = (secrets or {}).get(var) if secrets is not None else None
        except Exception:
            key = None
        key = key or os.environ.get(var)
        if key:
            return klasse(str(key).strip(), C.KI[name])
    return None
