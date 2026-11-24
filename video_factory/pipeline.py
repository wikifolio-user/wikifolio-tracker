"""Orchestrierung der Video Factory: Schritte mit Status, Protokoll, Wiederholung und Fortsetzen.

Schritte: skript -> storyboard -> bilder -> stimme -> schnitt -> thumbnail -> beschreibung -> qualitaet.
Jeder Schritt ist einzeln ausfuehrbar; ein fehlgeschlagener Schritt stoppt den Lauf, das Projekt bleibt erhalten
und laesst sich ab dort fortsetzen. Nichts wird als erledigt markiert, was nicht wirklich erzeugt wurde.
Projekt-dict (JSON-faehig): siehe neues_projekt()."""
import datetime
import json
import os
import uuid

from video_factory import assets as AS
from video_factory import schnitt as SC
from video_factory import skript as SK
from video_factory import stimme as ST
from video_factory import storyboard as SB

SCHRITTE = ["skript", "storyboard", "bilder", "stimme", "schnitt", "thumbnail", "beschreibung", "qualitaet"]
SCHRITT_TEXT = {"skript": "Skript", "storyboard": "Storyboard", "bilder": "Bildmaterial", "stimme": "KI-Stimme",
                "schnitt": "Schnitt, Untertitel & MP4", "thumbnail": "Thumbnails", "beschreibung": "Titel, Beschreibung "
                "& Kapitel", "qualitaet": "Qualitätskontrolle"}


def jetzt():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def neues_projekt(auftrag, dauer_min=5, sprache="de", fmt="16:9", qualitaet="standard", untertitel=True,
                  skript=None, stimme=ST.STANDARD, tempo=1.0, aussprache=None):
    if not (auftrag or "").strip() and not skript:
        raise ValueError("Bitte einen Auftrag eingeben.")
    if fmt not in SC.FORMATE:
        raise ValueError("Unbekanntes Format.")
    if not 0.5 <= float(dauer_min) <= 30:
        raise ValueError("Die Länge muss zwischen 0,5 und 30 Minuten liegen.")
    if stimme not in ST.STIMMEN:
        raise ValueError("Unbekannte Stimme.")
    p = {"id": uuid.uuid4().hex[:10], "erstellt": jetzt(), "auftrag": (auftrag or "").strip()[:2000],
         "dauer_min": float(dauer_min), "sprache": sprache, "format": fmt, "qualitaet": qualitaet,
         "untertitel": bool(untertitel), "stimme": stimme, "tempo": float(tempo), "aussprache": dict(aussprache or {}),
         "skript": skript, "szenen": [], "dateien": {}, "schritte": {s: {"status": "offen"} for s in SCHRITTE},
         "protokoll": [], "kosten": {"posten": [], "summe": 0.0}, "bericht": None, "status": "entwurf"}
    if skript:
        p["schritte"]["skript"] = {"status": "ok", "zeit": jetzt(), "meldung": "Skript von Hand eingefügt."}
    return p


def _log(p, text, art="info"):
    p["protokoll"].append({"zeit": jetzt(), "art": art, "text": text})
    p["protokoll"] = p["protokoll"][-300:]


def _pfad(ctx, *teile):
    return os.path.join(ctx["ordner"], *teile)


# ---------------------------------------------------------------- Schritte
def s_skript(p, ctx):
    if p.get("skript"):
        return "Skript vorhanden (" + ("von Hand" if p["skript"].get("quelle") == "manuell" else "KI") + ")."
    p["skript"] = SK.mit_ki(ctx.get("ki"), p["auftrag"], p["dauer_min"], p["sprache"])
    p["kosten"]["posten"].append({"dienst": "KI-Skript (kostenloses Kontingent)", "betrag": 0.0})
    return f"Skript „{p['skript']['titel']}“ mit {SK.woerter(p['skript'])} Wörtern erstellt."


def s_storyboard(p, ctx):
    p["szenen"] = SB.erstellen(p["skript"])
    return f"{len(p['szenen'])} Szenen, geplant ca. {SB.zeit_text(sum(s['dauer_plan'] for s in p['szenen']))}."


def s_bilder(p, ctx):
    ordner = _pfad(ctx, "bilder")
    os.makedirs(ordner, exist_ok=True)
    gesehen = {(s.get("asset") or {}).get("url") for s in p["szenen"] if s.get("asset")}
    frei, eigen, hinweise = 0, 0, []
    for s in p["szenen"]:
        a = s.get("asset")
        if a and a.get("pfad") and os.path.exists(a["pfad"]):
            continue                                   # schon vorhanden (Wiederholung)
        kandidat, fehler = (AS.suchen(s["bild"], ctx["get"], gesehen) if ctx.get("get") and s.get("bild")
                            else (None, ["keine Bildsuche"]))
        if kandidat:
            try:
                kandidat["pfad"] = AS.laden(kandidat, ctx["get"], ordner)
                s["asset"] = kandidat
                gesehen.add(kandidat["url"])
                frei += 1
                continue
            except Exception as ex:
                fehler.append(f"Laden: {ex}")
        teil = sum(1 for x in p["szenen"] if x["kapitel_nr"] == s["kapitel_nr"] and x["nr"] < s["nr"])
        s["asset"] = AS.folie(s["text"], s["kapitel"], os.path.join(ordner, f"folie_{s['nr']:03d}.jpg"),
                              *SC.FORMATE[p["format"]], nr=s["kapitel_nr"], teil=teil)
        s["asset"]["grund"] = "; ".join(fehler)[:200]
        eigen += 1
        if fehler:
            hinweise.append(fehler[-1])
    return f"{frei} lizenzfreie Bilder, {eigen} eigene Grafik-Folien." + (
        f" Grund für Folien u. a.: {hinweise[0]}" if hinweise else "")


def s_stimme(p, ctx):
    modell = ST.stimme_laden(p["stimme"], ctx.get("stimmen_ordner") or _pfad(ctx, "stimmen"), ctx["get"])
    ordner = _pfad(ctx, "audio")
    for s in p["szenen"]:
        ziel = os.path.join(ordner, f"szene_{s['nr']:03d}.wav")
        if s.get("audio") and os.path.exists(s["audio"]["pfad"]) and s["audio"].get("text") == s["text"]:
            continue
        d = ST.sprechen(ST.aussprache(s["text"], p.get("aussprache")), modell, ziel, p.get("tempo", 1.0))
        s["audio"] = {"pfad": ziel, "dauer": round(d, 3), "text": s["text"]}
    gesamt = SB.zeiten_setzen(p["szenen"])
    return f"Sprachausgabe für {len(p['szenen'])} Szenen, Gesamtdauer {SB.zeit_text(gesamt)} " \
           f"(Stimme {ST.STIMMEN[p['stimme']]['name']}, Lizenz {ST.STIMMEN[p['stimme']]['lizenz']})."


def s_schnitt(p, ctx):
    SB.zeiten_setzen(p["szenen"])
    ordner = _pfad(ctx, "clips")
    os.makedirs(ordner, exist_ok=True)
    clips = []
    for s in p["szenen"]:
        ziel = os.path.join(ordner, f"clip_{s['nr']:03d}.mp4")
        SC.clip(s["asset"]["pfad"], s["audio"]["pfad"], s["dauer"], ziel, p["format"], p["qualitaet"], s["nr"])
        clips.append(ziel)
    bloecke = SB.untertitel(p["szenen"], 42 if p["format"] == "16:9" else 26)
    srt = _pfad(ctx, "untertitel.srt")
    with open(srt, "w", encoding="utf-8") as f:
        f.write(SB.srt(bloecke))
    with open(_pfad(ctx, "untertitel.vtt"), "w", encoding="utf-8") as f:
        f.write(SB.vtt(bloecke))
    video = _pfad(ctx, "video.mp4")
    SC.zusammenfuegen(clips, srt, video, p["format"], p["qualitaet"], p["untertitel"])
    info = SC.pruefen_datei(video)
    p["dateien"].update(video=video, srt=srt, vtt=_pfad(ctx, "untertitel.vtt"), video_info=info,
                        groesse_mb=round(os.path.getsize(video) / 1e6, 1))
    return f"MP4 {info['breite']}×{info['hoehe']}, {SB.zeit_text(info['dauer'])}, {p['dateien']['groesse_mb']} MB."


def s_thumbnail(p, ctx):
    # nur ein Foto mit geklaerter Lizenz als Hintergrund - eigene Folien tragen schon Text
    bild = next((s["asset"]["pfad"] for s in p["szenen"] if (s.get("asset") or {}).get("lizenz") not in (None, "eigen")),
                None)
    p["dateien"]["thumbnails"] = SC.thumbnails(p["skript"]["titel"], bild, ctx["ordner"], AS.SCHRIFT)
    return "3 Thumbnail-Konzepte erstellt (Titeltext, Bild mit geklärter Lizenz oder eigene Grafik)."


def beschreibung_text(p):
    sk = p["skript"]
    teile = [sk["titel"], "", sk.get("beschreibung") or ""]
    marken = SB.kapitelmarken(p["szenen"])
    if len(marken) >= 3:                             # YouTube erkennt Kapitel ab drei Marken mit 0:00 am Anfang
        teile += ["", "Kapitel:"] + [f"{SB.zeit_text(t)} {k}" for t, k in marken]
    nennungen = sorted({AS.namensnennung(s["asset"]) for s in p["szenen"] if AS.namensnennung(s.get("asset"))})
    teile += ["", "Bildquellen und Lizenzen:"] + (nennungen or ["Eigene Grafiken."])
    st = ST.STIMMEN[p["stimme"]]
    teile += ["", f"Sprecherstimme: KI-generiert (Piper, Stimme {st['name']}, {st['lizenz']}).",
              "Hinweis: Dieses Video wurde mit KI-Unterstützung erstellt und redaktionell geprüft."]
    return "\n".join(teile).strip()


def s_beschreibung(p, ctx):
    text = beschreibung_text(p)
    pfad = _pfad(ctx, "beschreibung.txt")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(text)
    lizenzen = [{"szene": s["nr"], **{k: (s.get("asset") or {}).get(k) for k in
                                      ("anbieter", "titel", "urheber", "lizenz", "lizenz_text", "lizenz_url", "quelle",
                                       "namensnennung_noetig")}} for s in p["szenen"]]
    with open(_pfad(ctx, "lizenzen.json"), "w", encoding="utf-8") as f:
        json.dump(lizenzen, f, ensure_ascii=False, indent=1)
    p["dateien"].update(beschreibung=pfad, lizenzen=_pfad(ctx, "lizenzen.json"), titel=p["skript"]["titel"],
                        tags=p["skript"].get("tags") or [])
    return f"Beschreibung mit {len(SB.kapitelmarken(p['szenen']))} Kapitelmarken und Quellenangaben."


def qualitaetsbericht(p):
    """Pruefungen -> {"punkte": [(name, ergebnis ok/warn/fehler, text)], "freigabe_noetig", "blockiert"}"""
    pk = []
    info = p["dateien"].get("video_info") or {}
    plan = sum(s.get("dauer") or 0 for s in p["szenen"])
    w, h = SC.FORMATE[p["format"]]
    pk.append(("Videodatei", "ok" if info.get("video") == "h264" and info.get("audio") == "aac" else "fehler",
               f"Video {info.get('video')}, Audio {info.get('audio')}"))
    pk.append(("Auflösung", "ok" if (info.get("breite"), info.get("hoehe")) == (w, h) else "fehler",
               f"{info.get('breite')}×{info.get('hoehe')} (Soll {w}×{h})"))
    abw = abs((info.get("dauer") or 0) - plan) / plan * 100 if plan else 100
    pk.append(("Ton synchron / Dauer", "ok" if abw <= 2 else "warn" if abw <= 5 else "fehler",
               f"{SB.zeit_text(info.get('dauer') or 0)} bei {SB.zeit_text(plan)} geplant (Abweichung {abw:.1f} %)"))
    ziel = p["dauer_min"] * 60
    pk.append(("Ziellänge", "ok" if abs(plan - ziel) / ziel <= 0.2 else "warn",
               f"{SB.zeit_text(plan)} statt {SB.zeit_text(ziel)}"))
    schwarz = p["dateien"].get("schwarzbilder") or []
    pk.append(("Schwarze Bilder", "ok" if not schwarz else "fehler", "keine" if not schwarz else
               ", ".join(f"{a:.1f}–{b:.1f} s" for a, b in schwarz[:5])))
    fehlt = [s["nr"] for s in p["szenen"] if not (s.get("asset") or {}).get("pfad") or not s.get("audio")]
    pk.append(("Vollständige Szenen", "ok" if not fehlt else "fehler", "alle Szenen mit Bild und Ton" if not fehlt
               else f"fehlend: Szenen {fehlt[:10]}"))
    ohne = [s["nr"] for s in p["szenen"] if (s.get("asset") or {}).get("lizenz") not in ("eigen", "cc0", "pdm", "by")]
    pk.append(("Lizenzen", "ok" if not ohne else "fehler", "alle Bilder frei nutzbar (CC0/PD/CC BY oder eigen)"
               if not ohne else f"ungeklärt: Szenen {ohne}"))
    by = [s["nr"] for s in p["szenen"] if (s.get("asset") or {}).get("namensnennung_noetig")]
    pk.append(("Namensnennung", "ok", f"{len(by)} Bild(er) mit Namensnennung – steht in der Beschreibung" if by
               else "keine nötig"))
    eigen = sum(1 for s in p["szenen"] if (s.get("asset") or {}).get("lizenz") == "eigen")
    pk.append(("Bildmaterial", "ok" if eigen <= len(p["szenen"]) / 2 else "warn",
               f"{eigen} von {len(p['szenen'])} Szenen mit eigener Grafik statt Foto"))
    doppelt = len(p["szenen"]) - len({(s.get("asset") or {}).get("pfad") for s in p["szenen"]})
    pk.append(("Doppelte Bilder", "ok" if doppelt == 0 else "warn", f"{doppelt} Wiederholungen"))
    pk.append(("Untertitel", "ok" if p["dateien"].get("srt") else "fehler", "SRT und VTT erzeugt" +
               (", eingebrannt" if p["untertitel"] else "")))
    offen = (p["skript"] or {}).get("zu_pruefen") or []
    gepr = (p["skript"] or {}).get("geprueft")
    pk.append(("Faktenprüfung", "ok" if gepr else "warn",
               "Skript als geprüft markiert" if gepr else f"{len(offen)} Aussage(n) vor Veröffentlichung prüfen"
               + (": " + "; ".join(offen[:3]) if offen else " – KI-Texte immer gegenlesen")))
    pk.append(("Originalität", "ok", "eigenes Skript aus Auftrag bzw. eigenem Text – keine Übernahme fremder Videos"))
    pk.append(("Affiliate-Kennzeichnung", "ok", "keine Affiliate-Links im Video"))
    blockiert = any(e == "fehler" for _, e, _ in pk)
    freigabe = blockiert or any(e == "warn" for n, e, _ in pk if n in ("Faktenprüfung", "Lizenzen"))
    return {"punkte": pk, "blockiert": blockiert, "freigabe_noetig": freigabe, "zeit": jetzt()}


def s_qualitaet(p, ctx):
    video = p["dateien"].get("video")
    if not video or not os.path.exists(video):
        raise RuntimeError("Kein Video vorhanden.")
    p["dateien"]["schwarzbilder"] = SC.schwarzbilder(video)
    p["bericht"] = qualitaetsbericht(p)
    fehler = [n for n, e, _ in p["bericht"]["punkte"] if e == "fehler"]
    warn = [n for n, e, _ in p["bericht"]["punkte"] if e == "warn"]
    return ("Blockiert: " + ", ".join(fehler)) if fehler else (
        "Bestanden" + (f", Hinweise: {', '.join(warn)}" if warn else "") + " – Veröffentlichung nur nach Freigabe.")


AUSFUEHREN = {"skript": s_skript, "storyboard": s_storyboard, "bilder": s_bilder, "stimme": s_stimme,
              "schnitt": s_schnitt, "thumbnail": s_thumbnail, "beschreibung": s_beschreibung, "qualitaet": s_qualitaet}
ABHAENGIG = {"storyboard": ["bilder", "stimme", "schnitt", "thumbnail", "beschreibung", "qualitaet"],
             "bilder": ["schnitt", "thumbnail", "beschreibung", "qualitaet"],
             "stimme": ["schnitt", "beschreibung", "qualitaet"], "schnitt": ["qualitaet"],
             "skript": ["storyboard", "bilder", "stimme", "schnitt", "thumbnail", "beschreibung", "qualitaet"]}


def zuruecksetzen(p, schritt):
    """Schritt (und alle davon abhaengigen) wieder auf "offen" - z. B. nach Aenderung einer Szene."""
    for s in [schritt] + ABHAENGIG.get(schritt, []):
        p["schritte"][s] = {"status": "offen"}
    p["status"] = "in_arbeit"
    return p


def ausfuehren(p, ctx, bis=None, nur=None, speichern=None):
    """Offene Schritte der Reihe nach ausfuehren (oder nur einen). Stoppt beim ersten Fehler. -> Projekt"""
    reihe = [nur] if nur else SCHRITTE[: SCHRITTE.index(bis) + 1] if bis else SCHRITTE
    os.makedirs(ctx["ordner"], exist_ok=True)
    p["status"] = "in_arbeit"
    for name in reihe:
        if not nur and p["schritte"][name]["status"] == "ok":
            continue
        p["schritte"][name] = {"status": "laeuft", "zeit": jetzt()}
        if speichern:
            speichern(p)
        try:
            meldung = AUSFUEHREN[name](p, ctx)
            p["schritte"][name] = {"status": "ok", "zeit": jetzt(), "meldung": meldung}
            _log(p, f"{SCHRITT_TEXT[name]}: {meldung}")
        except Exception as ex:
            p["schritte"][name] = {"status": "fehler", "zeit": jetzt(), "meldung": f"{type(ex).__name__}: {ex}"[:500]}
            _log(p, f"{SCHRITT_TEXT[name]} fehlgeschlagen: {ex}", "fehler")
            p["status"] = "fehler"
            if speichern:
                speichern(p)
            return p
        if speichern:
            speichern(p)
    if all(p["schritte"][s]["status"] == "ok" for s in SCHRITTE):
        p["status"] = "blockiert" if (p.get("bericht") or {}).get("blockiert") else "freigabe_noetig"
    p["kosten"]["summe"] = round(sum(x["betrag"] for x in p["kosten"]["posten"]), 2)
    return p
