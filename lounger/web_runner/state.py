"""Shared module-level state for the web runner.

All mutable state lives here with module-level globals.
Cross-module access must go through the helper functions below
— never use ``global`` in importing modules.
"""

import re
import threading
import time

# The project directory being served (set by main())
_scan_dir: str = "."

# Runtime state for active test runs
_active_runs: dict = {}
_runs_lock = threading.Lock()


def active_run_count() -> int:
    """Return the number of currently running test runs."""
    with _runs_lock:
        return sum(
            1 for info in _active_runs.values()
            if info.get("status") == "running"
        )


def is_any_run_active() -> bool:
    """Return True if any test run is currently executing."""
    return active_run_count() > 0

# Case cache
_cases_cache: list[dict] | None = None
_cases_cache_time: float = 0.0
_cache_ttl: float = 300.0

# YAML metadata cache
_yaml_metadata_cache: dict | None = None
_yaml_metadata_cache_scan_dir: str = ""

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


# ── cache helpers — the ONLY way other modules should touch caches ────

def get_cases_cache() -> list[dict] | None:
    """Return cached case list if fresh, else None."""
    global _cases_cache, _cases_cache_time, _cache_ttl
    if _cases_cache is not None and (time.time() - _cases_cache_time) < _cache_ttl:
        return _cases_cache
    return None


def set_cases_cache(cases: list[dict]) -> None:
    """Store case list in cache."""
    global _cases_cache, _cases_cache_time
    _cases_cache = cases
    _cases_cache_time = time.time()


def clear_caches() -> None:
    """Invalidate all caches (refresh)."""
    global _cases_cache, _cases_cache_time
    global _yaml_metadata_cache, _yaml_metadata_cache_scan_dir
    _cases_cache = None
    _cases_cache_time = 0.0
    _yaml_metadata_cache = None
    _yaml_metadata_cache_scan_dir = ""


def get_yaml_metadata_cache(scan_dir: str) -> dict | None:
    """Return cached YAML metadata if key matches."""
    global _yaml_metadata_cache, _yaml_metadata_cache_scan_dir
    if _yaml_metadata_cache is not None and _yaml_metadata_cache_scan_dir == scan_dir:
        return _yaml_metadata_cache
    return None


def set_yaml_metadata_cache(metadata: dict, scan_dir: str) -> None:
    """Store YAML metadata in cache."""
    global _yaml_metadata_cache, _yaml_metadata_cache_scan_dir
    _yaml_metadata_cache = metadata
    _yaml_metadata_cache_scan_dir = scan_dir
