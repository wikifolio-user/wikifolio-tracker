"""Qualitative Analyse vorberechnen (woechentlich, im Workflow "Investoren-Checks vorberechnen").

Je Aktie (groesster Boersenwert zuerst, nur neu, wenn ein neuer 10-K vorliegt oder die letzte Analyse aelter als
SEC["neu_nach_tagen"] ist):
  - US-Firmen: juengster 10-K von SEC EDGAR -> Business, Competition, Risk Factors, Grosskunden
  - alle anderen: Unternehmensbeschreibung von Yahoo Finance (Kurzbeschreibung, in der App gekennzeichnet)
  - Wikidata: Gruendungsjahr, Produkte, Tochterfirmen
  - Textanalyse (Burggraben-Woerter je 10.000 Woerter, Risiko-Woerter)
  - KI-Einschaetzung, falls GEMINI_API_KEY oder GROQ_API_KEY als Secret hinterlegt ist
Ergebnisse: state/qualitativ/werte/<SYMBOL>.json (je Aktie, die App laedt nur die gewaehlte),
state/qualitativ/index.json (Stand je Aktie + Textdichte) und state/qualitativ/meta.json (Sektor-Mediane).
"""
import datetime
import os
import re
import sys
import time

import investor_config as C
import ki_anbieter as KI
import investoren_agent as IA
import quellen_qualitativ as QQ
import top50_agent as T
from investor_checks import qualitativ as Q

log = T.log
STATE_WERT = "state/qualitativ/werte/{}.json"
STATE_INDEX = "state/qualitativ/index.json"
STATE_META = "state/qualitativ/meta.json"
MAX_KURZ = int(os.environ.get("QUALITATIV_MAX_KURZ", "300"))      # Yahoo-Kurzbeschreibungen je Lauf
ZEITBUDGET_SEK = float(os.environ.get("QUALITATIV_ZEITBUDGET_MIN", "90")) * 60
_uhr = time.monotonic


def datei(symbol):
    return STATE_WERT.format(re.sub(r"[^A-Za-z0-9.\-]", "_", symbol))


def faellig(eintrag, heute, acc=None):
    """Neu analysieren, wenn noch nichts da ist, ein neuer 10-K vorliegt oder die Analyse zu alt ist."""
    if not eintrag:
        return True
    if acc and eintrag.get("acc") != acc:
        return True
    grenze = (heute - datetime.timedelta(days=C.SEC["neu_nach_tagen"])).isoformat()
    return (eintrag.get("st") or "") < grenze


def auszuege(ab, max_woerter=None):
    """Kurze Auszuege fuer Prompt und Anzeige (statt des ganzen 10-K)."""
    def kurz(t, n):
        w = (t or "").split()
        return " ".join(w[:n])
    return {"business": kurz(ab.get("business"), 2500), "competition": kurz(ab.get("competition"), 900),
            "risiken": kurz(ab.get("risiken"), 2500)}


def analyse_text(text, quelle):
    """Textanalyse eines Quelltexts -> {quelle, woerter, dichte, risiko}."""
    return {"quelle": quelle, "woerter": Q.wortzahl(text),
            "dichte": Q.moat_dichte(text, min_woerter=200 if quelle == "10-K" else 60),
            "risiko": Q.risiko_treffer(text)}


def kennzahlen_fuer_prompt(e):
    k, i = e.get("k") or {}, e.get("info") or {}
    paare = [("Umsatzwachstum p. a.", k.get("g_ums"), "%"), ("Operative Marge", k.get("om"), "%"),
             ("Kapitalrendite (ROIC)", k.get("roic"), "%"), ("Free-Cashflow-Marge", k.get("fm"), "%"),
             ("Nettoschulden/EBITDA", k.get("nde"), "x"), ("KGV (erwartet)", k.get("fkgv"), "x")]
    aus = {n: f"{v:.1f}{e_}".replace(".", ",") for n, v, e_ in paare if isinstance(v, (int, float))}
    if i.get("mcap"):
        aus["Börsenwert"] = f"{float(i['mcap']):.0f} Mrd."
    return aus


def main():
    start, heute = _uhr(), datetime.date.today()
    ua = QQ.sec_user_agent()
    u, _fx = IA.universum_laden()
    if not u:
        log.error("Top-500-Daten nicht lesbar - Abbruch.")
        return 1
    aktien = sorted([e for e in u if e["art"] == "aktie" and e.get("ticker")],
                    key=lambda e: -float((e.get("info") or {}).get("mcap") or 0))
    index, st_index = T.lade_state_geprueft(STATE_INDEX, {})
    if st_index == "fehler":
        log.error("Index nicht lesbar - Abbruch ohne zu schreiben.")
        return 1
    index = index or {}
    ki = KI.verfuegbar()
    ki_rest = C.KI[ki.name]["max_je_lauf"] if ki else 0
    ciks = QQ.sec_cik_tabelle(ua) if ua else {}
    log.info(f"Qualitativ: {len(aktien)} Aktien, {len(index)} im Index, SEC {'an' if ua else 'aus (kein SEC_USER_AGENT)'}"
             f" ({len(ciks)} CIKs), KI {ki.titel if ki else 'aus (kein Key)'}")
    n_sec = n_kurz = 0
    for e in aktien:
        if _uhr() - start > ZEITBUDGET_SEK or (n_sec >= C.SEC["max_je_lauf"] and n_kurz >= MAX_KURZ):
            break
        sym = e["ticker"]
        alt = index.get(sym)
        cik = ciks.get(sym.upper()) if "." not in sym else None      # nur US-Ticker (ohne Boersenendung)
        wert = None
        if cik and n_sec < C.SEC["max_je_lauf"]:
            f10k = QQ.sec_letzter_10k(cik, ua)
            if f10k and faellig(alt, heute, f10k["acc"]):
                html = QQ.sec_dokument(f10k["url"], ua)
                if html:
                    ab = Q.abschnitte(Q.text_aus_html(html))
                    text = " ".join([ab["business"], ab["risiken"]])
                    wert = {"quelle_text": "10-K", "sec": f10k, **analyse_text(text, "10-K"),
                            "grosskunden": Q.grosskunden(ab["business"] + " " + ab["risiken"]),
                            "auszuege": auszuege(ab)}
                    n_sec += 1
        elif not cik and n_kurz < MAX_KURZ and faellig(alt, heute):
            try:
                from investor_checks import abruf as AB
                info = (AB.roh_laden(sym, parallel=1) or {}).get("info") or {}
            except Exception as ex:
                log.warning(f"{sym}: {type(ex).__name__}")
                info = {}
            txt = info.get("longBusinessSummary") or ""
            if txt:
                wert = {"quelle_text": "Kurzbeschreibung", **analyse_text(txt, "Kurzbeschreibung"),
                        "grosskunden": [], "auszuege": {"business": txt}}
                n_kurz += 1
        if not wert:
            continue
        wert["wikidata"] = QQ.wikidata(cik=cik, isin=e.get("isin") or None, ua=ua or None)
        wert.update({"st": heute.isoformat(), "name": e["name"], "sektor": e.get("sektor") or ""})
        if ki and ki_rest > 0:
            p = Q.prompt({"name": e["name"], "ticker": sym, "sektor": e.get("sektor")}, kennzahlen_fuer_prompt(e),
                         {"Geschäftsbeschreibung": wert["auszuege"].get("business"),
                          "Wettbewerb": wert["auszuege"].get("competition"),
                          "Risikofaktoren": wert["auszuege"].get("risiken")}, C.KI[ki.name]["max_woerter"])
            erg, fehler = ki.analyse(p)
            ki_rest -= 1
            if erg:
                erg["datum"] = heute.isoformat()
                wert["ki"] = erg
            else:
                log.warning(f"{sym}: KI ohne gültige Antwort ({fehler})")
        if T.speichere_state(datei(sym), wert, "qualitativ [skip ci]"):
            index[sym] = {"st": wert["st"], "acc": (wert.get("sec") or {}).get("acc"), "q": wert["quelle_text"],
                          "d": wert["dichte"], "sek": wert["sektor"], "ki": bool(wert.get("ki"))}
        if (n_sec + n_kurz) % 50 == 0:
            T.speichere_state(STATE_INDEX, index, "qualitativ index [skip ci]")
    T.speichere_state(STATE_INDEX, index, "qualitativ index [skip ci]")
    T.speichere_state(STATE_META, meta_aus_index(index, heute), "qualitativ meta [skip ci]")
    log.info(f"Fertig: {n_sec} 10-K, {n_kurz} Kurzbeschreibungen, Index {len(index)} Werte.")
    return 0


def meta_aus_index(index, heute):
    """Sektor-Mediane der Textdichte je Quelle (10-K / Kurzbeschreibung) - Vergleichsbasis der Textanalyse."""
    peer, alle = {}, {}
    for w in index.values():
        q, sek = w.get("q"), w.get("sek") or ""
        peer.setdefault(q, {}).setdefault(sek, []).append(w.get("d") or {})
        alle.setdefault(q, []).append(w.get("d") or {})
    return {"stand": heute.isoformat(),
            "peer": {q: {s: Q.peer_mediane(v) for s, v in je.items()} for q, je in peer.items()},
            "alle": {q: Q.peer_mediane(v) for q, v in alle.items()}}


if __name__ == "__main__":
    sys.exit(main())
