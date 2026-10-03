"""
this is pytest_req log

The loguru logger and its config object live in ``pytest_req``. They are
re-exported lazily through :pep:`562` so that importing this module (which many
lounger modules do at import time, including the pytest entry-point plugin) has
**no side effects**:

``pytest_req.log`` writes ``<dir of the caller module>/logs/requests_log.log``
when it is imported, deriving that directory from ``inspect.stack()[1]``. When
lounger is loaded as a ``pytest11`` entry-point plugin, the caller frame is
``_pytest/assertion/rewrite.py``, so the dependency tried to create
``<site-packages>/_pytest/assertion/logs/`` and the pytest session aborted with
``PermissionError`` before running a single test.

Deferring the import keeps the plugin load safe while preserving the historical
public API, ``from lounger.log import log`` / ``log_cfg``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from loguru import Logger

    from pytest_req.log import LogConfig

    log: Logger
    log_cfg: LogConfig

#: Names served lazily from :mod:`pytest_req.log`.
_LAZY_EXPORTS = ("log", "log_cfg")


def __getattr__(name: str) -> Any:
    """
    Resolve ``lounger.log.log`` / ``lounger.log.log_cfg`` on first access.

    Resolved values are cached as real module attributes, so the dependency is
    imported at most once and ``from lounger.log import log`` keeps working.
    """
    if name in _LAZY_EXPORTS:
        import pytest_req.log as _req_log

        value = getattr(_req_log, name)
        globals()[name] = value  # cache: later lookups skip __getattr__
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
