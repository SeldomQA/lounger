import warnings

import pytest

from lounger.runtime import (
    clear_template_funcs,
    get_all_template_funcs,
    get_template_func,
    register_template_func,
)
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

    # The auto-scan fallback is deprecated: creating the extractor must warn.
    with pytest.warns(DeprecationWarning, match="Auto-scanning"):
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

    # The explicit registry path must NOT trigger the deprecation warning.
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        extractor = ExtractVar()

    assert extractor.cwd() == str(tmp_path)
    with pytest.raises(AttributeError):
        getattr(extractor, "helper")


def test_register_template_func_api(tmp_path, monkeypatch):
    """The official registration API works end-to-end via ExtractVar."""
    monkeypatch.chdir(tmp_path)
    ExtractVar.reset()
    clear_template_funcs()

    def double(n):
        return n * 2

    # register returns the callable (usable as a decorator)
    assert register_template_func("double", double) is double
    assert get_template_func("double") is double
    assert get_all_template_funcs() == {"double": double}

    extractor = ExtractVar()
    assert extractor.double(21) == 42

    # overwriting an existing name is allowed
    register_template_func("double", lambda n: n + 1)
    assert extractor.double(21) == 22

    # unknown name -> AttributeError via ExtractVar, KeyError via registry
    with pytest.raises(AttributeError):
        getattr(extractor, "missing_func")
    with pytest.raises(KeyError):
        get_template_func("missing_func")

    # non-callable registration is rejected
    with pytest.raises(TypeError, match="must be callable"):
        register_template_func("not_a_func", 42)

    clear_template_funcs()
    with pytest.raises(KeyError):
        get_template_func("double")


def test_extract_var_register_api_in_conftest_no_warning(tmp_path, monkeypatch):
    """conftest using register_template_func() directly must not trigger the
    deprecated auto-scan path."""
    (tmp_path / "conftest.py").write_text(
        "\n".join(
            [
                "from lounger.runtime import register_template_func",
                "",
                "def triple(n):",
                "    return int(n) * 3",
                "",
                "register_template_func('triple', triple)",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    ExtractVar.reset()

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        extractor = ExtractVar()

    assert extractor.triple(3) == 9


def test_extract_var_reset_clears_runtime_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no conftest.py in cwd
    ExtractVar.reset()
    register_template_func("helper", lambda: "ok")

    extractor = ExtractVar()
    assert extractor.helper() == "ok"

    ExtractVar.reset()
    # registry is cleared: the old instance can no longer resolve the function
    assert get_all_template_funcs() == {}
    with pytest.raises(AttributeError):
        extractor.helper()
