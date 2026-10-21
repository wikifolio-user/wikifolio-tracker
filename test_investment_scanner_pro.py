import unittest
from investment_scanner_pro_engine import kaufplan, entnahmeplan, holdings_from_csv, treffer_waehlen


def portfolio():
    return {'positionen': [
        {'name': 'ETF A', 'isin': 'DE000A', 'score': 83, 'art': 'etf', 'gewicht': 50, 'kurs': 100},
        {'name': 'Aktie B', 'isin': 'DE000B', 'score': 72, 'art': 'aktie', 'gewicht': 30, 'kurs': 25},
    ], 'cash': 20, 'hinweise': []}


class Engine(unittest.TestCase):
    def test_no_fictional_purchase_without_verified_quote(self):
        p = kaufplan(portfolio(), 10000, reserve_pct=15)
        self.assertEqual(0, p['investiert_neu'])
        self.assertEqual(2, p['fehlende_livekurse'])
        self.assertEqual(10000, p['liquiditaet'])

    def test_buys_are_whole_units_reserve_respected(self):
        q = {'DE000A': {'kurs':100,'quelle':'live'}, 'DE000B': {'kurs':25,'quelle':'live'}}
        p = kaufplan(portfolio(), 10000, reserve_pct=15, live_quotes=q)
        self.assertGreater(p['investiert_neu'], 0)
        self.assertGreaterEqual(p['liquiditaet'], 1500)
        self.assertLessEqual(p['investiert_neu'], 6800 + 1e-5)  # after 15% reserve + 20% model cash
        self.assertEqual(p['positionen'][0]['stueck_kauf'], int(p['positionen'][0]['stueck_kauf']))
        self.assertAlmostEqual(sum(x['kauf_eur'] for x in p['positionen']), p['investiert_neu'], places=2)

    def test_existing_positions_reduce_new_purchase(self):
        q = {'DE000A': {'kurs':100}, 'DE000B': {'kurs':25}}
        existing = [{'name':'ETF A', 'isin':'DE000A', 'stueck': 40, 'kurs_eur':100}]
        p = kaufplan(portfolio(), 6000, bestand=existing, reserve_pct=15, live_quotes=q)
        self.assertEqual(10000, p['gesamt'])
        self.assertLess(p['positionen'][0]['kauf_eur'], 250)
        self.assertEqual(p['positionen'][0]['bestand_eur'], 4000)

    def test_large_immediate_withdrawal_capped_and_no_overselling(self):
        p = kaufplan(portfolio(), 10000, reserve_pct=15,
                     live_quotes={'DE000A': {'kurs':100}, 'DE000B': {'kurs':25}})
        s = entnahmeplan(p, 50000)
        self.assertGreater(s['fehlbetrag'], 0)
        self.assertLessEqual(s['auszahlung'], 10000)
        self.assertEqual(0, s['depotwert_danach'])
        for z in s['verkaeufe']:
            self.assertGreaterEqual(z['Rest Stück'], 0)

    def test_cash_first_withdrawal(self):
        p = kaufplan(portfolio(), 10000, reserve_pct=15)
        s = entnahmeplan(p, 500)
        self.assertEqual(s['cash_genutzt'], 500)
        self.assertEqual(s['verkaeufe'], [])

    def test_holdings_match_even_if_only_wkn_was_imported(self):
        d = portfolio()
        d['positionen'][0]['wkn'] = 'A12345'
        q = {'DE000A': {'kurs': 100}, 'DE000B': {'kurs':25}}
        p = kaufplan(d, 6000, bestand=[{'wkn':'A12345', 'stueck':40, 'kurs_eur':100}],
                     live_quotes=q)
        self.assertEqual(4000, p['positionen'][0]['bestand_eur'])
        self.assertLessEqual(p['positionen'][0]['stueck_kauf'], 3)

    def test_existing_unknown_not_sold_to_fund_new_purchases(self):
        q = {'DE000A': {'kurs':100}, 'DE000B': {'kurs':25}}
        p = kaufplan(portfolio(), 1000, bestand=[{'name':'Externer Fonds','isin':'ZZZ','stueck':20,'kurs_eur':500}],
                     reserve_pct=15, live_quotes=q)
        self.assertEqual(11000, p['gesamt'])
        self.assertTrue(p['nicht_im_modell'])
        self.assertEqual(p['investiert_neu'], 0)

    def test_csv_german_decimals(self):
        data = 'Name;ISIN;WKN;Ticker;Stueck;KursEUR\nETF;DE000A;;;10,5;123,45\n'
        got = holdings_from_csv(data)
        self.assertEqual(got[0]['stueck'], 10.5)
        self.assertEqual(got[0]['kurs_eur'], 123.45)

    def test_csv_invalid_price_rejected(self):
        with self.assertRaises(ValueError):
            holdings_from_csv('Name;ISIN;Stueck;KursEUR\nX;DE000;3;-3\n')


class Kurssuche(unittest.TestCase):
    T = [{'instrument_id': 1, 'name': 'Apple Inc.', 'wkn': '865985', 'isin': 'US0378331005', 'kategorie': 'Aktie'},
         {'instrument_id': 2, 'name': 'Apple Hospitality REIT', 'wkn': 'A2AJHS', 'isin': 'US03784Y2000',
          'kategorie': 'Aktie'},
         {'instrument_id': 3, 'name': 'Apple Inc. Turbo Call', 'wkn': 'XY1234', 'isin': 'DE000XY12345',
          'kategorie': 'Knock-Out'}]

    def test_exakt_ueber_isin_oder_wkn(self):
        self.assertEqual(treffer_waehlen({'isin': 'us0378331005'}, self.T), (self.T[0], 'exakt'))
        self.assertEqual(treffer_waehlen({'wkn': 'A2AJHS'}, self.T), (self.T[1], 'exakt'))
        self.assertEqual(treffer_waehlen({'isin': 'US0000000000'}, self.T), (None, None))   # nie ueber Namen

    def test_name_nur_eindeutig_und_nur_aktien(self):
        self.assertEqual(treffer_waehlen({'name': 'Apple Inc', 'ticker': 'AAPL'}, self.T), (self.T[0], 'name'))
        self.assertEqual(treffer_waehlen({'name': 'Apple', 'ticker': 'AAPL'}, self.T), (self.T[0], 'name'))  # Rechtsform egal
        self.assertEqual(treffer_waehlen({'name': 'Apple Computer'}, self.T), (None, None))      # anderer Name
        doppelt = self.T + [dict(self.T[0], instrument_id=9, isin='US0378331099')]
        self.assertEqual(treffer_waehlen({'name': 'Apple Inc.'}, doppelt), (None, None))


if __name__ == '__main__':
    unittest.main()
