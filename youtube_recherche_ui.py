"""Faceless YouTube Phase 2a - Recherche ueber die YouTube Data API v3: weltweite Trends, Stichwortsuche,
Kanal untersuchen. Jeder Abruf wird mit seinen Kosten auf das Tageskontingent gebucht und 24 Stunden
zwischengespeichert (state/youtube_api.json). Ohne YOUTUBE_API_KEY erscheint nur ein Hinweis.
Der Schluessel selbst ist hier nie sichtbar: h["yt_abruf"] ist eine fertige Abruf-Funktion aus app.py."""
import datetime
import logging
import statistics
import uuid

import streamlit as st

import ui_stil as UI
import youtube_api as YA
import youtube_nische as YN
from youtube_ui import K, _e, _kpis, _speichern

API_DATEI = "state/youtube_api.json"
ZEITRAEUME = {7: "letzte 7 Tage", 30: "letzte 30 Tage", 90: "letzte 90 Tage", 365: "letztes Jahr", 0: "ohne Grenze"}
SPRACHEN = {"": "alle Sprachen", "de": "Deutsch", "en": "Englisch", "es": "Spanisch", "fr": "Französisch",
            "it": "Italienisch", "pt": "Portugiesisch"}
KLEIN_ABOS = 10000


def _jetzt():
    return datetime.datetime.now(datetime.timezone.utc)


def _zahl(x, n=0):
    if x is None:
        return "–"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def grenze(d):
    try:
        return min(int((d.get("einstellungen") or {}).get("api_grenze") or YA.STANDARD_GRENZE), YA.TAGESKONTINGENT)
    except (TypeError, ValueError):
        return YA.STANDARD_GRENZE


def _speicher(h):
    try:
        s, ok = h["lesen"](h["upfad"](API_DATEI), {})
    except Exception:
        s, ok = {}, False
    return (s if isinstance(s, dict) else {}), ok


def kontingent_zeile(h, d):
    s, _ = _speicher(h)
    jetzt = _jetzt()
    v = YA.verbraucht(s, jetzt)
    st.caption(f"Kontingent heute: **{_zahl(v)}** von {_zahl(grenze(d))} Einheiten (eigene Grenze; YouTube erlaubt "
               f"{_zahl(YA.TAGESKONTINGENT)}) · Neustart {YA.neustart_text(jetzt)}")


def ausfuehren(h, d, art, params, funktion, neu=False):
    """funktion(abruf) -> daten. Erst Zwischenspeicher (Sitzung, dann Datei), sonst Kontingent pruefen, abrufen,
    Kosten buchen und Ergebnis ablegen. -> {"daten", "zeit", "cache", "einheiten"} oder None (Meldung gesetzt)."""
    ss = st.session_state
    jetzt = _jetzt()
    schl = YA.cache_schluessel(art, params)
    sitzung = ss.setdefault(K + "api_cache", {})
    speicher, lesbar = _speicher(h)
    if not neu:
        e = YA.cache_holen({"cache": sitzung}, schl, jetzt) or YA.cache_holen(speicher, schl, jetzt)
        if e:
            return {"daten": e["daten"], "zeit": e["zeit"], "cache": True, "einheiten": 0}
    if not h.get("yt_abruf"):
        ss[K + "meldung"] = ("warn", "YOUTUBE_API_KEY fehlt – siehe „Einstellungen“.")
        return None
    try:
        YA.pruefen(speicher, YA.SCHAETZUNG.get(art, 1), grenze(d), jetzt)
    except YA.ApiFehler as ex:
        ss[K + "meldung"] = ("warn", str(ex))
        return None
    z = YA.Zaehler(h["yt_abruf"])
    daten, fehler = None, None
    try:
        daten = funktion(z)
    except YA.ApiFehler as ex:
        fehler = str(ex)
    except Exception as ex:                                   # unerwartet: Typ melden, keinen Text (kein Schluessel)
        logging.warning("YouTube-API: unerwarteter Fehler %s", type(ex).__name__)
        fehler = f"Unerwarteter Fehler beim Abruf ({type(ex).__name__})."
    zeit = jetzt.isoformat(timespec="seconds")
    if daten is not None:
        sitzung[schl] = {"art": art, "zeit": zeit, "daten": daten}
    if h.get("speichern") and lesbar and z.einheiten:

        def aendern(alt):
            s = YA.buchen(alt if isinstance(alt, dict) else {}, z.einheiten, jetzt)
            return YA.cache_ablegen(s, schl, art, daten, jetzt) if daten is not None else s
        try:
            h["aktualisiere"](h["upfad"](API_DATEI), aendern, {}, f"youtube: api {art} [skip ci]")
        except Exception as ex:
            logging.warning("YouTube-API: Kontingent nicht gespeichert (%s)", type(ex).__name__)
    if fehler:
        ss[K + "meldung"] = ("warn", fehler)
        return None
    return {"daten": daten, "zeit": zeit, "cache": False, "einheiten": z.einheiten}


def _herkunft(erg):
    zeit = str(erg.get("zeit") or "")[:16].replace("T", " ")
    if erg.get("cache"):
        return f"Aus dem Zwischenspeicher (abgerufen {zeit} UTC) – kein Kontingent verbraucht."
    return f"Frisch abgerufen ({zeit} UTC) – {erg.get('einheiten', 0)} Einheiten verbraucht."


# ---------------------------------------------------------------------------------------------------- Aktionen
def idee_speichern(h, v, herkunft, markt="Global"):
    idee = {"id": uuid.uuid4().hex[:8], "titel": (v.get("titel") or "")[:120], "nische": "", "markt": markt,
            "quelle": v.get("url") or "", "status": "neu", "datum": datetime.date.today().isoformat(),
            "notiz": f"{herkunft}: {v.get('kanal') or '–'} · {_zahl(v.get('views'))} Aufrufe"
                     + (f" · {_zahl(v['faktor_kanal'], 1)}× Abonnenten" if v.get("faktor_kanal") else "")
                     + (f" · Outlier ×{v['outlier']:.1f}" if v.get("outlier") else "")
                     + " – nur als Inspiration, eigenes Konzept nötig."}

    def neu_idee(x):
        if any(y.get("quelle") == idee["quelle"] for y in x["ideen"]):
            return x
        return dict(x, ideen=x["ideen"] + [idee])
    return _speichern(h, neu_idee, "Idee gespeichert")


def kanal_oeffnen(kanal_id):
    """Wechselt zu „Kanal untersuchen“ und startet die Untersuchung (Schalter vor dem Widget setzen)."""
    st.session_state[K + "rech_teil_neu"] = "Kanal untersuchen"
    st.session_state[K + "api_kanal_neu"] = kanal_id
    st.session_state[K + "api_kanal_start"] = True


def radar_id(h, d, eingabe):
    """@Handle oder Kanal-Adresse fuer das Kanal-Radar aufloesen (1 Einheit). -> (kanal_id, name) oder None."""
    erg = ausfuehren(h, d, "kanal_id", {"eingabe": str(eingabe).strip().lower()},
                     lambda abruf: YA.kanal_aufloesen(abruf, eingabe))
    if not erg:
        return None
    return erg["daten"]["id"], erg["daten"]["name"]


# ---------------------------------------------------------------------------------------------------- Tabelle
def _tabelle(h, videos, schluessel, herkunft, mit_outlier=False, markt="Global"):
    if not videos:
        st.info("Keine Videos für diese Auswahl.")
        return
    import pandas as pd
    df = pd.DataFrame([{
        "Titel": v["titel"], "Kanal": v["kanal"], "Format": "Short" if v.get("shorts") else "Longform",
        "Länge (min)": round(v["dauer_s"] / 60, 1) if v.get("dauer_s") else None, "Aufrufe": v.get("views"),
        "Alter (Tage)": v.get("alter_tage"),
        "Aufrufe/Tag": round(v["views_pro_tag"]) if v.get("views_pro_tag") is not None else None,
        **({"Outlier ×": round(v["outlier"], 1) if v.get("outlier") else None} if mit_outlier else {}),
        "Abonnenten": v.get("abonnenten"),
        "Aufrufe/Abos ×": round(v["faktor_kanal"], 2) if v.get("faktor_kanal") else None,
        "Likes %": round(v["likes_pct"], 2) if v.get("likes_pct") is not None else None,
        "Kommentare": v.get("kommentare"), "Link": v.get("url"), "ID": v.get("id")} for v in videos])
    for sp in df.columns:
        if sp not in ("Titel", "Kanal", "Format", "Link", "ID"):
            df[sp] = pd.to_numeric(df[sp], errors="coerce")
    ev = st.dataframe(df, hide_index=True, width="stretch", key=K + schluessel, on_select="rerun",
                      selection_mode="single-row",
                      column_config={"ID": None, "Link": st.column_config.LinkColumn("Link", display_text="öffnen")})
    st.caption("Aufrufe/Abos × = Aufrufe des Videos geteilt durch die Abonnenten des Kanals – über 1 heißt: das Video "
               "erreicht mehr Menschen, als der Kanal Abonnenten hat. Ausgeblendete Abonnentenzahlen bleiben leer. "
               "Zeile antippen für Aktionen.")
    if ev and ev.selection.rows:
        vid = df.iloc[ev.selection.rows[0]]["ID"]
        v = next((x for x in videos if x.get("id") == vid), None)
        if not v:
            return
        sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
        if sp[0].button("💡 Als Idee speichern", key=K + schluessel + "_idee"):
            if idee_speichern(h, v, herkunft, markt):
                st.rerun()
        if v.get("kanal_id") and sp[1].button(f"🔎 Kanal „{v['kanal'][:30]}“ untersuchen",
                                               key=K + schluessel + "_kanal"):
            kanal_oeffnen(v["kanal_id"])
            st.rerun()


def _format_filter(videos, fmt):
    if fmt == "Shorts":
        return [v for v in videos if v.get("shorts")]
    if fmt == "Longform":
        return [v for v in videos if not v.get("shorts")]
    return videos


def _ohne_schluessel(h):
    if h.get("yt_abruf"):
        return False
    st.info("Für diesen Bereich fehlt der **YOUTUBE_API_KEY** (Streamlit-Secrets). Die Anleitung steht unter "
            "„Einstellungen“. Das Kanal-Radar funktioniert auch ohne Schlüssel.")
    return True


# ---------------------------------------------------------------------------------------------------- Trends
def trends(h, d):
    st.markdown("**Weltweite Trends** – die aktuelle YouTube-Trendliste je Land und Kategorie")
    if _ohne_schluessel(h):
        return
    sp = st.columns([2, 2, 2]) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
    region = sp[0].selectbox("Land", list(YA.REGIONEN), format_func=lambda r: f"{r} · {YA.REGIONEN[r]}",
                             key=K + "t_region")
    kat = sp[1].selectbox("Kategorie", list(YA.KATEGORIEN), format_func=YA.KATEGORIEN.get, key=K + "t_kat")
    fmt = sp[2].segmented_control("Format", YA.FORMATE, default="Alle", key=K + "t_fmt") or "Alle"
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    laden = sp[0].button("📈 Trends laden", key=K + "t_btn", type="primary", help="Kostet 2 Einheiten.")
    neu = sp[1].button("Neu abrufen", key=K + "t_neu", help="Zwischenspeicher übergehen (2 Einheiten).")
    params = {"region": region, "kategorie": kat}
    if laden or neu:
        erg = ausfuehren(h, d, "trends", params, lambda abruf: YA.trends(abruf, region, kat), neu=neu)
        if erg:
            st.session_state[K + "t_erg"] = dict(erg, params=params)
        st.rerun()
    kontingent_zeile(h, d)
    erg = st.session_state.get(K + "t_erg")
    if not erg:
        return
    p = erg["params"]
    videos = _format_filter(erg["daten"]["videos"], fmt)
    st.caption(f"{YA.REGIONEN.get(p['region'], p['region'])} · {YA.KATEGORIEN.get(p['kategorie'])} · "
               + _herkunft(erg))
    pro_h = [v["views_pro_stunde"] for v in videos if v.get("views_pro_stunde")]
    _kpis([("Videos", _zahl(len(videos)), f"Format: {fmt}", ""),
           ("Median Aufrufe", _zahl(statistics.median([v["views"] for v in videos if v.get("views") is not None]))
            if videos else "–", "", ""),
           ("Median Aufrufe/Stunde", _zahl(statistics.median(pro_h)) if pro_h else "–", "seit Veröffentlichung", ""),
           ("Shorts-Anteil", f"{round(100 * sum(1 for v in erg['daten']['videos'] if v.get('shorts')) / max(len(erg['daten']['videos']), 1))} %",
            "der ganzen Liste", "")])
    _tabelle(h, sorted(videos, key=lambda v: -(v.get("views_pro_stunde") or 0)), "t_tab", "Aus den YouTube-Trends",
             markt=p["region"])


# ---------------------------------------------------------------------------------------------------- Suche
def such_params(begriff, tage, fmt, region, sprache, reihe):
    """Schluessel fuer den Zwischenspeicher - Suche und Nische teilen sich dieselben Ergebnisse."""
    return {"begriff": (begriff or "").strip().lower(), "tage": tage, "format": fmt, "region": region,
            "sprache": sprache, "reihe": reihe}


def such_lauf(h, d, begriff, params, neu=False):
    return ausfuehren(h, d, "suche", params, lambda abruf: YA.suche(
        abruf, begriff, params["tage"], params["format"], params["region"], params["sprache"], params["reihe"]),
        neu=neu)


def suche(h, d):
    st.markdown("**Suche** – die erfolgreichsten Videos zu einem Stichwort, mit Kanalgröße")
    if _ohne_schluessel(h):
        return
    begriff = st.text_input("Suchbegriff", key=K + "s_begriff", max_chars=120,
                            placeholder="z. B. KI Tools für Selbstständige")
    sp = st.columns(5) if not UI.ist_smartphone() else [st.container() for _ in range(5)]
    tage = sp[0].selectbox("Zeitraum", list(ZEITRAEUME), index=1, format_func=ZEITRAEUME.get, key=K + "s_tage")
    fmt = sp[1].selectbox("Format", YA.FORMATE, key=K + "s_fmt")
    region = sp[2].selectbox("Land", [""] + list(YA.REGIONEN), format_func=lambda r: YA.REGIONEN.get(r, "alle Länder"),
                             key=K + "s_region")
    sprache = sp[3].selectbox("Sprache", list(SPRACHEN), format_func=SPRACHEN.get, key=K + "s_sprache")
    reihe = sp[4].selectbox("Reihenfolge", list(YA.REIHENFOLGEN), format_func=YA.REIHENFOLGEN.get, key=K + "s_reihe")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    los = sp[0].button("🔍 Suchen", key=K + "s_btn", type="primary", disabled=not (begriff or "").strip(),
                       help="Kostet etwa 102 Einheiten – rund 75 Suchen pro Tag.")
    neu = sp[1].button("Neu abrufen", key=K + "s_neu", disabled=not (begriff or "").strip(),
                       help="Zwischenspeicher übergehen (etwa 102 Einheiten).")
    params = such_params(begriff, tage, fmt, region, sprache, reihe)
    if los or neu:
        erg = such_lauf(h, d, begriff, params, neu)
        if erg:
            st.session_state[K + "s_erg"] = dict(erg, params=dict(params, anzeige=begriff.strip()))
        st.rerun()
    kontingent_zeile(h, d)
    erg = st.session_state.get(K + "s_erg")
    if not erg:
        return
    p, videos = erg["params"], erg["daten"]["videos"]
    st.caption(f"„{p['anzeige']}“ · {ZEITRAEUME.get(p['tage'])} · {p['format']} · "
               f"{YA.REGIONEN.get(p['region'], 'alle Länder')} · {_herkunft(erg)}")
    views = [v["views"] for v in videos if v.get("views") is not None]
    abos = [v["abonnenten"] for v in videos if v.get("abonnenten") is not None]
    klein = [v for v in videos if v.get("abonnenten") is not None and v["abonnenten"] < KLEIN_ABOS
             and (v.get("faktor_kanal") or 0) >= 1]
    _kpis([("Treffer", _zahl(len(videos)), f"von {erg['daten']['treffer']} Suchergebnissen", ""),
           ("Median Aufrufe", _zahl(statistics.median(views)) if views else "–", "", ""),
           ("Median Abonnenten", _zahl(statistics.median(abos)) if abos else "–", "der Kanäle", ""),
           ("Kleine Kanäle mit Treffer", _zahl(len(klein)), f"unter {_zahl(KLEIN_ABOS)} Abos, Aufrufe ≥ Abos", "")])
    if p["reihe"] == "viewCount":
        videos = sorted(videos, key=lambda v: -(v.get("views") or 0))
    _tabelle(h, videos, "s_tab", f"Aus der Suche „{p['anzeige']}“", markt=p["region"] or "Global")


# ---------------------------------------------------------------------------------------------------- Kanal
def kanal(h, d):
    ss = st.session_state
    st.markdown("**Kanal untersuchen** – Größe, Rhythmus und die Ausreißer der letzten 50 Uploads")
    if _ohne_schluessel(h):
        return
    if K + "api_kanal_neu" in ss:
        ss[K + "api_kanal"] = ss.pop(K + "api_kanal_neu")
    eingabe = st.text_input("@Handle, Kanal-Adresse oder Kanal-ID", key=K + "api_kanal", max_chars=200,
                            placeholder="@kanalname  ·  youtube.com/@kanalname  ·  UC…")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    los = sp[0].button("🔎 Untersuchen", key=K + "k_btn", type="primary", disabled=not (eingabe or "").strip(),
                       help="Kostet 3 Einheiten.")
    neu = sp[1].button("Neu abrufen", key=K + "k_neu", disabled=not (eingabe or "").strip())
    if ss.pop(K + "api_kanal_start", False) and (eingabe or "").strip():
        los = True
    if los or neu:
        try:
            schl = "{}:{}".format(*YA.kanal_eingabe(eingabe))
        except YA.ApiFehler as ex:
            ss[K + "meldung"] = ("warn", str(ex))
            st.rerun()
        erg = ausfuehren(h, d, "kanal", {"kanal": schl.lower() if not schl.startswith("id:") else schl},
                         lambda abruf: YA.kanal_untersuchen(abruf, eingabe), neu=neu)
        if erg:
            ss[K + "k_erg"] = erg
        st.rerun()
    kontingent_zeile(h, d)
    erg = ss.get(K + "k_erg")
    if not erg:
        return
    a = erg["daten"]
    k = a["kanal"]
    st.markdown(f"#### {_e(k['name'])}" + (f" · {_e(k['handle'])}" if k.get("handle") else "")
                + (f" · {_e(k['land'])}" if k.get("land") else ""))
    st.caption(f"[Kanal öffnen](https://www.youtube.com/channel/{k['id']}) · " + _herkunft(erg))
    _kpis([("Abonnenten", _zahl(k.get("abonnenten")) if k.get("abonnenten") is not None else "ausgeblendet",
            f"Kanal seit {_zahl(a.get('alter_jahre'), 1)} Jahren" if a.get("alter_jahre") is not None else "", ""),
           ("Gesamtaufrufe", _zahl(k.get("aufrufe")), f"{_zahl(a.get('aufrufe_je_video'))} je Video", ""),
           ("Videos", _zahl(k.get("videos")), f"letzter Upload {a.get('letzter_upload') or '–'}", ""),
           ("Uploads pro Woche", ("≥ " if a.get("rhythmus_gedeckelt") else "") + _zahl(a.get("uploads_pro_woche"), 1),
            f"letzte 90 Tage · Abstand Median {_zahl(a.get('abstand_median_tage'), 1)} Tage", "")])
    f = a["formate"]
    _kpis([("Median Aufrufe Longform", _zahl(f["Longform"]["median"]), f"{f['Longform']['anzahl']} Videos", ""),
           ("Median Aufrufe Shorts", _zahl(f["Shorts"]["median"]), f"{f['Shorts']['anzahl']} Videos", ""),
           ("Ausreißer (≥ 3×)", _zahl(sum(1 for v in a["videos"] if (v.get("outlier") or 0) >= 3)),
            "Aufrufe/Tag gegenüber dem Kanal-Median", ""),
           ("Aufrufe/Abos", _zahl(f["Longform"]["median"] / k["abonnenten"], 2)
            if f["Longform"]["median"] and k.get("abonnenten") else "–", "Median Longform je Abonnent", "")])
    tab = rpm_tabelle(d)
    vm = YN.kanal_views_monat(a["videos"])
    if vm:
        rn = YN.nische_raten(" ".join(v["titel"] for v in a["videos"][:20]) + " " + k.get("beschreibung", ""),
                             a["videos"])
        von, bis = YN.einnahmen(vm, tab[rn])
        st.caption(f"Werbeeinnahmen grob geschätzt: **{_eur(von)}–{_eur(bis)} pro Monat** – aus ~{_zahl(vm)} "
                   f"Aufrufen/Monat der Videos der letzten 90 Tagen (ohne älteren Katalog) und der RPM-Nische „{rn}“. "
                   "Reine Schätzung, YouTube veröffentlicht keine Einnahmen.")
    with st.expander("📡 Ins Kanal-Radar übernehmen", expanded=False):
        schon = any(r.get("id") == k["id"] for r in d["radar"])
        if schon:
            st.caption("Dieser Kanal ist bereits im Kanal-Radar.")
        else:
            sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
            markt = sp[0].selectbox("Markt", ["US", "DE", "UK", "AT", "CH", "Global"], key=K + "k_markt",
                                    index=1 if k.get("land") == "DE" else 0)
            nische = sp[1].text_input("Nische", key=K + "k_nische", max_chars=60)
            if st.button("Ins Radar übernehmen", key=K + "k_radar_btn"):
                eintrag = {"id": k["id"], "name": k["name"], "markt": markt, "nische": (nische or "").strip()}

                def neu_kanal(x):
                    if any(r["id"] == eintrag["id"] for r in x["radar"]):
                        return x
                    return dict(x, radar=x["radar"] + [eintrag])
                if _speichern(h, neu_kanal, f"Kanal {k['name']} im Radar"):
                    st.rerun()
    st.markdown("**Letzte Uploads**")
    _tabelle(h, a["videos"], "k_tab", f"Aus der Kanal-Analyse {k['name']}", mit_outlier=True,
             markt=k.get("land") or "Global")
    st.caption("Outlier × = Aufrufe pro Tag gegenüber dem Median der anderen Videos desselben Formats (mindestens "
               "3 Vergleichsvideos). Ältere Videos haben naturgemäß weniger Aufrufe pro Tag.")


# ---------------------------------------------------------------------------------------------------- Nische
def rpm_tabelle(d):
    return YN.rpm_tabelle((d.get("einstellungen") or {}).get("rpm"))


def _eur(x):
    return f"{_zahl(x)} €"


def _potenzial_kpis(pot):
    _kpis([(f"{name.capitalize()}", f"{_eur(w['von'])}–{_eur(w['bis'])}",
            f"{_zahl(w['views_monat'])} Aufrufe/Monat", "") for name, w in pot.items()]
          + [("Hinweis", "Schätzung", "erst nach Aufnahme ins Partnerprogramm", "")])


def nische(h, d):
    ss = st.session_state
    st.markdown("**Nische untersuchen** – Nachfrage, Konkurrenz, Chancen und Einnahmepotenzial zu einem Stichwort")
    if _ohne_schluessel(h):
        return
    begriff = st.text_input("Nische / Stichwort", key=K + "n_begriff", max_chars=120,
                            placeholder="z. B. Excel Tipps, Börse für Anfänger, Psychologie Fakten")
    sp = st.columns(4) if not UI.ist_smartphone() else [st.container() for _ in range(4)]
    tage = sp[0].selectbox("Zeitraum", list(ZEITRAEUME), index=3, format_func=ZEITRAEUME.get, key=K + "n_tage",
                           help="Bewertet werden die meistgesehenen Videos dieses Zeitraums.")
    fmt = sp[1].selectbox("Format", YA.FORMATE, index=1, key=K + "n_fmt")
    region = sp[2].selectbox("Land", [""] + list(YA.REGIONEN), index=1,
                             format_func=lambda r: YA.REGIONEN.get(r, "alle Länder"), key=K + "n_region")
    sprache = sp[3].selectbox("Sprache", list(SPRACHEN), index=1, format_func=SPRACHEN.get, key=K + "n_sprache")
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    los = sp[0].button("🧭 Nische untersuchen", key=K + "n_btn", type="primary", disabled=not (begriff or "").strip(),
                       help="Eine Suche nach meisten Aufrufen – etwa 102 Einheiten. Dieselbe Suche aus „Suche“ wird "
                            "aus dem Zwischenspeicher wiederverwendet.")
    neu = sp[1].button("Neu abrufen", key=K + "n_neu", disabled=not (begriff or "").strip())
    params = such_params(begriff, tage, fmt, region, sprache, "viewCount")
    if los or neu:
        erg = such_lauf(h, d, begriff, params, neu)
        if erg:
            ss[K + "n_erg"] = dict(erg, params=dict(params, anzeige=begriff.strip()))
        st.rerun()
    kontingent_zeile(h, d)
    erg = ss.get(K + "n_erg")
    if not erg:
        return
    p, videos = erg["params"], erg["daten"]["videos"]
    b = YN.bewerten(videos, p["tage"])
    st.caption(f"„{p['anzeige']}“ · {ZEITRAEUME.get(p['tage'])} · {p['format']} · "
               f"{YA.REGIONEN.get(p['region'], 'alle Länder')} · {_herkunft(erg)}")
    if b["gesamt"] is None:
        st.info(b["hinweis"] or "Zu wenig Daten für eine Bewertung.")
    else:
        farbe = "yt-pos" if b["gesamt"] >= 70 else "" if b["gesamt"] >= 50 else "yt-neg"
        _kpis([("Nischen-Score", f"{b['gesamt']} / 100", b["einstufung"] + (" · vorläufig" if b["vorlaeufig"] else ""),
                farbe)] + [(YN.TEIL_TEXT[k], f"{b['teile'][k]}" if k in b["teile"] else "–",
                            f"Gewicht {YN.GEWICHTE[k]} %", "") for k in ("nachfrage", "konkurrenz", "chance")])
        st.markdown("\n".join(f"- **{YN.TEIL_TEXT[k]}"
                              + (f" ({b['teile'][k]})" if k in b["teile"] else "") + f":** {_e(b['texte'][k])}"
                              for k in YN.GEWICHTE if k in b["texte"]))
        st.caption("Der Score beschreibt nur die erfolgreichsten Videos der Suche – er sagt nichts über Qualität oder "
                   "Erfolg eines eigenen Kanals voraus. Teilwerte: Nachfrage log. (1.000 Aufrufe = 0, 1 Mio. = 100), "
                   "Konkurrenz = 100 − Anteil großer Kanäle, Chance: 25 % kleine Kanäle mit Treffer = 100, "
                   "Frische: 50 % junge Videos = 100.")
    # Einnahmepotenzial
    st.markdown("**Einnahmepotenzial für einen neuen Kanal** <span class='yt-schaetzung'>Schätzung</span>",
                unsafe_allow_html=True)
    tab = rpm_tabelle(d)
    geraten = YN.nische_raten(p["anzeige"], videos)
    sp = st.columns(2) if not UI.ist_smartphone() else [st.container(), st.container()]
    namen = list(tab)
    rpm_n = sp[0].selectbox("RPM-Nische", namen, index=namen.index(geraten) if geraten in namen else 0,
                            key=K + "n_rpm", format_func=lambda n: f"{n} ({_zahl(tab[n][0], 2)}–{_zahl(tab[n][1], 2)} €)")
    pro_monat = sp[1].slider("Videos pro Monat", 1, 30, 8, key=K + "n_vpm")
    shorts = p["format"] == "Shorts"
    if b["median_views"]:
        _potenzial_kpis(YN.potenzial(b["median_views"], pro_monat, tab[rpm_n], shorts))
        st.caption(f"Aufrufe je Video: {', '.join(f'{k} {int(v * 100)} %' for k, v in YN.SZENARIEN.items())} des "
                   f"Nischen-Medians ({_zahl(b['median_views'])}). RPM = Auszahlung je 1.000 Aufrufe"
                   + (" – bei Shorts deutlich niedriger" if shorts else "") + ". Werbeeinnahmen gibt es erst im "
                   "Partnerprogramm (1.000 Abos und 4.000 Wiedergabestunden oder 10 Mio. Shorts-Aufrufe in 90 Tagen). "
                   "Die RPM-Spannen lassen sich unter Finanzen → Einnahmepotenzial anpassen.")
    if st.button("💡 Nische als Idee merken", key=K + "n_idee"):
        notiz = (f"Nischen-Score {b['gesamt'] if b['gesamt'] is not None else '–'} ({b['einstufung']}) · Median "
                 f"{_zahl(b['median_views'])} Aufrufe · {ZEITRAEUME.get(p['tage'])} · RPM-Nische {rpm_n}")
        idee = {"id": uuid.uuid4().hex[:8], "titel": f"Nische: {p['anzeige']}"[:120], "nische": p["anzeige"][:60],
                "markt": p["region"] or "Global", "quelle": "", "notiz": notiz, "status": "neu",
                "datum": datetime.date.today().isoformat()}

        def neu_idee(x):
            if any(y["titel"].lower() == idee["titel"].lower() for y in x["ideen"]):
                return x
            return dict(x, ideen=x["ideen"] + [idee])
        if _speichern(h, neu_idee, "Nische als Idee gespeichert"):
            st.rerun()
    if b["chancen"]:
        st.markdown(f"**Chancen: kleine Kanäle mit Treffern ({len(b['chancen'])})**")
        _tabelle(h, b["chancen"], "n_tab", f"Aus der Nische „{p['anzeige']}“", markt=p["region"] or "Global")


# ---------------------------------------------------------------------------------------------------- Einnahmen
def einnahmen_bereich(h, d):
    st.markdown("**Einnahmepotenzial** <span class='yt-schaetzung'>Schätzung</span>", unsafe_allow_html=True)
    tab = rpm_tabelle(d)
    sp = st.columns(3) if not UI.ist_smartphone() else [st.container() for _ in range(3)]
    views = sp[0].number_input("Aufrufe pro Monat", 0, 1_000_000_000, 100000, step=10000, key=K + "e_views")
    rpm_n = sp[1].selectbox("RPM-Nische", list(tab), key=K + "e_rpm_n")
    fmt = sp[2].segmented_control("Format", ["Longform", "Shorts"], default="Longform", key=K + "e_rpm_fmt") \
        or "Longform"
    rpm = YN.SHORTS_RPM if fmt == "Shorts" else tab[rpm_n]
    von, bis = YN.einnahmen(views, rpm)
    _kpis([("Werbung pro Monat", f"{_eur(von)}–{_eur(bis)}", f"RPM {_zahl(rpm[0], 2)}–{_zahl(rpm[1], 2)} €", ""),
           ("Pro Jahr", f"{_eur(von * 12)}–{_eur(bis * 12)}", "bei gleichbleibenden Aufrufen", ""),
           ("Je Video (bei 8/Monat)", f"{_eur(von / 8)}–{_eur(bis / 8)}", "", ""),
           ("Hinweis", "Schätzung", "nur Werbung, ohne Affiliate/Sponsoring", "")])
    st.caption("RPM = Auszahlung an den Kanal je 1.000 Aufrufe (nach dem Anteil von YouTube). Die Werte schwanken "
               "stark nach Land, Jahreszeit und Publikum – sie sind Annahmen, keine Messwerte. Für eine Planung mit "
               "Kosten und Wachstum: Finanzen → Finanzrechner.")
    with st.expander("RPM-Spannen anpassen"):
        import pandas as pd
        df = pd.DataFrame([{"Nische": n, "RPM von €": v[0], "RPM bis €": v[1]} for n, v in tab.items()])
        neu = st.data_editor(df, hide_index=True, num_rows="dynamic", key=K + "e_rpm_tab", width="stretch",
                             column_config={"RPM von €": st.column_config.NumberColumn(min_value=0.0, max_value=200.0,
                                                                                         step=0.1, format="%.2f"),
                                            "RPM bis €": st.column_config.NumberColumn(min_value=0.0, max_value=200.0,
                                                                                         step=0.1, format="%.2f")})
        sp = st.columns(2)
        if sp[0].button("RPM-Spannen speichern", key=K + "e_rpm_btn"):
            eigene = {}
            for _, z in neu.iterrows():
                n = str(z.get("Nische") or "").strip()
                try:
                    a, b = float(z["RPM von €"]), float(z["RPM bis €"])
                except (TypeError, ValueError):
                    continue
                if n and 0 <= a <= b <= 200 and (n not in YN.STANDARD_RPM or YN.STANDARD_RPM[n] != (a, b)):
                    eigene[n] = [a, b]
            if _speichern(h, lambda x: dict(x, einstellungen=dict(x["einstellungen"], rpm=eigene)), "RPM-Spannen"):
                st.rerun()
        if sp[1].button("Standardwerte", key=K + "e_rpm_std"):
            if _speichern(h, lambda x: dict(x, einstellungen={k: v for k, v in x["einstellungen"].items()
                                                              if k != "rpm"}), "RPM-Standardwerte"):
                st.rerun()
        st.caption("Gespeichert werden nur Abweichungen vom Standard. Von ≤ bis, höchstens 200 €.")
