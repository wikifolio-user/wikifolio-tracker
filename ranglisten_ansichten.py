"""Ranglisten & Screener (Watchlist Top 50): Performance, Qualitaets-Score, alle Werte, Klassen-Score, Wikifolios,
Uebersichts-PDF und Detailansichten (aus app.render_dashboard ausgelagert, Audit ARCH-01). Die Rumpfe sind
unveraendert; was sie bisher aus dem Funktionskontext von render_dashboard lasen, bekommen sie ausdruecklich als
Woerterbuch k uebergeben. app.py ruft sie ueber gleichnamige Huellen auf (Dekoratoren bleiben dort).
"""
import config
import datetime
import formate as FMT
import pandas as pd
import plotly.graph_objects as go
import schritte
import streamlit as st
import ui_stil as UI

from depot_rechnen import berechne_performance_kennzahlen, fmt, haenge_live_punkt_an, perf_sortierwert


def wochen_bilanz(k, eintraege, raus, seit):
    """Frueher _wochen_bilanz in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    Q_KLASSEN_KURZ = k['Q_KLASSEN_KURZ']
    TREND_BIS = k['TREND_BIS']
    TREND_FARBE = k['TREND_FARBE']
    _seit_text = k['_seit_text']
    html = k['html']
    """eintraege: [(platz, name, kennung, vor)], raus: [{"name","vor","jetzt"}]"""
    seit_txt = _seit_text(seit)
    if not seit_txt:
        st.caption("Wochenvergleich: startet mit dem nächsten Lauf (es gibt noch keinen früheren Stand).")
        return
    eintraege = [e for e in eintraege if e[0] <= TREND_BIS]
    neu = [(p, n, k) for p, n, k, v in eintraege if v is None]
    bewegt = [(v - p, p, n, k) for p, n, k, v in eintraege if v is not None and v != p]
    auf = sorted([b for b in bewegt if b[0] > 0], reverse=True)[:5]
    ab = sorted([b for b in bewegt if b[0] < 0])[:5]

    def tabelle(kopf, zeilen):
        if not zeilen:
            return '<div class="pt-leer">– keine –</div>'
        k = "".join(f'<th class="{"pt-wert" if i == 0 else "pt-num"}">{h}</th>' for i, h in enumerate(kopf))
        z = "".join("<tr>" + "".join(zeilen_i) + "</tr>" for zeilen_i in zeilen)
        return f'<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt"><thead><tr>{k}</tr></thead><tbody>{z}</tbody></table></div>'

    def zelle(text, farbe=None, wert=False):
        # white-space normal: laengere Texte ("→ Beobachten") duerfen auf
        # dem iPhone umbrechen, statt die Tabelle zu verbreitern
        stil = f' style="color:{farbe};white-space:normal"' if farbe else ""
        return f'<td class="{"pt-wert" if wert else "pt-num"}"{stil}>{html.escape(str(text))}</td>'

    with st.expander(f"📅 Wochenveränderung: {len(neu)} neu · {len(raus)} rausgeflogen · "
                     f"{len(bewegt)} verschoben", expanded=True):
        st.caption(seit_txt)
        st.markdown(f"**🆕 Neu in der Liste ({len(neu)})**", unsafe_allow_html=True)
        st.markdown(tabelle(["Wert", "Platz"], [[zelle(n, wert=True), zelle(p, TREND_FARBE["neu"])]
                                              for p, n, k in neu]), unsafe_allow_html=True)
        st.markdown(f"**❌ Rausgeflogen ({len(raus)})**", unsafe_allow_html=True)
        st.markdown(tabelle(["Wert", "vorher", "jetzt"], [
            [zelle(r["name"], wert=True), zelle(r["vor"]),
             zelle(r["jetzt"] if r.get("jetzt") else
                   f"→ {Q_KLASSEN_KURZ.get(r['klasse'], r['klasse'])}" if r.get("klasse") else
                   "nicht bewertet" if r.get("grund") else "ohne Daten", TREND_FARBE["down"])]
            for r in sorted(raus, key=lambda r: r["vor"])]), unsafe_allow_html=True)
        st.markdown("**🚀 Größte Aufsteiger**", unsafe_allow_html=True)
        st.markdown(tabelle(["Wert", "Platz", "Veränderung"], [
            [zelle(n, wert=True), zelle(p), zelle(f"▲ {d}", TREND_FARBE["up"])] for d, p, n, k in auf]),
            unsafe_allow_html=True)
        st.markdown("**📉 Größte Absteiger**", unsafe_allow_html=True)
        st.markdown(tabelle(["Wert", "Platz", "Veränderung"], [
            [zelle(n, wert=True), zelle(p), zelle(f"▼ {-d}", TREND_FARBE["down"])] for d, p, n, k in ab]),
            unsafe_allow_html=True)


def performance(k):
    """Frueher _render_performance in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BERLIN_TZ = k['BERLIN_TZ']
    GH_STATE_READY = k['GH_STATE_READY']
    INDEX_REGIONEN_APP = k['INDEX_REGIONEN_APP']
    KV = k['KV']
    TREND_BIS = k['TREND_BIS']
    TREND_FARBE = k['TREND_FARBE']
    _auswahl_art = k['_auswahl_art']
    _index_auswahl = k['_index_auswahl']
    _listen_laenge = k['_listen_laenge']
    _p_index_kat = k['_p_index_kat']
    _trend = k['_trend']
    _wochen_bilanz = k['_wochen_bilanz']
    auswahl_kompakt = k['auswahl_kompakt']
    gh_read_taeglich = k['gh_read_taeglich']
    html = k['html']
    kurs_vorrat = k['kurs_vorrat']
    notify_app_error = k['notify_app_error']
    ranglisten_stand = k['ranglisten_stand']
    vz_zahl = k['vz_zahl']
    try:
        daten = gh_read_taeglich("state/top50.json", None)
        if not daten or not daten.get("kategorien"):
            st.info(
                "Noch keine Ranglisten vorhanden. Der Agent läuft täglich um 07:30 Uhr. "
                "Für einen Sofortstart: auf GitHub unter **Actions → Watchlist Top 50 "
                "(täglich) → Run workflow**."
            )
            return

        kategorien = daten["kategorien"]
        zeitraeume = daten.get("zeitraeume") or []
        stand = ranglisten_stand(daten)

        reihenfolge = daten.get("reihenfolge") or ["aktien", "dividenden", "etf", "wikifolios"]
        kat_keys = [k for k in reihenfolge if k in kategorien] + \
                   [k for k in kategorien if k not in reihenfolge]
        kat_titel = [kategorien[k]["titel"] for k in kat_keys]
        vergleich_seit = daten.get("vergleich_seit")
        if _auswahl_art("top50") == "Index":
            mitglieder_idx = (gh_read_taeglich("state/top50_indexmitglieder.json", None) or {}).get("indizes") or {}
            idx_key = _index_auswahl("top50", mitglieder_idx, INDEX_REGIONEN_APP)
            if not idx_key:
                return
            laenge = _listen_laenge("top50")
            kat, vergleich_seit = _p_index_kat(idx_key, mitglieder_idx[idx_key], daten, laenge)
            if not kat:
                st.info("Für diesen Index liegen noch keine Kursdaten vor – sie entstehen beim nächsten Lauf.")
                return
        else:
            gewaehlt = auswahl_kompakt("Kategorie", kat_titel, default=kat_titel[0], key="top50_kategorie")
            kat_key = kat_keys[kat_titel.index(gewaehlt)] if gewaehlt in kat_titel else kat_keys[0]
            kat = kategorien[kat_key]
            laenge = _listen_laenge("top50")
            if laenge > TREND_BIS:
                # Plaetze ab 51 aus der Langliste des Agenten (eine Datei je Kategorie);
                # die ersten 50 bleiben aus top50.json (mit Wochenvergleich)
                lang = gh_read_taeglich(f"state/top50_lang_{kat_key}.json", None) or {}
                if lang.get("top"):
                    def _verlaengern(kurz, lang_zeilen):
                        kurz = list(kurz or [])
                        gesehen = {e.get("wkn") for e in kurz}
                        for z in lang_zeilen or []:
                            if len(kurz) >= laenge:
                                break
                            if z[1] not in gesehen:
                                gesehen.add(z[1])
                                kurz.append({"name": z[0], "wkn": z[1], "perf": z[2], "div": z[3],
                                             "rhythmus": z[4] if len(z) > 4 else None})
                        return kurz
                    kat = dict(kat, top={zr: _verlaengern(kat.get("top", {}).get(zr), lang["top"].get(zr))
                                         for zr in set(kat.get("top", {})) | set(lang["top"])})
            elif laenge < TREND_BIS:
                kat = dict(kat, top={zr: v[:laenge] for zr, v in (kat.get("top") or {}).items()})

        # Kategorien mit Dividende bekommen zusaetzlich die Rangliste nach
        # laufender Dividendenrendite als eigene "Zeitraum"-Pille
        zr_liste = [tuple(z) for z in zeitraeume]
        div_zr = tuple(daten.get("dividenden_zeitraum") or ("DIV", "Div.-Rendite"))
        mit_div = bool(kat.get("dividende"))
        if mit_div and div_zr[0] in kat.get("top", {}):
            zr_liste.append(div_zr)
        import wikifolio_liste as WL
        zr_liste = WL.nach_wichtigkeit(zr_liste, lambda z: z[0])        # wichtigste Zeitraeume zuerst
        zr_titel = [t for _, t in zr_liste]
        zr_wahl = st.pills("Zeitraum", zr_titel, default="1 Jahr" if "1 Jahr" in zr_titel else zr_titel[0],
                           key="top50_zeitraum")
        zr_key = zr_liste[zr_titel.index(zr_wahl)][0] if zr_wahl in zr_titel else zr_liste[0][0]
        nach_div = zr_key == div_zr[0]

        liste = kat.get("top", {}).get(zr_key, [])
        mit_daten = kat.get("mit_daten", {}).get(zr_key, 0)
        st.caption(
            f"Stand {stand} · {mit_daten} von {kat.get('aktiv', 0)} aktiven Werten "
            + ("zahlen eine Dividende" if nach_div else "haben Kursdaten für diesen Zeitraum")
            + f" · Top {len(liste)}"
        )
        if kat.get("veraltet_seit"):
            try:
                alt_stand = datetime.datetime.fromisoformat(kat["veraltet_seit"]).strftime("%d.%m.%Y")
            except Exception:
                alt_stand = kat["veraltet_seit"]
            st.warning(f"Die Kursquelle für diese Liste hat beim letzten Lauf nicht vollständig "
                       f"geantwortet - angezeigt wird der Stand vom {alt_stand}.")

        if not liste:
            st.info("Für diesen Zeitraum reicht bei keinem Wert die Kurshistorie aus.")
            return

        def _pct(wert):
            if wert is None:
                return '<td class="pt-num">–</td>'
            farbe = "pt-up" if wert >= 0 else "pt-down"
            return f'<td class="pt-num pt-stark {farbe}">{vz_zahl(wert, 2)} %</td>'

        def _div(wert, rhythmus=None):
            if not wert:
                return '<td class="pt-num">–</td>'
            unter = f'<span class="pt-sub">{html.escape(rhythmus)}</span>' if rhythmus else ""
            return f'<td class="pt-num pt-stark pt-up">{FMT.pct(wert, 2)}{unter}</td>'

        # Live-Kurse der Top 50 (Kurs-Agent, alle 30 Min.): Spalte "Heute" = Kurs gegen Vortagesschluss.
        # Werte ohne ls-tc-Kursquelle (nur Yahoo) zeigen "–" - fuer sie gilt weiter der Tagesschluss.
        _live = kurs_vorrat().top50() if GH_STATE_READY else {"ids": {}, "werte": {}, "stand": None}
        _jetzt = datetime.datetime.now(BERLIN_TZ)
        mit_live = bool(_live["werte"]) and KV.aktuell(_live["stand"], _jetzt, 24 * 60)

        def _heute(e):
            iid = _live["ids"].get(str(e.get("wkn") or "").strip().upper())
            h = KV.heute(_live["werte"].get(iid) or {}) if iid else None
            if not h:
                return '<td class="pt-num">–</td>'
            kurs, vor = h
            pct = (kurs / vor - 1) * 100
            return (f'<td class="pt-num {"pt-up" if pct >= 0 else "pt-down"}">{vz_zahl(pct, 2)} %'
                    f'<span class="pt-sub">{FMT.kurs(kurs)}</span></td>')

        vergleich = (kat.get("vergleich") or {}).get(zr_key)
        mit_trend = vergleich is not None
        zeilen = ""
        for rang, e in enumerate(liste, 1):
            trend_td = ""
            if mit_trend:
                t, art = _trend(e.get("vor"), rang)
                trend_td = f'<td class="pt-num" style="color:{TREND_FARBE[art]};font-weight:700">{t}</td>'
            if nach_div:
                werte = _div(e.get("div"), e.get("rhythmus")) + _pct(e.get("perf"))
            else:
                werte = _pct(e.get("perf")) + (_div(e.get("div"), e.get("rhythmus")) if mit_div else "")
            if mit_live:
                werte += _heute(e)
            zeilen += (
                f'<tr class="{"pt-zebra" if rang % 2 == 0 else ""}">'
                f'<td class="pt-num pt-seit">{rang}</td>{trend_td}'
                f'<td class="pt-wert"><span class="pt-name">{html.escape(str(e["name"]))}</span>'
                f'<span class="pt-sub">{html.escape(str(e.get("wkn") or ""))}</span></td>'
                f'{werte}'
                f'</tr>'
            )
        if nach_div:
            spalten = '<th class="pt-num">Div.-<br>Rendite</th><th class="pt-num">1 Jahr</th>'
        else:
            spalten = f'<th class="pt-num">{zr_wahl}</th>' + (
                '<th class="pt-num">Div.-<br>Rendite</th>' if mit_div else "")
        if mit_live:
            spalten += '<th class="pt-num">Heute</th>'
        st.markdown(
            '<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt"><thead><tr>'
            '<th class="pt-num">#</th>' + ('<th class="pt-num">7&nbsp;T.</th>' if mit_trend else "") +
            f'<th class="pt-wert">Wert</th>'
            f'{spalten}'
            f'</tr></thead><tbody>{zeilen}</tbody></table></div>',
            unsafe_allow_html=True,
        )

        if mit_live:
            st.caption(f"Heute = aktueller Kurs (ls-tc.de) gegenüber dem Vortagesschluss, Stand "
                       f"{_live['stand'].astimezone(BERLIN_TZ).strftime('%H:%M')} Uhr – der Kurs-Agent "
                       "aktualisiert alle 30 Minuten (für die Top 50 je Kategorie). „–“: nicht unter den Top 50 oder keine "
                       "ls-tc-Kursquelle – dort gilt der Tagesschluss.")

        if mit_trend or vergleich_seit is None:
            _wochen_bilanz([(r, e["name"], e.get("wkn"), e.get("vor")) for r, e in enumerate(liste, 1)],
                           (vergleich or {}).get("raus", []), vergleich_seit)

        with st.expander("Hinweise zu den Ranglisten", expanded=False):
            st.caption(
                "Performance = reine Kursentwicklung ohne Dividenden, Gebühren oder Steuern. "
                "**Div.-Rendite** = Ausschüttungen der letzten 12 Monate geteilt durch den "
                "aktuellen Kurs (laufende Rendite, Quelle Yahoo Finance); darunter der Auszahlungsrhythmus "
                "(monatlich, quartalsweise, halbjährlich, jährlich) aus den Zahlungsterminen der letzten zwei "
                "Jahre. Sonderdividenden "
                "zählen mit; Werte über 30 % werden als unplausibel ausgeblendet. "
                "Werte ohne Kurs seit mehr als 10 Tagen gelten als inaktiv und fehlen. "
                "Vergangene Performance ist kein Hinweis auf künftige Entwicklung."
            )
            if kat.get("kennung") == "Symbol":
                st.caption(
                    "Länderlisten: alle Aktien der Heimatbörsen je Land ab einer Mindestgröße "
                    "(Börsenwert, laut Yahoo Finance), wöchentlich aktualisiert; ausländische "
                    "Zweitnotierungen und ADRs sind herausgefiltert, außerhalb der USA höchstens die "
                    "1.500 größten Werte je Land. Kurse "
                    "von Yahoo Finance (Heimatbörse), mit dem Wechselkurs des jeweiligen Tages "
                    "in Euro umgerechnet - Währungsschwankungen sind also enthalten. Nicht "
                    "jeder Nebenwert oder Auslandswert ist bei deutschen Brokern handelbar. "
                    + ("Quelle: " + ", ".join(kat["quellen"]) + "." if kat.get("quellen") else "")
                )
            else:
                st.caption(
                    "wikifolios werden automatisch über die Kursquelle gefunden (alle "
                    "Zertifikate mit WKN LS9…), die Suche wird wöchentlich erneuert."
                )
            st.caption(
                f"Letzter Lauf: {daten.get('anfragen', '–')} Kursabrufe in "
                f"{daten.get('laufzeit_sek', '–')} s, {daten.get('fehlgeschlagen', 0)} fehlgeschlagen."
            )
        fehlend = [f for f in daten.get("nicht_gefunden", []) if f.get("kategorie") == kat["titel"]]
        if fehlend:
            with st.expander(f"Nicht gefunden ({len(fehlend)})", expanded=False):
                if kat.get("kennung") == "Symbol":
                    st.caption("Für diese Indexmitglieder lieferte Yahoo keine Kurse "
                               "(z.B. frisch umbenannt oder gerade aufgenommen).")
                else:
                    st.caption("Diese Werte aus top50_universum.py ließen sich weder über die "
                               "ISIN noch über den Namen finden - dort korrigieren.")
                for f in fehlend[:100]:
                    st.write(f"- {f['name']} · {f['isin']}")
    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Top50", e)


def q_vergleich(k, werte, symbole):
    """Frueher _q_vergleich in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BR = k['BR']
    DV = k['DV']
    Q_FARBE_CSS = k['Q_FARBE_CSS']
    Q_KLASSEN = k['Q_KLASSEN']
    Q_SPALTEN = k['Q_SPALTEN']
    """Alle Kennzahlen nebeneinander (sortierbar per Tipp auf die Spalte, als CSV
    herunterladbar) + Direktvergleich ausgewaehlter Aktien Kennzahl fuer Kennzahl."""
    zeilen = []
    for rang, sym in enumerate(symbole, 1):
        e = werte.get(sym)
        if not e:
            continue
        sek_, br_ = BR.einordnen(e.get("br"))
        z = {"#": rang, "Unternehmen": e.get("name") or sym, "Symbol": sym, "Sektor": sek_,
             "Branche": br_, "Punkte": e.get("gesamt"), "Einordnung": Q_KLASSEN.get(e.get("klasse"), ""),
             "Dividenden-Kategorie": DV.text(e.get("div"), e.get("div_q"))}
        for key, titel, _, _ in Q_SPALTEN:
            z[titel] = e.get(key)
        zeilen.append(z)
    if not zeilen:
        st.info("Keine Daten.")
        return
    df = pd.DataFrame(zeilen)

    def faerben(spalte):
        regel = next((f for k, t, _, f in Q_SPALTEN if t == spalte.name), None)
        if regel is None:
            return [""] * len(spalte)
        aus = []
        for x in spalte:
            try:
                aus.append(Q_FARBE_CSS.get(regel(None if pd.isna(x) else x), ""))
            except Exception:
                aus.append("")
        return aus

    try:
        ansicht = df.style.apply(faerben, axis=0)
    except Exception:
        ansicht = df
    cfg = {"#": st.column_config.NumberColumn("#", width="small"),
           "Unternehmen": st.column_config.TextColumn("Unternehmen", width="medium", pinned=True),
           "Punkte": st.column_config.NumberColumn("Punkte", format="%d", width="small")}
    for key, titel, _, _ in Q_SPALTEN:
        if key in ("moat", "mgmt", "bew", "risiko"):
            continue
        prozent = key not in ("fkgv", "ev_ebit", "nde", "mcap")
        cfg[titel] = st.column_config.NumberColumn(titel, format="%.1f %%" if prozent else "%.1f")
    try:
        st.dataframe(ansicht, hide_index=True, width="stretch", column_config=cfg,
                     height=min(36 * (len(df) + 1) + 4, 720))
    except TypeError:                       # aeltere Streamlit-Version ohne "pinned"
        cfg["Unternehmen"] = st.column_config.TextColumn("Unternehmen", width="medium")
        st.dataframe(ansicht, hide_index=True, width="stretch", column_config=cfg,
                     height=min(36 * (len(df) + 1) + 4, 720))
    st.caption("Tipp auf einen Spaltenkopf sortiert nach dieser Kennzahl · grün/rot = günstig/ungünstig "
               "nach denselben Schwellen wie in der Einzelansicht · ⤓ oben rechts lädt die Tabelle als CSV.")

    # Direktvergleich: Kennzahlen als Zeilen, ausgewaehlte Aktien als Spalten
    namen = {z["Symbol"]: z["Unternehmen"] for z in zeilen}
    auswahl = st.multiselect("Aktien direkt vergleichen (bis 6)", list(namen), max_selections=6, placeholder="Aktien auswählen …",
                             default=list(namen)[:3], key="q_vergleich_wahl",
                             format_func=lambda s_: f"{namen[s_]} ({s_})")
    if auswahl:
        kennzahlen = [("Punkte", "gesamt", lambda x: "–" if x is None else f"{x}"),
                      ("Firmen-Kategorie", "br", BR.kategorie_text)] + \
                     [(t, k, f) for k, t, f, _ in Q_SPALTEN]
        tab = {"Kennzahl": [t for t, _, _ in kennzahlen]}
        for s_ in auswahl:
            e = werte.get(s_) or {}
            kopf = namen[s_][:22] if namen[s_][:22] not in tab else f"{namen[s_][:16]} ({s_})"
            tab[kopf] = [fmt(e.get(k)) if e.get(k) is not None else "–" for _, k, fmt in kennzahlen]
        vdf = pd.DataFrame(tab)

        def faerben_v(zeile):
            k = next((k for t, k, _ in kennzahlen if t == zeile["Kennzahl"]), None)
            regel = next((f for kk, _, _, f in Q_SPALTEN if kk == k), None)
            aus = [""]
            for s_ in auswahl:
                try:
                    aus.append(Q_FARBE_CSS.get(regel((werte.get(s_) or {}).get(k)), "") if regel else "")
                except Exception:
                    aus.append("")
            return aus

        try:
            vansicht = vdf.style.apply(faerben_v, axis=1)
        except Exception:
            vansicht = vdf
        st.dataframe(vansicht, hide_index=True, width="stretch", height=36 * (len(vdf) + 1) + 4)


def q_details(k, sym, zeile):
    """Frueher _q_details in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BR = k['BR']
    Q_BEREICHE = k['Q_BEREICHE']
    Q_KLASSEN = k['Q_KLASSEN']
    Q_KLASSE_CSS = k['Q_KLASSE_CSS']
    _q_pct = k['_q_pct']
    _q_x = k['_q_x']
    daten_q = k['daten_q']
    gh_read_taeglich = k['gh_read_taeglich']
    html = k['html']
    if not daten_q:                 # Aufruf aus einem anderen Reiter: Annahmen nachladen
        daten_q.update(gh_read_taeglich("state/qualitaet.json", None) or {})
    teil = gh_read_taeglich(f"state/qualitaet/details_{zeile.get('d', 0)}.json", None) or {}
    e = (teil.get("werte") or {}).get(sym)
    if not e:
        st.info("Die ausführliche Analyse wird gerade neu geschrieben - bitte in einer Minute erneut öffnen.")
        return
    st.markdown(f"#### {e['name']} ({sym})")
    st.caption(
        f"{BR.kategorie_text(e.get('br')) if e.get('br') else 'Branche unbekannt'} · {e.get('land') or '–'} · Kurs {e['kurs']:,.2f} {e['kwae']} · "
        f"Marktkap. {e['mcap']:,.1f} Mrd € · Jahresabschlüsse {e['gj_erst'][:4]}–{e['gj'][:4]} "
        f"({e['n']} Geschäftsjahre, letztes bis {datetime.date.fromisoformat(e['gj']).strftime('%d.%m.%Y')})"
    )
    kl_css = Q_KLASSE_CSS.get(e["klasse"], "")
    kacheln = [("Gesamtpunktzahl", f'<b class="{kl_css}">{e["gesamt"]}</b><span> / 100</span>'),
               ("Qualität", f'{e["q_ant"]:.0f}<span> %</span>'),
               ("Bewertung", f'{e["b_ant"]:.0f}<span> %</span>'),
               ("Risiko", html.escape(e["risiko"]))]
    st.markdown('<div class="q-kpis">' + "".join(
        f'<div class="q-kpi"><div class="q-kpi-l">{l}</div><div class="q-kpi-v">{v}</div></div>'
        for l, v in kacheln) + "</div>", unsafe_allow_html=True)
    st.markdown(f"**Einordnung: {Q_KLASSEN.get(e['klasse'])}** – {e['grund']}.")

    st.markdown("**Punkte je Bereich**")
    balken = ""
    for k, t, m in Q_BEREICHE:
        p = e["p"].get(k, 0)
        anteil = p / m if m else 0
        farbe = "#34D399" if anteil >= 0.7 else "#F5B942" if anteil >= 0.4 else "#F87171"
        balken += (f'<div class="q-b-zeile"><div>{html.escape(t)}</div>'
                   f'<div class="q-b-bahn"><div class="q-b-fuell" style="width:{anteil * 100:.0f}%;'
                   f'background:{farbe}"></div></div><div class="q-b-wert">{p}/{m}</div></div>')
    st.markdown(f'<div class="q-balken">{balken}</div>', unsafe_allow_html=True)
    if e["flags"]:
        st.markdown("**Red Flags (Abzug)**\n\n" + "\n".join(f"- {t} (−{a})" for t, a in e["flags"]))

    st.markdown("**Warum interessant?**\n\n" + ("\n".join(f"- {t}" for t in e["staerken"])
                                             or "- Keine herausragenden Stärken in den Kennzahlen."))
    abschnitte = [
        ("Wettbewerbsvorteil (Näherung)", [
            f"Einstufung: **{e['moat']}**",
            f"ROIC Ø {_q_pct(e['roic'], False)}, niedrigster Jahreswert {_q_pct(e['roic_min'], False)}",
            f"Bruttomarge Ø {_q_pct(e['gm'], False)}, Schwankung der operativen Marge {_q_x(e['om_std'], ' Prozentpunkte')}",
            "Netzwerkeffekte, Marke, Patente, Wechselkosten u. Ä. sind nicht automatisch bewertbar."]),
        ("Wachstum", [
            f"Umsatz {_q_pct(e['g_ums'])} p.a. · EPS {_q_pct(e['g_eps'])} p.a. · FCF {_q_pct(e['g_fcf'])} p.a. · "
            f"**FCF je Aktie {_q_pct(e['g_fcfps'])} p.a.**",
            f"Analysten: erwartetes Gewinnwachstum nächstes GJ {_q_pct(e.get('g1'))}"
            + (f" · Schätzungsrevision 90 Tage {_q_pct(e.get('rev90'))} ({e['rev']})" if e.get("rev") else "")]),
        ("ROIC und Reinvestment", [
            f"ROIC zuletzt {_q_pct(e['roic_l'], False)}, Ø {_q_pct(e['roic'], False)}, Trend {_q_x(e['roic_trend'], ' Prozentpunkte')}",
            f"ROE zuletzt {_q_pct(e['roe'], False)} · Capex {_q_pct(e['capex'], False)} vom Umsatz · "
            f"Zukäufe {_q_pct(e['zukauf'], False)} des Free Cashflows"]),
        ("Free Cashflow und Gewinnqualität", [
            f"FCF-Marge Ø {_q_pct(e['fm'], False)} · Cash Conversion (FCF/Gewinn) {_q_x(e['cc'])}",
            f"Aktienbasierte Vergütung {_q_pct(e['sbc'], False)} vom Umsatz · Goodwill/Immaterielles "
            f"{_q_pct(e['gw'], False)} der Bilanzsumme"]),
        ("Bilanz", [
            "Nettocash (mehr liquide Mittel als Schulden)" if e["netcash"] else
            f"Net Debt/EBITDA {_q_x(e['nde'])}",
            f"Zinsdeckung (EBIT/Zinsaufwand) {_q_x(e['zinsd'])}"]),
        ("Management und Kapitalallokation (Näherung)", [
            f"Einstufung: **{e['mgmt']}**",
            f"Aktienanzahl {_q_pct(e['akt'])} p.a. · Rückkäufe + Dividenden {_q_pct(e['aussch'], False)} des FCF",
            "Insiderkäufe, Vergütung und Prognosetreue sind nicht automatisch bewertbar."]),
        ("Dividende", [
            ("Keine Dividende" if e.get("div") == 0 else
             f"Dividendenrendite {_q_pct(e.get('div'), False, 2)} (letzte 12 Monate)")
            + (f" · Ausschüttungsquote {_q_pct(e.get('div_q'), False, 0)} vom Gewinn" if e.get("div_q") is not None else "")
            + (f" · in {e['div_n']} von {e['n']} Geschäftsjahren gezahlt" if e.get("div_n") is not None else "")]),
        ("Bewertung", [
            f"KGV {_q_x(e['kgv'], '')} · Forward-KGV {_q_x(e['fkgv'], '')} · EV/EBIT {_q_x(e['ev_ebit'], '')} · "
            f"EV/EBITDA {_q_x(e['ev_ebitda'], '')} · EV/FCF {_q_x(e['ev_fcf'], '')} · PEG {_q_x(e['peg'], '')}",
            f"FCF-Rendite {_q_pct(e['fcfy'], False, 2)} – eigener Schnitt zu früheren Geschäftsjahresenden "
            f"{_q_pct(e['h_fcfy'], False, 2)} · früheres KGV Ø {_q_x(e['h_kgv'], '')}"]),
        ("Reverse DCF", [
            ("Der heutige Unternehmenswert unterstellt **"
             + ("≥ 60" if e["g_impl"] >= 60 else "≤ −30" if e["g_impl"] <= -30 else f"{e['g_impl']:.1f}")
             + f" % FCF-Wachstum p.a.** über 10 Jahre – erreicht bzw. erwartet sind rund {e['g_ref']:.1f} %"
             + f" → **{e['erw']}**") if e.get("g_impl") is not None else f"Nicht berechenbar: {e['erw']}",
            f"Annahmen: Kapitalkosten {daten_q.get('annahmen', {}).get('diskont', 9):.0f} %, danach "
            f"{daten_q.get('annahmen', {}).get('g_ewig', 2.5):.1f} % ewiges Wachstum; bei Zyklikern "
            "normalisierter Free Cashflow"]),
    ]
    for titel, zeilen in abschnitte:
        st.markdown(f"**{titel}**\n\n" + "\n".join(f"- {z}" for z in zeilen))

    if e.get("szen"):
        st.markdown("**Szenarien (Bear / Base / Bull)**")
        namen = {"bear": "Bear", "base": "Base", "bull": "Bull"}
        zeilen = ""
        for k in ("bear", "base", "bull"):
            v = e["szen"].get(k)
            if not v:
                continue
            farbe = "pt-up" if (v["pot"] or 0) >= 0 else "pt-down"
            zeilen += (f'<tr><td class="pt-wert"><span class="pt-name">{namen[k]}</span></td>'
                       f'<td class="pt-num">{FMT.pct(v["g"], 1)}</td><td class="pt-num">{FMT.pct(v["r"], 1)}</td>'
                       f'<td class="pt-num">{v["m"]:.1f}x</td>'
                       f'<td class="pt-num pt-stark {farbe}">{v["pot"]:+.0f} %</td></tr>')
        st.markdown('<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt"><thead><tr><th class="pt-wert">Fall</th>'
                    '<th class="pt-num">FCF-<br>Wachstum</th><th class="pt-num">Kapital-<br>kosten</th>'
                    '<th class="pt-num">Multi-<br>ple</th><th class="pt-num">Wert vs.<br>Kurs</th></tr></thead>'
                    f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
        st.caption("FCF-Wachstum gilt für die Jahre 1–5 und läuft danach linear auf das ewige Wachstum "
                   "aus. Multiple = Endwert im Verhältnis zum FCF (EV/FCF). Bear Case zusätzlich mit 10 % "
                   "geringerem, normalisiertem Free Cashflow.")
    mos = e.get("mos")
    st.markdown("**Margin of Safety**\n\n- " + (
        "Kein positiver fairer Wert berechenbar." if mos is None else
        ("Kurs liegt beim Dreifachen des konservativen fairen Werts oder darüber." if mos <= -200 else
         f"{mos:+.0f} % Sicherheitsmarge zum konservativen fairen Wert (Base Case)"
         + (" – der Kurs liegt darüber." if mos < 0 else ""))))
    st.markdown("**Risiken (aus Kennzahlen)**\n\n" + "\n".join(
        f"- {r}" for r in (e["risiken"] + [f"Kursschwankung {_q_pct(e['vola'], False, 0)} p.a., "
                                           f"größter Rückgang 5 J. {_q_pct(e['dd'], True, 0)}"]))
                + "\n- Wettbewerb, Disruption, Regulierung, Kunden-/Lieferantenabhängigkeit: nicht automatisch bewertbar.")
    if e.get("kat"):
        st.markdown("**Mögliche Katalysatoren (aus Kennzahlen)**\n\n" + "\n".join(f"- {k}" for k in e["kat"]))
    st.markdown("**These-Killer (Kontrollpunkte)**\n\n" + "\n".join(f"- {k}" for k in e["killer"]))


def qualitaet(k):
    """Frueher _render_qualitaet in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BR = k['BR']
    DV = k['DV']
    INDEX_REGIONEN_APP = k['INDEX_REGIONEN_APP']
    Q_KLASSEN = k['Q_KLASSEN']
    Q_SPALTEN = k['Q_SPALTEN']
    _auswahl_art = k['_auswahl_art']
    _div_rhythmen = k['_div_rhythmen']
    _index_auswahl = k['_index_auswahl']
    _listen_laenge = k['_listen_laenge']
    _q_alle = k['_q_alle']
    _q_details = k['_q_details']
    _q_dividenden_tabelle = k['_q_dividenden_tabelle']
    _q_mitglieder = k['_q_mitglieder']
    _q_sektoren_tabelle = k['_q_sektoren_tabelle']
    _q_tabelle = k['_q_tabelle']
    _q_vergleich = k['_q_vergleich']
    _wochen_bilanz = k['_wochen_bilanz']
    auswahl_kompakt = k['auswahl_kompakt']
    daten_q = k['daten_q']
    gh_read_taeglich = k['gh_read_taeglich']
    ranglisten_stand = k['ranglisten_stand']
    daten = gh_read_taeglich("state/qualitaet.json", None)
    if not daten or not daten.get("kategorien"):
        st.info("Noch kein Qualitäts-Score vorhanden. Der Agent läuft täglich um 05:00 Uhr. Für einen "
                "Sofortstart: auf GitHub unter **Actions → Watchlist Qualitäts-Score (täglich) → Run "
                "workflow**. Die Kennzahlen aller Aktien werden in den ersten Tagen "
                "schrittweise aufgebaut (bis zu 3.000 je Lauf, große Werte zuerst).")
        return
    daten_q.clear()                 # gemeinsames Woerterbuch fuellen statt neu binden (auch fuer _q_details)
    daten_q.update(daten)
    kats = daten["kategorien"]
    keys = [k for k in daten.get("reihenfolge", kats) if k in kats]
    titel = [kats[k]["titel"] for k in keys]
    werte = daten.get("werte", {})
    ansichten = ["Gesamt-Rangliste"] + list(Q_KLASSEN.values())

    # Filter in einem aufklappbaren Bereich (auf dem Handy sonst ~1.100 px Bedienelemente vor der Liste);
    # die Ueberschrift zeigt die aktuelle Auswahl
    _ss = st.session_state
    if (_ss.get("q_auswahl_art") or "Kategorie") == "Index":
        _reg = _ss.get("q_region") or ""
        _was = str(_ss.get(f"q_index_{_reg}") or _reg or "Index").split(" (")[0]
    else:
        _was = str(_ss.get("q_kategorie") or titel[0])
    _filter_titel = " · ".join(x for x in (
        _was, _ss.get("q_laenge") or "Top 500",
        str(_ss.get("q_sektor") or "").split(" ", 1)[-1] if _ss.get("q_sektor") not in (None, "Alle Sektoren") else "",
        _ss.get("q_klasse") if _ss.get("q_klasse") not in (None, ansichten[0]) else "",
        f"Dividende {_ss.get('q_div_filter')}" if _ss.get("q_div_filter") not in (None, "Alle") else "",
        f"Ausschüttung {_ss.get('q_div_rhythmus')}" if _ss.get("q_div_rhythmus") not in (None, "Alle") else "",
        "nachhaltig" if _ss.get("q_div_nachhaltig") else "",
        "nach Dividende sortiert" if _ss.get("q_sortierung") == "Dividendenrendite" else "") if x)
    with st.expander(f"🔎 Filter: {_filter_titel}", expanded=False, key="q_filter_exp"):
        if _auswahl_art("q") == "Index":
            # Index: Rangliste aus den Gesamtdaten, gleiche Sortierung wie der Agent
            gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
            idx_key = _index_auswahl("q", gruppen.get("indizes") or {}, INDEX_REGIONEN_APP)
            if not idx_key:
                return
            alle, _ = _q_alle()
            info = gruppen["indizes"][idx_key]
            mitglieder = [s for s in info.get("s", []) if s in alle]
            werte = {s: alle[s] for s in mitglieder}
            n = _listen_laenge("q")

            def rang(liste):
                return sorted(liste, key=lambda s: (-werte[s]["gesamt"], -(werte[s]["b_ant"] or 0)))[:n]

            kat = {"top": rang(mitglieder), "universum": info.get("zugeordnet", len(mitglieder)),
                   "bewertet": len(mitglieder),
                   "je_klasse": {kl: rang([s for s in mitglieder if werte[s]["klasse"] == kl]) for kl in Q_KLASSEN},
                   "klassen": {kl: sum(1 for s in mitglieder if werte[s]["klasse"] == kl) for kl in Q_KLASSEN}}
            kat_key = f"i:{idx_key}"
        else:
            wahl = auswahl_kompakt("Kategorie", titel, default=titel[0], key="q_kategorie")
            kat_key = keys[titel.index(wahl)] if wahl in titel else keys[0]
            kat = kats[kat_key]
            n = _listen_laenge("q")
            if n > len(kat.get("top") or []):
                # Laengere Liste aus den Gesamtdaten - gleiche Sortierung wie der Agent
                gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
                alle, _ = _q_alle()
                g = (gruppen.get("kategorien") or {}).get(kat_key) or {}
                if alle and (kat_key == "alle" or g.get("s")):
                    mitglieder = list(alle) if kat_key == "alle" else [s_ for s_ in g["s"] if s_ in alle]
                    werte = {**werte, **{s_: alle[s_] for s_ in mitglieder}}

                    def rang_k(liste):
                        return sorted(liste, key=lambda s_: (-werte[s_]["gesamt"], -(werte[s_]["b_ant"] or 0)))[:n]

                    kat = dict(kat, top=rang_k(mitglieder),
                               je_klasse={kl: rang_k([s_ for s_ in mitglieder if werte[s_]["klasse"] == kl])
                                          for kl in Q_KLASSEN})
            else:
                kat = dict(kat, top=kat["top"][:n], je_klasse={k: v[:n] for k, v in kat["je_klasse"].items()})
        # Firmen-Kategorie (Sektor, aus der Yahoo-Branche): Rangliste aus allen Aktien der Auswahl
        sek_opt = ["Alle Sektoren"] + [f"{BR.SEKTOR_ICON[x]} {x}" for x in BR.SEKTOREN + ["Sonstige"]]
        sek_wahl = auswahl_kompakt("Firmen-Kategorie (Sektor)", sek_opt, default=sek_opt[0], key="q_sektor") or sek_opt[0]
        alle_q, _ = _q_alle()
        mitglieder_alle = _q_mitglieder(kat_key, alle_q)
        sektor = sek_wahl.split(" ", 1)[1] if sek_wahl != sek_opt[0] else None
        # Dividenden: Filter nach Hoehe/Nachhaltigkeit und Sortierung nach Rendite
        div_filter = st.selectbox("Dividende", list(DV.FILTER), key="q_div_filter") or "Alle"
        nur_nachhaltig = st.toggle("Nur nachhaltige Dividende", key="q_div_nachhaltig",
                                   help="Ausschüttungsquote höchstens 80 % des Gewinns")
        rhythmen = _div_rhythmen()
        rh_filter = st.selectbox("Ausschüttung", ["Alle"] + list(getattr(DV, "RHYTHMEN", ("monatlich", "alle 2 Monate", "quartalsweise", "halbjährlich", "jährlich"))), key="q_div_rhythmus",
                                 help="Wie oft die Dividende gezahlt wird – ermittelt aus den Zahlungsterminen "
                                      "der letzten zwei Jahre (Yahoo Finance)") or "Alle"
        if rh_filter != "Alle" and not rhythmen:
            st.info("Der Auszahlungsrhythmus wird beim nächsten nächtlichen Lauf der Ranglisten ermittelt – "
                    "bis dahin findet dieser Filter keine Werte.")
        sortierung = st.pills("Sortieren nach", ["Punkte", "Dividendenrendite"], default="Punkte",
                              key="q_sortierung") or "Punkte"
        nach_div = sortierung == "Dividendenrendite"
        gefiltert = bool(sektor or div_filter != "Alle" or nur_nachhaltig or nach_div or rh_filter != "Alle")
        if gefiltert and not mitglieder_alle:
            st.warning("Die Gesamtdaten sind gerade nicht lesbar – Filter bitte später erneut versuchen.")
            sektor, gefiltert = None, False
        if gefiltert:
            werte = {**werte, **{s_: alle_q[s_] for s_ in mitglieder_alle}}
            im_sektor = [s_ for s_ in mitglieder_alle
                         if (not sektor or BR.sektor(alle_q[s_].get("br")) == sektor)
                         and DV.passt(alle_q[s_], div_filter, nur_nachhaltig)
                         and (rh_filter == "Alle" or rhythmen.get(s_) == rh_filter)]

            def rang_sek(liste):
                if nach_div:
                    return sorted(liste, key=lambda s_: (-(werte[s_].get("div") or 0), -werte[s_]["gesamt"]))[:n]
                return sorted(liste, key=lambda s_: (-werte[s_]["gesamt"], -(werte[s_]["b_ant"] or 0)))[:n]

            kat = dict(kat, top=rang_sek(im_sektor), bewertet=len(im_sektor), universum=len(mitglieder_alle),
                       je_klasse={kl: rang_sek([s_ for s_ in im_sektor if werte[s_]["klasse"] == kl])
                                  for kl in Q_KLASSEN},
                       klassen={kl: sum(1 for s_ in im_sektor if werte[s_]["klasse"] == kl) for kl in Q_KLASSEN})
        a_wahl = st.pills("Einordnung", ansichten, default=ansichten[0], key="q_klasse") or ansichten[0]
    if rhythmen:
        werte = {s_: (dict(w, aus=rhythmen[s_]) if s_ in rhythmen else w) for s_, w in werte.items()}
    if mitglieder_alle:
        with st.expander("🏷️ Firmen-Kategorien im Überblick"):
            _q_sektoren_tabelle(alle_q, mitglieder_alle)
        with st.expander("💶 Dividenden-Kategorien im Überblick"):
            _q_dividenden_tabelle(alle_q, mitglieder_alle)
    if a_wahl == ansichten[0]:
        symbole, liste_key = kat["top"], f"{kat_key}|top"
    else:
        kl = next(k for k, v in Q_KLASSEN.items() if v == a_wahl)
        symbole, liste_key = kat["je_klasse"].get(kl, []), f"{kat_key}|{kl}"
    # Wochenvergleich gibt es nur fuer die Ranglisten des Agenten, nicht fuer eigene Filter
    vergleich = None if gefiltert else (daten.get("vergleich") or {}).get(liste_key)

    stand = ranglisten_stand(daten)
    abd = daten.get("abdeckung", {})
    kl = kat["klassen"]
    _filter_txt = " · ".join(x for x in (f"Sektor {sektor}" if sektor else "",
                                         f"Dividende {div_filter}" if div_filter != "Alle" else "",
                                         f"Ausschüttung {rh_filter}" if rh_filter != "Alle" else "",
                                         "nachhaltig" if nur_nachhaltig else "",
                                         "sortiert nach Dividendenrendite" if nach_div else "") if x)
    basis_txt = (f"Aktien der Auswahl ({_filter_txt})" if gefiltert else
                 "Indexmitgliedern" if kat_key.startswith("i:") else "Aktien")
    st.caption(
        f"Stand {stand} · {kat['bewertet']} von {kat['universum']} {basis_txt} bewertet · "
        f"Priorität {kl['prio']} · Beobachten {kl['beobachten']} · Nicht weiterverfolgen {kl['nicht']}"
    )
    if "offen" in abd:
        # Neuer Lauf: unterscheidet "noch nie abgerufen" von "Yahoo liefert keine Daten"
        if abd["offen"] > 0:
            st.warning(f"Aufbau läuft: {abd['offen']} Aktien wurden noch nicht abgerufen – jeder Lauf "
                       "ergänzt bis zu 3.000, große Werte zuerst.")
        if abd.get("ohne_daten"):
            st.caption(f"ℹ️ {abd['ohne_daten']} Aktien liefern bei Yahoo zu wenige Geschäftszahlen "
                       "(< 3 Jahre Abschlüsse, z. B. Neuemissionen, Fonds, Mantel) und werden nicht bewertet. "
                       "Sie werden alle 3 Tage erneut versucht.")
    elif abd.get("mit_kennzahlen", 0) < 0.9 * abd.get("universum", 1):
        st.caption(f"ℹ️ Kennzahlen für {abd.get('mit_kennzahlen', 0)} von {abd.get('universum', 0)} Aktien. "
                   "Der Rest liefert bei Yahoo vermutlich zu wenige Geschäftszahlen – die genaue "
                   "Aufteilung zeigt der nächste Lauf.")
    if not symbole:
        st.info("In dieser Einordnung gibt es hier derzeit keine Aktie.")
        return

    titel_fokus = ["📊 Alle Kennzahlen"] + [t for _, t, _, _ in Q_SPALTEN]
    f_wahl = auswahl_kompakt("Kennzahl in der Tabelle", titel_fokus, default=titel_fokus[0],
                      key="q_fokus") or titel_fokus[0]
    if f_wahl == titel_fokus[0]:
        _q_vergleich(werte, symbole)
    else:
        fokus = next((k for k, t, _, _ in Q_SPALTEN if t == f_wahl), "roic")
        _q_tabelle(werte, symbole, vergleich, fokus)
    if not gefiltert and (vergleich is not None or daten.get("vergleich_seit") is None):
        _wochen_bilanz([(r, werte[s]["name"] if s in werte else s, s, (vergleich or {}).get("vor", {}).get(s))
                        for r, s in enumerate(symbole, 1)],
                       (vergleich or {}).get("raus", []), daten.get("vergleich_seit"))

    optionen = [s for s in symbole if s in werte]
    auswahl = st.selectbox("Detailanalyse:", optionen, index=None, key="q_detail",
                           placeholder="Aktie auswählen …",
                           format_func=lambda s: f"{werte[s]['name']} ({s}) – {werte[s]['gesamt']} Punkte")
    if auswahl:
        _q_details(auswahl, werte[auswahl])

    with st.expander("Methodik und Grenzen", expanded=False):
        st.markdown(
            "**100 Punkte:** Unternehmensqualität 20 · Wachstum & Reinvestment 15 · Free Cashflow & "
            "Gewinnqualität 15 · Bilanz 10 · Management & Kapitalallokation 10 · Wettbewerbsvorteil 10 · "
            "Bewertung 15 · Chance-Risiko 5. Red Flags (z. B. negativer FCF, Verwässerung > 5 % p. a., "
            "stark steigende Schulden, SBC > 10 % vom Umsatz, extreme eingepreiste Erwartungen) ziehen "
            "Punkte ab.\n\n"
            "**Einordnung:** Qualität (die 80 Punkte ohne Bewertung) und Bewertung werden getrennt "
            "betrachtet. *Hohe Analysepriorität* = Qualität ≥ 70 %, Bewertung ≥ 55 %, mind. 65 Punkte, "
            "keine schwere Red Flag. *Beobachtungsliste* = Qualität ≥ 62 %, aber zu wenig "
            "Sicherheitsmarge. Alles andere: *Nicht weiterverfolgen*.\n\n"
            "**Näherungen:** Moat und Management lassen sich nicht aus Zahlen ablesen – sie werden über "
            "ROIC-Höhe und -Stabilität, Bruttomarge, Margenstabilität, Aktienanzahl, ROIC-Trend und "
            "Zukäufe angenähert. Qualitative Risiken (Wettbewerb, Disruption, Regulierung) werden nicht "
            "bewertet.\n\n"
            "**Nicht bewertet:** Banken und Versicherungen (Free Cashflow, ROIC und EBITDA sind dort "
            f"nicht sinnvoll definiert) – derzeit {abd.get('finanzwerte', 0)} Werte.\n\n"
            "**Daten:** Yahoo Finance – bis zu 5 Geschäftsjahre, wöchentlich aufgefrischt; Kurse und "
            "Bewertung täglich. Alle Beträge in Euro umgerechnet. Fehlerhafte Quelldaten sind möglich – "
            "vor jeder Entscheidung im Geschäftsbericht prüfen.\n\n"
            "**Keine Kauf- oder Verkaufsempfehlung.** Ein hervorragendes Unternehmen kann zum falschen "
            "Preis unattraktiv sein; eine billig aussehende Aktie wird dadurch nicht attraktiv."
        )


def qualitaet_kurs(k):
    """Frueher _render_qualitaet_kurs in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    INDEX_REGIONEN_APP = k['INDEX_REGIONEN_APP']
    QK_FELDER = k['QK_FELDER']
    QK_QUAL_GRENZE = k['QK_QUAL_GRENZE']
    QK_ZEITRAEUME = k['QK_ZEITRAEUME']
    _auswahl_art = k['_auswahl_art']
    _index_auswahl = k['_index_auswahl']
    _listen_laenge = k['_listen_laenge']
    _q_details = k['_q_details']
    _qk_daten = k['_qk_daten']
    _qk_diagramm = k['_qk_diagramm']
    _qk_einteilen = k['_qk_einteilen']
    _qk_tabelle = k['_qk_tabelle']
    _qk_zeilen = k['_qk_zeilen']
    auswahl_kompakt = k['auswahl_kompakt']
    vz_zahl = k['vz_zahl']
    m = _qk_daten()
    if not m:
        st.info("Noch keine Daten für den Abgleich. Die Kursentwicklung wird ab dem nächsten Lauf des "
                "Qualitäts-Agenten mitgespeichert; bis alle Aktien sie haben, dauert es einige Läufe.")
        return
    gruppen = m["gruppen"]
    if _auswahl_art("qk") == "Index":
        idx_key = _index_auswahl("qk", gruppen.get("indizes") or {}, INDEX_REGIONEN_APP)
        if not idx_key:
            return
        zeilen = [m["alle"][s_] for s_ in gruppen["indizes"][idx_key].get("s", []) if s_ in m["alle"]]
    else:
        kats = gruppen["kategorien"]
        keys = [k for k in gruppen.get("reihenfolge", kats) if k in kats]
        titel = [kats[k]["titel"] for k in keys]
        wahl = auswahl_kompakt("Kategorie", titel, default=titel[0], key="qk_kategorie") or titel[0]
        zeilen = _qk_zeilen(m, keys[titel.index(wahl)] if wahl in titel else keys[0])
    import wikifolio_liste as WL
    zr_titel = [t for _, t in WL.nach_wichtigkeit(QK_ZEITRAEUME, lambda z: z[0])]
    zr_wahl = st.pills("Zeitraum", zr_titel, default="1 Jahr", key="qk_zeitraum") or "1 Jahr"
    zr_key = dict((t, k) for k, t in QK_ZEITRAEUME)[zr_wahl]

    felder, median = _qk_einteilen(zeilen, zr_key)
    mit = sum(len(v) for v in felder.values())
    if not mit:
        st.info("Für diese Kategorie liegt die Kursentwicklung noch nicht vor – sie wird mit den nächsten "
                "Läufen aufgebaut.")
        return
    st.caption(f"{mit} von {len(zeilen)} bewerteten Aktien mit Kursdaten · Trennlinien: Qualität "
               f"{QK_QUAL_GRENZE} % (ohne Bewertung) und Median der Kursentwicklung ({vz_zahl(median, 1)} %)")
    _qk_diagramm(zeilen, zr_key, zr_wahl, median)

    f_titel = [f"{t} ({len(felder[f])})" for f, t, _ in QK_FELDER]
    f_wahl = auswahl_kompakt("Feld", f_titel, default=f_titel[0], key="qk_feld")
    f_key, _, f_text = QK_FELDER[f_titel.index(f_wahl) if f_wahl in f_titel else 0]
    st.caption(f_text)
    liste = felder[f_key][:_listen_laenge("qk")]
    if not liste:
        st.info("In diesem Feld liegt derzeit keine Aktie.")
        return
    _qk_tabelle(liste, zr_key, zr_wahl)
    st.markdown('<div class="q-legende">Punkte: <span class="q-prio">■</span> Hohe Analysepriorität · '
                '<span class="q-beob">■</span> Beobachtungsliste · <span class="q-nicht">■</span> '
                'Nicht weiterverfolgen · MoS = Sicherheitsmarge zum konservativen fairen Wert</div>',
                unsafe_allow_html=True)
    auswahl = st.selectbox("Detailanalyse:", [z["s"] for z in liste], index=None, key="qk_detail",
                           placeholder="Aktie auswählen …",
                           format_func=lambda s: next(f'{z["name"]} ({s}) – {z["gesamt"]} Punkte'
                                                      for z in liste if z["s"] == s))
    if auswahl:
        _q_details(auswahl, next(z for z in liste if z["s"] == auswahl))


def ue_abschnitte(k, dq, dp, umfang, teile):
    """Frueher _ue_abschnitte in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BR = k['BR']
    QK_FELDER = k['QK_FELDER']
    Q_KLASSEN_KURZ = k['Q_KLASSEN_KURZ']
    UE_ZEITRAEUME = k['UE_ZEITRAEUME']
    _qk_daten = k['_qk_daten']
    _qk_einteilen = k['_qk_einteilen']
    _seit_text = k['_seit_text']
    _trend = k['_trend']
    _ue_qualitaets_tabelle = k['_ue_qualitaets_tabelle']
    _ue_z = k['_ue_z']
    vz_zahl = k['vz_zahl']
    """Liste von Abschnitten: {"titel", "text", "spalten": [(name, gewicht, ausrichtung)],
    "zeilen": [[zelle, ...]], "seite": neue Seite im PDF}"""
    ab = []
    werte = (dq or {}).get("werte", {})
    kats = (dq or {}).get("kategorien", {})
    keys = [k for k in (dq or {}).get("reihenfolge", kats) if k in kats]
    verg = (dq or {}).get("vergleich") or {}

    if "Zusammenfassung" in teile and kats:
        zeilen = []
        for k in keys:
            kat, v = kats[k], verg.get(f"{k}|top")
            neu = sum(1 for s in kat["top"] if v is not None and s not in v["vor"])
            zeilen.append([_ue_z(kat["titel"], fett=True), _ue_z(kat["universum"]), _ue_z(kat["bewertet"]),
                           _ue_z(kat["klassen"]["prio"], "prio", True), _ue_z(kat["klassen"]["beobachten"], "beob"),
                           _ue_z(kat["klassen"]["nicht"], "nicht"),
                           _ue_z(neu if v is not None else "–", "up" if neu else None),
                           _ue_z(len(v["raus"]) if v is not None else "–", "down" if v and v["raus"] else None)])
        ab.append({"titel": "Zusammenfassung Qualitäts-Score", "seite": False,
                   "text": "Anzahl Aktien je Kategorie und Einordnung; Neu/Raus bezieht sich auf die "
                           f"Top {dq.get('top_n', 50)} der Gesamt-Rangliste gegenüber vor 7 Tagen.",
                   "spalten": [("Kategorie", 22, "l"), ("Aktien", 7, "r"), ("bewertet", 7, "r"),
                               ("Priorität", 7, "r"), ("Beobachten", 7, "r"), ("Nicht weiterv.", 8, "r"),
                               ("Neu (7 T.)", 7, "r"), ("Raus (7 T.)", 7, "r")],
                   "zeilen": zeilen})

    for teil, kl, text in (("Hohe Analysepriorität", "prio",
                            "Fundamental starke Unternehmen, deren aktuelle Bewertung eine genauere Prüfung rechtfertigt."),
                           ("Beobachtungsliste", "beobachten",
                            "Sehr gute Unternehmen, deren Bewertung aktuell wenig Sicherheitsmarge bietet "
                            "oder bei denen einzelne Kennzahlen das Bild trüben.")):
        if teil in teile and "alle" in kats:
            symbole = kats["alle"]["je_klasse"].get(kl, [])
            sp, zl = _ue_qualitaets_tabelle(werte, symbole, verg.get(f"alle|{kl}"), umfang)
            ab.append({"titel": f"{teil} – alle Aktien (Top {min(umfang, len(symbole))} von "
                                f"{kats['alle']['klassen'][kl]})", "text": text, "spalten": sp,
                       "zeilen": zl, "seite": True})

    if "Qualität je Kategorie" in teile:
        for k in keys:
            if k == "alle":
                continue
            kat = kats[k]
            sp, zl = _ue_qualitaets_tabelle(werte, kat["top"], verg.get(f"{k}|top"), umfang)
            if zl:
                ab.append({"titel": f"Qualitäts-Score: {kat['titel']}",
                           "text": f"Gesamt-Rangliste, Top {len(zl)} von {kat['bewertet']} bewerteten Aktien.",
                           "spalten": sp, "zeilen": zl, "seite": True})

    if "Qualität × Kurs" in teile:
        mq = _qk_daten()
        if mq:
            zeilen_alle = list(mq["alle"].values())
            felder, median = _qk_einteilen(zeilen_alle, "p12")
            for f_key, f_titel, f_text in QK_FELDER[:3]:
                zl = []
                for platz, z in enumerate(felder[f_key][:umfang], 1):
                    fy = z.get("fcfy")
                    zl.append([_ue_z(platz, fett=True), _ue_z(f'{z["name"]} ({z["s"]})', fett=True),
                               _ue_z(BR.kategorie_text(z.get("br")) if z.get("br") else "–"),
                               _ue_z(f'{vz_zahl(z["p12"], 1)} %', "up" if z["p12"] >= 0 else "down", True),
                               _ue_z(f'{z["q_ant"]:.0f} %'),
                               _ue_z(z["gesamt"], {"prio": "prio", "beobachten": "beob"}.get(z["klasse"], "nicht"), True),
                               _ue_z("–" if fy is None else f"{FMT.pct(fy, 1)}", "up" if (fy or 0) >= 5 else None),
                               _ue_z(z.get("bew") or "–"),
                               _ue_z("–" if z.get("mos") is None or z["mos"] <= -200 else f'{z["mos"]:+.0f} %')])
                ab.append({"titel": f"Qualität × Kurs (1 Jahr): {f_titel[2:].strip()} – alle Aktien "
                                    f"(Top {len(zl)} von {len(felder[f_key])})",
                           "text": f_text + (f" Median Kursentwicklung: {vz_zahl(median, 1)} %." if median is not None else ""),
                           "spalten": [("#", 3, "r"), ("Unternehmen", 22, "l"), ("Branche", 14, "l"),
                                       ("Kurs 1 J.", 7, "r"), ("Qualität", 7, "r"), ("Punkte", 6, "r"),
                                       ("FCF-Rendite", 8, "r"), ("Bewertung", 8, "l"), ("MoS", 7, "r")],
                           "zeilen": zl, "seite": True})

    if "Wochenveränderung" in teile and verg:
        zeilen = []
        for k in keys:
            v = verg.get(f"{k}|top")
            if v is None:
                continue
            neu = [f"{werte[s]['name']} (Platz {i})" for i, s in enumerate(kats[k]["top"], 1)
                   if s not in v["vor"] and s in werte]
            raus = [f"{r['name']} ({r['vor']} → " + (str(r["jetzt"]) if r.get("jetzt") else
                    Q_KLASSEN_KURZ.get(r.get("klasse"), "ohne Daten")) + ")" for r in v["raus"]]
            auf = sorted(((v["vor"][s] - i, werte[s]["name"], i) for i, s in enumerate(kats[k]["top"], 1)
                          if s in v["vor"] and s in werte and v["vor"][s] > i), reverse=True)[:3]
            zeilen.append([_ue_z(kats[k]["titel"], fett=True),
                           _ue_z("; ".join(neu) or "–", "up" if neu else None),
                           _ue_z("; ".join(raus) or "–", "down" if raus else None),
                           _ue_z("; ".join(f"{n} ▲ {d}" for d, n, _ in auf) or "–")])
        seit = _seit_text(dq.get("vergleich_seit")) or ""
        ab.append({"titel": "Wochenveränderung Qualitäts-Score (Gesamt-Rangliste)", "seite": True,
                   "text": seit, "spalten": [("Kategorie", 14, "l"), ("Neu aufgenommen", 30, "l"),
                                             ("Rausgeflogen (vorher → jetzt)", 30, "l"),
                                             ("Größte Aufsteiger", 26, "l")], "zeilen": zeilen})

    if "Performance" in teile and dp and dp.get("kategorien"):
        titel_zr = dict((k, t) for k, t in dp.get("zeitraeume", []))
        div_zr = tuple(dp.get("dividenden_zeitraum") or ("DIV", "Div.-Rendite"))
        for k in dp.get("reihenfolge") or list(dp["kategorien"]):
            kat = dp["kategorien"].get(k)
            if not kat:
                continue
            zrs = [z for z in UE_ZEITRAEUME if kat["top"].get(z)]
            if kat.get("dividende") and kat["top"].get(div_zr[0]):
                zrs.append(div_zr[0])
            if not zrs:
                continue
            zeilen = []
            for platz in range(1, umfang + 1):
                z = [_ue_z(platz, fett=True)]
                leer = True
                for zr in zrs:
                    liste = kat["top"][zr]
                    if platz > len(liste):
                        z.append(_ue_z(""))
                        continue
                    e, leer = liste[platz - 1], False
                    wert = e.get("div") if zr == div_zr[0] else e.get("perf")
                    zahl = "–" if wert is None else (f"{FMT.pct(wert, 2)}" if zr == div_zr[0] else f"{vz_zahl(wert, 1)} %")
                    v = (kat.get("vergleich") or {}).get(zr)
                    trend = _trend(e.get("vor"), platz)[0] if v is not None else ""
                    name = e["name"] if len(e["name"]) <= 26 else e["name"][:25] + "…"
                    z.append(_ue_z(f"{name}\n{zahl}\t{trend}" if trend else f"{name}\n{zahl}",
                                   "up" if (wert or 0) >= 0 else "down"))
                if not leer:
                    zeilen.append(z)
            ab.append({"titel": f"Performance: {kat['titel']}", "seite": True,
                       "text": "Kursentwicklung je Zeitraum (ohne Dividenden), Top "
                               f"{min(umfang, 50)} je Spalte; ▲/▼ = Platzveränderung zu vor 7 Tagen.",
                       "spalten": [("#", 3, "r")] + [(titel_zr.get(z, div_zr[1] if z == div_zr[0] else z), 12, "l")
                                                     for z in zrs],
                       "zeilen": zeilen})
    return ab


def ue_pdf(k, abschnitte, stand_text):
    """Frueher _ue_pdf in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    UE_FARBEN_DRUCK = k['UE_FARBEN_DRUCK']
    html = k['html']
    """Druckfertiges PDF (A4 quer). Pfeile werden als Vektorgrafik gezeichnet -
    Symbolschriften sind nicht auf jedem Geraet/Drucker vorhanden."""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    class Trend(Flowable):
        """▲ 3 / ▼ 2 als gezeichnetes Dreieck + Zahl"""
        def __init__(self, richtung, text, farbe, groesse=6.5):
            super().__init__()
            self.richtung, self.text, self.farbe, self.g = richtung, text, farbe, groesse
            self.width, self.height = 18 * mm, self.g + 1

        def wrap(self, *a):
            return self.width, self.height

        def draw(self):
            c = self.canv
            c.setFillColor(colors.HexColor(self.farbe))
            s = self.g * 0.8
            if self.richtung == "up":
                pfad = [(0, 0.5), (s, 0.5), (s / 2, s + 0.5)]
            else:
                pfad = [(0, s + 0.5), (s, s + 0.5), (s / 2, 0.5)]
            p = c.beginPath()
            p.moveTo(*pfad[0])
            for pt in pfad[1:]:
                p.lineTo(*pt)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", self.g)
            c.drawString(s + 2, 0.8, self.text)

    grund = ParagraphStyle("u", fontName="Helvetica", fontSize=6.6, leading=8)
    fett = ParagraphStyle("uf", parent=grund, fontName="Helvetica-Bold")
    titel = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=12.5, leading=15, spaceAfter=2)
    klein = ParagraphStyle("k", fontName="Helvetica", fontSize=7.5, leading=9.5,
                           textColor=colors.HexColor("#4B5563"), spaceAfter=5)
    breite = landscape(A4)[0] - 20 * mm

    # Koepfe fuer die schmalen PDF-Spalten: Umbruch nur an Leerzeichen
    PDF_KOPF = {"FCF/Aktie-Wachst.": "FCF/ Aktie p.a.", "FCF-Rendite": "FCF Rend.",
                "Forward-KGV": "Fwd KGV", "Umsatz-Wachst.": "Umsatz p.a.", "EPS-Wachst.": "EPS p.a.",
                "FCF-Wachst.": "FCF p.a.", "Net Debt/EBITDA": "ND/ EBITDA", "Verwässerung p.a.": "Aktien p.a.",
                "FCF-Marge": "FCF Marge",
                "Management*": "Mgmt.*", "Bewertung": "Bewer- tung", "Mkap. Mrd €": "Mkap. Mrd €",
                "Einordnung": "Einord.", "Nicht weiterv.": "Nicht weiterv."}

    def trend_zelle(t, farbe_zahl):
        """kleine Zeile: Zahl links, Trend (Dreieck/o/NEU) rechts daneben"""
        if t.startswith(("▲", "▼")):
            hexf = UE_FARBEN_DRUCK["up" if t[0] == "▲" else "down"]
            return Trend("up" if t[0] == "▲" else "down", t[1:].strip(), hexf, groesse=6)
        return Paragraph(f'<font color="{UE_FARBEN_DRUCK["up" if t == "NEU" else "grau"]}"><b>{t}</b></font>',
                         ParagraphStyle("tz", parent=grund, fontSize=6))

    def zelle(text, farbe, ist_fett, ausrichtung):
        hexfarbe = UE_FARBEN_DRUCK.get(farbe) if farbe else None
        if "\t" in text:                  # Performance-Matrix: Name / Zahl + Trend
            name, rest = text.split("\n", 1)
            zahl, t = rest.split("\t", 1)
            innen = Table([[Paragraph(html.escape(name), grund), ""],
                           [Paragraph(f'<font color="{hexfarbe}"><b>{html.escape(zahl)}</b></font>', grund),
                            trend_zelle(t, hexfarbe)]],
                          colWidths=[None, 12 * mm], style=TableStyle([
                              ("SPAN", (0, 0), (1, 0)), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            return innen
        text = text.replace("Netto-Cash", "Netcash")
        erste = text.split("\n")[0]
        if erste[:1] in ("▲", "▼") and "\n" not in text and hexfarbe:
            return Trend("up" if erste[0] == "▲" else "down", erste[1:].strip(), hexfarbe)
        teile_txt = []
        for zeile in text.split("\n"):
            z = html.escape(zeile)
            for sym, rtg in (("▲", "up"), ("▼", "down")):
                # Pfeile im Fliesstext (Performance-Matrix): als farbiges Wort
                z = z.replace(sym + " ", "+" if rtg == "up" else "−")
            teile_txt.append(z)
        inhalt = "<br/>".join(teile_txt)
        if hexfarbe:
            if "\n" in text:        # Performance-Zelle: Name schwarz, Zahl farbig
                kopf, rest = inhalt.split("<br/>", 1)
                inhalt = f'{kopf}<br/><font color="{hexfarbe}"><b>{rest}</b></font>'
            else:
                inhalt = f'<font color="{hexfarbe}">{inhalt}</font>'
        stil = ParagraphStyle("z", parent=fett if ist_fett else grund,
                              alignment=2 if ausrichtung == "r" else 0)
        return Paragraph(inhalt, stil)

    puffer = io.BytesIO()

    def rahmen(c, doc):
        c.saveState()
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(10 * mm, landscape(A4)[1] - 7 * mm, "Ranglisten – Gesamtübersicht")
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#6B7280"))
        c.drawRightString(landscape(A4)[0] - 10 * mm, landscape(A4)[1] - 7 * mm, stand_text)
        c.drawString(10 * mm, 6 * mm, "Keine Kauf- oder Verkaufsempfehlung. Kennzahlen aus Yahoo Finance, "
                                      "Moat/Management (*) aus Kennzahlen angenähert.")
        c.drawRightString(landscape(A4)[0] - 10 * mm, 6 * mm, f"Seite {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(puffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title="Ranglisten – Gesamtübersicht")
    inhalt = [Paragraph("Ranglisten – Gesamtübersicht", ParagraphStyle("h", fontName="Helvetica-Bold",
                                                                     fontSize=18, leading=22)),
              Paragraph(stand_text + " · Grün = Hohe Analysepriorität / positiv, Gelb = Beobachtungsliste, "
                        "Grau = Nicht weiterverfolgen, Rot = negativ · Dreieck = Platzveränderung zu vor "
                        "7 Tagen, o = unverändert, NEU = neu in der Liste.", klein), Spacer(1, 3 * mm)]
    erste = True
    for a in abschnitte:
        if a["seite"] and not erste:
            inhalt.append(PageBreak())
        erste = False
        inhalt.append(Paragraph(html.escape(a["titel"]), titel))
        if a.get("text"):
            inhalt.append(Paragraph(html.escape(a["text"]), klein))
        if not a["zeilen"]:
            inhalt.append(Paragraph("– keine Einträge –", klein))
            continue
        gewichte = [g for _, g, _ in a["spalten"]]
        spaltenbreiten = [breite * g / sum(gewichte) for g in gewichte]
        kopf = [Paragraph(html.escape(PDF_KOPF.get(n, n)), ParagraphStyle(
            "kopf", parent=fett, fontSize=6.2, leading=7.5, textColor=colors.white,
            alignment=2 if aus == "r" else 0)) for n, _, aus in a["spalten"]]
        daten = [kopf] + [[zelle(t, f, b, aus) for (t, f, b), (_, _, aus) in zip(z, a["spalten"])]
                          for z in a["zeilen"]]
        tab = Table(daten, colWidths=spaltenbreiten, repeatRows=1)
        stil = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5)]
        for r in range(2, len(daten), 2):
            stil.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F3F4F6")))
        tab.setStyle(TableStyle(stil))
        inhalt += [tab, Spacer(1, 4 * mm)]
    inhalt += [Spacer(1, 4 * mm), Paragraph(
        "Methodik: 100 Punkte (Qualität 20, Wachstum 15, Free Cashflow 15, Bilanz 10, Management 10, "
        "Wettbewerbsvorteil 10, Bewertung 15, Chance-Risiko 5) abzüglich Red Flags. Qualität und Bewertung "
        "werden getrennt betrachtet. Banken/Versicherungen sind nicht bewertet. Performance = reine "
        "Kursentwicklung in Euro. Alle Angaben ohne Gewähr – vor jeder Entscheidung im Geschäftsbericht "
        "prüfen.", klein)]
    doc.build(inhalt, onFirstPage=rahmen, onLaterPages=rahmen)
    return puffer.getvalue()


def liste_alle(k, art, werte, stand):
    """Frueher _render_liste_alle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    WK_SEITE = k['WK_SEITE']
    _h = k['_h']
    _listen_laenge = k['_listen_laenge']
    _startauswahl = k['_startauswahl']
    _startwert = k['_startwert']
    _wk_seite = k['_wk_seite']
    vz_zahl = k['vz_zahl']
    """Alle aktiven wikifolios bzw. ETFs mit allen Kennzahlen (*_kennzahlen_N.json des Watchlist-Agenten):
    Sortieren nach Zeitraum oder Kennzahl, Spalten waehlbar, Filter und eigene Bewertung (Mein Score).
    ETFs zusaetzlich: Filter nach Anbieter, Region, Thema, Ertragsverwendung und ohne Hebel/Short."""
    import etf_merkmale as EM
    import wikifolio_liste as WL
    etf = art == "etf"
    p = "etf" if etf else "wk"              # Schluessel der Bedienelemente (etf2_*/wk2_* bleiben je Sitzung)
    einzahl, mehrzahl = ("ETF", "ETFs") if etf else ("wikifolio", "wikifolios")
    zr_titel = {"1M": "Monat", "3M": "3 Monate", "6M": "6 Monate", "1J": "1 Jahr", "2J": "2 Jahre",
                "3J": "3 Jahre", "5J": "5 Jahre", "10J": "10 Jahre"}

    def titel(k):
        return zr_titel.get(k) or WL.TITEL[k]

    da = WL.vorhandene(werte) | {"mein_score"}
    alle = WL.nach_wichtigkeit([k for k in WL.ZEITRAEUME if k in da] + [k for k, *_ in WL.KENNZAHLEN if k in da])
    standard_spalten = list(WL.STANDARD_SPALTEN_ETF if etf else WL.STANDARD_SPALTEN) + ["1J", "3J"]
    sort = st.selectbox("Sortiert nach", alle, format_func=titel, key=f"{p}2_sort",
                        **_startauswahl(f"{p}2_sort", alle) or {"index": alle.index("1J") if "1J" in alle else 0})
    laenge = _listen_laenge(p, alle=etf)
    spalten = st.multiselect("Spalten", [k for k in alle if k != sort], format_func=titel, key=f"{p}2_spalten",
                             default=[k for k in (_startwert(f"{p}2_spalten", standard_spalten)["value"])
                                      if k in alle and k != sort])
    begriff = st.text_input("In der Liste suchen", key=f"{p}_such",
                            placeholder="Name, WKN oder ISIN …" if etf else "Name oder WKN …")

    merkmale = {}
    if etf:
        with st.expander("🧭 Anbieter, Region, Thema", expanded=False):
            m1, m2 = st.columns(2)
            for i, (feld, t) in enumerate((("region", "Region"), ("themen", "Thema"),
                                           ("anbieter", "Anbieter"), ("ertrag", "Ertragsverwendung"))):
                optionen = EM.auswahl(werte, feld)
                anzahl = dict(optionen)
                wahl = (m1 if i % 2 == 0 else m2).multiselect(
                    t, [o for o, _ in optionen], key=f"{p}2_m_{feld}",
                    format_func=lambda o, a=anzahl: f"{o} ({FMT.zahl(a[o], 0)})",
                    default=[o for o in _startwert(f"{p}2_m_{feld}", [])["value"] if o in anzahl],
                    placeholder="alle")
                if wahl:
                    merkmale[feld] = set(wahl)
            merkmale["ohne_hebel"] = st.toggle("Ohne Hebel- und Short-Produkte", key=f"{p}2_ohne_hebel",
                                               **_startwert(f"{p}2_ohne_hebel", True))
            st.caption("Anbieter, Region, Thema und Ausschüttung stammen aus dem ETF-Namen (z. B. „iShares Core "
                       "MSCI World … (Acc)“). Nicht erkennbare Werte stehen unter „Sonstige“ bzw. fehlen bei "
                       "der Ertragsverwendung. Mehrere Themen: mindestens eines muss passen.")

    grenzen = {}
    with st.expander("🔎 Filter (Kennzahlen)", expanded=False):
        f1, f2 = st.columns(2)
        filter_da = [f for f in WL.FILTER if f[0] in da]
        for i, (k, t, f_art, (lo, hi), schritt) in enumerate(filter_da):
            aus_wert = lo if f_art == "min" else hi
            v = (f1 if i % 2 == 0 else f2).slider(t, lo, hi, step=schritt, key=f"{p}2_f_{k}",
                                                  **_startwert(f"{p}2_f_{k}", aus_wert))
            if v != aus_wert:
                grenzen[k] = v
        nur_auf = st.toggle("Nur im Aufwärtstrend (Kurs über der 200-Tage-Linie)", key=f"{p}2_trend",
                            **_startwert(f"{p}2_trend", False))
        st.caption("Ein Regler am Anschlag filtert nicht. Werte ohne die gefilterte Kennzahl (z. B. zu kurze "
                   "Historie) fallen bei aktivem Filter heraus.")
    with st.expander("⚖️ Eigene Bewertung (Mein Score)", expanded=False):
        st.caption(f"Wie wichtig ist dir was? 0 = zählt nicht, 5 = sehr wichtig. Mein Score (0–100) vergleicht "
                   f"jeden Wert mit allen anderen {mehrzahl} nach dem Filter: je Kennzahl der Rangplatz, "
                   "gewichtet gemittelt. Fehlt mehr als die Hälfte der Gewichtung (zu kurze Historie), gibt es keinen "
                   "Score. Unter „Sortiert nach“ → „Mein Score“ wählen.")
        g1, g2 = st.columns(2)
        bewertung = [(k, g) for k, g in (WL.BEWERTUNG_ETF if etf else WL.BEWERTUNG) if k in da]
        gewichte = {k: (g1 if i % 2 == 0 else g2).slider(WL.TITEL[k], 0, 5, key=f"{p}2_g_{k}",
                                                          **_startwert(f"{p}2_g_{k}", g))
                    for i, (k, g) in enumerate(bewertung)}

    aktiv_mm = {k: v for k, v in merkmale.items() if v}
    gefiltert = WL.filtern(werte, grenzen, nur_auf, merkmale=aktiv_mm or None)
    WL.mein_score(gefiltert, gewichte)
    liste = WL.rangliste(gefiltert, sort, begriff, n=laenge)
    signatur = (sort, laenge, begriff, tuple(sorted(grenzen.items())), nur_auf,
                tuple(sorted((k, tuple(sorted(v)) if isinstance(v, set) else v) for k, v in aktiv_mm.items())))
    if st.session_state.get(f"{p}_signatur") != signatur:
        st.session_state[f"{p}_signatur"], st.session_state[f"{p}_seite"] = signatur, 1
    gefiltert_an = bool(grenzen or nur_auf or set(aktiv_mm) - {"ohne_hebel"})
    st.caption(f"Stand {stand} · {FMT.zahl(len(werte), 0)} {'ETFs' if etf else 'aktive wikifolios'}"
               + (f" · nach Filter {FMT.zahl(len(gefiltert), 0)}" if gefiltert_an or len(gefiltert) != len(werte)
                  else "")
               + f" · sortiert nach {titel(sort)}" + (f" · {len(liste)} Treffer" if begriff else ""))
    if not liste:
        st.info(f"Kein {einzahl} erfüllt Filter und Suche – Filter lockern.")
        return
    seiten = max((len(liste) + WK_SEITE - 1) // WK_SEITE, 1)
    nr = min(max(int(st.session_state.get(f"{p}_seite", 1)), 1), seiten)
    teil = liste[(nr - 1) * WK_SEITE:nr * WK_SEITE]
    EINORDNUNG = {"prio": "🟢", "beobachten": "🟡", "nicht": "⚪"}

    def _zelle(w, k):
        v = WL.wert_von(w, k)
        stark = "pt-stark " if k == sort else ""
        if v is None:
            return '<td class="pt-num">–</td>'
        e = "pct" if k in WL.ZEITRAEUME else WL.EINHEIT[k]
        if e == "punkte":
            sym = EINORDNUNG.get(w["kz"].get("_einordnung"), "") if k == "score" else ""
            return f'<td class="pt-num {stark}">{sym} {FMT.zahl(v, 0)}</td>'
        if e == "pct":
            return f'<td class="pt-num {stark}{"pt-up" if v >= 0 else "pt-down"}">{vz_zahl(v, 1)} %</td>'
        if e == "pct_minus":
            return f'<td class="pt-num {stark}{"pt-down" if v < 0 else ""}">{FMT.zahl(v, 1)} %</td>'
        if e == "pct_neutral":
            return f'<td class="pt-num {stark}">{FMT.zahl(v, 1 if k != "gewinnmonate" else 0)} %</td>'
        if e == "tage":
            return f'<td class="pt-num {stark}">{int(v)} T.</td>'
        if e == "jahre":
            return f'<td class="pt-num {stark}">{FMT.zahl(v, 1)} J.</td>'
        return f'<td class="pt-num {stark}{"pt-down" if v < 0 else ""}">{FMT.zahl(v, 2)}</td>'

    def _unterzeile(w):
        if not etf:
            return _h(w["wkn"])
        mm = w.get("mm") or {}
        teile_ = [w["wkn"], mm.get("region"), " · ".join(mm.get("themen") or [])]
        if mm.get("ertrag"):
            teile_.append("Aussch." if mm["ertrag"] == "Ausschüttend" else "Thes.")
        hebel = ' <span class="pt-down">Hebel/Short</span>' if mm.get("hebel") else ""
        return _h(" · ".join(t for t in teile_ if t and t != "Sonstige")) + hebel

    reihenfolge = [sort] + [k for k in spalten if k != sort]
    zeilen = "".join(
        f'<tr class="{"pt-zebra" if w["rang"] % 2 == 0 else ""}">'
        f'<td class="pt-num pt-seit ue-fix wk-rang">{w["rang"]}</td>'
        f'<td class="pt-wert ue-fix wk-name"><span class="pt-name">{_h(w["name"])}</span>'
        f'<span class="pt-sub">{_unterzeile(w)}</span></td>' + "".join(_zelle(w, k) for k in reihenfolge)
        + "</tr>" for w in teil)
    kopf = "".join(f'<th class="pt-num">{"▼ " if k == sort else ""}{_h(titel(k))}</th>' for k in reihenfolge)
    st.markdown('<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                '<table class="pt pt-kompakt ue wk"><thead><tr><th class="pt-num ue-fix wk-rang">#</th>'
                f'<th class="pt-wert ue-fix wk-name">{einzahl}</th>{kopf}</tr></thead>'
                f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    if seiten > 1:
        n1, n2, n3 = st.columns([0.5, 2, 0.5], vertical_alignment="bottom")
        n1.button("◀", key=f"{p}_zur", on_click=_wk_seite, args=(nr - 1, p), disabled=nr <= 1,
                  width="stretch", help="Vorherige Seite")

        def bereich(i):
            t = liste[(i - 1) * WK_SEITE:i * WK_SEITE]
            return f"Rang {t[0]['rang']}–{t[-1]['rang']}  ({i}/{seiten})"

        wahl = n2.selectbox("Seite", list(range(1, seiten + 1)), index=nr - 1, format_func=bereich,
                            key=f"{p}_bereich_{nr}", label_visibility="collapsed")
        if wahl != nr:
            st.session_state[f"{p}_seite"] = wahl
            st.rerun()
        n3.button("▶", key=f"{p}_vor", on_click=_wk_seite, args=(nr + 1, p), disabled=nr >= seiten,
                  width="stretch", help="Nächste Seite")
    with st.expander("Was bedeuten die Kennzahlen?", expanded=False):
        st.caption(
            "**Score**: eigene Bewertung wie unter „ETF- & wikifolio-Score“ (🟢 Priorität, 🟡 beobachten, ⚪ eher "
            "nicht). **Sharpe**: (Rendite p. a. − 2 % risikofrei) / Vola – Ertrag je Schwankung, über 1 gilt "
            "als gut. **Sortino**: wie Sharpe, zählt aber nur Schwankung nach unten. **Calmar 3 J.**: Rendite "
            "p. a. / größter Verlust der letzten 3 Jahre. **Rendite je Verlust**: Rendite p. a. / größter "
            "Verlust seit Beginn. **Vola**: Schwankung der Tageskurse p. a. **Max. Verlust**: größter Rückgang "
            "vom Höchststand (seit Beginn bzw. im letzten Jahr). **Abstand zum Hoch / Tage seit Hoch**: wie weit "
            "und wie lange unter dem Allzeithoch. **Gewinnmonate**: Anteil der Monate mit Plus. **Trend**: "
            "Abstand zur 200-Tage-Linie (positiv = Aufwärtstrend). "
            + ("**Rendite je Risiko**: Rendite p. a. / Vola. **Dividendenrendite**: nur, wo die Datenquelle sie "
               "liefert. **Hebel/Short**: Produkte mit Hebel, Short oder täglicher Neugewichtung – nur für "
               "kurzfristige Spekulation, standardmäßig ausgeblendet. Nicht in den Daten: laufende Kosten "
               "(TER), Fondsvolumen, Replikation. " if etf else "")
            + "Quelle: Kurshistorie ls-tc.de, täglich vom Watchlist-Agenten berechnet. Vergangene Werte sind "
            "keine Prognose.")
    st.caption("Tabelle seitlich wischen für alle Spalten – Rang und Name bleiben stehen. Werte übernehmen: im "
               + ("Portfolio Builder unter „Wert hinzufügen → 🏆 Top-Listen“." if etf else
                  "Portfolio Builder unter „Wert hinzufügen → Wikifolios → Top-Listen“."))


def wikifolios(k):
    """Frueher _render_wikifolios in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    WK_SEITE = k['WK_SEITE']
    WK_SPALTEN = k['WK_SPALTEN']
    _h = k['_h']
    _listen_laenge = k['_listen_laenge']
    _render_wikifolios_alle = k['_render_wikifolios_alle']
    _wk_seite = k['_wk_seite']
    gh_read_taeglich = k['gh_read_taeglich']
    ranglisten_stand = k['ranglisten_stand']
    vz_zahl = k['vz_zahl']
    wikifolio_alle = k['wikifolio_alle']
    wikifolio_kennzahlen = k['wikifolio_kennzahlen']
    wikifolio_rangliste = k['wikifolio_rangliste']
    wikifolio_werte = k['wikifolio_werte']
    """Uebergreifende Liste aller wikifolios der Ranglisten (Top 50 + Top 500 je Zeitraum):
    alle Zeitraeume nebeneinander, sortiert nach einem, seitenweise mit Suche."""
    daten = gh_read_taeglich("state/top50.json", None) or {}
    # Alle Kennzahlen (Sharpe, Vola, Verlust ...), sobald der Watchlist-Agent sie geschrieben hat
    if wikifolio_alle(datetime.date.today().isoformat()):
        _render_wikifolios_alle(None, ranglisten_stand(daten) if daten else "–")
        return
    kat = (daten.get("kategorien") or {}).get("wikifolios")
    if not kat:
        st.info("Noch keine wikifolio-Ranglisten vorhanden – sie entstehen beim nächsten Lauf des "
                "Watchlist-Agenten (täglich 07:30 Uhr).")
        return
    lang = gh_read_taeglich("state/top50_lang_wikifolios.json", None) or {}
    werte = wikifolio_werte(kat, lang)
    import klassen_score as KS
    kz = wikifolio_kennzahlen(datetime.date.today().isoformat())
    kz_titel = {s: t for s, t, _ in KS.SPALTEN} if kz else {}
    titel = {k: t for k, t in (daten.get("zeitraeume") or []) if k in WK_SPALTEN}
    spalten = [k for k in WK_SPALTEN if k in titel]
    zr_titel = [titel[k] for k in spalten]
    # sortieren nach Zeitraum oder nach einer Kennzahl (Score, Vola, max. Verlust ...)
    # Reihenfolge nach Wichtigkeit (Score, Rendite p. a., 1/3/5 Jahre ... kurze Zeitraeume hinten)
    import wikifolio_liste as WL
    titel_von = {**{k: titel[k] for k in spalten}, **kz_titel}
    wahl_titel = [titel_von[k] for k in WL.nach_wichtigkeit(list(titel_von))]
    zr_wahl = st.pills("Sortiert nach", wahl_titel, default="1 Jahr" if "1 Jahr" in zr_titel else zr_titel[0],
                       key="wk_zeitraum") or zr_titel[0]
    nach_kz = next((s for s, t in kz_titel.items() if t == zr_wahl), None)
    zr = None if nach_kz else spalten[zr_titel.index(zr_wahl)]
    laenge = _listen_laenge("wk")
    begriff = st.text_input("In der Liste suchen", key="wk_such", placeholder="Name oder WKN …")
    liste = (KS.rangliste_nach(werte, kz, nach_kz, begriff, n=laenge) if nach_kz
             else wikifolio_rangliste(werte, zr, begriff, n=laenge))
    signatur = (zr, laenge, begriff)
    if st.session_state.get("wk_signatur") != signatur:
        st.session_state["wk_signatur"], st.session_state["wk_seite"] = signatur, 1
    stand = ranglisten_stand(daten)
    st.caption(f"Stand {stand} · {len(werte)} wikifolios in den Ranglisten · {kat.get('aktiv', '–')} aktiv "
               f"· sortiert nach {zr_wahl}" + (f" · {len(liste)} Treffer" if begriff else ""))
    if not liste:
        st.info(f"„{begriff}“ ist nicht unter den Top {laenge} für {zr_wahl}." if begriff else
                "Für diesen Zeitraum liegen keine Werte vor.")
        return
    seiten = max((len(liste) + WK_SEITE - 1) // WK_SEITE, 1)
    nr = min(max(int(st.session_state.get("wk_seite", 1)), 1), seiten)
    teil = liste[(nr - 1) * WK_SEITE:nr * WK_SEITE]
    if kz:
        with st.expander("Was bedeuten Score, Vola und Max. Verlust?", expanded=False):
            st.caption(
                "**Score** (0–100): eigene Bewertung aus Rendite, Rendite je Verlust, max. Verlust, Track Record, "
                "Beständigkeit und Schwankung (wie unter „ETF- & wikifolio-Score“) – 🟢 Priorität, 🟡 beobachten, "
                "⚪ eher nicht. **Rendite je Verlust**: Rendite p. a. geteilt durch den größten Rückgang – je höher, "
                "desto mehr Ertrag pro ausgehaltenem Verlust. **Rendite p. a.**: über den längsten verfügbaren "
                "Zeitraum (darunter die Jahre). **Vola 1 J.**: Schwankung der Tageskurse im letzten Jahr, "
                "aufs Jahr hochgerechnet. **Max. Verlust**: größter Rückgang vom Höchststand seit Beginn der "
                "Kurshistorie. **Historie**: Jahre mit Kursdaten. Quelle: Kurshistorie ls-tc.de, täglich vom "
                "Watchlist-Agenten berechnet. Vergangene Werte sind keine Garantie für die Zukunft.")

    def _pct(v, stark):
        if v is None:
            return '<td class="pt-num">–</td>'
        return (f'<td class="pt-num {"pt-stark " if stark else ""}{"pt-up" if v >= 0 else "pt-down"}">'
                f'{vz_zahl(v, 1)} %</td>')

    EINORDNUNG = {"prio": ("🟢", "pt-up"), "beobachten": ("🟡", ""), "nicht": ("⚪", "")}

    def _kz(w, s, stark):
        v = (kz.get(w["wkn"].upper()) or {}).get(s)
        k = kz.get(w["wkn"].upper()) or {}
        if v is None:
            return '<td class="pt-num">–</td>'
        st_ = "pt-stark " if stark else ""
        if s == "score":
            sym, farbe = EINORDNUNG.get(k.get("einordnung"), ("", ""))
            return f'<td class="pt-num {st_}{farbe}">{sym} {vz_zahl(v, 0).lstrip("+")}</td>'
        if s == "rendite":
            unter = f'<span class="pt-sub">{k["rendite_jahre"]} J.</span>' if k.get("rendite_jahre") else ""
            return (f'<td class="pt-num {st_}{"pt-up" if v >= 0 else "pt-down"}">{vz_zahl(v, 1)} %'
                    f'{unter}</td>')
        if s == "dd":
            return f'<td class="pt-num {st_}pt-down">−{FMT.zahl(v, 1)} %</td>'
        if s == "vola":
            return f'<td class="pt-num {st_}">{FMT.zahl(v, 1)} %</td>'
        if s == "jahre":
            return f'<td class="pt-num {st_}">{FMT.zahl(v, 1)} J.</td>'
        return f'<td class="pt-num {st_}">{FMT.zahl(v, 2)}</td>'                      # Rendite je Verlust

    # sortierte Spalte direkt hinter den Namen (auf dem Handy sonst erst nach Wischen sichtbar)
    spalten = ([zr] if zr else []) + [k for k in spalten if k != zr]
    kz_spalten = ([nach_kz] if nach_kz else []) + [s for s in kz_titel if s != nach_kz]
    vorne = [("kz", nach_kz)] if nach_kz else [("zr", zr)]
    # Kennzahlen direkt nach der Sortierspalte, danach die uebrigen Zeitraeume (am Handy ohne langes Wischen)
    rest = [("kz", s) for s in kz_spalten if s != nach_kz] + [("zr", k) for k in spalten if k != zr]
    reihenfolge = vorne + rest

    def _zelle(w, art, k):
        if art == "zr":
            return _pct(w["perf"].get(k), k == zr)
        return _kz(w, k, k == nach_kz)

    zeilen = "".join(
        f'<tr class="{"pt-zebra" if w["rang"] % 2 == 0 else ""}">'
        f'<td class="pt-num pt-seit ue-fix wk-rang">{w["rang"]}</td>'
        f'<td class="pt-wert ue-fix wk-name"><span class="pt-name">{_h(w["name"])}</span>'
        f'<span class="pt-sub">{_h(w["wkn"])}</span></td>'
        + "".join(_zelle(w, a, k) for a, k in reihenfolge) + "</tr>"
        for w in teil)
    kopf = "".join(
        f'<th class="pt-num">{"▼ " if (a, k) == vorne[0] else ""}{_h(titel[k] if a == "zr" else kz_titel[k])}</th>'
        for a, k in reihenfolge)
    # wie die Gesamtuebersicht: seitlich wischbar (auch am iPhone), Rang und Name bleiben links stehen
    st.markdown('<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                '<table class="pt pt-kompakt ue wk"><thead><tr><th class="pt-num ue-fix wk-rang">#</th>'
                f'<th class="pt-wert ue-fix wk-name">wikifolio</th>{kopf}</tr></thead>'
                f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    if seiten > 1:
        # Rangbereich direkt waehlbar statt langem Scrollen - unter der Tabelle
        n1, n2, n3 = st.columns([0.5, 2, 0.5], vertical_alignment="bottom")
        n1.button("◀", key="wk_zur", on_click=_wk_seite, args=(nr - 1,), disabled=nr <= 1, width="stretch",
                  help="Vorherige Seite")

        def bereich(i):
            t = liste[(i - 1) * WK_SEITE:i * WK_SEITE]
            return f"Rang {t[0]['rang']}–{t[-1]['rang']}  ({i}/{seiten})"

        wahl = n2.selectbox("Seite", list(range(1, seiten + 1)), index=nr - 1, format_func=bereich,
                            key=f"wk_bereich_{nr}", label_visibility="collapsed")
        if wahl != nr:
            st.session_state["wk_seite"] = wahl
            st.rerun()
        n3.button("▶", key="wk_vor", on_click=_wk_seite, args=(nr + 1,), disabled=nr >= seiten,
                  width="stretch", help="Nächste Seite")
    # PDF erst auf Knopfdruck erzeugen: ganze Liste (alle Seiten), alle Zeitraeume
    pdf_schluessel = f"wk_pdf|{stand}|{zr_wahl}|{laenge}|{begriff}"
    if st.button("📄 PDF der ganzen Liste erstellen", key="wk_pdf_knopf", width="stretch"):
        try:
            import wikifolio_pdf
            kopfzeile = (f"Stand {stand} · Top {laenge} sortiert nach {zr_wahl} · {len(liste)} wikifolios"
                         + (f" · Suche „{begriff}“" if begriff else ""))
            st.session_state["wk_pdf"] = (pdf_schluessel, wikifolio_pdf.bericht(liste, spalten, titel, zr,
                                                                                 kopfzeile))
        except ImportError:
            st.error("Für das PDF fehlt das Paket **reportlab** (requirements.txt).")
    fertig = st.session_state.get("wk_pdf")
    if fertig and fertig[0] == pdf_schluessel:
        st.download_button("⬇️ PDF herunterladen", data=fertig[1], mime="application/pdf",
                           file_name=f"wikifolio_Rangliste_{datetime.date.today().isoformat()}.pdf",
                           key="wk_pdf_download", width="stretch")
    st.caption("Tabelle seitlich wischen für alle Zeiträume – Rang und Name bleiben stehen. "
               "– = in diesem Zeitraum nicht unter den Top 500 (oder noch keine so lange Historie). "
               "Werte übernehmen: im Portfolio Builder unter „Wert hinzufügen → Wikifolios → Top-Listen“. "
               "Vergangene Entwicklung ist keine Prognose.")


def klassen_score(k):
    """Frueher _render_klassen_score in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    KS_SEITE = k['KS_SEITE']
    Q_KLASSE_CSS = k['Q_KLASSE_CSS']
    _h = k['_h']
    _ks_de = k['_ks_de']
    _ks_rangliste = k['_ks_rangliste']
    _ks_seite = k['_ks_seite']
    _ks_tabelle = k['_ks_tabelle']
    _listen_laenge = k['_listen_laenge']
    vz_zahl = k['vz_zahl']
    """Eigene Bewertung fuer ETFs und wikifolios (klassen_score.py) - unabhaengig vom Aktien-Score."""
    import klassen_score as KS
    art_titel = {"ETFs": "etf", "wikifolios": "wikifolio"}
    art_wahl = st.pills("Anlageklasse", list(art_titel), default="ETFs", key="ks_art") or "ETFs"
    art = art_titel[art_wahl]
    stand, alle = _ks_rangliste(art)
    if not alle:
        st.info("Noch keine Kursdaten für diese Anlageklasse – sie entstehen beim nächsten Lauf des "
                "Watchlist-Agenten (täglich 07:30 Uhr).")
        return
    kriterien = KS.KRITERIEN[art]
    with st.expander("ℹ️ Wie wird bewertet?"):
        st.markdown(
            f"**{art_wahl} haben eine eigene Bewertung** – unabhängig vom Qualitäts-Score der Aktien "
            "(der beruht auf Geschäftszahlen, die es hier nicht gibt). Bewertet wird die Kurshistorie aus "
            "den Top-500-Daten. Jedes Kriterium gibt 0–100 Punkte, linear zwischen „schwach“ und „stark“; "
            "der Score ist der gewichtete Durchschnitt.")
        einheit = {"rendite": " % p. a.", "rr": "", "rdd": "", "dd": " %", "vola": " %", "historie": " J.",
                   "bestaendig": " %"}
        _ks_tabelle([("Kriterium", "l"), ("Gewicht", "r"), ("schwach (0 P.)", "r"), ("stark (100 P.)", "r")],
                    [[_h(t), f"{g} %",
                      ("−" if k == "dd" else "") + f"{_ks_de(sl, 1 if sl % 1 else 0)}{einheit[k]}",
                      ("−" if k == "dd" else "") + f"{_ks_de(gu, 1 if gu % 1 else 0)}{einheit[k]}"]
                     for k, t, g, sl, gu in kriterien])
        erkl = {"etf": "- **Rendite je Risiko** = Rendite p. a. ÷ Schwankung p. a.\n"
                       "- **Hebel-/Short-Produkte** werden auf höchstens 40 Punkte gedeckelt – sie eignen sich "
                       "nur für kurzfristige Spekulation.\n"
                       "- Nicht enthalten, weil in den Daten nicht vorhanden: laufende Kosten (TER), "
                       "Tracking Difference, Fondsvolumen, Replikation.",
                "wikifolio": "- **Rendite je Rückgang** = Rendite p. a. ÷ maximaler Rückgang. Die gemessene "
                             "Schwankung ist bei wikifolios oft untypisch niedrig, der Rückgang zeigt das "
                             "Verlustrisiko ehrlicher.\n"
                             "- **Track Record:** lange Historie zählt stärker als bei ETFs – kurze Zeiträume "
                             "sind bei aktiven Strategien wenig aussagekräftig.\n"
                             "- Renditen über 60 % p. a. bringen keine Extrapunkte (Ausnahme, nicht "
                             "fortschreibbar).\n"
                             "- Nicht enthalten: Gebühren, investiertes Kapital, Handelsstil des Traders, "
                             "Emittentenrisiko."}[art]
        st.markdown(
            "- **Tabelle:** Rendite p. a. über 1, 3, 5 und 10 Jahre sowie über die gesamte Laufzeit "
            "(„Gesamt p. a.“, ab 1 Jahr Historie).\n"
            "- **Für den Score** zählt die Rendite p. a. aus dem längsten vorhandenen Zeitraum (10, 5, 3 oder 1 Jahr).\n"
            "- **Beständigkeit** = Anteil der Zeiträume (1/3/5/10 Jahre) mit Gewinn.\n" + erkl + "\n"
            f"- **Einordnung:** ab {_ks_de(KS.GRENZE_PRIO, 0)} Punkten *Hohe Analysepriorität* (nur mit mindestens "
            f"{_ks_de(KS.MIN_JAHRE[art], 0)} Jahren Historie, ohne Hebel), ab {_ks_de(KS.GRENZE_BEOBACHTEN, 0)} "
            "*Beobachtungsliste*, darunter *Nicht weiterverfolgen*.\n"
            "- Modellbewertung aus vergangenen Kursen – keine Prognose und keine Kaufempfehlung.")
    ansichten = ["Gesamt-Rangliste"] + list(KS.KLASSEN.values())
    e_wahl = st.pills("Einordnung", ansichten, default=ansichten[0], key="ks_klasse") or ansichten[0]
    laenge = _listen_laenge("ks")
    begriff = st.text_input("In der Liste suchen", key="ks_such", placeholder="Name, WKN oder ISIN …")
    liste = alle
    if e_wahl != ansichten[0]:
        kl = next(k for k, v in KS.KLASSEN.items() if v == e_wahl)
        liste = [e for e in liste if e["bewertung"]["einordnung"] == kl]
    liste = liste[:laenge]
    b_ = str(begriff or "").strip().lower()
    if b_:
        liste = [e for e in liste if b_ in f'{e["name"]} {e["kennung"]} {e["isin"]}'.lower()]
    signatur = (art, e_wahl, laenge, begriff)
    if st.session_state.get("ks_signatur") != signatur:
        st.session_state["ks_signatur"], st.session_state["ks_seite"] = signatur, 1
    anz = {k: sum(1 for e in alle if e["bewertung"]["einordnung"] == k) for k in KS.KLASSEN}
    try:
        stand_txt = datetime.date.fromisoformat(str(stand)[:10]).strftime("%d.%m.%Y")
    except Exception:
        stand_txt = str(stand) or "–"
    st.caption(f"Stand {stand_txt} · {len(alle)} {art_wahl} bewertet · Priorität {anz['prio']} · "
               f"Beobachten {anz['beobachten']} · Nicht weiterverfolgen {anz['nicht']}"
               + (f" · {len(liste)} Treffer" if b_ else ""))
    if not liste:
        st.info(f"„{begriff}“ ist nicht in dieser Auswahl." if b_ else "Keine Werte in dieser Auswahl.")
        return
    seiten = max((len(liste) + KS_SEITE - 1) // KS_SEITE, 1)
    nr = min(max(int(st.session_state.get("ks_seite", 1)), 1), seiten)
    teil = liste[(nr - 1) * KS_SEITE:nr * KS_SEITE]
    risiko_titel = "Rendite je Risiko" if art == "etf" else "Rendite je Rückgang"
    risiko_k = "rr" if art == "etf" else "rdd"

    def zahl(v, dez=1, einheit="", vz=False, minus=False):
        if v is None:
            return '<td class="pt-num pt-leer">–</td>'
        if minus:
            return f'<td class="pt-num">−{_ks_de(v, 0)} %</td>'
        txt = (vz_zahl(v, dez) if vz else _ks_de(v, dez)) + einheit
        farbe = (" pt-up" if v >= 0 else " pt-down") if vz else ""
        return f'<td class="pt-num{farbe}">{txt}</td>'

    zeilen = []
    for e in teil:
        b = e["bewertung"]
        k = b["kennzahlen"]
        staerken, schwaechen = KS.staerken_schwaechen(b, art)
        grund = "".join(f'<span class="ks-plus">+ {_h(x)}</span>' for x in staerken) + "".join(
            f'<span class="ks-minus">– {_h(x)}</span>' for x in schwaechen)
        zeilen.append(
            f'<tr class="{"pt-zebra" if e["rang"] % 2 == 0 else ""}">'
            f'<td class="pt-num pt-seit ue-fix wk-rang">{e["rang"]}</td>'
            f'<td class="pt-wert ue-fix wk-name"><span class="pt-name">{_h(e["name"])}</span>'
            f'<span class="pt-sub">{_h(e["kennung"] or e["isin"])}</span></td>'
            f'<td class="pt-num"><span class="q-punkte {Q_KLASSE_CSS[b["einordnung"]]}">'
            f'{_ks_de(b["score"], 0)}</span></td>'
            + "".join(zahl(k["pa"][z], 1, " %", vz=True) for z in ("1J", "3J", "5J", "10J", "gesamt"))
            + zahl(k[risiko_k], 2)
            + zahl(k["dd"], minus=True) + zahl(k["vola"], 0, " %")
            + zahl(k["jahre"], 1, " J.")
            + f'<td class="ks-grund">{grund or "–"}</td></tr>')
    kopf = "".join(f'<th class="pt-num">{t}</th>' for t in
                   ("Score", "1 Jahr", "3 J. p. a.", "5 J. p. a.", "10 J. p. a.", "Gesamt p. a.", risiko_titel,
                    "Max. Rückgang", "Schwankung", "Historie"))
    st.markdown('<div class="q-legende">Score: <span class="q-prio">■</span> Hohe Analysepriorität · '
                '<span class="q-beob">■</span> Beobachtungsliste · <span class="q-nicht">■</span> '
                'Nicht weiterverfolgen</div>', unsafe_allow_html=True)
    st.markdown('<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                '<table class="pt pt-kompakt ue wk ks"><thead><tr><th class="pt-num ue-fix wk-rang">#</th>'
                f'<th class="pt-wert ue-fix wk-name">{art_wahl[:-1] if art == "etf" else "wikifolio"}</th>'
                f'{kopf}<th class="ks-grund">Begründung</th></tr></thead>'
                f'<tbody>{"".join(zeilen)}</tbody></table></div>', unsafe_allow_html=True)
    if seiten > 1:
        n1, n2, n3 = st.columns([0.5, 2, 0.5], vertical_alignment="bottom")
        n1.button("◀", key="ks_zur", on_click=_ks_seite, args=(nr - 1,), disabled=nr <= 1, width="stretch",
                  help="Vorherige Seite")

        def bereich(i):
            t = liste[(i - 1) * KS_SEITE:i * KS_SEITE]
            return f"Rang {t[0]['rang']}–{t[-1]['rang']}  ({i}/{seiten})"

        wahl = n2.selectbox("Seite", list(range(1, seiten + 1)), index=nr - 1, format_func=bereich,
                            key=f"ks_bereich_{nr}", label_visibility="collapsed")
        if wahl != nr:
            st.session_state["ks_seite"] = wahl
            st.rerun()
        n3.button("▶", key="ks_vor", on_click=_ks_seite, args=(nr + 1,), disabled=nr >= seiten,
                  width="stretch", help="Nächste Seite")

    # Teilpunkte eines Werts der aktuellen Seite
    fokus = st.selectbox("Teilpunkte ansehen", range(len(teil)), key=f"ks_fokus_{art}_{nr}",
                         format_func=lambda i: f"#{teil[i]['rang']} {teil[i]['name']}")
    e = teil[fokus if fokus is not None and fokus < len(teil) else 0]
    b = e["bewertung"]
    _ks_tabelle([("Kriterium", "l"), ("Gewicht", "r"), ("Punkte", "r"), ("", "l")],
                [[_h(t), f"{g} %", "keine Daten" if b["teile"].get(k) is None else _ks_de(b["teile"][k], 0),
                  f'<div class="ks-bahn"><div style="width:{b["teile"].get(k) or 0}%"></div></div>']
                 for k, t, g, _, _ in kriterien])
    if b["hinweise"]:
        st.caption(" · ".join(b["hinweise"]))

    pdf_schluessel = f"ks_pdf|{stand}|{signatur}"
    if st.button("📄 PDF der ganzen Liste erstellen", key="ks_pdf_knopf", width="stretch"):
        try:
            import wikifolio_pdf
            kopfzeile = (f"Stand {stand_txt} · {art_wahl} · {e_wahl} · Top {laenge} · {len(liste)} Werte"
                         + (f" · Suche „{begriff}“" if b_ else ""))
            st.session_state["ks_pdf"] = (pdf_schluessel, wikifolio_pdf.score_bericht(liste, art, kopfzeile))
        except ImportError:
            st.error("Für das PDF fehlt das Paket **reportlab** (requirements.txt).")
    fertig = st.session_state.get("ks_pdf")
    if fertig and fertig[0] == pdf_schluessel:
        st.download_button("⬇️ PDF herunterladen", data=fertig[1], mime="application/pdf",
                           file_name=f"{art}_Score_{datetime.date.today().isoformat()}.pdf",
                           key="ks_pdf_download", width="stretch")
    st.caption("Tabelle seitlich wischen für alle Kennzahlen – Rang und Name bleiben stehen. "
               "Vergangene Entwicklung ist keine Prognose.")


def ranglisten(k):
    """Frueher _render_top50 in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _render_etfs = k['_render_etfs']
    _render_klassen_score = k['_render_klassen_score']
    _render_performance = k['_render_performance']
    _render_qualitaet = k['_render_qualitaet']
    _render_qualitaet_kurs = k['_render_qualitaet_kurs']
    _render_uebersicht = k['_render_uebersicht']
    _render_wikifolios = k['_render_wikifolios']
    _zugang_pruefen = k['_zugang_pruefen']
    notify_app_error = k['notify_app_error']
    _zugang_pruefen("🏆 Watchlist Top 50")
    schritte.leiste(st, "watchlist")
    schritte.titel(st, "watchlist", 1)
    art = st.pills("Liste", ["🗂️ Gesamtübersicht", "⭐ Qualitäts-Score", "🏅 ETF- & wikifolio-Score",
                             "🧭 Qualität × Kurs", "📈 Performance", "🌍 ETFs", "🧩 Wikifolios"],
                   default="🗂️ Gesamtübersicht", key="top50_art") or "🗂️ Gesamtübersicht"
    schritte.titel(st, "watchlist", 2, art.split(" ", 1)[-1])
    if art == "🏅 ETF- & wikifolio-Score":
        try:
            _render_klassen_score()
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Klassen-Score", e)
        return
    if art == "🌍 ETFs":
        try:
            _render_etfs()
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-ETFs", e)
        return
    if art == "🧩 Wikifolios":
        try:
            _render_wikifolios()
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Wikifolios", e)
        return
    if art == "🧭 Qualität × Kurs":
        try:
            _render_qualitaet_kurs()
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-QualitaetKurs", e)
        return
    if art == "📈 Performance":
        _render_performance()
        return
    if art == "🗂️ Gesamtübersicht":
        try:
            _render_uebersicht()
        except Exception as e:
            st.error(f"⚠️ Fehler in diesem Tab: {e}")
            notify_app_error("Tab-Uebersicht", e)
        return
    try:
        _render_qualitaet()
    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Qualitaet", e)


def _trend(k, vor, jetzt):
    """Frueher _trend in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    TREND_BIS = k['TREND_BIS']
    """-> (text, art) - ▲ 3 / ▼ 2 / o / NEU; ab Platz 51 kein Vergleich ("·")"""
    if jetzt > TREND_BIS:
        return "·", "gleich"
    if vor is None:
        return "NEU", "neu"
    d = vor - jetzt
    if d > 0:
        return f"▲ {d}", "up"
    if d < 0:
        return f"▼ {-d}", "down"
    return "o", "gleich"


def _seit_text(k, seit):
    """Frueher _seit_text in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    try:
        d = datetime.date.fromisoformat(seit)
    except Exception:
        return None
    tage = (datetime.date.today() - d).days
    text = f"Vergleich mit dem Stand vom {d.strftime('%d.%m.%Y')}"
    if tage < 7:
        text += f" (erst {tage} Tag{'e' if tage != 1 else ''} Verlauf – volle Woche folgt)"
    return text


def _lade_teile(k, muster, anzahl):
    """Frueher _lade_teile in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    gh_read_streng = k['gh_read_streng']
    zeilen, felder, stand = [], None, None
    # gleichzeitig gelesen; streng: ein Lesefehler wirft und landet so NICHT 15 Min. im Cache (DATA-01)
    for d in UI.parallel_lesen(gh_read_streng, [muster.format(i) for i in range(anzahl)]):
        d = d or {}
        felder = d.get("felder") or felder
        stand = d.get("stand") or stand
        zeilen += d.get("zeilen") or []
    if not felder:
        return {}, None
    return {z[0]: dict(zip(felder, z)) for z in zeilen}, stand


def _q_alle(k):
    """Frueher _q_alle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _lade_teile = k['_lade_teile']
    github_store = k['github_store']
    try:
        return _lade_teile("state/qualitaet/alle_{}.json", 6)
    except github_store.LeseFehler:
        return {}, None


def _p_alle(k):
    """Frueher _p_alle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _lade_teile = k['_lade_teile']
    github_store = k['github_store']
    try:
        return _lade_teile("state/top50_alle_{}.json", 4)
    except github_store.LeseFehler:
        return {}, None


def _index_auswahl(k, prefix, indizes, regionen):
    """Frueher _index_auswahl in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    auswahl_kompakt = k['auswahl_kompakt']
    """Region + Index als Knoepfe. indizes = {key: {"titel","region","s"}}.
    Indizes ohne zugeordnete Aktien (Quelle beim letzten Lauf nicht lesbar)
    bleiben sichtbar – mit "(–)" und dem Grund. -> index_schluessel oder None"""
    if not any(v.get("s") for v in indizes.values()):
        st.info("Die Indexzuordnung liegt noch nicht vor – sie entsteht beim nächsten Lauf der Agenten.")
        return None
    regionen = list(regionen) + sorted({v.get("region") for v in indizes.values()
                                        if v.get("region") and v.get("region") not in regionen})
    vorhanden = [r for r in regionen if any(v.get("region") == r for v in indizes.values())]
    region = st.pills("Region", vorhanden, default=vorhanden[0], key=f"{prefix}_region") or vorhanden[0]
    keys = [k for k, v in indizes.items() if v.get("region") == region]
    keys = [k for k in keys if indizes[k].get("s")] + [k for k in keys if not indizes[k].get("s")]
    titel = [f'{indizes[k]["titel"]} ({len(indizes[k]["s"])})' if indizes[k].get("s")
             else f'{indizes[k]["titel"]} (–)' for k in keys]
    wahl = auswahl_kompakt("Index", titel, default=titel[0], key=f"{prefix}_index_{region}")
    # Die Anzahl im Namen kann sich ueber Nacht aendern - eine gespeicherte,
    # nicht mehr vorhandene Auswahl faellt dann auf den ersten Index zurueck
    key = keys[titel.index(wahl)] if wahl in titel else keys[0]
    if not indizes[key].get("s"):
        grund = indizes[key].get("hinweis") or "Quelle beim letzten Lauf nicht lesbar"
        st.info(f'Für {indizes[key]["titel"]} liegt noch keine Mitgliederliste vor ({grund}). '
                "Der nächste Lauf der Agenten versucht es erneut.")
        return None
    return key


def _listen_laenge(k, prefix, alle=False):
    """Frueher _listen_laenge in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    LISTEN_LAENGEN = k['LISTEN_LAENGEN']
    """Wie viele Plaetze die Rangliste zeigt (Standard: Top 500; alle=True bietet zusaetzlich "Alle")."""
    titel = [f"Top {n}" for n in LISTEN_LAENGEN] + (["Alle"] if alle else [])
    wahl = st.pills("Länge", titel, default="Top 500", key=f"{prefix}_laenge") or "Top 500"
    if wahl == "Alle":
        return 10 ** 6
    return LISTEN_LAENGEN[titel.index(wahl)] if wahl in titel else 500


def _auswahl_art(k, prefix):
    """Frueher _auswahl_art in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return st.pills("Auswahl nach", ["Kategorie", "Index"], default="Kategorie",
                    key=f"{prefix}_auswahl_art") or "Kategorie"


def _p_index_kat(k, idx_key, info, daten, laenge=50):
    """Frueher _p_index_kat in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _p_alle = k['_p_alle']
    gh_read_taeglich = k['gh_read_taeglich']
    """Baut aus den Gesamtdaten eine Rangliste im Format einer Kategorie
    (top/mit_daten/vergleich), damit dieselbe Anzeige genutzt werden kann."""
    alle, _ = _p_alle()
    if not alle:
        return None, None
    iv = gh_read_taeglich("state/top50_index_vergleich.json", None) or {}
    div_key = (daten.get("dividenden_zeitraum") or ["DIV"])[0]
    mitglieder = [alle[s] for s in info.get("s", []) if s in alle]
    top, mit_daten, vergleich = {}, {}, {}
    zrs = [z[0] for z in daten.get("zeitraeume") or []] + [div_key]
    for zr in zrs:
        mit = [z for z in mitglieder if z.get(zr) is not None and (zr != div_key or z[zr] > 0)]
        mit.sort(key=lambda z: (-z[zr], z["s"]))
        mit_daten[zr] = len(mit)
        v = (iv.get("listen") or {}).get(f"{idx_key}|{zr}")
        eintraege = []
        for z in mit[:laenge]:
            e = {"name": z["name"], "wkn": z["kennung"], "div": z.get(div_key),
                 "perf": z.get("1J") if zr == div_key else z[zr]}
            if v is not None:
                e["vor"] = v["vor"].get(z["s"])
            eintraege.append(e)
        top[zr] = eintraege
        if v is not None:
            vergleich[zr] = {"raus": v["raus"]}
    kat = {"titel": info.get("titel"), "top": top, "mit_daten": mit_daten, "aktiv": len(mitglieder),
           "dividende": True, "kennung": "WKN/Symbol", "vergleich": vergleich}
    return kat, (iv.get("seit") or {}).get(info.get("region"))


def _q_pct(k, x, vorzeichen=True, nachkomma=1):
    """Frueher _q_pct in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    if x is None:
        return "–"
    return f"{x:+.{nachkomma}f} %" if vorzeichen else f"{x:.{nachkomma}f} %"


def _q_x(k, x, suffix='x'):
    """Frueher _q_x in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return "–" if x is None else f"{x:.1f}{suffix}"


def _qf_pct(k, nachkomma=1, vorzeichen=True):
    """Frueher _qf_pct in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return lambda x: "–" if x is None else f"{x:+.{nachkomma}f} %" if vorzeichen else f"{x:.{nachkomma}f} %"


def _qf_zahl(k, suffix=''):
    """Frueher _qf_zahl in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return lambda x: "–" if x is None else f"{x:.1f}{suffix}"


def _qc_schwelle(k, gut, schlecht, umgekehrt=False):
    """Frueher _qc_schwelle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    def farbe(x):
        if x is None:
            return ""
        if umgekehrt:
            return "pt-up" if x <= gut else "pt-down" if x >= schlecht else ""
        return "pt-up" if x >= gut else "pt-down" if x <= schlecht else ""
    return farbe


def _qc_label(k, gut, schlecht):
    """Frueher _qc_label in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return lambda x: "pt-up" if x in gut else "pt-down" if x in schlecht else ""


def _q_tabelle(k, werte, symbole, vergleich=None, fokus='roic'):
    """Frueher _q_tabelle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BR = k['BR']
    Q_KLASSE_CSS = k['Q_KLASSE_CSS']
    Q_SPALTEN = k['Q_SPALTEN']
    TREND_FARBE = k['TREND_FARBE']
    _trend = k['_trend']
    html = k['html']
    """HTML-Tabelle. Am Desktop alle Kennzahlen (seitlich scrollbar), auf
    dem iPhone nur Rang, Trend, Name, die gewaehlte Kennzahl und Punkte -
    so bleiben alle Werte untereinander direkt vergleichbar."""
    mit_trend = vergleich is not None
    kopf = '<th class="pt-num">#</th>' + ('<th class="pt-num">7&nbsp;T.</th>' if mit_trend else "")
    kopf += '<th class="pt-wert">Unternehmen</th>'
    for key, titel, _, _ in Q_SPALTEN:
        hl = " q-fokus-hl" if key == fokus else ""
        kopf += f'<th class="pt-num{hl}" data-spalte="q_{key}">{titel}</th>'
    kopf += '<th class="pt-num">Punkte</th>'
    zeilen = ""
    for rang, sym in enumerate(symbole, 1):
        e = werte.get(sym)
        if not e:
            continue
        z = f'<td class="pt-num pt-seit">{rang}</td>'
        if mit_trend:
            t, art = _trend(vergleich["vor"].get(sym), rang)
            z += f'<td class="pt-num" style="color:{TREND_FARBE[art]};font-weight:700">{t}</td>'
        unter = " · ".join(x for x in (sym, BR.kategorie_text(e.get("br"))) if x)
        z += (f'<td class="pt-wert"><span class="pt-name">{html.escape(str(e["name"]))}</span>'
              f'<span class="pt-sub">{html.escape(unter)}</span></td>')
        for key, _, fmt, farbe in Q_SPALTEN:
            x = e.get(key)
            hl = " q-fokus-hl" if key == fokus else ""
            z += (f'<td class="pt-num pt-stark {farbe(x)}{hl}" data-spalte="q_{key}">'
                  f'{html.escape(fmt(x))}</td>')
        z += (f'<td class="pt-num q-punkte {Q_KLASSE_CSS.get(e.get("klasse"), "")}">'
              f'{e.get("gesamt", "–")}</td>')
        zeilen += f'<tr class="{"pt-zebra" if rang % 2 == 0 else ""}">{z}</tr>'
    # Nur die gewaehlte Kennzahl auf schmalen Bildschirmen einblenden
    # (die allgemeine Regel blendet dort alle data-spalte-Zellen aus)
    stil = (f'<style>@media (max-width: 700px) {{ .pt.qt td[data-spalte="q_{fokus}"], '
            f'.pt.qt th[data-spalte="q_{fokus}"] {{ display: table-cell; }} }}</style>')
    st.markdown(stil + f'<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt qt"><thead><tr>{kopf}</tr></thead>'
                f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    st.markdown('<div class="q-legende">Punkte: <span class="q-prio">■</span> Hohe Analysepriorität · '
                '<span class="q-beob">■</span> Beobachtungsliste · <span class="q-nicht">■</span> '
                'Nicht weiterverfolgen · * = aus Kennzahlen angenähert</div>', unsafe_allow_html=True)


def _q_mitglieder(k, kat_key, alle):
    """Frueher _q_mitglieder in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    gh_read_taeglich = k['gh_read_taeglich']
    """Alle Aktien der gewaehlten Kategorie bzw. des Index (fuer den Sektor-Filter)."""
    if not alle:
        return []
    if kat_key == "alle":
        return list(alle)
    gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
    if kat_key.startswith("i:"):
        g = (gruppen.get("indizes") or {}).get(kat_key[2:]) or {}
    else:
        g = (gruppen.get("kategorien") or {}).get(kat_key) or {}
    return [s_ for s_ in g.get("s") or [] if s_ in alle]


def _q_dividenden_tabelle(k, alle, mitglieder):
    """Frueher _q_dividenden_tabelle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    DV = k['DV']
    _de_zahl = k['_de_zahl']
    html = k['html']
    """Je Dividenden-Kategorie: Anzahl, Ø Punkte, davon nachhaltig, bester Wert."""
    zeilen = ""
    for i, z in enumerate(DV.uebersicht([alle[s_] for s_ in mitglieder]), 1):
        b = z["bester"]
        zeilen += (f'<tr class="{"pt-zebra" if i % 2 == 0 else ""}">'
                   f'<td class="pt-wert"><span class="pt-name">{DV.ICON[z["schluessel"]]} '
                   f'{html.escape(z["titel"])}</span></td>'
                   f'<td class="pt-num">{z["anzahl"]}</td><td class="pt-num">{_de_zahl(z["schnitt_punkte"], 0)}</td>'
                   f'<td class="pt-num">{z["nachhaltig"] if z["schluessel"] != "keine" else "–"}</td>'
                   f'<td class="pt-wert"><span class="pt-name">{html.escape(str(b["name"]))}</span>'
                   f'<span class="pt-sub">{b.get("gesamt")} Punkte · Dividende '
                   f'{FMT.pct(b.get("div") or 0, 1)}</span></td></tr>')
    st.markdown('<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                '<table class="pt"><thead><tr><th class="pt-wert">Dividende</th><th class="pt-num">Aktien</th>'
                '<th class="pt-num">Ø Punkte</th><th class="pt-num">nachhaltig</th>'
                '<th class="pt-wert">Bester Wert</th></tr></thead>'
                f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    st.caption("Dividendenrendite und Ausschüttungsquote vom Qualitäts-Agenten (Yahoo Finance). „nachhaltig“ = "
               "Ausschüttungsquote höchstens 80 % des Gewinns. Filter und Sortierung oben unter „🔎 Filter“.")


def _q_sektoren_tabelle(k, alle, mitglieder):
    """Frueher _q_sektoren_tabelle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BR = k['BR']
    _de_zahl = k['_de_zahl']
    html = k['html']
    """Je Sektor: Anzahl, Ø Punkte, Hohe Prioritaet, bester Wert."""
    je = {}
    for s_ in mitglieder:
        e = alle[s_]
        je.setdefault(BR.sektor(e.get("br")), []).append(e)
    zeilen = ""
    for i, (sek, liste) in enumerate(sorted(je.items(), key=lambda kv: -len(kv[1])), 1):
        bester = max(liste, key=lambda e: e.get("gesamt") or 0)
        schnitt = sum(e.get("gesamt") or 0 for e in liste) / len(liste)
        prio = sum(1 for e in liste if e.get("klasse") == "prio")
        branchen_n = len({BR.branche_de(e.get("br")) for e in liste})
        zeilen += (f'<tr class="{"pt-zebra" if i % 2 == 0 else ""}">'
                   f'<td class="pt-wert"><span class="pt-name">{BR.SEKTOR_ICON.get(sek, "")} {html.escape(sek)}</span>'
                   f'<span class="pt-sub">{"ohne Branchenangabe" if sek == "Sonstige" else f"{branchen_n} Branche" + ("n" if branchen_n != 1 else "")}</span></td>'
                   f'<td class="pt-num">{len(liste)}</td><td class="pt-num">{_de_zahl(schnitt, 0)}</td>'
                   f'<td class="pt-num">{prio}</td>'
                   f'<td class="pt-wert"><span class="pt-name">{html.escape(str(bester["name"]))}</span>'
                   f'<span class="pt-sub">{bester.get("gesamt")} Punkte · '
                   f'{html.escape(BR.branche_de(bester.get("br")))}</span></td></tr>')
    st.markdown('<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                '<table class="pt"><thead><tr><th class="pt-wert">Sektor</th><th class="pt-num">Aktien</th>'
                '<th class="pt-num">Ø Punkte</th><th class="pt-num">Priorität</th>'
                '<th class="pt-wert">Bester Wert</th></tr></thead>'
                f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)
    st.caption("Sektor und Branche aus der Yahoo-Branchenangabe (11 Sektoren). „Sonstige“ = keine "
               "Branchenangabe. Filter oben: „Firmen-Kategorie“.")


def _div_rhythmen(k):
    """Frueher _div_rhythmen in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    gh_read_taeglich = k['gh_read_taeglich']
    """{Yahoo-Symbol: Auszahlungsrhythmus} aus dem Top-50-Agenten (gleiche Symbole wie der Qualitaets-Agent)."""
    d = gh_read_taeglich("state/top50_dividenden.json", None) or {}
    return {s_: v[1] for s_, v in (d.get("werte") or {}).items() if isinstance(v, list) and len(v) > 1 and v[1]}


def _qk_daten(k):
    """Frueher _qk_daten in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _q_alle = k['_q_alle']
    gh_read_taeglich = k['gh_read_taeglich']
    """Gesamtdaten aller bewerteten Aktien + Kategorien/Indizes."""
    alle, _ = _q_alle()
    gruppen = gh_read_taeglich("state/qualitaet/gruppen.json", None) or {}
    if not alle or not gruppen.get("kategorien"):
        return None
    return {"alle": alle, "gruppen": gruppen}


def _qk_zeilen(k, m, kat_key):
    """Frueher _qk_zeilen in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    if kat_key == "alle":
        return list(m["alle"].values())
    return [m["alle"][s_] for s_ in m["gruppen"]["kategorien"].get(kat_key, {}).get("s", []) if s_ in m["alle"]]


def _qk_einteilen(k, zeilen, zr_key):
    """Frueher _qk_einteilen in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    QK_FELDER = k['QK_FELDER']
    QK_QUAL_GRENZE = k['QK_QUAL_GRENZE']
    """-> ({feld: [zeilen sortiert]}, median) fuer Zeilen mit Kursdaten"""
    mit = [z for z in zeilen if z.get(zr_key) is not None and z.get("q_ant") is not None]
    if not mit:
        return {f: [] for f, _, _ in QK_FELDER}, None
    werte = sorted(z[zr_key] for z in mit)
    median = werte[len(werte) // 2]
    felder = {f: [] for f, _, _ in QK_FELDER}
    for z in mit:
        q_hoch = z["q_ant"] >= QK_QUAL_GRENZE
        k_stark = z[zr_key] >= median
        felder[("gut_" if q_hoch else "schwach_") + ("stark" if k_stark else "schwach")].append(z)
    felder["gut_schwach"].sort(key=lambda z: (-z["gesamt"], z[zr_key]))
    felder["gut_stark"].sort(key=lambda z: -z["gesamt"])
    felder["schwach_stark"].sort(key=lambda z: -z[zr_key])
    felder["schwach_schwach"].sort(key=lambda z: -z["gesamt"])
    return felder, median


def _qk_tabelle(k, zeilen, zr_key, zr_titel):
    """Frueher _qk_tabelle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    Q_KLASSE_CSS = k['Q_KLASSE_CSS']
    html = k['html']
    vz_zahl = k['vz_zahl']
    kopf = ('<th class="pt-num">#</th><th class="pt-wert">Unternehmen</th>'
            f'<th class="pt-num">Kurs {html.escape(zr_titel)}</th><th class="pt-num">FCF-<br>Rendite</th>'
            '<th class="pt-num">Punkte</th>')
    z_html = ""
    for platz, z in enumerate(zeilen, 1):
        perf = z[zr_key]
        bew = z.get("bew") or "–"
        mos = z.get("mos")
        unter = f'{z["s"]} · Qualität {z["q_ant"]:.0f} % · Bewertung {bew}'
        if mos is not None and mos > -200:
            unter += f" · MoS {mos:+.0f} %"
        unter = unter.replace(" %", "\u00a0%")          # Zahl und % nie getrennt umbrechen
        fy = z.get("fcfy")
        z_html += (
            f'<tr class="{"pt-zebra" if platz % 2 == 0 else ""}">'
            f'<td class="pt-num pt-seit">{platz}</td>'
            f'<td class="pt-wert"><span class="pt-name">{html.escape(z["name"])}</span>'
            f'<span class="pt-sub">{html.escape(unter)}</span></td>'
            f'<td class="pt-num pt-stark {"pt-up" if perf >= 0 else "pt-down"}">{vz_zahl(perf, 1)} %</td>'
            f'<td class="pt-num pt-stark {"pt-up" if (fy or 0) >= 5 else "pt-down" if fy is not None and fy < 2 else ""}">'
            f'{"–" if fy is None else f"{FMT.pct(fy, 1)}"}</td>'
            f'<td class="pt-num q-punkte {Q_KLASSE_CSS.get(z["klasse"], "")}">{z["gesamt"]}</td></tr>')
    st.markdown(f'<div class="pt-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt"><thead><tr>{kopf}</tr></thead>'
                f'<tbody>{z_html}</tbody></table></div>', unsafe_allow_html=True)


def _qk_diagramm(k, zeilen, zr_key, zr_titel, median):
    """Frueher _qk_diagramm in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    QK_QUAL_GRENZE = k['QK_QUAL_GRENZE']
    _h = k['_h']
    vz_zahl = k['vz_zahl']
    mit = [z for z in zeilen if z.get(zr_key) is not None and z.get("q_ant") is not None]
    if not mit:
        return
    # Ausreisser (z.B. +900 %) stauchen sonst alles andere zusammen
    werte = sorted(z[zr_key] for z in mit)
    oben = werte[int(len(werte) * 0.98)] if len(werte) > 20 else werte[-1]
    unten = werte[int(len(werte) * 0.02)] if len(werte) > 20 else werte[0]
    fig = go.Figure()
    for kl, titel_kl, farbe in (("nicht", "Nicht weiterverfolgen", "#6B7280"),
                                ("beobachten", "Beobachtungsliste", "#F5B942"),
                                ("prio", "Hohe Analysepriorität", "#34D399")):
        pts = [z for z in mit if z["klasse"] == kl]
        if not pts:
            continue
        fig.add_trace(go.Scattergl(
            x=[min(max(z[zr_key], unten), oben) for z in pts], y=[z["q_ant"] for z in pts],
            mode="markers", name=titel_kl,
            marker=dict(color=farbe, size=6 if kl != "nicht" else 5, opacity=0.85 if kl != "nicht" else 0.45),
            text=[f'{_h(z["name"])} ({_h(z["s"])})<br>Kurs {zr_titel}: {vz_zahl(z[zr_key], 1)} %<br>'
                  f'Qualität {z["q_ant"]:.0f} % · {z["gesamt"]} Punkte' for z in pts],
            hovertemplate="%{text}<extra></extra>"))
    for x0, y0, text in ((unten, 99, "Qualität hoch · Kurs schwach"), (oben, 99, "Qualität hoch · Kurs stark"),
                         (unten, 1, "Qualität niedrig · Kurs schwach"), (oben, 1, "Qualität niedrig · Kurs stark")):
        fig.add_annotation(x=x0, y=y0, text=text, showarrow=False, font=dict(size=10, color="#71717A"),
                           xanchor="left" if x0 == unten else "right", yanchor="top" if y0 > 50 else "bottom")
    fig.add_vline(x=median, line=dict(color="#A1A1AA", width=1, dash="dot"))
    fig.add_hline(y=QK_QUAL_GRENZE, line=dict(color="#A1A1AA", width=1, dash="dot"))
    fig.update_layout(
        paper_bgcolor="#000000", plot_bgcolor="#000000", height=380, margin=dict(l=10, r=10, t=10, b=40),
        showlegend=True, legend=dict(orientation="h", y=-0.14, x=0, font=dict(color="#A1A1AA", size=10)),
        xaxis=dict(title=dict(text=f"Kursentwicklung {zr_titel} (EUR)", font=dict(color="#A1A1AA", size=12)),
                   ticksuffix=" %", showgrid=True, gridcolor="#1A1A1A", zeroline=True, zerolinecolor="#333",
                   tickfont=dict(color="#A1A1AA")),
        yaxis=dict(title=dict(text="Qualität (%)", font=dict(color="#A1A1AA", size=12)), range=[0, 100],
                   showgrid=True, gridcolor="#1A1A1A", tickfont=dict(color="#A1A1AA")),
        dragmode=False)
    st.plotly_chart(UI.chart_stil(fig), width="stretch", key="qk_diagramm", config={"displayModeBar": False})


def _ue_z(k, text, farbe=None, fett=False):
    """Frueher _ue_z in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return (str(text), farbe, fett)


def _ue_css_farbe(k, klasse):
    """Frueher _ue_css_farbe in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return {"pt-up": "up", "pt-down": "down"}.get(klasse)


def _ue_trend(k, vor, platz):
    """Frueher _ue_trend in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _trend = k['_trend']
    _ue_z = k['_ue_z']
    t, art = _trend(vor, platz)
    return _ue_z(t, {"up": "up", "down": "down", "neu": "up", "gleich": "grau"}[art], art != "gleich")


def _ue_qualitaets_tabelle(k, werte, symbole, vergleich, umfang):
    """Frueher _ue_qualitaets_tabelle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    BR = k['BR']
    Q_KLASSEN_KURZ = k['Q_KLASSEN_KURZ']
    Q_SPALTEN = k['Q_SPALTEN']
    _ue_css_farbe = k['_ue_css_farbe']
    _ue_trend = k['_ue_trend']
    _ue_z = k['_ue_z']
    spalten = [("#", 3, "r"), ("7 T.", 4, "r"), ("Unternehmen", 17, "l"), ("Branche", 11, "l"),
               ("Punkte", 5, "r"), ("Einordnung", 7, "l")]
    spalten[3] = ("Branche", 10, "l")
    spalten += [(titel, 7 if key == "nde" else 6, "r") for key, titel, _, _ in Q_SPALTEN]
    zeilen = []
    for platz, sym in enumerate(symbole[:umfang], 1):
        e = werte.get(sym)
        if not e:
            continue
        kl = e.get("klasse")
        z = [_ue_z(platz, fett=True),
             _ue_trend((vergleich or {}).get("vor", {}).get(sym), platz) if vergleich is not None else _ue_z("–", "grau"),
             _ue_z(f'{e["name"]} ({sym})', fett=True), _ue_z(BR.kategorie_text(e.get("br")) if e.get("br") else "–"),
             _ue_z(e.get("gesamt", "–"), {"prio": "prio", "beobachten": "beob"}.get(kl, "nicht"), True),
             _ue_z(Q_KLASSEN_KURZ.get(kl, "–"), {"prio": "prio", "beobachten": "beob"}.get(kl, "nicht"))]
        for key, _, fmt, farbe in Q_SPALTEN:
            x = e.get(key)
            z.append(_ue_z(fmt(x), _ue_css_farbe(farbe(x))))
        zeilen.append(z)
    return spalten, zeilen


def _ue_html(k, abschnitte):
    """Frueher _ue_html in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    UE_FARBEN_SCHIRM = k['UE_FARBEN_SCHIRM']
    html = k['html']
    """Bildschirm: breite Tabellen scrollen seitlich, die Namensspalte bleibt stehen."""
    for a in abschnitte:
        st.markdown(f'<div class="abschnitt">{html.escape(a["titel"])}</div>', unsafe_allow_html=True)
        if a.get("text"):
            st.caption(a["text"])
        if not a["zeilen"]:
            st.caption("– keine Einträge –")
            continue
        namensspalte = next((i for i, (n, _, _) in enumerate(a["spalten"])
                             if n in ("Unternehmen", "Kategorie")), None)
        kopf = "".join(
            f'<th class="{"pt-wert" if aus == "l" else "pt-num"}{" ue-fix" if i == namensspalte else ""}">'
            f'{html.escape(n).replace("7 T.", "7&nbsp;T.")}</th>' for i, (n, _, aus) in enumerate(a["spalten"]))
        zeilen = ""
        for r, zeile in enumerate(a["zeilen"]):
            zellen = ""
            for i, ((text, farbe, fett), (_, _, aus)) in enumerate(zip(zeile, a["spalten"])):
                stil = f"color:{UE_FARBEN_SCHIRM[farbe]};" if farbe else ""
                stil += "font-weight:700;" if fett else ""
                inhalt = "<br>".join(html.escape(t) for t in text.split("\n")).replace(
                    "\t", '&nbsp;&nbsp;<span style="font-weight:700">') + ("</span>" if "\t" in text else "")
                zellen += (f'<td class="{"pt-wert" if aus == "l" else "pt-num"}'
                           f'{" ue-fix" if i == namensspalte else ""}" style="{stil}">{inhalt}</td>')
            zeilen += f'<tr class="{"pt-zebra" if r % 2 else ""}">{zellen}</tr>'
        st.markdown(f'<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)"><table class="pt pt-kompakt ue"><thead><tr>{kopf}</tr></thead>'
                    f'<tbody>{zeilen}</tbody></table></div>', unsafe_allow_html=True)


def _render_uebersicht(k):
    """Frueher _render_uebersicht in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    UE_TEILE = k['UE_TEILE']
    _ue_abschnitte = k['_ue_abschnitte']
    _ue_html = k['_ue_html']
    _ue_pdf = k['_ue_pdf']
    gh_read_taeglich = k['gh_read_taeglich']
    dq = gh_read_taeglich("state/qualitaet.json", None)
    dp = gh_read_taeglich("state/top50.json", None)
    if not dq and not dp:
        st.info("Noch keine Daten vorhanden – die Übersicht erscheint nach dem ersten Lauf der Agenten.")
        return
    # Umfang und Inhalt in einem Klappbereich (UX 10/2026: am Handy standen drei Auswahlgruppen mit ~500 px
    # vor dem ersten Inhalt) - die Beschriftung zeigt die aktuelle Wahl
    _u = st.session_state.get("ue_umfang") or "Top 10"
    _t = st.session_state.get("ue_teile", UE_TEILE)
    with st.expander(f"⚙️ Umfang & Inhalt · {_u} · {len(_t or [])} von {len(UE_TEILE)} Bereichen",
                     key="ue_einstellungen"):
        umfang_txt = st.pills("Umfang je Liste", ["Top 10", "Top 25", "Top 50"], default="Top 10",
                              key="ue_umfang") or "Top 10"
        teile = st.pills("Inhalt", UE_TEILE, default=UE_TEILE, selection_mode="multi", key="ue_teile") or []
    umfang = int(umfang_txt.split()[1])
    try:
        stand = datetime.datetime.fromisoformat((dq or dp)["stand"]).strftime("%d.%m.%Y, %H:%M Uhr")
    except Exception:
        stand = "–"
    stand_text = f"Stand {stand}"
    abschnitte = _ue_abschnitte(dq, dp, umfang, teile)
    if not abschnitte:
        st.info("Bitte mindestens einen Inhalt auswählen.")
        return

    # PDF erst auf Knopfdruck erzeugen - das Bauen kostet einige Sekunden
    schluessel = f"ue_pdf|{stand}|{umfang}|{'/'.join(teile)}"
    if st.button("📄 PDF zum Drucken erstellen", key="ue_pdf_knopf", width="stretch"):
        try:
            st.session_state["ue_pdf"] = (schluessel, _ue_pdf(abschnitte, stand_text))
        except ImportError:
            st.error("Für das PDF fehlt das Paket **reportlab**: bitte die Zeile `reportlab` in die "
                     "requirements.txt des Repos aufnehmen – Streamlit installiert es dann automatisch.")
    fertig = st.session_state.get("ue_pdf")
    if fertig and fertig[0] == schluessel:
        st.download_button("⬇️ PDF herunterladen", data=fertig[1], mime="application/pdf",
                           file_name=f"Ranglisten_Uebersicht_{datetime.date.today().isoformat()}.pdf",
                           key="ue_pdf_download", width="stretch")
    st.caption(f"{stand_text} · A4 quer · breite Tabellen lassen sich hier seitlich wischen, "
               "die Namensspalte bleibt stehen.")
    _ue_html(abschnitte)


def _wk_seite(k, nr, p='wk'):
    """Frueher _wk_seite in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    st.session_state[f"{p}_seite"] = nr


def _render_wikifolios_alle(k, teile, stand):
    """Frueher _render_wikifolios_alle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _render_liste_alle = k['_render_liste_alle']
    wikifolio_alle = k['wikifolio_alle']
    _render_liste_alle("wikifolio", wikifolio_alle(datetime.date.today().isoformat()), stand)


def _render_etfs(k):
    """Frueher _render_etfs in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _render_liste_alle = k['_render_liste_alle']
    etf_alle = k['etf_alle']
    gh_read_taeglich = k['gh_read_taeglich']
    ranglisten_stand = k['ranglisten_stand']
    """Alle ETFs mit allen Kennzahlen, Merkmal-Filtern und eigener Bewertung - bis der Watchlist-Agent die
    ETF-Kennzahlen geschrieben hat, ein Hinweis auf den ETF-Score."""
    werte = etf_alle(datetime.date.today().isoformat())
    if not werte:
        st.info("Die erweiterte ETF-Übersicht entsteht beim nächsten Lauf des Watchlist-Agenten (täglich "
                "07:30 Uhr). Bis dahin: Bewertung der ETFs unter „🏅 ETF- & wikifolio-Score“.")
        return
    daten = gh_read_taeglich("state/top50.json", None) or {}
    _render_liste_alle("etf", werte, ranglisten_stand(daten) if daten else "–")


def _ks_de(k, x, dez=1):
    """Frueher _ks_de in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ks_seite(k, nr):
    """Frueher _ks_seite in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    st.session_state["ks_seite"] = nr


def _ks_rangliste(k, art):
    """Frueher _ks_rangliste in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    gh_read_taeglich = k['gh_read_taeglich']
    """ETF-/wikifolio-Score aus dem Top-500-Katalog - je Sitzung und Datenstand gemerkt."""
    import klassen_score as KS
    teile = [d or {} for d in UI.parallel_lesen(gh_read_taeglich, [f"state/planer/katalog_gross_{i}.json"
                                                                   for i in range(4)], {})]
    stand = next((t.get("stand") for t in teile if t.get("stand")), "")
    gemerkt = st.session_state.get(f"_ks_{art}")
    if gemerkt and gemerkt[0] == stand:
        return stand, gemerkt[1]
    liste = KS.rangliste(teile, art)
    st.session_state[f"_ks_{art}"] = (stand, liste)
    return stand, liste


def _ks_tabelle(k, spalten, zeilen):
    """Frueher _ks_tabelle in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    kopf = "".join(f'<th class="{"pt-num" if a == "r" else "pt-wert"}">{t}</th>' for t, a in spalten)
    rumpf = "".join("<tr>" + "".join(f'<td class="{"pt-num" if a == "r" else ""}">{z}</td>'
                                     for z, (_, a) in zip(r, spalten)) + "</tr>" for r in zeilen)
    st.markdown(f'<div class="ue-wrap" tabindex="0" role="region" aria-label="Tabelle (seitlich scrollbar)">'
                f'<table class="pt pt-kompakt ks-mini"><thead><tr>{kopf}</tr></thead>'
                f'<tbody>{rumpf}</tbody></table></div>', unsafe_allow_html=True)
