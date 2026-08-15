"""
Unified settings access for lounger.

Sources are consulted in order; the first source that returns a non-``None``
value wins.

Default source chain (via the module-level ``settings`` singleton):

1. :class:`EnvConfigSource` — environment variables (``LOUNGER_*``), so they
   override the YAML file without code changes;
2. :class:`YamlSettingsSource` — ``config/config.yaml``, located by walking up
   from the current working directory (project-root anchoring), with an
   mtime-based cache so editing the file is picked up without restarting.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml


class SettingsSource(Protocol):
    """
    Protocol for settings sources.
    """

    def get(self, key: str, default: Any = None, node: str | None = None) -> Any:
        """
        Return a setting value or default.
        """


def find_config_file(start: Path | None = None) -> Path | None:
    """
    Locate the project's ``config/config.yaml`` by walking up from ``start``
    (default: current working directory) until the filesystem root.

    The config file is the framework's fixed anchor: it always lives at
    ``<project_root>/config/config.yaml``.  This makes settings resolution
    independent of the directory pytest is launched from.

    :param start: Directory to start searching from (defaults to ``Path.cwd()``).
    :return: Absolute path to the found config file, or ``None``.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / "config" / "config.yaml"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


@dataclass
class YamlSettingsSource:
    """
    YAML-backed settings source.

    The config file is resolved through :func:`find_config_file` (project-root
    anchoring): unless an explicit path is given, the nearest
    ``config/config.yaml`` walking up from the CWD is used.  Parsed contents
    are cached and re-read only when the file's mtime changes.
    """

    config_file_path: str | None = None
    _cache_path: Path | None = field(default=None, repr=False, init=False)
    _cache_mtime: float | None = field(default=None, repr=False, init=False)
    _cache_data: dict[str, Any] | None = field(default=None, repr=False, init=False)

    def _load_config_data(self) -> dict[str, Any]:
        """Load and cache the YAML config, honoring file mtime changes.

        The config path is re-resolved on every call (cheap upward stat walk),
        so a change of working directory re-anchors the project root; only the
        parsed file contents are cached, keyed by path + mtime.
        """
        path = self._resolve_path()
        if path is None:
            return {}

        try:
            mtime = path.stat().st_mtime
        except OSError:
            return {}

        if self._cache_data is not None and self._cache_path == path and self._cache_mtime == mtime:
            return self._cache_data

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}
        self._cache_data = data
        self._cache_mtime = mtime
        self._cache_path = path
        return data

    def _resolve_path(self) -> Path | None:
        """Resolve the config file path (explicit path or upward search)."""
        if self.config_file_path:
            path = Path(self.config_file_path)
            if path.is_absolute():
                return path if path.is_file() else None
            resolved = (Path.cwd() / path).resolve()
            return resolved if resolved.is_file() else None
        return find_config_file()

    def get(self, key: str, default: Any = None, node: str | None = None) -> Any:
        config_data = self._load_config_data()
        try:
            if node is None:
                return config_data.get(key, default)
            node_values = config_data.get(node)
            if not isinstance(node_values, dict):
                return default
            return node_values.get(key, default)
        except Exception:
            return default


class EnvConfigSource:
    """
    Environment-variable settings source (overrides YAML).

    Convention:

    - top-level key:      ``LOUNGER_<KEY_UPPER>``  → ``get("key")``
    - key inside a node:  ``LOUNGER_<NODE_UPPER>__<KEY_UPPER>``
      (double underscore separates node and key) → ``get("key", node="node")``

    Examples::

        LOUNGER_BASE_URL=https://example.com
        LOUNGER_GLOBAL_TEST_CONFIG__VAR_ONE=42
    """

    PREFIX = "LOUNGER_"
    SEPARATOR = "__"

    @classmethod
    def _env_name(cls, key: str, node: str | None) -> str:
        name = cls.PREFIX + key.upper()
        if node is not None:
            name = cls.PREFIX + node.upper() + cls.SEPARATOR + key.upper()
        return name

    def get(self, key: str, default: Any = None, node: str | None = None) -> Any:
        env_name = self._env_name(key, node)
        value = os.environ.get(env_name)
        if value is None:
            return None
        return value


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
        self._default_sources = sources or [EnvConfigSource(), YamlSettingsSource()]
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
