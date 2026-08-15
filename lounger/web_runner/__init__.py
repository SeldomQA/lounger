"""Lounger web test runner — lightweight HTTP interface for test execution.

Usage:
    from lounger.web_runner import main
    main(host="127.0.0.1", port=5000, scan_dir="myapi")

CLI access via:
    lounger web [--host HOST] [--port PORT] [--project DIR]
"""

from pathlib import Path

from . import state
from .collect import get_test_cases  # noqa: F401 — public API
from .server import _RequestHandler, _ThreadingHTTPServer

__all__ = ["main", "get_test_cases"]


def main(host: str = "127.0.0.1", port: int = 5000, scan_dir: str = "."):
    """Start the lounger web test runner.

    Args:
        host: Bind address.
        port: Port number.
        scan_dir: Project root directory (where config/config.yaml lives).
    """
    state._scan_dir = str(Path(scan_dir).resolve())

    server = _ThreadingHTTPServer((host, port), _RequestHandler)
    print(f"🚀 lounger web runner → http://{host}:{port}")
    print(f"   Project: {state._scan_dir}")
    print("   Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down.")
        server.shutdown()
