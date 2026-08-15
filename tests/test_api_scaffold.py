from lounger.cli import create_scaffold


def test_create_api_scaffold_includes_support_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    create_scaffold("demo_api", "api")

    project_root = tmp_path / "demo_api"

    assert (project_root / "support" / "__init__.py").exists()
    assert (project_root / "support" / "db.py").exists()
    assert (project_root / "support" / "notify.py").exists()
    assert (project_root / "test_dir" / "conftest.py").exists()
    assert (project_root / "conftest.py").exists()

    db_text = (project_root / "support" / "db.py").read_text(encoding="utf-8")
    notify_text = (project_root / "support" / "notify.py").read_text(encoding="utf-8")
    root_conftest_text = (project_root / "conftest.py").read_text(encoding="utf-8")
    assert "build_mysql_resource" in db_text
    assert "create_mysql_resource" in db_text
    assert "register_dingtalk_integration" in notify_text
    assert "register_notifications" in notify_text
    assert "Optional post-run notification example" in root_conftest_text

    conftest_text = (project_root / "test_dir" / "conftest.py").read_text(encoding="utf-8")
    assert "Optional database fixture example" in conftest_text
    assert "create_mysql_resource" in conftest_text

    get_post_text = (project_root / "test_dir" / "posts_case" / "test_get_post.py").read_text(encoding="utf-8")
    create_post_text = (project_root / "test_dir" / "posts_case" / "test_create_post.py").read_text(encoding="utf-8")
    assert "from lounger.request import expect" in get_post_text
    assert "from lounger.request import expect" in create_post_text
