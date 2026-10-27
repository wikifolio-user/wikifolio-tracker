"""Zentrale Styles der App (UX 10/2026) - alles CSS an EINER Stelle.

- CSS_BASIS: Design-System (Farben, Schrift, Kacheln, Tabellen, Formulare) - frueher in app.py
- CSS_NAV: Startseite, Menue-Kacheln, Kopfleiste - frueher NAV_CSS in app.py
- CSS_RESPONSIV: Umbruchpunkte und Layout-Regeln fuer alle Bildschirmbreiten (siehe unten)

Umbruchpunkte (einheitlich):  S < 600 px (Handy)  |  M 600-899 (Handy quer, Tablet hoch)
                             L 900-1199 (Tablet quer, kleines Fenster)  |  XL >= 1200 (Desktop)
Inhalt ist auf grossen Monitoren auf INHALT_MAX px begrenzt (zentriert); breite Tabellen duerfen
ueber .ui-breit die volle Breite nutzen.
"""

INHALT_MAX = 1440
INHALT_MAX_BREIT = 1920

CSS_BASIS = """
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
        --ink:     #0B0B0C;   /* Hintergrund - nicht reines Schwarz, Hauch Blau */
        --surface: #151617;   /* erhoehte Flaechen */
        --line:    #252628;   /* Haarlinien */
        --muted:   #83868C;   /* Sekundaertext, tertiaer (Fussnoten) */
        --label:   #B1B3B7;   /* Zeilen-Labels - deutlich besser lesbar als --muted */
        --text:    #EBECED;   /* Primaertext */
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
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
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
        background: rgba(22, 199, 132, 0.12); color: var(--up);
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.2px;
        padding: 4px 10px 4px 8px; border-radius: 999px;
    }
    .live-pill.offline { background: rgba(234, 57, 67, 0.12); color: var(--down); }
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
        background: var(--surface); border: 1px solid var(--rand);
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
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
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
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
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
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
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
        color: var(--label); font-weight: 600; font-size: 0.8rem;
        letter-spacing: 0.3px;
    }

    /* Zahlen in Tabellenziffern, damit Nachkommastellen untereinander stehen */
    .pt-num {
        text-align: right;
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
        font-size: 0.8rem;
    }
    .pt-stark { font-weight: 700; font-size: 0.83rem; }
    .pt-klein { font-size: 0.8rem; opacity: 0.92; }
    .pt-up { color: #16C784; }
    .pt-down { color: #EA3943; }
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
    .q-prio { color: #16C784; }
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
        font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
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
    .ks-plus { color: #16C784; }
    .ks-minus { color: #F5B942; }
    .ks-bahn { width: 140px; height: 8px; background: rgba(255, 255, 255, 0.08); border-radius: 4px;
               overflow: hidden; }
    .ks-bahn > div { height: 100%; background: #16C784; border-radius: 4px; }
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
        font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
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
        font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
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
            linear-gradient(var(--accent, #0A84FF), var(--accent, #0A84FF)) no-repeat 16px 46px / calc((100% - 32px) * var(--ladebreite) / 100%) 9px,
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
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
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
        height: 100%; background: var(--accent, #0A84FF); border-radius: 999px;
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
        outline: 2px solid #409CFF !important; outline-offset: 2px !important;
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
        /* Apple-Graphit (Liquid Glass, 10/2026): neutrale Grautoene, Systemblau nur fuer Auswahl/Hauptaktion */
        --ink: #111113; --surface: #1C1C1E; --surface-2: #232325; --line: #38383A;
        --muted: #8E8E93; --label: #AEAEB2; --text: #F5F5F7;
        --accent: #0A84FF; --accent-hell: #409CFF; --accent-soft: rgba(10, 132, 255, 0.16);
        --accent-rand: rgba(10, 132, 255, 0.55);
        --karte: linear-gradient(180deg, rgba(58, 58, 60, 0.52) 0%, rgba(28, 28, 30, 0.62) 100%);
        /* Raender: dunkel klar hell mit leichtem Leuchten, hell (ui_hell) klar dunkel */
        --rand: rgba(255, 255, 255, 0.55);
        --rand-glow: 0 0 10px rgba(255, 255, 255, 0.14);
    }
    .stApp {
        background:
            radial-gradient(1100px 620px at 88% -8%, rgba(255, 255, 255, 0.09), transparent 60%),
            radial-gradient(900px 640px at -12% 42%, rgba(255, 255, 255, 0.05), transparent 62%),
            radial-gradient(700px 500px at 60% 110%, rgba(255, 255, 255, 0.04), transparent 60%),
            var(--ink) !important;
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
    [data-testid="stAlertContentInfo"] { color: #409CFF !important; }
    [data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) > div {
        background: rgba(10, 132, 255, 0.1) !important; border: 1px solid rgba(10, 132, 255, 0.28) !important;
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
    font-family: 'Space Grotesk', -apple-system, sans-serif; font-size: 1.5rem; font-weight: 700;
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
.nav-dot { width: 7px; height: 7px; border-radius: 50%; background: #16C784;
           box-shadow: 0 0 8px #16C784; animation: navpuls 2.4s ease-in-out infinite; }
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
    font-size: 0.8rem; font-weight: 700; letter-spacing: 2.2px; text-transform: uppercase; color: #FFFFFF;
}
.nav-gruppe::after {
    content: ""; position: absolute; left: 0; right: 0; bottom: 7px; height: 1px;
    background: linear-gradient(90deg, rgba(64, 156, 255, 0.7), rgba(10, 132, 255, 0.1));
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
    background: linear-gradient(165deg, #28292B, #191A1B);
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
    color: var(--label, #9AA0A6); padding: 2px 12px; border: 1px solid rgba(64, 156, 255, 0.25); border-radius: 14px;
    max-width: 100%; box-sizing: border-box; text-align: center; }
.nav-stand span > i { margin-right: 6px; vertical-align: 1px; }
.nav-stand b { color: #FFFFFF; font-weight: 600; }
.nav-stand i { width: 6px; height: 6px; border-radius: 50%; background: #16C784; display: inline-block; }
@media (max-width: 700px) {
    .nav-logo { font-size: 1.22rem; letter-spacing: 3.5px; }
    .st-key-nav_menue [data-testid="stButton"] button { min-height: 58px !important; }
    .st-key-nav_menue .st-key-nav_refresh button { min-height: 44px !important; }
    .nav-titel { font-size: 0.92rem; }
    .st-key-nav_leiste [data-testid="stButton"] button { padding: 4px 9px !important; }
}

/* ================= GLAS: Apple "Liquid Glass" (10/2026) =================
   Klares Glas in Kapselform: leicht getoente, durchscheinende Flaeche mit Unschaerfe dahinter, eine feine
   Lichtkante (Verlaufsrand: oben links und unten rechts hell, dazwischen fast unsichtbar), innen oben ein
   weicher Lichtsaum, darunter ein zarter Schatten. Beim Darueberfahren leuchtet die Kante auf und ein weisser
   Glow umgibt das Glas. Systemblau nur fuer Auswahl und Hauptaktion. Alle Farben ueber Variablen - die helle
   Ansicht setzt nur andere Werte (ui_hell.WIDGETS). */
:root {
    --glas-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.11) 0%, rgba(255, 255, 255, 0.04) 55%, rgba(255, 255, 255, 0.07) 100%);
    --glas-rand-flach: rgba(255, 255, 255, 0.10);
    --glas-kante: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(255, 255, 255, 0.55) 30%,
                  rgba(255, 255, 255, 0.45) 60%, rgba(255, 255, 255, 0.85) 100%);
    --glas-licht: rgba(255, 255, 255, 0.22);
    --glas-tiefe: rgba(0, 0, 0, 0.28);
    --glas-schatten: 0 10px 28px rgba(0, 0, 0, 0.40), 0 2px 6px rgba(0, 0, 0, 0.25);
    --glas-glow: rgba(255, 255, 255, 0.14);
    --glas-glow-stark: rgba(255, 255, 255, 0.22);
    --glas-text: #F5F5F7;
    --glas-aktiv-bg: linear-gradient(180deg, rgba(10, 132, 255, 0.55) 0%, rgba(10, 132, 255, 0.32) 100%);
    --glas-aktiv-kante: linear-gradient(135deg, rgba(170, 210, 255, 0.95) 0%, rgba(10, 132, 255, 0.35) 45%, rgba(120, 185, 255, 0.85) 100%);
    --glas-aktiv-text: #FFFFFF;
    --glas-primaer-bg: linear-gradient(180deg, #2E95FF 0%, #0A6FE0 100%);
    --glas-primaer-text: #FFFFFF;
}
/* Glasflaeche */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button, .nav-chip,
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *) {
    background: var(--glas-bg) !important;
    border: 1px solid transparent !important;
    -webkit-backdrop-filter: blur(20px) saturate(180%); backdrop-filter: blur(20px) saturate(180%);
    box-shadow: inset 0 1px 1px var(--glas-licht), inset 0 -1px 2px var(--glas-tiefe), var(--glas-schatten),
                0 0 0 0.5px var(--glas-rand-flach), 0 0 16px var(--glas-glow) !important;
    color: var(--glas-text) !important;
    transform: none !important;
    transition: box-shadow .25s ease, transform .15s ease, background .25s ease !important;
    position: relative; isolation: isolate;
}
/* Kapselform fuer einzeilige Knoepfe und Pillen; die Menuekacheln bleiben gross gerundet */
html body :is(.st-key-nav_leiste [data-testid="stButton"] button, [data-testid="stBaseButton-secondary"],
    [data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stDownloadButton"] button,
    [data-testid="stButtonGroup"] button, [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"], .st-key-nav_menue .st-key-nav_refresh button):not(.st-key-logout_ecke *) {
    border-radius: 999px !important;
}
html body .st-key-nav_menue [data-testid="stButton"] button:not(.st-key-logout_ecke *):not(.st-key-nav_refresh *) {
    border-radius: 24px !important;
}
/* Lichtkante: Verlaufsrand als Maske (nur die 1-px-Kante sichtbar) */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button, .nav-chip,
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *)::after {
    content: "" !important; position: absolute; inset: -1px; border-radius: inherit; pointer-events: none; padding: 1px;
    background: var(--glas-kante); display: block !important; animation: none !important; border: 0 !important;
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude;
    opacity: 1; transition: opacity .25s ease;
}
/* Innerer Glanz oben (gewoelbtes Glas) */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button,
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *)::before {
    content: ""; position: absolute; inset: 1px 6% auto 6%; height: 48%; border-radius: inherit; pointer-events: none;
    z-index: -1; background: linear-gradient(180deg, var(--glas-licht), transparent);
    opacity: 0.55;
}
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button):not(.st-key-logout_ecke *) :is(p, span, div) {
    color: inherit !important;
}
/* Darueberfahren / Fokus: Kante leuchtet, weisser Glow, Glas hebt sich minimal */
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button):not(.st-key-logout_ecke *):is(:hover, :focus-visible):not(:disabled) {
    box-shadow: inset 0 1px 1px var(--glas-licht), inset 0 -1px 2px var(--glas-tiefe), var(--glas-schatten),
                0 0 0 0.5px var(--glas-rand-flach), 0 0 24px var(--glas-glow-stark) !important;
    transform: translateY(-1px) !important;
}
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button):not(.st-key-logout_ecke *):is(:hover, :focus-visible):not(:disabled)::after {
    opacity: 1;
}
html body :is(.st-key-nav_menue [data-testid="stButton"] button, .st-key-nav_leiste [data-testid="stButton"] button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stDownloadButton"] button, [data-testid="stButtonGroup"] button,
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *):active:not(:disabled) {
    transform: scale(0.97) !important;
}
/* Gewaehlte Pille / Segment: Systemblau-Glas */
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] :is(button[aria-checked="true"], button[aria-pressed="true"],
    button[data-testid$="Active"]):not(.st-key-logout_ecke *):not(.st-key-x) {
    background: var(--glas-aktiv-bg) !important; color: var(--glas-aktiv-text) !important;
    box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.35), var(--glas-schatten), 0 0 20px rgba(10, 132, 255, 0.35) !important;
}
html body [data-testid="stButtonGroup"][data-testid="stButtonGroup"] :is(button[aria-checked="true"], button[aria-pressed="true"],
    button[data-testid$="Active"]):not(.st-key-logout_ecke *):not(.st-key-x)::after {
    background: var(--glas-aktiv-kante); opacity: 1;
}
/* Hauptaktion: Systemblau-Glas mit weisser Schrift */
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *):not(.st-key-x) {
    background: var(--glas-primaer-bg) !important;
    box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.45), inset 0 -1px 2px rgba(0, 40, 110, 0.35),
                0 10px 26px rgba(10, 132, 255, 0.30), 0 0 18px rgba(10, 132, 255, 0.25) !important;
}
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(.st-key-logout_ecke *):not(.st-key-x)::after {
    background: var(--glas-aktiv-kante);
}
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(:disabled),
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):not(:disabled) :is(p, span) {
    color: var(--glas-primaer-text) !important;
}
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):is(:hover, :focus-visible):not(:disabled):not(.st-key-x) {
    box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.55), 0 12px 30px rgba(10, 132, 255, 0.40),
                0 0 30px rgba(10, 132, 255, 0.45) !important;
    transform: translateY(-1px) !important;
}
/* Deaktiviert: mattes Glas, keine Kante, kein Glow */
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):disabled:not(.st-key-x):not(.st-key-y) {
    background: var(--glas-bg) !important; }
html body :is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):disabled:not(.st-key-x) :is(p, span) {
    color: var(--glas-text) !important; }
html body :is([data-testid="stButton"], [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"],
    [data-testid="stButtonGroup"]) button:disabled:not(.st-key-logout_ecke *):not(.st-key-x):not(.st-key-y) {
    box-shadow: none !important; opacity: 0.5; transform: none !important;
}
html body :is([data-testid="stButton"], [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"],
    [data-testid="stButtonGroup"]) button:disabled:not(.st-key-logout_ecke *):not(.st-key-x):not(.st-key-y)::after { opacity: 0.35; }
/* Segment-Schalter: keine Flaeche hinter den Glas-Pillen */
[data-testid="stButtonGroup"], [data-testid="stButtonGroup"] [role="radiogroup"],
[data-testid="stButtonGroup"] div:not(button div) { background: transparent !important; box-shadow: none !important; }

/* Rahmen von Karten, Klappbereichen, Formularen und Feldern im selben Glas-Look: feine Lichtkante statt Linie */
.quote::after, .hero::after {
    content: ""; position: absolute; inset: -1px; border-radius: inherit; pointer-events: none; padding: 1px;
    background: var(--glas-kante); opacity: 0.9;
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude;
}
html body [data-testid="stExpander"] details, html body [data-testid="stForm"] {
    border: 1px solid var(--rand) !important; border-radius: 20px !important;
    background: var(--glas-bg) !important;
    -webkit-backdrop-filter: blur(18px) saturate(160%); backdrop-filter: blur(18px) saturate(160%);
    box-shadow: inset 0 1px 1px var(--glas-licht), 0 8px 22px rgba(0, 0, 0, 0.22), var(--rand-glow) !important;
}
html body :is([data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"],
    [data-testid="stDateInputField"], [data-testid="stSelectbox"] [role="group"], [data-baseweb="textarea"],
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div) {
    border-radius: 14px !important; border-color: var(--rand) !important;
    box-shadow: inset 0 1px 2px var(--glas-tiefe), var(--rand-glow) !important;
}
html body :is([data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"],
    [data-testid="stDateInputField"], [data-testid="stSelectbox"] [role="group"], [data-baseweb="textarea"]):focus-within {
    border-color: rgba(10, 132, 255, 0.8) !important; box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.25) !important;
}
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
          font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
    .gv .gv-eur { font-size: 1.05rem; font-weight: 700; }
    .gv .gv-pct { font-size: 0.98rem; font-weight: 700; }
    .gv .gv-text { font-family: 'Space Grotesk', -apple-system, sans-serif; font-size: 0.82rem; font-weight: 500;
                   color: var(--label); }
    .gv.up .gv-eur, .gv.up .gv-pct, .gv.up .gv-pfeil { color: var(--up); }
    .gv.down .gv-eur, .gv.down .gv-pct, .gv.down .gv-pfeil { color: var(--down); }
    .gv.flat .gv-eur, .gv.flat .gv-pct, .gv.flat .gv-pfeil { color: var(--label); }
    .kz-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    @container (min-width: 520px) { .kz-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    .kz { border: 1px solid var(--rand); border-radius: 12px; padding: 8px 10px; min-width: 0;
          background: rgba(255, 255, 255, 0.025); }
    .kz-l { font-size: 0.78rem; font-weight: 700; color: var(--label); text-transform: uppercase; letter-spacing: 0.5px; }
    .kz-e, .kz-p { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums;
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
CHART_RASTER = "rgba(177, 179, 183, 0.13)"
CHART_SCHRIFT = "#BCBFC2"


def ist_smartphone():
    """True auf Smartphones (User-Agent; iPad meldet sich als Mac und gilt als Desktop)."""
    try:
        import streamlit as st
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:
        return False
    return "iphone" in ua or ("android" in ua and "mobile" in ua) or "ipod" in ua


def chart_stil(fig, schrumpfen=True):
    """Gemeinsame Plotly-Vorlage (UX 10/2026): Hintergrund durchsichtig (Seiten-Navy statt Schwarz), dezentes
    Raster, deutsche Zahlen. Am Handy: niedriger (70 %, mind. 260 px - ausser bei Legenden unter dem Chart),
    kleinere Achsenschrift, weniger Achsenbeschriftungen und schmalere Raender. -> fig"""
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", separators=",.",
                      font=dict(color=CHART_SCHRIFT))
    fig.update_xaxes(gridcolor=CHART_RASTER, zerolinecolor=CHART_RASTER)
    fig.update_yaxes(gridcolor=CHART_RASTER, zerolinecolor=CHART_RASTER)
    if not ist_smartphone():
        return fig
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
