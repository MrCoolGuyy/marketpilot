"""
MarketPilot Models — Account domain models.

Wallet balances and account information.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Balance(BaseModel, frozen=True):
    """Balance for a single coin in the wallet."""

    coin: str = Field(..., description="Coin ticker, e.g. 'USDT'")
    wallet_balance: str
    available_balance: str
    locked: str = "0"
    unrealised_pnl: str = "0"
    updated_at: datetime


class WalletInfo(BaseModel, frozen=True):
    """Aggregated wallet information."""

    account_type: str = Field(..., description="Account type, e.g. 'UNIFIED'")
    total_equity: str
    total_wallet_balance: str
    total_available_balance: str
    balances: list[Balance] = Field(default_factory=list)
    updated_at: datetime
