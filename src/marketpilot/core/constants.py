"""
MarketPilot Core — Constants.

Centralised, immutable values used across the application.
All Bybit-specific constants are kept here so the rest of the codebase
stays exchange-agnostic.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Application Metadata
# ---------------------------------------------------------------------------

APP_NAME: str = "MarketPilot"
APP_VERSION: str = "0.1.0"

# ---------------------------------------------------------------------------
# Bybit API
# ---------------------------------------------------------------------------

BYBIT_MAINNET_HTTP: str = "https://api.bybit.com"
BYBIT_MAINNET_WS_PUBLIC: str = "wss://stream.bybit.com/v5/public"
BYBIT_MAINNET_WS_PRIVATE: str = "wss://stream.bybit.com/v5/private"

BYBIT_TESTNET_HTTP: str = "https://api-testnet.bybit.com"
BYBIT_TESTNET_WS_PUBLIC: str = "wss://stream-testnet.bybit.com/v5/public"
BYBIT_TESTNET_WS_PRIVATE: str = "wss://stream-testnet.bybit.com/v5/private"

# ---------------------------------------------------------------------------
# Rate Limits (requests per second — conservative defaults)
# ---------------------------------------------------------------------------

DEFAULT_RATE_LIMIT: int = 10  # general API calls / second
ORDER_RATE_LIMIT: int = 10   # order placement calls / second

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS: int = 10
DEFAULT_RECV_WINDOW: int = 5000  # Bybit recv_window in ms
MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 1.5  # seconds — exponential backoff base

# ---------------------------------------------------------------------------
# Data Limits
# ---------------------------------------------------------------------------

MAX_KLINE_LIMIT: int = 1000
MAX_ORDERBOOK_LIMIT: int = 200
DEFAULT_KLINE_LIMIT: int = 200

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

DEFAULT_DB_URL: str = "sqlite+aiosqlite:///data/marketpilot.db"
DB_POOL_SIZE: int = 5
DB_MAX_OVERFLOW: int = 10
DB_POOL_RECYCLE: int = 3600  # seconds
