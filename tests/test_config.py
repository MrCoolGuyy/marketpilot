"""
Tests for the configuration layer.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from marketpilot.config.loader import (
    _interpolate_env,
    load_yaml_config,
    get_settings,
    override_settings,
    reset_settings,
)
from marketpilot.config.settings import AppSettings, ExchangeSettings
from marketpilot.core.exceptions import ConfigFileNotFoundError


class TestInterpolateEnv:
    """Test environment variable interpolation."""

    def test_simple_var(self) -> None:
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            assert _interpolate_env("${MY_VAR}") == "hello"

    def test_var_with_default(self) -> None:
        assert _interpolate_env("${MISSING_VAR:fallback}") == "fallback"

    def test_var_with_empty_default(self) -> None:
        assert _interpolate_env("${MISSING_VAR:}") == ""

    def test_missing_var_no_default(self) -> None:
        result = _interpolate_env("${TOTALLY_MISSING}")
        assert result == "${TOTALLY_MISSING}"

    def test_no_placeholders(self) -> None:
        assert _interpolate_env("plain text") == "plain text"


class TestLoadYamlConfig:
    """Test YAML config loading."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileNotFoundError):
            load_yaml_config(tmp_path / "nope.yaml")

    def test_valid_yaml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.yaml"
        cfg.write_text("app_name: TestApp\ndebug: true\n", encoding="utf-8")
        data = load_yaml_config(cfg)
        assert data["app_name"] == "TestApp"
        assert data["debug"] is True

    def test_env_interpolation_in_yaml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.yaml"
        cfg.write_text("key: ${TEST_YAML_VAR:default_val}\n", encoding="utf-8")
        data = load_yaml_config(cfg)
        assert data["key"] == "default_val"


class TestAppSettings:
    """Test Pydantic settings."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from marketpilot.config.settings import ExchangeSettings, StorageSettings, LoggingSettings, ScannerSettings
        monkeypatch.setitem(ExchangeSettings.model_config, "env_file", None)
        monkeypatch.setitem(StorageSettings.model_config, "env_file", None)
        monkeypatch.setitem(LoggingSettings.model_config, "env_file", None)
        monkeypatch.setitem(ScannerSettings.model_config, "env_file", None)
        
        # Pydantic v2 SettingsConfigDict is stored in model_config
        # We can also just instantiate the settings with _env_file=None directly to test defaults
        e = ExchangeSettings(_env_file=None)
        assert e.testnet is True
        
        settings = AppSettings(_env_file=None, exchange=e)
        assert settings.app_name == "MarketPilot"
        assert settings.debug is False
        assert settings.exchange.testnet is True

    def test_exchange_settings(self) -> None:
        exchange = ExchangeSettings(testnet=False, rate_limit=20)
        assert exchange.testnet is False
        assert exchange.rate_limit == 20


class TestSettingsSingleton:
    """Test the global settings accessor."""

    def test_get_returns_settings(self) -> None:
        reset_settings()
        settings = get_settings()
        assert isinstance(settings, AppSettings)

    def test_override_and_reset(self) -> None:
        custom = AppSettings(app_name="Custom")
        override_settings(custom)
        assert get_settings().app_name == "Custom"
        reset_settings()
        assert get_settings().app_name == "MarketPilot"
