# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date, datetime
from urllib.request import urlopen
import json

from core.model.currency import RateProviderUnavailable, CurrencyProvider

CURRENCY2BOCID = {
    'USD': 'IEXE0101',
    'ARS': 'IEXE2702',
    'AUD': 'IEXE1601',
    'BSD': 'IEXE6001',
    'BRL': 'IEXE2801',
    'XAF': 'IEXE4501',
    'XPF': 'IEXE4601',
    'CLP': 'IEXE2901',
    'CNY': 'IEXE2201',
    'COP': 'IEXE3901',
    'HRK': 'IEXE6101',
    'CZK': 'IEXE2301',
    'DKK': 'IEXE0301',
    'XCD': 'IEXE4001',
    'EUR': 'EUROCAE01',
    'FJD': 'IEXE4101',
    'GHS': 'IEXE4702',
    'GTQ': 'IEXE6501',
    'HNL': 'IEXE4301',
    'HKD': 'IEXE1401',
    'HUF': 'IEXE2501',
    'ISK': 'IEXE4401',
    'INR': 'IEXE3001',
    'IDR': 'IEXE2601',
    'ILS': 'IEXE5301',
    'JMD': 'IEXE6401',
    'JPY': 'IEXE0701',
    'MYR': 'IEXE3201',
    'MXN': 'IEXE2001',
    'MAD': 'IEXE4801',
    'MMK': 'IEXE3801',
    'NZD': 'IEXE1901',
    'NOK': 'IEXE0901',
    'PKR': 'IEXE5001',
    'PAB': 'IEXE5101',
    'PEN': 'IEXE5201',
    'PHP': 'IEXE3301',
    'PLN': 'IEXE2401',
    'RON': 'IEXE6505',
    'RUB': 'IEXE2101',
    'RSD': 'IEXE6504',
    'SGD': 'IEXE3701',
    'SKK': 'IEXE6201',
    'ZAR': 'IEXE3401',
    'KRW': 'IEXE3101',
    'LKR': 'IEXE5501',
    'SEK': 'IEXE1001',
    'CHF': 'IEXE1101',
    'TWD': 'IEXE3501',
    'THB': 'IEXE3601',
    'TND': 'IEXE5701',
    'AED': 'IEXE6506',
    'GBP': 'IEXE1201',
    'VEF': 'IEXE5902',
    'VND': 'IEXE6503',
}

class BOCProvider(CurrencyProvider):
    def register_currencies(self):
        self.supported_currency_codes |= {'USD', 'EUR'} # already added
        # In order we want to list them
        self.register_currency(
            'GBP', 'U.K. pound sterling',
            start_date=date(1998, 1, 2), start_rate=2.3397, latest_rate=1.5349, priority=3)
        self.register_currency(
            'AUD', 'Australian dollar',
            start_date=date(1998, 1, 2), start_rate=0.9267, latest_rate=0.9336, priority=5)
        self.register_currency(
            'JPY', 'Japanese yen',
            exponent=0, start_date=date(1998, 1, 2), start_rate=0.01076, latest_rate=0.01076, priority=6)
        self.register_currency(
            'INR', 'Indian rupee',
            start_date=date(1998, 1, 2), start_rate=0.03627, latest_rate=0.02273, priority=7)
        self.register_currency(
            'NZD', 'New Zealand dollar',
            start_date=date(1998, 1, 2), start_rate=0.8225, latest_rate=0.7257, priority=8)
        self.register_currency(
            'CHF', 'Swiss franc',
            start_date=date(1998, 1, 2), start_rate=0.9717, latest_rate=0.9273, priority=9)
        self.register_currency(
            'ZAR', 'South African rand',
            start_date=date(1998, 1, 2), start_rate=0.292, latest_rate=0.1353, priority=10)
        # The rest, alphabetical
        self.register_currency(
            'AED', 'U.A.E. dirham',
            start_date=date(2007, 9, 4), start_rate=0.2858, latest_rate=0.2757)
        self.register_currency(
            'ARS', 'Argentine peso',
            start_date=date(1998, 1, 2), start_rate=1.4259, latest_rate=0.2589)
        self.register_currency(
            'BRL', 'Brazilian real',
            start_date=date(1998, 1, 2), start_rate=1.2707, latest_rate=0.5741)
        self.register_currency(
            'BSD', 'Bahamian dollar',
            start_date=date(1998, 1, 2), start_rate=1.425, latest_rate=1.0128)
        self.register_currency(
            'CLP', 'Chilean peso',
            exponent=0, start_date=date(1998, 1, 2), start_rate=0.003236, latest_rate=0.001923)
        self.register_currency(
            'CNY', 'Chinese renminbi',
            start_date=date(1998, 1, 2), start_rate=0.1721, latest_rate=0.1484)
        self.register_currency(
            'COP', 'Colombian peso',
            start_date=date(1998, 1, 2), start_rate=0.00109, latest_rate=0.000513)
        self.register_currency(
            'CZK', 'Czech Republic koruna',
            start_date=date(1998, 2, 2), start_rate=0.04154, latest_rate=0.05202)
        self.register_currency(
            'DKK', 'Danish krone',
            start_date=date(1998, 1, 2), start_rate=0.2075, latest_rate=0.1785)
        self.register_currency(
            'FJD', 'Fiji dollar',
            start_date=date(1998, 1, 2), start_rate=0.9198, latest_rate=0.5235)
        self.register_currency(
            'GHS', 'Ghanaian cedi',
            start_date=date(2007, 7, 3), start_rate=1.1397, latest_rate=0.7134)
        self.register_currency(
            'GTQ', 'Guatemalan quetzal',
            start_date=date(2004, 12, 21), start_rate=0.15762, latest_rate=0.1264)
        self.register_currency(
            'HKD', 'Hong Kong dollar',
            start_date=date(1998, 1, 2), start_rate=0.1838, latest_rate=0.130385)
        self.register_currency(
            'HNL', 'Honduran lempira',
            start_date=date(1998, 1, 2), start_rate=0.108, latest_rate=0.0536)
        self.register_currency(
            'HRK', 'Croatian kuna',
            start_date=date(2002, 3, 1), start_rate=0.1863, latest_rate=0.1837)
        self.register_currency(
            'HUF', 'Hungarian forint',
            start_date=date(1998, 2, 2), start_rate=0.007003, latest_rate=0.00493)
        self.register_currency(
            'IDR', 'Indonesian rupiah',
            start_date=date(1998, 2, 2), start_rate=0.000145, latest_rate=0.000112)
        self.register_currency(
            'ILS', 'Israeli new shekel',
            start_date=date(1998, 1, 2), start_rate=0.4021, latest_rate=0.2706)
        self.register_currency(
            'ISK', 'Icelandic krona',
            exponent=0, start_date=date(1998, 1, 2), start_rate=0.01962, latest_rate=0.00782)
        self.register_currency(
            'JMD', 'Jamaican dollar',
            start_date=date(2001, 6, 25), start_rate=0.03341, latest_rate=0.01145)
        self.register_currency(
            'KRW', 'South Korean won',
            exponent=0, start_date=date(1998, 1, 2), start_rate=0.000841, latest_rate=0.000905)
        self.register_currency(
            'LKR', 'Sri Lanka rupee',
            start_date=date(1998, 1, 2), start_rate=0.02304, latest_rate=0.0089)
        self.register_currency(
            'MAD', 'Moroccan dirham',
            start_date=date(1998, 1, 2), start_rate=0.1461, latest_rate=0.1195)
        self.register_currency(
            'MMK', 'Myanmar (Burma) kyat',
            start_date=date(1998, 1, 2), start_rate=0.226, latest_rate=0.1793)
        self.register_currency(
            'MXN', 'Mexican peso',
            start_date=date(1998, 1, 2), start_rate=0.1769, latest_rate=0.08156)
        self.register_currency(
            'MYR', 'Malaysian ringgit',
            start_date=date(1998, 1, 2), start_rate=0.3594, latest_rate=0.3149)
        self.register_currency(
            'NOK', 'Norwegian krone',
            start_date=date(1998, 1, 2), start_rate=0.1934, latest_rate=0.1689)
        self.register_currency(
            'PAB', 'Panamanian balboa',
            start_date=date(1998, 1, 2), start_rate=1.425, latest_rate=1.0128)
        self.register_currency(
            'PEN', 'Peruvian new sol',
            start_date=date(1998, 1, 2), start_rate=0.5234, latest_rate=0.3558)
        self.register_currency(
            'PHP', 'Philippine peso',
            start_date=date(1998, 1, 2), start_rate=0.0345, latest_rate=0.02262)
        self.register_currency(
            'PKR', 'Pakistan rupee',
            start_date=date(1998, 1, 2), start_rate=0.03238, latest_rate=0.01206)
        self.register_currency(
            'PLN', 'Polish zloty',
            start_date=date(1998, 2, 2), start_rate=0.4108, latest_rate=0.3382)
        self.register_currency(
            'RON', 'Romanian new leu',
            start_date=date(2007, 9, 4), start_rate=0.4314, latest_rate=0.3215)
        self.register_currency(
            'RSD', 'Serbian dinar',
            start_date=date(2007, 9, 4), start_rate=0.0179, latest_rate=0.01338)
        self.register_currency(
            'RUB', 'Russian rouble',
            start_date=date(1998, 1, 2), start_rate=0.2375, latest_rate=0.03443)
        self.register_currency(
            'SEK', 'Swedish krona',
            start_date=date(1998, 1, 2), start_rate=0.1787, latest_rate=0.1378)
        self.register_currency(
            'SGD', 'Singapore dollar',
            start_date=date(1998, 1, 2), start_rate=0.84, latest_rate=0.7358)
        self.register_currency(
            'THB', 'Thai baht',
            start_date=date(1998, 1, 2), start_rate=0.0296, latest_rate=0.03134)
        self.register_currency(
            'TND', 'Tunisian dinar',
            exponent=3, start_date=date(1998, 1, 2), start_rate=1.2372, latest_rate=0.7037)
        self.register_currency(
            'TWD', 'Taiwanese new dollar',
            start_date=date(1998, 1, 2), start_rate=0.04338, latest_rate=0.03218)
        self.register_currency(
            'VEF', 'Venezuelan bolivar fuerte',
            start_date=date(2008, 1, 2), start_rate=0.4623, latest_rate=0.2358)
        self.register_currency(
            'VND', 'Vietnamese dong',
            start_date=date(2004, 1, 1), start_rate=8.2e-05, latest_rate=5.3e-05)
        self.register_currency(
            'XAF', 'CFA franc',
            exponent=0, start_date=date(1998, 1, 2), start_rate=0.002362, latest_rate=0.002027)
        self.register_currency(
            'XCD', 'East Caribbean dollar',
            start_date=date(1998, 1, 2), start_rate=0.5278, latest_rate=0.3793)
        self.register_currency(
            'XPF', 'CFP franc',
            exponent=0, start_date=date(1998, 1, 2), start_rate=0.01299, latest_rate=0.01114)

    @staticmethod
    def _load(url):
        try:
            with urlopen(url) as response:
                contents = response.read().decode('ascii')
                return json.loads(contents)
        except Exception:
            raise RateProviderUnavailable()

    @staticmethod
    def _parse(json_item, key):
        date = datetime.strptime(json_item['d'], '%Y-%m-%d').date()
        try:
            value = float(json_item[key]['v'])
        except (ValueError, KeyError):
            # Cover our ass in cases where we don't have proper keys or values
            value = None
        return (date, value)

    def get_historical_rates(self, currency_code, start_date, end_date):
        boc_code = CURRENCY2BOCID[currency_code]
        url = 'https://www.bankofcanada.ca/valet/observations/{}/json?start_date={}&end_date={}'.format(
            boc_code,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
        )
        results = self._load(url)

        try:
            return [self._parse(item, boc_code) for item in results['observations']]
        except Exception:
            raise RateProviderUnavailable()


    def get_currency_rates(self, currency_code, start_date, end_date):
        if start_date.year < 2017:
            return self.get_historical_rates(currency_code, start_date, end_date)
        url = 'http://www.bankofcanada.ca/valet/observations/FX{}CAD/json?start_date={}&end_date={}'.format(
            currency_code,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
        )
        results = self._load(url)
        key = 'FX{}CAD'.format(currency_code)
        try:
            return [self._parse(item, key) for item in results['observations']]
        except Exception:
            raise RateProviderUnavailable()

