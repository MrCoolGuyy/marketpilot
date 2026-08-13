"""
MarketPilot Utils — Helper functions.

General-purpose utilities for timestamp conversion and financial
precision handling.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation


# ---------------------------------------------------------------------------
# Timestamp conversion
# ---------------------------------------------------------------------------

def ms_to_datetime(timestamp_ms: int) -> datetime:
    """Convert a Unix timestamp in **milliseconds** to a UTC ``datetime``."""
    return datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC)


def datetime_to_ms(dt: datetime) -> int:
    """Convert a UTC ``datetime`` to a Unix timestamp in **milliseconds**."""
    return int(dt.timestamp() * 1_000)


def now_ms() -> int:
    """Return the current UTC time as a Unix timestamp in milliseconds."""
    return datetime_to_ms(datetime.now(tz=UTC))


# ---------------------------------------------------------------------------
# Decimal / financial helpers
# ---------------------------------------------------------------------------

def to_decimal(value: str | float | int) -> Decimal:
    """Safely convert a value to ``Decimal``.

    Raises
    ------
    ValueError
        If the value cannot be converted.
    """
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


def round_step(value: Decimal, step: Decimal) -> Decimal:
    """Round *value* down to the nearest multiple of *step*.

    Useful for aligning order quantities and prices to exchange tick/step
    sizes.

    Examples
    --------
    >>> round_step(Decimal("0.12345"), Decimal("0.001"))
    Decimal('0.123')
    """
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    return (value // step) * step


def format_price(value: Decimal, tick_size: Decimal) -> str:
    """Format *value* to match the precision of *tick_size*.

    Returns a plain string without scientific notation.
    """
    quantised = value.quantize(tick_size)
    return format(quantised, "f")
