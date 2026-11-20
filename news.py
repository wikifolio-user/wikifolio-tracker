"""Finanz-Nachrichten fuer den News-Ticker der Startseite.

Der Kurs-Agent (kurs_agent.py) holt die Schlagzeilen mit jedem Lauf aus oeffentlichen RSS-Feeds und legt sie ab:
  state/kurse/news.json   {"stand": iso, "eintraege": [{"titel", "link", "zeit": iso|None, "quelle"}]}
Die App liest nur diese Datei (keine Abrufe beim Start). Gezeigt werden nur Schlagzeile, Quelle und Link -
der Artikel selbst oeffnet sich beim Anbieter. Ein fehlgeschlagener Feed wird uebersprungen.
"""
import datetime
import email.utils
import html
import re
import xml.etree.ElementTree as ET

PFAD = "state/kurse/news.json"
FEEDS = [
    ("tagesschau", "https://www.tagesschau.de/wirtschaft/finanzen/index~rss2.xml"),
    ("tagesschau", "https://www.tagesschau.de/wirtschaft/index~rss2.xml"),
]
HEADERS = {"User-Agent": "Mozilla/5.0 (FinanzDashboard News-Ticker)"}
MAX_EINTRAEGE = 20
MAX_ALTER_STUNDEN = 48
MAX_BYTES = 2_000_000


def _text(el, *namen):
    for n in namen:
        x = el.find(n)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
        if x is not None and x.get("href"):              # Atom: <link href="...">
            return x.get("href").strip()
    return ""


def _zeit(text):
    """RSS (RFC 822) oder Atom (ISO 8601) -> aware datetime oder None."""
    if not text:
        return None
    try:
        t = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            t = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def _sauber(text):
    t = html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))
    return re.sub(r"\s+", " ", t).strip()


def parsen(xml_text, quelle):
    """RSS 2.0 oder Atom -> [{"titel", "link", "zeit", "quelle"}]; nur http(s)-Links. Kaputtes XML -> []."""
    if not xml_text or len(xml_text) > MAX_BYTES:
        return []
    try:
        wurzel = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    atom = "{http://www.w3.org/2005/Atom}"
    posten = wurzel.findall(".//item") or wurzel.findall(f".//{atom}entry")
    aus = []
    for p in posten:
        titel = _sauber(_text(p, "title", f"{atom}title"))[:200]
        link = _text(p, "link", f"{atom}link")
        if not titel or not re.match(r"^https?://", link or ""):
            continue
        t = _zeit(_text(p, "pubDate", f"{atom}updated", f"{atom}published"))
        aus.append({"titel": titel, "link": link[:500], "zeit": t.isoformat(timespec="seconds") if t else None,
                    "quelle": quelle})
    return aus


def zusammenfuehren(listen, jetzt, max_n=MAX_EINTRAEGE, max_alter_h=MAX_ALTER_STUNDEN):
    """Mehrere Feeds -> neueste zuerst, ohne doppelte Schlagzeilen, nicht aelter als max_alter_h."""
    gesehen, aus = set(), []
    for e in (x for l in listen for x in l):
        k = re.sub(r"\W+", "", e["titel"].lower())
        if k in gesehen:
            continue
        t = _zeit(e.get("zeit"))
        if t and jetzt - t > datetime.timedelta(hours=max_alter_h):
            continue
        gesehen.add(k)
        aus.append(e)
    aus.sort(key=lambda e: e.get("zeit") or "", reverse=True)
    return aus[:max_n]


def laden(get, jetzt):
    """Alle Feeds abrufen (Fehler je Feed werden uebersprungen). -> (eintraege, anzahl_feeds_ok)"""
    listen, ok = [], 0
    for quelle, url in FEEDS:
        try:
            r = get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            eintraege = parsen(r.text, quelle)
        except Exception:
            continue
        if eintraege:
            ok += 1
            listen.append(eintraege)
    return zusammenfuehren(listen, jetzt), ok
