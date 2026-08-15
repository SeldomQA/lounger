import os
from pathlib import Path
from typing import Any, List, Tuple

from lounger.log import log
from lounger.settings import find_config_file, settings


def global_test_config(key: str) -> Any:
    """
    get global test config
    param: key
    """
    return settings.get(key, node="global_test_config")


def base_url() -> str:
    """
    Read the base URL lazily from the current settings.

    Unlike a module-level constant, this reflects config changes without a
    process restart (the YAML source is mtime-cached and re-read on change).
    """
    return settings.get("base_url")


class _LazyBaseUrl:
    """
    Lazy, non-breaking ``base_url`` compatibility object.

    ``lounger.commons.load_config.base_url`` was historically a module-level
    value (and before that, a ``base_url()`` function) and is used widely
    across projects.  This object keeps every usage working while reading the
    value lazily from settings on each access:

    - value usage:   ``base_url == "https://..."``, ``f"{base_url}/path"``
    - call usage:    ``base_url()`` (legacy function form)
    - str methods:   ``base_url.startswith("http")`` etc.
    """

    def __call__(self) -> Any:
        return settings.get("base_url")

    def _value(self) -> Any:
        return settings.get("base_url")

    def __str__(self) -> str:
        return str(self._value())

    def __repr__(self) -> str:
        return repr(self._value())

    def __format__(self, format_spec: str) -> str:
        return format(self._value(), format_spec)

    def __eq__(self, other: Any) -> bool:
        return self._value() == other

    def __ne__(self, other: Any) -> bool:
        return self._value() != other

    def __hash__(self) -> int:
        return hash(self._value())

    def __bool__(self) -> bool:
        return bool(self._value())

    def __add__(self, other: Any) -> str:
        return self._value() + other

    def __radd__(self, other: Any) -> str:
        return other + self._value()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._value(), name)


#: Compat layer: historically a module-level constant, then a ``base_url()``
#: function.  Now a lazy proxy — reads settings on every access, so config
#: edits take effect without a process restart.
base_url = _LazyBaseUrl()


class LoadConfig:
    def __init__(self):
        self.test_project = settings.get("test_project", default={}) or {}

    @classmethod
    def get_project_root(cls) -> str:
        """
        Return the project root directory, anchored to config/config.yaml.

        The config file is the framework's fixed anchor — always located at
        <project_root>/config/config.yaml.  It is found by walking up from the
        current working directory, so the result is independent of the
        directory pytest is launched from.
        """
        config_file = find_config_file()
        if config_file is None:
            return str(Path.cwd())
        return str(config_file.parent.parent)

    def get_project_config(self) -> Tuple[List[str], List[str]]:
        """
        Get project run configuration to determine which projects need to be tested

        :return: Tuple containing two lists: projects to test and projects to skip
        """
        # Store projects that need to be tested
        need_test_projects: List[str] = []
        # Store projects that don't need to be tested
        skip_test_projects: List[str] = []

        # Determine which projects need to be tested
        for project_name, project_value in self.test_project.items():
            if project_value:
                need_test_projects.append(project_name)
            else:
                skip_test_projects.append(project_name)

        return need_test_projects, skip_test_projects

    def get_project_name(self) -> List[str]:
        """
        Get list of project names from the test project configuration.

        :return: List of project names
        """
        # Extract project names from the test project configuration keys
        return list(self.test_project.keys())

    def get_case_path(self) -> List[str]:
        """
        Get test case paths based on project configuration
        """
        log.info("=== Reading Test Configuration ===")
        project_name_list = self.get_project_name()
        try:
            need_test_projects, skip_test_projects = self.get_project_config()
            log.info(f"Running tests: {need_test_projects}")
            log.info(f"Skipped tests: {skip_test_projects}")

            if not need_test_projects:
                log.warning("No projects configured for testing")
                return []

            # Get execute YAML files
            valid_need_projects = [proj for proj in need_test_projects if proj in project_name_list]
            all_paths = self._get_specific_test_cases(valid_need_projects, project_name_list)

            # === Sort: global_setup | normal | global_teardown ===
            setup_paths = []
            teardown_paths = []
            normal_paths = []

            for path in all_paths:
                abs_path = os.path.abspath(path)
                norm_path = abs_path.replace("/", os.sep).lower()

                if "global_setup" in norm_path:
                    setup_paths.append(abs_path)
                elif "global_teardown" in norm_path:
                    teardown_paths.append(abs_path)
                else:
                    normal_paths.append(abs_path)
            normal_paths = sorted(normal_paths)
            sorted_paths = setup_paths + normal_paths + teardown_paths

            return sorted_paths
        except Exception as e:
            log.error(f"Failed to get test case paths: {e}")
            return []

    @staticmethod
    def _get_specific_test_cases(need_test_projects: List[str], supported_projects: List[str]) -> List[str]:
        """
        Get test cases for specific projects

        :param need_test_projects: List of projects to test
        :param supported_projects: List of supported projects
        :return: List of test case paths
        """
        case_paths = []

        for project_name in need_test_projects:
            if project_name in supported_projects:
                # Get all test cases under the specified project
                project_cases = [
                    str(path.as_posix())
                    for path in Path("datas", project_name).rglob("*.yaml")
                    if path.stem.startswith("test_") or path.stem.endswith("_test")
                ]

                case_paths.extend(project_cases)

        return case_paths
