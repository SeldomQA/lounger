"""
MySQL DB API
"""
from typing import Any, Optional

from lounger.db_operation.base_db import SQLBase
from lounger.db_operation.fabric_tunnel import FabricSSHTunnel
from lounger.db_operation.resource import MySQLConnectionConfig, MySQLResource, SSHTunnelConfig


def _get_pymysql():
    """
    Import PyMySQL lazily so this module can be imported without the driver.
    The error only surfaces when a connection is actually created.
    """
    try:
        import pymysql
        import pymysql.cursors
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "PyMySQL is required for MySQL support. "
            "Install with: pip install lounger[db-mysql]"
        ) from e
    return pymysql


class MySQLDB(SQLBase):
    """MySQL DB table API"""

    def __init__(self, host: str, port: int, user: str, password: str, database: str, charset='utf8mb4'):
        """
        Connect to the MySQL database
        :param host:
        :param port:
        :param user:
        :param password:
        :param database:
        """
        pymysql = _get_pymysql()
        self.connection = pymysql.connect(host=host,
                                          port=int(port),
                                          user=user,
                                          password=password,
                                          database=database,
                                          charset=charset,
                                          cursorclass=pymysql.cursors.DictCursor)
        self._ssh_tunnel: Optional[FabricSSHTunnel] = None

    @classmethod
    def from_ssh_tunnel(
            cls,
            ssh_host: str,
            ssh_port: int,
            ssh_user: str,
            remote_db_host: str,
            remote_db_port: int,
            db_user: str,
            db_password: str,
            db_database: str,
            db_charset: str = "utf8mb4",
            ssh_private_key: Optional[str] = None,
            ssh_password: Optional[str] = None,
            local_port: Optional[int] = None,
            ssh_timeout: int = 10,
            tunnel_ready_timeout: float = 5.0,
    ) -> "MySQLDB":
        """
        Create a MySQL connection through a Fabric SSH tunnel
        """
        resource = MySQLResource(
            connection=MySQLConnectionConfig(
                host="127.0.0.1",
                port=local_port or 0,
                user=db_user,
                password=db_password,
                database=db_database,
                charset=db_charset,
            ),
            tunnel=SSHTunnelConfig(
                ssh_host=ssh_host,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                ssh_private_key=ssh_private_key,
                ssh_password=ssh_password,
                remote_host=remote_db_host,
                remote_port=remote_db_port,
                local_port=local_port,
                timeout=ssh_timeout,
                ready_timeout=tunnel_ready_timeout,
            ),
        )
        return resource.connect()

    @classmethod
    def from_resource(
            cls,
            resource: MySQLResource,
    ) -> "MySQLDB":
        """
        Create a MySQLDB instance from a managed resource.
        """
        return resource.connect()

    def close(self) -> None:
        """
        Close the database connection
        """
        self.connection.close()
        if self._ssh_tunnel is not None:
            self._ssh_tunnel.close()
            self._ssh_tunnel = None

    def __enter__(self) -> "MySQLDB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def execute_sql(self, sql: str) -> None:
        """
        Execute SQL
        """
        self.log_execute_sql(sql)
        with self.connection.cursor() as cursor:
            self.connection.ping(reconnect=True)
            if "delete" in sql.lower()[0:6]:
                cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
            cursor.execute(sql)
        self.connection.commit()

    def query_sql(self, sql: str) -> list:
        """
        Query SQL
        return: query data
        """
        self.log_execute_sql(sql)
        data_list = []
        with self.connection.cursor() as cursor:
            self.connection.ping(reconnect=True)
            cursor.execute(sql)
            rows = cursor.fetchall()
            for row in rows:
                data_list.append(row)
            self.connection.commit()
            self.log_query_result(data_list)
            return data_list

    def query_one(self, sql: str) -> Any:
        """
        Query one data SQL
        :return:
        """
        self.log_execute_sql(sql)
        with self.connection.cursor() as cursor:
            self.connection.ping(reconnect=True)
            cursor.execute(sql)
            row = cursor.fetchone()
            self.connection.commit()
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
            self.connection.ping(reconnect=True)
            cursor.execute(sql)
            last_id = cursor.lastrowid
            self.connection.commit()
            return last_id

    def insert_data(self, table: str, data: dict) -> None:
        """
        insert sql statement
        """
        for key in data:
            data[key] = "'" + str(data[key]) + "'"
        key = ','.join(data.keys())
        value = ','.join(data.values())
        sql = f"""insert into {table} ({key}) values ({value})"""
        self.execute_sql(sql)

    def select_data(self, table: str, where: dict | None = None, one: bool = False) -> Any:
        """
        select sql statement
        """
        sql = f"""select * from {table} """
        if where is not None:
            sql += f""" where {self.dict_to_str_and(where)}"""
        if one is True:
            return self.query_one(sql)

        return self.query_sql(sql)

    def update_data(self, table: str, data: dict, where: dict) -> None:
        """
        update sql statement
        """
        sql = f"""update {table} set """
        sql += self.dict_to_str(data)
        if where:
            sql += f""" where {self.dict_to_str_and(where)};"""
        self.execute_sql(sql)

    def delete_data(self, table: str, where: dict | None = None) -> None:
        """
        delete table data
        """
        sql = f"""delete from {table}"""
        if where is not None:
            sql += f""" where {self.dict_to_str_and(where)};"""
        self.execute_sql(sql)

    def init_table(self, table_data: dict, clear: bool = True) -> None:
        """
        init table data
        """
        for table, data_list in table_data.items():
            if clear:
                self.delete_data(table)
            for data in data_list:
                self.insert_data(table, data)
        self.close()
