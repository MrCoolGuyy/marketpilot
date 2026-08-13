"""
MarketPilot Core - Event Bus.

Strictly ordered, immutable event bus for the Trading Pipeline.
"""

from typing import Any, Callable, TypeVar, Coroutine
from pydantic import BaseModel
import asyncio
from loguru import logger

T = TypeVar("T", bound=BaseModel)

class PipelineEvent(BaseModel, frozen=True):
    """Base class for all pipeline events."""
    pass

class EventBus:
    """A strictly ordered, asynchronous event bus."""
    
    def __init__(self):
        self._handlers: dict[type, list[Callable[[PipelineEvent], Coroutine[Any, Any, None]]]] = {}
        
    def subscribe(self, event_type: type[T], handler: Callable[[T], Coroutine[Any, Any, None]]) -> None:
        """Subscribes an async handler to a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        
    async def publish(self, event: PipelineEvent) -> None:
        """Publishes an event to all subscribed handlers concurrently."""
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        
        if not handlers:
            logger.debug(f"No handlers subscribed for {event_type.__name__}")
            return
            
        # Execute handlers concurrently
        tasks = [asyncio.create_task(handler(event)) for handler in handlers]
        
        # Wait for all handlers to finish before returning to guarantee ordering
        # If one fails, we want to know immediately.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Event handler failed processing {event_type.__name__}: {r}")
                raise r
