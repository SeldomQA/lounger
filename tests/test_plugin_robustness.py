"""
Robustness tests for lounger.plugin (docs/development_plan.md §3.7).

Covers:

- ``--html-title`` / ``--env`` default is ``None`` (semantically correct);
- failure-screenshot logic is extracted into a testable function;
- ``--run-json`` execution protocol: ordered execution, missing-case
  warning, exit on missing/invalid file;
- docstring decoration in ``pytest_collection_modifyitems`` (plain
  function and bound method) produces the expected docstring.
"""
import json
import sys
from types import SimpleNamespace

import pytest

from lounger import plugin

pytest_plugins = ["pytester"]

# ── log console handler stability ─────────────────────────────────────────

def test_console_log_handler_bound_to_real_stderr():
    """Logging must survive pytest replacing/closing sys.stderr (per-session
    capture, nested pytester sessions).

    ``setup_log`` binds the loguru console handler to ``sys.__stderr__`` (the
    real interpreter stderr, never closed) instead of the captured
    ``sys.stderr`` — otherwise loguru writes to a closed stream and every
    later log call emits "I/O operation on closed file".
    """
    import io

    from loguru import logger

    fake_stderr = io.StringIO()
    saved = sys.stderr
    sys.stderr = fake_stderr  # simulate pytest capture replacing stderr
    try:
        plugin._configure_logging("<level>{message}</level>")
    finally:
        sys.stderr = saved

    # loguru internals (loguru 0.7.x): Handler._sink is a StreamSink holding
    # the stream the console handler writes to.
    streams = []
    for handler in logger._core.handlers.values():
        sink = getattr(handler, "_sink", None)
        stream = getattr(sink, "_stream", None)
        if stream is not None:
            streams.append(stream)

    assert streams, "no console handler found"
    assert any(s is sys.__stderr__ for s in streams), (
        f"console handler not bound to real stderr: {streams!r}"
    )
    assert not any(s is fake_stderr for s in streams), (
        f"console handler bound to pytest-captured stderr: {streams!r}"
    )

# ── option defaults ───────────────────────────────────────────────────────

def test_html_title_and_env_default_to_none():
    """--html-title / --env default=None instead of [] (semantic correctness)."""
    class _FakeGroup:
        def __init__(self):
            self.option_list = []

        def addoption(self, *args, **kwargs):
            # addoption("--html-title", action=..., default=..., help=...)
            self.option_list.append((args[0], kwargs))

    fake_group = _FakeGroup()
    parser = SimpleNamespace(getgroup=lambda *a, **kw: fake_group)

    plugin.pytest_addoption(parser)

    defaults = {}
    for optstring, kwargs in fake_group.option_list:
        if optstring:
            defaults[optstring] = kwargs.get("default")

    assert defaults.get("--html-title") is None
    assert defaults.get("--env") is None


# ── failure screenshot extraction ─────────────────────────────────────────

class _FakeItem:
    def __init__(self, page=None):
        self.funcargs = {"page": page}


class _FakeHtml:
    class extras:
        @staticmethod
        def image(image, mime_type=None):
            return {"__image__": image, "mime": mime_type}


def test_screenshot_attached_on_failed_call(monkeypatch):
    monkeypatch.setattr("lounger.plugin.screenshot_base64", lambda page: "BASE64IMG")

    extra = []
    item = _FakeItem(page=object())
    report = SimpleNamespace(failed=True, skipped=False)

    attached = plugin._attach_failure_screenshot(item, report, _FakeHtml, extra)

    assert attached is True
    assert extra == [{"__image__": "BASE64IMG", "mime": "image/png"}]


def test_screenshot_attached_on_xfail_skipped(monkeypatch):
    monkeypatch.setattr("lounger.plugin.screenshot_base64", lambda page: "BASE64IMG")

    extra = []
    item = _FakeItem(page=object())
    report = SimpleNamespace(failed=True, skipped=True, wasxfail=True)  # xfail → skipped+wasxfail

    attached = plugin._attach_failure_screenshot(item, report, _FakeHtml, extra)

    assert attached is True


def test_screenshot_not_attached_on_pass_or_without_page(monkeypatch):
    calls = {"n": 0}

    def fake_base64(page):
        calls["n"] += 1
        return "IMG"

    monkeypatch.setattr("lounger.plugin.screenshot_base64", fake_base64)

    # passed case → no screenshot
    extra = []
    attached = plugin._attach_failure_screenshot(
        _FakeItem(page=object()), SimpleNamespace(failed=False, skipped=False), _FakeHtml, extra
    )
    assert attached is False
    assert extra == []

    # failed case but no page → no screenshot, base64 never called
    attached = plugin._attach_failure_screenshot(
        _FakeItem(page=None), SimpleNamespace(failed=True, skipped=False), _FakeHtml, extra
    )
    assert attached is False
    assert calls["n"] == 0


def test_screenshot_no_html_plugin_returns_false(monkeypatch):
    monkeypatch.setattr("lounger.plugin.screenshot_base64", lambda page: "BASE64IMG")

    extra = []
    attached = plugin._attach_failure_screenshot(
        _FakeItem(page=object()), SimpleNamespace(failed=True, skipped=False), None, extra
    )

    assert attached is False  # no plugin → nothing appended


# ── --run-json protocol ───────────────────────────────────────────────────

def _fake_config(run_json_path=None):
    return SimpleNamespace(getoption=lambda name: run_json_path if name == "--run-json" else None)


def _fake_item(nodeid, doc="original doc"):
    return SimpleNamespace(
        nodeid=nodeid,
        _obj=SimpleNamespace(__doc__=doc),
    )


def test_run_json_reorders_items_in_order(tmp_path):
    run_json = tmp_path / "run.json"
    run_json.write_text(
        json.dumps([{"nodeid": "b::t2"}, {"nodeid": "a::t1"}, {"nodeid": "c::t3"}]),
        encoding="utf-8",
    )

    items = [_fake_item("a::t1"), _fake_item("b::t2"), _fake_item("c::t3")]
    plugin.pytest_collection_modifyitems(_fake_config(str(run_json)), items)

    assert [i.nodeid for i in items] == ["b::t2", "a::t1", "c::t3"]


def test_run_json_missing_case_warns_and_skips(tmp_path, monkeypatch):
    run_json = tmp_path / "run.json"
    run_json.write_text(json.dumps([{"nodeid": "b::t2"}, {"nodeid": "missing::case"}]), encoding="utf-8")

    warnings = []
    monkeypatch.setattr("lounger.plugin.log.warning", lambda msg: warnings.append(msg))

    items = [_fake_item("a::t1"), _fake_item("b::t2")]
    plugin.pytest_collection_modifyitems(_fake_config(str(run_json)), items)

    # missing case is skipped, the rest run in JSON order
    assert [i.nodeid for i in items] == ["b::t2"]
    assert any("missing::case" in msg for msg in warnings)


def test_run_json_missing_file_exits(tmp_path):
    from _pytest.outcomes import Exit

    with pytest.raises(Exit):
        plugin.pytest_collection_modifyitems(
            _fake_config(str(tmp_path / "nope.json")), [_fake_item("a::t1")]
        )


def test_run_json_invalid_json_exits(tmp_path):
    from _pytest.outcomes import Exit

    run_json = tmp_path / "run.json"
    run_json.write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(Exit):
        plugin.pytest_collection_modifyitems(_fake_config(str(run_json)), [_fake_item("a::t1")])


# ── docstring decoration in pytest_collection_modifyitems ─────────────────

def test_collection_decorates_plain_function_docstring():
    def sample():
        """my original doc"""
        return None

    item = SimpleNamespace(
        nodeid="test_x.py::test_y",
        callspec=SimpleNamespace(params={"params": {"test_case": "case_a"}}),
        _obj=sample,
    )

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert item._obj.__doc__ == "my original doc | case_a"


def test_collection_decorates_bound_method_docstring_and_keeps_self():
    class TestClass:
        def test_sample(self):
            """class doc"""
            return self

    instance = TestClass()
    bound = instance.test_sample

    item = SimpleNamespace(
        nodeid="test_x.py::TestClass::test_sample",
        callspec=SimpleNamespace(params={"params": {"test_scene": "scene_b"}}),
        _obj=bound,
    )

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert item._obj.__doc__ == "class doc | scene_b"
    # bound method must keep working with `self` (re-bound to same instance)
    assert item._obj() is instance


def test_collection_skips_non_function_callables():
    """functools.partial / other callables must not crash collection."""
    from functools import partial

    def sample():
        """doc"""
        return None

    item = SimpleNamespace(
        nodeid="test_x.py::test_y",
        callspec=SimpleNamespace(params={"params": {"test_case": "case_a"}}),
        _obj=partial(sample),
    )

    # must not raise and must not replace the object
    plugin.pytest_collection_modifyitems(_fake_config(), [item])
    assert isinstance(item._obj, partial)


# ── end-to-end: --run-json in a real pytest session ───────────────────────

def test_run_json_end_to_end_reorders_execution(pytester):
    """A real pytest run executes tests in the order given by --run-json."""
    # Isolate from state left by earlier tests in this process: the lounger
    # plugin keeps per-item timing/finish sets and a hook registry that must
    # not leak into the inner pytest session (pytester runs in-process).
    from lounger.plugin_hooks import reset_hooks

    plugin._item_start_times.clear()
    plugin._item_finished.clear()
    reset_hooks()

    pytester.makepyfile(
        test_order="""
        ORDER = []

        def test_a():
            ORDER.append("a")

        def test_b():
            ORDER.append("b")

        def test_c():
            ORDER.append("c")

        def test_dump_order():
            # write the observed order to a file for the outer test to read
            import json
            with open("order.json", "w", encoding="utf-8") as f:
                json.dump(ORDER, f)
        """
    )

    run_json = pytester.path / "run.json"
    # JSON order: c, a, then dump (writes observed ORDER to file)
    run_json.write_text(
        json.dumps(
            [
                {"nodeid": "test_order.py::test_c"},
                {"nodeid": "test_order.py::test_a"},
                {"nodeid": "test_order.py::test_dump_order"},
            ]
        ),
        encoding="utf-8",
    )

    # Run the whole file in a SUBPROCESS: --run-json reorders execution per
    # the JSON. A subprocess is required because pytest-playwright >= 0.8
    # wraps every test in a module-global soft-assertion scope; running a
    # nested pytest session in-process (pytester.runpytest) would re-enter
    # that scope and fail every inner test with "nested soft assertion scopes
    # are not supported". Subprocess isolation also shields the inner run from
    # any other plugin state left by the outer process.
    result = pytester.runpytest_subprocess(f"--run-json={run_json}")

    result.assert_outcomes(passed=3)
    order_file = pytester.path / "order.json"
    observed = json.loads(order_file.read_text(encoding="utf-8"))
    assert observed == ["c", "a"], f"expected run order [c, a], got {observed}"
