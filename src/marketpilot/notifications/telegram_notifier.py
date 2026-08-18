"""
MarketPilot Notifications - Telegram Notifier.
"""
import asyncio
import json
import urllib.request
import urllib.error
from loguru import logger
from typing import Any

from marketpilot.config.settings import TelegramSettings
from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
from marketpilot.notifications.base import Notifier

class TelegramNotifier(Notifier):
    def __init__(self, settings: TelegramSettings):
        self.settings = settings
        self.base_url = f"https://api.telegram.org/bot{self.settings.bot_token.get_secret_value()}" if self.settings.bot_token else ""
        self._polling_task = None
        self._is_polling = False
        self._offset = 0

        # Event type to setting mapping
        self.dispatch_map = {
            NotificationType.STARTUP: self.settings.send_startup,
            NotificationType.SHUTDOWN: self.settings.send_startup,
            NotificationType.CIRCUIT_BREAKER_HALTED: self.settings.send_circuit_breaker,
            NotificationType.CIRCUIT_BREAKER_RECOVERED: self.settings.send_circuit_breaker,
            NotificationType.RECOVERY_STARTED: self.settings.send_circuit_breaker,
            NotificationType.RECOVERY_FINISHED: self.settings.send_circuit_breaker,
            NotificationType.RECOVERY_FAILED: self.settings.send_incident,
            NotificationType.EXECUTION_SUCCESS: self.settings.send_trade,
            NotificationType.EXECUTION_FAILED: self.settings.send_incident,
            NotificationType.EXECUTION_UNKNOWN: self.settings.send_incident,
            NotificationType.PAPER_TRADE: self.settings.send_trade,
            NotificationType.DAILY_SUMMARY: self.settings.send_daily_summary,
            NotificationType.CRITICAL_INCIDENT_P0: self.settings.send_incident,
            NotificationType.CRITICAL_INCIDENT_P1: self.settings.send_incident,
        }

    async def notify(self, event: NotificationEvent) -> None:
        """Asynchronously dispatches a notification if enabled."""
        if not self.settings.enabled or not self.settings.bot_token or not self.settings.chat_id:
            return

        is_enabled_for_event = self.dispatch_map.get(event.event_type, False)
        if not is_enabled_for_event:
            return

        message = self._format_message(event)
        if not message:
            return

        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, text: str, chat_id: str = None) -> None:
        target_chat_id = chat_id or self.settings.chat_id
        try:
            data = json.dumps({
                "chat_id": target_chat_id,
                "text": text,
                "parse_mode": "HTML"
            }).encode('utf-8')

            req = urllib.request.Request(
                f"{self.base_url}/sendMessage",
                data=data,
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                if response.status != 200:
                    logger.warning(f"Telegram API returned {response.status}")
        except urllib.error.URLError as e:
            logger.warning(f"Failed to send Telegram notification: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in Telegram notifier: {e}")

    async def start_polling(self):
        """Deprecated: Telegram is now strictly an outbound observability channel."""
        pass

    async def stop_polling(self):
        """Deprecated: Telegram is now strictly an outbound observability channel."""
        pass

    def _format_message(self, event: NotificationEvent) -> str:
        d = event.message_data

        # Always prefer pre-rendered canonical text if available
        if "message" in d:
            return d["message"]

        # Legacy fallback
        if event.event_type == NotificationType.STARTUP:
            return (
                "<b>MarketPilot RC-1 Started</b>\n"
                f"Version: {d.get('version', 'unknown')}\n"
                f"Config Hash: {d.get('config_hash', 'unknown')}\n"
            )
        elif event.event_type == NotificationType.CIRCUIT_BREAKER_HALTED:
            msg = f"<b>HALTED</b>\nReason: {d.get('reason', 'Unknown')}"
            if event.decision_id:
                msg += f"\nDecision ID: {event.decision_id}"
            return msg
        else:
            return f"<b>{event.event_type.value}</b>"
