"""Faceless YouTube - Beobachtungen: gespeicherte Suchen/Nischen, die der Recherche-Agent taeglich ausfuehrt.
Reine Logik (ohne Streamlit, ohne Netz). Daraus entstehen ein Verlauf je Nische (Nischen-Score und Teilwerte) und
Hinweise auf NEUE Ausreisser (Videos kleiner Kanaele mit vielen Aufrufen, die beim letzten Lauf noch nicht da waren).

Speicher:
  state/youtube.json             "beobachtungen": [{"id", "begriff", "tage", "format", "region", "sprache", "aktiv"}]
  state/youtube_recherche.json   {"verlauf": {bid: [{"datum", "score", "teile", "median_views", "treffer"}]},
                                  "gesehen": {bid: [video_id]}, "neu": {bid: [video]}, "laeufe": [...], "stand"}"""
import datetime
import uuid

import youtube_api as YA
import youtube_nische as YN

MAX_BEOBACHTUNGEN = 10
MAX_VERLAUF = 400
MAX_GESEHEN = 600
AUSREISSER_FAKTOR = 3.0          # Aufrufe mindestens 3x so hoch wie die Abonnenten des Kanals
KLEIN_ABOS = 50000
PFAD_RECHERCHE = "state/youtube_recherche.json"


def neue_beobachtung(begriff, tage=90, fmt="Longform", region="DE", sprache="de"):
    b = str(begriff or "").strip()
    if not b:
        raise ValueError("Bitte einen Suchbegriff angeben.")
    if fmt not in YA.FORMATE:
        raise ValueError("Unbekanntes Format.")
    return {"id": uuid.uuid4().hex[:8], "begriff": b[:120], "tage": int(tage or 0), "format": fmt,
            "region": region or "", "sprache": sprache or "", "aktiv": True,
            "angelegt": datetime.date.today().isoformat()}


def hinzufuegen(liste, eintrag):
    """Gleiche Suche nur einmal, hoechstens MAX_BEOBACHTUNGEN. Wirft ValueError."""
    schl = lambda x: (x["begriff"].lower(), x["tage"], x["format"], x["region"], x["sprache"])  # noqa: E731
    if any(schl(x) == schl(eintrag) for x in liste):
        return liste
    if len(liste) >= MAX_BEOBACHTUNGEN:
        raise ValueError(f"Höchstens {MAX_BEOBACHTUNGEN} Beobachtungen (jede kostet täglich etwa 102 Einheiten).")
    return liste + [eintrag]


def kosten_pro_tag(liste):
    return sum(YA.SCHAETZUNG["suche"] for x in liste if x.get("aktiv", True))


def ausreisser(videos):
    """Videos kleiner Kanaele mit Aufrufen >= AUSREISSER_FAKTOR x Abonnenten, staerkste zuerst."""
    return sorted([v for v in videos if v.get("abonnenten") is not None and v["abonnenten"] < KLEIN_ABOS
                   and (v.get("faktor_kanal") or 0) >= AUSREISSER_FAKTOR], key=lambda v: -(v.get("faktor_kanal") or 0))


def _kurz(v):
    return {k: v.get(k) for k in ("id", "titel", "kanal", "kanal_id", "views", "abonnenten", "faktor_kanal", "url",
                                  "datum", "alter_tage")}


def ergebnis_einfuegen(stand, b, videos, datum):
    """Ergebnis eines Laufs fuer Beobachtung b einfuegen. -> neuer Stand (Kopie)."""
    s = {k: dict(v) if isinstance(v, dict) else v for k, v in (stand or {}).items()}
    for k in ("verlauf", "gesehen", "neu"):
        s[k] = dict(s.get(k) or {})
    bew = YN.bewerten(videos, b["tage"])
    eintrag = {"datum": datum, "score": bew["gesamt"], "teile": bew["teile"], "median_views": bew["median_views"],
               "treffer": len(videos), "vorlaeufig": bew["vorlaeufig"]}
    verlauf = [x for x in s["verlauf"].get(b["id"]) or [] if x.get("datum") != datum] + [eintrag]
    s["verlauf"][b["id"]] = verlauf[-MAX_VERLAUF:]
    gesehen = list(s["gesehen"].get(b["id"]) or [])
    erster_lauf = b["id"] not in (stand or {}).get("gesehen", {})
    neu = [] if erster_lauf else [_kurz(v) for v in ausreisser(videos) if v.get("id") not in gesehen]
    s["neu"][b["id"]] = (neu + [x for x in s["neu"].get(b["id"]) or [] if x["id"] not in {n["id"] for n in neu}])[:30]
    for v in videos:
        if v.get("id") and v["id"] not in gesehen:
            gesehen.append(v["id"])
    s["gesehen"][b["id"]] = gesehen[-MAX_GESEHEN:]
    s["stand"] = datum
    return s, len(neu)


def aufraeumen(stand, beobachtungen):
    """Daten geloeschter Beobachtungen entfernen."""
    ids = {b["id"] for b in beobachtungen}
    s = dict(stand or {})
    for k in ("verlauf", "gesehen", "neu"):
        s[k] = {bid: v for bid, v in (s.get(k) or {}).items() if bid in ids}
    return s


def lauf(beobachtungen, abruf, speicher_api, grenze, jetzt, stand=None):
    """Alle aktiven Beobachtungen ausfuehren, solange die Tagesgrenze reicht.
    -> (neuer Stand, verbrauchte Einheiten, Protokollzeilen)"""
    datum = jetzt.date().isoformat()
    stand = aufraeumen(stand, beobachtungen)
    z = YA.Zaehler(abruf)
    zeilen = []
    for b in [x for x in beobachtungen if x.get("aktiv", True)]:
        try:
            YA.pruefen(YA.buchen(speicher_api, z.einheiten, jetzt), YA.SCHAETZUNG["suche"], grenze, jetzt)
        except YA.ApiFehler as ex:
            zeilen.append(f"„{b['begriff']}“ übersprungen: {ex}")
            continue
        try:
            r = YA.suche(z, b["begriff"], b["tage"], b["format"], b["region"], b["sprache"], "viewCount", jetzt)
        except YA.ApiFehler as ex:
            zeilen.append(f"„{b['begriff']}“: {ex}")
            continue
        stand, n = ergebnis_einfuegen(stand, b, r["videos"], datum)
        score = stand["verlauf"][b["id"]][-1]["score"]
        zeilen.append(f"„{b['begriff']}“: Score {score if score is not None else '–'}, {len(r['videos'])} Treffer, "
                      f"{n} neue Ausreißer")
    laeufe = list((stand or {}).get("laeufe") or [])
    stand = dict(stand or {}, laeufe=(laeufe + [{"zeit": jetzt.isoformat(timespec="seconds"),
                                                 "einheiten": z.einheiten, "zeilen": zeilen}])[-30:])
    return stand, z.einheiten, zeilen
