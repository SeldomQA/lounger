// Theme is a browser preference shared by runner projects on this origin.
function applyTheme(theme) {
  const dark = theme !== 'light';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  const toggle = document.getElementById('themeToggle');
  toggle.setAttribute('aria-checked', String(dark));
  toggle.title = dark ? '切换到白天模式' : '切换到夜间模式';
}
applyTheme(document.documentElement.dataset.theme);
document.getElementById('themeToggle').onclick = () => {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(theme);
  try { localStorage.setItem('lounger.webRunner.theme', theme); } catch (_) {}
};
window.addEventListener('storage', event => {
  if (event.key === 'lounger.webRunner.theme' || event.key === null) applyTheme(event.newValue);
});


// ── state ──
let allCases = [];
let caseTree = null;
let selectedIds = new Set();
let currentRunId = null;
let eventSource = null;
let currentVerbosity = 'quiet';
function setVerbosity(v) { currentVerbosity = v; }
let lastRunIds = new Set();
let EXPANDED_NODES_KEY = 'lounger.webRunner.expandedNodes';
let SIDEBAR_WIDTH_KEY = 'lounger.webRunner.sidebarWidth';
let FAVORITES_KEY = 'lounger.webRunner.favorites';
let REPORT_ENABLED_KEY = 'lounger.webRunner.reportEnabled';
let expandedNodes = loadExpandedNodes();
let favorites = loadFavorites();
let activeTagFilters = new Set();
let showFavoritesOnly = false;
let reportEnabled = loadReportEnabled();
let currentReportUrl = null;
let currentHistoryRunId = null;

function loadReportEnabled() {
  try {
    const raw = localStorage.getItem(REPORT_ENABLED_KEY);
    return raw === null ? true : raw === 'true';   // on by default
  } catch(_) {
    return true;
  }
}

function setReportEnabled(enabled) {
  reportEnabled = !!enabled;
  try {
    localStorage.setItem(REPORT_ENABLED_KEY, String(reportEnabled));
  } catch(_) {}
}

function showReportButton(url) {
  currentReportUrl = url || null;
  const btn = document.getElementById('reportBtn');
  if (!btn) return;
  if (currentReportUrl) {
    btn.style.display = '';
    btn.title = '在新标签页打开本次运行的 HTML 报告';
  } else {
    btn.style.display = 'none';
    btn.removeAttribute('title');
  }
}

function openReport() {
  if (!currentReportUrl) return;
  window.open(currentReportUrl, '_blank', 'noopener');
}

/** Open the archived run's report (served from reports/runs/<id>.json entry). */
function openHistoryReport() {
  if (!currentHistoryRunId) return;
  window.open('/api/report/' + currentHistoryRunId, '_blank', 'noopener');
}

// ── windowed log views ────────────────────────────────────────────────────
// A chatty run can stream tens of thousands of log lines; appending one DOM
// node per line freezes the browser. Each log view keeps the full text in
// memory and renders only the visible window (plus overscan) inside a
// translated viewport, while a spacer element carries the real scroll height.
//
// LOG_LINE_HEIGHT must match `.log-line` height in the CSS, and lines must
// not wrap (`white-space: pre`) so the windowed offset math stays exact.
const LOG_LINE_HEIGHT = 21;
const LOG_OVERSCAN = 60;
const LOG_FOLLOW_SLACK = 24;
const LOG_MAX_LINES = 100000;

function _logLineNode(line) {
  const div = document.createElement('div');
  div.className = 'log-line';
  if (line.includes('PASSED')) div.classList.add('pass');
  else if (line.includes('FAILED') || line.includes('ERROR')) div.classList.add('fail');
  else if (line.includes('WARNING') || line.includes('skipped')) div.classList.add('warn');
  else if (line.startsWith('──')) div.classList.add('summary');
  div.textContent = line;
  return div;
}

function createLogView(containerId, spacerId, viewportId, placeholderHtml) {
  const container = document.getElementById(containerId);
  const spacer = document.getElementById(spacerId);
  const viewport = document.getElementById(viewportId);
  const notice = document.getElementById('logNotice');

  let lines = [];
  let pending = [];
  let flushFrame = null;
  let renderFrame = null;
  let follow = true;
  let trimmed = 0;

  function atBottom() {
    return container.scrollTop + container.clientHeight >= container.scrollHeight - LOG_FOLLOW_SLACK;
  }

  function reserveHeight() {
    spacer.style.height = (lines.length * LOG_LINE_HEIGHT) + 'px';
  }

  function render() {
    renderFrame = null;
    if (!lines.length) {
      spacer.style.height = '0px';
      viewport.style.transform = 'translateY(0px)';
      viewport.innerHTML = placeholderHtml || '';
      return;
    }
    const visibleRows = Math.ceil(container.clientHeight / LOG_LINE_HEIGHT);
    const start = Math.max(0, Math.floor(container.scrollTop / LOG_LINE_HEIGHT) - LOG_OVERSCAN);
    const end = Math.min(lines.length, start + visibleRows + LOG_OVERSCAN * 2);
    const fragment = document.createDocumentFragment();
    for (let i = start; i < end; i++) fragment.appendChild(_logLineNode(lines[i]));
    reserveHeight();
    viewport.style.transform = 'translateY(' + (start * LOG_LINE_HEIGHT) + 'px)';
    viewport.replaceChildren(fragment);
  }

  function schedule() {
    follow = atBottom();
    if (renderFrame === null) renderFrame = requestAnimationFrame(render);
  }

  function flush() {
    flushFrame = null;
    if (pending.length) {
      for (const line of pending) lines.push(line);
      pending.length = 0;
      if (lines.length > LOG_MAX_LINES) {
        trimmed += lines.length - LOG_MAX_LINES;
        lines.splice(0, lines.length - LOG_MAX_LINES);
        if (notice && !notice.textContent) {
          notice.textContent = '（已省略最早的 ' + trimmed + ' 行）';
        }
      }
    }
    if (follow) {
      // reserve the new height first, then pin the view to the bottom
      reserveHeight();
      container.scrollTop = container.scrollHeight;
    }
    render();
  }

  container.addEventListener('scroll', schedule);

  const view = {
    push(newLines) {
      if (!newLines || !newLines.length) return;
      pending.push(...newLines);
      if (flushFrame === null) flushFrame = requestAnimationFrame(flush);
    },
    /** Replace the whole content (history detail) and jump to the end. */
    setLines(newLines) {
      lines = (newLines || []).slice();
      pending = [];
      trimmed = 0;
      if (notice) notice.textContent = '';
      follow = true;
      reserveHeight();
      container.scrollTop = container.scrollHeight;
      render();
    },
    clear() {
      lines = [];
      pending = [];
      trimmed = 0;
      if (notice) notice.textContent = '';
      follow = true;
      viewport.innerHTML = placeholderHtml || '';
      spacer.style.height = '0px';
      viewport.style.transform = 'translateY(0px)';
    },
    /** Full text (not just the rendered window) — used by the copy buttons. */
    getText() { return lines.join('\n'); },
    count() { return lines.length; },
    atBottom,
    refresh: schedule,
  };

  if (placeholderHtml) view.clear();
  return view;
}

const liveLog = createLogView(
  'logContainer', 'logSpacer', 'logViewport',
  '<div class="log-placeholder"><div class="icon">📋</div>' +
  '<div>选择左侧用例，点击「执行」开始</div></div>'
);
const historyLog = createLogView(
  'historyLogContainer', 'historyLogSpacer', 'historyLogViewport', ''
);

window.addEventListener('resize', function() {
  liveLog.refresh();
  historyLog.refresh();
});

// ── localStorage helpers ──
function loadExpandedNodes() {
  try {
    const raw = localStorage.getItem(EXPANDED_NODES_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch(_) { return new Set(); }
}
function saveExpandedNodes() {
  try { localStorage.setItem(EXPANDED_NODES_KEY, JSON.stringify([...expandedNodes])); } catch(_) {}
}
function loadSidebarWidth() {
  try { return localStorage.getItem(SIDEBAR_WIDTH_KEY); } catch(_) { return null; }
}
function saveSidebarWidth(width) {
  try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width)); } catch(_) {}
}
function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch(_) { return new Set(); }
}
function saveFavorites() {
  try { localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favorites])); } catch(_) {}
}
function applySidebarWidth(width) {
  const shell = document.getElementById('sidebarShell');
  if (!shell || !width) return;
  shell.style.width = width + 'px';
}
function startSidebarResize(event) {
  event.preventDefault();
  const shell = document.getElementById('sidebarShell');
  const resizer = document.getElementById('sidebarResizer');
  if (!shell || !resizer) return;
  resizer.classList.add('dragging');
  function onMove(ev) {
    const minWidth = 280;
    const maxWidth = Math.min(window.innerWidth * 0.7, 900);
    const nextWidth = Math.max(minWidth, Math.min(maxWidth, ev.clientX));
    shell.style.width = nextWidth + 'px';
    saveSidebarWidth(nextWidth);
  }
  function onUp() {
    resizer.classList.remove('dragging');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// ── tabs ──
function switchTab(tab) {
  document.getElementById('tabLive').classList.toggle('active', tab === 'live');
  document.getElementById('tabHistory').classList.toggle('active', tab === 'history');
  document.getElementById('panelLive').classList.toggle('active', tab === 'live');
  document.getElementById('panelHistory').classList.toggle('active', tab === 'history');
  document.getElementById('panelHistoryDetail').classList.remove('active');
  if (tab === 'history') loadHistory();
}
function showHistoryDetail() {
  document.getElementById('panelHistory').classList.remove('active');
  document.getElementById('panelHistoryDetail').classList.add('active');
}
function backToHistory() {
  document.getElementById('panelHistoryDetail').classList.remove('active');
  document.getElementById('panelHistory').classList.add('active');
}

// ── history ──
async function loadHistory() {
  const container = document.getElementById('historyList');
  try {
    const resp = await fetch('/api/history');
    const runs = await resp.json();
    if (!runs.length) {
      container.innerHTML = '<div class="log-placeholder"><div class="icon">📜</div><div>暂无历史记录</div></div>';
      return;
    }
    let html = '';
    for (const r of runs) {
      const statusClass = r.exit_code === 0 ? 'pass' : 'fail';
      const statusText = r.exit_code === 0 ? '通过' : '失败';
      const timeStr = r.finished_at ? formatTime(r.finished_at) : (r.started_at ? formatTime(r.started_at) : '未知');
      const duration = (r.started_at && r.finished_at) ? formatDuration(r.finished_at - r.started_at) : '';
      html += '<div class="history-item" onclick="viewHistoryRun(\'' + esc(r.run_id) + '\')">';
      html += '<div class="h-status ' + statusClass + '"></div>';
      html += '<div class="h-info">';
      html += '<div class="h-id">' + esc(r.run_id) + ' <span style="font-size:11px;color:var(--muted)">' + statusText + '</span></div>';
      html += '<div class="h-meta">' + r.case_count + ' 用例';
      if (duration) html += ' · ' + duration;
      html += ' · ' + timeStr + '</div>';
      html += '</div>';
      html += '<div class="h-actions">';
      html += '<button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteHistoryRun(\'' + esc(r.run_id) + '\')">删除</button>';
      html += '</div></div>';
    }
    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = '<div class="log-placeholder"><div class="icon">❌</div><div>加载失败: ' + esc(e.message) + '</div></div>';
  }
}

async function viewHistoryRun(runId) {
  try {
    const resp = await fetch('/api/history/' + runId);
    if (!resp.ok) { alert('未找到该运行记录'); return; }
    const data = await resp.json();
    document.getElementById('historyDetailTitle').textContent = runId + ' — ' + (data.exit_code === 0 ? '全部通过 ✅' : '执行失败 ❌');
    // show the panel first so the container has a real height for windowing
    showHistoryDetail();
    historyLog.setLines(data.logs || []);
    currentHistoryRunId = data.report_path ? runId : null;
    const reportBtn = document.getElementById('historyReportBtn');
    if (reportBtn) reportBtn.style.display = currentHistoryRunId ? '' : 'none';
  } catch(e) {
    alert('加载失败: ' + e.message);
  }
}

async function deleteHistoryRun(runId) {
  if (!confirm('确定要删除此历史记录吗？')) return;
  try {
    await fetch('/api/history/' + runId, { method: 'DELETE' });
    loadHistory();
  } catch(e) {
    alert('删除失败: ' + e.message);
  }
}

function copyHistoryLogs() {
  // copy the whole archived log (not just the rendered window)
  navigator.clipboard.writeText(historyLog.getText()).catch(() => {});
}

function formatTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function formatDuration(seconds) {
  if (seconds < 1) return '< 1s';
  if (seconds < 60) return Math.round(seconds) + 's';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m + 'm ' + s + 's';
}

// ── fetch cases ──
async function loadCases() {
  try {
    const [casesResp, treeResp] = await Promise.all([
      fetch('/api/cases'),
      fetch('/api/tree')
    ]);
    allCases = await casesResp.json();
    const treeData = await treeResp.json();
    caseTree = treeData.tree;
    renderTree();
    renderTagBar();
  } catch(e) {
    document.getElementById('caseList').innerHTML =
      '<div class="empty-state">❌ 加载失败: ' + e.message + '</div>';
  }
}

function updateStats() {
  const stats = document.getElementById('caseStats');
  if (!allCases.length) {
    stats.textContent = '📭 未发现用例';
    return;
  }
  const yaml = allCases.filter(c => c.file && c.file.endsWith('.yaml')).length;
  const pytest = allCases.length - yaml;
  stats.innerHTML = '📊 共 <b>' + allCases.length + '</b> 用例 &nbsp;|&nbsp; pytest: <b>' + pytest + '</b> &nbsp;|&nbsp; YAML: <b>' + yaml + '</b>';
}

// ── tag bar ──
function renderTagBar() {
  const bar = document.getElementById('tagBar');
  const allMarks = new Set();
  for (const c of allCases) {
    const marks = c.markers || c.marks || [];
    for (const m of marks) allMarks.add(m);
  }
  let html = '';
  // favorites toggle
  html += '<span class="tag-chip fav-chip' + (showFavoritesOnly ? ' active' : '') + '" onclick="toggleFavoritesFilter()">⭐ 收藏</span>';
  for (const tag of [...allMarks].sort()) {
    const active = activeTagFilters.has(tag) ? ' active' : '';
    html += '<span class="tag-chip' + active + '" onclick="toggleTagFilter(\'' + esc(tag) + '\')">' + esc(tag) + '</span>';
  }
  bar.innerHTML = html;
}

function toggleTagFilter(tag) {
  if (activeTagFilters.has(tag)) activeTagFilters.delete(tag);
  else activeTagFilters.add(tag);
  renderTagBar();
  filterCases();
}

function toggleFavoritesFilter() {
  showFavoritesOnly = !showFavoritesOnly;
  renderTagBar();
  filterCases();
}

function toggleFavorite(nodeid, ev) {
  ev.stopPropagation();
  if (favorites.has(nodeid)) favorites.delete(nodeid);
  else favorites.add(nodeid);
  saveFavorites();
  renderTree();
  renderTagBar();
}

// ── tree rendering ──
function renderTree() {
  const container = document.getElementById('caseList');
  if (!allCases.length) {
    container.innerHTML = '<div class="empty-state">📭 未发现测试用例<br><small>请确认 config/config.yaml 配置正确</small></div>';
    updateStats();
    return;
  }
  let html = '';
  if (caseTree && caseTree.children) {
    for (const child of caseTree.children) {
      html += renderNode(child, 0);
    }
  }
  container.innerHTML = html;
  updateStats();
  if (document.getElementById('search').value || activeTagFilters.size > 0 || showFavoritesOnly) {
    filterCases();
  }
}

function renderNode(node, depth) {
  const indent = depth * 18;
  const key = nodeKey(node);
  const isOpen = expandedNodes.has(key);
  let html = '';

  if (node.type === 'dir') {
    const hasKids = node.children && node.children.length > 0;
    html += '<div class="tree-node tree-dir' + (isOpen ? ' open' : '') + '" data-node-key="' + esc(key) + '" onclick="toggleTreeNode(this)" style="padding-left:' + indent + 'px">';
    html += '<span class="tree-toggle' + (hasKids ? '' : ' leaf') + '">▶</span>';
    html += '<span class="tree-icon">📁</span>';
    html += '<span class="tree-label" title="' + esc(node.relpath || node.name) + '">' + esc(node.name);
    html += ' <span class="count">(' + node.total_cases + ')</span></span>';
    html += '</div>';
    if (hasKids) {
      html += '<div class="tree-children' + (isOpen ? ' show' : '') + '">';
      for (const child of node.children) {
        html += renderNode(child, depth + 1);
      }
      html += '</div>';
    }
  } else if (node.type === 'file') {
    const hasCases = node.cases && node.cases.length > 0;
    html += '<div class="tree-node tree-file' + (isOpen ? ' open' : '') + '" data-node-key="' + esc(key) + '" onclick="toggleTreeNode(this)" style="padding-left:' + indent + 'px">';
    html += '<span class="tree-toggle' + (hasCases ? '' : ' leaf') + '">▶</span>';
    html += '<span class="tree-icon">📄</span>';
    html += '<span class="tree-label" title="' + esc(node.relpath || node.name) + '">' + esc(node.name);
    if (hasCases) html += ' <span class="count">(' + node.case_count + ')</span>';
    html += '</span>';
    if (hasCases) {
      const idsJson = encodeURIComponent(JSON.stringify(node.cases.map(c => c.nodeid)));
      html += '<button class="run-btn" data-ids="' + idsJson + '" onclick="event.stopPropagation(); runFile(this.dataset.ids)" title="运行此文件全部用例">▶▶</button>';
    }
    html += '</div>';
    if (hasCases) {
      html += '<div class="tree-children' + (isOpen ? ' show' : '') + '">';
      for (const c of node.cases) {
        html += renderCaseNode(c, depth + 1);
      }
      html += '</div>';
    }
  }
  return html;
}

function renderCaseNode(c, depth) {
  const indent = depth * 18;
  const sel = selectedIds.has(c.nodeid) ? ' selected' : '';
  const runFlag = lastRunIds.has(c.nodeid) ? ' just-run' : '';
  const checked = selectedIds.has(c.nodeid) ? ' checked' : '';
  const isFav = favorites.has(c.nodeid);
  const desc = c.description ? c.description.trim() : '';
  const titleParts = [c.name];
  if (c.nodeid) titleParts.push(c.nodeid);
  if (desc) titleParts.push(desc);
  const tooltip = titleParts.join('\n');

  let html = '';
  html += '<div class="tree-node tree-case' + sel + runFlag + '" onclick="toggleCase(\'' + esc(c.nodeid) + '\', event)" style="padding-left:' + indent + 'px">';
  html += '<span class="tree-toggle leaf">▶</span>';
  html += '<input type="checkbox" ' + checked + ' onclick="event.stopPropagation(); toggleCase(\'' + esc(c.nodeid) + '\', event)">';
  html += '<span class="tree-label" title="' + esc(tooltip) + '">🧪 ' + esc(c.name) + '</span>';
  html += '<button class="fav-btn' + (isFav ? ' is-fav' : '') + '" onclick="toggleFavorite(\'' + esc(c.nodeid) + '\', event)" title="' + (isFav ? '取消收藏' : '收藏') + '">' + (isFav ? '⭐' : '☆') + '</button>';
  html += '<button class="run-btn" onclick="event.stopPropagation(); runSingle(\'' + esc(c.nodeid) + '\')">▶</button>';
  html += '</div>';
  return html;
}

function nodeKey(node) {
  return node.type + ':' + (node.relpath || node.name || '');
}

function toggleTreeNode(el) {
  const key = el.dataset.nodeKey;
  const isOpen = el.classList.toggle('open');
  if (key) {
    if (isOpen) expandedNodes.add(key);
    else expandedNodes.delete(key);
    saveExpandedNodes();
  }
  const children = el.nextElementSibling;
  if (children && children.classList.contains('tree-children')) {
    children.style.display = '';
    children.classList.toggle('show', isOpen);
  }
}

function toggleCase(nodeid, ev) {
  if (selectedIds.has(nodeid)) selectedIds.delete(nodeid);
  else selectedIds.add(nodeid);
  const row = ev.target.closest('.tree-node');
  if (row) {
    const cb = row.querySelector('input[type=checkbox]');
    if (cb) cb.checked = selectedIds.has(nodeid);
    row.classList.toggle('selected', selectedIds.has(nodeid));
  }
}

function selectAll() {
  for (const c of allCases) selectedIds.add(c.nodeid);
  renderTree();
}
function deselectAll() {
  selectedIds.clear();
  renderTree();
}

function caseMatchesFilters(c) {
  // favorites filter
  if (showFavoritesOnly && !favorites.has(c.nodeid)) return false;
  // tag filter (OR logic: case must have at least one active tag)
  if (activeTagFilters.size > 0) {
    const marks = new Set(c.markers || c.marks || []);
    let hasMatch = false;
    for (const t of activeTagFilters) {
      if (marks.has(t)) { hasMatch = true; break; }
    }
    if (!hasMatch) return false;
  }
  return true;
}

function filterCases() {
  const q = document.getElementById('search').value.toLowerCase();
  const container = document.getElementById('caseList');
  const allRows = container.querySelectorAll('.tree-node');
  const allGroups = container.querySelectorAll('.tree-children');

  // build a set of case nodeids that pass filters
  const visibleNodeids = new Set();
  for (const c of allCases) {
    const label = (c.name || '').toLowerCase();
    const textMatch = !q || label.includes(q);
    if (textMatch && caseMatchesFilters(c)) {
      visibleNodeids.add(c.nodeid);
    }
  }

  const hasFilters = q || activeTagFilters.size > 0 || showFavoritesOnly;

  allRows.forEach(row => {
    if (row.classList.contains('tree-case')) {
      // extract nodeid from the onclick handler
      const onclickAttr = row.getAttribute('onclick') || '';
      const m = onclickAttr.match(/toggleCase\('([^']+)'/);
      const nid = m ? m[1] : '';
      row.style.display = (!hasFilters || visibleNodeids.has(nid)) ? '' : 'none';
    }
  });

  allGroups.forEach(group => {
    const header = group.previousElementSibling;
    // Filtering temporarily expands matching branches. Never keep an inline
    // display:block: it overrides the collapse class after the filter clears.
    group.style.display = '';
    if (!hasFilters) {
      const isOpen = expandedNodes.has(header?.dataset.nodeKey || '');
      group.classList.toggle('show', isOpen);
      if (header) { header.classList.toggle('open', isOpen); header.style.display = ''; }
      return;
    }
    const hasVisible = [...group.querySelectorAll('.tree-case')].some(row => row.style.display !== 'none');
    group.classList.toggle('show', hasVisible);
    if (header) { header.classList.toggle('open', hasVisible); header.style.display = hasVisible ? '' : 'none'; }
  });

  if (hasFilters) {
    allRows.forEach(row => {
      if (!row.classList.contains('tree-case')) {
        const next = row.nextElementSibling;
        if (next && next.classList.contains('tree-children')) {
          let anyVis = false;
          next.querySelectorAll('.tree-node.tree-case').forEach(cs => {
            if (cs.style.display !== 'none') anyVis = true;
          });
          row.style.display = anyVis ? '' : 'none';
        }
      }
    });
  } else {
    allRows.forEach(row => { row.style.display = ''; });
  }
}

// ── execution ──
async function runSelected() {
  if (selectedIds.size === 0) { alert('请先选择测试用例'); return; }
  const ids = [...selectedIds];
  for (const nid of ids) lastRunIds.add(nid);
  renderTree();
  await startRun(ids);
}

async function runAll() {
  if (!allCases.length) return;
  await startRun(allCases.map(c => c.nodeid));
}

async function runSingle(nodeid) {
  lastRunIds.add(nodeid);
  renderTree();
  await startRun([nodeid]);
}

function runFile(nodeidsStr) {
  const ids = JSON.parse(decodeURIComponent(nodeidsStr));
  for (const nid of ids) lastRunIds.add(nid);
  renderTree();
  startRun(ids);
}

async function startRun(nodeids) {
  if (eventSource) { eventSource.close(); eventSource = null; }

  const resp = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({nodeids, verbosity: currentVerbosity, report: reportEnabled})
  });
  const data = await resp.json();
  if (data.error) { alert(data.error); return; }

  currentRunId = data.run_id;
  setRunButtonsDisabled(true);
  switchTab('live');
  document.getElementById('statusDot').className = 'status-dot running';
  document.getElementById('statusText').textContent = '运行中 (' + data.count + ' 用例)';
  document.getElementById('copyBtn').style.display = '';
  document.getElementById('clearBtn').style.display = '';
  showReportButton(null);   // a new run invalidates the previous report
  clearLogs();

  eventSource = new EventSource('/api/stream/' + data.run_id);

  eventSource.onmessage = function(ev) {
    const msg = JSON.parse(ev.data);
    if (msg.heartbeat) return;
    // the server batches lines ("lines"); single-line events stay supported
    const incoming = Array.isArray(msg.lines) ? msg.lines : (msg.line ? [msg.line] : []);
    if (incoming.length) liveLog.push(incoming);
    if (msg.done) {
      eventSource.close();
      eventSource = null;
      document.getElementById('statusDot').className = 'status-dot ' +
        (msg.exit_code === 0 ? 'done' : 'error');
      document.getElementById('statusText').textContent =
        msg.exit_code === 0 ? '全部通过 ✅' : '执行失败 ❌ (exit ' + msg.exit_code + ')';
      showReportButton(msg.report_url || null);
      setRunButtonsDisabled(false);
      updateRunStatus();
      loadCases();
    }
  };

  eventSource.onerror = function() {
    if (eventSource && eventSource.readyState === EventSource.CLOSED) {
      eventSource = null;
      setRunButtonsDisabled(false);
      updateRunStatus();
    }
  };
}

function setRunButtonsDisabled(disabled) {
  const btn1 = document.getElementById('runSelectedBtn');
  const btn2 = document.getElementById('runAllBtn');
  if (btn1) { btn1.disabled = disabled; btn1.style.opacity = disabled ? '0.5' : '1'; }
  if (btn2) { btn2.disabled = disabled; btn2.style.opacity = disabled ? '0.5' : '1'; }
}

async function updateRunStatus() {
  try {
    const resp = await fetch('/api/runs');
    const data = await resp.json();
    const counter = document.getElementById('runCounter');
    if (data.running) {
      counter.textContent = '🏃 运行中';
      counter.style.color = 'var(--yellow)';
    } else {
      counter.textContent = '✅ 就绪';
      counter.style.color = 'var(--muted)';
    }
  } catch(_) {}
}

function copyLogs() {
  // copy the whole log from the backing array, not the rendered window
  const text = liveLog.getText();
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copyBtn');
    const orig = btn.textContent;
    btn.textContent = '✅ 已复制';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    const btn = document.getElementById('copyBtn');
    const orig = btn.textContent;
    btn.textContent = '✅ 已复制';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}

function clearLogs() {
  liveLog.clear();
}

async function refreshCases() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '⏳ 刷新中...';
  try {
    lastRunIds.clear();
    await fetch('/api/refresh', {method: 'POST'});
    await loadCases();
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 刷新用例列表';
  }
}

function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

const reportToggleEl = document.getElementById('reportToggle');
if (reportToggleEl) reportToggleEl.checked = reportEnabled;
// Platform bootstrap restores project preferences and loads initial data.
