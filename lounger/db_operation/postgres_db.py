from typing import Any

from lounger.db_operation.base_db import SQLBase


def _get_psycopg2():
    """
    Import psycopg2 lazily so this module can be imported without the driver.
    The error only surfaces when a connection is actually created.
    """
    try:
        import psycopg2
        import psycopg2.extras
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "psycopg2 is required for PostgreSQL support. "
            "Install with: pip install lounger[db-postgres]"
        ) from e
    return psycopg2


class PostgresDB(SQLBase):

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        """
        Connect to Postgres database
        :param host:
        :param port:
        :param database:
        :param  user:
        :param password:
        """
        psycopg2 = _get_psycopg2()
        self.connection = psycopg2.connect(host=host, port=port, database=database, user=user, password=password)
        self.connection.autocommit = True

    def close(self):
        """
        Close the database connection
        """
        self.connection.close()

    def execute_sql(self, sql: str) -> None:
        """
        Execute SQL
        """
        self.log_execute_sql(sql)
        with self.connection.cursor() as cursor:
            cursor.execute(sql)

    def query_sql(self, sql: str) -> list:
        """
        Query SQL
        :return: query data

        """
        self.log_execute_sql(sql)
        data_list = []
        with self.connection.cursor(cursor_factory=_get_psycopg2().extras.DictCursor) as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            for row in rows:
                data_list.append(row)
            self.log_query_result(data_list)
            return data_list

    def query_one(self, sql: str) -> Any:
        """
        Query one row
        """
        self.log_execute_sql(sql)
        with self.connection.cursor(cursor_factory=_get_psycopg2().extras.DictCursor) as cursor:
            cursor.execute(sql)
            row = cursor.fetchone()
            self.log_query_result(row)
            return row

    def insert_get_last_id(self, sql: str) -> int:
        """
        insert sql and get last row id
        :param sql:
        :return:
        """
        self.log_execute_sql(sql)
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
            last_id = cursor.lastrowid
            return last_id

    def insert_data(self, table: str, data: dict) -> None:
        """
        insert sql statement
        """
        for key in data:
            data[key] = "'" + str(data[key]) + "'"
        key = ','.join(data.keys())
        value = ','.join(data.values())
        sql = f"INSERT INTO {table} ({key}) VALUES ({value})"
        self.execute_sql(sql)

    def select_data(self, table: str, where: dict | None = None, one: bool = False) -> Any:
        """
        Select SQL statement
        """
        sql = f"SELECT * FROM {table}"
        if where:
            where_clause = self.dict_to_str_and(where)
            sql += f" WHERE {where_clause}"

        return self.query_one(sql) if one else self.query_sql(sql)

    def update_data(self, table: str, data: dict, where: dict) -> None:
        """
        Update SQL statement
        """
        set_clause = self.dict_to_str(data)
        where_clause = self.dict_to_str_and(where)
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        self.execute_sql(sql)

    def delete_data(self, table: str, where: dict | None = None) -> None:
        """
        Delete SQL statement
        """
        sql = f"DELETE FROM {table}"
        if where:
            where_clause = self.dict_to_str_and(where)
            sql += f" WHERE {where_clause}"
        self.execute_sql(sql)

    def init_table(self, table_data: dict, clear: bool = True) -> None:
        """
        Initialize table data
        """
        for table, data_list in table_data.items():
            if clear:
                self.delete_data(table)
            for data in data_list:
                self.insert_data(table, data)
