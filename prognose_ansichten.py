"""Zukunfts-Prognose und Szenario-Simulator (aus app.render_dashboard ausgelagert, Audit ARCH-01). Die Rumpfe sind
unveraendert; was sie bisher aus dem Funktionskontext von render_dashboard lasen (Depotdaten, Kursreihen, gemeinsame
Hilfsfunktionen), bekommen sie ausdruecklich als Woerterbuch k uebergeben. app.py ruft sie ueber gleichnamige Huellen
auf (die st.fragment-Dekoratoren bleiben dort).
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


def prognose_basis_verwalten(k):
    """Frueher _prognose_basis_verwalten in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    PROG_BASIS = k['PROG_BASIS']
    _h = k['_h']
    aendere_prognose_basis = k['aendere_prognose_basis']
    lade_prognose_basis = k['lade_prognose_basis']
    prognose_optionen = k['prognose_optionen']
    suche_instrument = k['suche_instrument']
    time = k['time']
    top500_optionen_bei_bedarf = k['top500_optionen_bei_bedarf']
    """Eigene Prognose-Basis: Werte aus der Top-500-Liste uebernehmen und wieder entfernen."""
    liste = lade_prognose_basis()
    with st.expander(f"⭐ Prognose-Basis verwalten ({len(liste)} eigene Werte)",
                     expanded=not prognose_optionen):
        st.caption("Werte aus der Top-500-Liste übernehmen – sie erscheinen in „Prognose Basis auswählen“ "
                   "(symbolisch 10.000 €, angelegt ab heute). Deine Depot-Positionen sind immer dabei. "
                   f"Höchstens {PROG_BASIS.MAX_EINTRAEGE} eigene Werte.")
        optionen = top500_optionen_bei_bedarf("prog_top500")
        if optionen is not None:
            optionen = [w for w in optionen if not PROG_BASIS.enthalten(liste, w)]

        def _beschriftung(i):
            w = optionen[i]
            return " · ".join(x for x in (w["name"], PROG_BASIS.ARTEN[w["art"]], w["wkn"] or w["isin"]) if x)

        if optionen is not None:
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            wahl = c1.selectbox(f"Aus der Top-500-Liste ({len(optionen)} Werte)", range(len(optionen)), index=None,
                                format_func=_beschriftung, placeholder="Name, WKN oder ISIN eintippen …",
                                key="prog_basis_wahl")
            if c2.button("➕ Hinzufügen", key="prog_basis_add", disabled=wahl is None, type="primary",
                         width="stretch"):
                w = dict(optionen[wahl])
                if not w["instrument_id"]:              # Kurs-ID nicht in den Top-500-Daten: exakte Suche
                    import investment_scanner_pro_engine as PRO
                    t, art = PRO.treffer_waehlen(w, suche_instrument(w["isin"] or w["wkn"] or w["name"]) or [])
                    w["instrument_id"] = int(t["instrument_id"]) if t and art == "exakt" else None
                if not w["instrument_id"]:
                    st.error(f"Für „{w['name']}“ wurde keine Kursquelle gefunden – nicht hinzugefügt.")
                elif aendere_prognose_basis(
                        lambda l: PROG_BASIS.hinzufuegen(l, PROG_BASIS.eintrag(w, time.time())),
                        "prognose-basis hinzugefuegt [skip ci]"):
                    st.session_state.pop("prog_basis_wahl", None)
                    st.rerun()
                else:
                    st.error("Nicht gespeichert – schon in der Liste, Liste voll oder Speicher gerade nicht "
                             "erreichbar.")
        for e in liste:
            z1, z2 = st.columns([5, 1], vertical_alignment="center")
            z1.markdown(f"**{_h(e.get('name', ''))}** · {_h(e.get('wkn') or e.get('isin') or '')}")
            if z2.button("🗑️ Entfernen", key=f"prog_basis_weg_{e.get('id')}", width="stretch"):
                if aendere_prognose_basis(lambda l, _id=e.get("id"): PROG_BASIS.entfernen(l, _id),
                                          "prognose-basis entfernt [skip ci]"):
                    st.rerun()
                else:
                    st.error("Entfernen fehlgeschlagen (Speicher gerade nicht erreichbar).")


def zukunfts_prognose(k):
    """Frueher _render_forecast in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _prognose_basis_verwalten = k['_prognose_basis_verwalten']
    _startauswahl = k['_startauswahl']
    _startwert = k['_startwert']
    _zugang_pruefen = k['_zugang_pruefen']
    fmt_vz = k['fmt_vz']
    heute_date = k['heute_date']
    notify_app_error = k['notify_app_error']
    now_berlin = k['now_berlin']
    prognose_optionen = k['prognose_optionen']
    simuliere_bandbreite = k['simuliere_bandbreite']
    _zugang_pruefen("🔮 Zukunfts-Prognose")
    schritte.leiste(st, "prognose")
    schritte.titel(st, "prognose", 1)
    _prognose_basis_verwalten()
    if not prognose_optionen:
        # normaler Benutzer ohne eigene Positionen/Prognose-Werte
        st.info("🔮 Noch kein eigenes Depot – lege im 🏠 Depot deine erste Position an "
                "oder übernimm oben Werte aus der Top-500-Liste, dann erscheint hier die Prognose.")
        return
    try:
        # Ab der zweiten Position eine Auswahl anbieten - bei nur einer
        # Position (Standardfall) waere ein Dropdown mit einem einzigen
        # Eintrag nur ueberfluessiger Klick.
        if len(prognose_optionen) > 1:
            # Gleiches Muster wie bei "Ansicht wählen": eigene
            # .abschnitt-Ueberschrift, natives Label per CSS (nicht
            # per Streamlit-"collapsed") ausgeblendet - siehe
            # Kommentar dort. "help" bewusst entfernt: der kleine
            # weisse Kreis daneben wirkte wie ein Darstellungsfehler.
            st.markdown(
                '<div class="abschnitt abschnitt-marker-prognose">Prognose Basis auswählen:</div>',
                unsafe_allow_html=True,
            )
            namen = [o["name"] for o in prognose_optionen]
            gewaehlter_name = st.selectbox(
                "Prognose Basis auswählen:", namen, **_startauswahl("prognose_wert_wahl", namen),
                key="prognose_wert_wahl",
            )
            opt = next(o for o in prognose_optionen if o["name"] == gewaehlter_name)
        else:
            opt = prognose_optionen[0]

        opt_startkapital = opt["startkapital"]
        opt_aktueller_wert = opt["aktueller_wert"]
        opt_kaufdatum = opt["kaufdatum"]
        opt_sparrate = opt["sparrate"]
        opt_entnahme = opt["entnahme"]                         # Rate je Monat
        opt_entnommen = float(opt.get("entnommen_bisher") or 0.0)  # bisher seit Kauf
        # Audit DEP-01: Gewinn gegen den Einstand (Startkapital + eingezahlte Sparraten)
        opt_einstand = float(opt.get("einstand", opt_startkapital))
        # Audit A-12: aktueller_wert ist der Wert NACH den echten Entnahmen; das bereits
        # ausgezahlte Geld gehoert zum Ergebnis.
        opt_gewinn = opt_aktueller_wert + opt_entnommen - opt_einstand

        _default_key = f"prognose_rate_{opt['name']}"
        schritte.titel(st, "prognose", 2)
        opt_cagr_pa = st.number_input(
            "Angenommene Rendite p.a. (%) für diese Prognose",
            min_value=-99.0, max_value=100000.0, step=0.5,
            **_startwert(_default_key, round(opt["cagr_pa"], 2)), key=_default_key,
            help="Vorbelegt mit der aus der Kurshistorie ermittelten Rate. "
                 "Frei überschreibbar, um andere Annahmen durchzurechnen.",
        )
        opt_zins_mo = (1 + (opt_cagr_pa / 100.0)) ** (1 / 12) - 1

        _opt_rueckfall = opt.get("cagr_rueckfall_hinweis")
        if _opt_rueckfall:
            # Produkt-Historie zu kurz -> Rate aus dem eigenen Kauf (Nutzerentscheid DEP-08)
            st.caption(f"⚠️ Vorbelegte Rate {opt['cagr_pa']:+.2f} % p.a.: {_opt_rueckfall}.")
        elif opt.get("cagr_details"):
            with st.expander("Wie wurde die vorbelegte Rate ermittelt?", expanded=False):
                st.caption("Grundlage ist ein **Trend über die gesamte Historie** (Regression durch alle Kurspunkte) plus Zeitfenster **ab 6 Monaten**, daraus der Median. Kürzere Fenster bleiben bewusst außen vor: ein Monat hochgerechnet multipliziert das Zufallsrauschen mit zwölf. Bei kurzer Historie wird das Ergebnis zusätzlich Richtung einer konservativen Marktrendite gedämpft, weil sich aus wenigen Monaten keine verlässliche Jahresrate ablesen lässt.")
                for _label, _wert in opt["cagr_details"]:
                    st.write(f"- {_label}: **{_wert:+.2f}% p.a.**")
                st.write(f"→ Verwendet: **{opt['cagr_pa']:+.2f}% p.a.**")

        sparrate_hinweis = f" Zusätzlich wird eine monatliche Sparrate von **{fmt(opt_sparrate, 2)}** eingerechnet." if opt_sparrate > 0 else ""
        if opt.get("symbolisch"):
            _cagr_seit = opt.get("cagr_seit")
            _seit_hinweis = (
                f" Kursdaten liegen seit {_cagr_seit.strftime('%d.%m.%Y')} vor."
                if _cagr_seit else ""
            )
            st.caption(
                f"Dieser Wert ist nur eine Beobachtung, kein echtes Investment. "
                f"Die Rechnung unterstellt ein **symbolisches** Startkapital von "
                f"{fmt(opt_startkapital, 0)}, das **heute** ({opt_kaufdatum.strftime('%d.%m.%Y')}) "
                f"angelegt würde - keine reale Position.{_seit_hinweis}{sparrate_hinweis}"
            )
        elif sparrate_hinweis:
            st.caption(sparrate_hinweis.strip())

        # Die Prognose startet immer HEUTE mit dem heutigen Depotwert: Gewinn und Entnahmen
        # zaehlen ab heute (der bisherige Gewinn steht darunter als Hinweis).
        forecast_data = [
            {"Jahr": "Start (heute)", "Datum": heute_date.strftime("%d.%m.%Y"), "Gewinn ab heute": fmt_vz(0.0),
             "Depotwert": fmt(opt_aktueller_wert, 2), "Kumulierte Entnahme": fmt(0.0, 2)}
        ]
        if not opt.get("symbolisch"):
            st.caption(f"Bisher seit Kauf ({opt_kaufdatum.strftime('%d.%m.%Y')}): Gewinn {fmt_vz(opt_gewinn)}"
                       + (f", entnommen {fmt(opt_entnommen, 2)}" if opt_entnommen else "")
                       + " – die Prognose unten rechnet ab heute.")

        # Fortschreibung mit ECHTEN Entnahmen (Audit A-12): jede Entnahme verlaesst das Depot
        # und verzinst sich nicht weiter; Sparraten erhoehen den Einsatz (DEP-01).
        # Gewinn ab heute = Depotwert + ab heute Ausgezahltes - (heutiger Wert + Sparraten).
        sim_w_prog, sim_e_prog = opt_aktueller_wert, 0.0
        sim_einstand = opt_aktueller_wert
        milestone_added = opt_aktueller_wert >= 100000.0

        for m_idx in range(1, 121):
            _entn = min(opt_entnahme, max(sim_w_prog * (1 + opt_zins_mo) + opt_sparrate, 0.0))
            sim_w_prog = max(sim_w_prog * (1 + opt_zins_mo) + opt_sparrate - _entn, 0.0)
            sim_einstand += opt_sparrate
            sim_e_prog += _entn

            current_date = now_berlin.replace(tzinfo=None) + pd.DateOffset(months=m_idx)

            if not milestone_added and sim_w_prog >= 100000.0:
                forecast_data.append({
                    "Jahr": "100k",
                    "Datum": current_date.strftime("%d.%m.%Y"),
                    "Gewinn ab heute": fmt_vz(sim_w_prog + sim_e_prog - sim_einstand),
                    "Depotwert": fmt(sim_w_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                })
                milestone_added = True

            if m_idx % 12 == 0:
                forecast_data.append({
                    "Jahr": f"Jahr +{m_idx // 12}",
                    "Datum": current_date.strftime("%d.%m.%Y"),
                    "Gewinn ab heute": fmt_vz(sim_w_prog + sim_e_prog - sim_einstand),
                    "Depotwert": fmt(sim_w_prog, 2), "Kumulierte Entnahme": fmt(sim_e_prog, 2)
                })

        df_forecast = pd.DataFrame(forecast_data)

        # Ohne Entnahme ist "Kumulierte Entnahme" durchgehend 0 und kostet
        # auf dem Smartphone nur seitliche Scrollbreite.
        if not opt_entnahme:
            df_forecast = df_forecast.drop(columns=["Kumulierte Entnahme"], errors="ignore")

        schritte.titel(st, "prognose", 3)
        # Hoehe an die tatsaechliche Zeilenzahl anpassen: st.dataframe
        # begrenzt sonst auf ~10 Zeilen und scrollt INNERHALB der
        # Tabelle - auf dem Smartphone unangenehm, weil man dann zwei
        # verschachtelte Scrollbereiche hat und das Ende nicht sieht.
        # 35px je Zeile + 38px Kopfzeile entspricht Streamlits Raster.
        _tabellen_hoehe = 38 + 35 * len(df_forecast)
        st.dataframe(
            df_forecast, width="stretch", hide_index=True, key="df_forecast",
            height=_tabellen_hoehe,
            column_config={
                # Jetzt wieder "small": "Jahr +10" ist der laengste
                # Eintrag, seit "🎯 100k Meilenstein" zu "100k" gekuerzt
                # wurde - spart Breite fuer die Betrags-Spalten.
                "Jahr": st.column_config.TextColumn("Jahr", width="small"),
                "Datum": st.column_config.TextColumn("Datum", width="small"),
                # Betraege sind fertig deutsch formatiert (1.234,56 €) - rechtsbuendig wie Zahlen
                **{s_: st.column_config.TextColumn(s_, alignment="right")
                   for s_ in ("Gewinn ab heute", "Depotwert", "Kumulierte Entnahme") if s_ in df_forecast.columns},
            },
        )
        with st.expander("ℹ️ Tipp zur Tabelle", expanded=False):
            st.caption("Ein Tippen auf einen Spaltenkopf sortiert die Tabelle - "
                       "erneutes Tippen stellt die ursprüngliche Reihenfolge wieder her.")

        # ---------- BANDBREITE STATT EINER EINZELNEN ZAHL ----------
        # Die Tabelle oben rechnet mit EINER konstanten Rendite. Das
        # ist leicht lesbar, verschweigt aber die Unsicherheit. Hier
        # daher zusaetzlich eine Monte-Carlo-Simulation: tausende
        # moegliche Verlaeufe auf Basis der tatsaechlichen
        # Volatilitaet der Kursreihe.
        schritte.titel(st, "prognose", 4, "Bandbreite möglicher Verläufe")

        mc_jahre = st.slider("Zeitraum der Simulation (Jahre)", 1, 15, **_startwert("mc_jahre", 5),
                             key="mc_jahre")
        mc_shrinkage = st.toggle(
            "Dämpfung bei kurzer Historie", **_startwert("mc_shrinkage", True), key="mc_shrinkage",
            help="Zieht den geschätzten Trend Richtung einer konservativen "
                 "Marktrendite (8 % p.a.) - je weniger Historie vorliegt, "
                 "desto stärker. Ohne Dämpfung wird ein kurzer Boom "
                 "ungebremst über Jahre fortgeschrieben.",
        )

        mc_perzentile, mc_kennzahlen = simuliere_bandbreite(
            startwert=opt_aktueller_wert,
            kursreihe=opt.get("kursreihe"),
            jahre=mc_jahre,
            sparrate_monat=opt_sparrate,
            entnahme_monat=opt_entnahme,
            shrinkage=mc_shrinkage,
        )

        if mc_perzentile is None:
            st.caption("Für diesen Wert liegen zu wenige Kursdaten für eine "
                       "Bandbreiten-Simulation vor (mindestens ~30 Handelstage nötig).")
        else:
            st.caption(
                f"{mc_kennzahlen['pfade']:,} simulierte Verläufe über {mc_jahre} Jahre, "
                f"basierend auf der tatsächlichen Schwankungsbreite dieses Wertes "
                f"({mc_kennzahlen['vola_pa']:.0f} % Volatilität p.a.)."
                .replace(",", ".")
            )

            b1, b2 = st.columns(2)
            b1.metric("Mittleres Ergebnis (Median)", fmt(mc_perzentile[50], 0))
            b2.metric("Verlustrisiko",
                      f"{mc_kennzahlen['verlust_wahrscheinlichkeit']:.0f} %",
                      help="Anteil der Verläufe, die unter dem insgesamt eingesetzten Geld enden "
                           f"(heutiger Wert + Sparraten − Entnahmen = {fmt(mc_kennzahlen['eingesetzt'], 0)}).")

            st.markdown(
                '<div class="rows">'
                '<div class="row"><span class="row-label">Sehr schlecht (5 %)</span>'
                f'<span class="row-val">{fmt(mc_perzentile[5], 0)}'
                '<span class="row-note">Nur 5 % der Verläufe endeten darunter</span></span></div>'
                '<div class="row"><span class="row-label">Schlechtes Viertel (25 %)</span>'
                f'<span class="row-val">{fmt(mc_perzentile[25], 0)}</span></div>'
                '<div class="row"><span class="row-label">Mitte (50 %)</span>'
                f'<span class="row-val">{fmt(mc_perzentile[50], 0)}'
                '<span class="row-note">Hälfte darüber, Hälfte darunter</span></span></div>'
                '<div class="row"><span class="row-label">Gutes Viertel (75 %)</span>'
                f'<span class="row-val">{fmt(mc_perzentile[75], 0)}</span></div>'
                '<div class="row"><span class="row-label">Sehr gut (95 %)</span>'
                f'<span class="row-val">{fmt(mc_perzentile[95], 0)}'
                '<span class="row-note">Nur 5 % der Verläufe endeten darüber</span></span></div>'
                '</div>',
                unsafe_allow_html=True,
            )

            with st.expander("Wie kommt diese Bandbreite zustande?", expanded=False):
                st.write(
                    f"- Kursdaten vorhanden für: **{mc_kennzahlen['jahre_historie']:.1f} Jahre**"
                )
                st.write(
                    f"- Trend aus den Rohdaten: **{mc_kennzahlen['mu_roh_pa']:+.0f} % p.a.**"
                )
                if mc_shrinkage:
                    st.write(
                        f"- Nach Dämpfung verwendet: **{mc_kennzahlen['mu_verwendet_pa']:+.0f} % p.a.** "
                        f"(Gewicht auf eigene Daten: {mc_kennzahlen['gewicht_eigene_daten']:.0f} %, "
                        f"Rest Richtung 8 % Marktrendite)"
                    )
                else:
                    st.write("- Dämpfung ist **aus**: der rohe Trend wird ungebremst fortgeschrieben.")
                st.write(f"- Schwankungsbreite: **{mc_kennzahlen['vola_pa']:.0f} % p.a.**")
                st.write("- Der verwendete Trend ist eine logarithmische Rate: ohne Ein-/Auszahlungen "
                         "wächst der **Median** genau mit dieser Rate p.a.; der Durchschnitt aller "
                         "Verläufe liegt wegen der Schwankung darüber.")
                st.write(f"- Verlust heißt: Endwert unter dem eingesetzten Geld "
                         f"({fmt(mc_kennzahlen['eingesetzt'], 0)} = heutiger Wert + Sparraten − Entnahmen).")
                st.caption(
                    "Auch das bleibt ein Modell: Es unterstellt, dass sich Schwankungen "
                    "künftig ähnlich verhalten wie bisher, und kennt weder Marktcrashs "
                    "noch Produktschließungen. Es zeigt aber ehrlicher als eine einzelne "
                    "Zahl, wie breit die möglichen Ausgänge auseinanderliegen."
                )

        # Kurzer, immer sichtbarer Hinweis statt eines langen
        # Dauertextes - die ausfuehrliche Begruendung steht bei
        # Bedarf im Expander darunter (gleiches Muster wie
        # "Wie kommt diese Bandbreite zustande?" darueber).
        st.caption("⚠️ Fortschreibung der Vergangenheit, keine Vorhersage - "
                   "die künftige Rendite kann stark abweichen.")
        with st.expander("Warum ist das keine Vorhersage?", expanded=False):
            st.write(
                "Diese Tabelle schreibt lediglich die Vergangenheit fort - sie "
                "rechnet mit einer konstanten jährlichen Rendite weiter, in der "
                "Realität schwankt jede Anlage. Besonders bei kurzer Haltedauer "
                "oder einem einzelnen, zufällig günstigen/ungünstigen "
                "Startzeitpunkt kann die historische Rate stark von der "
                "künftigen abweichen. Passe den Wert oben gerne an, um eigene "
                "(z. B. konservativere) Annahmen zu testen."
            )

    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Prognose", e)


def szenario_simulator(k):
    """Frueher _render_scenarios in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    SZ = k['SZ']
    WIKIFOLIO_STARTKURS = k['WIKIFOLIO_STARTKURS']
    _h = k['_h']
    _startauswahl = k['_startauswahl']
    _startwert = k['_startwert']
    _zugang_pruefen = k['_zugang_pruefen']
    auflegung_fuer = k['auflegung_fuer']
    get_kurshistorie = k['get_kurshistorie']
    heute_date = k['heute_date']
    ist_wikifolio = k['ist_wikifolio']
    notify_app_error = k['notify_app_error']
    produkt_rendite_pa = k['produkt_rendite_pa']
    prognose_optionen = k['prognose_optionen']
    re = k['re']
    speichere_auflegung = k['speichere_auflegung']
    _zugang_pruefen("📊 Szenario-Simulator (5 Jahre)")
    try:
        _titel_platz = st.empty()        # Titel nennt den gewaehlten Zeitraum - wird unten gefuellt
        schritte.leiste(st, "szenario")
        schritte.titel(st, "szenario", 1)
        # ---------- BASIS: hinterlegten Wert oder eigene Eingabe ----------
        # Vorher rechnete der Simulator immer mit festen 10.000 € und
        # hatte keinerlei Bezug zu den Werten der App. Jetzt laesst sich
        # jeder Wert waehlen, der auch in der Zukunfts-Prognose steht
        # (Hauptposition, weitere Positionen, Beobachtungswerte). Die
        # Felder darunter werden damit vorbelegt, bleiben aber frei
        # aenderbar. Zusaetzlich erscheint die historische Rate dieses
        # Werts als eigenes, hervorgehobenes Szenario.
        # "Standard" = das urspruengliche Verhalten: feste 10.000 €,
        # nur die 7 Standard-Raten (-10 bis +30 % p.a.), ohne Bezug zu
        # einem bestimmten Wert und ohne historisches ⭐-Szenario.
        # Steht bewusst an erster Stelle und ist damit die Vorauswahl.
        STANDARD = "📐 Standard (−10 bis +100 % p.a., 10.000 €)"
        _basis_namen = [STANDARD] + [o["name"] for o in prognose_optionen]
        basis_name = st.selectbox(
            "Wert auswählen:", _basis_namen, **_startauswahl("szenario_basis_wahl", _basis_namen),
            key="szenario_basis_wahl",
        )
        basis = next((o for o in prognose_optionen if o["name"] == basis_name), None)

        if basis is not None:
            _vorbelegung = {
                "start": float(basis["aktueller_wert"]),
                "entnahme": float(basis.get("entnahme") or 0.0),
                "sparrate": float(basis.get("sparrate") or 0.0),
            }
            if basis.get("symbolisch"):
                st.caption(
                    "Beobachtungswert ohne echtes Investment - gerechnet wird mit "
                    f"einem symbolischen Startkapital von {fmt(_vorbelegung['start'], 0)}."
                )
            else:
                st.caption("Vorbelegt mit dem aktuellen Wert dieser Position - "
                           "unten frei anpassbar.")
        else:
            _vorbelegung = {"start": 10000.0, "entnahme": 0.0, "sparrate": 0.0}
            st.caption("Standard-Szenarien ohne Bezug zu einem bestimmten Wert - "
                       "alle Beträge unten frei anpassbar.")

        # Eigener Widget-Key je Auswahl: Streamlit uebernimmt "value="
        # nur beim ERSTEN Anlegen eines Widgets. Mit festem Key bliebe
        # beim Wechsel der alte Betrag stehen - so bekommt jede Auswahl
        # ihr eigenes Feld mit passender Vorbelegung, und eigene
        # Aenderungen bleiben je Wert erhalten.
        _k = re.sub(r"[^A-Za-z0-9]+", "_", basis_name)

        schritte.titel(st, "szenario", 2)
        col_sk, col_en = st.columns(2)
        with col_sk:
            startkapital_szenario = st.number_input(
                "✏️ Startkapital (€)", min_value=0.0,
                **_startwert(f"szenario_startkapital_{_k}", round(_vorbelegung["start"], 2)),
                step=100.0, key=f"szenario_startkapital_{_k}",
            )
        with col_en:
            entnahme_eingabe = st.number_input(
                "✏️ Monatliche Entnahme (€)", min_value=0.0,
                **_startwert(f"szenario_entnahme_{_k}", _vorbelegung["entnahme"]),
                step=10.0, key=f"szenario_entnahme_{_k}",
            )
        sparrate_szenario = st.number_input(
            "✏️ Monatliche Sparrate (€)", min_value=0.0,
            **_startwert(f"szenario_sparrate_{_k}", _vorbelegung["sparrate"]),
            step=10.0, key=f"szenario_sparrate_{_k}",
            help="Zusätzliche monatliche Einzahlung - erhöht das Kapital jeden Monat, statt es zu verringern.",
        )
        # ZIELWERT: frei waehlbar (vorher fest 100k - lag das Kapital schon darueber, zeigte jede
        # Karte "0 Monate" und dasselbe Datum). Vorbelegt mit der naechsten runden Stufe.
        szenario_ziel = st.number_input(
            "🎯 Zielwert (€)", min_value=1000.0, step=10000.0, format="%.0f",
            **_startwert(f"szenario_ziel_{_k}", SZ.naechstes_ziel(startkapital_szenario)),
            key=f"szenario_ziel_{_k}",
            help="Ab welchem Depotwert gilt das Ziel als erreicht? Je Szenario steht darunter, wann.",
        )
        _ziel_txt = SZ.ziel_text(szenario_ziel)

        ohne_entnahme = st.toggle("Ohne monatliche Entnahme berechnen", **_startwert("szenario_ohne_entnahme", False),
                              key="szenario_ohne_entnahme")
        entnahme_fuer_szenario = 0.0 if ohne_entnahme else entnahme_eingabe

        # ZEITRAUM: 5 bis 30 Jahre (vorher fest 5 Jahre)
        szenario_jahre = st.segmented_control(
            "Zeitraum", SZ.ZEITRAEUME, key="szenario_jahre", format_func=lambda j: f"{j} Jahre",
            default=_startwert("szenario_jahre", 10)["value"],
        ) or 10
        szenario_monate = szenario_jahre * 12
        _titel_platz.markdown(
            '<div style="font-size: 1.05rem; font-weight: 800; color: #FFFFFF; margin-bottom: 4px;">'
            f'📊 Szenario-Analyse ({szenario_jahre} Jahre)</div>', unsafe_allow_html=True)

        # STEUERN AUF ENTNAHMEN (per Schalter): Abgeltungsteuer auf den Gewinnanteil jeder Entnahme -
        # damit die gewuenschte Entnahme netto ankommt, wird entsprechend mehr verkauft (szenario.py)
        szenario_steuer, szenario_einstand = None, None
        if entnahme_fuer_szenario > 0:
            if st.toggle("Steuern auf Entnahmen einrechnen", **_startwert("szenario_steuer_an", False),
                         key="szenario_steuer_an",
                         help="Abgeltungsteuer 25 % + Soli (ggf. Kirchensteuer) auf den Gewinnanteil jeder "
                              "Entnahme, mit Sparerpauschbetrag je Kalenderjahr. Die eingegebene Entnahme "
                              "kommt netto an – verkauft wird entsprechend mehr."):
                _st1, _st2 = st.columns(2)
                _kirche = _st1.selectbox("Kirchensteuer", [0, 8, 9], key="szenario_kirche",
                                         **_startauswahl("szenario_kirche", [0, 8, 9]),
                                         format_func=lambda k: "keine" if not k else f"{k} %")
                _frei = _st2.selectbox("Sparerpauschbetrag", [1000, 2000, 0], key="szenario_frei",
                                       **_startauswahl("szenario_frei", [1000, 2000, 0]),
                                       format_func=lambda b: {1000: "1.000 € (Einzelperson)",
                                                              2000: "2.000 € (Verheiratete)",
                                                              0: "schon ausgeschöpft"}[b])
                _st3, _st4 = st.columns(2)
                _tfs = _st3.selectbox("Teilfreistellung", [0, 30], key="szenario_tfs",
                                      **_startauswahl("szenario_tfs", [0, 30]),
                                      format_func=lambda t: "keine (Aktie, Zertifikat, wikifolio)" if not t
                                      else "30 % (Aktien-ETF/-Fonds)")
                _einstand_vor = float(basis.get("einstand") or 0.0) if (basis is not None and not
                                                                       basis.get("symbolisch")) else 0.0
                if not 0 < _einstand_vor <= startkapital_szenario:
                    _einstand_vor = startkapital_szenario
                szenario_einstand = _st4.number_input(
                    "Einstand / Kaufwert (€)", min_value=0.0, step=100.0,
                    **_startwert(f"szenario_einstand_{_k}", round(_einstand_vor, 2)),
                    key=f"szenario_einstand_{_k}",
                    help="Was das Startkapital gekostet hat. Nur der Gewinn darüber wird besteuert – "
                         "bei einem Neueinstieg heute = Startkapital.")
                szenario_steuer = {"kirchensteuer": _kirche, "freibetrag": _frei, "teilfreistellung": _tfs}
                st.caption(f"Steuersatz auf Gewinne: {FMT.pct(SZ.steuersatz(_kirche) * 100, 2)} · "
                           "Näherung ohne Vorabpauschale und Verlustverrechnung.")

        # STANDARD (Audit A-15): sieben Jahresraten inkl. Verlust- und Nullszenario statt
        # 19 Raten von 12,7-213,8 % p.a. - die Bandbreite soll realistische Verlaeufe zeigen.
        # HINTERLEGTER WERT: nur EIN Szenario - die Rate dieses Werts.
        # Vorher liefen dort zusaetzlich alle 19 Standardraten mit, und
        # die eigentlich relevante Rate ging in der Liste unter. Die Rate
        # ist mit der historischen Rendite vorbelegt, aber editierbar,
        # damit sich auch konservativere Annahmen durchrechnen lassen.
        eigene_rate_mo = None
        if basis is None:
            # Renditen in 5-%-Schritten bis 100 % p.a.; die Spanne laesst sich eingrenzen
            _von, _bis = st.select_slider(
                "Rendite-Spanne (% p.a.)", options=SZ.STANDARD_RATEN, key="szenario_spanne",
                value=tuple(_startwert("szenario_spanne", (SZ.STANDARD_RATEN[0], SZ.STANDARD_RATEN[-1]))["value"]),
                format_func=lambda p: f"{p:+.0f} %".replace("+0 %", "0 %"),
            )
            szenario_raten_mo = [SZ.monatsrate(pa) * 100.0 for pa in SZ.STANDARD_RATEN if _von <= pa <= _bis]
        else:
            # NEUEINSTIEG HEUTE: Die Rate kommt aus der Kurshistorie des
            # PRODUKTS, nicht aus dem eigenen Kauf. Der bisherige Wert
            # (basis["cagr_pa"]) misst bei eigenen Positionen Kurs gegen
            # den eigenen KAUFKURS - er haengt also am Einstiegszeitpunkt
            # und beantwortet die Frage "wie lief es fuer MICH bisher".
            # Fuer "was waere, wenn ich heute neu einsteige" zaehlt aber
            # die Entwicklung des Produkts selbst. Geladen wird dabei NUR
            # der gewaehlte Wert (gecacht) - nicht alle anderen.
            _inst_id = basis.get("instrument_id")
            _rate_quelle = "eigener Kauf"
            if basis.get("cagr_rueckfall_hinweis"):
                # < 1 Jahr: hochgerechnete Ø-Monatsrendite bzw. 0 % - Herkunft nennen
                _rate_quelle += ", " + basis["cagr_rueckfall_hinweis"].split(" – ")[0]
            _prod_pa = float(basis.get("cagr_pa") or 0.0)
            _details = []
            if _inst_id:
                _p_hist = get_kurshistorie(
                    # Komplette Historie seit Auflegung (Start bei 100 €)
                    _inst_id, datetime.date(2000, 1, 1), heute_date
                )

                # AUFLEGUNG: ls-tc.de liefert die Historie erst ab Listing
                # (LS9VFS: ab 09.07.2025 bei 128,80 €), obwohl das
                # Zertifikat frueher bei 100 € startete. Dieser Abschnitt
                # fehlt in den Daten - deshalb hier von Hand eintragbar.
                _datenbeginn = (_p_hist.index[0].date() if not _p_hist.empty else heute_date)
                _start_kurs_daten = (float(_p_hist.iloc[0]) if not _p_hist.empty else 100.0)
                # NUR wikifolio-Zertifikate starten bei 100 € - bei ETFs
                # (MSCI, Gold, Nasdaq ...) waere dieser Ankerpunkt falsch,
                # deshalb gibt es die Eingabe dort gar nicht erst.
                if ist_wikifolio(basis.get("wkn"), basis.get("name")):
                    with st.expander("Auflegung des Werts", expanded=False):
                        _gespeichert, _ = auflegung_fuer(_inst_id)
                        st.caption(
                            f"Kursdaten liegen erst ab **{_datenbeginn.strftime('%d.%m.%Y')}** "
                            f"({_start_kurs_daten:.2f} €) vor. wikifolio-Zertifikate starten "
                            f"immer bei **{WIKIFOLIO_STARTKURS:.0f} €** - trag das "
                            "Auflegungsdatum ein, dann zählt auch die Zeit davor mit. "
                            "Die Angabe wird dauerhaft gespeichert und gilt für Prognose, "
                            "Meilenstein und Simulator."
                        )
                        _auf_datum = st.date_input(
                            "Auflegungsdatum", format="DD.MM.YYYY", value=_gespeichert or _datenbeginn,
                            key=f"szenario_aufl_datum_{_k}",
                        )
                        _b1, _b2 = st.columns(2)
                        if _b1.button("Speichern", key=f"szenario_aufl_save_{_k}",
                                      width="stretch"):
                            if speichere_auflegung(_inst_id, _auf_datum):
                                st.success(f"Auflegung {_auf_datum.strftime('%d.%m.%Y')} "
                                           f"zu {WIKIFOLIO_STARTKURS:.0f} € gespeichert.")
                                st.rerun(scope="fragment")
                            else:
                                st.error("Speichern fehlgeschlagen (kein persistenter State?).")
                        if _gespeichert and _b2.button("Entfernen",
                                                       key=f"szenario_aufl_del_{_k}",
                                                       width="stretch"):
                            if speichere_auflegung(_inst_id, None):
                                st.rerun(scope="fragment")
                            else:
                                st.error("Entfernen fehlgeschlagen - nichts geändert.")
                        if _gespeichert:
                            st.caption(f"Aktiv: Auflegung {_gespeichert.strftime('%d.%m.%Y')} "
                                       f"zu {WIKIFOLIO_STARTKURS:.0f} €.")

                _daempfen = st.toggle(
                    "Dämpfung bei kurzer Historie", **_startwert(f"szenario_daempf_{_k}", False),
                    key=f"szenario_daempf_{_k}",
                    help="Zieht das Ergebnis Richtung einer konservativen Marktrendite "
                         "(8 % p.a.), je weniger Historie vorliegt. Aus = der ungefilterte "
                         "Median über alle Zeiträume.",
                )

                # Dieselbe zentrale Funktion wie 100k-Meilenstein und
                # Zukunfts-Prognose - eine Quelle, ueberall dieselbe Zahl.
                _robust, _details = produkt_rendite_pa(
                    _inst_id, heute_date, daempfung=_daempfen,
                )
                if _robust is not None:
                    _prod_pa = _robust
                    _rate_quelle = "Kursentwicklung des Produkts"

            rate_pa_szenario = st.number_input(
                "✏️ Angenommene Rendite p.a. (%)",
                min_value=-99.0, max_value=100000.0, step=5.0,
                **_startwert(f"szenario_rate_{_k}", round(max(_prod_pa, -99.0), 2)), key=f"szenario_rate_{_k}",
                help="Vorbelegt mit der bisherigen Entwicklung dieses Produkts - "
                     "unabhängig davon, wann du selbst gekauft hast. "
                     "Frei überschreibbar, um andere Annahmen durchzurechnen.",
            )
            eigene_rate_mo = ((1 + rate_pa_szenario / 100.0) ** (1 / 12) - 1) * 100.0
            szenario_raten_mo = [round(eigene_rate_mo, 4)]
            st.caption(
                f"Gerechnet als Neueinstieg heute: {fmt(startkapital_szenario, 2)} zum "
                f"{heute_date.strftime('%d.%m.%Y')}. Rendite-Vorgabe {_prod_pa:.2f} % p.a. "
                f"= {((1 + _prod_pa / 100.0) ** (1 / 12) - 1) * 100:.2f} % p.M. "
                f"(Quelle: {_rate_quelle}). Fortschreibung der Vergangenheit, keine Vorhersage."
            )
            if _details:
                with st.expander("Wie wurde die Rendite-Vorgabe ermittelt?", expanded=False):
                    st.caption("Grundlage ist ein **Trend über die gesamte Historie** (Regression durch alle Kurspunkte) plus Zeitfenster **ab 6 Monaten**, daraus der Median. Kürzere Fenster bleiben bewusst außen vor: ein Monat hochgerechnet multipliziert das Zufallsrauschen mit zwölf. Bei kurzer Historie wird das Ergebnis zusätzlich Richtung einer konservativen Marktrendite gedämpft, weil sich aus wenigen Monaten keine verlässliche Jahresrate ablesen lässt.")
                    for _label, _wert in _details:
                        st.write(f"- {_label}: **{_wert:+.2f}% p.a.**")
                    st.write(f"→ Verwendet: **{_prod_pa:+.2f}% p.a.**")

        summary_list = []
        scenario_series = {}

        for r_mo_pct in szenario_raten_mo:
            r_mo = r_mo_pct / 100.0
            r_pa_pct = ((1 + r_mo) ** 12 - 1) * 100.0
            ist_eigene_rate = (eigene_rate_mo is not None
                               and abs(r_mo_pct - round(eigene_rate_mo, 4)) < 1e-9)

            m_to_100k = SZ.monate_bis(szenario_ziel, startkapital_szenario, r_mo, sparrate_szenario,
                                      entnahme_fuer_szenario, szenario_steuer, szenario_einstand,
                                      heute=heute_date)
            _sim = SZ.simuliere(startkapital_szenario, r_mo, szenario_monate, sparrate_szenario,
                                entnahme_fuer_szenario, szenario_steuer, szenario_einstand, heute=heute_date)
            monthly_vals = _sim["werte"]

            _serien_name = f"{FMT.pct(r_pa_pct, 1)} p.a. ({FMT.pct(r_mo_pct, 2)} p.M.)"
            if ist_eigene_rate:
                _serien_name = f"⭐ {_h(basis_name)}: {_serien_name}"   # Plotly deutet Teile von HTML
            scenario_series[_serien_name] = monthly_vals

            if startkapital_szenario >= szenario_ziel:
                m_str = "✅ Bereits erreicht"
                target_date = heute_date.strftime("%m/%Y")
            elif m_to_100k is not None:
                years_100k = m_to_100k // 12
                rem_months = m_to_100k % 12
                m_str = f"🎯 {m_to_100k} Mon. ({years_100k}J {rem_months}M)"
                # Ab HEUTE rechnen, nicht ab dem Kaufdatum: die
                # Simulation startet mit dem heutigen Kapital und zeigt
                # in die Zukunft. Vorher lagen alle Zieldaten um die
                # bisherige Haltedauer zu frueh.
                target_date = (pd.Timestamp(heute_date) + pd.DateOffset(months=m_to_100k)).strftime("%m/%Y")
            else:
                m_str = "Nicht erreicht (> 100 J.)"
                target_date = "N/A"

            summary_list.append({
                "eigene": ist_eigene_rate,
                "rate": r_mo_pct, "rate_pa": r_pa_pct, "ziel_100k": m_str, "ziel_datum": target_date,
                "jahre": {j: monthly_vals[j * 12] for j in SZ.jahres_stuetzpunkte(szenario_jahre)},
                "steuern": _sim["steuern"], "leer_ab": _sim["leer_ab"],
            })

        karten_html = ('<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); '
                       'gap: 10px;">')
        for e in summary_list:
            # Historische Rate des gewaehlten Werts sichtbar absetzen
            _rahmen = ("2px solid #34D399; box-shadow: 0 0 12px rgba(52, 211, 153,0.25)"
                       if e["eigene"] else "1px solid var(--rand)")
            _marke = (f'<div style="font-size: 0.8rem; font-weight: 700; color: #34D399; '
                      f'letter-spacing: 0.6px; margin-bottom: 4px;">⭐ {_h(basis_name.upper())}</div>'
                      if e["eigene"] else "")
            # WICHTIG: HTML ohne Zeilenumbrueche/Einrueckung aufbauen.
            # In einem mehrzeiligen f-String entsteht bei leerem
            # {_marke} eine Leerzeile - Markdown wertet alles danach mit
            # 4+ Leerzeichen Einrueckung als CODEBLOCK und zeigt den
            # HTML-Quelltext als Text an (genau dieser Fehler trat auf).
            _jahre = "".join(
                f'<div><div style="font-size: 0.8rem; color: #A1A1AA;">{j}J</div>'
                f'<div style="font-size: clamp(0.68rem, 2.9vw, 0.8rem); color: #E5E7EB; font-weight: 700; overflow-wrap: anywhere;">{fmt(w, 0)}</div></div>'
                for j, w in e["jahre"].items()
            )
            _zusatz = ""
            if szenario_steuer:
                _zusatz += (f'<div style="font-size: 0.8rem; color: #CBD5E1; margin-top: 8px;">Steuern auf Entnahmen '
                            f'({szenario_jahre} J.): <b>{fmt(e["steuern"], 0)}</b></div>')
            if e["leer_ab"]:
                _zusatz += (f'<div style="font-size: 0.8rem; color: #F87171; margin-top: 4px;">Kapital aufgebraucht '
                            f'nach {e["leer_ab"] // 12} J. {e["leer_ab"] % 12} M.</div>')
            karten_html += (
                f'<div style="background: var(--karte); border: {_rahmen}; border-radius: 16px; padding: 16px;">'
                f'{_marke}'
                f'<div style="font-size: 1rem; font-weight: 800; color: #FFFFFF; margin-bottom: 8px;">'
                f'{FMT.pct(e["rate_pa"], 1)} p.a. <span style="color: #A1A1AA; font-weight: 600; font-size: 0.8rem;">({FMT.pct(e["rate"], 2)} p.M.)</span>'
                f'</div>'
                f'<div style="font-size: 0.85rem; color: #34D399; font-weight: 700; margin-bottom: 6px;">{e["ziel_100k"]}</div>'
                f'<div style="font-size: 0.8rem; color: #CBD5E1; margin-bottom: 8px;">Ziel-Datum ({_ziel_txt}): {e["ziel_datum"]}</div>'
                f'<div style="display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; border-top: 1px solid var(--trenn); padding-top: 8px; font-variant-numeric: tabular-nums;">'
                f'{_jahre}</div>{_zusatz}'
                f'</div>'
            )
        karten_html += "</div>"
        schritte.titel(st, "szenario", 3)
        st.markdown(karten_html, unsafe_allow_html=True)

        fig_scen = go.Figure()
        months_x = list(range(szenario_monate + 1))

        for label, vals in scenario_series.items():
            if label.startswith("⭐"):
                fig_scen.add_trace(go.Scatter(
                    x=months_x, y=vals, mode="lines", name=label,
                    line=dict(color="#34D399", width=4),
                ))
            else:
                fig_scen.add_trace(go.Scatter(
                    x=months_x, y=vals, mode="lines", name=label,
                    line=dict(width=1.5), opacity=0.75,
                ))

        fig_scen.add_hline(
            y=szenario_ziel,
            line_dash="dot",
            line_color="#34D399",
            annotation_text=f"🎯 Ziel {_ziel_txt}",
            annotation_position="top left",
            annotation_font=dict(color="#34D399", size=12)
        )

        fig_scen.update_layout(
            title=f"{szenario_jahre}-Jahres-Wertentwicklung<br>bei monatlichen Wachstumsraten"
                  + ("<br><sup>nach Steuern auf Entnahmen</sup>" if szenario_steuer else ""),
            paper_bgcolor="#000000", plot_bgcolor="#000000",
            margin=dict(l=10, r=60, t=80, b=120), 
            height=580, 
            legend=dict(
                orientation="h", 
                yanchor="top", 
                y=-0.15,  
                xanchor="center", 
                x=0.5, 
                font=dict(color="#E5E7EB", size=12)
            ),
            xaxis=dict(title="Monate ab heute", showgrid=True, gridcolor="#1A1A1A", tickfont=dict(color="#A1A1AA")),
            yaxis=dict(title="Depotwert (€)", showgrid=True, gridcolor="#1A1A1A", side="right", tickfont=dict(color="#A1A1AA")),
            hovermode="x unified",
        )
        st.plotly_chart(UI.chart_stil(fig_scen), width="stretch", key="chart_scenarios", config={"displayModeBar": False})
    except Exception as e:
        st.error(f"⚠️ Fehler in diesem Tab: {e}")
        notify_app_error("Tab-Szenarien", e)
