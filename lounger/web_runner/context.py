"""Explicit project context and cross-process project ownership."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True)
class ProjectContext:
    root: Path
    data_dir: Path
    python: str = sys.executable

    @classmethod
    def create(cls, root: str, data_dir: str | None = None):
        project = Path(root).resolve()
        if not project.is_dir():
            raise ValueError(f"Project directory does not exist: {project}")
        data = Path(data_dir) if data_dir else Path(".lounger")
        return cls(project, (project / data).resolve())


class ProjectLock:
    """OS-held lock, keyed by canonical source path (not the data directory)."""

    def __init__(self, context: ProjectContext):
        key = hashlib.sha256(os.path.normcase(str(context.root)).encode()).hexdigest()
        directory = Path(tempfile.gettempdir()) / "lounger-locks"
        directory.mkdir(exist_ok=True, mode=0o700)
        self.path = directory / (key + ".lock")
        self.handle: BinaryIO | None = None

    def acquire(self):
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if not handle.read(1):
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                getattr(msvcrt, "locking")(handle.fileno(), getattr(msvcrt, "LK_NBLCK"), 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("This project already has a running Lounger runner") from exc
        self.handle = handle
        return self

    def close(self):
        if self.handle:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                getattr(msvcrt, "locking")(self.handle.fileno(), getattr(msvcrt, "LK_UNLCK"), 1)
            self.handle.close()
            self.handle = None
