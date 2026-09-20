"""Durable runner contracts, failure handling and real pytest execution."""

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from lounger.web_runner.context import ProjectContext, ProjectLock
from lounger.web_runner.manager import RunManager, validate_definition
from lounger.web_runner.results import parse_junit
from lounger.web_runner.storage import Problem, Store, now


@pytest.fixture
def manager(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n")
    obj = RunManager(
        ProjectContext.create(str(tmp_path)), collector=lambda root: [{"nodeid": "test_sample.py::test_ok"}]
    )
    yield obj
    obj.close()


def request(ids=None):
    return {
        "selection": {"type": "nodeids", "nodeids": ids or ["test_sample.py::test_ok"]},
        "options": {"verbosity": "verbose", "html_report": False},
    }


def wait(manager):
    manager.thread.join(timeout=20)
    assert not manager.thread.is_alive()


def test_definition_validation():
    for bad in [None, [], {}, {"selection": {"nodeids": [""]}}, {"selection": {"nodeids": [1]}}]:
        with pytest.raises(Problem):
            validate_definition(bad)
    assert validate_definition(request(["x", "x"]))["selection"]["nodeids"] == ["x"]


def test_project_lock_across_data_directories(tmp_path):
    one = ProjectLock(ProjectContext.create(str(tmp_path))).acquire()
    try:
        with pytest.raises(RuntimeError):
            ProjectLock(ProjectContext.create(str(tmp_path), "other")).acquire()
    finally:
        one.close()
    two = ProjectLock(ProjectContext.create(str(tmp_path))).acquire()
    two.close()


def test_schema_rejects_future_version(tmp_path):
    Store(tmp_path)
    with sqlite3.connect(tmp_path / "runner.db") as db:
        db.execute("PRAGMA user_version=42")
    with pytest.raises(RuntimeError, match="newer"):
        Store(tmp_path)


def test_task_revisions_deletion_and_snapshot(manager):
    task = manager.store.save_task(validate_definition({**request(), "name": "Smoke"}, task=True))
    run = manager.start(task, task["id"])
    wait(manager)
    changed = manager.store.save_task({**task, "name": "New"}, task["id"])
    assert changed["revision"] == 2
    with pytest.raises(Problem, match="changed"):
        manager.store.save_task(task, task["id"])
    manager.store.delete_task(task["id"])
    assert manager.store.tasks()["total"] == 0
    saved = manager.store.run(run["id"])
    assert saved["task_name_snapshot"] == "Smoke"
    assert saved["task_revision"] == 1


def test_real_execution_persists_without_browser_and_survives_restart(manager):
    run = manager.start(request(), key="retry")
    wait(manager)
    saved = manager.store.run(run["id"])
    assert saved["state"] == "completed", saved
    assert saved["outcome"] == "passed"
    assert saved["result_status"] == "ready"
    assert saved["counts"]["passed"] == 1
    assert manager.logs(run["id"])["text"]
    assert manager.start(request(), key="retry")["id"] == run["id"]
    with pytest.raises(Problem, match="another request"):
        manager.start(request(["different"]), key="retry")
    manager.close()
    restarted = RunManager(manager.context)
    try:
        assert restarted.store.run(run["id"])["state"] == "completed"
        assert restarted.store.results(run["id"])["total"] == 1
    finally:
        restarted.close()


def test_failed_tests_are_completed_not_execution_errors(manager):
    (manager.context.root / "test_sample.py").write_text("def test_ok():\n    assert False\n")
    run = manager.start(request())
    wait(manager)
    saved = manager.store.run(run["id"])
    assert (saved["state"], saved["outcome"], saved["exit_code"]) == ("completed", "failed", 1)
    assert saved["counts"]["failed"] == 1


def test_stale_selection_no_run_created(manager):
    with pytest.raises(Problem) as error:
        manager.start(request(["gone"]))
    assert error.value.code == "selection_stale"
    assert manager.store.runs()["total"] == 0
    assert not manager.operation.locked()


def test_concurrent_start_only_one_process(manager):
    (manager.context.root / "test_sample.py").write_text("import time\ndef test_ok():\n    time.sleep(1)\n")
    gate = threading.Barrier(2)

    def launch():
        gate.wait()
        try:
            return manager.start(request())["id"]
        except Problem as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        answers = list(pool.map(lambda _: launch(), range(2)))
    assert answers.count("project_busy") == 1
    wait(manager)
    assert manager.store.runs()["total"] == 1


def test_stop_and_release_project(manager):
    (manager.context.root / "test_sample.py").write_text("import time\ndef test_ok():\n    time.sleep(60)\n")
    run = manager.start(request())
    deadline = time.monotonic() + 5
    while manager.process is None and time.monotonic() < deadline:
        time.sleep(0.01)
    manager.stop(run["id"])
    wait(manager)
    assert manager.store.run(run["id"])["state"] == "cancelled"
    assert not manager.operation.locked()
    assert manager.stop(run["id"])["state"] == "cancelled"


def test_storage_failure_does_not_launch(manager, monkeypatch):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(manager.store, "create_run", fail)
    with pytest.raises(sqlite3.OperationalError):
        manager.start(request())
    assert manager.process is None and not manager.operation.locked()


def test_completion_manifest_recovers_database_failure(manager, monkeypatch):
    original = manager.store.update_run

    def fail_complete(run_id, changes, results=None):
        if results is not None:
            raise sqlite3.OperationalError("disk full")
        return original(run_id, changes, results)

    monkeypatch.setattr(manager.store, "update_run", fail_complete)
    run = manager.start(request())
    wait(manager)
    assert manager.blocked
    manager.close()
    recovered = RunManager(manager.context)
    try:
        assert recovered.store.run(run["id"])["state"] == "completed"
        assert recovered.store.results(run["id"])["total"] == 1
    finally:
        recovered.close()


def test_log_cursor_utf8_and_path_boundaries(manager):
    run_id = "a" * 32
    manager.store.create_run(dict(id=run_id, state="running", started_at=now(), request=request()))
    directory = manager.directory(run_id)
    directory.mkdir(parents=True)
    path = directory / "output.log"
    path.write_bytes("你好\n".encode())
    first = manager.logs(run_id, limit=4)
    assert first == {"text": "你", "cursor": 3}
    assert manager.logs(run_id, cursor=3)["text"] == "好\n"
    with pytest.raises(Problem):
        manager.logs(run_id, -1)
    with pytest.raises(Problem):
        manager.artifact(run_id, "../../runner.db")
    with pytest.raises(Problem):
        manager.delete(run_id)


def test_multiple_nested_suites_and_unknown_nodeid(tmp_path):
    xml = tmp_path / "report.xml"
    xml.write_text("""<testsuites><testsuite><testcase name="a" time=".1"/></testsuite>
    <testsuite><testsuite><testcase name="b"><failure message="bad"/></testcase>
    <testcase name="c"><error>setup</error></testcase><testcase name="d"><skipped/></testcase>
    </testsuite></testsuite></testsuites>""")
    rows, counts = parse_junit(xml)
    assert counts == dict(passed=1, failed=1, error=1, skipped=1, total=4)
    assert all(row["nodeid"] is None for row in rows)
    assert rows[0]["duration_ms"] == 100


def test_legacy_import_is_idempotent_and_bad_file_is_visible(tmp_path):
    directory = tmp_path / "reports" / "runs"
    directory.mkdir(parents=True)
    (directory / "old.json").write_text(
        json.dumps(dict(status="completed", exit_code=0, logs=["hello\n"], nodeids=["a"]))
    )
    (directory / "bad.json").write_text("{bad")
    context = ProjectContext.create(str(tmp_path))
    one = RunManager(context)
    assert one.store.runs()["total"] == 1
    assert one.warnings
    run_id = one.store.runs()["items"][0]["id"]
    assert one.logs(run_id)["text"] == "hello\n"
    one.close()
    two = RunManager(context)
    try:
        assert two.store.runs()["total"] == 1
    finally:
        two.close()


def test_recovery_marks_unfinished_and_keeps_uncertain_ownership(tmp_path):
    context = ProjectContext.create(str(tmp_path))
    store = Store(context.data_dir)
    store.create_run(dict(id="b" * 32, state="starting", started_at=now(), request=request()))
    for _ in range(2):
        manager = RunManager(context)
        try:
            assert manager.store.run("b" * 32)["state"] == "interrupted"
            assert manager.blocked
        finally:
            manager.close()


def test_run_result_replacement_is_idempotent(manager):
    run = manager.start(request())
    wait(manager)
    results = manager.store.results(run["id"])["items"]
    manager.store.update_run(run["id"], {"state": "completed"}, results)
    assert manager.store.results(run["id"])["total"] == 1
    manager.delete(run["id"])
    assert not manager.directory(run["id"]).exists()
    assert manager.store.runs()["total"] == 0


def test_different_projects_cannot_share_active_data_directory(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    shared = str(tmp_path / "shared")
    manager = RunManager(ProjectContext.create(str(first), shared))
    try:
        with pytest.raises(RuntimeError):
            RunManager(ProjectContext.create(str(second), shared))
    finally:
        manager.close()


def test_interrupted_run_requires_explicit_acknowledgement(tmp_path):
    context = ProjectContext.create(str(tmp_path))
    Store(context.data_dir).create_run(dict(id="c" * 32, state="starting", started_at=now(), request=request()))
    manager = RunManager(context)
    try:
        assert manager.blocked
        manager.acknowledge("c" * 32)
        assert not manager.blocked
    finally:
        manager.close()
    restarted = RunManager(context)
    try:
        assert not restarted.blocked
    finally:
        restarted.close()


def test_legacy_import_preserves_history_on_task_delete(manager):
    task = manager.store.save_task(validate_definition({**request(), "name": "kept"}, task=True))
    run = manager.start(task, task["id"])
    wait(manager)
    manager.store.delete_task(task["id"])
    assert manager.store.runs(task_id=task["id"])["total"] == 1
    assert manager.store.run(run["id"])["task_name_snapshot"] == "kept"


def test_skip_and_setup_error_are_structured(manager):
    (manager.context.root / "test_sample.py").write_text("""import pytest
@pytest.fixture
def broken():
    raise RuntimeError("fixture error")
def test_ok(broken):
    pass
@pytest.mark.skip(reason="later")
def test_skip():
    pass
""")
    manager.collector = lambda _: [{"nodeid": "test_sample.py::test_ok"}, {"nodeid": "test_sample.py::test_skip"}]
    run = manager.start(request(["test_sample.py::test_ok", "test_sample.py::test_skip"]))
    wait(manager)
    assert manager.store.run(run["id"])["counts"] == dict(passed=0, failed=0, error=1, skipped=1, total=2)


def test_bad_report_does_not_invent_passes(manager, monkeypatch):
    def malformed(_):
        raise ValueError("bad xml")

    monkeypatch.setattr("lounger.web_runner.manager.parse_junit", malformed)
    run = manager.start(request())
    wait(manager)
    saved = manager.store.run(run["id"])
    assert saved["result_status"] == "unavailable"
    assert saved["counts"] == {}
    assert "bad xml" in saved["error_message"]
    assert saved["exit_code"] == 0


def test_collection_failure_is_reported(tmp_path):
    from lounger.services.case_discovery import discover_cases

    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_bad.py").write_text("this is invalid python !")
    result = discover_cases(str(tmp_path))
    assert isinstance(result, dict) and "error" in result


def test_launch_failure_is_durable(manager, monkeypatch):
    real = __import__("subprocess").Popen

    def launch(cmd, *args, **kwargs):
        if "-m" in cmd and "pytest" in cmd:
            raise FileNotFoundError("interpreter gone")
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr("lounger.web_runner.manager.subprocess.Popen", launch)
    run = manager.start(request())
    wait(manager)
    saved = manager.store.run(run["id"])
    assert saved["state"] == "error" and "interpreter gone" in saved["error_message"]
    assert not manager.operation.locked()


def test_large_log_is_read_in_bounded_chunks(manager):
    rid = "d" * 32
    manager.store.create_run(dict(id=rid, state="completed", started_at=now(), request=request()))
    directory = manager.directory(rid)
    directory.mkdir(parents=True)
    with (directory / "output.log").open("wb") as output:
        for _ in range(128):
            output.write(b"x" * 65536)
    batch = manager.logs(rid)
    assert len(batch["text"]) == 65536 and batch["cursor"] == 65536


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX process groups")
def test_stop_kills_descendant_that_ignores_sigterm(manager):
    import os
    import signal

    (manager.context.root / "test_sample.py").write_text("""import subprocess, sys, time
from pathlib import Path
def test_ok():
    child = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])
    Path("child.pid").write_text(str(child.pid))
    time.sleep(60)
""")
    run = manager.start(request())
    pid_file = manager.context.root / "child.pid"
    deadline = time.monotonic() + 8
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pid_file.exists()
    pid = int(pid_file.read_text())
    try:
        manager.stop(run["id"])
        wait(manager)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            # Some systems retain a reparented zombie briefly; it is no longer executing.
            status = __import__("subprocess").run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
            if "Z" in status.stdout or not status.stdout.strip():
                break
            time.sleep(0.05)
        else:
            pytest.fail("descendant is still executing")
        assert manager.store.run(run["id"])["state"] == "cancelled"
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_html_toggle_overrides_project_report_paths(manager):
    root = manager.context.root
    (root / "pytest.ini").write_text("[pytest]\naddopts = --html=old.html --junit-xml=old.xml\n")
    run = manager.start(request())
    wait(manager)
    assert not (root / "old.html").exists()
    assert not (root / "old.xml").exists()
    assert (manager.directory(run["id"]) / "junit.xml").exists()
    data = request()
    data["options"]["html_report"] = True
    enabled = manager.start(data)
    wait(manager)
    saved = manager.store.run(enabled["id"])
    assert saved["state"] == "completed", saved
    assert saved["report_path"] == "html/report.html"
    assert manager.artifact(enabled["id"], saved["report_path"]).is_file()


def test_shutdown_during_collection_cannot_start_tests(manager):
    entered, release = threading.Event(), threading.Event()
    failures = []

    def collect(_):
        entered.set()
        release.wait(5)
        return [{"nodeid": "test_sample.py::test_ok"}]

    manager.collector = collect

    def launch():
        try:
            manager.start(request())
        except Problem as exc:
            failures.append(exc.code)

    worker = threading.Thread(target=launch)
    worker.start()
    assert entered.wait(2)
    closer = threading.Thread(target=manager.close)
    closer.start()
    deadline = time.monotonic() + 2
    while not manager.closed and time.monotonic() < deadline:
        time.sleep(0.01)
    release.set()
    worker.join(5)
    closer.join(5)
    assert failures == ["shutting_down"]
    assert manager.store.runs()["total"] == 0
    assert not closer.is_alive()


def test_blocked_run_cannot_be_deleted_to_bypass_recovery(tmp_path):
    context = ProjectContext.create(str(tmp_path))
    Store(context.data_dir).create_run(dict(id="e" * 32, state="starting", started_at=now(), request=request()))
    manager = RunManager(context)
    try:
        with pytest.raises(Problem, match="Resolve recovery"):
            manager.delete("e" * 32)
        manager.acknowledge("e" * 32)
        manager.delete("e" * 32)
    finally:
        manager.close()


def test_task_validation_distinguishes_missing_cases_files_and_collection_errors(manager):
    task = manager.store.save_task(validate_definition({**request(), "name": "check"}, task=True))
    batch = manager.validate_tasks([task["id"]])
    assert batch["items"][0]["status"] == "valid"
    manager.collector = lambda _: [{"nodeid": "test_sample.py::test_renamed"}]
    batch = manager.validate_tasks([task["id"]])
    assert batch["items"][0]["status"] == "invalid"
    assert batch["items"][0]["missing"] == [{"nodeid": "test_sample.py::test_ok", "reason": "case_not_collected"}]
    (manager.context.root / "test_sample.py").unlink()
    assert manager.validate_tasks([task["id"]])["items"][0]["missing"][0]["reason"] == "file_missing"
    manager.collector = lambda _: {"error": "import failed"}
    result = manager.validate_tasks([task["id"]])["items"][0]
    assert result["status"] == "unknown" and not result["missing"]
    assert manager.store.task(task["id"])["selection"]["nodeids"] == ["test_sample.py::test_ok"]


def test_task_validation_collects_once_and_never_rewrites_task(manager):
    task1 = manager.store.save_task(validate_definition({**request(), "name": "one"}, task=True))
    task2 = manager.store.save_task(validate_definition({**request(), "name": "two"}, task=True))
    calls = []
    manager.collector = lambda root: calls.append(root) or []
    batch = manager.validate_tasks([task1["id"], task2["id"]])
    assert len(calls) == 1 and all(t["status"] == "invalid" for t in batch["items"])
    assert manager.store.task(task1["id"])["revision"] == 1
    manager.operation.acquire()
    try:
        assert manager.validate_tasks([task1["id"]])["items"][0]["status"] == "unknown"
    finally:
        manager.operation.release()


def test_log_tail_and_backward_windows_reconstruct_utf8(manager):
    rid = "f" * 32
    manager.store.create_run(dict(id=rid, state="completed", started_at=now(), request=request()))
    directory = manager.directory(rid)
    directory.mkdir(parents=True)
    text = "第一行\n第二行\n" * 9000
    (directory / "output.log").write_text(text, encoding="utf-8")
    batch = manager.log_window(rid, tail=True, limit=65536)
    reconstructed = batch["text"]
    assert batch["start"] > 0 and batch["cursor"] == len(text.encode())
    while batch["start"]:
        batch = manager.log_window(rid, before=batch["start"], limit=65536)
        reconstructed = batch["text"] + reconstructed
    assert reconstructed == text
    with pytest.raises(Problem):
        manager.log_window(rid, before=-1)


def test_task_search_and_latest_run_summary(manager):
    task = manager.store.save_task(
        validate_definition({**request(), "name": "Smoke task", "description": "orders"}, task=True)
    )
    run = manager.start(task, task["id"])
    wait(manager)
    page = manager.store.tasks(search="ORDERS")
    assert page["total"] == 1
    assert page["items"][0]["last_run"]["id"] == run["id"]
    assert manager.store.tasks(search="absent")["total"] == 0


def test_source_change_during_collection_keeps_cache_invalid(manager):
    def collect(root):
        manager.sources_changed()
        return [{"nodeid": "test_sample.py::test_ok"}]

    manager.collector = collect
    manager.cases(refresh=True)
    assert manager.cache_time == 0
    assert manager.project()["sources_revision"] == 1
    assert not manager.project()["busy"]


def test_quiet_overrides_project_and_environment_logging_but_keeps_failure(manager, monkeypatch):
    root = manager.context.root
    (root / "pytest.ini").write_text("[pytest]\naddopts = -s -vv\nlog_cli = true\nlog_cli_level = INFO\n")
    (root / "test_sample.py").write_text(
        "import logging\n"
        "def test_ok():\n"
        "    print('SUCCESS_OUTPUT_MUST_BE_CAPTURED')\n"
        "    logging.info('SUCCESS_LOG_MUST_BE_CAPTURED')\n"
        "def test_bad():\n"
        "    assert False, 'FAILURE_REASON_MUST_REMAIN'\n"
    )
    monkeypatch.setenv("PYTEST_ADDOPTS", "-s -vv -o log_cli=true")
    manager.collector = lambda root: [{"nodeid": "test_sample.py::test_ok"}, {"nodeid": "test_sample.py::test_bad"}]
    task = manager.store.save_task(validate_definition({**request(), "name": "legacy verbose task"}, task=True))
    run = manager.start(task, task["id"], verbosity_override="quiet")
    wait(manager)
    output = (manager.directory(run["id"]) / "output.log").read_text()
    assert "SUCCESS_OUTPUT_MUST_BE_CAPTURED" not in output
    assert "SUCCESS_LOG_MUST_BE_CAPTURED" not in output
    assert "PASSED" not in output
    assert manager.store.task(task["id"])["options"]["verbosity"] == "verbose"
    assert run["request"]["options"]["verbosity"] == "quiet"
    failed = manager.start({**request(["test_sample.py::test_bad"]), "options": {"verbosity": "quiet"}})
    wait(manager)
    assert "FAILURE_REASON_MUST_REMAIN" in (manager.directory(failed["id"]) / "output.log").read_text()
    assert manager.store.run(failed["id"])["outcome"] == "failed"
