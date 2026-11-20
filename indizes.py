"""Echte Indexstaende fuer den Kurs-Ticker der Startseite (DAX in Punkten statt Kurs eines DAX-ETFs).

Der Kurs-Agent (kurs_agent.py) holt sie mit jedem Lauf bei Yahoo Finance (oeffentlicher Chart-Endpunkt, nur
requests) und legt sie ab:
  state/kurse/indizes.json   {"stand": iso, "werte": {symbol: {"k": kurs, "p": vortag, "t": iso}}}
Die App liest nur diese Datei. Ein fehlgeschlagener Abruf behaelt den alten Eintrag.
"""
import datetime

PFAD = "state/kurse/indizes.json"

# (Yahoo-Symbol, Anzeigename, Einheit) - Einheit: "" = Punkte, "€", "$", "fx" = Wechselkurs (4 Nachkommastellen)
INDIZES = [
    ("^GDAXI", "DAX", ""),
    ("^MDAXI", "MDAX", ""),
    ("^STOXX50E", "Euro Stoxx 50", ""),
    ("^GSPC", "S&P 500", ""),
    ("^NDX", "Nasdaq 100", ""),
    ("^DJI", "Dow Jones", ""),
    ("^N225", "Nikkei 225", ""),
    ("GC=F", "Gold (Unze)", "$"),
    ("BTC-EUR", "Bitcoin", "€"),
    ("EURUSD=X", "EUR/USD", "fx"),
]

URL = "https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"}


def auswerten(antwort):
    """Yahoo-Chart-Antwort -> (kurs, vortag) oder None."""
    try:
        meta = antwort["chart"]["result"][0]["meta"]
        kurs = float(meta["regularMarketPrice"])
        vor = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return (kurs, vor) if kurs > 0 and vor > 0 else None


def markt_zeit(antwort):
    """Zeitpunkt des Kurses laut Boerse (regularMarketTime) als ISO-Text (UTC) oder None."""
    try:
        t = int(antwort["chart"]["result"][0]["meta"]["regularMarketTime"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


def abrufen(symbol, get, zeit):
    """Ein Index -> {"k", "p", "t"} oder None. get(url, params, headers, timeout) wie requests.get."""
    for host in ("query1", "query2"):
        try:
            r = get(URL.format(host=host, symbol=symbol), params={"range": "1d", "interval": "1d"},
                    headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            antwort = r.json()
            w = auswerten(antwort)
            if w:
                aus = {"k": w[0], "p": w[1], "t": zeit}
                m = markt_zeit(antwort)
                if m:
                    aus["m"] = m                      # Kurszeit der Boerse (Abrufzeit "t" kann spaeter sein)
                return aus
        except Exception:
            continue
    return None


def neue_datei(alt, geladen, stand):
    """Frische Werte, fuer fehlgeschlagene der alte Eintrag (nur noch gelistete Symbole)."""
    werte = dict(((alt or {}).get("werte") or {}) if isinstance(alt, dict) else {})
    werte.update(geladen)
    symbole = {s for s, _, _ in INDIZES}
    return {"stand": stand, "werte": {s: w for s, w in werte.items() if s in symbole}}


def ticker_eintraege(daten, max_alter_tage=7, jetzt=None):
    """indizes.json -> [(name, kurs, pct, einheit)] in der Reihenfolge von INDIZES; zu alte Werte entfallen."""
    werte = (daten or {}).get("werte") if isinstance(daten, dict) else None
    if not isinstance(werte, dict):
        return []
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    aus = []
    for symbol, name, einheit in INDIZES:
        w = werte.get(symbol)
        try:
            kurs, vor = float(w["k"]), float(w["p"])
            t = datetime.datetime.fromisoformat(w["t"])
        except (KeyError, TypeError, ValueError):
            continue
        if kurs <= 0 or vor <= 0 or (t.tzinfo and jetzt - t > datetime.timedelta(days=max_alter_tage)):
            continue
        aus.append((name, kurs, (kurs / vor - 1) * 100, einheit))
    return aus
