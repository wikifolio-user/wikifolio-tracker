"""Pyramidenmanager Etappe 4 - Aktien: Tageskerzen einzelner Aktien, Aktien-Trendscanner und die Grundlage fuer
Aktien-Pyramiden. Reine Logik ohne Streamlit (der Abruf bekommt get() von aussen).

Fuer Aktien gibt es weder Fear & Greed noch eine Gap-Analyse im Dashboard - dort zaehlen der technische Trend
(derselbe Trend-Score wie bei den Indizes), die vorhandene Aktienbewertung (Top-500-Score, Investoren-Note) und das
Risiko. Der kombinierte Wert einer Aktien-Pyramide besteht deshalb nur aus dem Trend (Gewichte 100/0/0, F&G aus).
Quelle der Kerzen: Yahoo Finance Chart-API (interval 1d), nur abgeschlossene Handelstage."""
import datetime
import statistics
from zoneinfo import ZoneInfo

import pyramide as P

YAHOO_URL = "https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
JAHRE = 3
ARTEN = {"EQUITY", "ETF"}
AKTIEN_EINSTELLUNGEN = P.AKTIEN_STANDARD
QUELLE = "Yahoo Finance, Tageskerzen der Aktie (beim Öffnen geladen, 6 Stunden zwischengespeichert)"
MAX_ALTER = 3                    # Handelstage (Mo-Fr) bis „veraltet"


class AbrufFehler(Exception):
    pass


def _zahl(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def kerzen_parsen(antwort, jetzt):
    """Yahoo-Chart-Antwort einer Aktie -> {"kerzen", "waehrung", "boerse", "name", "verworfen"}.
    Nur Aktien/ETFs; die Kerze des laufenden Handelstags (vor Handelsschluss) wird weggelassen."""
    try:
        r = antwort["chart"]["result"][0]
        meta, ts, q = r["meta"], r.get("timestamp") or [], r["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        raise AbrufFehler("Unerwartete Antwort von Yahoo Finance.") from None
    art = str(meta.get("instrumentType") or "").upper()
    if art not in ARTEN:
        raise AbrufFehler(f"Kein Aktienwert (Yahoo meldet „{art or 'unbekannt'}“).")
    try:
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    ende = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    heute = jetzt.astimezone(tz).date()
    offen = bool(ende) and jetzt.timestamp() < int(ende)
    kerzen, verworfen = {}, 0
    for i, t in enumerate(ts):
        try:
            o, h, lo, c = (_zahl(q[k][i]) for k in ("open", "high", "low", "close"))
            d = datetime.datetime.fromtimestamp(int(t), tz).date()
        except (KeyError, IndexError, TypeError, ValueError, OSError):
            verworfen += 1
            continue
        if None in (o, h, lo, c) or min(o, h, lo, c) <= 0 or lo > min(o, c) * 1.0001 or h < max(o, c) * 0.9999:
            verworfen += 1
            continue
        if d > heute or (d == heute and offen):
            continue                                      # laufender Handelstag: noch keine fertige Kerze
        kerzen[d.isoformat()] = [d.isoformat(), round(o, 4), round(h, 4), round(lo, 4), round(c, 4)]
    return {"kerzen": [kerzen[d] for d in sorted(kerzen)], "waehrung": meta.get("currency") or "",
            "boerse": meta.get("exchangeName") or "", "name": meta.get("longName") or meta.get("shortName") or "",
            "verworfen": verworfen}


def kerzen_laden(ticker, get, jetzt, headers=None, jahre=JAHRE):
    """Tageskerzen der letzten `jahre` Jahre. Wirft AbrufFehler mit verstaendlichem Text."""
    t = str(ticker or "").strip().upper()
    if not t or len(t) > 20 or any(ch.isspace() for ch in t):
        raise AbrufFehler("Ungültiges Börsenkürzel.")
    p1 = int((jetzt - datetime.timedelta(days=int(365.25 * jahre) + 10)).timestamp())
    p2 = int(jetzt.timestamp()) + 86400
    letzter = None
    for host in ("query1", "query2"):
        try:
            r = get(YAHOO_URL.format(host=host, symbol=t), headers=headers or {}, timeout=20,
                    params={"period1": p1, "period2": p2, "interval": "1d", "events": "history"})
        except Exception as ex:
            letzter = f"Keine Verbindung ({type(ex).__name__})"
            continue
        if r.status_code == 404:
            raise AbrufFehler(f"Börsenkürzel „{t}“ bei Yahoo Finance nicht gefunden.")
        if r.status_code != 200:
            letzter = f"Yahoo Finance antwortet mit {r.status_code}"
            continue
        try:
            return kerzen_parsen(r.json(), jetzt)
        except ValueError:
            letzter = "Antwort nicht lesbar"
    raise AbrufFehler((letzter or "Abruf fehlgeschlagen") + " – bitte später erneut versuchen.")


def handelstage_alt(letzte_iso, jetzt):
    """Abgeschlossene Wochentage (Mo-Fr) nach der letzten Kerze bis gestern - Feiertage zaehlen mit (vorsichtig)."""
    try:
        d = datetime.date.fromisoformat(str(letzte_iso)[:10])
    except ValueError:
        return None
    gestern = jetzt.date() - datetime.timedelta(days=1)
    n = 0
    while d < gestern:
        d += datetime.timedelta(days=1)
        n += d.weekday() < 5
    return n


def analyse(ticker, name, daten, jetzt, cfg=None):
    """Wie pyramide_daten.index_analyse fuer einen Index - ohne Gap- und Fear-&-Greed-Daten."""
    cfg = cfg or P.einstellungen(AKTIEN_EINSTELLUNGEN)
    kerzen = (daten or {}).get("kerzen") or []
    letzte = kerzen[-1][0] if kerzen else None
    alter = handelstage_alt(letzte, jetzt) if letzte else None
    status = "fehlt" if not kerzen else ("veraltet" if alter is not None and alter > MAX_ALTER else "aktuell")
    trend = P.trend_score(kerzen) if kerzen else None
    return {"code": ticker, "name": name or (daten or {}).get("name") or ticker, "yahoo": ticker, "kerzen": kerzen,
            "kurs": kerzen[-1][4] if kerzen else None, "letzte_kerze": letzte, "alter_handelstage": alter,
            "status": status, "quelle": QUELLE, "trend": trend, "atr": P.atr(kerzen, cfg["atr_tage"]) if kerzen else None,
            "waehrung": (daten or {}).get("waehrung") or "", "probleme": [], "fehlende": [],
            "gap_daten": {"status": "fehlt"}, "fg_index": None, "us_umfeld": None, "art": "aktie"}


def scanner_zeile(a, cfg=None, bewertung=None, investoren=None, quelle=""):
    """Eine Zeile des Aktien-Trendscanners. bewertung: (eintrag, scoring-Ergebnis) oder None;
    investoren: Kurzform des Legenden-Screeners oder None."""
    cfg = cfg or P.einstellungen(AKTIEN_EINSTELLUNGEN)
    trend = a["trend"] if a["status"] == "aktuell" else None
    sig, gruende = P.einstiegssignal(trend, cfg)
    if a["status"] != "aktuell":
        gruende = [f"Kerzen {a['status']} (letzte {a['letzte_kerze'] or '–'})."] + gruende
    w = (a["trend"] or {}).get("werte") or {}
    b = (bewertung or (None, None))[1] or {}
    return {"ticker": a["code"], "name": a["name"], "quelle": quelle, "kurs": a["kurs"], "waehrung": a["waehrung"],
            "status": a["status"], "letzte_kerze": a["letzte_kerze"],
            "trend": (a["trend"] or {}).get("score"), "signal": sig, "gruende": gruende,
            "atr_pct": a["atr"] / a["kurs"] * 100 if a["atr"] and a["kurs"] else None,
            "abstand_hoch_pct": w.get("abstand_hoch_pct"), "rendite_12m": w.get("rendite_12m"),
            "rendite_3m": w.get("rendite_3m"),
            "bewertung": b.get("gesamt"), "fazit": b.get("fazit"),
            "investoren_note": (investoren or {}).get("note"),
            "investoren_kaufen": f"{investoren.get('kaufen', 0)}/{investoren.get('inv', 0)}" if investoren else None}


def sortieren(zeilen):
    """Signal zuerst, dann Trend-Score absteigend; fehlende Werte ans Ende."""
    return sorted(zeilen, key=lambda z: (not z["signal"], -(z["trend"] if z["trend"] is not None else -1)))


def liste_zusammenstellen(depot, eigene, zuordnen):
    """Depotwerte (zugeordnet ueber zuordnen(position) -> (ticker, name) oder None) + eigene Liste, ohne Doppelte.
    -> ([{"ticker", "name", "quelle"}], [nicht zuordenbare Depotnamen])"""
    aus, ohne, gesehen = [], [], set()
    for p in depot or []:
        z = zuordnen(p)
        if not z:
            ohne.append(p.get("name") or p.get("wkn") or p.get("isin") or "?")
            continue
        t = z[0].upper()
        if t not in gesehen:
            gesehen.add(t)
            aus.append({"ticker": t, "name": z[1] or p.get("name") or t, "quelle": "Depot"})
    for e in eigene or []:
        t = str(e.get("ticker") or "").upper()
        if t and t not in gesehen:
            gesehen.add(t)
            aus.append({"ticker": t, "name": e.get("name") or t, "quelle": "eigene Liste"})
    return aus, ohne


def zusammenfassung(zeilen):
    trends = [z["trend"] for z in zeilen if z["trend"] is not None]
    return {"anzahl": len(zeilen), "signale": sum(1 for z in zeilen if z["signal"]),
            "median_trend": statistics.median(trends) if trends else None,
            "fehlt": sum(1 for z in zeilen if z["status"] != "aktuell")}
