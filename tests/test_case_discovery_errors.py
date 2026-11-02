"""Collection errors must expose pytest's cause rather than a JSON parser error."""
import subprocess

from lounger.services import case_discovery


def test_failed_subprocess_keeps_stdout_error_and_strips_ansi(tmp_path, monkeypatch):
    def failed(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 1,
            stdout="ERROR conftest.py: ModuleNotFoundError: No module named 'api.missing'\n",
            stderr="\x1b[32mLounger banner\x1b[0m\npytest collection failed with exit code 2\n",
        )

    monkeypatch.setattr(case_discovery, "_last_manifest", [{"params_id": "old.yaml::case_1_old"}])
    monkeypatch.setattr(case_discovery.subprocess, "run", failed)
    result = case_discovery.discover_cases(str(tmp_path))
    assert "Case collection failed:" in result["error"]
    assert "No module named 'api.missing'" in result["error"]
    assert "invalid JSON" not in result["error"]
    assert "\x1b" not in result["error"]
    assert case_discovery.collect_case_manifest() == []


def test_real_project_import_error_reaches_runner(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "conftest.py").write_text("import missing_api_collection_probe\n")
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    pass\n")
    result = case_discovery.discover_cases(str(tmp_path))
    assert "Case collection failed:" in result["error"]
    assert "missing_api_collection_probe" in result["error"]
    assert "ModuleNotFoundError" in result["error"]
    assert "invalid JSON" not in result["error"]


def test_import_noise_does_not_pollute_collected_json(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "conftest.py").write_text('print(\'["unrelated JSON in project output"]\')\n')
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    pass\n")
    cases = case_discovery.discover_cases(str(tmp_path))
    assert isinstance(cases, list)
    assert [case["nodeid"] for case in cases] == ["test_sample.py::test_ok"]

