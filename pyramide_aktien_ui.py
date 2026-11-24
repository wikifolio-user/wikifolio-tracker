"""Pyramidenmanager Etappe 4 - Aktien-Trendscanner und Daten fuer Aktien-Pyramiden (Rechenkern: pyramide_aktien.py).

Aktienliste = Depotwerte (zugeordnet ueber die Top-500-Bewertung: ISIN/WKN -> Yahoo-Kuerzel) + eigene Liste
(state/pyramiden_aktien.json je Benutzer). Kerzen werden beim Oeffnen geladen und 6 Stunden zwischengespeichert."""
import datetime
import html
import logging
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

import pyramide as P
import pyramide_aktien as PA
import ui_stil as UI

K = "pyr_ak_"
DATEI = "state/pyramiden_aktien.json"
MAX_WERTE = 60


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _de(x, n=1):
    if x is None:
        return "–"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(ttl=6 * 3600, max_entries=200, show_spinner=False)
def _kerzen(ticker, _get, fenster):
    """fenster: Zeitschluessel (6-Stunden-Takt), damit spaetestens dann neu geladen wird."""
    try:
        return PA.kerzen_laden(ticker, _get, datetime.datetime.now(datetime.timezone.utc), headers=_headers()), None
    except PA.AbrufFehler as ex:
        return None, str(ex)


def _headers():
    try:
        import markt_daten
        return markt_daten.HEADERS
    except Exception:
        return {}


def _fenster():
    j = datetime.datetime.now(datetime.timezone.utc)
    return f"{j:%Y-%m-%d}-{j.hour // 6}"


def analyse(h, ticker, name=""):
    """Analyse einer Aktie (fuer Aktien-Pyramiden). -> (a, fehler)"""
    if not h.get("get"):
        return None, "Kein Netzzugang für Kursdaten."
    daten, fehler = _kerzen(ticker, h["get"], _fenster())
    if fehler:
        return None, fehler
    return PA.analyse(ticker, name, daten, datetime.datetime.now(datetime.timezone.utc)), None


def _eigene_laden(h):
    try:
        d, ok = h["lesen"](h["upfad"](DATEI), {"aktien": []})
    except Exception:
        d, ok = {"aktien": []}, False
    liste = d.get("aktien") if isinstance(d, dict) and isinstance(d.get("aktien"), list) else []
    return [x for x in liste if isinstance(x, dict) and x.get("ticker")], ok


def _eigene_speichern(h, aendern, text):
    if not h.get("speichern"):
        st.session_state["pyr_meldung"] = ("warn", "Speichern ist gerade nicht möglich (kein Datenspeicher).")
        return False

    def f(alt):
        liste = alt.get("aktien") if isinstance(alt, dict) and isinstance(alt.get("aktien"), list) else []
        return {"aktien": aendern(list(liste))}
    try:
        ok, _ = h["aktualisiere"](h["upfad"](DATEI), f, {"aktien": []}, f"pyramiden: {text} [skip ci]")
    except Exception as ex:
        logging.warning("Aktienliste: Speichern fehlgeschlagen: %s", type(ex).__name__)
        ok = False
    st.session_state["pyr_meldung"] = ("ok", f"Gespeichert: {text}.") if ok else \
        ("warn", "Speichern fehlgeschlagen – bitte erneut versuchen.")
    return bool(ok)


def _bewertungsquellen(h):
    """(zuordnen(position) -> (ticker, name), bewertung(ticker) -> (eintrag, b), investoren {ticker: kurzform})."""
    d, inv = None, {}
    try:
        d = h["bewertung_daten"]() if h.get("bewertung_daten") else None
    except Exception as ex:
        logging.warning("Aktien-Scanner: Bewertung nicht verfügbar (%s)", type(ex).__name__)
    try:
        inv = h["investoren"]() if h.get("investoren") else {}
    except Exception as ex:
        logging.warning("Aktien-Scanner: Investoren-Checks nicht verfügbar (%s)", type(ex).__name__)
    import scoring as SC

    def finden(kennungen):
        if not d:
            return None
        for k in kennungen:
            eid = d["je_kennung"].get(str(k or "").upper()) if k else None
            if eid:
                e = d["je_id"][eid]
                return e, SC.bewerten(e, d["ver"])
        return None

    def zuordnen(p):
        r = finden((p.get("isin"), p.get("wkn"), p.get("symbol")))
        if r and r[0].get("ticker"):
            return r[0]["ticker"], r[0].get("name")
        return None
    return zuordnen, (lambda t: finden((t,))), inv or {}


def liste(h):
    """-> (werte [{ticker, name, quelle}], nicht zuordenbare Depotnamen, bewertung, investoren)"""
    zuordnen, bewertung, inv = _bewertungsquellen(h)
    try:
        depot = h["aktien_depot"]() if h.get("aktien_depot") else []
    except Exception:
        depot = []
    eigene, _ = _eigene_laden(h)
    werte, ohne = PA.liste_zusammenstellen(depot, eigene, zuordnen)
    return werte[:MAX_WERTE], ohne, bewertung, inv


def scanner(h, neue_pyramide):
    """Aktien-Trendscanner. neue_pyramide(ticker, name): Pyramide fuer diese Aktie anlegen (aus pyramide_ui)."""
    ss = st.session_state
    st.markdown("**Aktien-Trendscanner** – derselbe Trend-Score wie bei den Indizes, dazu die vorhandene "
                "Aktienbewertung")
    werte, ohne, bewertung, inv = liste(h)
    with st.expander("➕ Aktie zur eigenen Liste hinzufügen", expanded=not werte):
        sp = st.columns([2, 3, 1]) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        t = sp[0].text_input("Yahoo-Kürzel", key=K + "neu_ticker", max_chars=20, placeholder="z. B. AAPL, SAP.DE")
        n = sp[1].text_input("Name (optional)", key=K + "neu_name", max_chars=60)
        if sp[2].button("Hinzufügen", key=K + "neu_btn", disabled=not (t or "").strip(), width="stretch"):
            ticker = t.strip().upper()
            daten, fehler = _kerzen(ticker, h.get("get"), _fenster()) if h.get("get") else (None, "Kein Netzzugang.")
            if fehler:
                st.error(fehler)
            else:
                name = (n or "").strip() or daten.get("name") or ticker

                def dazu(x):
                    return x if any(y["ticker"] == ticker for y in x) else x + [{"ticker": ticker, "name": name[:60]}]
                if _eigene_speichern(h, dazu, f"{ticker} in die Aktienliste"):
                    for k in ("neu_ticker", "neu_name"):
                        ss.pop(K + k, None)
                    st.rerun()
        st.caption("Das Kürzel muss Yahoo Finance kennen (deutsche Werte meist mit „.DE“). Depotwerte erscheinen "
                   "automatisch, wenn sie in der Top-500-Bewertung stehen.")
    if ohne:
        st.caption("Nicht zuordenbare Depotwerte (kein Börsenkürzel bekannt, z. B. Fonds oder Zertifikate): "
                   + ", ".join(_e(x) for x in ohne[:12]) + (" …" if len(ohne) > 12 else ""))
    if not werte:
        st.info("Noch keine Aktien: Depotwerte aus der Top-500-Liste oder eigene Kürzel hinzufügen.")
        return
    if not h.get("get"):
        st.warning("Kein Netzzugang für Kursdaten.")
        return
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    fenster = _fenster()
    with st.spinner(f"Lade Tageskerzen für {len(werte)} Aktien …"):
        with ThreadPoolExecutor(max_workers=6) as ex:
            ergebnisse = list(ex.map(lambda w: _kerzen(w["ticker"], h["get"], fenster), werte))
    cfg = P.einstellungen(PA.AKTIEN_EINSTELLUNGEN)
    zeilen, fehler = [], []
    for w, (daten, f) in zip(werte, ergebnisse):
        if f:
            fehler.append(f"{w['ticker']}: {f}")
            continue
        a = PA.analyse(w["ticker"], w["name"], daten, jetzt, cfg)
        zeilen.append(PA.scanner_zeile(a, cfg, bewertung(w["ticker"]), inv.get(w["ticker"]), w["quelle"]))
    zeilen = PA.sortieren(zeilen)
    z = PA.zusammenfassung(zeilen)
    st.caption(f"{z['anzahl']} Aktien · {z['signale']} mit Einstiegssignal · Median Trend-Score "
               f"{_de(z['median_trend'], 0)}" + (f" · {z['fehlt']} ohne aktuelle Kerzen" if z["fehlt"] else ""))
    if fehler:
        st.caption("Nicht geladen: " + "; ".join(_e(x) for x in fehler[:8]))
    if not zeilen:
        return
    import pandas as pd
    df = pd.DataFrame([{
        "Signal": "✅" if r["signal"] else "–", "Name": r["name"], "Kürzel": r["ticker"], "Quelle": r["quelle"],
        "Trend-Score": r["trend"], "Kurs": r["kurs"], "Währung": r["waehrung"],
        "Abstand 52W-Hoch %": round(r["abstand_hoch_pct"], 1) if r["abstand_hoch_pct"] is not None else None,
        "12 Monate %": round(r["rendite_12m"], 1) if r["rendite_12m"] is not None else None,
        "ATR %": round(r["atr_pct"], 2) if r["atr_pct"] is not None else None,
        "Bewertung": r["bewertung"], "Fazit": r["fazit"] or "", "Investoren-Note": r["investoren_note"],
        "Kaufen (Investoren)": r["investoren_kaufen"] or "", "Kerze": r["letzte_kerze"] or ""} for r in zeilen])
    for sp in ("Trend-Score", "Kurs", "Bewertung"):
        df[sp] = pd.to_numeric(df[sp], errors="coerce")
    ev = st.dataframe(df, hide_index=True, width="stretch", key=K + "tab", on_select="rerun",
                      selection_mode="single-row",
                      column_config={"Trend-Score": st.column_config.ProgressColumn("Trend-Score", min_value=0,
                                                                                    max_value=100, format="%.0f"),
                                     "Bewertung": st.column_config.NumberColumn("Bewertung", format="%.0f")})
    st.caption("Einstiegssignal wie bei den Indizes: Trend-Score ≥ "
               f"{cfg['einstieg_ab']}, Kurs über der 200-Tage-Linie, 50-Tage- über 200-Tage-Linie. Bewertung: "
               "Gesamtscore der Top-500-Bewertung; Investoren-Note aus dem Legenden-Screener (sofern vorberechnet). "
               "Für Aktien gibt es kein Fear & Greed und keine Gap-Analyse. Keine Anlageberatung.")
    if ev and ev.selection.rows:
        r = zeilen[ev.selection.rows[0]]
        st.markdown(f"**{_e(r['name'])}** ({_e(r['ticker'])}): " + (
            "Einstiegssignal liegt vor." if r["signal"] else " ".join(_e(g) for g in r["gruende"])))
        sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
        if sp[0].button("🔺 Pyramide für diese Aktie anlegen", key=K + "pyr_btn"):
            neue_pyramide(r["ticker"], r["name"])
        if r["quelle"] == "eigene Liste" and sp[1].button("Aus der eigenen Liste entfernen", key=K + "weg_btn"):
            if _eigene_speichern(h, lambda x: [y for y in x if y["ticker"] != r["ticker"]],
                                 f"{r['ticker']} aus der Aktienliste"):
                st.rerun()
