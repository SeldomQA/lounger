import os
import re
from typing import Any, Dict

from lounger.log import log
from lounger.utils import cache
from lounger.utils.variables import ExtractVar

# Precompile regex pattern for performance
TEMPLATE_PATTERN = re.compile(r"\$\{(.*?)\((.*?)\)}")

#: Any ``${name(...)}`` reference, used to collect template symbols from a case.
TEMPLATE_CALL_PATTERN = re.compile(r"\$\{\s*([a-zA-Z_]\w*)\s*\(")

#: Template functions lounger always provides (see ``ExtractVar``).
BUILTIN_TEMPLATE_FUNCTIONS = frozenset({"config", "extract"})

#: Environment switch: make an unresolved ``${...}`` reference a hard error at
#: collection time instead of a warning.
STRICT_ENV = "LOUNGER_STRICT_TEMPLATES"


class UndefinedTemplateFunction(LookupError):
    """Raised in strict mode when a case references an unregistered symbol."""


def _strict_mode() -> bool:
    return os.environ.get(STRICT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def undefined_template_functions(case_info: Any) -> list[str]:
    """
    Return the template symbols used by a case that are not registered.

    Resolution needs the real case data (a step cannot be validated in
    isolation), so this walks the structure and collects every ``${name(...)}``
    reference, then subtracts the registered functions and the built-ins.

    :param case_info: Case/step data (dict, list or scalar).
    :return: Sorted list of unregistered symbol names.
    """
    from lounger.runtime import get_all_template_funcs

    extract_var = ExtractVar()
    registered = set(get_all_template_funcs()) | set(vars(type(extract_var))) | BUILTIN_TEMPLATE_FUNCTIONS
    registered |= set(vars(extract_var))

    found: set[str] = set()
    stack: list[Any] = [case_info]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            found.update(TEMPLATE_CALL_PATTERN.findall(current))
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, (list, tuple, set)):
            stack.extend(current)

    return sorted(name for name in found if name not in registered)


def validate_template_functions(case_info: Any, context: str = "") -> list[str]:
    """
    Report (and in strict mode reject) unregistered template symbols in a case.

    Rendering cannot fail loudly — a case is data, and an unresolved reference
    used to become ``None``, silently injecting ``null`` into the request.
    Checking the *data* before it is rendered turns that into an explicit message
    naming the case and the symbol.

    :param case_info: Case/step data to inspect.
    :param context: Human-readable location (file / case name) for the message.
    :return: Sorted list of unregistered symbol names (empty when all are known).
    :raises UndefinedTemplateFunction: In strict mode (``LOUNGER_STRICT_TEMPLATES``).
    """
    missing = undefined_template_functions(case_info)
    if not missing:
        return []

    where = f" in {context}" if context else ""
    message = f"Undefined template function(s){where}: {', '.join(missing)}"
    if _strict_mode():
        raise UndefinedTemplateFunction(message)
    log.warning(f"{message}. The reference will be left as written in the request.")
    return missing


class _Unresolved:
    """Marker returned when a reference cannot be resolved."""

    __slots__ = ()


#: Sentinel: the reference is unknown/failed, so the caller must keep it as written.
UNRESOLVED = _Unresolved()


def _is_template_function(extract_var, name: str) -> bool:
    """True when ``name`` is a registered template function on ``extract_var``."""
    try:
        return hasattr(extract_var, name)
    except (AttributeError, KeyError):
        return False


def _render_function(extract_var, func_name: str, func_args: str) -> Any:
    """
    Call a template function, or :data:`UNRESOLVED` when it has no usable value.

    ``UNRESOLVED`` makes the caller keep the original ``${...}`` text. That covers
    a symbol that is not registered *and* one whose value does not exist — a
    ``${extract(missing)}`` used to become ``None``, which injected a literal
    ``null`` into the request with no hint of what went wrong. A broken reference
    now stays visible in the request and is reported.
    """
    if not _is_template_function(extract_var, func_name):
        log.warning(f"Function '{func_name}' not found; leaving ${{{func_name}({func_args})}} as written")
        return UNRESOLVED

    method = getattr(extract_var, func_name)
    try:
        # Parse arguments (supports $var syntax for cache lookup)
        args: list[Any] = []
        if func_args.strip():
            raw_args = [arg.strip() for arg in func_args.split(",")]
            for arg in raw_args:
                if arg.startswith("$") and len(arg) > 1:
                    var_value = cache.get(arg[1:])
                    args.append(var_value)
                else:
                    args.append(arg)

        result = method(*args) if args else method()
    except Exception as e:
        log.error(f"Failed to execute ${{{func_name}({func_args})}}: {e}")
        return UNRESOLVED

    if result is None:
        log.warning(
            f"${{{func_name}({func_args})}} resolved to None; leaving it as written. "
            "Check that the value was actually extracted/saved before it is used."
        )
        return UNRESOLVED

    log.info(f"Template replaced: ${{{func_name}({func_args})}} -> {result} (type: {type(result).__name__})")
    return result


def _render_handle_args(func, args):
    pattern = re.compile(r"\$\{([a-zA-Z_]\w*)\((.+)\)\}")
    match = pattern.match(args.strip())
    if match:
        func_name, func_args = match.groups()
        args = _render_handle_args(func_name, func_args)
    else:
        args = _render_function(ExtractVar(), func, args)
    return args


def _execute_method(value, match):
    """
    Render one matched template expression.

    Returns the original ``value`` untouched whenever the reference cannot be
    resolved, so an undefined reference never silently becomes ``null``.
    """
    func_name, func_args = match.groups()
    if '${' in func_args:
        origin_match = re.search(r"\$\{.*?\}", func_args)
        if origin_match is None:
            return value
        origin_args = origin_match.group(0)
        rendered = _render_handle_args(func_name, func_args)
        if rendered is UNRESOLVED:
            return value
        func_args = func_args.replace(origin_args, str(rendered))

    result = _render_function(ExtractVar(), func_name, func_args)
    return value if result is UNRESOLVED else result


def _render_value(value: str) -> Any:
    """
    Render one string value.

    A complete ``${func(args)}`` expression returns the resolved value with its
    original type; an expression embedded in surrounding text is substituted in
    place. When the reference cannot be resolved, the text is returned exactly as
    written (see :data:`UNRESOLVED`) instead of injecting ``null``.

    :param value: The input value (should be a string)
    """
    if not isinstance(value, str) or "${" not in value or "}" not in value:
        return value
    # Only match complete template expressions like ${func(args)}
    match = TEMPLATE_PATTERN.fullmatch(value.strip())

    if not match:
        match = TEMPLATE_PATTERN.search(value.strip())
        if not match:
            return value
        result = _execute_method(value, match)
        if result is value:
            # unresolved: ``_execute_method`` returned the input unchanged
            return value
        return value.replace(match.group(), str(result))
    return _execute_method(value, match)


def template_replace(case_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively traverse the test case data and replace template expressions
    (e.g., ${config(username)}, ${extract(token)}) with their evaluated values,
    preserving the original data types (e.g., int, bool, str).

    :param case_info: The test case data (dict)
    """

    def _walk(obj):
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_walk(item) for item in obj]
        elif isinstance(obj, str):
            return _render_value(obj)
        else:
            return obj

    return _walk(case_info)
