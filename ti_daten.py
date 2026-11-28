"""Trading Intelligence - Datenbasis (ohne Streamlit). Etappe 1: Universum, Tageskerzen mit Volumen, Datenpruefung.

Universum
  1. Alle Wertpapiere, die im Dashboard hinterlegt sind (ISINs in den Dateien des Admins und aller Benutzer - dieselben
     Dateien, aus denen der Kurs-Agent seine Kurs-IDs sammelt, kurs_agent.DATEIEN, und die Suchtreffer
     state/kurse/suche.json). Wikifolios und Zertifikate haben keine Boersenhistorie mit Volumen: sie werden als
     "nicht analysierbar" gefuehrt, nicht mit duennen Daten bewertet.
  2. Die vier Cash-Indizes des Dashboards (S&P 500, Nasdaq 100, Dow Jones, DAX).
  3. ZUSATZ: eine kleine Standardliste fuer Kryptowaehrungen, Rohstoffe und Devisen (im Dashboard nicht hinterlegt);
     abschaltbar ueber ZUSATZ_AKTIV.
Kerzen: Yahoo Finance (oeffentliche Chart-Schnittstelle, wie markt_daten.py), Tageskerzen mit Volumen, um Splits und
Dividenden bereinigt (Faktor adjclose/close auf O/H/L/C). Nur ABGESCHLOSSENE Kerzen: die Kerze des laufenden
Handelstags faellt weg (Yahoo liefert sie schon waehrend des Handels - sonst entstuenden Signale, die sich bis
Handelsschluss wieder aendern = Repainting). Keine erfundenen Werte: ungueltige Kerzen fallen weg und werden gezaehlt.
Zuordnung ISIN -> Yahoo-Symbol ueber die Yahoo-Suche; bevorzugt werden Heimatboersen mit Volumen (siehe RANG).
"""
import datetime
import time

YAHOO_CHART = "https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_SUCHE = "https://query1.finance.yahoo.com/v1/finance/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36", "Accept": "application/json"}
START = datetime.date(2005, 1, 1)

INDIZES = [("^GSPC", "S&P 500"), ("^NDX", "Nasdaq 100"), ("^DJI", "Dow Jones"), ("^GDAXI", "DAX 40")]
ZUSATZ_AKTIV = True
ZUSATZ = [("BTC-USD", "Bitcoin", "krypto"), ("ETH-USD", "Ethereum", "krypto"), ("GC=F", "Gold (Future)", "rohstoff"),
          ("SI=F", "Silber (Future)", "rohstoff"), ("CL=F", "Rohöl WTI (Future)", "rohstoff"),
          ("EURUSD=X", "EUR/USD", "devisen"), ("USDJPY=X", "USD/JPY", "devisen")]
KLASSE = {"EQUITY": "aktie", "ETF": "etf", "MUTUALFUND": "etf", "INDEX": "index", "CRYPTOCURRENCY": "krypto",
          "CURRENCY": "devisen", "FUTURE": "rohstoff"}
# Boersen in Reihenfolge der Bevorzugung (liquide Heimat- bzw. Hauptboersen zuerst, Stuttgart/Fonds zuletzt)
RANG = ["NMS", "NYQ", "NGM", "NCM", "PCX", "ASE", "BTS", "GER", "LSE", "EBS", "AMS", "PAR", "MIL", "BRU", "MCE",
        "VIE", "CPH", "STO", "HEL", "OSL", "TOR", "JPX", "HKG", "IOB", "FRA", "STU", "MUN", "DUS", "HAM", "BER"]
NICHT_ANALYSIERBAR_PRAEFIX = ("DE000LS9",)            # Wikifolio-Zertifikate (Lang & Schwarz)
# Datenaktualitaet: hoechstens so viele Kalendertage seit der letzten abgeschlossenen Kerze
MAX_ALTER_TAGE = {"krypto": 2, "devisen": 4, "rohstoff": 4}
MAX_ALTER_STANDARD = 4                                   # Wochenende + ein Feiertag


# ---------------------------------------------------------------------------------------------------- Universum
def isins_in(daten, aus=None):
    """Alle ISINs (mit Namen und Kategorie) in einer verschachtelten JSON-Struktur -> {isin: {"name","kategorie"}}."""
    aus = {} if aus is None else aus
    if isinstance(daten, dict):
        isin = daten.get("isin")
        if isinstance(isin, str) and len(isin.strip()) == 12 and isin.strip()[:2].isalpha():
            i = isin.strip().upper()
            alt = aus.get(i) or {}
            aus[i] = {"name": alt.get("name") or str(daten.get("name") or daten.get("bezeichnung") or "").strip(),
                      "kategorie": alt.get("kategorie") or str(daten.get("kategorie") or "").strip()}
        for v in daten.values():
            isins_in(v, aus)
    elif isinstance(daten, list):
        for v in daten:
            isins_in(v, aus)
    return aus


def nicht_analysierbar(isin, kategorie=""):
    k = str(kategorie or "").lower()
    if isin.startswith(NICHT_ANALYSIERBAR_PRAEFIX) or k == "wikifolio":
        return "Wikifolio-Zertifikat – keine Börsenhistorie mit Volumen"
    if k in ("zertifikat", "knock-out", "optionsschein", "hebelprodukt"):
        return "Derivat – Kurs hängt am Emittenten, keine Börsenhistorie mit Volumen"
    return None


def symbol_waehlen(treffer):
    """Yahoo-Suchtreffer -> bester Treffer oder None. Aktien/ETFs/Indizes vor Fonds-Listings, liquide Boersen zuerst."""
    gut = [t for t in treffer or [] if t.get("symbol") and t.get("quoteType") in KLASSE]
    if not gut:
        return None

    def rang(t):
        b = t.get("exchange") or ""
        return (t.get("quoteType") == "MUTUALFUND", RANG.index(b) if b in RANG else len(RANG))
    return sorted(gut, key=rang)[0]


def yahoo_suchen(begriff, get):
    r = get(YAHOO_SUCHE, params={"q": begriff, "quotesCount": 10, "newsCount": 0}, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        raise IOError(f"Yahoo-Suche: HTTP {r.status_code}")
    return (r.json() or {}).get("quotes") or []


def universum(isins, get, cache=None, pause=0.2):
    """{isin: {...}} -> Liste der Werte [{"id","symbol","name","klasse","isin","quelle","grund"}].
    cache: {isin: {"symbol", "klasse"}} aus frueheren Laeufen (spart Suchen; symbol "" = nicht gefunden)."""
    cache = dict(cache or {})
    aus = []
    for isin, info in sorted(isins.items()):
        grund = nicht_analysierbar(isin, info.get("kategorie"))
        eintrag = {"id": isin, "isin": isin, "name": info.get("name") or isin, "symbol": None, "klasse": None,
                   "quelle": "dashboard", "grund": grund}
        if not grund:
            if isinstance(cache.get(isin), dict):
                sym, klasse = cache[isin].get("symbol") or "", cache[isin].get("klasse")
            else:
                try:
                    t = symbol_waehlen(yahoo_suchen(isin, get))
                except Exception as ex:                      # Netz/Rate-Limit: naechster Lauf versucht es erneut
                    eintrag["grund"] = f"Zuordnung fehlgeschlagen ({type(ex).__name__})"
                    aus.append(eintrag)
                    continue
                sym, klasse = (t["symbol"], KLASSE[t["quoteType"]]) if t else ("", None)
                cache[isin] = {"symbol": sym, "klasse": klasse}
                time.sleep(pause)
            if sym:
                eintrag.update(symbol=sym, klasse=klasse or "aktie")
            else:
                eintrag["grund"] = "Kein Yahoo-Symbol zur ISIN gefunden"
        aus.append(eintrag)
    for sym, name in INDIZES:
        aus.append({"id": sym, "isin": None, "name": name, "symbol": sym, "klasse": "index", "quelle": "index",
                    "grund": None})
    if ZUSATZ_AKTIV:
        for sym, name, klasse in ZUSATZ:
            aus.append({"id": sym, "isin": None, "name": name, "symbol": sym, "klasse": klasse, "quelle": "zusatz",
                        "grund": None})
    return aus, cache


# ---------------------------------------------------------------------------------------------------- Kerzen
def _zahl(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def kerzen_parsen(antwort, jetzt):
    """Yahoo-Chart-Antwort -> {"kerzen": [[iso, o, h, l, c, v]], "verworfen", "meta"} oder None.
    Bereinigt (adjclose/close), nur abgeschlossene Kerzen, ohne Doppelte."""
    try:
        r = antwort["chart"]["result"][0]
        meta, ts, q = r["meta"], r["timestamp"], r["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return None
    adj = ((r["indicators"].get("adjclose") or [{}])[0] or {}).get("adjclose")
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
    except Exception:
        tz = datetime.timezone.utc
    typ = str(meta.get("instrumentType") or "")
    ende = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    heute = jetzt.astimezone(tz).date()
    kerzen, verworfen = {}, 0
    for i, t in enumerate(ts or []):
        try:
            o, h, lo, c = (_zahl(q[k][i]) for k in ("open", "high", "low", "close"))
            v = _zahl((q.get("volume") or [None] * len(ts))[i]) or 0.0
            d = datetime.datetime.fromtimestamp(int(t), tz).date()
        except (KeyError, IndexError, TypeError, ValueError, OSError):
            verworfen += 1
            continue
        if None in (o, h, lo, c) or min(o, h, lo, c) <= 0 or lo > min(o, c) * (1 + 1e-6) or h < max(o, c) * (1 - 1e-6):
            verworfen += 1
            continue
        # laufender Handelstag: noch keine fertige Kerze (Krypto: Tageskerze endet um Mitternacht UTC)
        if d >= heute and (typ == "CRYPTOCURRENCY" or not ende or jetzt.timestamp() < float(ende)):
            continue
        f = 1.0
        if adj and i < len(adj) and _zahl(adj[i]):
            f = _zahl(adj[i]) / c
        kerzen[d.isoformat()] = [d.isoformat(), o * f, h * f, lo * f, c * f, max(0.0, v)]
    return {"kerzen": [kerzen[k] for k in sorted(kerzen)], "verworfen": verworfen,
            "meta": {"waehrung": meta.get("currency"), "boerse": meta.get("exchangeName"), "typ": typ,
                     "tz": meta.get("exchangeTimezoneName"), "letzter_kurs": _zahl(meta.get("regularMarketPrice")),
                     "kurszeit": meta.get("regularMarketTime")}}


def kerzen_abrufen(symbol, get, jetzt, ab=None, versuche=2, pause=1.5):
    """Tageskerzen seit `ab` (Standard START). Wiederholt bei Fehlern, wechselt den Yahoo-Host. -> dict oder None."""
    p1 = int(datetime.datetime.combine(ab or START, datetime.time(), datetime.timezone.utc).timestamp())
    p2 = int(jetzt.timestamp()) + 86400
    letzter = None
    for versuch in range(versuche):
        for host in ("query1", "query2"):
            try:
                r = get(YAHOO_CHART.format(host=host, symbol=symbol), headers=HEADERS, timeout=30,
                        params={"period1": p1, "period2": p2, "interval": "1d", "events": "div,split"})
                if r.status_code == 429:
                    letzter = "Rate-Limit (HTTP 429)"
                    continue
                if r.status_code != 200:
                    letzter = f"HTTP {r.status_code}"
                    continue
                e = kerzen_parsen(r.json(), jetzt)
            except Exception as ex:
                letzter = type(ex).__name__
                continue
            if e and e["kerzen"]:
                e.update(symbol=symbol, abruf=jetzt.isoformat(timespec="seconds"))
                return e
            letzter = "keine Kerzen"
        time.sleep(pause * (versuch + 1))
    return {"symbol": symbol, "kerzen": [], "fehler": letzter or "unbekannt"}


def pruefen(e, klasse, jetzt):
    """Datenpruefung -> {"ok", "alter_tage", "luecken", "volumen_anteil", "anzahl", "gruende": [..]}.
    ok=False: keine neuen Einstiegssignale aus diesen Daten."""
    k = e.get("kerzen") or []
    gruende = []
    if len(k) < 260:
        gruende.append(f"nur {len(k)} Tageskerzen (mindestens 260 nötig)")
    alter = None
    if k:
        letzte = datetime.date.fromisoformat(k[-1][0])
        alter = (jetzt.date() - letzte).days
        grenze = MAX_ALTER_TAGE.get(klasse, MAX_ALTER_STANDARD)
        if alter > grenze:
            gruende.append(f"letzte Kerze {alter} Tage alt (höchstens {grenze})")
    luecken = 0
    for a, b in zip(k, k[1:]):
        tage = (datetime.date.fromisoformat(b[0]) - datetime.date.fromisoformat(a[0])).days
        if tage > (4 if klasse == "krypto" else 7):
            luecken += 1
    if luecken > 5:
        gruende.append(f"{luecken} größere Datenlücken")
    vol = sum(1 for x in k[-250:] if x[5] > 0) / max(1, len(k[-250:]))
    if e.get("fehler"):
        gruende.append(f"Abruf fehlgeschlagen: {e['fehler']}")
    return {"ok": not gruende, "alter_tage": alter, "luecken": luecken, "volumen_anteil": vol, "anzahl": len(k),
            "gruende": gruende}


def liquiditaet(kerzen, klasse, min_umsatz=1_000_000):
    """Median-Tagesumsatz (Kurs x Volumen, Waehrung des Listings) der letzten 60 Kerzen -> (ok, umsatz).
    Indizes, Devisen: ohne Volumen, gelten als liquide (handelbar ueber liquide Derivate/ETFs)."""
    if klasse in ("index", "devisen"):
        return True, None
    u = sorted(x[4] * x[5] for x in kerzen[-60:])
    if not u:
        return False, 0.0
    m = u[len(u) // 2]
    return m >= min_umsatz, m
