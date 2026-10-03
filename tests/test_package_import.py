"""
Regression tests for the ``lounger`` package import surface (P0 fix).

Context: ``lounger/__init__.py`` used to run
``from .pytest_extend.params import data, file_data`` at import time, and
``lounger/plugin.py`` imported ``pytest_req.log`` at module level. Both pulled in
``pytest_req.log``, which infers its log directory from the *caller's* frame
(``inspect.stack()[1]``) at import time. Because ``lounger`` is loaded as a
``pytest11`` entry-point plugin, that caller frame was
``_pytest/assertion/rewrite.py`` — so the dependency tried to create
``<site-packages>/_pytest/assertion/logs/`` and the pytest session aborted with
``PermissionError`` before running a single test.

The module-level ``__getattr__`` fix makes importing the package (and the plugin
module) side-effect free. That property can only be observed in a *fresh*
interpreter — inside a running pytest session ``pytest_req`` is already imported
by other plugins — so it is asserted with subprocesses; the lazy-export contract
is asserted in-process.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _clean_env() -> dict:
    """Environment for a fresh interpreter: repo importable, plugin autoload off."""
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _run_probe(workdir: Path, code: str) -> subprocess.CompletedProcess:
    """Run ``code`` in a fresh interpreter whose working directory is ``workdir``."""
    workdir.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(workdir),
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )


#: Bare import only — nothing may be pulled in, nothing may be written.
_BARE_PROBE = """
    import sys
    import lounger
    print("VERSION", lounger.__version__)
    print("HAS_PYTEST_REQ", "pytest_req" in sys.modules)
    print("HAS_PYTEST_REQ_LOG", "pytest_req.log" in sys.modules)
    print("HAS_PARAMS", "lounger.pytest_extend.params" in sys.modules)
    print("HAS_LOGGER", "lounger.log" in sys.modules)
    """

#: The documented import idioms must keep working (this one may import
#: pytest_req, which is what historically created ./logs next to the package).
_IDIOM_PROBE = """
    import sys
    from lounger import __version__
    from lounger.log import log as log_a
    from lounger import data, file_data
    import lounger

    print("VERSION", __version__)
    print("LOG", type(log_a).__name__)
    print("DATA", data.__name__)
    print("FILE_DATA", file_data.__name__)
    print("LOGGER_ATTR", type(lounger.log.log).__name__)
    print("LOG_CFG", type(lounger.log.log_cfg).__name__)
    print("SAME_LOG", lounger.log.log is log_a)
    """


# ── side-effect freedom (fresh interpreter) ────────────────────────────────

def test_importing_lounger_does_not_import_pytest_req(tmp_path):
    """``import lounger`` in a fresh interpreter must not import pytest_req."""
    result = _run_probe(tmp_path / "clean", _BARE_PROBE)

    assert result.returncode == 0, f"probe failed:\n{result.stdout}\n{result.stderr}"
    assert "HAS_PYTEST_REQ False" in result.stdout, result.stdout
    assert "HAS_PYTEST_REQ_LOG False" in result.stdout, result.stdout
    assert "HAS_PARAMS False" in result.stdout, result.stdout


def test_importing_lounger_creates_no_log_directory(tmp_path):
    """The old failure mode: a logs directory inferred from the caller frame."""
    workdir = tmp_path / "no-logs-here"
    result = _run_probe(workdir, _BARE_PROBE)

    assert result.returncode == 0, f"probe failed:\n{result.stdout}\n{result.stderr}"
    assert not (workdir / "logs").exists(), "importing lounger created a logs directory"


def test_lazy_exports_still_resolve(tmp_path):
    """Every documented import idiom must keep working."""
    result = _run_probe(tmp_path / "idioms", _IDIOM_PROBE)

    assert result.returncode == 0, f"probe failed:\n{result.stdout}\n{result.stderr}"
    assert "LOG Logger" in result.stdout, result.stdout
    assert "DATA data" in result.stdout, result.stdout
    assert "FILE_DATA file_data" in result.stdout, result.stdout
    assert "LOGGER_ATTR Logger" in result.stdout, result.stdout
    assert "LOG_CFG LogConfig" in result.stdout, result.stdout
    assert "SAME_LOG True" in result.stdout, result.stdout


def test_entry_point_plugin_loads_without_error(tmp_path):
    """
    The plugin module must import cleanly.

    ``lounger.plugin`` used to import ``pytest_req.log`` at module level, which is
    what made the entry-point load fatal. The bare-import test above covers "no
    write happens"; this one covers "loading the plugin works".
    """
    code = """
    import lounger.plugin
    print("PLUGIN_LOADED", bool(lounger.plugin.__version__))
    print("HAS_LOG_CFG", callable(getattr(lounger.plugin, "_configure_logging", None)))
    """
    workdir = tmp_path / "plugin-import"
    result = _run_probe(workdir, code)

    assert result.returncode == 0, f"probe failed:\n{result.stdout}\n{result.stderr}"
    assert "PLUGIN_LOADED True" in result.stdout, result.stdout


def test_entry_point_plugin_runs_a_session(tmp_path):
    """
    End-to-end guard for the original symptom: a pytest session that loads
    ``lounger`` through its ``pytest11`` entry point must run a test.

    Autoload is disabled and the plugin plus its hookspec providers are loaded
    explicitly, so the session does not depend on unrelated plugins.
    """
    workdir = tmp_path / "session"
    workdir.mkdir()
    (workdir / "test_probe.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "test_probe.py",
            "-q", "-p", "no:cacheprovider", "--import-mode=importlib",
            "-p", "lounger.plugin", "-p", "pytest_xhtml.plugin",
        ],
        cwd=str(workdir),
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, (
        "pytest session loading the lounger plugin failed "
        f"(rc={result.returncode}):\n{result.stdout}\n{result.stderr}"
    )
    assert "1 passed" in result.stdout, result.stdout


# ── lazy-export contract (in-process) ─────────────────────────────────────

def test_lazy_export_is_cached_and_identity_stable():
    """
    The lazy export must resolve to the very same object as the direct import,
    and be cached as a real module attribute (so ``__getattr__`` runs once).
    """
    import lounger
    from lounger.pytest_extend import params

    assert lounger.data is params.data
    assert lounger.file_data is params.file_data
    assert lounger.__dict__["data"] is params.data
    assert lounger.__dict__["file_data"] is params.file_data


def test_log_module_attribute_is_lazy_and_stable():
    """``from lounger.log import log`` resolves through the package attribute."""
    import lounger
    import lounger.log as log_module

    assert lounger.log is log_module
    assert log_module.log.__class__.__name__ == "Logger"
    assert log_module.log_cfg.__class__.__name__ == "LogConfig"


def test_module_getattr_is_declared_and_version_is_plain():
    """Guard the mechanism itself, and keep ``__version__`` a plain attribute."""
    import lounger

    assert callable(getattr(lounger, "__getattr__", None))
    assert isinstance(lounger.__version__, str)
    assert lounger.__version__.count(".") >= 1


def test_unknown_attribute_raises_attribute_error():
    """A missing name must raise AttributeError instead of resolving oddly."""
    import lounger

    with pytest.raises(AttributeError, match="has no attribute 'definitely_not_here'"):
        lounger.definitely_not_here
