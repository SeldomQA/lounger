"""JUnit ingestion without guessing pytest node IDs from display names.

The runner writes the ordered selection to ``targets.json`` before starting
pytest and passes it as ``--run-json``; lounger's plugin replaces the collected
queue with that order, so JUnit emits one ``<testcase>`` per entry in exactly
that order. The manifest is therefore the authoritative source of node IDs, and
:func:`parse_junit` uses it to attach a ``nodeid`` to every result — which is
what lets a run result be traced back to a case in the workspace tree.

Alignment is positional — the run order is deterministic — but a position is
only trusted when the testcase there actually refers to that node ID; anything
that does not line up is resolved by a file/name fallback, and what remains
unresolved keeps ``nodeid=None`` rather than being guessed.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree

#: Upper bound for the JUnit report we are willing to parse.
MAX_JUNIT_BYTES = 32 * 1024 * 1024


def _location_matches(nodeid: str, classname: str, name: str) -> bool:
    """
    Return True when a nodeid plausibly refers to this testcase.

    ``classname`` comes from the file path (``test_dir.test_x``) while a nodeid
    keeps the path separators (``test_dir/test_x.py``). The test name must always
    match; the file is then compared as a relative path and, failing that, by
    file name — a nodeid may name a class that JUnit left out of ``classname``
    (``test_x.py::TestClass::test_a``), so the basename is the last thing checked.
    A testcase without a ``classname`` accepts any file.
    """
    if "::" not in nodeid:
        return nodeid == name
    file_part, tail = nodeid.split("::", 1)
    if tail != name:
        return False
    if not classname:
        return True
    relative = classname.replace(".", "/")
    if file_part == relative or file_part == f"{relative}.py":
        return True
    return Path(file_part).name == Path(f"{relative}.py").name


def _align_nodeids(results: list[dict], manifest: list[str] | None) -> None:
    """
    Attach node IDs from ``manifest`` to ``results`` in place.

    :param results: Parsed results, in JUnit order.
    :param manifest: Ordered node IDs from the run's ``targets.json`` (``None``
        when the caller has no manifest, e.g. a legacy run).
    """
    if not manifest:
        return

    # Primary strategy: positional (the manifest *is* the execution order), but
    # only trusted when the testcase at that position really is that node — a
    # case pytest never reported would otherwise shift every later result onto
    # the wrong node ID.
    for result, nodeid in zip(results, manifest):
        if _location_matches(nodeid, result.get("classname", ""), result.get("name", "")):
            result["nodeid"] = nodeid

    if all(result.get("nodeid") for result in results):
        return

    # Fallback: resolve the rest by file/name location, consuming each manifest
    # entry at most once so identical test names in different files stay apart.
    unused = set(manifest)
    for result in results:
        if result.get("nodeid"):
            unused.discard(result["nodeid"])
    for result in results:
        if result.get("nodeid"):
            continue
        classname, name = result.get("classname", ""), result.get("name", "")
        for candidate in manifest:
            if candidate in unused and _location_matches(candidate, classname, name):
                result["nodeid"] = candidate
                unused.discard(candidate)
                break


def parse_junit(path, manifest: Iterable[str] | None = None):
    """
    Parse a JUnit XML report into per-case results.

    :param path: Path to the JUnit XML file (``str`` or path-like).
    :param manifest: Ordered node IDs of the run (see module docstring); when
        given, every result gets a ``nodeid`` traceable to the workspace tree.
        Defaults to ``None``, which leaves ``nodeid`` unset.
    :return: ``(results, counts)``.
    """
    path = Path(path)
    if path.stat().st_size > MAX_JUNIT_BYTES:
        raise ValueError("JUnit report exceeds 32 MiB; raw report and logs remain available")
    root = ElementTree.parse(path).getroot()
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("Unsupported JUnit root element")
    results = []
    counts = dict(passed=0, failed=0, error=0, skipped=0, total=0)
    for case in root.iter("testcase"):
        outcome, message = "passed", ""
        for name, mapped in [("error", "error"), ("failure", "failed"), ("skipped", "skipped")]:
            element = case.find(name)
            if element is not None:
                outcome = mapped
                message = element.get("message", "") + "\n" + (element.text or "")
                break
        counts[outcome] += 1
        counts["total"] += 1
        results.append(
            dict(
                nodeid=None,
                name=case.get("name", ""),
                classname=case.get("classname", ""),
                outcome=outcome,
                duration_ms=round(float(case.get("time", "0")) * 1000),
                failure_text=message.strip(),
                stdout=case.findtext("system-out", ""),
                stderr=case.findtext("system-err", ""),
            )
        )

    _align_nodeids(results, list(manifest) if manifest else None)
    return results, counts
