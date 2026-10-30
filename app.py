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
import requests
import streamlit as st

import config
import github_store
import chronik
import login
import nutzerdaten
import kurs_dienst as KD
import formate as FMT
import ui_stil as UI
import ui_hell
import schritte
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


# --- ZAHLENFORMATIERUNG (Punkt = Tausender, Komma = Dezimal) ---
def _kaufm(val, dec=2):
    """Kaufmaennisch runden (360°-Pruefung F-07) - zentral in formate.runden. -> float"""
    return FMT.runden(val, dec)


def fmt(val, dec=2):
    """Euro-Betrag: '1.234,56 €' (zentral: formate.eur)."""
    return FMT.eur(val, max(dec, 0))


def fmt_vz(val, dec=2):
    """Wie fmt, aber immer mit Vorzeichen: '+1.234,00 €' / '−500,00 €' (Audit DEP-13).
    Werte, die auf 0 runden, erscheinen als '+0,00 €' (kein '−0,00 €')."""
    return FMT.eur(val, dec, vz=True)


def vz_zahl(wert, nachkomma=2):
    """Deutsche Zahl mit Vorzeichen ohne Einheit: '+1.234,56' / '−0,50' (Audit DEP-13)."""
    return FMT.zahl(wert, nachkomma, vz=True)


def wikifolio_werte(kat, lang):
    """Alle wikifolios der Ranglisten (Top 50 je Zeitraum + Top-500-Langliste) zu einer Tabelle:
    -> {wkn: {"name", "wkn", "perf": {zeitraum: Entwicklung %}}}. Ein Zeitraum fehlt, wenn der Wert
    dort nicht unter den Top 500 ist."""
    werte = {}

    def dazu(name, wkn, zr, perf):
        if not wkn or not isinstance(perf, (int, float)):
            return
        w = werte.setdefault(wkn, {"name": str(name or wkn), "wkn": wkn, "perf": {}})
        w["perf"].setdefault(zr, float(perf))

    for zr, liste in ((kat or {}).get("top") or {}).items():
        for e in liste or []:
            dazu(e.get("name"), e.get("wkn"), zr, e.get("perf"))
    for zr, liste in ((lang or {}).get("top") or {}).items():
        for r in liste or []:
            if len(r) >= 3:
                dazu(r[0], r[1], zr, r[2])
    return werte


def wikifolio_rangliste(werte, zeitraum, begriff="", n=500):
    """Rangliste nach einem Zeitraum (die besten n), danach optional nach Name/WKN gefiltert -
    der Rang bleibt der in der vollen Liste."""
    liste = sorted((w for w in werte.values() if w["perf"].get(zeitraum) is not None),
                   key=lambda w: (-w["perf"][zeitraum], w["name"].lower()))[:n]
    liste = [dict(w, rang=i) for i, w in enumerate(liste, 1)]
    b = str(begriff or "").strip().lower()
    return [w for w in liste if b in (w["name"] + " " + w["wkn"]).lower()] if b else liste


def _h(text):
    """HTML-Escaping fuer Nutzer-/Fremdtexte in unsafe_allow_html-Bausteinen (Audit SEC-04)."""
    return html.escape("" if text is None else str(text), quote=True)


# --- SPARPLAN / ENTNAHME: EIN gemeinsamer Monatsplan (Audit DEP-03/DEP-11) ---
def monats_termine(start, bis, ab_k=0):
    """Alle Termine start + k Monate (k >= ab_k), die am oder vor 'bis' liegen.
    Monatsenden werden von pandas gekappt (31.01. + 1 Monat = 28./29.02.)."""
    if start is None or bis is None:
        return []
    start_ts = pd.Timestamp(start).normalize()
    bis_ts = pd.Timestamp(bis).normalize()
    termine = []
    k = ab_k
    while True:
        t = start_ts + pd.DateOffset(months=k)
        if t > bis_ts:
            break
        termine.append(t)
        k += 1
    return termine


def sparplan_termine(start, heute):
    """Sparplan-Kaeufe: der erste am Starttag (k=0), dann monatlich."""
    return monats_termine(start, heute, ab_k=0)


def entnahme_termine(kaufdatum, heute):
    """Entnahmen: erstmals einen Monat nach dem Kauf (k=1), dann monatlich."""
    return monats_termine(kaufdatum, heute, ab_k=1)


def kumulierte_entnahme(index, termine, rate):
    """Je Zeitpunkt des Index: Summe aller Entnahmen bis einschliesslich dieses Tages."""
    sortiert = sorted(pd.Timestamp(t) for t in termine)
    return [rate * bisect.bisect_right(sortiert, pd.Timestamp(ts).normalize()) for ts in index]


def sparplan_phasen(state):
    """Gespeicherter Sparplan (Audit DEP-02) -> (start_datum | None, [(ab_datum, rate), ...]).
    Format: {"start_datum": "YYYY-MM-DD", "rate": 500.0, "phasen": [{"ab": ..., "rate": ...}]}.
    Altbestand nur mit start_datum (Rate wurde frueher nicht gespeichert) -> leere Phasen."""
    if not isinstance(state, dict) or not state.get("start_datum"):
        return None, []
    try:
        start = datetime.date.fromisoformat(str(state["start_datum"]))
    except ValueError:
        return None, []
    phasen = []
    for ph in state.get("phasen") or []:
        try:
            phasen.append((datetime.date.fromisoformat(str(ph["ab"])), float(ph["rate"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not phasen and state.get("rate") is not None:
        try:
            phasen = [(start, float(state["rate"]))]
        except (TypeError, ValueError):
            phasen = []
    return start, sorted(phasen)


def sparrate_am(phasen, tag):
    """Sparrate, die an 'tag' gilt (letzte Phase mit ab <= tag), sonst 0."""
    t = pd.Timestamp(tag).normalize()
    rate = 0.0
    for ab, r in phasen:
        if pd.Timestamp(ab) <= t:
            rate = r
        else:
            break
    return rate


def sparplan_state_neu(state, rate, heute):
    """Zustand nach dem AUSDRUECKLICHEN Speichern einer Sparrate > 0 (Audit DEP-02).
    Neuer Plan startet heute; eine geaenderte Rate gilt ab heute (fruehere Kaeufe
    behalten ihre Rate). Altbestand ohne gespeicherte Rate: Rate gilt ab Start.
    -> neuer Zustand oder None (nichts zu aendern)."""
    rate = float(rate)
    start, phasen = sparplan_phasen(state)
    if start is None:
        h = heute.isoformat()
        return {"start_datum": h, "rate": rate, "phasen": [{"ab": h, "rate": rate}]}
    if phasen and abs(phasen[-1][1] - rate) < 1e-9:
        return None
    if not phasen:
        phasen = [(start, rate)]
    else:
        phasen = [p for p in phasen if p[0] < heute] + [(heute, rate)]
    return {"start_datum": start.isoformat(), "rate": rate,
            "phasen": [{"ab": ab.isoformat(), "rate": r} for ab, r in phasen]}


def sparplan_einzelkaeufe(termine, kursreihe, rate, ersatzkurs=None, max_verzug_tage=7):
    """Jeder ausgefuehrte Sparplan-Kauf als (kauftag, betrag, stueck).
    Ausfuehrung wie beim Broker am ersten Handelstag am/nach dem Termin (Audit A-27,
    gleiche Regel wie die Verkaeufe in berechne_reale_stueckzahl); gibt es dafuer noch
    keinen Kurs (Termin heute/am Wochenende), gilt der Ersatzkurs (Live-Kurs), sonst
    bleibt der Kauf offen. Liegt der naechste Kurs mehr als max_verzug_tage nach dem
    Termin (Termin vor Beginn der Kursdaten), wird nicht zu einem spaeteren Kurs gekauft.
    rate: Zahl oder Funktion termin -> Rate (Phasen)."""
    if not callable(rate) and (not rate or rate <= 0):
        return []
    rate_fn = rate if callable(rate) else (lambda _t, _r=rate: _r)
    kaeufe = []
    for t in termine:
        t = pd.Timestamp(t).normalize()
        r_t = rate_fn(t) or 0.0
        if r_t <= 0:
            continue
        tag, preis = None, None
        if kursreihe is not None and len(kursreihe):
            danach = kursreihe[(kursreihe.index >= t) & (kursreihe.index <= t + pd.Timedelta(days=max_verzug_tage))]
            if len(danach):
                tag, preis = pd.Timestamp(danach.index[0]).normalize(), float(danach.iloc[0])
        nach_datenende = kursreihe is None or not len(kursreihe) or t > pd.Timestamp(kursreihe.index[-1])
        if preis is None and ersatzkurs and nach_datenende:
            tag, preis = t, float(ersatzkurs)
        if preis and preis > 0:
            kaeufe.append((tag, float(r_t), r_t / preis))
    return kaeufe


def sparplan_kaeufe(termine, kursreihe, rate, ersatzkurs=None):
    """-> (eingezahlt, stueck) aller ausgefuehrten Kaeufe (sparplan_einzelkaeufe).
    Nur tatsaechlich ausgefuehrte Kaeufe (mit Kurs) zaehlen zum Einstand."""
    kaeufe = sparplan_einzelkaeufe(termine, kursreihe, rate, ersatzkurs)
    return sum(k[1] for k in kaeufe), sum(k[2] for k in kaeufe)


def sparplan_verlauf(index, kaeufe):
    """Kumulierte (stueck, eingezahlt) je Zeitpunkt des Index (Audit A-09: Chart und
    Tabelle enthalten die Sparplan-Anteile ab ihrem Kauftag)."""
    stueck, geld = [], []
    if not len(index):
        return stueck, geld
    # Kaeufe nach dem letzten Punkt (vorgemerkt zum Live-Kurs, z. B. Termin am Wochenende)
    # zaehlen am letzten Punkt mit - sonst fehlten sie im Chart, waehrend die Kachel sie zeigt.
    ende = pd.Timestamp(index[-1]).normalize()
    kaeufe = [(min(k[0], ende), k[1], k[2]) for k in kaeufe]
    for ts in index:
        tag = pd.Timestamp(ts).normalize()
        stueck.append(sum(k[2] for k in kaeufe if k[0] <= tag))
        geld.append(sum(k[1] for k in kaeufe if k[0] <= tag))
    return stueck, geld


def entnahme_rate_aus_state(state, standard):
    """Monatliche Entnahme (Audit DEP-03): gespeicherter Wert, sonst Standard (config.ENTNAHME_PM)."""
    try:
        if isinstance(state, dict) and state.get("rate") is not None:
            return max(0.0, float(state["rate"]))
    except (TypeError, ValueError):
        pass
    return max(0.0, float(standard or 0.0))


def entnahme_standard(eigen):
    """Entnahme ohne gespeicherten Wert: Admin config.ENTNAHME_PM, normale Benutzer 0."""
    return 0.0 if eigen else float(getattr(config, "ENTNAHME_PM", 0.0) or 0.0)


def haupt_position_aktiv(eigen, sparplan_phasen_liste, sparplan_eingezahlt=0.0):
    """Gibt es eine Hauptposition (Depotwert-Kachel, Vermoegens-Charts)? Admin / ohne
    Login immer; normale Benutzer nur mit eigenem Sparplan (Startkapital 0)."""
    if not eigen:
        return True
    return bool(sparplan_phasen_liste) or float(sparplan_eingezahlt or 0.0) > 0


def hochgerechnete_rendite_pa(kurs, kaufkurs, tage, min_tage=30):
    """Prognose-Hochrechnung bei Historie unter 1 Jahr (Nutzerentscheid zu DEP-08):
    geometrische Ø-Monatsrendite r_m = (1+gesamt)^(1/monate) - 1 mit
    monate = tage / 30,4375, hochgerechnet auf r_pa = (1+r_m)^12 - 1.
    Unter min_tage (1 Monat) bzw. bei ungueltigen Kursen -> None.
    -> (rate_pa_pct, monate, rate_mo_pct) | None"""
    if not kaufkurs or kaufkurs <= 0 or not kurs or kurs <= 0 or tage < min_tage:
        return None
    monate = tage / 30.4375          # 365,25 / 12
    r_m = (kurs / kaufkurs) ** (1 / monate) - 1
    return ((1 + r_m) ** 12 - 1) * 100, monate, r_m * 100


def prognose_rate_rueckfall(kurs, kaufkurs, tage, min_tage=30):
    """Ersatz-Prognoserate, wenn die Produkt-Historie keine Rate liefert (Audit DEP-08):
    ab 365 Tagen realisierte Rendite p.a. (unveraendert); von min_tage (1 Monat) bis
    unter 1 Jahr die auf ein Jahr hochgerechnete Ø-Monatsrendite (mit Hinweis);
    darunter 0 % (bewusst neutral, manuell ueberschreibbar).
    -> (rate_pa, hinweis | None)"""
    if tage >= 365:
        r = realisierte_rendite_pa(kurs, kaufkurs, tage, 365)
        if r is not None:
            return r, None
    else:
        h = hochgerechnete_rendite_pa(kurs, kaufkurs, tage, min_tage)
        if h is not None:
            r, monate, r_m = h
            return r, (f"Hochgerechnet aus {monate:.1f} Monaten (Ø Monatsrendite {r_m:+.2f} %) – "
                       "vorläufig, bis 1 Jahr Historie vorliegt")
    return 0.0, "Zu kurze Historie (< 1 Monat) – 0 % p.a. angenommen, bitte bei Bedarf anpassen"


def depot_kennzahlen(stueck_basis, stueck_sparplan, kurs, startkapital, sparplan_eingezahlt,
                     entnahme_rate, anzahl_entnahmen):
    """Kennzahlen 'seit Kauf' (Audit DEP-01/DEP-03): Einstand = Startkapital + tatsaechlich
    eingezahlte Sparraten; Netto = Brutto - Rate x Anzahl Entnahmen seit Kauf."""
    brutto = (stueck_basis + stueck_sparplan) * kurs
    einstand = startkapital + sparplan_eingezahlt
    gewinn = brutto - einstand
    entnommen = entnahme_rate * anzahl_entnahmen
    return {
        "brutto": brutto, "einstand": einstand, "gewinn": gewinn,
        "rendite_pct": (gewinn / einstand * 100) if einstand else 0.0,
        "entnommen": entnommen, "netto": brutto - entnommen,
    }


def depot_kennzahlen_real(stueck_real, stueck_sparplan, kurs, einstand, ausgezahlt):
    """Kennzahlen bei ECHTEN Entnahmen (Audit A-12): Depotwert = verbliebene Anteile x Kurs;
    das bereits ausgezahlte Geld gehoert zum Ergebnis: Gewinn = Depotwert + ausgezahlt - Einstand.
    Ohne Entnahmen identisch mit depot_kennzahlen (brutto/gewinn/rendite_pct)."""
    wert = (stueck_real + stueck_sparplan) * kurs
    gewinn = wert + ausgezahlt - einstand
    return {"wert": wert, "gewinn": gewinn, "ausgezahlt": ausgezahlt,
            "rendite_pct": (gewinn / einstand * 100) if einstand else 0.0}


def rendite_pa_geldgewichtet(zahlungen, endwert, heute):
    """Interner Zinsfuss (XIRR) in % p. a.: zahlungen = [(datum, betrag)] mit Einzahlungen positiv
    (Startkapital, Sparraten) und Auszahlungen negativ (Entnahmen); endwert = Depotwert am Tag heute.
    Jede Zahlung zaehlt ab ihrem eigenen Datum - eine Sparrate von gestern hatte keine Zeit zu wachsen.
    -> Rate oder None (keine Loesung / keine Einzahlung)."""
    fluss = [(pd.Timestamp(d).normalize(), float(b)) for d, b in zahlungen or [] if b]
    if not fluss or sum(b for _, b in fluss if b > 0) <= 0 or endwert is None or endwert < 0:
        return None
    t_end = pd.Timestamp(heute).normalize()
    jahre = [max((t_end - d).days, 0) / 365.25 for d, _ in fluss]

    def wert_am_ende(r):          # Endwert der Zahlungen bei Rate r minus tatsaechlicher Endwert
        return sum(b * (1 + r) ** j for (_, b), j in zip(fluss, jahre)) - endwert

    lo, hi = -0.9999, 10.0
    if wert_am_ende(lo) > 0 or wert_am_ende(hi) < 0:
        return None
    for _ in range(200):
        mitte = (lo + hi) / 2
        if wert_am_ende(mitte) > 0:
            hi = mitte
        else:
            lo = mitte
    return (lo + hi) / 2 * 100


def rendite_pa_seit_kauf(einstand, ergebnis_wert, kaufdatum, heute, zahlungen=None, depotwert=None):
    """Ø-Rendite p.a. seit Kauf fuer Kachel UND Vergleichstabelle (Audit A-08, eine Quelle).
    ergebnis_wert = Depotwert + bereits ausgezahlte Entnahmen. Ab 1 Jahr jaehrlich, darunter
    ab 30 Tagen aus der Ø-Monatsrendite hochgerechnet (Nutzerentscheid DEP-08), sonst None.
    Mit zahlungen (Sparraten/Entnahmen mit Datum, siehe rendite_pa_geldgewichtet) und depotwert:
    geldgewichtet (XIRR) - sonst wuerde jede Sparrate so gerechnet, als laege sie seit dem Kauf im
    Depot, und die Rendite fiele viel zu niedrig aus (360°-Pruefung F-01).
    -> (rate_pa | None, hochgerechnet: bool)"""
    if not einstand or einstand <= 0 or ergebnis_wert is None or ergebnis_wert <= 0:
        return None, False
    if zahlungen and depotwert is not None:
        erste = min(pd.Timestamp(d) for d, _ in zahlungen).date()
        tage = (heute - erste).days
        if tage < 30:
            return None, False
        r = rendite_pa_geldgewichtet(zahlungen, depotwert, heute)
        return (r, tage < 365) if r is not None else (None, False)
    _, monatlich, jaehrlich, _ = berechne_performance_kennzahlen(einstand, ergebnis_wert, kaufdatum, heute)
    if jaehrlich is not None:
        return jaehrlich, False
    if monatlich is not None:
        return ((1 + monatlich / 100) ** 12 - 1) * 100, True
    return None, False


def berechne_reale_stueckzahl(df, start_stueckzahl, entnahme_pm, termine, spread_pct):
    """REAL: zu jedem Entnahmetermin werden tatsaechlich Anteile zum Geldkurs (Mid minus
    Spread) verkauft - am ersten Handelstag am/nach dem Termin. Gleicher Plan und gleiche
    Rate wie die Netto-Simulation (Audit DEP-03). -> Stueckzahl je Zeile von df."""
    stueckzahl = start_stueckzahl
    offen = sorted(pd.Timestamp(t) for t in termine)
    i = 0
    verlauf = []
    for ts, row in df.iterrows():
        tag = pd.Timestamp(ts).normalize()
        while i < len(offen) and offen[i] <= tag:
            geld_preis = float(row["Close"]) * (1 - spread_pct / 100.0)
            if entnahme_pm and geld_preis > 0:
                stueckzahl = max(0.0, stueckzahl - entnahme_pm / geld_preis)
            i += 1
        verlauf.append(stueckzahl)
    return verlauf


def berechne_performance_kennzahlen(erste_werte, letzter_wert, start_datum, end_datum):
    """Gesamt-%, Ø-monatliche % und Ø-jährliche % sowie Gewinn/Verlust in €.
    Keine Hochrechnung kurzer Zeitraeume (Audit DEP-08): Ø/Jahr erst ab 365 Tagen,
    Ø/Monat erst ab 30 Tagen - sonst None ('n. a.', angezeigt wird die Gesamtrendite)."""
    if not erste_werte or erste_werte <= 0:
        return None, None, None, letzter_wert - (erste_werte or 0.0)
    gesamt_pct = (letzter_wert / erste_werte - 1) * 100
    tage = max(1, (end_datum - start_datum).days)
    monate = tage / 30.44
    monatliche_pct = (((letzter_wert / erste_werte) ** (1 / monate)) - 1) * 100 if tage >= 30 else None
    jaehrliche_pct = (((letzter_wert / erste_werte) ** (365.25 / tage)) - 1) * 100 if tage >= 365 else None
    gewinn_verlust_euro = letzter_wert - erste_werte
    return gesamt_pct, monatliche_pct, jaehrliche_pct, gewinn_verlust_euro


def perf_sortierwert(e):
    """Sortierung der Vergleichstabellen: erst Eintraege mit Ø/Jahr (danach), sonst Gesamt."""
    j = e.get("_jaehrlich")
    return (1, j) if j is not None else (0, e.get("_perf") or 0.0)


def realisierte_rendite_pa(kurs, kaufkurs, tage, min_tage=180):
    """Realisierte Rendite p.a. seit Kauf - nur ab min_tage (Audit DEP-08), sonst None."""
    if not kaufkurs or kaufkurs <= 0 or not kurs or kurs <= 0 or tage < min_tage:
        return None
    return ((kurs / kaufkurs) ** (365.25 / tage) - 1) * 100


def gesamt_perioden_berechnen(beitraege, labels):
    """Depot-Gesamtsumme je Zeitraum (Audit DEP-07). beitraege: [(aktueller_wert,
    {label: betrag})] je Position. Basis je Zeitraum = nur die Positionen, die fuer
    diesen Zeitraum einen Wert liefern. -> [(label, betrag, pct, teilweise)]"""
    erg = []
    for lbl in labels:
        mit = [(w, z[lbl]) for w, z in beitraege if lbl in z]
        if not mit:
            continue
        betrag = sum(b for _, b in mit)
        basis = sum(w for w, _ in mit) - betrag
        pct = (betrag / basis * 100) if basis else 0.0
        erg.append((lbl, betrag, pct, len(mit) < len(beitraege)))
    return erg


# --- DEPOT-KACHELN (UX 10/2026) ---
# Oben steht, was zaehlt: Wert und Gewinn/Verlust seit Kauf (EUR und %). Darunter vier Kennzahl-Kacheln
# Tag / Woche / Monat / Jahr, die uebrigen Zeitraeume (3/6/9 Monate, lfd. Jahr, Vortag, Hoechststand) sind
# aufklappbar. Gewinn/Verlust nie nur ueber Farbe: immer Pfeil UND Vorzeichen.
KERN_ZEITRAEUME = ("Tag", "Woche", "Monat", "Jahr")
ALLE_ZEITRAEUME = ("Tag", "Woche", "Monat", "3 Monate", "6 Monate", "9 Monate", "Lfd. Jahr", "Jahr")


def zeitraeume_teilen(zeilen):
    """[(label, betrag, pct)] -> (kern, rest). Kern: Tag, Woche, Monat, Jahr - fehlt das Jahr, vertritt es
    die Zeile "seit TT.MM.JJJJ" (junge Produkte). "seit Kauf" steht in der Kopfzeile der Kachel."""
    kern, rest = [], []
    for z in zeilen:
        lbl = z[0].rstrip("*")
        if lbl == "seit Kauf":
            continue
        (kern if lbl in KERN_ZEITRAEUME or lbl.startswith("seit ") else rest).append(z)
    return kern, rest


def _richtung_html(betrag, nk):
    r = FMT.richtung(betrag, nk)
    return {"up": "up", "down": "down"}.get(r, "flat"), FMT.PFEIL[r]


def gv_zeile_html(betrag, pct, text="seit Kauf", nk=2):
    """Gewinn/Verlust-Zeile unter dem Wert: '▲ +21.592,90 € · +49,07 % seit Kauf'."""
    klasse, pfeil = _richtung_html(betrag, nk)
    return (f'<div class="gv {klasse}"><span class="gv-pfeil" aria-hidden="true">{pfeil}</span>'
            f'<span class="gv-eur">{FMT.eur(betrag, nk, vz=True)}</span>'
            f'<span class="gv-pct">{FMT.pct(pct, 2, vz=True)}</span>'
            f'<span class="gv-text">{html.escape(text)}</span></div>')


def kennzahl_kacheln_html(zeilen, nk=2):
    """Kennzahl-Kacheln je Zeitraum: Beschriftung, Betrag mit Pfeil, Prozent. Das Raster richtet sich nach
    der Kachelbreite (2 je Zeile, ab ~520 px Kachelbreite 4) - per Container-Abfrage, siehe ui_stil."""
    if not zeilen:
        return ""
    teile = []
    for label, betrag, pct in zeilen:
        klasse, pfeil = _richtung_html(betrag, nk)
        teile.append(f'<div class="kz {klasse}"><div class="kz-l">{html.escape(label)}</div>'
                     f'<div class="kz-e"><span aria-hidden="true">{pfeil}</span> <span class="kz-n">{FMT.eur(betrag, nk, vz=True)}</span></div>'
                     f'<div class="kz-p">{FMT.pct(pct, 2, vz=True)}</div></div>')
    return f'<div class="kz-grid">{"".join(teile)}</div>'


def zeitraum_zeilen_html(zeilen, nk=2, kopfzeile=None, fusszeile=""):
    """Weitere Zeitraeume als ruhige Zeilen (Beschriftung | Betrag | Prozent). kopfzeile: neutrale
    Referenzzeile (label, wert_html), z. B. der Vortageskurs; fusszeile: fertiges Zeilen-HTML."""
    h = ""
    if kopfzeile:
        h += (f'<div class="perf-row"><span class="perf-label">{html.escape(kopfzeile[0])}</span>'
              f'<span class="perf-vals"><span class="neutral">{kopfzeile[1]}</span></span></div>')
    for label, betrag, pct in zeilen:
        klasse, pfeil = _richtung_html(betrag, nk)
        h += (f'<div class="perf-row"><span class="perf-label">{html.escape(label)}</span>'
              f'<span class="perf-vals"><span class="{klasse}">{pfeil} {FMT.eur(betrag, nk, vz=True)}</span>'
              f'<span class="{klasse}">{FMT.pct(pct, 2, vz=True)}</span></span></div>')
    h += fusszeile
    return f'<div class="perf-table">{h}</div>' if h else ""


def depot_kachel_html(titel, wert, chips="", gv=None, zeilen=(), nk=2, kopfzeile=None, fusszeile="",
                      fussnote="", klasse="hero", wert_klasse="hero-val", titel_klasse="hero-label"):
    """Eine Kachel fuer Depot, Position oder Kurs.
    wert: fertiger Text (z. B. FMT.eur(...)); gv: (betrag, pct[, text]) fuer die Gewinn/Verlust-Zeile;
    zeilen: [(label, betrag, pct)] - Tag/Woche/Monat/Jahr als Kacheln, der Rest aufklappbar."""
    kern, rest = zeitraeume_teilen(zeilen)
    mehr = zeitraum_zeilen_html(rest, nk, kopfzeile, fusszeile)
    anzahl = len(rest) + (1 if kopfzeile else 0) + (1 if fusszeile else 0)
    return (f'<div class="{klasse}">'
            f'<div class="{titel_klasse}">{titel}</div>'
            f'<div class="price-line"><span class="{wert_klasse}">{wert}</span>{chips}</div>'
            + (gv_zeile_html(*gv, nk=nk) if gv else "")
            + kennzahl_kacheln_html(kern, nk)
            + (f'<details class="mehr"><summary>Weitere Zeiträume ({anzahl})</summary>{mehr}</details>'
               if mehr else "")
            + (f'<div class="card-footnote">{fussnote}</div>' if fussnote else "")
            + '</div>')


def badge_html(text, betrag, pct, nk=2):
    """Performance-Badge (gruen/rot) fuer den Hero: '▲ Heute +2.111,28 € · +3,38 %' - nie nur Farbe."""
    klasse, pfeil = _richtung_html(betrag, nk)
    return (f'<span class="hero-badge {klasse}"><span aria-hidden="true">{pfeil}</span>'
            f'<span class="hb-t">{html.escape(text)}</span>'
            f'<span class="hb-z">{FMT.eur(betrag, nk, vz=True)} · {FMT.pct(pct, 2, vz=True)}</span></span>')


def depot_hero_html(wert, chips="", gesamt=None, tag=None, mehr="", anzahl_mehr=0, fussnote=""):
    """Hero oben im Depot: Depotwert gross, Tages- und Gesamtperformance als Badges. Die uebrigen
    Zeitraeume (Woche/Monat/Jahr) folgen darunter als st.metric-Karten, der Rest ist aufklappbar."""
    badges = "".join(b for b in (badge_html("Heute", *tag) if tag else "",
                                 badge_html("Gesamt", *gesamt) if gesamt else "") if b)
    return ('<div class="hero depot-hero">'
            '<div class="hero-label">Depotwert</div>'
            f'<div class="price-line"><span class="hero-val depot-wert">{wert}</span>{chips}</div>'
            + (f'<div class="hero-badges">{badges}</div>' if badges else "")
            + (f'<details class="mehr"><summary>Weitere Zeiträume ({anzahl_mehr})</summary>{mehr}</details>'
               if mehr else "")
            + (f'<div class="card-footnote">{fussnote}</div>' if fussnote else "")
            + '</div>')


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


def haenge_live_punkt_an(df, heute, kurs):
    """Live-Kurs als Punkt fuer HEUTE (Audit DEP-10): gibt es die Zeile schon, wird sie
    aktualisiert, sonst wird der Index um heute verlaengert - statt den gestrigen
    Schlusskurs zu ueberschreiben. Gleiches Vorgehen wie bei den Vergleichswerten."""
    if df is None or df.empty or not kurs:
        return df
    heute_ts = pd.Timestamp(heute).normalize()
    letzter = pd.Timestamp(df.index[-1]).normalize()
    if letzter > heute_ts:
        return df
    df = df.copy()
    if letzter == heute_ts:
        ts = df.index[-1]
        df.loc[ts, "Close"] = kurs
        if "High" in df.columns:
            df.loc[ts, "High"] = max(float(df.loc[ts, "High"]), kurs)
        if "Low" in df.columns:
            df.loc[ts, "Low"] = min(float(df.loc[ts, "Low"]), kurs)
    else:
        df.loc[heute_ts] = [kurs] * len(df.columns)
        df = df.sort_index()
    return df


def _berlin_tage(ts_ms):
    """ls-tc-Zeitstempel (ms, UTC) -> Kalendertag in Europe/Berlin als naive Mitternacht
    (Audit DEP-09) - wie der Workflow; passt so auf bdate_range-Indizes."""
    s = pd.to_datetime(pd.Series(ts_ms), unit="ms", utc=True)
    return s.dt.tz_convert("Europe/Berlin").dt.normalize().dt.tz_localize(None)

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
    return geschrieben, erg.get("alt"), erg.get("neu")


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

    ok, _ = gh_aktualisiere(upfad(PROG_BASIS.PFAD), _a, default=None, message=message)
    return bool(ok and erg.get("neu") is not None)


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
    teile = [gh_read_taeglich(f"state/planer/katalog_gross_{i}.json", {}) or {} for i in range(4)]
    ids = scanner.top500_ids(gh_read_taeglich("state/top50_ids.json", {}) or {},
                             gh_read_taeglich("state/top50_wikifolios.json", {}) or {})
    werte = PROG_BASIS.top500_optionen(teile, ids)
    st.session_state["_prog_top500"] = (heute, werte)
    return werte


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


def referenzkurs_vor_tagen(historie, tage, heute):
    # Hinweis: der AKTUELLE Wert kommt immer live von get_live_kurs() herein,
    # hier wird ausschliesslich der historische Referenzpunkt gesucht.
    """Letzter Schlusskurs am oder vor dem Stichtag (heute - tage). Nimmt
    bewusst den naechstfrueheren Handelstag, wenn der Stichtag auf ein
    Wochenende/Feiertag faellt. None, wenn die Historie nicht weit genug
    zurueckreicht - dann entfaellt die Zeile in der Anzeige."""
    if historie is None or historie.empty:
        return None
    stichtag = pd.Timestamp(heute) - pd.Timedelta(days=tage)
    passend = historie[historie.index <= stichtag]
    if passend.empty:
        return None
    # Nur nutzen, wenn die Historie wirklich bis in die Naehe des Stichtags
    # reicht (sonst waere "1 Jahr" bei 3 Monaten Historie schlicht falsch).
    if (stichtag - passend.index[-1]).days > 10:
        return None
    return float(passend.iloc[-1])


def berechne_zeitraeume(aktueller_kurs, vortag_kurs, historie, heute):
    """Liefert [(Label, Kursdifferenz, Prozent), ...] fuer Tag/Woche/Monat/Jahr.

    Reicht die Historie fuer einen Zeitraum nicht aus, wird die Zeile
    weggelassen - AUSSER beim Jahr: dort wird ersatzweise der aelteste
    verfuegbare Kurs herangezogen und das Label entsprechend umbenannt
    ("seit 28.01.2026"). So bleibt bei jung aufgelegten Produkten die
    Langfrist-Zeile sichtbar, ohne einen Jahreswert vorzutaeuschen, den
    die Daten gar nicht hergeben."""
    zeilen = []
    if vortag_kurs:
        d = aktueller_kurs - vortag_kurs
        zeilen.append(("Tag", d, d / vortag_kurs * 100))

    for label, tage in [("Woche", 7), ("Monat", 30), ("3 Monate", 91),
                        ("6 Monate", 182), ("9 Monate", 273)]:
        ref = referenzkurs_vor_tagen(historie, tage, heute)
        if ref:
            d = aktueller_kurs - ref
            zeilen.append((label, d, d / ref * 100))

    # Laufendes Jahr (YTD) - bewusst nach den festen Zeitraeumen, da es je nach
    # Kalenderlage kuerzer oder laenger als 6 Monate sein kann.
    jahresanfang = datetime.date(heute.year, 1, 1)
    if historie is not None and not historie.empty:
        vor_jahresstart = historie[historie.index <= pd.Timestamp(jahresanfang)]
        if not vor_jahresstart.empty:
            ytd_ref = float(vor_jahresstart.iloc[-1])
            if ytd_ref:
                d = aktueller_kurs - ytd_ref
                zeilen.append(("Lfd. Jahr", d, d / ytd_ref * 100))

    jahr_ref = referenzkurs_vor_tagen(historie, 365, heute)
    if jahr_ref:
        d = aktueller_kurs - jahr_ref
        zeilen.append(("Jahr", d, d / jahr_ref * 100))
    elif historie is not None and not historie.empty:
        # Kein Jahreswert vorhanden - aeltesten Kurs nehmen und ehrlich
        # beschriften. Nur sinnvoll, wenn dieser Zeitraum laenger ist als der
        # bereits gezeigte Monat, sonst waere es eine Dopplung.
        aeltester_ts = historie.index[0]
        if (pd.Timestamp(heute) - aeltester_ts).days > 182:
            ref = float(historie.iloc[0])
            if ref:
                d = aktueller_kurs - ref
                zeilen.append((f"seit {aeltester_ts.strftime('%d.%m.%Y')}", d, d / ref * 100))
    return zeilen


def mc_einsatz(startwert, tage, sparrate_monat=0.0, entnahme_monat=0.0):
    """Eingesetztes Geld in der Simulation: Startwert + Zahlungen an jedem 21. Handelstag
    (genau wie in simuliere_bandbreite) - Bezugsgroesse der Verlustwahrscheinlichkeit."""
    monate = int(tage) // 21
    return float(startwert) + monate * (float(sparrate_monat or 0) - float(entnahme_monat or 0))


def simuliere_bandbreite(startwert, kursreihe, jahre, sparrate_monat=0.0,
                         entnahme_monat=0.0, shrinkage=True, pfade=4000):
    """Monte-Carlo-Simulation moeglicher Wertentwicklungen statt einer
    einzelnen Punktprognose.

    Warum ueberhaupt: Eine einzelne Zahl ("in 5 Jahren sind es X €")
    suggeriert eine Praezision, die es nicht gibt. Bei kurzer Historie ist
    der Standardfehler einer annualisierten Rendite riesig - bei ~7 Monaten
    Daten und hoher Volatilitaet liegt er schnell bei +/- 60 Prozentpunkten.
    Eine Bandbreite ist ehrlicher als eine Kommastelle.

    Methode: Aus den taeglichen Log-Renditen der echten Kursreihe werden
    Drift (mu) und Volatilitaet (sigma) geschaetzt, dann werden `pfade`
    moegliche Verlaeufe gewuerfelt (geometrische Brownsche Bewegung).

    shrinkage: Bei kurzer Historie ist der geschaetzte Drift extrem
    unzuverlaessig - ein siebenmonatiger Boom wuerde sonst ungebremst ueber
    Jahre fortgeschrieben (die naive Rechnung ergab dann z.B. 0% Verlust-
    wahrscheinlichkeit, was offensichtlich unrealistisch ist). Deshalb wird
    der Drift Richtung eines konservativen Ankers (8% p.a., grobe langfristige
    Aktienmarktrendite) zusammengezogen. Das Gewicht haengt an der Datenmenge:
    wenig Historie -> mehr Anker, viel Historie -> mehr eigene Daten.

    Gibt (perzentile_dict, kennzahlen_dict) zurueck oder (None, None), wenn
    die Kursreihe zu duenn fuer eine sinnvolle Schaetzung ist.
    """
    import numpy as np

    if kursreihe is None or len(kursreihe) < 30:
        return None, None

    reihe = kursreihe.dropna()
    reihe = reihe[reihe > 0]
    if len(reihe) < 30:
        return None, None

    log_renditen = np.diff(np.log(reihe.values))
    if len(log_renditen) < 20:
        return None, None

    mu_tag = float(np.mean(log_renditen))
    sigma_tag = float(np.std(log_renditen, ddof=1))
    if sigma_tag <= 0:
        return None, None

    jahre_historie = len(log_renditen) / 252.0
    mu_roh_pa = (np.exp(mu_tag * 252) - 1) * 100

    if shrinkage:
        ANKER_PA = 0.08          # grobe langfristige Marktrendite als Rueckfallanker
        HALBES_VERTRAUEN = 3.0   # ab 3 Jahren Historie: 50% Gewicht auf eigene Daten
        mu_anker_tag = np.log(1 + ANKER_PA) / 252
        gewicht = jahre_historie / (jahre_historie + HALBES_VERTRAUEN)
        mu_verwendet = gewicht * mu_tag + (1 - gewicht) * mu_anker_tag
    else:
        gewicht = 1.0
        mu_verwendet = mu_tag

    tage = max(1, int(jahre * 252))
    rng = np.random.default_rng(12345)   # fester Seed: gleiche Eingabe -> gleiches Bild
    z = rng.standard_normal((pfade, tage))
    # Audit DEP-05: mu_tag ist bereits der Mittelwert der LOG-Renditen (enthaelt -sigma^2/2),
    # der Anker ln(1,08)/252 ebenfalls eine Log-Rate - KEIN zweiter Abzug. Median der
    # Endwerte (ohne Ein-/Auszahlungen) = startwert * exp(mu_verwendet * tage).
    schritte = mu_verwendet + sigma_tag * z

    # Sparrate/Entnahme monatlich einrechnen: Pfade schrittweise aufbauen,
    # damit Ein-/Auszahlungen zum jeweils simulierten Kurs wirken.
    if sparrate_monat or entnahme_monat:
        werte = np.full(pfade, float(startwert))
        netto_monat = sparrate_monat - entnahme_monat
        for t in range(tage):
            werte = werte * np.exp(schritte[:, t])
            if (t + 1) % 21 == 0:          # ~1 Handelsmonat
                werte = np.maximum(0.0, werte + netto_monat)
        endwerte = werte
    else:
        endwerte = startwert * np.exp(schritte.sum(axis=1))

    perzentile = {p: float(np.percentile(endwerte, p)) for p in (5, 25, 50, 75, 95)}
    # Audit DEP-06: Verlust = Endwert unter dem insgesamt eingesetzten Geld
    # (Startwert + Einzahlungen - Entnahmen), nicht nur unter dem Startwert.
    eingesetzt = mc_einsatz(startwert, tage, sparrate_monat, entnahme_monat)
    kennzahlen = {
        "verlust_wahrscheinlichkeit": float((endwerte < eingesetzt).mean() * 100),
        "eingesetzt": float(eingesetzt),
        "vola_pa": float(sigma_tag * np.sqrt(252) * 100),
        "mu_roh_pa": float(mu_roh_pa),
        "mu_verwendet_pa": float((np.exp(mu_verwendet * 252) - 1) * 100),
        "jahre_historie": float(jahre_historie),
        "gewicht_eigene_daten": float(gewicht * 100),
        "pfade": pfade,
    }
    return perzentile, kennzahlen


def berechne_robuste_cagr(aktueller_kurs, historie, heute, daempfung=False,
                          auflage_datum=None, auflage_kurs=None):
    """Schaetzt eine annualisierte Wachstumsrate (CAGR), die ueber den Tag
    KONSTANT bleibt und nicht an einem einzelnen Kurspunkt haengt.

    Warum nicht einfach "aeltester Kurs vs. heute": beide Endpunkte sind
    Zufallspunkte. Und Achtung - der Mittelwert der taeglichen Log-Renditen
    ist KEINE Verbesserung: er teleskopiert sich exakt zu demselben
    Zwei-Punkte-Vergleich. Deshalb hier:

    1. TREND PER REGRESSION (Hauptwert): Kleinste-Quadrate-Gerade durch
       ln(Kurs) ueber die Zeit. Nutzt JEDEN Kurspunkt der Historie, nicht nur
       Anfang und Ende - ein einzelner Ausreisser am Rand verschiebt sie kaum.
    2. LANGE ZEITFENSTER als Quervergleich (ab 6 Monaten). Fenster unter 6
       Monaten werden bewusst NICHT verwendet: ein Monat hochgerechnet
       multipliziert das Zufallsrauschen mit 12 und ergibt Fantasiewerte
       (getestet: +1.480 % p.a. bei einem Produkt, das real ~150 % lief).
    3. MEDIAN aus Regression + Fenstern - unempfindlich gegen einen einzelnen
       Ausreisser darin.
    4. DAEMPFUNG bei kurzer Historie: aus 7 Monaten laesst sich keine
       Jahresrate ablesen (Standardfehler ueber 60 Prozentpunkte). Das
       Ergebnis wird deshalb Richtung einer konservativen Marktrendite
       (8 % p.a.) gezogen, gewichtet nach Datenmenge - dieselbe Regel wie in
       der Bandbreiten-Simulation. Ueber `daempfung=False` abschaltbar.

    Als "heutiger" Kurs dient bewusst der letzte SCHLUSSKURS der Historie,
    nicht der Live-Tick: sonst aenderte sich die Vorgabe mit jedem
    Kurs-Update um mehrere Prozentpunkte (getestet: +-2 % Kursbewegung
    verschob die Rate um +-5 Prozentpunkte).

    Gibt (cagr, details) zurueck; details ist eine Liste (Label, Wert) fuer
    die Transparenz-Anzeige. Reicht die Historie nicht (unter ~90
    Handelstagen), kommt (None, []) zurueck.
    """
    import numpy as np

    if historie is None or len(historie) < 90:
        return None, []
    reihe = historie.dropna()
    reihe = reihe[reihe > 0]
    if len(reihe) < 90:
        return None, []

    schlusskurs = float(reihe.iloc[-1])
    jahre_hist = max(1e-6, (reihe.index[-1] - reihe.index[0]).days / 365.25)

    # 1) Trend per Regression auf ln(Kurs)
    t = np.array([(ts - reihe.index[0]).days for ts in reihe.index], dtype=float) / 365.25
    y = np.log(reihe.values.astype(float))
    steigung = float(np.polyfit(t, y, 1)[0])          # ln-Einheiten pro Jahr
    cagr_trend = (float(np.exp(steigung)) - 1) * 100
    details = [(f"Trend über {jahre_hist:.1f} Jahre (Regression)", cagr_trend)]

    # 2) Lange Zeitfenster als Quervergleich
    for label, tage in [("6 Monate", 182), ("9 Monate", 273), ("1 Jahr", 365),
                        ("2 Jahre", 730), ("3 Jahre", 1095), ("5 Jahre", 1826)]:
        ref = referenzkurs_vor_tagen(reihe, tage, heute)
        if ref and ref > 0:
            details.append((label, ((schlusskurs / ref) ** (365.25 / tage) - 1) * 100))

    # SEIT BEGINN DER DATEN: gesamte Entwicklung vom ersten verfuegbaren Kurs.
    start_kurs = float(reihe.iloc[0])
    if start_kurs > 0 and jahre_hist >= 0.5:
        details.append((
            f"Seit Datenbeginn {reihe.index[0].strftime('%d.%m.%Y')} "
            f"({start_kurs:.2f} € → {schlusskurs:.2f} €)",
            ((schlusskurs / start_kurs) ** (1 / jahre_hist) - 1) * 100,
        ))

    # SEIT AUFLEGUNG: ls-tc.de liefert die Historie erst ab Listing - bei
    # LS9VFS z.B. erst ab 09.07.2025 bei 128,80 €, obwohl das Zertifikat am
    # 24.06.2025 bei 100 € startete. Dieser Teil der Entwicklung fehlt in den
    # Daten komplett. Deshalb laesst sich der Auflegungspunkt hier von Hand
    # setzen; er geht dann als eigenes Fenster in den Median ein.
    if auflage_datum is not None and auflage_kurs and auflage_kurs > 0:
        jahre_auflage = (pd.Timestamp(heute) - pd.Timestamp(auflage_datum)).days / 365.25
        if jahre_auflage >= 0.5:
            details.append((
                f"Seit Auflegung {pd.Timestamp(auflage_datum).strftime('%d.%m.%Y')} "
                f"({auflage_kurs:.2f} € → {schlusskurs:.2f} €)",
                ((schlusskurs / auflage_kurs) ** (1 / jahre_auflage) - 1) * 100,
            ))

    # 3) Median daraus
    werte = sorted(w for _, w in details)
    n = len(werte)
    roh = werte[n // 2] if n % 2 else (werte[n // 2 - 1] + werte[n // 2]) / 2

    # 4) Daempfung bei kurzer Historie (im Log-Raum, damit aus zwei
    #    Wachstumsraten wieder eine saubere Wachstumsrate wird)
    ergebnis = roh
    if daempfung:
        ANKER_PA = 8.0
        HALBES_VERTRAUEN = 3.0
        gewicht = jahre_hist / (jahre_hist + HALBES_VERTRAUEN)
        log_roh = np.log(max(1 + roh / 100, 1e-6))
        log_anker = np.log(1 + ANKER_PA / 100)
        ergebnis = (float(np.exp(gewicht * log_roh + (1 - gewicht) * log_anker)) - 1) * 100
        details.append((f"Median der Verfahren oben", roh))
        details.append((f"Nach Dämpfung ({gewicht * 100:.0f} % eigene Daten, "
                        f"Rest Richtung {ANKER_PA:.0f} % Marktrendite)", ergebnis))

    return ergebnis, details



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
            "https://www.ls-tc.de/_rpc/json/.lstc/instrument/search/main",
            params={"q": suchbegriff.strip(), "localeId": "2"},
            headers=config.LS_TC_HEADERS, timeout=8,
        )
        r.raise_for_status()
        daten = r.json()
        # Der Endpunkt liefert je nach Aufruf ein blankes Array oder ein
        # Objekt mit "results"/"data" - beide Formen abfangen.
        if isinstance(daten, dict):
            daten = daten.get("results") or daten.get("data", {}).get("results") or []
        treffer = []
        for eintrag in daten or []:
            inst_id = eintrag.get("instrumentId") or eintrag.get("id")
            if not inst_id:
                continue
            treffer.append({
                "instrument_id": int(inst_id),
                "name": eintrag.get("displayname") or "(ohne Namen)",
                "wkn": str(eintrag.get("wkn") or ""),
                "isin": eintrag.get("isin") or "",
                "kategorie": eintrag.get("categoryName") or "",
            })
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
APP_URL = "https://zzvuvqwe6.streamlit.app"     # fuer Permanentlinks, falls die Adresse nicht ermittelbar ist
# Permanentlinks: ?ansicht=<kuerzel> oeffnet direkt die Ansicht
ANSICHT_LINKS = {"zins": ANSICHT_ZINS, "abfindung": ANSICHT_ABFINDUNG, "rente": ANSICHT_ATZ}
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
    "🏆 Watchlist Top 50": "🏆 Watchlist",
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
    "🏆 Watchlist Top 50": "🏆 Watchlist Top 500",
    ANSICHT_MUSTER: "📦 Musterdepot",
    ANSICHT_ABFINDUNG: "💶 Abfindungsrechner",
    ANSICHT_ZINS: "🧮 Zinseszinsrechner",
    ANSICHT_ATZ: "🏖️ Altersteilzeit & Rente",
    ANSICHT_BENUTZER: "👥 Benutzer",
}
# Ausfuehrlicher Titel in der Kopfleiste (dort ist mehr Platz als auf der Kachel)
NAV_TITEL = {
    ANSICHT_ANALYSE: "🧠 Depot-Analyse & Optimierung",
    ANSICHT_BEWERTUNG: "⚖️ Bewertung (Top 500)",
    ANSICHT_ATZ: "🏖️ Altersteilzeit & Rentenplanung",
    "🔍 Seit 01.01.2026": "🔍 Performance seit 01.01.2026",
    "🔎 Seit 01.01.2021": "🔎 Performance seit 01.01.2021",
}
# Menue-Gruppen (Ueberschrift, Ansichten) - je Zeile zwei Buttons
NAV_FARBEN = {}   # leer = einheitlich Neon-Weiss; je Gruppe eine Farbe moeglich, z. B. {"Depot": "#22D3EE"}
NAV_ZEILEN = [
    ("Depot", [ANSICHT_DEPOT, ANSICHT_ANALYSE, ANSICHT_ANALYSE_DEPOT, ANSICHT_MUSTER, "📝 Trader-Log (Trades & Kommentare)", ANSICHT_EINST]),
    ("Charts", ["📈 Vermögens- & Substanzaufbau", "🔍 Seit 01.01.2026", "🔎 Seit 01.01.2021",
                "🕯️ Tages-Candlestick"]),
    ("Planung & Analyse", ["🔮 Zukunfts-Prognose", "📊 Szenario-Simulator (5 Jahre)", ANSICHT_BUILDER,
                           ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2, "💼 Portfolio-Planer",
                           "🏆 Watchlist Top 50", ANSICHT_BEWERTUNG]),
    ("Rechner", [ANSICHT_ABFINDUNG, ANSICHT_ZINS, ANSICHT_ATZ]),
    ("Verwaltung", [ANSICHT_BENUTZER]),
]
# Ansichten ohne Depot-/Kursdaten: dort wird gar nichts vom Depot geladen
LEICHTE_ANSICHTEN = {ANSICHT_ANALYSE_DEPOT, "💼 Portfolio-Planer", ANSICHT_BUILDER, ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2, "🏆 Watchlist Top 50", ANSICHT_MUSTER, ANSICHT_ABFINDUNG, ANSICHT_ZINS,
                     "📝 Trader-Log (Trades & Kommentare)",
                     ANSICHT_BENUTZER, ANSICHT_BEWERTUNG, ANSICHT_ATZ}

# Ansichten mit breiten Tabellen: duerfen auf grossen Monitoren breiter werden als UI.INHALT_MAX
BREITE_ANSICHTEN = {"🏆 Watchlist Top 50", ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2, ANSICHT_BENUTZER}

# Ansichten ohne Live-Kurse (Ranglisten der Agenten, Rechner, Verwaltung) - dort keine Kursstand-Zeile
OHNE_KURSE = {"🏆 Watchlist Top 50", ANSICHT_ABFINDUNG, ANSICHT_ZINS, ANSICHT_BENUTZER,
              "📝 Trader-Log (Trades & Kommentare)", ANSICHT_SCANNER, ANSICHT_SCANNER_PRO, ANSICHT_SCANNER2,
              ANSICHT_BEWERTUNG, ANSICHT_ATZ}

NAV_CSS = UI.CSS_NAV


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


def _kurslauf_faellig(seit):
    """Ist seit dem letzten Lauf (bzw. dem Start der App) ein Termin (9, 11, 13 … 23 Uhr) vergangen?"""
    return seit < letzter_termin(datetime.datetime.now(BERLIN_TZ))


@st.cache_resource(show_spinner=False)
def kurs_dienst():
    """EIN Kursdienst je App-Prozess (fuer alle Sitzungen): haelt alle Kurse im Speicher und
    aktualisiert sie im Hintergrund nach Zeitplan - niemand wartet beim Seitenaufbau auf Neuabrufe."""
    d = KD.KursDienst({"live": _live_roh, "historie": _historie_roh, "benchmark": _benchmark_netz},
                      jetzt=lambda: datetime.datetime.now(BERLIN_TZ), nach_lauf=_nach_kurslauf)
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
        d.zeitplan_starten(lambda letzter: _kurslauf_faellig(letzter or d.gestartet))
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
    try:
        return nutzerdaten.eingaben_merken(gh_aktualisiere, st.session_state, _nutzer(), bereich, werte,
                                           sofort=sofort)
    except Exception as e:
        logging.warning(f"Eingaben '{bereich}' nicht gemerkt: {type(e).__name__}")
        return False


# Eingaben ohne eigene Datei (Zukunfts-Prognose, Simulation): Streamlit loescht Widget-Werte,
# sobald ihre Ansicht nicht gezeichnet wird. Je Sitzung gemerkt und beim naechsten Anlegen des
# Felds als Startwert eingesetzt; Knoepfe und das gespeicherte Auflegungsdatum bleiben aussen vor.
SITZUNG_EINGABEN = re.compile(r"^(prognose_rate_|prognose_wert_wahl$|mc_jahre$|mc_shrinkage$|szenario_)"
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
            nutzerdaten.eingaben_merken(gh_aktualisiere, st.session_state, _nutzer(), bereich, offen, sofort=True)
        except Exception as e:
            logging.warning(f"Offene Eingaben '{bereich}' nicht gespeichert: {type(e).__name__}")


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
    if ansicht == ANSICHT_BENUTZER:
        return bool(n) and n.get("rolle") == "admin"
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


def kursstand_text(stx, jetzt):
    """Kurzer Stand aller Kurse fuer Kopf/Startseite."""
    if stx["aeltester"] is None:
        return "Kurse werden beim ersten Aufruf geladen"
    return f"Kurse vom <b>{_zeit_kurz(stx['aeltester'], jetzt)}&nbsp;Uhr</b>"


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
    balken = st.progress(0.0)
    t0 = time.monotonic()
    while d.laeuft() and time.monotonic() - t0 < KURSLAUF_WARTEN_MAX_SEK:
        x = d.status()
        balken.progress(x["fertig"] / x["gesamt"] if x["gesamt"] else 0.0,
                        text=f"⏳ Kurse werden geladen … {x['fertig']} von {x['gesamt']}")
        time.sleep(0.5)
    st.session_state.pop("_kurslauf_warten", None)
    st.rerun()


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
    stand_html = (f'<div class="nav-stand"><span><i></i>{kursstand_text(stx, jetzt)} · '
                  f'nächste {naechster_termin(jetzt).strftime("%H:%M")}&nbsp;Uhr</span></div>')
    hilfe = ("Die Kurse werden gerade im Hintergrund geladen – der Knopf ist bis zum Ende gesperrt." if laeuft else
             f"Alle Kurse jetzt im Hintergrund neu laden (sonst automatisch täglich ab {AKTUALISIERUNG_START} Uhr "
             f"alle {AKTUALISIERUNG_TAKT} Stunden)")

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
                '<div class="nav-credit">created by MarsTech</div>'
                f'<div class="nav-chip"><span class="nav-dot"></span><span>{kursstand_text(stx, jetzt)}'
                f' · nächste {naechster_termin(jetzt).strftime("%H:%M")}&nbsp;Uhr</span></div></div>',
                unsafe_allow_html=True)
            st.button("⏳ Kurse werden geladen …" if laeuft else "🔄 Kurse aktualisieren", key="nav_refresh",
                      width="content", help=hilfe, on_click=_nav_aktualisieren, disabled=laeuft)
            _kurslauf_fortschritt(stx)
            depot_kurzinfo_karte(jetzt)
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
            try:
                hat_muster = bool((gh_read_cached(upfad(PFAD_MUSTERDEPOT), {}) or {}).get("depots"))
            except Exception:
                hat_muster = False
            for titel, ansichten in NAV_ZEILEN:
                ansichten = [a for a in ansichten if (a != ANSICHT_MUSTER or hat_muster) and _sichtbar(a)]
                if not ansichten:
                    continue
                farbe = NAV_FARBEN.get(titel, "#F4F8FF")
                verzug = f"{[t for t, _ in NAV_ZEILEN].index(titel) * 0.25 + 0.3:.2f}s"
                st.markdown(f'<div class="nav-gruppe"><span class="nav-wander" style="--verzug:{verzug}">'
                            f'{titel}</span></div>', unsafe_allow_html=True)
                # alle Kacheln der Gruppe in EINER Zeile - das CSS bricht je nach Breite um
                # (Handy 2, Tablet 3, Desktop 4, breite Monitore 5 nebeneinander)
                spalten = st.columns(len(ansichten))
                for spalte, ansicht in zip(spalten, ansichten):
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
                    col1, col2 = st.columns([2, 3])
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
        """-> (text, art) - ▲ 3 / ▼ 2 / o / NEU; ab Platz 51 kein Vergleich ("·")"""
        if jetzt > TREND_BIS:
            return "·", "gleich"
        if vor is None:
            return "NEU", "neu"
        d = vor - jetzt
        if d > 0:
            return f"▲ {d}", "up"
        if d < 0:
            return f"▼ {-d}", "down"
        return "o", "gleich"

    def _seit_text(seit):
        try:
            d = datetime.date.fromisoformat(seit)
        except Exception:
            return None
        tage = (datetime.date.today() - d).days
        text = f"Vergleich mit dem Stand vom {d.strftime('%d.%m.%Y')}"
        if tage < 7:
            text += f" (erst {tage} Tag{'e' if tage != 1 else ''} Verlauf – volle Woche folgt)"
        return text

    def _wochen_bilanz(eintraege, raus, seit):
        """eintraege: [(platz, name, kennung, vor)], raus: [{"name","vor","jetzt"}]"""
        seit_txt = _seit_text(seit)
        if not seit_txt:
            st.caption("Wochenvergleich: startet mit dem nächsten Lauf (es gibt noch keinen früheren Stand).")
            return
        eintraege = [e for e in eintraege if e[0] <= TREND_BIS]
        neu = [(p, n, k) for p, n, k, v in eintraege if v is None]
        bewegt = [(v - p, p, n, k) for p, n, k, v in eintraege if v is not None and v != p]
        auf = sorted([b for b in bewegt if b[0] > 0], reverse=True)[:5]
        ab = sorted([b for b in bewegt if b[0] < 0])[:5]

        def tabelle(kopf, zeilen):
            if not zeilen:
                return '<div class="pt-leer">– keine –</div>'
            k = "".join(f'<th class="{"pt-wert" if i == 0 else "pt-num"}">{h}</th>' for i, h in enumerate(kopf))
            z = "".join("<tr>" + "".join(zeilen_i) + "</tr>" for zeilen_i in zeilen)
            return f'<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt"><thead><tr>{k}</tr></thead><tbody>{z}</tbody></table></div>'

        def zelle(text, farbe=None, wert=False):
            # white-space normal: laengere Texte ("→ Beobachten") duerfen auf
            # dem iPhone umbrechen, statt die Tabelle zu verbreitern
            stil = f' style="color:{farbe};white-space:normal"' if farbe else ""
            return f'<td class="{"pt-wert" if wert else "pt-num"}"{stil}>{html.escape(str(text))}</td>'

        with st.expander(f"📅 Wochenveränderung: {len(neu)} neu · {len(raus)} rausgeflogen · "
                         f"{len(bewegt)} verschoben", expanded=True):
            st.caption(seit_txt)
            st.markdown(f"**🆕 Neu in der Liste ({len(neu)})**", unsafe_allow_html=True)
            st.markdown(tabelle(["Wert", "Platz"], [[zelle(n, wert=True), zelle(p, TREND_FARBE["neu"])]
                                                  for p, n, k in neu]), unsafe_allow_html=True)
            st.markdown(f"**❌ Rausgeflogen ({len(raus)})**", unsafe_allow_html=True)
            st.markdown(tabelle(["Wert", "vorher", "jetzt"], [
                [zelle(r["name"], wert=True), zelle(r["vor"]),
                 zelle(r["jetzt"] if r.get("jetzt") else
                       f"→ {Q_KLASSEN_KURZ.get(r['klasse'], r['klasse'])}" if r.get("klasse") else
                       "nicht bewertet" if r.get("grund") else "ohne Daten", TREND_FARBE["down"])]
                for r in sorted(raus, key=lambda r: r["vor"])]), unsafe_allow_html=True)
            st.markdown("**🚀 Größte Aufsteiger**", unsafe_allow_html=True)
            st.markdown(tabelle(["Wert", "Platz", "Veränderung"], [
                [zelle(n, wert=True), zelle(p), zelle(f"▲ {d}", TREND_FARBE["up"])] for d, p, n, k in auf]),
                unsafe_allow_html=True)
            st.markdown("**📉 Größte Absteiger**", unsafe_allow_html=True)
            st.markdown(tabelle(["Wert", "Platz", "Veränderung"], [
                [zelle(n, wert=True), zelle(p), zelle(f"▼ {-d}", TREND_FARBE["down"])] for d, p, n, k in ab]),
                unsafe_allow_html=True)

    # ---------- INDEX-FILTER (gemeinsam fuer alle Listen) ----------
    # Die Agenten schreiben die Daten ALLER Aktien in Teildateien plus die
    # Indexmitglieder; die App bildet daraus die Rangliste des gewaehlten
    # Index mit derselben Sortierung wie der Agent. Pfeile/Neu/Raus kommen
    # aus dem Wochenvergleich, den die Agenten je Index-Rangliste fuehren.
    @st.cache_data(ttl=900, show_spinner=False)
    def _lade_teile(muster, anzahl):
        zeilen, felder, stand = [], None, None
        for i in range(anzahl):
            # streng: ein Lesefehler wirft und landet so NICHT 15 Min. im Cache (DATA-01)
            d = gh_read_streng(muster.format(i), None) or {}
            felder = d.get("felder") or felder
            stand = d.get("stand") or stand
            zeilen += d.get("zeilen") or []
        if not felder:
            return {}, None
        return {z[0]: dict(zip(felder, z)) for z in zeilen}, stand

    def _q_alle():
        try:
            return _lade_teile("state/qualitaet/alle_{}.json", 6)
        except github_store.LeseFehler:
            return {}, None

    def _p_alle():
        try:
            return _lade_teile("state/top50_alle_{}.json", 4)
        except github_store.LeseFehler:
            return {}, None

    def _index_auswahl(prefix, indizes, regionen):
        """Region + Index als Knoepfe. indizes = {key: {"titel","region","s"}}.
        Indizes ohne zugeordnete Aktien (Quelle beim letzten Lauf nicht lesbar)
        bleiben sichtbar – mit "(–)" und dem Grund. -> index_schluessel oder None"""
        if not any(v.get("s") for v in indizes.values()):
            st.info("Die Indexzuordnung liegt noch nicht vor – sie entsteht beim nächsten Lauf der Agenten.")
            return None
        regionen = list(regionen) + sorted({v.get("region") for v in indizes.values()
                                            if v.get("region") and v.get("region") not in regionen})
        vorhanden = [r for r in regionen if any(v.get("region") == r for v in indizes.values())]
        region = st.pills("Region", vorhanden, default=vorhanden[0], key=f"{prefix}_region") or vorhanden[0]
        keys = [k for k, v in indizes.items() if v.get("region") == region]
        keys = [k for k in keys if indizes[k].get("s")] + [k for k in keys if not indizes[k].get("s")]
        titel = [f'{indizes[k]["titel"]} ({len(indizes[k]["s"])})' if indizes[k].get("s")
                 else f'{indizes[k]["titel"]} (–)' for k in keys]
        wahl = auswahl_kompakt("Index", titel, default=titel[0], key=f"{prefix}_index_{region}")
        # Die Anzahl im Namen kann sich ueber Nacht aendern - eine gespeicherte,
        # nicht mehr vorhandene Auswahl faellt dann auf den ersten Index zurueck
        key = keys[titel.index(wahl)] if wahl in titel else keys[0]
        if not indizes[key].get("s"):
            grund = indizes[key].get("hinweis") or "Quelle beim letzten Lauf nicht lesbar"
            st.info(f'Für {indizes[key]["titel"]} liegt noch keine Mitgliederliste vor ({grund}). '
                    "Der nächste Lauf der Agenten versucht es erneut.")
            return None
        return key

    LISTEN_LAENGEN = [50, 100, 250, 500]
    TREND_BIS = 50              # Wochenvergleich (Pfeile/NEU) gibt es fuer die ersten 50 Plaetze

    def _listen_laenge(prefix):
        """Wie viele Plaetze die Rangliste zeigt (Standard: Top 500)."""
        titel = [f"Top {n}" for n in LISTEN_LAENGEN]
        wahl = st.pills("Länge", titel, default="Top 500", key=f"{prefix}_laenge") or "Top 500"
        return LISTEN_LAENGEN[titel.index(wahl)] if wahl in titel else 500

    def _auswahl_art(prefix):
        return st.pills("Auswahl nach", ["Kategorie", "Index"], default="Kategorie",
                        key=f"{prefix}_auswahl_art") or "Kategorie"

    INDEX_REGIONEN_APP = ["Deutschland", "USA", "Europa", "Asien/Pazifik & Kanada", "Schwellenländer"]

    def _p_index_kat(idx_key, info, daten, laenge=50):
        """Baut aus den Gesamtdaten eine Rangliste im Format einer Kategorie
        (top/mit_daten/vergleich), damit dieselbe Anzeige genutzt werden kann."""
        alle, _ = _p_alle()
        if not alle:
            return None, None
        iv = gh_read_taeglich("state/top50_index_vergleich.json", None) or {}
        div_key = (daten.get("dividenden_zeitraum") or ["DIV"])[0]
        mitglieder = [alle[s] for s in info.get("s", []) if s in alle]
        top, mit_daten, vergleich = {}, {}, {}
        zrs = [z[0] for z in daten.get("zeitraeume") or []] + [div_key]
        for zr in zrs:
            mit = [z for z in mitglieder if z.get(zr) is not None and (zr != div_key or z[zr] > 0)]
            mit.sort(key=lambda z: (-z[zr], z["s"]))
            mit_daten[zr] = len(mit)
            v = (iv.get("listen") or {}).get(f"{idx_key}|{zr}")
            eintraege = []
            for z in mit[:laenge]:
                e = {"name": z["name"], "wkn": z["kennung"], "div": z.get(div_key),
                     "perf": z.get("1J") if zr == div_key else z[zr]}
                if v is not None:
                    e["vor"] = v["vor"].get(z["s"])
                eintraege.append(e)
            top[zr] = eintraege
            if v is not None:
                vergleich[zr] = {"raus": v["raus"]}
        kat = {"titel": info.get("titel"), "top": top, "mit_daten": mit_daten, "aktiv": len(mitglieder),
               "dividende": True, "kennung": "WKN/Symbol", "vergleich": vergleich}
        return kat, (iv.get("seit") or {}).get(info.get("region"))

    def _render_performance():
        try:
            daten = gh_read_taeglich("state/top50.json", None)
            if not daten or not daten.get("kategorien"):
                st.info(
                    "Noch keine Ranglisten vorhanden. Der Agent läuft täglich um 07:30 Uhr. "
                    "Für einen Sofortstart: auf GitHub unter **Actions → Watchlist Top 50 "
                    "(täglich) → Run workflow**."
                )
                return

            kategorien = daten["kategorien"]
            zeitraeume = daten.get("zeitraeume") or []
            stand = ranglisten_stand(daten)

            reihenfolge = daten.get("reihenfolge") or ["aktien", "dividenden", "etf", "wikifolios"]
            kat_keys = [k for k in reihenfolge if k in kategorien] + \
                       [k for k in kategorien if k not in reihenfolge]
            kat_titel = [kategorien[k]["titel"] for k in kat_keys]
            vergleich_seit = daten.get("vergleich_seit")
            if _auswahl_art("top50") == "Index":
                mitglieder_idx = (gh_read_taeglich("state/top50_indexmitglieder.json", None) or {}).get("indizes") or {}
                idx_key = _index_auswahl("top50", mitglieder_idx, INDEX_REGIONEN_APP)
                if not idx_key:
                    return
                laenge = _listen_laenge("top50")
                kat, vergleich_seit = _p_index_kat(idx_key, mitglieder_idx[idx_key], daten, laenge)
                if not kat:
                    st.info("Für diesen Index liegen noch keine Kursdaten vor – sie entstehen beim nächsten Lauf.")
                    return
            else:
                gewaehlt = auswahl_kompakt("Kategorie", kat_titel, default=kat_titel[0], key="top50_kategorie")
                kat_key = kat_keys[kat_titel.index(gewaehlt)] if gewaehlt in kat_titel else kat_keys[0]
                kat = kategorien[kat_key]
                laenge = _listen_laenge("top50")
                if laenge > TREND_BIS:
                    # Plaetze ab 51 aus der Langliste des Agenten (eine Datei je Kategorie);
                    # die ersten 50 bleiben aus top50.json (mit Wochenvergleich)
                    lang = gh_read_taeglich(f"state/top50_lang_{kat_key}.json", None) or {}
                    if lang.get("top"):
                        def _verlaengern(kurz, lang_zeilen):
                            kurz = list(kurz or [])
                            gesehen = {e.get("wkn") for e in kurz}
                            for z in lang_zeilen or []:
                                if len(kurz) >= laenge:
                                    break
                                if z[1] not in gesehen:
                                    gesehen.add(z[1])
                                    kurz.append({"name": z[0], "wkn": z[1], "perf": z[2], "div": z[3],
                                                 "rhythmus": z[4] if len(z) > 4 else None})
                            return kurz
                        kat = dict(kat, top={zr: _verlaengern(kat.get("top", {}).get(zr), lang["top"].get(zr))
                                             for zr in set(kat.get("top", {})) | set(lang["top"])})
                elif laenge < TREND_BIS:
                    kat = dict(kat, top={zr: v[:laenge] for zr, v in (kat.get("top") or {}).items()})

            # Kategorien mit Dividende bekommen zusaetzlich die Rangliste nach
            # laufender Dividendenrendite als eigene "Zeitraum"-Pille
            zr_liste = [tuple(z) for z in zeitraeume]
            div_zr = tuple(daten.get("dividenden_zeitraum") or ("DIV", "Div.-Rendite"))
            mit_div = bool(kat.get("dividende"))
            if mit_div and div_zr[0] in kat.get("top", {}):
                zr_liste.append(div_zr)
            zr_titel = [t for _, t in zr_liste]
            zr_wahl = st.pills("Zeitraum", zr_titel, default="1 Jahr" if "1 Jahr" in zr_titel else zr_titel[0],
                               key="top50_zeitraum")
            zr_key = zr_liste[zr_titel.index(zr_wahl)][0] if zr_wahl in zr_titel else zr_liste[0][0]
            nach_div = zr_key == div_zr[0]

            liste = kat.get("top", {}).get(zr_key, [])
            mit_daten = kat.get("mit_daten", {}).get(zr_key, 0)
            st.caption(
                f"Stand {stand} · {mit_daten} von {kat.get('aktiv', 0)} aktiven Werten "
                + ("zahlen eine Dividende" if nach_div else "haben Kursdaten für diesen Zeitraum")
                + f" · Top {len(liste)}"
            )
            if kat.get("veraltet_seit"):
                try:
                    alt_stand = datetime.datetime.fromisoformat(kat["veraltet_seit"]).strftime("%d.%m.%Y")
                except Exception:
                    alt_stand = kat["veraltet_seit"]
                st.warning(f"Die Kursquelle für diese Liste hat beim letzten Lauf nicht vollständig "
                           f"geantwortet - angezeigt wird der Stand vom {alt_stand}.")

            if not liste:
                st.info("Für diesen Zeitraum reicht bei keinem Wert die Kurshistorie aus.")
                return

            def _pct(wert):
                if wert is None:
                    return '<td class="pt-num">–</td>'
                farbe = "pt-up" if wert >= 0 else "pt-down"
                return f'<td class="pt-num pt-stark {farbe}">{vz_zahl(wert, 2)} %</td>'

            def _div(wert, rhythmus=None):
                if not wert:
                    return '<td class="pt-num">–</td>'
                unter = f'<span class="pt-sub">{html.escape(rhythmus)}</span>' if rhythmus else ""
                return f'<td class="pt-num pt-stark pt-up">{FMT.pct(wert, 2)}{unter}</td>'

            vergleich = (kat.get("vergleich") or {}).get(zr_key)
            mit_trend = vergleich is not None
            zeilen = ""
            for rang, e in enumerate(liste, 1):
                trend_td = ""
                if mit_trend:
                    t, art = _trend(e.get("vor"), rang)
                    trend_td = f'<td class="pt-num" style="color:{TREND_FARBE[art]};font-weight:700">{t}</td>'
                if nach_div:
                    werte = _div(e.get("div"), e.get("rhythmus")) + _pct(e.get("perf"))
                else:
                    werte = _pct(e.get("perf")) + (_div(e.get("div"), e.get("rhythmus")) if mit_div else "")
                zeilen += (
                    f'<tr class="{"pt-zebra" if rang % 2 == 0 else ""}">'
                    f'<td class="pt-num pt-seit">{rang}</td>{trend_td}'
                    f'<td class="pt-wert"><span class="pt-name">{html.escape(str(e["name"]))}</span>'
                    f'<span class="pt-sub">{html.escape(str(e.get("wkn") or ""))}</span></td>'
                    f'{werte}'
                    f'</tr>'
                )
            if nach_div:
                spalten = '<th class="pt-num">Div.-<br>Rendite</th><th class="pt-num">1 Jahr</th>'
            else:
                spalten = f'<th class="pt-num">{zr_wahl}</th>' + (
                    '<th class="pt-num">Div.-<br>Rendite</th>' if mit_div else "")
            st.markdown(
                '<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt"><thead><tr>'
                '<th class="pt-num">#</th>' + ('<th class="pt-num">7&nbsp;T.</th>' if mit_trend else "") +
                f'<th class="pt-wert">Wert</th>'
                f'{spalten}'
                f'</tr></thead><tbody>{zeilen}</tbody></table></div>',
                unsafe_allow_html=True,
            )

            if mit_trend or vergleich_seit is None:
                _wochen_bilanz([(r, e["name"], e.get("wkn"), e.get("vor")) for r, e in enumerate(liste, 1)],
                               (vergleich or {}).get("raus", []), vergleich_seit)

            with st.expander("Hinweise zu den Ranglisten", expanded=False):
                st.caption(
                    "Performance = reine Kursentwicklung ohne Dividenden, Gebühren oder Steuern. "
                    "**Div.-Rendite** = Ausschüttungen der letzten 12 Monate geteilt durch den "
                    "aktuellen Kurs (laufende Rendite, Quelle Yahoo Finance); darunter der Auszahlungsrhythmus "
                    "(monatlich, quartalsweise, halbjährlich, jährlich) aus den Zahlungsterminen der letzten zwei "
                    "Jahre. Sonderdividenden "
                    "zählen mit; Werte über 30 % werden als unplausibel ausgeblendet. "
                    "Werte ohne Kurs seit mehr als 10 Tagen gelten als inaktiv und fehlen. "
                    "Vergangene Performance ist kein Hinweis auf künftige Entwicklung."
                )
                if kat.get("kennung") == "Symbol":
                    st.caption(
                        "Länderlisten: alle Aktien der Heimatbörsen je Land ab einer Mindestgröße "
                        "(Börsenwert, laut Yahoo Finance), wöchentlich aktualisiert; ausländische "
                        "Zweitnotierungen und ADRs sind herausgefiltert, außerhalb der USA höchstens die "
                        "1.500 größten Werte je Land. Kurse "
                        "von Yahoo Finance (Heimatbörse), mit dem Wechselkurs des jeweiligen Tages "
                        "in Euro umgerechnet - Währungsschwankungen sind also enthalten. Nicht "
                        "jeder Nebenwert oder Auslandswert ist bei deutschen Brokern handelbar. "
                        + ("Quelle: " + ", ".join(kat["quellen"]) + "." if kat.get("quellen") else "")
                    )
                else:
                    st.caption(
                        "wikifolios werden automatisch über die Kursquelle gefunden (alle "
                        "Zertifikate mit WKN LS9…), die Suche wird wöchentlich erneuert."
                    )
                st.caption(
                    f"Letzter Lauf: {daten.get('anfragen', '–')} Kursabrufe in "
                    f"{daten.get('laufzeit_sek', '–')} s, {daten.get('fehlgeschlagen', 0)} fehlgeschlagen."
                )
            fehlend = [f for f in daten.get("nicht_gefunden", []) if f.get("kategorie") == kat["titel"]]
            if fehlend:
                with st.expander(f"Nicht gefunden ({len(fehlend)})", expanded=False):
                    if kat.get("kennung") == "Symbol":
                        st.caption("Für diese Indexmitglieder lieferte Yahoo keine Kurse "
                                   "(z.B. frisch umbenannt oder gerade aufgenommen).")
                    else:
                        st.caption("Diese Werte aus top50_universum.py ließen sich weder über die "
                                   "ISIN noch über den Namen finden - dort korrigieren.")
                    for f in fehlend[:100]:
                        st.write(f"- {f['name']} · {f['isin']}")
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Top50", e)


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
        if x is None:
            return "–"
        return f"{x:+.{nachkomma}f} %" if vorzeichen else f"{x:.{nachkomma}f} %"

    def _q_x(x, suffix="x"):
        return "–" if x is None else f"{x:.1f}{suffix}"

    # Spalten der Qualitaets-Tabelle: (Schluessel, Kopf, Formatierung, Farbe)
    def _qf_pct(nachkomma=1, vorzeichen=True):
        return lambda x: "–" if x is None else f"{x:+.{nachkomma}f} %" if vorzeichen else f"{x:.{nachkomma}f} %"

    def _qf_zahl(suffix=""):
        return lambda x: "–" if x is None else f"{x:.1f}{suffix}"

    def _qc_schwelle(gut, schlecht, umgekehrt=False):
        def farbe(x):
            if x is None:
                return ""
            if umgekehrt:
                return "pt-up" if x <= gut else "pt-down" if x >= schlecht else ""
            return "pt-up" if x >= gut else "pt-down" if x <= schlecht else ""
        return farbe

    def _qc_label(gut, schlecht):
        return lambda x: "pt-up" if x in gut else "pt-down" if x in schlecht else ""

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
        """Alle Kennzahlen nebeneinander (sortierbar per Tipp auf die Spalte, als CSV
        herunterladbar) + Direktvergleich ausgewaehlter Aktien Kennzahl fuer Kennzahl."""
        zeilen = []
        for rang, sym in enumerate(symbole, 1):
            e = werte.get(sym)
            if not e:
                continue
            sek_, br_ = BR.einordnen(e.get("br"))
            z = {"#": rang, "Unternehmen": e.get("name") or sym, "Symbol": sym, "Sektor": sek_,
                 "Branche": br_, "Punkte": e.get("gesamt"), "Einordnung": Q_KLASSEN.get(e.get("klasse"), ""),
                 "Dividenden-Kategorie": DV.text(e.get("div"), e.get("div_q"))}
            for key, titel, _, _ in Q_SPALTEN:
                z[titel] = e.get(key)
            zeilen.append(z)
        if not zeilen:
            st.info("Keine Daten.")
            return
        df = pd.DataFrame(zeilen)

        def faerben(spalte):
            regel = next((f for k, t, _, f in Q_SPALTEN if t == spalte.name), None)
            if regel is None:
                return [""] * len(spalte)
            aus = []
            for x in spalte:
                try:
                    aus.append(Q_FARBE_CSS.get(regel(None if pd.isna(x) else x), ""))
                except Exception:
                    aus.append("")
            return aus

        try:
            ansicht = df.style.apply(faerben, axis=0)
        except Exception:
            ansicht = df
        cfg = {"#": st.column_config.NumberColumn("#", width="small"),
               "Unternehmen": st.column_config.TextColumn("Unternehmen", width="medium", pinned=True),
               "Punkte": st.column_config.NumberColumn("Punkte", format="%d", width="small")}
        for key, titel, _, _ in Q_SPALTEN:
            if key in ("moat", "mgmt", "bew", "risiko"):
                continue
            prozent = key not in ("fkgv", "ev_ebit", "nde", "mcap")
            cfg[titel] = st.column_config.NumberColumn(titel, format="%.1f %%" if prozent else "%.1f")
        try:
            st.dataframe(ansicht, hide_index=True, width="stretch", column_config=cfg,
                         height=min(36 * (len(df) + 1) + 4, 720))
        except TypeError:                       # aeltere Streamlit-Version ohne "pinned"
            cfg["Unternehmen"] = st.column_config.TextColumn("Unternehmen", width="medium")
            st.dataframe(ansicht, hide_index=True, width="stretch", column_config=cfg,
                         height=min(36 * (len(df) + 1) + 4, 720))
        st.caption("Tipp auf einen Spaltenkopf sortiert nach dieser Kennzahl · grün/rot = günstig/ungünstig "
                   "nach denselben Schwellen wie in der Einzelansicht · ⤓ oben rechts lädt die Tabelle als CSV.")

        # Direktvergleich: Kennzahlen als Zeilen, ausgewaehlte Aktien als Spalten
        namen = {z["Symbol"]: z["Unternehmen"] for z in zeilen}
        auswahl = st.multiselect("Aktien direkt vergleichen (bis 6)", list(namen), max_selections=6, placeholder="Aktien auswählen …",
                                 default=list(namen)[:3], key="q_vergleich_wahl",
                                 format_func=lambda s_: f"{namen[s_]} ({s_})")
        if auswahl:
            kennzahlen = [("Punkte", "gesamt", lambda x: "–" if x is None else f"{x}"),
                          ("Firmen-Kategorie", "br", BR.kategorie_text)] + \
                         [(t, k, f) for k, t, f, _ in Q_SPALTEN]
            tab = {"Kennzahl": [t for t, _, _ in kennzahlen]}
            for s_ in auswahl:
                e = werte.get(s_) or {}
                kopf = namen[s_][:22] if namen[s_][:22] not in tab else f"{namen[s_][:16]} ({s_})"
                tab[kopf] = [fmt(e.get(k)) if e.get(k) is not None else "–" for _, k, fmt in kennzahlen]
            vdf = pd.DataFrame(tab)

            def faerben_v(zeile):
                k = next((k for t, k, _ in kennzahlen if t == zeile["Kennzahl"]), None)
                regel = next((f for kk, _, _, f in Q_SPALTEN if kk == k), None)
                aus = [""]
                for s_ in auswahl:
                    try:
                        aus.append(Q_FARBE_CSS.get(regel((werte.get(s_) or {}).get(k)), "") if regel else "")
                    except Exception:
                        aus.append("")
                return aus

            try:
                vansicht = vdf.style.apply(faerben_v, axis=1)
            except Exception:
                vansicht = vdf
            st.dataframe(vansicht, hide_index=True, width="stretch", height=36 * (len(vdf) + 1) + 4)

    def _q_tabelle(werte, symbole, vergleich=None, fokus="roic"):
        """HTML-Tabelle. Am Desktop alle Kennzahlen (seitlich scrollbar), auf
        dem iPhone nur Rang, Trend, Name, die gewaehlte Kennzahl und Punkte -
        so bleiben alle Werte untereinander direkt vergleichbar."""
        mit_trend = vergleich is not None
        kopf = '<th class="pt-num">#</th>' + ('<th class="pt-num">7&nbsp;T.</th>' if mit_trend else "")
        kopf += '<th class="pt-wert">Unternehmen</th>'
        for key, titel, _, _ in Q_SPALTEN:
            hl = " q-fokus-hl" if key == fokus else ""
            kopf += f'<th class="pt-num{hl}" data-spalte="q_{key}">{titel}</th>'
        kopf += '<th class="pt-num">Punkte</th>'
        zeilen = ""
        for rang, sym in enumerate(symbole, 1):
            e = werte.get(sym)
            if not e:
                continue
            z = f'<td class="pt-num pt-seit">{rang}</td>'
            if mit_trend:
                t, art = _trend(vergleich["vor"].get(sym), rang)
                z += f'<td class="pt-num" style="color:{TREND_FARBE[art]};font-weight:700">{t}</td>'
            unter = " · ".join(x for x in (sym, BR.kategorie_text(e.get("br"))) if x)
            z += (f'<td class="pt-wert"><span class="pt-name">{html.escape(str(e["name"]))}</span>'
                  f'<span class="pt-sub">{html.escape(unter)}</span></td>')
            for key, _, fmt, farbe in Q_SPALTEN:
                x = e.get(key)
                hl = " q-fokus-hl" if key == fokus else ""
                z += (f'<td class="pt-num pt-stark {farbe(x)}{hl}" data-spalte="q_{key}">'
                      f'{html.escape(fmt(x))}</td>')
            z += (f'<td class="pt-num q-punkte {Q_KLASSE_CSS.get(e.get("klasse"), "")}">'
                  f'{e.get("gesamt", "–")}</td>')
            zeilen += f'<tr class="{"pt-zebra" if rang % 2 == 0 else ""}">{z}</tr>'
        # Nur die gewaehlte Kennzahl auf schmalen Bildschirmen einblenden
        # (die allgemeine Regel blendet dort alle data-spalte-Zellen aus)
        stil = (f'<style>@media (max-width: 700px) {{ .pt.qt td[data-spalte="q_{fokus}"], '
                f'.pt.qt th[data-spalte="q_{fokus}"] {{ display: table-cell; }} }}</style>')
        st.markdown(stil + f'<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt qt"><thead><tr>{kopf}</tr></thead>'
                    f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
        st.markdown('<div class="q-legende">Punkte: <span class="q-prio">■</span> Hohe Analysepriorität · '
                    '<span class="q-beob">■</span> Beobachtungsliste · <span class="q-nicht">■</span> '
                    'Nicht weiterverfolgen · * = aus Kennzahlen angenähert</div>', unsafe_allow_html=True)

    def _q_details(sym, zeile):
        if not daten_q:                 # Aufruf aus einem anderen Reiter: Annahmen nachladen
            daten_q.update(gh_read_taeglich("state/qualitaet.json", None) or {})
        teil = gh_read_taeglich(f"state/qualitaet/details_{zeile.get('d', 0)}.json", None) or {}
        e = (teil.get("werte") or {}).get(sym)
        if not e:
            st.info("Die ausführliche Analyse wird gerade neu geschrieben - bitte in einer Minute erneut öffnen.")
            return
        st.markdown(f"#### {e['name']} ({sym})")
        st.caption(
            f"{BR.kategorie_text(e.get('br')) if e.get('br') else 'Branche unbekannt'} · {e.get('land') or '–'} · Kurs {e['kurs']:,.2f} {e['kwae']} · "
            f"Marktkap. {e['mcap']:,.1f} Mrd € · Jahresabschlüsse {e['gj_erst'][:4]}–{e['gj'][:4]} "
            f"({e['n']} Geschäftsjahre, letztes bis {datetime.date.fromisoformat(e['gj']).strftime('%d.%m.%Y')})"
        )
        kl_css = Q_KLASSE_CSS.get(e["klasse"], "")
        kacheln = [("Gesamtpunktzahl", f'<b class="{kl_css}">{e["gesamt"]}</b><span> / 100</span>'),
                   ("Qualität", f'{e["q_ant"]:.0f}<span> %</span>'),
                   ("Bewertung", f'{e["b_ant"]:.0f}<span> %</span>'),
                   ("Risiko", html.escape(e["risiko"]))]
        st.markdown('<div class="q-kpis">' + "".join(
            f'<div class="q-kpi"><div class="q-kpi-l">{l}</div><div class="q-kpi-v">{v}</div></div>'
            for l, v in kacheln) + "</div>", unsafe_allow_html=True)
        st.markdown(f"**Einordnung: {Q_KLASSEN.get(e['klasse'])}** – {e['grund']}.")

        st.markdown("**Punkte je Bereich**")
        balken = ""
        for k, t, m in Q_BEREICHE:
            p = e["p"].get(k, 0)
            anteil = p / m if m else 0
            farbe = "#34D399" if anteil >= 0.7 else "#F5B942" if anteil >= 0.4 else "#F87171"
            balken += (f'<div class="q-b-zeile"><div>{html.escape(t)}</div>'
                       f'<div class="q-b-bahn"><div class="q-b-fuell" style="width:{anteil * 100:.0f}%;'
                       f'background:{farbe}"></div></div><div class="q-b-wert">{p}/{m}</div></div>')
        st.markdown(f'<div class="q-balken">{balken}</div>', unsafe_allow_html=True)
        if e["flags"]:
            st.markdown("**Red Flags (Abzug)**\n\n" + "\n".join(f"- {t} (−{a})" for t, a in e["flags"]))

        st.markdown("**Warum interessant?**\n\n" + ("\n".join(f"- {t}" for t in e["staerken"])
                                                 or "- Keine herausragenden Stärken in den Kennzahlen."))
        abschnitte = [
            ("Wettbewerbsvorteil (Näherung)", [
                f"Einstufung: **{e['moat']}**",
                f"ROIC Ø {_q_pct(e['roic'], False)}, niedrigster Jahreswert {_q_pct(e['roic_min'], False)}",
                f"Bruttomarge Ø {_q_pct(e['gm'], False)}, Schwankung der operativen Marge {_q_x(e['om_std'], ' Prozentpunkte')}",
                "Netzwerkeffekte, Marke, Patente, Wechselkosten u. Ä. sind nicht automatisch bewertbar."]),
            ("Wachstum", [
                f"Umsatz {_q_pct(e['g_ums'])} p.a. · EPS {_q_pct(e['g_eps'])} p.a. · FCF {_q_pct(e['g_fcf'])} p.a. · "
                f"**FCF je Aktie {_q_pct(e['g_fcfps'])} p.a.**",
                f"Analysten: erwartetes Gewinnwachstum nächstes GJ {_q_pct(e.get('g1'))}"
                + (f" · Schätzungsrevision 90 Tage {_q_pct(e.get('rev90'))} ({e['rev']})" if e.get("rev") else "")]),
            ("ROIC und Reinvestment", [
                f"ROIC zuletzt {_q_pct(e['roic_l'], False)}, Ø {_q_pct(e['roic'], False)}, Trend {_q_x(e['roic_trend'], ' Prozentpunkte')}",
                f"ROE zuletzt {_q_pct(e['roe'], False)} · Capex {_q_pct(e['capex'], False)} vom Umsatz · "
                f"Zukäufe {_q_pct(e['zukauf'], False)} des Free Cashflows"]),
            ("Free Cashflow und Gewinnqualität", [
                f"FCF-Marge Ø {_q_pct(e['fm'], False)} · Cash Conversion (FCF/Gewinn) {_q_x(e['cc'])}",
                f"Aktienbasierte Vergütung {_q_pct(e['sbc'], False)} vom Umsatz · Goodwill/Immaterielles "
                f"{_q_pct(e['gw'], False)} der Bilanzsumme"]),
            ("Bilanz", [
                "Nettocash (mehr liquide Mittel als Schulden)" if e["netcash"] else
                f"Net Debt/EBITDA {_q_x(e['nde'])}",
                f"Zinsdeckung (EBIT/Zinsaufwand) {_q_x(e['zinsd'])}"]),
            ("Management und Kapitalallokation (Näherung)", [
                f"Einstufung: **{e['mgmt']}**",
                f"Aktienanzahl {_q_pct(e['akt'])} p.a. · Rückkäufe + Dividenden {_q_pct(e['aussch'], False)} des FCF",
                "Insiderkäufe, Vergütung und Prognosetreue sind nicht automatisch bewertbar."]),
            ("Dividende", [
                ("Keine Dividende" if e.get("div") == 0 else
                 f"Dividendenrendite {_q_pct(e.get('div'), False, 2)} (letzte 12 Monate)")
                + (f" · Ausschüttungsquote {_q_pct(e.get('div_q'), False, 0)} vom Gewinn" if e.get("div_q") is not None else "")
                + (f" · in {e['div_n']} von {e['n']} Geschäftsjahren gezahlt" if e.get("div_n") is not None else "")]),
            ("Bewertung", [
                f"KGV {_q_x(e['kgv'], '')} · Forward-KGV {_q_x(e['fkgv'], '')} · EV/EBIT {_q_x(e['ev_ebit'], '')} · "
                f"EV/EBITDA {_q_x(e['ev_ebitda'], '')} · EV/FCF {_q_x(e['ev_fcf'], '')} · PEG {_q_x(e['peg'], '')}",
                f"FCF-Rendite {_q_pct(e['fcfy'], False, 2)} – eigener Schnitt zu früheren Geschäftsjahresenden "
                f"{_q_pct(e['h_fcfy'], False, 2)} · früheres KGV Ø {_q_x(e['h_kgv'], '')}"]),
            ("Reverse DCF", [
                ("Der heutige Unternehmenswert unterstellt **"
                 + ("≥ 60" if e["g_impl"] >= 60 else "≤ −30" if e["g_impl"] <= -30 else f"{e['g_impl']:.1f}")
                 + f" % FCF-Wachstum p.a.** über 10 Jahre – erreicht bzw. erwartet sind rund {e['g_ref']:.1f} %"
                 + f" → **{e['erw']}**") if e.get("g_impl") is not None else f"Nicht berechenbar: {e['erw']}",
                f"Annahmen: Kapitalkosten {daten_q.get('annahmen', {}).get('diskont', 9):.0f} %, danach "
                f"{daten_q.get('annahmen', {}).get('g_ewig', 2.5):.1f} % ewiges Wachstum; bei Zyklikern "
                "normalisierter Free Cashflow"]),
        ]
        for titel, zeilen in abschnitte:
            st.markdown(f"**{titel}**\n\n" + "\n".join(f"- {z}" for z in zeilen))

        if e.get("szen"):
            st.markdown("**Szenarien (Bear / Base / Bull)**")
            namen = {"bear": "Bear", "base": "Base", "bull": "Bull"}
            zeilen = ""
            for k in ("bear", "base", "bull"):
                v = e["szen"].get(k)
                if not v:
                    continue
                farbe = "pt-up" if (v["pot"] or 0) >= 0 else "pt-down"
                zeilen += (f'<tr><td class="pt-wert"><span class="pt-name">{namen[k]}</span></td>'
                           f'<td class="pt-num">{FMT.pct(v["g"], 1)}</td><td class="pt-num">{FMT.pct(v["r"], 1)}</td>'
                           f'<td class="pt-num">{v["m"]:.1f}x</td>'
                           f'<td class="pt-num pt-stark {farbe}">{v["pot"]:+.0f} %</td></tr>')
            st.markdown('<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt"><thead><tr><th class="pt-wert">Fall</th>'
                        '<th class="pt-num">FCF-<br>Wachstum</th><th class="pt-num">Kapital-<br>kosten</th>'
                        '<th class="pt-num">Multi-<br>ple</th><th class="pt-num">Wert vs.<br>Kurs</th></tr></thead>'
                        f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
            st.caption("FCF-Wachstum gilt für die Jahre 1–5 und läuft danach linear auf das ewige Wachstum "
                       "aus. Multiple = Endwert im Verhältnis zum FCF (EV/FCF). Bear Case zusätzlich mit 10 % "
                       "geringerem, normalisiertem Free Cashflow.")
        mos = e.get("mos")
        st.markdown("**Margin of Safety**\n\n- " + (
            "Kein positiver fairer Wert berechenbar." if mos is None else
            ("Kurs liegt beim Dreifachen des konservativen fairen Werts oder darüber." if mos <= -200 else
             f"{mos:+.0f} % Sicherheitsmarge zum konservativen fairen Wert (Base Case)"
             + (" – der Kurs liegt darüber." if mos < 0 else ""))))
        st.markdown("**Risiken (aus Kennzahlen)**\n\n" + "\n".join(
            f"- {r}" for r in (e["risiken"] + [f"Kursschwankung {_q_pct(e['vola'], False, 0)} p.a., "
                                               f"größter Rückgang 5 J. {_q_pct(e['dd'], True, 0)}"]))
                    + "\n- Wettbewerb, Disruption, Regulierung, Kunden-/Lieferantenabhängigkeit: nicht automatisch bewertbar.")
        if e.get("kat"):
            st.markdown("**Mögliche Katalysatoren (aus Kennzahlen)**\n\n" + "\n".join(f"- {k}" for k in e["kat"]))
        st.markdown("**These-Killer (Kontrollpunkte)**\n\n" + "\n".join(f"- {k}" for k in e["killer"]))

    daten_q = {}

    def _q_mitglieder(kat_key, alle):
        """Alle Aktien der gewaehlten Kategorie bzw. des Index (fuer den Sektor-Filter)."""
        if not alle:
            return []
        if kat_key == "alle":
            return list(alle)
        gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
        if kat_key.startswith("i:"):
            g = (gruppen.get("indizes") or {}).get(kat_key[2:]) or {}
        else:
            g = (gruppen.get("kategorien") or {}).get(kat_key) or {}
        return [s_ for s_ in g.get("s") or [] if s_ in alle]

    def _q_dividenden_tabelle(alle, mitglieder):
        """Je Dividenden-Kategorie: Anzahl, Ø Punkte, davon nachhaltig, bester Wert."""
        zeilen = ""
        for i, z in enumerate(DV.uebersicht([alle[s_] for s_ in mitglieder]), 1):
            b = z["bester"]
            zeilen += (f'<tr class="{"pt-zebra" if i % 2 == 0 else ""}">'
                       f'<td class="pt-wert"><span class="pt-name">{DV.ICON[z["schluessel"]]} '
                       f'{html.escape(z["titel"])}</span></td>'
                       f'<td class="pt-num">{z["anzahl"]}</td><td class="pt-num">{_de_zahl(z["schnitt_punkte"], 0)}</td>'
                       f'<td class="pt-num">{z["nachhaltig"] if z["schluessel"] != "keine" else "–"}</td>'
                       f'<td class="pt-wert"><span class="pt-name">{html.escape(str(b["name"]))}</span>'
                       f'<span class="pt-sub">{b.get("gesamt")} Punkte · Dividende '
                       f'{FMT.pct(b.get("div") or 0, 1)}</span></td></tr>')
        st.markdown('<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                    '<table class="pt"><thead><tr><th class="pt-wert">Dividende</th><th class="pt-num">Aktien</th>'
                    '<th class="pt-num">Ø Punkte</th><th class="pt-num">nachhaltig</th>'
                    '<th class="pt-wert">Bester Wert</th></tr></thead>'
                    f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
        st.caption("Dividendenrendite und Ausschüttungsquote vom Qualitäts-Agenten (Yahoo Finance). „nachhaltig“ = "
                   "Ausschüttungsquote höchstens 80 % des Gewinns. Filter und Sortierung oben unter „🔎 Filter“.")

    def _q_sektoren_tabelle(alle, mitglieder):
        """Je Sektor: Anzahl, Ø Punkte, Hohe Prioritaet, bester Wert."""
        je = {}
        for s_ in mitglieder:
            e = alle[s_]
            je.setdefault(BR.sektor(e.get("br")), []).append(e)
        zeilen = ""
        for i, (sek, liste) in enumerate(sorted(je.items(), key=lambda kv: -len(kv[1])), 1):
            bester = max(liste, key=lambda e: e.get("gesamt") or 0)
            schnitt = sum(e.get("gesamt") or 0 for e in liste) / len(liste)
            prio = sum(1 for e in liste if e.get("klasse") == "prio")
            branchen_n = len({BR.branche_de(e.get("br")) for e in liste})
            zeilen += (f'<tr class="{"pt-zebra" if i % 2 == 0 else ""}">'
                       f'<td class="pt-wert"><span class="pt-name">{BR.SEKTOR_ICON.get(sek, "")} {html.escape(sek)}</span>'
                       f'<span class="pt-sub">{"ohne Branchenangabe" if sek == "Sonstige" else f"{branchen_n} Branche" + ("n" if branchen_n != 1 else "")}</span></td>'
                       f'<td class="pt-num">{len(liste)}</td><td class="pt-num">{_de_zahl(schnitt, 0)}</td>'
                       f'<td class="pt-num">{prio}</td>'
                       f'<td class="pt-wert"><span class="pt-name">{html.escape(str(bester["name"]))}</span>'
                       f'<span class="pt-sub">{bester.get("gesamt")} Punkte · '
                       f'{html.escape(BR.branche_de(bester.get("br")))}</span></td></tr>')
        st.markdown('<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                    '<table class="pt"><thead><tr><th class="pt-wert">Sektor</th><th class="pt-num">Aktien</th>'
                    '<th class="pt-num">Ø Punkte</th><th class="pt-num">Priorität</th>'
                    '<th class="pt-wert">Bester Wert</th></tr></thead>'
                    f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
        st.caption("Sektor und Branche aus der Yahoo-Branchenangabe (11 Sektoren). „Sonstige“ = keine "
                   "Branchenangabe. Filter oben: „Firmen-Kategorie“.")

    def _div_rhythmen():
        """{Yahoo-Symbol: Auszahlungsrhythmus} aus dem Top-50-Agenten (gleiche Symbole wie der Qualitaets-Agent)."""
        d = gh_read_taeglich("state/top50_dividenden.json", None) or {}
        return {s_: v[1] for s_, v in (d.get("werte") or {}).items() if isinstance(v, list) and len(v) > 1 and v[1]}

    def _render_qualitaet():
        nonlocal daten_q
        daten = gh_read_taeglich("state/qualitaet.json", None)
        if not daten or not daten.get("kategorien"):
            st.info("Noch kein Qualitäts-Score vorhanden. Der Agent läuft täglich um 05:00 Uhr. Für einen "
                    "Sofortstart: auf GitHub unter **Actions → Watchlist Qualitäts-Score (täglich) → Run "
                    "workflow**. Die Kennzahlen aller Aktien werden in den ersten Tagen "
                    "schrittweise aufgebaut (bis zu 3.000 je Lauf, große Werte zuerst).")
            return
        daten_q = daten
        kats = daten["kategorien"]
        keys = [k for k in daten.get("reihenfolge", kats) if k in kats]
        titel = [kats[k]["titel"] for k in keys]
        werte = daten.get("werte", {})
        ansichten = ["Gesamt-Rangliste"] + list(Q_KLASSEN.values())

        # Filter in einem aufklappbaren Bereich (auf dem Handy sonst ~1.100 px Bedienelemente vor der Liste);
        # die Ueberschrift zeigt die aktuelle Auswahl
        _ss = st.session_state
        if (_ss.get("q_auswahl_art") or "Kategorie") == "Index":
            _reg = _ss.get("q_region") or ""
            _was = str(_ss.get(f"q_index_{_reg}") or _reg or "Index").split(" (")[0]
        else:
            _was = str(_ss.get("q_kategorie") or titel[0])
        _filter_titel = " · ".join(x for x in (
            _was, _ss.get("q_laenge") or "Top 500",
            str(_ss.get("q_sektor") or "").split(" ", 1)[-1] if _ss.get("q_sektor") not in (None, "Alle Sektoren") else "",
            _ss.get("q_klasse") if _ss.get("q_klasse") not in (None, ansichten[0]) else "",
            f"Dividende {_ss.get('q_div_filter')}" if _ss.get("q_div_filter") not in (None, "Alle") else "",
            f"Ausschüttung {_ss.get('q_div_rhythmus')}" if _ss.get("q_div_rhythmus") not in (None, "Alle") else "",
            "nachhaltig" if _ss.get("q_div_nachhaltig") else "",
            "nach Dividende sortiert" if _ss.get("q_sortierung") == "Dividendenrendite" else "") if x)
        with st.expander(f"🔎 Filter: {_filter_titel}", expanded=False, key="q_filter_exp"):
            if _auswahl_art("q") == "Index":
                # Index: Rangliste aus den Gesamtdaten, gleiche Sortierung wie der Agent
                gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
                idx_key = _index_auswahl("q", gruppen.get("indizes") or {}, INDEX_REGIONEN_APP)
                if not idx_key:
                    return
                alle, _ = _q_alle()
                info = gruppen["indizes"][idx_key]
                mitglieder = [s for s in info.get("s", []) if s in alle]
                werte = {s: alle[s] for s in mitglieder}
                n = _listen_laenge("q")

                def rang(liste):
                    return sorted(liste, key=lambda s: (-werte[s]["gesamt"], -(werte[s]["b_ant"] or 0)))[:n]

                kat = {"top": rang(mitglieder), "universum": info.get("zugeordnet", len(mitglieder)),
                       "bewertet": len(mitglieder),
                       "je_klasse": {kl: rang([s for s in mitglieder if werte[s]["klasse"] == kl]) for kl in Q_KLASSEN},
                       "klassen": {kl: sum(1 for s in mitglieder if werte[s]["klasse"] == kl) for kl in Q_KLASSEN}}
                kat_key = f"i:{idx_key}"
            else:
                wahl = auswahl_kompakt("Kategorie", titel, default=titel[0], key="q_kategorie")
                kat_key = keys[titel.index(wahl)] if wahl in titel else keys[0]
                kat = kats[kat_key]
                n = _listen_laenge("q")
                if n > len(kat.get("top") or []):
                    # Laengere Liste aus den Gesamtdaten - gleiche Sortierung wie der Agent
                    gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
                    alle, _ = _q_alle()
                    g = (gruppen.get("kategorien") or {}).get(kat_key) or {}
                    if alle and (kat_key == "alle" or g.get("s")):
                        mitglieder = list(alle) if kat_key == "alle" else [s_ for s_ in g["s"] if s_ in alle]
                        werte = {**werte, **{s_: alle[s_] for s_ in mitglieder}}

                        def rang_k(liste):
                            return sorted(liste, key=lambda s_: (-werte[s_]["gesamt"], -(werte[s_]["b_ant"] or 0)))[:n]

                        kat = dict(kat, top=rang_k(mitglieder),
                                   je_klasse={kl: rang_k([s_ for s_ in mitglieder if werte[s_]["klasse"] == kl])
                                              for kl in Q_KLASSEN})
                else:
                    kat = dict(kat, top=kat["top"][:n], je_klasse={k: v[:n] for k, v in kat["je_klasse"].items()})
            # Firmen-Kategorie (Sektor, aus der Yahoo-Branche): Rangliste aus allen Aktien der Auswahl
            sek_opt = ["Alle Sektoren"] + [f"{BR.SEKTOR_ICON[x]} {x}" for x in BR.SEKTOREN + ["Sonstige"]]
            sek_wahl = auswahl_kompakt("Firmen-Kategorie (Sektor)", sek_opt, default=sek_opt[0], key="q_sektor") or sek_opt[0]
            alle_q, _ = _q_alle()
            mitglieder_alle = _q_mitglieder(kat_key, alle_q)
            sektor = sek_wahl.split(" ", 1)[1] if sek_wahl != sek_opt[0] else None
            # Dividenden: Filter nach Hoehe/Nachhaltigkeit und Sortierung nach Rendite
            div_filter = st.selectbox("Dividende", list(DV.FILTER), key="q_div_filter") or "Alle"
            nur_nachhaltig = st.toggle("Nur nachhaltige Dividende", key="q_div_nachhaltig",
                                       help="Ausschüttungsquote höchstens 80 % des Gewinns")
            rhythmen = _div_rhythmen()
            rh_filter = st.selectbox("Ausschüttung", ["Alle"] + list(getattr(DV, "RHYTHMEN", ("monatlich", "alle 2 Monate", "quartalsweise", "halbjährlich", "jährlich"))), key="q_div_rhythmus",
                                     help="Wie oft die Dividende gezahlt wird – ermittelt aus den Zahlungsterminen "
                                          "der letzten zwei Jahre (Yahoo Finance)") or "Alle"
            if rh_filter != "Alle" and not rhythmen:
                st.info("Der Auszahlungsrhythmus wird beim nächsten nächtlichen Lauf der Ranglisten ermittelt – "
                        "bis dahin findet dieser Filter keine Werte.")
            sortierung = st.pills("Sortieren nach", ["Punkte", "Dividendenrendite"], default="Punkte",
                                  key="q_sortierung") or "Punkte"
            nach_div = sortierung == "Dividendenrendite"
            gefiltert = bool(sektor or div_filter != "Alle" or nur_nachhaltig or nach_div or rh_filter != "Alle")
            if gefiltert and not mitglieder_alle:
                st.warning("Die Gesamtdaten sind gerade nicht lesbar – Filter bitte später erneut versuchen.")
                sektor, gefiltert = None, False
            if gefiltert:
                werte = {**werte, **{s_: alle_q[s_] for s_ in mitglieder_alle}}
                im_sektor = [s_ for s_ in mitglieder_alle
                             if (not sektor or BR.sektor(alle_q[s_].get("br")) == sektor)
                             and DV.passt(alle_q[s_], div_filter, nur_nachhaltig)
                             and (rh_filter == "Alle" or rhythmen.get(s_) == rh_filter)]

                def rang_sek(liste):
                    if nach_div:
                        return sorted(liste, key=lambda s_: (-(werte[s_].get("div") or 0), -werte[s_]["gesamt"]))[:n]
                    return sorted(liste, key=lambda s_: (-werte[s_]["gesamt"], -(werte[s_]["b_ant"] or 0)))[:n]

                kat = dict(kat, top=rang_sek(im_sektor), bewertet=len(im_sektor), universum=len(mitglieder_alle),
                           je_klasse={kl: rang_sek([s_ for s_ in im_sektor if werte[s_]["klasse"] == kl])
                                      for kl in Q_KLASSEN},
                           klassen={kl: sum(1 for s_ in im_sektor if werte[s_]["klasse"] == kl) for kl in Q_KLASSEN})
            a_wahl = st.pills("Einordnung", ansichten, default=ansichten[0], key="q_klasse") or ansichten[0]
        if rhythmen:
            werte = {s_: (dict(w, aus=rhythmen[s_]) if s_ in rhythmen else w) for s_, w in werte.items()}
        if mitglieder_alle:
            with st.expander("🏷️ Firmen-Kategorien im Überblick"):
                _q_sektoren_tabelle(alle_q, mitglieder_alle)
            with st.expander("💶 Dividenden-Kategorien im Überblick"):
                _q_dividenden_tabelle(alle_q, mitglieder_alle)
        if a_wahl == ansichten[0]:
            symbole, liste_key = kat["top"], f"{kat_key}|top"
        else:
            kl = next(k for k, v in Q_KLASSEN.items() if v == a_wahl)
            symbole, liste_key = kat["je_klasse"].get(kl, []), f"{kat_key}|{kl}"
        # Wochenvergleich gibt es nur fuer die Ranglisten des Agenten, nicht fuer eigene Filter
        vergleich = None if gefiltert else (daten.get("vergleich") or {}).get(liste_key)

        stand = ranglisten_stand(daten)
        abd = daten.get("abdeckung", {})
        kl = kat["klassen"]
        _filter_txt = " · ".join(x for x in (f"Sektor {sektor}" if sektor else "",
                                             f"Dividende {div_filter}" if div_filter != "Alle" else "",
                                             f"Ausschüttung {rh_filter}" if rh_filter != "Alle" else "",
                                             "nachhaltig" if nur_nachhaltig else "",
                                             "sortiert nach Dividendenrendite" if nach_div else "") if x)
        basis_txt = (f"Aktien der Auswahl ({_filter_txt})" if gefiltert else
                     "Indexmitgliedern" if kat_key.startswith("i:") else "Aktien")
        st.caption(
            f"Stand {stand} · {kat['bewertet']} von {kat['universum']} {basis_txt} bewertet · "
            f"Priorität {kl['prio']} · Beobachten {kl['beobachten']} · Nicht weiterverfolgen {kl['nicht']}"
        )
        if "offen" in abd:
            # Neuer Lauf: unterscheidet "noch nie abgerufen" von "Yahoo liefert keine Daten"
            if abd["offen"] > 0:
                st.warning(f"Aufbau läuft: {abd['offen']} Aktien wurden noch nicht abgerufen – jeder Lauf "
                           "ergänzt bis zu 3.000, große Werte zuerst.")
            if abd.get("ohne_daten"):
                st.caption(f"ℹ️ {abd['ohne_daten']} Aktien liefern bei Yahoo zu wenige Geschäftszahlen "
                           "(< 3 Jahre Abschlüsse, z. B. Neuemissionen, Fonds, Mantel) und werden nicht bewertet. "
                           "Sie werden alle 3 Tage erneut versucht.")
        elif abd.get("mit_kennzahlen", 0) < 0.9 * abd.get("universum", 1):
            st.caption(f"ℹ️ Kennzahlen für {abd.get('mit_kennzahlen', 0)} von {abd.get('universum', 0)} Aktien. "
                       "Der Rest liefert bei Yahoo vermutlich zu wenige Geschäftszahlen – die genaue "
                       "Aufteilung zeigt der nächste Lauf.")
        if not symbole:
            st.info("In dieser Einordnung gibt es hier derzeit keine Aktie.")
            return

        titel_fokus = ["📊 Alle Kennzahlen"] + [t for _, t, _, _ in Q_SPALTEN]
        f_wahl = auswahl_kompakt("Kennzahl in der Tabelle", titel_fokus, default=titel_fokus[0],
                          key="q_fokus") or titel_fokus[0]
        if f_wahl == titel_fokus[0]:
            _q_vergleich(werte, symbole)
        else:
            fokus = next((k for k, t, _, _ in Q_SPALTEN if t == f_wahl), "roic")
            _q_tabelle(werte, symbole, vergleich, fokus)
        if not gefiltert and (vergleich is not None or daten.get("vergleich_seit") is None):
            _wochen_bilanz([(r, werte[s]["name"] if s in werte else s, s, (vergleich or {}).get("vor", {}).get(s))
                            for r, s in enumerate(symbole, 1)],
                           (vergleich or {}).get("raus", []), daten.get("vergleich_seit"))

        optionen = [s for s in symbole if s in werte]
        auswahl = st.selectbox("Detailanalyse:", optionen, index=None, key="q_detail",
                               placeholder="Aktie auswählen …",
                               format_func=lambda s: f"{werte[s]['name']} ({s}) – {werte[s]['gesamt']} Punkte")
        if auswahl:
            _q_details(auswahl, werte[auswahl])

        with st.expander("Methodik und Grenzen", expanded=False):
            st.markdown(
                "**100 Punkte:** Unternehmensqualität 20 · Wachstum & Reinvestment 15 · Free Cashflow & "
                "Gewinnqualität 15 · Bilanz 10 · Management & Kapitalallokation 10 · Wettbewerbsvorteil 10 · "
                "Bewertung 15 · Chance-Risiko 5. Red Flags (z. B. negativer FCF, Verwässerung > 5 % p. a., "
                "stark steigende Schulden, SBC > 10 % vom Umsatz, extreme eingepreiste Erwartungen) ziehen "
                "Punkte ab.\n\n"
                "**Einordnung:** Qualität (die 80 Punkte ohne Bewertung) und Bewertung werden getrennt "
                "betrachtet. *Hohe Analysepriorität* = Qualität ≥ 70 %, Bewertung ≥ 55 %, mind. 65 Punkte, "
                "keine schwere Red Flag. *Beobachtungsliste* = Qualität ≥ 62 %, aber zu wenig "
                "Sicherheitsmarge. Alles andere: *Nicht weiterverfolgen*.\n\n"
                "**Näherungen:** Moat und Management lassen sich nicht aus Zahlen ablesen – sie werden über "
                "ROIC-Höhe und -Stabilität, Bruttomarge, Margenstabilität, Aktienanzahl, ROIC-Trend und "
                "Zukäufe angenähert. Qualitative Risiken (Wettbewerb, Disruption, Regulierung) werden nicht "
                "bewertet.\n\n"
                "**Nicht bewertet:** Banken und Versicherungen (Free Cashflow, ROIC und EBITDA sind dort "
                f"nicht sinnvoll definiert) – derzeit {abd.get('finanzwerte', 0)} Werte.\n\n"
                "**Daten:** Yahoo Finance – bis zu 5 Geschäftsjahre, wöchentlich aufgefrischt; Kurse und "
                "Bewertung täglich. Alle Beträge in Euro umgerechnet. Fehlerhafte Quelldaten sind möglich – "
                "vor jeder Entscheidung im Geschäftsbericht prüfen.\n\n"
                "**Keine Kauf- oder Verkaufsempfehlung.** Ein hervorragendes Unternehmen kann zum falschen "
                "Preis unattraktiv sein; eine billig aussehende Aktie wird dadurch nicht attraktiv."
            )



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
        """Gesamtdaten aller bewerteten Aktien + Kategorien/Indizes."""
        alle, _ = _q_alle()
        gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
        if not alle or not gruppen.get("kategorien"):
            return None
        return {"alle": alle, "gruppen": gruppen}

    def _qk_zeilen(m, kat_key):
        if kat_key == "alle":
            return list(m["alle"].values())
        return [m["alle"][s_] for s_ in m["gruppen"]["kategorien"].get(kat_key, {}).get("s", []) if s_ in m["alle"]]

    def _qk_einteilen(zeilen, zr_key):
        """-> ({feld: [zeilen sortiert]}, median) fuer Zeilen mit Kursdaten"""
        mit = [z for z in zeilen if z.get(zr_key) is not None and z.get("q_ant") is not None]
        if not mit:
            return {f: [] for f, _, _ in QK_FELDER}, None
        werte = sorted(z[zr_key] for z in mit)
        median = werte[len(werte) // 2]
        felder = {f: [] for f, _, _ in QK_FELDER}
        for z in mit:
            q_hoch = z["q_ant"] >= QK_QUAL_GRENZE
            k_stark = z[zr_key] >= median
            felder[("gut_" if q_hoch else "schwach_") + ("stark" if k_stark else "schwach")].append(z)
        felder["gut_schwach"].sort(key=lambda z: (-z["gesamt"], z[zr_key]))
        felder["gut_stark"].sort(key=lambda z: -z["gesamt"])
        felder["schwach_stark"].sort(key=lambda z: -z[zr_key])
        felder["schwach_schwach"].sort(key=lambda z: -z["gesamt"])
        return felder, median

    def _qk_tabelle(zeilen, zr_key, zr_titel):
        kopf = ('<th class="pt-num">#</th><th class="pt-wert">Unternehmen</th>'
                f'<th class="pt-num">Kurs {html.escape(zr_titel)}</th><th class="pt-num">FCF-<br>Rendite</th>'
                '<th class="pt-num">Punkte</th>')
        z_html = ""
        for platz, z in enumerate(zeilen, 1):
            perf = z[zr_key]
            bew = z.get("bew") or "–"
            mos = z.get("mos")
            unter = f'{z["s"]} · Qualität {z["q_ant"]:.0f} % · Bewertung {bew}'
            if mos is not None and mos > -200:
                unter += f" · MoS {mos:+.0f} %"
            unter = unter.replace(" %", "\u00a0%")          # Zahl und % nie getrennt umbrechen
            fy = z.get("fcfy")
            z_html += (
                f'<tr class="{"pt-zebra" if platz % 2 == 0 else ""}">'
                f'<td class="pt-num pt-seit">{platz}</td>'
                f'<td class="pt-wert"><span class="pt-name">{html.escape(z["name"])}</span>'
                f'<span class="pt-sub">{html.escape(unter)}</span></td>'
                f'<td class="pt-num pt-stark {"pt-up" if perf >= 0 else "pt-down"}">{vz_zahl(perf, 1)} %</td>'
                f'<td class="pt-num pt-stark {"pt-up" if (fy or 0) >= 5 else "pt-down" if fy is not None and fy < 2 else ""}">'
                f'{"–" if fy is None else f"{FMT.pct(fy, 1)}"}</td>'
                f'<td class="pt-num q-punkte {Q_KLASSE_CSS.get(z["klasse"], "")}">{z["gesamt"]}</td></tr>')
        st.markdown(f'<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt"><thead><tr>{kopf}</tr></thead>'
                    f'<tbody>{z_html}</tbody></table></div>', unsafe_allow_html=True)

    def _qk_diagramm(zeilen, zr_key, zr_titel, median):
        mit = [z for z in zeilen if z.get(zr_key) is not None and z.get("q_ant") is not None]
        if not mit:
            return
        # Ausreisser (z.B. +900 %) stauchen sonst alles andere zusammen
        werte = sorted(z[zr_key] for z in mit)
        oben = werte[int(len(werte) * 0.98)] if len(werte) > 20 else werte[-1]
        unten = werte[int(len(werte) * 0.02)] if len(werte) > 20 else werte[0]
        fig = go.Figure()
        for kl, titel_kl, farbe in (("nicht", "Nicht weiterverfolgen", "#6B7280"),
                                    ("beobachten", "Beobachtungsliste", "#F5B942"),
                                    ("prio", "Hohe Analysepriorität", "#34D399")):
            pts = [z for z in mit if z["klasse"] == kl]
            if not pts:
                continue
            fig.add_trace(go.Scattergl(
                x=[min(max(z[zr_key], unten), oben) for z in pts], y=[z["q_ant"] for z in pts],
                mode="markers", name=titel_kl,
                marker=dict(color=farbe, size=6 if kl != "nicht" else 5, opacity=0.85 if kl != "nicht" else 0.45),
                text=[f'{_h(z["name"])} ({_h(z["s"])})<br>Kurs {zr_titel}: {vz_zahl(z[zr_key], 1)} %<br>'
                      f'Qualität {z["q_ant"]:.0f} % · {z["gesamt"]} Punkte' for z in pts],
                hovertemplate="%{text}<extra></extra>"))
        for x0, y0, text in ((unten, 99, "Qualität hoch · Kurs schwach"), (oben, 99, "Qualität hoch · Kurs stark"),
                             (unten, 1, "Qualität niedrig · Kurs schwach"), (oben, 1, "Qualität niedrig · Kurs stark")):
            fig.add_annotation(x=x0, y=y0, text=text, showarrow=False, font=dict(size=10, color="#71717A"),
                               xanchor="left" if x0 == unten else "right", yanchor="top" if y0 > 50 else "bottom")
        fig.add_vline(x=median, line=dict(color="#A1A1AA", width=1, dash="dot"))
        fig.add_hline(y=QK_QUAL_GRENZE, line=dict(color="#A1A1AA", width=1, dash="dot"))
        fig.update_layout(
            paper_bgcolor="#000000", plot_bgcolor="#000000", height=380, margin=dict(l=10, r=10, t=10, b=40),
            showlegend=True, legend=dict(orientation="h", y=-0.14, x=0, font=dict(color="#A1A1AA", size=10)),
            xaxis=dict(title=dict(text=f"Kursentwicklung {zr_titel} (EUR)", font=dict(color="#A1A1AA", size=12)),
                       ticksuffix=" %", showgrid=True, gridcolor="#1A1A1A", zeroline=True, zerolinecolor="#333",
                       tickfont=dict(color="#A1A1AA")),
            yaxis=dict(title=dict(text="Qualität (%)", font=dict(color="#A1A1AA", size=12)), range=[0, 100],
                       showgrid=True, gridcolor="#1A1A1A", tickfont=dict(color="#A1A1AA")),
            dragmode=False)
        st.plotly_chart(UI.chart_stil(fig), width="stretch", key="qk_diagramm", config={"displayModeBar": False})

    def _render_qualitaet_kurs():
        m = _qk_daten()
        if not m:
            st.info("Noch keine Daten für den Abgleich. Die Kursentwicklung wird ab dem nächsten Lauf des "
                    "Qualitäts-Agenten mitgespeichert; bis alle Aktien sie haben, dauert es einige Läufe.")
            return
        gruppen = m["gruppen"]
        if _auswahl_art("qk") == "Index":
            idx_key = _index_auswahl("qk", gruppen.get("indizes") or {}, INDEX_REGIONEN_APP)
            if not idx_key:
                return
            zeilen = [m["alle"][s_] for s_ in gruppen["indizes"][idx_key].get("s", []) if s_ in m["alle"]]
        else:
            kats = gruppen["kategorien"]
            keys = [k for k in gruppen.get("reihenfolge", kats) if k in kats]
            titel = [kats[k]["titel"] for k in keys]
            wahl = auswahl_kompakt("Kategorie", titel, default=titel[0], key="qk_kategorie") or titel[0]
            zeilen = _qk_zeilen(m, keys[titel.index(wahl)] if wahl in titel else keys[0])
        zr_titel = [t for _, t in QK_ZEITRAEUME]
        zr_wahl = st.pills("Zeitraum", zr_titel, default="1 Jahr", key="qk_zeitraum") or "1 Jahr"
        zr_key = dict((t, k) for k, t in QK_ZEITRAEUME)[zr_wahl]

        felder, median = _qk_einteilen(zeilen, zr_key)
        mit = sum(len(v) for v in felder.values())
        if not mit:
            st.info("Für diese Kategorie liegt die Kursentwicklung noch nicht vor – sie wird mit den nächsten "
                    "Läufen aufgebaut.")
            return
        st.caption(f"{mit} von {len(zeilen)} bewerteten Aktien mit Kursdaten · Trennlinien: Qualität "
                   f"{QK_QUAL_GRENZE} % (ohne Bewertung) und Median der Kursentwicklung ({vz_zahl(median, 1)} %)")
        _qk_diagramm(zeilen, zr_key, zr_wahl, median)

        f_titel = [f"{t} ({len(felder[f])})" for f, t, _ in QK_FELDER]
        f_wahl = auswahl_kompakt("Feld", f_titel, default=f_titel[0], key="qk_feld")
        f_key, _, f_text = QK_FELDER[f_titel.index(f_wahl) if f_wahl in f_titel else 0]
        st.caption(f_text)
        liste = felder[f_key][:_listen_laenge("qk")]
        if not liste:
            st.info("In diesem Feld liegt derzeit keine Aktie.")
            return
        _qk_tabelle(liste, zr_key, zr_wahl)
        st.markdown('<div class="q-legende">Punkte: <span class="q-prio">■</span> Hohe Analysepriorität · '
                    '<span class="q-beob">■</span> Beobachtungsliste · <span class="q-nicht">■</span> '
                    'Nicht weiterverfolgen · MoS = Sicherheitsmarge zum konservativen fairen Wert</div>',
                    unsafe_allow_html=True)
        auswahl = st.selectbox("Detailanalyse:", [z["s"] for z in liste], index=None, key="qk_detail",
                               placeholder="Aktie auswählen …",
                               format_func=lambda s: next(f'{z["name"]} ({s}) – {z["gesamt"]} Punkte'
                                                          for z in liste if z["s"] == s))
        if auswahl:
            _q_details(auswahl, next(z for z in liste if z["s"] == auswahl))

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
        return (str(text), farbe, fett)

    def _ue_css_farbe(klasse):
        return {"pt-up": "up", "pt-down": "down"}.get(klasse)

    def _ue_trend(vor, platz):
        t, art = _trend(vor, platz)
        return _ue_z(t, {"up": "up", "down": "down", "neu": "up", "gleich": "grau"}[art], art != "gleich")

    def _ue_qualitaets_tabelle(werte, symbole, vergleich, umfang):
        spalten = [("#", 3, "r"), ("7 T.", 4, "r"), ("Unternehmen", 17, "l"), ("Branche", 11, "l"),
                   ("Punkte", 5, "r"), ("Einordnung", 7, "l")]
        spalten[3] = ("Branche", 10, "l")
        spalten += [(titel, 7 if key == "nde" else 6, "r") for key, titel, _, _ in Q_SPALTEN]
        zeilen = []
        for platz, sym in enumerate(symbole[:umfang], 1):
            e = werte.get(sym)
            if not e:
                continue
            kl = e.get("klasse")
            z = [_ue_z(platz, fett=True),
                 _ue_trend((vergleich or {}).get("vor", {}).get(sym), platz) if vergleich is not None else _ue_z("–", "grau"),
                 _ue_z(f'{e["name"]} ({sym})', fett=True), _ue_z(BR.kategorie_text(e.get("br")) if e.get("br") else "–"),
                 _ue_z(e.get("gesamt", "–"), {"prio": "prio", "beobachten": "beob"}.get(kl, "nicht"), True),
                 _ue_z(Q_KLASSEN_KURZ.get(kl, "–"), {"prio": "prio", "beobachten": "beob"}.get(kl, "nicht"))]
            for key, _, fmt, farbe in Q_SPALTEN:
                x = e.get(key)
                z.append(_ue_z(fmt(x), _ue_css_farbe(farbe(x))))
            zeilen.append(z)
        return spalten, zeilen

    def _ue_abschnitte(dq, dp, umfang, teile):
        """Liste von Abschnitten: {"titel", "text", "spalten": [(name, gewicht, ausrichtung)],
        "zeilen": [[zelle, ...]], "seite": neue Seite im PDF}"""
        ab = []
        werte = (dq or {}).get("werte", {})
        kats = (dq or {}).get("kategorien", {})
        keys = [k for k in (dq or {}).get("reihenfolge", kats) if k in kats]
        verg = (dq or {}).get("vergleich") or {}

        if "Zusammenfassung" in teile and kats:
            zeilen = []
            for k in keys:
                kat, v = kats[k], verg.get(f"{k}|top")
                neu = sum(1 for s in kat["top"] if v is not None and s not in v["vor"])
                zeilen.append([_ue_z(kat["titel"], fett=True), _ue_z(kat["universum"]), _ue_z(kat["bewertet"]),
                               _ue_z(kat["klassen"]["prio"], "prio", True), _ue_z(kat["klassen"]["beobachten"], "beob"),
                               _ue_z(kat["klassen"]["nicht"], "nicht"),
                               _ue_z(neu if v is not None else "–", "up" if neu else None),
                               _ue_z(len(v["raus"]) if v is not None else "–", "down" if v and v["raus"] else None)])
            ab.append({"titel": "Zusammenfassung Qualitäts-Score", "seite": False,
                       "text": "Anzahl Aktien je Kategorie und Einordnung; Neu/Raus bezieht sich auf die "
                               f"Top {dq.get('top_n', 50)} der Gesamt-Rangliste gegenüber vor 7 Tagen.",
                       "spalten": [("Kategorie", 22, "l"), ("Aktien", 7, "r"), ("bewertet", 7, "r"),
                                   ("Priorität", 7, "r"), ("Beobachten", 7, "r"), ("Nicht weiterv.", 8, "r"),
                                   ("Neu (7 T.)", 7, "r"), ("Raus (7 T.)", 7, "r")],
                       "zeilen": zeilen})

        for teil, kl, text in (("Hohe Analysepriorität", "prio",
                                "Fundamental starke Unternehmen, deren aktuelle Bewertung eine genauere Prüfung rechtfertigt."),
                               ("Beobachtungsliste", "beobachten",
                                "Sehr gute Unternehmen, deren Bewertung aktuell wenig Sicherheitsmarge bietet "
                                "oder bei denen einzelne Kennzahlen das Bild trüben.")):
            if teil in teile and "alle" in kats:
                symbole = kats["alle"]["je_klasse"].get(kl, [])
                sp, zl = _ue_qualitaets_tabelle(werte, symbole, verg.get(f"alle|{kl}"), umfang)
                ab.append({"titel": f"{teil} – alle Aktien (Top {min(umfang, len(symbole))} von "
                                    f"{kats['alle']['klassen'][kl]})", "text": text, "spalten": sp,
                           "zeilen": zl, "seite": True})

        if "Qualität je Kategorie" in teile:
            for k in keys:
                if k == "alle":
                    continue
                kat = kats[k]
                sp, zl = _ue_qualitaets_tabelle(werte, kat["top"], verg.get(f"{k}|top"), umfang)
                if zl:
                    ab.append({"titel": f"Qualitäts-Score: {kat['titel']}",
                               "text": f"Gesamt-Rangliste, Top {len(zl)} von {kat['bewertet']} bewerteten Aktien.",
                               "spalten": sp, "zeilen": zl, "seite": True})

        if "Qualität × Kurs" in teile:
            mq = _qk_daten()
            if mq:
                zeilen_alle = list(mq["alle"].values())
                felder, median = _qk_einteilen(zeilen_alle, "p12")
                for f_key, f_titel, f_text in QK_FELDER[:3]:
                    zl = []
                    for platz, z in enumerate(felder[f_key][:umfang], 1):
                        fy = z.get("fcfy")
                        zl.append([_ue_z(platz, fett=True), _ue_z(f'{z["name"]} ({z["s"]})', fett=True),
                                   _ue_z(BR.kategorie_text(z.get("br")) if z.get("br") else "–"),
                                   _ue_z(f'{vz_zahl(z["p12"], 1)} %', "up" if z["p12"] >= 0 else "down", True),
                                   _ue_z(f'{z["q_ant"]:.0f} %'),
                                   _ue_z(z["gesamt"], {"prio": "prio", "beobachten": "beob"}.get(z["klasse"], "nicht"), True),
                                   _ue_z("–" if fy is None else f"{FMT.pct(fy, 1)}", "up" if (fy or 0) >= 5 else None),
                                   _ue_z(z.get("bew") or "–"),
                                   _ue_z("–" if z.get("mos") is None or z["mos"] <= -200 else f'{z["mos"]:+.0f} %')])
                    ab.append({"titel": f"Qualität × Kurs (1 Jahr): {f_titel[2:].strip()} – alle Aktien "
                                        f"(Top {len(zl)} von {len(felder[f_key])})",
                               "text": f_text + (f" Median Kursentwicklung: {vz_zahl(median, 1)} %." if median is not None else ""),
                               "spalten": [("#", 3, "r"), ("Unternehmen", 22, "l"), ("Branche", 14, "l"),
                                           ("Kurs 1 J.", 7, "r"), ("Qualität", 7, "r"), ("Punkte", 6, "r"),
                                           ("FCF-Rendite", 8, "r"), ("Bewertung", 8, "l"), ("MoS", 7, "r")],
                               "zeilen": zl, "seite": True})

        if "Wochenveränderung" in teile and verg:
            zeilen = []
            for k in keys:
                v = verg.get(f"{k}|top")
                if v is None:
                    continue
                neu = [f"{werte[s]['name']} (Platz {i})" for i, s in enumerate(kats[k]["top"], 1)
                       if s not in v["vor"] and s in werte]
                raus = [f"{r['name']} ({r['vor']} → " + (str(r["jetzt"]) if r.get("jetzt") else
                        Q_KLASSEN_KURZ.get(r.get("klasse"), "ohne Daten")) + ")" for r in v["raus"]]
                auf = sorted(((v["vor"][s] - i, werte[s]["name"], i) for i, s in enumerate(kats[k]["top"], 1)
                              if s in v["vor"] and s in werte and v["vor"][s] > i), reverse=True)[:3]
                zeilen.append([_ue_z(kats[k]["titel"], fett=True),
                               _ue_z("; ".join(neu) or "–", "up" if neu else None),
                               _ue_z("; ".join(raus) or "–", "down" if raus else None),
                               _ue_z("; ".join(f"{n} ▲ {d}" for d, n, _ in auf) or "–")])
            seit = _seit_text(dq.get("vergleich_seit")) or ""
            ab.append({"titel": "Wochenveränderung Qualitäts-Score (Gesamt-Rangliste)", "seite": True,
                       "text": seit, "spalten": [("Kategorie", 14, "l"), ("Neu aufgenommen", 30, "l"),
                                                 ("Rausgeflogen (vorher → jetzt)", 30, "l"),
                                                 ("Größte Aufsteiger", 26, "l")], "zeilen": zeilen})

        if "Performance" in teile and dp and dp.get("kategorien"):
            titel_zr = dict((k, t) for k, t in dp.get("zeitraeume", []))
            div_zr = tuple(dp.get("dividenden_zeitraum") or ("DIV", "Div.-Rendite"))
            for k in dp.get("reihenfolge") or list(dp["kategorien"]):
                kat = dp["kategorien"].get(k)
                if not kat:
                    continue
                zrs = [z for z in UE_ZEITRAEUME if kat["top"].get(z)]
                if kat.get("dividende") and kat["top"].get(div_zr[0]):
                    zrs.append(div_zr[0])
                if not zrs:
                    continue
                zeilen = []
                for platz in range(1, umfang + 1):
                    z = [_ue_z(platz, fett=True)]
                    leer = True
                    for zr in zrs:
                        liste = kat["top"][zr]
                        if platz > len(liste):
                            z.append(_ue_z(""))
                            continue
                        e, leer = liste[platz - 1], False
                        wert = e.get("div") if zr == div_zr[0] else e.get("perf")
                        zahl = "–" if wert is None else (f"{FMT.pct(wert, 2)}" if zr == div_zr[0] else f"{vz_zahl(wert, 1)} %")
                        v = (kat.get("vergleich") or {}).get(zr)
                        trend = _trend(e.get("vor"), platz)[0] if v is not None else ""
                        name = e["name"] if len(e["name"]) <= 26 else e["name"][:25] + "…"
                        z.append(_ue_z(f"{name}\n{zahl}\t{trend}" if trend else f"{name}\n{zahl}",
                                       "up" if (wert or 0) >= 0 else "down"))
                    if not leer:
                        zeilen.append(z)
                ab.append({"titel": f"Performance: {kat['titel']}", "seite": True,
                           "text": "Kursentwicklung je Zeitraum (ohne Dividenden), Top "
                                   f"{min(umfang, 50)} je Spalte; ▲/▼ = Platzveränderung zu vor 7 Tagen.",
                           "spalten": [("#", 3, "r")] + [(titel_zr.get(z, div_zr[1] if z == div_zr[0] else z), 12, "l")
                                                         for z in zrs],
                           "zeilen": zeilen})
        return ab

    def _ue_html(abschnitte):
        """Bildschirm: breite Tabellen scrollen seitlich, die Namensspalte bleibt stehen."""
        for a in abschnitte:
            st.markdown(f'<div class="abschnitt">{html.escape(a["titel"])}</div>', unsafe_allow_html=True)
            if a.get("text"):
                st.caption(a["text"])
            if not a["zeilen"]:
                st.caption("– keine Einträge –")
                continue
            namensspalte = next((i for i, (n, _, _) in enumerate(a["spalten"])
                                 if n in ("Unternehmen", "Kategorie")), None)
            kopf = "".join(
                f'<th class="{"pt-wert" if aus == "l" else "pt-num"}{" ue-fix" if i == namensspalte else ""}">'
                f'{html.escape(n).replace("7 T.", "7&nbsp;T.")}</th>' for i, (n, _, aus) in enumerate(a["spalten"]))
            zeilen = ""
            for r, zeile in enumerate(a["zeilen"]):
                zellen = ""
                for i, ((text, farbe, fett), (_, _, aus)) in enumerate(zip(zeile, a["spalten"])):
                    stil = f"color:{UE_FARBEN_SCHIRM[farbe]};" if farbe else ""
                    stil += "font-weight:700;" if fett else ""
                    inhalt = "<br>".join(html.escape(t) for t in text.split("\n")).replace(
                        "\t", '&nbsp;&nbsp;<span style="font-weight:700">') + ("</span>" if "\t" in text else "")
                    zellen += (f'<td class="{"pt-wert" if aus == "l" else "pt-num"}'
                               f'{" ue-fix" if i == namensspalte else ""}" style="{stil}">{inhalt}</td>')
                zeilen += f'<tr class="{"pt-zebra" if r % 2 else ""}">{zellen}</tr>'
            st.markdown(f'<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt ue"><thead><tr>{kopf}</tr></thead>'
                        f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)

    def _ue_pdf(abschnitte, stand_text):
        """Druckfertiges PDF (A4 quer). Pfeile werden als Vektorgrafik gezeichnet -
        Symbolschriften sind nicht auf jedem Geraet/Drucker vorhanden."""
        import io
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                        TableStyle)

        class Trend(Flowable):
            """▲ 3 / ▼ 2 als gezeichnetes Dreieck + Zahl"""
            def __init__(self, richtung, text, farbe, groesse=6.5):
                super().__init__()
                self.richtung, self.text, self.farbe, self.g = richtung, text, farbe, groesse
                self.width, self.height = 18 * mm, self.g + 1

            def wrap(self, *a):
                return self.width, self.height

            def draw(self):
                c = self.canv
                c.setFillColor(colors.HexColor(self.farbe))
                s = self.g * 0.8
                if self.richtung == "up":
                    pfad = [(0, 0.5), (s, 0.5), (s / 2, s + 0.5)]
                else:
                    pfad = [(0, s + 0.5), (s, s + 0.5), (s / 2, 0.5)]
                p = c.beginPath()
                p.moveTo(*pfad[0])
                for pt in pfad[1:]:
                    p.lineTo(*pt)
                p.close()
                c.drawPath(p, fill=1, stroke=0)
                c.setFont("Helvetica-Bold", self.g)
                c.drawString(s + 2, 0.8, self.text)

        grund = ParagraphStyle("u", fontName="Helvetica", fontSize=6.6, leading=8)
        fett = ParagraphStyle("uf", parent=grund, fontName="Helvetica-Bold")
        titel = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=12.5, leading=15, spaceAfter=2)
        klein = ParagraphStyle("k", fontName="Helvetica", fontSize=7.5, leading=9.5,
                               textColor=colors.HexColor("#4B5563"), spaceAfter=5)
        breite = landscape(A4)[0] - 20 * mm

        # Koepfe fuer die schmalen PDF-Spalten: Umbruch nur an Leerzeichen
        PDF_KOPF = {"FCF/Aktie-Wachst.": "FCF/ Aktie p.a.", "FCF-Rendite": "FCF Rend.",
                    "Forward-KGV": "Fwd KGV", "Umsatz-Wachst.": "Umsatz p.a.", "EPS-Wachst.": "EPS p.a.",
                    "FCF-Wachst.": "FCF p.a.", "Net Debt/EBITDA": "ND/ EBITDA", "Verwässerung p.a.": "Aktien p.a.",
                    "FCF-Marge": "FCF Marge",
                    "Management*": "Mgmt.*", "Bewertung": "Bewer- tung", "Mkap. Mrd €": "Mkap. Mrd €",
                    "Einordnung": "Einord.", "Nicht weiterv.": "Nicht weiterv."}

        def trend_zelle(t, farbe_zahl):
            """kleine Zeile: Zahl links, Trend (Dreieck/o/NEU) rechts daneben"""
            if t.startswith(("▲", "▼")):
                hexf = UE_FARBEN_DRUCK["up" if t[0] == "▲" else "down"]
                return Trend("up" if t[0] == "▲" else "down", t[1:].strip(), hexf, groesse=6)
            return Paragraph(f'<font color="{UE_FARBEN_DRUCK["up" if t == "NEU" else "grau"]}"><b>{t}</b></font>',
                             ParagraphStyle("tz", parent=grund, fontSize=6))

        def zelle(text, farbe, ist_fett, ausrichtung):
            hexfarbe = UE_FARBEN_DRUCK.get(farbe) if farbe else None
            if "\t" in text:                  # Performance-Matrix: Name / Zahl + Trend
                name, rest = text.split("\n", 1)
                zahl, t = rest.split("\t", 1)
                innen = Table([[Paragraph(html.escape(name), grund), ""],
                               [Paragraph(f'<font color="{hexfarbe}"><b>{html.escape(zahl)}</b></font>', grund),
                                trend_zelle(t, hexfarbe)]],
                              colWidths=[None, 12 * mm], style=TableStyle([
                                  ("SPAN", (0, 0), (1, 0)), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
                return innen
            text = text.replace("Netto-Cash", "Netcash")
            erste = text.split("\n")[0]
            if erste[:1] in ("▲", "▼") and "\n" not in text and hexfarbe:
                return Trend("up" if erste[0] == "▲" else "down", erste[1:].strip(), hexfarbe)
            teile_txt = []
            for zeile in text.split("\n"):
                z = html.escape(zeile)
                for sym, rtg in (("▲", "up"), ("▼", "down")):
                    # Pfeile im Fliesstext (Performance-Matrix): als farbiges Wort
                    z = z.replace(sym + " ", "+" if rtg == "up" else "−")
                teile_txt.append(z)
            inhalt = "<br/>".join(teile_txt)
            if hexfarbe:
                if "\n" in text:        # Performance-Zelle: Name schwarz, Zahl farbig
                    kopf, rest = inhalt.split("<br/>", 1)
                    inhalt = f'{kopf}<br/><font color="{hexfarbe}"><b>{rest}</b></font>'
                else:
                    inhalt = f'<font color="{hexfarbe}">{inhalt}</font>'
            stil = ParagraphStyle("z", parent=fett if ist_fett else grund,
                                  alignment=2 if ausrichtung == "r" else 0)
            return Paragraph(inhalt, stil)

        puffer = io.BytesIO()

        def rahmen(c, doc):
            c.saveState()
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(colors.HexColor("#111827"))
            c.drawString(10 * mm, landscape(A4)[1] - 7 * mm, "Watchlist-Gesamtübersicht")
            c.setFont("Helvetica", 7.5)
            c.setFillColor(colors.HexColor("#6B7280"))
            c.drawRightString(landscape(A4)[0] - 10 * mm, landscape(A4)[1] - 7 * mm, stand_text)
            c.drawString(10 * mm, 6 * mm, "Keine Kauf- oder Verkaufsempfehlung. Kennzahlen aus Yahoo Finance, "
                                          "Moat/Management (*) aus Kennzahlen angenähert.")
            c.drawRightString(landscape(A4)[0] - 10 * mm, 6 * mm, f"Seite {doc.page}")
            c.restoreState()

        doc = SimpleDocTemplate(puffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                                topMargin=12 * mm, bottomMargin=12 * mm, title="Watchlist-Gesamtübersicht")
        inhalt = [Paragraph("Watchlist-Gesamtübersicht", ParagraphStyle("h", fontName="Helvetica-Bold",
                                                                         fontSize=18, leading=22)),
                  Paragraph(stand_text + " · Grün = Hohe Analysepriorität / positiv, Gelb = Beobachtungsliste, "
                            "Grau = Nicht weiterverfolgen, Rot = negativ · Dreieck = Platzveränderung zu vor "
                            "7 Tagen, o = unverändert, NEU = neu in der Liste.", klein), Spacer(1, 3 * mm)]
        erste = True
        for a in abschnitte:
            if a["seite"] and not erste:
                inhalt.append(PageBreak())
            erste = False
            inhalt.append(Paragraph(html.escape(a["titel"]), titel))
            if a.get("text"):
                inhalt.append(Paragraph(html.escape(a["text"]), klein))
            if not a["zeilen"]:
                inhalt.append(Paragraph("– keine Einträge –", klein))
                continue
            gewichte = [g for _, g, _ in a["spalten"]]
            spaltenbreiten = [breite * g / sum(gewichte) for g in gewichte]
            kopf = [Paragraph(html.escape(PDF_KOPF.get(n, n)), ParagraphStyle(
                "kopf", parent=fett, fontSize=6.2, leading=7.5, textColor=colors.white,
                alignment=2 if aus == "r" else 0)) for n, _, aus in a["spalten"]]
            daten = [kopf] + [[zelle(t, f, b, aus) for (t, f, b), (_, _, aus) in zip(z, a["spalten"])]
                              for z in a["zeilen"]]
            tab = Table(daten, colWidths=spaltenbreiten, repeatRows=1)
            stil = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5)]
            for r in range(2, len(daten), 2):
                stil.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F3F4F6")))
            tab.setStyle(TableStyle(stil))
            inhalt += [tab, Spacer(1, 4 * mm)]
        inhalt += [Spacer(1, 4 * mm), Paragraph(
            "Methodik: 100 Punkte (Qualität 20, Wachstum 15, Free Cashflow 15, Bilanz 10, Management 10, "
            "Wettbewerbsvorteil 10, Bewertung 15, Chance-Risiko 5) abzüglich Red Flags. Qualität und Bewertung "
            "werden getrennt betrachtet. Banken/Versicherungen sind nicht bewertet. Performance = reine "
            "Kursentwicklung in Euro. Alle Angaben ohne Gewähr – vor jeder Entscheidung im Geschäftsbericht "
            "prüfen.", klein)]
        doc.build(inhalt, onFirstPage=rahmen, onLaterPages=rahmen)
        return puffer.getvalue()

    def _render_uebersicht():
        dq = gh_read_taeglich("state/qualitaet.json", None)
        dp = gh_read_taeglich("state/top50.json", None)
        if not dq and not dp:
            st.info("Noch keine Daten vorhanden – die Übersicht erscheint nach dem ersten Lauf der Agenten.")
            return
        # Umfang und Inhalt in einem Klappbereich (UX 10/2026: am Handy standen drei Auswahlgruppen mit ~500 px
        # vor dem ersten Inhalt) - die Beschriftung zeigt die aktuelle Wahl
        _u = st.session_state.get("ue_umfang") or "Top 10"
        _t = st.session_state.get("ue_teile", UE_TEILE)
        with st.expander(f"⚙️ Umfang & Inhalt · {_u} · {len(_t or [])} von {len(UE_TEILE)} Bereichen",
                         key="ue_einstellungen"):
            umfang_txt = st.pills("Umfang je Liste", ["Top 10", "Top 25", "Top 50"], default="Top 10",
                                  key="ue_umfang") or "Top 10"
            teile = st.pills("Inhalt", UE_TEILE, default=UE_TEILE, selection_mode="multi", key="ue_teile") or []
        umfang = int(umfang_txt.split()[1])
        try:
            stand = datetime.datetime.fromisoformat((dq or dp)["stand"]).strftime("%d.%m.%Y, %H:%M Uhr")
        except Exception:
            stand = "–"
        stand_text = f"Stand {stand}"
        abschnitte = _ue_abschnitte(dq, dp, umfang, teile)
        if not abschnitte:
            st.info("Bitte mindestens einen Inhalt auswählen.")
            return

        # PDF erst auf Knopfdruck erzeugen - das Bauen kostet einige Sekunden
        schluessel = f"ue_pdf|{stand}|{umfang}|{'/'.join(teile)}"
        if st.button("📄 PDF zum Drucken erstellen", key="ue_pdf_knopf", width="stretch"):
            try:
                st.session_state["ue_pdf"] = (schluessel, _ue_pdf(abschnitte, stand_text))
            except ImportError:
                st.error("Für das PDF fehlt das Paket **reportlab**: bitte die Zeile `reportlab` in die "
                         "requirements.txt des Repos aufnehmen – Streamlit installiert es dann automatisch.")
        fertig = st.session_state.get("ue_pdf")
        if fertig and fertig[0] == schluessel:
            st.download_button("⬇️ PDF herunterladen", data=fertig[1], mime="application/pdf",
                               file_name=f"Watchlist_Uebersicht_{datetime.date.today().isoformat()}.pdf",
                               key="ue_pdf_download", width="stretch")
        st.caption(f"{stand_text} · A4 quer · breite Tabellen lassen sich hier seitlich wischen, "
                   "die Namensspalte bleibt stehen.")
        _ue_html(abschnitte)

    WK_SEITE = 25                                       # Raenge je Seite der wikifolio-Liste
    WK_SPALTEN = ["1M", "3M", "6M", "1J", "2J", "3J", "5J"]

    def _wk_seite(nr):
        st.session_state["wk_seite"] = nr

    def _render_wikifolios():
        """Uebergreifende Liste aller wikifolios der Ranglisten (Top 50 + Top 500 je Zeitraum):
        alle Zeitraeume nebeneinander, sortiert nach einem, seitenweise mit Suche."""
        daten = gh_read_taeglich("state/top50.json", None) or {}
        kat = (daten.get("kategorien") or {}).get("wikifolios")
        if not kat:
            st.info("Noch keine wikifolio-Ranglisten vorhanden – sie entstehen beim nächsten Lauf des "
                    "Watchlist-Agenten (täglich 07:30 Uhr).")
            return
        lang = gh_read_taeglich("state/top50_lang_wikifolios.json", None) or {}
        werte = wikifolio_werte(kat, lang)
        titel = {k: t for k, t in (daten.get("zeitraeume") or []) if k in WK_SPALTEN}
        spalten = [k for k in WK_SPALTEN if k in titel]
        zr_titel = [titel[k] for k in spalten]
        zr_wahl = st.pills("Sortiert nach", zr_titel, default="1 Jahr" if "1 Jahr" in zr_titel else zr_titel[0],
                           key="wk_zeitraum") or zr_titel[0]
        zr = spalten[zr_titel.index(zr_wahl)]
        laenge = _listen_laenge("wk")
        begriff = st.text_input("In der Liste suchen", key="wk_such", placeholder="Name oder WKN …")
        liste = wikifolio_rangliste(werte, zr, begriff, n=laenge)
        signatur = (zr, laenge, begriff)
        if st.session_state.get("wk_signatur") != signatur:
            st.session_state["wk_signatur"], st.session_state["wk_seite"] = signatur, 1
        stand = ranglisten_stand(daten)
        st.caption(f"Stand {stand} · {len(werte)} wikifolios in den Ranglisten · {kat.get('aktiv', '–')} aktiv "
                   f"· sortiert nach {zr_wahl}" + (f" · {len(liste)} Treffer" if begriff else ""))
        if not liste:
            st.info(f"„{begriff}“ ist nicht unter den Top {laenge} für {zr_wahl}." if begriff else
                    "Für diesen Zeitraum liegen keine Werte vor.")
            return
        seiten = max((len(liste) + WK_SEITE - 1) // WK_SEITE, 1)
        nr = min(max(int(st.session_state.get("wk_seite", 1)), 1), seiten)
        teil = liste[(nr - 1) * WK_SEITE:nr * WK_SEITE]

        def _pct(v, stark):
            if v is None:
                return '<td class="pt-num">–</td>'
            return (f'<td class="pt-num {"pt-stark " if stark else ""}{"pt-up" if v >= 0 else "pt-down"}">'
                    f'{vz_zahl(v, 1)} %</td>')

        # sortierte Spalte direkt hinter den Namen (auf dem Handy sonst erst nach Wischen sichtbar)
        spalten = [zr] + [k for k in spalten if k != zr]
        zeilen = "".join(
            f'<tr class="{"pt-zebra" if w["rang"] % 2 == 0 else ""}">'
            f'<td class="pt-num pt-seit ue-fix wk-rang">{w["rang"]}</td>'
            f'<td class="pt-wert ue-fix wk-name"><span class="pt-name">{_h(w["name"])}</span>'
            f'<span class="pt-sub">{_h(w["wkn"])}</span></td>'
            + "".join(_pct(w["perf"].get(k), k == zr) for k in spalten) + "</tr>"
            for w in teil)
        kopf = "".join(f'<th class="pt-num">{"▼ " if k == zr else ""}{_h(titel[k])}</th>' for k in spalten)
        # wie die Gesamtuebersicht: seitlich wischbar (auch am iPhone), Rang und Name bleiben links stehen
        st.markdown('<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                    '<table class="pt pt-kompakt ue wk"><thead><tr><th class="pt-num ue-fix wk-rang">#</th>'
                    f'<th class="pt-wert ue-fix wk-name">wikifolio</th>{kopf}</tr></thead>'
                    f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
        if seiten > 1:
            # Rangbereich direkt waehlbar statt langem Scrollen - unter der Tabelle
            n1, n2, n3 = st.columns([0.5, 2, 0.5], vertical_alignment="bottom")
            n1.button("◀", key="wk_zur", on_click=_wk_seite, args=(nr - 1,), disabled=nr <= 1, width="stretch",
                      help="Vorherige Seite")

            def bereich(i):
                t = liste[(i - 1) * WK_SEITE:i * WK_SEITE]
                return f"Rang {t[0]['rang']}–{t[-1]['rang']}  ({i}/{seiten})"

            wahl = n2.selectbox("Seite", list(range(1, seiten + 1)), index=nr - 1, format_func=bereich,
                                key=f"wk_bereich_{nr}", label_visibility="collapsed")
            if wahl != nr:
                st.session_state["wk_seite"] = wahl
                st.rerun()
            n3.button("▶", key="wk_vor", on_click=_wk_seite, args=(nr + 1,), disabled=nr >= seiten,
                      width="stretch", help="Nächste Seite")
        # PDF erst auf Knopfdruck erzeugen: ganze Liste (alle Seiten), alle Zeitraeume
        pdf_schluessel = f"wk_pdf|{stand}|{zr}|{laenge}|{begriff}"
        if st.button("📄 PDF der ganzen Liste erstellen", key="wk_pdf_knopf", width="stretch"):
            try:
                import wikifolio_pdf
                kopfzeile = (f"Stand {stand} · Top {laenge} sortiert nach {zr_wahl} · {len(liste)} wikifolios"
                             + (f" · Suche „{begriff}“" if begriff else ""))
                st.session_state["wk_pdf"] = (pdf_schluessel, wikifolio_pdf.bericht(liste, spalten, titel, zr,
                                                                                     kopfzeile))
            except ImportError:
                st.error("Für das PDF fehlt das Paket **reportlab** (requirements.txt).")
        fertig = st.session_state.get("wk_pdf")
        if fertig and fertig[0] == pdf_schluessel:
            st.download_button("⬇️ PDF herunterladen", data=fertig[1], mime="application/pdf",
                               file_name=f"wikifolio_Rangliste_{datetime.date.today().isoformat()}.pdf",
                               key="wk_pdf_download", width="stretch")
        st.caption("Tabelle seitlich wischen für alle Zeiträume – Rang und Name bleiben stehen. "
                   "– = in diesem Zeitraum nicht unter den Top 500 (oder noch keine so lange Historie). "
                   "Werte übernehmen: im Portfolio Builder unter „Wert hinzufügen → Wikifolios → Top-Listen“. "
                   "Vergangene Entwicklung ist keine Prognose.")

    KS_SEITE = 25

    def _ks_de(x, dez=1):
        return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _ks_seite(nr):
        st.session_state["ks_seite"] = nr

    def _ks_rangliste(art):
        """ETF-/wikifolio-Score aus dem Top-500-Katalog - je Sitzung und Datenstand gemerkt."""
        import klassen_score as KS
        teile = [gh_read_taeglich(f"state/planer/katalog_gross_{i}.json", {}) or {} for i in range(4)]
        stand = next((t.get("stand") for t in teile if t.get("stand")), "")
        gemerkt = st.session_state.get(f"_ks_{art}")
        if gemerkt and gemerkt[0] == stand:
            return stand, gemerkt[1]
        liste = KS.rangliste(teile, art)
        st.session_state[f"_ks_{art}"] = (stand, liste)
        return stand, liste

    def _render_klassen_score():
        """Eigene Bewertung fuer ETFs und wikifolios (klassen_score.py) - unabhaengig vom Aktien-Score."""
        import klassen_score as KS
        art_titel = {"ETFs": "etf", "wikifolios": "wikifolio"}
        art_wahl = st.pills("Anlageklasse", list(art_titel), default="ETFs", key="ks_art") or "ETFs"
        art = art_titel[art_wahl]
        stand, alle = _ks_rangliste(art)
        if not alle:
            st.info("Noch keine Kursdaten für diese Anlageklasse – sie entstehen beim nächsten Lauf des "
                    "Watchlist-Agenten (täglich 07:30 Uhr).")
            return
        kriterien = KS.KRITERIEN[art]
        with st.expander("ℹ️ Wie wird bewertet?"):
            st.markdown(
                f"**{art_wahl} haben eine eigene Bewertung** – unabhängig vom Qualitäts-Score der Aktien "
                "(der beruht auf Geschäftszahlen, die es hier nicht gibt). Bewertet wird die Kurshistorie aus "
                "den Top-500-Daten. Jedes Kriterium gibt 0–100 Punkte, linear zwischen „schwach“ und „stark“; "
                "der Score ist der gewichtete Durchschnitt.")
            einheit = {"rendite": " % p. a.", "rr": "", "rdd": "", "dd": " %", "vola": " %", "historie": " J.",
                       "bestaendig": " %"}
            _ks_tabelle([("Kriterium", "l"), ("Gewicht", "r"), ("schwach (0 P.)", "r"), ("stark (100 P.)", "r")],
                        [[_h(t), f"{g} %",
                          ("−" if k == "dd" else "") + f"{_ks_de(sl, 1 if sl % 1 else 0)}{einheit[k]}",
                          ("−" if k == "dd" else "") + f"{_ks_de(gu, 1 if gu % 1 else 0)}{einheit[k]}"]
                         for k, t, g, sl, gu in kriterien])
            erkl = {"etf": "- **Rendite je Risiko** = Rendite p. a. ÷ Schwankung p. a.\n"
                           "- **Hebel-/Short-Produkte** werden auf höchstens 40 Punkte gedeckelt – sie eignen sich "
                           "nur für kurzfristige Spekulation.\n"
                           "- Nicht enthalten, weil in den Daten nicht vorhanden: laufende Kosten (TER), "
                           "Tracking Difference, Fondsvolumen, Replikation.",
                    "wikifolio": "- **Rendite je Rückgang** = Rendite p. a. ÷ maximaler Rückgang. Die gemessene "
                                 "Schwankung ist bei wikifolios oft untypisch niedrig, der Rückgang zeigt das "
                                 "Verlustrisiko ehrlicher.\n"
                                 "- **Track Record:** lange Historie zählt stärker als bei ETFs – kurze Zeiträume "
                                 "sind bei aktiven Strategien wenig aussagekräftig.\n"
                                 "- Renditen über 60 % p. a. bringen keine Extrapunkte (Ausnahme, nicht "
                                 "fortschreibbar).\n"
                                 "- Nicht enthalten: Gebühren, investiertes Kapital, Handelsstil des Traders, "
                                 "Emittentenrisiko."}[art]
            st.markdown(
                "- **Tabelle:** Rendite p. a. über 1, 3, 5 und 10 Jahre sowie über die gesamte Laufzeit "
                "(„Gesamt p. a.“, ab 1 Jahr Historie).\n"
                "- **Für den Score** zählt die Rendite p. a. aus dem längsten vorhandenen Zeitraum (10, 5, 3 oder 1 Jahr).\n"
                "- **Beständigkeit** = Anteil der Zeiträume (1/3/5/10 Jahre) mit Gewinn.\n" + erkl + "\n"
                f"- **Einordnung:** ab {_ks_de(KS.GRENZE_PRIO, 0)} Punkten *Hohe Analysepriorität* (nur mit mindestens "
                f"{_ks_de(KS.MIN_JAHRE[art], 0)} Jahren Historie, ohne Hebel), ab {_ks_de(KS.GRENZE_BEOBACHTEN, 0)} "
                "*Beobachtungsliste*, darunter *Nicht weiterverfolgen*.\n"
                "- Modellbewertung aus vergangenen Kursen – keine Prognose und keine Kaufempfehlung.")
        ansichten = ["Gesamt-Rangliste"] + list(KS.KLASSEN.values())
        e_wahl = st.pills("Einordnung", ansichten, default=ansichten[0], key="ks_klasse") or ansichten[0]
        laenge = _listen_laenge("ks")
        begriff = st.text_input("In der Liste suchen", key="ks_such", placeholder="Name, WKN oder ISIN …")
        liste = alle
        if e_wahl != ansichten[0]:
            kl = next(k for k, v in KS.KLASSEN.items() if v == e_wahl)
            liste = [e for e in liste if e["bewertung"]["einordnung"] == kl]
        liste = liste[:laenge]
        b_ = str(begriff or "").strip().lower()
        if b_:
            liste = [e for e in liste if b_ in f'{e["name"]} {e["kennung"]} {e["isin"]}'.lower()]
        signatur = (art, e_wahl, laenge, begriff)
        if st.session_state.get("ks_signatur") != signatur:
            st.session_state["ks_signatur"], st.session_state["ks_seite"] = signatur, 1
        anz = {k: sum(1 for e in alle if e["bewertung"]["einordnung"] == k) for k in KS.KLASSEN}
        try:
            stand_txt = datetime.date.fromisoformat(str(stand)[:10]).strftime("%d.%m.%Y")
        except Exception:
            stand_txt = str(stand) or "–"
        st.caption(f"Stand {stand_txt} · {len(alle)} {art_wahl} bewertet · Priorität {anz['prio']} · "
                   f"Beobachten {anz['beobachten']} · Nicht weiterverfolgen {anz['nicht']}"
                   + (f" · {len(liste)} Treffer" if b_ else ""))
        if not liste:
            st.info(f"„{begriff}“ ist nicht in dieser Auswahl." if b_ else "Keine Werte in dieser Auswahl.")
            return
        seiten = max((len(liste) + KS_SEITE - 1) // KS_SEITE, 1)
        nr = min(max(int(st.session_state.get("ks_seite", 1)), 1), seiten)
        teil = liste[(nr - 1) * KS_SEITE:nr * KS_SEITE]
        risiko_titel = "Rendite je Risiko" if art == "etf" else "Rendite je Rückgang"
        risiko_k = "rr" if art == "etf" else "rdd"

        def zahl(v, dez=1, einheit="", vz=False, minus=False):
            if v is None:
                return '<td class="pt-num pt-leer">–</td>'
            if minus:
                return f'<td class="pt-num">−{_ks_de(v, 0)} %</td>'
            txt = (vz_zahl(v, dez) if vz else _ks_de(v, dez)) + einheit
            farbe = (" pt-up" if v >= 0 else " pt-down") if vz else ""
            return f'<td class="pt-num{farbe}">{txt}</td>'

        zeilen = []
        for e in teil:
            b = e["bewertung"]
            k = b["kennzahlen"]
            staerken, schwaechen = KS.staerken_schwaechen(b, art)
            grund = "".join(f'<span class="ks-plus">+ {_h(x)}</span>' for x in staerken) + "".join(
                f'<span class="ks-minus">– {_h(x)}</span>' for x in schwaechen)
            zeilen.append(
                f'<tr class="{"pt-zebra" if e["rang"] % 2 == 0 else ""}">'
                f'<td class="pt-num pt-seit ue-fix wk-rang">{e["rang"]}</td>'
                f'<td class="pt-wert ue-fix wk-name"><span class="pt-name">{_h(e["name"])}</span>'
                f'<span class="pt-sub">{_h(e["kennung"] or e["isin"])}</span></td>'
                f'<td class="pt-num"><span class="q-punkte {Q_KLASSE_CSS[b["einordnung"]]}">'
                f'{_ks_de(b["score"], 0)}</span></td>'
                + "".join(zahl(k["pa"][z], 1, " %", vz=True) for z in ("1J", "3J", "5J", "10J", "gesamt"))
                + zahl(k[risiko_k], 2)
                + zahl(k["dd"], minus=True) + zahl(k["vola"], 0, " %")
                + zahl(k["jahre"], 1, " J.")
                + f'<td class="ks-grund">{grund or "–"}</td></tr>')
        kopf = "".join(f'<th class="pt-num">{t}</th>' for t in
                       ("Score", "1 Jahr", "3 J. p. a.", "5 J. p. a.", "10 J. p. a.", "Gesamt p. a.", risiko_titel,
                        "Max. Rückgang", "Schwankung", "Historie"))
        st.markdown('<div class="q-legende">Score: <span class="q-prio">■</span> Hohe Analysepriorität · '
                    '<span class="q-beob">■</span> Beobachtungsliste · <span class="q-nicht">■</span> '
                    'Nicht weiterverfolgen</div>', unsafe_allow_html=True)
        st.markdown('<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                    '<table class="pt pt-kompakt ue wk ks"><thead><tr><th class="pt-num ue-fix wk-rang">#</th>'
                    f'<th class="pt-wert ue-fix wk-name">{art_wahl[:-1] if art == "etf" else "wikifolio"}</th>'
                    f'{kopf}<th class="ks-grund">Begründung</th></tr></thead>'
                    f'<tbody>{"".join(zeilen)}</tbody></table></div>', unsafe_allow_html=True)
        if seiten > 1:
            n1, n2, n3 = st.columns([0.5, 2, 0.5], vertical_alignment="bottom")
            n1.button("◀", key="ks_zur", on_click=_ks_seite, args=(nr - 1,), disabled=nr <= 1, width="stretch",
                      help="Vorherige Seite")

            def bereich(i):
                t = liste[(i - 1) * KS_SEITE:i * KS_SEITE]
                return f"Rang {t[0]['rang']}–{t[-1]['rang']}  ({i}/{seiten})"

            wahl = n2.selectbox("Seite", list(range(1, seiten + 1)), index=nr - 1, format_func=bereich,
                                key=f"ks_bereich_{nr}", label_visibility="collapsed")
            if wahl != nr:
                st.session_state["ks_seite"] = wahl
                st.rerun()
            n3.button("▶", key="ks_vor", on_click=_ks_seite, args=(nr + 1,), disabled=nr >= seiten,
                      width="stretch", help="Nächste Seite")

        # Teilpunkte eines Werts der aktuellen Seite
        fokus = st.selectbox("Teilpunkte ansehen", range(len(teil)), key=f"ks_fokus_{art}_{nr}",
                             format_func=lambda i: f"#{teil[i]['rang']} {teil[i]['name']}")
        e = teil[fokus if fokus is not None and fokus < len(teil) else 0]
        b = e["bewertung"]
        _ks_tabelle([("Kriterium", "l"), ("Gewicht", "r"), ("Punkte", "r"), ("", "l")],
                    [[_h(t), f"{g} %", "keine Daten" if b["teile"].get(k) is None else _ks_de(b["teile"][k], 0),
                      f'<div class="ks-bahn"><div style="width:{b["teile"].get(k) or 0}%"></div></div>']
                     for k, t, g, _, _ in kriterien])
        if b["hinweise"]:
            st.caption(" · ".join(b["hinweise"]))

        pdf_schluessel = f"ks_pdf|{stand}|{signatur}"
        if st.button("📄 PDF der ganzen Liste erstellen", key="ks_pdf_knopf", width="stretch"):
            try:
                import wikifolio_pdf
                kopfzeile = (f"Stand {stand_txt} · {art_wahl} · {e_wahl} · Top {laenge} · {len(liste)} Werte"
                             + (f" · Suche „{begriff}“" if b_ else ""))
                st.session_state["ks_pdf"] = (pdf_schluessel, wikifolio_pdf.score_bericht(liste, art, kopfzeile))
            except ImportError:
                st.error("Für das PDF fehlt das Paket **reportlab** (requirements.txt).")
        fertig = st.session_state.get("ks_pdf")
        if fertig and fertig[0] == pdf_schluessel:
            st.download_button("⬇️ PDF herunterladen", data=fertig[1], mime="application/pdf",
                               file_name=f"{art}_Score_{datetime.date.today().isoformat()}.pdf",
                               key="ks_pdf_download", width="stretch")
        st.caption("Tabelle seitlich wischen für alle Kennzahlen – Rang und Name bleiben stehen. "
                   "Vergangene Entwicklung ist keine Prognose.")

    def _ks_tabelle(spalten, zeilen):
        kopf = "".join(f'<th class="{"pt-num" if a == "r" else "pt-wert"}">{t}</th>' for t, a in spalten)
        rumpf = "".join("<tr>" + "".join(f'<td class="{"pt-num" if a == "r" else ""}">{z}</td>'
                                         for z, (_, a) in zip(r, spalten)) + "</tr>" for r in zeilen)
        st.markdown(f'<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                    f'<table class="pt pt-kompakt ks-mini"><thead><tr>{kopf}</tr></thead>'
                    f'<tbody>{rumpf}</tbody></table></div>', unsafe_allow_html=True)

    @st.fragment
    def _render_top50():
        _zugang_pruefen("🏆 Watchlist Top 50")
        schritte.leiste(st, "watchlist")
        schritte.titel(st, "watchlist", 1)
        art = st.pills("Liste", ["🗂️ Gesamtübersicht", "⭐ Qualitäts-Score", "🏅 ETF- & wikifolio-Score",
                                 "🧭 Qualität × Kurs", "📈 Performance", "🧩 Wikifolios"],
                       default="🗂️ Gesamtübersicht", key="top50_art") or "🗂️ Gesamtübersicht"
        schritte.titel(st, "watchlist", 2, art.split(" ", 1)[-1])
        if art == "🏅 ETF- & wikifolio-Score":
            try:
                _render_klassen_score()
            except Exception as e:
                st.error(f"⚠️ Fehler in diesem Tab: {e}")
                notify_app_error("Tab-Klassen-Score", e)
            return
        if art == "🧩 Wikifolios":
            try:
                _render_wikifolios()
            except Exception as e:
                st.error(f"⚠️ Fehler in diesem Tab: {e}")
                notify_app_error("Tab-Wikifolios", e)
            return
        if art == "🧭 Qualität × Kurs":
            try:
                _render_qualitaet_kurs()
            except Exception as e:
                st.error(f"⚠️ Fehler in diesem Tab: {e}")
                notify_app_error("Tab-QualitaetKurs", e)
            return
        if art == "📈 Performance":
            _render_performance()
            return
        if art == "🗂️ Gesamtübersicht":
            try:
                _render_uebersicht()
            except Exception as e:
                st.error(f"⚠️ Fehler in diesem Tab: {e}")
                notify_app_error("Tab-Uebersicht", e)
            return
        try:
            _render_qualitaet()
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Qualitaet", e)

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

    # --- ALTERSTEILZEIT & RENTENPLANUNG (atz_rechner/ + atz_ui.py) - eigenstaendiger Rechner; den Depotwert
    # liest er nur (letzter Stand der Depot-Ansicht in dieser App-Instanz), er veraendert nichts
    if gewaehlte_ansicht == ANSICHT_ATZ:
        def _atz_depotwert():
            if not _sichtbar(ANSICHT_DEPOT):
                return None
            return (_depot_kurzinfo_speicher().get(st.session_state.get("login_name") or "_") or {}).get("wert")

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
            waehlbar = [a for a in ANSICHTEN if a != ANSICHT_BENUTZER]
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

    if gewaehlte_ansicht == "📝 Trader-Log (Trades & Kommentare)":
        melde("ansicht", 0.3, "Lade Chronik …")
        render_chronik()
        lade_fertig()

    # Watchlist und Portfolio-Planer brauchen keine Depot- oder Kursdaten -
    # dort endet der Aufbau hier, ohne Live-Kurs, Historie und Vergleichswerte.
    if gewaehlte_ansicht is None or gewaehlte_ansicht in LEICHTE_ANSICHTEN:
        lade_fertig()
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
    def lade_benchmarks_mit_fortschritt(df_index, start_datum, kapital, hinweis="Lade Vergleichswerte"):
        """Laedt alle Vergleichswerte und zeigt dabei einen zentrierten
        Fortschrittsbalken mit Prozentangabe. Gibt (series_dict, startdaten_dict)
        zurueck. Die Anzeige wird am Ende restlos entfernt."""
        series, startdaten = {}, {}
        items = [(vergleich_label(e), str(e["instrument_id"])) for e in lade_vergleichswerte()]
        gesamt = len(items)
        melde("benchmarks", 0.0, f"{hinweis} … ({gesamt} Werte)")
        vergleichswerte_vorladen([i for _, i in items])
        for i, (label, inst_id) in enumerate(items):
            melde("benchmarks", i / gesamt if gesamt else 1.0,
                  f"{hinweis} … ({i + 1}/{gesamt}) · {label}")
            s, erstes_datum = benchmark_normiert_auf_startkapital(
                df_index, inst_id, start_datum, heute_date, kapital
            )
            if s is not None:
                series[label] = s
                startdaten[label] = erstes_datum
        return series, startdaten

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
        """eintraege: Liste von (label, emoji) Tupeln. Fuer NICHT abwaehlbare
        Linien (Startkapital, eigenes Zertifikat) - einfacher Text mit
        Emoji-Symbol, garantiert einzeilig auf jeder Bildschirmbreite."""
        for label, emoji in eintraege:
            st.write(f"{emoji} {label}")

    def lese_pills_auswahl_still(labels, key):
        """Wie pills_auswahl(), aber OHNE das Widget zu rendern - liest nur
        den zuletzt gespeicherten Auswahlzustand (Standard: alle an). Fuer
        die Performance-Tabelle, die VOR dem sichtbaren Auswahl-Bereich
        steht, aber trotzdem die aktuelle Auswahl beruecksichtigen soll."""
        optionen = [f"{config.BENCHMARK_EMOJI.get(label, '⚪')} {label}" for label in labels]
        gespeichert = st.session_state.get(key, optionen)
        praefix_map = {opt: label for opt, label in zip(optionen, labels)}
        return [praefix_map[opt] for opt in gespeichert if opt in praefix_map]

    def pills_auswahl(labels, key):
        """Mehrfachauswahl per st.pills (anklickbare 'Pillen'-Buttons) statt
        Checkboxen - komplett anderes Widget ohne Checkbox-Innenleben, das
        sich per CSS nicht anpassen liess (moegliches Shadow-DOM). Emoji
        stecken direkt im Options-Text, keine separate Farbzuordnung noetig.
        Gibt die Liste der aktuell ausgewaehlten (reinen) Labels zurueck."""
        optionen = [f"{config.BENCHMARK_EMOJI.get(label, '⚪')} {label}" for label in labels]
        ausgewaehlt = st.pills(
            "Vergleichswerte im Chart anzeigen",
            optionen, selection_mode="multi", default=optionen, key=key,
        )
        ausgewaehlt = ausgewaehlt or []
        praefix_map = {opt: label for opt, label in zip(optionen, labels)}
        return [praefix_map[opt] for opt in ausgewaehlt]

    def pct_ueber_tage(reihe, tage):
        """Prozentuale Veraenderung einer Wertreihe ueber die letzten N Tage.
        Gibt None zurueck, wenn die Reihe nicht weit genug zurueckreicht - dann
        bleibt die Tabellenzelle leer, statt einen zu kurzen Zeitraum als
        Quartals-/Halbjahreswert auszugeben."""
        if reihe is None:
            return None
        gueltig = reihe.dropna()
        if gueltig.empty:
            return None
        stichtag = gueltig.index[-1] - pd.Timedelta(days=tage)
        davor = gueltig[gueltig.index <= stichtag]
        if davor.empty:
            return None
        # Toleranz: der Stichtag darf auf ein Wochenende/Feiertag fallen,
        # aber die Reihe muss wirklich bis in seine Naehe zurueckreichen.
        if (stichtag - davor.index[-1]).days > 10:
            return None
        basis = float(davor.iloc[-1])
        if not basis:
            return None
        return (float(gueltig.iloc[-1]) / basis - 1) * 100

    def kennzahl_umschalter(key, eintraege):
        """Waehlt, WELCHE Kennzahl auf schmalen Bildschirmen in der
        Vergleichstabelle steht. Am Desktop sind ohnehin alle Spalten
        sichtbar - dort dient der Umschalter nur der Hervorhebung.

        Bewusst st.pills statt eines Dropdowns: die Auswahl ist dauerhaft
        sichtbar, ein Tap genuegt, und man sieht sofort, welche
        Vergleichsmoeglichkeiten es ueberhaupt gibt."""
        moeglich = [("Ø/Jahr", "jaehrlich"), ("Ø/Mon.", "monatlich"), ("Gesamt", "perf")]
        if not any(e.get("_jaehrlich") is not None for e in eintraege):
            # Audit DEP-08: unter 1 Jahr kein Ø/Jahr -> Gesamtrendite als Vorauswahl
            moeglich = [("Gesamt", "perf"), ("Ø/Mon.", "monatlich"), ("Ø/Jahr", "jaehrlich")]
        for k, titel in [("_q", "3 Mon."), ("_h", "6 Mon."),
                         ("_n", "9 Mon."), ("_z", "12 Mon.")]:
            if any(e.get(k) is not None for e in eintraege):
                moeglich.append((titel, k))
        moeglich.append(("+/- €", "euro"))

        beschriftungen = [b for b, _ in moeglich]
        schritte.titel(st, "vergleich", 2)
        wahl = st.pills("Vergleichen nach", beschriftungen,
                        default=beschriftungen[0], key=key)
        zuordnung = dict(moeglich)
        return zuordnung.get(wahl or beschriftungen[0], moeglich[0][1])

    def performance_tabelle_html(eintraege, eigene_kennung=None, fokus="jaehrlich"):
        """Baut die Vergleichstabelle. Bewusst eine gemeinsame Funktion fuer
        alle drei Ansichten - vorher stand derselbe HTML-Block dreimal fast
        identisch im Code.

        Verbesserungen gegenueber der frueheren Fassung:
        - Zeitraum-Spalten ohne einen einzigen Wert werden WEGGELASSEN. Bei
          jungen Produkten waren "9 Mon." und "12 Mon." komplett leer und
          haben nur Breite gekostet.
        - Zebra-Streifen und Trennlinien zwischen den Spaltengruppen machen
          lange Zeilen ueber die ganze Breite verfolgbar.
        - Die eigene Position ist farblich hervorgehoben - sie ist der
          Bezugspunkt, alles andere ist Vergleich.
        - Name und WKN uebereinander statt nebeneinander: spart Breite und
          verhindert den unruhigen Zeilenumbruch mitten im Namen.
        - Zahlen in Tabellenziffern (Monospace), damit die Nachkommastellen
          untereinander stehen.
        """
        if not eintraege:
            return ""

        # Nur Zeitraum-Spalten zeigen, die mindestens einen Wert haben.
        zeitraeume = [("_q", "3 Mon."), ("_h", "6 Mon."),
                      ("_n", "9 Mon."), ("_z", "12 Mon.")]
        aktive_zeitraeume = [
            (key, titel) for key, titel in zeitraeume
            if any(e.get(key) is not None for e in eintraege)
        ]

        def zelle(wert, fett=False, klein=False, label="", spalte=""):
            """spalte kennzeichnet die Kennzahl (z.B. "jaehrlich") - auf
            schmalen Bildschirmen blendet das CSS alle bis auf die gewaehlte
            aus, damit die Tabelle ohne seitliches Scrollen vergleichbar
            bleibt."""
            attr = f' data-label="{label}" data-spalte="{spalte}"'
            if wert is None:
                return f'<td class="pt-num pt-leer"{attr}>–</td>'
            farbe = "pt-up" if wert >= 0 else "pt-down"
            klassen = f"pt-num {farbe}" + (" pt-stark" if fett else "") + (" pt-klein" if klein else "")
            return f'<td class="{klassen}"{attr}>{vz_zahl(wert, 2)} %</td>'

        zeilen = ""
        for i, e in enumerate(eintraege):
            ist_eigene = eigene_kennung and eigene_kennung in str(e.get("Wert", ""))
            zeilen_klasse = "pt-eigene" if ist_eigene else ("pt-zebra" if i % 2 else "")

            # Name und WKN trennen: "MSCI World (A0RPWH)" -> zwei Zeilen
            roh = str(e.get("Wert", ""))
            m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", roh)
            name, kuerzel = (m.group(1), m.group(2)) if m else (roh, "")

            euro = e.get("_euro")
            euro_klasse = "pt-up" if (euro or 0) >= 0 else "pt-down"
            seit = e.get("_gelistet_seit")
            seit_txt = seit.strftime("%d.%m.%y") if seit else "–"

            zeilen += (
                f'<tr class="{zeilen_klasse}">'
                f'<td class="pt-wert"><span class="pt-name">{_h(name)}</span></td>'
                + zelle(e.get("_monatlich"), fett=True, label="Ø/Mon.", spalte="monatlich")
                + zelle(e.get("_jaehrlich"), fett=True, label="Ø/Jahr", spalte="jaehrlich")
                + zelle(e.get("_perf"), fett=True, label="Gesamt", spalte="perf")
                + "".join(zelle(e.get(k), fett=True, label=titel, spalte=k)
                          for k, titel in aktive_zeitraeume)
                + f'<td class="pt-num pt-stark {euro_klasse}" data-label="+/- €" data-spalte="euro">{fmt(euro or 0, 0)}</td>'
                + f'<td class="pt-num pt-wknval" data-label="WKN" data-spalte="wkn">{_h(kuerzel) or "–"}</td>'
                + f'<td class="pt-num pt-seit" data-label="seit" data-spalte="seit">{seit_txt}</td>'
                '</tr>'
            )

        kopf = (
            '<th class="pt-wert">Wert</th>'
            '<th class="pt-num" data-spalte="monatlich">Ø/Mon.</th>'
              '<th class="pt-num" data-spalte="jaehrlich">Ø/Jahr</th>'
              '<th class="pt-num" data-spalte="perf">Gesamt</th>'
            + "".join(f'<th class="pt-num" data-spalte="{k}">{t}</th>'
                      for k, t in aktive_zeitraeume)
            + '<th class="pt-num" data-spalte="euro">+/- €</th>'
              '<th class="pt-num" data-spalte="wkn">WKN</th>'
              '<th class="pt-num" data-spalte="seit">seit</th>'
        )
        # Die Fokus-Klasse steuert per CSS, welche Kennzahl auf schmalen
        # Bildschirmen sichtbar ist (am Desktop sind ohnehin alle zu sehen).
        return (f'<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-fokus-{fokus}">'
                f'<thead><tr>{kopf}</tr></thead><tbody>{zeilen}</tbody></table></div>')

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
        """Deutsche Schreibweise (zentral: formate.zahl) - bewusst nur auf den ZAHLENWERT
        angewendet, nicht auf das umgebende HTML. Kurse mit 2 Nachkommastellen (UX 10/2026:
        "150,000 €" las sich wie 150 Tausend)."""
        return FMT.zahl(wert, nachkomma)

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
    def instrument_suchblock(prefix, label="WKN, ISIN oder Name suchen"):
        """Wiederverwendbarer Suchblock. Muss AUSSERHALB eines st.form stehen,
        da Formulare erst beim Submit einen Rerun ausloesen - die Suche soll
        aber sofort reagieren. Sucht bei Eingabe (Enter/Verlassen des Felds),
        ohne extra Klick. Gibt den gewaehlten Treffer als dict zurueck (oder None).

        prefix trennt die session_state-Keys, damit jede Position ihren
        eigenen, unabhaengigen Suchzustand hat."""
        # Schluessel mit Zaehler: nach dem Speichern bekommt das Feld einen neuen Schluessel und ist
        # wirklich leer - sonst schickt der Browser den alten Begriff erneut und das naechste
        # Formular uebernaehme wieder WKN/Kursquelle des alten Treffers (360°-Pruefung F-04)
        suchbegriff = st.text_input(
            label, key=f"{prefix}_suche_{st.session_state.get(f'{prefix}_nr', 0)}",
            placeholder="z. B. A0LC12, IE00B4L5Y983 oder MSCI World",
        )

        # Nur neu suchen, wenn sich der Begriff geaendert hat - sonst wuerde
        # jeder Rerun (z.B. durch ein anderes Widget) erneut suchen.
        if suchbegriff and st.session_state.get(f"{prefix}_letzter") != suchbegriff:
            st.session_state[f"{prefix}_letzter"] = suchbegriff
            st.session_state[f"{prefix}_treffer"] = suche_instrument(suchbegriff)
            st.session_state.pop(f"{prefix}_wahl", None)

        if not suchbegriff:
            return None

        treffer = st.session_state.get(f"{prefix}_treffer", [])
        if not treffer:
            st.caption("⚠️ Keine Treffer – Schreibweise prüfen oder die Kursquelle-ID manuell eintragen.")
            return None

        optionen = {
            f"{t['name']} · {t['kategorie']} · WKN {t['wkn'] or '–'}": t
            for t in treffer
        }
        wahl = st.selectbox("Treffer auswählen", list(optionen.keys()), key=f"{prefix}_wahl")
        gewaehlt = optionen[wahl]

        live_kurs, _, _ = get_live_kurs(gewaehlt["instrument_id"])
        kurs_txt = f"{FMT.eur(live_kurs, 2)}" if live_kurs else "kein Kurs verfügbar"
        st.caption(
            f"→ **{gewaehlt['name']}** · ID {gewaehlt['instrument_id']} · "
            f"ISIN {gewaehlt['isin'] or '–'} · aktuell {kurs_txt}"
        )
        return gewaehlt

    def suche_zuruecksetzen(prefix):
        """Suchblock leeren (neues, leeres Suchfeld; Treffer und Auswahl vergessen)."""
        for k in (f"{prefix}_letzter", f"{prefix}_treffer", f"{prefix}_wahl"):
            st.session_state.pop(k, None)
        st.session_state[f"{prefix}_nr"] = st.session_state.get(f"{prefix}_nr", 0) + 1

    def positions_anlage_formular(prefix):
        """Neue Position anlegen (Suche + Formular). prefix trennt die Schluessel - das
        Formular steht in den Einstellungen ("neu") und im leeren Depot ("leer")."""
        gewaehlt = instrument_suchblock(prefix)
        # Schluessel haengen am gewaehlten Treffer - so uebernimmt das Formular eine neue
        # Suche als Vorbelegung (gleiches Muster wie beim Bearbeiten)
        sfx = f"{prefix}_{gewaehlt['instrument_id'] if gewaehlt else 0}"

        with st.form(f"pos_form_{prefix}", clear_on_submit=True):
            neu_name = st.text_input(
                "Name", value=(gewaehlt["name"] if gewaehlt else ""),
                placeholder="z. B. MSCI World ETF", key=f"{sfx}_f_name")
            neu_wkn = st.text_input(
                "WKN / ISIN",
                value=(gewaehlt["wkn"] or gewaehlt["isin"]) if gewaehlt else "",
                placeholder="z. B. A0RPWH", key=f"{sfx}_f_wkn")
            neu_inst = st.number_input(
                "Kursquelle-ID (wird über die Suche gesetzt, optional)", min_value=0, step=1,
                value=int(gewaehlt["instrument_id"]) if gewaehlt else 0,
                help="Wird durch die Suche oben automatisch gefüllt. Kann auch leer "
                     "(0) bleiben - dann werden für diese Position keine Kurse geladen "
                     "und sie zählt nicht in die Depot-Summe. Jederzeit nachtragbar.",
                key=f"{sfx}_f_inst",
            )
            neu_datum = st.date_input("Kaufdatum", value=heute_date, key=f"{prefix}_f_datum", format="DD.MM.YYYY")
            neu_kurs = st.number_input("Kaufkurs (€)", min_value=0.0, step=0.01, format="%.4f", value=0.0,
                                       key=f"{prefix}_f_kurs")
            neu_kapital = st.number_input("Investiertes Kapital (€)", min_value=0.0, step=100.0, value=0.0,
                                          key=f"{prefix}_f_kapital")

            if st.form_submit_button("➕ Position anlegen", width="stretch"):
                if not neu_name or neu_kurs <= 0 or neu_kapital <= 0:
                    st.error("Bitte Name, Kaufkurs und Kapital ausfüllen.")
                else:
                    # Instrument-ID, falls angegeben, vor dem Speichern pruefen -
                    # verhindert stumme Fehlkonfiguration. Ohne ID wird die
                    # Position angelegt und spaeter als "keine Kursquelle" markiert.
                    test_kurs = None
                    if neu_inst:
                        test_kurs, _, _ = get_live_kurs(int(neu_inst))

                    if neu_inst and test_kurs is None:
                        st.error(
                            f"Für die Kursquelle-ID {int(neu_inst)} liefert ls-tc.de keine Kursdaten. "
                            "Bitte die ID prüfen – oder das Feld leer (0) lassen und später nachtragen."
                        )
                    else:
                        _p_anlage = {
                            "id": f"pos-{uuid.uuid4().hex[:12]}",     # eindeutig, auch bei zwei Anlagen je Sekunde
                            "name": neu_name, "wkn": neu_wkn,
                            "instrument_id": int(neu_inst) if neu_inst else None,
                            "kaufdatum": neu_datum.isoformat(), "kaufkurs": float(neu_kurs),
                            "startkapital": float(neu_kapital),
                        }
                        if aendere_positionen(lambda l: l + [_p_anlage], "position angelegt [skip ci]"):
                            suche_zuruecksetzen(prefix)
                            if test_kurs is not None:
                                st.success(f"„{neu_name}“ angelegt (aktueller Kurs {FMT.eur(test_kurs, 2)}).")
                            else:
                                st.success(f"„{neu_name}“ angelegt – ohne Kursquelle. "
                                           "Kursquelle-ID kann oben jederzeit ergänzt werden.")
                            st.rerun()
                        else:
                            st.error("Anlegen fehlgeschlagen (kein persistenter State?).")

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
        """Baut eine Kurskachel im selben Aufbau wie die Hauptkachel, aber fuer
        einen reinen Beobachtungswert. Höchststand wird hier aus der geladenen
        Historie bestimmt (kein persistenter State noetig) - fuer einen Wert,
        den man nicht besitzt, ist die Performance Fee ohnehin irrelevant."""
        if fortschritt:
            fortschritt(35, "Rufe Live-Kurs ab …")
        b_kurs, b_vortag, _ = get_live_kurs(eintrag["instrument_id"])
        if b_kurs is None:
            return (
                '<div class="quote">'
                f'<div class="q-name">{_h(eintrag.get("name", ""))} · {_h(eintrag.get("wkn", ""))}</div>'
                '<div class="price-line">'
                '<span class="q-price">–</span>'
                '<span class="meta-chip">keine Live-Daten</span>'
                '</div>'
                '<div class="card-footnote">ls-tc.de liefert für diesen Wert gerade '
                'keine Kurse. Kursquelle-ID prüfen oder später erneut versuchen.</div>'
                '</div>'
            )

        if fortschritt:
            fortschritt(65, "Lade Kurshistorie …")
        b_hist = get_kurshistorie(
            eintrag["instrument_id"], heute_date - datetime.timedelta(days=420), heute_date
        )
        if fortschritt:
            fortschritt(90, "Berechne Zeiträume …")
        b_perioden = berechne_zeitraeume(b_kurs, b_vortag, b_hist, heute_date)

        b_hw_zeile = ""
        if not b_hist.empty:
            b_hoch = float(b_hist.max())
            b_hoch_datum = b_hist.idxmax().strftime("%d.%m.%Y")
            b_abstand_pct = (b_kurs - b_hoch) / b_hoch * 100 if b_hoch else 0.0
            b_wert_html = ('<span class="up">erreicht</span>' if b_abstand_pct >= -0.0005
                           else f'<span class="down">{FMT.pct(b_abstand_pct, 2)}</span>')
            b_hw_zeile = (
                '<div class="perf-row"><span class="perf-label">Höchststand</span>'
                f'<span class="perf-vals"><span class="neutral">{FMT.eur(b_hoch, 2)}</span>'
                f'{b_wert_html}</span></div>'
            )
            b_fuss = (f'Lang &amp; Schwarz · je Anteil · Höchststand vom {b_hoch_datum} '
                      f'(aus verfügbarer Kurshistorie)')
        else:
            b_fuss = 'Lang &amp; Schwarz · je Anteil'
        if not im_depot:
            b_fuss += ' · nicht im Depot enthalten'

        return depot_kachel_html(
            f'{_h(eintrag.get("name", ""))} · {_h(eintrag.get("wkn", ""))}', FMT.kurs(b_kurs),
            chips=kurs_pill(*kurs_status(kurs_zeitpunkt(eintrag["instrument_id"]), now_berlin, True))
            + ('' if im_depot else '<span class="meta-chip">Beobachtung</span>'),
            zeilen=b_perioden, kopfzeile=("Vortag", FMT.kurs(b_vortag)) if b_vortag else None,
            fusszeile=b_hw_zeile, fussnote=b_fuss, klasse="quote", wert_klasse="q-price", titel_klasse="q-name")

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
    prognose_basis_liste = [e for e in lade_prognose_basis() if e.get("instrument_id")]
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
        gesamt_gewinn = gesamt_wert + gesamt_ausgezahlt - gesamt_einstand
        gesamt_rendite = (gesamt_gewinn / gesamt_einstand * 100) if gesamt_einstand else 0.0

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
                    ok, _ = gh_aktualisiere(upfad(config.STATE_PATH_SPARPLAN), lambda d: {}, default={},
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
                    ok, neu = gh_aktualisiere(
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
                ok, _ = gh_aktualisiere(upfad(STATE_PATH_ENTNAHME),
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
        """Eigene Vergleichswerte (Vermoegensaufbau, Performance seit 2026/2021): aus der Top-500-Liste oder per
        Suche hinzufuegen, wieder entfernen - je Benutzer gespeichert."""
        liste = lade_vergleichswerte()
        schritte.leiste(st, "vergleich")
        schritte.titel(st, "vergleich", 1)
        with st.expander(f"⭐ Vergleichswerte verwalten ({len(liste)})", expanded=offen):
            st.caption("Deine Vergleichswerte – gespeichert und in allen Vergleichs-Charts verwendet. Aus der "
                       f"Top-500-Liste übernehmen oder einen beliebigen Wert suchen. Höchstens "
                       f"{PROG_BASIS.MAX_EINTRAEGE} Werte.")
            optionen = [w for w in top500_prognose_optionen() if not PROG_BASIS.enthalten(liste, w)]

            def _hinzu(w):
                if not w.get("instrument_id"):                     # Kurs-ID fehlt: exakte Suche ueber WKN/ISIN
                    import investment_scanner_pro_engine as PRO
                    t, art = PRO.treffer_waehlen(w, suche_instrument(w.get("isin") or w.get("wkn") or w["name"]) or [])
                    w["instrument_id"] = int(t["instrument_id"]) if t and art == "exakt" else None
                if not w.get("instrument_id"):
                    st.error(f"Für „{w['name']}“ wurde keine Kursquelle gefunden – nicht hinzugefügt.")
                elif aendere_vergleichswerte(lambda l: PROG_BASIS.hinzufuegen(l, PROG_BASIS.eintrag(w, time.time())),
                                             "vergleichswert hinzugefuegt [skip ci]"):
                    for k in ("vgl_wahl", "vgl_such", "vgl_treffer"):
                        st.session_state.pop(k, None)
                    st.rerun()
                else:
                    st.error("Nicht gespeichert – schon in der Liste, Liste voll oder Speicher gerade nicht "
                             "erreichbar.")

            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            wahl = c1.selectbox(
                f"Aus der Top-500-Liste ({len(optionen)} Werte)", range(len(optionen)), index=None,
                format_func=lambda i: " · ".join(x for x in (optionen[i]["name"], PROG_BASIS.ARTEN[optionen[i]["art"]],
                                                             optionen[i]["wkn"] or optionen[i]["isin"]) if x),
                placeholder="Name, WKN oder ISIN eintippen …", key="vgl_wahl")
            if c2.button("➕ Hinzufügen", key="vgl_add", disabled=wahl is None, type="primary", width="stretch"):
                _hinzu(dict(optionen[wahl]))
            begriff = st.text_input("Oder eigenen Wert suchen (Name, WKN oder ISIN)", key="vgl_such",
                                    placeholder="z. B. Siemens, 723610, LS9…").strip()
            if len(begriff) >= 2:
                treffer = [t for t in (suche_instrument(begriff) or [])[:12] if t.get("instrument_id")]
                if not treffer:
                    st.caption("Keine Treffer – andere Schreibweise oder WKN/ISIN versuchen.")
                else:
                    t1, t2 = st.columns([4, 1], vertical_alignment="bottom")
                    t = t1.selectbox("Treffer", treffer, key="vgl_treffer", format_func=lambda t: " · ".join(
                        x for x in (t.get("name"), t.get("wkn") or t.get("isin"), t.get("kategorie")) if x))
                    if t2.button("➕ Hinzufügen", key="vgl_add_such", type="primary", width="stretch"):
                        _hinzu({"name": t.get("name") or begriff, "wkn": t.get("wkn") or "",
                                "isin": t.get("isin") or "", "instrument_id": int(t["instrument_id"])})
            for e in liste:
                z1, z2 = st.columns([5, 1], vertical_alignment="center")
                z1.markdown(f"**{_h(vergleich_label(e))}**")
                if z2.button("🗑️ Entfernen", key=f"vgl_weg_{e.get('id')}", width="stretch"):
                    if aendere_vergleichswerte(lambda l, _id=e.get("id"): PROG_BASIS.entfernen(l, _id),
                                               "vergleichswert entfernt [skip ci]"):
                        st.rerun()
                    else:
                        st.error("Entfernen fehlgeschlagen (Speicher gerade nicht erreichbar).")

    def _render_vergleich_eigen():
        """Vermoegensaufbau fuer Benutzer ohne Hauptposition: eigene Vergleichswerte, symbolisch angelegt ab
        einem waehlbaren Datum."""
        with tab_wealth:
            werte = lade_vergleichswerte()
            _vergleichswerte_verwalten(offen=not werte)
            if not werte:
                st.info("📈 Noch keine Vergleichswerte – oben aus der Top-500-Liste übernehmen oder einen Wert "
                        "suchen. Sie werden gespeichert und lassen sich jederzeit wieder entfernen.")
                return
            KAPITAL = 10000.0
            c1, _ = st.columns([1, 2])
            ab = c1.date_input("Vergleich ab", value=heute_date - datetime.timedelta(days=365),
                               max_value=heute_date - datetime.timedelta(days=7), key="vgl_ab", format="DD.MM.YYYY")
            idx = pd.bdate_range(pd.Timestamp(ab), pd.Timestamp(heute_date))
            series, startdaten = lade_benchmarks_mit_fortschritt(idx, ab, KAPITAL)
            if not series:
                st.warning("Für die gewählten Werte liegen gerade keine Kursdaten vor – bitte später mit 🔄 erneut laden.")
                return
            liste = []
            for label, s_ in series.items():
                g = s_.dropna()
                if g.empty or g.iloc[0] <= 0:
                    continue
                start_ = startdaten.get(label)
                start_ = start_.date() if hasattr(start_, "date") else ab
                gesamt, monatlich, jaehrlich, diff = berechne_performance_kennzahlen(g.iloc[0], g.iloc[-1], start_,
                                                                                      heute_date)
                liste.append({"Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich,
                              "_euro": diff, "_q": pct_ueber_tage(g, 91), "_h": pct_ueber_tage(g, 182),
                              "_n": pct_ueber_tage(g, 273), "_z": pct_ueber_tage(g, 365), "_gelistet_seit": start_})
            st.caption(f"📅 Symbolisch {fmt(KAPITAL, 0)} je Wert, angelegt am {ab.strftime('%d.%m.%Y')} "
                       "(spätere Auflage: ab dem ersten Kurs) · Ø/Jahr erst ab 1 Jahr, Ø/Mon. ab 30 Tagen")
            liste.sort(key=perf_sortierwert, reverse=True)
            _fokus = kennzahl_umschalter("fokus_vgl_eigen", liste)
            st.markdown(performance_tabelle_html(liste, fokus=_fokus), unsafe_allow_html=True)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=idx, y=[KAPITAL] * len(idx), name="Startkapital",
                                     line=dict(color="#71717A", width=1.5, dash="dash")))
            for i, (label, s_) in enumerate(series.items()):
                fig.add_trace(go.Scatter(x=idx, y=s_, name=label, line=dict(color=vergleich_farbe(label, i), width=2)))
            fig.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40),
                              height=450, showlegend=True, legend=dict(orientation="h", y=-0.15),
                              xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                              yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"),
                                         ticksuffix=" €"),
                              hovermode="x unified")
            schritte.titel(st, "vergleich", 3)
            st.plotly_chart(UI.chart_stil(fig), width="stretch", key="chart_vgl_eigen", config={"displayModeBar": False})

    def _render_wealth():
        try:
            with tab_wealth:
                _vergleichswerte_verwalten()
                if not is_live_history:
                    st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – der Vermögensverlauf "
                               "kann nicht gezeichnet werden. Bitte später mit 🔄 erneut laden.")
                    return
                # Auswahl still aus dem gespeicherten Zustand lesen (Standard: alle an) -
                # der sichtbare Auswahl-Bereich selbst steht weiter unten, direkt vor dem Chart.
                ausgewaehlte_benchmarks = lese_pills_auswahl_still(benchmark_series.keys(), key="benchmark_pills")

                performance_liste_haupt = []
                kurs_reihe = df_chart["Close"]
                # Eigene Zeile = dieselben Zahlen wie die Depotkachel (Audit A-08/A-09/A-12):
                # Gesamt/Ø gegen den Einstand inkl. Sparraten, Ergebnis inkl. ausgezahlter
                # Entnahmen. Die Zeitraum-Spalten zeigen - wie bei den Vergleichswerten - die
                # Kursentwicklung (Ein-/Auszahlungen wuerden sie sonst verzerren).
                if not kurs_reihe.empty and einstand_aktiv > 0:
                    gesamt, monatlich, jaehrlich, _ = berechne_performance_kennzahlen(
                        einstand_aktiv, depotwert_real_ist + ausgezahlt_ist, kaufdatum_aktiv, heute_date
                    )
                    # Ø/Jahr und Ø/Monat aus derselben (geldgewichteten) Rendite wie die Kachel
                    jaehrlich = rendite_pa_real if not rendite_pa_hochgerechnet else None
                    monatlich = (((1 + rendite_pa_real / 100) ** (1 / 12) - 1) * 100
                                 if rendite_pa_real is not None else None)
                    performance_liste_haupt.append({
                        "Wert": f"{haupt_name} ({config.WKN})",
                        "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": gewinn_real,
                        "_q": pct_ueber_tage(kurs_reihe, 91),
                        "_h": pct_ueber_tage(kurs_reihe, 182),
                        "_n": pct_ueber_tage(kurs_reihe, 273),
                        "_z": pct_ueber_tage(kurs_reihe, 365),
                        "_gelistet_seit": kaufdatum_aktiv,
                    })
                for label, s in benchmark_series.items():
                    s_gueltig = s.dropna()
                    if label in ausgewaehlte_benchmarks and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                        start_dieser_wert = benchmark_start_daten.get(label)
                        start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else kaufdatum_aktiv
                        gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                            s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                        )
                        performance_liste_haupt.append({
                            "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                            "_q": pct_ueber_tage(s_gueltig, 91),
                            "_h": pct_ueber_tage(s_gueltig, 182),
                            "_n": pct_ueber_tage(s_gueltig, 273),
                            "_z": pct_ueber_tage(s_gueltig, 365),
                            "_gelistet_seit": start_dieser_wert,
                        })

                if performance_liste_haupt:
                    # Tatsaechliches Startdatum der geladenen Reihe mit ausweisen -
                    # weicht es vom Kaufdatum ab, ist das ein Hinweis darauf, dass
                    # die Vergleichslinien einen anderen Zeitraum abdecken.
                    _daten_start = df_chart.index.min()
                    _start_hinweis = ""
                    if _daten_start is not None and _daten_start.date() != kaufdatum_aktiv:
                        _start_hinweis = f" · Kursdaten ab {_daten_start.strftime('%d.%m.%Y')}"
                    # kurz sichtbar, die Rechenregeln hinter dem "?" (UX 10/2026: der lange Text stand am Handy
                    # mit 8 Zeilen vor der Tabelle)
                    st.caption(
                        f"📅 Eigene Position ab Kaufdatum {kaufdatum_aktiv.strftime('%d.%m.%Y')}{_start_hinweis}",
                        help="Berechnet ab dem Kaufdatum gegen das eingesetzte Kapital"
                        + (f", inkl. Sparraten (Einstand {fmt(einstand_aktiv, 0)})" if sparplan_eingezahlt > 0 else "")
                        + (f", inkl. ausgezahlter Entnahmen ({fmt(ausgezahlt_ist, 0)})" if ausgezahlt_ist > 0 else "")
                        + ". 3–12 Mon.: reine Kursentwicklung. Ø/Jahr erst ab 1 Jahr Laufzeit, Ø/Mon. ab 30 Tagen "
                        "(sonst „–“).")
                    performance_liste_haupt.sort(key=perf_sortierwert, reverse=True)   # DEP-08: ohne Ø/Jahr nach Gesamt
                    _fokus = kennzahl_umschalter("fokus_haupt", performance_liste_haupt)
                    st.markdown(
                        performance_tabelle_html(performance_liste_haupt, eigene_kennung=config.WKN,
                                                 fokus=_fokus),
                        unsafe_allow_html=True,
                    )

                with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                    st.caption(
                        "„Depotwert“ ist der reale Wert nach den monatlichen Entnahmen: je Termin werden "
                        f"Anteile für {fmt(entnahme_rate, 2)} zum Geldkurs verkauft (Spread-Annahme "
                        f"{FMT.pct(config.SPREAD_PCT, 2)}), Sparplan-Käufe ab ihrem Kauftag. "
                        "„Eingezahlt“ = Startkapital plus Sparraten. Die Vergleichslinien zeigen, wie sich "
                        f"{fmt(startkapital_aktiv, 0)} im selben Zeitraum in gängigen Vergleichs-ETFs "
                        "entwickelt hätten (Kosten der ETFs bereits im Kurs enthalten, keine Steuern)."
                    )
                    zeige_chart_legende_liste([("Eingezahlt", "⚪"), (f"Depotwert {haupt_name} ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series.keys(), key="benchmark_pills")

                fig_wealth = go.Figure()
                fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Eingezahlt"], name="Eingezahlt", line=dict(color="#71717A", width=1.5, dash="dash")))
                fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Real"], name="Depotwert", line=dict(color=UI.AKZENT, width=2.5)))

                legende_eintraege = [("Eingezahlt", "#71717A"), (f"Depotwert {haupt_name} ({config.WKN})", UI.AKZENT)]
                for label, s in benchmark_series.items():
                    if label not in ausgewaehlte_benchmarks:
                        continue
                    farbe = vergleich_farbe(label, list(benchmark_series).index(label))
                    fig_wealth.add_trace(go.Scatter(
                        x=df_chart.index, y=s, name=label,
                        line=dict(color=farbe, width=1.5, dash="dashdot"),
                    ))
                    legende_eintraege.append((label, farbe))
    
                fig_wealth.update_layout(
                    paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=80, b=40), height=450,
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"),
                               ticksuffix=" €"),
                    hovermode="x unified",
                )
                schritte.titel(st, "vergleich", 3)
                st.plotly_chart(UI.chart_stil(fig_wealth, flaeche="Depotwert"), width="stretch", key="chart_wealth", config={"displayModeBar": False})

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Vermoegensaufbau", e)
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
        try:
            with tab_ytd:
                _vergleichswerte_verwalten()
                if not is_live_history:
                    st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – die Linie des Zertifikats "
                               "fehlt. Bitte später mit 🔄 erneut laden.")
                    return
                v2_start = pd.Timestamp(config.VERGLEICH2_START_DATUM)
                v2_kapital = config.VERGLEICH2_STARTKAPITAL

                # Eigenes Zertifikat: aus bereits geladenem df_chart ab v2_start neu skalieren
                eigene_reihe_v2 = df_chart["Close"][df_chart.index >= v2_start]
                if not eigene_reihe_v2.empty and eigene_reihe_v2.iloc[0] > 0:
                    eigene_reihe_v2 = eigene_reihe_v2 / eigene_reihe_v2.iloc[0] * v2_kapital

                # Benchmarks: eigener, frischer Abruf ab v2_start (eigene Cache-Zeile,
                # da anderer Startzeitpunkt als der Hauptvergleich oben)
                benchmark_series_v2, benchmark_start_daten_v2 = lade_benchmarks_mit_fortschritt(
                    eigene_reihe_v2.index, config.VERGLEICH2_START_DATUM, v2_kapital
                )

                # Auswahl still aus dem gespeicherten Zustand lesen - der sichtbare
                # Auswahl-Bereich steht weiter unten, direkt vor dem Chart.
                ausgewaehlte_v2 = lese_pills_auswahl_still(benchmark_series_v2.keys(), key="benchmark_v2_pills")

                fig_v2 = go.Figure()
                fig_v2.add_trace(go.Scatter(
                    x=eigene_reihe_v2.index, y=[v2_kapital] * len(eigene_reihe_v2),
                    name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash"),
                ))
                fig_v2.add_trace(go.Scatter(
                    x=eigene_reihe_v2.index, y=eigene_reihe_v2, name=f"{haupt_name} ({config.WKN})",
                    line=dict(color=UI.AKZENT, width=2.5),
                ))
                benchmark_colors_v2 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
                legende_eintraege_v2 = [("Startkapital", "#71717A"), (f"{haupt_name} ({config.WKN})", UI.AKZENT)]
                for i, (label, s) in enumerate(benchmark_series_v2.items()):
                    if label not in ausgewaehlte_v2:
                        continue
                    farbe_v2 = vergleich_farbe(label, list(benchmark_series_v2).index(label))
                    fig_v2.add_trace(go.Scatter(
                        x=eigene_reihe_v2.index, y=s, name=label,
                        line=dict(color=farbe_v2, width=1.5, dash="dashdot"),
                    ))
                    legende_eintraege_v2.append((label, farbe_v2))

                fig_v2.update_layout(
                    paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=40, b=40), height=450,
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=1000),
                    hovermode="x unified",
                )
                performance_liste_v2 = []
                if not eigene_reihe_v2.empty and eigene_reihe_v2.iloc[0] > 0:
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        eigene_reihe_v2.iloc[0], eigene_reihe_v2.iloc[-1], config.VERGLEICH2_START_DATUM, heute_date
                    )
                    performance_liste_v2.append({
                        "Wert": f"{haupt_name} ({config.WKN})",
                        "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_q": pct_ueber_tage(eigene_reihe_v2, 91),
                        "_h": pct_ueber_tage(eigene_reihe_v2, 182),
                        "_n": pct_ueber_tage(eigene_reihe_v2, 273),
                        "_z": pct_ueber_tage(eigene_reihe_v2, 365),
                        "_gelistet_seit": config.VERGLEICH2_START_DATUM,
                    })
                for label, s in benchmark_series_v2.items():
                    s_gueltig = s.dropna()
                    if label in ausgewaehlte_v2 and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                        start_dieser_wert = benchmark_start_daten_v2.get(label)
                        start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else config.VERGLEICH2_START_DATUM
                        gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                            s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                        )
                        performance_liste_v2.append({
                            "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                            "_q": pct_ueber_tage(s_gueltig, 91),
                            "_h": pct_ueber_tage(s_gueltig, 182),
                            "_n": pct_ueber_tage(s_gueltig, 273),
                            "_z": pct_ueber_tage(s_gueltig, 365),
                            "_gelistet_seit": start_dieser_wert,
                        })

                if performance_liste_v2:
                    st.caption(f"📅 Berechnet seit {config.VERGLEICH2_START_DATUM.strftime('%d.%m.%Y')}")
                    performance_liste_v2.sort(key=perf_sortierwert, reverse=True)   # DEP-08: ohne Ø/Jahr nach Gesamt
                    _fokus = kennzahl_umschalter("fokus_v2", performance_liste_v2)
                    st.markdown(
                        performance_tabelle_html(performance_liste_v2, eigene_kennung=config.WKN,
                                                 fokus=_fokus),
                        unsafe_allow_html=True,
                    )

                with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                    st.caption(
                        f"Alle Werte neu skaliert: {fmt(v2_kapital, 0)} investiert am "
                        f"{config.VERGLEICH2_START_DATUM.strftime('%d.%m.%Y')}, unabhängig vom "
                        "eigentlichen Kaufdatum deines Zertifikats - zeigt die reine "
                        "Performance seit Jahresanfang im direkten Vergleich."
                    )
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"{haupt_name} ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series_v2.keys(), key="benchmark_v2_pills")

                schritte.titel(st, "vergleich", 3)
                st.plotly_chart(UI.chart_stil(fig_v2, flaeche=f"{haupt_name} ({config.WKN})"), width="stretch", key="chart_ytd", config={"displayModeBar": False})

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Seit-2026", e)
    if gewaehlte_ansicht == "🔍 Seit 01.01.2026":
        melde("ansicht", 0.3, "Lade Vergleich seit 2026 …")
        _render_ytd()
        lade_fertig()

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _render_2021():
        try:
            with tab_2021:
                _vergleichswerte_verwalten()
                v3_start = pd.Timestamp(config.VERGLEICH3_START_DATUM)
                v3_kapital = config.VERGLEICH3_STARTKAPITAL
                master_index_v3 = pd.bdate_range(start=v3_start, end=pd.Timestamp(heute_date))

                # Eigenes Zertifikat: EIGENER, frischer Abruf ab 2021 (df_chart
                # reicht nur bis zum echten Kaufdatum zurueck, hier brauchen wir
                # ggf. deutlich mehr Historie). Wichtig: die Benchmarks werden
                # NICHT auf den (ggf. kuerzeren) Zeitraum des Zertifikats
                # zugeschnitten - sie laufen ueber den vollen 2021-Zeitraum,
                # nur die Zertifikat-Linie beginnt ggf. spaeter (echte Luecke).
                df_chart_v3, _v3_quelle = get_historical_market_data(config.VERGLEICH3_START_DATUM, heute_date)
                v3_echt = _v3_quelle != KEINE_HISTORIE              # Audit A-06: keine Ersatzreihen
                if v3_echt and is_live_data:                        # DEP-10: gleicher letzter Tag wie Vergleichswerte
                    df_chart_v3 = haenge_live_punkt_an(df_chart_v3, kurs_tag, aktueller_kurs)
                if not v3_echt:
                    st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – die Linie des Zertifikats "
                               "fehlt. Bitte später mit 🔄 erneut laden.")
                roh_eigen_v3 = df_chart_v3["Close"] if not df_chart_v3.empty else pd.Series(dtype=float)

                tatsaechlicher_start_v3 = roh_eigen_v3.index.min() if not roh_eigen_v3.empty else None

                if not roh_eigen_v3.empty and roh_eigen_v3.iloc[0] > 0:
                    skaliert_eigen_v3 = roh_eigen_v3 / roh_eigen_v3.iloc[0] * v3_kapital
                    # Auf vollen Zeitindex bringen, aber NUR nach vorne auffuellen -
                    # vor dem echten Start bleibt es NaN (keine erfundene Rueckrechnung)
                    eigene_reihe_v3 = skaliert_eigen_v3.reindex(master_index_v3).ffill()
                else:
                    eigene_reihe_v3 = pd.Series(index=master_index_v3, dtype=float)

                benchmark_series_v3, benchmark_start_daten_v3 = lade_benchmarks_mit_fortschritt(
                    master_index_v3, config.VERGLEICH3_START_DATUM, v3_kapital
                )

                # Auswahl still aus dem gespeicherten Zustand lesen - der sichtbare
                # Auswahl-Bereich steht weiter unten, direkt vor dem Chart.
                ausgewaehlte_v3 = lese_pills_auswahl_still(benchmark_series_v3.keys(), key="benchmark_v3_pills")

                fig_v3 = go.Figure()
                fig_v3.add_trace(go.Scatter(
                    x=master_index_v3, y=[v3_kapital] * len(master_index_v3),
                    name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash"),
                ))
                fig_v3.add_trace(go.Scatter(
                    x=eigene_reihe_v3.index, y=eigene_reihe_v3,
                    name=f"{haupt_name} ({config.WKN})",
                    line=dict(color=UI.AKZENT, width=2.5),
                ))
                benchmark_colors_v3 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
                legende_eintraege_v3 = [("Startkapital", "#71717A"), (f"{haupt_name} ({config.WKN})", UI.AKZENT)]
                for i, (label, s) in enumerate(benchmark_series_v3.items()):
                    if label not in ausgewaehlte_v3:
                        continue
                    farbe_v3 = vergleich_farbe(label, list(benchmark_series_v3).index(label))
                    fig_v3.add_trace(go.Scatter(
                        x=master_index_v3, y=s, name=label,
                        line=dict(color=farbe_v3, width=1.5, dash="dashdot"),
                    ))
                    legende_eintraege_v3.append((label, farbe_v3))

                fig_v3.update_layout(
                    paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=40, b=40), height=450,
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=2000),
                    hovermode="x unified",
                )
                performance_liste_v3 = []
                if not roh_eigen_v3.empty and roh_eigen_v3.iloc[0] > 0:
                    start_datum_eigen_v3 = tatsaechlicher_start_v3.date() if tatsaechlicher_start_v3 is not None else config.VERGLEICH3_START_DATUM
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        roh_eigen_v3.iloc[0], roh_eigen_v3.iloc[-1], start_datum_eigen_v3, heute_date
                    )
                    performance_liste_v3.append({
                        "Wert": f"{haupt_name} ({config.WKN})",
                        "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_q": pct_ueber_tage(roh_eigen_v3, 91),
                        "_h": pct_ueber_tage(roh_eigen_v3, 182),
                        "_n": pct_ueber_tage(roh_eigen_v3, 273),
                        "_z": pct_ueber_tage(roh_eigen_v3, 365),
                        "_gelistet_seit": start_datum_eigen_v3,
                    })
                for label, s in benchmark_series_v3.items():
                    s_gueltig = s.dropna()
                    if label in ausgewaehlte_v3 and not s_gueltig.empty and s_gueltig.iloc[0] > 0:
                        start_dieser_wert = benchmark_start_daten_v3.get(label)
                        start_dieser_wert = start_dieser_wert.date() if hasattr(start_dieser_wert, "date") else config.VERGLEICH3_START_DATUM
                        gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                            s_gueltig.iloc[0], s_gueltig.iloc[-1], start_dieser_wert, heute_date
                        )
                        performance_liste_v3.append({
                            "Wert": label, "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                            "_q": pct_ueber_tage(s_gueltig, 91),
                            "_h": pct_ueber_tage(s_gueltig, 182),
                            "_n": pct_ueber_tage(s_gueltig, 273),
                            "_z": pct_ueber_tage(s_gueltig, 365),
                            "_gelistet_seit": start_dieser_wert,
                        })

                if performance_liste_v3:
                    st.caption(f"📅 Berechnet seit {config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')} (bzw. erstem verfügbaren Kurs)")
                    performance_liste_v3.sort(key=perf_sortierwert, reverse=True)   # DEP-08: ohne Ø/Jahr nach Gesamt
                    _fokus = kennzahl_umschalter("fokus_v3", performance_liste_v3)
                    st.markdown(
                        performance_tabelle_html(performance_liste_v3, eigene_kennung=config.WKN,
                                                 fokus=_fokus),
                        unsafe_allow_html=True,
                    )

                with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                    st.caption(
                        f"Alle Werte neu skaliert: {fmt(v3_kapital, 0)} investiert am "
                        f"{config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')}, unabhängig vom "
                        "eigentlichen Kaufdatum deines Zertifikats."
                    )
                    if tatsaechlicher_start_v3 is not None and tatsaechlicher_start_v3 > v3_start:
                        st.info(
                            f"ℹ️ Für {config.WKN} liegen erst ab {tatsaechlicher_start_v3.strftime('%d.%m.%Y')} "
                            "Kursdaten vor (vermutlich Auflegungsdatum des Zertifikats) - die Linie beginnt "
                            "entsprechend später als die Vergleichswerte, keine erfundenen Daten. Die "
                            "Vergleichswerte selbst laufen trotzdem über den vollen Zeitraum seit "
                            f"{config.VERGLEICH3_START_DATUM.strftime('%d.%m.%Y')}."
                        )
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"{haupt_name} ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series_v3.keys(), key="benchmark_v3_pills")

                schritte.titel(st, "vergleich", 3)
                st.plotly_chart(UI.chart_stil(fig_v3, flaeche=f"{haupt_name} ({config.WKN})"), width="stretch", key="chart_2021", config={"displayModeBar": False})

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Seit-2021", e)
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
        try:
            with tab_candle:
                if not is_live_history:
                    st.warning("⚠️ ls-tc.de liefert gerade keine Kurshistorie – die Linie des Zertifikats "
                               "fehlt. Bitte später mit 🔄 erneut laden.")
                    return
                fig_c = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart["Open"], high=df_chart["High"], low=df_chart["Low"], close=df_chart["Close"], increasing_line_color="#34D399", decreasing_line_color="#F87171")])
                fig_c.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40), height=450, xaxis=dict(showgrid=True, gridcolor="#1A1A1A"), yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", dtick=10), showlegend=False)
                schritte.leiste(st, "candle")
                schritte.titel(st, "candle", 1)
                st.plotly_chart(UI.chart_stil(fig_c), width="stretch", key="chart_candlestick", config={"displayModeBar": False})
                schritte.titel(st, "candle", 2)
                st.caption(
                    "Basiert auf ls-tc.de Tages-Schlusskursen (Open/High/Low approximiert). "
                    "Der GitHub-Actions-Cron protokolliert seit Kurzem zusätzlich alle 5 Min den "
                    "echten Kurs in state/price_history/ — daraus lässt sich künftig ein echter "
                    "Intraday-Chart bauen, sobald genug Historie gesammelt ist."
                )

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Candlestick", e)
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
        """Eigene Prognose-Basis: Werte aus der Top-500-Liste uebernehmen und wieder entfernen."""
        liste = lade_prognose_basis()
        with st.expander(f"⭐ Prognose-Basis verwalten ({len(liste)} eigene Werte)",
                         expanded=not prognose_optionen):
            st.caption("Werte aus der Top-500-Liste übernehmen – sie erscheinen in „Prognose Basis auswählen“ "
                       "(symbolisch 10.000 €, angelegt ab heute). Deine Depot-Positionen sind immer dabei. "
                       f"Höchstens {PROG_BASIS.MAX_EINTRAEGE} eigene Werte.")
            optionen = [w for w in top500_prognose_optionen() if not PROG_BASIS.enthalten(liste, w)]

            def _beschriftung(i):
                w = optionen[i]
                return " · ".join(x for x in (w["name"], PROG_BASIS.ARTEN[w["art"]], w["wkn"] or w["isin"]) if x)

            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            wahl = c1.selectbox(f"Aus der Top-500-Liste ({len(optionen)} Werte)", range(len(optionen)), index=None,
                                format_func=_beschriftung, placeholder="Name, WKN oder ISIN eintippen …",
                                key="prog_basis_wahl")
            if c2.button("➕ Hinzufügen", key="prog_basis_add", disabled=wahl is None, type="primary",
                         width="stretch"):
                w = dict(optionen[wahl])
                if not w["instrument_id"]:              # Kurs-ID nicht in den Top-500-Daten: exakte Suche
                    import investment_scanner_pro_engine as PRO
                    t, art = PRO.treffer_waehlen(w, suche_instrument(w["isin"] or w["wkn"] or w["name"]) or [])
                    w["instrument_id"] = int(t["instrument_id"]) if t and art == "exakt" else None
                if not w["instrument_id"]:
                    st.error(f"Für „{w['name']}“ wurde keine Kursquelle gefunden – nicht hinzugefügt.")
                elif aendere_prognose_basis(
                        lambda l: PROG_BASIS.hinzufuegen(l, PROG_BASIS.eintrag(w, time.time())),
                        "prognose-basis hinzugefuegt [skip ci]"):
                    st.session_state.pop("prog_basis_wahl", None)
                    st.rerun()
                else:
                    st.error("Nicht gespeichert – schon in der Liste, Liste voll oder Speicher gerade nicht "
                             "erreichbar.")
            for e in liste:
                z1, z2 = st.columns([5, 1], vertical_alignment="center")
                z1.markdown(f"**{_h(e.get('name', ''))}** · {_h(e.get('wkn') or e.get('isin') or '')}")
                if z2.button("🗑️ Entfernen", key=f"prog_basis_weg_{e.get('id')}", width="stretch"):
                    if aendere_prognose_basis(lambda l, _id=e.get("id"): PROG_BASIS.entfernen(l, _id),
                                              "prognose-basis entfernt [skip ci]"):
                        st.rerun()
                    else:
                        st.error("Entfernen fehlgeschlagen (Speicher gerade nicht erreichbar).")

    @st.fragment
    def _render_forecast():
        _zugang_pruefen("🔮 Zukunfts-Prognose")
        schritte.leiste(st, "prognose")
        schritte.titel(st, "prognose", 1)
        _prognose_basis_verwalten()
        if not prognose_optionen:
            # normaler Benutzer ohne eigene Positionen/Prognose-Werte
            st.info("🔮 Noch kein eigenes Depot – lege im 🏠 Depot deine erste Position an "
                    "oder übernimm oben Werte aus der Top-500-Liste, dann erscheint hier die Prognose.")
            return
        try:
            # Ab der zweiten Position eine Auswahl anbieten - bei nur einer
            # Position (Standardfall) waere ein Dropdown mit einem einzigen
            # Eintrag nur ueberfluessiger Klick.
            if len(prognose_optionen) > 1:
                # Gleiches Muster wie bei "Ansicht wählen": eigene
                # .abschnitt-Ueberschrift, natives Label per CSS (nicht
                # per Streamlit-"collapsed") ausgeblendet - siehe
                # Kommentar dort. "help" bewusst entfernt: der kleine
                # weisse Kreis daneben wirkte wie ein Darstellungsfehler.
                st.markdown(
                    '<div class="abschnitt abschnitt-marker-prognose">Prognose Basis auswählen:</div>',
                    unsafe_allow_html=True,
                )
                namen = [o["name"] for o in prognose_optionen]
                gewaehlter_name = st.selectbox(
                    "Prognose Basis auswählen:", namen, **_startauswahl("prognose_wert_wahl", namen),
                    key="prognose_wert_wahl",
                )
                opt = next(o for o in prognose_optionen if o["name"] == gewaehlter_name)
            else:
                opt = prognose_optionen[0]

            opt_startkapital = opt["startkapital"]
            opt_aktueller_wert = opt["aktueller_wert"]
            opt_kaufdatum = opt["kaufdatum"]
            opt_sparrate = opt["sparrate"]
            opt_entnahme = opt["entnahme"]                         # Rate je Monat
            opt_entnommen = float(opt.get("entnommen_bisher") or 0.0)  # bisher seit Kauf
            # Audit DEP-01: Gewinn gegen den Einstand (Startkapital + eingezahlte Sparraten)
            opt_einstand = float(opt.get("einstand", opt_startkapital))
            # Audit A-12: aktueller_wert ist der Wert NACH den echten Entnahmen; das bereits
            # ausgezahlte Geld gehoert zum Ergebnis.
            opt_gewinn = opt_aktueller_wert + opt_entnommen - opt_einstand

            _default_key = f"prognose_rate_{opt['name']}"
            schritte.titel(st, "prognose", 2)
            opt_cagr_pa = st.number_input(
                "Angenommene Rendite p.a. (%) für diese Prognose",
                min_value=-99.0, max_value=100000.0, step=0.5,
                **_startwert(_default_key, round(opt["cagr_pa"], 2)), key=_default_key,
                help="Vorbelegt mit der aus der Kurshistorie ermittelten Rate. "
                     "Frei überschreibbar, um andere Annahmen durchzurechnen.",
            )
            opt_zins_mo = (1 + (opt_cagr_pa / 100.0)) ** (1 / 12) - 1

            _opt_rueckfall = opt.get("cagr_rueckfall_hinweis")
            if _opt_rueckfall:
                # Produkt-Historie zu kurz -> Rate aus dem eigenen Kauf (Nutzerentscheid DEP-08)
                st.caption(f"⚠️ Vorbelegte Rate {opt['cagr_pa']:+.2f} % p.a.: {_opt_rueckfall}.")
            elif opt.get("cagr_details"):
                with st.expander("Wie wurde die vorbelegte Rate ermittelt?", expanded=False):
                    st.caption("Grundlage ist ein **Trend über die gesamte Historie** (Regression durch alle Kurspunkte) plus Zeitfenster **ab 6 Monaten**, daraus der Median. Kürzere Fenster bleiben bewusst außen vor: ein Monat hochgerechnet multipliziert das Zufallsrauschen mit zwölf. Bei kurzer Historie wird das Ergebnis zusätzlich Richtung einer konservativen Marktrendite gedämpft, weil sich aus wenigen Monaten keine verlässliche Jahresrate ablesen lässt.")
                    for _label, _wert in opt["cagr_details"]:
                        st.write(f"- {_label}: **{_wert:+.2f}% p.a.**")
                    st.write(f"→ Verwendet: **{opt['cagr_pa']:+.2f}% p.a.**")

            sparrate_hinweis = f" Zusätzlich wird eine monatliche Sparrate von **{fmt(opt_sparrate, 2)}** eingerechnet." if opt_sparrate > 0 else ""
            if opt.get("symbolisch"):
                _cagr_seit = opt.get("cagr_seit")
                _seit_hinweis = (
                    f" Kursdaten liegen seit {_cagr_seit.strftime('%d.%m.%Y')} vor."
                    if _cagr_seit else ""
                )
                st.caption(
                    f"Dieser Wert ist nur eine Beobachtung, kein echtes Investment. "
                    f"Die Rechnung unterstellt ein **symbolisches** Startkapital von "
                    f"{fmt(opt_startkapital, 0)}, das **heute** ({opt_kaufdatum.strftime('%d.%m.%Y')}) "
                    f"angelegt würde - keine reale Position.{_seit_hinweis}{sparrate_hinweis}"
                )
            elif sparrate_hinweis:
                st.caption(sparrate_hinweis.strip())

            # Die Prognose startet immer HEUTE mit dem heutigen Depotwert: Gewinn und Entnahmen
            # zaehlen ab heute (der bisherige Gewinn steht darunter als Hinweis).
            forecast_data = [
                {"Jahr": "Start (heute)", "Datum": heute_date.strftime("%d.%m.%Y"), "Gewinn ab heute": fmt_vz(0.0),
                 "Depotwert": fmt(opt_aktueller_wert, 2), "Kumulierte Entnahme": fmt(0.0, 2)}
            ]
            if not opt.get("symbolisch"):
                st.caption(f"Bisher seit Kauf ({opt_kaufdatum.strftime('%d.%m.%Y')}): Gewinn {fmt_vz(opt_gewinn)}"
                           + (f", entnommen {fmt(opt_entnommen, 2)}" if opt_entnommen else "")
                           + " – die Prognose unten rechnet ab heute.")

            # Fortschreibung mit ECHTEN Entnahmen (Audit A-12): jede Entnahme verlaesst das Depot
            # und verzinst sich nicht weiter; Sparraten erhoehen den Einsatz (DEP-01).
            # Gewinn ab heute = Depotwert + ab heute Ausgezahltes - (heutiger Wert + Sparraten).
            sim_w_prog, sim_e_prog = opt_aktueller_wert, 0.0
            sim_einstand = opt_aktueller_wert
            milestone_added = opt_aktueller_wert >= 100000.0

            for m_idx in range(1, 121):
                _entn = min(opt_entnahme, max(sim_w_prog * (1 + opt_zins_mo) + opt_sparrate, 0.0))
                sim_w_prog = max(sim_w_prog * (1 + opt_zins_mo) + opt_sparrate - _entn, 0.0)
                sim_einstand += opt_sparrate
                sim_e_prog += _entn
    
                current_date = now_berlin.replace(tzinfo=None) + pd.DateOffset(months=m_idx)
    
                if not milestone_added and sim_w_prog >= 100000.0:
                    forecast_data.append({
                        "Jahr": "100k",
                        "Datum": current_date.strftime("%d.%m.%Y"),
                        "Gewinn ab heute": fmt_vz(sim_w_prog + sim_e_prog - sim_einstand),
                        "Depotwert": fmt(sim_w_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                    })
                    milestone_added = True

                if m_idx % 12 == 0:
                    forecast_data.append({
                        "Jahr": f"Jahr +{m_idx // 12}",
                        "Datum": current_date.strftime("%d.%m.%Y"),
                        "Gewinn ab heute": fmt_vz(sim_w_prog + sim_e_prog - sim_einstand),
                        "Depotwert": fmt(sim_w_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                    })
        
            df_forecast = pd.DataFrame(forecast_data)

            # Ohne Entnahme ist "Kumulierte Entnahme" durchgehend 0 und kostet
            # auf dem Smartphone nur seitliche Scrollbreite.
            if not opt_entnahme:
                df_forecast = df_forecast.drop(columns=["Kumulierte Entnahme"], errors="ignore")

            schritte.titel(st, "prognose", 3)
            # Hoehe an die tatsaechliche Zeilenzahl anpassen: st.dataframe
            # begrenzt sonst auf ~10 Zeilen und scrollt INNERHALB der
            # Tabelle - auf dem Smartphone unangenehm, weil man dann zwei
            # verschachtelte Scrollbereiche hat und das Ende nicht sieht.
            # 35px je Zeile + 38px Kopfzeile entspricht Streamlits Raster.
            _tabellen_hoehe = 38 + 35 * len(df_forecast)
            st.dataframe(
                df_forecast, width="stretch", hide_index=True, key="df_forecast",
                height=_tabellen_hoehe,
                column_config={
                    # Jetzt wieder "small": "Jahr +10" ist der laengste
                    # Eintrag, seit "🎯 100k Meilenstein" zu "100k" gekuerzt
                    # wurde - spart Breite fuer die Betrags-Spalten.
                    "Jahr": st.column_config.TextColumn("Jahr", width="small"),
                    "Datum": st.column_config.TextColumn("Datum", width="small"),
                    # Betraege sind fertig deutsch formatiert (1.234,56 €) - rechtsbuendig wie Zahlen
                    **{s_: st.column_config.TextColumn(s_, alignment="right")
                       for s_ in ("Gewinn ab heute", "Depotwert", "Kumulierte Entnahme") if s_ in df_forecast.columns},
                },
            )
            with st.expander("ℹ️ Tipp zur Tabelle", expanded=False):
                st.caption("Ein Tippen auf einen Spaltenkopf sortiert die Tabelle - "
                           "erneutes Tippen stellt die ursprüngliche Reihenfolge wieder her.")

            # ---------- BANDBREITE STATT EINER EINZELNEN ZAHL ----------
            # Die Tabelle oben rechnet mit EINER konstanten Rendite. Das
            # ist leicht lesbar, verschweigt aber die Unsicherheit. Hier
            # daher zusaetzlich eine Monte-Carlo-Simulation: tausende
            # moegliche Verlaeufe auf Basis der tatsaechlichen
            # Volatilitaet der Kursreihe.
            schritte.titel(st, "prognose", 4, "Bandbreite möglicher Verläufe")

            mc_jahre = st.slider("Zeitraum der Simulation (Jahre)", 1, 15, **_startwert("mc_jahre", 5),
                                 key="mc_jahre")
            mc_shrinkage = st.toggle(
                "Dämpfung bei kurzer Historie", **_startwert("mc_shrinkage", True), key="mc_shrinkage",
                help="Zieht den geschätzten Trend Richtung einer konservativen "
                     "Marktrendite (8 % p.a.) - je weniger Historie vorliegt, "
                     "desto stärker. Ohne Dämpfung wird ein kurzer Boom "
                     "ungebremst über Jahre fortgeschrieben.",
            )

            mc_perzentile, mc_kennzahlen = simuliere_bandbreite(
                startwert=opt_aktueller_wert,
                kursreihe=opt.get("kursreihe"),
                jahre=mc_jahre,
                sparrate_monat=opt_sparrate,
                entnahme_monat=opt_entnahme,
                shrinkage=mc_shrinkage,
            )

            if mc_perzentile is None:
                st.caption("Für diesen Wert liegen zu wenige Kursdaten für eine "
                           "Bandbreiten-Simulation vor (mindestens ~30 Handelstage nötig).")
            else:
                st.caption(
                    f"{mc_kennzahlen['pfade']:,} simulierte Verläufe über {mc_jahre} Jahre, "
                    f"basierend auf der tatsächlichen Schwankungsbreite dieses Wertes "
                    f"({mc_kennzahlen['vola_pa']:.0f} % Volatilität p.a.)."
                    .replace(",", ".")
                )

                b1, b2 = st.columns(2)
                b1.metric("Mittleres Ergebnis (Median)", fmt(mc_perzentile[50], 0))
                b2.metric("Wahrscheinlichkeit eines Verlusts",
                          f"{mc_kennzahlen['verlust_wahrscheinlichkeit']:.0f} %",
                          help="Anteil der Verläufe, die unter dem insgesamt eingesetzten Geld enden "
                               f"(heutiger Wert + Sparraten − Entnahmen = {fmt(mc_kennzahlen['eingesetzt'], 0)}).")

                st.markdown(
                    '<div class="rows">'
                    '<div class="row"><span class="row-label">Sehr schlecht (5 %)</span>'
                    f'<span class="row-val">{fmt(mc_perzentile[5], 0)}'
                    '<span class="row-note">Nur 5 % der Verläufe endeten darunter</span></span></div>'
                    '<div class="row"><span class="row-label">Schlechtes Viertel (25 %)</span>'
                    f'<span class="row-val">{fmt(mc_perzentile[25], 0)}</span></div>'
                    '<div class="row"><span class="row-label">Mitte (50 %)</span>'
                    f'<span class="row-val">{fmt(mc_perzentile[50], 0)}'
                    '<span class="row-note">Hälfte darüber, Hälfte darunter</span></span></div>'
                    '<div class="row"><span class="row-label">Gutes Viertel (75 %)</span>'
                    f'<span class="row-val">{fmt(mc_perzentile[75], 0)}</span></div>'
                    '<div class="row"><span class="row-label">Sehr gut (95 %)</span>'
                    f'<span class="row-val">{fmt(mc_perzentile[95], 0)}'
                    '<span class="row-note">Nur 5 % der Verläufe endeten darüber</span></span></div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

                with st.expander("Wie kommt diese Bandbreite zustande?", expanded=False):
                    st.write(
                        f"- Kursdaten vorhanden für: **{mc_kennzahlen['jahre_historie']:.1f} Jahre**"
                    )
                    st.write(
                        f"- Trend aus den Rohdaten: **{mc_kennzahlen['mu_roh_pa']:+.0f} % p.a.**"
                    )
                    if mc_shrinkage:
                        st.write(
                            f"- Nach Dämpfung verwendet: **{mc_kennzahlen['mu_verwendet_pa']:+.0f} % p.a.** "
                            f"(Gewicht auf eigene Daten: {mc_kennzahlen['gewicht_eigene_daten']:.0f} %, "
                            f"Rest Richtung 8 % Marktrendite)"
                        )
                    else:
                        st.write("- Dämpfung ist **aus**: der rohe Trend wird ungebremst fortgeschrieben.")
                    st.write(f"- Schwankungsbreite: **{mc_kennzahlen['vola_pa']:.0f} % p.a.**")
                    st.write("- Der verwendete Trend ist eine logarithmische Rate: ohne Ein-/Auszahlungen "
                             "wächst der **Median** genau mit dieser Rate p.a.; der Durchschnitt aller "
                             "Verläufe liegt wegen der Schwankung darüber.")
                    st.write(f"- Verlust heißt: Endwert unter dem eingesetzten Geld "
                             f"({fmt(mc_kennzahlen['eingesetzt'], 0)} = heutiger Wert + Sparraten − Entnahmen).")
                    st.caption(
                        "Auch das bleibt ein Modell: Es unterstellt, dass sich Schwankungen "
                        "künftig ähnlich verhalten wie bisher, und kennt weder Marktcrashs "
                        "noch Produktschließungen. Es zeigt aber ehrlicher als eine einzelne "
                        "Zahl, wie breit die möglichen Ausgänge auseinanderliegen."
                    )

            # Kurzer, immer sichtbarer Hinweis statt eines langen
            # Dauertextes - die ausfuehrliche Begruendung steht bei
            # Bedarf im Expander darunter (gleiches Muster wie
            # "Wie kommt diese Bandbreite zustande?" darueber).
            st.caption("⚠️ Fortschreibung der Vergangenheit, keine Vorhersage - "
                       "die künftige Rendite kann stark abweichen.")
            with st.expander("Warum ist das keine Vorhersage?", expanded=False):
                st.write(
                    "Diese Tabelle schreibt lediglich die Vergangenheit fort - sie "
                    "rechnet mit einer konstanten jährlichen Rendite weiter, in der "
                    "Realität schwankt jede Anlage. Besonders bei kurzer Haltedauer "
                    "oder einem einzelnen, zufällig günstigen/ungünstigen "
                    "Startzeitpunkt kann die historische Rate stark von der "
                    "künftigen abweichen. Passe den Wert oben gerne an, um eigene "
                    "(z. B. konservativere) Annahmen zu testen."
                )

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Prognose", e)
    if gewaehlte_ansicht == "🔮 Zukunfts-Prognose":
        melde("ansicht", 0.3, "Berechne Prognose …")
        _render_forecast()
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
        _zugang_pruefen("📊 Szenario-Simulator (5 Jahre)")
        try:
            st.markdown(
                '<div style="font-size: 1.05rem; font-weight: 800; color: #FFFFFF; margin-bottom: 4px;">'
                '📊 Szenario-Analyse (5 Jahre)</div>',
                unsafe_allow_html=True,
            )
            schritte.leiste(st, "szenario")
            schritte.titel(st, "szenario", 1)
            # ---------- BASIS: hinterlegten Wert oder eigene Eingabe ----------
            # Vorher rechnete der Simulator immer mit festen 10.000 € und
            # hatte keinerlei Bezug zu den Werten der App. Jetzt laesst sich
            # jeder Wert waehlen, der auch in der Zukunfts-Prognose steht
            # (Hauptposition, weitere Positionen, Beobachtungswerte). Die
            # Felder darunter werden damit vorbelegt, bleiben aber frei
            # aenderbar. Zusaetzlich erscheint die historische Rate dieses
            # Werts als eigenes, hervorgehobenes Szenario.
            # "Standard" = das urspruengliche Verhalten: feste 10.000 €,
            # nur die 7 Standard-Raten (-10 bis +30 % p.a.), ohne Bezug zu
            # einem bestimmten Wert und ohne historisches ⭐-Szenario.
            # Steht bewusst an erster Stelle und ist damit die Vorauswahl.
            STANDARD = "📐 Standard (−10 bis +30 % p.a., 10.000 €)"
            _basis_namen = [STANDARD] + [o["name"] for o in prognose_optionen]
            basis_name = st.selectbox(
                "Wert auswählen:", _basis_namen, **_startauswahl("szenario_basis_wahl", _basis_namen),
                key="szenario_basis_wahl",
            )
            basis = next((o for o in prognose_optionen if o["name"] == basis_name), None)

            if basis is not None:
                _vorbelegung = {
                    "start": float(basis["aktueller_wert"]),
                    "entnahme": float(basis.get("entnahme") or 0.0),
                    "sparrate": float(basis.get("sparrate") or 0.0),
                }
                if basis.get("symbolisch"):
                    st.caption(
                        "Beobachtungswert ohne echtes Investment - gerechnet wird mit "
                        f"einem symbolischen Startkapital von {fmt(_vorbelegung['start'], 0)}."
                    )
                else:
                    st.caption("Vorbelegt mit dem aktuellen Wert dieser Position - "
                               "unten frei anpassbar.")
            else:
                _vorbelegung = {"start": 10000.0, "entnahme": 0.0, "sparrate": 0.0}
                st.caption("Standard-Szenarien ohne Bezug zu einem bestimmten Wert - "
                           "alle Beträge unten frei anpassbar.")

            # Eigener Widget-Key je Auswahl: Streamlit uebernimmt "value="
            # nur beim ERSTEN Anlegen eines Widgets. Mit festem Key bliebe
            # beim Wechsel der alte Betrag stehen - so bekommt jede Auswahl
            # ihr eigenes Feld mit passender Vorbelegung, und eigene
            # Aenderungen bleiben je Wert erhalten.
            _k = re.sub(r"[^A-Za-z0-9]+", "_", basis_name)

            schritte.titel(st, "szenario", 2)
            col_sk, col_en = st.columns(2)
            with col_sk:
                startkapital_szenario = st.number_input(
                    "✏️ Startkapital (€)", min_value=0.0,
                    **_startwert(f"szenario_startkapital_{_k}", round(_vorbelegung["start"], 2)),
                    step=100.0, key=f"szenario_startkapital_{_k}",
                )
            with col_en:
                entnahme_eingabe = st.number_input(
                    "✏️ Monatliche Entnahme (€)", min_value=0.0,
                    **_startwert(f"szenario_entnahme_{_k}", _vorbelegung["entnahme"]),
                    step=10.0, key=f"szenario_entnahme_{_k}",
                )
            sparrate_szenario = st.number_input(
                "✏️ Monatliche Sparrate (€)", min_value=0.0,
                **_startwert(f"szenario_sparrate_{_k}", _vorbelegung["sparrate"]),
                step=10.0, key=f"szenario_sparrate_{_k}",
                help="Zusätzliche monatliche Einzahlung - erhöht das Kapital jeden Monat, statt es zu verringern.",
            )

            ohne_entnahme = st.toggle("Ohne monatliche Entnahme berechnen", **_startwert("szenario_ohne_entnahme", False),
                                  key="szenario_ohne_entnahme")
            entnahme_fuer_szenario = 0.0 if ohne_entnahme else entnahme_eingabe
            netto_cashflow_szenario = sparrate_szenario - entnahme_fuer_szenario

            # STANDARD (Audit A-15): sieben Jahresraten inkl. Verlust- und Nullszenario statt
            # 19 Raten von 12,7-213,8 % p.a. - die Bandbreite soll realistische Verlaeufe zeigen.
            # HINTERLEGTER WERT: nur EIN Szenario - die Rate dieses Werts.
            # Vorher liefen dort zusaetzlich alle 19 Standardraten mit, und
            # die eigentlich relevante Rate ging in der Liste unter. Die Rate
            # ist mit der historischen Rendite vorbelegt, aber editierbar,
            # damit sich auch konservativere Annahmen durchrechnen lassen.
            eigene_rate_mo = None
            if basis is None:
                szenario_raten_mo = [((1 + pa / 100.0) ** (1 / 12) - 1) * 100.0
                                     for pa in (-10.0, 0.0, 5.0, 10.0, 15.0, 20.0, 30.0)]
            else:
                # NEUEINSTIEG HEUTE: Die Rate kommt aus der Kurshistorie des
                # PRODUKTS, nicht aus dem eigenen Kauf. Der bisherige Wert
                # (basis["cagr_pa"]) misst bei eigenen Positionen Kurs gegen
                # den eigenen KAUFKURS - er haengt also am Einstiegszeitpunkt
                # und beantwortet die Frage "wie lief es fuer MICH bisher".
                # Fuer "was waere, wenn ich heute neu einsteige" zaehlt aber
                # die Entwicklung des Produkts selbst. Geladen wird dabei NUR
                # der gewaehlte Wert (gecacht) - nicht alle anderen.
                _inst_id = basis.get("instrument_id")
                _rate_quelle = "eigener Kauf"
                if basis.get("cagr_rueckfall_hinweis"):
                    # < 1 Jahr: hochgerechnete Ø-Monatsrendite bzw. 0 % - Herkunft nennen
                    _rate_quelle += ", " + basis["cagr_rueckfall_hinweis"].split(" – ")[0]
                _prod_pa = float(basis.get("cagr_pa") or 0.0)
                _details = []
                if _inst_id:
                    _p_hist = get_kurshistorie(
                        # Komplette Historie seit Auflegung (Start bei 100 €)
                        _inst_id, datetime.date(2000, 1, 1), heute_date
                    )

                    # AUFLEGUNG: ls-tc.de liefert die Historie erst ab Listing
                    # (LS9VFS: ab 09.07.2025 bei 128,80 €), obwohl das
                    # Zertifikat frueher bei 100 € startete. Dieser Abschnitt
                    # fehlt in den Daten - deshalb hier von Hand eintragbar.
                    _datenbeginn = (_p_hist.index[0].date() if not _p_hist.empty else heute_date)
                    _start_kurs_daten = (float(_p_hist.iloc[0]) if not _p_hist.empty else 100.0)
                    # NUR wikifolio-Zertifikate starten bei 100 € - bei ETFs
                    # (MSCI, Gold, Nasdaq ...) waere dieser Ankerpunkt falsch,
                    # deshalb gibt es die Eingabe dort gar nicht erst.
                    if ist_wikifolio(basis.get("wkn"), basis.get("name")):
                        with st.expander("Auflegung des Werts", expanded=False):
                            _gespeichert, _ = auflegung_fuer(_inst_id)
                            st.caption(
                                f"Kursdaten liegen erst ab **{_datenbeginn.strftime('%d.%m.%Y')}** "
                                f"({_start_kurs_daten:.2f} €) vor. wikifolio-Zertifikate starten "
                                f"immer bei **{WIKIFOLIO_STARTKURS:.0f} €** - trag das "
                                "Auflegungsdatum ein, dann zählt auch die Zeit davor mit. "
                                "Die Angabe wird dauerhaft gespeichert und gilt für Prognose, "
                                "Meilenstein und Simulator."
                            )
                            _auf_datum = st.date_input(
                                "Auflegungsdatum", format="DD.MM.YYYY", value=_gespeichert or _datenbeginn,
                                key=f"szenario_aufl_datum_{_k}",
                            )
                            _b1, _b2 = st.columns(2)
                            if _b1.button("Speichern", key=f"szenario_aufl_save_{_k}",
                                          width="stretch"):
                                if speichere_auflegung(_inst_id, _auf_datum):
                                    st.success(f"Auflegung {_auf_datum.strftime('%d.%m.%Y')} "
                                               f"zu {WIKIFOLIO_STARTKURS:.0f} € gespeichert.")
                                    st.rerun(scope="fragment")
                                else:
                                    st.error("Speichern fehlgeschlagen (kein persistenter State?).")
                            if _gespeichert and _b2.button("Entfernen",
                                                           key=f"szenario_aufl_del_{_k}",
                                                           width="stretch"):
                                if speichere_auflegung(_inst_id, None):
                                    st.rerun(scope="fragment")
                                else:
                                    st.error("Entfernen fehlgeschlagen - nichts geändert.")
                            if _gespeichert:
                                st.caption(f"Aktiv: Auflegung {_gespeichert.strftime('%d.%m.%Y')} "
                                           f"zu {WIKIFOLIO_STARTKURS:.0f} €.")

                    _daempfen = st.toggle(
                        "Dämpfung bei kurzer Historie", **_startwert(f"szenario_daempf_{_k}", False),
                        key=f"szenario_daempf_{_k}",
                        help="Zieht das Ergebnis Richtung einer konservativen Marktrendite "
                             "(8 % p.a.), je weniger Historie vorliegt. Aus = der ungefilterte "
                             "Median über alle Zeiträume.",
                    )

                    # Dieselbe zentrale Funktion wie 100k-Meilenstein und
                    # Zukunfts-Prognose - eine Quelle, ueberall dieselbe Zahl.
                    _robust, _details = produkt_rendite_pa(
                        _inst_id, heute_date, daempfung=_daempfen,
                    )
                    if _robust is not None:
                        _prod_pa = _robust
                        _rate_quelle = "Kursentwicklung des Produkts"

                rate_pa_szenario = st.number_input(
                    "✏️ Angenommene Rendite p.a. (%)",
                    min_value=-99.0, max_value=100000.0, step=0.5,
                    **_startwert(f"szenario_rate_{_k}", round(max(_prod_pa, -99.0), 2)), key=f"szenario_rate_{_k}",
                    help="Vorbelegt mit der bisherigen Entwicklung dieses Produkts - "
                         "unabhängig davon, wann du selbst gekauft hast. "
                         "Frei überschreibbar, um andere Annahmen durchzurechnen.",
                )
                eigene_rate_mo = ((1 + rate_pa_szenario / 100.0) ** (1 / 12) - 1) * 100.0
                szenario_raten_mo = [round(eigene_rate_mo, 4)]
                st.caption(
                    f"Gerechnet als Neueinstieg heute: {fmt(startkapital_szenario, 2)} zum "
                    f"{heute_date.strftime('%d.%m.%Y')}. Rendite-Vorgabe {_prod_pa:.2f} % p.a. "
                    f"= {((1 + _prod_pa / 100.0) ** (1 / 12) - 1) * 100:.2f} % p.M. "
                    f"(Quelle: {_rate_quelle}). Fortschreibung der Vergangenheit, keine Vorhersage."
                )
                if _details:
                    with st.expander("Wie wurde die Rendite-Vorgabe ermittelt?", expanded=False):
                        st.caption("Grundlage ist ein **Trend über die gesamte Historie** (Regression durch alle Kurspunkte) plus Zeitfenster **ab 6 Monaten**, daraus der Median. Kürzere Fenster bleiben bewusst außen vor: ein Monat hochgerechnet multipliziert das Zufallsrauschen mit zwölf. Bei kurzer Historie wird das Ergebnis zusätzlich Richtung einer konservativen Marktrendite gedämpft, weil sich aus wenigen Monaten keine verlässliche Jahresrate ablesen lässt.")
                        for _label, _wert in _details:
                            st.write(f"- {_label}: **{_wert:+.2f}% p.a.**")
                        st.write(f"→ Verwendet: **{_prod_pa:+.2f}% p.a.**")

            summary_list = []
            scenario_series = {}

            for r_mo_pct in szenario_raten_mo:
                r_mo = r_mo_pct / 100.0
                r_pa_pct = ((1 + r_mo) ** 12 - 1) * 100.0
                ist_eigene_rate = (eigene_rate_mo is not None
                                   and abs(r_mo_pct - round(eigene_rate_mo, 4)) < 1e-9)
    
                cap_sim = startkapital_szenario
                m_to_100k = None
                for m in range(1, 1200):
                    cap_sim = (cap_sim * (1 + r_mo)) + netto_cashflow_szenario
                    if cap_sim >= 100000.0:
                        m_to_100k = m
                        break

                monthly_vals = [startkapital_szenario]
                cap_5y = startkapital_szenario
                for m in range(1, 61):
                    cap_5y = (cap_5y * (1 + r_mo)) + netto_cashflow_szenario
                    monthly_vals.append(max(0, cap_5y))
        
                _serien_name = f"{FMT.pct(r_pa_pct, 1)} p.a. ({FMT.pct(r_mo_pct, 2)} p.M.)"
                if ist_eigene_rate:
                    _serien_name = f"⭐ {_h(basis_name)}: {_serien_name}"   # Plotly deutet Teile von HTML
                scenario_series[_serien_name] = monthly_vals

                if m_to_100k is not None:
                    years_100k = m_to_100k // 12
                    rem_months = m_to_100k % 12
                    m_str = f"🎯 {m_to_100k} Mon. ({years_100k}J {rem_months}M)"
                    # Ab HEUTE rechnen, nicht ab dem Kaufdatum: die
                    # Simulation startet mit dem heutigen Kapital und zeigt
                    # in die Zukunft. Vorher lagen alle Zieldaten um die
                    # bisherige Haltedauer zu frueh.
                    target_date = (pd.Timestamp(heute_date) + pd.DateOffset(months=m_to_100k)).strftime("%m/%Y")
                else:
                    m_str = "Nicht erreicht (>100J)"
                    target_date = "N/A"

                summary_list.append({
                    "eigene": ist_eigene_rate,
                    "rate": r_mo_pct, "rate_pa": r_pa_pct, "ziel_100k": m_str, "ziel_datum": target_date,
                    "j1": monthly_vals[12], "j2": monthly_vals[24], "j3": monthly_vals[36],
                    "j4": monthly_vals[48], "j5": monthly_vals[60],
                })

            karten_html = '<div style="display: flex; flex-direction: column; gap: 10px;">'
            for e in summary_list:
                # Historische Rate des gewaehlten Werts sichtbar absetzen
                _rahmen = ("2px solid #34D399; box-shadow: 0 0 12px rgba(52, 211, 153,0.25)"
                           if e["eigene"] else "1px solid var(--rand)")
                _marke = (f'<div style="font-size: 0.8rem; font-weight: 700; color: #34D399; '
                          f'letter-spacing: 0.6px; margin-bottom: 4px;">⭐ {_h(basis_name.upper())}</div>'
                          if e["eigene"] else "")
                # WICHTIG: HTML ohne Zeilenumbrueche/Einrueckung aufbauen.
                # In einem mehrzeiligen f-String entsteht bei leerem
                # {_marke} eine Leerzeile - Markdown wertet alles danach mit
                # 4+ Leerzeichen Einrueckung als CODEBLOCK und zeigt den
                # HTML-Quelltext als Text an (genau dieser Fehler trat auf).
                _jahre = "".join(
                    f'<div><div style="font-size: 0.8rem; color: #A1A1AA;">{j}J</div>'
                    f'<div style="font-size: clamp(0.68rem, 2.9vw, 0.8rem); color: #E5E7EB; font-weight: 700; overflow-wrap: anywhere;">{fmt(e[f"j{j}"], 0)}</div></div>'
                    for j in range(1, 6)
                )
                karten_html += (
                    f'<div style="background: var(--karte); border: {_rahmen}; border-radius: 16px; padding: 16px;">'
                    f'{_marke}'
                    f'<div style="font-size: 1rem; font-weight: 800; color: #FFFFFF; margin-bottom: 8px;">'
                    f'{FMT.pct(e["rate_pa"], 1)} p.a. <span style="color: #A1A1AA; font-weight: 600; font-size: 0.8rem;">({FMT.pct(e["rate"], 2)} p.M.)</span>'
                    f'</div>'
                    f'<div style="font-size: 0.85rem; color: #34D399; font-weight: 700; margin-bottom: 6px;">{e["ziel_100k"]}</div>'
                    f'<div style="font-size: 0.8rem; color: #CBD5E1; margin-bottom: 8px;">Ziel-Datum (100k): {e["ziel_datum"]}</div>'
                    f'<div style="display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; border-top: 1px solid var(--trenn); padding-top: 8px; font-variant-numeric: tabular-nums;">'
                    f'{_jahre}</div>'
                    f'</div>'
                )
            karten_html += "</div>"
            schritte.titel(st, "szenario", 3)
            st.markdown(karten_html, unsafe_allow_html=True)

            fig_scen = go.Figure()
            months_x = list(range(61))

            for label, vals in scenario_series.items():
                if label.startswith("⭐"):
                    fig_scen.add_trace(go.Scatter(
                        x=months_x, y=vals, mode="lines", name=label,
                        line=dict(color="#34D399", width=4),
                    ))
                else:
                    fig_scen.add_trace(go.Scatter(
                        x=months_x, y=vals, mode="lines", name=label,
                        line=dict(width=1.5), opacity=0.75,
                    ))

            fig_scen.add_hline(
                y=100000, 
                line_dash="dot", 
                line_color="#34D399", 
                annotation_text="🎯 100k Zielwert", 
                annotation_position="top left",
                annotation_font=dict(color="#34D399", size=12)
            )

            fig_scen.update_layout(
                title="5-Jahres Wertentwicklung<br>bei monatlichen Wachstumsraten",
                paper_bgcolor="#000000", plot_bgcolor="#000000",
                margin=dict(l=10, r=60, t=80, b=120), 
                height=580, 
                legend=dict(
                    orientation="h", 
                    yanchor="top", 
                    y=-0.15,  
                    xanchor="center", 
                    x=0.5, 
                    font=dict(color="#E5E7EB", size=12)
                ),
                xaxis=dict(title="Monate ab heute", showgrid=True, gridcolor="#1A1A1A", tickfont=dict(color="#A1A1AA")),
                yaxis=dict(title="Depotwert (€)", showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA")),
                hovermode="x unified",
            )
            st.plotly_chart(UI.chart_stil(fig_scen), width="stretch", key="chart_scenarios", config={"displayModeBar": False})
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Szenarien", e)
    if gewaehlte_ansicht == "📊 Szenario-Simulator (5 Jahre)":
        melde("ansicht", 0.3, "Berechne Szenarien …")
        _render_scenarios()
        lade_fertig()

    if gewaehlte_ansicht == ANSICHT_EINST:
        # --- DIAGNOSE GANZ AM ENDE (statt Sidebar - auf Mobile oft nicht auffindbar).
        # Bewusst als Letztes: im Alltag interessieren die Kurse/Charts, der
        # Systemstatus wird nur im Fehlerfall gebraucht. Faellt der persistente
        # State aus, klappt der Expander weiterhin automatisch auf.
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
    var st = D.createElement('style');
    st.textContent =
      'html.lade-js [data-testid="stApp"]::before, html.lade-js [data-testid="stApp"]::after { display:none !important; }' +
      'html.lade-js .loading-overlay { display:none !important; }' +
      '#lade-banner { position:fixed; top:0; left:0; right:0; z-index:10000; height:66px; box-sizing:border-box;' +
      ' padding:10px 16px 0; background:rgba(11,18,32,.97); border-bottom:1px solid #22344C;' +
      ' box-shadow:0 2px 14px rgba(0,0,0,.6); display:none; pointer-events:none; }' +
      '#lade-banner .lb-kopf { display:flex; align-items:center; justify-content:space-between; gap:12px; }' +
      '#lade-banner .lb-pct { font-family:"JetBrains Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums;' +
      ' font-size:1.35rem; font-weight:700; line-height:1.2; color:#E9EBEF; flex-shrink:0; }' +
      '#lade-banner .lb-text { font-size:.9rem; font-weight:600; color:#7C8493; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }' +
      '#lade-banner .lb-bar { margin-top:8px; height:9px; border-radius:999px; background:#1A2A40; overflow:hidden; }' +
      '#lade-banner .lb-fill { height:100%; width:0; border-radius:999px; background:#5B9BFF; transition:width .2s linear; }' +
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
    b.innerHTML = '<div class="lb-kopf"><span class="lb-pct">0 %</span><span class="lb-text">Lade Daten …</span></div>' +
                  '<div class="lb-bar"><div class="lb-fill"></div></div>';
    D.body.appendChild(b);
    var pct = b.querySelector('.lb-pct'), fill = b.querySelector('.lb-fill'), txt = b.querySelector('.lb-text');
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
    function setze(p) { wert = p; pct.textContent = Math.floor(p) + ' %'; fill.style.width = p + '%'; }
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
      if (!sichtbar) { b.style.display = 'block'; sichtbar = true; }
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
          start = Date.now(); setze(0);
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
