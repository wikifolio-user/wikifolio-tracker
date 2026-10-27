"""Standalone Streamlit screen (own navigation / state) for wikifolio-tracker.

Uses existing REAL watchlist/top-500 state, scanner scoring and LS-TC quotes.
No dependency on Portfolio Builder's entered capital, no order execution.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import csv

import pandas as pd
import streamlit as st

import portfolio_builder_ui as B
import scanner as S
import scanner_ui as SCANNER_DATA
import investment_scanner_pro_engine as E
import formate as FMT
import schritte


PROFILES = {'Defensiv': 'niedrig', 'Ausgewogen': 'mittel', 'Wachstum': 'hoch'}


def _spalten(n, je_zeile=None):
    """n Felder als Raster: je Zeile je_zeile (Standard: alle n), auf dem Smartphone 2 - sonst brechen
    die Beschriftungen zeichenweise. vertical_alignment="bottom" haelt die Felder einer Zeile auf einer Linie, auch wenn ein Label umbricht."""
    breite = 2 if B._smartphone() else (je_zeile or n)
    slots = []
    while len(slots) < n:
        slots += st.columns(breite, vertical_alignment="bottom")
    return slots[:n]


def euro(v):
    return FMT.eur(v, 2)


def _quote_map():
    result = {}
    now = datetime.now(timezone.utc)
    for k, q in (st.session_state.get('isp_quotes') or {}).items():
        try:
            age = now - datetime.fromisoformat(q['zeit'])
            if timedelta() <= age <= timedelta(hours=24) and E.positive(q.get('kurs')):
                result[k] = q
        except (TypeError, ValueError, KeyError):
            continue
    return result


def _refresh_live(h, positions, limit):
    suche, kurs_f = (h or {}).get('suche_instrument'), (h or {}).get('get_live_kurs')
    if not callable(suche) or not callable(kurs_f):
        return 0, ['Kursdienst ist nicht angebunden.']
    quotes = dict(st.session_state.get('isp_quotes') or {})
    frisch = _quote_map()
    # Werte ohne frischen Kurs zuerst - ein zweiter Klick holt so die restlichen
    positions = sorted(positions, key=lambda p: E.key(p) in frisch)
    success, failed = 0, []
    for p in positions[:limit]:
        ident = str(p.get('isin') or p.get('wkn') or '').strip().upper()
        begriff = ident or str(p.get('name') or '').strip()
        if not begriff:
            failed.append('Ohne Kennung')
            continue
        try:
            treffer, art = E.treffer_waehlen(p, suche(begriff) or [])
            if not treffer:
                failed.append(ident or str(p.get('name')))
                continue
            value, _, source = kurs_f(treffer['instrument_id'])
            if E.positive(value) <= 0:
                failed.append(ident or str(p.get('name')))
                continue
            quotes[E.key(p)] = {'kurs': float(value), 'zeit': datetime.now(timezone.utc).isoformat(),
                                 'quelle': f"{source or 'LS-TC'} · EUR-Abruf"
                                           + (f" · über Namen zugeordnet ({treffer.get('isin')}) – bitte prüfen"
                                              if art == 'name' else '')}
            success += 1
        except Exception:
            failed.append(ident or str(p.get('name')))
    st.session_state['isp_quotes'] = quotes
    return success, failed


def _alternativen(bewertet, amount, monate, target, save, withdraw, max_weight, fee, reserve):
    result = []
    for titel, pf in PROFILES.items():
        prof = S.PROFILE[pf]
        d = S.musterdepot(bewertet, {k: prof[k] for k in ('etf', 'aktie', 'wikifolio', 'cash')}, max_weight)
        mu, sigma = S.portfolio_kennzahlen(d)
        investment = max(0.0, amount)
        simulation = S.simulieren(mu, sigma, investment, [save - withdraw] * monate, fee,
                                  pfade=1300, seed=27)
        a = S.auswerten(simulation, target)
        result.append({'Strategie': titel, 'Anzahl Wertpapiere': len(d['positionen']),
                       'Cash im Zieldepot %': round(d['cash'], 1),
                       'Modellrendite p.a. %': round(mu - fee, 2),
                       'Median Endvermögen €': round(a['end'][50]),
                       'Spanne 10–90 % (€)': f"{a['end'][10]:,.0f} – {a['end'][90]:,.0f}",
                       'Zielchance (Modell) %': round(100 * a['wahrscheinlichkeit'], 1) if a['wahrscheinlichkeit'] is not None else None})
    return result


def _on_calculate(h, inputs, holdings):
    katalog = B._katalog(h)
    candidates, stand = SCANNER_DATA._daten(h, katalog)
    if not candidates:
        raise ValueError('Noch keine echten Watchlist-Daten verfügbar. Die Quellen müssen zunächst geladen werden.')
    years = inputs['jahre']
    bew = S.bewerten(candidates, years)
    profile = S.PROFILE[PROFILES[inputs['profil']]]
    split = {k: profile[k] for k in ('etf', 'aktie', 'wikifolio', 'cash')}
    depot = S.musterdepot(bew, split, inputs['max_gewicht'], inputs['min_score'])
    if not depot['positionen']:
        raise ValueError('Für das gewählte Risikoprofil wurden keine ausreichend bewertbaren Instrumente gefunden.')
    total = inputs['kapital'] + inputs['cash_alt'] + sum(E.positive(p['stueck']) * E.positive(p['kurs_eur']) for p in holdings)
    results = _alternativen(bew, max(0.0, total - inputs['sofort']), inputs['jahre'] * 12,
                            inputs['ziel'], inputs['sparen'], inputs['auszahlung'],
                            inputs['max_gewicht'], inputs['kosten'], inputs['reserve'])
    return {'bewertet': bew, 'depot': depot, 'stand': stand, 'inputs': inputs,
            'holdings': holdings, 'szenarien': results,
            'geladen': datetime.now().astimezone().strftime('%d.%m.%Y %H:%M'),
            'anzahl': {typ: sum(c['art'] == typ for c in bew) for typ in ('etf','aktie','wikifolio')}}


def seite(h):
    st.markdown(B.CSS, unsafe_allow_html=True)
    st.markdown('<div class="pb-kopf"><div class="pb-titel">Investment Scanner <span>Pro</span></div>'
                '<div class="pb-unter">Eigenes Kapital · Kaufplan in Stück · Reserve · Entnahmen</div></div>',
                unsafe_allow_html=True)
    st.caption('**Eigenständige Anwendung:** eigenes Anlagekapital, Top-500-/Watchlist-Daten, '
               'kombinierter Investment-Score, konkrete Kaufstückzahlen, Nachkaufreserve und Entnahmen. '
               'Deine anderen Scanner- und Depot-Einstellungen werden nicht verändert.')
    st.info('Datenquelle: gespeicherte echte Watchlist-/Ranking-Daten aus diesem GitHub-Projekt; '
            'Kurse auf Abruf über die bestehende LS-TC-Anbindung. Nicht jeder Wert ist dort handelbar. '
            'Bei fehlenden Kursen werden keine Käufe erfunden.', icon='ℹ️')
    schritte.leiste(st, "scanner_pro", spaeter=() if st.session_state.get('isp_result') is not None else (3, 4))
    schritte.titel(st, "scanner_pro", 1, "Bestand importieren (optional)")

    with st.expander('Eigenes Bestandsdepot optional importieren (CSV)', expanded=False):
        uploaded = st.file_uploader('Bestandsdepot mit Stueck und KursEUR', type=['csv'], key='isp_depot_csv')
        st.caption('Spalten: Name;ISIN;WKN;Ticker;Stueck;KursEUR. '
                   'CSV-Kurse stammen von dir (kein verifizierter Brokerstand). '
                   'Nur der selbst importierte Depotwert fließt ein.')
        st.download_button('Leere Depotvorlage', b'Name;ISIN;WKN;Ticker;Stueck;KursEUR\n',
                           file_name='investment_scanner_bestand.csv', mime='text/csv', key='isp_template')
    try:
        holdings = E.holdings_from_csv(uploaded.getvalue()) if uploaded else []
    except (UnicodeDecodeError, ValueError, csv.Error) as ex:
        st.error(f'Bestandsdepot kann nicht eingelesen werden: {ex}')
        return
    with st.form('isp_form'):
        schritte.titel(st, "scanner_pro", 2, "Kapital, Ziel und Entnahmen")
        # neu angelegte Benutzer (h["null"]): nichts vorbelegt, Regeln ohne Einschraenkung
        null = bool((h or {}).get('null'))
        c = _spalten(12, 3)                    # ein Raster: Desktop 3, Handy 2 Felder je Zeile
        capital = c[0].number_input('Neues Anlagekapital (€)', 0.0, 100_000_000.0, 0.0 if null else 25000.0,
                                    step=1000.0, format="%.0f")
        old_cash = c[1].number_input('Vorhandenes Depot-Cash (€)', 0.0, 100_000_000.0, 0.0, step=100.0,
                                     format="%.0f")
        goal = c[2].number_input('Zielvermögen (€)', 0.0, 500_000_000.0, 0.0 if null else 50000.0, step=1000.0,
                                 format="%.0f")
        years = c[3].number_input('Anlagezeit (Jahre)', 1, 50, 1 if null else 10)
        save = c[4].number_input('Monatlich einzahlen (€)', 0.0, 1_000_000.0, 0.0 if null else 250.0, step=50.0,
                                 format="%.0f")
        withdraw = c[5].number_input('Monatlich entnehmen (€)', 0.0, 1_000_000.0, 0.0, step=50.0, format="%.0f")
        once = c[6].number_input('Sofortentnahme (€)', 0.0, 100_000_000.0, 0.0, step=100.0, format="%.0f")
        reserve = c[7].slider('Nachkaufreserve (% vom Depot)', 0, 60, 0 if null else 15)
        profile = c[8].selectbox('Risikoprofil', list(PROFILES), index=1)
        maxw = c[9].number_input('Max. Gewicht je Wert (%)', 1.0, 100.0, 100.0 if null else 5.0, step=0.5,
                                 format="%.1f")
        minscore = c[10].slider('Mindestscore für Kauf', 0, 100, 0 if null else 55)
        fee = c[11].number_input('Kosten jährlich (%)', 0.0, 5.0, 0.0 if null else 0.3, step=0.1, format="%.2f")
        allow_partial = st.checkbox('Bruchstücke zulassen (falls Broker unterstützt)', value=False)
        submitted = st.form_submit_button('🔍 Investment Scanner berechnen', type='primary', width="stretch")

    input_data = {'kapital': capital, 'cash_alt': old_cash, 'ziel': goal, 'jahre': years,
                  'sparen': save, 'auszahlung': withdraw, 'sofort': once, 'reserve': reserve,
                  'profil': profile, 'max_gewicht': maxw, 'min_score': minscore,
                  'kosten': fee, 'ganze_stuecke': not allow_partial}
    if submitted:
        try:
            with st.spinner('Lese echte Ranglisten, berechne kombinierte Scores und Szenarien …'):
                st.session_state['isp_result'] = _on_calculate(h, input_data, holdings)
        except Exception as ex:
            st.error(f'Scanner konnte nicht berechnet werden: {ex}')
            st.session_state.pop('isp_result', None)
    res = st.session_state.get('isp_result')
    if res is None:
        st.caption('Noch kein Ergebnis – Scanner mit deinen Daten starten.')
        return
    if res['inputs'] != input_data or res['holdings'] != holdings:
        st.warning('Eingaben wurden verändert. „Berechnen“ klicken, um Ergebnis und Kapitalabgleich zu erneuern.')

    e = res['inputs']
    d = res['depot']
    st.caption(f"Scan: {res['geladen']} · {res['anzahl']['aktie']} Aktien, "
               f"{res['anzahl']['etf']} ETFs, {res['anzahl']['wikifolio']} wikifolios mit Daten im Universum")
    for note in d['hinweise'][:8]:
        st.caption('• ' + note)
    schritte.titel(st, "scanner_pro", 3, "Kaufplan zum Gesamtdepot")
    require_live = st.toggle('Für Neukäufe nur frisch abgerufene EUR-Kurse verwenden (empfohlen)',
                             value=True, key='isp_strict')
    c = _spalten(2)
    n_pos = max(len(d['positionen']), 1)
    count = c[0].slider('Wie viele Positionen auf Echtkurse prüfen?', 1, max(n_pos, 2), n_pos, key='isp_check_count',
                        help='Standard: alle Positionen des Musterdepots. Werte ohne frischen Kurs werden zuerst '
                             'abgefragt.')
    if c[1].button('🔄 Jetzt echte Börsenkurse abrufen', width="stretch", key='isp_fetch'):
        with st.spinner('Abruf über die bestehende LS-TC-Anbindung …'):
            ok, missing = _refresh_live(h, d['positionen'], count)
        st.info(f'{ok} von {min(count, len(d["positionen"]))} abgefragten Wertpapieren mit Kurs zugeordnet. '
                'Werte, die ls-tc.de nicht führt, bleiben ohne Echtkurs.')
        if missing:
            st.caption('Nicht verfügbar: ' + ', '.join(missing[:8]))
    quotes = _quote_map()
    plan = E.kaufplan(d, e['kapital'], res['holdings'], e['cash_alt'],
                     e['reserve'], quotes, e['ganze_stuecke'], nur_live=require_live)
    one = E.entnahmeplan(plan, e['sofort'], e['ganze_stuecke'])
    c = _spalten(4)
    c[0].metric('Gesamtdepot (Planungsstand)', euro(plan['gesamt']))
    c[1].metric('Geplante Neukäufe', euro(plan['investiert_neu']))
    c[2].metric('Nachkaufreserve (Ziel)', euro(plan['reserve_ziel']))
    c[3].metric('Verbleibendes Cash', euro(plan['liquiditaet']))
    if not plan['reserve_erreicht']:
        st.warning('Die Nachkaufreserve ist wegen vorhandener Depotpositionen/geringer Liquidität noch nicht vollständig vorhanden.')
    if plan['fehlende_livekurse']:
        st.warning(f"Bei {plan['fehlende_livekurse']} Kandidaten fehlt ein für Neukäufe zulässiger EUR-Kurs. "
                   'Sie bleiben im geplanten Kaufplan vorerst ohne Order.')
    table = pd.DataFrame(plan['positionen']).rename(columns={
        'name': 'Wertpapier', 'kennung': 'Kennung', 'art': 'Klasse', 'score': 'Score',
        'ziel_pct': 'Modellanteil %', 'ziel_eur': 'Modellziel €', 'bestand_stueck': 'Bestand Stück',
        'bestand_eur': 'Bestand €', 'kurs_eur': 'Kurs €', 'quelle': 'Kursquelle',
        'kurszeit': 'Kursabruf', 'stueck_kauf': 'Kauf Stück', 'kauf_eur': 'Kauf €',
        'nachher_eur': 'Wert danach €', 'anteil_gesamt_pct': 'Anteil gesamt %'})
    for spalte in ('Kurs €', 'Score'):
        if spalte in table:
            table[spalte] = pd.to_numeric(table[spalte], errors='coerce')
    st.dataframe(table, width="stretch", hide_index=True)
    if not table.empty:
        st.download_button('📥 Kaufplan CSV herunterladen', table.to_csv(index=False, sep=';').encode('utf-8-sig'),
                           'investment_scanner_pro_kaufplan.csv', 'text/csv', key='isp_export')
    if plan['nicht_im_modell']:
        st.info(f"{len(plan['nicht_im_modell'])} vorhandene Depotposition(en) liegen außerhalb des Musterdepots. "
                'Sie bleiben erhalten und werden bei der Depot-Gesamtsumme mitgezählt (kein automatischer Verkauf).')
    schritte.titel(st, "scanner_pro", 4, "Sofortige und laufende Entnahmen")
    if e['sofort'] > 0:
        c = _spalten(3)
        c[0].metric('Sofort auszahlbar (Modell)', euro(one['auszahlung']))
        c[1].metric('Nicht gedeckter Betrag', euro(one['fehlbetrag']))
        c[2].metric('Depot danach', euro(one['depotwert_danach']))
        if one['verkaeufe']:
            sold = pd.DataFrame(one['verkaeufe'])
            st.dataframe(sold, hide_index=True, width="stretch")
            st.download_button('📥 Verkaufsvorschlag CSV', sold.to_csv(index=False, sep=';').encode('utf-8-sig'),
                               'investment_scanner_pro_verkauf.csv', 'text/csv', key='isp_sales')
        if one['fehlbetrag']:
            st.error('Entnahme ist nicht vollständig durch Cash oder bewertbare Positionen gedeckt.')
        if one['cash_danach'] < plan['reserve_ziel'] - 0.01:
            st.warning('Nach der Sofortentnahme liegt die Liquidität unter der gewünschten Nachkaufreserve.')
    st.caption(f"Laufende Einzahlungen {e['sparen']:.0f} €/Monat; "
               f"Entnahmen {e['auszahlung']:.0f} €/Monat über {e['jahre']} Jahre. "
               'Keine tatsächliche Abbuchung und kein Depotauftrag.')

    st.markdown('#### Alternative Anlagevermögen und Zielerreichung')
    st.caption('Szenarien basieren auf Modellrenditen und Volatilitätsannahmen, nicht auf garantierten Echtzeit-Prognosen. '
               'Sie zeigen ausdrücklich auch Strategien mit geringer Zielchance.')
    st.dataframe(pd.DataFrame(res['szenarien']), hide_index=True, width="stretch")
    mu, sigma = S.portfolio_kennzahlen(d)
    m = e['jahre'] * 12
    cashflows = [e['sparen'] - e['auszahlung']] * m
    simulation = S.simulieren(mu, sigma, one['depotwert_danach'], cashflows, e['kosten'], pfade=2000, seed=31)
    outcome = S.auswerten(simulation, e['ziel'])
    d1, d2, d3 = _spalten(3)
    d1.metric('Median-Endvermögen', euro(outcome['end'][50]))
    d2.metric('Zielchance (Modell)', f"{100 * outcome['wahrscheinlichkeit']:.1f} %".replace('.', ',') if outcome['wahrscheinlichkeit'] is not None else '–')
    d3.metric('Schwankung Modell p.a.', f'{sigma:.1f} %'.replace('.', ','))
    Verlauf = pd.DataFrame(S.verlauf_jaehrlich(simulation)).rename(columns={
        'monat': 'Monat', 'p10': 'Pessimistisch (10 %)', 'p50': 'Median (50 %)', 'p90': 'Optimistisch (90 %)'})
    st.line_chart(Verlauf.set_index('Monat'))
    with st.expander('Kandidaten, Datenstand und Grenzen'):
        df = pd.DataFrame([{'Wertpapier': z['name'], 'Art': z['art'], 'Score': z['score'],
                            'Eignung': 'ausreichend' if z['ausreichend'] else 'nicht ausreichend',
                            'Kurs € (Datenbestand)': z.get('kurs'), 'Kennung': E.key(z)}
                           for z in res['bewertet']])
        st.dataframe(df.sort_values('Score', ascending=False).head(500), hide_index=True, width="stretch")
        for key_, value in res['stand'].items():
            st.caption(f'{key_}: {value or "kein Zeitstempel verfügbar"}')
        st.caption('Top 500 = höchstens 500 Ranglisteneinträge aus dem vorhandenen tatsächlichen Datenbestand, '
                   'keine Garantie auf 500 weltweit vollständige oder aktuelle Instrumente. '
                   'ETF-TER, Wikifolio-Gebühren, Liquidität und Emittentenrisiko werden nicht vollständig im Score erfasst.')
    st.caption('Fiktive Preise werden nicht erzeugt. Mit deaktiviertem Echtkurs-Schalter können ältere '
               'Watchlist-Kurse verwendet werden – bitte vor jeder Kaufentscheidung verifizieren. '
               'CSV-Import ist ein manuelles Modell, kein Brokerage-Sync. '
               'Steuern, Spread, Ausführungspreise und Wechselkurse bei Verkäufen sind nicht vollständig modelliert. '
               'Keine Anlageberatung, kein automatischer Handel.')
