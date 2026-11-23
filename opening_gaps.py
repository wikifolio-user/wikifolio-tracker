"""Opening-Gaps (Close-to-Open) fuer Nasdaq 100, DAX 40, S&P 500 und Dow Jones - reine Rechenlogik.

Ergaenzt den Gap Analyzer (gap_analyzer.py, High-Low-Gaps), ohne ihn zu veraendern: beide Gap-Arten werden
unabhaengig erkannt, gespeichert und ausgewertet. Ein Opening-Gap kann bestehen, ohne dass es ein High-Low-Gap gibt.

  Opening-Gap   = Eroeffnung heute - Schluss am vorherigen Handelstag
  Opening-Gap % = (Eroeffnung heute / Schluss vorher - 1) x 100
  Gap-up:   Eroeffnung > Schluss vorher -> geschlossen, sobald ein Tief <= Schluss vorher
  Gap-down: Eroeffnung < Schluss vorher -> geschlossen, sobald ein Hoch >= Schluss vorher
Fuellgrad: weitestes erreichtes Kursniveau in Richtung des vorherigen Schlusses (0-100 %), ab dem Entstehungstag.
Status: offen / teilweise / heute (am Entstehungstag geschlossen) / spaeter (an einem spaeteren Handelstag).
Ein geschlossenes Gap wird nie wieder offen; geschlossene Gaps bleiben in der Historie.

Uhrzeiten (erste Beruehrung, Schliessung) gibt es NUR aus Intraday-Daten (intraday_auswerten); mit reinen
Tageskerzen steht nur das Datum da - es wird keine Uhrzeit erfunden.
Kerzen: [[iso, o, h, l, c]] aufsteigend (state/markt/ohlc.json, nur abgeschlossene Handelstage)."""
import datetime
import statistics

MIN_PCT = 0.1                       # Standard-Mindestgroesse; kleinere Luecken gelten als "kein Opening-Gap"
FENSTER = (5, 20)                   # Schliessungsquoten innerhalb n Handelstagen (dazu: am selben Tag)
STATUS = {"offen": "Offen", "teilweise": "Teilweise geschlossen", "heute": "Heute vollständig geschlossen",
          "spaeter": "An einem späteren Handelstag geschlossen", "kein": "Kein Opening-Gap"}
DATENART = {"echtzeit": "Echtzeitdaten", "verzoegert": "Verzögerte Marktdaten", "tag": "Historische Tagesdaten"}


def gap_id(kurz, datum):
    return f"{kurz}|open|{datum}"


def _fuell(typ, schluss_vorher, eroeffnung, extrem):
    """Fuellgrad 0-100 aus dem weitesten Kurs Richtung Vortagesschluss (extrem = Tief bei up, Hoch bei down)."""
    groesse = abs(eroeffnung - schluss_vorher)
    if groesse <= 0:
        return 0.0
    weg = (eroeffnung - extrem) if typ == "up" else (extrem - eroeffnung)
    return max(0.0, min(100.0, weg / groesse * 100))


def erkennen(kerzen, kurz, min_pct=MIN_PCT, intraday=None, vorlaeufig=None):
    """Einen Eintrag je Handelstag (ab der zweiten Kerze), auch "kein" bei Luecken unter min_pct.
    intraday: {datum: {"beruehrt": "HH:MM", "geschlossen": "HH:MM"|None, "intervall", "datenart", ...}} - nur fuer
              Uhrzeiten am Entstehungstag (aus intraday_auswerten); fehlt er, gibt es nur Daten.
    vorlaeufig: laufender Handelstag als Kerze [iso, o, h, l, c] (aus Intraday-Daten) - wird angehaengt und als
                vorlaeufig gekennzeichnet; zaehlt nicht in Statistiken.
    -> [dict] chronologisch"""
    reihe = list(kerzen or [])
    vorl_datum = None
    if vorlaeufig and (not reihe or vorlaeufig[0] > reihe[-1][0]):   # nur ein wirklich neuer (laufender) Tag
        reihe.append(list(vorlaeufig))
        vorl_datum = vorlaeufig[0]
    intraday = intraday or {}
    aus = []
    for i in range(1, len(reihe)):
        vor, k = reihe[i - 1], reihe[i]
        d, o, h, l_ = k[0], k[1], k[2], k[3]
        sv = vor[4]
        if not sv or not o:
            continue
        pct = (o / sv - 1) * 100
        typ = "up" if pct > 0 else "down" if pct < 0 else "kein"
        if abs(pct) < min_pct:
            typ = "kein"
        g = {"id": gap_id(kurz, d), "index": kurz, "datum": d, "typ": typ, "schluss_vorher": sv, "eroeffnung": o,
             "hoch": h, "tief": l_, "schluss": k[4], "groesse": abs(o - sv), "groesse_pct": pct,
             "status": "kein" if typ == "kein" else "offen", "fuellgrad": 0.0, "rest": abs(o - sv),
             "beruehrt": None, "beruehrt_zeit": None, "geschlossen": None, "geschlossen_zeit": None,
             "dauer_tage": None, "dauer_min": None, "vorlaeufig": d == vorl_datum, "alter": len(reihe) - 1 - i,
             "zeiten": None}
        if typ != "kein":
            extrem = l_ if typ == "up" else h
            g["fuellgrad"] = _fuell(typ, sv, o, extrem)
            if g["fuellgrad"] > 0:
                g["beruehrt"] = d
            if g["fuellgrad"] >= 100:
                g.update(status="heute", geschlossen=d, dauer_tage=0)
            else:
                if g["fuellgrad"] > 0:
                    g["status"] = "teilweise"
                for j, kk in enumerate(reihe[i + 1:], 1):      # der laufende Tag zaehlt fuer den Fuellstand mit
                    extrem = kk[3] if typ == "up" else kk[2]
                    f = _fuell(typ, sv, o, extrem)
                    if f > g["fuellgrad"]:
                        g["fuellgrad"] = f
                        g["beruehrt"] = g["beruehrt"] or kk[0]
                        g["status"] = "teilweise"
                    if f >= 100:
                        g.update(status="spaeter", geschlossen=kk[0], dauer_tage=j, fuellgrad=100.0)
                        break
            g["rest"] = g["groesse"] * (1 - g["fuellgrad"] / 100)
            z = intraday.get(d)
            if z:
                g["zeiten"] = {k2: z.get(k2) for k2 in ("intervall", "datenart", "verzoegert_min", "quelle")}
                g["beruehrt_zeit"] = z.get("beruehrt") if g["beruehrt"] == d else None
                if g["status"] == "heute" and z.get("geschlossen"):
                    g["geschlossen_zeit"] = z["geschlossen"]
                    g["dauer_min"] = z.get("dauer_min")
        aus.append(g)
    return aus


def mit_kurs(gaps, kurs):
    """Abstand des aktuellen Kurses bis zur vollstaendigen Schliessung (Punkte, %); nur fuer nicht geschlossene."""
    for g in gaps:
        if g["typ"] == "kein" or g["status"] in ("heute", "spaeter") or not kurs:
            g["entfernung"] = g["entfernung_pct"] = None
            continue
        e = (kurs - g["schluss_vorher"]) if g["typ"] == "up" else (g["schluss_vorher"] - kurs)
        g["entfernung"] = max(0.0, e)
        g["entfernung_pct"] = max(0.0, e) / kurs * 100
    return gaps


def heute(gaps):
    """Letzter Eintrag (laufender oder letzter abgeschlossener Handelstag) - auch wenn bereits geschlossen."""
    return gaps[-1] if gaps else None


def jahre(gaps):
    return sorted({g["datum"][:4] for g in gaps}, reverse=True)


def filtern(gaps, jahr=None, typ=None, status=None, mit_kein=False):
    return [g for g in gaps if (mit_kein or g["typ"] != "kein") and (not jahr or g["datum"].startswith(str(jahr)))
            and (not typ or g["typ"] == typ) and (not status or g["status"] in status)]


def statistik(gaps):
    """Statistik der ENDGUELTIGEN Opening-Gaps (ohne vorlaeufige und ohne "kein"). Quoten je Fenster nur ueber Gaps,
    die mindestens so lange beobachtet werden konnten (alter >= n) oder vorher geschlossen wurden."""
    def zus(liste):
        if not liste:
            return {"anzahl": 0}
        pct = [abs(g["groesse_pct"]) for g in liste]
        pkt = [g["groesse"] for g in liste]
        ups = [g for g in liste if g["typ"] == "up"]
        downs = [g for g in liste if g["typ"] == "down"]
        zu = [g for g in liste if g["dauer_tage"] is not None]
        quoten = {0: (sum(g["status"] == "heute" for g in liste) / len(liste) * 100, len(liste))}
        for n in FENSTER:
            basis = [g for g in liste if (g["dauer_tage"] is not None and g["dauer_tage"] <= n) or g["alter"] >= n]
            ok = [g for g in basis if g["dauer_tage"] is not None and g["dauer_tage"] <= n]
            quoten[n] = (len(ok) / len(basis) * 100, len(basis)) if basis else (None, 0)
        minuten = [g["dauer_min"] for g in liste if g.get("dauer_min") is not None]
        return {"anzahl": len(liste), "up": len(ups), "down": len(downs),
                "pct_mittel": statistics.mean(pct), "pct_median": statistics.median(pct),
                "pkt_mittel": statistics.mean(pkt),
                "groesstes_up": max(ups, key=lambda g: g["groesse_pct"]) if ups else None,
                "groesstes_down": min(downs, key=lambda g: g["groesse_pct"]) if downs else None,
                "quoten": quoten, "dauer_tage_mittel": statistics.mean([g["dauer_tage"] for g in zu]) if zu else None,
                "dauer_min_mittel": statistics.mean(minuten) if minuten else None, "mit_minuten": len(minuten),
                "noch_offen": sum(g["status"] in ("offen", "teilweise") for g in liste)}
    fertig = [g for g in gaps if g["typ"] != "kein" and not g["vorlaeufig"]]
    return {"alle": zus(fertig), "up": zus([g for g in fertig if g["typ"] == "up"]),
            "down": zus([g for g in fertig if g["typ"] == "down"])}


# ---------------------------------------------------------------- Intraday
def _hhmm(ts, tz):
    return datetime.datetime.fromtimestamp(int(ts), tz).strftime("%H:%M")


def intraday_parsen(antwort, boerse_tz, auf, zu):
    """Yahoo-Chart-Antwort (interval 1m/5m) -> {"tage": {iso: [[ts, o, h, l, c], ...]}, "intervall",
    "verzoegert_min", "instrument"} oder None. Nur Instrumenttyp INDEX, nur Kerzen innerhalb der regulaeren
    Handelszeit (auf/zu als (h, m) in Boersenzeit) - keine Futures, CFDs oder vorboerslichen Kurse."""
    try:
        r = antwort["chart"]["result"][0]
        meta, ts, q = r["meta"], r["timestamp"], r["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if str(meta.get("instrumentType") or "").upper() != "INDEX":
        return None
    tage = {}
    for i, t in enumerate(ts or []):
        try:
            vals = [q[k][i] for k in ("open", "high", "low", "close")]
            if any(v is None for v in vals) or min(vals) <= 0:
                continue
            dt = datetime.datetime.fromtimestamp(int(t), boerse_tz)
        except (KeyError, IndexError, TypeError, ValueError, OSError):
            continue
        if not datetime.time(*auf) <= dt.time() < datetime.time(*zu):
            continue
        tage.setdefault(dt.date().isoformat(), []).append([int(t)] + [float(v) for v in vals])
    verz = meta.get("exchangeDataDelayedBy")
    return {"tage": {d: sorted(b) for d, b in tage.items()}, "intervall": meta.get("dataGranularity") or "",
            "verzoegert_min": int(verz) if isinstance(verz, (int, float)) else None,
            "instrument": "INDEX"}


def datenart(verzoegert_min):
    if verzoegert_min is None:
        return "verzoegert"                          # unbekannt -> nie als Echtzeit ausgeben
    return "echtzeit" if verzoegert_min == 0 else "verzoegert"


def intraday_auswerten(bars, schluss_vorher, boerse_tz, intervall="", verzoegert_min=None, vollstaendig=False):
    """Intraday-Kerzen EINES Handelstags -> Tageskerze und Uhrzeiten des Opening-Gaps.
    Erste Beruehrung = erste Kerze, die von der Eroeffnung Richtung Vortagesschluss laeuft; Schliessung = erste Kerze,
    deren Tief (up) bzw. Hoch (down) den Vortagesschluss erreicht. Zeit = Beginn dieser Kerze (Genauigkeit = Intervall).
    -> {"kerze": [iso, o, h, l, c], "beruehrt", "geschlossen", "dauer_min", "intervall", "datenart", ...} oder None"""
    if not bars or not schluss_vorher:
        return None
    start = datetime.datetime.fromtimestamp(bars[0][0], boerse_tz)
    o = bars[0][1]
    h = max(b[2] for b in bars)
    l_ = min(b[3] for b in bars)
    typ = "up" if o > schluss_vorher else "down" if o < schluss_vorher else "kein"
    beruehrt = geschlossen = dauer = None
    if typ != "kein":
        for b in bars:
            extrem = b[3] if typ == "up" else b[2]
            if beruehrt is None and (extrem < o if typ == "up" else extrem > o):
                beruehrt = _hhmm(b[0], boerse_tz)
            if (extrem <= schluss_vorher) if typ == "up" else (extrem >= schluss_vorher):
                geschlossen = _hhmm(b[0], boerse_tz)
                dauer = int((b[0] - bars[0][0]) // 60)
                break
    return {"kerze": [start.date().isoformat(), o, h, l_, bars[-1][4]], "beruehrt": beruehrt,
            "geschlossen": geschlossen, "dauer_min": dauer, "intervall": intervall,
            "datenart": datenart(verzoegert_min), "verzoegert_min": verzoegert_min, "vollstaendig": vollstaendig,
            "letzte_zeit": _hhmm(bars[-1][0], boerse_tz), "quelle": "Yahoo Finance (Cash-Index, Intraday)"}


def intraday_zusammenfuehren(alt, neu):
    """Gespeicherte Tageszusammenfassungen {datum: auswertung} um neue ergaenzen. Eine einmal erkannte Schliessung
    bleibt erhalten (nie wieder "offen"); vollstaendige Tage werden nicht mehr ueberschrieben; feinere Intervalle
    (1m) ersetzen groebere (5m) nur bei noch unvollstaendigen Tagen."""
    aus = dict(alt or {})
    for d, n in (neu or {}).items():
        if not n:
            continue
        a = aus.get(d)
        if a and a.get("vollstaendig") and not n.get("vollstaendig"):
            continue
        if a and a.get("geschlossen") and not n.get("geschlossen"):
            n = dict(n, geschlossen=a["geschlossen"], dauer_min=a.get("dauer_min"))
        aus[d] = {k: v for k, v in n.items() if k != "kerze"} | {"kerze": n.get("kerze")}
    return aus


# ---------------------------------------------------------------- Alerts (nur in der App)
STANDARD_ALERTS = {"neu_klein_an": True, "neu_klein_pct": 0.5, "neu_gross_an": True, "neu_gross_pct": 1.0,
                   "halb_an": True, "halb_pct": 50.0, "geschlossen_an": True, "offen_schluss_an": True}
ALERT_TAGE = 7


def alerts(gaps_je_index, einstellungen=None, gesehen=(), heute_datum=None):
    """Ereignisse der letzten ALERT_TAGE -> [{"schluessel", "index", "datum", "text", "art"}] (nur ungesehene).
    Jeder Alert hat einen festen Schluessel und erscheint daher nur einmal."""
    e = dict(STANDARD_ALERTS, **(einstellungen or {}))
    heute_datum = heute_datum or datetime.date.today()
    grenze = (heute_datum - datetime.timedelta(days=ALERT_TAGE)).isoformat()
    gesehen, aus = set(gesehen), []

    def neu(schluessel, g, text, art):
        if schluessel not in gesehen:
            aus.append({"schluessel": schluessel, "index": g["index"], "datum": g["datum"], "text": text, "art": art})

    for kurz, gaps in (gaps_je_index or {}).items():
        for g in gaps:
            if g["typ"] == "kein" or g["datum"] < grenze:
                continue
            richtung = "Gap-up" if g["typ"] == "up" else "Gap-down"
            gr = abs(g["groesse_pct"])
            if e["neu_gross_an"] and gr > e["neu_gross_pct"]:
                neu(g["id"] + "|gross", g, f"{kurz}: neues Opening-{richtung} {gr:.2f} % (> {e['neu_gross_pct']:g} %)",
                    "neu")
            elif e["neu_klein_an"] and gr > e["neu_klein_pct"]:
                neu(g["id"] + "|klein", g, f"{kurz}: neues Opening-{richtung} {gr:.2f} % (> {e['neu_klein_pct']:g} %)",
                    "neu")
            if e["halb_an"] and g["fuellgrad"] >= e["halb_pct"] and g["status"] in ("teilweise",):
                neu(g["id"] + "|halb", g, f"{kurz}: Opening-{richtung} vom {g['datum']} zu "
                                          f"{g['fuellgrad']:.0f} % geschlossen", "teilweise")
            if e["geschlossen_an"] and g["status"] in ("heute", "spaeter"):
                zeit = f" um {g['geschlossen_zeit']}" if g.get("geschlossen_zeit") else ""
                neu(g["id"] + "|zu", g, f"{kurz}: Opening-{richtung} vom {g['datum']} vollständig geschlossen "
                                        f"({g['geschlossen']}{zeit})", "geschlossen")
            if e["offen_schluss_an"] and not g["vorlaeufig"] and g["alter"] == 0 and g["status"] in ("offen",
                                                                                                    "teilweise"):
                neu(g["id"] + "|schluss", g, f"{kurz}: Opening-{richtung} vom {g['datum']} am Handelsschluss noch "
                                             f"offen ({g['fuellgrad']:.0f} % gefüllt)", "offen")
    return aus
