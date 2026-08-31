"""Fallback HTML template for the web runner UI."""

_FALLBACK_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>lounger Test Runner</title>
<style>
:root {
  --bg: #1e1e2e; --surface: #282840; --border: #3a3a5c;
  --text: #cdd6f4; --muted: #6c7086; --accent: #89b4fa;
  --green: #a6e3a1; --red: #f38ba8; --yellow: #f9e2af;
  --radius: 8px; --indent: 18px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg); color: var(--text); height: 100vh; display: flex; }
/* ── sidebar ── */
.sidebar-shell { width: 420px; min-width: 280px; max-width: 70vw; display: flex; flex-shrink: 0; }
.sidebar { width: calc(100% - 6px); min-width: 0; background: var(--surface);
  border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.sidebar-resizer { width: 6px; cursor: col-resize; background: transparent; position: relative; flex-shrink: 0; }
.sidebar-resizer::after { content: ""; position: absolute; top: 0; bottom: 0; left: 2px; width: 2px;
  background: var(--border); transition: background .15s; }
.sidebar-resizer:hover::after, .sidebar-resizer.dragging::after { background: var(--accent); }
.sidebar-header { padding: 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px; }
.sidebar-header h1 { font-size: 18px; font-weight: 600; flex: 1; }
.logo { font-size: 24px; }
.toolbar { padding: 10px 16px; display: flex; gap: 8px; flex-wrap: wrap;
  border-bottom: 1px solid var(--border); }
.toolbar input { flex: 1; min-width: 120px; padding: 6px 10px;
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
  color: var(--text); font-size: 13px; outline: none; }
.toolbar input:focus { border-color: var(--accent); }
.btn { padding: 6px 14px; border: none; border-radius: var(--radius);
  cursor: pointer; font-size: 13px; font-weight: 500; transition: opacity .15s; }
.btn:hover { opacity: 0.85; }
.btn-accent { background: var(--accent); color: var(--bg); }
.btn-green { background: var(--green); color: var(--bg); }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn-sm { padding: 3px 8px; font-size: 11px; }
.btn-danger { background: var(--red); color: var(--bg); }
/* ── tag chips ── */
.tag-bar { padding: 6px 16px; border-bottom: 1px solid var(--border); display: flex;
  gap: 4px; flex-wrap: wrap; align-items: center; min-height: 32px; }
.tag-bar:empty { display: none; }
.tag-chip { padding: 2px 8px; border-radius: 12px; font-size: 11px; cursor: pointer;
  border: 1px solid var(--border); color: var(--muted); background: transparent;
  transition: all .15s; user-select: none; }
.tag-chip:hover { border-color: var(--accent); color: var(--text); }
.tag-chip.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }
.tag-chip.fav-chip { border-color: var(--yellow); color: var(--yellow); }
.tag-chip.fav-chip.active { background: var(--yellow); color: var(--bg); }
/* ── tree nodes ── */
.case-list { flex: 1; overflow-x: hidden; overflow-y: auto; padding: 4px 0; }
.tree-node { display: flex; align-items: center; gap: 6px; cursor: pointer;
  user-select: none; font-size: 13px; border-left: 3px solid transparent;
  min-height: 30px; padding-right: 10px; }
.tree-node:hover { background: rgba(255,255,255,.04); }
.tree-node.tree-dir { color: var(--accent); font-weight: 500; }
.tree-node.tree-file { color: var(--text); }
.tree-node.tree-case { color: var(--muted); }
.tree-node.tree-case.selected { background: rgba(137,180,250,.08); border-left-color: var(--accent); }
.tree-node.tree-case.just-run { background: rgba(166,227,161,.06); border-left-color: var(--green); }
.tree-toggle { width: 16px; height: 16px; display: inline-flex; align-items: center;
  justify-content: center; font-size: 10px; flex-shrink: 0;
  transition: transform .15s; color: var(--muted); }
.tree-node.open > .tree-toggle { transform: rotate(90deg); }
.tree-toggle.leaf { visibility: hidden; }
.tree-icon { width: 16px; text-align: center; flex-shrink: 0; font-size: 14px; }
.tree-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-label .count { color: var(--muted); font-size: 11px; margin-left: 4px; }
.tree-children { display: none; }
.tree-children.show { display: block; }
.tree-node input[type=checkbox] { accent-color: var(--accent); flex-shrink: 0; }
.run-btn { padding: 2px 8px; font-size: 11px; background: var(--accent);
  color: var(--bg); border: none; border-radius: 4px; cursor: pointer; opacity: 0;
  flex-shrink: 0; }
.tree-node:hover .run-btn { opacity: 1; }
.fav-btn { padding: 2px 6px; font-size: 12px; background: transparent; border: none;
  cursor: pointer; opacity: 0.4; flex-shrink: 0; transition: opacity .15s; }
.fav-btn:hover { opacity: 0.8; }
.fav-btn.is-fav { opacity: 1; color: var(--yellow); }
.tree-node:hover .fav-btn { opacity: 0.7; }
.tree-node .fav-btn.is-fav { opacity: 1; }
.empty-state { padding: 40px 20px; text-align: center; color: var(--muted); }
/* ── main ── */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.main-header { padding: 12px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px; font-size: 14px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.status-dot.running { background: var(--yellow); animation: pulse 1s infinite; }
.status-dot.done { background: var(--green); }
.status-dot.error { background: var(--red); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
/* ── tabs ── */
.tab-bar { display: flex; gap: 0; border-bottom: 1px solid var(--border); padding: 0 20px; }
.tab-btn { padding: 8px 16px; font-size: 13px; cursor: pointer; background: transparent;
  border: none; border-bottom: 2px solid transparent; color: var(--muted);
  transition: all .15s; }
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-panel { display: none; flex: 1; overflow: hidden; flex-direction: column; }
.tab-panel.active { display: flex; }
/* ── history ── */
.history-list { padding: 16px 20px; overflow-y: auto; flex: 1; }
.history-item { display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 8px;
  cursor: pointer; transition: background .15s; }
.history-item:hover { background: rgba(255,255,255,.03); }
.history-item .h-status { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.history-item .h-status.pass { background: var(--green); }
.history-item .h-status.fail { background: var(--red); }
.history-item .h-info { flex: 1; }
.history-item .h-id { font-weight: 500; font-size: 13px; }
.history-item .h-meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
.history-item .h-actions { display: flex; gap: 6px; }
.history-detail { padding: 0; flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.history-detail-header { padding: 12px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px; }
/* ── log ── */
.log-container { flex: 1; overflow-y: auto; padding: 16px 20px;
  background: #11111b; font-family: "SF Mono", "Fira Code", monospace;
  font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
.log-line { }
.log-line.pass { color: var(--green); }
.log-line.fail { color: var(--red); }
.log-line.warn { color: var(--yellow); }
.log-line.summary { color: var(--accent); font-weight: bold; }
.log-placeholder { color: var(--muted); text-align: center; padding: 60px 20px; }
.log-placeholder .icon { font-size: 48px; margin-bottom: 12px; }
/* ── scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(108,112,134,.35); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(108,112,134,.55); }
::-webkit-scrollbar-corner { background: transparent; }
* { scrollbar-width: thin; scrollbar-color: rgba(108,112,134,.35) transparent; }
</style>
</head>
<body>

<div class="sidebar-shell" id="sidebarShell">
  <div class="sidebar">
    <div class="sidebar-header">
      <span class="logo">🧪</span>
      <h1>lounger Test Runner</h1>
    </div>
    <div style="padding:8px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
      <span id="caseStats" style="font-size:12px;color:var(--muted)">📊 加载中...</span>
      <button class="btn btn-outline" onclick="refreshCases()" style="font-size:12px">🔄 刷新用例列表</button>
    </div>
    <div class="toolbar">
      <input type="text" id="search" placeholder="搜索用例名称..." oninput="filterCases()">
      <button class="btn btn-outline" onclick="selectAll()">全选</button>
      <button class="btn btn-outline" onclick="deselectAll()">取消</button>
    </div>
    <div class="toolbar">
      <button class="btn btn-green" onclick="runSelected()" id="runSelectedBtn" style="flex:1">▶ 执行选中</button>
      <button class="btn btn-accent" onclick="runAll()" id="runAllBtn" style="flex:1">▶▶ 执行全部</button>
    </div>
    <!-- tag filter bar -->
    <div class="tag-bar" id="tagBar"></div>
    <div class="case-list" id="caseList">
      <div class="empty-state">⏳ 正在收集用例...</div>
    </div>
  </div>
  <div class="sidebar-resizer" id="sidebarResizer" onmousedown="startSidebarResize(event)"></div>
</div>

<div class="main">
  <div class="main-header">
    <span class="status-dot" id="statusDot"></span>
    <span id="statusText">就绪</span>
    <span id="runCounter" style="font-size:12px;color:var(--muted)"></span>
    <span style="flex:1"></span>
    <span id="verbosityGroup" style="display:flex;align-items:center;gap:2px;font-size:12px;color:var(--muted)">
      <label style="cursor:pointer"><input type="radio" name="verbosity" value="quiet" onclick="setVerbosity('quiet')"> 静默</label>
      <label style="cursor:pointer;margin-left:6px"><input type="radio" name="verbosity" value="normal" onclick="setVerbosity('normal')"> 标准</label>
      <label style="cursor:pointer;margin-left:6px"><input type="radio" name="verbosity" value="verbose" onclick="setVerbosity('verbose')" checked> 详细</label>
      <label style="cursor:pointer;margin-left:6px"><input type="radio" name="verbosity" value="full" onclick="setVerbosity('full')"> 完整</label>
    </span>
    <button class="btn btn-outline" onclick="copyLogs()" id="copyBtn" style="display:none">📋 复制日志</button>
    <button class="btn btn-outline" onclick="clearLogs()" id="clearBtn" style="display:none">🧹 清空日志</button>
  </div>
  <!-- tab bar -->
  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('live')" id="tabLive">📺 实时日志</button>
    <button class="tab-btn" onclick="switchTab('history')" id="tabHistory">📜 历史记录</button>
  </div>
  <!-- live log panel -->
  <div class="tab-panel active" id="panelLive">
    <div class="log-container" id="logContainer">
      <div class="log-placeholder">
        <div class="icon">📋</div>
        <div>选择左侧用例，点击「执行」开始</div>
      </div>
    </div>
  </div>
  <!-- history panel -->
  <div class="tab-panel" id="panelHistory">
    <div class="history-list" id="historyList">
      <div class="log-placeholder">
        <div class="icon">📜</div>
        <div>暂无历史记录</div>
      </div>
    </div>
  </div>
  <!-- history detail panel -->
  <div class="tab-panel" id="panelHistoryDetail">
    <div class="history-detail">
      <div class="history-detail-header">
        <button class="btn btn-outline btn-sm" onclick="backToHistory()">← 返回列表</button>
        <span id="historyDetailTitle" style="font-weight:500"></span>
        <span style="flex:1"></span>
        <button class="btn btn-outline btn-sm" onclick="copyHistoryLogs()" id="copyHistoryBtn">📋 复制</button>
      </div>
      <div class="log-container" id="historyLogContainer"></div>
    </div>
  </div>
</div>

<script>
// ── state ──
let allCases = [];
let caseTree = null;
let selectedIds = new Set();
let currentRunId = null;
let eventSource = null;
let currentVerbosity = 'verbose';
function setVerbosity(v) { currentVerbosity = v; }
let lastRunIds = new Set();
const EXPANDED_NODES_KEY = 'lounger.webRunner.expandedNodes';
const SIDEBAR_WIDTH_KEY = 'lounger.webRunner.sidebarWidth';
const FAVORITES_KEY = 'lounger.webRunner.favorites';
let expandedNodes = loadExpandedNodes();
let favorites = loadFavorites();
let activeTagFilters = new Set();
let showFavoritesOnly = false;

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
    const logEl = document.getElementById('historyLogContainer');
    logEl.innerHTML = '';
    const logs = data.logs || [];
    for (const line of logs) {
      const div = document.createElement('div');
      div.className = 'log-line';
      if (line.includes('PASSED')) div.classList.add('pass');
      else if (line.includes('FAILED') || line.includes('ERROR')) div.classList.add('fail');
      else if (line.includes('WARNING') || line.includes('skipped')) div.classList.add('warn');
      else if (line.startsWith('──')) div.classList.add('summary');
      div.textContent = line;
      logEl.appendChild(div);
    }
    logEl.scrollTop = logEl.scrollHeight;
    showHistoryDetail();
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
  const el = document.getElementById('historyLogContainer');
  navigator.clipboard.writeText(el.innerText || '').catch(() => {});
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
    let hasVisible = false;
    group.querySelectorAll(':scope > .tree-node').forEach(r => {
      if (r.style.display !== 'none') hasVisible = true;
    });
    group.querySelectorAll('.tree-children').forEach(n => {
      n.querySelectorAll(':scope > .tree-node').forEach(r => {
        if (r.style.display !== 'none') hasVisible = true;
      });
    });

    if (hasVisible) {
      group.style.display = 'block';
      group.classList.add('show');
      const header = group.previousElementSibling;
      if (header && header.classList.contains('tree-node')) {
        header.classList.add('open');
        header.style.display = '';
      }
    } else if (hasFilters) {
      group.style.display = 'none';
      group.classList.remove('show');
    } else {
      group.style.display = '';
      const header = group.previousElementSibling;
      if (header && header.classList.contains('tree-node')) {
        const isOpen = expandedNodes.has(header.dataset.nodeKey || '');
        header.classList.toggle('open', isOpen);
        group.classList.toggle('show', isOpen);
        header.style.display = '';
      }
    }
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
    body: JSON.stringify({nodeids, verbosity: currentVerbosity})
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
  clearLogs();

  eventSource = new EventSource('/api/stream/' + data.run_id);
  const logEl = document.getElementById('logContainer');

  eventSource.onmessage = function(ev) {
    const msg = JSON.parse(ev.data);
    if (msg.heartbeat) return;
    if (msg.line) {
      const div = document.createElement('div');
      div.className = 'log-line';
      if (msg.line.includes('PASSED')) div.classList.add('pass');
      else if (msg.line.includes('FAILED') || msg.line.includes('ERROR')) div.classList.add('fail');
      else if (msg.line.includes('WARNING') || msg.line.includes('skipped')) div.classList.add('warn');
      else if (msg.line.startsWith('──')) div.classList.add('summary');
      div.textContent = msg.line;
      logEl.appendChild(div);
      logEl.scrollTop = logEl.scrollHeight;
    }
    if (msg.done) {
      eventSource.close();
      eventSource = null;
      document.getElementById('statusDot').className = 'status-dot ' +
        (msg.exit_code === 0 ? 'done' : 'error');
      document.getElementById('statusText').textContent =
        msg.exit_code === 0 ? '全部通过 ✅' : '执行失败 ❌ (exit ' + msg.exit_code + ')';
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
  const el = document.getElementById('logContainer');
  const text = el.innerText || '';
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
  document.getElementById('logContainer').innerHTML = '';
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

applySidebarWidth(loadSidebarWidth());
loadCases();
updateRunStatus();
</script>
</body>
</html>"""
