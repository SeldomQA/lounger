"""
Regression tests for JUnit result ingestion (``lounger.web_runner.results``).

Context: ``parse_junit`` hard-coded ``nodeid=None``, so a run result could only
be shown by ``name`` / ``classname`` and could never be traced back to a case in
the workspace tree. The runner already knows the run order — it writes the
selected node IDs to ``targets.json`` and passes that file to pytest as
``--run-json``, which replaces the collected queue with exactly that order — so
JUnit's testcases line up with that manifest positionally.

These tests deliberately avoid the ``tmp_path`` fixture: it depends on pytest's
temp-directory factory, which some sandboxed environments cannot use. They create
their scratch directory explicitly instead — under the repository when the
process temp area turns out to be unusable.
"""
import contextlib
import itertools
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from lounger.web_runner.results import MAX_JUNIT_BYTES, parse_junit

_counter = itertools.count()

#: Fallback scratch root used when the process temp area cannot be scanned.
_REPO_SCRATCH = Path(__file__).resolve().parent.parent / ".run-tmp" / "results-tests"


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001 - pytest hook signature
    """
    Remove this module's scratch directory after the session.

    The per-run directories are deleted as soon as each test finishes; the parent
    is removed here so repeated runs do not leave empty scaffolding behind. On
    sandboxed hosts removal can be denied (the files were created by a restricted
    token), in which case the leftover is harmless — ``.run-tmp/`` is ignored by
    git.
    """
    shutil.rmtree(_REPO_SCRATCH.parent, ignore_errors=True)


def _scratch_parent() -> str:
    """
    Return a directory we can create files in *and* enumerate.

    Sandboxes sometimes hand the process a temp directory whose newly created
    children cannot be listed or written to again; the repository tree is the
    reliable fallback there. ``tempfile.mkdtemp`` is not used: it creates 0o700
    directories, which a restricted token may not be able to write into.
    """
    try:
        candidate = tempfile.mkdtemp(prefix="lounger-scratch-check-")
        os.listdir(candidate)
        shutil.rmtree(candidate, ignore_errors=True)
        return tempfile.gettempdir()
    except OSError:
        _REPO_SCRATCH.mkdir(parents=True, exist_ok=True)
        return str(_REPO_SCRATCH)


@contextlib.contextmanager
def report(body: str):
    """Yield a JUnit XML path containing ``body``; the directory is removed after."""
    directory = os.path.join(_scratch_parent(), f"lounger-results-{os.getpid()}-{next(_counter)}")
    os.makedirs(directory, exist_ok=True)
    try:
        path = os.path.join(directory, "junit.xml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        yield path
    finally:
        shutil.rmtree(directory, ignore_errors=True)


SIMPLE = """<testsuites><testsuite name="pytest">
    <testcase classname="test_dir.test_sample" name="test_ok" time="0.25"/>
    <testcase classname="test_dir.test_sample" name="test_bad" time="0.5">
        <failure message="boom">trace</failure></testcase>
    <testcase classname="test_dir.test_sample" name="test_skip" time="0">
        <skipped message="skip"/></testcase>
</testsuite></testsuites>"""


# ── positional mapping (the manifest is the run order) ─────────────────────

def test_nodeids_are_taken_from_the_manifest_in_order():
    manifest = [
        "test_dir/test_sample.py::test_ok",
        "test_dir/test_sample.py::test_bad",
        "test_dir/test_sample.py::test_skip",
    ]
    with report(SIMPLE) as path:
        rows, counts = parse_junit(path, manifest)

    assert counts == dict(passed=1, failed=1, error=0, skipped=1, total=3)
    assert [row["nodeid"] for row in rows] == manifest
    assert [row["outcome"] for row in rows] == ["passed", "failed", "skipped"]


def test_manifest_order_wins_over_junit_order():
    """--run-json reorders the queue; the manifest mirrors that order."""
    manifest = ["test_dir/test_sample.py::test_bad", "test_dir/test_sample.py::test_ok"]
    xml = """<testsuites><testsuite>
        <testcase classname="test_dir.test_sample" name="test_bad" time="0.5">
            <failure message="boom"/></testcase>
        <testcase classname="test_dir.test_sample" name="test_ok" time="0.1"/>
    </testsuite></testsuites>"""
    with report(xml) as path:
        rows, _ = parse_junit(path, manifest)

    assert [row["nodeid"] for row in rows] == manifest
    assert rows[0]["outcome"] == "failed"


def test_missing_manifest_leaves_results_unattributed():
    """A legacy run has no manifest; nothing may be invented."""
    with report(SIMPLE) as path:
        rows, _ = parse_junit(path)

    assert all(row["nodeid"] is None for row in rows)


def test_empty_manifest_leaves_results_unattributed():
    with report(SIMPLE) as path:
        rows, _ = parse_junit(path, [])

    assert all(row["nodeid"] is None for row in rows)


# ── fallback when JUnit and the manifest disagree ──────────────────────────

def test_fewer_testcases_than_manifest_falls_back_to_name_matching():
    """
    A case that pytest did not report at all (e.g. a collection error elsewhere)
    must not shift every following result onto the wrong node ID.
    """
    manifest = [
        "test_dir/test_sample.py::test_missing",
        "test_dir/test_sample.py::test_bad",
    ]
    xml = """<testsuites><testsuite>
        <testcase classname="test_dir.test_sample" name="test_bad" time="0.5">
            <failure message="boom"/></testcase>
    </testsuite></testsuites>"""
    with report(xml) as path:
        rows, _ = parse_junit(path, manifest)

    assert len(rows) == 1
    assert rows[0]["nodeid"] == "test_dir/test_sample.py::test_bad"
    assert rows[0]["outcome"] == "failed"


def test_parametrized_names_are_matched_when_counts_differ():
    manifest = [
        "test_dir/test_sample.py::test_param[case_2]",
        "test_api.py::test_api[sample::case_1_step_1]",
    ]
    xml = """<testsuites><testsuite>
        <testcase classname="test_api" name="test_api[sample::case_1_step_1]" time="0.2"/>
    </testsuite></testsuites>"""
    with report(xml) as path:
        rows, _ = parse_junit(path, manifest)

    assert rows[0]["nodeid"] == "test_api.py::test_api[sample::case_1_step_1]"


def test_unresolvable_case_keeps_nodeid_none():
    """Never guess: an unmatched case stays unattributed rather than mislabelled."""
    manifest = ["test_dir/test_sample.py::test_other"]
    xml = """<testsuites><testsuite>
        <testcase classname="test_dir.elsewhere" name="test_unknown" time="0.1"/>
    </testsuite></testsuites>"""
    with report(xml) as path:
        rows, _ = parse_junit(path, manifest)

    assert rows[0]["nodeid"] is None


def test_each_manifest_entry_is_used_at_most_once():
    """Identical test names in different files must not share one node ID."""
    manifest = [
        "tests/test_dir/a_test.py::test_dup",
        "tests/test_dir/b_test.py::test_dup",
    ]
    xml = """<testsuites><testsuite>
        <testcase classname="tests.test_dir.b_test" name="test_dup" time="0.1"/>
        <testcase classname="tests.test_dir.a_test" name="test_dup" time="0.2"/>
    </testsuite></testsuites>"""
    with report(xml) as path:
        rows, _ = parse_junit(path, manifest)

    nodeids = [row["nodeid"] for row in rows]
    assert nodeids == [
        "tests/test_dir/b_test.py::test_dup",
        "tests/test_dir/a_test.py::test_dup",
    ]


# ── unchanged contracts ────────────────────────────────────────────────────

def test_counts_outcomes_and_payload_fields():
    manifest = ["x.py::a", "x.py::b", "x.py::c"]
    xml = """<testsuites><testsuite>
        <testcase classname="x" name="a" time="1.5"><system-out>out</system-out></testcase>
        <testcase classname="x" name="b" time="0"><failure message="bad">detail</failure></testcase>
        <testcase classname="x" name="c" time="0"><error message="err">setup</error></testcase>
    </testsuite></testsuites>"""
    with report(xml) as path:
        rows, counts = parse_junit(path, manifest)

    assert counts == dict(passed=1, failed=1, error=1, skipped=0, total=3)
    assert rows[0]["duration_ms"] == 1500
    assert rows[0]["stdout"] == "out"
    assert "bad" in rows[1]["failure_text"]
    assert rows[2]["outcome"] == "error"
    assert [row["nodeid"] for row in rows] == manifest


def test_unsupported_root_element_is_rejected():
    with report("<report/>") as path:
        with pytest.raises(ValueError, match="Unsupported JUnit root element"):
            parse_junit(path)


def test_size_guard_triggers_before_parsing():
    """The guard is a byte check, so it must fire before the XML is parsed."""
    with report("<testsuites/>") as path:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("lounger.web_runner.results.MAX_JUNIT_BYTES", 1)
            with pytest.raises(ValueError, match="exceeds 32 MiB"):
                parse_junit(path, ["a"])


def test_size_guard_limit_is_32_mib():
    assert MAX_JUNIT_BYTES == 32 * 1024 * 1024
