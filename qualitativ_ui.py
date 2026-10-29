"""Qualitative Analyse - Bereich der Investoren-Checks (Abschnitt 15).

Zeigt die Vorberechnung (qualitativ_agent.py: 10-K, Wikidata, Textanalyse, ggf. KI), dazu live von Yahoo die
Unternehmensbeschreibung und Nachrichten. Option A: KI aus kostenlosem Kontingent (nur, wenn ein Key in den
Streamlit-Secrets liegt). Option B: Prompt fuer Claude kopieren und die Antwort einfuegen. Jede Einschaetzung
traegt ihre Quelle; die eigene Einschaetzung (Checkliste) ueberschreibt KI-Werte, Abweichungen werden markiert.
"""
import datetime
import html
import json
import re

import streamlit as st
import streamlit.components.v1 as components

import investor_config as C
import ki_anbieter as KI
from investor_checks import qualitativ as Q

P = "ql_"
QUELLE_CSS = {"berechnet": "q-b", "Textanalyse": "q-t", "KI": "q-k", "eigene Einschätzung": "q-e"}
CSS = """
<style>
.ql-q { display:inline-block; font-size:.7rem; font-weight:700; padding:1px 8px; border-radius:8px; margin:0 4px 4px 0;
  border:1px solid currentColor; white-space:nowrap; }
.ql-q.q-b { color:var(--accent,#7C9CFF); } .ql-q.q-t { color:#5EEAD4; } .ql-q.q-k { color:#A78BFA; }
.ql-q.q-e { color:#E5A50A; } .ql-q.q-y { color:var(--label,#A9ACB0); }
.ql-box { border:1px solid var(--glas-rand, rgba(255,255,255,.12)); border-radius:14px; padding:10px 14px;
  background:var(--surface-2,#191A1B); margin:6px 0 10px; }
.ql-warn { border-left:4px solid var(--neg,#F87171); }
.ql-abw { border-left:4px solid #E5A50A; }
.ql-m { color:var(--label,#A9ACB0); font-size:.84rem; }
.ql-zeile { display:grid; grid-template-columns:minmax(110px, 150px) 1fr 70px; gap:8px; align-items:center;
  font-size:.84rem; margin:3px 0; }
.ql-bahn { height:7px; border-radius:4px; background:rgba(127,127,127,.2); overflow:hidden; }
.ql-bahn > div { height:100%; border-radius:4px; background:var(--accent,#7C9CFF); }
.ql-bahn > div.hoch { background:var(--pos,#34D399); }
a.ql-link, .ql-box a, .ql-q + a { color:var(--accent,#7C9CFF) !important; text-decoration:underline; }
a.ql-knopf { display:inline-block; padding:10px 16px; border-radius:14px; text-decoration:none !important;
  border:1px solid var(--glas-rand, rgba(255,255,255,.2)); color:var(--text,#E8ECF6) !important; font-weight:600;
  margin:4px 0 8px; }
</style>
"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


def _q(text, art):
    return f'<span class="ql-q {art}">{_e(text)}</span>'


def _datei(symbol):
    return "state/qualitativ/werte/{}.json".format(re.sub(r"[^A-Za-z0-9.\-]", "_", symbol))


@st.cache_data(ttl=3600, show_spinner=False)
def _lade(_lesen, pfad, tag):
    return _lesen(pfad, None)


def _kopierknopf(text, schluessel):
    """Kopieren per Knopf - funktioniert auch auf iPhone/iPad (Clipboard-API, sonst Textauswahl + execCommand)."""
    daten = json.dumps(text)
    components.html(f"""
<button id="k" style="width:100%;min-height:48px;border-radius:14px;border:1px solid #4C6EF5;
 background:linear-gradient(135deg,#4C6EF5,#0D9488);color:#fff;font:600 16px -apple-system,
 Inter,sans-serif;cursor:pointer">📋 Prompt für Claude kopieren</button>
<div id="m" style="font:13px -apple-system,sans-serif;color:#7b8496;margin-top:6px;text-align:center"></div>
<script>
const t = {daten};
document.getElementById("k").addEventListener("click", async () => {{
  const m = document.getElementById("m");
  try {{ await navigator.clipboard.writeText(t); m.textContent = "Kopiert – jetzt in Claude einfügen."; return; }}
  catch (e) {{}}
  const a = document.createElement("textarea"); a.value = t; a.setAttribute("readonly", "");
  a.style.position = "fixed"; a.style.top = "0"; a.style.opacity = "0"; document.body.appendChild(a);
  a.focus(); a.setSelectionRange(0, t.length);
  const ok = document.execCommand("copy"); document.body.removeChild(a);
  m.textContent = ok ? "Kopiert – jetzt in Claude einfügen." : "Kopieren nicht möglich – bitte den Text unten markieren.";
}});
</script>""", height=90)


def _ki_anzeige(ki, titel):
    if not ki:
        return
    ff = ki.get("five_forces") or {}
    zeilen = [f"<b>Marktposition:</b> {_e(ki.get('marktposition'))}",
              f"<b>Alleinstellungsmerkmal:</b> {_e(ki.get('alleinstellungsmerkmal'))}",
              f"<b>Burggraben:</b> {_e(', '.join(ki.get('moat_typen') or []) or 'keiner')} · Trend "
              f"{_e(ki.get('moat_trend'))} · Disruptionsrisiko {_e(ki.get('disruptionsrisiko'))}",
              "<b>Five Forces:</b> " + " · ".join(f"{_e(k.replace('_', ' '))}: {_e(v)}" for k, v in ff.items()),
              "<b>Abhängigkeiten:</b> " + (_e(", ".join(ki.get("abhaengigkeiten") or [])) or "–"),
              f"<b>Begründung:</b> {_e(ki.get('begruendung'))}",
              f"<span class='ql-m'>Konfidenz {ki.get('konfidenz', 0) * 100:.0f} % · {_e(titel)} · "
              f"{_datum(ki.get('datum'))}</span>"]
    st.markdown(f"<div class='ql-box'>{_q(ki.get('quelle') or 'KI', 'q-k')}<br>" + "<br>".join(zeilen) + "</div>",
                unsafe_allow_html=True)
    st.caption("Automatisch erstellt, kann Fehler enthalten – keine Anlageberatung.")


def _kennzahlen_fuer_prompt(ergebnisse, f):
    aus = {}
    for r in ergebnisse:
        if r.get("score_0_100") is not None:
            aus[r["investor"]] = f"{r['erfuellt']} von {r['gesamt']} Kriterien erfüllt"
    j = (f.get("jahre") or [{}])[-1]
    if j.get("umsatz"):
        aus["Umsatz (letztes Jahr)"] = f"{j['umsatz'] / 1e9:.2f} Mrd. {f.get('waehrung') or ''}".replace(".", ",")
    return aus


def bereich(h, e, f, ergebnisse, notizen, speichern):
    """notizen: eigene Eintraege je Aktie; speichern(felder) legt Felder fuer diese Aktie ab."""
    st.markdown(CSS, unsafe_allow_html=True)
    sym = e.get("ticker") or e["id"]
    tag = datetime.date.today().isoformat()
    wert = _lade(h["gh_read_taeglich"], _datei(sym), tag) or {}
    meta = _lade(h["gh_read_taeglich"], "state/qualitativ/meta.json", tag) or {}
    eigen = notizen.get(sym) or {}
    us = (wert.get("quelle_text") == "10-K")

    # Quelle der Texte
    if us:
        sec = wert.get("sec") or {}
        st.markdown(f"{_q('SEC EDGAR', 'q-y')} {_e(sec.get('form'))} vom {_datum(sec.get('datum'))} · "
                    f"<a class='ql-link' href='{_e(sec.get('url'))}' target='_blank'>Dokument öffnen</a> · analysiert "
                    f"{_datum(wert.get('st'))}", unsafe_allow_html=True)
    elif wert:
        st.markdown(f"{_q('Nicht-US-Firma', 'q-y')} <span class='ql-m'>Kein 10-K – Auswertung nur aus Yahoo-"
                    f"Kurzbeschreibung und Wikidata (analysiert {_datum(wert.get('st'))}).</span>",
                    unsafe_allow_html=True)
    else:
        st.caption("Für diese Aktie liegt noch keine Vorberechnung vor (wöchentlich, größte Werte zuerst). "
                   "Beschreibung, Nachrichten und Option B funktionieren trotzdem.")

    # Moat-Score
    bf = next((r for r in ergebnisse if r["id"] == "buffett"), {})
    proxy = (bf.get("moat") or {}).get("punkte") if (bf.get("moat") or {}).get("stufe") != "n/a" else None
    peers = (((meta.get("peer") or {}).get(wert.get("quelle_text")) or {}).get(wert.get("sektor") or "")
             or (meta.get("alle") or {}).get(wert.get("quelle_text")) or {})
    t_score, betont, verh = Q.text_score(wert.get("dichte") or {}, peers)
    ki_liste = [k for k in (eigen.get("ki_claude"), eigen.get("ki_live"), wert.get("ki")) if k]
    ki = max(ki_liste, key=lambda k: str(k.get("datum") or "")) if ki_liste else None
    manuell = None
    if eigen.get("datum") and "burggraben" in (eigen.get("punkte") or {}):
        manuell = bool(eigen["punkte"]["burggraben"])
    m = Q.moat_score(proxy, t_score, ki, manuell)
    teile = m["teile"]
    teil_txt = " · ".join(f"{n} {v:.0f}" for n, v in (("Kennzahlen", teile["kennzahlen"]), ("Text", teile["text"]),
                                                      ("KI", teile["ki"])) if v is not None)
    quellen = "".join(_q(q.strip(), QUELLE_CSS.get(q.strip(), "q-k")) for q in (m["quelle"] or "").split("+"))
    score_txt = "n/a" if m["score"] is None else f"{m['score']:.0f} / 100"
    rahmen = "ql-abw" if m["abweichung"] else ""
    st.markdown(f"<div class='ql-box {rahmen}'><b>Burggraben-Score: {score_txt}</b><br>{quellen}"
                f"<div class='ql-m'>{_e(teil_txt)}" + (f" · berechnet {m['berechnet']:.0f}" if manuell is not None and
                                                       m.get("berechnet") is not None else "") + "</div>"
                + (f"<div><b>⚠️ Abweichung:</b> {_e(m['abweichung'])}</div>" if m["abweichung"] else "")
                + "</div>", unsafe_allow_html=True)

    # Grosskunden-Warnung
    for p, satz in wert.get("grosskunden") or []:
        st.markdown(f"<div class='ql-box ql-warn'><b>Großkunden-Abhängigkeit ({p:.0f} % des Umsatzes)</b><br>"
                    f"<span class='ql-m'>„{_e(satz[:300])}“ – {_q('10-K', 'q-y')}</span></div>",
                    unsafe_allow_html=True)

    with st.expander("Unternehmen, Textanalyse und Nachrichten"):
        if f.get("beschreibung"):
            st.markdown(f"{_q('Yahoo Finance', 'q-y')} {_e(f['beschreibung'][:1200])}"
                        + ("…" if len(f["beschreibung"]) > 1200 else ""), unsafe_allow_html=True)
        if f.get("mitarbeiter"):
            st.caption(f"Mitarbeiter: {f['mitarbeiter']:,.0f}".replace(",", "."))
        wd = wert.get("wikidata") or {}
        if wd:
            st.markdown(f"{_q('Wikidata', 'q-y')} Gründung: **{_e(wd.get('gruendung') or 'n/a')}** · "
                        f"Produkte: {_e(', '.join(wd.get('produkte') or []) or 'n/a')} · Tochterfirmen: "
                        f"{_e(', '.join((wd.get('toechter') or [])[:8]) or 'n/a')} · "
                        f"<a class='ql-link' href='https://www.wikidata.org/wiki/{_e(wd.get('qid'))}' "
                        "target='_blank'>Quelle</a>",
                        unsafe_allow_html=True)
        if wert.get("dichte"):
            st.markdown(f"**Textanalyse** {_q('Textanalyse', 'q-t')} <span class='ql-m'>Burggraben-Wörter je "
                        f"10.000 Wörter im Vergleich zum Sektor (1,0 = Sektor-Median) · Quelle: "
                        f"{_e(wert.get('quelle_text'))}</span>", unsafe_allow_html=True)
            zeilen = []
            for typ, d in sorted(wert["dichte"].items(), key=lambda kv: -(verh.get(kv[0]) or 0)):
                v = verh.get(typ)
                breite = 0 if v is None else min(100, v / 2 * 100)
                zeilen.append(f"<div class='ql-zeile'><span>{_e(typ)}</span><div class='ql-bahn'><div class='"
                              f"{'hoch' if typ in betont else ''}' style='width:{breite:.0f}%'></div></div>"
                              f"<span>{'n/a' if v is None else f'{v:.1f}×'.replace('.', ',')}</span></div>")
            st.markdown("".join(zeilen), unsafe_allow_html=True)
            if wert.get("risiko"):
                st.caption("Risiko-Wörter: " + ", ".join(f"„{k}“ ({n}×)" for k, n in wert["risiko"].items()))
        if f.get("news"):
            st.markdown(f"**Nachrichten** {_q('Yahoo Finance', 'q-y')}", unsafe_allow_html=True)
            for n in f["news"]:
                titel = (f"<a class='ql-link' href='{_e(n['link'])}' target='_blank'>{_e(n['titel'])}</a>"
                         if n["link"] else _e(n["titel"]))
                st.markdown(f"- {titel} <span class='ql-m'>{_e(n['quelle'])} · {_datum(n['datum'])}</span>",
                            unsafe_allow_html=True)

    # KI-Einschaetzung (neueste) + Abweichung zur eigenen Einschaetzung
    if ki:
        _ki_anzeige(ki, ki.get("modell") or "")
        if manuell is not None:
            ki_ja = any(t.lower() != "keiner" for t in ki.get("moat_typen") or [])
            if ki_ja != manuell:
                st.markdown(f"<div class='ql-box ql-abw'><b>Abweichung:</b> Deine Checkliste sagt Burggraben "
                            f"„{'ja' if manuell else 'nein'}“, die KI „{'ja' if ki_ja else 'nein'}“. Deine "
                            "Einschätzung gilt.</div>", unsafe_allow_html=True)

    texte = {"Geschäftsbeschreibung": (wert.get("auszuege") or {}).get("business") or f.get("beschreibung"),
             "Wettbewerb": (wert.get("auszuege") or {}).get("competition"),
             "Risikofaktoren": (wert.get("auszuege") or {}).get("risiken")}
    aktie = {"name": e["name"], "ticker": sym, "sektor": f.get("sektor") or e.get("sektor"),
             "branche": f.get("branche"), "land": f.get("land")}

    # Option A: kostenloses KI-Kontingent (nur mit Key in den Streamlit-Secrets)
    try:
        anbieter = KI.verfuegbar(st.secrets)
    except Exception:
        anbieter = None
    if anbieter:
        if st.button(f"Jetzt mit KI analysieren ({anbieter.titel}, kostenloses Kontingent)", key=P + "ki_" + sym):
            with st.spinner(f"Frage {anbieter.titel} …"):
                p = Q.prompt(aktie, _kennzahlen_fuer_prompt(ergebnisse, f), texte, C.KI[anbieter.name]["max_woerter"])
                erg, fehler = anbieter.analyse(p)
            if erg:
                erg["datum"] = datetime.date.today().isoformat()
                speichern({"ki_live": erg})
                st.rerun()
            st.warning(f"Keine gültige KI-Antwort ({fehler or 'Limit erreicht'}). Später erneut versuchen.")

    # Option B: Copy-Paste ueber das eigene Claude-Abo
    with st.expander("Mit Claude auswerten (dein Abo, Copy & Paste)"):
        p = Q.prompt(aktie, _kennzahlen_fuer_prompt(ergebnisse, f), texte)
        st.caption(f"1. Prompt kopieren ({len(p.split()):,} Wörter) · 2. in claude.ai einfügen · "
                   "3. Antwort hier einfügen und übernehmen.".replace(",", "."))
        _kopierknopf(p, sym)
        st.markdown("<a class='ql-knopf' href='https://claude.ai/new' target='_blank'>claude.ai öffnen ↗</a>",
                    unsafe_allow_html=True)
        if st.toggle("Prompt anzeigen", key=P + "zeigen_" + sym):
            st.code(p, language=None, wrap_lines=True)
        antwort = st.text_area("Claude-Antwort einfügen", key=P + "antwort_" + sym, height=140,
                               placeholder="Die komplette Antwort einfügen – auch mit ```json …``` oder Text drumherum.")
        if st.button("Antwort übernehmen", key=P + "uebernehmen_" + sym, type="primary"):
            obj, fehler = Q.pruefen(Q.json_aus_text(antwort))
            if obj:
                obj.update({"quelle": "KI (Claude manuell)", "datum": datetime.date.today().isoformat(),
                            "modell": "Claude (manuell)"})
                ok = speichern({"ki_claude": obj})
                st.success("Übernommen und gespeichert." if ok else "Übernommen (nur für diese Sitzung).")
                st.rerun()
            st.error("Die Antwort enthält kein gültiges JSON im verlangten Schema: " + "; ".join(fehler))
