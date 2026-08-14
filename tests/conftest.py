"""
Shared test fixtures for the MarketPilot test suite.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest

from marketpilot.config.loader import override_settings, reset_settings
from marketpilot.config.settings import (
    AppSettings,
    ExchangeSettings,
    LoggingSettings,
    StorageSettings,
)


@pytest.fixture()
def test_settings() -> Generator[AppSettings]:
    """Provide a deterministic ``AppSettings`` for unit tests."""
    settings = AppSettings(
        app_name="MarketPilot-Test",
        debug=True,
        exchange=ExchangeSettings(testnet=True),
        storage=StorageSettings(url="sqlite+aiosqlite:///:memory:", echo=False),
        logging=LoggingSettings(level="DEBUG"),
    )
    override_settings(settings)
    yield settings
    reset_settings()


@pytest.fixture()
def sample_datetime() -> datetime:
    """A fixed UTC datetime for reproducible tests."""
    return datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

@pytest.fixture(autouse=True)
def isolate_projections(tmp_path, monkeypatch):
    """Ensure no test pollutes the production ~/.marketpilot/projections directory."""
    projections_dir = tmp_path / "projections"
    monkeypatch.setattr("marketpilot.dashboard.projections.DEFAULT_PROJECTIONS_DIR", projections_dir)
