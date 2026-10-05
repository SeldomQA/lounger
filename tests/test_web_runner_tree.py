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


def test_node_keys_always_use_forward_slashes(tmp_path):
    """
    The UI builds its element keys as ``<type>:<relpath>`` and drives expand /
    collapse / favourites / single-case runs from them.

    ``str(Path(...))`` yields backslashes on Windows, which made every directory
    and file node unaddressable there (selectors such as
    ``[data-node-key="dir:datas/orders"]`` never matched).
    """
    project = tmp_path / "project"
    project.mkdir()
    cases = [
        {"file": "datas/orders/test_create.yaml", "nodeid": "a::b", "name": "create"},
        {"file": str(project / "nested" / "deeper" / "test_x.py"), "nodeid": "c::d", "name": "x"},
    ]

    tree = _build_case_tree(cases, str(project))

    keys = []

    def collect(node):
        keys.append(node["relpath"])
        for child in node.get("children", []) or []:
            collect(child)

    collect(tree)

    assert any("datas/orders" == key for key in keys), keys
    assert any("nested/deeper" == key for key in keys), keys
    assert not [key for key in keys if "\\" in key], f"backslash in a node key: {keys}"


def test_directory_and_file_keys_are_distinct_strings(tmp_path):
    """A directory and the file inside it must not collide after key building."""
    project = tmp_path / "project2"
    project.mkdir()
    cases = [
        {"file": "a/b.yaml", "nodeid": "x::1", "name": "one"},
        {"file": "a/b/c.yaml", "nodeid": "x::2", "name": "two"},
    ]

    tree = _build_case_tree(cases, str(project))

    keys = {tree["relpath"]}

    def collect(node):
        keys.add(f"{node['type']}:{node['relpath']}")
        for child in node.get("children", []) or []:
            collect(child)

    collect(tree)

    assert "dir:a" in keys
    assert "file:a/b.yaml" in keys
    assert "dir:a/b" in keys or "file:a/b" in keys
    assert "file:a/b/c.yaml" in keys
