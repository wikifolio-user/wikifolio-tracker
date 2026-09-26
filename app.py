import datetime
import re
import logging
import traceback
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st

import config
import github_store

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PAGE CONFIG ---
st.set_page_config(page_title="QUANT TERMINAL // LS9VFS", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- PWA / "App-Icon"-Unterstuetzung ---
# Ermoeglicht, die Seite ueber "Zum Home-Bildschirm hinzufuegen" wie eine
# eigene App aussehen zu lassen: eigenes Icon, kein Safari-Rahmen/Adresszeile
# beim Start vom Homescreen, passende Statusleisten-/Titelleisten-Farbe.
# Icons werden von GitHub (raw-content) geladen, da Streamlit selbst keine
# eigenen statischen Zusatzdateien unter frei waehlbaren Pfaden ausliefert.
_GH_RAW_BASE = "https://raw.githubusercontent.com/wikifolio-user/wikifolio-tracker/main"
st.markdown(f"""
<link rel="manifest" href="{_GH_RAW_BASE}/manifest.json">
<link rel="apple-touch-icon" href="{_GH_RAW_BASE}/icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="LS9VFS">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#000000">
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
WIKIFOLIO_STARTKURS = 100.0

# --- TERMINAL STYLING ---
# Bewusst AUSSERHALB des periodisch aktualisierenden Fragments (siehe unten) -
# wird dadurch nur EINMAL pro echtem Seitenaufbau injiziert, nicht alle 5 Min.
# War die Hauptursache fuer das sichtbare Aufhellen/Verdunkeln bei jedem
# Fragment-Rerun (kompletter CSS-Neuaufbau zwingt den Browser zum Neu-Rendern
# der gesamten Seite).
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* ============================================================
       DESIGN-SYSTEM
       Typo:  Space Grotesk = Labels/Text (charaktervoll, technisch)
              IBM Plex Mono = ALLE Zahlen (echte Tabellenziffern,
              fuer Datendarstellung entworfen - Betraege stehen
              dadurch sauber untereinander statt zu "wackeln")
       Farbe: Graustufen als Basis. Gruen/Rot AUSSCHLIESSLICH fuer
              Kursveraenderungen - dadurch sticht das hervor, was
              wirklich wichtig ist.
       ============================================================ */
    :root {
        --ink:     #0A0B0D;   /* Hintergrund - nicht reines Schwarz, Hauch Blau */
        --surface: #131519;   /* erhoehte Flaechen */
        --line:    #21252C;   /* Haarlinien */
        --muted:   #7C8493;   /* Sekundaertext, tertiaer (Fussnoten) */
        --label:   #AAB1BE;   /* Zeilen-Labels - deutlich besser lesbar als --muted */
        --text:    #E9EBEF;   /* Primaertext */
        --up:      #16C784;
        --down:    #EA3943;
    }

    .stApp { background-color: var(--ink); color: var(--text); }

    /* Basistypo fuer Text - Icon-Elemente (z.B. Expander-Pfeile,
       Number-Input-Steppers) werden HIER BEWUSST AUSGENOMMEN, da diese
       eine eigene Icon-Font (Material Symbols) benoetigen. Wurde diese
       durch Space Grotesk ueberschrieben, zeigte Streamlit statt des
       Pfeil-Glyphs den rohen Icon-Namen als Text an (z.B. "_arrow_right"). */
    .stApp,
    .stApp *:not([data-testid="stIconMaterial"]):not(.material-icons):not(.material-symbols-rounded):not(.material-symbols-outlined) {
        font-family: 'Space Grotesk', -apple-system, sans-serif;
    }

    /* Streamlit-eigene Icons (Expander-Chevron, Stepper-Pfeile etc.)
       explizit auf ihrer Icon-Font belassen. */
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    }

    /* Zahlen bekommen konsequent die Datenschrift mit Tabellenziffern */
    .num, .q-price, .q-delta, .row-val, .hero-val, .hero-sub {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum" 1;
    }

    /* ---------- KURS-KOPF: die Zahl ist der Held der Seite ---------- */
    .quote {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: 12px; padding: 14px 16px;
        /* Diese Kachel wird in einem eigenen Fragment-Container gezeichnet -
           dort greift der Grundabstand aus stVerticalBlock nicht. Deshalb hier
           derselbe Wert (0.7rem) direkt gesetzt, damit der Abstand zur
           Depotwert-Kachel genauso gross ist wie ueberall sonst. */
        margin-bottom: 0.7rem;
    }
    /* Kachel-Ueberschriften identisch zu den Abschnittsueberschriften:
       gleiche Schrift, gleiches Gewicht, Neonweiss mit leichtem Schein. */
    .q-name, .hero-label {
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
        font-size: 0.74rem; font-weight: 700; color: #FFFFFF;
        letter-spacing: 1.3px; text-transform: uppercase; margin-bottom: 6px;
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.30);
    }
    .q-price {
        font-size: 1.6rem; font-weight: 700; color: var(--text);
        line-height: 1; letter-spacing: -0.5px;
    }
    /* Kurs + Live-Badge + Boerse in einer Zeile: die Statusinfos gehoeren
       unmittelbar zum Kurs, nicht in die Kennzahlen-Chipreihe darunter. */
    .price-line {
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    }
    .q-delta { font-size: 1.1rem; font-weight: 600; margin-top: 12px; }
    .up { color: var(--up); } .down { color: var(--down); }

    /* ---------- META-CHIPS statt Punkt-getrennter Textwurst ----------
       Live-Status als farbiges Pill-Badge, restliche Fakten als eigene
       Chips - deutlich schneller erfassbar als eine lange "A · B · C"
       Zeile. Zeitstempel bewusst separat und kleiner: es ist die am
       wenigsten wichtige Information hier (Meta zur Meta). */
    .meta-row {
        display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
        margin-top: 14px;
    }
    .live-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(22, 199, 132, 0.12); color: var(--up);
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.2px;
        padding: 4px 10px 4px 8px; border-radius: 999px;
    }
    .live-pill.offline { background: rgba(234, 57, 67, 0.12); color: var(--down); }
    .meta-chip {
        font-size: 0.85rem; color: var(--label); font-weight: 500;
        background: rgba(255, 255, 255, 0.04);
        padding: 4px 10px; border-radius: 999px;
    }
    /* Badge fuer "aktuell auf Allzeithoch" - gleiche Pill-Optik wie das
       Live-Badge, damit sich die Statusmarker in beiden Kacheln gleichen. */
    .hw-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(22, 199, 132, 0.12); color: var(--up);
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.2px;
        padding: 4px 10px; border-radius: 999px;
    }

    .live-dot {
        display: inline-block; width: 7px; height: 7px; border-radius: 50%;
        background: var(--up); animation: pulse 2.4s ease-in-out infinite;
        flex-shrink: 0;
    }
    .live-dot.offline { background: var(--down); animation: none; }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50%      { opacity: 0.35; }
    }
    @media (prefers-reduced-motion: reduce) {
        .live-dot { animation: none; }
    }

    /* ---------- HERO: eine einzige hervorgehobene Kennzahl ---------- */
    .hero {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: 12px; padding: 14px 16px; margin-bottom: 0;
    }

    /* Gesamtsumme optisch abheben - gruener Akzentrand, damit sie sich
       trotz gleicher Struktur klar von den Einzelpositionen unterscheidet. */
    .hero.gesamt {
        border-color: rgba(22, 199, 132, 0.35);
        background: linear-gradient(rgba(22, 199, 132, 0.05), rgba(22, 199, 132, 0.05)), var(--surface);
    }
    .hero-val { font-size: 1.6rem; font-weight: 700; color: var(--text); letter-spacing: -0.3px; }
    .hero-sub { font-size: 0.92rem; color: var(--label); font-weight: 500; }

    /* Kompakte Fussnote am Kachelende (Zeitstempel, Stueckzahl) - bewusst
       ohne Chip-Pille, damit sie moeglichst wenig Hoehe kostet. */
    .card-footnote {
        font-size: 0.72rem; color: var(--muted); margin-top: 8px;
    }

    /* ---------- STAT-CHIPS: gleiche Pill-Optik wie die Meta-Chips
       oben beim Kurs-Kopf - Label + Wert in einer Pille, statt Label
       ueber Wert gestapelt. Sorgt fuer ein einheitliches Design ueber
       beide Kacheln hinweg. ---------- */
    .stat-chip {
        display: inline-flex; align-items: center; gap: 7px;
        background: rgba(255, 255, 255, 0.04);
        padding: 6px 12px; border-radius: 999px;
    }
    .stat-chip-label {
        font-size: 0.68rem; font-weight: 700; color: var(--muted);
        text-transform: uppercase; letter-spacing: 0.4px;
    }
    .stat-chip-val {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.9rem; font-weight: 700; color: var(--text);
    }
    .stat-chip-val.up { color: var(--up); } .stat-chip-val.down { color: var(--down); }

    /* ---------- DATENZEILEN statt Kachel-Wildwuchs ----------
       Sekundaerwerte als hairline-getrennte Liste: ruhiger, dichter
       und deutlich schneller zu scannen als 8 gleich grosse Boxen. */
    .rows { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; margin-bottom: 22px; }
    .row {
        display: flex; justify-content: space-between; align-items: flex-start;
        gap: 14px; padding: 14px 18px; background: var(--surface);
        border-bottom: 1px solid var(--line);
    }
    .row:last-child { border-bottom: none; }
    .row-label {
        font-size: 0.88rem; color: var(--text); font-weight: 600;
        line-height: 1.35; flex: 1 1 42%; min-width: 0;
    }
    .row-val {
        font-size: 1rem; color: var(--text); font-weight: 700;
        text-align: right; line-height: 1.35; flex: 1 1 58%; min-width: 0;
        overflow-wrap: break-word;
    }
    .row-note {
        display: block; font-size: 0.78rem; color: var(--muted);
        font-weight: 400; margin-top: 4px; white-space: normal;
    }

    /* ---------- PERFORMANCE-TABELLE INNERHALB einer Kachel ----------
       Hairline-getrennte Zeitraum-Zeilen (Tag/Woche/Monat/Jahr/seit Kauf)
       direkt unter den Chips. Bewusst ohne eigenen Rahmen/Hintergrund -
       sie sitzt ja schon IN der Kachel, ein zweiter Rahmen wuerde
       verschachtelt und unruhig wirken. */
    .perf-table {
        margin-top: 10px; border-top: 1px solid var(--line);
    }
    .perf-row {
        display: flex; justify-content: space-between; align-items: baseline;
        gap: 12px; padding: 7px 2px; border-bottom: 1px solid var(--line);
    }
    .perf-row:last-child { border-bottom: none; padding-bottom: 2px; }
    .perf-label {
        font-size: 0.82rem; color: var(--label); font-weight: 500;
    }
    .perf-vals {
        display: inline-flex; gap: 12px; justify-content: flex-end;
        flex-wrap: wrap; text-align: right;
    }
    .perf-vals .up, .perf-vals .down, .perf-vals .neutral {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.85rem; font-weight: 600; white-space: nowrap;
    }
    .perf-vals .neutral { color: var(--label); }

    /* ---------- Streamlit-Eigenheiten ---------- */
    #MainMenu, footer { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; }
    /* Streamlits eigenes "Running ..."-Kaestchen ausblenden - wir zeigen
       stattdessen den zentrierten Ladefortschritt unten. Mehrere Selektoren,
       da Streamlit das Widget je nach Version unterschiedlich benennt
       (stStatusWidget / stStatus / Toolbar-Container) - so greift es
       versionsunabhaengig. */
    [data-testid="stStatusWidget"],
    [data-testid="stStatus"],
    [data-testid="stHeader"] [data-testid="stStatusWidget"],
    .stStatusWidget,
    div[class*="StatusWidget"],
    div[data-testid="stDecoration"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
        height: 0 !important;
        width: 0 !important;
        overflow: hidden !important;
    }
    /* Der Header selbst darf bleiben (er haelt den Abstand oben frei),
       nur sein Inhalt wird unsichtbar. */
    /* Der (ohnehin leere) Streamlit-Header belegt sonst ~3rem Hoehe und
       schiebt den gesamten Inhalt nach unten. Auf Hoehe 0 zusammenfallen
       lassen - dadurch kann der Innenabstand oben deutlich kleiner sein,
       ohne dass etwas unter dem Header verschwindet. */
    [data-testid="stHeader"] {
        background: transparent !important;
        height: 0 !important;
        min-height: 0 !important;
    }
    [data-testid="stAppViewContainer"] > .main { padding-top: 0 !important; }

    /* ---------- KURSANSICHT-UMSCHALTER ----------
       Kompakt gehalten: der Umschalter ist Navigation, nicht Inhalt - er darf
       die eigentliche Kurskachel nicht aus dem sichtbaren Bereich draengen.
       Trefferflaeche bleibt mit 34px trotzdem daumentauglich. */
    [data-testid="stButtonGroup"] { margin-bottom: 8px; }
    [data-testid="stButtonGroup"] button {
        min-height: 34px !important;
        padding: 4px 12px !important;
        font-size: 0.8rem !important;
        border-radius: 999px !important;
    }
    /* Aktive Pille weiss hervorheben - gleiche Bildsprache wie beim Dropdown,
       und Gruen/Rot bleiben den Kursveraenderungen vorbehalten. */
    [data-testid="stButtonGroup"] button[aria-checked="true"],
    [data-testid="stButtonGroup"] button[aria-pressed="true"] {
        border-color: #FFFFFF !important;
        box-shadow: 0 0 10px rgba(255,255,255,0.35) !important;
    }
    /* Dropdown-Variante (ab 4 Werten) ebenfalls schlanker */
    /* ---------- DROPDOWNS DEUTLICH ALS BEDIENELEMENT KENNZEICHNEN ----------
       Streamlits Standard-Selectbox sieht im dunklen Theme fast wie eine
       Ueberschrift aus. Loesung: leuchtender weisser Rahmen plus dezenter
       Schein. Bewusst MEHRERE Selektoren - Streamlit verschachtelt die
       BaseWeb-Selectbox je nach Version unterschiedlich tief, ein einzelner
       Selektor griff hier nicht zuverlaessig. */
    [data-testid="stSelectbox"] { margin-bottom: 0; }

    /* Label dezent halten - es soll orientieren, nicht mit den Kachel-
       Ueberschriften konkurrieren. */
    /* Identisch zu .abschnitt, damit alle Ueberschriften gleich aussehen.
       Typografie fuer beide Ebenen (Streamlit legt den Text je nach Version
       direkt ins label oder in ein <p> darin). */
    [data-testid="stSelectbox"] label,
    [data-testid="stSelectbox"] label p {
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
        font-size: 0.74rem !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
        letter-spacing: 1.3px !important;
        text-transform: uppercase;
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.35);
    }
    /* Trennlinie und Abstaende NUR auf dem label - liegen sie auch auf dem
       <p> darin, zeichnen beide je einen Strich (das waren die zwei Linien).
       Der Streamlit-Grundabstand greift innerhalb eines Widgets nicht,
       deshalb sind die 13px hier direkt gesetzt (entspricht 2px margin +
       11px Grundabstand bei den .abschnitt-Ueberschriften). */
    [data-testid="stSelectbox"] label {
        display: block !important;
        width: 100% !important;
        /* KEINE Trennlinie hier: das Dropdown darunter hat bereits einen
           kraeftigen weissen Rahmen - eine zusaetzliche Linie direkt darueber
           wirkt wie eine doppelte Begrenzung. Der Abstand entspricht dem der
           .abschnitt-Ueberschriften (dort 7px padding + 2px margin + 11px
           Grundabstand = 20px, hier direkt als margin gesetzt). */
        /* Streamlit fuegt zwischen Label und Feld bereits einen eigenen
           Abstand ein - deshalb hier deutlich weniger als der rechnerische
           Wert der .abschnitt-Ueberschriften, sonst klafft eine Luecke. */
        margin: 16px 0 4px 2px !important;
        padding-bottom: 0 !important;
        border-bottom: none !important;
    }
    /* Etwaigen Zusatzabstand des Widget-Containers entfernen, damit der
       Abstand Ueberschrift -> Feld dem der Abschnitte entspricht. */
    [data-testid="stSelectbox"] > div:not(:first-child) {
        margin-top: 0 !important;
    }
    /* Das innere <p> bringt eigene Abstaende mit - hier entfernen. */
    [data-testid="stSelectbox"] label p {
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        line-height: 1.2 !important;
    }

    /* Rahmen per OUTLINE statt border: outline wird von BaseWebs eigenen
       Border-Regeln nicht ueberschrieben und liegt garantiert aussen an.
       Zusaetzlich auf mehreren Ebenen gesetzt, da Streamlit die Selectbox je
       nach Version unterschiedlich tief verschachtelt. */
    [data-testid="stSelectbox"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] {
        outline: 2px solid #FFFFFF !important;
        outline-offset: 0 !important;
        border-radius: 12px !important;
        background-color: var(--surface) !important;
        box-shadow: 0 0 14px rgba(255, 255, 255, 0.35) !important;
    }

    /* Aufmerksamkeits-Puls: laeuft nur kurz nach dem Laden und kommt dann zur
       Ruhe. Dauerhafte Animation wuerde dem Blick staendig Aufmerksamkeit
       abziehen - in einer Kurs-App soll Bewegung "hier hat sich etwas
       geaendert" bedeuten, nicht "hier ist ein Bedienelement". */
    @keyframes hinweis_puls {
        0%, 100% { box-shadow: 0 0 10px rgba(255,255,255,0.25); }
        50%      { box-shadow: 0 0 26px rgba(255,255,255,0.85); }
    }
    [data-testid="stSelectbox"] > div {
        animation: hinweis_puls 1.6s ease-in-out 3;
    }
    @media (prefers-reduced-motion: reduce) {
        [data-testid="stSelectbox"] > div { animation: none; }
    }

    /* Innere Ebenen rahmenlos halten, damit keine Doppellinie entsteht */
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > div {
        border: none !important;
        background-color: transparent !important;
        min-height: 46px !important;
    }
    [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {
        box-shadow: none !important;
    }
    /* Beim Antippen kurz kraeftiger - reine Rueckmeldung, keine Dauerbewegung */
    [data-testid="stSelectbox"] > div:hover,
    [data-testid="stSelectbox"] > div:focus-within {
        box-shadow: 0 0 22px rgba(255, 255, 255, 0.7) !important;
    }

    /* Auswahltext kraeftiger als normaler Fliesstext */
    [data-testid="stSelectbox"] [data-baseweb="select"] div[value],
    [data-testid="stSelectbox"] [data-baseweb="select"] span {
        font-weight: 600 !important;
    }
    /* Pfeil weiss und groesser - zusammen mit dem Rahmen das "hier tippen"-Signal */
    [data-testid="stSelectbox"] svg {
        fill: #FFFFFF !important;
        color: #FFFFFF !important;
        width: 24px !important; height: 24px !important;
    }
    /* Aufgeklappte Liste passend zum Rest gestalten */
    div[data-baseweb="popover"] li {
        font-size: 0.9rem !important;
        min-height: 44px !important;
    }

    /* ---------- ABSCHNITTE & AUFKLAPPBEREICHE ----------
       Die Aufklappbereiche taten bisher zweierlei (etwas einstellen vs. etwas
       nachschlagen), sahen aber identisch aus. Abschnittsueberschrift plus
       weisser Rahmen macht die Gliederung auf einen Blick lesbar. */
    .abschnitt {
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
        font-size: 0.74rem; font-weight: 700; color: #FFFFFF;
        letter-spacing: 1.3px; text-transform: uppercase;
        margin: 16px 0 2px 2px;
        padding-bottom: 7px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.45);
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.35);
    }

    /* Jeder Aufklappbereich als eigener Block mit weissem Rand. Bewusst
       schwaecher als das Ansichts-Dropdown (1px statt 2px outline, dezenteres
       Leuchten) - das Dropdown ist die Hauptnavigation und soll das
       auffaelligste Element auf der Seite bleiben. */
    [data-testid="stExpander"] {
        border: 1px solid rgba(255, 255, 255, 0.55) !important;
        border-radius: 12px !important;
        background: var(--surface) !important;
        margin-bottom: 0 !important;
        overflow: hidden;
        box-shadow: 0 0 8px rgba(255, 255, 255, 0.12);
        transition: box-shadow 0.15s ease, border-color 0.15s ease;
    }
    [data-testid="stExpander"]:hover {
        border-color: rgba(255, 255, 255, 0.9) !important;
        box-shadow: 0 0 16px rgba(255, 255, 255, 0.30);
    }

    /* Titelzeile vereinheitlichen: gleiche Schrift, gleiches Gewicht, gleiche
       Groesse. Streamlit setzt hier je nach Version eigene Werte - dadurch
       wirkten die Titel unterschiedlich, obwohl es dieselbe Schrift war. */
    /* ACHTUNG: Icon-Elemente hier ausnehmen! Wird ihnen eine Textschrift
       aufgezwungen, rendert Streamlit statt des Pfeil-Glyphs den rohen
       Icon-Namen als Text ("_arrow_right"). */
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span:not([data-testid="stIconMaterial"]):not(.material-icons):not([class*="material-symbols"]),
    [data-testid="stExpander"] summary div:not([data-testid="stIconMaterial"]) {
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        line-height: 1.35 !important;
        color: var(--text) !important;
    }

    /* Der Abstand kommt bei Streamlit vom umgebenden Block, nicht vom
       Expander selbst - deshalb dort verringern. Sonst stehen die Kacheln
       trotz margin-bottom:0 weit auseinander. */
    /* Zusammengehoerige Aufklappbereiche ruecken enger zusammen als der
       Grundabstand - sie bilden optisch eine Gruppe. */
    div[data-testid="stElementContainer"]:has([data-testid="stExpander"]) {
        margin-top: -0.35rem !important;
    }
    /* AUSNAHME: der ERSTE Bereich direkt unter einer Abschnittsueberschrift
       behaelt den vollen Abstand. Ohne das saehe der Abstand Ueberschrift ->
       erste Kachel enger aus als bei "Ansicht waehlen" -> Dropdown. */
    div[data-testid="stElementContainer"]:has(.abschnitt)
    + div[data-testid="stElementContainer"] {
        margin-top: 0 !important;
    }
    /* Fallback fuer Browser ohne :has()-Unterstuetzung: der Expander zieht
       sich selbst nach oben an den vorherigen Block heran. */
    @supports not selector(:has(*)) {
        [data-testid="stExpander"] { margin-top: -0.35rem !important; }
    }

    /* "Ansicht wählen:" und "Prognose Basis auswählen:" bekommen eine eigene
       .abschnitt-Ueberschrift (siehe oben, gleiche Optik wie "WEITERE
       INFORMATIONEN"). Das native Selectbox-Label direkt danach wird hier
       gezielt ausgeblendet - WICHTIG: nicht ueber Streamlits eigenes
       label_visibility="collapsed", sondern ausschliesslich per CSS. Ein
       frueherer Versuch mit "collapsed" hat zu doppeltem Text gefuehrt:
       unsere Label-Regel nutzt "display: block !important", und !important
       in einer Stylesheet-Regel gewinnt IMMER gegen ein simples Inline-
       "style=display:none" (das Streamlit fuer "collapsed" setzt) - das
       eigentlich versteckte Label wurde dadurch wieder sichtbar. Hier
       versteckt ausschliesslich UNSERE eigene Regel, kein Widerspruch. */
    div[data-testid="stElementContainer"]:has(.abschnitt-marker-ansicht)
    + div[data-testid="stElementContainer"] [data-testid="stSelectbox"] label,
    div[data-testid="stElementContainer"]:has(.abschnitt-marker-prognose)
    + div[data-testid="stElementContainer"] [data-testid="stSelectbox"] label {
        display: none !important;
    }

    /* Aufklapp-Pfeil: eigene Icon-Schrift erzwingen und deutlich vergroessern,
       damit klar erkennbar ist, dass sich der Bereich oeffnen laesst. */
    [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
                     'Material Icons' !important;
        font-size: 1.7rem !important;
        line-height: 1 !important;
        color: #FFFFFF !important;
        opacity: 1 !important;
        flex-shrink: 0;
    }
    [data-testid="stExpander"] summary {
        padding: 13px 14px !important;
        transition: background-color 0.15s ease;
    }
    [data-testid="stExpander"] summary:hover,
    [data-testid="stExpander"] summary:hover p {
        background-color: #171A1F !important;
        color: #FFFFFF !important;
    }
    /* Abstand zwischen Pfeil und Titel */
    [data-testid="stExpander"] summary { gap: 10px !important; }
    [data-testid="stExpander"] summary svg {
        fill: #FFFFFF !important;
        color: #FFFFFF !important;
    }

    /* ---------- VERGLEICHSTABELLE ----------
       Kernprobleme der alten Fassung: umbrechende Namen, komplett leere
       Zeitraum-Spalten, keine Zeilenfuehrung ueber die volle Breite. */
    .pt-wrap {
        overflow-x: auto; -webkit-overflow-scrolling: touch;
        border: 1px solid var(--line); border-radius: 10px;
        margin-bottom: 12px;
    }
    .pt { width: 100%; border-collapse: collapse; background: #0B0C0F; }

    .pt thead th {
        position: sticky; top: 0; z-index: 2;
        /* Harmonischer Grauton, deutlich abgesetzt von den Zeilen darunter
           (#0B0C0F) - die Kopfzeile soll klar als eigene Ebene erkennbar
           sein, nicht nur eine Nuance dunkler. */
        background: #1C1F26;
        padding: 9px 10px;
        font-size: 0.64rem; font-weight: 700; color: #FFFFFF;
        letter-spacing: 0.7px; text-transform: uppercase;
        text-align: center; white-space: nowrap;
        border-bottom: 1px solid var(--line);
        text-shadow: 0 0 8px rgba(255, 255, 255, 0.30);
    }

    /* Zebra-Streifen: machen lange Zeilen ueber die ganze Breite verfolgbar */
    .pt tbody tr.pt-zebra { background: rgba(255, 255, 255, 0.022); }
    .pt tbody tr:hover { background: rgba(255, 255, 255, 0.06); }

    /* Die EIGENE Position ist der Bezugspunkt - alles andere ist Vergleich.
       Deshalb farblich abgesetzt statt in der Masse unterzugehen. */
    .pt tbody tr.pt-eigene {
        background: rgba(22, 199, 132, 0.09);
        box-shadow: inset 3px 0 0 var(--up);
    }

    .pt td {
        padding: 9px 10px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        white-space: nowrap;
    }
    .pt tbody tr:last-child td { border-bottom: none; }

    /* Name und WKN untereinander statt nebeneinander - spart Breite und
       verhindert den Umbruch mitten im Namen. */
    .pt-wert { text-align: left; min-width: 110px; }
    .pt-name {
        display: block; font-size: 0.83rem; font-weight: 700; color: #FFFFFF;
        white-space: normal; line-height: 1.25;
    }
    .pt-wknval {
        color: var(--label); font-weight: 600; font-size: 0.72rem;
        letter-spacing: 0.3px;
    }

    /* Zahlen in Tabellenziffern, damit Nachkommastellen untereinander stehen */
    .pt-num {
        text-align: right;
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.78rem;
    }
    .pt-stark { font-weight: 700; font-size: 0.83rem; }
    .pt-klein { font-size: 0.74rem; opacity: 0.92; }
    .pt-up { color: #16C784; }
    .pt-down { color: #EA3943; }
    .pt-leer { color: #4B5058; }
    .pt-seit { color: #FFFFFF; font-weight: 700; font-size: 0.75rem; text-shadow: 0 0 8px rgba(255, 255, 255, 0.30); }

    /* ---------- MOBILE: FOKUS AUF EINE KENNZAHL ----------
       Die volle Tabelle braucht ~980px, ein Smartphone bietet ~360px.
       Ein Karten-Layout (jeder Wert eine eigene Karte) waere zwar lesbar,
       zerstoert aber genau den Zweck einer VERGLEICHStabelle: das schnelle
       Nebeneinander. Deshalb stattdessen: Tabelle bleibt Tabelle, aber es
       wird nur EINE Kennzahl-Spalte gezeigt - dafuer alle Werte untereinander
       direkt vergleichbar, ohne horizontales Scrollen. Welche Kennzahl das
       ist, waehlt der Nutzer per Umschalter darueber.
       Am Desktop (>700px) bleibt die volle Tabelle unveraendert. */
    @media (max-width: 700px) {
        /* Alle Kennzahl-Spalten ausblenden ... */
        .pt td[data-spalte], .pt th[data-spalte] { display: none; }
        /* ... und nur die aktive wieder einblenden. Die Klasse am Tabellen-
           Container steuert, welche das ist. */
        .pt-fokus-monatlich  td[data-spalte="monatlich"],
        .pt-fokus-monatlich  th[data-spalte="monatlich"],
        .pt-fokus-jaehrlich  td[data-spalte="jaehrlich"],
        .pt-fokus-jaehrlich  th[data-spalte="jaehrlich"],
        .pt-fokus-perf       td[data-spalte="perf"],
        .pt-fokus-perf       th[data-spalte="perf"],
        .pt-fokus-euro       td[data-spalte="euro"],
        .pt-fokus-euro       th[data-spalte="euro"],
        .pt-fokus-_q td[data-spalte="_q"], .pt-fokus-_q th[data-spalte="_q"],
        .pt-fokus-_h td[data-spalte="_h"], .pt-fokus-_h th[data-spalte="_h"],
        .pt-fokus-_n td[data-spalte="_n"], .pt-fokus-_n th[data-spalte="_n"],
        .pt-fokus-_z td[data-spalte="_z"], .pt-fokus-_z th[data-spalte="_z"] {
            display: table-cell;
        }

        /* Der Name bekommt den gewonnenen Platz, die Zahl bleibt gut lesbar */
        .pt-wert { min-width: 0; width: 58%; }
        .pt-name { font-size: 0.86rem; }
        .pt-num  { font-size: 0.92rem; }
        .pt-stark { font-size: 0.95rem; }
        .pt td, .pt thead th { padding: 10px 8px; }
        .pt-wrap { overflow-x: visible; }
    }

    /* ---------- LADEFORTSCHRITT: FESTES BANNER AM OBEREN RAND ----------
       Bewusst position:fixed statt im normalen Seitenfluss. Vorher wanderte
       der Balken mit, sobald darueber/darunter Inhalte erschienen - und das
       Fragment der Kursansicht zeichnete ihn an einer voellig anderen Stelle.
       Ergebnis war ein sichtbares Hin- und Herspringen.
       Fixiert belegt er ausserdem keinen Platz im Layout, es gibt also auch
       keinen Versatz mehr, wenn er wieder verschwindet. */
    .loading-overlay {
        position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
        display: flex; align-items: center; gap: 12px;
        padding: 10px 16px;
        background: rgba(10, 11, 13, 0.96);
        border-bottom: 1px solid var(--line);
        box-shadow: 0 2px 14px rgba(0, 0, 0, 0.55);
        backdrop-filter: blur(6px);
    }
    .loading-pct {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums;
        font-size: 1rem; font-weight: 700; color: var(--text);
        line-height: 1; min-width: 48px; flex-shrink: 0;
    }
    /* FESTE Breite: mit "flex: 1 1 auto" wuchs und schrumpfte der Balken je
       nach Laenge des Statustextes - er wirkte dadurch, als liefe er vor und
       zurueck. Jetzt bleibt seine Breite konstant, nur die Fuellung bewegt sich. */
    .loading-bar {
        flex: 0 0 140px; width: 140px; height: 5px; border-radius: 999px;
        background: var(--line); overflow: hidden;
    }
    .loading-bar-fill {
        height: 100%; background: var(--up); border-radius: 999px;
        transition: width 0.25s ease;
    }
    /* Der Text fuellt den Rest und wird bei Bedarf abgeschnitten - er darf
       die Position von Prozentzahl und Balken nicht mehr beeinflussen. */
    .loading-text {
        flex: 1 1 auto; min-width: 0;
        font-size: 0.75rem; color: var(--muted); font-weight: 500;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .block-container { padding-top: 0.8rem; padding-bottom: 4rem; max-width: 780px; }

    /* ---------- EINHEITLICHES ABSTANDS-RASTER ----------
       Streamlit setzt zwischen allen Bloecken 1rem. Zusammen mit den eigenen
       margin-Werten der Kacheln ergaben sich dadurch ueberall andere Abstaende.
       Deshalb: EIN Grundabstand hier, und die Elemente selbst bringen keinen
       eigenen mehr mit. Alles im Fluss haelt damit denselben Rhythmus. */
    div[data-testid="stVerticalBlock"] { gap: 0.7rem !important; }

    [data-testid="stNumberInput"] input {
        font-family: 'IBM Plex Mono', monospace !important;
        font-variant-numeric: tabular-nums;
        font-size: 1.15rem !important; font-weight: 600 !important;
    }
    [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {
        width: 42px !important; height: 42px !important; min-width: 42px !important;
    }
    [data-testid="stNumberInputStepUp"] svg, [data-testid="stNumberInputStepDown"] svg {
        width: 20px !important; height: 20px !important;
    }
    /* Tabs ruhiger, ohne dicke gruene Unterstreichung */
    [data-testid="stTabs"] button { font-size: 0.78rem !important; letter-spacing: 0.3px; }
    /* Tab-Leiste bei vielen Positionen horizontal scrollbar halten, statt
       die Beschriftungen umbrechen oder abschneiden zu lassen. */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto; scrollbar-width: none;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
    /* Kachel im Tab hat keinen doppelten Abstand nach unten */
    [data-testid="stTabs"] .hero { margin-bottom: 0; }
</style>
""", unsafe_allow_html=True)


# --- STATE-HELFER (persistent über GitHub statt fluechtiges Streamlit-Dateisystem) ---
def gh_read(path, default):
    if not GH_STATE_READY:
        return default
    data, _ = github_store.get_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, GITHUB_TOKEN, default=default)
    return data if data is not None else default


@st.cache_data(ttl=60, show_spinner=False)
def gh_read_cached(path, default):
    """Wie gh_read, aber 60s gecacht - für Status-/Alarm-Reads, die bei jedem
    30s-Autorefresh sonst unnötig oft die GitHub-API belasten (Rate-Limit
    5.000/Std.). NICHT für Daten verwenden, die sofort nach einem Schreiben
    im selben Nutzer-Flow wieder gelesen werden müssen (z.B. Trader-Log) -
    dafür bleibt gh_read() ungecacht."""
    return gh_read(path, default)


def gh_write(path, obj, message="update state [skip ci]"):
    if not GH_STATE_READY:
        return False
    erfolg = github_store.put_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, obj, GITHUB_TOKEN, message=message)
    if erfolg:
        # WICHTIG: den Lese-Cache leeren. Sonst liefert gh_read_cached() bis zu
        # 60s lang noch den ALTEN Zustand - bei mehreren Reruns innerhalb dieser
        # Zeit (jede Widget-Interaktion loest einen aus) wuerde ein bereits
        # gesetzter Alarm-Cooldown nicht gesehen und dieselbe Discord-Meldung
        # mehrfach verschickt.
        gh_read_cached.clear()
    return erfolg


# --- APP-FEHLER AN DISCORD MELDEN (Punkt 10) ---
def notify_app_error(context, exc):
    """Meldet einen Fehler INNERHALB der Streamlit-App an Discord (nicht nur
    in die schwer einsehbaren Cloud-Logs). Cooldown pro 'context' (z.B. Tab-
    Name), damit ein wiederholt fehlschlagender Bereich nicht bei jedem
    30s-Autorefresh erneut pingt."""
    logging.error(f"App-Fehler in '{context}': {exc}", exc_info=True)  # voller Traceback jetzt in den Logs
    if not DISCORD_WEBHOOK_URL:
        return

    state = gh_read_cached(config.STATE_PATH_APP_ERROR, {})
    now = datetime.datetime.now(BERLIN_TZ)
    last_str = state.get(context)
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
           f"Fehler: `{type(exc).__name__}: {str(exc)[:200]}`\n"
           f"```\n{traceback.format_exc()[-1200:]}\n```\n"
           f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}")
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
        state[context] = now.isoformat()
        gh_write(config.STATE_PATH_APP_ERROR, state, message="update app error state [skip ci]")
    except Exception as e:
        logging.error(f"Discord App-Error-Alert Fehler: {e}")


# --- ZAHLENFORMATIERUNG (Punkt = Tausender, Komma = Dezimal) ---
def fmt(val, dec=2):
    if dec > 0:
        s = f"{val:,.{dec}f}"
    else:
        s = f"{val:,.0f}"
    return f"{s.replace(',', 'X').replace('.', ',').replace('X', '.')}€"

# --- VOLLAUTOMATISCHER LIVE-KURS ABRUF (ls-tc.de, direkter Emittent LS9VFS) ---
@st.cache_data(ttl=30, show_spinner=False)
def get_live_market_data():
    """
    Holt den aktuellen Mid-Kurs direkt von ls-tc.de (Lang & Schwarz
    TradeCenter), dem Emittenten des Zertifikats. Kostenlos, kein API-Key nötig.
    Vortageskurs: aus info.plotlines[id="previousDay"].value (siehe
    config.extract_previous_close - DAS ist der Ort, wo ls-tc.de den echten
    Vortageswert mitliefert, kein top-level 'previousClose'-Feld). Die
    History-Suche dient nur noch als Rückfalloption.
    """
    params = {
        "container": "chart1",
        "instrumentId": config.LS_INSTRUMENT_ID,
        "marketId": "1",
        "quotetype": "mid",
        "series": "intraday,history,flags",
        "type": "",
        "localeId": "2",
    }

    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params, headers=config.LS_TC_HEADERS, timeout=6)
        r.raise_for_status()
        data = r.json()

        intraday = (
            data.get("series", {}).get("intraday", {}).get("data")
            or data.get("intraday", {}).get("data")
            or []
        )
        if intraday:
            akt = float(intraday[-1][1])

            vor = config.extract_previous_close(data)

            if vor is None:
                history = (
                    data.get("series", {}).get("history", {}).get("data")
                    or data.get("history", {}).get("data")
                    or []
                )
                vor = config.pick_previous_close_from_history(history)

            if vor is None:
                vor = float(intraday[0][1])

            if akt > 0 and vor > 0:
                return akt, vor, "ls-tc.de Live (Emittent)"

        logging.warning("ls-tc.de: Unerwartete JSON-Struktur, kein Kurs extrahiert.")
    except Exception as e:
        logging.error(f"Fehler beim Abruf von ls-tc.de: {e}")

    return None, None, "Fehler – keine Live-Daten"


# --- ECHTE HISTORISCHE DATEN VON ls-tc.de LADEN ---
@st.cache_data(ttl=300, show_spinner=False)
def get_historical_market_data(start_date, end_date, live_close_fallback):
    """
    Holt die Tages-History direkt von ls-tc.de. Da der Endpunkt primär
    Schlusskurse liefert, werden Open/High/Low pragmatisch aus dem Close
    approximiert, sofern die API keine echten OHLC liefert.
    """
    params = {
        "container": "chart1",
        "instrumentId": config.LS_INSTRUMENT_ID,
        "marketId": "1",
        "quotetype": "mid",
        "series": "history",
        "type": "",
        "localeId": "2",
    }
    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params, headers=config.LS_TC_HEADERS, timeout=8)
        r.raise_for_status()
        raw = r.json()
        history = (
            raw.get("series", {}).get("history", {}).get("data")
            or raw.get("history", {}).get("data")
            or []
        )
        if history:
            rows = []
            for ts_ms, close in history:
                ts = pd.to_datetime(ts_ms, unit="ms")
                if ts.date() < start_date or ts.date() > end_date:
                    continue
                rows.append({"Date": ts, "Close": float(close)})
            if rows:
                df = pd.DataFrame(rows).set_index("Date").sort_index()
                df = df[df["Close"] > 0]
                if not df.empty:
                    df["Open"] = df["Close"]
                    df["High"] = df["Close"] * 1.003
                    df["Low"] = df["Close"] * 0.997
                    return df[["Open", "High", "Low", "Close"]], "ls-tc.de Live (Emittent)"

        logging.warning("ls-tc.de: Keine verwertbare History-Struktur gefunden.")
    except Exception as e:
        logging.error(f"Fehler beim Laden der Historie von ls-tc.de: {e}")

    # --- FALLBACK: klar gekennzeichnete synthetische Daten, NICHT echt ---
    date_range = pd.date_range(start=start_date, end=end_date, freq="B")
    n = len(date_range)
    import numpy as np
    np.random.seed(42)
    base_prices = [
        config.ANFANGSKURS * ((live_close_fallback / config.ANFANGSKURS) ** (i / max(1, n - 1)))
        for i in range(n)
    ]
    noise = np.random.normal(0, live_close_fallback * 0.003, n)
    prices = [max(10, p + n_val) for p, n_val in zip(base_prices, noise)]
    prices[-1] = live_close_fallback

    df = pd.DataFrame(index=date_range)
    df["Close"] = prices
    df["Open"] = prices
    df["High"] = [p * 1.005 for p in prices]
    df["Low"] = [p * 0.995 for p in prices]
    return df, "⚠️ SYNTHETISCH (Fallback, KEINE ECHTEN DATEN)"


# --- BENCHMARK-VERGLEICHSDATEN (ls-tc.de, gleiche API wie LS9VFS) ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_benchmark_history(instrument_id, start_date, end_date):
    """Holt Tages-Schlusskurse für einen Vergleichswert (ETF) von ls-tc.de.
    Gibt eine Series (Index=Datum, Value=Close) zurück, oder None bei Fehler -
    Vergleichswerte sind "nice to have", kein Grund die App abstürzen zu lassen."""
    headers = {
        "User-Agent": config.LS_TC_HEADERS["User-Agent"],
        "Referer": f"https://www.ls-tc.de/de/etf/{instrument_id}",
    }
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "history", "type": "", "localeId": "2",
    }
    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        raw = r.json()
        history = (
            raw.get("series", {}).get("history", {}).get("data")
            or raw.get("history", {}).get("data") or []
        )
        rows = []
        for ts_ms, close in history:
            ts = pd.to_datetime(ts_ms, unit="ms")
            if start_date <= ts.date() <= end_date:
                rows.append({"Date": ts, "Close": float(close)})
        if not rows:
            return None
        s = pd.DataFrame(rows).set_index("Date").sort_index()["Close"]
        return s[s > 0]
    except Exception as e:
        logging.warning(f"Benchmark {instrument_id} nicht ladbar: {e}")
        return None


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
        heute_ts = pd.Timestamp(end_date)
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
    ausgebremst. gh_write() leert den Cache, Aenderungen sind also sofort da."""
    positionen = gh_read_cached(STATE_PATH_POSITIONEN, None)
    if not positionen:
        return [_position_aus_config()]
    return positionen


def speichere_positionen(positionen, message="update positionen [skip ci]"):
    return gh_write(STATE_PATH_POSITIONEN, positionen, message=message)


def lade_beobachtung():
    """Beobachtete Werte (reine Kursanzeige, NICHT im Depot). Standard ist eine
    leere Liste - ohne Eintraege verhaelt sich die App exakt wie vorher."""
    return gh_read_cached(STATE_PATH_BEOBACHTUNG, []) or []


def speichere_beobachtung(eintraege, message="update beobachtung [skip ci]"):
    return gh_write(STATE_PATH_BEOBACHTUNG, eintraege, message=message)


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
    """{instrument_id (str): {"datum": "YYYY-MM-DD", "kurs": 100.0}}"""
    return gh_read_cached(STATE_PATH_AUFLEGUNG, {}) or {}


def speichere_auflegung(instrument_id, datum, kurs=WIKIFOLIO_STARTKURS):
    """Merkt sich Auflegungsdatum und -kurs dauerhaft. datum=None loescht."""
    daten = dict(lade_auflegungen())
    schluessel = str(instrument_id)
    if datum is None:
        daten.pop(schluessel, None)
    else:
        daten[schluessel] = {"datum": datum.isoformat(), "kurs": float(kurs)}
    return gh_write(STATE_PATH_AUFLEGUNG, daten, message="update auflegung [skip ci]")


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


def position_stueckzahl(pos):
    """Stueckzahl ergibt sich aus Startkapital / Kaufkurs - damit bleibt sie
    automatisch konsistent, wenn das Startkapital angepasst wird."""
    kaufkurs = float(pos.get("kaufkurs") or 0)
    if kaufkurs <= 0:
        return 0.0
    return float(pos.get("startkapital") or 0) / kaufkurs


@st.cache_data(ttl=30, show_spinner=False)
def get_live_kurs(instrument_id):
    """Wie get_live_market_data(), aber fuer eine beliebige Instrument-ID.
    Gibt (aktueller_kurs, vortageskurs, quelle) zurueck bzw. (None, None, Fehler)."""
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "intraday,history,flags", "type": "", "localeId": "2",
    }
    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params,
                         headers=config.LS_TC_HEADERS, timeout=6)
        r.raise_for_status()
        data = r.json()
        intraday = (data.get("series", {}).get("intraday", {}).get("data")
                    or data.get("intraday", {}).get("data") or [])
        if intraday:
            akt = float(intraday[-1][1])
            vor = config.extract_previous_close(data)
            if vor is None:
                history = (data.get("series", {}).get("history", {}).get("data")
                           or data.get("history", {}).get("data") or [])
                vor = config.pick_previous_close_from_history(history)
            if vor is None:
                vor = float(intraday[0][1])
            if akt > 0 and vor > 0:
                return akt, vor, "ls-tc.de Live (Emittent)"
    except Exception as e:
        logging.error(f"Live-Kurs für Instrument {instrument_id} nicht ladbar: {e}")
    return None, None, "Fehler – keine Live-Daten"


@st.cache_data(ttl=120, show_spinner=False)
def get_kurshistorie(instrument_id, start_date, end_date):
    """Tages-Schlusskurse einer beliebigen Instrument-ID als Series
    (Index=Datum). Basis fuer die Zeitraum-Kennzahlen - ersetzt das
    produktspezifische Scraping der wikifolio-Seite."""
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "history", "type": "", "localeId": "2",
    }
    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params,
                         headers=config.LS_TC_HEADERS, timeout=8)
        r.raise_for_status()
        raw = r.json()
        history = (raw.get("series", {}).get("history", {}).get("data")
                   or raw.get("history", {}).get("data") or [])
        rows = []
        for ts_ms, close in history:
            ts = pd.to_datetime(ts_ms, unit="ms")
            if start_date <= ts.date() <= end_date:
                rows.append({"Date": ts, "Close": float(close)})
        if rows:
            s = pd.DataFrame(rows).set_index("Date").sort_index()["Close"]
            return s[s > 0]
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
    schritte = (mu_verwendet - 0.5 * sigma_tag ** 2) + sigma_tag * z

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
    kennzahlen = {
        "verlust_wahrscheinlichkeit": float((endwerte < startwert).mean() * 100),
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


@st.cache_data(ttl=3600, show_spinner=False)
def suche_instrument(suchbegriff):
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
        return []


def check_and_alert_fetch_failure(is_live_data, is_live_history):
    """Meldet per Discord, wenn Live-Kurs und/oder Chart-Historie gerade NICHT
    echt sind - mit 30-Min-Cooldown, damit nicht jede Sekunde gepingt wird."""
    if not DISCORD_WEBHOOK_URL:
        return
    state = gh_read_cached(config.STATE_PATH_FETCH_FAIL_ALARM, {"last_alert": None, "war_down": False})
    now = datetime.datetime.now(BERLIN_TZ)
    is_down = (not is_live_data) or (not is_live_history)

    war_down = bool(state.get("war_down", False))
    last_alert_str = state.get("last_alert")
    last_alert = None
    if last_alert_str:
        try:
            last_alert = datetime.datetime.fromisoformat(last_alert_str)
        except Exception:
            pass
    cooldown_ok = (last_alert is None) or ((now - last_alert).total_seconds() > 30 * 60)

    neuer_last_alert = last_alert_str

    if is_down and cooldown_ok:
        msg = (f"⚠️ **Datenquelle down ({config.WKN})**\n"
               f"ls-tc.de liefert gerade keine echten Live-/Chartdaten mehr. "
               f"App zeigt Fallback-/Synthetikwerte an.\n"
               f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}")
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            neuer_last_alert = now.isoformat()
        except Exception as e:
            logging.error(f"Discord Fetch-Fail-Alarm Fehler: {e}")
    elif not is_down and war_down:
        msg = f"✅ **Datenquelle wieder OK ({config.WKN})** — ls-tc.de liefert wieder Live-Daten."
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
        except Exception as e:
            logging.error(f"Discord Fetch-Recover Fehler: {e}")

    # NUR schreiben, wenn sich der Zustand tatsaechlich geaendert hat. Vorher
    # erzeugte jeder Durchlauf einen GitHub-Commit - bei haeufigen Reruns (jede
    # Widget-Interaktion loest einen aus) unnoetige API-Last und Rauschen.
    if war_down != is_down or neuer_last_alert != last_alert_str:
        gh_write(
            config.STATE_PATH_FETCH_FAIL_ALARM,
            {"last_alert": neuer_last_alert, "war_down": is_down},
            message="update fetch fail alarm state [skip ci]",
        )


def tab_label(name, wkn="", max_len=16):
    """Kuerzt Tab-Beschriftungen lesbar statt hart mitten im Wort.

    - Klammerzusaetze entfallen (die WKN steht ohnehin in der Kachel)
    - gekuerzt wird an der letzten Wortgrenze, mit Auslassungszeichen
    - passt der Name gar nicht, wird die WKN genommen: kurz und eindeutig
    """
    text = re.sub(r"\s*\([^)]*\)?\s*$", "", (name or "").strip())
    if not text:
        return wkn or "?"
    if len(text) <= max_len:
        return text
    gekuerzt = text[:max_len].rsplit(" ", 1)[0].rstrip(" ,-·")
    # Wuerde der Wortschnitt zu viel wegnehmen (z.B. "MSCI Semiconductors" ->
    # nur noch "MSCI"), lieber hart auf volle Laenge kuerzen: mehr Kontext als
    # ein einzelnes Kuerzel, und immer noch besser als die WKN.
    if len(gekuerzt) < max_len * 0.6:
        gekuerzt = text[:max_len - 1].rstrip(" ,-·")
    return gekuerzt + "…"


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

    def melde(schluessel, anteil=0.0, text=""):
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
            f'<div class="loading-text">{text}</div></div>',
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
            f'<div class="loading-text">{text}</div></div>',
            unsafe_allow_html=True,
        )
    return zeichne


# --- GESAMTE RENDER-LOGIK ALS FRAGMENT ---
# Vermeidet den harten Full-Page-Rerun von st_autorefresh (sichtbares
# Aufhellen/Neuzeichnen alle 30s). Ein Fragment aktualisiert sich selbst
# periodisch, ohne die komplette Seite neu zu bauen/zu scrollen.
@st.fragment(run_every="5m")
def render_dashboard():
    now_berlin = datetime.datetime.now(BERLIN_TZ)
    heute_date = now_berlin.date()

    # EINE gemeinsame Ladeanzeige fuer den kompletten Seitenaufbau. Die
    # Gewichte entsprechen grob dem Zeitanteil der jeweiligen Phase - dadurch
    # laeuft ein einziger Prozentwert von 0 auf 100, statt dass mehrere Balken
    # nacheinander jeweils wieder bei 0 % beginnen.
    _lade_platz = st.empty()
    melde, lade_fertig = erstelle_ladeanzeige(_lade_platz, [
        ("live",        8),    # ein Abruf
        ("kaufkurs",    5),    # ein Abruf, meist aus dem Cache
        ("historie",   12),    # ein groesserer Abruf
        ("benchmarks", 40),    # ein Abruf je Vergleichswert - der Loewenanteil
        ("positionen", 18),    # je weiterer Position zwei Abrufe
        ("beob_prognose", 10), # je Beobachtungswert ein Abruf fuer die Prognose-Basis
        ("ansicht",    7),     # gewaehlter Chart
    ])

    melde("live", 0.0, "Rufe Live-Kurs ab …")
    aktueller_kurs, vortag_kurs, fetched_source = get_live_market_data()

    is_live_data = "Fehler" not in fetched_source

    if not is_live_data:
        aktueller_kurs, vortag_kurs = 302.980, 302.100
        fetched_source = "⚠️ FALLBACK-WERT (KEINE ECHTEN DATEN)"

    # --- KAUFDATUM, KAUFKURS, KAPITAL: manuell anpassbar ---
    # Still aus dem gespeicherten Zustand lesen (Standard: config-Werte) - die
    # sichtbaren Eingabefelder stehen weiter unten im Eingaben-Expander.
    startkapital_aktiv = st.session_state.get("haupt_startkapital_input", float(config.STARTKAPITAL))
    kaufdatum_aktiv = st.session_state.get("haupt_kaufdatum_input", config.KAUFDATUM)
    if isinstance(kaufdatum_aktiv, datetime.datetime):
        kaufdatum_aktiv = kaufdatum_aktiv.date()

    # Kaufkurs wahlweise automatisch aus der Kurshistorie am Kaufdatum bestimmen
    # (letzter Schlusskurs am oder vor dem Tag - faellt der Kauftag auf ein
    # Wochenende/Feiertag, greift der vorherige Handelstag) oder manuell setzen.
    kaufkurs_auto = st.session_state.get("haupt_kaufkurs_auto", True)
    kaufkurs_ermittelt = None
    if kaufkurs_auto:
        melde("kaufkurs", 0.0, "Ermittle Kaufkurs …")
        _hist_kauf = get_kurshistorie(
            config.LS_INSTRUMENT_ID,
            kaufdatum_aktiv - datetime.timedelta(days=30), kaufdatum_aktiv
        )
        if not _hist_kauf.empty:
            kaufkurs_ermittelt = float(_hist_kauf.iloc[-1])

    kaufkurs_aktiv = (
        kaufkurs_ermittelt if kaufkurs_ermittelt
        else st.session_state.get("haupt_kaufkurs_input", float(config.ANFANGSKURS))
    )
    if not kaufkurs_aktiv or kaufkurs_aktiv <= 0:
        kaufkurs_aktiv = float(config.ANFANGSKURS)

    stueckzahl_aktiv = startkapital_aktiv / kaufkurs_aktiv

    melde("historie", 0.0, "Lade Kurshistorie …")
    df_chart, hist_source_name = get_historical_market_data(kaufdatum_aktiv, heute_date, aktueller_kurs)
    is_live_history = "SYNTHETISCH" not in hist_source_name

    check_and_alert_fetch_failure(is_live_data, is_live_history)

    if not df_chart.empty:
        df_chart.iloc[-1, df_chart.columns.get_loc("Close")] = aktueller_kurs
        df_chart.iloc[-1, df_chart.columns.get_loc("High")] = max(df_chart.iloc[-1]["High"], aktueller_kurs)
        df_chart.iloc[-1, df_chart.columns.get_loc("Low")] = min(df_chart.iloc[-1]["Low"], aktueller_kurs)

    df_chart["Startkapital"] = startkapital_aktiv

    # --- HIGH WATERMARK: mit echter Historie initialisieren/korrigieren ---
    # Der Cron kennt beim allerersten Lauf nur den aktuellen Kurs als "Hoch" -
    # hier wird das (still, ohne Alarm) auf den tatsächlichen historischen
    # Höchststand korrigiert, falls der genauer/höher ist.
    if not df_chart.empty:
        historischer_hoechststand = float(df_chart["Close"].max())
        historischer_hoechststand_datum = df_chart["Close"].idxmax()  # echtes Datum des Hochs, nicht "jetzt"
        hw_state = gh_read_cached(config.STATE_PATH_HIGH_WATERMARK, None)
        aktuelles_hoch = float(hw_state["high_watermark"]) if hw_state and "high_watermark" in hw_state else 0.0
        korrigiertes_hoch = max(historischer_hoechststand, aktuelles_hoch)

        if historischer_hoechststand >= aktuelles_hoch:
            # Die Chart-Historie kennt das (mindestens ebenso) hohe Hoch - deren echtes Datum nutzen
            high_watermark_datum = historischer_hoechststand_datum.strftime("%d.%m.%Y")
        else:
            # Der gespeicherte State (z.B. vom Cron erfasster Intraday-Wert) ist hoeher als
            # die Tages-Schlusskurse - dessen eigenes gespeichertes Datum nutzen
            gespeichertes_datum = hw_state.get("erreicht_am") if hw_state else None
            try:
                high_watermark_datum = datetime.datetime.fromisoformat(gespeichertes_datum).strftime("%d.%m.%Y") if gespeichertes_datum else "-"
            except Exception:
                high_watermark_datum = "-"

        if not hw_state or korrigiertes_hoch > aktuelles_hoch:
            gh_write(
                config.STATE_PATH_HIGH_WATERMARK,
                {"high_watermark": korrigiertes_hoch, "erreicht_am": datetime.datetime.now(BERLIN_TZ).isoformat()},
                message="app: korrigiere/initialisiere high watermark [skip ci]",
            )
        high_watermark_anzeige = korrigiertes_hoch
    else:
        high_watermark_anzeige = aktueller_kurs
        high_watermark_datum = "-"

    start_dt = pd.to_datetime(kaufdatum_aktiv)
    def get_entnahme_at_date(ts):
        months = (ts.year - start_dt.year) * 12 + (ts.month - start_dt.month)
        if ts.day < start_dt.day:
            months -= 1
        return max(0, months) * config.ENTNAHME_PM

    df_chart["Kumulierte_Entnahme"] = [get_entnahme_at_date(ts) for ts in df_chart.index]

    entnommen_aktiv = st.session_state.get("haupt_entnommen_input", 0.0)
    sparrate_aktiv = st.session_state.get("haupt_sparrate_input", 0.0)

    # --- SPARPLAN: Startdatum persistent verfolgen (GitHub-State), damit die
    # Berechnung nach einem Neustart nicht auf 0 zurueckfaellt. Wird beim
    # ersten Aktivieren (>0€) auf heute gesetzt, bei 0€ wieder geloescht -
    # reaktivieren startet die Zaehlung dann wieder neu ab dem Tag.
    #
    # Fachlich korrekt: eine Einzahlung kauft zusaetzliche ANTEILE zum
    # jeweiligen Monats-Kurs (nicht einfach ein fixer, nicht mitwachsender
    # Betrag) - diese Anteile schwanken danach mit dem Kurs mit, genau wie
    # die urspruenglichen. Deshalb fliesst das direkt in die Stueckzahl und
    # damit in den BRUTTO-Wert ein, nicht nur additiv in Netto. ---
    sparplan_state = gh_read_cached(config.STATE_PATH_SPARPLAN, {})
    zusaetzliche_stueckzahl_sparplan = 0.0
    if sparrate_aktiv > 0:
        if not sparplan_state.get("start_datum"):
            sparplan_state = {"start_datum": heute_date.isoformat()}
            gh_write(config.STATE_PATH_SPARPLAN, sparplan_state, message="sparplan gestartet [skip ci]")
        sparplan_start = datetime.date.fromisoformat(sparplan_state["start_datum"])
        monate_sparplan = max(0, (heute_date.year - sparplan_start.year) * 12 + (heute_date.month - sparplan_start.month))
        if heute_date.day < sparplan_start.day:
            monate_sparplan -= 1
        monate_sparplan = max(0, monate_sparplan)

        if not df_chart.empty:
            for k in range(0, monate_sparplan + 1):
                ziel_datum = pd.Timestamp(sparplan_start) + pd.DateOffset(months=k)
                passende_tage = df_chart.index[df_chart.index <= ziel_datum]
                preis_am_einzahlungstag = float(df_chart.loc[passende_tage[-1], "Close"]) if len(passende_tage) else aktueller_kurs
                if preis_am_einzahlungstag > 0:
                    zusaetzliche_stueckzahl_sparplan += sparrate_aktiv / preis_am_einzahlungstag
    else:
        if sparplan_state.get("start_datum"):
            gh_write(config.STATE_PATH_SPARPLAN, {}, message="sparplan gestoppt [skip ci]")

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
        items = list(config.BENCHMARKS.items())
        gesamt = len(items)
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

    benchmark_series, benchmark_start_daten = lade_benchmarks_mit_fortschritt(
        df_chart.index, kaufdatum_aktiv, startkapital_aktiv
    )

    # --- SIMULATION (bisheriges Verhalten): Stückzahl bleibt konstant, Entnahme
    # wird nur buchhalterisch vom Bruttowert abgezogen. ---
    df_chart["Depotwert_Brutto"] = df_chart["Close"] * stueckzahl_aktiv
    df_chart["Depotwert_Netto"] = df_chart["Depotwert_Brutto"] - df_chart["Kumulierte_Entnahme"]

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
        for k, titel in [("_q", "3 Mon."), ("_h", "6 Mon."),
                         ("_n", "9 Mon."), ("_z", "12 Mon.")]:
            if any(e.get(k) is not None for e in eintraege):
                moeglich.append((titel, k))
        moeglich.append(("+/- €", "euro"))

        beschriftungen = [b for b, _ in moeglich]
        wahl = st.pills("Vergleichen nach", beschriftungen,
                        default=beschriftungen[0], key=key)
        zuordnung = dict(moeglich)
        return zuordnung.get(wahl or beschriftungen[0], "jaehrlich")

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
            return f'<td class="{klassen}"{attr}>{wert:+.2f}%</td>'

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
                f'<td class="pt-wert"><span class="pt-name">{name}</span></td>'
                + zelle(e.get("_monatlich"), fett=True, label="Ø/Mon.", spalte="monatlich")
                + zelle(e.get("_jaehrlich"), fett=True, label="Ø/Jahr", spalte="jaehrlich")
                + zelle(e.get("_perf"), fett=True, label="Gesamt", spalte="perf")
                + "".join(zelle(e.get(k), fett=True, label=titel, spalte=k)
                          for k, titel in aktive_zeitraeume)
                + f'<td class="pt-num pt-stark {euro_klasse}" data-label="+/- €" data-spalte="euro">{fmt(euro or 0, 0)}</td>'
                + f'<td class="pt-num pt-wknval" data-label="WKN" data-spalte="wkn">{kuerzel or "–"}</td>'
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
        return (f'<div class="pt-wrap"><table class="pt pt-fokus-{fokus}">'
                f'<thead><tr>{kopf}</tr></thead><tbody>{zeilen}</tbody></table></div>')

    def berechne_performance_kennzahlen(erste_werte, letzter_wert, start_datum, end_datum):
        """Gesamt-%, Ø-monatliche % und Ø-jährliche % (beide CAGR-Stil,
        laufzeitbereinigt - fair vergleichbar auch bei unterschiedlich langen
        Zeiträumen) sowie Gewinn/Verlust in € für eine normierte Wertreihe
        (erster Wert = eingesetztes Kapital)."""
        gesamt_pct = (letzter_wert / erste_werte - 1) * 100
        tage = max(1, (end_datum - start_datum).days)
        monate = tage / 30.44
        monatliche_pct = (((letzter_wert / erste_werte) ** (1 / monate)) - 1) * 100 if monate > 0 else 0.0
        jaehrliche_pct = (((1 + monatliche_pct / 100) ** 12) - 1) * 100
        gewinn_verlust_euro = letzter_wert - erste_werte
        return gesamt_pct, monatliche_pct, jaehrliche_pct, gewinn_verlust_euro

    # --- REAL: Entnahme erfolgt tatsächlich durch monatlichen Verkauf von Anteilen
    # zum jeweils gültigen GELDKURS (Bid, nicht Mid) -> Stückzahl sinkt dauerhaft,
    # und der Spread schmälert die Rendite zusätzlich realistisch. ---
    def berechne_reale_stueckzahl(df, start_stueckzahl, entnahme_pm, start_dt, spread_pct):
        stueckzahl = start_stueckzahl
        verlauf = []
        letzter_monat = None
        for ts, row in df.iterrows():
            monat_key = (ts.year, ts.month)
            if letzter_monat is not None and monat_key != letzter_monat:
                mid_preis = row["Close"]
                geld_preis = mid_preis * (1 - spread_pct / 100.0)  # realer Verkaufskurs
                if geld_preis and geld_preis > 0:
                    verkaufte_stueck = entnahme_pm / geld_preis
                    stueckzahl = max(0.0, stueckzahl - verkaufte_stueck)
            letzter_monat = monat_key
            verlauf.append(stueckzahl)
        return verlauf

    df_chart["Stueckzahl_Real"] = berechne_reale_stueckzahl(
        df_chart, stueckzahl_aktiv, config.ENTNAHME_PM, start_dt, config.SPREAD_PCT
    )
    df_chart["Depotwert_Real"] = df_chart["Close"] * df_chart["Stueckzahl_Real"]

    # --- DISCORD ALERT (klassischer -1%-Alarm, Legacy-Button in Sidebar) ---
    def send_discord_alert(pct_change, current_price):
        if not DISCORD_WEBHOOK_URL:
            return False
        state = gh_read(config.STATE_PATH_ALARM, {})
        last_alert_time = None
        if state.get("last_alert"):
            try:
                last_alert_time = datetime.datetime.fromisoformat(state["last_alert"])
            except Exception:
                pass

        now = datetime.datetime.now(BERLIN_TZ)
        if last_alert_time and (now - last_alert_time).total_seconds() < 3600:
            return False

        msg = f"🚨 **QUANT TERMINAL ALARM** 🚨\nDas Wikifolio **{config.WKN}** ist gefallen!\nTagesveränderung: **{pct_change:+.2f}%**\nAktueller Kurs: **{current_price:.3f}€**"
        try:
            response = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            if response.status_code in (200, 204):
                gh_write(config.STATE_PATH_ALARM, {"last_alert": now.isoformat()}, message="update alarm state [skip ci]")
                return True
        except Exception as e:
            logging.error(f"Discord Alert Fehler: {e}")
        return False

    # --- RENDITE-KENNZAHLEN: zwei verschiedene Fragen, zwei Verfahren ---
    # 1) "Wie lief es fuer MICH bisher?" -> Kurs gegen den eigenen Kaufkurs.
    #    Das ist die realisierte Rendite dieser Position und gehoert genau so
    #    auf die Depotwert-Kachel und in die Vergleichstabellen.
    tage_gehalten = max(1, (heute_date - kaufdatum_aktiv).days)
    erwartete_rendite_pa = (((aktueller_kurs / kaufkurs_aktiv) ** (365.25 / tage_gehalten)) - 1) * 100

    # 2) "Womit ist kuenftig zu rechnen?" -> robuste Schaetzung aus der
    #    Kurshistorie des PRODUKTS (Trend-Regression + lange Zeitfenster,
    #    Median daraus). Nur fuer Hochrechnungen in die Zukunft: 100k-
    #    Meilenstein, Zukunfts-Prognose, Szenario-Simulator. Ein einzelner
    #    guenstiger Einstiegszeitpunkt soll die Zukunft nicht vorzeichnen.
    prognose_rendite_pa, prognose_rendite_details = produkt_rendite_pa(
        config.LS_INSTRUMENT_ID, heute_date
    )
    if prognose_rendite_pa is None:          # zu wenig Historie -> eigener Kauf als Rueckfall
        prognose_rendite_pa, prognose_rendite_details = erwartete_rendite_pa, []
    erwarteter_zins_mo = (1 + (prognose_rendite_pa / 100.0)) ** (1 / 12) - 1

    # --- SIDEBAR & STEUERUNG ---
    st.sidebar.markdown("### ⚡ System Status")
    if is_live_data:
        st.sidebar.success(f"🟢 Live-Daten aktiv\nKurs-Feed: {fetched_source}\nChart-Feed: {hist_source_name}")
    else:
        st.sidebar.error(f"🔴 KEINE LIVE-DATEN\nKurs-Feed: {fetched_source}\nChart-Feed: {hist_source_name}")
    st.sidebar.write(f"Webhook geladen: {'Ja' if DISCORD_WEBHOOK_URL else 'Nein'}")
    st.sidebar.write(f"Persistenter State (GitHub): {'Ja' if GH_STATE_READY else '⚠️ Nein - GITHUB_REPO/GITHUB_TOKEN fehlen'}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Live-Daten Monitor")
    st.sidebar.text(f"Aktueller Kurs: {aktueller_kurs:.3f} €")
    st.sidebar.text(f"Vortageskurs: {vortag_kurs:.3f} €")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 Automatische Prognose-Basis")
    st.sidebar.info(f"Realisiert seit Kauf: **{erwartete_rendite_pa:.2f}% p.a.**\n\n"
                    f"Basis der 100k-Simulation (Produkt-Historie, Median): "
                    f"**{prognose_rendite_pa:.2f}% p.a.**")

    if st.sidebar.button("🔔 Test-Alarm senden"):
        if send_discord_alert(-1.50, aktueller_kurs):
            st.sidebar.success("Test-Alarm gesendet!")

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
    letztes_update_zeit = now_berlin.strftime("%d.%m.%Y %H:%M:%S Uhr")


    def check_and_send_price_updates(pct_change, current_price):
        """
        Nur noch der Schwellen-Alarm bei Über-/Unterschreiten von
        config.TAGESVERLUST_SCHWELLE_PCT. Die routinemäßigen 5-Minuten-Updates
        übernimmt ausschließlich der externe GitHub-Actions-Cronjob.
        """
        if not DISCORD_WEBHOOK_URL:
            return
        if not config.ist_handelszeit(datetime.datetime.now(BERLIN_TZ)):
            return  # außerhalb der Handelszeiten keine (Fehl-)Alarme auf eingefrorene Kurse

        state = gh_read_cached(config.STATE_PATH_PRICE_ALERT, {"unter_schwelle": False})

        aktuell_unter_schwelle = pct_change <= config.TAGESVERLUST_SCHWELLE_PCT
        war_unter_schwelle = state.get("unter_schwelle", False)

        if aktuell_unter_schwelle and not war_unter_schwelle:
            msg = (f"🚨 **SCHWELLE UNTERSCHRITTEN ({config.WKN})** 🚨\n"
                   f"Tagesveränderung: **{pct_change:+.2f}%** "
                   f"(Schwelle: {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%)\n"
                   f"Aktueller Kurs: **{current_price:.3f}€**")
            try:
                requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            except Exception as e:
                logging.error(f"Discord Schwellen-Alarm Fehler: {e}")
            state["unter_schwelle"] = True

        elif not aktuell_unter_schwelle and war_unter_schwelle:
            msg = (f"✅ **Entwarnung ({config.WKN})**\n"
                   f"Tagesveränderung wieder über {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%: "
                   f"**{pct_change:+.2f}%**\n"
                   f"Aktueller Kurs: **{current_price:.3f}€**")
            try:
                requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
            except Exception as e:
                logging.error(f"Discord Entwarnung Fehler: {e}")
            state["unter_schwelle"] = False

        # Nur bei echtem Zustandswechsel schreiben (siehe Kommentar oben bei
        # check_and_alert_fetch_failure) - spart GitHub-Commits bei jedem Rerun.
        if state.get("unter_schwelle") != war_unter_schwelle:
            gh_write(config.STATE_PATH_PRICE_ALERT, state, message="update price alert state [skip ci]")


    check_and_send_price_updates(tages_verenderung_pct, aktueller_kurs)

    heutige_monate_anzahl = max(0, (now_berlin.year - start_dt.year) * 12 + (now_berlin.month - start_dt.month))
    if now_berlin.day < start_dt.day:
        heutige_monate_anzahl -= 1

    gesamt_entnommen = entnommen_aktiv
    brutto_ist = (stueckzahl_aktiv + zusaetzliche_stueckzahl_sparplan) * aktueller_kurs
    netto_ist = brutto_ist - gesamt_entnommen
    gewinn_brutto = brutto_ist - startkapital_aktiv
    rendite_ist_pct = ((aktueller_kurs - kaufkurs_aktiv) / kaufkurs_aktiv) * 100

    # Reale Variante fuer die aktuellen Kennzahlen (Stückzahl nach echten Verkäufen)
    stueckzahl_real_ist = df_chart["Stueckzahl_Real"].iloc[-1] if not df_chart.empty else stueckzahl_aktiv
    depotwert_real_ist = (stueckzahl_real_ist + zusaetzliche_stueckzahl_sparplan) * aktueller_kurs

    kumulierte_sparrate_marktwert = zusaetzliche_stueckzahl_sparplan * aktueller_kurs

    sim_b = brutto_ist
    monate_bis_ziel = 0
    while sim_b < 100000.0 and monate_bis_ziel < 600:
        sim_b = (sim_b * (1 + erwarteter_zins_mo)) - entnommen_aktiv + sparrate_aktiv
        monate_bis_ziel += 1

    monate_namen = {1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni", 
                    7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember"}

    if brutto_ist >= 100000.0:
        meilenstein_datum_str, meilenstein_details_str = "Bereits erreicht", "Ziel erreicht"
    elif monate_bis_ziel < 600:
        ms_date = (now_berlin.replace(tzinfo=None) + pd.DateOffset(months=monate_bis_ziel)).date()
        meilenstein_datum_str = f"{monate_namen[ms_date.month]} {ms_date.year}"
        meilenstein_details_str = f"In ca. {monate_bis_ziel // 12} Jahren & {monate_bis_ziel % 12} Monaten"
    else:
        meilenstein_datum_str, meilenstein_details_str = "> 50 Jahre", "Unrealistisch"

    richtung = "up" if tages_verenderung_pct >= 0 else "down"
    differenz_zum_vortag = aktueller_kurs - vortag_kurs

    # ---------- KURS-KOPF: der Kurs ist die eine Zahl, die zaehlt ----------
    live_markup = (
        '<span class="live-pill"><span class="live-dot"></span>Live</span>'
        if is_live_data else
        '<span class="live-pill offline"><span class="live-dot offline"></span>Keine Live-Daten</span>'
    )

    def de_zahl(wert, nachkomma=3):
        """Deutsche Schreibweise (Punkt = Tausender, Komma = Dezimal) - bewusst
        nur auf den ZAHLENWERT angewendet, nicht auf das umgebende HTML."""
        s = f"{wert:,.{nachkomma}f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    # ---------- PERFORMANCE JE ZEITRAUM (Tag/Woche/Monat/Jahr/seit Kauf) ----------
    # Referenzkurse werden aus der Kurshistorie berechnet (letzter Schlusskurs
    # am/vor dem Stichtag) - generisch fuer jedes Instrument, kein Scraping
    # einer produktspezifischen Seite mehr. "Tag" nutzt den Vortageskurs,
    # "seit Kauf" die bereits berechneten gewinn_brutto/rendite_ist_pct.
    #
    # WICHTIG - Einschraenkung: die €-Betraege je Zeitraum unterstellen eine ueber
    # den jeweiligen Zeitraum konstante Stueckzahl (aktuelle Stueckzahl rueckwirkend
    # angewendet). Bei zwischenzeitlichen Sparplan-Kaeufen ist das eine Naeherung.
    gesamt_stueckzahl_perf = stueckzahl_aktiv + zusaetzliche_stueckzahl_sparplan

    _hist_haupt = get_kurshistorie(
        config.LS_INSTRUMENT_ID, heute_date - datetime.timedelta(days=420), heute_date
    )
    periods_kurs = berechne_zeitraeume(aktueller_kurs, vortag_kurs, _hist_haupt, heute_date)

    periods_depot = [(lbl, d * gesamt_stueckzahl_perf, p) for lbl, d, p in periods_kurs]
    periods_depot.append(("seit Kauf", gewinn_brutto, rendite_ist_pct))

    def perf_zeilen_html(zeilen, nachkomma, kopfzeile=None, fusszeile=""):
        """Rendert die Zeitraum-Zeilen INNERHALB einer Kachel: hairline-getrennt,
        Betrag und Prozent rechtsbuendig nebeneinander, eingefaerbt nach Vorzeichen.
        kopfzeile: optionales (label, wert_html) Tupel fuer eine neutrale
        Referenzzeile ohne +/- Faerbung (z.B. der Vortageskurs) ganz oben.
        fusszeile: fertiges Zeilen-HTML, das unten angehaengt wird (z.B. Höchststand)."""
        html = ""
        if kopfzeile:
            k_label, k_wert = kopfzeile
            html += (
                f'<div class="perf-row"><span class="perf-label">{k_label}</span>'
                f'<span class="perf-vals"><span class="neutral">{k_wert}</span></span></div>'
            )
        for label, diff, prozent in zeilen:
            cls = "up" if diff >= 0 else "down"
            html += (
                f'<div class="perf-row"><span class="perf-label">{label}</span>'
                f'<span class="perf-vals">'
                f'<span class="{cls}">{"+" if diff >= 0 else ""}{de_zahl(diff, nachkomma)} €</span>'
                f'<span class="{cls}">{"+" if prozent >= 0 else ""}{de_zahl(prozent, 2)} %</span>'
                f'</span></div>'
            )
        html += fusszeile
        return f'<div class="perf-table">{html}</div>' if html else ""

    # Positionsliste einmalig laden - wird sowohl von der Verwaltung unten
    # als auch von den Positionskacheln weiter unten genutzt.
    alle_positionen = lade_positionen()

    # ---------- POSITIONEN VERWALTEN (anlegen / aendern / loeschen) ----------
    def instrument_suchblock(prefix, label="WKN, ISIN oder Name suchen"):
        """Wiederverwendbarer Suchblock. Muss AUSSERHALB eines st.form stehen,
        da Formulare erst beim Submit einen Rerun ausloesen - die Suche soll
        aber sofort reagieren. Sucht bei Eingabe (Enter/Verlassen des Felds),
        ohne extra Klick. Gibt den gewaehlten Treffer als dict zurueck (oder None).

        prefix trennt die session_state-Keys, damit jede Position ihren
        eigenen, unabhaengigen Suchzustand hat."""
        suchbegriff = st.text_input(
            label, key=f"{prefix}_suche",
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
            st.caption("⚠️ Keine Treffer – Schreibweise prüfen oder Instrument-ID manuell eintragen.")
            return None

        optionen = {
            f"{t['name']} · {t['kategorie']} · WKN {t['wkn'] or '–'}": t
            for t in treffer
        }
        wahl = st.selectbox("Treffer auswählen", list(optionen.keys()), key=f"{prefix}_wahl")
        gewaehlt = optionen[wahl]

        live_kurs, _, _ = get_live_kurs(gewaehlt["instrument_id"])
        kurs_txt = f"{de_zahl(live_kurs)} €" if live_kurs else "kein Kurs verfügbar"
        st.caption(
            f"→ **{gewaehlt['name']}** · ID {gewaehlt['instrument_id']} · "
            f"ISIN {gewaehlt['isin'] or '–'} · aktuell {kurs_txt}"
        )
        return gewaehlt

    # ---------- HIGH WATERMARK: als Zeile in der Kurskachel ----------
    # Bewusst KEINE eigene Kachel mehr: der Hoechststand ist eine Eigenschaft
    # des Kurses, keine gleichrangige Kennzahl. Als Zeile unter Vortag/Tag/
    # Woche steht er im richtigen Kontext und spart eine ganze Kachel.
    hw_abstand = aktueller_kurs - high_watermark_anzeige
    hw_abstand_pct = (hw_abstand / high_watermark_anzeige * 100) if high_watermark_anzeige else 0.0
    hw_am_hoch = hw_abstand >= -0.0005  # Toleranz gegen Rundungsrauschen

    if hw_am_hoch:
        hw_status_chip = '<span class="hw-pill">Allzeithoch</span>'
        hw_zeile = (
            '<div class="perf-row"><span class="perf-label">Höchststand</span>'
            f'<span class="perf-vals"><span class="neutral">{de_zahl(high_watermark_anzeige)} €</span>'
            '<span class="up">erreicht</span></span></div>'
        )
    else:
        hw_status_chip = ""
        hw_zeile = (
            '<div class="perf-row"><span class="perf-label">Höchststand</span>'
            f'<span class="perf-vals"><span class="neutral">{de_zahl(high_watermark_anzeige)} €</span>'
            f'<span class="down">{de_zahl(hw_abstand_pct, 2)} %</span></span></div>'
        )

    kurs_karte = (
        '<div class="quote">'
        f'<div class="q-name">Hauptindizes Global · {config.WKN}</div>'
        '<div class="price-line">'
        f'<span class="q-price">{de_zahl(aktueller_kurs)} €</span>'
        f'{live_markup}'
        f'{hw_status_chip}'
        '</div>'
        # Hoechststand als letzte Zeile der Zeitraum-Tabelle - dadurch steht er
        # im selben Raster wie Vortag/Tag/Woche/Monat/Jahr statt in eigener Kachel.
        + perf_zeilen_html(periods_kurs, 3,
                           kopfzeile=("Vortag", f"{de_zahl(vortag_kurs)} €"),
                           fusszeile=hw_zeile)
        + f'<div class="card-footnote">Lang &amp; Schwarz · Stand: {letztes_update_zeit} · '
          f'Höchststand vom {high_watermark_datum}, ab dort '
          f'{config.PERFORMANCE_FEE_PCT:.0f} % Performance Fee</div>'
        + '</div>'
    )
    # ---------- BEOBACHTETE WERTE: reine Kursanzeige, NICHT im Depot ----------
    def beobachtungs_karte(eintrag, fortschritt=None):
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
                f'<div class="q-name">{eintrag.get("name", "")} · {eintrag.get("wkn", "")}</div>'
                '<div class="price-line">'
                '<span class="q-price">–</span>'
                '<span class="meta-chip">keine Live-Daten</span>'
                '</div>'
                '<div class="card-footnote">ls-tc.de liefert für diesen Wert gerade '
                'keine Kurse. Instrument-ID prüfen oder später erneut versuchen.</div>'
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
                           else f'<span class="down">{de_zahl(b_abstand_pct, 2)} %</span>')
            b_hw_zeile = (
                '<div class="perf-row"><span class="perf-label">Höchststand</span>'
                f'<span class="perf-vals"><span class="neutral">{de_zahl(b_hoch)} €</span>'
                f'{b_wert_html}</span></div>'
            )
            b_fuss = (f'Lang &amp; Schwarz · Höchststand vom {b_hoch_datum} '
                      f'(aus verfügbarer Kurshistorie) · nicht im Depot enthalten')
        else:
            b_fuss = 'Lang &amp; Schwarz · nicht im Depot enthalten'

        return (
            '<div class="quote">'
            f'<div class="q-name">{eintrag.get("name", "")} · {eintrag.get("wkn", "")}</div>'
            '<div class="price-line">'
            f'<span class="q-price">{de_zahl(b_kurs)} €</span>'
            '<span class="live-pill"><span class="live-dot"></span>Live</span>'
            '<span class="meta-chip">Beobachtung</span>'
            '</div>'
            + perf_zeilen_html(
                b_perioden, 3,
                kopfzeile=("Vortag", f"{de_zahl(b_vortag)} €") if b_vortag else None,
                fusszeile=b_hw_zeile)
            + f'<div class="card-footnote">{b_fuss}</div>'
            '</div>'
        )

    beobachtung = [e for e in lade_beobachtung() if e.get("instrument_id")]

    # ---------- PROGNOSE-BASIS FUER BEOBACHTUNGSWERTE ----------
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
    _beob_gesamt = len(beobachtung)
    for _beob_i, _eintrag in enumerate(beobachtung):
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

    if beobachtung:
        # EIGENES FRAGMENT: beim Umschalten wird NUR dieser Bereich neu
        # gezeichnet, nicht das komplette Dashboard. Vorher lief bei jedem
        # Wechsel der gesamte Aufbau erneut - inkl. Positionsliste, Benchmarks
        # und aller Kacheln, was die spuerbare Wartezeit verursacht hat.
        @st.fragment
        def _render_kursansicht():
            # Umschalter bewusst adaptiv:
            #   bis 3 Werte -> Pills (ein Tap, alles sichtbar)
            #   ab 4 Werten -> Dropdown (Pills braeuchten sonst 3+ Zeilen)
            # Die WKN wird aus den Beschriftungen entfernt - sie steht ohnehin
            # in der Kachel darunter und macht die Buttons nur breiter.
            def _kurzname(text, fallback=""):
                ohne_wkn = re.sub(r"\s*\([^)]*\)\s*$", "", (text or "").strip())
                return ohne_wkn or fallback or "Wert"

            kurs_optionen = ["Hauptindizes Global"] + [
                _kurzname(e.get("name"), e.get("wkn")) for e in beobachtung
            ]
            # Doppelte Namen eindeutig machen, sonst laesst sich die Auswahl
            # nicht zuordnen (beide Widgets nutzen die Beschriftung als Schluessel).
            gesehen = {}
            for i, opt in enumerate(kurs_optionen):
                if opt in gesehen:
                    gesehen[opt] += 1
                    kurs_optionen[i] = f"{opt} ({gesehen[opt]})"
                else:
                    gesehen[opt] = 1

            if len(kurs_optionen) <= 3:
                auswahl = st.pills(
                    "Wert wählen", kurs_optionen, default=kurs_optionen[0],
                    key="kurs_ansicht_wahl", label_visibility="collapsed",
                )
            else:
                auswahl = st.selectbox(
                    "Wert wählen", kurs_optionen,
                    key="kurs_ansicht_wahl_select",
                )

            # Abwaehlen ist bei st.pills moeglich - dann auf den ersten Wert
            # zurueckfallen, damit nie eine leere Ansicht entsteht.
            if auswahl not in kurs_optionen:
                auswahl = kurs_optionen[0]

            if auswahl == kurs_optionen[0]:
                st.markdown(kurs_karte, unsafe_allow_html=True)
                return

            eintrag = beobachtung[kurs_optionen.index(auswahl) - 1]
            platz = st.empty()

            fortschritt = fortschritt_anzeige(platz)

            try:
                # Beide Schritte sind eigene Netzabrufe (bzw. Cache-Treffer) -
                # der Fortschritt bildet echte Arbeitsschritte ab, nicht bloss
                # eine Animation.
                fortschritt(15, f"Lade Kurs für {auswahl} …")
                karte = beobachtungs_karte(eintrag, fortschritt=fortschritt)
                platz.empty()
                st.markdown(karte, unsafe_allow_html=True)
            except Exception as e:
                platz.empty()
                st.error(f"⚠️ Beobachtungswert konnte nicht geladen werden: {e}")
                notify_app_error(f"Beobachtung-{eintrag.get('wkn', '?')}", e)

        _render_kursansicht()
    else:
        st.markdown(kurs_karte, unsafe_allow_html=True)

    # ---------- HERO: Depotwert ----------
    sparplan_zusatz = (
        f" · davon {zusaetzliche_stueckzahl_sparplan:.4f} aus Sparplan"
        if zusaetzliche_stueckzahl_sparplan > 0 else ""
    )
    richtung_gewinn = "up" if gewinn_brutto >= 0 else "down"
    depot_karte = (
        '<div class="hero">'
        '<div class="hero-label">Depotwert</div>'
        '<div class="price-line">'
        f'<span class="hero-val">{fmt(brutto_ist, 2)}</span>'
        # Ø p.a. bewusst als Rendite des PRODUKTS (Median ueber die volle
        # Historie), nicht als eigene Kaufrendite: so steht ueberall im
        # Dashboard dieselbe Zahl, mit der auch simuliert wird. Gewinn und
        # Rendite in den Zeilen darunter bleiben die eigenen, realisierten Werte.
        '<span class="stat-chip"><span class="stat-chip-label">Ø p.a.</span>'
        f'<span class="stat-chip-val">{prognose_rendite_pa:.1f} %</span></span>'
        '</div>'
        f'{perf_zeilen_html(periods_depot, 2)}'
        f'<div class="card-footnote">{stueckzahl_aktiv + zusaetzliche_stueckzahl_sparplan:.4f} '
        f'Anteile{sparplan_zusatz}</div>'
        '</div>'
    )
    # Alle Positionskacheln werden gesammelt und weiter unten gemeinsam in
    # einem horizontal wischbaren Container ausgegeben (Swipe statt langer
    # Scrollstrecke - auf dem Smartphone deutlich angenehmer).
    # (Label, HTML) je Position - das Label wird zur Tab-Beschriftung.
    positions_karten = [(alle_positionen[0].get("name", "Depotwert"), depot_karte)]

    # =================================================================
    # WEITERE POSITIONEN + GESAMTUEBERSICHT
    # =================================================================
    # Die erste Position ist die oben ausfuehrlich dargestellte Hauptposition
    # (sie speist auch alle Tabs/Charts). Jede weitere Position bekommt eine
    # eigene Kachel im selben Design; darunter folgt die Depot-Gesamtsumme.
    weitere_positionen = alle_positionen[1:] if len(alle_positionen) > 1 else []

    # Kennzahlen der Hauptposition als Startwert der Gesamtsumme
    gesamt_wert = brutto_ist
    gesamt_einstand = startkapital_aktiv
    gesamt_zeitraeume = {lbl: betrag for lbl, betrag, _ in periods_depot if lbl != "seit Kauf"}
    positionen_ok = True

    # Sammelt fuer jede Position mit echten Kursdaten die Basis-Kennzahlen
    # (Kapital, aktueller Wert, CAGR, Kaufdatum) - Grundlage fuer die Auswahl
    # in der Zukunfts-Prognose weiter unten. Beobachtungswerte fehlen hier
    # bewusst: ohne investiertes Kapital ergibt eine Kapitalprognose keinen Sinn.
    prognose_optionen = [{
        "name": alle_positionen[0].get("name", "Depotwert"),
        "startkapital": startkapital_aktiv,
        "aktueller_wert": brutto_ist,
        # Zukunftsrate (Produkt-Historie), NICHT die eigene Kaufrendite -
        # siehe Kommentar bei prognose_rendite_pa weiter oben.
        "cagr_pa": prognose_rendite_pa,
        "cagr_details": prognose_rendite_details,
        "kaufdatum": kaufdatum_aktiv,
        "sparrate": sparrate_aktiv,
        "entnahme": entnommen_aktiv,
        # Kursreihe fuer die Bandbreiten-Simulation weiter unten (Volatilitaet
        # und Drift werden daraus geschaetzt, nicht nur die Endpunkte).
        "kursreihe": df_chart["Close"] if not df_chart.empty else None,
        # Fuer den Szenario-Simulator: erlaubt, die Kurshistorie des
        # PRODUKTS zu laden (unabhaengig vom eigenen Kaufzeitpunkt).
        "instrument_id": config.LS_INSTRUMENT_ID,
        "wkn": config.WKN,
    }]

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
                karte = (
                    '<div class="hero">'
                    f'<div class="hero-label">{p_name} · {pos.get("wkn", "")}</div>'
                    '<div class="price-line">'
                    f'<span class="hero-val">{fmt(p_einstand, 2)}</span>'
                    '<span class="meta-chip">ohne Kursquelle</span>'
                    '</div>'
                    f'<div class="card-footnote">{p_stueck:.4f} Anteile · '
                    f'Kauf am {p_kaufdatum.strftime("%d.%m.%Y")} zu {de_zahl(float(pos["kaufkurs"]), 2)} € · '
                    'Instrument-ID ergänzen, um Kurse und Performance zu sehen</div>'
                    '</div>'
                )
                positions_karten.append((p_name, karte))
                continue

            p_kurs, p_vortag, p_quelle = get_live_kurs(pos["instrument_id"])
            if p_kurs is None:
                positionen_ok = False
                st.warning(f"⚠️ Für **{p_name}** sind gerade keine Live-Daten verfügbar.")
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
            for lbl, betrag, _ in p_perioden_depot:
                if lbl != "seit Kauf":
                    gesamt_zeitraeume[lbl] = gesamt_zeitraeume.get(lbl, 0.0) + betrag

            p_tage = max(1, (heute_date - p_kaufdatum).days)
            p_cagr = (((p_wert / p_einstand) ** (365.25 / p_tage)) - 1) * 100 if p_einstand > 0 and p_wert > 0 else 0.0
            # Fuer die Prognose die Produkt-Rendite (Median), fuer die Kachel
            # weiter unten die realisierte Rendite p_cagr - zwei Fragen, zwei Zahlen.
            p_prognose_pa, p_prognose_details = produkt_rendite_pa(pos["instrument_id"], heute_date)
            if p_prognose_pa is None:
                p_prognose_pa, p_prognose_details = p_cagr, []

            # Sparrate/Entnahme sind bislang nur fuer die Hauptposition
            # konfigurierbar - fuer weitere Positionen daher 0.
            prognose_optionen.append({
                "name": p_name,
                "startkapital": p_einstand,
                "aktueller_wert": p_wert,
                "cagr_pa": p_prognose_pa,
                "cagr_details": p_prognose_details,
                "kaufdatum": p_kaufdatum,
                "sparrate": 0.0,
                "entnahme": 0.0,
                "kursreihe": p_hist if p_hist is not None and not p_hist.empty else None,
                "instrument_id": pos["instrument_id"],
                "wkn": pos.get("wkn", ""),
            })

            karte = (
                '<div class="hero">'
                f'<div class="hero-label">{pos.get("name", "Position")} · {pos.get("wkn", "")}</div>'
                '<div class="price-line">'
                f'<span class="hero-val">{fmt(p_wert, 2)}</span>'
                '<span class="stat-chip"><span class="stat-chip-label">Ø p.a.</span>'
                f'<span class="stat-chip-val">{p_prognose_pa:.1f} %</span></span>'
                f'<span class="meta-chip">Kurs {de_zahl(p_kurs)} €</span>'
                '</div>'
                f'{perf_zeilen_html(p_perioden_depot, 2)}'
                f'<div class="card-footnote">{p_stueck:.4f} Anteile · '
                f'Kauf am {p_kaufdatum.strftime("%d.%m.%Y")} zu {de_zahl(float(pos["kaufkurs"]), 2)} €</div>'
                '</div>'
            )
            positions_karten.append((p_name, karte))

        except Exception as e:
            positionen_ok = False
            st.error(f"⚠️ Position **{pos.get('name', '?')}** konnte nicht berechnet werden: {e}")
            notify_app_error(f"Position-{pos.get('id', '?')}", e)

    # Beobachtungswerte (symbolische Prognose-Basis) hinten anfuegen - erst
    # die echten Positionen (reales Kapital), dann die hypothetischen.
    prognose_optionen.extend(prognose_beobachtung_optionen)

    # ---------- GESAMTUEBERSICHT (nur sinnvoll ab 2 Positionen) ----------
    if weitere_positionen:
        gesamt_gewinn = gesamt_wert - gesamt_einstand
        gesamt_rendite = (gesamt_gewinn / gesamt_einstand * 100) if gesamt_einstand else 0.0

        # Prozent je Zeitraum aus den summierten €-Betraegen ableiten, NICHT die
        # Einzelprozente mitteln - Positionen haben unterschiedliche Groessen,
        # ein einfacher Mittelwert waere schlicht falsch.
        gesamt_perioden = []
        for lbl in ["Tag", "Woche", "Monat", "Jahr"]:
            if lbl in gesamt_zeitraeume:
                betrag = gesamt_zeitraeume[lbl]
                basis = gesamt_wert - betrag
                pct = (betrag / basis * 100) if basis else 0.0
                gesamt_perioden.append((lbl, betrag, pct))
        gesamt_perioden.append(("seit Kauf", gesamt_gewinn, gesamt_rendite))

        # Nur Positionen mit Kursquelle sind in der Summe enthalten - das muss
        # sichtbar sein, sonst wirkt eine unvollstaendige Summe wie die volle.
        anzahl_gezaehlt = sum(1 for p in alle_positionen if p.get("instrument_id"))
        anzahl_gesamt = len(alle_positionen)
        if anzahl_gezaehlt < anzahl_gesamt:
            positions_chip = f"{anzahl_gezaehlt} von {anzahl_gesamt} Positionen"
        else:
            positions_chip = f"{anzahl_gesamt} Positionen"

        hinweis = "" if positionen_ok else " · ⚠️ unvollständig, s. Warnungen oben"
        if anzahl_gezaehlt < anzahl_gesamt:
            hinweis += " · Positionen ohne Kursquelle nicht enthalten"
        gesamt_karte = (
            '<div class="hero gesamt">'
            '<div class="hero-label">Depot gesamt</div>'
            '<div class="price-line">'
            f'<span class="hero-val">{fmt(gesamt_wert, 2)}</span>'
            f'<span class="meta-chip">{positions_chip}</span>'
            '</div>'
            f'{perf_zeilen_html(gesamt_perioden, 2)}'
            f'<div class="card-footnote">Einstand {fmt(gesamt_einstand, 2)}{hinweis}</div>'
            '</div>'
        )
        st.markdown(gesamt_karte, unsafe_allow_html=True)

    # ---------- POSITIONSKACHELN (Detailansicht je Position) ----------
    # Bei nur einer Position waere ein Swipe-Container sinnlos - dann normal
    # rendern. Ab zwei Positionen: scroll-snap-Container, in dem jede Kachel
    # die volle Breite einnimmt und beim Wischen sauber einrastet.
    if len(positions_karten) > 1:
        # st.tabs statt eines CSS-Swipe-Containers: auf iOS blockiert Streamlits
        # eigenes Container-Styling horizontales Wischen zuverlaessig, Tabs
        # funktionieren dagegen ueberall per Tap (und lassen sich bei vielen
        # Positionen zusaetzlich seitlich scrollen).
        tab_labels = [tab_label(lbl) for lbl, _ in positions_karten]
        for tab, (_, karte_html) in zip(st.tabs(tab_labels), positions_karten):
            with tab:
                st.markdown(karte_html, unsafe_allow_html=True)
    else:
        st.markdown(positions_karten[0][1], unsafe_allow_html=True)



    # ---------- Eingaben ----------
    # Wichtig: "value=" nur beim allerersten Erstellen des Widgets mitgeben,
    # NICHT bei jedem Rerun (klassischer Streamlit-Stolperstein).
    st.markdown('<div class="abschnitt">⚙️ Einstellungen</div>', unsafe_allow_html=True)

    with st.expander("🛠️ Kauf, Kapital, Sparrate und Entnahme anpassen", expanded=False):
        # Felder bewusst untereinander (keine Spalten) - auf dem Smartphone
        # sind nebeneinanderliegende Zahlenfelder samt Steppern sehr fummelig.
        kd_kwargs = dict(
            key="haupt_kaufdatum_input",
            help="Bestimmt den Startpunkt aller Berechnungen und Charts.",
        )
        if "haupt_kaufdatum_input" not in st.session_state:
            kd_kwargs["value"] = kaufdatum_aktiv
        st.date_input("Kaufdatum", **kd_kwargs)

        st.checkbox(
            "Kaufkurs automatisch aus der Kurshistorie am Kaufdatum holen",
            key="haupt_kaufkurs_auto", value=kaufkurs_auto,
            help="Nimmt den letzten Schlusskurs am oder vor dem Kaufdatum. "
                 "Ausschalten, um deinen tatsächlich gezahlten Kurs einzutragen "
                 "(z. B. inkl. Spread oder bei untertägigem Kauf).",
        )

        if kaufkurs_auto:
            if kaufkurs_ermittelt:
                st.success(
                    f"Kurs am {kaufdatum_aktiv.strftime('%d.%m.%Y')}: "
                    f"**{de_zahl(kaufkurs_ermittelt, 4)} €** "
                    f"→ {startkapital_aktiv / kaufkurs_ermittelt:.4f} Anteile"
                )
            else:
                st.warning(
                    f"Für den {kaufdatum_aktiv.strftime('%d.%m.%Y')} liegt kein Kurs vor "
                    f"(Historie reicht nicht zurück). Es gilt ersatzweise "
                    f"{de_zahl(kaufkurs_aktiv, 4)} €."
                )
        else:
            kk_kwargs = dict(
                min_value=0.0, step=0.01, format="%.4f", key="haupt_kaufkurs_input",
                help="Dein tatsächlich gezahlter Kurs je Anteil.",
            )
            if "haupt_kaufkurs_input" not in st.session_state:
                kk_kwargs["value"] = kaufkurs_aktiv
            st.number_input("Kaufkurs (€)", **kk_kwargs)

        ak_kwargs = dict(
            min_value=0.0, step=100.0, key="haupt_startkapital_input",
            help="Investiertes Kapital - die Stückzahl ergibt sich daraus "
                 "automatisch (Kapital ÷ Kaufkurs).",
        )
        if "haupt_startkapital_input" not in st.session_state:
            ak_kwargs["value"] = startkapital_aktiv
        st.number_input("Anfangskapital (€)", **ak_kwargs)
        st.caption(f"Ergibt aktuell **{stueckzahl_aktiv:.4f} Anteile** "
                   f"zu {de_zahl(kaufkurs_aktiv, 4)} €")

        sparrate_kwargs = dict(
            min_value=0.0, step=10.0, key="haupt_sparrate_input",
            help="Zusätzliche monatliche Einzahlung (Sparplan) - kauft laufend Anteile dazu und "
                 "fließt in die Zukunfts-Hochrechnungen ein. Ändert die bisherige Chart-Historie nicht.",
        )
        if "haupt_sparrate_input" not in st.session_state:
            sparrate_kwargs["value"] = 0.0
        st.number_input("Monatliche Sparrate (€)", **sparrate_kwargs)

        ek_kwargs = dict(
            min_value=0.0, step=10.0, key="haupt_entnommen_input",
            help="Standard: 0€ - hier frei einstellbar, ganz wie du es tatsächlich entnommen hast.",
        )
        if "haupt_entnommen_input" not in st.session_state:
            ek_kwargs["value"] = entnommen_aktiv
        st.number_input("Monatliche Entnahme (€)", **ek_kwargs)

    # Sicherheitsnetz: falls keine Ansicht gegriffen hat (z.B. unbekannter
    # gespeicherter Wert in der Auswahl), darf die Anzeige nicht stehenbleiben.
    lade_fertig()

    # ---------- BEOBACHTUNGSLISTE VERWALTEN ----------
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
                     "Instrument-ID hinterlegt - kein Suchen nötig.",
            )
            if v_btn.button("Übernehmen", width="stretch", key="beob_vorlage_btn"):
                _liste = lade_beobachtung()
                _liste.append({
                    "id": f"beob-{int(datetime.datetime.now().timestamp())}",
                    "name": v_wahl, "wkn": "",
                    "instrument_id": _vorschlaege[v_wahl],
                })
                if speichere_beobachtung(_liste, "beobachtung aus benchmark [skip ci]"):
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
                nb_inst = st.number_input("Instrument-ID (ls-tc.de)", min_value=0, step=1,
                                          value=bv_inst, key=f"bi_{b_suffix}")

                bc_save, bc_del = st.columns(2)
                b_gespeichert = bc_save.form_submit_button("💾 Speichern", width="stretch")
                b_geloescht = bc_del.form_submit_button("🗑️ Entfernen", width="stretch")

                if b_gespeichert:
                    beob_liste[b_idx] = {
                        "id": eintrag.get("id") or f"beob-{int(datetime.datetime.now().timestamp())}",
                        "name": nb_name, "wkn": nb_wkn,
                        "instrument_id": int(nb_inst) if nb_inst else None,
                    }
                    if speichere_beobachtung(beob_liste, "beobachtung geaendert [skip ci]"):
                        for k in (f"beob_edit_{b_idx}_suche", f"beob_edit_{b_idx}_letzter",
                                  f"beob_edit_{b_idx}_treffer", f"beob_edit_{b_idx}_wahl"):
                            st.session_state.pop(k, None)
                        st.success("Gespeichert.")
                        st.rerun()
                    else:
                        st.error("Speichern fehlgeschlagen (kein persistenter State?).")

                if b_geloescht:
                    beob_liste.pop(b_idx)
                    if speichere_beobachtung(beob_liste, "beobachtung entfernt [skip ci]"):
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
                "Instrument-ID (ls-tc.de)", min_value=0, step=1,
                value=int(b_gewaehlt["instrument_id"]) if b_gewaehlt else 0,
                help="Wird durch die Suche oben automatisch gefüllt. Ohne ID kann "
                     "kein Kurs angezeigt werden - hier also Pflicht.",
            )

            if st.form_submit_button("👁️ Zur Beobachtung hinzufügen", width="stretch"):
                if not bneu_name or not bneu_inst:
                    st.error("Bitte Name und Instrument-ID angeben.")
                else:
                    b_test, _, _ = get_live_kurs(int(bneu_inst))
                    if b_test is None:
                        st.error(
                            f"Für Instrument-ID {int(bneu_inst)} liefert ls-tc.de keine "
                            "Kursdaten. Bitte die ID prüfen."
                        )
                    else:
                        beob_liste.append({
                            "id": f"beob-{int(datetime.datetime.now().timestamp())}",
                            "name": bneu_name, "wkn": bneu_wkn,
                            "instrument_id": int(bneu_inst),
                        })
                        if speichere_beobachtung(beob_liste, "beobachtung angelegt [skip ci]"):
                            for k in ("beob_neu_suche", "beob_neu_letzter",
                                      "beob_neu_treffer", "beob_neu_wahl"):
                                st.session_state.pop(k, None)
                            st.success(f"„{bneu_name}“ hinzugefügt "
                                       f"(aktueller Kurs {de_zahl(b_test)} €).")
                            st.rerun()
                        else:
                            st.error("Hinzufügen fehlgeschlagen (kein persistenter State?).")

    # ---------- POSITIONEN VERWALTEN (anlegen / aendern / loeschen) ----------
    with st.expander("➕ Positionen verwalten", expanded=False):
        if not GH_STATE_READY:
            st.warning(
                "Ohne persistenten State (GITHUB_REPO/GITHUB_TOKEN) gehen angelegte "
                "Positionen beim nächsten Neustart verloren."
            )
        st.caption(
            "WKN oder ISIN ins Suchfeld eingeben – Name und Instrument-ID werden "
            "automatisch übernommen. Die erste Position ist die Hauptposition, "
            "sie speist zusätzlich alle Charts und Prognose-Tabs."
        )

        # --- Bestehende Positionen bearbeiten/loeschen ---
        for idx, pos in enumerate(alle_positionen):
            rolle = "Hauptposition" if idx == 0 else f"Position {idx + 1}"
            st.markdown("---")
            st.markdown(f"**{rolle}: {pos.get('name', '')}**")

            # Suchblock ausserhalb des Formulars - erlaubt, jederzeit ein
            # anderes Wertpapier fuer diese Position zu suchen und zu uebernehmen.
            treffer_edit = instrument_suchblock(
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
                n_wkn = st.text_input("WKN / ISIN", value=v_wkn, key=f"w_{suffix}")
                n_inst = st.number_input(
                    "Instrument-ID (ls-tc.de) – optional", min_value=0, step=1,
                    value=v_inst, key=f"i_{suffix}",
                    help="0 = keine Kursquelle. Die Position wird dann ohne Kurse "
                         "angezeigt und nicht in die Depot-Summe eingerechnet.",
                )
                n_kaufdatum = st.date_input(
                    "Kaufdatum", value=datetime.date.fromisoformat(pos["kaufdatum"]), key=f"d_{idx}")
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
                    alle_positionen[idx] = {
                        "id": pos.get("id") or f"pos-{int(datetime.datetime.now().timestamp())}",
                        "name": n_name, "wkn": n_wkn,
                        "instrument_id": int(n_inst) if n_inst else None,
                        "kaufdatum": n_kaufdatum.isoformat(), "kaufkurs": float(n_kaufkurs),
                        "startkapital": float(n_kapital),
                    }
                    if speichere_positionen(alle_positionen, "position geaendert [skip ci]"):
                        for k in (f"edit_{idx}_suche", f"edit_{idx}_letzter",
                                  f"edit_{idx}_treffer", f"edit_{idx}_wahl"):
                            st.session_state.pop(k, None)
                        st.success("Gespeichert.")
                        st.rerun()
                    else:
                        st.error("Speichern fehlgeschlagen (kein persistenter State?).")

                if geloescht:
                    if len(alle_positionen) <= 1:
                        st.error("Die letzte verbleibende Position kann nicht gelöscht werden.")
                    else:
                        alle_positionen.pop(idx)
                        if speichere_positionen(alle_positionen, "position geloescht [skip ci]"):
                            st.success("Gelöscht.")
                            st.rerun()
                        else:
                            st.error("Löschen fehlgeschlagen (kein persistenter State?).")

        # --- Neue Position anlegen ---
        st.markdown("---")
        st.markdown("**Neue Position hinzufügen**")

        gewaehlt = instrument_suchblock("neu")

        with st.form("pos_form_neu", clear_on_submit=True):
            neu_name = st.text_input(
                "Name", value=(gewaehlt["name"] if gewaehlt else ""),
                placeholder="z. B. MSCI World ETF")
            neu_wkn = st.text_input(
                "WKN / ISIN",
                value=(gewaehlt["wkn"] or gewaehlt["isin"]) if gewaehlt else "",
                placeholder="z. B. A0RPWH")
            neu_inst = st.number_input(
                "Instrument-ID (ls-tc.de) – optional", min_value=0, step=1,
                value=int(gewaehlt["instrument_id"]) if gewaehlt else 0,
                help="Wird durch die Suche oben automatisch gefüllt. Kann auch leer "
                     "(0) bleiben - dann werden für diese Position keine Kurse geladen "
                     "und sie zählt nicht in die Depot-Summe. Jederzeit nachtragbar.",
            )
            neu_datum = st.date_input("Kaufdatum", value=heute_date)
            neu_kurs = st.number_input("Kaufkurs (€)", min_value=0.0, step=0.01, format="%.4f", value=0.0)
            neu_kapital = st.number_input("Investiertes Kapital (€)", min_value=0.0, step=100.0, value=0.0)

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
                            f"Für Instrument-ID {int(neu_inst)} liefert ls-tc.de keine Kursdaten. "
                            "Bitte die ID prüfen – oder das Feld leer (0) lassen und später nachtragen."
                        )
                    else:
                        alle_positionen.append({
                            "id": f"pos-{int(datetime.datetime.now().timestamp())}",
                            "name": neu_name, "wkn": neu_wkn,
                            "instrument_id": int(neu_inst) if neu_inst else None,
                            "kaufdatum": neu_datum.isoformat(), "kaufkurs": float(neu_kurs),
                            "startkapital": float(neu_kapital),
                        })
                        if speichere_positionen(alle_positionen, "position angelegt [skip ci]"):
                            for k in ("neu_suche", "neu_letzter", "neu_treffer", "neu_wahl"):
                                st.session_state.pop(k, None)
                            if test_kurs is not None:
                                st.success(f"„{neu_name}“ angelegt (aktueller Kurs {de_zahl(test_kurs)} €).")
                            else:
                                st.success(f"„{neu_name}“ angelegt – ohne Kursquelle. "
                                           "Instrument-ID kann oben jederzeit ergänzt werden.")
                            st.rerun()
                        else:
                            st.error("Anlegen fehlgeschlagen (kein persistenter State?).")

    # ---------- DATENZEILEN: Sekundaerwerte, eingeklappt ----------
    # Meilenstein und Anfangskapital sind Kontext, keine taeglich relevanten
    # Kennzahlen - eingeklappt konkurrieren sie nicht mit Kurs und Depotwert.
    st.markdown('<div class="abschnitt">📄 Weitere Informationen</div>', unsafe_allow_html=True)

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
                <span class="row-note">Kauf am {kaufdatum_aktiv.strftime('%d.%m.%Y')} zu {de_zahl(kaufkurs_aktiv, 2)} €</span>
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- NETTO-WERTE + Kosten: nur bei Bedarf einblenden ---
    sparrate_note = (
        f" · inkl. {zusaetzliche_stueckzahl_sparplan:.4f} Sparplan-Anteile ({fmt(kumulierte_sparrate_marktwert, 2)})"
        if zusaetzliche_stueckzahl_sparplan > 0 else ""
    )
    with st.expander("💶 Netto-Werte und laufende Kosten", expanded=False):
        st.markdown(f"""
        <div class="rows">
            <div class="row">
                <span class="row-label">Netto (Simulation)</span>
                <span class="row-val">{fmt(netto_ist, 2)}
                    <span class="row-note">Entnahme nur buchhalterisch abgezogen{sparrate_note}</span>
                </span>
            </div>
            <div class="row">
                <span class="row-label">Netto (real verkauft)</span>
                <span class="row-val">{fmt(depotwert_real_ist, 2)}
                    <span class="row-note">{stueckzahl_real_ist:.4f} Anteile nach realer Entnahme, inkl. {config.SPREAD_PCT:.2f} % Spread</span>
                </span>
            </div>
            <div class="row">
                <span class="row-label">Laufende Kosten</span>
                <span class="row-val">{config.ZERTIFIKAT_GEBUEHR_PA_PCT:.2f} % p.a.
                    <span class="row-note">Zertifikatsgebühr, bereits im Kurs eingepreist</span>
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # TABS
    # ---------- ANSICHTSWAHL: Dropdown statt Tab-Leiste ----------
    # Sieben Tabs passen auf keinem Smartphone nebeneinander - man musste sich
    # mit winzigen Pfeilen durchscrollen und sah nie, was es ueberhaupt gibt.
    # Das Dropdown zeigt alle Ansichten auf einen Blick und braucht eine Zeile.
    #
    # Zweiter, wichtigerer Vorteil: Streamlit rendert bei st.tabs IMMER ALLE
    # Inhalte, auch die unsichtbaren - also sieben Charts inkl. aller Abrufe
    # bei jedem Rerun. Hier wird nur die gewaehlte Ansicht berechnet.
    ANSICHTEN = [
        "📈 Vermögens- & Substanzaufbau",
        "🔍 Seit 01.01.2026",
        "🔎 Seit 01.01.2021",
        "🕯️ Tages-Candlestick",
        "🔮 Zukunfts-Prognose",
        "📊 Szenario-Simulator (5 Jahre)",
        "📝 Trader-Log (Trades & Kommentare)",
        "🏆 Watchlist Top 50",
    ]
    # Eigene .abschnitt-Ueberschrift (identisch zu "WEITERE INFORMATIONEN":
    # gleiche Groesse, gleicher Abstand, gleiche Trennlinie). Diesmal OHNE
    # Streamlits label_visibility="collapsed" - das hatte mit unserer
    # !important-Regel kollidiert (!important schlaegt IMMER ein einfaches
    # Inline-style=display:none, das Streamlit fuer "collapsed" setzt - daher
    # die Dopplung zuvor). Stattdessen blenden WIR das native Label selbst
    # per CSS aus, gezielt nur nach diesem Marker (".abschnitt-marker-ansicht")
    # - kein Konflikt mit Streamlit, da Streamlit hier gar nichts versteckt.
    st.markdown(
        '<div class="abschnitt abschnitt-marker-ansicht">Ansicht wählen:</div>',
        unsafe_allow_html=True,
    )
    gewaehlte_ansicht = st.selectbox(
        "Ansicht wählen:", ANSICHTEN, key="ansicht_wahl",
    )

    # Die Render-Funktionen unten arbeiten mit "with tab_x:" - dafuer reicht
    # ein gemeinsamer Container, da ohnehin nur eine Ansicht gezeichnet wird.
    _ansicht_container = st.container()
    tab_wealth = tab_ytd = tab_2021 = tab_candle = _ansicht_container
    tab_forecast = tab_scenarios = tab_trades = _ansicht_container

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _render_wealth():
        try:
            with tab_wealth:
                # Auswahl still aus dem gespeicherten Zustand lesen (Standard: alle an) -
                # der sichtbare Auswahl-Bereich selbst steht weiter unten, direkt vor dem Chart.
                ausgewaehlte_benchmarks = lese_pills_auswahl_still(benchmark_series.keys(), key="benchmark_pills")

                performance_liste_haupt = []
                brutto_reihe = df_chart["Depotwert_Brutto"]
                # WICHTIG: gegen das eingesetzte Kapital rechnen, NICHT gegen
                # brutto_reihe.iloc[0]. Der erste Wert der Reihe ist der erste
                # verfuegbare Schlusskurs der Historie - der kann vom tatsaechlichen
                # Kaufkurs abweichen (Historie reicht weiter zurueck oder beginnt
                # spaeter). Sonst weicht diese Zeile von der "seit Kauf"-Zeile in
                # der Depotwert-Kachel ab, obwohl beide dasselbe messen sollen.
                if not brutto_reihe.empty and startkapital_aktiv > 0:
                    gesamt, monatlich, jaehrlich, diff_euro = berechne_performance_kennzahlen(
                        startkapital_aktiv, brutto_reihe.iloc[-1], kaufdatum_aktiv, heute_date
                    )
                    performance_liste_haupt.append({
                        "Wert": f"Hauptindizes Global ({config.WKN})",
                        "_perf": gesamt, "_monatlich": monatlich, "_jaehrlich": jaehrlich, "_euro": diff_euro,
                        "_q": pct_ueber_tage(brutto_reihe, 91),
                        "_h": pct_ueber_tage(brutto_reihe, 182),
                        "_n": pct_ueber_tage(brutto_reihe, 273),
                        "_z": pct_ueber_tage(brutto_reihe, 365),
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
                    st.caption(
                        f"📅 Eigene Position berechnet ab {kaufdatum_aktiv.strftime('%d.%m.%Y')} "
                        f"(Kaufdatum, gegen eingesetztes Kapital){_start_hinweis}"
                    )
                    performance_liste_haupt.sort(key=lambda x: x["_jaehrlich"], reverse=True)
                    _fokus = kennzahl_umschalter("fokus_haupt", performance_liste_haupt)
                    st.markdown(
                        performance_tabelle_html(performance_liste_haupt, eigene_kennung=config.WKN,
                                                 fokus=_fokus),
                        unsafe_allow_html=True,
                    )

                with st.expander("ℹ️ Erklärung & Vergleichswerte auswählen", expanded=False):
                    st.caption(
                        "„Netto (Simulation)“ zieht die Entnahme nur buchhalterisch vom Depotwert ab. "
                        f"„Real“ verkauft monatlich tatsächlich Anteile zum dann gültigen Geldkurs "
                        f"(inkl. {config.SPREAD_PCT:.2f}% Spread-Annahme) — realistischer, falls du die "
                        "70€/Monat wirklich entnimmst. Die gestrichelten Vergleichslinien zeigen, wie sich "
                        f"{fmt(startkapital_aktiv, 0)} im selben Zeitraum in gängigen Vergleichs-ETFs "
                        "entwickelt hätten (Kosten der ETFs bereits im Kurs enthalten, keine Steuern)."
                    )
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"Hauptindizes Global ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series.keys(), key="benchmark_pills")

                fig_wealth = go.Figure()
                fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Startkapital"], name="Startkapital", line=dict(color="#71717A", width=1.5, dash="dash")))
                fig_wealth.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Depotwert_Brutto"], name="Brutto-Depotwert", line=dict(color="#00C853", width=2.5)))

                legende_eintraege = [("Startkapital", "#71717A"), (f"Hauptindizes Global ({config.WKN})", "#00C853")]
                for label, s in benchmark_series.items():
                    if label not in ausgewaehlte_benchmarks:
                        continue
                    farbe = config.BENCHMARK_COLORS.get(label, "#9E9E9E")
                    fig_wealth.add_trace(go.Scatter(
                        x=df_chart.index, y=s, name=label,
                        line=dict(color=farbe, width=1.5, dash="dashdot"),
                    ))
                    legende_eintraege.append((label, farbe))
    
                fig_wealth.update_layout(
                    paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=80, b=40), height=450,
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="#1A1A1A", type="date", tickfont=dict(color="#A1A1AA")),
                    yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA"), dtick=2000),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_wealth, width="stretch", key="chart_wealth")

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Vermoegensaufbau", e)
    if gewaehlte_ansicht == "📈 Vermögens- & Substanzaufbau":
        melde("ansicht", 0.3, "Baue Vermögensaufbau auf …")
        _render_wealth()
        lade_fertig()

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _render_ytd():
        try:
            with tab_ytd:
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
                    x=eigene_reihe_v2.index, y=eigene_reihe_v2, name=f"Hauptindizes Global ({config.WKN})",
                    line=dict(color="#00C853", width=2.5),
                ))
                benchmark_colors_v2 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
                legende_eintraege_v2 = [("Startkapital", "#71717A"), (f"Hauptindizes Global ({config.WKN})", "#00C853")]
                for i, (label, s) in enumerate(benchmark_series_v2.items()):
                    if label not in ausgewaehlte_v2:
                        continue
                    farbe_v2 = config.BENCHMARK_COLORS.get(label, "#9E9E9E")
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
                        "Wert": f"Hauptindizes Global ({config.WKN})",
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
                    performance_liste_v2.sort(key=lambda x: x["_jaehrlich"], reverse=True)
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
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"Hauptindizes Global ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series_v2.keys(), key="benchmark_v2_pills")

                st.plotly_chart(fig_v2, width="stretch", key="chart_ytd")

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
                v3_start = pd.Timestamp(config.VERGLEICH3_START_DATUM)
                v3_kapital = config.VERGLEICH3_STARTKAPITAL
                master_index_v3 = pd.bdate_range(start=v3_start, end=pd.Timestamp(heute_date))

                # Eigenes Zertifikat: EIGENER, frischer Abruf ab 2021 (df_chart
                # reicht nur bis zum echten Kaufdatum zurueck, hier brauchen wir
                # ggf. deutlich mehr Historie). Wichtig: die Benchmarks werden
                # NICHT auf den (ggf. kuerzeren) Zeitraum des Zertifikats
                # zugeschnitten - sie laufen ueber den vollen 2021-Zeitraum,
                # nur die Zertifikat-Linie beginnt ggf. spaeter (echte Luecke).
                df_chart_v3, _ = get_historical_market_data(config.VERGLEICH3_START_DATUM, heute_date, aktueller_kurs)
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
                    x=eigene_reihe_v3.index, y=eigene_reihe_v3, name=f"Hauptindizes Global ({config.WKN})",
                    line=dict(color="#00C853", width=2.5),
                ))
                benchmark_colors_v3 = ["#AB47BC", "#EC407A", "#8D6E63", "#78909C", "#26C6DA", "#FF7043", "#9CCC65", "#FFCA28", "#5C6BC0", "#8D6E63", "#EF5350"]
                legende_eintraege_v3 = [("Startkapital", "#71717A"), (f"Hauptindizes Global ({config.WKN})", "#00C853")]
                for i, (label, s) in enumerate(benchmark_series_v3.items()):
                    if label not in ausgewaehlte_v3:
                        continue
                    farbe_v3 = config.BENCHMARK_COLORS.get(label, "#9E9E9E")
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
                        "Wert": f"Hauptindizes Global ({config.WKN})",
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
                    performance_liste_v3.sort(key=lambda x: x["_jaehrlich"], reverse=True)
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
                    zeige_chart_legende_liste([("Startkapital", "⚪"), (f"Hauptindizes Global ({config.WKN})", "🟢")])
                    pills_auswahl(benchmark_series_v3.keys(), key="benchmark_v3_pills")

                st.plotly_chart(fig_v3, width="stretch", key="chart_2021")

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
    def _render_trades():
        try:
            def load_db():
                return gh_read(config.STATE_PATH_TRADES_DB, [])

            def save_db(data):
                gh_write(config.STATE_PATH_TRADES_DB, data, message="update trades log [skip ci]")

            db_events = load_db()

            with tab_trades:
                st.markdown("### 📋 Historie")
                if not db_events:
                    st.info("Keine Einträge vorhanden.")
                else:
                    for ev in db_events:
                        st.markdown(f"""
                            <div style="background: #09090B; border: 1px solid #27272A; border-left: 3px solid #29B6F6; padding: 12px; border-radius: 6px; margin-bottom: 10px;">
                                <div style="font-size: 0.75rem; color: #71717A;"><b>[{ev.get('typ','')}]</b> - {ev.get('datum','')}</div>
                                <div style="font-weight: 700; color: #FFFFFF; font-size: 0.95rem;">{ev.get('titel','')}</div>
                                <div style="font-size: 0.85rem; color: #D1D5DB;">{ev.get('inhalt','')}</div>
                            </div>
                        """, unsafe_allow_html=True)

                with st.form("trade_form", clear_on_submit=True):
                    col1, col2, col3 = st.columns([2, 2, 3])
                    with col1: et = st.selectbox("Typ", ["Trade", "Kommentar", "Hinweis"])
                    with col2: ed = st.date_input("Datum", heute_date)
                    with col3: eti = st.text_input("Titel")
                    ei = st.text_area("Details")
                    if st.form_submit_button("Speichern") and eti:
                        db_events.insert(0, {"id": len(db_events) + 1, "typ": et, "datum": ed.strftime("%Y-%m-%d"), "titel": eti, "inhalt": ei})
                        save_db(db_events)
                        st.rerun()

        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Trader-Log", e)
    if gewaehlte_ansicht == "📝 Trader-Log (Trades & Kommentare)":
        melde("ansicht", 0.3, "Lade Trader-Log …")
        _render_trades()
        lade_fertig()

    # Bewusst KEIN @st.fragment: die Funktion schreibt in einen ausserhalb
    # erzeugten Container - Streamlit erlaubt das bei Fragment-Reruns nicht.
    # Noetig ist es auch nicht mehr, da nur die gewaehlte Ansicht laeuft.
    def _render_candle():
        try:
            with tab_candle:
                fig_c = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart["Open"], high=df_chart["High"], low=df_chart["Low"], close=df_chart["Close"], increasing_line_color="#00C853", decreasing_line_color="#FF3D00")])
                fig_c.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", margin=dict(l=10, r=60, t=30, b=40), height=450, xaxis=dict(showgrid=True, gridcolor="#1A1A1A"), yaxis=dict(showgrid=True, gridcolor="#1A1A1A", side="right", dtick=10), showlegend=False)
                st.plotly_chart(fig_c, width="stretch", key="chart_candlestick")
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
    @st.fragment
    def _render_forecast():
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
                    "Prognose Basis auswählen:", namen, key="prognose_wert_wahl",
                )
                opt = next(o for o in prognose_optionen if o["name"] == gewaehlter_name)
            else:
                opt = prognose_optionen[0]

            opt_startkapital = opt["startkapital"]
            opt_aktueller_wert = opt["aktueller_wert"]
            opt_kaufdatum = opt["kaufdatum"]
            opt_sparrate = opt["sparrate"]
            opt_entnahme = opt["entnahme"]
            opt_gewinn = opt_aktueller_wert - opt_startkapital
            opt_netto = opt_aktueller_wert - opt_entnahme

            _default_key = f"prognose_rate_{opt['name']}"
            opt_cagr_pa = st.number_input(
                "Angenommene Rendite p.a. (%) für diese Prognose",
                min_value=-99.0, max_value=100000.0, step=0.5,
                value=round(opt["cagr_pa"], 2), key=_default_key,
                help="Vorbelegt mit der aus der Kurshistorie ermittelten Rate. "
                     "Frei überschreibbar, um andere Annahmen durchzurechnen.",
            )
            opt_zins_mo = (1 + (opt_cagr_pa / 100.0)) ** (1 / 12) - 1

            if opt.get("cagr_details"):
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

            forecast_data = [
                {"Jahr": "Start", "Datum": opt_kaufdatum.strftime("%d.%m.%Y"), "Gesamter Gewinn": "+0,00€", "Netto Depotwert": fmt(opt_startkapital, 2), "Kumulierte Entnahme": "0,00€"},
                {"Jahr": "Heute", "Datum": heute_date.strftime("%d.%m.%Y"), "Gesamter Gewinn": f"+{fmt(opt_gewinn, 2)}", "Netto Depotwert": fmt(opt_netto, 2), "Kumulierte Entnahme": fmt(opt_entnahme, 2)}
            ]

            sim_b_prog, sim_n_prog, sim_e_prog = opt_aktueller_wert, opt_netto, opt_entnahme
            milestone_added = opt_aktueller_wert >= 100000.0

            for m_idx in range(1, 121):
                sim_b_prog = (sim_b_prog * (1 + opt_zins_mo)) + opt_sparrate
                sim_e_prog += opt_entnahme
                sim_n_prog = sim_b_prog - sim_e_prog
    
                current_date = now_berlin.replace(tzinfo=None) + pd.DateOffset(months=m_idx)
    
                if not milestone_added and sim_b_prog >= 100000.0:
                    forecast_data.append({
                        "Jahr": "100k",
                        "Datum": current_date.strftime("%d.%m.%Y"),
                        "Gesamter Gewinn": f"+{fmt(sim_b_prog - opt_startkapital, 2)}",
                        "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                    })
                    milestone_added = True

                if m_idx % 12 == 0:
                    forecast_data.append({
                        "Jahr": f"Jahr +{m_idx // 12}",
                        "Datum": current_date.strftime("%d.%m.%Y"),
                        "Gesamter Gewinn": f"+{fmt(sim_b_prog - opt_startkapital, 2)}",
                        "Netto Depotwert": fmt(sim_n_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                    })
        
            df_forecast = pd.DataFrame(forecast_data)

            # Spalten, die nur Nullen enthalten, gar nicht erst zeigen -
            # ohne Entnahme sind "Netto Depotwert" und "Kumulierte
            # Entnahme" identisch zum Bruttowert bzw. durchgehend 0 und
            # kosten auf dem Smartphone nur seitliche Scrollbreite.
            if not opt_entnahme:
                df_forecast = df_forecast.drop(
                    columns=["Netto Depotwert", "Kumulierte Entnahme"], errors="ignore"
                )

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
            st.markdown('<div class="abschnitt">📉 Bandbreite möglicher Verläufe</div>',
                        unsafe_allow_html=True)

            mc_jahre = st.slider("Zeitraum der Simulation (Jahre)", 1, 15, 5,
                                 key="mc_jahre")
            mc_shrinkage = st.toggle(
                "Dämpfung bei kurzer Historie", value=True, key="mc_shrinkage",
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
                          f"{mc_kennzahlen['verlust_wahrscheinlichkeit']:.0f} %")

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

    # @st.fragment: dadurch loest eine Auswahl INNERHALB dieser Ansicht
    # nur diesen Bereich neu aus - vorher lief der komplette Seitenaufbau
    # erneut (Live-Kurse, Benchmarks, alle Positionen und
    # Beobachtungswerte), obwohl nur ein einziger Wert gefragt war.
    # Voraussetzung: NICHT in einen ausserhalb erzeugten Container
    # schreiben ("with tab_scenarios:") - Streamlit verbietet das bei
    # Fragment-Reruns. Die Ansicht zeichnet daher direkt an ihrer Stelle.
    @st.fragment
    def _render_scenarios():
        try:
            st.markdown(
                '<div style="font-size: 1.05rem; font-weight: 800; color: #FFFFFF; margin-bottom: 4px;">'
                '📊 Szenario-Analyse (5 Jahre)</div>',
                unsafe_allow_html=True,
            )
            # ---------- BASIS: hinterlegten Wert oder eigene Eingabe ----------
            # Vorher rechnete der Simulator immer mit festen 10.000 € und
            # hatte keinerlei Bezug zu den Werten der App. Jetzt laesst sich
            # jeder Wert waehlen, der auch in der Zukunfts-Prognose steht
            # (Hauptposition, weitere Positionen, Beobachtungswerte). Die
            # Felder darunter werden damit vorbelegt, bleiben aber frei
            # aenderbar. Zusaetzlich erscheint die historische Rate dieses
            # Werts als eigenes, hervorgehobenes Szenario.
            # "Standard" = das urspruengliche Verhalten: feste 10.000 €,
            # nur die 19 Standard-Raten (1,0-10,0 % p.M.), ohne Bezug zu
            # einem bestimmten Wert und ohne historisches ⭐-Szenario.
            # Steht bewusst an erster Stelle und ist damit die Vorauswahl.
            STANDARD = "📐 Standard (1,0–10,0 % p.M., 10.000 €)"
            _basis_namen = [STANDARD] + [o["name"] for o in prognose_optionen]
            basis_name = st.selectbox(
                "Wert auswählen:", _basis_namen, key="szenario_basis_wahl",
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

            col_sk, col_en = st.columns(2)
            with col_sk:
                startkapital_szenario = st.number_input(
                    "✏️ Startkapital (€)", min_value=0.0, value=round(_vorbelegung["start"], 2),
                    step=100.0, key=f"szenario_startkapital_{_k}",
                )
            with col_en:
                entnahme_eingabe = st.number_input(
                    "✏️ Monatliche Entnahme (€)", min_value=0.0, value=_vorbelegung["entnahme"],
                    step=10.0, key=f"szenario_entnahme_{_k}",
                )
            sparrate_szenario = st.number_input(
                "✏️ Monatliche Sparrate (€)", min_value=0.0, value=_vorbelegung["sparrate"],
                step=10.0, key=f"szenario_sparrate_{_k}",
                help="Zusätzliche monatliche Einzahlung - erhöht das Kapital jeden Monat, statt es zu verringern.",
            )

            ohne_entnahme = st.toggle("Ohne monatliche Entnahme berechnen", value=False, key="szenario_ohne_entnahme")
            entnahme_fuer_szenario = 0.0 if ohne_entnahme else entnahme_eingabe
            netto_cashflow_szenario = sparrate_szenario - entnahme_fuer_szenario

            # STANDARD: die 19 festen Raten (1,0-10,0 % p.M.) wie gehabt.
            # HINTERLEGTER WERT: nur EIN Szenario - die Rate dieses Werts.
            # Vorher liefen dort zusaetzlich alle 19 Standardraten mit, und
            # die eigentlich relevante Rate ging in der Liste unter. Die Rate
            # ist mit der historischen Rendite vorbelegt, aber editierbar,
            # damit sich auch konservativere Annahmen durchrechnen lassen.
            eigene_rate_mo = None
            if basis is None:
                szenario_raten_mo = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0,
                                     5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]
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
                                "Auflegungsdatum", value=_gespeichert or _datenbeginn,
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
                                speichere_auflegung(_inst_id, None)
                                st.rerun(scope="fragment")
                            if _gespeichert:
                                st.caption(f"Aktiv: Auflegung {_gespeichert.strftime('%d.%m.%Y')} "
                                           f"zu {WIKIFOLIO_STARTKURS:.0f} €.")

                    _daempfen = st.toggle(
                        "Dämpfung bei kurzer Historie", value=False, key=f"szenario_daempf_{_k}",
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
                    value=round(max(_prod_pa, -99.0), 2), key=f"szenario_rate_{_k}",
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
        
                _serien_name = f"{r_mo_pct:.1f}% p.M. ({r_pa_pct:.1f}% p.a.)"
                if ist_eigene_rate:
                    _serien_name = f"⭐ {basis_name}: {_serien_name}"
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
                _rahmen = ("2px solid #16C784; box-shadow: 0 0 12px rgba(22,199,132,0.25)"
                           if e["eigene"] else "1px solid #27272A")
                _marke = (f'<div style="font-size: 0.72rem; font-weight: 700; color: #16C784; '
                          f'letter-spacing: 0.6px; margin-bottom: 4px;">⭐ {basis_name.upper()}</div>'
                          if e["eigene"] else "")
                # WICHTIG: HTML ohne Zeilenumbrueche/Einrueckung aufbauen.
                # In einem mehrzeiligen f-String entsteht bei leerem
                # {_marke} eine Leerzeile - Markdown wertet alles danach mit
                # 4+ Leerzeichen Einrueckung als CODEBLOCK und zeigt den
                # HTML-Quelltext als Text an (genau dieser Fehler trat auf).
                _jahre = "".join(
                    f'<div><div style="font-size: 0.65rem; color: #71717A;">{j}J</div>'
                    f'<div style="font-size: 0.75rem; color: #E5E7EB; font-weight: 700;">{fmt(e[f"j{j}"], 0)}</div></div>'
                    for j in range(1, 6)
                )
                karten_html += (
                    f'<div style="background: #09090B; border: {_rahmen}; border-radius: 6px; padding: 12px 14px;">'
                    f'{_marke}'
                    f'<div style="font-size: 1rem; font-weight: 800; color: #FFFFFF; margin-bottom: 8px;">'
                    f'{e["rate"]:.1f}% p.M. <span style="color: #A1A1AA; font-weight: 600; font-size: 0.8rem;">({e["rate_pa"]:.2f}% p.a.)</span>'
                    f'</div>'
                    f'<div style="font-size: 0.85rem; color: #00C853; font-weight: 700; margin-bottom: 6px;">{e["ziel_100k"]}</div>'
                    f'<div style="font-size: 0.8rem; color: #CBD5E1; margin-bottom: 8px;">Ziel-Datum (100k): {e["ziel_datum"]}</div>'
                    f'<div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; border-top: 1px solid #1A1A1A; padding-top: 8px;">'
                    f'{_jahre}</div>'
                    f'</div>'
                )
            karten_html += "</div>"
            st.markdown(karten_html, unsafe_allow_html=True)

            fig_scen = go.Figure()
            months_x = list(range(61))

            for label, vals in scenario_series.items():
                if label.startswith("⭐"):
                    fig_scen.add_trace(go.Scatter(
                        x=months_x, y=vals, mode="lines", name=label,
                        line=dict(color="#16C784", width=4),
                    ))
                else:
                    fig_scen.add_trace(go.Scatter(
                        x=months_x, y=vals, mode="lines", name=label,
                        line=dict(width=1.5), opacity=0.75,
                    ))

            fig_scen.add_hline(
                y=100000, 
                line_dash="dot", 
                line_color="#00C853", 
                annotation_text="🎯 100k Zielwert", 
                annotation_position="top left",
                annotation_font=dict(color="#00C853", size=11)
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
                    font=dict(color="#E5E7EB", size=11)
                ),
                xaxis=dict(title="Monate ab heute", showgrid=True, gridcolor="#1A1A1A", tickfont=dict(color="#A1A1AA")),
                yaxis=dict(title="Depotwert (€)", showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA")),
                hovermode="x unified",
            )
            st.plotly_chart(fig_scen, width="stretch", key="chart_scenarios")
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Szenarien", e)
    if gewaehlte_ansicht == "📊 Szenario-Simulator (5 Jahre)":
        melde("ansicht", 0.3, "Berechne Szenarien …")
        _render_scenarios()
        lade_fertig()

    # ---------- WATCHLIST TOP 50 ----------
    # Die Ranglisten berechnet der taegliche Agent (top50_agent.py, GitHub
    # Actions) und legt sie fertig in state/top50.json ab. Die App liest nur
    # diese Datei - kein einziger Kursabruf beim Umschalten, deshalb schnell.
    # Als Fragment: Kategorie- und Zeitraumwechsel bauen nur diesen Bereich neu.
    @st.fragment
    def _render_top50():
        try:
            daten = gh_read_cached("state/top50.json", None)
            if not daten or not daten.get("kategorien"):
                st.info(
                    "Noch keine Ranglisten vorhanden. Der Agent läuft täglich um 07:30 Uhr. "
                    "Für einen Sofortstart: auf GitHub unter **Actions → Watchlist Top 50 "
                    "(täglich) → Run workflow**."
                )
                return

            kategorien = daten["kategorien"]
            zeitraeume = daten.get("zeitraeume") or []
            try:
                stand = datetime.datetime.fromisoformat(daten["stand"]).strftime("%d.%m.%Y, %H:%M Uhr")
            except Exception:
                stand = daten.get("stand", "–")

            kat_keys = [k for k in ("aktien", "dividenden", "etf", "wikifolios") if k in kategorien]
            kat_titel = [kategorien[k]["titel"] for k in kat_keys]
            gewaehlt = st.pills("Kategorie", kat_titel, default=kat_titel[0], key="top50_kategorie")
            kat_key = kat_keys[kat_titel.index(gewaehlt)] if gewaehlt in kat_titel else kat_keys[0]
            kat = kategorien[kat_key]

            zr_titel = [t for _, t in zeitraeume]
            zr_wahl = st.pills("Zeitraum", zr_titel, default="1 Jahr" if "1 Jahr" in zr_titel else zr_titel[0],
                               key="top50_zeitraum")
            zr_key = zeitraeume[zr_titel.index(zr_wahl)][0] if zr_wahl in zr_titel else zeitraeume[0][0]

            liste = kat.get("top", {}).get(zr_key, [])
            mit_daten = kat.get("mit_daten", {}).get(zr_key, 0)
            st.caption(
                f"Stand {stand} · {mit_daten} von {kat.get('aktiv', 0)} aktiven Werten haben "
                f"Kursdaten für diesen Zeitraum · Top {len(liste)}"
            )

            if not liste:
                st.info("Für diesen Zeitraum reicht bei keinem Wert die Kurshistorie aus.")
                return

            zeilen = ""
            for rang, e in enumerate(liste, 1):
                farbe = "pt-up" if e["perf"] >= 0 else "pt-down"
                zeilen += (
                    f'<tr class="{"pt-zebra" if rang % 2 == 0 else ""}">'
                    f'<td class="pt-num pt-seit">{rang}</td>'
                    f'<td class="pt-wert"><span class="pt-name">{e["name"]}</span></td>'
                    f'<td class="pt-num pt-stark {farbe}">{e["perf"]:+.2f}%</td>'
                    f'<td class="pt-num pt-wknval">{e.get("wkn") or "–"}</td>'
                    f'</tr>'
                )
            st.markdown(
                '<div class="pt-wrap"><table class="pt"><thead><tr>'
                '<th class="pt-num">#</th><th class="pt-wert">Wert</th>'
                f'<th class="pt-num">{zr_wahl}</th><th class="pt-num">WKN</th>'
                f'</tr></thead><tbody>{zeilen}</tbody></table></div>',
                unsafe_allow_html=True,
            )

            with st.expander("Hinweise zu den Ranglisten", expanded=False):
                st.caption(
                    "Reine Kursperformance ohne Dividenden, Gebühren oder Steuern - bei den "
                    "Dividenden-Aktien sind die Ausschüttungen also NICHT enthalten. "
                    "Werte ohne Kurs seit mehr als 10 Tagen gelten als inaktiv und fehlen. "
                    "wikifolios werden automatisch über die Kursquelle gefunden (alle "
                    "Zertifikate mit WKN LS9…), die Suche wird wöchentlich erneuert. "
                    "Vergangene Performance ist kein Hinweis auf künftige Entwicklung."
                )
                st.caption(
                    f"Letzter Lauf: {daten.get('anfragen', '–')} Kursabrufe in "
                    f"{daten.get('laufzeit_sek', '–')} s, {daten.get('fehlgeschlagen', 0)} fehlgeschlagen."
                )
            fehlend = [f for f in daten.get("nicht_gefunden", []) if f.get("kategorie") == kat["titel"]]
            if fehlend:
                with st.expander(f"Nicht gefunden ({len(fehlend)})", expanded=False):
                    st.caption("Diese Werte aus top50_universum.py ließen sich weder über die "
                               "ISIN noch über den Namen finden - dort korrigieren.")
                    for f in fehlend:
                        st.write(f"- {f['name']} · {f['isin']}")
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Top50", e)

    if gewaehlte_ansicht == "🏆 Watchlist Top 50":
        melde("ansicht", 0.3, "Lade Ranglisten …")
        _render_top50()
        lade_fertig()

    # --- DIAGNOSE GANZ AM ENDE (statt Sidebar - auf Mobile oft nicht auffindbar).
    # Bewusst als Letztes: im Alltag interessieren die Kurse/Charts, der
    # Systemstatus wird nur im Fehlerfall gebraucht. Faellt der persistente
    # State aus, klappt der Expander weiterhin automatisch auf.
    st.markdown('<div class="abschnitt">🔧 System</div>', unsafe_allow_html=True)

    with st.expander("System-Status / Diagnose", expanded=not GH_STATE_READY):
        st.write(f"**Live-Daten aktiv:** {'✅ Ja' if is_live_data else '❌ Nein'} ({fetched_source})")
        st.write(f"**Chart-Historie live:** {'✅ Ja' if is_live_history else '❌ Nein'} ({hist_source_name})")
        st.write(f"**Discord-Webhook geladen:** {'✅ Ja' if DISCORD_WEBHOOK_URL else '❌ Nein'}")
        st.write(f"**Persistenter State (GitHub):** {'✅ Ja' if GH_STATE_READY else '❌ Nein - GITHUB_REPO/GITHUB_TOKEN fehlen'}")
        if GH_STATE_READY:
            st.caption(f"Repo: {GITHUB_REPO} • Branch: {config.GITHUB_STATE_BRANCH}")
        st.write(f"**High Watermark:** {high_watermark_anzeige:.3f}€")

        # Abgleich der Kauf-Eckdaten: macht sichtbar, ob die geladene Historie
        # wirklich am Kaufdatum beginnt - genau hier lief die Performance-
        # Tabelle frueher gegen einen anderen Startwert als die Kachel.
        st.markdown("**Kauf-Eckdaten**")
        _cfg_kd = config.KAUFDATUM.strftime("%d.%m.%Y")
        _akt_kd = kaufdatum_aktiv.strftime("%d.%m.%Y")
        st.write(f"- Kaufdatum aktiv: **{_akt_kd}**" + (f" (config.py: {_cfg_kd})" if _akt_kd != _cfg_kd else " (= config.py)"))
        st.write(f"- Kaufkurs aktiv: **{kaufkurs_aktiv:.4f} €** "
                 f"({'automatisch aus Historie' if kaufkurs_auto and kaufkurs_ermittelt else 'manuell/Fallback'}"
                 f", config.py: {config.ANFANGSKURS:.4f} €)")
        st.write(f"- Stückzahl: **{stueckzahl_aktiv:.4f}** ({fmt(startkapital_aktiv, 2)} ÷ {kaufkurs_aktiv:.4f} €)")
        if not df_chart.empty:
            _ds, _de = df_chart.index.min(), df_chart.index.max()
            _warnung = " ⚠️ weicht vom Kaufdatum ab" if _ds.date() != kaufdatum_aktiv else ""
            st.write(f"- Kursdaten von **{_ds.strftime('%d.%m.%Y')}** bis {_de.strftime('%d.%m.%Y')}"
                     f" ({len(df_chart)} Handelstage){_warnung}")
            st.write(f"- Erster Schlusskurs der Reihe: **{df_chart['Close'].iloc[0]:.4f} €**")



render_dashboard()
