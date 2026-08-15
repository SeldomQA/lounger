"""
Unified database connection factory.

Central entry point for creating database connections across the supported
engines, without importing optional drivers eagerly. Importing this module
never requires ``pymssql`` / ``psycopg2`` — drivers are only imported when a
connection is actually created.

Usage::

    from lounger.db_operation import DatabaseFactory
    from lounger.db_operation.resource import MySQLConnectionConfig, SSHTunnelConfig

    # MySQL (optionally through an SSH tunnel)
    db = DatabaseFactory.mysql(
        connection=MySQLConnectionConfig(host=..., port=3306, user=..., password=..., database=...),
        tunnel=SSHTunnelConfig(ssh_host=..., ssh_port=22, ssh_user=...,
                               remote_host=..., remote_port=3306),  # optional
    )

    # PostgreSQL
    db = DatabaseFactory.postgres(host=..., port=5432, database=..., user=..., password=...)

    # SQL Server
    db = DatabaseFactory.mssql(server=..., user=..., password=..., database=...)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from lounger.db_operation.resource import MySQLConnectionConfig, MySQLResource, SSHTunnelConfig

if TYPE_CHECKING:
    from lounger.db_operation.mssql_db import MSSQLDB
    from lounger.db_operation.mysql_db import MySQLDB
    from lounger.db_operation.postgres_db import PostgresDB


class DatabaseFactory:
    """
    Unified database connection factory.

    Every factory method returns a connection object that supports ``close()``
    and the context-manager protocol where applicable.
    """

    @staticmethod
    def mysql(
        connection: MySQLConnectionConfig,
        tunnel: SSHTunnelConfig | None = None,
    ) -> "MySQLDB":
        """
        Create a MySQL connection, optionally through an SSH tunnel.

        The connection and tunnel lifecycles are managed by
        :class:`lounger.db_operation.resource.MySQLResource`.

        :param connection: MySQL connection settings.
        :param tunnel: Optional SSH tunnel settings.
        :return: A connected :class:`lounger.db_operation.mysql_db.MySQLDB`.
        """
        return MySQLResource(connection=connection, tunnel=tunnel).connect()

    @staticmethod
    def postgres(host: str, port: int, database: str, user: str, password: str) -> "PostgresDB":
        """
        Create a PostgreSQL connection.

        Requires the optional dependency: ``pip install lounger[db-postgres]``.

        :param host: Database host.
        :param port: Database port.
        :param database: Database name.
        :param user: Database user.
        :param password: Database password.
        :return: A connected :class:`lounger.db_operation.postgres_db.PostgresDB`.
        """
        from lounger.db_operation.postgres_db import PostgresDB
        return PostgresDB(host=host, port=port, database=database, user=user, password=password)

    @staticmethod
    def mssql(
        server: str,
        user: str,
        password: str,
        database: str,
        charset: str = "utf8mb4",
    ) -> "MSSQLDB":
        """
        Create a SQL Server connection.

        Requires the optional dependency: ``pip install lounger[db-mssql]``.

        :param server: SQL Server host.
        :param user: Database user.
        :param password: Database password.
        :param database: Database name.
        :param charset: Connection charset.
        :return: A connected :class:`lounger.db_operation.mssql_db.MSSQLDB`.
        """
        from lounger.db_operation.mssql_db import MSSQLDB
        return MSSQLDB(server=server, user=user, password=password, database=database, charset=charset)
