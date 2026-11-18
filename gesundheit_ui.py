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

from gesundheit import lebensmittel as L
from gesundheit import quellen as Q
from gesundheit import rechnen as R
from gesundheit import speicher as S

BERLIN = ZoneInfo("Europe/Berlin")
P = "gs_"
BEREICHE = ["Heute", "Essen", "Trinken", "Körper", "Profil"]
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


def _kachel(label, wert, ziel, einheit, sub="", stellen=0):
    anteil = (wert / ziel) if ziel else None
    balken = ""
    if anteil is not None:
        balken = (f'<div class="gs-balken{" ueber" if anteil > 1.05 else ""}" role="progressbar" '
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
        s.setdefault(P + "bereich", BEREICHE[0])
        bereich = st.segmented_control("Bereich", BEREICHE, key=P + "bereich", label_visibility="collapsed",
                                       width="stretch") or BEREICHE[0]
        if bereich != "Profil":
            _tag_leiste()
        {"Heute": _heute_seite, "Essen": _essen_seite, "Trinken": _trinken_seite, "Körper": _koerper_seite,
         "Profil": _profil_seite}[bereich](h, doc)
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
    b = R.bilanz(z["kcal"], z["tdee"], su["kcal"], 0, doc["einstellungen"].get("sport_zusaetzlich"))
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
        st.button("⚖️ Gewicht", key=P + "q_gewicht", on_click=_zu, args=("Körper",))

    st.markdown("**Gegessen**")
    if not t["essen"]:
        st.markdown('<div class="gs-leer">Noch keine Mahlzeiten eingetragen</div>', unsafe_allow_html=True)
        st.button("＋ Erste Mahlzeit hinzufügen", key=P + "leer_essen", on_click=_zu, args=("Essen",), width="stretch")
    else:
        for m in S.MAHLZEITEN:
            posten = [e for e in t["essen"] if (e.get("mahlzeit") or "Snacks") == m]
            if posten:
                namen = ", ".join(e["name"] for e in posten[:4]) + (" …" if len(posten) > 4 else "")
                st.markdown(f'<div class="gs-zeile"><b>{m}</b> · {_z(su["mahlzeiten"].get(m, 0))} kcal '
                            f'<span>– {html.escape(namen)}</span></div>', unsafe_allow_html=True)
    if t["trinken"]:
        st.markdown(f'<div class="gs-zeile"><b>Getränke</b> · {_z(sum(x["ml"] for x in t["trinken"]))} ml '
                    f'<span>({len(t["trinken"])} ×)</span></div>', unsafe_allow_html=True)
    if t.get("gewicht"):
        st.markdown(f'<div class="gs-zeile"><b>Gewicht</b> · {_z(t["gewicht"], 1)} kg</div>', unsafe_allow_html=True)


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
    _tagebuch(h, tag, t)
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
            st.selectbox("Mahlzeit", S.MAHLZEITEN, index=S.MAHLZEITEN.index(mahlzeit_std), key=k + "_mahlzeit")
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


def _tagebuch(h, tag, t):
    su = S.tag_summen(t)
    if not t["essen"]:
        st.markdown('<div class="gs-leer">Noch nichts eingetragen – oben ein Lebensmittel suchen.</div>',
                    unsafe_allow_html=True)
        return
    st.markdown(f"**{_tag_name(tag)}: {_z(su['naehrwerte']['kcal']['wert'])} kcal gegessen**")
    for m in S.MAHLZEITEN:
        posten = [e for e in t["essen"] if (e.get("mahlzeit") or "Snacks") == m]
        if not posten:
            continue
        with st.expander(f"{m} · {_z(su['mahlzeiten'].get(m, 0))} kcal", expanded=True):
            for e in posten:
                _eintrag(h, tag, e)


def _eintrag(h, tag, e):
    nw = S.eintrag_naehrwerte(e)
    k = P + "eintrag_" + e["id"]
    with st.container(key="gs_eintrag_" + e["id"]):
        with st.popover(f"{e['name']} · {_menge_text(e['menge'], e['einheit'])} · {_z(nw.get('kcal'))} kcal",
                        width="stretch"):
            stueckig = e["einheit"] not in ("g", "ml")
            st.number_input("Menge", 0.0, 5000.0, float(e["menge"]), 0.5 if stueckig else 10.0, format="%g",
                                    key=k + "_m", help=f"in {e['einheit']}")
            st.selectbox("Mahlzeit", S.MAHLZEITEN, index=S.MAHLZEITEN.index(e.get("mahlzeit") or "Snacks")
                                if (e.get("mahlzeit") or "Snacks") in S.MAHLZEITEN else 4, key=k + "_mz")
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

    with st.expander("Weitere Einstellungen"):
        st.session_state.setdefault(P + "sport_zus", bool(doc["einstellungen"].get("sport_zusaetzlich")))
        st.toggle("Sportkalorien zusätzlich zum Tagesbedarf rechnen", key=P + "sport_zus",
                  help="Aus lassen, wenn dein Aktivitätslevel deinen Sport schon enthält – sonst würde er doppelt "
                       "gezählt. Sport kommt in einer der nächsten Ausbaustufen.",
                  on_change=lambda: _profil_aendern(
                      h, lambda d: {**d, "einstellungen": {**d["einstellungen"],
                                                           "sport_zusaetzlich": bool(st.session_state[P + "sport_zus"])}},
                      "gesundheit einstellungen"))
        st.button("Einrichtung erneut durchlaufen", key=P + "neu_einrichten",
                  on_click=lambda: st.session_state.update({P + "einrichtung": True, P + "schritt": 1,
                                                            P + "entwurf": dict(doc.get("profil") or {})}))
        st.caption("Deine Gesundheitsdaten liegen nur in deinem privaten Datenspeicher und sind nur für dich sichtbar. "
                   "Export und vollständiges Löschen folgen mit den Berichten.")
