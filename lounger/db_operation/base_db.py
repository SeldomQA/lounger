"""
SQL API
"""
from typing import Any

from lounger.log import log


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
    def dict_to_str(data: dict) -> str:
        """
        dict to set str
        """
        tmp_list = []
        for key, value in data.items():
            if value is None:
                tmp = f"{key}=null"
            elif isinstance(value, int):
                tmp = f"{key}={value}"
            else:
                tmp = f"{key}='{value}'"
            tmp_list.append(tmp)
        return ','.join(tmp_list)

    @staticmethod
    def dict_to_str_and(conditions: dict) -> str:
        """
        dict to where and str
        """
        tmp_list = []
        for key, value in conditions.items():
            if value is None:
                tmp = f"{key}=null"
            elif isinstance(value, int):
                tmp = f"{key}={value}"
            else:
                tmp = f"{key}='{value}'"
            tmp_list.append(tmp)
        return ' and '.join(tmp_list)

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
