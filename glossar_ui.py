"""Oberflaeche zum Glossar (glossar.py): eigene Seite "Begriffe" mit Suche und am Ende jeder Ansicht ein
eingeklapptes "Begriffe kurz erklaert" mit den Begriffen, die dort vorkommen."""
import html

import glossar as G

CSS = """<style>
.gl-karte { padding: 12px 14px; border-radius: 14px; margin: 0 0 10px;
    background: var(--karte, rgba(255,255,255,.04)); border: 1px solid var(--rand, rgba(255,255,255,.10)); }
.gl-name { font-weight: 700; color: var(--text, #E8ECF6); font-size: .98rem; line-height: 1.3; }
.gl-bereich { font-size: .72rem; font-weight: 650; letter-spacing: .05em; text-transform: uppercase;
    color: var(--label, #A9B1C4); margin-top: 2px; }
.gl-text { color: var(--text, #E8ECF6); opacity: .92; font-size: .9rem; line-height: 1.5; margin-top: 6px; }
.gl-kurz p { margin-bottom: .55rem; }
</style>"""


def _karte(name, bereich, text):
    return (f'<div class="gl-karte"><div class="gl-name">{html.escape(name)}</div>'
            + (f'<div class="gl-bereich">{html.escape(bereich)}</div>' if bereich else "")
            + f'<div class="gl-text">{html.escape(text)}</div></div>')


def seite(st):
    """Eigene Seite: alle Begriffe, durchsuchbar, wahlweise nach Bereich."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.caption(f"{len(G.BEGRIFFE)} Fachbegriffe aus der App in einfachen Worten – mit Faustregeln zum Einordnen.")
    such = st.text_input("Begriff suchen", key="gl_suche", placeholder="z. B. KGV, Drawdown, NPV …")
    bereich = st.pills("Bereich", ["Alle"] + list(G.BEREICHE), key="gl_bereich", default="Alle",
                       label_visibility="collapsed")
    treffer = G.suchen(such)
    if bereich and bereich != "Alle":
        treffer = [t for t in treffer if t[1] == bereich]
    if not treffer:
        st.info("Kein Begriff gefunden. Anders schreiben oder Bereich auf „Alle“ stellen.")
        return
    st.markdown("".join(_karte(n, b, e) for n, b, e in treffer), unsafe_allow_html=True)


def zur_ansicht(st, ansicht):
    """Am Ende einer Ansicht: eingeklappt die dort vorkommenden Begriffe (nichts, wenn keine hinterlegt sind)."""
    begriffe = G.fuer_ansicht(ansicht)
    if not begriffe:
        return
    with st.expander(f"📖 Begriffe kurz erklärt ({len(begriffe)})", expanded=False):
        st.markdown('<div class="gl-kurz">' + "".join(
            f"<p><b>{html.escape(n)}</b> – {html.escape(e)}</p>" for n, e in begriffe) + "</div>",
            unsafe_allow_html=True)
        st.caption("Alle Begriffe: Menü → Hilfe → 📖 Begriffe")
