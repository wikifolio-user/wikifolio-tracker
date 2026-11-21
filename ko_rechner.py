"""Knock-out-Gewinnrechner fuer Nasdaq 100, DAX 40, S&P 500 und Dow Jones - reine Rechenlogik ohne Streamlit.

Zwei Modi:
  1. Freie Hebel-Simulation: konstanter Anfangshebel, Verlust hoechstens 100 % - vereinfachte Simulation, keine
     Prognose eines Knock-out-Produkts.
  2. Echtes Knock-out-Zertifikat: Produktdaten (manuell oder spaeter automatisch) -> Hebel, Stueckzahl, Wert am
     Zieltermin mit Finanzierungskosten (wandernder Basispreis), Knock-out-Schwelle, Bezugsverhaeltnis, EUR/USD,
     Spread und Ordergebuehren.

Marktdaten: nur die offiziellen Indexstaende (Yahoo-Symbole ^NDX, ^GDAXI, ^GSPC, ^DJI - keine CFD-Kurse), die der
Kurs-Agent in state/kurse/indizes.json ablegt (indizes.py). Handelszeiten und Boersenfeiertage von Xetra und NYSE
sind hier hinterlegt, damit veraltete Staende erkannt werden.

Wichtig: Ein Kursziel allein schliesst einen zwischenzeitlichen Knock-out nicht aus - der Verlauf bis zum Zieltermin
entscheidet. Alle Ergebnisse gelten nur unter der Annahme, dass die Schwelle vorher nicht beruehrt wird.
"""
import datetime
import math
from zoneinfo import ZoneInfo

def de(x, n=2):
    """Zahl im deutschen Format (1.234,56)."""
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------------------------------- Indizes
INDIZES = {
    "NDX": {"name": "Nasdaq 100", "symbol": "NDX", "yahoo": "^NDX", "waehrung": "USD", "boerse": "NYSE"},
    "DAX": {"name": "DAX 40", "symbol": "DAX", "yahoo": "^GDAXI", "waehrung": "EUR", "boerse": "XETRA"},
    "SPX": {"name": "S&P 500", "symbol": "SPX", "yahoo": "^GSPC", "waehrung": "USD", "boerse": "NYSE"},
    "DJI": {"name": "Dow Jones", "symbol": "DJI", "yahoo": "^DJI", "waehrung": "USD", "boerse": "NYSE"},
}
FX_SYMBOL = "EURUSD=X"            # US-Dollar je Euro
QUELLE = "Yahoo Finance (offizieller Indexstand, über den Kurs-Agenten)"

HEBEL_VERGLEICH = (2, 3, 4, 5, 7, 10)
SZENARIEN = (-20, -10, -5, 5, 10, 20)
EINSATZ = {"min": 1000, "max": 100000, "schritt": 500, "standard": 10000, "schnell": (5000, 10000, 20000, 50000)}
HEBEL = {"min": 1.0, "max": 10.0, "max_erweitert": 20.0, "schritt": 0.5, "standard": 3.0}
KO_WARNUNG_PCT = 3.0              # Abstand zur Schwelle darunter: deutliche Warnung
KO_HINWEIS_PCT = 7.0              # darunter: Hinweis "gering"

# ---------------------------------------------------------------------------------------------------- Boersen
BOERSEN = {
    "XETRA": {"tz": ZoneInfo("Europe/Berlin"), "auf": (9, 0), "zu": (17, 30), "name": "Xetra"},
    "NYSE": {"tz": ZoneInfo("America/New_York"), "auf": (9, 30), "zu": (16, 0), "name": "NYSE"},
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
    monat = (h + l_ - 7 * m + 114) // 31
    tag = (h + l_ - 7 * m + 114) % 31 + 1
    return datetime.date(jahr, monat, tag)


def _nter_wochentag(jahr, monat, wochentag, n):
    """n-ter Wochentag (0 = Montag) im Monat; n = -1: letzter."""
    if n > 0:
        d = datetime.date(jahr, monat, 1)
        d += datetime.timedelta(days=(wochentag - d.weekday()) % 7)
        return d + datetime.timedelta(weeks=n - 1)
    d = datetime.date(jahr + (monat == 12), monat % 12 + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() - wochentag) % 7)


def _beobachtet(d):
    """US-Regel: Feiertag am Samstag -> Freitag davor, am Sonntag -> Montag danach."""
    if d.weekday() == 5:
        return d - datetime.timedelta(days=1)
    if d.weekday() == 6:
        return d + datetime.timedelta(days=1)
    return d


def feiertage(boerse, jahr):
    """Ganztaegige Boersenfeiertage (Halbtage zaehlen als Handelstag)."""
    ostern = ostersonntag(jahr)
    karfreitag = ostern - datetime.timedelta(days=2)
    if boerse == "XETRA":
        return {datetime.date(jahr, 1, 1), karfreitag, ostern + datetime.timedelta(days=1), datetime.date(jahr, 5, 1),
                datetime.date(jahr, 12, 24), datetime.date(jahr, 12, 25), datetime.date(jahr, 12, 26),
                datetime.date(jahr, 12, 31)}
    tage = {karfreitag, _nter_wochentag(jahr, 1, 0, 3), _nter_wochentag(jahr, 2, 0, 3),
            _nter_wochentag(jahr, 5, 0, -1), _nter_wochentag(jahr, 9, 0, 1), _nter_wochentag(jahr, 11, 3, 4),
            _beobachtet(datetime.date(jahr, 6, 19)), _beobachtet(datetime.date(jahr, 7, 4)),
            _beobachtet(datetime.date(jahr, 12, 25))}
    neujahr = datetime.date(jahr, 1, 1)
    if neujahr.weekday() != 5:                       # Neujahr am Samstag: kein Ersatztag (NYSE-Regel)
        tage.add(_beobachtet(neujahr))
    return tage


def ist_handelstag(boerse, d):
    return d.weekday() < 5 and d not in feiertage(boerse, d.year)


def boerse_offen(boerse, jetzt):
    b = BOERSEN[boerse]
    t = jetzt.astimezone(b["tz"])
    return ist_handelstag(boerse, t.date()) and datetime.time(*b["auf"]) <= t.time() < datetime.time(*b["zu"])


def letzter_handelsschluss(boerse, jetzt):
    """Zeitpunkt des letzten regulaeren Handelsschlusses vor `jetzt` (aware)."""
    b = BOERSEN[boerse]
    t = jetzt.astimezone(b["tz"])
    d = t.date()
    if not (ist_handelstag(boerse, d) and t.time() >= datetime.time(*b["zu"])):
        d -= datetime.timedelta(days=1)
        while not ist_handelstag(boerse, d):
            d -= datetime.timedelta(days=1)
    return datetime.datetime.combine(d, datetime.time(*b["zu"]), tzinfo=b["tz"])


def handelstage(boerse, von, bis):
    """Anzahl Handelstage im Zeitraum (von ausschliesslich, bis einschliesslich)."""
    n, d = 0, von
    while d < bis:
        d += datetime.timedelta(days=1)
        n += ist_handelstag(boerse, d)
    return n


# ---------------------------------------------------------------------------------------------------- Marktdaten
def _zeit(text):
    try:
        t = datetime.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def marktdaten(indizes_datei, code, jetzt, max_alter_offen_min=90):
    """Indexdaten aus indizes.json -> dict mit Kurs, Tagesveraenderung, Zeiten und Status:
    "live" (Boerse offen, frisch), "schluss" (letzter Schlusskurs, Boerse zu), "veraltet", "fehlt"."""
    i = INDIZES[code]
    aus = {"code": code, "name": i["name"], "symbol": i["symbol"], "waehrung": i["waehrung"], "quelle": QUELLE,
           "boerse": BOERSEN[i["boerse"]]["name"], "offen": boerse_offen(i["boerse"], jetzt), "kurs": None,
           "status": "fehlt", "hinweis": "Für diesen Index liegen gerade keine Marktdaten vor – bitte den "
                                         "Indexstand von Hand eingeben (wird als Referenzwert gekennzeichnet)."}
    w = (((indizes_datei or {}).get("werte") or {}) if isinstance(indizes_datei, dict) else {}).get(i["yahoo"])
    try:
        kurs, vor = float(w["k"]), float(w["p"])
    except (TypeError, KeyError, ValueError):
        return aus
    abruf = _zeit(w.get("t"))
    markt = _zeit(w.get("m")) or abruf
    if kurs <= 0 or vor <= 0 or not abruf:
        return aus
    aus.update({"kurs": kurs, "vortag": vor, "diff": kurs - vor, "pct": (kurs / vor - 1) * 100,
                "abruf": abruf, "zeit": markt})
    schluss = letzter_handelsschluss(i["boerse"], jetzt)
    if aus["offen"]:
        frisch = jetzt - abruf <= datetime.timedelta(minutes=max_alter_offen_min)
        aus["status"] = "live" if frisch else "veraltet"
    else:
        aus["status"] = "schluss" if markt >= schluss - datetime.timedelta(hours=1) else "veraltet"
    aus["hinweis"] = {"live": "Börse geöffnet – Stand mit bis zu 15 Min. Verzögerung.",
                      "schluss": "Börse geschlossen – letzter Schlusskurs.",
                      "veraltet": "Daten sind älter als erwartet – bitte aktualisieren oder den Indexstand "
                                  "von Hand prüfen."}[aus["status"]]
    return aus


def eurusd(indizes_datei):
    """US-Dollar je Euro aus indizes.json oder None."""
    w = (((indizes_datei or {}).get("werte") or {}) if isinstance(indizes_datei, dict) else {}).get(FX_SYMBOL)
    try:
        x = float(w["k"])
    except (TypeError, KeyError, ValueError):
        return None
    return x if x > 0 else None


# ---------------------------------------------------------------------------------------------------- Eingaben
def kursziel_bereich(kurs):
    """Reglerbereich und Schrittweite fuer das Kursziel: -50 % ... +50 % um den aktuellen Stand, runde Schritte."""
    roh = kurs * 0.001
    stufe = 10 ** math.floor(math.log10(roh)) if roh > 0 else 1
    schritt = next(stufe * f for f in (1, 2, 5, 10) if stufe * f >= roh)
    unten = math.floor(kurs * 0.5 / schritt) * schritt
    oben = math.ceil(kurs * 1.5 / schritt) * schritt
    return float(unten), float(oben), float(schritt)


def kursziel_standard(kurs, richtung="long"):
    """10 % ueber (Long) bzw. unter (Short) dem aktuellen Stand, auf die Schrittweite gerundet."""
    _, _, schritt = kursziel_bereich(kurs)
    return round(kurs * (1.1 if richtung == "long" else 0.9) / schritt) * schritt


def zieltermin_standard(heute):
    d = datetime.date(2027, 1, 29)
    return d if d > heute else _monate_spaeter(heute, 3)


def _monate_spaeter(d, n):
    m = d.month - 1 + n
    jahr, monat = d.year + m // 12, m % 12 + 1
    tag = min(d.day, [31, 29 if jahr % 4 == 0 and (jahr % 100 or jahr % 400 == 0) else 28, 31, 30, 31, 30, 31, 31,
                      30, 31, 30, 31][monat - 1])
    return datetime.date(jahr, monat, tag)


def zieltermin_schnell(heute, monate):
    return _monate_spaeter(heute, monate)


def pruefe(einsatz=None, start=None, ziel=None, hebel=None, richtung=None, max_hebel=HEBEL["max_erweitert"]):
    """Eingaben pruefen -> Liste verstaendlicher Fehlermeldungen (leer = gueltig)."""
    f = []
    if einsatz is not None and not (EINSATZ["min"] <= einsatz <= 10_000_000):
        f.append(f"Der Einsatz muss mindestens {de(EINSATZ['min'], 0)} € betragen.")
    if start is not None and not (start > 0 and math.isfinite(start)):
        f.append("Der Indexstand muss größer als 0 sein.")
    if ziel is not None and not (ziel > 0 and math.isfinite(ziel)):
        f.append("Das Kursziel muss größer als 0 sein.")
    if hebel is not None and not (HEBEL["min"] <= hebel <= max_hebel):
        f.append(f"Der Hebel muss zwischen 1 und {max_hebel:g} liegen.")
    if richtung is not None and richtung not in ("long", "short"):
        f.append("Richtung muss Long oder Short sein.")
    return f


# ---------------------------------------------------------------------------------------------------- Modus 1
def simulation(einsatz, start, ziel, hebel, richtung):
    """Freie Hebel-Simulation mit konstantem Anfangshebel (vereinfacht). -> dict"""
    fehler = pruefe(einsatz, start, ziel, hebel, richtung)
    if fehler:
        raise ValueError(fehler[0])
    index_pct = (ziel / start - 1) * 100
    rendite = index_pct * hebel * (1 if richtung == "long" else -1)
    rendite = max(rendite, -100.0)                                 # Verlust hoechstens 100 % des Einsatzes
    gv = einsatz * rendite / 100
    ko = start * (1 - 1 / hebel) if richtung == "long" else start * (1 + 1 / hebel)
    return {"modus": "simulation", "einsatz": einsatz, "kapital": einsatz, "start": start, "ziel": ziel,
            "hebel": hebel, "richtung": richtung, "index_pct": index_pct, "rendite_pct": rendite, "gv": gv,
            "endwert": max(0.0, einsatz + gv), "break_even": start, "max_verlust": einsatz,
            "ko_schwelle": ko if hebel > 1 else None, "ko_abstand_pct": 100 / hebel if hebel > 1 else None,
            "ko_abstand_pkt": abs(start - ko) if hebel > 1 else None,
            "ko_erreicht": hebel > 1 and (ziel <= ko if richtung == "long" else ziel >= ko)}


def hebel_vergleich(einsatz, start, ziel, richtung, hebel=HEBEL_VERGLEICH):
    return [simulation(einsatz, start, ziel, h, richtung) for h in hebel]


# ---------------------------------------------------------------------------------------------------- Modus 2
PRODUKT_FELDER = ("isin", "wkn", "emittent", "basiswert", "typ", "richtung", "basispreis", "ko_schwelle", "bezug",
                  "geld", "brief", "waehrung", "finanzierung_pct", "restwert", "stand", "quelle")


def produkt_pruefen(p, index_kurs=None):
    """Produktdaten auf Plausibilitaet pruefen -> (fehler, warnungen)."""
    fehler, warn = [], []
    if p.get("basiswert") not in INDIZES:
        fehler.append("Basiswert muss Nasdaq 100, DAX 40, S&P 500 oder Dow Jones sein.")
    if p.get("richtung") not in ("long", "short"):
        fehler.append("Richtung (Long/Short) fehlt.")
    for feld, text in (("basispreis", "Basispreis"), ("ko_schwelle", "Knock-out-Schwelle"),
                       ("bezug", "Bezugsverhältnis"), ("brief", "Briefkurs")):
        if not (isinstance(p.get(feld), (int, float)) and p[feld] > 0):
            fehler.append(f"{text} muss größer als 0 sein.")
    if fehler:
        return fehler, warn
    if p.get("geld") is not None and p["geld"] > p["brief"]:
        fehler.append("Der Geldkurs darf nicht über dem Briefkurs liegen.")
    long = p["richtung"] == "long"
    if long and p["ko_schwelle"] < p["basispreis"]:
        fehler.append("Bei Long liegt die Knock-out-Schwelle auf oder über dem Basispreis.")
    if not long and p["ko_schwelle"] > p["basispreis"]:
        fehler.append("Bei Short liegt die Knock-out-Schwelle auf oder unter dem Basispreis.")
    if index_kurs and (index_kurs <= p["ko_schwelle"] if long else index_kurs >= p["ko_schwelle"]):
        fehler.append("Der Index liegt bereits jenseits der Knock-out-Schwelle – das Produkt ist vermutlich "
                      "ausgeknockt.")
    if not 0 <= (p.get("finanzierung_pct") or 0) <= 25:
        warn.append("Ungewöhnliche Finanzierungskosten – bitte prüfen (übliche Werte: 2–8 % p. a.).")
    return fehler, warn


def _fx(produkt, eurusd_kurs):
    """Faktor Indexwaehrung -> EUR (1 bei DAX, 1/EURUSD bei US-Indizes)."""
    if INDIZES[produkt["basiswert"]]["waehrung"] == "EUR":
        return 1.0
    if not eurusd_kurs or eurusd_kurs <= 0:
        raise ValueError("Für US-Indizes wird der EUR/USD-Kurs benötigt.")
    return 1.0 / eurusd_kurs


def basispreis_am(produkt, tage):
    """Basispreis nach `tage` Kalendertagen: Finanzierungskosten verschieben ihn gegen den Anleger
    (Long: steigt, Short: faellt). Die KO-Schwelle wandert im gleichen Verhaeltnis mit."""
    r = (produkt.get("finanzierung_pct") or 0) / 100 * max(0, tage) / 365
    faktor = 1 + r if produkt["richtung"] == "long" else 1 - r
    return produkt["basispreis"] * faktor, produkt["ko_schwelle"] * faktor


def innerer_wert_eur(produkt, index, basis, eurusd_kurs):
    """Innerer Wert je Zertifikat in EUR: (Index - Basis) x Bezug (Long), umgekehrt bei Short, nie negativ."""
    diff = index - basis if produkt["richtung"] == "long" else basis - index
    return max(0.0, diff * produkt["bezug"]) * _fx(produkt, eurusd_kurs)


def produkt_hebel(produkt, index, eurusd_kurs):
    """Tatsaechlicher Hebel = Indexstand x Bezug (in EUR) / Briefkurs - ergibt sich aus dem Produkt."""
    return index * produkt["bezug"] * _fx(produkt, eurusd_kurs) / produkt["brief"]


def zertifikat(produkt, einsatz, index_start, ziel, eurusd_start=None, eurusd_ziel=None, tage=0,
               gebuehr_kauf=0.0, gebuehr_verkauf=0.0):
    """Echtes Knock-out-Zertifikat: Stueckzahl ueber den Briefkurs, Wert am Zieltermin (Verkauf zum Geldkurs, d. h.
    der heutige Spread bleibt), Finanzierungskosten, Knock-out (-> Restwert). -> dict"""
    fehler, warn = produkt_pruefen(produkt, index_start)
    fehler += pruefe(einsatz=einsatz, start=index_start, ziel=ziel)
    if fehler:
        raise ValueError(fehler[0])
    eurusd_ziel = eurusd_ziel or eurusd_start
    long = produkt["richtung"] == "long"
    brief = produkt["brief"]
    spread = max(0.0, brief - (produkt.get("geld") if produkt.get("geld") is not None else brief))
    stueck = int(max(0.0, einsatz - gebuehr_kauf) // brief)
    if stueck < 1:
        raise ValueError("Der Einsatz reicht nicht für ein Zertifikat.")
    kapital = stueck * brief + gebuehr_kauf
    basis_t, ko_t = basispreis_am(produkt, tage)
    ko = ziel <= ko_t if long else ziel >= ko_t
    if ko:
        je_stueck = max(0.0, produkt.get("restwert") or 0.0)
    else:
        je_stueck = max(0.0, innerer_wert_eur(produkt, ziel, basis_t, eurusd_ziel) - spread)
    endwert = max(0.0, stueck * je_stueck - (gebuehr_verkauf if stueck * je_stueck > 0 else 0))
    gv = endwert - kapital
    # Break-even am Zieltermin: Indexstand, bei dem der Verkaufserloes das eingesetzte Kapital deckt
    noetig = (kapital + gebuehr_verkauf) / stueck + spread
    fx_ziel = _fx(produkt, eurusd_ziel)
    be = basis_t + noetig / (produkt["bezug"] * fx_ziel) * (1 if long else -1)
    modell_jetzt = innerer_wert_eur(produkt, index_start, produkt["basispreis"], eurusd_start)
    mitte = (brief + (produkt.get("geld") or brief)) / 2
    if mitte and abs(modell_jetzt / mitte - 1) > 0.05:
        warn.append(f"Der berechnete innere Wert ({de(modell_jetzt)} €) weicht deutlich vom Kurs des Zertifikats "
                    f"({de(mitte)} €) ab – Bezugsverhältnis, Basispreis und Indexstand prüfen.")
    abstand = (index_start - produkt["ko_schwelle"]) if long else (produkt["ko_schwelle"] - index_start)
    return {"modus": "zertifikat", "stueck": stueck, "kapital": kapital, "einsatz": einsatz, "start": index_start,
            "ziel": ziel, "richtung": produkt["richtung"], "hebel": produkt_hebel(produkt, index_start, eurusd_start),
            "index_pct": (ziel / index_start - 1) * 100, "endwert": endwert, "gv": gv,
            "rendite_pct": gv / kapital * 100, "break_even": be, "max_verlust": kapital,
            "ko_schwelle": produkt["ko_schwelle"], "ko_schwelle_ziel": ko_t, "basis_ziel": basis_t,
            "ko_abstand_pkt": abstand, "ko_abstand_pct": abstand / index_start * 100, "ko_erreicht": ko,
            "spread_eur": spread, "finanzierung_eur": abs(basis_t - produkt["basispreis"]) * produkt["bezug"]
            * fx_ziel * stueck, "warnungen": warn}


# ---------------------------------------------------------------------------------------------------- Auswertung
def szenarien(rechne, start, prozente=SZENARIEN):
    """rechne(ziel) -> Ergebnis; je Indexbewegung in % ein Ergebnis (Annahme: kein Knock-out unterwegs, ausser die
    Schwelle liegt im Szenario selbst)."""
    return [(p, rechne(start * (1 + p / 100))) for p in prozente]


def ko_warnung(abstand_pct):
    if abstand_pct is None:
        return None
    if abstand_pct < KO_WARNUNG_PCT:
        return ("hoch", f"Sehr geringer Abstand zur Knock-out-Schwelle ({de(abstand_pct, 1)} %) – schon eine "
                        "normale Tagesschwankung kann zum Knock-out führen.")
    if abstand_pct < KO_HINWEIS_PCT:
        return ("mittel", f"Geringer Abstand zur Knock-out-Schwelle ({de(abstand_pct, 1)} %).")
    return None


def diagramm_achse(start, ziel, ko=None, punkte=121):
    """X-Werte fuer das Gewinndiagramm: deckt aktuellen Stand, Kursziel und KO-Schwelle mit Rand ab."""
    werte = [start, ziel] + ([ko] if ko else [])
    lo, hi = min(werte), max(werte)
    rand = max((hi - lo) * 0.25, start * 0.1)
    lo, hi = max(start * 0.05, lo - rand), hi + rand
    return [lo + (hi - lo) * i / (punkte - 1) for i in range(punkte)]


def csv_zeilen(kopf, ergebnis, vergleich=(), szen=()):
    """Ergebnisse als Zeilen [(Bereich, Bezeichnung, Wert)] fuer den CSV-Export."""
    z = [("Eingaben", k, v) for k, v in kopf.items()]
    for k, titel in (("gv", "Gewinn/Verlust €"), ("endwert", "Gesamtwert €"), ("index_pct", "Indexveränderung %"),
                     ("rendite_pct", "Rendite %"), ("kapital", "Eingesetztes Kapital €"), ("hebel", "Hebel"),
                     ("ko_schwelle", "Knock-out-Schwelle"), ("ko_abstand_pct", "Abstand KO %"),
                     ("break_even", "Break-even-Kurs"), ("stueck", "Stückzahl")):
        if ergebnis.get(k) is not None:
            z.append(("Ergebnis", titel, round(ergebnis[k], 4)))
    for e in vergleich:
        z.append(("Hebelvergleich", f"{e['hebel']:g}x", f"{e['gv']:.2f} € / {e['rendite_pct']:.2f} % / "
                                                         f"{e['endwert']:.2f} €"))
    for p, e in szen:
        z.append(("Szenario", f"{p:+d} %", f"{e['gv']:.2f} €"))
    return z
