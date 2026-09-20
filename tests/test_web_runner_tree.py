"""Tree paths must be project-relative regardless of the launcher directory."""

from lounger.web_runner.tree import _build_case_tree


def test_yaml_and_python_tree_paths_are_independent_of_cwd(tmp_path, monkeypatch):
    project = tmp_path / "myapi"
    project.mkdir()
    cases = [
        {"file": "datas/orders/test_create.yaml", "nodeid": "test_api.py::test_api[create]", "name": "create"},
        {
            "file": str(project / "test_dir" / "test_sample.py"),
            "nodeid": "test_dir/test_sample.py::test_ok",
            "name": "ok",
        },
    ]
    monkeypatch.chdir(tmp_path)
    outside = _build_case_tree(cases, str(project))
    monkeypatch.chdir(project)
    inside = _build_case_tree(cases, ".")
    assert inside == outside
    assert inside["total_cases"] == 2
    datas = inside["children"][0]
    assert datas["relpath"] == "datas"
    folder = datas["children"][0]
    assert folder["name"] == "orders"
    source = folder["children"][0]
    assert source["name"] == "test_create.yaml"
    assert source["cases"][0]["nodeid"] == cases[0]["nodeid"]
