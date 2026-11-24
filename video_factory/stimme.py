"""Sprecher-Agent: Sprachausgabe je Szene mit Piper (lokal, kostenlos). Standardstimme de_DE-thorsten-medium:
Datensatz CC0, Basismodell CC0 - kommerziell frei nutzbar. Keine nachgeahmten realen Stimmen.
Die Stimmdateien kommen von huggingface.co/rhasspy/piper-voices und werden zwischengespeichert."""
import os
import subprocess
import sys
import wave

STIMMEN = {
    "de_DE-thorsten-medium": {"sprache": "de", "pfad": "de/de_DE/thorsten/medium", "lizenz": "CC0 (Datensatz und "
                              "Basismodell)", "name": "Thorsten (Deutsch, männlich)"},
}
STANDARD = "de_DE-thorsten-medium"
URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{pfad}/{datei}"


def stimme_laden(name, ordner, get):
    """Stimmdatei (.onnx + .onnx.json) herunterladen, falls noch nicht da. -> Pfad der .onnx"""
    s = STIMMEN[name]
    os.makedirs(ordner, exist_ok=True)
    for datei in (f"{name}.onnx", f"{name}.onnx.json"):
        ziel = os.path.join(ordner, datei)
        if os.path.exists(ziel) and os.path.getsize(ziel) > 0:
            continue
        r = get(URL.format(pfad=s["pfad"], datei=datei), timeout=300, stream=True)
        if r.status_code != 200:
            raise IOError(f"Stimme {datei}: HTTP {r.status_code}")
        with open(ziel + ".teil", "wb") as f:
            for teil in r.iter_content(1 << 20):
                f.write(teil)
        os.replace(ziel + ".teil", ziel)
    return os.path.join(ordner, f"{name}.onnx")


def dauer(pfad):
    with wave.open(pfad, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def sprechen(text, modell, ziel, tempo=1.0):
    """Text -> WAV mit Piper. tempo > 1 = langsamer (length_scale). -> Dauer in Sekunden"""
    os.makedirs(os.path.dirname(ziel) or ".", exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "piper", "-m", modell, "-f", ziel, "--length-scale", str(tempo)],
                       input=text.encode("utf-8"), capture_output=True, timeout=300)
    if r.returncode != 0 or not os.path.exists(ziel):
        raise RuntimeError("Piper: " + r.stderr.decode("utf-8", "ignore")[-300:])
    return dauer(ziel)


def aussprache(text, ersetzungen=None):
    """Ausspracheanpassungen (z. B. {"KI": "K I", "SaaS": "Sass"}) - nur fuer die Stimme, nicht fuer Untertitel."""
    import re
    for a, b in (ersetzungen or {}).items():
        text = re.sub(rf"\b{re.escape(a)}\b", b, text)
    return text
