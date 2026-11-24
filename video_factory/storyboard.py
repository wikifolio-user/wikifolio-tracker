"""Storyboard-Agent: Skript -> Szenen (Nummer, Kapitel, Sprechertext, Bildsuchbegriff, geplante Dauer). Lange
Szenen werden an Satzgrenzen geteilt. Start- und Endzeiten werden nach der Sprachausgabe aus der echten
Audiodauer gesetzt (zeiten_setzen). Einzelne Szenen lassen sich aendern, ohne das ganze Video neu zu erzeugen."""
import re

from video_factory import skript as SK

PAUSE_S = 0.35                       # Pause nach jeder Szene


def _saetze(text):
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]


def _teilen(text, max_woerter=SK.MAX_SZENE_WOERTER):
    teile, akt = [], []
    for s in _saetze(text):
        if akt and len(re.findall(r"\w+", " ".join(akt + [s]))) > max_woerter:
            teile.append(" ".join(akt))
            akt = []
        akt.append(s)
    if akt:
        teile.append(" ".join(akt))
    return teile or [text.strip()]


def erstellen(skript):
    """-> Liste von Szenen-dicts (ohne Assets und Zeiten)."""
    szenen = []
    for ki, k in enumerate(skript["kapitel"]):
        for s in k["szenen"]:
            for teil in _teilen(s["text"]):
                szenen.append({"nr": len(szenen) + 1, "kapitel": k["titel"], "kapitel_nr": ki + 1, "text": teil,
                               "bild": s.get("bild") or k["titel"],
                               "dauer_plan": round(len(re.findall(r"\w+", teil)) / SK.WOERTER_PRO_MINUTE * 60, 1),
                               "asset": None, "audio": None, "start": None, "dauer": None})
    return szenen


def zeiten_setzen(szenen):
    """Start und Dauer aus der echten Audiodauer jeder Szene (+ Pause). Szenen ohne Audio -> Fehler."""
    t = 0.0
    for s in szenen:
        if not s.get("audio") or not s["audio"].get("dauer"):
            raise ValueError(f"Szene {s['nr']} hat noch keine Sprachausgabe.")
        s["start"] = round(t, 3)
        s["dauer"] = round(s["audio"]["dauer"] + PAUSE_S, 3)
        t += s["dauer"]
    return t


def kapitelmarken(szenen):
    """YouTube-Kapitel: erste Szene je Kapitel -> [(sekunden, titel)]; das erste beginnt bei 0:00."""
    aus, gesehen = [], set()
    for s in szenen:
        if s["kapitel_nr"] not in gesehen and s.get("start") is not None:
            gesehen.add(s["kapitel_nr"])
            aus.append((0.0 if not aus else s["start"], s["kapitel"]))
    return aus


def zeit_text(sek):
    sek = int(round(sek))
    return f"{sek // 3600}:{sek % 3600 // 60:02d}:{sek % 60:02d}" if sek >= 3600 else f"{sek // 60}:{sek % 60:02d}"


# ---------------------------------------------------------------- Untertitel
def _zeit_srt(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def _zeilen(text, breite=42):
    w, zeilen, akt = text.split(), [], ""
    for x in w:
        if akt and len(akt) + 1 + len(x) > breite:
            zeilen.append(akt)
            akt = x
        else:
            akt = f"{akt} {x}".strip()
    if akt:
        zeilen.append(akt)
    return zeilen


def untertitel(szenen, breite=42):
    """Untertitel-Bloecke (hoechstens 2 Zeilen) je Szene, Zeit anteilig nach Zeichen. -> [(start, ende, text)]"""
    aus = []
    for s in szenen:
        zeilen = _zeilen(s["text"], breite)
        bloecke = ["\n".join(zeilen[i:i + 2]) for i in range(0, len(zeilen), 2)]
        gesamt = sum(len(b) for b in bloecke) or 1
        sprech = (s["audio"] or {}).get("dauer") or s["dauer"]
        t = s["start"]
        for b in bloecke:
            d = sprech * len(b) / gesamt
            aus.append((t, t + d, b))
            t += d
    return aus


def srt(bloecke):
    return "\n".join(f"{i}\n{_zeit_srt(a)} --> {_zeit_srt(e)}\n{t}\n" for i, (a, e, t) in enumerate(bloecke, 1))


def vtt(bloecke):
    return "WEBVTT\n\n" + "\n".join(f"{_zeit_srt(a).replace(',', '.')} --> {_zeit_srt(e).replace(',', '.')}\n{t}\n"
                                    for a, e, t in bloecke)
