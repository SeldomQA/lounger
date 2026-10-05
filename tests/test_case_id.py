"""
Tests for YAML case identity (``lounger.case_id``) and its consumers.

Regression context: the source file of a YAML case used to be recovered by a
regular expression hard-coded to ``test_api.py::test_api`` in
:mod:`lounger.services.case_discovery`. Renaming the entry module or function —
which pytest and the execution path both allow — silently dropped per-file
attribution, so every YAML case showed up under one entry-file node in the Web
Runner tree.

The case id now carries the YAML path relative to the project root, and both the
producer (``analyze_cases``) and the consumers decode it through
:mod:`lounger.case_id`, with a manifest written during collection for exact
lookups.
"""
import contextlib
import itertools
import json
import shutil
from pathlib import Path

import pytest

from lounger import case_id
from lounger.services import case_discovery

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRATCH_ROOT = REPO_ROOT / ".run-tmp" / "case-id-tests"
_counter = itertools.count()

ENTRY_NAMES = [
    "test_api.py::test_api",
    "test_suite.py::test_suite",
    "test_api.py::test_yaml_suite",
    "test_dir/test_api.py::test_api",
    "test_dir/test_api.py::TestSuite::test_api",
]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_scratch():
    """Remove this module's scratch tree after the module finishes."""
    yield
    shutil.rmtree(_SCRATCH_ROOT, ignore_errors=True)


@contextlib.contextmanager
def scratch_project(yaml_body: str = None):
    """Yield a project root containing config/, datas/sample/ and one YAML case."""
    project = _SCRATCH_ROOT / f"project-{next(_counter)}"
    (project / "config").mkdir(parents=True, exist_ok=True)
    (project / "datas" / "sample").mkdir(parents=True, exist_ok=True)
    (project / "config" / "config.yaml").write_text(
        "base_url: http://example.invalid\ntest_project:\n  sample: true\n", encoding="utf-8"
    )
    (project / "datas" / "sample" / "test_alpha.yaml").write_text(
        yaml_body
        if yaml_body is not None
        else (
            "- teststeps:\n"
            "    - step: First alpha case\n"
            "      request:\n"
            "        method: GET\n"
            "        url: /alpha\n"
            "- teststeps:\n"
            "    - name: Second alpha case\n"
            "      request:\n"
            "        method: GET\n"
            "        url: /beta\n"
        ),
        encoding="utf-8",
    )
    try:
        yield project
    finally:
        shutil.rmtree(project, ignore_errors=True)


# ── codec ─────────────────────────────────────────────────────────────────

def test_encode_decode_round_trip():
    encoded = case_id.encode("datas/sample/test_alpha.yaml", 2, "Creating a resource")

    assert encoded == "datas/sample/test_alpha.yaml::case_2_Creating a resource"
    assert case_id.decode(encoded) == {
        "file": "datas/sample/test_alpha.yaml",
        "case_no": 2,
        "step_name": "Creating a resource",
    }


def test_encode_normalizes_windows_separators():
    assert case_id.encode(r"datas\sample\test_a.yaml", 1, "x") == "datas/sample/test_a.yaml::case_1_x"


def test_decode_handles_parameterized_names_and_brackets():
    decoded = case_id.decode("test_alpha.yaml::case_3_name with :: and [brackets]")

    assert decoded is not None
    assert decoded["case_no"] == 3
    assert decoded["step_name"] == "name with :: and [brackets]"


@pytest.mark.parametrize(
    "value",
    [None, 42, "", "no-separator", "file.yaml::case_x_y", "file.yaml::case_1", "::case_1_x", "file.yaml::x"],
)
def test_decode_rejects_foreign_values(value):
    assert case_id.decode(value) is None


def test_param_id_and_nodeid_decoding():
    nodeid = "test_api.py::test_api[datas/sample/test_alpha.yaml::case_1_First alpha case]"

    assert case_id.param_id_of(nodeid) == "datas/sample/test_alpha.yaml::case_1_First alpha case"
    assert case_id.decode_nodeid(nodeid)["file"] == "datas/sample/test_alpha.yaml"
    # a plain function node ID has no parametrize id
    assert case_id.param_id_of("test_dir/test_sample.py::test_ok") is None
    assert case_id.decode_nodeid("test_dir/test_sample.py::test_ok") is None


def test_extract_step_name_prefers_name_then_step():
    assert case_id.extract_step_name({"name": "n", "step": "s"}) == "n"
    assert case_id.extract_step_name({"step": "s"}) == "s"
    assert case_id.extract_step_name({}) == case_id.DEFAULT_STEP_NAME
    assert case_id.extract_step_name(None) == case_id.DEFAULT_STEP_NAME
    assert case_id.extract_step_name({"step": 5}) == "5"


def test_case_metadata_shape():
    meta = case_id.case_metadata("datas/x.yaml", 1, {"step": "Getting a resource"})

    assert meta["params_id"] == "datas/x.yaml::case_1_Getting a resource"
    assert meta["file"] == "datas/x.yaml"
    assert meta["name"] == "Getting a resource"
    assert meta["description"] == "Getting a resource"


# ── decoupling: the entry module must not matter ───────────────────────────

@pytest.mark.parametrize("entry", ENTRY_NAMES)
def test_attribution_ignores_the_entry_module_name(entry):
    """
    Whatever the entry file/function is called, the case id must decode to the
    YAML file. (The old regex only matched ``test_api.py::test_api``.)
    """
    entry_file, _, entry_func = entry.partition("::")
    entry_func = entry_func.rsplit("::", 1)[-1]
    param_id = case_id.encode("datas/sample/test_alpha.yaml", 1, "First alpha case")
    nodeid = f"{entry_file}::{entry_func}[{param_id}]"

    decoded = case_id.decode_nodeid(nodeid)

    assert decoded is not None, f"nodeid from entry {entry!r} no longer decodes"
    assert decoded["file"] == "datas/sample/test_alpha.yaml"
    assert decoded["case_no"] == 1


# ── consumer: default naming rule ─────────────────────────────────────────

def test_naming_rule_attributes_a_yaml_case_without_metadata():
    nodeid = "renamed_entry.py::run_cases[datas/sample/test_alpha.yaml::case_2_Creating a resource]"

    override = case_discovery._yaml_metadata_rule(nodeid, {})

    assert override == {"file": "datas/sample/test_alpha.yaml", "name": "Creating a resource"}


def test_naming_rule_prefers_metadata_over_decoding():
    nodeid = "any_entry.py::any_func[datas/sample/test_alpha.yaml::case_1_x]"
    metadata = {"datas/sample/test_alpha.yaml::case_1_x": {"file": "datas/sample/test_alpha.yaml",
                                                          "name": "Nice name",
                                                          "description": "desc"}}

    override = case_discovery._yaml_metadata_rule(nodeid, metadata)

    assert override == {"file": "datas/sample/test_alpha.yaml", "name": "Nice name", "description": "desc"}


def test_naming_rule_ignores_python_cases():
    assert case_discovery._yaml_metadata_rule("test_dir/test_sample.py::test_ok", {}) is None


# ── consumer: metadata derivation and manifest ─────────────────────────────

def test_yaml_metadata_keys_match_the_parametrize_id():
    """Keys must be exactly what the entry module puts into the id."""
    with scratch_project() as project:
        metadata = case_discovery._get_yaml_case_metadata(str(project))

    assert set(metadata) == {
        "datas/sample/test_alpha.yaml::case_1_First alpha case",
        "datas/sample/test_alpha.yaml::case_2_Second alpha case",
    }
    assert metadata["datas/sample/test_alpha.yaml::case_1_First alpha case"]["name"] == "First alpha case"


def test_manifest_takes_precedence_over_scanning(monkeypatch):
    """The collected manifest wins over scanning the YAML files."""
    monkeypatch.setattr(
        case_discovery,
        "collect_case_manifest",
        lambda: [
            {
                "params_id": "datas/sample/test_alpha.yaml::case_1_First alpha case",
                "file": "datas/sample/test_alpha.yaml",
                "name": "From manifest",
                "description": "From manifest",
            }
        ],
    )

    with scratch_project() as project:
        metadata = case_discovery._load_yaml_case_metadata(str(project))

    assert len(metadata) == 1
    assert metadata["datas/sample/test_alpha.yaml::case_1_First alpha case"]["name"] == "From manifest"


def test_scanning_is_the_fallback_when_nothing_was_collected(monkeypatch):
    """Without a collection the YAML files still yield the same keys."""
    monkeypatch.setattr(case_discovery, "collect_case_manifest", lambda: [])

    with scratch_project() as project:
        metadata = case_discovery._load_yaml_case_metadata(str(project))

    assert set(metadata) == {
        "datas/sample/test_alpha.yaml::case_1_First alpha case",
        "datas/sample/test_alpha.yaml::case_2_Second alpha case",
    }


def test_discover_cases_attributes_without_any_entry_module_knowledge(monkeypatch):
    """
    End of end: collection returns a nodeid produced by a *renamed* entry module;
    enrichment must still attribute it to the YAML file.
    """
    with scratch_project() as project:
        collected = [
            {
                "nodeid": "test_suite.py::test_suite[datas/sample/test_alpha.yaml::case_1_First alpha case]",
                "name": "test_suite[datas/sample/test_alpha.yaml::case_1_First alpha case]",
                "file": str(project / "test_suite.py"),
            },
            {"nodeid": "test_dir/test_plain.py::test_ok", "name": "test_ok", "file": "test_dir/test_plain.py"},
        ]
        monkeypatch.setattr(case_discovery, "_collect_via_subprocess", lambda scan_dir, timeout=30: collected)

        cases = case_discovery.discover_cases(str(project))

    assert cases[0]["file"] == "datas/sample/test_alpha.yaml"
    assert cases[0]["name"] == "First alpha case"
    # a genuine python case is untouched
    assert cases[1]["file"] == "test_dir/test_plain.py"
    assert cases[1]["name"] == "test_ok"


# ── producer: the manifest recorded during case loading ───────────────────

def test_load_test_cases_records_the_manifest(monkeypatch):
    """
    ``load_test_cases`` records where each case came from, in memory.

    The test session must not write the manifest file: the runner owns it (it
    knows its own data directory, while a test run only knows its cwd). The
    child process reports this list over stdout instead.
    """
    from lounger import analyze_cases

    with scratch_project() as project:
        (project / "test_suite.py").write_text("def test_suite():\n    pass\n", encoding="utf-8")
        monkeypatch.chdir(project)
        analyze_cases.reset_case_manifest()

        loaded = analyze_cases.load_test_cases()
        manifest = analyze_cases.get_case_manifest()

    assert len(loaded) == len(manifest) == 2
    assert manifest[0] == {
        "params_id": loaded[0][0],
        "file": "datas/sample/test_alpha.yaml",
        "name": "First alpha case",
        "description": "First alpha case",
    }
    assert manifest[0]["params_id"] == "datas/sample/test_alpha.yaml::case_1_First alpha case"
    assert manifest[1]["params_id"] == "datas/sample/test_alpha.yaml::case_2_Second alpha case"


def test_manifest_keys_are_the_parametrize_ids(monkeypatch):
    """The recorded ids are exactly what the entry module puts into the params id."""
    from lounger import analyze_cases

    with scratch_project() as project:
        (project / "test_suite.py").write_text("def test_suite():\n    pass\n", encoding="utf-8")
        monkeypatch.chdir(project)
        analyze_cases.reset_case_manifest()
        analyze_cases.load_test_cases()

        indexed = case_discovery._manifest_index(analyze_cases.get_case_manifest())
        scanned = case_discovery._get_yaml_case_metadata(str(project))

    assert set(indexed) == set(scanned)
    assert {k: v["name"] for k, v in indexed.items()} == {k: v["name"] for k, v in scanned.items()}


def test_manifest_index_skips_malformed_entries():
    """A partially written manifest must not shadow the file scan."""
    assert case_discovery._manifest_index(
        [
            {"params_id": "a.yaml::case_1_x", "file": "a.yaml", "name": "From manifest"},
            {"params_id": 42, "file": "b.yaml"},  # wrong type
            {"file": "c.yaml"},  # no id
            "not-a-dict",
        ]
    ) == {
        "a.yaml::case_1_x": {
            "file": "a.yaml",
            "name": "From manifest",
            "description": "From manifest",
        }
    }


# ── transport: the child reports cases and manifest on one stdout ─────────

def test_collection_output_splits_cases_and_manifest():
    payload = '[{"nodeid": "a::b"}]'
    manifest = [{"params_id": "a.yaml::case_1_x", "file": "a.yaml", "name": "x"}]

    cases, reported = case_discovery._parse_collection_output(
        f"{payload}\n{case_discovery.MANIFEST_PREFIX}{json.dumps(manifest)}"
    )

    assert cases == [{"nodeid": "a::b"}]
    assert reported == manifest


def test_collection_output_without_a_manifest_is_fine():
    """Projects without YAML cases never print a MANIFEST line."""
    cases, reported = case_discovery._parse_collection_output('[{"nodeid": "a::b"}]')

    assert cases == [{"nodeid": "a::b"}]
    assert reported == []


def test_collection_output_tolerates_a_broken_manifest_line():
    cases, reported = case_discovery._parse_collection_output(
        '[{"nodeid": "a::b"}]\nMANIFEST {not json'
    )

    assert cases == [{"nodeid": "a::b"}]
    assert reported == []


def test_collection_output_still_reads_a_bare_json_document():
    """An older child prints the JSON cases as the whole output."""
    cases, reported = case_discovery._parse_collection_output('  [\n  {"nodeid": "a::b"}\n]  ')

    assert cases == [{"nodeid": "a::b"}]
    assert reported == []


def test_collect_case_manifest_is_captured_by_the_parser(monkeypatch):
    """The parsed manifest lands in the module state the runner reads."""
    monkeypatch.setattr(
        case_discovery.subprocess,
        "run",
        lambda *a, **k: type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '[{"nodeid": "a::b"}]\nMANIFEST [{"params_id": "a.yaml::case_1_x", '
                '"file": "a.yaml", "name": "x"}]',
                "stderr": "",
            },
        )(),
    )

    cases = case_discovery._collect_via_subprocess(".")

    assert cases == [{"nodeid": "a::b"}]
    assert case_discovery.collect_case_manifest() == [
        {"params_id": "a.yaml::case_1_x", "file": "a.yaml", "name": "x"}
    ]

