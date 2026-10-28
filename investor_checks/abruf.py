"""Datenabruf ueber yfinance (ohne Streamlit) - gemeinsam fuer die App (mit st.cache_data) und den
woechentlichen Investoren-Agenten (investoren_agent.py), damit beide exakt dieselben Fakten bilden."""
import logging
from concurrent.futures import ThreadPoolExecutor

from . import daten as DT
from . import greenblatt as GB

ABRUFE = ("info", "gj", "bilanz", "cashflow", "q_gj", "dividenden", "insider", "revisionen")


def _yf():
    import yfinance as yf          # erst bei Bedarf laden (spart Startzeit der App)
    return yf


def roh_laden(symbol, parallel=8, timeout=20):
    """Fundamentaldaten: info, Jahres-GuV/Bilanz/Cashflow, Quartals-GuV, Dividenden, Insider, Revisionen.
    Teilausfaelle (Yahoo drosselt) landen in "fehler" statt eine Ausnahme zu werfen."""
    t = _yf().Ticker(symbol)
    abrufe = {"info": lambda: t.info, "gj": lambda: t.income_stmt, "bilanz": lambda: t.balance_sheet,
              "cashflow": lambda: t.cashflow, "q_gj": lambda: t.quarterly_income_stmt,
              "dividenden": lambda: t.dividends, "insider": lambda: t.insider_transactions,
              "revisionen": lambda: t.eps_revisions}
    aus, fehler = {}, []
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        laeufe = {k: ex.submit(fn) for k, fn in abrufe.items()}
        for k, lauf in laeufe.items():
            try:
                aus[k] = lauf.result(timeout=timeout)
            except Exception as e:
                logging.warning("yfinance %s %s: %s", symbol, k, type(e).__name__)
                aus[k] = None
                fehler.append(k)
    aus["fehler"] = fehler
    return aus


def kurse_laden(symbol, periode="5y"):
    try:
        return _yf().Ticker(symbol).history(period=periode, auto_adjust=True)
    except Exception as e:
        logging.warning("yfinance Kurse %s: %s", symbol, type(e).__name__)
        return None


def vergleich(universum):
    """Top-500-Vergleichsdaten: Magic-Formula-Raenge und Rang nach Boersenwert im Sektor."""
    sektoren = {}
    for e in universum:
        mcap = (e.get("info") or {}).get("mcap")
        if e["art"] == "aktie" and e.get("sektor") and mcap:
            sektoren.setdefault(e["sektor"], []).append((float(mcap), e["id"]))
    rang = {}
    for liste in sektoren.values():
        liste.sort(reverse=True)
        for i, (_, eid) in enumerate(liste, 1):
            rang[eid] = (i, len(liste))
    return {"greenblatt": GB.raenge(universum), "sektor_rang": rang}


def leitindex_fuer(roh):
    info = (roh or {}).get("info") or {}
    return DT.leitindex({"land": info.get("country") or "", "kurs_waehrung": info.get("currency") or ""})


def fakten(roh, kurse, index_hist, index_name, fx, agent):
    roh = roh or {}
    f = DT.fakten_aus_yfinance(roh.get("info") or {}, roh.get("gj"), roh.get("bilanz"), roh.get("cashflow"),
                               q_gj=roh.get("q_gj"), hist=kurse, dividenden=roh.get("dividenden"), fx=fx,
                               agent=agent, insider=roh.get("insider"), eps_revisionen=roh.get("revisionen"),
                               index_hist=index_hist, index_name=index_name)
    if not f["sektor"] and not f["branche"]:
        f["branche"] = (agent or {}).get("sektor") or ""
    return f


def kontext(agent, verteilungen, vgl, fue_median=None):
    return {"agent": agent, "verteilungen": verteilungen, "greenblatt": vgl["greenblatt"],
            "sektor_rang": vgl["sektor_rang"].get(agent["id"]), "fue_median": fue_median or {}}
