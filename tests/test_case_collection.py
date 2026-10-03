"""
Tests for case collection (``lounger.services.case_discovery``).

Regression context: ``_collect_via_subprocess`` inherited the parent environment
and let the project's own pytest configuration apply untouched. A ``pytest.ini``
requesting ``--html`` therefore aborted collection with ``unrecognized arguments``
whenever the reporting plugin was unavailable, and an inherited
``PYTEST_DISABLE_PLUGIN_AUTOLOAD`` could disable the plugins the project needed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lounger.services import case_discovery
from tests.conftest import scratch_dir, REPO_ROOT


# ── A3: child environment and project addopts ──────────────────────────────

def _fake_run(monkeypatch, payload):
    """Capture the subprocess invocation and return a canned JSON result."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        captured["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload, ensure_ascii=False), stderr=""
        )

    monkeypatch.setattr(case_discovery.subprocess, "run", fake_run)
    return captured


def test_collection_removes_inherited_pytest_env(monkeypatch):
    """A parent's PYTEST_* switches must not leak into the collection child."""
    monkeypatch.setenv("PYTEST_ADDOPTS", "-x --lf")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    captured = _fake_run(monkeypatch, [])

    case_discovery._collect_via_subprocess(".")

    assert captured["env"] is not None, "the child must get an explicit environment"
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in captured["env"]
    assert "PYTEST_ADDOPTS" not in captured["env"] or "addopts=" in captured["env"]["PYTEST_ADDOPTS"]


def test_collection_strips_html_addopts_from_project_config(monkeypatch):
    """
    A project requesting ``--html`` must still collect when the report plugin is
    missing: the flag is replaced through ``-o addopts=``.
    """
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", raising=False)
    captured = _fake_run(monkeypatch, [])

    with scratch_dir("addopts") as project:
        (project / "pytest.ini").write_text(
            "[pytest]\naddopts = --html=./reports/result.html -p no:randomly\n", encoding="utf-8"
        )
        case_discovery._collect_via_subprocess(str(project))

    addopts = captured["env"]["PYTEST_ADDOPTS"]
    assert "--html" not in addopts
    assert "addopts=" in addopts
    # unrelated options survive
    assert "-p no:randomly" in addopts


def test_collection_sets_no_addopts_override_without_project_config(monkeypatch):
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    captured = _fake_run(monkeypatch, [])

    with scratch_dir("no-addopts") as project:
        case_discovery._collect_via_subprocess(str(project))

    assert "PYTEST_ADDOPTS" not in captured["env"]


def test_collection_passes_the_scan_dir_and_runs_from_it(monkeypatch):
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    captured = _fake_run(monkeypatch, [])

    with scratch_dir("cwd") as project:
        case_discovery._collect_via_subprocess(str(project))

    assert captured["cwd"] == str(project)
    assert captured["cmd"][-1] == str(project)


def test_sanitized_addopts_is_best_effort(monkeypatch):
    """A malformed or unreadable config must not break collection."""
    def explode(_scan_dir):
        raise RuntimeError("boom")

    # _sanitized_addopts imports its helpers lazily, so patch them at the source.
    monkeypatch.setattr("lounger.services.test_execution.read_project_addopts", explode)

    assert case_discovery._sanitized_addopts(".") == ""


def test_collection_failure_reports_the_stderr(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 4, stdout="", stderr="usage: pytest\nunrecognized arguments")

    monkeypatch.setattr(case_discovery.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="unrecognized arguments"):
        case_discovery._collect_via_subprocess(".")


# ── real collection through the runner path ────────────────────────────────

def test_real_collection_finds_yaml_cases_without_a_report_plugin():
    """
    End to end: a project whose ``pytest.ini`` asks for ``--html`` collects
    successfully even though the child has no HTML plugin available.
    """
    with scratch_dir("real-collect") as project:
        (project / "config").mkdir()
        (project / "config" / "config.yaml").write_text(
            "test_project:\n  sample: true\n", encoding="utf-8"
        )
        (project / "datas" / "sample").mkdir(parents=True)
        (project / "datas" / "sample" / "test_alpha.yaml").write_text(
            "- teststeps:\n"
            "    - step: First alpha case\n"
            "      request:\n"
            "        method: GET\n"
            "        url: /alpha\n",
            encoding="utf-8",
        )
        (project / "test_suite.py").write_text(
            "from typing import Dict\n"
            "from lounger.analyze_cases import load_teststeps\n"
            "from lounger.case import execute_teststeps\n\n\n"
            "@load_teststeps()\n"
            "def test_suite(teststeps: Dict) -> None:\n"
            "    execute_teststeps(teststeps)\n",
            encoding="utf-8",
        )
        # Deliberately references the HTML plugin, which the child may not have.
        (project / "pytest.ini").write_text(
            "[pytest]\naddopts = --html=./reports/result.html\n", encoding="utf-8"
        )

        env_backup = os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        try:
            cases = case_discovery._collect_via_subprocess(str(project), timeout=120)
        finally:
            if env_backup is None:
                os.environ.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
            else:
                os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = env_backup

    nodeids = [case["nodeid"] for case in cases]
    assert any("datas/sample/test_alpha.yaml::case_1_First alpha case" in nodeid for nodeid in nodeids), nodeids
