"""
Case discovery — collect test cases and enrich YAML-driven cases.

Shared by the web runner and the platform script (docs/development_plan.md
§3.8).  Collecting is delegated to a pytest subprocess; the result is
validated and enriched with YAML case metadata.

YAML attribution no longer guesses at the entry module. A YAML case's parametrize
id embeds its source file (see :mod:`lounger.case_id`), so the source file is
recovered by *decoding* the node ID. Sources are read, in order of preference:

1. ``<data_dir>/cases.json`` — a manifest the lounger pytest plugin writes during
   collection (exact ids, no parsing);
2. the YAML files under ``datas/``, keyed by the same codec.

Errors are returned as structured dicts (``{"error": ...}``) instead of
printing to stderr, so any front-end can surface them.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from lounger.case_id import CASE_SUFFIX_RE, decode_nodeid, normalize_path

#: Manifest written by ``lounger.plugin`` during collection, relative to the
#: project root. Read-only for consumers; absent when collection did not run
#: through pytest (or the tree is read-only).
MANIFEST_RELPATH = (".lounger", "cases.json")

#: Identifies a YAML case inside an entry-module parametrize id. Kept for
#: reference/back-compat; matching itself goes through :func:`lounger.case_id.decode`.
YAML_CASE_RE = CASE_SUFFIX_RE

#: Pluggable naming rule: ``(nodeid, metadata) -> dict | None``.
#: Return a dict of case fields (file/name/description) to override, or None
#: to keep the collected case unchanged.
CaseNamingRule = Callable[[str, dict], dict | None]


def _sanitized_addopts(scan_dir: str) -> str:
    """
    Return the project's ``addopts`` with plugin-dependent options removed.

    Collection only needs to *find* tests, but pytest applies the project's
    ``addopts`` first. A checkout whose ``pytest.ini`` requests ``--html`` aborts
    collection with ``unrecognized arguments`` whenever the reporting plugin is
    not installed — making collection success depend on the environment. Report
    options are therefore stripped and applied via ``-o addopts=...``.
    """
    from lounger.services.test_execution import read_project_addopts, without_html_addopts

    try:
        return without_html_addopts(read_project_addopts(scan_dir))
    except Exception:  # noqa: BLE001 - a malformed config must not break collection
        return ""


def _collect_via_subprocess(scan_dir: str, timeout: int = 30) -> list[dict]:
    """
    Run pytest --collect-only in a subprocess and parse the JSON output.

    The child environment is sanitised: ``PYTEST_ADDOPTS`` and
    ``PYTEST_DISABLE_PLUGIN_AUTOLOAD`` are inherited otherwise, so a parent
    invocation could silently change or break the child (the latter disables the
    plugins the project's own ``addopts`` may need).

    :param scan_dir: Project root directory (where config/config.yaml lives).
    :param timeout: Subprocess timeout in seconds.
    :return: List of collected case dicts.
    :raises subprocess.TimeoutExpired: If collection exceeds the timeout.
    :raises json.JSONDecodeError: If the subprocess output is not valid JSON.
    """
    script = (
        "from lounger.utils.collect import get_test_cases\n"
        "import json, sys\n"
        "cases = get_test_cases(sys.argv[1] if len(sys.argv) > 1 else '.')\n"
        "print(json.dumps(cases, ensure_ascii=False))\n"
    )
    env = dict(os.environ)
    for inherited in ("PYTEST_ADDOPTS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"):
        env.pop(inherited, None)
    addopts = _sanitized_addopts(scan_dir)
    if addopts:
        # pytest applies the ini's ``addopts`` *before* PYTEST_ADDOPTS, so the
        # original value has to be replaced for the report flags to disappear:
        # ``-o addopts=`` overrides the ini entry outright.
        env["PYTEST_ADDOPTS"] = f"-o addopts={addopts}"

    result = subprocess.run(
        [sys.executable, "-c", script, scan_dir],
        cwd=scan_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout)[-4000:] or "pytest collection failed")
    stdout = result.stdout.strip()
    if not stdout:
        stdout = result.stderr.strip()
    lines = stdout.split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return json.loads(stdout)


def discover_cases(
    scan_dir: str,
    timeout: int = 30,
    yaml_naming_rule: CaseNamingRule | None = None,
) -> list[dict] | dict:
    """
    Collect all test cases in a project.

    :param scan_dir: Project root directory.
    :param timeout: Subprocess timeout in seconds.
    :param yaml_naming_rule: Optional custom naming rule for YAML cases.
        Defaults to :data:`YAML_NODEID_RE` based lookup against the YAML
        metadata (naming-rule pluginization, §3.8).
    :return: List of case dicts, or ``{"error": ...}`` on failure.
    """
    try:
        cases = _collect_via_subprocess(scan_dir, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return {"error": f"Case collection timed out after {timeout}s: {e}"}
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"Case collection produced invalid JSON: {e}"}
    except OSError as e:
        return {"error": f"Case collection failed: {e}"}

    metadata = _load_yaml_case_metadata(scan_dir)
    if metadata:
        rule = yaml_naming_rule or _yaml_metadata_rule
        cases = [_apply_naming_rule(case, metadata, rule) for case in cases]
    return cases


def _apply_naming_rule(case: dict, metadata: dict, rule: CaseNamingRule) -> dict:
    """Apply the naming rule to a single case (in place, returns it)."""
    override = rule(case.get("nodeid", ""), metadata)
    if override:
        case.update(override)
    return case


def _yaml_metadata_rule(nodeid: str, metadata: dict) -> dict | None:
    """
    Default naming rule: attribute a YAML case to its source file.

    The node ID is *decoded* (never pattern-guessed), so the entry module and
    function may be renamed freely.

    This is the fallback "generic rule" — projects may pass their own
    ``yaml_naming_rule`` to :func:`discover_cases` to change how YAML cases
    are re-parented to their source files.
    """
    decoded = decode_nodeid(nodeid)
    if decoded is None:
        return None

    param_id = nodeid[nodeid.rfind("[") + 1 : -1]
    meta = metadata.get(param_id) or metadata.get(decoded["file"])
    if meta and "file" in meta:
        return {
            "file": meta["file"],
            "name": meta.get("name") or decoded["step_name"],
            "description": meta.get("description"),
        }

    # The codec recognised the case but no metadata file/entry matches (the YAML
    # was edited between collection and enrichment): attribute it by the path
    # encoded in the id rather than silently dropping the attribution.
    return {"file": decoded["file"], "name": decoded["step_name"]}


# ── YAML metadata ─────────────────────────────────────────────────────────

def _load_yaml_case_metadata(scan_dir: str) -> dict:
    """
    Return the YAML case metadata of a project, keyed by parametrize id.

    Prefers the manifest written during collection (exact, already aligned with
    the entry module); falls back to scanning the YAML files with the same codec.
    """
    manifest = _read_manifest(scan_dir)
    return manifest if manifest else _get_yaml_case_metadata(scan_dir)


def _read_manifest(scan_dir: str) -> dict:
    """Read ``<scan_dir>/.lounger/cases.json`` if the plugin produced it."""
    path = Path(scan_dir).joinpath(*MANIFEST_RELPATH)
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}

    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list):
        return {}

    metadata: dict = {}
    for entry in cases:
        if not isinstance(entry, dict):
            continue
        params_id = entry.get("params_id")
        file_rel = entry.get("file")
        if not isinstance(params_id, str) or not isinstance(file_rel, str):
            continue
        metadata[params_id] = {
            "file": normalize_path(file_rel),
            "name": entry.get("name") or params_id,
            "description": entry.get("description") or entry.get("name") or params_id,
        }
    return metadata


def _get_yaml_case_metadata(scan_dir: str) -> dict:
    """
    Derive YAML case metadata from the files under ``datas/``.

    Keys are built with :mod:`lounger.case_id`, i.e. exactly what the entry
    module puts into the parametrize id, so lookup is an exact match.
    """
    try:
        import yaml
    except ImportError:
        return {}

    from lounger.case_id import case_metadata

    scan_path = Path(scan_dir)
    datas_dir = scan_path / "datas"
    if not datas_dir.is_dir():
        return {}

    metadata: dict = {}

    for yaml_file in sorted(datas_dir.rglob("*.yaml")):
        if not (yaml_file.stem.startswith("test_") or yaml_file.stem.endswith("_test")):
            continue
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue

        if not isinstance(data, list):
            continue

        rel_path = normalize_path(os.path.relpath(yaml_file, scan_path))

        for idx, block in enumerate(data):
            if not isinstance(block, dict) or "teststeps" not in block:
                continue
            steps = block["teststeps"]
            if not isinstance(steps, list) or len(steps) == 0:
                continue

            meta = case_metadata(rel_path, idx + 1, steps[0])
            metadata[meta["params_id"]] = {
                "file": meta["file"],
                "name": meta["name"],
                "description": meta["description"],
            }

    return metadata
