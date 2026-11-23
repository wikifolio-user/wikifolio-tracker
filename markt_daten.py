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
    # Volatilitaetsindizes der CBOE ("Angstbarometer"); fuer den DAX liefert Yahoo keinen VDAX
    "^VIX": ("VIX", "VIX (S&P 500)", "NYSE"),
    "^VXN": ("VXN", "VXN (Nasdaq 100)", "NYSE"),
    "^VXD": ("VXD", "VXD (Dow Jones)", "NYSE"),
}
YAHOO_URL = "https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
CRYPTO_URL = "https://api.alternative.me/fng/"
CMC_URL = "https://pro-api.coinmarketcap.com/public-api/v3/fear-and-greed/latest"        # oeffentlich, ohne Schluessel
CMC_VERLAUF_URL = "https://api.coinmarketcap.com/data-api/v3/fear-greed/chart"
# Teilindikatoren des CNN Fear & Greed Index (Schluessel in der CNN-Antwort -> Anzeigename)
CNN_TEILE = {"market_momentum_sp500": "Marktmomentum (S&P 500 vs. 125-Tage-Linie)",
             "stock_price_strength": "Kursstärke (52-Wochen-Hochs vs. -Tiefs)",
             "stock_price_breadth": "Marktbreite (Volumen steigender vs. fallender Aktien)",
             "put_call_options": "Put/Call-Verhältnis",
             "market_volatility_vix": "Volatilität (VIX)",
             "safe_haven_demand": "Nachfrage nach sicheren Häfen (Aktien vs. Anleihen)",
             "junk_bond_demand": "Nachfrage nach Hochzinsanleihen"}
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


# ---------------------------------------------------------------------------------------------------- Intraday
PFAD_INTRADAY = "state/markt/opening_intraday.json"
INTRADAY_INDIZES = ("^NDX", "^GDAXI", "^GSPC", "^DJI")


def intraday_abrufen(symbol, get, intervall="5m", spanne="5d"):
    """Intraday-Kerzen des Cash-Index (nur regulaere Handelszeit, Instrumenttyp INDEX) -> intraday_parsen-Ergebnis
    oder None. Yahoo liefert 1m fuer ca. 7 Tage, 5m fuer ca. 60 Tage."""
    import opening_gaps as OG
    boerse = INDEX_OHLC[symbol][2]
    b = BK.BOERSEN[boerse]
    for host in ("query1", "query2"):
        try:
            r = get(YAHOO_URL.format(host=host, symbol=symbol), headers=HEADERS, timeout=20,
                    params={"interval": intervall, "range": spanne, "includePrePost": "false"})
            if r.status_code != 200:
                continue
            e = OG.intraday_parsen(r.json(), b["tz"], b["auf"], b["zu"])
        except Exception:
            continue
        if e and e["tage"]:
            return e
    return None


def intraday_tage(e, kerzen, boerse, jetzt):
    """Intraday-Abruf eines Index + Tageskerzen -> {datum: opening_gaps.intraday_auswerten(...)} je Handelstag.
    Vortagesschluss aus den offiziellen Tageskerzen (letzte Kerze VOR dem Tag); ohne ihn keine Auswertung."""
    import opening_gaps as OG
    tz = BK.BOERSEN[boerse]["tz"]
    schluesse = [(k[0], k[4]) for k in (kerzen or [])]
    aus = {}
    for d, bars in sorted((e or {}).get("tage", {}).items()):
        vor = [c for dd, c in schluesse if dd < d]
        if not vor:
            continue
        aus[d] = OG.intraday_auswerten(bars, vor[-1], tz, e.get("intervall") or "", e.get("verzoegert_min"),
                                       BK.kerze_vollstaendig(boerse, datetime.date.fromisoformat(d), jetzt))
    return aus


def neue_intraday(alt, je_symbol, ohlc, stand, jetzt):
    """Gespeicherte Opening-Gap-Zeiten fortschreiben. je_symbol: {yahoo_symbol: intraday_abrufen-Ergebnis}.
    -> neue Datei oder None, wenn sich nichts geaendert hat."""
    import opening_gaps as OG
    alt_i = ((alt or {}).get("indizes") or {}) if isinstance(alt, dict) else {}
    idx = ((ohlc or {}).get("indizes") or {}) if isinstance(ohlc, dict) else {}
    neu_i = {k: dict(v) for k, v in alt_i.items()}
    for sym, e in (je_symbol or {}).items():
        kurz, _, boerse = INDEX_OHLC[sym]
        tage = intraday_tage(e, (idx.get(sym) or {}).get("kerzen"), boerse, jetzt)
        bisher = (alt_i.get(kurz) or {}).get("tage") or {}
        neu_i[kurz] = {"tage": OG.intraday_zusammenfuehren(bisher, tage), "symbol": sym, "boerse": boerse,
                       "abruf": jetzt.isoformat(timespec="seconds")}
    if all((neu_i.get(k) or {}).get("tage") == (alt_i.get(k) or {}).get("tage") for k in set(neu_i) | set(alt_i)):
        return None
    return {"stand": stand, "indizes": neu_i}


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
    teile = {}
    for k in CNN_TEILE:
        t = antwort.get(k) if isinstance(antwort.get(k), dict) else {}
        w = _wert(t.get("score"))
        if w is not None:
            teile[k] = {"wert": w, "kategorie": str(t.get("rating") or "")}
    return {"wert": wert, "kategorie": str(fg.get("rating") or ""), "zeit": str(fg.get("timestamp") or ""),
            "teile": teile,
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


CNN_START_LANG = "2020-07-15"      # moeglichst lange Historie (Zeitraeume 3/5 Jahre, Max)


def _abruf(get, url, params, parser):
    try:
        r = get(url, params=params, headers=HEADERS, timeout=25)
        return parser(r.json()) if r.status_code == 200 else None
    except Exception:
        return None


def cmc_parsen(latest, chart=None):
    """CoinMarketCap Crypto Fear & Greed (oeffentlicher Endpunkt) + Verlauf -> Eintrag wie crypto_parsen oder None."""
    try:
        d = latest["data"]
        if str((latest.get("status") or {}).get("error_code") or "0") != "0":
            return None
    except (KeyError, TypeError, AttributeError):
        return None
    wert = _wert(d.get("value"))
    if wert is None:
        return None
    punkte = {}
    for p in ((((chart or {}).get("data") or {}).get("dataList")) or []) if isinstance(chart, dict) else []:
        try:
            t = datetime.datetime.fromtimestamp(int(p["timestamp"]), datetime.timezone.utc).date().isoformat()
        except (KeyError, TypeError, ValueError, OSError):
            continue
        v = _wert(p.get("score"))
        if v is not None:
            punkte[t] = v
    verlauf = [[t, punkte[t]] for t in sorted(punkte)]
    heute = str(d.get("update_time") or "")[:10]
    if heute and (not verlauf or verlauf[-1][0] < heute):
        verlauf.append([heute, wert])
    vor = [w for t, w in verlauf if t < heute] if heute else []
    return {"wert": wert, "kategorie": str(d.get("value_classification") or ""), "zeit": str(d.get("update_time") or ""),
            "vortag": vor[-1] if vor else None, "vorwoche": None, "verlauf": verlauf, "quelle": "CoinMarketCap"}


def sentiment_abrufen(get, jetzt):
    """-> {"cnn": eintrag|None, "crypto": eintrag|None}. Erst die lange Historie; liefert die Quelle sie nicht,
    ersatzweise die letzten 400 Tage (dann fehlt nur die lange Historie, der aktuelle Wert bleibt aktuell)."""
    kurz = (jetzt.date() - datetime.timedelta(days=400)).isoformat()
    cnn = (_abruf(get, CNN_URL.format(start=CNN_START_LANG), None, cnn_parsen)
           or _abruf(get, CNN_URL.format(start=kurz), None, cnn_parsen))
    crypto = (_abruf(get, CRYPTO_URL, {"limit": 0, "format": "json"}, crypto_parsen)        # 0 = alle seit 2018
              or _abruf(get, CRYPTO_URL, {"limit": 400, "format": "json"}, crypto_parsen))
    cmc = None
    try:
        r = get(CMC_URL, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            chart = None
            try:
                c = get(CMC_VERLAUF_URL, params={"start": 1, "end": int(jetzt.timestamp())}, headers=HEADERS, timeout=25)
                chart = c.json() if c.status_code == 200 else None
            except Exception:
                chart = None
            cmc = cmc_parsen(r.json(), chart)
    except Exception:
        cmc = None
    return {"cnn": cnn, "crypto": crypto, "cmc": cmc}


def neue_sentiment(alt, geladen, stand):
    """Erfolgreiche Quellen ersetzen ihren Eintrag (mit Zeit des Abrufs "ok"), fehlgeschlagene behalten den alten."""
    q = dict((((alt or {}).get("quellen")) or {}) if isinstance(alt, dict) else {})
    for name, e in geladen.items():
        if e:
            q[name] = dict(e, ok=stand)
    return {"stand": stand, "quellen": q}
