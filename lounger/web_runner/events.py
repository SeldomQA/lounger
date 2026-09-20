"""Condition-based notifications and native filesystem events (no polling observer)."""

import threading
from pathlib import Path


class Events:
    def __init__(self):
        self.condition = threading.Condition()
        self.revision = 0
        self.sources = 0
        self.closed = False

    def publish(self, source=False):
        with self.condition:
            self.revision += 1
            self.sources += int(source)
            self.condition.notify_all()

    def wait(self, revision, timeout=15):
        with self.condition:
            self.condition.wait_for(lambda: self.closed or self.revision != revision, timeout)
            return self.revision

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class ProjectWatcher:
    def __init__(self, context, changed, log_changed):
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        ignored = {
            ".git",
            ".lounger",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            "node_modules",
            "reports",
            "logs",
        }
        root, data = context.root, context.data_dir

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.event_type not in {"created", "modified", "deleted", "moved"}:
                    return
                paths = [Path(p) for p in (event.src_path, getattr(event, "dest_path", "")) if p]
                for path in paths:
                    if path.is_relative_to(data):
                        if path.name == "output.log":
                            log_changed()
                        continue
                    if not path.is_relative_to(root):
                        continue
                    parts = path.relative_to(root).parts
                    if any(part in ignored or part.startswith(".") for part in parts):
                        continue
                    # Directory moves/deletes can remove whole sets of collected cases.
                    if (event.is_directory and event.event_type in {"moved", "deleted"}) or (
                        not event.is_directory
                        and path.suffix.lower() in {".py", ".yaml", ".yml", ".ini", ".toml", ".cfg"}
                    ):
                        changed()
                        break

        self.observer = Observer()
        handler = Handler()
        self.observer.schedule(handler, str(root), recursive=True)
        if not data.is_relative_to(root):
            self.observer.schedule(handler, str(data), recursive=True)
        self.observer.start()

    def close(self):
        self.observer.stop()
        self.observer.join(timeout=5)
