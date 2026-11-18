"""Kurs-Ticker der Startseite - ohne Streamlit, ohne Netz testbar.

Quelle sind nur die gespeicherten Kurse des Kurs-Agenten (state/kurse/live.json, siehe kurs_vorrat.py) - beim Start
werden keine Kurse abgerufen. Gezeigt werden die eigenen Depotwerte und die Standard-Vergleichswerte (config).
"""
import html
import re

import kurs_vorrat as KV

_KLAMMER = re.compile(r"\s*\([^)]*\)\s*$")


def kurzname(name, max_len=28):
    """"MSCI World (A0RPWH)" -> "MSCI World"; zu lange Namen gekuerzt."""
    n = _KLAMMER.sub("", str(name or "")).strip() or str(name or "").strip()
    return n if len(n) <= max_len else n[:max_len - 1].rstrip() + "…"


def ticker_daten(positionen, benchmarks, live_werte):
    """-> [(name, kurs, veraenderung_pct)] - erst die Depotwerte, dann die Vergleichswerte; jede Kurs-ID nur einmal,
    nur Werte mit Kurs UND Vortageskurs im Vorrat (sonst gaebe es kein "heute ±%")."""
    werte = live_werte if isinstance(live_werte, dict) else {}
    kandidaten = [(p.get("name"), p.get("instrument_id")) for p in (positionen or []) if isinstance(p, dict)]
    kandidaten += list((benchmarks or {}).items())
    aus, gesehen = [], set()
    for name, iid in kandidaten:
        iid = str(iid or "").strip()
        if not iid or iid in gesehen or not name:
            continue
        h = KV.heute(werte.get(iid) or {})
        if not h:
            continue
        gesehen.add(iid)
        kurs, vor = h
        aus.append((kurzname(name), kurs, (kurs / vor - 1) * 100))
    return aus


def _zahl(x, stellen=2):
    return f"{x:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ticker_html(eintraege, stand_text=""):
    """Laufband: Inhalt doppelt hintereinander, per CSS um eine Breite verschoben -> nahtlose Endlosschleife.
    Geschwindigkeit je Eintrag gleich (Dauer waechst mit der Anzahl)."""
    if not eintraege:
        return ""
    teile = []
    for name, kurs, pct in eintraege:
        klasse = "auf" if pct > 0.005 else "ab" if pct < -0.005 else "gleich"
        pfeil = "▲" if klasse == "auf" else "▼" if klasse == "ab" else "■"
        teile.append(f'<span class="tk-wert"><b>{html.escape(name)}</b> {_zahl(kurs)}&nbsp;€ '
                     f'<span class="tk-{klasse}">{pfeil}&nbsp;{"+" if pct > 0 else ""}{_zahl(pct)}&nbsp;%</span></span>')
    band = "".join(teile)
    dauer = max(20, 5 * len(eintraege))
    vorlese = "; ".join(f"{n} {_zahl(k)} Euro, {'+' if p > 0 else ''}{_zahl(p)} Prozent" for n, k, p in eintraege)
    return (f'<div class="tk-rahmen" role="marquee" aria-label="Kurse heute: {html.escape(vorlese)}">'
            + (f'<div class="tk-stand">{html.escape(stand_text)}</div>' if stand_text else "")
            + f'<div class="tk-fenster"><div class="tk-band" style="animation-duration:{dauer}s" aria-hidden="true">'
            f'<div class="tk-teil">{band}</div><div class="tk-teil">{band}</div></div></div></div>')


CSS = """<style>
.tk-rahmen { margin: 6px 0 4px; padding: 8px 0 10px; border-radius: 16px;
    background: var(--karte, rgba(255,255,255,.05)); border: 1px solid var(--rand, rgba(255,255,255,.12)); }
.tk-stand { font-size: .72rem; font-weight: 650; letter-spacing: .06em; text-transform: uppercase;
    color: var(--label, #A9B1C4); padding: 0 14px 6px; }
.tk-fenster { overflow: hidden; position: relative;
    -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 18px, #000 calc(100% - 18px), transparent 100%);
            mask-image: linear-gradient(90deg, transparent 0, #000 18px, #000 calc(100% - 18px), transparent 100%); }
.tk-band { display: flex; width: max-content; animation: tk-lauf linear infinite; }
.tk-rahmen:hover .tk-band, .tk-rahmen:active .tk-band { animation-play-state: paused; }
.tk-teil { display: flex; flex-shrink: 0; }
.tk-wert { white-space: nowrap; padding: 0 18px; font-size: .9rem; color: var(--text, #E8ECF6);
    font-variant-numeric: tabular-nums; border-right: 1px solid var(--rand, rgba(255,255,255,.12)); }
.tk-wert b { font-weight: 650; margin-right: 4px; }
.tk-auf { color: var(--pos, #34D399); font-weight: 650; }
.tk-ab { color: var(--neg, #F87171); font-weight: 650; }
.tk-gleich { color: var(--label, #A9B1C4); font-weight: 650; }
@keyframes tk-lauf { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@media (prefers-reduced-motion: reduce) {
    .tk-band { animation: none; } .tk-teil + .tk-teil { display: none; }
    .tk-fenster { overflow-x: auto; -webkit-mask-image: none; mask-image: none; }
}
</style>"""
