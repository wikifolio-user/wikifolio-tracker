"""Gesundheit (nur Admin): Ernaehrung, Trinken, Gewicht und Tagesziel - so einfach wie moeglich.

Rechenkern ohne Streamlit im Paket gesundheit/ (getestet in test_gesundheit.py). Gespeichert wird im privaten
State-Repo (gesundheit/speicher.py): profil.json und je Monat eine Datei mit allen Tagen.
Prinzip: wenige Felder, sinnvolle Standardwerte, Details erst auf Wunsch (Ausklapper "Weitere Angaben").
Alle Werte sind rechnerische Schaetzungen zur Dokumentation - keine Diagnosen.

h (aus app.py): lesen(pfad, default) -> (daten, ok), aktualisiere(pfad, aendern, default, message) -> (ok, neu),
                upfad(pfad) -> Pfad des Benutzers, speichern (bool), get (requests.get fuer die Online-Suche)
"""
import datetime
import html
import logging
from zoneinfo import ZoneInfo

import streamlit as st

from gesundheit import fasten as FA
from gesundheit import lebensmittel as L
from gesundheit import mikro as MI
from gesundheit import naehrstoffe as N
from gesundheit import quellen as Q
from gesundheit import rechnen as R
from gesundheit import referenz as F
from gesundheit import speicher as S
from gesundheit import sport as SP
from gesundheit import supplements as SU

BERLIN = ZoneInfo("Europe/Berlin")
P = "gs_"
BEREICHE = ["Heute", "Essen", "Trinken", "Sport", "Fasten", "Supplements", "Nährstoffe", "Körper", "Profil"]
AUSBLENDBAR = {"Supplements": "supplements_zeigen", "Fasten": "fasten_zeigen"}     # Bereich -> Einstellung
HINWEIS = ("Alle Werte sind rechnerische Schätzungen zur Dokumentation. Sie ersetzen keine medizinische oder "
           "ernährungsmedizinische Beratung.")
WOCHENTAG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

CSS = """<style>
.st-key-gs_seite { --gs-balken: var(--accent, #7C9CFF); }
.gs-gruss { font-size: 1.35rem; font-weight: 700; color: var(--text, #E8ECF6); margin: 2px 0 2px; }
.gs-datum { font-size: .9rem; color: var(--label, #A9B1C4); margin-bottom: 6px; }
.gs-kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 6px 0 12px; }
.gs-kachel { padding: 12px 14px; border-radius: 16px; background: var(--karte, rgba(255,255,255,.05));
    border: 1px solid var(--rand, rgba(255,255,255,.12)); }
.gs-k-label { font-size: .74rem; font-weight: 650; letter-spacing: .06em; text-transform: uppercase;
    color: var(--label, #A9B1C4); }
.gs-k-wert { font-size: 1.25rem; font-weight: 700; color: var(--text, #E8ECF6); margin-top: 4px;
    font-variant-numeric: tabular-nums; line-height: 1.25; }
.gs-k-wert small { font-size: .85rem; font-weight: 600; color: var(--label, #A9B1C4); }
.gs-k-sub { font-size: .8rem; color: var(--label, #A9B1C4); margin-top: 4px; }
.gs-balken { height: 8px; border-radius: 99px; background: var(--rand, rgba(255,255,255,.12)); margin-top: 8px;
    overflow: hidden; }
.gs-balken > i { display: block; height: 100%; border-radius: 99px; background: var(--gs-balken); }
.gs-balken.ueber > i { background: var(--neg, #F87171); }
.gs-ziel { text-align: center; padding: 18px 12px; border-radius: 18px; margin: 8px 0 12px;
    background: var(--karte, rgba(255,255,255,.05)); border: 1px solid var(--rand, rgba(255,255,255,.12)); }
.gs-ziel b { display: block; font-size: 2rem; color: var(--text, #E8ECF6); font-variant-numeric: tabular-nums; }
.gs-ziel span { color: var(--label, #A9B1C4); font-size: .9rem; }
.gs-leer { padding: 14px; border-radius: 14px; border: 1px dashed var(--rand, rgba(255,255,255,.2));
    color: var(--label, #A9B1C4); text-align: center; margin: 6px 0; }
.gs-zeile { color: var(--text, #E8ECF6); font-size: .95rem; margin: 2px 0; }
.gs-zeile span { color: var(--label, #A9B1C4); }
.gs-vorschau { font-size: .92rem; color: var(--text, #E8ECF6); margin: 2px 0 8px; font-variant-numeric: tabular-nums; }
.gs-vorschau span { color: var(--label, #A9B1C4); }
/* grosse Tippflaechen, Knopfreihen umbrechen statt quetschen */
.st-key-gs_seite [data-testid="stButton"] button, .st-key-gs_seite [data-testid="stPopover"] button {
    min-height: 48px; }
.st-key-gs_seite [class*="st-key-gs_reihe"] { flex-wrap: wrap !important; gap: 8px !important; }
.st-key-gs_seite [class*="st-key-gs_reihe"] > div { flex: 1 1 140px !important; min-width: 0; }
.st-key-gs_seite [class*="st-key-gs_eintrag_"] button { justify-content: flex-start !important; text-align: left; }
.st-key-gs_tagleiste { max-width: 640px; }
.st-key-gs_seite [data-testid="stButtonGroup"] button { min-width: 48px; }
.st-key-gs_tagleiste [data-testid="stButton"] button { min-width: 48px; }
</style>"""


# ====================================================================== Daten
def _jetzt():
    return datetime.datetime.now(BERLIN)


def _heute():
    return _jetzt().date()


def _profil(h):
    s = st.session_state
    if P + "profil" not in s:
        daten, ok = h["lesen"](h["upfad"](S.PFAD_PROFIL), None)
        s[P + "profil"], s[P + "profil_ok"] = S.profil_doc(daten), ok
    return s[P + "profil"]


def _monat(h, tag):
    s = st.session_state
    monate = s.setdefault(P + "monate", {})
    k = tag.strftime("%Y-%m")
    if k not in monate:
        daten, ok = h["lesen"](h["upfad"](S.monat_pfad(tag)), None)
        monate[k] = daten if isinstance(daten, dict) else {}
        s.setdefault(P + "monat_ok", {})[k] = ok
    return monate[k]


def _melden(text, art="ok"):
    st.session_state[P + "meldung"] = (text, art)


def _schreiben(h, pfad, aendern, lokal_setzen, nachricht):
    """Aenderung speichern (Versionspruefung im Speicher) und die Sitzungskopie nachziehen. Ist der Speicher nicht
    erreichbar, gilt die Aenderung nur in dieser Sitzung (klar gemeldet) - es wird nichts ueberschrieben."""
    if h.get("speichern"):
        try:
            ok, neu = h["aktualisiere"](h["upfad"](pfad), aendern, {}, nachricht + " [skip ci]")
        except Exception as e:
            logging.warning(f"Gesundheit speichern: {type(e).__name__}")
            ok, neu = False, None
        if ok and isinstance(neu, dict):
            lokal_setzen(neu)
            return True
        _melden("Die Daten konnten gerade nicht gespeichert werden. Bitte versuche es erneut.", "fehler")
    lokal_setzen(aendern(_lokal_alt(pfad)))
    return False


def _lokal_alt(pfad):
    s = st.session_state
    if pfad == S.PFAD_PROFIL:
        return s.get(P + "profil")
    return (s.get(P + "monate") or {}).get(pfad.rsplit("/", 1)[-1][:-5])


def _profil_aendern(h, f, nachricht="gesundheit profil"):
    def setzen(neu):
        st.session_state[P + "profil"] = S.profil_doc(neu)
    return _schreiben(h, S.PFAD_PROFIL, lambda alt: f(S.profil_doc(alt)), setzen, nachricht)


def _tag_aendern(h, tag, f, nachricht="gesundheit tag"):
    k = tag.strftime("%Y-%m")

    def setzen(neu):
        st.session_state.setdefault(P + "monate", {})[k] = neu
    return _schreiben(h, S.monat_pfad(tag), lambda alt: f(alt if isinstance(alt, dict) else {}), setzen, nachricht)


def _alle_lebensmittel(doc):
    eigene = [lm for lm in doc.get("eigene") or [] if isinstance(lm, dict) and lm.get("id")]
    ids = {lm["id"] for lm in eigene}
    return eigene + [lm for lm in L.MITGELIEFERT if lm["id"] not in ids]


def _ziele(doc):
    return R.ziele(doc.get("profil"), _heute())


# ====================================================================== Formatierung
def _z(x, stellen=0):
    if x is None:
        return "–"
    t = f"{x:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return t


def _menge_text(menge, einheit):
    m = _z(menge, 0 if float(menge).is_integer() else 1)
    return f"{m} {einheit}"


def _kachel(label, wert, ziel, einheit, sub="", stellen=0, warnung=None):
    """Kachel mit Fortschrittsbalken. warnung: True/False erzwingt die Warnfarbe (rot); None = ueber 105 % des Ziels
    (sinnvoll fuer Kalorien, nicht fuer Vitamine - dort nur ueber dem oberen Referenzwert)."""
    anteil = (wert / ziel) if ziel else None
    balken = ""
    if anteil is not None:
        rot = (anteil > 1.05) if warnung is None else warnung
        balken = (f'<div class="gs-balken{" ueber" if rot else ""}" role="progressbar" '
                  f'aria-valuenow="{round(anteil * 100)}" aria-valuemin="0" aria-valuemax="100" '
                  f'aria-label="{html.escape(label)} {round(anteil * 100)} Prozent"><i style="width:'
                  f'{min(100, anteil * 100):.0f}%"></i></div>')
    ziel_txt = f" <small>/ {_z(ziel, stellen)} {einheit}</small>" if ziel else f" <small>{einheit}</small>"
    return (f'<div class="gs-kachel"><div class="gs-k-label">{html.escape(label)}</div>'
            f'<div class="gs-k-wert">{_z(wert, stellen)}{ziel_txt}</div>{balken}'
            + (f'<div class="gs-k-sub">{html.escape(sub)}</div>' if sub else "") + '</div>')


# ====================================================================== Rahmen
def seite(h):
    with st.container(key="gs_seite"):
        st.markdown(CSS, unsafe_allow_html=True)
        doc = _profil(h)
        if not st.session_state.get(P + "profil_ok", True):
            st.warning("Deine Gesundheitsdaten sind gerade nicht lesbar. Bitte lade die Seite gleich neu – "
                       "bis dahin wird nichts gespeichert, damit nichts überschrieben wird.")
            h = {**h, "speichern": False}
        if not S.eingerichtet(doc) or st.session_state.get(P + "einrichtung"):
            _einrichtung(h, doc)
            return
        _meldung_zeigen(h)
        s = st.session_state
        if s.get(P + "bereich_neu"):
            s[P + "bereich"] = s.pop(P + "bereich_neu")
        bereiche = [b for b in BEREICHE if doc["einstellungen"].get(AUSBLENDBAR.get(b, ""), True)]
        if s.get(P + "bereich") not in bereiche:
            s[P + "bereich"] = bereiche[0]
        bereich = st.segmented_control("Bereich", bereiche, key=P + "bereich", label_visibility="collapsed",
                                       width="stretch") or bereiche[0]
        if bereich != "Profil":
            _tag_leiste()
        {"Heute": _heute_seite, "Essen": _essen_seite, "Trinken": _trinken_seite, "Sport": _sport_seite,
         "Fasten": _fasten_seite, "Supplements": _supplement_seite,
         "Nährstoffe": _naehrstoff_seite, "Körper": _koerper_seite, "Profil": _profil_seite}[bereich](h, doc)
        st.caption(HINWEIS)


def _meldung_zeigen(h):
    s = st.session_state
    m = s.pop(P + "meldung", None)
    if m:
        (st.error if m[1] == "fehler" else st.toast)(m[0])
    u = s.get(P + "undo")
    if u:
        with st.container(key="gs_reihe_undo", horizontal=True, vertical_alignment="center"):
            st.markdown(f'<div class="gs-zeile">{html.escape(u["text"])}</div>', unsafe_allow_html=True)
            st.button("↶ Rückgängig", key=P + "undo_btn", on_click=_rueckgaengig, args=(h,))


def _rueckgaengig(h):
    u = st.session_state.pop(P + "undo", None)
    if u:
        _tag_aendern(h, u["tag"], lambda m: S.wiederherstellen(m, u["tag"], u["liste"], u["eintrag"]),
                     "gesundheit rückgängig")
        _melden("Wiederhergestellt")


def _tag():
    s = st.session_state
    t = s.get(P + "tag")
    if not isinstance(t, datetime.date):
        t = s[P + "tag"] = _heute()
    return t


def _tag_setzen(tag):
    st.session_state[P + "tag"] = tag
    st.session_state.pop(P + "undo", None)


def _tag_name(tag):
    d = (tag - _heute()).days
    return {0: "Heute", -1: "Gestern", 1: "Morgen"}.get(d, f"{WOCHENTAG[tag.weekday()][:2]}, {tag.strftime('%d.%m.%Y')}")


def _tag_leiste():
    tag = _tag()
    with st.container(key="gs_tagleiste", horizontal=True, vertical_alignment="center"):
        st.button("←", key=P + "tag_zurueck", on_click=_tag_setzen, args=(tag - datetime.timedelta(days=1),),
                  help="Vortag")
        st.button(_tag_name(tag) if tag != _heute() else "Heute", key=P + "tag_heute", width="stretch",
                  on_click=_tag_setzen, args=(_heute(),), help="Zurück zu heute",
                  type="primary" if tag == _heute() else "secondary")
        st.button("→", key=P + "tag_vor", on_click=_tag_setzen, args=(tag + datetime.timedelta(days=1),),
                  help="Nächster Tag", disabled=tag >= _heute() + datetime.timedelta(days=7))
        with st.popover("📅", help="Datum wählen"):
            st.date_input("Datum", value=tag, key=P + "tag_kalender", format="DD.MM.YYYY",
                          on_change=lambda: _tag_setzen(st.session_state[P + "tag_kalender"]))


def _neu_aufbauen():
    """Nach dem Speichern eines Formulars neu zeichnen - im Fragment nur das Fragment."""
    try:
        st.rerun(scope="fragment")
    except Exception:
        st.rerun()


def _zu(bereich):
    st.session_state[P + "bereich_neu"] = bereich


# ====================================================================== Einrichtung
def _einrichtung(h, doc):
    s = st.session_state
    schritt = s.setdefault(P + "schritt", 1)
    entwurf = s.setdefault(P + "entwurf", dict(doc.get("profil") or {}))
    st.markdown(f'<div class="gs-gruss">Gesundheit einrichten</div>'
                f'<div class="gs-datum">Schritt {schritt} von 4 · alles später änderbar</div>', unsafe_allow_html=True)

    def weiter(**werte):
        entwurf.update(werte)
        s[P + "schritt"] = schritt + 1

    if schritt == 1:
        st.subheader("Was möchtest du erreichen?")
        for k, text, _, _ in R.ZIELE:
            st.button(text, key=P + f"ob_ziel_{k}", width="stretch", on_click=weiter, kwargs={"ziel": k},
                      type="primary" if entwurf.get("ziel") == k else "secondary")
    elif schritt == 2:
        st.subheader("Ein paar Angaben zu dir")
        jahr = _heute().year
        alt = R.alter(entwurf.get("geburtsjahr")) or 35
        a = st.number_input("Alter (Jahre)", 14, 100, int(alt), key=P + "ob_alter")
        g = st.number_input("Größe (cm)", 120, 230, int(entwurf.get("groesse_cm") or 175), key=P + "ob_groesse")
        w = st.number_input("Gewicht (kg)", 35.0, 300.0, float(entwurf.get("gewicht_kg") or 75.0), 0.1,
                            format="%.1f", key=P + "ob_gewicht")
        opts = {"m": "Mann", "w": "Frau", "x": "Keine Angabe"}
        ge = st.radio("Berechnung als", list(opts), format_func=opts.get, horizontal=True, key=P + "ob_geschlecht",
                      index=list(opts).index(entwurf.get("geschlecht", "x")),
                      help="Nur für die Formel des Grundumsatzes. „Keine Angabe“ rechnet mit dem Mittelwert.")
        _ob_knoepfe(lambda: weiter(geburtsjahr=jahr - int(a), groesse_cm=int(g), gewicht_kg=round(float(w), 1),
                                   geschlecht=ge))
    elif schritt == 3:
        st.subheader("Wie aktiv bist du im Alltag?")
        for k, kurz, lang, _ in R.AKTIVITAET:
            st.button(f"{kurz} – {lang}", key=P + f"ob_akt_{k}", width="stretch", on_click=weiter,
                      kwargs={"aktivitaet": k}, type="primary" if entwurf.get("aktivitaet") == k else "secondary")
        st.button("← Zurück", key=P + "ob_zurueck3", on_click=lambda: s.update({P + "schritt": 2}))
    else:
        z = R.ziele(entwurf, _heute())
        st.markdown(f'<div class="gs-ziel"><span>Dein Tagesziel</span><b>{_z(z["kcal"])} kcal</b>'
                    f'<span>Protein {_z(z["protein"])} g · Wasser {_z((z["wasser_ml"] or 0) / 1000, 1)} L</span></div>',
                    unsafe_allow_html=True)
        with st.expander("So wird gerechnet"):
            _rechenweg(entwurf, z)
        c = st.columns(2)
        c[0].button("← Zurück", key=P + "ob_zurueck4", width="stretch", on_click=lambda: s.update({P + "schritt": 3}))
        c[1].button("Fertig – Gesundheit starten", key=P + "ob_fertig", type="primary", width="stretch",
                    on_click=_einrichtung_fertig, args=(h,))


def _ob_knoepfe(weiter):
    s = st.session_state
    c = st.columns(2)
    c[0].button("← Zurück", key=P + "ob_zurueck", width="stretch", on_click=lambda: s.update({P + "schritt": s[P + "schritt"] - 1}))
    c[1].button("Weiter →", key=P + "ob_weiter", type="primary", width="stretch", on_click=weiter)


def _einrichtung_fertig(h):
    s = st.session_state
    entwurf = dict(s.get(P + "entwurf") or {})
    _profil_aendern(h, lambda d: S.profil_setzen(d, entwurf, _jetzt()), "gesundheit einrichtung")
    for k in ("schritt", "entwurf", "einrichtung"):
        s.pop(P + k, None)
    s[P + "bereich_neu"] = "Heute"
    _melden("Fertig – viel Erfolg!")


def _rechenweg(profil, z):
    akt = next((f"{kurz} (× {f:g})" for k, kurz, _, f in R.AKTIVITAET if k == profil.get("aktivitaet")), "–")
    delta = R.ZIEL_KCAL.get(profil.get("ziel"), 0)
    st.markdown(
        f"- **Grundumsatz:** {_z(z['bmr'])} kcal – was dein Körper in völliger Ruhe braucht "
        f"(Formel nach Mifflin-St Jeor aus Alter, Größe, Gewicht).\n"
        f"- **Tagesbedarf:** {_z(z['tdee'])} kcal – Grundumsatz × Aktivität {akt}.\n"
        f"- **Ziel:** {'+' if delta > 0 else ''}{_z(delta)} kcal je Tag"
        + (" (≈ 0,5 kg pro Woche)" if delta == -500 else "") + f" → **{_z(z['kcal'])} kcal**"
        + (f" (nie unter {_z(R.KCAL_MINIMUM)} kcal)" if delta < 0 else "") + ".\n"
        f"- **Protein:** {_z(R.ZIEL_PROTEIN.get(profil.get('ziel'), 1.4), 1)} g je kg Körpergewicht · "
        f"**Fett:** 30 % der Kalorien · **Kohlenhydrate:** der Rest · **Wasser:** 35 ml je kg (1,5–3,5 L).")


# ====================================================================== Heute
def _gruss():
    hh = _jetzt().hour
    return "Guten Morgen" if hh < 11 else "Guten Tag" if hh < 18 else "Guten Abend"


def _heute_seite(h, doc):
    tag = _tag()
    t = S.tag_aus(_monat(h, tag), tag)
    su = S.tag_summen(t)
    z = _ziele(doc)
    n = su["naehrwerte"]
    sport_kcal, sport_min = SP.summe(t)
    b = R.bilanz(z["kcal"], z["tdee"], su["kcal"], sport_kcal, doc["einstellungen"].get("sport_zusaetzlich"))
    if tag == _heute():
        st.markdown(f'<div class="gs-gruss">{_gruss()}</div>', unsafe_allow_html=True)
    rest = b["verbleibend"]
    kacheln = [
        _kachel("Kalorien", su["kcal"], z["kcal"], "kcal",
                f"noch {_z(rest)} kcal" if rest >= 0 else f"{_z(-rest)} kcal über dem Ziel"),
        _kachel("Protein", n["protein"]["wert"], z["protein"], "g"),
        _kachel("Wasser", su["fluessigkeit_ml"] / 1000, (z["wasser_ml"] or 0) / 1000, "L", stellen=1),
        _kachel("Kohlenhydrate", n["kh"]["wert"], z["kh"], "g"),
        _kachel("Fett", n["fett"]["wert"], z["fett"], "g"),
    ]
    plan = _sup_plan(doc, tag)
    if plan:
        geplant = [x for l in plan.values() for x in l]
        genommen = _einnahmen(t)
        n_ein = sum(1 for x in geplant if (genommen.get(x["id"]) or {}).get("status") == "eingenommen")
        kacheln.append(_kachel("Supplements", n_ein, len(geplant), "", "eingenommen"))
    if sport_kcal or sport_min:
        kacheln.append(_kachel("Sport", sport_kcal, None, "kcal", f"{_z(sport_min)} Minuten"
                               + ("" if doc["einstellungen"].get("sport_zusaetzlich") else " · im Tagesbedarf enthalten")))
    fa = FA.status(FA.zustand(doc)["laeuft"], _jetzt()) if doc["einstellungen"].get("fasten_zeigen", True) else None
    if fa:
        kacheln.append(_kachel("Fasten", fa["dauer_h"], fa["ziel_h"], "h",
                               "Ziel erreicht" if fa["erreicht"] else f"bis {fa['ende_geplant'].strftime('%H:%M')} Uhr",
                               stellen=1, warnung=False))
    if b["bilanz"] is not None and su["kcal"] > 0:
        kacheln.append(_kachel("Bilanz bisher", b["bilanz"], None, "kcal",
                               ("Defizit" if b["bilanz"] < 0 else "Überschuss") + f" · Bedarf {_z(z['tdee'])} kcal"))
    st.markdown('<div class="gs-kacheln">' + "".join(kacheln) + "</div>", unsafe_allow_html=True)

    st.markdown("**Was möchtest du eintragen?**")
    with st.container(key="gs_reihe_schnell", horizontal=True):
        st.button("＋ Essen", key=P + "q_essen", on_click=_zu, args=("Essen",), type="primary")
        for i, (name, ml) in enumerate(_wasser_knoepfe(doc)[:3]):
            st.button(f"💧 {name}", key=P + f"q_wasser_{i}", on_click=_trinken, args=(h, tag, "wasser", ml),
                      help=f"{_z(ml)} ml Wasser hinzufügen")
        if doc["einstellungen"].get("supplements_zeigen", True):
            st.button("💊 Supplements", key=P + "q_sup", on_click=_zu, args=("Supplements",))
        st.button("🏃 Sport", key=P + "q_sport", on_click=_zu, args=("Sport",))
        st.button("⚖️ Gewicht", key=P + "q_gewicht", on_click=_zu, args=("Körper",))
        if doc["einstellungen"].get("fasten_zeigen", True):
            if FA.zustand(doc)["laeuft"]:
                st.button("⏹ Fasten beenden", key=P + "q_fasten", on_click=_fasten_beenden, args=(h,))
            else:
                st.button("⏱ Fasten starten", key=P + "q_fasten", on_click=_fasten_starten, args=(h, doc))

    st.markdown("**Gegessen**")
    if not t["essen"]:
        st.markdown('<div class="gs-leer">Noch keine Mahlzeiten eingetragen</div>', unsafe_allow_html=True)
        st.button("＋ Erste Mahlzeit hinzufügen", key=P + "leer_essen", on_click=_zu, args=("Essen",), width="stretch")
    else:
        for m in _mahlzeiten(doc, t):
            posten = [e for e in t["essen"] if _mahlzeit_von(e, doc) == m]
            if posten:
                namen = ", ".join(e["name"] for e in posten[:4]) + (" …" if len(posten) > 4 else "")
                st.markdown(f'<div class="gs-zeile"><b>{m}</b> · {_z(su["mahlzeiten"].get(m, 0))} kcal '
                            f'<span>– {html.escape(namen)}</span></div>', unsafe_allow_html=True)
    if t["trinken"]:
        st.markdown(f'<div class="gs-zeile"><b>Getränke</b> · {_z(sum(x["ml"] for x in t["trinken"]))} ml '
                    f'<span>({len(t["trinken"])} ×)</span></div>', unsafe_allow_html=True)
    if t.get("gewicht"):
        st.markdown(f'<div class="gs-zeile"><b>Gewicht</b> · {_z(t["gewicht"], 1)} kg</div>', unsafe_allow_html=True)
    for x in t.get("sport") or []:
        st.markdown(f'<div class="gs-zeile"><b>{html.escape(x["name"])}</b> · {_z(x["minuten"])} min · '
                    f'{_z(x["kcal"])} kcal</div>', unsafe_allow_html=True)
    for dauer, ziel_h, ok in FA.am_tag(FA.zustand(doc)["verlauf"], tag):
        st.markdown(f'<div class="gs-zeile"><b>Fasten</b> · {FA.dauer_text(dauer)} '
                    f'<span>({"Ziel erreicht" if ok else f"Ziel {_z(ziel_h)} h"})</span></div>', unsafe_allow_html=True)


def _wasser_knoepfe(doc):
    eigene = [(g.get("name") or "Glas", float(g.get("ml") or 0)) for g in doc["einstellungen"].get("glaeser") or []
              if float(g.get("ml") or 0) > 0]
    return [("250 ml", 250.0), ("500 ml", 500.0)] + eigene


def _trinken(h, tag, art, ml):
    _tag_aendern(h, tag, lambda m: S.trinken_hinzu(m, tag, art, ml, _jetzt()), "gesundheit trinken")
    _melden(f"{S.GETRAENK_NAME.get(art, 'Getränk')} {_z(ml)} ml eingetragen")


# ====================================================================== Essen
def _essen_seite(h, doc):
    tag = _tag()
    s = st.session_state
    alle = _alle_lebensmittel(doc)
    extra = s.setdefault(P + "online", {})           # Online-Treffer dieser Sitzung (id -> Lebensmittel)
    nach_id = {**{lm["id"]: lm for lm in alle}, **extra}
    nutzung, fav = doc.get("nutzung") or {}, doc.get("favoriten") or []

    vorlagen = doc.get("vorlagen") or []
    if vorlagen:
        st.markdown("**Mahlzeiten-Vorlagen**")
        with st.container(key="gs_reihe_vorlagen", horizontal=True):
            for v in vorlagen:
                st.button(f"＋ {v['name']}", key=P + f"vl_{v['id']}", on_click=_vorlage_einfuegen, args=(h, tag, v),
                          help=", ".join(e.get("name", "") for e in v.get("eintraege") or []))
    vorschlaege = L.suchen("", alle, nutzung, fav, limit=8)
    if vorschlaege:
        st.markdown("**Favoriten & zuletzt**")
        with st.container(key="gs_reihe_vorschlag", horizontal=True):
            for lm in vorschlaege:
                st.button(("★ " if lm["id"] in fav else "") + lm["name"], key=P + f"vor_{lm['id']}",
                          on_click=lambda i=lm["id"]: s.update({P + "wahl": i}))
    # Auswahlliste mit Sofort-Suche beim Tippen: Favoriten und haeufige zuerst
    rang = {lm["id"]: i for i, lm in enumerate(L.suchen("", alle, nutzung, fav, limit=500))}
    optionen = sorted(nach_id, key=lambda i: (rang.get(i, 10_000), nach_id[i]["name"].lower()))
    if s.get(P + "wahl") not in nach_id:
        s[P + "wahl"] = None                          # Startwert ueber den Sitzungszustand (kein index=)
    wahl = st.selectbox("Lebensmittel", optionen, key=P + "wahl", placeholder="🔍 Lebensmittel suchen …",
                        format_func=lambda i: ("★ " if i in fav else "") + nach_id[i]["name"]
                        + (f" ({nach_id[i]['marke']})" if nach_id[i].get("marke") else ""),
                        label_visibility="collapsed")
    if wahl:
        _erfassen(h, doc, nach_id[wahl], tag)
    else:
        _nicht_gefunden(h, doc)

    st.divider()
    t = S.tag_aus(_monat(h, tag), tag)
    _tagebuch(h, doc, tag, t)
    gestern = tag - datetime.timedelta(days=1)
    t_gestern = S.tag_aus(_monat(h, gestern), gestern)
    if t_gestern["essen"]:
        st.button(f"⧉ Gestern übernehmen ({len(t_gestern['essen'])} Einträge)", key=P + "gestern", width="stretch",
                  on_click=_gestern_kopieren, args=(h, tag, t_gestern["essen"]),
                  help="Alle Einträge vom Vortag für diesen Tag übernehmen")


def _erfassen(h, doc, lm, tag):
    s = st.session_state
    u = (doc.get("nutzung") or {}).get(lm["id"]) or {}
    einheiten = L.einheiten(lm)
    start_menge, start_einheit = (u["menge"], u["einheit"]) if u.get("einheit") in einheiten else L.standard_menge(lm)
    k = P + "e_" + lm["id"].replace(":", "_")
    with st.container(border=True, key="gs_erfassen"):
        c = st.columns([1, 1])
        ein = c[1].selectbox("Einheit", einheiten, index=einheiten.index(start_einheit), key=k + "_einheit")
        stueckig = ein not in ("g", "ml")
        menge = c[0].number_input("Menge", min_value=0.0, max_value=5000.0,
                                  value=float(start_menge if ein == start_einheit else (1.0 if stueckig else 100.0)),
                                  step=0.5 if stueckig else 10.0, format="%g", key=k + f"_menge_{ein}")
        g = R.gramm(menge, ein, lm.get("einheiten"))
        nw = R.naehrwerte(lm.get("pro100"), g)
        if g:
            st.markdown(f'<div class="gs-vorschau"><b>{_z(nw.get("kcal"))} kcal</b> · Protein {_z(nw.get("protein"), 1)} g · '
                        f'KH {_z(nw.get("kh"), 1)} g · Fett {_z(nw.get("fett"), 1)} g'
                        + (f' <span>({_z(g)} {lm.get("basis", "g")})</span>' if stueckig else "") + '</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="gs-vorschau"><span>Bitte gib eine gültige Menge ein.</span></div>',
                        unsafe_allow_html=True)
        mahlzeit_std = R.mahlzeit_vorschlag(_jetzt().time()) if tag == _heute() else s.get(P + "letzte_mahlzeit", "Mittagessen")
        with st.expander("Weitere Angaben"):
            mz = _mahlzeiten(doc)
            st.selectbox("Mahlzeit", mz, index=mz.index(mahlzeit_std) if mahlzeit_std in mz else 0, key=k + "_mahlzeit")
            fav = lm["id"] in (doc.get("favoriten") or [])
            st.button("★ Aus Favoriten entfernen" if fav else "☆ Als Favorit merken", key=k + "_fav",
                      on_click=lambda: _profil_aendern(h, lambda d: S.favorit_umschalten(d, lm["id"]), "gesundheit favorit"))
            herkunft = lm.get("quelle") or "Richtwert"
            st.caption(f"Quelle: {herkunft}" + (f" · {lm['marke']}" if lm.get("marke") else "")
                       + " · Nährwerte je 100 " + (lm.get("basis") or "g") + ": "
                       + ", ".join(f"{_z(v, 1)} {'kcal' if n == 'kcal' else 'g'} {n.replace('kh', 'KH')}"
                                   for n, v in (lm.get("pro100") or {}).items() if n in ("kcal", "protein", "kh", "fett")))
            if (lm.get("pro100") or {}).get("kcal"):
                ziel_kcal = st.number_input("Umrechnen: Wie viel ergibt … kcal?", 0, 5000, 300, 50, key=k + "_rueck")
                st.markdown(f'<div class="gs-vorschau">{_z(ziel_kcal)} kcal ≙ '
                            f'<b>{_z(R.menge_fuer_kcal(lm["pro100"], ziel_kcal))} {lm.get("basis", "g")}</b></div>',
                            unsafe_allow_html=True)
        st.button("Speichern", key=P + "speichern_essen", type="primary", width="stretch", disabled=not g,
                  on_click=_essen_speichern, args=(h, lm, k, tag))


def _essen_speichern(h, lm, k, tag):
    """Werte aus dem Sitzungszustand lesen (nicht vom letzten Seitenaufbau): wer eine Menge tippt und sofort
    "Speichern" antippt, bekommt genau die getippte Menge."""
    s = st.session_state
    einheit = s.get(k + "_einheit")
    menge = s.get(k + f"_menge_{einheit}")
    mahlzeit = s.get(k + "_mahlzeit") or (R.mahlzeit_vorschlag(_jetzt().time()) if tag == _heute()
                                          else s.get(P + "letzte_mahlzeit", "Mittagessen"))
    e = S.essen_eintrag(lm, menge, einheit, mahlzeit, _jetzt())
    if e is None:
        _melden("Bitte gib eine gültige Menge ein.", "fehler")
        return
    _tag_aendern(h, tag, lambda m: S.essen_hinzu(m, tag, [e]), "gesundheit essen")

    def merken(d):
        d = S.nutzung_merken(d, lm["id"], menge, einheit, _jetzt())
        if lm.get("quelle") == "Open Food Facts" and all(x.get("id") != lm["id"] for x in d["eigene"]):
            d["eigene"] = d["eigene"] + [lm]                 # Online-Produkt fuer die naechste Suche behalten
        return d
    _profil_aendern(h, merken, "gesundheit nutzung")
    s[P + "letzte_mahlzeit"] = mahlzeit
    s[P + "wahl"] = None
    _melden(f"{lm['name']} gespeichert · {_z(S.eintrag_naehrwerte(e).get('kcal'))} kcal")


def _nicht_gefunden(h, doc):
    with st.expander("Nicht gefunden?"):
        st.caption("Produkt in der freien Lebensmitteldatenbank Open Food Facts suchen – mit Herstellerangaben.")
        begriff = st.text_input("Produkt suchen", key=P + "online_begriff", placeholder="z. B. Skyr, Müsliriegel …")
        if begriff and len(begriff.strip()) >= 2:
            treffer, fehler = _online_suchen(begriff.strip(), h)
            if fehler:
                st.warning(fehler)
            elif not treffer:
                st.info("Nichts gefunden. Anders schreiben oder ein eigenes Lebensmittel anlegen.")
            for lm in treffer[:10]:
                st.button(f"{lm['name']}" + (f" · {lm['marke']}" if lm.get("marke") else "")
                          + f" · {_z(lm['pro100'].get('kcal'))} kcal/100 {lm['basis']}", key=P + f"on_{lm['id']}",
                          width="stretch", on_click=_online_waehlen, args=(lm,))
    with st.expander("Eigenes Lebensmittel anlegen"):
        _eigenes_formular(h)


@st.cache_data(ttl=24 * 3600, show_spinner="Suche …")
def _online_cache(begriff, _get):
    return Q.off_suchen(begriff, _get)


def _online_suchen(begriff, h):
    get = h.get("get")
    if not get:
        return [], "Die Online-Suche ist hier nicht verfügbar."
    return _online_cache(begriff.lower(), get)


def _online_waehlen(lm):
    s = st.session_state
    s.setdefault(P + "online", {})[lm["id"]] = lm
    s[P + "wahl"] = lm["id"]


def _eigenes_formular(h):
    with st.form(P + "eigenes_form", clear_on_submit=True, border=False):
        name = st.text_input("Name", placeholder="z. B. Omas Apfelkuchen")
        c = st.columns(2)
        basis = c[0].selectbox("Angaben je 100", ["g", "ml"])
        kcal = c[1].number_input("Kalorien (kcal)", 0.0, 1000.0, None, 1.0, placeholder="Pflicht")
        c = st.columns(2)
        protein = c[0].number_input("Protein (g)", 0.0, 100.0, None, 0.1)
        kh = c[1].number_input("Kohlenhydrate (g)", 0.0, 100.0, None, 0.1)
        c = st.columns(2)
        fett = c[0].number_input("Fett (g)", 0.0, 100.0, None, 0.1)
        portion = c[1].number_input("Eine Portion wiegt (g/ml)", 0.0, 2000.0, None, 1.0,
                                    help="Optional – dann kannst du in Portionen eintragen.")
        if st.form_submit_button("Lebensmittel speichern", type="primary", width="stretch"):
            if not name.strip() or kcal is None:
                st.error("Bitte gib mindestens einen Namen und die Kalorien ein.")
                return
            lm = {"id": "eigen:" + S.neue_id(), "name": name.strip()[:80], "kategorie": "Eigene", "basis": basis,
                  "pro100": {k: v for k, v in {"kcal": kcal, "protein": protein, "kh": kh, "fett": fett}.items()
                             if v is not None},
                  "einheiten": {"Portion": portion} if portion else {}, "quelle": "eigen", "marke": "", "such": ""}
            _profil_aendern(h, lambda d: {**d, "eigene": d["eigene"] + [lm]}, "gesundheit eigenes lebensmittel")
            st.session_state[P + "wahl"] = lm["id"]
            _melden(f"{lm['name']} angelegt")
            _neu_aufbauen()


def _mahlzeiten(doc, t=None):
    """Mahlzeit-Kategorien des Benutzers (Einstellungen); Eintraege mit einer nicht (mehr) vorhandenen Kategorie
    erscheinen unter ihrer eigenen Bezeichnung am Ende."""
    eigene = [m for m in doc["einstellungen"].get("mahlzeiten") or S.MAHLZEITEN if m] or list(S.MAHLZEITEN)
    extra = []
    for e in (t or {}).get("essen") or []:
        m = e.get("mahlzeit") or "Snacks"
        if m not in eigene and m not in extra:
            extra.append(m)
    return eigene + extra


def _mahlzeit_von(e, doc):
    return e.get("mahlzeit") or "Snacks"


def _tagebuch(h, doc, tag, t):
    su = S.tag_summen(t)
    if not t["essen"]:
        st.markdown('<div class="gs-leer">Noch nichts eingetragen – oben ein Lebensmittel suchen.</div>',
                    unsafe_allow_html=True)
        return
    st.markdown(f"**{_tag_name(tag)}: {_z(su['naehrwerte']['kcal']['wert'])} kcal gegessen**")
    for i, m in enumerate(_mahlzeiten(doc, t)):
        posten = [e for e in t["essen"] if _mahlzeit_von(e, doc) == m]
        if not posten:
            continue
        with st.expander(f"{m} · {_z(su['mahlzeiten'].get(m, 0))} kcal", expanded=True):
            for e in posten:
                _eintrag(h, doc, tag, e)
            with st.container(key=f"gs_reihe_mahl_{i}", horizontal=True):
                with st.popover("☆ Als Vorlage merken", help="Diese Mahlzeit später mit einem Tipp eintragen"):
                    st.text_input("Name der Vorlage", m, key=P + f"vl_name_{i}", max_chars=40)
                    st.button("Vorlage speichern", key=P + f"vl_sp_{i}", type="primary",
                              on_click=lambda n=P + f"vl_name_{i}", p=posten: _vorlage_speichern(
                                  h, st.session_state.get(n) or "Vorlage", p))
                if tag != _heute():
                    st.button("⧉ Auf heute kopieren", key=P + f"mahl_kopie_{i}", on_click=_auf_heute_kopieren,
                              args=(h, posten))


def _eintrag(h, doc, tag, e):
    nw = S.eintrag_naehrwerte(e)
    k = P + "eintrag_" + e["id"]
    with st.container(key="gs_eintrag_" + e["id"]):
        with st.popover(f"{e['name']} · {_menge_text(e['menge'], e['einheit'])} · {_z(nw.get('kcal'))} kcal",
                        width="stretch"):
            stueckig = e["einheit"] not in ("g", "ml")
            st.number_input("Menge", 0.0, 5000.0, float(e["menge"]), 0.5 if stueckig else 10.0, format="%g",
                                    key=k + "_m", help=f"in {e['einheit']}")
            mz = _mahlzeiten(doc, {"essen": [e]})
            st.selectbox("Mahlzeit", mz, index=mz.index(_mahlzeit_von(e, doc)), key=k + "_mz")
            c = st.columns(2)
            c[0].button("Übernehmen", key=k + "_ok", type="primary", width="stretch",
                        on_click=_menge_uebernehmen, args=(h, tag, e["id"], k))
            c[1].button("🗑 Entfernen", key=k + "_weg", width="stretch", on_click=_entfernen,
                        args=(h, tag, "essen", e["id"], e["name"]))


def _menge_uebernehmen(h, tag, eid, k):
    s = st.session_state
    menge, mahl = s.get(k + "_m"), s.get(k + "_mz")
    _tag_aendern(h, tag, lambda m: S.essen_menge(m, tag, eid, menge, None, mahl), "gesundheit menge")
    _melden("Geändert")


def _entfernen(h, tag, liste, eid, name):
    box = {}

    def f(m):
        neu, weg = S.entfernen(m, tag, liste, eid)
        box["weg"] = weg or box.get("weg")
        return neu
    _tag_aendern(h, tag, f, "gesundheit entfernen")
    if box.get("weg"):
        st.session_state[P + "undo"] = {"tag": tag, "liste": liste, "eintrag": box["weg"], "text": f"{name} entfernt"}


def _vorlage_speichern(h, name, eintraege):
    _profil_aendern(h, lambda d: S.vorlage_speichern(d, name.strip()[:40], eintraege, "vl:" + S.neue_id()),
                    "gesundheit vorlage")
    _melden(f"Vorlage „{name.strip()[:40]}“ gespeichert")


def _vorlage_einfuegen(h, tag, v):
    kopie = S.kopieren(v.get("eintraege") or [], _jetzt())
    _tag_aendern(h, tag, lambda m: S.essen_hinzu(m, tag, kopie), "gesundheit vorlage eingetragen")
    _melden(f"{v['name']} eingetragen ({len(kopie)} Lebensmittel)")


def _auf_heute_kopieren(h, eintraege):
    heute = _heute()
    kopie = S.kopieren(eintraege, _jetzt())
    _tag_aendern(h, heute, lambda m: S.essen_hinzu(m, heute, kopie), "gesundheit mahlzeit kopiert")
    _melden(f"{len(kopie)} Einträge auf heute kopiert")


def _gestern_kopieren(h, tag, eintraege):
    kopie = S.kopieren(eintraege, _jetzt())
    _tag_aendern(h, tag, lambda m: S.essen_hinzu(m, tag, kopie), "gesundheit gestern kopiert")
    _melden(f"{len(kopie)} Einträge übernommen")


# ====================================================================== Trinken
def _trinken_seite(h, doc):
    tag = _tag()
    s = st.session_state
    t = S.tag_aus(_monat(h, tag), tag)
    su = S.tag_summen(t)
    ziel = _ziele(doc)["wasser_ml"]
    st.markdown('<div class="gs-kacheln">' + _kachel("Getrunken", su["fluessigkeit_ml"] / 1000, (ziel or 0) / 1000, "L",
                                                      stellen=1) + "</div>", unsafe_allow_html=True)
    s.setdefault(P + "getraenk", "wasser")
    art = st.pills("Getränk", [a for a, _, _ in S.GETRAENKE], format_func=S.GETRAENK_NAME.get, key=P + "getraenk",
                   label_visibility="collapsed") or "wasser"
    with st.container(key="gs_reihe_trinken", horizontal=True):
        for i, (name, ml) in enumerate(_wasser_knoepfe(doc)):
            st.button(f"＋ {name}" + (f" ({_z(ml)} ml)" if not name.endswith("ml") else ""), key=P + f"tr_{i}",
                      on_click=_trinken, args=(h, tag, art, ml), type="primary" if i == 0 else "secondary")
    with st.expander("Andere Menge"):
        c = st.columns(2)
        c[0].number_input("Menge (ml)", 0, 3000, 330, 10, key=P + "tr_ml")
        c[1].button("Hinzufügen", key=P + "tr_eigene", width="stretch",
                    on_click=lambda: _trinken(h, tag, st.session_state.get(P + "getraenk") or "wasser",
                                              st.session_state.get(P + "tr_ml") or 0))
    if t["trinken"]:
        st.markdown(f"**{_tag_name(tag)} getrunken**")
        for x in reversed(t["trinken"]):
            with st.container(key=f"gs_reihe_tr_{x['id']}", horizontal=True, vertical_alignment="center"):
                st.markdown(f'<div class="gs-zeile">{x.get("zeit", "")} · {S.GETRAENK_NAME.get(x.get("art"), "Getränk")} '
                            f'<b>{_z(x["ml"])} ml</b></div>', unsafe_allow_html=True)
                st.button("🗑", key=P + f"tr_weg_{x['id']}", help="Entfernen", on_click=_entfernen,
                          args=(h, tag, "trinken", x["id"], f"{S.GETRAENK_NAME.get(x.get('art'), 'Getränk')} {_z(x['ml'])} ml"))
    else:
        st.markdown('<div class="gs-leer">Noch nichts getrunken – ein Tipp auf einen Knopf oben genügt.</div>',
                    unsafe_allow_html=True)


# ====================================================================== Koerper
def _koerper_seite(h, doc):
    tag = _tag()
    t = S.tag_aus(_monat(h, tag), tag)
    profil = doc.get("profil") or {}
    letzt = t.get("gewicht") or profil.get("gewicht_kg") or 75.0
    st.markdown(f"**Gewicht {_tag_name(tag).lower() if tag != _heute() else 'heute'}**")
    with st.container(key="gs_reihe_gewicht", horizontal=True, vertical_alignment="bottom"):
        kg = st.number_input("Gewicht (kg)", 30.0, 300.0, float(letzt), 0.1, format="%.1f", key=P + f"kg_{tag}",
                             label_visibility="collapsed")
        st.button("Speichern", key=P + "kg_speichern", type="primary",
                  on_click=lambda: _gewicht_speichern(h, tag, st.session_state.get(P + f"kg_{tag}") or kg))
    if t.get("gewicht"):
        st.caption(f"Eingetragen: {_z(t['gewicht'], 1)} kg")
    # Verlauf: die letzten 6 Monate
    monate = []
    erster = _heute().replace(day=1)
    for i in range(6):
        y, m = divmod(erster.month - 1 - i, 12)
        monate.append(_monat(h, datetime.date(erster.year + y, m + 1, 1)))
    werte = S.gewichte(monate)
    ziel = profil.get("zielgewicht_kg")
    if len(werte) >= 2:
        import plotly.graph_objects as go
        fig = go.Figure(go.Scatter(x=[d for d, _ in werte], y=[w for _, w in werte], mode="lines+markers",
                                   line={"color": "#7C9CFF", "width": 3}, name="Gewicht",
                                   hovertemplate="%{x|%d.%m.%Y}: %{y:.1f} kg<extra></extra>"))
        if ziel:
            fig.add_hline(y=ziel, line_dash="dot", line_color="#5EEAD4", annotation_text="Ziel")
        fig.update_layout(height=260, margin={"l": 10, "r": 10, "t": 10, "b": 10}, showlegend=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          yaxis={"title": "kg", "ticksuffix": ""}, xaxis={"tickformat": "%d.%m."})
        st.plotly_chart(fig, config={"displayModeBar": False}, key=P + "kg_chart")
        diff = werte[-1][1] - werte[0][1]
        st.markdown(f'<div class="gs-zeile">Seit {werte[0][0].strftime("%d.%m.")}: '
                    f'<b>{"+" if diff > 0 else ""}{_z(diff, 1)} kg</b>'
                    + (f' <span>· noch {_z(abs(werte[-1][1] - ziel), 1)} kg bis zum Ziel</span>' if ziel else "")
                    + '</div>', unsafe_allow_html=True)
    elif not werte:
        st.markdown('<div class="gs-leer">Noch kein Gewicht eingetragen – oben eintragen und speichern.</div>',
                    unsafe_allow_html=True)
    _masse_bereich(h, t, tag, monate)


def _masse_bereich(h, t, tag, monate):
    masse = t.get("masse") or {}
    with st.expander("Weitere Körpermaße" + (f" ({len(masse)} eingetragen)" if masse else "")):
        with st.form(P + f"masse_{tag}", border=False):
            werte = {}
            for i in range(0, len(S.MASSE), 2):
                c = st.columns(2)
                for j, (k, name, einheit) in enumerate(S.MASSE[i:i + 2]):
                    werte[k] = c[j].number_input(f"{name} ({einheit})", 0.0, 300.0, float(masse.get(k) or 0), 0.1,
                                                 format="%.1f", help="0 = nicht erfasst")
            if st.form_submit_button("Körpermaße speichern", width="stretch"):
                _tag_aendern(h, tag, lambda m: S.masse_setzen(m, tag, werte), "gesundheit koerpermasse")
                _melden("Körpermaße gespeichert")
                _neu_aufbauen()
        mit_werten = [(k, n, e) for k, n, e in S.MASSE if len(S.mass_verlauf(monate, k)) >= 2]
        if mit_werten:
            k = st.selectbox("Verlauf", [x[0] for x in mit_werten], key=P + "masse_verlauf",
                             format_func=lambda x: next(n for kk, n, _ in S.MASSE if kk == x))
            einheit = next(e for kk, _, e in S.MASSE if kk == k)
            _linie(S.mass_verlauf(monate, k), einheit, P + "masse_chart")


def _linie(werte, einheit, key, ziel=None):
    import plotly.graph_objects as go
    fig = go.Figure(go.Scatter(x=[d for d, _ in werte], y=[w for _, w in werte], mode="lines+markers",
                               line={"color": "#7C9CFF", "width": 3},
                               hovertemplate="%{x|%d.%m.%Y}: %{y:.1f} " + einheit + "<extra></extra>"))
    if ziel:
        fig.add_hline(y=ziel, line_dash="dot", line_color="#5EEAD4", annotation_text="Ziel")
    fig.update_layout(height=240, margin={"l": 10, "r": 10, "t": 10, "b": 10}, showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis={"title": einheit},
                      xaxis={"tickformat": "%d.%m."})
    st.plotly_chart(fig, config={"displayModeBar": False}, key=key)


def _gewicht_speichern(h, tag, kg):
    _tag_aendern(h, tag, lambda m: S.gewicht_setzen(m, tag, kg), "gesundheit gewicht")
    if tag >= _heute() - datetime.timedelta(days=1):            # aktuelles Gewicht -> Ziele passen sich an
        _profil_aendern(h, lambda d: S.profil_setzen(d, {"gewicht_kg": round(float(kg), 1)}, _jetzt()),
                        "gesundheit profil gewicht")
    _melden(f"Gewicht {_z(kg, 1)} kg gespeichert")


# ====================================================================== Profil
def _profil_seite(h, doc):
    p = dict(doc.get("profil") or {})
    z = _ziele(doc)
    st.markdown(f'<div class="gs-ziel"><span>Dein Tagesziel</span><b>{_z(z["kcal"])} kcal</b>'
                f'<span>Protein {_z(z["protein"])} g · KH {_z(z["kh"])} g · Fett {_z(z["fett"])} g · '
                f'Wasser {_z((z["wasser_ml"] or 0) / 1000, 1)} L</span></div>', unsafe_allow_html=True)
    with st.expander("So wird gerechnet"):
        _rechenweg(p, z)
    with st.form(P + "profil_form", border=False):
        ziele = [k for k, *_ in R.ZIELE]
        ziel = st.selectbox("Ziel", ziele, index=ziele.index(p.get("ziel", "halten")),
                            format_func=lambda k: next(t for kk, t, *_ in R.ZIELE if kk == k))
        c = st.columns(2)
        alter = c[0].number_input("Alter", 14, 100, int(R.alter(p.get("geburtsjahr")) or 35))
        groesse = c[1].number_input("Größe (cm)", 120, 230, int(p.get("groesse_cm") or 175))
        c = st.columns(2)
        gewicht = c[0].number_input("Gewicht (kg)", 35.0, 300.0, float(p.get("gewicht_kg") or 75), 0.1, format="%.1f")
        zielgewicht = c[1].number_input("Zielgewicht (kg)", 0.0, 300.0, float(p.get("zielgewicht_kg") or 0), 0.1,
                                        format="%.1f", help="Optional – 0 = kein Zielgewicht")
        akt = [k for k, *_ in R.AKTIVITAET]
        aktivitaet = st.radio("Aktivität", akt, index=akt.index(p.get("aktivitaet", "wenig")),
                              format_func=lambda k: next(f"{a} – {b}" for kk, a, b, _ in R.AKTIVITAET if kk == k))
        opts = {"m": "Mann", "w": "Frau", "x": "Keine Angabe"}
        geschlecht = st.radio("Berechnung als", list(opts), format_func=opts.get, horizontal=True,
                              index=list(opts).index(p.get("geschlecht", "x")))
        with st.expander("Eigene Zielwerte (statt automatisch)"):
            st.caption("0 lassen = automatisch berechnen.")
            c = st.columns(2)
            kcal_e = c[0].number_input("Kalorien (kcal)", 0, 6000, int(p.get("kcal_eigen") or 0), 50)
            prot_e = c[1].number_input("Protein (g)", 0, 400, int(p.get("protein_eigen") or 0), 5)
            wasser_e = st.number_input("Wasser (ml)", 0, 6000, int(p.get("wasser_eigen") or 0), 100)
        if st.form_submit_button("Speichern", type="primary", width="stretch"):
            neu = {"ziel": ziel, "geburtsjahr": _heute().year - int(alter), "groesse_cm": int(groesse),
                   "gewicht_kg": round(float(gewicht), 1), "zielgewicht_kg": round(float(zielgewicht), 1) or None,
                   "aktivitaet": aktivitaet, "geschlecht": geschlecht, "kcal_eigen": kcal_e or None,
                   "protein_eigen": prot_e or None, "wasser_eigen": wasser_e or None}

            _profil_aendern(h, lambda d: S.profil_setzen(d, neu, _jetzt()))   # None-Werte entfallen dort
            _melden("Gespeichert")
            _neu_aufbauen()

    st.markdown("**Meine Gläser**")
    st.caption("Ein Tipp auf „Heute“ oder „Trinken“ trägt diese Menge ein.")
    glaeser = list(doc["einstellungen"].get("glaeser") or [])
    while len(glaeser) < 2:
        glaeser.append({"name": "", "ml": 0})
    with st.form(P + "glaeser_form", border=False):
        neu_g = []
        for i, g in enumerate(glaeser[:2]):
            c = st.columns(2)
            name = c[0].text_input(f"Name {i + 1}", g.get("name") or "", max_chars=20)
            ml = c[1].number_input(f"Menge {i + 1} (ml)", 0, 3000, int(g.get("ml") or 0), 10)
            neu_g.append({"name": name.strip() or f"Glas {i + 1}", "ml": ml})
        if st.form_submit_button("Gläser speichern", width="stretch"):
            _profil_aendern(h, lambda d: {**d, "einstellungen": {**d["einstellungen"],
                                                                 "glaeser": [g for g in neu_g if g["ml"] > 0]}},
                            "gesundheit einstellungen")
            _melden("Gespeichert")
            _neu_aufbauen()

    with st.expander("Meine Mahlzeiten"):
        st.caption("Reihenfolge und Namen der Mahlzeiten im Tagebuch – eine je Zeile.")
        with st.form(P + "mahlzeiten_form", border=False):
            text = st.text_area("Mahlzeiten", "\n".join(_mahlzeiten(doc)), height=150, label_visibility="collapsed")
            if st.form_submit_button("Mahlzeiten speichern", width="stretch"):
                liste = list(dict.fromkeys(z.strip()[:30] for z in text.splitlines() if z.strip()))[:12]
                if not liste:
                    st.error("Bitte gib mindestens eine Mahlzeit ein.")
                else:
                    _profil_aendern(h, lambda d: {**d, "einstellungen": {**d["einstellungen"], "mahlzeiten": liste}},
                                    "gesundheit einstellungen")
                    _melden("Gespeichert")
                    _neu_aufbauen()

    with st.expander("Weitere Einstellungen"):
        _schalter(h, doc, "erweitert", "Erweiterte Ansicht",
                  "Zeigt bei den Nährstoffen alle Vitamine, Mineralstoffe, Spurenelemente und Fettsäuren sowie die "
                  "Datenvollständigkeit. Aus: nur die wichtigsten.")
        _schalter(h, doc, "fasten_zeigen", "Fasten anzeigen",
                  "Aus, wenn du nicht fastest – dann verschwinden Bereich und Knopf.")
        _schalter(h, doc, "supplements_zeigen", "Supplements anzeigen",
                  "Aus, wenn du keine Nahrungsergänzung nimmst – dann verschwindet der Bereich.")
        _schalter(h, doc, "sport_zusaetzlich", "Sportkalorien zusätzlich zum Tagesbedarf rechnen",
                  "Aus lassen, wenn dein Aktivitätslevel deinen Sport schon enthält – sonst würde er doppelt "
                  "gezählt. Sport kommt in einer der nächsten Ausbaustufen.")
        st.button("Einrichtung erneut durchlaufen", key=P + "neu_einrichten",
                  on_click=lambda: st.session_state.update({P + "einrichtung": True, P + "schritt": 1,
                                                            P + "entwurf": dict(doc.get("profil") or {})}))
        st.caption("Deine Gesundheitsdaten liegen nur in deinem privaten Datenspeicher und sind nur für dich sichtbar. "
                   "Export und vollständiges Löschen folgen mit den Berichten.")


def _schalter(h, doc, name, text, hilfe):
    """Einstellung als Schalter - speichert sofort (Autosave)."""
    k = P + "set_" + name
    st.session_state.setdefault(k, bool(doc["einstellungen"].get(name, S.STANDARD_EINSTELLUNGEN.get(name))))

    def speichern():
        wert = bool(st.session_state[k])
        _profil_aendern(h, lambda d: {**d, "einstellungen": {**d["einstellungen"], name: wert}},
                        "gesundheit einstellungen")
        _melden("Gespeichert")
    st.toggle(text, key=k, help=hilfe, on_change=speichern)


# ====================================================================== Supplements
def _sup_plan(doc, tag):
    return SU.tagesplan(doc.get("supplements") or [], tag)


def _einnahmen(t):
    return {x.get("sup"): x for x in t.get("supplements") or []}


def _einnehmen(h, tag, sup, status):
    _tag_aendern(h, tag, lambda m: S.einnahme_setzen(m, tag, sup, status, _jetzt()), "gesundheit supplement")


def _zuruecksetzen(h, tag, sup_id):
    _tag_aendern(h, tag, lambda m: S.einnahme_loeschen(m, tag, sup_id), "gesundheit supplement")


def _alle_einnehmen(h, tag, sups):
    def f(m):
        for x in sups:
            m = S.einnahme_setzen(m, tag, x, "eingenommen", _jetzt())
        return m
    _tag_aendern(h, tag, f, "gesundheit supplement routine")
    _melden(f"{len(sups)} Supplements eingenommen")


def _supplement_seite(h, doc):
    tag = _tag()
    t = S.tag_aus(_monat(h, tag), tag)
    plan = _sup_plan(doc, tag)
    genommen = _einnahmen(t)
    aktive = [x for x in doc.get("supplements") or [] if x.get("aktiv", True)]
    if plan:
        geplant = [x for l in plan.values() for x in l]
        n_ein = sum(1 for x in geplant if (genommen.get(x["id"]) or {}).get("status") == "eingenommen")
        st.markdown('<div class="gs-kacheln">' + _kachel("Eingenommen", n_ein, len(geplant), "", "laut Plan")
                    + "</div>", unsafe_allow_html=True)
        for zeit, sups in plan.items():
            offen = [x for x in sups if x["id"] not in genommen]
            with st.container(key=f"gs_reihe_zeitkopf_{zeit}", horizontal=True, vertical_alignment="center"):
                st.markdown(f"**{zeit}**")
                if len(offen) > 1:
                    st.button(f"✓ Alle {zeit.lower()}", key=P + f"alle_{zeit}", on_click=_alle_einnehmen,
                              args=(h, tag, offen), help="Alle offenen Supplements dieser Tageszeit als eingenommen markieren")
            for x in sups:
                _sup_zeile(h, tag, x, genommen.get(x["id"]))
    elif aktive:
        st.markdown('<div class="gs-leer">Für diesen Tag ist nichts geplant.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="gs-leer">Noch keine Supplements angelegt – unten eines aus der Liste wählen.</div>',
                    unsafe_allow_html=True)
    ungeplant = [x for x in aktive if x["id"] not in {y["id"] for l in plan.values() for y in l}]
    if ungeplant:
        with st.expander("Zusätzlich eingenommen?"):
            for x in ungeplant:
                _sup_zeile(h, tag, x, genommen.get(x["id"]))
    st.divider()
    with st.expander("＋ Supplement hinzufügen", expanded=not aktive):
        namen = ["Eigenes Produkt"] + [v["name"] for v in SU.VORLAGEN]
        wahl = st.selectbox("Vorlage", namen, index=1 if not aktive else 0, key=P + "sup_vorlage",
                            help="Vorlagen sind mit typischen Mengen vorbelegt – bitte mit dem Etikett abgleichen.")
        vorlage = next((v for v in SU.VORLAGEN if v["name"] == wahl), None)
        _sup_formular(h, SU.neues(vorlage, "sup:" + S.neue_id(), _heute()), "neu_" + wahl, neu=True)
    if aktive:
        st.markdown("**Meine Supplements**")
        for x in aktive:
            with st.expander(f"{x['name']} · {SU.plan_text(x)}"):
                st.caption(SU.inhalt_text(x, 8) or "Kein Inhalt hinterlegt")
                _sup_formular(h, x, x["id"], neu=False)


def _sup_zeile(h, tag, x, einnahme):
    status = (einnahme or {}).get("status")
    portion = x.get("portion") or "1 Portion"
    with st.container(key=f"gs_reihe_sup_{x['id']}", horizontal=True, vertical_alignment="center"):
        if status == "eingenommen":
            st.button(f"✓ {x['name']} – eingenommen {einnahme.get('zeit', '')}", key=P + f"sup_{x['id']}",
                      type="primary", width="stretch", on_click=_zuruecksetzen, args=(h, tag, x["id"]),
                      help="Antippen, um es wieder zurückzusetzen")
        elif status == "ausgelassen":
            st.button(f"✗ {x['name']} – ausgelassen", key=P + f"sup_{x['id']}", width="stretch",
                      on_click=_zuruecksetzen, args=(h, tag, x["id"]), help="Antippen, um es wieder zurückzusetzen")
        else:
            st.button(f"☐ {x['name']} · {portion}", key=P + f"sup_{x['id']}", width="stretch",
                      on_click=_einnehmen, args=(h, tag, x, "eingenommen"), help="Antippen = eingenommen")
            st.button("Auslassen", key=P + f"sup_aus_{x['id']}", on_click=_einnehmen, args=(h, tag, x, "ausgelassen"),
                      help="Heute bewusst nicht genommen")


def _sup_formular(h, sup, k, neu):
    import pandas as pd
    namen = {n: N.NAEHRSTOFFE[n].name for n in N.MIKRO}
    nach_name = {v: n for n, v in namen.items()}
    plan = dict(sup.get("plan") or {})
    with st.form(P + "supf_" + k, border=False):
        name = st.text_input("Name", sup.get("name") or "", max_chars=60, placeholder="z. B. Vitamin D3 1000")
        c = st.columns(2)
        form = c[0].selectbox("Form", SU.FORMEN, index=SU.FORMEN.index(sup.get("form")) if sup.get("form") in SU.FORMEN else 0)
        portion = c[1].text_input("Eine Portion", sup.get("portion") or "1 Tablette", max_chars=30)
        c = st.columns(2)
        zeit = c[0].selectbox("Wann?", SU.ZEITEN, index=SU.ZEITEN.index(plan.get("zeit")) if plan.get("zeit") in SU.ZEITEN else 0)
        portionen = c[1].number_input("Portionen je Einnahme", 0.5, 20.0, float(plan.get("portionen") or 1), 0.5, format="%g")
        st.markdown("Inhalt je Portion")
        zeilen = pd.DataFrame([{"Nährstoff": namen.get(z["n"], z["n"]), "Menge": float(z["menge"]),
                                "Einheit": z["einheit"]} for z in sup.get("inhalt") or []]
                              or [{"Nährstoff": None, "Menge": None, "Einheit": "mg"}])
        tabelle = st.data_editor(
            zeilen, num_rows="dynamic", hide_index=True, width="stretch", key=P + "supt_" + k,
            column_config={"Nährstoff": st.column_config.SelectboxColumn("Nährstoff", options=list(namen.values()), required=True),
                           "Menge": st.column_config.NumberColumn("Menge", min_value=0.0, format="%g", required=True),
                           "Einheit": st.column_config.SelectboxColumn("Einheit", options=SU.EINHEITEN, required=True)})
        with st.expander("Weitere Angaben"):
            rhythmen = {"taeglich": "Jeden Tag", "wochentage": "An bestimmten Wochentagen", "intervall": "Alle paar Tage"}
            rhythmus = st.radio("Wie oft?", list(rhythmen), format_func=rhythmen.get, horizontal=True,
                                index=list(rhythmen).index(plan.get("rhythmus", "taeglich")))
            tage = st.pills("Wochentage", list(range(7)), selection_mode="multi", format_func=lambda i: SU.WOCHENTAGE[i],
                            default=plan.get("tage") or list(range(7)), help="Nur bei „An bestimmten Wochentagen“")
            alle = st.number_input("Alle … Tage", 2, 60, int(plan.get("alle") or 2), help="Nur bei „Alle paar Tage“ – ab heute")
            hersteller = st.text_input("Hersteller", sup.get("hersteller") or "", max_chars=60)
            notiz = st.text_area("Notiz", sup.get("notiz") or "", max_chars=300, height=68)
        c = st.columns(2) if not neu else [st]
        gespeichert = c[0].form_submit_button("Hinzufügen" if neu else "Speichern", type="primary", width="stretch")
        entfernt = (not neu) and c[1].form_submit_button("🗑 Entfernen", width="stretch")
    if entfernt:
        _profil_aendern(h, lambda d: S.supplement_entfernen(d, sup["id"]), "gesundheit supplement entfernt")
        _melden(f"{sup.get('name')} entfernt – frühere Einnahmen bleiben erhalten")
        _neu_aufbauen()
    if not gespeichert:
        return
    inhalt, fehler = [], []
    for _, z in tabelle.iterrows():
        n = nach_name.get(z.get("Nährstoff"))
        menge = z.get("Menge")
        if not n or menge is None or pd.isna(menge):
            continue
        if N.in_basis(n, menge, z.get("Einheit")) is None:
            fehler.append(f"Für {namen[n]} gibt es keine Umrechnung aus {z.get('Einheit')} – bitte mg, µg oder g wählen.")
            continue
        inhalt.append({"n": n, "menge": float(menge), "einheit": z.get("Einheit")})
    if not name.strip():
        fehler.insert(0, "Bitte gib einen Namen ein.")
    if fehler:
        for f in fehler:
            st.error(f)
        return
    neu_sup = {**sup, "name": name.strip(), "form": form, "portion": portion.strip() or "1 Portion", "inhalt": inhalt,
               "hersteller": hersteller.strip(), "notiz": notiz.strip(), "aktiv": True,
               "plan": {**plan, "zeit": zeit, "portionen": portionen, "rhythmus": rhythmus,
                        "tage": sorted(tage or []) or list(range(7)), "alle": int(alle),
                        "ab": plan.get("ab") if (plan.get("rhythmus") == "intervall" and plan.get("alle") == alle)
                        else _heute().isoformat()}}
    _profil_aendern(h, lambda d: S.supplement_speichern(d, neu_sup), "gesundheit supplement")
    _melden(f"{neu_sup['name']} gespeichert")
    _neu_aufbauen()


# ====================================================================== Naehrstoffe
def _naehrstoff_seite(h, doc):
    tag = _tag()
    t = S.tag_aus(_monat(h, tag), tag)
    p = doc.get("profil") or {}
    alter = R.alter(p.get("geburtsjahr"), _heute())
    erweitert = bool(doc["einstellungen"].get("erweitert"))
    s = st.session_state
    s.setdefault(P + "mikro_alle", erweitert)
    alle = st.toggle("Alle Nährstoffe zeigen", key=P + "mikro_alle")
    if not t["essen"] and not any(x.get("status") == "eingenommen" for x in t.get("supplements") or []):
        st.markdown('<div class="gs-leer">Für diesen Tag ist noch nichts eingetragen.</div>', unsafe_allow_html=True)
        st.button("＋ Essen eintragen", key=P + "mikro_essen", on_click=_zu, args=("Essen",), width="stretch")
        return
    q = MI.datenqualitaet(t)
    if q is not None and (alle or q < 100):
        st.caption(f"Datenvollständigkeit: Für {_z(q)} % der erfassten Lebensmittel liegen Vitamin- und "
                   f"Mineralstoffwerte vor. Fehlende Werte zählen nicht als 0 – die Summen sind dann eher zu niedrig.")
    gruppen = N.GRUPPEN if alle else [("Wichtige Nährstoffe", N.EINFACH)]
    ids_alle = [n for _, ids in gruppen for n in ids]
    werte = {x["id"]: x for x in MI.uebersicht(t, p, ids_alle, alter)}
    for titel, ids in gruppen:
        st.markdown(f"**{titel}**")
        st.markdown('<div class="gs-kacheln">' + "".join(_mikro_kachel(werte[n], alle) for n in ids) + "</div>",
                    unsafe_allow_html=True)
    st.selectbox("Details", ids_alle, index=None, key=P + "mikro_detail", placeholder="Details zu einem Nährstoff …",
                 format_func=lambda n: N.NAEHRSTOFFE[n].name, label_visibility="collapsed")
    if s.get(P + "mikro_detail"):
        _mikro_detail(h, doc, werte[s[P + "mikro_detail"]], tag)
    st.caption(f"Referenzwerte: {F.QUELLE_ZIEL}; obere Werte: {F.QUELLE_UL} (Stand {F.VERSION}). "
               "Rechnerischer Vergleich der dokumentierten Aufnahme – keine Diagnose.")


def _mikro_kachel(w, details=False):
    e = w["einheit"]
    stellen = 0 if (w["ziel"] or w["wert"] or 0) >= 100 else 1
    sub = []
    if w["prozent"] is not None:
        sub.append(f"{_z(w['prozent'])} %")
    ueber_ul = bool(w["ul"] and w["wert"] > w["ul"])
    if ueber_ul:
        sub.append("über dem oberen Referenzwert")
    if details and w["anzahl"] and w["bekannt"] < w["anzahl"]:
        sub.append(f"bekannt für {w['bekannt']} von {w['anzahl']} Lebensmitteln")
    return _kachel(w["name"], w["wert"], w["ziel"], e, " · ".join(sub), stellen=stellen, warnung=ueber_ul)


def _mikro_detail(h, doc, w, tag):
    e = w["einheit"]
    stellen = 0 if (w["ziel"] or w["wert"] or 0) >= 100 else 1
    with st.container(border=True, key="gs_mikro_detailkasten"):
        st.markdown(f"**{w['name']}** – {html.escape(N.NAEHRSTOFFE[w['id']].beschreibung or '')}")
        zeilen = [f"{_tag_name(tag)}: **{_z(w['wert'], stellen)} {e}**"]
        if w["ziel"]:
            zeilen.append(f"Referenzwert: {_z(w['ziel'], stellen)} {e} → **{_z(w['prozent'])} %**")
        st.markdown(" · ".join(zeilen))
        q = w["quellen"]
        if w["wert"]:
            st.markdown("  \n".join(f"{name}: {_z(q[name], stellen)} {e}" for name in MI.QUELLEN if q[name]))
        if w["top"]:
            st.caption("Größte Quellen: " + ", ".join(f"{html.escape(n)} ({_z(v, stellen)} {e})" for n, v in w["top"]))
        if w["ziel"] and w["wert"] < w["ziel"]:
            st.caption("Deine dokumentierte Aufnahme lag unter dem hinterlegten Referenzwert.")
        if w["ul"] and w["wert"] > w["ul"]:
            st.warning(f"Deine dokumentierte Aufnahme liegt über dem oberen Referenzwert ({_z(w['ul'])} {e}, EFSA).")
        if w["ref"] and w["ref"].bemerkung:
            st.caption(f"Hinweis zum Referenzwert: {w['ref'].bemerkung}.")
        # Verlauf: 7 und 30 Tage (Tage ohne Eintraege zaehlen nicht mit)
        tage = [tag - datetime.timedelta(days=i) for i in range(30)]
        daten = {d: S.tag_aus(_monat(h, d), d) for d in tage}
        for n_tage in (7, 30):
            mw, anzahl = MI.durchschnitt([daten[d] for d in tage[:n_tage]], w["id"])
            if mw is not None:
                st.markdown(f"Ø {n_tage} Tage: **{_z(mw, stellen)} {e}**"
                            + (f" ({_z(MI.abdeckung(mw, w['ziel']))} %)" if w["ziel"] else "")
                            + f" <span style='opacity:.8'>· {anzahl} Tage mit Einträgen</span>", unsafe_allow_html=True)
        reihe = [(d, MI.tag_naehrstoffe(daten[d], [w["id"]])[w["id"]]["wert"]) for d in reversed(tage[:14])]
        if sum(1 for _, v in reihe if v) >= 2:
            import plotly.graph_objects as go
            fig = go.Figure(go.Bar(x=[d for d, _ in reihe], y=[v for _, v in reihe], marker_color="#7C9CFF",
                                   hovertemplate="%{x|%d.%m.}: %{y:.1f} " + e + "<extra></extra>"))
            if w["ziel"]:
                fig.add_hline(y=w["ziel"], line_dash="dot", line_color="#5EEAD4", annotation_text="Referenz")
            fig.update_layout(height=220, margin={"l": 10, "r": 10, "t": 10, "b": 10}, showlegend=False,
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              yaxis={"title": e}, xaxis={"tickformat": "%d.%m."})
            st.plotly_chart(fig, config={"displayModeBar": False}, key=P + "mikro_chart")


# ====================================================================== Sport
def _sport_seite(h, doc):
    tag = _tag()
    s = st.session_state
    t = S.tag_aus(_monat(h, tag), tag)
    nutzung = doc.get("sport_nutzung") or {}
    gewicht = t.get("gewicht") or (doc.get("profil") or {}).get("gewicht_kg")
    kcal_sum, min_sum = SP.summe(t)
    st.markdown('<div class="gs-kacheln">' + _kachel("Sport", kcal_sum, None, "kcal", f"{_z(min_sum)} Minuten")
                + "</div>", unsafe_allow_html=True)
    # Haeufig genutzte zuerst, dann die uebrigen
    arten = sorted(SP.AKTIVITAETEN, key=lambda a: (-int((nutzung.get(a) or {}).get("n") or 0),
                                                   list(SP.AKTIVITAETEN).index(a))) + [SP.EIGENE]
    if s.get(P + "sport_art") not in arten:
        s[P + "sport_art"] = None
    art = st.pills("Aktivität", arten, key=P + "sport_art", label_visibility="collapsed",
                   format_func=lambda a: "＋ Andere" if a == SP.EIGENE else SP.AKTIVITAETEN[a]["name"])
    if art:
        _sport_erfassen(h, tag, art, nutzung.get(art) or {}, gewicht, doc)
    if t.get("sport"):
        st.markdown(f"**{_tag_name(tag)}**")
        for x in t["sport"]:
            with st.container(key=f"gs_reihe_sp_{x['id']}", horizontal=True, vertical_alignment="center"):
                st.markdown(f'<div class="gs-zeile">{html.escape(x["name"])} · {_z(x["minuten"])} min '
                            f'<span>({x.get("intensitaet", "")})</span> · <b>{_z(x["kcal"])} kcal</b></div>',
                            unsafe_allow_html=True)
                st.button("🗑", key=P + f"sp_weg_{x['id']}", help="Entfernen", on_click=_entfernen,
                          args=(h, tag, "sport", x["id"], x["name"]))
    elif not art:
        st.markdown('<div class="gs-leer">Noch kein Sport eingetragen – oben eine Aktivität antippen.</div>',
                    unsafe_allow_html=True)
    zus = doc["einstellungen"].get("sport_zusaetzlich")
    st.caption("Sportkalorien zählen zusätzlich zu deinem Tagesbedarf." if zus else
               "Sportkalorien werden nicht zusätzlich gerechnet, weil deine Aktivitätsstufe den Sport schon enthält "
               "(änderbar im Profil). Gerechnet wird nur der Verbrauch über dem Ruheumsatz.")


def _sport_erfassen(h, tag, art, u, gewicht, doc):
    k = P + "sp_" + art
    with st.container(border=True, key="gs_sport_erfassen"):
        if art == SP.EIGENE:
            c = st.columns(2)
            c[0].text_input("Was?", key=k + "_name", placeholder="z. B. Klettern", max_chars=40)
            c[1].number_input("Kalorien (kcal)", 0, 3000, 300, 10, key=k + "_kcal")
            st.number_input("Dauer (Minuten)", 1, 600, 60, 5, key=k + "_min")
        else:
            a = SP.AKTIVITAETEN[art]
            minuten = st.number_input("Dauer (Minuten)", 1, 600, int(u.get("minuten") or a["minuten"]), 5,
                                      key=k + "_min")
            st.session_state.setdefault(k + "_int", u.get("intensitaet") or "mittel")
            inten = st.segmented_control("Intensität", SP.INTENSITAETEN, key=k + "_int", width="stretch") or "mittel"
            berechnet = SP.kcal(art, minuten, inten, gewicht)
            if berechnet is None:
                st.caption("Für die Berechnung fehlt dein Gewicht – bitte unter „Körper“ eintragen.")
            else:
                st.markdown(f'<div class="gs-vorschau">≈ <b>{_z(berechnet)} kcal</b> '
                            f'<span>zusätzlich zum Ruheumsatz</span></div>', unsafe_allow_html=True)
            with st.expander("Weitere Angaben"):
                st.number_input("Kalorien selbst angeben (0 = berechnen)", 0, 5000, 0, 10, key=k + "_kcal",
                                help="z. B. aus deiner Sportuhr")
        st.button("Speichern", key=P + "sport_speichern", type="primary", width="stretch",
                  on_click=_sport_speichern, args=(h, tag, art, k, gewicht))


def _sport_speichern(h, tag, art, k, gewicht):
    s = st.session_state
    minuten = s.get(k + "_min") or 0
    if art == SP.EIGENE:
        name = (s.get(k + "_name") or "").strip() or "Sport"
        kcal, inten, manuell = s.get(k + "_kcal") or 0, "", True
    else:
        name = SP.AKTIVITAETEN[art]["name"]
        inten = s.get(k + "_int") or "mittel"
        eigen = s.get(k + "_kcal") or 0
        kcal = eigen or SP.kcal(art, minuten, inten, gewicht) or 0
        manuell = bool(eigen)
    if minuten <= 0:
        _melden("Bitte gib eine gültige Dauer ein.", "fehler")
        return
    e = SP.eintrag(art, name, minuten, inten, kcal, manuell, _jetzt(), S.neue_id())
    _tag_aendern(h, tag, lambda m: S.sport_hinzu(m, tag, e), "gesundheit sport")
    if art != SP.EIGENE:
        _profil_aendern(h, lambda d: S.sport_merken(d, art, minuten, inten), "gesundheit sport nutzung")
    s[P + "sport_art"] = None
    _melden(f"{name} gespeichert · {_z(kcal)} kcal")


# ====================================================================== Fasten
def _fasten_starten(h, doc):
    f = FA.zustand(doc)
    ziel = FA.ziel_stunden(f.get("plan"), f.get("eigene_h"))
    _profil_aendern(h, lambda d: FA.starten(d, _jetzt(), ziel), "gesundheit fasten")
    _melden(f"Fasten gestartet – Ziel {_z(ziel)} Stunden")


def _fasten_beenden(h):
    _profil_aendern(h, lambda d: FA.beenden(d, _jetzt()), "gesundheit fasten")
    _melden("Fasten beendet")


def _fasten_seite(h, doc):
    s = st.session_state
    f = FA.zustand(doc)
    st_ = FA.status(f["laeuft"], _jetzt())
    if st_:
        st.markdown(f'<div class="gs-ziel"><span>Du fastest seit</span><b>{FA.dauer_text(st_["dauer_h"])}</b>'
                    f'<span>Ziel {_z(st_["ziel_h"])} h · Start {st_["start"].strftime("%d.%m. %H:%M")} Uhr · '
                    + ("Ziel erreicht – Essensfenster offen" if st_["erreicht"] else
                       f"Essensfenster ab {st_['ende_geplant'].strftime('%H:%M')} Uhr")
                    + f' bis {st_["fenster_bis"].strftime("%H:%M")} Uhr</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="gs-kacheln">' + _kachel("Fortschritt", st_["dauer_h"], st_["ziel_h"], "h", stellen=1,
                                                          warnung=False) + "</div>", unsafe_allow_html=True)
        st.button("⏹ Fasten beenden", key=P + "fa_ende", type="primary", width="stretch", on_click=_fasten_beenden,
                  args=(h,))
        with st.expander("Weitere Angaben"):
            st.caption("Vergessen zu starten? Startzeit nachträglich setzen:")
            c = st.columns(2)
            c[0].date_input("Datum", st_["start"].date(), key=P + "fa_d", format="DD.MM.YYYY")
            c[1].time_input("Uhrzeit", st_["start"].time(), key=P + "fa_z", step=300)
            st.button("Startzeit übernehmen", key=P + "fa_start_neu", on_click=_fasten_start_setzen,
                      args=(h, P + "fa_d", P + "fa_z"))
            st.button("Versehentlich gestartet – verwerfen", key=P + "fa_weg",
                      on_click=lambda: (_profil_aendern(h, FA.abbrechen, "gesundheit fasten"), _melden("Verworfen")))
    else:
        plaene = list(FA.PLAENE) + ["eigene"]
        s.setdefault(P + "fa_plan", f.get("plan") if f.get("plan") in plaene else "16:8")
        plan = st.segmented_control("Plan", plaene, key=P + "fa_plan", width="stretch",
                                    format_func=lambda p: "Eigener" if p == "eigene" else p) or "16:8"
        eigene_h = None
        if plan == "eigene":
            eigene_h = st.number_input("Fastendauer (Stunden)", 1.0, 72.0, float(f.get("eigene_h") or 20), 0.5,
                                       key=P + "fa_eigen")
        ziel = FA.ziel_stunden(plan, eigene_h)
        st.caption(f"{_z(ziel)} Stunden fasten, danach {_z(max(0, 24 - ziel))} Stunden Essensfenster.")
        st.button("⏱ Fasten starten", key=P + "fa_start", type="primary", width="stretch",
                  on_click=_fasten_plan_start, args=(h, P + "fa_plan", P + "fa_eigen"))
    verlauf = list(reversed(f.get("verlauf") or []))[:14]
    if verlauf:
        st.markdown("**Letzte Fastenzeiten**")
        for v in verlauf:
            try:
                a, e = datetime.datetime.fromisoformat(v["start"]), datetime.datetime.fromisoformat(v["ende"])
            except (KeyError, TypeError, ValueError):
                continue
            dauer = (e - a).total_seconds() / 3600
            ok = dauer >= float(v.get("ziel_h") or 0)
            st.markdown(f'<div class="gs-zeile">{"✓" if ok else "○"} {a.strftime("%d.%m. %H:%M")} – '
                        f'{e.strftime("%d.%m. %H:%M")} · <b>{FA.dauer_text(dauer)}</b> '
                        f'<span>(Ziel {_z(v.get("ziel_h"))} h)</span></div>', unsafe_allow_html=True)
    elif not st_:
        st.markdown('<div class="gs-leer">Noch keine Fastenzeit – oben einfach starten.</div>', unsafe_allow_html=True)


def _fasten_plan_start(h, k_plan, k_eigen):
    s = st.session_state
    plan = s.get(k_plan) or "16:8"
    eigene_h = s.get(k_eigen)
    ziel = FA.ziel_stunden(plan, eigene_h)

    def f(d):
        d = dict(d)
        d["fasten"] = {**FA.zustand(d), "plan": plan, **({"eigene_h": float(eigene_h)} if eigene_h else {})}
        return FA.starten(d, _jetzt(), ziel)
    _profil_aendern(h, f, "gesundheit fasten")
    _melden(f"Fasten gestartet – Ziel {_z(ziel)} Stunden")


def _fasten_start_setzen(h, k_d, k_z):
    s = st.session_state
    start = datetime.datetime.combine(s.get(k_d), s.get(k_z)).replace(tzinfo=BERLIN)
    if start > _jetzt():
        _melden("Der Start kann nicht in der Zukunft liegen.", "fehler")
        return

    def f(d):
        d = dict(d)
        fz = FA.zustand(d)
        if fz["laeuft"]:
            fz["laeuft"] = {**fz["laeuft"], "start": start.isoformat(timespec="seconds")}
        d["fasten"] = fz
        return d
    _profil_aendern(h, f, "gesundheit fasten")
    _melden("Startzeit geändert")
