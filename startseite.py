"""Kurs-Ticker der Startseite - ohne Streamlit, ohne Netz testbar.

Quelle sind nur die gespeicherten Kurse des Kurs-Agenten (state/kurse/live.json, siehe kurs_vorrat.py) - beim Start
werden keine Kurse abgerufen. Gezeigt werden nur echte Indexstaende (indizes.py: DAX in Punkten usw.).
"""
import datetime
import html
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def _zahl(x, stellen=2):
    return f"{x:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _kurs_text(kurs, einheit):
    """Punkte ohne Einheit, Waehrungen mit Zeichen, Wechselkurse mit 4 Nachkommastellen."""
    if einheit == "fx":
        return _zahl(kurs, 4)
    return _zahl(kurs) + (f"&nbsp;{einheit}" if einheit else "")


def _vorlese(kurs, einheit):
    if einheit == "fx":
        return _zahl(kurs, 4)
    return _zahl(kurs) + {"€": " Euro", "$": " Dollar", "": " Punkte"}.get(einheit, "")


def ticker_html(eintraege, stand_text=""):
    """Laufband: Inhalt doppelt hintereinander, per CSS um eine Breite verschoben -> nahtlose Endlosschleife.
    Geschwindigkeit je Eintrag gleich (Dauer waechst mit der Anzahl). Jede Haelfte ist mindestens so breit wie
    der Bildschirm - so ist jeder Wert nur einmal zu sehen, auch wenn es wenige sind."""
    if not eintraege:
        return ""
    teile = []
    for name, kurs, pct, einheit in eintraege:
        klasse = "auf" if pct > 0.005 else "ab" if pct < -0.005 else "gleich"
        pfeil = "▲" if klasse == "auf" else "▼" if klasse == "ab" else "■"
        teile.append(f'<span class="tk-wert"><b>{html.escape(name)}</b> {_kurs_text(kurs, einheit)} '
                     f'<span class="tk-{klasse}">{pfeil}&nbsp;{"+" if pct > 0 else ""}{_zahl(pct)}&nbsp;%</span></span>')
    band = "".join(teile)
    dauer = max(10, 2.5 * len(eintraege))       # 2,5 s je Wert
    vorlese = "; ".join(f"{n} {_vorlese(k, e)}, {'+' if p > 0 else ''}{_zahl(p)} Prozent" for n, k, p, e in eintraege)
    return (f'<div class="tk-rahmen" role="marquee" aria-label="Kurse heute: {html.escape(vorlese)}">'
            + (f'<div class="tk-stand">{html.escape(stand_text)}</div>' if stand_text else "")
            + f'<div class="tk-fenster"><div class="tk-band" style="animation-duration:{dauer}s" aria-hidden="true">'
            f'<div class="tk-teil">{band}</div><div class="tk-teil">{band}</div></div></div></div>')


QUELLEN = {"tagesschau": "tagesschau.de"}


def _news_zeit(text, jetzt):
    try:
        t = datetime.datetime.fromisoformat(text).astimezone(BERLIN)
    except (TypeError, ValueError):
        return ""
    return t.strftime("%H:%M") if t.date() == jetzt.date() else t.strftime("%d.%m.")


def news_html(eintraege, jetzt=None, titel="Finanz-News"):
    """Zweites Laufband mit Schlagzeilen (Uhrzeit, Titel als Link zum Anbieter, Quelle). Langsamer als die Kurse,
    damit man mitlesen kann; bei Beruehrung oder Mauszeiger haelt es an (dann lassen sich die Links antippen)."""
    if not eintraege:
        return ""
    jetzt = jetzt or datetime.datetime.now(BERLIN)
    teile = []
    for e in eintraege:
        link = str(e.get("link") or "")
        if not link.startswith(("https://", "http://")):
            continue
        zeit = _news_zeit(e.get("zeit"), jetzt)
        teile.append('<span class="tk-wert">' + (f'<span class="tk-zeit">{zeit}</span>' if zeit else "")
                     + f'<a href="{html.escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">'
                     f'{html.escape(e.get("titel") or "")}</a>'
                     f'<span class="tk-quelle">{html.escape(QUELLEN.get(e.get("quelle"), e.get("quelle") or ""))}'
                     f'</span></span>')
    if not teile:
        return ""
    band = "".join(teile)
    dauer = max(30, 9 * len(teile))                 # 9 s je Schlagzeile: lesbar
    return (f'<div class="tk-rahmen tk-news" role="region" aria-label="{html.escape(titel)}">'
            f'<div class="tk-stand">{html.escape(titel)}</div>'
            f'<div class="tk-fenster"><div class="tk-band" style="animation-duration:{dauer}s">'
            f'<div class="tk-teil">{band}</div><div class="tk-teil" aria-hidden="true">'
            + band.replace("<a ", '<a tabindex="-1" ') + '</div></div></div></div>')   # Kopie: nicht doppelt per Tab


CSS = """<style>
.tk-rahmen { margin: 6px 0 4px; padding: 8px 0 10px; border-radius: 16px;
    background: var(--karte, rgba(255,255,255,.05)); border: 1px solid var(--rand, rgba(255,255,255,.12)); }
.tk-stand { font-size: .72rem; font-weight: 650; letter-spacing: .06em; text-transform: uppercase;
    color: var(--label, #A9B1C4); padding: 0 14px 6px; text-align: center; }
.tk-fenster { overflow: hidden; position: relative;
    -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 18px, #000 calc(100% - 18px), transparent 100%);
            mask-image: linear-gradient(90deg, transparent 0, #000 18px, #000 calc(100% - 18px), transparent 100%); }
.tk-band { display: flex; width: max-content; animation: tk-lauf linear infinite; }
.tk-rahmen:hover .tk-band, .tk-rahmen:active .tk-band { animation-play-state: paused; }
.tk-teil { display: flex; flex-shrink: 0; min-width: calc(100vw + 20rem); }   /* breiter als Bildschirm + ein Wert */
.tk-wert { white-space: nowrap; padding: 0 18px; font-size: .9rem; color: var(--text, #E8ECF6);
    font-variant-numeric: tabular-nums; border-right: 1px solid var(--rand, rgba(255,255,255,.12)); }
.tk-wert b { font-weight: 650; margin-right: 4px; }
.tk-auf { color: var(--pos, #34D399); font-weight: 650; }
.tk-ab { color: var(--neg, #F87171); font-weight: 650; }
.tk-gleich { color: var(--label, #A9B1C4); font-weight: 650; }
.tk-news .tk-wert { font-size: .86rem; }
.tk-news a { color: var(--text, #E8ECF6) !important; text-decoration: none; }
.tk-news a:hover, .tk-news a:focus-visible { text-decoration: underline; }
.tk-news .tk-zeit { color: var(--label, #A9B1C4); font-weight: 650; margin-right: 6px; }
.tk-news .tk-quelle { color: var(--label, #A9B1C4); margin-left: 6px; font-size: .78rem; }
@keyframes tk-lauf { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@media (prefers-reduced-motion: reduce) {
    .tk-band { animation: none; } .tk-teil + .tk-teil { display: none; }
    .tk-fenster { overflow-x: auto; -webkit-mask-image: none; mask-image: none; }
}
</style>"""
