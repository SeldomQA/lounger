"""
lounger CLI
"""
import os
from pathlib import Path

import click
from pytest_req.log import log

from lounger import __version__


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, help="Show version.")
@click.option("-pw", "--project-web", help="Create a Web automation test project.")
@click.option("-pa", "--project-api", help="Create an API automation test project.")
@click.pass_context
def main(ctx, project_web, project_api):
    """
    lounger — next generation automated testing framework.

    \b
    Examples:
      lounger --project-web myproject
      lounger --project-api myproject
      lounger runner --port 5002 --project ./myapi
    """
    if ctx.invoked_subcommand is not None:
        return

    if project_web:
        create_scaffold(project_web, "web")
    elif project_api:
        create_scaffold(project_api, "api")
    else:
        click.echo(ctx.get_help())


@main.command("runner")
@click.option("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
@click.option("--port", type=int, default=5000, help="Port (default: 5000)")
@click.option("--project", default=".", help="Project root directory (default: .)")
def runner(host, port, project):
    """Start the web test runner.

    Launches a browser-based UI for browsing and executing test cases.
    """
    from lounger.web_runner import main as start_runner
    start_runner(host=host, port=port, scan_dir=project)


# ── scaffold creation ──────────────────────────────────────────────────

def create_scaffold(project_name: str, type: str) -> None:
    """
    Create a project scaffold with the specified name and type.

    :param project_name: Name of the project (folder)
    :param type: Project type, one of "api", "web"
    """
    project_root = Path(project_name)

    if project_root.exists():
        log.info(f"Folder {project_name} already exists. Please specify a new folder name.")
        return

    log.info(f"Start to create new test project: {project_name}")
    log.info(f"CWD: {os.getcwd()}\n")

    current_file = Path(__file__).resolve()
    template_base = current_file.parent / "project_temp"

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "reports").mkdir(exist_ok=True)
    log.info("📁 created folder: reports")

    file_mappings = [(template_base / "conftest.py", "conftest.py")]

    if type == "web":
        file_mappings.extend([
            (template_base / "web" / ".env", ".env"),
            (template_base / "web" / "README.md", "README.md"),
            (template_base / "web" / "pytest.ini", "pytest.ini"),
            (template_base / "__init__.py", "test_dir/__init__.py"),
            (template_base / "web" / "test_dir" / "conftest.py", "test_dir/conftest.py"),
            (template_base / "web" / "test_dir" / "test_ai_sample.py", "test_dir/test_ai_sample.py"),
            (template_base / "web" / "test_dir" / "test_sample.py", "test_dir/test_sample.py"),
        ])
    elif type == "api":
        file_mappings.extend([
            (template_base / "api" / "SKILL.md", "SKILL.md"),
            (template_base / "api" / "pytest.ini", "pytest.ini"),
            (template_base / "api" / "test_api.py", "test_api.py"),
            (template_base / "__init__.py", "api/__init__.py"),
            (template_base / "__init__.py", "api/clients/__init__.py"),
            (template_base / "__init__.py", "support/__init__.py"),
            (template_base / "__init__.py", "test_dir/__init__.py"),
            (template_base / "__init__.py", "test_dir/posts_case/__init__.py"),
            (template_base / "api" / "config" / "config.yaml", "config/config.yaml"),
            (template_base / "api" / "support" / "db.py", "support/db.py"),
            (template_base / "api" / "support" / "notify.py", "support/notify.py"),
            (template_base / "api" / "datas" / "sample" / "test_sample.yaml", "datas/sample/test_sample.yaml"),
            (template_base / "api" / "api" / "clients" / "posts_api.py", "api/clients/posts_api.py"),
            (template_base / "api" / "test_dir" / "conftest.py", "test_dir/conftest.py"),
            (template_base / "api" / "test_dir" / "posts_case" / "test_get_post.py",
             "test_dir/posts_case/test_get_post.py"),
            (template_base / "api" / "test_dir" / "posts_case" / "test_create_post.py",
             "test_dir/posts_case/test_create_post.py"),
            (template_base / "api" / "test_dir" / "test_data" / "create_post_payload.json",
             "test_dir/test_data/create_post_payload.json"),
        ])
    else:
        log.error(f"Unsupported project type: {type}. Choose from 'api', 'web'.")
        return

    for src_path, dest_rel in file_mappings:
        try:
            content = src_path.read_text(encoding="utf-8")
            dest_path = project_root / dest_rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(content, encoding="utf-8")
            log.info(f"📄 created file: {dest_rel}")
        except Exception as e:
            log.error(f"Failed to create {dest_rel}: {e}")

    log.info(f"🎉 Project '{project_name}' created successfully.")
    log.info(f"👉 Go to the project folder and run 'pytest' to start testing.")


if __name__ == '__main__':
    main()
