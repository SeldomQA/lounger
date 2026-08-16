"""
Case discovery — collect test cases and enrich YAML-driven cases.

Shared by the web runner and the platform script (docs/development_plan.md
§3.8).  Collecting is delegated to a pytest subprocess; the result is
validated and optionally enriched with YAML case metadata.

Errors are returned as structured dicts (``{"error": ...}``) instead of
printing to stderr, so any front-end can surface them.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

#: Fallback naming rule for YAML-driven parametrized cases when no YAML
#: metadata matches: ``<file>::<case>(...::case_<n>_...)``
YAML_NODEID_RE = re.compile(r"^test_api\.py::test_api\[(.+?::case_\d+_.+?)\]$")

#: Pluggable naming rule: ``(nodeid, metadata) -> dict | None``.
#: Return a dict of case fields (file/name/description) to override, or None
#: to keep the collected case unchanged.
CaseNamingRule = Callable[[str, dict], dict | None]


def _collect_via_subprocess(scan_dir: str, timeout: int = 30) -> list[dict]:
    """
    Run pytest --collect-only in a subprocess and parse the JSON output.

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
    result = subprocess.run(
        [sys.executable, "-c", script, scan_dir],
        cwd=scan_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

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

    metadata = _get_yaml_case_metadata(scan_dir)
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
    Default naming rule: look the parametrized nodeid up in YAML metadata.

    This is the fallback "generic rule" — projects may pass their own
    ``yaml_naming_rule`` to :func:`discover_cases` to change how YAML cases
    are re-parented to their source files.
    """
    m = YAML_NODEID_RE.match(nodeid)
    if not m:
        return None
    param_key = m.group(1)
    meta = metadata.get(param_key)
    if not meta:
        return None
    return {
        "file": meta["file"],
        "name": meta["name"],
        "description": meta.get("description"),
    }


# ── YAML metadata ─────────────────────────────────────────────────────────

def _get_yaml_case_metadata(scan_dir: str) -> dict:
    """Parse YAML test case files from datas/ and return a metadata mapping."""
    try:
        import yaml
    except ImportError:
        return {}

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

        filename = yaml_file.stem
        rel_path = str(yaml_file.relative_to(scan_path))

        for idx, block in enumerate(data):
            if not isinstance(block, dict) or "teststeps" not in block:
                continue
            steps = block["teststeps"]
            if not isinstance(steps, list) or len(steps) == 0:
                continue

            first_step = steps[0]
            display_name = (
                first_step.get("step")
                or first_step.get("name")
                or f"测试用例 {idx + 1}"
            )
            step_name = first_step.get("name") or "step_1"
            case_id = f"{filename}::case_{idx + 1}_{step_name}"

            metadata[case_id] = {
                "file": rel_path,
                "name": display_name,
                "description": display_name,
            }

    return metadata
