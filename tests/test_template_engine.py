"""
Tests for template rendering and template-function validation.

Regression context: an unresolved ``${...}`` reference used to be replaced with
``None``. ``${extract(missing)}`` therefore injected a literal ``null`` into the
request body / header with no indication of what went wrong, and an unknown
symbol name produced a bare argument fragment (``${typo(x)}`` -> ``x``). Rendering
now leaves the reference exactly as written and reports the problem; collection
checks the case data up front so a typo is caught before anything runs.
"""
import pytest

from lounger.commons import template_engine
from lounger.runtime import clear_template_funcs, register_template_func
from lounger.utils import cache


@pytest.fixture(autouse=True)
def _clean_registry():
    """Keep the template registry and cache isolated per test."""
    clear_template_funcs()
    yield
    clear_template_funcs()
    cache.clear()


@pytest.fixture
def greet():
    register_template_func("greet", lambda who="x": f"hi {who}")
    return "greet"


# ── rendering: known references still resolve ──────────────────────────────

def test_registered_function_resolves(greet):
    assert template_engine._render_value("${greet(bob)}") == "hi bob"


def test_registered_function_resolves_inside_text(greet):
    assert template_engine._render_value("/users/${greet(bob)}") == "/users/hi bob"


def test_non_template_text_is_untouched():
    assert template_engine._render_value("plain text") == "plain text"
    assert template_engine._render_value("/posts/1") == "/posts/1"


def test_builtin_config_and_extract_resolve(monkeypatch):
    cache.set({"token": "abc123"})

    assert template_engine._render_value("${extract(token)}") == "abc123"


def test_nested_reference_resolves(greet):
    cache.set({"who": "sam"})

    assert template_engine._render_value("${greet($who)}") == "hi sam"


# ── rendering: unresolved references stay as written ───────────────────────

def test_unknown_function_is_left_as_written():
    """A typo must not turn into a bare argument fragment."""
    assert template_engine._render_value("${typo(id)}") == "${typo(id)}"
    assert template_engine._render_value("/u/${typo(id)}") == "/u/${typo(id)}"


def test_missing_cache_value_is_left_as_written():
    """The original bug: this used to become None (a literal ``null``)."""
    assert template_engine._render_value("${extract(missing)}") == "${extract(missing)}"


def test_missing_cache_value_inside_text_is_left_as_written():
    assert template_engine._render_value("Bearer ${extract(missing)}") == "Bearer ${extract(missing)}"


def test_unresolved_value_is_not_duplicated_in_text():
    """The embedded case must not re-substitute the whole input."""
    assert template_engine._render_value("<${extract(nope)}>") == "<${extract(nope)}>"


def test_exception_inside_a_function_leaves_the_reference():
    def boom(value):
        raise RuntimeError("nope")

    register_template_func("boom", boom)

    assert template_engine._render_value("${boom(1)}") == "${boom(1)}"


def test_valid_values_are_not_affected_by_the_none_rule(greet):
    """A legitimately false-y but present value still resolves."""
    cache.set({"count": 0, "empty": ""})

    assert template_engine._render_value("${extract(count)}") == 0
    assert template_engine._render_value("${extract(empty)}") == ""


# ── template_replace on a whole case ───────────────────────────────────────

def test_template_replace_keeps_unresolved_references(greet):
    case = {
        "url": "/posts/${extract(none)}",
        "headers": {"Authorization": "Bearer ${extract(missing)}", "X-Ok": "${greet(bob)}"},
        "body": {"n": 1, "nested": [{"v": "${typo(1)}"}]},
    }

    replaced = template_engine.template_replace(case)

    assert replaced["url"] == "/posts/${extract(none)}"
    assert replaced["headers"]["Authorization"] == "Bearer ${extract(missing)}"
    assert replaced["headers"]["X-Ok"] == "hi bob"
    assert replaced["body"]["n"] == 1
    assert replaced["body"]["nested"][0]["v"] == "${typo(1)}"


# ── collection-time validation ─────────────────────────────────────────────

def test_undefined_template_functions_finds_all_symbols(greet):
    case = {
        "request": {"url": "/u/${greet(a)}/${nope(1)}"},
        "steps": [{"deep": "${alsoMissing(2)}"}],
    }

    assert template_engine.undefined_template_functions(case) == ["alsoMissing", "nope"]


def test_undefined_template_functions_ignores_registered_and_builtin(greet):
    case = {"a": "${greet(x)}", "b": "${config(base_url)}", "c": "${extract(token)}"}

    assert template_engine.undefined_template_functions(case) == []


def test_undefined_template_functions_scans_non_string_values_safely():
    assert template_engine.undefined_template_functions({"n": 1, "b": True, "x": None}) == []


def test_validate_warns_and_returns_the_missing_names(caplog):
    missing = template_engine.validate_template_functions(
        {"url": "${nope(1)}"}, "datas/x.yaml case_2"
    )

    assert missing == ["nope"]


def test_validate_is_silent_when_everything_is_registered(greet):
    assert template_engine.validate_template_functions({"url": "${greet(a)}"}) == []


def test_strict_mode_raises(monkeypatch):
    """``LOUNGER_STRICT_TEMPLATES`` turns the warning into a hard failure."""
    monkeypatch.setenv(template_engine.STRICT_ENV, "1")

    with pytest.raises(template_engine.UndefinedTemplateFunction, match="nope"):
        template_engine.validate_template_functions({"url": "${nope(1)}"}, "case_1")


def test_strict_mode_accepts_resolved_cases(greet, monkeypatch):
    monkeypatch.setenv(template_engine.STRICT_ENV, "true")

    assert template_engine.validate_template_functions({"url": "${greet(a)}"}) == []


@pytest.mark.parametrize("value", ["0", "false", "off", ""])
def test_non_strict_values_keep_warning_mode(monkeypatch, value):
    monkeypatch.setenv(template_engine.STRICT_ENV, value)

    assert template_engine.validate_template_functions({"url": "${nope(1)}"}) == ["nope"]
