"""Hilfsbausteine fuer "Depot verwalten": Instrumentsuche, Formular fuer neue Positionen, Karten der Beobachtungsliste
(aus app.render_dashboard ausgelagert, Audit ARCH-01). Rumpfe unveraendert; was sie aus dem Funktionskontext lasen,
bekommen sie ausdruecklich als Woerterbuch k uebergeben. app.py ruft sie ueber gleichnamige Huellen auf.
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


def de_zahl(k, wert, nachkomma=2):
    """Frueher de_zahl in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    """Deutsche Schreibweise (zentral: formate.zahl) - bewusst nur auf den ZAHLENWERT
    angewendet, nicht auf das umgebende HTML. Kurse mit 2 Nachkommastellen (UX 10/2026:
    "150,000 €" las sich wie 150 Tausend)."""
    return FMT.zahl(wert, nachkomma)


def instrument_suchblock(k, prefix, label='WKN, ISIN oder Name suchen'):
    """Frueher instrument_suchblock in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    get_live_kurs = k['get_live_kurs']
    suche_instrument = k['suche_instrument']
    """Wiederverwendbarer Suchblock. Muss AUSSERHALB eines st.form stehen,
    da Formulare erst beim Submit einen Rerun ausloesen - die Suche soll
    aber sofort reagieren. Sucht bei Eingabe (Enter/Verlassen des Felds),
    ohne extra Klick. Gibt den gewaehlten Treffer als dict zurueck (oder None).

    prefix trennt die session_state-Keys, damit jede Position ihren
    eigenen, unabhaengigen Suchzustand hat."""
    # Schluessel mit Zaehler: nach dem Speichern bekommt das Feld einen neuen Schluessel und ist
    # wirklich leer - sonst schickt der Browser den alten Begriff erneut und das naechste
    # Formular uebernaehme wieder WKN/Kursquelle des alten Treffers (360°-Pruefung F-04)
    suchbegriff = st.text_input(
        label, key=f"{prefix}_suche_{st.session_state.get(f'{prefix}_nr', 0)}",
        placeholder="z. B. A0LC12, IE00B4L5Y983 oder MSCI World",
    )

    # Nur neu suchen, wenn sich der Begriff geaendert hat - sonst wuerde
    # jeder Rerun (z.B. durch ein anderes Widget) erneut suchen.
    if suchbegriff and st.session_state.get(f"{prefix}_letzter") != suchbegriff:
        st.session_state[f"{prefix}_letzter"] = suchbegriff
        st.session_state[f"{prefix}_treffer"] = suche_instrument(suchbegriff)
        st.session_state.pop(f"{prefix}_wahl", None)

    if not suchbegriff:
        return None

    treffer = st.session_state.get(f"{prefix}_treffer", [])
    if not treffer:
        st.caption("⚠️ Keine Treffer – Schreibweise prüfen oder die Kursquelle-ID manuell eintragen.")
        return None

    optionen = {
        f"{t['name']} · {t['kategorie']} · WKN {t['wkn'] or '–'}": t
        for t in treffer
    }
    wahl = st.selectbox("Treffer auswählen", list(optionen.keys()), key=f"{prefix}_wahl")
    gewaehlt = optionen[wahl]

    live_kurs, _, _ = get_live_kurs(gewaehlt["instrument_id"])
    kurs_txt = f"{FMT.eur(live_kurs, 2)}" if live_kurs else "kein Kurs verfügbar"
    st.caption(
        f"→ **{gewaehlt['name']}** · ID {gewaehlt['instrument_id']} · "
        f"ISIN {gewaehlt['isin'] or '–'} · aktuell {kurs_txt}"
    )
    return gewaehlt


def suche_zuruecksetzen(k, prefix):
    """Frueher suche_zuruecksetzen in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""

    """Suchblock leeren (neues, leeres Suchfeld; Treffer und Auswahl vergessen)."""
    for k in (f"{prefix}_letzter", f"{prefix}_treffer", f"{prefix}_wahl"):
        st.session_state.pop(k, None)
    st.session_state[f"{prefix}_nr"] = st.session_state.get(f"{prefix}_nr", 0) + 1


def positions_anlage_formular(k, prefix):
    """Frueher positions_anlage_formular in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    aendere_positionen = k['aendere_positionen']
    get_live_kurs = k['get_live_kurs']
    heute_date = k['heute_date']
    instrument_suchblock = k['instrument_suchblock']
    suche_zuruecksetzen = k['suche_zuruecksetzen']
    uuid = k['uuid']
    """Neue Position anlegen (Suche + Formular). prefix trennt die Schluessel - das
    Formular steht in den Einstellungen ("neu") und im leeren Depot ("leer")."""
    gewaehlt = instrument_suchblock(prefix)
    # Schluessel haengen am gewaehlten Treffer - so uebernimmt das Formular eine neue
    # Suche als Vorbelegung (gleiches Muster wie beim Bearbeiten)
    sfx = f"{prefix}_{gewaehlt['instrument_id'] if gewaehlt else 0}"

    with st.form(f"pos_form_{prefix}", clear_on_submit=True):
        neu_name = st.text_input(
            "Name", value=(gewaehlt["name"] if gewaehlt else ""),
            placeholder="z. B. MSCI World ETF", key=f"{sfx}_f_name")
        neu_wkn = st.text_input(
            "WKN / ISIN",
            value=(gewaehlt["wkn"] or gewaehlt["isin"]) if gewaehlt else "",
            placeholder="z. B. A0RPWH", key=f"{sfx}_f_wkn")
        neu_inst = st.number_input(
            "Kursquelle-ID (wird über die Suche gesetzt, optional)", min_value=0, step=1,
            value=int(gewaehlt["instrument_id"]) if gewaehlt else 0,
            help="Wird durch die Suche oben automatisch gefüllt. Kann auch leer "
                 "(0) bleiben - dann werden für diese Position keine Kurse geladen "
                 "und sie zählt nicht in die Depot-Summe. Jederzeit nachtragbar.",
            key=f"{sfx}_f_inst",
        )
        neu_datum = st.date_input("Kaufdatum", value=heute_date, key=f"{prefix}_f_datum", format="DD.MM.YYYY")
        neu_kurs = st.number_input("Kaufkurs (€)", min_value=0.0, step=0.01, format="%.4f", value=0.0,
                                   key=f"{prefix}_f_kurs")
        neu_kapital = st.number_input("Investiertes Kapital (€)", min_value=0.0, step=100.0, value=0.0,
                                      key=f"{prefix}_f_kapital")

        if st.form_submit_button("➕ Position anlegen", width="stretch"):
            if not neu_name or neu_kurs <= 0 or neu_kapital <= 0:
                st.error("Bitte Name, Kaufkurs und Kapital ausfüllen.")
            else:
                # Instrument-ID, falls angegeben, vor dem Speichern pruefen -
                # verhindert stumme Fehlkonfiguration. Ohne ID wird die
                # Position angelegt und spaeter als "keine Kursquelle" markiert.
                test_kurs = None
                if neu_inst:
                    test_kurs, _, _ = get_live_kurs(int(neu_inst))

                if neu_inst and test_kurs is None:
                    st.error(
                        f"Für die Kursquelle-ID {int(neu_inst)} liefert ls-tc.de keine Kursdaten. "
                        "Bitte die ID prüfen – oder das Feld leer (0) lassen und später nachtragen."
                    )
                else:
                    _p_anlage = {
                        "id": f"pos-{uuid.uuid4().hex[:12]}",     # eindeutig, auch bei zwei Anlagen je Sekunde
                        "name": neu_name, "wkn": neu_wkn,
                        "instrument_id": int(neu_inst) if neu_inst else None,
                        "kaufdatum": neu_datum.isoformat(), "kaufkurs": float(neu_kurs),
                        "startkapital": float(neu_kapital),
                    }
                    if aendere_positionen(lambda l: l + [_p_anlage], "position angelegt [skip ci]"):
                        suche_zuruecksetzen(prefix)
                        if test_kurs is not None:
                            st.success(f"„{neu_name}“ angelegt (aktueller Kurs {FMT.eur(test_kurs, 2)}).")
                        else:
                            st.success(f"„{neu_name}“ angelegt – ohne Kursquelle. "
                                       "Kursquelle-ID kann oben jederzeit ergänzt werden.")
                        st.rerun()
                    else:
                        st.error("Anlegen fehlgeschlagen (kein persistenter State?).")


def beobachtungs_karte(k, eintrag, fortschritt=None, im_depot=False):
    """Frueher beobachtungs_karte in app.render_dashboard (Rumpf unveraendert). k: alle benoetigten Werte und Funktionen der App."""
    _h = k['_h']
    berechne_zeitraeume = k['berechne_zeitraeume']
    depot_kachel_html = k['depot_kachel_html']
    get_kurshistorie = k['get_kurshistorie']
    get_live_kurs = k['get_live_kurs']
    heute_date = k['heute_date']
    kurs_pill = k['kurs_pill']
    kurs_status = k['kurs_status']
    kurs_zeitpunkt = k['kurs_zeitpunkt']
    now_berlin = k['now_berlin']
    """Baut eine Kurskachel im selben Aufbau wie die Hauptkachel, aber fuer
    einen reinen Beobachtungswert. Höchststand wird hier aus der geladenen
    Historie bestimmt (kein persistenter State noetig) - fuer einen Wert,
    den man nicht besitzt, ist die Performance Fee ohnehin irrelevant."""
    if fortschritt:
        fortschritt(35, "Rufe Live-Kurs ab …")
    b_kurs, b_vortag, _ = get_live_kurs(eintrag["instrument_id"])
    if b_kurs is None:
        return (
            '<div class="quote">'
            f'<div class="q-name">{_h(eintrag.get("name", ""))} · {_h(eintrag.get("wkn", ""))}</div>'
            '<div class="price-line">'
            '<span class="q-price">–</span>'
            '<span class="meta-chip">keine Live-Daten</span>'
            '</div>'
            '<div class="card-footnote">ls-tc.de liefert für diesen Wert gerade '
            'keine Kurse. Kursquelle-ID prüfen oder später erneut versuchen.</div>'
            '</div>'
        )

    if fortschritt:
        fortschritt(65, "Lade Kurshistorie …")
    b_hist = get_kurshistorie(
        eintrag["instrument_id"], heute_date - datetime.timedelta(days=420), heute_date
    )
    if fortschritt:
        fortschritt(90, "Berechne Zeiträume …")
    b_perioden = berechne_zeitraeume(b_kurs, b_vortag, b_hist, heute_date)

    b_hw_zeile = ""
    if not b_hist.empty:
        b_hoch = float(b_hist.max())
        b_hoch_datum = b_hist.idxmax().strftime("%d.%m.%Y")
        b_abstand_pct = (b_kurs - b_hoch) / b_hoch * 100 if b_hoch else 0.0
        b_wert_html = ('<span class="up">erreicht</span>' if b_abstand_pct >= -0.0005
                       else f'<span class="down">{FMT.pct(b_abstand_pct, 2)}</span>')
        b_hw_zeile = (
            '<div class="perf-row"><span class="perf-label">Höchststand</span>'
            f'<span class="perf-vals"><span class="neutral">{FMT.eur(b_hoch, 2)}</span>'
            f'{b_wert_html}</span></div>'
        )
        b_fuss = (f'Lang &amp; Schwarz · je Anteil · Höchststand vom {b_hoch_datum} '
                  f'(aus verfügbarer Kurshistorie)')
    else:
        b_fuss = 'Lang &amp; Schwarz · je Anteil'
    if not im_depot:
        b_fuss += ' · nicht im Depot enthalten'

    return depot_kachel_html(
        f'{_h(eintrag.get("name", ""))} · {_h(eintrag.get("wkn", ""))}', FMT.kurs(b_kurs),
        chips=kurs_pill(*kurs_status(kurs_zeitpunkt(eintrag["instrument_id"]), now_berlin, True))
        + ('' if im_depot else '<span class="meta-chip">Beobachtung</span>'),
        zeilen=b_perioden, kopfzeile=("Vortag", FMT.kurs(b_vortag)) if b_vortag else None,
        fusszeile=b_hw_zeile, fussnote=b_fuss, klasse="quote", wert_klasse="q-price", titel_klasse="q-name")
