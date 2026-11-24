"""Bild-Agent: je Szene ein Bild mit geklaerter, kommerziell nutzbarer Lizenz - oder eine eigene Grafik-Folie.

Quellen (ohne Schluessel): Openverse (api.openverse.org) und Wikimedia Commons. Erlaubt sind nur CC0, Public Domain
(PDM) und CC BY (Namensnennung) - ShareAlike, NonCommercial und NoDerivatives werden nie verwendet. Je Asset werden
Lizenz, Urheber, Quelle, Lizenz-Link und der Text fuer die Namensnennung gespeichert. Findet sich nichts, wird eine
eigene Folie (Text auf Verlauf, PIL) erzeugt - die ist immer frei nutzbar und wird als "eigene Grafik" ausgewiesen.
Fremde YouTube-Videos oder Bilder aus Suchmaschinen werden nie verwendet."""
import hashlib
import html
import os
import re

ERLAUBT = {"cc0": "CC0 1.0", "pdm": "Public Domain Mark", "by": "CC BY"}
UA = {"User-Agent": "FinanzDashboard-VideoFactory/1.0 (privates Projekt; Kontakt ueber GitHub)"}
MAX_BYTES = 15_000_000
MIN_BREITE = 1000
SCHRIFT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SCHRIFT_NORMAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FARBEN = [((17, 24, 39), (37, 99, 235)), ((20, 30, 48), (16, 185, 129)), ((30, 27, 75), (124, 58, 237)),
          ((28, 25, 23), (234, 88, 12)), ((12, 74, 110), (14, 165, 233))]


def _text(x):
    return re.sub(r"<[^>]+>", "", html.unescape(str(x or ""))).strip()


# ---------------------------------------------------------------- Openverse
def openverse_url(suche):
    from urllib.parse import quote
    return (f"https://api.openverse.org/v1/images/?q={quote(suche)}&license=cc0,pdm,by&license_type=commercial"
            "&aspect_ratio=wide&size=large&mature=false&page_size=10")


def openverse_parsen(daten):
    """Openverse-Antwort -> Kandidaten [{url, lizenz, ...}] (nur erlaubte Lizenzen, genug Aufloesung)."""
    aus = []
    for r in (daten or {}).get("results") or []:
        lz = str(r.get("license") or "").lower()
        if lz not in ERLAUBT or not r.get("url"):
            continue
        if (r.get("width") or 0) and r["width"] < MIN_BREITE:
            continue
        aus.append({"url": r["url"], "lizenz": lz, "lizenz_text": f"{ERLAUBT[lz]} {r.get('license_version') or ''}".strip(),
                    "lizenz_url": r.get("license_url") or "", "urheber": _text(r.get("creator")) or "unbekannt",
                    "titel": _text(r.get("title")), "quelle": r.get("foreign_landing_url") or r["url"],
                    "anbieter": f"Openverse / {r.get('source') or r.get('provider') or '?'}",
                    "namensnennung_noetig": lz == "by", "breite": r.get("width"), "hoehe": r.get("height")})
    return aus


# ---------------------------------------------------------------- Wikimedia Commons
def wikimedia_url(suche):
    from urllib.parse import quote
    return ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
            f"&gsrsearch={quote(suche + ' filetype:bitmap')}&gsrnamespace=6&gsrlimit=10&prop=imageinfo"
            "&iiprop=url|extmetadata|size&iiurlwidth=1920"
            "&iiextmetadatafilter=LicenseShortName|Artist|AttributionRequired|LicenseUrl|ObjectName")


def _lizenz_wikimedia(kurz):
    k = str(kurz or "").lower().replace("-", " ")
    if "sa" in k.split() or "nc" in k.split() or "nd" in k.split() or "share" in k:
        return None
    if k.startswith("cc0") or "cc zero" in k:
        return "cc0"
    if k.startswith("public domain") or k == "pd" or k.startswith("pd "):
        return "pdm"
    if k.startswith("cc by"):
        return "by"
    return None


def wikimedia_parsen(daten):
    aus = []
    for p in (((daten or {}).get("query") or {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        m = ii.get("extmetadata") or {}
        kurz = (m.get("LicenseShortName") or {}).get("value")
        lz = _lizenz_wikimedia(kurz)
        url = ii.get("thumburl") or ii.get("url")
        if not lz or not url or (ii.get("width") or 0) < MIN_BREITE:
            continue
        aus.append({"url": url, "lizenz": lz, "lizenz_text": _text(kurz), "lizenz_url": (m.get("LicenseUrl") or {}).get("value", ""),
                    "urheber": _text((m.get("Artist") or {}).get("value")) or "unbekannt",
                    "titel": _text((m.get("ObjectName") or {}).get("value")) or p.get("title", ""),
                    "quelle": ii.get("descriptionurl") or "", "anbieter": "Wikimedia Commons",
                    "namensnennung_noetig": lz == "by" or (m.get("AttributionRequired") or {}).get("value") == "true",
                    "breite": ii.get("width"), "hoehe": ii.get("height")})
    return aus


def suchen(suche, get, gesehen=()):
    """Erster passender Kandidat (Openverse, dann Wikimedia), der noch nicht verwendet wurde. -> (kandidat, fehler)"""
    fehler = []
    for name, url, parser in (("Openverse", openverse_url(suche), openverse_parsen),
                              ("Wikimedia", wikimedia_url(suche), wikimedia_parsen)):
        try:
            r = get(url, headers=UA, timeout=30)
            if r.status_code != 200:
                fehler.append(f"{name}: HTTP {r.status_code}")
                continue
            for k in parser(r.json()):
                if k["url"] not in gesehen:
                    return k, fehler
            fehler.append(f"{name}: kein passendes Bild mit freier Lizenz")
        except Exception as ex:                       # Netz/JSON - naechste Quelle
            fehler.append(f"{name}: {type(ex).__name__}")
    return None, fehler


def laden(kandidat, get, ordner):
    """Bild herunterladen, pruefen und als JPEG speichern. -> Pfad"""
    from PIL import Image
    r = get(kandidat["url"], headers=UA, timeout=60, stream=True)
    if r.status_code != 200:
        raise IOError(f"HTTP {r.status_code}")
    daten = b""
    for teil in r.iter_content(65536):
        daten += teil
        if len(daten) > MAX_BYTES:
            raise IOError("Bild zu groß")
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.join(ordner, hashlib.sha1(kandidat["url"].encode()).hexdigest()[:16] + ".jpg")
    import io
    with Image.open(io.BytesIO(daten)) as im:
        im = im.convert("RGB")
        if im.width < MIN_BREITE:
            raise IOError("Auflösung zu gering")
        im.save(pfad, "JPEG", quality=90)
    return pfad


# ---------------------------------------------------------------- eigene Grafik
def umbrechen(text, font, max_breite, max_zeilen=4):
    """Zeilenumbruch nach gemessener Textbreite (nie ueber den Rand)."""
    zeilen, akt = [], ""
    for w in str(text).split():
        probe = f"{akt} {w}".strip()
        if akt and font.getlength(probe) > max_breite:
            zeilen.append(akt)
            akt = w
        else:
            akt = probe
    if akt:
        zeilen.append(akt)
    if len(zeilen) > max_zeilen:
        zeilen = zeilen[:max_zeilen]
        zeilen[-1] = zeilen[-1].rstrip(".,;:") + " …"
    return zeilen


def folie(text, kapitel, pfad, breite=1920, hoehe=1080, nr=0, teil=None):
    """Eigene Grafik-Folie: Farbverlauf mit dezenten Formen und dem Kapiteltitel gross (den gesprochenen Text zeigen
    die Untertitel). Immer frei nutzbar."""
    from PIL import Image, ImageDraw, ImageFont
    a, b = FARBEN[nr % len(FARBEN)]
    im = Image.new("RGB", (breite, hoehe), a)
    d = ImageDraw.Draw(im)
    for y in range(hoehe):
        f = y / hoehe
        d.line([(0, y), (breite, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * f * 0.85) for i in range(3)))
    v = (teil or 0) % 3                               # leichte Abwandlung je Szene desselben Kapitels
    for i in range(3):
        r = int(min(breite, hoehe) * (0.18 + 0.12 * i))
        cx, cy = int(breite * (0.82 - 0.1 * v)), int(hoehe * (0.25 + 0.2 * v))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=tuple(min(255, c + 40) for c in b), width=3)
    rand = int(breite * 0.07)
    k = max(24, hoehe // 30)
    d.text((rand, int(hoehe * 0.12)), "KAPITEL", font=ImageFont.truetype(SCHRIFT, k), fill=(226, 232, 240))
    d.rectangle([rand, int(hoehe * 0.12) + k * 1.5, rand + k * 4, int(hoehe * 0.12) + k * 1.5 + 6], fill=(250, 204, 21))
    groesse = max(40, hoehe // 9)
    font = ImageFont.truetype(SCHRIFT, groesse)
    zeilen = umbrechen(kapitel, font, breite - 2 * rand, 3)
    y = int(hoehe * 0.42) - len(zeilen) * groesse * 0.6
    for z in zeilen:
        d.text((rand, y), z, font=font, fill=(255, 255, 255))
        y += int(groesse * 1.2)
    im.save(pfad, "JPEG", quality=92)
    return {"pfad": pfad, "lizenz": "eigen", "lizenz_text": "Eigene Grafik (frei)", "urheber": "eigene Erstellung",
            "quelle": "", "anbieter": "Video Factory", "titel": kapitel, "namensnennung_noetig": False}


def namensnennung(asset):
    """Text fuer die Videobeschreibung (Pflicht bei CC BY)."""
    if not asset or asset.get("lizenz") in (None, "eigen"):
        return None
    return (f"„{asset.get('titel') or 'Bild'}“ von {asset.get('urheber') or 'unbekannt'} – {asset.get('lizenz_text')}"
            + (f" ({asset['lizenz_url']})" if asset.get("lizenz_url") else "") + f" – Quelle: {asset.get('quelle')}")
