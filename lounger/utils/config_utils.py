"""
Configuration utility class for loading and accessing YAML configuration files.

Supports layered loading of multiple config files: files are parsed in the
order they are passed, and later files override same-named keys of earlier
files (node-level deep merge).

Typical usage:
    config = ConfigUtils("config/config.yaml", "config/config.local.yaml")
    config.get_config("bff_develop")   # -> {"base_url": "...", "api_key": "...", ...}

Merge rules (node-level deep merge):
    - both base and override values are dicts: merge recursively, override
      wins for same-named keys
    - base value is a str and override is a dict: treated as a URL shorthand,
      result = {"base_url": <base string>, **override}
      (e.g. base has bff_develop: https://..., local has bff_develop: {auth: ...})
    - otherwise: override fully replaces base
"""
import os
from typing import Any, Dict, Optional, Tuple

import yaml

from lounger.log import log

# Cached parse results keyed by file path, so that multiple ConfigUtils
# instances reading the same files do not re-parse them.
_FILE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _load_yaml_file(path: str) -> Dict[str, Any]:
    """Read and cache a YAML file (cache is invalidated by mtime)."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        log.error(f"Configuration file not found: {path}")
        raise

    cached = _FILE_CACHE.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        data = {}
    _FILE_CACHE[path] = (mtime, data)
    return data


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Deep-merge override into base in place; override wins for same-named keys."""
    for key, value in override.items():
        base_value = base.get(key)
        if isinstance(value, dict) and isinstance(base_value, dict):
            _deep_merge(base_value, value)
        elif isinstance(value, dict) and isinstance(base_value, str):
            # URL shorthand: a plain string in base is treated as the node's base_url
            base[key] = {"base_url": base_value, **value}
        else:
            base[key] = value


class ConfigUtils:
    """
    Configuration utility for layered loading of YAML files and accessing
    a config node (or a specific key within a node).

    The old single-file usage ConfigUtils("config/config.yaml") remains fully
    compatible; the new multi-file usage
    ConfigUtils("config/config.yaml", "config/config.local.yaml") supports
    per-user private config overrides.
    """

    def __init__(self, *config_file_paths: str):
        if not config_file_paths:
            raise ValueError("ConfigUtils requires at least one config file path")
        self.config_file_paths = config_file_paths
        # Kept for backward compatibility with code accessing config_file_path
        self.config_file_path = config_file_paths[0]
        self._data = self._load_config_data()

    def _load_config_data(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for path in self.config_file_paths:
            data = _load_yaml_file(path)
            if not isinstance(data, dict):
                log.warning(f"Configuration file is not a mapping: {path}")
                continue
            _deep_merge(merged, data)
        return merged

    def is_exists(self) -> bool:
        """True if at least one configured config file exists."""
        return any(os.path.exists(p) for p in self.config_file_paths)

    def get_config(self, config_node: str, config_key: Optional[str] = None) -> Any:
        """
        Get the config of the given node; if config_key is given, return the
        value of that key within the node.

        :param config_node: Name of the configuration node
        :param config_key: Optional key within the configuration node
        """
        try:
            if config_node not in self._data:
                log.warning(f"Configuration node '{config_node}' not found")
                raise KeyError(f"Configuration node '{config_node}' not found")

            if config_key is not None:
                node = self._data[config_node]
                if not isinstance(node, dict) or config_key not in node:
                    log.warning(f"Configuration key '{config_key}' not found in node '{config_node}'")
                    raise KeyError(f"Configuration key '{config_key}' not found in node '{config_node}'")
                return node[config_key]

            return self._data[config_node]
        except Exception as e:
            log.error(f"Failed to get configuration: {e}")
            raise e
