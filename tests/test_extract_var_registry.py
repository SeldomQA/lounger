import pytest

from lounger.utils.variables import ExtractVar


def test_extract_var_auto_loads_only_module_functions(tmp_path, monkeypatch):
    (tmp_path / "conftest.py").write_text(
        "\n".join(
            [
                "from math import ceil",
                "from pathlib import Path",
                "",
                "class HelperClass:",
                "    pass",
                "",
                "def helper():",
                "    return 'ok'",
                "",
                "def _private_helper():",
                "    return 'secret'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    ExtractVar.reset()

    extractor = ExtractVar()

    assert extractor.helper() == "ok"
    assert extractor._private_helper() == "secret"
    with pytest.raises(AttributeError):
        getattr(extractor, "ceil")
    with pytest.raises(AttributeError):
        getattr(extractor, "Path")
    with pytest.raises(AttributeError):
        getattr(extractor, "HelperClass")


def test_extract_var_explicit_registry_takes_precedence(tmp_path, monkeypatch):
    (tmp_path / "conftest.py").write_text(
        "\n".join(
            [
                "from os import getcwd",
                "",
                "def helper():",
                "    return 'helper'",
                "",
                "LOUNGER_TEMPLATE_FUNCTIONS = {",
                "    'cwd': getcwd,",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    ExtractVar.reset()

    extractor = ExtractVar()

    assert extractor.cwd() == str(tmp_path)
    with pytest.raises(AttributeError):
        getattr(extractor, "helper")
