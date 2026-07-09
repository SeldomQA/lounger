from collections.abc import Callable
from typing import Any

from lounger.db_operation.resource import MySQLResource, build_mysql_resource


def create_mysql_resource(get_value: Callable[[str], Any]) -> MySQLResource:
    """
    Official recommended MySQL resource builder.

    The config source is intentionally left open-ended. `get_value` can read from
    ExtractVar, environment variables, a dict, a secrets manager, or any other source.
    """
    return build_mysql_resource(get_value)
