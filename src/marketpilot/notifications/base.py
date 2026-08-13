"""
MarketPilot Notifications - Base Interface.
"""
from abc import ABC, abstractmethod
from marketpilot.notifications.notification_models import NotificationEvent

class Notifier(ABC):
    @abstractmethod
    async def notify(self, event: NotificationEvent) -> None:
        """Dispatches a notification."""
        pass
        
    async def start_polling(self) -> None:
        """Optional override for notifiers that support inbound commands."""
        pass
        
    async def stop_polling(self) -> None:
        """Optional override to gracefully stop polling."""
        pass
