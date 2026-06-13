"""Configuration module for Kicktipp Bot."""

import os
from datetime import timedelta
from typing import Optional


class Config:
    """Configuration class containing all environment variables and constants."""

    # Base URLs
    BASE_URL = "https://www.kicktipp.fr/"
    LOGIN_URL = "https://www.kicktipp.fr/info/profil/login/"

    # Required environment variables
    EMAIL: Optional[str] = os.getenv("KICKTIPP_EMAIL")
    PASSWORD: Optional[str] = os.getenv("KICKTIPP_PASSWORD")
    NAME_OF_COMPETITION: Optional[str] = os.getenv(
        "KICKTIPP_NAME_OF_COMPETITION")

    # Optional environment variables with defaults
    RUN_EVERY_X_MINUTES: Optional[int] = int(
        os.getenv("KICKTIPP_RUN_EVERY_X_MINUTES", "60"))
    OVERWRITE_TIPS: Optional[bool] = os.getenv("OVERWRITE_TIPS", "false").lower() == "true"

    # Chrome driver path
    CHROMEDRIVER_PATH: Optional[str] = os.getenv("CHROMEDRIVER_PATH")

    # Optional Kicktipp round navigation
    SPIELTAG_INDEX: Optional[int] = None
    SPIELTAG_INDEX_START: Optional[int] = None
    SPIELTAG_INDEX_END: Optional[int] = None
    try:
        spieltag_value = os.getenv("KICKTIPP_SPIELTAG_INDEX")
        SPIELTAG_INDEX = int(spieltag_value) if spieltag_value is not None else None
    except ValueError:
        SPIELTAG_INDEX = None

    try:
        start_value = os.getenv("KICKTIPP_SPIELTAG_INDEX_START")
        SPIELTAG_INDEX_START = int(start_value) if start_value is not None else None
    except ValueError:
        SPIELTAG_INDEX_START = None

    try:
        end_value = os.getenv("KICKTIPP_SPIELTAG_INDEX_END")
        SPIELTAG_INDEX_END = int(end_value) if end_value is not None else None
    except ValueError:
        SPIELTAG_INDEX_END = None

    # Time configuration
    HOURS_UNTIL_GAME: Optional[int] = int(
        os.getenv("KICKTIPP_HOURS_UNTIL_GAME", "2"))
    TIME_UNTIL_GAME: timedelta = timedelta(hours=HOURS_UNTIL_GAME)

    # Notification URLs
    ZAPIER_URL: Optional[str] = os.getenv("ZAPIER_URL")
    NTFY_URL: Optional[str] = os.getenv("NTFY_URL")
    NTFY_USERNAME: Optional[str] = os.getenv("NTFY_USERNAME")
    NTFY_PASSWORD: Optional[str] = os.getenv("NTFY_PASSWORD")
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL")
    GROUP_NOTIFICATIONS: bool = os.getenv("GROUP_NOTIFICATIONS", "false").lower() == "true"

    @classmethod
    def validate_required_config(cls) -> bool:
        """Validate that all required configuration is present."""
        required_vars = [cls.EMAIL, cls.PASSWORD, cls.NAME_OF_COMPETITION]
        return all(var is not None for var in required_vars)

    @classmethod
    def get_tipp_url(cls, spieltag_index: Optional[int] = None) -> str:
        """Get the URL for the tipping page."""
        url = f"https://www.kicktipp.fr/{cls.NAME_OF_COMPETITION}/tippabgabe"
        index = spieltag_index if spieltag_index is not None else cls.SPIELTAG_INDEX
        if index is not None:
            url += f"?spieltagIndex={index}"
        return url
