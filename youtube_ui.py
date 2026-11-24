"""Faceless YouTube Automation - Ansicht (Geschaeftsideen -> 🎬 Faceless YouTube), nur fuer den Admin.

Phase 1: Ueberblick (tatsaechliche Kennzahlen, Pipeline-Status), Recherche (gespeicherte Ideen; Trend-Radar ab
Phase 2), Analyse und Video Factory (Status: was ab welcher Phase kommt und was dafuer fehlt), Finanzen
(Finanzrechner mit Szenarien = Schaetzungen, Kassenbuch mit tatsaechlichen Einnahmen/Ausgaben, Kanaele) und
Einstellungen (Produktionsmodus, Budgets, Verbindungsstatus ohne Schluesselwerte).

Gespeichert wird in state/youtube.json im Benutzerbereich: {"kanaele", "buchungen", "ideen", "einstellungen"}.
Es wird nichts erfunden: Bereiche ohne angebundene Datenquelle sagen das, statt Ergebnisse vorzutaeuschen.
h = {"lesen": (pfad, default) -> (daten, ok), "aktualisiere": (pfad, aendern, default, msg) -> (ok, neu),
     "upfad": (basis) -> pfad, "speichern": bool, "zugaenge": {name: bool}}"""
import datetime
import html
import logging
import uuid

import streamlit as st

import ui_stil as UI
import youtube_finanzen as YF
import youtube_radar as YR

K = "yt_"
DATEI = "state/youtube.json"
LEER = {"kanaele": [], "buchungen": [], "ideen": [], "einstellungen": {}, "radar": [], "projekte": []}
RADAR_DATEI = "state/youtube_radar.json"
BEREICHE = ["Überblick", "Recherche", "Analyse", "Video Factory", "Finanzen", "Einstellungen"]
MODI = {"free": "Free – lokale/offene Werkzeuge, kostenlose APIs", "balanced": "Balanced – kostenlos + ausgewählte "
        "Premium-Dienste", "premium": "Premium – kommerzielle Dienste (nur mit Budget und Freigabe)"}
STANDARD_EINST = {"modus": "free", "budget_monat": 0.0, "budget_video": 0.0, "sprache": "de", "markt": "DE"}
ZUGAENGE = [  # (Secret-Name, wofuer, Phase, kostenlos?)
    ("YOUTUBE_API_KEY", "Trend-Radar, Video-Statistiken, Kommentare (YouTube Data API v3)", 2, "kostenlos, Kontingent"),
    ("GEMINI_API_KEY", "Skript, Storyboard, Kommentar-Gruppierung, Better-Video-Konzepte", 3, "kostenlos (Flash)"),
    ("PEXELS_API_KEY", "Stock-Fotos und -Videos (optional; ohne: Wikimedia Commons / Openverse)", 4, "kostenlos"),
    ("PIXABAY_API_KEY", "Stock-Fotos und -Videos (optional)", 4, "kostenlos"),
]
PIPELINE = [  # (Schritt, Phase, benoetigter Zugang oder None)
    ("Kanal-Radar (RSS, ohne Schlüssel)", 1, None), ("Viral Outliers & Success-Score (beobachtete Kanäle)", 1, None),
    ("Weltweite Trends & Suche", 2, "YOUTUBE_API_KEY"), ("Kanalgröße & Kommentare", 2, "YOUTUBE_API_KEY"),
    ("Einnahmepotenzial schätzen", 2, "YOUTUBE_API_KEY"), ("Nische untersuchen", 2, "YOUTUBE_API_KEY"),
    ("Kommentare analysieren", 3, "YOUTUBE_API_KEY"), ("Transkript auswerten (eigener Text/SRT)", 3, "GEMINI_API_KEY"),
    ("Affiliate-Programme (mit Quelle)", 3, None), ("Eigene Idee / Better Video", 3, "GEMINI_API_KEY"),
    ("Skript (KI oder eigenes) & Storyboard", 1, None), ("Bildmaterial (lizenzfrei oder eigene Grafik)", 1, None),
    ("KI-Stimme (Piper, lokal)", 1, None), ("Schnitt, Untertitel, MP4 (FFmpeg)", 1, None),
    ("Thumbnails & Qualitätskontrolle", 1, None), ("Freigabe & YouTube-Upload (als Entwurf)", 7, "YouTube-OAuth"),
    ("Einnahmen ins Kassenbuch", 1, None),
]
PHASE_FERTIG = 1

CSS = """<style>
.yt-raster { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin:6px 0 10px; }
@media (max-width: 1000px) { .yt-raster { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width: 420px) { .yt-raster { grid-template-columns:1fr; } }
.yt-kpi { border:1px solid rgba(255,255,255,.12); border-radius:14px; padding:10px 12px; background:rgba(255,255,255,.03);
    min-width:0; }
.yt-kpi .t { font-size:.72rem; color:#A9ACB0; text-transform:uppercase; letter-spacing:.4px; }
.yt-kpi .w { font-size:1.3rem; font-weight:800; color:#ffffff; font-variant-numeric:tabular-nums; margin-top:2px; }
.yt-kpi .s { font-size:.72rem; color:#A9ACB0; margin-top:2px; }
.yt-pos { color:#34D399 !important; } .yt-neg { color:#F87171 !important; }
.yt-schritt { display:grid; grid-template-columns:auto 1fr auto; gap:4px 10px; font-size:.84rem; align-items:center; }
.yt-schritt .st { font-size:.72rem; font-weight:700; padding:1px 8px; border-radius:10px; border:1px solid currentColor;
    white-space:nowrap; }
.yt-schaetzung { display:inline-block; font-size:.7rem; font-weight:700; color:#FBBF24; border:1px solid #FBBF24;
    border-radius:8px; padding:1px 7px; margin-left:6px; }
</style>"""


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _eur(x, n=0):
    if x is None:
        return "–"
    return f"{x:,.{n}f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x, n=1):
    return "–" if x is None else f"{x:,.{n}f} %".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------------------------------- Speicher
def _laden(h):
    try:
        d, ok = h["lesen"](h["upfad"](DATEI), dict(LEER))
    except Exception:
        d, ok = dict(LEER), False
    d = d if isinstance(d, dict) else {}
    return {k: (d.get(k) if isinstance(d.get(k), type(v)) else type(v)()) for k, v in LEER.items()}, ok


def _speichern(h, aendern, text):
    """aendern(daten) -> neue daten (mit frisch gelesenem Stand, Versionspruefung)."""
    if not h.get("speichern"):
        st.session_state[K + "meldung"] = ("warn", "Speichern ist gerade nicht möglich (kein Datenspeicher).")
        return False

    def f(alt):
        alt = alt if isinstance(alt, dict) else {}
        basis = {k: (alt.get(k) if isinstance(alt.get(k), type(v)) else type(v)()) for k, v in LEER.items()}
        return aendern(basis)
    try:
        ok, _ = h["aktualisiere"](h["upfad"](DATEI), f, dict(LEER), f"youtube: {text} [skip ci]")
    except Exception as ex:
        logging.warning("YouTube: Speichern fehlgeschlagen: %s", ex)
        ok = False
    st.session_state[K + "meldung"] = ("ok", f"Gespeichert: {text}.") if ok else \
        ("warn", "Speichern fehlgeschlagen – bitte erneut versuchen. Es wurde nichts überschrieben.")
    return bool(ok)


def _kpis(eintraege):
    st.markdown('<div class="yt-raster">' + "".join(
        f'<div class="yt-kpi"><div class="t">{_e(t)}</div><div class="w {css}">{w}</div>'
        f'<div class="s">{_e(s)}</div></div>' for t, w, s, css in eintraege) + "</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------------- Ueberblick
def _ueberblick(h, d):
    heute = datetime.date.today()
    gesamt = YF.auswertung(d["buchungen"])
    monat = YF.auswertung(d["buchungen"], von=heute.strftime("%Y-%m-01"))
    aktiv = [k for k in d["kanaele"] if k.get("status") == "aktiv"]
    _kpis([("Einnahmen (tatsächlich)", _eur(gesamt["einnahmen"]), f"davon {heute:%m/%Y}: {_eur(monat['einnahmen'])}", ""),
           ("Ausgaben (tatsächlich)", _eur(gesamt["ausgaben"]), f"davon {heute:%m/%Y}: {_eur(monat['ausgaben'])}", ""),
           ("Gewinn (tatsächlich)", _eur(gesamt["gewinn"]), f"ROI {_pct(gesamt['roi_pct'])}",
            "yt-pos" if gesamt["gewinn"] > 0 else "yt-neg" if gesamt["gewinn"] < 0 else ""),
           ("Kanäle / Ideen", f"{len(d['kanaele'])} / {len(d['ideen'])}", f"{len(aktiv)} aktiv", "")])
    st.caption("Nur tatsächlich erfasste Buchungen aus dem Kassenbuch – Prognosen aus dem Finanzrechner fließen hier "
               "nie ein.")
    st.markdown("**Automatisierungs-Pipeline – aktueller Stand**")
    zug = h.get("zugaenge") or {}
    zeilen = []
    for schritt, phase, braucht in PIPELINE:
        if phase <= PHASE_FERTIG:
            status, farbe = "verfügbar", "#34D399"
        elif braucht and braucht in zug and not zug[braucht]:
            status, farbe = f"Phase {phase} · {braucht} fehlt", "#FBBF24"
        else:
            status, farbe = f"Phase {phase}", "#A9ACB0"
        zeilen.append(f'<div>{"✅" if phase <= PHASE_FERTIG else "⏳"}</div><div>{_e(schritt)}</div>'
                      f'<div class="st" style="color:{farbe}">{_e(status)}</div>')
    st.markdown('<div class="yt-schritt">' + "".join(zeilen) + "</div>", unsafe_allow_html=True)
    st.caption("Jeder Schritt wird einzeln ausführbar. Was noch nicht gebaut oder nicht verbunden ist, steht hier so – "
               "es werden keine Ergebnisse vorgetäuscht.")


# ---------------------------------------------------------------------------------------------------- Recherche
def _recherche(h, d):
    teil = st.segmented_control("Recherche", ["Kanal-Radar", "Ideen"], default="Kanal-Radar", key=K + "rech_teil",
                                label_visibility="collapsed") or "Kanal-Radar"
    if teil == "Kanal-Radar":
        _radar(h, d)
    else:
        _ideen(h, d)


def _radar_laden(h):
    try:
        r, ok = h["lesen"](h["upfad"](RADAR_DATEI), {})
    except Exception:
        r, ok = {}, False
    return (r if isinstance(r, dict) else {}), ok


def _radar_abrufen(h, d):
    """Alle beobachteten Kanaele jetzt abrufen und als Momentaufnahme speichern."""
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    ergebnis = {}

    def aendern(alt):
        neu = alt if isinstance(alt, dict) else {}
        ok, fehler = 0, []
        for k in d["radar"]:
            try:
                neu = YR.einfuegen(neu, YR.abrufen(k["id"], h["get"]), jetzt)
                ok += 1
            except YR.RadarFehler as ex:
                neu = YR.fehler_merken(neu, k["id"], str(ex), jetzt)
                fehler.append(f"{k.get('name') or k['id']}: {ex}")
        ergebnis.update(ok=ok, fehler=fehler)
        return neu
    try:
        gespeichert, _ = h["aktualisiere"](h["upfad"](RADAR_DATEI), aendern, {}, "youtube: radar abgerufen [skip ci]")
    except Exception as ex:
        logging.warning("Radar: %s", ex)
        gespeichert = False
    text = f"{ergebnis.get('ok', 0)} von {len(d['radar'])} Kanälen abgerufen" + (
        "" if gespeichert else " – Speichern fehlgeschlagen")
    if ergebnis.get("fehler"):
        text += ". Fehler: " + "; ".join(ergebnis["fehler"])
    st.session_state[K + "meldung"] = ("ok" if gespeichert and not ergebnis.get("fehler") else "warn", text)


def _radar(h, d):
    st.markdown("**Kanal-Radar** – beobachtete Kanäle über den öffentlichen YouTube-RSS-Feed (ohne Schlüssel)")
    with st.expander("➕ Kanal beobachten", expanded=not d["radar"]):
        sp = st.columns([3, 1, 2]) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        eingabe = sp[0].text_input("Kanal-ID oder Kanal-Adresse mit /channel/UC…", key=K + "r_kanal",
                                   placeholder="UC…  (Kanal → Mehr → Kanal teilen → Kanal-ID kopieren)")
        markt = sp[1].selectbox("Markt", ["US", "DE", "UK", "AT", "CH", "Global"], key=K + "r_markt")
        nische = sp[2].text_input("Nische", key=K + "r_nische", max_chars=60)
        if st.button("Kanal hinzufügen", key=K + "r_add_btn", disabled=not (eingabe or "").strip()):
            try:
                cid = YR.kanal_id(eingabe)
                feed = YR.abrufen(cid, h["get"]) if h.get("get") else {"name": cid, "videos": []}
            except YR.RadarFehler as ex:
                st.error(str(ex))
                return
            eintrag = {"id": cid, "name": feed["name"] or cid, "markt": markt, "nische": (nische or "").strip()}

            def neu_kanal(x):
                if any(k["id"] == cid for k in x["radar"]):
                    return x
                return dict(x, radar=x["radar"] + [eintrag])
            if _speichern(h, neu_kanal, f"Kanal {eintrag['name']} im Radar"):
                st.session_state.pop(K + "r_kanal", None)
                st.rerun()
    if not d["radar"]:
        st.caption("Noch keine Kanäle im Radar. Tipp: erfolgreiche Faceless-Kanäle deiner Nische aus den USA und "
                   "Deutschland eintragen – der Agent misst dann täglich Aufrufe und Wachstum.")
        return
    radar, ok = _radar_laden(h)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    if sp[0].button("🔄 Jetzt abrufen", key=K + "r_abruf_btn", disabled=not h.get("get"),
                    help="Lädt die Feeds aller Kanäle und speichert eine Momentaufnahme."):
        with st.spinner("Lade Feeds …"):
            _radar_abrufen(h, d)
        st.rerun()
    kan = (radar.get("kanaele") or {})
    letzte = max((k.get("abruf") or "" for k in kan.values()), default="")
    sp[1].caption(f"Letzte Momentaufnahme: {letzte[:16].replace('T', ' ') or '–'} UTC · täglich automatisch "
                  "(Workflow „YouTube Kanal-Radar“)")
    with st.expander(f"Beobachtete Kanäle ({len(d['radar'])})"):
        for k in d["radar"]:
            info = kan.get(k["id"]) or {}
            c = st.columns([4, 1])
            c[0].markdown(f"**{_e(k['name'])}** · {_e(k.get('markt'))} · {_e(k.get('nische') or '–')}"
                          + (f"  \n⚠️ {_e(info['fehler'])}" if info.get("fehler") else ""))
            if c[1].button("Entfernen", key=K + f"r_del_{k['id']}"):
                if _speichern(h, lambda x, cid=k["id"]: dict(x, radar=[y for y in x["radar"] if y["id"] != cid]),
                              "Kanal aus dem Radar entfernt"):
                    st.rerun()
    zeilen = YR.kennzahlen(radar, datetime.datetime.now(datetime.timezone.utc)) if ok else []
    if not zeilen:
        st.info("Noch keine Momentaufnahme – „Jetzt abrufen“ drücken oder auf den täglichen Lauf warten.")
        return
    namen = {k["id"]: k["name"] for k in d["radar"]}
    markt_je = {k["id"]: k.get("markt") for k in d["radar"]}
    sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
    sicht = sp[0].segmented_control("Ansicht", ["Viral Outliers", "Success-Ranking", "Wachstum"],
                                    default="Viral Outliers", key=K + "r_sicht") or "Viral Outliers"
    fmt = sp[1].segmented_control("Format", ["Longform", "Shorts", "Alle"], default="Longform", key=K + "r_fmt") or "Alle"
    maerkte = sorted({m for m in markt_je.values() if m})
    m_wahl = sp[2].multiselect("Markt", maerkte, key=K + "r_mf", placeholder="alle Märkte")
    liste = [z for z in zeilen if z["kanal"] in namen and (fmt == "Alle" or z["shorts"] == (fmt == "Shorts"))
             and (not m_wahl or markt_je.get(z["kanal"]) in m_wahl)]
    if sicht == "Viral Outliers":
        liste = sorted([z for z in liste if z["outlier"] is not None], key=lambda z: -z["outlier"])
    elif sicht == "Success-Ranking":
        liste = sorted([z for z in liste if z["score"] is not None], key=lambda z: -z["score"])
    else:
        liste = sorted([z for z in liste if z["wachstum_pro_tag"] is not None], key=lambda z: -z["wachstum_pro_tag"])
    if not liste:
        st.info({"Viral Outliers": "Für Outlier braucht es je Kanal mindestens 3 Vergleichsvideos desselben Formats.",
                 "Success-Ranking": "Noch keine bewertbaren Videos.",
                 "Wachstum": "Gemessenes Wachstum gibt es erst ab der zweiten Momentaufnahme, mindestens 12 Stunden "
                                        "nach der ersten – eine Momentaufnahme allein ist kein Wachstum."}[sicht])
        return
    import pandas as pd
    df = pd.DataFrame([{"Titel": z["titel"], "Kanal": namen.get(z["kanal"], z["kanal"]),
                        "Format": "Short" if z["shorts"] else "Longform", "Aufrufe": z["views"],
                        "Alter (Tage)": round(z["alter_tage"], 1) if z["alter_tage"] else None,
                        "Aufrufe/Tag": round(z["views_pro_tag"]) if z["views_pro_tag"] else None,
                        "Outlier ×": round(z["outlier"], 1) if z["outlier"] else None,
                        "Gemessen/Tag": round(z["wachstum_pro_tag"]) if z["wachstum_pro_tag"] is not None else None,
                        "Likes %": round(z["engagement_pct"], 2) if z["engagement_pct"] is not None else None,
                        "Score": z["score"], "vorläufig": "ja" if z["vorlaeufig"] else "",
                        "Werbung (Schätzung) €": "{:,.0f}–{:,.0f}".format(*YR.werbung_schaetzung(z["views"]))
                        .replace(",", ".") if z["views"] else "–", "Link": z["url"], "ID": z["id"]}
                       for z in liste[:200]])
    for spalte in ("Alter (Tage)", "Aufrufe/Tag", "Outlier ×", "Gemessen/Tag", "Likes %"):   # fehlend = leer
        df[spalte] = pd.to_numeric(df[spalte], errors="coerce")
    ev = st.dataframe(df, hide_index=True, width="stretch", key=K + "r_tab", on_select="rerun",
                      selection_mode="single-row",
                      column_config={"ID": None, "Link": st.column_config.LinkColumn("Link", display_text="öffnen"),
                                     "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100,
                                                                              format="%.0f")})
    st.caption("Outlier × = Aufrufe pro Tag gegenüber dem Median der anderen Videos desselben Kanals und Formats "
               "(nur die letzten 15 Videos aus dem Feed). Score 0–100 je Format: 25 % Aufrufe/Alter, 20 % gemessenes "
               "Wachstum, 25 % Kanalvergleich, 15 % Engagement, 15 % Kanalgröße – fehlt ein Teil (Kanalgröße liefert der "
               "Feed nie), ist der Score „vorläufig“. Werbung: Spanne 1–5 € RPM, reine Schätzung.")
    if ev and ev.selection.rows:
        z = next(x for x in liste if x["id"] == df.iloc[ev.selection.rows[0]]["ID"])
        if st.button("💡 Als Idee speichern", key=K + "r_idee_btn"):
            idee = {"id": uuid.uuid4().hex[:8], "titel": z["titel"][:120], "nische": "", "markt":
                    markt_je.get(z["kanal"]) or "Global", "quelle": z["url"], "status": "neu",
                    "notiz": f"Aus dem Kanal-Radar: {namen.get(z['kanal'])} · {z['views']:,} Aufrufe"
                             .replace(",", ".") + (f" · Outlier ×{z['outlier']:.1f}" if z["outlier"] else "")
                             + " – nur als Inspiration, eigenes Konzept nötig.", "datum": datetime.date.today().isoformat()}

            def neu_idee(x):
                if any(y.get("quelle") == idee["quelle"] for y in x["ideen"]):
                    return x
                return dict(x, ideen=x["ideen"] + [idee])
            if _speichern(h, neu_idee, "Idee aus dem Radar gespeichert"):
                st.rerun()


def _ideen(h, d):
    st.markdown("**Gespeicherte Ideen**")
    with st.expander("➕ Idee speichern", expanded=not d["ideen"]):
        titel = st.text_input("Titel / Videoidee", key=K + "idee_titel", max_chars=120)
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        nische = sp[0].text_input("Nische", key=K + "idee_nische", max_chars=60)
        markt = sp[1].selectbox("Markt", ["DE", "AT", "CH", "US", "UK", "CA", "AU", "Global"], key=K + "idee_markt")
        quelle = sp[2].text_input("Quelle / Link (optional)", key=K + "idee_quelle", max_chars=300)
        notiz = st.text_area("Notiz", key=K + "idee_notiz", max_chars=1000, height=80)
        if st.button("Idee speichern", key=K + "idee_btn", disabled=not (titel or "").strip()):
            idee = {"id": uuid.uuid4().hex[:8], "titel": titel.strip(), "nische": nische.strip(), "markt": markt,
                    "quelle": quelle.strip(), "notiz": notiz.strip(), "status": "neu",
                    "datum": datetime.date.today().isoformat()}
            def neu_idee(x):                         # gleiche Idee nur einmal (auch bei Doppeltippen)
                if any(y["titel"].lower() == idee["titel"].lower() for y in x["ideen"]):
                    return x
                return dict(x, ideen=x["ideen"] + [idee])
            if _speichern(h, neu_idee, "Idee gespeichert"):
                for k in ("idee_titel", "idee_nische", "idee_quelle", "idee_notiz"):
                    st.session_state.pop(K + k, None)
                st.rerun()
    if not d["ideen"]:
        st.caption("Noch keine Ideen gespeichert.")
        return
    status_txt = {"neu": "neu", "pruefen": "in Prüfung", "geplant": "geplant", "verworfen": "verworfen"}
    for i in sorted(d["ideen"], key=lambda x: x.get("datum") or "", reverse=True):
        with st.container(border=True, key=K + f"idee_box_{i['id']}"):
            st.markdown(f"**{_e(i['titel'])}**  \n{_e(i.get('nische') or '–')} · {_e(i.get('markt'))} · "
                        f"{_e(i.get('datum'))}" + (f" · [Quelle]({i['quelle']})" if str(i.get('quelle', '')).startswith("http") else ""))
            if i.get("notiz"):
                st.caption(i["notiz"])
            sp = st.columns(2)
            neu = sp[0].selectbox("Status", list(status_txt), index=list(status_txt).index(i.get("status", "neu"))
                                  if i.get("status") in status_txt else 0, format_func=status_txt.get,
                                  key=K + f"idee_st_{i['id']}", label_visibility="collapsed")
            if neu != i.get("status"):
                if _speichern(h, lambda x, iid=i["id"], n=neu: dict(x, ideen=[dict(y, status=n) if y["id"] == iid else y
                                                                             for y in x["ideen"]]), "Status der Idee"):
                    st.rerun()
            if sp[1].button("Löschen", key=K + f"idee_del_{i['id']}"):
                if _speichern(h, lambda x, iid=i["id"]: dict(x, ideen=[y for y in x["ideen"] if y["id"] != iid]),
                              "Idee gelöscht"):
                    st.rerun()


# ---------------------------------------------------------------------------------------------------- Analyse / Factory
def _ausblick(h, titel, punkte, phase, braucht):
    zug = h.get("zugaenge") or {}
    st.markdown(f"**{titel}** – kommt in Phase {phase}")
    st.markdown("\n".join(f"- {p}" for p in punkte))
    fehlend = [b for b in braucht if b in zug and not zug[b]]
    if fehlend:
        st.warning("Dafür fehlt noch: " + ", ".join(fehlend) + " (siehe „Einstellungen“).")
    elif braucht:
        st.caption("Benötigte Zugänge: " + ", ".join(f"{b} ✅" for b in braucht))


def _analyse(h, d):
    _ausblick(h, "Analyse-Agenten", [
        "**Kommentar-Analyse:** öffentliche Kommentare über die offizielle API, Gruppen (Lob, Kritik, offene Fragen, "
        "Wünsche), Häufigkeit, Beispiele, Spam-Filter",
        "**Transkript-Analyse:** eingefügter Text oder SRT/VTT-Datei (fremde Untertitel gibt die API nicht heraus), "
        "Kernaussagen, Lücken, Kapitel",
        "**Better Video Generator:** drei eigenständige Konzepte aus Thema, Kommentaren und eigener Recherche – keine "
        "Übersetzung oder Paraphrase", "**Affiliate-Finder:** nur Programme mit offizieller Quelle und Prüfdatum"],
        3, ["YOUTUBE_API_KEY", "GEMINI_API_KEY"])


def _factory(h, d):
    import youtube_factory_ui
    youtube_factory_ui.bereich(h, d)


# ---------------------------------------------------------------------------------------------------- Finanzen
def _rechner():
    ss = st.session_state
    st.markdown('**Finanzrechner** <span class="yt-schaetzung">Schätzung</span>', unsafe_allow_html=True)
    felder = [("views_monat", "Monatliche Views", 1000.0, "%.0f"), ("rpm", "RPM (€ je 1.000 Views)", 0.5, "%.2f"),
              ("klickrate_pct", "Affiliate-Klickrate (%)", 0.1, "%.2f"), ("conversion_pct", "Conversion-Rate (%)", 0.1, "%.2f"),
              ("provision", "Provision je Verkauf (€)", 1.0, "%.2f"), ("sponsoring_monat", "Sponsoring je Monat (€)", 50.0, "%.0f"),
              ("sonstige_ein_monat", "Sonstige Einnahmen je Monat (€)", 10.0, "%.0f"),
              ("videos_monat", "Videos je Monat", 1.0, "%.0f"), ("kanaele", "Kanäle", 1.0, "%.0f"),
              ("produktion_monat", "Produktionskosten je Monat (€)", 10.0, "%.0f"),
              ("ki_monat", "KI-Tool-Kosten je Monat (€)", 5.0, "%.0f"),
              ("sonstige_kosten_monat", "Sonstige Kosten je Monat (€)", 5.0, "%.0f"),
              ("einmalig", "Einmalige Investitionen (€)", 50.0, "%.0f")]
    sp = st.columns(3) if not UI.ist_smartphone() else [st.container()]
    e = {}
    for i, (k, t, schritt, fmt) in enumerate(felder):
        ss.setdefault(K + "r_" + k, float(YF.STANDARD_EINGABEN[k]))
        e[k] = sp[i % len(sp)].number_input(t, min_value=0.0, step=schritt, format=fmt, key=K + "r_" + k)
    try:
        m = YF.monat(YF.pruefe(e))
        alle = YF.alle_szenarien(e)
    except ValueError as ex:
        st.warning(str(ex))
        return
    st.markdown("**Ein Monat mit diesen Werten (nach Aufnahme ins Partnerprogramm)**")
    _kpis([("YouTube-Umsatz", _eur(m["youtube"], 2), "Views / 1.000 × RPM", ""),
           ("Affiliate-Umsatz", _eur(m["affiliate"], 2), "Views × Klickrate × Conversion × Provision", ""),
           ("Gesamtumsatz", _eur(m["umsatz"], 2), f"{_eur(m['je_1000_views'], 2)} je 1.000 Views", ""),
           ("Gewinn", _eur(m["gewinn"], 2), f"Marge {_pct(m['marge_pct'])} · Kosten {_eur(m['kosten'], 0)}",
            "yt-pos" if m["gewinn"] > 0 else "yt-neg" if m["gewinn"] < 0 else "")])
    st.caption(f"Je Video: Umsatz {_eur(m['umsatz_je_video'], 2)}, Kosten {_eur(m['kosten_je_video'], 2)} · je Kanal: "
               f"Umsatz {_eur(m['umsatz_je_kanal'], 2)}")
    st.markdown("**Szenarien** – Werbeeinnahmen erst ab Aufnahme ins Partnerprogramm (neue Kanäle verdienen anfangs "
                "oft nichts an Werbung)")
    import pandas as pd
    zeilen = []
    for sz, v in alle.items():
        a = YF.SZENARIEN[sz]
        for n, z in v["zeitraeume"].items():
            zeilen.append({"Szenario": a["name"], "Zeitraum": f"{n} Monate", "Umsatz €": round(z["umsatz"], 2),
                           "Kosten € (inkl. einmalig)": round(z["kosten"], 2), "Gewinn €": round(z["gewinn"], 2),
                           "ROI %": None if z["roi_pct"] is None else round(z["roi_pct"], 1)})
    st.dataframe(pd.DataFrame(zeilen), hide_index=True, width="stretch", key=K + "szen_tab")
    st.caption(" · ".join(f"{a['name']}: Views ×{a['views_faktor']:g}, RPM ×{a['rpm_faktor']:g}, +{a['wachstum_pct']:g} % "
                          f"Views/Monat, Werbung ab Monat {a['monetarisierung_ab']}, Break-even "
                          f"{'Monat ' + str(alle[sz]['prognose']['break_even']) if alle[sz]['prognose']['break_even'] else 'nicht in 12 Monaten'}"
                          for sz, a in YF.SZENARIEN.items()))
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        for sz, v in alle.items():
            fig.add_scatter(x=[z["monat_nr"] for z in v["prognose"]["monate"]],
                            y=[z["kumuliert"] for z in v["prognose"]["monate"]], name=YF.SZENARIEN[sz]["name"])
        fig.add_hline(y=0, line=dict(color="#A9ACB0", width=1, dash="dot"))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=30), xaxis_title="Monat",
                          yaxis_title="Kumulierter Gewinn €", legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(UI.chart_stil(fig, schrumpfen=False), width="stretch", key=K + "szen_chart",
                        config={"displayModeBar": False})
    except Exception as ex:                                   # Diagramm ist Zusatz
        logging.warning("YouTube-Rechner: Diagramm: %s", ex)
    st.caption("Alle Werte sind Schätzungen aus deinen Annahmen – sie werden nie als verdientes Geld gebucht.")


def _kassenbuch(h, d):
    st.markdown("**Kassenbuch – tatsächliche Einnahmen und Ausgaben**")
    kanal_namen = {k["id"]: k["name"] for k in d["kanaele"]}
    with st.expander("➕ Buchung erfassen", expanded=not d["buchungen"]):
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        art = sp[0].segmented_control("Art", ["einnahme", "ausgabe"], default="ausgabe", key=K + "b_art",
                                      format_func=lambda x: "Einnahme" if x == "einnahme" else "Ausgabe") or "ausgabe"
        kats = YF.KATEGORIEN_EIN if art == "einnahme" else YF.KATEGORIEN_AUS
        kat = sp[1].selectbox("Kategorie", list(kats), format_func=kats.get, key=K + f"b_kat_{art}")
        betrag = sp[2].number_input("Betrag (€)", min_value=0.0, step=1.0, value=None, key=K + "b_betrag",
                                    placeholder="0,00")
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        datum = sp[0].date_input("Datum", value=datetime.date.today(), max_value=datetime.date.today(),
                                 key=K + "b_datum", format="DD.MM.YYYY")
        kanal = sp[1].selectbox("Kanal", [None] + list(kanal_namen),
                                format_func=lambda i: "ohne Kanal" if i is None else kanal_namen[i], key=K + "b_kanal")
        notiz = sp[2].text_input("Notiz", key=K + "b_notiz", max_chars=200)
        if st.button("Buchung speichern", key=K + "b_btn", type="primary", disabled=not betrag):
            try:
                b = YF.neue_buchung(datum.isoformat(), art, kat, betrag, kanal, notiz)
            except ValueError as ex:
                st.error(str(ex))
                return
            # feste ID je ausgefuelltem Formular: doppeltes Absenden erzeugt nie zwei Buchungen
            b["id"] = st.session_state.setdefault(K + "b_formular_id", uuid.uuid4().hex[:10])

            def neu_buchung(x):
                if any(y.get("id") == b["id"] for y in x["buchungen"]):
                    return x
                return dict(x, buchungen=x["buchungen"] + [b])
            if _speichern(h, neu_buchung, "Buchung erfasst"):
                for k in ("b_betrag", "b_notiz", "b_formular_id"):
                    st.session_state.pop(K + k, None)
                st.rerun()
    filt = st.selectbox("Auswertung für", [None] + list(kanal_namen), key=K + "b_filter",
                        format_func=lambda i: "alle Kanäle" if i is None else kanal_namen[i])
    a = YF.auswertung(d["buchungen"], filt)
    _kpis([("Einnahmen", _eur(a["einnahmen"], 2), f"{a['anzahl']} Buchungen", ""),
           ("Ausgaben", _eur(a["ausgaben"], 2), "", ""),
           ("Gewinn", _eur(a["gewinn"], 2), f"Marge {_pct(a['marge_pct'])}",
            "yt-pos" if a["gewinn"] > 0 else "yt-neg" if a["gewinn"] < 0 else ""),
           ("ROI", _pct(a["roi_pct"]), "Gewinn / Ausgaben", "")])
    if not d["buchungen"]:
        st.caption("Noch keine Buchungen.")
        return
    import pandas as pd
    liste = [b for b in d["buchungen"] if filt is None or b.get("kanal") == filt]
    kat = {**YF.KATEGORIEN_EIN, **YF.KATEGORIEN_AUS}
    df = pd.DataFrame([{"Datum": b["datum"], "Art": "Einnahme" if b["art"] == "einnahme" else "Ausgabe",
                        "Kategorie": kat.get(b["kategorie"], b["kategorie"]),
                        "Betrag €": b["betrag"] if b["art"] == "einnahme" else -b["betrag"],
                        "Kanal": kanal_namen.get(b.get("kanal"), "–"), "Notiz": b.get("notiz") or "", "ID": b["id"]}
                       for b in sorted(liste, key=lambda b: b["datum"], reverse=True)])
    ev = st.dataframe(df, hide_index=True, width="stretch", key=K + "b_tab", on_select="rerun",
                      selection_mode="single-row", column_config={"ID": None})
    if ev and ev.selection.rows:
        bid = df.iloc[ev.selection.rows[0]]["ID"]
        if st.button("Ausgewählte Buchung löschen", key=K + "b_del_btn"):
            if _speichern(h, lambda x: dict(x, buchungen=[b for b in x["buchungen"] if b["id"] != bid]),
                          "Buchung gelöscht"):
                st.rerun()
    csv = df.drop(columns=["ID"]).to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
    st.download_button("⬇️ Kassenbuch als CSV", csv, file_name=f"youtube_kassenbuch_{datetime.date.today()}.csv",
                       mime="text/csv", key=K + "b_csv")


def _kanaele(h, d):
    st.markdown("**Kanäle**")
    with st.expander("➕ Kanal anlegen", expanded=not d["kanaele"]):
        sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
        name = sp[0].text_input("Kanalname", key=K + "k_name", max_chars=80)
        nische = sp[1].text_input("Nische", key=K + "k_nische", max_chars=80)
        sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
        sprache = sp[0].selectbox("Sprache", ["de", "en", "fr", "es", "it"], key=K + "k_sprache")
        markt = sp[1].selectbox("Markt", ["DE", "AT", "CH", "DACH", "US", "UK", "Global"], key=K + "k_markt")
        status = sp[2].selectbox("Status", ["geplant", "aktiv", "pausiert", "beendet"], key=K + "k_status")
        if st.button("Kanal anlegen", key=K + "k_btn", disabled=not (name or "").strip()):
            try:
                k = YF.neuer_kanal(name, sprache, markt, nische, status)
            except ValueError as ex:
                st.error(str(ex))
                return
            def neu_kanal(x):                        # gleicher Name nur einmal (auch bei Doppeltippen)
                if any(y["name"].lower() == k["name"].lower() for y in x["kanaele"]):
                    return x
                return dict(x, kanaele=x["kanaele"] + [k])
            if _speichern(h, neu_kanal, "Kanal angelegt"):
                st.rerun()
    for k in d["kanaele"]:
        a = YF.auswertung(d["buchungen"], k["id"])
        with st.container(border=True, key=K + f"kanal_box_{k['id']}"):
            st.markdown(f"**{_e(k['name'])}** · {_e(k.get('nische') or '–')} · {_e(k['sprache'])}/{_e(k['markt'])} · "
                        f"{_e(k['status'])} seit {_e(k.get('start'))}  \nEinnahmen {_eur(a['einnahmen'], 2)} · Ausgaben "
                        f"{_eur(a['ausgaben'], 2)} · Gewinn {_eur(a['gewinn'], 2)}")
            if st.button("Kanal entfernen (Buchungen bleiben)", key=K + f"k_del_{k['id']}"):
                if _speichern(h, lambda x, kid=k["id"]: dict(x, kanaele=[y for y in x["kanaele"] if y["id"] != kid]),
                              "Kanal entfernt"):
                    st.rerun()


def _finanzen(h, d):
    teil = st.segmented_control("Finanzen", ["Kassenbuch", "Finanzrechner", "Kanäle"], default="Kassenbuch",
                                key=K + "fin_teil", label_visibility="collapsed") or "Kassenbuch"
    if teil == "Kassenbuch":
        _kassenbuch(h, d)
    elif teil == "Finanzrechner":
        _rechner()
    else:
        _kanaele(h, d)


# ---------------------------------------------------------------------------------------------------- Einstellungen
def _einstellungen(h, d):
    e = {**STANDARD_EINST, **d["einstellungen"]}
    modus = st.radio("Produktionsmodus", list(MODI), index=list(MODI).index(e["modus"]) if e["modus"] in MODI else 0,
                     format_func=MODI.get, key=K + "e_modus")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    b_monat = sp[0].number_input("Budgetgrenze je Monat für kostenpflichtige Dienste (€)", 0.0, 10000.0,
                                 value=float(e["budget_monat"]), step=5.0, key=K + "e_bm",
                                 help="0 = keine kostenpflichtigen Aktionen")
    b_video = sp[1].number_input("Budgetgrenze je Video (€)", 0.0, 1000.0, value=float(e["budget_video"]), step=1.0,
                                 key=K + "e_bv")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    sprache = sp[0].selectbox("Standardsprache", ["de", "en"], index=0 if e["sprache"] == "de" else 1, key=K + "e_spr")
    maerkte = ["DE", "AT", "CH", "DACH", "US", "UK", "Global"]
    markt = sp[1].selectbox("Hauptmarkt", maerkte, index=maerkte.index(e["markt"]) if e["markt"] in maerkte else 0,
                            key=K + "e_markt")
    if st.button("Einstellungen speichern", key=K + "e_btn", type="primary"):
        neu = {"modus": modus, "budget_monat": b_monat, "budget_video": b_video, "sprache": sprache, "markt": markt}
        if _speichern(h, lambda x: dict(x, einstellungen=neu), "Einstellungen"):
            st.rerun()
    st.caption("Kostenpflichtige Aktionen laufen nie ohne Freigabe und nie über die Budgetgrenze. Öffentliche "
               "Veröffentlichungen nur nach ausdrücklicher Freigabe.")
    st.markdown("**Verbindungen** (es werden nie Schlüsselwerte angezeigt)")
    zug = h.get("zugaenge") or {}
    for name, wofuer, phase, kosten in ZUGAENGE:
        ok = zug.get(name)
        st.markdown(f"{'✅' if ok else '⚪'} **{name}** – {'eingerichtet' if ok else 'fehlt'} · {wofuer} · ab Phase "
                    f"{phase} · {kosten}")
    with st.expander("So richtest du den YouTube-Schlüssel ein"):
        st.markdown(
            "1. In der Google Cloud Console ein Projekt anlegen.\n"
            "2. Unter „APIs & Dienste → Bibliothek“ die **YouTube Data API v3** aktivieren.\n"
            "3. Unter „Anmeldedaten“ einen **API-Schlüssel** erstellen und ihn auf die YouTube Data API v3 "
            "beschränken.\n"
            "4. Den Schlüssel als `YOUTUBE_API_KEY` eintragen: in den **Streamlit-Secrets** der App (Manage app → "
            "Settings → Secrets) und als **GitHub-Secret** des Repositories (für den Recherche-Agenten).\n\n"
            "Bitte den Schlüssel nirgends in einen Chat kopieren. Kostenlos mit Tageskontingent (10.000 Einheiten).")


# ---------------------------------------------------------------------------------------------------- Seite
def seite(h):
    st.markdown(CSS, unsafe_allow_html=True)
    ss = st.session_state
    st.markdown("### 🎬 Faceless YouTube Automation")
    st.caption("Recherche, Analyse, Videoproduktion und Finanzen für eigene Faceless-YouTube-Kanäle – Schritt für "
               "Schritt im Aufbau (Phase 1 von 8).")
    if ss.get(K + "meldung"):
        art, text = ss.pop(K + "meldung")
        (st.success if art == "ok" else st.warning)(text)
    d, ok = _laden(h)
    if not ok:
        st.warning("Die Daten sind gerade nicht lesbar – bitte später erneut versuchen. Es wird nichts überschrieben.")
        return
    if ss.get(K + "bereich") not in BEREICHE:
        ss[K + "bereich"] = BEREICHE[0]
    bereich = st.segmented_control("Bereich", BEREICHE, key=K + "bereich", label_visibility="collapsed",
                                   width="stretch") or BEREICHE[0]
    {"Überblick": _ueberblick, "Recherche": _recherche, "Analyse": _analyse, "Video Factory": _factory,
     "Finanzen": _finanzen, "Einstellungen": _einstellungen}[bereich](h, d)
