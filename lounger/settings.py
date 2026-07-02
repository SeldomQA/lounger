"""
Unified settings access for lounger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from lounger.utils.config_utils import ConfigUtils


class SettingsSource(Protocol):
    """
    Protocol for settings sources.
    """

    def get(self, key: str, default: Any = None, node: str | None = None) -> Any:
        """
        Return a setting value or default.
        """


@dataclass
class YamlSettingsSource:
    """
    YAML-backed settings source.
    """

    config_file_path: str = "config/config.yaml"

    def get(self, key: str, default: Any = None, node: str | None = None) -> Any:
        config_utils = ConfigUtils(self.config_file_path)
        if not config_utils.is_exists():
            return default

        try:
            if node is None:
                return config_utils.get_config(key)
            values = config_utils.get_config(node)
        except Exception:
            return default

        if not isinstance(values, dict):
            return default
        return values.get(key, default)


@dataclass
class DictSettingsSource:
    """
    In-memory settings source, mainly for tests or custom embedding.
    """

    values: dict[str, Any]

    def get(self, key: str, default: Any = None, node: str | None = None) -> Any:
        if node is None:
            return self.values.get(key, default)

        node_values = self.values.get(node, {})
        if not isinstance(node_values, dict):
            return default
        return node_values.get(key, default)


class Settings:
    """
    Unified settings accessor with pluggable sources.
    """

    def __init__(self, sources: list[SettingsSource] | None = None):
        self._default_sources = sources or [YamlSettingsSource()]
        self._sources = list(self._default_sources)

    def set_sources(self, sources: list[SettingsSource]) -> None:
        """
        Replace settings sources.
        """
        self._sources = list(sources)

    def reset_sources(self) -> None:
        """
        Reset to default settings sources.
        """
        self._sources = list(self._default_sources)

    def add_source(self, source: SettingsSource, prepend: bool = False) -> None:
        """
        Add a settings source.
        """
        if prepend:
            self._sources.insert(0, source)
        else:
            self._sources.append(source)

    def get(self, key: str, default: Any = None, node: str | None = None) -> Any:
        """
        Get a setting from the configured sources.
        """
        for source in self._sources:
            value = source.get(key, default=None, node=node)
            if value is not None:
                return value
        return default

    def require(self, key: str, node: str | None = None) -> Any:
        """
        Get a required setting or raise KeyError.
        """
        value = self.get(key, default=None, node=node)
        if value is None:
            full_key = f"{node}.{key}" if node else key
            raise KeyError(f"Setting '{full_key}' not found")
        return value

    def get_int(self, key: str, default: int | None = None, node: str | None = None) -> int | None:
        """
        Get an integer setting.
        """
        value = self.get(key, default=default, node=node)
        if value is None:
            return None
        return int(value)

    def get_bool(self, key: str, default: bool = False, node: str | None = None) -> bool:
        """
        Get a boolean setting.
        """
        value = self.get(key, default=default, node=node)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}

    def get_dict(self, node: str) -> dict[str, Any]:
        """
        Get a dictionary-like node.
        """
        value = self.get(node, default=None, node=None)
        if isinstance(value, dict):
            return value
        return {}


settings = Settings()
