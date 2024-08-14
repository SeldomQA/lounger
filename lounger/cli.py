"""
lounger CLI
"""
import os
from pathlib import Path

import click
from pytest_req.log import log

from lounger import __version__


@click.command()
@click.version_option(version=__version__, help="Show version.")
@click.option("-pw", "--project-web", help="Create an web automation test project.")
@click.option("-pa", "--project-api", help="Create an api automation test project.")
def main(project_web, project_api):
    """
    lounger CLI.
    """

    if project_web:
        create_scaffold(project_web, "web")
        return 0

    if project_api:
        create_scaffold(project_api, "api")
        return 0


def create_scaffold(project_name: str, type: str) -> None:
    """
    create scaffold with specified project name.
    :param project_name:
    :param type:
    :return:
    """
    if os.path.isdir(project_name):
        log.info(f"Folder {project_name} exists, please specify a new folder name.")
        return

    log.info(f"Start to create new test project: {project_name}")
    log.info(f"CWD: {os.getcwd()}\n")

    def create_folder(path):
        os.makedirs(path)
        log.info(f"created folder: {path}")

    def create_file(path, file_content=""):
        with open(path, 'w', encoding="utf-8") as py_file:
            py_file.write(file_content)
        msg = f"created file: {path}"
        log.info(msg)

    current_file = Path(__file__).resolve()

    # create base file
    conftest_path = current_file.parent / "project_temp" / "conftest.py"
    conftest_content = conftest_path.read_text(encoding='utf-8')
    create_folder(project_name)
    create_file(os.path.join(project_name, "conftest.py"), conftest_content)

    web_ini = '''[pytest]
base_url = https://cn.bing.com
addopts = -vs --browser=chromium --headed 
'''
    api_ini = '''[pytest]
base_url = https://httpbin.org
addopts = -vs 
'''

    if type == "api":
        # create api file
        api_case_path = current_file.parent / "project_temp" / "test_api.py"
        content = api_case_path.read_text(encoding='utf-8')
        create_file(os.path.join(project_name, "test_api.py"), content)
        create_file(os.path.join(project_name, "pytest.ini"), api_ini)
    elif type == "web":
        # create web file
        web_case_path = current_file.parent / "project_temp" / "test_web.py"
        content = web_case_path.read_text(encoding='utf-8')
        create_file(os.path.join(project_name, "test_web.py"), content)
        create_file(os.path.join(project_name, "pytest.ini"), web_ini)


if __name__ == '__main__':
    main()
