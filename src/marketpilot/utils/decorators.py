"""
MarketPilot Utils — Reusable decorators.

Production-grade decorators for retry logic, execution logging,
and response validation.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from loguru import logger

from marketpilot.core.constants import MAX_RETRIES, RETRY_BACKOFF_BASE

P = ParamSpec("P")
T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

def retry(
    max_retries: int = MAX_RETRIES,
    backoff_base: float = RETRY_BACKOFF_BASE,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator that retries a function on failure with exponential backoff.

    Works with both sync and async callables.

    Parameters
    ----------
    max_retries:
        Maximum number of retry attempts.
    backoff_base:
        Base for exponential backoff (seconds).
    exceptions:
        Tuple of exception types to catch and retry on.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                last_exc: BaseException | None = None
                for attempt in range(1, max_retries + 2):  # +2 → initial + retries
                    try:
                        return await func(*args, **kwargs)  # type: ignore[misc]
                    except exceptions as exc:
                        last_exc = exc
                        if attempt > max_retries:
                            break
                        delay = backoff_base ** attempt
                        logger.warning(
                            "Retry {}/{} for {} after {:.1f}s — {}",
                            attempt,
                            max_retries,
                            func.__qualname__,
                            delay,
                            exc,
                        )
                        await asyncio.sleep(delay)
                raise last_exc  # type: ignore[misc]

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                last_exc: BaseException | None = None
                for attempt in range(1, max_retries + 2):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt > max_retries:
                            break
                        delay = backoff_base ** attempt
                        logger.warning(
                            "Retry {}/{} for {} after {:.1f}s — {}",
                            attempt,
                            max_retries,
                            func.__qualname__,
                            delay,
                            exc,
                        )
                        time.sleep(delay)
                raise last_exc  # type: ignore[misc]

            return sync_wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# Execution logging
# ---------------------------------------------------------------------------

def log_execution(func: Callable[P, T]) -> Callable[P, T]:
    """Log function entry, exit, and wall-clock duration.

    Works with both sync and async callables.
    """
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            logger.debug("→ {}", func.__qualname__)
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)  # type: ignore[misc]
                elapsed = time.perf_counter() - start
                logger.debug("← {} ({:.3f}s)", func.__qualname__, elapsed)
                return result
            except Exception:
                elapsed = time.perf_counter() - start
                logger.error("✗ {} ({:.3f}s)", func.__qualname__, elapsed)
                raise

        return async_wrapper  # type: ignore[return-value]
    else:

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            logger.debug("→ {}", func.__qualname__)
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                logger.debug("← {} ({:.3f}s)", func.__qualname__, elapsed)
                return result
            except Exception:
                elapsed = time.perf_counter() - start
                logger.error("✗ {} ({:.3f}s)", func.__qualname__, elapsed)
                raise

        return sync_wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------

def validate_response(
    expected_keys: tuple[str, ...] = (),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Validate that a dict response contains the *expected_keys*.

    Raises ``ValueError`` if any key is missing.  Only useful for
    functions that return ``dict[str, Any]``.
    """

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                result = await func(*args, **kwargs)
                _check_keys(result, expected_keys, func.__qualname__)
                return result

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                result = func(*args, **kwargs)
                _check_keys(result, expected_keys, func.__qualname__)
                return result

            return sync_wrapper  # type: ignore[return-value]

    return decorator


def _check_keys(data: Any, keys: tuple[str, ...], source: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{source} expected dict, got {type(data).__name__}")
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError(f"{source} response missing keys: {missing}")
