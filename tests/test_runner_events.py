"""Notifications block while idle and native filesystem events invalidate sources."""

import threading

from lounger.web_runner.context import ProjectContext
from lounger.web_runner.events import Events, ProjectWatcher


def test_event_wakes_all_subscribers_and_cannot_lose_prior_change():
    events = Events()
    received = []
    threads = [threading.Thread(target=lambda: received.append(events.wait(0, 2))) for _ in range(2)]
    for thread in threads:
        thread.start()
    events.publish(source=True)
    for thread in threads:
        thread.join(3)
    assert received == [1, 1]
    assert events.sources == 1
    assert events.wait(0, 0) == 1
    assert events.wait(1, 0) == 1
    events.close()
    assert events.closed


def test_native_watcher_source_rename_and_ignored_artifacts(tmp_path):
    context = ProjectContext.create(str(tmp_path))
    context.data_dir.mkdir()
    source = tmp_path / "test_demo.py"
    source.write_text("def test_old(): pass")
    changed, log_changed = threading.Event(), threading.Event()
    watcher = ProjectWatcher(context, changed.set, log_changed.set)
    try:
        source.rename(tmp_path / "test_renamed.py")
        assert changed.wait(5), "native rename event missing"
    finally:
        watcher.close()
    assert not watcher.observer.is_alive()


def test_native_log_events_do_not_invalidate_sources(tmp_path):
    context = ProjectContext.create(str(tmp_path))
    context.data_dir.mkdir()
    changed, log_changed = threading.Event(), threading.Event()
    watcher = ProjectWatcher(context, changed.set, log_changed.set)
    try:
        (context.data_dir / "output.log").write_text("hello")
        assert log_changed.wait(5)
        assert not changed.wait(0.3)
    finally:
        watcher.close()
