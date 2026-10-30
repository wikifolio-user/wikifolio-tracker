"""Zentrale Styles der App (UX 10/2026) - alles CSS an EINER Stelle.

- CSS_BASIS: Design-System (Farben, Schrift, Kacheln, Tabellen, Formulare) - frueher in app.py
- CSS_NAV: Startseite, Menue-Kacheln, Kopfleiste - frueher NAV_CSS in app.py
- CSS_RESPONSIV: Umbruchpunkte und Layout-Regeln fuer alle Bildschirmbreiten (siehe unten)

Umbruchpunkte (einheitlich):  S < 600 px (Handy)  |  M 600-899 (Handy quer, Tablet hoch)
                             L 900-1199 (Tablet quer, kleines Fenster)  |  XL >= 1200 (Desktop)
Inhalt ist auf grossen Monitoren auf INHALT_MAX px begrenzt (zentriert); breite Tabellen duerfen
ueber .ui-breit die volle Breite nutzen.
"""
import re

INHALT_MAX = 1440
INHALT_MAX_BREIT = 1920

CSS_BASIS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
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
        --ink:     #07090F;   /* Hintergrund: tiefes Navy (glass_theme --bg-0) */
        --surface: #0D1220;   /* erhoehte Flaechen (--bg-1) */
        --line:    #232A3D;   /* Haarlinien */
        --muted:   #8A93A8;   /* Sekundaertext, tertiaer (Fussnoten) */
        --label:   #A9B1C4;   /* Zeilen-Labels - deutlich besser lesbar als --muted */
        --text:    #E8ECF6;   /* Primaertext */
        --up:      #34D399;
        --down:    #F87171;
    }

    .stApp { background-color: var(--ink); color: var(--text); }

    /* Basistypo fuer Text - Icon-Elemente (z.B. Expander-Pfeile,
       Number-Input-Steppers) werden HIER BEWUSST AUSGENOMMEN, da diese
       eine eigene Icon-Font (Material Symbols) benoetigen. Wurde diese
       durch Space Grotesk ueberschrieben, zeigte Streamlit statt des
       Pfeil-Glyphs den rohen Icon-Namen als Text an (z.B. "_arrow_right"). */
    .stApp,
    .stApp *:not([data-testid="stIconMaterial"]):not(.material-icons):not(.material-symbols-rounded):not(.material-symbols-outlined) {
        font-family: 'Inter', -apple-system, sans-serif;
    }

    /* Streamlit-eigene Icons (Expander-Chevron, Stepper-Pfeile etc.)
       explizit auf ihrer Icon-Font belassen. */
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    }

    /* Zahlen bekommen konsequent die Datenschrift mit Tabellenziffern */
    .num, .q-price, .q-delta, .row-val, .hero-val, .hero-sub {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum" 1;
    }

    /* ---------- KURS-KOPF: die Zahl ist der Held der Seite ---------- */
    .quote {
        background: var(--surface); border: 1px solid var(--rand);
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
        font-family: 'Inter', -apple-system, sans-serif !important;
        font-size: 0.8rem; font-weight: 700; color: #FFFFFF;
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
        background: rgba(52, 211, 153, 0.12); color: var(--up);
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.2px;
        padding: 4px 10px 4px 8px; border-radius: 999px;
    }
    .live-pill.offline { background: rgba(248, 113, 113, 0.12); color: var(--down); }
    .live-pill.stand { background: rgba(255, 255, 255, 0.06); color: var(--label); }
    .live-dot.stand { background: var(--label); animation: none; }
    .meta-chip {
        font-size: 0.85rem; color: var(--label); font-weight: 500;
        background: rgba(255, 255, 255, 0.04);
        padding: 4px 10px; border-radius: 999px;
    }
    /* Badge fuer "aktuell auf Allzeithoch" - gleiche Pill-Optik wie das
       Live-Badge, damit sich die Statusmarker in beiden Kacheln gleichen. */
    .hw-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(52, 211, 153, 0.12); color: var(--up);
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
        background: var(--surface); border: 1px solid var(--rand);
        border-radius: 12px; padding: 14px 16px; margin-bottom: 0;
    }

    /* Gesamtsumme optisch abheben - gruener Akzentrand, damit sie sich
       trotz gleicher Struktur klar von den Einzelpositionen unterscheidet. */
    .hero.gesamt {
        border-color: rgba(52, 211, 153, 0.35);
        background: linear-gradient(rgba(52, 211, 153, 0.05), rgba(52, 211, 153, 0.05)), var(--surface);
    }
    .hero-val { font-size: 1.6rem; font-weight: 700; color: var(--text); letter-spacing: -0.3px; }
    .hero-sub { font-size: 0.92rem; color: var(--label); font-weight: 500; }

    /* Kompakte Fussnote am Kachelende (Zeitstempel, Stueckzahl) - bewusst
       ohne Chip-Pille, damit sie moeglichst wenig Hoehe kostet. */
    .card-footnote {
        font-size: 0.8rem; color: var(--muted); margin-top: 8px;
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
        font-size: 0.8rem; font-weight: 700; color: var(--label);
        text-transform: uppercase; letter-spacing: 0.4px;
    }
    .stat-chip-val {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.9rem; font-weight: 700; color: var(--text);
    }
    .stat-chip-val.up { color: var(--up); } .stat-chip-val.down { color: var(--down); }

    /* ---------- DATENZEILEN statt Kachel-Wildwuchs ----------
       Sekundaerwerte als hairline-getrennte Liste: ruhiger, dichter
       und deutlich schneller zu scannen als 8 gleich grosse Boxen. */
    .rows { border: 1px solid var(--rand); border-radius: 12px; overflow: hidden; margin-bottom: 22px; }
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
        display: block; font-size: 0.8rem; color: var(--muted);
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
        font-family: 'JetBrains Mono', ui-monospace, monospace;
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
    /* Aussehen der Pillen/Knoepfe: siehe GLAS am Ende von CSS_NAV */
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
        font-family: 'Inter', -apple-system, sans-serif !important;
        font-size: 0.8rem !important;
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
        outline: 2px solid var(--rand) !important;
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
    /* Hilfe-Symbol (?) neben Dropdowns: nicht wie das Feld rahmen/fuellen - sonst
       erscheint es als weisser Kreis. Gleiche Optik wie bei den uebrigen Feldern. */
    [data-testid="stSelectbox"] [data-testid="stTooltipIcon"],
    [data-testid="stSelectbox"] [data-testid="stTooltipHoverTarget"],
    [data-testid="stSelectbox"] > div:has([data-testid="stTooltipIcon"]):not(:has([data-baseweb="select"])) {
        outline: none !important; background: transparent !important; box-shadow: none !important;
        animation: none !important; border: none !important;
    }
    [data-testid="stSelectbox"] [data-testid="stTooltipIcon"] svg,
    [data-testid="stSelectbox"] [data-testid="stTooltipHoverTarget"] svg {
        fill: none !important; color: #9AA0A6 !important; stroke: currentColor;
        width: 18px !important; height: 18px !important;
    }
    /* Aufgeklappte Liste passend zum Rest gestalten */
    div[data-baseweb="popover"] li {
        font-size: 0.9rem !important;
        min-height: 44px !important;
    }
    /* Streamlit begrenzt aufgeklappte Auswahllisten auf rund 300px - bei
       "Ansicht wählen" wurde dadurch der 8. Eintrag angeschnitten. Die Grenze
       sitzt ZWEIMAL: am aeusseren Rahmen (data-testid=stSelectboxVirtualDropdown)
       und an der inneren Liste (role=listbox), beide mit
       max-height: min(maxDropdownHeight, 70vh). Beide muessen angehoben
       werden. Die Liste misst ihre Groesse selbst nach, lange Listen bleiben
       also korrekt scrollbar. */
    [data-testid="stSelectboxVirtualDropdown"],
    [data-testid="stSelectboxVirtualDropdown"] [role="listbox"] {
        max-height: min(30rem, 80vh) !important;
    }

    /* ---------- ABSCHNITTE & AUFKLAPPBEREICHE ----------
       Die Aufklappbereiche taten bisher zweierlei (etwas einstellen vs. etwas
       nachschlagen), sahen aber identisch aus. Abschnittsueberschrift plus
       weisser Rahmen macht die Gliederung auf einen Blick lesbar. */
    .abschnitt {
        font-family: 'Inter', -apple-system, sans-serif !important;
        font-size: 0.8rem; font-weight: 700; color: #FFFFFF;
        letter-spacing: 1.3px; text-transform: uppercase;
        margin: 16px 0 2px 2px;
        padding-bottom: 7px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.45);
        /* Neon-Weiss wie Titel und Menue */
        text-shadow: 0 0 6px rgba(255, 255, 255, 0.35);
        box-shadow: 0 6px 8px -8px rgba(255, 255, 255, 0.35);
    }

    /* Jeder Aufklappbereich als eigener Block mit weissem Rand. Bewusst
       schwaecher als das Ansichts-Dropdown (1px statt 2px outline, dezenteres
       Leuchten) - das Dropdown ist die Hauptnavigation und soll das
       auffaelligste Element auf der Seite bleiben. */
    [data-testid="stExpander"] {
        border: 1px solid var(--rand) !important;
        border-radius: 12px !important;
        background: var(--surface) !important;
        margin-bottom: 0 !important;
        overflow: hidden;
        box-shadow: 0 0 8px rgba(255, 255, 255, 0.12);
        transition: box-shadow 0.15s ease, border-color 0.15s ease;
    }
    [data-testid="stExpander"]:hover {
        border-color: var(--rand) !important;
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
        font-family: 'Inter', -apple-system, sans-serif !important;
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
        background-color: #1A1B1C !important;
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
        border: 1px solid var(--rand); border-radius: 10px;
        margin-bottom: 12px;
    }
    .pt { width: 100%; border-collapse: collapse; background: #0C0D0E; }

    .pt thead th {
        position: sticky; top: 0; z-index: 2;
        /* Harmonischer Grauton, deutlich abgesetzt von den Zeilen darunter
           (#0C0D0E) - die Kopfzeile soll klar als eigene Ebene erkennbar
           sein, nicht nur eine Nuance dunkler. */
        background: #202022;
        padding: 9px 10px;
        font-size: 0.8rem; font-weight: 700; color: #FFFFFF;
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
        background: rgba(52, 211, 153, 0.09);
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
        color: var(--label); font-weight: 600; font-size: 0.8rem;
        letter-spacing: 0.3px;
    }

    /* Zahlen in Tabellenziffern, damit Nachkommastellen untereinander stehen */
    .pt-num {
        text-align: right;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.8rem;
    }
    .pt-stark { font-weight: 700; font-size: 0.83rem; }
    .pt-klein { font-size: 0.8rem; opacity: 0.92; }
    .pt-up { color: #34D399; }
    .pt-down { color: #F87171; }
    .pt-leer { color: #4B5058; }
    .pt-seit { color: #FFFFFF; font-weight: 700; font-size: 0.8rem; text-shadow: 0 0 8px rgba(255, 255, 255, 0.30); }

    /* ---------- WATCHLIST / QUALITAETS-SCORE ----------
       Zweite Zeile unter dem Namen (Kennung, Branche) statt eigener Spalten -
       spart auf dem iPhone die Breite fuer die eigentlichen Zahlen. */
    .pt-sub {
        display: block; margin-top: 2px; white-space: normal;
        font-size: 0.8rem; font-weight: 600; color: var(--label); letter-spacing: 0.2px;
    }
    .q-punkte { font-weight: 800; font-size: 0.9rem; }
    .q-prio { color: #34D399; }
    .q-beob { color: #F5B942; }
    .q-nicht { color: #8A9099; }
    .pt td.q-fokus-hl, .pt th.q-fokus-hl { background: rgba(255, 255, 255, 0.05); }
    .q-legende { font-size: 0.8rem; color: var(--label); margin: -4px 0 10px; }
    .q-kpis {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 8px; margin: 6px 0 12px;
    }
    .q-kpi {
        background: #0C0D0E; border: 1px solid var(--rand); border-radius: 10px;
        padding: 10px 12px; min-width: 0;
    }
    .q-kpi-l {
        font-size: 0.8rem; font-weight: 700; color: var(--label);
        text-transform: uppercase; letter-spacing: 0.6px;
    }
    .q-kpi-v {
        font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
        font-size: 1.35rem; font-weight: 800; color: #FFFFFF; line-height: 1.3;
    }
    .q-kpi-v span { font-size: 0.8rem; font-weight: 600; color: var(--label); }
    .q-kpi-v b { font-weight: 800; }
    /* Kleine Tabellen mit mehreren Zahlenspalten: Koepfe duerfen zweizeilig sein */
    .pt.pt-kompakt thead th { white-space: normal; line-height: 1.25; }
    /* Gesamtuebersicht: breite Tabellen scrollen IMMER seitlich (auch am
       iPhone), die Namensspalte bleibt beim Wischen links stehen */
    .ue-wrap {
        overflow-x: auto; -webkit-overflow-scrolling: touch;
        border: 1px solid var(--rand); border-radius: 10px; margin-bottom: 14px;
    }
    .pt.ue td { white-space: nowrap; }
    .pt.ue td.pt-wert { white-space: normal; min-width: 150px; max-width: 320px; }
    .pt.ue .ue-fix { position: sticky; left: 0; z-index: 1; background: #0C0D0E;
                     box-shadow: 1px 0 0 var(--line); }
    .pt.ue thead th.ue-fix { z-index: 3; background: #202022; }
    .pt.ue tr.pt-zebra .ue-fix { background: #131314; }
    /* wikifolio-Rangliste: Rang und Name bleiben beim Wischen beide links stehen */
    .pt.wk .wk-rang { left: 0; width: 44px; min-width: 44px; max-width: 44px; box-sizing: border-box;
                      box-shadow: none; }
    .pt.wk .wk-name { left: 44px; width: auto; min-width: 150px; max-width: 220px; }
    /* iPad hochkant: etwas engere Spalten, damit alle Zeitraeume ohne Wischen passen */
    @media (min-width: 701px) and (max-width: 1100px) {
        .pt.wk td, .pt.wk thead th { padding-left: 6px; padding-right: 6px; }
        .pt.wk .wk-rang { width: 36px; min-width: 36px; max-width: 36px; }
        .pt.wk .wk-name { left: 36px; min-width: 130px; max-width: 170px; }
    }
    @media (min-width: 701px) and (max-width: 800px) {
        .pt.wk td, .pt.wk thead th { padding-left: 4px; padding-right: 4px; }
        .pt.wk .wk-name { min-width: 112px; max-width: 140px; }
        .pt.wk .pt-num { font-size: 0.76rem; }
    }
    @media (max-width: 700px) { .pt.wk .wk-name { min-width: 128px; max-width: 150px; } }
    /* ETF-/wikifolio-Score: Begruendung als kurze Zeilen, Teilpunkte als Balken */
    .pt.ks td.ks-grund, .pt.ks th.ks-grund { white-space: normal; min-width: 220px; max-width: 320px;
                                              text-align: left; font-size: 0.78rem; line-height: 1.35; }
    .ks-plus, .ks-minus { display: block; }
    .ks-plus { color: #34D399; }
    .ks-minus { color: #F5B942; }
    .ks-bahn { width: 140px; height: 8px; background: rgba(255, 255, 255, 0.08); border-radius: 4px;
               overflow: hidden; }
    .ks-bahn > div { height: 100%; background: #34D399; border-radius: 4px; }
    .pt.ks-mini td { white-space: normal; }
    .pt.ks-mini td.pt-num { white-space: nowrap; }
    .q-balken { margin: 4px 0 14px; }
    .q-b-zeile {
        display: grid; grid-template-columns: minmax(0, 1fr) 96px 46px;
        gap: 10px; align-items: center; padding: 6px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-size: 0.82rem; color: #FFFFFF;
    }
    .q-b-bahn { height: 8px; background: rgba(255, 255, 255, 0.08); border-radius: 4px; overflow: hidden; }
    .q-b-fuell { height: 100%; border-radius: 4px; }
    .q-b-wert {
        text-align: right; font-weight: 700;
        font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
    }
    @media (max-width: 700px) {
        .q-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .q-kpi-v { font-size: 1.2rem; }
        .q-b-zeile { grid-template-columns: minmax(0, 1fr) 72px 44px; font-size: 0.86rem; }
        .pt-sub { font-size: 0.8rem; }
        .q-punkte { font-size: 0.98rem; }
        .pt.pt-kompakt td, .pt.pt-kompakt thead th { padding: 9px 6px; }
    }

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
        /* Tabellen ohne Fokus-Umschalter (z. B. "Qualität × Kurs", Wochenveraenderung) koennen breiter als das
           Handy sein - sie scrollen
           in ihrem Rahmen, sonst verschiebt sich die ganze Seite seitlich (UX 10/2026) */
        .pt-wrap:not(:has(> table[class*="pt-fokus-"])) { overflow-x: auto; }
    }

    /* ---------- ALLGEMEINE LADEANZEIGE (jede Ansicht) ----------
       Streamlit markiert die App waehrend jedes Durchlaufs mit
       data-test-script-state="running". Dauert ein Durchlauf laenger als
       0,5 s, erscheint oben dasselbe Banner wie beim genauen Balken:
       Prozentzahl, Text und Balken. Die Prozentzahl ist hier eine
       HOCHRECHNUNG (zaehlt zuegig an, wird dann langsamer und haelt bei
       95 %, bis die Seite fertig ist) - der genaue Stand ist unbekannt.
       Laeuft schon der genaue Prozent-Balken (.loading-overlay), bleibt
       diese Anzeige aus. */
    @property --ladepct { syntax: '<integer>'; inherits: false; initial-value: 0; }
    @property --ladebreite { syntax: '<percentage>'; inherits: false; initial-value: 0%; }
    [data-testid="stApp"][data-test-script-state="running"]::before,
    [data-testid="stApp"][data-test-script-state="rerunRequested"]::before {
        counter-reset: ladepct var(--ladepct);
        content: counter(ladepct) " %";
        position: fixed; top: 0; left: 0; right: 0; z-index: 10000; height: 66px; box-sizing: border-box;
        padding: 10px 16px 0; display: block;
        font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
        font-size: 1.35rem; font-weight: 700; line-height: 1.2; color: var(--text);
        background: rgba(21, 21, 22, 0.97); border-bottom: 1px solid var(--line);
        box-shadow: 0 2px 14px rgba(0, 0, 0, 0.6);
        opacity: 0; pointer-events: none;
        animation: ladeein 0.2s ease 0.5s forwards, ladezahl 12s cubic-bezier(.12, .75, .3, 1) 0.5s forwards;
    }
    [data-testid="stApp"][data-test-script-state="running"]::after,
    [data-testid="stApp"][data-test-script-state="rerunRequested"]::after {
        content: "Lade Daten …";
        position: fixed; z-index: 10001; top: 0; left: 0; right: 0; height: 66px; box-sizing: border-box;
        padding: 14px 16px 0 96px; text-align: right;
        font-size: 0.9rem; font-weight: 600; color: var(--muted); white-space: nowrap;
        /* Balken: unten im Banner, Fuellung waechst mit --ladebreite */
        background:
            linear-gradient(var(--accent, #7C9CFF), var(--accent, #7C9CFF)) no-repeat 16px 46px / calc((100% - 32px) * var(--ladebreite) / 100%) 9px,
            linear-gradient(var(--line), var(--line)) no-repeat 16px 46px / calc(100% - 32px) 9px;
        opacity: 0; pointer-events: none;
        animation: ladeein 0.2s ease 0.5s forwards, ladebalken 12s cubic-bezier(.12, .75, .3, 1) 0.5s forwards;
    }
    [data-testid="stApp"]:has(.loading-overlay)::before,
    [data-testid="stApp"]:has(.loading-overlay)::after { display: none !important; }
    @keyframes ladeein { to { opacity: 1; } }
    @keyframes ladezahl { from { --ladepct: 0; } to { --ladepct: 95; } }
    @keyframes ladebalken { from { --ladebreite: 0%; } to { --ladebreite: 95%; } }

    /* ---------- LADEFORTSCHRITT: FESTES BANNER AM OBEREN RAND ----------
       Bewusst position:fixed statt im normalen Seitenfluss. Vorher wanderte
       der Balken mit, sobald darueber/darunter Inhalte erschienen - und das
       Fragment der Kursansicht zeichnete ihn an einer voellig anderen Stelle.
       Ergebnis war ein sichtbares Hin- und Herspringen.
       Fixiert belegt er ausserdem keinen Platz im Layout, es gibt also auch
       keinen Versatz mehr, wenn er wieder verschwindet. */
    .loading-overlay {
        position: fixed; top: 0; left: 0; right: 0; z-index: 9999; height: 66px; box-sizing: border-box;
        display: flex; flex-wrap: wrap; align-items: center; column-gap: 12px; row-gap: 8px;
        padding: 10px 16px 0; align-content: flex-start;
        background: rgba(21, 21, 22, 0.97);
        border-bottom: 1px solid var(--line);
        box-shadow: 0 2px 14px rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(6px);
    }
    .loading-pct {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums;
        font-size: 1.35rem; font-weight: 700; color: var(--text);
        line-height: 1.2; min-width: 72px; flex-shrink: 0;
    }
    /* Balken in eigener Zeile ueber die volle Breite - feste Breite, nur die Fuellung bewegt sich */
    .loading-bar {
        order: 3; flex: 0 0 100%; width: 100%; height: 9px; border-radius: 999px;
        background: var(--line); overflow: hidden;
    }
    .loading-bar-fill {
        height: 100%; background: var(--accent, #7C9CFF); border-radius: 999px;
        transition: width 0.25s ease;
    }
    /* Text rechts neben der Prozentzahl, bei Bedarf abgeschnitten */
    .loading-text {
        flex: 1 1 0; min-width: 0; text-align: right;
        font-size: 0.9rem; color: var(--muted); font-weight: 600;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    /* ---------- VOLLE BREITE, RESPONSIV (gilt fuer alle Ansichten) ----------
       Der Inhalt nutzt die ganze verfuegbare Breite (mit Sidebar: den Rest daneben);
       seitliche Abstaende wachsen nur maessig mit dem Bildschirm. Kein seitliches
       Scrollen der Seite - breite Tabellen scrollen in ihrem eigenen Rahmen. */
    .block-container, [data-testid="stMainBlockContainer"] {
        padding-top: 0.8rem; padding-bottom: 4rem;
        max-width: 100% !important; width: 100% !important;
        padding-left: clamp(12px, 2.6vw, 48px) !important; padding-right: clamp(12px, 2.6vw, 48px) !important;
    }
    html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        overflow-x: hidden;
    }
    [data-testid="stMarkdownContainer"] img, [data-testid="stMarkdownContainer"] svg,
    [data-testid="stMarkdownContainer"] iframe, [data-testid="stImage"] img { max-width: 100%; height: auto; }
    [data-testid="stElementContainer"], [data-testid="stColumn"], [data-testid="stVerticalBlock"] { min-width: 0; }
    [data-testid="stDataFrame"], [data-testid="stTable"], [data-testid="stPlotlyChart"],
    [data-testid="stVegaLiteChart"] { max-width: 100%; }
    [data-testid="stTable"], [data-testid="stMarkdownContainer"] table { display: block; overflow-x: auto; }
    [data-testid="stMarkdownContainer"] .pt, [data-testid="stMarkdownContainer"] .ue-wrap table { display: table; }

    /* ---------- EINHEITLICHES ABSTANDS-RASTER ----------
       Streamlit setzt zwischen allen Bloecken 1rem. Zusammen mit den eigenen
       margin-Werten der Kacheln ergaben sich dadurch ueberall andere Abstaende.
       Deshalb: EIN Grundabstand hier, und die Elemente selbst bringen keinen
       eigenen mehr mit. Alles im Fluss haelt damit denselben Rhythmus. */
    div[data-testid="stVerticalBlock"] { gap: 0.7rem !important; }

    [data-testid="stNumberInput"] input {
        font-family: 'JetBrains Mono', monospace !important;
        font-variant-numeric: tabular-nums;
        font-size: 1.15rem !important; font-weight: 600 !important;
    }
    [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {
        width: 42px !important; height: 42px !important; min-width: 42px !important;
    }
    [data-testid="stNumberInputStepUp"] svg, [data-testid="stNumberInputStepDown"] svg {
        width: 20px !important; height: 20px !important;
    }
    /* Handy: die Zahlenfelder sind durch die grossen +/- Tasten 46 px hoch - Auswahlfelder daneben
       gleich hoch, sonst wirken sie in einer Reihe kleiner und versetzt */
    @media (max-width: 700px), (pointer: coarse) {
        [data-testid="stSelectbox"] > div:last-child,
        [data-testid="stSelectbox"] > div:last-child > div { min-height: 46px !important; }
        [data-testid="stSelectbox"] > div:last-child > div { display: flex; align-items: center; }
    }
    /* Tabs ruhiger, ohne dicke gruene Unterstreichung */
    [data-testid="stTabs"] button { font-size: 0.8rem !important; letter-spacing: 0.3px; }
    /* Tab-Leiste bei vielen Positionen horizontal scrollbar halten, statt
       die Beschriftungen umbrechen oder abschneiden zu lassen. */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto; scrollbar-width: none;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
    /* Sichtbarer Tastatur-Fokus (Audit A-16) */
    button:focus-visible, a:focus-visible, input:focus-visible, [role="tab"]:focus-visible,
    [role="button"]:focus-visible, [role="checkbox"]:focus-visible, [role="switch"]:focus-visible {
        outline: 2px solid #A5B8FF !important; outline-offset: 2px !important;
    }
    /* Kachel im Tab hat keinen doppelten Abstand nach unten */
    [data-testid="stTabs"] .hero { margin-bottom: 0; }

    /* ---------- UX 10/2026: Lesbarkeit auf kleinen Bildschirmen ----------
       Streamlit kuerzt Kennzahlen, Feldbeschriftungen und Knopftexte mit "…" - auf dem
       iPhone waren so Werte wie "4.00…" oder "Wahrscheinlichkeit …" nicht lesbar.
       Hier wird stattdessen umgebrochen. */
    [data-testid="stMetric"] .stMarkdownEllipsis, [data-testid="stMetric"] .stMarkdownEllipsis *,
    [data-testid="stWidgetLabel"] .stMarkdownEllipsis, [data-testid="stWidgetLabel"] .stMarkdownEllipsis *,
    [data-testid="stButton"] .stMarkdownEllipsis, [data-testid="stButton"] .stMarkdownEllipsis *,
    [data-testid="stFormSubmitButton"] .stMarkdownEllipsis, [data-testid="stFormSubmitButton"] .stMarkdownEllipsis *,
    [data-testid="stDownloadButton"] .stMarkdownEllipsis, [data-testid="stDownloadButton"] .stMarkdownEllipsis * {
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
        overflow-wrap: break-word;
    }
    [data-testid="stMetricValue"] { font-size: clamp(1.25rem, 5.2vw, 2.25rem) !important; line-height: 1.15 !important; }
    /* Depot | Kurse: gleich hohe Kopfzeilen (Titel links, Auswahl rechts), eine durchgehende Linie */
    .st-key-depot_kopf_links, .st-key-depot_kopf_rechts {
        min-height: 54px; justify-content: center; margin: 6px 0 4px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.45); padding-bottom: 6px; }
    .st-key-depot_kopf_links .abschnitt, .st-key-depot_kopf_rechts .abschnitt {
        border-bottom: none !important; box-shadow: none !important; margin: 0 0 0 2px !important;
        padding-bottom: 0 !important; }
    .st-key-depot_kopf_rechts [data-testid="stWidgetLabel"] { display: none !important; }
    /* Titel in der Kopfzeile senkrecht mittig (wie links), auch wenn der Block gestreckt wird */
    .st-key-depot_kopf_links [data-testid="stMarkdownContainer"],
    .st-key-depot_kopf_rechts [data-testid="stMarkdownContainer"] { display: flex; align-items: center; }
    /* Depot | Kurse nebeneinander: beide Spalten oben buendig, jede so hoch wie ihr Inhalt (UX 10/2026: das
       Strecken der Kurskachel auf die Hoehe der Depot-Spalte liess eine grosse leere Flaeche) */
    @media (min-width: 820px) {
        .st-key-depot_spalten > div > [data-testid="stHorizontalBlock"] { align-items: flex-start !important; }
    }
    /* Depot | Kurse: nebeneinander erst ab 820 px, darunter untereinander */
    @media (max-width: 819px) {
        .st-key-depot_spalten > div > [data-testid="stHorizontalBlock"],
        .st-key-depot_spalten [data-testid="stHorizontalBlock"]:first-of-type {
            flex-direction: column !important; flex-wrap: wrap !important; gap: 0.7rem !important; }
        .st-key-depot_spalten [data-testid="stColumn"] {
            width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
        .st-key-depot_kopf_rechts { margin-top: 14px; }
        /* Kopfzeile "Kurse | Auswahl" auch auf dem Handy in EINER Zeile (sonst ueberdeckt das
           Dropdown den Titel) - Titel so schmal wie noetig, Auswahl nimmt den Rest */
        .st-key-depot_spalten .st-key-depot_kopf_rechts [data-testid="stHorizontalBlock"] {
            flex-direction: row !important; flex-wrap: nowrap !important; gap: 0.6rem !important;
            align-items: center !important; }
        .st-key-depot_spalten .st-key-depot_kopf_rechts [data-testid="stColumn"] {
            min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
        .st-key-depot_spalten .st-key-depot_kopf_rechts [data-testid="stColumn"]:first-child {
            flex: 0 0 auto !important; }
    }
    /* Touch: Plotly-Werkzeugleiste (22-px-Symbole) ausblenden - Zoomen per Fingergeste geht weiter */
    @media (pointer: coarse) { .modebar-container { display: none !important; } }
    [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button { height: auto !important; }
    /* Primaer-Knoepfe: primaryColor ist Weiss - Schrift dunkel, sonst Weiss auf Weiss */
    [data-testid="stBaseButton-primary"]:not(:disabled), [data-testid="stBaseButton-primary"]:not(:disabled) p,
    [data-testid="stBaseButton-primaryFormSubmit"]:not(:disabled),
    [data-testid="stBaseButton-primaryFormSubmit"]:not(:disabled) p {
        color: #0B0B0C !important; }
    /* Mehrfachauswahl: gewaehlte Werte (Tags) haben die Primaerfarbe Weiss als Hintergrund - Schrift dunkel */
    [data-testid="stMultiSelect"] [data-tag], [data-testid="stMultiSelect"] [data-tag] * {
        color: #0B0B0C !important; }
    /* Touch-Geraete: Trefferflaechen mind. 44 px (Apple HIG) */
    @media (pointer: coarse) {
        [data-testid="stButtonGroup"] button { min-height: 44px !important; }
        [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button,
        [data-testid="stDownloadButton"] button { min-height: 44px !important; }
        [data-testid="stExpander"] summary { min-height: 44px; }
        [data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"],
        [data-testid="stDateInputField"], [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            min-height: 44px !important; height: auto !important; }
        [data-testid="stNumberInputField"], [data-testid="stTextInputRootElement"] input { min-height: 44px !important; }
        [data-testid="stTabs"] [role="tab"] { min-height: 44px !important; }
        /* "?"-Hilfe: sichtbar 16 px, Tippflaeche 44 px (360°-Pruefung) */
        /* nur die "?"-Knoepfe selbst - stTooltipIcon umhuellt auch Knoepfe mit Hinweistext (z. B. "Menue");
           Flaeche waechst nach links/oben/unten, nicht ueber den rechten Bildschirmrand */
        button[aria-label^="Help for"] { position: relative; }
        button[aria-label^="Help for"]::before { content: ""; position: absolute; inset: -14px 0 -14px -28px; }
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div { min-height: 44px !important; }
    }

    /* ============================================================
       BLAU-DESIGN (10/2026) - Vorbild "Portfolio Lab": Navy-Grund, ruhige Karten mit
       weichen Rahmen, fette Feldbeschriftungen, dunkle Eingabefelder, Blau als Bedienfarbe.
       Liegt bewusst am Ende und ueberschreibt die frueheren weissen Leucht-Rahmen.
       Gruen/Rot bleiben ausschliesslich Kursveraenderungen vorbehalten.
       ============================================================ */
    :root {
        /* Premium Glass (10/2026, glass_theme.py): Navy, Akzent Periwinkle, zweiter Akzent Tuerkis */
        --ink: #07090F; --surface: #0D1220; --surface-2: #111729; --line: #232A3D;
        --muted: #8A93A8; --label: #A9B1C4; --text: #E8ECF6;
        --accent: #7C9CFF; --accent-hell: #A5B8FF; --accent-2: #5EEAD4; --accent-soft: rgba(124, 156, 255, 0.18);
        --accent-rand: rgba(124, 156, 255, 0.55);
        --pos: #34D399; --neg: #F87171;
        --karte: linear-gradient(160deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.02) 100%);
        /* Raender: feines Glas (glass_theme --glass-border) */
        --rand: rgba(255, 255, 255, 0.12);
        --rand-glow: 0 0 0 transparent;
    }
    .stApp {
        background:
            radial-gradient(1200px 600px at 10% -10%, rgba(124, 156, 255, 0.18), transparent 60%),
            radial-gradient(900px 500px at 110% 10%, rgba(94, 234, 212, 0.12), transparent 60%),
            radial-gradient(800px 600px at 50% 120%, rgba(167, 139, 250, 0.12), transparent 60%),
            linear-gradient(180deg, var(--surface), var(--ink)) !important;
        background-color: var(--ink) !important;
        background-attachment: fixed !important;
    }
    [data-testid="stHeader"], [data-testid="stBottomBlockContainer"] { background: transparent !important; }

    /* Karten: Kacheln, Aufklappbereiche und umrandete Bloecke (.karte setzt das Lade-Skript) */
    .quote, .hero, .karte {
        background: var(--karte) !important;
        border: 1px solid var(--rand) !important;
        border-radius: 22px !important;
        -webkit-backdrop-filter: blur(20px) saturate(160%); backdrop-filter: blur(20px) saturate(160%);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.10), 0 12px 32px rgba(0, 0, 0, 0.35), var(--rand-glow);
        position: relative;
    }
    .karte { padding: 18px 18px 16px !important; }
    @media (max-width: 640px) { .karte { padding: 14px 14px 12px !important; } }
    [data-testid="stExpander"] {
        background: var(--karte) !important;
        border: 1px solid var(--rand) !important;
        border-radius: 16px !important;
        box-shadow: 0 6px 18px rgba(11, 11, 11, 0.28), var(--rand-glow) !important;
    }
    [data-testid="stExpander"]:hover { border-color: var(--accent-rand) !important;
                                       box-shadow: 0 6px 18px rgba(11, 11, 11, 0.28) !important; }
    [data-testid="stExpander"] summary:hover, [data-testid="stExpander"] summary:hover p { color: var(--accent-hell) !important; }

    /* Feldbeschriftungen: fett und hell wie im Vorbild, nicht als Grossbuchstaben-Ueberschrift */
    [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label,
    [data-testid="stSelectbox"] label, [data-testid="stSelectbox"] label p {
        font-size: 0.9rem !important; font-weight: 600 !important; color: #DFE0E2 !important;
        letter-spacing: 0.1px !important; text-transform: none !important; text-shadow: none !important;
    }

    /* Eingabefelder: dunkle Flaeche, feiner Rahmen, blauer Fokus */
    [data-baseweb="input"], [data-baseweb="textarea"], [data-testid="stNumberInputContainer"],
    [data-testid="stDateInputField"], [data-baseweb="base-input"] {
        background-color: var(--surface-2) !important;
        border-color: var(--rand) !important;
        border-radius: 12px !important;
    }
    [data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
    [data-testid="stNumberInputContainer"]:focus-within {
        border-color: var(--accent) !important; box-shadow: 0 0 0 3px var(--accent-soft) !important;
    }
    [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {
        background: transparent !important; color: var(--label) !important; border-radius: 10px !important;
    }
    [data-testid="stNumberInputStepUp"]:hover, [data-testid="stNumberInputStepDown"]:hover {
        background: var(--accent-soft) !important; color: var(--accent-hell) !important;
    }

    /* Auswahlfelder: ruhiger Rahmen statt weissem Leuchten und Puls */
    [data-testid="stSelectbox"] > div, [data-testid="stSelectbox"] [data-baseweb="select"] {
        outline: none !important; box-shadow: none !important; animation: none !important;
        background-color: var(--surface-2) !important; border-radius: 12px !important;
    }
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        border: 1px solid var(--rand) !important; border-radius: 12px !important;
        background-color: var(--surface-2) !important;
    }
    [data-testid="stSelectbox"] > div:hover [data-baseweb="select"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {
        border-color: var(--accent-rand) !important; box-shadow: 0 0 0 3px var(--accent-soft) !important;
    }
    [data-testid="stSelectbox"] > div:hover, [data-testid="stSelectbox"] > div:focus-within { box-shadow: none !important; }
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
        background-color: var(--surface-2) !important; border-color: var(--rand) !important; border-radius: 12px !important;
    }
    [data-testid="stMultiSelect"] [data-tag] { background: var(--accent) !important; }
    [data-testid="stMultiSelect"] [data-tag], [data-testid="stMultiSelect"] [data-tag] * { color: #151516 !important; }

    /* Pillen und Knoepfe (sekundaer/primaer): Glas-Optik - siehe GLAS am Ende von CSS_NAV */

    /* Reiter: blaue Markierung */
    [data-testid="stTabs"] [aria-selected="true"], [data-testid="stTabs"] [aria-selected="true"] p { color: var(--accent-hell) !important; }

    /* Hinweisboxen im Blau-Ton */
    [data-testid="stAlertContentInfo"] { color: #A5B8FF !important; }
    [data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) > div {
        background: rgba(124, 156, 255, 0.1) !important; border: 1px solid rgba(124, 156, 255, 0.28) !important;
        border-radius: 14px !important;
    }

</style>
"""

CSS_NAV = """
<style>
/* ================= STARTSEITE: Neon-Weiss ================= */
.st-key-nav_menue { max-width: 100%; margin: 0 auto; position: relative; }
/* Kacheln je Gruppe: Handy 2, Tablet 3, Desktop 4, breite Monitore 5 je Zeile */
.st-key-nav_menue [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
.st-key-nav_menue [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 0 1 calc((100% - 12px) / 2) !important; max-width: calc((100% - 12px) / 2) !important; }
@media (min-width: 760px) {
  .st-key-nav_menue [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
      flex-basis: calc((100% - 24px) / 3) !important; max-width: calc((100% - 24px) / 3) !important; } }
@media (min-width: 1150px) {
  .st-key-nav_menue [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
      flex-basis: calc((100% - 36px) / 4) !important; max-width: calc((100% - 36px) / 4) !important; } }
@media (min-width: 1700px) {
  .st-key-nav_menue [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
      flex-basis: calc((100% - 48px) / 5) !important; max-width: calc((100% - 48px) / 5) !important; } }
.st-key-nav_menue::before {
    content: ""; position: absolute; inset: -30px -10px; z-index: -1; pointer-events: none;
    background: radial-gradient(520px 320px at 50% 0%, rgba(255, 255, 255, 0.07), transparent 70%);
}
.st-key-nav_menue [data-testid="stVerticalBlock"] { gap: 12px !important; }
.st-key-nav_menue [data-testid="stHorizontalBlock"] { gap: 12px !important; }
.st-key-nav_menue [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
/* Streamlit zieht Markdown-Bloecke unten um 1rem hoch - hier nicht (sonst
   rutschen die Ueberschriften unter die Kacheln) */
.st-key-nav_menue [data-testid="stMarkdown"], .st-key-nav_menue .stMarkdown,
.st-key-nav_menue [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }

/* Kopf */
.nav-kopf { text-align: center; padding: 0 0 4px; margin-top: -26px; }
.nav-credit { font-size: 0.8rem; letter-spacing: 1.5px; color: #FFFFFF; margin-top: 3px;
              text-shadow: 0 0 6px rgba(255, 255, 255, 0.35); }
.nav-logo {
    font-family: 'Inter', -apple-system, sans-serif; font-size: 1.5rem; font-weight: 700;
    letter-spacing: 5px; color: #FFFFFF; text-transform: uppercase;
    text-shadow: 0 0 8px rgba(255, 255, 255, 0.45), 0 0 20px rgba(255, 255, 255, 0.15);
}
.nav-logo .nav-lauf > span { font-weight: 300; }
.nav-chip {
    /* Glas-Pille wie die Knoepfe (GLAS) */
    display: inline-flex; align-items: center; gap: 8px; margin: 12px 0 6px; padding: 7px 16px;
    border-radius: 999px; font-size: 0.8rem; font-weight: 700;
}
.nav-chip b { font-weight: 700; }
.nav-dot { width: 7px; height: 7px; border-radius: 50%; background: #34D399;
           box-shadow: 0 0 8px #34D399; animation: navpuls 2.4s ease-in-out infinite; }
@keyframes navpuls { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

/* Lichtschimmer, der langsam durch die Ueberschriften laeuft (alle 6 s,
   dazwischen Ruhe). Text = Verlauf, per background-clip auf die Schrift begrenzt. */
.nav-lauf {
    background: linear-gradient(100deg,
        rgba(255, 255, 255, 0.8) 0%, rgba(255, 255, 255, 0.8) 40%, #FFFFFF 47%, #FFFFFF 53%,
        rgba(255, 255, 255, 0.8) 60%, rgba(255, 255, 255, 0.8) 100%);
    background-size: 300% 100%; background-position: 100% 0;
    -webkit-background-clip: text; background-clip: text; color: transparent !important;
    -webkit-text-fill-color: transparent;
    animation: navschimmer 6s ease-in-out infinite;
}
.nav-logo .nav-lauf {
    background-image: linear-gradient(100deg,
        rgba(255, 255, 255, 0.82) 0%, rgba(255, 255, 255, 0.82) 40%, #FFFFFF 47%, #FFFFFF 53%,
        rgba(255, 255, 255, 0.82) 60%, rgba(255, 255, 255, 0.82) 100%);
}
@keyframes navschimmer { 0% { background-position: 100% 0; } 55%, 100% { background-position: 0% 0; } }
@media (prefers-reduced-motion: reduce) { .nav-lauf { animation: none; } }

/* Gruppen-Ueberschrift: schiesst beim Oeffnen einmal blitzschnell nach rechts
   aus dem Bild, kommt links wieder herein, bleibt stehen und pulsiert leicht */
.nav-gruppe {
    position: relative; height: 38px; margin: 0 4px; overflow: hidden;
    font-size: 0.8rem; font-weight: 700; letter-spacing: 2.2px; text-transform: uppercase; color: var(--label);
}
.nav-gruppe::after {
    content: ""; position: absolute; left: 0; right: 0; bottom: 7px; height: 1px;
    background: var(--trenn);
}
.nav-wander {
    position: absolute; bottom: 12px; left: 0; white-space: nowrap;
    /* Blitz nur einmal beim Oeffnen des Menues, danach stehen bleiben und pulsieren */
    animation: navblitz 0.6s 1 both, navpulsieren 2s ease-in-out infinite;
}
@keyframes navblitz {
    0%     { left: 0;    transform: translateX(0);     animation-timing-function: cubic-bezier(.7, 0, 1, .6); filter: none; }
    50%    { left: 100%; transform: translateX(0);     filter: blur(1.2px); }
    50.1%  { left: 0;    transform: translateX(-100%); animation-timing-function: cubic-bezier(0, .5, .3, 1); filter: blur(1.2px); }
    100%   { left: 0;    transform: translateX(0);     filter: none; }
}
@keyframes navpulsieren {
    0%, 100% { text-shadow: 0 0 2px rgba(255, 255, 255, 0.2); opacity: 0.6; }
    50%      { text-shadow: 0 0 6px rgba(255, 255, 255, 0.9), 0 0 14px rgba(255, 255, 255, 0.5); opacity: 1; }
}
/* Rand der Menue-Tasten pulsiert leicht: eigener Leuchtring (::after) ueber
   dem Rand - der eigentliche Rand ist per !important gesetzt und liesse sich
   nicht animieren */
/* (frueher: pulsierender weisser Leuchtring um die Kacheln - ersetzt durch den Glas-Glow, siehe GLAS) */
@keyframes navrandpuls {
    0%, 100% { opacity: 0.35; box-shadow: 0 0 0 rgba(255, 255, 255, 0); }
    50%      { opacity: 1;    box-shadow: 0 0 5px rgba(255, 255, 255, 0.45); }
}

/* Titel "FINANZ DASHBOARD" pulsiert ebenfalls dauerhaft */
.nav-logo { animation: navlogopuls 2s ease-in-out infinite; }
@keyframes navlogopuls {
    0%, 100% { text-shadow: 0 0 3px rgba(255, 255, 255, 0.25); opacity: 0.72; }
    50%      { text-shadow: 0 0 8px rgba(255, 255, 255, 0.9), 0 0 20px rgba(255, 255, 255, 0.45); opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
    .nav-wander, .nav-logo, .st-key-nav_menue [data-testid="stButton"] button::after { animation: none; }
}

/* Menue-Kacheln: Groesse und Form - das Aussehen (Glas) steht unter GLAS */
.st-key-nav_menue [data-testid="stButton"] button {
    position: relative; width: 100% !important; min-height: 58px !important; border-radius: 18px !important;
    padding: 8px 6px !important;
}
.st-key-nav_menue [data-testid="stButton"] button > div { min-width: 0; max-width: 100%; }
.st-key-nav_menue [data-testid="stButton"] button p {
    /* immer einzeilig: Schrift waechst/schrumpft mit der Bildschirmbreite */
    font-size: clamp(0.8rem, 3.4vw, 0.95rem) !important; font-weight: 700 !important; line-height: 1.2 !important;
    white-space: nowrap !important; overflow: hidden; text-overflow: ellipsis;
    color: #FFFFFF !important; letter-spacing: 0.2px;
    text-shadow: none !important;     /* Schatten wuerde hinter Emojis dunkle Kaestchen erzeugen */
}
/* sehr schmale Telefone (iPhone SE 1. Gen., 320 px): lange Namen zweizeilig statt ueber den Rand */
/* Zu lange Namen brechen um statt ueber den Kachelrand zu laufen (jede Breite) */
.st-key-nav_menue [data-testid="stButton"] button p { white-space: normal !important; overflow-wrap: normal;
    text-overflow: clip !important; overflow: visible !important; }   /* zweizeilig zwischen Woertern (UX 10/2026: mind. 12,8 px) */
.st-key-nav_menue .st-key-nav_refresh button p { font-size: 0.8rem !important; font-weight: 700 !important; }

/* Aktualisieren: schlanke Neon-Pille */
/* klein und mittig direkt unter der Kurs-Pille */
/* Streamlit gibt dem Button-Container bei width="content" nur Inhaltsbreite -
   deshalb den Container selbst mittig setzen (align-self + auto-Rand) */
.st-key-nav_menue .st-key-nav_refresh {
    align-self: center !important; margin-left: auto !important; margin-right: auto !important;
    margin-top: -4px; display: flex !important; justify-content: center !important;
}
.st-key-nav_menue .st-key-nav_refresh [data-testid="stButton"] {
    width: auto !important; display: flex !important; justify-content: center !important;
}
.st-key-nav_menue .st-key-nav_refresh button {
    width: auto !important; min-height: 34px !important; padding: 2px 18px !important; border-radius: 999px !important;
}

/* ================= IN EINER ANSICHT: Kopfleiste ================= */
.st-key-nav_leiste {
    padding: 6px 8px; border-radius: 18px;
    background: var(--karte);                       /* Glas wie die Karten (hell und dunkel gleich) */
    -webkit-backdrop-filter: blur(22px) saturate(160%); backdrop-filter: blur(22px) saturate(160%);
    border: 1px solid var(--rand);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 10px 24px rgba(11, 11, 11, 0.45);
}
.st-key-nav_leiste [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important;
                                                       align-items: center !important; }
.st-key-nav_leiste [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
.st-key-nav_leiste [data-testid="stColumn"]:nth-child(1),
.st-key-nav_leiste [data-testid="stColumn"]:nth-child(3) { flex: 0 0 auto !important; }
.st-key-nav_leiste [data-testid="stColumn"]:nth-child(2) { flex: 1 1 auto !important; }
.st-key-nav_leiste [data-testid="stButton"] button {
    min-height: 44px !important; min-width: 44px !important; border-radius: 14px !important; padding: 4px 12px !important;
    white-space: nowrap !important;
}
.st-key-nav_leiste [data-testid="stButton"] button p { font-weight: 700 !important; }
.nav-titel {
    font-size: 1.02rem; font-weight: 700; color: #FFFFFF; line-height: 1.2;
    overflow-wrap: anywhere; text-align: center; letter-spacing: 0.3px;
    text-shadow: none;
}
.nav-stand { display: flex; justify-content: center; margin: 6px 0 4px; }
.nav-stand span { display: inline-block; font-size: 0.78rem; line-height: 1.5;
    color: var(--label, #9AA0A6); padding: 2px 12px; border: 1px solid rgba(165, 184, 255, 0.25); border-radius: 14px;
    max-width: 100%; box-sizing: border-box; text-align: center; }
.nav-stand span > i { margin-right: 6px; vertical-align: 1px; }
.nav-stand b { color: #FFFFFF; font-weight: 600; }
.nav-stand i { width: 6px; height: 6px; border-radius: 50%; background: #34D399; display: inline-block; }
@media (max-width: 700px) {
    .nav-logo { font-size: 1.22rem; letter-spacing: 3.5px; }
    .st-key-nav_menue [data-testid="stButton"] button { min-height: 58px !important; }
    .st-key-nav_menue .st-key-nav_refresh button { min-height: 44px !important; }
    .nav-titel { font-size: 0.92rem; }
    .st-key-nav_leiste [data-testid="stButton"] button { padding: 4px 9px !important; }
}

/* ================= GLAS: Premium Glass (glass_theme.py, 10/2026) =================
   Baut auf glass_theme.py auf und setzt dessen Look app-weit durch (die App hat eigene, spezifischere
   Regeln): Glasflaeche mit Blur, Glanzstreifen oben (::before), durchlaufender Lichtreflex beim Hover
   (::after), Press-Feedback. Hauptaktion: getoentes Glas Periwinkle -> Tuerkis mit Akzent-Glow.
   Einheitliche Hoehe: 44 px am Desktop, 48 px auf Touch-Geraeten. ALLE Farben nur ueber Variablen - die helle
   Ansicht setzt eigene Werte (ui_hell.WIDGETS); Farbliterale hier wuerden von ui_hell (fuer Schatten falsch)
   umgerechnet. */
:root {
    --g-schrift: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    --g-zahl: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    --g-ease: cubic-bezier(.2, .8, .2, 1);
    --g-hoehe: 44px;
    --glas-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.14) 0%, rgba(255, 255, 255, 0.03) 100%), rgba(255, 255, 255, 0.055);
    --glas-bg-hover: linear-gradient(180deg, rgba(255, 255, 255, 0.18) 0%, rgba(255, 255, 255, 0.05) 100%), rgba(255, 255, 255, 0.09);
    --glas-rand: rgba(255, 255, 255, 0.12);
    --glas-rand-stark: rgba(255, 255, 255, 0.22);
    --glas-glanz: linear-gradient(180deg, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0));
    --glas-reflex: linear-gradient(110deg, transparent, rgba(255, 255, 255, 0.28), transparent);
    --glas-licht: rgba(255, 255, 255, 0.25);
    --glas-tiefe: rgba(0, 0, 0, 0.25);
    --glas-schatten: inset 0 1px 0 rgba(255, 255, 255, 0.25), inset 0 -1px 0 rgba(0, 0, 0, 0.25),
                     0 10px 40px -12px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.25);
    --glas-schatten-hover: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 0 0 1px rgba(124, 156, 255, 0.25),
                           0 14px 40px -10px rgba(124, 156, 255, 0.45);
    --glas-schatten-press: inset 0 2px 8px rgba(0, 0, 0, 0.35), 0 4px 14px -6px rgba(0, 0, 0, 0.5);
    --glas-text: #E8ECF6;
    --glas-text-hover: #FFFFFF;
    --glas-glow-stark: rgba(124, 156, 255, 0.35);
    --glas-rand-flach: rgba(255, 255, 255, 0.12);
    --karte-schatten: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 10px 40px -12px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.25);
    --trenn: rgba(255, 255, 255, 0.10);
    --seg-spur: rgba(255, 255, 255, 0.055);
    --seg-daumen: linear-gradient(180deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0.06));
    --seg-daumen-schatten: inset 0 1px 0 rgba(255, 255, 255, 0.30), 0 4px 14px -4px rgba(0, 0, 0, 0.5);
    --seg-text: #8A93A8;
    --seg-text-aktiv: #FFFFFF;
    --chip-aktiv-bg: linear-gradient(135deg, rgba(124, 156, 255, 0.36), rgba(94, 234, 212, 0.18));
    --chip-aktiv-rand: rgba(124, 156, 255, 0.55);
    --chip-aktiv-text: #FFFFFF;
    --glas-primaer-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.20) 0%, rgba(255, 255, 255, 0) 60%),
                       linear-gradient(135deg, rgba(124, 156, 255, 0.55), rgba(94, 234, 212, 0.35));
    --glas-primaer-rand: rgba(124, 156, 255, 0.45);
    --glas-primaer-text: #FFFFFF;
    --glas-primaer-schatten: inset 0 1px 0 rgba(255, 255, 255, 0.4), 0 10px 30px -8px rgba(124, 156, 255, 0.6);
    --glas-primaer-schatten-hover: inset 0 1px 0 rgba(255, 255, 255, 0.5), 0 0 0 1px rgba(124, 156, 255, 0.5),
                                   0 16px 44px -8px rgba(124, 156, 255, 0.75);
    --glas-fokus: 0 0 0 3px rgba(124, 156, 255, 0.35);
    --feld-bg: rgba(255, 255, 255, 0.04);
    --feld-innen: inset 0 1px 2px rgba(0, 0, 0, 0.25);
}
@media (pointer: coarse), (max-width: 768px) { :root { --g-hoehe: 48px; } }

/* ---- Glasflaeche: Knoepfe, Menuekacheln, Kopfleiste, Download, Pillen, Chips ---- */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button[data-variant="pills"], .nav-chip
    ):not(.st-key-logout_ecke *) {
    background: var(--glas-bg) !important;
    border: 1px solid var(--glas-rand) !important;
    -webkit-backdrop-filter: blur(22px) saturate(170%); backdrop-filter: blur(22px) saturate(170%);
    box-shadow: var(--glas-schatten) !important;
    color: var(--glas-text) !important;
    font-family: var(--g-schrift) !important;
    transform: none !important; animation: none !important;
    transition: transform .25s var(--g-ease), box-shadow .25s var(--g-ease), border-color .25s var(--g-ease),
                background .25s var(--g-ease) !important;
    position: relative; isolation: isolate; overflow: hidden;
    -webkit-tap-highlight-color: transparent;
}
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button, [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *) :is(p, span, div) {
    font-family: var(--g-schrift) !important; font-weight: 600 !important; letter-spacing: 0.01em !important;
    color: inherit !important; text-shadow: none !important;
}
/* Einheitliche Hoehe und Form: Knoepfe 14 px Radius, Pillen als Kapsel, Menuekacheln 20 px */
html body :is([data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"], .st-key-nav_leiste [data-testid="stButton"] button
    ):not(.st-key-logout_ecke *) {
    border-radius: 14px !important; min-height: var(--g-hoehe) !important;
}
html body [data-testid="stButtonGroup"] button:not(.st-key-logout_ecke *),
html body .st-key-nav_menue .st-key-nav_refresh button {
    border-radius: 999px !important; min-height: var(--g-hoehe) !important;
}
html body .st-key-nav_menue [data-testid="stButton"] button:not(.st-key-logout_ecke *):not(.st-key-nav_refresh *) {
    border-radius: 20px !important; min-height: 60px !important;
}
/* Glanzstreifen oben */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button[data-variant="pills"],
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *)::before {
    content: "" !important; display: block !important; position: absolute; inset: 0 0 50% 0; border-radius: inherit;
    background: var(--glas-glanz); pointer-events: none; z-index: -1; animation: none !important; border: 0 !important;
    box-shadow: none !important; opacity: 1;
}
/* Lichtreflex: laeuft beim Hover einmal durch */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button[data-variant="pills"],
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *)::after {
    content: "" !important; display: block !important; position: absolute; top: 0; left: -120%; width: 60%; height: 100%;
    inset: 0 auto auto -120%; padding: 0 !important; border: 0 !important; border-radius: 0 !important;
    background: var(--glas-reflex) !important; transform: skewX(-20deg); transition: left .7s var(--g-ease), inset .7s var(--g-ease);
    pointer-events: none; animation: none !important; box-shadow: none !important; opacity: 1;
    -webkit-mask: none !important; mask: none !important;
}
/* Darueberfahren: heller, Akzent-Schimmer, hebt sich; Druecken: sinkt ein */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button[data-variant="pills"]
    ):not(.st-key-logout_ecke *):is(:hover, :focus-visible):not(:disabled) {
    background: var(--glas-bg-hover) !important; border-color: var(--glas-rand-stark) !important;
    box-shadow: var(--glas-schatten-hover) !important; color: var(--glas-text-hover) !important;
}
@media (hover: hover) {
    html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
        [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
        [data-testid="stDownloadButton"] button, [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *):hover:not(:disabled) {
        transform: translateY(-2px) !important;
    }
    html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
        [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
        [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button[data-variant="pills"],
        [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *):hover:not(:disabled)::after {
        left: 140%; inset: 0 auto auto 140%;
    }
}
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button,
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *):active:not(:disabled) {
    transform: translateY(0) scale(0.98) !important; box-shadow: var(--glas-schatten-press) !important;
}
html body :is([data-testid="stButton"], [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"],
    [data-testid="stButtonGroup"]) button:not(.st-key-logout_ecke *):focus-visible {
    outline: 2px solid var(--accent) !important; outline-offset: 3px !important;
}

/* ---- Pillen (st.pills): Auswahl als getoentes Akzent-Glas ---- */
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] button[data-variant="pills"]:is([aria-checked="true"], [aria-pressed="true"]):not(.st-key-x) {
    background: var(--chip-aktiv-bg) !important; color: var(--chip-aktiv-text) !important;
    border-color: var(--chip-aktiv-rand) !important;
}

/* ---- Umschalter (st.segmented_control): Glas-Spur wie die Reiter, Auswahl als heller Glas-Daumen ---- */
html body [data-testid="stButtonGroup"] [role="radiogroup"]:has(> button[data-variant="segmented_control"]),
html body [data-testid="stButtonGroup"] [role="group"]:has(> button[data-variant="segmented_control"]) {
    /* 26 px statt 999 px: einzeilig wirkt es als Kapsel, umgebrochen (viele Optionen am Handy) als ruhige Flaeche */
    background: var(--seg-spur) !important; border: 1px solid var(--glas-rand) !important; border-radius: 26px !important;
    padding: 3px !important; gap: 3px !important; box-shadow: none !important;
    -webkit-backdrop-filter: blur(22px); backdrop-filter: blur(22px);
}
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] button[data-variant="segmented_control"]:not(.st-key-x) {
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: var(--seg-text) !important; font-family: var(--g-schrift) !important;
    min-height: var(--g-hoehe) !important; border-radius: 999px !important;
    -webkit-backdrop-filter: none; backdrop-filter: none;
    transition: background .25s var(--g-ease), box-shadow .25s var(--g-ease), color .25s var(--g-ease) !important;
}
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] button[data-variant="segmented_control"]:not(.st-key-x)::before,
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] button[data-variant="segmented_control"]:not(.st-key-x)::after {
    content: none !important; display: none !important;
}
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] button[data-variant="segmented_control"]:is([aria-checked="true"], [aria-pressed="true"]):not(.st-key-x) {
    background: var(--seg-daumen) !important; box-shadow: var(--seg-daumen-schatten) !important;
    color: var(--seg-text-aktiv) !important;
}
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] button[data-variant="segmented_control"]:not([aria-checked="true"]):hover:not(:disabled) {
    color: var(--glas-text) !important; background: transparent !important;
}

/* ---- Hauptaktion (type="primary"): getoentes Glas mit Akzent-Glow ---- */
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *):not(.st-key-x) {
    background: var(--glas-primaer-bg) !important; border: 1px solid var(--glas-primaer-rand) !important;
    box-shadow: var(--glas-primaer-schatten) !important; font-family: var(--g-schrift) !important;
    -webkit-backdrop-filter: blur(22px) saturate(170%); backdrop-filter: blur(22px) saturate(170%);
    transform: none; animation: none !important; position: relative; isolation: isolate; overflow: hidden;
    transition: transform .25s var(--g-ease), box-shadow .25s var(--g-ease) !important;
}
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(:disabled),
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(:disabled) :is(p, span) {
    color: var(--glas-primaer-text) !important;
}
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):is(:hover, :focus-visible):not(:disabled):not(.st-key-x) {
    box-shadow: var(--glas-primaer-schatten-hover) !important;
}
/* Deaktiviert: matt, ohne Glanz und Schatten */
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):disabled:not(.st-key-x):not(.st-key-y) {
    background: var(--glas-bg) !important; border-color: var(--glas-rand) !important; }
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):disabled:not(.st-key-x) :is(p, span) {
    color: var(--glas-text) !important; }
html body :is([data-testid="stButton"], [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"],
    [data-testid="stButtonGroup"]) button:disabled:not(.st-key-logout_ecke *):not(.st-key-x):not(.st-key-y) {
    box-shadow: none !important; opacity: 0.5; transform: none !important;
}
/* Werkzeug-/Symbolknoepfe von Streamlit (Tabellen-Toolbar, Kopfzeile) nicht als grosse Glasknoepfe */
html body :is([data-testid="stBaseButton-elementToolbar"], [data-testid="stBaseButton-minimal"],
    [data-testid="stBaseButton-borderlessIcon"], [data-testid^="stBaseButton-header"], [data-testid="stBaseButton-tertiary"]) {
    padding: revert !important; background: transparent !important; border: none !important; box-shadow: none !important;
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important; min-height: 0 !important;
}
html body :is([data-testid="stBaseButton-elementToolbar"], [data-testid="stBaseButton-minimal"],
    [data-testid="stBaseButton-borderlessIcon"], [data-testid^="stBaseButton-header"], [data-testid="stBaseButton-tertiary"])::after,
html body :is([data-testid="stBaseButton-elementToolbar"], [data-testid="stBaseButton-minimal"],
    [data-testid="stBaseButton-borderlessIcon"], [data-testid^="stBaseButton-header"], [data-testid="stBaseButton-tertiary"])::before {
    content: none !important; display: none !important;
}
/* Pillen-Spur ohne eigene Flaeche (die Segment-Spur oben setzt ihre Flaeche selbst) */
[data-testid="stButtonGroup"], [data-testid="stButtonGroup"] div:not(button div):not([role="radiogroup"]):not([role="group"]) {
    background: transparent !important; box-shadow: none !important; }
[data-testid="stButtonGroup"] [role="radiogroup"]:not(:has(> button[data-variant="segmented_control"])) {
    background: transparent !important; box-shadow: none !important; border: none !important; }

/* ---- Gruppen-Ueberschriften im Menue: ruhig, ohne Pulsieren ---- */
html body .nav-gruppe { font-family: var(--g-schrift); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em;
    color: var(--label); }
html body .nav-gruppe::after { background: var(--trenn); height: 1px; }
/* Logo und Gruppen-Ueberschriften pulsieren gemeinsam (gleiches Leuchten); die Ueberschriften schweben beim
   Oeffnen des Menues einmal von rechts nach links herein. Leuchtfarbe ueber --puls-licht (hell: Akzent statt Weiss). */
:root { --puls-licht: rgba(255, 255, 255, 0.9); --puls-licht-weit: rgba(255, 255, 255, 0.4); }
html body .nav-logo { animation: navpuls-glas 2.4s ease-in-out infinite !important; }
/* Raketenflug beim Oeffnen des Menues: einmal ganz nach rechts (mit Feuerschweif hinten), dort umdrehen, zurueck
   zur Ausgangsposition, wieder umdrehen - dann stehen bleiben und pulsieren. --verzug staffelt die Gruppen (app.py). */
html body .nav-wander { opacity: 1; filter: none !important; transform-style: preserve-3d;
    animation: navrakete 3.2s linear 1 both, navpuls-glas 2.4s ease-in-out infinite !important;
    animation-delay: var(--verzug, 0s), calc(var(--verzug, 0s) + 3.2s) !important; }
html body .nav-wander::before {
    content: ""; position: absolute; right: 100%; top: 50%; width: 72px; height: 70%; margin-right: 4px;
    transform: translateY(-50%); border-radius: 50% 0 0 50%; pointer-events: none; opacity: 0;
    background: linear-gradient(to left, rgba(255,255,255,.95), #FFD166 18%, #FF7A2C 45%, rgba(255,60,40,.55) 70%,
                                transparent);
    filter: blur(3px); box-shadow: 0 0 18px 6px rgba(255,140,40,.45);
    animation: navflamme 3.2s linear 1 both, navflackern 0.12s steps(2) 18;
    animation-delay: var(--verzug, 0s), var(--verzug, 0s);
}
@keyframes navrakete {
    0%   { left: 0;    transform: translateX(0) rotateY(0deg); animation-timing-function: cubic-bezier(.55, 0, .9, .6); }
    42%  { left: 100%; transform: translateX(-100%) rotateY(0deg); animation-timing-function: ease-in-out; }
    54%  { left: 100%; transform: translateX(-100%) rotateY(180deg); animation-timing-function: cubic-bezier(.55, 0, .9, .6); }
    90%  { left: 0;    transform: translateX(0) rotateY(180deg); animation-timing-function: ease-out; }
    100% { left: 0;    transform: translateX(0) rotateY(360deg); }
}
/* Schweif nur im Flug: an beim Start, aus beim Wenden, wieder an auf dem Rueckweg, aus bei der Ankunft */
@keyframes navflamme {
    0%, 100% { opacity: 0; width: 20px; }
    6%, 38%  { opacity: 1; width: 72px; }
    46%, 58% { opacity: 0; width: 20px; }
    64%, 84% { opacity: 1; width: 72px; }
    92%      { opacity: 0; width: 20px; }
}
@keyframes navflackern { 50% { filter: blur(4px) brightness(1.3); } }
@keyframes navpuls-glas {
    0%, 100% { text-shadow: 0 0 2px transparent; opacity: 0.8; }
    50%      { text-shadow: 0 0 8px var(--puls-licht), 0 0 20px var(--puls-licht-weit); opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
    html body :is(.nav-logo, .nav-wander) { animation: none !important; }
    html body .nav-wander::before { display: none; }
}

/* ---- Karten, Klappbereiche, Formulare, Metriken: Glas-Karte (20 px Radius) ---- */
.quote::after, .hero::after { content: none; }
html body :is([data-testid="stExpander"] details, [data-testid="stForm"], [data-testid="stMetric"]) {
    border: 1px solid var(--rand) !important; border-radius: 20px !important;
    background: var(--karte) !important;
    -webkit-backdrop-filter: blur(22px) saturate(160%); backdrop-filter: blur(22px) saturate(160%);
    box-shadow: var(--karte-schatten) !important;
}
html body [data-testid="stMetric"] { padding: 16px 20px !important; }
@media (max-width: 640px) { html body [data-testid="stMetric"] { padding: 14px 16px !important; } }
html body [data-testid="stMetricValue"], html body [data-testid="stMetricValue"] * {
    font-family: var(--g-zahl) !important; font-weight: 600 !important; font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em !important; }
html body [data-testid="stMetricDelta"], html body [data-testid="stMetricDelta"] * {
    font-family: var(--g-zahl) !important; font-weight: 500 !important; font-variant-numeric: tabular-nums; }
html body [data-testid="stMetricLabel"] p { font-family: var(--g-schrift) !important; color: var(--muted) !important;
    font-size: 0.78rem !important; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600 !important; }

/* ---- Eingabefelder: Glas, 14 px Radius, Akzent-Fokus, Touch 48 px ---- */
html body :is([data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"],
    [data-testid="stDateInputField"], [data-testid="stSelectbox"] [role="group"], [data-baseweb="textarea"],
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div) {
    border-radius: 14px !important; border-color: var(--rand) !important; background-color: var(--feld-bg) !important;
    box-shadow: var(--feld-innen) !important; min-height: var(--g-hoehe) !important;
}
html body :is([data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"],
    [data-testid="stDateInputField"], [data-testid="stSelectbox"] [role="group"], [data-baseweb="textarea"]):focus-within {
    border-color: var(--accent) !important; box-shadow: var(--glas-fokus) !important;
}
html body :is([data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"]) {
    min-width: 40px !important; min-height: calc(var(--g-hoehe) - 2px) !important;
}

/* ---- Depot-Hero: Depotwert gross (Mono), Heute/Gesamt als Badges, darunter st.metric-Karten ---- */
html body .depot-hero .hero-label { font-family: var(--g-schrift); font-size: 0.78rem; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
html body .depot-hero .hero-val { font-family: var(--g-zahl) !important; font-weight: 600 !important;
    font-size: clamp(2rem, 8.5vw, 2.75rem) !important; letter-spacing: -0.03em !important;
    font-variant-numeric: tabular-nums; line-height: 1.1 !important; color: var(--text) !important; }
html body .depot-hero .price-line { flex-wrap: wrap; row-gap: 8px; margin: 8px 0 4px; }
.hero-badges { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 8px; }
.hero-badge { display: inline-flex; align-items: center; gap: 8px; min-height: 32px; padding: 4px 12px;
    border-radius: 999px; font-size: 0.85rem; font-weight: 600; border: 1px solid var(--rand);
    background: var(--glas-bg); white-space: nowrap; max-width: 100%; }
.hero-badge .hb-t { color: var(--muted); font-family: var(--g-schrift); }
.hero-badge .hb-z { font-family: var(--g-zahl); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
.hero-badge.up { color: var(--pos); background: rgba(52, 211, 153, 0.12); border-color: rgba(52, 211, 153, 0.35); }
.hero-badge.down { color: var(--neg); background: rgba(248, 113, 113, 0.12); border-color: rgba(248, 113, 113, 0.35); }
@media (max-width: 400px) { .hero-badge { white-space: normal; } }
.st-key-depot_kpis { gap: 8px !important; margin-top: 8px; }
html body .st-key-depot_kpis [data-testid="stHorizontalBlock"][data-testid="stHorizontalBlock"] {
    flex-direction: row !important; flex-wrap: nowrap !important; gap: 8px !important; }
html body .st-key-depot_kpis [data-testid="stHorizontalBlock"] > [data-testid="stColumn"][data-testid="stColumn"] {
    min-width: 0 !important; flex: 1 1 0 !important; width: calc(50% - 4px) !important; max-width: calc(50% - 4px) !important; }
html body .st-key-depot_kpis [data-testid="stMetricValue"] { font-size: clamp(1.05rem, 4.4vw, 1.45rem) !important; }
html body [data-testid="stMetricValue"] > div { overflow: visible !important; text-overflow: clip !important; }
/* Metrik-Deltas in den Theme-Farben (gruen #34d399 / rot #f87171) */
html body [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]),
html body [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) * { color: var(--pos) !important; }
html body [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]),
html body [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) * { color: var(--neg) !important; }

/* ---- Touch-Ziele mind. 48 px (iPhone/iPad): Klappbereiche, Schritt-Chips ---- */
html body [data-testid="stExpander"] summary { min-height: var(--g-hoehe) !important; box-sizing: border-box; }
html body .sf-leiste :is(a.sf-s, span.sf-s) { min-height: var(--g-hoehe); padding-top: 6px; padding-bottom: 6px; box-sizing: border-box; }
/* ?-Hilfesymbole: Trefferflaeche 48 px ohne das Layout zu verschieben (Padding + negativer Rand) */
@media (pointer: coarse) {
    /* nur nach links/oben/unten erweitert: rechts am Rand wuerde es sonst seitlich ueberstehen */
    html body button[aria-label^="Help for"] { padding: 16px 0 16px 32px !important; margin: -16px 0 -16px -32px !important;
        box-sizing: content-box; }
}

/* ---- HTML-Ranglisten (.pt): Glas statt Schwarz ---- */
html body .pt, html body .pt tbody td { background-color: rgba(255, 255, 255, 0.02) !important; }
html body .pt thead th { background-color: #121829 !important; }      /* deckend: Kopf bleibt beim Scrollen stehen */
html body .pt tbody td.ue-fix { background-color: #0D1220 !important; }  /* fixierte Namensspalte deckend */
html body :is(.pt-wrap, .pt-scroll, .ks-wrap) { border-radius: 16px; }

/* ---- Kursstand-Pille im Menue: Live-Anzeige als leuchtender, pulsierender Balken ueber dem Text ---- */
html body .nav-chip { flex-direction: column; gap: 8px; padding: 10px 18px 9px; border-radius: 20px; text-align: center; }
html body .nav-chip .nav-dot { width: 44px; height: 6px; border-radius: 999px; flex: 0 0 auto;
    background: linear-gradient(90deg, rgba(52, 211, 153, 0.35), #34D399 50%, rgba(52, 211, 153, 0.35));
    background-size: 200% 100%; box-shadow: 0 0 10px rgba(52, 211, 153, 0.75), 0 0 22px rgba(52, 211, 153, 0.35);
    animation: navlive 2.4s ease-in-out infinite !important; }
@keyframes navlive {
    0%, 100% { opacity: 1; background-position: 0% 0; box-shadow: 0 0 10px rgba(52, 211, 153, 0.75), 0 0 22px rgba(52, 211, 153, 0.35); }
    50% { opacity: 0.45; background-position: 100% 0; box-shadow: 0 0 4px rgba(52, 211, 153, 0.35), 0 0 8px rgba(52, 211, 153, 0.15); }
}
@media (prefers-reduced-motion: reduce) { html body .nav-chip .nav-dot { animation: none !important; } }

/* ---- Zahlen: tabellarische Ziffern ueberall, Kennzahlen in Mono ---- */
.stApp { font-variant-numeric: tabular-nums; }
html body :is(.kz-w, .kz .w, .gv, .depot-wert, .hero-wert, .pb-kpis .w, .pb-grid .w, .pt td.r, .row-val) {
    font-variant-numeric: tabular-nums; }
/* Restliche Rahmen (umrandete Container, Tabellen, Kopfleiste) mit derselben klaren Randfarbe */
html body :is([data-testid="stVerticalBlockBorderWrapper"], [data-testid="stLayoutWrapper"]) > [data-testid="stVerticalBlock"][style*="border"],
html body [data-testid="stElementContainer"]:has([data-testid="stDataFrame"], [data-testid="stTable"]) {
    border: 1px solid var(--rand) !important; border-radius: 14px; box-shadow: var(--rand-glow); overflow: hidden;
}
/* Klappbereich: nur EIN Rand (am inneren details) - der aeussere Rahmen entfaellt */
html body [data-testid="stExpander"][data-testid="stExpander"] { border: none !important; box-shadow: none !important; background: transparent !important; }
html body [data-testid="stExpander"] summary { border-radius: 19px !important; }
html body [data-testid="stExpander"] summary:hover, html body [data-testid="stExpander"] summary:hover p {
    background-color: transparent !important; }

/* ================= SCHRITTE: Schritt-fuer-Schritt-Fuehrung (schritte.py) =================
   Oben eine Leiste mit nummerierten Glas-Kapseln, an den Abschnitten eine leuchtende Nummer mit Hinweis. */
.sf-leiste { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; margin: 2px 0 14px; }
.sf-leiste .sf-kopf { flex: 0 0 auto; font-size: 0.72rem; font-weight: 700; letter-spacing: 1.2px;
    text-transform: uppercase; color: var(--label); margin-right: 4px; }
.sf-leiste a.sf-s, .sf-leiste a.sf-s:visited { display: inline-flex; align-items: center; gap: 8px; min-height: 36px;
    padding: 3px 14px 3px 4px; border-radius: 999px; text-decoration: none !important; color: var(--text) !important;
    background: var(--glas-bg); border: 1px solid var(--rand); box-shadow: var(--rand-glow);
    font-size: 0.85rem; font-weight: 600; white-space: nowrap; transition: box-shadow .2s ease, transform .15s ease; }
.sf-leiste span.sf-s { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; padding: 3px 14px 3px 4px;
    border-radius: 999px; border: 1px dashed var(--rand); color: var(--label); font-size: 0.85rem; font-weight: 600;
    white-space: nowrap; opacity: 0.7; }
.sf-leiste span.sf-s b { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px;
    border-radius: 50%; font-weight: 800; font-size: 0.85rem; border: 1px solid var(--rand); color: var(--label); }
.sf-leiste a.sf-s:hover { box-shadow: 0 0 16px var(--glas-glow-stark); transform: translateY(-1px); }
.sf-leiste a.sf-s b, .sf-nr { display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 50%; flex: 0 0 auto; font-weight: 800; font-size: 0.85rem;
    color: var(--sf-nr-text, #0B1020); background: linear-gradient(135deg, var(--accent), var(--accent-2));
    box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.45), 0 0 12px rgba(124, 156, 255, 0.55); }
/* Rechner-Karten (Zins/Abfindung): Nummer in Groesse des frueheren Symbols */
.zr-kopf .sf-nr.sf-klein { width: 34px; height: 34px; font-size: 1rem; margin: 0; flex: 0 0 34px; scroll-margin-top: 90px; }
/* kleine Nummer in vorhandenen Abschnittsueberschriften */
.sf-nr.sf-klein { width: 22px; height: 22px; font-size: 0.72rem; margin-right: 8px; vertical-align: 1px;
    letter-spacing: 0; text-shadow: none; scroll-margin-top: 90px; }
.sf-titel { display: flex; align-items: flex-start; gap: 12px; margin: 10px 0 8px; scroll-margin-top: 90px; }
.sf-titel .sf-nr { width: 32px; height: 32px; font-size: 0.95rem; margin-top: 1px; }
.sf-titel .sf-name { font-size: 1.02rem; font-weight: 700; color: var(--text); line-height: 1.3; }
.sf-titel .sf-was { font-size: 0.84rem; color: var(--label); line-height: 1.35; margin-top: 2px; }
/* Handy: Leiste als waagerecht wischbare Reihe statt mehrerer Zeilen */
@media (max-width: 640px) {
    .sf-leiste { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; padding: 4px 2px 6px;
                 margin-left: -2px; margin-right: -2px; scroll-snap-type: x proximity; }
    .sf-leiste::-webkit-scrollbar { display: none; }
    .sf-leiste .sf-kopf { display: none; }
    .sf-leiste a.sf-s { scroll-snap-align: start; }
}
html body .st-key-nav_leiste { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 10px 24px rgba(11, 11, 11, 0.45), var(--rand-glow); }
</style>
"""

CSS_RESPONSIV = """
<style>
    /* ================= RESPONSIV (UX 10/2026) =================
       Umbruchpunkte: S < 600 | M 600-899 | L 900-1199 | XL >= 1200 */

    /* --- Spalten mit nur einem Knopf (z. B. "🗑️ Entfernen" neben einem Namen, "➕ Hinzufügen" neben einer
       Auswahl): die App verhindert Spaltenumbrueche global (min-width: 0) - am Handy wurden solche Knoepfe
       auf 35 px Breite gequetscht und der Text stand Buchstabe fuer Buchstabe untereinander. Jetzt bekommt
       der Knopf seine Textbreite, der Rest der Zeile teilt sich den uebrigen Platz; passt beides nicht,
       bricht die Zeile um. Menue und Kopfleiste haben ihr eigenes Raster und sind ausgenommen. */
    @media (max-width: 599px) {
        /* (:has() darf nicht verschachtelt werden - deshalb Geschwister-Selektoren statt "Zeile hat ...") */
        /* Knopf-Spalte hinter Text/Feld: Textbreite; die Spalte davor schrumpft (kein Umbruch der Zeile).
           Reine Knopf-Reihen (z. B. zwei Knoepfe nebeneinander) behalten ihr gleichmaessiges Raster. */
        [data-testid="stMain"] [data-testid="stHorizontalBlock"]:not(.st-key-nav_menue [data-testid="stHorizontalBlock"]):not(.st-key-nav_leiste [data-testid="stHorizontalBlock"]) > [data-testid="stColumn"]:not(:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child [data-testid="stButton"])) ~ [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child [data-testid="stButton"]) {
            flex: 0 0 auto !important; width: auto !important; min-width: max-content !important; max-width: 100% !important; }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"]:not(.st-key-nav_menue [data-testid="stHorizontalBlock"]):not(.st-key-nav_leiste [data-testid="stHorizontalBlock"]) > [data-testid="stColumn"]:not(:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child [data-testid="stButton"])) ~ [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child [data-testid="stButton"]) button { white-space: nowrap; }
        /* Zeilen mit Knopf, aber ohne Eingabefeld bleiben einzeilig - die Textspalte schrumpft */
        [data-testid="stMain"] [data-testid="stHorizontalBlock"]:not(.st-key-nav_menue [data-testid="stHorizontalBlock"]):not(.st-key-nav_leiste [data-testid="stHorizontalBlock"]):has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child [data-testid="stButton"]):not(:has(> [data-testid="stColumn"] :is([data-testid="stSelectbox"], [data-testid="stTextInput"], [data-testid="stNumberInput"], [data-testid="stMultiSelect"]))) { flex-wrap: nowrap !important; }
        /* Eingabefeld + Knopf (z. B. Auswahl + "➕ Hinzufügen"): untereinander, beide volle Breite - nebeneinander
           blieben fuer das Feld bei 320 px nur ~120 px */
        [data-testid="stMain"] [data-testid="stHorizontalBlock"]:not(.st-key-nav_menue [data-testid="stHorizontalBlock"]):not(.st-key-nav_leiste [data-testid="stHorizontalBlock"]):has(> [data-testid="stColumn"] :is([data-testid="stSelectbox"], [data-testid="stTextInput"], [data-testid="stNumberInput"], [data-testid="stMultiSelect"])):has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child [data-testid="stButton"]) { flex-wrap: wrap !important; }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"]:not(.st-key-nav_menue [data-testid="stHorizontalBlock"]):not(.st-key-nav_leiste [data-testid="stHorizontalBlock"]):has(> [data-testid="stColumn"] :is([data-testid="stSelectbox"], [data-testid="stTextInput"], [data-testid="stNumberInput"], [data-testid="stMultiSelect"])):has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child [data-testid="stButton"]) > [data-testid="stColumn"][data-testid="stColumn"] {
            flex: 1 1 100% !important; width: 100% !important; min-width: 100% !important; }
    }

    /* --- Touch: "Kurse aktualisieren" auf der Startseite mind. 44 px (gemessen: 34 px auf iPad/quer) */
    @media (pointer: coarse) {
        html body .st-key-nav_menue .st-key-nav_refresh button { min-height: 44px !important; }
        /* "?" an Beschriftungen ohne Feld (st.caption(help=...)) - gleiche 44-px-Flaeche wie an Feldern */
        button[aria-label="Help"] { position: relative; }
        button[aria-label="Help"]::before { content: ""; position: absolute; inset: -14px -14px; }
        /* Mehrfachauswahl: das "x" zum Entfernen eines gewaehlten Werts war 16 x 8 px */
        [data-testid="stMultiSelect"] [data-baseweb="tag"] { min-height: 32px; }
        [data-testid="stMultiSelect"] [data-baseweb="tag"] [role="presentation"],
        [data-testid="stMultiSelect"] [data-baseweb="tag"] span[aria-label^="Remove"],
        [data-testid="stMultiSelect"] [data-baseweb="tag"] svg { min-width: 24px; min-height: 24px; }
        /* Code-Feld "Kopieren" (Zinsrechner) */
        [data-testid="stCode"] button { min-width: 44px !important; min-height: 44px !important; }
    }

    /* --- Grosse Monitore: Inhalt hoechstens INHALT_MAX breit, zentriert (vorher 2.464 px breite Charts und
       Kennzahlen, die weit auseinanderlagen). Ansichten mit breiten Tabellen heben die Grenze an (app.py). */
    [data-testid="stMainBlockContainer"] { max-width: 1440px !important; margin-left: auto !important;
                                           margin-right: auto !important; }

    /* --- Unsichtbare Bausteine (reine <style>-Bloecke, 0-px-Skript-Rahmen) belegten je einen Block-Abstand:
       oben in jeder Ansicht ~45 px Leerraum (am Handy quer ein Achtel der Hoehe). Abstand zuruecknehmen. */
    [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:first-child:last-child),
    [data-testid="stElementContainer"]:has(> iframe[height="0"]) { margin-bottom: -0.7rem; }

    /* --- Knopf-Paare (z. B. Scanner 2.0 "Kurse laden" | "Kaufplan (CSV)"): gleich hoch, auch wenn einer umbricht */
    .st-key-is2_aktionen [data-testid="stHorizontalBlock"] { align-items: stretch !important; }
    .st-key-is2_aktionen [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
    .st-key-is2_aktionen [data-testid="stElementContainer"],
    .st-key-is2_aktionen :is([data-testid="stButton"], [data-testid="stDownloadButton"]),
    .st-key-is2_aktionen :is([data-testid="stButton"], [data-testid="stDownloadButton"]) > div,
    .st-key-is2_aktionen button { height: 100% !important; }

    /* --- Seitentitel doppelt: Builder, Scanner, Depot-Analyse, Analyse-Depot wiederholten den Namen der Ansicht
       direkt unter der Kopfleiste (dort steht er schon) - nur die Unterzeile bleibt */
    .pb-kopf .pb-titel { display: none; }
    .pb-kopf { margin-top: 0 !important; }

    /* --- DEPOT-KACHELN: Wert, Gewinn/Verlust, Kennzahl-Kacheln, weitere Zeitraeume (app.depot_kachel_html) --- */
    .hero, .quote { container-type: inline-size; }
    .gv { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin-top: 6px;
          font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
    .gv .gv-eur { font-size: 1.05rem; font-weight: 700; }
    .gv .gv-pct { font-size: 0.98rem; font-weight: 700; }
    .gv .gv-text { font-family: 'Inter', -apple-system, sans-serif; font-size: 0.82rem; font-weight: 500;
                   color: var(--label); }
    .gv.up .gv-eur, .gv.up .gv-pct, .gv.up .gv-pfeil { color: var(--up); }
    .gv.down .gv-eur, .gv.down .gv-pct, .gv.down .gv-pfeil { color: var(--down); }
    .gv.flat .gv-eur, .gv.flat .gv-pct, .gv.flat .gv-pfeil { color: var(--label); }
    .kz-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    @container (min-width: 520px) { .kz-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    .kz { border: 1px solid var(--rand); border-radius: 12px; padding: 8px 10px; min-width: 0;
          background: rgba(255, 255, 255, 0.025); }
    .kz-l { font-size: 0.78rem; font-weight: 700; color: var(--label); text-transform: uppercase; letter-spacing: 0.5px; }
    .kz-e, .kz-p { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
                   font-weight: 700; white-space: nowrap; }
    /* Betrag waechst/schrumpft mit der Kachelbreite (bei 320 px wurde "+12.066,50 €" abgeschnitten); reicht es
       trotzdem nicht, bricht er hinter dem Pfeil um statt abgeschnitten zu werden */
    .kz-e { font-size: clamp(0.78rem, 4.6cqi, 0.92rem); margin-top: 2px; white-space: normal; }
    .kz-e .kz-n { white-space: nowrap; }
    .kz-p { font-size: 0.85rem; opacity: 0.92; }
    .kz.up .kz-e, .kz.up .kz-p { color: var(--up); }
    .kz.down .kz-e, .kz.down .kz-p { color: var(--down); }
    .kz.flat .kz-e, .kz.flat .kz-p { color: var(--label); }
    details.mehr { margin-top: 10px; }
    details.mehr > summary { cursor: pointer; list-style: none; font-size: 0.85rem; font-weight: 600;
                             color: var(--label); padding: 10px 2px; min-height: 44px; box-sizing: border-box;
                             display: flex; align-items: center; gap: 8px; }
    details.mehr > summary::-webkit-details-marker { display: none; }
    details.mehr > summary::before { content: "▸"; transition: transform .15s ease; }
    details.mehr[open] > summary::before { transform: rotate(90deg); }
    details.mehr .perf-table { margin-top: 0; }
    .abschnitt.klein { font-size: 0.76rem; opacity: 0.85; margin-top: 10px !important; }
    .hero.kurz { margin-bottom: 8px; }
    .kurz-stand { font-weight: 500; letter-spacing: 0.3px; text-transform: none; color: var(--label); margin-left: 6px; }

    /* --- Titel in der Kopfleiste: ganze Woerter, nie "Vermögensaufba / u" (Umbruch mitten im Wort bei 320 px) */
    .nav-titel { overflow-wrap: normal !important; word-break: normal !important; hyphens: auto; }
    @media (max-width: 380px) { .nav-titel { font-size: 0.84rem !important; letter-spacing: 0 !important; } }
</style>
"""


# ------------------------------------------------------------------ Charts (eine Vorlage fuer alle)
CHART_RASTER = "rgba(255, 255, 255, 0.06)"      # dezente Gitterlinien (Premium Glass)
CHART_SCHRIFT = "#A9B1C4"
CHART_FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
AKZENT = "#7C9CFF"                                # Hauptlinie; zweiter Akzent #5EEAD4
CHART_FARBEN = ["#7C9CFF", "#5EEAD4", "#A78BFA", "#F5B942", "#F472B6", "#60A5FA", "#94A3B8"]


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+\\s*")


def ohne_emoji(text):
    """Ueberschriften ohne Emojis (Premium-Design): '🏠 Test-Depot' -> 'Test-Depot'."""
    return _EMOJI.sub("", str(text or "")).strip()


def ist_smartphone():
    """True auf Smartphones (User-Agent; iPad meldet sich als Mac und gilt als Desktop)."""
    try:
        import streamlit as st
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:
        return False
    return "iphone" in ua or ("android" in ua and "mobile" in ua) or "ipod" in ua


def _flaeche_unter(fig, name):
    """Hauptlinie (Trace mit diesem Namen): Akzentfarbe mit weichem Verlauf darunter. Die y-Achse wird auf den
    Datenbereich gesetzt, damit die Flaeche bis 0 die Kurve nicht plattdrueckt."""
    werte = []
    for tr in fig.data:
        if getattr(tr, "y", None) is not None and getattr(tr, "type", "") == "scatter" and tr.visible is not False:
            werte += [float(v) for v in tr.y if v is not None and v == v]
    for tr in fig.data:
        if getattr(tr, "name", None) == name and getattr(tr, "type", "") == "scatter":
            tr.update(line=dict(color=AKZENT, width=2.5), fill="tozeroy",
                      fillgradient=dict(type="vertical", colorscale=[[0, "rgba(124,156,255,0)"],
                                                                     [1, "rgba(124,156,255,0.28)"]]))
            break
    else:
        return
    if werte and fig.layout.yaxis.range is None:
        lo, hi = min(werte), max(werte)
        rand = (hi - lo) * 0.06 or abs(hi) * 0.05 or 1
        fig.update_yaxes(range=[lo - rand, hi + rand])


def tabellen_spalten(df, fortschritt=(), maximum=100):
    """column_config fuer st.dataframe: Zahlen im Gebietsschema des Browsers (de: 1.234,56), Spalten mit
    "€"/"%" im Namen als Zahl, fortschritt = Spalten (0..maximum) als Fortschrittsbalken. -> dict"""
    import pandas as pd
    import streamlit as st
    cfg = {}
    for spalte in df.columns:
        name = str(spalte)
        if not pd.api.types.is_numeric_dtype(df[spalte]):
            continue
        if name in fortschritt:
            cfg[name] = st.column_config.ProgressColumn(name, min_value=0, max_value=maximum, format="%.0f")
        else:
            cfg[name] = st.column_config.NumberColumn(name, format="localized")
    return cfg


HANDY_MAX_PUNKTE = 400     # mehr Punkte je Linie kann ein Handy-Bildschirm (~390 px breit) nicht darstellen


def ausduennen(fig, max_punkte=HANDY_MAX_PUNKTE):
    """Linien mit sehr vielen Punkten fuer das Handy ausduennen (jeder k-te Punkt, erster und letzter bleiben):
    weniger Daten zum Geraet, schnellerer Aufbau und fluessigeres Wischen. Kerzen (OHLC), Balken und kurze
    Linien bleiben unveraendert; Spuren gleicher Laenge werden gleich ausgeduennt (Flaechen passen weiter)."""
    for spur in fig.data:
        if getattr(spur, "type", "") not in ("scatter", "scattergl") or spur.x is None or spur.y is None:
            continue
        n = len(spur.x)
        if n <= max_punkte or len(spur.y) != n:
            continue
        schritt = -(-n // max_punkte)
        idx = list(range(0, n, schritt))
        if idx[-1] != n - 1:
            idx.append(n - 1)
        werte = {"x": spur.x, "y": spur.y}
        for feld in ("customdata", "text", "hovertext"):
            w = getattr(spur, feld, None)
            if w is not None and not isinstance(w, str) and len(w) == n:
                werte[feld] = w
        spur.update({k: [v[i] for i in idx] for k, v in werte.items()})
    return fig


def chart_stil(fig, schrumpfen=True, flaeche=None):
    """Gemeinsame Plotly-Vorlage (Premium Glass): Hintergrund durchsichtig, dezentes Raster, Schrift Inter,
    deutsche Zahlen, Tooltips im dunklen Glas-Look, Farbfolge mit Akzent #7c9cff; flaeche = Name der
    Hauptlinie (Akzent + Verlauf). Am Handy: niedriger (70 %, mind. 260 px - ausser bei Legenden unter dem
    Chart), kleinere Achsenschrift, weniger Achsenbeschriftungen und schmalere Raender. -> fig"""
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", separators=",.",
                      font=dict(color=CHART_SCHRIFT, family=CHART_FONT), colorway=CHART_FARBEN,
                      hoverlabel=dict(bgcolor="rgba(13,18,32,0.92)", bordercolor="rgba(255,255,255,0.14)",
                                      font=dict(family=CHART_FONT, color="#E8ECF6", size=13)))
    fig.update_xaxes(gridcolor=CHART_RASTER, zerolinecolor=CHART_RASTER)
    fig.update_yaxes(gridcolor=CHART_RASTER, zerolinecolor=CHART_RASTER)
    if flaeche:
        _flaeche_unter(fig, flaeche)
    if not ist_smartphone():
        return fig
    ausduennen(fig)
    lay = fig.layout
    legende_unten = lay.showlegend is not False and len(fig.data) > 1
    if schrumpfen and lay.height and not legende_unten:
        fig.update_layout(height=max(260, round(lay.height * 0.7)))
    m = lay.margin
    hat_titel = bool(lay.title and lay.title.text)
    fig.update_layout(font=dict(size=11), margin=dict(
        l=min(m.l if m.l is not None else 10, 6), r=min(m.r if m.r is not None else 10, 46),
        t=(m.t if hat_titel or m.t is None else min(m.t, 24)), b=min(m.b if m.b is not None else 40, 36)))
    fig.update_xaxes(tickfont=dict(size=10), nticks=5)
    fig.update_yaxes(tickfont=dict(size=10), nticks=6)
    return fig



# ---------- BOERSEN-BULLE UND -BAER (Silber, laufend) ----------
# Eigene SVG-Figuren statt Emojis: seitlich nach rechts laufend, Beine einzeln animiert (CSS-Klasse
# "tb-bein", vorderes und hinteres Paar gegenlaeufig). Nur doppelte Anfuehrungszeichen - das Markup
# wird auch in das Lade-Skript (JavaScript in einfachen Anfuehrungszeichen) eingesetzt.
_SILBER = ('<linearGradient id="tb-silber" x1="0" y1="0" x2="0" y2="1">'
           '<stop offset="0" stop-color="#FBFCFD"/><stop offset=".42" stop-color="#C9CED6"/>'
           '<stop offset=".58" stop-color="#8E949E"/><stop offset="1" stop-color="#E4E7EC"/></linearGradient>')
_RAND = 'stroke="#5B6270" stroke-width="0.9" stroke-linejoin="round"'


def _bein(x, y, art, hinten, baer, fern):
    """Ein Bein mit Gelenk (Pivot oben bei x, y). hinten: Sprunggelenk nach hinten geknickt;
    baer: kraeftig mit Tatze, sonst schlank mit Huf. fern: Bein auf der abgewandten Seite (dunkler)."""
    t = y - 9                      # Oberschenkel setzt im Rumpf an - beim Schwingen keine Luecke
    if baer:
        d = (f"M{x - 6} {t} C{x - 7} {t + 12} {x - 5} {t + 21} {x - 5} {t + 25} "
             f"C{x - 5} {t + 29.5} {x + 7} {t + 29.5} {x + 7.5} {t + 27} "
             f"C{x + 4.5} {t + 25} {x + 4.5} {t + 18} {x + 5.5} {t} Z")
        fuss = (f'<path d="M{x + 1} {t + 27.6} l1.2 1.4 M{x + 3.4} {t + 27.4} l1.2 1.4 M{x + 5.6} {t + 27} l1 1.3" '
                f'stroke="#3A3F48" stroke-width=".8"/>')
    elif hinten:
        d = (f"M{x - 6} {t} C{x - 7} {t + 8} {x - 1} {t + 18} {x - 3.8} {t + 24} "
             f"L{x - 1.5} {t + 35} L{x + 2.2} {t + 35} L{x + 1.2} {t + 24} "
             f"C{x + 4.5} {t + 17} {x + 6} {t + 8} {x + 5.5} {t} Z")
        fuss = f'<path d="M{x - 2} {t + 34.5} h4.6 l.7 2.8 h-5.8z" fill="#3A3F48"/>'
    else:
        d = (f"M{x - 5.5} {t} C{x - 6} {t + 9} {x - 3} {t + 17} {x - 2.4} {t + 24} "
             f"L{x - 2.2} {t + 35} L{x + 2} {t + 35} L{x + 2} {t + 24} "
             f"C{x + 3} {t + 16} {x + 5.5} {t + 9} {x + 5.5} {t} Z")
        fuss = f'<path d="M{x - 2.6} {t + 34.5} h4.8 l.7 2.8 h-6z" fill="#3A3F48"/>'
    stil = ' opacity=".72"' if fern else ""
    return f'<g class="tb-bein {art}"{stil}><path d="{d}" fill="url(#tb-silber)" {_RAND}/>{fuss}</g>'


def _beinpaar(vorne, hinten_, baer, fern):
    """Vorder- und Hinterbein einer Seite; diagonal gegenlaeufig (nah: vorne a/hinten b, fern umgekehrt)."""
    a, b = ("b", "a") if fern else ("a", "b")
    return _bein(*vorne, a, False, baer, fern) + _bein(*hinten_, b, True, baer, fern)


def tier_svg(art, breite=52):
    """Silberner Boersen-Bulle ("bulle") oder -Baer ("baer") als SVG, seitlich nach rechts laufend."""
    if art == "bulle":
        koerper = (
            _beinpaar((76, 48), (32, 46), False, True) + _beinpaar((84, 47), (24, 44), False, False)
            # Schwanz erhoben, mit Quaste
            + '<path d="M15 31 C7 28 3 20 6 11" fill="none" stroke="#8E949E" stroke-width="2.4" stroke-linecap="round"/>'
            + '<path d="M6 12 C2 9 3 4 8 5 C7 8 9 10 6 12z" fill="#8E949E"/>'
            # Rumpf: kraeftiger Schulterbuckel, gesenkter Kopf, Wamme
            + '<path d="M14 30 C18 22 34 20 50 21 C60 16 72 9 84 13 C90 15 94 21 97 27 L104 33 '
              'C108 37 110 43 106 47.5 C103 50 99 49 96 46 C92 44 88 46 86 50 C84 54 80 55 76 53 '
              'C66 52 54 50.5 44 50.5 C34 51 24 50 18 46 C13 42 11 36 14 30 Z" '
              f'fill="url(#tb-silber)" {_RAND}/>'
            # Muskeln / Fellkanten
            # Hoerner nach vorn geschwungen
            + f'<path d="M94 27 C95 19 100 14 107 14 C102 17 99 21 98 28 Z" fill="#E9EBEF" {_RAND}/>'
            + f'<path d="M98 29 C100 21 106 17 114 18 C109 20 105 25 103 32 Z" fill="#F4F5F7" {_RAND}/>'
            # Ohr, Auge, Nuestern
            + f'<path d="M93 30 C89 27 85 29 84 33 C88 33.5 91 32.5 93 31 Z" fill="url(#tb-silber)" {_RAND}/>'
            + '<ellipse cx="100.5" cy="36" rx="1.4" ry="1.1" fill="#22262C"/>'
            + '<ellipse cx="106.3" cy="45" rx="1.3" ry=".9" fill="#22262C"/>'
        )
        vb = (0, 2, 118, 77)
    else:
        koerper = (
            _beinpaar((70, 45), (30, 45), True, True) + _beinpaar((80, 43), (22, 42), True, False)
            # Rumpf: Grizzly mit Schulterbuckel, langer Schnauze
            + '<path d="M12 34 C12 26 20 22 30 22 C40 20 50 22 58 18 C66 12.5 76 13.5 82 20 C86 23 89 25 92 26 '
              'C96 24 101 25 104 28 C107 30 111 31 113.5 33 C115.5 35 114.5 38.5 111 38.5 C106 39 101 38 97 39.5 '
              'C93 41 90 43 86 44.5 C82 47 76 49 70 48 C58 49 44 49 34 48 C24 48 14 44 12 34 Z" '
              f'fill="url(#tb-silber)" {_RAND}/>'
            # Fell: Buckel und Flanke
            + '<path d="M60 19 C65 16 71 16 76 19" fill="none" stroke="#7A808A" stroke-width=".9" opacity=".7"/>'
            + '<path d="M12 31 C8.5 30 8 27.5 10.5 26.5" fill="none" stroke="#8E949E" stroke-width="2" stroke-linecap="round"/>'
            # Ohr, Auge, Nase, Maul
            + f'<path d="M92.5 26 C91 20.5 95.5 18.5 98.5 22 C97.5 24.5 95 25.5 92.5 26 Z" fill="url(#tb-silber)" {_RAND}/>'
            + '<ellipse cx="101.5" cy="30.5" rx="1.3" ry="1.1" fill="#22262C"/>'
            + '<ellipse cx="112.6" cy="34.6" rx="1.8" ry="1.4" fill="#22262C"/>'
            + '<path d="M104 38.3 C107 37.6 109 37.8 111 38.3" fill="none" stroke="#5B6270" stroke-width=".8"/>'
        )
        vb = (0, 8, 118, 64)
    hoch = round(breite * vb[3] / vb[2], 1)
    return (f'<svg class="tb-tier tb-{art}" viewBox="{" ".join(map(str, vb))}" width="{breite}" height="{hoch}" '
            f'xmlns="http://www.w3.org/2000/svg"><defs>{_SILBER}</defs>{koerper}</svg>')


# Laufbewegung: Beine schwingen um die Huefte, der Koerper wippt
TIER_CSS = (".tb-tier { display:block; overflow:visible; filter:drop-shadow(0 1px 1.5px rgba(0,0,0,.45)); "
            "animation:tbwipp .3s ease-in-out infinite alternate; }"
            " .tb-bein { transform-box:fill-box; transform-origin:50% 12%; animation:tbbein .3s ease-in-out infinite alternate; }"
            " .tb-bein.b { animation-delay:-.3s; }"
            " .tb-baer, .tb-baer .tb-bein { animation-duration:.26s; }"
            " .tb-baer .tb-bein.b { animation-delay:-.26s; }"
            " @keyframes tbbein { from { transform:rotate(24deg); } to { transform:rotate(-24deg); } }"
            " @keyframes tbwipp { from { translate:0 0; } to { translate:0 -2.5px; } }")


# ---------- KURS-LADEBALKEN (fuer Fortschritt im Seiteninhalt, z. B. Kurs-Aktualisierung) ----------
# Gleiche Optik wie das Lade-Banner oben (app.py, _LADE_JS): Kurslinie waechst mit dem Fortschritt,
# vorne laeuft der silberne Bulle, dahinter der Baer; die Prozentzahl steht gross daneben.
LADE_KURS_CSS = """<style>
.kl-box { margin: 6px 0 12px; }
.kl-kopf { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.kl-kopf > span:first-child { flex:0 0 auto; white-space:nowrap; }
.kl-pct { font-family:'JetBrains Mono', ui-monospace, monospace; font-variant-numeric:tabular-nums;
          font-size:1.25rem; font-weight:700; color:var(--text); }
.kl-pfeil { color:var(--up); font-size:.9rem; margin-right:4px; }
.kl-text { font-size:.88rem; font-weight:600; color:var(--muted); white-space:nowrap; overflow:hidden;
           text-overflow:ellipsis; min-width:0; }
.kl-chart { position:relative; height:44px; margin-top:4px; }
.kl-chart > svg { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
.kl-spur { stroke:var(--line); stroke-width:1; stroke-dasharray:3 3; vector-effect:non-scaling-stroke; }
.kl-linie { fill:none; stroke:var(--up); stroke-width:2.2; stroke-linejoin:round; vector-effect:non-scaling-stroke; }
.kl-tier { position:absolute; line-height:0; transform:translate(-62%,-92%); }
/* Endgeraet: am Handy kleinere Tiere, am Laptop/Desktop hoeherer Chart und groessere Tiere */
@media (max-width: 699px) { .kl-chart { height:40px; } .kl-tier svg { width:44px; height:auto; } .kl-baer svg { width:40px; } }
@media (min-width: 900px) { .kl-chart { height:58px; } .kl-tier svg { width:70px; height:auto; } .kl-baer svg { width:64px; } }
</style>"""


def _kurs_punkte(saat, n=60):
    """Zufaelliger Kursverlauf mit Aufwaertstrend, auf 0,04..0,76 gestreckt (oben Platz fuer die Tiere) (fester Startwert = ruhiges Bild)."""
    import random
    zufall = random.Random(saat)
    v, werte = 0.12, []
    for _ in range(n + 1):
        v = max(0.03, min(0.97, v + 0.013 + (zufall.random() - 0.5) * 0.09))
        werte.append(v)
    lo, hi = min(werte), max(werte)
    sp = max(hi - lo, 0.2)
    return [0.04 + (w - lo) / sp * 0.72 for w in werte]


_KL_NR = 0


def lade_balken_html(pct, text="", saat=7):
    """Ladebalken als kleiner Aktienchart mit Prozentangabe, Bulle vorne und Baer dahinter."""
    import html as _html
    p = max(0.0, min(100.0, float(pct)))
    k = _kurs_punkte(saat)
    n = len(k) - 1
    pts = " ".join(f"{i * 100 / n:.2f},{28 - w * 25:.2f}" for i, w in enumerate(k))

    def hoehe(x):
        x = max(0.0, min(100.0, x)) * n / 100
        i = int(x)
        w = k[i] + (k[min(i + 1, n)] - k[i]) * (x - i)
        return (28 - w * 25) / 30 * 100

    pb = max(p - 15, 0.0)
    global _KL_NR
    _KL_NR += 1
    gid = f"kl{saat}_{_KL_NR}"        # eindeutige SVG-IDs (sonst gilt die erste clipPath fuer alle Balken)
    baer = (f'<span class="kl-tier kl-baer" style="left:{pb:.1f}%;top:{hoehe(pb):.1f}%">{tier_svg("baer", 50)}</span>'
            if p > 4 else "")
    return (LADE_KURS_CSS.replace("</style>", TIER_CSS + "</style>") + f'<div class="kl-box"><div class="kl-kopf"><span><span class="kl-pfeil">▲</span>'
            f'<span class="kl-pct">{int(p)} %</span></span><span class="kl-text">{_html.escape(text)}</span></div>'
            f'<div class="kl-chart"><svg viewBox="0 0 100 30" preserveAspectRatio="none">'
            f'<defs><linearGradient id="{gid}v" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#34D399" '
            f'stop-opacity=".35"/><stop offset="1" stop-color="#34D399" stop-opacity="0"/></linearGradient>'
            f'<clipPath id="{gid}c"><rect x="0" y="-10" width="{p:.2f}" height="50"/></clipPath></defs>'
            f'<line class="kl-spur" x1="0" y1="29" x2="100" y2="29"/><g clip-path="url(#{gid}c)">'
            f'<path d="M0,29 L{pts.replace(" ", " L")} L100,29 Z" fill="url(#{gid}v)"/>'
            f'<polyline class="kl-linie" points="{pts}"/></g></svg>{baer}'
            f'<span class="kl-tier kl-bulle" style="left:{p:.1f}%;top:{hoehe(p):.1f}%">{tier_svg("bulle", 54)}</span>'
            '</div></div>')
