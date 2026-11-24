"""Faceless YouTube Phase 2 - Zugriff auf die offizielle YouTube Data API v3. Reine Logik (ohne Streamlit).

- Der Schluessel geht nur im Header "X-Goog-Api-Key" mit, nie in der Adresse. So taucht er weder in
  Fehlertexten von requests noch in Logs auf. Fehlertexte werden zusaetzlich bereinigt.
- Kontingent: YouTube zaehlt Einheiten je Tag (Neustart um Mitternacht pazifischer Zeit). Jeder Abruf wird
  mit seinen Kosten gebucht. Eine eigene Tagesgrenze verhindert, dass das Kontingent ausgeschoepft wird.
- Zwischenspeicher: Ergebnisse (bereits aufbereitet, nicht die Rohantworten) gelten 24 Stunden.
  Dieselbe Abfrage kostet in dieser Zeit kein zweites Mal Kontingent.
Speicherformat (state/youtube_api.json):
  {"kontingent": {"tag": "YYYY-MM-DD", "verbraucht": n},
   "cache": {schluessel: {"art", "zeit", "daten"}}}"""
import datetime
import hashlib
import json
import re
import statistics
from zoneinfo import ZoneInfo

BASIS = "https://www.googleapis.com/youtube/v3/"
KOSTEN = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1, "commentThreads": 1}
TAGESKONTINGENT = 10000
STANDARD_GRENZE = 8000
PAZIFIK = ZoneInfo("America/Los_Angeles")
BERLIN = ZoneInfo("Europe/Berlin")
CACHE_STUNDEN = 24
CACHE_MAX = 20
SHORT_MAX_S = 180               # YouTube Shorts sind hoechstens 3 Minuten lang
MIN_VERGLEICH = 3
SCHAETZUNG = {"trends": 1, "suche": 102, "kanal": 3, "kommentare": 4}

REGIONEN = {"DE": "Deutschland", "AT": "Österreich", "CH": "Schweiz", "US": "USA", "GB": "Großbritannien",
            "CA": "Kanada", "AU": "Australien", "FR": "Frankreich", "ES": "Spanien", "IT": "Italien",
            "NL": "Niederlande", "BR": "Brasilien", "IN": "Indien", "JP": "Japan"}
KATEGORIEN = {"0": "Alle", "1": "Film & Animation", "2": "Autos & Fahrzeuge", "10": "Musik", "15": "Tiere",
              "17": "Sport", "19": "Reisen & Events", "20": "Gaming", "22": "Menschen & Blogs", "23": "Comedy",
              "24": "Unterhaltung", "25": "Nachrichten & Politik", "26": "Praktische Tipps & Styling",
              "27": "Bildung", "28": "Wissenschaft & Technik"}
FORMATE = ("Alle", "Longform", "Shorts")
REIHENFOLGEN = {"viewCount": "meiste Aufrufe", "relevance": "Relevanz", "date": "neueste zuerst"}


class ApiFehler(Exception):
    pass


# ---------------------------------------------------------------------------------------------------- Abruf
def _bereinigen(text, key):
    t = str(text)
    if key:
        t = t.replace(key, "***")
    return re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "***", t)


def _fehlertext(status, antwort, key):
    try:
        f = (antwort.json() or {}).get("error") or {}
    except Exception:
        f = {}
    gruende = {str(e.get("reason") or "") for e in f.get("errors") or [] if isinstance(e, dict)}
    for d in f.get("details") or []:
        if isinstance(d, dict) and d.get("reason"):
            gruende.add(str(d["reason"]))
    if gruende & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
        return ("Das Tageskontingent der YouTube-API ist aufgebraucht. Es startet um Mitternacht pazifischer Zeit "
                f"neu ({neustart_text()}).")
    if gruende & {"keyInvalid", "API_KEY_INVALID", "badRequest"} and "key" in str(f.get("message", "")).lower():
        return "Der YouTube-Schlüssel ist ungültig. Bitte in den Streamlit-Secrets prüfen."
    if gruende & {"API_KEY_SERVICE_BLOCKED", "ipRefererBlocked", "API_KEY_HTTP_REFERRER_BLOCKED",
                  "API_KEY_IP_ADDRESS_BLOCKED"}:
        return ("Der Schlüssel darf diese Anfrage nicht stellen. In der Google Cloud Console prüfen: "
                "API-Einschränkung = YouTube Data API v3, Anwendungseinschränkung = Keine.")
    if gruende & {"accessNotConfigured", "SERVICE_DISABLED"}:
        return "Die YouTube Data API v3 ist im Google-Cloud-Projekt nicht aktiviert."
    if gruende & {"videoChartNotFound", "chartNotFound"}:
        return "Für diese Kategorie gibt es in diesem Land keine Trendliste. Bitte eine andere Kategorie wählen."
    if gruende & {"channelNotFound", "playlistNotFound"}:
        return "Kanal nicht gefunden."
    if gruende & {"commentsDisabled"}:
        return "Bei diesem Video sind die Kommentare deaktiviert."
    if gruende & {"videoNotFound"}:
        return "Video nicht gefunden (gelöscht, privat oder falsche ID)."
    text = _bereinigen(f.get("message") or "", key)[:200]
    return f"Die YouTube-API meldet Fehler {status}" + (f": {text}" if text else ".")


def verbindung(key, get, timeout=20):
    """-> abruf(endpunkt, params) -> JSON. Der Schluessel steckt nur in dieser Funktion."""
    def abruf(endpunkt, params):
        if endpunkt not in KOSTEN:
            raise ApiFehler(f"Unbekannter Endpunkt: {endpunkt}")
        try:
            r = get(BASIS + endpunkt, params=params, timeout=timeout,
                    headers={"X-Goog-Api-Key": key, "Accept": "application/json"})
        except Exception as ex:                              # Text der Ausnahme nie weitergeben
            raise ApiFehler(f"Keine Verbindung zur YouTube-API ({type(ex).__name__}). Bitte später erneut "
                            "versuchen.") from None
        if r.status_code != 200:
            raise ApiFehler(_fehlertext(r.status_code, r, key))
        try:
            return r.json()
        except ValueError:
            raise ApiFehler("Die YouTube-API hat keine gültige Antwort geliefert.") from None
    return abruf


class Zaehler:
    """Umhuellt abruf() und zaehlt die verbrauchten Einheiten - auch bei Fehlern (YouTube bucht diese ebenfalls)."""

    def __init__(self, abruf):
        self._abruf = abruf
        self.einheiten = 0
        self.aufrufe = 0

    def __call__(self, endpunkt, params):
        self.einheiten += KOSTEN.get(endpunkt, 1)
        self.aufrufe += 1
        return self._abruf(endpunkt, params)


# ---------------------------------------------------------------------------------------------------- Kontingent
def kontingent_tag(jetzt):
    return jetzt.astimezone(PAZIFIK).date().isoformat()


def neustart_text(jetzt=None):
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    p = jetzt.astimezone(PAZIFIK)
    naechste = datetime.datetime.combine(p.date() + datetime.timedelta(days=1), datetime.time(), PAZIFIK)
    return naechste.astimezone(BERLIN).strftime("%d.%m. %H:%M Uhr deutscher Zeit")


def verbraucht(speicher, jetzt):
    k = (speicher or {}).get("kontingent") or {}
    return int(k.get("verbraucht") or 0) if k.get("tag") == kontingent_tag(jetzt) else 0


def buchen(speicher, einheiten, jetzt):
    s = dict(speicher or {})
    s["kontingent"] = {"tag": kontingent_tag(jetzt), "verbraucht": verbraucht(s, jetzt) + max(0, int(einheiten))}
    return s


def pruefen(speicher, einheiten, grenze, jetzt):
    """Wirft ApiFehler, wenn der Abruf die eigene Tagesgrenze ueberschreiten wuerde."""
    v = verbraucht(speicher, jetzt)
    grenze = min(int(grenze or STANDARD_GRENZE), TAGESKONTINGENT)
    if v + einheiten > grenze:
        raise ApiFehler(f"Eigene Tagesgrenze erreicht: {v:,} von {grenze:,} Einheiten verbraucht, dieser Abruf "
                        f"bräuchte etwa {einheiten}. Neustart {neustart_text(jetzt)}. Die Grenze lässt sich unter "
                        "„Einstellungen“ ändern.".replace(",", "."))
    return v


# ---------------------------------------------------------------------------------------------------- Zwischenspeicher
def cache_schluessel(art, params):
    roh = json.dumps({"art": art, **{k: v for k, v in (params or {}).items()}}, sort_keys=True, ensure_ascii=False)
    return art + "-" + hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]


def _zeit(iso):
    try:
        z = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return z if z.tzinfo else z.replace(tzinfo=datetime.timezone.utc)


def cache_holen(speicher, schluessel, jetzt, stunden=CACHE_STUNDEN):
    e = ((speicher or {}).get("cache") or {}).get(schluessel)
    if not isinstance(e, dict):
        return None
    z = _zeit(e.get("zeit"))
    if not z or jetzt - z > datetime.timedelta(hours=stunden) or z > jetzt + datetime.timedelta(minutes=5):
        return None
    return e


def cache_ablegen(speicher, schluessel, art, daten, jetzt):
    s = dict(speicher or {})
    alt = {k: v for k, v in (s.get("cache") or {}).items()
           if isinstance(v, dict) and cache_holen(s, k, jetzt) is not None and k != schluessel}
    alt[schluessel] = {"art": art, "zeit": jetzt.isoformat(timespec="seconds"), "daten": daten}
    s["cache"] = dict(sorted(alt.items(), key=lambda kv: kv[1]["zeit"])[-CACHE_MAX:])
    return s


# ---------------------------------------------------------------------------------------------------- Aufbereitung
def dauer_s(iso):
    """ISO-8601-Dauer (PT1H2M3S, P1DT2H) -> Sekunden; unbekannt -> None."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", str(iso or ""))
    if not m or all(g is None for g in m.groups()):
        return None
    t, h, mi, s = (int(x or 0) for x in m.groups())
    return t * 86400 + h * 3600 + mi * 60 + s


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def video_parsen(item):
    sn, stt, cd = item.get("snippet") or {}, item.get("statistics") or {}, item.get("contentDetails") or {}
    vid = item.get("id") if isinstance(item.get("id"), str) else (item.get("id") or {}).get("videoId")
    d = dauer_s(cd.get("duration"))
    th = sn.get("thumbnails") or {}
    bild = next(((th.get(g) or {}).get("url") for g in ("medium", "high", "default") if (th.get(g) or {}).get("url")),
                "")
    return {"id": vid, "titel": sn.get("title") or "", "kanal_id": sn.get("channelId") or "",
            "kanal": sn.get("channelTitle") or "", "datum": sn.get("publishedAt") or "", "dauer_s": d,
            "shorts": d is not None and 0 < d <= SHORT_MAX_S, "views": _int(stt.get("viewCount")),
            "likes": _int(stt.get("likeCount")), "kommentare": _int(stt.get("commentCount")),
            "kategorie": sn.get("categoryId") or "", "live": sn.get("liveBroadcastContent") or "none",
            "sprache": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "",
            "url": f"https://www.youtube.com/watch?v={vid}" if vid else "", "thumbnail": bild}


def kanal_parsen(item):
    sn, stt = item.get("snippet") or {}, item.get("statistics") or {}
    uploads = ((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or ""
    th = sn.get("thumbnails") or {}
    return {"id": item.get("id") or "", "name": sn.get("title") or "", "handle": sn.get("customUrl") or "",
            "land": sn.get("country") or "", "erstellt": sn.get("publishedAt") or "",
            "abonnenten": None if stt.get("hiddenSubscriberCount") else _int(stt.get("subscriberCount")),
            "aufrufe": _int(stt.get("viewCount")), "videos": _int(stt.get("videoCount")), "uploads": uploads,
            "beschreibung": (sn.get("description") or "")[:400],
            "bild": ((th.get("medium") or th.get("default") or {}).get("url") or "")}


def anreichern(videos, kanaele, jetzt):
    """Kennzahlen je Video: Alter, Aufrufe pro Tag/Stunde, Verhaeltnis zur Kanalgroesse, Likes-Quote."""
    aus = []
    for v in videos:
        z = _zeit(v.get("datum"))
        alter_h = max((jetzt - z).total_seconds() / 3600, 1.0) if z else None
        k = kanaele.get(v.get("kanal_id")) or {}
        ab = k.get("abonnenten")
        views = v.get("views")
        aus.append(dict(v, alter_tage=round(alter_h / 24, 2) if alter_h else None,
                        views_pro_tag=views / max(alter_h / 24, 1.0) if views is not None and alter_h else None,
                        views_pro_stunde=views / alter_h if views is not None and alter_h else None,
                        abonnenten=ab,
                        faktor_kanal=views / ab if views is not None and ab else None,
                        likes_pct=100 * v["likes"] / views if views and v.get("likes") is not None else None))
    return aus


def _stapel(liste, n=50):
    return [liste[i:i + n] for i in range(0, len(liste), n)]


def videos_laden(abruf, ids):
    aus = []
    for teil in _stapel([i for i in ids if i]):
        r = abruf("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(teil), "maxResults": 50})
        aus += [video_parsen(i) for i in r.get("items") or []]
    return aus


def kanaele_laden(abruf, ids):
    aus = {}
    for teil in _stapel(sorted({i for i in ids if i})):
        r = abruf("channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(teil), "maxResults": 50})
        for i in r.get("items") or []:
            k = kanal_parsen(i)
            aus[k["id"]] = k
    return aus


def _format_ok(v, fmt):
    if v.get("live") in ("live", "upcoming"):
        return False
    if fmt == "Shorts":
        return bool(v.get("shorts"))
    if fmt == "Longform":
        return v.get("dauer_s") is not None and v["dauer_s"] > SHORT_MAX_S
    return True


# ---------------------------------------------------------------------------------------------------- Abfragen
def trends(abruf, region="DE", kategorie="0", jetzt=None, anzahl=50):
    """Meistgesehene Videos eines Landes (YouTube-Trendliste). Kosten: 1-2 Einheiten."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    p = {"part": "snippet,statistics,contentDetails", "chart": "mostPopular", "regionCode": region,
         "maxResults": max(1, min(int(anzahl), 50))}
    if kategorie and str(kategorie) != "0":
        p["videoCategoryId"] = str(kategorie)
    videos = [video_parsen(i) for i in abruf("videos", p).get("items") or []]
    kan = kanaele_laden(abruf, [v["kanal_id"] for v in videos])
    return {"videos": anreichern(videos, kan, jetzt), "kanaele": len(kan)}


def such_parameter(begriff, tage=30, fmt="Alle", region="", sprache="", reihenfolge="viewCount", jetzt=None):
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    p = {"part": "snippet", "type": "video", "q": str(begriff).strip()[:200], "maxResults": 50,
         "order": reihenfolge if reihenfolge in REIHENFOLGEN else "viewCount"}
    if tage:
        ab = (jetzt - datetime.timedelta(days=int(tage))).replace(minute=0, second=0, microsecond=0)
        p["publishedAfter"] = ab.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if fmt == "Shorts":
        p["videoDuration"] = "short"                        # < 4 Minuten; genau gefiltert wird danach
    if region:
        p["regionCode"] = region
    if sprache:
        p["relevanceLanguage"] = sprache
    return p


def suche(abruf, begriff, tage=30, fmt="Alle", region="", sprache="", reihenfolge="viewCount", jetzt=None):
    """Stichwortsuche + Statistik der Treffer und ihrer Kanaele. Kosten: 100 + 2 Einheiten."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    if not str(begriff or "").strip():
        raise ApiFehler("Bitte einen Suchbegriff eingeben.")
    r = abruf("search", such_parameter(begriff, tage, fmt, region, sprache, reihenfolge, jetzt))
    ids = [((i.get("id") or {}).get("videoId")) for i in r.get("items") or []]
    videos = [v for v in videos_laden(abruf, ids) if _format_ok(v, fmt)]
    reihe = {vid: n for n, vid in enumerate(ids)}
    videos.sort(key=lambda v: reihe.get(v["id"], 99))
    kan = kanaele_laden(abruf, [v["kanal_id"] for v in videos])
    return {"videos": anreichern(videos, kan, jetzt), "treffer": len(ids), "kanaele": len(kan)}


def kanal_eingabe(eingabe):
    """-> (art, wert) mit art in id/handle/username. Wirft ApiFehler bei unbrauchbarer Eingabe."""
    s = str(eingabe or "").strip()
    m = re.search(r"(UC[A-Za-z0-9_-]{22})", s)
    if m:
        return "id", m.group(1)
    m = re.search(r"(?:youtube\.com/)?@([A-Za-z0-9._\-]{3,100})", s)
    if m:
        return "handle", "@" + m.group(1).rstrip("/")
    m = re.search(r"youtube\.com/user/([A-Za-z0-9_\-]+)", s)
    if m:
        return "username", m.group(1)
    if re.search(r"youtube\.com/c/", s):
        raise ApiFehler("Adressen mit /c/ lassen sich nicht eindeutig auflösen. Bitte das @Handle oder die Kanal-ID "
                        "(UC…) angeben.")
    if re.fullmatch(r"[A-Za-z0-9._\-]{3,100}", s):
        return "handle", "@" + s
    raise ApiFehler("Bitte ein @Handle, eine Kanal-Adresse oder eine Kanal-ID (UC…) angeben.")


def kanal_aufloesen(abruf, eingabe):
    art, wert = kanal_eingabe(eingabe)
    p = {"part": "snippet,statistics,contentDetails"}
    p[{"id": "id", "handle": "forHandle", "username": "forUsername"}[art]] = wert
    items = abruf("channels", p).get("items") or []
    if not items:
        raise ApiFehler(f"Kein Kanal zu „{wert}“ gefunden.")
    return kanal_parsen(items[0])


def kanal_auswerten(kanal, videos, jetzt):
    """Kennzahlen eines Kanals aus seinen letzten Uploads (bis 50)."""
    vs = anreichern([v for v in videos if v.get("live") not in ("live", "upcoming")], {kanal["id"]: kanal}, jetzt)
    teile = {}
    for name, filt in (("Longform", lambda v: not v["shorts"]), ("Shorts", lambda v: v["shorts"])):
        gr = [v for v in vs if filt(v) and v.get("views") is not None]
        teile[name] = {"anzahl": len(gr), "median": statistics.median([v["views"] for v in gr]) if gr else None}
        for v in gr:                                      # Ausreisser: Aufrufe/Tag gegen den Median der anderen
            andere = [x["views_pro_tag"] for x in gr if x is not v and x.get("views_pro_tag")]
            med = statistics.median(andere) if len(andere) >= MIN_VERGLEICH else None
            v["outlier"] = v["views_pro_tag"] / med if med and v.get("views_pro_tag") is not None else None
    neu_90 = [v for v in vs if v.get("alter_tage") is not None and v["alter_tage"] <= 90]
    daten = sorted((_zeit(v["datum"]) for v in vs if _zeit(v.get("datum"))), reverse=True)
    abstaende = [(a - b).total_seconds() / 86400 for a, b in zip(daten, daten[1:])]
    erstellt = _zeit(kanal.get("erstellt"))
    return {"kanal": kanal, "videos": sorted(vs, key=lambda v: v.get("datum") or "", reverse=True),
            "formate": teile, "uploads_pro_woche": round(len(neu_90) / (90 / 7), 2) if len(vs) else 0.0,
            "abstand_median_tage": round(statistics.median(abstaende), 1) if abstaende else None,
            "letzter_upload": daten[0].date().isoformat() if daten else None,
            "alter_jahre": round((jetzt - erstellt).days / 365.25, 1) if erstellt else None,
            "aufrufe_je_video": round(kanal["aufrufe"] / kanal["videos"]) if kanal.get("aufrufe") is not None
            and kanal.get("videos") else None,
            "rhythmus_gedeckelt": len(neu_90) >= 50}           # alle 50 geladenen Videos juenger als 90 Tage


def kanal_untersuchen(abruf, eingabe, jetzt=None):
    """Kanal aufloesen + letzte 50 Uploads auswerten. Kosten: 3 Einheiten."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    k = kanal_aufloesen(abruf, eingabe)
    ids = []
    if k.get("uploads"):
        r = abruf("playlistItems", {"part": "contentDetails", "playlistId": k["uploads"], "maxResults": 50})
        ids = [(i.get("contentDetails") or {}).get("videoId") for i in r.get("items") or []]
    return kanal_auswerten(k, videos_laden(abruf, ids), jetzt)
