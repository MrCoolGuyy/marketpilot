"""
MarketPilot — Multi-Asset Trading Bot.

A modular, production-ready trading bot framework for Bybit exchange
supporting spot, linear, inverse, and options markets.
"""

from __future__ import annotations

__version__: str = "0.1.0"
__app_name__: str = "MarketPilot"


def main() -> None:
    """CLI entry point — bootstraps logging and prints readiness banner."""
    from marketpilot.config import get_settings
    from marketpilot.utils.logging import setup_logging

    settings = get_settings()
    setup_logging(settings.logging)

    from loguru import logger

    logger.info("━" * 50)
    logger.info("  {} v{}", __app_name__, __version__)
    logger.info("  Market Data: {}", settings.exchange.environment.value)
    logger.info("  Execution  : {}", settings.execution_mode.value)
    logger.info("  DB         : {}", settings.storage.url)
    logger.info("━" * 50)
    logger.info("Foundation loaded — ready for module integration.")
