"""Faceless YouTube - Kanal-Radar ohne API-Schluessel. Reine Rechenlogik (ohne Streamlit).

Quelle: der oeffentliche RSS-Feed je Kanal (https://www.youtube.com/feeds/videos.xml?channel_id=UC...), den YouTube
selbst bereitstellt. Er liefert die letzten 15 Videos mit Titel, Datum, Aufrufen und Likes - KEINE Abonnenten,
Kommentare oder Suche. Es wird nichts von YouTube-Webseiten ausgelesen (kein Scraping).

Echtes Wachstum entsteht nur aus gespeicherten Momentaufnahmen (mindestens zwei, mindestens 12 Stunden
auseinander) - eine einzelne Momentaufnahme wird nie als Wachstum ausgegeben.
Speicherformat (state/youtube_radar.json):
  {"kanaele": {cid: {"name", "abruf", "fehler"}},
   "videos": {vid: {"kanal", "titel", "datum", "url", "shorts", "thumbnail", "verlauf": [[iso, views, likes]]}}}"""
import datetime
import re
import statistics
import xml.etree.ElementTree as ET

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "m": "http://search.yahoo.com/mrss/"}
MAX_VERLAUF = 120               # Momentaufnahmen je Video
MIN_ABSTAND_H = 12              # fuer gemessenes Wachstum
MIN_VERGLEICH = 3               # Vergleichsvideos fuer den Outlier-Faktor
GEWICHTE = {"alter": 25, "wachstum": 20, "outlier": 25, "engagement": 15, "kanal": 15}
TEIL_TEXT = {"alter": "Aufrufe im Verhältnis zum Alter", "wachstum": "Gemessenes Wachstum",
             "outlier": "Im Vergleich zum Kanal", "engagement": "Engagement (Likes/Aufrufe)",
             "kanal": "Verhältnis zur Kanalgröße"}


class RadarFehler(Exception):
    pass


def kanal_id(eingabe):
    """Kanal-ID aus einer Eingabe: 'UC...' (24 Zeichen) oder eine Adresse mit /channel/UC... .
    @Handles lassen sich ohne API-Schluessel nicht zuverlaessig aufloesen -> verstaendlicher Fehler."""
    s = str(eingabe or "").strip()
    m = re.search(r"(UC[A-Za-z0-9_-]{22})", s)
    if m:
        return m.group(1)
    if "@" in s or "youtube.com" in s:
        raise RadarFehler("Bitte die Kanal-ID (beginnt mit „UC“, 24 Zeichen) angeben. Sie steht im Kanal unter "
                          "„Mehr“ → „Kanal teilen“ → „Kanal-ID kopieren“. @Namen lassen sich ohne YouTube-Schlüssel "
                          "nicht auflösen.")
    raise RadarFehler("Das ist keine gültige Kanal-ID (beginnt mit „UC“, 24 Zeichen).")


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def rss_parsen(text):
    """RSS-Feed eines Kanals -> {"kanal_id", "name", "videos": [...]}. Wirft RadarFehler bei ungueltigem Feed."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise RadarFehler("Der Feed ist kein gültiges XML.") from None
    if root.tag != f"{{{NS['a']}}}feed":
        raise RadarFehler("Unerwartetes Feed-Format.")
    cid = (root.findtext("yt:channelId", default="", namespaces=NS) or "").strip()
    if cid and not cid.startswith("UC"):
        cid = "UC" + cid                              # der Feed nennt die ID teils ohne "UC"
    videos = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", default="", namespaces=NS)
        if not vid:
            continue
        link = next((l.get("href") for l in e.findall("a:link", NS) if l.get("rel") == "alternate"), "") or ""
        g = e.find("m:group", NS)
        stat = g.find("m:community/m:statistics", NS) if g is not None else None
        stern = g.find("m:community/m:starRating", NS) if g is not None else None
        thumb = g.find("m:thumbnail", NS) if g is not None else None
        videos.append({"id": vid, "titel": (e.findtext("a:title", default="", namespaces=NS) or "").strip(),
                       "datum": e.findtext("a:published", default="", namespaces=NS),
                       "url": link or f"https://www.youtube.com/watch?v={vid}", "shorts": "/shorts/" in link,
                       "views": _int(stat.get("views")) if stat is not None else None,
                       "likes": _int(stern.get("count")) if stern is not None else None,
                       "thumbnail": thumb.get("url") if thumb is not None else None})
    return {"kanal_id": cid, "name": (root.findtext("a:title", default="", namespaces=NS) or "").strip(),
            "videos": videos}


def abrufen(cid, get):
    """Feed laden und auswerten. get: requests.get-kompatibel. -> rss_parsen-Ergebnis"""
    try:
        r = get(FEED.format(cid), timeout=20, headers={"Accept": "application/atom+xml"})
    except Exception as ex:
        raise RadarFehler(f"Feed nicht erreichbar ({type(ex).__name__}).") from None
    if r.status_code == 404:
        raise RadarFehler("Kanal nicht gefunden (Feed 404) – ist die Kanal-ID richtig?")
    if r.status_code != 200:
        raise RadarFehler(f"Feed antwortet mit HTTP {r.status_code}.")
    return rss_parsen(r.text)


def _zeit(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def einfuegen(radar, feed, zeitpunkt):
    """Momentaufnahme eines Feeds ins Radar uebernehmen (hoechstens eine je Stunde und Video). -> neues Radar"""
    radar = {"kanaele": dict((radar or {}).get("kanaele") or {}), "videos": dict((radar or {}).get("videos") or {})}
    iso = zeitpunkt.isoformat(timespec="seconds")
    cid = feed["kanal_id"]
    radar["kanaele"][cid] = {"name": feed["name"], "abruf": iso, "fehler": None}
    for v in feed["videos"]:
        if v["views"] is None:
            continue
        alt = dict(radar["videos"].get(v["id"]) or {})
        verlauf = list(alt.get("verlauf") or [])
        punkt = [iso, v["views"], v["likes"]]
        letzte = _zeit(verlauf[-1][0]) if verlauf else None
        if letzte and zeitpunkt - letzte < datetime.timedelta(hours=1):
            verlauf[-1] = punkt
        else:
            verlauf.append(punkt)
        radar["videos"][v["id"]] = {"kanal": cid, "titel": v["titel"], "datum": v["datum"], "url": v["url"],
                                    "shorts": v["shorts"], "thumbnail": v["thumbnail"],
                                    "verlauf": verlauf[-MAX_VERLAUF:]}
    return radar


def fehler_merken(radar, cid, text, zeitpunkt):
    radar = {"kanaele": dict((radar or {}).get("kanaele") or {}), "videos": dict((radar or {}).get("videos") or {})}
    k = dict(radar["kanaele"].get(cid) or {})
    k.update(fehler=text, fehler_zeit=zeitpunkt.isoformat(timespec="seconds"))
    radar["kanaele"][cid] = k
    return radar


def wachstum(verlauf):
    """Gemessene Aufrufe pro Tag zwischen der letzten und der aeltesten Momentaufnahme der letzten 7 Tage
    (mindestens MIN_ABSTAND_H Stunden auseinander) oder None."""
    if not verlauf or len(verlauf) < 2:
        return None
    ende = _zeit(verlauf[-1][0])
    for t, v, _ in verlauf[:-1]:
        anfang = _zeit(t)
        if not anfang or not ende:
            continue
        dauer = ende - anfang
        if datetime.timedelta(hours=MIN_ABSTAND_H) <= dauer <= datetime.timedelta(days=7, hours=12):
            return max(0.0, (verlauf[-1][1] - v) / (dauer.total_seconds() / 86400))
    return None


def _perzentil(werte, x):
    if x is None or not werte:
        return None
    return sum(1 for w in werte if w < x) / len(werte) * 100 + sum(1 for w in werte if w == x) / len(werte) * 50


def kennzahlen(radar, jetzt):
    """Je Video: Aufrufe, Alter, Aufrufe/Tag, Engagement, gemessenes Wachstum, Outlier-Faktor, Success-Score.
    Vergleiche nur innerhalb desselben Formats (Shorts vs. Longform). -> Liste von dicts"""
    zeilen = []
    for vid, v in ((radar or {}).get("videos") or {}).items():
        if not v.get("verlauf"):
            continue
        _, views, likes = v["verlauf"][-1]
        pub = _zeit(v.get("datum"))
        alter = max((jetzt - pub).total_seconds() / 86400, 1 / 24) if pub else None
        zeilen.append({"id": vid, "kanal": v["kanal"], "titel": v["titel"], "url": v["url"], "datum": v.get("datum"),
                       "shorts": bool(v.get("shorts")), "views": views, "likes": likes, "alter_tage": alter,
                       # unter einem Tag zaehlt als ein Tag - sonst wirken Videos von wenigen Stunden riesig
                       "views_pro_tag": views / max(alter, 1.0) if alter else None,
                       "engagement_pct": likes / views * 100 if likes is not None and views else None,
                       "wachstum_pro_tag": wachstum(v["verlauf"]), "momentaufnahmen": len(v["verlauf"])})
    # Outlier: Aufrufe/Tag gegen den Median der anderen Videos desselben Kanals und Formats (mind. 1 Tag alt)
    for z in zeilen:
        vergleich = [x["views_pro_tag"] for x in zeilen if x["kanal"] == z["kanal"] and x["shorts"] == z["shorts"]
                     and x["id"] != z["id"] and x["alter_tage"] and x["alter_tage"] >= 1 and x["views_pro_tag"]]
        if len(vergleich) >= MIN_VERGLEICH and z["views_pro_tag"] is not None:
            med = statistics.median(vergleich)
            z["outlier"] = z["views_pro_tag"] / med if med > 0 else None
            z["vergleich_n"] = len(vergleich)
        else:
            z["outlier"], z["vergleich_n"] = None, len(vergleich)
        z["outlier_stufe"] = (20 if (z["outlier"] or 0) >= 20 else 10 if (z["outlier"] or 0) >= 10
                              else 5 if (z["outlier"] or 0) >= 5 else None)
    # Success-Score: Perzentile je Format, fehlende Teile fallen aus der Gewichtung (dann "vorlaeufig")
    for fmt in (True, False):
        gruppe = [z for z in zeilen if z["shorts"] == fmt]
        verteilung = {"alter": [z["views_pro_tag"] for z in gruppe if z["views_pro_tag"] is not None],
                      "wachstum": [z["wachstum_pro_tag"] for z in gruppe if z["wachstum_pro_tag"] is not None],
                      "outlier": [z["outlier"] for z in gruppe if z["outlier"] is not None],
                      "engagement": [z["engagement_pct"] for z in gruppe if z["engagement_pct"] is not None]}
        for z in gruppe:
            teile = {"alter": _perzentil(verteilung["alter"], z["views_pro_tag"]),
                     "wachstum": _perzentil(verteilung["wachstum"], z["wachstum_pro_tag"]),
                     "outlier": _perzentil(verteilung["outlier"], z["outlier"]),
                     "engagement": _perzentil(verteilung["engagement"], z["engagement_pct"]),
                     "kanal": None}                   # Abonnenten liefert der Feed nicht
            da = {k: w for k, w in teile.items() if w is not None}
            g = sum(GEWICHTE[k] for k in da)
            z["score"] = round(sum(GEWICHTE[k] * w for k, w in da.items()) / g, 1) if g else None
            z["score_teile"] = teile
            z["score_fehlt"] = [TEIL_TEXT[k] for k, w in teile.items() if w is None]
            z["vorlaeufig"] = bool(z["score_fehlt"]) or len(gruppe) < 10
    return zeilen


def werbung_schaetzung(views, rpm_von=1.0, rpm_bis=5.0):
    """Moegliche Werbeeinnahmen eines fremden Videos als Spanne (Schaetzung - echte Zahlen sind nicht oeffentlich)."""
    if not views:
        return None, None
    return views / 1000 * rpm_von, views / 1000 * rpm_bis
