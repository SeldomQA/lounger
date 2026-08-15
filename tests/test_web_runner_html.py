from lounger.web_runner.html import _FALLBACK_HTML


def test_web_runner_tree_defaults_to_collapsed():
    assert "const EXPANDED_NODES_KEY = 'lounger.webRunner.expandedNodes';" in _FALLBACK_HTML
    assert "'<div class=\"tree-node tree-dir' + (isOpen ? ' open' : '')" in _FALLBACK_HTML
    assert "'<div class=\"tree-children' + (isOpen ? ' show' : '')" in _FALLBACK_HTML


def test_web_runner_refresh_preserves_expand_state():
    assert "let expandedNodes = loadExpandedNodes();" in _FALLBACK_HTML
    assert "saveExpandedNodes();" in _FALLBACK_HTML
    assert "expandedNodes.has(header.dataset.nodeKey || '')" in _FALLBACK_HTML
    assert "await loadCases();" in _FALLBACK_HTML


def test_web_runner_sidebar_is_resizable():
    assert 'class="sidebar-shell" id="sidebarShell"' in _FALLBACK_HTML
    assert 'class="sidebar-resizer" id="sidebarResizer"' in _FALLBACK_HTML
    assert "function startSidebarResize(event)" in _FALLBACK_HTML
    assert "const SIDEBAR_WIDTH_KEY = 'lounger.webRunner.sidebarWidth';" in _FALLBACK_HTML
