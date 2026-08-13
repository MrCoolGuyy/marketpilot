"""
MarketPilot Telegram — Outbound Notifier.
"""

from __future__ import annotations

import httpx
from loguru import logger

from marketpilot.config.settings import TelegramSettings
from marketpilot.telegram.models import AnyNotification


class TelegramNotifier:
    """Outbound-only Telegram notification service."""
    
    def __init__(self, settings: TelegramSettings) -> None:
        self._settings = settings
        self._enabled = settings.enabled and bool(settings.bot_token.get_secret_value()) and bool(settings.chat_id)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def notify(self, event: AnyNotification) -> None:
        """Send a notification if enabled. Never raises an exception on delivery failure."""
        if not self._enabled:
            return
            
        text = event.render()
        
        # Max message size is 4096, truncate safely
        if len(text) > 4000:
            text = text[:4000] + "\n...[TRUNCATED]"
            
        token = self._settings.bot_token.get_secret_value()
        chat_id = self._settings.chat_id
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        
        # We retry only on 5xx or Timeout/ConnectionError.
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
                    resp = await client.post(url, json=payload)
                    
                    if resp.status_code == 200:
                        logger.debug("Telegram notification sent successfully")
                        return
                    elif 400 <= resp.status_code < 500:
                        # 4xx means bad request/unauthorized, no point in retrying.
                        logger.warning("Telegram notification failed with 4xx status: {}", resp.status_code)
                        return
                    else:
                        # 5xx
                        if attempt == max_retries:
                            logger.warning("Telegram notification failed after retries with status: {}", resp.status_code)
                            return
                            
            except httpx.RequestError as exc:
                if attempt == max_retries:
                    logger.warning("Telegram notification failed due to network error: {}", type(exc).__name__)
                    return
            except Exception:
                # Catch-all to absolutely prevent breaking the execution flow
                logger.warning("Telegram notification failed due to unexpected error")
                return
