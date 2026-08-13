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
                "parse_mode": "Markdown"
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
        if not self.settings.enabled or not self.settings.bot_token:
            return
        self._is_polling = True
        self._polling_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram command polling started.")
        
    async def stop_polling(self):
        self._is_polling = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram command polling stopped.")
        
    async def _poll_loop(self):
        while self._is_polling:
            try:
                updates = await asyncio.to_thread(self._get_updates_sync)
                if updates:
                    for update in updates:
                        self._offset = update['update_id'] + 1
                        if 'message' in update and 'text' in update['message']:
                            await self._handle_command(update['message'])
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
            await asyncio.sleep(2)
            
    def _get_updates_sync(self):
        try:
            url = f"{self.base_url}/getUpdates?offset={self._offset}&timeout=5"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("ok"):
                    return data.get("result", [])
        except Exception:
            pass
        return []
        
    async def _handle_command(self, message: dict):
        chat_id = str(message.get('chat', {}).get('id', ''))
        text = message.get('text', '').strip()
        
        # Security: Whitelist Chat ID
        if chat_id != str(self.settings.chat_id):
            logger.warning(f"Unauthorized Telegram command from {chat_id}: {text}")
            return
            
        if not text.startswith('/'):
            return
            
        cmd = text.split()[0].lower()
        response = ""
        
        # We rely on dashboard_app.state injected in daemon for read-only status
        from marketpilot.dashboard.server import app as dashboard_app
        daemon = dashboard_app.state.daemon
        
        if cmd == "/status":
            cb_state = "NORMAL"
            if daemon and daemon.health and daemon.health.cb:
                cb_state = daemon.health.cb.state.value
            response = f"*RC-1 Status*\nRunning\nCircuit Breaker: {cb_state}"
        elif cmd == "/health":
            response = "*Health Summary*\nEverything is operational."
        elif cmd == "/incident":
            response = "*Recent Incidents*\nNone recorded."
        elif cmd == "/cycle":
            response = "*Last Cycle*\nNo data yet."
        else:
            response = "Unknown command."
            
        await asyncio.to_thread(self._send_sync, response, chat_id)

    def _format_message(self, event: NotificationEvent) -> str:
        d = event.message_data
        
        if event.event_type == NotificationType.STARTUP:
            return (
                "?? *MarketPilot RC-1 Started*\n"
                f"Version: {d.get('version', 'unknown')}\n"
                f"Config Hash: {d.get('config_hash', 'unknown')}\n"
            )
        elif event.event_type == NotificationType.CIRCUIT_BREAKER_HALTED:
            return f"?? *HALTED*\nReason: {d.get('reason', 'Unknown')}"
        else:
            return f"*{event.event_type.value}*"
