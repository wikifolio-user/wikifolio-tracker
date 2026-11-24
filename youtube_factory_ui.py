"""Faceless YouTube - Bereich "Video Factory" (aus youtube_ui aufgerufen).

Neues Video: Auftrag (KI-Skript ueber Gemini) oder eigenes Skript, Laenge, Format, Qualitaet, Kostenvoranschlag ->
Projekt mit Skript und Storyboard (in der App, schnell). Projekte: Fortschritt je Schritt, Szenen bearbeiten,
Rendern im Hintergrund (GitHub Actions, youtube-render.yml), Vorschau und Downloads, Qualitaetsbericht, Freigabe,
Kosten ins Kassenbuch. Gerendert wird nie auf dem Geraet; veroeffentlicht wird hier nichts.
Speicher: state/youtube/projekte/<id>.json, Index in state/youtube.json unter "projekte".
h zusaetzlich: "ki": () -> KI-Anbieter|None, "render_starten": (pid) -> (ok, text),
               "release_laden": (asset_id) -> bytes"""
import datetime
import html
import logging
import tempfile

import streamlit as st

import ui_stil as UI
import youtube_finanzen as YF
from video_factory import kosten as KO
from video_factory import pipeline as PL
from video_factory import skript as SK

K = "yt_vf_"
STATUS_TEXT = {"entwurf": "Entwurf", "in_arbeit": "in Arbeit", "warteschlange": "wartet aufs Rendern",
               "rendert": "wird gerendert", "fehler": "Fehler", "freigabe_noetig": "fertig – Freigabe nötig",
               "blockiert": "fertig – blockiert", "freigegeben": "freigegeben"}
SYMBOL = {"ok": "✅", "offen": "⚪", "laeuft": "⏳", "fehler": "⛔"}
BEISPIEL = ("Erstelle ein professionelles deutsches YouTube-Video über die fünf besten KI-Tools für kleine "
            "Unternehmen. Verständliche Erklärungen, konkrete Einsatzbeispiele, ohne Gesicht.")
SKRIPT_HILFE = ("Absätze werden Szenen. Kapitel beginnen mit „## Titel“. Optional am Ende eines Absatzes "
                "„[bild: english search words]“ für die Bildsuche.")


def _e(t):
    return html.escape(str(t if t is not None else ""))


def projekt_pfad(pid):
    return f"state/youtube/projekte/{pid}.json"


# ---------------------------------------------------------------------------------------------------- Speicher
def _projekt_laden(h, pid):
    try:
        p, ok = h["lesen"](h["upfad"](projekt_pfad(pid)), None)
    except Exception:
        p, ok = None, False
    return (p if isinstance(p, dict) and p.get("id") == pid else None), ok


def _projekt_speichern(h, p, text, status=None):
    """Projekt-Datei und Index-Eintrag schreiben. -> bool"""
    if not h.get("speichern"):
        st.session_state["yt_meldung"] = ("warn", "Speichern ist gerade nicht möglich (kein Datenspeicher).")
        return False
    if status:
        p["status"] = status
    try:
        ok1, _ = h["aktualisiere"](h["upfad"](projekt_pfad(p["id"])), lambda _alt: p, {},
                                   f"youtube projekt: {text} [skip ci]")
    except Exception as ex:
        logging.warning("Video Factory: Speichern: %s", ex)
        ok1 = False
    eintrag = {"id": p["id"], "titel": (p.get("skript") or {}).get("titel") or p["auftrag"][:60],
               "status": p["status"], "erstellt": p["erstellt"], "geaendert": PL.jetzt(), "dauer_min": p["dauer_min"]}

    def index(x):
        x = x if isinstance(x, dict) else {}
        liste = [y for y in x.get("projekte") or [] if y.get("id") != p["id"]]
        return dict(x, projekte=liste + [eintrag])
    try:
        ok2, _ = h["aktualisiere"](h["upfad"]("state/youtube.json"), index, {}, "youtube: projektliste [skip ci]")
    except Exception as ex:
        logging.warning("Video Factory: Index: %s", ex)
        ok2 = False
    st.session_state["yt_meldung"] = ("ok", f"Gespeichert: {text}.") if ok1 and ok2 else \
        ("warn", "Speichern fehlgeschlagen – bitte erneut versuchen.")
    return ok1 and ok2


# ---------------------------------------------------------------------------------------------------- Neues Video
def _neu(h, d):
    ss = st.session_state
    if K + "vorlage" in ss:                                  # Ideen-Transfer (vor den Widgets setzen)
        v = ss.pop(K + "vorlage")
        ss[K + "auftrag"], ss[K + "titel"] = v.get("auftrag", ""), v.get("titel", "")
    einst = d.get("einstellungen") or {}
    ki = None
    try:
        ki = h["ki"]() if h.get("ki") else None
    except Exception:
        ki = None
    quelle = st.segmented_control("Skript", ["ki", "eigen"], default="ki" if ki else "eigen", key=K + "quelle",
                                  format_func=lambda x: "KI-Skript aus Auftrag" if x == "ki" else "Eigenes Skript") or "eigen"
    if quelle == "ki":
        if not ki:
            st.warning("Kein KI-Zugang (GEMINI_API_KEY) eingerichtet – bitte „Eigenes Skript“ wählen.")
        auftrag = st.text_area("Auftrag", key=K + "auftrag", height=110, max_chars=2000, placeholder=BEISPIEL)
        titel, text = "", ""
    else:
        titel = st.text_input("Videotitel", key=K + "titel", max_chars=100)
        text = st.text_area("Skript", key=K + "text", height=260, max_chars=30000, help=SKRIPT_HILFE,
                            placeholder="Einstieg …\n\n## Kapitel 1\nErklärung … [bild: small business laptop]")
        auftrag = titel
    sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
    dauer = sp[0].slider("Länge (Minuten)", 1, 15, 5, key=K + "dauer", disabled=quelle == "eigen",
                         help="Beim eigenen Skript ergibt sich die Länge aus dem Text.")
    fmt = sp[1].segmented_control("Format", ["16:9", "9:16"], default="16:9", key=K + "fmt",
                                  format_func=lambda x: "Longform 16:9" if x == "16:9" else "Short 9:16") or "16:9"
    qual = sp[2].selectbox("Qualität", ["standard", "hoch", "entwurf"], key=K + "qual",
                           format_func={"standard": "Standard", "hoch": "Hoch (langsamer)", "entwurf": "Entwurf (schnell)"}.get)
    unter = st.toggle("Untertitel einbrennen (SRT/VTT gibt es immer)", value=True, key=K + "unter")
    posten, summe, im_budget = KO.voranschlag(einst, dauer, bool(ki))
    st.markdown("**Kostenvoranschlag** – Modus " + _e({"free": "Free", "balanced": "Balanced", "premium": "Premium"}
                                                      .get(einst.get("modus", "free"), "Free")))
    st.markdown("\n".join(f"- {a}: {b} – **{x:.2f} €**" for a, b, x in posten) + f"\n\n**Summe: {summe:.2f} €**")
    if not im_budget:
        st.error("Über der Budgetgrenze je Video – bitte das Budget in den Einstellungen anpassen.")
    bereit = im_budget and ((quelle == "ki" and ki and (auftrag or "").strip()) or
                            (quelle == "eigen" and (titel or "").strip() and (text or "").strip()))
    if st.button("Projekt anlegen und Skript erstellen", key=K + "anlegen_btn", type="primary", disabled=not bereit):
        try:
            skript = SK.aus_text(titel, text) if quelle == "eigen" else None
            p = PL.neues_projekt(auftrag, dauer if quelle == "ki" else max(0.5, SK.geschaetzte_dauer_s(skript) / 60),
                                 einst.get("sprache", "de"), fmt, qual, unter, skript=skript)
        except (ValueError, SK.SkriptFehler) as ex:
            st.error(str(ex))
            return
        with st.spinner("Erstelle Skript und Storyboard …" if quelle == "ki" else "Erstelle Storyboard …"):
            with tempfile.TemporaryDirectory() as ordner:
                p = PL.ausfuehren(p, {"ordner": ordner, "get": None, "ki": ki}, bis="storyboard")
        p["status"] = "fehler" if p["status"] == "fehler" else "entwurf"
        if _projekt_speichern(h, p, "Projekt angelegt"):
            ss[K + "wahl"] = p["id"]
            ss[K + "teil_neu"] = "Projekte"            # erst vor dem naechsten Aufbau des Schalters setzen
            for k in ("auftrag", "titel", "text"):
                ss.pop(K + k, None)
            st.rerun()
    st.caption("Skript und Storyboard entstehen sofort; Bilder, Stimme und Schnitt laufen danach im Hintergrund – "
               "nie auf dem Smartphone. Inhalte fremder Videos werden nicht übernommen.")


# ---------------------------------------------------------------------------------------------------- Projekte
@st.cache_data(ttl=3600, show_spinner=False, max_entries=6)
def _datei(_laden, asset_id):
    return _laden(asset_id)


def _szenen_bearbeiten(h, p, gesperrt):
    import pandas as pd
    df = pd.DataFrame([{"Nr": s["nr"], "Kapitel": s["kapitel"], "Sprechertext": s["text"], "Bildsuche (englisch)":
                        s.get("bild") or "", "Bild": (s.get("asset") or {}).get("anbieter") or "–"} for s in p["szenen"]])
    neu = st.data_editor(df, hide_index=True, width="stretch", key=K + f"szenen_{p['id']}", disabled=gesperrt or
                         ["Nr", "Kapitel", "Bild"], num_rows="fixed",
                         column_config={"Sprechertext": st.column_config.TextColumn(width="large")})
    if gesperrt:
        return
    geaendert_text, geaendert_bild = [], []
    for s, (_, z) in zip(p["szenen"], neu.iterrows()):
        if str(z["Sprechertext"]).strip() and str(z["Sprechertext"]).strip() != s["text"]:
            geaendert_text.append((s, str(z["Sprechertext"]).strip()))
        if str(z["Bildsuche (englisch)"]).strip() != (s.get("bild") or ""):
            geaendert_bild.append((s, str(z["Bildsuche (englisch)"]).strip()))
    if (geaendert_text or geaendert_bild) and st.button(
            f"{len(geaendert_text) + len(geaendert_bild)} Änderung(en) übernehmen", key=K + "szenen_btn", type="primary"):
        for s, t in geaendert_text:
            s["text"], s["audio"] = t, None
        for s, b in geaendert_bild:
            s["bild"], s["asset"], s["neu_suchen"] = b, None, True
        PL.zuruecksetzen(p, "bilder" if geaendert_bild else "stimme")
        if geaendert_text:
            PL.zuruecksetzen(p, "stimme")
        p["status"] = "entwurf"
        PL._log(p, f"Szenen geändert: {len(geaendert_text)} Text, {len(geaendert_bild)} Bildsuche – nur betroffene "
                   "Schritte werden neu ausgeführt.")
        if _projekt_speichern(h, p, "Szenen geändert"):
            st.rerun()


def _ergebnis(h, p):
    rel = (p.get("dateien") or {}).get("release") or {}
    assets = rel.get("assets") or {}
    if not assets:
        return
    st.markdown("**Ergebnis**")
    laden = h.get("release_laden")
    if not laden:
        st.caption("Dateien liegen als Release im State-Repo (" + _e(rel.get("tag")) + ").")
        return
    try:
        if "video.mp4" in assets:
            with st.spinner("Lade Video …"):
                st.video(_datei(laden, assets["video.mp4"]["id"]), format="video/mp4")
        bilder = [assets[f"thumbnail_{i}.jpg"]["id"] for i in (1, 2, 3) if f"thumbnail_{i}.jpg" in assets]
        if bilder:
            sp = st.columns(3)
            for i, aid in enumerate(bilder):
                sp[i].image(_datei(laden, aid), caption=f"Thumbnail {i + 1}", width="stretch")
        with st.container(horizontal=True, key=K + "reihe_downloads"):
            for name, typ in (("video.mp4", "video/mp4"), ("untertitel.srt", "text/plain"), ("untertitel.vtt", "text/vtt"),
                              ("beschreibung.txt", "text/plain"), ("lizenzen.json", "application/json")):
                if name in assets:
                    st.download_button(f"⬇️ {name}", _datei(laden, assets[name]["id"]), file_name=name, mime=typ,
                                       key=K + f"dl_{name}")
        if "beschreibung.txt" in assets:
            st.text_area("Titel und Beschreibung für YouTube", _datei(laden, assets["beschreibung.txt"]["id"])
                         .decode("utf-8"), height=220, key=K + f"beschr_{p['id']}")
    except Exception as ex:
        st.warning(f"Ergebnis konnte nicht geladen werden ({type(ex).__name__}).")


def _bericht(p):
    b = p.get("bericht")
    if not b:
        return
    st.markdown("**Qualitätsbericht**" + (" ⛔ blockiert – erst beheben" if b["blockiert"] else ""))
    sym = {"ok": "✅", "warn": "⚠️", "fehler": "⛔"}
    st.markdown("\n".join(f"- {sym[e]} **{_e(n)}:** {_e(t)}" for n, e, t in b["punkte"]))


def _projekt(h, d, pid):
    ss = st.session_state
    p, ok = _projekt_laden(h, pid)
    if not p:
        st.warning("Projekt nicht lesbar." if not ok else "Projekt nicht gefunden.")
        return
    st.markdown(f"### {_e((p.get('skript') or {}).get('titel') or p['auftrag'][:80])}")
    st.caption(f"Status: **{STATUS_TEXT.get(p['status'], p['status'])}** · {p['format']} · Qualität {p['qualitaet']} · "
               f"angelegt {p['erstellt'][:16].replace('T', ' ')} UTC · Kosten bisher {p['kosten']['summe']:.2f} €")
    st.markdown("**Fortschritt**")
    st.markdown("\n".join(f"- {SYMBOL.get(s['status'], '•')} {PL.SCHRITT_TEXT[n]}"
                          + (f" – {_e(s.get('meldung'))}" if s.get("meldung") else "")
                          for n, s in ((n, p["schritte"][n]) for n in PL.SCHRITTE)))
    laeuft = p["status"] in ("warteschlange", "rendert")
    if p.get("szenen"):
        with st.expander(f"Skript und Szenen ({len(p['szenen'])})", expanded=p["status"] in ("entwurf", "fehler")):
            if (p.get("skript") or {}).get("zu_pruefen"):
                st.warning("Vor Veröffentlichung prüfen: " + "; ".join(p["skript"]["zu_pruefen"]))
            _szenen_bearbeiten(h, p, laeuft)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    kann = p["schritte"]["storyboard"]["status"] == "ok" and not laeuft and p["status"] != "freigegeben"
    if sp[0].button("🎬 Rendern starten" if p["status"] != "fehler" else "🔁 Erneut versuchen", key=K + "render_btn",
                    type="primary", disabled=not kann):
        if _projekt_speichern(h, p, "Rendern angefordert", status="warteschlange"):
            ok_start, text = h["render_starten"](p["id"]) if h.get("render_starten") else (False, "nicht verbunden")
            ss["yt_meldung"] = ("ok", "Rendern gestartet – das dauert einige Minuten. Mit „Status aktualisieren“ "
                                      "den Fortschritt abrufen.") if ok_start else \
                ("warn", f"Automatischer Start nicht möglich ({text}). Das Projekt steht in der Warteschlange: der "
                         "Ersatzlauf rendert es spätestens in 6 Stunden – oder in GitHub unter Actions → „YouTube "
                         "Video rendern“ → „Run workflow“ starten.")
            st.rerun()
    if sp[1].button("🔄 Status aktualisieren", key=K + "status_btn"):
        st.cache_data.clear()
        st.rerun()
    _ergebnis(h, p)
    _bericht(p)
    if p["status"] == "freigabe_noetig" and not (p.get("bericht") or {}).get("blockiert"):
        geprueft = st.checkbox("Ich habe Fakten, Lizenzen und Inhalt geprüft.", key=K + f"geprueft_{p['id']}")
        if st.button("✅ Freigeben", key=K + "frei_btn", disabled=not geprueft):
            PL._log(p, "Freigegeben (manuell geprüft).")
            if _projekt_speichern(h, p, "Freigegeben", status="freigegeben"):
                st.rerun()
        st.caption("Freigegebene Videos lädst du vorerst selbst bei YouTube hoch (Upload über die App folgt mit "
                   "der YouTube-Verbindung). Bei KI-Stimme und realistisch wirkenden Inhalten im YouTube Studio "
                   "„veränderte oder synthetische Inhalte“ angeben.")
    summe = p["kosten"]["summe"]
    if summe > 0 and not p.get("kosten_gebucht"):
        if st.button(f"Kosten {summe:.2f} € ins Kassenbuch", key=K + "kosten_btn"):
            b = YF.neue_buchung(datetime.date.today().isoformat(), "ausgabe", "produktion", summe, None,
                                f"Video Factory: {p['id']}")

            def buchen(x):
                x = x if isinstance(x, dict) else {}
                return dict(x, buchungen=list(x.get("buchungen") or []) + [b])
            h["aktualisiere"](h["upfad"]("state/youtube.json"), buchen, {}, "youtube: produktionskosten [skip ci]")
            p["kosten_gebucht"] = True
            _projekt_speichern(h, p, "Kosten gebucht")
            st.rerun()
    elif summe == 0:
        st.caption("Produktionskosten: 0,00 € (alles im kostenlosen Rahmen) – nichts zu buchen.")
    with st.expander("Protokoll"):
        for e in reversed(p.get("protokoll") or []):
            st.markdown(f"- {'⛔ ' if e['art'] == 'fehler' else ''}{e['zeit'][:16].replace('T', ' ')} – {_e(e['text'])}")
    if st.checkbox("Projekt löschen", key=K + f"loesch_{p['id']}") and st.button("Endgültig löschen", key=K + "loesch_btn"):
        def ohne(x):
            x = x if isinstance(x, dict) else {}
            return dict(x, projekte=[y for y in x.get("projekte") or [] if y.get("id") != p["id"]])
        h["aktualisiere"](h["upfad"]("state/youtube.json"), ohne, {}, "youtube: projekt entfernt [skip ci]")
        ss.pop(K + "wahl", None)
        ss["yt_meldung"] = ("ok", "Projekt aus der Liste entfernt (die Dateien im State-Repo bleiben erhalten).")
        st.rerun()


def bereich(h, d):
    ss = st.session_state
    if ss.get(K + "teil_neu"):
        ss[K + "teil"] = ss.pop(K + "teil_neu")
    ss.setdefault(K + "teil", "Projekte" if d.get("projekte") else "Neues Video")
    teil = st.segmented_control("Video Factory", ["Neues Video", "Projekte"], key=K + "teil",
                                label_visibility="collapsed") or "Neues Video"
    if teil == "Neues Video":
        _neu(h, d)
        return
    liste = sorted(d.get("projekte") or [], key=lambda x: x.get("geaendert") or x.get("erstellt") or "", reverse=True)
    if not liste:
        st.info("Noch keine Projekte – unter „Neues Video“ anlegen.")
        return
    ids = [x["id"] for x in liste]
    if ss.get(K + "wahl") not in ids:
        ss[K + "wahl"] = ids[0]
    je = {x["id"]: x for x in liste}
    st.selectbox("Projekt", ids, key=K + "wahl", format_func=lambda i: f"{je[i].get('titel') or i} · "
                 f"{STATUS_TEXT.get(je[i].get('status'), je[i].get('status'))}")
    _projekt(h, d, ss[K + "wahl"])
