"""HTML-Bausteine der Depot-Kacheln ohne Streamlit (aus app.py ausgelagert, Audit ARCH-01): Kopfkachel, Kennzahl-
Kacheln, Gewinn/Verlust-Zeilen und Zeitraum-Zeilen. app.py importiert alle Namen zurueck; test_depot_kacheln
importiert dieses Modul direkt.
"""
import html

import formate as FMT


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
