"""
Tests for web runner v2 features:

- Run history persistence (list/load/delete archived runs, timestamps)
- Concurrency control (MAX_CONCURRENT_RUNS, can_start_run, active_run_count)
- Multi-project support (init_projects, switch_project, get_current_scan_dir)
- HTML UI elements (tabs, history panel, project selector, tag chips, favorites)
"""
import json
import threading
import time

from lounger.services import test_execution
from lounger.web_runner import html, state

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

def test_is_any_run_active_false_when_empty():
    saved = dict(state._active_runs)
    state._active_runs.clear()
    try:
        assert state.is_any_run_active() is False
        assert state.active_run_count() == 0
    finally:
        state._active_runs.update(saved)


def test_is_any_run_active_true_when_running():
    saved = dict(state._active_runs)
    state._active_runs.clear()
    try:
        state._active_runs["r0"] = {"status": "running"}
        assert state.is_any_run_active() is True
    finally:
        state._active_runs.clear()
        state._active_runs.update(saved)


def test_active_run_count_ignores_completed():
    """Only 'running' status counts."""
    saved = dict(state._active_runs)
    state._active_runs.clear()
    try:
        state._active_runs["r0"] = {"status": "running"}
        state._active_runs["r1"] = {"status": "completed"}
        state._active_runs["r2"] = {"status": "error"}
        assert state.active_run_count() == 1
    finally:
        state._active_runs.clear()
        state._active_runs.update(saved)


# ── HTML UI checks ─────────────────────────────────────────────────────────

def test_html_has_tab_switching():
    """HTML contains tab bar with live and history tabs."""
    assert 'tab-btn active' in _FALLBACK_HTML
    assert 'onclick="switchTab(\'live\')"' in _FALLBACK_HTML
    assert 'onclick="switchTab(\'history\')"' in _FALLBACK_HTML
    assert 'id="panelLive"' in _FALLBACK_HTML
    assert 'id="panelHistory"' in _FALLBACK_HTML


def test_html_has_history_functions():
    """HTML contains history loading, viewing, and deleting functions."""
    assert 'async function loadHistory()' in _FALLBACK_HTML
    assert 'async function viewHistoryRun(' in _FALLBACK_HTML
    assert 'async function deleteHistoryRun(' in _FALLBACK_HTML
    assert '/api/history' in _FALLBACK_HTML


def test_html_no_project_selector():
    """Project selector has been removed (single-project mode)."""
    assert 'projectSelector' not in _FALLBACK_HTML
    assert 'loadProjects' not in _FALLBACK_HTML
    assert 'switchProject' not in _FALLBACK_HTML


def test_html_has_tag_filter():
    """HTML contains tag filter bar and related functions."""
    assert 'id="tagBar"' in _FALLBACK_HTML
    assert 'function renderTagBar()' in _FALLBACK_HTML
    assert 'function toggleTagFilter(' in _FALLBACK_HTML
    assert 'activeTagFilters' in _FALLBACK_HTML
    assert 'tag-chip' in _FALLBACK_HTML


def test_html_has_favorites():
    """HTML contains favorites with localStorage persistence."""
    assert 'FAVORITES_KEY' in _FALLBACK_HTML
    assert 'lounger.webRunner.favorites' in _FALLBACK_HTML
    assert 'function loadFavorites()' in _FALLBACK_HTML
    assert 'function saveFavorites()' in _FALLBACK_HTML
    assert 'function toggleFavorite(' in _FALLBACK_HTML
    assert 'fav-btn' in _FALLBACK_HTML


def test_html_has_run_status():
    """HTML shows run status and disables buttons while running."""
    assert 'id="runCounter"' in _FALLBACK_HTML
    assert 'function updateRunStatus()' in _FALLBACK_HTML
    assert 'function setRunButtonsDisabled(' in _FALLBACK_HTML
    assert 'id="runSelectedBtn"' in _FALLBACK_HTML
    assert 'id="runAllBtn"' in _FALLBACK_HTML
    assert '/api/runs' in _FALLBACK_HTML


def test_html_no_queue_ui():
    """Queue UI has been removed (simplified for single-user)."""
    assert 'queueBar' not in _FALLBACK_HTML
    assert 'showQueueBar' not in _FALLBACK_HTML
    assert 'pollQueueStatus' not in _FALLBACK_HTML


# keep reference for readability
_FALLBACK_HTML = html._FALLBACK_HTML
