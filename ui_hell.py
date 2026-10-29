"""Helle Ansicht (UX 10/2026).

Die App ist dunkel gestaltet; ihre Farben stehen in vielen CSS-Bloecken (ui_stil.py und die Module).
Statt jede Regel doppelt zu pflegen, rechnet dieses Modul die dunklen Farben in passende helle um:

- alle <style>-Bloecke der App-Quellen werden gelesen; jede Deklaration mit einer Farbe wird mit der
  umgerechneten Farbe erneut ausgegeben (gleicher Selektor, hoehere Spezifitaet - unabhaengig von der
  Reihenfolge im Dokument)
- feste Farben in style="..."-Attributen bekommen eigene Attribut-Regeln
- Streamlit-Bausteine (Eingabefelder, Auswahllisten, Tabellen, Charts) haben eigene Regeln (WIDGETS)

Umrechnung: Hintergruende und Flaechen werden hell, Texte dunkel (Helligkeit gespiegelt, Farbton bleibt);
kraeftige Farben (Gruen/Rot fuer Kursveraenderungen, Blau als Bedienfarbe) behalten ihren Farbton und werden
nur so weit abgedunkelt, dass sie auf hellem Grund lesbar sind. Weisse Leuchtschatten entfallen.

stil(modus) -> fertiges <style>-Markup: "" fuer dunkel, die Regeln fuer hell, bei "auto" dieselben Regeln
innerhalb von @media (prefers-color-scheme: light).
"""
import colorsys
import functools
import glob
import os
import re

MODI = ("dunkel", "hell", "auto")
MODUS_TEXT = {"dunkel": "🌙 Dunkel", "hell": "☀️ Hell", "auto": "🖥️ Wie Gerät"}

_STAERKER = ":not(#fd-hell)"          # +1 ID-Spezifitaet: die helle Regel gewinnt immer gegen ihr dunkles Original
_FARBE = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b|rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*(?:,\s*[\d.]+\s*)?\)")
_FARB_EIGENSCHAFT = re.compile(r"^(--[\w-]+|color|background(-color|-image)?|border(-top|-right|-bottom|-left)?(-color)?|"
                               r"outline(-color)?|box-shadow|text-shadow|fill|stroke|caret-color|"
                               r"text-decoration-color|accent-color)$")


# ------------------------------------------------------------------ Farben
def _hex_zu_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _parse(farbe):
    """-> (r, g, b, a) oder None."""
    f = farbe.strip()
    if f.startswith("#"):
        return (*_hex_zu_rgb(f), 1.0)
    zahlen = [float(x) for x in re.findall(r"[\d.]+", f)]
    if len(zahlen) == 3:
        zahlen.append(1.0)
    return tuple(zahlen[:4]) if len(zahlen) == 4 else None


def _ausgabe(r, g, b, a):
    r, g, b = (max(0, min(255, round(x))) for x in (r, g, b))
    if a >= 0.999:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"rgba({r}, {g}, {b}, {round(a, 3)})"


def hell(farbe):
    """Eine Farbe des dunklen Designs -> die passende Farbe des hellen Designs (Text bleibt Text-Syntax)."""
    p = _parse(farbe)
    if p is None:
        return farbe
    r, g, b, a = p
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    # Weisse Ueberlagerungen (Zebra, Hover, Glanz) -> dunkle Ueberlagerung, etwas schwaecher
    if l > 0.97 and a < 0.999:
        return _ausgabe(0, 0, 0, a * 0.6)
    # Schatten (schwarz / fast schwarz, transparent) -> leichter, kuehler Schatten
    if l < 0.12 and a < 0.999:
        return _ausgabe(0, 0, 0, min(a, 0.6) * 0.25)
    if a >= 0.999 and l > 0.9 and s < 0.25:
        return "#1C1C1E"                                     # Weiss als Textfarbe -> Apple-Textschwarz
    if s >= 0.4 and 0.22 < l < 0.85:
        # kraeftige Farbe (Gruen/Rot/Blau/Gelb): Farbton bleibt, auf hellem Grund lesbar (Kontrast >= 4,5)
        l2 = min(l, 0.3 if 0.05 < h < 0.2 else 0.27 if 0.2 <= h < 0.55 else 0.42)   # Gelb/Gruen dunkler
        if a < 0.999:                                        # getoente Flaechen bleiben hell und zart
            l2 = l
    elif l < 0.3:
        l2 = 1 - l * 0.45                                    # Grund und Flaechen: sehr hell, leicht blau
    elif l > 0.7:
        l2 = (1 - l) * 1.5                                   # helle Texte -> dunkle Texte
    else:
        l2 = 1 - l                                           # Mitteltoene (Sekundaertext) spiegeln
    r2, g2, b2 = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l2)), min(s, 0.85))
    return _ausgabe(r2 * 255, g2 * 255, b2 * 255, a)


def _rand(farbe):
    """Weisse/helle Raender (Neon-Look) -> weiches Graublau statt Navy-Schwarz."""
    p = _parse(farbe)
    if p is None:
        return farbe
    r, g, b, a = p
    if colorsys.rgb_to_hls(r / 255, g / 255, b / 255)[1] > 0.85:
        return "#C7C7CC" if a >= 0.999 else _ausgabe(0, 0, 0, min(1.0, a * 0.45))
    return hell(farbe)


def _schrift(farbe):
    """Schriftfarbe: dunkle Schrift (z. B. auf hellen Knoepfen) bleibt dunkel, alles andere wie hell()."""
    p = _parse(farbe)
    if p and colorsys.rgb_to_hls(*[x / 255 for x in p[:3]])[1] < 0.3:
        return "#1C1C1E"
    return hell(farbe)


def _wert_umrechnen(eigenschaft, wert):
    if eigenschaft == "text-shadow":
        return "none"
    if eigenschaft in ("color", "-webkit-text-fill-color", "caret-color"):
        return _FARBE.sub(lambda m: _schrift(m.group(0)), wert)
    abbild = _rand if eigenschaft.startswith(("border", "outline")) else hell
    return _FARBE.sub(lambda m: abbild(m.group(0)), wert)


def _hintergrund(wert):
    """'background'-Kurzform -> Einzeleigenschaften: die Kurzform wuerde background-clip zuruecksetzen
    (Schrift mit Farbverlauf wuerde zum Balken). -> [(eigenschaft, wert)]"""
    if "gradient(" not in wert:
        return [("background-color", wert)] if _FARBE.fullmatch(wert.strip()) else [("background", wert)]
    schichten = [t.strip() for t in _teile(wert)]
    verlaeufe = [t for t in schichten if "gradient(" in t]
    rest = [t for t in schichten if "gradient(" not in t and _FARBE.fullmatch(t)]
    aus = [("background-image", ", ".join(verlaeufe))]
    if rest:
        aus.append(("background-color", rest[-1]))
    return aus


# ------------------------------------------------------------------ CSS lesen und umschreiben
def _staerker(selektor):
    """Selektorliste mit +1 ID-Spezifitaet; Pseudo-Elemente bleiben am Ende."""
    teile = []
    for s in _teile(selektor):
        s = s.strip()
        if not s:
            continue
        if s in (":root", "html", "body"):
            teile.append(f"{s}{_STAERKER}")
            continue
        m = re.search(r"::?(before|after|placeholder|selection|-webkit-[\w-]+|marker)\b.*$", s)
        if m:
            teile.append(s[:m.start()] + _STAERKER + s[m.start():])
        else:
            teile.append(s + _STAERKER)
    return ", ".join(teile)


def _teile(selektor):
    """Selektorliste an Kommas auf oberster Ebene teilen (nicht in :is(...)/:not(...))."""
    tiefe, akt, aus = 0, "", []
    for ch in selektor:
        if ch == "(":
            tiefe += 1
        elif ch == ")":
            tiefe -= 1
        if ch == "," and tiefe == 0:
            aus.append(akt)
            akt = ""
        else:
            akt += ch
    aus.append(akt)
    return aus


def _bloecke(css):
    """Tokenisiert CSS in (kopf, inhalt) auf oberster Ebene - inhalt ist Deklarationstext oder verschachteltes CSS."""
    i, n, aus = 0, len(css), []
    while i < n:
        auf = css.find("{", i)
        if auf < 0:
            break
        kopf = css[i:auf].strip()
        tiefe, j = 1, auf + 1
        while j < n and tiefe:
            if css[j] == "{":
                tiefe += 1
            elif css[j] == "}":
                tiefe -= 1
            j += 1
        aus.append((kopf, css[auf + 1:j - 1]))
        i = j
    return aus


def umschreiben(css):
    """Dunkles CSS -> nur die Farb-Regeln, umgerechnet fuer die helle Ansicht."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    aus = []
    for kopf, inhalt in _bloecke(css):
        kopf = re.sub(r"\s+", " ", kopf)
        if kopf.startswith("@"):
            if re.match(r"@(-webkit-)?keyframes|@property|@font-face|@import", kopf):
                continue
            innen = umschreiben(inhalt)
            if innen:
                aus.append(f"{kopf} {{{innen}}}")
            continue
        if "{" in inhalt:                              # unerwartete Verschachtelung - ueberspringen
            continue
        dekl = []
        hg = re.search(r"background(?:-color)?\s*:\s*([^;]+)", inhalt)
        dunkle_flaeche = False
        if hg:
            m = _FARBE.search(hg.group(1))
            if m and _parse(hell(m.group(0))) and colorsys.rgb_to_hls(*[x / 255 for x in _parse(hell(m.group(0)))[:3]])[1] < 0.55 \
                    and (_parse(m.group(0)) or (0, 0, 0, 0))[3] >= 0.9:
                dunkle_flaeche = True             # z. B. blaues Symbol mit weisser Ziffer: Schrift bleibt hell
        for d in inhalt.split(";"):
            if ":" not in d:
                continue
            eig, wert = d.split(":", 1)
            eig = eig.strip().lower()
            if not _FARB_EIGENSCHAFT.match(eig):
                continue
            if not _FARBE.search(wert) and eig != "text-shadow":
                continue
            wert = wert.replace("!important", "").strip()
            if eig == "text-shadow" and wert == "none":
                continue
            if dunkle_flaeche and eig == "color":
                continue
            neu = _wert_umrechnen(eig, wert)
            for e2, w2 in (_hintergrund(neu) if eig == "background" else [(eig, neu)]):
                dekl.append(f"{e2}: {w2} !important")
        if dekl and kopf:
            aus.append(f"{_staerker(kopf)} {{ {'; '.join(dekl)}; }}")
    return "\n".join(aus)


def _quellen_css(ordner):
    """Alle <style>-Bloecke aus den App-Quellen (ohne Tests). Platzhalter von f-Strings fallen weg."""
    teile = []
    for pfad in sorted(glob.glob(os.path.join(ordner, "*.py"))):
        name = os.path.basename(pfad)
        # glass_theme.py: Grundlage arbeitet mit Variablen - die helle Ansicht setzt deren Werte in WIDGETS;
        # automatisch umgerechnete Kopien seiner Regeln wuerden das Glas grau und schwer machen
        if name.startswith("test_") or name in ("ui_hell.py", "glass_theme.py"):
            continue
        try:
            text = open(pfad, encoding="utf-8").read()
        except OSError:
            continue
        for block in re.findall(r"<style>(.*?)</style>", text, flags=re.S):
            if "{{" in block:                          # f-String: doppelte Klammern sind echte Klammern
                block = block.replace("{{", "{").replace("}}", "}")
            block = re.sub(r"\{[A-Za-z_][\w.\[\]'\"()]*(:[^{}]*)?\}", "", block)   # {variable} entfernen
            teile.append(block)
    return "\n".join(teile)


def _inline_regeln(ordner):
    """Feste Farben in style="..."-Attributen. Viele setzt Python dynamisch (style="color:{farbe}") - deshalb
    bekommt jedes Farbliteral aus Zeilen mit Farbbezug eine kompakte Attribut-Regel: helle und kraeftige Farben
    als Schrift, dunkle als Hintergrund."""
    farben = set()
    for pfad in glob.glob(os.path.join(ordner, "*.py")):
        if os.path.basename(pfad).startswith("test_") or os.path.basename(pfad) == "ui_hell.py":
            continue
        for zeile in open(pfad, encoding="utf-8"):
            if re.search(r"color|background|farbe|FARBE", zeile):
                farben |= {f.upper() for f in re.findall(r"#[0-9A-Fa-f]{6}\b", zeile)}
    regeln = []
    for f in sorted(farben):
        h = hell(f)
        if h.upper() == f:
            continue
        l = colorsys.rgb_to_hls(*[x / 255 for x in _hex_zu_rgb(f)])[1]
        eig = "background-color" if l < 0.3 else "color"
        r, g, b = _hex_zu_rgb(f)
        # Streamlit schreibt style-Attribute als "color: rgb(r, g, b)" ins HTML (React) - beide Formen abdecken
        regeln.append(f'[style*="rgb({r}, {g}, {b})"]{_STAERKER}, [style*="{f}" i]{_STAERKER}{{{eig}:{h}!important}}')
    return "\n".join(regeln)


# Streamlit-Bausteine: deren Farben kommen aus dem (dunklen) Streamlit-Theme, nicht aus unserem CSS
WIDGETS = """
.stApp:not(#fd-hell), [data-testid="stAppViewContainer"]:not(#fd-hell) { color: #1C1C1E !important; color-scheme: light; }
[data-testid="stMarkdownContainer"]:not(#fd-hell), [data-testid="stWidgetLabel"]:not(#fd-hell),
[data-testid="stWidgetLabel"] p:not(#fd-hell), [data-testid="stExpander"] summary:not(#fd-hell),
[data-testid="stExpander"] summary p:not(#fd-hell), [data-testid="stMetricValue"]:not(#fd-hell),
[data-testid="stMetricLabel"]:not(#fd-hell), [data-testid="stMetricLabel"] p:not(#fd-hell),
[data-testid="stHeading"]:not(#fd-hell), [data-testid="stHeading"] *:not(#fd-hell),
[data-testid="stText"]:not(#fd-hell), [data-testid="stCheckbox"] label:not(#fd-hell),
[data-testid="stRadio"] label:not(#fd-hell), [data-testid="stToggle"] label:not(#fd-hell),
[role="tab"]:not(#fd-hell), [role="tab"] p:not(#fd-hell) { color: #1C1C1E !important; }
[data-testid="stCaptionContainer"]:not(#fd-hell), [data-testid="stCaptionContainer"] *:not(#fd-hell) { color: #6E6E73 !important; }
[role="tab"][aria-selected="true"]:not(#fd-hell), [role="tab"][aria-selected="true"] p:not(#fd-hell) { color: #4C6EF5 !important; }
/* Eingabefelder */
:is([data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-testid="stNumberInputContainer"],
    [data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stDateInputField"],
    [data-testid="stSelectbox"] [role="group"],
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div):not(#fd-hell) {
    background: #FFFFFF !important; border-color: var(--rand) !important; color: #1C1C1E !important; }
:is(input, textarea):not(#fd-hell) { color: #1C1C1E !important; -webkit-text-fill-color: #1C1C1E !important;
    background: transparent !important; caret-color: #4C6EF5 !important; }
:is(input, textarea)::placeholder { color: #8E8E93 !important; -webkit-text-fill-color: #8E8E93 !important; }
:is([data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"]):not(#fd-hell) {
    background: transparent !important; color: #1C1C1E !important; }
:is([data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"]):hover:not(#fd-hell) { background: #F2F2F7 !important; }
[data-testid="stSelectbox"] svg:not(#fd-hell), [data-testid="stMultiSelect"] svg:not(#fd-hell),
[data-testid="stDateInput"] svg:not(#fd-hell) { color: #3A3A3C !important; fill: currentColor; }
/* Auswahllisten (Popover der Auswahlfelder, Kalender) */
:is([data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"], [data-baseweb="calendar"]):not(#fd-hell),
:is([data-baseweb="popover"], [role="listbox"]) :is(ul, li, div):not(#fd-hell) {
    background-color: #FFFFFF !important; color: #1C1C1E !important; }
:is([role="option"]):hover:not(#fd-hell), [role="option"][aria-selected="true"]:not(#fd-hell),
[role="option"][data-focused="true"]:not(#fd-hell) { background-color: #E5E5EA !important; }
/* Knoepfe, Kacheln, Pillen: Glas-Optik (ui_stil GLAS) - hier nur die Werte fuer helles, milchiges Glas */
:root:not(#fd-hell) {
    --glas-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(255, 255, 255, 0.72) 100%), rgba(255, 255, 255, 0.55) !important;
    --glas-bg-hover: linear-gradient(180deg, #F3F4F7 0%, #E4E7ED 100%), #E9ECF1 !important;   /* Darueberfahren: grau */
    --glas-rand: rgba(15, 23, 42, 0.10) !important;
    --glas-rand-stark: rgba(15, 23, 42, 0.24) !important;
    --glas-glanz: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0)) !important;
    --glas-reflex: linear-gradient(110deg, transparent, rgba(15, 23, 42, 0.10), transparent) !important;
    --glas-licht: #FFFFFF !important;
    --glas-tiefe: rgba(15, 23, 42, 0.06) !important;
    --glas-schatten: inset 0 1px 0 #FFFFFF, 0 1px 2px rgba(15, 23, 42, 0.06), 0 8px 24px -10px rgba(15, 23, 42, 0.18) !important;
    --glas-schatten-hover: inset 0 1px 0 rgba(255, 255, 255, 0.9), 0 0 0 1px rgba(15, 23, 42, 0.10), 0 14px 32px -10px rgba(15, 23, 42, 0.32) !important;
    --glas-schatten-press: inset 0 2px 6px rgba(15, 23, 42, 0.12) !important;
    --glas-text: #0F172A !important;
    --glas-text-hover: #0F172A !important;
    --glas-glow-stark: rgba(76, 110, 245, 0.18) !important;
    --glas-rand-flach: rgba(15, 23, 42, 0.08) !important;
    --karte-schatten: inset 0 1px 0 #FFFFFF, 0 1px 2px rgba(15, 23, 42, 0.05), 0 12px 32px -14px rgba(15, 23, 42, 0.16) !important;
    --trenn: rgba(15, 23, 42, 0.10) !important;
    --seg-spur: rgba(15, 23, 42, 0.05) !important;
    --seg-daumen: #FFFFFF !important;
    --seg-daumen-schatten: 0 1px 2px rgba(15, 23, 42, 0.10), 0 4px 12px -4px rgba(15, 23, 42, 0.18) !important;
    --seg-text: #475569 !important;
    --seg-text-aktiv: #0F172A !important;
    --chip-aktiv-bg: linear-gradient(135deg, rgba(76, 110, 245, 0.16), rgba(20, 184, 166, 0.10)) !important;
    --chip-aktiv-rand: rgba(76, 110, 245, 0.45) !important;
    --chip-aktiv-text: #2F4AC7 !important;
    --glas-aktiv-text: #FFFFFF !important;
    --glas-primaer-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.18) 0%, rgba(255, 255, 255, 0) 60%), linear-gradient(135deg, #5B7BFF, #2BB5A5) !important;
    --glas-primaer-rand: rgba(76, 110, 245, 0.55) !important;
    --glas-primaer-text: #FFFFFF !important;
    --glas-primaer-schatten: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 8px 22px -8px rgba(76, 110, 245, 0.55) !important;
    --glas-primaer-schatten-hover: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 12px 30px -8px rgba(76, 110, 245, 0.65) !important;
    --glas-fokus: 0 0 0 3px rgba(76, 110, 245, 0.25) !important;
    --feld-bg: #FFFFFF !important;
    --feld-innen: inset 0 1px 2px rgba(15, 23, 42, 0.05) !important;
    --karte: linear-gradient(160deg, rgba(255, 255, 255, 0.92) 0%, rgba(255, 255, 255, 0.74) 100%) !important;
    --rand: rgba(15, 23, 42, 0.12) !important;
    --rand-glow: 0 0 0 transparent !important;
    --accent: #4C6EF5 !important;
    --bg-0: #EEF1F8 !important;
    --bg-1: #FFFFFF !important;
    --text: #0F172A !important;
    --text-dim: #64748B !important;
    --glass-bg: rgba(255, 255, 255, 0.72) !important;
    --glass-bg-hover: rgba(255, 255, 255, 0.92) !important;
    --glass-border: rgba(15, 23, 42, 0.10) !important;
    --glass-border-strong: rgba(76, 110, 245, 0.35) !important;
    --shadow: 0 1px 2px rgba(15, 23, 42, 0.05), 0 12px 32px -14px rgba(15, 23, 42, 0.16) !important;
    --accent-2: #0D9488 !important;
    --puls-licht: rgba(76, 110, 245, 0.55) !important;
    --puls-licht-weit: rgba(76, 110, 245, 0.22) !important;
    --sf-nr-text: #FFFFFF !important;
    --accent-hell: #3B5BDB !important;
    --pos: #047857 !important;
    --neg: #B91C1C !important;
}
button:disabled:not([data-testid^="stNumberInputStep"]):not(#fd-hell) { background: #E5E5EA !important; border-color: #D1D1D6 !important; }
[data-testid^="stNumberInputStep"]:disabled:not(#fd-hell) { background: transparent !important; }
/* Auswahlfelder: nur der feine Feldrand - alter Leucht-Rahmen (umgerechnet zu grauem Schatten) entfaellt */
:is([data-testid="stSelectbox"] > div, [data-testid="stSelectbox"] [data-baseweb="select"]):not(#fd-hell) {
    outline: none !important; box-shadow: none !important; }
/* glass_theme.py (Grundlage) in Hell: Titel und Reiter dunkel statt weiss */
h1:not(#fd-hell) { background: none !important; color: #0F172A !important; -webkit-text-fill-color: #0F172A !important; }
[data-baseweb="tab"][aria-selected="true"]:not(#fd-hell) { background: #FFFFFF !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08), 0 4px 12px -4px rgba(15, 23, 42, 0.16) !important; }
button:disabled:not(#fd-hell), button:disabled p:not(#fd-hell), button:disabled span:not(#fd-hell) { color: #6E6E73 !important; }
/* Klappbereiche, Reiter, Formulare, Hinweise */
[data-testid="stExpander"] details:not(#fd-hell) { background: var(--glas-bg) !important; border-color: var(--rand) !important; }
[data-testid="stExpander"] summary:not(#fd-hell) { background-color: transparent !important; }
[data-testid="stExpander"] summary:hover:not(#fd-hell) { background-color: #F2F2F7 !important; }
[data-testid="stDateInputField"] *:not(#fd-hell), [data-testid="stDateInput"] [role="spinbutton"]:not(#fd-hell),
[data-testid="stTimeInput"] [role="spinbutton"]:not(#fd-hell) { color: #1C1C1E !important; }
[data-testid="stDateInput"] [role="spinbutton"][aria-valuenow=""]:not(#fd-hell) { color: #8E8E93 !important; }
[data-testid="stExpander"] summary svg:not(#fd-hell) { fill: #3A3A3C !important; color: #3A3A3C !important; }
[data-testid="stForm"]:not(#fd-hell) { background: var(--glas-bg) !important; border-color: var(--rand) !important; }
[data-testid="stTabs"] [data-baseweb="tab-border"]:not(#fd-hell) { background: #D1D1D6 !important; }
[data-testid="stAlertContainer"]:not(#fd-hell) { color: #1C1C1E !important; }
[data-testid="stAlertContainer"] *:not(#fd-hell) { color: inherit !important; }
[data-testid="stCode"] pre:not(#fd-hell), [data-testid="stCode"] code:not(#fd-hell) { background: #F2F2F7 !important; color: #1C1C1E !important; }
[data-testid="stTooltipIcon"] svg:not(#fd-hell), button[aria-label^="Help"] svg:not(#fd-hell) {
    color: #6E6E73 !important; stroke: #6E6E73 !important; opacity: 1 !important; }
/* Tabellen (Datenraster wird auf Leinwand gezeichnet - per Filter hell, Farben behalten ihren Ton) */
[data-testid="stDataFrame"]:not(#fd-hell), [data-testid="stDataEditor"]:not(#fd-hell) {
    filter: invert(1) hue-rotate(180deg); }
.pt-leer:not(#fd-hell) { color: #8E8E93 !important; }
[data-testid="stTable"] :is(th, td):not(#fd-hell) { color: #1C1C1E !important; border-color: #D1D1D6 !important; }
/* Charts: Plotly- und Vega-Beschriftungen dunkel */
.js-plotly-plot .main-svg :is(text, .legendtext, .gtitle, .xtitle, .ytitle):not(#fd-hell) { fill: #3A3A3C !important; }
.js-plotly-plot .hoverlayer .hovertext text:not(#fd-hell) { fill: #1C1C1E !important; }
.vega-embed text:not(#fd-hell) { fill: #3A3A3C !important; }
/* Ladeanzeige oben */
[data-testid="stApp"][data-test-script-state="running"]::before, [data-testid="stApp"][data-test-script-state="rerunRequested"]::before {
    background: rgba(242, 242, 247, 0.97) !important; color: #1C1C1E !important; }
"""


@functools.lru_cache(maxsize=1)
def _regeln():
    ordner = os.path.dirname(os.path.abspath(__file__))
    widgets = WIDGETS.replace(_STAERKER, _STAERKER + ":not(#fd-w)")
    return umschreiben(_quellen_css(ordner)) + "\n" + _inline_regeln(ordner) + "\n" + widgets


def stil(modus):
    """<style>-Markup fuer den Modus ("dunkel" -> "")."""
    if modus not in ("hell", "auto"):
        return ""
    regeln = _regeln()
    if modus == "auto":
        regeln = f"@media (prefers-color-scheme: light) {{\n{regeln}\n}}"
    return f"<style>\n{regeln}\n</style>"
