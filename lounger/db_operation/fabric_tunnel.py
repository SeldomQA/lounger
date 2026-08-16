"""
Fabric SSH tunnel helpers for database connections.
"""
import socket
import time
from pathlib import Path
from typing import Any, Optional

from lounger.log import log


def get_free_port() -> int:
    """
    Get an available random local port
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


class FabricSSHTunnel:
    """
    Manage a Fabric SSH local forwarding tunnel lifecycle.
    """

    def __init__(
            self,
            ssh_host: str,
            ssh_port: int,
            ssh_user: str,
            remote_host: str,
            remote_port: int,
            ssh_private_key: Optional[str] = None,
            ssh_password: Optional[str] = None,
            local_port: Optional[int] = None,
            timeout: int = 10,
            ready_timeout: float = 5.0,
            ready_interval: float = 0.1,
    ):
        self.ssh_host = ssh_host
        self.ssh_port = int(ssh_port)
        self.ssh_user = ssh_user
        self.remote_host = remote_host
        self.remote_port = int(remote_port)
        self.ssh_private_key = ssh_private_key
        self.ssh_password = ssh_password
        self.local_port = int(local_port) if local_port is not None else get_free_port()
        self.timeout = int(timeout)
        self.ready_timeout = float(ready_timeout)
        self.ready_interval = float(ready_interval)
        # fabric Connection and its forward_local context are dynamic (optional dep)
        self._connection: Any = None
        self._tunnel_ctx: Any = None

    def _wait_until_ready(self) -> None:
        """
        Wait until the local forwarded port starts accepting connections.
        """
        deadline = time.time() + self.ready_timeout
        last_error = None
        while time.time() < deadline:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.settimeout(self.ready_interval)
                probe.connect(("127.0.0.1", self.local_port))
                return
            except OSError as e:
                last_error = e
                time.sleep(self.ready_interval)
            finally:
                probe.close()

        raise TimeoutError(
            f"Fabric SSH tunnel local port 127.0.0.1:{self.local_port} "
            f"is not ready within {self.ready_timeout}s: {last_error}"
        )

    @staticmethod
    def _get_connection_cls():
        """
        Lazy import Fabric to keep it an optional dependency.
        """
        try:
            from fabric import Connection
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(
                "Please install the library. pip install fabric"
            ) from e
        return Connection

    def start(self) -> int:
        """
        Start SSH local forwarding tunnel
        """
        if self._connection is not None:
            return self.local_port

        connection_cls = self._get_connection_cls()
        connect_kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self.ssh_private_key:
            connect_kwargs["key_filename"] = str(Path(self.ssh_private_key).expanduser())
        if self.ssh_password:
            connect_kwargs["password"] = self.ssh_password

        self._connection = connection_cls(
            host=self.ssh_host,
            port=self.ssh_port,
            user=self.ssh_user,
            connect_kwargs=connect_kwargs,
        )
        self._tunnel_ctx = self._connection.forward_local(
            local_port=self.local_port,
            remote_port=self.remote_port,
            remote_host=self.remote_host,
        )
        self._tunnel_ctx.__enter__()
        self._wait_until_ready()
        log.info(
            f"🔐 Fabric SSH tunnel started: 127.0.0.1:{self.local_port} -> "
            f"{self.remote_host}:{self.remote_port}"
        )
        return self.local_port

    def close(self) -> None:
        """
        Close SSH tunnel and Fabric connection
        """
        if self._tunnel_ctx is not None:
            self._tunnel_ctx.__exit__(None, None, None)
            self._tunnel_ctx = None

        if self._connection is not None:
            self._connection.close()
            self._connection = None
            log.info("🔐 Fabric SSH tunnel and connection closed")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
