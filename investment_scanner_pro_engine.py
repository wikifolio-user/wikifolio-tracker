"""Investment Scanner Pro: pure, offline-testable portfolio / order calculations.

All currency inputs MUST be EUR, quotes from external feeds must be timestamped.
Does not place orders or transfer funds.
"""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict


def number(value, default=0.0):
    if isinstance(value, str):
        value = value.strip().replace('€', '').replace(' ', '')
        if ',' in value:
            value = value.replace('.', '').replace(',', '.')
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return n if math.isfinite(n) else default


def positive(value):
    return max(0.0, number(value))


def key(position):
    return str(position.get('isin') or position.get('wkn') or position.get('ticker')
               or position.get('kennung') or position.get('name') or '').strip().upper()


def aliases(position):
    """Identifiers for exact matching; never fuzzy-match different securities."""
    found = [str(position.get(k) or '').strip().upper()
             for k in ('isin', 'wkn', 'ticker', 'kennung')]
    real = [v for v in found if v]
    return real if real else [key(position)]


def holdings_from_csv(raw):
    """Read optional actual holdings: Name;ISIN;WKN;Ticker;Stueck;KursEUR.

    File is interpreted as user-provided snapshot, never as authenticated broker data.
    """
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8-sig')
    if len(raw) > 750_000:
        raise ValueError('Die CSV-Datei ist zu groß (maximal 750 kB).')
    dialect = csv.Sniffer().sniff(raw[:4096], delimiters=';,\t')
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    if reader.fieldnames is None:
        raise ValueError('CSV-Kopfzeile fehlt.')
    def get(row, *names):
        d = {str(k or '').lower().replace('_', '').replace(' ', '').replace('ü','ue'):v
             for k, v in row.items()}
        return next((d[n] for n in names if n in d and d[n] not in (None, '')), '')
    out = []
    for row in reader:
        if len(out) >= 500:
            raise ValueError('Maximal 500 Depotpositionen importierbar.')
        quantity = number(get(row, 'stueck', 'stuck', 'anzahl', 'quantity'), -1)
        price = number(get(row, 'kurseur', 'kurs', 'preiseur', 'priceeur'), -1)
        if quantity < 0 or price <= 0:
            raise ValueError('CSV-Zeile benötigt eine nichtnegative Stückzahl und einen positiven EUR-Kurs.')
        pos = {'name': str(get(row, 'name', 'wertpapier') or '').strip(),
               'isin': str(get(row, 'isin') or '').strip(),
               'wkn': str(get(row, 'wkn') or '').strip(),
               'ticker': str(get(row, 'ticker', 'symbol') or '').strip(),
               'stueck': quantity, 'kurs_eur': price}
        if not key(pos):
            raise ValueError('CSV-Zeile ohne Wertpapierkennung.')
        out.append(pos)
    return out


def kaufplan(depot, kapital_neu, bestand=None, cash_vorhanden=0.0, reserve_pct=15.0,
             live_quotes=None, ganze_stuecke=True, nur_live=True):
    """Buy towards target weights of *whole* portfolio; do not auto-sell existing assets.

    Reserve is reserved from total wealth and existing cash; the portfolio's
    model cash is additional. Returns proposed share counts (never negative).
    Quotes: {key: {'kurs': EUR_price, 'quelle': ..., 'zeit': ...}}.
    Missing or unverifiable quotes never trigger fabricated purchases.
    """
    bestand = bestand or []
    quotes = live_quotes or {}
    kapital_neu, cash_vorhanden = positive(kapital_neu), positive(cash_vorhanden)
    reserve_pct = max(0.0, min(100.0, number(reserve_pct, 15.0)))
    existing = defaultdict(lambda: {'stueck': 0.0, 'wert': 0.0, 'name': '', 'kurs_eur': None})
    alias_to_key = {}
    gesamt_bestand = 0.0
    for p in bestand:
        ident, st, kurs = key(p), positive(p.get('stueck')), positive(p.get('kurs_eur'))
        if not ident or not kurs or not st:
            continue
        e = existing[ident]
        for alias in aliases(p):
            alias_to_key.setdefault(alias, ident)
        e['stueck'] += st
        e['wert'] += st * kurs
        e['name'] = str(p.get('name') or ident)
        e['kurs_eur'] = kurs
        gesamt_bestand += st * kurs
    gesamt = kapital_neu + cash_vorhanden + gesamt_bestand
    reserve = gesamt * reserve_pct / 100.0
    anlagebasis = gesamt - reserve
    modell_cash = anlagebasis * max(0.0, number(depot.get('cash'))) / 100.0
    liquid = kapital_neu + cash_vorhanden
    kaufbudget = max(0.0, liquid - reserve - modell_cash)

    candidates = []
    all_existing = dict(existing)
    for p in sorted(depot.get('positionen') or [], key=lambda t: -number(t.get('score'))):
        ident = key(p)
        if not ident:
            continue
        match = next((alias_to_key[a] for a in aliases(p) if a in alias_to_key), ident)
        ist = existing.pop(match, {'stueck': 0.0, 'wert': 0.0, 'name': '', 'kurs_eur': None})
        target = max(0.0, number(p.get('gewicht'))) / 100.0 * anlagebasis
        deficit = max(0.0, target - ist['wert'])
        q = quotes.get(ident) or {}
        lprice = positive(q.get('kurs'))
        modelprice = positive(p.get('kurs'))
        price = lprice or (modelprice if not nur_live else 0.0)
        source = str(q.get('quelle') or 'Abgerufener EUR-Kurs') if lprice else (
            'Watchlist-Kurs: Alter/Währung prüfen' if price else 'Kein bestätigter EUR-Echtkurs')
        candidates.append({'name': str(p.get('name') or ident), 'kennung': ident,
                           'art': p.get('art') or '', 'score': p.get('score'),
                           'ziel_pct': number(p.get('gewicht')), 'ziel_eur': round(target, 2),
                           'bestand_stueck': ist['stueck'], 'bestand_eur': round(ist['wert'], 2),
                           'restbedarf': deficit, 'kurs_eur': price or None,
                           'quelle': source, 'kurszeit': str(q.get('zeit') or '') if lprice else '',
                           'stueck_kauf': 0.0, 'kauf_eur': 0.0})
    kaufbar = sum(z['restbedarf'] for z in candidates if z['kurs_eur'])
    scale = min(1.0, kaufbudget / kaufbar) if kaufbar > 0 else 0.0
    ausgegeben = 0.0
    # First pass allocates proportionally to deficits; after rounding preserve cash.
    for z in candidates:
        price = positive(z['kurs_eur'])
        if not price:
            continue
        budget = min(z['restbedarf'] * scale, max(0.0, kaufbudget - ausgegeben))
        units = budget / price
        if ganze_stuecke:
            units = math.floor(units + 1e-10)
        cost = max(0.0, units * price)
        if cost > kaufbudget - ausgegeben + 1e-7:
            units = max(0, math.floor((kaufbudget - ausgegeben) / price))
            cost = units * price
        z['stueck_kauf'] = units
        z['kauf_eur'] = round(cost, 2)
        ausgegeben += cost
    # Keep residual cash; no forced top-ups that could breach target.
    for z in candidates:
        z['nachher_eur'] = round(z['bestand_eur'] + z['kauf_eur'], 2)
        z['anteil_gesamt_pct'] = round(100 * z['nachher_eur'] / gesamt, 2) if gesamt else 0.0
        del z['restbedarf']
    unmatched = [dict(kennung=k, name=v['name'], stueck=v['stueck'],
                      kurs_eur=v['kurs_eur'], wert_eur=round(v['wert'], 2)) for k, v in existing.items()]
    available = max(0.0, liquid - ausgegeben)
    return {'gesamt': gesamt, 'bestandwert': gesamt_bestand, 'neues_kapital': kapital_neu,
            'liquiditaet': available, 'investiert_neu': ausgegeben,
            'reserve_ziel': reserve, 'modell_cash_ziel': modell_cash,
            'reserve_erreicht': available + 1e-7 >= reserve,
            'kaufbudget': kaufbudget, 'fehlende_livekurse': sum(1 for z in candidates if not z['kurs_eur']),
            'positionen': candidates, 'nicht_im_modell': unmatched,
            'bestehende_positionen': all_existing}


def entnahmeplan(plan, auszahlung, ganze_stuecke=True):
    """Cash-first immediate withdrawal, then sell largest positions without overselling."""
    cash = positive(plan.get('liquiditaet'))
    wunsch = positive(auszahlung)
    vom_cash = min(wunsch, cash)
    rest = max(0.0, wunsch - vom_cash)
    holdings = []
    for p in plan.get('positionen') or []:
        units = positive(p.get('bestand_stueck')) + positive(p.get('stueck_kauf'))
        kurs = positive(p.get('kurs_eur'))
        if not kurs and positive(p.get('bestand_eur')) and units:
            kurs = positive(p.get('bestand_eur')) / units
        if units and kurs:
            holdings.append({'name': p['name'], 'kennung': p['kennung'], 'stueck': units, 'kurs_eur': kurs})
    for p in plan.get('nicht_im_modell') or []:
        holdings.append({'name': p['name'], 'kennung': p['kennung'],
                         'stueck': positive(p['stueck']), 'kurs_eur': positive(p['kurs_eur'])})
    verkauft, summe = [], 0.0
    for p in sorted(holdings, key=lambda z: -z['stueck'] * z['kurs_eur']):
        if rest <= 1e-8:
            break
        kurs = p['kurs_eur']
        if not kurs:
            continue
        units = min(p['stueck'], math.ceil(rest / kurs - 1e-10) if ganze_stuecke else rest / kurs)
        if units <= 0:
            continue
        val = units * kurs
        verkauft.append({'Wertpapier': p['name'], 'Kennung': p['kennung'], 'Verkauf Stück': units,
                         'Kurs €': kurs, 'Erlös €': round(val, 2), 'Rest Stück': p['stueck'] - units})
        rest = max(0.0, rest - val)
        summe += val
    covered = min(wunsch, cash + summe)
    return {'gewünscht': wunsch, 'auszahlung': covered, 'fehlbetrag': max(0.0, wunsch - covered),
            'cash_genutzt': vom_cash, 'verkaufserloes': summe,
            'cash_danach': max(0.0, cash + summe - covered),
            'depotwert_danach': max(0.0, positive(plan.get('gesamt')) - covered),
            'verkaeufe': verkauft}
