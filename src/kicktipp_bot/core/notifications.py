"""Notification module for sending webhooks and alerts."""

import requests
from datetime import datetime
from typing import List, Tuple, Optional
import logging

from ..config import Config


logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages different types of notifications for game tips."""

    def __init__(self):
        self.zapier_enabled = Config.ZAPIER_URL is not None
        self.ntfy_enabled = all([
            Config.NTFY_URL,
            Config.NTFY_USERNAME,
            Config.NTFY_PASSWORD
        ])
        self.webhook_enabled = Config.WEBHOOK_URL is not None
        self.group_notifications = Config.GROUP_NOTIFICATIONS
        self.pending_events = []

    def send_all_notifications(
        self,
        game_time: datetime,
        home_team: str,
        away_team: str,
        quotes: List[str],
        tip: Tuple[int, int]
    ) -> None:
        """Send all configured notifications."""
        try:
            if self.group_notifications:
                # Collect event for grouped notification
                self._collect_event(game_time, home_team, away_team, quotes, tip)
            else:
                # Send notifications immediately (original behavior)
                if self.zapier_enabled:
                    self._send_zapier_webhook(
                        game_time, home_team, away_team, quotes, tip)

                if self.ntfy_enabled:
                    self._send_ntfy_notification(
                        game_time, home_team, away_team, quotes, tip)

                if self.webhook_enabled:
                    self._send_webhook_notification(
                        game_time, home_team, away_team, quotes, tip)

        except Exception as e:
            logger.error(f"Error sending notifications: {e}")

    def _send_zapier_webhook(
        self,
        game_time: datetime,
        home_team: str,
        away_team: str,
        quotes: List[str],
        tip: Tuple[int, int]
    ) -> None:
        """Send notification to Zapier webhook."""
        try:
            payload = {
                'date': game_time.isoformat(),
                'team1': home_team,
                'team2': away_team,
                'quoteteam1': quotes[0] if len(quotes) > 0 else '',
                'quotedraw': quotes[1] if len(quotes) > 1 else '',
                'quoteteam2': quotes[2] if len(quotes) > 2 else '',
                'tipteam1': tip[0],
                'tipteam2': tip[1]
            }

            response = requests.post(
                Config.ZAPIER_URL,
                data=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Zapier webhook sent successfully")

        except requests.RequestException as e:
            logger.error(f"Failed to send Zapier webhook: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending Zapier webhook: {e}")

    def _send_ntfy_notification(
        self,
        game_time: datetime,
        home_team: str,
        away_team: str,
        quotes: List[str],
        tip: Tuple[int, int]
    ) -> None:
        """Send notification via ntfy service."""
        try:
            title = f"{home_team} - {away_team} tipped {tip[0]}:{tip[1]}"
            message = f"Time: {game_time.strftime('%d.%m.%y %H:%M')}\nQuotes: {quotes}"

            headers = {
                "X-Title": title.encode('utf-8'),
                "Content-Type": "text/plain; charset=utf-8"
            }

            response = requests.post(
                Config.NTFY_URL,
                auth=(Config.NTFY_USERNAME, Config.NTFY_PASSWORD),
                data=message.encode('utf-8'),
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Ntfy notification sent successfully")

        except requests.RequestException as e:
            logger.error(f"Failed to send ntfy notification: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending ntfy notification: {e}")

    def _send_webhook_notification(
        self,
        game_time: datetime,
        home_team: str,
        away_team: str,
        quotes: List[str],
        tip: Tuple[int, int]
    ) -> None:
        """Send notification to generic webhook."""
        try:
            data = {
                "home_team": home_team,
                "away_team": away_team,
                "quotes": quotes,
                "tip": list(tip),
                "time": game_time.strftime('%d.%m.%y %H:%M'),
                "timestamp": game_time.isoformat()
            }

            headers = {
                "Content-Type": "application/json"
            }

            response = requests.post(
                Config.WEBHOOK_URL,
                json=data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Generic webhook sent successfully")

        except requests.RequestException as e:
            logger.error(f"Failed to send generic webhook: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending generic webhook: {e}")

    def _collect_event(
        self,
        game_time: datetime,
        home_team: str,
        away_team: str,
        quotes: List[str],
        tip: Tuple[int, int]
    ) -> None:
        """Collect an event for grouped notification."""
        event = {
            "home_team": home_team,
            "away_team": away_team,
            "quotes": quotes,
            "tip": list(tip),
            "time": game_time.strftime('%d.%m.%y %H:%M'),
            "timestamp": game_time.isoformat()
        }
        self.pending_events.append(event)
        logger.debug(f"Collected event for grouped notification: {home_team} vs {away_team}")

    def send_grouped_notifications(self) -> None:
        """Send all collected events as grouped notifications."""
        if not self.pending_events:
            logger.debug("No events to send in grouped notification")
            return

        logger.info(f"Sending grouped notifications for {len(self.pending_events)} events")

        try:
            if self.zapier_enabled:
                self._send_grouped_zapier_webhook()

            if self.ntfy_enabled:
                self._send_grouped_ntfy_notification()

            if self.webhook_enabled:
                self._send_grouped_webhook_notification()

            # Clear pending events after sending
            self.pending_events = []

        except Exception as e:
            logger.error(f"Error sending grouped notifications: {e}")

    def _send_grouped_zapier_webhook(self) -> None:
        """Send grouped notification to Zapier webhook."""
        try:
            payload = {
                'events': self.pending_events
            }

            response = requests.post(
                Config.ZAPIER_URL,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Grouped Zapier webhook sent successfully")

        except requests.RequestException as e:
            logger.error(f"Failed to send grouped Zapier webhook: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending grouped Zapier webhook: {e}")

    def _send_grouped_ntfy_notification(self) -> None:
        """Send grouped notification via ntfy service."""
        try:
            # Create a summary message for ntfy
            title = f"{len(self.pending_events)} games tipped"
            message_parts = []
            for event in self.pending_events:
                message_parts.append(
                    f"{event['home_team']} - {event['away_team']}: {event['tip'][0]}:{event['tip'][1]} ({event['time']})"
                )
            message = "\n".join(message_parts)

            headers = {
                "X-Title": title,
                "Content-Type": "text/plain; charset=utf-8"
            }

            response = requests.post(
                Config.NTFY_URL,
                auth=(Config.NTFY_USERNAME, Config.NTFY_PASSWORD),
                data=message.encode('utf-8'),
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Grouped ntfy notification sent successfully")

        except requests.RequestException as e:
            logger.error(f"Failed to send grouped ntfy notification: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending grouped ntfy notification: {e}")

    def _send_grouped_webhook_notification(self) -> None:
        """Send grouped notification to generic webhook."""
        try:
            data = {
                "events": self.pending_events
            }

            headers = {
                "Content-Type": "application/json"
            }

            response = requests.post(
                Config.WEBHOOK_URL,
                json=data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Grouped generic webhook sent successfully")

        except requests.RequestException as e:
            logger.error(f"Failed to send grouped generic webhook: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending grouped generic webhook: {e}")
