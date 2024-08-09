import pytest
import inspect as sys_inspect
import os
from pathlib import Path
from pytest_req.log import log

from lounger.pytest_extend import conversion
from lounger.config import Lounger

__all__ = [
    "file_data", "data",
]


def _search_file_path(file_name: str, file_dir: Path) -> str:
    """
    find file path
    :param file_name:
    :param file_dir:
    """
    file_path = ""
    find_root_dir = file_dir.parent.parent

    for root, _, files in os.walk(find_root_dir, topdown=False):
        for file in files:
            if Lounger.env is not None:
                if root.endswith(Lounger.env) and file == file_name:
                    file_path = os.path.join(root, file_name)
                    break
            else:
                if file == file_name:
                    file_path = os.path.join(root, file_name)
                    break
        else:
            continue
        break

    return file_path


def _search_env_file_path(file_dir: Path, file_part_path: str) -> str:
    """
    find environment file path, Lounger.env != None
    :param file_dir:
    :param file_part_path:
    """
    file_path = ""
    find_root_dir = file_dir.parent
    file_name = file_part_path.split("/")[-1]
    file_part = os.path.join(Lounger.env, file_part_path[:-len(file_name) - 1])

    for root, _, files in os.walk(find_root_dir, topdown=False):
        for file in files:
            if root.endswith(file_part) and file == file_name:
                file_path = os.path.join(root, file_name)
                break
        else:
            continue
        break

    return file_path


def find_file(file: str, file_dir: Path) -> str:
    """
    find file
    :param file:
    :param file_dir:
    """
    if os.path.isfile(file) is True:
        return file

    if "/" in file or "\\" in file:
        file = file.replace("\\", "/")

        if Lounger.env is not None:
            file_path = _search_env_file_path(file_dir=file_dir, file_part_path=file)
            return file_path
        else:
            # Starting at file_dir, search up the 5 levels of parent directories
            for _ in range(5):
                current_dir = os.path.join(file_dir, file)
                if os.path.isfile(current_dir):
                    return current_dir
                file_dir = file_dir.parent  # Move up to the parent directory
            else:
                return ""
    else:
        file_path = _search_file_path(file_dir=file_dir, file_name=file)
        return file_path


def file_data(file: str, line: int = 1, sheet: str = "Sheet1", key: str = None, end_line: int = None):
    """
    Support file parametrize decorator.

    :param file: file name
    :param line: Start line number of an Excel/CSV file
    :param end_line:  End line number of an Excel/CSV file
    :param sheet: Excel sheet name
    :param key: Key name of an YAML/JSON file

    Usage:
    d.json
    ```json
    {
     "login":  [
        ["admin", "admin123"],
        ["guest", "guest123"]
     ]
    }
    ```
    >>  @file_data(file="d.json", key="login")
    ... def test_case(self, username, password):
    ...     print(username)
    ...     print(password)
    """
    if file is None:
        raise FileExistsError("File name does not exist.")

    stack_t = sys_inspect.stack()
    ins = sys_inspect.getframeinfo(stack_t[1][0])
    file_dir = Path(ins.filename).resolve().parent

    if Lounger.env is not None:
        log.info(f"env: '{Lounger.env}', find data file: '{file}'")
    else:
        log.info(f"find data file: {file}")

    file_path = find_file(file, file_dir)
    if file_path == "":
        if Lounger.env is not None:
            raise FileExistsError(f"No '{Lounger.env}/{file}' data file found.")
        raise FileExistsError(f"No '{file}' data file found.")

    suffix = file.split(".")[-1]
    if suffix == "csv":
        data_list = conversion.csv_to_list(file_path, line=line, end_line=end_line)
    elif suffix == "xlsx":
        data_list = conversion.excel_to_list(file_path, sheet=sheet, line=line, end_line=end_line)
    elif suffix == "json":
        data_list = conversion.json_to_list(file_path, key=key)
    elif suffix == "yaml":
        data_list = conversion.yaml_to_list(file_path, key=key)
    else:
        raise FileExistsError(f"Your file is not supported: {file}")

    return data(data_list)


def data(datas, ids: list = None, scope=None):
    """
    lounger parametrize decorator
    :param datas:
    :param ids:
    :param scope:
    :return:
    """
    if ids is None:
        ids = []

    if scope is None:
        scope = "function"

    return pytest.mark.parametrize(
        "params",
        datas,
        ids=ids,
        scope=scope)
