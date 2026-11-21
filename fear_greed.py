"""Fear & Greed Monitor - reine Rechenlogik ohne Streamlit.

Externe Indikatoren (state/markt/sentiment.json, markt_daten.py):
  US-Aktienmarkt   CNN Business Fear & Greed
  Kryptowaehrungen Alternative.me Crypto Fear & Greed
  Bitcoin          kein eigener frei nutzbarer Index -> Crypto Fear & Greed als ausdruecklich gekennzeichneter PROXY
                   (zaehlt nicht in Gesamtstimmung/Durchschnitt, damit kein Wert doppelt eingeht)
  Ethereum         keine verlaessliche freie Quelle (CoinMarketCap/CoinGlass nur mit kostenpflichtigem Schluessel)
                   -> "Nicht verfuegbar"; nie ein Bitcoin- oder Gesamtmarktwert als Ethereum-Wert
Eigene Scores (state/markt/ohlc.json, Tageskerzen): "Eigener ...-Sentiment-Score" fuer DAX, Nasdaq 100, S&P 500 und
Dow Jones - KEIN offizieller Fear-&-Greed-Index. Feste Faktoren und Gewichte (FAKTOREN), je 0-100 normiert.
"""
import datetime
import math
import statistics

# Einheitliche Dashboard-Kategorien (Wert < obere Grenze)
KATEGORIEN = [(25, "Extreme Angst", "#EF4444"), (45, "Angst", "#F97316"), (56, "Neutral", "#EAB308"),
              (76, "Gier", "#84CC16"), (101, "Extreme Gier", "#22C55E")]

# Eigener Score: (Schluessel, Bezeichnung, Gewicht %, Beschreibung der Normierung)
FAKTOREN = [
    ("rsi", "RSI (14 Tage)", 25, "RSI direkt als 0–100"),
    ("sma50", "Abstand zur 50-Tage-Linie", 20, "−10 % → 0, 0 % → 50, +10 % → 100"),
    ("sma200", "Abstand zur 200-Tage-Linie", 20, "−15 % → 0, 0 % → 50, +15 % → 100"),
    ("mom20", "Momentum 20 Handelstage", 20, "−8 % → 0, 0 % → 50, +8 % → 100"),
    ("vola", "Volatilität 20 Tage ggü. 1 Jahr", 15, "doppelt so hoch → 0, gleich → 67, halb so hoch → 100"),
]
MIN_KERZEN = 260                 # 200-Tage-Linie + 1 Jahr Volatilitaet brauchen so viele Tageskerzen

MAERKTE = [  # (id, Name, Art, Quelle/Basis)
    ("us", "US-Aktienmarkt", "extern", "cnn"),
    ("krypto", "Kryptowährungen", "extern", "crypto"),
    ("btc", "Bitcoin", "proxy", "crypto"),
    ("eth", "Ethereum", "fehlt", None),
    ("dax", "DAX 40", "eigen", "^GDAXI"),
    ("ndx", "Nasdaq 100", "eigen", "^NDX"),
    ("spx", "S&P 500", "eigen", "^GSPC"),
    ("dji", "Dow Jones", "eigen", "^DJI"),
]
VERALTET_NACH_H = {"cnn": 36, "crypto": 48}     # Quelle aktualisiert (mind.) taeglich
QUELLEN_TEXT = {"cnn": "CNN Business", "crypto": "Alternative.me"}


def kategorie(wert):
    """-> (Name, Farbe) der Dashboard-Kategorie oder (None, None)."""
    if wert is None or not 0 <= wert <= 100:
        return None, None
    for grenze, name, farbe in KATEGORIEN:
        if wert < grenze:
            return name, farbe
    return KATEGORIEN[-1][1], KATEGORIEN[-1][2]


def gruppe(wert):
    """Angst / Neutral / Gier (fuer die Zaehlung)."""
    k, _ = kategorie(wert)
    return None if k is None else ("Angst" if "Angst" in k else "Gier" if "Gier" in k else "Neutral")


ORIGINAL = {"extreme fear": "Extreme Angst", "fear": "Angst", "neutral": "Neutral", "greed": "Gier",
            "extreme greed": "Extreme Gier"}


def original_deutsch(text):
    return ORIGINAL.get(str(text or "").strip().lower(), str(text or ""))


# ---------------------------------------------------------------------------------------------------- eigener Score
def _linear(x, lo, hi):
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))


def rsi(schluss, n=14):
    """RSI nach Wilder (geglaettet) -> 0..100 oder None."""
    if len(schluss) < n + 1:
        return None
    d = [b - a for a, b in zip(schluss[:-1], schluss[1:])]
    auf = sum(max(x, 0) for x in d[:n]) / n
    ab = sum(max(-x, 0) for x in d[:n]) / n
    for x in d[n:]:
        auf = (auf * (n - 1) + max(x, 0)) / n
        ab = (ab * (n - 1) + max(-x, 0)) / n
    if ab == 0:
        return 100.0
    return 100 - 100 / (1 + auf / ab)


def _vola(renditen):
    return statistics.pstdev(renditen) * math.sqrt(252) if len(renditen) > 1 else None


def faktoren(schluss):
    """Rohwerte und 0-100-Teilwerte der Faktoren aus Schlusskursen (aelteste zuerst) -> dict oder None."""
    if len(schluss) < MIN_KERZEN or any(not x or x <= 0 for x in schluss[-MIN_KERZEN:]):
        return None
    k = schluss[-1]
    sma50 = sum(schluss[-50:]) / 50
    sma200 = sum(schluss[-200:]) / 200
    ren = [math.log(b / a) for a, b in zip(schluss[-253:-1], schluss[-252:])]
    v20, v252 = _vola(ren[-20:]), _vola(ren)
    roh = {"rsi": rsi(schluss[-120:]), "sma50": (k / sma50 - 1) * 100, "sma200": (k / sma200 - 1) * 100,
           "mom20": (k / schluss[-21] - 1) * 100, "vola": v20 / v252 if v252 else None}
    teil = {"rsi": roh["rsi"], "sma50": _linear(roh["sma50"], -10, 10), "sma200": _linear(roh["sma200"], -15, 15),
            "mom20": _linear(roh["mom20"], -8, 8),
            "vola": None if roh["vola"] is None else _linear(-roh["vola"], -2.0, -0.5)}
    return {"roh": roh, "teil": teil}


def score(schluss):
    """Eigener Sentiment-Score 0-100 (gewichteter Mittelwert; alle Faktoren noetig) oder None."""
    f = faktoren(schluss)
    if not f or any(f["teil"][k] is None for k, *_ in FAKTOREN):
        return None
    return sum(f["teil"][k] * g for k, _, g, _ in FAKTOREN) / sum(g for _, _, g, _ in FAKTOREN)


def score_verlauf(kerzen, tage=None):
    """Eigener Score fuer jeden Handelstag (bzw. die letzten `tage`) -> [[iso, wert]] - nur echte Kerzen, kein
    Auffuellen. Der Score braucht nur die letzten MIN_KERZEN Schlusskurse, daher ist auch die ganze Historie schnell."""
    schluss = [k[4] for k in kerzen]
    aus = []
    erster = MIN_KERZEN if tage is None else max(MIN_KERZEN, len(kerzen) - tage)
    for i in range(erster, len(kerzen) + 1):
        s = score(schluss[i - MIN_KERZEN:i])
        if s is not None:
            aus.append([kerzen[i - 1][0], round(s, 1)])
    return aus


# ---------------------------------------------------------------------------------------------------- Karten
def _zeit(text):
    try:
        t = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def _wert_vor(verlauf, tage):
    """Wert vor `tage` Kalendertagen (letzter Punkt an oder vor dem Datum) aus [[iso, wert]]."""
    if not verlauf:
        return None
    ziel = (datetime.date.fromisoformat(verlauf[-1][0]) - datetime.timedelta(days=tage)).isoformat()
    vor = [w for d, w in verlauf if d <= ziel]
    return vor[-1] if vor else None


def eigene_verlaeufe(ohlc):
    """Score-Verlaeufe aller Indizes (ganze Historie) -> {yahoo_symbol: [[iso, wert]]}. Teuer (einige Sekunden),
    aendert sich aber nur mit neuen Tageskerzen - die App speichert das Ergebnis je Datenstand zwischen."""
    idx = ((ohlc or {}).get("indizes") or {}) if isinstance(ohlc, dict) else {}
    return {basis: score_verlauf((idx.get(basis) or {}).get("kerzen") or [])
            for _, _, art, basis in MAERKTE if art == "eigen"}


def karten(sentiment, ohlc, jetzt, eigene=None):
    """eigene: vorberechnete Score-Verlaeufe (eigene_verlaeufe), sonst wird hier gerechnet.
    Acht Karten -> [{"id", "name", "art", "wert", "kategorie", "farbe", "original", "vortag", "aenderung",
    "vorwoche", "zeit", "status" (aktuell/veraltet/fehlt), "quelle", "verlauf", "hinweis"}]."""
    q = ((sentiment or {}).get("quellen") or {}) if isinstance(sentiment, dict) else {}
    idx = ((ohlc or {}).get("indizes") or {}) if isinstance(ohlc, dict) else {}
    aus = []
    for mid, name, art, basis in MAERKTE:
        k = {"id": mid, "name": name, "art": art, "wert": None, "status": "fehlt", "verlauf": [], "hinweis": "",
             "quelle": "", "zeit": None, "vortag": None, "vorwoche": None, "original": ""}
        if art in ("extern", "proxy"):
            e = q.get(basis) or {}
            if e.get("wert") is not None:
                ok = _zeit(e.get("ok"))
                alt = not ok or jetzt - ok > datetime.timedelta(hours=VERALTET_NACH_H[basis])
                k.update({"wert": e["wert"], "vortag": e.get("vortag"), "vorwoche": e.get("vorwoche"),
                          "original": original_deutsch(e.get("kategorie")), "zeit": _zeit(e.get("zeit")) or ok,
                          "status": "veraltet" if alt else "aktuell", "verlauf": e.get("verlauf") or [],
                          "quelle": QUELLEN_TEXT[basis]})
            if art == "proxy":
                k["hinweis"] = ("Proxy: kein eigener frei verfügbarer Bitcoin-Index – angezeigt wird der Crypto "
                                "Fear & Greed Index (Alternative.me). Zählt nicht in der Gesamtstimmung.")
        elif art == "fehlt":
            k["hinweis"] = ("Nicht verfügbar: Für Ethereum gibt es keine verlässliche frei nutzbare Quelle "
                            "(CoinMarketCap/CoinGlass nur mit kostenpflichtigem API-Schlüssel).")
        else:
            e = idx.get(basis) or {}
            kerzen = e.get("kerzen") or []
            verlauf = (eigene or {}).get(basis) if eigene is not None else score_verlauf(kerzen)
            if verlauf:
                letzte = datetime.date.fromisoformat(verlauf[-1][0])
                alt = (jetzt.date() - letzte).days > 5            # mehr als ein langes Wochenende ohne neue Kerze
                k.update({"wert": verlauf[-1][1], "vortag": verlauf[-2][1] if len(verlauf) > 1 else None,
                          "vorwoche": _wert_vor(verlauf, 7), "zeit": letzte, "status": "veraltet" if alt else "aktuell",
                          "verlauf": verlauf, "quelle": f"Eigener {name}-Sentiment-Score",
                          "faktoren": faktoren([x[4] for x in kerzen])})
                if mid == "spx":
                    k["hinweis"] = "Allgemeiner US-Aktienmarkt: siehe CNN Fear & Greed (Karte US-Aktienmarkt)."
            elif kerzen:
                k["hinweis"] = f"Zu wenige Tageskerzen für einen Score (mindestens {MIN_KERZEN})."
        k["kategorie"], k["farbe"] = kategorie(k["wert"])
        k["aenderung"] = None if k["wert"] is None or k["vortag"] is None else round(k["wert"] - k["vortag"], 1)
        aus.append(k)
    return aus


def gesamt(karten_liste):
    """Gesamtstimmung aus den UNABHAENGIGEN Indikatoren (ohne Proxy, ohne fehlende).
    -> {"angst", "neutral", "gier", "score" (Dashboard-Sentiment-Score), "aenderung", "anzahl", "letzte"}"""
    unab = [k for k in karten_liste if k["art"] in ("extern", "eigen") and k["wert"] is not None]
    zaehl = {"Angst": 0, "Neutral": 0, "Gier": 0}
    for k in unab:
        zaehl[gruppe(k["wert"])] += 1
    werte = [k["wert"] for k in unab]
    aend = [k["aenderung"] for k in unab if k["aenderung"] is not None]
    zeiten = [k["zeit"] for k in unab if isinstance(k["zeit"], datetime.datetime)]
    return {"angst": zaehl["Angst"], "neutral": zaehl["Neutral"], "gier": zaehl["Gier"], "anzahl": len(unab),
            "score": round(sum(werte) / len(werte), 1) if len(werte) >= 2 else None,
            "aenderung": round(sum(aend) / len(aend), 1) if aend else None,
            "letzte": max(zeiten) if zeiten else None}


def zeitraum(verlauf, tage):
    """Verlauf der letzten `tage` Kalendertage + Kennzahlen -> dict oder None (keine Daten)."""
    if not verlauf:
        return None
    grenze = (datetime.date.fromisoformat(verlauf[-1][0]) - datetime.timedelta(days=tage)).isoformat()
    teil = [p for p in verlauf if p[0] >= grenze]
    w = [x for _, x in teil]
    return {"punkte": teil, "aktuell": w[-1], "hoch": max(w), "tief": min(w), "aenderung": round(w[-1] - w[0], 1),
            "von": teil[0][0], "bis": teil[-1][0]}


# ---------------------------------------------------------------------------------------------------- Warnungen
STANDARD_REGELN = [
    {"id": "r1", "markt": "us", "art": "unter", "schwelle": 25, "aktiv": True},
    {"id": "r2", "markt": "krypto", "art": "unter", "schwelle": 20, "aktiv": True},
    {"id": "r3", "markt": "alle", "art": "ueber", "schwelle": 75, "aktiv": True},
    {"id": "r4", "markt": "alle", "art": "aenderung", "schwelle": 15, "aktiv": True},
]
ART_TEXT = {"unter": "fällt unter", "ueber": "steigt über", "aenderung": "ändert sich um mehr als"}


def warnungen(karten_liste, regeln, gesehen=()):
    """Ausgeloeste Warnungen -> [{"schluessel", "text", "markt", "neu"}]. Ein Ereignis ist (Regel, Markt, Datum des
    Werts): dasselbe unveraenderte Ereignis loest nie zweimal "neu" aus. Proxy und fehlende Maerkte zaehlen nicht."""
    nach_id = {k["id"]: k for k in karten_liste if k["art"] in ("extern", "eigen") and k["wert"] is not None}
    aus = []
    for r in regeln or []:
        if not r.get("aktiv"):
            continue
        ziele = list(nach_id.values()) if r.get("markt") == "alle" else [nach_id[r["markt"]]] if r.get("markt") in nach_id else []
        for k in ziele:
            w, s = k["wert"], float(r.get("schwelle") or 0)
            if r["art"] == "unter":
                treffer = w < s
            elif r["art"] == "ueber":
                treffer = w > s
            else:
                treffer = k["aenderung"] is not None and abs(k["aenderung"]) > s
            if not treffer:
                continue
            tag = k["zeit"].date().isoformat() if isinstance(k["zeit"], datetime.datetime) else str(k["zeit"])
            schluessel = f"{r['id']}|{k['id']}|{tag}"
            wert_txt = (f"{'+' if (k['aenderung'] or 0) > 0 else ''}{k['aenderung']:.1f} Punkte" if r["art"] == "aenderung"
                        else f"{w:.1f}").replace(".", ",")
            aus.append({"schluessel": schluessel, "markt": k["id"], "neu": schluessel not in set(gesehen),
                        "text": f"{k['name']} {ART_TEXT[r['art']]} {s:g}: aktuell {wert_txt}"})
    return aus
