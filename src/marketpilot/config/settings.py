"""
MarketPilot Config - Application settings.

Uses Pydantic Settings to load configuration from environment variables
and ``.env`` files.  All secrets (API keys) are loaded from env vars only
- never from YAML or committed files.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from marketpilot.core.enums import MarketDataEnvironment, ExecutionMode
from marketpilot.core.constants import (
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
    DB_POOL_SIZE,
    DEFAULT_DB_URL,
    DEFAULT_RATE_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_RETRIES,
    ORDER_RATE_LIMIT,
    RETRY_BACKOFF_BASE,
)


# ---------------------------------------------------------------------------
# Sub-settings (composed into AppSettings)
# ---------------------------------------------------------------------------

class ExchangeSettings(BaseSettings):
    """Bybit API credentials and connection tuning."""

    model_config = SettingsConfigDict(env_prefix="BYBIT_", env_file=".env", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""), description="Bybit API key")
    api_secret: SecretStr = Field(default=SecretStr(""), description="Bybit API secret")
    environment: MarketDataEnvironment = Field(default=MarketDataEnvironment.MAINNET, description="Market data source environment")
    rate_limit: int = Field(default=DEFAULT_RATE_LIMIT, ge=1)
    order_rate_limit: int = Field(default=ORDER_RATE_LIMIT, ge=1)
    timeout: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1)
    max_retries: int = Field(default=MAX_RETRIES, ge=0)
    retry_backoff: float = Field(default=RETRY_BACKOFF_BASE, ge=0.0)


class StorageSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    url: str = Field(default=DEFAULT_DB_URL, description="SQLAlchemy async DB URL")
    pool_size: int = Field(default=DB_POOL_SIZE, ge=1)
    max_overflow: int = Field(default=DB_MAX_OVERFLOW, ge=0)
    pool_recycle: int = Field(default=DB_POOL_RECYCLE, ge=60)
    echo: bool = Field(default=False, description="Echo SQL statements for debugging")


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=".env", extra="ignore")

    level: str = Field(default="INFO", description="Minimum log level")
    format: str = Field(
        default=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        description="Loguru format string",
    )
    rotation: str = Field(default="10 MB", description="Log file rotation threshold")
    retention: str = Field(default="7 days", description="Log file retention period")
    log_dir: Path = Field(default=Path("logs"), description="Directory for log files")


class ScannerSettings(BaseSettings):
    """Configuration for the market scanner."""

    model_config = SettingsConfigDict(env_prefix="SCANNER_", env_file=".env", extra="ignore")

    asset_type: str = Field(default="linear", description="Asset type to scan (e.g., linear, spot)")
    quote_coin: str = Field(default="USDT", description="Quote coin to filter by (e.g., USDT)")
    min_turnover_24h: float = Field(default=10_000_000.0, description="Minimum 24h turnover in quote coin")
    max_results: int = Field(default=20, ge=1, description="Maximum number of results to return")

    # Engine Weights for Opportunity Score
    weight_liquidity: float = Field(default=0.20, description="Weight for liquidity/turnover")
    weight_spread: float = Field(default=0.10, description="Weight for tight spread")
    weight_atr: float = Field(default=0.15, description="Weight for volatility (ATR)")
    weight_momentum: float = Field(default=0.15, description="Weight for 24h momentum")
    weight_trend_strength: float = Field(default=0.10, description="Weight for trend strength")
    weight_funding: float = Field(default=0.10, description="Weight for funding rate")
    weight_open_interest: float = Field(default=0.10, description="Weight for open interest")
    weight_trend_age: float = Field(default=0.10, description="Weight for trend age")

    # Absolute Thresholds (If failed, Market Quality = 0)
    minimum_liquidity: float = Field(default=1_000_000.0, description="Minimum 24h turnover")
    minimum_volume: float = Field(default=10.0, description="Minimum 24h base volume")
    minimum_atr_percent: float = Field(default=0.01, description="Minimum ATR percent (1%)")
    maximum_spread_bps: float = Field(default=50.0, description="Maximum spread in BPS")

    def model_post_init(self, __context: object) -> None:
        total_weight = (
            self.weight_liquidity + self.weight_spread + self.weight_atr +
            self.weight_momentum + self.weight_trend_strength + self.weight_funding +
            self.weight_open_interest + self.weight_trend_age
        )
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Scanner weights must sum to 1.0, got {total_weight}")


class IndicatorSettings(BaseSettings):
    """Configuration for technical indicators."""

    model_config = SettingsConfigDict(env_prefix="INDICATOR_", env_file=".env", extra="ignore")

    ema_fast: int = Field(default=20, gt=0, description="Fast EMA period")
    ema_slow: int = Field(default=50, gt=0, description="Slow EMA period")

    rsi_period: int = Field(default=14, gt=0, description="RSI calculation period")

    macd_fast: int = Field(default=12, gt=0, description="MACD fast EMA period")
    macd_slow: int = Field(default=26, gt=0, description="MACD slow EMA period")
    macd_signal: int = Field(default=9, gt=0, description="MACD signal EMA period")

    atr_period: int = Field(default=14, gt=0, description="ATR calculation period")
    volume_sma_period: int = Field(default=20, gt=0, description="Volume SMA period")

    @property
    def is_macd_valid(self) -> bool:
        return self.macd_fast < self.macd_slow

    def model_post_init(self, __context: object) -> None:
        if not self.is_macd_valid:
            raise ValueError(f"MACD fast ({self.macd_fast}) must be < slow ({self.macd_slow})")


class StrategySettings(BaseSettings):
    """Configuration for trading strategies."""

    model_config = SettingsConfigDict(env_prefix="STRATEGY_", env_file=".env", extra="ignore")

    # Minimum acceptable reward-to-risk ratio
    minimum_rr: float = Field(default=2.0, description="Minimum acceptable Reward-to-Risk ratio")

    # Weights for the Overall Strategy Score
    weight_confidence: float = Field(default=0.35, description="Weight for Strategy Confidence")
    weight_market_quality: float = Field(default=0.25, description="Weight for Scanner Market Quality")
    weight_regime_match: float = Field(default=0.20, description="Weight for Regime Match")
    weight_expected_rr: float = Field(default=0.20, description="Weight for Expected RR")

    def model_post_init(self, __context: object) -> None:
        total_weight = (
            self.weight_confidence + self.weight_market_quality +
            self.weight_regime_match + self.weight_expected_rr
        )
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Strategy weights must sum to 1.0, got {total_weight}")


class BaselineStrategySettings(BaseSettings):
    """Configuration for baseline strategy rules."""

    model_config = SettingsConfigDict(env_prefix="STRAT_", env_file=".env", extra="ignore")

    rsi_long_min: int = Field(default=55, ge=0, le=100, description="Minimum RSI for LONG")
    rsi_long_max: int = Field(default=70, ge=0, le=100, description="Maximum RSI for LONG")
    rsi_short_min: int = Field(default=30, ge=0, le=100, description="Minimum RSI for SHORT")
    rsi_short_max: int = Field(default=45, ge=0, le=100, description="Maximum RSI for SHORT")

    def model_post_init(self, __context: object) -> None:
        if self.rsi_long_min > self.rsi_long_max:
            raise ValueError(f"rsi_long_min ({self.rsi_long_min}) must be <= rsi_long_max ({self.rsi_long_max})")
        if self.rsi_short_min > self.rsi_short_max:
            raise ValueError(f"rsi_short_min ({self.rsi_short_min}) must be <= rsi_short_max ({self.rsi_short_max})")
        if self.rsi_short_max >= self.rsi_long_min:
            raise ValueError(f"LONG and SHORT RSI ranges must not overlap (rsi_short_max {self.rsi_short_max} must be < rsi_long_min {self.rsi_long_min})")


class RiskSettings(BaseSettings):
    """Configuration for theoretical risk management."""

    model_config = SettingsConfigDict(env_prefix="RISK_", env_file=".env", extra="ignore")

    risk_per_trade_fraction: Decimal = Field(
        default=Decimal("0.005"), description="Fraction of account equity to risk per trade"
    )
    max_risk_per_trade_fraction: Decimal = Field(
        default=Decimal("0.01"), description="Hard policy ceiling for risk per trade"
    )
    atr_stop_multiplier: Decimal = Field(
        default=Decimal("1.5"), description="Multiplier for ATR to calculate stop distance"
    )
    minimum_reward_risk: Decimal = Field(
        default=Decimal("2.0"), description="Minimum reward to risk ratio"
    )
    maximum_atr_fraction: Decimal = Field(
        default=Decimal("0.05"), description="Maximum allowed volatility (ATR / Entry Price)"
    )

    def model_post_init(self, __context: object) -> None:
        if (
            not self.risk_per_trade_fraction.is_finite()
            or self.risk_per_trade_fraction <= 0
            or self.risk_per_trade_fraction > Decimal("1")
        ):
            raise ValueError("risk_per_trade_fraction must be a finite positive decimal <= 1")
        if (
            not self.max_risk_per_trade_fraction.is_finite()
            or self.max_risk_per_trade_fraction <= 0
            or self.max_risk_per_trade_fraction > Decimal("1")
        ):
            raise ValueError("max_risk_per_trade_fraction must be a finite positive decimal <= 1")
        if self.risk_per_trade_fraction > self.max_risk_per_trade_fraction:
            raise ValueError(
                f"risk_per_trade_fraction ({self.risk_per_trade_fraction}) exceeds hard ceiling ({self.max_risk_per_trade_fraction})"
            )
        if not self.atr_stop_multiplier.is_finite() or self.atr_stop_multiplier <= 0:
            raise ValueError("atr_stop_multiplier must be a finite positive decimal")
        if not self.minimum_reward_risk.is_finite() or self.minimum_reward_risk <= 0:
            raise ValueError("minimum_reward_risk must be a finite positive decimal")
        if not self.maximum_atr_fraction.is_finite() or self.maximum_atr_fraction <= 0 or self.maximum_atr_fraction > Decimal("1"):
            raise ValueError("maximum_atr_fraction must be a finite positive decimal <= 1")


class SimulationSettings(BaseSettings):
    """Shared mathematics for simulated paper trading and backtesting."""

    leverage: int = Field(default=3, description="Fixed leverage multiplier")
    taker_fee_fraction: Decimal = Field(default=Decimal("0.0006"), description="Simulated taker fee fraction")
    slippage_bps: Decimal = Field(default=Decimal("5"), description="Slippage in basis points")

    def validate_simulation_settings(self) -> None:
        if self.leverage < 1 or self.leverage > 10:
            raise ValueError("leverage must be between 1 and 10")
        if not self.taker_fee_fraction.is_finite() or self.taker_fee_fraction < 0 or self.taker_fee_fraction >= 1:
            raise ValueError("taker_fee_fraction must be a valid positive fraction < 1")
        if not self.slippage_bps.is_finite() or self.slippage_bps < 0:
            raise ValueError("slippage_bps must be positive and finite")


class PaperSettings(SimulationSettings):
    """Configuration for local paper trading simulation."""

    model_config = SettingsConfigDict(env_prefix="PAPER_", env_file=".env", extra="ignore")

    initial_equity: Decimal = Field(default=Decimal("10000"), description="Starting balance for paper trading")

    def model_post_init(self, __context: object) -> None:
        self.validate_simulation_settings()
        if not self.initial_equity.is_finite() or self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive and finite")


class BacktestSettings(SimulationSettings):
    """Configuration for historical backtesting."""

    model_config = SettingsConfigDict(env_prefix="BACKTEST_", env_file=".env", extra="ignore")

    initial_equity: Decimal = Field(default=Decimal("10000"), description="Starting balance for backtesting")

    def model_post_init(self, __context: object) -> None:
        self.validate_simulation_settings()
        if not self.initial_equity.is_finite() or self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive and finite")

class OptimizationSettings(BaseSettings):
    """Configuration for historical parameter optimization."""

    model_config = SettingsConfigDict(env_prefix="OPT_", env_file=".env", extra="ignore")

    train_fraction: Decimal = Field(default=Decimal("0.70"), description="Fraction of dataset to use for training")
    minimum_train_trades: int = Field(default=5, description="Minimum trades required in training to qualify")
    maximum_candidates: int = Field(default=100, description="Hard cap on total generated candidates")

    grid_rsi_long_min: list[int] = Field(default_factory=lambda: [52, 55, 58])
    grid_rsi_long_max: list[int] = Field(default_factory=lambda: [68, 70, 72])
    grid_rsi_short_min: list[int] = Field(default_factory=lambda: [28, 30, 32])
    grid_rsi_short_max: list[int] = Field(default_factory=lambda: [42, 45, 48])

    def model_post_init(self, __context: object) -> None:
        if not self.train_fraction.is_finite() or self.train_fraction <= Decimal("0") or self.train_fraction >= Decimal("1"):
            raise ValueError("train_fraction must be strictly between 0 and 1 exclusive")
        if self.minimum_train_trades < 0:
            raise ValueError("minimum_train_trades must be at least 0")
        if self.maximum_candidates < 1:
            raise ValueError("maximum_candidates must be at least 1")


class TelegramSettings(BaseSettings):
    """Telegram Opt-in Notification settings."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", env_file=".env", extra="ignore")

    enabled: bool = Field(default=False)
    bot_token: SecretStr = Field(default=SecretStr(""))
    chat_id: str = Field(default="")
    timeout_seconds: int = Field(default=5, ge=1)

    send_startup: bool = Field(default=True)
    send_trade: bool = Field(default=True)
    send_daily_summary: bool = Field(default=True)
    send_incident: bool = Field(default=True)
    send_circuit_breaker: bool = Field(default=True)


class DemoSettings(BaseSettings):
    """Configuration for Bybit Demo Trading Execution."""

    model_config = SettingsConfigDict(env_prefix="DEMO_", env_file=".env", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""), description="Bybit Demo Trading API key")
    api_secret: SecretStr = Field(default=SecretStr(""), description="Bybit Demo Trading API secret")
    execution_enabled: bool = Field(default=False, description="Master switch for Demo execution")

    # Autopilot Guards
    auto_submit_enabled: bool = Field(default=False, description="Enable Autopilot to submit Demo orders (Default OFF)")
    kill_switch: bool = Field(default=False, description="Emergency stop for all Demo executions")
    max_daily_trades: int = Field(default=5, ge=0, description="Maximum number of autopilot demo trades per day")
    daily_loss_limit: Decimal = Field(default=Decimal("0.05"), description="Maximum daily loss fraction before halting")


class PortfolioSettings(BaseSettings):
    """Phase-5 Capital Allocation Rules."""
    model_config = SettingsConfigDict(env_prefix="MARKETPILOT_PORTFOLIO_", env_file=".env", extra="ignore")

    allocated_capital: Optional[Decimal] = Field(
        default=None,
        description="Explicitly allocated risk capital for MarketPilot."
    )
    minimum_unallocated_buffer: Decimal = Field(
        default=Decimal("3.0"),
        description="Minimum cash buffer that must remain unallocated in the account."
    )
    max_total_heat_ratio: Decimal = Field(
        default=Decimal("0.10"),
        description="Maximum sum of (risk/equity) across all active and pending reservations."
    )
    max_simultaneous_lineages: int = Field(
        default=1,
        description="Maximum active logical lineages allowed globally."
    )

# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------

class AppSettings(BaseSettings):
    """Top-level application settings composing all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MarketPilot"
    debug: bool = Field(default=False, description="Enable debug mode")
    execution_mode: ExecutionMode = Field(default=ExecutionMode.PAPER, description="Global Execution Mode (PAPER, DEMO, LIVE)")

    exchange: ExchangeSettings = Field(default_factory=ExchangeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    indicators: IndicatorSettings = Field(default_factory=IndicatorSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    paper: PaperSettings = Field(default_factory=PaperSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    optimization: OptimizationSettings = Field(default_factory=OptimizationSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    demo: DemoSettings = Field(default_factory=DemoSettings)
    portfolio: PortfolioSettings = Field(default_factory=PortfolioSettings)

    dashboard_control_key: SecretStr = Field(default=SecretStr(""), description="Secret key required for Dashboard POST endpoints")

AppSettings.model_rebuild()
