from lounger.commons.load_config import global_test_config
from lounger.settings import DictSettingsSource, Settings, YamlSettingsSource


def test_settings_yaml_access(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "\n".join(
            [
                "base_url: https://example.com",
                "test_project:",
                "  sample: true",
                "global_test_config:",
                "  var_one: foo",
                "  port: '3306'",
                "  enabled: 'true'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    local_settings = Settings([YamlSettingsSource()])

    assert local_settings.get("base_url") == "https://example.com"
    assert local_settings.get("sample", node="test_project") is True
    assert local_settings.get("var_one", node="global_test_config") == "foo"
    assert local_settings.get_int("port", node="global_test_config") == 3306
    assert local_settings.get_bool("enabled", node="global_test_config") is True


def test_settings_source_override():
    local_settings = Settings([DictSettingsSource({"global_test_config": {"var_one": "yaml"}})])
    local_settings.add_source(
        DictSettingsSource({"global_test_config": {"var_one": "override"}}),
        prepend=True,
    )

    assert local_settings.get("var_one", node="global_test_config") == "override"


def test_global_test_config_compatibility(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "\n".join(
            [
                "global_test_config:",
                "  var_one: foo",
                "  var_two: bar",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert global_test_config("var_one") == "foo"
    assert global_test_config("var_two") == "bar"
