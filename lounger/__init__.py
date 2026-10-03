#!/usr/bin/python
#
# Licensed to the Software Freedom Conservancy (SFC) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The SFC licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from typing import Any

__version__ = "1.7.1"

__all__ = ["data", "file_data", "__version__"]

#: Public callables resolved lazily from :mod:`lounger.pytest_extend.params`.
_LAZY_EXPORTS = ("data", "file_data")


def __getattr__(name: str) -> Any:
    """
    Resolve the lazy public names of this package on first access.

    Two concerns are handled here:

    1. ``lounger.data`` / ``lounger.file_data`` — importing this package must
       **not** import :mod:`pytest_req`. ``lounger`` is loaded as a ``pytest11``
       entry-point plugin, and ``pytest_req.log`` infers its log directory from
       the *caller's* frame at import time (``inspect.stack()[1]``). When that
       import happened here, the caller frame was
       ``_pytest/assertion/rewrite.py``, so the dependency tried to create
       ``<site-packages>/_pytest/assertion/logs/`` and the whole pytest session
       aborted with ``PermissionError`` before running a single test.
    2. ``lounger.log`` — ``from lounger.log import log`` first tries to import
       ``lounger.log`` as a *submodule*. This package intentionally has no
       ``log.py``, so the interpreter falls back to ``getattr(lounger, "log")``;
       returning the lazy module here makes that idiom work without depending on
       that fallback (``import lounger.log`` still fails, as there is no module).

    Keeping this package import side-effect free makes the entry-point load safe,
    while ``data`` / ``file_data`` / ``log`` stay public API.
    """
    if name in _LAZY_EXPORTS:
        from .pytest_extend import params

        value = getattr(params, name)
        globals()[name] = value  # cache: later lookups skip __getattr__
        return value
    if name == "log":
        from . import log as _log_module

        globals()[name] = _log_module  # cache: later lookups skip __getattr__
        return _log_module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
