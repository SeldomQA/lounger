"""
Tests for web runner v2 features:

- Run history persistence (list/load/delete archived runs, timestamps)
- Concurrency control (single run per project, enforced by ``RunManager``)
- Shell UI elements (tabs, history panel, tag chips, favorites)

The archived-run helpers in ``lounger.services.test_execution`` are still used to
import legacy ``reports/runs/*.json`` snapshots, so their contracts stay covered.
"""
import json
import threading
import time

import pytest

from lounger.services import test_execution
from tests.conftest import shell_assets

# ── history API ────────────────────────────────────────────────────────────

def test_list_archived_runs_empty(tmp_path):
    """No reports/runs/ dir returns empty list."""
    assert test_execution.list_archived_runs(str(tmp_path)) == []


def test_list_archived_runs_returns_sorted_summaries(tmp_path):
    """Archived runs are listed newest-first with summary fields."""
    runs_dir = tmp_path / "reports" / "runs"
    runs_dir.mkdir(parents=True)

    for i, rid in enumerate(["run_a", "run_b", "run_c"]):
        data = {
            "status": "completed",
            "nodeids": [f"n{i}"],
            "logs": [f"log-{i}"],
            "exit_code": 0,
            "started_at": 1000.0 + i,
            "finished_at": 1100.0 + i,
        }
        (runs_dir / f"{rid}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        # ensure different mtimes for stable sort
        time.sleep(0.05)

    result = test_execution.list_archived_runs(str(tmp_path))

    assert len(result) == 3
    # newest first
    assert result[0]["run_id"] == "run_c"
    assert result[-1]["run_id"] == "run_a"
    # summary fields
    for item in result:
        assert "run_id" in item
        assert "status" in item
        assert "exit_code" in item
        assert "case_count" in item
        assert item["case_count"] == 1
        assert "started_at" in item
        assert "finished_at" in item


def test_load_archived_run_returns_full_data(tmp_path):
    """load_archived_run reads the complete snapshot including logs."""
    runs_dir = tmp_path / "reports" / "runs"
    runs_dir.mkdir(parents=True)
    data = {
        "status": "completed",
        "nodeids": ["a::t1", "a::t2"],
        "logs": ["line1", "line2"],
        "exit_code": 0,
        "started_at": 1000.0,
        "finished_at": 1100.0,
    }
    (runs_dir / "run_x.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )

    loaded = test_execution.load_archived_run(str(tmp_path), "run_x")

    assert loaded is not None
    assert loaded["logs"] == ["line1", "line2"]
    assert loaded["nodeids"] == ["a::t1", "a::t2"]
    assert loaded["started_at"] == 1000.0
    assert loaded["finished_at"] == 1100.0


def test_load_archived_run_returns_none_for_missing(tmp_path):
    assert test_execution.load_archived_run(str(tmp_path), "nonexistent") is None


def test_delete_archived_run_removes_file(tmp_path):
    runs_dir = tmp_path / "reports" / "runs"
    runs_dir.mkdir(parents=True)
    fp = runs_dir / "to_delete.json"
    fp.write_text('{"status":"completed"}', encoding="utf-8")

    assert test_execution.delete_archived_run(str(tmp_path), "to_delete") is True
    assert not fp.exists()


def test_delete_archived_run_returns_false_for_missing(tmp_path):
    assert test_execution.delete_archived_run(str(tmp_path), "nope") is False


def test_serialize_run_includes_timestamps():
    """_serialize_run preserves started_at and finished_at."""
    info = {
        "status": "completed",
        "logs": [],
        "nodeids": ["n1"],
        "exit_code": 0,
        "started_at": 1000.0,
        "finished_at": 1100.0,
        "queue": "non-serializable",
    }
    snapshot = test_execution._serialize_run(info)
    assert snapshot["started_at"] == 1000.0
    assert snapshot["finished_at"] == 1100.0
    assert "queue" not in snapshot


def test_archive_run_persists_timestamps(tmp_path):
    """Archived runs include timestamps in the persisted file."""
    runs = {}
    lock = threading.Lock()
    runs["r0"] = {
        "status": "completed",
        "logs": ["log"],
        "nodeids": ["n0"],
        "exit_code": 0,
        "started_at": 2000.0,
        "finished_at": 2100.0,
        "queue": object(),
    }

    test_execution.archive_run(runs, str(tmp_path), "r0", keep_recent=0, lock=lock)

    persisted = tmp_path / "reports" / "runs" / "r0.json"
    assert persisted.exists()
    data = json.loads(persisted.read_text(encoding="utf-8"))
    assert data["started_at"] == 2000.0
    assert data["finished_at"] == 2100.0


# ── concurrency control ────────────────────────────────────────────────────

def test_project_lock_rejects_a_second_manager(runner_project):
    """Only one manager may own a project (the production concurrency guard)."""
    from lounger.web_runner.context import ProjectContext
    from lounger.web_runner.manager import RunManager

    first = RunManager(ProjectContext.create(str(runner_project)))
    try:
        with pytest.raises(RuntimeError, match="already has a running Lounger runner"):
            RunManager(ProjectContext.create(str(runner_project)))
    finally:
        first.close()


def test_busy_project_is_reported_to_the_ui(runner):
    """``/api/v1/project`` exposes a busy flag the shell uses to disable runs."""
    client, manager = runner
    status, project = client.call("/api/v1/project")

    assert status == 200
    assert project["busy"] is False
    assert manager.operation.locked() is False


# ── shell UI checks (against the shipped assets) ───────────────────────────

ASSETS = shell_assets()


def test_html_has_tab_switching():
    """The shell contains a tab bar with the live and history panes."""
    assert 'tab-btn active' in ASSETS
    assert 'onclick="switchTab(\'live\')"' in ASSETS
    assert 'onclick="switchTab(\'history\')"' in ASSETS
    assert 'id="panelLive"' in ASSETS
    assert 'id="panelHistory"' in ASSETS


def test_html_has_history_functions():
    """The shell contains history loading, viewing, and deleting functions."""
    assert 'async function loadHistory()' in ASSETS
    assert 'async function viewHistoryRun(' in ASSETS
    assert 'async function deleteHistoryRun(' in ASSETS
    assert '/api/history' in ASSETS


def test_html_no_project_selector():
    """Project selector has been removed (single-project mode)."""
    assert 'projectSelector' not in ASSETS
    assert 'loadProjects' not in ASSETS
    assert 'switchProject' not in ASSETS


def test_html_has_tag_filter():
    """The shell contains the tag filter bar and its functions."""
    assert 'id="tagBar"' in ASSETS
    assert 'function renderTagBar()' in ASSETS
    assert 'function toggleTagFilter(' in ASSETS
    assert 'activeTagFilters' in ASSETS
    assert 'tag-chip' in ASSETS


def test_html_has_favorites():
    """The shell contains favorites with localStorage persistence."""
    assert 'FAVORITES_KEY' in ASSETS
    assert 'lounger.webRunner.favorites' in ASSETS
    assert 'function loadFavorites()' in ASSETS
    assert 'function saveFavorites()' in ASSETS
    assert 'function toggleFavorite(' in ASSETS
    assert 'fav-btn' in ASSETS


def test_html_has_run_status():
    """The shell shows run status and disables buttons while running."""
    assert 'id="runCounter"' in ASSETS
    assert 'function updateRunStatus()' in ASSETS
    assert 'function setRunButtonsDisabled(' in ASSETS
    assert 'id="runSelectedBtn"' in ASSETS
    assert 'id="runAllBtn"' in ASSETS
    assert '/api/runs' in ASSETS


def test_html_no_queue_ui():
    """Queue UI has been removed (simplified for single-user)."""
    assert 'queueBar' not in ASSETS
    assert 'showQueueBar' not in ASSETS
    assert 'pollQueueStatus' not in ASSETS
