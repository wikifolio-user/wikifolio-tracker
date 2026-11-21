"""Gemeinsame Marktdaten fuer Fear & Greed Monitor, ETP-Hebelrechner und Gap Analyzer - Datenadapter je Quelle.

Der Kurs-Agent (kurs_agent.py) ruft sie bei jedem Lauf auf und legt die Ergebnisse ab; die App liest nur die Dateien:
  state/markt/ohlc.json       echte Tageskerzen der Cash-Indizes (Yahoo, Instrumenttyp INDEX - keine Futures, CFDs
                              oder ETFs), nur ABGESCHLOSSENE Kerzen, mit Datenpruefung (fehlende Tage, Doppelte)
  state/markt/sentiment.json  CNN Fear & Greed (US-Aktienmarkt) und Crypto Fear & Greed (Alternative.me), je mit
                              Verlauf; ein fehlgeschlagener Abruf behaelt den alten Stand (die App zeigt dann
                              "Veraltete Daten")
Keine erfundenen Werte: ungueltige Kerzen/Werte fallen weg und werden gezaehlt.
"""
import datetime

import boersenkalender as BK

PFAD_OHLC = "state/markt/ohlc.json"
PFAD_SENTIMENT = "state/markt/sentiment.json"
START = datetime.date(2015, 1, 1)            # Historie ab hier (Gap Analyzer, Backtests)

INDEX_OHLC = {        # Yahoo-Symbol -> (Kurzname, Anzeigename, Boerse)
    "^NDX": ("NDX", "Nasdaq 100", "NYSE"),
    "^GDAXI": ("DAX", "DAX 40", "XETRA"),
    "^GSPC": ("SPX", "S&P 500", "NYSE"),
    "^DJI": ("DJI", "Dow Jones", "NYSE"),
}
YAHOO_URL = "https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
CRYPTO_URL = "https://api.alternative.me/fng/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36", "Accept": "application/json"}


def _zahl(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


# ---------------------------------------------------------------------------------------------------- OHLC
def ohlc_parsen(antwort, symbol, jetzt):
    """Yahoo-Chart-Antwort (interval=1d) -> {"kerzen": [[iso, o, h, l, c]], "verworfen": n, "tz", "instrument"}
    oder None. Nur Instrumenttyp INDEX, nur abgeschlossene Kerzen, Datum in Boersenzeit, ohne Doppelte."""
    try:
        r = antwort["chart"]["result"][0]
        meta, ts, q = r["meta"], r["timestamp"], r["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if str(meta.get("instrumentType") or "").upper() != "INDEX":
        return None                                   # nie Futures/CFDs/ETFs als Indexkerzen verwenden
    boerse = INDEX_OHLC[symbol][2]
    tz = BK.BOERSEN[boerse]["tz"]
    kerzen, verworfen = {}, 0
    for i, t in enumerate(ts or []):
        try:
            o, h, l_, c = (_zahl(q[k][i]) for k in ("open", "high", "low", "close"))
            d = datetime.datetime.fromtimestamp(int(t), tz).date()
        except (KeyError, IndexError, TypeError, ValueError, OSError):
            verworfen += 1
            continue
        if None in (o, h, l_, c) or min(o, h, l_, c) <= 0 or l_ > min(o, c) + 1e-6 or h < max(o, c) - 1e-6:
            verworfen += 1                            # unvollstaendige oder widerspruechliche Kerze
            continue
        if not BK.kerze_vollstaendig(boerse, d, jetzt):
            continue                                  # laufender Handelstag: noch keine fertige Kerze
        kerzen[d.isoformat()] = [d.isoformat(), round(o, 4), round(h, 4), round(l_, 4), round(c, 4)]
    return {"kerzen": [kerzen[d] for d in sorted(kerzen)], "verworfen": verworfen, "tz": str(tz),
            "instrument": "INDEX", "boerse": boerse}


def pruefen(kerzen, boerse):
    """Datenpruefung: fehlende Handelstage laut Kalender (zwischen erster und letzter Kerze) und Kerzen an
    Nicht-Handelstagen. -> {"fehlende": [iso], "unerwartet": [iso]}"""
    if not kerzen:
        return {"fehlende": [], "unerwartet": []}
    da = {k[0] for k in kerzen}
    erste, letzte = (datetime.date.fromisoformat(kerzen[i][0]) for i in (0, -1))
    soll = {d.isoformat() for d in BK.handelstage_zwischen(boerse, erste, letzte)}
    return {"fehlende": sorted(soll - da), "unerwartet": sorted(da - soll)}


def ohlc_abrufen(symbol, get, jetzt):
    """Tageskerzen seit START. -> Eintrag fuer ohlc.json oder None."""
    p1 = int(datetime.datetime.combine(START, datetime.time(), datetime.timezone.utc).timestamp())
    p2 = int(jetzt.timestamp()) + 86400
    for host in ("query1", "query2"):
        try:
            r = get(YAHOO_URL.format(host=host, symbol=symbol), headers=HEADERS, timeout=30,
                    params={"period1": p1, "period2": p2, "interval": "1d", "events": "history"})
            if r.status_code != 200:
                continue
            e = ohlc_parsen(r.json(), symbol, jetzt)
        except Exception:
            continue
        if e and e["kerzen"]:
            kurz, name, boerse = INDEX_OHLC[symbol]
            e.update({"kurz": kurz, "name": name, "quelle": "Yahoo Finance (Cash-Index)", "symbol": symbol,
                      "pruefung": pruefen(e["kerzen"], boerse), "abruf": jetzt.isoformat(timespec="seconds")})
            return e
    return None


def neue_ohlc(alt, geladen, stand):
    """Neue ohlc.json oder None, wenn sich an den Kerzen nichts geaendert hat (spart Schreibvorgaenge).
    Fehlgeschlagene Indizes behalten ihren alten Eintrag. Korrigierte historische Kurse ueberschreiben die alten
    (der Gap Analyzer rechnet ohnehin jedes Mal aus den Kerzen neu)."""
    alt_i = ((alt or {}).get("indizes") or {}) if isinstance(alt, dict) else {}
    neu_i = dict(alt_i)
    geaendert = False
    for sym, e in geladen.items():
        if (alt_i.get(sym) or {}).get("kerzen") != e["kerzen"] or (alt_i.get(sym) or {}).get("pruefung") != e["pruefung"]:
            geaendert = True
        neu_i[sym] = e
    if not geaendert and alt_i:
        return None
    return {"stand": stand, "indizes": neu_i}


# ---------------------------------------------------------------------------------------------------- Sentiment
def _wert(x):
    v = _zahl(x)
    return round(v, 1) if v is not None and 0 <= v <= 100 else None


def cnn_parsen(antwort):
    """CNN-Grafikdaten -> {"wert", "kategorie", "zeit", "vortag", "vorwoche", "vormonat", "vorjahr",
    "verlauf": [[iso_datum, wert]]} oder None (ungueltig)."""
    try:
        fg = antwort["fear_and_greed"]
    except (KeyError, TypeError):
        return None
    wert = _wert(fg.get("score"))
    if wert is None:
        return None
    verlauf = {}
    for p in ((antwort.get("fear_and_greed_historical") or {}).get("data") or []):
        try:
            d = datetime.datetime.fromtimestamp(float(p["x"]) / 1000, datetime.timezone.utc).date().isoformat()
        except (KeyError, TypeError, ValueError, OSError):
            continue
        v = _wert(p.get("y"))
        if v is not None:
            verlauf[d] = v                             # je Tag der letzte Wert
    return {"wert": wert, "kategorie": str(fg.get("rating") or ""), "zeit": str(fg.get("timestamp") or ""),
            "vortag": _wert(fg.get("previous_close")), "vorwoche": _wert(fg.get("previous_1_week")),
            "vormonat": _wert(fg.get("previous_1_month")), "vorjahr": _wert(fg.get("previous_1_year")),
            "verlauf": [[d, verlauf[d]] for d in sorted(verlauf)], "quelle": "CNN Business"}


def crypto_parsen(antwort):
    """Alternative.me -> {"wert", "kategorie", "zeit", "vortag", "vorwoche", "verlauf"} oder None."""
    try:
        if (antwort.get("metadata") or {}).get("error"):
            return None
        daten = antwort["data"]
    except (KeyError, TypeError, AttributeError):
        return None
    punkte = {}
    for p in daten or []:
        try:
            t = datetime.datetime.fromtimestamp(int(p["timestamp"]), datetime.timezone.utc)
        except (KeyError, TypeError, ValueError, OSError):
            continue
        v = _wert(p.get("value"))
        if v is not None:
            punkte[t.date().isoformat()] = (v, str(p.get("value_classification") or ""), t)
    if not punkte:
        return None
    tage = sorted(punkte)
    v, kat, t = punkte[tage[-1]]

    def vor(n):
        d = (datetime.date.fromisoformat(tage[-1]) - datetime.timedelta(days=n)).isoformat()
        return punkte[d][0] if d in punkte else None
    return {"wert": v, "kategorie": kat, "zeit": t.isoformat(), "vortag": vor(1), "vorwoche": vor(7),
            "verlauf": [[d, punkte[d][0]] for d in tage], "quelle": "Alternative.me"}


def sentiment_abrufen(get, jetzt):
    """-> {"cnn": eintrag|None, "crypto": eintrag|None}"""
    aus = {}
    start = (jetzt.date() - datetime.timedelta(days=400)).isoformat()
    for name, url, params, parser in (("cnn", CNN_URL.format(start=start), None, cnn_parsen),
                                      ("crypto", CRYPTO_URL, {"limit": 400, "format": "json"}, crypto_parsen)):
        try:
            r = get(url, params=params, headers=HEADERS, timeout=20)
            aus[name] = parser(r.json()) if r.status_code == 200 else None
        except Exception:
            aus[name] = None
    return aus


def neue_sentiment(alt, geladen, stand):
    """Erfolgreiche Quellen ersetzen ihren Eintrag (mit Zeit des Abrufs "ok"), fehlgeschlagene behalten den alten."""
    q = dict((((alt or {}).get("quellen")) or {}) if isinstance(alt, dict) else {})
    for name, e in geladen.items():
        if e:
            q[name] = dict(e, ok=stand)
    return {"stand": stand, "quellen": q}
