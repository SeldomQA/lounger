"""
Tests for settings anchoring (3.4), lazy base_url, EnvConfigSource and
ConfigUtils deprecation.

Covers the acceptance points of docs/development_plan.md §3.4:

- project-root anchoring: ``config/config.yaml`` is found by walking up from
  the CWD, so settings survive a change of working directory;
- lazy ``base_url``: editing the config file is picked up without restarting;
- ``EnvConfigSource``: ``LOUNGER_*`` environment variables override YAML;
- ``ConfigUtils`` deprecation warning.
"""

import pytest

from lounger.commons.load_config import base_url
from lounger.settings import (
    DictSettingsSource,
    EnvConfigSource,
    Settings,
    YamlSettingsSource,
    find_config_file,
    settings,
)
from lounger.utils.config_utils import ConfigUtils

CONFIG_TEXT = "\n".join(
    [
        "base_url: https://example.com",
        "global_test_config:",
        "  var_one: foo",
        "  port: '3306'",
        "  enabled: 'true'",
    ]
)


def _write_config(tmp_path, text=CONFIG_TEXT):
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.yaml"
    config_file.write_text(text, encoding="utf-8")
    return config_file


# ── project-root anchoring ────────────────────────────────────────────────

def test_find_config_file_walks_up_from_subdirectory(tmp_path):
    config_file = _write_config(tmp_path)
    deep_dir = tmp_path / "a" / "b" / "c"
    deep_dir.mkdir(parents=True)

    found = find_config_file(start=deep_dir)

    assert found is not None
    assert found.resolve() == config_file.resolve()


def test_find_config_file_returns_none_when_missing(tmp_path):
    assert find_config_file(start=tmp_path) is None


def test_yaml_settings_source_anchors_project_root(tmp_path, monkeypatch):
    """Settings work even when CWD is a nested subdirectory."""
    _write_config(tmp_path)
    deep_dir = tmp_path / "src" / "tests"
    deep_dir.mkdir(parents=True)
    monkeypatch.chdir(deep_dir)

    local_settings = Settings([YamlSettingsSource()])

    assert local_settings.get("base_url") == "https://example.com"
    assert local_settings.get("var_one", node="global_test_config") == "foo"


def test_yaml_settings_source_explicit_path(tmp_path):
    """An explicit config_file_path is honored as-is (relative to CWD)."""
    _write_config(tmp_path)
    local_settings = Settings([YamlSettingsSource(config_file_path=str(tmp_path / "config" / "config.yaml"))])
    assert local_settings.get("base_url") == "https://example.com"


# ── mtime cache invalidation ──────────────────────────────────────────────

def test_settings_reflects_config_edit_without_reload(tmp_path, monkeypatch):
    """Editing the YAML file must be picked up by the next get()."""
    config_file = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    local_settings = Settings([YamlSettingsSource()])

    assert local_settings.get("base_url") == "https://example.com"

    config_file.write_text("base_url: https://new-host.example.com\n", encoding="utf-8")
    # Force a different mtime even on coarse-resolution filesystems.
    import os
    os.utime(config_file, (os.stat(config_file).st_atime + 2, os.stat(config_file).st_mtime + 2))

    assert local_settings.get("base_url") == "https://new-host.example.com"


# ── EnvConfigSource ───────────────────────────────────────────────────────

def test_env_config_source_overrides_yaml(tmp_path, monkeypatch):
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOUNGER_BASE_URL", "https://from-env.example.com")

    local_settings = Settings([EnvConfigSource(), YamlSettingsSource()])

    assert local_settings.get("base_url") == "https://from-env.example.com"
    # unset key falls through to YAML
    assert local_settings.get("var_one", node="global_test_config") == "foo"


def test_env_config_source_node_key(tmp_path, monkeypatch):
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOUNGER_GLOBAL_TEST_CONFIG__VAR_ONE", "from-env")

    local_settings = Settings([EnvConfigSource(), YamlSettingsSource()])

    assert local_settings.get("var_one", node="global_test_config") == "from-env"


def test_env_config_source_precedence_with_prepend(tmp_path, monkeypatch):
    """EnvConfigSource prepended wins over YAML in the default singleton chain."""
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOUNGER_BASE_URL", "https://env-wins.example.com")

    assert settings.get("base_url") == "https://env-wins.example.com"


# ── lazy base_url compatibility ───────────────────────────────────────────

def test_get_base_url_is_lazy_and_returns_current_value(tmp_path, monkeypatch):
    config_file = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert base_url() == "https://example.com"

    config_file.write_text("base_url: https://changed.example.com\n", encoding="utf-8")
    import os
    os.utime(config_file, (os.stat(config_file).st_atime + 2, os.stat(config_file).st_mtime + 2))

    assert base_url() == "https://changed.example.com"


def test_base_url_module_attribute_compat(tmp_path, monkeypatch):
    """
    `from lounger.commons.load_config import base_url` still works in all
    historical usage forms: value, legacy function call, and str methods.
    """
    import lounger.commons.load_config as load_config_mod

    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Real module attribute (visible to hasattr / dir / IDEs)
    assert hasattr(load_config_mod, "base_url")

    from lounger.commons.load_config import base_url

    # value usage
    assert base_url == "https://example.com"
    assert f"{base_url}/posts/1" == "https://example.com/posts/1"
    assert "prefix-" + base_url == "prefix-https://example.com"
    # legacy function-call usage (CHANGES.md: base_url() → base_url variable)
    assert base_url() == "https://example.com"
    # str methods forwarded to the current value
    assert base_url.startswith("https://")
    assert base_url.split("//")[1] == "example.com"


def test_base_url_lazy_proxy_reflects_config_edit(tmp_path, monkeypatch):
    """The compat proxy reads the *current* value on every access."""
    from lounger.commons.load_config import base_url

    config_file = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert base_url == "https://example.com"

    config_file.write_text("base_url: https://edited.example.com\n", encoding="utf-8")
    import os
    os.utime(config_file, (os.stat(config_file).st_atime + 2, os.stat(config_file).st_mtime + 2))

    assert base_url == "https://edited.example.com"
    assert base_url() == "https://edited.example.com"


# ── ConfigUtils deprecation ───────────────────────────────────────────────

def test_config_utils_is_deprecated(tmp_path):
    with pytest.warns(DeprecationWarning, match="deprecated"):
        ConfigUtils(str(tmp_path / "config" / "config.yaml"))


# ── source override helpers still work ────────────────────────────────────

def test_settings_source_override():
    local_settings = Settings([DictSettingsSource({"global_test_config": {"var_one": "yaml"}})])
    local_settings.add_source(
        DictSettingsSource({"global_test_config": {"var_one": "override"}}),
        prepend=True,
    )

    assert local_settings.get("var_one", node="global_test_config") == "override"


def test_settings_get_int_bool_through_yaml(tmp_path, monkeypatch):
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    local_settings = Settings([YamlSettingsSource()])

    assert local_settings.get_int("port", node="global_test_config") == 3306
    assert local_settings.get_bool("enabled", node="global_test_config") is True


# ── RequestClient lazy session (3.4: no import-time binding) ──────────────

def test_request_client_session_rebinds_on_base_url_change(tmp_path, monkeypatch):
    """The request client must not hold an import-time base_url snapshot."""
    from lounger.request.request_client import RequestClient

    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    client = RequestClient()

    first = client._get_session()
    assert first.base_url == "https://example.com"

    # Simulate the YAML file being edited while the process stays alive.
    config_file = tmp_path / "config" / "config.yaml"
    config_file.write_text("base_url: https://changed.example.com\n", encoding="utf-8")
    import os
    os.utime(config_file, (os.stat(config_file).st_atime + 2, os.stat(config_file).st_mtime + 2))

    second = client._get_session()
    assert second is not first
    assert second.base_url == "https://changed.example.com"


def test_request_client_import_does_not_evaluate_settings(tmp_path, monkeypatch):
    """Importing the module must not read settings (no import-time binding)."""
    import sys

    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Import in a clean-ish state: the module-level singleton is created at
    # import time; make sure creating it did not touch the config file.
    from lounger.request import request_client  # noqa: F401

    assert request_client._session is None
    assert sys.modules["lounger.request.request_client"].request_client._session is None
