"""Video Factory - Hintergrundmusik: leise unter der Stimme, automatisch abgesenkt, solange gesprochen wird.

Quellen (in dieser Reihenfolge der Lizenzsicherheit):
  klang      eigene, mit FFmpeg erzeugte ruhige Klangflaeche - keine Lizenzfragen (Standard)
  openverse  Musik unter CC0 / Public Domain / CC BY ueber die Openverse-API - Namensnennung automatisch
  eigene     selbst hochgeladene Datei - nur nach Bestaetigung, dass die Rechte vorliegen
  aus        keine Musik
Schlaegt Openverse fehl (Netz, keine Treffer), wird die eigene Klangflaeche verwendet und das protokolliert."""
import hashlib
import os
import subprocess
from urllib.parse import quote

MODI = {"klang": "Eigene Klangfläche (erzeugt, ohne Lizenzfragen)", "openverse": "Freie Musik (CC0/CC BY, Openverse)",
        "eigene": "Eigene Datei (Rechte vorhanden)", "aus": "Keine Musik"}
STIMMUNGEN = {"ruhig": {"name": "ruhig", "toene": (110.0, 220.0, 261.63, 329.63), "tremolo": 0.15,
                        "suche": "calm ambient piano"},
              "freundlich": {"name": "freundlich", "toene": (130.81, 261.63, 329.63, 392.0), "tremolo": 0.25,
                             "suche": "uplifting acoustic"},
              "spannend": {"name": "spannend", "toene": (73.42, 146.83, 174.61, 220.0), "tremolo": 0.5,
                           "suche": "cinematic tension"}}
ERLAUBT = {"cc0": "CC0 1.0", "pdm": "Public Domain Mark", "by": "CC BY"}
STANDARD = {"modus": "klang", "stimmung": "ruhig", "lautstaerke_db": -20, "suche": ""}
LAUTSTAERKE = (-35, -8)
MAX_BYTES = 25_000_000
MIN_DAUER_S = 45
DATEITYPEN = ("mp3", "ogg", "wav", "flac", "m4a")
UA = {"User-Agent": "FinanzDashboard-VideoFactory/1.0 (privates Projekt; Kontakt ueber GitHub)"}


class MusikFehler(Exception):
    pass


def einstellungen(m=None):
    """Musik-Einstellungen eines Projekts mit Standardwerten, Werte begrenzt."""
    m = {**STANDARD, **(m or {})}
    if m["modus"] not in MODI:
        m["modus"] = "klang"
    if m["stimmung"] not in STIMMUNGEN:
        m["stimmung"] = "ruhig"
    try:
        m["lautstaerke_db"] = max(LAUTSTAERKE[0], min(LAUTSTAERKE[1], float(m["lautstaerke_db"])))
    except (TypeError, ValueError):
        m["lautstaerke_db"] = STANDARD["lautstaerke_db"]
    m["suche"] = str(m.get("suche") or "")[:80]
    return m


def _ffmpeg(args, timeout=900):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args, capture_output=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise MusikFehler(r.stderr.decode("utf-8", "ignore")[-400:] or "FFmpeg-Fehler")


# ---------------------------------------------------------------------------------------------------- erzeugen
def erzeugen(ziel, dauer, stimmung="ruhig"):
    """Ruhige Klangflaeche (Akkord aus Sinustoenen, langsames Tremolo, leises gefiltertes Rauschen) als M4A."""
    s = STIMMUNGEN.get(stimmung) or STIMMUNGEN["ruhig"]
    d = max(5.0, float(dauer)) + 1.0
    args = []
    for f in s["toene"]:
        args += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={d:.2f}:sample_rate=48000"]
    args += ["-f", "lavfi", "-i", f"anoisesrc=color=brown:duration={d:.2f}:amplitude=0.04:sample_rate=48000"]
    n = len(s["toene"])
    ketten = "".join(f"[{i}]volume={0.5 if i == 0 else 0.3}[t{i}];" for i in range(n))
    filt = (ketten + "".join(f"[t{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,"
            f"tremolo=f={s['tremolo']}:d=0.35,lowpass=f=1800[a];[{n}]lowpass=f=500[r];"
            f"[a][r]amix=inputs=2:normalize=0,afade=t=in:d=3,afade=t=out:st={max(0.0, d - 3):.2f}:d=3,"
            "volume=0.6,aformat=channel_layouts=stereo[o]")
    _ffmpeg(args + ["-filter_complex", filt, "-map", "[o]", "-c:a", "aac", "-b:a", "128k", ziel])
    return {"pfad": ziel, "lizenz": "eigen", "lizenz_text": "eigene Erzeugung", "titel": f"Klangfläche "
            f"({s['name']})", "urheber": "eigene Erzeugung (FFmpeg)", "quelle": "", "anbieter": "eigen",
            "namensnennung_noetig": False}


# ---------------------------------------------------------------------------------------------------- Openverse
def openverse_url(suche, nur_musik=True):
    return (f"https://api.openverse.org/v1/audio/?q={quote(suche)}&license=cc0,pdm,by&license_type=commercial"
            + ("&category=music" if nur_musik else "") + "&mature=false&page_size=20")


def openverse_parsen(daten):
    """Openverse-Audio-Antwort -> Kandidaten (nur erlaubte Lizenzen, mindestens MIN_DAUER_S, bekannte Formate)."""
    aus = []
    for r in (daten or {}).get("results") or []:
        lz = str(r.get("license") or "").lower()
        typ = str(r.get("filetype") or "").lower()
        typ = "mp3" if typ.startswith("mp3") else typ             # Jamendo meldet "mp32"
        dauer = (r.get("duration") or 0) / 1000
        if lz not in ERLAUBT or not r.get("url") or not str(r["url"]).startswith("https://"):
            continue
        if dauer and dauer < MIN_DAUER_S:
            continue
        if typ and typ not in DATEITYPEN:
            continue
        aus.append({"url": r["url"], "lizenz": lz, "lizenz_text": f"{ERLAUBT[lz]} {r.get('license_version') or ''}"
                    .strip(), "lizenz_url": r.get("license_url") or "", "urheber": str(r.get("creator") or "unbekannt")
                    [:80], "titel": str(r.get("title") or "Musik")[:100], "quelle": r.get("foreign_landing_url")
                    or r["url"], "anbieter": f"Openverse / {r.get('source') or r.get('provider') or '?'}",
                    "namensnennung_noetig": lz == "by", "dauer": dauer or None, "typ": typ})
    return aus


def suchen(suche, get):
    """Erst in der Kategorie Musik, ohne Treffer in allen Audios (laengere Stuecke zuerst)."""
    for nur_musik in (True, False):
        r = get(openverse_url(suche, nur_musik), headers=UA, timeout=30)
        if r.status_code != 200:
            raise MusikFehler(f"Openverse antwortet mit {r.status_code}")
        k = openverse_parsen(r.json())
        if k:
            return sorted(k, key=lambda x: -(x.get("dauer") or 0)) if not nur_musik else k
    return []


def laden(kandidat, get, ordner):
    """Audiodatei herunterladen (hoechstens MAX_BYTES). -> Pfad"""
    r = get(kandidat["url"], headers=UA, timeout=120, stream=True)
    if r.status_code != 200:
        raise MusikFehler(f"Download: HTTP {r.status_code}")
    daten = b""
    for teil in r.iter_content(65536):
        daten += teil
        if len(daten) > MAX_BYTES:
            raise MusikFehler("Datei zu groß")
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.join(ordner, "musik_" + hashlib.sha1(kandidat["url"].encode()).hexdigest()[:12] + "." +
                        (kandidat.get("typ") or "mp3"))
    with open(pfad, "wb") as f:
        f.write(daten)
    return pfad


# ---------------------------------------------------------------------------------------------------- mischen
def mischen(video, musik, ziel, dauer, lautstaerke_db=-20):
    """Musik in Schleife unter die Stimme legen: Grundlautstaerke lautstaerke_db, waehrend Sprache weiter abgesenkt
    (Sidechain-Kompression), Ein-/Ausblenden, Limiter. Das Bild wird nur kopiert."""
    ende = max(0.0, float(dauer) - 2.5)
    filt = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={float(lautstaerke_db):.1f}dB,"
            f"afade=t=in:d=1.5,afade=t=out:st={ende:.2f}:d=2.5[m];"
            "[0:a]aresample=48000,asplit=2[sprache][steuer];"
            "[m][steuer]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=600[unter];"
            "[sprache][unter]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89[a]")
    _ffmpeg(["-i", video, "-stream_loop", "-1", "-i", musik, "-filter_complex", filt, "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", f"{float(dauer):.3f}",
             "-movflags", "+faststart", ziel], timeout=1800)
    return ziel


def namensnennung(asset):
    """Zeile fuer die Videobeschreibung."""
    if not asset:
        return None
    if asset.get("lizenz") == "eigen":
        return "Musik: eigene, erzeugte Klangfläche."
    if asset.get("lizenz") == "rechte":
        return "Musik: eigene Datei (Nutzungsrechte liegen beim Kanal)."
    return (f"Musik: „{asset.get('titel') or 'Musik'}“ von {asset.get('urheber') or 'unbekannt'} – "
            f"{asset.get('lizenz_text')}" + (f" ({asset['lizenz_url']})" if asset.get("lizenz_url") else "")
            + f" – Quelle: {asset.get('quelle')}")
