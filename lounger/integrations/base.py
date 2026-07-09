"""
Base integration types for lounger.
"""
from __future__ import annotations

from typing import Optional, Protocol

from lounger.plugin_hooks import TestRunSummary


class SessionFinishIntegration(Protocol):
    """
    Protocol for post-run integrations.
    """

    def after_session_finish(self, summary: TestRunSummary) -> None:
        """
        Handle session finish summary.
        """

    def after_run_finish(self, report_path: Optional[str], summary: TestRunSummary) -> None:
        """
        Handle run finish with optional report path.
        """
