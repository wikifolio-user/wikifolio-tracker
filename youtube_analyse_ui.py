"""Faceless YouTube Phase 3 - Bereich „Analyse“: Kommentar- und Transkript-Analyse (Rechenkern youtube_analyse.py).
Ergebnisse lassen sich merken (state/youtube.json, Liste "analysen") - sie sind die Grundlage fuer die
Better-Video-Konzepte. Gemerkt werden nur Auswertungen und kurze Beispielzitate, nie Namen von Verfassern."""
import datetime
import uuid

import streamlit as st

import ui_stil as UI
import youtube_analyse as YAN
import youtube_api as YA
from youtube_ui import K, _e, _kpis, _speichern

TEILE = ["Kommentare", "Transkript"]
MAX_ANALYSEN = 30


def _ki(h):
    try:
        return h["ki"]() if h.get("ki") else None
    except Exception:
        return None


def _merken(h, art, titel, quelle, ergebnis, ki=None):
    eintrag = {"id": uuid.uuid4().hex[:8], "art": art, "titel": (titel or "")[:120], "quelle": quelle[:300],
               "datum": datetime.date.today().isoformat(), "ergebnis": ergebnis, "ki": ki}

    def neu(x):
        alt = [a for a in x["analysen"] if not (a.get("art") == art and a.get("quelle") == eintrag["quelle"]
                                               and quelle)]
        return dict(x, analysen=(alt + [eintrag])[-MAX_ANALYSEN:])
    return _speichern(h, neu, f"{'Kommentar' if art == 'kommentare' else 'Transkript'}-Analyse gemerkt")


def _liste(titel, punkte):
    if punkte:
        st.markdown(f"**{titel}**")
        st.markdown("\n".join(f"- {_e(p)}" for p in punkte))


# ---------------------------------------------------------------------------------------------------- Kommentare
def kommentare(h, d):
    import youtube_recherche_ui as YRU
    ss = st.session_state
    st.markdown("**Kommentar-Analyse** – öffentliche Kommentare eines Videos über die offizielle API")
    if not h.get("yt_abruf"):
        st.info("Dafür fehlt der **YOUTUBE_API_KEY** (siehe „Einstellungen“).")
        return
    if K + "an_video_neu" in ss:
        ss[K + "an_video"] = ss.pop(K + "an_video_neu")
    eingabe = st.text_input("Video-Link oder Video-ID", key=K + "an_video", max_chars=200,
                            placeholder="https://www.youtube.com/watch?v=…")
    sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
    anzahl = sp[0].select_slider("Kommentare", [100, 200, 300, 500, 1000], value=300, key=K + "an_anzahl",
                                 help="1 Einheit je 100 Kommentare, dazu 1 Einheit für die Videodaten.")
    reihe = sp[1].selectbox("Reihenfolge", ["relevance", "time"], key=K + "an_reihe",
                            format_func=lambda r: "relevanteste" if r == "relevance" else "neueste")
    vid = YAN.video_id(eingabe)
    los = sp[2].button("💬 Kommentare analysieren", key=K + "an_btn", type="primary", disabled=not vid)
    if (eingabe or "").strip() and not vid:
        st.caption("Das ist kein gültiger Video-Link.")
    if los:
        def holen(abruf):
            v = YA.videos_laden(abruf, [vid])
            if not v:
                raise YA.ApiFehler("Video nicht gefunden (gelöscht, privat oder falsche ID).")
            return {"video": v[0], "kommentare": YAN.kommentare_laden(abruf, vid, anzahl, reihe)}
        erg = YRU.ausfuehren(h, d, "kommentare", {"video": vid, "anzahl": anzahl, "reihe": reihe}, holen,
                             datei_cache=False)
        if erg:
            ss[K + "an_erg"] = dict(erg, auswertung=YAN.kommentare_auswerten(erg["daten"]["kommentare"]))
            ss.pop(K + "an_ki", None)
        st.rerun()
    YRU.kontingent_zeile(h, d)
    erg = ss.get(K + "an_erg")
    if not erg:
        return
    v, a = erg["daten"]["video"], erg["auswertung"]
    st.markdown(f"**{_e(v['titel'])}** · {_e(v['kanal'])} · {YRU._zahl(v.get('views'))} Aufrufe · "
                f"{YRU._zahl(v.get('kommentare'))} Kommentare insgesamt")
    st.caption(YRU._herkunft(erg) + f" · ausgewertet: {a['anzahl']} Kommentare, davon {a['spam']} als Spam aussortiert.")
    if not a["echt"]:
        st.info("Keine auswertbaren Kommentare.")
        return
    g = a["gruppen"]
    _kpis([(g[x]["name"], f"{round(g[x]['anteil'])} %", f"{g[x]['anzahl']} Kommentare", "")
           for x in ("lob", "kritik", "frage", "wunsch")])
    st.caption("Gruppen über Stichworte (ohne KI): ein Kommentar zählt zu genau einer Gruppe in der Reihenfolge "
               "Wunsch → Frage → Kritik → Lob → Sonstiges. Beispiele nach Likes.")
    for x in ("wunsch", "frage", "kritik", "lob", "sonstiges"):
        if g[x]["anzahl"]:
            with st.expander(f"{g[x]['name']} ({g[x]['anzahl']})"):
                for k in g[x]["beispiele"]:
                    st.markdown(f"- {_e(k['text'])}  \n  <span style='color:#A9ACB0;font-size:.78rem'>👍 {k['likes']}"
                                f" · {k['antworten']} Antworten · {_e(k['datum'])}</span>", unsafe_allow_html=True)
    if a["begriffe"]:
        st.markdown("**Häufige Begriffe:** " + ", ".join(f"{_e(b)} ({n})" for b, n in a["begriffe"][:15]))
    ki = _ki(h)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    if sp[0].button("✨ Mit KI zusammenfassen", key=K + "an_ki_btn", disabled=ki is None,
                    help="Gemini (kostenlos) – fasst die 150 meistgelikten Kommentare zusammen." if ki else
                    "Kein KI-Zugang (GEMINI_API_KEY)."):
        with st.spinner("KI fasst zusammen …"):
            obj, fehler = YAN.mit_ki(ki, YAN.ki_prompt_kommentare(v["titel"], erg["daten"]["kommentare"]),
                                     YAN.ki_kommentare_pruefen)
        if fehler:
            st.warning(fehler)
        else:
            ss[K + "an_ki"] = obj
    k_obj = ss.get(K + "an_ki")
    if k_obj:
        st.markdown("**KI-Zusammenfassung** <span class='yt-schaetzung'>KI</span>", unsafe_allow_html=True)
        if k_obj["zusammenfassung"]:
            st.markdown(_e(k_obj["zusammenfassung"]))
        for gr in k_obj["gruppen"]:
            st.markdown(f"- **{_e(gr['name'])}**" + (f" (~{round(gr['anteil'])} %)" if gr["anteil"] is not None else "")
                        + f": {_e(gr['kern'])}")
        _liste("Offene Fragen", k_obj["offene_fragen"])
        _liste("Wünsche", k_obj["wuensche"])
        _liste("Kritikpunkte", k_obj["kritikpunkte"])
        _liste("Chancen für ein eigenes Video", k_obj["chancen"])
        st.caption("KI-Auswertung kann Fehler enthalten – mit den Beispielen oben abgleichen.")
    if sp[1].button("📌 Analyse merken", key=K + "an_merken",
                    help="Für die Better-Video-Konzepte und zum späteren Nachlesen."):
        kurz = {k: a[k] for k in ("anzahl", "echt", "spam", "begriffe", "fragen", "wuensche")}
        kurz["gruppen"] = {x: {"name": y["name"], "anzahl": y["anzahl"], "anteil": y["anteil"],
                               "beispiele": [b["text"] for b in y["beispiele"][:3]]} for x, y in g.items()}
        if _merken(h, "kommentare", v["titel"], v["url"], kurz, k_obj):
            st.rerun()


# ---------------------------------------------------------------------------------------------------- Transkript
def transkript(h, d):
    ss = st.session_state
    st.markdown("**Transkript-Analyse** – eigener Text oder Untertiteldatei (SRT/VTT)")
    st.caption("Fremde Untertitel gibt die YouTube-API nicht heraus. Für eigene Videos: in YouTube Studio unter "
               "„Untertitel“ herunterladen; sonst nur Texte verwenden, die du nutzen darfst.")
    datei = st.file_uploader("SRT- oder VTT-Datei", type=["srt", "vtt", "txt"], key=K + "tr_datei")
    text = st.text_area("… oder Text einfügen", key=K + "tr_text", height=160, max_chars=200_000)
    titel = st.text_input("Titel (optional)", key=K + "tr_titel", max_chars=120)
    fragen = []
    gemerkt = [x for x in d.get("analysen") or [] if x.get("art") == "kommentare"]
    if gemerkt:
        wahl = st.selectbox("Offene Fragen aus einer gemerkten Kommentar-Analyse abgleichen (optional)",
                            [""] + [x["id"] for x in gemerkt], key=K + "tr_bezug",
                            format_func=lambda i: "– keine –" if not i else next(
                                f"{x['titel']} ({x['datum']})" for x in gemerkt if x["id"] == i))
        if wahl:
            x = next(y for y in gemerkt if y["id"] == wahl)
            fragen = (x.get("ergebnis") or {}).get("fragen") or []
            fragen += ((x.get("ki") or {}).get("offene_fragen") or [])
    roh = ""
    if datei is not None:
        try:
            roh = datei.getvalue().decode("utf-8-sig", errors="replace")
        except Exception:
            roh = ""
    roh = roh or text or ""
    if st.button("📝 Transkript auswerten", key=K + "tr_btn", type="primary", disabled=not roh.strip()):
        t = YAN.transkript_parsen(roh)
        if not t["segmente"]:
            st.warning("Kein auswertbarer Text gefunden.")
        else:
            ss[K + "tr_erg"] = {"t": t, "a": YAN.transkript_auswerten(t, fragen), "titel": titel or
                                (datei.name if datei is not None else ""), "fragen": fragen}
            ss.pop(K + "tr_ki", None)
    erg = ss.get(K + "tr_erg")
    if not erg:
        return
    a = erg["a"]
    _kpis([("Wörter", f"{a['woerter']:,}".replace(",", "."), f"{a['segmente']} Abschnitte · {a['art'].upper()}", ""),
           ("Dauer", YAN.zeit_text(a["dauer_s"]), "aus den Zeitmarken" if a["dauer_s"] else "ohne Zeitmarken", ""),
           ("Sprechtempo", f"{round(a['wpm'])} W/min" if a["wpm"] else "–", "130–160 ist gut verständlich", ""),
           ("Mögliche Lücken", str(len(a["luecken"])), "Fragen ohne passende Begriffe im Text" if fragen else
            "keine Fragen zum Abgleich", "")])
    _liste("Kernsätze (nach Begriffsgewicht, ohne KI)", a["kernsaetze"])
    if a["kapitel"]:
        st.markdown("**Kapitelvorschlag (alle ~2,5 Minuten, Titel aus häufigen Begriffen)**")
        st.code("\n".join(f"{YAN.zeit_text(k['start'])} {k['titel']}" for k in a["kapitel"]), language=None)
    if a["begriffe"]:
        st.markdown("**Häufige Begriffe:** " + ", ".join(f"{_e(b)} ({n})" for b, n in a["begriffe"]))
    _liste("Mögliche Lücken (Fragen der Zuschauer, deren Begriffe im Transkript nicht vorkommen)", a["luecken"])
    ki = _ki(h)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    if sp[0].button("✨ Mit KI auswerten", key=K + "tr_ki_btn", disabled=ki is None):
        with st.spinner("KI wertet aus …"):
            obj, fehler = YAN.mit_ki(ki, YAN.ki_prompt_transkript(erg["titel"], erg["t"], erg["fragen"]),
                                     YAN.ki_transkript_pruefen)
        if fehler:
            st.warning(fehler)
        else:
            ss[K + "tr_ki"] = obj
    k_obj = ss.get(K + "tr_ki")
    if k_obj:
        st.markdown("**KI-Auswertung** <span class='yt-schaetzung'>KI</span>", unsafe_allow_html=True)
        if k_obj["zusammenfassung"]:
            st.markdown(_e(k_obj["zusammenfassung"]))
        _liste("Kernaussagen", k_obj["kernaussagen"])
        _liste("Lücken", k_obj["luecken"])
        _liste("Schwächen", k_obj["schwaechen"])
        if k_obj["kapitel"]:
            st.code("\n".join(f"{k['zeit']} {k['titel']}".strip() for k in k_obj["kapitel"]), language=None)
    if sp[1].button("📌 Analyse merken", key=K + "tr_merken"):
        kurz = {k: a[k] for k in ("woerter", "dauer_s", "wpm", "begriffe", "kernsaetze", "kapitel", "luecken")}
        if _merken(h, "transkript", erg["titel"] or "Transkript", erg["titel"] or "", kurz, k_obj):
            st.rerun()


# ---------------------------------------------------------------------------------------------------- Gemerkt
def gemerkt(h, d):
    liste = list(reversed(d.get("analysen") or []))
    if not liste:
        return
    with st.expander(f"📌 Gemerkte Analysen ({len(liste)})"):
        for x in liste:
            c = st.columns([5, 1])
            c[0].markdown(f"**{_e(x['titel'] or '–')}** · {'Kommentare' if x['art'] == 'kommentare' else 'Transkript'}"
                          f" · {_e(x['datum'])}" + (" · mit KI" if x.get("ki") else ""))
            if c[1].button("Löschen", key=K + f"an_del_{x['id']}"):
                if _speichern(h, lambda y, i=x["id"]: dict(y, analysen=[a for a in y["analysen"] if a["id"] != i]),
                              "Analyse gelöscht"):
                    st.rerun()


def bereich(h, d):
    teil = st.segmented_control("Analyse", TEILE, default=TEILE[0], key=K + "an_teil",
                                label_visibility="collapsed") or TEILE[0]
    {"Kommentare": kommentare, "Transkript": transkript}[teil](h, d)
    gemerkt(h, d)
