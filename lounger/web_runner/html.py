"""Compatibility export of the packaged runner page."""

from importlib.resources import files

_resources = files("lounger.web_runner").joinpath("static")
_FALLBACK_HTML = (
    _resources.joinpath("index.html")
    .read_text(encoding="utf-8")
    .replace(
        '<link rel="stylesheet" href="/static/runner.css">',
        "<style>" + _resources.joinpath("runner.css").read_text(encoding="utf-8") + "</style>",
    )
    .replace(
        '<script src="/static/runner.js"></script>',
        "<script>" + _resources.joinpath("runner.js").read_text(encoding="utf-8") + "</script>",
    )
)
