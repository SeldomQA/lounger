"""
Case identity codec — the single source of truth for YAML case names.

A YAML case is turned into a pytest parametrize id by the entry file
(``@load_teststeps``), and that id ends up embedded in the pytest node ID::

    datas/sample/test_sample.yaml::case_2_Creating a resource      <- param id
    test_api.py::test_api[datas/sample/test_sample.yaml::case_2_Creating a resource]

Both the *producer* (:mod:`lounger.analyze_cases`) and the *consumer*
(:mod:`lounger.services.case_discovery`, the Web Runner tree) must agree on that
format. They used to implement it independently — the consumer with a regular
expression that hard-coded ``test_api.py::test_api`` — so renaming the entry file
silently broke per-file attribution of YAML cases.

The format lives here once. Encoding is reversible, so no consumer needs to guess
at a file name or remember which entry module produced the id.

Format::

    <yaml path relative to the project root>::case_<n>_<step name>

``case_<n>_`` is the anchor: everything before it is the source file, everything
after it is the case label (which may itself contain ``_`` or spaces).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

#: Parametrize id layout: ``<file>::case_<n>_<label>``. The anchor matters —
#: the label may itself contain ``::``, so splitting on the last separator is not
#: reliable and the anchor is searched instead. ``CASE_SUFFIX_RE`` is matched
#: against the remainder *after* the anchor.
CASE_ANCHOR = "::case_"
CASE_SUFFIX_RE = re.compile(r"^case_(?P<case_no>\d+)_(?P<label>.*)$", re.DOTALL)

#: Fallback case label when a case has neither ``name`` nor ``step``.
DEFAULT_STEP_NAME = "step_1"


def normalize_path(value: str) -> str:
    """Return ``value`` with forward slashes (stable across platforms)."""
    return str(value).replace("\\", "/")


def extract_step_name(case_step: Mapping[str, Any] | None) -> str:
    """
    Return the case label of a single step.

    Mirrors the historical rule: ``name`` wins, then ``step``, then
    :data:`DEFAULT_STEP_NAME`. Both producer and consumer use this so the two
    sides cannot drift apart (the previous implementations each applied their own
    fallback and only matched by coincidence).
    """
    if not isinstance(case_step, Mapping):
        return DEFAULT_STEP_NAME
    value = case_step.get("name") or case_step.get("step")
    if value is None:
        return DEFAULT_STEP_NAME
    return str(value)


def encode(file_relpath: str, case_no: int, step_name: str) -> str:
    """
    Build the parametrize id for one YAML case.

    :param file_relpath: YAML file path relative to the project root.
    :param case_no: 1-based case index inside the file.
    :param step_name: case label (see :func:`extract_step_name`).
    :return: ``"<file>::case_<n>_<step>"``.
    """
    return f"{normalize_path(file_relpath)}::case_{case_no}_{step_name}"


def decode(case_id: str) -> dict[str, Any] | None:
    """
    Parse a case id produced by :func:`encode`.

    The ``::case_`` anchor separates file from case number (a case label may
    itself contain ``::``, so the split is not done at the last separator).

    :param case_id: A parametrize id (or any string with the same shape).
    :return: ``{"file", "case_no", "step_name"}`` or ``None`` when ``case_id``
        does not have the expected shape. Callers must handle ``None`` instead of
        assuming a file name.
    """
    if not isinstance(case_id, str) or CASE_ANCHOR not in case_id:
        return None
    file_part, _, suffix = case_id.partition(CASE_ANCHOR)
    match = CASE_SUFFIX_RE.match("case_" + suffix)
    if not match or not file_part:
        return None
    return {
        "file": normalize_path(file_part),
        "case_no": int(match.group("case_no")),
        "step_name": match.group("label"),
    }


def param_id_of(nodeid: str) -> str | None:
    """
    Return the parametrize id embedded in a pytest node ID.

    ``"test_api.py::test_api[a.yaml::case_1_x]"`` -> ``"a.yaml::case_1_x"``.
    Returns ``None`` for a non-parametrized node ID.
    """
    if not isinstance(nodeid, str):
        return None
    start = nodeid.rfind("[")
    if start == -1 or not nodeid.endswith("]"):
        return None
    return nodeid[start + 1 : -1]


def decode_nodeid(nodeid: str) -> dict[str, Any] | None:
    """Decode the YAML case a pytest node ID refers to, or ``None``."""
    param_id = param_id_of(nodeid)
    return decode(param_id) if param_id else None


def case_metadata(file_relpath: str, case_no: int, first_step: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    Build the collection metadata of one YAML case.

    :param file_relpath: YAML file path relative to the project root.
    :param case_no: 1-based case index inside the file.
    :param first_step: First step of the case (source of the label).
    :return: ``{"params_id", "file", "name", "description"}``.
    """
    step_name = extract_step_name(first_step)
    return {
        "params_id": encode(file_relpath, case_no, step_name),
        "file": normalize_path(file_relpath),
        "name": step_name,
        "description": step_name,
    }


def iter_case_paths(project_root: str | Path, project_names: Iterable[str]) -> list[Path]:
    """
    Return the YAML case files of the given ``test_project`` entries, sorted.

    Mirrors the discovery rules used by :class:`lounger.commons.load_config.LoadConfig`:
    files live under ``<project_root>/datas/<project>/`` and are named
    ``test_*.yaml`` or ``*_test.yaml``.
    """
    root = Path(project_root)
    paths: list[Path] = []
    for name in project_names:
        folder = root / "datas" / str(name)
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.yaml"):
            if path.stem.startswith("test_") or path.stem.endswith("_test"):
                paths.append(path)
    return sorted(paths)
