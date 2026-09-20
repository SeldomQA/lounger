"""Lounger web test runner — lightweight HTTP interface for test execution.

Usage:
    from lounger.web_runner import main
    main(host="127.0.0.1", port=5000, scan_dir="myapi")

CLI access via:
    lounger runner [--host HOST] [--port PORT] [--project DIR] [--no-browser]
"""

import errno
import os
import socket
import threading
import webbrowser
from pathlib import Path

from lounger.log import log

from . import state
from .api import PlatformHandler as _RequestHandler
from .collect import get_test_cases  # noqa: F401 — public API
from .context import ProjectContext
from .manager import RunManager
from .server import _ThreadingHTTPServer

__all__ = ["main", "browser_url", "get_test_cases"]

#: Bind addresses that cannot be used as a browser URL.
_WILDCARD_HOSTS = ("", "0.0.0.0", "::", "[::]")

#: How many extra ports to try when the requested one is already in use.
_PORT_ATTEMPTS = 20

#: errno values meaning "someone else is already listening on this port".
_ADDRESS_IN_USE_ERRNOS = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE)}


def browser_url(host: str, port: int) -> str:
    """
    Return a browser-friendly URL for the runner.

    A wildcard bind address (``0.0.0.0`` / ``::`` / empty) is not reachable as
    a URL, so it is mapped to ``127.0.0.1``; bare IPv6 literals are bracketed.

    :param host: The bind address the server listens on.
    :param port: The port the server listens on.
    :return: A URL suitable for ``webbrowser.open``.
    """
    host = (host or "").strip()
    if host in _WILDCARD_HOSTS:
        host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"


def _auto_open_enabled() -> bool:
    """
    Whether opening a browser automatically makes sense here.

    CI runners have no display and no user to show a page to, so auto-open is
    skipped there (``--no-browser`` disables it explicitly as well).
    """
    return not os.environ.get("CI")


def _open_browser(url: str) -> None:
    """
    Open ``url`` in the user's default browser.

    Runs on a daemon thread and swallows every error: failing to launch a
    browser must never stop the runner from serving.
    """
    def _open() -> None:
        try:
            opened = webbrowser.open(url)
        except Exception as exc:  # pragma: no cover — platform dependent
            log.warning(f"   Could not open a browser automatically: {exc}")
            return
        if not opened:
            log.info(f"   No browser could be opened automatically — visit {url}")

    threading.Thread(target=_open, name="lounger-open-browser", daemon=True).start()


def _port_has_listener(host: str, port: int) -> bool:
    """Detect listeners before bind, including macOS wildcard SO_REUSEADDR sharing."""
    if port == 0:
        return False
    target = "127.0.0.1" if host in _WILDCARD_HOSTS else host.strip("[]")
    try:
        with socket.create_connection((target, port), timeout=0.2):
            return True
    except OSError:
        return False


def _bind_server(host: str, port: int):
    """
    Bind the runner, moving to the next free port when ``port`` is taken.

    A busy port used to surface as a raw ``OSError`` traceback. Instead the
    requested port is tried first, then the following ones, and a clear warning
    tells the user which port is actually used.

    :param host: Bind address.
    :param port: Preferred port (``0`` lets the OS pick any free port).
    :return: ``(server, bound_port)``.
    :raises SystemExit: If no free port could be found (friendly message, no
        traceback); the exit code is 1.
    """
    candidates = [port] + [port + offset for offset in range(1, _PORT_ATTEMPTS + 1)]
    for index, candidate in enumerate(candidates):
        try:
            if _port_has_listener(host, candidate):
                raise OSError(errno.EADDRINUSE, "An existing service is listening on this port")
            server = _ThreadingHTTPServer((host, candidate), _RequestHandler)
        except OSError as exc:
            if exc.errno not in _ADDRESS_IN_USE_ERRNOS:
                log.error(f"❌ Could not start the web runner on {host}:{candidate}: {exc}")
                raise SystemExit(1) from exc
            if index == 0:
                log.warning(f"⚠️  Port {port} is already in use — looking for a free port…")
            continue

        bound_port = server.server_address[1]
        if port != 0 and bound_port != port:
            log.warning(
                f"⚠️  Using port {bound_port} instead of {port} "
                f"(pass --port to pin a specific port)."
            )
        return server, bound_port

    log.error(
        f"❌ Ports {port}-{candidates[-1]} are all in use. "
        f"Free a port or start the runner with another one, e.g. "
        f"`lounger runner --port {candidates[-1] + 1}`."
    )
    raise SystemExit(1)


def main(
    host: str = "127.0.0.1",
    port: int = 5000,
    scan_dir: str = ".",
    open_browser: bool = True,
    data_dir: str | None = None,
):
    """Start the lounger web test runner.

    Args:
        host: Bind address.
        port: Port number.
        scan_dir: Project root directory (where config/config.yaml lives).
        open_browser: Open the runner in the default browser (skipped when the
            ``CI`` environment variable is set).
    """
    state._scan_dir = str(Path(scan_dir).resolve())

    server, bound_port = _bind_server(host, port)
    # Tests and third-party adapters can still supply lightweight server doubles.
    manager = None
    if hasattr(server, 'server_close'):
        import secrets
        try:
            manager = RunManager(ProjectContext.create(scan_dir, data_dir))
            manager.watch()
            server.manager = manager
            server.session_token = secrets.token_urlsafe(32)
        except Exception:
            server.server_close()
            if manager is not None:
                manager.close()
            raise

    url = browser_url(host, bound_port)
    log.info(f"🚀 lounger web runner → {url}")
    if url != f"http://{host}:{bound_port}":
        log.info(f"   Bound to: {host}:{bound_port}")
    log.info(f"   Project: {state._scan_dir}")

    if open_browser and _auto_open_enabled():
        log.info("   Opening in your default browser (disable with --no-browser).")
        _open_browser(url)

    log.info("   Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("👋 Shutting down.")
        # serve_forever has already exited; shutdown() here would deadlock on real servers.
        if manager is None:
            server.shutdown()

    finally:
        if manager is not None:
            # Release the listening socket before potentially slow worker/watcher cleanup.
            try:
                server.server_close()
            finally:
                manager.close()
