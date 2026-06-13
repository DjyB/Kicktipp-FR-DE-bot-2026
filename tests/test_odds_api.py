import json
from types import SimpleNamespace

import requests

from kicktipp_bot.core.odds_api import OddsAPI


class MockResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


def test_get_quotes_matches_french_names(monkeypatch):
    # ensure API key present for the function to attempt API calls
    monkeypatch.setenv('KICKTIPP_ODDS_API_KEY', 'dummy-key')
    # Prepare a fake API response matching United States vs Mexico
    fake_events = [
        {
            'home_team': 'United States',
            'away_team': 'Mexico',
            'bookmakers': [
                {
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'United States', 'price': 1.8},
                                {'name': 'Draw', 'price': 3.5},
                                {'name': 'Mexico', 'price': 4.2},
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    def mock_get(*args, **kwargs):
        return MockResponse(fake_events, status=200)

    monkeypatch.setattr(requests, 'get', mock_get)
    quotes = OddsAPI.get_quotes('États-Unis', 'Mexique')
    assert quotes == ['1.80', '3.50', '4.20']
