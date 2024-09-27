import threading


class BrowserConfig:
    """
    Define run browser config
    """
    NAME = None
    REPORT_PATH = None
    REPORT_TITLE = "Lounger Test Report"
    LOG_PATH = None


class Lounger:
    env = None

    _thread_local = threading.local()

    @property
    def action(self):
        """
        playwright locator action
        """
        return getattr(self._thread_local, 'action', None)

    @action.setter
    def action(self, value):
        self._thread_local.action = value
