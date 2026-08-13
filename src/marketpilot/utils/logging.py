"""
MarketPilot Utils — Logging setup.

Configures Loguru sinks for console and file output, and patches stdlib
logging so third-party libraries (SQLAlchemy, pybit) route through the
same pipeline.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

from marketpilot.config.settings import LoggingSettings


# ---------------------------------------------------------------------------
# Stdlib → Loguru bridge
# ---------------------------------------------------------------------------

class _InterceptHandler(logging.Handler):
    """Redirect stdlib ``logging`` records into Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the logged message originated.
        frame = logging.currentframe()
        depth = 0
        while frame is not None:
            filename = frame.f_code.co_filename
            if filename == logging.__file__:
                frame = frame.f_back
                depth += 1
                continue
            break

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(settings: LoggingSettings | None = None) -> None:
    """Configure Loguru sinks and intercept stdlib logging.

    Parameters
    ----------
    settings:
        Logging settings.  When ``None`` the defaults from
        ``LoggingSettings`` are used.
    """
    if settings is None:
        settings = LoggingSettings()

    # Remove default Loguru handler
    logger.remove()

    # Console sink (stderr)
    logger.add(
        sys.stderr,
        level=settings.level,
        format=settings.format,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File sink
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "marketpilot.log",
        level=settings.level,
        format=settings.format,
        rotation=settings.rotation,
        retention=settings.retention,
        compression="gz",
        enqueue=True,  # thread-safe writes
    )

    # Intercept stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Quieten noisy third-party loggers
    for name in ("sqlalchemy.engine", "urllib3", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logger.info("Logging initialised (level={})", settings.level)
