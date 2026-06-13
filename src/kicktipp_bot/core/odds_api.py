"""Odds API client for fetching h2h odds from the-odds-api.com."""

import json
import logging
import os
import re
import requests
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional

logger = logging.getLogger(__name__)

# Read API key from environment for security
API_KEY = os.getenv('KICKTIPP_ODDS_API_KEY')
if not API_KEY:
    logger.warning('KICKTIPP_ODDS_API_KEY not set; Odds API calls will be skipped')

# Optional Odds API configuration from environment
ODDS_API_SPORT_KEY = os.getenv('KICKTIPP_ODDS_API_SPORT_KEY', 'soccer_fifa_world_cup')
ODDS_API_REGIONS = os.getenv('KICKTIPP_ODDS_API_REGIONS', 'fr')
ODDS_API_FALLBACK_SPORT_KEYS = [
    key.strip() for key in os.getenv('KICKTIPP_ODDS_API_SPORT_KEYS', 'soccer').split(',') if key.strip()
]

# Candidate sport keys to try if fallback logic is still used
SPORT_KEYS = ODDS_API_FALLBACK_SPORT_KEYS


def _discover_soccer_sports() -> List[str]:
    """Discover available soccer-related sport keys from the Odds API.

    Returns a list of sport keys (fallback to SPORT_KEYS on error).
    """
    if not API_KEY:
        logger.debug("Skipping sports discovery because API key is not configured")
        return SPORT_KEYS
    url = f"https://api.the-odds-api.com/v4/sports?apiKey={API_KEY}"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            logger.warning(f"Could not discover sports, status {resp.status_code}")
            return SPORT_KEYS
        data = resp.json()
        keys = []
        for s in data:
            key = s.get('key', '')
            title = s.get('title', '')
            group = s.get('group', '')
            low = (key + ' ' + title + ' ' + str(group)).lower()
            if 'soccer' in low or 'football' in low:
                keys.append(key)
        # Ensure at least the default
        return keys or SPORT_KEYS
    except Exception as e:
        logger.warning(f"Error discovering sports keys: {e}")
        return SPORT_KEYS

TEAM_MAPPING = {
    "Mexique": "Mexico", "Corée du Sud": "South Korea", "République Tchèque": "Czech Republic",
    "Afrique du Sud": "South Africa", "Bosnien-Herzegowina": "Bosnia & Herzegovina", "Canada": "Canada",
    "Qatar": "Qatar", "Suisse": "Switzerland", "Brésil": "Brazil", "Haïti": "Haiti",
    "Maroc": "Morocco", "Écosse": "Scotland", "États-Unis": "USA", "Australie": "Australia",
    "Turquie": "Turkey", "Paraguay": "Paraguay", "Curaçao": "Curaçao", "Allemagne": "Germany",
    "Équateur": "Ecuador", "Côte d'Ivoire": "Ivory Coast", "Japon": "Japan", "Pays-Bas": "Netherlands",
    "Suède": "Sweden", "Tunisie": "Tunisia", "Égypte": "Egypt", "Belgique": "Belgium",
    "Iran": "Iran", "Nouvelle-Zélande": "New Zealand", "Cap-Vert": "Cape Verde",
    "Arabie saoudite": "Saudi Arabia", "Espagne": "Spain", "Uruguay": "Uruguay",
    "France": "France", "Irak": "Iraq", "Norvège": "Norway", "Sénégal": "Senegal",
    "Algérie": "Algeria", "Argentine": "Argentina", "Jordanie": "Jordan", "Autriche": "Austria",
    "RD Congo": "DR Congo", "Colombie": "Colombia", "Portugal": "Portugal",
    "Ouzbékistan": "Uzbekistan", "Angleterre": "England", "Ghana": "Ghana",
    "Croatie": "Croatia", "Panama": "Panama"
}


def normalize_string(text: str) -> str:
    """Nettoie, met en minuscules et enlève TOUS les accents."""
    if not text:
        return ""
    # Enlever les textes entre parenthèses et les espaces en trop
    cleaned = re.sub(r"\s*\([^)]*\)", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Enlever les accents
    cleaned = unicodedata.normalize('NFD', cleaned).encode('ascii', 'ignore').decode('utf-8')
    return cleaned.lower()

# Création dynamique d'un dictionnaire où toutes les clés sont sans accent et en minuscules
NORMALIZED_MAPPING = {normalize_string(k): v for k, v in TEAM_MAPPING.items()}


def translate_team_name(kicktipp_name: str) -> str:
    """Traduit le nom Kicktipp en nom API The Odds"""
    normalized_name = normalize_string(kicktipp_name)
    translated = NORMALIZED_MAPPING.get(normalized_name, kicktipp_name)
    return translated


def map_to_api_name(name: str) -> str:
    """Map a French Kicktipp team name to the Odds API English name if known."""
    if not name:
        return ''
    return translate_team_name(name)


def translate_name(name: str) -> str:
    """Translate a team name using normalized mapping."""
    if not name:
        return ''
    return translate_team_name(name)


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    # Remove accents, lower-case and strip
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = nfkd.encode('ascii', 'ignore').decode('ascii')
    return ascii_name.lower().replace("\u2019", "'").strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class OddsAPI:
    """Simple wrapper around the-odds-api for H2H (1X2) market."""

    @staticmethod
    def _fetch_odds_for_sport(sport_key: str, regions: str = 'eu') -> Optional[List[dict]]:
        if not API_KEY:
            # No API key configured; skip calling remote API
            logger.debug("Skipping Odds API fetch because API key is not configured")
            return None
        url = (
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
            f"?regions={regions}&markets=h2h&oddsFormat=decimal&dateFormat=iso&apiKey={API_KEY}"
        )
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Odds API returned status {resp.status_code} for sport {sport_key}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching odds for sport {sport_key}: {e}")
            return None

    @staticmethod
    def _match_event(event: dict, home: str, away: str) -> bool:
        api_home = translate_name(event.get('home_team', ''))
        api_away = translate_name(event.get('away_team', ''))
        home_n = translate_name(home)
        away_n = translate_name(away)

        # Try direct normalized equality
        if home_n == api_home and away_n == api_away:
            return True

        # Try fuzzy similarity both directions
        scores = [
            _similar(home_n, api_home),
            _similar(away_n, api_away),
        ]
        # Accept match if both similarities are reasonably high
        if scores[0] >= 0.7 and scores[1] >= 0.7:
            return True

        # Cross-match (sometimes home/away swapped in naming)
        if _similar(home_n, api_away) >= 0.8 and _similar(away_n, api_home) >= 0.8:
            return True

        return False

    @staticmethod
    def _extract_h2h_from_event(event: dict) -> Optional[List[str]]:
        # The response includes 'bookmakers' -> list -> 'markets' -> list -> 'outcomes'
        try:
            bookmakers = event.get('bookmakers') or []
            if not bookmakers:
                return None
            # Use the first bookmaker and its first h2h market if present
            bm = bookmakers[0]
            markets = bm.get('markets') or []
            if not markets:
                return None
            # Prefer the first market
            market = markets[0]
            outcomes = market.get('outcomes') or []
            if len(outcomes) < 3:
                return None

            # Map outcomes to home/draw/away by name matching
            api_home = _normalize_name(event.get('home_team', ''))
            api_away = _normalize_name(event.get('away_team', ''))

            prices = [None, None, None]
            for o in outcomes:
                name = _normalize_name(o.get('name', ''))
                price = o.get('price')
                if 'draw' in name or name in ('x', 'nul', 'nulle', 'match nul'):
                    prices[1] = price
                elif name == api_home or _similar(name, api_home) >= 0.8:
                    prices[0] = price
                elif name == api_away or _similar(name, api_away) >= 0.8:
                    prices[2] = price
                else:
                    # If ambiguous, try to fill empty slots by order later
                    pass

            # Fill any None by order from outcomes
            for i, o in enumerate(outcomes):
                if prices[i] is None:
                    try:
                        prices[i] = o.get('price')
                    except Exception:
                        prices[i] = None

            if all(p is not None for p in prices):
                return [f"{float(p):.2f}" for p in prices]
            return None
        except Exception as e:
            logger.warning(f"Error extracting h2h from event: {e}")
            return None

    @staticmethod
    def _find_event_in_api(home: str, away: str, events: List[dict]) -> Optional[dict]:
        """Find the matching event in the Odds API response using bidirectional team matching."""
        search_home = _normalize_name(home)
        search_away = _normalize_name(away)

        for event in events:
            api_home = _normalize_name(event.get('home_team', ''))
            api_away = _normalize_name(event.get('away_team', ''))
            logger.info(f"Tentative de correspondance : Kicktipp [{home} vs {away}] avec API [{event.get('home_team', '')} vs {event.get('away_team', '')}]")

            if (search_home == api_home and search_away == api_away) or (search_home == api_away and search_away == api_home):
                logger.info(f"Match trouvé dans l'API pour {home} vs {away} via événement [{event.get('home_team', '')} vs {event.get('away_team', '')}]")
                return event

        return None

    @staticmethod
    def _compute_score_from_quotes(quotes: List[str]) -> tuple:
        try:
            hq, dq, aq = float(quotes[0]), float(quotes[1]), float(quotes[2])
            prices = {'home': hq, 'draw': dq, 'away': aq}
            fav = min(prices, key=prices.get)
            if fav == 'draw' or abs(dq - min(hq, aq)) <= 0.05:
                return (1, 1)
            if fav == 'home':
                ratio = (aq / hq) if hq > 0 else 1
                if ratio >= 5:
                    return (3, 0)
                if ratio >= 2.5:
                    return (2, 0)
                if ratio >= 1.5:
                    return (2, 1)
                return (2, 1)
            ratio = (hq / aq) if aq > 0 else 1
            if ratio >= 5:
                return (0, 3)
            if ratio >= 2.5:
                return (0, 2)
            if ratio >= 1.5:
                return (1, 2)
            return (1, 2)
        except Exception:
            return (2, 1)

    @staticmethod
    def get_score(home: str, away: str) -> tuple:
        """Return a predicted score tuple and quotes list using the Odds API.

        The function calls the exact World Cup endpoint with regions=fr and markets=h2h.
        If the API returns an error (e.g. 422) or no matching event is found, this
        function returns the default fallback score (2, 1) and None for quotes.
        """
        if not API_KEY:
            logger.warning("Odds API key missing; using fallback score")
            return (2, 1), None

        url = (
            f"https://api.the-odds-api.com/v4/sports/{ODDS_API_SPORT_KEY}/odds/"
            f"?apiKey={API_KEY}&regions={ODDS_API_REGIONS}&markets=h2h"
        )
        try:
            resp = requests.get(url, timeout=10)
        except Exception as e:
            logger.warning(f"Odds API request failed: {e}; using fallback score")
            return (2, 1), None

        if resp.status_code == 422:
            logger.warning("Odds API returned 422 for world cup endpoint; using fallback score")
            return (2, 1), None

        if resp.status_code != 200:
            logger.warning(f"Odds API returned status {resp.status_code}; using fallback score")
            return (2, 1), None

        try:
            events = resp.json()
        except Exception as e:
            logger.warning(f"Could not decode Odds API response: {e}; using fallback score")
            return (2, 1), None

        mapped_home = map_to_api_name(home)
        mapped_away = map_to_api_name(away)

        logger.info(f"INFO - Searching API for: [{mapped_home}] vs [{mapped_away}]")

        event = OddsAPI._find_event_in_api(mapped_home, mapped_away, events)
        if not event:
            first_three = events[:3]
            first_three_names = ", ".join(
                f"[{e.get('home_team', '')} vs {e.get('away_team', '')}]" for e in first_three
            )
            logger.info(f"INFO - Aucun match trouvé. Premiers événements API pour comparaison : {first_three_names}")
            logger.info(f"No matching event found in Odds API for {home} vs {away}; using fallback score")
            return (2, 1), None

        quotes = OddsAPI._extract_h2h_from_event(event)
        if not quotes:
            logger.warning(f"Matched event found but could not extract quotes for {home} vs {away}; using fallback score")
            return (2, 1), None

        return OddsAPI._compute_score_from_quotes(quotes), quotes

    @staticmethod
    def get_quotes(home: str, away: str) -> Optional[List[str]]:
        """Return list of quotes [home, draw, away] as strings or None on failure."""
        # First try the user-specified FIFA world cup endpoint with French region
        sport_keys = ['soccer_fifa_world_cup'] + _discover_soccer_sports()
        logger.debug(f"Using sport keys from discovery: {sport_keys}")
        for sport in sport_keys:
            # use regions=fr specifically for world cup key to match user's preference
            regions = 'fr' if sport == 'soccer_fifa_world_cup' else 'eu'
            events = OddsAPI._fetch_odds_for_sport(sport, regions=regions)
            if not events:
                continue
            for event in events:
                if OddsAPI._match_event(event, home, away):
                    quotes = OddsAPI._extract_h2h_from_event(event)
                    if quotes:
                        logger.info(f"Found quotes from API (sport={sport}) for {home} vs {away}: {quotes}")
                        return quotes
        logger.info(f"No matching event found in Odds API for {home} vs {away}")
        return None
