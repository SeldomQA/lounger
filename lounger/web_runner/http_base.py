"""
Shared HTTP plumbing for the Web Runner.

The runner serves every route through :class:`lounger.web_runner.api.PlatformHandler`.
This module holds only what that handler (and future handlers) actually share:
the threading server, quiet access logging for streamed endpoints, and the small
response helpers used across routes.

It intentionally contains no routing: the versioned platform API is the single
source of routes.
"""

from __future__ import annotations

import http.server
import json
from typing import Any


class BaseHandler(http.server.BaseHTTPRequestHandler):
    """Base request handler with the runner's shared response helpers."""

    # NOTE: no ``protocol_version`` override here. The runner has always answered
    # as HTTP/1.0 (one request per connection) and the streaming endpoints rely on
    # that: a client that navigates away aborts the connection, which ends the SSE
    # response naturally. Forcing HTTP/1.1 keep-alive changes connection reuse and
    # the ordering of concurrent browser requests.

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        """Suppress per-chunk access logging for streamed responses."""
        if self.path.startswith("/api/stream") or "/events" in self.path:
            return
        super().log_message(format, *args)

    def redirect(self, location: str) -> None:
        """Answer with a 302 to ``location``."""
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def sse_event(self, data: dict[str, Any]) -> None:
        """Write one Server-Sent-Event payload and flush it immediately."""
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()


class RunnerHTTPServer(http.server.ThreadingHTTPServer):
    """Threading server; several browser streams are open at once."""

    allow_reuse_address = True
    daemon_threads = True


#: Historical name kept so existing imports keep working.
_ThreadingHTTPServer = RunnerHTTPServer
