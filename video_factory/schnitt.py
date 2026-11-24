"""Schnitt-Agent (FFmpeg): je Szene ein Clip (Bild mit langsamem Zoom, Ein-/Ausblendung, Sprachausgabe), dann
Verketten, Untertitel einbrennen, Lautheit normalisieren (EBU R128) -> MP4 (H.264 + AAC).
Formate: Longform 1920x1080 (16:9), Shorts 1080x1920 (9:16). Thumbnails mit PIL (drei Varianten)."""
import json
import os
import re
import subprocess

FORMATE = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
FPS = 25
QUALITAET = {"standard": {"crf": 23, "preset": "veryfast"}, "hoch": {"crf": 20, "preset": "medium"},
             "entwurf": {"crf": 30, "preset": "ultrafast"}}


class SchnittFehler(Exception):
    pass


def _ffmpeg(args, timeout=1800):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args, capture_output=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise SchnittFehler(r.stderr.decode("utf-8", "ignore")[-500:] or "FFmpeg-Fehler")


def clip(bild, audio, dauer, ziel, fmt="16:9", qualitaet="standard", nr=0):
    """Ein Szenen-Clip: Bild (zugeschnitten, leichter Zoom - abwechselnd hinein/heraus), Ton mit Pause aufgefuellt."""
    w, h = FORMATE[fmt]
    q = QUALITAET[qualitaet]
    frames = max(1, int(round(dauer * FPS)))
    zoom = "min(zoom+0.0005,1.10)" if nr % 2 == 0 else "if(eq(on,1),1.10,max(zoom-0.0005,1.0))"
    vf = (f"scale={int(w * 1.1)}:{int(h * 1.1)}:force_original_aspect_ratio=increase,"
          f"crop={int(w * 1.1)}:{int(h * 1.1)},"
          f"zoompan=z='{zoom}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={FPS},"
          f"fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.0, dauer - 0.25):.3f}:d=0.25,format=yuv420p")
    _ffmpeg(["-i", bild, "-i", audio, "-filter_complex", f"[0:v]{vf}[v];[1:a]apad,atrim=0:{dauer:.3f},"
             "aresample=48000[a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", q["preset"],
             "-crf", str(q["crf"]), "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-t", f"{dauer:.3f}",
             ziel])
    return ziel


def zusammenfuegen(clips, srt_pfad, ziel, fmt="16:9", qualitaet="standard", untertitel=True, schrift=None):
    """Clips verketten, Untertitel einbrennen (optional), Lautheit normalisieren -> MP4."""
    ordner = os.path.dirname(os.path.abspath(ziel))
    liste = os.path.join(ordner, "clips.txt")
    with open(liste, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    roh = os.path.join(ordner, "roh.mp4")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", liste, "-c", "copy", roh])
    q = QUALITAET[qualitaet]
    w, h = FORMATE[fmt]
    groesse = (schrift or {}).get("groesse") or (18 if fmt == "16:9" else 13)
    rand = (schrift or {}).get("rand") or (40 if fmt == "16:9" else 220)
    vf = []
    if untertitel and srt_pfad:
        stil = (f"FontName=DejaVu Sans,FontSize={groesse},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                f"BorderStyle=1,Outline=2,Shadow=0,MarginV={rand},Alignment=2")
        vf = ["-vf", f"subtitles={os.path.basename(srt_pfad)}:force_style='{stil}'"]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", "roh.mp4"] + vf +
                       ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", q["preset"],
                        "-crf", str(q["crf"]), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                        "-movflags", "+faststart", os.path.basename(ziel)],
                       capture_output=True, timeout=3600, cwd=ordner)
    if r.returncode != 0:
        raise SchnittFehler(r.stderr.decode("utf-8", "ignore")[-500:])
    os.remove(roh)
    return ziel


def pruefen_datei(pfad):
    """ffprobe -> {"dauer", "breite", "hoehe", "video", "audio"}"""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,"
                        "width,height", "-of", "json", pfad], capture_output=True, timeout=120)
    if r.returncode != 0:
        raise SchnittFehler("ffprobe: Datei nicht lesbar")
    d = json.loads(r.stdout or b"{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {"dauer": float((d.get("format") or {}).get("duration") or 0), "breite": v.get("width"),
            "hoehe": v.get("height"), "video": v.get("codec_name"), "audio": a.get("codec_name")}


def schwarzbilder(pfad, min_dauer=0.6):
    """Abschnitte mit (fast) schwarzem Bild -> [(start, ende)]"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", pfad, "-vf", f"blackdetect=d={min_dauer}:pix_th=0.08",
                        "-an", "-f", "null", "-"], capture_output=True, timeout=1800)
    return [(float(a), float(b)) for a, b in
            re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr.decode("utf-8", "ignore"))]


# ---------------------------------------------------------------- Thumbnails
def _kurztitel(titel, max_woerter=6):
    """Kurzer Thumbnail-Text: Teil vor " | ", ": ", " – " oder " - " (Bindestriche in Woertern bleiben)."""
    w = re.split(r"\s[|–-]\s|:\s", titel, maxsplit=1)[0].split() or titel.split()
    return " ".join(w[:max_woerter])


def thumbnails(titel, bild, ordner, schrift_fett):
    """Drei Thumbnail-Konzepte (1280x720): Bild mit dunklem Verlauf, Farbfläche, geteilt. -> [pfade]"""
    from PIL import Image, ImageDraw, ImageFont
    text = _kurztitel(titel).upper()
    aus = []

    from video_factory.assets import umbrechen

    def schreiben(d, x, y, breite, groesse, farbe=(255, 255, 255)):
        font = ImageFont.truetype(schrift_fett, groesse)
        while groesse > 40 and len(umbrechen(text, font, breite, 99)) > 3:      # kleiner, bis es in 3 Zeilen passt
            groesse -= 6
            font = ImageFont.truetype(schrift_fett, groesse)
        for z in umbrechen(text, font, breite, 3):
            d.text((x + 3, y + 3), z, font=font, fill=(0, 0, 0))
            d.text((x, y), z, font=font, fill=farbe)
            y += int(groesse * 1.12)

    def grund():
        if bild and os.path.exists(bild):
            im = Image.open(bild).convert("RGB")
            r = max(1280 / im.width, 720 / im.height)
            im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
            return im.crop(((im.width - 1280) // 2, (im.height - 720) // 2, (im.width - 1280) // 2 + 1280,
                            (im.height - 720) // 2 + 720))
        return Image.new("RGB", (1280, 720), (30, 41, 59))
    # A: Bild + Verlauf links, gelber Text
    im = grund()
    schatten = Image.new("L", (1280, 720))
    ImageDraw.Draw(schatten).rectangle([0, 0, 1280, 720], fill=0)
    for x in range(1280):
        ImageDraw.Draw(schatten).line([(x, 0), (x, 720)], fill=int(max(0, 220 - x * 0.25)))
    im = Image.composite(Image.new("RGB", (1280, 720), (0, 0, 0)), im, schatten)
    schreiben(ImageDraw.Draw(im), 60, 200, 760, 96, (250, 204, 21))
    aus.append(im)
    # B: Farbflaeche mit grossem Text
    im = Image.new("RGB", (1280, 720), (37, 99, 235))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 600, 1280, 720], fill=(250, 204, 21))
    schreiben(d, 70, 150, 1140, 110)
    aus.append(im)
    # C: geteilt - links Farbe mit Text, rechts Bild
    im = Image.new("RGB", (1280, 720), (17, 24, 39))
    rechts = grund().crop((320, 0, 960, 720))
    im.paste(rechts, (640, 0))
    schreiben(ImageDraw.Draw(im), 50, 180, 560, 84)
    aus.append(im)
    pfade = []
    for i, x in enumerate(aus, 1):
        p = os.path.join(ordner, f"thumbnail_{i}.jpg")
        x.save(p, "JPEG", quality=90)
        pfade.append(p)
    return pfade
