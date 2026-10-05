"""
this is pytest_req log

The loguru logger and its config object live in ``pytest_req``. Importing that
package is not safe in every environment: ``pytest_req.log`` creates
``<directory of the caller module>/logs/requests_log.log`` at import time, using
``inspect.stack()[1]``. For lounger that directory is ``lounger/logs/`` inside the
*installed* package, which is read-only for a normal (non-editable) installation —
so the import raised ``PermissionError`` and, because ``lounger`` is loaded as a
``pytest11`` entry-point plugin, aborted the whole session before a single test.

The import is therefore deferred (PEP 562) *and* guarded: when ``pytest_req``
cannot set up its log file, lounger falls back to the plain loguru logger that
``pytest_req`` itself is built on. Logging keeps working, the session keeps
running, and the pytest-req report integration is used whenever it is available.
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

#: Set when ``pytest_req.log`` could not be imported; explains the fallback.
FALLBACK_REASON: str | None = None


class _FallbackLogConfig:
    """Minimal stand-in for ``pytest_req.log.LogConfig`` used when it is unavailable."""

    def __init__(self, **kwargs: Any) -> None:
        self.logger = _fallback_logger()

    def set_level(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002 - compatibility shim
        """No-op: loguru is already configured with a working default sink."""


def _fallback_logger():
    """Return the plain loguru logger (what ``pytest_req.log`` re-exports)."""
    from loguru import logger

    return logger


def _load(name: str) -> Any:
    """
    Resolve ``name`` from ``pytest_req.log``, falling back to loguru on failure.

    ``pytest_req.log`` fails when it cannot create its log directory (read-only
    install, sandboxed checkout). That must not take the test session down: the
    logger degrades to loguru, which is the same object pytest_req uses
    internally.
    """
    global FALLBACK_REASON
    try:
        import pytest_req.log as _req_log

        return getattr(_req_log, name)
    except Exception as exc:  # noqa: BLE001 - any import-time failure is degraded, not fatal
        FALLBACK_REASON = f"{type(exc).__name__}: {exc}"
        return _fallback_logger() if name == "log" else _FallbackLogConfig


def __getattr__(name: str) -> Any:
    """
    Resolve ``lounger.log.log`` / ``lounger.log.log_cfg`` on first access.

    Resolved values are cached as real module attributes, so the dependency is
    imported at most once and ``from lounger.log import log`` keeps working.
    """
    if name in _LAZY_EXPORTS:
        value = _load(name)
        globals()[name] = value  # cache: later lookups skip __getattr__
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
