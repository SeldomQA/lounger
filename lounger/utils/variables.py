import importlib.util
import inspect
import warnings
from pathlib import Path
from typing import Any, Callable

from lounger.log import log
from lounger.runtime import (
    clear_template_funcs,
    get_all_template_funcs,
    get_template_func,
    register_template_func,
)
from lounger.settings import settings

#: Name of the explicit registry dict that conftest.py may define.
TEMPLATE_REGISTRY_NAME = "LOUNGER_TEMPLATE_FUNCTIONS"


class ExtractVar:
    """
    Extract variables and resolve template functions.

    Template functions are resolved through the official runtime registry
    (:func:`lounger.runtime.register_template_func`). For backwards
    compatibility, a ``conftest.py`` in the current working directory is still
    loaded: if it defines a ``LOUNGER_TEMPLATE_FUNCTIONS`` dict, its callables
    are registered; if it registers functions via ``register_template_func``,
    those are used as-is; otherwise all of its module-level functions are
    auto-scanned, which is **deprecated** (use the explicit registry or
    ``register_template_func`` instead).
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_conftest_functions()
        return cls._instance

    def _load_conftest_functions(self) -> None:
        """
        Load template functions from conftest.py (once per instantiation).

        Preference order:
        1. ``LOUNGER_TEMPLATE_FUNCTIONS`` dict (explicit registry);
        2. functions registered during conftest execution via
           :func:`lounger.runtime.register_template_func`;
        3. auto-scan of module-level functions (deprecated fallback).
        """
        conftest_path = Path("conftest.py")
        if not conftest_path.exists():
            log.debug("No conftest.py found, skip loading custom functions.")
            return

        try:
            spec = importlib.util.spec_from_file_location("conftest", conftest_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("Unable to create module spec for conftest.py")
            conftest = importlib.util.module_from_spec(spec)
            registered_before = set(get_all_template_funcs())
            spec.loader.exec_module(conftest)
            registered_during_exec = set(get_all_template_funcs()) - registered_before
        except Exception as e:
            log.error(f"Failed to load conftest.py: {e}")
            return

        registry = getattr(conftest, TEMPLATE_REGISTRY_NAME, None)
        if isinstance(registry, dict):
            for name, obj in registry.items():
                if callable(obj):
                    register_template_func(name, obj)
                    log.debug(f"🔧 Loaded registered template function: {name}")
            return

        if registered_during_exec:
            # conftest registered functions directly via the official API;
            # explicit registration replaces the auto-scan, no deprecation warning.
            log.debug(
                "Template functions registered via register_template_func() "
                "in conftest.py; skipping auto-scan."
            )
            return

        # Legacy auto-scan fallback (deprecated)
        warnings.warn(
            "Auto-scanning conftest.py functions for YAML templates is deprecated. "
            f"Define a '{TEMPLATE_REGISTRY_NAME}' dict in conftest.py or use "
            "lounger.runtime.register_template_func() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        for name, obj in inspect.getmembers(conftest, inspect.isfunction):
            if name.startswith("pytest_"):
                continue
            if obj.__module__ != conftest.__name__:
                continue
            register_template_func(name, obj)
            log.debug(f"🔧 Loaded custom function: {name}")

    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton and clear all registered template functions.
        Primarily for tests.
        """
        cls._instance = None
        clear_template_funcs()

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
        try:
            return get_template_func(name)
        except KeyError:
            raise AttributeError(f"Function '{name}' not found") from None
