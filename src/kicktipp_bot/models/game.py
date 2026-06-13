"""Game model for representing football matches and calculating betting tips."""

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple, Union


@dataclass
class Game:
    """Represents a football game with teams, betting quotes, and tip calculation logic."""

    home_team: str
    away_team: str
    quotes: List[str]
    game_time: datetime
    _validated_quotes: List[float] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        """Validate and process data after initialization."""
        self.home_team = self.home_team.strip()
        self.away_team = self.away_team.strip()
        self._validated_quotes = self._validate_quotes(self.quotes)

    def _validate_quotes(self, quotes: List[str]) -> List[float]:
        """
        Validate and convert quotes to float values.

        Args:
            quotes: List of quote strings

        Returns:
            List of float quotes

        Raises:
            ValueError: If quotes are invalid
        """
        if len(quotes) != 3:
            raise ValueError(f"Expected 3 quotes, got {len(quotes)}")

        try:
            return [float(quote) for quote in quotes]
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid quote values: {quotes}") from e

    def calculate_tip(self, home_quote: Union[float, None] = None, away_quote: Union[float, None] = None) -> Tuple[int, int]:
        """
        Calculate betting tip based on the quotes.

        Args:
            home_quote: Quote for home team win (uses self._validated_quotes[0] if None)
            away_quote: Quote for away team win (uses self._validated_quotes[2] if None)

        Returns:
            Tuple of (home_goals, away_goals) prediction
        """
        try:
            if home_quote is None:
                home_q = float(self._validated_quotes[0])
            else:
                home_q = float(home_quote)
            if away_quote is None:
                away_q = float(self._validated_quotes[2])
            else:
                away_q = float(away_quote)
            draw_q = float(self._validated_quotes[1])

            # Determine favorite (lowest price)
            prices = {'home': home_q, 'draw': draw_q, 'away': away_q}
            fav = min(prices, key=prices.get)

            # If draw is the favourite or very close, predict a draw
            if fav == 'draw' or abs(draw_q - min(home_q, away_q)) <= 0.05:
                return (1, 1)

            # Favorite is a team
            if fav == 'home':
                fav_q = home_q
                opp_q = away_q
                # ratio of opponent price to favourite price
                ratio = opp_q / fav_q if fav_q > 0 else 1
                if ratio >= 5:
                    return (3, 0)
                if ratio >= 2.5:
                    return (2, 0)
                if ratio >= 1.5:
                    return random.choice([(2, 1), (1, 0)])
                return random.choice([(2, 1), (1, 1)])
            else:
                # away favourite
                fav_q = away_q
                opp_q = home_q
                ratio = opp_q / fav_q if fav_q > 0 else 1
                if ratio >= 5:
                    return (0, 3)
                if ratio >= 2.5:
                    return (0, 2)
                if ratio >= 1.5:
                    return random.choice([(1, 2), (0, 1)])
                return random.choice([(1, 2), (1, 1)])
        except Exception:
            # On any parsing or unexpected error, return safe fallback
            return (2, 1)

    def __str__(self) -> str:
        """String representation of the game."""
        return f"{self.home_team} vs {self.away_team} at {self.game_time.strftime('%d.%m.%y %H:%M')}"
