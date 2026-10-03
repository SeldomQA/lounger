"""
Shared test helpers.

Some environments (restricted sandboxes, locked-down CI images) provide a temp
directory whose newly created children cannot be enumerated or written to again,
which makes pytest's ``tmp_path``/``tmp_path_factory`` unusable. Tests that need a
scratch directory with files in it should use :func:`scratch_dir` instead: it
prefers the process temp area, verifies it is actually usable, and otherwise
falls back to a git-ignored directory under the repository.
"""
from __future__ import annotations

import contextlib
import itertools
import os
import shutil
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FALLBACK_ROOT = REPO_ROOT / ".run-tmp"

_counter = itertools.count()


def _usable_parent() -> Path:
    """Return a directory that supports create + list + write + delete."""
    try:
        candidate = Path(tempfile.mkdtemp(prefix="lounger-usable-check-"))
        (candidate / "probe").mkdir()
        (candidate / "probe" / "file").write_text("x", encoding="utf-8")
        os.listdir(candidate / "probe")
        shutil.rmtree(candidate, ignore_errors=True)
        return Path(tempfile.gettempdir())
    except OSError:
        FALLBACK_ROOT.mkdir(parents=True, exist_ok=True)
        return FALLBACK_ROOT


@contextlib.contextmanager
def scratch_dir(prefix: str = "scratch"):
    """
    Yield a fresh, writable, enumerable directory; it is removed afterwards.

    ``tempfile.mkdtemp`` is deliberately not used for the directory itself: it
    creates 0o700 directories that a restricted token may not be able to write
    into.
    """
    directory = _usable_parent() / f"{prefix}-{os.getpid()}-{next(_counter)}"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def scratch():
    """Fixture form of :func:`scratch_dir`."""
    with scratch_dir("fixture") as directory:
        yield directory
