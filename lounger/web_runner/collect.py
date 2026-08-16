"""
Case collection — thin web_runner wrapper over lounger.services.case_discovery.
"""

from pathlib import Path

from lounger.services.case_discovery import discover_cases

from . import state


def get_test_cases(scan_dir: str | None = None) -> list[dict]:
    """Collect all test cases in the project (cached, structured errors)."""
    sd = scan_dir if scan_dir is not None else state._scan_dir
    scan_dir_abs = str(Path(sd).resolve())

    cached = state.get_cases_cache()
    if cached is not None:
        return cached

    result = discover_cases(scan_dir_abs)
    if isinstance(result, dict) and "error" in result:
        # structured error surfaced to the front-end (3.8 §5)
        return [{"error": result["error"]}]

    assert isinstance(result, list)
    state.set_cases_cache(result)
    return result
