"""
SQL API
"""
from typing import Any

from lounger.log import log

#: SQL NULL keyword; kept explicit so the generated text is dialect-neutral.
SQL_NULL = "null"


class SQLBase:
    """SQL base API"""

    @staticmethod
    def log_execute_sql(sql: str) -> None:
        """
        Log SQL before execution
        """
        log.info(f"🗄️ Execute SQL: {sql}")

    @staticmethod
    def log_query_result(result: Any) -> None:
        """
        Log query result after execution
        """
        log.info(f"📥 Query result for SQL: {result}")

    @staticmethod
    def value_literal(value: Any) -> str:
        """
        Render one Python value as a SQL literal.

        Strings are single-quoted with embedded quotes doubled, which is the
        standard SQL escape (and what SQLite/MySQL/PostgreSQL/SQL Server all
        accept). Previously the value was interpolated verbatim, so ``O'Brien``
        produced a syntax error and ``x' OR 1=1 --`` changed the meaning of the
        statement.

        :param value: Value to render.
        :return: SQL literal text (``None`` -> ``null``, numbers unquoted).
        """
        if value is None:
            return SQL_NULL
        if isinstance(value, bool):
            # bool is an int subclass; keep the SQL keyword rather than 0/1.
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    @classmethod
    def dict_to_str(cls, data: dict) -> str:
        """
        Render a mapping as a comma-separated ``key=value`` list (for SET).
        """
        return ",".join(f"{key}={cls.value_literal(value)}" for key, value in data.items())

    @classmethod
    def dict_to_str_and(cls, conditions: dict) -> str:
        """
        Render a mapping as a ``key=value`` list joined by ``and`` (for WHERE).
        """
        return " and ".join(f"{key}={cls.value_literal(value)}" for key, value in conditions.items())

    @classmethod
    def insert_clause(cls, data: dict) -> tuple[str, str]:
        """
        Render an ``INSERT`` column list and value list.

        The input mapping is never modified: the previous implementation rewrote
        the caller's dict in place (wrapping values in quotes), so a second use
        of the same dict produced values like ``''x''``.

        :param data: Mapping of column -> value.
        :return: ``(columns, values)``, both comma-separated and ready to
            interpolate into ``insert into <table> (columns) values (values)``.
        """
        if not data:
            raise ValueError("insert requires at least one column")
        columns = ",".join(str(key) for key in data)
        values = ",".join(cls.value_literal(value) for value in data.values())
        return columns, values

    def delete(self, table: str, where: dict | None = None) -> None:
        """
        delete table data
        """
        # delete_data is implemented on concrete SQL subclasses
        return self.delete_data(table, where)  # type: ignore[attr-defined]

    def insert(self, table: str, data: dict) -> None:
        """
        insert sql statement
        """
        # insert_data is implemented on concrete SQL subclasses
        return self.insert_data(table, data)  # type: ignore[attr-defined]

    def select(self, table: str, where: dict | None = None, one: bool = False) -> list:
        """
        select sql statement
        """
        # select_data is implemented on concrete SQL subclasses
        return self.select_data(table, where, one)  # type: ignore[attr-defined]

    def update(self, table: str, data: dict, where: dict) -> None:
        """
        update sql statement
        """
        # update_data is implemented on concrete SQL subclasses
        return self.update_data(table, data, where)  # type: ignore[attr-defined]

    def __enter__(self):
        """
        Context manager entry: return the connection itself.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Context manager exit: always close the connection.
        """
        # close is implemented on concrete SQL subclasses
        self.close()  # type: ignore[attr-defined]
