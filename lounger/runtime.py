"""
Lounger runtime: official registration point for template functions.

Template functions can be referenced in YAML test cases via ``${func_name(args)}``.
Register a function once, then use it by name in any template:

    from lounger.runtime import register_template_func

    def random_email():
        return "user@example.com"

    register_template_func("random_email", random_email)

The registry is consumed by :class:`lounger.utils.variables.ExtractVar` (and
through it by the YAML template engine). The legacy auto-scan of ``conftest.py``
functions is deprecated; prefer this explicit registration.
"""
from __future__ import annotations

from typing import Callable

from lounger.log import log

#: Canonical registry of template functions (name -> callable).
_template_functions: dict[str, Callable] = {}


def register_template_func(name: str, func: Callable) -> Callable:
    """
    Register a callable as a template function.

    The function becomes available in YAML templates as ``${name(args)}``.

    :param name: Template function name.
    :param func: The callable to register.
    :return: The registered callable (so it can also be used as a decorator).
    :raises TypeError: If ``func`` is not callable.
    """
    if not callable(func):
        raise TypeError(
            f"Template function '{name}' must be callable, got {type(func).__name__}"
        )
    _template_functions[name] = func
    log.debug(f"🔧 Registered template function: {name}")
    return func


def get_template_func(name: str) -> Callable:
    """
    Return a registered template function.

    :param name: Template function name.
    :return: The registered callable.
    :raises KeyError: If the function is not registered.
    """
    try:
        return _template_functions[name]
    except KeyError:
        raise KeyError(f"Template function '{name}' not registered") from None


def get_all_template_funcs() -> dict[str, Callable]:
    """Return a copy of all registered template functions."""
    return dict(_template_functions)


def clear_template_funcs() -> None:
    """Clear all registered template functions. Primarily for tests."""
    _template_functions.clear()
