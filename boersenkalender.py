"""Handelskalender von Xetra und NYSE (ohne Streamlit, ohne Netz).

Ganztaegige Feiertage werden berechnet (Ostern, US-"observed"-Regeln), ausserplanmaessige Schliessungen stehen in
SONDERSCHLIESSUNGEN. Verkuerzte Handelstage (z. B. 24.12. an der NYSE) zaehlen als Handelstag.
"""
import datetime
from zoneinfo import ZoneInfo

BOERSEN = {
    "XETRA": {"tz": ZoneInfo("Europe/Berlin"), "auf": (9, 0), "zu": (17, 30), "name": "Xetra"},
    "NYSE": {"tz": ZoneInfo("America/New_York"), "auf": (9, 30), "zu": (16, 0), "name": "NYSE"},
    # Tokio: Handelszeiten mit Mittagspause; japanische Feiertage sind NICHT hinterlegt (nur Wochenenden)
    "TSE": {"tz": ZoneInfo("Asia/Tokyo"), "auf": (9, 0), "zu": (15, 30), "pause": ((11, 30), (12, 30)), "name": "Tokio"},
}
# Ausserplanmaessige ganztaegige Schliessungen (Staatstrauer, Unwetter)
SONDERSCHLIESSUNGEN = {
    "NYSE": {datetime.date(2018, 12, 5), datetime.date(2025, 1, 9), datetime.date(2012, 10, 29),
             datetime.date(2012, 10, 30)},
    "XETRA": set(),
}


def ostersonntag(jahr):
    """Gausssche Osterformel (gregorianisch)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    return datetime.date(jahr, (h + l_ - 7 * m + 114) // 31, (h + l_ - 7 * m + 114) % 31 + 1)


def _nter_wochentag(jahr, monat, wochentag, n):
    if n > 0:
        d = datetime.date(jahr, monat, 1)
        d += datetime.timedelta(days=(wochentag - d.weekday()) % 7)
        return d + datetime.timedelta(weeks=n - 1)
    d = datetime.date(jahr + (monat == 12), monat % 12 + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() - wochentag) % 7)


def _beobachtet(d):
    if d.weekday() == 5:
        return d - datetime.timedelta(days=1)
    if d.weekday() == 6:
        return d + datetime.timedelta(days=1)
    return d


def feiertage(boerse, jahr):
    ostern = ostersonntag(jahr)
    karfreitag = ostern - datetime.timedelta(days=2)
    if boerse == "XETRA":
        tage = {datetime.date(jahr, 1, 1), karfreitag, ostern + datetime.timedelta(days=1), datetime.date(jahr, 5, 1),
                datetime.date(jahr, 12, 24), datetime.date(jahr, 12, 25), datetime.date(jahr, 12, 26),
                datetime.date(jahr, 12, 31)}
    else:
        tage = {karfreitag, _nter_wochentag(jahr, 1, 0, 3), _nter_wochentag(jahr, 2, 0, 3),
                _nter_wochentag(jahr, 5, 0, -1), _nter_wochentag(jahr, 9, 0, 1), _nter_wochentag(jahr, 11, 3, 4),
                _beobachtet(datetime.date(jahr, 7, 4)), _beobachtet(datetime.date(jahr, 12, 25))}
        if jahr >= 2022:
            tage.add(_beobachtet(datetime.date(jahr, 6, 19)))          # Juneteenth seit 2022
        if datetime.date(jahr, 1, 1).weekday() != 5:
            tage.add(_beobachtet(datetime.date(jahr, 1, 1)))
    return tage | {d for d in SONDERSCHLIESSUNGEN.get(boerse, ()) if d.year == jahr}


def ist_handelstag(boerse, d):
    if boerse == "TSE":
        return d.weekday() < 5
    return d.weekday() < 5 and d not in feiertage(boerse, d.year)


def boerse_offen(boerse, jetzt):
    """Laeuft der regulaere Handel gerade (Handelstag, innerhalb der Zeiten, ausserhalb einer Mittagspause)?"""
    b = BOERSEN[boerse]
    t = jetzt.astimezone(b["tz"])
    if not ist_handelstag(boerse, t.date()) or not datetime.time(*b["auf"]) <= t.time() < datetime.time(*b["zu"]):
        return False
    pause = b.get("pause")
    return not (pause and datetime.time(*pause[0]) <= t.time() < datetime.time(*pause[1]))


NY = ZoneInfo("America/New_York")


def markt_offen(markt, jetzt):
    """Wie boerse_offen, zusaetzlich fuer rund um die Uhr gehandelte Maerkte:
    KRYPTO immer; FX (Devisen) So 17:00 - Fr 17:00 New York; COMEX (Gold-Future) So-Fr 18:00-17:00 New York."""
    if markt == "KRYPTO":
        return True
    if markt in ("FX", "COMEX"):
        t = jetzt.astimezone(NY)
        wt, zeit = t.weekday(), t.time()
        if wt == 5 or (wt == 6 and zeit < datetime.time(18 if markt == "COMEX" else 17)) or (wt == 4 and zeit >= datetime.time(17)):
            return False
        return markt == "FX" or not datetime.time(17) <= zeit < datetime.time(18)      # taegliche Pause COMEX
    return boerse_offen(markt, jetzt)


def handelstage_zwischen(boerse, von, bis):
    """Alle Handelstage von..bis (beide einschliesslich), aufsteigend."""
    aus, d = [], von
    while d <= bis:
        if ist_handelstag(boerse, d):
            aus.append(d)
        d += datetime.timedelta(days=1)
    return aus


def kerze_vollstaendig(boerse, d, jetzt):
    """Ist die Tageskerze vom Datum d (Boersenzeit) abgeschlossen? Erst nach Handelsschluss."""
    b = BOERSEN[boerse]
    t = jetzt.astimezone(b["tz"])
    return d < t.date() or (d == t.date() and t.time() >= datetime.time(*b["zu"]))
