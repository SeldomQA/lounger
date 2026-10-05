"""
Front-end shell checks (tree behaviour, sidebar).

Asserted against the assets that are actually shipped
(``lounger/web_runner/static``). They used to run against an inlined copy the
runner produced for tests — a copy that omitted ``platform.js``/``platform.css``
while the served page referenced them, so the assertions could pass while the real
page was broken.
"""
from tests.conftest import shell_assets

ASSETS = shell_assets()


def test_web_runner_tree_defaults_to_collapsed():
    assert "let EXPANDED_NODES_KEY = 'lounger.webRunner.expandedNodes';" in ASSETS
    assert "'<div class=\"tree-node tree-dir' + (isOpen ? ' open' : '')" in ASSETS
    assert "'<div class=\"tree-children' + (isOpen ? ' show' : '')" in ASSETS


def test_web_runner_refresh_preserves_expand_state():
    assert "let expandedNodes = loadExpandedNodes();" in ASSETS
    assert "saveExpandedNodes();" in ASSETS
    assert "expandedNodes.has(header?.dataset.nodeKey || '')" in ASSETS
    assert "await loadCases();" in ASSETS


def test_web_runner_sidebar_is_resizable():
    assert 'class="sidebar-shell" id="sidebarShell"' in ASSETS
    assert 'class="sidebar-resizer" id="sidebarResizer"' in ASSETS
    assert "function startSidebarResize(event)" in ASSETS
    assert "let SIDEBAR_WIDTH_KEY = 'lounger.webRunner.sidebarWidth';" in ASSETS


def test_web_runner_theme_toggle_is_wired():
    assert 'id="themeToggle"' in ASSETS
    assert "function applyTheme(theme)" in ASSETS
