"""Game tipping module for handling the core betting logic."""

import logging
import os
import re
import requests
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from time import sleep
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException

from ..config import Config
from ..models.game import Game
from .notifications import NotificationManager
from ..utils.selenium_utils import SeleniumUtils
from .table_processors import TimeExtractor, TableRowProcessor, GameDataExtractor
from .odds_api import OddsAPI
from pathlib import Path

logger = logging.getLogger(__name__)


def send_jbprod_notification(equipe_a, equipe_b, cote_a, cote_b, score_a, score_b):
    """Envoie une notification push via l'API JBProd"""
    api_token = os.environ.get('JBPROD_API_TOKEN')
    if not api_token:
        logging.warning("JBPROD_API_TOKEN manquant dans les variables d'environnement. Notification ignorée.")
        return

    url = 'https://push.jbprod.fr/send_notification.php'
    
    # Formatage sécurisé au cas où les cotes sont absentes (fallback)
    str_cote_a = str(cote_a) if cote_a else "N/A"
    str_cote_b = str(cote_b) if cote_b else "N/A"

    data = {
        'title': f'Kicktipp effectué : {equipe_a} vs {equipe_b}',
        'body': f'{equipe_a} ({str_cote_a}) {score_a} - {score_b} ({str_cote_b}) {equipe_b}'
    }

    headers = {
        'Content-Type': 'application/json',
        'X-Api-Token': api_token
    }

    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            logging.info("Notification push envoyée avec succès !")
        else:
            logging.error(f"Échec de la notification push : {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi de la notification push : {str(e)}")


class GameTippingError(Exception):
    """Custom exception for game tipping failures."""
    pass


class GameTipper:
    """Handles the core game tipping functionality."""

    def __init__(self, driver: WebDriver, notification_manager: NotificationManager):
        self.driver = driver
        self.notification_manager = notification_manager
        self.table_processor = TableRowProcessor(driver)
        # State management
        self.last_seen_time = None
        self.processed_count = 0
        self.game_number = 0

    def tip_all_games(self) -> None:
        """Process and tip all available games."""
        logger.info("Starting game tipping process")

        try:
            # Determine the range of days to process
            if Config.SPIELTAG_INDEX_START is not None and Config.SPIELTAG_INDEX_END is not None:
                start_day = Config.SPIELTAG_INDEX_START
                end_day = Config.SPIELTAG_INDEX_END
                if start_day > end_day:
                    logger.warning(
                        f"KICKTIPP_SPIELTAG_INDEX_START ({start_day}) > KICKTIPP_SPIELTAG_INDEX_END ({end_day}), swapping values"
                    )
                    start_day, end_day = end_day, start_day
                day_indices = range(start_day, end_day + 1)
            elif Config.SPIELTAG_INDEX is not None:
                day_indices = [Config.SPIELTAG_INDEX]
            else:
                day_indices = [None]

            total_processed = 0
            for day_index in day_indices:
                url = Config.get_tipp_url(day_index)
                if day_index is not None:
                    logger.info(f"Opening tipping page for spieltagIndex={day_index}")
                else:
                    logger.info("Opening tipping page")

                self.driver.get(url)

                # Wait for page to load
                if not SeleniumUtils.wait_for_page_load(self.driver):
                    raise GameTippingError("Tipping page failed to load")

                # Additional wait for dynamic content
                sleep(1)

                # Accept terms and conditions if they appear on the tipping page
                self._accept_terms_and_conditions()

                # Capture a screenshot for debugging after the tipping grid is loaded
                screenshot_name = f"debug-{day_index if day_index is not None else 'default'}.png"
                self._save_debug_screenshot(screenshot_name)

                # Get the number of games available
                games_count = self._get_games_count()
                if games_count == 0:
                    logger.warning("No games found to process - this could mean:")
                    logger.warning("  - No games are available for tipping")
                    logger.warning("  - Page structure has changed")
                    logger.warning("  - Terms dialog is still blocking content")
                    continue

                logger.info(f"Found {games_count} games to process")

                # Process games using sequential row processing approach
                self._reset_state()
                self._process_all_table_rows()
                total_processed += self.processed_count

                # Submit all tips for this day
                self._submit_all_tips()

            logger.info(f"Processed {total_processed} games successfully")

            # Debug mode sleep
            if self._is_debug_mode() and Config.RUN_EVERY_X_MINUTES != 0:
                logger.info(
                    "Local debug mode - sleeping for 20 seconds to review results")
                sleep(20)

        except GameTippingError:
            raise
        except WebDriverException as e:
            raise GameTippingError(f"WebDriver error during tipping: {e}")
        except Exception as e:
            raise GameTippingError(f"Unexpected error during tipping: {e}")
        finally:
            # Always send grouped notifications at the end, even if errors occurred
            # This ensures collected events are sent and pending_events is cleared
            self.notification_manager.send_grouped_notifications()

    def _reset_state(self) -> None:
        """Reset processing state for a new run."""
        self.last_seen_time = None
        self.processed_count = 0
        self.game_number = 0
        logger.debug("Reset processing state")

    def _save_debug_screenshot(self, filename: str) -> None:
        """Save a screenshot of the current page for headless debugging."""
        try:
            screenshot_path = Path.cwd() / filename
            if self.driver.save_screenshot(str(screenshot_path)):
                logger.info(f"Saved debug screenshot to {screenshot_path}")
            else:
                logger.warning(f"Failed to save debug screenshot to {screenshot_path}")
        except Exception as e:
            logger.warning(f"Error capturing debug screenshot: {e}")

    def _update_last_seen_time(self, new_time: datetime, source: str) -> None:
        """Update the last seen time and log the change."""
        self.last_seen_time = new_time
        logger.debug(
            f"Updated time from {source}: {self.last_seen_time.strftime('%d.%m.%y %H:%M')}")

    def _get_games_count(self) -> int:
        """Get the number of games available for tipping."""
        logger.debug("Counting available games")

        # Try to find the games table first
        table = SeleniumUtils.safe_find_element(
            self.driver, By.ID, "tippabgabeSpiele")
        if not table:
            logger.warning("Could not find tipping table (tippabgabeSpiele)")
            return 0

        # Count only datarow elements (actual games, not rowheaders)
        games = SeleniumUtils.safe_find_elements(
            self.driver, By.XPATH, '//*[@id="tippabgabeSpiele"]/tbody/tr[contains(@class, "datarow")]')
        count = len(games)
        logger.debug(f"Found {count} game rows with class 'datarow'")

        # If no datarow elements, try alternative selectors
        if count == 0:
            logger.debug(
                "No 'datarow' elements found, trying alternative selectors")
            # Try finding table rows in the tipping table
            table_rows = SeleniumUtils.safe_find_elements(
                self.driver, By.XPATH, '//*[@id="tippabgabeSpiele"]//tr')
            logger.debug(f"Found {len(table_rows)} total table rows")

            # Filter out header rows (usually first row)
            if len(table_rows) > 1:
                count = len(table_rows) - 1  # Subtract header row
                logger.debug(f"Adjusted count after removing header: {count}")

        return count

    def _process_all_table_rows(self) -> int:
        """Process all table rows sequentially, maintaining time state."""
        logger.debug("Processing table rows sequentially")

        all_rows = self.table_processor.get_all_table_rows()
        if not all_rows:
            logger.warning("No table rows found")
            return 0

        for row_index, _ in enumerate(all_rows):
            try:
                row, row_class = self.table_processor.get_row_safely(
                    all_rows, row_index)
                if row is None or row_class is None:
                    continue

                if 'rowheader' in row_class:
                    self._process_rowheader(row, row_index)
                elif 'datarow' in row_class:
                    self._process_datarow_wrapper(row, row_index)

            except Exception as e:
                logger.error(f"Error processing table row {row_index}: {e}")
                continue

        logger.info(f"Processed {self.processed_count} games successfully")
        return self.processed_count

    def _process_rowheader(self, row, row_index: int) -> None:
        """Process a rowheader row to extract time information."""
        logger.debug(f"Found rowheader row {row_index}")
        extracted_time = TimeExtractor.extract_from_rowheader(row)
        if extracted_time:
            self._update_last_seen_time(extracted_time, "rowheader")
        else:
            logger.debug("Could not extract time from rowheader")

    def _process_datarow_wrapper(self, row, row_index: int) -> None:
        """Process a datarow wrapper that handles time state management."""
        self.game_number += 1
        logger.debug(
            f"Processing datarow {self.game_number} (row {row_index}), "
            f"last_seen_time: {self.last_seen_time.strftime('%d.%m.%y %H:%M') if self.last_seen_time else 'None'}")

        # Get time for this game
        game_time = TimeExtractor.extract_from_datarow(
            row, self.last_seen_time)

        # Update last_seen_time if we found a visible time in this datarow
        if TimeExtractor.has_visible_time(row):
            self._update_last_seen_time(game_time, "datarow")

        # Process the actual game
        if self._process_datarow(self.game_number, row, game_time):
            self.processed_count += 1

    def _process_datarow(self, game_number: int, data_row, game_time: datetime) -> bool:
        """Process a single game datarow."""
        try:
            # Extract team names using the extractor
            home_team = GameDataExtractor.extract_team_name(
                data_row, 2, 'home')
            away_team = GameDataExtractor.extract_team_name(
                data_row, 3, 'away')

            if not home_team or not away_team:
                logger.warning(
                    f"Could not extract team names for game {game_number}")
                return False

            logger.info(
                f"Processing: {home_team} vs {away_team} | Time: {game_time.strftime('%d.%m.%y %H:%M')}")


            # Check if the game has already started (timezone-safe, zoneinfo)  
            now_berlin = datetime.now(ZoneInfo('Europe/Berlin'))
            if game_time <= now_berlin:
                logger.info(f"Game {game_number} has already started ({game_time.strftime('%d.%m.%y %H:%M %z')}). Skipping...")
                return False

            # Get tip fields using the new extractor
            tip_fields = GameDataExtractor.get_tip_fields(data_row)
            if not tip_fields:
                logger.debug(
                    f"Game {game_number} cannot be tipped (likely finished)")
                return False

            home_tip_field, away_tip_field = tip_fields

            # Check if already tipped
            if not Config.OVERWRITE_TIPS and self._is_already_tipped(home_tip_field, away_tip_field):
                home_val = SeleniumUtils.safe_get_attribute(
                    home_tip_field, 'value', 'home tip field') or ''
                away_val = SeleniumUtils.safe_get_attribute(
                    away_tip_field, 'value', 'away tip field') or ''
                logger.info(f"Game already tipped: {home_val} - {away_val}")
                return False

            # Check timing constraints
            if not self._should_tip_game(game_time):
                return False

            # Use OddsAPI single-request flow to get a tip (strict fallback to (2,1))
            try:
                tip, quotes = OddsAPI.get_score(home_team, away_team)
                logger.info(f"Using tip from Odds API for game {game_number}: {tip[0]} - {tip[1]}")
            except Exception as e:
                logger.warning(f"Odds API error for {home_team} vs {away_team}: {e}; using fallback tip")
                tip = (2, 1)
                quotes = None

            # Enter tip and send notifications
            if self._enter_tip(home_tip_field, away_tip_field, tip):
                try:
                    self.notification_manager.send_all_notifications(
                        game_time, home_team, away_team, quotes or GameDataExtractor.FALLBACK_QUOTES, tip
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to send notifications for game {game_number}: {e}")

                # Send JBProd notification for every successfully entered tip
                send_jbprod_notification(
                    home_team,
                    away_team,
                    quotes[0] if quotes else None,
                    quotes[2] if quotes else None,
                    tip[0],
                    tip[1]
                )
                return True
            else:
                logger.error(f"Failed to enter tip for game {game_number}")
                return False

        except Exception as e:
            logger.error(f"Error processing game {game_number}: {e}")
            return False

    def _is_already_tipped(self, home_field, away_field) -> bool:
        """Check if the game has already been tipped."""
        home_value = SeleniumUtils.safe_get_attribute(
            home_field, 'value', 'home tip field') or ''
        away_value = SeleniumUtils.safe_get_attribute(
            away_field, 'value', 'away tip field') or ''
        return bool(home_value and away_value)

    def _should_tip_game(self, game_time: datetime) -> bool:
        """Check if the game should be tipped based on timing."""
        time_until_game = game_time - datetime.now(ZoneInfo('Europe/Berlin'))
        logger.debug(f"Time until game: {time_until_game}")

        if time_until_game > Config.TIME_UNTIL_GAME:
            logger.info(
                f"Game starts in more than {Config.TIME_UNTIL_GAME}. Skipping...")
            return False

        logger.info(
            f"Game starts in less than {Config.TIME_UNTIL_GAME}. Proceeding with tip...")
        return True

    def _enter_tip(self, home_field, away_field, tip: tuple) -> bool:
        """
        Enter the calculated tip into the form fields.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Enter home team tip
            if not SeleniumUtils.safe_send_keys(home_field, str(tip[0]), "home tip field"):
                logger.error("Failed to enter home team tip")
                return False

            # Enter away team tip
            if not SeleniumUtils.safe_send_keys(away_field, str(tip[1]), "away tip field"):
                logger.error("Failed to enter away team tip")
                return False

            logger.info(f"Successfully entered tip: {tip[0]} - {tip[1]}")
            return True

        except Exception as e:
            logger.error(f"Unexpected error entering tip: {e}")
            return False

    def _submit_all_tips(self) -> None:
        """Submit all entered tips."""
        logger.info("Submitting tips form")

        # Wait a moment for any dynamic updates to the form
        sleep(1)

        submit_button = SeleniumUtils.safe_find_element(
            self.driver, By.NAME, "submitbutton")
        if not submit_button:
            logger.error(
                "Could not find submit button with name 'submitbutton'")
            raise GameTippingError("Submit button not found")

        logger.debug("Found submit button, attempting to click")

        # Try to scroll the button into view first
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", submit_button)
            sleep(0.5)  # Brief pause after scrolling
            logger.debug("Scrolled submit button into view")
        except Exception as e:
            logger.debug(f"Could not scroll to submit button: {e}")

        # Try regular click first
        if SeleniumUtils.safe_click(submit_button, "submit button"):
            logger.info("Tips form submitted successfully")
        else:
            # Fallback to JavaScript click
            logger.info("Regular click failed, trying JavaScript click")
            try:
                self.driver.execute_script(
                    "arguments[0].click();", submit_button)
                logger.info("Tips form submitted successfully via JavaScript")
            except Exception as e:
                logger.error(f"Both regular and JavaScript clicks failed: {e}")
                raise GameTippingError("Failed to submit tips form")

    def _is_debug_mode(self) -> bool:
        """Check if running in debug mode."""
        try:
            return len(sys.argv) > 1 and '--debug' in sys.argv
        except IndexError:
            return False

    def _accept_terms_and_conditions(self) -> None:
        """Accept terms and conditions if the dialog appears on the tipping page."""
        logger.debug("Checking for terms and conditions dialog")

        # Look for SourcePoint iframe (where the terms dialog actually is)
        try:
            iframes = self.driver.find_elements(
                By.CSS_SELECTOR, 'iframe[id*="sp_message_iframe"]'
            )
        except Exception as e:
            logger.debug(f"Error searching for terms iframe: {e}")
            iframes = []

        iframe = iframes[0] if iframes else None

        if iframe:
            try:
                # Switch to iframe and find accept button
                self.driver.switch_to.frame(iframe)
                sleep(1)  # Brief wait for iframe content

                accept_button = SeleniumUtils.safe_find_element(
                    self.driver,
                    By.XPATH,
                    '//button[contains(text(), "Akzeptieren") or contains(text(), "Accepter")]',
                    timeout=2
                )

                if accept_button and SeleniumUtils.safe_click(accept_button, "terms accept button"):
                    logger.info("Terms and conditions accepted successfully")

                # Always switch back to main content
                self.driver.switch_to.default_content()

            except Exception as e:
                logger.warning(f"Error handling terms dialog: {e}")
                # Ensure we switch back to main content
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
        else:
            logger.debug("No terms dialog found - may already be accepted")
