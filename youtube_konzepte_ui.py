"""Faceless YouTube Phase 3b - Better Video und Affiliate-Finder im Bereich „Analyse“
(Rechenkern youtube_konzepte.py)."""
import datetime
import uuid

import streamlit as st

import ui_stil as UI
import youtube_analyse as YAN
import youtube_konzepte as YK
import youtube_nische as YN
from youtube_ui import K, _e, _speichern


def _ki(h):
    try:
        return h["ki"]() if h.get("ki") else None
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------- Better Video
def _konzept(h, i, k, thema):
    with st.container(border=True, key=K + f"bv_box_{i}"):
        st.markdown(f"**{i + 1}. {_e(k['titel'])}**  \n<span style='color:#A9ACB0;font-size:.8rem'>"
                    f"{_e(YK.FORMATE.get(k['format'], ''))} · ~{k['laenge_min']} Min. · {_e(k['quelle'])}</span>",
                    unsafe_allow_html=True)
        if k.get("aehnlich"):
            st.warning(f"Titel ist sehr nah an „{k['aehnlich']}“ – bitte eigenständiger formulieren.")
        for feld, name in (("hook", "Hook"), ("versprechen", "Versprechen"), ("zielgruppe", "Zielgruppe"),
                           ("alleinstellung", "Besser als vorhandene Videos"), ("thumbnail_idee", "Thumbnail-Idee")):
            if k.get(feld):
                st.markdown(f"*{name}:* {_e(k[feld])}")
        if k["aufbau"]:
            st.markdown("\n".join(f"- **{_e(x['kapitel'])}** – {_e(x['inhalt'])}" for x in k["aufbau"]))
        if k["zu_pruefen"]:
            st.caption("Vor dem Skript belegen: " + "; ".join(_e(x) for x in k["zu_pruefen"]))
        sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
        if sp[0].button("💡 Als Idee speichern", key=K + f"bv_idee_{i}"):
            idee = {"id": uuid.uuid4().hex[:8], "titel": k["titel"][:120], "nische": (thema or "")[:60],
                    "markt": "DE", "quelle": "", "status": "neu", "datum": datetime.date.today().isoformat(),
                    "notiz": f"Better-Video-Konzept ({k['quelle']}): " + "; ".join(x["kapitel"] for x in k["aufbau"])}

            def neu(x):
                if any(y["titel"].lower() == idee["titel"].lower() for y in x["ideen"]):
                    return x
                return dict(x, ideen=x["ideen"] + [idee])
            if _speichern(h, neu, "Konzept als Idee gespeichert"):
                st.rerun()
        if sp[1].button("🎬 In der Video Factory starten", key=K + f"bv_vf_{i}"):
            st.session_state["yt_vf_vorlage"] = {"titel": k["titel"][:100], "auftrag": YK.auftrag(k, thema)}
            st.session_state["yt_vf_teil_neu"] = "Neues Video"
            st.session_state[K + "bereich_neu"] = "Video Factory"
            st.rerun()


def better_video(h, d):
    ss = st.session_state
    st.markdown("**Better Video** – drei eigenständige Konzepte aus Thema, Zuschauerstimmen und eigener Recherche")
    thema = st.text_input("Thema", key=K + "bv_thema", max_chars=120, placeholder="z. B. ETF-Sparplan für Anfänger")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    zielgruppe = sp[0].text_input("Zielgruppe (optional)", key=K + "bv_ziel", max_chars=100)
    laenge = sp[1].slider("Länge (Minuten)", 1, 20, 8, key=K + "bv_laenge")
    gemerkt = d.get("analysen") or []
    wahl = st.multiselect("Gemerkte Analysen einbeziehen", [a["id"] for a in gemerkt], key=K + "bv_analysen",
                          format_func=lambda i: next(f"{a['titel'] or '–'} ({'Kommentare' if a['art'] == 'kommentare' else 'Transkript'}, {a['datum']})"
                                                     for a in gemerkt if a["id"] == i),
                          placeholder="keine – nur Thema und Notizen")
    notizen = st.text_area("Eigene Recherche / Notizen (optional)", key=K + "bv_notizen", height=90, max_chars=3000)
    m = YK.material([a for a in gemerkt if a["id"] in wahl])
    ki = _ki(h)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    mit = sp[0].button("✨ Konzepte mit KI", key=K + "bv_ki_btn", type="primary",
                       disabled=ki is None or not (thema or "").strip(),
                       help=None if ki else "Kein KI-Zugang (GEMINI_API_KEY).")
    ohne = sp[1].button("Gerüst ohne KI", key=K + "bv_geruest_btn", disabled=not (thema or "").strip(),
                        help="Drei Gerüste aus den Fragen, Wünschen und Kritikpunkten der gewählten Analysen.")
    if mit:
        with st.spinner("KI entwickelt Konzepte …"):
            obj, fehler = YAN.mit_ki(ki, YK.prompt(thema, zielgruppe, laenge, m, notizen),
                                     lambda o: YK.pruefen(o, m["quellen"]))
        if fehler:
            st.warning(fehler)
        else:
            ss[K + "bv_erg"] = dict(obj, thema=thema)
    if ohne:
        ss[K + "bv_erg"] = dict(YK.geruest(thema, m, laenge), thema=thema)
    erg = ss.get(K + "bv_erg")
    if not erg:
        st.caption("Tipp: Zuerst unter „Kommentare“ oder „Transkript“ Analysen merken – dann wissen die Konzepte, "
                   "was Zuschauer vermissen.")
        return
    for i, k in enumerate(erg["konzepte"]):
        _konzept(h, i, k, erg["thema"])
    st.caption("Konzepte sind Vorschläge. Fakten und Zahlen vor dem Skript mit eigenen Quellen belegen; keine fremden "
               "Inhalte übernehmen. Ähnlichkeitsprüfung: Wortüberschneidung der Titel mit den analysierten Videos.")


# ---------------------------------------------------------------------------------------------------- Affiliate
def affiliate(h, d):
    ss = st.session_state
    st.markdown("**Affiliate-Finder** – nur Programme mit offizieller Quelle; geprüft erst nach deinem Häkchen")
    kategorien = ["alle"] + list(YN.STANDARD_RPM)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    kat = sp[0].selectbox("Nische", kategorien, key=K + "af_kat")
    markt = sp[1].selectbox("Markt", ["", "DE", "AT", "CH", "US", "UK"], key=K + "af_markt",
                            format_func=lambda x: x or "alle Märkte")
    pruef = d.get("affiliate") or {}
    liste = YK.passende(kat, markt, d.get("affiliate_eigene") or [], pruef)
    st.info(YK.KENNZEICHNUNG)
    for p in liste:
        with st.container(border=True, key=K + f"af_box_{p['id']}"):
            farbe = "#34D399" if p["geprueft"] else "#FBBF24"
            st.markdown(f"**{_e(p['name'])}** · {_e(p['art'])} · <span style='color:{farbe}'>{_e(p['status'])}"
                        + (f" am {_e(p['geprueft'])}" if p["geprueft"] else "") + "</span>  \n"
                        f"[{_e(p['url'])}]({p['url']}) · {_e(', '.join(p.get('kategorien') or []))}"
                        + (f" · {_e(', '.join(p['maerkte']))}" if p.get("maerkte") else ""),
                        unsafe_allow_html=True)
            if p.get("hinweis"):
                st.caption(p["hinweis"])
            if p["konditionen"]:
                st.markdown(f"*Konditionen (von dir geprüft):* {_e(p['konditionen'])}")
            with st.expander("Prüfung eintragen" if not p["geprueft"] else "Prüfung ändern"):
                kond = st.text_input("Konditionen laut offizieller Seite (z. B. Provision, Cookie-Dauer)",
                                     value=p["konditionen"], key=K + f"af_kond_{p['id']}", max_chars=200)
                ok = st.checkbox("Ich habe das Programm auf der offiziellen Seite geprüft", key=K + f"af_ok_{p['id']}")
                c = st.columns(2)
                if c[0].button("Als geprüft speichern", key=K + f"af_pr_{p['id']}", disabled=not ok):
                    eintrag = {"datum": datetime.date.today().isoformat(), "konditionen": (kond or "").strip()}
                    if _speichern(h, lambda x, i=p["id"]: dict(x, affiliate={**x["affiliate"], i: eintrag}),
                                  f"{p['name']} geprüft"):
                        st.rerun()
                if p["geprueft"] and c[1].button("Prüfung zurücknehmen", key=K + f"af_zu_{p['id']}"):
                    if _speichern(h, lambda x, i=p["id"]: dict(x, affiliate={k: v for k, v in x["affiliate"].items()
                                                                             if k != i}), "Prüfung zurückgenommen"):
                        st.rerun()
                if p.get("eigene") and c[1].button("Entfernen", key=K + f"af_weg_{p['id']}"):
                    if _speichern(h, lambda x, i=p["id"]: dict(x, affiliate_eigene=[y for y in x["affiliate_eigene"]
                                                                                    if y["id"] != i]),
                                  "Programm entfernt"):
                        st.rerun()
    with st.expander("➕ Eigenes Programm / KI-Vorschläge"):
        sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
        name = sp[0].text_input("Name", key=K + "af_name", max_chars=60)
        url = sp[1].text_input("Offizielle Adresse (https://…)", key=K + "af_url", max_chars=200)
        if st.button("Programm hinzufügen", key=K + "af_add", disabled=not (name and url)):
            try:
                neu = YK.eigenes_programm(name, url, [kat] if kat != "alle" else [])
            except ValueError as ex:
                st.error(str(ex))
            else:
                if _speichern(h, lambda x: dict(x, affiliate_eigene=[y for y in x["affiliate_eigene"]
                                                                     if y["id"] != neu["id"]] + [neu]),
                              f"{neu['name']} hinzugefügt"):
                    st.rerun()
        ki = _ki(h)
        thema = st.text_input("Thema für KI-Vorschläge", key=K + "af_thema", max_chars=120)
        if st.button("✨ KI-Vorschläge holen", key=K + "af_ki", disabled=ki is None or not (thema or "").strip()):
            with st.spinner("KI sucht Programme …"):
                obj, fehler = YAN.mit_ki(ki, YK.ki_prompt_affiliate(thema, kat), YK.ki_affiliate_pruefen)
            if fehler:
                st.warning(fehler)
            else:
                ss[K + "af_vorschlaege"] = obj["programme"]
        for j, v in enumerate(ss.get(K + "af_vorschlaege") or []):
            c = st.columns([4, 1])
            c[0].markdown(f"**{_e(v['name'])}** – {_e(v['warum'])}  \n{_e(v['url'])} · *ungeprüft (KI)*")
            if c[1].button("Übernehmen", key=K + f"af_ki_add_{j}"):
                try:
                    neu = YK.eigenes_programm(v["name"], v["url"], [kat] if kat != "alle" else [], ki=True,
                                              hinweis=v["warum"])
                except ValueError as ex:
                    st.error(str(ex))
                else:
                    if _speichern(h, lambda x: dict(x, affiliate_eigene=[y for y in x["affiliate_eigene"]
                                                                         if y["id"] != neu["id"]] + [neu]),
                                  f"{neu['name']} übernommen (ungeprüft)"):
                        st.rerun()
        st.caption("KI-Vorschläge können falsch oder veraltet sein: Adresse öffnen, Programm prüfen, dann oben "
                   "„Als geprüft speichern“.")
