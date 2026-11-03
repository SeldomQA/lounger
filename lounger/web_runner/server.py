"""Compatibility imports for the Web Runner's shared HTTP implementation.

Routing and live run state belong to ``PlatformHandler`` and ``RunManager``.
Keep the historical server imports pointing to the production implementation.
"""

from .api import PlatformHandler as _RequestHandler
from .http_base import RunnerHTTPServer as _ThreadingHTTPServer

__all__ = ["_RequestHandler", "_ThreadingHTTPServer"]
