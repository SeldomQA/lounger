"""
Database resource management layer.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Optional

from lounger.db_operation.fabric_tunnel import FabricSSHTunnel


@dataclass
class MySQLConnectionConfig:
    """
    MySQL connection settings.
    """

    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"


@dataclass
class SSHTunnelConfig:
    """
    SSH tunnel settings for database forwarding.
    """

    ssh_host: str
    ssh_port: int
    ssh_user: str
    remote_host: str
    remote_port: int
    ssh_private_key: Optional[str] = None
    ssh_password: Optional[str] = None
    local_port: Optional[int] = None
    timeout: int = 10
    ready_timeout: float = 5.0


class MySQLResource:
    """
    Manage MySQL connection lifecycle with optional SSH tunnel.
    """

    def __init__(
            self,
            connection: MySQLConnectionConfig,
            tunnel: SSHTunnelConfig | None = None,
    ):
        self.connection_config = connection
        self.tunnel_config = tunnel
        self._tunnel: FabricSSHTunnel | None = None
        # MySQLDB is lazily imported inside connect(); typed as Any to avoid a circular import
        self._db: Any = None

    def connect(self):
        """
        Create and return a MySQLDB instance.
        """
        from lounger.db_operation.mysql_db import MySQLDB

        if self._db is not None:
            return self._db

        connect_config = self.connection_config
        if self.tunnel_config is not None:
            self._tunnel = FabricSSHTunnel(
                ssh_host=self.tunnel_config.ssh_host,
                ssh_port=self.tunnel_config.ssh_port,
                ssh_user=self.tunnel_config.ssh_user,
                remote_host=self.tunnel_config.remote_host,
                remote_port=self.tunnel_config.remote_port,
                ssh_private_key=self.tunnel_config.ssh_private_key,
                ssh_password=self.tunnel_config.ssh_password,
                local_port=self.tunnel_config.local_port,
                timeout=self.tunnel_config.timeout,
                ready_timeout=self.tunnel_config.ready_timeout,
            )
            tunnel_port = self._tunnel.start()
            connect_config = MySQLConnectionConfig(
                host="127.0.0.1",
                port=tunnel_port,
                user=self.connection_config.user,
                password=self.connection_config.password,
                database=self.connection_config.database,
                charset=self.connection_config.charset,
            )

        try:
            self._db = MySQLDB(
                host=connect_config.host,
                port=connect_config.port,
                user=connect_config.user,
                password=connect_config.password,
                database=connect_config.database,
                charset=connect_config.charset,
            )
        except Exception:
            self.close()
            raise

        self._db._ssh_tunnel = self._tunnel
        return self._db

    def close(self) -> None:
        """
        Close managed resources.
        """
        if self._db is not None:
            self._db.connection.close()
            self._db = None

        if self._tunnel is not None:
            self._tunnel.close()
            self._tunnel = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def _source_get(source: Callable[[str], Any] | Mapping[str, Any], key: str) -> Any:
    """
    Read a config value from a callable getter or mapping.
    """
    if callable(source):
        return source(key)
    return source.get(key)


def build_mysql_resource(
        source: Callable[[str], Any] | Mapping[str, Any],
        use_ssh_tunnel: bool | None = None,
) -> MySQLResource:
    """
    Build a MySQLResource from any config source.

    The source can be:
    - a callable such as `ExtractVar().config`
    - a mapping such as `dict` or parsed env/config object
    """
    ssh_host = _source_get(source, "ssh_host")
    remote_db_host = _source_get(source, "remote_db_host")
    if use_ssh_tunnel is None:
        use_ssh_tunnel = bool(ssh_host and remote_db_host)

    connection = MySQLConnectionConfig(
        host=_source_get(source, "db_host") or "127.0.0.1",
        port=int(_source_get(source, "db_port") or _source_get(source, "remote_db_port") or 3306),
        user=_source_get(source, "db_user"),
        password=_source_get(source, "db_password"),
        database=_source_get(source, "db_database"),
        charset=_source_get(source, "db_charset") or "utf8mb4",
    )

    tunnel = None
    if use_ssh_tunnel:
        tunnel = SSHTunnelConfig(
            ssh_host=ssh_host,
            ssh_port=int(_source_get(source, "ssh_port")),
            ssh_user=_source_get(source, "ssh_user"),
            ssh_private_key=_source_get(source, "ssh_private_key"),
            ssh_password=_source_get(source, "ssh_password"),
            remote_host=remote_db_host,
            remote_port=int(_source_get(source, "remote_db_port")),
            local_port=_source_get(source, "local_db_port"),
            timeout=int(_source_get(source, "ssh_timeout") or 10),
            ready_timeout=float(_source_get(source, "tunnel_ready_timeout") or 5.0),
        )

    return MySQLResource(connection=connection, tunnel=tunnel)
