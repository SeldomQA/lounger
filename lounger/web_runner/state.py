"""
Shared module-level state for the web runner.

Only the project directory and the case-collection cache live here. Live run
state belongs to ``RunManager`` (one owner per project), and the YAML case index
is built on demand by :mod:`lounger.services.case_discovery`, so neither is
duplicated in module globals.
"""

import time

#: The project directory being served (set by :func:`lounger.web_runner.main`).
_scan_dir: str = "."

#: Case-collection cache (a project listing changes rarely; the runner refreshes
#: it explicitly after a source change).
_cases_cache: list[dict] | None = None
_cases_cache_time: float = 0.0
_cache_ttl: float = 300.0


def get_cases_cache() -> list[dict] | None:
    """Return the cached case list if it is still fresh, else ``None``."""
    if _cases_cache is not None and (time.time() - _cases_cache_time) < _cache_ttl:
        return _cases_cache
    return None


def set_cases_cache(cases: list[dict]) -> None:
    """Store the collected case list."""
    global _cases_cache, _cases_cache_time
    _cases_cache = cases
    _cases_cache_time = time.time()


def clear_caches() -> None:
    """Invalidate the case cache (used by an explicit refresh)."""
    global _cases_cache, _cases_cache_time
    _cases_cache = None
    _cases_cache_time = 0.0
