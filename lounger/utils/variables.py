import inspect
import importlib.util
from pathlib import Path
from typing import Any, Callable

from lounger.log import log
from lounger.settings import settings


class ExtractVar:
    """
    Extract variables
    """
    _instance = None
    _functions = {}
    _template_registry_name = "LOUNGER_TEMPLATE_FUNCTIONS"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_conftest_functions()
        return cls._instance

    def _load_conftest_functions(self):
        """
        Load the conftest function only once
        """
        conftest_path = Path("conftest.py")
        if not conftest_path.exists():
            log.debug("No conftest.py found, skip loading custom functions.")
            return

        try:
            spec = importlib.util.spec_from_file_location("conftest", conftest_path)
            conftest = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(conftest)

            registry = getattr(conftest, self._template_registry_name, None)
            if isinstance(registry, dict):
                for name, obj in registry.items():
                    if callable(obj):
                        self._functions[name] = obj
                        log.debug(f"🔧 Loaded registered template function: {name}")
                return

            for name, obj in inspect.getmembers(conftest, inspect.isfunction):
                if name.startswith("pytest_"):
                    continue
                if obj.__module__ != conftest.__name__:
                    continue
                self._functions[name] = obj
                log.debug(f"🔧 Loaded custom function: {name}")
        except Exception as e:
            log.error(f"Failed to load conftest.py: {e}")

    @classmethod
    def reset(cls) -> None:
        """
        Reset loaded custom functions.
        """
        cls._instance = None
        cls._functions = {}

    @staticmethod
    def config(key: str) -> Any:
        """
        Extract from the config file
        :param key:
        """
        return settings.get(key, node="global_test_config")

    @staticmethod
    def extract(key: str) -> Any:
        """
        Extract from the cache
        :param key：
        """
        from lounger.utils import cache
        return cache.get(key)

    def __getattr__(self, name: str) -> Callable:
        if name in self._functions:
            return self._functions[name]
        raise AttributeError(f"Function '{name}' not found")
