"""
MarketPilot Core — Exception hierarchy.

All application exceptions inherit from `MarketPilotError` to allow
blanket catching at the top level while preserving granular handling
at the module level.
"""

from __future__ import annotations


class MarketPilotError(Exception):
    """Base exception for all MarketPilot errors."""

    def __init__(self, message: str = "", *, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, details={self.details!r})"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ConfigError(MarketPilotError):
    """Raised when configuration loading or validation fails."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when a required configuration file is missing."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Configuration file not found: {path}", details={"path": path})


# ---------------------------------------------------------------------------
# Exchange / API
# ---------------------------------------------------------------------------

class ExchangeError(MarketPilotError):
    """Base exception for exchange-related errors."""


class ExchangeConnectionError(ExchangeError):
    """Raised when a connection to the exchange fails."""


class ExchangeAPIError(ExchangeError):
    """Raised when the exchange API returns an error response."""

    def __init__(self, status_code: int, message: str, *, ret_code: int = 0) -> None:
        self.status_code = status_code
        self.ret_code = ret_code
        super().__init__(
            message,
            details={"status_code": status_code, "ret_code": ret_code},
        )


class RateLimitError(ExchangeError):
    """Raised when exchange rate limits are exceeded."""


# ---------------------------------------------------------------------------
# Storage / Database
# ---------------------------------------------------------------------------

class StorageError(MarketPilotError):
    """Base exception for storage / database errors."""


class StorageConnectionError(StorageError):
    """Raised when database connection fails."""


class RecordNotFoundError(StorageError):
    """Raised when a requested record does not exist."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationError(MarketPilotError):
    """Raised when data validation fails outside Pydantic boundaries."""
