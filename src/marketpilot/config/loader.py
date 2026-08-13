"""
MarketPilot Config — Configuration loader.

Provides a thread-safe singleton for the application settings and an
optional YAML overlay loader that can interpolate environment variables.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from marketpilot.config.settings import AppSettings
from marketpilot.core.exceptions import ConfigError, ConfigFileNotFoundError


# ---------------------------------------------------------------------------
# Environment variable interpolation in YAML values
# ---------------------------------------------------------------------------

_ENV_PATTERN: re.Pattern[str] = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")


def _interpolate_env(value: str) -> str:
    """Replace ``${VAR}`` or ``${VAR:default}`` with environment values."""

    def _replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        if default is not None:
            return default
        return match.group(0)  # leave as-is if no env and no default

    return _ENV_PATTERN.sub(_replacer, value)


def _walk_and_interpolate(data: Any) -> Any:
    """Recursively interpolate env vars in a nested dict/list structure."""
    if isinstance(data, dict):
        return {k: _walk_and_interpolate(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_walk_and_interpolate(item) for item in data]
    if isinstance(data, str):
        return _interpolate_env(data)
    return data


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and interpolate ``${ENV_VAR}`` placeholders.

    Parameters
    ----------
    path:
        Path to the YAML configuration file.

    Returns
    -------
    dict[str, Any]
        Parsed and interpolated configuration dictionary.

    Raises
    ------
    ConfigFileNotFoundError
        If the file does not exist.
    ConfigError
        If the YAML is malformed.
    """
    filepath = Path(path)
    if not filepath.exists():
        raise ConfigFileNotFoundError(str(filepath))

    try:
        raw = filepath.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML config: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Expected top-level dict in YAML, got {type(data).__name__}")

    return _walk_and_interpolate(data)


# ---------------------------------------------------------------------------
# Singleton settings accessor
# ---------------------------------------------------------------------------

class _SettingsHolder:
    """Thread-safe lazy singleton for ``AppSettings``."""

    def __init__(self) -> None:
        self._settings: AppSettings | None = None
        self._lock = threading.Lock()

    def get(self) -> AppSettings:
        """Return the cached settings instance, creating it on first call."""
        if self._settings is None:
            with self._lock:
                if self._settings is None:
                    self._settings = AppSettings()
                    logger.info("Application settings loaded")
        return self._settings

    def override(self, settings: AppSettings) -> None:
        """Replace the cached settings (useful for testing)."""
        with self._lock:
            self._settings = settings
            logger.debug("Application settings overridden")

    def reset(self) -> None:
        """Clear the cached settings so the next ``get()`` reloads."""
        with self._lock:
            self._settings = None


_holder = _SettingsHolder()


def get_settings() -> AppSettings:
    """Public accessor for the global ``AppSettings`` singleton."""
    return _holder.get()


def override_settings(settings: AppSettings) -> None:
    """Override the global settings — primarily for tests."""
    _holder.override(settings)


def reset_settings() -> None:
    """Reset the global settings so the next access reloads from env."""
    _holder.reset()
