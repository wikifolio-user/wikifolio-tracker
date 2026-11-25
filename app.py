import bisect
import copy
import datetime
import time
import re
import html
import logging
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import plotly.graph_objects as go
import pytz
import os
import requests
import streamlit as st

import config
import github_store
import chronik
import indizes
import startseite
import depot_summe
import speicherleiste as SL
import charts_ansichten
import depot_verwalten_ansichten
import ranglisten_ansichten
import prognose_ansichten
from depot_html import (  # noqa: F401 - ausgelagert (Audit ARCH-01), Namen bleiben in app.py verfuegbar
    ALLE_ZEITRAEUME, KERN_ZEITRAEUME, _richtung_html, badge_html, depot_hero_html, depot_kachel_html,
    gv_zeile_html, kennzahl_kacheln_html, zeitraeume_teilen, zeitraum_zeilen_html,
)
from depot_rechnen import (  # noqa: F401 - ausgelagert (Audit ARCH-01), Namen bleiben in app.py verfuegbar
    _berlin_tage, _h, _kaufm, berechne_performance_kennzahlen, berechne_reale_stueckzahl, berechne_robuste_cagr,
    berechne_zeitraeume, depot_kennzahlen, depot_kennzahlen_real, entnahme_rate_aus_state, entnahme_termine, fmt,
    fmt_vz, gesamt_perioden_berechnen, haenge_live_punkt_an, hochgerechnete_rendite_pa, kumulierte_entnahme, mc_einsatz,
    monats_termine, perf_sortierwert, prognose_rate_rueckfall, realisierte_rendite_pa, referenzkurs_vor_tagen, rendite_pa_geldgewichtet,
    rendite_pa_seit_kauf, simuliere_bandbreite, sparplan_einzelkaeufe, sparplan_kaeufe, sparplan_phasen, sparplan_state_neu,
    sparplan_termine, sparplan_verlauf, sparrate_am, vz_zahl, wikifolio_rangliste, wikifolio_werte,
)
import glossar_ui
import login
import nutzerdaten
import kurs_dienst as KD
import kurs_vorrat as KV
import formate as FMT
import ui_stil as UI
import ui_hell
import schritte
import szenario as SZ
import prognose_basis as PROG_BASIS
import branchen as BR
import dividenden as DV

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PAGE CONFIG ---
st.set_page_config(page_title="Finanz Dashboard", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- PREMIUM GLASS THEME (Grundlage; ui_stil verfeinert darauf aufbauend) ---
from glass_theme import apply_glass_theme
apply_glass_theme()

# --- PWA / "App-Icon"-Unterstuetzung ---
# Ermoeglicht, die Seite ueber "Zum Home-Bildschirm hinzufuegen" wie eine
# eigene App aussehen zu lassen: eigenes Icon, kein Safari-Rahmen/Adresszeile
# beim Start vom Homescreen, passende Statusleisten-/Titelleisten-Farbe.
# Icons werden von GitHub (raw-content) geladen, da Streamlit selbst keine
# eigenen statischen Zusatzdateien unter frei waehlbaren Pfaden ausliefert.
#
# Audit SEC-01: raw.githubusercontent.com liefert nur bei OEFFENTLICHEM Repo aus.
# Liegt der State (benutzer.json mit Passwort-Hashes, Positionen, Chronik) im
# selben Repo, muss dieses PRIVAT sein - dann die Icons woanders ablegen (z. B.
# ein eigenes oeffentliches Repo nur mit manifest.json/icon-180.png oder GitHub
# Pages) und die Basis-URL per Secret ICON_BASE_URL setzen. Ohne Secret gilt
# die bisherige URL (funktioniert nur, solange das Repo oeffentlich ist).
_GH_RAW_BASE_STANDARD = "https://raw.githubusercontent.com/wikifolio-user/wikifolio-tracker/main"
try:
    _GH_RAW_BASE = str(st.secrets.get("ICON_BASE_URL", "") or _GH_RAW_BASE_STANDARD).rstrip("/")
except Exception:
    _GH_RAW_BASE = _GH_RAW_BASE_STANDARD
if not re.match(r"^https://[^\s\"'<>]+$", _GH_RAW_BASE):
    _GH_RAW_BASE = _GH_RAW_BASE_STANDARD
st.markdown(f"""
<link rel="manifest" href="{html.escape(_GH_RAW_BASE)}/manifest.json">
<link rel="apple-touch-icon" href="{html.escape(_GH_RAW_BASE)}/icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="LS9VFS">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#07090f">
""", unsafe_allow_html=True)

# --- SECRETS ---
DISCORD_WEBHOOK_URL = st.secrets.get("DISCORD_WEBHOOK_URL", "")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")   # z.B. "dein-user/wikifolio-tracker"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # Personal Access Token, Scope "repo"
GH_STATE_READY = bool(GITHUB_REPO and GITHUB_TOKEN)

BERLIN_TZ = pytz.timezone("Europe/Berlin")

# --- MEHRERE DEPOTPOSITIONEN ---
# Bewusst hier statt in config.py definiert, damit config.py unveraendert
# bleiben kann. Die Positionsliste selbst liegt im GitHub-State und ist damit
# zur Laufzeit anlegbar/aenderbar/loeschbar - ohne Code-Deploy.
STATE_PATH_POSITIONEN = "state/positionen.json"

# --- BEOBACHTUNGSLISTE (Watchlist) ---
# Werte, deren Kurs angezeigt werden soll, die aber KEIN Bestandteil des Depots
# sind - sie fliessen bewusst nicht in Depotwert, Gewinn oder Gesamtsumme ein.
STATE_PATH_BEOBACHTUNG = "state/beobachtung.json"

# --- AUFLEGUNGSDATEN ---
# wikifolio-Zertifikate starten IMMER bei 100 €. ls-tc.de liefert die Historie
# aber erst ab Listing (LS9VFS z.B. erst ab 09.07.2025 bei 128,80 €) - der
# Abschnitt davor fehlt in den Daten komplett. Das Auflegungsdatum wird deshalb
# hier je Instrument dauerhaft hinterlegt und fliesst ueberall dort ein, wo mit
# der Produkt-Rendite gerechnet wird (Prognose, Meilenstein, Simulator).
STATE_PATH_AUFLEGUNG = "state/auflegung.json"

# --- MONATLICHE ENTNAHME (Audit DEP-03) ---
# Eine einzige, gespeicherte Quelle fuer die Entnahme der Hauptposition
# ({"rate": 70.0}); fehlt die Datei, gilt config.ENTNAHME_PM.
STATE_PATH_ENTNAHME = "state/entnahme_state.json"
WIKIFOLIO_STARTKURS = 100.0

# --- TERMINAL STYLING ---
# Bewusst AUSSERHALB des periodisch aktualisierenden Fragments (siehe unten) -
# wird dadurch nur EINMAL pro echtem Seitenaufbau injiziert, nicht alle 5 Min.
# War die Hauptursache fuer das sichtbare Aufhellen/Verdunkeln bei jedem
# Fragment-Rerun (kompletter CSS-Neuaufbau zwingt den Browser zum Neu-Rendern
# der gesamten Seite).
st.markdown(UI.CSS_BASIS + UI.CSS_RESPONSIV, unsafe_allow_html=True)


# --- STATE-HELFER (persistent über GitHub statt fluechtiges Streamlit-Dateisystem) ---
def _speicher_fehler_merken():
    """Lesefehler des GitHub-Speichers fuer diesen Seitenaufbau vormerken (Audit A-10):
    die Anzeige ist dann unvollstaendig - render_dashboard() zeigt einen Hinweis."""
    try:
        st.session_state["_speicher_fehler"] = True
    except Exception:
        pass


def gh_read(path, default):
    if not GH_STATE_READY:
        return default
    data, _ = github_store.get_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, GITHUB_TOKEN, default=default)
    if path in github_store._fehlerhaft():
        _speicher_fehler_merken()
    return data if data is not None else default


def gh_read_streng(path, default):
    """Wie gh_read, wirft aber github_store.LeseFehler bei Lesefehlern (404 ->
    default). Grundlage der gecachten Leser: st.cache_data speichert Ausnahmen
    NICHT - ein Fehlschlag landet so nie im Zwischenspeicher (Audit DATA-01)."""
    if not GH_STATE_READY:
        return default
    data, _ = github_store.lese_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, GITHUB_TOKEN, default=default)
    return data if data is not None else default


@st.cache_data(ttl=900, show_spinner=False)
def _gh_read_taeglich_roh(path, default):
    return gh_read_streng(path, default)


def gh_read_taeglich(path, default):
    """Fuer Dateien, die die Agenten nur einmal taeglich schreiben (Watchlist-
    Ranglisten, Qualitaets-Score): 15 Minuten gehalten statt 60 Sekunden -
    die Dateien sind mehrere hundert KB gross. Lesefehler -> default, aber
    NICHT zwischengespeichert (naechster Aufruf versucht es erneut)."""
    try:
        return _gh_read_taeglich_roh(path, default)
    except github_store.LeseFehler as e:
        logging.warning(f"gh_read_taeglich: {path} nicht lesbar ({type(e).__name__})")
        _speicher_fehler_merken()
        return default


gh_read_taeglich.clear = _gh_read_taeglich_roh.clear


@st.cache_data(ttl=60, show_spinner=False)
def _gh_read_cached_roh(path, default):
    return gh_read_streng(path, default)


def gh_read_cached_status(path, default):
    """-> (daten, ok). ok=False: die Datei war gerade NICHT lesbar (daten = default).
    Wer auf Basis der gelesenen Daten etwas schreibt oder verschickt, muss ok pruefen."""
    try:
        return _gh_read_cached_roh(path, default), True
    except github_store.LeseFehler as e:
        logging.warning(f"gh_read_cached: {path} nicht lesbar ({type(e).__name__})")
        _speicher_fehler_merken()
        return default, False


def gh_read_cached(path, default):
    """Wie gh_read, aber 60s gecacht - für Status-/Alarm-Reads, die bei jedem
    30s-Autorefresh sonst unnötig oft die GitHub-API belasten (Rate-Limit
    5.000/Std.). NICHT für Daten verwenden, die sofort nach einem Schreiben
    im selben Nutzer-Flow wieder gelesen werden müssen (z.B. Trader-Log) -
    dafür bleibt gh_read() ungecacht. Fehlgeschlagene Lesevorgaenge werden
    nicht gecacht (Audit DATA-01)."""
    return gh_read_cached_status(path, default)[0]


gh_read_cached.clear = _gh_read_cached_roh.clear


def gh_write(path, obj, message="update state [skip ci]"):
    """Kompletter Ersatz einer Datei. -> True/False (Aufrufer MUSS das pruefen).
    Fuer Lesen-Aendern-Schreiben stattdessen gh_aktualisiere() verwenden."""
    if not GH_STATE_READY:
        return False
    erfolg = github_store.put_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, obj, GITHUB_TOKEN, message=message)
    if erfolg:
        # WICHTIG: den Lese-Cache leeren. Sonst liefert gh_read_cached() bis zu
        # 60s lang noch den ALTEN Zustand.
        gh_read_cached.clear()
    return erfolg


def gh_aktualisiere(path, aendern, default=None, message="update state [skip ci]"):
    """Lesen + Aendern + Schreiben mit Versionspruefung (github_store.aktualisiere_json).
    aendern(daten) -> neue Daten oder None (= nichts schreiben); wird bei einem
    Konflikt mit frisch gelesenen Daten erneut aufgerufen. Nach einem Lesefehler
    wird NICHTS geschrieben. -> (ok, neue_daten)"""
    if not GH_STATE_READY:
        return False, None
    ok, neu = github_store.aktualisiere_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, GITHUB_TOKEN,
                                             aendern, default=default, message=message)
    if ok:
        gh_read_cached.clear()
    return ok, neu


# --- BENUTZERBEZOGENE SPEICHERORTE (nutzerdaten.py) ---
# Admin und App ohne Login: bisherige Pfade unveraendert. Jeder andere Benutzer:
# state/benutzer/<name>/<datei> - existiert dort nichts, startet er leer (0).
# Gemeinsame Marktdaten (Top-Listen, Qualitaet, Katalog, Kurse, Alarm-Zustaende)
# laufen NIE hierueber. Gecachte Leser bekommen den aufgeloesten Pfad als Argument
# und sind damit automatisch je Benutzer getrennt zwischengespeichert.
def upfad(basis):
    """Speicherort einer Datei fuer den angemeldeten Benutzer."""
    return nutzerdaten.pfad(basis, st.session_state.get("_nutzer"))


def eigener_bereich():
    """True fuer normale Benutzer (eigene Daten), False fuer Admin / ohne Login."""
    return nutzerdaten.ist_eigener_bereich(st.session_state.get("_nutzer"))


def _discord_senden(text):
    """Eine Discord-Nachricht. -> True nur bei HTTP 2xx (Ergebnis wird geprueft)."""
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json={"content": text}, timeout=5)
        if 200 <= r.status_code < 300:
            return True
        logging.error(f"Discord-Versand fehlgeschlagen: HTTP {r.status_code}")
    except Exception as e:
        logging.error(f"Discord-Versand fehlgeschlagen: {type(e).__name__}")
    return False


def _bereinige(text, geheimnisse=()):
    """Entfernt URLs (z. B. Discord-Webhooks) und Tokens aus Log-/Fehlertexten."""
    s = str(text)
    for g in geheimnisse:
        if g:
            s = s.replace(str(g), "***")
    s = re.sub(r"https?://\S+", "<url>", s, flags=re.IGNORECASE)
    return re.sub(r"(gh[pousr]_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|Bearer\s+\S+)", "***", s)


# --- APP-FEHLER AN DISCORD MELDEN (Punkt 10) ---
def notify_app_error(context, exc):
    """Meldet einen Fehler INNERHALB der Streamlit-App an Discord (nicht nur
    in die schwer einsehbaren Cloud-Logs). Cooldown pro 'context' (z.B. Tab-
    Name), damit ein wiederholt fehlschlagender Bereich nicht bei jedem
    30s-Autorefresh erneut pingt. URLs und Tokens werden vor dem Loggen und
    Versenden entfernt."""
    geheim = (DISCORD_WEBHOOK_URL, GITHUB_TOKEN)
    fehler_text = _bereinige(f"{type(exc).__name__}: {exc}", geheim)
    tb_text = _bereinige(traceback.format_exc(), geheim)
    logging.error(f"App-Fehler in '{context}': {fehler_text}\n{tb_text}")
    if not DISCORD_WEBHOOK_URL:
        return

    state, lesbar = gh_read_cached_status(config.STATE_PATH_APP_ERROR, {})
    if not lesbar:
        return              # ohne gesicherten Cooldown-Zustand nichts verschicken
    now = datetime.datetime.now(BERLIN_TZ)
    last_str = (state or {}).get(context)
    cooldown_ok = True
    if last_str:
        try:
            cooldown_ok = (now - datetime.datetime.fromisoformat(last_str)).total_seconds() > 30 * 60
        except Exception:
            pass

    if not cooldown_ok:
        return

    msg = (f"🐞 **App-Fehler ({config.WKN})**\n"
           f"Bereich: **{context}**\n"
           f"Fehler: `{fehler_text[:200]}`\n"
           f"```\n{tb_text[-1200:]}\n```\n"
           f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}")
    if _discord_senden(msg):
        def _merken(d):
            d = d if isinstance(d, dict) else {}
            d[context] = now.isoformat()
            return d
        gh_aktualisiere(config.STATE_PATH_APP_ERROR, _merken, default={},
                        message="update app error state [skip ci]")


def entnahme_standard(eigen):
    """Entnahme ohne gespeicherten Wert: Admin config.ENTNAHME_PM, normale Benutzer 0."""
    return 0.0 if eigen else float(getattr(config, "ENTNAHME_PM", 0.0) or 0.0)


def haupt_position_aktiv(eigen, sparplan_phasen_liste, sparplan_eingezahlt=0.0):
    """Gibt es eine Hauptposition (Depotwert-Kachel, Vermoegens-Charts)? Admin / ohne
    Login immer; normale Benutzer nur mit eigenem Sparplan (Startkapital 0)."""
    if not eigen:
        return True
    return bool(sparplan_phasen_liste) or float(sparplan_eingezahlt or 0.0) > 0


def kpi_metriken(zeilen, key, nk=2):
    """Kennzahlen je Zeitraum als st.metric in Glas-Karten (2 je Reihe, auch am Handy)."""
    if not zeilen:
        return
    with st.container(key=key):
        for i in range(0, len(zeilen), 2):
            spalten = st.columns(2, gap="small")
            for spalte, (label, betrag, pct) in zip(spalten, zeilen[i:i + 2]):
                r = FMT.richtung(betrag, nk)
                spalte.metric(label, FMT.eur(betrag, nk, vz=True), FMT.pct(pct, 2, vz=True),
                              delta_color={"up": "green", "down": "red"}.get(r, "gray"),
                              delta_arrow={"up": "up", "down": "down"}.get(r, "off"))


# --- LIVE-KURS ABRUF (ls-tc.de, direkter Emittent) ---
def ls_tc_live_auswerten(data):
    """(aktuell, vortag, zeitpunkt_ms) aus einer dataForInstrument-Antwort; ValueError ohne Kurs.
    Vortageskurs aus info.plotlines[id="previousDay"] (config.extract_previous_close), sonst
    aus der History-Serie, zuletzt der erste Intraday-Punkt."""
    intraday = (data.get("series", {}).get("intraday", {}).get("data")
                or data.get("intraday", {}).get("data") or [])
    if not intraday:
        raise ValueError("keine Intraday-Daten")
    zeitpunkt_ms, akt = int(intraday[-1][0]), float(intraday[-1][1])
    vor = config.extract_previous_close(data)
    if vor is None:
        history = (data.get("series", {}).get("history", {}).get("data")
                   or data.get("history", {}).get("data") or [])
        vor = config.pick_previous_close_from_history(history)
    if vor is None:
        vor = float(intraday[0][1])
    if not (akt > 0 and vor > 0):
        raise ValueError("ungueltige Kurswerte")
    return akt, vor, zeitpunkt_ms


def _live_abruf(instrument_id):
    """Live-Kurs aus dem Kursdienst (Hintergrund-Aktualisierung nach Zeitplan). Wirft bei
    Fehlern - ein Fehlschlag wird nie gemerkt (Audit A-07)."""
    return kurs_dienst().hole("live", instrument_id)


def _live_roh(instrument_id):
    """Netzabruf des Live-Kurses (nur der Kursdienst ruft ihn auf)."""
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "intraday,history,flags", "type": "", "localeId": "2",
    }
    r = requests.get(config.LS_TC_BASE_URL, params=params, headers=config.LS_TC_HEADERS, timeout=6)
    r.raise_for_status()
    return ls_tc_live_auswerten(r.json())


def get_live_kurs(instrument_id):
    """(aktueller_kurs, vortageskurs, quelle) bzw. (None, None, "Fehler – keine Live-Daten")."""
    try:
        akt, vor, _ = _live_abruf(str(instrument_id))
        return akt, vor, "ls-tc.de Live (Emittent)"
    except Exception as e:
        logging.error(f"Live-Kurs für Instrument {instrument_id} nicht ladbar: {type(e).__name__}")
        return None, None, "Fehler – keine Live-Daten"


LIVE_MAX_ALTER_MIN = 20


def kurs_status(kurs_zeit, jetzt, live_abruf_ok):
    """Kennzeichnung des angezeigten Kurses (Audit A-11): "live" nur bei erfolgreichem Abruf,
    innerhalb der Handelszeit und hoechstens LIVE_MAX_ALTER_MIN alt; sonst "stand" (echter,
    aber aelterer Kurs mit Zeitpunkt) bzw. "offline". -> (art, text)"""
    if not live_abruf_ok or kurs_zeit is None:
        return "offline", "Keine Live-Daten"
    alter_min = (jetzt - kurs_zeit).total_seconds() / 60
    if config.ist_handelszeit(jetzt) and -5 <= alter_min <= LIVE_MAX_ALTER_MIN:
        return "live", "Live"
    heute = kurs_zeit.date() == jetzt.date()
    return "stand", f"Stand {kurs_zeit.strftime('%H:%M') if heute else kurs_zeit.strftime('%d.%m. %H:%M')}"


def kurs_pill(art, text):
    klasse = {"live": "", "stand": " stand", "offline": " offline"}[art]
    return (f'<span class="live-pill{klasse}"><span class="live-dot{klasse}"></span>{html.escape(text)}</span>')


def get_live_market_data():
    """Live-Kurs der Hauptposition (config.LS_INSTRUMENT_ID)."""
    return get_live_kurs(config.LS_INSTRUMENT_ID)


def kurs_zeitpunkt(instrument_id):
    """Zeitpunkt (Europe/Berlin) des zuletzt geladenen Live-Kurses oder None (Audit A-11)."""
    try:
        return datetime.datetime.fromtimestamp(_live_abruf(str(instrument_id))[2] / 1000, tz=BERLIN_TZ)
    except Exception:
        return None


# --- ECHTE HISTORISCHE DATEN VON ls-tc.de LADEN ---
# Tageskurs-Historien aendern sich hoechstens einmal am Handelstag - der
# aktuelle Wert kommt ohnehin live ueber get_live_kurs(). Deshalb EIN Abruf je
# Instrument im Kursdienst (gilt fuer alle Sitzungen), fuer alle Zeitraeume nur zugeschnitten.


def lade_rohhistorie(instrument_id):
    """[(ts_ms, close), ...] einer Instrument-ID aus dem Kursdienst; wirft bei Fehlern."""
    try:
        return kurs_dienst().hole("historie", instrument_id)
    except Exception as e:
        logging.error(f"Historie für Instrument {instrument_id} nicht ladbar: {e}")
        raise          # Fehler NICHT merken - beim naechsten Aufruf neu versuchen


def _historie_roh(instrument_id):
    """Netzabruf der Tageshistorie (nur der Kursdienst ruft ihn auf)."""
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "history", "type": "", "localeId": "2",
    }
    r = requests.get(config.LS_TC_BASE_URL, params=params, headers=config.LS_TC_HEADERS, timeout=8)
    r.raise_for_status()
    raw = r.json()
    return (raw.get("series", {}).get("history", {}).get("data")
            or raw.get("history", {}).get("data") or [])


def historie_zuschnitt(history, start_date, end_date):
    """Rohpunkte -> Series (Index=Zeitpunkt) im Datumsbereich, in einem
    Schritt fuer alle Punkte (schnell genug, um NICHT zwischenspeichern zu
    muessen - so landen auch keine Fehlerergebnisse im Speicher)."""
    if not history:
        return pd.Series(dtype=float)
    df = pd.DataFrame(history, columns=["ts", "Close"])
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    # Kalendertag in Europe/Berlin (Audit DEP-09): ls-tc liefert z. B. 22:00 UTC fuer
    # den Folgetag - als naive Mitternacht passt der Index zu bdate_range/reindex.
    df["Date"] = _berlin_tage(df["ts"]).values
    tage = df["Date"].dt.date
    df = df[(tage >= start_date) & (tage <= end_date) & (df["Close"] > 0)]
    s = df.set_index("Date").sort_index()["Close"].astype(float)
    return s[~s.index.duplicated(keep="last")]


KEINE_HISTORIE = "Fehler – keine Kurshistorie"


def get_historical_market_data(start_date, end_date):
    """Tages-Historie der Hauptposition von ls-tc.de als DataFrame (Open/High/Low/Close).
    Der Endpunkt liefert nur Schlusskurse - Open/High/Low werden daraus angenaehert
    (im Candlestick-Chart so beschriftet).

    Bei Fehlern: LEERER DataFrame und Quelle KEINE_HISTORIE - es werden nie Ersatz- oder
    Zufallsdaten erzeugt (Audit A-06)."""
    try:
        history = lade_rohhistorie(config.LS_INSTRUMENT_ID)
        closes = historie_zuschnitt(history, start_date, end_date)
        if not closes.empty:
            df = closes.to_frame("Close")
            df["Open"] = df["Close"]
            df["High"] = df["Close"] * 1.003
            df["Low"] = df["Close"] * 0.997
            return df[["Open", "High", "Low", "Close"]], "ls-tc.de Live (Emittent)"
        logging.warning("ls-tc.de: Keine verwertbare History-Struktur gefunden.")
    except Exception as e:
        logging.error(f"Fehler beim Laden der Historie von ls-tc.de: {type(e).__name__}")
    return pd.DataFrame(columns=["Open", "High", "Low", "Close"], dtype=float), KEINE_HISTORIE


def letzter_gespeicherter_kurs(reihen):
    """Letzter Kurs aus den vom Alarm-Workflow geschriebenen CSV-Texten
    (state/price_history/JJJJ-MM.csv, Zeilen "zeitstempel_iso,kurs"), neueste Datei zuerst.
    -> (kurs, zeitpunkt) oder (None, None). Ersatz, wenn ls-tc gerade nichts liefert (A-06)."""
    for text in reihen:
        for zeile in reversed((text or "").strip().splitlines()):
            teile = zeile.strip().split(",")
            if len(teile) != 2 or teile[0] == "timestamp":
                continue
            try:
                kurs = float(teile[1])
                zeit = datetime.datetime.fromisoformat(teile[0])
            except ValueError:
                continue
            if kurs > 0:
                return kurs, zeit
    return None, None


@st.cache_data(ttl=300, show_spinner=False)
def _preis_csv_roh(pfad):
    if not GH_STATE_READY:
        return ""
    text, _ = github_store.lese_text(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, GITHUB_TOKEN)
    return text or ""


def gespeicherter_kurs_hauptposition(heute):
    """Letzter vom Workflow protokollierter Kurs (diesen oder letzten Monat) oder (None, None)."""
    texte = []
    vormonat = heute.replace(day=1) - datetime.timedelta(days=1)
    for tag in (heute, vormonat):
        try:
            texte.append(_preis_csv_roh(config.price_history_csv_path(tag)))
        except Exception as e:
            logging.warning(f"Preis-Historie nicht lesbar: {type(e).__name__}")
    return letzter_gespeicherter_kurs(texte)


# --- BENCHMARK-VERGLEICHSDATEN (ls-tc.de, gleiche API wie LS9VFS) ---
def _benchmark_roh(instrument_id):
    """Rohhistorie eines Vergleichswerts aus dem Kursdienst; wirft bei Fehlern (Audit A-07)."""
    return kurs_dienst().hole("benchmark", instrument_id)


def _benchmark_netz(instrument_id):
    """Netzabruf der Vergleichswert-Historie (nur der Kursdienst ruft ihn auf)."""
    headers = {
        "User-Agent": config.LS_TC_HEADERS["User-Agent"],
        "Referer": f"https://www.ls-tc.de/de/etf/{instrument_id}",
    }
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "history", "type": "", "localeId": "2",
    }
    r = requests.get(config.LS_TC_BASE_URL, params=params, headers=headers, timeout=8)
    r.raise_for_status()
    raw = r.json()
    return (raw.get("series", {}).get("history", {}).get("data")
            or raw.get("history", {}).get("data") or [])


def get_benchmark_history(instrument_id, start_date, end_date):
    """Tages-Schlusskurse eines Vergleichswerts als Series (Berliner Kalendertage, DEP-09)
    oder None bei Fehler - Vergleichswerte sind "nice to have"."""
    try:
        history = _benchmark_roh(instrument_id)
    except Exception as e:
        logging.warning(f"Benchmark {instrument_id} nicht ladbar: {type(e).__name__}")
        return None
    s = historie_zuschnitt(history, start_date, end_date)
    return None if s.empty else s[s > 0]


def vergleichswerte_vorladen(instrument_ids, max_parallel=8):
    """Historie und Live-Kurs aller Vergleichswerte, die noch NICHT im Kursdienst liegen,
    GLEICHZEITIG abrufen (vorher nacheinander - 2 Netzabrufe je Wert). Fehler werden hier
    verschluckt; der anschliessende normale Aufruf behandelt sie wie bisher."""
    ids = list(dict.fromkeys(str(i) for i in instrument_ids if i))
    if len(ids) < 2:
        return

    def _eins(inst_id):
        for f in (_benchmark_roh, _live_abruf):
            try:
                f(inst_id)
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=min(max_parallel, len(ids))) as ex:
        list(ex.map(_eins, ids))


def benchmark_normiert_auf_startkapital(df_index, instrument_id, start_date, end_date, startkapital):
    """Reindext den Benchmark-Kurs auf die Handelstage von df_chart und
    skaliert ihn so, dass er am ersten ECHTEN Handelstag beim Startkapital
    beginnt. Kein Backfill mehr: existiert der Wert zu Beginn des Zeitraums
    noch nicht (z.B. spaeter aufgelegtes Produkt), bleibt die Linie davor
    leer statt rueckwirkend erfunden zu werden. Gibt (Series, erstes_echtes_Datum)
    zurueck."""
    s = get_benchmark_history(instrument_id, start_date, end_date)
    if s is None or s.empty:
        return None, None

    # LIVE-KURS EINSETZEN: die History-Endpunkte liefern Tages-Schlusskurse,
    # der letzte Punkt haengt also bis zu einen Handelstag hinterher. Fuer eine
    # ehrliche Momentaufnahme wird der aktuellste Punkt durch den Live-Kurs
    # ersetzt - sonst vergliche man einen tagesaktuellen eigenen Depotwert mit
    # veralteten Benchmarks. Faellt der Live-Abruf aus, bleibt der Schlusskurs
    # stehen (kein Grund, die ganze Linie zu verwerfen).
    live_kurs, _, _ = get_live_kurs(instrument_id)
    if live_kurs and live_kurs > 0:
        _zeit = kurs_zeitpunkt(instrument_id)              # Kalendertag des Kurses (Wochenende: Freitag)
        heute_ts = pd.Timestamp(_zeit.date() if _zeit is not None else end_date)
        s = s.copy()
        if not s.empty and s.index[-1].normalize() == heute_ts.normalize():
            s.iloc[-1] = live_kurs          # heutiger Punkt: aktualisieren
        else:
            s.loc[heute_ts] = live_kurs     # heute fehlt noch: anhaengen
            s = s.sort_index()

    erstes_echtes_datum = s.index.min()
    s_reindexed = s.reindex(df_index).ffill()
    gueltige = s_reindexed.dropna()
    if gueltige.empty or gueltige.iloc[0] == 0:
        return None, None
    normiert = s_reindexed / gueltige.iloc[0] * startkapital
    return normiert, erstes_echtes_datum


# =====================================================================
# MEHRERE POSITIONEN: Verwaltung, generische Kursabrufe, Kennzahlen
# =====================================================================

def _position_aus_config():
    """Die urspruengliche, fest in config.py verdrahtete Position - dient als
    Startbestand, damit nach dem Update sofort alles wie gewohnt aussieht."""
    return {
        "id": "config-hauptposition",
        "name": "Hauptindizes Global",
        "wkn": config.WKN,
        "instrument_id": int(config.LS_INSTRUMENT_ID),
        "kaufdatum": config.KAUFDATUM.isoformat(),
        "kaufkurs": float(config.ANFANGSKURS),
        "startkapital": float(config.STARTKAPITAL),
    }


def lade_positionen():
    """Liest die Positionsliste aus dem GitHub-State. Ist noch keine
    gespeichert, wird die config-Position als Startbestand zurueckgegeben
    (ohne zu schreiben - erst eine echte Nutzeraenderung legt die Datei an).

    Nutzt den 60s-Cache: die Liste wird bei jedem Rerun mehrfach gebraucht,
    ein ungecachter GitHub-API-Call pro Aufruf hat das Umschalten spuerbar
    ausgebremst. gh_write() leert den Cache, Aenderungen sind also sofort da.

    Normale Benutzer (eigener Bereich) lesen ihre eigene Datei und starten OHNE
    Startbestand - die config-Hauptposition gehoert dem Admin."""
    eigen = eigener_bereich()
    return positionen_oder_start(gh_read_cached(upfad(STATE_PATH_POSITIONEN), None), eigen)


def positionen_startbestand(eigen):
    """Startbestand, solange noch keine Positionsliste gespeichert ist:
    Admin / ohne Login die config-Position, normale Benutzer nichts (leeres Depot)."""
    return [] if eigen else [_position_aus_config()]


def positionen_oder_start(positionen, eigen):
    """Gespeicherte Liste oder (leer / nicht vorhanden) den Startbestand."""
    if positionen:
        return positionen
    return positionen_startbestand(eigen)


def depot_aufteilung(alle_positionen, eigen):
    """-> (Name der Hauptposition, weitere Positionen). Admin / ohne Login: die erste
    Position ist die Hauptposition (speist Charts/Prognose), der Rest sind weitere.
    Normale Benutzer: die Hauptposition ist hoechstens ihr Sparplan auf das config-
    Zertifikat - ALLE gespeicherten Positionen sind eigene, weitere Positionen."""
    alle_positionen = list(alle_positionen or [])
    if eigen:
        return f"Sparplan {config.WKN}", alle_positionen
    name = (alle_positionen[0].get("name", "Depotwert")
            if alle_positionen and isinstance(alle_positionen[0], dict) else "Depotwert")
    return name, alle_positionen[1:]


def _chronik_schreiben(pfad, kategorie, titel, inhalt="", schluessel=None):
    try:
        if not pfad or not GH_STATE_READY:
            return False
        return chronik.eintragen_github(github_store, GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, GITHUB_TOKEN,
                                        chronik.neuer_eintrag(kategorie, titel, inhalt, schluessel=schluessel))
    except Exception:
        return False


def chronik_eintrag(kategorie, titel, inhalt="", schluessel=None):
    """Automatischer Eintrag in die Chronik (Depot -> Chronik). Fehler werden
    geschluckt - die Chronik darf keine Speicherung verhindern. Schreibt mit
    Versionspruefung und nie nach einem Lesefehler (chronik.eintragen_github).
    Ziel ist die Chronik des angemeldeten Benutzers (Admin: die gemeinsame,
    in die auch die Workflows schreiben; normale Benutzer: ihre eigene)."""
    pfad = getattr(config, "STATE_PATH_TRADES_DB", None)
    return _chronik_schreiben(upfad(pfad) if pfad else None, kategorie, titel, inhalt, schluessel)


def chronik_eintrag_global(kategorie, titel, inhalt="", schluessel=None):
    """Eintrag in die gemeinsame (Admin-)Chronik - fuer Anmeldungen."""
    return _chronik_schreiben(getattr(config, "STATE_PATH_TRADES_DB", None), kategorie, titel, inhalt, schluessel)


def _de_zahl(x, nk=2):
    z = FMT.zahl(x, nk)
    return str(x) if z == FMT.LEER and x is not None else z


def _chronik_listen_diff(alt, neu, kategorie, wort, felder):
    """Unterschiede zweier Listen (Positionen/Beobachtung) als Chronik-Eintraege."""
    alt = {str(x.get("id")): x for x in (alt or []) if isinstance(x, dict)}
    neu = {str(x.get("id")): x for x in (neu or []) if isinstance(x, dict)}

    def name(x):
        return f"{x.get('name') or '?'}" + (f" ({x.get('wkn')})" if x.get("wkn") else "")
    for i, x in neu.items():
        if i not in alt:
            details = " · ".join(f"{lab} {fmt(x.get(k))}" for k, lab, fmt in felder if x.get(k) not in (None, ""))
            chronik_eintrag(kategorie, f"➕ {wort} angelegt: {name(x)}", details)
    for i, x in alt.items():
        if i not in neu:
            chronik_eintrag(kategorie, f"➖ {wort} entfernt: {name(x)}")
    for i, x in neu.items():
        if i in alt:
            aend = [f"{lab} {fmt(alt[i].get(k))} → {fmt(x.get(k))}" for k, lab, fmt in
                    [("name", "Name", str), ("wkn", "WKN", str)] + list(felder)
                    if str(alt[i].get(k)) != str(x.get(k))]
            if aend:
                chronik_eintrag(kategorie, f"✏️ {wort} geändert: {name(x)}", " · ".join(aend))


_POS_FELDER = [("kaufdatum", "Kaufdatum", lambda v: ".".join(reversed(str(v).split("-")))),
               ("kaufkurs", "Kaufkurs", lambda v: _de_zahl(v, 3) + " €"),
               ("startkapital", "Startkapital", lambda v: _de_zahl(v, 2) + " €"),
               ("instrument_id", "ID", str)]


def liste_element_index(liste, eid=None, idx=None, name=None):
    """Position eines Eintrags in einer (frisch gelesenen) Liste: ueber die id, ersatzweise
    (alte Eintraege ohne id) ueber Index + Name. -> Index oder None."""
    if eid:
        for i, x in enumerate(liste):
            if isinstance(x, dict) and str(x.get("id")) == str(eid):
                return i
        return None
    if idx is not None and 0 <= idx < len(liste) and isinstance(liste[idx], dict) \
            and liste[idx].get("name") == name:
        return idx
    return None


def _liste_aktualisieren(pfad, aendern, startbestand, message):
    """Lesen-Aendern-Schreiben einer Liste (Positionen/Beobachtung) ohne verlorene
    Updates und nie nach einem Lesefehler. aendern(liste) -> neue Liste | None.
    -> (geschrieben, alt, neu)"""
    erg = {}

    def _a(liste):
        alt = liste if isinstance(liste, list) and liste else startbestand()
        neu = aendern(copy.deepcopy(alt))
        erg["alt"], erg["neu"] = alt, neu
        return neu

    ok, _ = gh_aktualisiere(pfad, _a, default=None, message=message)
    geschrieben = bool(ok and erg.get("neu") is not None)
    if geschrieben:
        SL.gespeichert(st.session_state, SL_DEPOT, {"pfad": pfad, "inhalt": copy.deepcopy(erg.get("alt"))})
    elif not ok:
        SL.fehlgeschlagen(st.session_state, SL_DEPOT)
    return geschrieben, erg.get("alt"), erg.get("neu")


# --- Depot verwalten: Statuszeile und Rueckgaengig (speicherleiste) ueber alle Dateien des Bereichs ---
SL_DEPOT = "depot"
_SL_DEPOT_FELDER = ("haupt_sparrate_input", "_haupt_sparrate_input_basis", "haupt_entnommen_input",
                    "_haupt_entnommen_input_basis", "sparplan_beenden_ok")


def depot_aktualisieren(pfad, aendern, default=None, message="update state [skip ci]"):
    """gh_aktualisiere fuer Depot-Dateien (Sparplan, Entnahme) - merkt den alten Stand fuer Rueckgaengig."""
    alt_box = {}

    def _a(d):
        alt_box["alt"] = copy.deepcopy(d)
        return aendern(d)
    ok, neu = gh_aktualisiere(pfad, _a, default=default, message=message)
    if ok:
        SL.gespeichert(st.session_state, SL_DEPOT, {"pfad": pfad, "inhalt": alt_box.get("alt")})
    else:
        SL.fehlgeschlagen(st.session_state, SL_DEPOT)
    return ok, neu


def depot_rueckgaengig():
    """Letzte Speicherung in "Depot verwalten" zuruecknehmen (Callback). Die betroffene Datei bekommt ihren
    vorherigen Inhalt; Sparrate/Entnahme-Felder werden danach neu aus dem gespeicherten Stand vorbelegt."""
    z = SL.zustand(st.session_state, SL_DEPOT)
    if not z["stapel"] or not GH_STATE_READY:
        return
    stand = z["stapel"][-1]
    inhalt = stand.get("inhalt")
    try:
        ok, _ = gh_aktualisiere(stand["pfad"], lambda _alt: copy.deepcopy(inhalt if inhalt is not None else {}),
                                default=None, message="depot rückgängig [skip ci]")
    except Exception:
        ok = False
    if not ok:
        SL.fehlgeschlagen(st.session_state, SL_DEPOT)
        return
    z["stapel"].pop()
    SL.gespeichert(st.session_state, SL_DEPOT, merken=False)
    for k in _SL_DEPOT_FELDER:
        st.session_state.pop(k, None)
    try:
        gh_read_cached.clear()
    except Exception:
        pass
    chronik_eintrag("depot", "↶ Letzte Änderung zurückgenommen", stand["pfad"].rsplit("/", 1)[-1])


def aendere_positionen(aendern, message="update positionen [skip ci]"):
    """-> True nur, wenn wirklich gespeichert wurde."""
    eigen = eigener_bereich()
    ok, alt, neu = _liste_aktualisieren(upfad(STATE_PATH_POSITIONEN), aendern,
                                        lambda: positionen_startbestand(eigen), message)
    if ok:
        _chronik_listen_diff(alt, neu, "depot", "Position", _POS_FELDER)
    return ok


def lade_beobachtung():
    """Beobachtete Werte (reine Kursanzeige, NICHT im Depot). Standard ist eine
    leere Liste - ohne Eintraege verhaelt sich die App exakt wie vorher."""
    return gh_read_cached(upfad(STATE_PATH_BEOBACHTUNG), []) or []


def aendere_beobachtung(aendern, message="update beobachtung [skip ci]"):
    """-> True nur, wenn wirklich gespeichert wurde."""
    ok, alt, neu = _liste_aktualisieren(upfad(STATE_PATH_BEOBACHTUNG), aendern, lambda: [], message)
    if ok:
        _chronik_listen_diff(alt, neu, "beobachtung", "Beobachtung", [("instrument_id", "ID", str)])
    return ok


def lade_prognose_basis():
    """Eigene Prognose-Basis (Zukunfts-Prognose); noch nie gespeichert -> die Werte der Beobachtungsliste."""
    d = gh_read_cached(upfad(PROG_BASIS.PFAD), None)
    if isinstance(d, dict) and isinstance(d.get("werte"), list):
        return d["werte"]
    return PROG_BASIS.start_aus_beobachtung(lade_beobachtung())


def aendere_prognose_basis(aendern, message="update prognose-basis [skip ci]"):
    """aendern(liste) -> neue Liste | None. -> True nur, wenn wirklich gespeichert wurde."""
    erg = {}

    def _a(d):
        alt = (d["werte"] if isinstance(d, dict) and isinstance(d.get("werte"), list)
               else PROG_BASIS.start_aus_beobachtung(lade_beobachtung()))
        erg["neu"] = aendern(copy.deepcopy(alt))
        return None if erg["neu"] is None else {"werte": erg["neu"]}

    ok, _ = SL.aktualisieren(st.session_state, "prognose", gh_aktualisiere, upfad(PROG_BASIS.PFAD), _a, None,
                             message)
    return bool(ok and erg.get("neu") is not None)


def prognose_rueckgaengig():
    """Letzte Aenderung der Prognose-Werteliste zuruecknehmen (Callback, speicherleiste). War vorher noch nichts
    gespeichert, gilt wieder die Startliste aus der Beobachtungsliste."""
    z = SL.zustand(st.session_state, "prognose")
    if not z["stapel"] or not GH_STATE_READY:
        return
    stand = z["stapel"][-1]
    inhalt = stand if isinstance(stand, dict) else {"werte": PROG_BASIS.start_aus_beobachtung(lade_beobachtung())}
    try:
        ok, _ = gh_aktualisiere(upfad(PROG_BASIS.PFAD), lambda _alt: copy.deepcopy(inhalt), default=None,
                                message="prognose-basis rückgängig [skip ci]")
    except Exception:
        ok = False
    if not ok:
        SL.fehlgeschlagen(st.session_state, "prognose")
        return
    z["stapel"].pop()
    SL.gespeichert(st.session_state, "prognose", merken=False)
    try:
        gh_read_cached.clear()
    except Exception:
        pass


# --- VERGLEICHSWERTE (Vermoegensaufbau, Performance seit 2026/2021) je Benutzer ---
PFAD_VERGLEICHSWERTE = "state/vergleichswerte.json"
VERGLEICH_FARBEN = ["#2196F3", "#E91E63", "#FF9800", "#9C27B0", "#00BCD4", "#FFEB3B", "#795548", "#F44336",
                    "#3F51B5", "#FF5722", "#D4E157", "#26A69A", "#AB47BC", "#FFA726", "#29B6F6", "#EC407A"]


def _vergleich_start():
    """Startliste ohne gespeicherten Stand: Admin / ohne Login die bisherigen config.BENCHMARKS,
    neu angelegte Benutzer nichts (sie waehlen selbst aus der Top-500-Liste oder per Suche)."""
    if eigener_bereich():
        return []
    aus = []
    for i, (label, iid) in enumerate((getattr(config, "BENCHMARKS", {}) or {}).items()):
        m = re.search(r"\(([^)]*)\)\s*$", label)
        aus.append({"id": f"bench-{i}", "name": label, "label": label, "wkn": m.group(1) if m else "",
                    "instrument_id": int(iid)})
    return aus


def lade_vergleichswerte():
    d = gh_read_cached(upfad(PFAD_VERGLEICHSWERTE), None)
    if isinstance(d, dict) and isinstance(d.get("werte"), list):
        return [e for e in d["werte"] if isinstance(e, dict) and e.get("instrument_id")]
    return _vergleich_start()


def aendere_vergleichswerte(aendern, message="update vergleichswerte [skip ci]"):
    """aendern(liste) -> neue Liste | None. -> True nur, wenn wirklich gespeichert wurde."""
    erg = {}

    def _a(d):
        alt = (d["werte"] if isinstance(d, dict) and isinstance(d.get("werte"), list) else _vergleich_start())
        erg["neu"] = aendern(copy.deepcopy(alt))
        return None if erg["neu"] is None else {"werte": erg["neu"]}

    ok, _ = gh_aktualisiere(upfad(PFAD_VERGLEICHSWERTE), _a, default=None, message=message)
    return bool(ok and erg.get("neu") is not None)


def vergleich_label(e):
    """Anzeigename eines Vergleichswerts - bei den bisherigen Werten der config-Schluessel (Farben bleiben)."""
    return e.get("label") or (f"{e.get('name', 'Wert')} ({e['wkn']})" if e.get("wkn") else e.get("name", "Wert"))


def vergleich_farbe(label, i=0):
    return config.BENCHMARK_COLORS.get(label) or VERGLEICH_FARBEN[i % len(VERGLEICH_FARBEN)]


def top500_prognose_optionen():
    """Werte der Top-500-Daten mit Kurs-ID fuer die Prognose-Basis - je Sitzung und Tag gemerkt."""
    heute = datetime.date.today().isoformat()
    gemerkt = st.session_state.get("_prog_top500")
    if gemerkt and gemerkt[0] == heute:
        return gemerkt[1]
    import scanner
    teile = [d or {} for d in UI.parallel_lesen(gh_read_taeglich, [f"state/planer/katalog_gross_{i}.json"
                                                                   for i in range(4)], {})]
    ids = scanner.top500_ids(gh_read_taeglich("state/top50_ids.json", {}) or {},
                             gh_read_taeglich("state/top50_wikifolios.json", {}) or {})
    werte = PROG_BASIS.top500_optionen(teile, ids)
    st.session_state["_prog_top500"] = (heute, werte)
    return werte


def top500_optionen_bei_bedarf(schluessel):
    """Top-500-Auswahl erst laden, wenn sie gebraucht wird: sie besteht aus sechs grossen Dateien und steht
    in zugeklappten Bereichen - vorher wurde sie bei jedem Aufruf der Ansicht mitgeladen. Einmal geladen
    (je Sitzung und Tag gemerkt) erscheint sie sofort. -> Liste oder None (noch nicht angefordert)."""
    gemerkt = st.session_state.get("_prog_top500")
    if (gemerkt and gemerkt[0] == datetime.date.today().isoformat()) or st.session_state.get(schluessel):
        return top500_prognose_optionen()
    st.button("📋 Aus der Top-500-Liste wählen", key=f"{schluessel}_knopf",
              on_click=lambda: st.session_state.__setitem__(schluessel, True))
    return None


@st.cache_data(ttl=900, show_spinner=False)
def wikifolio_kennzahlen(tag):
    """Kennzahlen aller wikifolios aus dem Katalog des Watchlist-Agenten (Score, Vola, max. Verlust, Rendite p. a.,
    Rendite je Verlust, Historie) - je Tag einmal berechnet. tag nur als Cache-Schluessel."""
    import klassen_score as KS
    teile = [d for d in UI.parallel_lesen(gh_read_taeglich, [f"state/planer/katalog_gross_{i}.json"
                                                             for i in range(4)], None) if isinstance(d, dict)]
    return KS.je_kennung(teile, "wikifolio")


@st.cache_data(ttl=900, show_spinner=False)
def wikifolio_alle(tag):
    """Alle aktiven wikifolios mit Entwicklung und Kennzahlen (wikifolio_kennzahlen_N.json + Katalog-Score) -
    {} solange der Watchlist-Agent die Dateien noch nicht geschrieben hat. tag nur als Cache-Schluessel."""
    import wikifolio_liste as WL
    teile = [d for d in UI.parallel_lesen(gh_read_taeglich, [f"state/wikifolio_kennzahlen_{i}.json"
                                                             for i in range(4)], None)
             if isinstance(d, dict) and d.get("zeilen")]
    return WL.laden(teile, wikifolio_kennzahlen(tag)) if teile else {}


@st.cache_data(ttl=900, show_spinner=False)
def etf_alle(tag):
    """Alle ETFs mit Entwicklung, Kennzahlen und Merkmalen (etf_kennzahlen_N.json + Katalog-Score) - {} solange
    der Watchlist-Agent die Dateien noch nicht geschrieben hat. tag nur als Cache-Schluessel."""
    import klassen_score as KS
    import wikifolio_liste as WL
    teile = [d for d in UI.parallel_lesen(gh_read_taeglich, [f"state/etf_kennzahlen_{i}.json" for i in range(4)],
                                          None) if isinstance(d, dict) and d.get("zeilen")]
    if not teile:
        return {}
    katalog = [d for d in UI.parallel_lesen(gh_read_taeglich, [f"state/planer/katalog_gross_{i}.json"
                                                               for i in range(4)], None) if isinstance(d, dict)]
    return WL.laden(teile, KS.je_kennung(katalog, "etf"), art="etf")


def ist_wikifolio(wkn="", name=""):
    """True nur fuer wikifolio-Zertifikate. Die starten bei Auflegung immer bei
    100 € - ETFs (MSCI, Gold, Nasdaq ...) dagegen NICHT, dort waere ein
    100-€-Startpunkt schlicht falsch. Erkennung ueber die WKN: wikifolio-
    Zertifikate von Lang & Schwarz beginnen mit "LS9" (LS9VFS, LS9VSU,
    LS9VVK ...). Ersatzweise wird der Name geprueft, falls keine WKN
    hinterlegt ist (z.B. bei aus den Vergleichswerten uebernommenen Eintraegen).
    """
    text = f"{wkn or ''} {name or ''}".upper()
    return bool(re.search(r"\bLS9[A-Z0-9]{3}\b", text)) or "WIKIFOLIO" in text


def lade_auflegungen():
    """{instrument_id (str): {"datum": "YYYY-MM-DD", "kurs": 100.0}}
    Normale Benutzer: eigene Eintraege, ersatzweise die gemeinsamen (Auflegungsdaten
    sind Produktdaten - so rechnet die Prognose ohne eigene Angabe wie beim Admin)."""
    eigene = gh_read_cached(upfad(STATE_PATH_AUFLEGUNG), {}) or {}
    if not eigener_bereich():
        return eigene
    return auflegungen_zusammen(gh_read_cached(STATE_PATH_AUFLEGUNG, {}) or {}, eigene)


def auflegungen_zusammen(gemeinsam, eigene):
    """Eigene Auflegungsdaten vor den gemeinsamen."""
    aus = dict(gemeinsam) if isinstance(gemeinsam, dict) else {}
    if isinstance(eigene, dict):
        aus.update(eigene)
    return aus


def speichere_auflegung(instrument_id, datum, kurs=WIKIFOLIO_STARTKURS):
    """Merkt sich Auflegungsdatum und -kurs dauerhaft. datum=None loescht.
    Lesen-Aendern-Schreiben mit Versionspruefung (andere Instrumente bleiben erhalten)."""
    schluessel = str(instrument_id)

    def _a(daten):
        daten = dict(daten) if isinstance(daten, dict) else {}
        if datum is None:
            daten.pop(schluessel, None)
        else:
            daten[schluessel] = {"datum": datum.isoformat(), "kurs": float(kurs)}
        return daten

    ok, _ = gh_aktualisiere(upfad(STATE_PATH_AUFLEGUNG), _a, default={}, message="update auflegung [skip ci]")
    return ok


def auflegung_fuer(instrument_id):
    """(datum, kurs) des gespeicherten Auflegungspunkts, sonst (None, None)."""
    roh = lade_auflegungen().get(str(instrument_id))
    if not roh:
        return None, None
    try:
        if isinstance(roh, str):          # Altformat: nur das Datum
            return datetime.date.fromisoformat(roh), WIKIFOLIO_STARTKURS
        return (datetime.date.fromisoformat(roh["datum"]),
                float(roh.get("kurs", WIKIFOLIO_STARTKURS)))
    except Exception:
        return None, None


def hauptposition_werte(alle_positionen, eigen):
    """Kaufdatum, Kaufkurs und Kapital der Hauptposition aus EINER Quelle (Audit A-04/A-05).
    Admin / ohne Login: die gespeicherte erste Position (positionen.json), sofern sie das
    Hauptzertifikat ist; fehlende/ungueltige Felder und eine abweichende erste Position
    -> config.py. Normale Benutzer: Startkapital 0 (die config-Position gehoert dem Admin).
    -> {"kaufdatum", "kaufkurs", "startkapital", "abweichend"}"""
    werte = {"kaufdatum": config.KAUFDATUM, "kaufkurs": float(config.ANFANGSKURS),
             "startkapital": float(config.STARTKAPITAL), "abweichend": False}
    if eigen:
        werte["startkapital"] = 0.0
        return werte
    pos = alle_positionen[0] if alle_positionen and isinstance(alle_positionen[0], dict) else None
    if not pos:
        return werte
    if pos.get("instrument_id") and str(pos.get("instrument_id")) != str(config.LS_INSTRUMENT_ID):
        werte["abweichend"] = True          # erste Position ist ein anderes Papier
        return werte
    try:
        werte["kaufdatum"] = datetime.date.fromisoformat(str(pos["kaufdatum"]))
    except (KeyError, TypeError, ValueError):
        pass
    try:
        if float(pos.get("kaufkurs") or 0) > 0:
            werte["kaufkurs"] = float(pos["kaufkurs"])
    except (TypeError, ValueError):
        pass
    try:
        if pos.get("startkapital") is not None and float(pos["startkapital"]) >= 0:
            werte["startkapital"] = float(pos["startkapital"])
    except (TypeError, ValueError):
        pass
    return werte


def position_stueckzahl(pos):
    """Stueckzahl ergibt sich aus Startkapital / Kaufkurs - damit bleibt sie
    automatisch konsistent, wenn das Startkapital angepasst wird."""
    kaufkurs = float(pos.get("kaufkurs") or 0)
    if kaufkurs <= 0:
        return 0.0
    return float(pos.get("startkapital") or 0) / kaufkurs


def get_kurshistorie(instrument_id, start_date, end_date):
    """Tages-Schlusskurse einer beliebigen Instrument-ID als Series
    (Index=Datum). Basis fuer die Zeitraum-Kennzahlen - ersetzt das
    produktspezifische Scraping der wikifolio-Seite."""
    try:
        return historie_zuschnitt(lade_rohhistorie(instrument_id), start_date, end_date)
    except Exception as e:
        logging.error(f"Historie für Instrument {instrument_id} nicht ladbar: {e}")
    return pd.Series(dtype=float)


def produkt_rendite_pa(instrument_id, heute, daempfung=False,
                       auflage_datum=None, auflage_kurs=None, wkn="", name=""):
    """Robuste Renditeschaetzung fuer ein Instrument - EINE Stelle fuer alle
    Zukunfts-Hochrechnungen im Dashboard (100k-Meilenstein, Zukunfts-Prognose,
    Szenario-Simulator), damit dort ueberall dieselbe Zahl steht.

    Bewusst NICHT fuer realisierte Kennzahlen verwenden (Ø p.a. auf der
    Depotkachel, Vergleichstabellen, Zeitraum-Zeilen): die messen, was
    TATSAECHLICH passiert ist, und muessen am eigenen Kaufkurs bzw. am
    jeweiligen Zeitraum haengen.

    Laedt die komplette verfuegbare Historie (ab Listing) und nutzt als
    Bezugspunkt den letzten Schlusskurs, damit die Zahl ueber den Tag stabil
    bleibt. Gibt (rendite_pa, details) zurueck, oder (None, []) wenn die
    Historie zu duenn ist."""
    if not instrument_id:
        return None, []
    try:
        hist = get_kurshistorie(instrument_id, datetime.date(2000, 1, 1), heute)
        if hist is None or hist.empty:
            return None, []
        # Ohne ausdrueckliche Angabe: gespeichertes Auflegungsdatum verwenden.
        # Der Startkurs ist bei wikifolio-Zertifikaten immer 100 € - er muss
        # also nirgends eingetippt werden.
        # Gespeicherten Auflegungspunkt nur bei wikifolio-Zertifikaten
        # anwenden (Start immer 100 €). Werden wkn/name nicht mitgegeben,
        # greift der gespeicherte Eintrag - gespeichert wird er ohnehin nur
        # dort, wo die Eingabe angeboten wird.
        if auflage_datum is None:
            wkn_bekannt = bool(wkn or name)
            if not wkn_bekannt or ist_wikifolio(wkn, name):
                auflage_datum, gespeicherter_kurs = auflegung_fuer(instrument_id)
                if auflage_datum is not None and auflage_kurs is None:
                    auflage_kurs = gespeicherter_kurs
        return berechne_robuste_cagr(
            float(hist.iloc[-1]), hist, heute, daempfung=daempfung,
            auflage_datum=auflage_datum, auflage_kurs=auflage_kurs,
        )
    except Exception as e:
        logging.warning(f"Produkt-Rendite für Instrument {instrument_id} nicht ermittelbar: {e}")
        return None, []


def suche_instrument(suchbegriff):
    """Instrumentensuche auf ls-tc.de -> Trefferliste, [] bei Fehler. Fehler
    (Zeitueberschreitung, Sperre der Kursquelle) werden NICHT zwischengespeichert -
    sonst lieferte die Suche eine Stunde lang "nicht gefunden"."""
    if GH_STATE_READY and suchbegriff:
        gespeichert = kurs_vorrat().suche(suchbegriff)     # vom Kurs-Agenten vorab gesucht (Portfolio-Planer)
        if gespeichert is not None:
            return gespeichert
    try:
        return _suche_instrument_cache(suchbegriff)
    except Exception as e:
        logging.warning(f"Instrumentensuche für '{suchbegriff}' fehlgeschlagen: {e}")
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _suche_instrument_cache(suchbegriff):
    """Sucht auf ls-tc.de nach WKN, ISIN oder Name und gibt eine Liste von
    Treffern zurueck: [{"instrument_id", "name", "wkn", "isin", "kategorie"}].

    Nutzt den Such-Endpunkt der Seite, der pro Treffer bereits die
    'instrumentId' liefert - genau die ID, die die Kurs- und Historien-
    Endpunkte erwarten. 1 Std. Cache, da sich Stammdaten praktisch nie aendern.
    Bei Fehlern eine leere Liste, damit die manuelle Eingabe immer Fallback bleibt."""
    if not suchbegriff or not suchbegriff.strip():
        return []
    try:
        r = requests.get(
            KV.SUCH_URL,
            params={"q": suchbegriff.strip(), "localeId": "2"},
            headers=config.LS_TC_HEADERS, timeout=8,
        )
        r.raise_for_status()
        treffer = KV.suche_auswerten(r.json())
        return treffer
    except Exception as e:
        logging.warning(f"Instrumentensuche für '{suchbegriff}' fehlgeschlagen: {e}")
        raise          # Fehler nicht zwischenspeichern


def check_and_alert_fetch_failure(is_live_data, is_live_history):
    """Meldet per Discord, wenn Live-Kurs und/oder Chart-Historie gerade NICHT
    echt sind (und einmal, wenn sie wieder da sind). Abgesichert (Audit DATA-03):
    - nur mit lesbarem Zustand (sonst wuerde jede GitHub-Stoerung zum Dauer-Ping),
    - hoechstens ein Versuch je 30 Minuten (auch fehlgeschlagene Versuche zaehlen),
    - Versandergebnis wird geprueft, Zustand per Versionspruefung geschrieben.
    Kurs-Alarme verschickt die App NICHT mehr - das macht allein der Workflow."""
    if not DISCORD_WEBHOOK_URL or not GH_STATE_READY:
        return
    pfad = config.STATE_PATH_FETCH_FAIL_ALARM
    state, lesbar = gh_read_cached_status(pfad, {"last_alert": None, "war_down": False})
    if not lesbar or not isinstance(state, dict):
        return
    now = datetime.datetime.now(BERLIN_TZ)
    is_down = (not is_live_data) or (not is_live_history)
    war_down = bool(state.get("war_down", False))

    def _zeit(x):
        try:
            return datetime.datetime.fromisoformat(x) if x else None
        except Exception:
            return None
    letzte = [t for t in (_zeit(state.get("last_alert")), _zeit(state.get("letzter_versuch"))) if t]
    cooldown_ok = (not letzte) or ((now - max(letzte)).total_seconds() > 30 * 60)

    neu = {}
    if is_down and cooldown_ok:
        gesendet = _discord_senden(
            f"⚠️ **Datenquelle down ({config.WKN})**\n"
            f"ls-tc.de liefert gerade keine echten Live-/Chartdaten. Die App zeigt "
            f"gekennzeichnete Ersatzwerte und speichert/meldet nichts auf deren Basis.\n"
            f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}")
        neu["letzter_versuch"] = now.isoformat()
        if gesendet:
            neu["last_alert"] = now.isoformat()
    elif not is_down and war_down:
        if not _discord_senden(f"✅ **Datenquelle wieder OK ({config.WKN})** — ls-tc.de liefert wieder Live-Daten."):
            logging.warning("Entwarnung 'Datenquelle wieder OK' nicht zugestellt")
    if war_down != is_down:
        neu["war_down"] = is_down
    if neu:
        gh_aktualisiere(pfad, lambda d: dict(d if isinstance(d, dict) else {}, **neu),
                        default={"last_alert": None, "war_down": False},
                        message="update fetch fail alarm state [skip ci]")


def auswahl_kompakt(label, optionen, default=None, key=None, max_pills=6, **kw):
    """Wenige Optionen als Pillen (ein Tipp, alles sichtbar), viele als Auswahlfeld
    (Audit UX: 12-15 Pillen fuellten auf dem Handy mehr als eine Bildschirmhoehe,
    bevor der eigentliche Inhalt kam). Rueckgabe wie st.pills (gewaehlte Option)."""
    optionen = list(optionen)
    if len(optionen) <= max_pills:
        return st.pills(label, optionen, default=default, key=key, **kw)
    if key and st.session_state.get(key) not in optionen:
        st.session_state.pop(key, None)                 # z. B. Anzahl im Titel ueber Nacht geaendert
    idx = optionen.index(default) if default in optionen else 0
    return st.selectbox(label, optionen, index=idx, key=key, **kw)


def erstelle_ladeanzeige(platzhalter, phasen):
    """Eine EINZIGE, durchlaufende Ladeanzeige fuer den gesamten Seitenaufbau.

    Statt mehrerer nacheinander auftauchender Balken (die jeweils wieder bei
    0 % begannen und dadurch wie Stillstand wirkten) zaehlt hier ein einziger
    Wert von 0 auf 100. Jede Phase bekommt ein Gewicht entsprechend ihrem
    ungefaehren Zeitanteil; innerhalb einer Phase kann feiner gemeldet werden.

    phasen: [(schluessel, gewicht), ...] in Ausfuehrungsreihenfolge

    Rueckgabe: (melde, fertig)
        melde(schluessel, anteil=0.0, text="")  anteil = 0..1 innerhalb der Phase
        fertig()                                entfernt die Anzeige
    """
    gesamt_gewicht = sum(g for _, g in phasen) or 1
    versatz = {}
    laufend = 0
    for schluessel, gewicht in phasen:
        versatz[schluessel] = (laufend, gewicht)
        laufend += gewicht

    hoechster = {"pct": 0}
    beginn = time.monotonic()
    ANZEIGE_AB_SEK = 0.4      # kommt alles aus dem Zwischenspeicher, steht die Seite
                              # schneller - dann gar keinen Balken aufblitzen lassen

    def melde(schluessel, anteil=0.0, text=""):
        if time.monotonic() - beginn < ANZEIGE_AB_SEK:
            return
        start, gewicht = versatz.get(schluessel, (0, gesamt_gewicht))
        anteil = max(0.0, min(1.0, anteil))
        pct = int((start + gewicht * anteil) / gesamt_gewicht * 100)
        # Nie rueckwaerts laufen: ein zurueckspringender Balken wirkt wie ein
        # Fehler, auch wenn nur eine Phase uebersprungen wurde.
        pct = max(pct, hoechster["pct"])
        hoechster["pct"] = pct
        platzhalter.markdown(
            f'<div class="loading-overlay">'
            f'<div class="loading-pct">{pct} %</div>'
            f'<div class="loading-bar"><div class="loading-bar-fill" '
            f'style="width:{pct}%"></div></div>'
            f'<div class="loading-text">{_h(text)}</div></div>',
            unsafe_allow_html=True,
        )

    def fertig():
        platzhalter.empty()

    return melde, fertig


def fortschritt_anzeige(platzhalter):
    """Gibt eine Funktion zurueck, die einen zentrierten Ladebalken mit
    Prozentangabe in den uebergebenen Platzhalter zeichnet. Der Prozentwert
    bildet echte Arbeitsschritte ab (Netzabrufe), nicht bloss eine Animation.

    Verwendung:
        platz = st.empty()
        schritt = fortschritt_anzeige(platz)
        schritt(30, "Lade Kursdaten ...")
        ...
        platz.empty()
    """
    def zeichne(pct, text):
        platzhalter.markdown(
            f'<div class="loading-overlay">'
            f'<div class="loading-pct">{int(pct)} %</div>'
            f'<div class="loading-bar"><div class="loading-bar-fill" '
            f'style="width:{int(pct)}%"></div></div>'
            f'<div class="loading-text">{_h(text)}</div></div>',
            unsafe_allow_html=True,
        )
    return zeichne


# ---------------------------------------------------------------------------
# NAVIGATION: App-artige Kacheln statt Dropdown, ganz oben auf der Seite.
# Beim Aufruf ist noch nichts gewaehlt (Startseite = nur Kacheln, nichts wird
# geladen). Kurse werden nach Zeitplan aktualisiert: taeglich ab 9 Uhr alle
# 2 Stunden (9, 11, 13 ... 23 Uhr) - oder sofort per "Aktualisieren".
# ---------------------------------------------------------------------------
AKTUALISIERUNG_START = 9            # erste Aktualisierung am Tag (Uhr)
AKTUALISIERUNG_TAKT = 2             # danach alle x Stunden
AKTUALISIERUNG_ENDE = 23            # letzte Aktualisierung am Tag
NAV_PRUEF_SEK = 15 * 60             # offene Seite prueft alle 15 Min., ob ein Termin faellig ist

ANSICHT_DEPOT = "🏠 Depot"
ANSICHT_EINST = "⚙️ Einstellungen"   # interner Schluessel (Freigaben je Benutzer) - angezeigt: "Depot verwalten"
ANSICHT_MUSTER = "📦 Musterdepot"    # aus dem Portfolio-Planer erstellt - Button nur, wenn eines existiert
ANSICHT_ABFINDUNG = "💶 Abfindungsrechner"
ANSICHT_ZINS = "🧮 Zinseszinsrechner"
ANSICHT_BENUTZER = "👥 Benutzer"      # nur fuer den Admin sichtbar
ANSICHT_BUILDER = "🚀 Portfolio Builder 2.0"
ANSICHT_SCANNER = "🤖 Investment-Scanner"
ANSICHT_SCANNER_PRO = "🔎 Investment Scanner Pro"
ANSICHT_SCANNER2 = "🧭 Investment Scanner 2.0"
ANSICHT_ANALYSE = "🧠 Depot-Analyse & Optimierung"
ANSICHT_ANALYSE_DEPOT = "📥 Analyse-Depot"
ANSICHT_BEWERTUNG = "⚖️ Bewertung"
ANSICHT_ATZ = "🏖️ Altersteilzeit & Rente"
ANSICHT_WIKI = "💹 KI_Invest_System"
ANSICHT_EKS = "🎯 EKS-Investmentbewertung"
ANSICHT_GLOSSAR = "📖 Begriffe"         # Fachbegriffe erklaert (glossar.py) - fuer alle sichtbar
ANSICHT_GESUNDHEIT = "❤️ Gesundheit"     # gesundheit_ui.py - Gesundheitsdaten, NUR fuer den Admin
ANSICHT_KO = "🎯 Knock-out-Rechner"      # ko_rechner_ui.py - Index-Knock-out-Gewinnrechner, fuer alle
ANSICHT_ETP = "📈 ETF-/ETP-Hebelrechner"  # etp_rechner_ui.py - taeglich gehebelte Produkte, fuer alle
ANSICHT_FG = "🌡️ Fear & Greed"           # fear_greed_ui.py - Marktstimmung, fuer alle
ANSICHT_GAP = "🕳️ Gap Analyzer"          # gap_analyzer_ui.py - Kursluecken der vier Indizes, fuer alle
ANSICHT_PYR = "🔺 Pyramiden"             # pyramide_ui.py - Pyramidenmanager, fuer alle (Daten je Benutzer)
ANSICHT_YT = "🎬 Faceless YouTube"       # youtube_ui.py - Faceless YouTube Automation, nur Admin
ANSICHT_DK = "🧮 Durchschnittskurs-Rechner"   # durchschnittskurs_ui.py - gewichteter Einkaufskurs, fuer alle
APP_URL = "https://zzvuvqwe6.streamlit.app"     # fuer Permanentlinks, falls die Adresse nicht ermittelbar ist
# Permanentlinks: ?ansicht=<kuerzel> oeffnet direkt die Ansicht
ANSICHT_LINKS = {"zins": ANSICHT_ZINS, "abfindung": ANSICHT_ABFINDUNG, "rente": ANSICHT_ATZ,
                 "durchschnittskurs": ANSICHT_DK}
PFAD_MUSTERDEPOT = "state/musterdepot.json"
ANSICHTEN = [
    ANSICHT_DEPOT,
    ANSICHT_EINST,
    ANSICHT_MUSTER,
    "📈 Vermögens- & Substanzaufbau",
    "🔍 Seit 01.01.2026",
    "🔎 Seit 01.01.2021",
    "🕯️ Tages-Candlestick",
    "🔮 Zukunfts-Prognose",
    "📊 Szenario-Simulator (5 Jahre)",
    "💼 Portfolio-Planer",
    "📝 Trader-Log (Trades & Kommentare)",
    "🏆 Watchlist Top 50",
    ANSICHT_ABFINDUNG,          # immer ans Ende: die Kachel-Keys haengen am Index
    ANSICHT_ZINS,
    ANSICHT_BENUTZER,
    ANSICHT_BUILDER,            # neu: hinten anhaengen, damit die Kachel-Keys der anderen gleich bleiben
    ANSICHT_SCANNER,
    ANSICHT_SCANNER_PRO,
    ANSICHT_SCANNER2,           # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_ANALYSE,
    ANSICHT_ANALYSE_DEPOT,
    ANSICHT_BEWERTUNG,          # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_ATZ,
    ANSICHT_WIKI,               # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_EKS,                # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_GLOSSAR,            # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_GESUNDHEIT,         # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_KO,                 # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_ETP,                # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_FG,                 # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_GAP,                # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_PYR,                # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_YT,                 # hinten anhaengen (Kachel-Keys haengen am Index)
    ANSICHT_DK,                 # hinten anhaengen (Kachel-Keys haengen am Index)
]
ANSICHT_KURZ = {
    ANSICHT_DEPOT: "🏠 Depot",
    ANSICHT_EINST: "🛠️ Depot verwalten",
    "📈 Vermögens- & Substanzaufbau": "📈 Vermögen",
    "🔍 Seit 01.01.2026": "🔍 Seit 2026",
    "🔎 Seit 01.01.2021": "🔎 Seit 2021",
    "🕯️ Tages-Candlestick": "🕯️ Candles",
    "🔮 Zukunfts-Prognose": "🔮 Prognose",
    "📊 Szenario-Simulator (5 Jahre)": "📊 Szenarien",
    "💼 Portfolio-Planer": "💼 Planer",
    "📝 Trader-Log (Trades & Kommentare)": "📝 Chronik",
    "🏆 Watchlist Top 50": "🏆 Ranglisten",
    ANSICHT_MUSTER: "📦 Muster",
    ANSICHT_ABFINDUNG: "💶 Abfindung",
    ANSICHT_ZINS: "🧮 Zinsen",
    ANSICHT_BENUTZER: "👥 Benutzer",
    ANSICHT_BUILDER: "🚀 Builder 2.0",
    ANSICHT_SCANNER: "🤖 Scanner",
    ANSICHT_SCANNER_PRO: "🔎 Scanner Pro",
    ANSICHT_SCANNER2: "🧭 Scanner 2.0",
    ANSICHT_ANALYSE: "🧠 Depot-Analyse",
    ANSICHT_ANALYSE_DEPOT: "📥 Analyse-Depot",
    ANSICHT_BEWERTUNG: "⚖️ Bewertung",
    ANSICHT_ATZ: "🏖️ Altersteilzeit",
    ANSICHT_WIKI: "💹 KI_Invest_System",
    ANSICHT_EKS: "🎯 EKS-Bewertung",
    ANSICHT_GLOSSAR: "📖 Begriffe",
    ANSICHT_GESUNDHEIT: "❤️ Gesundheit",
    ANSICHT_KO: "🎯 Knock-out",
    ANSICHT_ETP: "📈 ETP-Hebel",
    ANSICHT_FG: "🌡️ Fear & Greed",
    ANSICHT_GAP: "🕳️ Gaps",
    ANSICHT_PYR: "🔺 Pyramiden",
    ANSICHT_YT: "🎬 YouTube",
    ANSICHT_DK: "🧮 Ø-Kurs",
}
# Anzeigenamen in Menue und Kopfleiste (die internen Schluessel bleiben gleich)
NAV_NAMEN = {
    ANSICHT_DEPOT: "🏠 Test-Depot",
    ANSICHT_EINST: "🛠️ Depot verwalten",
    "📝 Trader-Log (Trades & Kommentare)": "📝 Chronik",
    "📈 Vermögens- & Substanzaufbau": "📈 Vermögensaufbau",
    "🔍 Seit 01.01.2026": "🔍 Performance > 2026",
    "🔎 Seit 01.01.2021": "🔎 Performance > 2021",
    "🕯️ Tages-Candlestick": "🕯️ Candlestick (Tag)",
    "🔮 Zukunfts-Prognose": "🔮 Zukunfts-Prognose",
    "📊 Szenario-Simulator (5 Jahre)": "📊 Szenario-Simulator",
    "💼 Portfolio-Planer": "💼 Portfolio-Planer",
    ANSICHT_BUILDER: "🚀 Portfolio Builder 2.0",
    ANSICHT_SCANNER: "🤖 Investment-Scanner",
    ANSICHT_SCANNER_PRO: "🔎 Investment Scanner Pro",
    ANSICHT_SCANNER2: "🧭 Investment Scanner 2.0",
    ANSICHT_ANALYSE: "🧠 Depot-Analyse",          # Kachel: kurz, voller Name in der Kopfleiste (NAV_TITEL)
    ANSICHT_ANALYSE_DEPOT: "📥 Analyse-Depot",
    ANSICHT_BEWERTUNG: "⚖️ Bewertung",
    "🏆 Watchlist Top 50": "🏆 Ranglisten & Screener",
    ANSICHT_MUSTER: "📦 Musterdepot",
    ANSICHT_ABFINDUNG: "💶 Abfindungsrechner",
    ANSICHT_ZINS: "🧮 Zinseszinsrechner",
    ANSICHT_ATZ: "🏖️ Altersteilzeit & Rente",
    ANSICHT_WIKI: "💹 KI_Invest_System (wikifolio)",
    ANSICHT_EKS: "🎯 EKS-Bewertung",
    ANSICHT_GLOSSAR: "📖 Begriffe",
    ANSICHT_GESUNDHEIT: "❤️ Gesundheit",
    ANSICHT_KO: "🎯 Knock-out-Rechner",
    ANSICHT_ETP: "📈 ETF-/ETP-Hebelrechner",
    ANSICHT_FG: "🌡️ Fear & Greed Monitor",
    ANSICHT_GAP: "🕳️ Gap Analyzer",
    ANSICHT_PYR: "🔺 Pyramidenmanager",
    ANSICHT_YT: "🎬 Faceless YouTube Automation",
    ANSICHT_DK: "🧮 Durchschnittskurs-Rechner",
    ANSICHT_BENUTZER: "👥 Benutzer",
}
# Ausfuehrlicher Titel in der Kopfleiste (dort ist mehr Platz als auf der Kachel)
NAV_TITEL = {
    ANSICHT_ANALYSE: "🧠 Depot-Analyse & Optimierung",
    ANSICHT_BEWERTUNG: "⚖️ Bewertung (Top 500)",
    ANSICHT_ATZ: "🏖️ Altersteilzeit & Rentenplanung",
    ANSICHT_EKS: "🎯 EKS-Investmentbewertung",
    ANSICHT_GLOSSAR: "📖 Begriffe erklärt",
    "🔍 Seit 01.01.2026": "🔍 Performance seit 01.01.2026",
    "🔎 Seit 01.01.2021": "🔎 Performance seit 01.01.2021",
}
# Menue-Gruppen (Ueberschrift, Ansichten) - je Zeile zwei Buttons
NAV_FARBEN = {}   # leer = einheitlich Neon-Weiss; je Gruppe eine Farbe moeglich, z. B. {"Depot": "#22D3EE"}
# Sammel-Kacheln (Audit UX-02): verwandte Ansichten teilen sich EINE Menue-Kachel; in der Ansicht schaltet eine
# Leiste unter der Kopfzeile zwischen ihnen um. Die Ansichten selbst (Schluessel, Rechte, Links) bleiben unveraendert.
NAV_GRUPPEN = {
    "📈 Charts": ["📈 Vermögens- & Substanzaufbau", "🔍 Seit 01.01.2026", "🔎 Seit 01.01.2021", "🕯️ Tages-Candlestick"],
    "💼 Portfolio-Werkzeuge": [ANSICHT_BUILDER, "💼 Portfolio-Planer", ANSICHT_MUSTER],
    "🔎 Investment-Scanner": [ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2],
}
NAV_GRUPPE_KEY = {"📈 Charts": "charts", "💼 Portfolio-Werkzeuge": "portfolio", "🔎 Investment-Scanner": "scanner"}
NAV_ZEILEN = [
    ("Depot", [ANSICHT_DEPOT, ANSICHT_WIKI, "📈 Charts", ANSICHT_ANALYSE, ANSICHT_ANALYSE_DEPOT,
               "📝 Trader-Log (Trades & Kommentare)", ANSICHT_EINST]),
    ("Planung & Analyse", ["🔮 Zukunfts-Prognose", "📊 Szenario-Simulator (5 Jahre)", "💼 Portfolio-Werkzeuge",
                           "🔎 Investment-Scanner", "🏆 Watchlist Top 50", ANSICHT_BEWERTUNG]),
    ("Märkte", [ANSICHT_FG, ANSICHT_GAP, ANSICHT_PYR]),             # Marktstimmung und Index-Werkzeuge
    ("Geschäftsideen", [ANSICHT_EKS, ANSICHT_YT]),      # eigene Gruppe - weitere Werkzeuge fuer Geschaeftsideen hier anhaengen
    ("Rechner", [ANSICHT_ABFINDUNG, ANSICHT_ZINS, ANSICHT_ATZ, ANSICHT_KO, ANSICHT_ETP, ANSICHT_DK]),
    ("Gesundheit", [ANSICHT_GESUNDHEIT]),
    ("Hilfe", [ANSICHT_GLOSSAR]),
    ("Verwaltung", [ANSICHT_BENUTZER]),
]
# Ansichten ohne Depot-/Kursdaten: dort wird gar nichts vom Depot geladen
LEICHTE_ANSICHTEN = {ANSICHT_ANALYSE_DEPOT, "💼 Portfolio-Planer", ANSICHT_BUILDER, ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2, "🏆 Watchlist Top 50", ANSICHT_MUSTER, ANSICHT_ABFINDUNG, ANSICHT_ZINS,
                     "📝 Trader-Log (Trades & Kommentare)",
                     ANSICHT_BENUTZER, ANSICHT_BEWERTUNG, ANSICHT_ATZ, ANSICHT_WIKI, ANSICHT_EKS, ANSICHT_GLOSSAR,
                     ANSICHT_GESUNDHEIT, ANSICHT_KO, ANSICHT_ETP, ANSICHT_FG, ANSICHT_GAP, ANSICHT_PYR, ANSICHT_YT,
                     ANSICHT_DK}

# Ansichten mit breiten Tabellen: duerfen auf grossen Monitoren breiter werden als UI.INHALT_MAX
BREITE_ANSICHTEN = {"🏆 Watchlist Top 50", ANSICHT_WIKI, ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2, ANSICHT_BENUTZER}

# Ansichten ohne Live-Kurse (Ranglisten der Agenten, Rechner, Verwaltung) - dort keine Kursstand-Zeile
OHNE_KURSE = {"🏆 Watchlist Top 50", ANSICHT_ABFINDUNG, ANSICHT_ZINS, ANSICHT_BENUTZER,
              "📝 Trader-Log (Trades & Kommentare)", ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2,
              ANSICHT_BEWERTUNG, ANSICHT_ATZ, ANSICHT_WIKI, ANSICHT_EKS, ANSICHT_GLOSSAR, ANSICHT_GESUNDHEIT,
              ANSICHT_KO, ANSICHT_ETP, ANSICHT_FG, ANSICHT_GAP, ANSICHT_PYR, ANSICHT_YT, ANSICHT_DK}

NAV_CSS = UI.CSS_NAV

# Ansichten, die die Prognose-Basis (Beobachtungswerte mit voller Kurshistorie) brauchen
PROGNOSE_ANSICHTEN = {"🔮 Zukunfts-Prognose", "📊 Szenario-Simulator (5 Jahre)"}


def _termine(tag):
    """Aktualisierungstermine eines Tages in Berliner Zeit. Wichtig: pytz-Zonen
    per localize() setzen - tzinfo=BERLIN_TZ ergaebe die historische Ortszeit
    (+00:53) und verschoebe alle Termine um rund eine Stunde."""
    aus = []
    for h in range(AKTUALISIERUNG_START, AKTUALISIERUNG_ENDE + 1, AKTUALISIERUNG_TAKT):
        naiv = datetime.datetime.combine(tag, datetime.time(h))
        aus.append(BERLIN_TZ.localize(naiv) if hasattr(BERLIN_TZ, "localize") else naiv.replace(tzinfo=BERLIN_TZ))
    return aus


def letzter_termin(jetzt):
    """Letzter faelliger Aktualisierungstermin (vor 9 Uhr: gestern 23 Uhr)."""
    heute = [t for t in _termine(jetzt.date()) if t <= jetzt]
    return heute[-1] if heute else _termine(jetzt.date() - datetime.timedelta(days=1))[-1]


def naechster_termin(jetzt):
    spaeter = [t for t in _termine(jetzt.date()) if t > jetzt]
    return spaeter[0] if spaeter else _termine(jetzt.date() + datetime.timedelta(days=1))[0]


def _nach_kurslauf():
    """Nach jedem Hintergrund-Lauf: aus Kursen abgeleitete Zwischenspeicher verwerfen
    (sie rechnen beim naechsten Aufruf aus den neuen Kursen im Speicher, ohne Netzabruf)."""
    try:
        import planer_ui
        planer_ui._hist_eines_cache.clear()
    except Exception:
        pass


# --- KURS-AGENT (kurs_agent.py, GitHub Action alle 30 Min.): legt alle Kurse im Datenspeicher ab ---
# Die App liest beim Seitenaufbau nur diesen Vorrat. Der eigene Lauf der App (Zeitplan unten) springt nur
# noch ein, wenn der Agent laenger ausfaellt (AGENT_MAX_ALTER_MIN).
AGENT_MAX_ALTER_MIN = 75
AGENT_UTC_STUNDEN = range(5, 22)        # wie .github/workflows/kurse.yml: werktags 05:00-21:30 UTC
NACHLADEN_WARTEN_SEK = 2.0              # Wert fehlt im Vorrat: im Hintergrund laden, hoechstens so lange warten


@st.cache_resource(show_spinner=False)
def kurs_vorrat():
    """Gespeicherte Kurse des Kurs-Agenten (live 2 Min., Historien 15 Min. im Speicher)."""
    return KV.Vorrat(lambda pfad: gh_read_streng(pfad, None))


def _aus_vorrat(vorrat, art, instrument_id):
    """(wert, abgerufen_um) aus dem Vorrat im Format des Kursdienstes - oder None."""
    if art == "live":
        e = vorrat.live(instrument_id)
        if e is None:
            return None
        eintrag, zeit = e
        hist = None
        if not eintrag.get("p"):                     # ohne Vortageskurs: aus der Historie
            h = vorrat.historie(instrument_id)
            hist = h[0] if h else None
        return ls_tc_live_auswerten(KV.live_antwort(eintrag, hist)), zeit
    return vorrat.historie(instrument_id)            # "historie" und "benchmark": dieselbe Tageshistorie


def agent_aktuell(stand, jetzt):
    return KV.aktuell(stand, jetzt, AGENT_MAX_ALTER_MIN)


def naechster_agent_lauf(jetzt):
    return KV.naechster_lauf(jetzt, AGENT_UTC_STUNDEN)


def _kurslauf_faellig(seit, vorrat=None):
    """Ist seit dem letzten Lauf (bzw. dem Start der App) ein Termin (9, 11, 13 … 23 Uhr) vergangen - und
    liefert der Kurs-Agent gerade nicht? (Sonst haelt er die Kurse aktuell, die App ruft nichts ab.)"""
    jetzt = datetime.datetime.now(BERLIN_TZ)
    if not seit < letzter_termin(jetzt):
        return False
    return vorrat is None or not agent_aktuell(vorrat.stand(), jetzt)


@st.cache_resource(show_spinner=False)
def kurs_dienst():
    """EIN Kursdienst je App-Prozess (fuer alle Sitzungen): liest die Kurse aus dem Vorrat des Kurs-Agenten,
    haelt sie im Speicher und laedt Fehlendes im Hintergrund nach - niemand wartet beim Seitenaufbau auf
    Kursabrufe. Ohne Datenspeicher (lokal) wie bisher: fehlende Werte sofort abrufen."""
    vorrat = kurs_vorrat() if GH_STATE_READY else None
    d = KD.KursDienst({"live": _live_roh, "historie": _historie_roh, "benchmark": _benchmark_netz},
                      jetzt=lambda: datetime.datetime.now(BERLIN_TZ), nach_lauf=_nach_kurslauf,
                      vorrat=(lambda art, iid: _aus_vorrat(vorrat, art, iid)) if vorrat else None,
                      wartezeit=NACHLADEN_WARTEN_SEK if vorrat else None)
    d.vorrat = vorrat
    # Kein Lauf beim Start der App bzw. bei der Anmeldung - der erste kommt zum naechsten Termin
    d.gestartet = datetime.datetime.now(BERLIN_TZ)
    d.merken("live", config.LS_INSTRUMENT_ID)            # Hauptposition und Standard-Vergleichswerte
    d.merken("historie", config.LS_INSTRUMENT_ID)        # gleich beim ersten Lauf mitladen
    for iid in (getattr(config, "BENCHMARKS", None) or {}).values():
        d.merken("live", iid)
        d.merken("benchmark", iid)
    return d


def ranglisten_stand(daten):
    """Stand der taeglichen Ranglisten als Text - mit Hinweis, wenn der Lauf von heute noch aussteht."""
    try:
        t = datetime.datetime.fromisoformat(daten["stand"])
    except Exception:
        return str((daten or {}).get("stand", "–"))
    text = t.strftime("%d.%m.%Y, %H:%M Uhr")
    if t.date() < datetime.datetime.now(BERLIN_TZ).date():
        text += " (die Aktualisierung von heute steht noch aus)"
    return text


def kurs_dienst_bereit():
    """Kursdienst holen und sicherstellen, dass sein Zeitplan laeuft (auch nach einem Absturz)."""
    d = kurs_dienst()
    if not d.zeitplan_aktiv():
        d.zeitplan_starten(lambda letzter: _kurslauf_faellig(letzter or d.gestartet, d.vorrat))
    return d


def kurse_neu_laden():
    """Einen Hintergrund-Lauf starten. -> False, wenn schon einer laeuft."""
    st.session_state.pop("planer_hist", None)      # gemerkte Planer-Historie dieser Sitzung
    return kurs_dienst_bereit().aktualisieren()


# --- GEMERKTE RECHNER-EINGABEN (je Benutzer, nutzerdaten.eingaben_*) ---
# Bereich -> (Schluessel-Praefix, nicht zu merkende Schluessel). Gemerkt werden nur
# einfache Werte; interne/fluechtige Schluessel (Init-Merker, berechnete Anzeige-
# felder, Tabellen-Editoren, Knoepfe, PDF, Container) bleiben aussen vor.
RECHNER_EINGABEN = {
    "zinsrechner": ("zr_", re.compile(r"^zr_init$|^zr_dis_|_tab_|_ver$|_neu$|_an$|_pdf$|_chart$|^zr_sd_d$|_[jb]_\d+_\d+$|_del_|_leeren$|_leer$"
                                      r"|_karte|_form$")),
    "abfindung": ("abf_", re.compile(r"_tab_|^abf_fj|_pdf$|_karte|_form$|^abf_av_betrag$|_btn$|^abf_nav$"
                                     r"|^abf_mo_wahl$|^abf_sp_nav$")),
    # Knock-out-Rechner: je Index ko_<INDEX>_...; Spiegel-Widgets (_s/_n/_d), Knoepfe und Sitzungswerte nicht merken
    "ko_rechner": ("ko_", re.compile(r"_[snd]$|_q\d+$|_btn$|_auswahl$|_speichern$|_auto$|_abruf$|^ko_(csv|reset|frisch|meldung"
                                     r"|refresh_zeit|stand_gesehen|fx_ziel)$")),
    # ETF-/ETP-Hebelrechner: wie der Knock-out-Rechner je Basiswert etp_<CODE>_...
    "etp_rechner": ("etp_", re.compile(r"_[snd]$|_btn$|_auswahl$|_speichern$|_auto$|_abruf$|_chart$|^etp_(csv|csv_diag|reset"
                                       r"|meldung|bt_von_d|bt_bis_d)$")),
    # Fear & Greed Monitor: Auswahl, Warnregeln und gesehene Warnungen merken; Knoepfe/Sitzungswerte nicht
    "fear_greed": ("fg_", re.compile(r"_btn$|_editor$|_chart$|^fg_(frisch|meldung|refresh_zeit|stand_gesehen)$")),
    # Durchschnittskurs-Rechner: Kaeufe (als JSON-Text), Name, Waehrung, Gebuehren, Nachkauf-Felder; Tabelle/Knoepfe nicht
    "durchschnittskurs": ("dk_", re.compile(r"^dk_tab_|^dk_ver$|_btn$|^dk_meldung$")),
    # Gap Analyzer: Definition, Zeitraum, Filter, Alerts und gesehene Meldungen merken
    "gap_analyzer": ("gap_", re.compile(r"_btn$|^gap_tab_|^gap_csv|^gap_xlsx|^gap_chart$|_weg$|^gap_reihe_|_tab$")),
}


def eingaben_sammeln(session_state, prefix, ausnahmen=None):
    """Einfache Werte (Zahl, Text, Bool, None) aller Schluessel mit diesem Praefix."""
    werte = {}
    for k in list(session_state.keys()):
        k = str(k)
        if not k.startswith(prefix) or (ausnahmen is not None and ausnahmen.search(k)):
            continue
        v = session_state[k]
        if v is None or isinstance(v, (bool, int, float, str)):
            werte[k] = v
    return werte


def rechner_vorbelegen(bereich):
    """Gemerkte Eingaben (Datei, ersatzweise neuere Werte dieser Sitzung) vor dem
    Zeichnen der Felder einsetzen. -> dict der bekannten Werte (fuer render)."""
    gespeichert = {}
    if GH_STATE_READY:
        try:
            gespeichert = nutzerdaten.eingaben_laden(gh_read_cached, _nutzer(), bereich)
        except Exception:
            gespeichert = {}
    sitzung = (st.session_state.get(f"_eingaben_{bereich}_offen")
               or (st.session_state.get(f"_eingaben_{bereich}") or {}).get("werte"))
    if sitzung:
        gespeichert = dict(gespeichert, **sitzung)
    nutzerdaten.eingaben_vorbelegen(st.session_state, gespeichert, {k: k for k in gespeichert})
    return gespeichert


def rechner_merken(bereich, sofort=False):
    """Nach dem Zeichnen: geaenderte Eingaben fuer die naechste Anmeldung merken
    (hoechstens alle nutzerdaten.MIN_ABSTAND_SEK, nur bei Aenderung)."""
    if not GH_STATE_READY or bereich not in RECHNER_EINGABEN:
        return False
    prefix, ausnahmen = RECHNER_EINGABEN[bereich]
    werte = eingaben_sammeln(st.session_state, prefix, ausnahmen)
    merk = f"_eingaben_{bereich}"
    if merk not in st.session_state:
        # Ausgangsstand dieser Sitzung (Gemerktes bzw. Standard) - noch nichts zu speichern;
        # zeit 0: die erste echte Aenderung wird sofort gespeichert
        st.session_state[merk] = {"werte": nutzerdaten._sauber(werte), "zeit": 0}
        return False
    vorher = (st.session_state.get(merk) or {}).get("werte")
    try:
        ok = nutzerdaten.eingaben_merken(gh_aktualisiere, st.session_state, _nutzer(), bereich, werte,
                                         sofort=sofort)
    except Exception as e:
        logging.warning(f"Eingaben '{bereich}' nicht gemerkt: {type(e).__name__}")
        ok = False
    # Statuszeile/Rueckgaengig (speicherleiste): gespeichert -> alten Stand merken; gedrosselt -> "ungespeichert"
    if ok:
        SL.gespeichert(st.session_state, "rechner_" + bereich, vorher)
    elif st.session_state.get(merk + "_offen") is not None:
        SL.geaendert(st.session_state, "rechner_" + bereich)
    return ok


def rechner_rueckgaengig(bereich):
    """Letzte Speicherung der Rechner-Eingaben zuruecknehmen: nur dieser Bereich der Eingaben-Datei wird auf den
    vorherigen Stand gesetzt, die Felder ebenso (Callback - laeuft vor dem Zeichnen der Felder)."""
    z = SL.zustand(st.session_state, "rechner_" + bereich)
    if not z["stapel"] or not GH_STATE_READY:
        return
    stand = z["stapel"][-1]

    def aendern(daten):
        daten = daten if isinstance(daten, dict) else {}
        daten[bereich] = stand
        return daten
    try:
        ok, _ = gh_aktualisiere(nutzerdaten.eingaben_pfad(_nutzer()), aendern, default={},
                                message=f"eingaben {bereich} rückgängig [skip ci]")
    except Exception:
        ok = False
    if not ok:
        SL.fehlgeschlagen(st.session_state, "rechner_" + bereich)
        return
    z["stapel"].pop()
    for k, v in stand.items():
        st.session_state[k] = v
    st.session_state[f"_eingaben_{bereich}"] = {"werte": stand, "zeit": time.time()}
    st.session_state.pop(f"_eingaben_{bereich}_offen", None)
    SL.gespeichert(st.session_state, "rechner_" + bereich, merken=False)


def rechner_leiste(bereich):
    """Statuszeile am Ende des Rechners (automatisches Speichern, Rueckgaengig)."""
    if GH_STATE_READY:
        SL.leiste(st, "rechner_" + bereich, rueck=lambda: rechner_rueckgaengig(bereich),
                  hinweis="Eingaben werden automatisch gespeichert")
    else:
        SL.leiste(st, "rechner_" + bereich, modus="sitzung")


# Eingaben ohne eigene Datei (Zukunfts-Prognose, Simulation): Streamlit loescht Widget-Werte,
# sobald ihre Ansicht nicht gezeichnet wird. Je Sitzung gemerkt und beim naechsten Anlegen des
# Felds als Startwert eingesetzt; Knoepfe und das gespeicherte Auflegungsdatum bleiben aussen vor.
SITZUNG_EINGABEN = re.compile(r"^(prognose_rate_|prognose_wert_wahl$|mc_jahre$|mc_shrinkage$|szenario_|wk2_|etf2_)"
                              r"(?!(.*_)?(aufl|del|save)_)")


def sitzung_eingaben_merken(session_state):
    """Zu Beginn jedes Laufs - solange die Felder noch bestehen - ihre Werte merken."""
    merk = session_state.setdefault("_sitzung_eingaben", {})
    for k in list(session_state.keys()):
        k = str(k)
        if SITZUNG_EINGABEN.match(k):
            merk[k] = session_state[k]


def _startwert(key, standard):
    """Startwert eines Felds: der in dieser Sitzung gemerkte, sonst die Vorbelegung. Immer
    mitgeben: legt der Browser das Feld neu an, zeigt er sonst den Mindestwert, waehrend der
    Server noch den alten Wert haelt (die Felder sind ueber ihren Key identifiziert)."""
    return {"value": (st.session_state.get("_sitzung_eingaben") or {}).get(key, standard)}


def _startauswahl(key, optionen):
    """Wie _startwert fuer Auswahlfelder: gemerkter Eintrag, falls es ihn noch gibt."""
    gemerkt = (st.session_state.get("_sitzung_eingaben") or {}).get(key)
    if gemerkt not in optionen:
        return {}
    return {"index": list(optionen).index(gemerkt)}


def eingaben_offene_speichern():
    """Zurueckgehaltene (gedrosselte) Eingaben sofort speichern - beim Verlassen
    einer Ansicht und beim Abmelden."""
    if not GH_STATE_READY:
        return
    for bereich in RECHNER_EINGABEN:
        offen = st.session_state.get(f"_eingaben_{bereich}_offen")
        if offen is None:
            continue
        try:
            vorher = (st.session_state.get(f"_eingaben_{bereich}") or {}).get("werte")
            if nutzerdaten.eingaben_merken(gh_aktualisiere, st.session_state, _nutzer(), bereich, offen, sofort=True):
                SL.gespeichert(st.session_state, "rechner_" + bereich, vorher)
        except Exception as e:
            logging.warning(f"Offene Eingaben '{bereich}' nicht gespeichert: {type(e).__name__}")


def _ko_uebernehmen(w):
    """ETP-Rechner -> Knock-out-Rechner: Basiswert, Einsatz, Kursziel, Zieltermin, Richtung und Hebel uebernehmen
    (Schluessel wie ko_rechner_ui; die Spiegel-Widgets werden neu angelegt) und dorthin wechseln."""
    s = st.session_state
    c = w["index"]
    s["ko_index"] = c
    for feld in ("einsatz", "ziel", "hebel"):
        s[f"ko_{c}_{feld}"] = float(w[feld])
        for zusatz in ("_s", "_n"):
            s.pop(f"ko_{c}_{feld}{zusatz}", None)
    if w.get("termin"):
        s[f"ko_{c}_termin"] = w["termin"].isoformat()
        s.pop(f"ko_{c}_termin_d", None)
    s[f"ko_{c}_richtung"] = w["richtung"]
    if w["hebel"] > 10:
        s[f"ko_{c}_erweitert"] = True
    _nav_waehle(ANSICHT_KO)


def _nav_waehle(ansicht):
    eingaben_offene_speichern()
    st.session_state["ansicht_aktiv"] = ansicht
    # ein Permanentlink gilt nur fuer seine Ansicht - beim Wechsel aus der Adresse entfernen
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.session_state.pop("zr_init", None)
    st.session_state.pop("q_fokus", None)        # Qualitaets-Tabelle startet immer mit "Alle Kennzahlen"


def _zur_bewertung(eintrag):
    """Bewertungsseite mit diesem Wert oeffnen (aus der Depot-Analyse)."""
    import bewertung_ui
    bewertung_ui.oeffnen(eintrag)
    _nav_waehle(ANSICHT_BEWERTUNG)


def _nutzer():
    return st.session_state.get("_nutzer")


@st.cache_resource
def _depot_kurzinfo_speicher():
    """Je Benutzer die zuletzt in der Depot-Ansicht berechnete Summe - nur im Speicher des App-Prozesses.
    Die Startseite zeigt sie an, ohne selbst Kurse abzurufen ("Nie die Daten direkt beim Login laden")."""
    return {}


def depot_kurzinfo_merken(info):
    _depot_kurzinfo_speicher()[st.session_state.get("login_name") or "_"] = info


def depot_kurzinfo_karte(jetzt):
    """Kleine Depot-Karte ueber dem Menue: Gesamtwert, Gewinn/Verlust seit Kauf, Tag - aus dem Speicher.
    Gibt es noch keinen Stand (erste Anmeldung seit dem Start der App), entfaellt sie. Ins Depot fuehrt die
    Depot-Kachel im Menue darunter (ein eigener Knopf hier war doppelt)."""
    if not _sichtbar(ANSICHT_DEPOT):
        return
    info = _depot_kurzinfo_speicher().get(st.session_state.get("login_name") or "_")
    if not info:
        return
    tag = info.get("tag")
    zeit = info.get("zeit")
    stand = (zeit.strftime("%H:%M") if zeit and zeit.date() == jetzt.date()
             else zeit.strftime("%d.%m. %H:%M") if zeit else "")
    st.markdown(
        '<div class="hero gesamt kurz"><div class="hero-label">Depot gesamt'
        + (f' <span class="kurz-stand">Stand {stand}&nbsp;Uhr</span>' if stand else '') + '</div>'
        f'<div class="price-line"><span class="hero-val">{FMT.eur(info["wert"], 2)}</span></div>'
        + gv_zeile_html(info["gv"], info["gv_pct"])
        + (gv_zeile_html(tag[0], tag[1], text="heute") if tag else '')
        + '</div>', unsafe_allow_html=True)


@st.fragment(run_every=300)
def startseite_ticker():
    """Kurs-Ticker unter der Depot-Karte: nur echte Indexstaende (DAX in Punkten …), heute ±%. Liest nur die
    gespeicherten Kurse des Kurs-Agenten (keine Kursabrufe beim Start); laeuft alle 5 Min. neu (Agent: alle 30 Min.)."""
    if not GH_STATE_READY:
        return
    try:
        _idx = kurs_vorrat().indizes()
        eintraege = indizes.ticker_eintraege(_idx)
        nachrichten = kurs_vorrat().news()
    except Exception as e:
        logging.warning(f"Ticker nicht geladen: {type(e).__name__}")
        return
    teile = []
    if eintraege:          # je Wert: gruener Punkt = Boerse offen, "Schluss" = letzter Schlusskurs
        _stand = indizes.stand_text(_idx)
        teile.append(startseite.ticker_html(eintraege, "Indizes heute" + (f" · {_stand}" if _stand else "")))
    if nachrichten:        # Finanz-Schlagzeilen (Kurs-Agent, news.py)
        teile.append(startseite.news_html(nachrichten, datetime.datetime.now(BERLIN_TZ)))
    if any(teile):
        st.markdown(startseite.CSS + "".join(teile), unsafe_allow_html=True)


def darstellung_modus():
    """Gewaehlte Darstellung des Benutzers: "dunkel" (Standard), "hell" oder "auto" (wie das Geraet).
    Je Benutzer gespeichert (gemerkte Eingaben, Bereich "darstellung") - gilt so auf allen Geraeten."""
    if "ui_modus" not in st.session_state:
        try:
            gespeichert = nutzerdaten.eingaben_laden(gh_read_cached, _nutzer(), "darstellung").get("modus")
        except Exception:
            gespeichert = None
        st.session_state["ui_modus"] = gespeichert if gespeichert in ui_hell.MODI else "dunkel"
    return st.session_state["ui_modus"]


def _darstellung_gewaehlt():
    neu = st.session_state.get("ui_modus_wahl")
    if neu not in ui_hell.MODI:
        return
    st.session_state["ui_modus"] = neu
    try:
        nutzerdaten.eingaben_merken(gh_aktualisiere, st.session_state, _nutzer(), "darstellung", {"modus": neu},
                                    sofort=True)
    except Exception as e:
        logging.warning(f"Darstellung nicht gespeichert: {type(e).__name__}")


def _sichtbar(ansicht):
    """Darf der angemeldete Benutzer diese Ansicht sehen? Die Benutzerverwaltung
    nur fuer den Admin (Audit SEC-03) - auch nicht bei ausdruecklich deaktiviertem Login."""
    n = _nutzer()
    # Erklaerungen, Rechner und Marktdaten ohne eigene Daten - fuer alle
    if ansicht in (ANSICHT_GLOSSAR, ANSICHT_KO, ANSICHT_ETP, ANSICHT_FG, ANSICHT_GAP, ANSICHT_DK):
        return True
    if ansicht == ANSICHT_PYR:           # Pyramiden: jeder Benutzer in seinem eigenen Datenbereich
        return True
    if ansicht in (ANSICHT_BENUTZER, ANSICHT_GESUNDHEIT):     # Gesundheitsdaten: nur angemeldeter Admin
        return bool(n) and n.get("rolle") == "admin"
    if ansicht == ANSICHT_YT:            # Faceless YouTube: nur angemeldeter Admin
        return bool(n) and n.get("rolle") == "admin"
    if ansicht == ANSICHT_WIKI:          # eigene Handelsidee: Admin, sonst nur bei ausdruecklich vergebenem Recht
        return n is None or n.get("rolle") == "admin" or ansicht in (n.get("ansichten") or [])
    return login.darf(n, ansicht)


def _zugang_pruefen(ansicht=None):
    """Zugriffspruefung am Anfang jedes inneren Fragments (Audit SEC-10): ein
    Fragment-Neuaufbau laeuft ohne login.gate(). Abgemeldet/gesperrt -> ganze App neu
    (Anmeldemaske), fehlendes Recht auf die Ansicht -> Fragment stoppt."""
    u = login.pruefen(st, gh_read_cached)
    if ansicht and not _sichtbar(ansicht):
        st.warning("Kein Zugriff auf diese Ansicht.")
        st.stop()
    return u


def _abmelden():
    eingaben_offene_speichern()
    login.abmelden(st)
    try:
        st.query_params.clear()
    except Exception:
        pass


def _app_url():
    try:
        u = st.context.url
        if u:
            return u.split("?")[0]
    except Exception:
        pass
    return APP_URL


AKTUALISIEREN_MIN_ABSTAND_SEK = 60


def _nav_aktualisieren():
    """Einen Hintergrund-Lauf starten - hoechstens einmal je Minute fuer alle Sitzungen zusammen
    (Audit A-20: der Kursspeicher ist global). Waehrend des Laufs ist der Knopf gesperrt."""
    ende = kurs_dienst_bereit().status()["letzter_ende"]
    if ende is not None and (datetime.datetime.now(BERLIN_TZ) - ende).total_seconds() < AKTUALISIEREN_MIN_ABSTAND_SEK:
        st.toast("Kurse wurden gerade erst geladen.")
        return
    kurse_neu_laden()
    st.session_state["_kurslauf_warten"] = True        # diese Sitzung wartet auf das Ende des Laufs


def _zeit_kurz(t, jetzt):
    return t.strftime("%H:%M") if t.date() == jetzt.date() else t.strftime("%d.%m. %H:%M")


def kursstand_text(stx, jetzt, agent_stand=None):
    """Kurzer Stand aller Kurse fuer Kopf/Startseite (Kurs-Agent bzw. aeltester Wert im Speicher)."""
    if agent_aktuell(agent_stand, jetzt):
        return f"Kurse von <b>{_zeit_kurz(agent_stand, jetzt)}&nbsp;Uhr</b>"
    if stx["aeltester"] is None:
        return ("Kurse von <b>" + _zeit_kurz(agent_stand, jetzt) + "&nbsp;Uhr</b>" if agent_stand
                else "Kurse werden beim ersten Aufruf geladen")
    t = max(stx["aeltester"], agent_stand) if agent_stand else stx["aeltester"]
    return f"Kurse von <b>{_zeit_kurz(t, jetzt)}&nbsp;Uhr</b>"


def naechste_aktualisierung(jetzt, agent_stand):
    """Naechster Lauf: des Kurs-Agenten, solange er liefert - sonst der eigene Zeitplan der App."""
    if agent_aktuell(agent_stand, jetzt):
        return naechster_agent_lauf(jetzt) or naechster_termin(jetzt)
    return naechster_termin(jetzt)


KURSLAUF_WARTEN_MAX_SEK = 180


def _kurslauf_fortschritt(stx):
    """Waehrend eines Laufs: Wer ihn per Knopf gestartet hat, wartet hier mit Fortschrittsbalken bis
    zum Ende und bekommt danach die Seite mit den neuen Kursen (Knopf bis dahin gesperrt). Alle anderen
    sehen nur einen Hinweis und arbeiten mit dem bisherigen Stand weiter - ohne Wartezeit."""
    if not stx["laeuft"]:
        st.session_state.pop("_kurslauf_warten", None)
        return
    if not st.session_state.get("_kurslauf_warten"):
        st.caption(f"⏳ Kurse werden gerade im Hintergrund aktualisiert ({stx['fertig']} von {stx['gesamt']}) – "
                   "angezeigt wird bis dahin der bisherige Stand.")
        return
    d = kurs_dienst()
    balken = st.empty()
    t0 = time.monotonic()
    while d.laeuft() and time.monotonic() - t0 < KURSLAUF_WARTEN_MAX_SEK:
        x = d.status()
        balken.markdown(UI.lade_balken_html(100 * x["fertig"] / x["gesamt"] if x["gesamt"] else 0.0,
                                            f"⏳ Kurse werden geladen … {x['fertig']} von {x['gesamt']}"),
                        unsafe_allow_html=True)
        time.sleep(0.5)
    st.session_state.pop("_kurslauf_warten", None)
    st.rerun()


def _hat_muster():
    try:
        return bool((gh_read_cached(upfad(PFAD_MUSTERDEPOT), {}) or {}).get("depots"))
    except Exception:
        return False


def _gruppe_von(ansicht):
    return next((g for g, a in NAV_GRUPPEN.items() if ansicht in a), None)


def _gruppe_sichtbar(gruppe, hat_muster):
    """Ansichten der Sammel-Kachel, die der Benutzer sehen darf (Musterdepot nur, wenn es eines gibt)."""
    return [a for a in NAV_GRUPPEN[gruppe] if (a != ANSICHT_MUSTER or hat_muster) and _sichtbar(a)]


def _nav_gruppe_oeffnen(gruppe, ansichten):
    """Sammel-Kachel: zuletzt benutzte Ansicht der Gruppe, sonst die erste."""
    zuletzt = (st.session_state.get("_gruppe_zuletzt") or {}).get(gruppe)
    _nav_waehle(zuletzt if zuletzt in ansichten else ansichten[0])


def _nav_gruppe_gewaehlt(key, zuordnung):
    neu = zuordnung.get(st.session_state.get(key))
    if neu in ANSICHTEN and neu != st.session_state.get("ansicht_aktiv"):
        _nav_waehle(neu)


def _gruppen_leiste(aktiv):
    """Umschalter unter der Kopfleiste, wenn die Ansicht zu einer Sammel-Kachel gehoert."""
    gruppe = _gruppe_von(aktiv)
    if not gruppe:
        return
    st.session_state.setdefault("_gruppe_zuletzt", {})[gruppe] = aktiv
    ansichten = _gruppe_sichtbar(gruppe, _hat_muster() or aktiv == ANSICHT_MUSTER)
    if len(ansichten) < 2:
        return
    key = f"nav_gruppe_{NAV_GRUPPE_KEY[gruppe]}"
    zuordnung = {UI.ohne_emoji(ANSICHT_KURZ.get(a, a)): a for a in ansichten}      # Beschriftung -> Ansicht
    st.session_state[key] = UI.ohne_emoji(ANSICHT_KURZ.get(aktiv, aktiv))
    with st.container(key="nav_gruppe_leiste"):
        st.segmented_control(UI.ohne_emoji(gruppe), list(zuordnung), key=key, on_change=_nav_gruppe_gewaehlt,
                             args=(key, zuordnung), label_visibility="collapsed", width="stretch")


def navigation():
    """Startseite: Menue als Liste (untereinander, nach Gruppen). In einer
    Ansicht: schmale Kopfleiste mit "☰ Menü", Titel und Aktualisieren - der
    Inhalt beginnt direkt darunter, wie in einer App.
    -> gewaehlte Ansicht oder None (Startseite)."""
    st.markdown(NAV_CSS, unsafe_allow_html=True)
    login.pruefen(st, gh_read_cached)       # gesperrt/geloescht? -> sofort abmelden (auch bei Teil-Neuaufbau)
    _hell = ui_hell.stil(darstellung_modus())          # helle Ansicht: Regeln gelten unabhaengig von der Reihenfolge
    if _hell:
        st.markdown(_hell, unsafe_allow_html=True)
    jetzt = datetime.datetime.now(BERLIN_TZ)
    # Kurse aktualisiert der Kursdienst im Hintergrund (9, 11, 13 … 23 Uhr) - hier nur anzeigen
    dienst = kurs_dienst_bereit()
    stx = dienst.status()
    laeuft = stx["laeuft"]
    try:
        agent_stand = dienst.vorrat.stand() if getattr(dienst, "vorrat", None) else None
    except Exception:
        agent_stand = None
    _stand_txt = kursstand_text(stx, jetzt, agent_stand)
    _naechste = naechste_aktualisierung(jetzt, agent_stand).strftime("%H:%M")
    stand_html = (f'<div class="nav-stand"><span><i></i>{_stand_txt} · '
                  f'nächste {_naechste}&nbsp;Uhr</span></div>')
    hilfe = ("Die Kurse werden gerade im Hintergrund geladen – der Knopf ist bis zum Ende gesperrt." if laeuft else
             "Alle Kurse jetzt im Hintergrund neu laden (sonst automatisch: der Kurs-Agent aktualisiert werktags "
             "alle 30 Minuten)")

    # Permanentlink (?ansicht=zins&...): beim ersten Aufruf direkt diese Ansicht oeffnen
    if not st.session_state.get("_link_geprueft"):
        st.session_state["_link_geprueft"] = True
        ziel_link = ANSICHT_LINKS.get(st.query_params.get("ansicht", ""))
        if ziel_link and _sichtbar(ziel_link):
            st.session_state["ansicht_aktiv"] = ziel_link
    aktiv = st.session_state.get("ansicht_aktiv")
    if aktiv is not None and not _sichtbar(aktiv):
        aktiv = None
    if aktiv not in ANSICHTEN:
        aktiv = None

    if aktiv is None:
        # ---- Startseite: Menue ----
        with st.container(key="nav_menue"):
            st.markdown(
                '<div class="nav-kopf"><div class="nav-logo"><span class="nav-lauf">FINANZ <span>DASHBOARD</span></span></div>'
                '<div class="nav-credit">created by MarsTech</div></div>',
                unsafe_allow_html=True)
            # Kursstand und "Kurse aktualisieren" in EINER Kachel; der Live-Balken laeuft ueber die ganze Breite
            # Eine schlanke Zeile: blinkendes Live-Licht, Kursstand, runder Aktualisieren-Knopf
            with st.container(key="nav_kurse", horizontal=True, vertical_alignment="center", gap="small"):
                st.markdown(f'<div class="nav-kurse-kopf"><span class="nav-dot" aria-hidden="true"></span>'
                            f'<span class="nav-kurse-text">{_stand_txt} · nächste {_naechste}&nbsp;Uhr</span></div>',
                            unsafe_allow_html=True)
                st.button("⏳" if laeuft else "🔄", key="nav_refresh", help=hilfe, on_click=_nav_aktualisieren,
                          disabled=laeuft)
            _kurslauf_fortschritt(stx)
            depot_kurzinfo_karte(jetzt)
            startseite_ticker()
            if _nutzer():
                # klein, fest oben rechts in der Ecke
                st.markdown("""<style>
                .st-key-logout_ecke { position: fixed !important; z-index: 999999;
                    top: calc(env(safe-area-inset-top, 0px) + 8px); right: 10px;
                    width: auto !important; margin: 0 !important; }
                .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button,
                .st-key-logout_ecke [data-testid="stButton"] button {
                    width: 30px !important; height: 30px !important; min-height: 30px !important;
                    min-width: 30px !important; padding: 0 !important; border-radius: 50% !important;
                    background: var(--glas-bg) !important;
                    border: 1px solid rgba(255,77,77,.9) !important; transform: none !important;
                    position: relative !important; overflow: visible !important;
                    box-shadow: none !important; filter: none !important; }
                /* Leuchten ueber eigenen Ring - box-shadow des Knopfs ist global per !important belegt
                   (graue 3D-Schatten der Menue-Tasten) und liesse sich nicht animieren */
                .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button::before,
                .st-key-logout_ecke [data-testid="stButton"] button::before {
                    content: ""; position: absolute; inset: -1px; border-radius: 50%; pointer-events: none;
                    animation: logoutglow 2.4s ease-in-out infinite; }
                /* roter Rand mit gleichem Puls-Takt wie Logo und Ueberschriften (2,4 s) */
                /* Touch: 44-px-Trefferflaeche um den kleinen Kreis (Audit UX) */
                @media (pointer: coarse) {
                    /* Die ::after-Flaeche wurde vom Elternelement abgeschnitten (gemessen: 30 px) - deshalb
                       ist der Knopf selbst 44 px gross, der rote Kreis wird innen gezeichnet (UX 10/2026) */
                    html body .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button,
                    html body .st-key-logout_ecke [data-testid="stButton"] button {
                        width: 48px !important; height: 48px !important; min-width: 48px !important;
                        min-height: 48px !important; margin: -9px !important; background: transparent !important;
                        border: none !important; isolation: isolate; }
                    html body .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button::before,
                    html body .st-key-logout_ecke [data-testid="stButton"] button::before {
                        inset: 9px; z-index: -1; border: 1px solid rgba(255,77,77,.9);
                        background: var(--glas-bg); }
                }
                @keyframes logoutglow {
                    0%, 100% { box-shadow: 0 0 2px rgba(255,60,60,.25); }
                    50%      { box-shadow: 0 0 8px rgba(255,60,60,.85), 0 0 18px rgba(255,60,60,.4); }
                }
                @keyframes logouticon {
                    0%, 100% { opacity: .72; filter: drop-shadow(0 0 2px rgba(255,60,60,.3)); }
                    50%      { opacity: 1;   filter: drop-shadow(0 0 5px rgba(255,60,60,.95)); }
                }
                .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button::after { display: none !important; }
                .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button p,
                .st-key-logout_ecke [data-testid="stButton"] button p {
                    position: absolute !important; width: 1px !important; height: 1px !important;
                    overflow: hidden !important; clip: rect(0 0 0 0) !important; white-space: nowrap !important; }
                .st-key-logout_ecke [data-testid="stButton"] button [data-testid="stIconMaterial"] {
                    font-size: 16px !important; color: #ff5c5c !important; margin: 0 0 0 2px !important;
                    animation: none; }
                .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button:hover,
                .st-key-nav_menue .st-key-logout_ecke [data-testid="stButton"] button:active {
                    transform: none !important;
                    box-shadow: 0 0 10px rgba(255,60,60,.95), 0 0 22px rgba(255,60,60,.5) !important; }
                /* waehrend des Ladens ausblenden: sofort beim Prozent-Balken, sonst nach 0,5 s
                   (gleiche Verzoegerung wie die allgemeine Ladeanzeige - kein Flackern bei kurzen Klicks) */
                [data-testid="stApp"]:has(.loading-overlay) .st-key-logout_ecke { display: none !important; }
                body:has(#lade-banner[style*="block"]) .st-key-logout_ecke { display: none !important; }
                [data-testid="stApp"][data-test-script-state="running"] .st-key-logout_ecke,
                [data-testid="stApp"][data-test-script-state="rerunRequested"] .st-key-logout_ecke {
                    animation: logoutweg 0.15s ease 0.5s forwards; }
                @keyframes logoutweg { to { opacity: 0; visibility: hidden; } }
                @media (prefers-reduced-motion: reduce) {
                    .st-key-logout_ecke [data-testid="stButton"] button::before,
                    .st-key-logout_ecke [data-testid="stIconMaterial"] { animation: none !important; } }
                </style>""", unsafe_allow_html=True)
                with st.container(key="logout_ecke"):
                    # kein on_click: der Knopf liegt im Fragment - ein Callback wuerde nur das
                    # Fragment neu zeichnen (Menue ohne Knopf). Hier wird die GANZE App neu
                    # gestartet, damit die Anmeldemaske erscheint.
                    if st.button("Abmelden", icon=":material/logout:", key="nav_logout", width="content",
                                 help=f"Abmelden ({_nutzer()['name']})"):
                        _abmelden()
                        try:
                            st.rerun(scope="app")
                        except TypeError:
                            st.rerun()
            elif login.konfig(st) is None:
                # Nur erreichbar, wenn das Login AUSDRUECKLICH abgeschaltet ist - eine fehlende
                # Konfiguration stoppt login.gate() vorher (fail-closed, Audit SEC-03).
                st.markdown('<div style="text-align:center;font-size:.8rem;color:#f0a27f;margin:6px 0">🔓 Ohne '
                            'Anmeldung (Login in den Secrets ausdrücklich abgeschaltet)</div>',
                            unsafe_allow_html=True)
            farb_css = []
            hat_muster = _hat_muster()
            for titel, eintraege in NAV_ZEILEN:
                # je Eintrag: (Beschriftung, Key, Ansicht oder None, Sammel-Gruppe oder None, Gruppen-Ansichten)
                ansichten = []
                for e in eintraege:
                    if e in NAV_GRUPPEN:
                        g_an = _gruppe_sichtbar(e, hat_muster)
                        if len(g_an) == 1:                  # nur eine erlaubt -> normale Kachel
                            ansichten.append(g_an[0])
                        elif g_an:
                            ansichten.append(e)
                    elif (e != ANSICHT_MUSTER or hat_muster) and _sichtbar(e):
                        ansichten.append(e)
                if not ansichten:
                    continue
                farbe = NAV_FARBEN.get(titel, "#F4F8FF")
                verzug = f"{[t for t, _ in NAV_ZEILEN].index(titel) * 1.1:.2f}s"   # Laser je Gruppe versetzt
                st.markdown(f'<div class="nav-gruppe" style="--verzug:{verzug}"><span class="nav-wander">'
                            f'{titel}</span></div>', unsafe_allow_html=True)
                # alle Kacheln der Gruppe in EINER Zeile - das CSS bricht je nach Breite um
                # (Handy 2, Tablet 3, Desktop 4, breite Monitore 5 nebeneinander)
                spalten = st.columns(len(ansichten))
                for spalte, ansicht in zip(spalten, ansichten):
                    if ansicht in NAV_GRUPPEN:
                        spalte.button(ansicht, key=f"nav_g_{NAV_GRUPPE_KEY[ansicht]}", width="stretch",
                                      on_click=_nav_gruppe_oeffnen,
                                      args=(ansicht, _gruppe_sichtbar(ansicht, hat_muster)))
                        continue
                    idx = ANSICHTEN.index(ansicht)
                    spalte.button(NAV_NAMEN.get(ansicht, ansicht), key=f"nav_b{idx}",
                                  width="stretch", on_click=_nav_waehle, args=(ansicht,))
                    if titel in NAV_FARBEN:
                        farb_css.append(f".st-key-nav_menue .st-key-nav_b{idx} button {{ border-color: {farbe} !important; "
                                        f"box-shadow: 0 8px 18px rgba(0,0,0,.55), 0 0 14px {farbe}55 !important; }}")
            st.markdown("<style>" + "\n".join(farb_css) + "</style>", unsafe_allow_html=True)
            # Darstellung (hell / dunkel / wie das Geraet) - je Benutzer gespeichert
            st.markdown('<div class="nav-gruppe"><span class="nav-wander">Darstellung</span></div>',
                        unsafe_allow_html=True)
            st.session_state["ui_modus_wahl"] = darstellung_modus()
            st.segmented_control("Darstellung", ui_hell.MODI, format_func=ui_hell.MODUS_TEXT.get,
                                 key="ui_modus_wahl", on_change=_darstellung_gewaehlt, label_visibility="collapsed",
                                 width="stretch")
        return None

    # ---- In einer Ansicht: Kopfleiste ----
    # Grosse Monitore: Inhalt auf UI.INHALT_MAX begrenzt (ui_stil); Ansichten mit breiten Tabellen duerfen breiter
    if aktiv in BREITE_ANSICHTEN:
        st.markdown(f'<style>[data-testid="stMainBlockContainer"][data-testid="stMainBlockContainer"] '
                    f'{{ max-width: {UI.INHALT_MAX_BREIT}px !important; }}</style>', unsafe_allow_html=True)
    with st.container(key="nav_leiste"):
        c1, c2, c3 = st.columns([1, 3, 1], vertical_alignment="center")
        c1.button("☰ Menü", key="nav_menue_btn", on_click=_nav_waehle, args=(None,),
                  help="Zurück zur Übersicht aller Ansichten")
        c2.markdown(f'<div class="nav-titel">{html.escape(UI.ohne_emoji(NAV_TITEL.get(aktiv) or NAV_NAMEN.get(aktiv, aktiv)))}</div>',
                    unsafe_allow_html=True)
        c3.button("⏳" if laeuft else "🔄", key="nav_refresh_klein", help=hilfe, on_click=_nav_aktualisieren,
                  disabled=laeuft)
    _gruppen_leiste(aktiv)
    if aktiv not in OHNE_KURSE:              # Ansichten ohne Live-Kurse: dort zeigt jede Liste ihren eigenen Stand
        st.markdown(stand_html, unsafe_allow_html=True)
    _kurslauf_fortschritt(stx)
    return aktiv


def render_chronik():
    """Chronik-Ansicht. Braucht keine Kursdaten - laeuft daher als leichte Ansicht vor
    dem Kursabruf und bleibt auch bei einem Ausfall der Kursquelle erreichbar."""
    eigen = eigener_bereich()
    heute_date = datetime.datetime.now(BERLIN_TZ).date()
    tab_trades = st.container()
    try:
        # Admin: gemeinsame Chronik (auch Workflow-Alarme, Anmeldungen);
        # normale Benutzer: eigene Chronik (eigene Notizen und Depot-Ereignisse)
        _chronik_pfad = upfad(config.STATE_PATH_TRADES_DB)

        def load_db():
            return gh_read(_chronik_pfad, [])

        def notiz_speichern(eintrag):
            """Lesen-Aendern-Schreiben mit Versionspruefung (keine verlorenen
            Auto-Eintraege der Workflows, nie nach einem Lesefehler). -> True/False"""
            ok, _ = gh_aktualisiere(
                _chronik_pfad,
                lambda d: chronik.anhaengen(d if isinstance(d, list) else [], eintrag)[0],
                default=[], message="update chronik [skip ci]")
            return ok

        db_events = [x for x in (load_db() or []) if isinstance(x, dict)]

        with tab_trades:
            if eigen:
                st.caption("Deine persönliche Chronik: wird automatisch mit Änderungen an deinen "
                           "Depot-Positionen, beobachteten Werten, Sparplan und Entnahme gefüllt. "
                           "Eigene Notizen sind jederzeit möglich.")
            else:
                st.caption("Wird automatisch gefüllt: Kurs-Alarme, Entwarnungen und neue Allzeithochs aus dem "
                           "Discord-Workflow, Änderungen an Depot-Positionen und beobachteten Werten, Sparplan "
                           "Start/Stopp, Musterdepots und gespeicherte Planungen. Eigene Notizen sind weiter möglich.")
            anzahl = {}
            for ev in db_events:
                k_ = chronik.kategorie_von(ev)
                anzahl[k_] = anzahl.get(k_, 0) + 1
            optionen = ["alle"] + [k_ for k_ in chronik.KATEGORIEN if anzahl.get(k_)]
            beschr = {"alle": f"Alle ({len(db_events)})"}
            beschr.update({k_: f"{v_[0]} {v_[1]} ({anzahl.get(k_, 0)})" for k_, v_ in chronik.KATEGORIEN.items()})
            schritte.leiste(st, "chronik")
            schritte.titel(st, "chronik", 1)
            try:
                wahl = st.pills("Filter", optionen, default="alle", format_func=beschr.get,
                                key="chronik_filter", label_visibility="collapsed") or "alle"
            except Exception:
                wahl = st.selectbox("Filter", optionen, format_func=beschr.get, key="chronik_filter_sb")
            gezeigt = [ev for ev in db_events if wahl == "alle" or chronik.kategorie_von(ev) == wahl]
            schritte.titel(st, "chronik", 2)
            farben = {"alarm": "#F87171", "depot": "#29B6F6", "beobachtung": "#A78BFA", "planer": "#F5B942",
                      "notiz": "#71717A"}
            if not gezeigt:
                st.info("Noch keine Einträge – sie entstehen ab jetzt automatisch.")
            letzter_tag = None
            for ev in gezeigt[:200]:
                k_ = chronik.kategorie_von(ev)
                tag = ev.get("datum", "")
                if tag != letzter_tag:
                    try:
                        tag_txt = datetime.date.fromisoformat(tag).strftime("%d.%m.%Y")
                    except Exception:
                        tag_txt = tag
                    st.markdown(f'<div style="margin:14px 0 6px;font-size:.8rem;font-weight:700;'
                                f'color:#A1A1AA;letter-spacing:.06em">{html.escape(tag_txt)}</div>',
                                unsafe_allow_html=True)
                    letzter_tag = tag
                kopf = " · ".join(t for t in (ev.get("zeit", ""), ev.get("typ", "")) if t)
                st.markdown(f"""
                    <div style="background: #09090B; border: 1px solid var(--rand, rgba(255, 255, 255, 0.55)); border-left: 3px solid {farben.get(k_, '#29B6F6')}; padding: 10px 12px; border-radius: 6px; margin-bottom: 8px;">
                        <div style="font-size: 0.8rem; color: #A1A1AA;">{html.escape(kopf)}</div>
                        <div style="font-weight: 700; color: #FFFFFF; font-size: 0.95rem;">{html.escape(str(ev.get('titel','')))}</div>
                        <div style="font-size: 0.85rem; color: #D1D5DB;">{html.escape(str(ev.get('inhalt','')))}</div>
                    </div>
                """, unsafe_allow_html=True)
            if len(gezeigt) > 200:
                st.caption(f"Die neuesten 200 von {len(gezeigt)} Einträgen.")

            schritte.titel(st, "chronik", 3)
            with st.expander("✏️ Eigene Notiz hinzufügen", expanded=False):
                with st.form("trade_form", clear_on_submit=True):
                    col1, col2 = st.columns([1, 1])
                    with col1: ed = st.date_input("Datum", heute_date, format="DD.MM.YYYY")
                    with col2: eti = st.text_input("Titel")
                    ei = st.text_area("Details")
                    if st.form_submit_button("Speichern") and eti:
                        eintrag = chronik.neuer_eintrag("notiz", eti, ei, typ="Notiz", quelle="manuell")
                        eintrag["datum"] = ed.strftime("%Y-%m-%d")
                        if notiz_speichern(eintrag):
                            st.rerun()
                        else:
                            st.error("Notiz NICHT gespeichert (kein persistenter State oder Lesefehler).")

    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Trader-Log", e)


# --- GESAMTE RENDER-LOGIK ALS FRAGMENT ---
# Vermeidet den harten Full-Page-Rerun von st_autorefresh (sichtbares
# Aufhellen/Neuzeichnen alle 30s). Ein Fragment aktualisiert sich selbst
# periodisch, ohne die komplette Seite neu zu bauen/zu scrollen.
def begriffe_erklaeren(ansicht):
    """Fachbegriffe der geoeffneten Ansicht kurz erklaert (eingeklappt, am Seitenende - Audit UX-04).
    Innerhalb des Fragments aufrufen: ein Menue-Klick baut nur das Fragment neu auf."""
    try:
        glossar_ui.zur_ansicht(st, ansicht)
    except Exception as e:
        logging.warning(f"Glossar nicht angezeigt: {type(e).__name__}")


@st.fragment(run_every=NAV_PRUEF_SEK)
def render_dashboard():
    _zugang_pruefen()       # Audit SEC-10: auch der periodische Fragment-Neuaufbau prueft die Anmeldung
    sitzung_eingaben_merken(st.session_state)
    now_berlin = datetime.datetime.now(BERLIN_TZ)
    heute_date = now_berlin.date()

    # EINE gemeinsame Ladeanzeige fuer den kompletten Seitenaufbau. Die
    # Gewichte entsprechen grob dem Zeitanteil der jeweiligen Phase - dadurch
    # laeuft ein einziger Prozentwert von 0 auf 100, statt dass mehrere Balken
    # nacheinander jeweils wieder bei 0 % beginnen.
    _lade_platz = st.empty()
    # Hinweis bei Speicher-Lesefehlern (Audit A-10) - wird am Ende des Aufbaus gefuellt
    _speicher_platz = st.empty()
    st.session_state["_speicher_fehler"] = False
    melde, _lade_fertig_roh = erstelle_ladeanzeige(_lade_platz, [
        ("live",        8),    # ein Abruf
        ("kaufkurs",    5),    # ein Abruf, meist aus dem Cache
        ("historie",   12),    # ein groesserer Abruf
        ("benchmarks", 40),    # ein Abruf je Vergleichswert - der Loewenanteil
        ("positionen", 18),    # je weiterer Position zwei Abrufe
        ("beob_prognose", 10), # je Beobachtungswert ein Abruf fuer die Prognose-Basis
        ("ansicht",    7),     # gewaehlter Chart
    ])

    def lade_fertig():
        _lade_fertig_roh()
        if st.session_state.get("_speicher_fehler"):
            _speicher_platz.warning(
                "⚠️ Der Datenspeicher (GitHub) war gerade nicht erreichbar – gespeicherte Daten wie "
                "Positionen, Sparplan oder Chronik fehlen eventuell in der Anzeige. Es wurde nichts "
                "überschrieben. Bitte in ein paar Minuten mit 🔄 neu laden.")

    # ---------- NAVIGATION ganz oben ----------
    gewaehlte_ansicht = navigation()

    # ---------- WATCHLIST TOP 50 ----------
    # Die Ranglisten berechnet der taegliche Agent (top50_agent.py, GitHub
    # Actions) und legt sie fertig in state/top50.json ab. Die App liest nur
    # diese Datei - kein einziger Kursabruf beim Umschalten, deshalb schnell.
    # Als Fragment: Kategorie- und Zeitraumwechsel bauen nur diesen Bereich neu.
    # ---------- WOCHENVERGLEICH (Pfeile + Neu/Raus) ----------
    # Die Agenten speichern taeglich die Top 50 und vergleichen mit dem Stand
    # von vor 7 Tagen: "vor" = Platz damals (None = neu in der Liste).
    TREND_FARBE = {"up": "#34D399", "down": "#F87171", "gleich": "#9AA0A6", "neu": "#34D399"}
    Q_KLASSEN_KURZ = {"prio": "Priorität", "beobachten": "Beobachten", "nicht": "Nicht weiterv."}

    def _trend(vor, jetzt):
        return ranglisten_ansichten._trend({'TREND_BIS': TREND_BIS}, vor=vor, jetzt=jetzt)

    def _seit_text(seit):
        return ranglisten_ansichten._seit_text({}, seit=seit)

    def _wochen_bilanz(eintraege, raus, seit):
        return ranglisten_ansichten.wochen_bilanz({'Q_KLASSEN_KURZ': Q_KLASSEN_KURZ, 'TREND_BIS': TREND_BIS, 'TREND_FARBE': TREND_FARBE, '_seit_text': _seit_text, 'html': html}, eintraege=eintraege, raus=raus, seit=seit)

    # ---------- INDEX-FILTER (gemeinsam fuer alle Listen) ----------
    # Die Agenten schreiben die Daten ALLER Aktien in Teildateien plus die
    # Indexmitglieder; die App bildet daraus die Rangliste des gewaehlten
    # Index mit derselben Sortierung wie der Agent. Pfeile/Neu/Raus kommen
    # aus dem Wochenvergleich, den die Agenten je Index-Rangliste fuehren.
    @st.cache_data(ttl=900, show_spinner=False)
    def _lade_teile(muster, anzahl):
        return ranglisten_ansichten._lade_teile({'gh_read_streng': gh_read_streng}, muster=muster, anzahl=anzahl)

    def _q_alle():
        return ranglisten_ansichten._q_alle({'_lade_teile': _lade_teile, 'github_store': github_store})

    def _p_alle():
        return ranglisten_ansichten._p_alle({'_lade_teile': _lade_teile, 'github_store': github_store})

    def _index_auswahl(prefix, indizes, regionen):
        return ranglisten_ansichten._index_auswahl({'auswahl_kompakt': auswahl_kompakt}, prefix=prefix, indizes=indizes, regionen=regionen)

    LISTEN_LAENGEN = [50, 100, 250, 500]
    TREND_BIS = 50              # Wochenvergleich (Pfeile/NEU) gibt es fuer die ersten 50 Plaetze

    def _listen_laenge(prefix, alle=False):
        return ranglisten_ansichten._listen_laenge({'LISTEN_LAENGEN': LISTEN_LAENGEN}, prefix=prefix, alle=alle)

    def _auswahl_art(prefix):
        return ranglisten_ansichten._auswahl_art({}, prefix=prefix)

    INDEX_REGIONEN_APP = ["Deutschland", "USA", "Europa", "Asien/Pazifik & Kanada", "Schwellenländer"]

    def _p_index_kat(idx_key, info, daten, laenge=50):
        return ranglisten_ansichten._p_index_kat({'_p_alle': _p_alle, 'gh_read_taeglich': gh_read_taeglich}, idx_key=idx_key, info=info, daten=daten, laenge=laenge)

    def _render_performance():
        return ranglisten_ansichten.performance({'BERLIN_TZ': BERLIN_TZ, 'GH_STATE_READY': GH_STATE_READY, 'INDEX_REGIONEN_APP': INDEX_REGIONEN_APP, 'KV': KV, 'TREND_BIS': TREND_BIS, 'TREND_FARBE': TREND_FARBE, '_auswahl_art': _auswahl_art, '_index_auswahl': _index_auswahl, '_listen_laenge': _listen_laenge, '_p_index_kat': _p_index_kat, '_trend': _trend, '_wochen_bilanz': _wochen_bilanz, 'auswahl_kompakt': auswahl_kompakt, 'gh_read_taeglich': gh_read_taeglich, 'html': html, 'kurs_vorrat': kurs_vorrat, 'notify_app_error': notify_app_error, 'ranglisten_stand': ranglisten_stand, 'vz_zahl': vz_zahl})


    # ---------- QUALITAETS-SCORE (Hauptliste) ----------
    # Berechnet taeglich von qualitaet_agent.py (GitHub Actions) nach dem
    # 100-Punkte-Schema. Die Tabelle kommt aus state/qualitaet.json, die
    # ausfuehrliche Analyse je Aktie aus state/qualitaet/details_<n>.json -
    # erst geladen, wenn eine Aktie ausgewaehlt wird.
    Q_KLASSEN = {"prio": "Hohe Analysepriorität", "beobachten": "Beobachtungsliste",
                 "nicht": "Nicht weiterverfolgen"}
    Q_BEREICHE = [("qualitaet", "Unternehmensqualität", 20), ("wachstum", "Wachstum & Reinvestment", 15),
                  ("fcf", "Free Cashflow & Gewinnqualität", 15), ("bilanz", "Bilanzqualität", 10),
                  ("management", "Management & Kapitalallokation*", 10), ("moat", "Wettbewerbsvorteil*", 10),
                  ("bewertung", "Bewertung", 15), ("chance", "Chance-Risiko / Margin of Safety", 5)]

    def _q_pct(x, vorzeichen=True, nachkomma=1):
        return ranglisten_ansichten._q_pct({}, x=x, vorzeichen=vorzeichen, nachkomma=nachkomma)

    def _q_x(x, suffix='x'):
        return ranglisten_ansichten._q_x({}, x=x, suffix=suffix)

    # Spalten der Qualitaets-Tabelle: (Schluessel, Kopf, Formatierung, Farbe)
    def _qf_pct(nachkomma=1, vorzeichen=True):
        return ranglisten_ansichten._qf_pct({}, nachkomma=nachkomma, vorzeichen=vorzeichen)

    def _qf_zahl(suffix=''):
        return ranglisten_ansichten._qf_zahl({}, suffix=suffix)

    def _qc_schwelle(gut, schlecht, umgekehrt=False):
        return ranglisten_ansichten._qc_schwelle({}, gut=gut, schlecht=schlecht, umgekehrt=umgekehrt)

    def _qc_label(gut, schlecht):
        return ranglisten_ansichten._qc_label({}, gut=gut, schlecht=schlecht)

    Q_SPALTEN = [
        ("roic", "ROIC", _qf_pct(1, False), _qc_schwelle(15, 8)),
        ("g_fcfps", "FCF/Aktie-Wachst.", _qf_pct(), _qc_schwelle(8, 0)),
        ("fcfy", "FCF-Rendite", _qf_pct(2, False), _qc_schwelle(5, 2)),
        ("fkgv", "Forward-KGV", _qf_zahl(), _qc_schwelle(15, 35, True)),
        ("ev_ebit", "EV/EBIT", _qf_zahl(), _qc_schwelle(15, 30, True)),
        ("g_ums", "Umsatz-Wachst.", _qf_pct(), _qc_schwelle(8, 0)),
        ("g_eps", "EPS-Wachst.", _qf_pct(), _qc_schwelle(8, 0)),
        ("g_fcf", "FCF-Wachst.", _qf_pct(), _qc_schwelle(8, 0)),
        ("om", "Op. Marge", _qf_pct(1, False), _qc_schwelle(15, 5)),
        ("fm", "FCF-Marge", _qf_pct(1, False), _qc_schwelle(12, 3)),
        ("nde", "Net Debt/EBITDA", lambda x: "–" if x is None else "Netto-Cash" if x <= 0 else f"{x:.1f}x",
         _qc_schwelle(1, 3, True)),
        ("akt", "Verwässerung p.a.", _qf_pct(), _qc_schwelle(0, 2, True)),
        ("moat", "Moat*", str, _qc_label(("stark",), ("gering",))),
        ("mgmt", "Management*", str, _qc_label(("gut",), ("schwach",))),
        ("bew", "Bewertung", str, _qc_label(("günstig",), ("teuer",))),
        # Dividendenrendite (letzte 12 Monate): grün ab 3 %, keine Rotfärbung - keine Dividende ist kein Mangel
        ("div", "Dividende", _qf_pct(2, False), _qc_schwelle(3, -1)),
        ("aus", "Ausschüttung", lambda x: x or "–", lambda x: ""),
        ("div_q", "Ausschüttungsquote", _qf_pct(0, False), _qc_schwelle(60, 100, True)),
        ("risiko", "Risiko", str, _qc_label(("niedrig",), ("hoch",))),
        ("mcap", "Mkap. Mrd €", _qf_zahl(), lambda x: ""),
    ]
    Q_KLASSE_CSS = {"prio": "q-prio", "beobachten": "q-beob", "nicht": "q-nicht"}

    Q_FARBE_CSS = {"pt-up": "color: #34D399; font-weight: 600", "pt-down": "color: #F87171; font-weight: 600"}

    def _q_vergleich(werte, symbole):
        return ranglisten_ansichten.q_vergleich({'BR': BR, 'DV': DV, 'Q_FARBE_CSS': Q_FARBE_CSS, 'Q_KLASSEN': Q_KLASSEN, 'Q_SPALTEN': Q_SPALTEN}, werte=werte, symbole=symbole)

    def _q_tabelle(werte, symbole, vergleich=None, fokus='roic'):
        return ranglisten_ansichten._q_tabelle({'BR': BR, 'Q_KLASSE_CSS': Q_KLASSE_CSS, 'Q_SPALTEN': Q_SPALTEN, 'TREND_FARBE': TREND_FARBE, '_trend': _trend, 'html': html}, werte=werte, symbole=symbole, vergleich=vergleich, fokus=fokus)

    def _q_details(sym, zeile):
        return ranglisten_ansichten.q_details({'BR': BR, 'Q_BEREICHE': Q_BEREICHE, 'Q_KLASSEN': Q_KLASSEN, 'Q_KLASSE_CSS': Q_KLASSE_CSS, '_q_pct': _q_pct, '_q_x': _q_x, 'daten_q': daten_q, 'gh_read_taeglich': gh_read_taeglich, 'html': html}, sym=sym, zeile=zeile)

    daten_q = {}

    def _q_mitglieder(kat_key, alle):
        return ranglisten_ansichten._q_mitglieder({'gh_read_taeglich': gh_read_taeglich}, kat_key=kat_key, alle=alle)

    def _q_dividenden_tabelle(alle, mitglieder):
        return ranglisten_ansichten._q_dividenden_tabelle({'DV': DV, '_de_zahl': _de_zahl, 'html': html}, alle=alle, mitglieder=mitglieder)

    def _q_sektoren_tabelle(alle, mitglieder):
        return ranglisten_ansichten._q_sektoren_tabelle({'BR': BR, '_de_zahl': _de_zahl, 'html': html}, alle=alle, mitglieder=mitglieder)

    def _div_rhythmen():
        return ranglisten_ansichten._div_rhythmen({'gh_read_taeglich': gh_read_taeglich})

    def _render_qualitaet():
        return ranglisten_ansichten.qualitaet({'BR': BR, 'DV': DV, 'INDEX_REGIONEN_APP': INDEX_REGIONEN_APP, 'Q_KLASSEN': Q_KLASSEN, 'Q_SPALTEN': Q_SPALTEN, '_auswahl_art': _auswahl_art, '_div_rhythmen': _div_rhythmen, '_index_auswahl': _index_auswahl, '_listen_laenge': _listen_laenge, '_q_alle': _q_alle, '_q_details': _q_details, '_q_dividenden_tabelle': _q_dividenden_tabelle, '_q_mitglieder': _q_mitglieder, '_q_sektoren_tabelle': _q_sektoren_tabelle, '_q_tabelle': _q_tabelle, '_q_vergleich': _q_vergleich, '_wochen_bilanz': _wochen_bilanz, 'auswahl_kompakt': auswahl_kompakt, 'daten_q': daten_q, 'gh_read_taeglich': gh_read_taeglich, 'ranglisten_stand': ranglisten_stand})


    # ---------- QUALITAET x KURS ----------
    # Abgleich Qualitaets-Score mit der Kursentwicklung: trennt "Aktie ist
    # gefallen" von "Aktie ist fundamental gut" - und umgekehrt Kursstaerke
    # ohne fundamentale Deckung. Daten: state/qualitaet/matrix.json (alle
    # bewerteten Aktien, kompakt als Arrays).
    QK_QUAL_GRENZE = 62          # Qualitaet (ohne Bewertung) ab 62 % = "hoch" (wie Beobachtungsliste)
    QK_ZEITRAEUME = [("p6", "6 Monate"), ("p12", "1 Jahr"), ("p36", "3 Jahre")]
    QK_FELDER = [
        ("gut_schwach", "🔍 Gute Firma, schwacher Kurs",
         "Qualität hoch, Kurs schwächer als der Median der Kategorie. Kandidaten, bei denen kurzfristige "
         "Probleme den Kurs belastet haben könnten – ob die Aktie dadurch auch GÜNSTIG ist, zeigen "
         "FCF-Rendite und Bewertung. Ein Kursrückgang allein macht eine Aktie nicht attraktiv."),
        ("gut_stark", "✅ Qualität mit Rückenwind",
         "Qualität hoch, Kurs stärker als der Median. Der Markt honoriert die Qualität bereits – "
         "häufig mit höherer Bewertung."),
        ("schwach_stark", "⚠️ Kurs ohne Fundament",
         "Qualität niedrig, Kurs stärker als der Median. Kursstärke ohne fundamentale Deckung – "
         "Hype- und Rückschlagrisiko."),
        ("schwach_schwach", "❌ Weder noch",
         "Qualität niedrig und Kurs schwächer als der Median."),
    ]

    def _qk_daten():
        return ranglisten_ansichten._qk_daten({'_q_alle': _q_alle, 'gh_read_taeglich': gh_read_taeglich})

    def _qk_zeilen(m, kat_key):
        return ranglisten_ansichten._qk_zeilen({}, m=m, kat_key=kat_key)

    def _qk_einteilen(zeilen, zr_key):
        return ranglisten_ansichten._qk_einteilen({'QK_FELDER': QK_FELDER, 'QK_QUAL_GRENZE': QK_QUAL_GRENZE}, zeilen=zeilen, zr_key=zr_key)

    def _qk_tabelle(zeilen, zr_key, zr_titel):
        return ranglisten_ansichten._qk_tabelle({'Q_KLASSE_CSS': Q_KLASSE_CSS, 'html': html, 'vz_zahl': vz_zahl}, zeilen=zeilen, zr_key=zr_key, zr_titel=zr_titel)

    def _qk_diagramm(zeilen, zr_key, zr_titel, median):
        return ranglisten_ansichten._qk_diagramm({'QK_QUAL_GRENZE': QK_QUAL_GRENZE, '_h': _h, 'vz_zahl': vz_zahl}, zeilen=zeilen, zr_key=zr_key, zr_titel=zr_titel, median=median)

    def _render_qualitaet_kurs():
        return ranglisten_ansichten.qualitaet_kurs({'INDEX_REGIONEN_APP': INDEX_REGIONEN_APP, 'QK_FELDER': QK_FELDER, 'QK_QUAL_GRENZE': QK_QUAL_GRENZE, 'QK_ZEITRAEUME': QK_ZEITRAEUME, '_auswahl_art': _auswahl_art, '_index_auswahl': _index_auswahl, '_listen_laenge': _listen_laenge, '_q_details': _q_details, '_qk_daten': _qk_daten, '_qk_diagramm': _qk_diagramm, '_qk_einteilen': _qk_einteilen, '_qk_tabelle': _qk_tabelle, '_qk_zeilen': _qk_zeilen, 'auswahl_kompakt': auswahl_kompakt, 'vz_zahl': vz_zahl})

    # ---------- GESAMTUEBERSICHT (Ansicht + druckfertiges PDF) ----------
    # Ein gemeinsames Datenmodell fuer Bildschirm und PDF, damit beide immer
    # dasselbe zeigen. Zelle = (text, farbe, fett); farbe ist semantisch
    # ("up", "down", "warn", "grau", "prio", "beob", "nicht") und wird je
    # Ausgabe in passende Farben uebersetzt (dunkles Design vs. weisses Papier).
    UE_TEILE = ["Zusammenfassung", "Hohe Analysepriorität", "Beobachtungsliste",
                "Qualität je Kategorie", "Qualität × Kurs", "Wochenveränderung", "Performance"]
    UE_FARBEN_SCHIRM = {"up": "#34D399", "down": "#F87171", "warn": "#F5B942", "grau": "#9AA0A6",
                        "prio": "#34D399", "beob": "#F5B942", "nicht": "#9AA0A6"}
    UE_FARBEN_DRUCK = {"up": "#0E8A5F", "down": "#C62828", "warn": "#B7791F", "grau": "#6B7280",
                       "prio": "#0E8A5F", "beob": "#B7791F", "nicht": "#6B7280"}
    UE_ZEITRAEUME = ["1W", "1M", "3M", "6M", "1J", "3J", "5J", "10J"]

    def _ue_z(text, farbe=None, fett=False):
        return ranglisten_ansichten._ue_z({}, text=text, farbe=farbe, fett=fett)

    def _ue_css_farbe(klasse):
        return ranglisten_ansichten._ue_css_farbe({}, klasse=klasse)

    def _ue_trend(vor, platz):
        return ranglisten_ansichten._ue_trend({'_trend': _trend, '_ue_z': _ue_z}, vor=vor, platz=platz)

    def _ue_qualitaets_tabelle(werte, symbole, vergleich, umfang):
        return ranglisten_ansichten._ue_qualitaets_tabelle({'BR': BR, 'Q_KLASSEN_KURZ': Q_KLASSEN_KURZ, 'Q_SPALTEN': Q_SPALTEN, '_ue_css_farbe': _ue_css_farbe, '_ue_trend': _ue_trend, '_ue_z': _ue_z}, werte=werte, symbole=symbole, vergleich=vergleich, umfang=umfang)

    def _ue_abschnitte(dq, dp, umfang, teile):
        return ranglisten_ansichten.ue_abschnitte({'BR': BR, 'QK_FELDER': QK_FELDER, 'Q_KLASSEN_KURZ': Q_KLASSEN_KURZ, 'UE_ZEITRAEUME': UE_ZEITRAEUME, '_qk_daten': _qk_daten, '_qk_einteilen': _qk_einteilen, '_seit_text': _seit_text, '_trend': _trend, '_ue_qualitaets_tabelle': _ue_qualitaets_tabelle, '_ue_z': _ue_z, 'vz_zahl': vz_zahl}, dq=dq, dp=dp, umfang=umfang, teile=teile)

    def _ue_html(abschnitte):
        return ranglisten_ansichten._ue_html({'UE_FARBEN_SCHIRM': UE_FARBEN_SCHIRM, 'html': html}, abschnitte=abschnitte)

    def _ue_pdf(abschnitte, stand_text):
        return ranglisten_ansichten.ue_pdf({'UE_FARBEN_DRUCK': UE_FARBEN_DRUCK, 'html': html}, abschnitte=abschnitte, stand_text=stand_text)

    def _render_uebersicht():
        return ranglisten_ansichten._render_uebersicht({'UE_TEILE': UE_TEILE, '_ue_abschnitte': _ue_abschnitte, '_ue_html': _ue_html, '_ue_pdf': _ue_pdf, 'gh_read_taeglich': gh_read_taeglich})

    WK_SEITE = 25                                       # Raenge je Seite der wikifolio-Liste
    WK_SPALTEN = ["1M", "3M", "6M", "1J", "2J", "3J", "5J"]

    def _wk_seite(nr, p='wk'):
        return ranglisten_ansichten._wk_seite({}, nr=nr, p=p)

    def _render_wikifolios_alle(teile, stand):
        return ranglisten_ansichten._render_wikifolios_alle({'_render_liste_alle': _render_liste_alle, 'wikifolio_alle': wikifolio_alle}, teile=teile, stand=stand)

    def _render_liste_alle(art, werte, stand):
        return ranglisten_ansichten.liste_alle({'WK_SEITE': WK_SEITE, '_h': _h, '_listen_laenge': _listen_laenge, '_startauswahl': _startauswahl, '_startwert': _startwert, '_wk_seite': _wk_seite, 'vz_zahl': vz_zahl}, art=art, werte=werte, stand=stand)

    def _render_etfs():
        return ranglisten_ansichten._render_etfs({'_render_liste_alle': _render_liste_alle, 'etf_alle': etf_alle, 'gh_read_taeglich': gh_read_taeglich, 'ranglisten_stand': ranglisten_stand})

    def _render_wikifolios():
        return ranglisten_ansichten.wikifolios({'WK_SEITE': WK_SEITE, 'WK_SPALTEN': WK_SPALTEN, '_h': _h, '_listen_laenge': _listen_laenge, '_render_wikifolios_alle': _render_wikifolios_alle, '_wk_seite': _wk_seite, 'gh_read_taeglich': gh_read_taeglich, 'ranglisten_stand': ranglisten_stand, 'vz_zahl': vz_zahl, 'wikifolio_alle': wikifolio_alle, 'wikifolio_kennzahlen': wikifolio_kennzahlen, 'wikifolio_rangliste': wikifolio_rangliste, 'wikifolio_werte': wikifolio_werte})

    KS_SEITE = 25

    def _ks_de(x, dez=1):
        return ranglisten_ansichten._ks_de({}, x=x, dez=dez)

    def _ks_seite(nr):
        return ranglisten_ansichten._ks_seite({}, nr=nr)

    def _ks_rangliste(art):
        return ranglisten_ansichten._ks_rangliste({'gh_read_taeglich': gh_read_taeglich}, art=art)

    def _render_klassen_score():
        return ranglisten_ansichten.klassen_score({'KS_SEITE': KS_SEITE, 'Q_KLASSE_CSS': Q_KLASSE_CSS, '_h': _h, '_ks_de': _ks_de, '_ks_rangliste': _ks_rangliste, '_ks_seite': _ks_seite, '_ks_tabelle': _ks_tabelle, '_listen_laenge': _listen_laenge, 'vz_zahl': vz_zahl})

    def _ks_tabelle(spalten, zeilen):
        return ranglisten_ansichten._ks_tabelle({}, spalten=spalten, zeilen=zeilen)

    @st.fragment
    def _render_top50():
        return ranglisten_ansichten.ranglisten({'_render_etfs': _render_etfs, '_render_klassen_score': _render_klassen_score, '_render_performance': _render_performance, '_render_qualitaet': _render_qualitaet, '_render_qualitaet_kurs': _render_qualitaet_kurs, '_render_uebersicht': _render_uebersicht, '_render_wikifolios': _render_wikifolios, '_zugang_pruefen': _zugang_pruefen, 'notify_app_error': notify_app_error})

    if gewaehlte_ansicht == "🏆 Watchlist Top 50":
        melde("ansicht", 0.3, "Lade Ranglisten …")
        _render_top50()
        lade_fertig()

    # --- PORTFOLIO-PLANER: eigenes Modul (planer_daten / planer_engine /
    # planer_ui). Bekommt die vorhandenen Funktionen fuer Kurssuche, Historie
    # und GitHub-Speicher, statt sie doppelt zu implementieren.
    if gewaehlte_ansicht == "💼 Portfolio-Planer":
        melde("ansicht", 0.3, "Lade Portfolio-Planer …")
        try:
            import planer_ui
            planer_ui.render({
                "suche_instrument": suche_instrument, "get_kurshistorie": get_kurshistorie,
                "gh_read": gh_read, "gh_write": gh_write, "gh_read_taeglich": gh_read_taeglich,
                "chronik": chronik_eintrag, "heute": heute_date, "benchmarks": getattr(config, "BENCHMARKS", {}) or {},
                # benutzerbezogene Speicherorte (Admin: unveraendert), siehe nutzerdaten.py
                "upfad": upfad, "nutzer": _nutzer(), "gh_aktualisiere": gh_aktualisiere,
            })
        except Exception as e:
            st.error(f"⚠️ Fehler im Portfolio-Planer: {e}")
            notify_app_error("Tab-Portfolio-Planer", e)
        lade_fertig()

    # --- PORTFOLIO BUILDER 2.0: eigenstaendige, einfache Ein-Seiten-Ansicht
    # (Rechenkern portfolio_builder.py, Oberflaeche portfolio_builder_ui.py)
    if gewaehlte_ansicht == ANSICHT_BUILDER:
        _zugang_pruefen(ANSICHT_BUILDER)
        try:
            import portfolio_builder_ui
            portfolio_builder_ui.render({"gh_read": gh_read, "gh_write": gh_write,
                                         "gh_aktualisiere": gh_aktualisiere, "nutzer": _nutzer(),
                                         "gh_read_taeglich": gh_read_taeglich, "suche_instrument": suche_instrument,
                                         "get_live_kurs": get_live_kurs, "lade_historie": lade_rohhistorie,
                                         "zum_scanner": (lambda: _nav_waehle(ANSICHT_SCANNER))
                                         if _sichtbar(ANSICHT_SCANNER) else None})
        except Exception as e:
            st.error(f"⚠️ Fehler im Portfolio Builder: {e}")
            notify_app_error("Tab-Portfolio-Builder", e)
        lade_fertig()

    # --- INVESTMENT-SCANNER: eigene Ansicht; Kapital, Sparrate, Laufzeit, Ziel kommen aus dem Builder
    # (Rechenkern scanner.py, Oberflaeche scanner_ui.py)
    if gewaehlte_ansicht == ANSICHT_SCANNER:
        _zugang_pruefen(ANSICHT_SCANNER)
        try:
            import scanner_ui
            scanner_ui.seite({"gh_read": gh_read, "gh_write": gh_write, "gh_aktualisiere": gh_aktualisiere,
                              "nutzer": _nutzer(), "gh_read_taeglich": gh_read_taeglich,
                              "suche_instrument": suche_instrument, "get_live_kurs": get_live_kurs,
                              "chronik": chronik_eintrag, "zum_muster": lambda: _nav_waehle(ANSICHT_MUSTER),
                              "zum_builder": (lambda: _nav_waehle(ANSICHT_BUILDER))
                              if _sichtbar(ANSICHT_BUILDER) else None})
        except Exception as e:
            st.error(f"⚠️ Fehler im Investment-Scanner: {e}")
            notify_app_error("Tab-Investment-Scanner", e)
        lade_fertig()

    # --- INVESTMENT SCANNER 2.0: Nachbau des HTML-Scanners (Echtdaten & Entnahmen) mit den Top-500-Daten
    # (investment_scanner2.py / investment_scanner2_ui.py)
    if gewaehlte_ansicht == ANSICHT_SCANNER2:
        _zugang_pruefen(ANSICHT_SCANNER2)
        try:
            import investment_scanner2_ui
            investment_scanner2_ui.seite({"gh_read_taeglich": gh_read_taeglich, "suche_instrument": suche_instrument,
                                          "get_live_kurs": get_live_kurs, "null": eigener_bereich()})
        except Exception as e:
            st.error(f"⚠️ Fehler im Investment Scanner 2.0: {e}")
            notify_app_error("Tab-Investment-Scanner-2", e)
        lade_fertig()

    # --- BEWERTUNG: einen Wert der Top-500-Liste anhand aller vorhandenen Kennzahlen bewerten
    # (scoring.py / bewertung_ui.py) - liest nur die oeffentlichen Agenten-Dateien, schreibt nichts
    if gewaehlte_ansicht == ANSICHT_BEWERTUNG:
        @st.fragment
        def _render_bewertung():
            _zugang_pruefen(ANSICHT_BEWERTUNG)
            try:
                import bewertung_ui
                bewertung_ui.seite({"gh_read_taeglich": gh_read_taeglich, "gh_read": gh_read,
                                    "gh_aktualisiere": gh_aktualisiere, "speichern": GH_STATE_READY,
                                    "pfad_notizen": upfad("state/bewertung_notizen.json")})
            except Exception as e:
                st.error(f"⚠️ Fehler in der Bewertung: {e}")
                notify_app_error("Tab-Bewertung", e)
        _render_bewertung()
        lade_fertig()

    # --- WIKI-IDEE: Modelldepot (50 Aktien + 20 ETFs) - Liste nach Bedarf, Uebernahme nur auf Klick
    if gewaehlte_ansicht == ANSICHT_WIKI:
        @st.fragment
        def _render_wiki():
            _zugang_pruefen(ANSICHT_WIKI)
            try:
                import wiki_idee_ui
                wiki_idee_ui.seite({
                    "lesen": gh_read, "lesen_taeglich": gh_read_taeglich, "schreiben": gh_aktualisiere,
                    "schreiben_ok": GH_STATE_READY,
                    "live_kurs": lambda iid: _live_roh(str(iid))[0]})
            except Exception as e:
                st.error(f"⚠️ Fehler im KI_Invest_System: {e}")
                notify_app_error("Tab-Wiki-Idee", e)
        _render_wiki()
        lade_fertig()

    # --- ALTERSTEILZEIT & RENTENPLANUNG (atz_rechner/ + atz_ui.py) - eigenstaendiger Rechner; den Depotwert
    # liest er nur (letzter Stand der Depot-Ansicht in dieser App-Instanz), er veraendert nichts
    if gewaehlte_ansicht == ANSICHT_ATZ:
        def _atz_depotwert():
            """Gleicher Wert wie die Kachel "Depot gesamt" (depot_summe, zuletzt berechnet in der Depot-Ansicht)."""
            if not _sichtbar(ANSICHT_DEPOT):
                return None
            info = _depot_kurzinfo_speicher().get(st.session_state.get("login_name") or "_") or {}
            zeit = info.get("zeit")
            return {"wert": info.get("wert"),
                    "stand": zeit.strftime("%d.%m. %H:%M Uhr") if hasattr(zeit, "strftime") else ""}

        @st.fragment
        def _render_atz():
            _zugang_pruefen(ANSICHT_ATZ)
            try:
                import atz_ui
                atz_ui.seite({"depotwert": _atz_depotwert})
            except Exception as e:
                st.error(f"⚠️ Fehler im Altersteilzeit- & Rentenrechner: {e}")
                notify_app_error("Tab-Altersteilzeit", e)
        _render_atz()
        lade_fertig()

    # --- EKS-INVESTMENTBEWERTUNG (eks_rechner/ + eks_ui.py): Ideen fuer Nebengewerbe und Investments nach der
    # Engpasskonzentrierten Strategie bewerten; je Benutzer gespeichert (state/eks_ideen.json)
    if gewaehlte_ansicht == ANSICHT_EKS:
        @st.fragment
        def _render_eks():
            _zugang_pruefen(ANSICHT_EKS)
            try:
                import eks_ui
                eks_ui.seite({"gh_read": gh_read, "gh_aktualisiere": gh_aktualisiere,
                              "pfad": upfad("state/eks_ideen.json"), "speichern": GH_STATE_READY})
            except Exception as e:
                st.error(f"⚠️ Fehler in der EKS-Investmentbewertung: {e}")
                notify_app_error("Tab-EKS", e)
        _render_eks()
        lade_fertig()

    # --- ANALYSE-DEPOT: eigenes, vom echten Depot getrenntes Depot fuer die Depot-Analyse
    # (analyse_depot.py / analyse_depot_ui.py) - bequeme Erfassung, keine Depotberechnung noetig
    if gewaehlte_ansicht == ANSICHT_ANALYSE_DEPOT:
        _ad_h = {"gh_read": gh_read, "gh_aktualisiere": gh_aktualisiere, "pfad": upfad("state/analyse_depot.json"),
                 "speichern": GH_STATE_READY, "suche_instrument": suche_instrument, "get_live_kurs": get_live_kurs}

        @st.fragment
        def _render_analyse_depot():
            _zugang_pruefen(ANSICHT_ANALYSE_DEPOT)
            try:
                import analyse_depot_ui
                analyse_depot_ui.seite(_ad_h)
            except Exception as e:
                st.error(f"⚠️ Fehler im Analyse-Depot: {e}")
                notify_app_error("Tab-Analyse-Depot", e)
        _render_analyse_depot()
        lade_fertig()

    # --- INVESTMENT SCANNER PRO: eigenstaendiges Board mit eigenen Eingaben (Kaufplan, Reserve,
    # Sofortentnahme); keine gemeinsamen Eingaben mit dem Builder (investment_scanner_pro.py)
    if gewaehlte_ansicht == ANSICHT_SCANNER_PRO:
        _zugang_pruefen(ANSICHT_SCANNER_PRO)
        try:
            import investment_scanner_pro
            investment_scanner_pro.seite({"gh_read_taeglich": gh_read_taeglich, "suche_instrument": suche_instrument,
                                          "get_live_kurs": get_live_kurs, "null": eigener_bereich()})
        except Exception as e:
            st.error(f"⚠️ Fehler im Investment Scanner Pro: {e}")
            notify_app_error("Tab-Investment-Scanner-Pro", e)
        lade_fertig()


    if gewaehlte_ansicht == ANSICHT_BENUTZER:
        try:
            waehlbar = [a for a in ANSICHTEN if a not in (ANSICHT_BENUTZER, ANSICHT_GLOSSAR)]
            def _gh_write_frisch(*args, **kwargs):
                # nach dem Speichern den 60-s-Zwischenspeicher leeren: Sperren und
                # Rechte wirken dann bei den anderen Benutzern beim naechsten Klick
                ok = gh_write(*args, **kwargs)
                gh_read_cached.clear()
                return ok
            def _daten_loeschen(name):
                # Datenordner state/benutzer/<name>/ entfernen (nie Admin- oder gemeinsame Daten)
                o = nutzerdaten.ordner({"name": name, "rolle": "benutzer"})
                if not o or not GH_STATE_READY:
                    return False, 0
                ok, anzahl = github_store.loesche_ordner(GITHUB_REPO, config.GITHUB_STATE_BRANCH, o, GITHUB_TOKEN,
                                                         message=f"benutzerdaten {nutzerdaten.slug(name)} geloescht")
                gh_read_cached.clear()
                return ok, anzahl

            login.render_verwaltung(st, gh_read, _gh_write_frisch, waehlbar, NAV_NAMEN,
                                    gh_aktualisiere=gh_aktualisiere, daten_loeschen=_daten_loeschen)
        except Exception as e:
            st.error(f"⚠️ Fehler in der Benutzerverwaltung: {e}")
            notify_app_error("Tab-Benutzer", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_ZINS:
        try:
            import zinsrechner
            # Normale Benutzer starten bei 0, der Admin mit den bisherigen Standardwerten;
            # danach gelten die gemerkten Eingaben (je Benutzer)
            _gemerkt = rechner_vorbelegen("zinsrechner")
            zinsrechner.render(_app_url(), gespeichert=_gemerkt, null=eigener_bereich())
            rechner_merken("zinsrechner")
            rechner_leiste("zinsrechner")
        except Exception as e:
            st.error(f"⚠️ Fehler im Zinseszinsrechner: {e}")
            notify_app_error("Tab-Zinsrechner", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_ABFINDUNG:
        try:
            import abfindung
            _gemerkt = rechner_vorbelegen("abfindung")
            abfindung.render(gespeichert=_gemerkt, null=eigener_bereich())
            rechner_merken("abfindung")
            rechner_leiste("abfindung")
        except Exception as e:
            st.error(f"⚠️ Fehler im Abfindungsrechner: {e}")
            notify_app_error("Tab-Abfindungsrechner", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_MUSTER:
        melde("ansicht", 0.3, "Lade Musterdepot …")
        try:
            import planer_ui
            planer_ui.render_musterdepot({"gh_read": gh_read, "gh_write": gh_write, "get_live_kurs": get_live_kurs,
                                          "gh_read_taeglich": gh_read_taeglich,
                                          "chronik": chronik_eintrag, "upfad": upfad, "nutzer": _nutzer(),
                                          "gh_aktualisiere": gh_aktualisiere})
        except Exception as e:
            st.error(f"⚠️ Fehler im Musterdepot: {e}")
            notify_app_error("Tab-Musterdepot", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_GLOSSAR:
        glossar_ui.seite(st)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_DK:
        try:
            import durchschnittskurs_ui
            rechner_vorbelegen("durchschnittskurs")
            durchschnittskurs_ui.seite()
            rechner_merken("durchschnittskurs")
            rechner_leiste("durchschnittskurs")
        except Exception as e:
            st.error(f"⚠️ Fehler im Durchschnittskurs-Rechner: {e}")
            notify_app_error("Tab-Durchschnittskurs", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_ETP:
        try:
            import etp_rechner_ui
            rechner_vorbelegen("etp_rechner")
            etp_rechner_ui.seite({"indizes": lambda: kurs_vorrat().indizes(), "ohlc": lambda: kurs_vorrat().ohlc(),
                                  "abrufen": lambda sym: indizes.abrufen(
                                      sym, requests.get, datetime.datetime.now(datetime.timezone.utc).isoformat()),
                                  "zum_ko": _ko_uebernehmen, "get": requests.get})
            rechner_merken("etp_rechner")
            rechner_leiste("etp_rechner")
        except Exception as e:
            st.error(f"⚠️ Fehler im ETF-/ETP-Hebelrechner: {e}")
            notify_app_error("Tab-ETP-Rechner", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_KO:
        try:
            import ko_rechner_ui
            rechner_vorbelegen("ko_rechner")
            ko_rechner_ui.seite({"indizes": lambda: kurs_vorrat().indizes(), "get": requests.get,
                                 "abrufen": lambda sym: indizes.abrufen(
                                     sym, requests.get, datetime.datetime.now(datetime.timezone.utc).isoformat())})
            rechner_merken("ko_rechner")
            rechner_leiste("ko_rechner")
        except Exception as e:
            st.error(f"⚠️ Fehler im Knock-out-Rechner: {e}")
            notify_app_error("Tab-KO-Rechner", e)
    if gewaehlte_ansicht == ANSICHT_GAP:
        try:
            import gap_analyzer_ui
            import opening_gaps_ui
            rechner_vorbelegen("gap_analyzer")
            gap_analyzer_ui.seite({"ohlc": lambda: kurs_vorrat().ohlc(), "indizes": lambda: kurs_vorrat().indizes(),
                                   "intraday": lambda: kurs_vorrat().opening_intraday(),
                                   "live": opening_gaps_ui.live_abruf_yahoo})
            rechner_merken("gap_analyzer")
            rechner_leiste("gap_analyzer")
        except Exception as e:
            st.error(f"⚠️ Fehler im Gap Analyzer: {e}")
            notify_app_error("Tab-GapAnalyzer", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_YT:
        @st.fragment
        def _render_youtube():
            _zugang_pruefen(ANSICHT_YT)
            try:
                import youtube_ui

                def _hat(name):                      # nur ob ein Schluessel eingerichtet ist - nie seinen Wert
                    try:
                        return bool(st.secrets.get(name) or os.environ.get(name))
                    except Exception:
                        return bool(os.environ.get(name))
                import github_release

                def _ki():
                    import ki_anbieter
                    try:
                        return ki_anbieter.verfuegbar(st.secrets)
                    except Exception:
                        return ki_anbieter.verfuegbar()
                _code_repo = st.secrets.get("CODE_REPO", "") or "wikifolio-user/wikifolio-tracker"
                import youtube_api
                try:                                 # Schluessel nur in der Abruf-Funktion, nie in der Oberflaeche
                    _yt_key = st.secrets.get("YOUTUBE_API_KEY") or os.environ.get("YOUTUBE_API_KEY") or ""
                except Exception:
                    _yt_key = os.environ.get("YOUTUBE_API_KEY") or ""
                import youtube_upload

                def _yt_upload():               # OAuth nur aus den Secrets; ohne alle drei Werte kein Upload
                    try:
                        w = {n: st.secrets.get(n) or os.environ.get(n) for n in youtube_upload.SECRETS}
                    except Exception:
                        w = {n: os.environ.get(n) for n in youtube_upload.SECRETS}
                    if not all(w.values()):
                        return None
                    return {"zugang": lambda: youtube_upload.zugang(*(w[n] for n in youtube_upload.SECRETS),
                                                                    requests.post),
                            "post": requests.post, "put": requests.put}
                youtube_ui.seite({"lesen": gh_read_cached_status, "aktualisiere": gh_aktualisiere, "upfad": upfad,
                                  "speichern": GH_STATE_READY, "get": requests.get, "ki": _ki,
                                  "render_starten": lambda pid: github_release.workflow_starten(
                                      _code_repo, "youtube-render.yml", GITHUB_TOKEN, {"projekt": pid}),
                                  "release_laden": lambda aid: github_release.laden(GITHUB_REPO, aid, GITHUB_TOKEN),
                                  "musik_hochladen": lambda pfad, name, typ: github_release.hochladen(
                                      GITHUB_REPO, github_release.release_holen(GITHUB_REPO, "musik", GITHUB_TOKEN,
                                                                                "Eigene Musik (Video Factory)"),
                                      pfad, GITHUB_TOKEN, name, "audio/" + {"mp3": "mpeg", "m4a": "mp4"}.get(typ, typ))
                                  ["id"],
                                  "yt_abruf": youtube_api.verbindung(_yt_key, requests.get) if _yt_key else None,
                                  "yt_upload": _yt_upload(),
                                  "zugaenge": {n: _hat(n) for n, *_ in youtube_ui.ZUGAENGE}})
            except Exception as e:
                st.error(f"⚠️ Fehler im Bereich Faceless YouTube: {e}")
                notify_app_error("Tab-YouTube", e)
        _render_youtube()
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_PYR:
        try:
            import pyramide_ui
            pyramide_ui.seite({"ohlc": lambda: kurs_vorrat().ohlc(), "sentiment": lambda: kurs_vorrat().sentiment(),
                               "indizes": lambda: kurs_vorrat().indizes(), "lesen": gh_read_cached_status,
                               "aktualisiere": gh_aktualisiere, "upfad": upfad, "speichern": GH_STATE_READY,
                               "get": requests.get,
                               "aktien_depot": lade_positionen,
                               "bewertung_daten": lambda: __import__("bewertung_ui").daten(
                                   {"gh_read_taeglich": gh_read_taeglich}),
                               "investoren": lambda: __import__("investoren_ui").vorberechnet(
                                   {"gh_read_taeglich": gh_read_taeglich})[0],
                               "oeffnen": lambda z: _nav_waehle({"gap": ANSICHT_GAP, "fg": ANSICHT_FG}[z])})
        except Exception as e:
            st.error(f"⚠️ Fehler im Pyramidenmanager: {e}")
            notify_app_error("Tab-Pyramiden", e)
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_FG:
        try:
            import fear_greed_ui
            import markt_daten
            rechner_vorbelegen("fear_greed")
            fear_greed_ui.seite({"sentiment": lambda: kurs_vorrat().sentiment(), "ohlc": lambda: kurs_vorrat().ohlc(),
                                 "abrufen": lambda: markt_daten.sentiment_abrufen(
                                     requests.get, datetime.datetime.now(datetime.timezone.utc))})
            rechner_merken("fear_greed")
            rechner_leiste("fear_greed")
        except Exception as e:
            st.error(f"⚠️ Fehler im Fear & Greed Monitor: {e}")
            notify_app_error("Tab-FearGreed", e)
        lade_fertig()

    # --- GESUNDHEIT (gesundheit/ + gesundheit_ui.py): nur fuer den angemeldeten Admin; Daten im privaten State-Repo
    if gewaehlte_ansicht == ANSICHT_GESUNDHEIT:
        @st.fragment
        def _render_gesundheit():
            _zugang_pruefen(ANSICHT_GESUNDHEIT)
            try:
                import gesundheit_ui
                def _liste(ordner):
                    return [p for p, _ in github_store._liste(GITHUB_REPO, config.GITHUB_STATE_BRANCH, ordner,
                                                              GITHUB_TOKEN) if p.endswith(".json")]

                def _ordner_loeschen(ordner):
                    if not GH_STATE_READY:
                        return False, 0
                    ok, anzahl = github_store.loesche_ordner(GITHUB_REPO, config.GITHUB_STATE_BRANCH, ordner,
                                                             GITHUB_TOKEN, message="gesundheitsdaten geloescht")
                    gh_read_cached.clear()
                    return ok, anzahl
                try:                                   # Foto-Erkennung: derselbe Gemini-Schluessel wie die KI-Auswertung
                    _gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
                except Exception:
                    _gemini_key = os.environ.get("GEMINI_API_KEY")
                gesundheit_ui.seite({"lesen": gh_read_cached_status, "aktualisiere": gh_aktualisiere, "upfad": upfad,
                                     "speichern": GH_STATE_READY, "get": requests.get, "post": requests.post,
                                     "liste": _liste, "ordner_loeschen": _ordner_loeschen,
                                     "ki": {"key": _gemini_key, "modell": "gemini-flash-latest"}})   # immer aktuelles Flash-Modell
            except Exception as e:
                st.error("⚠️ Im Gesundheitsbereich ist ein Fehler aufgetreten. Bitte lade die Seite neu.")
                notify_app_error("Tab-Gesundheit", e)
        _render_gesundheit()
        lade_fertig()

    if gewaehlte_ansicht == "📝 Trader-Log (Trades & Kommentare)":
        melde("ansicht", 0.3, "Lade Chronik …")
        render_chronik()
        lade_fertig()

    # Watchlist und Portfolio-Planer brauchen keine Depot- oder Kursdaten -
    # dort endet der Aufbau hier, ohne Live-Kurs, Historie und Vergleichswerte.
    if gewaehlte_ansicht is None or gewaehlte_ansicht in LEICHTE_ANSICHTEN:
        lade_fertig()
        begriffe_erklaeren(gewaehlte_ansicht)
        return

    melde("live", 0.0, "Rufe Live-Kurs ab …")
    aktueller_kurs, vortag_kurs, fetched_source = get_live_market_data()
    is_live_data = "Fehler" not in fetched_source
    kurs_zeit = kurs_zeitpunkt(config.LS_INSTRUMENT_ID) if is_live_data else None
    kurs_tag = kurs_zeit.date() if kurs_zeit is not None else heute_date

    # --- HAUPTPOSITION: EINE Quelle (Audit A-04/A-05) ---
    # Kaufdatum, Kaufkurs und Kapital kommen aus der gespeicherten ersten Position
    # (positionen.json, bearbeitbar unter "Positionen verwalten"), sonst aus config.py.
    # Keine automatische Kursermittlung mehr: die Stueckzahl haengt so nie davon ab,
    # ob die Kurshistorie gerade erreichbar ist.
    eigen = eigener_bereich()
    alle_positionen = lade_positionen()
    _haupt = hauptposition_werte(alle_positionen, eigen)
    kaufdatum_aktiv = _haupt["kaufdatum"]
    kaufkurs_aktiv = _haupt["kaufkurs"]
    startkapital_aktiv = _haupt["startkapital"]
    haupt_abweichend = _haupt["abweichend"]
    stueckzahl_aktiv = startkapital_aktiv / kaufkurs_aktiv

    melde("historie", 0.0, "Lade Kurshistorie …")
    df_chart, hist_source_name = get_historical_market_data(kaufdatum_aktiv, heute_date)
    is_live_history = hist_source_name != KEINE_HISTORIE

    if not eigen:       # Datenquellen-Alarm (Discord + gemeinsamer Zustand): nur Admin / ohne Login
        check_and_alert_fetch_failure(is_live_data, is_live_history)

    # Kein Live-Kurs: nur ECHTE Ersatzwerte, jeweils mit Datum (Audit A-06) -
    # 1. letzter Schlusskurs der ls-tc-Historie, 2. letzter vom Workflow gespeicherte Kurs.
    # Gibt es keinen echten Kurs, werden keine Depotwerte angezeigt.
    if not is_live_data:
        if is_live_history and not df_chart.empty:
            aktueller_kurs = float(df_chart["Close"].iloc[-1])
            vortag_kurs = float(df_chart["Close"].iloc[-2]) if len(df_chart) > 1 else aktueller_kurs
            kurs_zeit = df_chart.index[-1].to_pydatetime()
            fetched_source = f"⚠️ letzter Schlusskurs vom {kurs_zeit.strftime('%d.%m.%Y')} (keine Live-Daten)"
        else:
            _gesp_kurs, _gesp_zeit = gespeicherter_kurs_hauptposition(heute_date)
            if _gesp_kurs:
                aktueller_kurs = vortag_kurs = _gesp_kurs
                kurs_zeit = _gesp_zeit
                fetched_source = (f"⚠️ letzter gespeicherter Kurs vom {_gesp_zeit.strftime('%d.%m.%Y %H:%M')} "
                                  "(keine Live-Daten)")
            else:
                st.error("⚠️ Gerade ist **kein echter Kurs** für die Hauptposition verfügbar (ls-tc.de "
                         "nicht erreichbar, keine gespeicherten Kurse). Depotwerte werden deshalb nicht "
                         "angezeigt – bitte später mit 🔄 erneut laden.")
                lade_fertig()
                return


    # Audit DEP-10: Live-Kurs als eigener Punkt fuer HEUTE (Index wird verlaengert,
    # der gestrige Schlusskurs bleibt erhalten) - die Vergleichswerte haengen ihren
    # Live-Kurs ebenfalls an heute an, beide Linien enden so am selben Datum.
    if is_live_data and is_live_history:
        # Punkt am Kalendertag des Kurses (am Wochenende: Freitag), nicht am Abruftag
        df_chart = haenge_live_punkt_an(df_chart, kurs_tag, aktueller_kurs)

    df_chart["Startkapital"] = startkapital_aktiv

    # --- HIGH WATERMARK: NUR ANZEIGE (Audit DATA-03/DEP-04) ---
    # Den gespeicherten Hoechststand pflegt allein der Workflow (discord_price_alert.py,
    # inkl. Initialisierung/Selbstheilung aus der Historie und Meldeschwelle). Schriebe
    # die App ihn mit, wuerde sie dort 'zuletzt_gemeldet' umgehen bzw. bei Ersatzdaten
    # ein erfundenes Hoch speichern. Angezeigt wird das hoehere aus Speicher und Historie.
    hw_state = gh_read_cached(config.STATE_PATH_HIGH_WATERMARK, None)
    try:
        gespeichertes_hoch = (float(hw_state["high_watermark"])
                              if isinstance(hw_state, dict) and hw_state.get("high_watermark") is not None else 0.0)
    except (TypeError, ValueError):
        gespeichertes_hoch = 0.0
    hist_hoch, hist_hoch_datum = 0.0, None
    if is_live_history and not df_chart.empty:       # synthetische Reihe liefert kein Hoch
        hist_hoch = float(df_chart["Close"].max())
        hist_hoch_datum = df_chart["Close"].idxmax()
    if hist_hoch and hist_hoch >= gespeichertes_hoch:
        high_watermark_anzeige = hist_hoch
        high_watermark_datum = hist_hoch_datum.strftime("%d.%m.%Y")
    elif gespeichertes_hoch:
        high_watermark_anzeige = gespeichertes_hoch
        try:
            high_watermark_datum = datetime.datetime.fromisoformat(
                str(hw_state.get("erreicht_am"))).strftime("%d.%m.%Y")
        except Exception:
            high_watermark_datum = "-"
    else:
        high_watermark_anzeige = aktueller_kurs
        high_watermark_datum = "-"
    hw_bekannt = high_watermark_datum != "-"         # ohne Historie/Speicher kein "Allzeithoch" behaupten

    start_dt = pd.to_datetime(kaufdatum_aktiv)

    # --- SPARPLAN: Rate + Startdatum persistent (Audit DEP-02) ---
    # Rate und Phasen liegen in STATE_PATH_SPARPLAN und belegen das Eingabefeld vor.
    # Gespeichert/beendet wird NUR per Knopf in den Einstellungen - eine neue Sitzung
    # (leerer session_state) aendert nichts mehr am gespeicherten Plan.
    # Jede Einzahlung kauft Anteile zum Kurs am/vor dem Termin; nur ausgefuehrte
    # Kaeufe zaehlen zum Einstand (DEP-01).
    sparplan_state, sparplan_lesbar = gh_read_cached_status(upfad(config.STATE_PATH_SPARPLAN), {})
    sparplan_start, sparplan_phasen_liste = sparplan_phasen(sparplan_state)
    if not GH_STATE_READY:
        _lokal = float(st.session_state.get("haupt_sparrate_input", 0.0) or 0.0)
        if _lokal > 0:
            _ls = st.session_state.setdefault("_sparplan_start_lokal", heute_date.isoformat())
            sparplan_start = datetime.date.fromisoformat(_ls)
            sparplan_phasen_liste = [(sparplan_start, _lokal)]
        else:
            sparplan_start, sparplan_phasen_liste = None, []
    sparrate_aktiv = sparplan_phasen_liste[-1][1] if sparplan_phasen_liste else 0.0
    # Altbestand: Plan laeuft, die Rate wurde frueher aber nicht gespeichert
    sparplan_ohne_rate = sparplan_start is not None and not sparplan_phasen_liste

    sparplan_termine_liste = (sparplan_termine(sparplan_start, heute_date)
                              if sparplan_start is not None and sparplan_phasen_liste else [])
    sparplan_kaufliste = []
    sparplan_ohne_kurse = False
    if sparplan_termine_liste:
        if is_live_history and not df_chart.empty:
            sparplan_kaufliste = sparplan_einzelkaeufe(
                sparplan_termine_liste, df_chart["Close"],
                lambda t: sparrate_am(sparplan_phasen_liste, t),
                ersatzkurs=aktueller_kurs if is_live_data else None,
            )
        else:
            sparplan_ohne_kurse = True      # ohne echte Kurshistorie keine Kaeufe (DEP-04)
    sparplan_eingezahlt = sum(k[1] for k in sparplan_kaufliste)
    zusaetzliche_stueckzahl_sparplan = sum(k[2] for k in sparplan_kaufliste)

    # --- ENTNAHME: EINE Quelle (Audit DEP-03) ---
    # Gespeicherte Monatsrate (Standard config.ENTNAHME_PM, normale Benutzer 0), erstmals
    # einen Monat nach dem Kauf, dann monatlich (DateOffset, Monatsenden gekappt - DEP-11).
    # Derselbe Terminplan und dieselbe Rate gelten fuer Netto (buchhalterisch) und Real
    # (Verkauf). Normale Benutzer: ab ihrem eigenen Sparplan-Start (sonst keine Termine).
    entnahme_state, entnahme_lesbar = gh_read_cached_status(upfad(STATE_PATH_ENTNAHME), None)
    entnahme_gespeichert = entnahme_rate_aus_state(entnahme_state, entnahme_standard(eigen))
    if GH_STATE_READY:
        entnahme_rate = entnahme_gespeichert
    else:                                   # ohne persistenten State: nur Sitzungswert
        entnahme_rate = float(st.session_state.get("haupt_entnommen_input", entnahme_gespeichert) or 0.0)
    _entnahme_ab = sparplan_start if eigen else kaufdatum_aktiv
    entnahme_termine_liste = entnahme_termine(_entnahme_ab, heute_date) if _entnahme_ab else []
    anzahl_entnahmen = len(entnahme_termine_liste)
    df_chart["Kumulierte_Entnahme"] = kumulierte_entnahme(df_chart.index, entnahme_termine_liste, entnahme_rate)

    # Hauptposition (Kachel "Depotwert", Charts, 100k-Meilenstein): Admin / ohne Login immer,
    # normale Benutzer nur mit eigenem Sparplan (kein Startkapital - das gehoert dem Admin).
    haupt_aktiv = haupt_position_aktiv(eigen, sparplan_phasen_liste, sparplan_eingezahlt)

    # --- BENCHMARKS: gleiche Handelstage, normiert auf dasselbe Startkapital ---
    # Zentrierter Ladefortschritt mit Prozentangabe statt Streamlits kleinem
    # "Running get_benchmark_history(...)"-Widget oben rechts (per CSS
    # ausgeblendet). Jeder Vergleichswert ist ein eigener Netzabruf, deshalb
    # laesst sich der Fortschritt hier ehrlich in Schritten anzeigen.
    def lade_benchmarks_mit_fortschritt(df_index, start_datum, kapital, hinweis='Lade Vergleichswerte'):
        return charts_ansichten.lade_benchmarks_mit_fortschritt({'benchmark_normiert_auf_startkapital': benchmark_normiert_auf_startkapital, 'heute_date': heute_date, 'lade_vergleichswerte': lade_vergleichswerte, 'melde': melde, 'vergleich_label': vergleich_label, 'vergleichswerte_vorladen': vergleichswerte_vorladen}, df_index=df_index, start_datum=start_datum, kapital=kapital, hinweis=hinweis)

    # Nur fuer den Vermoegensaufbau-Chart der Hauptposition (Admin) gebraucht - in allen anderen
    # Ansichten (Depot, Analyse, Prognose …) wird nichts davon angezeigt, also auch nichts geladen.
    if eigen or gewaehlte_ansicht != "📈 Vermögens- & Substanzaufbau":
        benchmark_series, benchmark_start_daten = {}, {}
    else:
        benchmark_series, benchmark_start_daten = lade_benchmarks_mit_fortschritt(
            df_chart.index, kaufdatum_aktiv, startkapital_aktiv
        )

    # --- SIMULATION (bisheriges Verhalten): Stückzahl bleibt konstant, Entnahme
    # wird nur buchhalterisch vom Bruttowert abgezogen. ---
    # Sparplan-Anteile ab ihrem Kauftag in allen Reihen (Audit A-09)
    df_chart["Sparplan_Stueck"], df_chart["Sparplan_Einzahlung"] = (
        sparplan_verlauf(df_chart.index, sparplan_kaufliste) if not df_chart.empty else ([], []))
    df_chart["Eingezahlt"] = startkapital_aktiv + df_chart["Sparplan_Einzahlung"]
    df_chart["Depotwert_Brutto"] = df_chart["Close"] * (stueckzahl_aktiv + df_chart["Sparplan_Stueck"])

    def zeige_chart_legende_liste(eintraege):
        return charts_ansichten.zeige_chart_legende_liste({}, eintraege=eintraege)

    def lese_pills_auswahl_still(labels, key):
        return charts_ansichten.lese_pills_auswahl_still({}, labels=labels, key=key)

    def pills_auswahl(labels, key):
        return charts_ansichten.pills_auswahl({}, labels=labels, key=key)

    def pct_ueber_tage(reihe, tage):
        return charts_ansichten.pct_ueber_tage({}, reihe=reihe, tage=tage)

    def kennzahl_umschalter(key, eintraege):
        return charts_ansichten.kennzahl_umschalter({}, key=key, eintraege=eintraege)

    def performance_tabelle_html(eintraege, eigene_kennung=None, fokus='jaehrlich'):
        return charts_ansichten.performance_tabelle_html({'_h': _h, 're': re, 'vz_zahl': vz_zahl}, eintraege=eintraege, eigene_kennung=eigene_kennung, fokus=fokus)

    # Kennzahlen je Zeitraum: module-weites berechne_performance_kennzahlen() (Audit DEP-08:
    # Ø/Jahr erst ab 365 Tagen, sonst None -> "–" in der Tabelle).

    # --- REAL: Entnahme durch tatsaechlichen Verkauf von Anteilen zum GELDKURS (Mid minus
    # Spread) - gleicher Terminplan und gleiche Rate wie die Netto-Simulation (DEP-03). ---
    df_chart["Stueckzahl_Real"] = berechne_reale_stueckzahl(
        df_chart, stueckzahl_aktiv, entnahme_rate, entnahme_termine_liste, config.SPREAD_PCT
    )
    df_chart["Depotwert_Real"] = df_chart["Close"] * (df_chart["Stueckzahl_Real"] + df_chart["Sparplan_Stueck"])

    # Kurs-Alarme (Schwelle/Entwarnung/Allzeithoch) verschickt die App NICHT mehr
    # (Audit DATA-03): einziger Absender und einziger Schreiber des Alarm-Zustands ist
    # der GitHub-Workflow discord_price_alert.py. Die App zeigt nur an.

    # --- RENDITE-KENNZAHLEN: zwei verschiedene Fragen, zwei Verfahren ---
    # 1) "Wie lief es fuer MICH bisher?" -> Kurs gegen den eigenen Kaufkurs.
    #    Das ist die realisierte Rendite dieser Position und gehoert genau so
    #    auf die Depotwert-Kachel und in die Vergleichstabellen.
    tage_gehalten = max(1, (heute_date - kaufdatum_aktiv).days)
    # Audit DEP-08 / Nutzerentscheid: ab 1 Jahr realisiert p.a., darunter ab 1 Monat
    # aus der Ø-Monatsrendite hochgerechnet (mit Hinweis), unter 1 Monat None / "n. a."
    if tage_gehalten >= 365:
        erwartete_rendite_pa = realisierte_rendite_pa(aktueller_kurs, kaufkurs_aktiv, tage_gehalten, 365)
        erwartete_rendite_hinweis = None
    else:
        _hr = hochgerechnete_rendite_pa(aktueller_kurs, kaufkurs_aktiv, tage_gehalten)
        erwartete_rendite_pa = _hr[0] if _hr else None
        erwartete_rendite_hinweis = (f"hochgerechnet aus {_hr[1]:.1f} Monaten (Ø Monatsrendite)"
                                     if _hr else None)

    # 2) "Womit ist kuenftig zu rechnen?" -> robuste Schaetzung aus der
    #    Kurshistorie des PRODUKTS (Trend-Regression + lange Zeitfenster,
    #    Median daraus). Nur fuer Hochrechnungen in die Zukunft: 100k-
    #    Meilenstein, Zukunfts-Prognose, Szenario-Simulator. Ein einzelner
    #    guenstiger Einstiegszeitpunkt soll die Zukunft nicht vorzeichnen.
    prognose_rendite_pa, prognose_rendite_details = produkt_rendite_pa(
        config.LS_INSTRUMENT_ID, heute_date
    )
    prognose_rueckfall_hinweis = None
    if prognose_rendite_pa is None:          # zu wenig Historie -> eigener Kauf als Rueckfall
        # < 1 Jahr: Ø-Monatsrendite auf ein Jahr hochgerechnet (ab 1 Monat), sonst 0 %
        prognose_rendite_pa, prognose_rueckfall_hinweis = prognose_rate_rueckfall(
            aktueller_kurs, kaufkurs_aktiv, tage_gehalten)
        prognose_rendite_details = ([(prognose_rueckfall_hinweis, prognose_rendite_pa)]
                                    if prognose_rueckfall_hinweis else [])
    erwarteter_zins_mo = (1 + (prognose_rendite_pa / 100.0)) ** (1 / 12) - 1

    # --- SIDEBAR entfernt ---
    # Die ganze Seite ist ein Fragment; Streamlit verbietet Fragment-Reruns
    # (z. B. durch die Menue-Kacheln) das Schreiben in die Sidebar
    # (StreamlitInvalidLayoutContext). Kursmonitor, Prognose-Basis und
    # Test-Alarm stehen jetzt unter Einstellungen -> System-Status.

    # --- WARNBANNER: KEIN PERSISTENTER STATE KONFIGURIERT ---
    if not GH_STATE_READY:
        st.warning(
            "⚠️ Kein persistenter State konfiguriert (GITHUB_REPO/GITHUB_TOKEN fehlen in den "
            "Streamlit-Secrets). Trader-Log, Alarm-Cooldowns etc. gehen bei jedem Neustart der "
            "App verloren, da Streamlit Cloud kein dauerhaftes Dateisystem hat."
        )

    # --- WARNBANNER BEI FEHLENDEN LIVE-DATEN ---
    if not is_live_data or not is_live_history:
        st.error(
            "⚠️ Achtung: Es werden gerade **keine echten Live-Daten** von ls-tc.de angezeigt "
            "(Kurs und/oder Chart-Historie sind Fallback-/Synthetikwerte). "
            "Prüfe die Server-Logs bzw. die JSON-Struktur des ls-tc.de-Endpunkts."
        )

    # --- KENNZAHLEN ---
    tages_verenderung_pct = ((aktueller_kurs - vortag_kurs) / vortag_kurs) * 100 if vortag_kurs else 0.0


    # --- DEPOT-KENNZAHLEN seit Kauf (Audit DEP-01/DEP-03) ---
    # Einstand = Startkapital + tatsaechlich eingezahlte Sparraten; Netto = Brutto minus
    # Rate x Anzahl Entnahmetermine seit Kauf (gleicher Plan wie die Real-Variante).
    _kz = depot_kennzahlen(stueckzahl_aktiv, zusaetzliche_stueckzahl_sparplan, aktueller_kurs,
                           startkapital_aktiv, sparplan_eingezahlt, entnahme_rate, anzahl_entnahmen)
    brutto_ist = _kz["brutto"]
    einstand_aktiv = _kz["einstand"]
    gesamt_entnommen = _kz["entnommen"]

    # --- HAUPTZAHL: realer Depotwert nach den tatsaechlichen Entnahme-Verkaeufen (Audit A-12) ---
    # Ausgezahlt = Rate x tatsaechlich ausgefuehrte Verkaeufe (Termin <= letzter Kurstag).
    stueckzahl_real_ist = df_chart["Stueckzahl_Real"].iloc[-1] if not df_chart.empty else stueckzahl_aktiv
    _letzter_kurstag = df_chart.index[-1] if not df_chart.empty else None
    verkaeufe_ausgefuehrt = (sum(1 for t in entnahme_termine_liste if pd.Timestamp(t) <= _letzter_kurstag)
                             if _letzter_kurstag is not None and entnahme_rate else 0)
    _real = depot_kennzahlen_real(stueckzahl_real_ist, zusaetzliche_stueckzahl_sparplan, aktueller_kurs,
                                  einstand_aktiv, entnahme_rate * verkaeufe_ausgefuehrt)
    depotwert_real_ist = _real["wert"]
    ausgezahlt_ist = _real["ausgezahlt"]
    gewinn_real = _real["gewinn"]
    rendite_real_pct = _real["rendite_pct"]
    # Zahlungen mit Datum: Startkapital am Kaufdatum, jede ausgefuehrte Sparrate am Kauftag,
    # jede ausgefuehrte Entnahme am Termin (Auszahlung) - fuer die geldgewichtete Rendite p. a.
    _zahlungen = ([(kaufdatum_aktiv, startkapital_aktiv)] if startkapital_aktiv and kaufdatum_aktiv else [])
    _zahlungen += [(k[0], k[1]) for k in sparplan_kaufliste]
    if entnahme_rate and _letzter_kurstag is not None:
        _zahlungen += [(t, -entnahme_rate) for t in entnahme_termine_liste if pd.Timestamp(t) <= _letzter_kurstag]
    rendite_pa_real, rendite_pa_hochgerechnet = rendite_pa_seit_kauf(
        einstand_aktiv, depotwert_real_ist + ausgezahlt_ist, kaufdatum_aktiv, heute_date,
        zahlungen=_zahlungen if len(_zahlungen) > 1 else None, depotwert=depotwert_real_ist)

    kumulierte_sparrate_marktwert = zusaetzliche_stueckzahl_sparplan * aktueller_kurs

    sim_b = depotwert_real_ist
    monate_bis_ziel = 0
    while sim_b < 100000.0 and monate_bis_ziel < 600:
        sim_b = (sim_b * (1 + erwarteter_zins_mo)) - entnahme_rate + sparrate_aktiv
        monate_bis_ziel += 1

    monate_namen = {1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni", 
                    7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember"}

    if depotwert_real_ist >= 100000.0:
        meilenstein_datum_str, meilenstein_details_str = "Bereits erreicht", "Ziel erreicht"
    elif monate_bis_ziel < 600:
        ms_date = (now_berlin.replace(tzinfo=None) + pd.DateOffset(months=monate_bis_ziel)).date()
        meilenstein_datum_str = f"{monate_namen[ms_date.month]} {ms_date.year}"
        meilenstein_details_str = f"In ca. {monate_bis_ziel // 12} Jahren & {monate_bis_ziel % 12} Monaten"
    else:
        meilenstein_datum_str, meilenstein_details_str = "> 50 Jahre", "Unrealistisch"
    if prognose_rueckfall_hinweis and depotwert_real_ist < 100000.0:
        # Rate stammt aus dem Rueckfall (hochgerechnet bzw. 0 %) - sichtbar kennzeichnen
        _ms_basis = (prognose_rueckfall_hinweis.split(" – ")[0]
                     if prognose_rueckfall_hinweis.startswith("Hochgerechnet") else "0 % p.a. (Historie < 1 Monat)")
        meilenstein_details_str += f" · Basis {FMT.pct(prognose_rendite_pa, 1)} p.a., {_ms_basis}"

    richtung = "up" if tages_verenderung_pct >= 0 else "down"
    differenz_zum_vortag = aktueller_kurs - vortag_kurs

    # ---------- ANSICHT "DEPOT" ----------
    # Kurs/„Wert wählen“, Depotwert, Positionen, Einstellungen und Verwaltung
    # bilden jetzt die eigene Ansicht "Depot". In anderen Ansichten wird der
    # Bereich weiterhin aufgebaut (die Werte brauchen auch die Charts, und die
    # Eingabefelder behalten so ihren Zustand), aber per CSS ausgeblendet.
    _depot_bereich = st.container(key="depot_bereich")
    if gewaehlte_ansicht != ANSICHT_DEPOT:
        st.markdown('<style>.st-key-depot_bereich { display: none !important; }</style>',
                    unsafe_allow_html=True)
    _depot_bereich.__enter__()

    # ---------- KURS-KOPF: der Kurs ist die eine Zahl, die zaehlt ----------
    _kurs_art, _kurs_text = kurs_status(kurs_zeit, now_berlin, is_live_data)
    live_markup = kurs_pill(_kurs_art, _kurs_text)
    kurs_zeit_text = (kurs_zeit.strftime("%d.%m.%Y %H:%M Uhr") if kurs_zeit is not None else "unbekannt")

    def de_zahl(wert, nachkomma=2):
        return depot_verwalten_ansichten.de_zahl({}, wert=wert, nachkomma=nachkomma)

    # ---------- PERFORMANCE JE ZEITRAUM (Tag/Woche/Monat/Jahr/seit Kauf) ----------
    # Referenzkurse werden aus der Kurshistorie berechnet (letzter Schlusskurs
    # am/vor dem Stichtag) - generisch fuer jedes Instrument, kein Scraping
    # einer produktspezifischen Seite mehr. "Tag" nutzt den Vortageskurs,
    # "seit Kauf" die realen Werte gewinn_real/rendite_real_pct (inkl. ausgezahlter Entnahmen).
    #
    # WICHTIG - Einschraenkung: die €-Betraege je Zeitraum unterstellen eine ueber
    # den jeweiligen Zeitraum konstante Stueckzahl (aktuelle Stueckzahl rueckwirkend
    # angewendet). Bei zwischenzeitlichen Sparplan-Kaeufen ist das eine Naeherung.
    gesamt_stueckzahl_perf = stueckzahl_real_ist + zusaetzliche_stueckzahl_sparplan

    _hist_haupt = get_kurshistorie(
        config.LS_INSTRUMENT_ID, heute_date - datetime.timedelta(days=420), heute_date
    )
    periods_kurs = berechne_zeitraeume(aktueller_kurs, vortag_kurs, _hist_haupt, heute_date)

    periods_depot = [(lbl, d * gesamt_stueckzahl_perf, p) for lbl, d, p in periods_kurs]
    # "seit Kauf": Gewinn gegen den Einstand (Startkapital + Sparraten), Prozent auf
    # denselben Einstand (Audit DEP-01) - Euro und Prozent passen so zusammen.
    periods_depot.append(("seit Kauf", gewinn_real, rendite_real_pct))

    # Positionsliste einmalig laden - wird sowohl von der Verwaltung unten
    # als auch von den Positionskacheln weiter unten genutzt.
    alle_positionen = lade_positionen()
    # Normale Benutzer: KEINE Kachel der Admin-Hauptposition - nur ein eigener Sparplan
    # erzeugt sie; alle gespeicherten Positionen sind "weitere" Positionen.
    haupt_name, weitere_positionen = depot_aufteilung(alle_positionen, eigen)

    # ---------- POSITIONEN VERWALTEN (anlegen / aendern / loeschen) ----------
    def instrument_suchblock(prefix, label='WKN, ISIN oder Name suchen'):
        return depot_verwalten_ansichten.instrument_suchblock({'get_live_kurs': get_live_kurs, 'suche_instrument': suche_instrument}, prefix=prefix, label=label)

    def suche_zuruecksetzen(prefix):
        return depot_verwalten_ansichten.suche_zuruecksetzen({}, prefix=prefix)

    def positions_anlage_formular(prefix):
        return depot_verwalten_ansichten.positions_anlage_formular({'aendere_positionen': aendere_positionen, 'get_live_kurs': get_live_kurs, 'heute_date': heute_date, 'instrument_suchblock': instrument_suchblock, 'suche_zuruecksetzen': suche_zuruecksetzen, 'uuid': uuid}, prefix=prefix)

    # ---------- HIGH WATERMARK: als Zeile in der Kurskachel ----------
    # Bewusst KEINE eigene Kachel mehr: der Hoechststand ist eine Eigenschaft
    # des Kurses, keine gleichrangige Kennzahl. Als Zeile unter Vortag/Tag/
    # Woche steht er im richtigen Kontext und spart eine ganze Kachel.
    hw_abstand = aktueller_kurs - high_watermark_anzeige
    hw_abstand_pct = (hw_abstand / high_watermark_anzeige * 100) if high_watermark_anzeige else 0.0
    hw_am_hoch = hw_abstand >= -0.0005  # Toleranz gegen Rundungsrauschen

    if not hw_bekannt:
        hw_status_chip = ""
        hw_zeile = ""
    elif hw_am_hoch:
        hw_status_chip = '<span class="hw-pill">Allzeithoch</span>'
        hw_zeile = (
            '<div class="perf-row"><span class="perf-label">Höchststand</span>'
            f'<span class="perf-vals"><span class="neutral">{FMT.eur(high_watermark_anzeige, 2)}</span>'
            '<span class="up">erreicht</span></span></div>'
        )
    else:
        hw_status_chip = ""
        hw_zeile = (
            '<div class="perf-row"><span class="perf-label">Höchststand</span>'
            f'<span class="perf-vals"><span class="neutral">{FMT.eur(high_watermark_anzeige, 2)}</span>'
            f'<span class="down">{FMT.pct(hw_abstand_pct, 2)}</span></span></div>'
        )

    # Kurszeit steht in der Plakette ("Live" / "Stand 14:00") - die Fussnote wiederholt sie nicht mehr
    kurs_karte = depot_kachel_html(
        f"{_h(haupt_name)} · {_h(config.WKN)}", FMT.kurs(aktueller_kurs), chips=live_markup + hw_status_chip,
        zeilen=periods_kurs, kopfzeile=("Vortag", FMT.kurs(vortag_kurs)), fusszeile=hw_zeile,
        fussnote="Lang &amp; Schwarz · je Anteil"
        + (f' · Höchststand vom {high_watermark_datum}, ab dort {config.PERFORMANCE_FEE_PCT:.0f} % Performance Fee'
           if hw_bekannt else ''),
        klasse="quote", wert_klasse="q-price", titel_klasse="q-name")
    # ---------- BEOBACHTETE WERTE: reine Kursanzeige, NICHT im Depot ----------
    def beobachtungs_karte(eintrag, fortschritt=None, im_depot=False):
        return depot_verwalten_ansichten.beobachtungs_karte({'_h': _h, 'berechne_zeitraeume': berechne_zeitraeume, 'depot_kachel_html': depot_kachel_html, 'get_kurshistorie': get_kurshistorie, 'get_live_kurs': get_live_kurs, 'heute_date': heute_date, 'kurs_pill': kurs_pill, 'kurs_status': kurs_status, 'kurs_zeitpunkt': kurs_zeitpunkt, 'now_berlin': now_berlin}, eintrag=eintrag, fortschritt=fortschritt, im_depot=im_depot)

    beobachtung = [e for e in lade_beobachtung() if e.get("instrument_id")]

    # ---------- EIGENE PROGNOSE-BASIS (frueher: Beobachtungswerte) ----------
    # Die Liste pflegt jeder Benutzer in der Zukunfts-Prognose selbst (aus der Top-500-Liste);
    # ohne gespeicherte Liste gelten wie bisher die Werte der Beobachtungsliste.
    # Beobachtungswerte haben KEIN investiertes Kapital (reine Kursanzeige) -
    # trotzdem soll sich die Zukunfts-Prognose auch fuer sie nutzen lassen.
    # Basis: die eigene historische CAGR des Werts (aeltester verfuegbarer
    # Kurs vs. aktueller Kurs), hochgerechnet auf ein SYMBOLISCHES Startkapital
    # (10.000 € - dieselbe Konvention wie bei den Vergleichswerten in den
    # anderen Tabs). Das ist ausdruecklich eine "was-waere-wenn"-Rechnung,
    # kein echtes Investment - wird im Dropdown-Namen und im Infotext
    # entsprechend gekennzeichnet.
    SYMBOLISCHES_PROGNOSE_KAPITAL = 10000.0
    prognose_beobachtung_optionen = []
    # Nur Zukunfts-Prognose und Szenario-Simulator nutzen die Prognose-Basis - je Wert ein Live-Kurs und die
    # komplette Kurshistorie. In allen anderen Ansichten (v. a. am Handy spuerbar) wird nichts davon geladen.
    prognose_basis_liste = ([e for e in lade_prognose_basis() if e.get("instrument_id")]
                            if gewaehlte_ansicht in PROGNOSE_ANSICHTEN else [])
    _beob_gesamt = len(prognose_basis_liste)
    for _beob_i, _eintrag in enumerate(prognose_basis_liste):
        _beob_name = _eintrag.get("name") or _eintrag.get("wkn") or "Beobachtungswert"
        if _beob_gesamt:
            melde("beob_prognose", _beob_i / _beob_gesamt,
                  f"Lade Prognose-Basis {_beob_i + 1}/{_beob_gesamt} · {_beob_name} …")
        try:
            _b_kurs, _b_vortag, _ = get_live_kurs(_eintrag["instrument_id"])
            if not _b_kurs:
                continue
            _b_hist = get_kurshistorie(
                # KOMPLETTE Historie seit Auflegung (Start bei 100 €), nicht
                # nur die letzten 5 Jahre - so zaehlt die gesamte Entwicklung
                # des Werts mit, nicht ein willkuerlich abgeschnittener Teil.
                _eintrag["instrument_id"], datetime.date(2000, 1, 1), heute_date
            )
            if _b_hist.empty:
                continue
            _b_start_datum = _b_hist.index.min()
            # Robuste CAGR (Trend-Regression + lange Fenster) statt naivem
            # Zwei-Punkte-Vergleich - siehe Docstring von berechne_robuste_cagr().
            _b_cagr, _b_cagr_details = berechne_robuste_cagr(_b_kurs, _b_hist, heute_date)
            if _b_cagr is None:
                continue
            prognose_beobachtung_optionen.append({
                "name": f"{_beob_name} (symbolisch)",
                "startkapital": SYMBOLISCHES_PROGNOSE_KAPITAL,
                # WICHTIG: NICHT die historisch bereits gewachsene Summe -
                # die Zukunfts-Prognose soll HEUTE starten (wie bei allen
                # anderen Positionen auch), nicht rueckwirkend ab dem
                # historischen Ursprung. Sonst zeigt die "Start"-Zeile ein
                # Datum von vor mehreren Jahren, obwohl es um die Zukunft
                # geht - genau das hat zur Nachfrage gefuehrt, warum die
                # Prognose "ab 2021" statt "ab heute" startet.
                "aktueller_wert": SYMBOLISCHES_PROGNOSE_KAPITAL,
                "cagr_pa": _b_cagr,
                "cagr_details": _b_cagr_details,
                "kaufdatum": heute_date,
                # Nur fuer den Hinweistext: seit wann Kursdaten vorliegen.
                "cagr_seit": _b_start_datum.date(),
                "sparrate": 0.0,
                "entnahme": 0.0,
                "symbolisch": True,
                "kursreihe": _b_hist,
                "instrument_id": _eintrag["instrument_id"],
                "wkn": _eintrag.get("wkn", ""),
            })
        except Exception as e:
            logging.warning(f"Prognose-Basis für Beobachtungswert '{_beob_name}' fehlgeschlagen: {e}")

    # ---------- HERO: Depotwert ----------
    sparplan_zusatz = (
        f" · davon {_de_zahl(zusaetzliche_stueckzahl_sparplan, 4)} aus Sparplan"
        if zusaetzliche_stueckzahl_sparplan > 0 else ""
    )
    # Ø p.a. = eigene realisierte Rendite seit Kauf (Audit A-08) - dieselbe Zahl wie
    # "Ø/Jahr" in der Vergleichstabelle. Die Prognoserate steht nur in den Prognosen.
    pa_chip = (f'<span class="stat-chip"><span class="stat-chip-label">Ø p.a. seit Kauf'
               f'{" (hochgerechnet)" if rendite_pa_hochgerechnet else ""}</span>'
               f'<span class="stat-chip-val">{FMT.pct(rendite_pa_real, 1)}</span></span>'
               if rendite_pa_real is not None else '')
    depot_karte = depot_kachel_html(
        f"{_h(haupt_name)} · {_h(config.WKN)}", fmt(depotwert_real_ist, 2), chips=pa_chip,
        gv=(gewinn_real, rendite_real_pct), zeilen=periods_depot,
        fussnote=f'{_de_zahl(stueckzahl_real_ist + zusaetzliche_stueckzahl_sparplan, 4)} '
        f'Anteile{sparplan_zusatz} · Kurs {FMT.kurs(aktueller_kurs)} · Einstand {fmt(einstand_aktiv, 2)}'
        + (f' (Startkapital {fmt(startkapital_aktiv, 2)} + Sparraten {fmt(sparplan_eingezahlt, 2)})'
           if sparplan_eingezahlt > 0 else '')
        + (f' · {verkaeufe_ausgefuehrt} Entnahmen à {fmt(entnahme_rate, 2)} ausgezahlt ({fmt(ausgezahlt_ist, 2)}),'
           ' im Gewinn „seit Kauf“ enthalten' if ausgezahlt_ist > 0 else '')
        + (' · ⚠️ Sparplan ohne echte Kurshistorie nicht eingerechnet' if sparplan_ohne_kurse else '')
        + (f' · {_h(fetched_source)}' if not is_live_data else '')
        + (' · ⚠️ Entnahmen nicht abgezogen (Kurshistorie fehlt – Verkaufskurse unbekannt)'
           if df_chart.empty and entnahme_rate and entnahme_termine_liste else ''))
    # Alle Positionskacheln werden gesammelt und unter der Depot-Summe als aufklappbare Liste
    # ausgegeben: (Name, Kachel-HTML, Kurzinfo) - die Kurzinfo (Wert, Gewinn seit Kauf in %) steht in
    # der Zeile, die Kachel mit allen Zeitraeumen klappt auf (UX 10/2026: statt Reitern mit gekuerzten
    # Namen wie "Hauptindizes…").
    positions_karten = ([(haupt_name, depot_karte, (depotwert_real_ist, gewinn_real, rendite_real_pct))]
                        if haupt_aktiv else [])

    # =================================================================
    # WEITERE POSITIONEN + GESAMTUEBERSICHT
    # =================================================================
    # Die erste Position ist die oben ausfuehrlich dargestellte Hauptposition
    # (sie speist auch alle Tabs/Charts). Jede weitere Position bekommt eine
    # eigene Kachel im selben Design; darunter folgt die Depot-Gesamtsumme.

    # Kennzahlen der Hauptposition als Startwert der Gesamtsumme (ohne Hauptposition: 0)
    gesamt_wert = depotwert_real_ist if haupt_aktiv else 0.0
    gesamt_ausgezahlt = ausgezahlt_ist if haupt_aktiv else 0.0     # gehoert zum Ergebnis (A-12)
    gesamt_einstand = einstand_aktiv if haupt_aktiv else 0.0     # inkl. Sparraten (Audit DEP-01)
    # Je Position (aktueller Wert, {Zeitraum: Betrag}) - die Prozentbasis je Zeitraum
    # bilden nur die Positionen, die dafuer einen Wert liefern (Audit DEP-07).
    gesamt_beitraege = ([(depotwert_real_ist, {lbl: betrag for lbl, betrag, _ in periods_depot if lbl != "seit Kauf"})]
                        if haupt_aktiv else [])
    positionen_ok = True

    # Sammelt fuer jede Position mit echten Kursdaten die Basis-Kennzahlen
    # (Kapital, aktueller Wert, CAGR, Kaufdatum) - Grundlage fuer die Auswahl
    # in der Zukunfts-Prognose weiter unten. Beobachtungswerte fehlen hier
    # bewusst: ohne investiertes Kapital ergibt eine Kapitalprognose keinen Sinn.
    prognose_optionen = [{
        "name": haupt_name,
        "startkapital": startkapital_aktiv,
        "aktueller_wert": depotwert_real_ist,
        # Zukunftsrate (Produkt-Historie), NICHT die eigene Kaufrendite -
        # siehe Kommentar bei prognose_rendite_pa weiter oben.
        "cagr_pa": prognose_rendite_pa,
        "cagr_details": prognose_rendite_details,
        "cagr_rueckfall_hinweis": prognose_rueckfall_hinweis,
        "kaufdatum": kaufdatum_aktiv,
        "sparrate": sparrate_aktiv,
        # Monatliche Entnahme (EINE Quelle, DEP-03) und bisher seit Kauf entnommen
        "entnahme": entnahme_rate,
        "entnommen_bisher": ausgezahlt_ist,
        # Einstand inkl. Sparraten (DEP-01) - Basis der Spalte "Gesamter Gewinn"
        "einstand": einstand_aktiv,
        # Kursreihe fuer die Bandbreiten-Simulation weiter unten (Volatilitaet
        # und Drift werden daraus geschaetzt, nicht nur die Endpunkte).
        # Keine Volatilitaet/Drift aus synthetischen Ersatzdaten schaetzen (DEP-04)
        "kursreihe": df_chart["Close"] if (not df_chart.empty and is_live_history) else None,
        # Fuer den Szenario-Simulator: erlaubt, die Kurshistorie des
        # PRODUKTS zu laden (unabhaengig vom eigenen Kaufzeitpunkt).
        "instrument_id": config.LS_INSTRUMENT_ID,
        "wkn": config.WKN,
    }] if haupt_aktiv else []
    # Bestand fuer die Depot-Analyse (depot_analyse_ui): dieselben Werte wie die Kacheln, je Position
    # Stueck, Kurs, Einstand, Kurshistorie. Positionen ohne Kurs werden markiert und nicht bewertet.
    depot_bestand = [{
        "name": haupt_name, "wkn": config.WKN, "instrument_id": config.LS_INSTRUMENT_ID,
        "stueck": depotwert_real_ist / aktueller_kurs if aktueller_kurs else 0.0,
        "kurs": aktueller_kurs, "vortag": vortag_kurs, "wert": depotwert_real_ist, "einstand": einstand_aktiv,
        "ausgezahlt": ausgezahlt_ist, "kaufdatum": kaufdatum_aktiv, "ist_wikifolio": ist_wikifolio(config.WKN),
        "hist": df_chart["Close"].iloc[-420:] if (not df_chart.empty and is_live_history) else None,
    }] if haupt_aktiv else []

    _pos_gesamt = len(weitere_positionen)

    for _pos_i, pos in enumerate(weitere_positionen):
        try:
            p_name = pos.get("name", pos.get("wkn", "Position"))
            if _pos_gesamt:
                melde("positionen", _pos_i / _pos_gesamt,
                      f"Lade Position {_pos_i + 1}/{_pos_gesamt} · {p_name} …")

            # --- Position ohne Kursquelle: eigene, ruhige Kachel statt Fehler ---
            # Sie zeigt nur den Einstand und laesst sich per Instrument-ID
            # jederzeit "scharfschalten". Sie fliesst NICHT in die Summe ein,
            # damit die Gesamtzahlen nicht stillschweigend falsch werden.
            if not pos.get("instrument_id"):
                p_stueck = position_stueckzahl(pos)
                p_einstand = float(pos.get("startkapital") or 0)
                p_kaufdatum = datetime.date.fromisoformat(pos["kaufdatum"])
                karte = depot_kachel_html(
                    f'{_h(p_name)} · {_h(pos.get("wkn", ""))}', fmt(p_einstand, 2),
                    chips='<span class="meta-chip">ohne Kursquelle</span>',
                    fussnote=f'{_de_zahl(p_stueck, 4)} Anteile · Kauf am {p_kaufdatum.strftime("%d.%m.%Y")} zu '
                    f'{FMT.kurs(float(pos["kaufkurs"]))} · Kursquelle-ID ergänzen (Position bearbeiten → Suche), '
                    'um Kurse und Performance zu sehen')
                positions_karten.append((p_name, karte, None))
                depot_bestand.append({"name": p_name, "wkn": pos.get("wkn", ""), "instrument_id": None,
                                      "stueck": p_stueck, "kurs": None, "wert": 0.0, "einstand": p_einstand,
                                      "ohne_kurs": True})
                continue

            p_kurs, p_vortag, p_quelle = get_live_kurs(pos["instrument_id"])
            if p_kurs is None:
                positionen_ok = False
                st.warning(f"⚠️ Für **{p_name}** sind gerade keine Live-Daten verfügbar.")
                depot_bestand.append({"name": p_name, "wkn": pos.get("wkn", ""), "instrument_id": pos["instrument_id"],
                                      "stueck": position_stueckzahl(pos), "kurs": None, "wert": 0.0,
                                      "einstand": float(pos.get("startkapital") or 0), "ohne_kurs": True})
                continue

            p_stueck = position_stueckzahl(pos)
            p_wert = p_kurs * p_stueck
            p_einstand = float(pos.get("startkapital") or 0)
            p_gewinn = p_wert - p_einstand
            p_rendite = (p_gewinn / p_einstand * 100) if p_einstand else 0.0

            p_kaufdatum = datetime.date.fromisoformat(pos["kaufdatum"])
            p_hist = get_kurshistorie(
                pos["instrument_id"], heute_date - datetime.timedelta(days=420), heute_date
            )
            p_perioden_kurs = berechne_zeitraeume(p_kurs, p_vortag, p_hist, heute_date)
            p_perioden_depot = [(lbl, d * p_stueck, pct) for lbl, d, pct in p_perioden_kurs]
            p_perioden_depot.append(("seit Kauf", p_gewinn, p_rendite))

            # in die Gesamtsumme einrechnen
            gesamt_wert += p_wert
            gesamt_einstand += p_einstand
            gesamt_beitraege.append((p_wert, {lbl: betrag for lbl, betrag, _ in p_perioden_depot
                                              if lbl != "seit Kauf"}))

            p_tage = max(1, (heute_date - p_kaufdatum).days)
            p_pa_ist, p_pa_hoch = rendite_pa_seit_kauf(p_einstand, p_wert, p_kaufdatum, heute_date)
            # Fuer die Prognose die Produkt-Rendite (Median); Rueckfall auf die eigene
            # Rendite seit Kauf: ab 1 Jahr realisiert p.a., darunter ab 1 Monat aus der
            # Ø-Monatsrendite hochgerechnet, sonst 0 % (Audit DEP-08 / Nutzerentscheid).
            p_prognose_pa, p_prognose_details = produkt_rendite_pa(pos["instrument_id"], heute_date)
            _p_hinweis = None
            if p_prognose_pa is None:
                p_prognose_pa, _p_hinweis = prognose_rate_rueckfall(p_wert, p_einstand, p_tage)
                p_prognose_details = [(_p_hinweis, p_prognose_pa)] if _p_hinweis else []

            # Sparrate/Entnahme sind bislang nur fuer die Hauptposition
            # konfigurierbar - fuer weitere Positionen daher 0.
            prognose_optionen.append({
                "name": p_name,
                "startkapital": p_einstand,
                "aktueller_wert": p_wert,
                "cagr_pa": p_prognose_pa,
                "cagr_details": p_prognose_details,
                "cagr_rueckfall_hinweis": _p_hinweis,
                "kaufdatum": p_kaufdatum,
                "sparrate": 0.0,
                "entnahme": 0.0,
                "einstand": p_einstand,
                "kursreihe": p_hist if p_hist is not None and not p_hist.empty else None,
                "instrument_id": pos["instrument_id"],
                "wkn": pos.get("wkn", ""),
            })
            depot_bestand.append({"name": p_name, "wkn": pos.get("wkn", ""), "instrument_id": pos["instrument_id"],
                                  "stueck": p_stueck, "kurs": p_kurs, "vortag": p_vortag, "wert": p_wert,
                                  "einstand": p_einstand, "kaufdatum": p_kaufdatum, "quelle": p_quelle,
                                  "ist_wikifolio": ist_wikifolio(pos.get("wkn", ""), p_name),
                                  "hist": p_hist if p_hist is not None and not p_hist.empty else None})

            # wie bei der Hauptposition: erzielte Rendite seit Kauf, nicht die Prognoserate
            # (die gehoert in die Prognosen - Audit A-08, 360°-Pruefung F-05)
            karte = depot_kachel_html(
                f'{_h(pos.get("name", "Position"))} · {_h(pos.get("wkn", ""))}', fmt(p_wert, 2),
                chips=(f'<span class="stat-chip"><span class="stat-chip-label">Ø p.a. seit Kauf'
                       f'{" (hochgerechnet)" if p_pa_hoch else ""}</span>'
                       f'<span class="stat-chip-val">{FMT.pct(p_pa_ist, 1)}</span></span>'
                       if p_pa_ist is not None else ''),
                gv=(p_gewinn, p_rendite), zeilen=p_perioden_depot,
                fussnote=f'{_de_zahl(p_stueck, 4)} Anteile · Kurs {FMT.kurs(p_kurs)} · '
                f'Kauf am {p_kaufdatum.strftime("%d.%m.%Y")} zu {FMT.kurs(float(pos["kaufkurs"]))} · '
                f'Einstand {fmt(p_einstand, 2)}')
            positions_karten.append((p_name, karte, (p_wert, p_gewinn, p_rendite)))

        except Exception as e:
            positionen_ok = False
            st.error(f"⚠️ Position **{pos.get('name', '?')}** konnte nicht berechnet werden: {e}")
            notify_app_error(f"Position-{pos.get('id', '?')}", e)

    # Beobachtungswerte (symbolische Prognose-Basis) hinten anfuegen - erst
    # die echten Positionen (reales Kapital), dann die hypothetischen.
    prognose_optionen.extend(prognose_beobachtung_optionen)

    # ---------- KURS-AUSWAHL: nur eigene Positionen und Beobachtungswerte ----------
    # (UX 10/2026) Frueher stand hier fuer JEDEN Benutzer die Kurskachel des fest eingestellten
    # Zertifikats - auch bei leerem Depot. Jetzt: Hauptposition (falls vorhanden), jede weitere
    # Position mit Kursquelle, danach die Beobachtungsliste. Ohne Werte gibt es keine Kurs-Spalte.
    kurs_auswahl = []                 # (Anzeigename, Eintrag oder None fuer die Hauptposition, im Depot)
    _ids = set()
    if haupt_aktiv:
        kurs_auswahl.append((haupt_name, None, True))
        _ids.add(str(config.LS_INSTRUMENT_ID))
    for _p in weitere_positionen:
        if _p.get("instrument_id") and str(_p["instrument_id"]) not in _ids:
            _ids.add(str(_p["instrument_id"]))
            kurs_auswahl.append((_p.get("name") or _p.get("wkn") or "Position",
                                 {"name": _p.get("name", ""), "wkn": _p.get("wkn", ""),
                                  "instrument_id": _p["instrument_id"]}, True))
    for _b in beobachtung:
        if str(_b["instrument_id"]) not in _ids:
            _ids.add(str(_b["instrument_id"]))
            kurs_auswahl.append((_b.get("name") or _b.get("wkn") or "Wert", _b, False))

    # ---------- ZWEI SPALTEN: links das eigene Depot, rechts die Kurse ----------
    # Auf breiten Bildschirmen nebeneinander, unter 820 px untereinander (Depot zuerst, siehe ui_stil).
    # Beide Spalten gleich breit und mit gleich hoher Kopfzeile (Titel | Auswahl).
    # Schritt-Fuehrung: nur Abschnitte, die es gerade gibt (fortlaufend nummeriert)
    _sf_aktiv = [1] + ([2] if positions_karten else []) + ([3] if kurs_auswahl else []) + ([4] if haupt_aktiv else [])
    _sf_nr = lambda n: schritte.nummer_html("depot", n, _sf_aktiv.index(n) + 1)
    schritte.leiste(st, "depot", _sf_aktiv)
    if kurs_auswahl:
        _spalte_depot, _spalte_kurse = st.container(key="depot_spalten").columns([1, 1], gap="large")
    else:
        _spalte_depot, _spalte_kurse = st.container(key="depot_spalten"), None
    _spalte_depot.__enter__()
    with st.container(key="depot_kopf_links"):
        st.markdown(f'<div class="abschnitt">{_sf_nr(1)}Mein Depot</div>', unsafe_allow_html=True)

    # ---------- DEPOT GESAMT: Wert und Gewinn/Verlust zuerst (ab einer Position) ----------
    if positions_karten and any(k[2] for k in positions_karten):
        # EINE Quelle fuer Depotwert, Gewinn und Rendite (Audit FIN-03): dieselbe Rechnung wie Depot-Analyse
        # und Altersteilzeit (depot_summe.summe ueber den Depotbestand)
        _summe = depot_summe.summe(depot_bestand)
        gesamt_wert, gesamt_einstand, gesamt_ausgezahlt = _summe["wert"], _summe["einstand"], _summe["ausgezahlt"]
        gesamt_gewinn = _summe["gewinn"] or 0.0
        gesamt_rendite = _summe["rendite_pct"] or 0.0

        # Prozent je Zeitraum aus den summierten €-Betraegen ableiten, NICHT die
        # Einzelprozente mitteln - Positionen haben unterschiedliche Groessen,
        # ein einfacher Mittelwert waere schlicht falsch.
        # Audit DEP-07: Basis je Zeitraum nur ueber die Positionen, die fuer diesen
        # Zeitraum einen Betrag liefern; fehlen Positionen, wird die Zeile mit "*"
        # gekennzeichnet (Fussnote unten).
        gesamt_perioden = []
        teilweise_zeitraeume = False
        for lbl, betrag, pct, teilweise in gesamt_perioden_berechnen(gesamt_beitraege, ALLE_ZEITRAEUME):
            gesamt_perioden.append((f"{lbl}*" if teilweise else lbl, betrag, pct))
            teilweise_zeitraeume = teilweise_zeitraeume or teilweise

        # Nur Positionen mit Kursquelle sind in der Summe enthalten - das muss
        # sichtbar sein, sonst wirkt eine unvollstaendige Summe wie die volle.
        _gezaehlte = ([{"instrument_id": config.LS_INSTRUMENT_ID}] if eigen and haupt_aktiv else []) + alle_positionen
        anzahl_gezaehlt = sum(1 for p in _gezaehlte if p.get("instrument_id"))
        anzahl_gesamt = len(_gezaehlte)
        if anzahl_gezaehlt < anzahl_gesamt:
            positions_chip = f"{anzahl_gezaehlt} von {anzahl_gesamt} Positionen"
        else:
            positions_chip = f"{anzahl_gesamt} Position{'en' if anzahl_gesamt != 1 else ''}"

        hinweis = "" if positionen_ok else " · ⚠️ unvollständig, s. Warnungen oben"
        if anzahl_gezaehlt < anzahl_gesamt:
            hinweis += " · Positionen ohne Kursquelle nicht enthalten"
        if teilweise_zeitraeume:
            hinweis += " · * nur Positionen mit Kursdaten für diesen Zeitraum (Prozent auf deren Wert)"
        if sparplan_eingezahlt > 0:
            hinweis += f" · inkl. Sparraten {fmt(sparplan_eingezahlt, 2)}"
        if gesamt_ausgezahlt > 0:
            hinweis += f" · inkl. ausgezahlter Entnahmen {fmt(gesamt_ausgezahlt, 2)}"
        # Hero: Tag als Badge; Woche/Monat/lfd. Jahr/Jahr als st.metric-Karten; der Rest aufklappbar
        _kpi_lbl = ("Woche", "Monat", "Lfd. Jahr", "Jahr")
        _tag = next(((b, p) for l, b, p in gesamt_perioden if l.rstrip("*") == "Tag"), None)
        _kpis = [z for z in gesamt_perioden if z[0].rstrip("*") in _kpi_lbl]
        _rest = [z for z in gesamt_perioden if z[0].rstrip("*") not in _kpi_lbl + ("Tag", "seit Kauf")]
        st.markdown(depot_hero_html(
            fmt(gesamt_wert, 2), chips=f'<span class="meta-chip">{positions_chip}</span>',
            gesamt=(gesamt_gewinn, gesamt_rendite), tag=_tag,
            mehr=zeitraum_zeilen_html(_rest), anzahl_mehr=len(_rest),
            fussnote=f"Einstand {fmt(gesamt_einstand, 2)}{hinweis}"),
            unsafe_allow_html=True)
        kpi_metriken(_kpis, key="depot_kpis")
        # Kurzinfo fuer die Startseite merken (nur Anzeige - dort wird nichts abgerufen)
        depot_kurzinfo_merken({"wert": gesamt_wert, "gv": gesamt_gewinn, "gv_pct": gesamt_rendite,
                               "tag": next(((b, p) for l, b, p in gesamt_perioden if l.rstrip("*") == "Tag"), None),
                               "zeit": now_berlin})

    # ---------- POSITIONEN: Liste mit Kurzinfo, Details aufklappbar ----------
    if positions_karten:
        st.markdown(f'<div class="abschnitt klein">{_sf_nr(2)}Positionen</div>', unsafe_allow_html=True)
        for _i, (_name, _karte, _kurz) in enumerate(positions_karten):
            if _kurz:
                _w, _gv, _gvp = _kurz
                _kl, _pf = _richtung_html(_gv, 2)
                _titel = f"{_name} · {FMT.eur(_w, 2)} · {_pf} {FMT.pct(_gvp, 2, vz=True)}"
            else:
                _titel = f"{_name} · ohne Kursquelle"
            with st.expander(_titel, expanded=False, key=f"pos_detail_{_i}"):
                st.markdown(_karte, unsafe_allow_html=True)
    elif not alle_positionen:
        # ---------- LEERES DEPOT (normaler Benutzer ohne eigene Daten) ----------
        st.markdown(
            '<div class="hero">'
            '<div class="hero-label">Mein Depot</div>'
            '<div class="price-line"><span class="hero-val">Noch kein eigenes Depot</span></div>'
            '<div class="card-footnote">Lege deine erste Position an – sie wird für deine nächste '
            'Anmeldung gespeichert. Sparrate und Entnahme findest du unter 🛠️ Depot verwalten.</div>'
            '</div>', unsafe_allow_html=True)
        with st.expander("➕ Erste Position anlegen", expanded=True):
            positions_anlage_formular("leer")

    _spalte_depot.__exit__(None, None, None)
    # ---------- KURSE (nach dem eigenen Depot) ----------
    if kurs_auswahl:
        _spalte_kurse.__enter__()

        # EIGENES FRAGMENT: beim Umschalten wird NUR dieser Bereich neu gezeichnet, nicht das
        # komplette Dashboard (Positionsliste, Benchmarks, alle Kacheln).
        @st.fragment
        def _render_kursansicht():
            _zugang_pruefen()      # nur Anmeldung - der Bereich wird auch in anderen Ansichten (verborgen) gebaut
            # Die WKN wird aus den Beschriftungen entfernt - sie steht ohnehin in der Kachel darunter.
            def _kurzname(text, fallback=""):
                ohne_wkn = re.sub(r"\s*\([^)]*\)\s*$", "", (text or "").strip())
                return ohne_wkn or fallback or "Wert"

            kurs_optionen = [_kurzname(n) for n, _, _ in kurs_auswahl]
            # Doppelte Namen eindeutig machen, sonst laesst sich die Auswahl nicht zuordnen.
            gesehen = {}
            for i, opt in enumerate(kurs_optionen):
                if opt in gesehen:
                    gesehen[opt] += 1
                    kurs_optionen[i] = f"{opt} ({gesehen[opt]})"
                else:
                    gesehen[opt] = 1

            # Kopfzeile wie links: Titel und Auswahl in einer Zeile
            with st.container(key="depot_kopf_rechts"):
                _k_titel, _k_wahl = st.columns([1, 1.6], vertical_alignment="center")
                _k_titel.markdown(f'<div class="abschnitt">{_sf_nr(3)}Kurse</div>', unsafe_allow_html=True)
                # immer ein Dropdown: Pills liefen in der halben Breite ueber den Rand
                auswahl = _k_wahl.selectbox("Wert wählen", kurs_optionen,
                                            key="kurs_ansicht_wahl_select", label_visibility="collapsed")
            if auswahl not in kurs_optionen:
                auswahl = kurs_optionen[0]
            _, eintrag, im_depot = kurs_auswahl[kurs_optionen.index(auswahl)]
            if eintrag is None:
                st.markdown(kurs_karte, unsafe_allow_html=True)
                return

            platz = st.empty()
            fortschritt = fortschritt_anzeige(platz)
            try:
                # Beide Schritte sind eigene Abrufe (bzw. Treffer im Kursdienst) - der Fortschritt
                # bildet echte Arbeitsschritte ab, nicht bloss eine Animation.
                fortschritt(15, f"Lade Kurs für {auswahl} …")
                karte = beobachtungs_karte(eintrag, fortschritt=fortschritt, im_depot=im_depot)
                platz.empty()
                st.markdown(karte, unsafe_allow_html=True)
            except Exception as e:
                platz.empty()
                st.error(f"⚠️ Kurs konnte nicht geladen werden: {e}")
                notify_app_error(f"Beobachtung-{eintrag.get('wkn', '?')}", e)

        _render_kursansicht()
        _spalte_kurse.__exit__(None, None, None)


    # ---------- ANSICHT "EINSTELLUNGEN" ----------
    # Eingaben und Verwaltung stehen in einer eigenen Ansicht; ausserhalb davon
    # werden sie weiter aufgebaut (Zustand bleibt erhalten), aber ausgeblendet.
    _depot_bereich.__exit__(None, None, None)
    _einst_bereich = st.container(key="einst_bereich")
    if gewaehlte_ansicht != ANSICHT_EINST:
        st.markdown('<style>.st-key-einst_bereich { display: none !important; }</style>',
                    unsafe_allow_html=True)
    _einst_bereich.__enter__()

    # ---------- Eingaben ----------
    # Wichtig: "value=" nur beim allerersten Erstellen des Widgets mitgeben,
    # NICHT bei jedem Rerun (klassischer Streamlit-Stolperstein).
    st.markdown('<div class="abschnitt">Depot verwalten</div>', unsafe_allow_html=True)
    st.caption("Positionen anlegen und ändern, Sparrate und Entnahme, Beobachtungsliste und System-Status "
               "deines Depots.")
    schritte.leiste(st, "verwalten")
    schritte.titel(st, "verwalten", 1, "Sparrate und Entnahme")

    with st.expander("🛠️ Sparrate und Entnahme anpassen", expanded=False):
        # Felder bewusst untereinander (keine Spalten) - auf dem Smartphone
        # sind nebeneinanderliegende Zahlenfelder samt Steppern sehr fummelig.
        if eigen:
            # Kauf/Kapital gehoeren zur Admin-Hauptposition - eigene Kaeufe sind Positionen
            st.caption("Eigene Käufe legst du unter „➕ Positionen verwalten“ an. Hier stellst du einen "
                       f"monatlichen Sparplan auf {config.WKN} und deine monatliche Entnahme ein – beides "
                       "startet bei 0 € und wird für deine nächste Anmeldung gespeichert.")
        else:
            # Audit A-04: Kaufdatum, Kaufkurs und Kapital haben EINE gespeicherte Quelle -
            # die Hauptposition unter "Positionen verwalten" (frueher hier nur fuer die Sitzung).
            st.caption(
                f"**Hauptposition:** Kauf am {kaufdatum_aktiv.strftime('%d.%m.%Y')} zu "
                f"{FMT.eur(kaufkurs_aktiv, 4)}, Kapital {fmt(startkapital_aktiv, 2)} → "
                f"{de_zahl(stueckzahl_aktiv, 4)} Anteile. Ändern unter „➕ Positionen verwalten“ "
                "(wird dauerhaft gespeichert)."
            )
            if haupt_abweichend:
                st.warning(f"Die erste gespeicherte Position ist nicht {config.WKN} – für die "
                           "Hauptposition gelten deshalb die Werte aus config.py.")

        def _vorbelegen(key, gespeichert):
            """Eingabefeld mit dem GESPEICHERTEN Wert vorbelegen. Aendert sich der gespeicherte
            Wert (andere Sitzung, Zustand wieder lesbar), wird nachgezogen - aber nur, solange
            hier nichts Ungespeichertes eingetippt wurde."""
            basis_key = f"_{key}_basis"
            basis = st.session_state.get(basis_key)
            akt = st.session_state.get(key)
            if akt is None or (basis is not None and abs(float(akt) - basis) < 1e-9
                               and abs(basis - float(gespeichert)) > 1e-9):
                st.session_state[key] = float(gespeichert)
                st.session_state[basis_key] = float(gespeichert)
            elif basis is None:
                st.session_state[basis_key] = float(gespeichert)

        # --- SPARRATE (Audit DEP-02): vorbelegt aus dem gespeicherten Plan; gespeichert
        # bzw. beendet wird NUR per Knopf (Beenden zusaetzlich mit Bestaetigung). ---
        _vorbelegen("haupt_sparrate_input", sparrate_aktiv)
        st.number_input(
            "Monatliche Sparrate (€)", min_value=0.0, step=10.0, key="haupt_sparrate_input",
            help="Zusätzliche monatliche Einzahlung (Sparplan) - kauft ab dem Starttag monatlich "
                 "Anteile zum jeweiligen Kurs. Eingezahlte Raten zählen zum Einstand, nicht zum Gewinn. "
                 "Wird erst mit „Sparrate speichern“ übernommen.",
        )
        if sparplan_start is not None:
            st.caption(f"Sparplan läuft seit {sparplan_start.strftime('%d.%m.%Y')} · "
                       f"{len(sparplan_termine_liste)} Käufe · eingezahlt {fmt(sparplan_eingezahlt, 2)}")
        if sparplan_ohne_rate:
            st.warning("Für den laufenden Sparplan ist noch keine Rate gespeichert (älterer Stand). "
                       "Bitte die Rate eintragen und speichern - sie gilt dann ab dem Starttag.")
        if GH_STATE_READY and not sparplan_lesbar:
            st.warning("Sparplan-Zustand gerade nicht lesbar - Speichern ist bis dahin gesperrt.")
        _sp_neu = float(st.session_state.get("haupt_sparrate_input") or 0.0)
        _sp_geaendert = abs(_sp_neu - sparrate_aktiv) > 1e-9 or sparplan_ohne_rate
        if GH_STATE_READY and sparplan_lesbar and _sp_geaendert:
            _beenden = _sp_neu <= 0
            _bestaetigt = True
            if _beenden:
                _bestaetigt = st.checkbox(
                    "Sparplan wirklich beenden (bisherige Sparplan-Käufe fallen aus der Rechnung)",
                    key="sparplan_beenden_ok")
            if st.button("🛑 Sparplan beenden" if _beenden else "💾 Sparrate speichern",
                         key="sparplan_speichern_btn", disabled=not _bestaetigt):
                if _beenden:
                    ok, _ = depot_aktualisieren(upfad(config.STATE_PATH_SPARPLAN), lambda d: {}, default={},
                                                message="sparplan gestoppt [skip ci]")
                    if ok:
                        chronik_eintrag("depot", "⏹️ Sparplan gestoppt",
                                        f"Lief seit {sparplan_start.strftime('%d.%m.%Y')}." if sparplan_start else "")
                        st.session_state.pop("sparplan_beenden_ok", None)
                        st.session_state["_haupt_sparrate_input_basis"] = 0.0
                        st.success("Sparplan beendet.")
                        st.rerun()
                    else:
                        st.error("Beenden fehlgeschlagen - der Sparplan-Zustand wurde NICHT geändert.")
                else:
                    ok, neu = depot_aktualisieren(
                        upfad(config.STATE_PATH_SPARPLAN),
                        lambda d: sparplan_state_neu(d, _sp_neu, heute_date), default={},
                        message="sparplan gespeichert [skip ci]")
                    if ok:
                        chronik_eintrag("depot", f"💶 Sparrate gespeichert: {FMT.eur(_sp_neu, 2)}/Monat",
                                        "Monatlicher Nachkauf zum jeweiligen Kurs (Rechnung).")
                        st.session_state["_haupt_sparrate_input_basis"] = _sp_neu
                        st.success("Sparrate gespeichert.")
                        st.rerun()
                    else:
                        st.error("Speichern fehlgeschlagen - die Sparrate wurde NICHT übernommen.")
        elif not GH_STATE_READY:
            st.caption("Ohne persistenten State gilt die Sparrate nur in dieser Sitzung.")

        # --- ENTNAHME (Audit DEP-03): EINE gespeicherte Monatsrate fuer Netto und Real ---
        _vorbelegen("haupt_entnommen_input", entnahme_rate)
        st.number_input(
            "Monatliche Entnahme (€)", min_value=0.0, step=10.0, key="haupt_entnommen_input",
            help=f"Wird ab einem Monat nach dem Kaufdatum monatlich entnommen und seit Kauf "
                 f"aufsummiert (Netto = Brutto − Rate × Anzahl Entnahmen). Dieselbe Rate gilt für "
                 f"die Real-Variante mit Anteilsverkauf. Standard: {FMT.eur(entnahme_standard(eigen), 2)}.",
        )
        st.caption(f"{anzahl_entnahmen} Entnahmen seit Kauf · zusammen {fmt(gesamt_entnommen, 2)}")
        _en_neu = float(st.session_state.get("haupt_entnommen_input") or 0.0)
        if GH_STATE_READY and abs(_en_neu - entnahme_rate) > 1e-9:
            if not entnahme_lesbar:
                st.warning("Entnahme-Zustand gerade nicht lesbar - Speichern ist bis dahin gesperrt.")
            elif st.button("💾 Entnahme speichern", key="entnahme_speichern_btn"):
                ok, _ = depot_aktualisieren(upfad(STATE_PATH_ENTNAHME),
                                            lambda d: dict(d if isinstance(d, dict) else {}, rate=_en_neu),
                                            default={}, message="entnahme gespeichert [skip ci]")
                if ok:
                    chronik_eintrag("depot", f"💸 Monatliche Entnahme: {FMT.eur(_en_neu, 2)}",
                                    "Gilt für Netto (Simulation) und Real.")
                    st.session_state["_haupt_entnommen_input_basis"] = _en_neu
                    st.success("Entnahme gespeichert.")
                    st.rerun()
                else:
                    st.error("Speichern fehlgeschlagen - die Entnahme wurde NICHT übernommen.")

    # Sicherheitsnetz: falls keine Ansicht gegriffen hat (z.B. unbekannter
    # gespeicherter Wert in der Auswahl), darf die Anzeige nicht stehenbleiben.
    lade_fertig()

    # ---------- BEOBACHTUNGSLISTE VERWALTEN ----------
    schritte.titel(st, "verwalten", 2)
    with st.expander("👁️ Beobachtungsliste verwalten", expanded=False):
        st.caption(
            "Werte hier werden nur als Kurskachel angezeigt (umschaltbar über die "
            "Tabs oben) und fließen **nicht** in Depotwert, Gewinn oder Gesamtsumme ein."
        )

        # Vergleichswerte aus config.BENCHMARKS als Ein-Klick-Vorlage anbieten -
        # deren Instrument-IDs sind bereits gepflegt, doppeltes Suchen entfaellt.
        _bereits = {e.get("instrument_id") for e in lade_beobachtung()}
        _vorschlaege = {
            label: iid for label, iid in (getattr(config, "BENCHMARKS", {}) or {}).items()
            if iid not in _bereits
        }
        if _vorschlaege:
            v_col, v_btn = st.columns([3, 1])
            v_wahl = v_col.selectbox(
                "Aus vorhandenen Vergleichswerten übernehmen",
                list(_vorschlaege.keys()), key="beob_vorlage",
                help="Diese Werte sind in config.BENCHMARKS bereits mit ihrer "
                     "Kursquelle-ID hinterlegt - kein Suchen nötig.",
            )
            if v_btn.button("Übernehmen", width="stretch", key="beob_vorlage_btn"):
                _neu_eintrag = {
                    "id": f"beob-{uuid.uuid4().hex[:12]}",
                    "name": v_wahl, "wkn": "",
                    "instrument_id": _vorschlaege[v_wahl],
                }
                if aendere_beobachtung(lambda l: l + [_neu_eintrag], "beobachtung aus benchmark [skip ci]"):
                    st.success(f"„{v_wahl}“ zur Beobachtung hinzugefügt.")
                    st.rerun()
                else:
                    st.error("Hinzufügen fehlgeschlagen (kein persistenter State?).")

        beob_liste = lade_beobachtung()

        for b_idx, eintrag in enumerate(beob_liste):
            st.markdown("---")
            st.markdown(f"**{eintrag.get('name', '')} · {eintrag.get('wkn', '')}**")
            b_treffer = instrument_suchblock(
                f"beob_edit_{b_idx}", label="Anderes Wertpapier suchen (optional)")

            with st.form(f"beob_form_{eintrag.get('id', b_idx)}"):
                bv_name = b_treffer["name"] if b_treffer else eintrag.get("name", "")
                bv_wkn = ((b_treffer["wkn"] or b_treffer["isin"]) if b_treffer
                          else eintrag.get("wkn", ""))
                bv_inst = (int(b_treffer["instrument_id"]) if b_treffer
                           else int(eintrag.get("instrument_id") or 0))
                b_suffix = f"{b_idx}_{bv_inst}"

                nb_name = st.text_input("Name", value=bv_name, key=f"bn_{b_suffix}")
                nb_wkn = st.text_input("WKN / ISIN", value=bv_wkn, key=f"bw_{b_suffix}")
                nb_inst = st.number_input("Kursquelle-ID (wird über die Suche gesetzt)", min_value=0, step=1,
                                          value=bv_inst, key=f"bi_{b_suffix}")

                bc_save, bc_del = st.columns(2)
                b_gespeichert = bc_save.form_submit_button("💾 Speichern", width="stretch")
                b_geloescht = bc_del.form_submit_button("🗑️ Entfernen", width="stretch")

                if b_gespeichert:
                    _b_neu = {
                        "id": eintrag.get("id") or f"beob-{uuid.uuid4().hex[:12]}",
                        "name": nb_name, "wkn": nb_wkn,
                        "instrument_id": int(nb_inst) if nb_inst else None,
                    }

                    def _b_ersetzen(l, _alt=eintrag, _i=b_idx, _neu=_b_neu):
                        j = liste_element_index(l, _alt.get("id"), _i, _alt.get("name"))
                        if j is None:
                            return None          # Eintrag inzwischen geaendert/entfernt
                        l[j] = _neu
                        return l
                    if aendere_beobachtung(_b_ersetzen, "beobachtung geaendert [skip ci]"):
                        suche_zuruecksetzen(f"beob_edit_{b_idx}")
                        st.success("Gespeichert.")
                        st.rerun()
                    else:
                        st.error("Speichern fehlgeschlagen (kein persistenter State, Lesefehler "
                                 "oder Eintrag inzwischen geändert) - nichts gespeichert.")

                if b_geloescht:
                    def _b_entfernen(l, _alt=eintrag, _i=b_idx):
                        j = liste_element_index(l, _alt.get("id"), _i, _alt.get("name"))
                        if j is None:
                            return None
                        l.pop(j)
                        return l
                    if aendere_beobachtung(_b_entfernen, "beobachtung entfernt [skip ci]"):
                        st.success("Entfernt.")
                        st.rerun()
                    else:
                        st.error("Entfernen fehlgeschlagen (kein persistenter State?).")

        st.markdown("---")
        st.markdown("**Wert zur Beobachtung hinzufügen**")
        b_gewaehlt = instrument_suchblock("beob_neu")

        with st.form("beob_form_neu", clear_on_submit=True):
            bneu_name = st.text_input(
                "Name", value=(b_gewaehlt["name"] if b_gewaehlt else ""),
                placeholder="z. B. FF Inlinetrading")
            bneu_wkn = st.text_input(
                "WKN / ISIN",
                value=(b_gewaehlt["wkn"] or b_gewaehlt["isin"]) if b_gewaehlt else "",
                placeholder="z. B. LS9VSU")
            bneu_inst = st.number_input(
                "Kursquelle-ID (wird über die Suche gesetzt)", min_value=0, step=1,
                value=int(b_gewaehlt["instrument_id"]) if b_gewaehlt else 0,
                help="Wird durch die Suche oben automatisch gefüllt. Ohne ID kann "
                     "kein Kurs angezeigt werden - hier also Pflicht.",
            )

            if st.form_submit_button("👁️ Zur Beobachtung hinzufügen", width="stretch"):
                if not bneu_name or not bneu_inst:
                    st.error("Bitte Name und Kursquelle-ID angeben (am einfachsten über die Suche).")
                else:
                    b_test, _, _ = get_live_kurs(int(bneu_inst))
                    if b_test is None:
                        st.error(
                            f"Für die Kursquelle-ID {int(bneu_inst)} liefert ls-tc.de keine "
                            "Kursdaten. Bitte die ID prüfen."
                        )
                    else:
                        _b_anlage = {
                            "id": f"beob-{uuid.uuid4().hex[:12]}",
                            "name": bneu_name, "wkn": bneu_wkn,
                            "instrument_id": int(bneu_inst),
                        }
                        if aendere_beobachtung(lambda l: l + [_b_anlage], "beobachtung angelegt [skip ci]"):
                            suche_zuruecksetzen("beob_neu")
                            st.success(f"„{bneu_name}“ hinzugefügt "
                                       f"(aktueller Kurs {FMT.eur(b_test, 2)}).")
                            st.rerun()
                        else:
                            st.error("Hinzufügen fehlgeschlagen (kein persistenter State?).")

    # ---------- POSITIONEN VERWALTEN (anlegen / aendern / loeschen) ----------
    schritte.titel(st, "verwalten", 3)
    with st.expander("➕ Positionen verwalten", expanded=False):
        if not GH_STATE_READY:
            st.warning(
                "Ohne persistenten State (GITHUB_REPO/GITHUB_TOKEN) gehen angelegte "
                "Positionen beim nächsten Neustart verloren."
            )
        st.caption(
            "WKN oder ISIN ins Suchfeld eingeben – Name und Kursquelle-ID werden "
            "automatisch übernommen. "
            + ("Deine Positionen werden nur für dich gespeichert und erscheinen bei der nächsten Anmeldung wieder."
               if eigen else
               "Die erste Position ist die Hauptposition, sie speist zusätzlich alle Charts und Prognose-Tabs.")
        )

        # --- Bestehende Positionen bearbeiten/loeschen ---
        for idx, pos in enumerate(alle_positionen):
            rolle = "Hauptposition" if idx == 0 and not eigen else f"Position {idx + 1}"
            st.markdown("---")
            st.markdown(f"**{rolle}: {pos.get('name', '')}**")

            # Hauptposition (Admin): Kaufdatum, Kaufkurs und Kapital wirken auf Depotwert,
            # Charts und Prognosen (Audit A-04). Das Papier selbst bleibt fest, da Charts
            # und Kurs-Alarme an config.LS_INSTRUMENT_ID haengen.
            ist_haupt = idx == 0 and not eigen
            if ist_haupt:
                st.caption("Kaufdatum, Kaufkurs und Kapital bestimmen Depotwert, Charts und Prognosen. "
                           f"Das Wertpapier ({config.WKN}) ist fest eingestellt.")
            # Suchblock ausserhalb des Formulars - erlaubt, jederzeit ein
            # anderes Wertpapier fuer diese Position zu suchen und zu uebernehmen.
            treffer_edit = None if ist_haupt else instrument_suchblock(
                f"edit_{idx}", label="Anderes Wertpapier suchen (optional)")

            with st.form(f"pos_form_{pos.get('id', idx)}"):
                # Wurde oben ein Treffer gewaehlt, ueberschreibt der die
                # gespeicherten Werte als Vorbelegung - so laesst sich eine
                # Position per Suche auf ein anderes Papier umstellen.
                v_name = treffer_edit["name"] if treffer_edit else pos.get("name", "")
                v_wkn = ((treffer_edit["wkn"] or treffer_edit["isin"]) if treffer_edit
                         else pos.get("wkn", ""))
                v_inst = (int(treffer_edit["instrument_id"]) if treffer_edit
                          else int(pos.get("instrument_id") or 0))
                # key vom Treffer abhaengig machen, damit Streamlit das Widget
                # neu aufbaut und die Vorbelegung wirklich uebernimmt.
                suffix = f"{idx}_{v_inst}"

                n_name = st.text_input("Name", value=v_name, key=f"n_{suffix}")
                n_wkn = st.text_input("WKN / ISIN", value=v_wkn, key=f"w_{suffix}", disabled=ist_haupt)
                n_inst = st.number_input(
                    "Kursquelle-ID (wird über die Suche gesetzt, optional)", min_value=0, step=1,
                    value=v_inst, key=f"i_{suffix}", disabled=ist_haupt,
                    help="0 = keine Kursquelle. Die Position wird dann ohne Kurse "
                         "angezeigt und nicht in die Depot-Summe eingerechnet.",
                )
                n_kaufdatum = st.date_input(
                    "Kaufdatum", format="DD.MM.YYYY", value=datetime.date.fromisoformat(pos["kaufdatum"]), key=f"d_{idx}")
                n_kaufkurs = st.number_input("Kaufkurs (€)", min_value=0.0, step=0.01, format="%.4f",
                                             value=float(pos.get("kaufkurs") or 0), key=f"k_{idx}")
                n_kapital = st.number_input("Investiertes Kapital (€)", min_value=0.0, step=100.0,
                                            value=float(pos.get("startkapital") or 0), key=f"s_{idx}")
                if n_kaufkurs > 0:
                    st.caption(f"Ergibt {n_kapital / n_kaufkurs:.4f} Anteile")

                c_save, c_del = st.columns(2)
                gespeichert = c_save.form_submit_button("💾 Speichern", width="stretch")
                geloescht = c_del.form_submit_button("🗑️ Löschen", width="stretch")

                if gespeichert:
                    _p_neu = {
                        "id": pos.get("id") or f"pos-{uuid.uuid4().hex[:12]}",
                        "name": n_name,
                        "wkn": config.WKN if ist_haupt else n_wkn,
                        "instrument_id": (int(config.LS_INSTRUMENT_ID) if ist_haupt
                                          else (int(n_inst) if n_inst else None)),
                        "kaufdatum": n_kaufdatum.isoformat(), "kaufkurs": float(n_kaufkurs),
                        "startkapital": float(n_kapital),
                    }

                    def _p_ersetzen(l, _alt=pos, _i=idx, _neu=_p_neu):
                        j = liste_element_index(l, _alt.get("id"), _i, _alt.get("name"))
                        if j is None:
                            return None
                        l[j] = _neu
                        return l
                    if aendere_positionen(_p_ersetzen, "position geaendert [skip ci]"):
                        suche_zuruecksetzen(f"edit_{idx}")
                        st.success("Gespeichert.")
                        st.rerun()
                    else:
                        st.error("Speichern fehlgeschlagen (kein persistenter State?).")

                # Admin: die Hauptposition bleibt immer; normale Benutzer duerfen alles loeschen
                _min_rest = 0 if eigen else 1
                _frage = f"pos_del_frage_{pos.get('id', idx)}"
                if geloescht:
                    if len(alle_positionen) <= _min_rest:
                        st.error("Die letzte verbleibende Position kann nicht gelöscht werden.")
                    else:
                        st.session_state[_frage] = True      # erst nachfragen (360°-Pruefung F-03)

            # Rueckfrage ausserhalb des Formulars - wie beim Loeschen eines Benutzers
            if st.session_state.get(_frage):
                st.warning(f"„{pos.get('name', '')}“ wirklich löschen? Kaufdatum, Kaufkurs und Kapital "
                           "dieser Position gehen verloren.")
                j1, j2 = st.columns(2)
                if j2.button("Abbrechen", key=f"pos_del_nein_{pos.get('id', idx)}", width="stretch"):
                    st.session_state.pop(_frage, None)
                    st.rerun()
                if j1.button("🗑️ Endgültig löschen", key=f"pos_del_ja_{pos.get('id', idx)}", width="stretch",
                             type="primary"):
                    st.session_state.pop(_frage, None)

                    def _p_entfernen(l, _alt=pos, _i=idx, _min=_min_rest):
                        j = liste_element_index(l, _alt.get("id"), _i, _alt.get("name"))
                        if j is None or len(l) <= _min:
                            return None
                        l.pop(j)
                        return l
                    if aendere_positionen(_p_entfernen, "position geloescht [skip ci]"):
                        st.success("Gelöscht.")
                        st.rerun()
                    else:
                        st.error("Löschen fehlgeschlagen (kein persistenter State?).")

        # --- Neue Position anlegen ---
        st.markdown("---")
        st.markdown("**Neue Position hinzufügen**")

        positions_anlage_formular("neu")

    _einst_bereich.__exit__(None, None, None)
    _depot_bereich.__enter__()

    # ---------- DATENZEILEN: Sekundaerwerte, eingeklappt ----------
    # Meilenstein und Anfangskapital sind Kontext, keine taeglich relevanten
    # Kennzahlen - eingeklappt konkurrieren sie nicht mit Kurs und Depotwert.
    # Normale Benutzer: nur mit eigenem Sparplan (Hauptposition); Meilenstein/Anfangskapital
    # beziehen sich auf das Startkapital der Admin-Hauptposition und entfallen dort.
    if haupt_aktiv:
        st.markdown(f'<div class="abschnitt">{_sf_nr(4)}Weitere Informationen</div>', unsafe_allow_html=True)

    if not eigen:
        with st.expander("🎯 Meilenstein und Anfangskapital", expanded=False):
            st.markdown(f"""
        <div class="rows">
            <div class="row">
                <span class="row-label">100k-Meilenstein</span>
                <span class="row-val">{meilenstein_datum_str}
                    <span class="row-note">{meilenstein_details_str}</span>
                </span>
            </div>
            <div class="row">
                <span class="row-label">Anfangskapital</span>
                <span class="row-val">{fmt(startkapital_aktiv, 2)}
                    <span class="row-note">Kauf am {kaufdatum_aktiv.strftime('%d.%m.%Y')} zu {FMT.eur(kaufkurs_aktiv, 2)}</span>
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    if haupt_aktiv:
        # --- ENTNAHMEN + Kosten: nur bei Bedarf einblenden (Audit A-12) ---
        sparrate_note = (
            f" · inkl. {_de_zahl(zusaetzliche_stueckzahl_sparplan, 4)} Sparplan-Anteile "
            f"({fmt(kumulierte_sparrate_marktwert, 2)})" if zusaetzliche_stueckzahl_sparplan > 0 else ""
        )
        with st.expander("💶 Entnahmen und laufende Kosten", expanded=False):
            st.markdown(f"""
            <div class="rows">
                <div class="row">
                    <span class="row-label">Depotwert (nach Entnahmen)</span>
                    <span class="row-val">{fmt(depotwert_real_ist, 2)}
                        <span class="row-note">{_de_zahl(stueckzahl_real_ist, 4)} Anteile nach {verkaeufe_ausgefuehrt} Verkäufen à {fmt(entnahme_rate, 2)} zum Geldkurs (Spread-Annahme {FMT.pct(config.SPREAD_PCT, 2)}){sparrate_note}</span>
                    </span>
                </div>
                <div class="row">
                    <span class="row-label">Bisher ausgezahlt</span>
                    <span class="row-val">{fmt(ausgezahlt_ist, 2)}
                        <span class="row-note">zählt zum Gewinn „seit Kauf“ ({fmt_vz(gewinn_real, 2)})</span>
                    </span>
                </div>
                <div class="row">
                    <span class="row-label">Ohne Entnahmen (Vergleich)</span>
                    <span class="row-val">{fmt(brutto_ist, 2)}
                        <span class="row-note">so viel wäre das Depot wert, wenn nichts entnommen worden wäre</span>
                    </span>
                </div>
                <div class="row">
                    <span class="row-label">Laufende Kosten</span>
                    <span class="row-val">{FMT.pct(config.ZERTIFIKAT_GEBUEHR_PA_PCT, 2)} p.a.
                        <span class="row-note">Zertifikatsgebühr, bereits im Kurs eingepreist</span>
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    _depot_bereich.__exit__(None, None, None)

    # TABS
    # ---------- ANSICHTSWAHL: Dropdown statt Tab-Leiste ----------
    # Sieben Tabs passen auf keinem Smartphone nebeneinander - man musste sich
    # mit winzigen Pfeilen durchscrollen und sah nie, was es ueberhaupt gibt.
    # Das Dropdown zeigt alle Ansichten auf einen Blick und braucht eine Zeile.
    #
    # Zweiter, wichtigerer Vorteil: Streamlit rendert bei st.tabs IMMER ALLE
    # Inhalte, auch die unsichtbaren - also sieben Charts inkl. aller Abrufe
    # bei jedem Rerun. Hier wird nur die gewaehlte Ansicht berechnet.
    # Die Ansicht kommt aus den Kacheln ganz oben (navigation()).

    # Die Render-Funktionen unten arbeiten mit "with tab_x:" - dafuer reicht
    # ein gemeinsamer Container, da ohnehin nur eine Ansicht gezeichnet wird.
    _ansicht_container = st.container()
    tab_wealth = tab_ytd = tab_2021 = tab_candle = _ansicht_container
    tab_forecast = tab_scenarios = _ansicht_container

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _vergleichswerte_verwalten(offen=False):
        return charts_ansichten._vergleichswerte_verwalten({'PROG_BASIS': PROG_BASIS, '_h': _h, 'aendere_vergleichswerte': aendere_vergleichswerte, 'lade_vergleichswerte': lade_vergleichswerte, 'suche_instrument': suche_instrument, 'time': time, 'top500_optionen_bei_bedarf': top500_optionen_bei_bedarf, 'vergleich_label': vergleich_label}, offen=offen)

    def _render_vergleich_eigen():
        charts_ansichten.vergleich_eigen({'_vergleichswerte_verwalten': _vergleichswerte_verwalten, 'heute_date': heute_date, 'kennzahl_umschalter': kennzahl_umschalter, 'lade_benchmarks_mit_fortschritt': lade_benchmarks_mit_fortschritt, 'lade_vergleichswerte': lade_vergleichswerte, 'pct_ueber_tage': pct_ueber_tage, 'performance_tabelle_html': performance_tabelle_html, 'tab_wealth': tab_wealth, 'vergleich_farbe': vergleich_farbe})

    def _render_wealth():
        charts_ansichten.vermoegen({'_vergleichswerte_verwalten': _vergleichswerte_verwalten, 'ausgezahlt_ist': ausgezahlt_ist, 'benchmark_series': benchmark_series, 'benchmark_start_daten': benchmark_start_daten, 'depotwert_real_ist': depotwert_real_ist, 'df_chart': df_chart, 'einstand_aktiv': einstand_aktiv, 'entnahme_rate': entnahme_rate, 'gewinn_real': gewinn_real, 'haupt_name': haupt_name, 'heute_date': heute_date, 'is_live_history': is_live_history, 'kaufdatum_aktiv': kaufdatum_aktiv, 'kennzahl_umschalter': kennzahl_umschalter, 'lese_pills_auswahl_still': lese_pills_auswahl_still, 'notify_app_error': notify_app_error, 'pct_ueber_tage': pct_ueber_tage, 'performance_tabelle_html': performance_tabelle_html, 'pills_auswahl': pills_auswahl, 'rendite_pa_hochgerechnet': rendite_pa_hochgerechnet, 'rendite_pa_real': rendite_pa_real, 'sparplan_eingezahlt': sparplan_eingezahlt, 'startkapital_aktiv': startkapital_aktiv, 'tab_wealth': tab_wealth, 'vergleich_farbe': vergleich_farbe, 'zeige_chart_legende_liste': zeige_chart_legende_liste})
    if gewaehlte_ansicht == "📈 Vermögens- & Substanzaufbau":
        melde("ansicht", 0.3, "Baue Vermögensaufbau auf …")
        if eigen:
            # ohne Hauptposition (Startkapital/Kaufdatum des Admins): Vergleich der eigenen Vergleichswerte
            try:
                _render_vergleich_eigen()
            except Exception as e:
                st.error(f"⚠️ Fehler in diesem Tab: {e}")
                notify_app_error("Tab-Vermoegensaufbau-eigen", e)
        else:
            _render_wealth()
        lade_fertig()

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _render_ytd():
        charts_ansichten.seit_2026({'_vergleichswerte_verwalten': _vergleichswerte_verwalten, 'df_chart': df_chart, 'haupt_name': haupt_name, 'heute_date': heute_date, 'is_live_history': is_live_history, 'kennzahl_umschalter': kennzahl_umschalter, 'lade_benchmarks_mit_fortschritt': lade_benchmarks_mit_fortschritt, 'lese_pills_auswahl_still': lese_pills_auswahl_still, 'notify_app_error': notify_app_error, 'pct_ueber_tage': pct_ueber_tage, 'performance_tabelle_html': performance_tabelle_html, 'pills_auswahl': pills_auswahl, 'tab_ytd': tab_ytd, 'vergleich_farbe': vergleich_farbe, 'zeige_chart_legende_liste': zeige_chart_legende_liste})
    if gewaehlte_ansicht == "🔍 Seit 01.01.2026":
        melde("ansicht", 0.3, "Lade Vergleich seit 2026 …")
        _render_ytd()
        lade_fertig()

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _render_2021():
        charts_ansichten.seit_2021({'KEINE_HISTORIE': KEINE_HISTORIE, '_vergleichswerte_verwalten': _vergleichswerte_verwalten, 'aktueller_kurs': aktueller_kurs, 'get_historical_market_data': get_historical_market_data, 'haupt_name': haupt_name, 'heute_date': heute_date, 'is_live_data': is_live_data, 'kennzahl_umschalter': kennzahl_umschalter, 'kurs_tag': kurs_tag, 'lade_benchmarks_mit_fortschritt': lade_benchmarks_mit_fortschritt, 'lese_pills_auswahl_still': lese_pills_auswahl_still, 'notify_app_error': notify_app_error, 'pct_ueber_tage': pct_ueber_tage, 'performance_tabelle_html': performance_tabelle_html, 'pills_auswahl': pills_auswahl, 'tab_2021': tab_2021, 'vergleich_farbe': vergleich_farbe, 'zeige_chart_legende_liste': zeige_chart_legende_liste})
    if gewaehlte_ansicht == "🔎 Seit 01.01.2021":
        melde("ansicht", 0.3, "Lade Vergleich seit 2021 …")
        _render_2021()
        lade_fertig()

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _render_candle():
        charts_ansichten.candlestick({'df_chart': df_chart, 'is_live_history': is_live_history, 'notify_app_error': notify_app_error, 'tab_candle': tab_candle})
    if gewaehlte_ansicht == "🕯️ Tages-Candlestick":
        melde("ansicht", 0.3, "Baue Candlestick-Chart …")
        _render_candle()
        lade_fertig()

    # @st.fragment: dadurch loest eine Auswahl INNERHALB dieser Ansicht
    # nur diesen Bereich neu aus - vorher lief der komplette Seitenaufbau
    # erneut (Live-Kurse, Benchmarks, alle Positionen und
    # Beobachtungswerte), obwohl nur ein einziger Wert gefragt war.
    # Voraussetzung: NICHT in einen ausserhalb erzeugten Container
    # schreiben ("with tab_forecast:") - Streamlit verbietet das bei
    # Fragment-Reruns. Die Ansicht zeichnet daher direkt an ihrer Stelle.
    def _prognose_basis_verwalten():
        return prognose_ansichten.prognose_basis_verwalten({'PROG_BASIS': PROG_BASIS, '_h': _h, 'aendere_prognose_basis': aendere_prognose_basis, 'lade_prognose_basis': lade_prognose_basis, 'prognose_optionen': prognose_optionen, 'suche_instrument': suche_instrument, 'time': time, 'top500_optionen_bei_bedarf': top500_optionen_bei_bedarf})

    @st.fragment
    def _render_forecast():
        return prognose_ansichten.zukunfts_prognose({'_prognose_basis_verwalten': _prognose_basis_verwalten, '_startauswahl': _startauswahl, '_startwert': _startwert, '_zugang_pruefen': _zugang_pruefen, 'fmt_vz': fmt_vz, 'heute_date': heute_date, 'notify_app_error': notify_app_error, 'now_berlin': now_berlin, 'prognose_optionen': prognose_optionen, 'simuliere_bandbreite': simuliere_bandbreite})
    if gewaehlte_ansicht == "🔮 Zukunfts-Prognose":
        melde("ansicht", 0.3, "Berechne Prognose …")
        _render_forecast()
        if GH_STATE_READY:
            SL.leiste(st, "prognose", rueck=prognose_rueckgaengig,
                      hinweis="die Werteliste wird gespeichert; Renditen und Zeitraum gelten nur in dieser Sitzung")
        else:
            SL.leiste(st, "prognose", modus="sitzung")
        lade_fertig()

    # --- DEPOT-ANALYSE & OPTIMIERUNG (depot_analyse.py / depot_analyse_ui.py): bewertet das echte Depot,
    # Simulator rechnet nur virtuell (das gespeicherte Depot aendert sich hier nie ohne Bestaetigung)
    if gewaehlte_ansicht == ANSICHT_ANALYSE:
        melde("ansicht", 0.3, "Analysiere Depot …")
        _da_h = {"bestand": depot_bestand, "kurs_stand": f"{fetched_source} · {kurs_zeit_text}",
                 "gh_read": gh_read, "gh_read_taeglich": gh_read_taeglich, "gh_aktualisiere": gh_aktualisiere,
                 "pfad": upfad("state/depot_analyse.json"), "speichern": GH_STATE_READY,
                 "chronik": chronik_eintrag, "suche_instrument": suche_instrument, "get_live_kurs": get_live_kurs,
                 "get_kurshistorie": get_kurshistorie,
                 "analyse_depot_lesen": lambda: gh_read(upfad("state/analyse_depot.json"), None),
                 "monatsplan": (sparrate_aktiv if haupt_aktiv else 0.0) - (entnahme_rate if haupt_aktiv else 0.0),
                 "zur_bewertung": _zur_bewertung if _sichtbar(ANSICHT_BEWERTUNG) else None}

        @st.fragment
        def _render_analyse():
            _zugang_pruefen(ANSICHT_ANALYSE)
            try:
                import depot_analyse_ui
                depot_analyse_ui.seite(_da_h)
            except Exception as e:
                st.error(f"⚠️ Fehler in der Depot-Analyse: {e}")
                notify_app_error("Tab-Depot-Analyse", e)
        _render_analyse()
        lade_fertig()

    # @st.fragment: dadurch loest eine Auswahl INNERHALB dieser Ansicht
    # nur diesen Bereich neu aus - vorher lief der komplette Seitenaufbau
    # erneut (Live-Kurse, Benchmarks, alle Positionen und
    # Beobachtungswerte), obwohl nur ein einziger Wert gefragt war.
    # Voraussetzung: NICHT in einen ausserhalb erzeugten Container
    # schreiben ("with tab_scenarios:") - Streamlit verbietet das bei
    # Fragment-Reruns. Die Ansicht zeichnet daher direkt an ihrer Stelle.
    @st.fragment
    def _render_scenarios():
        return prognose_ansichten.szenario_simulator({'SZ': SZ, 'WIKIFOLIO_STARTKURS': WIKIFOLIO_STARTKURS, '_h': _h, '_startauswahl': _startauswahl, '_startwert': _startwert, '_zugang_pruefen': _zugang_pruefen, 'auflegung_fuer': auflegung_fuer, 'get_kurshistorie': get_kurshistorie, 'heute_date': heute_date, 'ist_wikifolio': ist_wikifolio, 'notify_app_error': notify_app_error, 'produkt_rendite_pa': produkt_rendite_pa, 'prognose_optionen': prognose_optionen, 're': re, 'speichere_auflegung': speichere_auflegung})
    if gewaehlte_ansicht == "📊 Szenario-Simulator (5 Jahre)":
        melde("ansicht", 0.3, "Berechne Szenarien …")
        _render_scenarios()
        SL.leiste(st, "szenario", modus="sitzung", hinweis="zum Ausprobieren")
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_EINST:
        # --- DIAGNOSE GANZ AM ENDE (statt Sidebar - auf Mobile oft nicht auffindbar).
        # Bewusst als Letztes: im Alltag interessieren die Kurse/Charts, der
        # Systemstatus wird nur im Fehlerfall gebraucht. Faellt der persistente
        # State aus, klappt der Expander weiterhin automatisch auf.
        if GH_STATE_READY:
            SL.leiste(st, SL_DEPOT, rueck=depot_rueckgaengig,
                      hinweis="Positionen, Sparrate, Entnahme und Beobachtungsliste")
        else:
            SL.leiste(st, SL_DEPOT, modus="sitzung")
        schritte.titel(st, "verwalten", 4)

        with st.expander("System-Status / Diagnose", expanded=not GH_STATE_READY):
            st.write(f"**Live-Daten aktiv:** {'✅ Ja' if is_live_data else '❌ Nein'} ({fetched_source})")
            st.write(f"**Chart-Historie live:** {'✅ Ja' if is_live_history else '❌ Nein'} ({hist_source_name})")
            st.write(f"**Discord-Webhook geladen:** {'✅ Ja' if DISCORD_WEBHOOK_URL else '❌ Nein'}")
            st.write(f"**Persistenter State (GitHub):** {'✅ Ja' if GH_STATE_READY else '❌ Nein - GITHUB_REPO/GITHUB_TOKEN fehlen'}")
            if GH_STATE_READY:
                st.caption(f"Repo: {GITHUB_REPO} • Branch: {config.GITHUB_STATE_BRANCH}")
            st.write(f"**High Watermark:** {high_watermark_anzeige:.3f}€")
            st.write(f"**Kurs aktuell / Vortag:** {aktueller_kurs:.3f} € / {vortag_kurs:.3f} €")
            _real_txt = (f"{erwartete_rendite_pa:.2f} % p.a."
                         + (f" ({erwartete_rendite_hinweis})" if erwartete_rendite_hinweis else "")
                         if erwartete_rendite_pa is not None
                         else "n. a. (unter 1 Monat Haltedauer)")
            _basis_quelle = (f"Rückfall eigener Kauf: {prognose_rueckfall_hinweis.split(' – ')[0]}"
                             if prognose_rueckfall_hinweis else "Produkt-Historie, Median")
            st.write(f"**Prognose-Basis:** realisiert seit Kauf {_real_txt} · "
                     f"Basis der 100k-Simulation ({_basis_quelle}) {prognose_rendite_pa:.2f} % p.a.")
            st.caption("Kurs-Alarme, Entwarnungen und Allzeithoch-Meldungen verschickt ausschließlich der "
                       "GitHub-Workflow (discord_price_alert.py); die App zeigt nur an.")
            # Reine Verbindungsprobe: als TEST gekennzeichnet, schreibt KEINEN Alarm-Zustand (DATA-03).
            # Discord bleibt dem Admin vorbehalten.
            if not eigen and st.button("🔔 Test-Nachricht an Discord senden", key="test_alarm_btn"):
                if _discord_senden(f"🧪 **TEST ({config.WKN})** – Verbindungstest aus der App, kein Kursalarm."):
                    st.success("Test-Nachricht gesendet.")
                else:
                    st.error("Test-Nachricht NICHT zugestellt (Webhook fehlt oder Discord-Fehler).")

            # Abgleich der Kauf-Eckdaten: macht sichtbar, ob die geladene Historie
            # wirklich am Kaufdatum beginnt - genau hier lief die Performance-
            # Tabelle frueher gegen einen anderen Startwert als die Kachel.
            if not eigen:       # Eckdaten der Admin-Hauptposition
                st.markdown("**Kauf-Eckdaten**")
                _cfg_kd = config.KAUFDATUM.strftime("%d.%m.%Y")
                _akt_kd = kaufdatum_aktiv.strftime("%d.%m.%Y")
                st.write(f"- Kaufdatum aktiv: **{_akt_kd}**" + (f" (config.py: {_cfg_kd})" if _akt_kd != _cfg_kd else " (= config.py)"))
                st.write(f"- Kaufkurs aktiv: **{kaufkurs_aktiv:.4f} €** "
                         f"({'config.py' if haupt_abweichend or not alle_positionen else 'gespeicherte Hauptposition'}"
                         f", config.py: {config.ANFANGSKURS:.4f} €)")
                st.write(f"- Stückzahl: **{stueckzahl_aktiv:.4f}** ({fmt(startkapital_aktiv, 2)} ÷ {kaufkurs_aktiv:.4f} €)")
                if not df_chart.empty:
                    _ds, _de = df_chart.index.min(), df_chart.index.max()
                    _warnung = " ⚠️ weicht vom Kaufdatum ab" if _ds.date() != kaufdatum_aktiv else ""
                    st.write(f"- Kursdaten von **{_ds.strftime('%d.%m.%Y')}** bis {_de.strftime('%d.%m.%Y')}"
                             f" ({len(df_chart)} Handelstage){_warnung}")
                    st.write(f"- Erster Schlusskurs der Reihe: **{df_chart['Close'].iloc[0]:.4f} €**")

    begriffe_erklaeren(gewaehlte_ansicht)


# ---------- LOGIN: vor allem anderen (ohne [login] in den Secrets aus) ----------
# ---------- LADEANZEIGE MIT HOCHGERECHNETEM FORTSCHRITT (alle Ansichten) ----------
# Reines CSS kann die Prozentzahl auf dem iPhone (Safari) nicht hochzaehlen - deshalb
# ein kleines Skript, das EINMAL in die Seite eingesetzt wird und dort dauerhaft
# laeuft: Es beobachtet Streamlits Lauf-Status und zeigt ab 0,5 s Ladezeit ein
# Banner, dessen Zahl und Balken gemeinsam hochlaufen (schnell, dann langsamer,
# max. 95 %); ist die Seite fertig, springt es auf 100 % und verschwindet.
# Zeigt die App ihren genauen Balken (.loading-overlay), tritt es zurueck.
_LADE_JS = """
<script>
(function () {
  var P = window.parent, D = P.document;
  if (P.__ladeBanner) return;
  P.__ladeBanner = true;
  var code = function () {
    var D = document;
    D.documentElement.classList.add('lade-js');
    D.documentElement.lang = 'de';          // deutsche Silbentrennung (hyphens: auto) statt Trennung mitten im Wort
    // Eingabefelder nebeneinander buendig: Beschriftungen derselben Zeile bekommen die Hoehe der hoechsten
    // (sonst rutscht ein Feld nach unten, wenn seine Beschriftung zwei Zeilen braucht und die daneben eine)
    var angleichen = function () {
      var main = D.querySelector('[data-testid="stMain"]'); if (!main) return;
      main.querySelectorAll('[data-testid="stHorizontalBlock"]').forEach(function (hb) {
        var spalten = Array.prototype.filter.call(hb.children, function (c) { return c.matches('[data-testid="stColumn"]'); });
        if (spalten.length < 2) return;
        var labs = [];
        spalten.forEach(function (c) {
          c.querySelectorAll('[data-testid="stWidgetLabel"]').forEach(function (l) {
            if (l.closest('[data-testid="stHorizontalBlock"]') === hb) { l.style.minHeight = ''; labs.push(l); }
          });
        });
        labs = labs.filter(function (l) { return l.getBoundingClientRect().width > 0; });
        var fertig = [];
        for (var runde = 0; runde < 12; runde++) {
          var offen = labs.filter(function (l) { return fertig.indexOf(l) < 0; });
          if (offen.length < 2) break;
          var tops = offen.map(function (l) { return l.getBoundingClientRect().top; });
          var t0 = Math.min.apply(null, tops);
          var zeile = offen.filter(function (l, i) { return tops[i] - t0 < 30; });
          var h = Math.max.apply(null, zeile.map(function (l) { return l.getBoundingClientRect().height; }));
          if (zeile.length > 1) zeile.forEach(function (l) { if (l.getBoundingClientRect().height < h - 1) l.style.minHeight = h + 'px'; });
          fertig = fertig.concat(zeile);
        }
      });
    };
    var angleichenPlan = null;
    var angleichenSpaeter = function () {
      if (angleichenPlan) return;
      angleichenPlan = setTimeout(function () { angleichenPlan = null; window.requestAnimationFrame(angleichen); }, 120);
    };
    new window.MutationObserver(angleichenSpaeter).observe(D.body, { childList: true, subtree: true, characterData: true });
    window.addEventListener('resize', angleichenSpaeter);
    var st = D.createElement('style');
    st.textContent =
      'html.lade-js [data-testid="stApp"]::before, html.lade-js [data-testid="stApp"]::after { display:none !important; }' +
      'html.lade-js .loading-overlay { display:none !important; }' +
      '#lade-banner { position:fixed; top:0; left:0; right:0; z-index:100000; height:auto; box-sizing:border-box;' +
      ' padding:10px 16px 8px; background:#0B1220; border-bottom:1px solid #22344C;' +
      ' box-shadow:0 2px 14px rgba(0,0,0,.6); display:none; pointer-events:none; }' +
      '#lade-banner .lb-kopf { display:flex; align-items:center; justify-content:space-between; gap:12px; }' +
      /* Prozentzahl nie umbrechen - ein langer Ladetext wird gekuerzt, nicht die Zahl */
      '#lade-banner .lb-kopf > span:first-child { flex:0 0 auto; white-space:nowrap; }' +
      '#lade-banner .lb-pct { font-family:"JetBrains Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums;' +
      ' font-size:1.35rem; font-weight:700; line-height:1.2; color:#E9EBEF; flex-shrink:0; }' +
      '#lade-banner .lb-text { flex:1 1 auto; text-align:right; font-size:.9rem; font-weight:600; color:#7C8493; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }' +
      '#lade-banner .lb-pfeil { color:#34D399; font-size:.95rem; margin-right:4px; }' +
      /* Kurs-Chart als Ladebalken: Linie waechst mit dem Fortschritt, Bulle vorne, Baer hinterher */
      '#lade-banner .lb-chart { position:relative; height:44px; margin-top:4px; }' +
      '#lade-banner .lb-chart > svg { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }' +
      '#lade-banner .lb-spur { stroke:#22344C; stroke-width:1; stroke-dasharray:3 3; vector-effect:non-scaling-stroke; }' +
      '#lade-banner .lb-linie { fill:none; stroke:#34D399; stroke-width:2.2; stroke-linejoin:round; stroke-linecap:round;' +
      ' vector-effect:non-scaling-stroke; filter:drop-shadow(0 0 3px rgba(52,211,153,.55)); }' +
      '#lade-banner .lb-flaeche { fill:url(#lb-verlauf); stroke:none; }' +
      '#lade-banner .lb-tier { position:absolute; line-height:0; transform:translate(-62%,-92%);' +
      ' transition:left .2s linear, top .2s linear; will-change:left,top; }' +
      '__TIER_CSS__' +
      /* Endgeraet: Handy kompakt (flacher, kleinere Tiere); Laptop/Desktop hoeher, Inhalt zentriert und
         begrenzt (sonst wird die Kurslinie auf breiten Monitoren zum flachen Strich), groessere Tiere */
      '@media (max-width: 699px) { #lade-banner { padding:8px 12px 6px; } #lade-banner .lb-text { font-size:.8rem; }' +
      ' #lade-banner .lb-chart { height:40px; } #lade-banner .lb-pct { font-size:1.2rem; }' +
      ' #lade-banner .lb-tier svg { width:44px; height:auto; } #lade-banner .lb-baer svg { width:40px; } }' +
      '@media (min-width: 900px) { #lade-banner { padding:12px 24px 8px; }' +
      ' #lade-banner .lb-kopf, #lade-banner .lb-chart { max-width:1100px; margin-left:auto; margin-right:auto; }' +
      ' #lade-banner .lb-chart { height:62px; margin-top:6px; } #lade-banner .lb-pct { font-size:1.5rem; }' +
      ' #lade-banner .lb-tier svg { width:76px; height:auto; } #lade-banner .lb-baer svg { width:70px; } }' +
      /* helle Ansicht: heller Glas-Streifen */
      '#lade-banner.lb-hell { background:#F8FAFC; border-bottom-color:#D5DBE5; box-shadow:0 2px 14px rgba(15,23,42,.12); }' +
      '#lade-banner.lb-hell .lb-pct { color:#0F172A; } #lade-banner.lb-hell .lb-text { color:#5B6474; }' +
      '#lade-banner.lb-hell .lb-pfeil { color:#059669; } #lade-banner.lb-hell .lb-spur { stroke:#CBD3DF; }' +
      '#lade-banner.lb-hell .lb-linie { stroke:#059669; filter:none; }' +

      /* reine Navigation (Ansicht/Schritt/Unterseite): Inhalt nicht abdunkeln */
      'html.lade-still [data-stale="true"], html.lade-still .stale-element { opacity:1 !important; transition:none !important; }' +
      /* kurze Neuberechnungen (die meisten Klicks) nicht abdunkeln - erst nach 1,2 s */
      'html.lade-js [data-stale="true"], html.lade-js .stale-element { transition:opacity .25s ease 1.2s !important; }' +
      /* Ansichtswechsel ueber das Menue: die alte Ansicht (z. B. die Menue-Kacheln) bis zum Ende des Aufbaus
         ganz ausblenden - halb durchsichtig und ohne ihr Layout wirkte sie wie ein verzerrtes Bild */
      'html.lade-wechsel [data-stale="true"], html.lade-wechsel .stale-element { display:none !important; }';
    D.head.appendChild(st);
    var b = D.createElement('div');
    b.id = 'lade-banner';
    var SVG = 'http://www.w3.org/2000/svg';
    b.innerHTML = '<div class="lb-kopf"><span><span class="lb-pfeil">▲</span><span class="lb-pct">0 %</span></span>' +
                  '<span class="lb-text">Lade Daten …</span></div>' +
                  '<div class="lb-chart"><svg viewBox="0 0 100 30" preserveAspectRatio="none">' +
                  '<defs><linearGradient id="lb-verlauf" x1="0" y1="0" x2="0" y2="1">' +
                  '<stop offset="0" stop-color="#34D399" stop-opacity=".35"/><stop offset="1" stop-color="#34D399" stop-opacity="0"/>' +
                  '</linearGradient><clipPath id="lb-clip"><rect x="0" y="-10" width="0" height="50"/></clipPath></defs>' +
                  '<line class="lb-spur" x1="0" y1="29" x2="100" y2="29"/>' +
                  '<g clip-path="url(#lb-clip)"><path class="lb-flaeche"/><polyline class="lb-linie"/></g></svg>' +
                  '<span class="lb-tier lb-baer" title="Bär">__BAER__</span>' +
                  '<span class="lb-tier lb-bulle" title="Bulle">__BULLE__</span></div>';
    D.body.appendChild(b);
    var pct = b.querySelector('.lb-pct'), txt = b.querySelector('.lb-text');
    var clip = b.querySelector('#lb-clip rect'), linie = b.querySelector('.lb-linie'), flaeche = b.querySelector('.lb-flaeche');
    var bulle = b.querySelector('.lb-bulle'), baer = b.querySelector('.lb-baer');
    /* Jede Ladung ein neuer "Kursverlauf": Zufallsweg mit Aufwaertstrend (0..1), 61 Punkte */
    var kurs = [], N = 60, ABSTAND = 15;
    function neuerKurs() {
      /* Desktop: mehr Kurspunkte (feinere Linie) und der Baer naeher dran (die Strecke ist breiter) */
      var gross = window.matchMedia && window.matchMedia('(min-width: 900px)').matches;
      N = gross ? 120 : 60; ABSTAND = gross ? 9 : 15;
      kurs = []; var v = 0.12;
      for (var i = 0; i <= N; i++) {
        v += 0.78 / N + (Math.random() - 0.5) * (gross ? 0.065 : 0.09);
        v = Math.max(0.03, Math.min(0.97, v));
        kurs.push(v);
      }
      /* auf die volle Chart-Hoehe strecken, damit der Verlauf auch auf breiten Bildschirmen lebt */
      var lo = Math.min.apply(null, kurs), hi = Math.max.apply(null, kurs), sp = Math.max(hi - lo, 0.2);
      kurs = kurs.map(function (k) { return 0.04 + (k - lo) / sp * 0.72; });
      var pts = kurs.map(function (k, i) { return (i * 100 / N).toFixed(2) + ',' + (28 - k * 25).toFixed(2); });
      linie.setAttribute('points', pts.join(' '));
      flaeche.setAttribute('d', 'M0,29 L' + pts.join(' L') + ' L100,29 Z');
    }
    function hoehe(p) {           /* y des Kurses an Position p (0..100) in % der Chart-Hoehe */
      var x = Math.max(0, Math.min(100, p)) * N / 100, i = Math.floor(x), f = x - i;
      var k = kurs[i] + ((kurs[Math.min(i + 1, N)] - kurs[i]) * f);
      return (28 - k * 25) / 30 * 100;
    }
    function tiere(p) {
      var pb = Math.max(p - ABSTAND, 0);
      clip.setAttribute('width', p);
      bulle.style.left = p + '%'; bulle.style.top = hoehe(p) + '%';
      baer.style.left = pb + '%'; baer.style.top = hoehe(pb) + '%';
      baer.style.opacity = p > 4 ? '1' : '0';
    }
    neuerKurs();
    /* EINE Anzeige fuer alles: der genaue Balken der App (.loading-overlay) wird nur noch
       ausgelesen, nicht mehr gezeigt. Angezeigt wird immer der hoechste Wert aus Hochrechnung
       und genauem Stand - die Zahl laeuft so nur vorwaerts, von 0 bis 100 %. Folgt direkt
       ein weiterer Ladeschritt (innerhalb NACHLAUF_MS), laeuft die Zahl einfach weiter. */
    var start = 0, timer = null, sichtbar = false, wert = 0, ende = null;
    /* Balken erst ab 1,2 s Rechenzeit; nach dem Ende kurz 100 % und weg (vorher 0,6 + 0,35 s
       Nachlauf - der Balken stand dadurch noch rund eine Sekunde, obwohl die Seite fertig war,
       und ein Klick in dieser Zeit liess ihn einfach weiterlaufen) */
    var AB_SEK = 1.2, NACHLAUF_MS = 250, HUNDERT_MS = 150;
    /* Klicks auf reine Navigation (Container mit Key "pl_nav...") zeigen keinen Ladebalken:
       die Seite wird zwar neu gerechnet, das dauert aber nur Sekundenbruchteile. Dauert es
       ausnahmsweise laenger als 4 s, erscheint der Balken doch. */
    var navKlick = 0, still = false, menueKlick = 0, wechsel = false;
    function merkeNav(e) {
      var t = e.target;
      if (t && t.closest && t.closest('[class*="st-key-pl_nav"]')) navKlick = Date.now();
      /* Kachel im Menue oder Knopf "Menue" in der Kopfleiste: Wechsel der Ansicht */
      if (t && t.closest && t.closest('.st-key-nav_menue button, .st-key-nav_menue_btn')) menueKlick = Date.now();
    }
    D.addEventListener('pointerdown', merkeNav, true);
    D.addEventListener('keydown', merkeNav, true);
    function setze(p) { wert = p; pct.textContent = Math.floor(p) + ' %'; tiere(p); }
    function tick() {
      var t = (Date.now() - start) / 1000 - AB_SEK;
      var ov = D.querySelector('.loading-overlay');
      var genau = null;
      if (ov) {
        var g = parseInt((ov.querySelector('.loading-pct') || {}).textContent, 10);
        if (!isNaN(g)) genau = Math.min(g, 99);
        var tt = (ov.querySelector('.loading-text') || {}).textContent;
        if (tt) txt.textContent = tt;
      }
      if (still && !sichtbar && t < 2.8) return;
      if (t < 0 && genau === null && !sichtbar) return;
      if (!sichtbar) {
        /* helle oder dunkle Ansicht? an der Hintergrundfarbe der App erkennen */
        var bg = getComputedStyle(D.querySelector('[data-testid="stApp"]') || D.body).backgroundColor.match(/[0-9]+/g) || [0, 0, 0];
        b.classList.toggle('lb-hell', (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) > 150);
        b.style.display = 'block'; sichtbar = true;
      }
      var schaetz = 95 * (1 - Math.exp(-Math.max(t, 0) / 3.5));
      var ziel = Math.max(schaetz, genau === null ? 0 : genau);
      /* nie rueckwaerts; bei genauem Stand weich nachziehen statt springen */
      var neu = Math.max(wert, wert + (ziel - wert) * 0.35);
      setze(Math.min(neu, 99));
    }
    function fertig() {
      if (timer) { clearInterval(timer); timer = null; }
      if (!sichtbar) { wert = 0; return; }
      ende = setTimeout(function () {
        ende = null;
        if (timer) return;                    /* es laedt schon weiter */
        setze(100);
        setTimeout(function () {
          if (!timer) { b.style.display = 'none'; sichtbar = false; setze(0); txt.textContent = 'Lade Daten …'; }
        }, HUNDERT_MS);
      }, NACHLAUF_MS);
    }
    function pruefe() {
      var app = D.querySelector('[data-testid="stApp"]');
      if (!app) return;
      var s = app.getAttribute('data-test-script-state');
      var laeuft = (s === 'running' || s === 'rerunRequested');
      if (laeuft && !timer) {
        if (!sichtbar) {
          start = Date.now(); neuerKurs(); setze(0);
          still = (Date.now() - navKlick) < 2500;
          D.documentElement.classList.toggle('lade-still', still);
        }   /* sonst: laeuft vom bisherigen Stand weiter */
        if ((Date.now() - menueKlick) < 2500) { wechsel = true; D.documentElement.classList.add('lade-wechsel'); }
        if (ende) { clearTimeout(ende); ende = null; }
        timer = setInterval(tick, 100);
      } else if (!laeuft && timer) {
        fertig();
        if (wechsel) { wechsel = false; menueKlick = 0; D.documentElement.classList.remove('lade-wechsel'); }
        if (still) { still = false; navKlick = 0; setTimeout(function () {
          if (!timer) D.documentElement.classList.remove('lade-still'); }, 400); }
      }
    }
    new MutationObserver(pruefe).observe(D.body, { attributes: true, subtree: true,
                                                   attributeFilter: ['data-test-script-state'] });
    pruefe();
    /* Blau-Design: umrandete Bloecke (st.container(border=True)) als Karte markieren -
       Streamlit kennzeichnet sie im HTML nicht, erkennbar sind sie nur am Rahmen */
    var karteTimer = null;
    function karten() {
      karteTimer = null;
      var bl = D.querySelectorAll('[data-testid="stVerticalBlock"]:not(.karte)');
      for (var i = 0; i < bl.length; i++) {
        if (parseFloat(getComputedStyle(bl[i]).borderTopWidth) >= 1) bl[i].classList.add('karte');
      }
    }
    new MutationObserver(function () { if (!karteTimer) karteTimer = setTimeout(karten, 80); })
      .observe(D.body, { childList: true, subtree: true });
    karten();
  };
  var s = D.createElement('script');
  s.textContent = '(' + code.toString() + ')();';
  D.head.appendChild(s);
})();
</script>
"""
# Silberner Bulle und Baer (ui_stil.tier_svg) - ein Markup fuer Banner und Kurs-Ladebalken
_LADE_JS = (_LADE_JS.replace("__BULLE__", UI.tier_svg("bulle", 54)).replace("__BAER__", UI.tier_svg("baer", 50))
            .replace("__TIER_CSS__", UI.TIER_CSS))
try:
    import streamlit.components.v1 as _components
    with st.container(key="lade_js"):
        _components.html(_LADE_JS, height=0)
    st.markdown("<style>.st-key-lade_js { display: none !important; }</style>", unsafe_allow_html=True)
except Exception:
    pass                     # ohne Skript bleibt die reine CSS-Anzeige

# Audit SEC-03: login.gate ist fail-closed (ohne [login]-Konfiguration nur Fehlerseite) und
# schreibt Benutzerdaten per Versionspruefung ueber gh_aktualisiere.
st.session_state["_speicher_fehler"] = False
st.session_state["_nutzer"] = login.gate(st, gh_read, gh_read_cached, gh_write, chronik_eintrag_global,
                                         gh_aktualisiere=gh_aktualisiere,
                                         speicher_fehler=lambda: st.session_state.get("_speicher_fehler"))

render_dashboard()
